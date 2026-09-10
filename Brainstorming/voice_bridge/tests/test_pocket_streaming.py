"""The Pocket path must not let the speakers run dry on a long answer.

Pocket TTS is autoregressive, so one request gets slower per second of audio as
the text grows. Measured on this machine with the estelle voice:

    145 characters -> 1.11x real time
    291 characters -> 1.28x
    437 characters -> 2.35x

Played as a single request, a 454-character answer took 33.4 s of wall time for
22.7 s of audio: about ten seconds of silence inside the sentence. The fix is to
send short requests, which keeps the rate near 1.11x whatever the total length,
and to bank a little audio before starting so the player always stays ahead.

The playback timing is checked by simulation rather than by a real-time
consumer: a fake player holding 24 kHz on a loaded Windows box measures its own
scheduling noise as much as the code under test. The delivery of the bytes is
checked for real, against a fake daemon.

Run with:  uvx --with pytest --python 3.14 pytest tests -q
"""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import speak  # noqa: E402
from _pcm_daemon import pcm_for  # noqa: E402  - one source for the PCM pattern

LONG_TEXT = (
    "Le verrou de voix est maintenant en place dans le pont vocal, chaque terminal qui "
    "termine son tour attend que la voix soit libre avant de parler. Si l attente depasse "
    "trente secondes il renonce en silence plutot que d annoncer un resultat perime. Le "
    "demon a ete redemarre et il synthetise de nouveau plus vite que le temps reel. Cette "
    "phrase sert a verifier qu une lecture longue passe sans coupure du debut a la fin."
)

# --------------------------------------------------------------------------
# The measured behaviour of the real daemon, replayed by the simulation
# --------------------------------------------------------------------------

MEASURED_RTF = [(145, 1.11), (291, 1.28), (437, 2.35)]
# 437 characters produced 22.3 s of audio, 145 produced 7.8 s.
CHARS_PER_AUDIO_SECOND = 19.0
# The daemon streams as it generates, in pushes of about this much audio.
PUSH_SECONDS = 0.1
# Measured: the first sample of a request comes out about this late. It is part
# of the rates above, not extra, so the simulation takes it out of the first
# push rather than adding it on top.
REQUEST_LATENCY = 0.34


def measured_rtf(chars: int) -> float:
    """Interpolate the measured cost of one request of this length."""
    if chars <= MEASURED_RTF[0][0]:
        return MEASURED_RTF[0][1]
    for (low_n, low_r), (high_n, high_r) in zip(MEASURED_RTF, MEASURED_RTF[1:]):
        if chars <= high_n:
            share = (chars - low_n) / (high_n - low_n)
            return low_r + share * (high_r - low_r)
    # Past the longest measurement, keep the last slope rather than flattening.
    (prev_n, prev_r), (last_n, last_r) = MEASURED_RTF[-2:]
    slope = (last_r - prev_r) / (last_n - prev_n)
    return last_r + slope * (chars - last_n)


def simulate(chunks: list[str], start_at_first_sound: bool = False) -> dict:
    """Replay generation against playback and report any starvation.

    Calls the production decision, speak.should_start_playing, so this exercises
    the real strategy rather than a restatement of it.
    """
    total_chars = sum(len(chunk) for chunk in chunks)
    now = 0.0
    banked = 0.0  # seconds of audio generated so far
    chars_done = 0
    chunks_done = 0
    first_sound_at: float | None = None
    banked_at_first_sound = 0.0
    start: float | None = None
    starved = 0.0

    def consider() -> None:
        nonlocal start
        if start is not None:
            return
        if start_at_first_sound:
            if banked > 0:
                start = now
            return
        if first_sound_at is None:
            return
        progress = speak.Progress(
            banked=banked,
            streamed_audio=banked - banked_at_first_sound,
            streamed_seconds=now - first_sound_at,
            request_latency=first_sound_at,
            chars_done=chars_done,
            total_chars=total_chars,
            pending_requests=max(0, len(chunks) - chunks_done - 1),
        )
        if speak.should_start_playing(progress):
            start = now

    for chunk in chunks:
        audio = len(chunk) / CHARS_PER_AUDIO_SECOND
        generation = audio * measured_rtf(len(chunk))
        pushes = max(1, round(audio / PUSH_SECONDS))
        latency = min(REQUEST_LATENCY, generation / 2)
        now += latency  # the request is in flight, nothing to hear yet
        for _ in range(pushes):
            now += (generation - latency) / pushes
            banked += audio / pushes
            if first_sound_at is None:
                first_sound_at = now
                banked_at_first_sound = banked
            if start is not None:
                # Audio owed to the speakers by now, against what exists.
                starved = max(starved, (now - start) - banked)
            consider()
        chars_done += len(chunk)
        chunks_done += 1
        consider()

    assert start is not None, "playback never started"
    return {
        "start": start,
        "audio": banked,
        "generation": now,
        "starved": max(0.0, starved),
    }


