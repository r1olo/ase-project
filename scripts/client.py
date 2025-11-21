#!/usr/bin/env python3
"""
CLI helper for playing the card game against the running services.

The script walks through:
- Registering and logging in to obtain a JWT
- Enqueuing for matchmaking and polling /status until a match is found
- Browsing the catalogue and submitting a deck
- Polling the current round and submitting moves
"""
import argparse
import getpass
import os
import requests
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

DEFAULT_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:80")
DEFAULT_REQUEST_TIMEOUT = 10.0
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_POLL_TIMEOUT = 180.0
CLIENT_DECK_SIZE = 5
GAME_MAX_ROUNDS = 5

@dataclass
class ClientState:
    base_url: str
    game_engine_url: Optional[str] = None
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    poll_interval: float = DEFAULT_POLL_INTERVAL
    poll_timeout: float = DEFAULT_POLL_TIMEOUT
    token: Optional[str] = None
    user_id: Optional[int] = None
    queue_token: Optional[str] = None
    match_id: Optional[int] = None
    match_info: Optional[Dict] = None
    deck: List[str] = field(default_factory=list)
    played_cards: Set[str] = field(default_factory=set)
    cards_cache: Dict[str, Dict] = field(default_factory=dict)

    def auth_headers(self) -> Dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def is_player_one(self) -> Optional[bool]:
        if not self.match_info or self.user_id is None:
            return None
        if self.match_info.get("player1_id") == self.user_id:
            return True
        if self.match_info.get("player2_id") == self.user_id:
            return False
        return None

def _full_url(state: ClientState, path: str, base_url: Optional[str] = None) -> str:
    base = base_url or state.base_url
    cleaned = path if path.startswith("/") else f"/{path}"
    return f"{base.rstrip('/')}{cleaned}"

def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value

def _api_request(
    state: ClientState,
    method: str,
    path: str,
    *,
    use_auth: bool = True,
    base_url: Optional[str] = None,
    **kwargs,
) -> Tuple[Optional[requests.Response], Optional[Dict]]:
    headers = kwargs.pop("headers", {})
    if use_auth:
        headers.update(state.auth_headers())
    try:
        resp = requests.request(
            method,
            _full_url(state, path, base_url),
            headers=headers,
            timeout=state.request_timeout,
            **kwargs,
        )
    except requests.RequestException as exc:
        print(f"[error] request failed: {exc}")
        return None, None

    try:
        payload = resp.json()
    except ValueError:
        payload = None
    return resp, payload

def _print_error(resp: Optional[requests.Response], payload: Optional[Dict]) -> None:
    status = resp.status_code if resp else "?"
    msg = ""
    if payload and isinstance(payload, dict):
        msg = payload.get("msg") or payload.get("error") or str(payload)
    elif resp is not None:
        msg = resp.text
    print(f"[error] ({status}) {msg}")

def _require_login(state: ClientState) -> bool:
    if state.token:
        return True
    print("You need to login first.")
    return False

def cmd_register(state: ClientState) -> None:
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")
    resp, payload = _api_request(
        state,
        "post",
        "/register",
        use_auth=False,
        json={"email": email, "password": password},
    )
    if resp is None:
        return
    if 200 <= resp.status_code < 300:
        print("✅ Registered successfully.")
    else:
        _print_error(resp, payload)

def cmd_login(state: ClientState) -> None:
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")
    resp, payload = _api_request(
        state, "post", "/login", use_auth=False, json={"email": email, "password": password}
    )
    if resp is None:
        return
    if resp.status_code == 200 and payload:
        state.token = payload.get("access_token")
        user_id_raw = payload.get("user_id")
        try:
            state.user_id = int(user_id_raw)
        except (TypeError, ValueError):
            state.user_id = None
        print(f"🔑 Logged in as user {state.user_id}.")
    else:
        _print_error(resp, payload)

def cmd_enqueue(state: ClientState) -> None:
    if not _require_login(state):
        return
    resp, payload = _api_request(state, "post", "/enqueue")
    if resp is None:
        return
    if payload and payload.get("queue_token"):
        state.queue_token = payload["queue_token"]
    if payload:
        match_id = payload.get("id") or payload.get("match_id")
        if match_id is not None:
            state.match_id = _as_int(match_id)
            state.match_info = payload
            print(f"🎲 Matched immediately! Match #{state.match_id}.")
            fetch_match_info(state)
            return
    print("⏳ Joined queue, waiting for an opponent...")
    poll_matchmaking(state, blocking=True)

