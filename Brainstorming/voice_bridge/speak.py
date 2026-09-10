"""Speak a Claude Code / Codex answer out loud, in French.

Reads text from --text, a file, or stdin. Strips markdown, extracts the part
worth hearing, synthesizes it with the selected backend and plays it.

Backends:
    pocket - fully local (Kyutai Pocket TTS, 24 kHz). Best French, RTF ~0.8.
    piper  - fully local (ONNX, CPU). Fastest, RTF ~0.1, but robotic French.
    edge   - Microsoft Edge neural voices. Free, no API key, best French prosody.
    sapi   - Windows built-in voices. Zero install, instant, robotic.

Only one process may use the speakers at a time. Several terminals finishing
at once each spawn their own speak.py; the later ones wait for the voice to be
free (up to `queue_wait_seconds`) and then take their turn, or give up quietly
when the wait would make their announcement stale. See VoiceLock.

Usage:
    echo "Bonjour" | python speak.py
    python speak.py --text "Les tests passent." --backend edge
    python speak.py --stop            # cut whatever is currently playing
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import IO, NamedTuple

ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "voice_bridge"
PID_FILE = STATE_DIR / "player.pid"
SEQ_FILE = STATE_DIR / "sequencer.pid"
LOCK_FILE = STATE_DIR / "voice.lock"
STOP_STAMP = STATE_DIR / "stop.stamp"
CONFIG_FILE = ROOT / "config.json"

# How often a waiting reader re-tries the voice lock.
LOCK_POLL_SECONDS = 0.2

# Above this, a single utterance makes you wait too long for the first sound,
# so long text is cut into chunks played back to back.
CHUNK_CHARS = 320

# Pocket TTS is autoregressive: the cost per second of audio climbs with the
# length of the request. Measured on this machine, one request goes from 1.1x
# real time at 145 characters to 2.35x at 437, and the speakers run dry in the
# middle of the sentence. Short requests keep the rate near 1.1x whatever the
# total length of the answer.
POCKET_CHUNK_CHARS = 150

# Cushion on top of the computed need, for a CPU spike mid-answer.
PREBUFFER_MARGIN_SECONDS = 0.6

# Prior for how much text one second of speech holds, measured on the estelle
# voice (437 characters gave 22.3 s, 145 gave 7.8 s). Only used before the first
# chunk has been generated, to size the answer still to come; after that the
# real ratio is known and this is not consulted again.
CHARS_PER_AUDIO_SECOND = 19.0

# The generation rate cannot be measured from the first block alone: at that
# instant no time has passed since the first sample, so any daemon looks
# infinitely fast and playback starts on a sample of one. Wait for this much
# audio before trusting the rate. A shorter answer than this plays anyway, once
# the feed closes.
MIN_RATE_SAMPLE_SECONDS = 0.5

# 16-bit mono PCM.
PCM_BYTES_PER_SAMPLE = 2

DEFAULTS = {
    "backend": "piper",
    "piper_voice": "fr_FR-siwis-medium",
    "piper_port": 5111,
    "pocket_voice": "estelle",
    "pocket_port": 5112,
    "pocket_chunk_chars": POCKET_CHUNK_CHARS,
    "edge_voice": "fr-FR-DeniseNeural",
    "edge_rate": "+15%",
    "sapi_voice": "Microsoft Julie",
    "max_chars": 260,
    "enabled": True,
    # How long a reader waits for the speakers when another one is talking.
    # 0 means: give up at once if the voice is busy.
    "queue_wait_seconds": 30,
}


def find_tool(name: str) -> str:
    """Locate a uv-installed CLI: hooks run with a minimal PATH that often
    misses ~/.local/bin, where `uv tool install` drops its shims."""
    found = shutil.which(name)
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / f"{name}.exe"
    if candidate.exists():
        return str(candidate)
    raise FileNotFoundError(
        f"{name} introuvable. Installe-le avec: uv tool install {name}"
    )


def read_stdin_text() -> str:
    """Decode stdin as UTF-8 whatever the console codepage says.

    Python picks the ANSI codepage (cp1252 here) for stdin on Windows, so a
    piped UTF-8 answer comes back as mojibake and, once re-encoded, doubles up:
    "a grave" turns into two characters. Reading the raw buffer avoids it.
    """
    raw = sys.stdin.buffer.read()
    for encoding in ("utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


# --------------------------------------------------------------------------
# Text preparation
# --------------------------------------------------------------------------

# An explicit <voix>...</voix> block always wins: it lets the model write the
# spoken line itself instead of us guessing which sentences matter.
VOICE_TAG = re.compile(r"<voix>(.*?)</voix>", re.DOTALL | re.IGNORECASE)

FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE = re.compile(r"`([^`]*)`")
MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
MD_EMPHASIS = re.compile(r"(\*\*|__|\*|_)")
# Spaces and tabs only, never \s: with re.MULTILINE, `^\s*` also matches the
# blank line that separates two paragraphs, so cleaning a bulleted answer used
# to swallow one of the two newlines. Paragraphs then merged into a single
# block, and picking the closing paragraph read out the opening instead.
MD_HEADING = re.compile(r"^#{1,6}[ \t]*", re.MULTILINE)
MD_BULLET = re.compile(r"^[ \t]*(?:[-*+]|\d+\.)[ \t]+", re.MULTILINE)
HTML_TAG = re.compile(r"<[^>]+>")
PATHY = re.compile(r"(?:[A-Za-z]:)?[\\/][\w.\-\\/]{6,}")
MULTI_NL = re.compile(r"\n{3,}")


def clean_markdown(text: str) -> str:
    text = FENCED_CODE.sub(" (bloc de code) ", text)
    text = MD_LINK.sub(r"\1", text)
    text = INLINE_CODE.sub(r"\1", text)
    text = MD_HEADING.sub("", text)
    text = MD_BULLET.sub("", text)
    text = MD_EMPHASIS.sub("", text)
    text = HTML_TAG.sub("", text)
    text = PATHY.sub(" ce fichier ", text)
    text = MULTI_NL.sub("\n\n", text)
    return text.strip()


SENTENCE_START = re.compile(r"[.!?]\s+(\S)")


def tail_on_sentence_boundary(text: str, max_chars: int) -> str:
    """The end of the text, starting on a sentence rather than mid-word."""
    if len(text) <= max_chars:
        return text
    tail = text[-max_chars:]
    match = SENTENCE_START.search(tail)
    return tail[match.start(1) :] if match else tail.lstrip()


def pick_spoken_part(text: str, max_chars: int) -> str:
    """Choose what actually gets read aloud.

    A full Claude Code answer is unlistenable. Priority:
    1. an explicit <voix> block written by the model,
    2. otherwise the closing paragraph, which is where the conclusion lives,
    3. truncated on a sentence boundary.
    """
    tagged = VOICE_TAG.search(text)
    if tagged:
        line = clean_markdown(tagged.group(1))
        if line:
            return line
        # An empty tag must not silence the answer: fall through to the body.

    body = clean_markdown(VOICE_TAG.sub("", text))
    if not body:
        return ""
    if len(body) <= max_chars:
        return body

    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    for para in reversed(paragraphs):
        if len(para) >= 40:
            body = para
            break
    else:
        # Not one substantial paragraph, so there is no conclusion to single
        # out. Keep the end of the answer anyway: cutting from the top would
        # read out the opening, which is the part the reader already saw.
        return tail_on_sentence_boundary(body, max_chars)

    if len(body) <= max_chars:
        return body

    cut = body[:max_chars]
    boundary = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: boundary + 1] if boundary > max_chars // 3 else cut.rstrip() + "..."


# --------------------------------------------------------------------------
# Playback control
# --------------------------------------------------------------------------


def kill_recorded(pid_file: Path) -> None:
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        pid_file.unlink(missing_ok=True)
        return
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        check=False,
    )
    pid_file.unlink(missing_ok=True)


def stop_playing() -> None:
    """Kill the current utterance. Makes barge-in possible.

    The sequencer goes first: killing only the player would let it queue the
    next chunk immediately, so the speech would not actually stop.

    The stamp tells readers queued behind the lock to give up too: someone who
    asks for silence does not want the next announcement to start instead.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STOP_STAMP.touch()
    kill_recorded(SEQ_FILE)
    kill_recorded(PID_FILE)


