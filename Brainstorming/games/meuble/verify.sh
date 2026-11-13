#!/usr/bin/env bash
# UN, DEUX, TROIS, MEUBLE - the verification harness of docs/PRD.md section 10.
#
#   ./verify.sh            every stage, stops on the first red one
#   ./verify.sh compile    project setup + scripts compile
#   ./verify.sh edit       EditMode unit tests (10.1)
#   ./verify.sh play       PlayMode probe, 9 steps (10.2)
#   ./verify.sh audit      level audit (10.3)
#   ./verify.sh player     build a Windows player, run it with --probe, read its report (10.4)
#
# Rules this script enforces, all paid for on this toolchain:
#   - read the JUnit report, never the exit code alone: a run with zero tests exits 0;
#   - never read $? through a pipe, it is the code of the last command of the pipeline;
#   - a green editor test proves nothing about a build: the player is built, run and read.

set -uo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT" || exit 2
RESULTS="$PROJECT/TestResults"
SHOTS="$RESULTS/shots"
export PATH="${LOCALAPPDATA:-}/Unity/bin:${PATH}"
export UNITY_NO_BANNER=1 UNITY_NO_PAGER=1 UNITY_NON_INTERACTIVE=1
mkdir -p "$RESULTS"
WHAT="${1:-all}"

step() { echo; echo "=== $* ==="; }
red() { echo "  ROUGE : $*"; echo; echo "=== ROUGE (voir $RESULTS) ==="; exit 1; }
want() { [ "$WHAT" = all ] || [ "$WHAT" = "$1" ]; }

# Reads a JUnit report; refuses an empty run, a skipped case and a missing expected case;
# prints every failing case. $4 (optional) lists test name prefixes that must be present.
report() {
  local label="$1" xml="$2" code="$3" expected="${4:-}"
  [ -f "$xml" ] || red "$label : aucun rapport ($xml), code de sortie $code"
  python - "$label" "$xml" "$code" "$expected" <<'PY'
import sys, xml.etree.ElementTree as ET
label, path, code, expected = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].split()
root = ET.parse(path).getroot()
cases = list(root.iter("testcase"))
bad = []
for case in cases:
    for kind in ("failure", "error", "skipped"):
        node = case.find(kind)
        if node is not None:
            bad.append((case.get("classname", "") + "." + case.get("name", "") + (" (ignore)" if kind == "skipped" else ""),
                        (node.get("message") or node.text or "").strip()))
names = [c.get("name", "") for c in cases]
for prefix in expected:
    if not any(n.startswith(prefix) for n in names):
        bad.append((prefix, "etape attendue absente du rapport"))
if not cases:
    print("  %s : run a ZERO test (code %s) - un run vide sort 0 et ressemble a un succes" % (label, code))
    sys.exit(1)
for name, msg in bad:
    print("  ECHEC %s" % name)
    for line in msg.splitlines()[:4]:
        print("        %s" % line.strip())
print("  %s : %d tests, %d echecs" % (label, len(cases), len(bad)))
sys.exit(1 if bad else 0)
PY
  [ $? -eq 0 ] || red "$label"
}

run_tests() {
  local mode="$1" xml="$RESULTS/$1.xml" expected="${2:-}"
  rm -f "$xml"
  "$PROJECT/tools/unity.sh" test . --mode "$mode" --report-format junit --output "$xml" --timeout 3600 >"$RESULTS/$mode.log" 2>&1
  local code=$?
  report "$mode" "$xml" "$code" "$expected"
}

# Every probe step of PRD 10.2, plus the steps added since. A missing or ignored step is red.
PROBE_STEPS="Step01_ Step02_ Step03_ Step04_ Step05_ Step06_ Step07_ Step08_ Step09_ Step10_ Step11_ Step12_ Step13_ Step14_ Step15_ Step16_ Step17_ Step18_ Step19_ Step20_ Step21_ Step13b_ Step13c_ Step14b_ Step19b_ Step20b_ Step21b_ Step13d_ Step13e_ Step14c_ Step22_ Step23_ Step24_ Step25_ Step26_ Step27_ Step28_ Step28b_ Step28c_ Step28d_ Step28e_ Step28f_ Step28g_ Step29_ Step29b_ Step29c_ Step29d_ Step29e_ Step29f_ Step29g_ Step29h_ Step29i_ Step29j_ Step29k_ Step29l_ Step29m_ Step29n_ Step30_ Step30b_ Step30c_ Step30d_ Step30e_ Step30f_ Step31_ Step32_ Step33_ Step33b_ Step33c_ Step33d_ Step35_ Step35a_ Step35b_"

if want compile; then
  step "Setup du projet et compilation"
  "$PROJECT/tools/unity.sh" run . --timeout 900 -- -executeMethod Meuble.Editor.Builder.SetupAndCompile -logFile "$RESULTS/compile.log" >"$RESULTS/compile.out" 2>&1
  code=$?
  if [ $code -ne 0 ]; then
    grep -E "error CS|Compilation failed|\[Builder\]" "$RESULTS/compile.log" | sort -u | head -40
    red "compilation ou setup (code $code)"
  fi
  # A broken shader fails neither the compile nor the build: it only shows in the log.
  if grep -qE "Shader error|error in shader|Shader compilation failed" "$RESULTS/compile.log"; then
    grep -E "Shader error|error in shader|Shader compilation failed" "$RESULTS/compile.log" | sort -u | head -10
    red "erreur de shader"
  fi
  echo "  les scripts compilent, couches, shaders et scene Boot en place"
