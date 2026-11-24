using System;
using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// M7 level select: the cheap generated art of the Levels page. A top-down miniature of each level drawn once from its
    /// LevelDef into a small Texture2D (warm floors, cream walls with the doors as gaps, props as rounded blocks, the
    /// watchers' routes and start points, the player start as a red dot, the exit as a green mark), the level's watcher
    /// census (inhabitants, pets, robots) and its player furniture, plus the card glyphs (person, pet, robot, lock, check,
    /// one silhouette per furniture kind). Everything is cached: nothing is drawn per frame.
    /// </summary>
    public static class LevelMiniature
    {
        /// <summary>What a card shows of a level besides its miniature.</summary>
        public sealed class Summary
        {
            public int Humans;
            public int Pets;
            public int Robots;
            public string PlayerKind;
            public int Watchers => Humans + Pets + Robots;
        }

        // ----- Palette (shared with LevelSelect so the legend matches the drawing). -----
        public static readonly Color Ink = new Color(1f, 0.94f, 0.82f, 1f);
        public static readonly Color Paper = new Color(0.075f, 0.05f, 0.038f, 0.9f);
        public static readonly Color ChairRed = new Color(0.86f, 0.2f, 0.15f, 1f);
        public static readonly Color ExitGreen = new Color(0.42f, 0.8f, 0.44f, 1f);
        public static readonly Color PetAmber = new Color(0.96f, 0.68f, 0.32f, 1f);
        public static readonly Color RobotSteel = new Color(0.62f, 0.8f, 0.9f, 1f);
        private static readonly Color Outline = new Color(0.07f, 0.045f, 0.03f, 1f);
        private static readonly Color WoodDark = new Color(0.46f, 0.3f, 0.2f, 1f);
        private static readonly Color WoodLight = new Color(0.86f, 0.74f, 0.58f, 1f);
        private static readonly Color PropFill = new Color(0.27f, 0.18f, 0.125f, 0.95f);
        private static readonly Color PropTop = new Color(0.38f, 0.27f, 0.19f, 1f);
        private static readonly Color DecoyFill = new Color(0.45f, 0.24f, 0.19f, 0.95f);
        private static readonly Color PlantFill = new Color(0.33f, 0.45f, 0.26f, 0.95f);
        private static readonly Color Window = new Color(0.65f, 0.84f, 0.95f, 1f);

        private static readonly Dictionary<string, LevelDef> defs = new Dictionary<string, LevelDef>();
        private static readonly Dictionary<string, Sprite> miniatures = new Dictionary<string, Sprite>();
        private static readonly Dictionary<string, Summary> summaries = new Dictionary<string, Summary>();
        private static readonly Dictionary<string, Sprite> furniture = new Dictionary<string, Sprite>();
        private static Sprite person, pet, robot, lockGlyph, check, dot, exitMark;

        /// <summary>The level's definition, parsed once without validation (the page only draws it), or null.</summary>
        public static LevelDef Def(string levelId)
        {
            if (string.IsNullOrEmpty(levelId))
            {
                return null;
            }
            if (defs.TryGetValue(levelId, out LevelDef cached))
            {
                return cached;
            }
            LevelDef def = null;
            try
            {
                var asset = Resources.Load<TextAsset>(LevelLoader.Folder + "/" + levelId);
                def = asset != null ? LevelJson.Parse(asset.text) : null;
            }
            catch (Exception e)
            {
                Debug.LogWarning("[LevelMiniature] " + levelId + ": " + e.Message);
            }
            defs[levelId] = def;
            return def;
        }

        /// <summary>LOADDOTS: the level was already parsed (or found unreadable) by <see cref="Def"/>, so a new call is a lookup.</summary>
        public static bool IsParsed(string levelId) => !string.IsNullOrEmpty(levelId) && defs.ContainsKey(levelId);

        /// <summary>The watchers and the player furniture of a level (zeros and a chair when it cannot be read).</summary>
        public static Summary SummaryOf(string levelId)
        {
            if (levelId != null && summaries.TryGetValue(levelId, out Summary cached))
            {
                return cached;
            }
            var summary = new Summary { PlayerKind = BodyKinds.Chair };
            LevelDef def = Def(levelId);
            if (def != null)
            {
                foreach (InhabitantDef inhabitant in def.Inhabitants ?? new List<InhabitantDef>())
                {
                    if (IsPet(inhabitant))
                    {
                        summary.Pets++;
                    }
                    else
                    {
                        summary.Humans++;
                    }
                }
                summary.Robots = def.Robots != null ? def.Robots.Count : 0;
                summary.PlayerKind = def.Player != null ? BodyKinds.Of(def.Player.Kind) : BodyKinds.Chair;
            }
            if (levelId != null)
            {
                summaries[levelId] = summary;
            }
            return summary;
        }

        private static bool IsPet(InhabitantDef inhabitant) => inhabitant != null && !string.IsNullOrEmpty(inhabitant.Kind) && inhabitant.Kind != "human";

        /// <summary>The level's miniature as a sprite (drawn on first use, then cached), or null when the level cannot be read.</summary>
        public static Sprite MiniatureOf(string levelId)
        {
            if (string.IsNullOrEmpty(levelId))
            {
                return null;
            }
            if (miniatures.TryGetValue(levelId, out Sprite cached))
            {
                return cached;
            }
            Sprite sprite = null;
            LevelDef def = Def(levelId);
            if (def != null)
            {
                try
                {
                    Texture2D texture = Draw(def, Tuning.LevelMiniatureWidth, Tuning.LevelMiniatureHeight);
                    texture.name = "Miniature_" + levelId;
                    sprite = Sprite.Create(texture, new Rect(0, 0, texture.width, texture.height), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect);
                    sprite.name = texture.name;
                    sprite.hideFlags = HideFlags.DontUnloadUnusedAsset;
                }
                catch (Exception e)
                {
                    Debug.LogWarning("[LevelMiniature] drawing " + levelId + ": " + e.Message);
                }
            }
            miniatures[levelId] = sprite;
            return sprite;
        }

        // ===================================================================================================
        // The miniature: painted at twice the final size with signed distances, then box filtered.
        // ===================================================================================================

        private sealed class Raster
        {
            public readonly int W, H;
            public readonly Color[] Px;
            private readonly float scale, offX, offY, minX, minZ;

            public Raster(int w, int h, Rect world)
            {
                W = w;
                H = h;
                Px = new Color[w * h];
                scale = Mathf.Min(w / world.width, h / world.height);
                offX = (w - world.width * scale) * 0.5f;
                offY = (h - world.height * scale) * 0.5f;
                minX = world.xMin;
                minZ = world.yMin;
            }

            public float Scale => scale;
            public Vector2 ToPx(float x, float z) => new Vector2((x - minX) * scale + offX, (z - minZ) * scale + offY);

            /// <summary>Blends a shape given by its signed distance (in pixels) over its pixel bounds, antialiased over one pixel.</summary>
            public void Shape(Vector2 min, Vector2 max, Func<Vector2, float> distance, Color color)
            {
                int x0 = Mathf.Max(0, Mathf.FloorToInt(min.x) - 1);
                int y0 = Mathf.Max(0, Mathf.FloorToInt(min.y) - 1);
                int x1 = Mathf.Min(W - 1, Mathf.CeilToInt(max.x) + 1);
                int y1 = Mathf.Min(H - 1, Mathf.CeilToInt(max.y) + 1);
                for (int y = y0; y <= y1; y++)
                {
                    for (int x = x0; x <= x1; x++)
                    {
                        float coverage = Mathf.Clamp01(0.5f - distance(new Vector2(x + 0.5f, y + 0.5f)));
                        if (coverage > 0f)
                        {
                            Blend(y * W + x, color, coverage);
                        }
                    }
                }
            }

            private void Blend(int i, Color src, float coverage)
            {
                Color dst = Px[i];
                float a = src.a * coverage;
                float outA = a + dst.a * (1f - a);
                if (outA <= 0f)
                {
                    return;
                }
                float keep = dst.a * (1f - a);
                Px[i] = new Color((src.r * a + dst.r * keep) / outA, (src.g * a + dst.g * keep) / outA, (src.b * a + dst.b * keep) / outA, outA);
            }

            /// <summary>A world box (centre, size, yaw in degrees) with rounded corners (radius in pixels).</summary>
            public void Box(float x, float z, float sizeX, float sizeZ, float yaw, float radius, Color color, float minPixels = 2f)
            {
                Vector2 c = ToPx(x, z);
                float hx = Mathf.Max(minPixels, sizeX * scale) * 0.5f;
                float hz = Mathf.Max(minPixels, sizeZ * scale) * 0.5f;
                float r = Mathf.Min(radius, Mathf.Min(hx, hz));
                // A positive yaw turns clockwise seen from above (Unity's y rotation): undo it on the sample point.
                float rad = yaw * Mathf.Deg2Rad;
                float cos = Mathf.Cos(rad), sin = Mathf.Sin(rad);
                float reach = Mathf.Sqrt(hx * hx + hz * hz);
                Shape(c - Vector2.one * reach, c + Vector2.one * reach, p =>
                {
                    Vector2 d = p - c;
                    // Inverse of a clockwise turn by yaw in the (x, z) plane.
                    var local = new Vector2(d.x * cos - d.y * sin, d.x * sin + d.y * cos);
                    Vector2 q = new Vector2(Mathf.Abs(local.x) - hx + r, Mathf.Abs(local.y) - hz + r);
                    return new Vector2(Mathf.Max(q.x, 0f), Mathf.Max(q.y, 0f)).magnitude + Mathf.Min(Mathf.Max(q.x, q.y), 0f) - r;
                }, color);
            }

            public void Disc(Vector2 c, float radius, Color color)
            {
                Shape(c - Vector2.one * radius, c + Vector2.one * radius, p => (p - c).magnitude - radius, color);
            }

            public void Line(Vector2 a, Vector2 b, float width, Color color)
            {
                float h = width * 0.5f;
                Shape(Vector2.Min(a, b) - Vector2.one * h, Vector2.Max(a, b) + Vector2.one * h, p => Segment(p, a, b) - h, color);
            }

            /// <summary>A dashed line, dash and gap in pixels.</summary>
            public void Dashed(Vector2 a, Vector2 b, float width, float dash, float gap, Color color)
            {
                float length = (b - a).magnitude;
                if (length < 0.01f)
                {
                    return;
                }
                Vector2 dir = (b - a) / length;
                for (float t = 0f; t < length; t += dash + gap)
                {
                    Line(a + dir * t, a + dir * Mathf.Min(length, t + dash), width, color);
                }
            }

            /// <summary>Halves the resolution with a 2 x 2 box filter (premultiplied, so transparent pixels never darken edges).</summary>
            public Color[] Downsample(out int w, out int h)
            {
                w = W / 2;
                h = H / 2;
                var result = new Color[w * h];
                for (int y = 0; y < h; y++)
                {
                    for (int x = 0; x < w; x++)
                    {
                        float r = 0f, g = 0f, b = 0f, a = 0f;
                        for (int k = 0; k < 4; k++)
                        {
                            Color c = Px[(y * 2 + (k >> 1)) * W + x * 2 + (k & 1)];
                            r += c.r * c.a;
                            g += c.g * c.a;
                            b += c.b * c.a;
                            a += c.a;
                        }
                        result[y * w + x] = a > 0f ? new Color(r / a, g / a, b / a, a * 0.25f) : new Color(0f, 0f, 0f, 0f);
                    }
                }
                return result;
            }
        }

        private static float Segment(Vector2 p, Vector2 a, Vector2 b)
        {
            Vector2 ab = b - a;
            float len2 = ab.sqrMagnitude;
            float t = len2 > 1e-6f ? Mathf.Clamp01(Vector2.Dot(p - a, ab) / len2) : 0f;
            return (p - (a + ab * t)).magnitude;
        }

        /// <summary>A room floor colour mapped onto the warm wood ramp of the page (dark wood to cream), keeping a hint of its hue.</summary>
        private static Color WarmFloor(string hex)
        {
            Color c = LevelJson.ParseColor(hex, new Color(0.69f, 0.48f, 0.31f, 1f));
            float luminance = 0.299f * c.r + 0.587f * c.g + 0.114f * c.b;
            Color ramp = Color.Lerp(WoodDark, WoodLight, Mathf.InverseLerp(0.3f, 0.95f, luminance));
            Color warm = Color.Lerp(ramp, c, 0.22f);
            warm.a = 1f;
            return warm;
        }

        private static Texture2D Draw(LevelDef def, int width, int height)
        {
            List<RoomDef> rooms = def.AllRooms();
            float wall = def.WallThickness();
            Rect bounds = def.InteriorBounds();
            bounds = Rect.MinMaxRect(bounds.xMin - wall, bounds.yMin - wall, bounds.xMax + wall, bounds.yMax + wall);
            if (def.Exit != null)
            {
                bounds = Grow(bounds, def.Exit.X - def.Exit.SizeX * 0.5f, def.Exit.Z - def.Exit.SizeZ * 0.5f);
                bounds = Grow(bounds, def.Exit.X + def.Exit.SizeX * 0.5f, def.Exit.Z + def.Exit.SizeZ * 0.5f);
            }
            float pad = Tuning.LevelMiniaturePadding;
            bounds = Rect.MinMaxRect(bounds.xMin - pad, bounds.yMin - pad, bounds.xMax + pad, bounds.yMax + pad);
            if (bounds.width <= 0f || bounds.height <= 0f)
            {
                bounds = new Rect(-5f, -5f, 10f, 10f);
            }

            var raster = new Raster(width * 2, height * 2, bounds);
            float s = raster.Scale;
            float px = 2f; // one final pixel, in raster pixels

            // 1. Floors.
            foreach (RoomDef r in rooms)
            {
                Color floor = WarmFloor(r.FloorColor);
                if (r.IsSoft)
                {
                    floor = Color.Lerp(floor, new Color(0.72f, 0.5f, 0.42f, 1f), 0.25f);
                }
                raster.Box(r.X, r.Z, r.SizeX + wall, r.SizeZ + wall, 0f, 0f, floor);
            }
            // Doorway thresholds: the floor runs through every door, so the gap in the wall reads as an opening.
            foreach (OpeningDef door in def.Doors ?? new List<OpeningDef>())
            {
                foreach (RoomSide side in def.SidesOf(door, out float along))
                {
                    Color floor = WarmFloor(rooms[side.Room].FloorColor);
                    float depth = wall * 2f + 2f * px / s;
                    if (side.AlongX)
                    {
                        raster.Box(along, side.Line, door.Width, depth, 0f, 0f, floor);
                    }
                    else
                    {
                        raster.Box(side.Line, along, depth, door.Width, 0f, 0f, floor);
                    }
                }
            }

            // 2. Rugs, soft and translucent.
            foreach (RugDef rug in def.Rugs ?? new List<RugDef>())
            {
                Color c = Color.Lerp(LevelJson.ParseColor(rug.Color, new Color(0.7f, 0.4f, 0.35f, 1f)), WoodLight, 0.25f);
                c.a = 0.5f;
                raster.Box(rug.X, rug.Z, rug.SizeX, rug.SizeZ, rug.Yaw, 6f * px, c);
            }

            // 3. Routes: each inhabitant's loop of stations (faint), the robot's loop (dashed steel).
            foreach (InhabitantDef inhabitant in def.Inhabitants ?? new List<InhabitantDef>())
            {
                List<StationDef> stations = inhabitant.Stations;
                if (stations == null || stations.Count < 2)
                {
                    continue;
                }
                Color route = IsPet(inhabitant) ? PetAmber : Ink;
                route.a = 0.3f;
                for (int i = 0; i < stations.Count; i++)
                {
                    StationDef a = stations[i];
                    StationDef b = stations[(i + 1) % stations.Count];
                    raster.Dashed(raster.ToPx(a.X, a.Z), raster.ToPx(b.X, b.Z), 1.4f * px, 4f * px, 3f * px, route);
                }
            }
            foreach (RobotDef r in def.Robots ?? new List<RobotDef>())
            {
                if (r.Loop == null || r.Loop.Count < 2)
                {
                    continue;
                }
                Color route = RobotSteel;
                route.a = 0.55f;
                for (int i = 0; i < r.Loop.Count; i++)
                {
                    PointDef a = r.Loop[i];
                    PointDef b = r.Loop[(i + 1) % r.Loop.Count];
                    raster.Dashed(raster.ToPx(a.X, a.Z), raster.ToPx(b.X, b.Z), 1.4f * px, 2.5f * px, 2.5f * px, route);
                }
            }

            // 4. Props: rounded blocks with a lighter top; plants as round leaves; decoys (the other furniture) reddish.
            foreach (PropDef prop in def.Props ?? new List<PropDef>())
            {
                if (prop.Kind == "plant")
                {
                    float radius = Mathf.Max(2.5f * px, Mathf.Max(prop.SizeX, prop.SizeZ) * 0.5f * s);
                    raster.Disc(raster.ToPx(prop.X, prop.Z), radius, PlantFill);
                    continue;
                }
                raster.Box(prop.X, prop.Z, prop.SizeX, prop.SizeZ, prop.Yaw, 3f * px, PropFill, 3f * px);
                raster.Box(prop.X, prop.Z, prop.SizeX * 0.6f, prop.SizeZ * 0.6f, prop.Yaw, 2f * px, PropTop, 1f * px);
            }
            foreach (DecoyDef decoy in def.Decoys ?? new List<DecoyDef>())
            {
                Vector3 size = def.DecoySize(decoy);
                raster.Box(decoy.X, decoy.Z, size.x, size.z, decoy.Yaw, 2f * px, DecoyFill, 3f * px);
            }

            // 5. Walls: every room side as a cream line, broken at its doors; windows as pale blue strokes over it.
            float wallWidth = Mathf.Max(Tuning.LevelMiniatureWallPixels * px, wall * s);
            List<RoomSide> sides = def.Sides();
            var gaps = new Dictionary<int, List<Vector2>>();
            CollectGaps(def, def.Doors, sides, gaps);
            for (int i = 0; i < sides.Count; i++)
            {
                RoomSide side = sides[i];
                float half = wall * 0.5f;
                var spans = new List<Vector2> { new Vector2(side.From - half, side.To + half) };
                if (gaps.TryGetValue(i, out List<Vector2> cut))
                {
                    foreach (Vector2 g in cut)
                    {
                        spans = Subtract(spans, g);
                    }
                }
                foreach (Vector2 span in spans)
                {
                    Vector2 a = side.AlongX ? raster.ToPx(span.x, side.Line) : raster.ToPx(side.Line, span.x);
                    Vector2 b = side.AlongX ? raster.ToPx(span.y, side.Line) : raster.ToPx(side.Line, span.y);
                    raster.Line(a, b, wallWidth, Ink);
                }
            }
            foreach (OpeningDef window in def.Windows ?? new List<OpeningDef>())
            {
                foreach (RoomSide side in def.SidesOf(window, out float along))
                {
                    float h = window.Width * 0.5f;
                    Vector2 a = side.AlongX ? raster.ToPx(along - h, side.Line) : raster.ToPx(side.Line, along - h);
                    Vector2 b = side.AlongX ? raster.ToPx(along + h, side.Line) : raster.ToPx(side.Line, along + h);
                    raster.Line(a, b, wallWidth * 0.8f, Window);
                }
            }

            // 6. The exit: a green rounded mark.
            if (def.Exit != null)
            {
                Color exit = ExitGreen;
                raster.Box(def.Exit.X, def.Exit.Z, Mathf.Max(0.5f, def.Exit.SizeX), Mathf.Max(0.5f, def.Exit.SizeZ), 0f, 4f * px, Outline, 7f * px);
                raster.Box(def.Exit.X, def.Exit.Z, Mathf.Max(0.5f, def.Exit.SizeX) - 2.4f * px / s, Mathf.Max(0.5f, def.Exit.SizeZ) - 2.4f * px / s,
                    0f, 3f * px, exit, 5f * px);
            }

            // 7. The watchers where they start: people cream, pets amber, robots steel, each ringed in dark ink.
            float watcher = Mathf.Max(2.6f * px, 0.24f * s);
            foreach (InhabitantDef inhabitant in def.Inhabitants ?? new List<InhabitantDef>())
            {
                if (inhabitant.Stations == null || inhabitant.Stations.Count == 0)
                {
                    continue;
                }
                StationDef start = inhabitant.Stations[Mathf.Clamp(inhabitant.StartStation, 0, inhabitant.Stations.Count - 1)];
                Vector2 c = raster.ToPx(start.X, start.Z);
                raster.Disc(c, watcher + 1.2f * px, Outline);
                raster.Disc(c, watcher, IsPet(inhabitant) ? PetAmber : Ink);
            }
            foreach (RobotDef r in def.Robots ?? new List<RobotDef>())
            {
                if (r.Loop == null || r.Loop.Count == 0)
                {
                    continue;
                }
                PointDef start = r.Loop[Mathf.Clamp(r.Start, 0, r.Loop.Count - 1)];
                Vector2 c = raster.ToPx(start.X, start.Z);
                raster.Disc(c, watcher + 1.2f * px, Outline);
                raster.Disc(c, watcher, RobotSteel);
            }

            // 8. The player: a red dot ringed in cream, the brightest thing on the plan.
            if (def.Player != null)
            {
                Vector2 c = raster.ToPx(def.Player.X, def.Player.Z);
                float radius = Mathf.Max(3.5f * px, Tuning.LevelMiniaturePlayerRadius * s);
                raster.Disc(c, radius + 2.6f * px, Outline);
                raster.Disc(c, radius + 1.4f * px, Ink);
                raster.Disc(c, radius, ChairRed);
            }

            Color[] pixels = raster.Downsample(out int outW, out int outH);
            var texture = new Texture2D(outW, outH, TextureFormat.RGBA32, false)
            {
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear,
                hideFlags = HideFlags.DontUnloadUnusedAsset,
            };
            texture.SetPixels(pixels);
            texture.Apply(false, true);
            return texture;
        }

        private static Rect Grow(Rect r, float x, float z)
        {
            return Rect.MinMaxRect(Mathf.Min(r.xMin, x), Mathf.Min(r.yMin, z), Mathf.Max(r.xMax, x), Mathf.Max(r.yMax, z));
        }

        /// <summary>Per side index, the spans along the wall that doors open (a shared wall gets the gap on both of its sides).</summary>
        private static void CollectGaps(LevelDef def, List<OpeningDef> doors, List<RoomSide> sides, Dictionary<int, List<Vector2>> gaps)
        {
            if (doors == null)
            {
                return;
            }
            foreach (OpeningDef door in doors)
            {
                foreach (RoomSide side in def.SidesOf(door, out float along))
                {
                    int index = sides.FindIndex(s => s.Room == side.Room && s.Side == side.Side);
                    if (index < 0)
                    {
                        continue;
                    }
                    if (!gaps.TryGetValue(index, out List<Vector2> list))
                    {
                        gaps[index] = list = new List<Vector2>();
                    }
                    list.Add(new Vector2(along - door.Width * 0.5f, along + door.Width * 0.5f));
                }
            }
        }

        private static List<Vector2> Subtract(List<Vector2> spans, Vector2 gap)
        {
            var result = new List<Vector2>();
            foreach (Vector2 s in spans)
            {
                if (gap.y <= s.x || gap.x >= s.y)
                {
                    result.Add(s);
                    continue;
                }
                if (gap.x > s.x)
                {
                    result.Add(new Vector2(s.x, gap.x));
                }
                if (gap.y < s.y)
                {
                    result.Add(new Vector2(gap.y, s.y));
                }
            }
            return result;
        }

        // ===================================================================================================
        // Glyphs: signed distance silhouettes in [-1, 1], filled and ringed in dark ink so they read on brown and on red.
        // ===================================================================================================

        public static Sprite Person => person != null ? person : person = Glyph(96, PersonShape, Ink, "SelectPerson");
        public static Sprite Pet => pet != null ? pet : pet = Glyph(96, PetShape, PetAmber, "SelectPet");
        public static Sprite Robot => robot != null ? robot : robot = Glyph(96, RobotShape, RobotSteel, "SelectRobot");
        public static Sprite Lock => lockGlyph != null ? lockGlyph : lockGlyph = Glyph(128, LockShape, Ink, "SelectLock");
        public static Sprite Check => check != null ? check : check = Glyph(96, p => (p.magnitude - 0.86f), ExitGreen, "SelectCheck", CheckMark);
        public static Sprite Dot => dot != null ? dot : dot = Glyph(96, p => p.magnitude - 0.62f, ChairRed, "SelectDot", null, Ink);
        public static Sprite ExitMark => exitMark != null ? exitMark : exitMark = Glyph(96, p => RoundBox(p, new Vector2(0.62f, 0.62f), 0.22f), ExitGreen, "SelectExit");

        /// <summary>The red side silhouette of a furniture kind (BodyKinds), the chair for anything unknown.</summary>
        public static Sprite Furniture(string kind)
        {
            string k = BodyKinds.Of(kind);
            if (!furniture.TryGetValue(k, out Sprite sprite) || sprite == null)
            {
                Func<Vector2, float> shape;
                switch (k)
                {
                    case BodyKinds.Stool: shape = StoolShape; break;
                    case BodyKinds.Armchair: shape = ArmchairShape; break;
                    case BodyKinds.FloorLamp: shape = LampShape; break;
                    case BodyKinds.OfficeChair: shape = OfficeChairShape; break;
                    case BodyKinds.RockingChair: shape = RockingChairShape; break;
                    default: shape = ChairShape; break;
                }
                furniture[k] = sprite = Glyph(128, shape, ChairRed, "SelectFurniture_" + k);
            }
            return sprite;
        }

        private static Sprite Glyph(int size, Func<Vector2, float> shape, Color fill, string name, Func<Vector2, float> mark = null, Color? ring = null)
        {
            var texture = new Texture2D(size, size, TextureFormat.RGBA32, false)
            {
                name = name,
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear,
                hideFlags = HideFlags.DontUnloadUnusedAsset,
            };
            var pixels = new Color[size * size];
            float pixel = 2f / size;
            const float outline = 0.1f;
            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    var p = new Vector2((x + 0.5f) / size * 2f - 1f, (y + 0.5f) / size * 2f - 1f) * 1.08f;
                    float d = shape(p);
                    float outer = Mathf.Clamp01(0.5f - (d - outline) / pixel);
                    float inner = Mathf.Clamp01(0.5f - d / pixel);
                    Color c = Color.Lerp(ring ?? Outline, fill, ring.HasValue ? Mathf.Clamp01(0.5f - (d + 0.12f) / pixel) : inner);
                    if (ring.HasValue)
                    {
                        // A ringed dot: dark outside edge, cream ring, red heart.
                        c = Color.Lerp(Outline, c, inner);
                    }
                    if (mark != null)
                    {
                        c = Color.Lerp(c, Color.white, Mathf.Clamp01(0.5f - mark(p) / pixel) * inner);
                    }
                    c.a = outer;
                    pixels[y * size + x] = c;
                }
            }
            texture.SetPixels(pixels);
            texture.Apply(false, true);
            Sprite sprite = Sprite.Create(texture, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect);
            sprite.name = name;
            sprite.hideFlags = HideFlags.DontUnloadUnusedAsset;
            return sprite;
        }

        private static float Seg(Vector2 p, float ax, float ay, float bx, float by, float radius) => Segment(p, new Vector2(ax, ay), new Vector2(bx, by)) - radius;

        private static float RoundBox(Vector2 p, Vector2 half, float r)
        {
            Vector2 q = new Vector2(Mathf.Abs(p.x) - half.x + r, Mathf.Abs(p.y) - half.y + r);
            return new Vector2(Mathf.Max(q.x, 0f), Mathf.Max(q.y, 0f)).magnitude + Mathf.Min(Mathf.Max(q.x, q.y), 0f) - r;
        }

        private static float Min(params float[] d)
        {
            float m = float.MaxValue;
            foreach (float v in d)
            {
                m = Mathf.Min(m, v);
            }
            return m;
        }

        private static float PersonShape(Vector2 p)
        {
            float head = (p - new Vector2(0f, 0.42f)).magnitude - 0.3f;
            // Shoulders: a wide capsule cut flat at the bottom.
            float body = Mathf.Max(Seg(p, -0.24f, -0.42f, 0.24f, -0.42f, 0.42f), -(p.y + 0.8f));
            return Mathf.Min(head, body);
        }

        private static float PetShape(Vector2 p)
        {
            return Min(
                Seg(p, -0.45f, -0.05f, 0.3f, -0.05f, 0.22f),   // body
                (p - new Vector2(0.5f, 0.3f)).magnitude - 0.22f, // head
                Seg(p, 0.55f, 0.24f, 0.8f, 0.18f, 0.1f),        // snout
                Seg(p, 0.42f, 0.42f, 0.36f, 0.68f, 0.08f),      // ear
                Seg(p, -0.38f, -0.1f, -0.42f, -0.72f, 0.08f),   // back leg
                Seg(p, 0.24f, -0.1f, 0.28f, -0.72f, 0.08f),     // front leg
                Seg(p, -0.55f, 0.05f, -0.78f, 0.42f, 0.06f));   // tail
        }

        private static float RobotShape(Vector2 p)
        {
            // A robot vacuum from above: a disc with a bumper groove and a sensor dot.
            float disc = p.magnitude - 0.8f;
            float groove = p.y > 0.05f ? Mathf.Abs(p.magnitude - 0.54f) - 0.05f : 1f;
            float sensor = (p - new Vector2(0f, 0.22f)).magnitude - 0.12f;
            return Mathf.Max(disc, -Mathf.Min(groove, sensor));
        }

        private static float LockShape(Vector2 p)
        {
            float body = RoundBox(p - new Vector2(0f, -0.28f), new Vector2(0.58f, 0.44f), 0.12f);
            float shackle = Mathf.Abs((p - new Vector2(0f, 0.2f)).magnitude - 0.36f) - 0.1f;
            shackle = Mathf.Max(shackle, -(p.y - 0.15f));
            float hole = Seg(p, 0f, -0.2f, 0f, -0.42f, 0.08f);
            return Mathf.Max(Mathf.Min(body, shackle), -hole);
        }

        private static float CheckMark(Vector2 p) => Mathf.Min(Seg(p, -0.42f, 0.02f, -0.12f, -0.3f, 0.11f), Seg(p, -0.12f, -0.3f, 0.44f, 0.32f, 0.11f));

        private static float ChairShape(Vector2 p)
        {
            return Min(
                Seg(p, -0.38f, 0.78f, -0.38f, -0.02f, 0.1f),
                Seg(p, -0.38f, -0.02f, 0.42f, -0.02f, 0.1f),
                Seg(p, -0.36f, -0.02f, -0.4f, -0.8f, 0.07f),
                Seg(p, 0.4f, -0.02f, 0.44f, -0.8f, 0.07f));
        }

        private static float StoolShape(Vector2 p)
        {
            return Min(
                Seg(p, -0.42f, 0.32f, 0.42f, 0.32f, 0.12f),
                Seg(p, -0.3f, 0.3f, -0.48f, -0.8f, 0.07f),
                Seg(p, 0.3f, 0.3f, 0.48f, -0.8f, 0.07f),
                Seg(p, -0.4f, -0.36f, 0.4f, -0.36f, 0.05f));
        }

        private static float ArmchairShape(Vector2 p)
        {
            return Min(
                RoundBox(p - new Vector2(-0.52f, 0.2f), new Vector2(0.2f, 0.58f), 0.14f),  // back
                RoundBox(p - new Vector2(0.05f, -0.22f), new Vector2(0.6f, 0.22f), 0.1f),  // seat
                RoundBox(p - new Vector2(0.05f, 0.12f), new Vector2(0.5f, 0.1f), 0.08f),   // arm
                Seg(p, -0.5f, -0.45f, -0.52f, -0.78f, 0.07f),
                Seg(p, 0.55f, -0.45f, 0.57f, -0.78f, 0.07f));
        }

        private static float LampShape(Vector2 p)
        {
            // A shade (trapezoid as a rounded box squeezed at the top), a pole and a round foot.
            float shadeHalf = Mathf.Lerp(0.42f, 0.24f, Mathf.InverseLerp(0.45f, 0.9f, p.y));
            float shade = Mathf.Max(Mathf.Abs(p.x) - shadeHalf, Mathf.Abs(p.y - 0.67f) - 0.23f);
            return Min(shade, Seg(p, 0f, 0.45f, 0f, -0.72f, 0.06f), Seg(p, -0.3f, -0.8f, 0.3f, -0.8f, 0.08f));
        }

        private static float OfficeChairShape(Vector2 p)
        {
            return Min(
                RoundBox(p - new Vector2(-0.3f, 0.52f), new Vector2(0.14f, 0.34f), 0.12f), // back pad
                Seg(p, -0.3f, 0.2f, -0.2f, -0.02f, 0.06f),
                RoundBox(p - new Vector2(0.06f, -0.04f), new Vector2(0.44f, 0.1f), 0.08f), // seat
                Seg(p, 0.04f, -0.1f, 0.04f, -0.56f, 0.07f),                                // post
                Seg(p, -0.44f, -0.62f, 0.52f, -0.62f, 0.06f),                              // base
                (p - new Vector2(-0.44f, -0.78f)).magnitude - 0.1f,                         // wheels
                (p - new Vector2(0.52f, -0.78f)).magnitude - 0.1f);
        }

        private static float RockingChairShape(Vector2 p)
        {
            // The chair, raised, on a rocker: an arc of a large circle under the legs.
            float rocker = Mathf.Abs((p - new Vector2(0f, 0.9f)).magnitude - 1.62f) - 0.06f;
            rocker = Mathf.Max(rocker, Mathf.Abs(p.x) - 0.7f);
            return Min(
                Seg(p, -0.46f, 0.84f, -0.36f, 0.04f, 0.09f),
                Seg(p, -0.36f, 0.04f, 0.42f, 0.04f, 0.09f),
                Seg(p, -0.34f, 0.04f, -0.36f, -0.66f, 0.06f),
                Seg(p, 0.4f, 0.04f, 0.42f, -0.66f, 0.06f),
                rocker);
        }
    }
}