def poll_matchmaking(state: ClientState, blocking: bool = False) -> None:
    if not _require_login(state):
        return
    print("🔍 Looking for an opponent...", end="", flush=True)
    start = time.time()
    last_status = None
    waiting_msgs = ["", ".", "..", "..."]
    dots = 0
    while True:
        params = {"token": state.queue_token} if state.queue_token else None
        resp, payload = _api_request(state, "get", "/status", params=params)
        if resp is None:
            return
        if resp.status_code == 404:
            print("\n⚠️  You are no longer in the queue.")
            return
        if payload:
            status = payload.get("status")
            if status != last_status and status:
                print(f"\nQueue status: {status}")
                last_status = status
            if status == "Matched":
                state.match_id = _as_int(payload.get("match_id"))
                if payload.get("queue_token"):
                    state.queue_token = payload["queue_token"]
                print(f"\n🎯 Match found! Match #{state.match_id} vs {payload.get('opponent_id')}")
                info = fetch_match_info(state)
                if info:
                    print(_format_match_summary(info, state.user_id))
                return
        if not blocking and time.time() - start >= state.poll_timeout:
            print("\n⏱️  Stopped polling; try again soon.")
            return
        dots = (dots + 1) % len(waiting_msgs)
        print(f"\r🔍 Looking for an opponent{waiting_msgs[dots]}", end="", flush=True)
        time.sleep(state.poll_interval)

def fetch_cards(state: ClientState) -> List[Dict]:
    if not _require_login(state):
        return []
    resp, payload = _api_request(state, "get", "/cards")
    if resp is None:
        return []
    if not (200 <= resp.status_code < 300):
        _print_error(resp, payload)
        return []
    cards = payload.get("data") if payload else []
    state.cards_cache = {str(card["id"]): card for card in cards}
    for card in cards:
        print(
            f"{card['id']:>2} | {card['name']:<20} "
            f"E:{card['economy']} Env:{card['environment']} Food:{card['food']} "
            f"Spec:{card['special']} Tot:{card['total']}"
        )
    return cards

def _prompt_deck(card_ids: Set[str]) -> List[str]:
    while True:
        raw = input(f"Enter {CLIENT_DECK_SIZE} card IDs separated by space (or blank to cancel): ").strip()
        if not raw:
            return []
        tokens = [part for part in raw.replace(",", " ").split() if part]
        if len(tokens) != CLIENT_DECK_SIZE:
            print(f"Deck must contain exactly {CLIENT_DECK_SIZE} unique cards.")
            continue
        if len(set(tokens)) != CLIENT_DECK_SIZE:
            print("Cards must be unique.")
            continue
        missing = [c for c in tokens if c not in card_ids]
        if missing:
            print(f"Unknown card IDs: {', '.join(missing)}")
            continue
        return tokens

def cmd_submit_deck(state: ClientState) -> None:
    if not _require_login(state):
        return
    if not state.match_id:
        print("Join a match first (enqueue + poll).")
        return
    cards = fetch_cards(state)
    if not cards:
        return
    selection = _prompt_deck(set(str(card["id"]) for card in cards))
    if not selection:
        print("Deck selection cancelled.")
        return
    payload_deck = [_as_int(card_id) for card_id in selection]
    resp, payload = _api_request(
        state, "post", f"/matches/{state.match_id}/deck", json={"data": payload_deck}
    )
    if resp is None:
        return
    if 200 <= resp.status_code < 300:
        state.deck = selection
        state.played_cards.clear()
        fetch_match_info(state)
        print(f"🃏 Deck submitted with {len(selection)} cards.")
    else:
        _print_error(resp, payload)

def fetch_match_info(state: ClientState) -> Optional[Dict]:
    if not _require_login(state) or not state.match_id:
        return None
    resp, payload = _api_request(state, "get", f"/matches/{state.match_id}")
    if resp is None:
        return None
    if 200 <= resp.status_code < 300 and payload:
        state.match_info = payload
        return payload
    _print_error(resp, payload)
    return None

def show_match(state: ClientState) -> None:
    info = fetch_match_info(state)
    if info:
        print(_format_match_summary(info, state.user_id))

