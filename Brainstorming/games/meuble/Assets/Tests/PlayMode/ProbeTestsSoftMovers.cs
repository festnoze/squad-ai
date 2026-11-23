using System;
using System.Collections;
using System.Collections.Generic;
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
    /// Soft movers (product owner request, 2026-11-20), on the real Boot scene: the furniture bodies are rounded
    /// (<see cref="SoftBodies"/>) and nothing else changes. Each Kenney body model swaps its meshes for its rounded design
    /// and keeps its renderers, its slots, its paint (the player's red on the same material), its box and its pivot, within
    /// PRD 7.4's 400 triangles, its detail in metres; every procedural body stays within its box and budget with metric UVs;
    /// the memory ghost and the seat ghost draw the rounded chair. Every step asserts its premise.
    /// </summary>
    public sealed class ProbeTestsSoftMovers
    {
        private static readonly Color Red = new Color32(0xD7, 0x26, 0x3D, 0xFF);

        private static readonly (string id, string kind)[] BodyModels =
        {
            (ModelCatalog.KenneyChair, BodyKinds.Chair), (ModelCatalog.KenneyStool, BodyKinds.Stool),
            (ModelCatalog.KenneyArmchair, BodyKinds.Armchair), (ModelCatalog.KenneyFloorLamp, BodyKinds.FloorLamp),
        };

        /// <summary>GhostView's ring: 48 segments, two triangles each.</summary>
        private const int RingTriangles = 96;

        private Main main;
        private GameState Game => main.Game;
        private readonly List<string> errors = new List<string>();
        private readonly List<Object> scratch = new List<Object>();

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            ModelKit.Disabled = false;
            SoftBodies.RoundModels = true;
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
            yield return null;
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            ModelKit.Disabled = false;
            SoftBodies.RoundModels = true;
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

        private Transform Scratch(string name)
        {
            var go = new GameObject(name);
            scratch.Add(go);
            return go.transform;
        }

        private static Bounds BoundsUnder(Transform root)
        {
            Renderer[] renderers = root.GetComponentsInChildren<Renderer>(true);
            Assert.Greater(renderers.Length, 0, root.name + ": premise: no renderer");
            Bounds b = renderers[0].bounds;
            foreach (Renderer r in renderers)
            {
                b.Encapsulate(r.bounds);
            }
            return b;
        }

        [UnityTest]
        public IEnumerator SoftMovers_BodyModelsKeepTheirBoxSlotsAndPaint()
        {
            foreach ((string id, string kind) in BodyModels)
            {
                Vector3 size = BodyDef.For(kind).Size;
                var paint = new ModelPaint { Main = Red, Red = Red };
                SoftBodies.RoundModels = false;
                Transform hardParent = Scratch("Hard " + id);
                GameObject hard = ModelKit.Instantiate(id, hardParent, size, ModelFit.Box, paint);
                SoftBodies.RoundModels = true;
                Transform softParent = Scratch("Soft " + id);
                GameObject soft = ModelKit.Instantiate(id, softParent, size, ModelFit.Box, paint);
                Assert.IsNotNull(hard, id + ": premise: the hard model instantiates");
                Assert.IsNotNull(soft, id + ": the soft model does not instantiate");

                Renderer[] h = hard.GetComponentsInChildren<Renderer>(true);
                Renderer[] s = soft.GetComponentsInChildren<Renderer>(true);
                Assert.AreEqual(h.Length, s.Length, id + ": the renderers changed");
                Assert.IsTrue(h.All(r => !ModelKit.MeshOf(r).name.StartsWith("Soft", StringComparison.Ordinal)), id + ": premise: the hard model draws its GLB meshes");
                for (int i = 0; i < s.Length; i++)
                {
                    Assert.AreEqual(h[i].name, s[i].name, $"{id}: renderer {i}");
                    // The same materials slot by slot: the same paint, the player's red still on the main material.
                    CollectionAssert.AreEqual(h[i].sharedMaterials, s[i].sharedMaterials, $"{id} {s[i].name}: its slots' materials changed");
                    Mesh mesh = ModelKit.MeshOf(s[i]);
                    StringAssert.StartsWith("Soft", mesh.name, $"{id} {s[i].name}: not the rounded design");
                    Assert.IsTrue(mesh.isReadable, $"{id} {s[i].name}: the ghost and the load read the mesh");
                    Assert.AreEqual(s[i].sharedMaterials.Length, mesh.subMeshCount, $"{id} {s[i].name}: one submesh per slot");
                    for (int sub = 0; sub < mesh.subMeshCount; sub++)
                    {
                        Assert.Greater(mesh.GetIndexCount(sub), 0, $"{id} {s[i].name}: slot {sub} draws nothing");
                        // UVs in metres in the world, whatever the box fit's per axis scale: the detail is never stretched.
                        Assert.AreEqual(1f, PrimitiveKit.MetresPerUv(s[i], sub), 0.03f, $"{id} {s[i].name}: slot {sub}'s UVs are not in metres");
                    }
                }
                Assert.IsTrue(s.Any(r => r.sharedMaterials.Contains(PrimitiveKit.PlayerMaterial(Red))), id + ": nothing shows the player's red");

                // The box and the pivot: the same bounds as the hard model (the box fit fills the body's box).
                Bounds hb = BoundsUnder(hard.transform);
                Bounds sb = BoundsUnder(soft.transform);
                Vector3 hardCentre = hb.center - hardParent.position;
                Vector3 softCentre = sb.center - softParent.position;
                Assert.Less((hb.size - sb.size).magnitude, 0.012f, $"{id}: its bounds went from {hb.size:F3} to {sb.size:F3}");
                Assert.Less((hardCentre - softCentre).magnitude, 0.01f, $"{id}: its centre went from {hardCentre:F3} to {softCentre:F3}");
                Assert.AreEqual(0f, sb.min.y - softParent.position.y, 0.005f, id + ": it no longer stands on the floor");

                long triangles = Probe.TrianglesUnder(soft.transform);
                Assert.AreEqual(SoftBodies.Triangles(SoftBodies.ModelDesign(id, size)), triangles, id + ": the design is not drawn once");
                Assert.LessOrEqual(triangles, Tuning.BudgetFurnitureTriangles, id + ": PRD 7.4 furniture triangles");
                Debug.Log($"[SoftMovers] {id}: {Probe.TrianglesUnder(hard.transform)} -> {triangles} triangles, {s.Length} renderers, bounds {sb.size:F3}");
            }
            yield return null;
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        [UnityTest]
        public IEnumerator SoftMovers_ProceduralBodiesStayInTheirBoxWithMetricUvs()
        {
            foreach (string kind in BodyKinds.All)
            {
                Vector3 size = BodyDef.For(kind).Size;
                Transform holder = Scratch("Procedural " + kind);
                Assert.IsTrue(FurnitureKit.Body(kind, holder, size, Red, Layers.Player), kind + ": premise: a procedural body");
                long triangles = Probe.TrianglesUnder(holder);
                Assert.LessOrEqual(triangles, Tuning.BudgetFurnitureTriangles, kind + ": PRD 7.4 furniture triangles");
                Bounds b = BoundsUnder(holder);
                Assert.AreEqual(0f, b.min.y, 0.005f, kind + ": it does not stand on the floor");
                Assert.LessOrEqual(b.max.y, size.y + 0.005f, kind + ": taller than its box");
                Assert.Greater(b.max.y, size.y * 0.95f, kind + ": it does not reach its height");
                Assert.LessOrEqual(Mathf.Max(-b.min.x, b.max.x), size.x * 0.5f + 0.005f, kind + ": wider than its box");
                Assert.LessOrEqual(Mathf.Max(-b.min.z, b.max.z), size.z * 0.5f + 0.005f, kind + ": deeper than its box");
                foreach (MeshRenderer r in holder.GetComponentsInChildren<MeshRenderer>(true))
                {
                    // The office chair's frame carries its unit ball casters, measured as before; every other part is metric.
                    if (r.name == "Frame")
                    {
                        continue;
                    }
                    Assert.AreEqual(1f, PrimitiveKit.MetresPerUv(r, 0), 0.03f, $"{kind} {r.name}: its UVs are not in metres");
                }
                Debug.Log($"[SoftMovers] procedural {kind}: {triangles} triangles, {holder.GetComponentsInChildren<MeshRenderer>(true).Length} renderers, bounds {b.size:F3}");
            }
            yield return null;
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        [UnityTest]
        public IEnumerator SoftMovers_GhostsDrawTheRoundedChair()
        {
            Game.LoadLevel("level1");
            yield return null;
            FurnitureController furniture = Game.Furniture;
            Assert.AreEqual(BodyKinds.Chair, furniture.Kind, "premise: level 1's player is the chair");
            Assert.AreEqual(1, ModelKit.ModelRootsUnder(furniture.Visual).Count, "premise: it shows the Kenney chair");
            Assert.IsTrue(furniture.Visual.GetComponentsInChildren<MeshFilter>(true).All(f => f.sharedMesh.name.StartsWith("Soft", StringComparison.Ordinal)),
                "the player's chair is not the rounded one");
            long body = Probe.TrianglesUnder(furniture.Visual);

            // The memory ghost copies the furniture's own meshes: the rounded chair and its ring.
            GhostView ghost = Game.Ghost;
            ghost.Show(furniture.Pose, furniture.Size, furniture.Visual, 0.3f);
            Assert.IsTrue(ghost.Visible, "premise: the ghost shows");
            Assert.AreEqual(body + RingTriangles, ModelKit.Triangles(ghost.GetComponent<MeshFilter>().sharedMesh), "the memory ghost is not the rounded chair");
            Bounds visual = LoadView.BoundsOf(furniture.Visual);
            Bounds drawn = ghost.GetComponent<MeshRenderer>().bounds;
            Assert.AreEqual(visual.size.y, drawn.size.y, 0.03f, "the ghost's height is not the chair's");
            ghost.Hide();

            // The seat ghost (no furniture to copy) draws the rounded procedural chair.
            ghost.ShowSeat(furniture.Pose, furniture.Size);
            Transform seat = ghost.transform.parent.Find("SeatGhost");
            Assert.IsNotNull(seat, "premise: the seat ghost exists");
            Assert.AreEqual(SoftBodies.Triangles(SoftBodies.Chair(furniture.Size)) + RingTriangles, ModelKit.Triangles(seat.GetComponent<MeshFilter>().sharedMesh),
                "the seat ghost is not the rounded chair");
            ghost.ShowSeat(null);
            yield return null;
            CollectionAssert.IsEmpty(errors, "no error logged");
        }
    }
}
