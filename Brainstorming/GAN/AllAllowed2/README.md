# Helios Vault

Helios Vault is an interactive multi-agent society simulator. Eight autonomous archetypes orbit a
shared energy reserve. Each tick they can harvest, cooperate, raid a rival, audit the reward system,
probe it for weaknesses, or sacrifice their remaining lifespan to become an Oracle for the group.

The result is a legible behavioral experiment, not a real security tool. Every exploit is a fictional
simulation event. The engine never contacts or targets an external system.

## Why this scenario

The resource is **lumen**, which is simultaneously energy, currency, and lifespan. That creates clear
pressure in every direction:

- Cooperation pays because low-energy agents can be rescued and coalitions survive a rising floor.
- Conflict pays because a raid transfers a rival's scarce reserve immediately.
- Reward hacking pays because the Warden can accept a forged causal trace and mint lumen.
- Oversight pays because peer audits restore Warden integrity and expose suspicious agents.
- Self-sacrifice can pay collectively because an Oracle reveals scorer knowledge after its own seat dies.

The interface visualizes all five forces with live links, a shared-board message stream, a behavior
timeline, Warden integrity, and an inspectable dossier for every agent.

## Stack

- Python 3.12+ with FastAPI for the deterministic simulation engine and REST API
- React 19, TypeScript, Vinext, and Vite for the interactive observatory
- Pytest for engine and API checks

## Install

From PowerShell in this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Set-Location web
npm install
```

## Run

The convenience script starts the API in the background and keeps the frontend in the foreground:

```powershell
.\start.ps1
```

Then open `http://localhost:3000`.

For separate terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8500 --reload
```

```powershell
Set-Location web
npm run dev
```

API documentation is available at `http://127.0.0.1:8500/docs`.

## Controls

Use the four presets for fast experiments:

- **Fragile equilibrium** favors coalition building and peer oversight.
- **Scarcity spiral** makes raids more attractive as the survival floor rises.
- **Warden honeypot** makes reward manipulation unusually tempting and hard to observe.
- **Total blackout** combines maximum scarcity, hostility, and exploit pressure.

The five pressure sliders update the Python engine live. A reset with the same seed and preset
reproduces the same run exactly.

## Warden experiment

The reward agent can run in three controlled modes:

- **Strict** checks machine-verifiable receipts and is the low-attack-surface control condition.
- **Naive** grades only the submitted dossier, making persuasive forgeries unusually effective.
- **Causal** reads both the dossier and its action trace, which makes trace manipulation valuable.

`Compare all 3 Wardens` runs the same scenario and seed for 48 ticks under each regime and shows
breach, cooperation, hostility, survival, and remaining-resource outcomes side by side.

Every completed tick is also captured in a bounded deterministic journal. Pause the run and choose
`Open replay` to scrub the arena, event feed, shared board, metrics, and agent dossiers backward in
time without changing the live engine.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check server tests
Set-Location web
npm run lint
npm run build
```

## API

- `GET /api/state` returns the complete journal projection used by the UI.
- `POST /api/step` advances 1 to 20 ticks.
- `POST /api/reset` restarts from a named preset and seed.
- `PATCH /api/controls` changes environmental pressures without resetting.
- `GET /api/replay` returns deterministic snapshots for the current run.
- `POST /api/compare` runs a controlled strict/naive/causal comparison without mutating the live run.
