# Carusi S.r.l.

Team members:
- Francesco Alizzi
- Andrea Riolo Vinciguerra
- Rebecca Rodi
- Francesco Scarfato


## Game overview

### Cards set

The cards set represents the 20 regions of Italy.

Each card contains an image representing the region, its total score and the category subscores which it is based upon, namely *Economy*, *Environment*, *Food*, and *Special*.
The scores of Economy, Environment and Food were assigned on the basis of real data, while the Special score was assigned according to subjective criteria.

<p align="center">
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/04-campania.png?raw=true" alt="Campania" width="100"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/07-lazio.png?raw=true" alt="Lazio" width="100"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/08-liguria.png?raw=true" alt="Liguria" width="100"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/15-sicilia.png?raw=true" alt="Sicilia" width="100"/>
</p>

<p align="center">
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/01-abruzzo.png?raw=true" alt="Abruzzo" width="80"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/02-basilicata.png?raw=true" alt="Basilicata" width="80"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/03-calabria.png?raw=true" alt="Calabria" width="80"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/05-emilia_romagna.png?raw=true" alt="Emilia-Romagna" width="80"/>
</p>

<p align="center">
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/06-friuli_venezia_giulia.png?raw=true" alt="Friuli-Venezia Giulia" width="80"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/09-lombardia.png?raw=true" alt="Lombardia" width="80"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/10-marche.png?raw=true" alt="Marche" width="80"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/11-molise.png?raw=true" alt="Molise" width="80"/>
</p>

<p align="center">
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/12-piemonte.png?raw=true" alt="Piemonte" width="80"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/13-puglia.png?raw=true" alt="Puglia" width="80"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/14-sardegna.png?raw=true" alt="Sardegna" width="80"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/16-toscana.png?raw=true" alt="Toscana" width="80"/>
</p>

<p align="center">
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/17-trentino_alto_adige.png?raw=true" alt="Trentino-Alto Adige" width="80"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/18-umbria.png?raw=true" alt="Umbria" width="80"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/19-valle_aosta.png?raw=true" alt="Valle d'Aosta" width="80"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/20-veneto.png?raw=true" alt="Veneto" width="80"/>
</p>

### Game rules


## Project overview

### Architecture

Carusi S.r.l. is implemented as a constellation of Flask microservices that only share JWT-signed identities. Every module has its own `Dockerfile`, while `docker-compose.yml` provisions per-service PostgreSQL databases plus Redis instances for the pieces that need ephemeral state. The shared `src/common` package contributes the Flask app factory, SQLAlchemy/Bcrypt/JWT extensions, and the reusable `RedisManager`, so every service boots consistently yet stays isolated. The main components are:

- **API Gateway (`src/api_gateway`)** – exposes `/health`, `/services`, and `/services/<name>/health` by reading the upstream URLs from `Config.SERVICE_DEFAULTS`. Today it surfaces metadata and health probes, but it is the public entry point that knows how to contact `http://auth:5000`, `http://matchmaking:5004`, `http://game-engine:5003`, and the other internal hosts declared in the compose file.
- **Auth service (`src/auth`)** – implements `/register`, `/login`, `/refresh`, and `/logout`. Users are stored via SQLAlchemy, credentials are hashed with Bcrypt, JWT access/refresh tokens are minted through Flask-JWT-Extended, and refresh JTIs are stored inside Redis so `logout` can revoke every session. RSA keys arrive via Docker secrets (`AUTH_PRIVATE_KEY`/`AUTH_PUBLIC_KEY`), and all other services verify tokens with the shared public key.
- **Players service (`src/players`)** – persists public player profiles (`PlayerProfile`). The `/players/<user_id>` endpoints let clients create or update usernames, bios, avatars, and other metadata tied to the authenticated `user_id`.
- **Catalogue service (`src/catalogue`)** – is the source of truth for the 20 Italian-region cards in `cards/cards.json`. It exposes `/cards`, `/cards/<id>`, and `/cards/validation` so deck builders can fetch stats or confirm that a submitted deck matches what the DB contains.
- **Matchmaking service (`src/matchmaking`)** – protects `/enqueue` and `/dequeue` with JWTs and keeps a Redis sorted set (`MATCHMAKING_QUEUE_KEY`) as a lobby. `_enqueue_atomic` guarantees atomic queue mutations, pairs the oldest two players, invokes the `call_game_engine` hook (currently a logging stub), and responds with the matched IDs.
- **Game Engine service (`src/game_engine`)** – stores `Match` and `Move` rows, exposes the `/game/**` routes, and delegates the core rules to `game_engine/GameEngine`. That module defines constants such as `DECK_SIZE = 10` and `MAX_ROUNDS = 10`, validates input, calculates round scores, advances to the next category, and finalizes winners.

Other supporting pieces include the `cards/` directory (images plus JSON used to seed the catalogue) and the environment wiring provided by Compose. Tests reuse in-memory SQLite databases and `fakeredis` via each service’s `create_test_app`, so they never touch the production containers.

### Match flow

A single match traverses several services and HTTP endpoints:

