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
