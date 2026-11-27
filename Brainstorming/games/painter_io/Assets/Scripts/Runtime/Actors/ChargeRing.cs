// Owned by B2 (actors). Contract 12.3 Charge: a thin white ring orbiting the carrier's pearl (a tilted ring whose axis
// turns), the only ring ever drawn around a pearl (brief 5: "un anneau autour de sa tete").
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    public sealed class ChargeRing
    {
        /// <summary>Distance between the pearl's rim and the ring's centerline (world units).</summary>
        public const float Gap = 0.2f;
        public const float TubeHalfWidth = 0.04f;
        public const float OrbitRadPerSecond = 2.4f;

        public void Reset()
        {
        }

        public void Tick(ActorContext ctx, PearlView[] pearls)
        {
            if (ctx.Overlays == null || pearls == null) return;
            Simulation sim = ctx.Sim;
            int n = Mathf.Min(sim.Players.Count, pearls.Length);
            float now = ctx.Time;
            for (int i = 0; i < n; i++)
            {
                PlayerState p = sim.Players[i];
                PearlView pearl = pearls[i];
                if (!p.Alive || !p.Charged || pearl == null || !pearl.WasVisible) continue;
                DrawAround(ctx, pearl.LastPosition, pearl.LastRadius, now, i);
            }
        }

        /// <summary>Draws the orbiting charge ring around a pearl of the given radius.</summary>
        public static void DrawAround(ActorContext ctx, Vector2 center, float pearlRadius, float now, int phase)
        {
            float r = pearlRadius + Gap;
            float half = r + TubeHalfWidth + 0.12f;
            float tilt = 0.8f + 0.04f * Mathf.Sin(now * 1.7f + phase);
            ctx.Overlays.AddOverlay(center, new Vector2(half, half * tilt), now * OrbitRadPerSecond + phase * 1.3f,
                                    OverlayShape.Ring, new Vector3(r / half, TubeHalfWidth / half, 0.25f),
                                    RingView.RingColor, 1f, 2f);
        }
    }
}
