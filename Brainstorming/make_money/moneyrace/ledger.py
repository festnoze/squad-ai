"""Persistence: write a run's full history and final standings to disk."""

import json
import os


def write_run(out_dir, config, history, leaderboard, graveyard):
    os.makedirs(out_dir, exist_ok=True)

    history_path = os.path.join(out_dir, "history.jsonl")
    with open(history_path, "w", encoding="utf-8") as fh:
        for row in history:
            fh.write(json.dumps(row) + "\n")

    summary_path = os.path.join(out_dir, "run.json")
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump({
            "config": config.as_dict(),
            "leaderboard": leaderboard,
            "deaths_total": len(graveyard),
            "graveyard_tail": graveyard[-50:],
        }, fh, indent=2)

    return {"history": history_path, "summary": summary_path}
