using System;
using System.Collections;
using System.Collections.Generic;
using System.Threading.Tasks;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.UI;
using Object = UnityEngine.Object;

namespace OutOfSight
{
    /// <summary>
    /// M7 title logo: the player's red chair seen at a three-quarter angle, with a short shadow cast by a high
    /// (about 11 am) sun, baked ONCE the first time the title page shows, then drawn above the title (it replaces the
    /// flat chair icon, kept as the fallback if the bake fails).
    ///
    /// - Isolation: a rig (the real level 1 chair model through ModelKit, or FurnitureKit's procedural chair) on an
    ///   unnamed layer (Tuning.TitleLogoLayer) that only the two logo cameras render, placed far sideways to the sun
    ///   (Tuning.TitleLogoRigDistance): beyond the main camera's far plane and outside its shadow cascades, and with
    ///   nothing between it and the sun. It lives for two frames, then the rig, cameras and render textures are destroyed:
    ///   nothing left in the scene for gameplay.
    /// - Lighting: the scene's own sun is the key light (no second directional light, which could take over as the main
    ///   light). The rig is rotated so that the sun arrives high and a little to one side (Tuning.TitleLogoSunElevation,
    ///   Tuning.TitleLogoSunHeading) in the rig's frame, so the chair's shading always matches its shadow; a small
    ///   range limited rim light sits behind it, and a warm spot from straight above lights the seat.
    /// - The pool of light: a soft warm disc on the ground, lit like a spot from above, centred between the chair's foot
    ///   and its shadow's tip and wide enough to hold the whole shadow (Tuning.TitleLogoPool*). An orthographic camera
    ///   maps pixels to the ground affinely, so the disc is an exact ellipse in perspective; it is brightest under the
    ///   chair, warms to amber and fades to nothing before the frame's edges, and a faint dither keeps its gradient free
    ///   of banding.
    /// - The shadow: a second camera renders the same chair through its view matrix times the projection onto the ground
    ///   along the sun, which is exactly the chair's shadow (its alpha is the mask). It darkens the pool's light, darkest
    ///   at the foot, fading and softening toward the tip. Composited on the CPU at twice the size and averaged down; this
    ///   never depends on the quality tier's shadow settings, so PC and Android get the same logo.
    /// - The loop (2026-11-20, reworked 2026-11-21: the game's premise in a few seconds): the bake keeps the layers in one
    ///   small atlas (the pool of light, the chair's shadow and the chair, cropped, and the dog: two baked walk frames and
    ///   their shadows), drawn by RawImages that share it (one batch). For most of the loop (Tuning.TitleLogoStillFraction,
    ///   at least 15 s) the chair stands perfectly still in the light; then the spot slides away to the left and dims, and
    ///   the chair, in the dark, sneaks off to the right in a few gentle hops (a soft lift, never deformed). The spot comes
    ///   back onto it where it now stands; caught, it gives one startled jump. Then the house dog (the game's Husky) trots in
    ///   from the frame's left edge, grabs the chair's edge in its mouth and walks backwards, tugging it home with a little
    ///   wobble, the light following, as the in-game dog now drags the furniture back itself
    ///   (docs/next/progress/DOGCARRY.md). The dog lets go, wags, turns round and trots out through the left edge, and the
    ///   still pose holds until the loop restarts (<see cref="Sample"/>).
    ///   GRIP (2026-11-22): the loops alternate. The dog's loop: it bites the chair's left back leg low, its head lowered (the
    ///   in-game grip, GripDef and GripMath), in two more baked frames. The next loop: a human (the level 1 man, at
    ///   Tuning.TitleLogoHumanScale) walks in from the left instead, rests his hands on the top rail of the chair's backrest
    ///   (the in-game hand grip and arm IK) and pulls it home walking backwards; he lets go, steps back, turns round and walks
    ///   out through the left edge. While he holds it, a baked picture of the pair (the chair and the human together, so his
    ///   hands lie on the rail and the backrest hides what it should) is drawn exactly over the chair's layer.
    ///   Since the camera is orthographic, a sideways move on the floor is a pure sideways move of a picture and of its
    ///   shadow's, and a hop is a small lift of the chair's picture over its shadow, which stays on the floor and shrinks
    ///   a little: the layers only slide, scale and swap between the dog's two frames. Per frame, a few RectTransform and
    ///   colour writes during the act, and none at all while the chair is still (no allocation, no render).
    /// </summary>
    public sealed class TitleLogo : MonoBehaviour
    {
        /// <summary>The logo's frame, placed by the menu: it draws the pool of light, under its children, the shadows, the
        /// chair and the dog (all hidden until the bake succeeds).</summary>
        public RawImage Image { get; private set; }

        /// <summary>The chair's shadow layer (a child of <see cref="Image"/>; null until the bake succeeds).</summary>
        public RawImage Shadow { get; private set; }

        /// <summary>The chair layer (a child of <see cref="Image"/>, pivoting at the chair's foot; null until the bake succeeds).</summary>
        public RawImage Chair { get; private set; }

        /// <summary>The dog layer (a child of <see cref="Image"/>, its frame swapped as it walks; null until the bake
        /// succeeds, and if the dog could not be baked: the chair then comes home on its own).</summary>
        public RawImage Dog { get; private set; }

        /// <summary>The dog's shadow layer (null without <see cref="Dog"/>).</summary>
        public RawImage DogShadow { get; private set; }

        /// <summary>GRIP: the human's walking layer (null until the bake succeeds, and if the human could not be baked: his
        /// loops then show the dog's).</summary>
        public RawImage Human { get; private set; }

        /// <summary>GRIP: the human and the chair together while he holds it, drawn exactly over <see cref="Chair"/> (null
        /// without <see cref="Human"/>).</summary>
        public RawImage HumanPair { get; private set; }

        /// <summary>GRIP: the human's shadow layer (null without <see cref="Human"/>).</summary>
        public RawImage HumanShadow { get; private set; }

        /// <summary>True once the logo is baked and shown.</summary>
        public bool Ready { get; private set; }

        /// <summary>The brightest lit floor pixel of the pool (no chair, no shadow), in frame pixels.</summary>
        public Vector2Int PoolPixel { get; private set; }

        /// <summary>The darkest shadow pixel on the floor (outside the chair), in frame pixels.</summary>
        public Vector2Int ShadowPixel { get; private set; }

        /// <summary>The pool's least light under any part of the shadow (0 when the shadow leaves the pool, 1 at its core).</summary>
        public float ShadowInPool { get; private set; }

        /// <summary>The loop's phase last applied, in [0, 2): the dog's loop, then (from 1) the human's; 0 and 1 are the starts
        /// of their still parts.</summary>
        public float Phase { get; private set; }

        /// <summary>The pose last applied to the layers.</summary>
        public Pose Current { get; private set; } = Rest;

        /// <summary>UI units per metre of the logo's floor (the chair's and the spot's offsets are in metres).</summary>
        public float UiPerMetre { get; private set; }

        /// <summary>One moment of the loop. The chair, the dog and the spot move sideways on the floor; the chair also hops
        /// (a lift of its picture, never a deformation); the dog walks (two frames), bobs, wags and turns.</summary>
        public struct Pose : IEquatable<Pose>
        {
            /// <summary>The chair's sideways offset on the floor, in metres (positive to the right).</summary>
            public float Chair;
            /// <summary>The chair's tilt, in degrees (positive tips its back to the left): only the dog's grab and the
            /// tug's wobble while it drags the chair.</summary>
            public float Lean;
            /// <summary>The spot's light on the floor and the chair: 1 in the full light, down to Tuning.TitleLogoSpotAway.</summary>
            public float Light;
            /// <summary>Where the pool of light is, sideways, in metres of floor (negative while it is away to the left).</summary>
            public float Spot;
            /// <summary>How high the chair's picture is lifted above its shadow (a hop, the startled jump, or the dog's low
            /// drag), in metres of the logo's frame.</summary>
            public float Hop;
            /// <summary>The dog's sideways offset on the floor from where it holds the chair on its mark, in metres (it holds
            /// the chair whenever Dog equals Chair; <see cref="DogEdge"/> is the frame's left edge, where it is hidden).</summary>
            public float Dog;
            /// <summary>The dog's opacity: 0 at the frame's left edge, 1 once it is well inside.</summary>
            public float DogAlpha;
            /// <summary>1 while the dog faces right (toward the chair, also while it walks backwards dragging it), -1 once it
            /// has turned round to leave.</summary>
            public float DogFacing;
            /// <summary>The dog's baked walk frame (0 or 1), from the distance it has walked.</summary>
            public int DogFrame;
            /// <summary>The dog's trotting bob, in metres of the logo's frame.</summary>
            public float DogHop;
            /// <summary>The dog's wag, a wiggle of its picture in degrees.</summary>
            public float DogWag;
            /// <summary>GRIP: the dog bites the chair (its head lowered to the left back leg: the two bite frames).</summary>
            public bool DogBite;
            /// <summary>GRIP: the human's sideways offset on the floor from where he holds the chair on its mark, in metres
            /// (<see cref="HumanEdge"/>: hidden at the frame's left edge).</summary>
            public float Human;
            /// <summary>GRIP: the human's opacity, 0 at the frame's left edge.</summary>
            public float HumanAlpha;
            /// <summary>GRIP: 1 while the human faces right (also while he walks backwards pulling the chair), -1 once he
            /// has turned round to leave.</summary>
            public float HumanFacing;
            /// <summary>GRIP: the human's baked walk frame (0 or 1), from the distance he has walked.</summary>
            public int HumanFrame;
            /// <summary>GRIP: the human's walking bob, in metres of the logo's frame (none while he holds the chair).</summary>
            public float HumanHop;
            /// <summary>GRIP: the human holds the chair (the pair's picture shows, over the chair's layer).</summary>
            public bool Holding;

            public bool Equals(Pose other) => Chair == other.Chair && Lean == other.Lean && Light == other.Light && Spot == other.Spot
                && Hop == other.Hop && Dog == other.Dog && DogAlpha == other.DogAlpha
                && DogFacing == other.DogFacing && DogFrame == other.DogFrame && DogHop == other.DogHop && DogWag == other.DogWag
                && DogBite == other.DogBite && Human == other.Human && HumanAlpha == other.HumanAlpha && HumanFacing == other.HumanFacing
                && HumanFrame == other.HumanFrame && HumanHop == other.HumanHop && Holding == other.Holding;

            public override bool Equals(object obj) => obj is Pose other && Equals(other);

            public override int GetHashCode() => (Chair, Lean, Light, Spot, Hop, Dog).GetHashCode() ^ (DogAlpha, DogFacing, DogFrame, DogHop, DogWag).GetHashCode()
                ^ (DogBite, Human, HumanAlpha, HumanFacing, HumanFrame, HumanHop, Holding).GetHashCode();

            public override string ToString() =>
                $"chair {Chair:0.000} m, hop {Hop:0.000} m, lean {Lean:0.0} deg, light {Light:0.00}, spot {Spot:0.000} m; "
                + $"dog {Dog:0.000} m, alpha {DogAlpha:0.00}, facing {DogFacing:0}, frame {DogFrame}, bite {DogBite}, bob {DogHop:0.000} m, wag {DogWag:0.0} deg; "
                + $"human {Human:0.000} m, alpha {HumanAlpha:0.00}, facing {HumanFacing:0}, frame {HumanFrame}, holding {Holding}, bob {HumanHop:0.000} m";
        }

        /// <summary>Where the dog is hidden (Pose.Dog): its body's centre on the frame's left edge.</summary>
        public const float DogEdge = -Tuning.TitleLogoChairInset - Tuning.TitleLogoDogGrip;

        /// <summary>
        /// GRIP: where the human stands when he holds the chair on its mark, on the floor from the chair's foot (x to the
        /// right, y into the depth; metres): Tuning.TitleLogoHumanReach behind the middle of his two hands, which rest on the
        /// top rail of the backrest (GripDef's chair wrists, across the rail at Tuning.TitleLogoHumanRightX and LeftX), the
        /// chair turned Tuning.TitleLogoChairYaw, he Tuning.TitleLogoHumanYaw. Pure arithmetic (no engine call).
        /// </summary>
        public static Vector2 HumanRoot => HumanRootValue;

        // Computed once (declared before Rest, which reads it: static fields initialise in their order in the file).
        private static readonly Vector2 HumanRootValue = ComputeHumanRoot();

        private static Vector2 ComputeHumanRoot()
        {
            Vector3 wrist = GripDef.For("chair").RightWrist;
            Vector2 right = Turn(new Vector2(Tuning.TitleLogoHumanRightX, wrist.z), Tuning.TitleLogoChairYaw);
            Vector2 left = Turn(new Vector2(Tuning.TitleLogoHumanLeftX, wrist.z), Tuning.TitleLogoChairYaw);
            Vector2 forward = Turn(new Vector2(0f, 1f), Tuning.TitleLogoHumanYaw);
            return 0.5f * (right + left) - forward * Tuning.TitleLogoHumanReach;
        }

        /// <summary>GRIP: (x, z) on the floor turned by a yaw of <paramref name="degrees"/> (Unity's: +z turns toward +x).</summary>
        public static Vector2 Turn(Vector2 p, float degrees)
        {
            float a = degrees * Mathf.Deg2Rad;
            float c = Mathf.Cos(a);
            float s = Mathf.Sin(a);
            return new Vector2(p.x * c + p.y * s, -p.x * s + p.y * c);
        }

        /// <summary>GRIP: where the human is hidden (Pose.Human): his feet on the frame's left edge.</summary>
        public static float HumanEdge => -Tuning.TitleLogoChairInset - HumanRoot.x;

