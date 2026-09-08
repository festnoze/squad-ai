using System.Collections.Generic;
using UnityEngine;
// Aliased rather than imported wholesale, the way ShotProbe does it: half a
// dozen types are wanted out of UnityEngine.Rendering.Universal, and opening
// that whole namespace beside UnityEngine is an ambiguity waiting for the next
// edit.
using DecalProjector = UnityEngine.Rendering.Universal.DecalProjector;
using DecalRendererFeature = UnityEngine.Rendering.Universal.DecalRendererFeature;
using DecalScaleMode = UnityEngine.Rendering.Universal.DecalScaleMode;
using ScriptableRendererData = UnityEngine.Rendering.Universal.ScriptableRendererData;
using ScriptableRendererFeature = UnityEngine.Rendering.Universal.ScriptableRendererFeature;
using UniversalRenderPipelineAsset = UnityEngine.Rendering.Universal.UniversalRenderPipelineAsset;

namespace Viewpoint
{
    /// <summary>
    /// Turns a LevelDef into GameObjects under a level root (PRD section 5.8).
    /// Everything a level owns lives under that root, so unloading a level is
    /// destroying the root's children, placed photo content included.
    ///
    /// This is the only place where authored level data crosses from design
    /// space into Unity space: every position goes through DesignSpace.ToUnity
    /// at the moment it is set, and nowhere else. Sizes are never mirrored.
    /// </summary>
    public static class LevelBuilder
    {
        /// <summary>
        /// The paved lip around a platform top (PRD_VISUAL 4.6 V-GEO-04), 6 cm
        /// as that item specifies. BeveledBox clamps it against the slab's own
        /// thinnest axis, so a 0.2 m thick platform gets what fits rather than a
        /// lip that eats its own face.
        /// </summary>
        const float PlatformTopLip = 0.06f;

        /// <summary>
        /// The palette keys that DECLARE a placement marker in the level data
        /// (PRD 13.4). No new data field was invented for V-PROP-06 because
        /// there is nothing to invent: the colour IS the declaration, and it is
        /// already the test the rest of the game applies. DesignAudit finds the
        /// markers it audits by "teal" and "accent", Materials.cs maps these
        /// four keys (the two dark sides included) to its flat untextured Marker
        /// style, and ShotProbe's census reads the same four. A marker stays a
        /// decor slab in the data, so nothing here could tell it apart any other
        /// way.
        /// </summary>
        static readonly string[] MarkerColors = { "teal", "teal_dark", "accent", "accent_dark" };

        /// <summary>
        /// Second half of the marker test: thicker than this and a tinted slab
        /// is furniture, not paint. The number is DesignAudit.MarkerMaxHeight,
        /// whose own comment reads "slabs this thin are paint, not furniture:
        /// they are markers, never steps", so the two files agree by
        /// construction.
        ///
        /// The colour alone would be wrong, and the photo data proves it rather
        /// than a hypothetical: photos.json paints a door frame in "accent"
        /// (0.12 x 2.6 x 0.5) and a console ledge in "teal" (2.0 x 0.3 x 2.0).
        /// Those are painted PROPS. Hiding a mesh on its tint alone would delete
        /// one of them from the world the day a level authors one.
        /// </summary>
        const float MarkerMaxThickness = 0.2f;

        /// <summary>
        /// How deep the ground decal boxes are, for markers (V-PROP-06) and for
        /// pickup halos (V-VFX-07) alike, and how far below the painted surface
        /// the box is centred. Together they put 5 cm of the box above that
        /// surface and 11 cm below it.
        ///
        /// A decal paints EVERY opaque surface inside its box, which pins this
        /// between three failures.
        ///
        /// Too shallow and it misses the ground: the painted surface sits within
        /// a centimetre of the marker's own centre in all 25 levels (50 markers
        /// are 1 cm under the platform top, the one on the level 5 socle 1 cm
        /// over it), and a centimetre is not slack.
        ///
        /// Too deep DOWNWARD and it reaches the UNDERSIDE of the very slab it
        /// paints, putting a teal square on the rock skirt for anyone looking up
        /// from the abyss. The thinnest platform in the data is 0.3 m thick, so
        /// 0.11 stops about 18 cm short of its underside.
        ///
        /// Too deep UPWARD and it smears paint up the foot of anything standing
        /// on the marker, because the stock decal graph gives the projector no
        /// angle fade to suppress vertical faces with (see AddGroundDecal). One
        /// marker in the data is exposed to that, the one at x 4.6, z 1.6 on
        /// level 20, whose footprint overlaps a lavender block: 5 cm of paint at
        /// the base of a wall is about what the ambient occlusion of the
        /// junction already darkens, and 5 cm is the smallest upward half that
        /// still leaves the painted surface comfortably inside the box.
        /// </summary>
        const float DecalDepth = 0.16f;
        const float DecalSink = 0.03f;

        /// <summary>
        /// The URP shader that can be projected as a decal, and the one thing
        /// these two items depend on that this project does not own. Its passes
        /// are what DecalProjector.IsValid() looks for; a material on any other
        /// shader is skipped by the renderer feature or drawn by its error pass.
        ///
        /// IT IS A PACKAGE SHADER THAT NOTHING IN THIS PROJECT REFERENCES, so it
        /// is stripped from a player unless it is listed in the Always Included
        /// Shaders of ProjectSettings/GraphicsSettings.asset. That file is not
        /// ours to edit; the warning below names it, and the slabs stay visible
        /// until it is.
        /// </summary>
        const string DecalShaderName = "Shader Graphs/Decal";

        /// <summary>
        /// Base colour map of that shader, and its normal blend weight. Both are
        /// PACKAGE property names, so both are checked with HasProperty before
        /// being written: a renamed property would otherwise be a silent no-op,
        /// and the decal would then draw the shader's own default white square
        /// over every marker in the game.
        /// </summary>
        const string DecalBaseMap = "Base_Map";
        const string DecalNormalBlend = "Normal_Blend";

        /// <summary>
        /// The painted square of V-PROP-06, in the units of a texture whose
        /// coordinates run from -1 to 1.
        ///
        /// PaintEdge leaves the outer tenth of the footprint unpainted, so the
        /// paint stops before the projector box does: a texture running to the
        /// box edge would show the BOX as a hard straight cut, which is the very
        /// thing the physical slab was being blamed for. CornerPower rounds the
        /// corners a little (a superellipse, not a circle), because a painted
        /// sign has no perfect right angles and the eye reads that at a metre.
        /// </summary>
        const int MarkerTextureSize = 128;
        const float PaintEdge = 0.90f;
        const float PaintEdgeSoftness = 0.08f;
        const float CornerPower = 6f;

