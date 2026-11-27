using System;

namespace PainterIO.Core
{
    /// <summary>Immutable, simple outline in simulation units. Its edges also drive the country ground mask.</summary>
    public sealed class ArenaPolygon
    {
        private readonly Vec2d[] vertices;
        private readonly Vec2d[] edges;
        private readonly double[] inverseLengthSquared;
        private readonly Vec2d interior;
        private readonly double winding;

        public ArenaPolygon(Vec2d[] outline, Vec2d interior)
        {
            if (outline == null || outline.Length < 3)
                throw new ArgumentException("A country needs at least three vertices.", nameof(outline));

            vertices = (Vec2d[])outline.Clone();
            edges = new Vec2d[vertices.Length];
            inverseLengthSquared = new double[vertices.Length];
            this.interior = interior;
            double area2 = 0;
            for (int i = 0; i < vertices.Length; i++)
            {
                Vec2d next = vertices[(i + 1) % vertices.Length];
                area2 += Vec2d.Cross(vertices[i], next);
                edges[i] = next - vertices[i];
                inverseLengthSquared[i] = 1.0 / edges[i].LengthSq;
                if (double.IsInfinity(inverseLengthSquared[i]))
                    throw new ArgumentException("Duplicate consecutive vertices.", nameof(outline));
            }
            Area = Math.Abs(area2) * 0.5;
            winding = Math.Sign(area2);
            if (Area <= 0 || Distance(interior, out _) >= 0)
                throw new ArgumentException("A country needs a point strictly inside its outline.", nameof(interior));
        }

        public double Area { get; }

        public bool Contains(Vec2d point)
        {
            bool inside = false;
            for (int i = 0; i < vertices.Length; i++)
            {
                Vec2d a = vertices[i];
                Vec2d b = vertices[(i + 1) % vertices.Length];
                if (point == a) return true;
                if (a.Y == b.Y)
                {
                    if (point.Y == a.Y && point.X >= Math.Min(a.X, b.X) && point.X <= Math.Max(a.X, b.X))
                        return true;
                    continue;
                }
                if ((a.Y > point.Y) == (b.Y > point.Y)) continue;
                double x = a.X + (point.Y - a.Y) * edges[i].X / edges[i].Y;
                if (point.X == x) return true;
                if (point.X < x) inside = !inside;
            }
            return inside;
        }

        public double Distance(Vec2d point, out Vec2d outward)
        {
            bool inside = false;
            double nearest = double.PositiveInfinity;
            int nearestEdge = 0;
            Vec2d difference = Vec2d.Zero;
            for (int i = 0; i < vertices.Length; i++)
            {
                Vec2d a = vertices[i];
                Vec2d b = vertices[(i + 1) % vertices.Length];
                Vec2d edge = edges[i];
                if ((a.Y > point.Y) != (b.Y > point.Y) &&
                    point.X < a.X + (point.Y - a.Y) * edge.X / edge.Y)
                    inside = !inside;

                double along = Vec2d.Dot(point - a, edge) * inverseLengthSquared[i];
                Vec2d delta = point - (a + edge * Math.Max(0, Math.Min(1, along)));
                double squared = delta.LengthSq;
                if (squared >= nearest) continue;
                nearest = squared;
                nearestEdge = i;
                difference = delta;
            }
            double distance = Math.Sqrt(nearest);
            if (distance <= 1e-10) outward = edges[nearestEdge].Perp().Normalized() * -winding;
            else outward = difference / (inside ? -distance : distance);
            return inside ? -distance : distance;
        }

        public Vec2d ClampInside(Vec2d point, double margin)
        {
            double distance = Distance(point, out Vec2d normal);
            if (distance <= -margin) return point;
            Vec2d projected = point - normal * (distance + margin + 0.00001);
            if (Distance(projected, out _) <= -margin) return projected;
            return StopBeforeBorder(interior, point, margin);
        }

        public Vec2d Step(Vec2d start, Vec2d delta, double margin, double holdAngle)
        {
            if (Distance(start, out _) > -margin) start = ClampInside(start, margin);
            Vec2d end = start + delta;
            Vec2d direct = StopBeforeBorder(start, end, margin);
            if (direct == end) return end;

            Distance(direct, out Vec2d normal);
            if (Vec2d.Dot(delta.Normalized(), normal) > Math.Cos(holdAngle)) return direct;
            Vec2d tangent = normal.Perp();
            double along = Vec2d.Dot(delta, tangent);
            double remaining = delta.Length - Vec2d.Distance(start, direct);
            Vec2d slide = tangent * (Math.Sign(along) * remaining);
            Vec2d target = StopBeforeBorder(start, direct + slide, margin);
            return Vec2d.Distance(start, target) > Vec2d.Distance(start, direct) ? target : direct;
        }

        private Vec2d StopBeforeBorder(Vec2d start, Vec2d end, double margin)
        {
            Vec2d delta = end - start;
            double length = delta.Length;
            if (length <= 1e-10) return start;
            double travelled = 0;
            Vec2d safe = start;
            // The signed distance bounds each step, even when the final point is across a narrow inlet.
            for (int i = 0; i < 48; i++)
            {
                double clearance = -Distance(safe, out _) - margin;
                if (clearance >= length - travelled) return end;
                double step = Math.Max(clearance * 0.9, 0.0001);
                travelled = Math.Min(length, travelled + step);
                Vec2d next = Vec2d.Lerp(start, end, travelled / length);
                if (Distance(next, out _) > -margin) break;
                if (travelled >= length) return end;
                safe = next;
            }
            return safe;
        }
    }
}
