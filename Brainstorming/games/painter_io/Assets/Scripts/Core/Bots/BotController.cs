// Owned by A5 (bots). Contract 5.7 and section 9: one finite state machine per bot, reading only SimView.
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>What a bot is currently doing (section 9). Exposed for tests, the probe and debug views (api addition).</summary>
    public enum BotMode
    {
        Home,     // inside its land, following (or about to plan) an excursion plan
        Out,      // trailing, following the excursion plan [E + theta depth, side leg, R]
        Return,   // trailing, heading straight for NearestOwned (a return trigger fired)
        Attack,   // committed to an intercept point on an enemy trail (up to 1.5 s)
        Ring,     // going to take the ring
        Idle,     // home and not planning (no valid plan, or not enough round time left): orbits inside its land
    }

    /// <summary>
    /// Section 9 bot. Decisions are taken every 0.1 s of sim time (decision index = floor(Tick * 10 / TickRate)); the
    /// heading is output every tick toward the current target. Reads only the SimView (never mutates anything reachable
    /// from it) and draws every random number from its own Rng, so it is deterministic given its seed and the view.
    /// One instance drives one player; a new round (another SimView, or time going backwards) resets it and re-seeds it.
    /// </summary>
    public sealed class BotController : IController
    {
        /// <summary>Decisions per second of sim time (section 9: every 0.1 s).</summary>
        public const int DecisionsPerSecond = 10;

        /// <summary>Longest commitment to one intercept (section 9).</summary>
        public const double AttackCommitSeconds = 1.5;

        /// <summary>The ring is considered only when its center is within this distance of the head (section 9).</summary>
        public const double RingRange = 8.0;

        /// <summary>A lasso curl crosses the trail at least this far back along its arc (section 9).</summary>
        public const double LassoMinBack = 3.0;

        /// <summary>Extra margin of every plan point from the arena rim on top of ArenaMargin (section 9).</summary>
        public const double PlanBorderMargin = 1.0;

        /// <summary>Radius of NearestOwned searches (section 9).</summary>
        public const double SearchRadius = 100.0;

        /// <summary>Contract 24: a non-lethal (denial) cut is considered only on a victim trail at least this long (u).</summary>
        public const double DenialMinTrail = 6.0;

        /// <summary>Contract 24: the denial draw is AttackChance x this (Aggressive: x DenialScaleAggressive).</summary>
        public const double DenialScale = 0.6;

        /// <summary>Contract 24: the Aggressive denial draw scale.</summary>
        public const double DenialScaleAggressive = 1.0;

        private const double WaypointReach = 0.5;      // a plan point is reached within this distance
        private const double SampleFirstOffset = 0.3;  // attack samples start at L - HeadGrace - 0.3
        private const double SampleSpacing = 0.5;      // and step back 0.5 u along the trail
        private const double LethalSafety = 0.2;       // lethal when C < E_v - 0.2
        private const double ReturnRetargetSeconds = 0.5;
        private const double MinPlanDepth = 1.5;       // shorter excursions are not worth starting
        private const double TransitPenalty = 0.02;    // score per u between the head and E (prefers nearby edges)
        private const double CurlOvershoot = 1.2;      // the curl crosses the trail and ends this far beyond it
        private const double CurlMinWidth = 2.5;
        private const double CurlMaxWidth = 6.0;
        private const double IdleOrbitRadius = 1.5;
        private const double RestMin = 0.1;           // dwell at home after a return before the next plan (s)
        private const double RestMax = 0.6;
        private const double AvoidRecentArc = 1.0;    // the last 1 u of trail never counts as a crossing to avoid
        private const double AvoidMaxDetour = 1.6;    // a detour may be at most this many times the direct distance (+2 u)
        private const double AvoidDepth = 0.5;        // detour targets lie this far inside the own land
        private const double EndOfRoundSlack = 2.0;    // section 9 round-time trigger constant

        /// <summary>
        /// docs/BIOME_TRAITS.md 7.2 (kill-core): while its own shield lasts longer than this (s), a bot ignores threats to
        /// its trail and plans bolder excursions (they cannot cut it yet).
        /// </summary>
        public const double ShieldSafeMargin = 1.0;

        /// <summary>7.2: excursion depth multiplier of a plan made while shielded (longer than ShieldSafeMargin).</summary>
        public const double ShieldBoldness = 1.4;

        /// <summary>
        /// 7.2: under KillInheritance a lethal cut is worth 1 + Share x victim cells / own cells; the lethal draw is
        /// AttackChance x min(that value, LethalValueCap).
        /// </summary>
        public const double LethalValueCap = 1.5;

        private static readonly Vec2d[] Directions = BuildDirections();

        // Fan of ray offsets (radians) tried in order when the straight way home would cross the own trail.
        private static readonly double[] FanAngles = BuildFan();

        private readonly BotPersonality personality;
        private readonly ulong seed;
        private Rng rng;

        // Round binding (Bind resets everything when the view or the player changes, or time goes backwards).
        private SimView view;
        private int self = -1;
        private byte myId;
        private double lastTime = double.NegativeInfinity;
        private long lastDecision = long.MinValue;
        private Arena planArena;            // inset by ArenaMargin + PlanBorderMargin: every plan point is clamped into it
        private Func<byte, bool> notMine, isMine;
        private Vec2d startPos;

        // Traits (docs/BIOME_TRAITS.md section 4), read from the round's SimConfig at Bind. Both are exactly 1 and 0 in
        // classic rounds, where every estimate below keeps its classic expression (bit-identical bots).
        private double homeFactor = 1.0;    // Conduction: speed factor while the current cell is own (SimView.HomeSpeed / PawnSpeed)
        private double reachBonus;          // ArcReach: ContactRadius - (HeadRadius + TrailHalfWidth), the extra cut reach (u)
        private double inheritShare;        // KillInheritance Share (0 without the trait): the value of a lethal cut (7.2)
        // Kill rewards (7.2) are read from the live state: PlayerState.SpeedMultiplier (every speed estimate multiplies by
        // it), PlayerState.Shielded / ShieldEnd (no attack on a shielded enemy, bolder while shielded). All neutral in
        // classic rounds (multiplier 1.0, never shielded), where every expression keeps its classic value bit for bit.

        // Steering.
        private Vec2d target;
        private bool hasTarget;
        private double jitter;
        private Vec2d idleCenter;
        private double restUntil;
        private bool detourActive;          // steering to 'detour' instead of the own-land goal (no own-trail crossing)
        private Vec2d detour;

        // Excursion plan: plan[0 .. returnIndex - 1] are excursion points, plan[returnIndex] is R (inside own land).
        private readonly Vec2d[] plan = new Vec2d[8];
        private int planCount, planIndex, returnIndex;
        private Vec2d planSide;
        private double planWidth;
        private Vec2d edgePoint;

        // Own exit bookkeeping.
        private bool wasTrailing;
        private Vec2d exitPoint;
        private bool lassoDrawn, lassoWanted, curlDone;
        private double threatSince = double.NaN;

        // Rule v1.6 (contract 30): PlayerState.InheritanceBridges seen at the last decision; when it grows while the bot is
        // trailing, the closure target R of its plan is re-picked as the nearest own cell (the domain now includes the band
        // and the inherited land). Never changes in rounds without the single-domain rule.
        private int seenBridges;
        private bool retargetReturn;

        // Attack.
        private int victim = -1;
        private double victimS, attackStart;
        private Vec2d victimExit;

        // Ring.
        private Vec2d ringPos;

        // Return.
        private bool returnHasTarget;
        private Vec2d returnTarget;
        private double returnTargetTime;

        // Per-enemy memory: AttackChance is drawn once per enemy exit (lethal and denial separately).
        private EnemyMemory[] memory = new EnemyMemory[0];

        private struct EnemyMemory
        {
            public bool Trailing;
            public Vec2d Exit;
            public bool LethalDrawn, DenialDrawn;
        }

        public BotController(BotPersonality personality, ulong seed)
        {
            this.personality = personality ?? throw new ArgumentNullException(nameof(personality));
            this.seed = seed;
            rng = new Rng(seed);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Read-only debug surface (api additions: tests, probe, debug views).

        /// <summary>The personality this bot was built with (live object: changes apply from the next decision).</summary>
        public BotPersonality Personality => personality;

        /// <summary>Current FSM state.</summary>
        public BotMode Mode { get; private set; } = BotMode.Home;

        /// <summary>Number of decisions taken since the round started (one per 0.1 s of sim time).</summary>
        public int DecisionCount { get; private set; }

        /// <summary>Player index of the attack target while Mode == Attack, else -1.</summary>
        public int AttackVictim => Mode == BotMode.Attack ? victim : -1;

        /// <summary>The point currently steered at (plan point, return target, intercept or ring), if any.</summary>
        public bool TryGetTarget(out Vec2d point)
        {
            point = target;
            return hasTarget;
        }

        /// <summary>Edge point E of the current excursion plan (section 9).</summary>
        public Vec2d EdgePoint => edgePoint;

        /// <summary>Clears output, then adds the remaining plan points (the next one first; the last one is R).</summary>
        public void CopyPlan(List<Vec2d> output)
        {
            if (output == null) throw new ArgumentNullException(nameof(output));
            output.Clear();
            for (int k = planIndex; k < planCount; k++) output.Add(plan[k]);
        }

        // ------------------------------------------------------------------------------------------------------------
        // IController

        public double? DesiredHeading(SimView view, int playerIndex)
        {
            if (view == null) throw new ArgumentNullException(nameof(view));
            PlayerState me = view.Player(playerIndex);
            if (!me.Alive) return null;
            double t = view.Time;
            if (!ReferenceEquals(view, this.view) || playerIndex != self || t < lastTime - 1e-9) Bind(view, playerIndex, me);
            lastTime = t;

            // Decision clock from the integer tick (Time = Tick / TickRate exactly, so the rounding is exact).
            int rate = view.Config.TickRate;
            long tick = (long)Math.Round(t * rate);
            long decision = tick * DecisionsPerSecond / rate;
            if (decision != lastDecision)
            {
                lastDecision = decision;
                DecisionCount++;
                Decide(me, t);
            }
            return Steer(me);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Round binding

        private void Bind(SimView v, int playerIndex, PlayerState me)
        {
            view = v;
            self = playerIndex;
            myId = me.Id;
            rng = new Rng(seed);
            lastDecision = long.MinValue;
            DecisionCount = 0;
            SimConfig c = v.Config;
            double margin = Math.Min(c.ArenaMargin + PlanBorderMargin, 0.5 * c.ArenaHalfSize);
            planArena = new Arena(c.ArenaHalfSize, c.ArenaCornerRadius, margin, c.ArenaBoundary);
            homeFactor = ConductionTrait.HomeSpeedFactorOf(c.Traits);
            reachBonus = c.ContactRadius - (c.HeadRadius + c.TrailHalfWidth);
            TraitSpec inherit = c.Traits?.Get(TraitId.KillInheritance);
            inheritShare = inherit != null ? inherit.P1 : 0.0;
            byte id = myId;
            notMine = o => o != id;
            isMine = o => o == id;
            detourActive = false;
            startPos = me.Pos;
            idleCenter = me.Pos;
            restUntil = 0.0;
            memory = new EnemyMemory[v.PlayerCount];
            Mode = BotMode.Home;
            hasTarget = false;
            jitter = 0.0;
            planCount = planIndex = returnIndex = 0;
            planSide = Vec2d.Zero;
            planWidth = 0.0;
            edgePoint = me.Pos;
            wasTrailing = false;
            lassoDrawn = lassoWanted = curlDone = false;
            threatSince = double.NaN;
            seenBridges = me.InheritanceBridges;
            retargetReturn = false;
            victim = -1;
            returnHasTarget = false;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Decision (every 0.1 s)

        private void Decide(PlayerState me, double t)
        {
            bool trailing = !me.Home;
            TrackOwnExit(me, trailing);
            TrackEnemies();
            if (me.InheritanceBridges != seenBridges)
            {
                // Rule v1.6: an inheritance bridge joined the land of a victim to this bot's domain. Every own cell is home:
                // the leg to R will aim at the nearest one (and Return mode already does, NearestOwned).
                seenBridges = me.InheritanceBridges;
                retargetReturn = trailing;
                returnHasTarget = false;
            }
            detourActive = false;   // recomputed below by UpdateOut / UpdateReturnTarget

            // Follow the simulation's Home flag (the only truth about safety, R5).
            if (!trailing)
            {
                retargetReturn = false;
                if (Mode == BotMode.Out || Mode == BotMode.Return)
                {
                    // Back home: dwell a moment, heading into the land, before the next plan.
                    Mode = BotMode.Home;
                    ClearPlan();
                    restUntil = t + rng.Range(RestMin, RestMax);
                }
            }
            else if (Mode == BotMode.Home || Mode == BotMode.Idle)
            {
                // The planned exit happened, or the land under the head was taken (R9): follow the plan if any.
                if (PlanRemaining) Mode = BotMode.Out;
                else EnterReturn();
            }

            UpdateThreat(me, t, trailing);
            if (trailing && Mode != BotMode.Return && ReturnTriggered(me, t)) EnterReturn();

            if (Mode == BotMode.Attack && !AttackStillValid(me, t)) EndAttack(trailing);
            if (Mode != BotMode.Return && Mode != BotMode.Attack) TryAttack(me, t);

            if (Mode == BotMode.Ring && !RingStillValid(me)) EndRing(trailing);
            if (Mode == BotMode.Home || Mode == BotMode.Out) TryRing(me);

            if (Mode == BotMode.Out && me.Charged) TryCurl(me);

            switch (Mode)
            {
                case BotMode.Home:
                case BotMode.Idle:
                    UpdateHome(me, t);
                    break;
                case BotMode.Out:
                    UpdateOut(me);
                    break;
                case BotMode.Return:
                    UpdateReturnTarget(me, t);
                    break;
                case BotMode.Attack:
                    target = view.Player(victim).Trail.PointAt(victimS);   // re-aim at the same s_k
                    hasTarget = true;
                    break;
                case BotMode.Ring:
                    target = ringPos;
                    hasTarget = true;
                    break;
            }

            // Heading noise of the Out phase (section 9), redrawn at each decision so the turns stay smooth.
            if ((Mode == BotMode.Home || Mode == BotMode.Out) && personality.Jitter > 0.0)
                jitter = rng.Range(-personality.Jitter, personality.Jitter);
            else jitter = 0.0;
        }

        private bool PlanRemaining => planCount > 0 && planIndex <= returnIndex;

        private void ClearPlan()
        {
            planCount = planIndex = returnIndex = 0;
        }

        private void EnterReturn()
        {
            Mode = BotMode.Return;
            victim = -1;
            returnHasTarget = false;
        }

        /// <summary>A new exit starts when the head becomes trailing or the trail restarts (Points[0] changes).</summary>
        private void TrackOwnExit(PlayerState me, bool trailing)
        {
            if (trailing)
            {
                Vec2d start = me.Trail.Points[0];
                if (!wasTrailing || start != exitPoint)
                {
                    exitPoint = start;
                    lassoDrawn = lassoWanted = curlDone = false;
                    threatSince = double.NaN;
                }
            }
            wasTrailing = trailing;
        }

        /// <summary>Resets the per-enemy attack draws whenever an enemy starts a new exit (bookkeeping only).</summary>
        private void TrackEnemies()
        {
            for (int i = 0; i < memory.Length; i++)
            {
                if (i == self) continue;
                PlayerState p = view.Player(i);
                bool tr = p.Alive && !p.Home && p.Trail.Count > 0;
                if (tr)
                {
                    Vec2d ex = p.Trail.Points[0];
                    if (!memory[i].Trailing || ex != memory[i].Exit) memory[i] = new EnemyMemory { Trailing = true, Exit = ex };
                }
                else memory[i].Trailing = false;
            }
        }

        /// <summary>An enemy is visible when alive and its head is within SenseRadius of this bot's head (section 9).</summary>
        private bool Visible(PlayerState me, PlayerState other)
        {
            return other.Alive && other.Index != self && Vec2d.Distance(me.Pos, other.Pos) <= personality.SenseRadius;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Return triggers

        /// <summary>Threat bookkeeping: a visible enemy head within ThreatRadius of the exposed part of the own trail.</summary>
        private void UpdateThreat(PlayerState me, double t, bool trailing)
        {
            bool threat = false;
            // KillShield (7.2): no enemy can cut a shielded trail; threats count again ShieldSafeMargin before the end.
            if (trailing && ShieldLeft(me, t) <= ShieldSafeMargin)
            {
                Trail trail = me.Trail;
                double length = trail.Length;
                double exposed = length - view.Config.HeadGrace;
                double radius = personality.ThreatRadius;
                if (exposed > 0.0)
                {
                    for (int i = 0; i < view.PlayerCount && !threat; i++)
                    {
                        PlayerState e = view.Player(i);
                        if (!Visible(me, e)) continue;
                        // Every trail point lies within arc distance L of the head: a cheap rejection first.
                        if (Vec2d.Distance(e.Pos, me.Pos) > length + radius) continue;
                        threat = BotSenses.DistanceToTrailPrefix(trail, exposed, e.Pos, radius) <= radius;
                    }
                }
            }
            if (!threat) threatSince = double.NaN;
            else if (double.IsNaN(threatSince)) threatSince = t;
        }

        private bool ReturnTriggered(PlayerState me, double t)
        {
            BotPersonality bp = personality;
            SimConfig c = view.Config;
            double length = me.Trail.Length;
            double v = c.PawnSpeed * me.SpeedMultiplier;   // trailing speed (7.1; exactly PawnSpeed in classic rounds)
            // KillShield (7.2): the trail may grow by the distance covered while the shield still protects it.
            double maxTrail = bp.MaxTrailLength;
            double shieldLeft = ShieldLeft(me, t);
            if (shieldLeft > 0.0) maxTrail += shieldLeft * v;
            if (length > maxTrail) return true;
            // A new own spark or a new threat is ignored for ReactionDelay seconds.
            if (me.Spark != null && t >= me.Spark.TimeCut + bp.ReactionDelay - 1e-9) return true;
            // 7.1: a cut exit never captures; once KillShield extinguished its spark there is nothing left to gain out
            // there (never true in classic rounds, where ExitWasCut means "has a spark").
            if (me.ExitWasCut && me.Spark == null) return true;
            if (!double.IsNaN(threatSince) && t - threatSince >= bp.ReactionDelay - 1e-9) return true;
            // Round time: Time + D_home / PawnSpeed + 2 >= RoundDuration. D_home <= L + one cell while the exit cell is
            // still owned, so the NearestOwned search is skipped while even that bound cannot trigger (and always run in
            // the last 15 s, which covers a stolen exit cell).
            double rd = c.RoundDuration;
            if (t + (length + 1.0) / v + EndOfRoundSlack >= rd || t >= rd - 15.0)
            {
                if (GridQueries.NearestOwned(view.Grid, myId, me.Pos, SearchRadius, out _, out double dHome)
                    && t + dHome / v + EndOfRoundSlack >= rd) return true;
            }
            return false;
        }

        private void UpdateReturnTarget(PlayerState me, double t)
        {
            OwnerGrid g = view.Grid;
            bool refresh = !returnHasTarget || g.OwnerAt(returnTarget) != myId || t - returnTargetTime >= ReturnRetargetSeconds - 1e-9;
            if (refresh)
            {
                returnHasTarget = GridQueries.NearestOwned(g, myId, me.Pos, SearchRadius, out returnTarget, out _);
                returnTargetTime = t;
            }
            // Avoid crossing the own trail on the way home (section 9), except when chased: then the shortest way wins.
            detourActive = returnHasTarget && me.Spark == null && !me.Charged && FindDetour(me, returnTarget, out detour);
            target = detourActive ? detour : returnTarget;
            hasTarget = returnHasTarget;
        }

        /// <summary>
        /// Section 9 "avoid crossing own trail when uncharged". When the straight path from the head to an own-land goal
        /// crosses an older part of the own trail (an uncharged crossing loop-erases the capture, R8), returns an own-land
        /// entry point found by rays fanned around the goal direction (GridRaster.FirstEntry, smallest angular offset first)
        /// whose straight path crosses nothing, within AvoidMaxDetour times the direct distance + 2 u. False when no
        /// detour is needed or none exists (the bot then keeps the straight way).
        /// </summary>
        private bool FindDetour(PlayerState me, Vec2d goal, out Vec2d result)
        {
            result = goal;
            Trail trail = me.Trail;
            double maxArc = trail.Length - AvoidRecentArc;
            Vec2d head = me.Pos;
            if (maxArc <= 0.0 || !BotSenses.CrossesTrail(trail, maxArc, head, goal)) return false;
            OwnerGrid g = view.Grid;
            double reach = Vec2d.Distance(head, goal) * AvoidMaxDetour + 2.0;
            double baseAngle = (goal - head).Angle();
            for (int k = 0; k < FanAngles.Length; k++)
            {
                Vec2d dir = Vec2d.FromAngle(baseAngle + FanAngles[k]);
                Vec2d far = head + dir * reach;
                if (!GridRaster.FirstEntry(g, head, far, isMine, out double u)) continue;
                Vec2d entry = Vec2d.Lerp(head, far, u);
                Vec2d candidate = entry + dir * AvoidDepth;
                if (g.OwnerAt(candidate) != myId) candidate = entry + dir * (0.4 * g.CellSize);
                if (BotSenses.CrossesTrail(trail, maxArc, head, candidate)) continue;
                result = candidate;
                return true;
            }
            return false;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Home: plan an excursion from the edge point E

        private void UpdateHome(PlayerState me, double t)
        {
            if (Mode == BotMode.Home && PlanRemaining)
            {
                SkipOwnedExcursionPoints();
                if (planIndex < returnIndex)
                {
                    target = plan[planIndex];
                    hasTarget = true;
                    return;
                }
            }
            if (t < restUntil)
            {
                UpdateIdleCenter(me);
                hasTarget = false;
                return;
            }
            // No plan (or it degenerated, or the bot is idle): try a fresh plan at every decision.
            if (Plan(me, t))
            {
                Mode = BotMode.Home;
                target = plan[planIndex];
                hasTarget = true;
                return;
            }
            Mode = BotMode.Idle;
            ClearPlan();
            UpdateIdleCenter(me);
            hasTarget = false;
        }

        /// <summary>
        /// Section 9 plan: theta among 8 directions by the sector score beyond E, then [E + theta depth, a side leg of
        /// length width toward the higher-scoring half, R = E - theta * 1], every point clamped into the arena inset by an
        /// extra PlanBorderMargin. Returns false when no direction gives a usable excursion or the round is too close to
        /// its end for even a short one.
        /// </summary>
        private bool Plan(PlayerState me, double t)
        {
            BotPersonality bp = personality;
            SimConfig c = view.Config;
            OwnerGrid g = view.Grid;
            Vec2d head = me.Pos;
            double rivalValue = bp.Style == BotStyle.Aggressive ? 1.5 : bp.Style == BotStyle.Cautious ? 0.2 : 0.5;
            double reach = 3.0 * c.ArenaHalfSize;
            bool outside = g.Cells[me.Cell] != myId;
            double maxOut = Math.Max(bp.MaxOut, 1.0);

            double[] score = scoreScratch, left = leftScratch, right = rightScratch;
            Vec2d[] edges = edgeScratch;
            for (int d = 0; d < 8; d++)
            {
                score[d] = double.NegativeInfinity;
                Vec2d e = head;
                if (!outside && !BotSenses.EdgePoint(g, notMine, isMine, head, Directions[d], reach, out e)) continue;
                edges[d] = e;
                // An edge inside the rim band leaves no room for an excursion in that direction.
                if (planArena.SignedDistance(e) > -planArena.Margin) continue;
                BotSenses.ScoreSector(g, myId, e, d * (Math.PI / 4.0), maxOut, rivalValue, out double tot, out double l, out double r);
                if (!(tot > 0.0)) continue;
                score[d] = tot * rng.Range(0.85, 1.15) - TransitPenalty * Vec2d.Distance(head, e);
                left[d] = l;
                right[d] = r;
            }

            double depth = rng.Range(Math.Min(bp.MinOut, bp.MaxOut), Math.Max(bp.MinOut, bp.MaxOut));
            double widthFactor = rng.Range(0.6, 1.2);
            bool tieLeft = rng.NextDouble() < 0.5;
            // KillShield (7.2): bolder while shielded (no extra random draw, so the draw sequence is unchanged).
            if (ShieldLeft(me, t) > ShieldSafeMargin) depth *= ShieldBoldness;
            double speed = c.PawnSpeed * me.SpeedMultiplier;   // KillSpeedBoost (7.1); exactly PawnSpeed in classic rounds

            for (int attempt = 0; attempt < 8; attempt++)
            {
                int best = -1;
                for (int d = 0; d < 8; d++)
                {
                    if (score[d] > double.NegativeInfinity && (best < 0 || score[d] > score[best])) best = d;
                }
                if (best < 0) return false;
                score[best] = double.NegativeInfinity;

                Vec2d dir = Directions[best];
                Vec2d e = edges[best];
                bool toLeft = left[best] > right[best] || (left[best] == right[best] && tieLeft);
                Vec2d side = toLeft ? dir.Perp() : -dir.Perp();

                // End of round: the excursion (head to E, then about depth (1 + f + sqrt(1 + f^2)) of trail) must end
                // EndOfRoundSlack seconds before the round does; shrink it, or try a nearer edge (no direction: Idle).
                double perDepth = 1.0 + widthFactor + Math.Sqrt(1.0 + widthFactor * widthFactor);
                double transit = Vec2d.Distance(head, e);
                double budget;
                if (homeFactor != 1.0 && !outside)
                {
                    // Conduction: the transit from the head to E runs on own land at PawnSpeed x factor.
                    budget = (c.RoundDuration - EndOfRoundSlack - t - transit / (speed * homeFactor)) * speed;
                }
                else budget = (c.RoundDuration - EndOfRoundSlack - t) * speed - transit;
                double dep = Math.Min(depth, budget / perDepth);
                if (dep < MinPlanDepth) continue;
                double wid = dep * widthFactor;

                Vec2d p1 = planArena.ClampInside(e + dir * dep);
                if (g.OwnerAt(p1) == myId) continue;   // the sector beyond E is own land after all (hole, clamp)
                Vec2d p2 = planArena.ClampInside(p1 + side * wid);
                Vec2d r = ReturnPoint(g, e, dir, p2);

                plan[0] = p1;
                plan[1] = p2;
                plan[2] = r;
                planCount = 3;
                returnIndex = 2;
                planIndex = 0;
                planSide = side;
                planWidth = wid;
                edgePoint = e;
                return true;
            }
            return false;
        }

        // Per-plan scratch (no allocation per plan).
        private readonly Vec2d[] edgeScratch = new Vec2d[8];
        private readonly double[] scoreScratch = new double[8];
        private readonly double[] leftScratch = new double[8];
        private readonly double[] rightScratch = new double[8];

        /// <summary>R = E - theta * 1 (1 u inside own land), or the nearest own cell pushed 1 u deeper when that is not own.</summary>
        private Vec2d ReturnPoint(OwnerGrid g, Vec2d e, Vec2d dir, Vec2d from)
        {
            Vec2d r = planArena.ClampInside(e - dir * 1.0);
            if (g.OwnerAt(r) == myId) return r;
            return DeeperOwned(g, e, from, r);
        }

        /// <summary>NearestOwned(near) pushed 1 u deeper along the approach direction from 'from' (fallback 'fallback').</summary>
        private Vec2d DeeperOwned(OwnerGrid g, Vec2d near, Vec2d from, Vec2d fallback)
        {
            if (!GridQueries.NearestOwned(g, myId, near, SearchRadius, out Vec2d owned, out _)) return fallback;
            Vec2d approach = (owned - from).Normalized();
            Vec2d deeper = planArena.ClampInside(owned + approach * 1.0);
            return g.OwnerAt(deeper) == myId ? deeper : owned;
        }

        /// <summary>Skips every excursion point (not R) that has become own territory (section 9).</summary>
        private void SkipOwnedExcursionPoints()
        {
            OwnerGrid g = view.Grid;
            while (planIndex < returnIndex && g.OwnerAt(plan[planIndex]) == myId) planIndex++;
        }

        private void UpdateIdleCenter(PlayerState me)
        {
            OwnerGrid g = view.Grid;
            if (g.OwnerAt(startPos) == myId) idleCenter = startPos;
            else if (g.OwnerAt(idleCenter) != myId
                     && GridQueries.NearestOwned(g, myId, me.Pos, SearchRadius, out Vec2d owned, out _)) idleCenter = owned;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Out: follow the plan

        private void UpdateOut(PlayerState me)
        {
            SkipOwnedExcursionPoints();
            if (!PlanRemaining)
            {
                EnterReturn();
                UpdateReturnTarget(me, view.Time);
                return;
            }
            OwnerGrid g = view.Grid;
            if (g.OwnerAt(plan[returnIndex]) != myId)
            {
                // R was taken: nearest own cell, pushed 1 u deeper along the approach direction.
                Vec2d from = planIndex == returnIndex ? me.Pos : plan[returnIndex - 1];
                plan[returnIndex] = DeeperOwned(g, me.Pos, from, plan[returnIndex]);
            }
            else if (retargetReturn && planIndex == returnIndex)
            {
                // Rule v1.6: after a bridge, close into the nearest own cell (band or inherited land included).
                plan[returnIndex] = DeeperOwned(g, me.Pos, me.Pos, plan[returnIndex]);
                retargetReturn = false;
            }
            if (planIndex == returnIndex) retargetReturn = false;
            // On the leg to R, avoid crossing the own trail when uncharged (section 9).
            detourActive = planIndex == returnIndex && !me.Charged && FindDetour(me, plan[returnIndex], out detour);
            target = detourActive ? detour : plan[planIndex];
            hasTarget = true;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Attack (contract 24: lethal-sample rule first, otherwise a denial cut on a trail of at least DenialMinTrail)

        /// <summary>
        /// Section 9 attack amended by contract 24 (every cut denies the victim's capture, R13 v1.4). For each visible enemy
        /// that is trailing without a spark, the exposed trail is sampled at s_k = L - HeadGrace - 0.3 - 0.5 k within
        /// AttackRadius. Preferred: the lethal sample with the largest s_k (C &lt; E_v - 0.2), taken with probability
        /// AttackChance. Otherwise a denial cut on the largest reachable s_k when the victim's trail is at least
        /// DenialMinTrail long, with probability AttackChance x DenialScale (Aggressive: x DenialScaleAggressive). Both
        /// draws are made once per enemy exit and are scaled by HumanAttackScale when the victim is the human; the chosen
        /// intercept follows the usual commit / abort rules (StartAttack, AttackStillValid).
        /// </summary>
        private void TryAttack(PlayerState me, double t)
        {
            BotPersonality bp = personality;
            double denialScale = bp.Style == BotStyle.Aggressive ? DenialScaleAggressive : DenialScale;
            if (!(bp.AttackChance > 0.0) || !(bp.AttackRadius > 0.0)) return;
            SimConfig c = view.Config;
            double v = c.PawnSpeed;
            if (!(v > 0.0)) return;
            double turnRate = c.TurnRateRad;
            // docs/BIOME_TRAITS.md 7.1 / 7.2: speeds carry each player's SpeedMultiplier and the predicted spark follows the
            // victim's (SimConfig.SparkSpeedOf). Classic rounds: every multiplier is 1.0, so vMe = vv = PawnSpeed and
            // closing = SparkSpeed - PawnSpeed exactly as before.
            double vMe = v * me.SpeedMultiplier;
            double myCells = inheritShare > 0.0 ? view.Grid.CountOf(myId) : 0.0;

            int lethalVictim = -1, denialVictim = -1;
            double lethalS = -1.0, denialS = -1.0, lethalValue = 0.0;
            for (int i = 0; i < view.PlayerCount; i++)
            {
                PlayerState pv = view.Player(i);
                if (i == self || !pv.Alive || pv.Home || pv.Spark != null || !Visible(me, pv)) continue;
                if (pv.Shielded) continue;   // KillShield (7.2): never aim at a shielded enemy
                double vv = v * pv.SpeedMultiplier;
                double closing = c.SparkSpeedOf(pv.SpeedMultiplier) - vv;
                if (!(closing > 0.0)) continue;
                Trail trail = pv.Trail;
                double length = trail.Length;
                bool denialOpen = !memory[i].DenialDrawn && length >= DenialMinTrail;
                if (memory[i].LethalDrawn && !denialOpen) continue;
                double sTop = length - c.HeadGrace - SampleFirstOffset;
                if (sTop < 0.0) continue;
                if (Vec2d.Distance(pv.Pos, me.Pos) > length + bp.AttackRadius) continue;

                IReadOnlyList<Vec2d> pts = trail.Points;
                IReadOnlyList<double> arc = trail.Arc;
                int seg = trail.Count - 2;
                double escape = double.NaN;       // E_v, computed lazily (one NearestOwned per enemy and decision)
                double reachS = -1.0, foundLethal = -1.0;
                bool wantLethal = !memory[i].LethalDrawn;
                bool wantDenial = denialOpen;
                for (int k = 0; ; k++)
                {
                    double s = sTop - SampleSpacing * k;
                    if (s < 0.0) break;
                    // Once even an instant intercept could not be lethal, no older sample can be (G only grows).
                    if (wantLethal && !double.IsNaN(escape) && (length - s) / closing >= escape - LethalSafety) wantLethal = false;
                    if (!wantLethal && (!wantDenial || reachS >= 0.0)) break;
                    while (seg > 0 && arc[seg] > s) seg--;
                    double s0 = arc[seg], s1 = arc[seg + 1];
                    Vec2d p = s1 > s0 ? Vec2d.Lerp(pts[seg], pts[seg + 1], (s - s0) / (s1 - s0)) : pts[seg];
                    Vec2d rel = p - me.Pos;
                    double dist = rel.Length;
                    if (dist > bp.AttackRadius) continue;
                    // Denial aim: the largest reachable s_k, i.e. the most recent sample within AttackRadius (as the v1.3
                    // harassment aim; also requiring T < E_v made such cuts rarer and cut the asserted cut share).
                    if (reachS < 0.0) reachS = s;
                    if (!wantLethal) continue;
                    if (double.IsNaN(escape))
                    {
                        escape = GridQueries.NearestOwned(view.Grid, pv.Id, pv.Pos, SearchRadius, out _, out double dv)
                            ? dv / vv : double.PositiveInfinity;
                        if ((length - s) / closing >= escape - LethalSafety)
                        {
                            wantLethal = false;   // even an instant intercept here could not be lethal
                            continue;
                        }
                    }
                    double turn = turnRate > 0.0 && dist > 0.0 ? Math.Abs(Geo.WrapAngle(rel.Angle() - me.Heading)) / turnRate : 0.0;
                    double time = (homeFactor != 1.0 || reachBonus != 0.0) ? InterceptTime(me, p, dist, vMe) + turn : dist / vMe + turn;
                    double gap = length + vv * time - s;
                    double catchTime = gap / closing;
                    if (catchTime < escape - LethalSafety)
                    {
                        foundLethal = s;
                        break;
                    }
                }
                bool takeLethal;
                double value = 1.0;
                if (inheritShare > 0.0 && foundLethal >= 0.0 && !memory[i].LethalDrawn)
                {
                    // KillInheritance (7.2): the lethal cut also brings the victim's land; prefer the most valuable victim,
                    // then the largest s_k.
                    value = 1.0 + inheritShare * view.Grid.CountOf(pv.Id) / Math.Max(1.0, myCells);
                    takeLethal = lethalVictim < 0 || value > lethalValue || (value == lethalValue && foundLethal > lethalS);
                }
                else takeLethal = foundLethal >= 0.0 && !memory[i].LethalDrawn && foundLethal > lethalS;
                if (takeLethal)
                {
                    lethalS = foundLethal;
                    lethalVictim = i;
                    lethalValue = value;
                }
                else if (denialOpen && reachS >= 0.0 && reachS > denialS)
                {
                    denialS = reachS;
                    denialVictim = i;
                }
            }

            if (lethalVictim >= 0)
            {
                memory[lethalVictim].LethalDrawn = true;
                double chance = bp.AttackChance * HumanScale(lethalVictim);
                if (inheritShare > 0.0) chance *= Math.Min(lethalValue, LethalValueCap);
                if (rng.NextDouble() < chance)
                {
                    StartAttack(lethalVictim, lethalS, t);
                    return;
                }
            }
            if (denialVictim >= 0)
            {
                memory[denialVictim].DenialDrawn = true;
                if (rng.NextDouble() < bp.AttackChance * denialScale * HumanScale(denialVictim)) StartAttack(denialVictim, denialS, t);
            }
        }

        /// <summary>
        /// Travel time to an intercept point under the round's traits (classic rounds never call it). ArcReach: the cut
        /// happens reachBonus earlier along the approach. Conduction: while the bot is home, the part of the straight way
        /// that stays on its own land (up to the first non-own cell, GridRaster.FirstEntry) is covered at PawnSpeed x
        /// factor, the rest at PawnSpeed (docs/BIOME_TRAITS.md section 4).
        /// </summary>
        private double InterceptTime(PlayerState me, Vec2d point, double dist, double v)
        {
            return InterceptTime(view.Grid, me, point, dist, v, homeFactor, reachBonus, notMine);
        }

        /// <summary>
        /// Seconds the player's head needs to bring point within cut contact along a straight line, turning ignored, under
        /// the round's traits (api addition, docs/BIOME_TRAITS.md section 4): distance / PawnSpeed in classic rounds;
        /// ArcReach shortens the approach by ContactRadius - (HeadRadius + TrailHalfWidth); with Conduction a home player
        /// covers the part of the way that stays on its own land at SimView.HomeSpeed; every speed is multiplied by the
        /// player's SpeedMultiplier (KillSpeedBoost, docs/BIOME_TRAITS.md 7.1).
        /// </summary>
        public static double InterceptTravelTime(SimView view, int playerIndex, Vec2d point)
        {
            if (view == null) throw new ArgumentNullException(nameof(view));
            SimConfig c = view.Config;
            PlayerState me = view.Player(playerIndex);
            byte id = me.Id;
            double reach = c.ContactRadius - (c.HeadRadius + c.TrailHalfWidth);
            return InterceptTime(view.Grid, me, point, Vec2d.Distance(me.Pos, point), c.PawnSpeed * me.SpeedMultiplier,
                                 ConductionTrait.HomeSpeedFactorOf(c.Traits), reach, o => o != id);
        }

        private static double InterceptTime(OwnerGrid g, PlayerState me, Vec2d point, double dist, double v, double factor,
                                            double reach, Func<byte, bool> notOwn)
        {
            double approach = reach != 0.0 ? Math.Max(0.0, dist - reach) : dist;
            if (factor == 1.0 || !me.Home || approach <= 0.0) return approach / v;
            double onOwn = approach;
            if (GridRaster.FirstEntry(g, me.Pos, point, notOwn, out double u)) onOwn = Math.Min(approach, u * dist);
            return onOwn / (v * factor) + (approach - onOwn) / v;
        }

        /// <summary>HumanAttackScale applies when the target is the human; IsHuman is read for nothing else (section 9).</summary>
        private double HumanScale(int index) => view.Player(index).IsHuman ? personality.HumanAttackScale : 1.0;

        /// <summary>Seconds of KillShield left at t (0 when not shielded; always 0 in classic rounds).</summary>
        private static double ShieldLeft(PlayerState p, double t) => p.Shielded ? p.ShieldEnd - t : 0.0;

        private void StartAttack(int index, double s, double t)
        {
            PlayerState pv = view.Player(index);
            Mode = BotMode.Attack;
            victim = index;
            victimS = s;
            attackStart = t;
            victimExit = pv.Trail.Points[0];
        }

        private bool AttackStillValid(PlayerState me, double t)
        {
            if (victim < 0) return false;
            PlayerState pv = view.Player(victim);
            if (!pv.Alive || pv.Home || pv.Spark != null || pv.Trail.Count == 0) return false;   // home, cut, dead
            if (pv.Shielded) return false;                                                        // KillShield (7.2)
            if (pv.Trail.Points[0] != victimExit) return false;                                   // another exit
            if (t - attackStart > AttackCommitSeconds + 1e-9) return false;
            return Visible(me, pv);
        }

        private void EndAttack(bool trailing)
        {
            victim = -1;
            if (trailing) EnterReturn();
            else
            {
                Mode = BotMode.Home;
                ClearPlan();
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Ring and lasso

        private void TryRing(PlayerState me)
        {
            Ring ring = view.Ring;
            if (ring == null || me.Charged) return;
            if (!RingSafe(me, ring.Pos)) return;
            ringPos = ring.Pos;
            Mode = BotMode.Ring;
        }

        /// <summary>Section 9 safe ring: within 8 u, no visible enemy head within ThreatRadius of the bot or of the ring,
        /// and trail length + 2 x distance to the ring &lt;= MaxTrailLength. While trailing (always uncharged here) the
        /// straight way to the ring must not cross the own trail either (section 9, an uncharged crossing loop-erases
        /// the capture, R8).</summary>
        private bool RingSafe(PlayerState me, Vec2d pos)
        {
            double d = Vec2d.Distance(me.Pos, pos);
            if (d > RingRange) return false;
            double length = me.Trail.Length;
            if (length + 2.0 * d > personality.MaxTrailLength) return false;
            if (!me.Home && BotSenses.CrossesTrail(me.Trail, length - AvoidRecentArc, me.Pos, pos)) return false;
            double radius = personality.ThreatRadius;
            for (int i = 0; i < view.PlayerCount; i++)
            {
                PlayerState e = view.Player(i);
                if (!Visible(me, e)) continue;
                if (Vec2d.Distance(e.Pos, me.Pos) <= radius || Vec2d.Distance(e.Pos, pos) <= radius) return false;
            }
            return true;
        }

        private bool RingStillValid(PlayerState me)
        {
            Ring ring = view.Ring;
            return ring != null && ring.Pos == ringPos && !me.Charged && RingSafe(me, ring.Pos);
        }

        private void EndRing(bool trailing)
        {
            if (!trailing) Mode = BotMode.Home;          // keeps the plan if one is pending
            else if (PlanRemaining) Mode = BotMode.Out;
            else EnterReturn();
        }

        /// <summary>
        /// Lasso (section 9): once per exit while charged, a draw below LassoChance makes the bot curl a loop once it has
        /// passed the tip of its plan: sideways by w, back parallel to the trail, then across the trail at X = the point
        /// b &gt;= 3 u back along the arc, ending CurlOvershoot beyond it, then R. The loop X..head..Q1..Q2..X is a b x w
        /// pocket (R16 needs 0.75 u^2). Skipped when the trail budget (MaxTrailLength) or the arena cannot hold it.
        /// </summary>
        private void TryCurl(PlayerState me)
        {
            BotPersonality bp = personality;
            if (!lassoDrawn)
            {
                lassoDrawn = true;
                lassoWanted = bp.LassoChance > 0.0 && rng.NextDouble() < bp.LassoChance;
            }
            if (!lassoWanted || curlDone || planIndex < 1 || !PlanRemaining) return;

            Trail trail = me.Trail;
            double length = trail.Length;
            double back = Math.Min(Math.Max(LassoMinBack, 0.7 * length), Math.Min(8.0, length - 0.5));
            if (back < LassoMinBack) return;   // not enough trail yet: retry at the next decision
            curlDone = true;                   // one attempt per exit from here on

            Vec2d head = me.Pos;
            Vec2d x = trail.PointAt(length - back);
            Vec2d axis = head - x;
            double axisLength = axis.Length;
            if (axisLength < 0.5 * back) return;   // the recent trail is too curved for a clean rectangle
            axis = axis / axisLength;
            Vec2d n = axis.Perp();
            if (Vec2d.Dot(n, planSide) < 0.0) n = -n;

            double width = Math.Min(Math.Max(planWidth, CurlMinWidth), CurlMaxWidth);
            double widthBudget = (bp.MaxTrailLength - length - axisLength - CurlOvershoot - 1.0) / 2.0;
            width = Math.Min(width, widthBudget);
            if (width < CurlMinWidth) return;

            Vec2d q1 = head + n * width;
            Vec2d q2 = x + n * width;
            Vec2d q3 = x - n * CurlOvershoot;
            if (!InsidePlanArena(q1) || !InsidePlanArena(q2) || !InsidePlanArena(q3)) return;

            Vec2d r = plan[returnIndex];
            plan[0] = q1;
            plan[1] = q2;
            plan[2] = q3;
            plan[3] = r;
            planCount = 4;
            returnIndex = 3;
            planIndex = 0;
        }

        private bool InsidePlanArena(Vec2d p) => Vec2d.Distance(planArena.ClampInside(p), p) <= 0.5;

        // ------------------------------------------------------------------------------------------------------------
        // Steering (every tick)

        private double? Steer(PlayerState me)
        {
            switch (Mode)
            {
                case BotMode.Home:
                case BotMode.Out:
                    AdvanceWaypoints(me);
                    if (planIndex < planCount)
                    {
                        bool onDetour = detourActive && planIndex == returnIndex;
                        target = onDetour ? detour : plan[planIndex];
                        hasTarget = true;
                        return Aim(me.Pos, target, onDetour ? 0.0 : jitter);
                    }
                    return Orbit(me);
                case BotMode.Return:
                case BotMode.Attack:
                case BotMode.Ring:
                    return hasTarget ? Aim(me.Pos, target, 0.0) : (double?)null;
                default:
                    return Orbit(me);
            }
        }

        /// <summary>
        /// Advances past every plan point reached (within WaypointReach), or passed: within the turning diameter
        /// 2 PawnSpeed / TurnRate and behind the head, so a point approached from the side is never orbited.
        /// </summary>
        private void AdvanceWaypoints(PlayerState me)
        {
            SimConfig c = view.Config;
            double turnRate = c.TurnRateRad;
            // Conduction: at home the bot moves at PawnSpeed x factor, so its turning circle is that much wider; the same for
            // KillSpeedBoost's SpeedMultiplier (7.2: faster pawns turn wider), 1.0 in classic rounds.
            double baseSpeed = c.PawnSpeed * me.SpeedMultiplier;
            double speed = homeFactor != 1.0 && me.Home ? baseSpeed * homeFactor : baseSpeed;
            double pass = turnRate > 0.0 ? 2.0 * speed / turnRate : 0.0;
            Vec2d forward = Vec2d.FromAngle(me.Heading);
            while (planIndex < planCount)
            {
                Vec2d rel = plan[planIndex] - me.Pos;
                double d = rel.Length;
                if (d <= WaypointReach || (d < pass && Vec2d.Dot(forward, rel) < 0.0)) planIndex++;
                else break;
            }
        }

        private static double? Aim(Vec2d from, Vec2d to, double noise)
        {
            Vec2d rel = to - from;
            if (rel.LengthSq < 1e-18) return null;
            return Geo.WrapAngle(rel.Angle() + noise);
        }

        /// <summary>Counter-clockwise orbit of radius 1.5 around the idle center (stays home, like HomeCirclerController).</summary>
        private double? Orbit(PlayerState me)
        {
            hasTarget = false;
            Vec2d rel = me.Pos - idleCenter;
            double r = rel.Length;
            if (r < 1e-9) return null;
            double correction = 2.0 * (r - IdleOrbitRadius);
            if (correction > 0.5 * Math.PI) correction = 0.5 * Math.PI;
            if (correction < -0.5 * Math.PI) correction = -0.5 * Math.PI;
            return Geo.WrapAngle(rel.Angle() + 0.5 * Math.PI + correction);
        }

        private static double[] BuildFan()
        {
            double[] degrees = { 12, -12, 24, -24, 36, -36, 50, -50, 65, -65, 80, -80 };
            var fan = new double[degrees.Length];
            for (int k = 0; k < degrees.Length; k++) fan[k] = degrees[k] * (Math.PI / 180.0);
            return fan;
        }

        private static Vec2d[] BuildDirections()
        {
            var dirs = new Vec2d[8];
            for (int d = 0; d < 8; d++) dirs[d] = Vec2d.FromAngle(d * (Math.PI / 4.0));
            return dirs;
        }
    }
}
