using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Meuble
{
    /// <summary>
    /// Dollhouse view through shared walls (docs/CONTRACT_M2.md 6). An outer wall has a single inward face,
    /// so the orbit camera outside the house sees through its back (PRD 3.1). An interior wall has two
    /// faces, and from the next room the camera would look at the near one. Every frame, after the camera
    /// moved, each registered face whose plane separates the camera from the player furniture is hidden.
    /// Renderer only: the collider stays, so the wall still blocks sight, the chair and the NavMesh. The
    /// face keeps casting its shadow, so the lighting does not change when the camera moves.
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
        }

        /// <summary>The player furniture: the faces between it and the camera are hidden.</summary>
        public Transform Target;

        /// <summary>The camera to clear the view for; the main camera when null.</summary>
        public Camera View;

        private readonly List<Entry> entries = new List<Entry>();

        public int Count => entries.Count;

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

        /// <summary>Applies the rule for a camera position (also callable from tests and tools).</summary>
        public void Apply(Vector3 camera)
        {
            HiddenCount = 0;
            if (Target == null)
            {
                return;
            }
            Vector3 player = Target.position;
            for (int i = 0; i < entries.Count; i++)
            {
                Entry e = entries[i];
                if (e.Renderer == null)
                {
                    continue;
                }
                bool hidden = Vector3.Dot(camera - e.Point, e.Normal) * Vector3.Dot(player - e.Point, e.Normal) < 0f;
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
