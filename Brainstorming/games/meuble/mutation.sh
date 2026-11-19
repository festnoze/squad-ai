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
  "feet|Assets/Scripts/Runtime/InhabitantRig.cs|CompleteClips(); // MUTATION:FEET|// MUTATION:FEET removed|PlayMode|Step24f_ Step24g_ Step24h_"
  # M5 wave 5A: the save, the level select, the bodies and the core.
  "probe_real_save|Assets/Scripts/Runtime/SaveStore.cs|if (probe) return true; // MUTATION:PROBE_REAL_SAVE|if (false) return true; // MUTATION:PROBE_REAL_SAVE|EditMode|Probe_save_never_points_at_the_real_file ChoosePath_gives_the_real_file_only_to_a_plain_built_player"
  "locked_playable|Assets/Scripts/Runtime/LevelSelect.cs|=> SaveStore.IsUnlocked(order, index); // MUTATION:LOCKED_PLAYABLE|=> index >= 0; // MUTATION:LOCKED_PLAYABLE|PlayMode|Step41_LockedLevelsUnlockThroughRealWins Step41f_CorruptSaveAtBootStartsFresh"
  "best_time|Assets/Scripts/Core/SaveData.cs|if (seconds < previous) // MUTATION:BEST_TIME|if (seconds >= 0f) // MUTATION:BEST_TIME|EditMode|A_slower_time_never_replaces_the_best RecordWin_replaces_a_best_time_only_with_a_strictly_lower_one"
  "external_still|Assets/Scripts/Runtime/FurnitureController.cs|bool still = !IsMoving && !Gliding && !pendingTip; // MUTATION:EXTERNAL_STILL|bool still = true; // MUTATION:EXTERNAL_STILL|PlayMode|Step36h_"
  "e_claim|Assets/Scripts/Runtime/FurnitureController.cs|bool claimed = ActionKeyClaimed != null && ActionKeyClaimed(); // MUTATION:E_CLAIM|bool claimed = false; // MUTATION:E_CLAIM|PlayMode|Step36j_"
  "personality_range|Assets/Scripts/Core/InhabitantRoutine.cs|public float ViewRange => personality.ViewRange; // MUTATION:PERSONALITY_RANGE|public float ViewRange => Tuning.ViewRange; // MUTATION:PERSONALITY_RANGE|EditMode|Each_personality_sees_with_its_own_range_and_angle_through_the_routine"
  "tidy_tolerance|Assets/Scripts/Core/FurnitureMemory.cs|if (WithinTolerance(player, PlayerSlot, Tolerance)) // MUTATION:TIDY_TOLERANCE|if (WithinTolerance(player, PlayerSlot, Tuning.DisplacementTolerance)) // MUTATION:TIDY_TOLERANCE|EditMode|Tidy_memory_notices_0_4_m_where_the_default_one_confirms"
  "wander_seed|Assets/Scripts/Core/RoutinePatterns.cs|x = seed; // MUTATION:WANDER_SEED|x = 0; // MUTATION:WANDER_SEED|EditMode|Routine_visits_follow_the_pattern_over_20_visits StationOrder_draws_each_pattern_in_the_contract_order"
  "wake|Assets/Scripts/Core/InhabitantRoutine.cs|Enqueue(new Action { Kind = Kind.Telegraph, Value = Tuning.WakeTelegraph }); // MUTATION:WAKE|// MUTATION:WAKE removed|EditMode|Sleep_station_closes_the_eye_for_the_dwell_and_the_wake_telegraph"
  "dog_eye|Assets/Scripts/Core/InhabitantRoutine.cs|private float StandingEye => personality.EyeHeight; // MUTATION:DOG_EYE|private float StandingEye => Tuning.EyeHeight; // MUTATION:DOG_EYE|EditMode|Eye_height_follows_the_personality_through_every_reset The_dog_never_sits_never_hears_never_investigates"
  "detail|Assets/Scripts/Runtime/PrimitiveKit.cs|detailBlock.SetTexture(BaseMapId, texture); // MUTATION:DETAIL|detailBlock.SetTexture(BaseMapId, TextureLibrary.Flat); // MUTATION:DETAIL|PlayMode|Step22c_ Step22d_"
  "frozen_walk|Assets/Scripts/Core/InhabitantRoutine.cs|private IPathPlanner StationPlanner => planner; // MUTATION:FROZEN_WALK|private IPathPlanner StationPlanner => InvestigatePlanner ?? planner; // MUTATION:FROZEN_WALK|EditMode|Station_walks_are_frozen_with_the_station_planner_and_every_other_walk_uses_the_investigate_planner"
  "audit_separation|Assets/Editor/LevelAudit.cs|private static float Separation => Tuning.WatcherSeparation; // MUTATION:AUDIT_SEPARATION|private static float Separation => 0.3f; // MUTATION:AUDIT_SEPARATION|Audit|test_cross"
  # M5 wave 5A: watchers, house and game.
  "pet_eye_target|Assets/Scripts/Runtime/ModelKit.cs|return ModelMath.UniformScale(entry.eyeHeight, entry.TargetEye); // MUTATION:PET_EYE_TARGET|return ModelMath.UniformScale(entry.eyeHeight, Tuning.EyeHeight); // MUTATION:PET_EYE_TARGET|EditMode|The_dog_is_fitted_with_its_eyes_at_the_dog_eye_and_the_humans_at_theirs"
  "cone_range|Assets/Scripts/Runtime/VisionConeView.cs|public float Range => (Owner != null && Owner.Routine != null ? Owner.Routine.ViewRange : Tuning.ViewRange) * RangeFactor; // MUTATION:CONE_RANGE|public float Range => Tuning.ViewRange * RangeFactor; // MUTATION:CONE_RANGE|PlayMode|Step37_EachConeUsesItsWatchersRangeAndAngle Step38_DogConeColourWalkPatterAndFeet"
  "visual_floor|Assets/Scripts/Runtime/Inhabitant.cs|private Vector3 GroundedPosition => Routine.Position + Vector3.up * Routine.FloorHeight; // MUTATION:VISUAL_FLOOR|private Vector3 GroundedPosition => Routine.Position; // MUTATION:VISUAL_FLOOR|PlayMode|Step37_VisualEyeIsTheRoutineEye"
  "floor_map|Assets/Scripts/Core/FloorMap.cs|return Raised(x, z); // MUTATION:FLOOR_MAP|return 0f; // MUTATION:FLOOR_MAP|EditMode|FloorMap_gives_the_platform_height_on_it_the_ramp_slope_along_it_and_0_elsewhere FloorMap_reads_the_level_live_and_the_flat_floor_is_0"
  "leaf_collider|Assets/Scripts/Runtime/DoorLeaf.cs|Pose solid = pose; // MUTATION:LEAF_COLLIDER|Pose solid = Geometry.Pose(0f, out Vector3 _); // MUTATION:LEAF_COLLIDER|PlayMode|Step36_LeafPosesAndTheColliderAndOcclusionSwap"
  "leaf_samples|Assets/Scripts/Runtime/DoorLeaf.cs|bool sampled = Swinging; // MUTATION:LEAF_SAMPLES|bool sampled = true; // MUTATION:LEAF_SAMPLES|PlayMode|Step36_LeafPosesAndTheColliderAndOcclusionSwap"
  "bark_at|Assets/Scripts/Runtime/GameState.cs|Vector3 at = YawMath.Planar(Level.Inhabitants[i].Routine.Position); // MUTATION:BARK_AT|Vector3 at = YawMath.Planar(furniture.transform.position); // MUTATION:BARK_AT|PlayMode|Step38b_ Step37e_"
  "leaf_join|Assets/Scripts/Runtime/GameState.cs|bool seesSwing = vision != null && vision.StepLeaves(Level.Leaves); // MUTATION:LEAF_JOIN|bool seesSwing = false; // MUTATION:LEAF_JOIN|PlayMode|Step36e_"
  "dog_catch|Assets/Scripts/Runtime/GameState.cs|bool catches = p.CountsForCatch; // MUTATION:DOG_CATCH|bool catches = true; // MUTATION:DOG_CATCH|PlayMode|Step38e_ Step38b_ Step38c_"
  "floor_eye|Assets/Scripts/Core/InhabitantRoutine.cs|EyeHeight + FloorHeight, 0f); // MUTATION:FLOOR_EYE|EyeHeight, 0f); // MUTATION:FLOOR_EYE|PlayMode|Step39e_ Step37_VisualEyeIsTheRoutineEye"
  "floor_y|Assets/Scripts/Runtime/FurnitureController.cs|float y = Floor.HeightAt(position.x, position.z); // MUTATION:FLOOR_Y|float y = position.y; // MUTATION:FLOOR_Y|PlayMode|Step39c_"
  "ghost_floor|Assets/Scripts/Runtime/GhostView.cs|return new Vector3(p.x, CurrentFloor().HeightAt(p.x, p.z), p.z); // MUTATION:GHOST_FLOOR|return YawMath.Planar(p); // MUTATION:GHOST_FLOOR|PlayMode|Step39d_"
  # M5 wave 5A.1.
  "tmp_kept|Assets/Scripts/Runtime/SaveStore.cs|if (File.Exists(path)) // MUTATION:TMP_KEPT|if (true) // MUTATION:TMP_KEPT|EditMode|A_locked_tmp_in_the_fallback_is_kept_and_restored_at_the_next_load"
  "tmp_restore|Assets/Scripts/Runtime/SaveStore.cs|SaveData fromTmp = tmpText != null ? SaveData.Parse(tmpText, out tmpProblem) : null; // MUTATION:TMP_RESTORE|SaveData fromTmp = null; // MUTATION:TMP_RESTORE|EditMode|A_missing_file_with_a_good_tmp_is_restored_from_it_before_the_bak A_locked_tmp_in_the_fallback_is_kept_and_restored_at_the_next_load"
  "missing_bak|Assets/Scripts/Runtime/SaveStore.cs|SaveData fromBak = bakText != null ? SaveData.Parse(bakText, out bakProblem) : null; // MUTATION:MISSING_BAK|SaveData fromBak = null; // MUTATION:MISSING_BAK|EditMode|Missing_file_"
  "leaf_last_step|Assets/Scripts/Runtime/DoorLeaf.cs|SwingProgress = 1f; // MUTATION:LEAF_LAST_STEP|SwingProgress = 1f; Swinging = false; // MUTATION:LEAF_LAST_STEP|PlayMode|Step36_LeafPosesAndTheColliderAndOcclusionSwap Step36c_EOpensTheLeafInExactlyThirtyMovingSteps"
  "leaf_fade|Assets/Scripts/Runtime/WallFader.cs|bool crossed = CrossesBox(camera, points, count, e.Box, e.HalfSize); // MUTATION:LEAF_FADE|bool crossed = false; // MUTATION:LEAF_FADE|PlayMode|Step36o_OpenLeafBetweenTheCameraAndTheChairIsFaded"
  "dog_asleep|Assets/Scripts/Runtime/Vision.cs|if (routine.Asleep) // MUTATION:DOG_ASLEEP|if (false) // MUTATION:DOG_ASLEEP|PlayMode|Step38g_"
  "draw_slots|Assets/Scripts/Runtime/Probe.cs|count.MaterialSlots++; // MUTATION:DRAW_SLOTS|// MUTATION:DRAW_SLOTS removed|PlayMode|Step22c_"
  "visual_slope|Assets/Scripts/Runtime/FurnitureController.cs|if (GroundFrame(position, yaw, ref ground, ref lift)) // MUTATION:VISUAL_SLOPE|if (false) // MUTATION:VISUAL_SLOPE|PlayMode|Step39k_"
  "audit_draw_calls|Assets/Editor/LevelAudit.cs|int drawCalls = slots ? count.Slots : count.Renderers; // MUTATION:AUDIT_DRAW_CALLS|int drawCalls = count.Renderers; // MUTATION:AUDIT_DRAW_CALLS|Audit|test_m5_audit_drawcalls"
  "audit_cone_colours|Assets/Editor/LevelAudit.cs|bool dog = coneColours && cone.Owner != null && cone.Owner.IsDog; // MUTATION:AUDIT_CONE_COLOURS|bool dog = false; // MUTATION:AUDIT_CONE_COLOURS|Audit|test_m5_audit_conecolours"
  "audit_dark_memory|Assets/Editor/LevelAudit.cs|if (strict && !w.Watchers[h].Personality.Memory) // MUTATION:AUDIT_DARK_MEMORY|if (false) // MUTATION:AUDIT_DARK_MEMORY|Audit|test_m5_audit_darkpass"
  "audit_dark_range|Assets/Editor/LevelAudit.cs|float darkRange = (strict ? w.Watchers[h].Range : Tuning.ViewRange) * Tuning.LampOffLight; // MUTATION:AUDIT_DARK_RANGE|float darkRange = Tuning.ViewRange * Tuning.LampOffLight; // MUTATION:AUDIT_DARK_RANGE|Audit|test_m5_audit_darkpass"
  "dog_alarm_hue|Assets/Scripts/Runtime/VisionConeView.cs|Color c = alarm ? Tuning.DogConeAlarmColor : Tuning.DogConeColor; // MUTATION:DOG_ALARM_HUE|Color c = Tuning.DogConeColor; // MUTATION:DOG_ALARM_HUE|PlayMode|Step38_DogConeColourWalkPatterAndFeet"
  # M5 wave 5B.1.
  "push_moving|Assets/Scripts/Runtime/FurnitureController.cs|IsMoving = !Pinned && MotionRule.IsMoving(PlanarSpeed, YawRate, ActionActive); // MUTATION:PUSH_MOVING|IsMoving = !Pinned && MotionRule.IsMoving(PlanarSpeed, YawRate, ActionActive && Action != BodyAction.Push); // MUTATION:PUSH_MOVING|PlayMode|Step42b_ Step42c_ Step42g_"
  # M6.
  "lacquer_red|Assets/Scripts/Runtime/FurnitureKit.cs|private static Surface MainSurface(Color color, Surface normal) => ModelMath.IsRed(color) ? Surface.Lacquer : normal; // MUTATION:LACQUER_RED|private static Surface MainSurface(Color color, Surface normal) => normal; // MUTATION:LACQUER_RED|PlayMode|Step50a_"
  "lit_surface_key|Assets/Scripts/Runtime/PrimitiveKit.cs|var key = (color32, surface); // MUTATION:LIT_SURFACE_KEY|var key = (color32, Surface.Plain); // MUTATION:LIT_SURFACE_KEY|PlayMode|Step50a_ Step50b_"
  "options_step_round|Assets/Scripts/Core/SaveData.cs|float steps = Mathf.Round((clamped - min) / step); // MUTATION:OPTIONS_STEP_ROUND|float steps = Mathf.Floor((clamped - min) / step); // MUTATION:OPTIONS_STEP_ROUND|EditMode|Clamped_RoundsToTheNearestStep"
  "options_cone_fallback|Assets/Scripts/Core/SaveData.cs|Cone = Cone == ConeNever ? ConeNever : ConeAlways, // MUTATION:OPTIONS_CONE_FALLBACK|Cone = Cone, // MUTATION:OPTIONS_CONE_FALLBACK|EditMode|Clamped_InvalidConeFallsBackToAlways Parse_MalformedOptionsFallsBackFieldByField"
  "volume_scale|Assets/Scripts/Runtime/SaveStore.cs|AppliedVolume = Mathf.Clamp01(Current.Options.Volume / 100f); // MUTATION:VOLUME_SCALE|AppliedVolume = Mathf.Clamp01(Current.Options.Volume); // MUTATION:VOLUME_SCALE|PlayMode|Step51a_OptionsAppliedAtOnce Step51b_OptionsSurviveRestartAndReload"
  "camera_sensitivity|Assets/Scripts/Runtime/OrbitCamera.cs|float sens = SaveStore.Options.Sensitivity; // MUTATION:CAMERA_SENSITIVITY|float sens = 1f; // MUTATION:CAMERA_SENSITIVITY|PlayMode|Step51a_OptionsAppliedAtOnce"
  "cone_hide|Assets/Scripts/Runtime/VisionConeView.cs|bool coneHidden = SaveStore.Options.HidesCone; // MUTATION:CONE_HIDE|bool coneHidden = false; // MUTATION:CONE_HIDE|PlayMode|Step51a_OptionsAppliedAtOnce"
  "cone_outline_alarm|Assets/Scripts/Runtime/VisionConeView.cs|outline.enabled = !coneHidden && alarm; // MUTATION:CONE_OUTLINE_ALARM|outline.enabled = !coneHidden; // MUTATION:CONE_OUTLINE_ALARM|PlayMode|Step52b_EyeShapesEdgePatternAndConeOutline"
  "pulse_pattern_gate|Assets/Scripts/Runtime/Hud.cs|pc.a = seenMoving > 0f ? a : 0f; // MUTATION:PULSE_PATTERN_GATE|pc.a = seenMoving <= 0f ? a : 0f; // MUTATION:PULSE_PATTERN_GATE|PlayMode|Step52b_EyeShapesEdgePatternAndConeOutline"
  "controls_gamepad_text|Assets/Scripts/Runtime/Hud.cs|controls.text = gamepad ? Strings.HudControlsGamepad : Strings.HudControls; // MUTATION:CONTROLS_GAMEPAD_TEXT|controls.text = gamepad ? Strings.HudControls : Strings.HudControlsGamepad; // MUTATION:CONTROLS_GAMEPAD_TEXT|PlayMode|Step52b_EyeShapesEdgePatternAndConeOutline"
  "door_memory|Assets/Scripts/Core/DoorMemory.cs|if (open[leaf] == isOpen) // MUTATION:DOOR_MEMORY|if (leaf >= 0) // MUTATION:DOOR_MEMORY|EditMode|DoorMemory_remembers_the_authored_leaves_and_a_mismatch_is_one_suspect"
  "wardrobe_fit|Assets/Scripts/Core/LevelDefM5.cs|bool narrow = size.x <= Tuning.WardrobeFitWidth + Eps && size.z <= Tuning.WardrobeFitWidth + Eps; // MUTATION:WARDROBE_FIT|bool narrow = true; // MUTATION:WARDROBE_FIT|EditMode|Wardrobe_fits_the_stool_and_the_floor_lamp_only Wardrobe_entry_zone_is_the_strip_in_front_of_its_front_face"
  "empty_spot|Assets/Scripts/Core/FurnitureMemory.cs|if (blind) // MUTATION:EMPTY_SPOT|if (dt >= 0f) // MUTATION:EMPTY_SPOT|EditMode|Empty_spot_is_a_suspect_then_one_discovery_until_the_furniture_is_seen"
  "hidden_samples|Assets/Scripts/Runtime/Vision.cs|if (furniture.Hidden) // MUTATION:HIDDEN_SAMPLES|if (furniture.Hidden && furniture.Carried) // MUTATION:HIDDEN_SAMPLES|PlayMode|Step53a_"
  "muffled_creak|Assets/Scripts/Runtime/GameState.cs|float creakRadius = furniture.Hidden ? Tuning.CreakRadius * Tuning.WardrobeCreakFactor : Tuning.CreakRadius; // MUTATION:MUFFLED_CREAK|float creakRadius = Tuning.CreakRadius; // MUTATION:MUFFLED_CREAK|PlayMode|Step53b_"
  "door_suspect|Assets/Scripts/Runtime/GameState.cs|meters[i].AddDiscovery(); // MUTATION:DOOR_SUSPECT|DoorSuspectCount += 0; // MUTATION:DOOR_SUSPECT|PlayMode|Step54a_"
  "household_cross|Assets/Scripts/Runtime/GameState.cs|return distance <= DoorStopDistance(g, side); // MUTATION:HOUSEHOLD_CROSS|return distance < 0f; // MUTATION:HOUSEHOLD_CROSS|PlayMode|Step55a_"
  "door_stop|Assets/Scripts/Runtime/GameState.cs|routine.Hold(Tuning.InhabitantDoorStop); // MUTATION:DOOR_STOP|routine.Hold(0f); // MUTATION:DOOR_STOP|PlayMode|Step55a_"
  "audit_hide|Assets/Editor/LevelAudit.cs|w.HideFrom[k] = true; // MUTATION:AUDIT_HIDE|w.HideFrom[k] = false; // MUTATION:AUDIT_HIDE|Audit|test_m6_audit_wardrobe"
  "audit_inhab_door|Assets/Editor/LevelAudit.cs|bool opens = inhabitantDoors && w.HoldStep[l] >= 0; // MUTATION:AUDIT_INHAB_DOOR|bool opens = false; // MUTATION:AUDIT_INHAB_DOOR|Audit|test_m6_audit_inhabdoor"
  "audit_door_memory|Assets/Editor/LevelAudit.cs|bool remembered = w.DoorMemory; // MUTATION:AUDIT_DOOR_MEMORY|bool remembered = false; // MUTATION:AUDIT_DOOR_MEMORY|Audit|test_m6_audit_doormemory"
  "load_sway|Assets/Scripts/Runtime/GameState.cs|LoadView.SetTilt(CarryingLoad ? Load.SwayTiltLocal(furniture.Yaw) : Vector2.zero); // MUTATION:LOAD_SWAY|LoadView.SetTilt(CarryingLoad ? Load.SwayTilt : Vector2.zero); // MUTATION:LOAD_SWAY|PlayMode|Step44e_"
  "load_velocity|Assets/Scripts/Runtime/GameState.cs|Vector2 v = new Vector2(fv.x, fv.z); // MUTATION:LOAD_VELOCITY|Vector2 v = Vector2.zero; // MUTATION:LOAD_VELOCITY|PlayMode|Step44b_ Step44c_ Step44d_ Step44e_"
  "robot_turn_cap|Assets/Scripts/Runtime/Robot.cs|VisualYaw = Mathf.MoveTowardsAngle(VisualYaw, Yaw, Tuning.RobotTurnRate * dt); // MUTATION:ROBOT_TURN_CAP|VisualYaw = Yaw; // MUTATION:ROBOT_TURN_CAP|PlayMode|Step42w_"
  "clue_surface|Assets/Scripts/Runtime/LoadView.cs|bool fits = LiesOnOneSurface(floor, c, yaw, spread, out Vector3 rest, out Quaternion f); // MUTATION:CLUE_SURFACE|bool fits = LiesOnOneSurface(floor, c, yaw, spread, out Vector3 rest, out Quaternion f) && false; // MUTATION:CLUE_SURFACE|PlayMode|Step44x_"
  # M5 wave 5B.
  "hum_none|Assets/Scripts/Core/Hearing.cs|float hum = Tuning.RobotHumRadius; // MUTATION:HUM_NONE|float hum = -1f; // MUTATION:HUM_NONE|EditMode|The_hum_masks_a_hop_a_roll_and_a_click_within_2_5_m_only Topple_creak_crash_and_bark_are_never_masked"
  "hum_creak|Assets/Scripts/Core/Hearing.cs|return false; // MUTATION:HUM_CREAK|return kind == NoiseKind.Creak; // MUTATION:HUM_CREAK|EditMode|Topple_creak_crash_and_bark_are_never_masked"
  "load_fall|Assets/Scripts/Core/LoadBalance.cs|float threshold = Tuning.LoadFallDeltaV; // MUTATION:LOAD_FALL|float threshold = float.PositiveInfinity; // MUTATION:LOAD_FALL|EditMode|A_90_deg_turn_at_full_chair_speed_drops_the_load Any_full_speed_reversal_drops_the_load The_office_chair_full_start_and_full_glide_drop_the_load Careful_U_turns_of_the_stool_and_the_office_chair_drop_the_load The_fall_is_at_the_threshold_latched_until_reset_and_ratio_is_the_gauge"
  "load_window|Assets/Scripts/Core/LoadBalance.cs|double cutoff = time - Tuning.LoadWindow + 0.5 * dt; // MUTATION:LOAD_WINDOW|double cutoff = time - dt + 0.5 * dt; // MUTATION:LOAD_WINDOW|EditMode|DeltaV_compares_with_the_velocity_exactly_one_window_before A_90_deg_turn_at_full_chair_speed_drops_the_load Any_full_speed_reversal_drops_the_load"
  "motion_glide|Assets/Scripts/Core/MotionProfile.cs|bool glides = Bodies && Body.Glides; // MUTATION:MOTION_GLIDE|bool glides = false; // MUTATION:MOTION_GLIDE|EditMode|Stop_distance_and_slide_samples_per_body Office_chair_glides_when_braked_against_its_motion_then_drives_back Release_is_the_instant_stop_the_glide_or_the_tip"
  "motion_careful|Assets/Scripts/Core/MotionProfile.cs|return b.MaxSpeed * (careful && bodies ? Tuning.CarefulFactor : 1f); // MUTATION:MOTION_CAREFUL|return b.MaxSpeed; // MUTATION:MOTION_CAREFUL|EditMode|Straight_start_follows_the_body_table_full_and_careful Every_careful_straight_move_holds"
  "robot_reverse|Assets/Scripts/Core/RobotPath.cs|legs.Add(new Leg { T0 = at, S0 = ArcOn(leg, at), Dir = -leg.Dir }); // MUTATION:ROBOT_REVERSE|legs.Add(new Leg { T0 = at, S0 = ArcOn(leg, at), Dir = leg.Dir }); // MUTATION:ROBOT_REVERSE|EditMode|Reverse_travels_the_loop_backwards_from_where_it_is"
  "put_away|Assets/Scripts/Core/InhabitantRoutine.cs|JustPutAway = true; // MUTATION:PUT_AWAY|JustPutAway = false; // MUTATION:PUT_AWAY|EditMode|Put_away_walks_to_the_clue_faces_it_bends_for_0_6_s_and_resumes A_clue_within_reach_is_put_away_without_walking"
  "rocks_row|Assets/Scripts/Core/BodyDef.cs|Rocks = true, // MUTATION:ROCKS_ROW|Rocks = false, // MUTATION:ROCKS_ROW|EditMode|Rocking_chair_row_matches_the_contract_member_by_member Only_the_rocking_chair_rocks_and_every_kind_is_a_known_body"
  "cone_radial|Assets/Scripts/Runtime/VisionConeView.cs|int samples = floor.IsFlat ? 1 : Mathf.CeilToInt(Owner.Routine.ViewRange / Tuning.ConeRadialStep); // MUTATION:CONE_RADIAL|int samples = 1; // MUTATION:CONE_RADIAL|PlayMode|Step37w_ConeFollowsThePlatformTop"
  "fan_superset|Assets/Scripts/Runtime/VisionConeView.cs|bool lookingUp = eye.y < top; // MUTATION:FAN_SUPERSET|bool lookingUp = false; // MUTATION:FAN_SUPERSET|PlayMode|Step38w_DogFanCoversWhatItSees"
  "robot_pose|Assets/Scripts/Runtime/Robot.cs|transform.SetPositionAndRotation(position, Quaternion.Euler(0f, yaw, 0f)); // MUTATION:ROBOT_POSE|transform.rotation = Quaternion.Euler(0f, yaw, 0f); // MUTATION:ROBOT_POSE|PlayMode|Step42w_RobotVisualFollowsSetPoseWithoutCollider"
  "load_hide|Assets/Scripts/Runtime/LoadView.cs|Carried.gameObject.SetActive(false); // MUTATION:LOAD_HIDE|Carried.gameObject.SetActive(true); // MUTATION:LOAD_HIDE|PlayMode|Step44w_LoadSitsOnTopTiltsAndBreaks"
  "robot_count|Assets/Scripts/Core/LevelValidator.cs|issues.Add(\$\"{level.Robots.Count} robots: at most one per level\"); // MUTATION:ROBOT_COUNT|{ } // MUTATION:ROBOT_COUNT|EditMode|At_most_one_robot_per_level"
  "robot_walls|Assets/Scripts/Core/LevelValidator.cs|if (!SegmentCovered(free, a, b)) // MUTATION:ROBOT_WALLS|if (false) // MUTATION:ROBOT_WALLS|EditMode|Robot_loop_runs_into_no_wall_and_never_leaves_the_house House_robot_fixture_crosses_a_doorway_without_a_leaf"
  "robot_floor|Assets/Scripts/Core/LevelValidator.cs|issues.Add(\$\"{segment} leaves the floor level: it touches platform {pf.Name}\"); // MUTATION:ROBOT_FLOOR|{ } // MUTATION:ROBOT_FLOOR|EditMode|Robot_loop_stays_on_the_floor_level"
  "robot_sector|Assets/Scripts/Core/LevelValidator.cs|issues.Add(\$\"{segment} enters the swing sector of door {k + 1} ({door.Id})\"); // MUTATION:ROBOT_SECTOR|{ } // MUTATION:ROBOT_SECTOR|EditMode|Robot_loop_stays_out_of_leaf_swing_sectors_and_off_the_leaf Robot_loop_runs_into_no_wall_and_never_leaves_the_house"
  "robot_clearance|Assets/Scripts/Core/LevelValidator.cs|issues.Add(\$\"{label} passes {d:0.##} m from the player spawn: at least {clearance} m\"); // MUTATION:ROBOT_CLEARANCE|{ } // MUTATION:ROBOT_CLEARANCE|EditMode|Robot_loop_keeps_one_metre_from_the_spawn_the_seat_homes_and_the_exit"
  "rocking_load|Assets/Scripts/Core/LevelValidator.cs|issues.Add(\$\"player load '{load}' on the {body.Kind}: the rocking chair carries no load\"); // MUTATION:ROCKING_LOAD|{ } // MUTATION:ROCKING_LOAD|EditMode|No_load_on_the_rocking_chair"
  "lesson_final|Assets/Scripts/Core/LevelValidator.cs|if (mechanics.Count < FinalMechanics) // MUTATION:LESSON_FINAL|if (mechanics.Count < 1) // MUTATION:LESSON_FINAL|EditMode|Lesson_final_needs_three_mechanics_and_mechanics_are_listed_in_order"
  "shelf_combine|Assets/Scripts/Runtime/FurnitureKit.cs|var parts = new PartBatch(p, layer, combine && visual); // MUTATION:SHELF_COMBINE|var parts = new PartBatch(p, layer, false); // MUTATION:SHELF_COMBINE|PlayMode|Step39h_CombinedRenderersKeepCollidersMaterialsAndFades"
  "face_plane|Assets/Scripts/Runtime/LevelBuilder.cs|FaceScope, \"Face\", fader, frame.position, normal); // MUTATION:FACE_PLANE|FaceScope, \"Face\", fader, wall.TransformPoint(faceCenter), frame.TransformDirection(new Vector3(0f, 0f, f.Side))); // MUTATION:FACE_PLANE|PlayMode|Step39h_CombinedRenderersKeepCollidersMaterialsAndFades"
  "robot_build|Assets/Scripts/Runtime/LevelBuilder.cs|level.Robots.Add(Robot.Create(robotDef, root)); // MUTATION:ROBOT_BUILD|Robot.Create(robotDef, root); // MUTATION:ROBOT_BUILD|PlayMode|Step39l_"
  "load_target|Assets/Scripts/Runtime/LevelBuilder.cs|return body.Size.y - Tuning.SampleInset + load; // MUTATION:LOAD_TARGET|return body.Size.y - Tuning.SampleInset; // MUTATION:LOAD_TARGET|PlayMode|Step39l_"
  "load_build|Assets/Scripts/Runtime/LevelBuilder.cs|level.LoadView = ApplyLoad(furniture, spawn.Load); // MUTATION:LOAD_BUILD|level.LoadView = null; // MUTATION:LOAD_BUILD|PlayMode|Step39l_"
  "game_hum_none|Assets/Scripts/Runtime/GameState.cs|bool masked = Hearing.IsMasked(heard, at, robotPositions); // MUTATION:GAME_HUM_NONE|bool masked = false; // MUTATION:GAME_HUM_NONE|PlayMode|Step42f_"
  "game_hum_creak|Assets/Scripts/Runtime/GameState.cs|NoiseKind heard = kind; // MUTATION:GAME_HUM_CREAK|NoiseKind heard = NoiseKind.Hop; // MUTATION:GAME_HUM_CREAK|PlayMode|Step42f_"
  "robot_contact|Assets/Scripts/Runtime/GameState.cs|bool touching = RobotPath.Overlaps(at, furniture.Pose, furniture.SampleSize); // MUTATION:ROBOT_CONTACT|bool touching = false; // MUTATION:ROBOT_CONTACT|PlayMode|Step42b_ Step42c_ Step42d_ Step42e_"
  "rock_stop|Assets/Scripts/Runtime/GameState.cs|bool rocks = body != null && body.Rocks; // MUTATION:ROCK_STOP|bool rocks = false; // MUTATION:ROCK_STOP|PlayMode|Step43b_"
  "rock_careful|Assets/Scripts/Runtime/GameState.cs|float time = furniture.Careful ? Tuning.RockCarefulTime : Tuning.RockTime; // MUTATION:ROCK_CAREFUL|float time = Tuning.RockTime; // MUTATION:ROCK_CAREFUL|PlayMode|Step43b_"
  "clue_discovery|Assets/Scripts/Runtime/GameState.cs|meters[i].AddDiscovery(); // MUTATION:CLUE_DISCOVERY|meters[i].Step(0f); // MUTATION:CLUE_DISCOVERY|PlayMode|Step44c_"
  "load_box|Assets/Scripts/Runtime/Vision.cs|Vector3 box = furniture.SampleSize + Vector3.up * ExtraHeight; // MUTATION:LOAD_BOX|Vector3 box = furniture.SampleSize; // MUTATION:LOAD_BOX|PlayMode|Step44f_"
  "balance_red|Assets/Scripts/Runtime/Hud.cs|BalanceRed = visible && ratio > Tuning.BalanceWarning; // MUTATION:BALANCE_RED|BalanceRed = false; // MUTATION:BALANCE_RED|PlayMode|Step44e_"
  "push_free|Assets/Scripts/Runtime/FurnitureController.cs|bool free = !ActionActive && !Tipped && !Pinned && !Carried; // MUTATION:PUSH_FREE|bool free = true; // MUTATION:PUSH_FREE|PlayMode|Step42g_"
  "push_slide|Assets/Scripts/Runtime/FurnitureController.cs|Velocity = Action == BodyAction.Push ? pushVelocity : Vector3.zero; // MUTATION:PUSH_SLIDE|Velocity = Vector3.zero; // MUTATION:PUSH_SLIDE|PlayMode|Step42g_"
  "push_hop|Assets/Scripts/Runtime/FurnitureController.cs|hopping = !rolls && !ActionActive && MotionRule.IsMoving(PlanarSpeed, YawRate); // MUTATION:PUSH_HOP|hopping = !rolls && MotionRule.IsMoving(PlanarSpeed, YawRate); // MUTATION:PUSH_HOP|PlayMode|Step42g_"
  "push_still|Assets/Scripts/Runtime/FurnitureController.cs|Velocity = Vector3.zero; // MUTATION:PUSH_STILL|Velocity = pushVelocity; // MUTATION:PUSH_STILL|PlayMode|Step42g_ Step44g_"
  "push_block|Assets/Scripts/Runtime/FurnitureController.cs|if (Pushing && -Vector3.Dot(v / speed, n.normalized) > Tuning.PushBlockedDot) // MUTATION:PUSH_BLOCK|if (false) // MUTATION:PUSH_BLOCK|PlayMode|Step42g_"
  "ghost_slope|Assets/Scripts/Runtime/GhostView.cs|if (FurnitureController.RampFrame(CurrentFloor(), at, pose.Yaw, size, ref frame, ref lift)) // MUTATION:GHOST_SLOPE|if (false) // MUTATION:GHOST_SLOPE|PlayMode|Step39m_"
  "audit_hum|Assets/Editor/LevelAudit.cs|float reach = Tuning.RobotHumRadius - w.RobotTravel; // MUTATION:AUDIT_HUM|float reach = -1f; // MUTATION:AUDIT_HUM|Audit|test_robot"
  "audit_robot_contact|Assets/Editor/LevelAudit.cs|bool inside = YawMath.Planar(robot - (pa + ab * f)).magnitude < zone; // MUTATION:AUDIT_ROBOT_CONTACT|bool inside = false; // MUTATION:AUDIT_ROBOT_CONTACT|Audit|test_m5_levels_robotblock"
  "audit_rock|Assets/Editor/LevelAudit.cs|int rock = w.RockSamples; // MUTATION:AUDIT_ROCK|int rock = 0; // MUTATION:AUDIT_ROCK|Audit|test_rock"
  "audit_load|Assets/Editor/LevelAudit.cs|float threshold = Tuning.LoadFallDeltaV - LoadEpsilon; // MUTATION:AUDIT_LOAD|float threshold = float.MaxValue; // MUTATION:AUDIT_LOAD|Audit|test_load"
)