fi

# EditMode tests the gate relies on (mutation killers and the M4 chair-row identity). A missing one is red.
EDIT_TESTS="Seen_and_moving_018_then_hidden_is_not_caught_and_resets Chair_row_equals_the_M1_constants_field_by_field Paused_gauge_freezes_like_carried_and_resumes_where_it_stopped"

if want edit; then
  step "Tests unitaires (EditMode, PRD 10.1)"
  run_tests EditMode "$EDIT_TESTS"
fi

if want play; then
  step "Sonde PlayMode (PRD 10.2)"
  run_tests PlayMode "$PROBE_STEPS"
fi

if want audit; then
  step "Audit de niveau (PRD 10.3)"
  "$PROJECT/tools/unity.sh" run . --timeout 2400 -- -executeMethod Meuble.Editor.LevelAudit.RunBatch -logFile "$RESULTS/audit.log" >"$RESULTS/audit.out" 2>&1
  code=$?
  python - "$RESULTS/audit.log" <<'PY'
import sys, io
text = io.open(sys.argv[1], encoding="utf-8", errors="replace").read()
out, keep = [], False
for line in text.splitlines():
    if line.startswith("[LevelAudit]"):
        keep = True
    elif keep and not (line.startswith("  ") or line.strip() == ""):
        keep = False
    if keep and line.strip():
        out.append(line)
print("\n".join("  " + l for l in out) if out else "  (aucune sortie d'audit dans le journal)")
PY
  [ $code -eq 0 ] || red "audit (code $code)"
fi

if want player; then
  step "Le jeu dans un player construit (PRD 10.4)"
  rm -rf "$PROJECT/Build/Windows"
  "$PROJECT/tools/unity.sh" run . --timeout 1800 -- -executeMethod Meuble.Editor.Builder.BuildWindows -logFile "$RESULTS/build.log" >"$RESULTS/build.out" 2>&1
  code=$?
  EXE="$PROJECT/Build/Windows/Meuble.exe"
  if [ $code -ne 0 ] || [ ! -f "$EXE" ]; then
    grep -E "error CS|Build failed|\[Builder\]" "$RESULTS/build.log" | head -20
    red "build du player (code $code)"
  fi
  SIZE_MB=$(du -sm --exclude='*DoNotShip*' "$PROJECT/Build/Windows" | cut -f1)
  echo "  player construit : ${SIZE_MB} MB (budget 120 MB)"
  [ "$SIZE_MB" -le 120 ] || red "build de ${SIZE_MB} MB au dessus du budget de 120 MB"

  rm -rf "$SHOTS"; mkdir -p "$SHOTS"
  PLAYER_LOG="$RESULTS/Player.log"
  rm -f "$PLAYER_LOG"
  timeout 300 "$EXE" --probe --shot "$(cygpath -w "$SHOTS")" -screen-width 1280 -screen-height 720 -screen-fullscreen 0 \
    -logFile "$(cygpath -w "$PLAYER_LOG")"
  code=$?
  [ $code -ne 124 ] || red "le player ne s'est jamais termine (300 s)"

  python - "$SHOTS/report.json" "$PLAYER_LOG" "$code" <<'PY'
import sys, json, io, os
report_path, log_path, code = sys.argv[1], sys.argv[2], int(sys.argv[3])
bad = []
if not os.path.exists(report_path):
    print("  pas de report.json : la sonde n'a pas conclu (code %d)" % code)
    sys.exit(1)
r = json.load(io.open(report_path, encoding="utf-8"))
a = r.get("audit", {})
for k in sorted(a):
    if k.startswith("shader"):
        print("  %-44s %s" % (k, a[k]))
print("  renderers %s, sans materiau %s, triangles %s, materiaux %s, lumieres %s (ombrees %s)" % (
    a.get("renderers"), a.get("renderersWithoutMaterial"), a.get("triangles"), a.get("materials"), a.get("lights"), a.get("shadowedLights")))
print("  police : %s, %d libelles" % (a.get("font"), len(a.get("labels", {}))))
for s in r.get("shots", []):
    print("  capture %-14s %sx%s luminance moyenne %.3f" % (s["file"], s["width"], s["height"], s["meanLuminance"]))
print("  etats atteints : Caught=%s Won=%s, panneaux echec=%s victoire=%s" % (
    r.get("caughtReached"), r.get("wonReached"), r.get("failPanelVisible"), r.get("winPanelVisible")))
for f in r.get("failures", []):
    bad.append(f)
if os.path.exists(log_path):
    lines = io.open(log_path, encoding="utf-8", errors="replace").read().splitlines()
    exc = [l for l in lines if "Exception" in l]
    print("  Player.log : %d ligne(s) d'exception" % len(exc))
    bad += ["Player.log : " + l.strip() for l in exc[:5]]
else:
    bad.append("Player.log absent")
if code != 0:
    bad.append("le player est sorti avec le code %d" % code)
if len(r.get("shots", [])) < 2:
    bad.append("moins de deux captures")
for b in bad:
    print("  ECHEC " + b)
sys.exit(1 if bad else 0)
PY
  [ $? -eq 0 ] || red "verification du player"
  echo "  captures a regarder (aucune assertion ne remplace un oeil) :"
  for f in "$SHOTS"/*.png; do echo "    $(cygpath -w "$f")"; done
fi

echo
echo "=== VERT ==="
exit 0
