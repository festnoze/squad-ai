using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>
    /// Floor dust (product owner request, 2026-11-20, docs/m9/FLOORS_WALLS.md section 10): on the Haut tier only, the room
    /// floors lose their showroom cleanness. The floor shader (OutOfSight/Wall Finishes, WallFinishesForward.hlsl) reads a
    /// small top-down map of the level, built here once per level and only while the tier is Haut:
    /// <list type="bullet">
    /// <item>R, grime: highest against the walls and stronger again in the corners (the wall pieces standing on the floor,
    /// the colliders named <see cref="WallSegmentName"/>, so a doorway stays clean), unevenly (noise);</item>
    /// <item>G, wear: the traffic paths of each room, from doorway to doorway through the thresholds (a room with one door:
    /// from it to the room's centre), where the dust is swept away and the finish a touch worn;</item>
    /// <item>B, patches: low-frequency noise (2.8 m, 1.2 m and 0.5 m octaves, 0.5 on average) for faint dust patches and a soft
    /// variation that breaks the obvious repeat of the floor images.</item>
    /// </list>
    /// The shader variant that reads it is chosen by the global keyword <see cref="KeywordName"/>, on only while the tier is
    /// Haut and the map belongs to the level on screen: Bas and Moyen (the Android default) draw the floors exactly as before
    /// and build no map. The map is one RGBA32 texture of <see cref="TexelsPerMetre"/> texels per metre (at most
    /// <see cref="MaxSide"/> a side), linear, bilinear, set as a global texture: no material, no renderer, no draw call.
    /// Rugs, furniture and walls are untouched (the shader only changes vertices that name a floor look and face up).
    /// </summary>
    public static class FloorDust
    {
        /// <summary>The global shader keyword of the dusty floor variant (multi_compile_fragment in WallFinishes.shader).</summary>
        public const string KeywordName = "OOS_FLOOR_DUST";

        /// <summary>The global texture the shader samples, and its world rectangle (x, z of its corner, 1 / its size in metres).</summary>
        public const string MapProperty = "_OosFloorDust";
        public const string RectProperty = "_OosFloorDustRect";

        /// <summary>
        /// The first slice of the room surface arrays that is a floor look (WallArray.Slices: Parquet, then every floor look):
        /// the shader dusts a vertex whose UV1.x (slice + 1) is above this (FLOOR_DUST_FIRST_FINISH).
        /// </summary>
        public const int FirstFloorSlice = 12;

        /// <summary>The name LevelBuilder.WallSegment gives every solid piece of wall (a box collider).</summary>
        public const string WallSegmentName = "Segment";

        /// <summary>Map resolution: 12 texels per metre (an 8 cm texel, bilinear), at most 512 texels a side.</summary>
        public const float TexelsPerMetre = 12f;
        public const int MaxSide = 512;

        /// <summary>Margin around the house's walls covered by the map (metres).</summary>
        public const float Margin = 0.75f;

        /// <summary>A wall piece whose bottom is higher than this stands over a door or a window: no grime under it.</summary>
        public const float WallMaxBottom = 0.05f;

        /// <summary>How far from a wall face its grime reaches, and the wider reach whose product makes the corners.</summary>
        public const float EdgeReach = 0.4f;
        public const float CornerReach = 1.0f;

        /// <summary>Grime against a wall face, and what a corner adds (the result is clamped to 1).</summary>
        public const float EdgeGrime = 0.7f;
        public const float CornerGrime = 0.7f;

        /// <summary>A doorway's path point, this far into its room from the wall face (metres), and a path's half width.</summary>
        public const float DoorStep = 0.45f;
        public const float PathHalfWidth = 0.55f;

        private static GlobalKeyword keyword;
        private static bool keywordMade;
        private static Texture2D map;
        private static GameObject builtFor;
        private static LevelDef levelDef;
        private static GameObject levelRoot;
        private static bool quitHooked;

        /// <summary>True while the quality tier is Haut (QualityTier.Apply).</summary>
        public static bool TierOn { get; private set; }

        /// <summary>
        /// Tests and shots: keeps the dusty variant off whatever the tier (to compare the same frame with and without it).
        /// Set it through <see cref="SetSuppressed"/>.
        /// </summary>
        public static bool Suppressed { get; private set; }

        /// <summary>The map of the level on screen, or null (not Haut, or no level built since).</summary>
        public static Texture2D Map => map != null && builtFor != null && builtFor == levelRoot ? map : null;

        /// <summary>The world rectangle (x, z) the map covers.</summary>
        public static Rect MapRect { get; private set; }

        /// <summary>How many maps were built since start (tests: Bas and Moyen build none).</summary>
        public static int Builds { get; private set; }

        /// <summary>True while the dusty floor variant is drawn (the global keyword).</summary>
        public static bool KeywordOn => Shader.IsKeywordEnabled(Keyword);

        private static GlobalKeyword Keyword
        {
            get
            {
                if (!keywordMade)
                {
                    keyword = GlobalKeyword.Create(KeywordName);
                    keywordMade = true;
                }
                return keyword;
            }
        }

        /// <summary>QualityTier: the tier is Haut (true) or not. Builds the map of the current level if it has none yet.</summary>
        public static void SetTier(bool high)
        {
            TierOn = high;
            HookQuit();
            Refresh();
        }

        /// <summary>LevelBuilder.Build: a new level stands (its walls built). Its map is built now when the tier is Haut.</summary>
        public static void LevelBuilt(LevelDef def, GameObject root)
        {
            levelDef = def;
            levelRoot = root;
            Refresh();
        }

        /// <summary>Tests and shots: see <see cref="Suppressed"/>.</summary>
        public static void SetSuppressed(bool suppressed)
        {
            Suppressed = suppressed;
            Refresh();
        }

        /// <summary>The map's channels at a world point (tests): grime, wear, patches, in [0, 1]; zero without a map.</summary>
        public static Vector3 Sample(Vector3 world)
        {
            Texture2D m = Map;
            if (m == null)
            {
                return Vector3.zero;
            }
            Rect r = MapRect;
            Color c = m.GetPixelBilinear((world.x - r.xMin) / r.width, (world.z - r.yMin) / r.height);
            return new Vector3(c.r, c.g, c.b);
        }

        private static void Refresh()
        {
            bool want = TierOn && !Suppressed && levelRoot != null && levelDef != null;
            if (want && (map == null || builtFor == null || builtFor != levelRoot))
            {
                try
                {
                    Build(levelDef, levelRoot);
                }
                catch (System.Exception e)
                {
                    Debug.LogWarning("[FloorDust] cannot build the floor map: " + e.Message);
                    builtFor = null;
                }
            }
            Shader.SetKeyword(Keyword, want && Map != null);
        }

        private static void HookQuit()
        {
            if (quitHooked)
            {
                return;
            }
            quitHooked = true;
            // Leaving play mode (and quitting): the editor's own floors draw without it again.
            Application.quitting += () =>
            {
                TierOn = false;
                levelRoot = null;
                Shader.SetKeyword(Keyword, false);
            };
        }

        // ----- The map -----

        private static void Build(LevelDef def, GameObject root)
        {
            Rect interior = def.InteriorBounds();
            float pad = def.WallThickness() + Margin;
            Rect rect = Rect.MinMaxRect(interior.xMin - pad, interior.yMin - pad, interior.xMax + pad, interior.yMax + pad);
            int w = Mathf.Clamp(Mathf.CeilToInt(rect.width * TexelsPerMetre), 8, MaxSide);
            int h = Mathf.Clamp(Mathf.CeilToInt(rect.height * TexelsPerMetre), 8, MaxSide);
            var field = new Field(rect, w, h);

            // Grime: every solid wall piece standing on the floor, by the axis it runs along.
            foreach (BoxCollider box in root.GetComponentsInChildren<BoxCollider>(true))
            {
                if (box.gameObject.name != WallSegmentName)
                {
                    continue;
                }
                Bounds b = WorldBox(box);
                if (b.min.y > WallMaxBottom)
                {
                    continue;
                }
                field.StampWall(b.min.x, b.min.z, b.max.x, b.max.z, b.size.x >= b.size.z);
            }

            // Wear: the paths between the doorways of each room.
            foreach ((Vector2 a, Vector2 b) in Paths(def))
            {
                field.StampPath(a, b);
            }

            uint seed = Hash(def.Id ?? "level");
            var pixels = new Color32[w * h];
            field.Pack(pixels, (seed & 0xFFFF) * 0.0137f + 31.7f, ((seed >> 16) & 0xFFFF) * 0.0113f + 57.3f);

            if (map == null || map.width != w || map.height != h)
            {
                if (map != null && Application.isPlaying)
                {
                    Object.Destroy(map);
                }
                else if (map != null)
                {
                    Object.DestroyImmediate(map);
                }
                map = new Texture2D(w, h, TextureFormat.RGBA32, false, true)
                {
                    name = "OutOfSight Floor Dust",
                    wrapMode = TextureWrapMode.Clamp,
                    filterMode = FilterMode.Bilinear,
                    anisoLevel = 0,
                    hideFlags = HideFlags.DontSave,
                };
            }
            map.SetPixels32(pixels);
            // Kept readable: Sample (tests) reads it back; it is small (at most 1 MB, a house 0.5 MB).
            map.Apply(false, false);
            MapRect = rect;
            builtFor = root;
            Builds++;
            Shader.SetGlobalTexture(MapProperty, map);
            Shader.SetGlobalVector(RectProperty, new Vector4(rect.xMin, rect.yMin, 1f / rect.width, 1f / rect.height));
        }

        /// <summary>The world axis-aligned box of a box collider (the walls are axis aligned), from its transform.</summary>
        private static Bounds WorldBox(BoxCollider box)
        {
            Transform t = box.transform;
            Vector3 half = box.size * 0.5f;
            var b = new Bounds(t.TransformPoint(box.center), Vector3.zero);
            for (int k = 0; k < 8; k++)
            {
                var corner = new Vector3((k & 1) == 0 ? -half.x : half.x, (k & 2) == 0 ? -half.y : half.y, (k & 4) == 0 ? -half.z : half.z);
                b.Encapsulate(t.TransformPoint(box.center + corner));
            }
            return b;
        }

        /// <summary>
        /// The traffic paths (planar x, z): through every doorway (its point in each room it opens on, joined), then in
        /// each room every pair of its doorway points, or for a room with one doorway, that point to the room's centre.
        /// </summary>
        private static List<(Vector2, Vector2)> Paths(LevelDef def)
        {
            var paths = new List<(Vector2, Vector2)>();
            List<RoomDef> rooms = def.AllRooms();
            var entries = new List<Vector2>[rooms.Count];
            for (int i = 0; i < rooms.Count; i++)
            {
                entries[i] = new List<Vector2>();
            }
            if (def.Doors != null)
            {
                foreach (OpeningDef door in def.Doors)
                {
                    List<RoomSide> sides = def.SidesOf(door, out float along);
                    Vector2 first = default;
                    for (int k = 0; k < sides.Count; k++)
                    {
                        RoomSide s = sides[k];
                        float into = rooms[s.Room].WallThickness * 0.5f + DoorStep;
                        float across = s.Line - s.Outward * into;
                        var entry = s.AlongX ? new Vector2(along, across) : new Vector2(across, along);
                        entries[s.Room].Add(entry);
                        if (k == 0)
                        {
                            first = entry;
                            if (sides.Count == 1)
                            {
                                // An outer door: on to its threshold.
                                paths.Add((entry, s.AlongX ? new Vector2(along, s.Line) : new Vector2(s.Line, along)));
                            }
                        }
                        else
                        {
                            paths.Add((first, entry));
                        }
                    }
                }
            }
            for (int i = 0; i < rooms.Count; i++)
            {
                List<Vector2> e = entries[i];
                if (e.Count == 1)
                {
                    paths.Add((e[0], new Vector2(rooms[i].X, rooms[i].Z)));
                    continue;
                }
                for (int a = 0; a < e.Count; a++)
                {
                    for (int b = a + 1; b < e.Count; b++)
                    {
                        paths.Add((e[a], e[b]));
                    }
                }
            }
            return paths;
        }

        private static uint Hash(string s)
        {
            uint h = 2166136261u;
            foreach (char c in s)
            {
                h = (h ^ c) * 16777619u;
            }
            return h;
        }

        /// <summary>The map's fields, one float per texel each, then packed to bytes.</summary>
        private sealed class Field
        {
            private readonly Rect rect;
            private readonly int w;
            private readonly int h;
            // Grime: the near reach and the wide reach, from walls along x and walls along z.
            private readonly float[] edgeX;
            private readonly float[] edgeZ;
            private readonly float[] wideX;
            private readonly float[] wideZ;
            private readonly float[] wear;

            public Field(Rect rect, int w, int h)
            {
                this.rect = rect;
                this.w = w;
                this.h = h;
                int n = w * h;
                edgeX = new float[n];
                edgeZ = new float[n];
                wideX = new float[n];
                wideZ = new float[n];
                wear = new float[n];
            }

            private float X(int i) => rect.xMin + (i + 0.5f) * rect.width / w;
            private float Z(int j) => rect.yMin + (j + 0.5f) * rect.height / h;

            private void Range(float x0, float z0, float x1, float z1, out int i0, out int j0, out int i1, out int j1)
            {
                i0 = Mathf.Clamp(Mathf.FloorToInt((x0 - rect.xMin) / rect.width * w), 0, w - 1);
                i1 = Mathf.Clamp(Mathf.CeilToInt((x1 - rect.xMin) / rect.width * w), 0, w - 1);
                j0 = Mathf.Clamp(Mathf.FloorToInt((z0 - rect.yMin) / rect.height * h), 0, h - 1);
                j1 = Mathf.Clamp(Mathf.CeilToInt((z1 - rect.yMin) / rect.height * h), 0, h - 1);
            }

            /// <summary>(1 - d / reach) squared inside the reach, 0 beyond.</summary>
            private static float Falloff(float d, float reach)
            {
                float q = 1f - d / reach;
                return q > 0f ? q * q : 0f;
            }

            public void StampWall(float x0, float z0, float x1, float z1, bool alongX)
            {
                float reach = Mathf.Max(EdgeReach, CornerReach);
                Range(x0 - reach, z0 - reach, x1 + reach, z1 + reach, out int i0, out int j0, out int i1, out int j1);
                float[] edge = alongX ? edgeX : edgeZ;
                float[] wide = alongX ? wideX : wideZ;
                for (int j = j0; j <= j1; j++)
                {
                    float z = Z(j);
                    float dz = Mathf.Max(0f, Mathf.Max(z0 - z, z - z1));
                    for (int i = i0; i <= i1; i++)
                    {
                        float x = X(i);
                        float dx = Mathf.Max(0f, Mathf.Max(x0 - x, x - x1));
                        float d = Mathf.Sqrt(dx * dx + dz * dz);
                        int k = j * w + i;
                        edge[k] = Mathf.Max(edge[k], Falloff(d, EdgeReach));
                        // The wide reach falls linearly: its product with the crossing wall's is the soft corner.
                        wide[k] = Mathf.Max(wide[k], Mathf.Max(0f, 1f - d / CornerReach));
                    }
                }
            }

            public void StampPath(Vector2 a, Vector2 b)
            {
                float r = PathHalfWidth;
                Range(Mathf.Min(a.x, b.x) - r, Mathf.Min(a.y, b.y) - r, Mathf.Max(a.x, b.x) + r, Mathf.Max(a.y, b.y) + r,
                    out int i0, out int j0, out int i1, out int j1);
                Vector2 ab = b - a;
                float len2 = Mathf.Max(ab.sqrMagnitude, 1e-6f);
                for (int j = j0; j <= j1; j++)
                {
                    for (int i = i0; i <= i1; i++)
                    {
                        var p = new Vector2(X(i), Z(j));
                        float t = Mathf.Clamp01(Vector2.Dot(p - a, ab) / len2);
                        float d = Vector2.Distance(p, a + ab * t);
                        int k = j * w + i;
                        wear[k] = Mathf.Max(wear[k], Falloff(d, r));
                    }
                }
            }

            /// <summary>Grime, wear and patches to bytes, each made uneven by noise at the level's own offset.</summary>
            public void Pack(Color32[] pixels, float ox, float oz)
            {
                for (int j = 0; j < h; j++)
                {
                    float z = Z(j);
                    for (int i = 0; i < w; i++)
                    {
                        float x = X(i);
                        int k = j * w + i;
                        // Faint patches and the soft variation: three octaves, contrast stretched around 0.5.
                        float n = 0.5f * Mathf.PerlinNoise(ox + x / 2.8f, oz + z / 2.8f)
                            + 0.3f * Mathf.PerlinNoise(ox + 17.1f + x / 1.2f, oz + 3.3f + z / 1.2f)
                            + 0.2f * Mathf.PerlinNoise(ox + 41.7f + x / 0.5f, oz + 29.9f + z / 0.5f);
                        float patch = Mathf.Clamp01(0.5f + (n - 0.5f) * 2.2f);

                        float grime = EdgeGrime * Mathf.Max(edgeX[k], edgeZ[k]) + CornerGrime * wideX[k] * wideZ[k];
                        if (grime > 0f)
                        {
                            // Uneven along the walls: dust gathers in drifts, not in a ruled band.
                            grime *= 0.6f + 0.8f * Mathf.PerlinNoise(ox + 71.3f + x * 1.6f, oz + 11.9f + z * 1.6f);
                        }
                        float worn = wear[k];
                        if (worn > 0f)
                        {
                            worn *= 0.65f + 0.7f * Mathf.PerlinNoise(ox + 93.1f + x * 0.9f, oz + 47.2f + z * 0.9f);
                        }
                        pixels[k] = new Color32(Byte(grime), Byte(worn), Byte(patch), 255);
                    }
                }
            }

            private static byte Byte(float v) => (byte)Mathf.RoundToInt(Mathf.Clamp01(v) * 255f);
        }
    }
}
