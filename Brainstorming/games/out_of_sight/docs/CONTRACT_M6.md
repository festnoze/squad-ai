# CONTRACT M6 - "Finition" (PC)

Build contract for milestone M6 of [PRD.md](PRD.md) v1.9 (section 11, M6). The product owner moved the
mobile port to M7, so M6 is PC only. The PRD wins where this contract is silent; this contract wins
over the agent prompts. Budget: the product owner has few credits left, so every agent does the
smallest work that meets its items and the gate, with few Unity runs and short reports.

## 1. Scope

1. **Options** (PRD q5): an "Options" screen reachable from the main menu and the pause menu.
2. **Gamepad pass**: every action and every screen works with a gamepad alone.
3. **Accessibility**: the seen state is never conveyed by colour alone.
4. **Texture pass 2** (PRD M6, q28).
5. **The wardrobe** hiding prop (q12, q22).
6. **Door memory** (q19).
7. **Inhabitants opening doors** (q23).
8. **(Moved to M6b, section 5.)** Level 18 "L'armoire", which uses 5, 6 and 7, and the fix of the M5 levels 10, 13, 17 that the
   new audit wait rule rejects (the M6 gate includes every earlier gate).

## 2. Decisions (binding)

### 2.1 Options
- Three settings, saved in the save file (`SaveData`, new `options` object, `version` stays 1: a
  missing object means the defaults; old saves load unchanged):
  - **Sensibilité** of the camera, 0.25 to 2.0, step 0.25, default 1.0: multiplies the mouse and
    the right stick orbit rates.
  - **Volume**, 0 to 100 %, step 10, default 80 %: `AudioListener.volume`.
  - **Cône de vision**: "Toujours" (default) or "Jamais": hides the floor cones
    (`VisionConeView`), never the eye indicator or the screen edge pulse. Rules are unchanged.
- Applied at once, kept across levels and restarts, reset by "Par défaut".
- The editor, `--probe` and `--look` never read or write options (as the save).

### 2.2 Gamepad
- In play: left stick moves, right stick orbits, left trigger careful, X (buttonWest) the action
  key, Start pauses, B backs out of menus. Menus: D-pad or left stick moves the selection, A
  validates, B goes back. Every menu has a visible selection highlight and works without a mouse.
