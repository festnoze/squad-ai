# Prediction Exchange (pxe)

An arena where LLM agents trade binary contracts on a shared central limit order
book. Each agent gets capital, partial and asymmetric information (noisy public
news plus private signals) and two independent ways to express a belief:
declared probabilities scored with the Brier score, and orders scored with PnL.
The simulation engine is the only referee: matching, accounting and event
resolution are deterministic, and **no metric depends on an LLM judge**.

> **Read `docs/CONTRACTS.md` before writing a single line of code.** It is the
> single source of truth for module boundaries, public APIs, the determinism
> contract, the event sourcing contract and the accounting invariants. The PRD
> (`PRD_Prediction_Exchange v2.md`, French) is the functional reference;
> `docs/CONTRACTS.md` is the technical one.

## Layout

```
docs/CONTRACTS.md          the anchor contract, authoritative
schemas/                   versioned JSON Schemas (observation, action)
src/pxe/                   the Python package
tests/                     pytest suite, one file per owning module
web/                       React + Vite replay front end
Makefile                   every developer entry point
.github/workflows/ci.yml   the T1.1 gate: lint, types, tests, coverage
runs/                      match journals and traces (git ignored)
```

## Install

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

git-bash or Linux:

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e ".[dev]"
```

The LLM path additionally requires the **Claude Code CLI** on the `PATH`
(`claude.cmd` on Windows, `claude` elsewhere), already authenticated over OAuth.
`ANTHROPIC_API_KEY` is not used and `--bare` is never passed.

## Run the tests

Use the Makefile. Every recipe is a single `python -m <tool>` call, so the same
targets work in PowerShell, Git Bash and `sh`, and `PY` is overridable
(`make test PY=python`).

```bash
make test          # the whole suite, quiet
make test-fast     # no llm, no slow, no statistical
make determinism   # the O1 / AC-P1 guards, never skipped
make lint          # ruff check src tests
make format-check  # ruff format --check src tests
make typecheck     # mypy, strict, over src/pxe
make cov           # coverage, terminal plus coverage.xml
make gate          # everything CI runs, in CI order
make help          # the list above, generated from the Makefile
```

Without `make`, the same four commands are:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m mypy
```

Markers are strict: an unregistered marker fails the run. Register new ones in
`pyproject.toml`. Shared fixtures live in `tests/conftest.py` and ten names are
reserved there (`standard_config`, `tiny_world`, `flat_accounts`,
`scripted_gateway`, ...); see CONTRACTS section 10 before inventing your own.

## CI

`.github/workflows/ci.yml` runs five jobs on every push and pull request:

| Job | What it proves |
|---|---|
| `quality` | `make lint`, `make format-check`, `make typecheck`, and the repository wide style scan (`tests/test_style_rules.py`) |
| `test` | the fast suite plus the determinism guards, on **Linux and Windows** |
| `determinism-cross-platform` | publishes the reference journal hash from each platform: AC-P1's "two machines" clause |
| `coverage` | everything except the `llm` tests, publishing `coverage.xml` and `htmlcov/` |
| `web` | `npm ci`, typecheck, vitest and build, skipped until `web/package.json` exists |

## Run a scripted match (no LLM, no network, no cost)

```powershell
.\.venv\Scripts\pxe.exe match run `
    --template election --seed 42 `
    --agents fundamentalist,momentum,noise,zero_intelligence,fundamentalist,momentum `
    --ticks 48 --liquidity standard --out runs
```

This writes `runs/<match_id>/journal.jsonl` plus a printed summary holding the
final ranking, the journal hash and the market maker PnL (the cost of
liquidity). A 6 agents x 48 ticks scripted match must complete in under 5
seconds (milestone M0).

Verify determinism (AC-P1) by replaying the same seed twice and comparing the
journal hashes:

```powershell
.\.venv\Scripts\pxe.exe match verify --template election --seed 42 --repeat 2
```

Replay an existing journal into a state and recompute every metric from it
alone (FR-5.1.3):

```powershell
.\.venv\Scripts\pxe.exe match replay runs/m-election-42-00/journal.jsonl
```

## Run an LLM match

Costs real money. Budget caps are mandatory and enforced by the gateway; one
provider call per agent per tick covers **all** markets at once.

```powershell
.\.venv\Scripts\pxe.exe match run `
    --template election --seed 42 `
    --agents llm:sonnet5,llm:sonnet5,llm:sonnet5,llm:sonnet5,fundamentalist,noise `
    --model claude-sonnet-5 `
    --budget-usd-per-call 0.10 --budget-usd-per-match 5.00 `
    --timeout 60 --out runs
```

Order of magnitude measured on the Claude Code CLI: about 0.027 USD and 6
seconds per call, with roughly 35k cached input tokens of unavoidable CLI
overhead. A 6 tick smoke match with 4 LLM agents therefore costs about 0.65 USD.
Use `--ticks 6` for smoke tests.

Provider traces (cost, latency, token counts, retries) land in
`runs/<match_id>/llm_trace.jsonl`. They are deliberately **not** part of the
journal.

That is not the same as saying an LLM match is reproducible. It is not:
`agent_timed_out` is a journal event and whether it fires is a wall clock and
budget decision, so a slow provider run and a fast one on the same seed diverge
from the first timeout onwards. The honest statement, and the one the contract
makes in section 3.7, is: **the engine's decisions are a deterministic function
of the actions it received; the journal of an LLM match replays bit identically
through `pxe match replay`, but re-running the same seed against a provider is
not expected to reproduce it.** Bit identical re-runs (AC-P1) are a scripted
match guarantee, checked by `pxe match verify`.

## Run a tournament

```powershell
.\.venv\Scripts\pxe.exe tournament run --config configs/nightly.toml --out runs
.\.venv\Scripts\pxe.exe report build --tournament T-nightly-0007 --format md,html
```

## Start the API and the UI

```powershell
.\.venv\Scripts\pxe.exe api serve --host 127.0.0.1 --port 8400 --runs-dir runs
```

REST plus WebSocket replay on `http://127.0.0.1:8400`, OpenAPI at `/docs`.

```powershell
cd web
npm install
npm run dev            # Vite dev server on http://127.0.0.1:5173, proxies /api to 8400
npm run build          # static bundle in web/dist, served by the API at /replay/<id>
```

A shared replay URL is a plain path with no query string and no token,
`http://127.0.0.1:8400/replay/<match_id>`, and the API exposes no mutating
verb at all (CONTRACTS section 7.21, decision 33).

## Golden rules for contributors

1. Money is an integer number of cents. Prices are integers in `[1, 99]`.
   Quantities are integer contracts. **No float ever touches money.**
2. The journal contains no floats, no timestamps and no provider metrics.
   Probabilities are `*_ppm` integers, latent quantities are `*_milli`
   integers.
3. All randomness comes from `pxe.rng.RngTree` through a **named, registered**
   substream. No `random.random()`, no `uuid4()`, no clock inside the engine.
4. The engine never calls an LLM (FR-5.1.2). Only `pxe.gateway` is async, and
   only async functions are prefixed with `a` (`acollect_actions`,
   `acall_agent`). `run_match` is synchronous and there is no `arun_match`.
5. Code, comments and docs in English. The PRD is French; the code is not.
6. Never use the em-dash character in any produced content.
   `tests/test_style_rules.py` scans the whole repository for it; the French
   PRD and `docs/reviews/` are exempt because they are inputs, not output.
7. Never edit a file you do not own. Ownership is CONTRACTS table 1, and a
   change to somebody else's file is a contract change: amend
   `docs/CONTRACTS.md` first.