        /// <summary>
        /// The wear. EdgeWear wobbles the boundary by plus or minus half of it
        /// on a COARSE lattice, so the edge waves over tens of centimetres
        /// instead of shimmering per pixel; WearBite then eats alpha with the
        /// fine grain, and only where the paint is already thinning, so the
        /// middle of the square stays solid. PaintGrain is the 6 percent noise
        /// the item asks for, applied to the VALUE around a mean of 1.0: the
        /// average pixel is exactly the palette colour, which is the same
        /// mean-preserving rule the surface shader follows (Appendix C.12).
        /// </summary>
        const float EdgeWear = 0.05f;
        const float WearBite = 0.35f;
        const float PaintGrain = 0.06f;
        const int WearCells = 5;
        const int GrainCells = 22;

        /// <summary>
        /// The hovering halos of V-VFX-07: a soft disc at 6 percent alpha of the
        /// object's own colour. 64 pixels is plenty for a blurred disc, and the
        /// 6 percent is baked into the texture's ALPHA rather than left to the
        /// projector's fadeFactor, so nothing outside this file can dilute it a
        /// second time.
        /// </summary>
        const int HaloTextureSize = 64;
        const float HaloAlpha = 0.06f;

        /// <summary>
        /// Halo diameters, and how far under each prop's origin its ground is.
        ///
        /// The drops are measured, not guessed: over the 25 levels every one of
        /// the 57 batteries and 10 cameras is authored with its origin exactly
        /// on the platform top, and all 43 polaroids exactly 0.9 m above it. A
        /// placement that broke the pattern would leave its ground outside the
        /// decal box and simply lose its halo, which is the right way for this
        /// to fail.
        ///
        /// The diameters grow faster than the props do (a 0.32 m battery gets
        /// 0.62, a 0.72 m polaroid hovering 0.9 m up gets 1.05), because a
        /// STATIC halo has to say with its shape what a breathing one would have
        /// said with motion: the higher the prop, the broader and softer the
        /// pool of light under it.
        /// </summary>
        const float PhotoHaloDrop = 0.9f;
        const float PhotoHaloDiameter = 1.05f;
        const float BatteryHaloDiameter = 0.62f;
        const float CameraHaloDiameter = 0.78f;

        /// <summary>
        /// Generated decal materials and their textures, one entry per (kind,
        /// palette key), cached for the session and never cleared. Exactly the
        /// reasoning of the gradient and map caches in Materials.cs: live
        /// materials are sampling these textures, so destroying one on a cache
        /// clear would blank every marker in the level, and without a cache each
        /// of the 25 levels would generate its own copy of the same two painted
        /// squares.
        ///
        /// A palette retune (Materials.ClearCache) does NOT reach them, which is
        /// safe only because Palette is immutable at run time. If it ever gains
        /// a setter, these two caches have to be cleared with the materials.
        /// </summary>
        static readonly Dictionary<string, Material> DecalMaterials = new Dictionary<string, Material>();
        static readonly Dictionary<string, Texture2D> DecalTextures = new Dictionary<string, Texture2D>();

        const string MarkerKind = "marker";
        const string HaloKind = "halo";

        /// <summary>
        /// Latched the first time a generated decal material turns out to carry
        /// no decal pass (a stripped or swapped shader). That is a property of
        /// the BUILD and not of a level, so it is asked once and never retried:
        /// fifty identical warnings would bury the one that matters.
        /// </summary>
        static bool _decalMaterialBroken;

        /// <summary>Keeps the "no decals" warning to one line per session.</summary>
        static bool _decalObstacleReported;

        public static Teleporter Build(Transform root, LevelDef def)
        {
            if (root == null || def == null)
            {
                Debug.LogError("LevelBuilder.Build needs a root and a definition.");
                return null;
            }

            // CAN A DECAL ACTUALLY DRAW? Asked ONCE, here, and handed down to
            // everything that would paint one (PRD_VISUAL 4.7 V-PROP-06 and 4.8
            // V-VFX-07). Asking per object would let one level hide half its
            // marker slabs and only then discover the decals are dead.
            //
            // This one flag is the whole design of V-PROP-06, so it is worth
            // saying at length why it exists. A DecalProjector renders NOTHING without the
            // Decal Renderer Feature in the active renderer, and a feature whose
            // m_Script guid does not resolve is DROPPED by Unity on load without
            // a word: no exception, no warning, no null in any code path. The
            // item hides the physical marker slab, so on that failure the player
            // is left with nothing where they are meant to stand, the design
            // audit still finds its markers (it reads level DATA, which is
            // untouched), and every test in the harness still passes. An
            // unplayable level that verifies green.
            //
            // So the slab is hidden only where a projector has been created AND
            // validated. Two alternatives were weighed and rejected:
            //   - keeping the slab but FLATTENING it. That changes BlockSize,
            //     which is the BoxCollider, and the gameplay PRD pins marker
            //     geometry: the standable surface the audit checks would move;
            //   - trusting the projector's existence alone. AddComponent cannot
            //     fail here (the type is compiled in), so it proves nothing
            //     about the feature or about the shader surviving the build.
            string decalObstacle = DecalObstacle();
            bool decals = decalObstacle == null;
            if (!decals && !_decalObstacleReported && HasMarker(def))
            {
                _decalObstacleReported = true;
                Debug.LogWarning("[LevelBuilder] V-PROP-06: ground decals cannot draw ("
                    + decalObstacle + "). Marker slabs KEEP their mesh, so the level still"
                    + " says where to stand; they z-fight at grazing angles and cast a step"
                    + " shadow, which is the defect this item exists to fix and the lesser"
                    + " of the two evils. Pickup halos (V-VFX-07) are skipped entirely.");
            }

            if (def.Platforms != null)
            {
                for (int i = 0; i < def.Platforms.Count; i++)
                {
                    AddPlatform(root, def.Platforms[i]);
                }
            }

            if (def.Decor != null)
            {
                for (int i = 0; i < def.Decor.Count; i++)
                {
                    AddDecor(root, def.Decor[i], decals);
                }
            }

            if (def.Erasables != null)
            {
                for (int i = 0; i < def.Erasables.Count; i++)
                {
                    AddErasable(root, def.Erasables[i]);
                }
            }

            if (def.Cages != null)
            {
                for (int i = 0; i < def.Cages.Count; i++)
                {
                    AddCage(root, def.Cages[i]);
                }
            }

            if (def.Photos != null)
            {
                for (int i = 0; i < def.Photos.Count; i++)
                {
                    AddPhotoItem(root, def.Photos[i], decals);
                }
            }

            if (def.Batteries != null)
            {
                for (int i = 0; i < def.Batteries.Count; i++)
                {
                    AddBattery(root, def.Batteries[i], false, decals);
                }
            }

            if (def.SealedBatteries != null)
            {
                // Same battery, same value to a teleporter, but no film prints it.
                for (int i = 0; i < def.SealedBatteries.Count; i++)
                {
                    AddBattery(root, def.SealedBatteries[i], true, decals);
                }
            }

            if (def.Camera != null)
            {
                AddCamera(root, def.Camera, decals);
            }

            IReadOnlyList<IslandDef> islands = LevelDefs.DecorIslands;
            if (islands != null)
            {
                for (int i = 0; i < islands.Count; i++)
                {
                    AddIsland(root, islands[i]);
                }
            }

            if (def.Teleporter == null)
            {
                Debug.LogError("LevelBuilder: level \"" + def.Name + "\" has no teleporter.");
                return null;
            }
            GameObject exit = NewObject("Teleporter");
            Teleporter teleporter = exit.AddComponent<Teleporter>();
            teleporter.Setup(def.Teleporter.Required);
            Place(exit, root, def.Teleporter.Pos);

            // The air of the level (PRD_VISUAL 4.8 V-VFX-08), last, so the
            // bounds cover everything that was built. Decor only: no group, no
            // collider, culled from the picture studio, and it goes down with
            // the level root.
            Atmosphere.Install(root, PlayableBounds(root));

            return teleporter;
        }

