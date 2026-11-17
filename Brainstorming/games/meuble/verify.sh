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

# M5 5B.1 (CONTRACT_M5 16.11 and 19 M1): every killer of mutation.sh must be a test this gate requires, so a killer that
# is renamed or deleted turns the gate red instead of leaving its rule unseen. A killer prefix is covered by a required
# name that starts with it (the presence check then proves a test with that prefix exists).
killers_listed() {
  local mode="$1" listed="$2" missing="" row id file marked replacement m expected k e hit
  local -a MUTATIONS=() ks=()
  eval "$(sed -n '/^MUTATIONS=(/,/^)/p' "$PROJECT/mutation.sh")"
  [ "${#MUTATIONS[@]}" -gt 0 ] || red "aucune ligne de mutation lue dans mutation.sh"
  for row in "${MUTATIONS[@]}"; do
    IFS='|' read -r id file marked replacement m expected <<<"$row"
    [ "$m" = "$mode" ] || continue
    read -r -a ks <<<"$expected"
    for k in "${ks[@]}"; do
      hit=0
      for e in $listed; do
        case "$e" in "$k"*) hit=1; break ;; esac
      done
      [ $hit -eq 1 ] || missing="$missing $id:$k"
    done
  done
  [ -z "$missing" ] || red "tueurs $mode de mutation.sh absents de la liste exigee par verify.sh :$missing"
  echo "  tous les tueurs $mode de mutation.sh sont exiges"
}

