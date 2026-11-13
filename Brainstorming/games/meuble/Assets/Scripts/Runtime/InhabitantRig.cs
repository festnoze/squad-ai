using System;
using Meuble.Core;
using UnityEngine;

namespace Meuble
{
    /// <summary>
    /// Drives a rigged human model from the inhabitant's routine (docs/CONTRACT_M3.md 5). The model is a visual
    /// only: the routine stays the gameplay truth, and this component never moves anything the rules read.
    ///
    /// Built for the Quaternius HumanArmature family (docs/M3_ASSETS.md 6): 31 bones, Legacy clips named
    /// "HumanArmature|Man_Idle" or "HumanArmature|Female_Idle", armature node at scale 100, facing +Z.
    ///
    /// - <b>Clips.</b> glTFast puts an <see cref="UnityEngine.Animation"/> on the model root that plays its first
    ///   clip (Clapping) automatically. Attach turns that off, finds Idle, Walk and Jump by suffix, and cross fades
    ///   by activity: Walk while walking or carrying, Jump once (then held) when startled, Idle otherwise.
    /// - <b>Walk phase.</b> The walk clip is slaved to the fixed step gait phase that <see cref="Inhabitant"/>
    ///   advances by the distance walked (one clip cycle per <see cref="WalkCycleDistance"/>), so the feet do not
    ///   slide and each footstep sound lands on a foot contact.
    /// - <b>Head.</b> In LateUpdate, after the animation, the head bone world rotation is set absolutely to
    ///   LookRotation(interpolated eye forward) * calibration * telegraph roll. The calibration is the head's
    ///   rotation in the bind pose (from the skin's bindposes) relative to the body facing; for this family the
    ///   bind pose is a T-pose with the head upright, so the face looks exactly along the routine's eye forward.
    ///   Note: the glTF node rest pose is NOT the bind pose (head tilted 3.5 to 4.8 deg, arms down).
    /// - <b>Carry and bend.</b> The arms (carry) and the spine (pick up, put down) are set absolutely toward a
    ///   target pose built from the Idle pose, blended with the M2 visual weights, never added on top of the clip.
    /// - <b>Unkeyed bones.</b> Legacy Animation only writes the bones a clip keys, and no clip of this family keys
    ///   the spine (Abdomen), nor Idle the head. So every bone the rig drives is put back to its rest local rotation
    ///   in Update, before the animation: an override never outlives its frame.
    /// - <b>Brows</b> (M3.1). Two small boxes on the head bone frown while investigating or carrying (pillar 4's comic
    ///   beat), with the model's own near-black material: no new material.
    /// - <b>Pause.</b> While <see cref="GamePause.IsPaused"/> every clip runs at speed 0.
    /// - <b>Sitting</b> (M4, docs/CONTRACT_M4.md 3). While the routine is seated the rig plays "_Sitting" (once, then
    ///   held), "_Standing" while it stands up, and Idle when the model lacks the clip. The family's sitting pose is a
    ///   high perch (eyes at 1.31 m, hips 0.26 m back), so a seat fit moves the whole visual until the head bone stands
    ///   where the standing head would be, at the routine's eye height: the eyes are at 1.15 m on a seat and the
    ///   hips land over the seat. A pratfall sits on nothing, then drops to the floor tilting back.
    ///
    /// Everything is driven by <see cref="Inhabitant"/>'s LateUpdate (one call per frame, after the body is placed),
    /// so the order of the two components never matters. The component lives on the inhabitant root: no Transform
    /// is added (probe step 09 counts them).
    /// </summary>
    public sealed class InhabitantRig : MonoBehaviour
    {
        // Wanted in Tuning (integrator); private until they land there.
        private const float CrossFadeSeconds = Tuning.RigCrossFadeSeconds;
        private const float TelegraphRollDegrees = Tuning.RigTelegraphRollDegrees;
        private const float WalkCycleMeters = Tuning.RigWalkCycleMeters;
        private const float FootContactCycle = Tuning.RigFootContactCycle;
        private const float BendDegrees = Tuning.RigBendDegrees;
        private const float CarryUpperArmPitch = Tuning.RigCarryUpperArmPitch;
        private const float CarryLowerArmPitch = Tuning.RigCarryLowerArmPitch;
        private const float CarryArmSplay = Tuning.RigCarryArmSplay;

