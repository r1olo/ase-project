"""
Comprehensive Locust suite for the entire platform.

Coverage (mirrors integration Postman flow):
- Auth: happy path + token refresh.
- Players: create/update profile, lookup by id/username, friendships (request, accept, list).
- Catalogue: list, single card, missing card.
- Matchmaking: enqueue → status polling → dequeue (both success and TooLate),
  match setup through the game engine.
- Game engine: deck submission, five rounds of moves, round status, match snapshot,
  full history, per-player history, and leaderboard.

Configuration (env vars):
- GATEWAY_URL: base URL (default: https://localhost). Override with `-H` as usual.
- LOCUST_VERIFY_TLS: "true"/"false" (default false) for self-signed gateways.
- LOCUST_REQUEST_TIMEOUT: seconds per request (default 8).
- LOCUST_MATCH_POLL_RETRIES: attempts when waiting for a match (default 10).
- LOCUST_MATCH_POLL_INTERVAL: seconds between status polls (default 0.8).
"""
from __future__ import annotations

import os
import random
import threading
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import gevent
from locust import HttpUser, between, task

# ---- Configuration ----

GATEWAY_URL = os.getenv("GATEWAY_URL", "https://localhost")
VERIFY_TLS = os.getenv("LOCUST_VERIFY_TLS", "false").lower() in {"1", "true", "yes", "on"}
REQUEST_TIMEOUT = float(os.getenv("LOCUST_REQUEST_TIMEOUT", "8"))
MATCH_POLL_RETRIES = int(os.getenv("LOCUST_MATCH_POLL_RETRIES", "10"))
MATCH_POLL_INTERVAL = float(os.getenv("LOCUST_MATCH_POLL_INTERVAL", "0.8"))

# Regions copied from players.models.Region
REGIONS = [
    "Abruzzo",
    "Basilicata",
    "Calabria",
    "Campania",
    "Emilia-Romagna",
    "Friuli-Venezia Giulia",
    "Lazio",
    "Liguria",
    "Lombardia",
    "Marche",
    "Molise",
    "Piemonte",
    "Puglia",
    "Sardegna",
    "Sicilia",
    "Toscana",
    "Trentino-Alto Adige",
    "Umbria",
    "Valle d'Aosta",
    "Veneto",
]

# Decks and moves from Postman integration collection
DECK1 = [8, 9, 12, 16, 7]
DECK2 = [4, 15, 13, 14, 5]
MISSING_CARD_ID = 99999
INVALID_DECK = [-1, -2, -3]


# ---- Shared state helpers ----

@dataclass
class PlayerCtx:
    email: str
    password: str
    username: str
    region: str
    user_id: Optional[int] = None
    jwt: Optional[str] = None
    refresh_cookies: Dict[str, str] = field(default_factory=dict)
    last_queue_token: Optional[str] = None
    last_match_id: Optional[int] = None


players_lock = threading.Lock()
players_registry: List[PlayerCtx] = []


def _rand_email() -> str:
    return f"locust_{uuid.uuid4().hex[:10]}@example.com"


def _rand_username(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:6]}"


# ---- Locust user ----


