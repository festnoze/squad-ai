using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;
using UnityEngine;

namespace Meuble.Core
{
    /// <summary>
    /// A level as data (PRD 6.1, docs/CONTRACT_M2.md 4). Positions are in meters on the floor plane.
    /// Yaw follows <see cref="YawMath"/>: 0 faces +z, 180 faces -z.
    ///
    /// Two forms are accepted. M1: a single <see cref="Room"/> centered on the origin, doors and windows
    /// named by wall ("+x", "-z", ...). v2: a list of <see cref="Rooms"/>, rectangles of the interior,
    /// adjacent rooms separated by exactly one wall thickness, and doors given as a point on a wall line.
    /// </summary>
    public sealed class LevelDef
    {
        public string Id;
        public string NameKey;
        public string HintKey;
        public RoomDef Room;
        public List<OpeningDef> Doors = new List<OpeningDef>();
        public List<OpeningDef> Windows = new List<OpeningDef>();
        public SpawnDef Player;
        public ZoneDef Exit;
        public List<PropDef> Props = new List<PropDef>();
        public List<InhabitantDef> Inhabitants = new List<InhabitantDef>();

        // ----- v2 (docs/CONTRACT_M2.md 4) -----
        public List<RoomDef> Rooms = new List<RoomDef>();
        public List<RugDef> Rugs = new List<RugDef>();
        public List<DecoyDef> Decoys = new List<DecoyDef>();
        public List<RouteStepDef> DesignerRoute = new List<RouteStepDef>();

        /// <summary>M4: the level's lesson for the audit's lesson-required check ("careful", "sit", "dark", "glide").</summary>
        public string Lesson;

        // ----- M4 lessons (docs/CONTRACT_M4.md amendment 9.11) -----
        /// <summary>The stool: no schedule at full stool speed.</summary>
        public const string LessonCareful = "careful";
        /// <summary>A "sit": "player" station constrains the schedule.</summary>
        public const string LessonSit = "sit";
        /// <summary>The floor lamp: no schedule without darkness.</summary>
        public const string LessonDark = "dark";
        /// <summary>The office chair: the stop samples bind.</summary>
        public const string LessonGlide = "glide";

        /// <summary>Every accepted <see cref="Lesson"/> value (null is accepted too: no lesson).</summary>
        public static readonly string[] Lessons = { LessonCareful, LessonSit, LessonDark, LessonGlide };

        /// <summary>
        /// M4: resolves <see cref="StationDef.PropSeat"/> for every station whose Sit names a prop of the level (the prop
        /// center, with the station's Facing), and clears it on every other station. LevelJson.Parse calls it; a level
        /// built in code calls it after changing its props or stations.
        /// </summary>
        public void ResolveSeats()
        {
            if (Inhabitants == null)
            {
                return;
            }
            foreach (InhabitantDef h in Inhabitants)
            {
                if (h?.Stations == null)
                {
                    continue;
                }
                foreach (StationDef s in h.Stations)
                {
                    if (s == null)
                    {
                        continue;
                    }
                    PropDef prop = string.IsNullOrEmpty(s.Sit) || s.SitsOnPlayer || Props == null ? null : Props.Find(p => p.Name == s.Sit);
                    s.PropSeat = prop != null ? new FurniturePose(prop.Position, s.Facing) : (FurniturePose?)null;
                }
            }
        }

        /// <summary>M4: the player's body, <see cref="BodyDef.For"/> of the player kind (the chair when none is given).</summary>
        public BodyDef PlayerBody()
        {
            return BodyDef.For(Player?.Kind);
        }

        /// <summary>Every room; an M1 level (single "room") yields that room.</summary>
        public List<RoomDef> AllRooms()
        {
            if (Rooms != null && Rooms.Count > 0)
            {
                return Rooms;
            }
            return Room != null ? new List<RoomDef> { Room } : new List<RoomDef>();
        }

