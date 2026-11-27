using System;

namespace PainterIO.Core
{
    /// <summary>
    /// The play area (R1): a rounded square of half size HalfSize and corner radius CornerRadius centered on the origin.
    /// Head centers live in the inset shape {SignedDistance &lt;= -Margin} (R1, R4).
    /// </summary>
    public sealed class Arena
    {
        /// <summary>
        /// ClampInside lands this far inside the inset boundary so that SignedDistance(result) &lt;= -Margin holds
        /// despite rounding (about 150 ulps at |p| = 32, far below anything visible).
        /// </summary>
        public const double ClampBias = 1e-12;

        private readonly double innerHalf;   // half size of the straight part: HalfSize - CornerRadius
        private readonly double insetBox;    // the inset shape is the box [-insetBox, insetBox]^2 grown by insetRadius
        private readonly double insetRadius;
        private readonly ArenaPolygon polygon;

        public Arena(double halfSize, double cornerRadius, double margin, ArenaPolygon polygon = null)
        {
            if (!(halfSize > 0.0)) throw new ArgumentOutOfRangeException(nameof(halfSize), "must be > 0");
            if (!(cornerRadius >= 0.0 && cornerRadius <= halfSize))
                throw new ArgumentOutOfRangeException(nameof(cornerRadius), "must be in [0, halfSize]");
            if (!(margin >= 0.0 && margin < halfSize))
                throw new ArgumentOutOfRangeException(nameof(margin), "must be in [0, halfSize)");

            HalfSize = halfSize;
            CornerRadius = cornerRadius;
            Margin = margin;
            this.polygon = polygon;
            innerHalf = halfSize - cornerRadius;
            // {sd <= -m} of a rounded box is the same box with radius r - m while m <= r, else a sharp square of
            // half size h - m (the corner arcs vanish).
            if (margin <= cornerRadius)
            {
                insetBox = innerHalf;
                insetRadius = cornerRadius - margin;
            }
            else
            {
                insetBox = halfSize - margin;
                insetRadius = 0.0;
            }
            ShapeArea = polygon?.Area ?? (4.0 * halfSize * halfSize - (4.0 - Math.PI) * cornerRadius * cornerRadius);
        }

        public double HalfSize { get; }
        public double CornerRadius { get; }
        public double Margin { get; }
        public ArenaPolygon Polygon => polygon;

        /// <summary>Analytic area of the full shape: (2h)^2 - (4 - pi) r^2.</summary>
        public double ShapeArea { get; }

        /// <summary>Exact signed distance to the rounded square: negative inside, 0 on the rim, positive outside.</summary>
        public double SignedDistance(Vec2d p)
        {
            if (polygon != null) return polygon.Distance(p, out _);
            double qx = Math.Abs(p.X) - innerHalf;
            double qy = Math.Abs(p.Y) - innerHalf;
            double ox = qx > 0.0 ? qx : 0.0;
            double oy = qy > 0.0 ? qy : 0.0;
            double inside = Math.Min(Math.Max(qx, qy), 0.0);
            return Math.Sqrt(ox * ox + oy * oy) + inside - CornerRadius;
        }

        /// <summary>True when p lies in the full shape (rim included): SignedDistance(p) &lt;= 0.</summary>
        public bool Contains(Vec2d p) => polygon != null ? polygon.Contains(p) : SignedDistance(p) <= 0.0;

        /// <summary>
        /// Unit gradient of the SDF: radial from the corner arc center in a corner region, otherwise the axis of the
        /// nearest side. Where the gradient is undefined (diagonal inside the straight part, center) the x axis wins
        /// and a zero coordinate counts as positive, so the result is always a unit vector.
        /// </summary>
        public Vec2d OutwardNormal(Vec2d p)
        {
            if (polygon != null)
            {
                polygon.Distance(p, out Vec2d normal);
                return normal;
            }
            double sx = p.X >= 0.0 ? 1.0 : -1.0;
            double sy = p.Y >= 0.0 ? 1.0 : -1.0;
            double qx = Math.Abs(p.X) - innerHalf;
            double qy = Math.Abs(p.Y) - innerHalf;
            if (qx > 0.0 && qy > 0.0)
            {
                double len = Math.Sqrt(qx * qx + qy * qy);
                return new Vec2d(sx * qx / len, sy * qy / len);
            }
            return qx >= qy ? new Vec2d(sx, 0.0) : new Vec2d(0.0, sy);
        }

