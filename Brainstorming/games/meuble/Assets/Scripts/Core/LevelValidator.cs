using System.Collections.Generic;
using UnityEngine;

namespace Meuble.Core
{
    /// <summary>
    /// Static checks of a <see cref="LevelDef"/> (PRD 10.1, docs/CONTRACT_M2.md 4): everything that can be
    /// decided from the data alone. Path clearance and unseen time need physics and live in the editor
    /// level audit (PRD 10.3). Every M1 message is kept as it was.
    ///
    /// M4 (docs/CONTRACT_M4.md 2, 3, 5, amendments 9.3, 9.5, 9.11): the player kind selects its <see cref="BodyDef"/>,
    /// which is the one size source (the player size must equal it); the spawn margin and the door clearance use the
    /// body radius; sit stations, seat homes, the lesson and the route step fields are checked against the body.
    /// </summary>
    public static class LevelValidator
    {
        private const float Eps = 1e-4f;

        /// <summary>
        /// Amendment 9.11: a door must be at least 2 x body radius + this wide (0.45 m armchair radius: 1.0 m doors).
        /// Alias of Tuning.DoorClearanceMargin.
        /// </summary>
        public const float DoorClearanceMargin = Tuning.DoorClearanceMargin;

        // A "sit": "player" station is the seat front: about 0.5 m in front of the seat home along its yaw (between these
        // bounds, this far to the side at most), facing the seat's yaw. Authoring tolerances of the validator, not tuning.
        public const float SeatFrontMin = 0.3f;
        public const float SeatFrontMax = 0.8f;
        public const float SeatFrontAside = 0.2f;
        public const float SeatFacingTolerance = 1f;
        /// <summary>CONTRACT_M4 10.2: a prop seat front faces away from the prop center within this.</summary>
        public const float PropSeatFacingTolerance = 30f;

        /// <summary>The narrowest door a body passes (amendment 9.11).</summary>
        public static float DoorClearance(BodyDef body)
        {
            return 2f * body.Radius + DoorClearanceMargin;
        }

