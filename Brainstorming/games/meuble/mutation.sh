#!/usr/bin/env bash
# Mutation check (PRD 10.2, extended per milestone): each mutation breaks one rule on a marked line,
# runs the suite that must notice, and the file is restored whatever happens. A mutation that leaves
# every expected test green means the harness cannot see that rule.
#
#   ./mutation.sh          every mutation
#   ./mutation.sh grace    only the mutations whose id contains "grace"

set -uo pipefail
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT" || exit 2
RESULTS="$PROJECT/TestResults/mutation"
export UNITY_NO_BANNER=1 UNITY_NO_PAGER=1 UNITY_NON_INTERACTIVE=1
mkdir -p "$RESULTS"
ONLY="${1:-}"

# id | file | marked text | replacement | mode | expected red names (space separated)
# mode is EditMode or PlayMode (expected = test name prefixes), or Audit (expected = level or fixture ids
# that the level audit must report as failing).
# The fields are split on '|': a marked text must never contain '|' (use a /*MUTATION:X*/ token).
MUTATIONS=(
  "cone|Assets/Scripts/Core/VisionMath.cs|return inside; // MUTATION:CONE|return !inside; // MUTATION:CONE|PlayMode|Step03_StillWhileSeen Step04_Caught Step05_Occluder Step06_OutOfCone"
  "reset|Assets/Scripts/Core/CaughtRule.cs|SeenMoving = 0f; // MUTATION:RESET (mutation.sh removes this line)|// MUTATION:RESET removed|EditMode|Seen_and_moving_018_then_hidden_is_not_caught_and_resets"
  "grace|Assets/Scripts/Core/FurnitureMemory.cs|if (outOfPlace >= Tuning.DiscoveryGrace - GraceEpsilon) // MUTATION:GRACE|if (outOfPlace >= 0f) // MUTATION:GRACE|PlayMode|Step13c_"
  "decay|Assets/Scripts/Runtime/GameState.cs|rules.DisplacementMemory && InCalmMode(inhabitants[i].Routine)) // MUTATION:DECAY|rules.DisplacementMemory) // MUTATION:DECAY|PlayMode|Step21b_"
  # M3: model facing, head driven by the eye, pause, hop variants.
  "facing|Assets/Scripts/Runtime/ModelKit.cs|float yaw = ModelMath.SnapYaw(entry.yawOffset); // MUTATION:FACING|float yaw = 0f; // MUTATION:FACING|PlayMode|Step22_ModelsReplaceTheProceduralVisuals"
  "head|Assets/Scripts/Runtime/InhabitantRig.cs|Head.rotation = Quaternion.Euler(0f, eyeYaw, 0f) * headCalibration * roll; // MUTATION:HEAD|Head.rotation = Quaternion.Euler(0f, bodyYaw, 0f) * headCalibration * roll; // MUTATION:HEAD|PlayMode|Step24_LoopDrivesClipsHeadAndFootsteps"
  "pause|Assets/Scripts/Runtime/GameState.cs|Paused /*MUTATION:PAUSE*/|false /*MUTATION:PAUSE*/|PlayMode|Step26_PauseStopsEveryRuleAndHoldsVisuals"
  "variant|Assets/Scripts/Runtime/Sfx.cs|return v >= last ? v + 1 : v; // MUTATION:VARIANT|return last; // MUTATION:VARIANT|PlayMode|Step27d_HopVariantsNeverRepeat"
  # M4: the bodies, the gauge frozen while sat on, the chair row (an M1 step must turn red).
  "stool_tip|Assets/Scripts/Runtime/FurnitureController.cs|bool tips = bodies && Body.Tips; // MUTATION:STOOL_TIP|bool tips = false; // MUTATION:STOOL_TIP|PlayMode|Step29i_ Step29j_"
  "glide|Assets/Scripts/Runtime/FurnitureController.cs|bool glides = bodies && Body.Glides; // MUTATION:GLIDE|bool glides = false; // MUTATION:GLIDE|PlayMode|Step29_ Step29b_ Step29c_ Step29d_"
  "lamp_range|Assets/Scripts/Runtime/LampLight.cs|public float RangeFactor => On ? 1f : Tuning.LampOffLight; // MUTATION:LAMP_RANGE|public float RangeFactor => 1f; // MUTATION:LAMP_RANGE|PlayMode|Step29l_"
  "paused_gauge|Assets/Scripts/Core/CreakGauge.cs|paused, levelTime); // MUTATION:PAUSED|false, levelTime); // MUTATION:PAUSED|EditMode|Paused_gauge_freezes_like_carried_and_resumes_where_it_stopped"
  "chair_row|Assets/Scripts/Core/BodyDef.cs|MaxSpeed = Tuning.ChairMaxSpeed /*MUTATION:CHAIR_ROW*/|MaxSpeed = Tuning.ChairMaxSpeed * 1.5f /*MUTATION:CHAIR_ROW*/|PlayMode|Step02_MoveUnseen"
  "saton_moving|Assets/Scripts/Runtime/GameState.cs|furniture.IsMoving /*MUTATION:SATON_MOVING*/|!(!furniture.IsMoving && !furniture.Pinned) /*MUTATION:SATON_MOVING*/|PlayMode|Step32_"
  "sit_check|Assets/Scripts/Runtime/GameState.cs|return off <= Tuning.SeatHomeTolerance; // MUTATION:SIT_CHECK|return off <= 1f; // MUTATION:SIT_CHECK|PlayMode|Step33d_"
  "topple_noise|Assets/Scripts/Runtime/GameState.cs|if (toppledThisStep) // MUTATION:TOPPLE_NOISE|if (toppledThisStep && false) // MUTATION:TOPPLE_NOISE|PlayMode|Step28_ Step28b_ Step28d_"
  "toggle_lit|Assets/Scripts/Runtime/FurnitureController.cs|if (Action == BodyAction.Toggle) return 1f; // MUTATION:TOGGLE_LIT|// MUTATION:TOGGLE_LIT removed|PlayMode|Step29h_ Step29l_"
  "tell_speed|Assets/Scripts/Runtime/FurnitureController.cs|speedNow > Tuning.StoolTellSpeed; // MUTATION:TELL_SPEED|speedNow > Tuning.StoolTipSpeed; // MUTATION:TELL_SPEED|PlayMode|Step29m_"
  "audit_sit_moment|Assets/Editor/LevelAudit.cs|if (r.SittingOnPlayer) // MUTATION:AUDIT_SIT_MOMENT|if (false) // MUTATION:AUDIT_SIT_MOMENT|Audit|level5"
)

