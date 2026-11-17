#!/usr/bin/env bash
# Scratch: applies one GameState mutation, runs the given PlayMode filter, restores the file.
cd /c/Dev/squad-ai/Brainstorming/games/meuble || exit 2
f=Assets/Scripts/Runtime/GameState.cs
id="$1"; marked="$2"; repl="$3"; filter="$4"
cp "$f" "scratchpad/game/GameState.$id.bak"
trap 'cp "scratchpad/game/GameState.$id.bak" "$f"' EXIT INT TERM
MSYS2_ARG_CONV_EXCL="*" python - "$f" "$marked" "$repl" <<'PY' || exit 3
import sys, io
p, m, r = sys.argv[1:4]
s = io.open(p, encoding="utf-8").read()
if m not in s: sys.exit("marker not found: " + m)
io.open(p, "w", encoding="utf-8", newline="").write(s.replace(m, r, 1))
PY
xml="scratchpad/game/mut_$id.xml"; rm -f "$xml"
MEUBLE_AGENT=game tools/unity.sh test . --mode PlayMode --filter "$filter" --report-format junit --output "$xml" --timeout 1500 > "scratchpad/game/mut_$id.log" 2>&1
cp "scratchpad/game/GameState.$id.bak" "$f"; trap - EXIT INT TERM
python - "$xml" <<'PY'
import sys, xml.etree.ElementTree as ET
for c in ET.parse(sys.argv[1]).getroot().iter("testcase"):
    f = c.find("failure")
    print(("RED   " if f is not None else "green ") + c.get("name"))
PY