        /// <summary>
        /// The volume the level actually occupies, from the renderers that were
        /// just built. Measured rather than taken from the data, because the
        /// data is design space and this has to be Unity space, and because the
        /// decor islands sit far outside the playable area and would otherwise
        /// stretch the box across the whole horizon.
        /// </summary>
        static Bounds PlayableBounds(Transform root)
        {
            var renderers = new List<MeshRenderer>();
            root.GetComponentsInChildren(true, renderers);
            var bounds = new Bounds(root.position, Vector3.one * 8f);
            var started = false;
            for (int i = 0; i < renderers.Count; i++)
            {
                // Decor islands are scenery on the horizon, not part of the
                // playable volume; including them would spread the dust so thin
                // that none of it is ever on screen.
                if (renderers[i].gameObject.name.StartsWith("DecorIsland"))
                {
                    continue;
                }
                if (!started)
                {
                    bounds = renderers[i].bounds;
                    started = true;
                }
                else
                {
                    bounds.Encapsulate(renderers[i].bounds);
                }
            }
            return bounds;
        }

        /// Ground. Grey by default and PERMANENT: a photo placed over it is
        /// added to it, the slab stays. A "soft" platform is pale instead and
        /// the frame carves it like a lavender wall: that is the whole
        /// language, said in color.
        static void AddPlatform(Transform root, PlatformDef platform)
        {
            string[] groups = platform.Soft
                ? new string[] { Groups.Platform, Groups.Erasable }
                : new string[] { Groups.Platform };
            ErasableBlock block = ErasableBlock.Create(
                platform.Size,
                platform.Soft ? "platform_soft" : "platform",
                0f,
                groups,
                platform.Soft,
                ErasableBlock.UnsetSeed,
                // V-GEO-04: the 6 cm paved lip, on the ground and nowhere else.
                // A platform edge is the one place in this game the player looks
                // straight down at from standing height, and a hard 90 degree
                // cut there is what makes a slab read as a primitive. Crates and
                // lavender walls deliberately keep their crisp 2.5 cm chamfer:
                // a rounded top would make solid matter look soft, and the
                // ephemeral half of the colour language needs to look solid
                // right up to the moment a frame removes it.
                PlatformTopLip);
            block.gameObject.name = platform.Soft ? "PlatformSoft" : "Platform";
            Place(block.gameObject, root, platform.Pos);

            // The rock mass hanging under the slab (PRD_VISUAL 4.6 V-GEO-02).
            // It was a darker BOX, which section 1.1 of that document names as
            // its own defect: "the one thing meant to say terrain says second
            // box". Still a child of the block, so it vanishes with the block
            // and carved fragments have none.
            AddSkirt(block.transform, platform.Size, platform.Pos,
                platform.Soft ? "platform_soft_side" : "platform_side");
        }

        /// Decor is part of the fixed world: photographable, permanent, never
        /// carved, like the grey ground. The thin tinted slabs are the
        /// placement markers; their photo, aim and roll fields are read by the
        /// design audit and change nothing here.
        ///
        /// V-PROP-06 turns those slabs into PAINT. The block itself stays, in
        /// the data and in every group it joined, and keeps its collider: the
        /// audit reads level data, the gameplay PRD pins the marker positions,
        /// and a marker is still somewhere the player stands. Only its MESH goes
        /// away, and only once a decal is actually painting in its place.
        static void AddDecor(Transform root, DecorDef decor, bool decals)
        {
            string color = string.IsNullOrEmpty(decor.Color) ? "wood" : decor.Color;
            ErasableBlock block = ErasableBlock.Create(decor.Size, color, 0f, null, false);
            block.gameObject.name = "Decor";
            Place(block.gameObject, root, decor.Pos);

            if (!decals || !IsMarkerSlab(color, decor.Size))
            {
                return;
            }

            // A child of the block, at its own origin: the block is already at
            // the one converted position (Place did that), so the decal inherits
            // it instead of converting a second time, and it goes down with the
            // block when the level is torn down or the rewind hides it.
            //
            // Sizes are never mirrored, and the offset is pure Y, so nothing
            // here can pick up a second design-space flip. The painted square
            // itself carries no orientation: it is noise inside a symmetric
            // outline, so even a flipped axis would be invisible in it.
            DecalProjector painted = AddGroundDecal(
                "MarkerPaint",
                block.transform,
                0f,
                decor.Size.x,
                decor.Size.z,
                DecalMaterial(MarkerKind, color));

            // THE ORDER OF THESE TWO STATEMENTS IS THE ITEM. Nothing is hidden
            // until a projector exists and has told us it can draw.
            if (painted != null)
            {
                block.ShowMesh = false;
            }
        }

        /// <summary>
        /// Whether a decor slab is a placement marker: one of the marker tints
        /// AND thin enough to be paint rather than furniture.
        ///
        /// Both halves are needed. The tint alone would catch the painted door
        /// frame and the console ledge of photos.json, which are props; the
        /// thinness alone would catch every flat prop in the game whatever its
        /// colour. The second thickness test (thin RELATIVE to its own
        /// footprint) is what keeps a small tinted cube, say 15 x 10 x 15 cm,
        /// from being read as a sign and silently losing its mesh.
        /// </summary>
        static bool IsMarkerSlab(string colorKey, Vector3 size)
        {
            bool tinted = false;
            for (int i = 0; i < MarkerColors.Length; i++)
            {
                if (MarkerColors[i] == colorKey)
                {
                    tinted = true;
                    break;
                }
            }
            if (!tinted)
            {
                return false;
            }

            return size.y <= MarkerMaxThickness
                && size.y < Mathf.Min(size.x, size.z) * 0.5f;
        }