        /// <summary>The still pose: the chair on its mark, upright, in the full light; the dog and the human hidden at the left edge.</summary>
        public static readonly Pose Rest = new Pose { Light = 1f, Dog = DogEdge, DogFacing = 1f, Human = HumanEdge, HumanFacing = 1f };

        // The act (the last 1 - Tuning.TitleLogoStillFraction of the loop), in fractions of its own length (ActSeconds,
        // 11 s at a 26 s loop; the seconds below are at that length):
        // - the spot slides away to the left and dims, gone at LeaveEnd (0.70 s);
        // - the hops start at HopStart (0.60 s, the light already under a fifth), one every HopPitch (0.75 s), each a soft
        //   lift (no squash, no tilt) for HopFlight of the pitch, then a pause on the floor (3 hops, the last lands at 2.70 s);
        // - the spot comes back onto the chair where it now stands, from ReturnStart to ReturnEnd (3.10 to 3.80 s),
        //   accelerating all the way, landing at full light; caught, the chair gives one startled jump (StartleStart to
        //   StartleEnd, 3.95 to 4.35 s);
        // - the dog trots in from the left edge (TrotStart to TrotEnd, 4.70 to 5.90 s), grabs the chair (a small jolt,
        //   until DragStart, 6.30 s) and drags it home walking backwards (to DragEnd, 9.10 s), the light following it;
        // - the dog lets go and backs off a step (ReleaseEnd, 9.40 s), wags (WagEnd, 10.00 s), turns round and trots out
        //   through the left edge, gone at the act's end (11 s); then the still pose holds 15 s.
        public const float LeaveEnd = 0.70f / 11f;
        public const float HopStart = 0.60f / 11f;
        public const float HopPitch = 0.75f / 11f;
        public const float HopFlight = 0.8f;
        public const float ReturnStart = 3.10f / 11f;
        public const float ReturnEnd = 3.80f / 11f;
        public const float StartleStart = 3.95f / 11f;
        public const float StartleEnd = 4.35f / 11f;
        public const float TrotStart = 4.70f / 11f;
        public const float TrotEnd = 5.90f / 11f;
        public const float DragStart = 6.30f / 11f;
        public const float DragEnd = 9.10f / 11f;
        public const float ReleaseEnd = 9.40f / 11f;
        public const float WagEnd = 10.00f / 11f;
        /// <summary>The act's length in seconds.</summary>
        public const float ActSeconds = Tuning.TitleLogoCycleSeconds * (1f - Tuning.TitleLogoStillFraction);
        // In the air, the shadow on the floor shrinks and fades by these at the top of the highest jump.
        private const float HopShadowShrink = 0.15f;
        private const float HopShadowFade = 0.4f;
        // The drag's tug: the wobble's rate (the in-game Tuning.DogDragWobbleHz), and how long it takes to fade in and out,
        // as a share of the drag; the step the dog backs off when it lets go, in metres; the wag's rate.
        private const float DragWobbleHz = Tuning.DogDragWobbleHz;
        private const float DragEase = 0.12f;
        private const float DogRelease = 0.05f;
        private const float WagHz = 6f;
        /// <summary>The dog's baked walk frames.</summary>
        public const int DogFrames = 2;

        private const string ChairModel = "kenney.chair";
        // GRIP: the human of the alternate loops, the level 1 man in his own clothes.
        private const string HumanModel = "quaternius.man";
        private static readonly Color ChairRed = new Color32(0xD7, 0x26, 0x3D, 0xFF);
        // DOGBIG: the game's dog, whatever it is: the dog row's model and fur tint (PersonalityDef), never a copy of them.
        private static string DogModel => PersonalityDef.For(PersonalityDef.Dog).Model;
        private static Color DogTint => ColorUtility.TryParseHtmlString(PersonalityDef.For(PersonalityDef.Dog).Tint, out Color c)
            ? new Color(c.r, c.g, c.b, 1f)
            : Color.gray;
        private static readonly Color PoolCore = new Color(1f, 0.9f, 0.7f);
        private static readonly Color PoolRim = new Color(0.93f, 0.55f, 0.27f);
        private static readonly Color ShadowInk = new Color(0.24f, 0.11f, 0.06f);
        private static readonly Color RimColor = new Color(1f, 0.86f, 0.66f);
        private static readonly Color SpotColor = new Color(1f, 0.88f, 0.7f);
        // The chair out of the light: darker and a little cooler, still readable over the dark title band.
        private static readonly Color ChairInDark = new Color(0.56f, 0.53f, 0.62f, 1f);
        private const float FadeSeconds = 0.45f;
        private const float ChairCurve = 1.45f;

        private Menu menu;
        private Graphic fallback;
        private CanvasGroup group;
        private Texture2D atlas;
        private Layers layers;
        private Vector2 frameRest;
        private float clockStart;
        private float pinned = -1f;
        private bool applied;
        // The dog's frames on its two layers (built once with the layers), the frame shown, and the pool's centre on the
        // floor (metres, x sideways from the chair's foot, y in depth), for the dog's shadow.
        private LayerFrame[] dogFrames;
        private LayerFrame[] dogShadowFrames;
        private int dogFrameShown = -1;
        private Vector2 poolCentre;
        // GRIP: the human's frames (walk 0 and 1, then the two holding poses alone, for their shadows), the pair's frames
        // (the chair and the human together), and the frames shown.
        private LayerFrame[] humanFrames;
        private LayerFrame[] humanShadowFrames;
        private LayerFrame[] pairFrames;
        private int humanFrameShown = -1;
        private int humanShadowShown = -1;
        private int pairFrameShown = -1;

        /// <summary>One crop of the atlas on a layer: its uv rect, its size in UI units, its pivot, and the sideways offset
        /// that puts its pivot back where it was rendered.</summary>
        private struct LayerFrame
        {
            public Rect Uv;
            public Vector2 Size;
            public Vector2 Pivot;
            public float OffsetX;
        }