        // Brows (M3.1), in meters in the face frame (x right, y up, z forward) from the eye centroid. Wanted in Tuning.
        private static readonly Vector3 BrowSize = new Vector3(0.042f, 0.010f, 0.012f);   // Tuning.RigBrowSize
        private static readonly Vector3 BrowOffset = new Vector3(0.032f, 0.030f, 0.016f); // Tuning.RigBrowOffset (x mirrored)
        private const float BrowFlatDegrees = Tuning.RigBrowFlat;       // inner ends slightly up at rest
        private const float BrowFrownDegrees = Tuning.RigBrowFrown;    // inner ends down
        private const float BrowFrownDrop = Tuning.RigBrowFrownDrop;    // m

        /// <summary>Clip suffixes, matched with EndsWith ("Jump" alone would also match RunningJump).</summary>
        public const string IdleSuffix = "_Idle";
        public const string WalkSuffix = "_Walk";
        public const string JumpSuffix = "_Jump";
        public const string SitSuffix = "_Sitting";
        public const string StandSuffix = "_Standing";

        /// <summary>The hips bone, the pivot of the pratfall's backward tilt.</summary>
        public const string HipsBoneName = "Hips";

        // M4 pratfall pose (render only; wanted in Tuning, integrator): from the seat fit down to the floor, tilting back.
        private const float PratfallDrop = Tuning.RigPratfallDrop;
        private const float PratfallPitchDegrees = Tuning.RigPratfallPitchDegrees;

        // Bone names of the HumanArmature skeleton, shared by every Quaternius human of docs/M3_ASSETS.md 6.1.
        public const string DefaultHeadBone = "Head";
        public const string SpineBoneName = "Abdomen";
        public const string UpperArmLeftName = "UpperArm.L";
        public const string LowerArmLeftName = "LowerArm.L";
        public const string UpperArmRightName = "UpperArm.R";
        public const string LowerArmRightName = "LowerArm.R";

        public enum Clip
        {
            None,
            Idle,
            Walk,
            Jump,
            // M4.
            Sit,
            Stand,
        }

        public Inhabitant Owner { get; private set; }
        public GameObject Model { get; private set; }
        public ModelCatalog.Entry Entry { get; private set; }

        /// <summary>The Legacy animation component glTFast put on the model root (null if the model has none).</summary>
        public Animation Animation { get; private set; }

        public SkinnedMeshRenderer Skin { get; private set; }
        public Transform Head { get; private set; }
        public Transform Spine { get; private set; }
        public Transform UpperArmLeft { get; private set; }
        public Transform LowerArmLeft { get; private set; }
        public Transform UpperArmRight { get; private set; }
        public Transform LowerArmRight { get; private set; }

        /// <summary>M3.1: the brow boxes (children of <see cref="BrowPivot"/>, itself a child of the head bone).</summary>
        public Transform BrowLeft { get; private set; }
        public Transform BrowRight { get; private set; }

        /// <summary>The face frame on the head bone: origin at the eyes, meters, x right, y up, z forward.</summary>
        public Transform BrowPivot { get; private set; }

        /// <summary>Animation state names (the glTF clip names), null when the model lacks the clip.</summary>
        public string IdleClipName { get; private set; }
        public string WalkClipName { get; private set; }
        public string JumpClipName { get; private set; }

        public AnimationState IdleState => StateOf(IdleClipName);
        public AnimationState WalkState => StateOf(WalkClipName);
        public AnimationState JumpState => StateOf(JumpClipName);

        // ----- M4: sitting (docs/CONTRACT_M4.md 3) -----

        /// <summary>The "_Sitting" and "_Standing" state names, null when the model lacks them (Idle is lowered instead).</summary>
        public string SitClipName { get; private set; }
        public string StandClipName { get; private set; }
        public AnimationState SitState => StateOf(SitClipName);
        public AnimationState StandState => StateOf(StandClipName);

