# M3 assets shortlist - free CC0 low poly models

Status: scouting done on 2026-11-11, nothing imported into `Assets/`. Every
number below was read from the downloaded GLB files themselves (JSON chunk and
binary buffer), not from the website, unless a column says "site". Licences
were read on each model's own poly.pizza page on the same day.

Scope: PRD section 7 (assets, budgets 7.4) and milestones M3 (real furniture,
rigged inhabitant), M4 (six player furniture) and M5 (doors, a pet).

Files: the picks and alternates are in `ThirdParty_staging/poly.pizza/`
(see section 12), with `manifest.json` (sha256, source, licence, facts).

---

## 1. Summary

### 1.1 Recommended picks

All furniture picks come from one pack, Kenney "Furniture Kit" (CC0 1.0), so
the art style, the scale and the material palette are shared.

| Item | Pick | Tris | 400 budget | Why this one |
|---|---|---|---|---|
| Chair (reference) | Kenney Chair | 340 | fits (85%) | Classic wooden chair, one material, closest to the M1 silhouette |
| Stool | Kenney Bar Stool | 352 | fits (88%) | Round seat reads as "stool"; scale it down for the small, fast M4 stool |
| Armchair | Kenney Lounge Chair | 256 | fits (64%) | Unmistakable armchair; about 1.0 m tall at kit scale, so it hides a 0.9 m chair |
| Floor lamp | Kenney Lamp Round Floor | 152 | fits (38%) | Shade is a separate material ("lamp"), easy to swap to an emissive one for the on/off rule |
| Office chair | Kenney Desk Chair | 656 | **over (164%)** | Only CC0 wheeled office chair under 2 000 tris; needs a budget decision (section 8) |
| Wardrobe | Kenney Bookcase Closed Doors | 536 | **over (134%)** | Looks exactly like a wardrobe, and its two doors are separate nodes (hide-inside rule); needs a budget decision |
| Sofa | Kenney Lounge Sofa | 256 | fits (64%) | Same family as the armchair; fits the 2.0 x 0.85 x 0.9 m level 1 box |
| Bookshelf | Kenney Bookcase Open Low | 368 | fits (92%) | Only Kenney shelf under budget; a low (about 0.85 m) occluder like the sofa |
| Dining table | Kenney Table | 240 | fits (60%) | Plain rectangular table, one material, fits the 1.4 x 0.75 x 0.9 m box |
| Rug | Kenney Rug Rectangle | 56 | fits (14%) | Two materials (field and border), 56 tris |
| Doormat | Kenney Rug Square | 56 | fits (14%) | Same pack as the rug, scaled to 0.9 x 0.55 m and recoloured; "Rug Doormat" is 408 tris |
| Door | Kenney Doorway | 216 | fits (54%) | Frame and door leaf are separate nodes, so the leaf can swing (M5 doors) |
| Inhabitant A | Quaternius Man in Long Sleeves | 1 970 | fits (66% of 3 000), 31 bones | Casual adult, neutral style, fewest materials (5), Idle/Walk/Sitting clips |
| Inhabitant B | Quaternius Woman Casual | 2 776 | fits (93% of 3 000), 31 bones | Casual adult, **same rig and clip set** as A: one animator controller for both |
| Pet (M5) | Quaternius Shiba Inu | 1 950 | fits tris; **46 bones** | Faceted style matches the humans; Idle, Idle_2, Walk, Gallop, Eating |

### 1.2 What is missing

- **No CC0 office chair and no CC0 wardrobe under 400 tris** in a matching
  style. Kenney's are 656 and 536 tris. Decision needed (section 8).
- **No "surprised" and no "pick up" clip** in the recommended rig family
  (HumanArmature). A standalone Quaternius woman has PickUp/Sitting/SitIdle,
  but on a different 41-bone rig (section 6.4).
- **No CC0 cat in a matching style.** The only animated CC0 cats are a blocky
  "Cube World" cat and a blob monster head. The dog (Shiba Inu) is the pet
  pick.
- The Shiba Inu has 46 bones, over the 40-bone inhabitant budget, if that
  budget also applies to pets.

### 1.3 Biggest risks for the Unity import

1. **GLB only.** poly.pizza serves glTF binaries, not FBX, so M3 needs the UPM
   package `com.unity.cloud.gltfast` (already foreseen by PRD 7.1). It is not
   in `Packages/manifest.json` yet. The Kenney FBX originals are on kenney.nl,
   which answers 403 to scripted downloads (stated in the brief, not retried).
2. **Scale.** Kenney furniture is about 1/2.1 of real size (doorway 1.01 m).
   The Quaternius humans are 4.6 to 4.8 units tall, under an armature node at
   scale 100. The Shiba Inu is 3.1 units tall.
3. **Pivots.** Every Kenney model has its pivot on a corner of its bounding
   box, not at its centre.
4. **Red is taken.** Kenney's shared "carpet" material is red (0.88, 0.11,
   0.09). PRD 7.2 reserves red for the player furniture, so the props need a
   material remap.

Section 9 lists every import note.

---

## 2. How this was verified

- **Source.** poly.pizza only (scriptable, no login). Bundles listed through
  the site's own data: Kenney "Furniture Kit" (116 models, all CC0) and
  "Building Kit" (79, all CC0); Quaternius "Ultimate House Interior Pack",
  "Furniture Pack", "Animated Men Pack", "Animated Women Pack", "Ultimate
  Modular Men/Women Pack", "Animated Animal Pack", "Post Apocalypse Pack";
  plus CreativeTrio, Isa Lousberg, iPoly3D packs. Searches: chair, office
  chair, desk chair, stool, armchair, floor lamp, wardrobe, closet, cabinet,
  bookshelf, doormat, door, cat, kitten, dog, casual character, animated
  character, animated man, animated woman (2 to 4 result pages each).
- **Scale of the screening.** 100 GLBs downloaded and parsed (67 furniture,
  33 characters and pets), 34 kept in staging.
- **Rate.** At most one request per 1.1 s, generic User-Agent, no personal
  data.
- **Untrusted data.** Downloads went to `ThirdParty_staging/` only. Every
  script that reads them ran with `python -I`, and nothing from a download is
  executed.
- **What was parsed** (`tools/assets/glb_inspect.py`, stdlib only):
  - triangles: index count / 3 per primitive, summed over the mesh nodes of
    the scene;
  - meshes, materials (name, base colour, metallic), textures with their
    pixel size, vertex colours;
  - skins (bone count), animations (names, durations);
  - the extensions used: none on any pick;
  - **exact bounds**: every vertex transformed by its node's world matrix, or
    skinned with the joint matrices at rest for rigged models.
- **Facing** was derived from geometry: a seat faces away from its backrest,
  a human's toes are ahead of its shins, a dog's head is at its front.
- **Style** was checked on the site's preview images: contact sheets are in
  `ThirdParty_staging/poly.pizza/_previews/`.

The site's metadata is not reliable, which is why everything was measured:

- The "Ultimate Modular" characters are announced at 3 282 to 4 318 tris on
  their pages but are 5 240 to 7 276 tris in the GLB, with 62 bones.
- The page of Quaternius "Animated Woman" (`9kF7eTDbhO`) says
  `Animated: false`, yet the GLB holds 10 clips.

---

## 3. Reading the numbers

- **Units and axes.** Sizes and bounds are in glTF units (meant as meters),
  Y up. "Native size" is X x Y x Z before any scaling.
- **Kenney Furniture Kit.** Exported with obj2gltf, identity node transforms,
  flat-colour materials and no textures.
  - The whole kit shares one palette of material names: wood, carpet,
    carpetDarker, carpetBlue, metal, metalMedium, lamp.
  - Pivot on a box corner: x spans [-width, 0] and z spans [0, depth].
  - One uniform scale of about 2.1 brings the kit to real size (doorway 1.01
    becomes 2.12 m; table 0.33 becomes 0.69 m). Where the level defines a
    gameplay box (chair 0.45 x 0.90 x 0.45, sofa 2.0 x 0.85 x 0.9, table
    1.4 x 0.75 x 0.9, from `FurnitureController` and PRD 6.3), fit the model
    to the box instead (per-axis factors below).