        /// <summary>The logo under <paramref name="parent"/>; <paramref name="fallback"/> (the flat icon) shows only if the bake fails.</summary>
        public static TitleLogo Create(Transform parent, Menu menu, Graphic fallback)
        {
            var go = new GameObject("Logo", typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var image = go.AddComponent<RawImage>();
            image.raycastTarget = false;
            image.enabled = false;
            var logo = go.AddComponent<TitleLogo>();
            logo.Image = image;
            logo.menu = menu;
            logo.fallback = fallback;
            // The fade in, for every layer at once.
            logo.group = go.AddComponent<CanvasGroup>();
            logo.group.interactable = false;
            logo.group.blocksRaycasts = false;
            if (fallback != null)
            {
                fallback.enabled = false;
            }
            return logo;
        }

        /// <summary>
        /// The loop at <paramref name="phase"/> (any real number; one loop per unit, 0 is the start of the still part).
        /// Pure, so the probes check the choreography itself: still in the full light for Tuning.TitleLogoStillFraction of
        /// the loop, then the act, which starts and ends exactly on <see cref="Rest"/> (a seamless loop, every position
        /// continuous): the chair hops off only once the light has left it, jumps once when the light catches it, and comes
        /// back only in the dog's mouth, in the full light that follows it.
        /// </summary>
        public static Pose Sample(float phase)
        {
            float loop = Mathf.Floor(phase);
            float u = phase - loop;
            float still = Tuning.TitleLogoStillFraction;
            if (u < still)
            {
                return Rest;
            }
            float a = (u - still) / (1f - still);
            // GRIP: the loops alternate, the dog's (even), then the human's (odd).
            if (Mathf.Repeat(loop, 2f) >= 1f)
            {
                return HumanAct(a);
            }
            float far = Tuning.TitleLogoChairHops * Tuning.TitleLogoChairHopStride;
            Pose pose = Rest;
            if (a < ReturnEnd)
            {
                // Away to the left and dim, then back onto the chair where it now stands, accelerating all the way (a cubic
                // ease in), landing at full light.
                float leave = Ease(a / LeaveEnd);
                float back = Mathf.Clamp01((a - ReturnStart) / (ReturnEnd - ReturnStart));
                back = back * back * back;
                pose.Spot = Mathf.Lerp(-Tuning.TitleLogoSpotDrift * leave, far, back);
                pose.Light = Mathf.Lerp(1f - (1f - Tuning.TitleLogoSpotAway) * leave, 1f, back);
                Hops(a, ref pose);
            }
            else if (a < DragStart)
            {
                // Caught in the light: one startled jump, then the dog trots in from the left edge and grabs the chair.
                pose.Chair = far;
                pose.Spot = far;
                pose.Hop = StartleHop(a);
                if (a >= TrotEnd)
                {
                    // The grab: the chair jolts toward the dog, which bites its leg.
                    pose.Lean = Tuning.TitleLogoDragWobble * Mathf.Sin(Mathf.PI * (a - TrotEnd) / (DragStart - TrotEnd));
                    pose.DogBite = true;
                }
                if (a >= TrotStart)
                {
                    pose.Dog = a < TrotEnd ? Mathf.Lerp(DogEdge, far, Ease((a - TrotStart) / (TrotEnd - TrotStart))) : far;
                }
            }
            else if (a < DragEnd)
            {
                // The drag: home in the dog's mouth, lifted a little, with the tug's wobble fading in and out; the light
                // follows the chair.
                float d = (a - DragStart) / (DragEnd - DragStart);
                float env = Ease(d / DragEase) * Ease((1f - d) / DragEase);
                float t = (a - DragStart) * ActSeconds;
                pose.Chair = far * (1f - Ease(d));
                pose.Spot = pose.Chair;
                pose.Dog = pose.Chair;
                pose.Lean = Tuning.TitleLogoDragWobble * Mathf.Sin(2f * Mathf.PI * DragWobbleHz * t) * env;
                pose.Hop = Tuning.TitleLogoDragLift * env * (0.75f + 0.25f * Mathf.Sin(4f * Mathf.PI * DragWobbleHz * t));
                pose.DogBite = true;
            }
            else if (a < ReleaseEnd)
            {
                // Home, in the full light: the dog lets go and backs off a step.
                pose.Dog = -DogRelease * Ease((a - DragEnd) / (ReleaseEnd - DragEnd));
            }
            else if (a < WagEnd)
            {
                // A tiny wag.
                float w = (a - ReleaseEnd) / (WagEnd - ReleaseEnd);
                pose.Dog = -DogRelease;
                pose.DogWag = Tuning.TitleLogoDogWag * Mathf.Sin(2f * Mathf.PI * WagHz * (a - ReleaseEnd) * ActSeconds) * Mathf.Sin(Mathf.PI * w);
            }
            else
            {
                // Turned round, it trots out through the left edge, speeding up.
                float e = (a - WagEnd) / (1f - WagEnd);
                pose.DogFacing = -1f;
                pose.Dog = Mathf.Lerp(-DogRelease, DogEdge, e * e);
            }
            pose.DogAlpha = Mathf.Clamp01((pose.Dog - DogEdge) / Tuning.TitleLogoDogFade);
            if (pose.DogAlpha <= 0f)
            {
                // Out of sight, the dog waits at the edge as in the still pose (the act's first and last instants are Rest).
                pose.Dog = DogEdge;
                pose.DogFacing = 1f;
                pose.DogWag = 0f;
            }
            else
            {
                // Its walk: the frames swap every half stride of the floor it covers, with a little bob.
                float halfStride = Tuning.TitleLogoDogStride * 0.5f;
                float walked = (pose.Dog - DogEdge) / halfStride;
                pose.DogFrame = (int)Mathf.Floor(walked) & 1;
                pose.DogHop = Tuning.TitleLogoDogBob * Mathf.Abs(Mathf.Sin(Mathf.PI * walked));
            }
            return pose;
        }

        /// <summary>The startled jump's lift at <paramref name="a"/> (0 outside it): up fast, down a little slower (a sine
        /// arc on a time warped toward the start), soft at both ends.</summary>
        private static float StartleHop(float a)
        {
            if (a < StartleStart || a >= StartleEnd)
            {
                return 0f;
            }
            float s = (a - StartleStart) / (StartleEnd - StartleStart);
            float arc = Mathf.Sin(Mathf.PI * Mathf.Sqrt(s));
            return Tuning.TitleLogoChairStartle * arc * arc;
        }

        // GRIP: the step the human backs off when he lets go, and the floor between two swaps of his walk frames while he
        // pulls the chair (short shuffling steps backwards), in metres.
        private const float HumanRelease = 0.06f;
        private const float HumanPullStep = 0.1f;

        /// <summary>
        /// GRIP: the human's loop at <paramref name="a"/> (a fraction of the act): the same spot, hops, return and startle as
        /// the dog's; then he walks in from the left edge (TrotStart to TrotEnd), puts his hands on the backrest's top rail
        /// (the grab, to DragStart), pulls the chair home walking backwards with short steps in the light that follows it (to
        /// DragEnd), lets go and backs off a step (ReleaseEnd), stands a beat (WagEnd), turns round and walks out through the
        /// left edge. Neither lift nor tilt while he holds it: the pair's picture covers the chair's exactly.
        /// </summary>
        private static Pose HumanAct(float a)
        {
            float far = Tuning.TitleLogoChairHops * Tuning.TitleLogoChairHopStride;
            float edge = HumanEdge;
            Pose pose = Rest;
            if (a < ReturnEnd)
            {
                float leave = Ease(a / LeaveEnd);
                float back = Mathf.Clamp01((a - ReturnStart) / (ReturnEnd - ReturnStart));
                back = back * back * back;
                pose.Spot = Mathf.Lerp(-Tuning.TitleLogoSpotDrift * leave, far, back);
                pose.Light = Mathf.Lerp(1f - (1f - Tuning.TitleLogoSpotAway) * leave, 1f, back);
                Hops(a, ref pose);
            }
            else if (a < DragStart)
            {
                pose.Chair = far;
                pose.Spot = far;
                pose.Hop = StartleHop(a);
                if (a >= TrotStart)
                {
                    pose.Human = a < TrotEnd ? Mathf.Lerp(edge, far, Ease((a - TrotStart) / (TrotEnd - TrotStart))) : far;
                }
                pose.Holding = a >= TrotEnd;
            }
            else if (a < DragEnd)
            {
                float d = (a - DragStart) / (DragEnd - DragStart);
                pose.Chair = far * (1f - Ease(d));
                pose.Spot = pose.Chair;
                pose.Human = pose.Chair;
                pose.Holding = true;
            }
            else if (a < ReleaseEnd)
            {
                pose.Human = -HumanRelease * Ease((a - DragEnd) / (ReleaseEnd - DragEnd));
            }
            else if (a < WagEnd)
            {
                pose.Human = -HumanRelease;
            }
            else
            {
                float e = (a - WagEnd) / (1f - WagEnd);
                pose.HumanFacing = -1f;
                pose.Human = Mathf.Lerp(-HumanRelease, edge, e * e);
            }
            pose.HumanAlpha = Mathf.Clamp01((pose.Human - edge) / Tuning.TitleLogoDogFade);
            if (pose.HumanAlpha <= 0f)
            {
                pose.Human = edge;
                pose.HumanFacing = 1f;
                pose.Holding = false;
            }
            else if (pose.Holding)
            {
                // Pulling: a swap every short step back; the picture carries the chair, so no bob.
                pose.HumanFrame = (int)Mathf.Floor((far - pose.Human) / HumanPullStep) & 1;
            }
            else
            {
                float halfStride = 0.5f * Tuning.RigWalkCycleMeters * Tuning.TitleLogoHumanScale;
                float walked = (pose.Human - edge) / halfStride;
                pose.HumanFrame = (int)Mathf.Floor(walked) & 1;
                pose.HumanHop = Tuning.TitleLogoHumanBob * Mathf.Abs(Mathf.Sin(Mathf.PI * walked));
            }
            return pose;
        }

        /// <summary>Off to the right in gentle hops: the finished ones, plus the one under way. Each is a soft lift (a
        /// squared sine, so it leaves and meets the floor without a bump) while the chair eases across its stride; the
        /// chair keeps its shape and stays upright.</summary>
        private static void Hops(float a, ref Pose pose)
        {
            float stride = Tuning.TitleLogoChairHopStride;
            for (int i = 0; i < Tuning.TitleLogoChairHops; i++)
            {
                float p = (a - HopStart - i * HopPitch) / (HopPitch * HopFlight);
                if (p <= 0f)
                {
                    break;
                }
                if (p >= 1f)
                {
                    pose.Chair += stride;
                    continue;
                }
                float arc = Mathf.Sin(Mathf.PI * p);
                pose.Chair += stride * Ease(p);
                pose.Hop = Tuning.TitleLogoChairHopHeight * arc * arc;
                break;
            }
        }

        /// <summary>The pool's light (1 at its core, 0 beyond its radius) at <paramref name="offset"/> metres from its
        /// centre on the floor: the bake's falloff, also used for the dog's shadow as it crosses the pool.</summary>
        private static float PoolLightAt(Vector2 offset)
        {
            float r = offset.magnitude / Tuning.TitleLogoPoolRadius;
            // (Mathf.SmoothStep interpolates between its first two arguments, it is not GLSL's smoothstep: the edge is
            // mapped to 0..1 first.)
            float edge = Mathf.InverseLerp(Tuning.TitleLogoPoolCore, 1f, r);
            return (1f - Mathf.SmoothStep(0f, 1f, edge)) * Mathf.Lerp(1f, 0.82f, Mathf.Min(r, 1f));
        }

        /// <summary>Holds the loop at <paramref name="phase"/> (the probes' checks and shots; from 1 to 2 the human's loop)
        /// until <see cref="Unpin"/>.</summary>
        public void Pin(float phase)
        {
            pinned = Mathf.Repeat(phase, 2f);
            if (Ready)
            {
                Phase = pinned;
                Apply(Sample(pinned));
            }
        }

        /// <summary>Lets the loop run on its clock again.</summary>
        public void Unpin()
        {
            pinned = -1f;
        }

        /// <summary>
        /// The still pose composited from the atlas (pool, shadow, chair, straight alpha over nothing), at
        /// Tuning.TitleLogoWidth x Height: what the frame shows at rest. For the probes only (it reads the atlas back,
        /// which only development builds and the editor keep readable); null before the bake.
        /// </summary>
        public Color32[] RestFrame()
        {
            if (atlas == null || layers == null)
            {
                return null;
            }
            Color32[] src = atlas.GetPixels32();
            int aw = layers.AtlasWidth;
            int w = layers.Width;
            int h = layers.Height;
            var frame = new Color32[w * h];
            for (int y = 0; y < h; y++)
            {
                for (int x = 0; x < w; x++)
                {
                    Color c = src[(layers.PoolAt.y + y) * aw + layers.PoolAt.x + x];
                    c = Over(Pick(src, aw, layers.ShadowRect, layers.ShadowAt, x, y), c);
                    c = Over(Pick(src, aw, layers.ChairRect, layers.ChairAt, x, y), c);
                    frame[y * w + x] = c;
                }
            }
            return frame;
        }

        private static Color Pick(Color32[] src, int aw, RectInt rect, Vector2Int at, int x, int y)
        {
            if (!rect.Contains(new Vector2Int(x, y)))
            {
                return Color.clear;
            }
            return src[(at.y + y - rect.y) * aw + at.x + x - rect.x];
        }

        private static Color Over(Color s, Color d)
        {
            float a = s.a + d.a * (1f - s.a);
            if (a <= 1e-5f)
            {
                return Color.clear;
            }
            Color rgb = (new Color(s.r, s.g, s.b) * s.a + new Color(d.r, d.g, d.b) * (d.a * (1f - s.a))) * (1f / a);
            return new Color(rgb.r, rgb.g, rgb.b, a);
        }

        private static float Ease(float p)
        {
            p = Mathf.Clamp01(p);
            return p * p * (3f - 2f * p);
        }

        private IEnumerator Start()
        {
            if (SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null)
            {
                Fail("no graphics device");
                yield break;
            }
            // Baked the first time the title page actually shows (never under the probe, which keeps it closed).
            while (menu != null && !menu.TitlePageShown)
            {
                yield return null;
            }
            yield return null;

            Rig rig = null;
            try
            {
                rig = Rig.Build();
            }
            catch (Exception e)
            {
                rig?.Dispose();
                Fail(e.Message);
                yield break;
            }
            // The two cameras render on request, right away (2026-11-19): an editor in batch mode never reaches the end of
            // a frame, so the old wait for it left the probes without a logo. Where the pipeline cannot take a request,
            // they render with the next frame as before.
            yield return null;
            bool rendered;
            try
            {
                rendered = rig.Render();
            }
            catch (Exception e)
            {
                rig.Dispose();
                Fail(e.Message);
                yield break;
            }
            if (!rendered)
            {
                yield return null;
                yield return new WaitForEndOfFrame();
            }
            // Read back over the next frames, then compose on a worker thread: a synchronous read and the composition
            // took a single frame of about 150 ms, a visible hitch on the title page (and on the probes' clocks).
            IEnumerator readBack = rig.ReadBack();
            while (true)
            {
                bool more;
                try
                {
                    more = readBack.MoveNext();
                }
                catch (Exception e)
                {
                    rig.Dispose();
                    Fail(e.Message);
                    yield break;
                }
                if (!more)
                {
                    break;
                }
                yield return readBack.Current;
            }
            rig.Dispose();
            Task<Layers> compose = Task.Run(() => rig.Compose());
            while (!compose.IsCompleted)
            {
                yield return null;
            }
            if (compose.IsFaulted || compose.IsCanceled)
            {
                Fail(compose.Exception != null ? compose.Exception.GetBaseException().Message : "composition cancelled");
                yield break;
            }
            try
            {
                layers = compose.Result;
                atlas = Rig.MakeTexture(layers);
                PoolPixel = rig.PoolPixel;
                ShadowPixel = rig.ShadowPixel;
                ShadowInPool = rig.ShadowInPool;
                BuildLayers();
            }
            catch (Exception e)
            {
                Fail(e.Message);
                yield break;
            }
            group.alpha = 0f;
            Image.enabled = true;
            Ready = true;
            clockStart = Time.unscaledTime;
            Phase = pinned >= 0f ? pinned : Tuning.TitleLogoStartPhase;
            Apply(Sample(Phase));
            for (float t = 0f; t < FadeSeconds; t += Time.unscaledDeltaTime)
            {
                group.alpha = Mathf.SmoothStep(0f, 1f, t / FadeSeconds);
                yield return null;
            }
            group.alpha = 1f;
        }

        /// <summary>The frame shows the pool from the atlas; the shadows, the chair and the dog become its children. The
        /// chair's layers are anchored at its foot (their pivot), so a pose only slides them sideways (and tips the chair
        /// about its foot). The dog's are anchored where its body stood in the bake (holding the chair on its mark); its
        /// picture pivots at its own centre, so it turns round in place.</summary>
        private void BuildLayers()
        {
            RectTransform frame = Image.rectTransform;
            frameRest = frame.anchoredPosition;
            Vector2 size = frame.rect.size;
            UiPerMetre = size.x / Tuning.TitleLogoFrameWidth;
            float heading = Tuning.TitleLogoSunHeading * Mathf.Deg2Rad;
            poolCentre = new Vector2(Mathf.Cos(heading), Mathf.Sin(heading)) * Tuning.TitleLogoPoolCentre;
            var foot = new Vector2(layers.Width * Tuning.TitleLogoChairInset / Tuning.TitleLogoFrameWidth, layers.Height * Tuning.TitleLogoFootHeight);
            var scale = new Vector2(size.x / layers.Width, size.y / layers.Height);
            Image.texture = atlas;
            Image.uvRect = Uv(new RectInt(layers.PoolAt.x, layers.PoolAt.y, layers.Width, layers.Height));
            Shadow = NewLayer("Shadow", layers.ShadowRect, layers.ShadowAt, foot, scale);
            // The shadows under every body, then the chair, the pair over it, then the dog and the walking human in front.
            Vector2 dogRoot = default;
            Vector2 humanRoot = default;
            if (layers.HasDog)
            {
                dogRoot = new Vector2(layers.Width * (Tuning.TitleLogoChairInset + Tuning.TitleLogoDogGrip) / Tuning.TitleLogoFrameWidth, foot.y);
                dogFrames = new LayerFrame[2 * DogFrames];
                dogShadowFrames = new LayerFrame[2 * DogFrames];
                for (int k = 0; k < dogFrames.Length; k++)
                {
                    RectInt body = layers.DogRect[k];
                    float centre = body.x + body.width * 0.5f;
                    dogFrames[k] = Crop(body, layers.DogAt[k], new Vector2(centre, dogRoot.y), scale, (centre - dogRoot.x) * scale.x);
                    dogShadowFrames[k] = Crop(layers.DogShadowRect[k], layers.DogShadowAt[k], dogRoot, scale, 0f);
                }
                DogShadow = NewLayer("DogShadow", layers.DogShadowRect[0], layers.DogShadowAt[0], dogRoot, scale);
                DogShadow.color = Color.clear;
            }
            if (layers.HasHuman)
            {
                // Anchored on the floor line under his feet' x (any fixed point of the frame keeps the pictures where they
                // were rendered; the walking ones pivot on their own centre so he turns round in place).
                humanRoot = new Vector2(layers.Width * (Tuning.TitleLogoChairInset + HumanRoot.x) / Tuning.TitleLogoFrameWidth, foot.y);
                humanFrames = new LayerFrame[2 * DogFrames];
                humanShadowFrames = new LayerFrame[2 * DogFrames];
                for (int k = 0; k < humanFrames.Length; k++)
                {
                    RectInt body = layers.HumanRect[k];
                    float centre = body.x + body.width * 0.5f;
                    humanFrames[k] = Crop(body, layers.HumanAt[k], new Vector2(centre, humanRoot.y), scale, (centre - humanRoot.x) * scale.x);
                    humanShadowFrames[k] = Crop(layers.HumanShadowRect[k], layers.HumanShadowAt[k], humanRoot, scale, 0f);
                }
                pairFrames = new LayerFrame[DogFrames];
                for (int k = 0; k < DogFrames; k++)
                {
                    pairFrames[k] = Crop(layers.PairRect[k], layers.PairAt[k], humanRoot, scale, 0f);
                }
                HumanShadow = NewLayer("HumanShadow", layers.HumanShadowRect[0], layers.HumanShadowAt[0], humanRoot, scale);
                HumanShadow.color = Color.clear;
            }
            Chair = NewLayer("Chair", layers.ChairRect, layers.ChairAt, foot, scale);
            if (layers.HasHuman)
            {
                HumanPair = NewLayer("HumanPair", layers.PairRect[0], layers.PairAt[0], humanRoot, scale);
                HumanPair.color = Color.clear;
            }
            if (layers.HasDog)
            {
                Dog = NewLayer("Dog", layers.DogRect[0], layers.DogAt[0], dogRoot, scale);
                Dog.color = Color.clear;
            }
            if (layers.HasHuman)
            {
                Human = NewLayer("Human", layers.HumanRect[0], layers.HumanAt[0], humanRoot, scale);
                Human.color = Color.clear;
            }
        }

        private LayerFrame Crop(RectInt rect, Vector2Int at, Vector2 pivot, Vector2 scale, float offsetX)
        {
            return new LayerFrame
            {
                Uv = Uv(new RectInt(at.x, at.y, rect.width, rect.height)),
                Size = new Vector2(rect.width * scale.x, rect.height * scale.y),
                Pivot = new Vector2((pivot.x - rect.x) / rect.width, (pivot.y - rect.y) / rect.height),
                OffsetX = offsetX,
            };
        }

        private static void Show(RawImage image, LayerFrame frame)
        {
            image.uvRect = frame.Uv;
            RectTransform rt = image.rectTransform;
            rt.pivot = frame.Pivot;
            rt.sizeDelta = frame.Size;
        }

        private RawImage NewLayer(string name, RectInt rect, Vector2Int at, Vector2 foot, Vector2 scale)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(transform, false);
            var image = go.AddComponent<RawImage>();
            image.raycastTarget = false;
            image.texture = atlas;
            image.uvRect = Uv(new RectInt(at.x, at.y, rect.width, rect.height));
            RectTransform rt = image.rectTransform;
            rt.anchorMin = rt.anchorMax = new Vector2(foot.x / layers.Width, foot.y / layers.Height);
            rt.pivot = new Vector2((foot.x - rect.x) / rect.width, (foot.y - rect.y) / rect.height);
            rt.sizeDelta = new Vector2(rect.width * scale.x, rect.height * scale.y);
            rt.anchoredPosition = Vector2.zero;
            return image;
        }

