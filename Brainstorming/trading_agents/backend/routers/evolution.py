"""GP Evolution via WebSocket — streams generation-by-generation progress.

Supports dual-tree evolution (separate entry + exit trees).
"""
from __future__ import annotations

import sys
import json
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.data.provider import load_price_data, INTERVAL_TO_FREQ  # noqa: E402
from src.agent.evolution import setup_evolution, validate_top_strategies  # noqa: E402
from backend.schemas import EvolutionConfig  # noqa: E402

router = APIRouter()


async def _send_json(ws: WebSocket, data: dict) -> None:
    text = json.dumps(data, default=str, allow_nan=False)
    await ws.send_text(text)


def _safe_float(v: float) -> float | None:
    if np.isnan(v) or np.isinf(v):
        return None
    return round(float(v), 6)


@router.websocket("/ws")
async def evolution_ws(ws: WebSocket):
    """WebSocket endpoint for dual-tree GP evolution with live progress."""
    await ws.accept()

    try:
        raw = await ws.receive_text()
        config = EvolutionConfig(**json.loads(raw))

        await _send_json(ws, {"type": "status", "message": "Loading price data..."})

        df = load_price_data(config.symbol, interval=config.interval,
                             start=config.start, end=config.end)
        freq = INTERVAL_TO_FREQ[config.interval]

        train_end = pd.Timestamp(config.train_end)
        df_train = df.loc[:train_end]
        df_test = df.loc[train_end:]

        if len(df_train) < 60:
            await _send_json(ws, {"type": "error",
                "message": f"Training set too small: {len(df_train)} bars (need >= 60)"})
            await ws.close()
            return

        if len(df_test) < 20:
            await _send_json(ws, {"type": "error",
                "message": f"Test set too small: {len(df_test)} bars (need >= 20)"})
            await ws.close()
            return

        await _send_json(ws, {"type": "status",
            "message": f"Data: {len(df_train)} train / {len(df_test)} test. Setting up evolution..."})

        toolbox, pset, stats, hof = setup_evolution(
            df_train=df_train, freq=freq,
            init_cash=10_000, fees=0.001,
            complexity_penalty=config.complexity_penalty,
            max_depth=config.max_depth, seed=config.seed,
        )

        pop = toolbox.population(n=config.pop_size)
        cx_prob = 0.7
        mut_prob = 0.2

        await _send_json(ws, {"type": "status",
            "message": f"Population: {config.pop_size} individuals. Starting {config.n_gen} generations..."})

        # Evaluate initial population
        invalid_ind = [ind for ind in pop if not ind.fitness.valid]
        fitnesses = list(map(toolbox.evaluate, invalid_ind))
        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = fit
        hof.update(pop)

        fits = [ind.fitness.values[0] for ind in pop]
        viable_fits = [f for f in fits if f > -900]
        await _send_json(ws, {"type": "generation", "gen": 0,
            "nevals": len(invalid_ind),
            "avg": _safe_float(float(np.mean(viable_fits)) if viable_fits else 0.0),
            "best": _safe_float(float(max(fits))),
            "viable": len(viable_fits)})

        # Evolution loop
        for gen in range(1, config.n_gen + 1):
            offspring = toolbox.select(pop, len(pop))
            offspring = [toolbox.clone(ind) for ind in offspring]

            # Crossover
            import random
            for i in range(1, len(offspring), 2):
                if random.random() < cx_prob:
                    toolbox.mate(offspring[i - 1], offspring[i])
                    del offspring[i - 1].fitness.values
                    del offspring[i].fitness.values

            # Mutation
            for i in range(len(offspring)):
                if random.random() < mut_prob:
                    toolbox.mutate(offspring[i])
                    del offspring[i].fitness.values

            # Evaluate
            invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
            fitnesses = list(map(toolbox.evaluate, invalid_ind))
            for ind, fit in zip(invalid_ind, fitnesses):
                ind.fitness.values = fit

            pop[:] = offspring
            hof.update(pop)

            fits = [ind.fitness.values[0] for ind in pop]
            viable_fits = [f for f in fits if f > -900]
            await _send_json(ws, {"type": "generation", "gen": gen,
                "nevals": len(invalid_ind),
                "avg": _safe_float(float(np.mean(viable_fits)) if viable_fits else 0.0),
                "best": _safe_float(float(max(fits))),
                "viable": len(viable_fits)})

        # Validate top strategies
        await _send_json(ws, {"type": "status", "message": "Validating top strategies..."})

        top_results = validate_top_strategies(
            hof=hof, toolbox=toolbox,
            df_train=df_train, df_test=df_test, freq=freq,
            init_cash=10_000, fees=0.001, top_n=5,
        )

        strategies_out = []
        for r in top_results:
            entry = {
                "rank": r["rank"],
                "entry_expression": r.get("entry_expression", r.get("expression", "")),
                "exit_expression": r.get("exit_expression", ""),
                "entry_size": r.get("entry_size", r.get("tree_size", 0)),
                "exit_size": r.get("exit_size", 0),
                "train_return": _safe_float(r.get("train_return", 0)),
                "train_sharpe": _safe_float(r.get("train_sharpe", 0)),
                "train_drawdown": _safe_float(r.get("train_drawdown", 0)),
                "train_trades": r.get("train_trades", 0),
                "test_return": _safe_float(r.get("test_return", 0)),
                "test_sharpe": _safe_float(r.get("test_sharpe", 0)),
                "test_drawdown": _safe_float(r.get("test_drawdown", 0)),
                "test_trades": r.get("test_trades", 0),
                "is_overfit": (r.get("test_sharpe", 0) or 0) < (r.get("train_sharpe", 0) or 0) * 0.3,
            }
            strategies_out.append(entry)

        await _send_json(ws, {"type": "complete", "top_strategies": strategies_out})

    except WebSocketDisconnect:
        pass
    except json.JSONDecodeError as exc:
        try:
            await _send_json(ws, {"type": "error", "message": f"Invalid JSON: {exc}"})
        except Exception:
            pass
    except Exception as exc:
        try:
            await _send_json(ws, {"type": "error",
                "message": f"Evolution failed: {exc}\n{traceback.format_exc()}"})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