        /// <summary>
        /// True when the level data holds at least one marker. Only used to
        /// decide whether a level has anything to LOSE when decals cannot draw,
        /// so the warning is silent for a level that would not have painted one.
        /// </summary>
        static bool HasMarker(LevelDef def)
        {
            if (def.Decor == null)
            {
                return false;
            }
            for (int i = 0; i < def.Decor.Count; i++)
            {
                string color = string.IsNullOrEmpty(def.Decor[i].Color) ? "wood" : def.Decor[i].Color;
                if (IsMarkerSlab(color, def.Decor[i].Size))
                {
                    return true;
                }
            }
            return false;
        }

        /// The "erasable" group is only a lavender marker (readability and
        /// tests): every block of the ephemeral half is carvable anyway.
        static void AddErasable(Transform root, ErasableDef erasable)
        {
            ErasableBlock block = ErasableBlock.Create(
                erasable.Size,
                "erasable",
                0.25f,
                new string[] { Groups.Erasable },
                true);
            block.gameObject.name = "Erasable";
            Place(block.gameObject, root, erasable.Pos);
        }

        static void AddCage(Transform root, CageDef cage)
        {
            Cage body = Cage.Create(cage.Size, cage.Erasable, cage.Roof, cage.Sealed);
            // pos is the center of the cage FLOOR; the body sits half a cage
            // higher, on the volumetric center the breakable test reads.
            Place(body.gameObject, root, cage.Pos + new Vector3(0f, cage.Size.y * 0.5f, 0f));
        }

        static void AddPhotoItem(Transform root, PhotoPlacementDef photo, bool decals)
        {
            if (string.IsNullOrEmpty(photo.Id))
            {
                Debug.LogError("LevelBuilder: a photo placement has no id.");
                return;
            }
            GameObject go = NewObject("PhotoItem");
            PhotoItem item = go.AddComponent<PhotoItem>();
            item.Setup(photo.Id);
            Place(go, root, photo.Pos);
            // The polaroid is the one pickup that hovers well clear of the
            // ground, so its halo is also the one that has to reach for it.
            AddHalo(go.transform, PhotoHaloDrop, PhotoHaloDiameter, "frame", decals);
        }

        static void AddBattery(Transform root, Vector3 pos, bool isSealed, bool decals)
        {
            GameObject go = NewObject(isSealed ? "SealedBattery" : "Battery");
            Battery battery = go.AddComponent<Battery>();
            battery.Setup(isSealed);
            Place(go, root, pos);
            // No halo under a leaden battery. V-VFX-07 is about what HOVERS, and
            // a sealed battery does not: Battery.Update returns at once for it,
            // so it has no height to read off a halo, and the absence is one
            // more way the game says "this one is dead weight".
            if (!isSealed)
            {
                AddHalo(go.transform, 0f, BatteryHaloDiameter, "battery", decals);
            }
        }

        static void AddCamera(Transform root, CameraDef camera, bool decals)
        {
            GameObject go = NewObject("CameraItem");
            CameraItem item = go.AddComponent<CameraItem>();
            item.Setup(camera.Films);
            Place(go, root, camera.Pos);
            // The camera takes its BODY colour (battery_tip, the same key its
            // body renderer uses) and not the teal of its lens. Teal and coral
            // are the two tints this game reserves for "stand here", and a teal
            // pool on the ground next to a painted teal marker square would be
            // the one halo that could be misread as an instruction.
            AddHalo(go.transform, 0f, CameraHaloDiameter, "battery_tip", decals);
        }

        /// Scenery beyond the world: mesh only, no collision, no group. The
        /// camera must not photograph them and the player must never land on
        /// one.
        static void AddIsland(Transform root, IslandDef island)
        {
            // V-GEO-03 IS DELIBERATELY NOT DONE, and this comment is the record
            // of why rather than an oversight.
            //
            // It was implemented: the same IslandSkirt mass the platforms now
            // hang, under a thin pale cap. On the level 16 frame it was clearly
            // WORSE than these two boxes. Decor islands are numerous, broad and
            // close together in the data, so a mass proportioned to each one's
            // span turned the horizon into a single dark wall, and the pale caps
            // read as plates sitting on it. Two attempts at the proportions and
            // one wrong diagnosis of the sky's abyss darkening later, the honest
            // conclusion is that the item needs something the platform version
            // does not: masses that are SMALLER than their cap, spaced apart,
            // and hazed most of the way to the horizon colour.
            //
            // So the boxes stay until that is designed properly. The platform
            // skirts of V-GEO-02, which the same frame shows working, are kept.
            // A tier that half-lands an item and leaves the game looking worse
            // is not progress, and PRD_VISUAL 6.1 exists to catch exactly this.
            //
            // Positions and sizes are DATA (LevelDefs.DecorIslands) and were
            // never touched by any of it.
            MakeBox("DecorIsland", root, island.Size, island.Pos, Materials.Solid("platform_side"));
            MakeBox(
                "DecorIslandTop",
                root,
                new Vector3(island.Size.x * 1.05f, 0.3f, island.Size.z * 1.05f),
                island.Pos + new Vector3(0f, island.Size.y * 0.5f + 0.1f, 0f),
                Materials.Solid("platform"));
        }