# --------------------------------------------------------------------------
# The strategy
# --------------------------------------------------------------------------


def test_short_requests_and_prebuffer_remove_the_starvation() -> None:
    chunks = speak.chunk_text(LONG_TEXT, speak.POCKET_CHUNK_CHARS)
    assert simulate(chunks)["starved"] == 0.0, "the speakers ran dry"


def test_one_long_request_starves_the_speakers() -> None:
    """The bug being fixed, and the guard against a vacuous suite.

    This is the old behaviour: the whole answer in one request, played from the
    first sound. If it ever stops starving, the model of the daemon no longer
    reproduces the reported stutter and the test above proves nothing.
    """
    result = simulate([LONG_TEXT], start_at_first_sound=True)
    assert result["starved"] > 5.0, "the daemon model no longer reproduces the stutter"


def test_chunking_alone_is_not_enough() -> None:
    """Short requests still starve without the prebuffer, at 1.11x real time."""
    chunks = speak.chunk_text(LONG_TEXT, speak.POCKET_CHUNK_CHARS)
    result = simulate(chunks, start_at_first_sound=True)
    assert result["starved"] > 0.5, "the prebuffer is what closes the last gap"


def test_the_prebuffer_costs_little_on_a_normal_answer() -> None:
    """A spoken answer is capped at max_chars, so the delay must stay small."""
    text = LONG_TEXT[: speak.DEFAULTS["max_chars"]]
    result = simulate(speak.chunk_text(text, speak.POCKET_CHUNK_CHARS))
    assert result["starved"] == 0.0
    assert result["start"] < 3.0, "the answer takes too long to start"



def test_a_daemon_faster_than_real_time_starts_at_once() -> None:
    """Measured at 0.75x after the daemon restart: nothing to bank, so speak.

    Waiting for the first chunk to finish instead put the first word 6 s into a
    24-second answer, which is what this guards against.
    """
    fast = [(n, 0.75) for n, _ in MEASURED_RTF]
    chunks = speak.chunk_text(LONG_TEXT, speak.POCKET_CHUNK_CHARS)
    import unittest.mock as mock

    with mock.patch.dict(globals(), {"MEASURED_RTF": fast}):
        result = simulate(chunks)
    assert result["starved"] == 0.0
    # The floor is the measurement window: half a second of audio has to arrive
    # before any rate can be read off it.
    floor = REQUEST_LATENCY + speak.PREBUFFER_MARGIN_SECONDS + REQUEST_LATENCY
    assert result["start"] < floor + 1.0, "the first word came out late"


def test_chunks_stay_short_however_long_the_answer() -> None:
    long_answer = LONG_TEXT * 3
    chunks = speak.chunk_text(long_answer, speak.POCKET_CHUNK_CHARS)
    assert len(chunks) > 5, "the text was not split"
    assert max(len(chunk) for chunk in chunks) <= speak.POCKET_CHUNK_CHARS
    # Nothing is dropped at the seams.
    assert "".join(chunks).replace(" ", "") == long_answer.replace(" ", "")


# --------------------------------------------------------------------------
# The decision, exactly
# --------------------------------------------------------------------------


MARGIN = speak.PREBUFFER_MARGIN_SECONDS


def test_prebuffer_formula() -> None:
    # Faster than real time: only the fixed cushion, no deficit to cover.
    assert speak.required_prebuffer_seconds(0.8, 20) == pytest.approx(MARGIN)
    assert speak.required_prebuffer_seconds(1.0, 20) == pytest.approx(MARGIN)
    assert speak.required_prebuffer_seconds(1.3, 20) == pytest.approx(6.0 + MARGIN, abs=0.01)
    assert speak.required_prebuffer_seconds(2.0, 0) == pytest.approx(MARGIN)
    # Uncapped on purpose: a 3x daemon banks the whole answer rather than
    # starting early and stuttering through it.
    assert speak.required_prebuffer_seconds(3.0, 60) == pytest.approx(120.0 + MARGIN, abs=0.01)
    # Each request still to send is silent until its first sample, and one more
    # latency is held back as cushion.
    assert speak.required_prebuffer_seconds(
        1.0, 20, pending_requests=3, request_latency=0.5
    ) == pytest.approx(1.5 + MARGIN + 0.5, abs=0.01)
    # A generator fast enough absorbs those latencies, but still keeps the
    # cushion of one seam.
    assert speak.required_prebuffer_seconds(
        0.5, 20, pending_requests=3, request_latency=0.5
    ) == pytest.approx(MARGIN + 0.5, abs=0.01)