        /// <summary>The room whose interior contains the point (edges included), or null.</summary>
        public RoomDef RoomAt(Vector3 point)
        {
            foreach (RoomDef r in AllRooms())
            {
                if (r.Contains(point))
                {
                    return r;
                }
            }
            return null;
        }

        /// <summary>True on a rug or in a room whose floor is soft (PRD 4.5).</summary>
        public bool IsSilentFloor(Vector3 point)
        {
            if (Rugs != null)
            {
                foreach (RugDef rug in Rugs)
                {
                    if (rug.Contains(point))
                    {
                        return true;
                    }
                }
            }
            RoomDef room = RoomAt(point);
            return room != null && room.IsSoft;
        }

        /// <summary>How many pieces of furniture of each kind the household owns: the player plus the decoys.</summary>
        public Dictionary<string, int> Census()
        {
            var census = new Dictionary<string, int>();
            void Count(string kind)
            {
                string k = string.IsNullOrEmpty(kind) ? DecoyDef.DefaultKind : kind;
                census[k] = census.TryGetValue(k, out int n) ? n + 1 : 1;
            }
            if (Player != null)
            {
                Count(Player.Kind);
            }
            if (Decoys != null)
            {
                foreach (DecoyDef d in Decoys)
                {
                    Count(d.Kind);
                }
            }
            return census;
        }

        /// <summary>The wall thickness shared by every room (the first room's).</summary>
        public float WallThickness()
        {
            List<RoomDef> rooms = AllRooms();
            return rooms.Count > 0 ? rooms[0].WallThickness : 0f;
        }

        /// <summary>The four sides of every room, in room order, then +z, -z, +x, -x.</summary>
        public List<RoomSide> Sides()
        {
            var sides = new List<RoomSide>();
            List<RoomDef> rooms = AllRooms();
            for (int i = 0; i < rooms.Count; i++)
            {
                RoomDef r = rooms[i];
                float t = r.WallThickness;
                sides.Add(new RoomSide(i, "+z", true, r.MaxZ + t * 0.5f, r.MinX, r.MaxX, 1f));
                sides.Add(new RoomSide(i, "-z", true, r.MinZ - t * 0.5f, r.MinX, r.MaxX, -1f));
                sides.Add(new RoomSide(i, "+x", false, r.MaxX + t * 0.5f, r.MinZ, r.MaxZ, 1f));
                sides.Add(new RoomSide(i, "-x", false, r.MinX - t * 0.5f, r.MinZ, r.MaxZ, -1f));
            }
            return sides;
        }

        /// <summary>
        /// The room sides an opening lies on, and the coordinate of its center along the wall. An opening on
        /// an outer wall lies on one side, on a shared wall on two (one per room). M1 form: the named wall of
        /// the single room, <see cref="OpeningDef.Center"/> along it. v2 form: every side whose wall center
        /// line is within half a wall thickness of the point and whose interior span contains it.
        /// </summary>
        public List<RoomSide> SidesOf(OpeningDef opening, out float along)
        {
            var found = new List<RoomSide>();
            along = 0f;
            if (opening == null)
            {
                return found;
            }
            List<RoomSide> sides = Sides();
            if (!opening.IsPointForm)
            {
                if (AllRooms().Count != 1)
                {
                    return found;
                }
                along = opening.Center;
                foreach (RoomSide s in sides)
                {
                    if (s.Side == opening.Wall && along >= s.From - Eps && along <= s.To + Eps)
                    {
                        found.Add(s);
                    }
                }
                return found;
            }
            foreach (RoomSide s in sides)
            {
                float across = s.AlongX ? opening.Z : opening.X;
                float at = s.AlongX ? opening.X : opening.Z;
                float half = AllRooms()[s.Room].WallThickness * 0.5f;
                if (Mathf.Abs(across - s.Line) <= half + Eps && at >= s.From - Eps && at <= s.To + Eps)
                {
                    found.Add(s);
                    along = at;
                }
            }
            return found;
        }

