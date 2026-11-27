// Owned by A4 (sim). The ring spawn rule of contract section 6 step 3 (R15).
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// Spawns the lasso ring at the end of a tick when there is none, LassoEnabled is set and Time &gt;= NextRingTime.
    /// SimSetup.ForcedRingPos wins when set. Otherwise up to 200 deterministic random tries (own Rng seeded from the
    /// round seed): a point qualifies when the ring disc lies inside the arena (SignedDistance &lt;= -(ArenaMargin +
    /// RingRadius), so the whole ring is visible and every point of it is reachable by a head), every arena cell within
    /// RingClearance is neutral (GridQueries.IsNeutralDisc) and every live head is at least RingMinHeadDistance away.
    /// With a live human, the first 100 tries sample points 6 to 22 u from the human's head (feel-11). On failure the
    /// spawner retries at the next tick.
    /// </summary>
    internal sealed class RingSpawner
    {
        public const int Tries = 200;
        public const int HumanTries = 100;
        public const double HumanMinDistance = 6.0;
        public const double HumanMaxDistance = 22.0;

        // Decorrelates the ring stream from any other generator seeded with the same round seed.
        private const ulong SeedSalt = 0x52494E475350574EUL;

        private readonly Rng rng;

        public RingSpawner(ulong seed)
        {
            rng = new Rng(seed ^ SeedSalt);
        }

        public void Run(Simulation sim)
        {
            SimConfig cfg = sim.Config;
            if (sim.Ring != null || !cfg.LassoEnabled || sim.Time < sim.NextRingTime) return;
            if (!TryPick(sim, out Vec2d pos)) return;
            double now = sim.Time;
            sim.Ring = new Ring { Pos = pos, SpawnTime = now };
            sim.Emit(new SimEvent { Type = SimEventType.RingSpawned, Time = now, Point = pos });
        }

        private bool TryPick(Simulation sim, out Vec2d pos)
        {
            if (sim.ForcedRingPos.HasValue)
            {
                pos = sim.ForcedRingPos.Value;
                return true;
            }
            SimConfig cfg = sim.Config;
            Arena arena = sim.Arena;
            double inset = cfg.ArenaMargin + cfg.RingRadius;
            double half = arena.HalfSize - inset;
            IReadOnlyList<PlayerState> players = sim.Players;
            PlayerState human = null;
            int hi = sim.HumanIndex;
            if (hi >= 0 && hi < players.Count && players[hi].Alive) human = players[hi];

            for (int k = 0; k < Tries; k++)
            {
                Vec2d p;
                if (human != null && k < HumanTries)
                {
                    double angle = rng.Range(0.0, 2.0 * Math.PI);
                    double radius = rng.Range(HumanMinDistance, HumanMaxDistance);
                    p = human.Pos + Vec2d.FromAngle(angle) * radius;
                }
                else
                {
                    double x = rng.Range(-half, half);
                    double y = rng.Range(-half, half);
                    p = new Vec2d(x, y);
                }
                if (Acceptable(sim, p, inset))
                {
                    pos = p;
                    return true;
                }
            }
            pos = Vec2d.Zero;
            return false;
        }

        private static bool Acceptable(Simulation sim, Vec2d p, double inset)
        {
            SimConfig cfg = sim.Config;
            if (sim.Arena.SignedDistance(p) > -inset) return false;
            IReadOnlyList<PlayerState> players = sim.Players;
            double min = cfg.RingMinHeadDistance;
            for (int i = 0; i < players.Count; i++)
            {
                if (players[i].Alive && Vec2d.Distance(players[i].Pos, p) < min) return false;
            }
            return GridQueries.IsNeutralDisc(sim.Grid, p, cfg.RingClearance);
        }
    }
}
