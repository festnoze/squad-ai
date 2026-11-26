using System;

namespace OutOfSight.Core
{
    /// <summary>What a first-time tip points at: a HUD element, or a spot in the world (the rug, a decoy).</summary>
    public enum TipAnchor
    {
        Eye,
        CreakGauge,
        SuspicionGauge,
        World,
    }

    /// <summary>
    /// Onboarding tips (idea 3, docs/next/progress/TIPS.md): the six first-time tips of levels 1 to 3, each a one-sentence
    /// string (tips.* in <see cref="Strings"/>) shown once per save (SaveData.Tips) when its situation first happens, with a
    /// small pointer on the related HUD element or world spot. This table is pure data: the runtime component (Tips) reads
    /// the game and decides when a tip fires; the thresholds of those decisions live here so tests can read them.
    /// </summary>
    public sealed class TipDef
    {
        public const string Eye = "tips.eye";
        public const string Freeze = "tips.freeze";
        public const string Creak = "tips.creak";
        public const string Suspicion = "tips.suspicion";
        public const string Rug = "tips.rug";
        public const string Decoy = "tips.decoy";

        /// <summary>The {move} token of a tip: resolved per device from tips.move.keyboard, tips.move.gamepad, tips.move.touch.</summary>
        public const string MoveToken = "{move}";

        /// <summary>A tip stays this long (unscaled seconds, not counting pauses) unless an input dismisses it earlier.</summary>
        public const float ShowSeconds = 5f;

        /// <summary>
        /// Before this much shown time no input dismisses a tip, and a tip cut short (restart, caught) is not counted as
        /// shown: it comes back the next time its situation happens.
        /// </summary>
        public const float MinSeconds = 1f;

        /// <summary>The freeze tip: a cone counts as turning toward the furniture within this many degrees of its edge.</summary>
        public const float ApproachMarginDegrees = 25f;

        /// <summary>The freeze tip: a cone further than its range times this never counts.</summary>
        public const float ApproachRangeFactor = 1.25f;

        /// <summary>The decoy tip: a decoy of the furniture's kind within this many metres (planar) is "nearby".</summary>
        public const float DecoyNearMetres = 2f;

        /// <summary>The string key (Strings table and SaveData.Tips entry).</summary>
        public readonly string Key;

        /// <summary>What the pointer points at.</summary>
        public readonly TipAnchor Anchor;

        /// <summary>The level ids the tip may show on (an empty list never shows).</summary>
        public readonly string[] Levels;

        private TipDef(string key, TipAnchor anchor, params string[] levels)
        {
            Key = key;
            Anchor = anchor;
            Levels = levels;
        }

        /// <summary>Every tip, in the order of precedence when two fire on the same step (the first wins).</summary>
        public static readonly TipDef[] All =
        {
            new TipDef(Freeze, TipAnchor.Eye, "level1", "level2", "level3"),
            new TipDef(Creak, TipAnchor.CreakGauge, "level1", "level2", "level3"),
            new TipDef(Suspicion, TipAnchor.SuspicionGauge, "level1", "level2", "level3"),
            new TipDef(Decoy, TipAnchor.World, "level3"),
            new TipDef(Rug, TipAnchor.World, "level2", "level3"),
            new TipDef(Eye, TipAnchor.Eye, "level1", "level2", "level3"),
        };

        /// <summary>The tip of a key, or null.</summary>
        public static TipDef Find(string key)
        {
            if (string.IsNullOrEmpty(key))
            {
                return null;
            }
            foreach (TipDef tip in All)
            {
                if (tip.Key == key)
                {
                    return tip;
                }
            }
            return null;
        }

        /// <summary>The tip may show on the level with this id.</summary>
        public bool AppliesTo(string levelId)
        {
            return !string.IsNullOrEmpty(levelId) && Array.IndexOf(Levels, levelId) >= 0;
        }

        /// <summary>
        /// A watcher's cone is turning toward the furniture: the angle between its eye forward and the direction to the
        /// furniture is within <see cref="ApproachMarginDegrees"/> of the cone's half angle (inside the cone counts too) and
        /// it shrank since the previous step. A watcher that only pans away, or holds still, never fires.
        /// </summary>
        public static bool ConeTurnsToward(float angleNow, float anglePrevious, float halfAngle)
        {
            return angleNow <= halfAngle + ApproachMarginDegrees && angleNow < anglePrevious - 0.02f;
        }

        /// <summary>The {move} key of a device: "keyboard", "gamepad" or "touch" (anything else reads as the keyboard).</summary>
        public static string MoveKey(string device)
        {
            return device == "gamepad" || device == "touch" ? "tips.move." + device : "tips.move.keyboard";
        }
    }
}
