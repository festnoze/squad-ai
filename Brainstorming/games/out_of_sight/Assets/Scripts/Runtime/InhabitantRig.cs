using System;
using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
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
    ///   in Update, before the animation: an override never outlives its frame. (Since M4.2 the completed clips key
    ///   them all; the reset stays for a model whose clips key none of them.)
    /// - <b>Brows</b> (M3.1). Two small boxes on the head bone frown while investigating or carrying (pillar 4's comic
    ///   beat), with the model's own near-black material: no new material.
    /// - <b>Pause.</b> While <see cref="GamePause.IsPaused"/> every clip runs at speed 0.
    /// - <b>Sitting</b> (M4, docs/CONTRACT_M4.md 3). While the routine is seated the rig plays "_Sitting" (once, then
    ///   held), "_Standing" while it stands up, and Idle when the model lacks the clip. The family's sitting pose is a
    ///   high perch (eyes at 1.31 m, hips 0.26 m back), so a seat fit moves the whole visual until the head bone stands
    ///   where the standing head would be, at the routine's eye height: the eyes are at 1.15 m on a seat and the
    ///   hips land over the seat. A pratfall sits on nothing, then drops to the floor tilting back.
    /// - <b>Feet</b> (M4.2). The family's rig is an IK rig baked to FK: Foot.L and Foot.R hang under the root bone, not
    ///   under the shins, and each clip puts them where its shins end. The clips key different bones ("_Idle" keys no foot,
    ///   nor Body's rotation, the Torso, the Head or the fingers; the woman's not even the Neck or the right arm), and
    ///   Legacy Animation leaves an unkeyed bone where the last clip put it: after a walk, Idle bent the legs back to
    ///   its stance while the feet stayed mid-stride, and the ankles (skinned to both the shin and the foot) tore by
    ///   0.2 to 0.46 m. So Attach replaces every clip the rig plays by a copy that also holds, as a constant at the
    ///   model's rest pose, every bone property another of them keys (<see cref="CompleteClips"/>): every state writes
    ///   the same bones, every cross fade blends them. While the Jump plays, the feet are also put on the shin tips: at
    ///   the top of the hop the clip's legs fall 0.06 m short of its feet.
    ///
    /// - <b>Pets</b> (M5, docs/CONTRACT_M5_v3.md 15.5). A catalog entry of kind "pet" (the Husky) names its Idle and Walk
    ///   clips exactly; it has no Jump (Startled plays Idle), no sitting, no carry pose, no brows, no seat fit. Its head bone
    ///   follows the eye yaw like a human's, its stride is <see cref="Tuning.DogWalkCycleMeters"/>, and
    ///   <see cref="CompleteClips"/> completes its two clips too (its IK feet hang under the armature like the humans').
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
        private static readonly Vector3 BrowSize = new Vector3(0.033f, 0.007f, 0.006f);   // Tuning.RigBrowSize
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
        /// <summary>GRIP: the palm bones (at the wrists; the fingers hang under them), the end of the arm IK.</summary>
        public const string PalmLeftName = "Palm.L";
        public const string PalmRightName = "Palm.R";
        /// <summary>GRIP: the pet's neck chain, root first (the Husky's AnimalArmature), bent by the bite.</summary>
        public static readonly string[] NeckNames = { "Neck1", "Neck2", "Neck3" };

        /// <summary>M4.2: the foot bones (children of the root bone in this IK rig) and the tips of the shins they belong on.</summary>
        public const string FootLeftName = "Foot.L";
        public const string FootRightName = "Foot.R";
        public const string ShinTipLeftName = "LowerLeg.L_end";
        public const string ShinTipRightName = "LowerLeg.R_end";

        // M4.2: a pose no clip keys a bone to, for finding which properties a clip keys (CompleteClips).
        private static readonly Vector3 SentinelPosition = new Vector3(-917.3f, 433.1f, 271.9f);
        private static readonly Quaternion SentinelRotation = Quaternion.Euler(41.7f, -133.9f, 77.3f);

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

        /// <summary>GRIP: the palm bones (null when the model lacks them: no hand grip).</summary>
        public Transform PalmLeft { get; private set; }
        public Transform PalmRight { get; private set; }

        /// <summary>M3.1: the brow boxes (children of <see cref="BrowPivot"/>, itself a child of the head bone).</summary>
        public Transform BrowLeft { get; private set; }
        public Transform BrowRight { get; private set; }

        /// <summary>The face frame on the head bone: origin at the eyes, meters, x right, y up, z forward.</summary>
        public Transform BrowPivot { get; private set; }

        /// <summary>True when the head textures have been applied to the skinned mesh.</summary>
        public bool HasPaintedHead { get; private set; }

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

        /// <summary>
        /// M4.2: how many bone properties (a bone's position or its rotation, in one clip) Attach added to the played clips
        /// so they all key the same ones. 0 means the clips already did.
        /// </summary>
        public int CompletedProperties { get; private set; }

        /// <summary>M4.2: the foot bones and the shin tips (null when the model lacks them).</summary>
        public Transform FootLeft { get; private set; }
        public Transform FootRight { get; private set; }
        public Transform ShinTipLeft { get; private set; }
        public Transform ShinTipRight { get; private set; }

        /// <summary>The weight (0 to 1) of the telegraph roll applied to the head this frame.</summary>
        public float Tilt { get; private set; }

        /// <summary>True when the head calibration came from the skin's bindposes (false: from the Idle pose).</summary>
        public bool CalibratedFromBindPose { get; private set; }

        /// <summary>Height of the head bone above the feet in the Idle pose (m), measured once at Attach.</summary>
        public float HeadRestHeight { get; private set; }

        /// <summary>Meters walked per Walk clip cycle: the gait phase advances by distance / this. M5: a pet's own stride.</summary>
        public float WalkCycleDistance => IsPet ? Tuning.DogWalkCycleMeters : WalkCycleMeters;

        /// <summary>Normalized clip time of the first foot contact; the second one is half a cycle later.</summary>
        public float FootContactPhase => IsPet ? Tuning.DogFootContactCycle : FootContactCycle;

        /// <summary>M5: the model is a pet (its catalog entry's kind): Idle and Walk only, no brows, no seat fit.</summary>
        public bool IsPet => Entry != null && Entry.IsPet;

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
        // M4.2: the clip copies CompleteClips made, destroyed with the rig.
        private readonly List<AnimationClip> completedClips = new List<AnimationClip>();

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
            FootLeft = FindBone(FootLeftName);
            FootRight = FindBone(FootRightName);
            ShinTipLeft = FindBone(ShinTipLeftName);
            ShinTipRight = FindBone(ShinTipRightName);

            // The body frame the model is authored in: the inhabitant's Visual (its parent).
            if (inhabitant.Visual == null && modelRoot.transform.parent != null && modelRoot.transform.parent != inhabitant.transform)
            {
                inhabitant.Visual = modelRoot.transform.parent;
            }
            Transform frame = inhabitant.Visual != null ? inhabitant.Visual : inhabitant.transform;
            Quaternion facing = Quaternion.Euler(0f, frame.eulerAngles.y, 0f);
            Quaternion toFacing = Quaternion.Inverse(facing);

            SetUpAnimation(modelRoot);
            if (entry != null && entry.IsPet)
            {
                PetPose pose = PetPose.Find(modelRoot.transform, facing);
                petPose = pose.HasBones ? pose : null;
            }
            // GRIP: the palms (human hands on the carried furniture), the dog's neck chain (its head lowered to the bite).
            PalmLeft = FindBone(PalmLeftName);
            PalmRight = FindBone(PalmRightName);

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
            MeasureGrip(frame, toFacing);
            // M5: a pet never sits, and has no face for brows.
            // M4 seat fit: where the head bone stands in Idle, and the eyes above it with the head held as Apply holds it.
            Hips = FindBone(HipsBoneName);
            HeadRestLocal = toFacing * (Head.position - frame.position);
            Quaternion idleHead = Head.rotation;
            Head.rotation = facing * headCalibration;
            EyeAboveHead = EyePosition.y - Head.position.y;
            Head.rotation = idleHead;
            if (!IsPet)
            {
                BuildBrows();
                // M7 faces and clothes (CharacterLook): never at the cost of the rig.
                try
                {
                    CharacterLook.Apply(this);
                }
                catch (Exception e)
                {
                    Debug.LogError($"[InhabitantRig] model '{entry?.id}': CharacterLook failed: {e}");
                }
            }
            var bones = new System.Collections.Generic.List<Transform>();
            foreach (Transform t in new[] { Spine, UpperArmLeft, LowerArmLeft, UpperArmRight, LowerArmRight, Head, PalmLeft, PalmRight })
            {
                if (t != null)
                {
                    bones.Add(t);
                }
            }
            // GRIP: the neck bones the bite bends.
            for (int i = 0; neckBones != null && i < neckBones.Length; i++)
            {
                bones.Add(neckBones[i]);
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

        /// <summary>The eyebrows are part of the continuous head artwork. Keep the rig transforms for expression timing.</summary>
        internal void SetPaintedHead()
        {
            HasPaintedHead = true;
            foreach (Transform brow in new[] { BrowLeft, BrowRight })
            {
                if (brow != null && brow.TryGetComponent(out Renderer renderer))
                {
                    renderer.forceRenderingOff = true;
                }
            }
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
            bool pet = IsPet;
            foreach (AnimationState state in Animation)
            {
                string n = state.name;
                if (pet)
                {
                    // M5: a pet's clip map names its clips exactly (the Husky also stores "AnimalArmature|Idle" and so on).
                    if (IdleClipName == null && n == Entry.idleClip)
                    {
                        IdleClipName = n;
                    }
                    else if (WalkClipName == null && n == Entry.walkClip)
                    {
                        WalkClipName = n;
                    }
                    continue;
                }
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
            // M4.2: before any state is configured or sampled (the copies replace the states).
            CompleteClips(); // MUTATION:FEET
            // M4: sitting down and standing up each play once, then hold their last pose.
            if (SitState != null)
            {
                SitState.wrapMode = WrapMode.ClampForever;
            }
            if (StandState != null)
            {
                StandState.wrapMode = WrapMode.ClampForever;
            }
            if (IdleClipName == null || WalkClipName == null || (JumpClipName == null && !pet))
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
        /// M4.2: makes every clip the rig plays (Idle, Walk, Jump, Sitting, Standing) key the same bone properties. Legacy
        /// Animation writes only what a clip keys, so a property one clip keys and another does not keeps, under the
        /// second, the value the first left: the feet of this IK rig stayed mid-stride under Idle (see the class summary).
        ///
        /// Which properties a clip keys is read from the clip itself: every bone is put in a sentinel pose, the clip is
        /// sampled, and what moved off the sentinel is keyed. A clip that misses a property another one keys is replaced
        /// (same state name) by a copy holding it as a constant at the model's rest pose: the prefab's local values, the
        /// pose the clips were authored over (with them, Idle stands each foot on its shin tip within 7 mm). Legacy clips
        /// accept new curves at run time, in a player too. The copies die with the rig.
        /// </summary>
        private void CompleteClips()
        {
            CompletedProperties = 0;
            if (Animation == null || Skin == null || Model == null)
            {
                return;
            }
            var names = new List<string>();
            foreach (string n in new[] { IdleClipName, WalkClipName, JumpClipName, SitClipName, StandClipName })
            {
                if (n != null && !names.Contains(n) && StateOf(n) != null && StateOf(n).clip != null)
                {
                    names.Add(n);
                }
            }
            Transform animationRoot = Animation.transform;
            var bones = new List<Transform>();
            var paths = new List<string>();
            foreach (Transform bone in Skin.bones)
            {
                string path = bone != null ? PathFrom(animationRoot, bone) : null;
                if (!string.IsNullOrEmpty(path) && !bones.Contains(bone))
                {
                    bones.Add(bone);
                    paths.Add(path);
                }
            }
            if (names.Count < 2 || bones.Count == 0)
            {
                return;
            }

            // The rest pose: the prefab's local values (a rebind may find the live bones posed), else the live ones.
            Transform prefabRoot = Entry != null && Entry.prefab != null ? Entry.prefab.transform : null;
            var restPosition = new Vector3[bones.Count];
            var restRotation = new Quaternion[bones.Count];
            for (int b = 0; b < bones.Count; b++)
            {
                string modelPath = PathFrom(Model.transform, bones[b]);
                Transform source = prefabRoot != null && !string.IsNullOrEmpty(modelPath) ? prefabRoot.Find(modelPath) : null;
                if (source == null)
                {
                    source = bones[b];
                }
                restPosition[b] = source.localPosition;
                restRotation[b] = source.localRotation;
            }

            // What each clip keys: sampling writes only its keyed properties over the sentinel pose.
            var keyedPosition = new bool[names.Count, bones.Count];
            var keyedRotation = new bool[names.Count, bones.Count];
            var anyPosition = new bool[bones.Count];
            var anyRotation = new bool[bones.Count];
            for (int c = 0; c < names.Count; c++)
            {
                foreach (Transform bone in bones)
                {
                    bone.localPosition = SentinelPosition;
                    bone.localRotation = SentinelRotation;
                }
                StateOf(names[c]).clip.SampleAnimation(Animation.gameObject, 0f);
                for (int b = 0; b < bones.Count; b++)
                {
                    keyedPosition[c, b] = (bones[b].localPosition - SentinelPosition).sqrMagnitude > 1e-6f;
                    keyedRotation[c, b] = Quaternion.Angle(bones[b].localRotation, SentinelRotation) > 0.01f;
                    anyPosition[b] |= keyedPosition[c, b];
                    anyRotation[b] |= keyedRotation[c, b];
                }
            }
            for (int b = 0; b < bones.Count; b++)
            {
                bones[b].localPosition = restPosition[b];
                bones[b].localRotation = restRotation[b];
            }

            // A copy of each clip that misses a property, holding it at rest.
            for (int c = 0; c < names.Count; c++)
            {
                AnimationClip source = StateOf(names[c]).clip;
                AnimationClip copy = null;
                float end = Mathf.Max(source.length, 1e-3f);
                for (int b = 0; b < bones.Count; b++)
                {
                    bool position = anyPosition[b] && !keyedPosition[c, b];
                    bool rotation = anyRotation[b] && !keyedRotation[c, b];
                    if (!position && !rotation)
                    {
                        continue;
                    }
                    if (copy == null)
                    {
                        copy = Instantiate(source);
                        copy.name = source.name;
                    }
                    if (position)
                    {
                        Vector3 p = restPosition[b];
                        copy.SetCurve(paths[b], typeof(Transform), "localPosition.x", AnimationCurve.Constant(0f, end, p.x));
                        copy.SetCurve(paths[b], typeof(Transform), "localPosition.y", AnimationCurve.Constant(0f, end, p.y));
                        copy.SetCurve(paths[b], typeof(Transform), "localPosition.z", AnimationCurve.Constant(0f, end, p.z));
                        CompletedProperties++;
                    }
                    if (rotation)
                    {
                        Quaternion q = restRotation[b];
                        copy.SetCurve(paths[b], typeof(Transform), "localRotation.x", AnimationCurve.Constant(0f, end, q.x));
                        copy.SetCurve(paths[b], typeof(Transform), "localRotation.y", AnimationCurve.Constant(0f, end, q.y));
                        copy.SetCurve(paths[b], typeof(Transform), "localRotation.z", AnimationCurve.Constant(0f, end, q.z));
                        copy.SetCurve(paths[b], typeof(Transform), "localRotation.w", AnimationCurve.Constant(0f, end, q.w));
                        CompletedProperties++;
                    }
                }
                if (copy != null)
                {
                    copy.EnsureQuaternionContinuity();
                    Animation.RemoveClip(names[c]);
                    Animation.AddClip(copy, names[c]);
                    completedClips.Add(copy);
                }
            }
        }

        /// <summary>The path of <paramref name="t"/> under <paramref name="root"/> ("" for the root, null when not under it).</summary>
        private static string PathFrom(Transform root, Transform t)
        {
            var parts = new List<string>();
            for (Transform c = t; c != null; c = c.parent)
            {
                if (c == root)
                {
                    parts.Reverse();
                    return string.Join("/", parts);
                }
                parts.Add(c.name);
            }
            return null;
        }

        private void OnDestroy()
        {
            foreach (AnimationClip clip in completedClips)
            {
                if (clip == null)
                {
                    continue;
                }
                if (Application.isPlaying)
                {
                    Destroy(clip);
                }
                else
                {
                    DestroyImmediate(clip);
                }
            }
            completedClips.Clear();
        }

        /// <summary>M4.2: puts a foot bone on the tip of its shin (both in world space; the foot hangs under the root bone).</summary>
        private static void PinFoot(Transform foot, Transform shinTip)
        {
            if (foot != null && shinTip != null)
            {
                foot.position = shinTip.position;
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
            if (CurrentClip == Clip.Jump)
            {
                // M4.2: at the top of the hop the Jump's legs fall 0.06 m short of its feet. Every clip keys the feet, so
                // the next animation pass puts them back where the clip wants them: the pin never outlives its frame.
                PinFoot(FootLeft, ShinTipLeft);
                PinFoot(FootRight, ShinTipRight);
            }

            // Parents first: the spine moves the arms and the head.
            if (Spine != null && bend > 0f)
            {
                Quaternion bent = facing * Quaternion.AngleAxis(BendDegrees, Vector3.right) * spineRest;
                Spine.rotation = Quaternion.Slerp(Spine.rotation, bent, bend);
            }
            float hands = Mathf.Clamp01(HandGripWeight);
            if (Spine != null && hands > 0f && handLean > 0f)
            {
                // GRIP: the lean over a low furniture (the stool), never on top of the pick up's bend.
                Spine.rotation = Quaternion.AngleAxis(handLean * hands * (1f - Mathf.Clamp01(bend)), facing * Vector3.right) * Spine.rotation;
            }
            if (carry > 0f)
            {
                float down = BendDegrees * bend;
                PoseArm(UpperArmLeft, upperLeftRest, CarryUpperArmPitch + down, -CarryArmSplay, facing, carry);
                PoseArm(LowerArmLeft, lowerLeftRest, CarryLowerArmPitch + down, 0.5f * CarryArmSplay, facing, carry);
                PoseArm(UpperArmRight, upperRightRest, CarryUpperArmPitch + down, CarryArmSplay, facing, carry);
                PoseArm(LowerArmRight, lowerRightRest, CarryLowerArmPitch + down, -0.5f * CarryArmSplay, facing, carry);
            }
            if (hands > 0f)
            {
                // GRIP: from that carry pose, each arm reaches its wrist target on the furniture (two bone IK, the elbow out
                // and down) and the hand points its fingers over the surface.
                bool swap = armLeftSide > 0f;
                ReachArm(UpperArmLeft, LowerArmLeft, PalmLeft, swap ? rightWristTarget : leftWristTarget,
                    swap ? rightFingerTarget : leftFingerTarget, armLeftSide, facing, hands);
                ReachArm(UpperArmRight, LowerArmRight, PalmRight, swap ? leftWristTarget : rightWristTarget,
                    swap ? leftFingerTarget : rightFingerTarget, -armLeftSide, facing, hands);
            }
            // GRIP: the biting dog lowers its head onto the point it bites (the neck bent nose down, eased with the bite).
            float neck = neckBones != null ? GripNeck * Mathf.Clamp01(Bite) : 0f;
            if (neck > 0f)
            {
                BendNeck(neckBones, facing * Vector3.right, neck);
            }

            // The head: absolute, so the clip's head motion never leaks into where the inhabitant looks.
            Tilt = Mathf.Clamp01(tilt);
            Quaternion roll = Quaternion.AngleAxis(TelegraphRollDegrees * Tilt, headLocalForward);
            Head.rotation = Quaternion.Euler(0f, eyeYaw, 0f) * headCalibration * roll; // MUTATION:HEAD
            if (neck > 0f)
            {
                // GRIP: the muzzle follows the neck down (the bite's roll and dip then ride on it, PetPose).
                Head.rotation = Quaternion.AngleAxis(neck * Tuning.DogGripHeadFollow, Quaternion.Euler(0f, eyeYaw, 0f) * Vector3.right) * Head.rotation;
            }
            PoseBrows(frown, startled);
            // DOGBIG: the black Labrador's bigger head, its bite, hanging ears and low tail, after the head (all ride on it).
            if (petPose != null)
            {
                petPose.Bite = Bite;
                petPose.Apply(Quaternion.Euler(0f, eyeYaw, 0f), facing);
            }
        }

        // DOGBIG: the pet's head, ear, tail and jaw bones (null for a human, or a pet model without them).
        private PetPose petPose;

        /// <summary>DOGBIG v3: the bite pose's weight, 0 to 1, set by Inhabitant each frame (a pet only).</summary>
        public float Bite { get; set; }

        /// <summary>DOGBIG v3: true when the model has the bite's jaw joint.</summary>
        public bool HasJaw => petPose != null && petPose.HasJaw;

        /// <summary>
        /// DOGBIG: how far ahead of the body root the snout reaches, metres: the catalog's rest pose reach
        /// (ModelKit.ForwardReach), plus what the grown head (Tuning.DogHeadScale) adds ahead of the head bone.
        /// </summary>
        public float SnoutReach
        {
            get
            {
                float reach = ModelKit.ForwardReach(Entry);
                return petPose != null ? reach + (Tuning.DogHeadScale - 1f) * Mathf.Max(0f, reach - HeadRestLocal.z) : reach;
            }
        }

        // ----- GRIP (2026-11-22, presentation only): hands on the carried furniture, the dog's head lowered to its bite -----

        // The human hand grip set by Inhabitant each frame: its weight, the wrist targets and finger directions (world), the
        // spine's lean; which side of the body the ".L" arm hangs on (-1: the body's left, as expected).
        private float handLean;
        private Vector3 leftWristTarget;
        private Vector3 rightWristTarget;
        private Vector3 leftFingerTarget = Vector3.forward;
        private Vector3 rightFingerTarget = Vector3.forward;
        private float armLeftSide = -1f;
        // The pet's neck chain and, in its body plane (x forward, y up, metres from the feet, Idle pose), its base, its
        // segments up to the head bone and the snout tip ahead of the head bone (the grown head included).
        private Transform[] neckBones;
        private Vector2 neckBase;
        private Vector2[] neckSegments;
        private Vector2 snoutFromHead;

        /// <summary>GRIP: the weight of the human hand grip this frame, 0 to 1 (set by <see cref="SetHandGrip"/>).</summary>
        public float HandGripWeight { get; private set; }

        /// <summary>GRIP: the dog's neck bend for its bite, degrees (Inhabitant solves it; applied times <see cref="Bite"/>).</summary>
        public float GripNeck { get; set; }

        /// <summary>GRIP: true when the pet's neck chain was found (its head can be lowered to the bite).</summary>
        public bool HasNeck => neckBones != null;

        /// <summary>
        /// GRIP (Inhabitant, every frame): where the human's hands rest on the carried furniture this frame (wrists and finger
        /// directions in world space, the carrier's left and right), the lean of his spine, and the grip's weight (0: the
        /// plain carry pose).
        /// </summary>
        internal void SetHandGrip(float weight, Vector3 leftWrist, Vector3 rightWrist, Vector3 leftFingers, Vector3 rightFingers, float lean)
        {
            HandGripWeight = PalmLeft != null && PalmRight != null && UpperArmLeft != null && UpperArmRight != null
                && LowerArmLeft != null && LowerArmRight != null ? Mathf.Clamp01(weight) : 0f;
            leftWristTarget = leftWrist;
            rightWristTarget = rightWrist;
            leftFingerTarget = leftFingers;
            rightFingerTarget = rightFingers;
            handLean = lean;
        }

        /// <summary>
        /// GRIP: the neck bend (degrees) that brings the dog's snout tip down to <paramref name="targetHeight"/> metres above its
        /// feet (GripMath, from the Idle pose's neck chain), and how far ahead of its feet the tip then is. Without a neck
        /// chain: no bend, the DOGBIG snout reach.
        /// </summary>
        internal void SolveBite(float targetHeight, out float bend, out float tipForward)
        {
            if (neckBones == null)
            {
                bend = 0f;
                tipForward = SnoutReach;
                return;
            }
            bend = GripMath.SolveNeckBend(neckBase, neckSegments, snoutFromHead, Tuning.DogGripHeadFollow, targetHeight);
            tipForward = GripMath.Tip(neckBase, neckSegments, snoutFromHead, bend, Tuning.DogGripHeadFollow).x;
        }

        /// <summary>GRIP: the arm side and the pet's neck chain, measured once in the Idle pose (Bind).</summary>
        private void MeasureGrip(Transform frame, Quaternion toFacing)
        {
            if (UpperArmLeft != null)
            {
                float side = (toFacing * (UpperArmLeft.position - frame.position)).x;
                armLeftSide = side > 0f ? 1f : -1f;
            }
            neckBones = null;
            if (Entry == null || !Entry.IsPet)
            {
                return;
            }
            var chain = new Transform[NeckNames.Length];
            for (int i = 0; i < chain.Length; i++)
            {
                chain[i] = FindBone(NeckNames[i]);
                if (chain[i] == null)
                {
                    return;
                }
            }
            Vector2 Plane(Transform t)
            {
                Vector3 local = toFacing * (t.position - frame.position);
                return new Vector2(local.z, local.y);
            }
            neckBones = chain;
            neckBase = Plane(chain[0]);
            neckSegments = new Vector2[chain.Length];
            for (int i = 0; i < chain.Length; i++)
            {
                Transform next = i + 1 < chain.Length ? chain[i + 1] : Head;
                neckSegments[i] = Plane(next) - Plane(chain[i]);
            }
            // The tip ahead of the head bone: the catalog's rest reach (ModelKit.ForwardReach) less the head bone's, a little
            // below it (Tuning.DogSnoutDrop), grown with the head (PetPose scales it every frame).
            float headForward = Plane(Head).x;
            float grow = petPose != null ? Tuning.DogHeadScale : 1f;
            snoutFromHead = new Vector2(Mathf.Max(0f, ModelKit.ForwardReach(Entry) - headForward), -Tuning.DogSnoutDrop) * grow;
        }

        /// <summary>GRIP: one arm onto its wrist target (the elbow out to its side, down and back), then the hand's fingers.</summary>
        private static void ReachArm(Transform upper, Transform lower, Transform palm, Vector3 wrist, Vector3 fingers, float side,
            Quaternion facing, float weight)
        {
            Vector3 pole = facing * new Vector3(side, -0.7f, -0.4f);
            SolveArm(upper, lower, palm, wrist, pole, weight);
            AimBone(palm, fingers, weight);
        }

        /// <summary>
        /// GRIP: a two bone IK, swing only (each bone keeps its twist): <paramref name="upper"/> and <paramref name="lower"/> turn
        /// so <paramref name="end"/> reaches <paramref name="target"/> (or as close as the arm's length allows), the middle
        /// joint bending toward <paramref name="pole"/>; <paramref name="weight"/> blends from the pose they had.
        /// </summary>
        internal static void SolveArm(Transform upper, Transform lower, Transform end, Vector3 target, Vector3 pole, float weight)
        {
            if (upper == null || lower == null || end == null || weight <= 0f)
            {
                return;
            }
            Vector3 a = upper.position;
            Vector3 b = lower.position;
            Vector3 c = end.position;
            float la = (b - a).magnitude;
            float lb = (c - b).magnitude;
            Vector3 toTarget = target - a;
            float d = toTarget.magnitude;
            if (la < 1e-5f || lb < 1e-5f || d < 1e-5f)
            {
                return;
            }
            Vector3 n = toTarget / d;
            d = Mathf.Clamp(d, Mathf.Abs(la - lb) + 1e-4f, (la + lb) * 0.999f);
            Vector3 m = pole - Vector3.Dot(pole, n) * n;
            if (m.sqrMagnitude < 1e-8f)
            {
                m = Vector3.Cross(n, Vector3.right);
            }
            m.Normalize();
            float x = (la * la - lb * lb + d * d) / (2f * d);
            float h = Mathf.Sqrt(Mathf.Max(0f, la * la - x * x));
            Vector3 elbow = a + n * x + m * h;
            float w = Mathf.Clamp01(weight);
            upper.rotation = Quaternion.Slerp(upper.rotation, Quaternion.FromToRotation(b - a, elbow - a) * upper.rotation, w);
            b = lower.position;
            c = end.position;
            Vector3 reach = a + n * d;
            lower.rotation = Quaternion.Slerp(lower.rotation, Quaternion.FromToRotation(c - b, reach - b) * lower.rotation, w);
        }

        /// <summary>GRIP: turns <paramref name="bone"/> so its axis (+Y, the Blender bone direction) points along <paramref name="direction"/>.</summary>
        internal static void AimBone(Transform bone, Vector3 direction, float weight)
        {
            if (bone == null || direction.sqrMagnitude < 1e-8f || weight <= 0f)
            {
                return;
            }
            Quaternion aimed = Quaternion.FromToRotation(bone.up, direction.normalized) * bone.rotation;
            bone.rotation = Quaternion.Slerp(bone.rotation, aimed, Mathf.Clamp01(weight));
        }

        /// <summary>GRIP: bends a neck chain nose down by <paramref name="degrees"/> about <paramref name="right"/>, a share per bone
        /// (each child also turns with its parent: the first segment turns a third, the last all of it, as GripMath assumes).</summary>
        internal static void BendNeck(Transform[] chain, Vector3 right, float degrees)
        {
            if (chain == null || chain.Length == 0)
            {
                return;
            }
            Quaternion step = Quaternion.AngleAxis(degrees / chain.Length, right);
            foreach (Transform bone in chain)
            {
                if (bone != null)
                {
                    bone.rotation = step * bone.rotation;
                }
            }
        }

        /// <summary>
        /// GRIP: the neck chain of a pet model under <paramref name="model"/> in its current pose, in the body plane of
        /// <paramref name="frame"/> (for the title logo, which has no rig): false when a bone is missing.
        /// </summary>
        internal static bool NeckChain(Transform model, Transform frame, out Transform[] chain, out Transform head, out Vector2 basePoint,
            out Vector2[] segments)
        {
            chain = new Transform[NeckNames.Length];
            head = FindDeep(model, DefaultHeadBone);
            basePoint = Vector2.zero;
            segments = null;
            for (int i = 0; i < chain.Length; i++)
            {
                chain[i] = FindDeep(model, NeckNames[i]);
                if (chain[i] == null || head == null)
                {
                    return false;
                }
            }
            Quaternion toFrame = Quaternion.Inverse(Quaternion.Euler(0f, frame.eulerAngles.y, 0f));
            Vector2 Plane(Transform t)
            {
                Vector3 local = toFrame * (t.position - frame.position);
                return new Vector2(local.z, local.y);
            }
            basePoint = Plane(chain[0]);
            segments = new Vector2[chain.Length];
            for (int i = 0; i < chain.Length; i++)
            {
                Transform next = i + 1 < chain.Length ? chain[i + 1] : head;
                segments[i] = Plane(next) - Plane(chain[i]);
            }
            return true;
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
            // M5: the eye is "still low" against the model's own standing eye (a human's 1.6 m); a pet never sits.
            float standingEye = Entry != null ? Entry.TargetEye : Tuning.EyeHeight;
            SeatFitActive = frame != null && !IsPet
                && (seatedPose || CurrentClip == Clip.Sit || standClipRunning || eyeHeight < standingEye - 1e-3f);
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
                // Clip cycles per second = meters per second / meters per cycle. M5: the personality's own pace (the
                // default one is the M1 1.2 m/s); the stride itself stays slaved to the gait phase below.
                PersonalityDef personality = Owner != null && Owner.Routine != null ? Owner.Routine.Personality : null;
                float pace = personality != null && personality.WalkSpeed > 0f ? personality.WalkSpeed : Tuning.WalkSpeed;
                float metersPerSecond = activity == RoutineActivity.Carrying ? Tuning.CarrySpeed : pace;
                walkSpeed = metersPerSecond / WalkCycleDistance * walk.length;
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
