using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M6 texture pass 2 probe (docs/CONTRACT_M6.md 2.4): the six new surfaces (Grass, Lacquer, Metal, Plastic,
    /// Foliage, Soil) each resolve to a detail texture in the library, and every renderer that is meant to show one
    /// carries the right texture, smoothness and metallic. No single shipped level uses every new surface (the fallen
    /// load's "plant" kind, Soil and part of Foliage, is never the data in levels 1 to 17), so Step50a_ uses two
    /// levels (level7: the garden, the office chair's lacquer seat and metal frame, a plant prop's foliage, a window;
    /// level9: a chair's lacquer via its Kenney model, a robot's metal shell and plastic bumper, a window) and
    /// Step50b_ calls LoadView.Create directly for the fallen load's soil, the one production path that reaches it.
    /// </summary>
    public sealed class ProbeTestsM6Textures
    {
        private static readonly int BaseMap = Shader.PropertyToID("_BaseMap");
        // M7 textures (CONTRACT_M7 1.2): the normal map and its strength, read back the same way as BaseMap.
        private static readonly int BumpMap = Shader.PropertyToID("_BumpMap");
        private static readonly int BumpScale = Shader.PropertyToID("_BumpScale");

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

        // ----- What a Lit slot shows -----

        private struct Slot
        {
            public Renderer Renderer;
            public int Index;
            public Material Material;
            public Surface Surface;
        }

        /// <summary>Every URP Lit slot of the enabled, active renderers under <paramref name="root"/>.</summary>
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
                    slots.Add(new Slot { Renderer = r, Index = i, Material = m, Surface = TextureLibrary.SurfaceOf(texture) });
                }
            }
            return slots;
        }

        private static string Label(Slot s) => $"{s.Renderer.name}[{s.Index}] ({s.Material.name})";

        /// <summary>The material's own smoothness and metallic match the surface's fixed finish (TextureLibrary.FinishOf).</summary>
        private static void AssertFinish(Slot s, Surface surface, string label)
        {
            Assert.IsTrue(TextureLibrary.FinishOf(surface, out float smoothness, out float metallic), $"premise: {surface} has no fixed finish");
            Assert.That(s.Material.GetFloat("_Smoothness"), Is.EqualTo(smoothness).Within(1e-4f), $"{label}: {Label(s)} smoothness");
            Assert.That(s.Material.GetFloat("_Metallic"), Is.EqualTo(metallic).Within(1e-4f), $"{label}: {Label(s)} metallic");
        }

        /// <summary>
        /// M7 real colours (CONTRACT_M7 5): a player furniture slot shows the owner's red image through its own material,
        /// at the painted metal finish (Tuning.PlayerSmoothness and PlayerMetallic), with a white base colour.
        /// </summary>
        private static void AssertPlayerFinish(Slot s, string label)
        {
            Assert.AreSame(TextureLibrary.PlayerColour, ShownTexture(s.Renderer, s.Index), $"{label}: {Label(s)} does not show the player's red image");
            Assert.That(s.Material.GetFloat("_Smoothness"), Is.EqualTo(Tuning.PlayerSmoothness).Within(1e-4f), $"{label}: {Label(s)} smoothness");
            Assert.That(s.Material.GetFloat("_Metallic"), Is.EqualTo(Tuning.PlayerMetallic).Within(1e-4f), $"{label}: {Label(s)} metallic");
            Assert.AreEqual(Color.white, s.Material.GetColor("_BaseColor"), $"{label}: {Label(s)} tints the red image");
        }

        /// <summary>
        /// M7 real colours (CONTRACT_M7 5): an ordinary slot shows its surface's image through that surface's one material
        /// (white base colour, the colour map as base map).
        /// </summary>
        private static void AssertRealColour(Slot s, Surface surface, string label)
        {
            Assert.AreSame(PrimitiveKit.SurfaceMaterial(surface), s.Material, $"{label}: {Label(s)} is not drawn with the {surface} colour material");
            Assert.AreSame(TextureLibrary.ColourOf(surface), ShownTexture(s.Renderer, s.Index), $"{label}: {Label(s)} does not show the {surface} image");
        }

        private static void AssertMaterialBudget(GameState game, string id)
        {
            Renderer[] drawn = game.Level.Root.GetComponentsInChildren<Renderer>(false);
            Probe.RenderCount count = Probe.CountRenderers(drawn);
            bool house = game.Def.AllRooms().Count >= Tuning.HouseBudgetRooms;
            int cap = house ? Tuning.BudgetHouseMaterials : Tuning.BudgetMaterials;
            if (count.Materials.Count > cap)
            {
                Debug.Log("[DIAG] " + id + " materials: " + string.Join(" | ", count.Materials.Select(m => m.name)));
            }
            Assert.LessOrEqual(count.Materials.Count, cap, $"{id}: materials");
            Assert.LessOrEqual(count.MaterialSlots, house ? Tuning.BudgetHouseRenderers : Tuning.BudgetRenderers, $"{id}: draw calls");
        }

        // ----- Step50a -----

        /// <summary>
        /// The library resolves a texture for every textured surface, including the six new ones, each at its own
        /// mean (premise, as ProbeTestsM42Look's). Then level7 and level9 (chosen so the six new surfaces are all
        /// seen at least once): the garden shows Grass, the player furniture shows Lacquer (its own colour kept) on
        /// both the procedural path (level7's office chair) and the Kenney model path (level9's chair), the metal
        /// frame and the robot shell show Metal, the robot bumper shows Plastic, a potted plant's leaves show
        /// Foliage, the window pane carries its own smoothness with no texture; a decoy never shows Lacquer. Then
        /// every level 1 to 17 holds the PRD 7.4 material and draw call budgets. A few screenshots are saved for the
        /// product owner's playtest (reported, not asserted on).
        /// </summary>
        [UnityTest]
        public IEnumerator Step50a_NewSurfacesShowTheirDetailAndFinish()
        {
            TextureLibrary library = TextureLibrary.Load();
            Assert.IsNotNull(library, $"premise: no Resources/{TextureLibrary.ResourcePath}");
            foreach (Surface s in TextureLibrary.Textured)
            {
                Assert.IsNotNull(TextureLibrary.TextureOf(s), $"premise: the library has no texture for {s}");
                float mean = TextureLibrary.MeanOf(TextureLibrary.TextureOf(s));
                Assert.That(mean, Is.EqualTo(Tuning.DetailMean).Within(Tuning.DetailMeanTolerance), $"{s}: mean");
                // M7 real colours (CONTRACT_M7 5): Metal included (metal.png), every surface has its colour map.
                Assert.IsNotNull(TextureLibrary.ColourOf(s), $"premise: the library has no colour map for {s}");
            }
            Assert.IsNotNull(TextureLibrary.PlayerColour, "premise: the library has no player colour map");

            var shots = new List<string>();

            // ----- level7: the garden, the office chair (procedural lacquer + metal frame), a plant's foliage, a window -----
            yield return LoadLevel("level7");
            Assert.AreEqual(BodyKinds.OfficeChair, Game.Def.PlayerBody().Kind, "premise: level7's player is the office chair");
            List<Slot> level7 = LitSlots(Game.Level.Root.transform);

            Slot garden = level7.FirstOrDefault(s => s.Renderer.name == "Garden");
            Assert.IsNotNull(garden.Renderer, "premise: level7 has a Garden renderer");
            Assert.AreEqual(Surface.Grass, garden.Surface, "the garden shows no grass detail");
            AssertFinish(garden, Surface.Grass, "level7 garden");
            AssertRealColour(garden, Surface.Grass, "level7 garden");

            List<Slot> player7 = LitSlots(Game.Furniture.transform);
            Assert.IsTrue(player7.Any(s => s.Surface == Surface.Lacquer), "level7: the office chair's seat shows no lacquer");
            foreach (Slot s in player7.Where(s => s.Surface == Surface.Lacquer))
            {
                // M7 real colours (CONTRACT_M7 5): the owner's red painted metal image replaces the lacquer.
                AssertPlayerFinish(s, "level7 player (procedural)");
                Color? palette = PrimitiveKit.PaletteOf(s.Material);
                Assert.IsTrue(palette.HasValue && ModelMath.IsRed(palette.Value), $"level7: a lacquer slot ({Label(s)}) is not the player's own red");
            }
            List<Slot> frame7 = player7.Where(s => s.Surface == Surface.Metal).ToList();
            Assert.Greater(frame7.Count, 0, "level7: the office chair's frame shows no metal");
            foreach (Slot s in frame7)
            {
                AssertFinish(s, Surface.Metal, "level7 player frame");
                AssertRealColour(s, Surface.Metal, "level7 player frame");
            }

            // A decoy (never red, PRD 7.2) keeps its usual surface: no lacquer, but the same metal frame.
            Assert.Greater(Game.Level.Decoys.Count, 0, "premise: level7 has decoys");
            int decoysChecked = 0;
            foreach (Decoy decoy in Game.Level.Decoys)
            {
                if (decoy.Kind != BodyKinds.OfficeChair)
                {
                    continue;
                }
                List<Slot> decoySlots = LitSlots(decoy.transform);
                Assert.IsFalse(decoySlots.Any(s => s.Surface == Surface.Lacquer), $"level7: decoy {decoy.Id} (never red) shows lacquer");
                Assert.IsTrue(decoySlots.Any(s => s.Surface == Surface.Metal), $"level7: decoy {decoy.Id}'s frame shows no metal");
                decoysChecked++;
            }
            Assert.Greater(decoysChecked, 0, "premise: level7 has an office chair decoy");

            PropDef plant7 = Game.Def.Props.FirstOrDefault(p => p.Kind == "plant");
            Assert.IsNotNull(plant7, "premise: level7 has a plant prop");
            Transform plantT = Game.Level.Root.transform.Find(plant7.Name);
            Assert.IsNotNull(plantT, "level7: the plant prop was not built");
            List<Slot> plantSlots = LitSlots(plantT);
            Slot leaves7 = plantSlots.FirstOrDefault(s => s.Renderer.name == "Leaves");
            Assert.IsNotNull(leaves7.Renderer, "level7: the plant has no Leaves renderer");
            Assert.AreEqual(Surface.Foliage, leaves7.Surface, "level7: the plant's leaves show no foliage detail");
            AssertFinish(leaves7, Surface.Foliage, "level7 plant leaves");

            AssertWindowPane(Game.Level.Root.transform, "level7");
            AssertMaterialBudget(Game, "level7");
            shots.Add(Shoot("step50a_level7"));

            // ----- level9: the chair (lacquer via its Kenney model), a robot (metal shell, plastic bumper), a window -----
            yield return LoadLevel("level9");
            Assert.AreEqual(BodyKinds.Chair, Game.Def.PlayerBody().Kind, "premise: level9's player is the plain chair");
            List<Slot> player9 = LitSlots(Game.Furniture.transform);
            Assert.IsTrue(player9.Any(s => s.Surface == Surface.Lacquer), "level9: the model chair shows no lacquer");
            foreach (Slot s in player9.Where(s => s.Surface == Surface.Lacquer))
            {
                AssertPlayerFinish(s, "level9 player (model)");
            }

            Assert.Greater(Game.Robots.Count, 0, "premise: level9 has a robot");
            Robot robot = Game.Robots[0];
            Assert.IsNotNull(robot.Body, "premise: the robot has a drawn body");
            Renderer shell = robot.Body.Find("Shell")?.GetComponent<Renderer>();
            Renderer bumper = robot.Body.Find("Bumper")?.GetComponent<Renderer>();
            Assert.IsNotNull(shell, "premise: the robot has a Shell renderer");
            Assert.IsNotNull(bumper, "premise: the robot has a Bumper renderer");
            Assert.AreEqual(Surface.Metal, TextureLibrary.SurfaceOf(ShownTexture(shell)), "the robot's shell shows no metal detail");
            Assert.AreEqual(Surface.Plastic, TextureLibrary.SurfaceOf(ShownTexture(bumper)), "the robot's bumper shows no plastic detail");
            Assert.That(shell.sharedMaterial.GetFloat("_Smoothness"), Is.EqualTo(Tuning.MetalSmoothness).Within(1e-4f), "robot shell smoothness");
            Assert.That(shell.sharedMaterial.GetFloat("_Metallic"), Is.EqualTo(Tuning.MetalMetallic).Within(1e-4f), "robot shell metallic");
            Assert.That(bumper.sharedMaterial.GetFloat("_Smoothness"), Is.EqualTo(Tuning.PlasticSmoothness).Within(1e-4f), "robot bumper smoothness");
            Assert.That(bumper.sharedMaterial.GetFloat("_Metallic"), Is.EqualTo(0f).Within(1e-4f), "robot bumper metallic");

            AssertWindowPane(Game.Level.Root.transform, "level9");
            AssertMaterialBudget(Game, "level9");
            shots.Add(Shoot("step50a_level9"));

            // ----- Every level 1 to 17: the PRD 7.4 budgets still hold. -----
            Assert.GreaterOrEqual(Game.LevelOrder.Count, 17, "premise: levels.json lists at least the 17 M1-M5 levels");
            foreach (string id in Game.LevelOrder.ToList())
            {
                yield return LoadLevel(id);
                AssertMaterialBudget(Game, id);
            }

            Debug.Log("[Step50a] screenshots: " + string.Join(", ", shots));
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>The detail texture a renderer's slot 0 shows through its property block, or null.</summary>
        private static Texture ShownTexture(Renderer r) => ShownTexture(r, 0);

        /// <summary>The texture a renderer's slot shows through its property block, or null.</summary>
        private static Texture ShownTexture(Renderer r, int slot)
        {
            var block = new MaterialPropertyBlock();
            r.GetPropertyBlock(block, slot);
            return block.isEmpty ? null : block.GetTexture(BaseMap);
        }

        /// <summary>The window pane: no texture (Surface.Plain), but its own smoothness (CONTRACT_M6 2.4).</summary>
        private static void AssertWindowPane(Transform root, string id)
        {
            Renderer pane = root.GetComponentsInChildren<Renderer>(false).FirstOrDefault(r => r.name == "WindowPane");
            Assert.IsNotNull(pane, $"{id}: premise: no WindowPane renderer");
            Assert.AreEqual(Surface.Plain, TextureLibrary.SurfaceOf(ShownTexture(pane)), $"{id}: the window pane shows a texture");
            Assert.That(pane.sharedMaterial.GetFloat("_Smoothness"), Is.EqualTo(Tuning.WindowPaneSmoothness).Within(1e-4f), $"{id}: window pane smoothness");
            Assert.That(pane.sharedMaterial.GetFloat("_Metallic"), Is.EqualTo(0f).Within(1e-4f), $"{id}: window pane metallic");
        }

        /// <summary>Renders the current camera view to a PNG under the agent's scratch folder; returns its path.</summary>
        private string Shoot(string name)
        {
            const int width = 960;
            const int height = 540;
            Game.Camera.Snap();
            RenderTexture rt = RenderTexture.GetTemporary(width, height, 24);
            var request = new RenderPipeline.StandardRequest { destination = rt };
            if (!RenderPipeline.SupportsRenderRequest(main.Camera, request))
            {
                RenderTexture.ReleaseTemporary(rt);
                return "(no render request support)";
            }
            RenderPipeline.SubmitRenderRequest(main.Camera, request);
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = rt;
            var texture = new Texture2D(width, height, TextureFormat.RGBA32, false);
            texture.ReadPixels(new Rect(0, 0, width, height), 0, 0);
            texture.Apply();
            RenderTexture.active = previous;
            RenderTexture.ReleaseTemporary(rt);
            byte[] png = texture.EncodeToPNG();
            Object.Destroy(texture);
            // The agent's own scratch folder (never the project): a fixed path, not derived from Application.*.
            const string dir = @"C:\Users\E6FB4~1.MIL\AppData\Local\Temp\claude\c--Dev-squad-ai-Brainstorming"
                + @"\3e111d42-8539-4163-b07f-518922ca148e\scratchpad\texturesm6";
            string path;
            try
            {
                Directory.CreateDirectory(dir);
                path = Path.Combine(dir, name + ".png");
                File.WriteAllBytes(path, png);
            }
            catch (Exception e)
            {
                path = "(could not save: " + e.Message + ")";
            }
            return path;
        }

        // ----- Step50b: the fallen load's plant (Soil, and Foliage again) -----

        /// <summary>
        /// No shipped level (1 to 17) ever sets <c>player.load</c> to "plant" (only "vase" is used), so the fallen
        /// load's Soil (and its own Foliage) is otherwise untested: this calls LoadView.Create directly, the same
        /// production method LevelBuilder.ApplyLoad calls, on a throwaway furniture transform.
        /// </summary>
        [UnityTest]
        public IEnumerator Step50b_FallenLoadPlantShowsSoilAndFoliage()
        {
            yield return null; // the Boot scene from UnitySetUp is enough; no level reload needed.
            var furniture = new GameObject("Step50b furniture");
            try
            {
                LoadView view = LoadView.Create(LoadView.Plant, furniture.transform, new Vector3(0.45f, 0.9f, 0.45f));
                Assert.IsNotNull(view, "premise: LoadView.Create('plant') failed");
                Transform soilT = view.Carried.Find("Soil");
                Transform leavesT = view.Carried.Find("Leaves");
                Assert.IsNotNull(soilT, "premise: the plant load has no Soil part");
                Assert.IsNotNull(leavesT, "premise: the plant load has no Leaves part");
                Renderer soil = soilT.GetComponent<Renderer>();
                Renderer leaves = leavesT.GetComponent<Renderer>();
                Assert.AreEqual(Surface.Soil, TextureLibrary.SurfaceOf(ShownTexture(soil)), "the fallen load's soil shows no soil detail");
                Assert.AreEqual(Surface.Foliage, TextureLibrary.SurfaceOf(ShownTexture(leaves)), "the fallen load's leaves show no foliage detail");
                Assert.That(soil.sharedMaterial.GetFloat("_Smoothness"), Is.EqualTo(Tuning.SoilSmoothness).Within(1e-4f), "fallen load soil smoothness");
                Assert.That(soil.sharedMaterial.GetFloat("_Metallic"), Is.EqualTo(0f).Within(1e-4f), "fallen load soil metallic");
                Assert.That(leaves.sharedMaterial.GetFloat("_Smoothness"), Is.EqualTo(Tuning.FoliageSmoothness).Within(1e-4f), "fallen load leaves smoothness");
            }
            finally
            {
                Object.Destroy(furniture);
            }
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        // ----- Step61a: M7 textures (CONTRACT_M7 1.2): normal maps and the new Tile floor -----

        /// <summary>The normal map a renderer's slot shows through its property block, or null.</summary>
        private static Texture ShownNormal(Renderer r, int slot)
        {
            var block = new MaterialPropertyBlock();
            r.GetPropertyBlock(block, slot);
            return block.isEmpty ? null : block.GetTexture(BumpMap);
        }

        /// <summary>The slot's own <c>_BumpScale</c> (0 when the property block carries none).</summary>
        private static float ShownBumpScale(Renderer r, int slot)
        {
            var block = new MaterialPropertyBlock();
            r.GetPropertyBlock(block, slot);
            return block.isEmpty ? 0f : block.GetFloat(BumpScale);
        }

        /// <summary>
        /// Every M4.2/M6 detail that reads at play distance, and the new Tile floor, resolves its own 512 normal map
        /// at a positive <c>_BumpScale</c> (CONTRACT_M7 1.2); Plastic, Foliage and Soil (not in the 1.2 list) stay
        /// bump-free. Then level3's kitchen (a room <c>"floorFinish": "tile"</c>): its floor shows the tile detail
        /// and its normal map together, at the tile's own smoothness, and the house material budgets (PRD 7.4) still
        /// hold with the new surface in the mix. Finally level9's robot bumper (Plastic, no normal map in the
        /// library): its slot carries no stale <c>_BumpMap</c> left over from another surface's property block.
        /// </summary>
        [UnityTest]
        public IEnumerator Step61a_NormalMapsAndTheTileFloorShowOnTheRightSlots()
        {
            TextureLibrary library = TextureLibrary.Load();
            Assert.IsNotNull(library, $"premise: no Resources/{TextureLibrary.ResourcePath}");
            var withNormal = new[]
            {
                Surface.Wood, Surface.Parquet, Surface.Plaster, Surface.Upholstery, Surface.Linen, Surface.Carpet,
                Surface.Grass, Surface.Lacquer, Surface.Metal, Surface.Tile,
            };
            foreach (Surface s in withNormal)
            {
                Assert.IsNotNull(TextureLibrary.NormalOf(s), $"premise: {s} has no normal map in the library");
                Assert.Greater(TextureLibrary.BumpScaleOf(s), 0f, $"{s}: its _BumpScale is not a positive value");
            }
            foreach (Surface s in new[] { Surface.Plastic, Surface.Foliage, Surface.Soil })
            {
                Assert.IsNull(TextureLibrary.NormalOf(s), $"{s} is not in the 1.2 list and should stay bump-free");
            }

            yield return LoadLevel("level3");
            List<Slot> level3 = LitSlots(Game.Level.Root.transform);
            List<Slot> tileFloor = level3.Where(s => s.Surface == Surface.Tile).ToList();
            Assert.Greater(tileFloor.Count, 0, "level3: the kitchen floor shows no tile detail");
            foreach (Slot s in tileFloor)
            {
                // M7 real colours (CONTRACT_M7 5): the tile image in its own colours, at the tile's finish and normal map.
                AssertRealColour(s, Surface.Tile, "level3 tile floor");
                Assert.That(s.Material.GetFloat("_Smoothness"), Is.EqualTo(Tuning.TileSmoothness).Within(1e-4f), $"{Label(s)}: tile smoothness");
                Assert.AreSame(TextureLibrary.NormalOf(Surface.Tile), ShownNormal(s.Renderer, s.Index), $"{Label(s)}: shows no tile normal map");
                Assert.That(ShownBumpScale(s.Renderer, s.Index), Is.EqualTo(Tuning.NormalScaleTile).Within(1e-4f), $"{Label(s)}: wrong tile _BumpScale");
            }
            AssertMaterialBudget(Game, "level3");

            yield return LoadLevel("level9");
            Assert.Greater(Game.Robots.Count, 0, "premise: level9 has a robot");
            Renderer bumper = Game.Robots[0].Body.Find("Bumper")?.GetComponent<Renderer>();
            Assert.IsNotNull(bumper, "premise: level9's robot has no Bumper renderer");
            Assert.IsNull(ShownNormal(bumper, 0), "the robot's plastic bumper shows a normal map it should not have");

            CollectionAssert.IsEmpty(errors, "no error logged");
        }
    }
}
