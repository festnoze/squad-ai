"""Speak a Claude Code / Codex answer out loud, in French.

Reads text from --text, a file, or stdin. Strips markdown, extracts the part
worth hearing, synthesizes it with the selected backend and plays it.

Backends:
    piper  - fully local (ONNX, CPU). Free, private, RTF ~0.1. Default.
    edge   - Microsoft Edge neural voices. Free, no API key, best French prosody.
    sapi   - Windows built-in voices. Zero install, instant, robotic.

Usage:
    echo "Bonjour" | python speak.py
    python speak.py --text "Les tests passent." --backend edge
    python speak.py --stop            # cut whatever is currently playing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "voice_bridge"
PID_FILE = STATE_DIR / "player.pid"
SEQ_FILE = STATE_DIR / "sequencer.pid"
CONFIG_FILE = ROOT / "config.json"

# Above this, a single utterance makes you wait too long for the first sound,
# so long text is cut into chunks played back to back.
CHUNK_CHARS = 320

DEFAULTS = {
    "backend": "piper",
    "piper_voice": "fr_FR-siwis-medium",
    "piper_port": 5111,
    "edge_voice": "fr-FR-DeniseNeural",
    "edge_rate": "+15%",
    "sapi_voice": "Microsoft Julie",
    "max_chars": 260,
    "enabled": True,
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
MD_HEADING = re.compile(r"^#{1,6}\s*", re.MULTILINE)
MD_BULLET = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+", re.MULTILINE)
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


def pick_spoken_part(text: str, max_chars: int) -> str:
    """Choose what actually gets read aloud.

    A full Claude Code answer is unlistenable. Priority:
    1. an explicit <voix> block written by the model,
    2. otherwise the closing paragraph, which is where the conclusion lives,
    3. truncated on a sentence boundary.
    """
    tagged = VOICE_TAG.search(text)
    if tagged:
        return clean_markdown(tagged.group(1))

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


def stop_playing(keep_sequencer: bool = False) -> None:
    """Kill the current utterance. Makes barge-in possible.

    The sequencer goes first: killing only the player would let it queue the
    next chunk immediately, so the speech would not actually stop.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not keep_sequencer:
        kill_recorded(SEQ_FILE)
    kill_recorded(PID_FILE)


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


def play(path: Path, keep_sequencer: bool = False, wait: bool = False) -> None:
    stop_playing(keep_sequencer=keep_sequencer)
    sweep_old_clips()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [find_tool("ffplay"), "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    if wait:
        proc.wait()


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------


def synth_piper_daemon(text: str, cfg: dict) -> Path | None:
    """Ask the resident daemon, which answers in ~0.5 s. None if it is down."""
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{cfg['piper_port']}/"
    request = urllib.request.Request(url, data=text.encode("utf-8"), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            audio = response.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None
    out = Path(tempfile.mkstemp(suffix=".wav", prefix="vb_")[1])
    out.write_bytes(audio)
    return out


def synth_piper(text: str, cfg: dict) -> Path:
    from_daemon = synth_piper_daemon(text, cfg)
    if from_daemon is not None:
        return from_daemon

    # Fallback: the CLI reloads the 63 MB model every time, so it costs ~6 s.
    # Fine as a safety net, not as the normal path - keep the daemon alive.
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
    stop_playing()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert proc.stdin is not None
    # Close stdin without waiting: communicate() would block until the whole
    # sentence has been spoken, and --stop needs the pid to stay killable.
    proc.stdin.write(text.encode("utf-8"))
    proc.stdin.close()
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")


BACKENDS = {"piper": synth_piper, "edge": synth_edge}


def speak(text: str, cfg: dict) -> None:
    backend = cfg["backend"]
    if backend == "sapi":
        speak_sapi(text, cfg)
        return
    if backend not in BACKENDS:
        raise ValueError(f"Backend inconnu: {backend}")
    play(BACKENDS[backend](text, cfg))


# --------------------------------------------------------------------------
# Long-form reading, for models that have no Stop hook to summarize for us
# --------------------------------------------------------------------------


SENTENCE_END = re.compile(r"(?<=[.!?:])\s+")


def chunk_text(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """Split on sentence boundaries into pieces small enough that the first
    one starts playing quickly, and long enough not to sound chopped."""
    chunks: list[str] = []
    current = ""
    for sentence in SENTENCE_END.split(text.replace("\n", " ")):
        sentence = sentence.strip()
        if not sentence:
            continue
        if current and len(current) + len(sentence) + 1 > limit:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def speak_sequence(text: str, cfg: dict) -> None:
    """Read a whole answer, chunk by chunk, without cutting itself off.

    Runs in its own process so `--stop` can kill the queue and not just the
    chunk currently in the speakers.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    stop_playing()
    SEQ_FILE.write_text(str(os.getpid()), encoding="utf-8")
    try:
        backend = cfg["backend"]
        if backend == "sapi":
            speak_sapi(text, cfg)
            return
        for chunk in chunk_text(text):
            play(BACKENDS[backend](chunk, cfg), keep_sequencer=True, wait=True)
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
    parser.add_argument("--backend", choices=["piper", "edge", "sapi"])
    parser.add_argument("--voice", help="Override the backend voice.")
    parser.add_argument("--max-chars", type=int)
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

    if args.sequence:
        speak_sequence(spoken, cfg)
    elif args.tee:
        # --raw matters: without it the sequencer would run the extraction
        # again and read only the closing paragraph of what we handed it.
        spawn_sequencer(spoken, ["--raw", "--backend", cfg["backend"]])
    else:
        speak(spoken, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