        /// <summary>
        /// The rock mass under a slab. Built at its real size and drawn at UNIT
        /// SCALE, never a scaled primitive: Viewpoint/Surface samples its maps
        /// triplanar from world position, and a non-uniform scale skews the
        /// normals, which breaks both the lighting and the triplanar blend.
        ///
        /// No collider and no group. It is decor: the player walks on the slab
        /// above it, the design audit reads level data rather than meshes, and
        /// nothing may raycast it.
        /// </summary>
        static void AddSkirt(Transform parent, Vector3 size, Vector3 designPos, string colorKey)
        {
            GameObject skirt = new GameObject("Skirt");
            skirt.layer = Layers.World;
            skirt.transform.SetParent(parent, false);
            // The slab's underside. The mesh hangs from local y = 0 downward and
            // the Rock style's fade is measured from the object origin, so this
            // is both the geometric and the shading anchor.
            skirt.transform.localPosition = new Vector3(0f, -size.y * 0.5f, 0f);
            skirt.transform.localScale = Vector3.one;

            MeshFilter filter = skirt.AddComponent<MeshFilter>();
            // DEPTH COMES FROM THE FOOTPRINT, NOT FROM THE SLAB THICKNESS, and
            // getting that backwards was visible the moment a frame was taken.
            // Keyed on thickness (size.y * 3) a 12 m wide platform 0.2 m thick
            // got 1.6 m of rock: twelve metres across and one and a half deep is
            // not a mass, it is a dark PANCAKE, and that is exactly how level 16
            // rendered. What reads as an island is a drop comparable to its own
            // width, so the wider the slab the further its rock has to fall.
            float span = Mathf.Max(size.x, size.z);
            //
            // AND IT IS CAPPED BY THE NARROW SPAN, because the wide span alone
            // is not a bound on anything: an ELONGATED slab is not a wide
            // island, it is a bridge, and a bridge whose rock falls as far as
            // it is long hangs a wall down through whatever the level put under
            // it. Level 11 "Sous le pont" is the case, and it was a real one:
            // its pale carvable bridge is 2 x 0.3 x 8.4, so the wide span asked
            // for 4.62 m of rock hanging from y -0.30 down to -4.92. That mass
            // swallowed the "escalier" polaroid at y -3.1 (dead centre of the
            // taper), the battery at [0, -4, -3], and part of the teal marker
            // at [0, -4.01, -4.2], and it pierced the lower walkway's top face
            // (y -4.0) by nearly a metre. Every one of those is INVISIBLE to the
            // harness: a skirt is not level data, so DesignAudit reads its
            // twenty-five untouched levels and reports zero defects while the
            // level hides its own pickups inside opaque geometry.
            //
            // The cap is one sentence of geometry - the mass never falls further
            // than the island is wide across its NARROW axis - which is also
            // what makes it read as terrain rather than as a fin. It costs the
            // pancake argument above nothing: no island keyed at the 9 m ceiling
            // moves, and only eight of the fifty-seven platforms in the data
            // change at all (the bridge from 4.62 to 2.00, the rest by half a
            // metre or so off masses already 4 m deep or more). Re-running the
            // data scan for anything authored inside a skirt volume comes back
            // empty across all 25 levels, with 0.6 m of margin in every
            // direction.
            float depth = Mathf.Clamp(Mathf.Min(span * 0.55f, Mathf.Min(size.x, size.z)), 1.5f, 9f);
            filter.sharedMesh = ProceduralMeshes.IslandSkirt(
                new Vector3(size.x * 0.94f, size.y, size.z * 0.94f), depth, IslandSeed(designPos));
            skirt.AddComponent<MeshRenderer>().sharedMaterial = Materials.Solid(colorKey);
        }

        /// <summary>
        /// A stable seed from an authored design-space position. Quantised to a
        /// centimetre first, so a float that differs in its last bit between two
        /// runs cannot reshape an island.
        /// </summary>
        static int IslandSeed(Vector3 designPos)
        {
            int x = Mathf.RoundToInt(designPos.x * 100f);
            int y = Mathf.RoundToInt(designPos.y * 100f);
            int z = Mathf.RoundToInt(designPos.z * 100f);
            unchecked
            {
                return (x * 73856093) ^ (y * 19349663) ^ (z * 83492791);
            }
        }

        /// A GameObject that is not live yet: Setup must run, and the position
        /// must be set, before the component builds itself and registers its
        /// groups on enable (several of them read their own position to pick
        /// an idle phase).
        static GameObject NewObject(string name)
        {
            GameObject go = new GameObject(name);
            go.SetActive(false);
            return go;
        }

        /// Parents a finished object under the level root, converts its
        /// authored position once, then wakes it up.
        static void Place(GameObject go, Transform root, Vector3 designPos)
        {
            go.transform.SetParent(root, false);
            go.transform.localPosition = DesignSpace.ToUnity(designPos);
            go.SetActive(true);
        }

        /// A plain visible box: no collider, no group, nothing to interact
        /// with. Used for the platform skirts and the decor islands.
        static GameObject MakeBox(string name, Transform parent, Vector3 size, Vector3 designLocalPos, Material material)
        {
            GameObject box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.name = name;
            box.layer = Layers.World;

            // CreatePrimitive hands out a collider these boxes must not have.
            // This runs while the box is being built, never on a live world
            // object, so it is not a removal in the sense of Rewind.Retire.
            // Disabling comes first because Destroy only bites at the end of the
            // frame: a level built from Start would otherwise expose these
            // skirts and islands to the frame's physics steps as solid ground
            // (the same order Teleporter.SpawnPart uses).
            Collider extra = box.GetComponent<Collider>();
            if (extra != null)
            {
                extra.enabled = false;
                if (Application.isPlaying)
                {
                    UnityEngine.Object.Destroy(extra);
                }
                else
                {
                    UnityEngine.Object.DestroyImmediate(extra);
                }
            }

            box.transform.SetParent(parent, false);
            box.transform.localPosition = DesignSpace.ToUnity(designLocalPos);
            // The primitive cube is one meter on every axis, so the scale IS
            // the size.
            box.transform.localScale = size;
            box.GetComponent<MeshRenderer>().sharedMaterial = material;
            return box;
        }

        /// <summary>
        /// The soft ground halo under a hovering prop (PRD_VISUAL 4.8 V-VFX-07).
        /// A child of the prop, which is what makes it stay PUT: all three
        /// pickups bob a child they each call "Visual" and never their own root,
        /// so a halo parented to the root sits still on the ground while the
        /// prop rises and falls over it. It also means the halo is retired,
        /// revived and destroyed with the prop, and that ShotProbe finds it
        /// where its census looks for it.
        ///
        /// THE HALO IS STATIC, and the item allows that in as many words ("if
        /// the pickups' bob phase is not reachable from here, a static halo is
        /// acceptable: say so"). It is not reachable: _bobPhase is private in
        /// each of PhotoItem, Battery and CameraItem, and so are the phase
        /// weights and speeds that seed it. Re-deriving the phase here would
        /// copy three private contracts out of three files this pass does not
        /// own, and the copy would fall out of step the moment any of them is
        /// retuned. A halo breathing out of time with the object above it is
        /// worse than one that does not breathe, so the height is said with
        /// shape instead: the higher the prop, the broader and fainter its pool.
        /// </summary>
        static void AddHalo(Transform prop, float drop, float diameter, string colorKey, bool decals)
        {
            if (!decals)
            {
                return;
            }

            AddGroundDecal("Halo", prop, drop, diameter, diameter, DecalMaterial(HaloKind, colorKey));
        }

