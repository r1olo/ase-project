"""
Locust performance suite for the full card-game platform.

This file drives realistic end-to-end flows across:
- Auth (/register, /login, /refresh)
- Players (profile CRUD and friendships)
- Catalogue (card listing + single card fetch)
- Matchmaking (enqueue/status/dequeue)
- Game Engine (match creation via matchmaking, deck submission, move rounds, history, leaderboard)

Environment knobs (override via `LOCUST_ENV_VAR=value`):
- GATEWAY_URL: base URL for the API Gateway (default: https://localhost:443)
- AUTH_BASE_URL / PLAYERS_BASE_URL / CATALOGUE_BASE_URL / MATCHMAKING_BASE_URL / GAME_ENGINE_BASE_URL:
  optional service-specific overrides (useful to hit services directly without the gateway).
- GAME_ENGINE_INTERNAL_URL: optional override for endpoints blocked by the gateway such as /internal/matches/create.
- LOCUST_VERIFY_TLS: "true"/"false" to enable TLS verification (default: false, useful with self-signed certs).
- LOCUST_REQUEST_TIMEOUT: per-request timeout in seconds (default: 5).
- LOCUST_MATCH_POLL_RETRIES: status polls after enqueue before giving up (default: 8).
- LOCUST_MATCH_POLL_INTERVAL: seconds between matchmaking status polls (default: 1.0).
"""
from __future__ import annotations

import os
import random
import string
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import gevent
from locust import HttpUser, between, task

# ---- Configuration helpers ----


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


DEFAULT_GATEWAY = os.getenv("GATEWAY_URL", "https://localhost:443")

SERVICE_BASE = {
    "auth": os.getenv("AUTH_BASE_URL", DEFAULT_GATEWAY),
    "players": os.getenv("PLAYERS_BASE_URL", DEFAULT_GATEWAY),
    "catalogue": os.getenv("CATALOGUE_BASE_URL", DEFAULT_GATEWAY),
    "matchmaking": os.getenv("MATCHMAKING_BASE_URL", DEFAULT_GATEWAY),
    "game_engine": os.getenv("GAME_ENGINE_BASE_URL", DEFAULT_GATEWAY),
    # Gateway blocks /internal/matches/create, so allow an internal override for direct calls if needed.
    "game_engine_internal": os.getenv(
        "GAME_ENGINE_INTERNAL_URL", os.getenv("GAME_ENGINE_BASE_URL", DEFAULT_GATEWAY)
    ),
}

VERIFY_TLS = _bool_env("LOCUST_VERIFY_TLS", False)
REQUEST_TIMEOUT = float(os.getenv("LOCUST_REQUEST_TIMEOUT", "5"))
MATCH_POLL_RETRIES = int(os.getenv("LOCUST_MATCH_POLL_RETRIES", "8"))
MATCH_POLL_INTERVAL = float(os.getenv("LOCUST_MATCH_POLL_INTERVAL", "1.0"))


# ---- Data classes ----


@dataclass
class PlayerContext:
    email: str
    password: str
    username: str
    user_id: Optional[int] = None
    access_token: Optional[str] = None
    refresh_cookie: Dict[str, str] = field(default_factory=dict)
    deck: List[int] = field(default_factory=list)


# ---- Utility functions ----


def _rand_email() -> str:
    return f"locust-{uuid.uuid4().hex[:10]}@example.com"


def _rand_password() -> str:
    return uuid.uuid4().hex


def _rand_username(prefix: str) -> str:
    letters = "".join(random.choices(string.ascii_lowercase, k=5))
    return f"{prefix}-{letters}"


def _service_url(service: str, path: str) -> str:
    base = SERVICE_BASE.get(service, DEFAULT_GATEWAY).rstrip("/")
    return f"{base}{path}"


# ---- Locust user ----


