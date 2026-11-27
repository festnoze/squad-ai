// Europe campaign on the real map (docs/europe/PROGRESSION.md): the land graph derived from countries.json, the unlock
// rule on real countries (islands included), a full 46-country campaign, the JSON / PlayerPrefs round trip and the win
// definition. The rules themselves are also covered on synthetic maps by Core/EuropeProgressionTests.cs.
using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;

public sealed class EuropeProgressTests
{
    private const string TestKey = "pio.europe.progress.editmode-test";

    [TearDown]
    public void TearDown()
    {
        PlayerPrefs.DeleteKey(TestKey);
        EuropeProgress.StorageKey = null;
    }

    private static EuropeGraph Graph => EuropeProgress.Graph;

    [Test]
    public void RealGraph_SharedBordersAreSymmetricAndMatchTheMap()
    {
        EuropeGraph g = Graph;
        Assert.That(g.Count, Is.EqualTo(46));
        CollectionAssert.AreEquivalent(new[] { "ES", "CH", "BE", "IT", "DE", "LU", "AD", "MC" }, g.Neighbors("FR").Select(n => n.Code));
        Assert.That(g.Neighbors("FR")[0].Code, Is.EqualTo("ES"), "longest French land border");
        Assert.That(g.Neighbors("GB").Select(n => n.Code), Is.EqualTo(new[] { "IE" }));
        Assert.That(g.Neighbors("IT").Select(n => n.Code), Has.Member("VA").And.Member("SM"));
        foreach (string island in new[] { "CY", "IS", "MT" }) Assert.That(g.Neighbors(island), Is.Empty, island);
        foreach (string a in g.Codes)
        foreach (EuropeGraph.Neighbor n in g.Neighbors(a))
        {
            Assert.That(n.SharedLength, Is.GreaterThan(0), a + "-" + n.Code);
            Assert.That(g.SharedBorder(n.Code, a), Is.EqualTo(n.SharedLength).Within(1e-6), a + "-" + n.Code);
        }
        // Every country is connected to France by land but the islands, the UK-Ireland pair and, Russia being out of the
        // map, the Nordic block (Norway, Sweden, Finland): those are reached through the centroid fallback.
        var reached = new HashSet<string> { "FR" };
        var queue = new Queue<string>(reached);
        while (queue.Count > 0)
        foreach (EuropeGraph.Neighbor n in g.Neighbors(queue.Dequeue()))
            if (reached.Add(n.Code)) queue.Enqueue(n.Code);
        CollectionAssert.AreEquivalent(new[] { "CY", "FI", "GB", "IE", "IS", "MT", "NO", "SE" }, g.Codes.Where(c => !reached.Contains(c)));
    }

    [Test]
    public void StartState_AndFirstWinOnFrance()
    {
        var p = new EuropeProgression(Graph);
        Assert.That(p.PlayablePool(), Is.EqualTo(new[] { "FR" }));
        Assert.That(p.RecordWin("FR"), Is.EqualTo(new[] { "ES", "CH" }));
        Assert.That(p.PlayablePool(), Is.EqualTo(new[] { "CH", "ES" }));
        Assert.That(p.StateOf("BE"), Is.EqualTo(CountryProgress.Locked));
    }

    [Test]
    public void IslandFallback_UnitedKingdomAndIceland()
    {
        var p = new EuropeProgression(Graph);
        IReadOnlyList<string> uk = p.RecordWin("GB");
        Assert.That(uk.Count, Is.EqualTo(2));
        Assert.That(uk[0], Is.EqualTo("IE"), "the only land neighbor first");
        Assert.That(uk[1], Is.EqualTo(NearestLocked("GB", new[] { "FR", "GB", "IE" }, 1)[0]));

        var q = new EuropeProgression(Graph);
        IReadOnlyList<string> iceland = q.RecordWin("IS");
        Assert.That(iceland, Is.EqualTo(NearestLocked("IS", new[] { "FR", "IS" }, 2)));
        foreach (string code in new[] { "CY", "MT" })
        {
            var r = new EuropeProgression(Graph);
            Assert.That(r.RecordWin(code).Count, Is.EqualTo(2), code);
        }
    }