def _can_play(round_payload: Dict, state: ClientState) -> bool:
    round_obj = round_payload.get("round") or {}
    seat = state.is_player_one()
    if seat is None:
        return True
    if seat:
        return round_obj.get("player1_card_id") is None
    return round_obj.get("player2_card_id") is None

def wait_for_round_slot(state: ClientState) -> Optional[Dict]:
    """Poll /matches/<id>/round until the player can submit a move or the match ends."""
    if not _require_login(state) or not state.match_id:
        return None
    start = time.time()
    last_status = None
    last_round = None
    while time.time() - start < state.poll_timeout:
        resp, payload = _api_request(state, "get", f"/matches/{state.match_id}/round")
        if resp is None:
            return None
        if resp.status_code == 404:
            print("Round not found.")
            return None
        match = fetch_match_info(state)
        if match and match.get("status") == "FINISHED":
            print("Match already finished.")
            return None
        if payload:
            round_num = payload.get("current_round_number") or (payload.get("round") or {}).get("round_number")
            if round_num is not None and round_num != last_round:
                last_round = round_num
            status = payload.get("round_status")
            if status != last_status:
                print(f"Round status: {status}")
                last_status = status
            if status in {"WAITING_FOR_BOTH_PLAYERS", "WAITING_FOR_ONE_PLAYER"} and _can_play(
                payload, state
            ):
                return payload
            if round_num is not None and round_num >= GAME_MAX_ROUNDS and match and match.get("status") == "FINISHED":
                print(_format_match_summary(match, state.user_id))
                return None
        time.sleep(state.poll_interval)
    print("Timed out waiting for a playable round.")
    return None

def _poll_round_resolution(state: ClientState, start_round: Optional[int]) -> None:
    """After submitting a move, keep polling until the round advances or match ends."""
    start = time.time()
    last_status = None
    while time.time() - start < state.poll_timeout:
        resp, payload = _api_request(state, "get", f"/matches/{state.match_id}/round")
        if resp is None:
            return
        match = fetch_match_info(state)
        if match and match.get("status") == "FINISHED":
            print(_format_match_summary(match, state.user_id))
            return
        if payload:
            round_num = payload.get("current_round_number") or (payload.get("round") or {}).get("round_number")
            if round_num is not None and round_num != start_round:
                print(f"➡️  Moving to round {round_num}.")
                return
            if round_num is not None and round_num >= GAME_MAX_ROUNDS:
                if match:
                    print(_format_match_summary(match, state.user_id))
                else:
                    print(f"Match should be finished at round {round_num}.")
                return
            status = payload.get("round_status")
            if status != last_status and status:
                print(f"Round status: {status}")
                last_status = status
            if status == "ROUND_COMPLETE":
                print("✅ Round resolved. Check scores above.")
                return
        time.sleep(state.poll_interval)
    print("⏱️  Stopped waiting for round resolution.")

def _prompt_move(deck: List[str], played: Set[str], category: Optional[str], cards: Dict[str, Dict]) -> Optional[str]:
    available = [c for c in deck if c not in played] if deck else None
    if available is not None and not available:
        print("No cards left to play.")
        return None
    if category:
        print(f"Category this round: {category}")
    if available is not None:
        print("Available cards:")
        for cid in available:
            card_info = cards.get(cid) or cards.get(str(cid))
            if card_info:
                print(
                    f"- {cid}: {card_info.get('name', '')} "
                    f"(E:{card_info.get('economy')} Env:{card_info.get('environment')} "
                    f"Food:{card_info.get('food')} Spec:{card_info.get('special')} "
                    f"Tot:{card_info.get('total')})"
                )
            else:
                print(f"- {cid}")
    else:
        print("Deck unknown locally; type the card ID you want to play.")
    while True:
        choice = input("Card to play (blank to cancel): ").strip()
        if not choice:
            return None
        if available is not None and choice not in available:
            print("Choose a card from your remaining deck.")
            continue
        card_info = cards.get(choice)
        if card_info and category and category in card_info:
            print(f"{card_info['name']} has {category}={card_info[category]}")
        return choice