        public Transform Hips { get; private set; }

        /// <summary>True on the frames the seat fit moved the visual (seated, standing up, or the eye still low).</summary>
        public bool SeatFitActive { get; private set; }

        /// <summary>What the seat fit and the pratfall added to the visual's position this frame (world space, meters).</summary>
        public Vector3 SeatOffset { get; private set; }

        /// <summary>The head bone in the Idle pose, in the body frame (x right, y up, z forward, meters from the feet).</summary>
        public Vector3 HeadRestLocal { get; private set; }

        /// <summary>Height of the eyes above the head bone with the head held upright (the rig's head pose).</summary>
        public float EyeAboveHead { get; private set; }

        /// <summary>The clip the rig last cross faded to.</summary>
        public Clip CurrentClip { get; private set; }

        /// <summary>The weight (0 to 1) of the telegraph roll applied to the head this frame.</summary>
        public float Tilt { get; private set; }

        /// <summary>True when the head calibration came from the skin's bindposes (false: from the Idle pose).</summary>
        public bool CalibratedFromBindPose { get; private set; }

        /// <summary>Height of the head bone above the feet in the Idle pose (m), measured once at Attach.</summary>
        public float HeadRestHeight { get; private set; }

        /// <summary>Meters walked per Walk clip cycle: the gait phase advances by distance / this.</summary>
        public float WalkCycleDistance => WalkCycleMeters;

        /// <summary>Normalized clip time of the first foot contact; the second one is half a cycle later.</summary>
        public float FootContactPhase => FootContactCycle;

        /// <summary>The face direction of the head bone: the bone axis that pointed forward in the bind pose.</summary>
        public Vector3 HeadForward => Head != null ? Head.rotation * headLocalForward : Vector3.forward;

        /// <summary>The model's eye (catalog eyeLocal in head bone space), in world space.</summary>
        public Vector3 EyePosition => Head != null ? Head.TransformPoint(Entry != null ? Entry.eyeLocal : Vector3.zero) : Vector3.zero;

        private Quaternion headCalibration = Quaternion.identity;
        private Vector3 headLocalForward = Vector3.forward;
        private Quaternion spineRest = Quaternion.identity;
        private Quaternion upperLeftRest = Quaternion.identity;
        private Quaternion lowerLeftRest = Quaternion.identity;
        private Quaternion upperRightRest = Quaternion.identity;
        private Quaternion lowerRightRest = Quaternion.identity;
        // Rest local rotations of every driven bone (same order as Driven()), restored before each animation pass.
        private Transform[] driven = new Transform[0];
        private Quaternion[] drivenLocalRest = new Quaternion[0];

        /// <summary>
        /// Binds a model instantiated under the inhabitant's Visual (docs/CONTRACT_M3.md 5). Returns null, with one
        /// warning, when the model has no head bone: the caller then falls back to the procedural body. Can be called
        /// before or after <see cref="Inhabitant.Init(InhabitantDef, IPathPlanner)"/>.
        /// </summary>
        public static InhabitantRig Attach(Inhabitant inhabitant, GameObject modelRoot, ModelCatalog.Entry entry)
        {
            if (inhabitant == null || modelRoot == null)
            {
                Debug.LogWarning("[InhabitantRig] Attach called without an inhabitant or a model.");
                return null;
            }
            InhabitantRig rig = inhabitant.GetComponent<InhabitantRig>();
            if (rig == null)
            {
                rig = inhabitant.gameObject.AddComponent<InhabitantRig>();
            }
            if (!rig.Bind(inhabitant, modelRoot, entry))
            {
                Destroy(rig);
                return null;
            }
            inhabitant.AttachRig(rig);
            return rig;
        }

