// Owned by BI since wave B-2 (written by B0a). Contract 11.5 (+ 25.1 Biome): persistent settings, stats and tutorial flags (PlayerPrefs keys "pio.<Name>").
// Wave C (game-flow): TutSelfCrossDone (the self-crossing lesson of rules-01) and the MemoryOnly test scope.
// Wave D-2 (traits-infra, docs/BIOME_TRAITS.md section 5): BiomeRulesOn (the Options toggle "Regles des biomes", OFF =
// "Regles classiques") and TraitMatrix (the hidden trait matrix, canonical text of BiomeTraitTable, "" = the table) with
// ResetTraitMatrix; TuningModified also covers a matrix that differs from the table (BiomeRulesOn does not).
// Every PlayerPrefs access is wrapped in try/catch and falls back to the default. Values are cached in memory after the
// first read (only this class writes these keys), so per-frame readers (Palette, Sfx) cost nothing.
using System;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    public static class SaveData
    {
        public const string Prefix = "pio.";

        // Test-setting ranges (contract 15.2).
        public const float SparkFactorMin = 1.4f, SparkFactorMax = 2.4f, SparkFactorStep = 0.1f;
        public const float RingDelayMin = 10f, RingDelayMax = 30f, RingDelayStep = 5f;
        /// <summary>
        /// Rule v1.7 (contract 31): the round time is only the ultimate limit of a country round (the goal is to conquer
        /// 100 %): 5, 10 or 15 minutes, 15 by default. A value saved by an older version (60 / 90 / 120 s, below the first
        /// choice) reads as the default.
        /// </summary>
        public static readonly float[] RoundSecondsChoices = { 300f, 600f, 900f };
        public const float DefaultRoundSeconds = 900f;

        /// <summary>Raised after every setter (also when the value did not change).</summary>
        public static event Action Changed;

        private static readonly BoolPref soundOn = new BoolPref("SoundOn", true);
        private static readonly BoolPref hapticsOn = new BoolPref("HapticsOn", true);
        private static readonly BoolPref lassoOn = new BoolPref("LassoOn", false);
        private static readonly IntPref language = new IntPref("Language", 0, 0, 1);
        private static readonly IntPref quality = new IntPref("Quality", 0, 0, 3);
        private static readonly IntPref colorIndex = new IntPref("ColorIndex", 0, 0, 3);
        private static readonly IntPref biome = new IntPref("Biome", 0, 0, BiomeTheme.Count - 1);
        private static readonly FloatPref bestArea = new FloatPref("BestArea", 0f, 0f, 100f);
        private static readonly IntPref wins = new IntPref("Wins", 0, 0, int.MaxValue);
        private static readonly IntPref roundsPlayed = new IntPref("RoundsPlayed", 0, 0, int.MaxValue);
        private static readonly BoolPref tutExitDone = new BoolPref("TutExitDone", false);
        private static readonly BoolPref tutCutDone = new BoolPref("TutCutDone", false);
        private static readonly BoolPref tutLassoDone = new BoolPref("TutLassoDone", false);
        private static readonly BoolPref tutSelfCrossDone = new BoolPref("TutSelfCrossDone", false);
        private static readonly FloatPref sparkFactor = new FloatPref("SparkFactor", (float)Tuning.SparkSpeedFactor, SparkFactorMin, SparkFactorMax);
        // The stored range is wider than the choices so an old saved value survives the clamp and is migrated by the getter.
        private static readonly FloatPref roundSeconds = new FloatPref("RoundSeconds", DefaultRoundSeconds, 0f, 3600f);
        private static readonly FloatPref ringDelay = new FloatPref("RingDelay", (float)Tuning.LassoFirstSpawn, RingDelayMin, RingDelayMax);
        private static readonly BoolPref biomeRulesOn = new BoolPref("BiomeRulesOn", true);
        private static readonly StringPref traitMatrix = new StringPref("TraitMatrix", "", BiomeTraitTable.CanonicalMatrix);

        /// <summary>Default true.</summary>
        public static bool SoundOn { get => soundOn.Get(); set => Set(soundOn, value); }

        /// <summary>Default true.</summary>
        public static bool HapticsOn { get => hapticsOn.Get(); set => Set(hapticsOn, value); }

        /// <summary>Default FALSE (first Revanche trial without lasso, brief closing paragraph).</summary>
        public static bool LassoOn { get => lassoOn.Get(); set => Set(lassoOn, value); }

        /// <summary>0 FR (default), 1 EN; Strings.Language reads and writes it.</summary>
        public static int Language { get => language.Get(); set => Set(language, value); }

        /// <summary>0 Auto (default), 1 High, 2 Medium, 3 Low.</summary>
        public static int Quality { get => quality.Get(); set => Set(quality, value); }

        /// <summary>0..3, default 0 (the human's palette color).</summary>
        public static int ColorIndex { get => colorIndex.Get(); set => Set(colorIndex, value); }

        /// <summary>Contract 25.1: the biome picked in the menu (BiomeId as int: 0 Liquid (default), 1 Fire, 2 Electric).</summary>
        public static int Biome { get => biome.Get(); set => Set(biome, value); }

        /// <summary>Best human area percent (alive at round end, or FinalCells when eliminated).</summary>
        public static float BestArea { get => bestArea.Get(); set => Set(bestArea, value); }

        /// <summary>Rounds where the human has rank 1, shared included.</summary>
        public static int Wins { get => wins.Get(); set => Set(wins, value); }

        public static int RoundsPlayed { get => roundsPlayed.Get(); set => Set(roundsPlayed, value); }

        public static bool TutExitDone { get => tutExitDone.Get(); set => Set(tutExitDone, value); }

        public static bool TutCutDone { get => tutCutDone.Get(); set => Set(tutCutDone, value); }

        public static bool TutLassoDone { get => tutLassoDone.Get(); set => Set(tutLassoDone, value); }

        /// <summary>
        /// Wave C (rules-01): the self-crossing lesson (bubble tut.selfcross at the first unchased return after an
        /// uncharged crossing of the own trail) was shown. Default false.
        /// </summary>
        public static bool TutSelfCrossDone { get => tutSelfCrossDone.Get(); set => Set(tutSelfCrossDone, value); }

        /// <summary>
        /// Tests only. While true, the setters update the in-memory cache and raise Changed but never write PlayerPrefs,
        /// and Flush does nothing, so a test can set flags and settings without touching the player's saved data.
        /// Every change of the value drops the cache: turning it off brings the PlayerPrefs values back.
        /// </summary>
        public static bool MemoryOnly
        {
            get => memoryOnly;
            set
            {
                if (memoryOnly == value) return;
                memoryOnly = value;
                ReloadCache();
            }
        }

        private static bool memoryOnly;

        /// <summary>Test setting, default 1.8, range 1.4..2.4 step 0.1 (rounded to the step).</summary>
        public static float SparkFactor
        {
            get => sparkFactor.Get();
            set => Set(sparkFactor, Snap(value, SparkFactorMin, SparkFactorMax, SparkFactorStep));
        }

        /// <summary>
        /// Test setting, default 900 (300 / 600 / 900 s: snapped to the nearest choice). Rule v1.7: a stored value below the
        /// first choice is a pre-v1.7 save (60 / 90 / 120 s) and reads as DefaultRoundSeconds.
        /// </summary>
        public static float RoundSeconds
        {
            get => MigrateRoundSeconds(roundSeconds.Get());
            set => Set(roundSeconds, SnapChoice(value));
        }

        /// <summary>The round time a stored value stands for: DefaultRoundSeconds for a pre-v1.7 value, else the nearest choice.</summary>
        public static float MigrateRoundSeconds(float stored)
        {
            if (float.IsNaN(stored) || float.IsInfinity(stored) || stored < RoundSecondsChoices[0] - 0.5f) return DefaultRoundSeconds;
            return SnapChoice(stored);
        }

        /// <summary>Test setting, default 15 (10..30 step 5).</summary>
        public static float RingDelay
        {
            get => ringDelay.Get();
            set => Set(ringDelay, Snap(value, RingDelayMin, RingDelayMax, RingDelayStep));
        }

        /// <summary>
        /// Wave D-2 (BIOME_TRAITS 5): the Options toggle "Regles des biomes" (default true). False = "Regles classiques":
        /// every round and the attract match run the classic rules (no trait). A normal option: it does not mark the
        /// tuning as modified.
        /// </summary>
        public static bool BiomeRulesOn { get => biomeRulesOn.Get(); set => Set(biomeRulesOn, value); }

        /// <summary>
        /// Wave D-2 (BIOME_TRAITS 5): the hidden trait matrix (trait -> set of biomes) as canonical text of
        /// BiomeTraitTable ("Id=letters;...", only the rows that differ from the table); "" = the default table. The
        /// setter canonicalizes (unknown rows dropped). Edit it through BiomeTraitTable.SetAssigned.
        /// </summary>
        public static string TraitMatrix { get => traitMatrix.Get(); set => Set(traitMatrix, value ?? ""); }

        /// <summary>The trait matrix differs from the default table (a test setting: stats are not saved then).</summary>
        public static bool TraitMatrixModified => !string.IsNullOrEmpty(TraitMatrix);

        /// <summary>Restores the default trait table (the matrix "Reinitialiser" button).</summary>
        public static void ResetTraitMatrix()
        {
            Set(traitMatrix, "");
        }

        /// <summary>
        /// Any test setting differs from its default (Tuning; the round time from DefaultRoundSeconds since rule v1.7), or
        /// the trait matrix differs from the table (BiomeRulesOn excluded).
        /// </summary>
        public static bool TuningModified =>
            Mathf.Abs(SparkFactor - (float)Tuning.SparkSpeedFactor) > 1e-3f
            || Mathf.Abs(RoundSeconds - DefaultRoundSeconds) > 1e-3f
            || Mathf.Abs(RingDelay - (float)Tuning.LassoFirstSpawn) > 1e-3f
            || TraitMatrixModified;

        /// <summary>Restores the three test settings to their Tuning defaults (the Options "Reinitialiser" button).</summary>
        public static void ResetTestSettings()
        {
            sparkFactor.Set((float)Tuning.SparkSpeedFactor);
            roundSeconds.Set(DefaultRoundSeconds);
            ringDelay.Set((float)Tuning.LassoFirstSpawn);
            RaiseChanged();
        }

        /// <summary>PlayerPrefs.Save: when Options close, when Results appear, on OnApplicationPause(true).</summary>
        public static void Flush()
        {
            if (memoryOnly) return;
            try
            {
                PlayerPrefs.Save();
            }
            catch (Exception e)
            {
                Debug.LogWarning("[PainterIO] SaveData.Flush failed: " + e.Message);
            }
        }

        /// <summary>
        /// Drops the in-memory cache so the next read comes from PlayerPrefs again (tests that edit PlayerPrefs
        /// directly). Not needed in normal play.
        /// </summary>
        public static void ReloadCache()
        {
            soundOn.Invalidate(); hapticsOn.Invalidate(); lassoOn.Invalidate(); language.Invalidate();
            quality.Invalidate(); colorIndex.Invalidate(); biome.Invalidate(); bestArea.Invalidate(); wins.Invalidate();
            roundsPlayed.Invalidate(); tutExitDone.Invalidate(); tutCutDone.Invalidate(); tutLassoDone.Invalidate();
            tutSelfCrossDone.Invalidate(); sparkFactor.Invalidate(); roundSeconds.Invalidate(); ringDelay.Invalidate();
            biomeRulesOn.Invalidate(); traitMatrix.Invalidate();
        }

        private static void Set<T>(Pref<T> pref, T value)
        {
            pref.Set(value);
            RaiseChanged();
        }

        private static void RaiseChanged()
        {
            Action handler = Changed;
            if (handler == null) return;
            foreach (Delegate d in handler.GetInvocationList())
            {
                try
                {
                    ((Action)d)();
                }
                catch (Exception e)
                {
                    Debug.LogError("[PainterIO] SaveData.Changed subscriber failed: " + e);
                }
            }
        }

        private static float Snap(float value, float min, float max, float step)
        {
            if (float.IsNaN(value)) value = min;
            value = Mathf.Clamp(value, min, max);
            return Mathf.Clamp(min + Mathf.Round((value - min) / step) * step, min, max);
        }

        private static float SnapChoice(float value)
        {
            float best = DefaultRoundSeconds;
            float bestDistance = float.MaxValue;
            foreach (float c in RoundSecondsChoices)
            {
                float d = Mathf.Abs(c - value);
                if (d < bestDistance)
                {
                    bestDistance = d;
                    best = c;
                }
            }
            return best;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Cached preferences.

        private abstract class Pref<T>
        {
            protected readonly string Key;
            protected readonly T Default;
            private bool loaded;
            private T value;

            protected Pref(string name, T defaultValue)
            {
                Key = Prefix + name;
                Default = defaultValue;
            }

            public T Get()
            {
                if (!loaded)
                {
                    try
                    {
                        value = Sanitize(PlayerPrefs.HasKey(Key) ? Read() : Default);
                    }
                    catch (Exception)
                    {
                        value = Default;
                    }
                    loaded = true;
                }
                return value;
            }

            public void Set(T v)
            {
                value = Sanitize(v);
                loaded = true;
                if (memoryOnly) return;   // tests only: the cache holds the value, PlayerPrefs stay untouched
                try
                {
                    Write(value);
                }
                catch (Exception e)
                {
                    Debug.LogWarning("[PainterIO] SaveData could not write " + Key + ": " + e.Message);
                }
            }

            public void Invalidate()
            {
                loaded = false;
            }

            protected abstract T Read();
            protected abstract void Write(T v);
            protected virtual T Sanitize(T v) => v;
        }

        private sealed class BoolPref : Pref<bool>
        {
            public BoolPref(string name, bool defaultValue) : base(name, defaultValue) { }
            protected override bool Read() => PlayerPrefs.GetInt(Key, Default ? 1 : 0) != 0;
            protected override void Write(bool v) => PlayerPrefs.SetInt(Key, v ? 1 : 0);
        }

        private sealed class IntPref : Pref<int>
        {
            private readonly int min, max;

            public IntPref(string name, int defaultValue, int min, int max) : base(name, defaultValue)
            {
                this.min = min;
                this.max = max;
            }

            protected override int Read() => PlayerPrefs.GetInt(Key, Default);
            protected override void Write(int v) => PlayerPrefs.SetInt(Key, v);
            protected override int Sanitize(int v) => v < min ? min : (v > max ? max : v);
        }

        private sealed class StringPref : Pref<string>
        {
            private readonly Func<string, string> canonical;

            public StringPref(string name, string defaultValue, Func<string, string> canonical) : base(name, defaultValue)
            {
                this.canonical = canonical;
            }

            protected override string Read() => PlayerPrefs.GetString(Key, Default);
            protected override void Write(string v) => PlayerPrefs.SetString(Key, v);

            protected override string Sanitize(string v)
            {
                if (v == null) return Default;
                try
                {
                    return canonical != null ? canonical(v) ?? Default : v;
                }
                catch (Exception)
                {
                    return Default;
                }
            }
        }

        private sealed class FloatPref : Pref<float>
        {
            private readonly float min, max;

            public FloatPref(string name, float defaultValue, float min, float max) : base(name, defaultValue)
            {
                this.min = min;
                this.max = max;
            }

            protected override float Read() => PlayerPrefs.GetFloat(Key, Default);
            protected override void Write(float v) => PlayerPrefs.SetFloat(Key, v);
            protected override float Sanitize(float v) => float.IsNaN(v) || float.IsInfinity(v) ? Default : Mathf.Clamp(v, min, max);
        }
    }
}
