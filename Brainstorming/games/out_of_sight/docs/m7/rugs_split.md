# Rug split investigation (long carpets vs the single-image stretch)

Product owner's request (2026-11-18/19): on levels with very long carpets, replace the one rug
image with several smaller rugs and a small gap, so `rug_modern_inset_border.png` does not stretch
as much. This note records what was found, what was tried, and why every rug ended up unchanged.

## 1. The image and the rug pipeline

`Assets/Art/Environment/rug_modern_inset_border.png` is 1536 x 1024 px, aspect ratio 1.5 (3:2). Every
rug (`LevelBuilder.BuildRug` / `BuildRugImage`) draws this image once, stretched to exactly
`sizeX` x `sizeZ` with no rotation: `sizeX` maps to the image's width, `sizeZ` to its height. A rug
whose `sizeX`/`sizeZ` ratio departs from 1.5 (or its reciprocal) shows visible stretch.

Threshold used to flag a rug: `max(sizeX,sizeZ)/min(sizeX,sizeZ) > 2.25` (1.5x the image's own 1.5
aspect, per the request).

## 2. What rugs do for gameplay (checked before touching anything)

A rug is a **silent floor area** (PRD 4.5, `docs/CONTRACT_M2.md` 3.2, `RugDef` in
`Assets/Scripts/Core/LevelDef.cs`): `LevelDef.IsSilentFloor(point)` returns true when `point` is
inside *any* `RugDef.Contains` box (an OR over every rug entry), or inside a room with a soft floor.
This flag gates every furniture noise (`CONTRACT_M4` 10.6: hop, topple, click, roll are silent on a
rug) through `GameState.floorSilent` (checked every physics step from the furniture's live position)
and through the level audit's `Heard()` and route-diagnostics (`Assets/Editor/LevelAudit.cs`). Rugs
have no collider and never affect movement/pathing, only noise.

**Consequence:** splitting one `RugDef` into N `RugDef`s with real gaps between them removes
silence from the gap cells. Unlike a merely cosmetic change, this can change whether a level's
designer route is heard, and it can change how hard the level audit's own search has to work to
prove the level is still "always doable" (`CONTRACT_M7` 4.1: the audit must pass at Normal and at
Difficile).

## 3. Rugs over the threshold

Every `rugs` entry of every file in `Assets/Resources/Levels/*.json` was scanned. Three rugs, in two
levels, are over the 2.25 ratio:

| Level | Rug | x, z | sizeX x sizeZ | ratio |
|---|---|---|---|---|
| level2 | rug 1 (couloir) | 0, 1.55 | 5.2 x 0.8 | 6.50 |
| level22 | rug 1 (galerie) | 12, 10.95 | 15.0 x 1.2 | 12.50 |
| level22 | rug 2 (galerie_est) | 20.95, 6.5 | 1.2 x 9.0 | 7.50 |

Every other rug in the project (level2 rug 2, level3, level5, level9, level11, level14, level17,
level20, level23, level24) sits at or under 1.5 and was left alone, as the request only covers rugs
stretched more than that.

## 4. What was tried, and why it was reverted

### level2, rug 1 (couloir corridor)

Split into 4 equal pieces (1.21 x 0.8, three 0.12 m gaps, same yaw, same 5.2 m footprint). Compiled
clean, and the EditMode `LevelData*Tests` passed. But `Step20_DesignerRoutes` (PlayMode, the
exact-replay check of the shipped `designerRoute`) regressed from 0 discoveries / 0 alerts / 0
creaks to **1 discovery, 1 alert** at all three tested start offsets (-0.2 s, 0 s, +0.2 s).

Root cause: the level's inhabitant has a station at (0, 2.25), dwelling 7 s, only about 0.7 m from
the rug's centerline (z = 1.55). Furniture movement noise has a 2.0 m radius (`Tuning`, logged as
"bruit de deplacement 2.0 m"), which from that station covers every x inside roughly ±1.87 m of the
station, i.e. almost the whole rug. The chair crosses the corridor along that exact z for several
seconds during the dwell, so any gap anywhere along the rug's 5.2 m span sits inside the hearing
bubble for long enough to be heard, regardless of where the gap is placed. There is no gap position
that keeps this specific encounter silent, so the change is not gameplay-identical.

**Decision: reverted to the original single rug** (5.2 x 0.8, unchanged). Confirmed clean again
afterward (EditMode 172/172, `Step20_DesignerRoutes` 0/0/0 at all three offsets).

### level22, rugs 1 and 2 (galerie / galerie_est)