# Refuse to start on a tree that still holds a mutation (an interrupted run), and snapshot the sources.
for row in "${MUTATIONS[@]}"; do
  bars="${row//[^|]/}"
  if [ "${#bars}" -ne 5 ]; then
    echo "ECHEC ligne de mutation ${row%%|*} : ${#bars} separateurs '|' au lieu de 5"
    exit 2
  fi
  IFS='|' read -r id file marked replacement mode expected <<<"$row"
  # M5 5B.1 (CONTRACT_M5 19 B2): the killer field holds bare test-name prefixes (or audit ids) only, space
  # separated. Prose, commas or parentheses can never match a red name and would report a false survivor.
  case "$mode" in EditMode|PlayMode|Audit) ;; *) echo "ECHEC ligne de mutation $id : mode '$mode' inconnu"; exit 2 ;; esac
  read -r -a killers <<<"$expected"
  if [ "${#killers[@]}" -eq 0 ]; then
    echo "ECHEC ligne de mutation $id : aucun nom attendu"
    exit 2
  fi
  for name in "${killers[@]}"; do
    if ! [[ "$name" =~ ^[A-Za-z0-9_]+$ ]]; then
      echo "ECHEC ligne de mutation $id : nom attendu '$name' hors de [A-Za-z0-9_]"
      exit 2
    fi
  done
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
    # CONTRACT_M5 16.3: audit only what the killers name (fixtures start with test_, the rest are levels).
    fixtures=""; levels=""
    for name in $expected; do
      case "$name" in test_*) fixtures="${fixtures:+$fixtures,}$name" ;; *) levels="${levels:+$levels,}$name" ;; esac
    done
    flags=()
    if [ -n "$levels" ]; then flags+=(-auditLevels "$levels"); fi
    if [ -n "$fixtures" ]; then flags+=(-fixtures "$fixtures"); else flags+=(-skipFixtures); fi
    "$PROJECT/tools/unity.sh" run . --timeout 2400 -- -executeMethod OutOfSight.Editor.LevelAudit.RunBatch "${flags[@]}" -logFile "$RESULTS/$id.audit.log" >"$RESULTS/$id.log" 2>&1
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