- **Quaternius** (FBX2glTF exports). Each mesh node carries rotation -90
  degrees about X and scale 100 (Z-up source).
  - Furniture sits at about 2x real size (door 4.19 m, chair 1.77 m).
  - The Animated Men/Women humans are 4.64 to 4.84 units tall. Mesh vertices
    are authored at about 0.048, under `HumanArmature` at scale 100.
- **Facing** (in glTF space):
  - Kenney seats (chair, lounge chair, desk chair, sofa) face **-Z**: the
    backrest is on +Z.
  - Quaternius humans and dogs face **+Z**, which is the glTF convention.
  - glTFast mirrors the X axis to change handedness, so +Z should stay Unity
    forward. Confirm with one screenshot on the first import.

---

## 4. Player furniture (M4 list)

"Suggested scale" is for the pick only. A triple is a per-axis fit to the
gameplay box; a single number is a uniform scale.

| Item | Pick | Native size | Suggested scale | Result (m) |
|---|---|---|---|---|
| Chair | Chair `vHyrBYPBum` | 0.20 x 0.47 x 0.20 | (2.25, 1.91, 2.25) fit to the M1 box, or 1.91 uniform | 0.45 x 0.90 x 0.45 (uniform: 0.38 x 0.90 x 0.38) |
| Stool | Bar Stool `2do92chR2k` | 0.27 x 0.43 x 0.23 | 1.2 for a small stool (2.1 gives a bar stool) | 0.32 x 0.52 x 0.28 |
| Armchair | Lounge Chair `RY93lbAIFg` | 0.49 x 0.46 x 0.41 | 2.1 | 1.03 x 0.97 x 0.86 |
| Floor lamp | Lamp Round Floor `8LiDIfXVLi` | 0.15 x 0.86 x 0.18 | 2.1 | 0.32 x 1.81 x 0.37 |
| Office chair | Desk Chair `CKSz6PB1vO` | 0.34 x 0.61 x 0.31 | 1.65 | 0.55 x 1.00 x 0.52 |
| Wardrobe | Bookcase Closed Doors `6Z0Z91EvJw` | 0.40 x 0.85 x 0.25 | 2.2 | 0.88 x 1.87 x 0.55 outside; a 0.45 m chair should fit inside (check the inner depth on import) |

Candidate facts (Tris = from the GLB; Site tris = what the page claims):

#### Chair

