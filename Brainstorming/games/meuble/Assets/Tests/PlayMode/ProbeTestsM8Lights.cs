using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M8 secondary lighting (docs/m8/ROOMS_PLAN.md 5) on the real Boot scene: every typed room of the throwaway level
    /// test_lights gets its fixtures (no collider, Default layer, unshadowed lights inside the room), the quality tiers limit
    /// the lights per room (none on Bas, one on Moyen, all on Haut), the vision results of a level are the same with and
    /// without the secondary lights, and the floor lamp dims the secondary lights of its room and restores them exactly.
    /// Lights_z_Shots is a look tool (explicit): it renders test_lights, level12 and level20 with the lights on and off to
    /// Build/shots/lights.
    /// </summary>
    public sealed class ProbeTestsM8Lights
    {
        private const string TestLevel = "test_lights";

        private Main main;
        private GameState Game => main.Game;
        private readonly List<string> errors = new List<string>();

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            RoomLights.Disabled = false;
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
            RoomLights.Disabled = false;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
            }
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            InputReader.ResetInjections();
            // Also puts the quality back to the platform default (Haut in the editor).
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
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

        private RoomLights Lights => Game.Level.Root.GetComponentInChildren<RoomLights>(true);

        private static RoomLights.Style Expected(string type)
        {
            switch (type)
            {
                case RoomTypes.Bathroom: return RoomLights.Style.Tube;
                case RoomTypes.Kitchen: return RoomLights.Style.Strip;
                case RoomTypes.Dining: return RoomLights.Style.TableLamp;
                case RoomTypes.Bedroom: return RoomLights.Style.Bedside;
                case RoomTypes.Study: return RoomLights.Style.DeskLamp;
                default: return RoomLights.Style.Sconce;
            }
        }

        // ----- a: fixtures by room type, gameplay-free -----

        [UnityTest]
        public IEnumerator Lights_a_EveryTypedRoomGetsItsFixturesAndNoGameplayFootprint()
        {
            yield return LoadLevel(TestLevel);
            RoomLights lights = Lights;
            Assert.IsNotNull(lights, "the level has no RoomLights");
            List<RoomDef> rooms = Game.Def.AllRooms();
            CollectionAssert.AreEquivalent(RoomTypes.All.Where(t => t != RoomTypes.Other), rooms.Select(r => r.Type),
                "premise: test_lights has one room of each type");
            Assert.AreEqual(RoomTypes.Living, rooms.Find(r => r.Id == "atelier").Type, "premise: the declared type of 'atelier'");
            foreach (RoomDef room in rooms)
            {
                List<RoomLights.Fixture> mine = lights.Fixtures.Where(f => f.Room == room).OrderBy(f => f.Rank).ToList();
                Assert.That(mine.Count, Is.InRange(1, RoomLights.MaxPerRoom), $"{room.Id} ({room.Type}): fixtures");
                Assert.AreEqual(Expected(room.Type), mine[0].Style, $"{room.Id} ({room.Type}): first fixture");
                for (int k = 0; k < mine.Count; k++)
                {
                    RoomLights.Fixture f = mine[k];
                    Assert.AreEqual(k, f.Rank, $"{room.Id}: ranks");
                    Assert.IsNotNull(f.Light, $"{room.Id}: fixture {k} has no light");
                    Assert.AreEqual(LightShadows.None, f.Light.shadows, $"{room.Id}: a secondary light casts shadows");
                    Assert.IsTrue(f.Light.type == LightType.Spot || f.Light.type == LightType.Point, $"{room.Id}: light type {f.Light.type}");
                    Assert.IsTrue(room.Contains(f.Light.transform.position), $"{room.Id}: light {k} at {f.Light.transform.position} is not in its room");
                    Assert.AreEqual(room, Game.Def.RoomAt(f.Light.transform.position), $"{room.Id}: light {k} stands in another room");
                    Assert.Less(f.Light.transform.position.y, room.WallHeight, $"{room.Id}: light {k} above the walls");
                    Color c = f.Light.color;
                    if (room.Type == RoomTypes.Bathroom)
                    {
                        Assert.Greater(c.b, c.r, $"{room.Id}: the neon is not cool");
                    }
                    else if (room.Type != RoomTypes.Kitchen && room.Type != RoomTypes.Study)
                    {
                        Assert.Greater(c.r, c.b + 0.3f, $"{room.Id}: the light is not warm");
                    }
                }
            }
            // No collider, nothing on a gameplay layer, no shadow: only the sun casts one (the look's own check).
            Assert.IsEmpty(lights.GetComponentsInChildren<Collider>(true), "a fixture carries a collider");
            foreach (Transform t in lights.GetComponentsInChildren<Transform>(true))
            {
                Assert.AreEqual(0, t.gameObject.layer, $"{t.name} is on layer {LayerMask.LayerToName(t.gameObject.layer)}");
            }
            foreach (Renderer r in lights.GetComponentsInChildren<Renderer>(true))
            {
                Assert.AreEqual(ShadowCastingMode.Off, r.shadowCastingMode, $"{r.name} casts a shadow");
            }
            CollectionAssert.IsEmpty(main.LookProblems(), "the look's checks (one shadowed light, the sun)");
            // Budgets: at most two glow renderers, the warm one the lamp glow's material, the cool one the window pane's.
            Assert.That(lights.Glows.Count, Is.InRange(1, 2), "glow renderers");
            Material pane = Game.Level.Root.GetComponentsInChildren<MeshRenderer>(true).Where(r => r.name == "WindowPane").Select(r => r.sharedMaterial).FirstOrDefault();
            Assert.IsNotNull(pane, "premise: test_lights has window panes");
            foreach (MeshRenderer g in lights.Glows)
            {
                bool cool = g.name.EndsWith("Cool", StringComparison.Ordinal);
                Material expected = cool ? pane : PrimitiveKit.Emissive(new Color(1f, 0.8f, 0.46f), 1.9f);
                Assert.AreSame(expected, g.sharedMaterial, $"{g.name}: not the shared {(cool ? "window pane" : "lamp glow")} material");
            }
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        // ----- b: quality tiers -----

        [UnityTest]
        public IEnumerator Lights_b_TiersLimitTheSecondaryLightsPerRoom()
        {
            yield return LoadLevel(TestLevel);
            int rooms = Game.Def.AllRooms().Count(r => r.Type != RoomTypes.Other);
            int all = Lights.Fixtures.Count;
            Assert.Greater(all, rooms, "premise: some rooms of test_lights have two lights");
            Assert.AreEqual(all, Lights.EnabledLights, "premise: Haut (the editor default) keeps every light");
            var tiers = new[] { (SaveOptions.QualityLow, 0), (SaveOptions.QualityMedium, 1), (SaveOptions.QualityHigh, RoomLights.MaxPerRoom) };
            foreach ((string tier, int perRoom) in tiers)
            {
                QualityTier.Apply(new SaveOptions { Quality = tier });
                yield return null;
                yield return null;
                AssertTier(tier, perRoom, "switched while playing");
                Game.Restart();
                yield return Steps(2);
                AssertTier(tier, perRoom, "after a restart");
            }
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        private void AssertTier(string tier, int perRoom, string when)
        {
            RoomLights lights = Lights;
            Assert.AreEqual(tier, lights.Tier, $"{tier} {when}: the tier the lights follow");
            foreach (RoomDef room in Game.Def.AllRooms())
            {
                List<RoomLights.Fixture> mine = lights.Fixtures.Where(f => f.Room == room).ToList();
                int on = mine.Count(f => f.Light.enabled);
                Assert.AreEqual(Mathf.Min(perRoom, mine.Count), on, $"{tier} {when}: {room.Id} has {on} lights on of {mine.Count}");
                Assert.IsTrue(mine.Where(f => f.Light.enabled).All(f => f.Rank < perRoom), $"{tier} {when}: {room.Id} keeps a later light on");
            }
            // The glowing fixtures stay on every tier (Bas: emissive only).
            Assert.IsTrue(lights.Glows.Count > 0 && lights.Glows.All(g => g.enabled && g.gameObject.activeInHierarchy), $"{tier} {when}: glows");
            int enabled = Object.FindObjectsByType<Light>(FindObjectsSortMode.None)
                .Count(l => l.enabled && l.type != LightType.Directional && l.transform.IsChildOf(lights.transform));
            Assert.AreEqual(lights.EnabledLights, enabled, $"{tier} {when}: enabled secondary lights in the scene");
            if (tier == SaveOptions.QualityLow)
            {
                Assert.AreEqual(0, enabled, "Bas: a secondary light is on");
            }
        }

        // ----- c: vision never reads the lights -----

        [UnityTest]
        public IEnumerator Lights_c_VisionIsTheSameWithAndWithoutTheSecondaryLights()
        {
            foreach (string id in new[] { TestLevel, "level20", "level12" })
            {
                yield return LoadLevel(id);
                RoomLights lights = Lights;
                Assert.IsNotNull(lights, $"{id}: premise: secondary lights");
                Assert.Greater(lights.EnabledLights, 0, $"{id}: premise: lights on");
                List<string> on = Sweep(out int seen);
                Assert.Greater(seen, 0, $"{id}: premise: the sweep sees the player somewhere");
                lights.gameObject.SetActive(false);
                Physics.SyncTransforms();
                List<string> off = Sweep(out _);
                lights.gameObject.SetActive(true);
                Assert.AreEqual(on.Count, off.Count, $"{id}: premise: same sweep");
                for (int i = 0; i < on.Count; i++)
                {
                    Assert.AreEqual(on[i], off[i], $"{id}: the vision changed with the secondary lights off");
                }

                // A level built without them at all (no fixture, no light) sees the same as well.
                List<string> colliders = Colliders();
                RoomLights.Disabled = true;
                Game.Restart();
                yield return Steps(2);
                Assert.IsNull(Lights, $"{id}: premise: built without secondary lights");
                CollectionAssert.AreEqual(colliders, Colliders(), $"{id}: the secondary lights changed a collider");
                RoomLights.Disabled = false;
                Game.Restart();
                yield return Steps(2);
            }
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>The player furniture on a grid over the house, each watcher's vision of it (seen and the samples seen).</summary>
        private List<string> Sweep(out int seen)
        {
            var results = new List<string>();
            seen = 0;
            FurnitureController chair = Game.Furniture;
            Vector3 home = chair.transform.position;
            float yaw = chair.Yaw;
            Rect box = Game.Def.InteriorBounds();
            var sb = new StringBuilder();
            for (float x = box.xMin + 0.3f; x < box.xMax; x += 0.7f)
            {
                for (float z = box.yMin + 0.3f; z < box.yMax; z += 0.7f)
                {
                    if (Game.Def.RoomAt(new Vector3(x, 0f, z)) == null)
                    {
                        continue;
                    }
                    chair.Teleport(new Vector3(x, 0f, z), 45f);
                    Physics.SyncTransforms();
                    foreach (Vision v in Game.Level.Visions)
                    {
                        bool sees = v.Step(chair);
                        seen += sees ? 1 : 0;
                        sb.Clear().Append(x.ToString("0.00")).Append(',').Append(z.ToString("0.00")).Append(' ').Append(v.name).Append(' ').Append(sees)
                            .Append(' ').Append(v.Range.ToString("0.0000"));
                        foreach (bool s in v.SampleVisible)
                        {
                            sb.Append(s ? '1' : '0');
                        }
                        results.Add(sb.ToString());
                    }
                }
            }
            chair.Teleport(home, yaw);
            Physics.SyncTransforms();
            return results;
        }

        /// <summary>The static colliders of the level (the player furniture and the inhabitants move, and are not decor).</summary>
        private List<string> Colliders()
        {
            return Game.Level.Root.GetComponentsInChildren<Collider>(true)
                .Where(c => c.gameObject.layer != Layers.Player && c.gameObject.layer != Layers.Inhabitant)
                .Select(c => $"{c.name} {c.gameObject.layer} {c.bounds.center.ToString("F3")} {c.bounds.size.ToString("F3")}")
                .OrderBy(s => s, StringComparer.Ordinal).ToList();
        }

        // ----- d: the floor lamp dims the secondary lights of its room -----

        [UnityTest]
        public IEnumerator Lights_d_TheLampDimsTheSecondaryLightsOfItsRoomOnly()
        {
            yield return LoadLevel("level20");
            LampLight lamp = Game.Furniture.Lamp;
            Assert.IsNotNull(lamp, "premise: level20's player is the floor lamp");
            RoomDef lampRoom = Game.Def.RoomAt(lamp.transform.position);
            Assert.IsNotNull(lampRoom, "premise: the lamp stands in a room");
            RoomLights lights = Lights;
            List<RoomLights.Fixture> inRoom = lights.Fixtures.Where(f => f.Room == lampRoom && f.Light.enabled).ToList();
            List<RoomLights.Fixture> elsewhere = lights.Fixtures.Where(f => f.Room != lampRoom && f.Light.enabled).ToList();
            Assert.IsNotEmpty(inRoom, $"premise: the lamp's room {lampRoom.Id} has a secondary light");
            Assert.IsNotEmpty(elsewhere, "premise: other rooms have secondary lights");
            Assert.IsTrue(lights.Fixtures.All(f => Mathf.Approximately(f.Light.intensity, f.Intensity)), "premise: every light at its own intensity");

            lamp.SetOn(false);
            foreach (RoomLights.Fixture f in inRoom)
            {
                Assert.AreEqual(f.Intensity * Tuning.LampOffLight, f.Light.intensity, 1e-5f, $"{f.Light.name} was not dimmed with the lamp");
            }
            foreach (RoomLights.Fixture f in elsewhere)
            {
                Assert.AreEqual(f.Intensity, f.Light.intensity, 1e-6f, $"{f.Light.name} in {f.Room.Id} was dimmed by a lamp in another room");
            }
            Assert.AreEqual(Tuning.LampOffLight, lamp.RangeFactor, 1e-6f, "the lamp's own rule");
            lamp.SetOn(true);
            foreach (RoomLights.Fixture f in lights.Fixtures)
            {
                Assert.AreEqual(f.Intensity, f.Light.intensity, 1e-6f, $"{f.Light.name} was not restored exactly");
            }
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        // ----- e: budgets (PRD 7.4) -----

        [UnityTest]
        public IEnumerator Lights_e_EveryLevelGainsAtMostTwoDrawCallsAndTwoMaterials()
        {
            var table = new List<string>();
            foreach (string id in Game.LevelOrder)
            {
                // Walls 4 (the flaky failures of the M9 runs, a different level each time): a watcher's vision cone shows or
                // hides with its state at the snapshot (the dog asleep or awake: "VisionCone Rex" came between the two
                // counts on level16), which the lights never touch; the comparison leaves the cones out, as Step39h does.
                // The budgets themselves are asserted below on everything drawn, cones included.
                RoomLights.Disabled = true;
                yield return LoadLevel(id);
                Probe.RenderCount before = Probe.CountRenderers(NotCones());
                List<string> drawnBefore = DrawnSlots();
                RoomLights.Disabled = false;
                Game.Restart();
                yield return Steps(2);
                Probe.RenderCount after = Probe.CountRenderers(NotCones());
                Probe.RenderCount drawn = Probe.CountRenderers(Game.Level.Root.GetComponentsInChildren<Renderer>(false));
                List<string> drawnAfter = DrawnSlots();
                // Walls 4: what differs besides the lights, named, so a failure says which renderer came or went.
                string diff = "added: " + string.Join(", ", Except(drawnAfter, drawnBefore)) + "; gone: " + string.Join(", ", Except(drawnBefore, drawnAfter));
                // M7 walls pass: the see-through walls' one material counts whatever the Walls option (as the probe counts it).
                if (Game.Level.Root.GetComponent<WallFader>().Count > 0)
                {
                    before.Materials.Add(WallFader.GhostMaterial);
                    after.Materials.Add(WallFader.GhostMaterial);
                    drawn.Materials.Add(WallFader.GhostMaterial);
                }
                RoomLights lights = Lights;
                int fixtures = lights != null ? lights.Fixtures.Count : 0;
                int slots = after.MaterialSlots - before.MaterialSlots;
                int materials = after.Materials.Count - before.Materials.Count;
                Assert.LessOrEqual(slots, 2, $"{id}: the secondary lights add {slots} draw calls ({diff})");
                Assert.LessOrEqual(materials, 2, $"{id}: the secondary lights add {materials} materials");
                Assert.AreEqual(lights != null ? lights.Glows.Count : 0, after.Renderers - before.Renderers, $"{id}: renderers added besides the glows ({diff})");
                bool house = Game.Def.AllRooms().Count >= Tuning.HouseBudgetRooms;
                Assert.LessOrEqual(drawn.MaterialSlots, house ? Tuning.BudgetHouseRenderers : Tuning.BudgetRenderers, $"{id}: draw calls with the lights");
                Assert.LessOrEqual(drawn.Materials.Count, house ? Tuning.BudgetHouseMaterials : Tuning.BudgetMaterials, $"{id}: materials with the lights");
                table.Add($"{id}: {fixtures} lights, draw calls {before.MaterialSlots} -> {after.MaterialSlots} (+{slots}), materials "
                    + $"{before.Materials.Count} -> {after.Materials.Count} (+{materials}) of {(house ? Tuning.BudgetHouseMaterials : Tuning.BudgetMaterials)}");
            }
            Debug.Log("[Lights_e] " + string.Join(" | ", table));
            TestContext.WriteLine("[Lights_e] " + string.Join(" | ", table));
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>The level's renderers but the vision cones (their visibility follows the watchers' state, never the lights).</summary>
        private List<Renderer> NotCones()
        {
            return Game.Level.Root.GetComponentsInChildren<Renderer>(false).Where(r => r.GetComponentInParent<VisionConeView>() == null).ToList();
        }

        /// <summary>Every drawn renderer of the level but the cones as "parent/name x slots", one entry each (a sorted multiset).</summary>
        private List<string> DrawnSlots()
        {
            var list = new List<string>();
            foreach (Renderer r in NotCones())
            {
                if (r.enabled && r.gameObject.activeInHierarchy)
                {
                    list.Add($"{(r.transform.parent != null ? r.transform.parent.name : "")}/{r.name} x{r.sharedMaterials.Length}");
                }
            }
            list.Sort(StringComparer.Ordinal);
            return list;
        }

        /// <summary>The entries of <paramref name="a"/> not matched one for one in <paramref name="b"/>.</summary>
        private static List<string> Except(List<string> a, List<string> b)
        {
            var left = new List<string>(b);
            var result = new List<string>();
            foreach (string s in a)
            {
                if (!left.Remove(s))
                {
                    result.Add(s);
                }
            }
            return result;
        }

        // ----- z: the look shots (a tool, explicit) -----

        private static string ShotsDir => Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Build", "shots", "lights"));

        [UnityTest, Explicit("look tool: renders Build/shots/lights")]
        public IEnumerator Lights_z_Shots()
        {
            Directory.CreateDirectory(ShotsDir);
            var log = new List<string>();
            yield return LoadLevel(TestLevel);
            // No rule runs while the player furniture is moved around for the views (nobody catches it, no restart).
            Game.Paused = true;
            foreach (RoomDef room in Game.Def.AllRooms())
            {
                Vector3 centre = new Vector3(room.X, 0f, room.Z);
                yield return Shoot($"test_lights_{room.Type}", centre, 0f, 58f, Mathf.Max(6.5f, Mathf.Max(room.SizeX, room.SizeZ) * 1.6f), log);
            }
            Rect all = Game.Def.InteriorBounds();
            yield return Shoot("test_lights_house", new Vector3(all.center.x, 0f, all.center.y), 0f, 62f, 17f, log);
            foreach (string id in new[] { "level12", "level20" })
            {
                Game.Paused = false;
                yield return LoadLevel(id);
                Game.Paused = true;
                Rect house = Game.Def.InteriorBounds();
                var mid = new Vector3(house.center.x, 0f, house.center.y);
                float far = Mathf.Max(house.width, house.height) * 1.05f;
                yield return Shoot($"{id}_house", mid, 0f, 60f, far, log);
                yield return Shoot($"{id}_house_back", mid, 180f, 55f, far, log);
                FurnitureController chair = Game.Furniture;
                Vector3 start = chair.transform.position;
                yield return Shoot($"{id}_start", start, chair.Yaw, Tuning.PitchDefault, Tuning.OrbitDistance * 1.3f, log, false);
                QualityTier.Apply(new SaveOptions { Quality = SaveOptions.QualityMedium });
                yield return null;
                yield return Shoot($"{id}_house_moyen", mid, 0f, 60f, far, log, false);
                QualityTier.Apply(new SaveOptions { Quality = SaveOptions.QualityHigh });
                yield return null;
            }
            File.WriteAllLines(Path.Combine(ShotsDir, "shots_log.txt"), log);
            Debug.Log("[LightShots] " + string.Join(" | ", log));
        }

        /// <summary>
        /// Renders the view of <paramref name="focus"/> from <paramref name="yaw"/>, <paramref name="pitch"/> and
        /// <paramref name="distance"/> with the secondary lights on (and off unless <paramref name="pair"/> is false), the player
        /// moved to the focus so the walls in front fade as in play, and logs how much the lights changed the frame.
        /// </summary>
        private IEnumerator Shoot(string name, Vector3 focus, float yaw, float pitch, float distance, List<string> log, bool pair = true)
        {
            FurnitureController chair = Game.Furniture;
            Vector3 home = chair.transform.position;
            float homeYaw = chair.Yaw;
            Vector3 spot = FreeSpot(focus);
            chair.Teleport(spot, yaw);
            Physics.SyncTransforms();
            yield return null;
            Camera cam = main.Camera;
            Quaternion rotation = Quaternion.Euler(pitch, yaw, 0f);
            Vector3 position = focus + Vector3.up * 0.6f - rotation * Vector3.forward * distance;
            var fader = Game.Level.Root.GetComponent<WallFader>();
            RoomLights lights = Lights;
            Color32[] lit = Render(cam, position, rotation, fader);
            Save(name + (pair ? "_on" : ""), lit);
            if (pair && lights != null)
            {
                lights.gameObject.SetActive(false);
                Color32[] dark = Render(cam, position, rotation, fader);
                lights.gameObject.SetActive(true);
                Save(name + "_off", dark);
                double sum = 0;
                int max = 0;
                int changed = 0;
                int redOn = 0, redOff = 0;
                for (int i = 0; i < lit.Length; i++)
                {
                    int d = Luma(lit[i]) - Luma(dark[i]);
                    sum += d;
                    max = Math.Max(max, d);
                    changed += d > 8 ? 1 : 0;
                    redOn += ModelMath.IsRed(lit[i]) ? 1 : 0;
                    redOff += ModelMath.IsRed(dark[i]) ? 1 : 0;
                }
                log.Add($"{name}: mean luma +{sum / lit.Length:0.00}, max +{max}, {100.0 * changed / lit.Length:0.0}% px brighter by more than 8, red px {redOff} -> {redOn}");
            }
            chair.Teleport(home, homeYaw);
            Physics.SyncTransforms();
            Game.Camera.Snap();
            yield return null;
        }

        private Vector3 FreeSpot(Vector3 focus)
        {
            // The player furniture as the fade target, on the floor near the focus and clear of the props.
            for (float r = 0f; r < 3f; r += 0.25f)
            {
                for (int a = 0; a < 8; a++)
                {
                    Vector3 p = focus + Quaternion.Euler(0f, a * 45f, 0f) * Vector3.forward * r;
                    if (Game.Def.RoomAt(p) != null && !Physics.CheckSphere(p + Vector3.up * 0.5f, 0.35f, Layers.OccluderMask, QueryTriggerInteraction.Ignore))
                    {
                        return p;
                    }
                }
            }
            return focus;
        }

        private const int Width = 1280;
        private const int Height = 720;

        private static Color32[] Render(Camera cam, Vector3 position, Quaternion rotation, WallFader fader)
        {
            cam.transform.SetPositionAndRotation(position, rotation);
            fader.Apply(position);
            fader.DrawFaded(cam);
            RenderTexture rt = RenderTexture.GetTemporary(Width, Height, 24);
            var request = new RenderPipeline.StandardRequest { destination = rt };
            RenderPipeline.SubmitRenderRequest(cam, request);
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = rt;
            var texture = new Texture2D(Width, Height, TextureFormat.RGBA32, false);
            texture.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
            texture.Apply();
            RenderTexture.active = previous;
            RenderTexture.ReleaseTemporary(rt);
            Color32[] pixels = texture.GetPixels32();
            Object.Destroy(texture);
            return pixels;
        }

        private static void Save(string name, Color32[] pixels)
        {
            var texture = new Texture2D(Width, Height, TextureFormat.RGBA32, false);
            texture.SetPixels32(pixels);
            texture.Apply();
            File.WriteAllBytes(Path.Combine(ShotsDir, name + ".png"), texture.EncodeToPNG());
            Object.Destroy(texture);
        }

        private static int Luma(Color32 c)
        {
            return (c.r * 299 + c.g * 587 + c.b * 114) / 1000;
        }
    }
}