# Every probe step of PRD 10.2, plus the steps added since, plus the full name of every PlayMode mutation killer
# (M5 5B.1: a prefix shared by two tests, such as Step37w_, would let one of them vanish). A missing or ignored
# step is red.
PROBE_STEPS="Step01_ Step02_ Step03_ Step04_ Step05_ Step06_ Step07_ Step08_ Step09_ Step10_ Step11_ Step12_ Step13_ Step14_ Step15_ Step16_ Step17_ Step18_ Step19_ Step20_ Step21_ Step13b_ Step13c_ Step14b_ Step19b_ Step20b_ Step21b_ Step13d_ Step13e_ Step14c_ Step22_ Step22b_ Step22c_ Step22d_ Step22e_ Step22f_ Step23_ Step24_ Step24f_ Step24g_ Step24h_ Step25_ Step26_ Step27_ Step27b_ Step27c_ Step27d_ Step27e_ Step27f_ Step27g_ Step27h_ Step28_ Step28b_ Step28c_ Step28d_ Step28e_ Step28f_ Step28g_ Step29_ Step29b_ Step29c_ Step29d_ Step29e_ Step29f_ Step29g_ Step29h_ Step29i_ Step29j_ Step29k_ Step29l_ Step29m_ Step29n_ Step30_ Step30b_ Step30c_ Step30d_ Step30e_ Step30f_ Step31_ Step32_ Step33_ Step33b_ Step33c_ Step33d_ Step35_ Step35a_ Step35b_ Step41_ Step41b_ Step41c_ Step41d_ Step41e_ Step41f_ Step41g_ Step36g_ Step36h_ Step36i_ Step36j_ Step36k_ Step36_ Step36b_ Step36c_ Step36d_ Step36e_ Step36f_ Step36l_ Step36m_ Step36n_ Step37_ Step37b_ Step37c_ Step37d_ Step37e_ Step37f_ Step37g_ Step38_ Step38b_ Step38c_ Step38d_ Step38e_ Step38f_ Step39_ Step39c_ Step39d_ Step39e_ Step39f_ Step39g_ Step39h_ Step39i_ Step39j_ Step40_ Step45_ Step45a_ Step45b_ Step45c_ Step45d_ Step45e_ Step45f_ Step45h_ Step45g_ Step39k_ Step38g_ Step37h_ Step36o_ Step37w_ConeFollowsThePlatformTop Step37x_ Step38w_ Step39l_ Step39m_ Step42b_ Step42c_ Step42d_ Step42e_ Step42f_ Step42g_ Step42w_ Step43b_ Step43r_ Step44b_ Step44c_ Step44d_ Step44e_ Step44f_ Step44g_ Step44w_ Step45i_ Step45j_ Step45k_ Step45l_ Step45m_ Step45n_ Step45o_ Step45p_ Step45q_ Step45r_ Step03_StillWhileSeen Step04_Caught Step05_Occluder Step06_OutOfCone Step22_ModelsReplaceTheProceduralVisuals Step24_LoopDrivesClipsHeadAndFootsteps Step26_PauseStopsEveryRuleAndHoldsVisuals Step27d_HopVariantsNeverRepeat Step02_MoveUnseen Step41_LockedLevelsUnlockThroughRealWins Step41f_CorruptSaveAtBootStartsFresh Step37_EachConeUsesItsWatchersRangeAndAngle Step38_DogConeColourWalkPatterAndFeet Step37_VisualEyeIsTheRoutineEye Step36_LeafPosesAndTheColliderAndOcclusionSwap Step36c_EOpensTheLeafInExactlyThirtyMovingSteps Step36o_OpenLeafBetweenTheCameraAndTheChairIsFaded Step38w_DogFanCoversWhatItSees Step42w_RobotVisualFollowsSetPoseWithoutCollider Step44w_LoadSitsOnTopTiltsAndBreaks Step39h_CombinedRenderersKeepCollidersMaterialsAndFades Step44x_ Step50a_NewSurfacesShowTheirDetailAndFinish Step50b_FallenLoadPlantShowsSoilAndFoliage Step53a_EnterAndLeaveTheWardrobe Step53b_HiddenCreakIsMuffled Step53c_RememberedSpotSeenEmpty Step54a_DoorMemoryPutsTheDoorBack Step55a_InhabitantOpensAnOptInDoor Step56a_Level18RouteWins Step51a_OptionsAppliedAtOnce Step51b_OptionsSurviveRestartAndReload Step52a_MenusNavigableWithInjectedGamepadAlone Step52b_EyeShapesEdgePatternAndConeOutline Step57a_ Step57b_"

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
EDIT_TESTS="Seen_and_moving_018_then_hidden_is_not_caught_and_resets Chair_row_equals_the_M1_constants_field_by_field Paused_gauge_freezes_like_carried_and_resumes_where_it_stopped Probe_save_never_points_at_the_real_file A_slower_time_never_replaces_the_best Each_personality_sees_with_its_own_range_and_angle_through_the_routine Tidy_memory_notices_0_4_m_where_the_default_one_confirms Routine_visits_follow_the_pattern_over_20_visits Sleep_station_closes_the_eye_for_the_dwell_and_the_wake_telegraph Eye_height_follows_the_personality_through_every_reset Station_walks_are_frozen_with_the_station_planner_and_every_other_walk_uses_the_investigate_planner RecordWin_replaces_a_best_time_only_with_a_strictly_lower_one The_dog_is_fitted_with_its_eyes_at_the_dog_eye_and_the_humans_at_theirs Three_humans_and_a_dog_add_at_most_twelve_materials FloorMap_gives_the_platform_height_on_it_the_ramp_slope_along_it_and_0_elsewhere Door_reach_needs_the_distance_and_a_footprint_outside_the_sector Manifest_lists_the_levels_in_play_order_and_each_is_valid Every_shipped_designer_route_ends_at_its_exit_and_starts_after_the_level ChoosePath_gives_the_real_file_only_to_a_plain_built_player StationOrder_draws_each_pattern_in_the_contract_order The_dog_never_sits_never_hears_never_investigates FloorMap_reads_the_level_live_and_the_flat_floor_is_0 A_locked_tmp_in_the_fallback_is_kept_and_restored_at_the_next_load A_missing_file_with_a_good_tmp_is_restored_from_it_before_the_bak Missing_file_without_tmp_is_restored_from_bak Rocking_chair_row_matches_the_contract_member_by_member The_fall_is_at_the_threshold_latched_until_reset_and_ratio_is_the_gauge A_90_deg_turn_at_full_chair_speed_drops_the_load A_careful_90_deg_chair_turn_and_a_careful_chair_reversal_hold The_hum_masks_a_hop_a_roll_and_a_click_within_2_5_m_only Reverse_travels_the_loop_backwards_from_where_it_is Put_away_walks_to_the_clue_faces_it_bends_for_0_6_s_and_resumes At_most_one_robot_per_level No_load_on_the_rocking_chair Wave5B_levels_follow_the_revised_level_table Wave5B_levels_are_valid_and_played_in_number_order Wave5B_audit_fixtures_are_valid_levels_kept_out_of_the_play_order Topple_creak_crash_and_bark_are_never_masked Any_full_speed_reversal_drops_the_load The_office_chair_full_start_and_full_glide_drop_the_load Careful_U_turns_of_the_stool_and_the_office_chair_drop_the_load DeltaV_compares_with_the_velocity_exactly_one_window_before Stop_distance_and_slide_samples_per_body Office_chair_glides_when_braked_against_its_motion_then_drives_back Release_is_the_instant_stop_the_glide_or_the_tip Straight_start_follows_the_body_table_full_and_careful Every_careful_straight_move_holds A_clue_within_reach_is_put_away_without_walking Only_the_rocking_chair_rocks_and_every_kind_is_a_known_body Robot_loop_runs_into_no_wall_and_never_leaves_the_house House_robot_fixture_crosses_a_doorway_without_a_leaf Robot_loop_stays_on_the_floor_level Robot_loop_stays_out_of_leaf_swing_sectors_and_off_the_leaf Robot_loop_keeps_one_metre_from_the_spawn_the_seat_homes_and_the_exit Lesson_final_needs_three_mechanics_and_mechanics_are_listed_in_order Robot_and_load_meshes_face_outward Clamped_ClampsOutOfRangeToTheBounds Clamped_InvalidConeFallsBackToAlways Clamped_RoundsToTheNearestStep Default_IsSensitivity1Volume80ConeAlways DoorMemory_remembers_the_authored_leaves_and_a_mismatch_is_one_suspect Empty_spot_is_a_suspect_then_one_discovery_until_the_furniture_is_seen Parse_MalformedOptionsFallsBackFieldByField Parse_MissingOptionsIsDefault Parse_ValidOptionsRoundTripThroughJson SaveStore_SetOptions_RoundTripsThroughLoad Wardrobe_entry_zone_is_the_strip_in_front_of_its_front_face Wardrobe_fits_the_stool_and_the_floor_lamp_only"