    [Test]
    public void ReplayOfAWonCountry_UnlocksNothing()
    {
        var p = new EuropeProgression(Graph);
        p.RecordWin("FR");
        string before = EuropeProgress.ToJson(p);
        Assert.That(p.RecordWin("FR"), Is.Empty);
        Assert.That(EuropeProgress.ToJson(p), Is.EqualTo(before));
    }

    [Test]
    public void FullCampaign_AllCountriesWon_PoolNeverEmpty_Deterministic()
    {
        string first = Walk(out int steps);
        Assert.That(steps, Is.EqualTo(46));
        Assert.That(Walk(out _), Is.EqualTo(first), "same history, same map");
    }

    private static string Walk(out int steps)
    {
        var p = new EuropeProgression(Graph);
        var log = new List<string>();
        steps = 0;
        while (p.WonCount < Graph.Count)
        {
            List<string> pool = p.PlayablePool();
            Assert.That(pool, Is.Not.Empty, "after " + steps + " wins");
            int locked = Graph.Count - p.UnlockedCount;
            IReadOnlyList<string> unlocked = p.RecordWin(pool[0]);
            Assert.That(unlocked.Count, Is.EqualTo(Mathf.Min(EuropeProgression.UnlocksPerFirstWin, locked)), pool[0]);
            log.Add(pool[0] + ">" + string.Join("+", unlocked));
            steps++;
            Assert.That(steps, Is.LessThanOrEqualTo(Graph.Count));
        }
        Assert.That(p.PlayablePool(), Is.Empty);
        return string.Join(" ", log);
    }

    [Test]
    public void SaveLoad_RoundTripThroughJsonAndPlayerPrefs()
    {
        var p = new EuropeProgression(Graph);
        p.RecordWin("FR");
        p.RecordWin("ES");
        string json = EuropeProgress.ToJson(p);
        StringAssert.Contains("\"version\":1", json);
        EuropeProgression back = EuropeProgress.FromJson(json);
        foreach (string code in Graph.Codes) Assert.That(back.StateOf(code), Is.EqualTo(p.StateOf(code)), code);
        Assert.That(back.PendingReveal, Is.EqualTo(p.PendingReveal));
        Assert.That(EuropeProgress.FromJson("not json").PlayablePool(), Is.EqualTo(new[] { "FR" }));

        EuropeProgress.StorageKey = TestKey;
        EuropeProgress.ResetProgress();
        EuropeProgress.RecordWin("FR");
        EuropeProgress.RecordWin("CH");
        string saved = EuropeProgress.ToJson(EuropeProgress.Current);
        EuropeProgress.StorageKey = TestKey;   // drops the cached campaign: the next read loads PlayerPrefs
        Assert.That(EuropeProgress.ToJson(EuropeProgress.Current), Is.EqualTo(saved));
        Assert.That(EuropeProgress.Current.StateOf("CH"), Is.EqualTo(CountryProgress.Won));
        EuropeProgress.ConsumeReveal();
        EuropeProgress.StorageKey = TestKey;
        Assert.That(EuropeProgress.Current.PendingReveal, Is.Empty);
    }

    [Test]
    public void WinDefinition_IsTheRankOneOfAStatsCountedRound()
    {
        Assert.That(EuropeProgress.IsCountedWin(true, false, new HumanOutcome { Rank = 1 }), Is.True);
        Assert.That(EuropeProgress.IsCountedWin(true, false, new HumanOutcome { Rank = 1, SharedRank = true }), Is.True);
        Assert.That(EuropeProgress.IsCountedWin(true, false, new HumanOutcome { Rank = 2 }), Is.False);
        Assert.That(EuropeProgress.IsCountedWin(false, false, new HumanOutcome { Rank = 1 }), Is.False, "attract, probe, DevShot");
        Assert.That(EuropeProgress.IsCountedWin(true, true, new HumanOutcome { Rank = 1 }), Is.False, "modified test settings");
        Assert.That(EuropeProgress.IsCountedWin(true, false, null), Is.False);
    }

    /// <summary>Brute force: the locked countries (all but <paramref name="unlocked"/>) nearest to the code by centroid.</summary>
    private static List<string> NearestLocked(string code, string[] unlocked, int count)
    {
        return Graph.Codes.Where(c => !unlocked.Contains(c))
            .OrderBy(c => Graph.CentroidDistance(code, c)).ThenBy(c => c, System.StringComparer.Ordinal)
            .Take(count).ToList();
    }
}
