using System.Collections.Generic;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// HUD gauge redesign (2026-11-19): the procedural sprites of the bottom band's capsule gauges (creak, suspicion,
    /// balance), drawn once in code like <see cref="ProceduralArt"/>, with no texture asset. Every capsule shape is a
    /// rounded box whose corner radius is half its height (a pill), anti aliased over one texel.
    ///
    /// The nine sliced sprites (<see cref="Plate"/>, <see cref="Recess"/>, <see cref="Shade"/>, <see cref="Glow"/>) keep
    /// their round ends at any length: their border is <see cref="SliceBorder"/> texels (<see cref="GlowBorder"/> for the
    /// glow), and an Image of height H units shows them as a pill with <see cref="PillMultiplier"/>(H) as its
    /// pixelsPerUnitMultiplier. The two fill sprites (<see cref="Bar"/>, <see cref="Hatch"/>) are drawn at the exact
    /// size of a track (cached by size) for a horizontally Filled Image: its round left end shows from the first percent,
    /// its leading edge is cut straight at the value.
    /// </summary>
    public static class GaugeArt
    {
        /// <summary>The border, in texels, of the sliced pill sprites: the corner radius plus two texels.</summary>
        public const float SliceBorder = 34f;

        /// <summary>The border, in texels, of <see cref="Glow"/>: the pill radius plus its halo.</summary>
        public const float GlowBorder = 58f;

        /// <summary>The halo of <see cref="Glow"/> beyond the pill, in texels.</summary>
        public const float GlowHalo = 24f;

        // The sliced sprites are 2 * border + 2 texels tall (a two texel centre row) and 128 wide.
        private const int SliceWidth = 128;
        private const float Radius = 32f;

        private static Sprite plate;
        private static Sprite recess;
        private static Sprite shade;
        private static Sprite glow;
        private static Sprite badge;
        private static readonly Dictionary<long, Sprite> Bars = new Dictionary<long, Sprite>();
        private static readonly Dictionary<long, Sprite> Hatches = new Dictionary<long, Sprite>();

        /// <summary>The pixelsPerUnitMultiplier that shows a sliced pill sprite <paramref name="height"/> units tall with round ends.</summary>
        public static float PillMultiplier(float height) => 2f * SliceBorder / Mathf.Max(1f, height);

        /// <summary>The pixelsPerUnitMultiplier of <see cref="Glow"/> for a pill <paramref name="height"/> units tall plus <paramref name="halo"/> units around it.</summary>
        public static float GlowMultiplier(float height, float halo) => GlowBorder / Mathf.Max(1f, height * 0.5f + halo);

        /// <summary>The capsule's backing: dark and translucent (contrast over any floor), a thin cream rim, a faint top sheen.</summary>
        public static Sprite Plate => plate != null ? plate : plate = Sliced("GaugePlate", SliceBorder, PlateTexel);

        /// <summary>The track's recess under the fill: darker, with an inner shadow from the top and a faint light lip at the bottom.</summary>
        public static Sprite Recess => recess != null ? recess : recess = Sliced("GaugeRecess", SliceBorder, RecessTexel);

        /// <summary>The inner shadow alone, drawn over the fill so it sits in the recess (transparent elsewhere).</summary>
        public static Sprite Shade => shade != null ? shade : shade = Sliced("GaugeShade", SliceBorder, ShadeTexel);

        /// <summary>A soft white halo around a pill, tinted and faded in near the gauge's limit.</summary>
        public static Sprite Glow => glow != null ? glow : glow = Sliced("GaugeGlow", GlowBorder, GlowTexel);

        /// <summary>The icon's badge at the capsule's left end: a dark disc in a cream ring (the ring takes the tint).</summary>
        public static Sprite Badge => badge != null ? badge : badge = Draw("GaugeBadge", 128, 128, Vector4.zero, BadgeTexel);

        /// <summary>The fill of a track <paramref name="width"/> x <paramref name="height"/> units: a white pill with a vertical sheen, to tint.</summary>
        public static Sprite Bar(float width, float height) => Sized(Bars, "GaugeBar", width, height, BarTexel);

        /// <summary>The same pill cut in diagonal stripes: the danger zone past the threshold, never told by colour alone.</summary>
        public static Sprite Hatch(float width, float height) => Sized(Hatches, "GaugeHatch", width, height, HatchTexel);

        private delegate Color TexelFn(float x, float y, int width, int height);

        private static Sprite Sliced(string name, float border, TexelFn fn)
        {
            int height = Mathf.RoundToInt(border) * 2 + 2;
            int width = Mathf.Max(SliceWidth, height + 4);
            return Draw(name, width, height, new Vector4(border, border, border, border), fn);
        }

        private static Sprite Sized(Dictionary<long, Sprite> cache, string name, float width, float height, TexelFn fn)
        {
            // Two texels per unit: crisp at 1080p and on a 20:9 phone (about 1.1 screen pixels per unit).
            int w = Mathf.Clamp(Mathf.RoundToInt(width * 2f), 8, 2048);
            int h = Mathf.Clamp(Mathf.RoundToInt(height * 2f), 4, 256);
            long key = ((long)w << 16) | (long)h;
            if (cache.TryGetValue(key, out Sprite cached) && cached != null)
            {
                return cached;
            }
            Sprite sprite = Draw(name, w, h, Vector4.zero, fn);
            cache[key] = sprite;
            return sprite;
        }

        private static Sprite Draw(string name, int width, int height, Vector4 border, TexelFn fn)
        {
            var texture = new Texture2D(width, height, TextureFormat.RGBA32, false)
            {
                name = name,
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear,
                hideFlags = HideFlags.DontUnloadUnusedAsset,
            };
            var pixels = new Color[width * height];
            for (int y = 0; y < height; y++)
            {
                for (int x = 0; x < width; x++)
                {
                    pixels[y * width + x] = fn(x + 0.5f, y + 0.5f, width, height);
                }
            }
            texture.SetPixels(pixels);
            texture.Apply(false, true);
            Sprite sprite = Sprite.Create(texture, new Rect(0, 0, width, height), new Vector2(0.5f, 0.5f), 100f, 0,
                SpriteMeshType.FullRect, border);
            sprite.name = name;
            sprite.hideFlags = HideFlags.DontUnloadUnusedAsset;
            return sprite;
        }

        /// <summary>Signed distance (texels, negative inside) to a pill inset by <paramref name="inset"/> in a width x height texture.</summary>
        private static float Pill(float x, float y, int width, int height, float inset, float radius)
        {
            float hw = width * 0.5f - inset;
            float hh = height * 0.5f - inset;
            float r = Mathf.Min(radius, Mathf.Min(hw, hh));
            float qx = Mathf.Abs(x - width * 0.5f) - (hw - r);
            float qy = Mathf.Abs(y - height * 0.5f) - (hh - r);
            float outside = new Vector2(Mathf.Max(qx, 0f), Mathf.Max(qy, 0f)).magnitude;
            return outside + Mathf.Min(Mathf.Max(qx, qy), 0f) - r;
        }

        private static float Cover(float d) => Mathf.Clamp01(0.5f - d);

        /// <summary>The inner shadow from above: 1 at the shape's top inner edge, fading over <paramref name="spread"/> texels.</summary>
        private static float InnerShadow(float x, float y, int width, int height, float inset, float radius, float drop, float spread)
        {
            // The shape moved down by drop: what of the real shape falls outside it, near the top edge, is in shadow.
            float shifted = Pill(x, y + drop, width, height, inset, radius);
            return Mathf.Clamp01(1f + shifted / spread);
        }

        private static Color PlateTexel(float x, float y, int width, int height)
        {
            float d = Pill(x, y, width, height, 1f, Radius);
            float a = Cover(d);
            if (a <= 0f)
            {
                return Color.clear;
            }
            float v = y / height;
            // A dark warm glass, a touch lighter at the top.
            var c = new Color(0.075f + 0.05f * v, 0.065f + 0.04f * v, 0.08f + 0.04f * v, 0.9f);
            // The cream rim: 2.5 texels inside the edge, brighter at the top.
            float rim = Mathf.Clamp01(1f - Mathf.Abs(d + 1.8f) / 1.6f);
            var cream = new Color(1f, 0.93f, 0.8f, 0.6f + 0.3f * v);
            c = Color.Lerp(c, cream, rim * cream.a);
            c.a = Mathf.Max(c.a, rim * cream.a) * a;
            return c;
        }

        private static Color RecessTexel(float x, float y, int width, int height)
        {
            float d = Pill(x, y, width, height, 1f, Radius);
            float a = Cover(d);
            if (a <= 0f)
            {
                return Color.clear;
            }
            float shadow = InnerShadow(x, y, width, height, 1f, Radius, 5f, 9f);
            var c = new Color(0.03f, 0.022f, 0.03f, 0.82f + 0.15f * shadow);
            // A faint light lip along the bottom inner edge.
            float lip = Mathf.Clamp01(1f - Mathf.Abs(d + 1.5f) / 1.5f) * Mathf.Clamp01(1f - y / (height * 0.45f));
            c = Color.Lerp(c, new Color(1f, 0.92f, 0.8f, 1f), lip * 0.22f);
            c.a *= a;
            return c;
        }

        private static Color ShadeTexel(float x, float y, int width, int height)
        {
            float d = Pill(x, y, width, height, 1f, Radius);
            float a = Cover(d);
            if (a <= 0f)
            {
                return Color.clear;
            }
            float shadow = InnerShadow(x, y, width, height, 1f, Radius, 5f, 9f);
            float lip = Mathf.Clamp01(1f - Mathf.Abs(d + 1.2f) / 1.4f) * Mathf.Clamp01(1f - y / (height * 0.45f));
            Color c = Color.Lerp(new Color(0f, 0f, 0f, 0.5f * shadow), new Color(1f, 0.95f, 0.85f, 0.25f), lip);
            c.a *= a;
            return c;
        }

        private static Color GlowTexel(float x, float y, int width, int height)
        {
            float d = Pill(x, y, width, height, GlowBorder - Radius, Radius);
            float t = Mathf.Clamp01(1f - Mathf.Max(d, 0f) / GlowHalo);
            float a = t * t * (3f - 2f * t);
            return new Color(1f, 1f, 1f, a * a);
        }

        private static Color BadgeTexel(float x, float y, int width, int height)
        {
            float r = new Vector2(x - width * 0.5f, y - height * 0.5f).magnitude;
            float outer = Cover(r - 61f);
            if (outer <= 0f)
            {
                return Color.clear;
            }
            float ring = Cover(r - 61f) * Cover(54.5f - r);
            float v = y / height;
            var inside = new Color(0.1f + 0.06f * v, 0.085f + 0.05f * v, 0.11f + 0.05f * v, 0.96f);
            var cream = new Color(1f, 0.94f, 0.82f, 1f);
            Color c = Color.Lerp(inside, cream, ring);
            c.a = Mathf.Max(inside.a, ring) * outer;
            return c;
        }

        private static Color BarTexel(float x, float y, int width, int height)
        {
            float d = Pill(x, y, width, height, 0.5f, height * 0.5f);
            float a = Cover(d);
            if (a <= 0f)
            {
                return Color.clear;
            }
            float v = y / height;
            float u = x / width;
            // Darker at the bottom, a gloss band over the upper half, a little brighter towards the leading end.
            float light = 0.74f + 0.2f * v + 0.06f * u;
            float gloss = Mathf.Clamp01(1f - Mathf.Abs(v - 0.74f) / 0.12f) * 0.16f;
            float l = Mathf.Min(1f, light + gloss);
            return new Color(l, l, l, a);
        }

        private static Color HatchTexel(float x, float y, int width, int height)
        {
            float d = Pill(x, y, width, height, 0.5f, height * 0.5f);
            float a = Cover(d);
            if (a <= 0f)
            {
                return Color.clear;
            }
            // Stripes leaning forward, 12 texels apart, half of them solid, with soft edges.
            float s = Mathf.Repeat(x + y, 12f);
            float stripe = Mathf.Clamp01(Mathf.Min(s - 1f, 7f - s));
            return new Color(1f, 1f, 1f, a * Mathf.Lerp(0.3f, 1f, stripe));
        }
    }
}