def stop_requested_since(moment: float) -> bool:
    try:
        return STOP_STAMP.stat().st_mtime > moment
    except OSError:
        return False


def _lock_exclusive_nonblocking(fd: int) -> bool:
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fd: int) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


class VoiceLock:
    """Exclusive, cross-process right to use the speakers.

    Every terminal that finishes a turn spawns its own speak.py, and before this
    lock existed each one killed whatever the previous one was saying. The lock
    is an OS file lock rather than a marker file: the kernel drops it the moment
    the holder dies, even under `taskkill /F`, so a crash can never leave the
    voice locked for good.

    Hold it for the whole playback, not just the launch of the player.
    """

    def __init__(self, path: Path = LOCK_FILE) -> None:
        self._path = path
        self._fh: IO[bytes] | None = None

    def acquire(self, timeout: float) -> bool:
        """Wait up to `timeout` seconds for the voice. False means: stay silent.

        A `--stop` issued while we wait also returns False, so that cutting the
        voice does not simply hand it to the next reader in line.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        queued_at = time.time()
        deadline = time.monotonic() + max(0.0, timeout)
        self._fh = open(self._path, "a+b")
        if self._fh.tell() == 0:
            # Windows locks a byte range, so the file needs at least one byte.
            self._fh.write(b"\0")
            self._fh.flush()
        while True:
            self._fh.seek(0)
            if _lock_exclusive_nonblocking(self._fh.fileno()):
                return True
            if stop_requested_since(queued_at) or time.monotonic() >= deadline:
                self.release()
                return False
            time.sleep(LOCK_POLL_SECONDS)

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            self._fh.seek(0)
            _unlock(self._fh.fileno())
        finally:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "VoiceLock":
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


def sweep_old_clips(keep_seconds: int = 3600) -> None:
    """Drop stale clips. We cannot delete the one being played (ffplay still
    holds it), so each run cleans up after the previous ones instead."""
    cutoff = time.time() - keep_seconds
    for clip in Path(tempfile.gettempdir()).glob("vb_*"):
        try:
            if clip.stat().st_mtime < cutoff:
                clip.unlink()
        except OSError:
            pass  # still open, or already gone


def play(path: Path) -> None:
    """Play a clip and wait for it to finish.

    Waiting is what makes the voice lock mean something: the lock lives in this
    process, so it must stay alive as long as the speakers are in use.
    """
    sweep_old_clips()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [find_tool("ffplay"), "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    proc.wait()


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------


def synth_piper_daemon(text: str, cfg: dict) -> Path | None:
    """Ask the resident daemon, which answers in ~0.5 s. None if it is down."""
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{cfg['piper_port']}/"
    request = urllib.request.Request(
        url,
        data=text.encode("utf-8"),
        method="POST",
        # The daemon answers 409 if it holds a different voice, which sends us
        # to the CLI instead of quietly speaking in the wrong one.
        headers={"X-Voice": cfg["piper_voice"]},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            audio = response.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None
    out = Path(tempfile.mkstemp(suffix=".wav", prefix="vb_")[1])
    out.write_bytes(audio)
    return out


def start_daemon_detached(cfg: dict) -> None:
    """Bring the daemon back after a reboot, without making anyone wait for it.

    The toggle survives restarts but the resident process does not, so the first
    answer after booting would otherwise fall back to the slow CLI forever.
    """
    server = ROOT / "piper_server.py"
    python = Path(os.environ.get("APPDATA", "")) / "uv/tools/piper-tts/Scripts/python.exe"
    if not python.exists() or not server.exists():
        return
    try:
        subprocess.Popen(
            [
                str(python), str(server),
                "--port", str(cfg["piper_port"]),
                # Without this the daemon would come back holding the default
                # voice and 409 every request, pinning us to the slow CLI.
                "--model", str(ROOT / "voices" / f"{cfg['piper_voice']}.onnx"),
            ],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )
    except OSError:
        pass  # the CLI fallback below still speaks


def synth_piper(text: str, cfg: dict) -> Path:
    from_daemon = synth_piper_daemon(text, cfg)
    if from_daemon is not None:
        return from_daemon

    # The daemon is down: relaunch it for next time, and serve this one from
    # the CLI, which reloads the 63 MB model and so costs ~6 s.
    start_daemon_detached(cfg)
    model = ROOT / "voices" / f"{cfg['piper_voice']}.onnx"
    if not model.exists():
        raise FileNotFoundError(
            f"Voix Piper absente: {model}. Lance install.ps1 ou choisis --backend edge."
        )
    out = Path(tempfile.mkstemp(suffix=".wav", prefix="vb_")[1])
    subprocess.run(
        [find_tool("piper"), "-m", str(model), "-f", str(out)],
        input=text.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    return out


def required_prebuffer_seconds(
    rtf: float,
    remaining_audio: float,
    pending_requests: int = 0,
    request_latency: float = 0.0,
) -> float:
    """Seconds of audio to bank before starting, so the speakers never run dry.

    Once playback starts with B seconds banked and R seconds still to generate,
    the audio lasts B + R while generation needs rtf * R, plus one latency per
    request still to be sent, since each one is silent until its first sample.
    Silence appears unless B + R >= rtf * R + latencies, which gives the deficit
    below. Generating faster than real time usually needs nothing banked.

    Deliberately uncapped. Capping it would only trade a late start for gaps
    mid-sentence, and buy nothing: the answer cannot finish before generation
    does either way, so stuttering costs the same wall time and sounds worse.
    A very slow daemon therefore ends up generating the whole answer first,
    which is what `wait_for_prebuffer` does when the feed closes.
    """
    deficit = (rtf - 1.0) * max(0.0, remaining_audio) + pending_requests * request_latency
    # One measured latency of cushion on top, always. The rate is read early,
    # on the calm part of the run, and it does get worse once the player is
    # competing for the CPU; one seam is what an optimistic estimate costs
    # before the ear notices. Measured seams here run at 0.48 s.
    return max(0.0, deficit) + PREBUFFER_MARGIN_SECONDS + request_latency


class Progress(NamedTuple):
    """What has been observed of the generation so far.

    Kept separate from the clock and the sockets so the decision below is a
    pure function of the observations, and the whole strategy can be replayed
    in the tests against measured daemon behaviour.
    """

    banked: float  # seconds of audio generated, all of it still unplayed
    streamed_audio: float  # of that, how much arrived after the first block
    streamed_seconds: float  # wall time spent receiving `streamed_audio`
    request_latency: float  # from sending a request to its first block
    chars_done: int  # characters whose audio is fully in hand
    total_chars: int  # characters in the whole answer
    pending_requests: int  # requests not yet sent, each paying the latency again


class PcmFeed:
    """PCM generated by a background thread, drained by the caller.

    Splitting the answer into short requests is what keeps generation near real
    time, and one shared player is what keeps the sentences seamless. This is
    the buffer between the two.
    """

    def __init__(self) -> None:
        self.cond = threading.Condition()
        self.blocks: collections.deque[bytes] = collections.deque()
        self.rate = 0
        self.bytes_generated = 0
        self.chars_done = 0
        self.chunks_done = 0
        # When the very first block arrived, as a monotonic reading, and how
        # much audio existed then. The gap between the request and that moment
        # is the daemon's start-up latency, which every later request pays
        # again; the rate is measured only on what came after it.
        self.first_sound_at: float | None = None
        self.bytes_at_first_sound = 0
        self.done = False
        self.error: Exception | None = None

    def push(self, rate: int, block: bytes) -> None:
        with self.cond:
            self.rate = self.rate or rate
            self.blocks.append(block)
            self.bytes_generated += len(block)
            if self.first_sound_at is None:
                self.first_sound_at = time.monotonic()
                self.bytes_at_first_sound = self.bytes_generated
            self.cond.notify_all()

    def progress(self, started: float, total_chars: int, total_chunks: int) -> Progress | None:
        """Observations for the start decision. None until the first block."""
        if not self.rate or self.first_sound_at is None:
            return None
        per_second = self.rate * PCM_BYTES_PER_SAMPLE
        return Progress(
            banked=self.bytes_generated / per_second,
            streamed_audio=(self.bytes_generated - self.bytes_at_first_sound) / per_second,
            streamed_seconds=time.monotonic() - self.first_sound_at,
            request_latency=self.first_sound_at - started,
            chars_done=self.chars_done,
            total_chars=total_chars,
            # The chunk being generated is already paying its own latency.
            pending_requests=max(0, total_chunks - self.chunks_done - 1),
        )

    def finish_chunk(self, chars: int) -> None:
        with self.cond:
            self.chars_done += chars
            self.chunks_done += 1
            self.cond.notify_all()

    def close(self, error: Exception | None = None) -> None:
        with self.cond:
            self.error = error
            self.done = True
            self.cond.notify_all()


def stream_pocket_chunk(text: str, cfg: dict, feed: PcmFeed) -> None:
    """POST one chunk and push its PCM into the feed as it arrives."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        f"http://127.0.0.1:{cfg['pocket_port']}/stream",
        data=text.encode("utf-8"),
        method="POST",
        headers={"X-Voice": cfg["pocket_voice"]},
    )
    try:
        response = urllib.request.urlopen(request, timeout=120)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise RuntimeError(
            f"demon pocket injoignable sur le port {cfg['pocket_port']}."
            " Lance: .\\voice.ps1 start"
        ) from exc

    rate = int(response.headers.get("X-Sample-Rate") or 24000)
    while True:
        block = response.read(8192)
        if not block:
            return
        feed.push(rate, block)