if want edit; then
  step "Tests unitaires (EditMode, PRD 10.1)"
  killers_listed EditMode "$EDIT_TESTS"
  run_tests EditMode "$EDIT_TESTS"
fi

if want play; then
  step "Sonde PlayMode (PRD 10.2)"
  killers_listed PlayMode "$PROBE_STEPS"
  run_tests PlayMode "$PROBE_STEPS"
fi

if want audit; then
  step "Audit de niveau (PRD 10.3)"
  # CONTRACT_M5 16.3: 1.3 x the per-level warning (240 s) for every level of the manifest and every fixture.
  # M5 5B.1 (CONTRACT_M5 19 m11): Windows Python reads the manifest by its Windows path, the levels are its "levels"
  # list, and the fixtures are the self-test table of LevelAudit (one "new FixtureRule" each), never a fixed count.
  LEVEL_COUNT=$(python -c 'import io, json, sys; print(len(json.load(io.open(sys.argv[1], encoding="utf-8"))["levels"]))' \
    "$(cygpath -w "$PROJECT/Assets/Resources/Levels/levels.json")" 2>/dev/null)
  [ -n "$LEVEL_COUNT" ] || red "manifeste des niveaux illisible (Assets/Resources/Levels/levels.json)"
  FIXTURE_COUNT=$(grep -cE 'new FixtureRule\b' "$PROJECT/Assets/Editor/LevelAudit.cs")
  [ "${FIXTURE_COUNT:-0}" -gt 0 ] || red "aucune fixture d'audit lue dans Assets/Editor/LevelAudit.cs"
  ITEMS=$(( LEVEL_COUNT + FIXTURE_COUNT ))
  echo "  $LEVEL_COUNT niveaux et $FIXTURE_COUNT fixtures : limite de $(( ITEMS * 312 > 2400 ? ITEMS * 312 : 2400 )) s"
  AUDIT_TIMEOUT=$(( ITEMS * 312 > 2400 ? ITEMS * 312 : 2400 ))
  "$PROJECT/tools/unity.sh" run . --timeout "$AUDIT_TIMEOUT" -- -executeMethod Meuble.Editor.LevelAudit.RunBatch -logFile "$RESULTS/audit.log" >"$RESULTS/audit.out" 2>&1
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
  # M5 (CONTRACT_M5_v3 15.10): the real save must not change during a probe run.
  REAL_SAVE="${USERPROFILE:-$HOME}/AppData/LocalLow/Meuble/UN, DEUX, TROIS, MEUBLE/meuble_save.json"
  REAL_HASH_BEFORE="$( [ -f "$REAL_SAVE" ] && sha256sum "$REAL_SAVE" | cut -d" " -f1 || echo absent)"
  PLAYER_LOG="$RESULTS/Player.log"
  rm -f "$PLAYER_LOG"
  timeout 900 "$EXE" --probe --shot "$(cygpath -w "$SHOTS")" -screen-width 1280 -screen-height 720 -screen-fullscreen 0 \
    -logFile "$(cygpath -w "$PLAYER_LOG")"
  code=$?
  [ $code -ne 124 ] || red "le player ne s'est jamais termine (900 s)"
  REAL_HASH_AFTER="$( [ -f "$REAL_SAVE" ] && sha256sum "$REAL_SAVE" | cut -d" " -f1 || echo absent)"
  [ "$REAL_HASH_BEFORE" = "$REAL_HASH_AFTER" ] || red "la sonde a modifie la vraie sauvegarde ($REAL_SAVE)"

  python - "$SHOTS/report.json" "$PLAYER_LOG" "$code" "$(cygpath -w "$SHOTS")" <<'PY'
