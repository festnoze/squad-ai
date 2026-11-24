using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.Experimental.Rendering;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Textures probe (steps 22c to 22f) on the real Boot scene, every level of levels.json. M7 real colours
    /// (CONTRACT_M7 5, product owner decision of 2026-11-18): every textured surface shows its image in the image's own
    /// colours through ONE URP Lit material per surface (white base colour, the colour map as base map,
    /// PrimitiveKit.SurfaceMaterial), tiled through a MaterialPropertyBlock (PrimitiveKit.Detail); the player furniture
    /// shows the owner's red image (PrimitiveKit.PlayerMaterial) and stays the one saturated red of the frame (PRD 7.2);
    /// the inhabitants keep the M4.2 rule (palette material, grayscale detail of mean Tuning.DetailMean). Every step
    /// asserts its premise first (the library resolves, the level has model visuals and textured slots), so a Detail that
    /// does nothing cannot pass.
    /// </summary>
    public sealed class ProbeTestsM42Look
    {
        private static readonly int BaseMap = Shader.PropertyToID("_BaseMap");
        private static readonly int BaseMapSt = Shader.PropertyToID("_BaseMap_ST");

        /// <summary>
        /// "A visible pattern, not noise": the textured start view may have at most this much more fine detail (mean
        /// absolute difference between neighbour pixels) than the same view flat. M7 real colours: the images are meant to
        /// read as a pattern, so the M4.2 cap (2.0, calm grayscale details) is raised to what a clear but not noisy
        /// pattern measures, with a margin: 4.2 on level1 (the lawn and the parquet fill the frame), 2.5 on level5
        /// (CONTRACT_M7 5). Pixel-level noise (an aliasing image, a texture shown without its mipmaps) blows through it.
        /// </summary>
        private const float MaxDetailGain = 5.0f;

        /// <summary>The images must show: the textured view has at least this much more fine detail than the flat one.</summary>
        private const float MinDetailGain = 1.1f;

        /// <summary>
        /// PRD 7.2 in the rendered start view: of every red pixel of the frame (ModelMath.IsRed), at least this fraction lies
        /// on the player furniture's screen box (the floor, walls and props in their real colours must never read as red).
        /// </summary>
        private const float MinPlayerRedShare = 0.85f;

        private Main main;
        private GameState Game => main.Game;
        private readonly List<string> errors = new List<string>();

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            ModelKit.Disabled = false;
            TextureLibrary.Disabled = false;
            errors.Clear();
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.IsNotNull(Game.Level, "the level was never built");
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            ModelKit.Disabled = false;
            TextureLibrary.Disabled = false;
            Application.logMessageReceived -= OnLog;
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            yield return null;
        }

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                errors.Add(condition);
            }
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private IEnumerator LoadLevel(string id)
        {
            Game.LoadLevel(id);
            Assert.AreEqual(id, Game.LevelId);
            yield return Steps(2);
        }

        // ----- What a slot shows -----

        private struct Slot
        {
            public Renderer Renderer;
            public int Index;
            public Material Material;
            public Texture Texture;
            public Vector4 St;
            public Surface Surface;
        }

        /// <summary>Every URP Lit slot of the enabled, active renderers under <paramref name="root"/>, with what its property block shows.</summary>
        private static List<Slot> LitSlots(Transform root)
        {
            var slots = new List<Slot>();
            var block = new MaterialPropertyBlock();
            foreach (Renderer r in root.GetComponentsInChildren<Renderer>(false))
            {
                if (!r.enabled)
                {
                    continue;
                }
                Material[] materials = r.sharedMaterials;
                for (int i = 0; i < materials.Length; i++)
                {
                    Material m = materials[i];
                    if (m == null || m.shader == null || m.shader.name != PrimitiveKit.LitShaderName)
                    {
                        continue;
                    }
                    r.GetPropertyBlock(block, i);
                    Texture texture = block.isEmpty ? null : block.GetTexture(BaseMap);
                    // M7 faces (CharacterLook): the head and garment surfaces show the product owner's prints, not
                    // a library detail; Step22c checks the humans wear them.
                    if (CharacterLook.IsCharacterTexture(texture))
                    {
                        continue;
                    }
                    slots.Add(new Slot
                    {
                        Renderer = r,
                        Index = i,
                        Material = m,
                        Texture = texture,
                        St = block.isEmpty ? Vector4.zero : block.GetVector(BaseMapSt),
                        Surface = TextureLibrary.SurfaceOf(texture),
                    });
                }
            }
            return slots;
        }

        private static string Label(Slot s)
        {
            string parent = s.Renderer.transform.parent != null ? s.Renderer.transform.parent.name : "";
            return $"{parent}/{s.Renderer.name}[{s.Index}] ({s.Material.name})";
        }

        /// <summary>
        /// The library resolves a detail and a colour map for every textured surface, and the player's own colour map
        /// (the premise of every step).
        /// </summary>
        private static void AssertLibrary()
        {
            TextureLibrary library = TextureLibrary.Load();
            Assert.IsNotNull(library, $"premise: no Resources/{TextureLibrary.ResourcePath}");
            foreach (Surface s in TextureLibrary.Textured)
            {
                Assert.IsNotNull(TextureLibrary.TextureOf(s), $"premise: the library has no detail for {s}");
                Assert.IsNotNull(TextureLibrary.ColourOf(s), $"premise: the library has no colour map for {s}");
            }
            Assert.IsNotNull(TextureLibrary.PlayerColour, "premise: the library has no player colour map");
        }

        private static bool OnInhabitant(Slot s) => s.Renderer.GetComponentInParent<Inhabitant>() != null;

        /// <summary>
        /// The surface each slot of every model visual must show, by the name of its source material in the catalog
        /// prefab (renderers matched by their path under the model root: the rig adds brows under the head bone).
        /// </summary>
        private static Dictionary<(Renderer, int), Surface> ExpectedModelSurfaces(LevelInstance level)
        {
            var expected = new Dictionary<(Renderer, int), Surface>();
            foreach (GameObject model in level.ModelVisuals)
            {
                string id = model.name.Substring(ModelKit.RootPrefix.Length);
                ModelCatalog.Entry entry = ModelCatalog.Lookup(id);
                Assert.IsNotNull(entry, "premise: no catalog entry for " + id);
                bool flat = id == ModelCatalog.KenneyRug || id == ModelCatalog.KenneyDoormat;
                var source = new Dictionary<string, Renderer>();
                foreach (Renderer r in entry.prefab.GetComponentsInChildren<Renderer>(true))
                {
                    source[PathUnder(r.transform, entry.prefab.transform)] = r;
                }
                int matched = 0;
                foreach (Renderer r in model.GetComponentsInChildren<Renderer>(true))
                {
                    if (!source.TryGetValue(PathUnder(r.transform, model.transform), out Renderer original))
                    {
                        continue;
                    }
                    Material[] names = original.sharedMaterials;
                    for (int i = 0; i < names.Length; i++)
                    {
                        expected[(r, i)] = ModelKit.SurfaceOf(names[i].name, flat);
                    }
                    matched++;
                }
                Assert.AreEqual(source.Count, matched, $"premise: every renderer of the {id} prefab is found in its instance");
            }
            return expected;
        }

        private static string PathUnder(Transform t, Transform root)
        {
            var parts = new List<string>();
            for (Transform c = t; c != null && c != root; c = c.parent)
            {
                parts.Add(c.name);
            }
            parts.Reverse();
            return string.Join("/", parts);
        }

        /// <summary>
        /// The procedural parts that show no detail: the garden, books and leaves (small and saturated), the metal frames
        /// (the near-black), the procedural inhabitant's face and the brows of any inhabitant (on its skin's near-black).
        /// M8 (docs/m8/ROOMS_PLAN.md 3): the room objects' white ceramic (glaze shows no grain). PLANT (2026-11-24): the plants'
        /// glazed pot, in the pot colour, for the same reason.
        /// </summary>
        private bool PlainAllowed(Slot s)
        {
            string name = s.Renderer.name;
            if (name == "Garden" || name.StartsWith("Books", StringComparison.Ordinal) || name == "Leaves" || name == "PotShape")
            {
                return true;
            }
            Color? palette = PrimitiveKit.PaletteOf(s.Material);
            if (palette.HasValue && (Same(palette.Value, FurnitureKit.FrameColor) || Same(palette.Value, FurnitureKit.CeramicColor)))
            {
                return true;
            }
            Inhabitant owner = s.Renderer.GetComponentInParent<Inhabitant>();
            return owner != null && !(s.Renderer is SkinnedMeshRenderer);
        }

        private static bool Same(Color a, Color b)
        {
            Color32 x = a;
            Color32 y = b;
            return x.r == y.r && x.g == y.g && x.b == y.b;
        }

        private static readonly Dictionary<string, Surface[]> PropSurfaces = new Dictionary<string, Surface[]>
        {
            ["sofa"] = new[] { Surface.Upholstery },
            ["armchair"] = new[] { Surface.Upholstery },
            ["bookshelf"] = new[] { Surface.Wood },
            ["table"] = new[] { Surface.Wood, Surface.Linen },
            ["cabinet"] = new[] { Surface.Wood },
            ["counter"] = new[] { Surface.Wood, Surface.Plaster },
            // PLANT (2026-11-24): ficus or banana, the dark soil and wood (Soil) and the leaves (Foliage); the pot is plain glaze.
            ["plant"] = new[] { Surface.Soil, Surface.Foliage },
            // M8 room objects, procedural or with their Kenney model (ceramic and the near-black stay plain).
            [PropKinds.Bathtub] = new[] { Surface.Metal },
            [PropKinds.Washbasin] = new[] { Surface.Wood, Surface.Metal },
            [PropKinds.Toilet] = new[] { Surface.Metal },
            [PropKinds.KitchenSink] = new[] { Surface.Wood, Surface.Plaster, Surface.Metal },
            [PropKinds.Stove] = new[] { Surface.Metal },
            [PropKinds.Fridge] = new[] { Surface.Metal },
            [PropKinds.CoffeeTable] = new[] { Surface.Wood },
            [PropKinds.TvUnit] = new[] { Surface.Wood, Surface.Metal },
            [PropKinds.Bed] = new[] { Surface.Wood, Surface.Linen, Surface.Upholstery },
            [PropKinds.Nightstand] = new[] { Surface.Wood, Surface.Metal },
        };

        // M6 (CONTRACT_M6 2.4): the player's own furniture (never a decoy or a prop) shows the glossy lacquer finish
        // instead of its usual surface, whatever its body kind.
        private static readonly Dictionary<string, Surface> BodySurface = new Dictionary<string, Surface>
        {
            [BodyKinds.Chair] = Surface.Lacquer,
            [BodyKinds.Stool] = Surface.Lacquer,
            [BodyKinds.Armchair] = Surface.Lacquer,
            [BodyKinds.FloorLamp] = Surface.Lacquer,
            [BodyKinds.OfficeChair] = Surface.Lacquer,
            [BodyKinds.RockingChair] = Surface.Lacquer,
        };

        // ----- 22c -----

        /// <summary>
        /// On every level: every URP Lit slot shows its texture, except the few that must stay plain; floors are
        /// parquet (hard), carpet (soft) or tile, wall faces and caps plaster, rugs and the doormat carpet; each prop, the
        /// player body and the decoys show the surfaces of what they are made of; every model slot shows the surface of
        /// its source material, so the inhabitants' clothes are linen and their skin plain, on a skinned mesh that now
        /// has UVs. M7 real colours (CONTRACT_M7 5): outside the inhabitants, every textured slot shows a colour map
        /// through its surface's one white-based material, the player furniture through its own red one, and no other
        /// slot shows the player's red image. The budgets of PRD 7.4 hold (one material per surface now).
        /// </summary>
        [UnityTest]
        public IEnumerator Step22c_EveryMaterialHasItsDetailTexture()
        {
            AssertLibrary();
            Assert.GreaterOrEqual(Game.LevelOrder.Count, 7, "premise: levels.json lists the seven levels");
            var table = new List<string>();
            // The head image of each gender (keyed by "female"): one shared texture, whatever the character.
            var heads = new Dictionary<bool, Texture>();
            foreach (string id in Game.LevelOrder.ToList())
            {
                yield return LoadLevel(id);
                LevelInstance level = Game.Level;
                Assert.Greater(level.ModelVisuals.Count, 0, $"{id}: premise: no model visual");
                List<Slot> slots = LitSlots(level.Root.transform);
                Assert.Greater(slots.Count, 20, $"{id}: premise: few Lit slots");
                Dictionary<(Renderer, int), Surface> models = ExpectedModelSurfaces(level);

                int detailed = 0;
                int coloured = 0;
                var missing = new List<string>();
                foreach (Slot s in slots)
                {
                    if (s.Texture != null)
                    {
                        detailed++;
                        Assert.AreNotEqual(Surface.Plain, s.Surface, $"{id}: {Label(s)} shows a texture that is not in the library ({s.Texture.name})");
                        Assert.Greater(s.St.x, 0f, $"{id}: {Label(s)} has no tiling");
                        if (!OnInhabitant(s))
                        {
                            // M7 real colours: the image in its own colours, under its surface's one white-based material.
                            Assert.IsTrue(TextureLibrary.IsColourMap(s.Texture), $"{id}: {Label(s)} shows {s.Texture.name}, not its image in real colours");
                            bool mine = s.Renderer.transform.IsChildOf(Game.Furniture.transform);
                            Material want = s.Texture == TextureLibrary.PlayerColour
                                ? PrimitiveKit.PlayerMaterial(PrimitiveKit.PaletteOf(s.Material) ?? Color.clear)
                                : PrimitiveKit.SurfaceMaterial(s.Surface);
                            Assert.AreSame(want, s.Material, $"{id}: {Label(s)} is not drawn with its surface's one material");
                            Assert.IsTrue(s.Texture != TextureLibrary.PlayerColour || mine, $"{id}: {Label(s)} shows the player's red image (PRD 7.2)");
                            Color baseColour = s.Material.GetColor("_BaseColor");
                            Assert.That(Mathf.Min(baseColour.r, Mathf.Min(baseColour.g, baseColour.b)), Is.EqualTo(1f).Within(1e-4f),
                                $"{id}: {Label(s)}: the base colour is not white, the image's colours are tinted");
                            coloured++;
                        }
                        else
                        {
                            Assert.IsFalse(TextureLibrary.IsColourMap(s.Texture), $"{id}: {Label(s)}: an inhabitant keeps its palette colour (CharacterLook)");
                        }
                    }
                    if (models.TryGetValue((s.Renderer, s.Index), out Surface wanted))
                    {
                        // M6 (CONTRACT_M6 2.4): the player's own furniture may show lacquer instead of its catalog
                        // surface (ModelKit.Paint's main-slot override); Step50a_ (ProbeTestsM6Textures) checks that
                        // override itself, so here it is simply accepted wherever it appears, on the player only.
                        bool playerLacquer = s.Surface == Surface.Lacquer && s.Renderer.transform.IsChildOf(Game.Furniture.transform);
                        if (!playerLacquer)
                        {
                            Assert.AreEqual(wanted, s.Surface, $"{id}: model slot {Label(s)}");
                        }
                    }
                    else if (s.Surface == Surface.Plain && !PlainAllowed(s))
                    {
                        missing.Add(Label(s));
                    }
                }
                CollectionAssert.IsEmpty(missing, $"{id}: Lit slots without their detail texture");
                // Two fifths, not half (2026-11-20): walls and floors moved to the shared Texture2DArray shader and no
                // longer count as Lit slots, while plain fixture and handle slots remain; the per-slot check above is
                // the real guard, this ratio only catches a wholesale loss of textures.
                Assert.Greater(detailed, slots.Count * 2 / 5, $"{id}: only {detailed} of {slots.Count} slots show a detail");
                Assert.Greater(coloured, slots.Count / 3, $"{id}: only {coloured} of {slots.Count} slots show an image in real colours");

                // Floors, walls, caps.
                bool soft = Game.Def.AllRooms().Any(r => r.IsSoft);
                // M7 (CONTRACT_M7 1.2): a room can also set its own "floorFinish": "tile" (kitchen, bathroom).
                bool tiled = Game.Def.AllRooms().Any(r => r.IsTile);
                // M8 floor finishes (docs/m8/ROOMS_PLAN.md 4): a floor may also show the marble, herringbone or carpet
                // finish one of the level's rooms asks for.
                var floorFinishes = new HashSet<Surface>(Game.Def.AllRooms().Select(r => TextureLibrary.FloorSurface(r.FloorFinish, r.IsSoft)));
                // Walls 4 (WallArray): the floors are drawn with the one room surface material too, their looks named by
                // their vertices; every look a room asks for shows.
                var floors = level.Root.GetComponentsInChildren<Renderer>(false)
                    .Where(r => r.enabled && r.gameObject.layer == Layers.Floor && r.name != "Garden").ToList();
                Assert.Greater(floors.Count, 0, $"{id}: premise: no floor renderer");
                var floorShown = new HashSet<Surface>();
                foreach (Renderer r in floors)
                {
                    Assert.IsTrue(WallArray.IsWallMaterial(r.sharedMaterial), $"{id}: floor {r.name} is not drawn with the room surface material");
                    Assert.IsFalse(r.HasPropertyBlock(), $"{id}: floor {r.name} carries a property block");
                    floorShown.UnionWith(WallArray.SurfacesOf(ModelKit.MeshOf(r)));
                }
                foreach (Surface s in floorShown)
                {
                    Assert.IsTrue(s == Surface.Parquet || (soft && s == Surface.Carpet) || (tiled && s == Surface.Tile) || floorFinishes.Contains(s),
                        $"{id}: a floor shows {s}");
                }
                CollectionAssert.IsSubsetOf(floorFinishes, floorShown, $"{id}: a room's floor look does not show");
                // Wall finishes (2026-11-19): a face shows the crepi or a finish one of the level's rooms asks for, and
                // every finish asked for shows; caps stay plaster. Walls 4 (WallArray): every face, cap and stub is drawn
                // with the one wall material, its finishes named by its vertices (no property block, no URP Lit slot).
                Material wallMaterial = WallArray.Material;
                Assert.IsNotNull(wallMaterial, $"{id}: premise: the library has no wall material");
                var walls = level.Root.GetComponentsInChildren<Renderer>(false)
                    .Where(r => r.enabled && (r.name == "Face" || r.name == "Cap" || r.name == LevelBuilder.StubName)).ToList();
                Assert.Greater(walls.Count, 3, $"{id}: premise: no wall faces");
                var finishes = new HashSet<Surface>(Game.Def.AllRooms().Select(r => TextureLibrary.WallSurface(r.WallFinish)));
                var shown = new HashSet<Surface>();
                foreach (Renderer r in walls)
                {
                    Assert.AreSame(wallMaterial, r.sharedMaterial, $"{id}: wall {r.name} is not drawn with the wall material");
                    Assert.IsFalse(r.HasPropertyBlock(), $"{id}: wall {r.name} carries a property block");
                    HashSet<Surface> named = WallArray.SurfacesOf(ModelKit.MeshOf(r));
                    Assert.IsNotEmpty(named, $"{id}: wall {r.name}: its vertices name no finish");
                    if (r.name != "Face")
                    {
                        CollectionAssert.AreEquivalent(new[] { Surface.Plaster }, named, $"{id}: wall {r.name} (cap, closure, stub)");
                        continue;
                    }
                    foreach (Surface s in named)
                    {
                        Assert.IsTrue(s == Surface.Plaster || finishes.Contains(s), $"{id}: wall face shows {s}");
                    }
                    shown.UnionWith(named);
                }
                foreach (Surface finish in finishes)
                {
                    Assert.IsTrue(shown.Contains(finish), $"{id}: no wall face shows the {finish} finish");
                }

                // Rugs and the doormat: unchanged (every slot Surface.Carpet), plus the M7 rug image (product owner,
                // 2026-11-18): BuildRugImage's own extra quad, the picture exactly once, also Surface.Carpet.
                for (int i = 0; i < Game.Def.Rugs.Count; i++)
                {
                    Transform rug = level.Root.transform.Find("Rug " + (i + 1));
                    Assert.IsNotNull(rug, $"{id}: no Rug {i + 1}");
                    AssertAll(LitSlots(rug), Surface.Carpet, $"{id} rug {i + 1}");
                }
                Transform doormat = level.Root.transform.Find("Doormat");
                Assert.IsNotNull(doormat, $"{id}: no doormat");
                AssertAll(LitSlots(doormat), Surface.Carpet, id + " doormat");

                // Props by kind, the player body, the decoys.
                foreach (PropDef prop in Game.Def.Props)
                {
                    Transform t = level.Root.transform.Find(prop.Name);
                    Assert.IsNotNull(t, $"{id}: no prop {prop.Name}");
                    if (PropSurfaces.TryGetValue(prop.Kind, out Surface[] want))
                    {
                        List<Slot> mine = LitSlots(t);
                        foreach (Surface w in want)
                        {
                            Assert.IsTrue(mine.Any(s => s.Surface == w), $"{id}: prop {prop.Name} ({prop.Kind}) shows no {w}: {string.Join(", ", mine.Select(s => s.Surface).Distinct())}");
                        }
                    }
                }
                string body = Game.Def.PlayerBody().Kind;
                List<Slot> player = LitSlots(Game.Furniture.transform);
                Assert.Greater(player.Count, 0, $"{id}: premise: the player furniture has no Lit slot");
                Assert.IsTrue(player.Any(s => s.Surface == BodySurface[body]), $"{id}: the {body} shows no {BodySurface[body]}");
                // M7 real colours (CONTRACT_M7 5): the player's own furniture shows the owner's red image (PlayerMaterial).
                Material red = PrimitiveKit.PlayerMaterial(LevelJson.ParseColor(Game.Def.Player.Color, Color.red));
                Assert.IsTrue(player.Any(s => s.Material == red), $"{id}: premise: the player furniture is not in the player colour");
                Assert.IsTrue(player.Where(s => s.Material == red).All(s => s.Texture == TextureLibrary.PlayerColour),
                    $"{id}: a slot of the player colour does not show the player's red image");
                foreach (Decoy decoy in level.Decoys)
                {
                    // A decoy is the player's furniture kind in real colours, never its red (PRD 7.2).
                    List<Slot> decoySlots = LitSlots(decoy.transform);
                    Assert.IsTrue(decoySlots.Any(s => s.Texture != null), $"{id}: decoy {decoy.Id} shows no detail");
                    Assert.IsFalse(decoySlots.Any(s => s.Texture == TextureLibrary.PlayerColour), $"{id}: decoy {decoy.Id} shows the player's red image");
                }

                // Humans share a projected mesh derived from the selected catalog model.
                foreach (Inhabitant h in level.Inhabitants)
                {
                    var skin = h.GetComponentInChildren<SkinnedMeshRenderer>(true);
                    Assert.IsNotNull(skin, $"{id}: premise: {h.name} is not skinned");
                    Mesh mesh = skin.sharedMesh;
                    Assert.IsTrue(mesh.HasVertexAttribute(VertexAttribute.TexCoord0), $"{id}: {h.name}'s mesh has no UVs");
                    var uv = new List<Vector2>();
                    mesh.GetUVs(0, uv);
                    Assert.AreEqual(mesh.vertexCount, uv.Count, $"{id}: {h.name}: UV count");
                    Assert.Greater(uv.Distinct().Count(), mesh.vertexCount / 4, $"{id}: {h.name}: degenerate UVs");
                    InhabitantDef def = Game.Def.Inhabitants.First(d => d.Name == h.name);
                    // M5: a personality inhabitant names no model; the rig holds the catalog entry it was built from.
                    Assert.IsNotNull(h.Rig, $"{id}: premise: {h.name} has no rig");
                    ModelCatalog.Entry entry = h.Rig.Entry;
                    Assert.IsNotNull(entry, $"{id}: premise: {h.name}'s rig has no catalog entry");
                    if (entry.kind == "pet")
                    {
                        continue; // the dog has no clothes: its fur shows no detail (watchers, M5)
                    }
                    Mesh prefabMesh = entry.prefab.GetComponentInChildren<SkinnedMeshRenderer>(true).sharedMesh;
                    Assert.IsTrue(CharacterLook.UsesProjection(prefabMesh, mesh), $"{id}: {h.name} uses the wrong projected mesh");
                    CollectionAssert.AreEqual(prefabMesh.bindposes, mesh.bindposes, $"{id}: {h.name}'s binding was changed");
                    // M7 faces (CharacterLook): the shirt and trousers show the clothes prints instead of the linen, in
                    // their real colours (a white base colour; the personality's colour is banded into its own copy).
                    var garment = new MaterialPropertyBlock();
                    bool dressed = false;
                    for (int slot = 0; slot < skin.sharedMaterials.Length; slot++)
                    {
                        skin.GetPropertyBlock(garment, slot);
                        dressed |= !garment.isEmpty && CharacterLook.IsClothesTexture(garment.GetTexture(BaseMap))
                            && garment.GetColor("_BaseColor") == Color.white;
                    }
                    Assert.IsTrue(dressed, $"{id}: {h.name}'s clothes show no print");
                    Assert.IsTrue(h.Rig.HasPaintedHead, $"{id}: {h.name} has no painted head");
                    Material[] sources = entry.prefab.GetComponentInChildren<SkinnedMeshRenderer>(true).sharedMaterials;
                    int skinSlot = Array.FindIndex(sources, m => m.name == "Skin");
                    Assert.GreaterOrEqual(skinSlot, 0, $"premise: {entry.id} has a Skin material");
                    skin.GetPropertyBlock(garment, skinSlot);
                    Texture portrait = garment.GetTexture(BaseMap);
                    Assert.AreEqual(Surface.Plain, TextureLibrary.SurfaceOf(portrait), $"{id}: {h.name}'s skin uses an environment texture");
                    Assert.IsTrue(CharacterLook.IsCharacterTexture(portrait), $"{id}: {h.name}'s skin shows no portrait");
                    // The product owner's head image in its own colours: a white base colour and the same image for
                    // every head of a gender, so no character gets its own skin or hair colour.
                    Assert.AreEqual(Color.white, garment.GetColor("_BaseColor"), $"{id}: {h.name}'s head image is tinted");
                    bool female = CharacterLook.IsFemale(entry);
                    if (heads.TryGetValue(female, out Texture shared))
                    {
                        Assert.AreSame(shared, portrait, $"{id}: {h.name}'s head image differs from the other {(female ? "women" : "men")}'s");
                    }
                    else
                    {
                        heads[female] = portrait;
                    }
                    Vector3[] normals = mesh.normals;
                    int[] head = mesh.GetTriangles(skinSlot).Where(vertex => uv[vertex].y > 0.05f).Distinct().ToArray();
                    Assert.IsNotEmpty(head, $"{id}: {h.name}'s skin has no wrapped head vertices");
                    Assert.IsTrue(head.All(vertex => normals[vertex].sqrMagnitude > 0.9f),
                        $"{id}: {h.name}'s head contains unlit vertices with missing normals");
                }

                Renderer[] drawn = level.Root.GetComponentsInChildren<Renderer>(false);
                Probe.RenderCount count = Probe.CountRenderers(drawn);
                // PRD 7.4 v1.7, CONTRACT_M5 16.11: a house of HouseBudgetRooms rooms or more has the house budget.
                bool house = Game.Def.AllRooms().Count >= Tuning.HouseBudgetRooms;
                Assert.LessOrEqual(count.Materials.Count, house ? Tuning.BudgetHouseMaterials : Tuning.BudgetMaterials, $"{id}: materials");
                // CONTRACT_M5 16.11 and 17: the draw call budget counts material slots (draw calls), not renderers. The
                // probe's count must be every slot of every drawn renderer, counted here independently.
                int slotsHere = drawn.Where(r => r.enabled && r.gameObject.activeInHierarchy).Sum(r => r.sharedMaterials.Length);
                Assert.Greater(slotsHere, 0, $"{id}: premise: no material slot drawn");
                Assert.AreEqual(slotsHere, count.MaterialSlots, $"{id}: Probe.CountRenderers does not count every material slot as a draw call");
                Assert.LessOrEqual(count.MaterialSlots, house ? Tuning.BudgetHouseRenderers : Tuning.BudgetRenderers,
                    $"{id}: draw calls (material slots; {count.Renderers} renderers)");
                table.Add($"{id}: {count.Renderers} renderers, {count.MaterialSlots} draw calls, {count.Materials.Count} materials, {detailed} of {slots.Count} Lit slots detailed");
            }
            Debug.Log("[Step22c] " + string.Join(" | ", table));
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        private static void AssertAll(List<Slot> slots, Surface surface, string label)
        {
            Assert.Greater(slots.Count, 0, label + ": premise: no Lit slot");
            foreach (Slot s in slots)
            {
                Assert.AreEqual(surface, s.Surface, $"{label}: {Label(s)}");
            }
        }

        // ----- 22d -----

        /// <summary>
        /// M7 real colours (CONTRACT_M7 5, product owner decision of 2026-11-18). Numerically: each textured surface's one
        /// material has a white base colour, its own sRGB colour map as base map and its surface's finish; the player's
        /// material has a white base colour, the owner's red image and the painted metal finish, and that image reads as
        /// red. Rendered: on level 1 (the red chair) and level 5 (the red armchair), the start view is rendered textured,
        /// then flat (TextureLibrary.Disabled: the palette materials and no image, the same level rebuilt at the same
        /// step): the textured view has clearly more fine detail than the flat one (the images read as a pattern) but stays
        /// under the noise cap, and the player furniture is still the one saturated red region of the frame: nearly every
        /// red pixel of the textured view lies on it, and its red is saturated.
        /// </summary>
        [UnityTest]
        public IEnumerator Step22d_ImageColoursShowAndThePlayerStaysTheRedOne()
        {
            AssertLibrary();
            foreach (Surface s in TextureLibrary.Textured)
            {
                Material m = PrimitiveKit.SurfaceMaterial(s);
                Assert.IsNotNull(m, $"{s}: no colour material");
                Assert.AreSame(TextureLibrary.ColourOf(s), m.GetTexture(BaseMap), $"{s}: its material does not show its colour map");
                AssertWhite(m, s.ToString());
                Assert.IsTrue(TextureLibrary.ColourFinishOf(s, out float smoothness, out float metallic), $"{s}: no finish");
                Assert.That(m.GetFloat("_Smoothness"), Is.EqualTo(smoothness).Within(1e-4f), $"{s}: smoothness");
                Assert.That(m.GetFloat("_Metallic"), Is.EqualTo(metallic).Within(1e-4f), $"{s}: metallic");
                Color? mean = TextureLibrary.MeanColourOf(TextureLibrary.ColourOf(s));
                Assert.IsTrue(mean.HasValue && mean.Value.maxColorComponent > 0.005f, $"{s}: the colour map's mean colour was not measured");
                // PRD 7.2: no surface image may read as the player's red.
                Assert.IsFalse(ModelMath.IsRed(mean.Value.gamma), $"{s}: its image reads as red ({Hex(mean.Value.gamma)})");
            }
            Color? playerMean = TextureLibrary.MeanColourOf(TextureLibrary.PlayerColour);
            Assert.IsTrue(playerMean.HasValue, "premise: the player colour map's mean colour was not measured");
            Assert.IsTrue(ModelMath.IsRed(playerMean.Value.gamma), $"the player's image does not read as red ({Hex(playerMean.Value.gamma)})");
            // M7 rug image (product owner, 2026-11-18): the rug's and the doormat's own picture, checked the same way
            // as every other surface above: its mean colour, not any one of its pixels, must not read as the player's red.
            Color? rugMean = TextureLibrary.MeanColourOf(TextureLibrary.RugColour);
            Assert.IsTrue(rugMean.HasValue, "premise: the rug image's mean colour was not measured");
            Assert.IsFalse(ModelMath.IsRed(rugMean.Value.gamma), $"the rug image reads as red ({Hex(rugMean.Value.gamma)})");

            int checkedMaterials = 0;
            foreach (string id in new[] { "level1", "level5" })
            {
                yield return LoadLevel(id);
                Material playerMaterial = PrimitiveKit.PlayerMaterial(LevelJson.ParseColor(Game.Def.Player.Color, Color.red));
                Assert.IsNotNull(playerMaterial, $"{id}: no player material");
                Assert.AreSame(TextureLibrary.PlayerColour, playerMaterial.GetTexture(BaseMap), $"{id}: the player material does not show the red image");
                AssertWhite(playerMaterial, id + " player");
                Assert.That(playerMaterial.GetFloat("_Smoothness"), Is.EqualTo(Tuning.PlayerSmoothness).Within(1e-4f), $"{id}: player smoothness");
                Assert.That(playerMaterial.GetFloat("_Metallic"), Is.EqualTo(Tuning.PlayerMetallic).Within(1e-4f), $"{id}: player metallic");
                // Every material that shows an image outside the inhabitants is a white-based colour material.
                foreach (Material m in LitSlots(Game.Level.Root.transform).Where(s => s.Texture != null && !OnInhabitant(s)).Select(s => s.Material).Distinct())
                {
                    AssertWhite(m, $"{id}: {m.name}");
                    checkedMaterials++;
                }

                // Side by side: textured, then flat.
                Color32[] textured = null;
                Color32[] plain = null;
                int width = 640;
                int height = 360;
                Rect player = default;
                var rugBoxes = new List<Rect>();
                foreach (bool flat in new[] { false, true })
                {
                    TextureLibrary.Disabled = flat;
                    Game.Restart();
                    yield return Steps(3);
                    Game.Camera.Snap();
                    yield return null;
                    yield return null;
                    List<Slot> all = LitSlots(Game.Level.Root.transform);
                    if (flat)
                    {
                        Assert.IsFalse(all.Any(s => s.Texture != null), $"{id}: control: TextureLibrary.Disabled still shows details");
                    }
                    else
                    {
                        // Walls 4 (WallArray): the walls and floors are a few renderers of the room surface material, their
                        // images named per vertex; they count with the URP Lit slots that show an image.
                        int roomSurfaces = Game.Level.Root.GetComponentsInChildren<Renderer>(false).Count(r => WallArray.IsWallMaterial(r.sharedMaterial));
                        Assert.Greater(roomSurfaces, 0, $"{id}: premise: no wall or floor of the room surface material");
                        Assert.Greater(all.Count(s => s.Texture != null) + roomSurfaces, 20, $"{id}: premise: few textured slots");
                    }
                    Camera cam = main.Camera;
                    // The boxes are projected with the camera's own aspect: pinned to the render's (2026-11-20), else
                    // a box near the frame's edge (the doormat, an inhabitant) lands off what the render shows there.
                    cam.aspect = width / (float)height;
                    Rect box = ScreenBox(cam, Game.Furniture.transform, width, height);
                    Color32[] pixels = RenderPixels(cam, width, height);
                    if (flat)
                    {
                        plain = pixels;
                    }
                    else
                    {
                        textured = pixels;
                        player = box;
                        // M7 rug image (product owner, 2026-11-18): the rug's and the doormat's own picture, like
                        // every other surface's image, is only checked by its mean colour for PRD 7.2 (above:
                        // TextureLibrary.RugColour's mean is not red), never pixel by pixel; a patch of it can still
                        // read as red on its own (ModelMath.IsRed), so its own screen box is exempt below, same as
                        // the player's.
                        rugBoxes.Clear();
                        for (int i = 0; i < Game.Def.Rugs.Count; i++)
                        {
                            Transform rug = Game.Level.Root.transform.Find("Rug " + (i + 1));
                            if (rug != null)
                            {
                                rugBoxes.Add(ScreenBox(cam, rug, width, height));
                            }
                        }
                        Transform doormat = Game.Level.Root.transform.Find("Doormat");
                        if (doormat != null)
                        {
                            rugBoxes.Add(ScreenBox(cam, doormat, width, height));
                        }
                        // The heads wear the product owner's own wrap-around images (2026-11-18, auburn hair
                        // included): like the rug's, that picture is the owner's, not a red prop, so each
                        // inhabitant's screen box is exempt too.
                        foreach (Inhabitant inhabitant in Game.Level.Inhabitants)
                        {
                            if (inhabitant != null)
                            {
                                rugBoxes.Add(ScreenBox(cam, inhabitant.transform, width, height));
                            }
                        }
                    }
                    cam.ResetAspect();
                }
                TextureLibrary.Disabled = false;

                float gain = FineDetail(textured, width, height) / Mathf.Max(1e-4f, FineDetail(plain, width, height));
                Debug.Log($"[Step22d] {id}: fine detail textured / flat = {gain:0.000}");
                Assert.Greater(gain, MinDetailGain, $"{id}: the textured view has hardly more fine detail than the flat one: the images do not show");
                Assert.Less(gain, MaxDetailGain, $"{id}: the textured view is noisy ({gain:0.00} times the fine detail of the flat one)");
                AssertPlayerIsTheRedOne(textured, width, height, player, rugBoxes, id);
            }
            Assert.Greater(checkedMaterials, 5, "premise: few colour materials checked");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        private static void AssertWhite(Material m, string label)
        {
            Color c = m.GetColor("_BaseColor");
            Assert.That(Mathf.Min(c.r, Mathf.Min(c.g, c.b)), Is.EqualTo(1f).Within(1e-4f), $"{label}: base colour {Hex(c)} is not white: the image's own colours are tinted");
        }

        /// <summary>
        /// PRD 7.2 on the rendered frame: the red pixels (ModelMath.IsRed) are found on the player furniture's screen box
        /// (<paramref name="box"/>), at least <see cref="MinPlayerRedShare"/> of all of them, and their mean is a saturated
        /// red. M7 rug image (product owner, 2026-11-18): a red pixel inside <paramref name="exempt"/> (the rug's or the
        /// doormat's own screen box) counts neither for nor against the player: its picture is checked by its mean colour
        /// only (above, like every other surface's), never pixel by pixel.
        /// </summary>
        private static void AssertPlayerIsTheRedOne(Color32[] pixels, int width, int height, Rect box, List<Rect> exempt, string label)
        {
            int inside = 0;
            int outside = 0;
            Color sum = Color.clear;
            for (int y = 0; y < height; y++)
            {
                for (int x = 0; x < width; x++)
                {
                    Color32 p = pixels[y * width + x];
                    if (!ModelMath.IsRed(p))
                    {
                        continue;
                    }
                    var point = new Vector2(x + 0.5f, y + 0.5f);
                    if (box.Contains(point))
                    {
                        inside++;
                        sum += p;
                    }
                    else if (!exempt.Any(r => r.Contains(point)))
                    {
                        outside++;
                    }
                }
            }
            float share = inside / (float)Mathf.Max(1, inside + outside);
            Color mean = inside > 0 ? sum / inside : Color.clear;
            Color.RGBToHSV(mean, out _, out float saturation, out _);
            Debug.Log($"[Step22d] {label}: {inside} red px on the player furniture, {outside} elsewhere (share {share:0.000}), its mean red {Hex(mean)}, saturation {saturation:0.00}");
            Assert.Greater(inside, 40, $"{label}: premise: the player furniture shows only {inside} red pixels ({box})");
            Assert.GreaterOrEqual(share, MinPlayerRedShare, $"{label}: {outside} red pixels lie off the player furniture (it is no longer the one red thing, PRD 7.2)");
            Assert.Greater(saturation, 0.6f, $"{label}: the player furniture's red is washed out ({Hex(mean)})");
        }

        private static string Hex(Color c) => "#" + ColorUtility.ToHtmlStringRGB(c);

        /// <summary>Mean absolute difference between horizontally and vertically adjacent pixels (luma, 0 to 255).</summary>
        private static float FineDetail(Color32[] p, int width, int height)
        {
            double sum = 0;
            long n = 0;
            for (int y = 0; y < height - 1; y++)
            {
                for (int x = 0; x < width - 1; x++)
                {
                    int i = y * width + x;
                    float l = Luma(p[i]);
                    sum += Mathf.Abs(l - Luma(p[i + 1])) + Mathf.Abs(l - Luma(p[i + width]));
                    n += 2;
                }
            }
            return n > 0 ? (float)(sum / n) : 0f;
        }

        private static float Luma(Color32 c) => 0.2126f * c.r + 0.7152f * c.g + 0.0722f * c.b;

        /// <summary>The screen rectangle (render pixels) of every renderer under <paramref name="root"/>.</summary>
        private static Rect ScreenBox(Camera cam, Transform root, int width, int height)
        {
            float xMin = float.MaxValue, yMin = float.MaxValue, xMax = float.MinValue, yMax = float.MinValue;
            foreach (Renderer r in root.GetComponentsInChildren<Renderer>(false))
            {
                Bounds b = r.bounds;
                for (int k = 0; k < 8; k++)
                {
                    var corner = new Vector3((k & 1) == 0 ? b.min.x : b.max.x, (k & 2) == 0 ? b.min.y : b.max.y, (k & 4) == 0 ? b.min.z : b.max.z);
                    Vector3 v = cam.WorldToViewportPoint(corner);
                    xMin = Mathf.Min(xMin, v.x * width);
                    xMax = Mathf.Max(xMax, v.x * width);
                    yMin = Mathf.Min(yMin, v.y * height);
                    yMax = Mathf.Max(yMax, v.y * height);
                }
            }
            return xMax > xMin ? Rect.MinMaxRect(xMin, yMin, xMax, yMax) : default;
        }

        private static Color32[] RenderPixels(Camera cam, int width, int height)
        {
            RenderTexture rt = RenderTexture.GetTemporary(width, height, 24);
            var request = new RenderPipeline.StandardRequest { destination = rt };
            Assert.IsTrue(RenderPipeline.SupportsRenderRequest(cam, request), "premise: the pipeline cannot render the camera to a texture");
            RenderPipeline.SubmitRenderRequest(cam, request);
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = rt;
            var texture = new Texture2D(width, height, TextureFormat.RGBA32, false);
            texture.ReadPixels(new Rect(0, 0, width, height), 0, 0);
            texture.Apply();
            RenderTexture.active = previous;
            RenderTexture.ReleaseTemporary(rt);
            Color32[] pixels = texture.GetPixels32();
            Object.Destroy(texture);
            return pixels;
        }

        // ----- 22e -----

        /// <summary>
        /// The details are at world scale, whatever the mesh: on every level, for every detailed slot, the world metres
        /// one repeat of its texture spans (measured here on the mesh as drawn: its edges in metres over its UVs, times
        /// the tiling of its block) is its surface's tile, the same on both axes. The premise of the Kenney models: their
        /// own UVs are a planar projection at Tuning.KenneyUvPerNativeUnit per native unit (measured on the GLB meshes).
        /// </summary>
        [UnityTest]
        public IEnumerator Step22e_DetailRepeatsAtItsTileInMetres()
        {
            AssertLibrary();
            // Premise: the Kenney UV scale (39.37 UV per native unit, inches per metre).
            int kenney = 0;
            foreach (string id in ModelCatalog.Ids.Where(i => i.StartsWith("kenney.", StringComparison.Ordinal)))
            {
                foreach (MeshFilter f in ModelCatalog.Lookup(id).prefab.GetComponentsInChildren<MeshFilter>(true))
                {
                    float metresPerUv = Median(f.sharedMesh, -1, f.sharedMesh.vertices, Matrix4x4.identity);
                    Assert.That(1f / metresPerUv, Is.EqualTo(Tuning.KenneyUvPerNativeUnit).Within(0.01f * Tuning.KenneyUvPerNativeUnit),
                        $"{id} {f.name}: UV per native unit");
                    kenney++;
                }
            }
            Assert.Greater(kenney, 6, "premise: few Kenney meshes measured");

            int measured = 0;
            int sized = 0;
            int skinnedSlots = 0;
            var worst = new Dictionary<Surface, float>();
            foreach (string id in Game.LevelOrder.ToList())
            {
                yield return LoadLevel(id);
                // M7 rug image (product owner, 2026-11-18): the rug's and the doormat's own picture is stretched over
                // their own quad (PrimitiveKit.QuadMesh, scaled up directly by its transform, like the Garden above),
                // never tiled at a metres-per-repeat: it is never measured against Carpet's tile here.
                // PLANT (2026-11-24): the banana plant's leaf chart, like the rug's picture, shows once per blade (unit UVs).
                foreach (Slot s in LitSlots(Game.Level.Root.transform).Where(s => s.Texture != null && s.Texture != TextureLibrary.RugColour
                    && s.Texture != TextureLibrary.BananaLeafColour))
                {
                    Assert.That(s.St.y, Is.EqualTo(s.St.x).Within(1e-5f), $"{id}: {Label(s)}: anisotropic tiling");
                    Mesh mesh = ModelKit.MeshOf(s.Renderer);
                    Vector3[] vertices;
                    if (s.Renderer is SkinnedMeshRenderer skinned)
                    {
                        var baked = new Mesh();
                        skinned.BakeMesh(baked, true);
                        vertices = baked.vertices;
                        Object.Destroy(baked);
                    }
                    else
                    {
                        vertices = mesh.vertices;
                    }
                    float metresPerUv = Median(mesh, s.Index, vertices, s.Renderer.transform.localToWorldMatrix);
                    float repeat = metresPerUv / s.St.x;
                    float tile = TextureLibrary.TileMetres(s.Surface);
                    float error = Mathf.Abs(repeat / tile - 1f);
                    worst[s.Surface] = Mathf.Max(worst.TryGetValue(s.Surface, out float w) ? w : 0f, error);
                    Assert.Less(error, Tuning.DetailTileTolerance, $"{id}: {Label(s)} repeats every {repeat:0.###} m, its {s.Surface} tile is {tile} m");
                    // Independent of any measure: a PrimitiveKit box or quad carries UVs in metres (its transform scale is
                    // its size, its parents are unscaled), so its tiling is exactly 1 / tile; the humans' generated UVs are
                    // in mesh units, so one UV is the skinned renderer's scale in metres. M6: the Garden is the one
                    // exception (PrimitiveKit.QuadMesh, the raw unit quad, scaled up directly by its own transform, not a
                    // QuadMeshSized mesh under an unscaled parent), so its tiling is size / tile, not 1 / tile.
                    if ((mesh.name == "Box" || mesh.name == "Quad" || mesh.name == "Boxes") && s.Renderer.name != "Garden"
                        && s.Renderer.transform.parent != null && (s.Renderer.transform.parent.lossyScale - Vector3.one).sqrMagnitude < 1e-8f)
                    {
                        Assert.That(s.St.x, Is.EqualTo(1f / tile).Within(1e-3f / tile), $"{id}: {Label(s)}: a metric mesh's tiling");
                        sized++;
                    }
                    if (s.Renderer is SkinnedMeshRenderer)
                    {
                        float scale = s.Renderer.transform.lossyScale.x;
                        Assert.That(metresPerUv / scale, Is.EqualTo(1f).Within(0.15f), $"{id}: {Label(s)}: {metresPerUv:0.###} m per UV, its scale is {scale:0.###}");
                        skinnedSlots++;
                    }
                    measured++;
                }
                // Walls 4 (WallArray): a wall of the wall material repeats each finish at its tile too: per finish named by
                // its vertices (UV1), UV0's metres per unit (measured on its triangles as drawn) over the repeats per metre
                // the vertices carry, the same on both axes (UV0 is metric both ways).
                foreach (Renderer r in Game.Level.Root.GetComponentsInChildren<Renderer>(false).Where(r => r.enabled && WallArray.IsWallMaterial(r.sharedMaterial)))
                {
                    Mesh mesh = ModelKit.MeshOf(r);
                    var finish = new List<Vector4>();
                    mesh.GetUVs(WallArray.FinishChannel, finish);
                    Assert.AreEqual(mesh.vertexCount, finish.Count, $"{id}: wall {r.name}: no finish per vertex");
                    var uv = new List<Vector2>();
                    mesh.GetUVs(0, uv);
                    Vector3[] vertices = mesh.vertices;
                    int[] t = mesh.triangles;
                    var ratios = new Dictionary<Surface, List<float>>();
                    for (int i = 0; i + 2 < t.Length; i += 3)
                    {
                        // Fixture housings (2026-11-19, RoomLights): a wall cap may carry the black frames of its wall's
                        // fixtures, flat vertices (WallArray.Flat) that name a colour instead of a finish and tile nothing.
                        if (r.name == LevelBuilder.CapName && finish[t[i]].x == WallArray.FlatFinish)
                        {
                            Assert.IsTrue(finish[t[i + 1]].x == WallArray.FlatFinish && finish[t[i + 2]].x == WallArray.FlatFinish,
                                $"{id}: wall {r.name}: a triangle mixes a housing and a finish");
                            continue;
                        }
                        Surface s = WallArray.SurfaceOf(finish[t[i]]);
                        Assert.AreNotEqual(Surface.Plain, s, $"{id}: wall {r.name}: a triangle names no finish");
                        Assert.That(finish[t[i]].y, Is.EqualTo(1f / TextureLibrary.TileMetres(s)).Within(1e-4f), $"{id}: wall {r.name}: {s} repeats per metre");
                        for (int e = 0; e < 3; e++)
                        {
                            int a = t[i + e];
                            int b = t[i + (e + 1) % 3];
                            float du = (uv[b] - uv[a]).magnitude;
                            float dw = r.transform.localToWorldMatrix.MultiplyVector(vertices[b] - vertices[a]).magnitude;
                            if (du > 1e-6f && dw > 1e-6f)
                            {
                                (ratios.TryGetValue(s, out List<float> list) ? list : ratios[s] = new List<float>()).Add(dw / du);
                            }
                        }
                    }
                    foreach (KeyValuePair<Surface, List<float>> pair in ratios)
                    {
                        pair.Value.Sort();
                        float metresPerUv = pair.Value[pair.Value.Count / 2];
                        Assert.That(metresPerUv, Is.EqualTo(1f).Within(1e-3f), $"{id}: wall {r.name}: {pair.Key}: UV0 is not in metres");
                        float tile = TextureLibrary.TileMetres(pair.Key);
                        float repeat = metresPerUv * tile;
                        float error = Mathf.Abs(repeat / tile - 1f);
                        worst[pair.Key] = Mathf.Max(worst.TryGetValue(pair.Key, out float w) ? w : 0f, error);
                        measured++;
                    }
                }
            }
            Debug.Log("[Step22e] worst relative error per surface: " + string.Join(", ", worst.Select(p => $"{p.Key} {p.Value:0.000}")));
            Assert.Greater(measured, 100, "premise: few detailed slots measured");
            Assert.Greater(sized, 50, "premise: few PrimitiveKit boxes and quads checked against 1 / tile");
            // M7 faces: the garments left the library details (CharacterLook); the socks still show linen.
            Assert.Greater(skinnedSlots, 0, "premise: no skinned slot checked against its scale");
            // M6 (CONTRACT_M6 2.4): Soil is never level data (only LoadView's "plant" load reaches it, and no shipped
            // level sets player.load to "plant"; ProbeTestsM6Textures.Step50b_ exercises it directly), so it alone is
            // never seen here. M9 floors (docs/m9/FLOORS_WALLS.md, 2026-11-19): every floor finish (the M8 Marble,
            // Herringbone and CarpetFinish, the new LightOak, Verde, IvoryTile and TealTile) is used by at least one of
            // the levels levels.json lists (20 since levels.json rev 3), so all of them must be seen here, at their own repeat.
            // 2026-11-24: the Verde floor was replaced in every level at the user's request (halls and corridors now
            // IvoryTile, the level22 office LightOak), so it is no longer shipped either.
            Surface[] neverShipped = { Surface.Soil, Surface.Verde };
            int expectedSurfaces = TextureLibrary.Textured.Length - neverShipped.Count(s => !worst.ContainsKey(s));
            Assert.AreEqual(expectedSurfaces, worst.Count,
                "premise: every surface but Soil was seen in the levels: " + string.Join(", ", worst.Keys));
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>The median, over the edges of submesh <paramref name="sub"/> (all when -1), of world length over UV length.</summary>
        private static float Median(Mesh mesh, int sub, Vector3[] vertices, Matrix4x4 toWorld)
        {
            var uv = new List<Vector2>();
            mesh.GetUVs(0, uv);
            Assert.AreEqual(vertices.Length, uv.Count, $"{mesh.name}: UV count");
            var ratios = new List<float>();
            int from = sub < 0 ? 0 : sub;
            int to = sub < 0 ? mesh.subMeshCount : sub + 1;
            for (int m = from; m < to; m++)
            {
                int[] t = mesh.GetTriangles(m);
                for (int i = 0; i + 2 < t.Length; i += 3)
                {
                    for (int e = 0; e < 3; e++)
                    {
                        int a = t[i + e];
                        int b = t[i + (e + 1) % 3];
                        float du = (uv[b] - uv[a]).magnitude;
                        float dw = toWorld.MultiplyVector(vertices[b] - vertices[a]).magnitude;
                        if (du > 1e-6f && dw > 1e-6f)
                        {
                            ratios.Add(dw / du);
                        }
                    }
                }
            }
            Assert.Greater(ratios.Count, 0, $"{mesh.name}: no measurable edge");
            ratios.Sort();
            return ratios[ratios.Count / 2];
        }

        // ----- 22f -----

        /// <summary>Repeat on U; on V Repeat, or Clamp for a tiled wall's map (<paramref name="clampV"/>, TextureLibrary.ClampsVertically).</summary>
        private static void AssertWrap(Texture t, bool clampV, string label)
        {
            Assert.AreEqual(TextureWrapMode.Repeat, t.wrapModeU, $"{label}: wrap U");
            Assert.AreEqual(clampV ? TextureWrapMode.Clamp : TextureWrapMode.Repeat, t.wrapModeV, $"{label}: wrap V");
        }

        /// <summary>
        /// A shipped colour map: its own texture, sRGB, mipmapped, repeating (a tiled wall's, <paramref name="clampV"/>:
        /// repeating along the wall, clamped up it), compressed, at most 512 px, not readable.
        /// </summary>
        private static void AssertColourMap(Texture2D t, string label, HashSet<Texture2D> seen, bool clampV = false)
        {
            Assert.IsNotNull(t, $"{label}: no colour map");
            Assert.IsTrue(seen.Add(t), $"{label}: its colour map is another texture of the library");
            Assert.LessOrEqual(Mathf.Max(t.width, t.height), 512, $"{label}: {t.width} px");
            Assert.Greater(t.mipmapCount, 5, $"{label}: colour map mipmaps");
            AssertWrap(t, clampV, label + ": colour map");
            Assert.IsFalse(t.isReadable, $"{label}: colour map CPU readable (twice the memory)");
            Assert.IsTrue(GraphicsFormatUtility.IsSRGBFormat(t.graphicsFormat), $"{label}: the colour map is linear ({t.graphicsFormat}); its texels are sRGB colours");
            Assert.IsTrue(GraphicsFormatUtility.IsCompressedFormat(t.graphicsFormat), $"{label}: colour map not compressed ({t.graphicsFormat})");
        }

        /// <summary>
        /// What ships: the library in Resources holds, per textured surface, a grayscale detail (linear: a multiplier, not
        /// a colour; its measured mean the detail mean) and, M7 real colours, an sRGB colour map, plus the player's own
        /// colour map; all mipmapped, repeating, compressed for the platform, at most 512 px and not CPU readable (light
        /// enough for mobile). A missing texture is reported as an error, never silently flat: the built player's probe
        /// fails on any logged error.
        /// </summary>
        [UnityTest]
        public IEnumerator Step22f_LibraryShipsLinearCompressedMipmappedTextures()
        {
            AssertLibrary();
            TextureLibrary library = TextureLibrary.Load();
            Assert.AreEqual(TextureLibrary.Textured.Length, library.entries.Count, "one entry per textured surface");
            var seen = new HashSet<Texture2D>();
            foreach (Surface s in TextureLibrary.Textured)
            {
                TextureLibrary.Entry e = library.Find(s);
                Assert.IsNotNull(e, "no entry for " + s);
                Texture2D t = e.texture;
                Assert.IsTrue(seen.Add(t), $"{s}: its texture is another surface's");
                Assert.LessOrEqual(Mathf.Max(t.width, t.height), 512, $"{s}: {t.width} px");
                Assert.Greater(t.mipmapCount, 5, $"{s}: mipmaps");
                // Tiled walls (2026-11-19): a whole wall image repeats along the wall and is clamped up it, its normal map too.
                bool clampV = TextureLibrary.ClampsVertically(s);
                AssertWrap(t, clampV, s.ToString());
                if (e.normal != null)
                {
                    AssertWrap(e.normal, clampV, s + ": normal map");
                }
                Assert.IsFalse(t.isReadable, $"{s}: CPU readable (twice the memory)");
                Assert.IsFalse(GraphicsFormatUtility.IsSRGBFormat(t.graphicsFormat), $"{s}: sRGB ({t.graphicsFormat}); a detail is a linear multiplier");
                Assert.IsTrue(GraphicsFormatUtility.IsCompressedFormat(t.graphicsFormat), $"{s}: not compressed ({t.graphicsFormat})");
                Assert.That(e.mean, Is.EqualTo(Tuning.DetailMean).Within(Tuning.DetailMeanTolerance), $"{s}: mean");
                Assert.IsFalse(string.IsNullOrEmpty(e.source), $"{s}: no source asset");
                StringAssert.Contains(e.source, t.name, $"{s}: the texture is not derived from {e.source}");
                // M7 real colours (CONTRACT_M7 5): the colour map, sRGB (it is a colour), otherwise shipped as the detail.
                AssertColourMap(e.colour, s.ToString(), seen, clampV);
                StringAssert.Contains(e.source, e.colour.name, $"{s}: the colour map is not prepared from {e.source}");
                Assert.AreEqual(s, TextureLibrary.SurfaceOf(e.colour), $"{s}: its colour map is not recognised");
            }
            // Walls 4 (WallArray): the wall finish arrays, one 512 slice per finish in WallArray.Slices order, mipmapped,
            // repeating, compressed, sRGB for the colours and linear for the normals, and the two wall materials on them.
            CollectionAssert.AreEqual(WallArray.Slices, library.wallSlices, "the wall arrays' slices");
            foreach ((Texture2DArray array, bool srgb, string label) in new[] { (library.wallColours, true, "wall colours"), (library.wallNormals, false, "wall normals") })
            {
                Assert.IsNotNull(array, $"{label}: no array");
                Assert.AreEqual(WallArray.Depth, array.depth, $"{label}: slices (the surfaces, then DRESSING's images)");
                Assert.AreEqual(512, array.width, $"{label}: width");
                Assert.AreEqual(512, array.height, $"{label}: height");
                Assert.Greater(array.mipmapCount, 5, $"{label}: mipmaps");
                Assert.AreEqual(TextureWrapMode.Repeat, array.wrapModeU, $"{label}: wrap U");
                Assert.AreEqual(TextureWrapMode.Repeat, array.wrapModeV, $"{label}: wrap V");
                Assert.AreEqual(srgb, GraphicsFormatUtility.IsSRGBFormat(array.graphicsFormat), $"{label}: {array.graphicsFormat}");
                Assert.IsTrue(GraphicsFormatUtility.IsCompressedFormat(array.graphicsFormat), $"{label}: not compressed ({array.graphicsFormat})");
                Assert.IsFalse(array.isReadable, $"{label}: CPU readable");
            }
            foreach (Material m in new[] { library.wallMaterial, library.wallSeeThrough })
            {
                Assert.IsNotNull(m, "premise: a wall material is missing");
                Assert.IsTrue(m.shader.isSupported, $"{m.name}: {m.shader.name} is not supported");
                Assert.AreSame(library.wallColours, m.GetTexture("_WallColours"), $"{m.name}: colour array");
                Assert.AreSame(library.wallNormals, m.GetTexture("_WallNormals"), $"{m.name}: normal array");
            }
            Assert.AreSame(library.wallMaterial, WallArray.Material, "the walls are drawn with the library's wall material");
            Assert.AreSame(library.wallSeeThrough, WallFader.GhostMaterial, "the wall fader draws with the library's see-through material");
            AssertColourMap(library.playerColour, "player", seen);
            Assert.IsFalse(string.IsNullOrEmpty(library.playerSource), "player: no source asset");
            Assert.AreEqual(Surface.Lacquer, TextureLibrary.SurfaceOf(library.playerColour), "the player's image replaces its lacquer");
            Assert.AreEqual(Surface.Plain, TextureLibrary.SurfaceOf(TextureLibrary.Flat), "the flat map is no detail");
            Assert.AreEqual(0f, TextureLibrary.TileMetres(Surface.Plain));

            // A slot whose mesh cannot carry a detail reports it once as an error (here: a mesh without UVs).
            // The problem is reported once per renderer name: a fresh name each run.
            var go = new GameObject("NoUv" + Guid.NewGuid().ToString("N"));
            try
            {
                var mesh = new Mesh { name = "NoUvMesh" };
                mesh.vertices = new[] { Vector3.zero, Vector3.right, Vector3.up };
                mesh.triangles = new[] { 0, 1, 2 };
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                var r = go.AddComponent<MeshRenderer>();
                r.sharedMaterial = PrimitiveKit.Lit(Color.gray);
                int before = errors.Count;
                LogAssert.Expect(LogType.Error, new System.Text.RegularExpressions.Regex("NoUv[0-9a-f]+ slot 0: its mesh has no measurable UVs"));
                PrimitiveKit.Detail(r, Surface.Wood);
                Assert.AreEqual(before + 1, errors.Count, "a slot that cannot show its detail is not reported");
                Assert.IsFalse(r.HasPropertyBlock(), "a detail was set without UVs");
                errors.RemoveAt(errors.Count - 1);
                Object.Destroy(mesh);
            }
            finally
            {
                Object.Destroy(go);
            }
            yield return null;
            CollectionAssert.IsEmpty(errors, "no error logged");
        }
    }
}
