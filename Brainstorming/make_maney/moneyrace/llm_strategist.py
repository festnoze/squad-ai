"""Optional LLM strategist: asks the Claude CLI to design offspring genomes.

Off by default; enable with --llm-strategist. Each call shells out to
`claude -p` in headless mode, so it costs tokens and wall clock time. The
world only consults it for a fraction of births (config.strategist_share),
and any failure (no CLI, timeout, bad JSON) silently falls back to normal
mutation so a run can never be blocked by the LLM.
"""

import json
import shutil
import subprocess

from .genome import GENE_NAMES

PROMPT_TEMPLATE = """You are designing the genome of a money-making agent in an
evolutionary simulation. All genes are floats in [0, 1]:
- risk: fraction of wealth put at stake per arena
- auction_shade: bid shading in second-price auctions (low avoids the winner's curse)
- signal_trust: trust in noisy signals vs the prior
- momentum: trend-following weight in a market with drift regimes
- reversion: mean-reversion weight in the same market
- trade_size: position sizing in the market
- confidence: bet threshold and sizing when betting against a mispricing house

Recent generation statistics (JSON):
{history}

A mutated baseline genome you may improve on:
{baseline}

Reply with ONLY a JSON object mapping every gene name to a float in [0, 1].
No prose, no markdown fences."""


class ClaudeStrategist:
    def __init__(self, timeout=90):
        self.timeout = timeout
        self.available = shutil.which("claude") is not None
        self.calls = 0
        self.successes = 0

    def propose(self, history, baseline):
        if not self.available:
            return None
        self.calls += 1
        tail = [
            {
                "generation": row["generation"],
                "mean_wealth": round(row["mean_wealth"], 1),
                "max_wealth": round(row["max_wealth"], 1),
                "deaths": row["deaths"],
                "gene_means": {k: round(v, 3) for k, v in row["gene_means"].items()},
            }
            for row in history[-5:]
        ]
        prompt = PROMPT_TEMPLATE.format(
            history=json.dumps(tail), baseline=json.dumps(baseline))
        try:
            # Prompt goes through stdin: `claude -p` reads it, and this avoids
            # shell quoting issues on Windows where claude is a .cmd shim.
            proc = subprocess.run(
                "claude -p", shell=True, input=prompt,
                capture_output=True, text=True, timeout=self.timeout)
            if proc.returncode != 0:
                return None
            text = proc.stdout.strip()
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                return None
            data = json.loads(text[start:end + 1])
            genes = {}
            for name in GENE_NAMES:
                genes[name] = min(1.0, max(0.0, float(data[name])))
            self.successes += 1
            return genes
        except Exception:
            return None