        private bool Bind(Inhabitant inhabitant, GameObject modelRoot, ModelCatalog.Entry entry)
        {
            Owner = inhabitant;
            Model = modelRoot;
            Entry = entry;
            Skin = modelRoot.GetComponentInChildren<SkinnedMeshRenderer>(true);
            string headName = entry != null && !string.IsNullOrEmpty(entry.headBone) ? entry.headBone : DefaultHeadBone;
            Head = FindBone(headName);
            if (Head == null)
            {
                Debug.LogWarning($"[InhabitantRig] model '{entry?.id}' has no head bone '{headName}': procedural body instead.");
                return false;
            }
            Spine = FindBone(SpineBoneName);
            UpperArmLeft = FindBone(UpperArmLeftName);
            LowerArmLeft = FindBone(LowerArmLeftName);
            UpperArmRight = FindBone(UpperArmRightName);
            LowerArmRight = FindBone(LowerArmRightName);

            // The body frame the model is authored in: the inhabitant's Visual (its parent).
            if (inhabitant.Visual == null && modelRoot.transform.parent != null && modelRoot.transform.parent != inhabitant.transform)
            {
                inhabitant.Visual = modelRoot.transform.parent;
            }
            Transform frame = inhabitant.Visual != null ? inhabitant.Visual : inhabitant.transform;
            Quaternion facing = Quaternion.Euler(0f, frame.eulerAngles.y, 0f);
            Quaternion toFacing = Quaternion.Inverse(facing);

            SetUpAnimation(modelRoot);

            // Head: the bind pose rotation relative to the body facing. Fallback: the Idle pose just sampled.
            CalibratedFromBindPose = TryBindRotation(Skin, Head, out Quaternion headBind);
            headCalibration = toFacing * (CalibratedFromBindPose ? headBind : Head.rotation);
            headLocalForward = Quaternion.Inverse(headCalibration) * Vector3.forward;

            // Arms and spine: their Idle pose, the base of the absolute carry and bend targets.
            spineRest = Spine != null ? toFacing * Spine.rotation : Quaternion.identity;
            upperLeftRest = UpperArmLeft != null ? toFacing * UpperArmLeft.rotation : Quaternion.identity;
            lowerLeftRest = LowerArmLeft != null ? toFacing * LowerArmLeft.rotation : Quaternion.identity;
            upperRightRest = UpperArmRight != null ? toFacing * UpperArmRight.rotation : Quaternion.identity;
            lowerRightRest = LowerArmRight != null ? toFacing * LowerArmRight.rotation : Quaternion.identity;
            HeadRestHeight = Head.position.y - frame.position.y;
            // M4 seat fit: where the head bone stands in Idle, and the eyes above it with the head held as Apply holds it.
            Hips = FindBone(HipsBoneName);
            HeadRestLocal = toFacing * (Head.position - frame.position);
            Quaternion idleHead = Head.rotation;
            Head.rotation = facing * headCalibration;
            EyeAboveHead = EyePosition.y - Head.position.y;
            Head.rotation = idleHead;
            BuildBrows();
            var bones = new System.Collections.Generic.List<Transform>();
            foreach (Transform t in new[] { Spine, UpperArmLeft, LowerArmLeft, UpperArmRight, LowerArmRight, Head })
            {
                if (t != null)
                {
                    bones.Add(t);
                }
            }
            driven = bones.ToArray();
            drivenLocalRest = new Quaternion[driven.Length];
            for (int i = 0; i < driven.Length; i++)
            {
                drivenLocalRest[i] = driven[i].localRotation;
            }
            return true;
        }

        private void Update()
        {
            // Before the animation pass: the keyed bones get the clip's value, the unkeyed ones their rest.
            for (int i = 0; i < driven.Length; i++)
            {
                if (driven[i] != null)
                {
                    driven[i].localRotation = drivenLocalRest[i];
                }
            }
        }

