// Owned by BI (wave B-2). Contract 25.1: the small animated preview of each biome card in the menu, painted in C# into a
// tiny texture (no asset, no extra shader): a glossy liquid puddle with a bobbing pearl (Liquide), an ember bed with
// licking flames (Feu), a neon plasma field on a hex circuit with a flickering arc (Électricité). Colors come from the
// biome's theme. Wave C (perf-08): MenuScreen repaints only the selected card's tile (15 times per second) while the menu
// is visible; the other cards keep a still frame. The rounded-corner alpha mask is computed once for all tiles.
using System;
using UnityEngine;

namespace PainterIO.Runtime
{
    public sealed class BiomePreview
    {
        public const int Width = 128;
        public const int Height = 80;
        public const int CornerRadius = 12;

        private static byte[] cornerMask;

        private readonly BiomeId biome;
        private readonly Texture2D texture;
        private readonly Color32[] pixels = new Color32[Width * Height];

        /// <summary>Paint calls since construction (the constructor's first frame included). Tests count repaints with it.</summary>
        internal int PaintCount { get; private set; }

        public BiomePreview(BiomeId biome)
        {
            this.biome = biome;
            texture = new Texture2D(Width, Height, TextureFormat.RGBA32, false)
            {
                name = "PIO BiomePreview " + biome,
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp,
                hideFlags = HideFlags.HideAndDontSave,
            };
            Sprite = Sprite.Create(texture, new Rect(0, 0, Width, Height), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect);
            Sprite.name = texture.name;
            Paint(0f);
        }

        public BiomeId Biome => biome;

        public Sprite Sprite { get; }

        /// <summary>Repaints the tile for the animation time t (seconds) and uploads it.</summary>
        public void Paint(float t)
        {
            PaintCount++;
            BiomeTheme theme = BiomeTheme.Get(biome);
            switch (biome)
            {
                case BiomeId.Fire: PaintFire(theme, t); break;
                case BiomeId.Electric: PaintElectric(theme, t); break;
                default: PaintLiquid(theme, t); break;
            }
            RoundCorners();
            texture.SetPixels32(pixels);
            texture.Apply(false, false);
        }

