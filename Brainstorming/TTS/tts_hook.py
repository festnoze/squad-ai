"""
Claude Code Stop hook — reads the transcript and speaks the last assistant message.

Called by Claude Code via settings.local.json hooks config.
Receives JSON on stdin with transcript_path and stop_hook_active fields.
"""

import json
import os
import re
import subprocess
import sys

MAX_TEXT_LENGTH = 5000


def clean_markdown(text: str) -> str:
    """Strip markdown formatting to produce plain readable text."""
    # Remove fenced code blocks (``` ... ```)
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code (`...`)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    # Remove bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    # Remove markdown links [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove image syntax ![alt](url)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    # Remove heading markers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # Remove blockquote markers
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_last_assistant_text(transcript_path: str) -> str:
    """Read the transcript JSONL and return the last assistant text content."""
    last_text_parts: list[str] = []

    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") != "assistant":
                continue
            # Skip sidechain (subagent) entries
            if entry.get("isSidechain"):
                continue

            content = entry.get("message", {}).get("content", [])
            if not isinstance(content, list):
                continue

            # Collect text blocks from this assistant entry
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    t = block.get("text", "").strip()
                    if t:
                        texts.append(t)

            # Only update if this entry had text (skip tool_use-only entries)
            if texts:
                last_text_parts = texts

    return "\n".join(last_text_parts)


def main() -> None:
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    # Prevent infinite loops
    if hook_input.get("stop_hook_active", False):
        sys.exit(0)

    transcript_path = hook_input.get("transcript_path", "")
    if not transcript_path or not os.path.isfile(transcript_path):
        sys.exit(0)

    text = extract_last_assistant_text(transcript_path)
    if not text:
        sys.exit(0)

    text = clean_markdown(text)
    if not text:
        sys.exit(0)

    # Truncate to stay within Google TTS limits
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]

    # Resolve the streaming TTS script path relative to this file
    tts_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "text_to_speech_google_streaming.py")

    try:
        subprocess.run(
            [sys.executable, tts_script, text],
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass


if __name__ == "__main__":
    main()
