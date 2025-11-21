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
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/04-campania.png?raw=true" alt="Campania" width="200"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/07-lazio.png?raw=true" alt="Lazio" width="200"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/08-liguria.png?raw=true" alt="Liguria" width="200"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/15-sicilia.png?raw=true" alt="Sicilia" width="200"/>
</p>

<p align="center">
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/01-abruzzo.png?raw=true" alt="Abruzzo" width="150"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/02-basilicata.png?raw=true" alt="Basilicata" width="150"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/03-calabria.png?raw=true" alt="Calabria" width="150"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/05-emilia_romagna.png?raw=true" alt="Emilia-Romagna" width="150"/>
</p>

<p align="center">
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/06-friuli_venezia_giulia.png?raw=true" alt="Friuli-Venezia Giulia" width="150"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/09-lombardia.png?raw=true" alt="Lombardia" width="150"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/10-marche.png?raw=true" alt="Marche" width="150"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/11-molise.png?raw=true" alt="Molise" width="150"/>
</p>

<p align="center">
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/12-piemonte.png?raw=true" alt="Piemonte" width="150"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/13-puglia.png?raw=true" alt="Puglia" width="150"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/14-sardegna.png?raw=true" alt="Sardegna" width="150"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/16-toscana.png?raw=true" alt="Toscana" width="150"/>
</p>

<p align="center">
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/17-trentino_alto_adige.png?raw=true" alt="Trentino-Alto Adige" width="150"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/18-umbria.png?raw=true" alt="Umbria" width="150"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/19-valle_aosta.png?raw=true" alt="Valle d'Aosta" width="150"/>
<img src="https://github.com/r1olo/ase-project/blob/master/cards/images/20-veneto.png?raw=true" alt="Veneto" width="150"/>
</p>

### Game rules

The game is played between two players.

1. Each player builds a deck of 10 unique cards drawn from the full set of Italian regions.

2. After both players have submitted their decks, the match begins.

3. In each round:

   i. One of the five categories (Economy, Environment, Food, Special, Total) is randomly selected.

   ii. Both players must then select one card from their respective decks.

   iii. The selected cards are revealed simultaneously, and their scores in the chosen category are compared.
   
   The player whose card has the higher score in that category wins the round and earns one point. In case of a tie, no points are awarded.

6. The game continues with subsequent rounds, until all rounds have been played or a player concedes.

7. The player with the most points at the end of the game is declared the winner. In case of a tie, the game ends in a draw.


## Project overview

### Architecture

The card game is implemented as a collection of Flask microservices, which are barely coupled with each other only for the minimum interactions.
All microservices live under their own modules, each one of which has its own `Dockerfile`, while `docker-compose.yml` provisions per-service PostgreSQL databases plus Redis instances for the components that need ephemeral state (such as the matchmaking queue).
The `src/common` package contains shared functionality needed by the modules, including a custom-made Flask extension (`RedisManager`) and a generic app factory function.

<p align="center">
<img src="https://github.com/r1olo/ase-project/blob/master/architecture.png?raw=true" alt="Architecture" width="500"/>
</p>

The main components are:

- **API Gateway (`src/api_gateway`)** &ndash; the main application entrypoint, which exposes all the RESTful API methods as specified in `spec.yaml`. It reads internal components' upstream URLs from `Config.SERVICE_DEFAULTS`. Requests are routed to the appropriate service based on the path prefix.
- **Authentication service (`src/auth`)** &ndash; implements `/register`, `/login`, `/refresh`, and `/logout`. Users are stored via SQLAlchemy in its own database, passwords are hashed with Bcrypt, JWT access/refresh tokens are generated via Flask-JWT-Extended, and refresh JTIs are stored inside Redis so `logout` can revoke every session. RSA keys arrive via Docker secrets (`AUTH_PRIVATE_KEY`/`AUTH_PUBLIC_KEY`), and all other services verify tokens with the shared public key.
- **Players service (`src/players`)** &ndash; stores public player profiles (`PlayerProfile`). The `/players/<user_id>` endpoints let clients create or update usernames, bios, avatars, and other metadata tied to the authenticated `user_id`. This service purposefully does not communicate with the Authentication service as to separate profile data from user credentials, enhancing security.
- **Catalogue service (`src/catalogue`)** &ndash; is the authoritative source of the game cards found in `cards/cards.json`. It exposes `/cards`, `/cards/<id>`, and `/cards/validation` so the game engine or the frontend(s) can fetch stats or confirm that a submitted deck matches what the database contains.
- **Matchmaking service (`src/matchmaking`)** &ndash; exposes `/enqueue` and `/dequeue` with JWTs and keeps a Redis sorted set (indexed by `MATCHMAKING_QUEUE_KEY`) as a lobby. `_enqueue_atomic` guarantees atomic queue mutations, pairs the oldest two players, invokes the `call_game_engine` hook, and records match info per-player so `/status` polling can surface the match ID to players who previously got a `Waiting` response.
- **Game Engine service (`src/game_engine`)** &ndash; the main orchestrator of a match, which stores `Match` and `Move` rows, exposes various routes that allow the players to make their moves and query the match status. It delegates the core rules to the `GameEngine` class, which defines constants such as `DECK_SIZE = 10` and `MAX_ROUNDS = 10`, enabling modularity.

