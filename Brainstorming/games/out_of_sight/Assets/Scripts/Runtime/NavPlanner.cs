using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.AI;

namespace OutOfSight
{
    /// <summary>
    /// Path planner over the runtime NavMesh of one level (docs/CONTRACT_M2.md 6). Works in play mode and
    /// in edit mode (the level audit plans with it). Only complete paths are accepted; the corners after
    /// the start are returned on the floor plane, and the last corner is exactly the requested target.
    ///
    /// The NavMesh data of the last level built is cached by a key (the level data itself): a restart of
    /// the same level adds the cached data again instead of rebuilding it.
    ///
    /// M5 (docs/CONTRACT_M5_v3.md 15.1 and 15.4): one NavMeshData per level, never rebuilt for a door. The level builder
    /// adds a NavMesh area box per leaf doorway (area Tuning.DoorAreaBase + leaf index) and a Not Walkable box per open
    /// leaf pose as extra sources; a plan restricted to an area mask leaves the closed leaves' doorways out
    /// (<see cref="IAreaMaskPlanner"/>). On a level with platforms or ramps, the ends of a plan are sampled from
    /// <see cref="Floor"/>'s height + 0.5 m, so a point on a platform snaps to the platform top and never to the floor
    /// under it; a flat level samples from the given points exactly as in M2 to M4.
    /// </summary>
    public sealed class NavPlanner : IAreaMaskPlanner
    {
        private const int AgentTypeId = 0;

        private static string cachedKey;
        private static NavMeshData cachedData;

        private readonly NavMeshPath path = new NavMeshPath();
        private readonly NavMeshQueryFilter filter = new NavMeshQueryFilter { agentTypeID = AgentTypeId, areaMask = NavMesh.AllAreas };
        private Vector3[] buffer = new Vector3[32];
        private NavMeshData data;
        private NavMeshDataInstance instance;

        /// <summary>True when the data was built and added (a level without a NavMesh plans nothing).</summary>
        public bool HasData => data != null && instance.valid;

        /// <summary>Number of sources the build collected (0 when the data came from the cache).</summary>
        public int SourceCount { get; private set; }

        /// <summary>True when this planner reused the cached data of an identical level.</summary>
        public bool FromCache { get; private set; }

        /// <summary>M5: the level's floor heights (the level builder sets it); flat by default.</summary>
        public FloorMap Floor
        {
            get => floor;
            set => floor = value ?? FloorMap.Flat;
        }

        private FloorMap floor = FloorMap.Flat;

        /// <summary>M5: how far above the floor a plan's ends are sampled on a level with platforms or ramps.</summary>
        public const float SampleLift = 0.5f;

        /// <summary>
        /// Builds the NavMesh of a level from the physics colliders under <paramref name="root"/> on the
        /// Occluder, Floor and Furniture layers, clipped to <paramref name="bounds"/>, and adds it. With a
        /// <paramref name="cacheKey"/> equal to the previous build's, the previous data is reused.
        /// </summary>
        public static NavPlanner Build(Transform root, Bounds bounds, string cacheKey = null)
        {
            return Build(root, bounds, cacheKey, null);
        }

        /// <summary>
        /// M5: <see cref="Build(Transform, Bounds, string)"/> with <paramref name="extraSources"/> added to the collected
        /// colliders (the leaves' NavMesh area and Not Walkable boxes). They are part of the level data, so the cache key
        /// (the level data) still decides alone whether the cached NavMesh is reused.
        /// </summary>
        public static NavPlanner Build(Transform root, Bounds bounds, string cacheKey, IList<NavMeshBuildSource> extraSources)
        {
            var planner = new NavPlanner();
            if (cacheKey != null && cacheKey == cachedKey && cachedData != null)
            {
                planner.data = cachedData;
                planner.instance = NavMesh.AddNavMeshData(cachedData);
                planner.FromCache = true;
                return planner;
            }
            NavMeshBuildSettings settings = NavMesh.GetSettingsByID(AgentTypeId);
            settings.agentRadius = Tuning.NavAgentRadius;
            settings.agentHeight = Tuning.NavAgentHeight;
            settings.agentClimb = Tuning.NavAgentClimb;
            settings.agentSlope = Tuning.NavAgentSlope;
            settings.overrideVoxelSize = true;
            settings.voxelSize = Tuning.NavVoxelSize;
            foreach (string warning in settings.ValidationReport(bounds))
            {
                Debug.LogWarning("[NavPlanner] " + warning);
            }
            var sources = new List<NavMeshBuildSource>();
            NavMeshBuilder.CollectSources(root, Layers.NavMeshSourceMask, NavMeshCollectGeometry.PhysicsColliders, 0,
                new List<NavMeshBuildMarkup>(), sources);
            if (extraSources != null)
            {
                sources.AddRange(extraSources);
            }
            planner.SourceCount = sources.Count;
            planner.data = NavMeshBuilder.BuildNavMeshData(settings, sources, bounds, Vector3.zero, Quaternion.identity);
            if (planner.data == null)
            {
                Debug.LogError("[NavPlanner] BuildNavMeshData returned null");
                return planner;
            }
            planner.data.name = "Level NavMesh";
            planner.instance = NavMesh.AddNavMeshData(planner.data);
            if (cacheKey != null)
            {
                if (cachedData != null)
                {
                    Object.DestroyImmediate(cachedData);
                }
                // Runtime data survives scene loads; never let an asset sweep unload it under the cache.
                planner.data.hideFlags = HideFlags.DontUnloadUnusedAsset;
                cachedData = planner.data;
                cachedKey = cacheKey;
            }
            return planner;
        }

