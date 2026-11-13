using System.Collections.Generic;
using Meuble.Core;
using UnityEngine;
using UnityEngine.AI;

namespace Meuble
{
    /// <summary>
    /// Path planner over the runtime NavMesh of one level (docs/CONTRACT_M2.md 6). Works in play mode and
    /// in edit mode (the level audit plans with it). Only complete paths are accepted; the corners after
    /// the start are returned on the floor plane, and the last corner is exactly the requested target.
    ///
    /// The NavMesh data of the last level built is cached by a key (the level data itself): a restart of
    /// the same level adds the cached data again instead of rebuilding it.
    /// </summary>
    public sealed class NavPlanner : IPathPlanner
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

        /// <summary>
        /// Builds the NavMesh of a level from the physics colliders under <paramref name="root"/> on the
        /// Occluder, Floor and Furniture layers, clipped to <paramref name="bounds"/>, and adds it. With a
        /// <paramref name="cacheKey"/> equal to the previous build's, the previous data is reused.
        /// </summary>
        public static NavPlanner Build(Transform root, Bounds bounds, string cacheKey = null)
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
            corners.Clear();
            if (!NavMesh.SamplePosition(from, out NavMeshHit start, Tuning.NavSnapDistance, filter)
                || !NavMesh.SamplePosition(to, out NavMeshHit end, Tuning.NavSnapDistance, filter))
            {
                return false;
            }
            if (!NavMesh.CalculatePath(start.position, end.position, filter, path) || path.status != NavMeshPathStatus.PathComplete)
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
            return NavMesh.SamplePosition(point, out _, Tuning.NavSnapDistance, filter);
        }
    }
}