        /// <summary>
        /// The brows hang under the head bone through a pivot that cancels the bone's scale (about 36: the armature's
        /// 100 times the model's fit) and its calibration, so the boxes are laid out in meters in the face frame,
        /// from the catalog's eye centroid. Built once per model; a rebind keeps them.
        /// </summary>
        private void BuildBrows()
        {
            if (BrowPivot != null && BrowPivot.parent == Head)
            {
                return;
            }
            Material dark = DarkestMaterial(Skin);
            float scale = Head.lossyScale.x;
            if (dark == null || scale < 1e-6f || Entry == null || Entry.eyeLocal == Vector3.zero)
            {
                Debug.LogWarning($"[InhabitantRig] model '{Entry?.id}': no brows (material {dark}, head scale {scale}, eye {Entry?.eyeLocal}).");
                return;
            }
            int layer = Skin.gameObject.layer;
            var pivot = new GameObject("Brows") { layer = layer };
            BrowPivot = pivot.transform;
            BrowPivot.SetParent(Head, false);
            BrowPivot.localPosition = Entry.eyeLocal;
            BrowPivot.localRotation = Quaternion.Inverse(headCalibration);
            BrowPivot.localScale = Vector3.one / scale;
            BrowLeft = MakeBrow("BrowL", -1f, dark, layer);
            BrowRight = MakeBrow("BrowR", 1f, dark, layer);
        }

        private Transform MakeBrow(string name, float side, Material material, int layer)
        {
            var at = new Vector3(side * BrowOffset.x, BrowOffset.y, BrowOffset.z);
            GameObject brow = PrimitiveKit.Box(BrowPivot, name, at, BrowSize, material, layer, false);
            brow.GetComponent<MeshRenderer>().shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            return brow.transform;
        }

        /// <summary>The darkest material already on the skin (the merged near-black of eyes and shoes).</summary>
        private static Material DarkestMaterial(SkinnedMeshRenderer skin)
        {
            Material best = null;
            float bestLuma = float.MaxValue;
            if (skin == null)
            {
                return null;
            }
            foreach (Material m in skin.sharedMaterials)
            {
                if (m == null)
                {
                    continue;
                }
                Color c = m.HasProperty("_BaseColor") ? m.GetColor("_BaseColor") : m.color;
                float luma = 0.2126f * c.r + 0.7152f * c.g + 0.0722f * c.b;
                if (luma < bestLuma)
                {
                    bestLuma = luma;
                    best = m;
                }
            }
            return best;
        }

        private void PoseBrows(float frown, float startled)
        {
            if (BrowLeft == null || BrowRight == null)
            {
                return;
            }
            float y = BrowOffset.y - BrowFrownDrop * frown + 0.008f * startled;
            float tilt = Mathf.Lerp(BrowFlatDegrees, BrowFrownDegrees, frown) + 10f * startled;
            // Left brow on -x: a negative roll lowers its inner (+x) end; the right brow mirrors it.
            BrowLeft.localPosition = new Vector3(-BrowOffset.x, y, BrowOffset.z);
            BrowLeft.localRotation = Quaternion.Euler(0f, 0f, tilt);
            BrowRight.localPosition = new Vector3(BrowOffset.x, y, BrowOffset.z);
            BrowRight.localRotation = Quaternion.Euler(0f, 0f, -tilt);
        }

        private void SetUpAnimation(GameObject modelRoot)
        {
            Animation = modelRoot.GetComponent<Animation>();
            if (Animation == null)
            {
                Animation = modelRoot.GetComponentInChildren<Animation>(true);
            }
            IdleClipName = WalkClipName = JumpClipName = null;
            SitClipName = StandClipName = null;
            CurrentClip = Clip.None;
            if (Animation == null)
            {
                Debug.LogWarning($"[InhabitantRig] model '{Entry?.id}' has no Animation component: the head still follows the routine.");
                return;
            }
            Animation.playAutomatically = false;
            Animation.cullingType = AnimationCullingType.AlwaysAnimate;
            Animation.Stop();
            foreach (AnimationState state in Animation)
            {
                string n = state.name;
                if (IdleClipName == null && n.EndsWith(IdleSuffix, StringComparison.Ordinal))
                {
                    IdleClipName = n;
                }
                else if (WalkClipName == null && n.EndsWith(WalkSuffix, StringComparison.Ordinal))
                {
                    WalkClipName = n;
                }
                else if (JumpClipName == null && n.EndsWith(JumpSuffix, StringComparison.Ordinal))
                {
                    JumpClipName = n;
                }
                else if (SitClipName == null && n.EndsWith(SitSuffix, StringComparison.Ordinal))
                {
                    SitClipName = n;
                }
                else if (StandClipName == null && n.EndsWith(StandSuffix, StringComparison.Ordinal))
                {
                    StandClipName = n;
                }
            }
            // M4: sitting down and standing up each play once, then hold their last pose.
            if (SitState != null)
            {
                SitState.wrapMode = WrapMode.ClampForever;
            }
            if (StandState != null)
            {
                StandState.wrapMode = WrapMode.ClampForever;
            }
            if (IdleClipName == null || WalkClipName == null || JumpClipName == null)
            {
                Debug.LogWarning($"[InhabitantRig] model '{Entry?.id}' misses a clip (Idle {IdleClipName}, Walk {WalkClipName}, Jump {JumpClipName}).");
            }
            if (IdleState != null)
            {
                IdleState.wrapMode = WrapMode.Loop;
            }
            if (WalkState != null)
            {
                WalkState.wrapMode = WrapMode.Loop;
            }
            if (JumpState != null)
            {
                JumpState.wrapMode = WrapMode.ClampForever;
            }
            AnimationState idle = IdleState;
            if (idle != null)
            {
                // Start in Idle, sampled now: the arm and spine rests are measured on this pose.
                Animation.clip = idle.clip;
                Animation.Play(idle.name);
                idle.time = 0f;
                Animation.Sample();
                CurrentClip = Clip.Idle;
            }
        }