        public static List<string> Validate(LevelDef level)
        {
            var issues = new List<string>();
            if (level == null)
            {
                issues.Add("level is null");
                return issues;
            }
            List<RoomDef> rooms = level.AllRooms();
            if (!CheckRooms(level, rooms, issues))
            {
                return issues;
            }
            BodyDef body = level.PlayerBody();
            CheckOpenings(level, rooms, body, issues);

            if (level.Player == null)
            {
                issues.Add("player spawn is missing");
            }
            else
            {
                CheckBody(level, body, issues);
                Vector2 half = new Vector2(level.Player.SizeX, level.Player.SizeZ) * 0.5f;
                float margin = Mathf.Max(body.Radius, Mathf.Max(half.x, half.y));
                if (!InsideRoom(rooms, level.Player.X, level.Player.Z, margin, margin))
                {
                    issues.Add($"player spawn ({level.Player.X}, {level.Player.Z}) is not inside the room");
                }
                foreach (PropDef prop in level.Props)
                {
                    if (Overlaps(level.Player.X, level.Player.Z, body.Radius, body.Radius, 0f, prop))
                    {
                        issues.Add($"player spawn overlaps prop {prop.Name}");
                    }
                }
                for (int i = 0; i < level.Decoys.Count; i++)
                {
                    if (OverlapsDecoy(level, level.Decoys[i], level.Player.X, level.Player.Z, body.Radius))
                    {
                        issues.Add($"player spawn overlaps decoy {i + 1}");
                    }
                }
            }

            if (level.Exit == null)
            {
                issues.Add("exit zone is missing");
            }
            else
            {
                ZoneDef e = level.Exit;
                if (!InsideRoom(rooms, e.X, e.Z, e.SizeX * 0.5f, e.SizeZ * 0.5f, 0f))
                {
                    issues.Add($"exit zone ({e.X}, {e.Z}) is not inside the room");
                }
                foreach (PropDef prop in level.Props)
                {
                    if (Overlaps(e.X, e.Z, e.SizeX * 0.5f, e.SizeZ * 0.5f, 0f, prop))
                    {
                        issues.Add($"exit zone overlaps prop {prop.Name}");
                    }
                }
                for (int i = 0; i < level.Decoys.Count; i++)
                {
                    Vector3 s = level.DecoySize(level.Decoys[i]);
                    DecoyDef d = level.Decoys[i];
                    if (RectsOverlap(new Vector2(e.X, e.Z), new Vector2(e.SizeX, e.SizeZ) * 0.5f, 0f,
                            new Vector2(d.X, d.Z), new Vector2(s.x, s.z) * 0.5f, d.Yaw))
                    {
                        issues.Add($"exit zone overlaps decoy {i + 1}");
                    }
                }
            }

            foreach (PropDef prop in level.Props)
            {
                if (prop.SizeX <= 0f || prop.SizeY <= 0f || prop.SizeZ <= 0f)
                {
                    issues.Add($"prop {prop.Name} has a non positive size");
                }
                else if (!FootprintInsideRoom(rooms, prop.X, prop.Z, prop.SizeX, prop.SizeZ, prop.Yaw))
                {
                    issues.Add($"prop {prop.Name} is not inside a room");
                }
            }

            CheckDecoys(level, rooms, issues);
            CheckRugs(level, rooms, issues);
            CheckRoute(level, rooms, body, issues);
            CheckLesson(level, body, issues);

            if (level.Inhabitants == null || level.Inhabitants.Count == 0)
            {
                issues.Add("level has no inhabitant");
                return issues;
            }
            foreach (InhabitantDef inhabitant in level.Inhabitants)
            {
                if (inhabitant.Stations == null || inhabitant.Stations.Count == 0)
                {
                    issues.Add($"inhabitant {inhabitant.Name} has no station");
                    continue;
                }
                if (inhabitant.StartStation < 0 || inhabitant.StartStation >= inhabitant.Stations.Count)
                {
                    issues.Add($"inhabitant {inhabitant.Name} start station {inhabitant.StartStation} is out of range");
                }
                for (int i = 0; i < inhabitant.Stations.Count; i++)
                {
                    StationDef s = inhabitant.Stations[i];
                    string label = $"inhabitant {inhabitant.Name} station {i + 1}";
                    if (!InsideRoom(rooms, s.X, s.Z, Tuning.InhabitantRadius, Tuning.InhabitantRadius))
                    {
                        issues.Add($"{label} ({s.X}, {s.Z}) is not inside the room");
                    }
                    foreach (PropDef prop in level.Props)
                    {
                        if (Overlaps(s.X, s.Z, Tuning.InhabitantRadius, Tuning.InhabitantRadius, 0f, prop))
                        {
                            issues.Add($"{label} ({s.X}, {s.Z}) is inside prop {prop.Name}");
                        }
                    }
                    for (int d = 0; d < level.Decoys.Count; d++)
                    {
                        if (OverlapsDecoy(level, level.Decoys[d], s.X, s.Z, Tuning.InhabitantRadius))
                        {
                            issues.Add($"{label} ({s.X}, {s.Z}) is inside decoy {d + 1}");
                        }
                    }
                    if (s.Dwell < 0f)
                    {
                        issues.Add($"{label} has a negative dwell");
                    }
                    float previousOffset = -1f;
                    foreach (GlanceDef g in s.Glances)
                    {
                        if (Mathf.Abs(g.Yaw) > Tuning.HeadYawLimit + 1e-4f)
                        {
                            issues.Add($"{label} glance yaw {g.Yaw} exceeds the head limit of {Tuning.HeadYawLimit}");
                        }
                        if (g.Offset < previousOffset || g.Offset < 0f || g.Hold < 0f)
                        {
                            issues.Add($"{label} glances must have increasing non negative offsets and holds");
                        }
                        previousOffset = g.Offset;
                    }
                    CheckSit(level, rooms, body, s, label, issues);
                }
            }
            return issues;
        }

        // ----- M4: the body, sitting, the lesson -----