def cmd_play_move(state: ClientState) -> None:
    if not _require_login(state):
        return
    if not state.match_id:
        print("No active match. Enqueue and poll first.")
        return
    match_info = fetch_match_info(state)
    if match_info and match_info.get("status") == "SETUP":
        print("⚠️  Match is still in SETUP. Submit your deck before playing.")
        return
    if not state.cards_cache:
        fetch_cards(state)
    round_payload = wait_for_round_slot(state)
    if not round_payload:
        return
    category = round_payload.get("current_category")
    card_id = _prompt_move(state.deck, state.played_cards, category, state.cards_cache)
    if not card_id:
        print("Move cancelled.")
        return
    round_number = _as_int(
        round_payload.get("current_round_number")
        or (round_payload.get("round") or {}).get("round_number")
    )
    if round_number is None:
        print("Could not determine round number; try polling again.")
        return
    card_id_int = _as_int(card_id)
    resp, payload = _api_request(
        state,
        "post",
        f"/matches/{state.match_id}/moves/{round_number}",
        json={"card_id": card_id_int},
    )
    if resp is None:
        return
    if resp.status_code == 200:
        state.played_cards.add(card_id)
        match_info = fetch_match_info(state)
        print(_describe_move_result(payload or {}, match_info, state.user_id))
        if payload and payload.get("status") == "WAITING_FOR_OPPONENT":
            _poll_round_resolution(state, round_number)
        if payload and payload.get("game_status") == "FINISHED":
            if match_info:
                print(_format_match_summary(match_info, state.user_id))
    else:
        _print_error(resp, payload)

def cmd_poll_round(state: ClientState) -> None:
    round_payload = wait_for_round_slot(state)
    if round_payload:
        category = round_payload.get("current_category")
        round_num = round_payload.get("current_round_number")
        print(f"Round {round_num} | Category: {category}")
        round_info = round_payload.get("round") or {}
        if round_info.get("player1_card_id") or round_info.get("player2_card_id"):
            print("Opponent may have played already; you can submit your move.")

def _extract_played_cards(match: Dict, user_id: Optional[int]) -> Set[str]:
    if user_id is None:
        return set()
    cards = set()
    rounds = match.get("rounds") or []
    is_p1 = match.get("player1_id") == user_id
    for rnd in rounds:
        card_id = rnd.get("player1_card_id") if is_p1 else rnd.get("player2_card_id")
        if card_id is not None:
            cards.add(str(card_id))
    return cards

def _format_match_summary(match: Dict, user_id: Optional[int]) -> str:
    if not match:
        return "No match info."
    p1 = match.get("player1_id")
    p2 = match.get("player2_id")
    me = user_id
    status = match.get("status")
    p1_score = match.get("player1_score")
    p2_score = match.get("player2_score")
    if me is not None:
        if p1 == me:
            scores = f"You {p1_score} - {p2_score} Opponent({p2})"
        elif p2 == me:
            scores = f"You {p2_score} - {p1_score} Opponent({p1})"
        else:
            scores = f"P1 {p1_score} - {p2_score} P2"
    else:
        scores = f"P1 {p1_score} - {p2_score} P2"
    winner = match.get("winner_id")
    if status == "FINISHED":
        if winner is None:
            verdict = "It was a tie."
        elif winner == me:
            verdict = "You won! 🎉"
        else:
            verdict = f"Opponent {winner} won."
    else:
        verdict = f"Status: {status}"
    return f"Match #{match.get('id')}: {scores}. {verdict}"

def _describe_move_result(payload: Dict, match: Optional[Dict], user_id: Optional[int]) -> str:
    status = payload.get("status")
    if status == "WAITING_FOR_OPPONENT":
        return "Move submitted. Waiting for the opponent..."
    if status == "ROUND_PROCESSED":
        winner = payload.get("round_winner_id")
        is_draw = payload.get("is_draw")
        if is_draw:
            result = "Round ended in a tie."
        elif user_id is not None and winner == user_id:
            result = "You won this round! ✅"
        elif winner is None:
            result = "Round complete."
        else:
            result = f"Opponent {winner} won the round."
        scores = payload.get("scores") or {}
        score_line = ""
        if match and scores:
            p1 = match.get("player1_id")
            p2 = match.get("player2_id")
            score_line = f" | {p1}:{scores.get(p1)} {p2}:{scores.get(p2)}"
        game_status = payload.get("game_status")
        if game_status == "FINISHED":
            result += " Match finished."
        return result + score_line
    return "Move submitted."

