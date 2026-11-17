using System.Collections.Generic;
using UnityEngine;

namespace Meuble.Core
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5_v3.md 15.1): a planner that can restrict its paths to an area mask (the NavMesh areas of the
    /// open leaves). NavPlanner already has the method; declaring the interface lets RoutineFactory plan the frozen
    /// station walks with the authored mask whatever mask the level is in later.
    /// </summary>
    public interface IAreaMaskPlanner : IPathPlanner
    {
        bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners, int areaMask);
    }

    /// <summary>An <see cref="IAreaMaskPlanner"/> bound to one area mask, seen as a plain planner.</summary>
    public sealed class AreaMaskPlanner : IPathPlanner
    {
        public IAreaMaskPlanner Inner { get; }
        public int AreaMask { get; }

        public AreaMaskPlanner(IAreaMaskPlanner inner, int areaMask)
        {
            Inner = inner;
            AreaMask = areaMask;
        }

        public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners)
        {
            return Inner.TryPlan(from, to, corners, AreaMask);
        }
    }

    /// <summary>
    /// M5 (docs/CONTRACT_M5_v3.md 15.6, CONTRACT_M5 16.12): the one place a routine is built, so the game (Inhabitant),
    /// the level audit and the tests set the same fields, in the same order, before the first step.
    /// </summary>
    public static class RoutineFactory
    {
        /// <summary>
        /// M7 (docs/CONTRACT_M7.md 4.1): the personality an inhabitant plays with, a new instance: its row
        /// (<see cref="PersonalityDef.ForInhabitant"/>) under <see cref="DifficultyDef.Current"/>. The one place the
        /// difficulty reaches the watchers' range, angle, hearing and suspicion: every routine (game, audit, tests) gets its
        /// personality here, and the audit's own watcher rows too.
        /// </summary>
        public static PersonalityDef PersonalityOf(InhabitantDef def)
        {
            return DifficultyDef.Current.Apply(PersonalityDef.ForInhabitant(def)); // MUTATION:DIFFICULTY_APPLY
        }

        /// <summary>The area mask that keeps every area (NavMesh.AllAreas).</summary>
        public const int AllAreas = -1;

        /// <summary>
        /// Builds the routine of <paramref name="def"/>:
        /// <list type="bullet">
        /// <item>its personality (<see cref="PersonalityDef.ForInhabitant"/>: a dog kind wins), pattern and seed;</item>
        /// <item>station walks planned by <paramref name="stationPlanner"/>, restricted to
        /// <paramref name="stationAreaMask"/> when the planner is an <see cref="IAreaMaskPlanner"/> and the mask is not
        /// <see cref="AllAreas"/> (otherwise the planner is expected to plan with the authored leaves already), and frozen
        /// at once for every ordered pair the pattern can produce;</item>
        /// <item><paramref name="investigatePlanner"/> (null: the station planner) for every other walk;</item>
        /// <item>the shared <paramref name="seats"/> registry (null: every seat free) and this routine's
        /// <paramref name="owner"/> id in it (the inhabitant index);</item>
        /// <item>the level's floor (<see cref="LevelDef.Floor"/>; flat without a level).</item>
        /// </list>
        /// GameState still sets the M4 hooks (SeatOccupied, CarryForward, SittingEnabled) as before.
        /// </summary>
        public static InhabitantRoutine Create(InhabitantDef def, LevelDef level, IPathPlanner stationPlanner,
            IPathPlanner investigatePlanner, SeatRegistry seats, int owner, int stationAreaMask)
        {
            if (def == null)
            {
                throw new System.ArgumentNullException(nameof(def));
            }
            IPathPlanner station = stationPlanner ?? StraightPlanner.Instance;
            if (stationAreaMask != AllAreas && station is IAreaMaskPlanner masked)
            {
                station = new AreaMaskPlanner(masked, stationAreaMask);
            }
            var routine = new InhabitantRoutine(def.Stations, def.StartStation, station)
            {
                Personality = PersonalityOf(def),
                Pattern = def.Pattern,
                Seed = def.Seed,
                InvestigatePlanner = investigatePlanner,
                Seats = seats,
                SeatOwner = owner,
                Floor = level != null ? level.Floor : FloorMap.Flat,
                StationAreaMask = stationAreaMask,
            };
            routine.FreezeStationWalks();
            return routine;
        }

        /// <summary>
        /// <see cref="Create(InhabitantDef, LevelDef, IPathPlanner, IPathPlanner, SeatRegistry, int, int)"/> with one
        /// planner for everything, no registry and every area: what a level without leaves or seats needs.
        /// </summary>
        public static InhabitantRoutine Create(InhabitantDef def, LevelDef level, IPathPlanner planner)
        {
            return Create(def, level, planner, null, null, 0, AllAreas);
        }
    }
}
