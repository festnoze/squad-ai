using Meuble.Core;
using UnityEngine;
using UnityEngine.UI;

namespace Meuble
{
    /// <summary>
    /// Applies an <see cref="InhabitantRoutine"/> to a body made of primitives (PRD 5.1, 5.2). The routine
    /// is the gameplay truth; transforms follow it and only the visuals interpolate.
    ///
    /// M2 visuals (docs/CONTRACT_M2.md 7): a floating "?" over the head while Alerted, a frown (two tilted
    /// eyebrow boxes) and a "!" while Investigating or Carrying, the arms forward while carrying. The
    /// marker is a world space Canvas, shown and hidden by enabling the Canvas, never its GameObject.
    /// Everything is built once in <see cref="Init(InhabitantDef, IPathPlanner)"/>, so a rebuilt level always
    /// has the same object count (probe step 09).
    ///
    /// M3 (docs/CONTRACT_M3.md 5): when a rigged model is attached (<see cref="InhabitantRig.Attach"/>), there is
    /// no procedural body. The rig is driven from this LateUpdate with the same interpolated pose, the markers
    /// float above its head bone, and the frown is the rig's two brow boxes on the head bone (M3.1), driven by the
    /// same blend as <see cref="Frowning"/>. <see cref="FootstepCount"/> counts foot contacts
    /// of the fixed step gait. While <see cref="GamePause.IsPaused"/> the visuals hold the last fixed step pose.
    /// </summary>
    public sealed class Inhabitant : MonoBehaviour
    {
        public Transform Visual;
        public Transform Body;
        public Transform HeadPivot;
        public Transform ArmLeft;
        public Transform ArmRight;
        public Transform[] Eyes;

        public InhabitantRoutine Routine { get; private set; }

        /// <summary>M3: the rigged model driving the visuals, or null for the procedural body (docs/CONTRACT_M3.md 5).</summary>
        public InhabitantRig Rig { get; private set; }

        public bool HasModel => Rig != null;

        /// <summary>M2: the routine mode (Routine, Alerted, Investigating, Carrying, Startled).</summary>
        public InhabitantMode Mode => Routine != null ? Routine.Mode : InhabitantMode.Routine;

        /// <summary>Which marker the head shows: none, "?" or "!" (probe and tests).</summary>
        public enum MarkerKind { None, Question, Exclamation }

        public MarkerKind Marker { get; private set; }
        public bool Frowning => frownBlend > 0.5f;

        private Vector3 previousPosition;
        private Vector3 currentPosition;
        private float previousBodyYaw;
        private float currentBodyYaw;
        private float previousHeadYaw;
        private float currentHeadYaw;
        private float tilt;
        private float walkPhase;
        // M3 gait: walk cycles from level start (fixed step), the previous step's value, and the last foot contact.
        private float gaitCycles;
        private float previousGaitCycles;
        private int footContactIndex;
        private float visualClock;
        private float startledBlend;
        private float frownBlend;
        private float carryBlend;
        private float bendBlend;
        // M4: the routine's eye height at the last two fixed steps, and the pratfall blend.
        private float previousEyeHeight = Tuning.EyeHeight;
        private float currentEyeHeight = Tuning.EyeHeight;
        private float pratfallBlend;

        private Transform browLeft;
        private Transform browRight;
        private Canvas markerCanvas;
        private Image markerImage;
        private Transform markerRoot;

        // Same color as the pupils of LevelBuilder: PrimitiveKit caches by color, so no new material (PRD 7.4).
        private static readonly Color BrowColor = new Color(0.06f, 0.06f, 0.08f);
        private const float MarkerHeight = 2.08f;
        private const float MarkerSize = 0.34f;

        // M4 pratfall pose (render only; wanted in Tuning, integrator): it lands fast and gets up slower.
        private const float PratfallInRate = Tuning.PratfallInRate;
        private const float PratfallOutRate = Tuning.PratfallOutRate;
        private const float ProceduralPratfallDrop = Tuning.ProceduralPratfallDrop;
        private const float ProceduralPratfallArms = Tuning.ProceduralPratfallArms;

        public Vector3 EyePosition => Routine.EyePosition;

        /// <summary>
        /// M3 (docs/CONTRACT_M3.md 5): increments at every foot contact, twice per walk cycle, from the fixed step
        /// gait phase (never from the rendered clip time). The audio agent plays a step on each increment.
        /// </summary>
        public int FootstepCount { get; protected set; }
        public Vector3 EyeForward => Routine.EyeForward;