        /// <summary>
        /// One frame of the rig, called by <see cref="Inhabitant"/> in LateUpdate after the animation was sampled
        /// and the Visual placed at the interpolated pose. Every bone it touches is set in world space, absolutely.
        /// </summary>
        internal void Apply(float bodyYaw, float eyeYaw, RoutineActivity activity, float tilt, float carry, float bend,
            float frown, float startled, float gaitCycles, bool isPaused)
        {
            Apply(bodyYaw, eyeYaw, activity, tilt, carry, bend, frown, startled, gaitCycles, isPaused, false, Tuning.EyeHeight, 0f);
        }

        /// <summary>
        /// M4: the same frame with the routine's sitting state. <paramref name="seated"/> is
        /// <see cref="InhabitantRoutine.IsSitting"/>, <paramref name="eyeHeight"/> the interpolated eye height and
        /// <paramref name="pratfall"/> the pratfall pose weight. The seat fit and the pratfall move the visual before any
        /// bone is set absolutely, so the head still looks exactly along the eye forward.
        /// </summary>
        internal void Apply(float bodyYaw, float eyeYaw, RoutineActivity activity, float tilt, float carry, float bend,
            float frown, float startled, float gaitCycles, bool isPaused, bool seated, float eyeHeight, float pratfall)
        {
            if (Head == null)
            {
                return;
            }
            bool seatedPose = seated || activity == RoutineActivity.Sitting || activity == RoutineActivity.StandingUp
                || activity == RoutineActivity.Pratfall;
            UpdateClip(activity, seatedPose, gaitCycles, isPaused);
            Quaternion facing = Quaternion.Euler(0f, bodyYaw, 0f);
            FitSeat(facing, seatedPose, eyeHeight, pratfall);

            // Parents first: the spine moves the arms and the head.
            if (Spine != null && bend > 0f)
            {
                Quaternion bent = facing * Quaternion.AngleAxis(BendDegrees, Vector3.right) * spineRest;
                Spine.rotation = Quaternion.Slerp(Spine.rotation, bent, bend);
            }
            if (carry > 0f)
            {
                float down = BendDegrees * bend;
                PoseArm(UpperArmLeft, upperLeftRest, CarryUpperArmPitch + down, -CarryArmSplay, facing, carry);
                PoseArm(LowerArmLeft, lowerLeftRest, CarryLowerArmPitch + down, 0.5f * CarryArmSplay, facing, carry);
                PoseArm(UpperArmRight, upperRightRest, CarryUpperArmPitch + down, CarryArmSplay, facing, carry);
                PoseArm(LowerArmRight, lowerRightRest, CarryLowerArmPitch + down, -0.5f * CarryArmSplay, facing, carry);
            }

            // The head: absolute, so the clip's head motion never leaks into where the inhabitant looks.
            Tilt = Mathf.Clamp01(tilt);
            Quaternion roll = Quaternion.AngleAxis(TelegraphRollDegrees * Tilt, headLocalForward);
            Head.rotation = Quaternion.Euler(0f, eyeYaw, 0f) * headCalibration * roll; // MUTATION:HEAD
            PoseBrows(frown, startled);
        }