        /// <summary>
        /// The axis aligned box of every room interior, plus the walls between them. The runtime NavMesh is
        /// clipped to it, so no path leaves the house through the exit door (docs/CONTRACT_M2.md 6).
        /// </summary>
        public Rect InteriorBounds()
        {
            List<RoomDef> rooms = AllRooms();
            if (rooms.Count == 0)
            {
                return new Rect();
            }
            float minX = float.MaxValue, minZ = float.MaxValue, maxX = float.MinValue, maxZ = float.MinValue;
            foreach (RoomDef r in rooms)
            {
                minX = Mathf.Min(minX, r.MinX);
                minZ = Mathf.Min(minZ, r.MinZ);
                maxX = Mathf.Max(maxX, r.MaxX);
                maxZ = Mathf.Max(maxZ, r.MaxZ);
            }
            return Rect.MinMaxRect(minX, minZ, maxX, maxZ);
        }

        /// <summary>
        /// The size of a decoy: its own on every axis it gives, else the body size of its kind (M4: "the decoy size
        /// comes from the decoy kind", docs/CONTRACT_M4.md 2). Until M4 the default was the player's size: every
        /// level so far has a chair player and chair decoys, so nothing changes for them.
        /// </summary>
        public Vector3 DecoySize(DecoyDef decoy)
        {
            Vector3 body = BodyDef.For(BodyKinds.Of(decoy.Kind)).Size;
            return new Vector3(
                decoy.SizeX > 0f ? decoy.SizeX : body.x,
                decoy.SizeY > 0f ? decoy.SizeY : body.y,
                decoy.SizeZ > 0f ? decoy.SizeZ : body.z);
        }

        internal const float Eps = 1e-4f;
    }

    /// <summary>One side of one room: the wall band that stands outside the interior on that side.</summary>
    public readonly struct RoomSide
    {
        /// <summary>Index of the room in <see cref="LevelDef.AllRooms"/>.</summary>
        public readonly int Room;
        /// <summary>"+z", "-z", "+x" or "-x".</summary>
        public readonly string Side;
        /// <summary>True for the z walls (+z, -z), which run along x; false for the x walls.</summary>
        public readonly bool AlongX;
        /// <summary>Coordinate of the wall center line: z for a z wall, x for an x wall.</summary>
        public readonly float Line;
        /// <summary>Interior span along the wall (x for a z wall, z for an x wall).</summary>
        public readonly float From;
        public readonly float To;
        /// <summary>+1 when the room interior lies toward lower coordinates (the wall faces -axis), else -1.</summary>
        public readonly float Outward;

        public RoomSide(int room, string side, bool alongX, float line, float from, float to, float outward)
        {
            Room = room;
            Side = side;
            AlongX = alongX;
            Line = line;
            From = from;
            To = to;
            Outward = outward;
        }
    }

    /// <summary>A silent floor area (PRD 4.5): a flat rug, rotated by its yaw.</summary>
    public sealed class RugDef
    {
        /// <summary>M3: catalog model id for the visual (docs/CONTRACT_M3.md 4); null keeps the procedural visual.</summary>
        public string Model;

        public float X;
        public float Z;
        public float SizeX;
        public float SizeZ;
        public float Yaw;
        public string Color;

        [JsonIgnore] public Vector3 Position => new Vector3(X, 0f, Z);

        /// <summary>True when the point (planar) is on the rug, edges included.</summary>
        public bool Contains(Vector3 point)
        {
            Vector3 local = YawMath.Rotate(new Vector3(point.x - X, 0f, point.z - Z), -Yaw);
            return Mathf.Abs(local.x) <= SizeX * 0.5f + LevelDef.Eps && Mathf.Abs(local.z) <= SizeZ * 0.5f + LevelDef.Eps;
        }
    }