        /// <summary>Interpolated eye pose, for the floor cone (render only).</summary>
        public Vector3 VisualEyePosition { get; private set; }
        public float VisualEyeYaw { get; private set; }

        /// <summary>
        /// M4 (docs/CONTRACT_M4.md 3): the eye height above the floor between fixed steps, interpolated from
        /// <see cref="InhabitantRoutine.EyeHeight"/> (1.6 m standing, 1.15 m seated). The visual eye, the procedural
        /// head and the model's head bone follow it.
        /// </summary>
        public float VisualEyeHeight { get; private set; } = Tuning.EyeHeight;

        /// <summary>M4: the body shows seated (on a seat, on nothing, or standing up from one).</summary>
        public bool SeatedPose { get; private set; }

        /// <summary>M4: the pratfall pose weight, 0 to 1 (render only).</summary>
        public float PratfallBlend => pratfallBlend;

        public void Init(InhabitantDef def)
        {
            Init(def, StraightPlanner.Instance);
        }

        /// <summary>M2: the routine plans its walks with <paramref name="planner"/> (docs/CONTRACT_M2.md 5).</summary>
        public void Init(InhabitantDef def, IPathPlanner planner)
        {
            Routine = new InhabitantRoutine(def.Stations, def.StartStation, planner ?? StraightPlanner.Instance);
            BuildExpressions();
            ResetFootContact();
            SnapToRoutine();
        }

        /// <summary>Called by <see cref="InhabitantRig.Attach"/>: the model replaces the procedural body.</summary>
        internal void AttachRig(InhabitantRig rig)
        {
            Rig = rig;
            ResetFootContact();
            if (Routine != null)
            {
                SnapToRoutine();
            }
        }

        /// <summary>Foot contacts: on the clip's contacts with a model, at the bob minima of the procedural body.</summary>
        private float FootContactPhase => Rig != null ? Rig.FootContactPhase : 0f;

        private void ResetFootContact()
        {
            footContactIndex = Mathf.FloorToInt((gaitCycles - FootContactPhase) * 2f);
        }

        private void SnapToRoutine()
        {
            currentPosition = previousPosition = Routine.Position;
            currentBodyYaw = previousBodyYaw = Routine.BodyYaw;
            currentHeadYaw = previousHeadYaw = Routine.HeadYaw;
            currentEyeHeight = previousEyeHeight = Routine.EyeHeight;
            previousGaitCycles = gaitCycles;
            transform.SetPositionAndRotation(Routine.Position, Quaternion.Euler(0f, Routine.BodyYaw, 0f));
            VisualEyePosition = Routine.EyePosition;
            VisualEyeYaw = Routine.EyeYaw;
            ApplyVisual(1f);
        }

        /// <summary>Freezes the inhabitant at a pose for the probe (see <see cref="InhabitantRoutine.Pin"/>).</summary>
        public void Pin(Vector3 position, float bodyYaw, float headYaw = 0f)
        {
            Routine.Pin(position, bodyYaw, headYaw);
            SnapToRoutine();
        }

        /// <summary>
        /// M2 pin (docs/CONTRACT_M2.md 3.4): a frozen pin when <paramref name="reactive"/> is false (M1), or a
        /// reactive pin that still hears and investigates, then walks back to the pose. Cancels any mode.
        /// </summary>
        public void Pin(Vector3 position, float bodyYaw, float headYaw, bool reactive)
        {
            Routine.Pin(position, bodyYaw, headYaw, reactive);
            SnapToRoutine();
        }

        public void Startle(Vector3 target)
        {
            Routine.Startle(target);
        }

