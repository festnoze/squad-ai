// The Europe campaign of the player (docs/europe/PROGRESSION.md): the pure rules of PainterIO.Core.EuropeProgression,
// the land graph built once from EuropeCatalog, its own PlayerPrefs key (small JSON, independent of SaveData), the round
// win hook called by GameDirector.ShowResults and the command line test flags:
//   -europe-reset          back to a new campaign (saved)
//   -europe-wins FR,ES,... records these wins in order, as real first wins would (saved)
//   -europe-unlockall      every country playable (saved)
// They apply once per run, in this order, the first time Current is read.
using System;
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    public static class EuropeProgress
    {
        /// <summary>PlayerPrefs key of the campaign JSON (EuropeProgressData).</summary>
        public const string PrefsKey = "pio.europe.progress";

        private static EuropeGraph graph;
        private static EuropeProgression current;
        private static string storageKey = PrefsKey;
        private static bool launchArgsApplied;

        /// <summary>Raised after every change of Current (win, reset, unlock all, reveal played).</summary>
        public static event Action Changed;

        /// <summary>The land graph of the 46 countries (shared edges and centroids of countries.json), built once.</summary>
        public static EuropeGraph Graph => graph ?? (graph = BuildGraph(EuropeCatalog.Load()));

        /// <summary>The player's campaign, loaded on first use (the command line test flags apply then).</summary>
        public static EuropeProgression Current
        {
            get
            {
                if (current != null) return current;
                current = Load(storageKey);
                if (!launchArgsApplied)
                {
                    launchArgsApplied = true;
                    ApplyLaunchArgs(current);
                }
                return current;
            }
        }

        /// <summary>Tests only: another PlayerPrefs key (null restores PrefsKey); Current reloads from it.</summary>
        public static string StorageKey
        {
            get => storageKey;
            set
            {
                storageKey = string.IsNullOrEmpty(value) ? PrefsKey : value;
                current = null;
            }
        }

        public static EuropeGraph BuildGraph(EuropeCatalog catalog)
        {
            var shapes = new List<EuropeGraph.Shape>();
            foreach (EuropeCatalog.Country country in catalog.countries)
            {
                var shape = new EuropeGraph.Shape { Code = country.code };
                foreach (EuropeCatalog.Part part in country.parts)
                {
                    shape.Rings.Add(ToRing(part.outer));
                    if (part.holes == null) continue;
                    foreach (EuropeCatalog.Ring hole in part.holes) shape.Rings.Add(ToRing(hole.points));
                }
                shapes.Add(shape);
            }
            return EuropeGraph.FromShapes(shapes);
        }

        private static Vec2d[] ToRing(EuropeCatalog.Point[] points) =>
            points == null ? new Vec2d[0] : Array.ConvertAll(points, p => new Vec2d(p.x, p.y));

        // ------------------------------------------------------------------------------------------------------------
        // Persistence.

        public static string ToJson(EuropeProgression progression) => JsonUtility.ToJson(progression.ToData());

        /// <summary>A campaign from JSON; a new campaign when the text is empty or unreadable.</summary>
        public static EuropeProgression FromJson(string json)
        {
            EuropeProgressData data = null;
            if (!string.IsNullOrEmpty(json))
            {
                try { data = JsonUtility.FromJson<EuropeProgressData>(json); }
                catch (Exception e) { Debug.LogWarning("[PainterIO] Europe progress unreadable, starting over: " + e.Message); }
            }
            return EuropeProgression.FromData(Graph, data);
        }

        public static EuropeProgression Load(string key)
        {
            string json = null;
            try { json = PlayerPrefs.GetString(key, null); }
            catch (Exception e) { Debug.LogWarning("[PainterIO] Europe progress load failed: " + e.Message); }
            return FromJson(json);
        }

        /// <summary>Writes Current under StorageKey and flushes PlayerPrefs (changes are rare: wins, resets).</summary>
        public static void Save()
        {
            if (current == null) return;
            try
            {
                PlayerPrefs.SetString(storageKey, ToJson(current));
                PlayerPrefs.Save();
            }
            catch (Exception e)
            {
                Debug.LogWarning("[PainterIO] Europe progress save failed: " + e.Message);
            }
        }

        private static void Commit()
        {
            Save();
            Action handler = Changed;
            if (handler == null) return;
            foreach (Delegate d in handler.GetInvocationList())
            {
                try { ((Action)d)(); }
                catch (Exception e) { Debug.LogError("[PainterIO] EuropeProgress.Changed subscriber failed: " + e); }
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Game hooks.

        /// <summary>
        /// The game's round victory, as counted in SaveData.Wins by GameDirector.RecordStats: a real round (not attract,
        /// probe, DevShot or test sessions), with stats-valid settings (no modified test tuning, no command line override),
        /// that the human finished first (rank 1, shared first place included).
        /// </summary>
        public static bool IsCountedWin(bool countsForStats, bool tuned, HumanOutcome outcome) =>
            countsForStats && !tuned && outcome != null && outcome.Rank == 1;

        /// <summary>Called by GameDirector.ShowResults after every real round: records a win on a country round.</summary>
        public static void OnRoundResults(GameSession session, HumanOutcome outcome, EuropeCatalog.Country country)
        {
            if (session == null || session.IsAttract || country == null) return;
            bool tuned = SaveData.TuningModified || LaunchArgs.HasTuningOverride;
            if (!IsCountedWin(session.CountsForStats, tuned, outcome)) return;
            RecordWin(country.code);
        }

        /// <summary>Records a win on the country; returns the newly unlocked countries (empty on a replay).</summary>
        public static IReadOnlyList<string> RecordWin(string code)
        {
            IReadOnlyList<string> unlocked = Current.RecordWin(code);
            Debug.Log("[PainterIO] Europe win " + code + (unlocked.Count > 0 ? ", unlocked " + string.Join(",", unlocked) : ", nothing new"));
            Commit();
            return unlocked;
        }

        /// <summary>The hidden "Réinitialiser la progression" action and -europe-reset.</summary>
        public static void ResetProgress()
        {
            Current.Reset();
            Commit();
        }

        public static void UnlockAll()
        {
            Current.UnlockAll();
            Commit();
        }

        /// <summary>The map played the reveal of the newly unlocked flags.</summary>
        public static void ConsumeReveal()
        {
            if (Current.PendingReveal.Count == 0) return;
            Current.ClearReveal();
            Commit();
        }

        private static void ApplyLaunchArgs(EuropeProgression progression)
        {
            bool changed = false;
            if (LaunchArgs.Has("-europe-reset"))
            {
                progression.Reset();
                changed = true;
            }
            string wins = LaunchArgs.Value("-europe-wins");
            if (!string.IsNullOrEmpty(wins) && !wins.StartsWith("-", StringComparison.Ordinal))
            {
                foreach (string raw in wins.Split(new[] { ',', ';' }, StringSplitOptions.RemoveEmptyEntries))
                    progression.RecordWin(raw.Trim().ToUpperInvariant());
                changed = true;
            }
            if (LaunchArgs.Has("-europe-unlockall"))
            {
                progression.UnlockAll();
                changed = true;
            }
            if (!changed) return;
            Debug.Log("[PainterIO] Europe progress from the command line: " + ToJson(progression));
            Save();
        }
    }
}