        private Rect Uv(RectInt r)
        {
            float w = atlas.width;
            float h = atlas.height;
            return new Rect(r.x / w, r.y / h, r.width / w, r.height / h);
        }

        private void Update()
        {
            // Nothing to do before the bake, or while another page hides the title (its canvas is only disabled).
            if (!Ready || (menu != null && !menu.TitlePageShown))
            {
                return;
            }
            Phase = pinned >= 0f
                ? pinned
                : Mathf.Repeat(Tuning.TitleLogoStartPhase + (Time.unscaledTime - clockStart) / Tuning.TitleLogoCycleSeconds, 2f);
            Apply(Sample(Phase));
        }

        /// <summary>Puts the layers in <paramref name="pose"/>; no write at all while the pose does not change (the long
        /// still part), so the title canvas is not rebuilt for nothing.</summary>
        private void Apply(Pose pose)
        {
            if (Chair == null || (applied && pose.Equals(Current)))
            {
                return;
            }
            Current = pose;
            applied = true;
            // The frame carries the pool with the spot; its children move back by the same amount, then by their own.
            Image.rectTransform.anchoredPosition = frameRest + new Vector2(pose.Spot * UiPerMetre, 0f);
            Image.color = new Color(1f, 1f, 1f, pose.Light);
            var local = new Vector2((pose.Chair - pose.Spot) * UiPerMetre, 0f);
            // In a jump the shadow stays on the floor, a little smaller and fainter at the top.
            float highest = Mathf.Max(Tuning.TitleLogoChairHopHeight, Tuning.TitleLogoChairStartle);
            float air = highest > 0f ? Mathf.Clamp01(pose.Hop / highest) : 0f;
            float shrink = 1f - HopShadowShrink * air;
            Shadow.rectTransform.anchoredPosition = local;
            Shadow.rectTransform.localScale = new Vector3(shrink, shrink, 1f);
            // The shadow is a darkening of the spot's light: it fades with it.
            Shadow.color = new Color(1f, 1f, 1f, pose.Light * (1f - HopShadowFade * air));
            // The chair's picture lifts over its shadow (the orthographic view tilts the floor, so up on screen reads as
            // up off the floor); it never changes shape.
            Chair.rectTransform.anchoredPosition = local + new Vector2(0f, pose.Hop * UiPerMetre);
            Chair.rectTransform.localRotation = Quaternion.Euler(0f, 0f, pose.Lean);
            Color lit = Color.Lerp(ChairInDark, Color.white, pose.Light);
            Chair.color = lit;
            if (Dog != null)
            {
                // GRIP: the bite frames (its head lowered to the chair's leg) while it holds the chair.
                int f = Mathf.Clamp(pose.DogFrame, 0, DogFrames - 1) + (pose.DogBite ? DogFrames : 0);
                if (f != dogFrameShown)
                {
                    Show(Dog, dogFrames[f]);
                    Show(DogShadow, dogShadowFrames[f]);
                    dogFrameShown = f;
                }
                float dog = (pose.Dog - pose.Spot) * UiPerMetre;
                RectTransform body = Dog.rectTransform;
                body.anchoredPosition = new Vector2(dog + dogFrames[f].OffsetX, pose.DogHop * UiPerMetre);
                body.localScale = new Vector3(pose.DogFacing, 1f, 1f);
                body.localRotation = Quaternion.Euler(0f, 0f, pose.DogWag);
                Color dogLit = lit;
                dogLit.a = pose.DogAlpha;
                Dog.color = dogLit;
                // The dog's shadow darkens the pool's light where the dog stands (the pool moves with the spot).
                DogShadow.rectTransform.anchoredPosition = new Vector2(dog, 0f);
                var ground = new Vector2(Tuning.TitleLogoDogGrip + pose.Dog - pose.Spot, 0f);
                DogShadow.color = new Color(1f, 1f, 1f, pose.DogAlpha * pose.Light * PoolLightAt(ground - poolCentre));
            }
            if (Human != null)
            {
                ApplyHuman(pose, lit);
            }
        }

        /// <summary>GRIP: the human's layers: walking (his frame, bob and facing), or holding the chair (the pair's picture
        /// exactly over the chair's layer, the walking layer hidden), and his shadow in the pool's light.</summary>
        private void ApplyHuman(Pose pose, Color lit)
        {
            int f = Mathf.Clamp(pose.HumanFrame, 0, DogFrames - 1);
            float x = (pose.Human - pose.Spot) * UiPerMetre;
            Color shown = lit;
            shown.a = pose.HumanAlpha;
            if (pose.Holding)
            {
                if (f != pairFrameShown)
                {
                    Show(HumanPair, pairFrames[f]);
                    pairFrameShown = f;
                }
                HumanPair.rectTransform.anchoredPosition = new Vector2(x, 0f);
                HumanPair.color = shown;
                Human.color = Color.clear;
            }
            else
            {
                if (f != humanFrameShown)
                {
                    Show(Human, humanFrames[f]);
                    humanFrameShown = f;
                }
                RectTransform body = Human.rectTransform;
                body.anchoredPosition = new Vector2(x + humanFrames[f].OffsetX, pose.HumanHop * UiPerMetre);
                body.localScale = new Vector3(pose.HumanFacing, 1f, 1f);
                Human.color = shown;
                HumanPair.color = Color.clear;
            }
            int s = f + (pose.Holding ? DogFrames : 0);
            if (s != humanShadowShown)
            {
                Show(HumanShadow, humanShadowFrames[s]);
                humanShadowShown = s;
            }
            HumanShadow.rectTransform.anchoredPosition = new Vector2(x, 0f);
            Vector2 root = HumanRoot;
            var ground = new Vector2(root.x + pose.Human - pose.Spot, root.y);
            HumanShadow.color = new Color(1f, 1f, 1f, pose.HumanAlpha * pose.Light * PoolLightAt(ground - poolCentre));
        }

        private void Fail(string why)
        {
            Debug.LogWarning("[TitleLogo] Logo not baked, the flat icon stays: " + why);
            if (fallback != null)
            {
                fallback.enabled = true;
            }
        }

        private void OnDestroy()
        {
            if (atlas != null)
            {
                Destroy(atlas);
            }
        }

        /// <summary>The bake's result: the frame's size, the layers packed in one atlas (the pool, full frame, at the bottom
        /// left; the chair and its shadow, each cropped to its pixels plus a transparent margin, side by side above it; the
        /// dog's frames and their shadows in a row above those), and where each crop sits in the frame.</summary>
        private sealed class Layers
        {
            public int Width;
            public int Height;
            public int AtlasWidth;
            public int AtlasHeight;
            public Color32[] Atlas;
            public Vector2Int PoolAt;
            public RectInt ChairRect;
            public Vector2Int ChairAt;
            public RectInt ShadowRect;
            public Vector2Int ShadowAt;
            public bool HasDog;
            public RectInt[] DogRect;
            public Vector2Int[] DogAt;
            public RectInt[] DogShadowRect;
            public Vector2Int[] DogShadowAt;
            // GRIP: the human's four frames (walk 0 and 1, then holding 0 and 1 alone) and their shadows, and the pair's two.
            public bool HasHuman;
            public RectInt[] HumanRect;
            public Vector2Int[] HumanAt;
            public RectInt[] HumanShadowRect;
            public Vector2Int[] HumanShadowAt;
            public RectInt[] PairRect;
            public Vector2Int[] PairAt;
        }

        /// <summary>The temporary scene: the chair, the dog's posed frames, the lights and the two cameras, with their
        /// render targets.</summary>
        private sealed class Rig : IDisposable
        {
            private GameObject root;
            private GameObject chairHolder;
            private Camera chairCamera;
            private Camera shadowCamera;
            private RenderTexture chairTarget;
            private RenderTexture shadowTarget;
            private Vector3 horizontal;
            private float shadowLength;
            // The dog: one static copy of the dog per baked walk frame (its skinned mesh baked in that pose), each shown
            // alone for its own pass into its two targets. Null when the dog could not be built (the logo then has none).
            private GameObject[] dogPoses;
            private readonly List<Mesh> dogMeshes = new List<Mesh>();
            private RenderTexture[] dogTargets;
            private RenderTexture[] dogShadowTargets;
            private Color32[][] dogPixels;
            private Color32[][] dogShadowPixels;
            // GRIP: the human's four static copies (walk 0 and 1, then holding the chair's rail 0 and 1), each rendered alone
            // (colour and shadow); the two holding ones also with the chair (the pair). Null when he could not be built.
            private GameObject[] humanPoses;
            private RenderTexture[] humanTargets;
            private RenderTexture[] humanShadowTargets;
            private RenderTexture[] pairTargets;
            private Color32[][] humanPixels;
            private Color32[][] humanShadowPixels;
            private Color32[][] pairPixels;

            private bool HasDog => dogPoses != null;
            private bool HasHuman => humanPoses != null;

            public Vector2Int PoolPixel { get; private set; }
            public Vector2Int ShadowPixel { get; private set; }
            public float ShadowInPool { get; private set; }

            private static int Width => Tuning.TitleLogoWidth * 2;
            private static int Height => Tuning.TitleLogoHeight * 2;

            public static Rig Build()
            {
                var rig = new Rig();
                try
                {
                    rig.Create();
                }
                catch
                {
                    rig.Dispose();
                    throw;
                }
                return rig;
            }