    /// <summary>A static furniture of the same kind as the player (PRD 11 M2). Size defaults to the player size.</summary>
    public sealed class DecoyDef
    {
        /// <summary>M3: catalog model id for the visual (docs/CONTRACT_M3.md 4); null keeps the procedural visual.</summary>
        public string Model;

        public const string DefaultKind = "chair";

        public string Kind = DefaultKind;
        public float X;
        public float Z;
        public float Yaw;
        public float SizeX;
        public float SizeY;
        public float SizeZ;
        public string Color;

        [JsonIgnore] public Vector3 Position => new Vector3(X, 0f, Z);
    }

    /// <summary>
    /// One step of a designer route: at game time At, drive straight to (X, Z). The M4 fields are written only when
    /// they differ from their default, so a route rewritten by the audit leaves an M1 to M3 level file unchanged.
    /// </summary>
    public sealed class RouteStepDef
    {
        /// <summary>M4: <see cref="Action"/> that presses E (the floor lamp's light).</summary>
        public const string ActionToggle = "toggle";
        /// <summary>M4: <see cref="Action"/> that presses a move key to right a tipped stool.</summary>
        public const string ActionRightUp = "rightup";

        public float X;
        public float Z;
        public float At;
        // M4 (docs/CONTRACT_M4.md amendment 9.3).
        /// <summary>Holds the careful key (Left Shift) for the leg: half the body's max speed.</summary>
        [JsonProperty(DefaultValueHandling = DefaultValueHandling.Ignore)]
        public bool Careful;
        /// <summary>"toggle" (E), "rightup" (a move key to right a tipped stool), or null.</summary>
        public string Action;
        // CONTRACT_M4 10.7: WaitFor is removed (never read); a route step has x, z, at, careful and action only.
    }

    /// <summary>M4: the authored home of the player's seat for a "sit": "player" station.</summary>
    public sealed class SeatDef
    {
        public float X;
        public float Z;
        public float Yaw;

        [JsonIgnore] public Vector3 Position => new Vector3(X, 0f, Z);
    }

    /// <summary>
    /// M4: the furniture body kinds of <see cref="BodyDef"/> (docs/CONTRACT_M4.md 2). <see cref="BodyDef.For"/> turns an
    /// unknown kind into the chair at run time; the level validator rejects an unknown kind instead, so a typo never
    /// becomes a chair silently.
    /// </summary>
    public static class BodyKinds
    {
        public const string Chair = "chair";
        public const string Stool = "stool";
        public const string Armchair = "armchair";
        public const string FloorLamp = "floor_lamp";
        public const string OfficeChair = "office_chair";

        /// <summary>Every body kind, in the order of the contract table.</summary>
        public static readonly string[] All = { Chair, Stool, Armchair, FloorLamp, OfficeChair };

        /// <summary>The kind a furniture of <paramref name="kind"/> stands for: null or empty is the chair (M1 data).</summary>
        public static string Of(string kind)
        {
            return string.IsNullOrEmpty(kind) ? Chair : kind;
        }

        /// <summary>True for a kind <see cref="BodyDef.For"/> knows (null or empty counts as the chair).</summary>
        public static bool IsKnown(string kind)
        {
            string k = Of(kind);
            return BodyDef.For(k).Kind == k;
        }

        /// <summary>
        /// The catalog model a furniture of <paramref name="kind"/> shows when its data names none: the body's model,
        /// except for the chair, whose M1 to M3 data without a model keeps the procedural chair (docs/CONTRACT_M3.md 4),
        /// and for an unknown kind. Null means the procedural visual.
        /// </summary>
        public static string DefaultModel(string kind)
        {
            string k = Of(kind);
            return k != Chair && IsKnown(k) ? BodyDef.For(k).Model : null;
        }
    }

    /// <summary>levels.json: the play order (docs/CONTRACT_M2.md 4). It is not a level.</summary>
    public static class LevelManifest
    {
        public const string FileName = "levels";