        /// <summary>
        /// Nearest point of the inset shape {SignedDistance &lt;= -Margin}: p itself when already there, otherwise the
        /// projection onto the inset rounded box, landing ClampBias inside its boundary.
        /// </summary>
        public Vec2d ClampInside(Vec2d p)
        {
            if (SignedDistance(p) <= -Margin) return p;
            if (polygon != null) return polygon.ClampInside(p, Margin);
            if (insetRadius > ClampBias)
            {
                // Outside the inset rounded box means outside its inner box, so v is never zero here.
                double cx = Clamp(p.X, -insetBox, insetBox);
                double cy = Clamp(p.Y, -insetBox, insetBox);
                double vx = p.X - cx, vy = p.Y - cy;
                double len = Math.Sqrt(vx * vx + vy * vy);
                if (len > 0.0)
                {
                    double k = (insetRadius - ClampBias) / len;
                    return new Vec2d(cx + vx * k, cy + vy * k);
                }
                return new Vec2d(cx, cy);
            }
            // Sharp (or nearly sharp) inset square: clamp to the box shrunk by the bias.
            double b = insetBox + insetRadius - ClampBias;
            return new Vec2d(Clamp(p.X, -b, b), Clamp(p.Y, -b, b));
        }

        /// <summary>
        /// A held head whose start lies this close to the inset line (SignedDistance + Margin >= -HoldSnap) is already
        /// on it and stays exactly where it is (contract 23.2 D3). Larger than ClampBias, so a point that ClampInside or a
        /// previous hold put on the line counts as on it; far below the 1e-9 u tolerance of D3.
        /// </summary>
        public const double HoldSnap = 1e-11;

        /// <summary>
        /// R4 border motion. p1 = p0 + d when that stays in the inset shape. Otherwise, with n the outward normal at
        /// p0 + d: if the angle between d and n is below holdAngleRad the head is held; else d is projected onto the
        /// border tangent, rescaled to the full step length |d|, and the result is clamped inside (on a corner arc this
        /// makes the head follow the arc). A push with no tangent component (exactly along n) is held too.
        /// Hold (contract 23.2 D3): before holding, the head advances along d up to the inset line, so a held head stops
        /// on the inset line whatever the tick rate (within 1e-9 u), and a head already on the line stays exactly in
        /// place on the following ticks. A start outside the inset shape moving inward is simply clamped (it cannot
        /// happen in a round; it keeps DebugSetTrail states sane).
        /// </summary>
        public Vec2d Step(Vec2d p0, Vec2d d, double holdAngleRad)
        {
            if (polygon != null) return polygon.Step(p0, d, Margin, holdAngleRad);
            Vec2d p1 = p0 + d;
            if (SignedDistance(p1) <= -Margin) return p1;

            double len = d.Length;
            if (!(len > 0.0)) return ClampInside(p0);

            Vec2d n = OutwardNormal(p1);
            double cosAngle = Vec2d.Dot(d, n) / len;
            // From inside the inset shape, leaving it implies d.n > 0 (convexity); d.n <= 0 means p0 was outside.
            if (cosAngle <= 0.0) return ClampInside(p1);
            // angle < hold  <=>  cos(angle) > cos(hold) for angles in [0, pi]; hold = 0 never holds.
            if (cosAngle > Math.Cos(holdAngleRad)) return HoldPoint(p0, d);

            Vec2d tangent = n.Perp();
            double along = Vec2d.Dot(d, tangent);
            if (along == 0.0) return HoldPoint(p0, d);
            Vec2d slid = p0 + tangent * (along > 0.0 ? len : -len);
            return ClampInside(slid);
        }

