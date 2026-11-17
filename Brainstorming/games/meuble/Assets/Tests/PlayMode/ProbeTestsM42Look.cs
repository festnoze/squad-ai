using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using Meuble.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.Experimental.Rendering;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace Meuble.Tests
{
    /// <summary>
    /// M4.2 textures probe (steps 22c to 22f) on the real Boot scene, every level of levels.json. The technique under
    /// test: one URP Lit material per palette colour, its base colour the palette divided by Tuning.DetailMean and its
    /// base map a flat texture of that mean; a renderer slot shows a grayscale detail of the same mean through a
    /// MaterialPropertyBlock (PrimitiveKit.Detail). Every step asserts its premise first (the library resolves, the
    /// level has model visuals and detailed slots), so a Detail that does nothing cannot pass.
    /// </summary>
    public sealed class ProbeTestsM42Look
    {
        private static readonly int BaseMap = Shader.PropertyToID("_BaseMap");
        private static readonly int BaseMapSt = Shader.PropertyToID("_BaseMap_ST");

        /// <summary>
        /// "Nothing becomes noisy": the textured start view may have at most this much more fine detail (mean absolute
        /// difference between neighbour pixels) than the same view flat. Calibrated on the M4.2 shots: about 1.1 to 1.3.
        /// M6 (CONTRACT_M6 2.4, q28): the player furniture's glossy lacquer is a deliberately bolder grain ("strong
        /// highlights, the wood grain still visible under it"), measured up to about 1.8 on level1's red chair.
        /// </summary>
        private const float MaxDetailGain = 2.0f;

        /// <summary>Premise of the side by side render: the textures add at least this much fine detail, or they do not show.</summary>
        private const float MinDetailGain = 1.02f;

        /// <summary>The player furniture's rendered colour, textured against flat: at most this hue shift (degrees).</summary>
        private const float MaxHueShift = 4f;

        /// <summary>... and at most this relative change of its mean value and saturation.</summary>
        private const float MaxShadeChange = 0.06f;

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

        /// <summary>The library resolves a texture for every textured surface (the premise of every step).</summary>
        private static void AssertLibrary()
        {
            TextureLibrary library = TextureLibrary.Load();
            Assert.IsNotNull(library, $"premise: no Resources/{TextureLibrary.ResourcePath}");
            foreach (Surface s in TextureLibrary.Textured)
            {
                Assert.IsNotNull(TextureLibrary.TextureOf(s), $"premise: the library has no texture for {s}");
            }
        }

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
        /// </summary>
        private bool PlainAllowed(Slot s)
        {
            string name = s.Renderer.name;
            if (name == "Garden" || name.StartsWith("Books", StringComparison.Ordinal) || name == "Leaves")
            {
                return true;
            }
            Color? palette = PrimitiveKit.PaletteOf(s.Material);
            if (palette.HasValue && Same(palette.Value, FurnitureKit.FrameColor))
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
            ["plant"] = new[] { Surface.Plaster, Surface.Foliage },
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
        /// On every level: every URP Lit slot shows its detail texture, except the few that must stay plain; floors are
        /// parquet (hard) or carpet (soft), wall faces and caps plaster, rugs and the doormat carpet; each prop, the
        /// player body and the decoys show the surfaces of what they are made of; every model slot shows the surface of
        /// its source material, so the inhabitants' clothes are linen and their skin plain, on a skinned mesh that now
        /// has UVs. The budgets of PRD 7.4 hold (materials are still one per palette colour).
        /// </summary>
        [UnityTest]
        public IEnumerator Step22c_EveryMaterialHasItsDetailTexture()
        {
            AssertLibrary();
            Assert.GreaterOrEqual(Game.LevelOrder.Count, 7, "premise: levels.json lists the seven levels");
            var table = new List<string>();
            foreach (string id in Game.LevelOrder.ToList())
            {
                yield return LoadLevel(id);
                LevelInstance level = Game.Level;
                Assert.Greater(level.ModelVisuals.Count, 0, $"{id}: premise: no model visual");
                List<Slot> slots = LitSlots(level.Root.transform);
                Assert.Greater(slots.Count, 20, $"{id}: premise: few Lit slots");
                Dictionary<(Renderer, int), Surface> models = ExpectedModelSurfaces(level);

                int detailed = 0;
                var missing = new List<string>();
                foreach (Slot s in slots)
                {
                    if (s.Texture != null)
                    {
                        detailed++;
                        Assert.AreNotEqual(Surface.Plain, s.Surface, $"{id}: {Label(s)} shows a texture that is not in the library ({s.Texture.name})");
                        Assert.Greater(s.St.x, 0f, $"{id}: {Label(s)} has no tiling");
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
                Assert.Greater(detailed, slots.Count / 2, $"{id}: only {detailed} of {slots.Count} slots show a detail");

                // Floors, walls, caps.
                bool soft = Game.Def.AllRooms().Any(r => r.IsSoft);
                // M7 (CONTRACT_M7 1.2): a room can also set its own "floorFinish": "tile" (kitchen, bathroom).
                bool tiled = Game.Def.AllRooms().Any(r => r.IsTile);
                var floors = slots.Where(s => s.Renderer.gameObject.layer == Layers.Floor && s.Renderer.name != "Garden").ToList();
                Assert.Greater(floors.Count, 0, $"{id}: premise: no floor renderer");
                foreach (Slot s in floors)
                {
                    Assert.IsTrue(s.Surface == Surface.Parquet || (soft && s.Surface == Surface.Carpet) || (tiled && s.Surface == Surface.Tile),
                        $"{id}: floor {Label(s)} shows {s.Surface}");
                }
                if (!soft && !tiled)
                {
                    Assert.IsTrue(floors.All(s => s.Surface == Surface.Parquet), $"{id}: a hard floor is not parquet");
                }
                var walls = slots.Where(s => s.Renderer.name == "Face" || s.Renderer.name == "Cap").ToList();
                Assert.Greater(walls.Count, 3, $"{id}: premise: no wall faces");
                foreach (Slot s in walls)
                {
                    Assert.AreEqual(Surface.Plaster, s.Surface, $"{id}: wall {Label(s)}");
                }

                // Rugs and the doormat.
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
                // M6 (CONTRACT_M6 2.4): the player's own furniture is lacquered (PrimitiveKit.LitSurface), not a plain Lit material.
                Material red = PrimitiveKit.LitSurface(LevelJson.ParseColor(Game.Def.Player.Color, Color.red), Surface.Lacquer);
                Assert.IsTrue(player.Any(s => s.Material == red), $"{id}: premise: the player furniture is not in the player colour");
                Assert.IsTrue(player.Where(s => s.Material == red).All(s => s.Texture != null), $"{id}: a slot of the player colour shows no detail");
                foreach (Decoy decoy in level.Decoys)
                {
                    Assert.IsTrue(LitSlots(decoy.transform).Any(s => s.Texture != null), $"{id}: decoy {decoy.Id} shows no detail");
                }

                // The inhabitants: UVs generated in place on the prefab's own mesh, clothes linen, skin plain.
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
                    Assert.AreSame(prefabMesh, mesh, $"{id}: {h.name} no longer draws the catalog prefab's own mesh (UVs must be added in place)");
                    List<Slot> worn = LitSlots(h.transform).Where(s => s.Renderer == skin).ToList();
                    Assert.IsTrue(worn.Any(s => s.Surface == Surface.Linen), $"{id}: {h.name}'s clothes show no linen");
                    Material[] sources = entry.prefab.GetComponentInChildren<SkinnedMeshRenderer>(true).sharedMaterials;
                    int skinSlot = Array.FindIndex(sources, m => m.name == "Skin");
                    Assert.GreaterOrEqual(skinSlot, 0, $"premise: {entry.id} has a Skin material");
                    Assert.AreEqual(Surface.Plain, worn.First(s => s.Index == skinSlot).Surface, $"{id}: {h.name}'s skin shows a detail");
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
        /// The palette colour is kept. Numerically: every detail texture's mean is Tuning.DetailMean, and every Lit
        /// material's base colour times that mean is its palette colour, its base map the flat map of that mean.
        /// Rendered: on level 1 (the red chair, the blue sofa) and level 5 (the red armchair), the start view is
        /// rendered textured, then flat (TextureLibrary.Disabled, the same level rebuilt at the same step): the red
        /// and blue pixels keep their hue, value and saturation; the textured view has more fine detail than the flat
        /// one (the textures show) but not much more (nothing becomes noisy).
        /// </summary>
        [UnityTest]
        public IEnumerator Step22d_PaletteColourIsKept()
        {
            AssertLibrary();
            foreach (TextureLibrary.Entry e in TextureLibrary.Load().entries)
            {
                Assert.That(e.mean, Is.EqualTo(Tuning.DetailMean).Within(Tuning.DetailMeanTolerance), $"{e.surface}: mean of {e.texture.name}");
            }
            Assert.That(TextureLibrary.MeanOf(TextureLibrary.Flat), Is.EqualTo(Tuning.DetailMean).Within(1e-4f), "the flat map");

            int checkedMaterials = 0;
            foreach (string id in new[] { "level1", "level5" })
            {
                yield return LoadLevel(id);
                foreach (Material m in LitSlots(Game.Level.Root.transform).Select(s => s.Material).Distinct())
                {
                    Color? palette = PrimitiveKit.PaletteOf(m);
                    Assert.IsTrue(palette.HasValue, $"{id}: {m.name} is not a PrimitiveKit material");
                    Assert.AreSame(TextureLibrary.Flat, m.GetTexture(BaseMap), $"{id}: {m.name}'s base map is not the flat map");
                    Color baseLinear = m.GetColor("_BaseColor").linear;
                    Color want = palette.Value.linear;
                    for (int c = 0; c < 3; c++)
                    {
                        Assert.That(baseLinear[c] * Tuning.DetailMean, Is.EqualTo(want[c]).Within(0.004f), $"{id}: {m.name} channel {c}");
                    }
                    checkedMaterials++;
                }

                // Side by side: textured, then flat.
                Color32[] textured = null;
                Color32[] plain = null;
                int width = 640;
                int height = 360;
                Rect player = default;
                Rect sofa = default;
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
                        Assert.Greater(all.Count(s => s.Texture != null), 20, $"{id}: premise: few detailed slots");
                    }
                    Camera cam = main.Camera;
                    player = ScreenBox(cam, Game.Furniture.transform, width, height);
                    Transform sofaProp = Game.Def.Props.Where(p => p.Kind == "sofa" && !string.IsNullOrEmpty(p.Model))
                        .Select(p => Game.Level.Root.transform.Find(p.Name)).FirstOrDefault();
                    sofa = sofaProp != null ? ScreenBox(cam, sofaProp, width, height) : default;
                    Color32[] pixels = RenderPixels(cam, width, height);
                    if (flat)
                    {
                        plain = pixels;
                    }
                    else
                    {
                        textured = pixels;
                    }
                }
                TextureLibrary.Disabled = false;

                float gain = FineDetail(textured, width, height) / Mathf.Max(1e-4f, FineDetail(plain, width, height));
                Debug.Log($"[Step22d] {id}: fine detail textured / flat = {gain:0.000}");
                Assert.Greater(gain, MinDetailGain, $"{id}: the textured view has no more fine detail than the flat one: the details do not show");
                Assert.Less(gain, MaxDetailGain, $"{id}: the textured view is noisy ({gain:0.00} times the fine detail of the flat one)");

                AssertColourKept(textured, plain, width, height, player, c => ModelMath.IsRed(c), id + " player furniture (red)");
                if (sofa.width > 0f)
                {
                    AssertColourKept(textured, plain, width, height, sofa, c => IsBlue(c), id + " sofa (blue)");
                }
            }
            Assert.Greater(checkedMaterials, 20, "premise: few materials checked");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        private static bool IsBlue(Color c)
        {
            Color.RGBToHSV(c, out float h, out float s, out float v);
            return h * 360f > 190f && h * 360f < 240f && s > 0.35f && v > 0.25f;
        }

        /// <summary>
        /// The pixels of <paramref name="box"/> that pass <paramref name="isColour"/> in the flat render: their mean colour
        /// in the textured render keeps its hue, value and saturation, and still passes the test.
        /// </summary>
        private static void AssertColourKept(Color32[] textured, Color32[] plain, int width, int height, Rect box, Func<Color, bool> isColour, string label)
        {
            Color sumT = Color.clear;
            Color sumF = Color.clear;
            int n = 0;
            for (int y = Mathf.Max(0, (int)box.yMin); y < Mathf.Min(height, (int)box.yMax); y++)
            {
                for (int x = Mathf.Max(0, (int)box.xMin); x < Mathf.Min(width, (int)box.xMax); x++)
                {
                    int i = y * width + x;
                    if (!isColour(plain[i]))
                    {
                        continue;
                    }
                    sumT += textured[i];
                    sumF += plain[i];
                    n++;
                }
            }
            Assert.Greater(n, 40, $"{label}: premise: only {n} pixels of that colour in the flat render ({box})");
            Color t = sumT / n;
            Color f = sumF / n;
            Color.RGBToHSV(t, out float ht, out float st, out float vt);
            Color.RGBToHSV(f, out float hf, out float sf, out float vf);
            float hue = Mathf.Abs(Mathf.DeltaAngle(ht * 360f, hf * 360f));
            Debug.Log($"[Step22d] {label}: {n} px, flat {Hex(f)} textured {Hex(t)}, hue shift {hue:0.0} deg, value {vt / vf:0.000}, saturation {st / sf:0.000}");
            Assert.Less(hue, MaxHueShift, $"{label}: hue shift");
            Assert.That(vt / vf, Is.EqualTo(1f).Within(MaxShadeChange), $"{label}: value");
            Assert.That(st / sf, Is.EqualTo(1f).Within(MaxShadeChange), $"{label}: saturation");
            Assert.IsTrue(isColour(t), $"{label}: the textured mean colour {Hex(t)} no longer reads as that colour");
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
                foreach (Slot s in LitSlots(Game.Level.Root.transform).Where(s => s.Texture != null))
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
            }
            Debug.Log("[Step22e] worst relative error per surface: " + string.Join(", ", worst.Select(p => $"{p.Key} {p.Value:0.000}")));
            Assert.Greater(measured, 100, "premise: few detailed slots measured");
            Assert.Greater(sized, 50, "premise: few PrimitiveKit boxes and quads checked against 1 / tile");
            Assert.Greater(skinnedSlots, 6, "premise: few skinned slots checked against their scale");
            // M6 (CONTRACT_M6 2.4): Soil is never level data (only LoadView's "plant" load reaches it, and no shipped
            // level sets player.load to "plant"; ProbeTestsM6Textures.Step50b_ exercises it directly), so it alone is
            // never seen here.
            int expectedSurfaces = TextureLibrary.Textured.Length - (worst.ContainsKey(Surface.Soil) ? 0 : 1);
            Assert.AreEqual(expectedSurfaces, worst.Count, "premise: every surface but Soil was seen in the levels: " + string.Join(", ", worst.Keys));
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

        /// <summary>
        /// What ships: the library in Resources holds one texture per textured surface, each linear (a multiplier, not a
        /// colour), mipmapped, repeating, compressed for the platform, at most 512 px and not CPU readable (light enough for
        /// mobile); its measured mean is the detail mean. A missing texture is reported as an error, never silently flat:
        /// the built player's probe fails on any logged error.
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
                Assert.AreEqual(TextureWrapMode.Repeat, t.wrapMode, $"{s}: wrap");
                Assert.IsFalse(t.isReadable, $"{s}: CPU readable (twice the memory)");
                Assert.IsFalse(GraphicsFormatUtility.IsSRGBFormat(t.graphicsFormat), $"{s}: sRGB ({t.graphicsFormat}); a detail is a linear multiplier");
                Assert.IsTrue(GraphicsFormatUtility.IsCompressedFormat(t.graphicsFormat), $"{s}: not compressed ({t.graphicsFormat})");
                Assert.That(e.mean, Is.EqualTo(Tuning.DetailMean).Within(Tuning.DetailMeanTolerance), $"{s}: mean");
                Assert.IsFalse(string.IsNullOrEmpty(e.source), $"{s}: no source asset");
                StringAssert.Contains(e.source, t.name, $"{s}: the texture is not derived from {e.source}");
            }
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