        private sealed class Manifest
        {
            public List<string> Levels = new List<string>();
        }

        public static List<string> Parse(string json)
        {
            Manifest m = JsonConvert.DeserializeObject<Manifest>(json);
            return m?.Levels ?? new List<string>();
        }
    }

    /// <summary>
    /// A rectangle of the interior. X, Z is its center (an M1 single room sits at the origin). Walls stand
    /// outside the interior, <see cref="WallThickness"/> thick.
    /// </summary>
    public sealed class RoomDef
    {
        public const string HardFloor = "hard";
        public const string SoftFloor = "soft";

        public string Id;
        public float X;
        public float Z;
        /// <summary>"hard" (default) or "soft" (silent, PRD 4.5).</summary>
        public string Floor;
        public float SizeX;
        public float SizeZ;
        public float WallHeight;
        public float WallThickness;
        public string FloorColor;
        public string WallColor;

        [JsonIgnore] public float MinX => X - SizeX * 0.5f;
        [JsonIgnore] public float MaxX => X + SizeX * 0.5f;
        [JsonIgnore] public float MinZ => Z - SizeZ * 0.5f;
        [JsonIgnore] public float MaxZ => Z + SizeZ * 0.5f;
        [JsonIgnore] public bool IsSoft => Floor == SoftFloor;

        public bool Contains(Vector3 point)
        {
            return Mathf.Abs(point.x - X) <= SizeX * 0.5f + LevelDef.Eps && Mathf.Abs(point.z - Z) <= SizeZ * 0.5f + LevelDef.Eps;
        }
    }

    /// <summary>
    /// A door (a gap in the wall) or a window (decorative, no gap). M1 form: <see cref="Wall"/> names one of
    /// the four walls of the single room and <see cref="Center"/> places it along that wall. v2 form
    /// (<see cref="Wall"/> null): <see cref="X"/>, <see cref="Z"/> is a point on a wall line.
    /// </summary>
    public sealed class OpeningDef
    {
        private const float TopDefault = Tuning.DoorTopDefault;

        /// <summary>"+x", "-x", "+z" or "-z" (M1 form). Null in the v2 form, which uses X and Z.</summary>
        public string Wall;
        /// <summary>v2 form: a point on a wall line.</summary>
        public float X;
        public float Z;
        /// <summary>M1 form: coordinate of the opening center along the wall (z for the x walls, x for the z walls).</summary>
        public float Center;
        public float Width;
        public float Bottom;
        public float Top = TopDefault;

        [JsonIgnore] public bool IsPointForm => Wall == null;
    }

    /// <summary>The player furniture: kind, floor position, yaw and bounding box size.</summary>
    public sealed class SpawnDef
    {
        /// <summary>M3: catalog model id for the visual (docs/CONTRACT_M3.md 4); null keeps the procedural visual.</summary>
        public string Model;

        public string Kind;
        public float X;
        public float Z;
        public float Yaw;
        public float SizeX;
        public float SizeY;
        public float SizeZ;
        public string Color;

        [JsonIgnore] public Vector3 Position => new Vector3(X, 0f, Z);
        [JsonIgnore] public Vector3 Size => new Vector3(SizeX, SizeY, SizeZ);
    }

    /// <summary>Axis aligned rectangle on the floor (the exit doormat).</summary>
    public sealed class ZoneDef
    {
        /// <summary>M3: catalog model id for the visual (docs/CONTRACT_M3.md 4); null keeps the procedural visual.</summary>
        public string Model;

        public float X;
        public float Z;
        public float SizeX;
        public float SizeZ;
        public string Color;

        public bool Contains(Vector3 point)
        {
            return Mathf.Abs(point.x - X) <= SizeX * 0.5f && Mathf.Abs(point.z - Z) <= SizeZ * 0.5f;
        }
    }

