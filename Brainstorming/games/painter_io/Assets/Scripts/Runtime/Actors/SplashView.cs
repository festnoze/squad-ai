// Owned by B2 (actors). Contract 12.3 Splash: on elimination the pearl bursts into 8 to 12 bead drops flying out and
// shrinking over 0.5 s (deterministic per event). All drops of all splashes are one dynamic bead mesh.
using UnityEngine;

namespace PainterIO.Runtime
{
    public sealed class SplashView
    {
        public const float Duration = 0.5f;
        public const int MinDrops = 8;
        public const int MaxDrops = 12;
        public const int MaxSplashes = 8;

        private readonly QuadBatch batch;
        private readonly Vector2[] origins = new Vector2[MaxSplashes];
        private readonly Color[] colors = new Color[MaxSplashes];
        private readonly float[] starts = new float[MaxSplashes];
        private readonly int[] seeds = new int[MaxSplashes];
        private int count;

        public SplashView(Transform parent, Shader beadShader)
        {
            batch = new QuadBatch("Splash", parent, beadShader, QuadBatch.QueueSplash, 20);
        }

        /// <summary>Splashes alive in the last frame.</summary>
        public int ActiveCount => count;

        /// <summary>Number of drops of a splash with this seed (8 to 12).</summary>
        public static int DropCount(int seed)
        {
            return MinDrops + (int)(RetractionView.Hash01(seed * 31 + 5) * (MaxDrops - MinDrops + 1) - 1e-4f);
        }

        public void Spawn(Vector2 origin, Color linearColor, int player, float now, double simTime)
        {
            if (count >= MaxSplashes)
            {
                for (int k = 1; k < count; k++)
                {
                    origins[k - 1] = origins[k];
                    colors[k - 1] = colors[k];
                    starts[k - 1] = starts[k];
                    seeds[k - 1] = seeds[k];
                }
                count--;
            }
            origins[count] = origin;
            colors[count] = linearColor;
            starts[count] = now;
            seeds[count] = player * 7919 + (int)(simTime * 60.0) * 31;
            count++;
        }

        public void Reset()
        {
            count = 0;
            batch.Hide();
        }

        public void Hide()
        {
            batch.Hide();
        }

        public void Destroy()
        {
            batch.Destroy();
        }

        public void Tick(ActorContext ctx)
        {
            float now = ctx.Time;
            batch.Begin();
            int w = 0;
            for (int k = 0; k < count; k++)
            {
                float t = now - starts[k];
                if (t >= Duration) continue;
                origins[w] = origins[k];
                colors[w] = colors[k];
                starts[w] = starts[k];
                seeds[w] = seeds[k];
                w++;
                Draw(ctx, origins[k], colors[k], seeds[k], Mathf.Max(0f, t));
            }
            count = w;
            batch.End();
        }

        private void Draw(ActorContext ctx, Vector2 origin, Color color, int seed, float t)
        {
            float u = t / Duration;
            float head = (float)ctx.Sim.Config.HeadRadius;
            // The pearl itself pops for the first frames (the drop bursts).
            if (t < 0.08f)
            {
                float b = 1f - t / 0.08f;
                batch.AddBead(origin, head * (1f + 0.25f * (1f - b)), Vector2.right, 1f, color, b, 0.4f, ctx.Lobes, 0.6f);
            }
            int drops = DropCount(seed);
            float opacity = u < 0.7f ? 1f : Mathf.Clamp01((1f - u) / 0.3f);
            float travel = 1f - (1f - u) * (1f - u) * (1f - u);
            for (int d = 0; d < drops; d++)
            {
                float h0 = RetractionView.Hash01(seed + d * 17 + 1);
                float h1 = RetractionView.Hash01(seed + d * 17 + 2);
                float h2 = RetractionView.Hash01(seed + d * 17 + 3);
                float angle = 2f * Mathf.PI * (d + 0.5f * (h0 - 0.5f)) / drops;
                var dir = new Vector2(Mathf.Cos(angle), Mathf.Sin(angle));
                float speed = 3.0f + 2.6f * h1;
                float r0 = 0.09f + 0.12f * h2;
                float dist = head * 0.55f + speed * Duration / 3f * travel;
                float r = r0 * Mathf.Pow(1f - u, 0.7f);
                float stretch = 1f + 0.55f * (1f - u) * (1f - u);
                batch.AddBead(origin + dir * dist, r, dir, stretch, color, opacity, 0.3f, ctx.Lobes, 0.5f);
            }
        }
    }
}