            private void Create()
            {
                int layer = Tuning.TitleLogoLayer;
                Light sun = Main.Instance != null ? Main.Instance.Sun : null;
                Vector3 sunForward = sun != null ? sun.transform.forward : Quaternion.Euler(44f, 32f, 0f) * Vector3.forward;

                // The sun's travel in the rig's frame: low over the ground, heading right and into the depth of the view.
                float elevation = Tuning.TitleLogoSunElevation * Mathf.Deg2Rad;
                float heading = Tuning.TitleLogoSunHeading * Mathf.Deg2Rad;
                horizontal = new Vector3(Mathf.Cos(heading), 0f, Mathf.Sin(heading));
                Vector3 local = (horizontal * Mathf.Cos(elevation) + Vector3.down * Mathf.Sin(elevation)).normalized;
                // The rotation that carries it onto the real sun, keeping the rig's up as close to the world's as it can.
                Quaternion rotation = Frame(sunForward) * Quaternion.Inverse(Frame(local));
                Vector3 side = Vector3.Cross(sunForward, Vector3.up);
                if (side.sqrMagnitude < 1e-4f)
                {
                    side = Vector3.right;
                }
                Vector3 origin = side.normalized * Tuning.TitleLogoRigDistance;

                root = new GameObject("TitleLogoRig") { layer = layer };
                root.transform.SetPositionAndRotation(origin, rotation);

                Vector3 size = BodyDef.For("chair").Size;
                shadowLength = size.y / Mathf.Tan(elevation);
                var holder = new GameObject("Chair") { layer = layer };
                chairHolder = holder;
                holder.transform.SetParent(root.transform, false);
                holder.transform.localRotation = Quaternion.Euler(0f, Tuning.TitleLogoChairYaw, 0f);
                if (ModelKit.Instantiate(ChairModel, holder.transform, size, ModelFit.Box, new ModelPaint { Main = ChairRed, Red = ChairRed }) == null)
                {
                    FurnitureKit.Chair(holder.transform, size, ChairRed, layer);
                }
                foreach (Transform t in holder.GetComponentsInChildren<Transform>(true))
                {
                    t.gameObject.layer = layer;
                }
                foreach (Renderer r in holder.GetComponentsInChildren<Renderer>(true))
                {
                    r.shadowCastingMode = ShadowCastingMode.On;
                    r.receiveShadows = true;
                }

                // A warm rim behind the chair, its range far short of anything else: on the side its back points to (right
                // for the old yaw of 220, which faced left; left since it faces right, 2026-11-21).
                float yaw = Tuning.TitleLogoChairYaw * Mathf.Deg2Rad;
                float backSide = Mathf.Sin(yaw) > 0f ? -1f : 1f;
                var rim = new GameObject("Rim") { layer = layer };
                rim.transform.SetParent(root.transform, false);
                rim.transform.localPosition = new Vector3(0.75f * backSide, 1.35f, 0.9f);
                Light light = rim.AddComponent<Light>();
                light.type = LightType.Point;
                light.color = RimColor;
                light.intensity = 1.4f;
                light.range = 2.6f;
                light.shadows = LightShadows.None;
                light.cullingMask = 1 << layer;

                // A soft fill from in front of the chair (2026-11-21): facing right, its seat front and the face of its back
                // turn away from the sun, which comes from the left; this keeps them a readable red, not a dark block.
                var fill = new GameObject("Fill") { layer = layer };
                fill.transform.SetParent(root.transform, false);
                fill.transform.localPosition = new Vector3(Mathf.Sin(yaw), 0f, Mathf.Cos(yaw)) * 1.1f + Vector3.up * 0.8f;
                Light fillLight = fill.AddComponent<Light>();
                fillLight.type = LightType.Point;
                fillLight.color = RimColor;
                fillLight.intensity = Tuning.TitleLogoFillIntensity;
                fillLight.range = 2.4f;
                fillLight.shadows = LightShadows.None;
                fillLight.cullingMask = 1 << layer;

                // The spot the pool of light comes from: straight above the pool's centre, warm, lighting the seat and the
                // tops of the rails (no shadow of its own: the short sun shadow is the one the logo shows).
                var spot = new GameObject("Spot") { layer = layer };
                spot.transform.SetParent(root.transform, false);
                spot.transform.localPosition = horizontal * Tuning.TitleLogoPoolCentre + Vector3.up * 2.2f;
                spot.transform.localRotation = Quaternion.Euler(90f, 0f, 0f);
                Light spotLight = spot.AddComponent<Light>();
                spotLight.type = LightType.Spot;
                spotLight.color = SpotColor;
                spotLight.intensity = Tuning.TitleLogoSpotIntensity;
                spotLight.range = 4f;
                spotLight.spotAngle = 70f;
                spotLight.innerSpotAngle = 30f;
                spotLight.shadows = LightShadows.None;
                spotLight.cullingMask = 1 << layer;

                // The dog (never at the cost of the chair: without it, the chair just comes home on its own).
                try
                {
                    BuildDog(layer);
                }
                catch (Exception e)
                {
                    Debug.LogWarning("[TitleLogo] no dog in the logo: " + e.Message);
                    dogPoses = null;
                }

                // GRIP: the human of the alternate loops (never at the cost of the chair or the dog).
                try
                {
                    BuildHuman(layer);
                }
                catch (Exception e)
                {
                    Debug.LogWarning("[TitleLogo] no human in the logo: " + e.Message);
                    humanPoses = null;
                    // Whatever he left half built stays out of the chair's and the dog's passes.
                    foreach (Transform child in root.transform)
                    {
                        if (child.name.StartsWith("Human", StringComparison.Ordinal))
                        {
                            child.gameObject.SetActive(false);
                        }
                    }
                }

                chairTarget = NewTarget("TitleLogoChair");
                shadowTarget = NewTarget("TitleLogoShadow");
                if (HasDog)
                {
                    dogTargets = new RenderTexture[2 * DogFrames];
                    dogShadowTargets = new RenderTexture[2 * DogFrames];
                    for (int k = 0; k < dogTargets.Length; k++)
                    {
                        dogTargets[k] = NewTarget("TitleLogoDog" + k);
                        dogShadowTargets[k] = NewTarget("TitleLogoDogShadow" + k);
                    }
                }
                if (HasHuman)
                {
                    humanTargets = new RenderTexture[2 * DogFrames];
                    humanShadowTargets = new RenderTexture[2 * DogFrames];
                    pairTargets = new RenderTexture[DogFrames];
                    for (int k = 0; k < humanTargets.Length; k++)
                    {
                        humanTargets[k] = NewTarget("TitleLogoHuman" + k);
                        humanShadowTargets[k] = NewTarget("TitleLogoHumanShadow" + k);
                    }
                    for (int k = 0; k < pairTargets.Length; k++)
                    {
                        pairTargets[k] = NewTarget("TitleLogoPair" + k);
                    }
                }
                chairCamera = NewCamera("ChairCamera", chairTarget, true);
                shadowCamera = NewCamera("ShadowCamera", shadowTarget, false);
                // The shadow camera sees every point of the chair moved onto the ground along the sun.
                Vector3 up = root.transform.up;
                shadowCamera.worldToCameraMatrix = chairCamera.worldToCameraMatrix * Projection(up, origin, sunForward);
                shadowCamera.cullingMatrix = chairCamera.projectionMatrix * chairCamera.worldToCameraMatrix;
            }

            /// <summary>
            /// The game's dog (the dog row's model, the Husky since DOGBIG, in its tint at Tuning.TitleLogoDogScale of its
            /// in-game size), standing where it holds the chair on its mark: its body Tuning.TitleLogoDogGrip from the chair's
            /// foot, facing right and a little toward the camera (Tuning.TitleLogoDogYaw), its snout at the chair's left edge.
            /// For each walk frame, its Walk clip is sampled at a stride's foot contact and its skinned mesh baked into a static
            /// copy (hidden until its pass), so every frame renders in the same frame with the same light. The skinned model
            /// is then hidden.
            /// </summary>
            private void BuildDog(int layer)
            {
                var holder = new GameObject("Dog") { layer = layer };
                holder.transform.SetParent(root.transform, false);
                holder.transform.localPosition = new Vector3(Tuning.TitleLogoDogGrip, 0f, 0f);
                holder.transform.localRotation = Quaternion.Euler(0f, Tuning.TitleLogoDogYaw, 0f);
                var box = new Vector3(2f * Tuning.DogCapsuleRadius, Tuning.DogCapsuleHeight, 2f * Tuning.DogCapsuleRadius);
                string dogModel = DogModel;
                GameObject model = ModelKit.Instantiate(dogModel, holder.transform, box, ModelFit.Uniform, new ModelPaint { Main = DogTint });
                if (model == null)
                {
                    throw new InvalidOperationException("the dog model did not load");
                }
                // The paint gave the fur the dog row's tint (and the fur texture once it exists), as in the game.
                ModelCatalog.Entry entry = ModelCatalog.Lookup(dogModel);
                Animation animation = model.GetComponentInChildren<Animation>(true);
                AnimationState walk = animation != null && entry != null && !string.IsNullOrEmpty(entry.walkClip) ? animation[entry.walkClip] : null;
                if (walk == null || walk.clip == null)
                {
                    throw new InvalidOperationException("the dog has no Walk clip");
                }
                animation.playAutomatically = false;
                animation.Stop();
                SkinnedMeshRenderer[] skins = model.GetComponentsInChildren<SkinnedMeshRenderer>(true);
                if (skins.Length == 0)
                {
                    throw new InvalidOperationException("the dog has no skinned mesh");
                }
                // The dog's height in the game (its catalog height at the rig's eye scale, ears pricked as in the GLB's rest
                // pose): a baked copy far from it (the 2026-11-21 0.13 fit applied twice) is held to it; then every copy takes
                // the logo's own scale (DOGBIG: the bigger dog at full size would not fit between the frame's left edge and the
                // chair), scaled about the model's root, so the grip stays where the root stands.
                float expected = entry.nativeSize.y * ModelKit.RiggedScale(entry);
                // DOGBIG: the black Labrador's bigger head, hanging ears and low tail, as in the game (PetPose), on each sampled frame.
                // GRIP: frames 0 and 1 walk (the trot in and out); frames 2 and 3 bite (the drag): the same strides with the
                // bite's roll and open jaw and the neck bent nose down (GripMath) until the snout is at the chair's leg,
                // Tuning.TitleLogoDogBiteHeight over the floor (in the model's own size: the copies are scaled afterwards).
                PetPose petPose = PetPose.Find(model.transform, holder.transform.rotation);
                bool hasNeck = InhabitantRig.NeckChain(model.transform, holder.transform, out Transform[] neck, out _, out _, out _);
                var neckRest = new Quaternion[hasNeck ? neck.Length : 0];
                var poses = new GameObject[2 * DogFrames];
                var walkFactors = new float[DogFrames];
                var parts = new List<Transform>();
                for (int k = 0; k < poses.Length; k++)
                {
                    // Opposite strides: each frame at a foot contact, half a cycle apart.
                    float time = walk.clip.length * Mathf.Repeat(Tuning.DogFootContactCycle + (k % DogFrames) / (float)DogFrames, 1f);
                    walk.clip.SampleAnimation(animation.gameObject, time);
                    bool bite = k >= DogFrames;
                    if (bite && hasNeck)
                    {
                        // Measured on this stride's pose, then put back after the bake (no clip may key the neck).
                        InhabitantRig.NeckChain(model.transform, holder.transform, out neck, out _, out Vector2 neckBase, out Vector2[] segments);
                        for (int i = 0; i < neck.Length; i++)
                        {
                            neckRest[i] = neck[i].localRotation;
                        }
                        Vector2 headPlane = neckBase;
                        foreach (Vector2 s in segments)
                        {
                            headPlane += s;
                        }
                        var snout = new Vector2(Mathf.Max(0f, ModelKit.ForwardReach(entry) - headPlane.x), -Tuning.DogSnoutDrop) * Tuning.DogHeadScale;
                        // The head rides on the bent chain here (no rig resets it), which is a head following the neck fully.
                        float bend = GripMath.SolveNeckBend(neckBase, segments, snout, 1f, Tuning.TitleLogoDogBiteHeight / Tuning.TitleLogoDogScale);
                        InhabitantRig.BendNeck(neck, holder.transform.right, bend);
                        if (k == DogFrames)
                        {
                            Debug.Log($"[TitleLogo] the dog bites the chair's leg: neck bent {bend:0.0} deg, snout at "
                                + $"{GripMath.Tip(neckBase, segments, snout, bend, 1f).y * Tuning.TitleLogoDogScale:0.000} m");
                        }
                    }
                    petPose.Bite = bite ? 1f : 0f;
                    petPose.Apply(holder.transform.rotation, holder.transform.rotation);
                    var pose = new GameObject("DogPose" + k) { layer = layer };
                    pose.transform.SetParent(root.transform, false);
                    parts.Clear();
                    foreach (SkinnedMeshRenderer skin in skins)
                    {
                        var mesh = new Mesh { name = "TitleLogoDog" + k };
                        dogMeshes.Add(mesh);
                        // Without the renderer's scale: the skinned vertices are already world sized (2026-11-21: with
                        // its scale, the model's 0.13 fit was applied twice and the dog came out 5 cm tall).
                        skin.BakeMesh(mesh, false);
                        mesh.RecalculateBounds();
                        var part = new GameObject(skin.name) { layer = layer };
                        part.transform.SetParent(pose.transform, false);
                        part.transform.SetPositionAndRotation(skin.transform.position, skin.transform.rotation);
                        part.AddComponent<MeshFilter>().sharedMesh = mesh;
                        MeshRenderer renderer = part.AddComponent<MeshRenderer>();
                        renderer.sharedMaterials = skin.sharedMaterials;
                        renderer.shadowCastingMode = ShadowCastingMode.On;
                        renderer.receiveShadows = true;
                        parts.Add(part.transform);
                    }
                    // Whatever the bake's scale convention, the copy stands at the dog's height with its feet on the floor.
                    HeightOf(parts, out float low, out float high);
                    // The hanging ears make the posed dog up to about 15 % lower than its rest pose: only a gross mismatch is a
                    // scale convention error.
                    // GRIP: a biting frame (its head lowered, so lower than it stands) takes the factor of its walking stride.
                    bool wrongScale = high - low > 1e-4f && Mathf.Abs((high - low) / expected - 1f) > 0.25f;
                    float factor = bite ? walkFactors[k - DogFrames] : (wrongScale ? expected / (high - low) : 1f) * Tuning.TitleLogoDogScale;
                    if (!bite)
                    {
                        walkFactors[k] = factor;
                    }
                    if (Mathf.Abs(factor - 1f) > 1e-4f)
                    {
                        foreach (Transform part in parts)
                        {
                            part.localScale = Vector3.one * factor;
                        }
                        HeightOf(parts, out low, out high);
                    }
                    pose.transform.localPosition = new Vector3(0f, -low, 0f);
                    pose.SetActive(false);
                    poses[k] = pose;
                    if (bite && hasNeck)
                    {
                        for (int i = 0; i < neck.Length; i++)
                        {
                            neck[i].localRotation = neckRest[i];
                        }
                    }
                }
                petPose.Bite = 0f;
                model.SetActive(false);
                dogPoses = poses;
            }