class GameSystemUser(HttpUser):
    """
    A virtual user that exercises end-to-end flows across all microservices.

    Each Locust user owns two player identities so matches, friendships, and deck
    submissions can be run without relying on other virtual users.
    """

    host = DEFAULT_GATEWAY
    wait_time = between(1, 3)

    def on_start(self):
        self.cards: List[int] = []
        self.player_a = PlayerContext(
            email=_rand_email(),
            password=_rand_password(),
            username=_rand_username("alpha"),
        )
        self.player_b = PlayerContext(
            email=_rand_email(),
            password=_rand_password(),
            username=_rand_username("beta"),
        )

        # Bootstrap both identities and cache the catalogue list once.
        for player in (self.player_a, self.player_b):
            self._register_and_login(player)
            self._ensure_profile(player)

        self.cards = self._load_catalogue_cards(self.player_a)
        if not self.cards:
            # Default to a safe fallback range; service seeds 20 cards.
            self.cards = list(range(1, 21))

    # ---- Task helpers ----

    def _register_and_login(self, player: PlayerContext) -> None:
        # Registration is idempotent; conflict just means user exists.
        self.client.post(
            _service_url("auth", "/register"),
            json={"email": player.email, "password": player.password},
            name="auth_register",
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )

        resp = self.client.post(
            _service_url("auth", "/login"),
            json={"email": player.email, "password": player.password},
            name="auth_login",
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        if not resp or not resp.ok:
            return

        data = resp.json() if resp.content else {}
        player.access_token = data.get("access_token")
        player.user_id = data.get("user_id")
        # Capture refresh cookies for later /refresh or /logout calls.
        player.refresh_cookie = self.client.cookies.get_dict()
        # Clear cookies so subsequent logins do not reuse them implicitly.
        self.client.cookies.clear()

    def _auth_headers(self, player: PlayerContext) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if player.access_token:
            headers["Authorization"] = f"Bearer {player.access_token}"
        return headers

    def _ensure_profile(self, player: PlayerContext) -> None:
        headers = self._auth_headers(player)
        resp = self.client.get(
            _service_url("players", "/players/me"),
            name="players_me_get",
            headers=headers,
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 404:
            payload = {"username": player.username}
            self.client.post(
                _service_url("players", "/players"),
                json=payload,
                headers=headers,
                name="players_create",
                verify=VERIFY_TLS,
                timeout=REQUEST_TIMEOUT,
            )

    def _load_catalogue_cards(self, player: PlayerContext) -> List[int]:
        headers = self._auth_headers(player)
        resp = self.client.get(
            _service_url("catalogue", "/cards"),
            name="catalogue_cards",
            headers=headers,
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        if not resp or not resp.ok:
            return []
        try:
            payload = resp.json()
        except ValueError:
            return []
        cards = payload.get("data") or []
        return [card["id"] for card in cards if isinstance(card, dict) and "id" in card]

    def _refresh_access_token(self, player: PlayerContext) -> None:
        if not player.refresh_cookie:
            return
        headers = self._auth_headers(player)
        csrf = player.refresh_cookie.get("csrf_refresh_token")
        if csrf:
            headers["X-CSRF-TOKEN"] = csrf
        resp = self.client.post(
            _service_url("auth", "/refresh"),
            name="auth_refresh",
            headers=headers,
            cookies=player.refresh_cookie,
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        if resp and resp.ok:
            try:
                player.access_token = resp.json().get("access_token", player.access_token)
            except ValueError:
                pass

    def _sample_deck(self) -> List[int]:
        deck_size = 5  # Game engine constant
        if len(self.cards) < deck_size:
            return list(range(1, deck_size + 1))
        return random.sample(self.cards, deck_size)

    def _enqueue_player(self, player: PlayerContext) -> Tuple[Optional[str], Optional[str]]:
        headers = self._auth_headers(player)
        resp = self.client.post(
            _service_url("matchmaking", "/enqueue"),
            name="matchmaking_enqueue",
            headers=headers,
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        if not resp:
            return None, None
        try:
            payload = resp.json()
        except ValueError:
            return None, None

        # Immediate match (rare) returns match id
        if "match_id" in payload:
            return payload.get("queue_token"), str(payload.get("match_id"))
        return payload.get("queue_token"), None

    def _poll_match_status(self, player: PlayerContext, token: Optional[str]) -> Optional[str]:
        headers = self._auth_headers(player)
        params = {"token": token} if token else None
        for _ in range(MATCH_POLL_RETRIES):
            resp = self.client.get(
                _service_url("matchmaking", "/status"),
                name="matchmaking_status",
                headers=headers,
                params=params,
                verify=VERIFY_TLS,
                timeout=REQUEST_TIMEOUT,
            )
            if resp and resp.status_code == 200:
                try:
                    payload = resp.json()
                except ValueError:
                    payload = {}
                if payload.get("status") == "Matched":
                    return str(payload.get("match_id"))
            gevent.sleep(MATCH_POLL_INTERVAL)
        return None

    def _submit_deck(self, player: PlayerContext, match_id: str) -> List[int]:
        deck = self._sample_deck()
        headers = self._auth_headers(player)
        self.client.post(
            _service_url("game_engine", f"/matches/{match_id}/deck"),
            name="game_engine_deck",
            json={"data": deck},
            headers=headers,
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        return deck

    def _play_round(self, match_id: str, round_number: int, decks: Dict[int, List[int]]) -> None:
        # Each deck is keyed by user_id; pop one card per player and submit.
        for player in (self.player_a, self.player_b):
            if not decks.get(player.user_id):
                continue
            card_id = decks[player.user_id].pop()
            headers = self._auth_headers(player)
            self.client.post(
                _service_url("game_engine", f"/matches/{match_id}/moves/{round_number}"),
                name="game_engine_move",
                json={"card_id": card_id},
                headers=headers,
                verify=VERIFY_TLS,
                timeout=REQUEST_TIMEOUT,
            )

    def _current_round(self, match_id: str) -> Optional[int]:
        resp = self.client.get(
            _service_url("game_engine", f"/matches/{match_id}/round"),
            name="game_engine_round_status",
            headers=self._auth_headers(self.player_a),
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        if not resp or resp.status_code != 200:
            return None
        try:
            payload = resp.json()
        except ValueError:
            return None
        return payload.get("current_round_number") or 1

    # ---- Tasks ----

    @task(1)
    def health_checks(self):
        """Probe all public health endpoints."""
        self.client.get(
            _service_url("catalogue", "/health"),
            name="catalogue_health",
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        self.client.get(
            _service_url("players", "/health"),
            name="players_health",
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        self.client.get(
            _service_url("game_engine", "/health"),
            name="game_engine_health",
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )

    @task(3)
    def browse_cards_and_profiles(self):
        """Exercise catalogue + profile endpoints."""
        headers_a = self._auth_headers(self.player_a)
        headers_b = self._auth_headers(self.player_b)

        # Fetch catalogue list and a random single card
        cards_resp = self.client.get(
            _service_url("catalogue", "/cards"),
            name="catalogue_cards",
            headers=headers_a,
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        if cards_resp and cards_resp.ok:
            try:
                data = cards_resp.json().get("data") or []
            except ValueError:
                data = []
            if data:
                card_id = random.choice(data).get("id")
                if card_id is not None:
                    self.client.get(
                        _service_url("catalogue", f"/cards/{card_id}"),
                        name="catalogue_card",
                        headers=headers_a,
                        verify=VERIFY_TLS,
                        timeout=REQUEST_TIMEOUT,
                    )

        # Profile lookup/update
        self.client.get(
            _service_url("players", "/players/me"),
            name="players_me_get",
            headers=headers_a,
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        self.client.patch(
            _service_url("players", "/players/me"),
            name="players_me_patch",
            json={"region": random.choice(["north", "center", "south", "islands"])},
            headers=headers_a,
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )

        # Friend search + request/accept flow (idempotent enough for repeated runs)
        self.client.post(
            _service_url("players", "/players/search"),
            name="players_search",
            json={"username": self.player_b.username},
            headers=headers_a,
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        self.client.post(
            _service_url("players", f"/players/me/friends/{self.player_b.username}"),
            name="players_friend_request",
            headers=headers_a,
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        self.client.post(
            _service_url("players", f"/players/me/friends/{self.player_a.username}"),
            name="players_friend_accept",
            json={"accepted": True},
            headers=headers_b,
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        self.client.get(
            _service_url("players", "/players/me/friends"),
            name="players_friends_list",
            headers=headers_a,
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )

    @task(2)
    def refresh_and_leaderboard(self):
        """Refresh access token, fetch leaderboard and personal history."""
        self._refresh_access_token(self.player_a)

        headers_a = self._auth_headers(self.player_a)
        self.client.get(
            _service_url("game_engine", "/leaderboard"),
            name="game_engine_leaderboard",
            headers=headers_a,
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        if self.player_a.user_id:
            self.client.get(
                _service_url("game_engine", f"/matches/history/{self.player_a.user_id}"),
                name="game_engine_player_history",
                headers=headers_a,
                verify=VERIFY_TLS,
                timeout=REQUEST_TIMEOUT,
            )

    @task(4)
    def matchmaking_and_play(self):
        """Full flow: enqueue both players, submit decks, play a round, fetch history."""
        queue_token_a, match_id = self._enqueue_player(self.player_a)
        queue_token_b, immediate_match = self._enqueue_player(self.player_b)
        if not match_id:
            match_id = immediate_match

        # Poll matchmaking status until both players see a match
        if not match_id:
            match_id = self._poll_match_status(self.player_a, queue_token_a)
        if not match_id:
            match_id = self._poll_match_status(self.player_b, queue_token_b)

        if not match_id:
            # Clean up queue if nothing happened
            for player in (self.player_a, self.player_b):
                self.client.post(
                    _service_url("matchmaking", "/dequeue"),
                    name="matchmaking_dequeue",
                    headers=self._auth_headers(player),
                    verify=VERIFY_TLS,
                    timeout=REQUEST_TIMEOUT,
                )
            return

        # Submit decks for both players
        decks = {}
        for player in (self.player_a, self.player_b):
            deck = self._submit_deck(player, match_id)
            decks[player.user_id] = deck[::-1]  # reverse for pop()

        # Play a single round to exercise move submission
        round_number = self._current_round(match_id) or 1
        self._play_round(match_id, round_number, decks)

        # Fetch match snapshots
        self.client.get(
            _service_url("game_engine", f"/matches/{match_id}"),
            name="game_engine_match",
            headers=self._auth_headers(self.player_a),
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )
        self.client.get(
            _service_url("game_engine", f"/matches/{match_id}/history"),
            name="game_engine_match_history",
            headers=self._auth_headers(self.player_a),
            verify=VERIFY_TLS,
            timeout=REQUEST_TIMEOUT,
        )

        # Clean queue state for future runs
        for player in (self.player_a, self.player_b):
            self.client.post(
                _service_url("matchmaking", "/dequeue"),
                name="matchmaking_dequeue",
                headers=self._auth_headers(player),
                verify=VERIFY_TLS,
                timeout=REQUEST_TIMEOUT,
            )