        /// <summary>The player kind is a body, its size is the body size (amendment 9.5), a named model is the body's.</summary>
        private static void CheckBody(LevelDef level, BodyDef body, List<string> issues)
        {
            SpawnDef p = level.Player;
            if (!BodyKinds.IsKnown(p.Kind))
            {
                issues.Add($"player kind '{p.Kind}' is not a furniture body ({string.Join(", ", BodyKinds.All)})");
                return;
            }
            if (!SameSize(p.Size, body.Size))
            {
                issues.Add($"player size ({p.SizeX}, {p.SizeY}, {p.SizeZ}) disagrees with the {body.Kind} body size "
                    + $"({body.Size.x}, {body.Size.y}, {body.Size.z}): BodyDef is the one size source");
            }
            if (!string.IsNullOrEmpty(p.Model) && p.Model != body.Model)
            {
                issues.Add($"player model '{p.Model}' is not the model of the {body.Kind} body ({body.Model ?? "none, procedural"})");
            }
        }

        /// <summary>
        /// A sit station (CONTRACT_M4 3): "sit" names a prop of the level, or "player" with a seat home and a seat body.
        /// A seat home is only meaningful on a "player" station; the player body must fit there, inside a room and
        /// clear of the props.
        /// </summary>
        private static void CheckSit(LevelDef level, List<RoomDef> rooms, BodyDef body, StationDef s, string label, List<string> issues)
        {
            if (s.SitsOnPlayer)
            {
                if (s.Seat == null)
                {
                    issues.Add($"{label} sits on the player but has no seat home");
                }
                if (!body.IsSeat)
                {
                    issues.Add($"{label} sits on the player, but the {body.Kind} body is not a seat");
                }
            }
            else if (!string.IsNullOrEmpty(s.Sit))
            {
                PropDef seatProp = level.Props.Find(p => p.Name == s.Sit);
                if (seatProp == null)
                {
                    issues.Add($"{label} sits on '{s.Sit}', which is not a prop of the level");
                }
                else
                {
                    CheckPropSeatFront(s, seatProp, label, issues);
                }
            }
            if (s.Seat == null)
            {
                return;
            }
            if (!s.SitsOnPlayer)
            {
                issues.Add($"{label} has a seat home but does not sit on the player");
                return;
            }
            SeatDef seat = s.Seat;
            // The routine stands at the station (the seat front), its arrival turn is the back turn to Facing, then it
            // sits on the seat home (core's geometry, CONTRACT_M4 3): the station stands about 0.5 m in front of the seat
            // along its yaw, and faces the seat's yaw.
            Vector3 front = YawMath.Forward(seat.Yaw);
            Vector3 offset = new Vector3(s.X - seat.X, 0f, s.Z - seat.Z);
            float ahead = Vector3.Dot(offset, front);
            float aside = Mathf.Abs(Vector3.Dot(offset, YawMath.Forward(seat.Yaw + 90f)));
            if (ahead < SeatFrontMin - Eps || ahead > SeatFrontMax + Eps || aside > SeatFrontAside + Eps)
            {
                issues.Add($"{label} stands {ahead:0.##} m ahead of and {aside:0.##} m beside its seat home: a seat front is {SeatFrontMin} to {SeatFrontMax} m in front of the seat along its yaw");
            }
            if (Mathf.Abs(Mathf.DeltaAngle(s.Facing, seat.Yaw)) > SeatFacingTolerance + Eps)
            {
                issues.Add($"{label} faces {s.Facing} but its seat home faces {seat.Yaw}: the station facing is the seated facing");
            }
            if (!FootprintInsideRoom(rooms, seat.X, seat.Z, body.Size.x, body.Size.z, seat.Yaw))
            {
                issues.Add($"{label} seat home ({seat.X}, {seat.Z}) is not inside a room");
            }
            foreach (PropDef prop in level.Props)
            {
                if (Overlaps(seat.X, seat.Z, body.Size.x * 0.5f, body.Size.z * 0.5f, seat.Yaw, prop))
                {
                    issues.Add($"{label} seat home overlaps prop {prop.Name}");
                }
            }
        }

