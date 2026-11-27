using System;
using System.Collections.Generic;
using System.Linq;
using PainterIO.Core;

// A "novice" human: from home, picks a direction, goes out Depth u, turns 90 deg for Width u, then heads straight to
// the nearest own cell. Ignores threats. When chased, heads straight home (what the tutorial says).
sealed class Novice : IController
{
    readonly Random rng; readonly double depth, width;
    int phase; Vec2d a, b; bool wasHome = true, hadSpark; double dwellUntil;
    public Novice(int seed, double depth, double width) { rng = new Random(seed); this.depth = depth; this.width = width; }
    public double? DesiredHeading(SimView v, int i)
    {
        var p = v.Player(i);
        if (p.Spark != null) hadSpark = true;
        if (p.Spark != null || (phase == 3 && !p.Home))
        {
            if (GridQueries.NearestOwned(v.Grid, p.Id, p.Pos, 100, out Vec2d t, out double _)) return (t - p.Pos).Angle();
            return null;
        }
        if (p.Home)
        {
            if (!wasHome && (phase == 3 || hadSpark)) { phase = 0; dwellUntil = v.Time + 0.3; hadSpark = false; }
            wasHome = true;
            if (phase == 0)
            {
                if (v.Time < dwellUntil) return null;
                // aim outward: away from own start centroid toward the arena center with noise
                double ang = Math.Atan2(-p.Pos.Y, -p.Pos.X) + (rng.NextDouble() * 2 - 1) * 1.6;
                Vec2d dir = Vec2d.FromAngle(ang);
                a = Clamp(p.Pos + dir * (depth + 2.5));
                Vec2d side = Vec2d.FromAngle(ang + (rng.Next(2) == 0 ? 1 : -1) * Math.PI / 2);
                b = Clamp(a + side * width);
                phase = 1;
            }
            return (phase == 2 ? (b - p.Pos) : (a - p.Pos)).Angle();
        }
        wasHome = false;
        if (phase == 1 && (a - p.Pos).Length < 0.6) phase = 2;
        if (phase == 2 && (b - p.Pos).Length < 0.6) phase = 3;
        if (phase == 1) return (a - p.Pos).Angle();
        if (phase == 2) return (b - p.Pos).Angle();
        return null;
    }
    static Vec2d Clamp(Vec2d q) { double m = 27; return new Vec2d(Math.Max(-m, Math.Min(m, q.X)), Math.Max(-m, Math.Min(m, q.Y))); }
}

static class P
{
    static ulong BotSeed(ulong s, int i) => s * 7919UL + (ulong)i * 104729UL + 17UL;
    static void Main()
    {
        foreach (var spf in new[] { 1.8, 1.5 }) foreach (var human in new[] { "balancedProxy" })
        foreach (var scale in new[] { 1.0, 0.3 })
        {
            int N = 120; int alive = 0, first = 0; double area = 0; int exits = 0, cutExits = 0, deaths = 0;
            var deathTimes = new List<double>(); var cutBy = new int[4]; int savedReturns = 0, captures = 0; var gaps = new List<double>();
            int caughtFast = 0; var delays = new List<double>();
            for (int seed = 1; seed <= N; seed++)
            {
                var cfg = new SimConfig { Seed = (ulong)seed, LassoEnabled = false, SparkSpeedFactor = spf };
                var ctr = new IController[4];
                if (human == "novice") ctr[0] = new Novice(seed, 7, 6);
                else { var bp = BotPersonality.Preset(BotStyle.Balanced); ctr[0] = new BotController(bp, BotSeed((ulong)seed, 0)); }
                BotStyle[] lineup = { BotStyle.Balanced, BotStyle.Greedy, BotStyle.Aggressive };
                for (int i = 1; i < 4; i++) { var bp = BotPersonality.Preset(lineup[i - 1]); bp.HumanAttackScale = scale; ctr[i] = new BotController(bp, BotSeed((ulong)seed, i)); }
                var sim = new Simulation(cfg, ctr, new SimSetup { HumanIndex = 0 });
                double cutTime = -1;
                sim.EventRaised += e =>
                {
                    if (e.Player != 0) return;
                    if (e.Type == SimEventType.Exit) exits++;
                    if (e.Type == SimEventType.Cut) { cutExits++; if (e.Other >= 0) cutBy[e.Other]++; cutTime = e.Time; gaps.Add(sim.Players[0].Trail.Length - e.S); }
                    if (e.Type == SimEventType.Return) { if (e.Chased) savedReturns++; else if (e.Cells != null && e.Cells.Length > 0) captures++; }
                    if (e.Type == SimEventType.SparkCaught) { if (cutTime >= 0 && e.Time - cutTime < 0.6) caughtFast++; if (cutTime >= 0) delays.Add(e.Time - cutTime); }
                    if (e.Type == SimEventType.Eliminated) { deaths++; deathTimes.Add(e.Time); }
                };
                while (!sim.Ended) sim.Step();
                if (sim.Players[0].Alive) alive++;
                if (sim.Result.Ranks[0] == 1) first++;
                area += sim.Result.FinalAreaPercent[0];
            }
            deathTimes.Sort(); gaps.Sort();
            delays.Sort(); Console.WriteLine($"spark={spf} medianCatchDelay={(delays.Count>0?delays[delays.Count/2]:0):0.00}s p90CatchDelay={(delays.Count>0?delays[(int)(delays.Count*0.9)]:0):0.00}s"); Console.WriteLine($"human={human,-14} botHumanScale={scale:0.0}  alive={100.0 * alive / N:0}%  first={100.0 * first / N:0}%  meanFinalArea={area / N:0.0}%  exits/round={exits / (double)N:0.0}  cuts/round={cutExits / (double)N:0.00}  cut%ofExits={100.0 * cutExits / Math.Max(1, exits):0}%  captures/round={captures / (double)N:0.0} savedChases/round={savedReturns / (double)N:0.00} deaths={deaths} medianDeathT={(deathTimes.Count > 0 ? deathTimes[deathTimes.Count / 2] : 0):0}s caughtWithin0.6s={caughtFast}/{deaths} cutBy[B,G,A]={cutBy[1]},{cutBy[2]},{cutBy[3]} medianGapAtCut={(gaps.Count > 0 ? gaps[gaps.Count / 2] : 0):0.0}u");
        }
    }
}




