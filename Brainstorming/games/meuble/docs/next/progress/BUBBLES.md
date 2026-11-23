# BUBBLES progress (idea 7: comic speech bubbles over the inhabitants)

## State (2026-11-21)
- Code written, one compile-only Unity run (Build/BUBBLES.log): 0 error CS, "[Builder] Scripts compiled and project set up.", exit 0; the three .meta files were generated. No test run, no build (policy of the wave).
- Always on: no Options toggle (the Options page is shared with other agents of the wave; a row there is not trivial).

## What shows
- One screen space overlay canvas (sorting order 8: under the HUD at 10, the touch controls at 30, the menus at 50;
  over the world and the world space markers "?" "!" "z") with the HUD's CanvasScaler (1920 x 1080, match 0.5), so a
  bubble reads the same on PC and on a phone. A bubble is UI: a wall never hides it, whatever the walls option.
- Pool of 8 bubbles built once (SpeechBubbles.Init): cream rounded plate (ProceduralArt.Rounded, sliced), a small tail
  (a rotated square under the plate, slightly left of centre), one line in Hud.DisplayFont (DM Serif Display, 30 units),
  dark ink. Width fits the text (96 to 560 units). Pop in over 0.14 s, holds 2 s, fades over 0.35 s. Held while paused.
- Placed every LateUpdate at the projection of Inhabitant.BubbleAnchor (0.32 m above the marker's float, so it clears
  the "?" / "!"), clamped inside the screen; a robot's bubble points 0.5 m over its centre. Hidden when behind the camera.
- One bubble per speaker: a new line replaces the one up (and avoids repeating the same variant of the same kind).
- No per-bubble allocation: the text is the Strings table's own instance; Reactions builds its key index once.

## Triggers (Core.ReactionKind) and where they fire
| Kind | Where | Speaker |
| --- | --- | --- |
| NearMiss | SpeechBubbles.StepNearMiss, on GameState.FixedStepped: a cone saw the still furniture (not moving, carried, hidden or pinned) for 0.2 to 3 s with at least one Walking step in the sighting, then lost it while still still; the sighting that ends because the furniture moved raises nothing. Cooldown 10 s per inhabitant. Station glances (the sentinel's metronome) never count: no walking step. | the walker |
| Noticed | GameState.StepMemory, Observation.Discovery with the furniture visible | the discoverer |
| SpotEmpty | same, with the furniture hidden in a wardrobe | the discoverer |
| PutBack | GameState carry, JustPutDown | the carrier |
| SatOn | GameState.StepSitting, SitResult.OnPlayer | the sitter (Granny has her own) |
| DogBark | GameState.EmitBarks (each bark), the hold's start and each hold bark (every 0.8 s) | the dog |
| DogCall | GameState.StepDogHold when the human is sent | the called human |
| Caught | GameState.Lose, after StateChanged: the inhabitant the rule named (suspicion), else the first human that sees the furniture or a swinging leaf (FirstSeer) | the seer |
| DoorOpened | GameState.StepHouseholdDoors (openedByInhabitants) | the walker |
| RobotBump | GameState.Contact while playing (RobotBumped event) | the robot |

Mute: the title house (Menu.TitleOpen, LevelSelectOpen, CreditsOpen), any state other than Playing except the catch's
own line. StateChanged to Won or Caught clears every bubble (the Caught line is raised after the clear and survives).
A level change clears the pool and restarts the seeded sequence.

## Lines (Strings.cs, section "react.*" at the end of the table)
- Key: react.<kind>.<personality>.<n>, n from 1; 3 to 6 per group; 1 to 5 words; EN and FR; no em-dash.
- Per-personality voices (3 each for dreamer, watchful, hurried, granny, teen, tidy; 4 default): NearMiss, Noticed,
  PutBack, Caught = 4 kinds x 22 = 88 keys.
- Shared default-only (4 each): SpotEmpty, DogCall, DoorOpened = 12 keys. SatOn: default 4 + granny 4 = 8 keys.
- DogBark (dog, 4), RobotBump (robot, 3) = 7 keys.
- Total: 115 keys, 230 lines. A personality without a group for a kind says the default lines (Reactions.Keys fallback).

## Files
- New: Assets/Scripts/Core/Reactions.cs (ReactionKind, the key index, the seeded Pick), Assets/Scripts/Runtime/SpeechBubbles.cs
  (canvas, pool, placement, fade, near miss), Assets/Tests/PlayMode/ProbeTestsBubbles.cs (Step80a to Step80e, NOT RUN).
- Edited: Assets/Scripts/Core/Strings.cs (react.* section at the end of the table), Assets/Scripts/Runtime/Inhabitant.cs
  (BubbleLift, BubbleAnchor), Assets/Scripts/Runtime/GameState.cs (events Reacted and RobotBumped, React helper,
  FirstSeer, SpeechBubbles.Ensure(this) in Begin, one-line hooks at the eight sites above; every MUTATION marker kept).

## A VERIFIER
- Run ProbeTestsBubbles (Step80a to Step80e): never run. Step80c/d pin the main inhabitant and teleport the chair in front
  of it on the Boot level; the premise waits may need the level's geometry checked.
- Look: the bubble under the fail panel's dim (sorting 8 under the HUD's 10): the catch line may read dimmed; move the
  bubbles canvas above the HUD (order 11) if the product owner wants it bright, at the cost of overlapping the gauges.
- Near miss frequency in play (10 s cooldown, 0.2 to 3 s sighting with a walking step): tune NearMissCooldown if chatty, or
  if the loop walkers never trigger it (their cones may sweep in under 0.2 s at 1.7 m/s: lower NearMissMinSeen to 0.1).
- Font size 30 units on a 20:9 phone: check readability on device; the HUD's intro card uses 26 to 38.
- The dog's hold barks every 0.8 s each refresh the "WOUF !" bubble: the bubble stays up for the whole hold (wanted);
  check it does not fight the "!" marker visually (BubbleLift 0.32 m above the marker).
- DoorOpened fires on every household door, also for inhabitants far from the player: harmless, but may read as noise.
- .meta files for the three new .cs files: generated by the compile run; check they exist before any commit.
- ProbeTestsBubbles.cs line 135 was edited after the compile run (the em-dash check now uses (char)0x2014 so the file holds no em-dash character): trivial, but the next compile should confirm it.