            /// <summary>
            /// GRIP: the human of the alternate loops (the level 1 man, his faces and clothes through the game's own rig and
            /// CharacterLook, at Tuning.TitleLogoHumanScale), standing where he holds the chair on its mark
            /// (<see cref="HumanRoot"/>, turned Tuning.TitleLogoHumanYaw). Four static copies: walk frames 0 and 1 (his Walk
            /// clip at its two foot contacts), then the same strides with his hands on the top rail of the backrest (the game's
            /// arm IK, InhabitantRig.SolveArm, onto GripDef's chair wrists across the rail, the fingers over it).
            /// </summary>
            private void BuildHuman(int layer)
            {
                var go = new GameObject("Human") { layer = layer };
                go.transform.SetParent(root.transform, false);
                Vector2 at = HumanRoot;
                go.transform.localPosition = new Vector3(at.x, 0f, at.y);
                go.transform.localRotation = Quaternion.Euler(0f, Tuning.TitleLogoHumanYaw, 0f);
                go.transform.localScale = Vector3.one * Tuning.TitleLogoHumanScale;
                var visual = new GameObject("Visual") { layer = layer };
                visual.transform.SetParent(go.transform, false);
                var box = new Vector3(2f * Tuning.InhabitantRadius, Tuning.InhabitantHeight, 2f * Tuning.InhabitantRadius);
                GameObject model = ModelKit.Instantiate(HumanModel, visual.transform, box, ModelFit.Uniform, default);
                if (model == null)
                {
                    throw new InvalidOperationException("the human model did not load");
                }
                ModelCatalog.Entry entry = ModelCatalog.Lookup(HumanModel);
                // The game's rig dresses him (CharacterLook: the painted head, the clothes); then it stays off: the bake
                // poses the bones itself, once.
                Inhabitant inhabitant = go.AddComponent<Inhabitant>();
                inhabitant.Visual = visual.transform;
                InhabitantRig rig = InhabitantRig.Attach(inhabitant, model, entry);
                if (rig == null)
                {
                    throw new InvalidOperationException("the human model has no rig");
                }
                rig.enabled = false;
                inhabitant.enabled = false;
                AnimationState walk = rig.WalkState;
                if (walk == null || walk.clip == null || rig.Animation == null)
                {
                    throw new InvalidOperationException("the human has no Walk clip");
                }
                rig.Animation.Stop();
                SkinnedMeshRenderer[] skins = model.GetComponentsInChildren<SkinnedMeshRenderer>(true);
                if (skins.Length == 0)
                {
                    throw new InvalidOperationException("the human has no skinned mesh");
                }
                // The wrists on the rail and the fingers over it, in the chair's frame, then in the rig's world.
                GripDef grip = GripDef.For("chair");
                Transform chair = chairHolder.transform;
                Vector3 rightWrist = chair.TransformPoint(new Vector3(Tuning.TitleLogoHumanRightX, grip.RightWrist.y, grip.RightWrist.z));
                Vector3 leftWrist = chair.TransformPoint(new Vector3(Tuning.TitleLogoHumanLeftX, grip.LeftWrist.y, grip.LeftWrist.z));
                Vector3 rightFingers = chair.rotation * grip.RightFingers;
                Vector3 leftFingers = chair.rotation * grip.LeftFingers;
                Transform frame = visual.transform;
                float expected = entry.nativeSize.y * ModelKit.RiggedScale(entry) * Tuning.TitleLogoHumanScale;
                var poses = new GameObject[2 * DogFrames];
                var parts = new List<Transform>();
                for (int k = 0; k < poses.Length; k++)
                {
                    float time = walk.clip.length * Mathf.Repeat(Tuning.RigFootContactCycle + (k % DogFrames) / (float)DogFrames, 1f);
                    walk.clip.SampleAnimation(rig.Animation.gameObject, time);
                    if (k >= DogFrames)
                    {
                        // Which side each ".L" and ".R" arm hangs on, from the pose (the body's right is +x of its frame).
                        float leftSide = Vector3.Dot(rig.UpperArmLeft.position - frame.position, frame.right) > 0f ? 1f : -1f;
                        bool swap = leftSide > 0f;
                        Reach(rig.UpperArmLeft, rig.LowerArmLeft, rig.PalmLeft, swap ? rightWrist : leftWrist, swap ? rightFingers : leftFingers,
                            leftSide, frame);
                        Reach(rig.UpperArmRight, rig.LowerArmRight, rig.PalmRight, swap ? leftWrist : rightWrist, swap ? leftFingers : rightFingers,
                            -leftSide, frame);
                        if (k == DogFrames && rig.PalmRight != null && rig.PalmLeft != null)
                        {
                            Debug.Log($"[TitleLogo] the human's hands on the rail: right {Vector3.Distance(rig.PalmRight.position, swap ? leftWrist : rightWrist):0.000} m, "
                                + $"left {Vector3.Distance(rig.PalmLeft.position, swap ? rightWrist : leftWrist):0.000} m from their targets");
                        }
                    }
                    var pose = new GameObject("HumanPose" + k) { layer = layer };
                    pose.transform.SetParent(root.transform, false);
                    parts.Clear();
                    foreach (SkinnedMeshRenderer skin in skins)
                    {
                        var mesh = new Mesh { name = "TitleLogoHuman" + k };
                        dogMeshes.Add(mesh);
                        // Without the renderer's scale, as the dog's (the skinned vertices are already world sized, the
                        // human's own scale included).
                        skin.BakeMesh(mesh, false);
                        mesh.RecalculateBounds();
                        var part = new GameObject(skin.name) { layer = layer };
                        part.transform.SetParent(pose.transform, false);
                        part.transform.SetPositionAndRotation(skin.transform.position, skin.transform.rotation);
                        part.AddComponent<MeshFilter>().sharedMesh = mesh;
                        MeshRenderer renderer = part.AddComponent<MeshRenderer>();
                        renderer.sharedMaterials = skin.sharedMaterials;
                        renderer.shadowCastingMode = ShadowCastingMode.On;
                        renderer.receiveShadows = true;
                        parts.Add(part.transform);
                    }
                    HeightOf(parts, out float low, out float high);
                    if (k == 0)
                    {
                        Debug.Log($"[TitleLogo] the human: {high - low:0.000} m tall (expected about {expected:0.000}), feet at {low:0.000} m");
                    }
                    pose.SetActive(false);
                    poses[k] = pose;
                }
                model.SetActive(false);
                humanPoses = poses;
            }

            /// <summary>GRIP: one arm onto its wrist target, the elbow out to its side, down and back, then its fingers.</summary>
            private static void Reach(Transform upper, Transform lower, Transform palm, Vector3 wrist, Vector3 fingers, float side, Transform frame)
            {
                Vector3 pole = frame.rotation * new Vector3(side, -0.7f, -0.4f);
                InhabitantRig.SolveArm(upper, lower, palm, wrist, pole, 1f);
                InhabitantRig.AimBone(palm, fingers, 1f);
            }

            private void ShowHuman(int frame)
            {
                for (int k = 0; k < humanPoses.Length; k++)
                {
                    humanPoses[k].SetActive(k == frame);
                }
            }

            /// <summary>The lowest and highest points of <paramref name="parts"/>' meshes, in metres above the rig's floor.</summary>
            private void HeightOf(List<Transform> parts, out float low, out float high)
            {
                low = float.MaxValue;
                high = float.MinValue;
                foreach (Transform part in parts)
                {
                    Bounds b = part.GetComponent<MeshFilter>().sharedMesh.bounds;
                    for (int c = 0; c < 8; c++)
                    {
                        var corner = new Vector3((c & 1) == 0 ? b.min.x : b.max.x, (c & 2) == 0 ? b.min.y : b.max.y, (c & 4) == 0 ? b.min.z : b.max.z);
                        float y = root.transform.InverseTransformPoint(part.TransformPoint(corner)).y;
                        low = Mathf.Min(low, y);
                        high = Mathf.Max(high, y);
                    }
                }
            }

            private void ShowDog(int frame)
            {
                for (int k = 0; k < dogPoses.Length; k++)
                {
                    dogPoses[k].SetActive(k == frame);
                }
            }

            /// <summary>Renders both cameras into their targets now: the chair, then each dog frame alone; false (nothing
            /// rendered, cameras left to the next frame, and no dog) where the pipeline cannot take a render request.</summary>
            public bool Render()
            {
                var chairRequest = new RenderPipeline.StandardRequest { destination = chairTarget };
                var shadowRequest = new RenderPipeline.StandardRequest { destination = shadowTarget };
                if (!RenderPipeline.SupportsRenderRequest(chairCamera, chairRequest)
                    || !RenderPipeline.SupportsRenderRequest(shadowCamera, shadowRequest))
                {
                    // The dog's and the human's passes need render requests: the logo goes without them.
                    DropDog();
                    return false;
                }
                // Rendered once here, never again with the frame.
                chairCamera.enabled = false;
                shadowCamera.enabled = false;
                RenderPipeline.SubmitRenderRequest(chairCamera, chairRequest);
                RenderPipeline.SubmitRenderRequest(shadowCamera, shadowRequest);
                if (HasDog)
                {
                    // Each request culls the scene anew: the chair hidden, one dog frame shown at a time.
                    chairHolder.SetActive(false);
                    for (int k = 0; k < dogTargets.Length; k++)
                    {
                        ShowDog(k);
                        RenderPipeline.SubmitRenderRequest(chairCamera, new RenderPipeline.StandardRequest { destination = dogTargets[k] });
                        RenderPipeline.SubmitRenderRequest(shadowCamera, new RenderPipeline.StandardRequest { destination = dogShadowTargets[k] });
                    }
                    ShowDog(-1);
                    chairHolder.SetActive(true);
                }
                if (HasHuman)
                {
                    // GRIP: each human frame alone (colour and shadow), then each holding frame with the chair (the pair).
                    chairHolder.SetActive(false);
                    for (int k = 0; k < humanTargets.Length; k++)
                    {
                        ShowHuman(k);
                        RenderPipeline.SubmitRenderRequest(chairCamera, new RenderPipeline.StandardRequest { destination = humanTargets[k] });
                        RenderPipeline.SubmitRenderRequest(shadowCamera, new RenderPipeline.StandardRequest { destination = humanShadowTargets[k] });
                    }
                    chairHolder.SetActive(true);
                    for (int k = 0; k < pairTargets.Length; k++)
                    {
                        ShowHuman(DogFrames + k);
                        RenderPipeline.SubmitRenderRequest(chairCamera, new RenderPipeline.StandardRequest { destination = pairTargets[k] });
                    }
                    ShowHuman(-1);
                }
                return true;
            }

            private void DropDog()
            {
                if (dogPoses != null)
                {
                    ShowDog(-1);
                }
                dogPoses = null;
                if (humanPoses != null)
                {
                    ShowHuman(-1);
                }
                humanPoses = null;
            }

            private static Quaternion Frame(Vector3 forward)
            {
                Vector3 up = Vector3.up - Vector3.Dot(Vector3.up, forward) * forward;
                if (up.sqrMagnitude < 1e-4f)
                {
                    up = Vector3.forward;
                }
                return Quaternion.LookRotation(forward, up.normalized);
            }

            /// <summary>The projection onto the plane through <paramref name="point"/> of normal <paramref name="normal"/>, along <paramref name="direction"/>.</summary>
            private static Matrix4x4 Projection(Vector3 normal, Vector3 point, Vector3 direction)
            {
                float nd = Vector3.Dot(normal, direction);
                float np = Vector3.Dot(normal, point);
                Matrix4x4 m = Matrix4x4.identity;
                for (int r = 0; r < 3; r++)
                {
                    for (int c = 0; c < 3; c++)
                    {
                        m[r, c] = (r == c ? 1f : 0f) - direction[r] * normal[c] / nd;
                    }
                    m[r, 3] = direction[r] * np / nd;
                }
                return m;
            }

            private static RenderTexture NewTarget(string name)
            {
                var rt = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB)
                {
                    name = name,
                    antiAliasing = 1,
                };
                rt.Create();
                return rt;
            }

            private Camera NewCamera(string name, RenderTexture target, bool shadows)
            {
                float pitch = Tuning.TitleLogoPitch;
                float frameWidth = Tuning.TitleLogoFrameWidth;
                float frameHeight = frameWidth * Height / Width;
                Quaternion look = Quaternion.Euler(pitch, 0f, 0f);
                Vector3 right = Vector3.right;
                Vector3 up = look * Vector3.up;
                Vector3 forward = look * Vector3.forward;
                // The chair's foot (the rig origin) sits TitleLogoChairInset from the left edge, TitleLogoFootHeight up.
                Vector3 aim = right * (frameWidth * 0.5f - Tuning.TitleLogoChairInset) + up * (frameHeight * (0.5f - Tuning.TitleLogoFootHeight));

                var go = new GameObject(name) { layer = Tuning.TitleLogoLayer };
                go.transform.SetParent(root.transform, false);
                go.transform.localRotation = look;
                go.transform.localPosition = aim - forward * 8f;
                Camera cam = go.AddComponent<Camera>();
                cam.orthographic = true;
                cam.orthographicSize = frameHeight * 0.5f;
                cam.aspect = Width / (float)Height;
                cam.nearClipPlane = 0.1f;
                cam.farClipPlane = 30f;
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0f, 0f, 0f, 0f);
                cam.cullingMask = 1 << Tuning.TitleLogoLayer;
                cam.allowHDR = false;
                cam.allowMSAA = false;
                cam.useOcclusionCulling = false;
                cam.depth = -50f;
                cam.targetTexture = target;
                UniversalAdditionalCameraData data = cam.GetUniversalAdditionalCameraData();
                data.renderPostProcessing = false;
                data.antialiasing = AntialiasingMode.None;
                data.renderShadows = shadows;
                data.requiresColorOption = CameraOverrideOption.Off;
                data.requiresDepthOption = CameraOverrideOption.Off;
                return cam;
            }

            private Color32[] chairPixels;
            private Color32[] shadowPixels;
            private Vector2 g00;
            private Vector2 gx;
            private Vector2 gy;

