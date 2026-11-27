// Written by A1 as complete data types (contract 5.5), owned by A4.
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// Why a round ended (R19). Conquest (rule v1.7, contract 31): a player owns the conquest goal (Simulation.ConquestTargetCells,
    /// SimConfig.ConquestShare of the conquerable cells) and wins at once.
    /// </summary>
    public enum RoundEndReason { None = 0, LastSurvivor = 1, AllEliminated = 2, TimeUp = 3, Conquest = 4 }

    /// <summary>Final standings of a round (R19).</summary>
    public sealed class RoundResult
    {
        public RoundEndReason Reason;
        public double EndTime;
        public int[] Ranks;                           // per player index, 1 = first, competition ranking (1, 1, 3)
        public int[] FinalCells;
        public double[] FinalAreaPercent;
        public List<int> Winners;                     // player indices with rank 1
    }
}
