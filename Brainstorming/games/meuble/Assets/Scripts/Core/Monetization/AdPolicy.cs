namespace OutOfSight.Core
{
    /// <summary>ADSSHOP: why a level end shows an ad or not (logged, and read by the tests).</summary>
    public enum AdDecision
    {
        /// <summary>Show the ad (after <see cref="AdConfig.ShowDelaySeconds"/>, if the player is still on the panel).</summary>
        Show,
        /// <summary>The master switch is off (<see cref="AdConfig.Enabled"/>).</summary>
        Disabled,
        /// <summary>The player bought the No ads item.</summary>
        NoAdsOwned,
        /// <summary>This outcome (a win or a fail) does not show ads (<see cref="AdConfig.Placement"/>).</summary>
        PlacementOff,
        /// <summary>Before <see cref="AdConfig.FirstEligibleLevel"/>, or a level outside the play order.</summary>
        TooEarlyLevel,
        /// <summary>Not in <see cref="AdConfig.OnlyLevels"/>, or in <see cref="AdConfig.ExcludedLevels"/>.</summary>
        LevelExcluded,
        /// <summary>The level lasted less than <see cref="AdConfig.MinSecondsInLevel"/> (a quick fail or retry): not counted.</summary>
        QuickEnd,
        /// <summary><see cref="AdConfig.MaxAdsPerSession"/> reached.</summary>
        SessionCap,
        /// <summary>Within <see cref="AdConfig.MinSecondsAfterLaunch"/> of the session start.</summary>
        TooSoonAfterLaunch,
        /// <summary>Within <see cref="AdConfig.MinSecondsBetweenAds"/> of the last ad.</summary>
        Cooldown,
        /// <summary>Fewer than <see cref="AdConfig.EveryNLevelEnds"/> eligible ends since the last ad.</summary>
        NotEveryLevel,
    }

    /// <summary>ADSSHOP: one level end, as the policy sees it.</summary>
    public struct AdLevelEnd
    {
        public bool Won;
        public string LevelId;
        /// <summary>1-based position in the play order; 0 for a level outside it (never eligible).</summary>
        public int LevelNumber;
        /// <summary>The level's clock at the end (GameState.Elapsed).</summary>
        public float SecondsInLevel;
    }

    /// <summary>ADSSHOP: the session's ad bookkeeping (in memory: a new session starts fresh).</summary>
    public sealed class AdPolicyState
    {
        /// <summary>The session start, on the same clock as the "now" given to <see cref="AdPolicy.Decide"/>.</summary>
        public float SessionStart;

        /// <summary>When the last ad showed; negative when none did this session.</summary>
        public float LastAdAt = -1f;

        /// <summary>Eligible level ends counted since the last ad.</summary>
        public int EndsSinceAd;

        public int AdsThisSession;

        /// <summary>An ad really showed at <paramref name="now"/>: the cooldown and the every-N count start again.</summary>
        public void RecordShown(float now)
        {
            LastAdAt = now;
            EndsSinceAd = 0;
            AdsThisSession++;
        }
    }

    /// <summary>
    /// ADSSHOP: the frequency rules of the automatic end-of-level ad, the way successful casual games cap them: never on the
    /// first levels, never after a quick retry, never within the first minutes of a session, a cooldown in seconds
    /// between two ads, at most one ad every N eligible level ends, an optional cap per session, and never once the No ads
    /// item is owned. Pure: the only state is the <see cref="AdPolicyState"/> passed in.
    /// ADSEVERY: these rules are never weakened here. The Simulated provider's "every level end" override is a config the
    /// caller passes in (<see cref="AdConfig.PolicyFor"/>, every frequency rule off), so a real provider keeps them all.
    /// </summary>
    public static class AdPolicy
    {
        /// <summary>True when <paramref name="placement"/> lets a win (or a fail) show an ad.</summary>
        public static bool PlacementAllows(AdPlacement placement, bool won)
        {
            return placement == AdPlacement.Both || (won ? placement == AdPlacement.Win : placement == AdPlacement.Fail);
        }

        /// <summary>True when <paramref name="levelId"/> passes <see cref="AdConfig.OnlyLevels"/> and <see cref="AdConfig.ExcludedLevels"/>.</summary>
        public static bool LevelAllowed(AdConfig config, string levelId)
        {
            if (config.ExcludedLevels != null && levelId != null && config.ExcludedLevels.Contains(levelId))
            {
                return false;
            }
            return config.OnlyLevels == null || config.OnlyLevels.Count == 0 || (levelId != null && config.OnlyLevels.Contains(levelId));
        }

        /// <summary>
        /// The decision for <paramref name="end"/> at <paramref name="now"/>. An end that passes the level rules (enabled,
        /// not owned, placement, first level, level lists, long enough) counts toward <see cref="AdConfig.EveryNLevelEnds"/>
        /// (state.EndsSinceAd grows) even when the time rules then hold the ad back, so the first eligible end after a
        /// cooldown shows it. The caller records the ad with <see cref="AdPolicyState.RecordShown"/> only once it really
        /// showed (a network with no ad ready keeps the count for the next end).
        /// </summary>
        public static AdDecision Decide(AdConfig config, AdPolicyState state, AdLevelEnd end, float now, bool noAdsOwned)
        {
            if (config == null || state == null || !config.Enabled) // MUTATION:ADS_MASTER_SWITCH
            {
                return AdDecision.Disabled;
            }
            if (noAdsOwned) // MUTATION:ADS_NO_ADS_ENTITLEMENT
            {
                return AdDecision.NoAdsOwned;
            }
            if (!PlacementAllows(config.Placement, end.Won))
            {
                return AdDecision.PlacementOff;
            }
            if (end.LevelNumber < 1 || end.LevelNumber < config.FirstEligibleLevel) // MUTATION:ADS_FIRST_LEVEL
            {
                return AdDecision.TooEarlyLevel;
            }
            if (!LevelAllowed(config, end.LevelId))
            {
                return AdDecision.LevelExcluded;
            }
            if (end.SecondsInLevel < config.MinSecondsInLevel) // MUTATION:ADS_QUICK_END
            {
                return AdDecision.QuickEnd;
            }
            state.EndsSinceAd++;
            if (config.MaxAdsPerSession > 0 && state.AdsThisSession >= config.MaxAdsPerSession)
            {
                return AdDecision.SessionCap;
            }
            if (now - state.SessionStart < config.MinSecondsAfterLaunch)
            {
                return AdDecision.TooSoonAfterLaunch;
            }
            if (state.LastAdAt >= 0f && now - state.LastAdAt < config.MinSecondsBetweenAds) // MUTATION:ADS_COOLDOWN
            {
                return AdDecision.Cooldown;
            }
            if (state.EndsSinceAd < config.EveryNLevelEnds) // MUTATION:ADS_EVERY_N
            {
                return AdDecision.NotEveryLevel;
            }
            return AdDecision.Show;
        }
    }
}