            /// <summary>
            /// Reads both targets back without stalling the frame where the platform can (AsyncGPUReadback), over a few
            /// frames; a synchronous read otherwise, or if the request fails. Then takes the ground mapping from the camera,
            /// so the composition needs nothing from the rig afterwards (it can be disposed).
            /// </summary>
            public IEnumerator ReadBack()
            {
                // The chair's two targets, then each dog frame's two, then each human frame's two and the pairs.
                var list = new List<RenderTexture> { chairTarget, shadowTarget };
                for (int k = 0; HasDog && k < dogTargets.Length; k++)
                {
                    list.Add(dogTargets[k]);
                    list.Add(dogShadowTargets[k]);
                }
                for (int k = 0; HasHuman && k < humanTargets.Length; k++)
                {
                    list.Add(humanTargets[k]);
                    list.Add(humanShadowTargets[k]);
                }
                for (int k = 0; HasHuman && k < pairTargets.Length; k++)
                {
                    list.Add(pairTargets[k]);
                }
                RenderTexture[] targets = list.ToArray();
                int count = targets.Length;
                var pixels = new Color32[count][];
                if (SystemInfo.supportsAsyncGPUReadback)
                {
                    var requests = new AsyncGPUReadbackRequest[count];
                    for (int t = 0; t < count; t++)
                    {
                        requests[t] = AsyncGPUReadback.Request(targets[t], 0, TextureFormat.RGBA32);
                    }
                    for (int i = 0; i < 30 && !AllDone(requests); i++)
                    {
                        yield return null;
                    }
                    for (int t = 0; t < count; t++)
                    {
                        requests[t].WaitForCompletion();
                        if (!requests[t].hasError)
                        {
                            pixels[t] = requests[t].GetData<Color32>().ToArray();
                        }
                    }
                }
                for (int t = 0; t < count; t++)
                {
                    if (pixels[t] == null)
                    {
                        pixels[t] = Read(targets[t]);
                    }
                }
                chairPixels = pixels[0];
                shadowPixels = pixels[1];
                int next = 2;
                if (HasDog)
                {
                    dogPixels = new Color32[dogTargets.Length][];
                    dogShadowPixels = new Color32[dogTargets.Length][];
                    for (int k = 0; k < dogTargets.Length; k++)
                    {
                        dogPixels[k] = pixels[next++];
                        dogShadowPixels[k] = pixels[next++];
                    }
                }
                if (HasHuman)
                {
                    humanPixels = new Color32[humanTargets.Length][];
                    humanShadowPixels = new Color32[humanTargets.Length][];
                    pairPixels = new Color32[pairTargets.Length][];
                    for (int k = 0; k < humanTargets.Length; k++)
                    {
                        humanPixels[k] = pixels[next++];
                        humanShadowPixels[k] = pixels[next++];
                    }
                    for (int k = 0; k < pairTargets.Length; k++)
                    {
                        pairPixels[k] = pixels[next++];
                    }
                }
                // Ground coordinates of the pixel centres, affine in an orthographic view: three corners give the map.
                g00 = Ground(0f, 0f);
                gx = (Ground(1f, 0f) - g00) / Tuning.TitleLogoWidth;
                gy = (Ground(0f, 1f) - g00) / Tuning.TitleLogoHeight;
            }

            /// <summary>The logo's atlas from <see cref="Compose"/>'s layers (main thread).</summary>
            public static Texture2D MakeTexture(Layers layers)
            {
                var texture = new Texture2D(layers.AtlasWidth, layers.AtlasHeight, TextureFormat.RGBA32, false, false)
                {
                    name = "TitleLogo",
                    wrapMode = TextureWrapMode.Clamp,
                    filterMode = FilterMode.Bilinear,
                };
                texture.SetPixels32(layers.Atlas);
                // Readable (about 800 KB) only where the probes run (the editor, development builds): they check the
                // pool and the shadow in it. A release build keeps the GPU copy only.
                texture.Apply(false, !Debug.isDebugBuild);
                layers.Atlas = null;
                return texture;
            }

            /// <summary>Composes the logo's three layers (straight alpha, sRGB) at Tuning.TitleLogoWidth x Height from the
            /// read back targets and packs them in one atlas. Pure arithmetic on arrays, safe off the main thread (the bake
            /// runs it on a worker so the title's frames never stall).</summary>
            public Layers Compose()
            {
                int w = Tuning.TitleLogoWidth;
                int h = Tuning.TitleLogoHeight;
                // Should the target drop the alpha (all opaque), tell the chair from the cleared black by its colour.
                bool alpha = chairPixels[0].a < 128;

                var chair = new Color[w * h];
                var mask = new float[w * h];
                for (int y = 0; y < h; y++)
                {
                    for (int x = 0; x < w; x++)
                    {
                        Color sum = Color.clear;
                        float shadow = 0f;
                        for (int k = 0; k < 4; k++)
                        {
                            int i = (2 * y + (k >> 1)) * Width + 2 * x + (k & 1);
                            Color32 c = chairPixels[i];
                            float a = alpha ? c.a / 255f : Mathf.Max(c.r, Mathf.Max(c.g, c.b)) > 3 ? 1f : 0f;
                            sum += new Color(c.r / 255f, c.g / 255f, c.b / 255f, a);
                            Color32 s = shadowPixels[i];
                            shadow += alpha ? s.a / 255f : Mathf.Max(s.r, Mathf.Max(s.g, s.b)) > 3 ? 1f : 0f;
                        }
                        chair[y * w + x] = sum * 0.25f;
                        mask[y * w + x] = shadow * 0.25f;
                    }
                }
                float[] soft = Blur(Blur(mask, w, h, Tuning.TitleLogoShadowBlur), w, h, Tuning.TitleLogoShadowBlur);

                // The three layers, each with its colour defined on every pixel (even where it is transparent), so the
                // bilinear filter never pulls a black fringe in at their soft edges.
                var poolLayer = new Color[w * h];
                var shadowLayer = new Color[w * h];
                var chairLayer = new Color[w * h];
                var poolCentre = new Vector2(Tuning.TitleLogoPoolCentre, 0f);
                float brightest = -1f;
                float darkest = -1f;
                float leastLight = 1f;
                for (int y = 0; y < h; y++)
                {
                    for (int x = 0; x < w; x++)
                    {
                        int i = y * w + x;
                        Vector2 g = g00 + gx * (x + 0.5f) + gy * (y + 0.5f);
                        float along = g.x;
                        float t = Mathf.Clamp01(along / shadowLength);

                        // The pool of light: a lit plateau a little hotter at its heart, then a soft falloff to nothing at
                        // the radius, like a spot's penumbra, warming from cream to amber outward.
                        float light = PoolLightAt(g - poolCentre);
                        Color ground = Color.Lerp(PoolRim, PoolCore, Mathf.Sqrt(light));
                        // Light over the dark title band: the pool's opacity is its light (with a faint dither so the
                        // 8 bit gradient does not band).
                        float dither = light > 0f ? (Hash(x, y) - 0.5f) / 255f : 0f;
                        float groundAlpha = Mathf.Clamp01(light * Tuning.TitleLogoPoolAlpha + dither);
                        poolLayer[i] = new Color(ground.r, ground.g, ground.b, groundAlpha);
                        // The chair's shadow darkens that light: sharp and deep at the foot, softer toward the tip. Drawn
                        // over the pool as ink times the pool's opacity, at the shade's opacity, it gives exactly the old
                        // single image's floor, lerp(pool, ink, shade) at the pool's opacity, over a dark band.
                        float shade = Mathf.Lerp(mask[i], soft[i], Mathf.SmoothStep(0f, 1f, t))
                            * Mathf.Lerp(Tuning.TitleLogoShadowNear, Tuning.TitleLogoShadowFar, t);
                        Color ink = ShadowInk * (light * Tuning.TitleLogoPoolAlpha);
                        shadowLayer[i] = new Color(ink.r, ink.g, ink.b, shade);

                        Color c = chair[i];
                        if (c.a < 0.01f)
                        {
                            if (shade < 0.02f && light > brightest)
                            {
                                brightest = light;
                                PoolPixel = new Vector2Int(x, y);
                            }
                            if (shade > darkest)
                            {
                                darkest = shade;
                                ShadowPixel = new Vector2Int(x, y);
                            }
                            if (mask[i] > 0.05f)
                            {
                                leastLight = Mathf.Min(leastLight, light);
                            }
                        }
                        if (c.a > 1e-4f)
                        {
                            // The graphic treatment: a gamma curve on the chair deepens the lacquer red and its shaded side
                            // (the chair is premultiplied by its coverage here; the layer keeps it straight).
                            float a = c.a;
                            chairLayer[i] = new Color(
                                Mathf.Pow(Mathf.Clamp01(c.r / a), ChairCurve),
                                Mathf.Pow(Mathf.Clamp01(c.g / a), ChairCurve),
                                Mathf.Pow(Mathf.Clamp01(c.b / a), ChairCurve),
                                Mathf.Clamp01(a));
                        }
                    }
                }
                ShadowInPool = leastLight;

                RectInt chairRect = Bounds(chairLayer, w, h, 2);
                if (chairRect.width <= 0)
                {
                    throw new InvalidOperationException("the chair did not render");
                }
                RectInt shadowRect = Bounds(shadowLayer, w, h, 2);
                if (shadowRect.width <= 0)
                {
                    shadowRect = new RectInt(0, 0, 1, 1);
                }
                Bleed(chairLayer, w, chairRect, 3);

                // The extra layers, in shelves above the chair's row: the dog's frames and their shadows (when the dog was
                // baked), GRIP: then the human's frames and their shadows and the pairs (when he was).
                int row = h + Mathf.Max(chairRect.height, shadowRect.height);
                var extra = new List<Color[]>();
                var extraRects = new List<RectInt>();
                int dogStart = 0;
                int humanStart = 0;
                bool hasDog = dogPixels != null && dogShadowPixels != null && AddBodies(dogPixels, dogShadowPixels, alpha, extra, extraRects, out dogStart);
                bool hasHuman = humanPixels != null && humanShadowPixels != null && pairPixels != null
                    && AddBodies(humanPixels, humanShadowPixels, alpha, extra, extraRects, out humanStart);
                int pairStart = extra.Count;
                for (int k = 0; hasHuman && k < pairPixels.Length; k++)
                {
                    Color[] pair = PairLayer(pairPixels[k], humanPixels[DogFrames + k], alpha);
                    RectInt rect = Bounds(pair, w, h, 2);
                    if (rect.width <= 0)
                    {
                        // Never half a human: the logo goes without him (his loops then show the dog's).
                        hasHuman = false;
                        break;
                    }
                    Bleed(pair, w, rect, 3);
                    extra.Add(pair);
                    extraRects.Add(rect);
                }
                if (!hasHuman)
                {
                    humanStart = 0;
                }
                if (!hasHuman && extra.Count > (hasDog ? 4 * DogFrames : 0))
                {
                    // Drop the human's half built layers.
                    int keep = hasDog ? 4 * DogFrames : 0;
                    extra.RemoveRange(keep, extra.Count - keep);
                    extraRects.RemoveRange(keep, extraRects.Count - keep);
                }
                // Shelves, left to right, a new one above when the next crop would pass the widest the atlas may grow.
                int maxWidth = Mathf.Max(w, 1024);
                var at = new Vector2Int[extra.Count];
                int sx = 0;
                int sy = row;
                int shelf = 0;
                int widest = 0;
                for (int i = 0; i < extra.Count; i++)
                {
                    RectInt rect = extraRects[i];
                    if (sx > 0 && sx + rect.width > maxWidth)
                    {
                        sy += shelf;
                        sx = 0;
                        shelf = 0;
                    }
                    at[i] = new Vector2Int(sx, sy);
                    sx += rect.width;
                    shelf = Mathf.Max(shelf, rect.height);
                    widest = Mathf.Max(widest, sx);
                }

                var layers = new Layers
                {
                    Width = w,
                    Height = h,
                    AtlasWidth = Mathf.Max(w, Mathf.Max(chairRect.width + shadowRect.width, widest)),
                    AtlasHeight = sy + shelf,
                    PoolAt = Vector2Int.zero,
                    ChairRect = chairRect,
                    ChairAt = new Vector2Int(0, h),
                    ShadowRect = shadowRect,
                    ShadowAt = new Vector2Int(chairRect.width, h),
                    HasDog = hasDog,
                    HasHuman = hasHuman,
                };
                layers.Atlas = new Color32[layers.AtlasWidth * layers.AtlasHeight];
                Blit(poolLayer, w, new RectInt(0, 0, w, h), layers.Atlas, layers.AtlasWidth, layers.PoolAt);
                Blit(chairLayer, w, chairRect, layers.Atlas, layers.AtlasWidth, layers.ChairAt);
                Blit(shadowLayer, w, shadowRect, layers.Atlas, layers.AtlasWidth, layers.ShadowAt);
                for (int i = 0; i < extra.Count; i++)
                {
                    Blit(extra[i], w, extraRects[i], layers.Atlas, layers.AtlasWidth, at[i]);
                }
                if (hasDog)
                {
                    Unpack(extraRects, at, dogStart, 2 * DogFrames, out layers.DogRect, out layers.DogAt, out layers.DogShadowRect, out layers.DogShadowAt);
                }
                if (hasHuman)
                {
                    Unpack(extraRects, at, humanStart, 2 * DogFrames, out layers.HumanRect, out layers.HumanAt, out layers.HumanShadowRect,
                        out layers.HumanShadowAt);
                    layers.PairRect = new RectInt[DogFrames];
                    layers.PairAt = new Vector2Int[DogFrames];
                    for (int k = 0; k < DogFrames; k++)
                    {
                        layers.PairRect[k] = extraRects[pairStart + k];
                        layers.PairAt[k] = at[pairStart + k];
                    }
                }
                return layers;
            }

