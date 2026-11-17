using UnityEngine;

namespace Meuble.Core
{
    /// <summary>
    /// M7 (docs/CONTRACT_M7.md 4.1): the difficulty option, one table of data rows like <see cref="PersonalityDef"/>.
    /// <para>
    /// The knobs (values in Tuning, "M7 design"): <see cref="ViewRangeFactor"/> scales every watcher's view range (the lamp
    /// factor applies on top), <see cref="HalfAngleOffset"/> widens or narrows every cone, <see cref="HearingFactor"/>
    /// scales every listener's hearing factor, <see cref="SuspicionFactor"/> every suspicion gain,
    /// <see cref="CaughtGrace"/> replaces the 0.2 s grace of the caught rule (and of the dog's bark), and
    /// <see cref="CreakFillTime"/> replaces the 20 s fill of the creak gauge. Facile only ever helps the player, Difficile
    /// only ever hinders (an EditMode test checks every knob), and the Normal row is the M6 game exactly.
    /// </para>
    /// <para>
    /// Applied in one place: <see cref="RoutineFactory.PersonalityOf"/> (the routine and watcher construction, which the
    /// game, the audit and the tests all go through) for the range, angle, hearing and suspicion knobs; GameState reads
    /// <see cref="Current"/> for the grace and the creak, and the audit reads it for the creak. The game sets
    /// <see cref="Current"/> from the saved option when a level is built (load or restart): a change in the Options page
    /// applies from the next level load. The audit sets it from its "-difficulty" argument.
    /// </para>
    /// The turn telegraph (0.6 s) is not a knob: it is the fairness rule of PRD 4.3 and 5.4, the same in every mode.
    /// </summary>
    public sealed class DifficultyDef
    {
        public const string Facile = "facile";
        public const string Normal = "normal";
        public const string Difficile = "difficile";

        /// <summary>In the order of the option's cycle (and from easiest to hardest).</summary>
        public static readonly string[] All = { Facile, Normal, Difficile };

        public string Id;
        public float ViewRangeFactor;
        public float HalfAngleOffset;
        public float HearingFactor;
        public float SuspicionFactor;
        public float CaughtGrace;
        public float CreakFillTime;

        private static DifficultyDef current = For(Normal);

        /// <summary>
        /// The difficulty the routines being built and the level being played use. Never null: setting null gives Normal.
        /// The game sets it in GameState when it builds a level; the audit for each of its runs; tests restore Normal.
        /// </summary>
        public static DifficultyDef Current
        {
            get => current;
            set => current = value ?? For(Normal);
        }

        /// <summary>The row of an id, a new instance on every call; null or unknown gives Normal.</summary>
        public static DifficultyDef For(string id)
        {
            switch (id)
            {
                case Facile:
                    return new DifficultyDef
                    {
                        Id = Facile, ViewRangeFactor = Tuning.EasyViewRangeFactor, HalfAngleOffset = Tuning.EasyHalfAngleOffset,
                        HearingFactor = Tuning.EasyHearingFactor, SuspicionFactor = Tuning.EasySuspicionFactor,
                        CaughtGrace = Tuning.EasyCaughtGrace, CreakFillTime = Tuning.EasyCreakFillTime,
                    };
                case Difficile:
                    return new DifficultyDef
                    {
                        Id = Difficile, ViewRangeFactor = Tuning.HardViewRangeFactor, HalfAngleOffset = Tuning.HardHalfAngleOffset, // MUTATION:HARD_RANGE
                        HearingFactor = Tuning.HardHearingFactor, SuspicionFactor = Tuning.HardSuspicionFactor,
                        CaughtGrace = Tuning.HardCaughtGrace, CreakFillTime = Tuning.HardCreakFillTime,
                    };
                default:
                    // The M6 game, knob for knob.
                    return new DifficultyDef
                    {
                        Id = Normal, ViewRangeFactor = 1f, HalfAngleOffset = 0f, HearingFactor = 1f, SuspicionFactor = 1f,
                        CaughtGrace = Tuning.CaughtGrace, CreakFillTime = Tuning.CreakFillTime,
                    };
            }
        }

        /// <summary>The id itself when it is one of <see cref="All"/>; Normal otherwise (null, a missing field, a typo).</summary>
        public static string Normalize(string id)
        {
            return id == Facile || id == Difficile ? id : Normal;
        }

        /// <summary>The Difficulté button's cycle: Facile, Normal, Difficile, then Facile again (anything else is Normal).</summary>
        public static string Next(string id)
        {
            switch (Normalize(id))
            {
                case Facile:
                    return Normal;
                case Normal:
                    return Difficile;
                default:
                    return Facile;
            }
        }

        /// <summary>
        /// CONTRACT_M7 4.1: the key of a level's record in SaveData.best. Normal keeps the bare level id (an old save keeps its
        /// records), the others get "@facile" or "@difficile". Null or empty level ids stay as they are.
        /// </summary>
        public static string RecordKey(string levelId, string difficulty)
        {
            string d = Normalize(difficulty);
            return string.IsNullOrEmpty(levelId) || d == Normal ? levelId : levelId + "@" + d; // MUTATION:RECORD_KEY_NORMAL
        }

        /// <summary>
        /// The personality <paramref name="p"/> under this difficulty, changed in place and returned: range times
        /// <see cref="ViewRangeFactor"/>, half angle plus <see cref="HalfAngleOffset"/> (kept in [1, 89] deg), hearing and
        /// suspicion factors times theirs (a watcher that does not hear or suspect, the dog, stays at 0). Null stays null.
        /// </summary>
        public PersonalityDef Apply(PersonalityDef p)
        {
            if (p == null)
            {
                return null;
            }
            p.ViewRange *= ViewRangeFactor;
            p.HalfAngle = Mathf.Clamp(p.HalfAngle + HalfAngleOffset, 1f, 89f); // MUTATION:DIFFICULTY_ANGLE
            p.HearingFactor *= HearingFactor;
            p.SuspicionFactor *= SuspicionFactor;
            return p;
        }
    }
}
