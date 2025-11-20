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

<!-- TODO -->
The game is played between two players, each of whom builds a deck of 10 unique cards drawn from the full set of 20 Italian regions.


## Project overview

### Architecture

Carusi S.r.l. is implemented as a collection of Flask microservices, which are barely coupled with each other only for the minimum interactions.
All microservices live under their own modules, each one of which has its own `Dockerfile`, while `docker-compose.yml` provisions per-service PostgreSQL databases plus Redis instances for the components that need ephemeral state (such as the matchmaking queue).
The `src/common` package contains shared functionality needed by the modules, including a custom-made Flask extension (`RedisManager`) and a generic app factory function.
The main components are:

- **API Gateway (`src/api_gateway`)** &ndash; the main application entrypoint, which exposes all the RESTful API methods as specified in `spec.yaml`. It reads internal components' upstream URLs from `Config.SERVICE_DEFAULTS`. Requests are routed to the appropriate service based on the path prefix.
- **Authentication service (`src/auth`)** &ndash; implements `/register`, `/login`, `/refresh`, and `/logout`. Users are stored via SQLAlchemy in its own database, passwords are hashed with Bcrypt, JWT access/refresh tokens are generated via Flask-JWT-Extended, and refresh JTIs are stored inside Redis so `logout` can revoke every session. RSA keys arrive via Docker secrets (`AUTH_PRIVATE_KEY`/`AUTH_PUBLIC_KEY`), and all other services verify tokens with the shared public key.
- **Players service (`src/players`)** &ndash; stores public player profiles (`PlayerProfile`). The `/players/<user_id>` endpoints let clients create or update usernames, bios, avatars, and other metadata tied to the authenticated `user_id`. This service purposefully does not communicate with the Authentication service as to separate profile data from user credentials, enhancing security.
- **Catalogue service (`src/catalogue`)** &ndash; is the authoritative source of the game cards found in `cards/cards.json`. It exposes `/cards`, `/cards/<id>`, and `/cards/validation` so the game engine or the frontend(s) can fetch stats or confirm that a submitted deck matches what the database contains.
- **Matchmaking service (`src/matchmaking`)** &ndash; exposes `/enqueue` and `/dequeue` with JWTs and keeps a Redis sorted set (indexed by `MATCHMAKING_QUEUE_KEY`) as a lobby. `_enqueue_atomic` guarantees atomic queue mutations, pairs the oldest two players, invokes the `call_game_engine` hook, and responds with the matched IDs.
- **Game Engine service (`src/game_engine`)** &ndash; the main orchestrator of a match, which stores `Match` and `Move` rows, exposes various routes that allow the players to make their moves and query the match status. It delegates the core rules to the `GameEngine` class, which defines constants such as `DECK_SIZE = 10` and `MAX_ROUNDS = 10`, enabling modularity.

Other supporting elements include the `cards/` directory (images plus JSON used to seed the catalogue) and the environment wiring provided by Docker Compose. The tests reuse in-memory SQLite databases and `fakeredis` via each service’s `create_test_app`, so they never touch the production containers.


### Match flow

A single match goes through several services and HTTP endpoints:

1. **Authentication** &ndash; Players register and log in through the Authentication service to obtain a JWT access token plus a refresh cookie. That token is attached to subsequent `Authorization: Bearer` headers so that all the downstream services within the system can immediately authenticate the player, extracting its `user_id`.
2. **Profile setup** &ndash; Players must call the Players service (`POST /players/<user_id>`) to create their public profile. This step is mandatory before initiating a match, as the Game Engine requires a full profile to proceed. This guarantees a proper separation of concerns between user credentials and public player profiles.
3. **Queueing** Ready players call `POST /enqueue` on Matchmaking service that stores their identity inside a Redis sorted set keyed by `MATCHMAKING_QUEUE_KEY`. As soon as the second player arrives, the oldest two Redis entries are popped and delivered to the caller while the Game Engine is invoked and a match is formed.
4. **Match creation** &ndash; Once the Matchmaking service calls the Game Engine with the two players' IDs, a new match is created and stored within the database.
5. **Deck selection** &ndash; Each player submits exactly 10 (may change in the future) unique card IDs via `POST /game/matches/<match_id>/deck`. Once the decks have been submitted by both players, the match enters the ongoing status. At this point the players can start submitting their moves.
6. **Rounds** &ndash; Every round compares a single category chosen from `["economy", "food", "environment", "special", "total"]`. The first player to call `POST /game/matches/<match_id>/rounds/<round_id>` receives `{"status": "WAITING_FOR_OPPONENT"}`. When the second move arrives, the round row is updated, both moves are analyzed through and the winner is computed, and either the next round begins (with a fresh random category) or the match ends when all the rounds have been played.
7. **Status tracking** &ndash; Clients can poll `/game/matches/<match_id>/round/<round_id>` to see whether both moves have been submitted, fetch `/game/matches/<match_id>` for a summary without moves, or `/game/matches/<match_id>/history` for the entire round log.
8. **Completion** &ndash; When the match is over, its status is set to finished, and the `winner_id` (or `None` for a draw) is stored in the database.


### Compilation instructions

**Docker Compose (full stack)**

1. Install Docker and Docker Compose, then place an RSA key pair under `secrets/jwtRS256.key` and `secrets/jwtRS256.key.pub` (they are mounted as the `jwt_*` secrets referenced by `docker-compose.yml`). Without those files the containers fall back to symmetric JWTs, which is acceptable only for ad-hoc local runs.
2. From the repository root execute `docker compose up --build`. Compose builds every microservice image, provisions PostgreSQL/Redis sidecars for Auth, Catalogue, Players, Matchmaking, and the Game Engine, and connects them on a shared network so they can reach each other through hostnames such as `auth`, `catalogue`, or `game-engine`.
3. Once the stack is up, inspect `http://localhost/health` for the gateway view. Only the gateway is exposed on port 80; all internal services listen on port 5000 and are reachable only from inside the Compose network. Logs show when Matchmaking pairs players and when a match transitions through its life cycle.

**Running individual services for development**

1. Create a virtual environment (Python 3.13 matches the Docker image) and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Export service-specific settings. The default configs use in-memory SQLite databases and expect Redis; to avoid external dependencies set `FAKE_REDIS=1` for Auth or Matchmaking, or point `*_DATABASE_URL`/`*_REDIS_URL` to your own instances.
3. Start the service you need, e.g. `flask --app=auth.app run --port=5000`, `python src/catalogue/app.py`, `python src/players/app.py`, `flask --app=matchmaking.app run --port=5000`, or `python src/game_engine/app.py`. Run them from the repository root (or export `PYTHONPATH=src`) so imports like `common.extensions` resolve correctly.

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
