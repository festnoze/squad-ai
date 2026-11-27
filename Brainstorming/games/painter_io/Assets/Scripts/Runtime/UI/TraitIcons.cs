// Owned by traits-ui (wave D-2). docs/BIOME_TRAITS.md section 5: "each biome card shows its active traits as small icons".
// One procedural icon per TraitId: a white alpha mask drawn from signed distances (circles, capsules, arcs, polygons),
// tinted by the Image color. Generated once at 96 x 96 with mipmaps (trilinear), so the same sprite stays clean from 28 to
// 64 reference units (biome cards, the rules line of the menu, the hidden trait matrix, the HUD reward chips). Any trait
// may sit on any biome, so the icons are biome neutral; the screens tint them.
//
// Inertia: a wide U-turn arrow. Coalescence: two drops fusing. SparkSpeed: a spark with speed lines. Propagation: a dot
// with spreading rings. ScorchedEarth: a flame over a scorched line. Conduction: double chevron. ArcReach: a jagged arc
// between two dots. RingInterval: a ring with clock hands. KillInheritance: a flag. KillSpeedBoost: a lightning bolt.
// KillShield: a shield. An unknown id gets a plain dot.
using System;
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    public static class TraitIcons
    {
        /// <summary>Texture size of every icon (pixels).</summary>
        public const int Size = 96;

        private static readonly Dictionary<TraitId, Sprite> cache = new Dictionary<TraitId, Sprite>();
        private static Sprite check;

        /// <summary>The icon of a trait (cached; recreated if Unity destroyed it). Never null.</summary>
        public static Sprite Get(TraitId id)
        {
            if (cache.TryGetValue(id, out Sprite s) && s != null) return s;
            s = Draw("PIO_Trait_" + id, ShapeOf(id));
            cache[id] = s;
            return s;
        }

        /// <summary>A check mark (the trait matrix checkboxes).</summary>
        public static Sprite Check
        {
            get
            {
                if (check == null) check = Draw("PIO_UiCheck", CheckShape);
                return check;
            }
        }

        /// <summary>True when the trait has its own drawing (not the plain dot of an unknown id). Tests.</summary>
        internal static bool HasOwnShape(TraitId id)
        {
            return ShapeOf(id) != (Func<Vector2, float>)Dot;
        }

        /// <summary>
        /// A PNG sheet of every trait icon plus the check mark, white on the menu navy, cell pixels per icon, one row
        /// (tests save it for a visual check).
        /// </summary>
        internal static byte[] RenderSheetPng(int cell)
        {
            IReadOnlyList<TraitId> all = TraitDefaults.All;
            int n = all.Count + 1;
            var tex = new Texture2D(cell * n, cell, TextureFormat.RGBA32, false);
            var px = new Color32[cell * n * cell];
            Color32 navy = UiKit.PanelNavy;
            for (int k = 0; k < n; k++)
            {
                Func<Vector2, float> f = k < all.Count ? ShapeOf(all[k]) : CheckShape;
                for (int y = 0; y < cell; y++)
                {
                    for (int x = 0; x < cell; x++)
                    {
                        float a = Mathf.Clamp01(0.5f - f(new Vector2((x + 0.5f) / cell, (y + 0.5f) / cell)) * cell);
                        px[y * cell * n + k * cell + x] = Color32.Lerp(navy, new Color32(255, 255, 255, 255), a);
                    }
                }
            }
            tex.SetPixels32(px);
            tex.Apply(false);
            byte[] png = tex.EncodeToPNG();
            UnityEngine.Object.DestroyImmediate(tex);
            return png;
        }

        /// <summary>Share of the icon's pixels that are at least half covered (tests: every icon draws something).</summary>
        internal static float Coverage(TraitId id)
        {
            Func<Vector2, float> f = ShapeOf(id);
            int covered = 0;
            for (int y = 0; y < Size; y++)
            {
                for (int x = 0; x < Size; x++)
                {
                    if (f(new Vector2((x + 0.5f) / Size, (y + 0.5f) / Size)) < 0f) covered++;
                }
            }
            return covered / (float)(Size * Size);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Shapes (icon units: 0..1 on both axes, y up). Each returns a signed distance, negative inside.

        private static Func<Vector2, float> ShapeOf(TraitId id)
        {
            switch (id)
            {
                case TraitId.Inertia: return Inertia;
                case TraitId.Coalescence: return Coalescence;
                case TraitId.SparkSpeed: return SparkSpeed;
                case TraitId.Propagation: return Propagation;
                case TraitId.ScorchedEarth: return ScorchedEarth;
                case TraitId.Conduction: return Conduction;
                case TraitId.ArcReach: return ArcReach;
                case TraitId.RingInterval: return RingInterval;
                case TraitId.KillInheritance: return KillInheritance;
                case TraitId.KillSpeedBoost: return KillSpeedBoost;
                case TraitId.KillShield: return KillShield;
                default: return Dot;
            }
        }

        private static float Dot(Vector2 p) => Circle(p, new Vector2(0.5f, 0.5f), 0.22f);

        private static readonly Vector2 InertiaCenter = new Vector2(0.5f, 0.40f);
        private const float InertiaRadius = 0.29f, InertiaHalfWidth = 0.062f, InertiaEnd = 192f;

        private static float Inertia(Vector2 p)
        {
            // A wide arc over the top (round start cap on the right), ending in an arrowhead on the left that points down.
            float d = Arc(p, InertiaCenter, InertiaRadius, InertiaHalfWidth, -12f, InertiaEnd);
            float a = InertiaEnd * Mathf.Deg2Rad;
            var radial = new Vector2(Mathf.Cos(a), Mathf.Sin(a));
            var tangent = new Vector2(-radial.y, radial.x);   // the direction of travel (counterclockwise)
            Vector2 end = InertiaCenter + radial * InertiaRadius;
            Vector2 tip = end + tangent * 0.19f;
            Vector2 baseCenter = end - tangent * 0.02f;
            float head = Poly(p, new[] { tip, baseCenter + radial * 0.145f, baseCenter - radial * 0.145f });
            return Mathf.Min(d, head);
        }

        private static float Coalescence(Vector2 p)
        {
            float a = Circle(p, new Vector2(0.37f, 0.53f), 0.235f);
            float b = Circle(p, new Vector2(0.72f, 0.42f), 0.16f);
            float c = Circle(p, new Vector2(0.86f, 0.74f), 0.07f);
            return Mathf.Min(SmoothUnion(a, b, 0.12f), c);
        }

        private static float SparkSpeed(Vector2 p)
        {
            var center = new Vector2(0.66f, 0.5f);
            var star = new Vector2[8];
            for (int k = 0; k < 8; k++)
            {
                float a = (90f + k * 45f) * Mathf.Deg2Rad;
                float r = (k & 1) == 0 ? 0.29f : 0.075f;
                star[k] = center + new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * r;
            }
            float d = Poly(p, star);
            d = Mathf.Min(d, Segment(p, new Vector2(0.05f, 0.5f), new Vector2(0.29f, 0.5f), 0.04f));
            d = Mathf.Min(d, Segment(p, new Vector2(0.13f, 0.30f), new Vector2(0.40f, 0.30f), 0.036f));
            d = Mathf.Min(d, Segment(p, new Vector2(0.13f, 0.70f), new Vector2(0.40f, 0.70f), 0.036f));
            return d;
        }

        private static float Propagation(Vector2 p)
        {
            var c = new Vector2(0.5f, 0.5f);
            float d = Circle(p, c, 0.115f);
            d = Mathf.Min(d, Ring(p, c, 0.255f, 0.045f));
            for (int k = 0; k < 4; k++)
            {
                float mid = 45f + 90f * k;
                d = Mathf.Min(d, Arc(p, c, 0.40f, 0.04f, mid - 26f, mid + 26f));
            }
            return d;
        }

        private static float ScorchedEarth(Vector2 p)
        {
            float body = Circle(p, new Vector2(0.5f, 0.37f), 0.205f);
            float tongue = Poly(p, new[] { new Vector2(0.30f, 0.42f), new Vector2(0.70f, 0.42f), new Vector2(0.60f, 0.94f) });
            // A smaller side tongue on the left so the shape reads as a flame, not a drop.
            float side = Poly(p, new[] { new Vector2(0.29f, 0.36f), new Vector2(0.44f, 0.50f), new Vector2(0.24f, 0.74f) });
            float flame = SmoothUnion(SmoothUnion(body, tongue, 0.07f), side, 0.05f);
            float innerBody = Circle(p, new Vector2(0.5f, 0.33f), 0.085f);
            float innerTongue = Poly(p, new[] { new Vector2(0.415f, 0.35f), new Vector2(0.585f, 0.35f), new Vector2(0.53f, 0.62f) });
            float core = SmoothUnion(innerBody, innerTongue, 0.04f);
            float d = Mathf.Max(flame, -core);
            return Mathf.Min(d, Segment(p, new Vector2(0.15f, 0.075f), new Vector2(0.85f, 0.075f), 0.037f));
        }

        private static float Conduction(Vector2 p)
        {
            const float hw = 0.068f;
            float d = Mathf.Min(Segment(p, new Vector2(0.24f, 0.24f), new Vector2(0.46f, 0.5f), hw),
                                Segment(p, new Vector2(0.46f, 0.5f), new Vector2(0.24f, 0.76f), hw));
            d = Mathf.Min(d, Segment(p, new Vector2(0.54f, 0.24f), new Vector2(0.76f, 0.5f), hw));
            return Mathf.Min(d, Segment(p, new Vector2(0.76f, 0.5f), new Vector2(0.54f, 0.76f), hw));
        }

        private static float ArcReach(Vector2 p)
        {
            float d = Mathf.Min(Circle(p, new Vector2(0.16f, 0.29f), 0.105f), Circle(p, new Vector2(0.84f, 0.71f), 0.105f));
            const float hw = 0.042f;
            Vector2 a = new Vector2(0.24f, 0.35f), b = new Vector2(0.45f, 0.66f), c = new Vector2(0.55f, 0.36f), e = new Vector2(0.76f, 0.65f);
            d = Mathf.Min(d, Segment(p, a, b, hw));
            d = Mathf.Min(d, Segment(p, b, c, hw));
            return Mathf.Min(d, Segment(p, c, e, hw));
        }

        private static float RingInterval(Vector2 p)
        {
            var c = new Vector2(0.5f, 0.5f);
            float d = Ring(p, c, 0.335f, 0.062f);
            d = Mathf.Min(d, Segment(p, c, new Vector2(0.5f, 0.73f), 0.046f));
            return Mathf.Min(d, Segment(p, c, new Vector2(0.67f, 0.41f), 0.046f));
        }

        private static float KillInheritance(Vector2 p)
        {
            float pole = Segment(p, new Vector2(0.30f, 0.09f), new Vector2(0.30f, 0.90f), 0.047f);
            float flag = Poly(p, new[]
            {
                new Vector2(0.30f, 0.91f), new Vector2(0.85f, 0.80f), new Vector2(0.71f, 0.67f), new Vector2(0.85f, 0.54f),
                new Vector2(0.30f, 0.51f),
            });
            float ground = Segment(p, new Vector2(0.15f, 0.08f), new Vector2(0.47f, 0.08f), 0.04f);
            return Mathf.Min(pole, Mathf.Min(flag, ground));
        }

        private static float KillSpeedBoost(Vector2 p)
        {
            return Poly(p, new[]
            {
                new Vector2(0.55f, 0.95f), new Vector2(0.75f, 0.95f), new Vector2(0.57f, 0.60f), new Vector2(0.79f, 0.60f),
                new Vector2(0.35f, 0.04f), new Vector2(0.47f, 0.46f), new Vector2(0.25f, 0.46f),
            }) - 0.012f;
        }

        private static float KillShield(Vector2 p)
        {
            float shield = Poly(p, new[]
            {
                new Vector2(0.5f, 0.92f), new Vector2(0.82f, 0.80f), new Vector2(0.80f, 0.50f), new Vector2(0.69f, 0.27f),
                new Vector2(0.5f, 0.08f), new Vector2(0.31f, 0.27f), new Vector2(0.20f, 0.50f), new Vector2(0.18f, 0.80f),
            }) - 0.015f;
            float seam = Segment(p, new Vector2(0.5f, 0.79f), new Vector2(0.5f, 0.24f), 0.034f);
            return Mathf.Max(shield, -seam);
        }

        private static float CheckShape(Vector2 p)
        {
            const float hw = 0.088f;
            return Mathf.Min(Segment(p, new Vector2(0.22f, 0.52f), new Vector2(0.42f, 0.30f), hw),
                             Segment(p, new Vector2(0.42f, 0.30f), new Vector2(0.80f, 0.74f), hw));
        }

        // ------------------------------------------------------------------------------------------------------------
        // Signed distance primitives.

        private static float Circle(Vector2 p, Vector2 c, float r) => (p - c).magnitude - r;

        private static float Ring(Vector2 p, Vector2 c, float r, float halfWidth) => Mathf.Abs((p - c).magnitude - r) - halfWidth;

        /// <summary>A capsule from a to b with the given half width.</summary>
        private static float Segment(Vector2 p, Vector2 a, Vector2 b, float halfWidth)
        {
            Vector2 pa = p - a, ba = b - a;
            float h = Mathf.Clamp01(Vector2.Dot(pa, ba) / Mathf.Max(1e-9f, Vector2.Dot(ba, ba)));
            return (pa - ba * h).magnitude - halfWidth;
        }

        /// <summary>A ring stroke from angle a0 to a1 (degrees, counterclockwise, a1 &gt; a0) with round caps.</summary>
        private static float Arc(Vector2 p, Vector2 c, float r, float halfWidth, float a0Deg, float a1Deg)
        {
            Vector2 q = p - c;
            float ang = Mathf.Atan2(q.y, q.x) * Mathf.Rad2Deg;
            while (ang < a0Deg) ang += 360f;
            while (ang >= a0Deg + 360f) ang -= 360f;
            if (ang <= a1Deg) return Mathf.Abs(q.magnitude - r) - halfWidth;
            float a0 = a0Deg * Mathf.Deg2Rad, a1 = a1Deg * Mathf.Deg2Rad;
            Vector2 e0 = c + new Vector2(Mathf.Cos(a0), Mathf.Sin(a0)) * r;
            Vector2 e1 = c + new Vector2(Mathf.Cos(a1), Mathf.Sin(a1)) * r;
            return Mathf.Min((p - e0).magnitude, (p - e1).magnitude) - halfWidth;
        }

        /// <summary>Signed distance to a simple polygon (either winding).</summary>
        private static float Poly(Vector2 p, Vector2[] v)
        {
            float d = Vector2.Dot(p - v[0], p - v[0]);
            float s = 1f;
            for (int i = 0, j = v.Length - 1; i < v.Length; j = i, i++)
            {
                Vector2 e = v[j] - v[i];
                Vector2 w = p - v[i];
                Vector2 b = w - e * Mathf.Clamp01(Vector2.Dot(w, e) / Mathf.Max(1e-9f, Vector2.Dot(e, e)));
                d = Mathf.Min(d, Vector2.Dot(b, b));
                bool c1 = p.y >= v[i].y, c2 = p.y < v[j].y, c3 = e.x * w.y > e.y * w.x;
                if ((c1 && c2 && c3) || (!c1 && !c2 && !c3)) s = -s;
            }
            return s * Mathf.Sqrt(d);
        }

        private static float SmoothUnion(float a, float b, float k)
        {
            float h = Mathf.Clamp01(0.5f + 0.5f * (b - a) / k);
            return Mathf.Lerp(b, a, h) - k * h * (1f - h);
        }

        private static Sprite Draw(string name, Func<Vector2, float> shape)
        {
            const float inv = 1f / Size;
            // Coverage from the distance in pixels (one-pixel ramp centered on the edge).
            return UiKit.MakeSprite(name, Size, Size, (x, y) => Mathf.Clamp01(0.5f - shape(new Vector2(x * inv, y * inv)) * Size),
                                    Vector4.zero, true);
        }
    }
}