1. **Authentication** – Players register and log in through the Auth service to obtain a JWT access token plus a refresh cookie. That token is attached to subsequent `Authorization: Bearer` headers so downstream services know the player’s `user_id`.
2. **Profile setup** – Players may call the Players service (`POST /players/<user_id>`) to create or update their public profile, so opponents can see usernames and avatars distinct from the auth database.
3. **Queueing** – Ready players call `POST /enqueue` on Matchmaking. The service stores their identity inside a Redis sorted set keyed by `MATCHMAKING_QUEUE_KEY`; when the second player arrives the oldest two entries are popped and delivered to the caller while `call_game_engine` is invoked (currently it only logs, but it marks the future hand-off spot to the Game Engine).
4. **Match creation** – With two IDs in hand, a client creates a match by calling `POST /game/matches`. `GameEngine.validate_match_creation` ensures the IDs differ and are integers, then a `Match` row is stored in the `SETUP` state with a random `current_round_category`.
5. **Deck selection** – Each player submits exactly 10 unique card IDs via `POST /game/matches/<match_id>/deck`. `GameEngine.validate_deck_submission` enforces membership, deck size, and uniqueness before assigning the card stats to `player*_deck`. The route is wired for a Catalogue RPC (currently stubbed with random stats) and flips the match into `IN_PROGRESS` once both decks are registered.
6. **Rounds** – Every round compares a single category chosen from `["economy", "food", "environment", "special", "total"]`. The first player to call `POST /game/matches/<match_id>/moves` receives `{"status": "WAITING_FOR_OPPONENT"}`. When the second move arrives, the match row is locked, both `Move` rows are analyzed through `GameEngine.calculate_round_scores`, the winner is computed, the scoreboard is updated, and either the next round begins (with a fresh random category) or the match ends when `MAX_ROUNDS` (10) have been played.
7. **Observability** – Clients can poll `/game/matches/<match_id>/round` to see whether both moves have been submitted, fetch `/game/matches/<match_id>` for a summary without moves, or `/game/matches/<match_id>/history` for the entire move log (with `joinedload` to avoid N+1 queries).
8. **Completion** – When the end condition is met, `GameEngine.finalize_match` sets `status = FINISHED`, stores `winner_id` (or `None` for a draw), clears the active category, and the final `submit_move` response includes the updated scores so the UI can show the result.

### Compilation instructions

**Docker Compose (full stack)**

1. Install Docker and Docker Compose, then place an RSA key pair under `secrets/jwtRS256.key` and `secrets/jwtRS256.key.pub` (they are mounted as the `jwt_*` secrets referenced by `docker-compose.yml`). Without those files the containers fall back to symmetric JWTs, which is acceptable only for ad-hoc local runs.
2. From the repository root execute `docker compose up --build`. Compose builds every microservice image, provisions PostgreSQL/Redis sidecars for Auth, Catalogue, Players, Matchmaking, and the Game Engine, and connects them on a shared network so they can reach each other through hostnames such as `auth`, `catalogue`, or `game-engine`.
3. Once the stack is up, inspect `http://localhost:5080/health` for the gateway view or hit each service directly on ports 5000–5004 to drive the APIs. Logs show when Matchmaking pairs players and when a match transitions through its life cycle.

**Running individual services for development**

1. Create a virtual environment (Python 3.13 matches the Docker image) and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Export service-specific settings. The default configs use in-memory SQLite databases and expect Redis; to avoid external dependencies set `FAKE_REDIS=1` for Auth or Matchmaking, or point `*_DATABASE_URL`/`*_REDIS_URL` to your own instances.
3. Start the service you need, e.g. `flask --app=auth.app run --port=5000`, `python src/catalogue/app.py`, `python src/players/app.py`, `flask --app=matchmaking.app run --port=5004`, or `python src/game_engine/app.py`. Run them from the repository root (or export `PYTHONPATH=src`) so imports like `common.extensions` resolve correctly.

### Tests

All automated checks live under `tests/` and use pytest. `tests/conftest.py` spins up isolated Flask apps for every microservice, swaps in-memory SQLite databases plus `fakeredis` through each `TestConfig`, and tears everything down after every test, so the suite runs without Docker.

Run the full suite with:

```bash
pytest
```

Key suites:

- `tests/test_auth.py` verifies registration, login, refresh, and logout, asserting that refresh tokens are stored in and removed from Redis and that CSRF-protected cookies behave as expected.
- `tests/test_catalogue.py` loads the data from `cards/cards.json`, checks the `/cards` and `/cards/<id>` contracts, and exercises the `/cards/validation` rule set.
- `tests/test_matchmaking.py` uses `fakeredis` to populate the lobby, ensures `_enqueue_atomic` pairs players fairly, and validates `/dequeue` when players leave or were already matched.
- `tests/test_game_engine.py` covers the pure business logic in `game_engine/GameEngine`—score calculation, per-round winners, match finalization, and round advancement.
- `tests/test_game_engine_api.py` drives the `/game/**` endpoints end-to-end by creating a match, monkeypatching the catalogue lookup, submitting decks/moves for both players, and confirming that the match history records every move until `FINISHED`.


## Credits