        /// <summary>Where a marker floating <paramref name="height"/> meters above the feet goes: above the head bone.</summary>
        internal Vector3 MarkerPosition(float height)
        {
            return Head.position + Vector3.up * (height - HeadRestHeight);
        }

        /// <summary>
        /// M4: while seated, standing up or with the eye still low, the visual moves so the head bone stands where it
        /// stands in Idle, at <paramref name="eyeHeight"/> minus the eyes' height over it: the model's eyes are then at the
        /// routine's eye whatever the clip does. A pratfall then drops the body to the floor and tilts it back around
        /// the hips (the legs fly up). Standing, nothing moves: the M3 pose is untouched.
        /// </summary>
        private void FitSeat(Quaternion facing, bool seatedPose, float eyeHeight, float pratfall)
        {
            SeatOffset = Vector3.zero;
            Transform frame = Owner != null && Owner.Visual != null ? Owner.Visual : null;
            bool standClipRunning = CurrentClip == Clip.Stand && StandState != null && StandState.time < StandState.length;
            SeatFitActive = frame != null
                && (seatedPose || CurrentClip == Clip.Sit || standClipRunning || eyeHeight < Tuning.EyeHeight - 1e-3f);
            if (!SeatFitActive)
            {
                return;
            }
            Vector3 root = frame.position;
            Vector3 rest = facing * new Vector3(HeadRestLocal.x, 0f, HeadRestLocal.z);
            Vector3 target = root + rest + Vector3.up * (eyeHeight - EyeAboveHead);
            Vector3 offset = target - Head.position;
            frame.position += offset;
            float p = Mathf.Clamp01(pratfall);
            if (p > 0f)
            {
                Vector3 drop = Vector3.down * (PratfallDrop * p);
                frame.position += drop;
                offset += drop;
                if (Hips != null)
                {
                    // Leaning back: a negative angle around the body's right axis lifts the front (the knees and feet).
                    frame.RotateAround(Hips.position, facing * Vector3.right, -PratfallPitchDegrees * p);
                }
            }
            SeatOffset = offset;
        }

        private void UpdateClip(RoutineActivity activity, bool seatedPose, float gaitCycles, bool isPaused)
        {
            if (Animation == null)
            {
                return;
            }
            Clip target;
            if (activity == RoutineActivity.StandingUp)
            {
                target = Clip.Stand;
            }
            else if (seatedPose)
            {
                // Seated, whatever the routine does with its head (telegraph, glances, an alert look), and the pratfall.
                target = Clip.Sit;
            }
            else
            {
                target = ActivityClip(activity);
            }
            ApplyClip(target, activity, gaitCycles, isPaused);
        }

        private Clip ActivityClip(RoutineActivity activity)
        {
            Clip target;
            switch (activity)
            {
                case RoutineActivity.Walking:
                case RoutineActivity.Carrying:
                    target = Clip.Walk;
                    break;
                case RoutineActivity.Startled:
                    target = Clip.Jump;
                    break;
                case RoutineActivity.TurningBody:
                case RoutineActivity.TurningHead:
                    // A corner turn between two walk segments keeps the stride (no fade down and back up).
                    target = CurrentClip == Clip.Walk ? Clip.Walk : Clip.Idle;
                    break;
                default:
                    // Idle, Waiting, Telegraph, Looking, Pinned, turns, and PickingUp/PuttingDown (plus the bend).
                    target = Clip.Idle;
                    break;
            }
            return target;
        }