        /// <summary>One fixed step, called by GameState.</summary>
        public void Step(float dt)
        {
            Routine.Step(dt);
            previousPosition = currentPosition;
            previousBodyYaw = currentBodyYaw;
            previousHeadYaw = currentHeadYaw;
            previousEyeHeight = currentEyeHeight;
            currentPosition = Routine.Position;
            currentBodyYaw = Routine.BodyYaw;
            currentHeadYaw = Routine.HeadYaw;
            currentEyeHeight = Routine.EyeHeight;
            transform.SetPositionAndRotation(currentPosition, Quaternion.Euler(0f, currentBodyYaw, 0f));
            previousGaitCycles = gaitCycles;
            RoutineActivity activity = Routine.LastActivity;
            if (activity == RoutineActivity.Walking || activity == RoutineActivity.Carrying)
            {
                // Carrying a chair is a heavier, slower gait.
                float rate = activity == RoutineActivity.Carrying ? 7.5f : 9f;
                walkPhase += dt * rate;
                if (Rig != null)
                {
                    // The model's stride: one clip cycle per WalkCycleDistance walked, so the feet do not slide.
                    float walked = YawMath.Planar(currentPosition - previousPosition).magnitude;
                    gaitCycles += Mathf.Min(walked, 2f * Tuning.WalkSpeed * dt) / Rig.WalkCycleDistance;
                }
                else
                {
                    // The procedural gait of M2: one cycle per 2 pi of walkPhase, a foot down at each bob minimum.
                    gaitCycles += dt * rate / (2f * Mathf.PI);
                }
                int contact = Mathf.FloorToInt((gaitCycles - FootContactPhase) * 2f);
                if (contact > footContactIndex)
                {
                    FootstepCount += contact - footContactIndex;
                    footContactIndex = contact;
                }
            }
        }

        private void LateUpdate()
        {
            if (Routine == null)
            {
                return;
            }
            // Paused: no fixed step runs, so the visuals hold the last step's pose (CONTRACT_M3 6).
            float alpha = GamePause.IsPaused ? 1f : Mathf.Clamp01((Time.time - Time.fixedTime) / Time.fixedDeltaTime);
            ApplyVisual(alpha);
        }

