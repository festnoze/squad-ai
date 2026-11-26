using System.Collections.Generic;
using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>
    /// How a model is painted at instantiate time (docs/CONTRACT_M3.md 3, colours). Every colour is sRGB.
    /// </summary>
    public struct ModelPaint
    {
        /// <summary>When set, the main material (the source material with the most triangles) takes this colour.</summary>
        public Color? Main;

        /// <summary>
        /// When set, every red source colour (<see cref="ModelMath.IsRed"/>) becomes this colour, darkened by
        /// the ratio of its value to the brightest red of the model. Unset: <see cref="ModelMath.DefaultRedTarget"/>.
        /// </summary>
        public Color? Red;
    }

    /// <summary>
    /// Pure math of the M3 model pipeline (docs/CONTRACT_M3.md 3): fit scale, recentring, sRGB colour
    /// quantisation, the red test and colour mapping. Core-only, so EditMode tests need no scene.
    ///
    /// Frames: a model's native bounds are measured in its own root space (root at the origin, no rotation,
    /// unit scale). The fit then gives the root a local position, a yaw (<c>yawOffset</c>, a multiple of 90)
    /// and a scale under its parent, so the bounds fill the gameplay box: centred on x and z, bottom on y = 0.
    /// </summary>
    public static class ModelMath
    {
        /// <summary>sRGB quantisation step (CONTRACT_M3 3): near-identical imported colours share one material.</summary>
        public const float QuantStep = 1f / 64f;

        /// <summary>
        /// A colour whose every channel, in LINEAR space, is below this is a near-black: they all merge into one
        /// (M3.1: in sRGB nothing of the man merged; in linear his eyes and hair do, and the woman's six darks).
        /// </summary>
        public const float NearBlackMax = 0.08f;

        /// <summary>The red test (CONTRACT_M3 3): hue within this many degrees of 0.</summary>
        public const float RedHueRange = 20f;
        public const float RedMinSaturation = 0.5f;
        public const float RedMinValue = 0.35f;

        /// <summary>
        /// The one material every near-black merges into (sRGB, on the quantisation grid): a dark grey near the
        /// mean of what merges (eyes 0.15, hair 0.18 to 0.29, the woman's trousers 0.23), itself a near-black.
        /// </summary>
        public static readonly Color NearBlack = new Color(12f / 64f, 12f / 64f, 12f / 64f, 1f);

        /// <summary>
        /// Where a red goes when the caller names no target: the dark wood already used by the books and the
        /// decoys, never red (PRD 7.2 keeps red for the player furniture).
        /// </summary>
        public static readonly Color DefaultRedTarget = new Color32(0x8C, 0x5A, 0x36, 0xFF);

        private const float Eps = 1e-6f;

        // ----- Yaw -----

        /// <summary>The yaw snapped to the nearest multiple of 90, in [0, 360).</summary>
        public static float SnapYaw(float yawDeg)
        {
            float snapped = Mathf.Round(yawDeg / 90f) * 90f;
            snapped %= 360f;
            return snapped < 0f ? snapped + 360f : snapped;
        }

        /// <summary>True when the yaw is a multiple of 90 (catalog yaw offsets must be).</summary>
        public static bool IsRightAngle(float yawDeg)
        {
            return Mathf.Abs(Mathf.DeltaAngle(yawDeg, SnapYaw(yawDeg))) < 1e-3f;
        }

        /// <summary>True for 90 and 270: the model's x axis lies along the parent's z axis.</summary>
        public static bool IsQuarterTurn(float yawDeg)
        {
            float s = SnapYaw(yawDeg);
            return Mathf.Abs(s - 90f) < 1e-3f || Mathf.Abs(s - 270f) < 1e-3f;
        }

        /// <summary>
        /// The yaw offset that turns a model whose forward is <paramref name="nativeForward"/> (root space) to
        /// face +z, snapped to 90 degrees. A model facing +z gets 0, one facing -z gets 180.
        /// </summary>
        public static float YawOffsetFacing(Vector3 nativeForward)
        {
            return SnapYaw(-YawMath.YawOf(nativeForward));
        }

        // ----- Fit -----

        /// <summary>True when every component is strictly positive and finite.</summary>
        public static bool IsValidSize(Vector3 size)
        {
            return Valid(size.x) && Valid(size.y) && Valid(size.z);
        }

        private static bool Valid(float v) => v > Eps && !float.IsNaN(v) && !float.IsInfinity(v);

        /// <summary>
        /// ModelFit.Box: the per axis scale (in the model's own axes) so its native bounds, turned by
        /// <paramref name="yawOffset"/>, fill <paramref name="box"/> exactly. A quarter turn swaps x and z.
        /// </summary>
        public static Vector3 BoxScale(Vector3 nativeSize, Vector3 box, float yawOffset)
        {
            bool quarter = IsQuarterTurn(yawOffset);
            float bx = quarter ? box.z : box.x;
            float bz = quarter ? box.x : box.z;
            return new Vector3(Ratio(bx, nativeSize.x), Ratio(box.y, nativeSize.y), Ratio(bz, nativeSize.z));
        }

        /// <summary>ModelFit.Uniform: one scale that brings <paramref name="native"/> to <paramref name="target"/>.</summary>
        public static float UniformScale(float native, float target)
        {
            return Ratio(target, native);
        }

        private static float Ratio(float target, float native) => native > Eps ? target / native : 0f;

        /// <summary>
        /// The local position of a model root scaled by <paramref name="scale"/> and turned by
        /// <paramref name="yawOffset"/>, so its native bounds (<paramref name="center"/>, <paramref name="nativeSize"/>)
        /// end up centred on x and z with their bottom on y = 0. This is the recentring of Kenney's corner pivot.
        /// </summary>
        public static Vector3 FitPosition(Vector3 center, Vector3 nativeSize, Vector3 scale, float yawOffset)
        {
            Vector3 turned = Quaternion.Euler(0f, yawOffset, 0f) * Vector3.Scale(center, scale);
            return new Vector3(-turned.x, nativeSize.y * scale.y * 0.5f - turned.y, -turned.z);
        }

        /// <summary>Transforms a native point by the fit (scale, then yaw, then the fit position).</summary>
        public static Vector3 ApplyFit(Vector3 nativePoint, Vector3 position, Vector3 scale, float yawOffset)
        {
            return position + Quaternion.Euler(0f, yawOffset, 0f) * Vector3.Scale(nativePoint, scale);
        }

        // ----- Colours (sRGB) -----

        /// <summary>Snaps each sRGB channel to the 1/64 grid; alpha becomes 1.</summary>
        public static Color Quantize(Color srgb)
        {
            return new Color(Q(srgb.r), Q(srgb.g), Q(srgb.b), 1f);
        }

        private static float Q(float v)
        {
            return Mathf.Clamp01(Mathf.Round(Mathf.Clamp01(v) / QuantStep) * QuantStep);
        }

        /// <summary>Every channel of the sRGB colour, converted to linear, below <see cref="NearBlackMax"/>.</summary>
        public static bool IsNearBlack(Color srgb)
        {
            return ToLinear(srgb.r) < NearBlackMax && ToLinear(srgb.g) < NearBlackMax && ToLinear(srgb.b) < NearBlackMax;
        }

        /// <summary>The sRGB transfer function, inverted (IEC 61966-2-1): one sRGB channel to linear.</summary>
        public static float ToLinear(float srgb)
        {
            srgb = Mathf.Clamp01(srgb);
            return srgb <= 0.04045f ? srgb / 12.92f : Mathf.Pow((srgb + 0.055f) / 1.055f, 2.4f);
        }

        /// <summary>The value (HSV) of an sRGB colour: its largest channel.</summary>
        public static float Value(Color srgb)
        {
            return Mathf.Max(srgb.r, Mathf.Max(srgb.g, srgb.b));
        }

        /// <summary>
        /// The red test of CONTRACT_M3 3, on the sRGB colour: hue within 20 degrees of 0, saturation above 0.5,
        /// value above 0.35. Kenney wood (hue 25 in sRGB) is not red; Kenney carpet and carpetDarker are.
        /// </summary>
        public static bool IsRed(Color srgb)
        {
            Color.RGBToHSV(srgb, out float h, out float s, out float v);
            float hue = h * 360f;
            float fromZero = Mathf.Min(hue, 360f - hue);
            return fromZero <= RedHueRange && s > RedMinSaturation && v > RedMinValue;
        }

        /// <summary>The value of the brightest red among <paramref name="sources"/>, or 0 when none is red.</summary>
        public static float RedReference(IEnumerable<Color> sources)
        {
            float best = 0f;
            foreach (Color c in sources)
            {
                if (IsRed(c))
                {
                    best = Mathf.Max(best, Value(c));
                }
            }
            return best;
        }

        /// <summary>
        /// <paramref name="target"/> darkened by <paramref name="ratio"/> (in sRGB) and quantised; the exact
        /// target (opaque) when the ratio is 1, so it shares the material of the level colour it comes from.
        /// </summary>
        public static Color Shade(Color target, float ratio)
        {
            ratio = Mathf.Clamp01(ratio);
            if (ratio >= 1f - 1e-3f)
            {
                return Opaque(target);
            }
            return Quantize(new Color(target.r * ratio, target.g * ratio, target.b * ratio, 1f));
        }

        public static Color Opaque(Color c) => new Color(c.r, c.g, c.b, 1f);

        /// <summary>
        /// The colour a material slot is painted with (CONTRACT_M3 3):
        /// 1. the main material takes <see cref="ModelPaint.Main"/> when set (player and decoys), exactly;
        /// 2. a red takes <see cref="ModelPaint.Red"/> (rug, doormat or accent colour), shaded like the source;
        /// 3. a near-black takes <see cref="NearBlack"/>;
        /// 4. anything else is quantised.
        /// </summary>
        public static Color MapColor(Color source, bool isMain, float redReference, ModelPaint paint)
        {
            if (isMain && paint.Main.HasValue)
            {
                return Opaque(paint.Main.Value);
            }
            if (IsRed(source))
            {
                Color target = paint.Red ?? DefaultRedTarget;
                float ratio = redReference > Eps ? Value(source) / redReference : 1f;
                return Shade(target, ratio);
            }
            if (IsNearBlack(source))
            {
                return NearBlack;
            }
            return Quantize(source);
        }

        /// <summary>Index of the largest count (the first one on a tie), or -1 for an empty list.</summary>
        public static int IndexOfMax(IList<long> counts)
        {
            int best = -1;
            for (int i = 0; i < counts.Count; i++)
            {
                if (best < 0 || counts[i] > counts[best])
                {
                    best = i;
                }
            }
            return best;
        }
    }
}
