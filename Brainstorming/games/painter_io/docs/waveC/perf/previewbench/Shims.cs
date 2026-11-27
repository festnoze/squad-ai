// Minimal UnityEngine shims so BiomePreview's paint code can be timed under dotnet (benchmark only).
using System;

public struct Color
{
    public float r, g, b, a;
    public Color(float r, float g, float b, float a = 1f) { this.r = r; this.g = g; this.b = b; this.a = a; }
    public static Color white => new Color(1f, 1f, 1f, 1f);
    public static Color operator *(Color c, float k) => new Color(c.r * k, c.g * k, c.b * k, c.a * k);
    public static Color operator +(Color x, Color y) => new Color(x.r + y.r, x.g + y.g, x.b + y.b, x.a + y.a);
    public static Color Lerp(Color x, Color y, float t)
    {
        t = Mathf.Clamp01(t);
        return new Color(x.r + (y.r - x.r) * t, x.g + (y.g - x.g) * t, x.b + (y.b - x.b) * t, x.a + (y.a - x.a) * t);
    }
    public static implicit operator Color32(Color c) => new Color32(
        (byte)Math.Round(Mathf.Clamp01(c.r) * 255f), (byte)Math.Round(Mathf.Clamp01(c.g) * 255f),
        (byte)Math.Round(Mathf.Clamp01(c.b) * 255f), (byte)Math.Round(Mathf.Clamp01(c.a) * 255f));
}

public struct Color32
{
    public byte r, g, b, a;
    public Color32(byte r, byte g, byte b, byte a) { this.r = r; this.g = g; this.b = b; this.a = a; }
}

public struct Vector2
{
    public float x, y;
    public Vector2(float x, float y) { this.x = x; this.y = y; }
    public static Vector2 operator +(Vector2 p, Vector2 q) => new Vector2(p.x + q.x, p.y + q.y);
    public static Vector2 operator -(Vector2 p, Vector2 q) => new Vector2(p.x - q.x, p.y - q.y);
    public static Vector2 operator *(Vector2 p, float k) => new Vector2(p.x * k, p.y * k);
    public static Vector2 operator /(Vector2 p, float k) => new Vector2(p.x / k, p.y / k);
    public float sqrMagnitude => x * x + y * y;
    public float magnitude => (float)Math.Sqrt(x * x + y * y);
    public Vector2 normalized { get { float m = magnitude; return m > 1e-5f ? this / m : new Vector2(0f, 0f); } }
    public static float Dot(Vector2 p, Vector2 q) => p.x * q.x + p.y * q.y;
    public static float Distance(Vector2 p, Vector2 q) => (p - q).magnitude;
    public static Vector2 Lerp(Vector2 p, Vector2 q, float t) { t = Mathf.Clamp01(t); return new Vector2(p.x + (q.x - p.x) * t, p.y + (q.y - p.y) * t); }
}

public struct Vector3
{
    public float x, y, z;
    public Vector3(float x, float y, float z) { this.x = x; this.y = y; this.z = z; }
    public static Vector3 forward => new Vector3(0f, 0f, 1f);
    public static Vector3 operator +(Vector3 p, Vector3 q) => new Vector3(p.x + q.x, p.y + q.y, p.z + q.z);
    public float magnitude => (float)Math.Sqrt(x * x + y * y + z * z);
    public Vector3 normalized { get { float m = magnitude; return m > 1e-5f ? new Vector3(x / m, y / m, z / m) : new Vector3(0f, 0f, 0f); } }
    public static float Dot(Vector3 p, Vector3 q) => p.x * q.x + p.y * q.y + p.z * q.z;
}

public static class Mathf
{
    public const float PI = (float)Math.PI;
    public static float Sin(float v) => (float)Math.Sin(v);
    public static float Cos(float v) => (float)Math.Cos(v);
    public static float Sqrt(float v) => (float)Math.Sqrt(v);
    public static float Pow(float a, float b) => (float)Math.Pow(a, b);
    public static float Abs(float v) => Math.Abs(v);
    public static float Atan2(float y, float x) => (float)Math.Atan2(y, x);
    public static float Floor(float v) => (float)Math.Floor(v);
    public static int FloorToInt(float v) => (int)Math.Floor(v);
    public static int RoundToInt(float v) => (int)Math.Round(v);
    public static float Max(float a, float b) => a > b ? a : b;
    public static float Min(float a, float b) => a < b ? a : b;
    public static float Clamp01(float v) => v < 0f ? 0f : (v > 1f ? 1f : v);
    public static float Lerp(float a, float b, float t) => a + (b - a) * Clamp01(t);
}

public sealed class Theme
{
    public Color Ground = new Color(0.08f, 0.09f, 0.18f);
    public Color[] PlayerColors = { new Color(1f, 0.35f, 0.16f), new Color(0.13f, 0.88f, 0.72f), new Color(1f, 0.76f, 0.12f), new Color(0.7f, 0.45f, 1f) };
    public Color[] SecondaryColors = { new Color(1f, 0.82f, 0.54f), new Color(0.8f, 1f, 1f), new Color(1f, 0.95f, 0.6f), new Color(0.9f, 0.8f, 1f) };
}