import sys, json, io, os
report_path, log_path, code = sys.argv[1], sys.argv[2], int(sys.argv[3])
shots_dir = os.path.normcase(os.path.abspath(sys.argv[4]))
bad = []
if not os.path.exists(report_path):
    print("  pas de report.json : la sonde n'a pas conclu (code %d)" % code)
    sys.exit(1)
r = json.load(io.open(report_path, encoding="utf-8"))
save = r.get("savePath")
if not save:
    bad.append("report.json ne donne pas savePath")
elif not os.path.normcase(os.path.abspath(save)).startswith(shots_dir):
    bad.append("la sauvegarde de la sonde n'est pas dans le dossier des captures : %s" % save)
else:
    print("  sauvegarde de la sonde : %s" % save)
a = r.get("audit", {})
for k in sorted(a):
    if k.startswith("shader"):
        print("  %-44s %s" % (k, a[k]))
print("  renderers %s, sans materiau %s, triangles %s, materiaux %s, lumieres %s (ombrees %s)" % (
    a.get("renderers"), a.get("renderersWithoutMaterial"), a.get("triangles"), a.get("materials"), a.get("lights"), a.get("shadowedLights")))
print("  police : %s, %d libelles" % (a.get("font"), len(a.get("labels", {}))))
for s in r.get("shots", []):
    print("  capture %-14s %sx%s luminance moyenne %.3f" % (s["file"], s["width"], s["height"], s["meanLuminance"]))
# CONTRACT_M5 17: the frame time per level (the probe fails above Tuning.FrameTimeFailMs; 60 fps is only reported).
for lid, lv in sorted((r.get("levels") or {}).items()):
    if isinstance(lv, dict) and "frameMedianMs" in lv:
        med, p95 = lv["frameMedianMs"], lv.get("frameP95Ms")
        print("  images %-8s mediane %5.1f ms, p95 %5.1f ms%s" % (lid, med, p95 if p95 is not None else -1, "" if med <= 16.7 else "  (sous 60 i/s)"))
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