        public void Destroy()
        {
            if (Sprite != null) UnityEngine.Object.Destroy(Sprite);
            if (texture != null) UnityEngine.Object.Destroy(texture);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Liquide: a glossy coral puddle (two metaballs) lit from the upper left with a soft lower-right shadow, and a
        // teal pearl orbiting next to it with a thin thread back to the puddle.

        private void PaintLiquid(BiomeTheme th, float t)
        {
            Color ground = th.Ground, puddle = th.PlayerColors[0], pearlC = th.PlayerColors[1];
            float wob = Mathf.Sin(t * 2.1f) * 1.2f;
            Vector2 a = new Vector2(46f, 38f), b = new Vector2(66f + wob, 46f);
            float ang = t * 1.6f;
            Vector2 pearl = new Vector2(98f + Mathf.Cos(ang) * 10f, 40f + Mathf.Sin(ang) * 14f);
            for (int y = 0; y < Height; y++)
            {
                for (int x = 0; x < Width; x++)
                {
                    float grain = (Hash(x * 7 + y * 131) - 0.5f) * 0.03f;
                    Color c = ground * (1f + grain);
                    // Shadow of the puddle and the pearl (offset to the lower right).
                    float fs = Field(x - 3f, y + 4f, a, b);
                    float ds = Vector2.Distance(new Vector2(x - 2f, y + 3f), pearl);
                    float shadow = Mathf.Max(Smooth(0.7f, 1.1f, fs) * 0.45f, (1f - Smooth(6f, 9f, ds)) * 0.4f);
                    c *= 1f - shadow;
                    // Puddle.
                    float f = Field(x, y, a, b);
                    if (f > 0.75f)
                    {
                        float cover = Smooth(0.95f, 1.05f, f);
                        float gx = Field(x + 1, y, a, b) - Field(x - 1, y, a, b);
                        float gy = Field(x, y + 1, a, b) - Field(x, y - 1, a, b);
                        float rim = 1f - Smooth(1.0f, 1.9f, f);
                        var n = new Vector3(-gx * 6f * rim, -gy * 6f * rim, 1f).normalized;
                        Color shaded = Shade(puddle, n);
                        c = Color.Lerp(c, shaded, cover);
                    }
                    // Thread from the puddle edge to the pearl.
                    float dl = SegmentDistance(new Vector2(x, y), new Vector2(76f, 44f), pearl);
                    if (dl < 2.4f) c = Color.Lerp(c, Shade(pearlC, new Vector3(0f, 0f, 1f)), 1f - Smooth(1.4f, 2.4f, dl));
                    // Pearl.
                    float dp = Vector2.Distance(new Vector2(x, y), pearl);
                    if (dp < 7.5f)
                    {
                        Vector2 q = (new Vector2(x, y) - pearl) / 7f;
                        float z = Mathf.Sqrt(Mathf.Max(0f, 1f - q.sqrMagnitude));
                        c = Color.Lerp(c, Shade(pearlC, new Vector3(q.x, q.y, z)), 1f - Smooth(6.5f, 7.5f, dp));
                    }
                    pixels[y * Width + x] = c;
                }
            }
        }

        private static float Field(float x, float y, Vector2 a, Vector2 b)
        {
            float da = (x - a.x) * (x - a.x) + (y - a.y) * (y - a.y);
            float db = (x - b.x) * (x - b.x) + (y - b.y) * (y - b.y);
            return 380f / Mathf.Max(1f, da) + 260f / Mathf.Max(1f, db);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Feu: charred stone with faint cracks, a bed of breathing embers (cellular crust) and flame tongues licking up
        // from its edge, hot core near the coals.

        private void PaintFire(BiomeTheme th, float t)
        {
            Color ground = th.Ground, flame = th.PlayerColors[0], core = th.SecondaryColors[0];
            Color crust = Color.Lerp(ground, flame, 0.15f) * 0.6f;
            for (int y = 0; y < Height; y++)
            {
                for (int x = 0; x < Width; x++)
                {
                    float crack = Mathf.Abs(Noise(x * 0.09f, y * 0.09f) - 0.5f) < 0.02f ? 0.06f : 0f;
                    Color c = ground * (1f + (Hash(x * 3 + y * 977) - 0.5f) * 0.05f) + new Color(crack, crack * 0.5f, 0f, 0f);
                    // Ember bed: an ellipse in the lower part of the tile.
                    float ex = (x - 64f) / 50f, ey = (y - 26f) / 20f;
                    float bed = ex * ex + ey * ey;
                    float edgeNoise = (Noise(x * 0.12f, t * 0.8f) - 0.5f) * 0.25f;
                    if (bed < 1f + edgeNoise)
                    {
                        // Cellular coals: bright cells with a dark crust between them, breathing slowly.
                        float cell = Cellular(x * 0.16f, y * 0.16f);
                        float breathe = 0.75f + 0.25f * Mathf.Sin(t * 2.2f + x * 0.05f);
                        float glow = Mathf.Clamp01((cell - 0.18f) * 2.2f) * breathe;
                        Color coal = Color.Lerp(crust, Color.Lerp(flame, core, glow * 0.6f), glow);
                        c = Color.Lerp(c, coal, Smooth(1f + edgeNoise, 0.85f + edgeNoise, bed));
                    }
                    // Flames above the bed edge (screen up = +y in the texture).
                    float top = 26f + 20f * Mathf.Sqrt(Mathf.Max(0f, 1f - ex * ex));
                    float h = y - top + 4f;
                    if (h > 0f && Mathf.Abs(ex) < 1.05f)
                    {
                        float warp = Noise(x * 0.07f, y * 0.05f - t * 2.4f);
                        float tongue = Noise(x * 0.18f + warp * 1.6f, y * 0.09f - t * 3.4f);
                        float height = 26f * tongue * (1f - Mathf.Abs(ex) * 0.6f);
                        float k = Mathf.Clamp01(1f - h / Mathf.Max(1f, height));
                        if (k > 0f)
                        {
                            Color fc = Color.Lerp(flame, core, k * k);
                            c = Color.Lerp(c, fc, Smooth(0f, 0.35f, k));
                        }
                    }
                    pixels[y * Width + x] = c;
                }
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Électricité: blue-black board with a faint hex circuit grid, a neon plasma field with a flowing hex pattern and
        // a bright rim, and a jagged arc that hops along the border.

        private void PaintElectric(BiomeTheme th, float t)
        {
            Color ground = th.Ground, neon = th.PlayerColors[1], core = th.SecondaryColors[1];
            int step = Mathf.FloorToInt(t * 12f);
            float arcAngle = Hash(step * 17 + 3) * Mathf.PI * 2f;
            for (int y = 0; y < Height; y++)
            {
                for (int x = 0; x < Width; x++)
                {
                    float hex = HexEdge(x / 9f, y / 9f);
                    Vector2 p = new Vector2(x - 60f, y - 40f);
                    float r = new Vector2(p.x / 38f, p.y / 26f).magnitude;
                    float near = 1f - Smooth(1f, 1.8f, r);
                    Color c = ground + neon * (Smooth(0.9f, 1f, hex) * (0.05f + 0.12f * near));
                    if (r < 1.06f)
                    {
                        float flow = HexEdge(x / 7f + t * 0.6f, y / 7f - t * 0.3f);
                        Color field = Color.Lerp(neon * 0.55f, neon, Smooth(0.85f, 1f, flow) * 0.6f);
                        float rimK = Smooth(0.82f, 1f, r);
                        float crawl = Noise(Mathf.Atan2(p.y, p.x) * 5f + t * 6f, r * 3f);
                        field = Color.Lerp(field, Color.Lerp(neon, core, 0.6f), rimK * (0.6f + 0.4f * crawl));
                        c = Color.Lerp(c, field, 1f - Smooth(1f, 1.06f, r));
                    }
                    // Arc: a jagged lightning bolt from the rim outward, redrawn 12 times per second.
                    Vector2 start = new Vector2(Mathf.Cos(arcAngle) * 38f, Mathf.Sin(arcAngle) * 26f);
                    Vector2 end = start * 1.45f + new Vector2(Hash(step * 5 + 1) - 0.5f, Hash(step * 5 + 2) - 0.5f) * 20f;
                    float d = JaggedDistance(p, start, end, step);
                    if (d < 3.5f)
                    {
                        float k = 1f - Smooth(0.6f, 3.5f, d);
                        c = Color.Lerp(c, d < 1.0f ? Color.white : Color.Lerp(neon, core, 0.5f), k);
                    }
                    pixels[y * Width + x] = c;
                }
            }
        }

        private static float JaggedDistance(Vector2 p, Vector2 a, Vector2 b, int step)
        {
            const int segments = 5;
            Vector2 prev = a;
            Vector2 dir = b - a;
            Vector2 normal = new Vector2(-dir.y, dir.x).normalized;
            float best = float.MaxValue;
            for (int k = 1; k <= segments; k++)
            {
                float u = k / (float)segments;
                Vector2 next = Vector2.Lerp(a, b, u);
                if (k < segments) next += normal * ((Hash(step * 31 + k * 7) - 0.5f) * 9f);
                best = Mathf.Min(best, SegmentDistance(p, prev, next));
                prev = next;
            }
            return best;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Helpers.

        private static Color Shade(Color albedo, Vector3 n)
        {
            var l = new Vector3(-0.45f, 0.6f, 0.66f).normalized;
            var h = (l + Vector3.forward).normalized;
            float diffuse = Mathf.Lerp(0.55f, 1.05f, Mathf.Clamp01((Vector3.Dot(n, l) + 0.25f) / 1.25f));
            float spec = Mathf.Pow(Mathf.Clamp01(Vector3.Dot(n, h)), 60f) * 0.9f;
            Color c = albedo * diffuse;
            c.r += spec;
            c.g += spec;
            c.b += spec;
            c.a = 1f;
            return c;
        }

        private void RoundCorners()
        {
            byte[] mask = CornerMask;
            for (int i = 0; i < pixels.Length; i++) pixels[i].a = mask[i];
        }

        /// <summary>The rounded-corner alpha of every pixel of a tile, computed once (perf-08).</summary>
        internal static byte[] CornerMask
        {
            get
            {
                if (cornerMask != null) return cornerMask;
                var mask = new byte[Width * Height];
                for (int y = 0; y < Height; y++)
                {
                    for (int x = 0; x < Width; x++)
                    {
                        float dx = Mathf.Max(0f, Mathf.Max(CornerRadius - x - 0.5f, x + 0.5f - (Width - CornerRadius)));
                        float dy = Mathf.Max(0f, Mathf.Max(CornerRadius - y - 0.5f, y + 0.5f - (Height - CornerRadius)));
                        float d = Mathf.Sqrt(dx * dx + dy * dy);
                        mask[y * Width + x] = (byte)Mathf.RoundToInt(255f * Mathf.Clamp01(CornerRadius - d + 0.5f));
                    }
                }
                cornerMask = mask;
                return mask;
            }
        }

        private static float Smooth(float e0, float e1, float x)
        {
            float k = Mathf.Clamp01((x - e0) / (e1 - e0));
            return k * k * (3f - 2f * k);
        }

        private static float SegmentDistance(Vector2 p, Vector2 a, Vector2 b)
        {
            Vector2 ab = b - a;
            float k = ab.sqrMagnitude > 1e-6f ? Mathf.Clamp01(Vector2.Dot(p - a, ab) / ab.sqrMagnitude) : 0f;
            return Vector2.Distance(p, a + ab * k);
        }

        /// <summary>Deterministic hash of an integer to [0, 1).</summary>
        private static float Hash(int k)
        {
            unchecked
            {
                uint h = (uint)k * 2654435761u;
                h ^= h >> 15;
                h *= 2246822519u;
                h ^= h >> 13;
                return (h & 0xFFFFFF) / 16777216f;
            }
        }

        /// <summary>Smooth value noise in [0, 1].</summary>
        private static float Noise(float x, float y)
        {
            int ix = Mathf.FloorToInt(x), iy = Mathf.FloorToInt(y);
            float fx = x - ix, fy = y - iy;
            float ux = fx * fx * (3f - 2f * fx), uy = fy * fy * (3f - 2f * fy);
            float a = Hash(ix * 374761 + iy * 668265), b = Hash((ix + 1) * 374761 + iy * 668265);
            float c = Hash(ix * 374761 + (iy + 1) * 668265), d = Hash((ix + 1) * 374761 + (iy + 1) * 668265);
            return Mathf.Lerp(Mathf.Lerp(a, b, ux), Mathf.Lerp(c, d, ux), uy);
        }

        /// <summary>Distance to the nearest jittered cell point (cellular noise), about [0, 0.9].</summary>
        private static float Cellular(float x, float y)
        {
            int ix = Mathf.FloorToInt(x), iy = Mathf.FloorToInt(y);
            float best = 9f;
            for (int j = -1; j <= 1; j++)
            {
                for (int i = -1; i <= 1; i++)
                {
                    int cx = ix + i, cy = iy + j;
                    float px = cx + Hash(cx * 92837 + cy * 689287), py = cy + Hash(cx * 283923 + cy * 12893 + 7);
                    float d = (px - x) * (px - x) + (py - y) * (py - y);
                    if (d < best) best = d;
                }
            }
            return Mathf.Sqrt(best);
        }

        /// <summary>1 on the edges of a hexagonal grid, 0 at the cell centers (cell size 1).</summary>
        private static float HexEdge(float x, float y)
        {
            const float s = 1.7320508f;
            float ax = x, ay = y;
            float bx = x - 0.5f * s, by = y - 0.5f;
            ax = Mod(ax, s) - 0.5f * s;
            ay = Mod(ay, 1f) - 0.5f;
            bx = Mod(bx, s) - 0.5f * s;
            by = Mod(by, 1f) - 0.5f;
            float da = ax * ax + ay * ay, db = bx * bx + by * by;
            float hx = da < db ? ax : bx, hy = da < db ? ay : by;
            hx = Mathf.Abs(hx);
            hy = Mathf.Abs(hy);
            float edge = Mathf.Max(hx * 0.8660254f + hy * 0.5f, hy);
            return Mathf.Clamp01(edge * 2f);
        }

        private static float Mod(float a, float m)
        {
            float r = a - m * Mathf.Floor(a / m);
            return r < 0f ? r + m : r;
        }
    }
}