        /// <summary>
        /// CONTRACT_M4 10.2: a station that sits on a prop is its seat front. It stands <see cref="SeatFrontMin"/> to
        /// <see cref="SeatFrontMax"/> m from the prop center (the seat home), in front of the prop along the station's
        /// facing, and faces away from the prop within <see cref="PropSeatFacingTolerance"/> deg.
        /// </summary>
        private static void CheckPropSeatFront(StationDef s, PropDef prop, string label, List<string> issues)
        {
            Vector3 toProp = new Vector3(prop.X - s.X, 0f, prop.Z - s.Z);
            float distance = toProp.magnitude;
            if (distance < SeatFrontMin - Eps || distance > SeatFrontMax + Eps)
            {
                issues.Add($"{label} stands {distance:0.##} m from the center of {prop.Name}: a seat front is {SeatFrontMin} to {SeatFrontMax} m from it");
            }
            // The station faces away from the seat: the prop center lies behind it.
            float away = distance > Eps ? Vector3.Angle(-YawMath.Forward(s.Facing), toProp) : 180f;
            if (away > PropSeatFacingTolerance + Eps)
            {
                issues.Add($"{label} faces {s.Facing}, {away:0} deg off facing away from {prop.Name}: the station facing is the seated facing, back to the seat");
            }
        }

        /// <summary>The lesson knob (amendment 9.11) is one of four values, and the level has what the lesson is about.</summary>
        private static void CheckLesson(LevelDef level, BodyDef body, List<string> issues)
        {
            string lesson = level.Lesson;
            if (lesson == null)
            {
                return;
            }
            if (System.Array.IndexOf(LevelDef.Lessons, lesson) < 0)
            {
                issues.Add($"lesson '{lesson}' is not one of {string.Join(", ", LevelDef.Lessons)}");
                return;
            }
            if (lesson == LevelDef.LessonCareful && !body.Tips)
            {
                issues.Add($"lesson careful needs a body that tips (the stool), not the {body.Kind}");
            }
            else if (lesson == LevelDef.LessonDark && !body.HasLight)
            {
                issues.Add($"lesson dark needs a body with a light (the floor lamp), not the {body.Kind}");
            }
            else if (lesson == LevelDef.LessonGlide && !body.Glides)
            {
                issues.Add($"lesson glide needs a body that glides (the office chair), not the {body.Kind}");
            }
            else if (lesson == LevelDef.LessonSit
                && (level.Inhabitants == null || !level.Inhabitants.Exists(h => h.Stations != null && h.Stations.Exists(st => st.SitsOnPlayer))))
            {
                issues.Add("lesson sit needs a station that sits on the player");
            }
        }

        private static bool SameSize(Vector3 a, Vector3 b)
        {
            return Mathf.Abs(a.x - b.x) <= Eps && Mathf.Abs(a.y - b.y) <= Eps && Mathf.Abs(a.z - b.z) <= Eps;
        }

        // ----- Rooms -----

        /// <summary>Returns false when the rooms are too broken for any other check to make sense.</summary>
        private static bool CheckRooms(LevelDef level, List<RoomDef> rooms, List<string> issues)
        {
            if (rooms.Count == 0)
            {
                issues.Add("room is missing or has a non positive size");
                return false;
            }
            bool sane = true;
            foreach (RoomDef r in rooms)
            {
                if (r == null || r.SizeX <= 0f || r.SizeZ <= 0f || r.WallHeight <= 0f || r.WallThickness <= 0f)
                {
                    issues.Add("room is missing or has a non positive size" + (r != null && r.Id != null ? $" ({r.Id})" : ""));
                    sane = false;
                }
            }
            if (!sane)
            {
                return false;
            }
            if (level.Room != null && level.Rooms != null && level.Rooms.Count > 0)
            {
                issues.Add("level gives both room and rooms: use rooms only");
            }
            var ids = new HashSet<string>();
            float t = rooms[0].WallThickness;
            for (int i = 0; i < rooms.Count; i++)
            {
                RoomDef r = rooms[i];
                if (r.Floor != null && r.Floor != RoomDef.HardFloor && r.Floor != RoomDef.SoftFloor)
                {
                    issues.Add($"room {Name(r, i)} floor '{r.Floor}' is neither hard nor soft");
                }
                if (Mathf.Abs(r.WallThickness - t) > Eps)
                {
                    issues.Add($"room {Name(r, i)} wall thickness {r.WallThickness} differs from {t}: all rooms share one wall thickness");
                }
                if (r.Id != null && !ids.Add(r.Id))
                {
                    issues.Add($"room id {r.Id} is used twice");
                }
            }
            for (int i = 0; i < rooms.Count; i++)
            {
                for (int j = i + 1; j < rooms.Count; j++)
                {
                    RoomDef a = rooms[i];
                    RoomDef b = rooms[j];
                    // Signed gaps between the interiors: negative means they overlap along that axis.
                    float gx = Mathf.Max(b.MinX - a.MaxX, a.MinX - b.MaxX);
                    float gz = Mathf.Max(b.MinZ - a.MaxZ, a.MinZ - b.MaxZ);
                    if (gx < -Eps && gz < -Eps)
                    {
                        issues.Add($"rooms {Name(a, i)} and {Name(b, j)} overlap");
                        continue;
                    }
                    // Facing each other across a wall line: the walls are either one shared wall (gap = t)
                    // or clear of each other (gap at least 2 t). Anything else makes walls cross.
                    float facing = gz < -Eps ? gx : gx < -Eps ? gz : float.NaN;
                    if (!float.IsNaN(facing) && facing < 2f * t - Eps && Mathf.Abs(facing - t) > Eps)
                    {
                        issues.Add($"rooms {Name(a, i)} and {Name(b, j)} are {facing:0.###} m apart: adjacent rooms are separated by exactly one wall thickness ({t})");
                    }
                }
            }
            return true;
        }

