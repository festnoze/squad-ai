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
    /// The M3 models probe (docs/CONTRACT_M3.md 9, steps 22, 23 and 25) on the real Boot scene. Every step first
    /// asserts its premise (model renderers and a skinned mesh exist), so a ModelKit that returns null cannot pass.
    /// </summary>
    public sealed class ProbeTestsM3Models
    {
        private static readonly string[] Levels = { "level1", "level2", "level3" };

        /// <summary>M3.1 N4: the model's eyes within this of Tuning.EyeHeight (the rig's own test uses the same).</summary>
        private const float EyeTolerance = 0.03f;

        /// <summary>The seats of CONTRACT_M3 3 and the side of their procedural backrest (-z chair, +z sofa).</summary>
        private static readonly (string id, float backrestSide)[] Seats =
        {
            (ModelCatalog.KenneyChair, -1f), (ModelCatalog.KenneyArmchair, -1f), (ModelCatalog.KenneySofa, 1f),
        };

        private Main main;
        private GameState Game => main.Game;
        private readonly List<string> errors = new List<string>();
        /// <summary>The warnings of ModelKit (one per failed instantiate).</summary>
        private readonly List<string> warnings = new List<string>();
        private readonly List<Object> scratch = new List<Object>();

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            ModelKit.Disabled = false;
            errors.Clear();
            warnings.Clear();
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
            else if (type == LogType.Warning && condition.StartsWith("[ModelKit]", StringComparison.Ordinal))
            {
                // Only ModelKit's own warnings: a NavMesh rebuild or another agent may warn for its own reasons.
                warnings.Add(condition);
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

        /// <summary>The premise of every M3 models step: model renderers exist in the level, and a skinned mesh.</summary>
        private void AssertModelsPresent(string label)
        {
            Assert.Greater(Game.Level.ModelVisuals.Count, 0, $"{label}: premise: the level has no model visual (a null ModelKit would pass)");
            int meshes = 0;
            int skinned = 0;
            foreach (GameObject m in Game.Level.ModelVisuals)
            {
                Assert.IsNotNull(m, label + ": a model visual was destroyed");
                meshes += m.GetComponentsInChildren<MeshRenderer>(true).Length;
                skinned += m.GetComponentsInChildren<SkinnedMeshRenderer>(true).Length;
            }
            Assert.Greater(meshes, 0, label + ": premise: no model MeshRenderer");
            Assert.Greater(skinned, 0, label + ": premise: no model SkinnedMeshRenderer (the inhabitant)");
        }

        private Transform Child(string name)
        {
            Transform t = Game.Level.Root.transform.Find(name);
            Assert.IsNotNull(t, $"no '{name}' under the level root");
            return t;
        }

        /// <summary>
        /// One element whose data names a model: exactly one model root under it, every renderer and mesh filter
        /// under it belongs to that model (the procedural parts are collider-only), and the model has the layer of
        /// its parent on every child.
        /// </summary>
        private static Transform AssertModelElement(Transform element, string label)
        {
            List<Transform> roots = ModelKit.ModelRootsUnder(element);
            Assert.AreEqual(1, roots.Count, $"{label}: {roots.Count} model roots");
            Transform model = roots[0];
            Assert.Greater(model.GetComponentsInChildren<Renderer>(true).Length, 0, label + ": the model has no renderer");
            foreach (Renderer r in element.GetComponentsInChildren<Renderer>(true))
            {
                Assert.IsNotNull(ModelKit.ModelRootOf(r.transform), $"{label}: procedural renderer {r.name} left next to the model");
            }
            foreach (MeshFilter f in element.GetComponentsInChildren<MeshFilter>(true))
            {
                Assert.IsNotNull(ModelKit.ModelRootOf(f.transform), $"{label}: procedural MeshFilter {f.name} left next to the model");
            }
            int layer = model.parent.gameObject.layer;
            foreach (Transform t in model.GetComponentsInChildren<Transform>(true))
            {
                Assert.AreEqual(layer, t.gameObject.layer, $"{label}: {t.name} is on layer {t.gameObject.layer}, its parent on {layer}");
            }
            foreach (Renderer r in model.GetComponentsInChildren<Renderer>(true))
            {
                foreach (Material m in r.sharedMaterials)
                {
                    Assert.IsNotNull(m, $"{label}: {r.name} has an empty slot");
                    Assert.IsTrue(m.shader.name.StartsWith(Probe.UrpShaderPrefix, StringComparison.Ordinal),
                        $"{label}: {r.name} renders with {m.shader.name}, not a PrimitiveKit material");
                }
            }
            return model;
        }

        /// <summary>
        /// The side (sign of z in <paramref name="frame"/>) of the tallest part of a model: the mean z of every
        /// vertex in the top 15 % of its height. The magnitude is returned too, so a flat answer is caught.
        /// </summary>
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
            float minZ = points.Min(p => p.z);
            float maxZ = points.Max(p => p.z);
            depth = maxZ - minZ;
            float cut = maxY - 0.15f * (maxY - minY);
            return points.Where(p => p.y >= cut).Average(p => p.z);
        }

        private static void AssertSameSide(float tallest, float depth, float backrest, string label)
        {
            Assert.That(Mathf.Abs(tallest), Is.GreaterThan(0.1f * depth), $"{label}: the tallest part sits in the middle ({tallest:0.###} m), facing undecided");
            Assert.AreNotEqual(0f, backrest, label + ": no procedural backrest side");
            Assert.AreEqual(Mathf.Sign(backrest), Mathf.Sign(tallest),
                $"{label}: the model's tallest part is on z {tallest:0.###}, the procedural backrest on z {backrest:0.###}: the model faces the wrong way");
        }

        // ----- 22 -----

        [UnityTest]
        public IEnumerator Step22_ModelsReplaceTheProceduralVisuals()
        {
            // The catalog resolves every id, with right angle yaw offsets, and each instantiates.
            ModelCatalog catalog = ModelCatalog.Load();
            Assert.IsNotNull(catalog, "Resources/ModelCatalog is missing");
            foreach (string id in ModelCatalog.Ids)
            {
                ModelCatalog.Entry e = catalog.Find(id);
                Assert.IsNotNull(e, "the catalog does not resolve " + id);
                Assert.IsNotNull(e.prefab, id + ": no prefab");
                Assert.IsTrue(ModelMath.IsValidSize(e.nativeSize), $"{id}: native size {e.nativeSize}");
                Assert.IsTrue(ModelMath.IsRightAngle(e.yawOffset), $"{id}: yaw offset {e.yawOffset} is not a multiple of 90");
                // M5 (CONTRACT_M5_v3 15.5): every Quaternius model is a rigged character, a human or a pet (the dog); the
                // human checks (the "_Idle" clip, the eyes at Tuning.EyeHeight) apply to humans, a pet's eyes stand at its
                // own target and its Idle is named by its clip map.
                bool character = id.StartsWith("quaternius.", StringComparison.Ordinal);
                bool human = character && e.kind == ModelCatalog.KindHuman;
                Assert.AreEqual(character, e.rigged, id + ": rigged");
                Assert.AreEqual(character, e.IsHuman || e.IsPet, id + ": a character is a human or a pet, a static model neither");
                if (character)
                {
                    Assert.IsFalse(string.IsNullOrEmpty(e.headBone), id + ": no head bone");
                    Assert.Greater(e.eyeHeight, 0f, id + ": eye height");
                }
                Transform parent = Scratch("Catalog " + id);
                GameObject model = ModelKit.Instantiate(id, parent, new Vector3(0.6f, 0.9f, 0.5f), character ? ModelFit.Uniform : ModelFit.Box);
                Assert.IsNotNull(model, id + " does not instantiate");
                if (character)
                {
                    Transform head = model.GetComponentsInChildren<Transform>(true).FirstOrDefault(t => t.name == e.headBone);
                    Assert.IsNotNull(head, $"{id}: head bone '{e.headBone}' missing in the instance");
                    Assert.IsNotNull(model.GetComponentInChildren<SkinnedMeshRenderer>(true), id + ": no skinned mesh");
                    // M3.1 N4: in the Idle clip, with the head held in its bind orientation as InhabitantRig holds it,
                    // the eyes of the fitted model stand at the routine's eye.
                    Animation anim = model.GetComponent<Animation>();
                    Assert.IsNotNull(anim, id + ": no Animation on the model root");
                    AnimationClip idle = null;
                    foreach (AnimationState state in anim)
                    {
                        if (human ? state.name.EndsWith("_Idle", StringComparison.Ordinal) : state.name == e.idleClip)
                        {
                            idle = state.clip;
                        }
                    }
                    Assert.IsNotNull(idle, id + ": no Idle clip");
                    Assert.IsTrue(ModelKit.TryBindRotation(model.GetComponentInChildren<SkinnedMeshRenderer>(true), head, out _), id + ": head not in the bind poses");
                    float eyeY = ModelKit.IdleEyeHeight(model, idle, head, e.eyeLocal, parent, 24);
                    float wantEye = human ? Tuning.EyeHeight : e.TargetEye;
                    Assert.That(eyeY, Is.EqualTo(wantEye).Within(EyeTolerance), $"{id}: the eyes stand at {eyeY:0.###} m, the routine's eye at {wantEye}");
                }
                else
                {
                    var bounds = new Bounds();
                    bool any = false;
                    foreach (Renderer r in model.GetComponentsInChildren<Renderer>(true))
                    {
                        if (!any)
                        {
                            bounds = r.bounds;
                            any = true;
                        }
                        else
                        {
                            bounds.Encapsulate(r.bounds);
                        }
                    }
                    Assert.IsTrue(any, id + ": no renderer");
                    Assert.That((bounds.size - new Vector3(0.6f, 0.9f, 0.5f)).magnitude, Is.LessThan(0.01f), $"{id}: box fit gives {bounds.size:F3}");
                    Assert.That(bounds.min.y, Is.EqualTo(0f).Within(0.005f), $"{id}: bottom at {bounds.min.y:0.###}");
                    Assert.That(new Vector2(bounds.center.x, bounds.center.z).magnitude, Is.LessThan(0.005f), $"{id}: centre {bounds.center:F3}");
                }
            }
            // A rigged model is never box fitted (one warning, no model).
            int before = warnings.Count;
            Assert.IsNull(ModelKit.Instantiate(ModelCatalog.QuaterniusMan, Scratch("Sheared"), Vector3.one, ModelFit.Box), "a rigged model accepted a box fit");
            Assert.AreEqual(before + 1, warnings.Count, "one warning for a refused box fit");

            // Levels 1 to 3: every element that names a model shows it, and only it.
            foreach (string level in Levels)
            {
                yield return LoadLevel(level);
                AssertModelsPresent(level);
                CollectionAssert.IsEmpty(Game.Level.ModelFallbacks, level + ": fallbacks");
                LevelDef def = Game.Def;
                Color playerColor = LevelJson.ParseColor(def.Player.Color, Color.red);
                int checkedElements = 0;
                if (!string.IsNullOrEmpty(def.Player.Model))
                {
                    Transform model = AssertModelElement(Game.Furniture.transform, level + " player");
                    // M6 (CONTRACT_M6 2.4): the player's own furniture is lacquered (PrimitiveKit.LitSurface), not a plain Lit material.
                    Material red = PrimitiveKit.LitSurface(playerColor, Surface.Lacquer);
                    Assert.IsTrue(model.GetComponentsInChildren<Renderer>(true).Any(r => r.sharedMaterials.Contains(red)),
                        level + ": the player model is not in the player colour");
                    foreach (Renderer r in Object.FindObjectsByType<Renderer>(FindObjectsSortMode.None))
                    {
                        if (!r.transform.IsChildOf(Game.Furniture.transform))
                        {
                            Assert.IsFalse(r.sharedMaterials.Contains(red), $"{level}: {r.name} is red too (PRD 7.2: only the player furniture is)");
                        }
                    }
                    checkedElements++;
                }
                foreach (PropDef p in def.Props.Where(p => !string.IsNullOrEmpty(p.Model)))
                {
                    AssertModelElement(Child(p.Name), $"{level} prop {p.Name}");
                    checkedElements++;
                }
                for (int i = 0; i < def.Decoys.Count; i++)
                {
                    if (!string.IsNullOrEmpty(def.Decoys[i].Model))
                    {
                        AssertModelElement(Game.Level.Decoys[i].transform, $"{level} decoy {i + 1}");
                        checkedElements++;
                    }
                }
                for (int i = 0; i < def.Rugs.Count; i++)
                {
                    if (!string.IsNullOrEmpty(def.Rugs[i].Model))
                    {
                        AssertModelElement(Child("Rug " + (i + 1)), $"{level} rug {i + 1}");
                        checkedElements++;
                    }
                }
                if (!string.IsNullOrEmpty(def.Exit.Model))
                {
                    AssertModelElement(Child("Doormat"), level + " doormat");
                    checkedElements++;
                }
                for (int i = 0; i < def.Inhabitants.Count; i++)
                {
                    if (!string.IsNullOrEmpty(def.Inhabitants[i].Model))
                    {
                        Inhabitant h = Game.Level.Inhabitants[i];
                        Assert.AreEqual(1, ModelKit.ModelRootsUnder(h.transform).Count, $"{level} inhabitant {h.name}: no model");
                        Assert.IsNotNull(h.GetComponentInChildren<SkinnedMeshRenderer>(true), $"{level} inhabitant {h.name}: no skinned mesh");
                        Assert.AreEqual(Layers.Inhabitant, h.GetComponentInChildren<SkinnedMeshRenderer>(true).gameObject.layer,
                            $"{level} inhabitant {h.name}: the x-ray pass needs the Inhabitant layer on the model");
                        checkedElements++;
                    }
                }
                Assert.Greater(checkedElements, 2, level + ": premise: the data names models");
                Assert.AreEqual(checkedElements, Game.Level.ModelVisuals.Count, level + ": one model visual per element that names one");
            }

            // Facing, catalog wide: for every seat, the tallest part of the model is on the side of the procedural backrest.
            foreach ((string id, float side) in Seats)
            {
                var box = id == ModelCatalog.KenneySofa ? new Vector3(2.0f, 0.85f, 0.9f) : new Vector3(0.45f, 0.9f, 0.45f);
                Transform reference = Scratch("Procedural " + id);
                if (id == ModelCatalog.KenneySofa)
                {
                    FurnitureKit.Build(new PropDef { Name = "Sofa", Kind = "sofa", SizeX = box.x, SizeY = box.y, SizeZ = box.z }, reference, 0, false);
                }
                else
                {
                    FurnitureKit.Chair(reference, box, Color.gray, 0);
                }
                Transform backrest = reference.Find("Backrest");
                Assert.IsNotNull(backrest, id + ": no procedural backrest");
                Assert.AreEqual(Mathf.Sign(side), Mathf.Sign(backrest.localPosition.z), id + ": the procedural backrest moved side");
                Transform frame = Scratch("Facing " + id);
                GameObject model = ModelKit.Instantiate(id, frame, box, ModelFit.Box);
                Assert.IsNotNull(model, id);
                float tallest = TallestSide(model.transform, frame, out float depth);
                AssertSameSide(tallest, depth, backrest.localPosition.z, "catalog " + id);
                // Control: the same model turned half way must read on the other side, or the measure sees nothing.
                Transform turned = Scratch("Turned " + id);
                model.transform.SetParent(turned, true);
                turned.rotation = Quaternion.Euler(0f, 180f, 0f);
                Assert.AreEqual(-Mathf.Sign(tallest), Mathf.Sign(TallestSide(model.transform, frame, out _)), id + ": control: a half turn does not flip the facing");
            }

            // Facing in the levels: the level 1 sofa against its own Backrest collider, every chair against the procedural chair.
            yield return LoadLevel("level1");
            Transform sofa = Child("Sofa");
            Transform sofaBackrest = sofa.Find("Backrest");
            Assert.IsNotNull(sofaBackrest, "level1: the sofa lost its Backrest collider");
            Assert.IsNotNull(sofaBackrest.GetComponent<BoxCollider>(), "level1: the sofa Backrest is not a collider");
            Assert.IsNull(sofaBackrest.GetComponent<MeshFilter>(), "level1: the sofa Backrest still has a MeshFilter");
            Transform sofaModel = ModelKit.ModelRootsUnder(sofa).Single();
            AssertSameSide(TallestSide(sofaModel, sofa, out float sofaDepth), sofaDepth, sofaBackrest.localPosition.z, "level1 sofa");
            yield return LoadLevel("level3");
            var chairs = new List<Transform> { Game.Furniture.transform };
            chairs.AddRange(Game.Level.Decoys.Select(d => d.transform));
            Assert.Greater(chairs.Count, 1, "premise: level 3 has decoys");
            foreach (Transform chair in chairs)
            {
                Transform model = ModelKit.ModelRootsUnder(chair).Single();
                // The player visual hops and rocks; its parent Visual is the chair frame.
                Transform frame = model.parent;
                AssertSameSide(TallestSide(model, frame, out float depth), depth, -1f, "level3 " + chair.name);
            }

            // An unknown id falls back with one warning and no error, directly and through the level builder.
            int warned = warnings.Count;
            Assert.IsNull(ModelKit.Instantiate("nope.unknown", Scratch("Unknown"), new Vector3(0.5f, 0.5f, 0.5f), ModelFit.Box));
            Assert.AreEqual(warned + 1, warnings.Count, "exactly one warning");
            StringAssert.Contains("nope.unknown", warnings[warnings.Count - 1]);
            yield return LoadLevel("level1");
            warned = warnings.Count;
            Game.Def.Player.Model = "nope.unknown";
            Game.Restart();
            Assert.AreEqual(warned + 1, warnings.Count, "the level builder logs one warning: " + string.Join(" | ", warnings.Skip(warned)));
            CollectionAssert.AreEqual(new[] { "player (nope.unknown)" }, Game.Level.ModelFallbacks);
            Assert.AreEqual(0, ModelKit.ModelRootsUnder(Game.Furniture.transform).Count, "no model on the fallback player");
            Assert.AreEqual(6, Game.Furniture.GetComponentsInChildren<MeshRenderer>(true).Length, "the procedural chair (6 boxes) is back");
            Assert.Greater(Game.Level.ModelVisuals.Count, 0, "the other models are still there");
            yield return Steps(5);
            Assert.AreEqual(PlayState.Playing, Game.State);
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        // ----- 22b (M3.1 B1) -----

        /// <summary>
        /// At the start view of each level, nothing drawn on the Occluder layer stands between the camera and the top
        /// of the chair, and every wall cap follows the WallFader rule: hidden exactly when its wall plane separates
        /// the camera from the chair (M3 drew the near outer cap across the frame). A control quad proves the check
        /// sees a blocker, and ignores one seen from behind.
        /// </summary>
        [UnityTest]
        public IEnumerator Step22b_NothingHidesTheChairAtTheStart()
        {
            foreach (string level in Levels)
            {
                yield return LoadLevel(level);
                yield return Steps(25);
                // Two rendered frames: the camera moved, then the WallFader applied its position.
                yield return null;
                yield return null;
                AssertModelsPresent(level);
                Camera cam = Game.Camera.GetComponent<Camera>();
                Assert.IsNotNull(cam, level + ": no camera");
                FurnitureController chair = Game.Furniture;
                Vector3 eye = cam.transform.position;
                Vector3 target = chair.transform.position;

                int caps = 0;
                int hiddenCaps = 0;
                foreach (MeshRenderer r in Game.Level.Root.GetComponentsInChildren<MeshRenderer>(true))
                {
                    if (r.name != "Cap")
                    {
                        continue;
                    }
                    caps++;
                    // The wall frame: origin on the centre line, +z toward the outside (LevelBuilder.BuildWallLine).
                    Transform wall = r.transform.parent;
                    bool separates = Vector3.Dot(eye - wall.position, wall.forward) * Vector3.Dot(target - wall.position, wall.forward) < 0f;
                    bool hidden = r.shadowCastingMode == UnityEngine.Rendering.ShadowCastingMode.ShadowsOnly;
                    Assert.AreEqual(separates, hidden, $"{level}: the cap of {wall.name} is {(hidden ? "hidden" : "drawn")} while its wall "
                        + $"{(separates ? "stands" : "does not stand")} between the camera and the chair");
                    if (hidden)
                    {
                        hiddenCaps++;
                    }
                }
                Assert.Greater(caps, 3, level + ": premise: the walls have caps");
                Assert.Greater(hiddenCaps, 0, level + ": premise: the start camera stands outside a wall (else nothing is tested)");

                List<string> blockers = Probe.ChairBlockers(cam, chair);
                CollectionAssert.IsEmpty(blockers, $"{level}: at the start view, drawn occluders hide the top of the chair");

                // Control: a quad on the Occluder layer half way to a top sample, front facing the camera, is a blocker;
                // turned to show the camera its back, it is culled, so it is not.
                var samples = new Vector3[Tuning.SampleCount];
                chair.GetSamplePoints(samples);
                Vector3 mid = Vector3.Lerp(eye, samples[1], 0.5f);
                GameObject quad = PrimitiveKit.Part(Scratch("Blocker " + level), "ControlQuad", PrimitiveKit.QuadMesh, mid,
                    Quaternion.LookRotation(samples[1] - eye), Vector3.one * 0.4f, PrimitiveKit.Lit(Color.gray), Layers.Occluder);
                Assert.IsTrue(Probe.ChairBlockers(cam, chair).Any(b => b.StartsWith("ControlQuad", StringComparison.Ordinal)),
                    level + ": control: a quad facing the camera in front of the chair is not seen as a blocker");
                quad.transform.rotation = Quaternion.LookRotation(eye - samples[1]);
                Assert.IsFalse(Probe.ChairBlockers(cam, chair).Any(b => b.StartsWith("ControlQuad", StringComparison.Ordinal)),
                    level + ": control: a quad seen from behind (culled) is counted as a blocker");
                Object.DestroyImmediate(quad);
            }
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        // ----- 23 -----

        /// <summary>Every collider of the level as (layer, bounds center, bounds size, trigger), sorted.</summary>
        private List<string> ColliderSet()
        {
            var set = new List<string>();
            foreach (Collider c in Game.Level.Root.GetComponentsInChildren<Collider>(true))
            {
                Bounds b = c.bounds;
                set.Add(string.Format(CultureInfo.InvariantCulture, "{0} {1} L{2} c({3:0.000},{4:0.000},{5:0.000}) s({6:0.000},{7:0.000},{8:0.000}) t{9} e{10}",
                    c.GetType().Name, c.name, c.gameObject.layer, b.center.x, b.center.y, b.center.z, b.size.x, b.size.y, b.size.z,
                    c.isTrigger, c.enabled && c.gameObject.activeInHierarchy));
            }
            set.Sort(StringComparer.Ordinal);
            return set;
        }

        [UnityTest]
        public IEnumerator Step23_CollidersUnchangedWithoutModels()
        {
            foreach (string level in Levels)
            {
                yield return LoadLevel(level);
                Game.Restart();
                AssertModelsPresent(level);
                List<string> withModels = ColliderSet();
                Assert.Greater(withModels.Count, 10, level + ": premise: the level has colliders");

                ModelKit.Disabled = true;
                try
                {
                    Game.Restart();
                    Assert.AreEqual(0, Game.Level.ModelVisuals.Count, level + ": ModelKit.Disabled still built models");
                    Assert.AreEqual(0, ModelKit.ModelRootsUnder(Game.Level.Root.transform).Count, level + ": a model root without ModelKit");
                    Assert.Greater(Game.Furniture.GetComponentsInChildren<MeshRenderer>(true).Length, 0, level + ": no procedural chair");
                    List<string> procedural = ColliderSet();
                    var onlyModels = withModels.Except(procedural).ToList();
                    var onlyProcedural = procedural.Except(withModels).ToList();
                    Assert.IsTrue(onlyModels.Count == 0 && onlyProcedural.Count == 0 && withModels.Count == procedural.Count,
                        $"{level}: colliders differ. With models only: {string.Join(" | ", onlyModels.Take(6))}. Procedural only: {string.Join(" | ", onlyProcedural.Take(6))}");
                }
                finally
                {
                    ModelKit.Disabled = false;
                }
                Game.Restart();
                yield return Steps(2);
                AssertModelsPresent(level + " after re-enabling");
            }
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        // ----- 25 -----

        [UnityTest]
        public IEnumerator Step25_BudgetsWithModels()
        {
            foreach (string level in Levels)
            {
                yield return LoadLevel(level);
                yield return Steps(3);
                AssertModelsPresent(level);
                Probe.RenderCount count = Probe.CountRenderers(Object.FindObjectsByType<Renderer>(FindObjectsSortMode.None));
                var furniture = new List<Transform> { Game.Furniture.transform };
                furniture.AddRange(Game.Level.Decoys.Select(d => d.transform));
                furniture.AddRange(Game.Def.Props.Select(p => Child(p.Name)));
                long worstFurniture = 0;
                foreach (Transform f in furniture)
                {
                    long t = Probe.TrianglesUnder(f);
                    worstFurniture = Math.Max(worstFurniture, t);
                    Assert.LessOrEqual(t, Tuning.BudgetFurnitureTriangles, $"{level}: furniture {f.name} has {t} triangles");
                }
                long worstInhabitant = 0;
                int worstBones = 0;
                foreach (Inhabitant h in Game.Level.Inhabitants)
                {
                    long t = Probe.TrianglesUnder(h.transform);
                    int bones = Probe.BonesUnder(h.transform);
                    SkinnedMeshRenderer skin = h.GetComponentInChildren<SkinnedMeshRenderer>(true);
                    Assert.IsNotNull(skin, $"{level}: premise: inhabitant {h.name} is skinned");
                    Assert.GreaterOrEqual(t, ModelKit.Triangles(skin.sharedMesh), $"{level}: the skinned triangles of {h.name} are not counted");
                    Assert.Greater(bones, 0, $"{level}: premise: the bones of {h.name} are counted");
                    Assert.LessOrEqual(t, Tuning.BudgetInhabitantTriangles, $"{level}: inhabitant {h.name} has {t} triangles");
                    // M5: a pet (the dog) may have Tuning.BudgetPetBones bones; humans keep 40.
                    int boneBudget = h.Rig != null && h.Rig.IsPet ? Tuning.BudgetPetBones : Tuning.BudgetInhabitantBones;
                    Assert.LessOrEqual(bones, boneBudget, $"{level}: inhabitant {h.name} has {bones} bones");
                    worstInhabitant = Math.Max(worstInhabitant, t);
                    worstBones = Math.Max(worstBones, bones);
                }
                Assert.Greater(count.MaterialSlots, count.Renderers, $"{level}: premise: multi-slot model renderers are counted slot by slot");
                Debug.Log($"[Step25] {level}: {count.Renderers} renderers, {count.Materials.Count} materials ({count.MaterialSlots} slots), "
                    + $"{count.Triangles} triangles, worst furniture {worstFurniture}, inhabitant {worstInhabitant} triangles / {worstBones} bones, "
                    + $"{Game.Level.ModelVisuals.Count} model visuals");
                // CONTRACT_M5 16.11 and 17: draw calls are material slots; a house of HouseBudgetRooms rooms has the house budget.
                bool house = Game.Def.AllRooms().Count >= Tuning.HouseBudgetRooms;
                Assert.LessOrEqual(count.MaterialSlots, house ? Tuning.BudgetHouseRenderers : Tuning.BudgetRenderers, level + ": draw calls (material slots)");
                Assert.LessOrEqual(count.Materials.Count, house ? Tuning.BudgetHouseMaterials : Tuning.BudgetMaterials,
                    $"{level}: materials: {string.Join(", ", count.Materials.Select(m => m.name).OrderBy(n => n))}");
                Assert.LessOrEqual(count.Triangles, Tuning.BudgetLevelTriangles, level + ": level triangles");
                Assert.AreEqual(0, count.SlotsWithoutMaterial, level + ": empty material slots");
                CollectionAssert.IsEmpty(count.NonUrp, level + ": non URP shaders");
            }

            // M3.1 S4: the woman (8 source materials) on level 3, the level with the most materials, stays within 24.
            yield return LoadLevel("level3");
            foreach (InhabitantDef h in Game.Def.Inhabitants)
            {
                h.Model = ModelCatalog.QuaterniusWoman;
            }
            Game.Restart();
            yield return Steps(3);
            AssertModelsPresent("level3 with the woman");
            CollectionAssert.IsEmpty(Game.Level.ModelFallbacks, "level3 with the woman: fallbacks");
            Mesh womanMesh = ModelCatalog.Lookup(ModelCatalog.QuaterniusWoman).prefab.GetComponentInChildren<SkinnedMeshRenderer>(true).sharedMesh;
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                SkinnedMeshRenderer skin = h.GetComponentInChildren<SkinnedMeshRenderer>(true);
                Assert.AreSame(womanMesh, skin.sharedMesh, $"premise: inhabitant {h.name} wears the woman model");
                Assert.AreEqual(8, skin.sharedMaterials.Length, "premise: the woman has 8 material slots");
                Assert.LessOrEqual(Probe.TrianglesUnder(h.transform), Tuning.BudgetInhabitantTriangles, $"the woman {h.name}: triangles");
                Assert.LessOrEqual(Probe.BonesUnder(h.transform), Tuning.BudgetInhabitantBones, $"the woman {h.name}: bones");
            }
            Probe.RenderCount woman = Probe.CountRenderers(Object.FindObjectsByType<Renderer>(FindObjectsSortMode.None));
            Debug.Log($"[Step25] level3 with the woman: {woman.Renderers} renderers, {woman.Materials.Count} materials ({woman.MaterialSlots} slots)");
            Assert.LessOrEqual(woman.Materials.Count, Tuning.BudgetMaterials,
                $"level3 with the woman: materials: {string.Join(", ", woman.Materials.Select(m => m.name).OrderBy(n => n))}");
            Assert.LessOrEqual(woman.Renderers, Tuning.BudgetRenderers, "level3 with the woman: renderers");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }
    }
}