# Refuse to start on a tree that still holds a mutation (an interrupted run), and snapshot the sources.
for row in "${MUTATIONS[@]}"; do
  bars="${row//[^|]/}"
  if [ "${#bars}" -ne 5 ]; then
    echo "ECHEC ligne de mutation a ${#bars} separateurs '|' au lieu de 5 : $row"
    exit 2
  fi
  IFS='|' read -r id file marked replacement mode expected <<<"$row"
  if MSYS2_ARG_CONV_EXCL="*" python - "$file" "$replacement" <<'PY'
import sys, io
sys.exit(0 if sys.argv[2] in io.open(sys.argv[1], encoding="utf-8").read() else 1)
PY
  then
    echo "ECHEC $file contient encore la mutation $id (run interrompu ?) : restaurer depuis $RESULTS/$id.bak ou le snapshot"
    exit 2
  fi
done
[ -f "$RESULTS/snapshot.tar" ] && mv -f "$RESULTS/snapshot.tar" "$RESULTS/snapshot.prev.tar"
tar -cf "$RESULTS/snapshot.tar" Assets/Scripts Assets/Editor || { echo "ECHEC snapshot des sources"; exit 2; }

# Prints the ids the level audit reports as failing (a level with defects, or a self-test fixture that
# does not fail for its rule), one per line.
audit_failing() {
  python - "$1" <<'PY'
import sys, io, re
text = io.open(sys.argv[1], encoding="utf-8", errors="replace").read()
for m in re.finditer(r"\[LevelAudit\] Niveau (\S+) : \d+ defaut", text):
    print(m.group(1))
for m in re.finditer(r"\[DEFAUT\] (\S+) :", text):
    print(m.group(1))
PY
}

