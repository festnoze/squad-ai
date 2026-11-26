using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M8 room objects (docs/m8/ROOMS_PLAN.md 3) on the real Boot scene, with the throwaway level test_rooms (every M8 kind,
    /// four of them with their Kenney model): each builds as a static prop (colliders on the Occluder layer inside its box
    /// when it is an occluder, none and layer 0 when it is not), within the furniture triangle budget, adding no material but
    /// the white ceramic; the bed has exactly the colliders of a sofa of its size, its headboard on the sofa's backrest side.
    /// </summary>
    public sealed class ProbeTestsM8Props
    {
        private const string Level = "test_rooms";

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
            Game.LoadLevel(Level);
            Assert.AreEqual(Level, Game.LevelId);
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

        private Transform Scratch(string name)
        {
            var go = new GameObject(name);
            scratch.Add(go);
            return go.transform;
        }

        private List<PropDef> RoomObjects() => Game.Def.Props.Where(p => Array.IndexOf(PropKinds.RoomObjects, p.Kind) >= 0).ToList();

        private Transform PropRoot(PropDef p)
        {
            Transform t = Game.Level.Root.transform.Find(p.Name);
            Assert.IsNotNull(t, $"no prop {p.Name} under the level root");
            return t;
        }

        [UnityTest]
        public IEnumerator Step80a_RoomObjectsBuildAsStaticPropsWithTheirOccluderFlag()
        {
            CollectionAssert.AreEquivalent(PropKinds.RoomObjects, RoomObjects().Select(p => p.Kind).Distinct(), "premise: test_rooms has every M8 kind");
            Assert.IsEmpty(LevelValidator.Validate(Game.Def), "test_rooms validates");
            CollectionAssert.IsEmpty(Game.Level.ModelFallbacks, "every named model instantiates");
            foreach (bool models in new[] { true, false })
            {
                ModelKit.Disabled = !models;
                Game.Restart();
                yield return Steps(2);
                string pass = models ? "with models" : "procedural";
                foreach (PropDef p in RoomObjects())
                {
                    string label = $"{pass}: {p.Kind} {p.Name}";
                    Transform t = PropRoot(p);
                    Assert.AreEqual(Layers.Occluder, t.gameObject.layer, label + ": an occluder prop is on the Occluder layer");
                    Collider[] colliders = t.GetComponentsInChildren<Collider>(true);
                    Assert.Greater(colliders.Length, 0, label + ": no collider");
                    var box = new Bounds(t.position + Vector3.up * (p.SizeY * 0.5f), p.Size + Vector3.one * 2e-3f);
                    foreach (Collider c in colliders)
                    {
                        Assert.IsInstanceOf<BoxCollider>(c, label);
                        Assert.IsFalse(c.isTrigger, label + ": a trigger");
                        Assert.IsTrue(c.enabled && c.gameObject.activeInHierarchy, label + ": a disabled collider");
                        Assert.AreEqual(Layers.Occluder, c.gameObject.layer, $"{label}: collider {c.name} is on layer {c.gameObject.layer}");
                        Assert.IsTrue(box.Contains(c.bounds.min) && box.Contains(c.bounds.max), $"{label}: collider {c.name} {c.bounds} leaves the box {box}");
                    }
                    Assert.IsNull(t.GetComponentInChildren<Rigidbody>(true), label + ": a static prop has no rigidbody");
                    Assert.IsNull(t.GetComponentInChildren<Decoy>(true), label + ": never player furniture");
                    long triangles = Probe.TrianglesUnder(t);
                    Assert.Greater(triangles, 0, label + ": nothing drawn");
                    Assert.LessOrEqual(triangles, Tuning.BudgetFurnitureTriangles, $"{label}: {triangles} triangles");
                    // A procedural room object is one renderer per material; a Kenney model keeps its own slots (its nodes
                    // come twice in the GLB, as every Kenney model of M3).
                    int slots = ModelKit.SlotsUnder(t);
                    bool model = models && !string.IsNullOrEmpty(p.Model);
                    Assert.AreEqual(model ? 1 : 0, ModelKit.ModelRootsUnder(t).Count, label + ": model roots");
                    Assert.LessOrEqual(slots, model ? 10 : 4, $"{label}: {slots} draw calls");
                    foreach (Renderer r in t.GetComponentsInChildren<Renderer>(true))
                    {
                        Assert.AreEqual(Layers.Occluder, r.gameObject.layer, $"{label}: renderer {r.name} is not on the prop's layer");
                    }
                    Debug.Log($"[Step80a] {label}: {triangles} triangles, {slots} draw calls, {colliders.Length} colliders, "
                        + $"materials {string.Join(", ", t.GetComponentsInChildren<Renderer>(true).SelectMany(r => r.sharedMaterials).Select(m => m.name).Distinct())}");
                }
                // Never a hiding spot: only wardrobes are (test_rooms has none).
                Assert.AreEqual(0, Game.Level.Wardrobes.Count, $"{pass}: a room object was built as a wardrobe");
            }
            ModelKit.Disabled = false;

            // Not an occluder: layer 0 and no collider at all (the M2 rule), the visual still drawn.
            foreach (PropDef p in RoomObjects())
            {
                p.Occluder = false;
            }
            try
            {
                Game.Restart();
                yield return Steps(2);
                foreach (PropDef p in RoomObjects())
                {
                    Transform t = PropRoot(p);
                    Assert.AreEqual(0, t.gameObject.layer, $"{p.Name}: a prop that is no occluder is on the Default layer");
                    Assert.AreEqual(0, t.GetComponentsInChildren<Collider>(true).Length, $"{p.Name}: a prop that is no occluder has no collider");
                    Assert.Greater(Probe.TrianglesUnder(t), 0, $"{p.Name}: still drawn");
                }
            }
            finally
            {
                foreach (PropDef p in RoomObjects())
                {
                    p.Occluder = true;
                }
            }
            Game.Restart();
            yield return Steps(2);
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>The colliders under <paramref name="root"/> as (name, layer, bounds in its frame), sorted.</summary>
        private static List<string> LocalColliders(Transform root)
        {
            var set = new List<string>();
            foreach (BoxCollider c in root.GetComponentsInChildren<BoxCollider>(true))
            {
                Vector3 center = root.InverseTransformPoint(c.transform.TransformPoint(c.center));
                Vector3 size = Vector3.Scale(c.size, c.transform.lossyScale);
                set.Add(string.Format(CultureInfo.InvariantCulture, "{0} L{1} c({2:0.0000},{3:0.0000},{4:0.0000}) s({5:0.0000},{6:0.0000},{7:0.0000})",
                    c.name, c.gameObject.layer, center.x, center.y, center.z, size.x, size.y, size.z));
            }
            set.Sort(StringComparer.Ordinal);
            return set;
        }

        [UnityTest]
        public IEnumerator Step80b_TheBedHasExactlyTheSofaColliders()
        {
            foreach (Vector3 size in new[] { new Vector3(1.6f, 0.55f, 2.0f), new Vector3(0.8f, 0.5f, 1.6f), new Vector3(1.6f, 0.55f, 1.4f) })
            {
                foreach (bool visual in new[] { true, false })
                {
                    Transform sofa = Scratch("Sofa");
                    Transform bed = Scratch("Bed");
                    sofa.gameObject.layer = bed.gameObject.layer = Layers.Occluder;
                    FurnitureKit.Build(new PropDef { Name = "Lit", Kind = PropKinds.Sofa, SizeX = size.x, SizeY = size.y, SizeZ = size.z }, sofa, Layers.Occluder, visual, true);
                    FurnitureKit.Build(new PropDef { Name = "Lit", Kind = PropKinds.Bed, SizeX = size.x, SizeY = size.y, SizeZ = size.z }, bed, Layers.Occluder, visual, true);
                    List<string> want = LocalColliders(sofa);
                    Assert.Greater(want.Count, 0, "premise: the sofa has colliders");
                    CollectionAssert.AreEqual(want, LocalColliders(bed), $"{size} visual {visual}: the bed's colliders are not the sofa's");
                }
            }

            // The headboard on the sofa's backrest side (+z), procedural and the Kenney bed: the mean z of the top 15 % of the
            // vertices, as step 22 checks the seats.
            PropDef lit = Game.Def.Props.First(p => p.Kind == PropKinds.Bed);
            Assert.AreEqual(ModelCatalog.KenneyBed, lit.Model, "premise: test_rooms names the Kenney bed");
            foreach (bool models in new[] { true, false })
            {
                ModelKit.Disabled = !models;
                Game.Restart();
                yield return Steps(1);
                Transform t = PropRoot(lit);
                Assert.AreEqual(models ? 1 : 0, ModelKit.ModelRootsUnder(t).Count, "premise: the model is there or not");
                var points = new List<Vector3>();
                foreach (MeshFilter f in t.GetComponentsInChildren<MeshFilter>(true))
                {
                    Assert.IsTrue(f.sharedMesh.isReadable, f.name + ": mesh not readable");
                    points.AddRange(f.sharedMesh.vertices.Select(v => t.InverseTransformPoint(f.transform.TransformPoint(v))));
                }
                float top = points.Max(p => p.y);
                float bottom = points.Min(p => p.y);
                float side = points.Where(p => p.y >= top - 0.15f * (top - bottom)).Average(p => p.z);
                Assert.Greater(side, 0.1f * lit.SizeZ, $"{(models ? "the Kenney bed" : "the procedural bed")}: its headboard is not on +z ({side:0.###})");
            }
            ModelKit.Disabled = false;
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        [UnityTest]
        public IEnumerator Step80c_RoomObjectsAddNoMaterialButTheCeramic()
        {
            // What a level already draws: the surfaces' shared images and the household's near-black.
            var shared = new HashSet<Material>
            {
                PrimitiveKit.SurfaceMaterial(Surface.Wood), PrimitiveKit.SurfaceMaterial(Surface.Plaster), PrimitiveKit.SurfaceMaterial(Surface.Linen),
                PrimitiveKit.SurfaceMaterial(Surface.Upholstery), PrimitiveKit.SurfaceMaterial(Surface.Metal), FurnitureKit.DarkMaterial,
            };
            Assert.IsFalse(shared.Contains(null), "premise: the texture library has every surface's image");
            foreach (bool models in new[] { true, false })
            {
                ModelKit.Disabled = !models;
                Game.Restart();
                yield return Steps(1);
                var added = new HashSet<Material>();
                foreach (PropDef p in RoomObjects())
                {
                    foreach (Renderer r in PropRoot(p).GetComponentsInChildren<Renderer>(true))
                    {
                        foreach (Material m in r.sharedMaterials)
                        {
                            Assert.IsNotNull(m, $"{p.Name}: an empty slot");
                            Color? palette = PrimitiveKit.PaletteOf(m);
                            Assert.IsFalse(palette.HasValue && ModelMath.IsRed(palette.Value), $"{p.Name}: {r.name} is red (PRD 7.2)");
                            if (!shared.Contains(m))
                            {
                                added.Add(m);
                            }
                        }
                    }
                }
                CollectionAssert.AreEquivalent(new[] { FurnitureKit.CeramicMaterial }, added,
                    $"{(models ? "with models" : "procedural")}: the room objects add {string.Join(", ", added.Select(m => m.name))}");
            }
            ModelKit.Disabled = false;
            CollectionAssert.IsEmpty(errors, "no error logged");
        }
    }
}