        private static string Name(RoomDef r, int index) => r.Id ?? "#" + (index + 1);

        // ----- Doors and windows -----

        private static void CheckOpenings(LevelDef level, List<RoomDef> rooms, BodyDef body, List<string> issues)
        {
            // Union find over rooms, joined by doors on a shared wall.
            var parent = new int[rooms.Count];
            for (int i = 0; i < parent.Length; i++)
            {
                parent[i] = i;
            }
            int Find(int i) => parent[i] == i ? i : parent[i] = Find(parent[i]);

            float clearance = DoorClearance(body);
            for (int k = 0; k < level.Doors.Count; k++)
            {
                OpeningDef door = level.Doors[k];
                List<RoomSide> sides = CheckOpening(level, rooms, door, $"door {k + 1}", issues);
                if (sides.Count == 2)
                {
                    parent[Find(sides[0].Room)] = Find(sides[1].Room);
                }
                // M4 amendment 9.11: every door lets the level's body through.
                if (door.Width > 0f && door.Width < clearance - Eps)
                {
                    issues.Add($"door {k + 1} is {door.Width} m wide: the {body.Kind} body needs at least {clearance:0.###} m (2 x radius {body.Radius} + {DoorClearanceMargin})");
                }
            }
            for (int k = 0; k < level.Windows.Count; k++)
            {
                CheckOpening(level, rooms, level.Windows[k], $"window {k + 1}", issues);
            }
            int root = Find(0);
            for (int i = 1; i < rooms.Count; i++)
            {
                if (Find(i) != root)
                {
                    issues.Add($"room {Name(rooms[i], i)} is not connected to room {Name(rooms[0], 0)} through doors");
                }
            }
        }

        private static List<RoomSide> CheckOpening(LevelDef level, List<RoomDef> rooms, OpeningDef o, string label, List<string> issues)
        {
            var none = new List<RoomSide>();
            if (o.Width <= 0f || o.Top <= o.Bottom || o.Bottom < 0f)
            {
                issues.Add($"{label} has a non positive width or height");
                return none;
            }
            if (!o.IsPointForm && rooms.Count != 1)
            {
                issues.Add($"{label} uses the M1 form (wall '{o.Wall}'), which is only accepted on a single room level");
                return none;
            }
            List<RoomSide> sides = level.SidesOf(o, out float along);
            if (sides.Count == 0)
            {
                issues.Add(o.IsPointForm ? $"{label} ({o.X}, {o.Z}) does not lie on a wall" : $"{label} on wall '{o.Wall}' at {o.Center} does not lie on a wall");
                return none;
            }
            foreach (RoomSide s in sides)
            {
                RoomDef r = rooms[s.Room];
                if (along - o.Width * 0.5f < s.From - Eps || along + o.Width * 0.5f > s.To + Eps)
                {
                    issues.Add($"{label} is {o.Width} m wide and runs past the end of the wall of room {Name(r, s.Room)}");
                }
                if (o.Top > r.WallHeight + Eps)
                {
                    issues.Add($"{label} top {o.Top} is above the wall height {r.WallHeight} of room {Name(r, s.Room)}");
                }
            }
            return sides;
        }

