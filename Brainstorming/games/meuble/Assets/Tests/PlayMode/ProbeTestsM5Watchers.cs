using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M5 watchers probe (docs/CONTRACT_M5.md 3, 12 and 16.11; CONTRACT_M5_v3.md 4 and 15.5): probe steps 37 (the
    /// inhabitants' identity, eyes and cones) and 38 (the dog's eye, rig, cone, sleep and wake). Steps 37b to 37f and 38b
    /// to 38f are the game agent's.
    ///
    /// Fixtures: test_m5_watchers_people (three humans with personalities and a dog, none naming a model: the level builder
    /// resolves each personality's) and test_m5_watchers_dog (the dog alone, naming its model, starting asleep facing the
    /// chair, then walking 2 m to a station that sees it). Every scenario asserts its premise first, waits are bounded by
    /// game time (fixed steps), and the rendered pose is measured after every other LateUpdate.
    /// </summary>
    public sealed class ProbeTestsM5Watchers
    {
        private const float Dt = Tuning.FixedStep;
        private const string PeopleLevel = "test_m5_watchers_people";
        private const string DogLevel = "test_m5_watchers_dog";
        private const string FloorLevel = "test_m5_watchers_floor";

        /// <summary>The platform the man of the floor fixture dwells on.</summary>
        private const float PlatformHeight = 0.6f;

        /// <summary>Step 37: the visual eye (and the model's eyes, dwelling) against the routine's eye.</summary>
        private const float EyeTolerance = 0.05f;

        /// <summary>The humans of the people fixture take these personalities in two passes (the dog is the fourth).</summary>
        private static readonly string[][] Passes =
        {
            new[] { PersonalityDef.Dreamer, PersonalityDef.Watchful, PersonalityDef.Hurried },
            new[] { PersonalityDef.Granny, PersonalityDef.Teen, PersonalityDef.Tidy },
        };

        // The dog fixture (CONTRACT_M5_v3 4): the sleep station facing the chair, the station it walks to.
        private static readonly Vector3 SleepStation = new Vector3(0f, 0f, 1.5f);
        private static readonly Vector3 WatchStation = new Vector3(2f, 0f, 1.5f);
        private static readonly Vector3 BehindTheDog = new Vector3(-3.3f, 0f, 2.5f);

        // The Shiba's IK feet and the shin tips they hang under (M4.2's feet fix applies to its clips too).
        private static readonly (string foot, string tip)[] DogFeet =
        {
            ("FF.L", "FrontLowerLeg.L_end"), ("FF.R", "FrontLowerLeg.R_end"), ("FFB.L", "BackLowerLeg.L_end"), ("FFB.R", "BackLowerLeg.R_end"),
        };

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private int fixedSteps;
        private readonly List<Object> scratch = new List<Object>();

        private Main main;
        private GameState Game => main.Game;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            fixedSteps = 0;
            ModelKit.Disabled = false;
            GamePause.IsPaused = false;
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
            GamePause.IsPaused = false;
            Game.Rules = GameRules.M1;
            Game.FixedStepped += CountStep;
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            GamePause.IsPaused = false;
            Application.logMessageReceived -= OnLog;
            foreach (Object o in scratch)
            {
                if (o != null)
                {
                    Object.Destroy(o);
                }
            }
            scratch.Clear();
            if (main != null && main.Game != null)
            {
                main.Game.FixedStepped -= CountStep;
                if (main.Game.Furniture != null)
                {
                    main.Game.Furniture.ScriptedDirection = null;
                }
            }
            yield return null;
        }

        private void CountStep() => fixedSteps++;

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                exceptions++;
                logged.Add(condition);
            }
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private static int StepsFor(float seconds) => Mathf.CeilToInt(seconds / Dt);

        /// <summary>Runs the game at <paramref name="scale"/> until <paramref name="until"/> holds or <paramref name="maxSteps"/> fixed steps ran.</summary>
        private IEnumerator Run(int maxSteps, Func<bool> until, float scale)
        {
            int end = fixedSteps + maxSteps;
            float realStart = Time.realtimeSinceStartup;
            Time.timeScale = scale;
            try
            {
                while (fixedSteps < end && (until == null || !until()) && Time.realtimeSinceStartup - realStart < 150f)
                {
                    yield return null;
                }
            }
            finally
            {
                Time.timeScale = 1f;
            }
        }

        private IEnumerator Load(string id)
        {
            Game.LoadLevel(id);
            Game.Rules = GameRules.M1;
            yield return Steps(2);
            Assert.AreEqual(id, Game.Def.Id, "premise: the fixture did not load");
        }

        /// <summary>The people fixture with its three humans set to <paramref name="personalities"/>, rebuilt.</summary>
        private IEnumerator LoadPeople(string[] personalities)
        {
            yield return Load(PeopleLevel);
            List<InhabitantDef> humans = Game.Def.Inhabitants.Where(d => d.Kind != PersonalityDef.Dog).ToList();
            Assert.AreEqual(3, humans.Count, "premise: the people fixture has three humans");
            Assert.AreEqual(1, Game.Def.Inhabitants.Count(d => d.Kind == PersonalityDef.Dog), "premise: the people fixture has one dog");
            for (int i = 0; i < humans.Count; i++)
            {
                humans[i].Personality = personalities[i];
                Assert.IsTrue(string.IsNullOrEmpty(humans[i].Model), "premise: the fixture names no model (the personality's must show)");
                Assert.IsTrue(string.IsNullOrEmpty(humans[i].BodyColor), "premise: the fixture names no body colour (the personality's tint must show)");
            }
            Game.Restart();
            Game.Rules = GameRules.M1;
            yield return Steps(2);
        }

        private Transform Scratch(string name)
        {
            var go = new GameObject(name);
            scratch.Add(go);
            return go.transform;
        }

        private static WatchersFrameProbe Watch(Action late)
        {
            var go = new GameObject("WatchersFrameProbe");
            var probe = go.AddComponent<WatchersFrameProbe>();
            probe.Late = late;
            return probe;
        }

        private static void Unwatch(WatchersFrameProbe probe)
        {
            if (probe != null)
            {
                probe.Late = null;
                Object.Destroy(probe.gameObject);
            }
        }

        private Inhabitant TheDog => Game.Level.Inhabitants.FirstOrDefault(h => h.IsDog);

        private VisionConeView ConeOf(Inhabitant h) => Game.Level.Cones.Find(c => c != null && c.Owner == h);

        private static Color PaletteColour(Material m)
        {
            Color? c = PrimitiveKit.PaletteOf(m);
            Assert.IsTrue(c.HasValue, $"{m.name} is not a PrimitiveKit material");
            return c.Value;
        }

        private static bool Same(Color a, Color b)
        {
            Color32 x = a;
            Color32 y = b;
            return x.r == y.r && x.g == y.g && x.b == y.b;
        }

        private static bool InPalette(Color c) => Tuning.CharacterPalette.Any(p => Same(p, c));

        private static Transform FindDeep(Transform root, string name)
        {
            if (root.name == name)
            {
                return root;
            }
            for (int i = 0; i < root.childCount; i++)
            {
                Transform t = FindDeep(root.GetChild(i), name);
                if (t != null)
                {
                    return t;
                }
            }
            return null;
        }

        /// <summary>
        /// Every slot of a character model: the clothes wear <paramref name="tint"/>, every other slot a shared palette
        /// colour. Returns the model's distinct materials.
        /// </summary>
        private static HashSet<Material> AssertWears(GameObject model, ModelCatalog.Entry entry, Color tint, string label)
        {
            List<(Renderer renderer, int slot, string source)> slots = ModelKit.SourceSlots(model, entry);
            Assert.Greater(slots.Count, 2, $"{label}: premise: the model's slots are matched to its source materials");
            Material tinted = PrimitiveKit.Lit(tint);
            int clothes = 0;
            var used = new HashSet<Material>();
            foreach ((Renderer r, int slot, string source) in slots)
            {
                Material m = r.sharedMaterials[slot];
                used.Add(m);
                if (ModelKit.PartOf(source, entry.IsPet) == ModelKit.CharacterPart.Clothes)
                {
                    clothes++;
                    Assert.AreSame(tinted, m, $"{label}: the clothes slot {slot} ({source}) is not in the tint");
                }
                else
                {
                    Color c = PaletteColour(m);
                    Assert.IsTrue(InPalette(c), $"{label}: slot {slot} ({source}) is {c}, not a palette colour");
                }
            }
            Assert.Greater(clothes, 0, $"{label}: premise: no clothes slot to tint");
            return used;
        }

        // ----- 37 -----

        /// <summary>
        /// Every personality (and the dog) has its own catalog model of its kind and its own clothes tint (CONTRACT_M5 3),
        /// never red, never a palette colour; fitted, each model wears its tint on its clothes and only palette colours
        /// elsewhere (16.11), so the six humans and the dog together use at most 8 shared colours plus their tints, and any
        /// 3 humans with the dog at most 12 materials.
        /// </summary>
        [UnityTest]
        public IEnumerator Step37_EveryPersonalityHasItsOwnModelAndTint()
        {
            var models = new Dictionary<string, string>();
            var tints = new Dictionary<string, Color>();
            var materials = new Dictionary<string, HashSet<Material>>();
            foreach (string id in PersonalityDef.All.Where(i => i != PersonalityDef.Default))
            {
                PersonalityDef p = PersonalityDef.For(id);
                bool dog = id == PersonalityDef.Dog;
                Assert.IsFalse(string.IsNullOrEmpty(p.Model), id + ": no model");
                ModelCatalog.Entry entry = ModelCatalog.Lookup(p.Model);
                Assert.IsNotNull(entry, $"{id}: the catalog does not resolve {p.Model}");
                Assert.AreEqual(dog ? ModelCatalog.KindPet : ModelCatalog.KindHuman, entry.kind, $"{id}: {p.Model} is the wrong kind");
                Assert.IsTrue(ColorUtility.TryParseHtmlString(p.Tint, out Color tint), $"{id}: tint '{p.Tint}' does not parse");
                tint.a = 1f;
                Assert.IsFalse(ModelMath.IsRed(tint), $"{id}: tint {p.Tint} is red (PRD 7.2: red is the player's)");
                Assert.IsFalse(InPalette(tint), $"{id}: tint {p.Tint} is a shared palette colour");
                CollectionAssert.DoesNotContain(models.Values, p.Model, $"{id}: model {p.Model} is another personality's");
                Assert.IsFalse(tints.Values.Any(t => Same(t, tint)), $"{id}: tint {p.Tint} is another personality's");
                models[id] = p.Model;
                tints[id] = tint;

                Transform parent = Scratch("Identity " + id);
                GameObject model = ModelKit.Instantiate(p.Model, parent, new Vector3(0.5f, 1.75f, 0.5f), ModelFit.Uniform,
                    new ModelPaint { Main = tint });
                Assert.IsNotNull(model, $"{id}: {p.Model} does not instantiate");
                materials[id] = AssertWears(model, entry, tint, id);
                // The same model tinted after the fact (as the rig does at Attach) ends the same.
                GameObject plain = ModelKit.Instantiate(p.Model, Scratch("Retinted " + id), new Vector3(0.5f, 1.75f, 0.5f), ModelFit.Uniform);
                Assert.Greater(ModelKit.TintClothes(plain, entry, tint), 0, $"{id}: TintClothes found no clothes");
                CollectionAssert.AreEquivalent(materials[id], AssertWears(plain, entry, tint, id + " retinted"), $"{id}: a later tint differs");
                yield return null;
            }
            Assert.AreEqual(7, models.Count, "premise: six personalities and the dog");

            // All of them: 8 shared colours at most, plus one tint each.
            var all = new HashSet<Material>(materials.Values.SelectMany(m => m));
            int shared = all.Count(m => InPalette(PaletteColour(m)));
            Assert.LessOrEqual(shared, Tuning.CharacterPalette.Length, "the characters use more than the 8 shared colours");
            Assert.AreEqual(all.Count, shared + models.Count, "every material is a shared colour or a personality's tint");
            // Any three humans and the dog.
            string[] humans = models.Keys.Where(k => k != PersonalityDef.Dog).ToArray();
            int worst = 0;
            string worstSet = null;
            for (int a = 0; a < humans.Length; a++)
            {
                for (int b = a + 1; b < humans.Length; b++)
                {
                    for (int c = b + 1; c < humans.Length; c++)
                    {
                        var set = new HashSet<Material>(materials[humans[a]].Concat(materials[humans[b]]).Concat(materials[humans[c]])
                            .Concat(materials[PersonalityDef.Dog]));
                        if (set.Count > worst)
                        {
                            worst = set.Count;
                            worstSet = $"{humans[a]}, {humans[b]}, {humans[c]} and the dog";
                        }
                    }
                }
            }
            Debug.Log($"[Step37] characters: {all.Count} materials for the six personalities and the dog ({shared} shared); "
                + $"the worst three humans and a dog: {worstSet}, {worst} materials");
            Assert.LessOrEqual(worst, 12, $"{worstSet} use {worst} materials (CONTRACT_M5 16.11: at most 12)");
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        /// <summary>
        /// Built by the real level builder from data that names no model: each inhabitant has its personality (the dog
        /// row for the dog kind), wears its personality's model, tinted on its clothes, distinct from the others; three
        /// humans and the dog stay within 12 character materials.
        /// </summary>
        [UnityTest]
        public IEnumerator Step37_InhabitantsWearTheirPersonality()
        {
            var counts = new List<string>();
            foreach (string[] pass in Passes)
            {
                yield return LoadPeople(pass);
                var seenModels = new HashSet<string>();
                var seenTints = new HashSet<Color32>();
                var characterMaterials = new HashSet<Material>();
                int humans = 0;
                foreach (Inhabitant h in Game.Level.Inhabitants)
                {
                    InhabitantDef def = h.Def;
                    Assert.IsNotNull(def, $"{h.name}: Init kept no InhabitantDef");
                    string want = def.Kind == PersonalityDef.Dog ? PersonalityDef.Dog : def.Personality;
                    Assert.IsNotNull(h.Personality, $"{h.name}: no personality");
                    Assert.AreEqual(want, h.Personality.Id, $"{h.name}: personality");
                    Assert.AreSame(h.Routine.Personality, h.Personality, $"{h.name}: the inhabitant and its routine disagree on the personality");
                    Assert.AreEqual(def.Kind == PersonalityDef.Dog, h.IsDog, $"{h.name}: IsDog");
                    PersonalityDef row = PersonalityDef.For(want);
                    Assert.IsNotNull(h.Rig, $"{h.name} ({want}) shows no model: the level builder must instantiate Inhabitant.ModelIdOf(def) "
                        + $"= {Inhabitant.ModelIdOf(def)} (CONTRACT_M5 3) and attach its rig");
                    Assert.AreEqual(row.Model, h.Rig.Entry.id, $"{h.name}: model");
                    Assert.AreEqual(def.Kind == PersonalityDef.Dog, h.Rig.IsPet, $"{h.name}: a pet rig exactly on the dog");
                    Assert.IsTrue(h.Tint.HasValue, $"{h.name}: no tint");
                    Assert.IsTrue(ColorUtility.TryParseHtmlString(row.Tint, out Color tint), $"premise: {want}'s tint parses");
                    Assert.IsTrue(Same(tint, h.Tint.Value), $"{h.name}: tint {h.Tint.Value}, expected {row.Tint}");
                    Assert.Greater(h.TintedSlots, 0, $"{h.name}: no clothes slot took the tint");
                    characterMaterials.UnionWith(AssertWears(ModelKit.ModelRootsUnder(h.transform).Single().gameObject, h.Rig.Entry, tint, h.name));
                    Assert.IsTrue(seenModels.Add(h.Rig.Entry.id), $"{h.name}: model {h.Rig.Entry.id} is worn twice in the level");
                    Assert.IsTrue(seenTints.Add(h.Tint.Value), $"{h.name}: tint worn twice in the level");
                    humans += h.IsDog ? 0 : 1;
                }
                Assert.AreEqual(3, humans, "premise: three humans");
                CollectionAssert.IsEmpty(Game.Level.ModelFallbacks, "fallbacks");
                Probe.RenderCount level = Probe.CountRenderers(Game.Level.Root.GetComponentsInChildren<Renderer>(false));
                counts.Add($"{string.Join(", ", pass)} and the dog: {characterMaterials.Count} character materials, "
                    + $"{level.Materials.Count} materials and {level.MaterialSlots} material slots in the level");
                Assert.LessOrEqual(characterMaterials.Count, 12, $"{string.Join(", ", pass)} and the dog: {characterMaterials.Count} character materials");
            }
            Debug.Log("[Step37] " + string.Join(" | ", counts));
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        /// <summary>
        /// In every rendered frame of 8 s of play, the visual eye of every inhabitant (the floor cone's apex) is the
        /// routine's eye within 0.05 m (the eye height of its personality: 1.6 m, the dog's 0.35 m, plus the floor), and
        /// a dwelling model's own eyes (head held as the rig holds it) are there too. On the people fixture, the dog's, and
        /// a split level where a man dwells on a 0.6 m platform (CONTRACT_M5_v3 15.4): his body stands on it, and his cone's
        /// apex too while the fan's far vertices lie on the floor below.
        /// </summary>
        [UnityTest]
        public IEnumerator Step37_VisualEyeIsTheRoutineEye()
        {
            int frames = 0;
            int modelFrames = 0;
            int raisedFrames = 0;
            float worst = 0f;
            float worstModel = 0f;
            float worstRaised = 0f;
            string worstWho = null;
            foreach (string level in new[] { PeopleLevel, DogLevel, FloorLevel })
            {
                if (level == PeopleLevel)
                {
                    yield return LoadPeople(Passes[1]);
                }
                else
                {
                    yield return Load(level);
                }
                if (level == FloorLevel)
                {
                    Inhabitant perched = Game.Level.Inhabitants.Single();
                    Assert.That(perched.Routine.FloorHeight, Is.EqualTo(PlatformHeight).Within(0.01f),
                        "premise: the man dwells on the platform (the routine's floor is the level's)");
                    Assert.That(perched.Routine.EyePosition.y, Is.EqualTo(PlatformHeight + Tuning.EyeHeight).Within(0.01f),
                        "premise: the routine's eye adds the platform");
                }
                foreach (Inhabitant h in Game.Level.Inhabitants)
                {
                    float eye = h.Routine.Personality.EyeHeight;
                    Assert.AreEqual(h.IsDog ? Tuning.DogEyeHeight : Tuning.EyeHeight, eye, 1e-6f, $"{level}/{h.name}: the personality's eye");
                }
                WatchersFrameProbe probe = Watch(() =>
                {
                    foreach (Inhabitant h in Game.Level.Inhabitants)
                    {
                        InhabitantRoutine r = h.Routine;
                        float d = (h.VisualEyePosition - r.EyePosition).magnitude;
                        if (d > worst)
                        {
                            worst = d;
                            worstWho = $"{level}/{h.name} ({r.LastActivity})";
                        }
                        frames++;
                        if (r.FloorHeight > 0.1f)
                        {
                            // On the platform: the body stands on it, and the cone's apex lies on it too.
                            raisedFrames++;
                            worstRaised = Mathf.Max(worstRaised, Mathf.Abs(h.transform.position.y - r.FloorHeight));
                            VisionConeView cone = ConeOf(h);
                            if (cone != null && !cone.Hidden)
                            {
                                worstRaised = Mathf.Max(worstRaised, Mathf.Abs(cone.Vertices[0].y - (r.FloorHeight + 0.015f)));
                            }
                        }
                        float standing = r.Personality.EyeHeight;
                        bool dwelling = (r.LastActivity == RoutineActivity.Idle || r.LastActivity == RoutineActivity.Waiting)
                            && Mathf.Abs(r.EyeHeight - standing) < 1e-4f && h.Rig != null
                            && h.Rig.CurrentClip == InhabitantRig.Clip.Idle && h.Rig.IdleState != null && h.Rig.IdleState.weight > 0.99f;
                        if (dwelling)
                        {
                            worstModel = Mathf.Max(worstModel, Mathf.Abs(h.Rig.EyePosition.y - r.EyePosition.y));
                            modelFrames++;
                        }
                    }
                });
                yield return Run(StepsFor(level == FloorLevel ? 3f : 8f), null, 4f);
                Unwatch(probe);
                Assert.AreEqual(PlayState.Playing, Game.State, $"{level}: the level ended ({Game.LoseReason})");
                if (level == FloorLevel)
                {
                    // The fan descends from the platform: its far vertices lie on the floor below.
                    Vector3[] v = ConeOf(Game.Level.Inhabitants.Single()).Vertices;
                    Assert.Less(v.Skip(1).Min(p => p.y), 0.05f, "no vertex of the platform man's fan lies on the floor below");
                }
            }
            Debug.Log($"[Step37] visual eye: {frames} samples, worst {worst:0.0000} m ({worstWho}); model eyes dwelling: {modelFrames} samples, "
                + $"worst {worstModel:0.000} m; on the platform: {raisedFrames} samples, body and apex off the floor by {worstRaised:0.0000} m");
            Assert.Greater(frames, 200, "premise: too few rendered samples");
            Assert.Greater(modelFrames, 20, "premise: too few dwelling model samples (no rigged inhabitant?)");
            Assert.Greater(raisedFrames, 20, "premise: too few samples on the platform");
            Assert.LessOrEqual(worstRaised, 0.002f, $"on the platform the body or the cone's apex stands {worstRaised:0.000} m off the floor");
            Assert.LessOrEqual(worst, EyeTolerance, $"the visual eye left the routine's eye by {worst:0.000} m ({worstWho})");
            Assert.LessOrEqual(worstModel, EyeTolerance, $"a dwelling model's eyes stand {worstModel:0.000} m off the routine's eye");
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        /// <summary>
        /// Each floor cone uses its own watcher's range and half angle (CONTRACT_M5 3; the teen sees 6 m at 35 deg, the dog
        /// 6 m at 70 deg): pinned facing +x in open floor, its central ray reaches exactly the range, no vertex goes past
        /// it, and its outer rays open at the half angle.
        /// </summary>
        [UnityTest]
        public IEnumerator Step37_EachConeUsesItsWatchersRangeAndAngle()
        {
            int checkedCones = 0;
            foreach (string[] pass in Passes)
            {
                yield return LoadPeople(pass);
                for (int i = 0; i < Game.Level.Inhabitants.Count; i++)
                {
                    Inhabitant h = Game.Level.Inhabitants[i];
                    PersonalityDef row = PersonalityDef.For(h.IsDog ? PersonalityDef.Dog : h.Def.Personality);
                    var at = new Vector3(-5f, 0f, -1.5f + 1f * i);
                    h.Pin(at, 90f);
                    yield return Steps(2);
                    yield return null;
                    VisionConeView cone = ConeOf(h);
                    Assert.IsNotNull(cone, $"{h.name}: no cone");
                    Assert.IsFalse(cone.Hidden, $"premise: {h.name}'s cone is hidden");
                    Assert.AreEqual(1f, cone.RangeFactor, 1e-6f, "premise: no dark lamp");
                    Assert.AreEqual(row.ViewRange, cone.Range, 1e-4f, $"{h.name} ({row.Id}): cone range");
                    Assert.AreEqual(row.HalfAngle, cone.HalfAngle, 1e-4f, $"{h.name} ({row.Id}): cone half angle");
                    Vector3[] v = cone.Vertices;
                    Vector3 apex = v[0];
                    Assert.That(Vector3.Distance(YawMath.Planar(apex), YawMath.Planar(h.VisualEyePosition)), Is.LessThan(1e-3f), $"{h.name}: the apex is not under the eye");
                    int n = v.Length - 1;
                    float far = 0f;
                    for (int k = 1; k < v.Length; k++)
                    {
                        far = Mathf.Max(far, YawMath.Planar(v[k] - apex).magnitude);
                    }
                    float central = YawMath.Planar(v[1 + n / 2] - apex).magnitude;
                    Assert.LessOrEqual(far, row.ViewRange + 0.01f, $"{h.name} ({row.Id}): the fan reaches {far:0.00} m, past its {row.ViewRange} m");
                    Assert.That(central, Is.EqualTo(row.ViewRange).Within(0.05f), $"{h.name} ({row.Id}): the central ray reaches {central:0.00} m in open floor");
                    float left = Vector3.Angle(Vector3.right, YawMath.Planar(v[1] - apex));
                    float right = Vector3.Angle(Vector3.right, YawMath.Planar(v[n] - apex));
                    Assert.That(left, Is.EqualTo(row.HalfAngle).Within(0.5f), $"{h.name} ({row.Id}): first ray at {left:0.0} deg");
                    Assert.That(right, Is.EqualTo(row.HalfAngle).Within(0.5f), $"{h.name} ({row.Id}): last ray at {right:0.0} deg");
                    checkedCones++;
                }
            }
            Assert.AreEqual(8, checkedCones, "premise: six humans and the dog twice");
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        // ----- 38 -----

        /// <summary>
        /// The dog (CONTRACT_M5_v3 4, 15.5): its routine eye, its visual eye and its model's own eyes at 0.35 m; a pet rig
        /// (Idle and Walk from its clip map, no Jump, no brows, 46 bones at most, the clips completed as M4.2's feet fix).
        /// </summary>
        [UnityTest]
        public IEnumerator Step38_DogEyeIsLowAndItsModelIsAPet()
        {
            yield return Load(DogLevel);
            Inhabitant dog = TheDog;
            Assert.IsNotNull(dog, "premise: the fixture has no dog");
            Assert.AreEqual(PersonalityDef.Dog, dog.Personality.Id, "the dog's personality");
            InhabitantRig rig = dog.Rig;
            Assert.IsNotNull(rig, "premise: the dog has no rig (its model did not attach)");
            Assert.AreEqual(ModelCatalog.QuaterniusShiba, rig.Entry.id, "premise: the Shiba");
            Assert.IsTrue(rig.IsPet, "the Shiba's rig is not a pet's");
            Assert.IsNotNull(rig.IdleState, "no Idle");
            Assert.IsNotNull(rig.WalkState, "no Walk");
            Assert.AreEqual(rig.Entry.idleClip, rig.IdleClipName, "Idle is not the clip map's");
            Assert.AreEqual(rig.Entry.walkClip, rig.WalkClipName, "Walk is not the clip map's");
            Assert.IsNull(rig.JumpState, "a pet has no Jump");
            Assert.IsNull(rig.BrowLeft, "a pet has no brows");
            Assert.Greater(rig.CompletedProperties, 0, "the dog's Idle and Walk were not completed (M4.2 feet fix)");
            Assert.IsTrue(rig.CalibratedFromBindPose, "the dog's head calibration did not come from the bind pose");
            int bones = Probe.BonesUnder(dog.transform);
            Assert.Greater(bones, Tuning.BudgetInhabitantBones, "premise: the Shiba has more bones than a human may");
            Assert.LessOrEqual(bones, Tuning.BudgetPetBones, "the dog's bones");
            Assert.LessOrEqual(Probe.TrianglesUnder(dog.transform), Tuning.BudgetInhabitantTriangles, "the dog's triangles");

            InhabitantRoutine r = dog.Routine;
            Assert.IsTrue(r.Asleep, "premise: the dog starts asleep");
            Assert.AreEqual(Tuning.DogEyeHeight, r.EyeHeight, 1e-5f, "the routine's eye height");
            float worstVisual = 0f;
            float sum = 0f;
            int samples = 0;
            WatchersFrameProbe probe = Watch(() =>
            {
                worstVisual = Mathf.Max(worstVisual, Mathf.Abs(dog.VisualEyePosition.y - (Tuning.DogEyeHeight + r.FloorHeight)));
                if (rig.CurrentClip == InhabitantRig.Clip.Idle)
                {
                    sum += rig.EyePosition.y - dog.transform.position.y;
                    samples++;
                }
            });
            yield return Run(StepsFor(1.2f), null, 1f);
            Unwatch(probe);
            Assert.IsTrue(r.Asleep, "premise: still asleep");
            Assert.Greater(samples, 5, "premise: too few Idle frames");
            float modelEye = sum / samples;
            Debug.Log($"[Step38] dog: {bones} bones, routine eye {r.EyeHeight} m, visual eye off by {worstVisual:0.0000} m, model eyes at {modelEye:0.000} m");
            Assert.LessOrEqual(worstVisual, 0.005f, "the visual eye is not at 0.35 m");
            Assert.That(modelEye, Is.EqualTo(Tuning.DogEyeHeight).Within(0.03f), "the Shiba's eyes are not at the dog's eye");
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        /// <summary>
        /// Asleep, the dog's cone and chevron are hidden and a "z" floats above its head; the wake telegraph that ends the
        /// sleep (0.6 s, eye still closed) keeps the cone hidden, blinks the "z" and tilts the head; awake, the cone shows
        /// and the marker goes.
        /// </summary>
        [UnityTest]
        public IEnumerator Step38_SleepHidesTheConeAndTheWakeIsTelegraphed()
        {
            yield return Load(DogLevel);
            Inhabitant dog = TheDog;
            Assert.IsNotNull(dog, "premise: no dog");
            InhabitantRoutine r = dog.Routine;
            VisionConeView cone = ConeOf(dog);
            Assert.IsNotNull(cone, "premise: the dog has no cone");
            yield return null;
            Assert.IsTrue(r.Asleep, "premise: the dog starts asleep");
            Assert.IsTrue(cone.Hidden, "the sleeping dog's cone shows");
            Assert.IsFalse(cone.GetComponent<MeshRenderer>().enabled, "the sleeping dog's fan renders");
            Assert.IsFalse(cone.Facing.GetComponent<Canvas>().enabled, "the sleeping dog's chevron renders");
            Assert.AreEqual(Inhabitant.MarkerKind.Sleeping, dog.Marker, "no sleep marker");
            Assert.IsTrue(dog.MarkerShown, "the sleep marker is not drawn");
            float above = dog.MarkerPosition.y - dog.VisualEyePosition.y;
            Assert.That(above, Is.InRange(0.2f, 1.0f), $"the z floats {above:0.00} m above the dog's eye");
            Assert.Less(YawMath.Planar(dog.MarkerPosition - dog.transform.position).magnitude, 0.6f, "the z is not over the dog");

            // The wake telegraph: asleep and telegraphing, for 0.6 s.
            int wakeSteps = 0;
            int wakeHidden = 0;
            int wakeMarked = 0;
            float maxTilt = 0f;
            WatchersFrameProbe probe = Watch(() =>
            {
                if (r.Asleep && r.IsTelegraphing)
                {
                    maxTilt = Mathf.Max(maxTilt, dog.Rig != null ? dog.Rig.Tilt : 0f);
                    wakeHidden += cone.Hidden && !cone.GetComponent<MeshRenderer>().enabled ? 1 : 0;
                    wakeMarked += dog.Marker == Inhabitant.MarkerKind.Waking && dog.MarkerShown ? 1 : 0;
                }
            });
            Action count = () => wakeSteps += r.Asleep && r.IsTelegraphing ? 1 : 0;
            Game.FixedStepped += count;
            yield return Run(StepsFor(4f), () => !r.Asleep, 1f);
            Game.FixedStepped -= count;
            Unwatch(probe);
            Assert.IsFalse(r.Asleep, "premise: the dog never woke");
            Debug.Log($"[Step38] wake: {wakeSteps} telegraph steps, {wakeMarked} frames with the blinking z, max head tilt {maxTilt:0.00}");
            Assert.AreEqual(Mathf.RoundToInt(Tuning.WakeTelegraph / Dt), wakeSteps, 1, "the wake telegraph is not 0.6 s with the eye closed");
            Assert.Greater(wakeMarked, 3, "the wake telegraph shows no blinking z");
            Assert.AreEqual(wakeMarked, wakeHidden, "the cone showed during the wake telegraph");
            Assert.Greater(maxTilt, 0.5f, "the head shows no telegraph tilt while waking");

            yield return Steps(1);
            yield return null;
            Assert.IsFalse(cone.Hidden, "the awake dog's cone is hidden");
            Assert.IsTrue(cone.GetComponent<MeshRenderer>().enabled, "the awake dog's fan does not render");
            Assert.AreEqual(Inhabitant.MarkerKind.None, dog.Marker, "the awake dog still shows a marker");
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        /// <summary>
        /// Awake, the dog's cone is its own cyan (Tuning.DogConeColor; the vivid, more opaque Tuning.DogConeAlarmColor while it
        /// sees the chair, and its chevron with it), with its 6 m range and 70 deg half angle; it walks on its pet rig, its
        /// head following the eye yaw, its steps the synthesized patter played by its FootstepAudio (required whenever the
        /// footstep library resolves), and after the walk its Idle feet are where they were before it (the completed clips).
        /// </summary>
        [UnityTest]
        public IEnumerator Step38_DogConeColourWalkPatterAndFeet()
        {
            yield return Load(DogLevel);
            Inhabitant dog = TheDog;
            Assert.IsNotNull(dog, "premise: no dog");
            InhabitantRig rig = dog.Rig;
            Assert.IsNotNull(rig, "premise: the dog has no rig");
            InhabitantRoutine r = dog.Routine;
            VisionConeView cone = ConeOf(dog);
            Vision vision = Game.Level.Visions.Find(v => v != null && v.Owner == dog);
            Assert.IsNotNull(vision, "premise: the dog has no vision");

            // The feet in Idle at the start (asleep), against the same feet in Idle after the walk.
            var feet = new List<(Transform foot, Transform tip)>();
            foreach ((string foot, string tip) in DogFeet)
            {
                Transform f = FindDeep(rig.Model.transform, foot);
                Transform t = FindDeep(rig.Model.transform, tip);
                Assert.IsNotNull(f, "premise: no " + foot);
                Assert.IsNotNull(t, "premise: no " + tip);
                feet.Add((f, t));
            }
            yield return null;
            float[] before = feet.Select(p => (p.foot.position - p.tip.position).magnitude).ToArray();

            int walkFrames = 0;
            float worstHead = 0f;
            int contactsBefore = dog.FootstepCount;
            WatchersFrameProbe probe = Watch(() =>
            {
                if (r.LastActivity == RoutineActivity.Walking && rig.CurrentClip == InhabitantRig.Clip.Walk)
                {
                    walkFrames++;
                    Vector3 head = YawMath.Planar(rig.HeadForward);
                    worstHead = Mathf.Max(worstHead, Vector3.Angle(head, YawMath.Forward(dog.VisualEyeYaw)));
                }
            });
            // Wake, turn, walk 2 m, turn, settle in Idle at the watch station.
            yield return Run(StepsFor(12f), () => !r.Asleep && r.InDwell && r.StationIndex == 1 && r.LastActivity == RoutineActivity.Waiting
                && rig.CurrentClip == InhabitantRig.Clip.Idle && rig.IdleState.weight > 0.99f, 2f);
            yield return Run(StepsFor(0.5f), null, 1f);
            Unwatch(probe);
            Assert.AreEqual(1, r.StationIndex, $"premise: the dog did not reach its watch station ({r.LastActivity})");
            Assert.That(Vector3.Distance(YawMath.Planar(dog.transform.position), WatchStation), Is.LessThan(0.05f), "premise: not at the watch station");
            Debug.Log($"[Step38] walk: {walkFrames} walking frames, head off the eye yaw by {worstHead:0.0} deg, {dog.FootstepCount - contactsBefore} paw contacts");
            Assert.Greater(walkFrames, 10, "premise: the dog never walked on its Walk clip");
            Assert.LessOrEqual(worstHead, 5f, "the dog's head does not follow its eye yaw");
            Assert.Greater(dog.FootstepCount - contactsBefore, 4, "the dog's walk counted no foot contacts");
            float[] after = feet.Select(p => (p.foot.position - p.tip.position).magnitude).ToArray();
            for (int i = 0; i < feet.Count; i++)
            {
                Assert.That(after[i], Is.EqualTo(before[i]).Within(0.02f),
                    $"{DogFeet[i].foot}: {after[i]:0.000} m from its shin in Idle after the walk, {before[i]:0.000} m before (a foot left mid stride)");
            }
            // The patter (critique m10): whenever the footstep library resolves, Sfx gives every inhabitant, the dog included,
            // its FootstepAudio, so a dog without one walks silently and fails. Only an explicitly absent library falls back
            // to checking the synthesized patter directly.
            FootstepAudio steps = dog.GetComponent<FootstepAudio>();
            Sfx sfx = main.Sfx;
            bool library = sfx != null && sfx.Library != null && AudioLibrary.HasAll(sfx.Library.footsteps);
            if (library)
            {
                Assert.IsNotNull(steps, "the footstep library resolves, yet the dog has no FootstepAudio (it walks silently)");
                Assert.IsTrue(steps.IsPatter, "the dog walks in shoes");
                Assert.Greater(steps.StepsPlayed, 0, "no patter played");
                Assert.IsNotNull(steps.LastClip, "the dog's last step has no clip");
                StringAssert.StartsWith(FootstepAudio.PatterClipPrefix, steps.LastClip.name, "the dog's step is not the patter");
            }
            else
            {
                Debug.LogWarning("[Step38] premise: no footstep library (Sfx " + (sfx != null) + "): the patter is checked directly");
                Assert.IsNull(steps, "premise: a FootstepAudio exists without a footstep library");
                AudioLibrary.Entry[] patter = FootstepAudio.DogPatter;
                Assert.AreEqual(Tuning.DogPatterVariants, patter.Length, "the patter variants");
                Assert.IsTrue(AudioLibrary.HasAll(patter), "the synthesized patter has no clips");
                StringAssert.StartsWith(FootstepAudio.PatterClipPrefix, patter[0].clip.name, "the patter clip name");
            }

            // The cone: the dog's range and angle, its colour, sees the chair (alarm), then not (calm).
            yield return null;
            Assert.IsFalse(cone.Hidden, "premise: the awake dog's cone is hidden");
            Assert.AreEqual(6f, cone.Range, 1e-4f, "the dog's cone range");
            Assert.AreEqual(70f, cone.HalfAngle, 1e-4f, "the dog's cone half angle");
            Assert.IsTrue(vision.SeesPlayer, "premise: at its watch station the dog sees the chair");
            Color alarm = cone.Color;
            Assert.AreEqual(VisionConeView.ConeColor(true, true, false), alarm, "the dog's cone while it sees the chair");
            Material fan = cone.GetComponent<MeshRenderer>().sharedMaterial;
            Assert.AreSame(PrimitiveKit.UnlitTransparent(alarm), fan, "the fan's material is not the cone colour");
            Color alarmChevron = cone.FacingFill;
            Assert.AreEqual(VisionConeView.FacingColor(true, true), alarmChevron, "the dog's chevron while it sees the chair");
            Game.Furniture.Teleport(BehindTheDog, 0f);
            yield return Steps(2);
            yield return null;
            Assert.IsFalse(vision.SeesPlayer, "premise: the chair behind the dog is seen");
            Color calm = cone.Color;
            Assert.AreEqual(VisionConeView.ConeColor(true, false, false), calm, "the dog's calm cone");
            Color calmChevron = cone.FacingFill;
            Assert.AreEqual(VisionConeView.FacingColor(true, false), calmChevron, "the dog's calm chevron");
            // CONTRACT_M5 17: the calm fan is the cyan Tuning.DogConeColor, the alarm fan the vivid Tuning.DogConeAlarmColor,
            // more opaque; the chevron changes with it (ModelM5Tests measures how far apart they are over the floors).
            Assert.IsTrue(Same(calm, Tuning.DogConeColor), $"the dog's calm cone {calm} is not Tuning.DogConeColor");
            Assert.IsTrue(Same(alarm, Tuning.DogConeAlarmColor), $"the dog's alarm cone {alarm} is not Tuning.DogConeAlarmColor");
            Assert.AreEqual(Tuning.DogConeCalmAlpha, calm.a, 1e-4f, "the dog's calm cone alpha");
            Assert.AreEqual(Tuning.DogConeAlarmAlpha, alarm.a, 1e-4f, "the dog's alarm cone alpha");
            Assert.Greater(alarm.a, calm.a, "seeing the chair does not deepen the dog's cone");
            Assert.IsFalse(Same(alarmChevron, calmChevron), "the dog's chevron does not change when it sees the chair");
            Color human = VisionConeView.ConeColor(false, false, false);
            Assert.IsFalse(Same(human, calm), "control: a human's cone has the dog's colour");
            Assert.IsFalse(Same(VisionConeView.ConeColor(false, true, false), alarm), "control: a human's alarm has the dog's colour");
            CollectionAssert.IsEmpty(logged, "no error logged");
        }
    }

    /// <summary>Runs a callback in a LateUpdate after every other one (the rendered pose).</summary>
    [DefaultExecutionOrder(32000)]
    public sealed class WatchersFrameProbe : MonoBehaviour
    {
        public Action Late;

        private void LateUpdate()
        {
            Late?.Invoke();
        }
    }
}