        private void ApplyClip(Clip target, RoutineActivity activity, float gaitCycles, bool isPaused)
        {
            string name = NameOf(target);
            if (name == null)
            {
                // A missing clip (a model without "_Sitting"): Idle, lowered by the seat fit.
                target = Clip.Idle;
                name = IdleClipName;
            }
            AnimationState walk = WalkState;
            float cycle = gaitCycles - Mathf.Floor(gaitCycles);
            if (name != null && target != CurrentClip)
            {
                if (target == Clip.Jump || target == Clip.Sit || target == Clip.Stand)
                {
                    // Once, then held (ClampForever): a new startle starts the hop over, a new sitting sits down again.
                    StateOf(name).time = 0f;
                }
                else if (target == Clip.Walk && walk != null)
                {
                    walk.normalizedTime = cycle;
                }
                Animation.CrossFade(name, CrossFadeSeconds);
                CurrentClip = target;
            }

            float walkSpeed = 0f;
            if (walk != null && walk.length > 0f)
            {
                // Clip cycles per second = meters per second / meters per cycle.
                float metersPerSecond = activity == RoutineActivity.Carrying ? Tuning.CarrySpeed : Tuning.WalkSpeed;
                walkSpeed = metersPerSecond / WalkCycleMeters * walk.length;
            }
            foreach (AnimationState state in Animation)
            {
                state.speed = isPaused ? 0f : (state == walk ? walkSpeed : 1f);
            }
            if (!isPaused && CurrentClip == Clip.Walk && walk != null)
            {
                // Slave the visible stride to the fixed step gait: footsteps land on foot contacts.
                walk.normalizedTime = cycle;
            }
        }

        private static void PoseArm(Transform bone, Quaternion rest, float pitch, float yaw, Quaternion facing, float weight)
        {
            if (bone == null)
            {
                return;
            }
            // Blender bones point along +Y: turn the rest pose so the bone points along the target direction.
            Vector3 direction = Quaternion.Euler(pitch, yaw, 0f) * Vector3.forward;
            Quaternion target = facing * Quaternion.FromToRotation(rest * Vector3.up, direction) * rest;
            bone.rotation = Quaternion.Slerp(bone.rotation, target, Mathf.Clamp01(weight));
        }

        private string NameOf(Clip clip)
        {
            switch (clip)
            {
                case Clip.Idle:
                    return IdleClipName;
                case Clip.Walk:
                    return WalkClipName;
                case Clip.Jump:
                    return JumpClipName;
                case Clip.Sit:
                    return SitClipName;
                case Clip.Stand:
                    return StandClipName;
                default:
                    return null;
            }
        }

        private AnimationState StateOf(string name)
        {
            return Animation != null && name != null ? Animation[name] : null;
        }

        private Transform FindBone(string boneName)
        {
            if (Skin != null)
            {
                foreach (Transform bone in Skin.bones)
                {
                    if (bone != null && bone.name == boneName)
                    {
                        return bone;
                    }
                }
            }
            return Model != null ? FindDeep(Model.transform, boneName) : null;
        }

        private static Transform FindDeep(Transform root, string boneName)
        {
            if (root.name == boneName)
            {
                return root;
            }
            for (int i = 0; i < root.childCount; i++)
            {
                Transform found = FindDeep(root.GetChild(i), boneName);
                if (found != null)
                {
                    return found;
                }
            }
            return null;
        }

        /// <summary>
        /// The world rotation <paramref name="bone"/> had in the bind pose, placed where the skin is now:
        /// bindposes[i] = bone.worldToLocal * skin.localToWorld at bind time (scale free: built from two axes).
        /// </summary>
        private static bool TryBindRotation(SkinnedMeshRenderer skin, Transform bone, out Quaternion rotation)
        {
            rotation = Quaternion.identity;
            if (skin == null || skin.sharedMesh == null || bone == null)
            {
                return false;
            }
            int index = Array.IndexOf(skin.bones, bone);
            Matrix4x4[] bindposes = skin.sharedMesh.bindposes;
            if (index < 0 || index >= bindposes.Length)
            {
                return false;
            }
            Matrix4x4 world = skin.transform.localToWorldMatrix * bindposes[index].inverse;
            Vector3 forward = world.GetColumn(2);
            Vector3 up = world.GetColumn(1);
            if (forward.sqrMagnitude < 1e-12f || up.sqrMagnitude < 1e-12f)
            {
                return false;
            }
            rotation = Quaternion.LookRotation(forward, up);
            return true;
        }
    }
}