- Ctrl+F and F11 toggle full screen (Main.cs, the integrator's; never bind them to anything else).
- The controls line (hud.controls) shows the gamepad glyph names when the last input came from a
  gamepad, the keyboard names otherwise.

### 2.3 Accessibility
- Each eye indicator state (Closed, Suspicious, Seen) has a distinct **shape**, not only a colour:
  closed lid, half open with "?", wide open with "!".
- The seen-moving screen edge pulse also shows a **pattern** (a dashed or striped border) that the
  calm and suspicious states never show.
- The cone of an alerted watcher gets a dashed outline, not only a colour change.
- Checked: the states differ in grayscale luminance by at least 0.15 or by shape, asserted by a probe
  on the rendered HUD.

### 2.4 Texture pass 2
Per [M6_TEXTURES_RESEARCH.md](M6_TEXTURES_RESEARCH.md), same derivation as M4.2 (512 x 512 grayscale
detail, licence row in LICENSES.md, the file under `Assets/ThirdParty/Textures/ambientCG/`):
- garden: Grass001 (smoothness 0.2);
- player furniture: PaintedWood006C, glossy lacquer, smoothness 0.8, metallic 0 (q28 default); the
  player colour stays unique (PRD 7.2);
- metal parts (office chair frame, lamp pole and base, robot body): Metal009, smoothness 0.5,
  metallic 0.9;
- plastic (robot bumper): Plastic006, smoothness 0.55;
- leaves: Moss002; soil: Ground104;
- window pane: no texture, smoothness 0.95;
- wardrobe: Wood049 (reuse).
- New `Surface` values: Grass, Lacquer, Metal, Plastic, Foliage, Soil. The material caps of PRD 7.4
  (24 and 32) still hold on every level, checked by the probe and the audit.

### 2.5 The wardrobe
- A prop of kind `wardrobe`, 1.0 x 2.0 x 0.6 m (w x h x d), a full occluder, with a front.
- A player furniture whose footprint fits (as built: width and depth at most 0.40 m, height plus load at most 1.85 m,
  Tuning.WardrobeFitWidth and WardrobeFitHeight:
  the stool and the floor lamp) enters it with the action key, facing its front within 0.6 m: an
  action of 0.5 s (seen as moving, like a door), then it is **hidden**: no vision samples, no
  footsteps, it cannot move. The action key again leaves (0.5 s, seen as moving) in front of it.
- While hidden, the creak gauge still fills, but the creak's hearing radius is halved (muffled).
- A furniture hidden in the wardrobe is not "seen out of place", but an inhabitant with memory who
  sees its **remembered spot empty** (the remembered pose inside its view, the furniture not there)
  gets a Suspect, like a moved furniture seen (PRD 4.4), and investigates the spot.
- Strings: the prompt "E : se cacher" / "E : sortir" (gamepad "X : ...").

### 2.6 Door memory
- An inhabitant with `Personality.Memory` remembers each door leaf's state (open or closed) when it
  sees the leaf. Seeing a leaf in another state than remembered gives a Suspect (PRD 4.4 gain), and
  the inhabitant walks to the door and **puts it back** (the lamp pattern, CONTRACT_M5_v3 q19
  fallback), then resumes its routine. A door it changed itself updates its memory.
- Opt-in per level (`"doorMemory": true`), so levels 8 to 17 keep their audited behaviour unless
  the levels agent turns it on and re-audits.

### 2.7 Inhabitants opening doors
- An inhabitant whose walk crosses a closed leaf stops 0.6 s in front of it, opens it (the leaf
  swing of M5), walks through and **leaves it open**. Its plan uses the doorway area of that leaf.
- Opt-in per door (`"openedByInhabitants": true` on the door), default false: existing levels keep
  their routes.

### 2.8 Audit
- The audit models: the wardrobe as a hiding cell (unseen while hidden, the entry and exit actions
  seen as moving); doors opened by inhabitants (a leaf opens at the time the frozen walk reaches it);
  door memory, conservatively: a schedule may not leave a leaf in a state a memory watcher will see
  changed, unless the level's lesson needs it and the audit models the put back.
- Level 18 passes the audit with -writeRoutes and its Step45 replays win; levels 10, 13 and 17 pass
  the new wait rule (CONTRACT_M5 19 and 19.1: smallest data change; for level 10 the rock lesson).

## 3. Agents and file ownership

| Agent | Files |
|---|---|
| **textures** | `Runtime/TextureLibrary.cs`, `Editor/ModelCatalogBuilder.cs` (the texture library part), `Runtime/PrimitiveKit.cs`, `Runtime/Robot.cs` (materials), `Runtime/LoadView.cs` (materials), `Assets/ThirdParty/Textures/`, `docs/LICENSES.md`, `Tests/EditMode/LicenseTests.cs`, new `Tests/PlayMode/ProbeTestsM6Textures.cs`; shared with small Edits: `Runtime/LevelBuilder.cs` (garden, window), `Runtime/FurnitureKit.cs` (metal parts, player lacquer) |
| **options** | `Runtime/Menu.cs`, `Runtime/GamePause.cs`, `Runtime/SaveStore.cs`, `Core/SaveData.cs`, `Runtime/InputReader.cs`, `Runtime/OrbitCamera.cs`, `Runtime/VisionConeView.cs` (the hide switch and the alert outline), `Runtime/LevelSelect.cs`, new `Tests/EditMode/OptionsM6Tests.cs`, new `Tests/PlayMode/ProbeTestsM6Options.cs`; shared with small Edits: `Runtime/Hud.cs` (eye shapes, edge pattern, controls line), `Runtime/ProceduralArt.cs` (glyphs) |
| **gameplay** | `Runtime/GameState.cs`, `Runtime/Inhabitant.cs`, `Runtime/DoorLeaf.cs`, `Runtime/NavPlanner.cs`, `Runtime/FurnitureController.cs`, `Runtime/Vision.cs`, `Core/FurnitureMemory.cs`, `Core/InhabitantRoutine.cs`, `Core/LevelDef.cs`, `Core/LevelDefM5.cs`, `Core/LevelValidator.cs`, `Core/BodyDef.cs`, new `Core/DoorMemory.cs`, new `Tests/EditMode/CoreM6Tests.cs`, new `Tests/PlayMode/ProbeTestsM6Gameplay.cs`, fixtures `Resources/Levels/test_m6_gameplay_*.json`; shared with small Edits: `Runtime/LevelBuilder.cs` (the wardrobe), `Runtime/FurnitureKit.cs` (the wardrobe model), `Runtime/Hud.cs` (the hide prompt) |
| **audit** | `Editor/LevelAudit.cs`, fixtures `Resources/Levels/test_m6_audit_*.json` |
| **levels** | `Resources/Levels/*.json` (levels 1 to 18, levels.json), `Tests/PlayMode/ProbeTestsM5Levels.cs`, `Tests/PlayMode/RouteReplayer.cs`, new `Tests/PlayMode/ProbeTestsM6Levels.cs`, `Tests/EditMode/LevelDataM2Tests.cs` (manifest count) |
| **integrator** | `verify.sh`, `mutation.sh`, `tools/`, `Main.cs`, `Probe.cs`, docs (PRD, README, contracts) |

- `Core/Strings.cs` and `Core/Tuning.cs`: each agent adds only inside its own marked block at the
  end ("M6 <agent>"); never edit another block.
- Shared files: re-read before each Edit, small targeted Edits only, never rewrite the file.

## 4. Gate

The M6 gate is `./verify.sh` green (every M1 to M5 stage included) plus `./mutation.sh` with the M6
rows, plus: the built player check on PC (60 fps: median frame time under 16.6 ms on every level),
the options persisted across a restart of the player, and the probe shots of the new textures.

## 5. M6b (product owner, 2026-11-15)

M6 stops once texture pass 2 has landed. M6b takes what is left:
- level 18 "L'armoire" (1.8) and the fix of levels 10, 13 and 17 (2.8), by the levels agent, with the
  audit agent's brief in its report (docs/m6/audit.json);
- the RouteReplayer plays the route actions "hide" and "leave" (LevelAudit.RouteHide and RouteLeave:
  press E at "at" with the furniture still at (x, z));
- the M6 gate (section 4): verify, the M6 mutation rows from the agents' reports (docs/m6/*.json),
  the PRD and README notes.
- **Level 10 waiver** (integrator for the product owner, 2026-11-16, credits): no data change made the
  rock lesson bind without breaking the wait rule (six audits, a dog included). Level 10 sets
  `"lessonAdvisory": true`: the audit prints its lesson as a note, not a defect. Level 10 stays
  winnable and keeps its rocking chair. A real rock lesson waits for the improvement loop.
