using System.Collections.Generic;
using NUnit.Framework;
using OutOfSight.Core;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Stars (idea 5, docs/next/progress/STARS.md): the count against the audit's exit (three at or under the reference
    /// times 1.5, two under 2.5, one otherwise; a level with no route gives three), the reference per difficulty (the
    /// hard route at Difficile, the normal one otherwise, plus the slack), the save (only up, clamped, per difficulty and
    /// record revision, migration safe: a save without "stars" loads with none, a malformed "stars" never fails it, a round
    /// trip keeps it), the strings in both languages, and the real line-up (every level has a reference at both
    /// difficulties, 20 levels hold 60 stars since the rev 3 line-up, ACT3A).
    /// </summary>
    public sealed class StarsTests
    {
        private static LevelDef Level(float[] normal, float[] hard)
        {
            var def = new LevelDef { Id = "levelX" };
            foreach (float at in normal ?? new float[0])
            {
                def.DesignerRoute.Add(new RouteStepDef { At = at });
            }
            foreach (float at in hard ?? new float[0])
            {
                def.DesignerRouteHard.Add(new RouteStepDef { At = at });
            }
            return def;
        }

        [Test]
        public void Tuning_FactorsAreOrderedAndGenerous()
        {
            Assert.AreEqual(3, Tuning.StarsPerLevel, "premise: three stars per level");
            Assert.Greater(Tuning.StarsThreeFactor, 1f, "three stars must leave room over the solver's own time");
            Assert.Greater(Tuning.StarsTwoFactor, Tuning.StarsThreeFactor, "two stars must be looser than three");
            Assert.GreaterOrEqual(Tuning.StarsReferenceSlack, 0f);
        }

        [Test]
        public void Count_ThreeAtOrUnderOneAndAHalf_TwoUnderTwoAndAHalf_OneOtherwise()
        {
            const float reference = 10f;
            float three = Stars.ThreeStarsUpTo(reference);
            float two = Stars.TwoStarsUnder(reference);
            Assert.AreEqual(15f, three, 1e-4f, "premise: the three star limit is 1.5 x");
            Assert.AreEqual(25f, two, 1e-4f, "premise: the two star limit is 2.5 x");
            Assert.AreEqual(3, Stars.Count(0f, reference));
            Assert.AreEqual(3, Stars.Count(reference, reference));
            Assert.AreEqual(3, Stars.Count(three, reference), "at the limit is still three (MUTATION:STARS_THREE)");
            Assert.AreEqual(2, Stars.Count(three + 0.01f, reference));
            Assert.AreEqual(2, Stars.Count(two - 0.01f, reference));
            Assert.AreEqual(1, Stars.Count(two, reference), "the two star limit is exclusive (MUTATION:STARS_TWO)");
            Assert.AreEqual(1, Stars.Count(1000f, reference));
        }

        [Test]
        public void Count_NoReferenceGivesEveryStar()
        {
            Assert.AreEqual(3, Stars.Count(500f, -1f));
            Assert.AreEqual(3, Stars.Count(500f, 0f));
        }

        [Test]
        public void Reference_LastPointPlusSlack_HardRouteOnlyAtDifficile()
        {
            LevelDef def = Level(new[] { 0f, 5f, 11.6f }, new[] { 0f, 7f, 19f });
            Assert.AreEqual(11.6f + Tuning.StarsReferenceSlack, Stars.Reference(def, DifficultyDef.Normal), 1e-4f);
            Assert.AreEqual(11.6f + Tuning.StarsReferenceSlack, Stars.Reference(def, DifficultyDef.Facile), 1e-4f, "Facile is judged against the normal route");
            Assert.AreEqual(19f + Tuning.StarsReferenceSlack, Stars.Reference(def, DifficultyDef.Difficile), 1e-4f, "MUTATION:STARS_HARD_ROUTE");
            Assert.AreEqual(11.6f + Tuning.StarsReferenceSlack, Stars.Reference(def, null), 1e-4f, "an unknown difficulty is Normal");
        }

        [Test]
        public void Reference_LatestAtWins_NotTheLastListed()
        {
            LevelDef def = Level(new[] { 0f, 12f, 9f }, null);
            Assert.AreEqual(12f + Tuning.StarsReferenceSlack, Stars.Reference(def, DifficultyDef.Normal), 1e-4f);
        }

        [Test]
        public void Reference_DifficileWithoutHardRouteFallsBackToNormal_NoRouteIsNegative()
        {
            LevelDef def = Level(new[] { 0f, 8f }, null);
            Assert.AreEqual(8f + Tuning.StarsReferenceSlack, Stars.Reference(def, DifficultyDef.Difficile), 1e-4f);
            Assert.Less(Stars.Reference(Level(null, null), DifficultyDef.Normal), 0f);
            Assert.Less(Stars.Reference(null, DifficultyDef.Normal), 0f);
            Assert.AreEqual(3, Stars.CountFor(Level(null, null), 999f, DifficultyDef.Normal));
        }

        [Test]
        public void CountFor_Level1Numbers()
        {
            // docs/next/progress/STARS.md: level 1's route ends at 11.6 s, so 3 stars up to 20.4 s and 2 under 34 s.
            LevelDef def = Level(new[] { 0f, 11.6f }, null);
            Assert.AreEqual(3, Stars.CountFor(def, 20.4f, DifficultyDef.Normal));
            Assert.AreEqual(2, Stars.CountFor(def, 20.5f, DifficultyDef.Normal));
            Assert.AreEqual(2, Stars.CountFor(def, 33.9f, DifficultyDef.Normal));
            Assert.AreEqual(1, Stars.CountFor(def, 34f, DifficultyDef.Normal));
        }

        [Test]
        public void Save_RecordStarsOnlyUp_ClampedToThree_PerDifficultyAndRevision()
        {
            var save = new SaveData();
            Assert.AreEqual(0, save.StarsOf("level1", DifficultyDef.Normal), "premise: a fresh save has no stars");
            Assert.AreEqual(2, save.RecordStars("level1", 2, DifficultyDef.Normal));
            Assert.AreEqual(2, save.RecordStars("level1", 1, DifficultyDef.Normal), "a worse win keeps the best (MUTATION:STARS_ONLY_UP)");
            Assert.AreEqual(2, save.StarsOf("level1", DifficultyDef.Normal));
            Assert.AreEqual(3, save.RecordStars("level1", 7, DifficultyDef.Normal), "clamped to three");
            Assert.AreEqual(0, save.RecordStars("level1", -4, DifficultyDef.Facile), "clamped to zero");
            Assert.AreEqual(3, save.StarsOf("level1", DifficultyDef.Normal), "Facile's entry never touches Normal's");
            Assert.AreEqual(0, save.StarsOf("level1", DifficultyDef.Difficile));
            save.RecordStars("level1", 1, DifficultyDef.Difficile);
            Assert.AreEqual(1, save.StarsOf("level1", DifficultyDef.Difficile));
            Assert.IsTrue(save.Stars.ContainsKey("level1") && save.Stars.ContainsKey("level1@difficile") && save.Stars.ContainsKey("level1@facile"),
                "the keys are the record keys: " + string.Join(", ", save.Stars.Keys));
            // A redesigned level (rev 1) keeps its stars under "level6~1": the old "level6" stars are never read for it.
            save.RecordStars("level6", 3, DifficultyDef.Normal);
            Assert.AreEqual(0, save.StarsOf("level6~1", DifficultyDef.Normal));
            Assert.AreEqual(0, save.RecordStars(null, 3, DifficultyDef.Normal));
            Assert.AreEqual(0, save.RecordStars(string.Empty, 3, DifficultyDef.Normal));
            Assert.AreEqual(0, save.StarsOf(null, DifficultyDef.Normal));
        }

        [Test]
        public void Save_StarsDoNotTouchWonOrBest()
        {
            var save = new SaveData();
            save.RecordStars("level1", 3, DifficultyDef.Normal);
            Assert.AreEqual(0, save.Won.Count);
            Assert.AreEqual(0, save.Best.Count);
        }

        [Test]
        public void Parse_MissingStarsIsEmpty_MalformedStarsNeverFailsTheSave()
        {
            SaveData old = SaveData.Parse("{ \"version\": 1, \"won\": [\"level1\"], \"best\": { \"level1\": 12.5 } }", out string problem);
            Assert.IsNotNull(old, "an old save must load: " + problem);
            Assert.IsNotNull(old.Stars);
            Assert.AreEqual(0, old.Stars.Count);
            Assert.AreEqual(0, old.StarsOf("level1", DifficultyDef.Normal));

            SaveData notObject = SaveData.Parse("{ \"version\": 1, \"stars\": 7 }", out problem);
            Assert.IsNotNull(notObject, "a save whose stars are not an object must still load: " + problem);
            Assert.AreEqual(0, notObject.Stars.Count);

            SaveData nullStars = SaveData.Parse("{ \"version\": 1, \"stars\": null }", out problem);
            Assert.IsNotNull(nullStars, problem);
            Assert.AreEqual(0, nullStars.Stars.Count);

            SaveData mixed = SaveData.Parse("{ \"version\": 1, \"stars\": { \"level1\": 2, \"level2\": \"x\", \"level3@difficile\": 9, \"level4\": -1, \"level5\": 1.5 } }", out problem);
            Assert.IsNotNull(mixed, problem);
            Assert.AreEqual(2, mixed.StarsOf("level1", DifficultyDef.Normal));
            Assert.AreEqual(0, mixed.StarsOf("level2", DifficultyDef.Normal), "a string entry is skipped");
            Assert.AreEqual(3, mixed.StarsOf("level3", DifficultyDef.Difficile), "a value above three is clamped");
            Assert.AreEqual(0, mixed.StarsOf("level4", DifficultyDef.Normal), "a negative value is clamped");
            Assert.AreEqual(0, mixed.StarsOf("level5", DifficultyDef.Normal), "a fractional entry is skipped");
            Assert.AreEqual(3, mixed.Stars.Count);
        }

        [Test]
        public void Parse_RoundTripKeepsStars()
        {
            var save = new SaveData();
            save.RecordWin("level1", 12.5f);
            save.RecordStars("level1", 3, DifficultyDef.Normal);
            save.RecordStars("level2~1", 2, DifficultyDef.Difficile);
            string json = save.ToJson();
            StringAssert.Contains("\"stars\"", json);
            SaveData back = SaveData.Parse(json, out string problem);
            Assert.IsNotNull(back, problem);
            Assert.AreEqual(3, back.StarsOf("level1", DifficultyDef.Normal));
            Assert.AreEqual(2, back.StarsOf("level2~1", DifficultyDef.Difficile));
            Assert.AreEqual(12.5f, back.Best["level1"], 1e-5f, "the record survived beside the stars");
        }

        [Test]
        public void Total_SumsTheSavedStarsOfTheGivenRecordIds()
        {
            var save = new SaveData();
            save.RecordStars("level1", 3, DifficultyDef.Normal);
            save.RecordStars("level2", 1, DifficultyDef.Normal);
            save.RecordStars("level2", 3, DifficultyDef.Difficile);
            var ids = new List<string> { "level1", "level2", "level3" };
            Assert.AreEqual(4, Stars.Total(save, ids, DifficultyDef.Normal));
            Assert.AreEqual(3, Stars.Total(save, ids, DifficultyDef.Difficile));
            Assert.AreEqual(0, Stars.Total(save, null, DifficultyDef.Normal));
            Assert.AreEqual(0, Stars.Total(null, ids, DifficultyDef.Normal));
            Assert.AreEqual(9, Stars.Possible(3));
            Assert.AreEqual(0, Stars.Possible(-2));
        }

        [Test]
        public void Strings_StarsSectionHasBothLanguages()
        {
            foreach (string key in new[] { "stars.total", "stars.newBest" })
            {
                string en = Strings.Get(key, Strings.English);
                string fr = Strings.Get(key, Strings.French);
                Assert.AreNotEqual(key, en, key + " has no English text");
                Assert.AreNotEqual(key, fr, key + " has no French text");
                Assert.AreNotEqual(en, fr, key + " is not translated");
            }
            Assert.AreEqual("12 / 66 stars", string.Format(Strings.Get("stars.total", Strings.English), 12, 66));
            Assert.AreEqual("12 / 66 étoiles", string.Format(Strings.Get("stars.total", Strings.French), 12, 66));
        }

        [Test]
        public void LineUp_EveryLevelHasAReferenceAtBothDifficulties_And60Stars()
        {
            ManifestDef manifest = LevelLoader.LoadManifestDef();
            Assert.Greater(manifest.Levels.Count, 0, "premise: levels.json lists levels");
            Assert.AreEqual(60, Stars.Possible(manifest.Levels.Count), "the line-up holds 20 levels, 60 stars (rev 3, ACT3A; update the task if it changed)");
            foreach (string id in manifest.Levels)
            {
                LevelDef def = LevelLoader.Load(id);
                float normal = Stars.Reference(def, DifficultyDef.Normal);
                float hard = Stars.Reference(def, DifficultyDef.Difficile);
                Assert.Greater(normal, Tuning.StarsReferenceSlack, id + " has no normal route to judge the stars against");
                Assert.Greater(hard, Tuning.StarsReferenceSlack, id + " has no route to judge Difficile's stars against");
                Assert.GreaterOrEqual(hard, normal - 1e-3f, id + ": Difficile's reference is under Normal's (the audit's hard exit is never earlier)");
            }
        }
    }
}