        /// <summary>Forgets the cached data (tools and tests that change a level in place).</summary>
        public static void ClearCache()
        {
            if (cachedData != null)
            {
                Object.DestroyImmediate(cachedData);
            }
            cachedData = null;
            cachedKey = null;
        }

        /// <summary>Triangle count of the NavMesh currently in the world (a full copy: audit and tools only).</summary>
        public static int CountTriangles()
        {
            return NavMesh.CalculateTriangulation().indices.Length / 3;
        }

        /// <summary>Removes the NavMesh from the world, and frees it unless it is the cached one (level teardown).</summary>
        public void Remove()
        {
            if (instance.valid)
            {
                NavMesh.RemoveNavMeshData(instance);
            }
            instance = default;
            if (data != null && data != cachedData)
            {
                Object.DestroyImmediate(data);
            }
            data = null;
        }

        public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners)
        {
            return TryPlan(from, to, corners, NavMesh.AllAreas);
        }

        /// <summary>M5 (docs/CONTRACT_M5_v3.md 15.1): a plan restricted to an area mask (closed leaves excluded).</summary>
        public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners, int areaMask)
        {
            corners.Clear();
            NavMeshQueryFilter masked = filter;
            masked.areaMask = areaMask;
            if (!NavMesh.SamplePosition(Lift(from), out NavMeshHit start, Tuning.NavSnapDistance, masked)
                || !NavMesh.SamplePosition(Lift(to), out NavMeshHit end, Tuning.NavSnapDistance, masked))
            {
                return false;
            }
            if (!NavMesh.CalculatePath(start.position, end.position, masked, path) || path.status != NavMeshPathStatus.PathComplete)
            {
                return false;
            }
            int count = path.GetCornersNonAlloc(buffer);
            while (count >= buffer.Length)
            {
                buffer = new Vector3[buffer.Length * 2];
                count = path.GetCornersNonAlloc(buffer);
            }
            // corners[0] is the (snapped) start point: the polyline is what comes after it.
            for (int i = 1; i < count; i++)
            {
                corners.Add(YawMath.Planar(buffer[i]));
            }
            Vector3 target = YawMath.Planar(to);
            if (corners.Count == 0)
            {
                corners.Add(target);
            }
            else
            {
                corners[corners.Count - 1] = target;
            }
            return true;
        }

        /// <summary>True when a point of the floor lies on (or within the snap distance of) the NavMesh.</summary>
        public bool Covers(Vector3 point)
        {
            return NavMesh.SamplePosition(Lift(point), out _, Tuning.NavSnapDistance, filter);
        }

        /// <summary>M5: <see cref="Covers(Vector3)"/> restricted to an area mask.</summary>
        public bool Covers(Vector3 point, int areaMask)
        {
            NavMeshQueryFilter masked = filter;
            masked.areaMask = areaMask;
            return NavMesh.SamplePosition(Lift(point), out _, Tuning.NavSnapDistance, masked);
        }

        /// <summary>
        /// M5 (CONTRACT_M5_v3 15.4): where a plan end is sampled from: the point itself on a flat level (M2 to M4 exactly),
        /// else its planar position at the floor height + <see cref="SampleLift"/>.
        /// </summary>
        public Vector3 Lift(Vector3 point)
        {
            return floor.IsFlat ? point : new Vector3(point.x, floor.HeightAt(point.x, point.z) + SampleLift, point.z);
        }
    }

    /// <summary>
    /// M5 (docs/CONTRACT_M5_v3.md 15.1): a planner bound to one NavMesh area mask over the level's one NavMesh
    /// (LevelInstance.PlannerFor). Its plain TryPlan uses that mask; the masked overload passes the given mask through.
    /// Without an inner masked planner (a torn down level) it plans straight lines.
    /// </summary>
    public sealed class MaskedPlanner : IAreaMaskPlanner
    {
        public IAreaMaskPlanner Inner { get; }
        public int AreaMask { get; }

        public MaskedPlanner(IAreaMaskPlanner inner, int areaMask)
        {
            Inner = inner;
            AreaMask = areaMask;
        }

        public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners)
        {
            return TryPlan(from, to, corners, AreaMask);
        }

        public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners, int areaMask)
        {
            if (Inner == null)
            {
                return StraightPlanner.Instance.TryPlan(from, to, corners);
            }
            return Inner.TryPlan(from, to, corners, areaMask);
        }
    }
}
