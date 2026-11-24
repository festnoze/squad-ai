using System.Collections.Generic;
using System.IO;
using System.Linq;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M5 watchers, EditMode (docs/CONTRACT_M5.md 3 and 16.11, CONTRACT_M5_v3.md 15.5): the catalog's character kinds, eye
    /// targets and pet clip map, the personalities' models and tints, the budgets of every character, and the character
    /// palette (8 shared colours plus one tint per personality; the default man of levels 1 to 7 keeps his M4 colours).
    /// M5B: the merged character slots against a count made from the catalog alone, and the robot's and the loads' meshes
    /// facing outward. The catalog is read from Resources (built by ModelCatalogBuilder at every SetupAndCompile).
    /// </summary>
    public sealed class ModelM5Tests
    {
        private static readonly string[] Humans =
        {
            ModelCatalog.QuaterniusMan, ModelCatalog.QuaterniusWoman, ModelCatalog.QuaterniusManShorts, ModelCatalog.QuaterniusManSuit,
            ModelCatalog.QuaterniusManTshirt, ModelCatalog.QuaterniusWomanJacket, ModelCatalog.QuaterniusWomanDress,
        };

        private static ModelCatalog Catalog()
        {
            ModelCatalog catalog = ModelCatalog.Load();
            Assert.IsNotNull(catalog, "premise: Resources/ModelCatalog is missing (run Builder.SetupAndCompile)");
            return catalog;
        }

        private static ModelCatalog.Entry Entry(string id)
        {
            ModelCatalog.Entry e = Catalog().Find(id);
            Assert.IsNotNull(e, "the catalog does not resolve " + id);
            Assert.IsNotNull(e.prefab, id + ": no prefab");
            return e;
        }

        private static SkinnedMeshRenderer Skin(ModelCatalog.Entry e)
        {
            SkinnedMeshRenderer skin = e.prefab.GetComponentInChildren<SkinnedMeshRenderer>(true);
            Assert.IsNotNull(skin, e.id + ": no skinned mesh");
            return skin;
        }

        /// <summary>The source materials of a character, with their glTF colour (sRGB).</summary>
        private static List<(string name, Color color)> Sources(ModelCatalog.Entry e)
        {
            var list = new List<(string, Color)>();
            foreach (Material m in Skin(e).sharedMaterials)
            {
                Color? c = ModelKit.SourceColor(m);
                Assert.IsTrue(c.HasValue, $"{e.id}: material {m.name} has no base colour");
                list.Add((m.name, c.Value));
            }
            Assert.Greater(list.Count, 2, e.id + ": premise: few source materials");
            return list;
        }

        private static Color Tint(PersonalityDef p)
        {
            Assert.IsTrue(ColorUtility.TryParseHtmlString(p.Tint, out Color c), $"{p.Id}: tint '{p.Tint}' does not parse");
            return new Color(c.r, c.g, c.b, 1f);
        }

        private static bool Same(Color a, Color b)
        {
            Color32 x = a;
            Color32 y = b;
            return x.r == y.r && x.g == y.g && x.b == y.b;
        }

        private static bool InPalette(Color c) => Tuning.CharacterPalette.Any(p => Same(p, c));

        private static IEnumerable<string> People => PersonalityDef.All.Where(id => id != PersonalityDef.Default);

        // ----- The catalog -----

        [Test]
        public void Catalog_kinds_eye_targets_and_the_pet_clip_map()
        {
            foreach (string id in Humans)
            {
                ModelCatalog.Entry e = Entry(id);
                Assert.IsTrue(e.rigged, id + ": rigged");
                Assert.AreEqual(ModelCatalog.KindHuman, e.kind, id + ": kind");
                Assert.IsTrue(e.IsHuman && !e.IsPet, id);
                Assert.AreEqual(0f, e.targetEyeHeight, id + ": a human's target is the default one");
                Assert.AreEqual(Tuning.EyeHeight, e.TargetEye, id + ": a human's eyes at Tuning.EyeHeight");
                Assert.IsTrue(string.IsNullOrEmpty(e.idleClip) && string.IsNullOrEmpty(e.walkClip), id + ": a human finds its clips by suffix");
                Assert.Greater(e.eyeHeight, 0f, id + ": no measured eye height");
            }
            ModelCatalog.Entry dog = Entry(ModelCatalog.QuaterniusHusky);
            Assert.IsTrue(dog.rigged, "the Husky is rigged");
            Assert.AreEqual(ModelCatalog.KindPet, dog.kind, "the Husky is a pet");
            Assert.IsTrue(dog.IsPet && !dog.IsHuman);
            // DOGBIG: the model is fitted bigger than the gameplay eye (Tuning.DogEyeHeight stays the routine's).
            Assert.AreEqual(Tuning.DogModelEyeHeight, dog.targetEyeHeight, 1e-6f, "the dog's eyes are fitted at Tuning.DogModelEyeHeight");
            Assert.AreEqual(Tuning.DogModelEyeHeight, dog.TargetEye, 1e-6f);
            Assert.AreEqual(Tuning.DogEyeHeight * Tuning.DogModelScale, Tuning.DogModelEyeHeight, 1e-6f, "the model eye is the gameplay eye times the model scale");
            Assert.AreEqual("Idle", dog.idleClip, "the pet clip map's Idle");
            Assert.AreEqual("Walk", dog.walkClip, "the pet clip map's Walk");
            Assert.AreEqual("Head", dog.headBone, "the Husky's head bone");
            Assert.AreNotEqual(Vector3.zero, dog.eyeLocal, "the Husky's eyes were not found");
            Animation anim = dog.prefab.GetComponentInChildren<Animation>(true);
            Assert.IsNotNull(anim, "premise: the Husky has an Animation");
            var clips = new List<string>();
            foreach (AnimationState s in anim)
            {
                clips.Add(s.name);
            }
            CollectionAssert.Contains(clips, dog.idleClip, "the Husky's Idle clip is missing");
            CollectionAssert.Contains(clips, dog.walkClip, "the Husky's Walk clip is missing");
            foreach (string id in ModelCatalog.Ids.Where(i => i.StartsWith("kenney.", System.StringComparison.Ordinal)))
            {
                ModelCatalog.Entry e = Entry(id);
                Assert.IsFalse(e.rigged, id);
                Assert.IsFalse(e.IsHuman || e.IsPet, id + ": a static model is no character");
            }
            CollectionAssert.IsSubsetOf(Humans.Concat(new[] { ModelCatalog.QuaterniusHusky }), ModelCatalog.Ids, "every character is a required id");
        }

        [Test]
        public void The_dog_is_fitted_with_its_eyes_at_the_dog_eye_and_the_humans_at_theirs()
        {
            ModelCatalog.Entry dog = Entry(ModelCatalog.QuaterniusHusky);
            float dogEyes = ModelKit.RiggedScale(dog) * dog.eyeHeight;
            Assert.That(dogEyes, Is.EqualTo(Tuning.DogModelEyeHeight).Within(1e-4f), $"the fitted dog's eyes stand at {dogEyes:0.###} m");
            foreach (string id in Humans)
            {
                ModelCatalog.Entry e = Entry(id);
                Assert.That(ModelKit.RiggedScale(e) * e.eyeHeight, Is.EqualTo(Tuning.EyeHeight).Within(1e-4f), id);
            }
            // DOGBIG: the fitted dog is a big dog (it was a 0.4 m Shiba): about 0.6 m tall at the ears (its native height
            // times the same scale), at most 0.8 m from snout to tail, its snout about 0.47 m ahead of its root.
            float height = ModelKit.RiggedScale(dog) * dog.nativeSize.y;
            Assert.That(height, Is.InRange(0.55f, 0.75f), $"the fitted dog is {height:0.00} m tall");
            float length = ModelKit.RiggedScale(dog) * dog.nativeSize.z;
            Assert.That(length, Is.InRange(0.6f, 0.85f), $"the fitted dog is {length:0.00} m long");
            Assert.That(ModelKit.ForwardReach(dog), Is.InRange(0.4f, 0.55f), "the fitted dog's snout reach");
        }

        [Test]
        public void Every_character_is_within_its_budget()
        {
            foreach (string id in Humans.Concat(new[] { ModelCatalog.QuaterniusHusky }))
            {
                ModelCatalog.Entry e = Entry(id);
                SkinnedMeshRenderer skin = Skin(e);
                int bones = skin.bones.Where(b => b != null).Distinct().Count();
                long triangles = ModelKit.Triangles(skin.sharedMesh);
                int budget = e.IsPet ? Tuning.BudgetPetBones : Tuning.BudgetInhabitantBones;
                Assert.Greater(bones, 0, id + ": premise: no bones");
                Assert.LessOrEqual(bones, budget, $"{id}: {bones} bones");
                Assert.LessOrEqual(triangles, Tuning.BudgetInhabitantTriangles, $"{id}: {triangles} triangles");
                if (e.IsPet)
                {
                    Assert.Greater(bones, Tuning.BudgetInhabitantBones, "premise: the Husky needs the pet bone budget");
                }
            }
        }

        // ----- The personalities -----

        [Test]
        public void Every_personality_has_its_own_model_of_its_kind_and_its_own_tint()
        {
            var models = new HashSet<string>();
            var tints = new List<Color>();
            foreach (string id in People)
            {
                PersonalityDef p = PersonalityDef.For(id);
                ModelCatalog.Entry e = Entry(p.Model);
                Assert.AreEqual(id == PersonalityDef.Dog ? ModelCatalog.KindPet : ModelCatalog.KindHuman, e.kind, $"{id}: {p.Model}");
                Assert.IsTrue(models.Add(p.Model), $"{id}: model {p.Model} is another personality's");
                Color tint = Tint(p);
                Assert.IsFalse(tints.Any(t => Same(t, tint)), $"{id}: tint {p.Tint} is another personality's");
                Assert.IsFalse(ModelMath.IsRed(tint), $"{id}: tint {p.Tint} is red (PRD 7.2)");
                Assert.IsFalse(ModelMath.IsNearBlack(tint), $"{id}: tint {p.Tint} is a near-black (it would merge into the eyes)");
                Assert.IsFalse(InPalette(tint), $"{id}: tint {p.Tint} is a shared palette colour");
                tints.Add(tint);
            }
            Assert.AreEqual(7, models.Count, "premise: six personalities and the dog");
            PersonalityDef def = PersonalityDef.For(PersonalityDef.Default);
            Assert.IsNull(def.Model, "the default row names no model (levels 1 to 7 name theirs)");
            Assert.IsNull(def.Tint, "the default row has no tint (levels 1 to 7 keep their model's clothes)");
            // The inhabitant's view of it: the personality's model and tint, an explicit model or body colour winning,
            // and no tint for a default inhabitant whatever its body colour.
            Assert.AreEqual(ModelCatalog.QuaterniusWomanDress, Inhabitant.ModelIdOf(new InhabitantDef { Personality = PersonalityDef.Granny }));
            Assert.AreEqual(ModelCatalog.QuaterniusWomanDress, Inhabitant.ModelIdOf(new InhabitantDef { Personality = PersonalityDef.Watchful }));
            Assert.AreEqual(ModelCatalog.QuaterniusWomanDress, Inhabitant.ModelIdOf(new InhabitantDef { Personality = PersonalityDef.Tidy }));
            Assert.AreEqual(ModelCatalog.QuaterniusWomanDress, Inhabitant.ModelIdOf(new InhabitantDef { Model = ModelCatalog.QuaterniusWomanJacket }));
            Assert.AreEqual(ModelCatalog.QuaterniusWomanDress, Inhabitant.ModelIdOf(new InhabitantDef { Model = ModelCatalog.QuaterniusWoman }));
            Assert.AreEqual(ModelCatalog.QuaterniusHusky, Inhabitant.ModelIdOf(new InhabitantDef { Kind = PersonalityDef.Dog }));
            Assert.AreEqual(ModelCatalog.QuaterniusMan, Inhabitant.ModelIdOf(new InhabitantDef { Personality = PersonalityDef.Teen, Model = "quaternius.man" }));
            Assert.IsNull(Inhabitant.ModelIdOf(new InhabitantDef()), "a default inhabitant naming no model keeps the procedural body");
            Assert.IsTrue(Same(Tint(PersonalityDef.For(PersonalityDef.Teen)), Inhabitant.TintOf(new InhabitantDef { Personality = PersonalityDef.Teen }).Value));
            Assert.IsTrue(Same(new Color32(0x12, 0x34, 0x56, 0xFF),
                Inhabitant.TintOf(new InhabitantDef { Personality = PersonalityDef.Teen, BodyColor = "#123456" }).Value), "an explicit body colour wins");
            Assert.IsNull(Inhabitant.TintOf(new InhabitantDef { BodyColor = "#2F6E4E", Model = "quaternius.man" }), "a default inhabitant takes no tint");
        }

        // ----- Identity against the house and each other (CONTRACT_M5 17, wave 5A critique m18 and m19) -----

        private const string LevelFolder = "Assets/Resources/Levels/";

        /// <summary>
        /// CIE76 distance the dog's tint keeps from every floor it walks on. The 5A Shiba orange #C07A3A was 14 from the
        /// #B07A4E wood: the dog vanished into the floor.
        /// </summary>
        private const float DogFloorDeltaE = 30f;

        /// <summary>Degrees of hue between two women's tints: another hue family, not a lighter or darker shade of one.</summary>
        private const float WomenHueGap = 90f;

        /// <summary>CIE76 distance between the dog's calm and alarm chevrons, and from each human chevron (yellow to red: 77).</summary>
        private const float DogChevronDeltaE = 40f;

        /// <summary>The darker border of a carpet room (LevelBuilder.BuildFloors draws it at the floor colour times this).</summary>
        private const float CarpetBorderShade = 0.82f;

        private static Color Hex(string hex)
        {
            Assert.IsTrue(ColorUtility.TryParseHtmlString(hex, out Color c), $"'{hex}' does not parse");
            return new Color(c.r, c.g, c.b, 1f);
        }

        private static Color Linear(Color srgb) =>
            new Color(ModelMath.ToLinear(srgb.r), ModelMath.ToLinear(srgb.g), ModelMath.ToLinear(srgb.b), 1f);

        /// <summary>CIE L*a*b* (D65 white) of a linear RGB colour.</summary>
        private static Vector3 Lab(Color linear)
        {
            float x = (0.4124f * linear.r + 0.3576f * linear.g + 0.1805f * linear.b) / 0.95047f;
            float y = 0.2126f * linear.r + 0.7152f * linear.g + 0.0722f * linear.b;
            float z = (0.0193f * linear.r + 0.1192f * linear.g + 0.9505f * linear.b) / 1.08883f;
            float fx = LabF(x);
            float fy = LabF(y);
            float fz = LabF(z);
            return new Vector3(116f * fy - 16f, 500f * (fx - fy), 200f * (fy - fz));
        }

        private static float LabF(float t) => t > 0.008856f ? Mathf.Pow(t, 1f / 3f) : 7.787f * t + 16f / 116f;

        /// <summary>The CIE76 distance between two opaque sRGB colours.</summary>
        private static float DeltaE(Color a, Color b) => Vector3.Distance(Lab(Linear(a)), Lab(Linear(b)));

        /// <summary>A transparent fan (sRGB, its alpha) over an opaque sRGB floor, blended in linear space as URP does.</summary>
        private static Color Over(Color fan, Color floor) => Color.LerpUnclamped(Linear(floor), Linear(fan), fan.a);

        /// <summary>The CIE76 distance between two fans as they show over a floor.</summary>
        private static float FanDeltaE(Color a, Color b, Color floor) => Vector3.Distance(Lab(Over(a, floor)), Lab(Over(b, floor)));

        private static float HueGap(Color a, Color b)
        {
            Color.RGBToHSV(a, out float ha, out _, out _);
            Color.RGBToHSV(b, out float hb, out _, out _);
            float d = Mathf.Abs(ha - hb) * 360f;
            return Mathf.Min(d, 360f - d);
        }

        /// <summary>
        /// Every floor colour (opaque sRGB) of the shipped levels where a dog walks: each room's floor, and a carpet room's
        /// darker border. <paramref name="levels"/> counts those levels.
        /// </summary>
        private static List<(string where, Color colour)> DogFloors(out int levels)
        {
            var floors = new List<(string, Color)>();
            levels = 0;
            foreach (string id in LevelManifest.Parse(File.ReadAllText(LevelFolder + LevelManifest.FileName + ".json")))
            {
                LevelDef def = LevelJson.Parse(File.ReadAllText(LevelFolder + id + ".json"));
                if (def.Inhabitants == null || !def.Inhabitants.Any(i => i != null && i.Kind == PersonalityDef.Dog))
                {
                    continue;
                }
                levels++;
                foreach (RoomDef room in def.AllRooms())
                {
                    Color c = LevelJson.ParseColor(room.FloorColor, Color.gray);
                    floors.Add(($"{id} {room.Id}", new Color(c.r, c.g, c.b, 1f)));
                    if (room.IsSoft)
                    {
                        floors.Add(($"{id} {room.Id} (carpet border)",
                            new Color(c.r * CarpetBorderShade, c.g * CarpetBorderShade, c.b * CarpetBorderShade, 1f)));
                    }
                }
            }
            return floors;
        }

        /// <summary>The dog's tint stands out from every floor of every shipped level with a dog (critique m19).</summary>
        [Test]
        public void The_dog_stands_out_from_every_floor_it_walks_on()
        {
            PersonalityDef row = PersonalityDef.For(PersonalityDef.Dog);
            Color dog = Tint(row);
            List<(string where, Color colour)> floors = DogFloors(out int levels);
            Assert.GreaterOrEqual(levels, 2, "premise: levels 12 and 16 have a dog");
            Assert.GreaterOrEqual(floors.Count, 8, "premise: the dog's houses have their room floors");
            // Control: the measure fails the 5A orange dog on the wood floor.
            Assert.Less(DeltaE(Hex("#C07A3A"), Hex("#B07A4E")), DogFloorDeltaE, "control: the 5A orange dog passes on the wood floor");
            foreach ((string where, Color floor) in floors)
            {
                float d = DeltaE(dog, floor);
                Assert.GreaterOrEqual(d, DogFloorDeltaE,
                    $"the dog's tint {row.Tint} is {d:0.0} from the floor of {where} (#{ColorUtility.ToHtmlStringRGB(floor)})");
            }
        }

        /// <summary>
        /// DOGBIG (black Labrador): once the dog's fur map ships, its mean colour (the map's pixels averaged in linear light:
        /// the atlas is fur wherever no triangle maps, so this is the dog's mean within a unit) stands out from every floor of
        /// every shipped level with a dog, as its tint must (offline, v3 with its strands lifted: #3E3C3C, 36.5 from the nearest, the carpet borders).
        /// </summary>
        [Test]
        public void The_dog_fur_map_stands_out_from_every_floor_it_walks_on()
        {
            const string path = "Assets/Art/Characters/Resources/" + Tuning.DogFurTextureResource + ".png";
            if (!File.Exists(path))
            {
                Assert.Ignore("no dog fur map: the dog shows its tint (checked above)");
            }
            var map = new Texture2D(2, 2);
            try
            {
                Assert.IsTrue(map.LoadImage(File.ReadAllBytes(path)), "the fur map does not decode");
                Color[] pixels = map.GetPixels();
                var sum = Vector3.zero;
                foreach (Color p in pixels)
                {
                    Color l = Linear(p);
                    sum += new Vector3(l.r, l.g, l.b);
                }
                sum /= pixels.Length;
                var mean = new Color(Mathf.LinearToGammaSpace(sum.x), Mathf.LinearToGammaSpace(sum.y), Mathf.LinearToGammaSpace(sum.z), 1f);
                foreach ((string where, Color floor) in DogFloors(out _))
                {
                    float d = DeltaE(mean, floor);
                    Assert.GreaterOrEqual(d, DogFloorDeltaE,
                        $"the dog's fur (mean #{ColorUtility.ToHtmlStringRGB(mean)}) is {d:0.0} from the floor of {where} (#{ColorUtility.ToHtmlStringRGB(floor)})");
                }
            }
            finally
            {
                Object.DestroyImmediate(map);
            }
        }

        /// <summary>
        /// DOGFACE (black Labrador, 2026-11-22: "the brows and the mouth barely show, the open mouth does not read"): on the
        /// fur map, the tan brow marks over the eyes stand out from the forehead's black, and the mouth's inside (the atlas
        /// region the bite's open jaw shows: make_husky.py v5 MOUTH_REGION 0.60, 0.62, 0.30 x 0.14, painted by
        /// compose_dogfur.py) is a pink far from the coat. Offline: brows L* 34 against the forehead's 22 (dE 14.7), the
        /// tongue #AE5B67 (dE about 40 from the coat's mean).
        /// </summary>
        [Test]
        public void The_dog_face_marks_and_mouth_inside_read_against_its_black_fur()
        {
            const string path = "Assets/Art/Characters/Resources/" + Tuning.DogFurTextureResource + ".png";
            if (!File.Exists(path))
            {
                Assert.Ignore("no dog fur map: the dog shows its tint");
            }
            var map = new Texture2D(2, 2);
            try
            {
                Assert.IsTrue(map.LoadImage(File.ReadAllBytes(path)), "the fur map does not decode");
                // Atlas UVs from the image's top left (glTF), averaged over 7 x 7 pixels.
                Color At(float u, float v)
                {
                    int cx = Mathf.RoundToInt(u * map.width), cy = map.height - 1 - Mathf.RoundToInt(v * map.height);
                    Color sum = Color.clear;
                    for (int dy = -3; dy <= 3; dy++)
                    {
                        for (int dx = -3; dx <= 3; dx++)
                        {
                            sum += map.GetPixel(cx + dx, cy + dy);
                        }
                    }
                    return sum / 49f;
                }
                Color[] pixels = map.GetPixels();
                var lin = Vector3.zero;
                foreach (Color p in pixels)
                {
                    Color l = Linear(p);
                    lin += new Vector3(l.r, l.g, l.b);
                }
                lin /= pixels.Length;
                var coat = new Color(Mathf.LinearToGammaSpace(lin.x), Mathf.LinearToGammaSpace(lin.y), Mathf.LinearToGammaSpace(lin.z), 1f);
                Color forehead = At(0.7634f, 0.1221f);
                foreach (float u in new[] { 0.6969f, 0.8298f })
                {
                    Color brow = At(u, 0.1517f);
                    Assert.Greater(brow.grayscale, forehead.grayscale, $"the brow at u {u} is not lighter than the forehead");
                    Assert.GreaterOrEqual(DeltaE(brow, forehead), 10f,
                        $"the brow at u {u} (#{ColorUtility.ToHtmlStringRGB(brow)}) does not stand out from the forehead (#{ColorUtility.ToHtmlStringRGB(forehead)})");
                }
                Color tongue = At(0.60f + 0.30f * 0.5f, 0.62f + 0.14f * 0.8f);
                Color palate = At(0.60f + 0.30f * 0.5f, 0.62f + 0.14f * 0.1f);
                Assert.GreaterOrEqual(DeltaE(tongue, coat), 30f,
                    $"the tongue (#{ColorUtility.ToHtmlStringRGB(tongue)}) does not stand out from the coat (#{ColorUtility.ToHtmlStringRGB(coat)})");
                Assert.Greater(tongue.r - tongue.g, 0.2f, $"the tongue (#{ColorUtility.ToHtmlStringRGB(tongue)}) is not pink");
                Assert.Greater(palate.r - palate.g, 0.1f, $"the mouth's inside (#{ColorUtility.ToHtmlStringRGB(palate)}) is not a dark red");
            }
            finally
            {
                Object.DestroyImmediate(map);
            }
        }

        /// <summary>
        /// Two women (granny and tidy share level 14) wear tints of different hue families, so the player tells "Mamie" from
        /// "la maniaque" at a glance (critique m19).
        /// </summary>
        [Test]
        public void Two_women_never_share_a_hue_family()
        {
            List<PersonalityDef> women = People.Select(PersonalityDef.For)
                .Where(p => p.Model.StartsWith(ModelCatalog.QuaterniusWoman, System.StringComparison.Ordinal)).ToList();
            CollectionAssert.AreEquivalent(new[] { PersonalityDef.Watchful, PersonalityDef.Granny, PersonalityDef.Tidy }, women.Select(p => p.Id),
                "premise: the watchful, granny and tidy rows are the women");
            // Control: the 5A pink of tidy is a shade of granny's lavender family.
            Assert.Less(HueGap(Hex("#E58FB5"), Tint(PersonalityDef.For(PersonalityDef.Granny))), WomenHueGap, "control: 5A tidy pink vs granny");
            for (int a = 0; a < women.Count; a++)
            {
                for (int b = a + 1; b < women.Count; b++)
                {
                    float gap = HueGap(Tint(women[a]), Tint(women[b]));
                    Assert.GreaterOrEqual(gap, WomenHueGap,
                        $"{women[a].Id} ({women[a].Tint}) and {women[b].Id} ({women[b].Tint}) are only {gap:0} deg of hue apart");
                }
            }
        }

        /// <summary>
        /// The dog's cone (CONTRACT_M5 17): cyan, its alarm the vivid Tuning.DogConeAlarmColor. Over every floor of a level with
        /// a dog, lit or dark, its alarm fan stands at least as far from its calm fan as a human's red from its yellow, each dog
        /// fan stands that far from the human fan of the other state, and its chevron changes as clearly (critique m18).
        /// </summary>
        [Test]
        public void The_dog_alarm_cone_is_as_distinct_from_its_calm_as_a_human_s()
        {
            Color dogCalm = VisionConeView.ConeColor(true, false, false);
            Color dogAlarm = VisionConeView.ConeColor(true, true, false);
            Assert.IsTrue(Same(dogCalm, Tuning.DogConeColor), "the dog's calm fan is Tuning.DogConeColor");
            Assert.IsTrue(Same(dogAlarm, Tuning.DogConeAlarmColor), "the dog's alarm fan is Tuning.DogConeAlarmColor");
            Assert.AreEqual(Tuning.DogConeCalmAlpha, dogCalm.a, 1e-6f);
            Assert.AreEqual(Tuning.DogConeAlarmAlpha, dogAlarm.a, 1e-6f);
            foreach (Color c in new[] { Tuning.DogConeColor, Tuning.DogConeAlarmColor })
            {
                Color.RGBToHSV(c, out float h, out float s, out _);
                Assert.That(h * 360f, Is.InRange(165f, 200f), $"the dog's cone {c} is not a cyan");
                Assert.Greater(s, 0.5f, $"the dog's cone {c} is greyish");
            }
            List<(string where, Color colour)> floors = DogFloors(out _);
            Assert.Greater(floors.Count, 0, "premise: no floor under a dog");
            // Control: the 5A alarm (the calm colour, only more opaque) does not pass over the wood floor.
            Color wood = Hex("#B07A4E");
            Color alphaOnly = new Color(dogCalm.r, dogCalm.g, dogCalm.b, 0.36f);
            Assert.Less(FanDeltaE(alphaOnly, dogCalm, wood), FanDeltaE(VisionConeView.ConeColor(false, true, false), VisionConeView.ConeColor(false, false, false), wood),
                "control: an alarm that only deepens the calm fan passes");
            foreach (bool dark in new[] { false, true })
            {
                Color calm = VisionConeView.ConeColor(true, false, dark);
                Color alarm = VisionConeView.ConeColor(true, true, dark);
                Color humanCalm = VisionConeView.ConeColor(false, false, dark);
                Color humanAlarm = VisionConeView.ConeColor(false, true, dark);
                string lamp = dark ? "dark" : "lit";
                foreach ((string where, Color floor) in floors)
                {
                    float human = FanDeltaE(humanAlarm, humanCalm, floor);
                    Assert.Greater(human, 5f, $"premise: a human's {lamp} alarm hardly shows over {where}");
                    float dog = FanDeltaE(alarm, calm, floor);
                    Assert.GreaterOrEqual(dog, human, $"{lamp} over {where}: the dog's alarm is {dog:0.0} from its calm fan, a human's {human:0.0}");
                    if (!dark)
                    {
                        float calmToHuman = FanDeltaE(calm, humanAlarm, floor);
                        float alarmToHuman = FanDeltaE(alarm, humanCalm, floor);
                        Assert.GreaterOrEqual(calmToHuman, human, $"over {where}: the dog's calm fan is {calmToHuman:0.0} from a human's alarm");
                        Assert.GreaterOrEqual(alarmToHuman, human, $"over {where}: the dog's alarm fan is {alarmToHuman:0.0} from a human's calm");
                    }
                }
            }
            Color chevronCalm = VisionConeView.FacingColor(true, false);
            Color chevronAlarm = VisionConeView.FacingColor(true, true);
            Assert.GreaterOrEqual(DeltaE(chevronAlarm, chevronCalm), DogChevronDeltaE, "the dog's chevron hardly changes when it sees the chair");
            foreach (Color human in new[] { VisionConeView.FacingColor(false, false), VisionConeView.FacingColor(false, true) })
            {
                Assert.GreaterOrEqual(DeltaE(chevronCalm, human), DogChevronDeltaE, $"the dog's calm chevron is close to a human's {human}");
                Assert.GreaterOrEqual(DeltaE(chevronAlarm, human), DogChevronDeltaE, $"the dog's alarm chevron is close to a human's {human}");
            }
        }

        // ----- The character palette (CONTRACT_M5 16.11) -----

        [Test]
        public void The_palette_has_eight_shared_colours_none_red()
        {
            Color[] palette = Tuning.CharacterPalette;
            Assert.AreEqual(8, palette.Length, "8 shared colours");
            for (int i = 0; i < palette.Length; i++)
            {
                Assert.IsFalse(ModelMath.IsRed(palette[i]), $"palette {i} is red");
                Assert.AreEqual(ModelMath.Quantize(palette[i]), palette[i], $"palette {i} is off the 1/64 grid");
                for (int j = 0; j < i; j++)
                {
                    Assert.IsFalse(Same(palette[i], palette[j]), $"palette {i} and {j} are the same colour");
                }
            }
            Assert.AreEqual(ModelMath.NearBlack, palette[0], "palette 0 is the near-black");
        }

        [Test]
        public void Every_character_maps_onto_the_palette_plus_its_tint()
        {
            foreach (string id in People)
            {
                PersonalityDef p = PersonalityDef.For(id);
                ModelCatalog.Entry e = Entry(p.Model);
                Color tint = Tint(p);
                int clothes = 0;
                foreach ((string name, Color source) in Sources(e))
                {
                    Color c = ModelKit.CharacterColor(name, source, e.IsPet, tint);
                    if (ModelKit.PartOf(name, e.IsPet) == ModelKit.CharacterPart.Clothes)
                    {
                        clothes++;
                        Assert.AreEqual(tint, c, $"{id}: the clothes ({name}) are not the tint");
                    }
                    else
                    {
                        Assert.IsTrue(InPalette(c), $"{id}: {name} maps to {c}, not a palette colour");
                    }
                    Assert.IsFalse(ModelMath.IsRed(c), $"{id}: {name} maps to a red");
                    if (ModelKit.PartOf(name, e.IsPet) == ModelKit.CharacterPart.Skin)
                    {
                        Assert.IsTrue(Same(c, Tuning.CharacterPalette[1]) || Same(c, Tuning.CharacterPalette[2]), $"{id}: the skin took {c}, not a skin tone");
                    }
                }
                Assert.Greater(clothes, 0, $"{id}: premise: {p.Model} has no clothes slot to tint");
            }
        }

        [Test]
        public void Three_humans_and_a_dog_add_at_most_twelve_materials()
        {
            var colours = new Dictionary<string, HashSet<Color32>>();
            foreach (string id in People)
            {
                PersonalityDef p = PersonalityDef.For(id);
                ModelCatalog.Entry e = Entry(p.Model);
                Color tint = Tint(p);
                colours[id] = new HashSet<Color32>(Sources(e).Select(s => (Color32)ModelKit.CharacterColor(s.name, s.color, e.IsPet, tint)));
            }
            string[] humans = colours.Keys.Where(k => k != PersonalityDef.Dog).ToArray();
            Assert.AreEqual(6, humans.Length, "premise: six human personalities");
            int worst = 0;
            int sets = 0;
            for (int a = 0; a < humans.Length; a++)
            {
                for (int b = a + 1; b < humans.Length; b++)
                {
                    for (int c = b + 1; c < humans.Length; c++)
                    {
                        var set = new HashSet<Color32>(colours[humans[a]]);
                        set.UnionWith(colours[humans[b]]);
                        set.UnionWith(colours[humans[c]]);
                        set.UnionWith(colours[PersonalityDef.Dog]);
                        worst = Mathf.Max(worst, set.Count);
                        sets++;
                    }
                }
            }
            Assert.AreEqual(20, sets, "premise: every set of three humans");
            Assert.LessOrEqual(worst, 12, $"three humans and a dog use {worst} colours");
            var all = new HashSet<Color32>(colours.Values.SelectMany(c => c));
            Assert.LessOrEqual(all.Count, Tuning.CharacterPalette.Length + colours.Count, "more than 8 shared colours plus the tints");
        }

        /// <summary>
        /// Levels 1 to 7 name the M3 man with the default personality: with no tint, every slot keeps exactly the colour M4
        /// gave it (ModelMath.MapColor), so those levels look and count materials as before.
        /// </summary>
        [Test]
        public void The_default_man_keeps_his_M4_colours()
        {
            ModelCatalog.Entry man = Entry(ModelCatalog.QuaterniusMan);
            List<(string name, Color color)> sources = Sources(man);
            SkinnedMeshRenderer skin = Skin(man);
            var triangles = new List<long>();
            for (int i = 0; i < sources.Count; i++)
            {
                triangles.Add(i < skin.sharedMesh.subMeshCount ? skin.sharedMesh.GetIndexCount(i) / 3 : 0);
            }
            int main = ModelMath.IndexOfMax(triangles);
            float redReference = ModelMath.RedReference(sources.Select(s => s.color));
            int shared = 0;
            for (int i = 0; i < sources.Count; i++)
            {
                Color m4 = ModelMath.MapColor(sources[i].color, i == main, redReference, default);
                Color m5 = ModelKit.CharacterColor(sources[i].name, sources[i].color, false, null, redReference);
                Assert.AreEqual(m4, m5, $"the man's {sources[i].name} changed colour without a tint");
                shared += InPalette(m5) ? 1 : 0;
            }
            Assert.GreaterOrEqual(shared, sources.Count - 1, "premise: all but the man's shirt are shared palette colours");
        }

        // ----- M5B: the robot and the load visuals -----

        /// <summary>
        /// Every triangle of the robot's and of every load's meshes (carried and broken) faces its own normals (Unity draws
        /// the side where cross(b - a, c - a) points; a reversed face would vanish), and their UVs are in metres (the
        /// detail is measurable).
        /// </summary>
        [Test]
        public void Robot_and_load_meshes_face_outward()
        {
            var root = new GameObject("VisualsTest");
            try
            {
                var furniture = new GameObject("Furniture");
                furniture.transform.SetParent(root.transform, false);
                var meshes = new List<Mesh>();
                foreach (string kind in LoadView.Kinds)
                {
                    LoadView view = LoadView.Create(kind, furniture.transform, new Vector3(0.45f, 0.9f, 0.45f));
                    Assert.IsNotNull(view, kind);
                    view.SpawnClue(new Vector3(1f, 0f, 0f));
                    meshes.AddRange(view.GetComponentsInChildren<MeshFilter>(true).Select(f => f.sharedMesh));
                    meshes.AddRange(view.Clue.GetComponentsInChildren<MeshFilter>(true).Select(f => f.sharedMesh));
                    Object.DestroyImmediate(view.Clue);
                }
                Robot robot = Robot.Create(new RobotDef { Loop = new List<PointDef> { new PointDef(), new PointDef { X = 1f } } }, root.transform);
                meshes.AddRange(robot.GetComponentsInChildren<MeshFilter>(true).Select(f => f.sharedMesh));
                Assert.GreaterOrEqual(meshes.Count, 12, "premise: the visuals' meshes");
                foreach (Mesh m in meshes.Distinct())
                {
                    Vector3[] v = m.vertices;
                    Vector3[] n = m.normals;
                    int[] t = m.triangles;
                    Assert.Greater(t.Length, 0, m.name + ": no triangle");
                    Assert.AreEqual(v.Length, m.uv.Length, m.name + ": no UVs");
                    int backwards = 0;
                    for (int i = 0; i + 2 < t.Length; i += 3)
                    {
                        Vector3 face = Vector3.Cross(v[t[i + 1]] - v[t[i]], v[t[i + 2]] - v[t[i]]);
                        Vector3 normal = n[t[i]] + n[t[i + 1]] + n[t[i + 2]];
                        if (face.sqrMagnitude > 1e-14f && Vector3.Dot(face, normal) <= 0f)
                        {
                            backwards++;
                        }
                    }
                    Assert.AreEqual(0, backwards, m.name + ": faces turned away from their normals");
                }
            }
            finally
            {
                Object.DestroyImmediate(root);
            }
        }
    }
}
