using OutOfSight.Core;
using UnityEngine;
using UnityEngine.UI;

namespace OutOfSight
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
    ///
    /// M5 (docs/CONTRACT_M5.md 3, CONTRACT_M5_v3.md 15.4 to 15.6):
    /// - the routine is built by <see cref="RoutineFactory.Create(InhabitantDef, LevelDef, IPathPlanner, IPathPlanner, SeatRegistry, int, int)"/>
    ///   (the personality, the pattern, the frozen station walks, the investigate planner, the shared seats, the floor), and
    ///   <see cref="Personality"/> is its personality (a dog kind wins);
    /// - the transform stands on the floor under the routine (<see cref="InhabitantRoutine.FloorHeight"/>), and the visual
    ///   eye is the routine's eye (the personality's height, the dog's 0.35 m, plus the floor);
    /// - the identity: the personality's model (<see cref="ModelIdOf"/>, resolved by the level builder) wears its clothes
    ///   tint (<see cref="TintOf"/>, applied to the rig's model here);
    /// - a sleeping watcher shows a "z" (<see cref="MarkerKind.Sleeping"/>), and the wake telegraph that ends its sleep, eye
    ///   still closed, a blinking "z" (<see cref="MarkerKind.Waking"/>) with the head's telegraph tilt.
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

        /// <summary>
        /// M5 (docs/CONTRACT_M5.md 3, 16.12): the personality (or the dog), set at Init: the routine's own instance, so its
        /// range, angle, eye, hearing and roles are the ones the routine uses.
        /// </summary>
        public PersonalityDef Personality { get; set; }

        /// <summary>M5: the data this inhabitant was built from (null before Init).</summary>
        public InhabitantDef Def { get; private set; }

        /// <summary>M5: the dog (CONTRACT_M5_v3 4): its personality is the dog row.</summary>
        public bool IsDog => Personality != null && Personality.Id == PersonalityDef.Dog;

        /// <summary>M5: the clothes tint this inhabitant wears (<see cref="TintOf"/>), or null (a default inhabitant).</summary>
        public Color? Tint { get; private set; }

        /// <summary>M5: the clothes slots of the model that took <see cref="Tint"/> (0 without a model or a tint).</summary>
        public int TintedSlots { get; private set; }

        /// <summary>M3: the rigged model driving the visuals, or null for the procedural body (docs/CONTRACT_M3.md 5).</summary>
        public InhabitantRig Rig { get; private set; }

        public bool HasModel => Rig != null;

        /// <summary>M2: the routine mode (Routine, Alerted, Investigating, Carrying, Startled).</summary>
        public InhabitantMode Mode => Routine != null ? Routine.Mode : InhabitantMode.Routine;

        /// <summary>
        /// Which marker the head shows: none, "?" or "!" (probe and tests). M5: <see cref="Sleeping"/> a "z" over a sleeping
        /// watcher (its eye closed, its cone hidden), <see cref="Waking"/> the same "z" blinking during the wake telegraph.
        /// </summary>
        public enum MarkerKind { None, Question, Exclamation, Sleeping, Waking }

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

        /// <summary>
        /// M2: the routine plans its walks with <paramref name="planner"/> (docs/CONTRACT_M2.md 5). M5: through
        /// <see cref="RoutineFactory"/> with no level (a flat floor), no seat registry and every NavMesh area, so the
        /// personality and the pattern of <paramref name="def"/> still apply.
        /// </summary>
        public void Init(InhabitantDef def, IPathPlanner planner)
        {
            Init(def, null, planner, null, null, 0, RoutineFactory.AllAreas);
        }

        /// <summary>
        /// M5 (docs/CONTRACT_M5_v3.md 15.6): the routine of <paramref name="def"/> from
        /// <see cref="RoutineFactory.Create(InhabitantDef, LevelDef, IPathPlanner, IPathPlanner, SeatRegistry, int, int)"/>,
        /// with the level (its floor), the station planner (frozen station walks, restricted to
        /// <paramref name="stationAreaMask"/>: the authored leaves), the planner of every other walk (null: the station
        /// planner; the game passes one that plans with the current door mask), the level's shared seat registry and this
        /// inhabitant's index in it. Then the personality, the identity tint and the pose.
        /// </summary>
        public void Init(InhabitantDef def, LevelDef level, IPathPlanner stationPlanner, IPathPlanner investigatePlanner,
            SeatRegistry seats, int owner, int stationAreaMask)
        {
            Def = def;
            Routine = RoutineFactory.Create(def, level, stationPlanner ?? StraightPlanner.Instance, investigatePlanner, seats, owner,
                stationAreaMask);
            Personality = Routine.Personality;
            Tint = TintOf(def);
            BuildExpressions();
            ResetFootContact();
            SnapToRoutine();
            ApplyIdentity();
        }

        /// <summary>
        /// M5: the catalog model an inhabitant shows: its personality's (CONTRACT_M5 3; the dog's Shiba), an explicit
        /// <see cref="InhabitantDef.Model"/> winning. Null for a default inhabitant that names none (the procedural body).
        /// The level builder instantiates it.
        /// </summary>
        public static string ModelIdOf(InhabitantDef def)
        {
            return def != null ? PersonalityDef.ForInhabitant(def).Model : null;
        }

        /// <summary>
        /// M5: the clothes tint of an inhabitant: its personality's <see cref="PersonalityDef.Tint"/>, an explicit
        /// <see cref="InhabitantDef.BodyColor"/> winning. Null for the default personality: the inhabitants of levels 1 to 7
        /// keep the clothes of their model (their body colour paints the procedural body only, as in M3 and M4).
        /// </summary>
        public static Color? TintOf(InhabitantDef def)
        {
            if (def == null)
            {
                return null;
            }
            PersonalityDef p = PersonalityDef.ForInhabitant(def);
            if (p.Id == PersonalityDef.Default || string.IsNullOrEmpty(p.Tint) || !ColorUtility.TryParseHtmlString(p.Tint, out Color c))
            {
                return null;
            }
            return new Color(c.r, c.g, c.b, 1f);
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
            ApplyIdentity();
        }

        /// <summary>M5: the model's clothes take the personality's tint (whichever of Init and the rig comes last).</summary>
        private void ApplyIdentity()
        {
            TintedSlots = Rig != null && Tint.HasValue ? ModelKit.TintClothes(Rig.Model, Rig.Entry, Tint.Value) : 0;
            // M7 (product owner, 2026-11-18): the human's prints keep their real colours; the tint shows on the shirt's
            // collar and hem bands (CharacterLook).
            CharacterLook.Identify(Rig, Tint);
        }

        /// <summary>M5: where the body stands: the routine's planar position on the floor under it (CONTRACT_M5_v3 15.4).</summary>
        private Vector3 GroundedPosition => Routine.Position + Vector3.up * Routine.FloorHeight; // MUTATION:VISUAL_FLOOR

        /// <summary>Foot contacts: on the clip's contacts with a model, at the bob minima of the procedural body.</summary>
        private float FootContactPhase => Rig != null ? Rig.FootContactPhase : 0f;

        private void ResetFootContact()
        {
            footContactIndex = Mathf.FloorToInt((gaitCycles - FootContactPhase) * 2f);
        }

        private void SnapToRoutine()
        {
            currentPosition = previousPosition = GroundedPosition;
            currentBodyYaw = previousBodyYaw = Routine.BodyYaw;
            currentHeadYaw = previousHeadYaw = Routine.HeadYaw;
            currentEyeHeight = previousEyeHeight = Routine.EyeHeight;
            previousGaitCycles = gaitCycles;
            transform.SetPositionAndRotation(currentPosition, Quaternion.Euler(0f, Routine.BodyYaw, 0f));
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
            currentPosition = GroundedPosition;
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
            // M4: the eye height follows the routine (seated 1.15 m), interpolated like the pose. M5: the position stands on
            // the floor, so the visual eye is the routine's eye (EyePosition adds the same floor height).
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
            if (Routine.Asleep)
            {
                // M5: asleep, its eye is closed; the wake telegraph that ends the sleep keeps it closed and blinks the "z".
                kind = Routine.IsTelegraphing ? MarkerKind.Waking : MarkerKind.Sleeping;
            }
            else if (mode == InhabitantMode.Alerted)
            {
                kind = MarkerKind.Question;
            }
            else if (mode == InhabitantMode.Investigating || mode == InhabitantMode.Carrying || Routine.IsCarrying)
            {
                kind = MarkerKind.Exclamation;
            }
            bool sleepMarker = kind == MarkerKind.Sleeping || kind == MarkerKind.Waking;
            if (kind != Marker)
            {
                Marker = kind;
                markerCanvas.enabled = kind != MarkerKind.None;
                if (kind != MarkerKind.None)
                {
                    markerImage.sprite = sleepMarker ? SleepGlyph
                        : kind == MarkerKind.Question ? ProceduralArt.Question : ProceduralArt.Exclamation;
                    markerRoot.localScale = Vector3.one * ((sleepMarker ? Tuning.SleepMarkerSize : MarkerSize) / 100f);
                }
            }
            if (kind == MarkerKind.None)
            {
                return;
            }
            // M5: the wake telegraph blinks the "z" (held while paused, like the float).
            bool blinkOff = kind == MarkerKind.Waking && Mathf.Repeat(visualClock * Tuning.WakeMarkerBlinkRate, 1f) >= 0.5f;
            markerImage.color = new Color(1f, 1f, 1f, blinkOff ? 0.25f : 1f);
            // Billboard toward the camera, with a gentle float (held while paused).
            float bob = 0.04f * Mathf.Sin(visualClock * 3.2f);
            if (Rig != null && Rig.Head != null)
            {
                // M5: above the head of a lower watcher (the dog): the height follows the personality's standing eye.
                float standingEye = Personality != null && Personality.EyeHeight > 0f ? Personality.EyeHeight : Tuning.EyeHeight;
                markerRoot.position = Rig.MarkerPosition(MarkerHeight - Tuning.EyeHeight + standingEye + bob);
            }
            else
            {
                // The procedural body already sinks by its eye's drop below Tuning.EyeHeight (seated, or a low watcher).
                markerRoot.localPosition = new Vector3(0f, MarkerHeight + bob, 0f);
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

        /// <summary>M5: the marker's world position (tests: above the head of the watcher that wears it).</summary>
        public Vector3 MarkerPosition => markerRoot != null ? markerRoot.position : transform.position;

        /// <summary>M5: true while the marker canvas draws (tests).</summary>
        public bool MarkerShown => markerCanvas != null && markerCanvas.enabled;

        // ----- M5: the sleep "z" (drawn here: a glyph of the watchers' own marker, no new material) -----

        private static Sprite sleepGlyph;

        /// <summary>A big "Z" and a small one above it, pale blue with a dark outline (the style of the "?" and "!").</summary>
        public static Sprite SleepGlyph => sleepGlyph != null ? sleepGlyph : sleepGlyph = DrawSleepGlyph();

        private static Sprite DrawSleepGlyph()
        {
            const int size = 96;
            var texture = new Texture2D(size, size, TextureFormat.RGBA32, false)
            {
                name = "SleepZ",
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear,
                hideFlags = HideFlags.DontUnloadUnusedAsset,
            };
            var pixels = new Color[size * size];
            float pixel = 2f / size;
            var fill = new Color(0.74f, 0.88f, 1f, 1f);
            var ink = new Color(0.08f, 0.08f, 0.1f, 1f);
            const float outline = 0.07f;
            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    var p = new Vector2((x + 0.5f) / size * 2f - 1f, (y + 0.5f) / size * 2f - 1f);
                    float d = Mathf.Min(ZDistance(p, new Vector2(-0.78f, -0.78f), 0.95f) - 0.11f,
                        ZDistance(p, new Vector2(0.3f, 0.3f), 0.5f) - 0.075f);
                    float inked = Mathf.Clamp01(0.5f - (d - outline) / pixel);
                    float filled = Mathf.Clamp01(0.5f - d / pixel);
                    Color c = Color.Lerp(ink, fill, filled);
                    c.a = inked;
                    pixels[y * size + x] = c;
                }
            }
            texture.SetPixels(pixels);
            texture.Apply(false, true);
            Sprite sprite = Sprite.Create(texture, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f);
            sprite.name = "SleepZ";
            sprite.hideFlags = HideFlags.DontUnloadUnusedAsset;
            return sprite;
        }

        /// <summary>Distance to a "Z" of side <paramref name="side"/> whose bottom left corner is <paramref name="corner"/>.</summary>
        private static float ZDistance(Vector2 p, Vector2 corner, float side)
        {
            var bottomLeft = corner;
            var bottomRight = corner + new Vector2(side, 0f);
            var topLeft = corner + new Vector2(0f, side);
            var topRight = corner + new Vector2(side, side);
            return Mathf.Min(Segment(p, topLeft, topRight), Mathf.Min(Segment(p, topRight, bottomLeft), Segment(p, bottomLeft, bottomRight)));
        }

        private static float Segment(Vector2 p, Vector2 a, Vector2 b)
        {
            Vector2 ab = b - a;
            float t = Mathf.Clamp01(Vector2.Dot(p - a, ab) / ab.sqrMagnitude);
            return (p - (a + ab * t)).magnitude;
        }
    }
}