        // ----- Decoys, rugs, designer route -----

        private static void CheckDecoys(LevelDef level, List<RoomDef> rooms, List<string> issues)
        {
            Color player = LevelJson.ParseColor(level.Player?.Color, Color.red);
            for (int i = 0; i < level.Decoys.Count; i++)
            {
                DecoyDef d = level.Decoys[i];
                string label = $"decoy {i + 1}";
                // M4: a decoy is a furniture body too (its size comes from its kind), and shows that body's model.
                if (!BodyKinds.IsKnown(d.Kind))
                {
                    issues.Add($"{label} kind '{d.Kind}' is not a furniture body ({string.Join(", ", BodyKinds.All)})");
                }
                else if (!string.IsNullOrEmpty(d.Model) && d.Model != BodyDef.For(BodyKinds.Of(d.Kind)).Model)
                {
                    BodyDef decoyBody = BodyDef.For(BodyKinds.Of(d.Kind));
                    issues.Add($"{label} model '{d.Model}' is not the model of the {decoyBody.Kind} body ({decoyBody.Model ?? "none, procedural"})");
                }
                Vector3 size = level.DecoySize(d);
                if (size.x <= 0f || size.y <= 0f || size.z <= 0f)
                {
                    issues.Add($"{label} has a non positive size");
                    continue;
                }
                if (!FootprintInsideRoom(rooms, d.X, d.Z, size.x, size.z, d.Yaw))
                {
                    issues.Add($"{label} ({d.X}, {d.Z}) is not inside a room");
                }
                if (d.Color != null && SameColor(LevelJson.ParseColor(d.Color, Color.clear), player))
                {
                    issues.Add($"{label} has the player color {d.Color}: the player furniture must be the only one of its color");
                }
                foreach (PropDef prop in level.Props)
                {
                    if (RectsOverlap(new Vector2(d.X, d.Z), new Vector2(size.x, size.z) * 0.5f, d.Yaw,
                            new Vector2(prop.X, prop.Z), new Vector2(prop.SizeX, prop.SizeZ) * 0.5f, prop.Yaw))
                    {
                        issues.Add($"{label} overlaps prop {prop.Name}");
                    }
                }
            }
        }

        private static void CheckRugs(LevelDef level, List<RoomDef> rooms, List<string> issues)
        {
            for (int i = 0; i < level.Rugs.Count; i++)
            {
                RugDef r = level.Rugs[i];
                if (r.SizeX <= 0f || r.SizeZ <= 0f)
                {
                    issues.Add($"rug {i + 1} has a non positive size");
                }
                else if (!FootprintInsideRoom(rooms, r.X, r.Z, r.SizeX, r.SizeZ, r.Yaw))
                {
                    issues.Add($"rug {i + 1} ({r.X}, {r.Z}) is not inside a room");
                }
            }
        }

        private static void CheckRoute(LevelDef level, List<RoomDef> rooms, BodyDef body, List<string> issues)
        {
            float previous = 0f;
            for (int i = 0; i < level.DesignerRoute.Count; i++)
            {
                RouteStepDef s = level.DesignerRoute[i];
                if (!InsideRoom(rooms, s.X, s.Z, 0f, 0f))
                {
                    issues.Add($"designer route waypoint {i + 1} ({s.X}, {s.Z}) is not inside a room");
                }
                if (s.At < previous - Eps)
                {
                    issues.Add($"designer route waypoint {i + 1} time {s.At} is before the previous one ({previous})");
                }
                previous = Mathf.Max(previous, s.At);
                // M4 (CONTRACT_M4 5, amendment 9.3): the action is one the level's body can do; the wait is not negative.
                if (s.Action != null && s.Action != RouteStepDef.ActionToggle && s.Action != RouteStepDef.ActionRightUp)
                {
                    issues.Add($"designer route waypoint {i + 1} action '{s.Action}' is neither {RouteStepDef.ActionToggle} nor {RouteStepDef.ActionRightUp}");
                }
                else if (s.Action == RouteStepDef.ActionToggle && !body.HasLight)
                {
                    issues.Add($"designer route waypoint {i + 1} toggles a light, but the {body.Kind} body has none");
                }
                else if (s.Action == RouteStepDef.ActionRightUp && !body.Tips)
                {
                    issues.Add($"designer route waypoint {i + 1} rights the furniture up, but the {body.Kind} body never tips");
                }
            }
        }

