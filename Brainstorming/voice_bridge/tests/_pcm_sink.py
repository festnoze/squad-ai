"""Stand-in for ffplay that keeps what it was fed.

No timing here on purpose: playback timing is covered by the deterministic
simulation in test_pocket_streaming.py, which is stable on a loaded machine
where a real-time consumer is not.

    python _pcm_sink.py <out.pcm>
"""

import sys

with open(sys.argv[1], "wb") as out:
    while True:
        block = sys.stdin.buffer.read(8192)
        if not block:
            break
        out.write(block)