# Prints the names of the failing test cases of a JUnit report, one per line.
failing() {
  python - "$1" <<'PY'
import sys, xml.etree.ElementTree as ET
for case in ET.parse(sys.argv[1]).getroot().iter("testcase"):
    if case.find("failure") is not None or case.find("error") is not None:
        print(case.get("name"))
PY
}

OK=1
for row in "${MUTATIONS[@]}"; do
  IFS='|' read -r id file marked replacement mode expected <<<"$row"
  if [ -n "$ONLY" ] && [[ "$id" != *"$ONLY"* ]]; then
    continue
  fi
  echo "=== Mutation $id ($file) ==="
  cp "$file" "$RESULTS/$id.bak"
  # The restore runs whatever happens, including Ctrl+C.
  trap 'cp "$RESULTS/$id.bak" "$file"' EXIT INT TERM
  # Git Bash (MSYS) rewrites arguments that start with "//" into paths: "// MUTATION" would reach
  # Python as "/ MUTATION" and break the compile. Conversion is off for this call only (unity.exe
  # still needs its paths converted).
  if ! MSYS2_ARG_CONV_EXCL="*" python - "$file" "$marked" "$replacement" <<'PY'
import sys, io
path, marked, replacement = sys.argv[1], sys.argv[2], sys.argv[3]
s = io.open(path, encoding="utf-8").read()
if marked not in s:
    sys.exit("marker not found: " + marked)
io.open(path, "w", encoding="utf-8", newline="").write(s.replace(marked, replacement, 1))
PY
  then
    echo "  ECHEC marqueur introuvable"; OK=0; continue
  fi
  xml="$RESULTS/$id.xml"
  rm -f "$xml"
  if [ "$mode" = "Audit" ]; then
    "$PROJECT/tools/unity.sh" run . --timeout 2400 -- -executeMethod Meuble.Editor.LevelAudit.RunBatch -logFile "$RESULTS/$id.audit.log" >"$RESULTS/$id.log" 2>&1
  else
    # Only the tests that must turn red are run (a regex alternation of their name prefixes).
    "$PROJECT/tools/unity.sh" test . --mode "$mode" --filter "$(echo $expected | tr ' ' '|')" --report-format junit --output "$xml" --timeout 3600 >"$RESULTS/$id.log" 2>&1
  fi
  cp "$RESULTS/$id.bak" "$file"
  trap - EXIT INT TERM
  if [ "$mode" = "Audit" ]; then
    if [ ! -f "$RESULTS/$id.audit.log" ]; then
      echo "  ECHEC pas de journal d audit (voir $RESULTS/$id.log)"; OK=0; continue
    fi
    red="$(audit_failing "$RESULTS/$id.audit.log")"
  else
    if [ ! -f "$xml" ]; then
      echo "  ECHEC pas de rapport (voir $RESULTS/$id.log)"; OK=0; continue
    fi
    red="$(failing "$xml")"
  fi
  echo "  rouges : $(echo $red)"
  for name in $expected; do
    if echo "$red" | grep -q "^$name"; then
      echo "  OK  $name rougit"
    else
      echo "  ECHEC $name reste vert sous la mutation"; OK=0
    fi
  done
done

if [ $OK -eq 1 ]; then echo "=== MUTATIONS DETECTEES ==="; exit 0; fi
echo "=== UNE MUTATION A SURVECU ==="; exit 1
