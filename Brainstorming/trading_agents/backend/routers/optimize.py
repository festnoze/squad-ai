"""Optuna hyperparameter optimization via WebSocket — live trial-by-trial progress."""
from __future__ import annotations

import sys
import json
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.data.provider import load_price_data, INTERVAL_TO_FREQ  # noqa: E402

router = APIRouter()


class OptimizeConfig(BaseModel):
    symbol: str
    interval: str = "1d"
    start: str = "2020-01-01"
    end: str = "2026-05-31"
    train_end: str = "2025-01-01"
    n_trials: int = 15
    seed: int = 42


def _safe(v: float) -> float | None:
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    return round(float(v), 6)


@router.websocket("/ws")
async def optimize_ws(ws: WebSocket):
    """WebSocket endpoint for Optuna GP hyperparameter optimization."""
    await ws.accept()

    try:
        raw = await ws.receive_text()
        config = OptimizeConfig(**json.loads(raw))

        await ws.send_text(json.dumps({"type": "status", "message": "Loading data..."}))

        df = load_price_data(config.symbol, interval=config.interval,
                             start=config.start, end=config.end)
        freq = INTERVAL_TO_FREQ[config.interval]

        train_end = pd.Timestamp(config.train_end)
        df_train = df.loc[:train_end]
        df_test = df.loc[train_end:]

        if len(df_train) < 60 or len(df_test) < 20:
            await ws.send_text(json.dumps({
                "type": "error",
                "message": f"Insufficient data: train={len(df_train)}, test={len(df_test)}"
            }))
            await ws.close()
            return

        await ws.send_text(json.dumps({
            "type": "status",
            "message": f"Data: {len(df_train)} train / {len(df_test)} test. Starting {config.n_trials} Optuna trials..."
        }))

        # Import here to avoid slow startup
        from src.agent.optimizer import optimize_gp_hyperparams  # noqa: E402

        # Callback to stream progress
        import asyncio
        loop = asyncio.get_event_loop()

        trial_results = []

        def on_trial(trial_num, params, score):
            trial_results.append({
                "trial": trial_num,
                "params": {k: round(v, 4) if isinstance(v, float) else v for k, v in params.items()},
                "score": _safe(score),
            })
            # Can't await in sync callback, so we'll send after all trials

        result = optimize_gp_hyperparams(
            df_train=df_train,
            df_test=df_test,
            freq=freq,
            n_trials=config.n_trials,
            seed=config.seed,
            callback=on_trial,
        )

        # Send trial-by-trial results
        for tr in trial_results:
            await ws.send_text(json.dumps({"type": "trial", **tr}, default=str))

        # Send final result
        best_strat = result.get("best_strategy", {})
        await ws.send_text(json.dumps({
            "type": "complete",
            "best_params": result["best_params"],
            "best_score": _safe(result["best_score"]),
            "best_strategy": {
                "entry_expression": best_strat.get("entry_expression", ""),
                "exit_expression": best_strat.get("exit_expression", ""),
                "train_return": _safe(best_strat.get("train_return", 0)),
                "train_sharpe": _safe(best_strat.get("train_sharpe", 0)),
                "test_return": _safe(best_strat.get("test_return", 0)),
                "test_sharpe": _safe(best_strat.get("test_sharpe", 0)),
            },
            "study_stats": result["study_stats"],
            "all_trials": [
                {"trial": t["trial"], "score": t["score"],
                 "params": t["params"]}
                for t in trial_results
            ],
        }, default=str))

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await ws.send_text(json.dumps({
                "type": "error",
                "message": f"Optimization failed: {exc}\n{traceback.format_exc()}"
            }))
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
