using System.Linq;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;

public sealed class EuropeLevelsTests
{
    [Test]
    public void EveryCountryHasAFlagAndFourPlayableStarts()
    {
        var countries = EuropeCatalog.Load().countries;
        Assert.That(countries.Select(country => country.code).Distinct().Count(), Is.EqualTo(46));
        CollectionAssert.IsSubsetOf(new[] { "GB", "TR", "CY", "VA", "XK" }, countries.Select(country => country.code));
        Assert.That(countries.Any(country => country.code == "RU"), Is.False);

        foreach (var country in countries)
        {
            Assert.That(Resources.Load<Texture2D>("EuropeFlags/" + country.code), Is.Not.Null, country.code);
            var config = new SimConfig();
            var setup = new SimSetup();
            country.Configure(config, setup);
            var sim = new Simulation(config, new IController[4], setup);
            Assert.That(sim.Arena.Polygon, Is.Not.Null, country.code);
            Assert.That(sim.Grid.ArenaCellCount, Is.GreaterThan(3000), country.code);
            Assert.That(sim.Players.All(player => player.Home), Is.True, country.code);
            Assert.That(sim.Players.All(player => sim.Grid.CountOf(player.Id) > 250), Is.True, country.code);
            Assert.That(sim.Grid.CountOf(OwnerGrid.Neutral), Is.GreaterThan(sim.Grid.ArenaCellCount / 2), country.code);
        }
    }

    /// <summary>
    /// Rule v1.7 (contract 31): every country has a conquest goal. The conquerable cells (Simulation.ConquestCellCount)
    /// leave out only the rim band and the pieces beyond thin necks, and stay above Conquest.LazyFloor of the arena
    /// cells (the lazy mask of Simulation.ConquestReached relies on it). Reports the smallest share and the slowest mask.
    /// </summary>
    [Test]
    public void EveryCountryHasAReachableConquestGoal()
    {
        double minShare = 1.0, maxMs = 0.0;
        string minCode = "", slowCode = "";
        foreach (var country in EuropeCatalog.Load().countries)
        {
            var config = new SimConfig();
            var setup = new SimSetup();
            country.Configure(config, setup);
            var sim = new Simulation(config, new IController[4], setup);
            var watch = System.Diagnostics.Stopwatch.StartNew();
            int conquerable = sim.ConquestCellCount;
            watch.Stop();
            double share = conquerable / (double)sim.Grid.ArenaCellCount;
            Assert.That(share, Is.GreaterThan(PainterIO.Core.Conquest.LazyFloor), country.code + " conquerable share " + share);
            Assert.That(sim.ConquestTargetCells, Is.LessThanOrEqualTo(conquerable), country.code);
            for (int i = 0; i < 4; i++)
            {
                Assert.That(sim.ConquestPercent(i), Is.GreaterThan(0.0), country.code + " start disc " + i + " counts");
            }
            if (share < minShare)
            {
                minShare = share;
                minCode = country.code;
            }
            if (watch.Elapsed.TotalMilliseconds > maxMs)
            {
                maxMs = watch.Elapsed.TotalMilliseconds;
                slowCode = country.code;
            }
        }
        Debug.Log("[EuropeLevels] smallest conquerable share " + minShare.ToString("F3") + " (" + minCode + "), slowest mask "
                  + maxMs.ToString("F1") + " ms (" + slowCode + ")");
        TestContext.WriteLine("smallest conquerable share " + minShare.ToString("F3") + " (" + minCode + "), slowest mask "
                              + maxMs.ToString("F1") + " ms (" + slowCode + ")");
    }

    [Test]
    public void CrossingANarrowInletCannotSkipTheBorder()
    {
        var outline = new[]
        {
            new Vec2d(-2, -2), new Vec2d(2, -2), new Vec2d(2, 2),
            new Vec2d(0.02, 2), new Vec2d(0.02, -1), new Vec2d(-0.02, -1),
            new Vec2d(-0.02, 2), new Vec2d(-2, 2)
        };
        var arena = new Arena(3, 0, 0.05, new ArenaPolygon(outline, new Vec2d(-1, 0)));
        var start = new Vec2d(-0.1, 1);
        var end = arena.Step(start, new Vec2d(0.3, 0), 0.6);
        Assert.That(end.X, Is.LessThanOrEqualTo(-0.07));
        Assert.That(arena.SignedDistance(end), Is.LessThanOrEqualTo(-arena.Margin));
        Assert.That(arena.Step(end, new Vec2d(0.03, 0.12), 0.6).Y, Is.GreaterThan(end.Y));
    }
}
