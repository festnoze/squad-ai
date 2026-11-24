# COHERENCE (2026-11-24): logical room furnishing and decor

Follow-up of DRESSING (docs/next/progress/DRESSING.md). Goal: the living rooms read as living rooms (a TV stand with its
TV facing the sofa, a coffee table in front of it, the small items on that table, the throw on the sofa back), the key
dish by the front door, the mug and the book together, never anything in a bathroom.

## Why the user saw no decor in level8 (card 8)

- Main cause: the Windows build played dated from 12:25, before DRESSING baked its library and edited the levels.
- Code paths checked, no other loss: `"decor"` and `"dress"` parse (Newtonsoft camel case); hosts resolve by prop name;
  `Resources/DressingLibrary.asset` holds its 12 meshes as sub-assets, `m_IsReadable: 1` (the combiner reads them in a
  player); they draw with the wall material that every level already uses (no extra shader to strip); the wall arrays
  hold 28 slices on every platform (Standalone keeps the 16384 default); no `UNITY_EDITOR` guard; the decor joins the
  floor renderer, which neither the ceiling (shown only below its height) nor the wall fader hides.
- Real design bug: the media console look on a `counter` (level8 MeubleTV, level12 Television) drew a bare walnut
  cabinet, no TV: only a `tv_unit` drew one. And both stands had yaw 0 against the south wall, so their front faced the
  wall, not the sofa. Exactly the "low cabinet that is neither a TV stand nor a TV" of the complaint.

## Code

