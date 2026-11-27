// Written by A1 as a complete data type with the contract 5.7 starting presets; owned by A5, who tuned the values.
using System;

namespace PainterIO.Core
{
    public enum BotStyle { Cautious, Greedy, Aggressive, Balanced }

    /// <summary>
    /// Section 9 bot parameters (contract 5.7). Preset values, tuned by A5 against the section 9 targets on bot-only
    /// rounds (seeds 1-50 asserted, seeds 101-200 held out); changes from the contract's starting table are marked:
    /// <code>
    /// Style       MinOut MaxOut MaxTrail Threat AttackR AttackC Lasso Jitter React
    /// Balanced    4.5*   10*    34*      6      7       0.45    0.5   0.10   0.30
    /// Greedy      5.5*   13*    45*      8**    5       0.25    0.8   0.06   0.40
    /// Aggressive  3      7      24       8**    11      0.75    0.3   0.12   0.25
    /// Cautious    2.5    5      16       8      4       0.15    0.4   0.08   0.35
    /// </code>
    /// SenseRadius 16 and HumanAttackScale 1 for every preset. Balanced grew a little (the human-proxy fixture was
    /// alive too often and rarely first) and Greedy shrank a little (it won most rounds and trailed more than 75 % of
    /// its alive time).
    /// ** Contract 24 retune (package A8): every cut now denies the capture and bots also make denial cuts, so the Spark
    /// elimination share of the bot-only rounds rose above the asserted 85 % (86 % with lasso on and off). Greedy (4.5)
    /// and Aggressive (5) now guard their trails like Cautious (ThreatRadius 8): back to about 70 % with the cut share
    /// still above 90 %. Balanced is unchanged, so the human-proxy fixture (built from Balanced) keeps its ThreatRadius.
    /// </summary>
    public sealed class BotPersonality
    {
        public BotStyle Style;
        public double MinOut, MaxOut;            // excursion depth range (u), measured from the edge point E (section 9)
        public double MaxTrailLength;            // return when trail is longer
        public double ThreatRadius;              // enemy head distance to own trail that triggers return
        public double AttackRadius;
        public double AttackChance;
        public double LassoChance;
        public double Jitter;                    // radians of heading noise
        public double ReactionDelay;             // seconds: a new own spark or a new threat is ignored this long
        public double SenseRadius = 16;          // enemies farther than this (u) are invisible to the bot
        public double HumanAttackScale = 1;      // multiplies AttackChance when the target is the human

        /// <summary>A new instance with the preset values above (callers may modify it freely).</summary>
        public static BotPersonality Preset(BotStyle style)
        {
            switch (style)
            {
                case BotStyle.Balanced:
                    return Make(style, 4.5, 10, 34, 6, 7, 0.45, 0.5, 0.10, 0.30);
                case BotStyle.Greedy:
                    return Make(style, 5.5, 13, 45, 8, 5, 0.25, 0.8, 0.06, 0.40);
                case BotStyle.Aggressive:
                    return Make(style, 3, 7, 24, 8, 11, 0.75, 0.3, 0.12, 0.25);
                case BotStyle.Cautious:
                    return Make(style, 2.5, 5, 16, 8, 4, 0.15, 0.4, 0.08, 0.35);
                default:
                    throw new ArgumentOutOfRangeException(nameof(style), style, "unknown bot style");
            }
        }

        private static BotPersonality Make(BotStyle style, double minOut, double maxOut, double maxTrailLength,
                                           double threatRadius, double attackRadius, double attackChance,
                                           double lassoChance, double jitter, double reactionDelay)
        {
            return new BotPersonality
            {
                Style = style,
                MinOut = minOut,
                MaxOut = maxOut,
                MaxTrailLength = maxTrailLength,
                ThreatRadius = threatRadius,
                AttackRadius = attackRadius,
                AttackChance = attackChance,
                LassoChance = lassoChance,
                Jitter = jitter,
                ReactionDelay = reactionDelay,
            };
        }
    }
}