| Status | Model (author) | Page | GLB | Licence read on page | Tris | Site tris | 400 budget | Materials / textures | Native size | Bounds min / max |
|---|---|---|---|---|---|---|---|---|---|---|
| **PICK** | Chair (Kenney) | [m/vHyrBYPBum](https://poly.pizza/m/vHyrBYPBum) | [fca1766a...glb](https://static.poly.pizza/fca1766a-cc7b-4e22-a60f-49689446bd46.glb) | CC0 1.0 / "Public Domain (CC0)" | 340 | 340 | fits (85%) | 1: wood; no texture | 0.20 x 0.47 x 0.20 | [-0.2, 0.0, 0.0] / [0.0, 0.47, 0.2] |
| alternate | Chair Cushion (Kenney) | [m/UMtt043myZ](https://poly.pizza/m/UMtt043myZ) | [8e2842d3...glb](https://static.poly.pizza/8e2842d3-cce7-4010-ba2d-f7acab26d1d9.glb) | CC0 1.0 / "Public Domain (CC0)" | 396 | 396 | fits (99%) | 2: wood, carpet; no texture | 0.20 x 0.46 x 0.20 | [-0.2, 0.0, 0.0] / [0.0, 0.46, 0.2] |
| screened | Chair Modern Cushion (Kenney) | [m/KuTg9Uw3QC](https://poly.pizza/m/KuTg9Uw3QC) | [2946053d...glb](https://static.poly.pizza/2946053d-9e0c-4629-8069-fce2b1e06c0c.glb) | CC0 1.0 | 184 | 184 | fits (46%) | 2: metal, carpetBlue; no texture | 0.20 x 0.46 x 0.20 | [-0.2, -0.0, 0.0] / [0.0, 0.46, 0.2] |
| screened | Chair Rounded (Kenney) | [m/o7i23ZgseY](https://poly.pizza/m/o7i23ZgseY) | [3b62877f...glb](https://static.poly.pizza/3b62877f-a791-43d9-8a3a-0e5cbc74a0c0.glb) | CC0 1.0 | 560 | 560 | over (140%) | 1: wood; no texture | 0.20 x 0.46 x 0.20 | [-0.2, 0.0, 0.0] / [0.0, 0.455, 0.2] |
| screened | Chair (Quaternius) | [m/iMNqRzPwwe](https://poly.pizza/m/iMNqRzPwwe) | [84ecc6a3...glb](https://static.poly.pizza/84ecc6a3-2751-4f50-912a-b9f4ff033d7a.glb) | CC0 1.0 | 216 | 216 | fits (54%) | 1: Wood; no texture | 0.76 x 1.77 x 0.83 | [-0.3809, -0.0033, -0.4446] / [0.3809, 1.7645, 0.3809] |
| screened | Chair (Quaternius) | [m/kLViSk9EhX](https://poly.pizza/m/kLViSk9EhX) | [b92206cb...glb](https://static.poly.pizza/b92206cb-3715-4d6e-9cef-c682b93a2018.glb) | CC0 1.0 | 736 | 736 | over (184%) | 2: Wood, Cushing; no texture | 0.51 x 1.07 x 0.63 | [-0.2536, -0.0066, -0.3655] / [0.2536, 1.0598, 0.2667] |

#### Stool

| Status | Model (author) | Page | GLB | Licence read on page | Tris | Site tris | 400 budget | Materials / textures | Native size | Bounds min / max |
|---|---|---|---|---|---|---|---|---|---|---|
| **PICK** | Bar Stool (Kenney) | [m/2do92chR2k](https://poly.pizza/m/2do92chR2k) | [92b747ab...glb](https://static.poly.pizza/92b747ab-ed11-47f4-bcfb-a218b0b7e439.glb) | CC0 1.0 / "Public Domain (CC0)" | 352 | 352 | fits (88%) | 2: wood, carpet; no texture | 0.27 x 0.43 x 0.23 | [-0.2654, 0.0, 0.0] / [0.0, 0.435, 0.2299] |
| alternate | Stool Bar Square (Kenney) | [m/2EwBIClO8u](https://poly.pizza/m/2EwBIClO8u) | [fea46325...glb](https://static.poly.pizza/fea46325-5200-445c-8c65-7c1145a5158c.glb) | CC0 1.0 / "Public Domain (CC0)" | 284 | 284 | fits (71%) | 2: wood, carpet; no texture | 0.15 x 0.41 x 0.15 | [-0.2095, 0.0, 0.0411] / [-0.056, 0.405, 0.1888] |
| screened | Stool (Quaternius) | [m/TvaOenUAni](https://poly.pizza/m/TvaOenUAni) | [6ee9a20a...glb](https://static.poly.pizza/6ee9a20a-99f8-4c05-a30c-248b102a16ec.glb) | CC0 1.0 | 500 | 452 | over (125%) | 2: Wood, Cushin; no texture | 0.68 x 1.37 x 0.71 | [-0.3376, -0.0089, -0.355] / [0.3377, 1.3634, 0.355] |
| screened | Stool (Quaternius) | [m/9QpPhjLcMV](https://poly.pizza/m/9QpPhjLcMV) | [50ac9812...glb](https://static.poly.pizza/50ac9812-3998-4b82-94c7-b45e2999ab76.glb) | CC0 1.0 | 524 | 524 | over (131%) | 2: Wood, Cushing; no texture | 0.51 x 0.58 x 0.53 | [-0.2536, -0.0066, -0.2667] / [0.2536, 0.5703, 0.2667] |
| screened | Stool (CreativeTrio) | [m/VZw6xzQbOb](https://poly.pizza/m/VZw6xzQbOb) | [9e6e2670...glb](https://static.poly.pizza/9e6e2670-441d-46c5-95b6-a384111a5d5a.glb) | CC0 1.0 | 610 | 610 | over (152%) | 1: Material; tex 128x128 | 0.21 x 0.36 x 0.21 | [-0.1063, 0.0, -0.1064] / [0.1064, 0.3619, 0.1064] |

#### Armchair

| Status | Model (author) | Page | GLB | Licence read on page | Tris | Site tris | 400 budget | Materials / textures | Native size | Bounds min / max |
|---|---|---|---|---|---|---|---|---|---|---|
| **PICK** | Lounge Chair (Kenney) | [m/RY93lbAIFg](https://poly.pizza/m/RY93lbAIFg) | [21d3c956...glb](https://static.poly.pizza/21d3c956-0747-422c-b06d-6d4392380384.glb) | CC0 1.0 / "Public Domain (CC0)" | 256 | 256 | fits (64%) | 2: carpet, wood; no texture | 0.49 x 0.46 x 0.41 | [-0.49, 0.0, 0.0] / [0.0, 0.46, 0.41] |
| alternate | Lounge Chair "relax", with footrest (Kenney) | [m/PImRvMqW1O](https://poly.pizza/m/PImRvMqW1O) | [34b83c3a...glb](https://static.poly.pizza/34b83c3a-319d-413b-8b96-8f5980f29468.glb) | CC0 1.0 / "Public Domain (CC0)" | 376 | 376 | fits (94%) | 3: metal, carpet, wood; no texture | 0.49 x 0.63 x 0.67 | [-0.49, 0.0, 0.0] / [0.0, 0.63, 0.6747] |
| screened | Lounge Design Chair (Kenney) | [m/3ioSlOSyU8](https://poly.pizza/m/3ioSlOSyU8) | [36331876...glb](https://static.poly.pizza/36331876-a6da-4a91-9788-ac78650dd891.glb) | CC0 1.0 | 232 | 232 | fits (58%) | 2: carpetBlue, metal; no texture | 0.73 x 0.40 x 0.41 | [-0.7296, 0.0, 0.0] / [0.0, 0.4, 0.41] |
| screened | Armchair (CreativeTrio) | [m/myd1WSucAz](https://poly.pizza/m/myd1WSucAz) | [2584a961...glb](https://static.poly.pizza/2584a961-1b06-4fb7-ba7d-1074b52ca908.glb) | CC0 1.0 | 162 | 162 | fits (40%) | 1: Material; tex 128x128 | 0.59 x 0.72 x 0.54 | [-0.2223, -0.0, -0.3161] / [0.3659, 0.7162, 0.2223] |
| screened | Sofa Small (Quaternius) | [m/vRMLQC5Dfg](https://poly.pizza/m/vRMLQC5Dfg) | [00de7fa2...glb](https://static.poly.pizza/00de7fa2-1b21-44c8-afe9-fb35b9fde5d1.glb) | CC0 1.0 | 264 | 264 | fits (66%) | 1: Red; no texture | 2.03 x 1.32 x 1.46 | [-1.0127, -0.0038, -0.8857] / [1.0195, 1.3203, 0.5786] |

The alternate is taller (0.63 vs 0.46, so about 1.3 m at 2.1). Prefer it if
the armchair must hide more than the chair (M4 "blocks sight for anything
behind it").

#### Floor lamp

| Status | Model (author) | Page | GLB | Licence read on page | Tris | Site tris | 400 budget | Materials / textures | Native size | Bounds min / max |
|---|---|---|---|---|---|---|---|---|---|---|
| **PICK** | Lamp Round Floor (Kenney) | [m/8LiDIfXVLi](https://poly.pizza/m/8LiDIfXVLi) | [98dd45a1...glb](https://static.poly.pizza/98dd45a1-0682-4d44-83d1-32fa2a4fca5b.glb) | CC0 1.0 / "Public Domain (CC0)" | 152 | 152 | fits (38%) | 2: metal, lamp; no texture | 0.15 x 0.86 x 0.18 | [-0.136, 0.0, -0.0278] / [0.016, 0.86, 0.1478] |
| alternate | Lamp Square Floor (Kenney) | [m/YhhExKQQCs](https://poly.pizza/m/YhhExKQQCs) | [03fd9796...glb](https://static.poly.pizza/03fd9796-72b3-4bbe-b023-05092e4c2edb.glb) | CC0 1.0 / "Public Domain (CC0)" | 120 | 120 | fits (30%) | 2: lamp, metal; no texture | 0.12 x 0.86 x 0.12 | [-0.12, 0.0, 0.0] / [0.0, 0.86, 0.12] |
| screened | Light Floor (Quaternius) | [m/eBQtooeh43](https://poly.pizza/m/eBQtooeh43) | [19259c43...glb](https://static.poly.pizza/19259c43-99cb-43c6-aaee-dcf8d1d36fdb.glb) | CC0 1.0 | 226 | 166 | fits (56%) | 3: Grey, LightMetal, Light; no texture | 0.28 x 1.60 x 0.30 | [-0.1404, 0.0144, -0.1477] / [0.1404, 1.6177, 0.1477] |
| screened | Lamp With Shade (CreativeTrio) | [m/1nKtMmYxLT](https://poly.pizza/m/1nKtMmYxLT) | [cc9fbab2...glb](https://static.poly.pizza/cc9fbab2-f93f-4dfc-947b-b91f10a7b6bb.glb) | CC0 1.0 | 786 | 786 | over (196%) | 1: Material; tex 128x128 | 0.16 x 0.32 x 0.16 | [-0.0785, -0.0, -0.0785] / [0.0785, 0.3249, 0.0785] |

#### Office chair

| Status | Model (author) | Page | GLB | Licence read on page | Tris | Site tris | 400 budget | Materials / textures | Native size | Bounds min / max |
|---|---|---|---|---|---|---|---|---|---|---|
| **PICK** | Desk Chair (Kenney) | [m/CKSz6PB1vO](https://poly.pizza/m/CKSz6PB1vO) | [64699642...glb](https://static.poly.pizza/64699642-a4c2-4850-9c4b-558a328ed1bf.glb) | CC0 1.0 / "Public Domain (CC0)" | 656 | 656 | over (164%) | 2: metalMedium, carpet; no texture | 0.34 x 0.61 x 0.31 | [-0.335, 0.0, 0.0] / [0.0, 0.6076, 0.3143] |
| screened | Office Chair (Quaternius) | [m/UfKvrZBK6C](https://poly.pizza/m/UfKvrZBK6C) | [ac2301f3...glb](https://static.poly.pizza/ac2301f3-af86-435a-885a-d8f1a32f9f76.glb) | CC0 1.0 | 2116 | 2116 | over (529%) | 3: Grey, Black, Chair; no texture | 0.72 x 1.13 x 0.81 | [-0.3612, 0.0001, -0.4419] / [0.3605, 1.1277, 0.3653] |

The Desk Chair GLB has three mesh nodes (`chairDesk`, `chairDesk_1`,
`chair`). All other CC0 "office chair" results on poly.pizza were already
covered (searches "office chair" and "desk chair", 3 pages each).

#### Wardrobe

| Status | Model (author) | Page | GLB | Licence read on page | Tris | Site tris | 400 budget | Materials / textures | Native size | Bounds min / max |
|---|---|---|---|---|---|---|---|---|---|---|
| **PICK** | Bookcase Closed Doors (Kenney) | [m/6Z0Z91EvJw](https://poly.pizza/m/6Z0Z91EvJw) | [f2967462...glb](https://static.poly.pizza/f2967462-8f28-4977-aab4-8508eb23bf2c.glb) | CC0 1.0 / "Public Domain (CC0)" | 536 | 536 | over (134%) | 2: wood, metal; no texture | 0.40 x 0.85 x 0.25 | [-0.4, 0.0, 0.0] / [0.0, 0.85, 0.25] |
| screened | Cabinet (CreativeTrio) | [m/wOiMrnUuhe](https://poly.pizza/m/wOiMrnUuhe) | [57d9a5e8...glb](https://static.poly.pizza/57d9a5e8-3130-42eb-b436-28e1586facc0.glb) | CC0 1.0 | 324 | 324 | fits (81%) | 1: Material; tex 128x128 | 0.50 x 0.49 x 0.30 | [-0.248, 0.0, -0.2851] / [0.248, 0.4922, 0.0132] |
| screened | Dresser (CreativeTrio) | [m/Ud8QR8Ku9e](https://poly.pizza/m/Ud8QR8Ku9e) | [cc976603...glb](https://static.poly.pizza/cc976603-194e-4f9e-a017-c83273f6ff0f.glb) | CC0 1.0 | 430 | 430 | over (108%) | 1: Material; tex 128x128 | 1.03 x 0.63 x 0.33 | [-0.1714, -0.0, -0.1669] / [0.857, 0.6256, 0.1669] |
| screened | Closet (Quaternius) | [m/BHEVb1DIuH](https://poly.pizza/m/BHEVb1DIuH) | [87908291...glb](https://static.poly.pizza/87908291-7b01-45e9-90b9-fe41d63f511b.glb) | CC0 1.0 | 2988 | 2988 | over (747%) | 3: DarkWood, Metal, Wood; no texture | 1.55 x 2.98 x 0.87 | [-0.7769, -0.0079, -0.4302] / [0.7756, 2.9696, 0.4398] |
| screened | Short Closet (Quaternius) | [m/ND4Z53Ne4C](https://poly.pizza/m/ND4Z53Ne4C) | [9d3b575e...glb](https://static.poly.pizza/9d3b575e-1d1e-43b0-bdcc-186dfbbecfe7.glb) | CC0 1.0 | 4040 | 4040 | over (1010%) | 3: DarkWood, Metal, Wood; no texture | 1.55 x 2.27 x 0.91 | [-0.776, -0.0079, -0.4302] / [0.7765, 2.2588, 0.4766] |

The pick has four mesh nodes: `bookcaseClosedDoors`, `bookcaseClosedDoors_1`,
`doorLeft`, `doorRight`. The two CC0 models under budget are a low cabinet and
a dresser: neither is tall enough to be a full occluder or to hold a chair.

---

## 5. Props

| Item | Pick | Native size | Suggested scale | Result (m) |
|---|---|---|---|---|
| Sofa | Lounge Sofa `jMu2iCmGxU` | 0.98 x 0.46 x 0.41 | (2.04, 1.85, 2.20) fit to the level 1 box | 2.0 x 0.85 x 0.9 |
| Bookshelf | Bookcase Open Low `KRuVwg39aX` | 0.40 x 0.40 x 0.25 | 2.1 | 0.84 x 0.84 x 0.53 |
| Dining table | Table `41R2HTYj1O` | 0.84 x 0.33 x 0.45 | (1.66, 2.30, 2.01) fit to the level 1 box | 1.4 x 0.75 x 0.9 |
| Rug | Rug Rectangle `k5oJLb49gw` | 1.57 x 0.01 x 0.92 | 2.1, or fit to the rug's LevelDef size | 3.30 x 0.02 x 1.93 |
| Doormat | Rug Square `FiyXx0J6VB` | 0.90 x 0.01 x 0.92 | (1.0, 1.0, 0.6) | 0.90 x 0.01 x 0.55 |
| Door | Doorway `NjrIKzZLYv` | 0.49 x 1.01 x 0.11 | 2.1, or fit to the doorway width and `Top` | 1.02 x 2.12 x 0.24 |

#### Sofa

| Status | Model (author) | Page | GLB | Licence read on page | Tris | Site tris | 400 budget | Materials / textures | Native size | Bounds min / max |
|---|---|---|---|---|---|---|---|---|---|---|
| **PICK** | Lounge Sofa (Kenney) | [m/jMu2iCmGxU](https://poly.pizza/m/jMu2iCmGxU) | [f47310a0...glb](https://static.poly.pizza/f47310a0-4d22-48a3-a2ce-62f67bcc998d.glb) | CC0 1.0 / "Public Domain (CC0)" | 256 | 256 | fits (64%) | 2: carpet, wood; no texture | 0.98 x 0.46 x 0.41 | [-0.98, 0.0, 0.0] / [0.0, 0.46, 0.41] |
| alternate | Lounge Design Sofa (Kenney) | [m/xYNuGPF9wK](https://poly.pizza/m/xYNuGPF9wK) | [c9239576...glb](https://static.poly.pizza/c9239576-bf6c-4f2d-b706-ad8d92093161.glb) | CC0 1.0 / "Public Domain (CC0)" | 232 | 232 | fits (58%) | 2: carpetBlue, metal; no texture | 1.12 x 0.40 x 0.41 | [-1.12, 0.0, 0.0] / [0.0, 0.4, 0.41] |
| screened | Lounge Sofa Long (Kenney) | [m/gX7VhrgdIE](https://poly.pizza/m/gX7VhrgdIE) | [1b04ad72...glb](https://static.poly.pizza/1b04ad72-7896-4ba3-9003-46d6119bfd6e.glb) | CC0 1.0 | 372 | 372 | fits (93%) | 2: carpet, wood; no texture | 0.98 x 0.46 x 0.82 | [-0.98, 0.0, -0.41] / [0.0, 0.46, 0.41] |
| screened | Couch Medium (Quaternius) | [m/mWgQ94zhDZ](https://poly.pizza/m/mWgQ94zhDZ) | [92a2404e...glb](https://static.poly.pizza/92a2404e-10d5-4c6a-a188-18b556474f8f.glb) | CC0 1.0 | 1012 | 1012 | over (253%) | 2: Couch_Blue, Black; no texture | 4.69 x 1.91 x 2.20 | [-2.3441, -0.0131, -1.1835] / [2.3441, 1.8969, 1.02] |
| screened | Sofa (Quaternius) | [m/l84E3NzGSF](https://poly.pizza/m/l84E3NzGSF) | [fcf68889...glb](https://static.poly.pizza/fcf68889-d20f-4128-b8a9-4ae28556e819.glb) | CC0 1.0 | 2390 | 2390 | over (598%) | 2: Sofa, Legs; no texture | 4.24 x 1.51 x 1.78 | [-2.1205, -0.0076, -0.901] / [2.1205, 1.5002, 0.8826] |

#### Bookshelf

| Status | Model (author) | Page | GLB | Licence read on page | Tris | Site tris | 400 budget | Materials / textures | Native size | Bounds min / max |
|---|---|---|---|---|---|---|---|---|---|---|
| **PICK** | Bookcase Open Low (Kenney) | [m/KRuVwg39aX](https://poly.pizza/m/KRuVwg39aX) | [501665c0...glb](https://static.poly.pizza/501665c0-827b-4ad8-8c2a-0d2894c25857.glb) | CC0 1.0 / "Public Domain (CC0)" | 368 | 368 | fits (92%) | 1: wood; no texture | 0.40 x 0.40 x 0.25 | [-0.4, 0.0, 0.0] / [0.0, 0.4, 0.25] |
| alternate | Bookcase Open (Kenney) | [m/MTH8ZwnA27](https://poly.pizza/m/MTH8ZwnA27) | [867fee8d...glb](https://static.poly.pizza/867fee8d-2b89-4383-92f9-58660a76d29a.glb) | CC0 1.0 / "Public Domain (CC0)" | 640 | 640 | over (160%) | 1: wood; no texture | 0.40 x 0.88 x 0.25 | [-0.4, 0.0, 0.0] / [0.0, 0.88, 0.25] |
| screened | Bookcase Closed (Kenney) | [m/DO6AMMTYVI](https://poly.pizza/m/DO6AMMTYVI) | [fcdb70e0...glb](https://static.poly.pizza/fcdb70e0-cc38-4e91-9480-0e79f778e2a5.glb) | CC0 1.0 | 744 | 744 | over (186%) | 1: wood; no texture | 0.40 x 0.85 x 0.25 | [-0.4, 0.0, 0.0] / [0.0, 0.85, 0.25] |
| screened | Bookshelf (CreativeTrio) | [m/30Iealxb0p](https://poly.pizza/m/30Iealxb0p) | [0be37a0d...glb](https://static.poly.pizza/0be37a0d-0a0d-41db-b937-46773b53f02c.glb) | CC0 1.0 | 236 | 236 | fits (59%) | 1: Material; tex 128x128 | 0.57 x 1.32 x 0.15 | [-0.292, -0.0, -0.0771] / [0.2821, 1.3202, 0.0764] |
| screened | Bookcase with Books (Quaternius) | [m/tACDGJ4CGW](https://poly.pizza/m/tACDGJ4CGW) | [7d59d0aa...glb](https://static.poly.pizza/7d59d0aa-6447-4bbb-afc7-0452e9a34353.glb) | CC0 1.0 | 10948 | 10948 | over (2737%) | 11 materials; no texture | 1.84 x 3.37 x 0.66 | [-0.9167, -0.0182, -0.2865] / [0.9252, 3.3531, 0.3779] |

The tall Kenney bookcase (alternate) is open shelving: it is see-through, so
a tall occluder collider behind it would feel unfair. It is fine as a
non-blocking decoration.

#### Dining table

| Status | Model (author) | Page | GLB | Licence read on page | Tris | Site tris | 400 budget | Materials / textures | Native size | Bounds min / max |
|---|---|---|---|---|---|---|---|---|---|---|
| **PICK** | Table (Kenney) | [m/41R2HTYj1O](https://poly.pizza/m/41R2HTYj1O) | [b8daa8f9...glb](https://static.poly.pizza/b8daa8f9-78f0-4897-b22a-2561f804779e.glb) | CC0 1.0 / "Public Domain (CC0)" | 240 | 240 | fits (60%) | 1: wood; no texture | 0.84 x 0.33 x 0.45 | [-0.8415, 0.0, 0.0] / [0.0, 0.3267, 0.4474] |
| alternate | Table Cross Cloth (Kenney) | [m/VhhNCfQ8gj](https://poly.pizza/m/VhhNCfQ8gj) | [47200556...glb](https://static.poly.pizza/47200556-ca11-4dd9-abe8-caa673ccc452.glb) | CC0 1.0 / "Public Domain (CC0)" | 404 | 404 | over (101%) | 2: wood, carpet; no texture | 0.85 x 0.35 x 0.45 | [-0.8521, 0.0, 0.0] / [0.0, 0.3474, 0.4474] |
| screened | Table Cross (Kenney) | [m/wKoIHI7aZE](https://poly.pizza/m/wKoIHI7aZE) | [981ead6e...glb](https://static.poly.pizza/981ead6e-194a-4911-8ede-9b01de2d2ecb.glb) | CC0 1.0 | 356 | 356 | fits (89%) | 1: wood; no texture | 0.85 x 0.35 x 0.45 | [-0.8521, 0.0, 0.0] / [0.0, 0.3474, 0.4474] |
| screened | Table (Quaternius) | [m/gQFkiM8PlM](https://poly.pizza/m/gQFkiM8PlM) | [4353724c...glb](https://static.poly.pizza/4353724c-2da2-4eb3-b370-f93726a9fb89.glb) | CC0 1.0 | 1108 | 1108 | over (277%) | 2: DarkWood, Wood; no texture | 1.42 x 0.82 x 2.78 | [-0.7092, 0.0009, -1.3901] / [0.7092, 0.8253, 1.3901] |

#### Rug

| Status | Model (author) | Page | GLB | Licence read on page | Tris | Site tris | 400 budget | Materials / textures | Native size | Bounds min / max |
|---|---|---|---|---|---|---|---|---|---|---|
| **PICK** | Rug Rectangle (Kenney) | [m/k5oJLb49gw](https://poly.pizza/m/k5oJLb49gw) | [bbccb6a6...glb](https://static.poly.pizza/bbccb6a6-5194-41fa-9614-f02d01879496.glb) | CC0 1.0 / "Public Domain (CC0)" | 56 | 56 | fits (14%) | 2: carpet, carpetDarker; no texture | 1.57 x 0.01 x 0.92 | [-1.57, 0.0, 0.0] / [0.0, 0.01, 0.92] |
| alternate | Rug Rounded (Kenney) | [m/6RpHup9ZHp](https://poly.pizza/m/6RpHup9ZHp) | [8bc9a56c...glb](https://static.poly.pizza/8bc9a56c-7fc3-4aaa-9a97-a765a94b8287.glb) | CC0 1.0 / "Public Domain (CC0)" | 408 | 408 | over (102%) | 2: carpetDarker, carpet; no texture | 1.57 x 0.01 x 0.92 | [-1.57, 0.0, 0.0] / [0.0, 0.01, 0.92] |
| screened | Rug Round (Kenney) | [m/jeDDiN69Ze](https://poly.pizza/m/jeDDiN69Ze) | [06a5cc94...glb](https://static.poly.pizza/06a5cc94-d146-4ee6-8506-1be516dc4dbd.glb) | CC0 1.0 | 376 | 376 | fits (94%) | 2: carpet, carpetDarker; no texture | 0.92 x 0.01 x 0.92 | [-0.92, 0.0, 0.0] / [0.0, 0.01, 0.92] |
| screened | Rug (Quaternius) | [m/7H5qKjuxVY](https://poly.pizza/m/7H5qKjuxVY) | [93588780...glb](https://static.poly.pizza/93588780-3405-40b7-acb4-9a87c88569f6.glb) | CC0 1.0 | 108 | 108 | fits (27%) | 2: DarkRed, LightOrange; no texture | 2.13 x 0.04 x 3.09 | [-1.0582, -0.0009, -1.556] / [1.073, 0.0358, 1.5372] |

#### Doormat

| Status | Model (author) | Page | GLB | Licence read on page | Tris | Site tris | 400 budget | Materials / textures | Native size | Bounds min / max |
|---|---|---|---|---|---|---|---|---|---|---|
| **PICK** | Rug Square (Kenney) | [m/FiyXx0J6VB](https://poly.pizza/m/FiyXx0J6VB) | [b3cd980b...glb](https://static.poly.pizza/b3cd980b-cdca-471c-ab0f-124a47373d49.glb) | CC0 1.0 / "Public Domain (CC0)" | 56 | 56 | fits (14%) | 2: carpet, carpetDarker; no texture | 0.90 x 0.01 x 0.92 | [-0.9043, 0.0, 0.0] / [0.0, 0.01, 0.92] |
| alternate | Rug Doormat (Kenney) | [m/nwwFXS6B9T](https://poly.pizza/m/nwwFXS6B9T) | [65a09bc5...glb](https://static.poly.pizza/65a09bc5-89c5-4953-a60f-5acaaf02fbb7.glb) | CC0 1.0 / "Public Domain (CC0)" | 408 | 408 | over (102%) | 1: wood; no texture | 0.43 x 0.01 x 0.24 | [-0.4293, 0.0, 0.0] / [0.0, 0.01, 0.237] |
| screened | Doormat (Isa Lousberg) | [m/M2uWCZdX1Y](https://poly.pizza/m/M2uWCZdX1Y) | [a4dc7565...glb](https://static.poly.pizza/a4dc7565-b2c4-4a22-9f4f-23d71f7ae16e.glb) | CC0 1.0 | 180 | 180 | fits (45%) | 1: tiny_treats_1; tex 1024x1024 | 1.20 x 0.10 x 0.70 | [-0.6, -0.0, -0.35] / [0.6, 0.1, 0.35] |

#### Door

| Status | Model (author) | Page | GLB | Licence read on page | Tris | Site tris | 400 budget | Materials / textures | Native size | Bounds min / max |
|---|---|---|---|---|---|---|---|---|---|---|
| **PICK** | Doorway (Kenney) | [m/NjrIKzZLYv](https://poly.pizza/m/NjrIKzZLYv) | [f8349a23...glb](https://static.poly.pizza/f8349a23-d921-4903-9b2e-96e64f6c21ad.glb) | CC0 1.0 / "Public Domain (CC0)" | 216 | 216 | fits (54%) | 2: wood, metal; no texture | 0.49 x 1.01 x 0.11 | [-0.486, 0.0, -0.0121] / [0.0, 1.0095, 0.1013] |
| alternate | Wooden Door, Building Kit (Kenney) | [m/P09FqyST04](https://poly.pizza/m/P09FqyST04) | [16c02d69...glb](https://static.poly.pizza/16c02d69-21ae-49c2-bed1-6325570e356a.glb) | CC0 1.0 / "Public Domain (CC0)" | 240 | 204 | fits (60%) | 1: colormap; tex 512x512 | 0.25 x 2.10 x 0.93 | [-0.125, -0.0, -0.025] / [0.125, 2.1, 0.9] |
| screened | Doorway Front (Kenney) | [m/ZIueKgYj4i](https://poly.pizza/m/ZIueKgYj4i) | [b0659120...glb](https://static.poly.pizza/b0659120-e56c-472c-a418-d921178f23e2.glb) | CC0 1.0 | 184 | 184 | fits (46%) | 4: carpetWhite, metal, metalDark, glass; no texture | 0.49 x 1.01 x 0.11 | [-0.486, 0.0, -0.0121] / [0.0, 1.0095, 0.1013] |
| screened | Door (Quaternius) | [m/LI93WgnjyS](https://poly.pizza/m/LI93WgnjyS) | [df219d1d...glb](https://static.poly.pizza/df219d1d-2583-4082-b150-f7529527a63a.glb) | CC0 1.0 | 456 | 336 | over (114%) | 2: White, Metal; no texture | 1.74 x 4.19 x 0.42 | [-1.7358, -0.0, -0.2101] / [0.0, 4.1878, 0.2101] |

About the pick and the alternate:

- The pick's door leaf is the `door` node, but its vertices are baked in kit
  space: the node origin is (0, 0, 0), not the hinge. Swinging it needs a
  parent pivot placed on the hinge edge.
- The alternate is real scale with a hinge node (`door-rotate-square-c`) and
  12 node-animation clips (open, close, open-and-close for door and handle).
  But it uses a 512 px texture atlas and the Building Kit style.

---

## 6. Inhabitants

### 6.1 Recommendation

Use the **HumanArmature rig family** (Quaternius "Animated Men Pack" and
"Animated Women Pack", all CC0 1.0).

- All eight characters share the same 31-joint skeleton: identical joint
  names and parents (signature `27c1a493` in the screening).
- They share the same 11 clips with identical durations. Only the prefix
  differs: `HumanArmature|Man_<clip>` for the men, `HumanArmature|Female_<clip>`
  for the women.
- They are therefore interchangeable: one generic animator controller (bound
  by bone path) drives any of them, and M5's second inhabitant costs nothing.
- Visual check (`_previews/contact_sheet_characters.png`): adults in everyday
  clothes, neutral faces, no weapon meshes.

| Role | Model | Page | GLB | Tris | Bones | Materials | Height (glTF units) | Scale to 1.75 m |
|---|---|---|---|---|---|---|---|---|
| **Inhabitant A** | Man in Long Sleeves | [m/DLptRuewTn](https://poly.pizza/m/DLptRuewTn) | [e6019b9f...glb](https://static.poly.pizza/e6019b9f-aed0-400c-8df4-ce5b648e9b82.glb) | 1 970 | 31 | 5: Shirt, Pants, Eyes, Skin, Hair | 4.81 | 0.364 |
| **Inhabitant B** | Woman Casual | [m/jpKRgGDxhk](https://poly.pizza/m/jpKRgGDxhk) | [51d5abdd...glb](https://static.poly.pizza/51d5abdd-bb87-4b8d-9967-21738ffb8437.glb) | 2 776 | 31 | 8: Shirt, Skin, Pants, Shoes, Socks, HairBase, Hair, Eyes | 4.64 | 0.377 |
| same rig | Man in Suit | [m/mQnGoME1ez](https://poly.pizza/m/mQnGoME1ez) | [66b57880...glb](https://static.poly.pizza/66b57880-bcb0-479a-8d72-5c3e88afaa39.glb) | 2 058 | 31 | 7 | 4.83 | 0.362 |
| same rig | Man (t-shirt, shorts) | [m/HMnuH5geEG](https://poly.pizza/m/HMnuH5geEG) | [3746be88...glb](https://static.poly.pizza/3746be88-6799-4817-929b-6bc067c47caa.glb) | 1 852 | 31 | 6 | 4.83 | 0.362 |
| same rig | Man (t-shirt) | [m/fjHyMd5Wxw](https://poly.pizza/m/fjHyMd5Wxw) | [985eacbf...glb](https://static.poly.pizza/985eacbf-9dde-44b7-9270-4e35c8400b13.glb) | 1 854 | 31 | 9 | 4.84 | 0.361 |
| same rig | Woman (jacket) | [m/AQsd9ngvKU](https://poly.pizza/m/AQsd9ngvKU) | [906a0cbe...glb](https://static.poly.pizza/906a0cbe-b0a4-4312-b898-0f974b6f6771.glb) | 2 004 | 31 | 10 | 4.65 | 0.376 |
| same rig | Woman in Tank Top | [m/XqzeZGB7iU](https://poly.pizza/m/XqzeZGB7iU) | [9a6a3e55...glb](https://static.poly.pizza/9a6a3e55-23ce-4d5c-89bc-7d3f30307ed0.glb) | 1 983 | 31 | 7 | 4.65 | 0.376 |
| same rig | Woman in Dress | [m/zMyPlQXBzq](https://poly.pizza/m/zMyPlQXBzq) | [a642af96...glb](https://static.poly.pizza/a642af96-e239-4c5f-b50d-7661ff51deec.glb) | 1 786 | 31 | 5 | 4.65 | 0.376 |

Pairing choice:

- A has the fewest materials of the men (5).
- B is the only woman named "casual". "Woman in Dress" (1 786 tris, 5
  materials) is the leaner swap if the material budget gets tight.

### 6.2 Clips of the HumanArmature family (from the GLB)

| Clip (suffix) | Duration | Use in the game |
|---|---|---|
| Idle | 4.17 s | Idle, loop |
| Walk | 1.04 s | Routine walk, loop |
| Run | 0.88 s | Alerted or investigating, loop |
| Sitting | 8.33 s | M4 "inhabitants can sit" (sit down then sit) |
| Standing | 0.83 s | Stand up from sitting |
| Jump | 1.04 s | Best stand-in for "surprised" (startled hop) |
| Clapping | 1.67 s | Comedic "found you" or win-screen gag |
| RunningJump | 1.25 s | unused |
| Punch | 0.92 s | unused (combat) |
| SwordSlash | 1.04 s | unused (combat; no sword mesh in the file) |
| Death | 2.08 s | unused |

All clips animate rotation and translation only, with no scale tracks.

### 6.3 Missing clips

- **Surprised**: none. Fallbacks are the `Jump` clip, or a procedural head
  turn plus the existing telegraph.
- **Pick up / carry**: none in this family. The M2 carry-back can keep its
  current code-driven carry (the furniture parented at `CarryHeight`) with the
  Walk clip.

### 6.4 Alternate rig with PickUp and Sitting (single model)

Quaternius "Animated Woman" [m/9kF7eTDbhO](https://poly.pizza/m/9kF7eTDbhO),
CC0 1.0:

- 1 908 tris, **41 bones** (1 over budget).
- 1 material with a 32 x 32 palette texture.
- Clips: Idle 8.33 s, Walking 1.17 s, Running 0.67 s, **PickUp 5.96 s**,
  **Sitting 4.42 s**, **SitIdle 6.38 s**, Jump 2.58 s, Jump2 1.00 s, Punch
  1.00 s, Death 2.58 s.
- Its rig (`Armature`, signature `1c75c298`) matches no other model found,
  so it cannot share an animator with the HumanArmature family.
- Its page flag says "Animated: false", which is wrong.
- The geometry facing check read +X instead of +Z, so verify its orientation
  on import.
- Kept in `alternates/` for the PickUp clip.

### 6.5 Rejected humanoids (facts from the GLB)

| Model(s) | Why rejected |
|---|---|
| Ultimate Modular Men: Casual, Hoodie, Beach, Business Man, Farmer, Worker | 5 240 to 6 634 tris, 62 bones (site claims 3 350 to 4 318); clips include Gun_Shoot, Idle_Gun, Idle_Sword |
| Ultimate Modular Women, CC0 ones: Animated Woman x2, Punk, Hooded Adventurer | 5 956 to 7 276 tris, 62 bones; same gun/sword clip set |
| Ultimate Modular Women: Suit, Worker, Witch, Soldier, Sci Fi | **CC-BY 3.0** on their pages |
| Character Animated `DgOCW9ZCRJ` | 6 050 tris (site: 1 246), dagger clips |
| Anne `tZYaOQ4l94`, Characters Sam `UcLErL2W37` | 12 368 and 9 636 tris; Sam has gun clips |
| Animated Human `c3Ibh9I3udk` | 1 578 tris but a blank white mannequin, 41 bones |
| Fitness Character (iPoly3D) | no skin, no animation |

---

## 7. Pet (M5)

| Status | Model | Page | GLB | Licence | Tris | Bones | Clips | Materials | Size (glTF units) |
|---|---|---|---|---|---|---|---|---|---|
| **PICK** | Shiba Inu (Quaternius) | [m/y4wdQpg767](https://poly.pizza/m/y4wdQpg767) | [ba6d0ee3...glb](https://static.poly.pizza/ba6d0ee3-bcc0-4ef0-9d3c-a3e245b41c77.glb) | CC0 1.0 / "Public Domain (CC0)" | 1 950 | 46 | 12 distinct (stored twice, 24) | 6, no texture | 1.07 x 3.09 x 4.16 |
| alternate | Husky (Quaternius) | [m/wcWiuEqwzq](https://poly.pizza/m/wcWiuEqwzq) | [611d25c7...glb](https://static.poly.pizza/611d25c7-430f-4bb5-ab2c-d8f5f3cb9712.glb) | CC0 1.0 / "Public Domain (CC0)" | 1 920 | 49 | same 12 (stored twice, 24) | 5 (Material.00x), no texture | 0.99 x 3.19 x 3.89 |
| alternate (cat) | Cat, blocky (Quaternius) | [m/qKICY6xla2](https://poly.pizza/m/qKICY6xla2) | [67f5e3fe...glb](https://static.poly.pizza/67f5e3fe-37ee-4c86-95c8-d269d8c9f8ba.glb) | CC0 1.0 / "Public Domain (CC0)" | 2 448 | 16 | 8: Idle, Walk, Run, Idle_Eating, Headbutt, Jump_Start, Jump_Loop, Death | 1 atlas, tex 512x512, vertex colours | 1.31 x 1.87 x 2.16 |
| screened | Cat `2f54vbV0In` (Quaternius) | [m/2f54vbV0In](https://poly.pizza/m/2f54vbV0In) | | CC0 1.0 | 1 772 | 4 | 9 | 5 | a round blob monster head, not a pet cat |
| screened | Dog `2kUk0QqpCg` (Quaternius) | [m/2kUk0QqpCg](https://poly.pizza/m/2kUk0QqpCg) | | CC0 1.0 | 3 604 | 16 | 8 | 1 atlas, 512 px | blocky, over 3 000 tris |
| screened | Pug `1gXKv15ik8` (Quaternius) | [m/1gXKv15ik8](https://poly.pizza/m/1gXKv15ik8) | | CC0 1.0 | 644 | 24 | 2: Idle, Jump (no Walk) | 2 | |
| screened | Characters Pug `xvcUwuKl4c` (Quaternius) | [m/xvcUwuKl4c](https://poly.pizza/m/xvcUwuKl4c) | | **CC-BY 3.0** | 3 603 | 36 | 11 | 1 atlas, 512 px | |

Shiba Inu clips:

- Idle 3.33 s, Idle_2 3.33 s, Idle_2_HeadLow 4.00 s, Walk 1.04 s, Gallop
  0.54 s, Gallop_Jump 0.92 s, Jump_ToIdle 1.33 s, Eating 2.50 s, Attack
  1.33 s, Death 1.04 s, Idle_HitReact_Left/Right 0.67 s.
- Each clip exists twice, once plain and once prefixed `AnimalArmature|`,
  with slightly different Attack/Eating durations. Use one set.
- It faces +Z. Scale it by about 0.15 for a 0.45 m tall dog.

No CC0 animated cat exists in a matching style: among the 106 "cat" search
results, every cat model is CC-BY except the two Quaternius cats above. If M5 insists on a cat, the
blocky cat is the only CC0 option, and it clashes with the faceted humans.

---

## 8. Gaps and fallbacks

| Gap | Facts | Options (pick one in the PRD) |
|---|---|---|
| Office chair over budget | Best CC0: Kenney Desk Chair 656 tris (164%); next is 2 116 | (a) Budget exception for player furniture: a single instance per level, and the level total of 60 000 is unaffected. (b) Keep the procedural primitive for the office chair. (c) Decimate with headless Blender (PRD 7.1 fallback; needs a written need first) |
| Wardrobe over budget | Best CC0: Kenney Bookcase Closed Doors 536 tris (134%); the in-budget CC0 cabinets are too low to hold a chair | Same three options; (a) is the cheapest and keeps the openable doors |
| Tall bookshelf | Tall Kenney bookcases are 640 to 744 tris | Recommended low one fits (368); keep tall ones for later, with an exception |
| "Surprised" clip | Not in any recommended rig | Use `Jump`, or a procedural reaction |
| "Pick up" clip | Only in `9kF7eTDbhO` (different rig, 41 bones) | Keep the code-driven carry; or adopt that woman as a third, unique inhabitant |
| Cat | No CC0 animated cat in style | Dog (Shiba Inu) as the pet; blocky cat as last resort |
| Pet bones | Shiba Inu 46, Husky 49 (inhabitant budget is 40) | Accept for a pet (state it in 7.4), or strip the unused tail/ear bones later |

If any import fails or a budget decision says no, the **procedural primitive
stays as the fallback** for that item: PRD M3 already keeps primitives behind
the same `LevelDef`, with a `model` field that may be absent.

---

## 9. Unity import notes and risks

1. **Package.** Add `com.unity.cloud.gltfast` (Unity's glTF importer) before
   any GLB lands in `Assets/`. Verify the version against the registry (skill
   `unity-package-management`); none is pinned here on purpose. Without the
   package, Unity ignores `.glb` files silently.
2. **Built player.** Check a built player, not only the editor (lesson from
   VIEWPOINT Unity: a green editor says nothing about the build). glTFast
   materials use glTFast's own shader graphs. Remapping to the project's URP
   Lit materials at import (by name, see item 6) removes that question and
   also solves the material budget.
3. **Scale.** Apply one prefab scale per model, never per child.
   - Kenney: about 2.1 uniform, or fit to the LevelDef box (sections 4 and 5).
   - Humans: 0.364 (men) and 0.377 (women).
   - Shiba Inu: about 0.15.
   - The Quaternius armature nodes keep **scale 100**: anything parented to a
     bone (a carried chair, a hat) inherits it. Divide by the chain scale, as
     learned on CALL OF WAR.
4. **Pivots.** Kenney pivots sit on a box corner. Wrap each model in a parent
   and offset the child by minus its bounds centre (computed from renderer
   bounds at build time, not hard coded), so `x, z, yaw` in `LevelDef` keep
   meaning "centre of the footprint".
5. **Facing.** Kenney seats face -Z in glTF space, the humans and the dog +Z.
   Expect a 180 degree yaw on Kenney seats so the chair "front" matches the
   M1 primitive. Confirm on the first import with one screenshot.
6. **Materials (budget: 24 per level).** glTFast creates one material
   instance per material per file.
   - The 12 Kenney picks use only 6 distinct name and colour pairs (wood 8
     files, carpet 6, metal 3, carpetDarker 2, metalMedium 1, lamp 1). Remap
     by name to one shared palette, or the furniture alone spends 21
     materials.
   - Humans: 5 + 8 materials, dog 6. Near-black ones (Eyes, Shoes, Black,
     Eyes_Black, Eyes_Pupil) can share one material.
   - Estimate with sharing: furniture 6, player colour 1, two humans and the
     dog about 14, walls/floor/trim 3, for about 24. That fits M5, but only
     with sharing.
7. **Red is reserved** (PRD 7.2). Kenney "carpet" (0.88, 0.11, 0.09) appears
   on the armchair, sofa, stool cushion, desk chair, rug and doormat.
   Recolour those per prop, and keep red for the player furniture only.
8. **Metallic.** Quaternius materials have metallic 0.40 and roughness 0.42.
   With no reflection probe they render dark and dull in URP: set metallic to
   0. Their base colours are dark linear values, which suits the project's
   Linear colour space (`m_ActiveColorSpace: 1`).
9. **Lamp on/off** (PRD 4.7). The "lamp" material is a plain base colour
   (1, 0.82, 0.31) with no emission. Add an emissive variant, swapped when
   the lamp switches.
10. **Animation import.**
    - Import the clips as Mecanim generic clips; they bind by transform path.
    - glTF has no loop flag: set loop time on Idle, Walk, Run, SitIdle and
      the Shiba loops explicitly, and check it in a test (on CALL OF WAR in
      Godot every clip arrived non-looping).
    - Drop the duplicated `AnimalArmature|` clips of the dogs.
11. **Skinned bounds.** Quaternius skinned meshes are authored Z-up under a
    rotated, scaled node, so the imported bounds may not follow the walking
    pose. If an inhabitant pops out at screen edges, enlarge the
    SkinnedMeshRenderer bounds rather than turning on "update when
    offscreen" everywhere.
12. **Draw calls.** Each Kenney model is split into 2 to 4 mesh nodes (one
    per material plus moving parts), so 12 props make about 30 renderers.
    That is well under the 120 budget, and the SRP batcher handles it.
13. **Textures.** No pick has a texture. The textured ones are only the
    alternates: Building Kit door 512 px, blocky cat 512 px, alternate woman
    32 px.
14. **Git.** `games/meuble/` is untracked today. `ThirdParty_staging/` holds
    9.7 MB of binaries: decide whether it is committed, ignored, or emptied
    once the picks move into `Assets/`.

---

## 10. Licence evidence

Read on 2026-11-11, on each model's own page (`https://poly.pizza/m/<id>`),
in two places:

1. The page's embedded data, field `initialData.model.Licence`: every pick
   and alternate reads `"CC0 1.0"`.
2. The rendered page body: the licence label reads **"Public Domain (CC0)"**
   and links to `https://creativecommons.org/publicdomain/zero/1.0/`. This
   was captured for all 34 staged files (`licence_label_on_page` and
   `licence_link_on_page` in `manifest.json`).

Control (the check really discriminates): Quaternius "Suit"
[m/sOUciDsoVV](https://poly.pizza/m/sOUciDsoVV), from the same pack as CC0
characters, reads `"CC-BY 3.0"`, label "Creative Commons Attribution", link
`https://creativecommons.org/licenses/by/3.0/`. The licence is per model,
not per author.

Pack-level corroboration:

- The Kenney "Furniture Kit" bundle lists all 116 models as CC0 1.0, and the
  "Building Kit" all 79.
- The Quaternius "Animated Men Pack" (4) and "Animated Women Pack" (4) list
  all models as CC0 1.0, as does the "Animated Animal Pack" (12).
- The "Ultimate Modular Women Pack" is mixed: 5 CC0, 5 CC-BY 3.0.

| Pick | Page | State field | Label on page | Link on page |
|---|---|---|---|---|
| Kenney Chair | https://poly.pizza/m/vHyrBYPBum | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |
| Kenney Bar Stool | https://poly.pizza/m/2do92chR2k | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |
| Kenney Lounge Chair | https://poly.pizza/m/RY93lbAIFg | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |
| Kenney Lamp Round Floor | https://poly.pizza/m/8LiDIfXVLi | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |
| Kenney Desk Chair | https://poly.pizza/m/CKSz6PB1vO | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |
| Kenney Bookcase Closed Doors | https://poly.pizza/m/6Z0Z91EvJw | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |
| Kenney Lounge Sofa | https://poly.pizza/m/jMu2iCmGxU | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |
| Kenney Bookcase Open Low | https://poly.pizza/m/KRuVwg39aX | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |
| Kenney Table | https://poly.pizza/m/41R2HTYj1O | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |
| Kenney Rug Rectangle | https://poly.pizza/m/k5oJLb49gw | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |
| Kenney Rug Square | https://poly.pizza/m/FiyXx0J6VB | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |
| Kenney Doorway | https://poly.pizza/m/NjrIKzZLYv | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |
| Quaternius Man in Long Sleeves | https://poly.pizza/m/DLptRuewTn | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |
| Quaternius Woman Casual | https://poly.pizza/m/jpKRgGDxhk | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |
| Quaternius Shiba Inu | https://poly.pizza/m/y4wdQpg767 | CC0 1.0 | Public Domain (CC0) | creativecommons.org/publicdomain/zero/1.0/ |

CC0 needs no attribution. Crediting Kenney and Quaternius anyway is good
practice, and the M3 gate asks for the licence file regardless.

---

## 11. LICENSES draft (one line per recommended model)

```
Chair                  - Kenney     - https://poly.pizza/m/vHyrBYPBum - CC0 1.0 (Public Domain)
Bar Stool              - Kenney     - https://poly.pizza/m/2do92chR2k - CC0 1.0 (Public Domain)
Lounge Chair           - Kenney     - https://poly.pizza/m/RY93lbAIFg - CC0 1.0 (Public Domain)
Lamp Round Floor       - Kenney     - https://poly.pizza/m/8LiDIfXVLi - CC0 1.0 (Public Domain)
Desk Chair             - Kenney     - https://poly.pizza/m/CKSz6PB1vO - CC0 1.0 (Public Domain)
Bookcase Closed Doors  - Kenney     - https://poly.pizza/m/6Z0Z91EvJw - CC0 1.0 (Public Domain)
Lounge Sofa            - Kenney     - https://poly.pizza/m/jMu2iCmGxU - CC0 1.0 (Public Domain)
Bookcase Open Low      - Kenney     - https://poly.pizza/m/KRuVwg39aX - CC0 1.0 (Public Domain)
Table                  - Kenney     - https://poly.pizza/m/41R2HTYj1O - CC0 1.0 (Public Domain)
Rug Rectangle          - Kenney     - https://poly.pizza/m/k5oJLb49gw - CC0 1.0 (Public Domain)
Rug Square (doormat)   - Kenney     - https://poly.pizza/m/FiyXx0J6VB - CC0 1.0 (Public Domain)
Doorway                - Kenney     - https://poly.pizza/m/NjrIKzZLYv - CC0 1.0 (Public Domain)
Man in Long Sleeves    - Quaternius - https://poly.pizza/m/DLptRuewTn - CC0 1.0 (Public Domain)
Woman Casual           - Quaternius - https://poly.pizza/m/jpKRgGDxhk - CC0 1.0 (Public Domain)
Shiba Inu              - Quaternius - https://poly.pizza/m/y4wdQpg767 - CC0 1.0 (Public Domain)
```

Pack of origin, for the credits screen: Kenney "Furniture Kit"
(https://poly.pizza/bundle/Furniture-Kit-NoG1sEUD1z, also kenney.nl),
Quaternius "Animated Men Pack" and "Animated Women Pack"
(https://poly.pizza/bundle/Animated-Men-Pack-DAC9SDgMQT,
https://poly.pizza/bundle/Animated-Women-Pack-HHSKxnk1mY), Quaternius
"Animated Animal Pack" (https://poly.pizza/bundle/Animated-Animal-Pack-ILAPXeUYiS).

---

## 12. Staging content and reproduction

```
ThirdParty_staging/poly.pizza/
  manifest.json            34 entries: file, sha256, bytes, title, author, page, glb_url,
                           licence (state field, page label, page link), tris, bones,
                           materials, textures, animations, bounds
  picks/furniture/         12 GLBs, named <role>__<author>_<title>__<id>.glb
  picks/inhabitants/       2 GLBs (inhabitant_a, inhabitant_b)
  picks/pets/              1 GLB (pet_dog)
  alternates/furniture/    10 GLBs (the "two if close" second choices)
  alternates/inhabitants/  6 same-rig humans + the PickUp/Sit woman
  alternates/pets/         Husky, blocky cat
  _previews/               site preview images and two contact sheets (style check)
```

Tools (stdlib only, in `tools/assets/`):

- `polypizza.py` - polite fetcher (1.1 s between requests).
  Subcommands: `bundle`, `search`, `model` (licence state field, page label,
  page link, GLB URL), `download` (sha256).
- `glb_inspect.py` - GLB facts: tris, materials, textures, skins, clips,
  exact skinned bounds, extensions.

```
python -I tools/assets/polypizza.py model vHyrBYPBum --out facts.json
python -I tools/assets/polypizza.py download vHyrBYPBum --dest ThirdParty_staging/poly.pizza/check --facts facts.json
python -I tools/assets/glb_inspect.py ThirdParty_staging/poly.pizza/picks/*/*.glb --json report.json
```
