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
    ///
    /// M5 (docs/CONTRACT_M5_v3.md 2, 3, 4, 15.2, 15.4, 15.6, 15.10; CONTRACT_M5.md 3, 6, 16.5 to 16.7): the leaves, the
    /// split level (platforms, ramps, flush ends, widths on the audit cell grid, thresholds, heights under footprints), the
    /// watchers (kinds, personalities, patterns, sleep, the dog), the load and the M5 lesson prerequisites. The station walk
    /// check against closed leaves belongs to the audit (LevelAudit.CheckWalks), not here.
    ///
    /// M5 wave 5B (CONTRACT_M5.md 4 to 6, 8, 10, 16.5, 16.8, 16.9): the robot (at most one, its loop on the floor of the
    /// rooms and its floor level, clear of walls, props, decoys, leaves and their swing sectors with its radius, clearance
    /// from the spawn, the seat homes and the exit, its start a waypoint index), no load on the rocking chair, and the
    /// robot, rock, load and final lessons.
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
            CheckRoute(level, level.DesignerRouteHard, "hard designer route", rooms, body, issues); // M7 design (CONTRACT_M7 4.1)
            CheckLesson(level, body, issues);
            CheckLeaves(level, rooms, body, issues);
            CheckSplitLevel(level, rooms, body, issues);
            CheckPassages(level, rooms, body, issues);
            CheckWatchers(level, issues);
            CheckLoad(level, body, issues);
            CheckRobots(level, rooms, issues);
            CheckM6Gameplay(level, rooms, issues);

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

        /// <summary>
        /// The lesson knob (amendment 9.11) is one of the known values, and the level has what the lesson is about. M5: door a
        /// closed leaf, pet a dog, split a platform; wave 5B: robot a robot, rock the rocking chair body, load a load on the
        /// player, final at least <see cref="FinalMechanics"/> of those six mechanics (<see cref="MechanicsOf"/>).
        /// </summary>
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
            // M5 (CONTRACT_M5_v3 15.10, CONTRACT_M5 16.6): what the door, pet and split lessons are about.
            else if (lesson == LevelDef.LessonDoor && !level.Doors.Exists(d => d != null && d.Leaf == OpeningDef.LeafClosed))
            {
                issues.Add("lesson door needs a closed leaf");
            }
            else if (lesson == LevelDef.LessonPet && (level.Inhabitants == null || !level.Inhabitants.Exists(h => h != null && h.Kind == PersonalityDef.Dog)))
            {
                issues.Add("lesson pet needs a dog");
            }
            else if (lesson == LevelDef.LessonSplit && (level.Platforms == null || level.Platforms.Count == 0))
            {
                issues.Add("lesson split needs a platform");
            }
            // M5 wave 5B (CONTRACT_M5 4 to 6, 8, 10): what the robot, rock, load and final lessons are about.
            else if (lesson == LevelDef.LessonRobot && (level.Robots == null || level.Robots.Count == 0))
            {
                issues.Add("lesson robot needs a robot");
            }
            else if (lesson == LevelDef.LessonRock && !body.Rocks)
            {
                issues.Add($"lesson rock needs a body that rocks (the rocking chair), not the {body.Kind}");
            }
            else if (lesson == LevelDef.LessonLoad && string.IsNullOrEmpty(level.Player?.Load))
            {
                issues.Add("lesson load needs a load on the player");
            }
            // M6 (CONTRACT_M6 2.5): the wardrobe lesson needs a wardrobe the player body fits in.
            else if (lesson == LevelDef.LessonWardrobe
                && (level.Wardrobes().Count == 0 || !WardrobeRule.Fits(body.Size, string.IsNullOrEmpty(level.Player?.Load) ? 0f : Tuning.LoadHeight)))
            {
                issues.Add($"lesson wardrobe needs a wardrobe and a body that fits in it (the stool or the floor lamp), not the {body.Kind}");
            }
            else if (lesson == LevelDef.LessonFinal)
            {
                List<string> mechanics = MechanicsOf(level);
                if (mechanics.Count < FinalMechanics) // MUTATION:LESSON_FINAL
                {
                    issues.Add($"lesson final needs at least {FinalMechanics} of door, pet, split, robot, rock and load; the level has "
                        + (mechanics.Count == 0 ? "none" : string.Join(", ", mechanics)));
                }
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
                // M7 (CONTRACT_M7 1.2): floorFinish is visual only, and only meaningful on a hard floor (a soft one
                // is already a distinct carpet look; tile and carpet together would be two floor treatments at once).
                if (!string.IsNullOrEmpty(r.FloorFinish) && r.FloorFinish != RoomDef.TileFinish)
                {
                    issues.Add($"room {Name(r, i)} floor finish '{r.FloorFinish}' is not 'tile'"); // MUTATION:FLOOR_FINISH_VALUE
                }
                else if (r.IsTile && r.IsSoft) // MUTATION:FLOOR_FINISH_SOFT_TILE
                {
                    issues.Add($"room {Name(r, i)} is both soft and tiled: a tile finish needs a hard floor");
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
            CheckRoute(level, level.DesignerRoute, "designer route", rooms, body, issues);
        }

        /// <summary>M7 design: the checks of one route, <paramref name="route"/> (designerRoute or designerRouteHard).</summary>
        private static void CheckRoute(LevelDef level, List<RouteStepDef> route, string name, List<RoomDef> rooms, BodyDef body, List<string> issues)
        {
            route = route ?? new List<RouteStepDef>();
            float previous = 0f;
            for (int i = 0; i < route.Count; i++)
            {
                RouteStepDef s = route[i];
                if (!InsideRoom(rooms, s.X, s.Z, 0f, 0f))
                {
                    issues.Add($"{name} waypoint {i + 1} ({s.X}, {s.Z}) is not inside a room");
                }
                if (s.At < previous - Eps)
                {
                    issues.Add($"{name} waypoint {i + 1} time {s.At} is before the previous one ({previous})");
                }
                previous = Mathf.Max(previous, s.At);
                // M4 (CONTRACT_M4 5, amendment 9.3): the action is one the level's body can do; the wait is not negative.
                // M5 (CONTRACT_M5_v3 5, 15.10): "open" presses E at a closed leaf the step names by its id.
                if (s.Action != null && s.Action != RouteStepDef.ActionToggle && s.Action != RouteStepDef.ActionRightUp
                    && s.Action != RouteStepDef.ActionOpen && s.Action != RouteStepDef.ActionHide && s.Action != RouteStepDef.ActionLeave)
                {
                    issues.Add($"{name} waypoint {i + 1} action '{s.Action}' is neither {RouteStepDef.ActionToggle} nor {RouteStepDef.ActionRightUp} nor {RouteStepDef.ActionOpen} nor {RouteStepDef.ActionHide} nor {RouteStepDef.ActionLeave}");
                }
                else if (s.Action == RouteStepDef.ActionOpen)
                {
                    if (string.IsNullOrEmpty(s.Door) || !level.Doors.Exists(d => d != null && d.HasLeaf && d.Id == s.Door))
                    {
                        issues.Add($"{name} waypoint {i + 1} opens door '{s.Door}', which is not a leaf of the level");
                    }
                }
                else if (s.Action == RouteStepDef.ActionToggle && !body.HasLight)
                {
                    issues.Add($"{name} waypoint {i + 1} toggles a light, but the {body.Kind} body has none");
                }
                else if (s.Action == RouteStepDef.ActionRightUp && !body.Tips)
                {
                    issues.Add($"{name} waypoint {i + 1} rights the furniture up, but the {body.Kind} body never tips");
                }
                if (s.Door != null && s.Action != RouteStepDef.ActionOpen)
                {
                    issues.Add($"{name} waypoint {i + 1} names door '{s.Door}' but its action is not {RouteStepDef.ActionOpen}");
                }
            }
        }

        // ----- M5: leaves (docs/CONTRACT_M5_v3.md 3, 15.2, 15.10) -----

        /// <summary>
        /// Leaf, hinge, swing and id only on doors; a leaf is "open" or "closed", has a unique id and a swing room on either
        /// side of it; at most <see cref="Tuning.MaxLeavesPerLevel"/> leaves; the swing sector (a quarter disc of radius the
        /// width) is free of props, decoys, rugs, stations, seat homes and the spawn.
        /// </summary>
        private static void CheckLeaves(LevelDef level, List<RoomDef> rooms, BodyDef body, List<string> issues)
        {
            for (int k = 0; k < level.Windows.Count; k++)
            {
                OpeningDef w = level.Windows[k];
                if (w != null && (w.Leaf != null || w.Hinge != null || w.Id != null || w.Swing != null))
                {
                    issues.Add($"window {k + 1} has a leaf, hinge, swing or id: only doors carry them");
                }
            }
            var ids = new HashSet<string>();
            int leaves = 0;
            for (int k = 0; k < level.Doors.Count; k++)
            {
                OpeningDef d = level.Doors[k];
                string label = $"door {k + 1}";
                if (d == null)
                {
                    continue;
                }
                if (!d.HasLeaf)
                {
                    if (d.Hinge != null || d.Swing != null || d.Id != null)
                    {
                        issues.Add($"{label} has a hinge, swing or id but no leaf");
                    }
                    continue;
                }
                leaves++;
                if (d.Leaf != OpeningDef.LeafOpen && d.Leaf != OpeningDef.LeafClosed)
                {
                    issues.Add($"{label} leaf '{d.Leaf}' is neither {OpeningDef.LeafOpen} nor {OpeningDef.LeafClosed}");
                }
                if (d.Hinge != null && d.Hinge != OpeningDef.HingeStart && d.Hinge != OpeningDef.HingeEnd)
                {
                    issues.Add($"{label} hinge '{d.Hinge}' is neither {OpeningDef.HingeStart} nor {OpeningDef.HingeEnd}");
                }
                if (string.IsNullOrEmpty(d.Id))
                {
                    issues.Add($"{label} has a leaf but no id");
                }
                else if (!ids.Add(d.Id))
                {
                    issues.Add($"door id '{d.Id}' is used twice");
                }
                List<RoomSide> sides = level.SidesOf(d, out float _);
                if (string.IsNullOrEmpty(d.Swing))
                {
                    issues.Add($"{label} has a leaf but no swing room");
                    continue;
                }
                if (!sides.Exists(s => rooms[s.Room].Id == d.Swing))
                {
                    issues.Add($"{label} swings into '{d.Swing}', which is not a room on either side of it");
                    continue;
                }
                CheckSwingSector(level, body, new DoorGeometry(level, d), $"{label} ({d.Id}) swing sector", issues);
            }
            if (leaves > Tuning.MaxLeavesPerLevel)
            {
                issues.Add($"{leaves} door leaves: at most {Tuning.MaxLeavesPerLevel} per level");
            }
        }

        private static void CheckSwingSector(LevelDef level, BodyDef body, DoorGeometry g, string label, List<string> issues)
        {
            foreach (PropDef prop in level.Props)
            {
                if (g.SectorOverlapsRect(prop.Position, prop.SizeX, prop.SizeZ, prop.Yaw))
                {
                    issues.Add($"{label} overlaps prop {prop.Name}");
                }
            }
            for (int i = 0; i < level.Decoys.Count; i++)
            {
                DecoyDef d = level.Decoys[i];
                Vector3 size = level.DecoySize(d);
                if (g.SectorOverlapsRect(d.Position, size.x, size.z, d.Yaw))
                {
                    issues.Add($"{label} overlaps decoy {i + 1}");
                }
            }
            for (int i = 0; i < level.Rugs.Count; i++)
            {
                RugDef r = level.Rugs[i];
                if (g.SectorOverlapsRect(r.Position, r.SizeX, r.SizeZ, r.Yaw))
                {
                    issues.Add($"{label} overlaps rug {i + 1}");
                }
            }
            if (level.Player != null && g.SectorOverlapsRect(level.Player.Position, body.Size.x, body.Size.z, level.Player.Yaw))
            {
                issues.Add($"{label} overlaps the player spawn");
            }
            if (level.Inhabitants == null)
            {
                return;
            }
            foreach (InhabitantDef h in level.Inhabitants)
            {
                if (h?.Stations == null)
                {
                    continue;
                }
                for (int i = 0; i < h.Stations.Count; i++)
                {
                    StationDef s = h.Stations[i];
                    if (g.SectorOverlapsDisc(s.Position, Tuning.InhabitantRadius))
                    {
                        issues.Add($"{label} overlaps inhabitant {h.Name} station {i + 1}");
                    }
                    if (s.Seat != null && g.SectorOverlapsRect(s.Seat.Position, body.Size.x, body.Size.z, s.Seat.Yaw))
                    {
                        issues.Add($"{label} overlaps the seat home of inhabitant {h.Name} station {i + 1}");
                    }
                }
            }
        }

        // ----- M5: the split level (docs/CONTRACT_M5_v3.md 2, 15.4; CONTRACT_M5.md 16.6) -----

        /// <summary>
        /// Platforms inside a room, named, unique, between the height bounds, never overlapping; ramps naming a platform, yaw
        /// a multiple of 90, inside a room, at most RampMaxSlope, flush at the foot (the floor at 0) and at the head (on the
        /// platform edge facing them); no platform or ramp over a door threshold; no footprint straddles two heights or lies
        /// on a ramp.
        /// </summary>
        private static void CheckSplitLevel(LevelDef level, List<RoomDef> rooms, BodyDef body, List<string> issues)
        {
            bool platforms = level.Platforms != null && level.Platforms.Count > 0;
            bool ramps = level.Ramps != null && level.Ramps.Count > 0;
            if (!platforms && !ramps)
            {
                return;
            }
            float tolerance = Tuning.FloorFlushTolerance;
            var names = new HashSet<string>();
            var surfaces = new List<(string label, Vector2 center, Vector2 half, float yaw)>();
            for (int i = 0; i < level.Platforms.Count; i++)
            {
                PlatformDef p = level.Platforms[i];
                string label = $"platform {p?.Name ?? "#" + (i + 1)}";
                if (p == null || p.SizeX <= 0f || p.SizeZ <= 0f)
                {
                    issues.Add($"{label} has a non positive size");
                    continue;
                }
                if (string.IsNullOrEmpty(p.Name))
                {
                    issues.Add($"{label} has no name: a ramp names its platform");
                }
                else if (!names.Add(p.Name))
                {
                    issues.Add($"platform name {p.Name} is used twice");
                }
                if (p.Height < Tuning.PlatformMinHeight - Eps || p.Height > Tuning.PlatformMaxHeight + Eps)
                {
                    issues.Add($"{label} height {p.Height} is outside {Tuning.PlatformMinHeight} to {Tuning.PlatformMaxHeight} m");
                }
                if (!FootprintInsideRoom(rooms, p.X, p.Z, p.SizeX, p.SizeZ, 0f))
                {
                    issues.Add($"{label} is not inside a room");
                }
                surfaces.Add((label, new Vector2(p.X, p.Z), new Vector2(p.SizeX, p.SizeZ) * 0.5f, 0f));
            }
            for (int i = 0; i < level.Ramps.Count; i++)
            {
                RampDef r = level.Ramps[i];
                string label = $"ramp {i + 1}";
                if (r == null || r.Width <= 0f || r.Length <= 0f)
                {
                    issues.Add($"{label} has a non positive size");
                    continue;
                }
                PlatformDef p = FloorMap.PlatformOf(level, r);
                if (p == null)
                {
                    issues.Add($"{label} leads to '{r.Platform}', which is not a platform of the level");
                    continue;
                }
                if (!MultipleOf90(r.Yaw))
                {
                    issues.Add($"{label} yaw {r.Yaw} is not a multiple of 90");
                    continue;
                }
                if (!FootprintInsideRoom(rooms, r.X, r.Z, r.Width, r.Length, r.Yaw))
                {
                    issues.Add($"{label} is not inside a room");
                }
                float slope = Mathf.Atan2(p.Height, r.Length) * Mathf.Rad2Deg;
                if (slope > Tuning.RampMaxSlope + 1e-3f)
                {
                    issues.Add($"{label} rises {slope:0.#} deg: at most {Tuning.RampMaxSlope} deg");
                }
                Vector3 up = YawMath.Forward(r.Yaw);
                Vector3 head = new Vector3(r.X, 0f, r.Z) + up * (r.Length * 0.5f);
                bool alongX = Mathf.Abs(up.x) > 0.5f;
                float edge = alongX ? (up.x > 0f ? p.X - p.SizeX * 0.5f : p.X + p.SizeX * 0.5f) : (up.z > 0f ? p.Z - p.SizeZ * 0.5f : p.Z + p.SizeZ * 0.5f);
                float headLine = alongX ? head.x : head.z;
                float c = alongX ? r.Z : r.X;
                float spanMin = alongX ? p.Z - p.SizeZ * 0.5f : p.X - p.SizeX * 0.5f;
                float spanMax = alongX ? p.Z + p.SizeZ * 0.5f : p.X + p.SizeX * 0.5f;
                if (Mathf.Abs(headLine - edge) > tolerance || c - r.Width * 0.5f < spanMin - tolerance || c + r.Width * 0.5f > spanMax + tolerance)
                {
                    issues.Add($"{label} head is not flush with the edge of platform {p.Name} facing it");
                }
                Vector3 foot = new Vector3(r.X, 0f, r.Z) - up * (r.Length * 0.5f + 2f * tolerance);
                if (level.FloorHeightAt(foot.x, foot.z) > tolerance)
                {
                    issues.Add($"{label} foot is not on the floor (height 0)");
                }
                surfaces.Add((label, new Vector2(r.X, r.Z), new Vector2(r.Width, r.Length) * 0.5f, r.Yaw));
            }
            // No walkable surface above another: platforms and ramps never overlap (a ramp head touches its platform edge).
            for (int a = 0; a < surfaces.Count; a++)
            {
                for (int b = a + 1; b < surfaces.Count; b++)
                {
                    if (RectsOverlap(surfaces[a].center, surfaces[a].half, surfaces[a].yaw, surfaces[b].center, surfaces[b].half, surfaces[b].yaw))
                    {
                        issues.Add($"{surfaces[a].label} and {surfaces[b].label} overlap: no walkable surface above another");
                    }
                }
            }
            // No platform or ramp over a door threshold: the doorway band and one audit cell on each side stay on the floor.
            float t = level.WallThickness();
            for (int k = 0; k < level.Doors.Count; k++)
            {
                OpeningDef door = level.Doors[k];
                List<RoomSide> sides = level.SidesOf(door, out float along);
                if (sides.Count == 0)
                {
                    continue;
                }
                RoomSide s = sides[0];
                Vector2 center = s.AlongX ? new Vector2(along, s.Line) : new Vector2(s.Line, along);
                float depth = t * 0.5f + Tuning.AuditCellSize;
                Vector2 half = s.AlongX ? new Vector2(door.Width * 0.5f, depth) : new Vector2(depth, door.Width * 0.5f);
                foreach ((string label, Vector2 c, Vector2 h, float yaw) in surfaces)
                {
                    if (RectsOverlap(center, half, 0f, c, h, yaw))
                    {
                        issues.Add($"{label} stands over the threshold of door {k + 1}");
                    }
                }
            }
            CheckHeights(level, body, issues);
        }

        private static bool MultipleOf90(float yaw)
        {
            float r = Mathf.Repeat(yaw, 90f);
            return r < 1e-3f || r > 90f - 1e-3f;
        }

        /// <summary>
        /// Nothing straddles two heights or lies on a ramp: props, decoys, rugs, the spawn, the exit, stations and seat homes
        /// stand wholly on the floor or wholly on one platform, never on a ramp.
        /// </summary>
        private static void CheckHeights(LevelDef level, BodyDef body, List<string> issues)
        {
            void Check(string what, Vector3 position, float sizeX, float sizeZ, float yaw)
            {
                var center = new Vector2(position.x, position.z);
                var half = new Vector2(sizeX, sizeZ) * 0.5f;
                for (int i = 0; i < level.Ramps.Count; i++)
                {
                    RampDef r = level.Ramps[i];
                    if (r != null && RectsOverlap(center, half, yaw, new Vector2(r.X, r.Z), new Vector2(r.Width, r.Length) * 0.5f, r.Yaw))
                    {
                        issues.Add($"{what} lies on ramp {i + 1}");
                        return;
                    }
                }
                foreach (PlatformDef p in level.Platforms)
                {
                    if (p == null)
                    {
                        continue;
                    }
                    var pc = new Vector2(p.X, p.Z);
                    var ph = new Vector2(p.SizeX, p.SizeZ) * 0.5f;
                    if (RectsOverlap(center, half, yaw, pc, ph, 0f) && !RectInside(center, half, yaw, pc, ph))
                    {
                        issues.Add($"{what} straddles the edge of platform {p.Name}: it stands on two heights");
                        return;
                    }
                }
            }
            foreach (PropDef prop in level.Props)
            {
                Check($"prop {prop.Name}", prop.Position, prop.SizeX, prop.SizeZ, prop.Yaw);
            }
            for (int i = 0; i < level.Decoys.Count; i++)
            {
                Vector3 size = level.DecoySize(level.Decoys[i]);
                Check($"decoy {i + 1}", level.Decoys[i].Position, size.x, size.z, level.Decoys[i].Yaw);
            }
            for (int i = 0; i < level.Rugs.Count; i++)
            {
                RugDef r = level.Rugs[i];
                Check($"rug {i + 1}", r.Position, r.SizeX, r.SizeZ, r.Yaw);
            }
            if (level.Player != null)
            {
                Check("player spawn", level.Player.Position, body.Size.x, body.Size.z, level.Player.Yaw);
            }
            if (level.Exit != null)
            {
                Check("exit zone", new Vector3(level.Exit.X, 0f, level.Exit.Z), level.Exit.SizeX, level.Exit.SizeZ, 0f);
            }
            if (level.Inhabitants == null)
            {
                return;
            }
            foreach (InhabitantDef h in level.Inhabitants)
            {
                if (h?.Stations == null)
                {
                    continue;
                }
                for (int i = 0; i < h.Stations.Count; i++)
                {
                    StationDef s = h.Stations[i];
                    float d = 2f * Tuning.InhabitantRadius;
                    Check($"inhabitant {h.Name} station {i + 1}", s.Position, d, d, 0f);
                    if (s.Seat != null)
                    {
                        Check($"inhabitant {h.Name} station {i + 1} seat home", s.Seat.Position, body.Size.x, body.Size.z, s.Seat.Yaw);
                    }
                }
            }
        }

        /// <summary>True when the rotated rectangle (centre, half sizes, yaw) lies wholly inside an axis aligned one.</summary>
        private static bool RectInside(Vector2 center, Vector2 half, float yaw, Vector2 outerCenter, Vector2 outerHalf)
        {
            for (int k = 0; k < 4; k++)
            {
                float sx = k == 0 || k == 3 ? -1f : 1f;
                float sz = k < 2 ? -1f : 1f;
                Vector3 corner = YawMath.Rotate(new Vector3(sx * half.x, 0f, sz * half.y), yaw);
                if (Mathf.Abs(center.x + corner.x - outerCenter.x) > outerHalf.x + 1e-3f || Mathf.Abs(center.y + corner.z - outerCenter.y) > outerHalf.y + 1e-3f)
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>
        /// CONTRACT_M5 16.6: corridors (every room's narrow side) and ramps are at least Tuning.PassageWidth wide, or
        /// Tuning.ArmchairPassageWidth for the armchair; along every ramp, between its railings, a line of audit cell
        /// centres (the 0.5 m grid of its room) leaves the body its radius on both sides, so the audit can climb it; and
        /// the armchair's ramp has its axis on such a line.
        /// </summary>
        private static void CheckPassages(LevelDef level, List<RoomDef> rooms, BodyDef body, List<string> issues)
        {
            float required = PassageWidth(body);
            for (int i = 0; i < rooms.Count; i++)
            {
                float narrow = Mathf.Min(rooms[i].SizeX, rooms[i].SizeZ);
                if (narrow < required - Eps)
                {
                    issues.Add($"room {Name(rooms[i], i)} is {narrow} m wide: a corridor is at least {required} m wide for the {body.Kind}");
                }
            }
            if (level.Ramps == null)
            {
                return;
            }
            float cell = Tuning.AuditCellSize;
            for (int i = 0; i < level.Ramps.Count; i++)
            {
                RampDef r = level.Ramps[i];
                if (r == null || r.Width <= 0f || !MultipleOf90(r.Yaw))
                {
                    continue;
                }
                if (r.Width < required - Eps)
                {
                    issues.Add($"ramp {i + 1} is {r.Width} m wide: the {body.Kind} needs at least {required} m");
                    continue;
                }
                RoomDef room = level.RoomAt(new Vector3(r.X, 0f, r.Z));
                if (room == null)
                {
                    continue;
                }
                // The ramp's axis runs along its uphill direction; the cells across it are counted on the other axis.
                bool acrossX = Mathf.Abs(YawMath.Forward(r.Yaw).z) > 0.5f;
                float axis = acrossX ? r.X : r.Z;
                float origin = acrossX ? room.MinX : room.MinZ;
                float k = Mathf.Round((axis - origin) / cell - 0.5f);
                float nearest = origin + (k + 0.5f) * cell;
                float slack = r.Width * 0.5f - Tuning.RailingThickness - body.Radius;
                if (Mathf.Abs(nearest - axis) > slack + Eps)
                {
                    issues.Add($"ramp {i + 1}: no line of audit cells fits the {body.Kind} between its railings (axis {axis} off the {cell} m cell grid of its room)");
                }
                else if (body.Kind == BodyKinds.Armchair && Mathf.Abs(nearest - axis) > Tuning.FloorFlushTolerance)
                {
                    issues.Add($"ramp {i + 1}: the armchair's ramp has its axis on a line of audit cell centres of its room ({nearest}), not at {axis}");
                }
            }
        }

        /// <summary>CONTRACT_M5 16.6: the passage width a body needs (the armchair a wider one).</summary>
        public static float PassageWidth(BodyDef body)
        {
            return body != null && body.Kind == BodyKinds.Armchair ? Tuning.ArmchairPassageWidth : Tuning.PassageWidth;
        }

        // ----- M5: watchers (docs/CONTRACT_M5.md 3, 16.7; CONTRACT_M5_v3.md 4, 15.6, 15.10) -----

        /// <summary>The inhabitant kinds: "human" (also null) and "dog".</summary>
        public const string KindHuman = "human";

        /// <summary>
        /// Known kinds, personalities and patterns; at most Tuning.MaxHumans humans and one dog; a seed only with wander;
        /// wander needs 3 stations or more, pingpong 2; sleep only on a dog's stations; a dog never sits and never glances;
        /// a prop named by a sit has a unique name.
        /// </summary>
        private static void CheckWatchers(LevelDef level, List<string> issues)
        {
            if (level.Inhabitants == null)
            {
                return;
            }
            int humans = 0;
            int dogs = 0;
            var seats = new HashSet<string>();
            foreach (InhabitantDef h in level.Inhabitants)
            {
                if (h == null)
                {
                    continue;
                }
                string label = $"inhabitant {h.Name}";
                if (h.Kind != null && h.Kind != KindHuman && h.Kind != PersonalityDef.Dog)
                {
                    issues.Add($"{label} kind '{h.Kind}' is neither {KindHuman} nor {PersonalityDef.Dog}");
                }
                bool dog = h.Kind == PersonalityDef.Dog;
                if (dog)
                {
                    dogs++;
                }
                else
                {
                    humans++;
                }
                if (h.Personality != null && System.Array.IndexOf(PersonalityDef.All, h.Personality) < 0)
                {
                    issues.Add($"{label} personality '{h.Personality}' is not one of {string.Join(", ", PersonalityDef.All)}");
                }
                else if (h.Personality == PersonalityDef.Dog && !dog)
                {
                    issues.Add($"{label} has the dog personality but is not of kind {PersonalityDef.Dog}");
                }
                if (h.Pattern != null && System.Array.IndexOf(RoutinePatterns.All, h.Pattern) < 0)
                {
                    issues.Add($"{label} pattern '{h.Pattern}' is not one of {string.Join(", ", RoutinePatterns.All)}");
                }
                string pattern = RoutinePatterns.Normalize(h.Pattern);
                if (h.Seed != 0 && pattern != RoutinePatterns.Wander)
                {
                    issues.Add($"{label} has a seed but its pattern is {pattern}: a seed is for {RoutinePatterns.Wander} only");
                }
                if (h.Seed < 0)
                {
                    issues.Add($"{label} seed {h.Seed} is negative: a seed is in [0, 2^31 - 1]");
                }
                int n = h.Stations != null ? h.Stations.Count : 0;
                if (pattern == RoutinePatterns.Wander && n < 3)
                {
                    issues.Add($"{label} wanders over {n} stations: {RoutinePatterns.Wander} needs 3 or more");
                }
                else if (pattern == RoutinePatterns.PingPong && n < 2)
                {
                    issues.Add($"{label} ping-pongs over {n} station: {RoutinePatterns.PingPong} needs 2 or more");
                }
                for (int i = 0; i < n; i++)
                {
                    StationDef s = h.Stations[i];
                    string station = $"{label} station {i + 1}";
                    if (s.Sleep && !dog)
                    {
                        issues.Add($"{station} sleeps: only a dog sleeps");
                    }
                    if (dog && !string.IsNullOrEmpty(s.Sit))
                    {
                        issues.Add($"{station} sits: a dog never sits");
                    }
                    if (dog && s.Glances != null && s.Glances.Count > 0)
                    {
                        issues.Add($"{station} glances: a dog has no glances");
                    }
                    if (!string.IsNullOrEmpty(s.Sit) && !s.SitsOnPlayer)
                    {
                        seats.Add(s.Sit);
                    }
                }
            }
            if (humans > Tuning.MaxHumans)
            {
                issues.Add($"{humans} humans: at most {Tuning.MaxHumans} per level");
            }
            if (dogs > 1)
            {
                issues.Add($"{dogs} dogs: at most one per level");
            }
            foreach (string seat in seats)
            {
                int count = level.Props.FindAll(p => p.Name == seat).Count;
                if (count > 1)
                {
                    issues.Add($"{count} props are named {seat}: a prop named by a sit has a unique name");
                }
            }
        }

        // ----- M5: the load (docs/CONTRACT_M5.md 6, 16.5) -----

        /// <summary>The loads a furniture may carry on top.</summary>
        public static readonly string[] LoadKinds = { "vase", "books", "plant" };

        /// <summary>A known load kind, never on the floor lamp nor on the rocking chair (CONTRACT_M5 16.5).</summary>
        private static void CheckLoad(LevelDef level, BodyDef body, List<string> issues)
        {
            string load = level.Player?.Load;
            if (load == null)
            {
                return;
            }
            if (System.Array.IndexOf(LoadKinds, load) < 0)
            {
                issues.Add($"player load '{load}' is not one of {string.Join(", ", LoadKinds)}");
            }
            if (body.Kind == BodyKinds.FloorLamp)
            {
                issues.Add($"player load '{load}' on the {body.Kind}: the floor lamp carries no load");
            }
            else if (body.Kind == BodyKinds.RockingChair)
            {
                issues.Add($"player load '{load}' on the {body.Kind}: the rocking chair carries no load"); // MUTATION:ROCKING_LOAD
            }
        }

        // ----- M5 wave 5B: the mechanics of a level (CONTRACT_M5 10, the final lesson) -----

        /// <summary>CONTRACT_M5 8 and 10: the final level combines at least this many of the M5 mechanics.</summary>
        public const int FinalMechanics = 3;

        /// <summary>
        /// The M5 mechanics a level has, named by their lessons, in this order: "door" (a closed leaf), "pet" (a dog), "split"
        /// (a platform), "robot" (a robot), "rock" (the rocking chair body) and "load" (a load on the player). The final
        /// lesson needs <see cref="FinalMechanics"/> of them; the audit's final check reads the same list.
        /// </summary>
        public static List<string> MechanicsOf(LevelDef level)
        {
            var mechanics = new List<string>();
            if (level == null)
            {
                return mechanics;
            }
            if (level.Doors != null && level.Doors.Exists(d => d != null && d.Leaf == OpeningDef.LeafClosed))
            {
                mechanics.Add(LevelDef.LessonDoor);
            }
            if (level.Inhabitants != null && level.Inhabitants.Exists(h => h != null && h.Kind == PersonalityDef.Dog))
            {
                mechanics.Add(LevelDef.LessonPet);
            }
            if (level.Platforms != null && level.Platforms.Count > 0)
            {
                mechanics.Add(LevelDef.LessonSplit);
            }
            if (level.Robots != null && level.Robots.Count > 0)
            {
                mechanics.Add(LevelDef.LessonRobot);
            }
            if (level.Player != null && level.PlayerBody().Rocks)
            {
                mechanics.Add(LevelDef.LessonRock);
            }
            if (!string.IsNullOrEmpty(level.Player?.Load))
            {
                mechanics.Add(LevelDef.LessonLoad);
            }
            return mechanics;
        }

        // ----- M6 gameplay (docs/CONTRACT_M6.md 2.5 to 2.7) -----

        /// <summary>
        /// M6: every wardrobe prop is Tuning.WardrobeSize* (1.0 x 2.0 x 0.6, within 1 mm), an occluder, and its entry zone (the
        /// strip WardrobeReach deep along its whole front face, WardrobeRule.EntryCenter) lies inside a room and clear of every
        /// other prop and decoy. "openedByInhabitants" is only on a door with a leaf (never a window, never a doorway); a level
        /// with "doorMemory" has at least one leaf.
        /// </summary>
        private static void CheckM6Gameplay(LevelDef level, List<RoomDef> rooms, List<string> issues)
        {
            const float sizeEps = 1e-3f;
            foreach (PropDef w in level.Wardrobes())
            {
                string label = $"wardrobe {w.Name}";
                if (Mathf.Abs(w.SizeX - Tuning.WardrobeSizeX) > sizeEps || Mathf.Abs(w.SizeY - Tuning.WardrobeSizeY) > sizeEps
                    || Mathf.Abs(w.SizeZ - Tuning.WardrobeSizeZ) > sizeEps)
                {
                    issues.Add($"{label} is ({w.SizeX}, {w.SizeY}, {w.SizeZ}): a wardrobe is ({Tuning.WardrobeSizeX}, {Tuning.WardrobeSizeY}, {Tuning.WardrobeSizeZ})");
                    continue;
                }
                if (!w.Occluder)
                {
                    issues.Add($"{label} is not an occluder");
                }
                Vector3 entry = WardrobeRule.EntryCenter(w);
                if (!FootprintInsideRoom(rooms, entry.x, entry.z, w.SizeX, Tuning.WardrobeReach, w.Yaw))
                {
                    issues.Add($"{label}: its front (entry zone at ({entry.x:0.###}, {entry.z:0.###})) is not inside a room");
                }
                var half = new Vector2(w.SizeX, Tuning.WardrobeReach) * 0.5f;
                foreach (PropDef other in level.Props)
                {
                    if (other != w && RectsOverlap(new Vector2(entry.x, entry.z), half, w.Yaw,
                            new Vector2(other.X, other.Z), new Vector2(other.SizeX, other.SizeZ) * 0.5f, other.Yaw))
                    {
                        issues.Add($"{label}: prop {other.Name} stands in its front");
                    }
                }
                for (int d = 0; d < level.Decoys.Count; d++)
                {
                    DecoyDef decoy = level.Decoys[d];
                    Vector3 ds = level.DecoySize(decoy);
                    if (RectsOverlap(new Vector2(entry.x, entry.z), half, w.Yaw, new Vector2(decoy.X, decoy.Z), new Vector2(ds.x, ds.z) * 0.5f, decoy.Yaw))
                    {
                        issues.Add($"{label}: decoy {d + 1} stands in its front");
                    }
                }
            }
            for (int k = 0; k < level.Windows.Count; k++)
            {
                if (level.Windows[k] != null && level.Windows[k].OpenedByInhabitants)
                {
                    issues.Add($"window {k + 1} is openedByInhabitants: only a door with a leaf is");
                }
            }
            for (int k = 0; k < level.Doors.Count; k++)
            {
                OpeningDef d = level.Doors[k];
                if (d != null && d.OpenedByInhabitants && !d.HasLeaf)
                {
                    issues.Add($"door {k + 1} is openedByInhabitants but has no leaf");
                }
            }
            if (level.DoorMemory && level.LeafDoors().Count == 0)
            {
                issues.Add("doorMemory needs at least one door leaf");
            }
        }

        // ----- M5 wave 5B: the robot (docs/CONTRACT_M5.md 4, 16.8) -----

        /// <summary>
        /// At most one robot per level. Each robot has at least 2 waypoints, a start that is a waypoint index, a speed that
        /// is not negative (0 means Tuning.RobotSpeed) and no two consecutive waypoints at one point. Every straight segment of
        /// its loop (each waypoint to the next, the last back to the first), swept by the robot's disc of Tuning.RobotRadius:
        /// <list type="bullet">
        /// <item>stays on the floor of the rooms, clear of every wall: it crosses a wall only through a doorway without a leaf
        /// between two rooms (<see cref="DiscFreeSpace"/>), so it never leaves the house;</item>
        /// <item>stays on the floor level: clear of every platform and ramp (their railings stand inside them);</item>
        /// <item>stays clear of every prop and decoy, of every leaf's swing sector and of the leaf itself, closed or open;</item>
        /// <item>keeps Tuning.RobotClearance (centre line) from the player spawn, every seat home and the exit zone.</item>
        /// </list>
        /// Inhabitants may walk across its loop (CONTRACT_M5 16.8: it has no collider); rugs are floor.
        /// </summary>
        private static void CheckRobots(LevelDef level, List<RoomDef> rooms, List<string> issues)
        {
            if (level.Robots == null || level.Robots.Count == 0)
            {
                return;
            }
            if (level.Robots.Count > 1)
            {
                issues.Add($"{level.Robots.Count} robots: at most one per level"); // MUTATION:ROBOT_COUNT
            }
            float radius = Tuning.RobotRadius;
            List<Rect> free = DiscFreeSpace(level, rooms, radius);
            for (int i = 0; i < level.Robots.Count; i++)
            {
                RobotDef robot = level.Robots[i];
                if (robot == null)
                {
                    continue;
                }
                string label = "robot " + (string.IsNullOrEmpty(robot.Name) ? "#" + (i + 1) : robot.Name);
                int n = robot.Loop != null ? robot.Loop.Count : 0;
                if (n < 2)
                {
                    issues.Add($"{label} has {n} waypoint{(n == 1 ? "" : "s")}: a loop needs at least 2");
                    continue;
                }
                if (robot.Loop.Exists(p => p == null))
                {
                    issues.Add($"{label} has an empty waypoint");
                    continue;
                }
                if (robot.Start < 0 || robot.Start >= n)
                {
                    issues.Add($"{label} start {robot.Start} is not a waypoint index (0 to {n - 1})");
                }
                if (robot.Speed < 0f)
                {
                    issues.Add($"{label} speed {robot.Speed} is negative (0 means the default {Tuning.RobotSpeed} m/s)");
                }
                // A loop of two waypoints goes there and back on one segment.
                int segments = n == 2 ? 1 : n;
                var drawn = new List<(Vector3 a, Vector3 b)>();
                for (int k = 0; k < segments; k++)
                {
                    int next = (k + 1) % n;
                    Vector3 a = robot.Loop[k].Position;
                    Vector3 b = robot.Loop[next].Position;
                    if ((b - a).magnitude < 1e-3f)
                    {
                        issues.Add($"{label} waypoints {k + 1} and {next + 1} coincide");
                        continue;
                    }
                    CheckRobotSegment(level, free, a, b, $"{label} segment {k + 1} (waypoint {k + 1} to {next + 1})", issues);
                    drawn.Add((a, b));
                }
                CheckRobotClearance(level, drawn, label, issues);
            }
        }

        private static void CheckRobotSegment(LevelDef level, List<Rect> free, Vector3 a, Vector3 b, string segment, List<string> issues)
        {
            float radius = Tuning.RobotRadius;
            if (!SegmentCovered(free, a, b)) // MUTATION:ROBOT_WALLS
            {
                issues.Add($"{segment} runs into a wall: the robot stays on the floor of the rooms and crosses walls through doorways without a leaf only");
            }
            foreach (PropDef prop in level.Props)
            {
                if (SegmentDistance(a, b, p => DistanceToRect(p, prop.Position, prop.SizeX, prop.SizeZ, prop.Yaw)) < radius - Eps)
                {
                    issues.Add($"{segment} touches prop {prop.Name}");
                }
            }
            for (int i = 0; i < level.Decoys.Count; i++)
            {
                DecoyDef d = level.Decoys[i];
                Vector3 size = level.DecoySize(d);
                if (SegmentDistance(a, b, p => DistanceToRect(p, d.Position, size.x, size.z, d.Yaw)) < radius - Eps)
                {
                    issues.Add($"{segment} touches decoy {i + 1}");
                }
            }
            if (level.Platforms != null)
            {
                foreach (PlatformDef pf in level.Platforms)
                {
                    if (pf != null && SegmentDistance(a, b, p => DistanceToRect(p, new Vector3(pf.X, 0f, pf.Z), pf.SizeX, pf.SizeZ, 0f)) < radius - Eps)
                    {
                        issues.Add($"{segment} leaves the floor level: it touches platform {pf.Name}"); // MUTATION:ROBOT_FLOOR
                    }
                }
            }
            if (level.Ramps != null)
            {
                for (int i = 0; i < level.Ramps.Count; i++)
                {
                    RampDef r = level.Ramps[i];
                    if (r != null && SegmentDistance(a, b, p => DistanceToRect(p, new Vector3(r.X, 0f, r.Z), r.Width, r.Length, r.Yaw)) < radius - Eps)
                    {
                        issues.Add($"{segment} leaves the floor level: it touches ramp {i + 1}");
                    }
                }
            }
            for (int k = 0; k < level.Doors.Count; k++)
            {
                OpeningDef door = level.Doors[k];
                if (door == null || !door.HasLeaf)
                {
                    continue;
                }
                var g = new DoorGeometry(level, door);
                if (!g.Valid)
                {
                    continue;
                }
                if (SegmentDistance(a, b, g.DistanceToSector) < radius - Eps)
                {
                    issues.Add($"{segment} enters the swing sector of door {k + 1} ({door.Id})"); // MUTATION:ROBOT_SECTOR
                }
                // Each pose on its own: the distance to one leaf is convex along the segment, the nearer of two is not.
                else if (Mathf.Min(SegmentDistance(a, b, p => g.DistanceToLeaf(p, 0f)), SegmentDistance(a, b, p => g.DistanceToLeaf(p, Tuning.DoorSwingDegrees)))
                    < radius - Eps)
                {
                    issues.Add($"{segment} touches the leaf of door {k + 1} ({door.Id})");
                }
            }
        }

        /// <summary>The loop's centre line keeps Tuning.RobotClearance from the spawn, every seat home and the exit zone.</summary>
        private static void CheckRobotClearance(LevelDef level, List<(Vector3 a, Vector3 b)> segments, string label, List<string> issues)
        {
            if (segments.Count == 0)
            {
                return;
            }
            float clearance = Tuning.RobotClearance;
            float Closest(System.Func<Vector3, float> distance)
            {
                float best = float.MaxValue;
                foreach ((Vector3 a, Vector3 b) in segments)
                {
                    best = Mathf.Min(best, SegmentDistance(a, b, distance));
                }
                return best;
            }
            if (level.Player != null)
            {
                Vector3 spawn = level.Player.Position;
                float d = Closest(p => YawMath.Planar(p - spawn).magnitude);
                if (d < clearance - Eps)
                {
                    issues.Add($"{label} passes {d:0.##} m from the player spawn: at least {clearance} m"); // MUTATION:ROBOT_CLEARANCE
                }
            }
            if (level.Exit != null)
            {
                ZoneDef e = level.Exit;
                float d = Closest(p => DistanceToRect(p, new Vector3(e.X, 0f, e.Z), e.SizeX, e.SizeZ, 0f));
                if (d < clearance - Eps)
                {
                    issues.Add($"{label} passes {d:0.##} m from the exit zone: at least {clearance} m");
                }
            }
            if (level.Inhabitants == null)
            {
                return;
            }
            foreach (InhabitantDef h in level.Inhabitants)
            {
                if (h?.Stations == null)
                {
                    continue;
                }
                for (int i = 0; i < h.Stations.Count; i++)
                {
                    SeatDef seat = h.Stations[i]?.Seat;
                    if (seat == null)
                    {
                        continue;
                    }
                    Vector3 home = seat.Position;
                    float d = Closest(p => YawMath.Planar(p - home).magnitude);
                    if (d < clearance - Eps)
                    {
                        issues.Add($"{label} passes {d:0.##} m from the seat home of inhabitant {h.Name} station {i + 1}: at least {clearance} m");
                    }
                }
            }
        }

        /// <summary>
        /// Where the centre of a disc of <paramref name="radius"/> may stand on the floor of the rooms, as axis aligned
        /// rectangles (x, z): every room interior shrunk by the radius, and through every doorway without a leaf between two
        /// rooms, a band of the doorway's width less the radius at each jamb, from one room's shrunk interior to the other's.
        /// An outer door leads out of the house and a doorway with a leaf is closed to the disc (its swing sector covers the
        /// doorway's mouth), so neither adds a band.
        /// </summary>
        public static List<Rect> DiscFreeSpace(LevelDef level, List<RoomDef> rooms, float radius)
        {
            var free = new List<Rect>();
            foreach (RoomDef r in rooms)
            {
                if (r != null && r.SizeX > 2f * radius && r.SizeZ > 2f * radius)
                {
                    free.Add(Rect.MinMaxRect(r.MinX + radius, r.MinZ + radius, r.MaxX - radius, r.MaxZ - radius));
                }
            }
            float t = level.WallThickness();
            foreach (OpeningDef door in level.Doors)
            {
                if (door == null || door.HasLeaf || door.Width <= 2f * radius)
                {
                    continue;
                }
                List<RoomSide> sides = level.SidesOf(door, out float along);
                if (sides.Count < 2)
                {
                    continue;
                }
                RoomSide s = sides[0];
                float from = along - door.Width * 0.5f + radius;
                float to = along + door.Width * 0.5f - radius;
                float low = s.Line - t * 0.5f - radius;
                float high = s.Line + t * 0.5f + radius;
                free.Add(s.AlongX ? Rect.MinMaxRect(from, low, to, high) : Rect.MinMaxRect(low, from, high, to));
            }
            return free;
        }

        /// <summary>True when every point of the planar segment from a to b lies in the union of the rectangles (x, z).</summary>
        public static bool SegmentCovered(List<Rect> rects, Vector3 a, Vector3 b)
        {
            var spans = new List<Vector2>();
            foreach (Rect r in rects)
            {
                if (ClipSegment(r, a, b, out float t0, out float t1))
                {
                    spans.Add(new Vector2(t0, t1));
                }
            }
            if (spans.Count == 0)
            {
                return false;
            }
            spans.Sort((x, y) => x.x.CompareTo(y.x));
            float length = YawMath.Planar(b - a).magnitude;
            float tolerance = length > Eps ? Eps / length : 1f;
            float reach = 0f;
            foreach (Vector2 s in spans)
            {
                if (s.x > reach + tolerance)
                {
                    return false;
                }
                reach = Mathf.Max(reach, s.y);
            }
            return reach >= 1f - tolerance;
        }

        /// <summary>Liang-Barsky: the parameter span [t0, t1] of the segment a + t (b - a), t in [0, 1], inside the rectangle.</summary>
        private static bool ClipSegment(Rect r, Vector3 a, Vector3 b, out float t0, out float t1)
        {
            t0 = 0f;
            t1 = 1f;
            float dx = b.x - a.x;
            float dz = b.z - a.z;
            return Clip(-dx, a.x - r.xMin, ref t0, ref t1) && Clip(dx, r.xMax - a.x, ref t0, ref t1)
                && Clip(-dz, a.z - r.yMin, ref t0, ref t1) && Clip(dz, r.yMax - a.z, ref t0, ref t1) && t0 <= t1;
        }

        /// <summary>One Liang-Barsky boundary: inside where p t &lt;= q (edges included, within Eps).</summary>
        private static bool Clip(float p, float q, ref float t0, ref float t1)
        {
            q += Eps;
            if (Mathf.Abs(p) < 1e-9f)
            {
                return q >= 0f;
            }
            float t = q / p;
            if (p < 0f)
            {
                if (t > t1)
                {
                    return false;
                }
                t0 = Mathf.Max(t0, t);
            }
            else
            {
                if (t < t0)
                {
                    return false;
                }
                t1 = Mathf.Min(t1, t);
            }
            return true;
        }

        /// <summary>
        /// The least value of a convex distance (to a convex set: a rectangle, a swing sector, a leaf, a point) along the
        /// planar segment from a to b: golden section search on the segment parameter, ends included.
        /// </summary>
        public static float SegmentDistance(Vector3 a, Vector3 b, System.Func<Vector3, float> distance)
        {
            const float ratio = 0.618034f;
            float lo = 0f;
            float hi = 1f;
            float x1 = hi - ratio * (hi - lo);
            float x2 = lo + ratio * (hi - lo);
            float f1 = distance(Vector3.Lerp(a, b, x1));
            float f2 = distance(Vector3.Lerp(a, b, x2));
            float best = Mathf.Min(Mathf.Min(f1, f2), Mathf.Min(distance(a), distance(b)));
            for (int i = 0; i < 40; i++)
            {
                if (f1 <= f2)
                {
                    hi = x2;
                    x2 = x1;
                    f2 = f1;
                    x1 = hi - ratio * (hi - lo);
                    f1 = distance(Vector3.Lerp(a, b, x1));
                    best = Mathf.Min(best, f1);
                }
                else
                {
                    lo = x1;
                    x1 = x2;
                    f1 = f2;
                    x2 = lo + ratio * (hi - lo);
                    f2 = distance(Vector3.Lerp(a, b, x2));
                    best = Mathf.Min(best, f2);
                }
            }
            return best;
        }

        /// <summary>The planar distance from a point to a rotated rectangle (centre, full sizes, yaw); 0 inside.</summary>
        public static float DistanceToRect(Vector3 point, Vector3 center, float sizeX, float sizeZ, float yawDeg)
        {
            Vector3 local = YawMath.Rotate(new Vector3(point.x - center.x, 0f, point.z - center.z), -yawDeg);
            float dx = Mathf.Max(0f, Mathf.Abs(local.x) - sizeX * 0.5f);
            float dz = Mathf.Max(0f, Mathf.Abs(local.z) - sizeZ * 0.5f);
            return Mathf.Sqrt(dx * dx + dz * dz);
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
