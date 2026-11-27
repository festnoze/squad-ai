// Owned by B2 (actors). Contract 12.3 Cut flash and brief 4 (lisibilite): at every cut point visible on screen (any
// attacker, any victim) a white ring pulse blinking 3 times over 0.6 s (overlay), with a short white burst at the impact.
using UnityEngine;

namespace PainterIO.Runtime
{
    public sealed class CutFlash
    {
        public const float Duration = 0.6f;
        public const int Blinks = 3;
        public const int MaxFlashes = 16;
        /// <summary>A cut is "on screen" when its point lies inside the view grown by this margin (world units).</summary>
        public const float ScreenMargin = 0.6f;

        private readonly Vector2[] points = new Vector2[MaxFlashes];
        private readonly float[] starts = new float[MaxFlashes];
        private int count;

        /// <summary>Flashes alive in the last frame.</summary>
        public int ActiveCount => count;

        public void Reset()
        {
            count = 0;
        }

        /// <summary>Starts a flash at a cut point when it is on screen.</summary>
        public void Spawn(ActorContext ctx, Vector2 point)
        {
            if (ctx.HasCamera && !ctx.IsOnScreen(point, ScreenMargin)) return;
            if (count >= MaxFlashes)
            {
                // Drop the oldest.
                for (int k = 1; k < count; k++)
                {
                    points[k - 1] = points[k];
                    starts[k - 1] = starts[k];
                }
                count--;
            }
            points[count] = point;
            starts[count] = ctx.Time;
            count++;
        }

        /// <summary>Blink pattern: 3 blinks over Duration (on for 65 % of each period), fading slightly.</summary>
        public static float Intensity(float t)
        {
            if (t < 0f || t >= Duration) return 0f;
            float period = Duration / Blinks;
            float phase = (t % period) / period;
            float on = phase < 0.65f ? 1f : 0.12f;
            return on * (1f - 0.35f * t / Duration);
        }

        public void Tick(ActorContext ctx)
        {
            float now = ctx.Time;
            int w = 0;
            for (int k = 0; k < count; k++)
            {
                float t = now - starts[k];
                if (t >= Duration) continue;
                points[w] = points[k];
                starts[w] = starts[k];
                w++;
                if (ctx.Overlays == null) continue;
                float u = Mathf.Clamp01(t / Duration);
                float radius = 0.32f + 0.6f * Mathf.Sqrt(u);
                const float half = 1.2f;
                float alpha = Intensity(t);
                ctx.Overlays.AddOverlay(points[k], new Vector2(half, half), 0f, OverlayShape.Flash,
                                        new Vector3(radius / half, 0.045f / half, 0.45f), Color.white, alpha, ctx.Lobes);
                if (t < 0.12f)
                {
                    // Impact burst.
                    float b = 1f - t / 0.12f;
                    ctx.Overlays.AddOverlay(points[k], new Vector2(0.55f, 0.55f), 0.6f, OverlayShape.Glint,
                                            new Vector3(0.3f, 0.35f, 0.08f), Color.white, b, ctx.Lobes);
                }
            }
            count = w;
        }
    }
}
