using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>
    /// M8 secondary lighting (docs/m8/ROOMS_PLAN.md 5), visual only: one or two light fixtures per room by its type
    /// (<see cref="RoomDef.Type"/>): a small emissive mesh and an unshadowed spot light. No rule reads them: vision
    /// is geometry and range only (Vision, VisionMath, the lamp's own on/off factor), the fixtures carry no collider and
    /// stand on the Default layer (never an occluder, a NavMesh source, an obstacle or an x-ray mark), and the sun stays the
    /// one shadowed light (Main.LookProblems).
    ///
    /// Fixtures by type (placed from the room's size, its doors, windows and props; never in a doorway or over a window, never
    /// over a prop taller than the fixture): bathroom a cool neon tube on a wall (over the washbasin when there is one);
    /// kitchen a neutral white strip on the wall over the longest counter run (else a wall strip); dining a warm globe lamp in
    /// the middle of the largest table; living warm wall lights; bedroom a dim warm bedside lamp on the nightstand (else a reading light by
    /// the bed head, else a wall light); study a desk lamp on the largest table; hall and corridor warm wall sconces. A large
    /// room gets a second fixture (<see cref="MaxPerRoom"/>). The room field "lightWall" (<see cref="RoomDef.LightWall"/>)
    /// pins the wall fixtures to one wall, or gives the room none.
    ///
    /// Every light is an unshadowed spot standing higher than its fixture (there is no ceiling: a wider, softer pool, and no
    /// burnt surface right under the fixture), aimed at the floor half way across the room (a lamp: straight down, tipped
    /// away from a near wall), its cone stopping short of the wall behind it so nothing leaks into the next room, its intensity
    /// set from the light its pool centre should get (the mood's Pool) and capped for the nearest surface under it. Nothing
    /// hangs in mid-air: a pendant would hide the player furniture from the high camera, and a wall fixture's glow goes with
    /// its wall line (M7 walls pass, <see cref="FollowWalls"/>): it shows only while that line fully stands, so a lowered wall
    /// never leaves its sconce floating and a see-through wall never carries an opaque one. Its light stays (visual only).
    ///
    /// Budgets (PRD 7.4): the glows of a level draw as at most two renderers (one per colour family, combined), with materials
    /// the level usually already has: the warm family is the floor lamp's glow material (LampLight), the cool family the window
    /// pane's (LevelBuilder). So a level gains at most two draw calls and, unless it has a floor lamp, one material.
    ///
    /// Housings (product owner request, 2026-11-19): every wall fixture (sconce, reading light, neon tube, counter strip) sits
    /// in a slim black metal housing, a backplate with softened corners and end caps or rims around its glow, so it reads as
    /// a real fixture rather than a floating glowing bar. The housing is merged into its wall line's cap (the renderer whose
    /// fade the glow follows) as flat vertices of the wall material (WallArray.Flat: the household's near-black at the
    /// models' finish, exactly how the handles' dark metal shows), so it costs no material and no draw call, and it sinks,
    /// fades and comes back with its wall by construction. A level whose walls keep their URP Lit materials (textures off)
    /// shows no housing. About 22 triangles per housing box, three boxes per fixture.
    ///
    /// Quality tiers (QualityTier): Bas keeps the glowing fixtures and switches every light off; Moyen keeps the first light of
    /// each room (the Forward renderer of Mobile_RPAsset shades at most 4 additional lights per object); Haut keeps them all
    /// (Forward+). The tier is read when the level is built and again whenever it changes (a string compare per frame, no
    /// allocation). Only <see cref="Light.enabled"/> changes, never an intensity, so LampLight's room dimming (every enabled
    /// point or spot light standing in the lamp's room, to Tuning.LampOffLight) dims these lights and restores them exactly.
    /// </summary>
    public sealed class RoomLights : MonoBehaviour
    {
        /// <summary>The name of the root under the level root.</summary>
        public const string RootName = "RoomLights";

        /// <summary>At most this many fixtures (and lights) per room; Haut keeps them all.</summary>
        public const int MaxPerRoom = 2;

        /// <summary>Tests and tools: build no fixture and no light (the level as it was before M8).</summary>
        public static bool Disabled;

        public enum Style
        {
            /// <summary>A warm wall light (spot).</summary>
            Sconce,
            /// <summary>The bathroom's neon tube (spot).</summary>
            Tube,
            /// <summary>The kitchen's light strip on the wall (spot).</summary>
            Strip,
            /// <summary>A small globe lamp in the middle of the dining table (spot from above).</summary>
            TableLamp,
            /// <summary>A small globe lamp on a desk (spot from above).</summary>
            DeskLamp,
            /// <summary>A small globe lamp on a nightstand (spot from above).</summary>
            Bedside,
            /// <summary>A small wall light beside the bed head (spot).</summary>
            Reading,
        }

        /// <summary>One fixture: its room, its kind, its rank in the room (0 first) and its light.</summary>
        public sealed class Fixture
        {
            public RoomDef Room;
            public string Type;
            public Style Style;
            public int Rank;
            public Light Light;
            /// <summary>The cool glow family (the window pane's material); false: the warm one (the lamp glow's).</summary>
            public bool Cool;
            /// <summary>The light's intensity as built (LampLight may dim it for a while).</summary>
            public float Intensity;
        }

        private readonly List<Fixture> fixtures = new List<Fixture>();

        /// <summary>Every fixture of the level, rooms in level order.</summary>
        public IReadOnlyList<Fixture> Fixtures => fixtures;

        /// <summary>The tier applied last ("low", "medium" or "high").</summary>
        public string Tier { get; private set; }

        /// <summary>The glow renderers (one per family when combined), for tests and budgets.</summary>
        public readonly List<MeshRenderer> Glows = new List<MeshRenderer>();

        /// <summary>The wall caps that carry fixture housings (their own renderers, for tests and shots).</summary>
        public readonly List<MeshRenderer> Housings = new List<MeshRenderer>();

        private string seenTier;

        /// <summary>How many of this level's lights are enabled now.</summary>
        public int EnabledLights
        {
            get
            {
                int n = 0;
                foreach (Fixture f in fixtures)
                {
                    if (f.Light != null && f.Light.enabled)
                    {
                        n++;
                    }
                }
                return n;
            }
        }

        /// <summary>The lights a room keeps on a tier: none on Bas, its first on Moyen, all of them on Haut (and in edit mode).</summary>
        public static int AllowedPerRoom(string quality)
        {
            return quality == SaveOptions.QualityLow ? 0 : quality == SaveOptions.QualityMedium ? 1 : MaxPerRoom; // MUTATION:LIGHTS_TIER
        }

        /// <summary>Enables the lights the tier allows (<see cref="AllowedPerRoom"/>, by rank in the room). Never touches an intensity.</summary>
        public void ApplyTier(string quality)
        {
            Tier = string.IsNullOrEmpty(quality) ? SaveOptions.QualityHigh : quality;
            int allowed = AllowedPerRoom(Tier);
            foreach (Fixture f in fixtures)
            {
                if (f.Light != null)
                {
                    bool on = f.Rank < allowed;
                    if (f.Light.enabled != on)
                    {
                        f.Light.enabled = on;
                    }
                }
            }
        }

        private void LateUpdate()
        {
            // The Qualité option can change while a level is played: follow it (no allocation, a string compare).
            string tier = QualityTier.Applied;
            if (tier != seenTier)
            {
                seenTier = tier;
                ApplyTier(tier);
            }
        }

        // ----- Building -----

        // Not in Tuning: presentation only, the rules never read any of it.
        // A fixture keeps this far from a room corner, a doorway and a window (metres, along the wall).
        private const float CornerMargin = 0.35f;
        private const float DoorMargin = 0.3f;
        private const float WindowMargin = 0.15f;
        // A prop this close to a wall (or closer) stands under its wall fixtures; it blocks them when it reaches this far
        // below the fixture (a wardrobe under a sconce), and it frees this much room on each side.
        private const float PropWallGap = 0.6f;
        private const float PropHeadroom = 0.35f;
        private const float PropMargin = 0.12f;
        // A counter, a washbasin or a bed head this close to a wall is against it.
        private const float AgainstWall = 0.25f;
        // Two fixtures of a room stand at least this far apart.
        private const float Spacing = 1.8f;
        // Fixture heights above the floor (wall fixtures) and how far their light stands off the wall.
        private const float SconceHeight = 1.85f;
        private const float TubeHeight = 1.95f;
        private const float TubeOverBasin = 1.8f;
        private const float StripOverCounter = 0.5f;
        private const float ReadingHeight = 1.15f;
        private const float BedroomWallHeight = 1.6f;
        // Room sizes that get a second fixture.
        private const float SecondArea = 18f;
        private const float SecondLength = 5f;

        // The light itself. There is no ceiling and the camera looks from above, so the source stands higher than its
        // fixture (a wall light's at SourceHeight, LightOffWall off its wall; a lamp's SourceAboveLamp over its globe): the
        // pool it casts is wider and softer, and the surfaces right under the fixture (a sofa back, a basin) do not burn out.
        private const float SourceHeight = 2.45f;
        private const float LightOffWall = 0.35f;
        private const float SourceAboveLamp = 1.0f;
        // A spot never shines behind its own wall: its cone stops this far short of the wall's far face.
        private const float BehindWall = 0.12f;
        // The intensity gives the pool centre the mood's Pool (added linear light, the sun gives a lit floor about 1) through
        // URP's inverse square falloff, the range ending at RangeOverReach times that distance (its smooth window then keeps
        // about RangeKeep of it), and is capped so the nearest lit surface (a prop top under the light) gets at most NearCap.
        private const float RangeOverReach = 1.8f;
        private const float RangeKeep = 0.82f;
        private const float NearCap = 1.2f;

        // The two glow materials (PRD 7.4: one per colour family, both shared with what a level usually already draws).
        // Warm: exactly the floor lamp's glow (LampLight.GlowColor x GlowIntensity), so a lamp level shares it.
        private static readonly Color WarmGlow = new Color(1f, 0.8f, 0.46f);
        private const float WarmGlowIntensity = 1.9f;
        // Cool: exactly the window pane's (LevelBuilder.WindowPane x Tuning.WindowPaneEmission, its smoothness): every level
        // with a window shares it.
        private static readonly Color CoolGlow = new Color32(0xBF, 0xE3, 0xF5, 0xFF);

        /// <summary>A light mood of a room type: the light's colour, the light its pool centre gets, and its glow family.</summary>
        private readonly struct Mood
        {
            public readonly Color Colour;
            public readonly float Pool;
            public readonly bool Cool;

            public Mood(Color colour, float pool, bool cool)
            {
                Colour = colour;
                Pool = pool;
                Cool = cool;
            }
        }

        // Colours read against the warm sun and the warm grade (Main: WhiteBalance +9): kept a little less saturated than the
        // black body ones, so a warm pool never pushes a wood floor toward the player's red (PRD 7.2).
        private static Mood MoodOf(string type)
        {
            switch (type)
            {
                case RoomTypes.Bathroom: return new Mood(new Color(0.80f, 0.89f, 1f), 0.65f, true); // about 6500 K, a touch blue
                case RoomTypes.Kitchen: return new Mood(new Color(1f, 0.94f, 0.86f), 0.7f, true); // about 4000 K, neutral
                case RoomTypes.Dining: return new Mood(new Color(1f, 0.80f, 0.60f), 0.6f, false); // about 2700 K
                case RoomTypes.Living: return new Mood(new Color(1f, 0.80f, 0.60f), 0.6f, false); // about 2700 K
                case RoomTypes.Bedroom: return new Mood(new Color(1f, 0.76f, 0.54f), 0.4f, false); // about 2400 K, dim
                case RoomTypes.Study: return new Mood(new Color(1f, 0.93f, 0.82f), 0.5f, false); // neutral
                case RoomTypes.Hall: return new Mood(new Color(1f, 0.81f, 0.62f), 0.6f, false); // warm sconce
                case RoomTypes.Corridor: return new Mood(new Color(1f, 0.81f, 0.62f), 0.55f, false); // warm sconce
                default: return default;
            }
        }

        /// <summary>
        /// The intensity that gives a surface <paramref name="reach"/> away along the axis <paramref name="pool"/> of light,
        /// capped so the surface straight below, <paramref name="near"/> away and seen at <paramref name="nearFactor"/> of the
        /// spot's full strength (its cone falloff), gets at most <see cref="NearCap"/>.
        /// </summary>
        private static float IntensityFor(float pool, float reach, float near, float nearFactor)
        {
            return Mathf.Min(pool * reach * reach / RangeKeep, NearCap * near * near / Mathf.Max(0.05f, nearFactor));
        }

        /// <summary>URP's spot falloff at <paramref name="angle"/> off the axis, for a cone of <paramref name="half"/> (its inner half is half of it).</summary>
        private static float SpotFactor(float angle, float half)
        {
            float cosOuter = Mathf.Cos(half * Mathf.Deg2Rad);
            float cosInner = Mathf.Cos(half * 0.5f * Mathf.Deg2Rad);
            float f = Mathf.Clamp01((Mathf.Cos(angle * Mathf.Deg2Rad) - cosOuter) / Mathf.Max(1e-4f, cosInner - cosOuter));
            return f * f;
        }

        private struct GlowPart
        {
            public Mesh Mesh;
            public Vector3 Position;
            public Quaternion Rotation;
            public Vector3 Scale;
            /// <summary>The wall line a wall fixture's glow hangs on (an index of <see cref="wallLines"/>); -1 for a lamp.</summary>
            public int Wall;
        }

        private readonly List<GlowPart> warmParts = new List<GlowPart>();
        private readonly List<GlowPart> coolParts = new List<GlowPart>();

        /// <summary>M7 walls pass: a wall line that carries fixtures, the cap renderer whose fade level it follows, and whether its glows show.</summary>
        private sealed class WallGlowLine
        {
            public bool AlongX;
            public float Line;
            public Renderer Cap;
            public bool Shown = true;
            /// <summary>The housing boxes of the fixtures on this line, placed in world space (merged into <see cref="Cap"/>).</summary>
            public readonly List<PrimitiveKit.CombinePart> Housing = new List<PrimitiveKit.CombinePart>();
        }

        /// <summary>A wall fixture's glow in its family's combined mesh (its vertex range), or its own renderer when not combined.</summary>
        private struct WallGlowPart
        {
            public int Line;
            public int Family;
            public int Start;
            public int Count;
            /// <summary>Where its vertices collapse while hidden (on the floor under it: no triangle left to draw).</summary>
            public Vector3 Collapsed;
            public Renderer Own;
        }

        /// <summary>A glow family's own copy of its combined mesh (the cached one is shared) and its vertices as built and as shown.</summary>
        private sealed class GlowMesh
        {
            public Mesh Mesh;
            public Vector3[] Rest;
            public Vector3[] Shown;
            public bool Dirty;
        }

        private readonly List<WallGlowLine> wallLines = new List<WallGlowLine>();
        private readonly List<WallGlowPart> wallParts = new List<WallGlowPart>();
        private readonly GlowMesh[] glowMeshes = new GlowMesh[2];
        private WallFader fader;

        /// <summary>
        /// Builds the fixtures and lights of every typed room of <paramref name="def"/> under <paramref name="levelRoot"/> (the
        /// level root, at the origin), and applies the current tier. With <paramref name="fader"/>, the wall fixtures' glows
        /// follow their wall line (<see cref="FollowWalls"/>). Null when <see cref="Disabled"/>.
        /// </summary>
        public static RoomLights Build(LevelDef def, Transform levelRoot, WallFader fader = null)
        {
            if (Disabled || def == null)
            {
                return null;
            }
            var go = new GameObject(RootName) { layer = 0 };
            go.transform.SetParent(levelRoot, false);
            RoomLights lights = go.AddComponent<RoomLights>();
            var placer = new Placer(def, lights);
            List<RoomDef> rooms = def.AllRooms();
            for (int i = 0; i < rooms.Count; i++)
            {
                placer.Room(i, rooms[i]);
            }
            lights.Flush(fader != null ? fader.transform.position.y : levelRoot.position.y);
            lights.Follow(levelRoot, fader);
            lights.seenTier = QualityTier.Applied;
            lights.ApplyTier(lights.seenTier);
            return lights;
        }

        /// <summary>
        /// The glows of each family as one renderer (or part by part when LevelBuilder.CombineRenderers is off). A wall glow
        /// collapses onto <paramref name="floor"/> while hidden.
        /// </summary>
        private void Flush(float floor)
        {
            FlushFamily(0, warmParts, PrimitiveKit.Emissive(WarmGlow, WarmGlowIntensity), "FixtureGlow Warm", floor);
            FlushFamily(1, coolParts, PrimitiveKit.Emissive(CoolGlow, Tuning.WindowPaneEmission, Tuning.WindowPaneSmoothness, 0f), "FixtureGlow Cool", floor);
            warmParts.Clear();
            coolParts.Clear();
        }

        private void FlushFamily(int family, List<GlowPart> parts, Material material, string name, float floor)
        {
            if (parts.Count == 0)
            {
                return;
            }
            Matrix4x4 toRoot = transform.worldToLocalMatrix;
            if (LevelBuilder.CombineRenderers)
            {
                var combine = new List<PrimitiveKit.CombinePart>(parts.Count);
                bool walls = false;
                int start = 0;
                foreach (GlowPart p in parts)
                {
                    combine.Add(new PrimitiveKit.CombinePart { Mesh = p.Mesh, Matrix = toRoot * Matrix4x4.TRS(p.Position, p.Rotation, p.Scale) });
                    int count = p.Mesh.vertexCount;
                    if (p.Wall >= 0)
                    {
                        walls = true;
                        wallParts.Add(new WallGlowPart
                        {
                            Line = p.Wall, Family = family, Start = start, Count = count,
                            Collapsed = toRoot.MultiplyPoint3x4(new Vector3(p.Position.x, floor, p.Position.z)),
                        });
                    }
                    start += count;
                }
                Mesh mesh = PrimitiveKit.CombinedMesh(combine);
                if (walls)
                {
                    // Its own copy: the combined mesh is cached and shared by every build of this level.
                    mesh = Instantiate(mesh);
                    mesh.name = name;
                    Vector3[] rest = mesh.vertices;
                    glowMeshes[family] = new GlowMesh { Mesh = mesh, Rest = rest, Shown = (Vector3[])rest.Clone() };
                }
                Glows.Add(Glow(PrimitiveKit.Part(transform, name, mesh, Vector3.zero, Quaternion.identity, Vector3.one, material, 0)));
                return;
            }
            foreach (GlowPart p in parts)
            {
                GameObject go = PrimitiveKit.Part(transform, name, p.Mesh, Vector3.zero, Quaternion.identity, Vector3.one, material, 0);
                go.transform.SetPositionAndRotation(p.Position, p.Rotation);
                go.transform.localScale = p.Scale;
                MeshRenderer renderer = Glow(go);
                Glows.Add(renderer);
                if (p.Wall >= 0)
                {
                    wallParts.Add(new WallGlowPart { Line = p.Wall, Family = family, Own = renderer });
                }
            }
        }

        /// <summary>
        /// M7 walls pass: finds the cap of every wall line that carries fixtures (a cap is registered with its line's fade rule,
        /// never kept standing when lowered) and follows the fader from now on. Without a fader the glows always show.
        /// </summary>
        private void Follow(Transform levelRoot, WallFader wallFader)
        {
            if (wallFader == null || wallLines.Count == 0)
            {
                return;
            }
            foreach (MeshRenderer r in levelRoot.GetComponentsInChildren<MeshRenderer>(true))
            {
                if (r.name != LevelBuilder.CapName || !wallFader.PlaneOf(r, out Vector3 point, out Vector3 normal))
                {
                    continue;
                }
                // A line along x faces z (and its plane point is on the line).
                bool alongX = Mathf.Abs(normal.z) > 0.5f;
                float line = alongX ? point.z : point.x;
                foreach (WallGlowLine w in wallLines)
                {
                    if (w.Cap == null && w.AlongX == alongX && Mathf.Abs(w.Line - line) < 1e-3f)
                    {
                        w.Cap = r;
                    }
                }
            }
            fader = wallFader;
            fader.Stepped += FollowWalls;
            MergeHousings();
        }

        /// <summary>
        /// The fixture housings of each wall line merged into its cap's mesh as flat vertices (<see cref="WallArray.Flat"/>):
        /// the cap draws them with the wall material, so they cost no material and no draw call, and they go wherever the cap
        /// goes (sinking, see-through, back). Skipped for a cap that is not drawn with the wall material (textures off).
        /// The combined mesh is cached by its parts, so a rebuilt level reuses it.
        /// </summary>
        private void MergeHousings()
        {
            foreach (WallGlowLine w in wallLines)
            {
                if (w.Cap == null || w.Housing.Count == 0 || !WallArray.IsWallMaterial(w.Cap.sharedMaterial))
                {
                    continue;
                }
                MeshFilter filter = w.Cap.GetComponent<MeshFilter>();
                if (filter == null || filter.sharedMesh == null)
                {
                    continue;
                }
                Matrix4x4 toCap = w.Cap.transform.worldToLocalMatrix;
                var parts = new List<PrimitiveKit.CombinePart>(w.Housing.Count + 1)
                {
                    new PrimitiveKit.CombinePart { Mesh = filter.sharedMesh, Matrix = Matrix4x4.identity },
                };
                foreach (PrimitiveKit.CombinePart p in w.Housing)
                {
                    parts.Add(new PrimitiveKit.CombinePart
                    {
                        Mesh = WallArray.Flat(p.Mesh, FurnitureKit.FrameColor, Tuning.ModelSmoothness, 0f),
                        Matrix = toCap * p.Matrix,
                    });
                }
                filter.sharedMesh = PrimitiveKit.CombinedMesh(parts);
                if (w.Cap is MeshRenderer r && !Housings.Contains(r))
                {
                    Housings.Add(r);
                }
            }
        }

        // Housing sizes (metres, presentation only). A backplate this thick stands this far off the wall face (never on it),
        // its corners softened by Chamfer; the rims and end caps stand Lip proud of the glow on every visible side.
        private const float PlateThickness = 0.012f;
        private const float PlateGap = 0.002f;
        private const float Lip = 0.006f;

        /// <summary>
        /// A wall fixture's housing on wall line <paramref name="line"/>, in the fixture's frame (<paramref name="face"/> on
        /// the wall face, <paramref name="rotation"/>: x along the wall, y up, z into the room) around its glow box
        /// (<paramref name="glow"/>, centred <paramref name="glowOff"/> off the face): a backplate behind it, and end caps (a
        /// tube, a strip) or top and bottom rims (a sconce; a reading light gets a top rim).
        /// </summary>
        private void AddHousing(int line, Style style, Vector3 face, Quaternion rotation, Vector3 glow, float glowOff)
        {
            Matrix4x4 fixture = Matrix4x4.TRS(face, rotation, Vector3.one);
            List<PrimitiveKit.CombinePart> housing = wallLines[line].Housing;
            void Box(Vector3 centre, Vector3 size, float chamfer)
            {
                housing.Add(new PrimitiveKit.CombinePart { Mesh = HousingMesh(size, chamfer), Matrix = fixture * Matrix4x4.Translate(centre) });
            }
            float front = glowOff + glow.z * 0.5f + Lip;
            float plateZ = PlateGap + PlateThickness * 0.5f;
            // A rim or an end cap reaches from the plate's back to just in front of the glow.
            float capDepth = front - PlateGap;
            float capZ = PlateGap + capDepth * 0.5f;
            switch (style)
            {
                case Style.Tube:
                case Style.Strip:
                {
                    bool tube = style == Style.Tube;
                    float plateH = glow.y + (tube ? 0.026f : 0.02f);
                    Box(new Vector3(0f, 0f, plateZ), new Vector3(glow.x + 0.04f, plateH, PlateThickness), plateH * 0.25f);
                    // The end caps overlap the glow's ends, so the light seems to run into them.
                    float capW = tube ? 0.026f : 0.02f;
                    float capX = glow.x * 0.5f + capW * 0.5f - 0.008f;
                    var cap = new Vector3(capW, glow.y + 2f * Lip + 0.004f, capDepth);
                    Box(new Vector3(-capX, 0f, capZ), cap, capW * 0.3f);
                    Box(new Vector3(capX, 0f, capZ), cap, capW * 0.3f);
                    break;
                }
                case Style.Reading:
                {
                    Box(new Vector3(0f, 0f, plateZ), new Vector3(glow.x * 0.75f, glow.y + 0.07f, PlateThickness), 0.025f);
                    var rim = new Vector3(glow.x + 2f * Lip, 0.016f, capDepth);
                    Box(new Vector3(0f, glow.y * 0.5f, capZ), rim, 0.006f);
                    break;
                }
                default:
                {
                    Box(new Vector3(0f, 0f, plateZ), new Vector3(glow.x + 0.04f, glow.y + 0.06f, PlateThickness), 0.03f);
                    var rim = new Vector3(glow.x + 2f * Lip, 0.02f, capDepth);
                    Box(new Vector3(0f, glow.y * 0.5f, capZ), rim, 0.008f);
                    Box(new Vector3(0f, -glow.y * 0.5f, capZ), rim, 0.008f);
                    break;
                }
            }
        }

        private static readonly Dictionary<string, Mesh> HousingCache = new Dictionary<string, Mesh>();

        /// <summary>
        /// A housing box of <paramref name="size"/> centred on the origin, its four edges along z (out of the wall) cut at 45
        /// degrees by <paramref name="chamfer"/> so its corners read rounded from the room, without the face toward the wall
        /// (never seen): an octagon in front and eight sides, 22 triangles, flat normals, UV0 in metres. Cached by size.
        /// </summary>
        private static Mesh HousingMesh(Vector3 size, float chamfer)
        {
            System.Globalization.CultureInfo inv = System.Globalization.CultureInfo.InvariantCulture;
            string key = string.Format(inv, "{0:0.####}x{1:0.####}x{2:0.####}c{3:0.####}", size.x, size.y, size.z, chamfer);
            if (HousingCache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            float hx = size.x * 0.5f;
            float hy = size.y * 0.5f;
            float hz = size.z * 0.5f;
            float c = Mathf.Clamp(chamfer, 0.0005f, Mathf.Min(hx, hy) * 0.9f);
            // The outline, counter clockwise seen from the room (+z).
            var outline = new[]
            {
                new Vector2(-hx + c, -hy), new Vector2(hx - c, -hy), new Vector2(hx, -hy + c), new Vector2(hx, hy - c),
                new Vector2(hx - c, hy), new Vector2(-hx + c, hy), new Vector2(-hx, hy - c), new Vector2(-hx, -hy + c),
            };
            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var uvs = new List<Vector2>();
            var triangles = new List<int>();
            // One triangle facing its normal (Unity's front faces: Cross(b - a, c - a) along the normal, as Handles.PullMesh).
            void Triangle(int a, int b, int d, Vector3 normal)
            {
                bool facing = Vector3.Dot(Vector3.Cross(vertices[b] - vertices[a], vertices[d] - vertices[a]), normal) > 0f;
                triangles.AddRange(facing ? new[] { a, b, d } : new[] { a, d, b });
            }
            int start = vertices.Count;
            foreach (Vector2 p in outline)
            {
                vertices.Add(new Vector3(p.x, p.y, hz));
                normals.Add(Vector3.forward);
                uvs.Add(p);
            }
            for (int i = 1; i + 1 < outline.Length; i++)
            {
                Triangle(start, start + i, start + i + 1, Vector3.forward);
            }
            for (int i = 0; i < outline.Length; i++)
            {
                Vector2 a = outline[i];
                Vector2 b = outline[(i + 1) % outline.Length];
                Vector2 edge = b - a;
                var normal = new Vector3(edge.y, -edge.x, 0f).normalized;
                int s = vertices.Count;
                vertices.AddRange(new[] { new Vector3(a.x, a.y, -hz), new Vector3(a.x, a.y, hz), new Vector3(b.x, b.y, hz), new Vector3(b.x, b.y, -hz) });
                normals.AddRange(new[] { normal, normal, normal, normal });
                float length = edge.magnitude;
                uvs.AddRange(new[] { new Vector2(0f, 0f), new Vector2(0f, size.z), new Vector2(length, size.z), new Vector2(length, 0f) });
                Triangle(s, s + 1, s + 2, normal);
                Triangle(s, s + 2, s + 3, normal);
            }
            var mesh = new Mesh { name = "FixtureHousing" };
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            mesh.hideFlags = HideFlags.DontUnloadUnusedAsset;
            HousingCache[key] = mesh;
            return mesh;
        }

        /// <summary>
        /// M7 walls pass, called by the wall fader after each update: a wall fixture's glow shows only while its wall line fully
        /// stands (the level of its cap), so it goes at once with a wall that sinks or fades and comes back with it, as the
        /// line's own parts are drawn again only once whole. A hidden glow's vertices collapse to one point (no allocation).
        /// </summary>
        private void FollowWalls()
        {
            if (fader == null)
            {
                return;
            }
            bool changed = false;
            for (int i = 0; i < wallLines.Count; i++)
            {
                WallGlowLine w = wallLines[i];
                float level = w.Cap != null ? fader.LevelOf(w.Cap) : -1f;
                bool shown = level < 0f || level >= 1f;
                if (shown != w.Shown)
                {
                    w.Shown = shown;
                    changed = true;
                }
            }
            if (!changed)
            {
                return;
            }
            foreach (WallGlowPart p in wallParts)
            {
                bool shown = wallLines[p.Line].Shown;
                if (p.Own != null)
                {
                    p.Own.forceRenderingOff = !shown;
                    continue;
                }
                GlowMesh g = glowMeshes[p.Family];
                for (int v = p.Start; v < p.Start + p.Count; v++)
                {
                    g.Shown[v] = shown ? g.Rest[v] : p.Collapsed;
                }
                g.Dirty = true;
            }
            foreach (GlowMesh g in glowMeshes)
            {
                if (g != null && g.Dirty)
                {
                    g.Dirty = false;
                    g.Mesh.SetVertices(g.Shown);
                }
            }
        }

        private void OnDestroy()
        {
            if (fader != null)
            {
                fader.Stepped -= FollowWalls;
            }
            foreach (GlowMesh g in glowMeshes)
            {
                if (g != null && g.Mesh != null)
                {
                    if (Application.isPlaying)
                    {
                        Destroy(g.Mesh);
                    }
                    else
                    {
                        DestroyImmediate(g.Mesh);
                    }
                }
            }
        }

        private static MeshRenderer Glow(GameObject go)
        {
            MeshRenderer r = go.GetComponent<MeshRenderer>();
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            r.lightProbeUsage = LightProbeUsage.Off;
            r.reflectionProbeUsage = ReflectionProbeUsage.Off;
            return r;
        }

        /// <summary>A glow part; <paramref name="wall"/> is the wall line a wall fixture hangs on (<see cref="WallLineOf"/>), -1 for a lamp.</summary>
        private void AddGlow(bool cool, Mesh mesh, Vector3 position, Quaternion rotation, Vector3 scale, int wall = -1)
        {
            (cool ? coolParts : warmParts).Add(new GlowPart { Mesh = mesh, Position = position, Rotation = rotation, Scale = scale, Wall = wall });
        }

        /// <summary>The index of the wall line along x (or z) at <paramref name="line"/> in <see cref="wallLines"/>, added when new.</summary>
        private int WallLineOf(bool alongX, float line)
        {
            for (int i = 0; i < wallLines.Count; i++)
            {
                if (wallLines[i].AlongX == alongX && Mathf.Abs(wallLines[i].Line - line) < 1e-3f)
                {
                    return i;
                }
            }
            wallLines.Add(new WallGlowLine { AlongX = alongX, Line = line });
            return wallLines.Count - 1;
        }

        private Light AddLight(RoomDef room, int rank, Vector3 position, Vector3 direction, bool spot, float spotAngle, Mood mood,
            float intensity, float range)
        {
            var go = new GameObject($"RoomLight {room.Id ?? "room"} {rank + 1}") { layer = 0 };
            go.transform.SetParent(transform, false);
            go.transform.position = position;
            // A spot aimed straight down needs another up vector than the world's.
            go.transform.rotation = spot ? Quaternion.LookRotation(direction, Mathf.Abs(direction.y) > 0.99f ? Vector3.forward : Vector3.up)
                : Quaternion.identity;
            Light l = go.AddComponent<Light>();
            l.type = spot ? LightType.Spot : LightType.Point;
            l.shadows = LightShadows.None;
            l.color = mood.Colour;
            l.intensity = intensity;
            l.range = range;
            l.bounceIntensity = 0f;
            l.renderMode = LightRenderMode.Auto;
            if (spot)
            {
                l.spotAngle = spotAngle;
                l.innerSpotAngle = spotAngle * 0.5f;
            }
            return l;
        }

        private void Add(RoomDef room, string type, Style style, int rank, Light light, bool cool)
        {
            fixtures.Add(new Fixture { Room = room, Type = type, Style = style, Rank = rank, Light = light, Cool = cool, Intensity = light.intensity });
        }

        /// <summary>The placement of one level's fixtures (build time only: it may allocate).</summary>
        private sealed class Placer
        {
            private static readonly string[] Sides = { "+z", "-z", "+x", "-x" };

            private readonly LevelDef def;
            private readonly RoomLights owner;
            private readonly List<Vector3> taken = new List<Vector3>();
            // The rank of the room's next fixture: its first is 0 whatever placement failed before it.
            private int next;

            public Placer(LevelDef def, RoomLights owner)
            {
                this.def = def;
                this.owner = owner;
            }

            /// <summary>A point on a room's wall face: the wall's side, its coordinate along the wall and its inward normal.</summary>
            private struct WallSpot
            {
                public string Side;
                public float Along;
                public Vector3 Inward;
                public float Score;
            }

            public void Room(int index, RoomDef room)
            {
                string type = room.Type;
                if (room.LightWall == RoomDef.LightWallNone || !IsLit(type))
                {
                    return;
                }
                taken.Clear();
                next = 0;
                Mood mood = MoodOf(type);
                float area = room.SizeX * room.SizeZ;
                float longest = Mathf.Max(room.SizeX, room.SizeZ);
                switch (type)
                {
                    case RoomTypes.Bathroom:
                        if (!OverProp(index, room, type, mood, Style.Tube, PropKinds.Washbasin))
                        {
                            Wall(index, room, type, mood, Style.Tube);
                        }
                        break;
                    case RoomTypes.Kitchen:
                        if (!OverProp(index, room, type, mood, Style.Strip, null))
                        {
                            Wall(index, room, type, mood, Style.Strip);
                        }
                        if (area >= SecondArea)
                        {
                            Wall(index, room, type, mood, Style.Strip);
                        }
                        break;
                    case RoomTypes.Dining:
                        if (!OnTable(index, room, type, mood, Style.TableLamp))
                        {
                            Wall(index, room, type, MoodOf(RoomTypes.Living), Style.Sconce);
                        }
                        if (area >= SecondArea)
                        {
                            Wall(index, room, type, MoodOf(RoomTypes.Living), Style.Sconce);
                        }
                        break;
                    case RoomTypes.Study:
                        if (!OnTable(index, room, type, mood, Style.DeskLamp))
                        {
                            Wall(index, room, type, mood, Style.Sconce);
                        }
                        if (area >= SecondArea)
                        {
                            Wall(index, room, type, mood, Style.Sconce);
                        }
                        break;
                    case RoomTypes.Bedroom:
                        if (!Bedside(index, room, type, mood) && !OverProp(index, room, type, mood, Style.Reading, null))
                        {
                            Wall(index, room, type, mood, Style.Reading);
                        }
                        break;
                    default:
                        // Living, hall, corridor: wall sconces, a pair along the longest free wall in a large room.
                        bool two = type == RoomTypes.Corridor ? longest >= SecondLength : area >= SecondArea;
                        if (!two || !Pair(index, room, type, mood))
                        {
                            Wall(index, room, type, mood, Style.Sconce);
                            if (two)
                            {
                                Wall(index, room, type, mood, Style.Sconce);
                            }
                        }
                        break;
                }
            }

            private static bool IsLit(string type)
            {
                return type != RoomTypes.Other && RoomTypes.IsKnown(type);
            }

            // ----- Wall geometry -----

            private static void Frame(RoomDef r, string side, out bool alongX, out float line, out float from, out float to, out Vector3 inward)
            {
                switch (side)
                {
                    case "+z":
                        alongX = true; line = r.MaxZ; from = r.MinX; to = r.MaxX; inward = Vector3.back;
                        return;
                    case "-z":
                        alongX = true; line = r.MinZ; from = r.MinX; to = r.MaxX; inward = Vector3.forward;
                        return;
                    case "+x":
                        alongX = false; line = r.MaxX; from = r.MinZ; to = r.MaxZ; inward = Vector3.left;
                        return;
                    default:
                        alongX = false; line = r.MinX; from = r.MinZ; to = r.MaxZ; inward = Vector3.right;
                        return;
                }
            }

            /// <summary>The world point <paramref name="inset"/> off a wall face at <paramref name="along"/>, at height <paramref name="y"/>.</summary>
            private static Vector3 OnWall(RoomDef r, string side, float along, float inset, float y)
            {
                Frame(r, side, out bool alongX, out float line, out _, out _, out Vector3 inward);
                return alongX ? new Vector3(along, y, line + inward.z * inset) : new Vector3(line + inward.x * inset, y, along);
            }

            private static void Extents(PropDef p, out float ex, out float ez)
            {
                float rad = p.Yaw * Mathf.Deg2Rad;
                float c = Mathf.Abs(Mathf.Cos(rad));
                float s = Mathf.Abs(Mathf.Sin(rad));
                ex = 0.5f * (c * p.SizeX + s * p.SizeZ);
                ez = 0.5f * (s * p.SizeX + c * p.SizeZ);
            }

            /// <summary>How far a prop stands off a wall of its room, and the span it covers along that wall.</summary>
            private static float GapTo(RoomDef r, string side, PropDef p, out float a0, out float a1)
            {
                Extents(p, out float ex, out float ez);
                switch (side)
                {
                    case "+z":
                        a0 = p.X - ex; a1 = p.X + ex;
                        return r.MaxZ - (p.Z + ez);
                    case "-z":
                        a0 = p.X - ex; a1 = p.X + ex;
                        return p.Z - ez - r.MinZ;
                    case "+x":
                        a0 = p.Z - ez; a1 = p.Z + ez;
                        return r.MaxX - (p.X + ex);
                    default:
                        a0 = p.Z - ez; a1 = p.Z + ez;
                        return p.X - ex - r.MinX;
                }
            }

            private float FloorAt(Vector3 p)
            {
                return def.FloorHeightAt(p.x, p.z);
            }

            /// <summary>The spans of a wall a fixture at <paramref name="y"/> must keep clear of: doorways, windows, tall props.</summary>
            private List<Vector2> Blocked(int index, RoomDef r, string side, float y, PropDef under = null)
            {
                var spans = new List<Vector2>();
                void Openings(List<OpeningDef> openings, float margin)
                {
                    if (openings == null)
                    {
                        return;
                    }
                    foreach (OpeningDef o in openings)
                    {
                        List<RoomSide> on = def.SidesOf(o, out float along);
                        foreach (RoomSide s in on)
                        {
                            if (s.Room == index && s.Side == side)
                            {
                                spans.Add(new Vector2(along - o.Width * 0.5f - margin, along + o.Width * 0.5f + margin));
                            }
                        }
                    }
                }
                Openings(def.Doors, DoorMargin);
                Openings(def.Windows, WindowMargin);
                if (def.Props != null)
                {
                    foreach (PropDef p in def.Props)
                    {
                        // The prop a fixture belongs to (the washbasin under its tube) never blocks it.
                        if (p == null || p == under || !r.Contains(p.Position))
                        {
                            continue;
                        }
                        float gap = GapTo(r, side, p, out float a0, out float a1);
                        if (gap <= PropWallGap && FloorAt(p.Position) + p.SizeY >= y - PropHeadroom)
                        {
                            spans.Add(new Vector2(a0 - PropMargin, a1 + PropMargin));
                        }
                    }
                }
                return spans;
            }

            /// <summary>The free point nearest <paramref name="want"/> in [lo, hi] for a fixture <paramref name="half"/> wide each way.</summary>
            private static bool Free(float lo, float hi, float want, float half, List<Vector2> blocked, out float at)
            {
                at = 0f;
                lo += half;
                hi -= half;
                if (lo > hi)
                {
                    return false;
                }
                want = Mathf.Clamp(want, lo, hi);
                const float step = 0.05f;
                int steps = Mathf.CeilToInt((hi - lo) / step) + 1;
                for (int k = 0; k <= 2 * steps; k++)
                {
                    float c = want + step * ((k + 1) / 2) * (k % 2 == 0 ? 1f : -1f);
                    if (c < lo - 1e-4f || c > hi + 1e-4f)
                    {
                        continue;
                    }
                    bool clear = true;
                    foreach (Vector2 b in blocked)
                    {
                        if (c + half > b.x && c - half < b.y)
                        {
                            clear = false;
                            break;
                        }
                    }
                    if (clear)
                    {
                        at = c;
                        return true;
                    }
                }
                return false;
            }

            private bool FarFromTaken(Vector3 p)
            {
                foreach (Vector3 t in taken)
                {
                    if (new Vector2(p.x - t.x, p.z - t.z).magnitude < Spacing)
                    {
                        return false;
                    }
                }
                return true;
            }

            private IEnumerable<string> WallsOf(RoomDef r)
            {
                if (!string.IsNullOrEmpty(r.LightWall) && r.LightWall != RoomDef.LightWallNone)
                {
                    yield return r.LightWall;
                    yield break;
                }
                foreach (string s in Sides)
                {
                    yield return s;
                }
            }

            /// <summary>
            /// The best free wall spot of a room for a fixture <paramref name="half"/> wide at <paramref name="y"/>: the longest
            /// wall first, as near its middle as it is free, away from the room's other fixtures.
            /// </summary>
            private bool BestSpot(int index, RoomDef r, float y, float half, out WallSpot best)
            {
                best = default;
                bool found = false;
                foreach (string side in WallsOf(r))
                {
                    Frame(r, side, out _, out _, out float from, out float to, out Vector3 inward);
                    List<Vector2> blocked = Blocked(index, r, side, y);
                    float length = to - from;
                    foreach (float f in new[] { 0.5f, 0.3f, 0.7f })
                    {
                        if (!Free(from + CornerMargin, to - CornerMargin, from + f * length, half, blocked, out float at))
                        {
                            continue;
                        }
                        if (!FarFromTaken(OnWall(r, side, at, 0f, 0f)))
                        {
                            continue;
                        }
                        float score = length - 0.8f * Mathf.Abs(at - (from + to) * 0.5f);
                        if (!found || score > best.Score + 1e-4f)
                        {
                            best = new WallSpot { Side = side, Along = at, Inward = inward, Score = score };
                            found = true;
                        }
                    }
                }
                return found;
            }

            /// <summary>A pair of sconces at about a quarter and three quarters of the longest wall that has room for both.</summary>
            private bool Pair(int index, RoomDef r, string type, Mood mood)
            {
                var sides = new List<string>(WallsOf(r));
                sides.Sort((s1, s2) => WallLength(r, s2).CompareTo(WallLength(r, s1)));
                float y = Height(r, SconceHeight);
                float half = HalfWidth(Style.Sconce, 0f);
                foreach (string side in sides)
                {
                    Frame(r, side, out _, out _, out float from, out float to, out Vector3 inward);
                    List<Vector2> blocked = Blocked(index, r, side, y);
                    float length = to - from;
                    if (!Free(from + CornerMargin, to - CornerMargin, from + 0.27f * length, half, blocked, out float a)
                        || !Free(from + CornerMargin, to - CornerMargin, from + 0.73f * length, half, blocked, out float b)
                        || Mathf.Abs(b - a) < Spacing)
                    {
                        continue;
                    }
                    PlaceWall(r, type, mood, Style.Sconce, new WallSpot { Side = side, Along = a, Inward = inward }, SconceHeight, 0f);
                    PlaceWall(r, type, mood, Style.Sconce, new WallSpot { Side = side, Along = b, Inward = inward }, SconceHeight, 0f);
                    return true;
                }
                return false;
            }

            private static float WallLength(RoomDef r, string side)
            {
                return side == "+z" || side == "-z" ? r.SizeX : r.SizeZ;
            }

            private static float Height(RoomDef r, float aboveFloor)
            {
                return Mathf.Min(aboveFloor, r.WallHeight - 0.3f);
            }

            private static float HalfWidth(Style style, float length)
            {
                switch (style)
                {
                    case Style.Tube: return 0.31f;
                    case Style.Strip: return Mathf.Max(0.3f, length * 0.5f);
                    case Style.Reading: return 0.07f;
                    default: return 0.09f;
                }
            }

            /// <summary>A wall fixture of <paramref name="style"/> at the best free spot of the room.</summary>
            private bool Wall(int index, RoomDef r, string type, Mood mood, Style style)
            {
                float above = style == Style.Tube ? TubeHeight : style == Style.Reading ? BedroomWallHeight
                    : style == Style.Strip ? TubeHeight : SconceHeight;
                float length = style == Style.Strip ? 0.9f : 0f;
                float y = Height(r, above);
                if (!BestSpot(index, r, y, HalfWidth(style, length), out WallSpot spot))
                {
                    return false;
                }
                PlaceWall(r, type, mood, style, spot, above, length);
                return true;
            }

            /// <summary>
            /// A wall fixture over the prop it belongs to, against a wall: the washbasin (bathroom), the longest counter run
            /// (kitchen: <paramref name="kind"/> null), the bed head (bedroom reading light, <see cref="Style.Reading"/>).
            /// </summary>
            private bool OverProp(int index, RoomDef r, string type, Mood mood, Style style, string kind)
            {
                PropDef best = null;
                string bestSide = null;
                float bestA0 = 0f, bestA1 = 0f;
                foreach (PropDef p in def.Props)
                {
                    if (p == null || !r.Contains(p.Position) || !Matches(p, style, kind))
                    {
                        continue;
                    }
                    foreach (string side in WallsOf(r))
                    {
                        float gap = GapTo(r, side, p, out float a0, out float a1);
                        // The longest counter run; for a bed, its head: the shorter of its sides against a wall.
                        bool better = best == null || (style == Style.Reading ? a1 - a0 < bestA1 - bestA0 - 1e-4f : a1 - a0 > bestA1 - bestA0 + 1e-4f);
                        if (gap > AgainstWall || !better)
                        {
                            continue;
                        }
                        best = p;
                        bestSide = side;
                        bestA0 = a0;
                        bestA1 = a1;
                    }
                }
                if (best == null)
                {
                    return false;
                }
                Frame(r, bestSide, out _, out _, out float from, out float to, out Vector3 inward);
                float floor = FloorAt(best.Position);
                float above;
                float length = 0f;
                float lo = Mathf.Max(from + CornerMargin, bestA0);
                float hi = Mathf.Min(to - CornerMargin, bestA1);
                float want = (bestA0 + bestA1) * 0.5f;
                switch (style)
                {
                    case Style.Strip:
                        // Over the worktop (a kitchen sink's height includes its 0.18 m tap).
                        above = (best.Kind == PropKinds.KitchenSink ? best.SizeY - 0.18f : best.SizeY) + StripOverCounter;
                        length = Mathf.Clamp(bestA1 - bestA0 - 0.3f, 0.4f, 1.2f);
                        break;
                    case Style.Tube:
                        // Over the basin's mirror (FurnitureKit draws one when the washbasin is 1.3 m tall or more), else at
                        // mirror height over the basin; the tube may run a little past a narrow basin.
                        above = best.SizeY >= 1.3f ? best.SizeY + 0.08f : Mathf.Max(TubeOverBasin, best.SizeY + 0.9f);
                        lo = Mathf.Max(from + CornerMargin, bestA0 - 0.25f);
                        hi = Mathf.Min(to - CornerMargin, bestA1 + 0.25f);
                        break;
                    default:
                        // The reading light hangs beside the bed head, on the side that is free.
                        above = ReadingHeight;
                        lo = from + CornerMargin;
                        hi = to - CornerMargin;
                        want = bestA1 + 0.3f;
                        break;
                }
                float y = Height(r, floor + above);
                List<Vector2> blocked = Blocked(index, r, bestSide, y, best);
                if (style == Style.Reading)
                {
                    // Beside the bed, never over it: the bed's own span is taken.
                    blocked.Add(new Vector2(bestA0, bestA1));
                }
                float half = HalfWidth(style, length);
                if (!Free(lo, hi, want, half, blocked, out float at) && !(style == Style.Reading && Free(lo, hi, bestA0 - 0.3f, half, blocked, out at)))
                {
                    return false;
                }
                if (style == Style.Reading && Mathf.Min(Mathf.Abs(at - bestA1), Mathf.Abs(at - bestA0)) > 0.6f)
                {
                    // Too far from the bed to read by: a plain bedroom wall light instead.
                    return false;
                }
                PlaceWall(r, type, mood, style, new WallSpot { Side = bestSide, Along = at, Inward = inward }, y - FloorAt(OnWall(r, bestSide, at, 0.4f, 0f)), length);
                return true;
            }

            private static bool Matches(PropDef p, Style style, string kind)
            {
                switch (style)
                {
                    case Style.Strip:
                        return (p.Kind == PropKinds.Counter || p.Kind == PropKinds.KitchenSink || p.Kind == PropKinds.Stove) && p.SizeY <= 1.2f;
                    case Style.Reading:
                        return IsBed(p);
                    default:
                        return p.Kind == kind;
                }
            }

            private static bool IsBed(PropDef p)
            {
                return p.Kind == PropKinds.Bed || (p.Kind == PropKinds.Sofa && p.Name != null && p.Name.StartsWith("Lit", System.StringComparison.OrdinalIgnoreCase));
            }

            /// <summary>Puts a wall fixture's glow at <paramref name="spot"/>, <paramref name="above"/> the floor, and its spot light.</summary>
            private void PlaceWall(RoomDef r, string type, Mood mood, Style style, WallSpot spot, float above, float length)
            {
                float floor = FloorAt(OnWall(r, spot.Side, spot.Along, 0.4f, 0f));
                float y = Height(r, floor + above);
                Vector3 face = OnWall(r, spot.Side, spot.Along, 0f, y);
                Quaternion rotation = Quaternion.LookRotation(spot.Inward, Vector3.up);
                Vector3 glow;
                float glowOff;
                switch (style)
                {
                    case Style.Tube:
                        glow = new Vector3(0.62f, 0.045f, 0.05f);
                        glowOff = 0.04f;
                        break;
                    case Style.Strip:
                        glow = new Vector3(Mathf.Max(0.6f, length), 0.03f, 0.06f);
                        glowOff = 0.045f;
                        break;
                    case Style.Reading:
                        glow = new Vector3(0.13f, 0.13f, 0.11f);
                        glowOff = 0.06f;
                        break;
                    default:
                        glow = new Vector3(0.16f, 0.24f, 0.1f);
                        glowOff = 0.055f;
                        break;
                }
                // M7 walls pass: on its wall line (centred half a wall thickness beyond the room's face), whose fade it follows.
                Frame(r, spot.Side, out bool alongX, out float line, out _, out _, out Vector3 inward);
                float centre = line - (alongX ? inward.z : inward.x) * r.WallThickness * 0.5f;
                int wallLine = owner.WallLineOf(alongX, centre);
                owner.AddGlow(mood.Cool, PrimitiveKit.BoxMesh, face + spot.Inward * glowOff, rotation, glow, wallLine);
                // Its black metal housing, merged into that line's cap (MergeHousings).
                owner.AddHousing(wallLine, style, face, rotation, glow, glowOff);

                // The spot: above the fixture, aimed at the floor half way across the room (at most a sconce's height out),
                // its cone stopping short of the wall behind it. Under a counter strip, it aims at the worktop's front.
                float sourceY = Mathf.Max(y + 0.1f, Mathf.Min(floor + SourceHeight, r.WallHeight - 0.25f));
                Vector3 at = OnWall(r, spot.Side, spot.Along, LightOffWall, sourceY);
                float depth = spot.Side == "+z" || spot.Side == "-z" ? r.SizeZ : r.SizeX;
                float nearTop = Mathf.Max(floor, TopUnder(r, spot, floor, out float front));
                float targetY = style == Style.Strip && nearTop > floor + 0.3f ? nearTop : floor;
                float height = sourceY - targetY;
                float aim = style == Style.Strip && targetY > floor ? 0.45f : Mathf.Clamp(depth * 0.5f - LightOffWall, 0.3f, height);
                // Nothing under the light: the floor, which the axis meets.
                float nearFront = nearTop > floor ? front - LightOffWall : float.MaxValue;
                AimedSpot(r, type, mood, style, at, spot.Inward, aim, height, sourceY - floor, sourceY - nearTop, nearFront, LightOffWall);
                taken.Add(face);
            }

            /// <summary>
            /// A spot at <paramref name="at"/> aimed <paramref name="aim"/> out (along <paramref name="away"/>) and
            /// <paramref name="height"/> down, its cone stopping short of the wall <paramref name="wallGap"/> behind it, its
            /// intensity giving the aimed point the mood's pool, capped for the nearest surface under the light: a flat top
            /// <paramref name="near"/> below it reaching <paramref name="nearFront"/> out along <paramref name="away"/>.
            /// </summary>
            private void AimedSpot(RoomDef r, string type, Mood mood, Style style, Vector3 at, Vector3 away, float aim, float height,
                float floorDrop, float near, float nearFront, float wallGap)
            {
                float tilt = Mathf.Atan2(height, Mathf.Max(0.01f, aim)) * Mathf.Rad2Deg; // below the horizontal
                // The cone's half angle: as wide as it can be without reaching the floor behind the wall (behind the light,
                // wallGap + BehindWall back and floorDrop down, is that far from straight down).
                float behind = Mathf.Atan2(wallGap + BehindWall, Mathf.Max(0.1f, floorDrop)) * Mathf.Rad2Deg;
                float half = Mathf.Clamp(behind + (90f - tilt) - 2f, 18f, 60f);
                Vector3 direction = (away * Mathf.Max(0.01f, aim) + Vector3.down * height).normalized;
                float reach = new Vector2(aim, height).magnitude;
                // The near surface (a counter, a sofa back, a lamp's own table): the axis meets it when it reaches that far out,
                // else its front edge is its point nearest the axis.
                near = Mathf.Max(0.3f, near);
                float hit = near / Mathf.Tan(Mathf.Max(1f, tilt) * Mathf.Deg2Rad);
                float offAxis = 0f;
                float nearDistance = near / Mathf.Sin(Mathf.Max(1f, tilt) * Mathf.Deg2Rad);
                if (nearFront < hit)
                {
                    float edge = Mathf.Atan2(near, Mathf.Max(0.01f, nearFront)) * Mathf.Rad2Deg;
                    offAxis = edge - tilt;
                    nearDistance = new Vector2(Mathf.Max(0f, nearFront), near).magnitude;
                }
                float intensity = IntensityFor(mood.Pool, reach, nearDistance, SpotFactor(offAxis, half));
                float range = Mathf.Clamp(RangeOverReach * reach, 2.4f, 4.5f);
                int rank = next++;
                Light light = owner.AddLight(r, rank, at, direction, true, 2f * half, mood, intensity, range);
                owner.Add(r, type, style, rank, light, mood.Cool);
            }

            /// <summary>
            /// The highest prop top under a wall fixture (within 0.9 m of its wall and 0.6 m along it), or the floor, and how far
            /// from the wall that prop reaches (<paramref name="front"/>).
            /// </summary>
            private float TopUnder(RoomDef r, WallSpot spot, float floor, out float front)
            {
                float top = floor;
                front = 0f;
                foreach (PropDef p in def.Props)
                {
                    if (p == null || !r.Contains(p.Position))
                    {
                        continue;
                    }
                    float gap = GapTo(r, spot.Side, p, out float a0, out float a1);
                    if (gap <= 0.9f && a1 > spot.Along - 0.6f && a0 < spot.Along + 0.6f)
                    {
                        // A washbasin's height includes its mirror and a kitchen sink's its tap: their lit top is the basin or worktop.
                        float height = p.Kind == PropKinds.Washbasin ? Mathf.Min(p.SizeY, 0.9f) : p.Kind == PropKinds.KitchenSink ? p.SizeY - 0.18f : p.SizeY;
                        float propTop = FloorAt(p.Position) + height;
                        if (propTop > top)
                        {
                            top = propTop;
                            Extents(p, out float ex, out float ez);
                            front = gap + 2f * (spot.Side == "+z" || spot.Side == "-z" ? ez : ex);
                        }
                    }
                }
                return top;
            }

            /// <summary>
            /// A small glowing globe lamp standing on a prop top at <paramref name="on"/> (the dining table lamp, the desk lamp,
            /// the bedside lamp), lit by a spot SourceAboveLamp over it aimed straight down, tipped away from a near wall.
            /// </summary>
            private void PlaceLamp(RoomDef r, string type, Mood mood, Style style, Vector3 on, Vector3 globe)
            {
                owner.AddGlow(mood.Cool, PrimitiveKit.SphereMesh(8, 6), on + Vector3.up * (globe.y * 0.5f), Quaternion.identity, globe);
                float floor = FloorAt(on);
                float sourceY = Mathf.Min(on.y + SourceAboveLamp, r.WallHeight - 0.25f);
                // The nearest wall: its distance and the direction away from it.
                float wall = on.x - r.MinX;
                Vector3 away = Vector3.right;
                if (r.MaxX - on.x < wall) { wall = r.MaxX - on.x; away = Vector3.left; }
                if (on.z - r.MinZ < wall) { wall = on.z - r.MinZ; away = Vector3.forward; }
                if (r.MaxZ - on.z < wall) { wall = r.MaxZ - on.z; away = Vector3.back; }
                float height = sourceY - floor;
                float aim = wall < 1.2f ? height * 0.27f : 0.01f; // about 15 degrees off straight down near a wall
                var at = new Vector3(on.x, sourceY, on.z);
                AimedSpot(r, type, mood, style, at, away, aim, height, height, sourceY - on.y, float.MaxValue, wall);
                taken.Add(on);
            }

            /// <summary>A lamp on the room's largest table: the dining table lamp in its middle, the desk lamp on a corner.</summary>
            private bool OnTable(int index, RoomDef r, string type, Mood mood, Style style)
            {
                PropDef table = Largest(r, PropKinds.Table);
                if (table == null)
                {
                    return false;
                }
                float top = FloorAt(table.Position) + table.SizeY;
                if (style == Style.TableLamp)
                {
                    PlaceLamp(r, type, mood, style, new Vector3(table.X, top, table.Z), new Vector3(0.26f, 0.2f, 0.26f));
                    return true;
                }
                PlaceLamp(r, type, mood, style, TableCorner(r, table, top), new Vector3(0.2f, 0.18f, 0.2f));
                return true;
            }

            /// <summary>The bedside lamp on the room's largest nightstand.</summary>
            private bool Bedside(int index, RoomDef r, string type, Mood mood)
            {
                PropDef stand = Largest(r, PropKinds.Nightstand);
                if (stand == null)
                {
                    return false;
                }
                PlaceLamp(r, type, mood, Style.Bedside, new Vector3(stand.X, FloorAt(stand.Position) + stand.SizeY, stand.Z), new Vector3(0.2f, 0.24f, 0.2f));
                return true;
            }
            private PropDef Largest(RoomDef r, string kind)
            {
                PropDef best = null;
                foreach (PropDef p in def.Props)
                {
                    if (p != null && p.Kind == kind && r.Contains(p.Position) && (best == null || p.SizeX * p.SizeZ > best.SizeX * best.SizeZ))
                    {
                        best = p;
                    }
                }
                return best;
            }

            /// <summary>The top corner of a table nearest a wall of its room (its middle for a small table), slightly inset.</summary>
            private static Vector3 TableCorner(RoomDef r, PropDef table, float top)
            {
                if (table.SizeX < 0.5f || table.SizeZ < 0.5f)
                {
                    return new Vector3(table.X, top, table.Z);
                }
                Vector3 best = Vector3.zero;
                float bestGap = float.MaxValue;
                for (int k = 0; k < 4; k++)
                {
                    var local = new Vector3((k & 1) == 0 ? -1f : 1f, 0f, (k & 2) == 0 ? -1f : 1f);
                    local.x *= table.SizeX * 0.5f - 0.17f;
                    local.z *= table.SizeZ * 0.5f - 0.14f;
                    Vector3 p = table.Position + YawMath.Rotate(local, table.Yaw);
                    float gap = Mathf.Min(Mathf.Min(p.x - r.MinX, r.MaxX - p.x), Mathf.Min(p.z - r.MinZ, r.MaxZ - p.z));
                    if (gap < bestGap - 1e-4f)
                    {
                        bestGap = gap;
                        best = p;
                    }
                }
                return new Vector3(best.x, top, best.z);
            }
        }
    }
}
