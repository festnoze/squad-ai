"""Helper run as a separate process by test_voice_lock.py.

Takes the voice lock, holds it for a while, and appends `start end acquired`
to a log so the test can check that holders never overlapped.

    python _lock_holder.py <lock> <stamp> <hold_s> <timeout_s> <log> <name>
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import speak  # noqa: E402

lock_path, stamp_path, hold, timeout, log = sys.argv[1:6]
speak.STOP_STAMP = Path(stamp_path)

lock = speak.VoiceLock(Path(lock_path))
# Tell the test we are about to queue: Python startup alone can take longer
# than the delays the test would otherwise have to guess.
Path(log + f".ready.{sys.argv[6]}").touch()
acquired = lock.acquire(float(timeout))
start = time.time()
if acquired:
    time.sleep(float(hold))
    lock.release()
end = time.time()
with open(log, "a", encoding="utf-8") as fh:
    fh.write(f"{start:.3f} {end:.3f} {int(acquired)}\n")
