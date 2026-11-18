using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>
    /// Dollhouse view through shared walls (docs/CONTRACT_M2.md 6). An outer wall has a single inward face,
    /// so the orbit camera outside the house sees through its back (PRD 3.1). An interior wall has two
    /// faces, and from the next room the camera would look at the near one. Every frame, after the camera
    /// moved, each registered face whose plane separates the camera from the player furniture is hidden.
    /// Renderer only: the collider stays, so the wall still blocks sight, the chair and the NavMesh. The
    /// face keeps casting its shadow, so the lighting does not change when the camera moves.
    /// M5 wave 5A.1 (critique m15): an entry may also carry a box (a transform and its size, read at its current pose every
    /// frame), and then also hides while a sight line from the camera to the player furniture crosses that box (grown by
    /// Tuning.LeafFadeMargin). A door leaf uses it: open in the player's room, it never hides the furniture.
    /// </summary>
    [DefaultExecutionOrder(300)] // after OrbitCamera (200), which moves in LateUpdate
    public sealed class WallFader : MonoBehaviour
    {
        private struct Entry
        {
            public Renderer Renderer;
            public Vector3 Point;
            public Vector3 Normal;
            public ShadowCastingMode Shown;
            /// <summary>M5: the box whose current pose also hides the renderer (null: the plane rule only).</summary>
            public Transform Box;
            public Vector3 HalfSize;
        }

        /// <summary>The player furniture: the faces between it and the camera are hidden.</summary>
        public Transform Target;

        /// <summary>
        /// M5: the player furniture whose sight points (its centre and top corners, as the probe's start view) end the sight
        /// lines of the box rule; null: the target's position only.
        /// </summary>
        public FurnitureController Furniture;

        private readonly Vector3[] points = new Vector3[Tuning.SampleCount];

        /// <summary>The camera to clear the view for; the main camera when null.</summary>
        public Camera View;

        private readonly List<Entry> entries = new List<Entry>();

        public int Count => entries.Count;

        /// <summary>
        /// Wave 5B (tests): the fade plane a renderer is registered with (its first entry); false when it never fades.
        /// </summary>
        public bool PlaneOf(Renderer renderer, out Vector3 point, out Vector3 normal)
        {
            foreach (Entry e in entries)
            {
                if (e.Renderer == renderer)
                {
                    point = e.Point;
                    normal = e.Normal;
                    return true;
                }
            }
            point = default;
            normal = default;
            return false;
        }

        /// <summary>Number of faces hidden on the last update (probe and tests).</summary>
        public int HiddenCount { get; private set; }

        /// <summary>Registers a renderer that hides when the plane (point, normal) separates camera and target.</summary>
        public void Add(Renderer renderer, Vector3 point, Vector3 normal)
        {
            if (renderer == null)
            {
                return;
            }
            entries.Add(new Entry { Renderer = renderer, Point = point, Normal = normal.normalized, Shown = renderer.shadowCastingMode });
        }

        /// <summary>
        /// M5: registers a renderer that hides when the plane (point, normal) separates camera and target, or when a sight
        /// line from the camera to the player furniture crosses the box of <paramref name="box"/> (centred on it, at its
        /// current pose, <paramref name="size"/> in its local axes).
        /// </summary>
        public void Add(Renderer renderer, Vector3 point, Vector3 normal, Transform box, Vector3 size)
        {
            if (renderer == null)
            {
                return;
            }
            Vector3 half = size * 0.5f + Vector3.one * Tuning.LeafFadeMargin;
            entries.Add(new Entry
            {
                Renderer = renderer, Point = point, Normal = normal.normalized, Shown = renderer.shadowCastingMode, Box = box, HalfSize = half,
            });
        }

        /// <summary>Applies the rule for a camera position (also callable from tests and tools).</summary>
        public void Apply(Vector3 camera)
        {
            HiddenCount = 0;
            if (Target == null)
            {
                return;
            }
            Vector3 player = Target.position;
            int count = 1;
            if (Furniture != null)
            {
                Furniture.GetSamplePoints(points);
                count = points.Length;
            }
            else
            {
                points[0] = player;
            }
            for (int i = 0; i < entries.Count; i++)
            {
                Entry e = entries[i];
                if (e.Renderer == null)
                {
                    continue;
                }
                bool hidden = Vector3.Dot(camera - e.Point, e.Normal) * Vector3.Dot(player - e.Point, e.Normal) < 0f;
                if (!hidden && e.Box != null)
                {
                    bool crossed = CrossesBox(camera, points, count, e.Box, e.HalfSize); // MUTATION:LEAF_FADE
                    hidden = crossed;
                }
                ShadowCastingMode mode = hidden ? ShadowCastingMode.ShadowsOnly : e.Shown;
                if (e.Renderer.shadowCastingMode != mode)
                {
                    e.Renderer.shadowCastingMode = mode;
                }
                if (hidden)
                {
                    HiddenCount++;
                }
            }
        }

        /// <summary>True when a segment from <paramref name="from"/> to one of the first <paramref name="count"/> points crosses the box.</summary>
        private static bool CrossesBox(Vector3 from, Vector3[] to, int count, Transform box, Vector3 half)
        {
            Quaternion inverse = Quaternion.Inverse(box.rotation);
            Vector3 origin = inverse * (from - box.position);
            for (int i = 0; i < count; i++)
            {
                if (SegmentHitsBox(origin, inverse * (to[i] - from), half))
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>
        /// Slab test: the segment origin + t * delta, t in [0, 1], meets the axis aligned box of half sizes
        /// <paramref name="half"/> centred on the origin of the local frame.
        /// </summary>
        public static bool SegmentHitsBox(Vector3 origin, Vector3 delta, Vector3 half)
        {
            float enter = 0f;
            float exit = 1f;
            for (int k = 0; k < 3; k++)
            {
                float o = origin[k];
                float d = delta[k];
                float h = half[k];
                if (Mathf.Abs(d) < 1e-8f)
                {
                    if (o < -h || o > h)
                    {
                        return false;
                    }
                    continue;
                }
                float a = (-h - o) / d;
                float b = (h - o) / d;
                if (a > b)
                {
                    (a, b) = (b, a);
                }
                enter = Mathf.Max(enter, a);
                exit = Mathf.Min(exit, b);
                if (enter > exit)
                {
                    return false;
                }
            }
            return true;
        }

        private void LateUpdate()
        {
            if (entries.Count == 0)
            {
                return;
            }
            Camera cam = View != null ? View : Camera.main;
            if (cam != null)
            {
                Apply(cam.transform.position);
            }
        }
    }
}
