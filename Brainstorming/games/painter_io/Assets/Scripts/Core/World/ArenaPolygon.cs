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

        /// <summary>
        /// Smallest step of StopBeforeBorder (u). Rule v1.7 fix: it was 1e-4, so a head sliding along the border (clearance
        /// about 0) advanced 48 x 1e-4 u per tick, about 0.3 u/s instead of PawnSpeed, and the rim of a country could hardly
        /// be painted. 0.01 u is far below the 2 x margin a step would need to skip over an inlet, and a step that would leave
        /// the inset shape is still refused (the head then stops at most this far before the inset line).
        /// </summary>
        public const double MinBorderStep = 0.01;

        /// <summary>Rule v1.9 border ride: an edge whose distance is within margin + this (u) constrains the riding tangent.</summary>
        public const double RideActiveTolerance = 0.02;

        /// <summary>Rule v1.9 border ride: the ride keeps the head this far (u) inside the inset line.</summary>
        public const double RideBias = 1e-6;

        /// <summary>
        /// Rule v1.9 (contract 33, Arena.FollowBorder): moves along the inset line {Distance = -margin} for 'length' (u) in the
        /// direction sign x outward.Perp(). Each sub-step takes the tangent of one ACTIVE edge (within margin +
        /// RideActiveTolerance): the one that points least into the other active edges, so at a convex vertex (a pocket,
        /// where a plain slide is held) the head turns onto the next edge instead of pushing into it, and around a reflex
        /// vertex the nearest feature is the vertex itself and the head follows the arc of radius margin around it. The
        /// sub-step end is projected back onto the line (RideBias inside); a projection that cannot get inside falls back to
        /// StopBeforeBorder, so the result is always in the inset shape. A ride that makes no progress for four sub-steps in
        /// a row (a dead end narrower than the head) stops there.
        /// </summary>
        public Vec2d Follow(Vec2d start, double length, int sign, double margin, out Vec2d direction)
        {
            double s = sign < 0 ? -1.0 : 1.0;
            Vec2d q = OntoRideLine(start, start, margin);
            direction = RideTangent(q, s, margin);
            if (!(length > 0.0)) return q;
            int steps = (int)Math.Ceiling(length / Arena.RideSubStep);
            if (steps < 1) steps = 1;
            if (steps > Arena.RideMaxSubSteps) steps = Arena.RideMaxSubSteps;
            double h = length / steps;
            int stalled = 0;
            for (int k = 0; k < steps; k++)
            {
                Vec2d t = RideTangent(q, s, margin);
                if (t.LengthSq == 0.0) break;
                direction = t;
                Vec2d c = OntoRideLine(q + t * h, q, margin);
                bool slow = Vec2d.Distance(q, c) < 0.25 * h;
                q = c;
                if (!slow) stalled = 0;
                else if (++stalled >= 4) break;
            }
            return q;
        }

        /// <summary>
        /// Rule v1.9: the riding tangent at q (unit, or zero when no edge is near). Among the edges within margin +
        /// RideActiveTolerance of q, each gives the outward normal n_i (toward its closest point) and the tangent t_i =
        /// sign x n_i.Perp(); the tangent with the smallest max_j dot(t_i, n_j) wins (it does not push into any active edge),
        /// ties to the nearest edge.
        /// </summary>
        private Vec2d RideTangent(Vec2d q, double s, double margin)
        {
            Span<Vec2d> normals = stackalloc Vec2d[8];
            Span<double> dists = stackalloc double[8];
            int count = 0;
            double limit = margin + RideActiveTolerance;
            for (int i = 0; i < vertices.Length && count < 8; i++)
            {
                Vec2d a = vertices[i];
                double along = Vec2d.Dot(q - a, edges[i]) * inverseLengthSquared[i];
                Vec2d closest = a + edges[i] * Math.Max(0, Math.Min(1, along));
                Vec2d toward = closest - q;
                double d = toward.Length;
                if (!(d <= limit) || d <= 1e-12) continue;
                normals[count] = toward / d;
                dists[count] = d;
                count++;
            }
            if (count == 0)
            {
                Distance(q, out Vec2d outward);
                return outward.Perp() * s;
            }
            int best = 0;
            double bestScore = double.PositiveInfinity;
            for (int i = 0; i < count; i++)
            {
                Vec2d t = normals[i].Perp() * s;
                double score = double.NegativeInfinity;
                for (int j = 0; j < count; j++)
                {
                    if (j == i) continue;
                    double push = Vec2d.Dot(t, normals[j]);
                    if (push > score) score = push;
                }
                if (score == double.NegativeInfinity) score = 0.0;
                if (score < bestScore - 1e-9 || (Math.Abs(score - bestScore) <= 1e-9 && dists[i] < dists[best]))
                {
                    bestScore = score;
                    best = i;
                }
            }
            return normals[best].Perp() * s;
        }

        /// <summary>
        /// Rule v1.9: projects p onto the inset line (RideBias inside) along the nearest feature's normal, a few times (two
        /// lines meeting at a convex vertex are reached by alternating projections); if the point is still outside the
        /// inset shape, StopBeforeBorder from 'from' (inside) keeps it inside.
        /// </summary>
        private Vec2d OntoRideLine(Vec2d p, Vec2d from, double margin)
        {
            Vec2d c = p;
            for (int k = 0; k < 6; k++)
            {
                double d = Distance(c, out Vec2d outward);
                double f = d + margin + RideBias;
                if (Math.Abs(f) <= 1e-12) break;
                c = c - outward * f;
            }
            if (Distance(c, out _) <= -margin) return c;
            if (Distance(from, out _) > -margin) return ClampInside(c, margin);
            return StopBeforeBorder(from, c, margin);
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
                double step = Math.Max(clearance * 0.9, MinBorderStep);
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
