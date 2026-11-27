// Written by A1 as a complete data type (contract 5.5), owned by A4.
using System;

namespace PainterIO.Core
{
    /// <summary>Optional overrides of a round's start (tests, probe, attract mode).</summary>
    public sealed class SimSetup
    {
        public int PlayerCount = Tuning.PlayerCount;
        public Vec2d[] StartPositions;                // null => R2 defaults
        public double[] StartHeadings;                // null => toward center
        public Action<OwnerGrid> Territory;           // null => R2 discs; otherwise fills the grid itself
        public string[] Names;
        public int HumanIndex = 0;                    // -1 => all bots (attract mode)
        public Vec2d? ForcedRingPos;                  // when set, RingSpawner uses it instead of a random cell (probe, tests)
    }
}
