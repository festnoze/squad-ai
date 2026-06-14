"""BUG1 — the untrusted generated app must run with a UTF-8 stdio so a main.py
that prints non-ASCII neither crashes (Windows cp1252 UnicodeEncodeError) nor
produces mojibake (cp1252 bytes mis-read as utf-8)."""

import subprocess
import sys

from autospec.orchestrator import pipeline


def test_minimal_env_forces_utf8():
    env = pipeline._minimal_env()
    assert env.get("PYTHONUTF8") == "1"
    assert env.get("PYTHONIOENCODING") == "utf-8"


def test_child_prints_non_ascii_without_crash_or_mojibake():
    env = pipeline._minimal_env()
    # A child printing accents + an arrow + a ligature exercises cp1252.
    proc = subprocess.run(
        [sys.executable, "-c", "print('café → œuf')"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stdout
    assert "café → œuf" in proc.stdout