        private void ApplyVisual(float alpha)
        {
            Vector3 position = Vector3.Lerp(previousPosition, currentPosition, alpha);
            float bodyYaw = Mathf.LerpAngle(previousBodyYaw, currentBodyYaw, alpha);
            float headYaw = Mathf.Lerp(previousHeadYaw, currentHeadYaw, alpha);
            // M4: the eye height follows the routine (seated 1.15 m), interpolated like the pose.
            float eyeHeight = Mathf.Lerp(previousEyeHeight, currentEyeHeight, alpha);
            VisualEyeHeight = eyeHeight;
            VisualEyePosition = position + new Vector3(0f, eyeHeight, 0f);
            VisualEyeYaw = bodyYaw + headYaw;
            bool paused = GamePause.IsPaused;
            // Every visual blend and the marker float hold while paused.
            float dt = Application.isPlaying && !paused ? Time.deltaTime : 0f;
            visualClock += dt;
            RoutineActivity current = Routine.LastActivity;
            // Down: seated, on the floor after a pratfall (its telegraph before getting up included), or standing up.
            SeatedPose = Routine.IsLowered || Routine.IsSitting || current == RoutineActivity.Sitting
                || current == RoutineActivity.StandingUp || current == RoutineActivity.Pratfall;
            bool onTheFloor = current == RoutineActivity.Pratfall
                || (Routine.IsLowered && !Routine.IsSitting && current != RoutineActivity.StandingUp
                    && Routine.LastSitResult == SitResult.Pratfall);
            pratfallBlend = Mathf.MoveTowards(pratfallBlend, onTheFloor ? 1f : 0f, dt * (onTheFloor ? PratfallInRate : PratfallOutRate));
            // M4.1 (CONTRACT_M4 10.2): the routine itself slides onto the seat over the sit-down, so the body, the
            // model's eyes and the floor cone's apex all follow the one interpolated pose: no visual-only slide.
            if (Rig != null)
            {
                ApplyRig(position, bodyYaw, headYaw, eyeHeight, alpha, dt, paused);
                return;
            }
            UpdateMarker();
            if (Visual == null)
            {
                return;
            }
            InhabitantMode mode = Routine.Mode;
            RoutineActivity activity = Routine.LastActivity;
            bool carrying = mode == InhabitantMode.Carrying || Routine.IsCarrying;
            bool frown = mode == InhabitantMode.Investigating || carrying;
            // Telegraph: a small head tilt, eased in and out so it reads as a beat, not a twitch.
            tilt = Mathf.MoveTowards(tilt, Routine.IsTelegraphing ? 1f : 0f, dt * 6f);
            startledBlend = Mathf.MoveTowards(startledBlend, Routine.IsStartled ? 1f : 0f, dt * 8f);
            frownBlend = Mathf.MoveTowards(frownBlend, frown ? 1f : 0f, dt * 7f);
            carryBlend = Mathf.MoveTowards(carryBlend, carrying ? 1f : 0f, dt * 5f);
            // Pick up and put down: a short forward bend over the furniture (0.5 s each, so a fast blend).
            bool bending = activity == RoutineActivity.PickingUp || activity == RoutineActivity.PuttingDown;
            bendBlend = Mathf.MoveTowards(bendBlend, bending ? 1f : 0f, dt * 6f);
            bool walking = activity == RoutineActivity.Walking || activity == RoutineActivity.Carrying;
            float bob = walking ? 0.025f * Mathf.Abs(Mathf.Sin(walkPhase)) : 0f;
            // M4: the procedural body sits by sinking as a whole, so its head pivot (built at the standing eye
            // height) stays exactly at the routine's eye; a pratfall sinks it further, to the floor.
            float sink = Tuning.EyeHeight - eyeHeight + ProceduralPratfallDrop * pratfallBlend;
            Visual.SetPositionAndRotation(position + Vector3.up * (bob - sink), Quaternion.Euler(-6f * startledBlend + 14f * bendBlend, bodyYaw, 0f));
            if (HeadPivot != null)
            {
                HeadPivot.localRotation = Quaternion.Euler(-4f * tilt + 6f * frownBlend, headYaw, 12f * tilt);
            }
            // Arms: swing while walking, forward while carrying (holding the chair at CarryAnchor), up when startled
            // and, flailing, during a pratfall.
            float swing = walking ? 22f * Mathf.Sin(walkPhase) * (1f - carryBlend) : 0f;
            float forward = -72f * carryBlend + 20f * bendBlend;
            float raise = 150f * startledBlend + ProceduralPratfallArms * pratfallBlend;
            if (ArmLeft != null)
            {
                ArmLeft.localRotation = Quaternion.Euler(swing + forward, 0f, -raise - 6f * carryBlend);
            }
            if (ArmRight != null)
            {
                ArmRight.localRotation = Quaternion.Euler(-swing + forward, 0f, raise + 6f * carryBlend);
            }
            if (Eyes != null)
            {
                float s = 1f + 0.6f * startledBlend;
                foreach (Transform eye in Eyes)
                {
                    if (eye != null)
                    {
                        eye.localScale = Vector3.one * s;
                    }
                }
            }
            // Frown: the inner ends of the brows go down (left brow turns clockwise, right brow counterclockwise).
            if (browLeft != null)
            {
                browLeft.localPosition = new Vector3(-0.062f, 0.098f - 0.012f * frownBlend + 0.02f * startledBlend, 0.11f);
                browLeft.localRotation = Quaternion.Euler(0f, 0f, Mathf.Lerp(6f, -24f, frownBlend) + 10f * startledBlend);
            }
            if (browRight != null)
            {
                browRight.localPosition = new Vector3(0.062f, 0.098f - 0.012f * frownBlend + 0.02f * startledBlend, 0.11f);
                browRight.localRotation = Quaternion.Euler(0f, 0f, Mathf.Lerp(-6f, 24f, frownBlend) - 10f * startledBlend);
            }
        }

        /// <summary>
        /// M3: the model's visuals. The body is placed without the procedural bob or tilt (the clips move it), then
        /// the rig poses the spine, the arms and the head, then the marker goes above the posed head.
        /// </summary>
        private void ApplyRig(Vector3 position, float bodyYaw, float headYaw, float eyeHeight, float alpha, float dt, bool paused)
        {
            InhabitantMode mode = Routine.Mode;
            RoutineActivity activity = Routine.LastActivity;
            bool carrying = mode == InhabitantMode.Carrying || Routine.IsCarrying;
            bool frown = mode == InhabitantMode.Investigating || carrying;
            bool bending = activity == RoutineActivity.PickingUp || activity == RoutineActivity.PuttingDown;
            tilt = Mathf.MoveTowards(tilt, Routine.IsTelegraphing ? 1f : 0f, dt * 6f);
            startledBlend = Mathf.MoveTowards(startledBlend, Routine.IsStartled ? 1f : 0f, dt * 8f);
            frownBlend = Mathf.MoveTowards(frownBlend, frown ? 1f : 0f, dt * 7f);
            carryBlend = Mathf.MoveTowards(carryBlend, carrying ? 1f : 0f, dt * 5f);
            bendBlend = Mathf.MoveTowards(bendBlend, bending ? 1f : 0f, dt * 6f);
            if (Visual != null)
            {
                Visual.SetPositionAndRotation(position, Quaternion.Euler(0f, bodyYaw, 0f));
            }
            float gait = Mathf.Lerp(previousGaitCycles, gaitCycles, alpha);
            Rig.Apply(bodyYaw, bodyYaw + headYaw, activity, tilt, carryBlend, bendBlend, frownBlend, startledBlend, gait, paused,
                SeatedPose, eyeHeight, pratfallBlend);
            UpdateMarker();
        }