def decide(banked, rtf, chars_done=0, pending=3, latency=0.34, total=481) -> bool:
    """The decision, expressed as a banked amount and an observed rate."""
    return speak.should_start_playing(
        speak.Progress(
            banked=banked,
            streamed_audio=banked,
            streamed_seconds=banked * rtf,
            request_latency=latency,
            chars_done=chars_done,
            total_chars=total,
            pending_requests=pending,
        )
    )


def test_should_start_playing() -> None:
    assert not decide(banked=0.0, rtf=1.0), "not one sample yet"
    assert not decide(banked=0.1, rtf=1.0), "a rate needs more than one block"
    # Mid-first-chunk and running slow: the length of the answer comes from the
    # prior, and 1.4 s banked does not cover a 20% deficit over 24 s.
    assert not decide(banked=1.4, rtf=1.2)
    # Mid-first-chunk, generating faster than it plays: the surplus absorbs the
    # start-up latency of the three requests still to send, and one seam of
    # cushion is kept.
    assert decide(banked=2.0, rtf=0.8)
    assert not decide(banked=0.7, rtf=0.8), "no cushion for a seam"
    # Exactly real time: nothing absorbs those three latencies.
    assert not decide(banked=1.0, rtf=1.0), "three latencies are not covered"
    # One chunk of four in hand, so the answer is now sized from real data.
    assert decide(banked=2.2, rtf=1.05, chars_done=143, pending=2)
    # The same audio banked but far slower: not enough to outrun the rest.
    assert not decide(banked=1.4, rtf=2.0, chars_done=143, pending=2)
    # The last chunk is in hand: nothing left to generate or to request.
    assert decide(banked=1.4, rtf=2.0, chars_done=481, pending=0)


# --------------------------------------------------------------------------
# The delivery, for real
# --------------------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def pcm_daemon():
    started = []

    def start(fail_after: int | None = None) -> int:
        port = free_port()
        argv = [sys.executable, str(HERE / "_pcm_daemon.py"), str(port)]
        if fail_after is not None:
            argv += ["--fail-after", str(fail_after)]
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        started.append(proc)
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == b"ready"
        return port

    yield start
    for proc in started:
        proc.kill()
        proc.wait()


def run_pocket(text: str, port: int, tmp_path: Path, monkeypatch) -> bytes:
    """Speak `text` through the real Pocket path into a recording sink."""
    pcm = tmp_path / "out.pcm"
    monkeypatch.setattr(speak, "STATE_DIR", tmp_path)
    monkeypatch.setattr(speak, "PID_FILE", tmp_path / "player.pid")
    monkeypatch.setattr(speak, "SEQ_FILE", tmp_path / "sequencer.pid")
    monkeypatch.setattr(
        speak,
        "spawn_pcm_player",
        lambda rate: subprocess.Popen(
            [sys.executable, str(HERE / "_pcm_sink.py"), str(pcm)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
    )
    cfg = dict(speak.DEFAULTS)
    cfg["pocket_port"] = port
    speak.speak_pocket(text, cfg)
    return pcm.read_bytes()


def expected_pcm(chunks: list[str]) -> bytes:
    return b"".join(pcm_for(chunk) for chunk in chunks)


def test_every_chunk_reaches_the_player_in_order(pcm_daemon, tmp_path, monkeypatch) -> None:
    port = pcm_daemon()
    written = run_pocket(LONG_TEXT, port, tmp_path, monkeypatch)
    chunks = speak.chunk_text(LONG_TEXT, speak.POCKET_CHUNK_CHARS)
    assert len(chunks) > 1, "the answer was not split, so this proves nothing"
    assert written == expected_pcm(chunks)


def test_a_short_answer_is_one_request(pcm_daemon, tmp_path, monkeypatch) -> None:
    port = pcm_daemon()
    short = "Les tests passent, la voix est libre."
    written = run_pocket(short, port, tmp_path, monkeypatch)
    assert written == expected_pcm([short])


def test_a_failure_midway_plays_what_was_generated(pcm_daemon, tmp_path, monkeypatch) -> None:
    """A daemon that dies mid-answer must not swallow the part already made."""
    port = pcm_daemon(fail_after=1)
    with pytest.raises(Exception):
        run_pocket(LONG_TEXT, port, tmp_path, monkeypatch)
    written = (tmp_path / "out.pcm").read_bytes()
    first = speak.chunk_text(LONG_TEXT, speak.POCKET_CHUNK_CHARS)[0]
    assert written == expected_pcm([first]), "the first chunk was lost"


def test_daemon_down_is_reported(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(speak, "STATE_DIR", tmp_path)
    monkeypatch.setattr(speak, "SEQ_FILE", tmp_path / "sequencer.pid")
    cfg = dict(speak.DEFAULTS)
    cfg["pocket_port"] = free_port()  # nothing listening
    with pytest.raises(RuntimeError, match="injoignable"):
        speak.speak_pocket("Bonjour.", cfg)