def list_active_matches(state: ClientState) -> List[Dict]:
    if not _require_login(state):
        return []
    if state.user_id is None:
        print("User id not set; please login again.")
        return []
    params = {"status": "IN_PROGRESS", "limit": 20, "offset": 0}

    def _try_fetch(base: Optional[str]) -> Tuple[Optional[requests.Response], Optional[Dict]]:
        return _api_request(
            state,
            "get",
            f"/players/{state.user_id}/history",
            params=params,
            base_url=base,
        )

    resp, payload = _try_fetch(None)
    if resp is None or resp.status_code == 404:
        # Gateway might not expose this route; hit game-engine directly if configured
        if state.game_engine_url:
            resp, payload = _try_fetch(state.game_engine_url)
    if resp is None:
        return []
    if not (200 <= resp.status_code < 300):
        _print_error(resp, payload)
        return []
    matches = payload.get("matches") or []
    if not matches and params.get("status"):
        # Try again without status filter as a fallback
        params.pop("status", None)
        resp, payload = _try_fetch(None)
        if resp is None or (resp.status_code == 404 and state.game_engine_url):
            resp, payload = _try_fetch(state.game_engine_url)
        if resp and 200 <= resp.status_code < 300:
            matches = payload.get("matches") or []
    if not matches:
        print("No ongoing matches found.")
        return []
    print("Ongoing matches:")
    for idx, match in enumerate(matches, start=1):
        opp_id = match.get("opponent_id")
        status = match.get("status")
        score_me = match.get("player_score")
        score_opp = match.get("opponent_score")
        print(f"[{idx}] id={match.get('id')} status={status} you={score_me} opp={score_opp} vs {opp_id}")
    return matches

def cmd_rejoin(state: ClientState) -> None:
    matches = list_active_matches(state)
    if not matches:
        return
    while True:
        choice = input("Select match number or ID to rejoin (blank to cancel): ").strip()
        if not choice:
            return
        selected = None
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(matches):
                selected = matches[idx - 1]
        if selected is None:
            for match in matches:
                if str(match.get("id")) == choice:
                    selected = match
                    break
        if not selected:
            print("Invalid selection.")
            continue
        state.match_id = _as_int(selected.get("id"))
        state.match_info = selected
        state.played_cards = _extract_played_cards(selected, state.user_id)
        info = fetch_match_info(state)
        print(f"Rejoined match {state.match_id}.")
        if info:
            print(_format_match_summary(info, state.user_id))
        return

COMMANDS = {
    "register": ("Register a new user", cmd_register),
    "login": ("Login", cmd_login),
    "enqueue": ("Join the matchmaking queue", cmd_enqueue),
    "poll-match": ("Poll status until matched", lambda s: poll_matchmaking(s, blocking=True)),
    "rejoin": ("List ongoing matches and reattach to one", cmd_rejoin),
    "cards": ("List available cards", fetch_cards),
    "deck": ("Choose and submit a deck", cmd_submit_deck),
    "match": ("Show current match summary", show_match),
    "poll-round": ("Poll round status until you can move", cmd_poll_round),
    "move": ("Submit a move for the current round", cmd_play_move),
    "help": ("Show this help", None),
    "exit": ("Exit the client", None),
    "quit": ("Exit the client", None),
}

def main() -> None:
    parser = argparse.ArgumentParser(description="CLI client for the card game services")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Gateway base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--engine-url",
        default=os.getenv("GAME_ENGINE_URL"),
        help="Direct Game Engine URL for routes not proxied by the gateway (optional)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="Seconds between polling attempts",
    )
    parser.add_argument(
        "--poll-timeout",
        type=float,
        default=DEFAULT_POLL_TIMEOUT,
        help="Maximum seconds to poll for queue/rounds",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT,
        help="Per-request timeout in seconds",
    )
    args = parser.parse_args()

    state = ClientState(
        base_url=args.base_url,
        game_engine_url=args.engine_url,
        request_timeout=args.request_timeout,
        poll_interval=args.poll_interval,
        poll_timeout=args.poll_timeout,
    )

    print("Card Game CLI")
    print("Type 'help' to see commands.")
    while True:
        try:
            cmd = input(">> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not cmd:
            continue
        if cmd in {"exit", "quit"}:
            break
        if cmd == "help":
            for name, (desc, _) in COMMANDS.items():
                print(f"{name:<12} {desc}")
            continue
        entry = COMMANDS.get(cmd)
        if not entry:
            print("Unknown command. Type 'help' for the list.")
            continue
        func = entry[1]
        if func is fetch_cards:
            func(state)
        else:
            func(state)

if __name__ == "__main__":
    sys.exit(main())
