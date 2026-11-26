using System.Collections.Generic;
using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5_v3.md 3 and 15.2): the geometry of a door leaf, shared by DoorLeaf, the validator, the level
    /// builder's NavMesh areas and the audit.
    /// <list type="bullet">
    /// <item>The hinge stands on the wall's centre line at one end of the opening: "start" (the default) is the end with
    /// the lower world coordinate along the wall, "end" the other one.</item>
    /// <item>Closed (0 deg), the leaf fills the opening, centred on the wall line, <see cref="Tuning.LeafThickness"/>
    /// thick. It swings about the hinge into the room named by <see cref="OpeningDef.Swing"/>, up to
    /// <see cref="Tuning.DoorSwingDegrees"/> (open: perpendicular to the wall, against the end of the opening).</item>
    /// <item>The swing sector is the quarter disc of radius the opening width, centred on the hinge, between the closed
    /// and the open pose, in the swing room.</item>
    /// <item>Every height adds the floor height at the door centre (a platform never stands over a threshold, so it is
    /// 0 in a valid level).</item>
    /// </list>
    /// </summary>
    public sealed class DoorGeometry
    {
        public readonly OpeningDef Door;
        public readonly LevelDef Level;

        /// <summary>False when the door lies on no wall (an invalid level): the frame then defaults to the door point.</summary>
        public readonly bool Valid;
        /// <summary>The wall runs along x (a z wall).</summary>
        public readonly bool AlongX;
        /// <summary>The wall's centre line coordinate (z for a z wall, x for an x wall).</summary>
        public readonly float Line;
        /// <summary>The opening centre's coordinate along the wall.</summary>
        public readonly float Along;
        /// <summary>The hinge, on the wall line, at the floor (planar).</summary>
        public readonly Vector3 Hinge;
        /// <summary>From the hinge toward the free end of the closed leaf, along the wall (planar unit vector).</summary>
        public readonly Vector3 AlongDirection;
        /// <summary>The normal of the wall pointing into the swing room (planar unit vector).</summary>
        public readonly Vector3 Into;
        /// <summary>The swing room's index in <see cref="LevelDef.AllRooms"/>, or -1.</summary>
        public readonly int SwingRoom;
        /// <summary>The wall thickness of the level.</summary>
        public readonly float WallThickness;
        /// <summary>The floor height under the door centre.</summary>
        public readonly float FloorY;

        private const float Eps = 1e-4f;

        public DoorGeometry(LevelDef level, OpeningDef door)
        {
            Level = level;
            Door = door;
            SwingRoom = -1;
            List<RoomSide> sides = level != null && door != null ? level.SidesOf(door, out Along) : new List<RoomSide>();
            WallThickness = level != null ? level.WallThickness() : 0f;
            if (sides.Count == 0)
            {
                Valid = false;
                AlongX = true;
                Line = door != null ? door.Z : 0f;
                Along = door != null ? door.X : 0f;
                Hinge = new Vector3(Along - Width * 0.5f, 0f, Line);
                AlongDirection = Vector3.right;
                Into = Vector3.forward;
                FloorY = 0f;
                return;
            }
            Valid = true;
            RoomSide swing = sides[0];
            List<RoomDef> rooms = level.AllRooms();
            foreach (RoomSide s in sides)
            {
                if (door.Swing != null && rooms[s.Room].Id == door.Swing)
                {
                    swing = s;
                    SwingRoom = s.Room;
                }
            }
            if (SwingRoom < 0 && door.Swing == null && sides.Count == 1)
            {
                SwingRoom = sides[0].Room;
            }
            AlongX = swing.AlongX;
            Line = swing.Line;
            Vector3 axis = AlongX ? Vector3.right : Vector3.forward;
            Vector3 normal = AlongX ? Vector3.forward : Vector3.right;
            // Outward is +1 when the room lies toward lower coordinates: its interior is on the -normal side.
            Into = normal * -swing.Outward;
            bool end = door.Hinge == OpeningDef.HingeEnd;
            float hingeAlong = end ? Along + Width * 0.5f : Along - Width * 0.5f;
            Hinge = AlongX ? new Vector3(hingeAlong, 0f, Line) : new Vector3(Line, 0f, hingeAlong);
            AlongDirection = end ? -axis : axis;
            Vector3 c = Center;
            FloorY = level.FloorHeightAt(c.x, c.z);
        }

        /// <summary>The opening width (the leaf length and the swing radius).</summary>
        public float Width => Door != null ? Door.Width : 0f;

        /// <summary>The bottom of the leaf above the floor (the opening's bottom).</summary>
        public float Bottom => Door != null ? Door.Bottom : 0f;

        /// <summary>The leaf height: the opening's height less <see cref="Tuning.LeafTopGap"/>.</summary>
        public float LeafHeight => Door != null ? Mathf.Max(0f, Door.Top - Door.Bottom - Tuning.LeafTopGap) : 0f;

        /// <summary>The centre of the doorway, on the wall line, at the floor height.</summary>
        public Vector3 Center => AlongX ? new Vector3(Along, FloorY, Line) : new Vector3(Line, FloorY, Along);

        /// <summary>The planar direction of the leaf, from the hinge to its free end, at a swing angle.</summary>
        public Vector3 Direction(float swingDegrees)
        {
            float r = swingDegrees * Mathf.Deg2Rad;
            return AlongDirection * Mathf.Cos(r) + Into * Mathf.Sin(r);
        }

        /// <summary>
        /// The leaf box at a swing angle: its centre and rotation (local +x from the hinge to the free end, +y up, +z the
        /// leaf's normal), and <paramref name="size"/> (width, height, thickness). DoorLeaf's transform is this pose, its
        /// collider and visual are centred on it.
        /// </summary>
        public Pose Pose(float swingDegrees, out Vector3 size)
        {
            Vector3 d = Direction(swingDegrees);
            size = new Vector3(Width, LeafHeight, Tuning.LeafThickness);
            Vector3 c = Hinge + d * (Width * 0.5f);
            c.y = FloorY + Bottom + LeafHeight * 0.5f;
            return new Pose(c, Quaternion.Euler(0f, YawOfAxisX(d), 0f));
        }

        /// <summary>The yaw whose rotation turns local +x into the planar direction <paramref name="d"/>.</summary>
        public static float YawOfAxisX(Vector3 d)
        {
            return Mathf.Atan2(-d.z, d.x) * Mathf.Rad2Deg;
        }

        /// <summary>
        /// The leaf's sample points at a swing angle (<see cref="Tuning.LeafSampleCount"/>): the corners of the leaf's mid
        /// plane, inset by <see cref="Tuning.LeafSampleInset"/>: near the hinge low and high, then at the free end low and high.
        /// </summary>
        public Vector3[] Samples(float swingDegrees)
        {
            var samples = new Vector3[Tuning.LeafSampleCount];
            Samples(swingDegrees, samples);
            return samples;
        }

        /// <summary><see cref="Samples(float)"/> into a buffer of at least <see cref="Tuning.LeafSampleCount"/> points.</summary>
        public void Samples(float swingDegrees, Vector3[] into)
        {
            float inset = Tuning.LeafSampleInset;
            Vector3 d = Direction(swingDegrees);
            float low = FloorY + Bottom + inset;
            float high = FloorY + Bottom + LeafHeight - inset;
            Vector3 near = Hinge + d * inset;
            Vector3 far = Hinge + d * (Width - inset);
            into[0] = new Vector3(near.x, low, near.z);
            into[1] = new Vector3(near.x, high, near.z);
            into[2] = new Vector3(far.x, low, far.z);
            into[3] = new Vector3(far.x, high, far.z);
        }

        // ----- The swing sector -----

        /// <summary>The planar coordinates of a point in the hinge frame: (along the closed leaf, into the swing room).</summary>
        private Vector2 Local(Vector3 p)
        {
            Vector3 d = YawMath.Planar(p - Hinge);
            return new Vector2(Vector3.Dot(d, AlongDirection), Vector3.Dot(d, Into));
        }

        /// <summary>True when a planar point lies in the quarter disc the leaf sweeps (edges included).</summary>
        public bool InSwingSector(Vector3 point)
        {
            Vector2 l = Local(point);
            return l.x >= -Eps && l.y >= -Eps && l.sqrMagnitude <= Width * Width + Eps;
        }

        /// <summary>The planar distance from a point to the swing sector (0 inside).</summary>
        public float DistanceToSector(Vector3 point)
        {
            return DistanceToQuarterDisc(Local(point), Width);
        }

        private static float DistanceToQuarterDisc(Vector2 p, float radius)
        {
            if (p.x >= 0f && p.y >= 0f)
            {
                return Mathf.Max(0f, p.magnitude - radius);
            }
            if (p.x < 0f && p.y >= 0f)
            {
                return new Vector2(p.x, p.y - Mathf.Clamp(p.y, 0f, radius)).magnitude;
            }
            if (p.y < 0f && p.x >= 0f)
            {
                return new Vector2(p.x - Mathf.Clamp(p.x, 0f, radius), p.y).magnitude;
            }
            return p.magnitude;
        }

        /// <summary>True when a disc (a station's inhabitant, a seat) overlaps the swing sector (touching does not).</summary>
        public bool SectorOverlapsDisc(Vector3 center, float radius)
        {
            return DistanceToSector(center) < radius - Eps;
        }

        /// <summary>
        /// True when a rectangle footprint (centre, full sizes, yaw) overlaps the swing sector with a positive area: the
        /// rectangle clipped to the sector's quadrant, then its distance to the hinge against the radius. Touching does not.
        /// </summary>
        public bool SectorOverlapsRect(Vector3 center, float sizeX, float sizeZ, float yawDeg)
        {
            var polygon = new List<Vector2>(8);
            for (int k = 0; k < 4; k++)
            {
                float sx = k == 0 || k == 3 ? -0.5f : 0.5f;
                float sz = k < 2 ? -0.5f : 0.5f;
                Vector3 corner = center + YawMath.Rotate(new Vector3(sx * sizeX, 0f, sz * sizeZ), yawDeg);
                polygon.Add(Local(corner));
            }
            polygon = Clip(polygon, 0);
            polygon = Clip(polygon, 1);
            if (polygon.Count < 3 || Mathf.Abs(Area(polygon)) < 1e-6f)
            {
                return false;
            }
            return DistanceToPolygon(polygon) < Width - Eps;
        }

        /// <summary>Sutherland-Hodgman clip of a convex polygon to the half plane where coordinate <paramref name="axis"/> is >= 0.</summary>
        private static List<Vector2> Clip(List<Vector2> polygon, int axis)
        {
            var result = new List<Vector2>(polygon.Count + 2);
            for (int i = 0; i < polygon.Count; i++)
            {
                Vector2 a = polygon[i];
                Vector2 b = polygon[(i + 1) % polygon.Count];
                bool ina = a[axis] >= 0f;
                bool inb = b[axis] >= 0f;
                if (ina)
                {
                    result.Add(a);
                }
                if (ina != inb)
                {
                    float t = a[axis] / (a[axis] - b[axis]);
                    result.Add(a + (b - a) * t);
                }
            }
            return result;
        }

        private static float Area(List<Vector2> polygon)
        {
            float area = 0f;
            for (int i = 0; i < polygon.Count; i++)
            {
                Vector2 a = polygon[i];
                Vector2 b = polygon[(i + 1) % polygon.Count];
                area += a.x * b.y - b.x * a.y;
            }
            return area * 0.5f;
        }

        /// <summary>The distance from the origin (the hinge) to a convex polygon: 0 when it contains the origin.</summary>
        private static float DistanceToPolygon(List<Vector2> polygon)
        {
            bool inside = true;
            float sign = Mathf.Sign(Area(polygon));
            float best = float.MaxValue;
            for (int i = 0; i < polygon.Count; i++)
            {
                Vector2 a = polygon[i];
                Vector2 b = polygon[(i + 1) % polygon.Count];
                // The origin is on the inner side of every edge of a convex polygon that contains it.
                if ((a.x * b.y - b.x * a.y) * sign < 0f)
                {
                    inside = false;
                }
                best = Mathf.Min(best, DistanceToSegment(Vector2.zero, a, b));
            }
            return inside ? 0f : best;
        }

        private static float DistanceToSegment(Vector2 p, Vector2 a, Vector2 b)
        {
            Vector2 ab = b - a;
            float len = ab.sqrMagnitude;
            float t = len > 1e-12f ? Mathf.Clamp01(Vector2.Dot(p - a, ab) / len) : 0f;
            return (p - (a + ab * t)).magnitude;
        }

        // ----- Reach -----

        /// <summary>
        /// CONTRACT_M5_v3 15.2: the chair's planar centre is within <see cref="Tuning.DoorReach"/> of the door centre, and
        /// its footprint (full sizes, at its yaw) is outside the swing sector. No facing condition.
        /// </summary>
        public bool InReach(Vector3 chairCenter, Vector3 footprintSize, float yaw)
        {
            if (!Valid)
            {
                return false;
            }
            float distance = YawMath.Planar(chairCenter - Center).magnitude;
            return distance <= Tuning.DoorReach + Eps && !SectorOverlapsRect(chairCenter, footprintSize.x, footprintSize.z, yaw);
        }

        // ----- The open leaf and the NavMesh boxes (CONTRACT_M5_v3 15.1) -----

        /// <summary>
        /// The planar distance from a point to the leaf's footprint at a swing angle (its centre segment, less half its
        /// thickness; 0 when the point is in the leaf). The audit can block the cells an open leaf touches with it.
        /// </summary>
        public float DistanceToLeaf(Vector3 point, float swingDegrees)
        {
            Vector3 d = Direction(swingDegrees);
            Vector3 p = YawMath.Planar(point);
            Vector3 a = YawMath.Planar(Hinge);
            Vector2 local = new Vector2(p.x - a.x, p.z - a.z);
            float distance = DistanceToSegment(local, Vector2.zero, new Vector2(d.x, d.z) * Width);
            return Mathf.Max(0f, distance - Tuning.LeafThickness * 0.5f);
        }

        /// <summary>
        /// The NavMesh area box of the doorway (CONTRACT_M5_v3 15.1): the opening's width along the wall, the wall thickness
        /// plus <see cref="Tuning.DoorAreaOverhang"/> on each face across it, from below the floor to above it.
        /// </summary>
        public void DoorwayBox(out Vector3 center, out Quaternion rotation, out Vector3 size)
        {
            center = Center + Vector3.up * NavBoxMid;
            rotation = Quaternion.Euler(0f, YawOfAxisX(AlongX ? Vector3.right : Vector3.forward), 0f);
            size = new Vector3(Width, NavBoxHeight, WallThickness + 2f * Tuning.DoorAreaOverhang);
        }

        /// <summary>
        /// The Not Walkable NavMesh box of the leaf's open pose (CONTRACT_M5_v3 15.1: no path ever crosses an open leaf): the
        /// open leaf's footprint grown by the agent radius, from the wall face into the swing room, so the doorway itself
        /// keeps its door area and stays passable.
        /// </summary>
        public void OpenLeafBox(out Vector3 center, out Quaternion rotation, out Vector3 size)
        {
            float r = Tuning.NavAgentRadius;
            float from = WallThickness * 0.5f;
            float to = Width + r;
            Vector3 planar = Hinge + Into * ((from + to) * 0.5f);
            center = new Vector3(planar.x, FloorY + NavBoxMid, planar.z);
            rotation = Quaternion.Euler(0f, YawOfAxisX(AlongDirection), 0f);
            size = new Vector3(Tuning.LeafThickness + 2f * r, NavBoxHeight, Mathf.Max(0.01f, to - from));
        }

        // The NavMesh boxes reach from 0.5 m below the floor to 1 m above it: they hold the walkable surface whatever the
        // voxel heights.
        private const float NavBoxMid = 0.25f;
        private const float NavBoxHeight = 1.5f;
    }
}