class FullSystemUser(HttpUser):
    """
    Each Locust user owns two player identities so matchmaking and friendships
    can run without coordinating across workers.
    """

    host = GATEWAY_URL
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        # Configure TLS verification once for this client session
        self.client.verify = VERIFY_TLS
        self.did_dequeue_once = False

        self.player1 = PlayerCtx(
            email=_rand_email(),
            password="Passw0rd!",
            username=_rand_username("alpha"),
            region=random.choice(REGIONS),
        )
        self.player2 = PlayerCtx(
            email=_rand_email(),
            password="Passw0rd!",
            username=_rand_username("beta"),
            region=random.choice(REGIONS),
        )

        for player in (self.player1, self.player2):
            self._register_login_profile(player)
            self._store_player(player)

    # ---- HTTP helpers ----

    def _request(
        self,
        method: str,
        path: str,
        *,
        player: Optional[PlayerCtx] = None,
        name: Optional[str] = None,
        expected: Optional[Tuple[int, ...]] = None,
        **kwargs,
    ):
        headers = kwargs.pop("headers", {}) or {}
        if player and player.jwt:
            headers.setdefault("Authorization", f"Bearer {player.jwt}")
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        with self.client.request(
            method, path, headers=headers, name=name, catch_response=True, **kwargs
        ) as resp:
            ok_codes = expected or tuple(range(200, 300))
            if resp.status_code in ok_codes:
                resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")
            return resp

    def _register_login_profile(self, player: PlayerCtx) -> None:
        self._request(
            "POST",
            "/register",
            json={"email": player.email, "password": player.password},
            name="auth_register",
        )
        resp = self._request(
            "POST",
            "/login",
            json={"email": player.email, "password": player.password},
            name="auth_login",
        )
        if resp and resp.ok:
            payload = self._safe_json(resp)
            player.jwt = payload.get("access_token")
            player.user_id = payload.get("user_id")
            player.refresh_cookies = self.client.cookies.get_dict()
        # Clear cookies so refresh is explicit
        self.client.cookies.clear()

        # Create profile if missing
        self._request(
            "POST",
            "/players",
            player=player,
            json={"username": player.username, "region": player.region},
            name="players_create",
        )

    def _refresh_token(self, player: PlayerCtx) -> None:
        if not player.refresh_cookies:
            return
        headers = {}
        csrf = player.refresh_cookies.get("csrf_refresh_token")
        if csrf:
            headers["X-CSRF-TOKEN"] = csrf
        resp = self._request(
            "POST",
            "/refresh",
            headers=headers,
            cookies=player.refresh_cookies,
            name="auth_refresh",
        )
        if resp and resp.ok:
            payload = self._safe_json(resp)
            player.jwt = payload.get("access_token", player.jwt)

    def _store_player(self, player: PlayerCtx) -> None:
        with players_lock:
            players_registry.append(player)

    def _pick_peer(self, exclude: PlayerCtx) -> Optional[PlayerCtx]:
        with players_lock:
            candidates = [p for p in players_registry if p.user_id and p is not exclude]
        if not candidates:
            return None
        return random.choice(candidates)

    def _safe_json(self, resp) -> Dict:
        try:
            return resp.json() if resp and resp.content else {}
        except ValueError:
            return {}

    # ---- Tasks ----

    @task(1)
    def health_checks(self) -> None:
        """Basic liveness probes."""
        self._request("GET", "/catalogue/health", name="catalogue_health")
        self._request("GET", "/players/health", name="players_health")
        self._request("GET", "/game_engine/health", name="game_engine_health")

    @task(2)
    def profiles_and_friendships(self) -> None:
        """Profile CRUD + friendship flow with a peer (player2 by default)."""
        p1, p2 = self.player1, self.player2
        self._request("GET", "/players/me", player=p1, name="players_me_get")
        self._request(
            "PATCH",
            "/players/me",
            player=p1,
            json={"region": random.choice(REGIONS)},
            name="players_me_patch",
        )
        if p1.user_id:
            self._request(
                "GET",
                f"/players/{p1.user_id}",
                player=p1,
                name="players_by_id",
            )
        self._request(
            "GET",
            f"/players/search/{p1.username}",
            player=p1,
            name="players_search_self",
        )
        self._request(
            "GET",
            f"/players/search/{p2.username}",
            player=p1,
            name="players_search_peer",
        )

        # Friendship lifecycle
        self._request(
            "POST",
            f"/players/me/friends/{p2.username}",
            player=p1,
            name="friends_send_request",
            expected=(200, 201, 409),
        )
        self._request(
            "GET",
            f"/players/me/friends/{p2.username}",
            player=p1,
            name="friends_status_pending",
            expected=(200, 404),
        )
        self._request(
            "POST",
            f"/players/me/friends/{p1.username}",
            player=p2,
            json={"accepted": True},
            name="friends_accept",
            expected=(200, 201, 409),
        )
        self._request(
            "GET",
            "/players/me/friends",
            player=p1,
            name="friends_list",
            expected=(200, 404),
        )
        self._request(
            "GET",
            f"/players/me/friends/{p2.username}",
            player=p1,
            name="friends_status_accepted",
            expected=(200, 404),
        )

    @task(3)
    def catalogue_validation_flow(self) -> None:
        """Stress catalogue listing, single fetch, and deck validation."""
        p = self.player1
        resp = self._request("GET", "/cards", player=p, name="catalogue_cards_all")
        cards = self._safe_json(resp).get("data", [])
        if cards:
            card_id = cards[0].get("id")
        else:
            card_id = DECK1[0]

        self._request(
            "GET",
            f"/cards/{card_id}",
            player=p,
            name="catalogue_card_single",
        )
        self._request(
            "GET",
            f"/cards/{MISSING_CARD_ID}",
            player=p,
            name="catalogue_card_missing",
            expected=(200, 404),
        )

    @task(4)
    def matchmaking_and_gameplay(self) -> None:
        """
        Exercises the full game loop:
        enqueue → status → dequeue (success and TooLate) → deck submission → five moves →
        round status → match and history queries → leaderboard and player history.
        """
        p1, p2 = self.player1, self.player2

        # First run: demonstrate dequeue before a match
        if not self.did_dequeue_once:
            token, _, _ = self._enqueue(p1, name_suffix="first_pass")
            if token:
                self._status_poll(p1, token, max_attempts=2)
                self._dequeue(p1, token, name_suffix="first_pass")
            self.did_dequeue_once = True

        # Enqueue both players for an actual match
        token1, match_id, opp1 = self._enqueue(p1)
        token2, immediate, opp2 = self._enqueue(p2)
        match_id = match_id or immediate

        if not match_id:
            match_id, opp1 = self._status_poll(p1, token1)
        if not match_id:
            match_id, opp2 = self._status_poll(p2, token2)

        # Proceed only if both of our players are matched together
        if not match_id or not p1.user_id or not p2.user_id:
            # Clean up if no match could be found
            if token1:
                self._dequeue(p1, token1, name_suffix="cleanup")
            if token2:
                self._dequeue(p2, token2, name_suffix="cleanup")
            return
        if not ((opp1 == p2.user_id) or (opp2 == p1.user_id)):
            return

        p1.last_match_id = p2.last_match_id = match_id

        # Dequeue attempt after match (TooLate scenario)
        if token1:
            self._dequeue(p1, token1, name_suffix="too_late")

        # Deck submissions
        self._submit_deck(match_id, p1, DECK1)
        self._submit_deck(match_id, p2, DECK2)

        # Current round status before moves
        self._request(
            "GET",
            f"/matches/{match_id}/round",
            player=p1,
            name="game_engine_round_status_start",
        )

        # Five rounds of moves (mirrors integration deck order)
        for idx, (c1, c2) in enumerate(zip(DECK1, DECK2), start=1):
            self._submit_move(match_id, p1, idx, c1)
            self._submit_move(match_id, p2, idx, c2)
            gevent.sleep(0.1)
            self._request(
                "GET",
                f"/matches/{match_id}/history",
                player=p1,
                name=f"game_engine_history_after_round_{idx}",
            )

        # Final match status and history
        self._request(
            "GET",
            f"/matches/{match_id}",
            player=p1,
            name="game_engine_match_final",
        )
        self._request(
            "GET",
            f"/matches/{match_id}/history",
            player=p1,
            name="game_engine_history_final",
        )
        self._request(
            "GET",
            f"/matches/history/{p1.user_id}?status=finished&limit=5",
            player=p1,
            name="game_engine_player_history_finished",
        )
        self._request(
            "GET",
            "/leaderboard?limit=10",
            player=p1,
            name="game_engine_leaderboard",
        )

        # Refresh token to keep sessions alive
        self._refresh_token(p1)

    # ---- Matchmaking / engine helpers ----

    def _enqueue(
        self, player: PlayerCtx, name_suffix: str = "enqueue"
    ) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        resp = self._request(
            "POST",
            "/enqueue",
            player=player,
            name=f"matchmaking_{name_suffix}",
        )
        payload = self._safe_json(resp)
        token = payload.get("queue_token")
        player.last_queue_token = token or player.last_queue_token
        match_id = payload.get("match_id")
        opponent = payload.get("opponent_id")
        return token, match_id, opponent

    def _status_poll(
        self, player: PlayerCtx, token: Optional[str], max_attempts: Optional[int] = None
    ) -> Tuple[Optional[int], Optional[int]]:
        attempts = max_attempts or MATCH_POLL_RETRIES
        for _ in range(attempts):
            resp = self._request(
                "GET",
                "/status",
                player=player,
                params={"token": token},
                name="matchmaking_status",
                expected=(200, 404),
            )
            payload = self._safe_json(resp)
            if payload.get("status") == "Matched":
                return payload.get("match_id"), payload.get("opponent_id")
            gevent.sleep(MATCH_POLL_INTERVAL)
        return None, None

    def _dequeue(self, player: PlayerCtx, token: str, name_suffix: str = "dequeue") -> None:
        self._request(
            "POST",
            "/dequeue",
            player=player,
            json={"token": token},
            name=f"matchmaking_{name_suffix}",
            expected=(200, 409),
        )

    def _submit_deck(self, match_id: int, player: PlayerCtx, cards: List[int]) -> None:
        self._request(
            "POST",
            f"/matches/{match_id}/deck",
            player=player,
            json={"data": cards},
            name=f"game_engine_deck_{player.username}",
        )

    def _submit_move(self, match_id: int, player: PlayerCtx, round_number: int, card_id: int) -> None:
        self._request(
            "POST",
            f"/matches/{match_id}/moves/{round_number}",
            player=player,
            json={"card_id": card_id},
            name=f"game_engine_move_r{round_number}_{player.username}",
        )
