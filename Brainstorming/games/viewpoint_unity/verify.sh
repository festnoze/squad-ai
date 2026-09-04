#!/usr/bin/env bash
# VIEWPOINT Unity - the whole verification harness, in the order that fails
# fastest. Mirrors what run_tests.gd / --smoke / design_audit.gd do for the
# Godot original (see docs/PRD.md section 17).
#
#   ./verify.sh            everything
#   ./verify.sh compile    scripts compile, nothing else
#   ./verify.sh edit       EditMode suites
#   ./verify.sh play       PlayMode smoke probe
#   ./verify.sh audit      level design audit
#   ./verify.sh player     build a player, run it, and read what it reports
#
# Two rules this script exists to enforce, both learned on this toolchain:
#   - read the JUnit report, never the exit code alone: a run with zero tests
#     exits 0 and looks exactly like a pass;
#   - never read $? through a pipe, it returns the code of the last command in
#     the pipeline (tail, grep) instead of the one that matters.

set -uo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDITOR_VERSION="6000.3.23f1"
RESULTS="$PROJECT/TestResults"
export PATH="${LOCALAPPDATA}/Unity/bin:${PATH}"
export UNITY_NO_BANNER=1 UNITY_NO_PAGER=1 UNITY_NON_INTERACTIVE=1

mkdir -p "$RESULTS"
WHAT="${1:-all}"
FAILED=0

step() { echo; echo "=== $* ==="; }

# Reads a JUnit report and refuses to call an empty run a success.
report() {
  local label="$1" xml="$2" code="$3"
  if [ ! -f "$xml" ]; then
    echo "  ECHEC $label : aucun rapport ($xml), code $code"
    FAILED=1
    return
  fi
  python - "$label" "$xml" "$code" <<'PY'
import sys, xml.etree.ElementTree as ET
label, path, code = sys.argv[1], sys.argv[2], sys.argv[3]
root = ET.parse(path).getroot()
suites = [root] if root.tag == "testsuite" else root.iter("testsuite")
tests = failures = errors = skipped = 0
for s in suites:
    tests += int(s.get("tests", 0)); failures += int(s.get("failures", 0))
    errors += int(s.get("errors", 0)); skipped += int(s.get("skipped", 0))
bad = failures + errors
if tests == 0:
    print("  ECHEC %s : run a zero test (code %s) - un run vide sort 0 et ressemble a un succes" % (label, code))
    sys.exit(1)
for case in root.iter("testcase"):
    for kind in ("failure", "error"):
        node = case.find(kind)
        if node is not None:
            print("  ECHEC %s :: %s" % (label, case.get("name")))
            for line in (node.get("message") or node.text or "").strip().splitlines()[:4]:
                print("         %s" % line.strip())
print("  %s : %d verifications, %d echecs, %d ignorees" % (label, tests, bad, skipped))
sys.exit(1 if bad else 0)
PY
  [ $? -ne 0 ] && FAILED=1
  return 0
}

run_tests() {
  local mode="$1" xml="$RESULTS/$1.xml"
  rm -f "$xml"
  unity test "$PROJECT" --mode "$mode" --report-format junit --output "$xml" >"$RESULTS/$mode.log" 2>&1
  local code=$?
  report "$mode" "$xml" "$code"
}

if [ "$WHAT" = all ] || [ "$WHAT" = compile ]; then
  step "Compilation"
  unity run "$PROJECT" -- -executeMethod Viewpoint.Editor.Builder.CompileCheck \
    >"$RESULTS/compile.log" 2>&1
  code=$?
  if [ $code -eq 0 ]; then
    echo "  les scripts compilent"
  else
    echo "  ECHEC compilation (code $code) :"
    grep -E "error CS|Compilation failed" "$RESULTS/compile.log" | sort -u | head -40
    FAILED=1
  fi
fi

if [ "$WHAT" = all ] || [ "$WHAT" = edit ]; then
  step "Suites unitaires (EditMode)"
  run_tests EditMode
fi

if [ "$WHAT" = all ] || [ "$WHAT" = play ]; then
  step "Sonde d'integration (PlayMode)"
  run_tests PlayMode
fi

# THE STEP THAT WAS MISSING, and whose absence cost a working build: every
# suite above runs inside the EDITOR, where Shader.Find resolves everything and
# TextMeshPro tolerates a missing settings asset. A player has neither, and a
# game that passed all 130 tests showed nothing but a horizon line. Delegated to
# PowerShell because that is where it is actually exercised on this machine.
if [ "$WHAT" = all ] || [ "$WHAT" = player ]; then
  step "Le jeu dans un player construit"
  if powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PROJECT/verify-player.ps1"; then
    echo "  player vert"
  else
    echo "  ECHEC player"
    FAILED=1
  fi
fi

if [ "$WHAT" = all ] || [ "$WHAT" = audit ]; then
  step "Audit de level design"
  unity run "$PROJECT" -- -executeMethod Viewpoint.Editor.DesignAudit.RunBatch \
    >"$RESULTS/audit.log" 2>&1
  code=$?
  grep -E "^\s+(Niveau|\[|aucun defaut|[0-9]+ defauts)" "$RESULTS/audit.log" | head -40
  if [ $code -ne 0 ]; then
    echo "  ECHEC audit (code $code)"
    FAILED=1
  fi
fi

echo
if [ $FAILED -eq 0 ]; then
  echo "=== VERT ==="
else
  echo "=== ROUGE : voir $RESULTS ==="
fi
exit $FAILED