            /// <summary>One dog frame at Tuning.TitleLogoWidth x Height (straight alpha), averaged down from its target,
            /// and its shadow: a soft darkening of full pool light (the runtime fades it with the pool's light where the dog
            /// stands), its colour defined on every pixel.</summary>
            private static void DogLayers(Color32[] colour, Color32[] shadow, bool alpha, out Color[] dog, out Color[] dogShadow)
            {
                int w = Tuning.TitleLogoWidth;
                int h = Tuning.TitleLogoHeight;
                dog = new Color[w * h];
                var mask = new float[w * h];
                for (int y = 0; y < h; y++)
                {
                    for (int x = 0; x < w; x++)
                    {
                        Color sum = Color.clear;
                        float covered = 0f;
                        for (int k = 0; k < 4; k++)
                        {
                            int i = (2 * y + (k >> 1)) * Width + 2 * x + (k & 1);
                            Color32 c = colour[i];
                            float a = alpha ? c.a / 255f : Mathf.Max(c.r, Mathf.Max(c.g, c.b)) > 3 ? 1f : 0f;
                            sum += new Color(c.r / 255f, c.g / 255f, c.b / 255f, a);
                            Color32 s = shadow[i];
                            covered += alpha ? s.a / 255f : Mathf.Max(s.r, Mathf.Max(s.g, s.b)) > 3 ? 1f : 0f;
                        }
                        sum *= 0.25f;
                        if (sum.a > 1e-4f)
                        {
                            float a = sum.a;
                            dog[y * w + x] = new Color(Mathf.Clamp01(sum.r / a), Mathf.Clamp01(sum.g / a), Mathf.Clamp01(sum.b / a), Mathf.Clamp01(a));
                        }
                        mask[y * w + x] = covered * 0.25f;
                    }
                }
                float[] soft = Blur(Blur(mask, w, h, DogShadowBlur), w, h, DogShadowBlur);
                Color ink = ShadowInk * Tuning.TitleLogoPoolAlpha;
                dogShadow = new Color[w * h];
                for (int i = 0; i < dogShadow.Length; i++)
                {
                    dogShadow[i] = new Color(ink.r, ink.g, ink.b, soft[i] * Tuning.TitleLogoDogShadow);
                }
            }

            // The dog's shadow's softness, in logo pixels (its shadow is short and small).
            private const int DogShadowBlur = 2;

            /// <summary>
            /// The layers of a body's frames (the dog's or the human's), each frame then its shadow, cropped and bled, appended to
            /// <paramref name="extra"/> from <paramref name="start"/>; nothing appended and false when a frame did not render.
            /// </summary>
            private static bool AddBodies(Color32[][] colours, Color32[][] shadows, bool alpha, List<Color[]> extra, List<RectInt> rects, out int start)
            {
                int w = Tuning.TitleLogoWidth;
                int h = Tuning.TitleLogoHeight;
                start = extra.Count;
                var layers = new List<Color[]>();
                var crops = new List<RectInt>();
                for (int k = 0; k < colours.Length; k++)
                {
                    DogLayers(colours[k], shadows[k], alpha, out Color[] body, out Color[] shadow);
                    RectInt rect = Bounds(body, w, h, 2);
                    if (rect.width <= 0)
                    {
                        return false;
                    }
                    Bleed(body, w, rect, 3);
                    RectInt shadowRect = Bounds(shadow, w, h, 2);
                    if (shadowRect.width <= 0)
                    {
                        shadowRect = new RectInt(0, 0, 1, 1);
                    }
                    layers.Add(body);
                    crops.Add(rect);
                    layers.Add(shadow);
                    crops.Add(shadowRect);
                }
                extra.AddRange(layers);
                rects.AddRange(crops);
                return true;
            }

            /// <summary>The crops and atlas places of <paramref name="count"/> frames appended by <see cref="AddBodies"/>.</summary>
            private static void Unpack(List<RectInt> rects, Vector2Int[] at, int start, int count, out RectInt[] frameRects, out Vector2Int[] frameAt,
                out RectInt[] shadowRects, out Vector2Int[] shadowAt)
            {
                frameRects = new RectInt[count];
                frameAt = new Vector2Int[count];
                shadowRects = new RectInt[count];
                shadowAt = new Vector2Int[count];
                for (int k = 0; k < count; k++)
                {
                    frameRects[k] = rects[start + 2 * k];
                    frameAt[k] = at[start + 2 * k];
                    shadowRects[k] = rects[start + 2 * k + 1];
                    shadowAt[k] = at[start + 2 * k + 1];
                }
            }

            /// <summary>
            /// GRIP: one pair frame (the chair and the human holding it, rendered together), straight alpha at the logo's size.
            /// Each rendered sample is the human's where it matches the human rendered alone better than the chair rendered
            /// alone (his hands on the rail, his arms in front), else the chair's (the backrest hiding him, his shadow on the
            /// seat), which then takes the chair layer's gamma curve: drawn over the chair's layer, the chair's pixels stay
            /// the chair's.
            /// </summary>
            private Color[] PairLayer(Color32[] pair, Color32[] human, bool alpha)
            {
                int w = Tuning.TitleLogoWidth;
                int h = Tuning.TitleLogoHeight;
                var px = new Color[w * h];
                for (int y = 0; y < h; y++)
                {
                    for (int x = 0; x < w; x++)
                    {
                        Color sum = Color.clear;
                        for (int k = 0; k < 4; k++)
                        {
                            int i = (2 * y + (k >> 1)) * Width + 2 * x + (k & 1);
                            Color32 p = pair[i];
                            if (!Covered(p, alpha))
                            {
                                continue;
                            }
                            Color32 hu = human[i];
                            Color32 ch = chairPixels[i];
                            float toHuman = Covered(hu, alpha) ? Distance(p, hu) : float.MaxValue;
                            float toChair = Covered(ch, alpha) ? Distance(p, ch) : float.MaxValue;
                            var c = new Color(p.r / 255f, p.g / 255f, p.b / 255f, 1f);
                            if (toHuman > toChair)
                            {
                                c = new Color(Mathf.Pow(c.r, ChairCurve), Mathf.Pow(c.g, ChairCurve), Mathf.Pow(c.b, ChairCurve), 1f);
                            }
                            sum += c;
                        }
                        sum *= 0.25f;
                        if (sum.a > 1e-4f)
                        {
                            float a = sum.a;
                            px[y * w + x] = new Color(Mathf.Clamp01(sum.r / a), Mathf.Clamp01(sum.g / a), Mathf.Clamp01(sum.b / a), Mathf.Clamp01(a));
                        }
                    }
                }
                return px;
            }

            private static bool Covered(Color32 c, bool alpha) => alpha ? c.a >= 128 : Mathf.Max(c.r, Mathf.Max(c.g, c.b)) > 3;

            private static float Distance(Color32 a, Color32 b)
            {
                int dr = a.r - b.r;
                int dg = a.g - b.g;
                int db = a.b - b.b;
                return dr * dr + dg * dg + db * db;
            }

            /// <summary>The pixels of <paramref name="px"/> with any opacity, plus <paramref name="pad"/> transparent ones
            /// around (inside the frame); empty when none.</summary>
            private static RectInt Bounds(Color[] px, int w, int h, int pad)
            {
                int x0 = w;
                int y0 = h;
                int x1 = -1;
                int y1 = -1;
                for (int y = 0; y < h; y++)
                {
                    for (int x = 0; x < w; x++)
                    {
                        if (px[y * w + x].a > 1f / 512f)
                        {
                            x0 = Mathf.Min(x0, x);
                            x1 = Mathf.Max(x1, x);
                            y0 = Mathf.Min(y0, y);
                            y1 = Mathf.Max(y1, y);
                        }
                    }
                }
                if (x1 < 0)
                {
                    return new RectInt(0, 0, 0, 0);
                }
                x0 = Mathf.Max(0, x0 - pad);
                y0 = Mathf.Max(0, y0 - pad);
                x1 = Mathf.Min(w - 1, x1 + pad);
                y1 = Mathf.Min(h - 1, y1 + pad);
                return new RectInt(x0, y0, x1 - x0 + 1, y1 - y0 + 1);
            }

            /// <summary>Spreads the colour of the opaque pixels into the transparent ones around them (alpha unchanged),
            /// <paramref name="passes"/> pixels deep, inside <paramref name="r"/>.</summary>
            private static void Bleed(Color[] px, int w, RectInt r, int passes)
            {
                var known = new bool[px.Length];
                for (int y = r.yMin; y < r.yMax; y++)
                {
                    for (int x = r.xMin; x < r.xMax; x++)
                    {
                        known[y * w + x] = px[y * w + x].a > 0f;
                    }
                }
                var grown = new bool[px.Length];
                for (int pass = 0; pass < passes; pass++)
                {
                    for (int y = r.yMin; y < r.yMax; y++)
                    {
                        for (int x = r.xMin; x < r.xMax; x++)
                        {
                            int i = y * w + x;
                            if (known[i])
                            {
                                continue;
                            }
                            Color sum = Color.clear;
                            int n = 0;
                            if (x > r.xMin && known[i - 1]) { sum += px[i - 1]; n++; }
                            if (x < r.xMax - 1 && known[i + 1]) { sum += px[i + 1]; n++; }
                            if (y > r.yMin && known[i - w]) { sum += px[i - w]; n++; }
                            if (y < r.yMax - 1 && known[i + w]) { sum += px[i + w]; n++; }
                            if (n > 0)
                            {
                                px[i] = new Color(sum.r / n, sum.g / n, sum.b / n, 0f);
                                grown[i] = true;
                            }
                        }
                    }
                    for (int y = r.yMin; y < r.yMax; y++)
                    {
                        for (int x = r.xMin; x < r.xMax; x++)
                        {
                            int i = y * w + x;
                            known[i] |= grown[i];
                            grown[i] = false;
                        }
                    }
                }
            }

            private static void Blit(Color[] src, int srcWidth, RectInt from, Color32[] dst, int dstWidth, Vector2Int to)
            {
                for (int y = 0; y < from.height; y++)
                {
                    for (int x = 0; x < from.width; x++)
                    {
                        dst[(to.y + y) * dstWidth + to.x + x] = src[(from.y + y) * srcWidth + from.x + x];
                    }
                }
            }

            /// <summary>A cheap per pixel hash in [0, 1), for the dither.</summary>
            private static float Hash(int x, int y)
            {
                uint n = (uint)(x * 73856093) ^ (uint)(y * 19349663);
                n = (n ^ (n >> 13)) * 1274126177u;
                return (n & 0xFFFF) / 65536f;
            }

            /// <summary>The rig ground point under a viewport point, as (along the shadow, across it) in metres.</summary>
            private Vector2 Ground(float u, float v)
            {
                Ray ray = chairCamera.ViewportPointToRay(new Vector3(u, v, 0f));
                Transform frame = root.transform;
                var plane = new Plane(frame.up, frame.position);
                plane.Raycast(ray, out float distance);
                Vector3 p = frame.InverseTransformPoint(ray.GetPoint(distance));
                return new Vector2(p.x * horizontal.x + p.z * horizontal.z, -p.x * horizontal.z + p.z * horizontal.x);
            }

            private static Color32[] Read(RenderTexture target)
            {
                RenderTexture previous = RenderTexture.active;
                var texture = new Texture2D(target.width, target.height, TextureFormat.RGBA32, false, false);
                try
                {
                    RenderTexture.active = target;
                    texture.ReadPixels(new Rect(0, 0, target.width, target.height), 0, 0, false);
                    texture.Apply(false);
                    return texture.GetPixels32();
                }
                finally
                {
                    RenderTexture.active = previous;
                    Object.Destroy(texture);
                }
            }

            /// <summary>A separable box blur of <paramref name="radius"/> pixels (two passes approach a gaussian).</summary>
            private static float[] Blur(float[] src, int w, int h, int radius)
            {
                var tmp = new float[src.Length];
                var dst = new float[src.Length];
                float norm = 1f / (2 * radius + 1);
                for (int y = 0; y < h; y++)
                {
                    float sum = 0f;
                    for (int k = -radius; k <= radius; k++)
                    {
                        sum += src[y * w + Mathf.Clamp(k, 0, w - 1)];
                    }
                    for (int x = 0; x < w; x++)
                    {
                        tmp[y * w + x] = sum * norm;
                        sum += src[y * w + Mathf.Min(x + radius + 1, w - 1)] - src[y * w + Mathf.Max(x - radius, 0)];
                    }
                }
                for (int x = 0; x < w; x++)
                {
                    float sum = 0f;
                    for (int k = -radius; k <= radius; k++)
                    {
                        sum += tmp[Mathf.Clamp(k, 0, h - 1) * w + x];
                    }
                    for (int y = 0; y < h; y++)
                    {
                        dst[y * w + x] = sum * norm;
                        sum += tmp[Mathf.Min(y + radius + 1, h - 1) * w + x] - tmp[Mathf.Max(y - radius, 0) * w + x];
                    }
                }
                return dst;
            }

            public void Dispose()
            {
                if (root != null)
                {
                    Object.Destroy(root);
                    root = null;
                }
                Release(chairTarget);
                Release(shadowTarget);
                for (int k = 0; dogTargets != null && k < dogTargets.Length; k++)
                {
                    Release(dogTargets[k]);
                    Release(dogShadowTargets[k]);
                }
                for (int k = 0; humanTargets != null && k < humanTargets.Length; k++)
                {
                    Release(humanTargets[k]);
                    Release(humanShadowTargets[k]);
                }
                for (int k = 0; pairTargets != null && k < pairTargets.Length; k++)
                {
                    Release(pairTargets[k]);
                }
                chairTarget = null;
                shadowTarget = null;
                dogTargets = null;
                dogShadowTargets = null;
                humanTargets = null;
                humanShadowTargets = null;
                pairTargets = null;
                foreach (Mesh mesh in dogMeshes)
                {
                    if (mesh != null)
                    {
                        Object.Destroy(mesh);
                    }
                }
                dogMeshes.Clear();
            }

            private static void Release(RenderTexture rt)
            {
                if (rt != null)
                {
                    rt.Release();
                    Object.Destroy(rt);
                }
            }

            private static bool AllDone(AsyncGPUReadbackRequest[] requests)
            {
                foreach (AsyncGPUReadbackRequest r in requests)
                {
                    if (!r.done)
                    {
                        return false;
                    }
                }
                return true;
            }
        }
    }
}