def spawn_pcm_player(rate: int) -> subprocess.Popen:
    """A player that reads raw PCM on stdin. Replaced wholesale by the tests."""
    return subprocess.Popen(
        [
            find_tool("ffplay"),
            "-f", "s16le", "-ar", str(rate), "-ac", "1",
            "-nodisp", "-autoexit", "-loglevel", "quiet", "-i", "-",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def estimate_total_audio(progress: Progress) -> float:
    """How many seconds the whole answer will last, best guess so far.

    Once a chunk is done, its own characters-to-audio ratio is known and used.
    Before that the prior stands in, so the decision below can be taken during
    the very first chunk instead of after it: waiting for chunk one to finish
    put the first word 6 s into a measured 24-second answer.
    """
    if progress.chars_done > 0:
        return progress.banked * progress.total_chars / progress.chars_done
    return progress.total_chars / CHARS_PER_AUDIO_SECOND


def should_start_playing(progress: Progress) -> bool:
    """Is enough audio banked to start playing and never run dry?

    No speed is assumed. The rate is the one observed, over the window that
    starts at the first block: measuring from the request instead would blame
    the generator for the daemon's start-up latency, and crediting the first
    block with no elapsed time at all would flatter it by a fifth. That latency
    is charged separately, once per request still to be sent.
    """
    if progress.streamed_audio < MIN_RATE_SAMPLE_SECONDS:
        return False  # too little audio to measure a rate on
    remaining = max(0.0, estimate_total_audio(progress) - progress.banked)
    return progress.banked >= required_prebuffer_seconds(
        rtf=progress.streamed_seconds / progress.streamed_audio,
        remaining_audio=remaining,
        pending_requests=progress.pending_requests,
        request_latency=progress.request_latency,
    )


def wait_for_prebuffer(feed: PcmFeed, total_chars: int, total_chunks: int) -> None:
    """Hold the first sound back just long enough to outrun the generator.

    A short answer starts almost immediately; a long one banks a few seconds
    rather than stuttering halfway through.
    """
    started = time.monotonic()
    with feed.cond:
        while True:
            if feed.error is not None:
                raise feed.error
            if feed.done:
                return  # everything is generated; nothing left to outrun
            progress = feed.progress(started, total_chars, total_chunks)
            if progress is not None and should_start_playing(progress):
                return
            feed.cond.wait(0.05)


def speak_pocket(text: str, cfg: dict) -> None:
    """Kyutai Pocket TTS: 24 kHz, far more natural in French than Piper.

    Generation runs close to real time on short requests and well below it on
    long ones, so the text goes out sentence by sentence while a single player
    consumes the PCM. This process stays alive while it pumps, and records its
    pid so --stop can cut it.
    """
    chunks = chunk_text(text, cfg.get("pocket_chunk_chars", POCKET_CHUNK_CHARS))
    if not chunks:
        return
    total_chars = sum(len(chunk) for chunk in chunks)

    feed = PcmFeed()

    def produce() -> None:
        try:
            for chunk in chunks:
                stream_pocket_chunk(chunk, cfg, feed)
                feed.finish_chunk(len(chunk))
        except Exception as exc:  # noqa: BLE001 - reported to the consumer
            feed.close(exc)
        else:
            feed.close()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SEQ_FILE.write_text(str(os.getpid()), encoding="utf-8")
    producer = threading.Thread(target=produce, daemon=True)
    producer.start()
    try:
        wait_for_prebuffer(feed, total_chars, len(chunks))
        player = spawn_pcm_player(feed.rate or 24000)
        assert player.stdin is not None
        PID_FILE.write_text(str(player.pid), encoding="utf-8")
        try:
            while True:
                with feed.cond:
                    while not feed.blocks and not feed.done:
                        feed.cond.wait(0.1)
                    block = feed.blocks.popleft() if feed.blocks else None
                    drained = not feed.blocks
                    # Only surface a failure once the queue is empty, so the
                    # audio generated before it still reaches the speakers.
                    error = feed.error if drained else None
                    finished = feed.done and drained
                if block:
                    # Blocks once the player's pipe is full, which is exactly
                    # the back-pressure that keeps memory flat.
                    player.stdin.write(block)
                if error is not None:
                    player.stdin.close()
                    player.wait()
                    raise error
                if block is None and finished:
                    break
            player.stdin.close()
            player.wait()
        except (BrokenPipeError, OSError):
            pass  # --stop killed the player mid-sentence
    finally:
        SEQ_FILE.unlink(missing_ok=True)


def synth_edge(text: str, cfg: dict) -> Path:
    out = Path(tempfile.mkstemp(suffix=".mp3", prefix="vb_")[1])
    subprocess.run(
        [
            find_tool("edge-tts"),
            "--voice", cfg["edge_voice"],
            "--rate", cfg["edge_rate"],
            "--text", text,
            "--write-media", str(out),
        ],
        capture_output=True,
        check=True,
    )
    return out


def speak_sapi(text: str, cfg: dict) -> None:
    """SAPI plays through its own synthesizer, so it bypasses the ffplay path."""
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"try {{ $s.SelectVoice('{cfg['sapi_voice']}') }} catch {{}};"
        "$s.Rate = 2;"
        "$s.Speak([Console]::In.ReadToEnd())"
    )
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert proc.stdin is not None
    # Record the pid before waiting so --stop can still cut the sentence.
    proc.stdin.write(text.encode("utf-8"))
    proc.stdin.close()
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    proc.wait()


BACKENDS = {"piper": synth_piper, "edge": synth_edge}


def speak(text: str, cfg: dict) -> None:
    backend = cfg["backend"]
    if backend == "sapi":
        speak_sapi(text, cfg)
        return
    if backend == "pocket":
        speak_pocket(text, cfg)
        return
    if backend not in BACKENDS:
        raise ValueError(f"Backend inconnu: {backend}")
    play(BACKENDS[backend](text, cfg))


# --------------------------------------------------------------------------
# Long-form reading, for models that have no Stop hook to summarize for us
# --------------------------------------------------------------------------


SENTENCE_END = re.compile(r"(?<=[.!?:])\s+")


def split_long_sentence(sentence: str, limit: int) -> list[str]:
    """Break a sentence with no usable punctuation on word boundaries.

    Sentence splitting alone leaves pieces over the limit whenever the text has
    no full stop for a while, and an over-long request is exactly what makes the
    Pocket daemon slow. A seam between words is barely audible; a stutter is not.
    """
    words = sentence.split()
    pieces: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + len(word) + 1 > limit:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_text(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """Split on sentence boundaries into pieces small enough that the first
    one starts playing quickly, and long enough not to sound chopped."""
    chunks: list[str] = []
    current = ""
    for sentence in SENTENCE_END.split(text.replace("\n", " ")):
        sentence = sentence.strip()
        if not sentence:
            continue
        for piece in split_long_sentence(sentence, limit):
            if current and len(current) + len(piece) + 1 > limit:
                chunks.append(current)
                current = piece
            else:
                current = f"{current} {piece}".strip()
    if current:
        chunks.append(current)
    return chunks


def speak_sequence(text: str, cfg: dict) -> None:
    """Read a whole answer, chunk by chunk, without cutting itself off.

    Runs in its own process so `--stop` can kill the queue and not just the
    chunk currently in the speakers.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SEQ_FILE.write_text(str(os.getpid()), encoding="utf-8")
    try:
        backend = cfg["backend"]
        if backend == "sapi":
            speak_sapi(text, cfg)
            return
        if backend == "pocket":
            # Pocket streams and handles arbitrarily long text on its own,
            # so cutting it into chunks would only add seams.
            speak_pocket(text, cfg)
            return
        for chunk in chunk_text(text):
            play(BACKENDS[backend](chunk, cfg))
    finally:
        SEQ_FILE.unlink(missing_ok=True)


def spawn_sequencer(text: str, extra: list[str]) -> None:
    """Hand the text to a detached reader so the pipeline gets its prompt back."""
    handle, path = tempfile.mkstemp(suffix=".txt", prefix="vbtext_")
    with os.fdopen(handle, "w", encoding="utf-8") as fh:
        fh.write(text)
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--file", path, "--sequence", *extra],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
    )


# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", help="Text to speak. Defaults to stdin.")
    parser.add_argument("--file", type=Path, help="Read the text from this file.")
    parser.add_argument("--backend", choices=["piper", "pocket", "edge", "sapi"])
    parser.add_argument("--voice", help="Override the backend voice.")
    parser.add_argument("--max-chars", type=int)
    parser.add_argument(
        "--queue-wait",
        type=float,
        metavar="SECONDS",
        help="How long to wait if another reader holds the voice (0: give up at once).",
    )
    parser.add_argument("--raw", action="store_true", help="Skip extraction, speak it all.")
    parser.add_argument("--stop", action="store_true", help="Cut the current playback.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be spoken.")
    parser.add_argument(
        "--tee",
        action="store_true",
        help="Echo stdin to stdout, then read it aloud. For piping any CLI into it.",
    )
    parser.add_argument(
        "--sequence",
        action="store_true",
        help="Read long text chunk by chunk in this process (used by --tee).",
    )
    args = parser.parse_args()

    if args.stop:
        stop_playing()
        return 0

    cfg = load_config()
    if args.backend:
        cfg["backend"] = args.backend
    if args.max_chars:
        cfg["max_chars"] = args.max_chars
    if args.queue_wait is not None:
        cfg["queue_wait_seconds"] = args.queue_wait
    if args.voice:
        cfg[f"{cfg['backend']}_voice"] = args.voice

    if args.text is not None:
        source = args.text
    elif args.file:
        source = args.file.read_text(encoding="utf-8")
    else:
        source = read_stdin_text()

    if args.tee:
        # Pass the output through untouched first: the pipeline's job comes
        # before ours, and a filter that swallows its input is a broken filter.
        sys.stdout.buffer.write(source.encode("utf-8", "replace"))
        sys.stdout.buffer.flush()

    # Piped output has no <voix> tag and no agent to write one, so read it all.
    speak_everything = args.raw or args.tee
    spoken = source.strip() if speak_everything else pick_spoken_part(source, cfg["max_chars"])
    if not spoken:
        return 0

    if args.dry_run:
        # Write bytes: the Windows console is cp1252 and would mangle accents.
        sys.stdout.buffer.write(spoken.encode("utf-8", "replace") + b"\n")
        sys.stdout.buffer.flush()
        return 0

    spoken = clean_markdown(spoken) if speak_everything else spoken

    if args.tee:
        # --raw matters: without it the sequencer would run the extraction
        # again and read only the closing paragraph of what we handed it.
        # The detached child takes the voice lock itself.
        spawn_sequencer(spoken, ["--raw", "--backend", cfg["backend"]])
        return 0

    lock = VoiceLock()
    if not lock.acquire(float(cfg["queue_wait_seconds"])):
        # Someone else kept the speakers for the whole wait, or the user asked
        # for silence meanwhile: an announcement this late would only confuse.
        return 0
    try:
        if args.sequence:
            speak_sequence(spoken, cfg)
        else:
            speak(spoken, cfg)
    finally:
        lock.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
