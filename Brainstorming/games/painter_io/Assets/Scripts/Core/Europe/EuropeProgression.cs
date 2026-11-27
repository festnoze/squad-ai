using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>State of one country in the Europe campaign (docs/europe/PROGRESSION.md).</summary>
    public enum CountryProgress
    {
        /// <summary>Not playable yet (dimmed on the map, skipped by the arrows).</summary>
        Locked = 0,
        /// <summary>Playable, not won yet: a floating flag stands on it.</summary>
        Unlocked = 1,
        /// <summary>Won at least once: shown as conquered. Still playable.</summary>
        Won = 2,
    }

    /// <summary>The saved form of a campaign (JSON through JsonUtility in PainterIO.Runtime.EuropeProgress).</summary>
    [Serializable]
    public sealed class EuropeProgressData
    {
        public int version;
        /// <summary>Countries won at least once, ordinal order.</summary>
        public string[] won;
        /// <summary>Countries playable (won ones included), ordinal order.</summary>
        public string[] unlocked;
        /// <summary>Countries unlocked by the last first wins whose flags the map has not revealed yet, in unlock order.</summary>
        public string[] reveal;
    }

    /// <summary>
    /// The Europe campaign rules, pure C# (no UnityEngine) so they are unit tested: one start country; the FIRST win on a
    /// country unlocks up to UnlocksPerFirstWin still locked countries, its locked land neighbors first (longest shared
    /// border, then nearest centroid, then code), then the nearest locked countries by centroid (islands); replaying a
    /// won country unlocks nothing. The same history always gives the same map.
    /// </summary>
    public sealed class EuropeProgression
    {
        /// <summary>The only country unlocked in a new campaign.</summary>
        public const string StartCountry = "FR";

        /// <summary>How many locked countries the first win on a country unlocks (fewer when not enough are left).</summary>
        public const int UnlocksPerFirstWin = 2;

        /// <summary>Version written in EuropeProgressData.version.</summary>
        public const int DataVersion = 1;

        private readonly HashSet<string> won = new HashSet<string>(StringComparer.Ordinal);
        private readonly HashSet<string> unlocked = new HashSet<string>(StringComparer.Ordinal);
        private readonly List<string> reveal = new List<string>();

        public EuropeProgression(EuropeGraph graph)
        {
            Graph = graph ?? throw new ArgumentNullException(nameof(graph));
            if (!graph.Contains(StartCountry)) throw new ArgumentException("The map has no start country " + StartCountry + ".", nameof(graph));
            Reset();
        }

        public EuropeGraph Graph { get; }

        public int WonCount => won.Count;

        public int UnlockedCount => unlocked.Count;

        /// <summary>Unlocked countries not won yet (the floating flags), ordinal order.</summary>
        public List<string> PlayablePool()
        {
            var pool = new List<string>();
            foreach (string code in Graph.Codes)
            {
                if (unlocked.Contains(code) && !won.Contains(code)) pool.Add(code);
            }
            return pool;
        }

        /// <summary>Countries unlocked by first wins whose reveal the map has not played yet, in unlock order.</summary>
        public IReadOnlyList<string> PendingReveal => reveal;

        public CountryProgress StateOf(string code)
        {
            if (code != null && won.Contains(code)) return CountryProgress.Won;
            if (code != null && unlocked.Contains(code)) return CountryProgress.Unlocked;
            return CountryProgress.Locked;
        }

        /// <summary>"Jouer ce pays" is allowed: the country is unlocked or won.</summary>
        public bool IsPlayable(string code) => StateOf(code) != CountryProgress.Locked;

        /// <summary>
        /// A round won on the country. The first win unlocks countries (PickUnlocks) and queues them for the map's reveal;
        /// a replay of a won country, or an unknown code, changes nothing. A win on a locked country (only reachable
        /// through the test hooks) unlocks it first. Returns the newly unlocked countries, in unlock order.
        /// </summary>
        public IReadOnlyList<string> RecordWin(string code)
        {
            if (!Graph.Contains(code) || won.Contains(code)) return Array.Empty<string>();
            unlocked.Add(code);
            won.Add(code);
            reveal.Remove(code);   // won before the map revealed its flag: nothing left to reveal
            List<string> picks = PickUnlocks(Graph, code, c => !unlocked.Contains(c), UnlocksPerFirstWin);
            foreach (string pick in picks)
            {
                unlocked.Add(pick);
                if (!reveal.Contains(pick)) reveal.Add(pick);
            }
            return picks;
        }

        /// <summary>
        /// The unlock rule, kept in one place. Up to <paramref name="count"/> codes for which <paramref name="isLocked"/>
        /// is true: first the land neighbors of <paramref name="wonCode"/> (longest shared border, then nearest centroid,
        /// then ordinal code), then the other countries by centroid distance to it (then ordinal code).
        /// </summary>
        public static List<string> PickUnlocks(EuropeGraph graph, string wonCode, Func<string, bool> isLocked, int count)
        {
            var picks = new List<string>();
            if (graph == null || isLocked == null || count <= 0 || !graph.Contains(wonCode)) return picks;
            var neighbors = new List<EuropeGraph.Neighbor>();
            foreach (EuropeGraph.Neighbor n in graph.Neighbors(wonCode))
            {
                if (isLocked(n.Code)) neighbors.Add(n);
            }
            neighbors.Sort((a, b) =>
            {
                int byBorder = b.SharedLength.CompareTo(a.SharedLength);
                if (byBorder != 0) return byBorder;
                int byDistance = graph.CentroidDistance(wonCode, a.Code).CompareTo(graph.CentroidDistance(wonCode, b.Code));
                return byDistance != 0 ? byDistance : string.CompareOrdinal(a.Code, b.Code);
            });
            for (int i = 0; i < neighbors.Count && picks.Count < count; i++) picks.Add(neighbors[i].Code);
            if (picks.Count >= count) return picks;

            var others = new List<string>();
            foreach (string code in graph.Codes)
            {
                if (code != wonCode && isLocked(code) && !picks.Contains(code)) others.Add(code);
            }
            others.Sort((a, b) =>
            {
                int byDistance = graph.CentroidDistance(wonCode, a).CompareTo(graph.CentroidDistance(wonCode, b));
                return byDistance != 0 ? byDistance : string.CompareOrdinal(a, b);
            });
            for (int i = 0; i < others.Count && picks.Count < count; i++) picks.Add(others[i]);
            return picks;
        }

        /// <summary>Back to a new campaign: only StartCountry unlocked, nothing won, no reveal pending.</summary>
        public void Reset()
        {
            won.Clear();
            unlocked.Clear();
            reveal.Clear();
            unlocked.Add(StartCountry);
        }

        /// <summary>Test hook (-europe-unlockall): every country playable, wins kept, no reveal.</summary>
        public void UnlockAll()
        {
            foreach (string code in Graph.Codes) unlocked.Add(code);
            reveal.Clear();
        }

        /// <summary>The map played the reveal of the pending countries.</summary>
        public void ClearReveal() => reveal.Clear();

        public EuropeProgressData ToData()
        {
            return new EuropeProgressData
            {
                version = DataVersion,
                won = Sorted(won),
                unlocked = Sorted(unlocked),
                reveal = reveal.ToArray(),
            };
        }

        /// <summary>
        /// A campaign from saved data. Unknown codes are dropped, won countries count as unlocked, StartCountry is always
        /// unlocked and a reveal only lists unlocked, not won countries. Null data gives a new campaign.
        /// </summary>
        public static EuropeProgression FromData(EuropeGraph graph, EuropeProgressData data)
        {
            var progression = new EuropeProgression(graph);
            if (data == null) return progression;
            if (data.unlocked != null)
            {
                foreach (string code in data.unlocked)
                {
                    if (graph.Contains(code)) progression.unlocked.Add(code);
                }
            }
            if (data.won != null)
            {
                foreach (string code in data.won)
                {
                    if (!graph.Contains(code)) continue;
                    progression.won.Add(code);
                    progression.unlocked.Add(code);
                }
            }
            if (data.reveal != null)
            {
                foreach (string code in data.reveal)
                {
                    if (graph.Contains(code) && progression.StateOf(code) == CountryProgress.Unlocked && !progression.reveal.Contains(code))
                        progression.reveal.Add(code);
                }
            }
            return progression;
        }

        private static string[] Sorted(HashSet<string> set)
        {
            var list = new List<string>(set);
            list.Sort(string.CompareOrdinal);
            return list.ToArray();
        }
    }
}
