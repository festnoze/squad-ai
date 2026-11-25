using System.Collections;
using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// ADSSHOP (docs/next/progress/ADSSHOP.md): the hook between the end-of-level flow and <see cref="AdService"/>, built
    /// by Main after the menus. It only listens to <see cref="GameState.StateChanged"/>: gameplay is untouched. At a win
    /// (not the last level's end screen) or a fail, it asks the policy; on "Show" it waits
    /// <see cref="AdConfig.ShowDelaySeconds"/> with the win or fail panel up, then shows the ad, but only if the player is
    /// still on that panel (a Retry, a Next level or a menu opened meanwhile cancels it, so an ad never interrupts play).
    /// A spectator run never ends, so it never shows one.
    /// ADSEVERY (2026-11-25): with the Simulated provider and ads.json "simulatedEveryLevelEnd", every win and fail asks
    /// for an ad, the finale included (<see cref="AdService.EveryLevelEnd"/>); the delay and the "still on the panel" check
    /// stay, so a quick Retry still cancels it and two overlays never stack.
    /// </summary>
    public sealed class AdDirector : MonoBehaviour
    {
        public GameState Game;
        public Menu Menu;
        public Hud Hud;

        /// <summary>The ads really shown by this director (tests, logs).</summary>
        public int Shown { get; private set; }

        /// <summary>An ad is waiting for its delay to run out.</summary>
        public bool Pending => pending != null;

        private Coroutine pending;

        public void Init(GameState game, Menu menu, Hud hud)
        {
            Game = game;
            Menu = menu;
            Hud = hud;
            if (Game != null)
            {
                Game.StateChanged -= OnStateChanged;
                Game.StateChanged += OnStateChanged;
            }
        }

        private void OnDestroy()
        {
            if (Game != null)
            {
                Game.StateChanged -= OnStateChanged;
            }
        }

        /// <summary>ADSEVERY: an ad on screen keeps the game paused and silent, whatever a menu toggle did under it.</summary>
        private void LateUpdate()
        {
            AdService.KeepAdPause();
        }

        private void OnStateChanged(PlayState state)
        {
            if (state != PlayState.Won && state != PlayState.Caught)
            {
                return;
            }
            if (Game == null || Game.Spectator || !AdService.Active)
            {
                return;
            }
            // The last level's end screen is the game's finale: never an ad over it with a real provider. ADSEVERY: the
            // Simulated provider's "every level end" override shows one there too (its button is reselected after it).
            bool everyEnd = AdService.EveryLevelEnd;
            if (state == PlayState.Won && Game.IsLastLevel && !everyEnd)
            {
                return;
            }
            var end = new AdLevelEnd
            {
                Won = state == PlayState.Won,
                LevelId = Game.LevelId,
                LevelNumber = LevelNumber(Game.LevelOrder, Game.LevelId),
                SecondsInLevel = Game.Elapsed,
            };
            AdDecision decision = AdService.EvaluateLevelEnd(end);
            Debug.Log($"[Ads] {(end.Won ? "win" : "fail")} of {end.LevelId} (#{end.LevelNumber}) after {end.SecondsInLevel:0.0} s: {decision}"
                + (everyEnd ? " (simulation: every level end)" : string.Empty));
            if (decision != AdDecision.Show)
            {
                return;
            }
            if (pending != null)
            {
                StopCoroutine(pending);
            }
            pending = StartCoroutine(ShowAfterDelay(state, end.LevelId, end.Won ? "level_end_win" : "level_end_fail"));
        }

        /// <summary>The 1-based position of <paramref name="levelId"/> in <paramref name="order"/>, 0 when it is not listed.</summary>
        public static int LevelNumber(IReadOnlyList<string> order, string levelId)
        {
            if (order == null || levelId == null)
            {
                return 0;
            }
            for (int i = 0; i < order.Count; i++)
            {
                if (order[i] == levelId)
                {
                    return i + 1;
                }
            }
            return 0;
        }

        private IEnumerator ShowAfterDelay(PlayState state, string levelId, string placement)
        {
            float until = Time.realtimeSinceStartup + AdService.Config.ShowDelaySeconds;
            while (Time.realtimeSinceStartup < until)
            {
                if (!StillOnPanel(state, levelId))
                {
                    pending = null;
                    yield break;
                }
                yield return null;
            }
            pending = null;
            if (!StillOnPanel(state, levelId))
            {
                yield break;
            }
            aShowNow(placement);
        }

        /// <summary>The level still sits on the same end (no retry, no next level, no menu, the panel up).</summary>
        private bool StillOnPanel(PlayState state, string levelId)
        {
            if (Game == null || Game.State != state || Game.LevelId != levelId || AdService.Showing)
            {
                return false;
            }
            if (Menu != null && Menu.IsOpen)
            {
                return false;
            }
            return Hud == null || Hud.WinVisible || Hud.FailVisible;
        }

        private async void aShowNow(string placement)
        {
            AdShowResult result = await AdService.aShowAd(AdService.AutomaticFormat, placement);
            if (result.Shown)
            {
                Shown++;
            }
        }
    }
}
