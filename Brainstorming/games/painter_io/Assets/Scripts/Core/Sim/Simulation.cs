// Owned by A4 (sim). Contract sections 4 (rules R1-R20), 5.5 (API) and 6 (event engine).
// Simulation owns the round state and the tick skeleton; EventResolver runs steps 1-2 of section 6 (motion, event loop,
// group application) and RingSpawner the ring rule of step 3.
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// One round of Painter IO (contract 5.5). Deterministic: same config, setup and controller decisions give the same
    /// StateHash. Step() advances exactly one tick of 1 / TickRate seconds (the last tick may be partial, section 6).
    /// </summary>
    public sealed class Simulation
    {
        /// <summary>Raised in resolution order during Step.</summary>
        public event Action<SimEvent> EventRaised;

        /// <summary>Raised at the start of Step(), before controllers are polled (tests, probe: key on the integer Tick).</summary>
        public event Action<Simulation> BeforeTick;

        private readonly PlayerState[] players;
        private readonly List<SimEvent> lastEvents = new List<SimEvent>();
        private readonly EventResolver resolver;
        private readonly RingSpawner ringSpawner;
        private readonly SimSetup setup;

        // Biome traits (docs/BIOME_TRAITS.md section 4). Empty / false / "" in classic rounds, where none of the trait
        // code paths runs, so the classic simulation and its StateHash are bit-identical to the ones without traits.
        private readonly bool traitsActive;
        private readonly string traitKey;
        private readonly List<SimEvent> traitEvents = new List<SimEvent>();
        private readonly List<int> captureScratch = new List<int>();
        private readonly List<ScorchedEarthTrait.Batch> scorchScratch = new List<ScorchedEarthTrait.Batch>();
        private double traitTime = double.NaN;

        // R19: rank of an eliminated player, fixed when the Step that eliminated it returns (0 while alive).
        internal readonly int[] EliminatedRank;

        /// <summary>
        /// Builds the round. The config is cloned (later changes to the caller's object do not leak into the round) and
        /// its PlayerCount is set to controllers.Length, which is the player count of the round. A null controller keeps
        /// its player's heading. Throws ArgumentException if HeadGrace &lt;= PawnSpeed * Dt (section 3.1).
        /// Traits (docs/BIOME_TRAITS.md section 4): the config traits of Config.Traits are applied to the CLONED config
        /// (TraitRegistry.ApplyConfig), then the behaviour traits are created (TraitRegistry.CreateBehaviours) and
        /// attached; with a speed trait the HeadGrace check uses PawnSpeed x the largest factor it can return.
        /// </summary>
        public Simulation(SimConfig config, IController[] controllers, SimSetup setup = null)
        {
            if (config == null) throw new ArgumentNullException(nameof(config));
            if (controllers == null) throw new ArgumentNullException(nameof(controllers));
            if (config.TickRate <= 0) throw new ArgumentException("TickRate must be > 0", nameof(config));
            if (!(config.HeadGrace > config.PawnSpeed * config.Dt))
                throw new ArgumentException("HeadGrace (" + config.HeadGrace + ") must exceed PawnSpeed * Dt ("
                                            + config.PawnSpeed * config.Dt + "): the segment drawn in one tick must never be exposed", nameof(config));
            if (!(config.RoundDuration > 0.0)) throw new ArgumentException("RoundDuration must be > 0", nameof(config));
            if (!(config.EventEpsilonSeconds >= 0.0)) throw new ArgumentException("EventEpsilonSeconds must be >= 0", nameof(config));

            int n = controllers.Length;
            if (n < 1) throw new ArgumentException("at least one controller (player) is required", nameof(controllers));
            if (n > 254) throw new ArgumentException("at most 254 players (grid owner ids)", nameof(controllers));
            if (setup != null && setup.StartPositions != null && setup.StartPositions.Length < n)
                throw new ArgumentException("SimSetup.StartPositions is shorter than the player count", nameof(setup));
            if ((setup == null || setup.StartPositions == null) && n > 4)
                throw new ArgumentException("default start positions exist for 4 players only", nameof(controllers));
            if (setup != null && setup.StartHeadings != null && setup.StartHeadings.Length < n)
                throw new ArgumentException("SimSetup.StartHeadings is shorter than the player count", nameof(setup));

            Config = config.Clone();
            Config.PlayerCount = n;
            TraitRegistry.ApplyConfig(Config.Traits, Config);
            this.setup = setup;
            Controllers = (IController[])controllers.Clone();
            Arena = new Arena(Config.ArenaHalfSize, Config.ArenaCornerRadius, Config.ArenaMargin, Config.ArenaBoundary);
            Grid = new OwnerGrid(Arena, Config.CellSize);
            EndTick = (long)Math.Ceiling(Config.RoundDuration * Config.TickRate - 1e-9);
            NextRingTime = Config.LassoFirstSpawn;
            HumanIndex = setup != null ? setup.HumanIndex : 0;
            ForcedRingPos = setup != null ? setup.ForcedRingPos : null;

            players = new PlayerState[n];
            EliminatedRank = new int[n];
            double d = Config.StartDiscOffset;
            for (int i = 0; i < n; i++)
            {
                Vec2d start;
                if (setup != null && setup.StartPositions != null) start = setup.StartPositions[i];
                else start = DefaultStart(i, d);

                double heading;
                if (setup != null && setup.StartHeadings != null) heading = setup.StartHeadings[i];
                else heading = (start.LengthSq > 0.0) ? (-start).Angle() : 0.0;   // R2: toward the arena center

                string name = (setup != null && setup.Names != null && i < setup.Names.Length && setup.Names[i] != null)
                    ? setup.Names[i] : "P" + (i + 1);

                players[i] = new PlayerState
                {
                    Index = i,
                    Id = (byte)(i + 1),
                    Name = name,
                    IsHuman = i == HumanIndex,
                    Pos = start,
                    PrevPos = start,
                    Heading = heading,
                    DesiredHeading = heading,
                    Pocket = new CellMask(Grid.Size),
                };
            }
            Players = Array.AsReadOnly(players);

            // R2 territory: discs at the start positions unless the setup fills the grid itself.
            if (setup != null && setup.Territory != null) setup.Territory(Grid);
            else for (int i = 0; i < n; i++) Grid.FillDisc(players[i].Pos, Config.StartDiscRadius, players[i].Id);

            // R5: the current cell comes from the start position once; afterwards only section 6 changes it. A player
            // whose start cell is not its own (custom setups only) starts trailing from its head, so the state is
            // consistent (Home == owner(Cell) == Id) from the first frame.
            for (int i = 0; i < n; i++)
            {
                PlayerState p = players[i];
                if (!Grid.TryCellOf(p.Pos, out int ci, out int cj))
                    throw new ArgumentException("start position of player " + i + " is outside the grid: " + p.Pos, nameof(setup));
                p.Cell = Grid.Index(ci, cj);
                p.Home = Grid.Cells[p.Cell] == p.Id;
                if (!p.Home) p.Trail.Start(p.Pos);
            }

            View = new SimView(this);

            // Behaviour traits, attached once the grid and the players exist.
            traitsActive = !Config.Traits.IsClassic;
            traitKey = traitsActive ? Config.Traits.ToKey() : "";
            Behaviours = TraitRegistry.CreateBehaviours(Config.Traits).ToArray();
            // HeadGrace check (docs/BIOME_TRAITS.md 7.1): the maximum REACHABLE speed factor. Factors multiply (PawnSpeed x
            // SpeedMultiplier x Conduction), so the largest reachable one is the product of every speed trait's maximum
            // (each >= 1); with a single speed trait this is that trait's maximum, as before.
            double maxFactor = 1.0;
            var kills = new List<IKillTrait>();
            for (int b = 0; b < Behaviours.Length; b++)
            {
                Behaviours[b].Attach(this, Config.Traits.Get(Behaviours[b].Id));
                if (Behaviours[b] is ISpeedTrait speed && speed.MaxSpeedFactor > 1.0) maxFactor *= speed.MaxSpeedFactor;
                if (Behaviours[b] is IKillTrait kill) kills.Add(kill);
            }
            MaxSpeedFactor = maxFactor;
            KillTraits = kills.ToArray();
            if (maxFactor > 1.0 && !(Config.HeadGrace > Config.PawnSpeed * maxFactor * Config.Dt))
                throw new ArgumentException("HeadGrace (" + Config.HeadGrace + ") must exceed PawnSpeed x max trait speed factor x Dt ("
                                            + Config.PawnSpeed * maxFactor * Config.Dt + ", traits " + traitKey
                                            + "): the segment drawn in one tick must never be exposed", nameof(config));

            resolver = new EventResolver(this);
            ringSpawner = new RingSpawner(Config.Seed);
        }

        public SimConfig Config { get; }
        public Arena Arena { get; }
        public OwnerGrid Grid { get; }
        public IReadOnlyList<PlayerState> Players { get; }
        public long Tick { get; private set; }

        /// <summary>(long)Math.Ceiling(RoundDuration * TickRate - 1e-9).</summary>
        public long EndTick { get; }

        /// <summary>Tick / (double)TickRate (never accumulated); RoundDuration after the last tick.</summary>
        public double Time => Tick >= EndTick ? Config.RoundDuration : Tick / (double)Config.TickRate;

        public bool Ended { get; private set; }
        public RoundResult Result { get; private set; }
        public Ring Ring { get; internal set; }
        public double NextRingTime { get; internal set; }

        /// <summary>Events of the last Step, in resolution order.</summary>
        public IReadOnlyList<SimEvent> LastEvents => lastEvents;

        /// <summary>Times the event loop hit MaxEventsPerTick (tests assert 0).</summary>
        public int EventCapHits { get; internal set; }

        public SimView View { get; }

        // Internal plumbing for EventResolver and RingSpawner.
        internal IController[] Controllers { get; }
        internal PlayerState[] PlayerArray => players;
        internal int HumanIndex { get; }
        internal Vec2d? ForcedRingPos { get; }

        // ------------------------------------------------------------------------------------------------------------
        // Trait plumbing (docs/BIOME_TRAITS.md sections 4 and 6). Internal: traits live in this assembly.

        /// <summary>The attached behaviour traits in TraitId order (empty in classic rounds).</summary>
        internal ISimTrait[] Behaviours { get; }

        /// <summary>
        /// The largest reachable speed factor: the product of the speed traits' MaxSpeedFactor (1 without speed traits;
        /// HeadGrace check, docs/BIOME_TRAITS.md 7.1).
        /// </summary>
        internal double MaxSpeedFactor { get; }

        /// <summary>The attached kill traits (IKillTrait) in TraitId order (empty in classic rounds and without kill traits).</summary>
        internal IKillTrait[] KillTraits { get; }

        /// <summary>
        /// docs/BIOME_TRAITS.md section 7, after step b of a group: every kill trait for every kill (killer alive), in kill
        /// order then TraitId order; the events each call raises are emitted right after it.
        /// </summary>
        internal void NotifyKills(List<KillInfo> kills)
        {
            for (int k = 0; k < kills.Count; k++)
            {
                for (int t = 0; t < KillTraits.Length; t++)
                {
                    traitEvents.Clear();
                    KillTraits[t].OnKill(this, kills[k], traitEvents);
                    for (int e = 0; e < traitEvents.Count; e++) Emit(traitEvents[e]);
                }
            }
            traitEvents.Clear();
        }

        /// <summary>The ScorchedEarth trait when attached (it registers itself), else null.</summary>
        internal ScorchedEarthTrait Scorch { get; set; }

        /// <summary>Start time of the current (or last) Step: Time before the tick advanced.</summary>
        internal double TickStartTime { get; private set; }

        /// <summary>The clock of the trait hooks: the group time while a group is applied (step a hooks), else Time.</summary>
        internal double TraitTime
        {
            get => double.IsNaN(traitTime) ? Time : traitTime;
            set => traitTime = value;
        }

        /// <summary>Scorched at 'time' (ScorchedEarth): neutral and time &lt; its scorch end. False without the trait.</summary>
        internal bool IsScorchedAt(int cell, double time)
        {
            return Scorch != null && Scorch.IsScorched(cell, time);
        }

        /// <summary>Section 6 step 1: the product of the behaviours' SpeedFactor for p (1 when classic).</summary>
        internal double SpeedFactorOf(PlayerState p)
        {
            double f = 1.0;
            for (int b = 0; b < Behaviours.Length; b++) f *= Behaviours[b].SpeedFactor(this, p);
            return f;
        }

        /// <summary>Section 6 step a: lets every behaviour add cells to an unchased capture; ascending and distinct result.</summary>
        internal int[] AugmentCapture(PlayerState p, int[] cells)
        {
            captureScratch.Clear();
            captureScratch.AddRange(cells);
            for (int b = 0; b < Behaviours.Length; b++) Behaviours[b].AugmentCapture(this, p, captureScratch);
            if (captureScratch.Count == cells.Length) return cells;
            captureScratch.Sort();
            int w = 0;
            for (int r = 0; r < captureScratch.Count; r++)
            {
                if (w > 0 && captureScratch[w - 1] == captureScratch[r]) continue;
                captureScratch[w++] = captureScratch[r];
            }
            var result = new int[w];
            captureScratch.CopyTo(0, result, 0, w);
            return result;
        }

        /// <summary>After an elimination neutralized its cells (freed ascending), at group time t.</summary>
        internal void NotifyEliminated(PlayerState p, int[] freed, double t)
        {
            for (int b = 0; b < Behaviours.Length; b++) Behaviours[b].OnEliminated(this, p, freed, t);
        }

        /// <summary>Section 6 step 3 trait hook (Time = tick end), then the events they raised, in order.</summary>
        private void RunEndOfTickTraits()
        {
            traitTime = double.NaN;
            traitEvents.Clear();
            for (int b = 0; b < Behaviours.Length; b++) Behaviours[b].EndOfTick(this, traitEvents);
            for (int e = 0; e < traitEvents.Count; e++) Emit(traitEvents[e]);
            traitEvents.Clear();
        }

        /// <summary>One tick (section 6 steps 0-3); no-op when Ended.</summary>
        public void Step()
        {
            if (Ended) return;
            lastEvents.Clear();

            // Step 0. Handlers may call the Debug* hooks; everything below reads the state after them.
            BeforeTick?.Invoke(this);
            if (Ended) return;

            long k = Tick;
            double t0 = Time;
            TickStartTime = t0;
            double uEnd = 1.0;
            bool lastTick = k >= EndTick - 1;
            if (lastTick)
            {
                double x = Config.RoundDuration * Config.TickRate - k;
                uEnd = (x > 1.0 - 1e-9) ? 1.0 : x;
            }

            // Steps 1 and 2.
            resolver.BeginTick(t0, uEnd, lastTick);
            double uStop = resolver.RunEventLoop();

            // Step 3 (uStop = uEnd unless the round ended inside the tick, then the state freezes at that instant).
            resolver.EndTick(uStop);
            Tick = k + 1;
            if (!Ended)
            {
                // Trait hook of step 3: after the trail appends, positions and sparks, before the ring spawner.
                if (Behaviours.Length > 0) RunEndOfTickTraits();
                ringSpawner.Run(this);
                if (Tick >= EndTick && !Ended)
                {
                    // Defensive: TimeUp is a candidate of the last tick, so the round has ended by now.
                    EndRound(RoundEndReason.TimeUp, Config.RoundDuration);
                }
            }
        }

        /// <summary>R20: owned cells / arena (non-void) cells * 100 (current ownership; 0 for an eliminated player).</summary>
        public double AreaPercent(int playerIndex)
        {
            CheckPlayer(playerIndex);
            int arena = Grid.ArenaCellCount;
            return arena > 0 ? 100.0 * Grid.CountOf(players[playerIndex].Id) / arena : 0.0;
        }

        /// <summary>
        /// R19 competition rank. Eliminated: 1 + players alive after its event group (final once its Step returned).
        /// Alive: Result.Ranks once Ended, else 1 + alive players with strictly more cells (provisional).
        /// </summary>
        public int RankOf(int playerIndex)
        {
            CheckPlayer(playerIndex);
            if (Ended && Result != null) return Result.Ranks[playerIndex];
            PlayerState p = players[playerIndex];
            if (!p.Alive) return EliminatedRank[playerIndex];
            int mine = Grid.CountOf(p.Id);
            int rank = 1;
            for (int i = 0; i < players.Length; i++)
            {
                if (i != playerIndex && players[i].Alive && Grid.CountOf(players[i].Id) > mine) rank++;
            }
            return rank;
        }

        /// <summary>
        /// FNV-1a (64 bit) over Tick, grid cells, and per player: position rounded to 1e-9, Cell, flags (Alive, Home,
        /// Charged), heading rounded to 1e-9, trail points rounded to 1e-9, spark S rounded to 1e-9, pocket count;
        /// then the ring position. Only when at least one trait is enabled (classic hash unchanged): the trait key, then
        /// the scorch state (end time rounded to 1e-9 and cell count of every scorch still running). Only when a kill
        /// trait is attached (docs/BIOME_TRAITS.md 7.1, so the D-1 trait sets keep their hashes): per player the
        /// SpeedMultiplier, ExitWasCut, ShieldEnd and Spark.Speed (rounded to 1e-9).
        /// </summary>
        public ulong StateHash()
        {
            ulong h = 14695981039346656037UL;
            h = HashLong(h, Tick);
            byte[] cells = Grid.Cells;
            for (int c = 0; c < cells.Length; c++) h = HashByte(h, cells[c]);
            for (int i = 0; i < players.Length; i++)
            {
                PlayerState p = players[i];
                h = HashVec(h, p.Pos);
                h = HashLong(h, p.Cell);
                h = HashByte(h, (byte)((p.Alive ? 1 : 0) | (p.Home ? 2 : 0) | (p.Charged ? 4 : 0) | (p.Spark != null ? 8 : 0)));
                h = HashLong(h, Round9(p.Heading));
                IReadOnlyList<Vec2d> pts = p.Trail.Points;
                int count = p.Trail.Count;
                h = HashLong(h, count);
                for (int k = 0; k < count; k++) h = HashVec(h, pts[k]);
                if (p.Spark != null) h = HashLong(h, Round9(p.Spark.S));
                h = HashLong(h, p.Pocket.Count);
            }
            if (Ring != null) h = HashVec(h, Ring.Pos);
            if (traitsActive)
            {
                h = HashLong(h, traitKey.Length);
                for (int c = 0; c < traitKey.Length; c++) h = HashLong(h, traitKey[c]);
                if (Scorch != null)
                {
                    Scorch.CopyActive(Time, scorchScratch);
                    h = HashLong(h, scorchScratch.Count);
                    for (int k = 0; k < scorchScratch.Count; k++)
                    {
                        h = HashLong(h, Round9(scorchScratch[k].Until));
                        h = HashLong(h, scorchScratch[k].Count);
                    }
                }
                if (KillTraits.Length > 0)
                {
                    for (int i = 0; i < players.Length; i++)
                    {
                        PlayerState p = players[i];
                        h = HashLong(h, Round9(p.SpeedMultiplier));
                        h = HashByte(h, (byte)(p.ExitWasCut ? 1 : 0));
                        h = HashLong(h, Round9(p.ShieldEnd));
                        if (p.Spark != null) h = HashLong(h, Round9(p.Spark.Speed));
                    }
                }
            }
            return h;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Test and probe hooks (test-only). They do not raise events.

        /// <summary>
        /// Contract 10.0 item 4: the player becomes trailing with this trail (at least 2 points). Heading =
        /// DesiredHeading = direction of the last segment, Pos = PrevPos = last point, Cell = TryCellOf(head) (throws
        /// InvalidOperationException if that cell is owned by the player), Home = false. Any spark and pocket are cleared
        /// (and ExitWasCut: this is a new exit). SpeedMultiplier and the shield are kept.
        /// </summary>
        public void DebugSetTrail(int player, IReadOnlyList<Vec2d> points)
        {
            CheckPlayer(player);
            if (points == null || points.Count < 2) throw new ArgumentException("a trail needs at least 2 points", nameof(points));
            PlayerState p = players[player];
            if (!p.Alive) throw new InvalidOperationException("player " + player + " is eliminated");
            Vec2d head = points[points.Count - 1];
            if (!Grid.TryCellOf(head, out int ci, out int cj)) throw new ArgumentException("trail head outside the grid", nameof(points));
            int cell = Grid.Index(ci, cj);
            if (Grid.Cells[cell] == p.Id)
                throw new InvalidOperationException("DebugSetTrail: the head cell of player " + player + " is its own territory");

            p.Trail.Start(points[0]);
            for (int k = 1; k < points.Count; k++) p.Trail.Append(points[k]);
            Vec2d dir = head - points[points.Count - 2];
            double heading = dir.LengthSq > 0.0 ? dir.Angle() : p.Heading;
            p.Heading = heading;
            p.DesiredHeading = heading;
            p.Pos = head;
            p.PrevPos = head;
            p.Cell = cell;
            p.Home = false;
            p.Spark = null;
            p.ExitWasCut = false;
            p.Pocket.Clear();
        }

        /// <summary>
        /// Spawns a spark now on the victim's trail as if cut: Spark { SCut = sCut, TimeCut = Time, Attacker, S = PrevS =
        /// sCut, Speed = Config.SparkSpeedOf(victim.SpeedMultiplier) }, ExitWasCut = true, attacker CutsMade++ (attacker may
        /// be -1: nobody is credited). No-op if the victim already has a spark, is home, is eliminated or is shielded
        /// (KillShield). sCut &gt;= L gives a catch at the next tick start.
        /// </summary>
        public void DebugForceCut(int victim, double sCut, int attacker)
        {
            CheckPlayer(victim);
            PlayerState v = players[victim];
            if (v.Spark != null || !v.Alive || v.Home || v.Shielded) return;
            v.Spark = new Spark
            {
                SCut = sCut, TimeCut = Time, Attacker = attacker, S = sCut, PrevS = sCut, Speed = Config.SparkSpeedOf(v.SpeedMultiplier),
                ExitWasCutBefore = v.ExitWasCut,
            };
            v.ExitWasCut = true;
            if (attacker >= 0 && attacker < players.Length) players[attacker].CutsMade++;
        }

        public void DebugSetCharged(int player, bool charged)
        {
            CheckPlayer(player);
            players[player].Charged = charged;
        }

        /// <summary>Places (or moves) the ring at pos now, SpawnTime = Time.</summary>
        public void DebugPlaceRing(Vec2d pos)
        {
            Ring = new Ring { Pos = pos, SpawnTime = Time };
        }

        // ------------------------------------------------------------------------------------------------------------
        // Internal helpers.

        internal void Emit(SimEvent e)
        {
            lastEvents.Add(e);
            EventRaised?.Invoke(e);
        }

        /// <summary>R19 round end at group time t: final ranks, FinalCells of the alive players, RoundEnded.</summary>
        internal void EndRound(RoundEndReason reason, double t)
        {
            if (Ended) return;
            int n = players.Length;
            var result = new RoundResult
            {
                Reason = reason,
                EndTime = reason == RoundEndReason.TimeUp ? Config.RoundDuration : t,
                Ranks = new int[n],
                FinalCells = new int[n],
                FinalAreaPercent = new double[n],
                Winners = new List<int>(),
            };
            for (int i = 0; i < n; i++)
            {
                PlayerState p = players[i];
                if (p.Alive)
                {
                    p.FinalCells = Grid.CountOf(p.Id);
                    int rank = 1;
                    for (int j = 0; j < n; j++)
                    {
                        if (j != i && players[j].Alive && Grid.CountOf(players[j].Id) > p.FinalCells) rank++;
                    }
                    result.Ranks[i] = rank;
                }
                else
                {
                    result.Ranks[i] = EliminatedRank[i];
                }
            }
            int arena = Grid.ArenaCellCount;
            for (int i = 0; i < n; i++)
            {
                result.FinalCells[i] = players[i].FinalCells;
                result.FinalAreaPercent[i] = arena > 0 ? 100.0 * players[i].FinalCells / arena : 0.0;
                if (result.Ranks[i] == 1) result.Winners.Add(i);
            }
            Result = result;
            Ended = true;
            Emit(new SimEvent { Type = SimEventType.RoundEnded, Time = t });
        }

        private static Vec2d DefaultStart(int i, double d)
        {
            // R2 / Tuning.StartDiscOffset: (-d,-d), (d,-d), (d,d), (-d,d) for players 0..3.
            switch (i)
            {
                case 0: return new Vec2d(-d, -d);
                case 1: return new Vec2d(d, -d);
                case 2: return new Vec2d(d, d);
                default: return new Vec2d(-d, d);
            }
        }

        private void CheckPlayer(int index)
        {
            if ((uint)index >= (uint)players.Length)
                throw new ArgumentOutOfRangeException(nameof(index), index, "player index outside [0, PlayerCount)");
        }

        private static long Round9(double v)
        {
            if (double.IsNaN(v)) return long.MinValue;
            double r = Math.Round(v * 1e9);
            if (r >= 9.2e18) return long.MaxValue;
            if (r <= -9.2e18) return long.MinValue + 1;
            return (long)r;
        }

        private static ulong HashVec(ulong h, Vec2d v)
        {
            h = HashLong(h, Round9(v.X));
            return HashLong(h, Round9(v.Y));
        }

        private static ulong HashLong(ulong h, long v)
        {
            ulong u = unchecked((ulong)v);
            for (int b = 0; b < 8; b++)
            {
                h = HashByte(h, (byte)(u & 0xFF));
                u >>= 8;
            }
            return h;
        }

        private static ulong HashByte(ulong h, byte b)
        {
            unchecked
            {
                h ^= b;
                h *= 1099511628211UL;
            }
            return h;
        }
    }
}