Other supporting elements include the `cards/` directory (images plus JSON used to seed the catalogue) and the environment wiring provided by Docker Compose. The tests reuse in-memory SQLite databases and `fakeredis` via each service’s `create_test_app`, so they never touch the production containers.


### Match flow

A single match goes through several services and HTTP endpoints:

1. **Authentication** &ndash; Players register and log in through the Authentication service to obtain a JWT access token plus a refresh cookie. That token is attached to subsequent `Authorization: Bearer` headers so that all the downstream services within the system can immediately authenticate the player, extracting its `user_id`.
2. **Profile setup** &ndash; Players must call the Players service (`POST /players/<user_id>`) to create their public profile. This step is mandatory before initiating a match, as the Game Engine requires a full profile to proceed. This guarantees a proper separation of concerns between user credentials and public player profiles.
3. **Queueing** Ready players call `POST /enqueue` on Matchmaking service that stores their identity inside a Redis sorted set keyed by `MATCHMAKING_QUEUE_KEY`. Each enqueue returns a queue token; clients poll `GET /status` with their JWT (and optional token) until a match ID appears. As soon as the second player arrives, the oldest two Redis entries are popped atomically and the Game Engine is invoked to form the match while both players' status snapshots are updated in Redis.
4. **Match creation** &ndash; Once the Matchmaking service calls the Game Engine with the two players' IDs, a new match is created and stored within the database. Matched IDs are persisted alongside queue tokens so that both players can discover the match even if only one received the immediate HTTP response.
5. **Deck selection** &ndash; Each player submits exactly 10 unique card IDs via `POST /game/matches/<match_id>/deck`. Once the decks have been submitted by both players, the match enters the ongoing status. At this point the players can start submitting their moves.
6. **Rounds** &ndash; Every round compares a single category chosen from `["economy", "food", "environment", "special", "total"]`. The first player to call `POST /game/matches/<match_id>/rounds/<round_id>` receives `{"status": "WAITING_FOR_OPPONENT"}`. When the second move arrives, the round row is updated, both moves are analyzed through and the winner is computed, and either the next round begins (with a fresh random category) or the match ends when all the rounds have been played.
7. **Status tracking** &ndash; Clients can poll `/game/matches/<match_id>/round/<round_id>` to see whether both moves have been submitted, fetch `/game/matches/<match_id>` for a summary without moves, or `/game/matches/<match_id>/history` for the entire round log.
8. **Completion** &ndash; When the match is over, its status is set to finished, and the `winner_id` (or `None` for a draw) is stored in the database.


### Compilation instructions

1. Install Docker and Docker Compose.
2. Place an RSA key pair under `secrets/jwtRS256.key` and `secrets/jwtRS256.key.pub` (they are mounted as the `jwt_*` secrets referenced by `docker-compose.yml`). The keys can be generated using the script in `scripts/genkeys.sh`. Without those files the containers fall back to symmetric JWTs, which is acceptable only for ad-hoc local runs.
3. From the repository root execute `docker compose up --build`.
4. Once the stack is up, you may access the API Gateway at port `150`. You can access endpoint `/health` for a general service overview.
5. You can simulate a client using the script in `scripts/client.py`. In order to play a game, you need to execute two instances of the client scripts to be able to enqueue and send various moves. The list of available commands can be accessed by running `python scripts/client.py --help`. Notice: the `requests` Python library is required to run the client script.


### Tests

All automated checks live under `tests/` and use pytest. `tests/conftest.py` spins up isolated Flask apps for every microservice, swaps in-memory SQLite databases plus `fakeredis` through each `TestConfig`, and tears everything down after every test, so the suite runs without Docker.

Run the full suite with:

```bash
pytest
```

Run the single tests with logs with:

```bash
pytest -v tests/<test_module>
```

Key suites:

- `tests/test_auth.py` verifies registration, login, refresh, and logout, asserting that refresh tokens are stored in and removed from Redis.
- `tests/test_catalogue.py` checks cards and card by id, and validates decks submitted by players.
<!--
- `tests/test_matchmaking.py` uses `fakeredis` to populate the lobby, ensures `_enqueue_atomic` pairs players fairly, and validates `/dequeue` when players leave or were already matched.
- `tests/test_game_engine.py` covers the pure business logic in `game_engine/GameEngine`—score calculation, per-round winners, match finalization, and round advancement.
- `tests/test_game_engine_api.py` drives the `/game/**` endpoints end-to-end by creating a match, monkeypatching the catalogue lookup, submitting decks/moves for both players, and confirming that the match history records every move until `FINISHED`.
 -->

## Credits
