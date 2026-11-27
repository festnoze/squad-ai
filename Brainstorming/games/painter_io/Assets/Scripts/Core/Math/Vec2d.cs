using System;
using System.Globalization;

namespace PainterIO.Core
{
    /// <summary>
    /// Immutable 2D vector in double precision (contract 3 and 5.1). Simulation space: x right, y up, angles in radians,
    /// 0 = +x, counter-clockwise positive.
    /// </summary>
    public readonly struct Vec2d : IEquatable<Vec2d>
    {
        public readonly double X, Y;

        public Vec2d(double x, double y)
        {
            X = x;
            Y = y;
        }

        public static readonly Vec2d Zero = new Vec2d(0.0, 0.0);

        public static Vec2d operator +(Vec2d a, Vec2d b) => new Vec2d(a.X + b.X, a.Y + b.Y);
        public static Vec2d operator -(Vec2d a, Vec2d b) => new Vec2d(a.X - b.X, a.Y - b.Y);
        public static Vec2d operator -(Vec2d a) => new Vec2d(-a.X, -a.Y);
        public static Vec2d operator *(Vec2d a, double k) => new Vec2d(a.X * k, a.Y * k);
        public static Vec2d operator *(double k, Vec2d a) => new Vec2d(a.X * k, a.Y * k);
        public static Vec2d operator /(Vec2d a, double k) => new Vec2d(a.X / k, a.Y / k);

        /// <summary>Exact component-wise comparison (no tolerance).</summary>
        public static bool operator ==(Vec2d a, Vec2d b) => a.X == b.X && a.Y == b.Y;
        public static bool operator !=(Vec2d a, Vec2d b) => !(a == b);

        public double Length => Math.Sqrt(X * X + Y * Y);
        public double LengthSq => X * X + Y * Y;

        /// <summary>
        /// Unit vector with the same direction. Zero stays Zero. Components so small (or large) that X*X underflows
        /// (or overflows) are rescaled first, so any finite non-zero vector gives a unit vector.
        /// </summary>
        public Vec2d Normalized()
        {
            double len = Length;
            if (len > 0.0 && !double.IsInfinity(len)) return new Vec2d(X / len, Y / len);
            double m = Math.Max(Math.Abs(X), Math.Abs(Y));
            if (!(m > 0.0) || double.IsInfinity(m)) return Zero;
            double sx = X / m, sy = Y / m;
            double sl = Math.Sqrt(sx * sx + sy * sy);
            return new Vec2d(sx / sl, sy / sl);
        }

        public static double Dot(Vec2d a, Vec2d b) => a.X * b.X + a.Y * b.Y;

        /// <summary>2D cross product (z of the 3D cross): positive when b is counter-clockwise from a.</summary>
        public static double Cross(Vec2d a, Vec2d b) => a.X * b.Y - a.Y * b.X;

        public static double Distance(Vec2d a, Vec2d b)
        {
            double dx = a.X - b.X, dy = a.Y - b.Y;
            return Math.Sqrt(dx * dx + dy * dy);
        }

        /// <summary>
        /// Unclamped linear interpolation a + t (b - a). Exact at both ends: t == 0 returns a and t == 1 returns b
        /// bit for bit (plain a + (b - a) can miss b by one ulp), so a tick segment evaluated at u = 1 lands on p1.
        /// </summary>
        public static Vec2d Lerp(Vec2d a, Vec2d b, double t)
        {
            if (t == 1.0) return b;
            return new Vec2d(a.X + (b.X - a.X) * t, a.Y + (b.Y - a.Y) * t);
        }

        /// <summary>Unit vector at the given angle (radians, 0 = +x, CCW positive).</summary>
        public static Vec2d FromAngle(double radians) => new Vec2d(Math.Cos(radians), Math.Sin(radians));

        /// <summary>atan2(Y, X) in (-pi, pi]; 0 for the zero vector.</summary>
        public double Angle() => Math.Atan2(Y, X);

        /// <summary>The vector rotated by +90 degrees: (-Y, X).</summary>
        public Vec2d Perp() => new Vec2d(-Y, X);

        public bool Equals(Vec2d other) => X.Equals(other.X) && Y.Equals(other.Y);

        public override bool Equals(object obj) => obj is Vec2d other && Equals(other);

        public override int GetHashCode()
        {
            unchecked
            {
                return (X.GetHashCode() * 397) ^ Y.GetHashCode();
            }
        }

        public override string ToString()
        {
            return "(" + X.ToString("R", CultureInfo.InvariantCulture) + ", " + Y.ToString("R", CultureInfo.InvariantCulture) + ")";
        }
    }
}
