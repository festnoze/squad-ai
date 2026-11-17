#!/usr/bin/env bash
# Scratch: like mut.sh, but takes the Unity lock BEFORE mutating and releases it AFTER the restore,
# so no other agent ever compiles the mutated file.
cd /c/Dev/squad-ai/Brainstorming/games/meuble || exit 2
LOCK=.unity.lock
until mkdir "$LOCK" 2>/dev/null; do sleep 5; done
echo "$(cat /proc/$$/winpid 2>/dev/null || echo $$) game mutation $*" > "$LOCK/owner"
f=Assets/Scripts/Runtime/GameState.cs
cp "$f" scratchpad/game/GameState.pristine
trap 'cp scratchpad/game/GameState.pristine "$f"; rm -rf "$LOCK"' EXIT INT TERM
export PATH="${LOCALAPPDATA:-}/Unity/bin:${PATH}" UNITY_NO_BANNER=1 UNITY_NO_PAGER=1 UNITY_NON_INTERACTIVE=1
while [ $# -ge 4 ]; do
  id="$1"; marked="$2"; repl="$3"; filter="$4"; shift 4
  cp scratchpad/game/GameState.pristine "$f"
  MSYS2_ARG_CONV_EXCL="*" python - "$f" "$marked" "$repl" <<'PY' || { echo "marker not found: $id"; continue; }
import sys, io
p, m, r = sys.argv[1:4]
s = io.open(p, encoding="utf-8").read()
if m not in s: sys.exit(1)
io.open(p, "w", encoding="utf-8", newline="").write(s.replace(m, r, 1))
PY
  xml="scratchpad/game/mut_$id.xml"; rm -f "$xml"
  MEUBLE_UNITY_LOCK_HELD=1 MEUBLE_AGENT=game tools/unity.sh test . --mode PlayMode --filter "$filter" --report-format junit --output "$xml" --timeout 1500 > "scratchpad/game/mut_$id.log" 2>&1
  cp scratchpad/game/GameState.pristine "$f"
  echo "== $id"
  python - "$xml" <<'PY'
import sys, xml.etree.ElementTree as ET
for c in ET.parse(sys.argv[1]).getroot().iter("testcase"):
    f = c.find("failure")
    print(("RED   " if f is not None else "green ") + c.get("name"), ((f.get("message") or "")[:160].replace("\n", " ") if f is not None else ""))
PY
done
