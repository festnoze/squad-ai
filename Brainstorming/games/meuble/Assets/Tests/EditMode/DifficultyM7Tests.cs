using System.Collections.Generic;
using OutOfSight.Core;
using NUnit.Framework;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M7 design (docs/CONTRACT_M7.md 4.1): the difficulty table. Facile only ever helps and Difficile only ever hinders,
    /// knob by knob, on the table and on every personality as RoutineFactory gives it; Normal is the M6 game field for
    /// field; the creak gauge and the caught rule take the difficulty's times; the option and the record keys.
    /// Every test leaves <see cref="DifficultyDef.Current"/> at Normal.
    /// </summary>
    public sealed class DifficultyM7Tests
    {
        [SetUp]
        public void SetUp()
        {
            DifficultyDef.Current = null;
        }

        [TearDown]
        public void TearDown()
        {
            DifficultyDef.Current = null;
        }

        private static DifficultyDef Easy => DifficultyDef.For(DifficultyDef.Facile);
        private static DifficultyDef Mid => DifficultyDef.For(DifficultyDef.Normal);
        private static DifficultyDef Hard => DifficultyDef.For(DifficultyDef.Difficile);

        // ----- the table, knob by knob -----

        [Test]
        public void Table_EveryKnobHelpsAtFacileAndHindersAtDifficile()
        {
            // A wider sight, a keener ear and a faster suspicion hinder; a longer grace and a slower creak help.
            Assert.Less(Easy.ViewRangeFactor, Mid.ViewRangeFactor, "range: Facile must see less far");
            Assert.Greater(Hard.ViewRangeFactor, Mid.ViewRangeFactor, "range: Difficile must see farther");
            Assert.Less(Easy.HalfAngleOffset, Mid.HalfAngleOffset, "angle: Facile must narrow the cone");
            Assert.Greater(Hard.HalfAngleOffset, Mid.HalfAngleOffset, "angle: Difficile must widen the cone");
            Assert.Less(Easy.HearingFactor, Mid.HearingFactor, "hearing: Facile must hear less");
            // Difficile keeps the Normal hearing (Tuning, M7 design): at 1.25 levels 2 and 3 had no schedule. Never less.
            Assert.GreaterOrEqual(Hard.HearingFactor, Mid.HearingFactor, "hearing: Difficile must never hear less");
            Assert.Less(Easy.SuspicionFactor, Mid.SuspicionFactor, "suspicion: Facile must suspect slower");
            Assert.Greater(Hard.SuspicionFactor, Mid.SuspicionFactor, "suspicion: Difficile must suspect faster");
            Assert.Greater(Easy.CaughtGrace, Mid.CaughtGrace, "grace: Facile must forgive longer");
            Assert.Less(Hard.CaughtGrace, Mid.CaughtGrace, "grace: Difficile must forgive shorter");
            Assert.Greater(Easy.CreakFillTime, Mid.CreakFillTime, "creak: Facile must fill slower");
            Assert.Less(Hard.CreakFillTime, Mid.CreakFillTime, "creak: Difficile must fill faster");
        }

        [Test]
        public void Table_NormalIsTheM6GameKnobForKnob()
        {
            DifficultyDef n = Mid;
            Assert.AreEqual(DifficultyDef.Normal, n.Id);
            Assert.AreEqual(1f, n.ViewRangeFactor);
            Assert.AreEqual(0f, n.HalfAngleOffset);
            Assert.AreEqual(1f, n.HearingFactor);
            Assert.AreEqual(1f, n.SuspicionFactor);
            Assert.AreEqual(Tuning.CaughtGrace, n.CaughtGrace);
            Assert.AreEqual(Tuning.CreakFillTime, n.CreakFillTime);
        }

        [Test]
        public void Table_GracesAreWholeFixedStepsAndPositive()
        {
            foreach (string id in DifficultyDef.All)
            {
                DifficultyDef d = DifficultyDef.For(id);
                float steps = d.CaughtGrace / Tuning.FixedStep;
                Assert.AreEqual(UnityEngine.Mathf.Round(steps), steps, 1e-3f, id + ": the grace must be a whole number of fixed steps");
                Assert.Greater(d.CaughtGrace, 0f, id);
                Assert.Greater(d.CreakFillTime, Tuning.CreakWarning, id + ": the creak needs its warning");
                Assert.Greater(d.ViewRangeFactor, 0f, id);
            }
        }

        [Test]
        public void Table_UnknownAndNullAreNormal()
        {
            Assert.AreEqual(DifficultyDef.Normal, DifficultyDef.For(null).Id);
            Assert.AreEqual(DifficultyDef.Normal, DifficultyDef.For("expert").Id);
            Assert.AreEqual(DifficultyDef.Normal, DifficultyDef.Normalize(null));
            Assert.AreEqual(DifficultyDef.Normal, DifficultyDef.Normalize("Difficile"), "ids are lower case");
            Assert.AreEqual(DifficultyDef.Facile, DifficultyDef.Normalize(DifficultyDef.Facile));
            Assert.AreEqual(DifficultyDef.Difficile, DifficultyDef.Normalize(DifficultyDef.Difficile));
            DifficultyDef.Current = null;
            Assert.AreEqual(DifficultyDef.Normal, DifficultyDef.Current.Id, "setting null gives Normal");
        }

        [Test]
        public void Next_CyclesFacileNormalDifficile()
        {
            Assert.AreEqual(DifficultyDef.Normal, DifficultyDef.Next(DifficultyDef.Facile));
            Assert.AreEqual(DifficultyDef.Difficile, DifficultyDef.Next(DifficultyDef.Normal));
            Assert.AreEqual(DifficultyDef.Facile, DifficultyDef.Next(DifficultyDef.Difficile));
            Assert.AreEqual(DifficultyDef.Difficile, DifficultyDef.Next(null), "a missing choice is Normal, so Difficile is next");
        }

        // ----- every personality, through the one place the game and the audit use -----

        private static InhabitantDef Def(string personality, string kind = null)
        {
            return new InhabitantDef { Personality = personality, Kind = kind, Stations = new List<StationDef>() };
        }

        private static PersonalityDef At(string difficulty, InhabitantDef def)
        {
            DifficultyDef.Current = DifficultyDef.For(difficulty);
            PersonalityDef p = RoutineFactory.PersonalityOf(def);
            DifficultyDef.Current = null;
            return p;
        }

        [Test]
        public void PersonalityOf_EveryRowMonotoneKnobByKnob()
        {
            foreach (string id in PersonalityDef.All)
            {
                InhabitantDef def = id == PersonalityDef.Dog ? Def(null, PersonalityDef.Dog) : Def(id);
                PersonalityDef e = At(DifficultyDef.Facile, def);
                PersonalityDef n = At(DifficultyDef.Normal, def);
                PersonalityDef h = At(DifficultyDef.Difficile, def);
                Assert.Less(e.ViewRange, n.ViewRange, id + ": range at Facile");
                Assert.Greater(h.ViewRange, n.ViewRange, id + ": range at Difficile");
                Assert.Less(e.HalfAngle, n.HalfAngle, id + ": angle at Facile");
                Assert.Greater(h.HalfAngle, n.HalfAngle, id + ": angle at Difficile");
                Assert.LessOrEqual(e.HearingFactor, n.HearingFactor, id + ": hearing at Facile");
                Assert.GreaterOrEqual(h.HearingFactor, n.HearingFactor, id + ": hearing at Difficile");
                Assert.LessOrEqual(e.SuspicionFactor, n.SuspicionFactor, id + ": suspicion at Facile");
                Assert.GreaterOrEqual(h.SuspicionFactor, n.SuspicionFactor, id + ": suspicion at Difficile");
                if (n.HearingFactor > 0f)
                {
                    Assert.Less(e.HearingFactor, n.HearingFactor, id + ": a listener hears strictly less at Facile");
                    Assert.GreaterOrEqual(h.HearingFactor, n.HearingFactor, id + ": a listener never hears less at Difficile");
                }
                else
                {
                    Assert.AreEqual(0f, h.HearingFactor, id + ": a deaf watcher stays deaf");
                }
                // The knobs that are not the difficulty's stay the personality's.
                Assert.AreEqual(n.Tolerance, h.Tolerance, id);
                Assert.AreEqual(n.WalkSpeed, h.WalkSpeed, id);
                Assert.AreEqual(n.EyeHeight, h.EyeHeight, id);
                Assert.AreEqual(n.Memory, h.Memory, id);
                Assert.AreEqual(n.Hears, h.Hears, id);
            }
        }

        [Test]
        public void PersonalityOf_NormalIsTheRowFieldForField()
        {
            foreach (string id in PersonalityDef.All)
            {
                InhabitantDef def = id == PersonalityDef.Dog ? Def(null, PersonalityDef.Dog) : Def(id);
                PersonalityDef row = PersonalityDef.ForInhabitant(def);
                PersonalityDef n = At(DifficultyDef.Normal, def);
                Assert.AreEqual(row.ViewRange, n.ViewRange, id);
                Assert.AreEqual(row.HalfAngle, n.HalfAngle, id);
                Assert.AreEqual(row.HearingFactor, n.HearingFactor, id);
                Assert.AreEqual(row.SuspicionFactor, n.SuspicionFactor, id);
            }
        }

        [Test]
        public void RoutineFactory_RoutineSeesWithTheCurrentDifficulty()
        {
            var def = new InhabitantDef
            {
                Personality = PersonalityDef.Watchful,
                Stations = new List<StationDef> { new StationDef { X = 0f, Z = 0f, Facing = 0f, Dwell = 1f } },
            };
            DifficultyDef.Current = DifficultyDef.For(DifficultyDef.Difficile);
            InhabitantRoutine hard = RoutineFactory.Create(def, null, StraightPlanner.Instance);
            DifficultyDef.Current = null;
            InhabitantRoutine normal = RoutineFactory.Create(def, null, StraightPlanner.Instance);
            Assert.AreEqual(10f * Tuning.HardViewRangeFactor, hard.ViewRange, 1e-4f);
            Assert.AreEqual(60f + Tuning.HardHalfAngleOffset, hard.HalfAngle, 1e-4f);
            Assert.AreEqual(1f * Tuning.HardHearingFactor, hard.HearingFactor, 1e-4f);
            Assert.AreEqual(10f, normal.ViewRange, 1e-4f, "a routine built after the switch back sees as before");
            Assert.AreEqual(60f, normal.HalfAngle, 1e-4f);
        }

        // ----- the creak and the grace -----

        [Test]
        public void CreakGauge_CreaksAfterTheDifficultyFillTime()
        {
            foreach (string id in DifficultyDef.All)
            {
                DifficultyDef d = DifficultyDef.For(id);
                var gauge = new CreakGauge { FillTime = d.CreakFillTime };
                int startSteps = UnityEngine.Mathf.RoundToInt(Tuning.CreakStartDelay / Tuning.FixedStep);
                int fillSteps = UnityEngine.Mathf.RoundToInt(d.CreakFillTime / Tuning.FixedStep);
                int creakAt = -1;
                for (int s = 0; s < startSteps + fillSteps + 10 && creakAt < 0; s++)
                {
                    if (gauge.Step(Tuning.FixedStep, false, false, s * Tuning.FixedStep))
                    {
                        creakAt = s + 1;
                    }
                }
                Assert.AreEqual(startSteps + fillSteps, creakAt, id + ": creaks on the step that ends the fill time");
                Assert.AreEqual(1f - Tuning.CreakWarning / d.CreakFillTime, gauge.WarningStart, 1e-5f, id + ": the warning is the last 3 s");
            }
        }

        [Test]
        public void CaughtRule_CaughtAfterTheDifficultyGrace()
        {
            foreach (string id in DifficultyDef.All)
            {
                DifficultyDef d = DifficultyDef.For(id);
                var rule = new CaughtRule { Grace = d.CaughtGrace };
                int steps = UnityEngine.Mathf.RoundToInt(d.CaughtGrace / Tuning.FixedStep);
                for (int s = 1; s < steps; s++)
                {
                    Assert.IsFalse(rule.Step(true, true, Tuning.FixedStep), id + ": not caught before the grace, step " + s);
                }
                Assert.IsTrue(rule.Step(true, true, Tuning.FixedStep), id + ": caught on the step that ends the grace");
            }
        }

        // ----- the record keys -----

        [Test]
        public void RecordKey_NormalKeepsTheBareIdOthersGetASuffix()
        {
            Assert.AreEqual("level3", DifficultyDef.RecordKey("level3", DifficultyDef.Normal));
            Assert.AreEqual("level3", DifficultyDef.RecordKey("level3", null), "a missing choice is Normal: old saves keep their records");
            Assert.AreEqual("level3@facile", DifficultyDef.RecordKey("level3", DifficultyDef.Facile));
            Assert.AreEqual("level3@difficile", DifficultyDef.RecordKey("level3", DifficultyDef.Difficile));
            Assert.IsNull(DifficultyDef.RecordKey(null, DifficultyDef.Difficile));
        }

        // ----- the option (SaveData.options.difficulty) -----

        [Test]
        public void Option_DefaultAndMissingAreNormal()
        {
            Assert.IsNull(SaveOptions.Default().Difficulty, "a fresh save has no difficulty field");
            Assert.AreEqual(DifficultyDef.Normal, SaveOptions.Default().DifficultyId);
            // An M6 save: options without the field.
            SaveData m6 = SaveData.Parse("{ \"version\": 1, \"won\": [], \"best\": {}, \"options\": { \"sensitivity\": 1.0, \"volume\": 80, \"cone\": \"always\" } }", out string problem);
            Assert.IsNotNull(m6, problem);
            Assert.AreEqual(1, m6.Version, "the version stays 1");
            Assert.AreEqual(DifficultyDef.Normal, m6.Options.DifficultyId);
            Assert.IsFalse(m6.ToJson().Contains("difficulty"), "a save without a choice is written without the field");
        }

        [Test]
        public void Option_UnknownDifficultyFallsBackToNormal()
        {
            var odd = new SaveOptions { Difficulty = "expert" };
            Assert.IsNull(odd.Clamped().Difficulty, "an unknown id is dropped by Clamped");
            Assert.AreEqual(DifficultyDef.Normal, odd.DifficultyId);
            SaveData parsed = SaveData.Parse("{ \"version\": 1, \"options\": { \"difficulty\": \"expert\" } }", out string problem);
            Assert.IsNotNull(parsed, problem);
            Assert.IsNull(parsed.Options.Difficulty);
            SaveData typed = SaveData.Parse("{ \"version\": 1, \"options\": { \"difficulty\": 3 } }", out problem);
            Assert.IsNotNull(typed, "a malformed difficulty never fails the save: " + problem);
            Assert.AreEqual(DifficultyDef.Normal, typed.Options.DifficultyId);
            foreach (string id in DifficultyDef.All)
            {
                Assert.AreEqual(id, new SaveOptions { Difficulty = id }.Clamped().Difficulty, id + " is kept");
            }
        }

        [Test]
        public void Option_DifficultyRoundTripsThroughSaveStore()
        {
            string dir = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "outofsight_difficulty_tests_" + System.Guid.NewGuid().ToString("N"));
            System.IO.Directory.CreateDirectory(dir);
            try
            {
                SaveStore.ResetForTests();
                SaveStore.PathOverride = System.IO.Path.Combine(dir, SaveStore.FileName);
                SaveOptions o = SaveStore.Options;
                SaveStore.SetOptions(new SaveOptions { Sensitivity = 1.5f, Volume = o.Volume, Cone = o.Cone, Quality = o.Quality, Difficulty = DifficultyDef.Difficile });
                SaveStore.Load();
                Assert.AreEqual(DifficultyDef.Difficile, SaveStore.Options.DifficultyId, "the difficulty survives a fresh load");
                Assert.AreEqual(1.5f, SaveStore.Options.Sensitivity, 1e-6f, "and the other options with it");
                SaveStore.ResetOptions();
                SaveStore.Load();
                Assert.AreEqual(DifficultyDef.Normal, SaveStore.Options.DifficultyId, "Par défaut resets the difficulty to Normal");
            }
            finally
            {
                SaveStore.ResetForTests();
                try
                {
                    System.IO.Directory.Delete(dir, true);
                }
                catch (System.Exception)
                {
                    // A leftover temp folder is harmless.
                }
            }
        }

        // ----- the records per difficulty -----

        [Test]
        public void RecordWin_KeepsOneRecordPerDifficultyAndOneWinPerLevel()
        {
            var save = new SaveData();
            RecordResult hard = save.RecordWin("level2", 20f, DifficultyDef.Difficile);
            Assert.IsTrue(hard.NewBest);
            CollectionAssert.AreEqual(new[] { "level2" }, save.Won, "a win at Difficile unlocks like any win");
            Assert.AreEqual(20f, save.Best["level2@difficile"]);
            Assert.IsFalse(save.Best.ContainsKey("level2"), "a Difficile win is not a Normal record");

            RecordResult normal = save.RecordWin("level2", 30f, DifficultyDef.Normal);
            Assert.IsTrue(normal.NewBest, "the first Normal win is a record of its own, slower or not");
            Assert.AreEqual(30f, save.Best["level2"]);
            Assert.AreEqual(20f, save.Best["level2@difficile"], "the Difficile record is untouched");

            RecordResult easy = save.RecordWin("level2", 10f, DifficultyDef.Facile);
            Assert.AreEqual(10f, save.Best["level2@facile"]);
            Assert.AreEqual(30f, save.Best["level2"], "a faster Facile win never beats the Normal record");
            CollectionAssert.AreEqual(new[] { "level2" }, save.Won, "a level is won once whatever the difficulty");

            RecordResult slower = save.RecordWin("level2", 25f, DifficultyDef.Difficile);
            Assert.IsFalse(slower.NewBest);
            Assert.AreEqual(20f, slower.PreviousBest);
            Assert.AreEqual(20f, save.Best["level2@difficile"]);
            Assert.AreEqual(30f, save.RecordWin("level2", 31f).Best, "the two argument RecordWin is Normal");
        }

        [Test]
        public void RecordWin_OldSaveRecordsStayNormalAndRoundTrip()
        {
            SaveData old = SaveData.Parse("{ \"version\": 1, \"won\": [\"level1\"], \"best\": { \"level1\": 12.5 } }", out string problem);
            Assert.IsNotNull(old, problem);
            RecordResult n = old.RecordWin("level1", 13f, DifficultyDef.Normal);
            Assert.AreEqual(12.5f, n.PreviousBest, "an M6 record is the Normal record");
            old.RecordWin("level1", 40f, DifficultyDef.Difficile);
            SaveData back = SaveData.Parse(old.ToJson(), out problem);
            Assert.IsNotNull(back, problem);
            Assert.AreEqual(12.5f, back.Best["level1"]);
            Assert.AreEqual(40f, back.Best["level1@difficile"], "the suffixed key survives the file");
        }
    }
}