    /// <summary>A static prop, built from primitives by kind, filling the box of the given size.</summary>
    public sealed class PropDef
    {
        /// <summary>M3: catalog model id for the visual (docs/CONTRACT_M3.md 4); null keeps the procedural visual.</summary>
        public string Model;

        public string Name;
        /// <summary>"sofa", "bookshelf", "table", "cabinet", "counter", "plant", "armchair" (M4) or "box".</summary>
        public string Kind;
        public float X;
        public float Z;
        public float Yaw;
        public float SizeX;
        public float SizeY;
        public float SizeZ;
        public bool Occluder = true;
        public string Color;
        public string AccentColor;

        [JsonIgnore] public Vector3 Position => new Vector3(X, 0f, Z);
        [JsonIgnore] public Vector3 Size => new Vector3(SizeX, SizeY, SizeZ);
    }

    public sealed class InhabitantDef
    {
        /// <summary>M3: catalog model id for the visual (docs/CONTRACT_M3.md 4); null keeps the procedural visual.</summary>
        public string Model;

        public string Name;
        public int StartStation;
        public string BodyColor;
        public string HeadColor;
        public List<StationDef> Stations = new List<StationDef>();
    }

    /// <summary>PRD 5.1: a position, a facing yaw, a dwell time and head glances.</summary>
    public sealed class StationDef
    {
        /// <summary>M4: the <see cref="Sit"/> value that sits on the player's seat at <see cref="Seat"/>.</summary>
        public const string SitOnPlayer = "player";

        public float X;
        public float Z;
        public float Facing;
        public float Dwell;
        public List<GlanceDef> Glances = new List<GlanceDef>();
        /// <summary>M4: a prop name, "player", or null (no sitting).</summary>
        public string Sit;
        /// <summary>M4: the seat home when Sit is "player".</summary>
        public SeatDef Seat;

        [JsonIgnore] public Vector3 Position => new Vector3(X, 0f, Z);

        /// <summary>M4: true for a "sit": "player" station.</summary>
        [JsonIgnore] public bool SitsOnPlayer => Sit == SitOnPlayer;

        /// <summary>
        /// M4: the seat home of a station that sits on a prop: the prop center, facing the station's Facing (the seated
        /// facing). Not data: <see cref="LevelDef.ResolveSeats"/> sets it from the props (LevelJson.Parse calls it), so the
        /// sitter sits on the sofa instead of hovering at the seat front. Null for any other station.
        /// </summary>
        [JsonIgnore] public FurniturePose? PropSeat;
    }

    /// <summary>A head glance: time offset into the dwell, head yaw relative to the body, hold duration.</summary>
    public sealed class GlanceDef
    {
        public float Offset;
        public float Yaw;
        public float Hold;
    }

    /// <summary>JSON reading and writing of levels (Newtonsoft, camelCase, unknown members rejected).</summary>
    public static class LevelJson
    {
        private static readonly JsonSerializerSettings Settings = new JsonSerializerSettings
        {
            ContractResolver = new CamelCasePropertyNamesContractResolver(),
            MissingMemberHandling = MissingMemberHandling.Error,
            NullValueHandling = NullValueHandling.Ignore,
            Formatting = Formatting.Indented,
        };

        /// <summary>Reads a level and resolves its derived data (M4: <see cref="LevelDef.ResolveSeats"/>).</summary>
        public static LevelDef Parse(string json)
        {
            LevelDef level = JsonConvert.DeserializeObject<LevelDef>(json, Settings);
            level?.ResolveSeats();
            return level;
        }

        public static string Serialize(LevelDef level)
        {
            return JsonConvert.SerializeObject(level, Settings);
        }

        /// <summary>Parses "#RRGGBB" or "#RRGGBBAA"; anything else returns <paramref name="fallback"/>.</summary>
        public static Color ParseColor(string hex, Color fallback)
        {
            return !string.IsNullOrEmpty(hex) && ColorUtility.TryParseHtmlString(hex, out Color c) ? c : fallback;
        }
    }
}
