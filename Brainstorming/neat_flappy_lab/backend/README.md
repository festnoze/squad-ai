# neat_flappy_lab — backend

NEAT (topology-augmenting neuroevolution) + optional lifetime gradient descent
(imitation of the elite) playing a Flappy-like game. Everything is tunable from
the frontend via a validated config schema; state streams over WebSocket.

See `../PLAN.md` for the full design.

## Setup

```bash
uv venv
uv pip install -e ".[dev]"
```

## Headless run

```bash
uv run nfl --mode evolution_only --generations 50
uv run nfl --mode write_back --generations 50 --max-ticks 500
uv run nfl --mode evaluate_only --generations 50
```

## API server (for the frontend)

```bash
uv run uvicorn nfl.api.server:app --reload --port 8000
```

- `GET /config/schema` — JSON schema of every tunable (the frontend auto-builds its controls from this).
- `GET /config/defaults` — default values.
- `WS /ws` — live engine: send `{"type":"config","patch":{...}}`, `{"type":"control","action":"play|pause|step|reset"}`, `{"type":"select","birdId":N}`; receive `frame`, `generation`, `genome`, `config`, `error` messages.

## Tests

```bash
uv run pytest -q
```

33 tests: NEAT engine (genome/mutations/crossover/speciation/population), the
hand-written autograd (gradient-checked vs finite differences), and the API.

## Layout

```
nfl/
  config.py            # SimConfig: every tunable + bounds (drives /config/schema)
  neat/                # genome, mutations, crossover, speciation, population
  nn/                  # network (forward) + autograd (hand-written backprop)
  learning/imitation.py# lifetime GD by imitation of the elite
  sim/flappy.py        # vectorized Flappy world
  engine/              # runner (3 modes) + snapshots
  api/                 # FastAPI + WebSocket + config schema
  cli.py               # headless driver
```