        /// <summary>
        /// A decal box that paints downward onto the ground, and the only place
        /// in this file that creates a DecalProjector. Returns the projector, or
        /// null when nothing can be painted: the caller uses that to decide
        /// whether it may hide anything.
        ///
        /// <paramref name="drop"/> is how far BELOW the parent the painted
        /// surface is expected to be. The box is centred there and is
        /// DecalDepth deep, so the paint lands on whatever opaque surface lies
        /// within half of that; a surface further away simply does not get
        /// painted.
        /// </summary>
        static DecalProjector AddGroundDecal(string name, Transform parent, float drop, float width, float length, Material material)
        {
            if (parent == null || material == null)
            {
                return null;
            }

            GameObject go = NewObject(name);
            // Before the component exists and before the object is live, as
            // everywhere else here. It matters more than usual for a decal: the
            // renderer feature caches gameObject.layer when the projector
            // registers, and tests it against each camera's culling mask. On
            // Layers.World the player camera paints it and the picture studio
            // (Layers.PhotoStudioMask) does not, which is what keeps a level's
            // painted marker out of a polaroid.
            go.layer = Layers.World;
            go.transform.SetParent(parent, false);
            // A PURE Y OFFSET, so it needs no DesignSpace conversion of its own:
            // the mirror is on z, the parent already carries the one converted
            // position, and height is the same number in both spaces.
            go.transform.localPosition = new Vector3(0f, -drop, 0f);
            // A URP decal projects along its own FORWARD, so forward has to
            // point at the ground: Euler(90, 0, 0) turns +z into -y. After that
            // turn the projector's local x is still world x and its local y is
            // world z, which is the order the size below is written in.
            go.transform.localRotation = Quaternion.Euler(90f, 0f, 0f);
            go.transform.localScale = Vector3.one;

            DecalProjector projector = go.AddComponent<DecalProjector>();
            projector.material = material;
            // ScaleInvariant (the default, set here because it is load bearing):
            // the box IS the size field in metres and the transform's scale is
            // ignored. Nothing here is a unit primitive stretched per axis, for
            // the reason the skirt comment gives about skewed normals, and a
            // scale-inheriting decal would reintroduce exactly that.
            projector.scaleMode = DecalScaleMode.ScaleInvariant;
            projector.size = new Vector3(width, length, DecalDepth);
            // The pivot is the box CENTRE in the projector's own space, and its
            // z runs along the projection, so a positive z sinks the box. The
            // URP default is (0, 0, 0.5), which with a unit depth hangs the
            // whole box below the transform; zero would straddle the surface
            // evenly, and DecalSink shifts it down so that most of the depth is
            // under the ground rather than above it.
            projector.pivot = new Vector3(0f, 0f, DecalSink);
            // Angle fade is left OFF (start and end stay at 180), and that is
            // checked rather than assumed: the package graph declares
            // "angleFade": false, so it compiles none of the support the
            // projector needs, and DecalProjectorEditor greys the slider out
            // when the material has no _DecalAngleFadeSupported property.
            // Setting it here would LOOK like a safeguard against painting
            // vertical faces while doing nothing at all. The shallow box
            // (DecalDepth and DecalSink) is the real safeguard.
            //
            // The same file says "affectsMAOS": false, which is the other
            // question worth having asked: the paint cannot leave a smoother or
            // less occluded patch of ground behind it, only a differently
            // coloured one.

            if (!projector.IsValid())
            {
                // The material resolved a shader that carries no decal pass, so
                // this projector would draw nothing (or be drawn by the decal
                // error pass). Latched, warned once, and torn down before it is
                // ever live, so the caller keeps its slab and the level stays
                // playable.
                _decalMaterialBroken = true;
                Debug.LogWarning("[LevelBuilder] V-PROP-06: \"" + DecalShaderName + "\" resolved"
                    + " but carries no decal pass, so no decal can be painted. Marker slabs keep"
                    + " their mesh.");
                RetireDuringBuild(go);
                return null;
            }

            go.SetActive(true);
            return projector;
        }

        /// <summary>
        /// Why a decal cannot be painted right now, or null when one can. A
        /// SENTENCE rather than a bool, because every branch below is a
        /// different silent failure and the warning that quotes it is the only
        /// thing that will name the cause.
        /// </summary>
        static string DecalObstacle()
        {
            if (_decalMaterialBroken)
            {
                return "the decal material carries no decal pass";
            }

            // No rasterizer, nothing to paint on. Same guard, same reason, as
            // Atmosphere.Install: a headless run has no use for this and the
            // test suites must not pay for it.
            if (SystemInfo.graphicsDeviceType == UnityEngine.Rendering.GraphicsDeviceType.Null)
            {
                return "no graphics device";
            }

            UniversalRenderPipelineAsset pipeline =
                UnityEngine.Rendering.GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
            if (pipeline == null)
            {
                return "the active render pipeline is not URP";
            }

            // currentRenderPipeline is the asset the active QUALITY LEVEL uses,
            // so this answers for the renderer the player is really running
            // (PC_RPAsset or Mobile_RPAsset) and not for whichever asset happens
            // to be the project default.
            //
            // EVERY renderer data of that asset has to carry the feature, not
            // merely the first one. Both assets ship exactly one today, so the
            // strict reading costs nothing; if a second is ever added, the
            // conservative answer is the one that cannot leave a camera drawing
            // a hidden marker, and a camera may name its own renderer index.
            var datas = pipeline.rendererDataList;
            if (datas.Length == 0)
            {
                return pipeline.name + " has no renderer";
            }
            for (int i = 0; i < datas.Length; i++)
            {
                if (!HasDecalFeature(datas[i]))
                {
                    return "no active Decal Renderer Feature in " + pipeline.name;
                }
            }

            // AUTHORED TECHNIQUE, and the second half of the same trap. The
            // loop above proves a DecalRendererFeature EXISTS and is switched
            // on, and nothing more: isActive is the serialised checkbox and
            // only that (Runtime/ScriptableRendererFeature.cs, "public bool
            // isActive => m_Active;"), so it never says the feature can RUN.
            //
            // PC_Renderer.asset authors technique: 1, which is
            // DecalTechniqueOption.DBuffer (explicit, NOT Automatic), and
            // DecalRendererFeature.GetTechnique then answers
            // DecalTechnique.Invalid on a GL device or on a device without MRT4
            // support. Invalid propagates: RecreateSystemsIfNeeded returns
            // false, AddRenderPasses bails on "if (!isValid) return;", and NOT
            // ONE decal pass is enqueued, for any camera, for the whole run.
            // URP logs a single Debug.LogError and that is the only trace.
            //
            // This path is live on the desktop the game ships to, which is why
            // it is worth two SystemInfo reads: QualitySettings puts Standalone
            // on the PC quality level (PC_RPAsset, PC_Renderer), and a Windows
            // player started with -force-glcore or -force-opengl, or a Linux
            // player falling back to OpenGLCore, is a GL device. Unchecked, the
            // gate would say yes, every marker slab would lose its mesh, and
            // nothing would be painted where it stood: an unplayable level that
            // verifies green, which is the one outcome this whole gate exists
            // to prevent.
            //
            // The feature cannot be asked which technique it resolved:
            // DecalSettings, DecalTechniqueOption and GetTechnique are all
            // internal to the URP assembly. So the two PUBLIC conditions URP
            // itself tests are tested here instead. That is the strictest
            // reading, and the correct one while the only decal feature in the
            // project is authored as DBuffer; if PC_Renderer is ever moved to
            // Automatic (which resolves to ScreenSpace on a GL device), this
            // turns pessimistic rather than wrong, and pessimistic means the
            // marker keeps its mesh.
            UnityEngine.Rendering.GraphicsDeviceType device = SystemInfo.graphicsDeviceType;
            if (device == UnityEngine.Rendering.GraphicsDeviceType.OpenGLCore
                || device == UnityEngine.Rendering.GraphicsDeviceType.OpenGLES3)
            {
                return "the Decal Renderer Feature is authored as DBuffer, which URP refuses on"
                    + " OpenGL (" + device + ")";
            }
            if (SystemInfo.supportedRenderTargetCount < 4)
            {
                return "the Decal Renderer Feature is authored as DBuffer, which URP refuses"
                    + " without MRT4 support (this device reports "
                    + SystemInfo.supportedRenderTargetCount + " render targets)";
            }

            // The last hole, and the one this project has already fallen into
            // once (see the README and Appendix C of PRD_VISUAL): a shader that
            // no ASSET references is stripped from the player, and every
            // material built through Shader.Find then comes back on a null
            // shader. This one belongs to the URP package and only a package
            // material in the editor refers to it, so it needs listing by hand.
            if (Shader.Find(DecalShaderName) == null)
            {
                return "the shader \"" + DecalShaderName + "\" is absent from this build; list it"
                    + " in ProjectSettings/GraphicsSettings.asset m_AlwaysIncludedShaders";
            }

            return null;
        }

