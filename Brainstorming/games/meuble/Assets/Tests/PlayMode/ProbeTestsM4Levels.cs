using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Meuble.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace Meuble.Tests
{
    /// <summary>
    /// M4 levels probe (docs/CONTRACT_M4.md 2, 4, amendments 9.5 and 9.13), on the real Boot scene.
    ///
    /// Phase A (35a): the level builder makes every furniture body from its kind (BodyDef size, controller, model or
    /// procedural visual within 400 triangles, the lamp's LampLight), decoys of every kind at their kind's size, the
    /// "armchair" prop with collider-only parts under its model, and the facing of the new seat models. Each step
    /// asserts its premise first (a model exists, the level changed), so a builder that does nothing cannot pass.
    /// Phase C adds the designer route replays of levels 4 to 7 (step 35), M5: through the shared RouteReplayer.
    /// </summary>
    public sealed class ProbeTestsM4Levels
    {
        private Main main;
        private GameState Game => main.Game;
        private readonly List<string> errors = new List<string>();
        private readonly List<Object> scratch = new List<Object>();

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            ModelKit.Disabled = false;
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
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            ModelKit.Disabled = false;
            Application.logMessageReceived -= OnLog;
            foreach (Object o in scratch)
            {
                if (o != null)
                {
                    Object.DestroyImmediate(o);
                }
            }
            scratch.Clear();
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

        private Transform Scratch(string name)
        {
            var go = new GameObject(name);
            scratch.Add(go);
            return go.transform;
        }

        /// <summary>Level 1 rebuilt with a player of <paramref name="kind"/>, sized and modelled as its body.</summary>
        private IEnumerator RebuildWithBody(string kind)
        {
            BodyDef body = BodyDef.For(kind);
            SpawnDef p = Game.Def.Player;
            p.Kind = kind;
            p.Model = body.Model;
            p.SizeX = body.Size.x;
            p.SizeY = body.Size.y;
            p.SizeZ = body.Size.z;
            Game.Restart();
            yield return Steps(2);
        }

        /// <summary>Union of the renderer bounds under <paramref name="root"/>, relative to <paramref name="origin"/>.</summary>
        private static Bounds RendererBounds(Transform root, Vector3 origin)
        {
            Renderer[] renderers = root.GetComponentsInChildren<Renderer>(true);
            Assert.Greater(renderers.Length, 0, root.name + ": no renderer");
            Bounds b = renderers[0].bounds;
            foreach (Renderer r in renderers)
            {
                b.Encapsulate(r.bounds);
            }
            b.center -= origin;
            return b;
        }

        /// <summary>The visual fills no more than the box of <paramref name="size"/> (centred, on the floor).</summary>
        private static void AssertWithinBox(Bounds b, Vector3 size, string label)
        {
            const float tolerance = 0.01f;
            Assert.That(b.min.y, Is.GreaterThanOrEqualTo(-tolerance), $"{label}: bottom at {b.min.y:0.###}");
            Assert.That(b.max.y, Is.LessThanOrEqualTo(size.y + tolerance), $"{label}: top at {b.max.y:0.###}, the body is {size.y} tall");
            Assert.That(Mathf.Max(Mathf.Abs(b.min.x), Mathf.Abs(b.max.x)), Is.LessThanOrEqualTo(size.x * 0.5f + tolerance), $"{label}: x {b.min.x:0.###} to {b.max.x:0.###}");
            Assert.That(Mathf.Max(Mathf.Abs(b.min.z), Mathf.Abs(b.max.z)), Is.LessThanOrEqualTo(size.z * 0.5f + tolerance), $"{label}: z {b.min.z:0.###} to {b.max.z:0.###}");
            Assert.That(b.size.y, Is.GreaterThan(size.y * 0.9f), $"{label}: the visual is {b.size.y:0.###} tall, the body {size.y}");
        }

        /// <summary>Every collider under <paramref name="root"/>: "type name layer" and its world bounds, sorted by key.</summary>
        private static List<(string key, Bounds bounds)> Colliders(Transform root)
        {
            var set = new List<(string key, Bounds bounds)>();
            foreach (Collider c in root.GetComponentsInChildren<Collider>(true))
            {
                set.Add((string.Format(CultureInfo.InvariantCulture, "{0} {1} L{2}", c.GetType().Name, c.name, c.gameObject.layer), c.bounds));
            }
            set.Sort((a, b) => StringComparer.Ordinal.Compare(a.key, b.key));
            return set;
        }

        /// <summary>Same colliders: same keys, bounds within a millimetre (a mesh-scaled and a collider-only box round apart).</summary>
        private static void AssertSameColliders(List<(string key, Bounds bounds)> expected, List<(string key, Bounds bounds)> actual, string label)
        {
            Assert.AreEqual(expected.Count, actual.Count, label + ": collider count");
            for (int i = 0; i < expected.Count; i++)
            {
                Assert.AreEqual(expected[i].key, actual[i].key, label);
                Assert.That((expected[i].bounds.center - actual[i].bounds.center).magnitude, Is.LessThan(1e-3f), $"{label}: {expected[i].key} centre");
                Assert.That((expected[i].bounds.size - actual[i].bounds.size).magnitude, Is.LessThan(1e-3f), $"{label}: {expected[i].key} size");
            }
        }

        /// <summary>The side (sign of z in <paramref name="frame"/>) of the top 15 % of a model's vertices, and its depth.</summary>
        private static float TallestSide(Transform model, Transform frame, out float depth)
        {
            var points = new List<Vector3>();
            foreach (MeshFilter f in model.GetComponentsInChildren<MeshFilter>(true))
            {
                Assert.IsTrue(f.sharedMesh.isReadable, $"{f.name}: mesh not readable, the facing test cannot see it");
                foreach (Vector3 v in f.sharedMesh.vertices)
                {
                    points.Add(frame.InverseTransformPoint(f.transform.TransformPoint(v)));
                }
            }
            Assert.Greater(points.Count, 0, model.name + ": no vertex");
            float minY = points.Min(p => p.y);
            float maxY = points.Max(p => p.y);
            depth = points.Max(p => p.z) - points.Min(p => p.z);
            float cut = maxY - 0.15f * (maxY - minY);
            return points.Where(p => p.y >= cut).Average(p => p.z);
        }

        // ----- 35: the designer routes of levels 4 to 7 (RouteReplayer) -----

        /// <summary>
        /// Step 35 (CONTRACT_M4 4 and 8, amendment 9.4): every designer route of levels 4 to 7 wins under the M4 rules
        /// with every "at" shifted by -0.2 s, 0 and +0.2 s, with no discovery, no alert and no creak, and plays its
        /// level's lesson: the stool never tips and stays under the tip speed, the armchair is sat on and nobody falls,
        /// the lamp is switched and nobody comes to switch it on, the office chair stops beside decoys.
        /// </summary>
        [UnityTest]
        [Timeout(900000)]
        public IEnumerator Step35_DesignerRoutesOfLevels4To7()
        {
            var failures = new List<string>();
            foreach (string level in new[] { "level4", "level5", "level6", "level7" })
            {
                foreach (float offset in new[] { -0.2f, 0f, 0.2f })
                {
                    if (!new List<string>(Game.LevelOrder).Contains(level))
                    {
                        failures.Add($"{level}: not listed in levels.json");
                        break;
                    }
                    int errorsBefore = errors.Count;
                    Game.LoadLevel(level);
                    Game.Rules = GameRules.M4;
                    yield return Steps(1);
                    if (errors.Count != errorsBefore)
                    {
                        failures.Add($"{level}: error(s) at boot: {string.Join(" | ", errors.Skip(errorsBefore))}");
                    }
                    if (Game.Def.DesignerRoute == null || Game.Def.DesignerRoute.Count < 2)
                    {
                        failures.Add($"{level}: no designerRoute");
                        break;
                    }
                    var r = new RouteReplayer.Result();
                    yield return RouteReplayer.Replay(Game, offset, r, 8f);
                    string id = r.Label;
                    Debug.Log("[Step35] " + r);
                    if (r.State != PlayState.Won)
                    {
                        failures.Add($"{id}: the route did not win ({r.State}, {r.Reason}) after {r.Time:0.0} s, waypoint {r.Waypoint}/{r.Waypoints}");
                    }
                    if (r.Discoveries != 0 || r.Alerts != 0 || r.Creaks != 0)
                    {
                        failures.Add($"{id}: {r.Discoveries} discoveries, {r.Alerts} alerts, {r.Creaks} creaks (all must be 0)");
                    }
                    switch (level)
                    {
                        case "level4":
                            if (r.Topples != 0 || r.TopSpeed > Tuning.StoolTipSpeed)
                            {
                                failures.Add($"{id}: the careful stool tipped ({r.Topples}) or went {r.TopSpeed:0.00} m/s, above {Tuning.StoolTipSpeed}");
                            }
                            break;
                        case "level5":
                            if (r.SatOn == 0 || !r.Pinned || r.Pratfalls != 0)
                            {
                                failures.Add($"{id}: sat on {r.SatOn} time(s), pinned {r.Pinned}, {r.Pratfalls} pratfalls (the armchair must be home in time)");
                            }
                            break;
                        case "level6":
                            if (r.Toggles == 0 || r.SwitchOns != 0)
                            {
                                failures.Add($"{id}: {r.Toggles} toggles, {r.SwitchOns} switch-ons (the lamp crosses dark, unseen)");
                            }
                            break;
                        case "level7":
                            if (r.Explained == 0)
                            {
                                failures.Add($"{id}: the route never stopped beside a decoy in sight (no ExplainedByDecoy step)");
                            }
                            break;
                    }
                }
            }
            Assert.IsEmpty(failures, string.Join("\n", failures));
        }

        /// <summary>
        /// CONTRACT_M4 10.1: the lesson of level 5 cannot be skipped. A "rush" counter-route (drive straight at the exit
        /// from the first step, never waiting) does not win: it is caught, or it is still short of the exit at the first
        /// moment an inhabitant sits on the player. Premises: the rush really moves, and the sitting really happens.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator Step35b_Level5RushDoesNotWin()
        {
            Game.LoadLevel("level5");
            Game.Rules = GameRules.M4;
            yield return Steps(1);
            FurnitureController chair = Game.Furniture;
            Vector3 home = YawMath.Planar(chair.transform.position);
            var exit = new Vector3(Game.Def.Exit.X, 0f, Game.Def.Exit.Z);
            bool sat = false;
            bool wonBeforeSitting = false;
            float sitAt = -1f;
            float travelled = 0f;
            Vector3 atSitting = home;
            void Rush()
            {
                FurnitureController f = Game.Furniture;
                travelled = Mathf.Max(travelled, YawMath.Planar(f.transform.position - home).magnitude);
                foreach (Inhabitant h in Game.Level.Inhabitants)
                {
                    if (!sat && h.Routine.JustSat)
                    {
                        sat = true;
                        sitAt = Game.Elapsed;
                        atSitting = YawMath.Planar(f.transform.position);
                    }
                }
                wonBeforeSitting |= Game.State == PlayState.Won && !sat;
                Vector3 to = YawMath.Planar(exit - f.transform.position);
                f.ScriptedDirection = Game.State == PlayState.Playing && !f.Pinned && to.magnitude > 0.05f ? to.normalized : (Vector3?)null;
            }
            Game.FixedStepped += Rush;
            try
            {
                yield return RouteReplayer.RunFor(Game, 60f, () => sat || Game.State != PlayState.Playing, 8f);
            }
            finally
            {
                Game.FixedStepped -= Rush;
                Game.Furniture.ScriptedDirection = null;
            }
            Debug.Log($"[Step35b] level5 rush: {Game.State} ({Game.LoseReason}) at {Game.Elapsed:0.0} s, sat at {sitAt:0.0} s, travelled {travelled:0.00} m, "
                      + $"{Planar(atSitting, exit):0.00} m from the exit at the sitting");
            Assert.Greater(travelled, 0.5f, "premise: the rush never moved");
            Assert.IsFalse(wonBeforeSitting, "the rush reached the exit before anybody sat on the armchair: the lesson can be skipped");
            Assert.AreNotEqual(PlayState.Won, Game.State, "the rush won");
            Assert.IsTrue(sat || Game.State == PlayState.Caught, "premise: neither caught nor sat on within 60 s");
            if (Game.State == PlayState.Playing)
            {
                Assert.IsFalse(Game.Def.Exit.Contains(atSitting), "the rush stood in the exit at the sitting");
            }
        }

        private static float Planar(Vector3 a, Vector3 b) => YawMath.Planar(a - b).magnitude;

        // ----- 35a: the player body -----

        [UnityTest]
        public IEnumerator Step35a_EveryBodyBuildsFromItsKind()
        {
            yield return LoadLevel("level1");
            Color red = LevelJson.ParseColor(Game.Def.Player.Color, Color.red);
            foreach (string kind in BodyKinds.All)
            {
                BodyDef body = BodyDef.For(kind);
                yield return RebuildWithBody(kind);
                FurnitureController f = Game.Furniture;
                string label = "body " + kind;
                Assert.AreEqual(kind, f.Body.Kind, label + ": SetBody was not called with the kind's body");
                Assert.AreEqual(kind, f.Kind, label + ": furniture kind");
                Assert.AreEqual(LevelBuilder.PlayerObjectName(body), f.name, label);
                Assert.AreEqual(body.Size, f.Size, label + ": the sample box is the body size");
                var cc = f.GetComponent<CharacterController>();
                Assert.AreEqual(body.Radius, cc.radius, 1e-4f, label + ": controller radius");
                Assert.AreEqual(body.Size.y, cc.height, 1e-4f, label + ": controller height");
                Assert.AreEqual(1, f.GetComponentsInChildren<Collider>(true).Length, label + ": the controller is the player's only collider");
                Assert.AreEqual(body.HasLight, f.GetComponent<LampLight>() != null, label + ": a LampLight exactly on the lamp");
                Assert.AreEqual(body.HasLight, f.Lamp != null, label + ": FurnitureController.Lamp");
                foreach (VisionConeView cone in Game.Level.Cones)
                {
                    Assert.AreEqual(body.Size.y - Tuning.SampleInset, cone.TargetHeight, 1e-4f, label + ": the floor cone aims at the body's top");
                }

                List<Transform> roots = ModelKit.ModelRootsUnder(f.transform);
                CollectionAssert.IsEmpty(Game.Level.ModelFallbacks, label + ": fallbacks");
                if (body.Model != null)
                {
                    Assert.AreEqual(1, roots.Count, label + ": the body's model");
                    StringAssert.EndsWith(body.Model, roots[0].name, label);
                    foreach (Renderer r in f.Visual.GetComponentsInChildren<Renderer>(true))
                    {
                        Assert.IsNotNull(ModelKit.ModelRootOf(r.transform), $"{label}: procedural renderer {r.name} next to the model");
                    }
                }
                else
                {
                    Assert.AreEqual(0, roots.Count, label + ": no model");
                    Assert.Greater(f.GetComponentsInChildren<MeshRenderer>(true).Length, 0, label + ": no procedural visual");
                }
                // M6 (CONTRACT_M6 2.4): the player's own furniture is lacquered (PrimitiveKit.LitSurface), not a plain Lit material.
                Assert.IsTrue(f.GetComponentsInChildren<Renderer>(true).Any(r => r.sharedMaterials.Contains(PrimitiveKit.LitSurface(red, Surface.Lacquer))),
                    label + ": nothing is in the player colour");
                long triangles = Probe.TrianglesUnder(f.transform);
                Assert.Greater(triangles, 0, label + ": premise: triangles are counted");
                Assert.LessOrEqual(triangles, Tuning.BudgetFurnitureTriangles, $"{label}: {triangles} triangles");
                AssertWithinBox(RendererBounds(f.Visual, f.transform.position), body.Size, label);
                Debug.Log($"[Step35a] {label}: {triangles} triangles, {f.GetComponentsInChildren<Renderer>(true).Length} renderers, model {body.Model ?? "none"}");
            }

            // The office chair: a seat, a backrest on -z, and the metal frame (hub, column, post, five spokes on wheels)
            // as one mesh: 3 renderers per chair (level 7 has five office chairs within the 120 renderer budget).
            yield return RebuildWithBody(BodyKinds.OfficeChair);
            Transform visual = Game.Furniture.Visual;
            foreach (string part in new[] { "Seat", "Backrest", "Frame" })
            {
                Assert.IsNotNull(visual.Find(part), "office chair: no " + part);
            }
            Assert.AreEqual(3, visual.GetComponentsInChildren<MeshRenderer>(true).Length, "office chair: 3 renderers");
            Assert.Less(visual.Find("Backrest").localPosition.z, 0f, "office chair: the backrest is on -z, as the chair's");
            Assert.AreEqual(5, FurnitureKit.OfficeChairSpokes);
            Mesh frame = visual.Find("Frame").GetComponent<MeshFilter>().sharedMesh;
            // Hub and post 24, column 24, 5 spokes 60, 5 wheels 180.
            Assert.AreEqual(288, ModelKit.Triangles(frame), "office chair frame: hub, post, column, five spokes and five wheels");
            Assert.AreSame(frame, FurnitureKit.OfficeChairFrame(BodyDef.For(BodyKinds.OfficeChair).Size), "the frame mesh is cached by size");

            // Without models, every body builds its procedural visual within the budget and the box.
            ModelKit.Disabled = true;
            try
            {
                foreach (string kind in BodyKinds.All)
                {
                    BodyDef body = BodyDef.For(kind);
                    yield return RebuildWithBody(kind);
                    FurnitureController f = Game.Furniture;
                    string label = "procedural " + kind;
                    Assert.AreEqual(0, ModelKit.ModelRootsUnder(f.transform).Count, label);
                    Assert.Greater(f.GetComponentsInChildren<MeshRenderer>(true).Length, 0, label + ": no visual");
                    Assert.AreEqual(1, f.GetComponentsInChildren<Collider>(true).Length, label + ": a procedural part carries a collider");
                    long triangles = Probe.TrianglesUnder(f.transform);
                    Assert.LessOrEqual(triangles, Tuning.BudgetFurnitureTriangles, $"{label}: {triangles} triangles");
                    AssertWithinBox(RendererBounds(f.Visual, f.transform.position), body.Size, label);
                }
            }
            finally
            {
                ModelKit.Disabled = false;
            }
            yield return RebuildWithBody(BodyKinds.Chair);
            Game.Def.Player.Model = null;
            Game.Restart();
            Assert.AreEqual(6, Game.Furniture.GetComponentsInChildren<MeshRenderer>(true).Length, "a chair without a model is the M1 chair (6 boxes)");
            Assert.AreEqual(0, ModelKit.ModelRootsUnder(Game.Furniture.transform).Count, "no default model for the chair (M3 data)");
            yield return Steps(5);
            Assert.AreEqual(PlayState.Playing, Game.State);
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        // ----- 35a: decoys of every kind -----

        [UnityTest]
        public IEnumerator Step35a_DecoysOfEveryKindTakeTheirBodySize()
        {
            yield return LoadLevel("level1");
            Assert.IsEmpty(Game.Def.Decoys, "premise: level 1 has no decoy");
            // Free spots of level 1, clear of the props, the stations and their walks.
            var spots = new Dictionary<string, Vector2>
            {
                { BodyKinds.Chair, new Vector2(-2.4f, -1.0f) },
                { BodyKinds.Stool, new Vector2(-3.5f, 2.5f) },
                { BodyKinds.Armchair, new Vector2(-3.4f, 1.2f) },
                { BodyKinds.FloorLamp, new Vector2(-3.6f, -0.6f) },
                { BodyKinds.OfficeChair, new Vector2(-2.6f, 2.2f) },
                { BodyKinds.RockingChair, new Vector2(3.3f, 0.6f) }, // M5 5B: east of the walks, clear of the table and the exit
            };
            foreach (string kind in BodyKinds.All)
            {
                Game.Def.Decoys.Add(new DecoyDef { Kind = kind, X = spots[kind].x, Z = spots[kind].y, Color = "#8C5A36" });
            }
            Game.Restart();
            yield return Steps(2);
            Assert.AreEqual(BodyKinds.All.Length, Game.Level.Decoys.Count, "premise: the decoys were built");
            Material red = PrimitiveKit.Lit(LevelJson.ParseColor(Game.Def.Player.Color, Color.red));
            for (int i = 0; i < BodyKinds.All.Length; i++)
            {
                string kind = BodyKinds.All[i];
                BodyDef body = BodyDef.For(kind);
                Decoy d = Game.Level.Decoys[i];
                string label = "decoy " + kind;
                Assert.AreEqual(kind, d.Kind, label);
                Assert.AreEqual(body.Size, d.Size, label + ": the decoy size comes from its kind");
                var box = d.GetComponent<BoxCollider>();
                Assert.AreEqual(body.Size, box.size, label + ": its one collider");
                Assert.AreEqual(1, d.GetComponentsInChildren<Collider>(true).Length, label + ": one collider only");
                string model = BodyKinds.DefaultModel(kind);
                Assert.AreEqual(model != null ? 1 : 0, ModelKit.ModelRootsUnder(d.transform).Count, label + ": model " + (model ?? "none"));
                Assert.Greater(d.GetComponentsInChildren<Renderer>(true).Length, 0, label + ": no visual");
                Assert.IsFalse(d.GetComponentsInChildren<Renderer>(true).Any(r => r.sharedMaterials.Contains(red)), label + " is red (PRD 7.2)");
                Assert.LessOrEqual(Probe.TrianglesUnder(d.transform), Tuning.BudgetFurnitureTriangles, label);
                AssertWithinBox(RendererBounds(d.transform, d.transform.position), body.Size, label);
            }
            Assert.AreEqual(6, Game.Level.Decoys[0].GetComponentsInChildren<MeshRenderer>(true).Length, "the chair decoy without a model is the procedural chair");
            CollectionAssert.IsEmpty(Game.Level.ModelFallbacks, "fallbacks");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        // ----- 35a: the armchair prop -----

        [UnityTest]
        public IEnumerator Step35a_ArmchairPropIsCoverWithCollidersUnderItsModel()
        {
            yield return LoadLevel("level1");
            const string name = "TestArmchair";
            var prop = new PropDef
            {
                Name = name, Kind = BodyKinds.Armchair, Model = ModelCatalog.KenneyArmchair, X = -3.2f, Z = 1.0f,
                SizeX = 0.9f, SizeY = 0.95f, SizeZ = 0.85f, Occluder = true, Color = "#4F7CAC",
            };
            Game.Def.Props.Add(prop);
            Game.Restart();
            yield return Steps(2);
            Transform armchair = Game.Level.Root.transform.Find(name);
            Assert.IsNotNull(armchair, "premise: the armchair prop was built");
            List<Transform> roots = ModelKit.ModelRootsUnder(armchair);
            Assert.AreEqual(1, roots.Count, "the Kenney armchair");
            CollectionAssert.IsEmpty(Game.Level.ModelFallbacks, "fallbacks");
            foreach (Renderer r in armchair.GetComponentsInChildren<Renderer>(true))
            {
                Assert.IsNotNull(ModelKit.ModelRootOf(r.transform), $"procedural renderer {r.name} next to the model");
            }
            foreach (string part in new[] { "Base", "Backrest", "ArmL", "ArmR" })
            {
                Transform t = armchair.Find(part);
                Assert.IsNotNull(t, "no collider-only " + part);
                Assert.IsNotNull(t.GetComponent<BoxCollider>(), part + " has no collider");
                Assert.IsNull(t.GetComponent<MeshFilter>(), part + " still has a MeshFilter (CONTRACT_M3 1: collider-only)");
                Assert.AreEqual(Layers.Occluder, t.gameObject.layer, part + " is no occluder");
            }
            Assert.IsNull(armchair.Find("Cushion"), "a visual-only part is not built under a model");
            Assert.Less(armchair.Find("Backrest").localPosition.z, 0f, "the backrest is on -z, where the model's is (yaw offset 180)");
            AssertWithinBox(RendererBounds(armchair, armchair.position), prop.Size, "armchair model");
            Assert.LessOrEqual(Probe.TrianglesUnder(armchair), Tuning.BudgetFurnitureTriangles, "armchair triangles");

            // Cover for a stool (CONTRACT_M4 2.2): from 1.6 m in front, the top of a stool behind the backrest is hidden.
            Vector3 eye = new Vector3(prop.X, Tuning.EyeHeight, 2.8f);
            Vector3 stoolTop = new Vector3(prop.X, BodyDef.For(BodyKinds.Stool).Size.y - Tuning.SampleInset, 0.2f);
            Assert.IsTrue(Physics.Linecast(eye, stoolTop, out RaycastHit hit, 1 << Layers.Occluder, QueryTriggerInteraction.Ignore),
                "the armchair does not hide a stool behind it");
            Assert.IsTrue(hit.collider.transform.IsChildOf(armchair), "hidden by " + hit.collider.name + ", not by the armchair");
            Vector3 chairTopFar = new Vector3(prop.X, BodyDef.For(BodyKinds.Chair).Size.y - Tuning.SampleInset, 2.2f);
            Assert.IsFalse(Physics.Linecast(eye, chairTopFar, 1 << Layers.Occluder, QueryTriggerInteraction.Ignore),
                "control: a point in front of the armchair is hidden too, so the line test hits something else");

            // Identical colliders without the model (CONTRACT_M3 1), and the procedural armchair has its cushion.
            List<(string key, Bounds bounds)> withModel = Colliders(armchair);
            Assert.AreEqual(4, withModel.Count, "premise: four colliders: " + string.Join(" | ", withModel.Select(c => c.key)));
            ModelKit.Disabled = true;
            try
            {
                Game.Restart();
                yield return Steps(2);
                armchair = Game.Level.Root.transform.Find(name);
                Assert.AreEqual(0, ModelKit.ModelRootsUnder(armchair).Count, "ModelKit.Disabled still built a model");
                AssertSameColliders(withModel, Colliders(armchair), "the armchair without its model");
                Assert.AreEqual(5, armchair.GetComponentsInChildren<MeshRenderer>(true).Length, "the procedural armchair: 5 boxes");
                Assert.IsNotNull(armchair.Find("Cushion"));
                AssertWithinBox(RendererBounds(armchair, armchair.position), prop.Size, "procedural armchair");
            }
            finally
            {
                ModelKit.Disabled = false;
            }
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        // ----- 35a: facing of the new seat models -----

        [UnityTest]
        public IEnumerator Step35a_SeatModelsFaceLikeTheirProceduralVisuals()
        {
            // The armchair model's back is on the side of the procedural armchair's backrest (like the M3 seats).
            BodyDef armchair = BodyDef.For(BodyKinds.Armchair);
            Transform reference = Scratch("Procedural armchair");
            Assert.IsTrue(FurnitureKit.Body(BodyKinds.Armchair, reference, armchair.Size, Color.gray, 0));
            Transform backrest = reference.Find("Backrest");
            Assert.IsNotNull(backrest, "no procedural backrest");
            Transform frame = Scratch("Facing armchair");
            GameObject model = ModelKit.Instantiate(ModelCatalog.KenneyArmchair, frame, armchair.Size, ModelFit.Box);
            Assert.IsNotNull(model, "kenney.armchair does not instantiate");
            float tallest = TallestSide(model.transform, frame, out float depth);
            Assert.That(Mathf.Abs(tallest), Is.GreaterThan(0.1f * depth), $"control: the armchair has a back, the measure sees no side ({tallest:0.###} m)");
            Assert.AreEqual(Mathf.Sign(backrest.localPosition.z), Mathf.Sign(tallest),
                $"the armchair model's back is on z {tallest:0.###}, the procedural backrest on z {backrest.localPosition.z:0.###}");

            // The bar stool and the round floor lamp have no back: their top is centred, any quarter turn fits.
            foreach ((string id, string kind) in new[] { (ModelCatalog.KenneyStool, BodyKinds.Stool), (ModelCatalog.KenneyFloorLamp, BodyKinds.FloorLamp) })
            {
                Transform f = Scratch("Facing " + id);
                GameObject m = ModelKit.Instantiate(id, f, BodyDef.For(kind).Size, ModelFit.Box);
                Assert.IsNotNull(m, id + " does not instantiate");
                float side = TallestSide(m.transform, f, out float d);
                Assert.That(Mathf.Abs(side), Is.LessThan(0.1f * d), $"{id}: the top is off centre ({side:0.###} m of {d:0.###}): it has a facing, set its yaw offset");
                Assert.AreEqual(0f, ModelCatalog.Lookup(id).yawOffset, id + ": yaw offset");
            }
            Assert.AreEqual(180f, ModelCatalog.Lookup(ModelCatalog.KenneyArmchair).yawOffset, "armchair yaw offset");
            yield return null;
            CollectionAssert.IsEmpty(errors, "no error logged");
        }
    }
}