        // ----- Geometry -----

        private static bool InsideRoom(List<RoomDef> rooms, float x, float z, float marginX, float marginZ)
        {
            foreach (RoomDef r in rooms)
            {
                if (Mathf.Abs(x - r.X) <= r.SizeX * 0.5f - marginX + Eps && Mathf.Abs(z - r.Z) <= r.SizeZ * 0.5f - marginZ + Eps)
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>A rectangle of half sizes (hx, hz) and no yaw, wholly inside one room.</summary>
        private static bool InsideRoom(List<RoomDef> rooms, float x, float z, float hx, float hz, float yawDeg)
        {
            return FootprintInsideRoom(rooms, x, z, hx * 2f, hz * 2f, yawDeg);
        }

        /// <summary>The rotated footprint (full sizes) lies wholly inside one room interior.</summary>
        private static bool FootprintInsideRoom(List<RoomDef> rooms, float x, float z, float sizeX, float sizeZ, float yawDeg)
        {
            float r = yawDeg * Mathf.Deg2Rad;
            float c = Mathf.Abs(Mathf.Cos(r));
            float s = Mathf.Abs(Mathf.Sin(r));
            float hx = (c * sizeX + s * sizeZ) * 0.5f;
            float hz = (s * sizeX + c * sizeZ) * 0.5f;
            return InsideRoom(rooms, x, z, hx, hz);
        }

        private static bool OverlapsDecoy(LevelDef level, DecoyDef d, float x, float z, float radius)
        {
            Vector3 size = level.DecoySize(d);
            return RectsOverlap(new Vector2(x, z), new Vector2(radius, radius), 0f, new Vector2(d.X, d.Z), new Vector2(size.x, size.z) * 0.5f, d.Yaw);
        }

        private static bool SameColor(Color a, Color b)
        {
            Color32 x = a;
            Color32 y = b;
            return x.r == y.r && x.g == y.g && x.b == y.b;
        }

        /// <summary>Separating axis test between a rectangle (center, half sizes, yaw) and a prop footprint.</summary>
        public static bool Overlaps(float x, float z, float halfX, float halfZ, float yawDeg, PropDef prop)
        {
            return RectsOverlap(
                new Vector2(x, z), new Vector2(halfX, halfZ), yawDeg,
                new Vector2(prop.X, prop.Z), new Vector2(prop.SizeX * 0.5f, prop.SizeZ * 0.5f), prop.Yaw);
        }

        public static bool RectsOverlap(Vector2 ca, Vector2 ha, float yawA, Vector2 cb, Vector2 hb, float yawB)
        {
            Vector2[] axes = { AxisX(yawA), AxisZ(yawA), AxisX(yawB), AxisZ(yawB) };
            Vector2 d = cb - ca;
            foreach (Vector2 axis in axes)
            {
                float ra = ha.x * Mathf.Abs(Vector2.Dot(AxisX(yawA), axis)) + ha.y * Mathf.Abs(Vector2.Dot(AxisZ(yawA), axis));
                float rb = hb.x * Mathf.Abs(Vector2.Dot(AxisX(yawB), axis)) + hb.y * Mathf.Abs(Vector2.Dot(AxisZ(yawB), axis));
                // Touching edges do not overlap.
                if (Mathf.Abs(Vector2.Dot(d, axis)) >= ra + rb - 1e-4f)
                {
                    return false;
                }
            }
            return true;
        }

        private static Vector2 AxisX(float yawDeg)
        {
            Vector3 v = YawMath.Rotate(Vector3.right, yawDeg);
            return new Vector2(v.x, v.z);
        }

        private static Vector2 AxisZ(float yawDeg)
        {
            Vector3 v = YawMath.Rotate(Vector3.forward, yawDeg);
            return new Vector2(v.x, v.z);
        }
    }
}