        /// <summary>
        /// D3 hold point: where the segment p0 + t d (t in [0, 1]) reaches the inset line. Called only when p0 + d is
        /// outside the inset shape, so f(t) = SignedDistance(p0 + t d) + Margin has f(1) > 0; f is convex in t (the
        /// inset shape is convex), so with f(0) &lt;= 0 the root is unique. Bisection on t keeps the last evaluated point
        /// with f &lt;= 0, so the result is inside the inset shape as computed (no clamp needed) and within rounding of
        /// the line. Deterministic (fixed iteration rule, doubles only).
        /// </summary>
        private Vec2d HoldPoint(Vec2d p0, Vec2d d)
        {
            double f0 = SignedDistance(p0) + Margin;
            if (f0 > 0.0) return ClampInside(p0);   // start outside the inset shape (DebugSetTrail states)
            if (f0 >= -HoldSnap) return p0;          // already on the inset line: stay exactly in place
            double lo = 0.0, hi = 1.0;
            Vec2d best = p0;
            for (int k = 0; k < 64; k++)
            {
                double mid = 0.5 * (lo + hi);
                if (!(mid > lo && mid < hi)) break;  // the interval cannot shrink any further in doubles
                Vec2d q = p0 + d * mid;
                if (SignedDistance(q) + Margin <= 0.0)
                {
                    lo = mid;
                    best = q;
                }
                else
                {
                    hi = mid;
                }
            }
            return best;
        }

        /// <summary>Rule v1.9 border ride: longest sub-step (u) of FollowBorder (the requested length is split evenly).</summary>
        public const double RideSubStep = 0.05;

        /// <summary>Rule v1.9 border ride: most sub-steps of one FollowBorder call (longer moves use longer sub-steps).</summary>
        public const int RideMaxSubSteps = 64;

        /// <summary>
        /// Rule v1.9 (contract 33) border ride motion: moves a head that lies on (or within the contact tolerance of) the
        /// inset line {SignedDistance = -Margin} along that line for 'length' (u), in the direction sign x OutwardNormal.Perp()
        /// (sign +1 or -1), around every corner: the rounded corners of the classic square, and on a country polygon both the
        /// convex vertices (where the head would be held) and the reflex ones (ArenaPolygon.Follow). The result is in the
        /// inset shape. direction = the unit tangent of the last sub-step (the riding heading). Deterministic, doubles only.
        /// </summary>
        public Vec2d FollowBorder(Vec2d p, double length, int sign, out Vec2d direction)
        {
            if (polygon != null) return polygon.Follow(p, length, sign, Margin, out direction);
            double s = sign < 0 ? -1.0 : 1.0;
            Vec2d q = OntoInsetLine(p);
            direction = OutwardNormal(q).Perp() * s;
            if (!(length > 0.0)) return q;
            int steps = (int)Math.Ceiling(length / RideSubStep);
            if (steps < 1) steps = 1;
            if (steps > RideMaxSubSteps) steps = RideMaxSubSteps;
            double h = length / steps;
            for (int k = 0; k < steps; k++)
            {
                // The inset rounded box is convex: a tangent step leaves it (or stays on a straight side) and the
                // projection brings it back onto the line, so the head follows the sides and the corner arcs.
                Vec2d t = OutwardNormal(q).Perp() * s;
                direction = t;
                q = OntoInsetLine(q + t * h);
            }
            return q;
        }

        /// <summary>Nearest point of the inset line for a point near it (pushed out from inside, clamped from outside).</summary>
        private Vec2d OntoInsetLine(Vec2d p)
        {
            double f = SignedDistance(p) + Margin;
            if (f < 0.0) p = p - OutwardNormal(p) * f;
            return ClampInside(p);
        }

        private static double Clamp(double v, double lo, double hi)
        {
            if (v < lo) return lo;
            if (v > hi) return hi;
            return v;
        }
    }
}
