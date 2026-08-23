"""Headless Claude CLI wrapper: prompt via stdin, JSON extraction, logging.

Every call is logged (prompt + raw response) under work/logs so any agent
output can be audited or replayed. All failures return None; callers must
have a deterministic fallback, per the engine's design rule.
"""

import json
import os
import shutil
import subprocess


class ClaudeClient:
    def __init__(self, log_dir, model=None, timeout=240):
        self.log_dir = log_dir
        self.model = model
        self.timeout = timeout
        self.available = shutil.which("claude") is not None
        self.calls = 0

    def run(self, prompt, expect_json=False, label="agent"):
        if not self.available:
            return None
        self.calls += 1
        command = "claude -p" + (f" --model {self.model}" if self.model else "")
        try:
            proc = subprocess.run(command, shell=True, input=prompt,
                                  capture_output=True, text=True,
                                  timeout=self.timeout, encoding="utf-8",
                                  errors="ignore")
        except (OSError, subprocess.TimeoutExpired):
            self._log(label, prompt, "(timeout or launch failure)")
            return None
        raw = (proc.stdout or "").strip()
        self._log(label, prompt, raw)
        if proc.returncode != 0 or not raw:
            return None
        if not expect_json:
            return raw
        return self._extract_json(raw)

    @staticmethod
    def _extract_json(text):
        for open_ch, close_ch in (("{", "}"), ("[", "]")):
            start, end = text.find(open_ch), text.rfind(close_ch)
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except ValueError:
                    continue
        return None

    def _log(self, label, prompt, response):
        os.makedirs(self.log_dir, exist_ok=True)
        path = os.path.join(self.log_dir, f"{self.calls:03d}_{label}.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("=== PROMPT ===\n" + prompt + "\n\n=== RESPONSE ===\n"
                     + str(response) + "\n")