First pass: rug 1 split into 4 pieces (3.66 x 1.2) and rug 2 into 2 pieces (1.2 x 4.44). This blew
the house draw-call budget (166 of 160, `Step39h_CombinedRenderersKeepCollidersMaterialsAndFades`):
each added rug entry costs about 5-6 draw calls in practice (the `kenney.rug` model already uses 2
material slots per CONTRACT_M3_ASSETS.md, plus the image quad, plus whatever renderers the fallback
or model-fit path adds), well above the 3 initially assumed. Reduced to rug 1 x2 pieces (7.44 x 1.2)
and rug 2 x2 pieces (1.2 x 4.44, 4 rugs total): draw calls down to 153/160, and all of
`Step25_BudgetsWithModels`, `Step39h_...`, `Step22e_...`, `Step58b3_Level22RouteWinsNormal` and
`Step58b4_Level22RouteWinsDifficile` passed (the stored `designerRoute` and `designerRouteHard`
still replay with 0 discoveries/alerts/creaks).

However, `OutOfSight.Editor.LevelAudit.RunBatch` (the project's own exhaustive proof that a level is
"always doable", required by `CONTRACT_M7` 4.1 to pass at both Normal and Difficile) failed at
**Difficile**: `budget de l'audit epuise : une recherche cree plus de 40000000 noeuds
(Tuning.AuditSearchNodeCap) : aucun horaire n'est garanti`. The audit's own search ran out of its
40M-node budget before it could prove a schedule exists, even though the one specific stored route
still plays fine. To isolate the cause, rug 2 was reverted (kept rug 1's 2-piece split alone): the
exact same Difficile search-budget failure reproduced. Fragmenting either long rug's silence
footprint, even by a single 0.12 m gap, is enough to tip this already-complex 8-room, 3-inhabitant,
2-closed-door house over its audit search budget at Difficile. The real-time replay of the one saved
route still works, but the project's stronger "the audit can still prove it" guarantee does not, so
the change is not accepted as gameplay-identical.

**Decision: reverted both rugs to their original single pieces** (15.0 x 1.2 and 1.2 x 9.0,
unchanged).

## 5. Final result

No rug was changed in any level. The three rugs over the 2.25 stretch threshold were each split and
tested; each split provably changed gameplay (level2: a real discovery/alert regression in the exact
replay test; level22: the mandatory Normal+Difficile audit no longer completes within its search
budget, independent of which of the two rugs was split). Both were reverted to keep the rule "the
split must keep the gameplay identical" rather than ship a level that is weaker-proven or a level
whose shipped route gets caught.

| Level | Rug | Before | After |
|---|---|---|---|
| level2 | rug 1 (couloir) | 1 piece, 5.2 x 0.8 | unchanged (reverted) |
| level22 | rug 1 (galerie) | 1 piece, 15.0 x 1.2 | unchanged (reverted) |
| level22 | rug 2 (galerie_est) | 1 piece, 1.2 x 9.0 | unchanged (reverted) |

## 6. Budgets (final, unchanged state, PRD 7.4 v1.7)

Measured with `OutOfSight.Editor.LevelAudit.RunBatch -auditLevels level2,level22 -skipFixtures`
after the revert (matches the pre-task numbers exactly, since no rug content changed):

| Level | Draw calls (slots) | Materials | Renderers | Budget |
|---|---|---|---|---|
| level2 (2 rooms) | 62 / 120 | 16 / 24 | 52 | normal |
| level22 (8 rooms) | 143 / 160 | 28 / 32 | 114 | house |

Both pass `aucun defaut` at Normal and Difficile.

## 7. Verification performed

- Compile (`Builder.SetupAndCompile`): clean.
- EditMode: `LevelDataTests`, `LevelDataM2Tests`, `LevelDataM4Tests`, `LevelDataM5Tests` - 172/172
  passed on the final (reverted) data.
- PlayMode: `Step25_BudgetsWithModels`, `Step39h_CombinedRenderersKeepCollidersMaterialsAndFades`,
  `Step22e_DetailRepeatsAtItsTileInMetres`, `Step20_DesignerRoutes`,
  `Step58b3_Level22RouteWinsNormal`, `Step58b4_Level22RouteWinsDifficile` - all passed on the final
  data (6/6).
- `OutOfSight.Editor.LevelAudit.RunBatch -auditLevels level2,level22 -skipFixtures`: both levels
  `aucun defaut` at Normal and Difficile, budgets as in section 6.

No other level content was touched.
