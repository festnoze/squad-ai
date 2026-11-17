using System.Collections.Generic;
using UnityEngine;

namespace Meuble.Core
{
    /// <summary>
    /// Plans a walk for an inhabitant (docs/CONTRACT_M2.md 3.4). Fills <paramref name="corners"/> with the
    /// polyline after <paramref name="from"/>, ending at <paramref name="to"/> (or at the closest reachable
    /// point), and returns false when there is no path at all.
    /// </summary>
    public interface IPathPlanner
    {
        bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners);
    }

    /// <summary>The M1 behavior: a single straight segment.</summary>
    public sealed class StraightPlanner : IPathPlanner
    {
        public static readonly StraightPlanner Instance = new StraightPlanner();

        public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners)
        {
            corners.Clear();
            corners.Add(YawMath.Planar(to));
            return true;
        }
    }
}
