using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// GARDENZOOM (2026-11-25, user request: "upon strong dezoom, enlarge the garden background cylinder so that the camera
    /// remains inside it whatever the de-zoom level is; re-shrink upon re-zoom until the default garden cylinder size defined
    /// by config"). Added to the garden ring by GardenBackdrop.Build; every frame, once the cameras have moved, it scales
    /// the ring (and its sky ceiling, a child) so the game camera always stands inside the closed volume.
    /// <list type="bullet">
    /// <item>Size: the smallest scale, never below 1 (the default ring, GardenBackdrop.RingFor and
    /// Tuning.GardenRingHouseMargin), that holds the camera (GardenBackdrop.ScaleToHold): the radius is max(the default
    /// radius, the camera's horizontal distance from the ring's axis + Tuning.GardenRingCameraMargin) and the ceiling stays
    /// GardenBackdrop.HeadRoom above the camera, the rounded rim included. Every zoom, orbit angle and view pitch.</item>
    /// <item>How: one uniform transform scale about the centre of the ring's foot, which stays at y = -GardenBackdrop.Sink
    /// (the transform rises by Sink x (scale - 1)), so the ring stands on the lawn at every size. No mesh is rebuilt: the
    /// garden picture keeps its aspect (its height grows with the circumference, the three repeats stay), the ceiling's
    /// sky picture still spans its diameter.</item>
    /// <item>Smooth: the scale eases toward its fit (Tuning.GardenRingFitTime) both ways, so a wheel notch does not pop
    /// the ring; but the camera never comes closer than <see cref="MinClearance"/> to the wall or the ceiling: a zoom out
    /// faster than the easing pushes the ring out at once. Zoomed in, the ring lands on exactly scale 1 (the default size,
    /// transform scale one). The first fit after a build lands at once (no growing at level start).</item>
    /// <item>Coverage: the far clip (GardenBackdrop.Ring.FarClip, set by OrbitCamera.SetTarget) and the lawn (LevelBuilder,
    /// 2 x Ring.MaxRadius + 20) hold the largest ring any camera of the level can ask for (Ring.MaxScale: the orbit
    /// camera's space and the spectator's flight box); should a camera ever go further, the far clip is raised here. The
    /// game has no fog (Main: RenderSettings.fog off).</item>
    /// <item>Any camera: it follows Main's camera whoever drives it (the orbit camera, the spectator's free camera, the
    /// title tour, which stays inside the title house: scale 1).</item>
    /// <item>Cost (Android): one LateUpdate of a few float operations; the transform is written only when the scale
    /// changes; no allocation. Play mode only (edit mode tools keep the default ring).</item>
    /// </list>
    /// </summary>
    [DefaultExecutionOrder(280)] // after OrbitCamera (200), TitleCameraTour (250), SpectatorCamera (260): the camera has moved
    public sealed class GardenBackdropFit : MonoBehaviour
    {
        /// <summary>
        /// The least room, in metres, between the camera and the ring's wall or ceiling while the ring eases: closer, the
        /// ring is pushed out at once (the near plane is 0.05 m).
        /// </summary>
        public const float MinClearance = 0.3f;

        /// <summary>Below this distance from its fit (in scale) the easing lands on the fit exactly.</summary>
        public const float LandEpsilon = 1e-4f;

        /// <summary>The ring at its default size (GardenBackdrop.RingFor).</summary>
        public GardenBackdrop.Ring Ring { get; private set; }

        /// <summary>The ring's current scale: 1 at its default size.</summary>
        public float Scale { get; private set; } = 1f;

        /// <summary>The ring's current radius.</summary>
        public float Radius => Ring.Radius * Scale;

        /// <summary>The ring's current height, from its foot (y = -Sink) to its ceiling.</summary>
        public float Height => Ring.Height * Scale;

        /// <summary>The ring's current ceiling height (y, its flat part).</summary>
        public float Top => Height - GardenBackdrop.Sink;

        /// <summary>The camera followed (tests and tools); null follows Main's camera.</summary>
        public Camera View { get; set; }

        private Vector3 home;
        private bool fitted;

        /// <summary>Takes the ring's default size and its place under the level root (GardenBackdrop.Build).</summary>
        public void Init(GardenBackdrop.Ring ring)
        {
            Ring = ring;
            home = transform.localPosition;
            fitted = false;
            Scale = 1f;
            Apply();
        }

        /// <summary>The scale that holds a camera at <paramref name="eye"/> (world space).</summary>
        public float FitFor(Vector3 eye)
        {
            return GardenBackdrop.ScaleToHold(Ring, Local(eye));
        }

        /// <summary>
        /// One fit to the followed camera, eased over <paramref name="dt"/> seconds (float.PositiveInfinity: lands at
        /// once). Tests call it right after moving the camera; LateUpdate calls it every frame.
        /// </summary>
        public void Refresh(float dt)
        {
            Camera cam = Followed();
            if (cam == null)
            {
                return;
            }
            Vector3 eye = Local(cam.transform.position);
            FitTo(eye, dt);
            // The far clip holds the far side of the ring as it is now (OrbitCamera already set it for the largest ring:
            // this only matters for a camera beyond the level's own bounds). Raised only, never lowered.
            float reach = Mathf.Sqrt(GardenBackdrop.HorizontalSqr(Ring, eye)) + Radius;
            float rise = Mathf.Max(Top - eye.y, eye.y + GardenBackdrop.Sink);
            float need = Mathf.Sqrt(reach * reach + rise * rise) + 2f;
            if (cam.farClipPlane < need)
            {
                cam.farClipPlane = need;
            }
        }

        private void LateUpdate()
        {
            Refresh(Time.unscaledDeltaTime);
        }

        /// <summary>Fits the ring to a camera at <paramref name="eye"/> (in the level root's space), eased over <paramref name="dt"/>.</summary>
        private void FitTo(Vector3 eye, float dt)
        {
            float horizontal = Mathf.Sqrt(GardenBackdrop.HorizontalSqr(Ring, eye));
            float want = GardenBackdrop.ScaleToHold(Ring, horizontal, eye.y);
            float next = want;
            if (fitted && Tuning.GardenRingFitTime > 0f)
            {
                next = want + (Scale - want) * Mathf.Exp(-Mathf.Max(0f, dt) / Tuning.GardenRingFitTime);
                if (Mathf.Abs(next - want) < LandEpsilon)
                {
                    next = want;
                }
                // Never closer than MinClearance: a zoom out faster than the easing pushes the ring out at once.
                next = Mathf.Max(next, GardenBackdrop.ScaleToHold(Ring, horizontal, eye.y, MinClearance, MinClearance)); // MUTATION:GARDENZOOM_FLOOR
            }
            fitted = true;
            if (next != Scale)
            {
                Scale = next;
                Apply();
            }
        }

        private void Apply()
        {
            // Uniform about the centre of the foot: the foot (y = -Sink at scale 1) stays where it is.
            transform.localScale = new Vector3(Scale, Scale, Scale);
            transform.localPosition = home + Vector3.up * (GardenBackdrop.Sink * (Scale - 1f));
        }

        private Camera Followed()
        {
            if (View != null)
            {
                return View;
            }
            Main main = Main.Instance;
            return main != null ? main.Camera : null;
        }

        /// <summary>A world point in the ring's parent space (the level root's), where the ring's centre is given.</summary>
        private Vector3 Local(Vector3 world)
        {
            Transform parent = transform.parent;
            return parent != null ? parent.InverseTransformPoint(world) : world;
        }
    }
}