        /// <summary>
        /// Whether a renderer data carries a Decal Renderer Feature that is
        /// switched on.
        ///
        /// A FEATURE WHOSE m_Script GUID DOES NOT RESOLVE DESERIALISES AS A NULL
        /// HOLE in this list, with no exception and no log line anywhere, which
        /// is the failure the whole gate exists for. So the question asked here
        /// is "is there a live DecalRendererFeature, and is it enabled", never
        /// "is the list the length the YAML suggests".
        ///
        /// EXISTENCE IS ALL THIS ANSWERS. isActive reads back the serialised
        /// checkbox and nothing else, so a feature that passes here can still
        /// resolve a technique URP refuses and enqueue no pass at all; that
        /// second question is asked by the caller, on the device, and its
        /// reasoning is written out there.
        /// </summary>
        static bool HasDecalFeature(ScriptableRendererData data)
        {
            if (data == null)
            {
                return false;
            }

            List<ScriptableRendererFeature> features = data.rendererFeatures;
            if (features == null)
            {
                return false;
            }
            for (int i = 0; i < features.Count; i++)
            {
                DecalRendererFeature feature = features[i] as DecalRendererFeature;
                if (feature != null && feature.isActive)
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>
        /// The decal material for a kind and a palette key, generated once and
        /// shared. Null means "cannot paint", and every caller treats it that
        /// way rather than substituting something plausible.
        /// </summary>
        static Material DecalMaterial(string kind, string colorKey)
        {
            string cacheKey = kind + ":" + colorKey;
            Material cached;
            if (DecalMaterials.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            Shader shader = Shader.Find(DecalShaderName);
            if (shader == null)
            {
                // DecalObstacle has already said this, once, with the fix in it.
                return null;
            }

            Texture2D painted = DecalTexture(kind, colorKey);
            if (painted == null)
            {
                return null;
            }

            Material material = new Material(shader);
            material.name = "Decal_" + kind + "_" + colorKey;
            if (!material.HasProperty(DecalBaseMap))
            {
                // A package property name, so this is checked rather than
                // trusted: SetTexture on a name the shader does not have is a
                // SILENT no-op, and the decal would then paint the shader's own
                // default white square over every marker in the game.
                Debug.LogWarning("[LevelBuilder] V-PROP-06: \"" + DecalShaderName + "\" has no \""
                    + DecalBaseMap + "\" property, so the painted square cannot be attached."
                    + " Marker slabs keep their mesh.");
                _decalMaterialBroken = true;
                return null;
            }
            material.SetTexture(DecalBaseMap, painted);
            // NO RELIEF, deliberately. The stock decal graph blends a normal map
            // at Normal_Blend and ships that at 0.5 with no map assigned, and an
            // unassigned texture property samples WHITE, which unpacks to a
            // meaningless normal. Half of that would be blended into the ground
            // under every marker and every pickup in the game. Paint is flat.
            if (material.HasProperty(DecalNormalBlend))
            {
                material.SetFloat(DecalNormalBlend, 0f);
            }

            DecalMaterials[cacheKey] = material;
            return material;
        }

        /// <summary>
        /// The generated image a decal material carries, cached per kind and
        /// palette key. It is a PAINTED SIGN and not a material, which is why it
        /// is generated from the palette in code: the day a palette colour moves
        /// the paint moves with it, and PRD_VISUAL 3.2 as amended (Appendix
        /// C.11) allows the ten CC0 sets and the one font on disk, nothing else.
        /// </summary>
        static Texture2D DecalTexture(string kind, string colorKey)
        {
            string cacheKey = kind + ":" + colorKey;
            Texture2D cached;
            if (DecalTextures.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            Texture2D texture = kind == MarkerKind ? PaintedSquare(colorKey) : SoftHalo(colorKey);
            DecalTextures[cacheKey] = texture;
            return texture;
        }

        /// <summary>
        /// The marker's painted square (V-PROP-06): a solid middle, a soft inner
        /// edge that wobbles where the paint has worn, and 6 percent grain over
        /// the whole of it. Alpha carries the shape, rgb carries the tint, and
        /// both are baked here so the material stays one shared object.
        /// </summary>
        static Texture2D PaintedSquare(string colorKey)
        {
            Color paint = Palette.Get(colorKey);
            Texture2D texture = NewDecalTexture("MarkerPaint_" + colorKey, MarkerTextureSize);
            Color32[] pixels = new Color32[MarkerTextureSize * MarkerTextureSize];
            for (int y = 0; y < MarkerTextureSize; y++)
            {
                for (int x = 0; x < MarkerTextureSize; x++)
                {
                    float u = (((x + 0.5f) / MarkerTextureSize) * 2f) - 1f;
                    float v = (((y + 0.5f) / MarkerTextureSize) * 2f) - 1f;
                    // Superellipse: 1 on the sides, a little short of 1 in the
                    // corners, so the square keeps its edges and loses its
                    // needle-sharp points.
                    float d = Mathf.Pow(
                        Mathf.Pow(Mathf.Abs(u), CornerPower) + Mathf.Pow(Mathf.Abs(v), CornerPower),
                        1f / CornerPower);

                    float un = (u + 1f) * 0.5f;
                    float vn = (v + 1f) * 0.5f;
                    float wobble = (ValueNoise(un, vn, WearCells, 17) - 0.5f) * EdgeWear;
                    float alpha = Smooth(Mathf.Clamp01(((PaintEdge + wobble) - d) / PaintEdgeSoftness));

                    float grain = ValueNoise(un, vn, GrainCells, 41);
                    // The wear only bites where the paint is already thinning:
                    // (1 - alpha) is 0 in the middle of the sign and 1 outside
                    // it, so the grain ragged-edges the rim and leaves the
                    // middle solid.
                    alpha *= 1f - (grain * WearBite * (1f - alpha));

                    // Mean-preserving by construction: value noise averages 0.5,
                    // so shade averages 1.0 and the average pixel of the square
                    // is exactly the palette colour (Appendix C.12).
                    float shade = 1f + (((grain - 0.5f) * 2f) * PaintGrain);
                    pixels[(y * MarkerTextureSize) + x] = new Color32(
                        ToByte(paint.r * shade),
                        ToByte(paint.g * shade),
                        ToByte(paint.b * shade),
                        ToByte(alpha));
                }
            }
            texture.SetPixels32(pixels);
            texture.Apply(true, true);
            return texture;
        }

        /// <summary>
        /// The pickup halo (V-VFX-07): a disc of the prop's colour whose alpha
        /// peaks at 6 percent under the middle of the prop and fades to nothing
        /// at the rim.
        /// </summary>
        static Texture2D SoftHalo(string colorKey)
        {
            Color tint = Palette.Get(colorKey);
            Texture2D texture = NewDecalTexture("Halo_" + colorKey, HaloTextureSize);
            Color32[] pixels = new Color32[HaloTextureSize * HaloTextureSize];
            float centre = (HaloTextureSize - 1) * 0.5f;
            for (int y = 0; y < HaloTextureSize; y++)
            {
                for (int x = 0; x < HaloTextureSize; x++)
                {
                    float dx = (x - centre) / centre;
                    float dy = (y - centre) / centre;
                    float r = Mathf.Sqrt((dx * dx) + (dy * dy));
                    float alpha = Mathf.Clamp01(1f - r);
                    // Squared falloff, for the reason Atmosphere's dust sprite
                    // gives: a linear ramp still shows a disc EDGE at a few
                    // percent alpha, and a halo with a visible rim reads as a
                    // decal rather than as light.
                    alpha *= alpha;
                    pixels[(y * HaloTextureSize) + x] = new Color32(
                        ToByte(tint.r),
                        ToByte(tint.g),
                        ToByte(tint.b),
                        ToByte(alpha * HaloAlpha));
                }
            }
            texture.SetPixels32(pixels);
            texture.Apply(true, true);
            return texture;
        }

        static Texture2D NewDecalTexture(string name, int size)
        {
            // sRGB and NOT linear: the palette holds sRGB components (see
            // Palette), so writing them in raw is what reproduces the palette
            // colour exactly, the same way Materials hands its colours to Unity
            // and lets the upload convert them. Alpha is linear either way,
            // which is what a falloff needs.
            Texture2D texture = new Texture2D(size, size, TextureFormat.RGBA32, true, false);
            texture.name = name;
            // Clamped, or the soft edge of the square wraps and paints a
            // hairline of the opposite side inside the projector box.
            texture.wrapMode = TextureWrapMode.Clamp;
            texture.filterMode = FilterMode.Bilinear;
            // Aniso 8 for the reason TextureImportRules gives the CC0 maps: a
            // painted square lying on the ground is the most grazing-angle
            // surface in this game, and without it the far half of a marker
            // turns to mush at exactly the distance the player reads it from.
            texture.anisoLevel = 8;
            return texture;
        }

        /// <summary>
        /// Smooth value noise over the unit square, on a lattice of
        /// <paramref name="cells"/> cells per side.
        ///
        /// Deterministic and stateless: no Random, no Time, no static state, so
        /// a marker is painted identically in every run and after every rebuild.
        /// That is the same requirement Atmosphere states for its dust and
        /// Materials.SeedFor for its jitter, and it is what keeps a screenshot
        /// comparable with the reference frames of PRD_VISUAL 6.1.
        /// </summary>
        static float ValueNoise(float u, float v, int cells, int salt)
        {
            float x = u * cells;
            float y = v * cells;
            int x0 = Mathf.FloorToInt(x);
            int y0 = Mathf.FloorToInt(y);
            float fx = Smooth(x - x0);
            float fy = Smooth(y - y0);
            float low = Mathf.Lerp(Hash01(x0, y0, salt), Hash01(x0 + 1, y0, salt), fx);
            float high = Mathf.Lerp(Hash01(x0, y0 + 1, salt), Hash01(x0 + 1, y0 + 1, salt), fx);
            return Mathf.Lerp(low, high, fy);
        }

        /// <summary>
        /// A hash of a lattice cell in [0, 1). The three odd multipliers are the
        /// ones IslandSeed above already uses; the avalanche after them is what
        /// makes one step of one coordinate change the whole value, which a
        /// lattice noise needs and a plain multiply-and-xor does not give.
        /// </summary>
        static float Hash01(int x, int y, int salt)
        {
            unchecked
            {
                uint h = (uint)((x * 73856093) ^ (y * 19349663) ^ (salt * 83492791));
                h ^= h >> 16;
                h *= 0x7feb352du;
                h ^= h >> 15;
                h *= 0x846ca68bu;
                h ^= h >> 16;
                return (h & 0xFFFFFFu) / 16777216f;
            }
        }

        /// <summary>Smoothstep on an already normalised t.</summary>
        static float Smooth(float t)
        {
            return t * t * (3f - (2f * t));
        }

        static byte ToByte(float value)
        {
            return (byte)Mathf.RoundToInt(Mathf.Clamp01(value) * 255f);
        }

        /// <summary>
        /// Destroys something that was being BUILT and never went live. Same
        /// two branches and the same reason as MakeBox's spare collider: Destroy
        /// only bites at the end of the frame and Unity refuses it outside play
        /// mode, and the object is still inactive here, so it can reach neither
        /// a physics step nor a render pass on its way out.
        /// </summary>
        static void RetireDuringBuild(GameObject go)
        {
            if (Application.isPlaying)
            {
                UnityEngine.Object.Destroy(go);
            }
            else
            {
                UnityEngine.Object.DestroyImmediate(go);
            }
        }
    }
}
