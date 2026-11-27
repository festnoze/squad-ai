// Owned by A4 (sim). The section 6 event engine: step 1 (controllers, motion, visit lists), step 2 (candidate events,
// grouping by EventEpsilonSeconds, fixed application order a-g with re-validation) and step 3 (end of tick).
//
// Parameter convention (section 6, normative): every in-tick value is a TICK parameter u in [0, uEnd] with
// p_i(u) = p0_i + u (p1_i - p0_i). Queries always receive the full tick segment (p0, p1) and uMin = uCur. For each
// trailing player uTrailEnd_i is the tick u at which the stored trail end equals the head, so its trail length at u is
// L_i(u) = Trail.Length + growth_i (u - uTrailEnd_i).
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    internal sealed class EventResolver
    {
        // ShieldEnd (docs/BIOME_TRAITS.md 7.1, kill-core) is appended last so the in-group order of the older kinds is
        // unchanged.
        private enum Kind { Return, Exit, SparkCatch, Cut, Lasso, Pickup, TimeUp, ShieldEnd }

        private struct Candidate
        {
            public Kind Kind;
            public double U;          // tick parameter of this member (its own geometry uses it)
            public int Player;        // returner, exiter, caught victim, cut victim, lasso owner, picker
            public int Attacker;      // Cut only
            public Vec2d Point;       // Return / Exit crossing point, Lasso X
            public double S;          // Cut: s_cut. ShieldEnd: the shield end time the candidate was computed for
            public int TrailVersion;  // Cut (victim trail), Lasso (owner trail)
            public int Segment;       // Lasso: crossed segment k
            public List<Vec2d> Loop;  // Lasso: loop polygon taken BEFORE X is appended (section 8)
        }

        // Validity of a lasso loop for one (player, trail version, segment, u) within the current tick, so the event
        // loop does not rasterize the same loop again after every group.
        private struct LoopCacheEntry
        {
            public int Player, Version, Segment;
            public double U;
            public bool Valid;
            public List<Vec2d> Loop;
        }

        private readonly Simulation sim;
        private readonly SimConfig cfg;
        private readonly OwnerGrid grid;
        private readonly PlayerState[] players;
        private readonly int n;

        // Per-tick state (step 1).
        private readonly Vec2d[] p0, p1;
        private readonly double[] growth, uTrailEnd;
        private readonly List<CellEntry>[] visits;
        private readonly double?[] desired;
        private double t0, dt, uEnd;
        private bool lastTick;

        // Buffers reused across ticks.
        private readonly List<Candidate> candidates = new List<Candidate>();
        private readonly List<Candidate> group = new List<Candidate>();
        private readonly List<SelfCrossing> crossings = new List<SelfCrossing>();
        private readonly List<LoopCacheEntry> loopCache = new List<LoopCacheEntry>();
        private readonly int[] snapshot;          // owned cells at the start of the group (FinalCells, R19)
        private readonly bool[] aliveAtStart;     // alive at the start of the group (cuts, step c)
        private readonly List<int> eliminatedInGroup = new List<int>();
        private readonly List<KillInfo> killsInGroup = new List<KillInfo>();   // Spark eliminations (kill traits only)
        private readonly List<KillInfo> rewarded = new List<KillInfo>();
        private bool rewardedInGroup;                                          // kill traits ran in the current group
        private readonly List<Candidate> pending = new List<Candidate>();      // ReturnsBeforeRoundEnd
        private readonly List<Candidate> saved = new List<Candidate>();
        private readonly List<Vec2d> outlineInput = new List<Vec2d>();
        private readonly List<int> freed = new List<int>();
        private readonly List<int> maskIndices = new List<int>();
        private readonly CellMask pocketScratch;
        private readonly double[] pickupIn, pickupOut;
        private readonly List<double> pickupTimes = new List<double>();

        // Rule v1.5 (contract 29), per player index: the victims of one step a, the cells each lost to other players, the
        // anchor cell (taken on the grid before the captures), the index of its own return in the step (-1 when none),
        // and the split analysis (severed cells with the cutter of their group).
        private readonly bool[] severVictim;
        private readonly List<int>[] severLost;
        private readonly int[] severAnchor, severOwnReturn;
        private readonly List<int>[] severCells, severCutter;
        private readonly List<int> severScratch = new List<int>();

        // Rule v1.6 (single domain and kill inheritance bridge, contract 30). singleDomain is fixed for the round
        // (Simulation.SingleDomain: KillInheritance with Share > 0 and SimConfig.InheritanceBridge not Off, or rule v1.8);
        // none of the code below runs otherwise. Rule v1.8 (contract 32): linkBands = SimConfig.SingleDomain On, the
        // guarantee in every round type (closures take the band of their trail, LinkCapture); inheritanceJoin = the v1.6
        // kill inheritance path (KillInheritance attached with Share > 0). With SingleDomain Off both keep the v1.6 meaning,
        // so classic rounds and the other trait sets keep their exact pre-v1.8 behaviour.
        private readonly bool singleDomain;
        private readonly bool linkBands;
        private readonly bool inheritanceJoin;
        private readonly List<int> linkExtra = new List<int>();
        private readonly List<int> domainSevered = new List<int>();
        private readonly List<int> domainSeveredWithBand = new List<int>();
        private readonly List<int> bandCells = new List<int>();
        private readonly List<int> bandExtra = new List<int>();
        private readonly List<Vec2d> bandLine = new List<Vec2d>();
        private readonly List<int> bandWho = new List<int>(1);
        private readonly List<int> footprint = new List<int>();
        private CellMask bandMask;

        public EventResolver(Simulation sim)
        {
            this.sim = sim;
            cfg = sim.Config;
            grid = sim.Grid;
            players = sim.PlayerArray;
            n = players.Length;
            singleDomain = sim.SingleDomain;
            linkBands = singleDomain && cfg.SingleDomain == SingleDomainRule.On;
            inheritanceJoin = singleDomain && sim.Inheritance != null && sim.Inheritance.Share > 0.0;
            p0 = new Vec2d[n];
            p1 = new Vec2d[n];
            growth = new double[n];
            uTrailEnd = new double[n];
            desired = new double?[n];
            visits = new List<CellEntry>[n];
            for (int i = 0; i < n; i++) visits[i] = new List<CellEntry>(8);
            snapshot = new int[n];
            aliveAtStart = new bool[n];
            pickupIn = new double[n];
            pickupOut = new double[n];
            pocketScratch = new CellMask(grid.Size);
            severVictim = new bool[n];
            severAnchor = new int[n];
            severOwnReturn = new int[n];
            severLost = new List<int>[n];
            severCells = new List<int>[n];
            severCutter = new List<int>[n];
            for (int i = 0; i < n; i++)
            {
                severLost[i] = new List<int>();
                severCells[i] = new List<int>();
                severCutter[i] = new List<int>();
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Step 1: controllers, turn (R3), border (R4), full-step targets and visit lists.

        public void BeginTick(double tickStart, double tickUEnd, bool isLastTick)
        {
            t0 = tickStart;
            dt = cfg.Dt;
            uEnd = tickUEnd;
            lastTick = isLastTick;
            loopCache.Clear();

            // Poll every alive controller first, so no controller sees another player's half-updated state.
            IController[] controllers = sim.Controllers;
            SimView view = sim.View;
            for (int i = 0; i < n; i++)
            {
                desired[i] = null;
                if (players[i].Alive && controllers[i] != null) desired[i] = controllers[i].DesiredHeading(view, i);
            }

            double maxTurn = cfg.TurnRateRad * dt;
            double stepLength = cfg.PawnSpeed * dt;
            double hold = cfg.BorderHoldAngleRad;
            bool speedTraits = sim.Behaviours.Length > 0;
            bool rideOn = cfg.BorderRide == BorderRideRule.On;
            for (int i = 0; i < n; i++)
            {
                PlayerState p = players[i];
                uTrailEnd[i] = 0.0;
                if (!p.Alive)
                {
                    p.PrevPos = p.Pos;
                    p0[i] = p.Pos;
                    p1[i] = p.Pos;
                    growth[i] = 0.0;
                    visits[i].Clear();
                    continue;
                }
                double? want = desired[i];
                if (want.HasValue && !double.IsNaN(want.Value) && !double.IsInfinity(want.Value)) p.DesiredHeading = want.Value;
                p.Heading = Geo.MoveTowardsAngle(p.Heading, p.DesiredHeading, maxTurn);

                Vec2d a = p.Pos;
                // Traits (BIOME_TRAITS section 6 step 1 and 7.1): tick speed = PawnSpeed x SpeedMultiplier x the behaviours'
                // speed factor (Conduction when home), all read at tick start, for this whole tick. Classic rounds
                // (SpeedMultiplier 1, no behaviour) keep the exact classic step.
                double step = stepLength;
                double factor = p.SpeedMultiplier;
                if (speedTraits) factor *= sim.SpeedFactorOf(p);
                if (factor != 1.0) step = stepLength * factor;
                // Rule v1.9 (contract 33): with the border ride on, BorderRide.Move replaces the R4 step (x BorderRideFactor
                // and boundary following while riding). Off keeps the exact R4 call.
                Vec2d b = rideOn
                    ? BorderRide.Move(sim, p, a, step, hold, t0, dt)
                    : sim.Arena.Step(a, Vec2d.FromAngle(p.Heading) * step, hold);
                p0[i] = a;
                p1[i] = b;
                p.PrevPos = a;
                growth[i] = Vec2d.Distance(a, b);
                if (lastTick)
                {
                    // R19 (audit A6 fix): a cell edge reached exactly at t = RoundDuration can round to U = uEnd + 1e-15.
                    // On other ticks that entry simply shows up at U ~ 0 of the next tick; on the last tick there is no
                    // next tick and the return of that final instant would be lost. Keep such entries, clamped to uEnd.
                    GridRaster.TraverseFrom(grid, p.Cell, a, b, uEnd + LastTickSlack, visits[i]);
                    ClampEntries(visits[i], uEnd);
                }
                else
                {
                    GridRaster.TraverseFrom(grid, p.Cell, a, b, uEnd, visits[i]);
                }
                if (p.Spark != null) p.Spark.PrevS = p.Spark.S;
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Step 2: the event loop. Returns the tick parameter at which the state is frozen in step 3 (uEnd, or the group
        // parameter uG when the round ended inside the tick).

        public double RunEventLoop()
        {
            double uCur = 0.0;
            int groups = 0;
            double eps = cfg.EventEpsilonSeconds;
            while (true)
            {
                ComputeCandidates(uCur);
                if (candidates.Count == 0) return uEnd;
                if (groups >= cfg.MaxEventsPerTick)
                {
                    // Safety valve (section 6): stop, step 3 runs normally. Core tests assert this never happens.
                    sim.EventCapHits++;
                    return uEnd;
                }
                groups++;

                double uMin = double.PositiveInfinity;
                for (int c = 0; c < candidates.Count; c++)
                {
                    if (candidates[c].U < uMin) uMin = candidates[c].U;
                }
                group.Clear();
                double uG = uMin;
                for (int c = 0; c < candidates.Count; c++)
                {
                    Candidate cand = candidates[c];
                    if ((cand.U - uMin) * dt <= eps)
                    {
                        group.Add(cand);
                        if (cand.U > uG) uG = cand.U;
                    }
                }

                ApplyGroup(t0 + uMin * dt, uG);
                if (sim.Ended) return uG;
                uCur = uG;
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Step 3: trail ends, positions, current cells and spark S (closed form) at uStop.

        public void EndTick(double uStop)
        {
            for (int i = 0; i < n; i++)
            {
                PlayerState p = players[i];
                if (!p.Alive) continue;
                Vec2d pos = PosAt(i, uStop);
                if (!p.Home) p.Trail.Append(pos);
                p.Pos = pos;
                p.Cell = CellAt(i, uStop);
                if (p.Spark != null) p.Spark.S = SparkS(p.Spark, uStop);
            }
            // Rule v1.9 (contract 33): a spark or an elimination of this tick ends a ride.
            if (cfg.BorderRide == BorderRideRule.On)
            {
                for (int i = 0; i < n; i++) BorderRide.EndOfTick(players[i]);
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Candidate computation (section 6 step 2), always from the CURRENT state.

        private void ComputeCandidates(double uCur)
        {
            candidates.Clear();
            for (int i = 0; i < n; i++)
            {
                if (players[i].Alive) AddHomeTransition(i, uCur);
            }
            for (int v = 0; v < n; v++)
            {
                PlayerState victim = players[v];
                // KillShield (docs/BIOME_TRAITS.md section 7): a shielded trail cannot be cut (no Cut candidate at all).
                if (!victim.Alive || victim.Home || victim.Spark != null || victim.Shielded) continue;
                for (int a = 0; a < n; a++)
                {
                    if (a != v && players[a].Alive) AddCut(a, v, uCur);
                }
            }
            for (int i = 0; i < n; i++)
            {
                if (players[i].Alive && players[i].Shielded) AddShieldEnd(i, uCur);
            }
            for (int v = 0; v < n; v++)
            {
                if (players[v].Alive && players[v].Spark != null) AddSparkCatch(v, uCur);
            }
            for (int i = 0; i < n; i++)
            {
                if (players[i].Alive && !players[i].Home) AddLasso(i, uCur);
            }
            if (sim.Ring != null) AddPickup(uCur);
            if (lastTick)
            {
                candidates.Add(new Candidate { Kind = Kind.TimeUp, U = uEnd, Player = -1, Attacker = -1 });
            }
        }

        // R5 / R7 / R9: home transitions come from the visit list plus a state check at uCur (replaces FirstEntry).
        private void AddHomeTransition(int i, double uCur)
        {
            PlayerState p = players[i];
            List<CellEntry> v = visits[i];
            if (v.Count == 0) return;
            int c = IndexAt(v, uCur);
            bool ownHere = grid.Cells[v[c].Index] == p.Id;
            Kind kind = p.Home ? Kind.Exit : Kind.Return;
            if (p.Home != ownHere)
            {
                // A home player on a non-own cell exits at its head; a trailing player on an own cell returns there.
                candidates.Add(new Candidate { Kind = kind, U = uCur, Player = i, Attacker = -1, Point = PosAt(i, uCur) });
                return;
            }
            for (int k = c + 1; k < v.Count; k++)
            {
                bool own = grid.Cells[v[k].Index] == p.Id;
                if (own != ownHere)
                {
                    double u = v[k].U;
                    candidates.Add(new Candidate { Kind = kind, U = u, Player = i, Attacker = -1, Point = PosAt(i, u) });
                    return;
                }
            }
        }

        // R10 / R11: first contact of attacker a's head with the exposed part of v's trail.
        private void AddCut(int a, int v, double uCur)
        {
            Trail trail = players[v].Trail;
            if (trail.Count < 2) return;   // a single point has no segment: nothing exposed yet
            if (trail.FirstContact(p0[a], p1[a], cfg.ContactRadius, uCur, uTrailEnd[v], growth[v], cfg.HeadGrace,
                                   out double u, out double sCut)
                && u <= uEnd && u >= uCur)
            {
                candidates.Add(new Candidate
                {
                    Kind = Kind.Cut, U = u, Player = v, Attacker = a, S = sCut, TrailVersion = trail.Version,
                });
            }
        }

        // docs/BIOME_TRAITS.md 7.1: the shield end is an event candidate, so cut candidates are recomputed from that exact u
        // (a head already over the trail when the shield ends cuts at that instant, subject to HeadGrace). The end time is
        // recorded for the re-validation (a kill in the same group may extend the shield).
        private void AddShieldEnd(int i, double uCur)
        {
            double end = players[i].ShieldEnd;
            double u = Math.Max(uCur, (end - t0) / dt);
            if (u <= uEnd)
            {
                candidates.Add(new Candidate { Kind = Kind.ShieldEnd, U = u, Player = i, Attacker = -1, S = end });
            }
        }

        // R12 / R13: closed-form catch with the epsilon shift u_c = max(uCur, u0 + eps / dt).
        private void AddSparkCatch(int v, double uCur)
        {
            Spark spark = players[v].Spark;
            double speed = SpeedOf(spark);   // Spark.Speed (7.1), = SparkSpeed in classic rounds
            // f(u) = S(u) - L_v(u) = f0 + slope * u.
            double s0 = spark.SCut + speed * (t0 - spark.TimeCut);
            double l0 = players[v].Trail.Length - growth[v] * uTrailEnd[v];
            double f0 = s0 - l0;
            double slope = speed * dt - growth[v];
            double uc;
            if (slope > 0.0)
            {
                double u0 = -f0 / slope;
                uc = Math.Max(uCur, u0 + cfg.EventEpsilonSeconds / dt);
                // R13 + R19 (audit A6 fix): on the last tick the eps shift would push an impact with t_c <= RoundDuration
                // past the end, where no later tick can fire it, so the victim was ranked alive. It is an event of the
                // final instant: fire it at uEnd, grouped with TimeUp and with any return of that instant (which wins).
                if (lastTick && uc > uEnd && u0 <= uEnd + LastTickSlack) uc = uEnd;
            }
            else
            {
                // Only with a spark not faster than the pawn (misconfiguration): caught now if already reached.
                if (f0 + slope * uCur >= 0.0) uc = uCur;
                else return;
            }
            if (uc <= uEnd)
            {
                candidates.Add(new Candidate { Kind = Kind.SparkCatch, U = uc, Player = v, Attacker = spark.Attacker });
            }
        }

        // R16 / section 8: the first VALID proper crossing of the head path with an older segment of its own trail.
        private void AddLasso(int i, double uCur)
        {
            Trail trail = players[i].Trail;
            if (trail.Count < 2) return;
            double minArc = cfg.LassoMinArc;
            int count = trail.SelfCrossings(p0[i], p1[i], uCur, TrailLength(i, uEnd) - minArc, crossings);
            if (count == 0) return;
            IReadOnlyList<double> arc = trail.Arc;
            int version = trail.Version;
            for (int c = 0; c < count; c++)
            {
                SelfCrossing x = crossings[c];
                if (x.U > uEnd) break;          // sorted by U ascending
                if (x.U <= uCur) continue;      // SelfCrossings already uses u > uMin; kept as a guard
                if (!(arc[x.Segment + 1] <= TrailLength(i, x.U) - minArc)) continue;
                if (!LoopValid(i, version, x, out List<Vec2d> loop)) continue;
                candidates.Add(new Candidate
                {
                    Kind = Kind.Lasso, U = x.U, Player = i, Attacker = -1, Point = x.Point, Segment = x.Segment,
                    Loop = loop, TrailVersion = version,
                });
                return;
            }
        }

        private bool LoopValid(int i, int version, SelfCrossing x, out List<Vec2d> loop)
        {
            for (int k = 0; k < loopCache.Count; k++)
            {
                LoopCacheEntry e = loopCache[k];
                if (e.Player == i && e.Version == version && e.Segment == x.Segment && e.U == x.U)
                {
                    loop = e.Loop;
                    return e.Valid;
                }
            }
            loop = players[i].Trail.LoopPolygon(x.Segment, x.Point, x.Point);
            bool valid = LassoGeometry.IsValidPocket(grid, loop, cfg.LassoMinArea);
            loopCache.Add(new LoopCacheEntry { Player = i, Version = version, Segment = x.Segment, U = x.U, Valid = valid, Loop = loop });
            return valid;
        }

        // R15: pickup by contact intervals I_i = [in_i, out_i) of the eligible players (alive, not charged). The candidate
        // is the smallest u in {uCur} and the interval bounds >= uCur where exactly one eligible player is in contact.
        private void AddPickup(double uCur)
        {
            Vec2d ring = sim.Ring.Pos;
            double r = cfg.PickupRadius;
            pickupTimes.Clear();
            pickupTimes.Add(uCur);
            bool any = false;
            for (int i = 0; i < n; i++)
            {
                pickupIn[i] = double.PositiveInfinity;
                pickupOut[i] = double.NegativeInfinity;
                PlayerState p = players[i];
                if (!p.Alive || p.Charged) continue;
                if (!ContactInterval(p0[i], p1[i], ring, r, out double uin, out double uout)) continue;
                pickupIn[i] = uin;
                pickupOut[i] = uout;
                any = true;
                if (uin >= uCur && uin <= uEnd) pickupTimes.Add(uin);
                if (uout >= uCur && uout <= uEnd) pickupTimes.Add(uout);
            }
            if (!any) return;
            pickupTimes.Sort();
            // Brief 6.4 / Tuning.EventEpsilonSeconds (audit A6 fix): contact bounds closer than eps are the same instant.
            // Two heads entering at the same analytic instant get entry parameters that differ by rounding (1e-16); the
            // exact test gave the ring to whichever rounded first. Counting a player from in - tol to out - tol makes
            // such entries contested (and such exits leave nobody), while the candidate times stay the true bounds.
            double tol = cfg.EventEpsilonSeconds / dt;
            for (int k = 0; k < pickupTimes.Count; k++)
            {
                double u = pickupTimes[k];
                if (u > uEnd) break;
                int inContact = 0, who = -1;
                for (int i = 0; i < n; i++)
                {
                    if (pickupIn[i] - tol <= u && u < pickupOut[i] - tol)
                    {
                        inContact++;
                        who = i;
                    }
                }
                if (inContact == 1)
                {
                    candidates.Add(new Candidate { Kind = Kind.Pickup, U = u, Player = who, Attacker = -1 });
                    return;
                }
            }
        }

        /// <summary>
        /// Contact interval of the head path a + u (b - a), u in [0, inf), with the disc (c, r): [uin, uout) where
        /// uin = max(0, first root). A stationary head is in contact for all u (uout = +inf) or never.
        /// </summary>
        private static bool ContactInterval(Vec2d a, Vec2d b, Vec2d c, double r, out double uin, out double uout)
        {
            uin = double.PositiveInfinity;
            uout = double.NegativeInfinity;
            double dx = b.X - a.X, dy = b.Y - a.Y;
            double wx = a.X - c.X, wy = a.Y - c.Y;
            double qa = dx * dx + dy * dy;
            double qc = wx * wx + wy * wy - r * r;
            if (!(qa > 0.0))
            {
                if (qc > 0.0) return false;
                uin = 0.0;
                uout = double.PositiveInfinity;
                return true;
            }
            double qb = 2.0 * (dx * wx + dy * wy);
            double disc = qb * qb - 4.0 * qa * qc;
            if (disc < 0.0) return false;
            double sq = Math.Sqrt(disc);
            // Cancellation-free roots: q = -(b + sign(b) sqrt(disc)) / 2, roots q / a and c / q.
            double q = -0.5 * (qb + (qb >= 0.0 ? sq : -sq));
            double r1, r2;
            if (q == 0.0)
            {
                r1 = 0.0;
                r2 = 0.0;
            }
            else
            {
                r1 = q / qa;
                r2 = qc / q;
            }
            if (r1 > r2)
            {
                double tmp = r1;
                r1 = r2;
                r2 = tmp;
            }
            double lo = Math.Max(0.0, r1);
            if (!(r2 > lo)) return false;
            uin = lo;
            uout = r2;
            return true;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Group application (section 6 steps a-g) at group time t; current cells use c_i at uG.

        private void ApplyGroup(double t, double uG)
        {
            for (int i = 0; i < n; i++)
            {
                snapshot[i] = grid.CountOf(players[i].Id);
                aliveAtStart[i] = players[i].Alive;
            }
            sim.TraitTime = t;   // the clock of the trait hooks during this group
            try
            {
                ApplyGroupSteps(t, uG);
            }
            finally
            {
                sim.TraitTime = double.NaN;
            }
        }

        private void ApplyGroupSteps(double t, double uG)
        {
            eliminatedInGroup.Clear();
            killsInGroup.Clear();
            bool timeUp = false;
            for (int c = 0; c < group.Count; c++)
            {
                if (group[c].Kind == Kind.TimeUp) timeUp = true;
            }
            group.Sort(CompareMembers);

            StepReturns(t, uG);      // a
            StepSparkCatches(t);     // b
            StepKillRewards(t, uG);  // b, end: kill traits (docs/BIOME_TRAITS.md section 7), v1.6 bridge (contract 30)
            StepShieldEnds(t);       // b, end: shield ends (7.1), after a kill of this group may have extended the shield
            StepCuts(t);             // c
            StepLassos(t);           // d
            StepPickups(t);          // e
            StepExits(t);            // f

            int alive = 0;
            for (int i = 0; i < n; i++)
            {
                if (players[i].Alive) alive++;
            }
            // docs/BIOME_TRAITS.md 7.2: a kill reward (KillInheritance) can put a trailing killer's head on its own cell; the
            // next candidate pass returns it at this very instant (section 6 state check). When the round ends in this group
            // there is no next pass, so those same-instant returns are applied here, before the round end check, with the
            // step a rules (the outcome the next pass would give). Never runs without kill rewards in this group.
            if (rewardedInGroup && alive > 0 && ((n >= 2 && alive == 1) || timeUp))
            {
                ReturnsBeforeRoundEnd(t, uG);
                alive = 0;
                for (int i = 0; i < n; i++)
                {
                    if (players[i].Alive) alive++;
                }
            }
            rewardedInGroup = false;

            // R19: an eliminated player's rank is final now: 1 + players alive after its event group.
            for (int k = 0; k < eliminatedInGroup.Count; k++) sim.EliminatedRank[eliminatedInGroup[k]] = 1 + alive;

            // g. Round end check, TimeUp last. Rule v1.7 (contract 31): the conquest goal ends the round after the
            // last-survivor and all-eliminated checks and before TimeUp.
            if (n >= 2 && alive == 1) sim.EndRound(RoundEndReason.LastSurvivor, t);
            else if (alive == 0) sim.EndRound(RoundEndReason.AllEliminated, t);
            else if (sim.ConquestReached()) sim.EndRound(RoundEndReason.Conquest, t);
            else if (timeUp) sim.EndRound(RoundEndReason.TimeUp, t);
        }

        // Deterministic order inside a group: by kind, then player index, then attacker index.
        private static int CompareMembers(Candidate x, Candidate y)
        {
            int c = ((int)x.Kind).CompareTo((int)y.Kind);
            if (c != 0) return c;
            c = x.Player.CompareTo(y.Player);
            if (c != 0) return c;
            return x.Attacker.CompareTo(y.Attacker);
        }

        // a. Returns (R7, R18), then severed territory (rule v1.5, contract 29), then the single domain of the returners
        // (rule v1.6, contract 30, KillInheritance rounds only), then stolen home cells (R9), then players left with no cell
        // (R9). A chased returner
        // (R13 v1.4, contract 24) is saved with an empty capture: its trail, spark and pocket are cleared, nothing is won.
        // A spark spawned less than eps before the return is a cut at closure (R14) and is cancelled first (unchased).
        private void StepReturns(double t, double uG)
        {
            int returners = 0;
            for (int c = 0; c < group.Count; c++)
            {
                if (group[c].Kind == Kind.Return) returners++;
            }
            if (returners == 0) return;

            var who = new List<int>(returners);
            var points = new List<Vec2d>(returners);
            var us = new List<double>(returners);
            var captured = new List<int[]>(returners);
            var linked = new List<bool>(returners);   // rule v1.8: the capture took the band of the trail (DomainLinks)
            for (int c = 0; c < group.Count; c++)
            {
                Candidate cand = group[c];
                if (cand.Kind != Kind.Return) continue;
                PlayerState p = players[cand.Player];
                if (!p.Alive || p.Home) continue;
                if (CaughtBeforeReturn(cand.Player, cand.U)) continue;   // R13: step b eliminates it
                CancelCutAtClosure(p, cand.U);                          // R14 across a tick boundary
                who.Add(cand.Player);
                points.Add(cand.Point);
                us.Add(cand.U);
                bool link = false;
                // R13 / contract 24 (v1.4): a chased return survives but captures nothing. CaptureSolver is not called,
                // the pending pocket is not validated (it is cleared below) and the empty set claims no cell in the R18
                // conflict rule. Unchased returns: against the grid as it is now (R18). docs/BIOME_TRAITS.md 7.1: "chased"
                // is ExitWasCut (a cut exit never captures, even if KillShield removed the spark since); in classic
                // rounds ExitWasCut is exactly "has a spark".
                if (p.ExitWasCut) captured.Add(Array.Empty<int>());
                else
                {
                    int[] cells = ComputeCapture(cand.Player, cand.Point);
                    // Rule v1.8 (contract 32): a closure whose capture would leave the domain in pieces (a lasso pocket or
                    // a region that touches only the trail, a part joined only at a corner, a trail that leaves one piece
                    // and enters another) also takes the band of its trail, which joins them. Rule v1.6 (contract 30,
                    // SingleDomain Off): the trail footprint when the capture is not attached. Before the traits, so
                    // Coalescence also fills the holes the band closes.
                    if (linkBands) cells = LinkCapture(cand.Player, cand.Point, cand.U, cells, out link);
                    else if (singleDomain && cells.Length > 0 && !TerritorySplit.GainAttached(grid, p.Id, cells))
                        cells = WithTrailFootprint(cand.Player, cand.Point, cells);
                    // Traits (BIOME_TRAITS section 6, step a): unchased returns only, before the R18 conflict rule.
                    if (sim.Behaviours.Length > 0) cells = sim.AugmentCapture(p, cells);
                    captured.Add(cells);
                }
                linked.Add(link);
            }
            int m = who.Count;
            if (m == 0) return;

            // R18: a cell claimed by two or more simultaneous returns keeps its previous owner (or stays neutral).
            var applied = new int[m][];
            var victims = new ulong[m];   // bit (owner - 1) set when this return took cells of that player (Other, 5.5)
            var keep = new List<int>();
            for (int r = 0; r < m; r++)
            {
                keep.Clear();
                int[] mine = captured[r];
                for (int k = 0; k < mine.Length; k++)
                {
                    int cell = mine[k];
                    bool contested = false;
                    for (int o = 0; o < m && !contested; o++)
                    {
                        if (o != r && Array.BinarySearch(captured[o], cell) >= 0) contested = true;
                    }
                    if (!contested) keep.Add(cell);
                }
                applied[r] = keep.ToArray();
            }
            // Rule v1.5 (contract 29): the victims of these captures and their anchors, on the grid before it is written.
            bool severing = cfg.SeveredTerritory != SeveredTerritoryRule.Off && CollectSevered(who, applied, m, uG);
            for (int r = 0; r < m; r++)
            {
                byte id = players[who[r]].Id;
                int[] cells = applied[r];
                for (int k = 0; k < cells.Length; k++)
                {
                    byte prev = grid.Cells[cells[k]];
                    if (prev != OwnerGrid.Neutral && prev != OwnerGrid.Void && prev <= 64) victims[r] |= 1UL << (prev - 1);
                    grid.Set(cells[k], id);
                }
            }

            for (int r = 0; r < m; r++)
            {
                PlayerState p = players[who[r]];
                bool chased = p.ExitWasCut;
                double margin = 0.0;
                if (chased && p.Spark != null)
                {
                    double l = TrailLength(who[r], us[r]);
                    double s = SparkS(p.Spark, us[r]);
                    margin = Math.Max(0.0, (l - s) / SpeedOf(p.Spark));
                }
                p.Trail.Clear();
                p.Spark = null;
                p.ExitWasCut = false;
                p.Pocket.Clear();   // validated into applied[r] when unchased; erased unvalidated when chased (contract 24)
                p.Home = true;
                // Contract 23.2 D2: Captures counts only the returns that applied cells (after the R18 conflict rule);
                // the Return event is still emitted for every return (a chased one with an empty Cells array).
                if (applied[r].Length > 0) p.Captures++;
                if (linked[r] && applied[r].Length > 0) p.DomainLinks++;
                sim.Emit(new SimEvent
                {
                    Type = SimEventType.Return, Time = t, Player = who[r], Point = points[r], Cells = applied[r],
                    Chased = chased, Margin = margin,
                });
            }

            // Rule v1.5 (contract 29): split territories keep one piece; the others are severed (TerritorySevered). The kept
            // piece holds the victim's pawn when it stands on its land, so no home player's current cell is severed.
            if (severing) ApplySevered(applied, t);

            // Rule v1.6 (contract 30): every returner keeps one domain (a contested cell or a simultaneous capture can
            // still leave a gained part apart).
            if (singleDomain) KeepReturnersWhole(who, applied, m, severing, t, uG);

            // R9 / R18b: every alive home player (returners included) whose current cell at uG was just taken by one of
            // these returns starts an exit at its head. (A home player whose cell at uG is not its own for any other
            // reason has its own exit candidate in this group: step f handles it at its exact crossing point.)
            for (int i = 0; i < n; i++)
            {
                PlayerState p = players[i];
                if (!p.Alive || !p.Home) continue;
                int cell = CellAt(i, uG);
                if (grid.Cells[cell] == p.Id) continue;
                int taker = -1;
                for (int r = 0; r < m && taker < 0; r++)
                {
                    if (Array.BinarySearch(applied[r], cell) >= 0) taker = who[r];
                }
                if (taker < 0) continue;
                Vec2d head = PosAt(i, uG);
                p.Home = false;
                p.ExitWasCut = false;
                p.Trail.Start(head);
                uTrailEnd[i] = uG;
                sim.Emit(new SimEvent { Type = SimEventType.TerritoryStolen, Time = t, Player = i, Other = taker, Point = head });
                sim.Emit(new SimEvent { Type = SimEventType.Exit, Time = t, Player = i, Point = head });
            }

            // R9: losing the last cell eliminates. Other = the lowest-index returner that took cells of that player.
            for (int i = 0; i < n; i++)
            {
                PlayerState p = players[i];
                if (!p.Alive || grid.CountOf(p.Id) != 0) continue;
                int other = -1;
                for (int r = 0; r < m; r++)
                {
                    int bit = p.Id - 1;
                    if (bit < 64 && (victims[r] & (1UL << bit)) != 0 && (other < 0 || who[r] < other)) other = who[r];
                }
                Eliminate(i, EliminationCause.TerritoryLost, other, t, uG);
            }
        }

        /// <summary>
        /// Rule v1.5 (contract 29), before the captures of step a are written: every living player that loses cells to
        /// another player's capture is a victim; its lost cells (ascending) and its anchor cell are recorded on the grid as
        /// it is before the captures. False when nobody loses a cell to another player (the common case: nothing else runs).
        /// </summary>
        private bool CollectSevered(List<int> who, int[][] applied, int m, double uG)
        {
            bool any = false;
            for (int i = 0; i < n; i++)
            {
                severVictim[i] = false;
                severLost[i].Clear();
                severOwnReturn[i] = -1;
            }
            for (int r = 0; r < m; r++)
            {
                severOwnReturn[who[r]] = r;
                byte id = players[who[r]].Id;
                int[] cells = applied[r];
                for (int k = 0; k < cells.Length; k++)
                {
                    byte prev = grid.Cells[cells[k]];
                    if (prev == OwnerGrid.Neutral || prev == OwnerGrid.Void || prev == id || prev > n) continue;
                    int v = prev - 1;
                    if (!players[v].Alive) continue;   // never true (a dead player owns no cell), kept as a guard
                    severLost[v].Add(cells[k]);
                    severVictim[v] = true;
                    any = true;
                }
            }
            if (!any) return false;
            for (int v = 0; v < n; v++)
            {
                if (!severVictim[v]) continue;
                severLost[v].Sort();
                severAnchor[v] = AnchorCell(v, uG);
            }
            return true;
        }

        /// <summary>
        /// Rule v1.5 anchor, on the grid before the captures: the pawn's current cell at uG when the player owns it (a home
        /// player, or a returner on its return cell); a home player crossing out at this very instant: the last own cell of
        /// its visit list (the cell it is leaving); a trailing player: the cell it left home from
        /// (TerritorySplit.ExitCell of Trail.Points[0]). -1 when there is none.
        /// </summary>
        private int AnchorCell(int i, double uG)
        {
            PlayerState p = players[i];
            int c = CellAt(i, uG);
            if (grid.Cells[c] == p.Id) return c;
            if (p.Home)
            {
                List<CellEntry> v = visits[i];
                if (v.Count > 0)
                {
                    for (int k = IndexAt(v, uG) - 1; k >= 0; k--)
                    {
                        if (grid.Cells[v[k].Index] == p.Id) return v[k].Index;
                    }
                }
                return grid.Cells[p.Cell] == p.Id ? p.Cell : -1;
            }
            return p.Trail.Count > 0 ? TerritorySplit.ExitCell(grid, p.Id, p.Trail.Points[0]) : -1;
        }

        /// <summary>
        /// Rule v1.5, after the captures of step a and their Return events: every victim recorded by CollectSevered keeps
        /// one piece of each territory the captures split (TerritorySplit.Find) and loses the others, which become neutral
        /// (SeveredTerritoryRule.Neutral, scorch forgotten) or the cutter's (Capturer). Every victim is analysed first on the
        /// grid left by the captures, then the changes are written, so with Capturer a cutter that is itself a victim of the
        /// same group is judged on its own land only. One TerritorySevered event per victim and cutter (victims ascending,
        /// then cutters ascending), cells ascending. A victim always keeps a piece, so nobody is eliminated here.
        /// </summary>
        private void ApplySevered(int[][] applied, double t)
        {
            bool anything = false;
            for (int v = 0; v < n; v++)
            {
                severCells[v].Clear();
                severCutter[v].Clear();
                if (!severVictim[v] || !players[v].Alive) continue;
                int r = severOwnReturn[v];
                int[] gained = r >= 0 ? applied[r] : null;
                if (TerritorySplit.Find(grid, players[v].Id, severLost[v], gained, severAnchor[v], severCells[v], severCutter[v]) > 0)
                    anything = true;
            }
            if (!anything) return;

            bool toCutter = cfg.SeveredTerritory == SeveredTerritoryRule.Capturer;
            for (int v = 0; v < n; v++)
            {
                List<int> cells = severCells[v], cutters = severCutter[v];
                int done = 0, previous = int.MinValue;
                while (done < cells.Count)
                {
                    int cutter = int.MaxValue;
                    for (int k = 0; k < cutters.Count; k++)
                    {
                        if (cutters[k] > previous && cutters[k] < cutter) cutter = cutters[k];
                    }
                    previous = cutter;
                    severScratch.Clear();
                    for (int k = 0; k < cells.Count; k++)
                    {
                        if (cutters[k] == cutter) severScratch.Add(cells[k]);
                    }
                    done += severScratch.Count;
                    severScratch.Sort();
                    int recipient = toCutter && cutter >= 0 && cutter < n && players[cutter].Alive ? cutter : -1;
                    byte owner = recipient >= 0 ? players[recipient].Id : OwnerGrid.Neutral;
                    ScorchedEarthTrait scorch = recipient < 0 ? sim.Scorch : null;
                    for (int k = 0; k < severScratch.Count; k++)
                    {
                        grid.Set(severScratch[k], owner);
                        scorch?.Forget(severScratch[k]);
                    }
                    sim.Emit(new SimEvent
                    {
                        Type = SimEventType.TerritorySevered, Time = t, Player = v, Other = cutter, Recipient = recipient,
                        Cells = severScratch.ToArray(),
                    });
                }
            }
        }

        /// <summary>
        /// R13 (audit A6 fix): the catch candidate already sits at t_c + eps, so a return of the same player whose own u
        /// is strictly after it (t_r &gt; t_c + eps) lost the race. Grouping by eps can still put both in one group (a
        /// return up to 2 eps after t_c), where step a would have saved the player, and only when both fell in the same
        /// tick, which made the outcome depend on the tick rate. Exact ties (t_r = t_c) keep u_r &lt; u_c and are saved.
        /// </summary>
        private bool CaughtBeforeReturn(int player, double uReturn)
        {
            for (int c = 0; c < group.Count; c++)
            {
                Candidate other = group[c];
                if (other.Kind == Kind.SparkCatch && other.Player == player && other.U < uReturn) return true;
            }
            return false;
        }

        /// <summary>
        /// R14 + contract 24 (v1.4 rule verifier fix): a cut at the instant the trail closes has no effect, and events
        /// closer than EventEpsilonSeconds are simultaneous. Inside one tick the grouping already drops such a cut (returns
        /// resolve first). Across a tick boundary it cannot: the cut lands at the end of tick k (u = 1 - tiny) while the
        /// return lands at the start of tick k + 1, so the cut was applied and, since v1.4, the return captured nothing. A
        /// cut at exactly t = 0.5 with the return at exactly t = 0.5 hit this through rounding at 144 and 240 Hz (not at 30,
        /// 48 or 60 Hz). So a spark spawned less than EventEpsilonSeconds before this return instant is a cut at closure:
        /// it is removed and its CutsMade credit taken back, and the return resolves as unchased (it captures). The Cut
        /// event raised in the previous tick cannot be withdrawn. docs/BIOME_TRAITS.md 7.1: ExitWasCut goes back to its
        /// value before this spark (cleared in classic rounds, so the return captures). kill-verify fix: a re-cut of an exit
        /// whose first spark KillShield extinguished keeps the exit cut, so its loop stays lost (7.2).
        /// </summary>
        private void CancelCutAtClosure(PlayerState p, double uReturn)
        {
            Spark spark = p.Spark;
            if (spark == null) return;
            if (!(t0 + uReturn * dt - spark.TimeCut < cfg.EventEpsilonSeconds)) return;
            if (spark.Attacker >= 0 && spark.Attacker < n && players[spark.Attacker].CutsMade > 0) players[spark.Attacker].CutsMade--;
            p.Spark = null;
            p.ExitWasCut = spark.ExitWasCutBefore;
        }

        // Section 7 capture of one returner: outline = loop-erased trail ending at the crossing point, plus the pocket.
        private int[] ComputeCapture(int i, Vec2d crossing)
        {
            PlayerState p = players[i];
            outlineInput.Clear();
            IReadOnlyList<Vec2d> pts = p.Trail.Points;
            int count = p.Trail.Count;
            for (int k = 0; k < count; k++) outlineInput.Add(pts[k]);
            if (outlineInput.Count == 0 || Vec2d.Distance(outlineInput[outlineInput.Count - 1], crossing) >= 1e-9)
                outlineInput.Add(crossing);
            List<Vec2d> outline = LoopErase.Erase(outlineInput);
            int[] cells = CaptureSolver.Compute(grid, p.Id, outline, p.Pocket.Count > 0 ? p.Pocket : null);
            return cells ?? Array.Empty<int>();
        }

        // ------------------------------------------------------------------------------------------------------------
        // Rule v1.6: single domain and kill inheritance bridge (contract 30). Runs only when singleDomain is true.

        /// <summary>
        /// Rule v1.6, step a: the capture plus the trail footprint (the supercover raster of the whole trail up to the
        /// crossing point, the footprint a closure gives a trail), minus own and Void cells, ascending. Used when the
        /// capture alone would leave a part apart from the domain (TerritorySplit.GainAttached false): the trail joins the
        /// exit, the entry and every captured part (a lasso pocket lies on the trail), as a trail that leaves one piece of the
        /// domain and enters another closes the loop.
        /// </summary>
        private int[] WithTrailFootprint(int i, Vec2d crossing, int[] cells)
        {
            PlayerState p = players[i];
            outlineInput.Clear();
            IReadOnlyList<Vec2d> pts = p.Trail.Points;
            for (int k = 0; k < p.Trail.Count; k++) outlineInput.Add(pts[k]);
            if (outlineInput.Count == 0 || Vec2d.Distance(outlineInput[outlineInput.Count - 1], crossing) >= 1e-9) outlineInput.Add(crossing);
            CellMask mask = BandMask();
            mask.Clear();
            GridRaster.RasterPolyline(grid, outlineInput, mask);
            for (int k = 0; k < cells.Length; k++) mask.Set(cells[k]);
            mask.CopyIndices(footprint);
            byte[] owners = grid.Cells;
            int w = 0;
            for (int k = 0; k < footprint.Count; k++)
            {
                byte o = owners[footprint[k]];
                if (o != p.Id && o != OwnerGrid.Void) footprint[w++] = footprint[k];
            }
            footprint.RemoveRange(w, footprint.Count - w);
            return footprint.ToArray();
        }

        /// <summary>
        /// Rule v1.8 (contract 32), step a, every round type: the capture of an unchased return, plus the band of its trail
        /// when the capture alone would leave the returner's domain in pieces. Pieces are read with the capture counted as
        /// the returner's (the grid is not written yet) and the piece of the return cell kept. When the domain plus the
        /// capture is one 4-connected piece nothing changes (the common case: one flood, O(territory)). Otherwise the band
        /// of the whole trail up to the crossing point (cells within InheritanceBandHalfWidth of it plus its supercover
        /// raster, the v1.6 band, InheritanceBridge.BandCells) is added when it leaves fewer cells apart (8-connected
        /// pieces first, then 4-connected ones, so a part joined only at a corner is linked too): it joins a detached
        /// lasso pocket or region, a corner-joined region, and two separate pieces the trail goes between. The band is part
        /// of the capture: R18 and rule v1.5 apply to it, cells of a living rival under it are taken (the trail is the only
        /// line the player drew). Own and Void cells are left out; the result is ascending.
        /// </summary>
        private int[] LinkCapture(int i, Vec2d crossing, double u, int[] cells, out bool link)
        {
            link = false;
            PlayerState p = players[i];
            byte id = p.Id;
            int anchor = CellAt(i, u);
            if (grid.Cells[anchor] != id) anchor = -1;
            linkExtra.Clear();
            linkExtra.AddRange(cells);
            domainSevered.Clear();
            if (TerritorySplit.KeepOnePiece(grid, id, linkExtra, anchor, domainSevered, 4) <= 1) return cells;
            int apart4 = domainSevered.Count;
            domainSevered.Clear();
            TerritorySplit.KeepOnePiece(grid, id, linkExtra, anchor, domainSevered);
            int apart8 = domainSevered.Count;

            outlineInput.Clear();
            IReadOnlyList<Vec2d> pts = p.Trail.Points;
            for (int k = 0; k < p.Trail.Count; k++) outlineInput.Add(pts[k]);
            if (outlineInput.Count == 0 || Vec2d.Distance(outlineInput[outlineInput.Count - 1], crossing) >= 1e-9) outlineInput.Add(crossing);
            CellMask mask = BandMask();
            InheritanceBridge.BandCells(grid, outlineInput, cfg.InheritanceBandHalfWidth, mask, bandCells);   // leaves the band in mask
            for (int k = 0; k < cells.Length; k++) mask.Set(cells[k]);
            mask.CopyIndices(footprint);
            byte[] owners = grid.Cells;
            int w = 0;
            for (int k = 0; k < footprint.Count; k++)
            {
                int c = footprint[k];
                byte o = owners[c];
                if (o != id && o != OwnerGrid.Void && RimSafe(c)) footprint[w++] = c;
            }
            footprint.RemoveRange(w, footprint.Count - w);

            domainSevered.Clear();
            TerritorySplit.KeepOnePiece(grid, id, footprint, anchor, domainSevered);
            int band8 = domainSevered.Count;
            bool better = band8 < apart8;
            if (!better && band8 == apart8)
            {
                domainSevered.Clear();
                TerritorySplit.KeepOnePiece(grid, id, footprint, anchor, domainSevered, 4);
                better = domainSevered.Count < apart4;
            }
            if (!better) return cells;
            link = true;
            return footprint.ToArray();
        }

        private CellMask BandMask()
        {
            if (bandMask == null) bandMask = new CellMask(grid.Size);
            return bandMask;
        }

        /// <summary>
        /// Rule v1.6, end of step a: every returner that gained cells keeps one 8-connected domain. The cheap check
        /// (TerritorySplit.GainAttached: every gained cell joins the cells it had) is exact while its territory was one
        /// domain and lost nothing; with simultaneous returns, a severance of its own land or the Capturer option the full
        /// labelling decides. A part apart from the piece of its return cell (else the largest piece) is severed (neutral).
        /// </summary>
        private void KeepReturnersWhole(List<int> who, int[][] applied, int m, bool severing, double t, double uG)
        {
            for (int r = 0; r < m; r++)
            {
                int i = who[r];
                PlayerState p = players[i];
                if (!p.Alive || applied[r].Length == 0) continue;
                bool full = m >= 2 || (severing && (severVictim[i] || cfg.SeveredTerritory == SeveredTerritoryRule.Capturer));
                if (!full && TerritorySplit.GainAttached(grid, p.Id, applied[r])) continue;
                int cell = CellAt(i, uG);
                int anchor = grid.Cells[cell] == p.Id ? cell : -1;
                domainSevered.Clear();
                if (TerritorySplit.KeepOnePiece(grid, p.Id, null, anchor, domainSevered) > 1) SeverPieces(i, domainSevered, t);
            }
        }

        /// <summary>
        /// Rule v1.6: the cells (ascending) become plain neutral (a running ScorchedEarth scorch is forgotten) and one
        /// TerritorySevered event is raised (Player = the owner, Other = -1: no cutter, the single-domain rule severed them,
        /// Recipient = -1).
        /// </summary>
        private void SeverPieces(int player, List<int> cells, double t)
        {
            if (cells.Count == 0) return;
            ScorchedEarthTrait scorch = sim.Scorch;
            for (int k = 0; k < cells.Count; k++)
            {
                grid.Set(cells[k], OwnerGrid.Neutral);
                scorch?.Forget(cells[k]);
            }
            sim.Emit(new SimEvent
            {
                Type = SimEventType.TerritorySevered, Time = t, Player = player, Other = -1, Recipient = -1, Cells = cells.ToArray(),
            });
        }

        /// <summary>
        /// Rule v1.6, right after the kill traits of one kill gave the victim's land to the killer (KillInheritanceTrait
        /// .LastInherited not empty). If the killer's territory is now several pieces: with InheritanceBridge = Bridge, the
        /// band of the kill line is built (BuildBand) and applied when it joins the anchor's piece to inherited land
        /// (ApplyBand: InheritanceBridged, the v1.5 split rule for third players, R9, the killer's trail cut at the cut
        /// point); then the killer keeps the piece of its anchor (read on the grid before the inheritance: the v1.5 anchor,
        /// else the largest piece) and every other piece is severed. Rule v1.8 (contract 32): with SingleDomain On this also
        /// runs when InheritanceBridge is Off, which then behaves as AnchorOnly (no band, the island is severed).
        /// </summary>
        private void JoinInheritance(KillInfo kill, int anchor, double t, double uG)
        {
            int killer = kill.Killer;
            byte id = players[killer].Id;
            domainSevered.Clear();
            if (TerritorySplit.KeepOnePiece(grid, id, null, anchor, domainSevered) <= 1) return;   // one domain already
            if (cfg.InheritanceBridge == InheritanceBridgeRule.Bridge && BuildBand(kill, out double split))
            {
                bandExtra.Clear();
                for (int k = 0; k < bandCells.Count; k++)
                {
                    if (grid.Cells[bandCells[k]] != id) bandExtra.Add(bandCells[k]);
                }
                if (bandExtra.Count > 0)
                {
                    domainSeveredWithBand.Clear();
                    TerritorySplit.KeepOnePiece(grid, id, bandExtra, anchor, domainSeveredWithBand);
                    if (BandJoins())
                    {
                        ApplyBand(kill, split, t, uG);
                        domainSevered.Clear();
                        if (players[killer].Alive) TerritorySplit.KeepOnePiece(grid, id, null, anchor, domainSevered);
                    }
                }
            }
            if (players[killer].Alive) SeverPieces(killer, domainSevered, t);
        }

        /// <summary>
        /// The band is applied only when it joins pieces to the kept one (the anchor's piece, else the largest): no band cell
        /// would be cut off (the band touches the kept piece) and fewer cells would be severed than without it. Before the
        /// inheritance the killer had one domain, so the pieces it joins are inherited land.
        /// </summary>
        private bool BandJoins()
        {
            for (int k = 0; k < domainSeveredWithBand.Count; k++)
            {
                if (bandExtra.BinarySearch(domainSeveredWithBand[k]) >= 0) return false;
            }
            return domainSeveredWithBand.Count < domainSevered.Count;
        }

        /// <summary>
        /// Builds the kill line and its band cells (bandCells). False when no bridge can be made: a forced cut (no contact
        /// geometry); the killer still out on the exit that made the cut but that exit was cut since (v1.4: a cut exit never
        /// becomes territory, ExitWasCut covers a running chase too); the killer home at the cut or back home since, and its
        /// head point at the cut (Q) is no longer its cell (the line it made was taken since). split = the arc of Q on the
        /// killer's current trail when the trail prefix [exit, Q] is part of the line (the trail is cut there), else 0.
        /// </summary>
        private bool BuildBand(KillInfo kill, out double split)
        {
            split = 0.0;
            Spark spark = kill.Spark;
            List<Vec2d> victimPrefix = kill.VictimPrefix;
            if (spark == null || !spark.Linked || victimPrefix == null || victimPrefix.Count == 0) return false;
            PlayerState k = players[kill.Killer];
            byte id = k.Id;
            bandLine.Clear();
            if (spark.AttackerEpoch >= 0 && !k.Home && k.Trail.Count > 0 && k.Trail.Epoch == spark.AttackerEpoch)
            {
                if (k.ExitWasCut) return false;
                double s = spark.AttackerArc - (k.Trail.Dropped - spark.AttackerDropped);
                if (s > Trail.MinPointSpacing)
                {
                    InheritanceBridge.AppendPrefix(k.Trail, s, bandLine);
                    split = Math.Min(s, k.Trail.Length);
                }
                else
                {
                    // The cut point lies on a part of this exit that already became territory (an earlier bridge).
                    if (!OwnsPoint(id, spark.AttackerHead)) return false;
                    bandLine.Add(spark.AttackerHead);
                }
            }
            else
            {
                if (!OwnsPoint(id, spark.AttackerHead)) return false;
                bandLine.Add(spark.AttackerHead);
            }
            // The link Q -> P (P = the last point of the victim's prefix), then the victim's trail back to its exit.
            for (int j = victimPrefix.Count - 1; j >= 0; j--) InheritanceBridge.AddPoint(bandLine, victimPrefix[j]);
            InheritanceBridge.BandCells(grid, bandLine, cfg.InheritanceBandHalfWidth, BandMask(), bandCells);
            if (linkBands)
            {
                // Rule v1.8 (contract 32): the band never reaches the outer rim band of R1 (kept neutral forever).
                int w = 0;
                for (int c = 0; c < bandCells.Count; c++)
                {
                    if (RimSafe(bandCells[c])) bandCells[w++] = bandCells[c];
                }
                bandCells.RemoveRange(w, bandCells.Count - w);
            }
            return bandCells.Count > 0;
        }

        /// <summary>
        /// Rule v1.8 (contract 32), R1: a band cell must be a cell a trail raster can reach. A head center stays at least
        /// ArenaMargin inside the rim, so every cell of a trail's supercover raster has its center at most ArenaMargin minus
        /// half a cell diagonal inside it; band cells closer to the rim are left out, so the outer rim band stays neutral
        /// forever (R1) whatever the band half width.
        /// </summary>
        private bool RimSafe(int cell)
        {
            int size = grid.Size;
            Vec2d center = grid.CellCenter(cell % size, cell / size);
            return sim.Arena.SignedDistance(center) <= -(cfg.ArenaMargin - 0.5 * Math.Sqrt(2.0) * grid.CellSize) + 1e-9;
        }

        /// <summary>True when one of the cells whose closed square contains p is the player's.</summary>
        private bool OwnsPoint(byte id, Vec2d p)
        {
            int c = TerritorySplit.ExitCell(grid, id, p);
            return c >= 0 && grid.Cells[c] == id;
        }

        /// <summary>
        /// Writes the band cells that were not the killer's (bandExtra) as a capture of the killer: third players that lose
        /// cells are judged by the v1.5 split rule (anchors read before the write), then a home player whose cell was taken
        /// exits (R9, TerritoryStolen + Exit, Other = the killer) and a player left with no cell is eliminated
        /// (TerritoryLost). The killer's trail prefix [exit, Q] is territory now: the trail is cut at split (the rest stays
        /// its active trail, whose exit point is Q). Emits InheritanceBridged right after the write.
        /// </summary>
        private void ApplyBand(KillInfo kill, double split, double t, double uG)
        {
            int killer = kill.Killer;
            PlayerState k = players[killer];
            byte id = k.Id;
            int[] band = bandExtra.ToArray();
            var applied = new[] { band };
            bandWho.Clear();
            bandWho.Add(killer);
            bool severing = cfg.SeveredTerritory != SeveredTerritoryRule.Off && CollectSevered(bandWho, applied, 1, uG);
            for (int c = 0; c < band.Length; c++) grid.Set(band[c], id);
            if (split > 0.0) k.Trail.DropPrefix(split);
            k.InheritanceBridges++;
            sim.Emit(new SimEvent
            {
                Type = SimEventType.InheritanceBridged, Time = t, Player = killer, Other = kill.Victim, Point = kill.Point, Cells = band,
            });
            if (severing) ApplySevered(applied, t);
            for (int i = 0; i < n; i++)
            {
                PlayerState p = players[i];
                if (i == killer || !p.Alive || !p.Home) continue;
                int cell = CellAt(i, uG);
                if (grid.Cells[cell] == p.Id || Array.BinarySearch(band, cell) < 0) continue;
                Vec2d head = PosAt(i, uG);
                p.Home = false;
                p.ExitWasCut = false;
                p.Trail.Start(head);
                uTrailEnd[i] = uG;
                sim.Emit(new SimEvent { Type = SimEventType.TerritoryStolen, Time = t, Player = i, Other = killer, Point = head });
                sim.Emit(new SimEvent { Type = SimEventType.Exit, Time = t, Player = i, Point = head });
            }
            for (int i = 0; i < n; i++)
            {
                PlayerState p = players[i];
                if (i == killer || !p.Alive || grid.CountOf(p.Id) != 0) continue;
                Eliminate(i, EliminationCause.TerritoryLost, killer, t, uG);
            }
        }

        // b. Spark catches: only a player still alive that still has its spark (a returner of step a has none).
        private void StepSparkCatches(double t)
        {
            for (int c = 0; c < group.Count; c++)
            {
                Candidate cand = group[c];
                if (cand.Kind != Kind.SparkCatch) continue;
                PlayerState v = players[cand.Player];
                if (!v.Alive || v.Spark == null) continue;
                Eliminate(cand.Player, EliminationCause.Spark, v.Spark.Attacker, t, cand.U);
            }
        }

        /// <summary>
        /// docs/BIOME_TRAITS.md section 7, at the end of step b (the last step of a group that can eliminate anyone, so a
        /// killer alive now is alive after the group): the kill traits run for every Spark elimination of this group whose
        /// killer is alive, in elimination order. A kill whose killer is dead or was eliminated in this group gets nothing
        /// (the victim's cells stay neutral, as without the traits). Nothing runs without kill traits (classic rounds).
        /// Rule v1.6 (contract 30, single-domain rounds only): after the kill traits of each kill, the inherited land is
        /// joined to the killer's domain by the bridge band, or severed (JoinInheritance). The killer's anchor is read on the
        /// grid before that kill's inheritance. A killer whose last cell an earlier bridge band of this group took is
        /// eliminated (TerritoryLost) and gets nothing more.
        /// </summary>
        private void StepKillRewards(double t, double uG)
        {
            if (killsInGroup.Count == 0) return;
            rewarded.Clear();
            for (int k = 0; k < killsInGroup.Count; k++)
            {
                KillInfo kill = killsInGroup[k];
                if (players[kill.Killer].Alive) rewarded.Add(kill);
            }
            if (rewarded.Count > 0)
            {
                if (!inheritanceJoin) sim.NotifyKills(rewarded);
                else
                {
                    for (int k = 0; k < rewarded.Count; k++)
                    {
                        KillInfo kill = rewarded[k];
                        if (!players[kill.Killer].Alive) continue;
                        int anchor = AnchorCell(kill.Killer, uG);
                        sim.NotifyKill(kill);
                        if (sim.Inheritance.LastInherited.Length > 0 && players[kill.Killer].Alive) JoinInheritance(kill, anchor, t, uG);
                    }
                }
                rewardedInGroup = true;
            }
            rewarded.Clear();
            killsInGroup.Clear();
        }

        /// <summary>
        /// Before a round end in a group with kill rewards: every alive trailing player whose current cell at uG is now its
        /// own (an inherited cell under its head) returns at uG, exactly as step a would apply that same-instant Return
        /// candidate (capture, R18, R9 stolen cells and TerritoryLost eliminations, chased returns capture nothing).
        /// </summary>
        private void ReturnsBeforeRoundEnd(double t, double uG)
        {
            pending.Clear();
            for (int i = 0; i < n; i++)
            {
                PlayerState p = players[i];
                if (!p.Alive || p.Home || grid.Cells[CellAt(i, uG)] != p.Id) continue;
                pending.Add(new Candidate { Kind = Kind.Return, U = uG, Player = i, Attacker = -1, Point = PosAt(i, uG) });
            }
            if (pending.Count == 0) return;
            saved.Clear();
            saved.AddRange(group);
            group.Clear();
            group.AddRange(pending);
            try
            {
                StepReturns(t, uG);
            }
            finally
            {
                group.Clear();
                group.AddRange(saved);
                saved.Clear();
                pending.Clear();
            }
        }

        /// <summary>
        /// docs/BIOME_TRAITS.md 7.1: a shield ends at its exact end time (the ShieldEnd candidate). Re-validated: the player
        /// is alive and its shield still ends at the candidate's time (a kill of this group may have extended it). Emits
        /// ShieldEnded (Value = the end time). The cut candidates of the next loop pass are computed from this u.
        /// </summary>
        private void StepShieldEnds(double t)
        {
            for (int c = 0; c < group.Count; c++)
            {
                Candidate cand = group[c];
                if (cand.Kind != Kind.ShieldEnd) continue;
                PlayerState p = players[cand.Player];
                if (!p.Alive || !p.Shielded || p.ShieldEnd != cand.S) continue;
                p.ShieldEnd = double.NegativeInfinity;
                sim.Emit(new SimEvent { Type = SimEventType.ShieldEnded, Time = t, Player = cand.Player, Value = cand.S });
            }
        }

        // c. Cuts (R11, R14): attacker alive at the start of this instant; victim alive, trailing, spark-less, not shielded
        // (KillShield: the shield may have started in step b of this very group) and with the trail the candidate was
        // computed on. Largest s_cut per victim wins, ties go to the lowest attacker index.
        private void StepCuts(double t)
        {
            for (int v = 0; v < n; v++)
            {
                int best = -1;
                for (int c = 0; c < group.Count; c++)
                {
                    Candidate cand = group[c];
                    if (cand.Kind != Kind.Cut || cand.Player != v || !aliveAtStart[cand.Attacker]) continue;
                    if (best < 0 || cand.S > group[best].S || (cand.S == group[best].S && cand.Attacker < group[best].Attacker))
                        best = c;
                }
                if (best < 0) continue;
                Candidate win = group[best];
                PlayerState victim = players[v];
                if (!victim.Alive || victim.Home || victim.Spark != null || victim.Shielded || victim.Trail.Version != win.TrailVersion) continue;
                // docs/BIOME_TRAITS.md 7.1: the spark speed is fixed now from the victim's SpeedMultiplier (classic: SparkSpeed).
                victim.Spark = new Spark
                {
                    SCut = win.S, TimeCut = t, Attacker = win.Attacker, S = win.S, PrevS = win.S, Speed = cfg.SparkSpeedOf(victim.SpeedMultiplier),
                    ExitWasCutBefore = victim.ExitWasCut,
                };
                if (inheritanceJoin) RecordCutGeometry(victim.Spark, win.Attacker, win.U);
                victim.ExitWasCut = true;
                players[win.Attacker].CutsMade++;
                sim.Emit(new SimEvent
                {
                    Type = SimEventType.Cut, Time = t, Player = v, Other = win.Attacker, Point = victim.Trail.PointAt(win.S),
                    S = win.S,
                });
            }
        }

        /// <summary>
        /// Rule v1.6: the geometry of a real cut, for a later inheritance bridge: the attacker's head at the cut's own u (Q)
        /// and, when the attacker is trailing then, its exit identity, its trail length at that u (Q's arc) and its
        /// Trail.Dropped.
        /// </summary>
        private void RecordCutGeometry(Spark spark, int attacker, double u)
        {
            PlayerState a = players[attacker];
            spark.Linked = true;
            spark.AttackerHead = PosAt(attacker, u);
            if (!a.Home && a.Trail.Count > 0)
            {
                spark.AttackerEpoch = a.Trail.Epoch;
                spark.AttackerArc = TrailLength(attacker, u);
                spark.AttackerDropped = a.Trail.Dropped;
            }
        }

        // d. Lassos (R16, R17): charged -> pocket, uncharged -> LassoCrossNoCharge; then X is appended as a normal point.
        private void StepLassos(double t)
        {
            for (int c = 0; c < group.Count; c++)
            {
                Candidate cand = group[c];
                if (cand.Kind != Kind.Lasso) continue;
                int i = cand.Player;
                PlayerState p = players[i];
                if (!p.Alive || p.Home || p.Trail.Version != cand.TrailVersion) continue;
                if (p.Charged)
                {
                    pocketScratch.Clear();
                    GridRaster.RasterPolygon(grid, cand.Loop, pocketScratch);
                    pocketScratch.CopyIndices(maskIndices);
                    var added = new List<int>(maskIndices.Count);
                    for (int k = 0; k < maskIndices.Count; k++)
                    {
                        int cell = maskIndices[k];
                        if (grid.Cells[cell] == OwnerGrid.Void) continue;
                        if (!p.Pocket.Get(cell))
                        {
                            p.Pocket.Set(cell);
                            added.Add(cell);
                        }
                    }
                    p.Charged = false;
                    p.PocketsMade++;
                    sim.Emit(new SimEvent
                    {
                        Type = SimEventType.LassoPocket, Time = t, Player = i, Point = cand.Point, Cells = added.ToArray(),
                    });
                }
                else
                {
                    sim.Emit(new SimEvent { Type = SimEventType.LassoCrossNoCharge, Time = t, Player = i, Point = cand.Point });
                }
                p.Trail.Append(cand.Point);
                uTrailEnd[i] = cand.U;
            }
        }

        // e. Pickup (R15): the single eligible player of the candidate takes the ring if still alive and uncharged.
        private void StepPickups(double t)
        {
            for (int c = 0; c < group.Count; c++)
            {
                Candidate cand = group[c];
                if (cand.Kind != Kind.Pickup) continue;
                PlayerState p = players[cand.Player];
                if (sim.Ring == null || !p.Alive || p.Charged) continue;
                p.Charged = true;
                Vec2d at = sim.Ring.Pos;
                sim.Ring = null;
                sim.NextRingTime = t + cfg.LassoRespawn;
                sim.Emit(new SimEvent { Type = SimEventType.RingPicked, Time = t, Player = cand.Player, Point = at });
            }
        }

        // f. Exits (R5): a player still alive and still home (one already made to exit in step a is skipped).
        private void StepExits(double t)
        {
            for (int c = 0; c < group.Count; c++)
            {
                Candidate cand = group[c];
                if (cand.Kind != Kind.Exit) continue;
                int i = cand.Player;
                PlayerState p = players[i];
                if (!p.Alive || !p.Home) continue;
                p.Home = false;
                p.ExitWasCut = false;
                p.Trail.Start(cand.Point);
                uTrailEnd[i] = cand.U;
                sim.Emit(new SimEvent { Type = SimEventType.Exit, Time = t, Player = i, Point = cand.Point });
            }
        }

        // Elimination (idempotent): FinalCells from the group snapshot, DistanceHome BEFORE Neutralize, freed cells,
        // everything of the exit cleared, Kills credited to the spark's attacker even if dead (R12).
        private void Eliminate(int i, EliminationCause cause, int other, double t, double u)
        {
            PlayerState p = players[i];
            if (!p.Alive) return;
            Vec2d head = PosAt(i, u);
            p.FinalCells = snapshot[i];
            p.Pos = head;
            p.Cell = CellAt(i, u);
            if (cause == EliminationCause.Spark)
            {
                double distance = -1.0;
                if (GridQueries.NearestOwned(grid, p.Id, head, 100.0, out Vec2d _, out double dist)) distance = dist;
                sim.Emit(new SimEvent
                {
                    Type = SimEventType.SparkCaught, Time = t, Player = i, Other = other, Point = head, DistanceHome = distance,
                    Cause = EliminationCause.Spark,
                });
            }
            // Rule v1.6 (contract 30): the spark and the victim's trail from its exit to the cut point, kept for the bridge.
            Spark sparkAtKill = null;
            List<Vec2d> victimPrefix = null;
            if (inheritanceJoin && cause == EliminationCause.Spark && p.Spark != null && other >= 0 && other < n)
            {
                sparkAtKill = p.Spark;
                victimPrefix = new List<Vec2d>();
                InheritanceBridge.AppendPrefix(p.Trail, p.Spark.SCut, victimPrefix);
            }
            freed.Clear();
            grid.Neutralize(p.Id, freed);
            freed.Sort();
            int[] freedCells = freed.ToArray();
            // Traits (ScorchedEarth): before the event is raised, so its subscribers already see the scorch.
            if (sim.Behaviours.Length > 0) sim.NotifyEliminated(p, freedCells, t);
            sim.Emit(new SimEvent
            {
                Type = SimEventType.Eliminated, Time = t, Player = i, Other = other, Point = head, Cells = freedCells,
                Cause = cause,
            });
            p.Trail.Clear();
            p.Spark = null;
            p.ExitWasCut = false;
            p.ShieldEnd = double.NegativeInfinity;   // an elimination ends a shield silently (Eliminated tells it)
            p.Pocket.Clear();
            p.Charged = false;
            p.Alive = false;
            p.Home = true;   // a dead player has no trail; keeps "trail empty iff home" true for everyone
            p.EliminatedAt = t;
            p.Cause = cause;
            if (cause == EliminationCause.Spark && other >= 0 && other < n)
            {
                players[other].Kills++;
                // docs/BIOME_TRAITS.md section 7: a kill, rewarded at the end of step b if its killer is still alive.
                if (sim.KillTraits.Length > 0)
                {
                    killsInGroup.Add(new KillInfo
                    {
                        Killer = other, Victim = i, Time = t, Point = head, FreedCells = freedCells, Spark = sparkAtKill,
                        VictimPrefix = victimPrefix,
                    });
                }
            }
            eliminatedInGroup.Add(i);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Small helpers.

        /// <summary>Tick-u slack for events of the final instant on the last tick (same 1e-9 as the uEnd rule).</summary>
        private const double LastTickSlack = 1e-9;

        private static void ClampEntries(List<CellEntry> v, double uMax)
        {
            for (int k = 0; k < v.Count; k++)
            {
                if (v[k].U > uMax)
                {
                    CellEntry e = v[k];
                    e.U = uMax;
                    v[k] = e;
                }
            }
        }

        private Vec2d PosAt(int i, double u) => Vec2d.Lerp(p0[i], p1[i], u);

        private double TrailLength(int i, double u) => players[i].Trail.Length + growth[i] * (u - uTrailEnd[i]);

        private double SparkS(Spark s, double u) => s.SCut + SpeedOf(s) * (t0 + u * dt - s.TimeCut);

        /// <summary>Spark.Speed (docs/BIOME_TRAITS.md 7.1), or SimConfig.SparkSpeed for a Spark built outside the Core (0).</summary>
        private double SpeedOf(Spark s) => s.Speed > 0.0 ? s.Speed : cfg.SparkSpeed;

        // c_i: the last visit entry with U <= u (the current cell at u).
        private static int IndexAt(List<CellEntry> v, double u)
        {
            int c = 0;
            for (int k = 1; k < v.Count; k++)
            {
                if (v[k].U <= u) c = k;
                else break;
            }
            return c;
        }

        private int CellAt(int i, double u)
        {
            List<CellEntry> v = visits[i];
            if (v.Count == 0) return players[i].Cell;
            return v[IndexAt(v, u)].Index;
        }
    }
}