- `LevelBuilderDressing.DressProp`: a counter or cabinet wearing `walnut_media_console` now carries the flat screen TV
  on its top (visual only, above the prop's unchanged colliders), centred in x, against the back, screen to the front.
- `DecorKinds`: `CarriesTopTv`, `TopTvScale`, `TopTvFootprint` (shared by the builder and the validator),
  `KeyDishMaxExitDistance` (4.5 m).
- `LevelValidator.CheckDecorSense`: no item in the TV on a console top; the key dish never on a TV stand and at most
  4.5 m from the exit; a remote only in a room with a TV.

## Per level (card / file)

| Card | File | Living room after COHERENCE |
|---|---|---|
| 5 | level5 | TV turned 180 (it faced the wall) and moved to x 1.5, centred on the sofa; coffee table between; magazines + remote on it, throw on the back |
| 6 | level6 | ADDED MeubleTV (counter 1.2x0.55x0.4, console + TV) on the north wall at (2.0, 1.75), facing the sofa; coffee table unchanged with magazines + remote |
| 8 | level8 | MeubleTV turned 180 (faced the wall), now with its TV; remote on its front strip; key dish removed (no furniture by the front door); book + mug stay on the kitchen table. No coffee table: the strip between sofa and TV is the hard route (z 1.25) and Paul's sit approach |
| 9 | level9 | unchanged layout (already right); mug added beside the book on the desk |
| 10 | level12 | Television turned 180, now with its TV; ADDED TableBasse (coffee table 1.0x0.42x0.45) at (7.25, 0.95); book, mug (moved from the kitchen table) and remote on it |
| 11 | level11 | coffee table kept; the remote (no TV in the room) replaced by a small pothos. No TV: the wall across the sofa holds the bookshelf Lea faces |
| 12 | level15 | ADDED TableBasse at (8.75, 5.15) and MeubleTV on the south wall at (8.75, 2.25) facing the sofa; remote on the coffee table |
| 14 | level14 | unchanged (skipped). A coffee table at (12.0, 3.225) plus a TV stand on the north wall (first at x 12.0: on ramp 2; then x 12.6, 1.1 wide) made the audit find no schedule (normal and difficile); both reverted |
| 15 | level18 | key dish moved to the Buffet's west end (by the exit), the frame to its east end |
| 16 | level17 | mug added beside the book on the desk. No TV or coffee table: the south wall in front of the sofa is Lea's station, the strip in front of the sofa her sit approach and second station |
| 18 | level19 | unchanged layout (already right); mug added beside the book on the dining table |
| menu | title_house | same as level15: TableBasse (8.75, 5.05), MeubleTV (8.3, 2.25, clear of the plant), remote |

Skipped, with the reason: card 1 (level1, the tutorial room: the sofa faces the window and the guard's loop), card 4
(level4: the strip in front of the sofa is the sit approach, the south wall carries the bench and the designer route),
card 17 (level25: a shop, the sofa is a showroom piece). Other cards have no sofa; their decor hosts were checked (frame on
desks, consoles, shelves; lamps on side tables, consoles, dressers; key dishes within 4.5 m of the exit).

## Audit

LevelAudit -writeRoutes, normal and difficile (Build/coherence_r2.log, r3, r4): 0 defect on level5, 6, 8, 9, 11, 12, 15,
17, 18, 19; level14 back to its own layout (r4). Budgets unchanged in materials (the looks share the wall material and the
level's one "Dressing" renderer): level6 62/120 dc 23/24 mat, level8 76/120 24/24, level12 95/160 22/32, level15 66/120
22/24, level19 118/160 28/32. title_house is not a playable level: the audit finds no schedule for it by nature (no
route, menu tour), its budgets 104/160 dc, 32/32 materials.

## Tests (written, not run)

- EditMode `--filter Dressing_`: levels now carry 2 to 6 items, the new looks are expected, the new validator rules have
  failing cases, `Dressing_TopTv_SitsAgainstTheBackOfTheConsole`.
- PlayMode `--filter Dressing_` (ProbeTestsDressing, unchanged).

## A VERIFIER

- In game, level8, 12, 6, 14, 15 and the menu house: the TV on the console top faces the sofa, its foot on the top.
- The TV on a console is visual only above the 0.55 to 0.6 m collider: an inhabitant can see through it (thin, against a
  wall); judge whether that reads wrong anywhere.
- level12: the coffee table is 0.28 m from the TV stand (the sit approach sets its place); judge the spacing.
- level8 has no coffee table: the remote stands in front of the TV on the console.
- level5's TV is a 0.6 m `tv_unit`: its TV is drawn inside the box, small (0.33 m), as before COHERENCE.
- title_house shows 32/32 materials in the audit: check the menu house has not gone over a cap with its two new looks.
- level14 still has no TV stand or coffee table: a later pass could try one of the two alone and re-audit.

## THROWFIX (2026-11-24): the sofa throw drapes over the backrest top

Report: in game the throw's fringes showed low, against the backrest, its plaid never on top.

Cause (measured, Build/throwfix.log): the placement maths was right (every throw is on a `kenney.sofa`, backrest on +z,
top 0.85 = sizeY, z 0.2625..0.45 measured by downward rays on the drawn mesh; the procedural sofa's backrest 0.24..0.45).
The throw mesh is the problem: it is folded over a rounded crest, a narrow cap 6 to 7 cm deep at its sides' gap. Its
crest on the top of a square backrest put the backrest's top corners 6 to 7 cm above the sheet: the backrest swallowed the
cap (three dots of crest showed through) and only the hanging sides and fringes stayed visible, low.

Fix (data driven):
- ModelCatalog.Entry.backrestTop and backrestSpan: a seat's backrest top (height, native z span), measured by
  ModelCatalogBuilder on the mesh vertices in the top 2 % of its height (Spec.Backrest, set on kenney.sofa).
- LevelBuilder.SofaBackrest: the drawn sofa's backrest in the host frame (centre z, thickness, top) through the model's
  box fit; the procedural sofa (or no measured backrest) uses DecorKinds.SofaBackDepth, which FurnitureKit.Sofa now
  builds from too. A backrest on -z turns the throw by 180 so yaw 0 still hangs the long side behind.
- LevelBuilder.DrapedThrow: the throw mesh laid over a square backrest of that thickness: the cap between the two faces
  flat 3.7 mm above the top (DecorKinds.ThrowClearance), each hanging side lifted by its first row beyond the face, so it
  hangs from the edge, outside it; a fold of a hanging side that reaches back under the top stays on its side, pushed out to the face (else its triangles tore up to the top). One mesh per thickness, cached. ThrowDepthScale now takes the backrest thickness.
- LevelValidator: the throw's footprint centre and its Z tolerance from DecorKinds.BackrestCentre(size) and
  SofaBackDepth (the procedural backrest; the Kenney one is within 2 cm). Side unchanged (+z).

Shots: Editor/ThrowShots.cs (`-executeMethod OutOfSight.Editor.ThrowShots.Shoot`), Build/shots/throw/
(level5, 8, 11, 4, 6, title_house and level5 with a procedural sofa; seat, profile, back and game views).

Tests (written before, not run): EditMode and PlayMode `--filter Dressing_` (ProbeTestsDressing checks the throw's top
at the host top + 3.7 mm, which the drape keeps).

A VERIFIER: in game, the long side's folds leave two thin slivers where they meet the top edge (Build/shots/throw/*_back.png); level4's throw (yaw 180) hangs its long side on the seat side, as its data asks. Windows build not run (an OutOfSight process was running).