        // ----- M2 expressions -----

        private void BuildExpressions()
        {
            int layer = gameObject.layer;
            if (HeadPivot != null && browLeft == null)
            {
                Material brow = PrimitiveKit.Lit(BrowColor, 0.7f);
                var size = new Vector3(0.075f, 0.017f, 0.02f);
                browLeft = PrimitiveKit.Box(HeadPivot, "BrowL", new Vector3(-0.062f, 0.098f, 0.11f), size, brow, layer, false).transform;
                browRight = PrimitiveKit.Box(HeadPivot, "BrowR", new Vector3(0.062f, 0.098f, 0.11f), size, brow, layer, false).transform;
                foreach (Transform b in new[] { browLeft, browRight })
                {
                    b.GetComponent<MeshRenderer>().shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                }
            }
            if (markerCanvas == null)
            {
                Transform parent = Visual != null ? Visual : transform;
                var go = new GameObject("Marker", typeof(RectTransform)) { layer = layer };
                go.transform.SetParent(parent, false);
                markerRoot = go.transform;
                var rect = (RectTransform)go.transform;
                rect.localPosition = new Vector3(0f, MarkerHeight, 0f);
                // 100 canvas units per meter: a 100 x 100 rect scaled to MarkerSize meters.
                rect.sizeDelta = new Vector2(100f, 100f);
                rect.localScale = Vector3.one * (MarkerSize / 100f);
                markerCanvas = go.AddComponent<Canvas>();
                markerCanvas.renderMode = RenderMode.WorldSpace;
                markerCanvas.sortingOrder = 5;
                var imageGo = new GameObject("Glyph", typeof(RectTransform)) { layer = layer };
                imageGo.transform.SetParent(go.transform, false);
                var imageRect = (RectTransform)imageGo.transform;
                imageRect.anchorMin = Vector2.zero;
                imageRect.anchorMax = Vector2.one;
                imageRect.offsetMin = Vector2.zero;
                imageRect.offsetMax = Vector2.zero;
                markerImage = imageGo.AddComponent<Image>();
                markerImage.sprite = ProceduralArt.Question;
                markerImage.raycastTarget = false;
                markerImage.preserveAspect = true;
                markerCanvas.enabled = false;
            }
        }

        private void UpdateMarker()
        {
            if (markerCanvas == null || Routine == null)
            {
                return;
            }
            InhabitantMode mode = Routine.Mode;
            MarkerKind kind = MarkerKind.None;
            if (mode == InhabitantMode.Alerted)
            {
                kind = MarkerKind.Question;
            }
            else if (mode == InhabitantMode.Investigating || mode == InhabitantMode.Carrying || Routine.IsCarrying)
            {
                kind = MarkerKind.Exclamation;
            }
            if (kind != Marker)
            {
                Marker = kind;
                markerCanvas.enabled = kind != MarkerKind.None;
                if (kind != MarkerKind.None)
                {
                    markerImage.sprite = kind == MarkerKind.Question ? ProceduralArt.Question : ProceduralArt.Exclamation;
                }
            }
            if (kind == MarkerKind.None)
            {
                return;
            }
            // Billboard toward the camera, with a gentle float (held while paused).
            float height = MarkerHeight + 0.04f * Mathf.Sin(visualClock * 3.2f);
            if (Rig != null && Rig.Head != null)
            {
                markerRoot.position = Rig.MarkerPosition(height);
            }
            else
            {
                markerRoot.localPosition = new Vector3(0f, height, 0f);
            }
            Camera cam = Camera.main;
            if (cam != null)
            {
                Vector3 toCamera = markerRoot.position - cam.transform.position;
                if (toCamera.sqrMagnitude > 1e-6f)
                {
                    markerRoot.rotation = Quaternion.LookRotation(toCamera, Vector3.up);
                }
            }
        }
    }
}
