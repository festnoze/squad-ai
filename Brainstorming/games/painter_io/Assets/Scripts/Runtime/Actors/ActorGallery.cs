// Owned by B2 (actors). Development aid for the visual check loop (contract 23.3): with "-actorgallery" on the command
// line, ActorViews also draws the overlays the demo round never shows (lasso ring with halo, a pearl carrying a charge
// ring with the home arrow chevron, glint, cut flash ring, ring indicator and spark edge chevron) at fixed places of the
// current view, so a DevShot run shows them next to the real actors. Without the flag nothing here runs.
using UnityEngine;

namespace PainterIO.Runtime
{
    public static class ActorGallery
    {
        public const string Flag = "-actorgallery";

        private static int enabled = -1;

        /// <summary>True when "-actorgallery" is on the command line (read once).</summary>
        public static bool Enabled
        {
            get
            {
                if (enabled < 0) enabled = LaunchArgs.Has(Flag) ? 1 : 0;
                return enabled == 1;
            }
        }

        /// <summary>Draws the gallery into the context batches (call between Begin and End of the batches).</summary>
        public static void Draw(ActorContext ctx)
        {
            if (!ctx.HasCamera || ctx.Overlays == null) return;
            Rect v = ctx.ViewRect;
            float t = ctx.Time;
            float rt = ctx.RealTime;

            // Lasso ring with its halo, upper left.
            var ringPos = new Vector2(v.xMin + v.width * 0.22f, v.yMin + v.height * 0.8f + RingView.Bob * Mathf.Sin(2f * Mathf.PI * RingView.BobHz * t));
            RingView.DrawRing(ctx, ringPos, 1f, t, 1f, true);

            // A pearl (player 0's color) carrying a charge, with the home arrow chevron, upper right.
            var pearlPos = new Vector2(v.xMin + v.width * 0.7f, v.yMin + v.height * 0.8f);
            float radius = 0.45f;
            ctx.Pearls?.AddBead(pearlPos, radius, Vector2.right, 1.04f, ctx.LinearColor(0), 1f, PearlView.ShadowStrength, ctx.Lobes, PearlView.HighlightBoost);
            ChargeRing.DrawAround(ctx, pearlPos, radius, t, 0);
            HomeArrow.DrawChevron(ctx, pearlPos, new Vector2(-0.6f, -0.8f), radius, rt);

            // Glint and a cut flash ring (looping), lower left (clear of the tutorial bubble).
            var mid = new Vector2(v.xMin + v.width * 0.3f, v.yMin + v.height * 0.16f);
            ctx.Overlays.AddOverlay(mid + new Vector2(-1.4f, 0f), new Vector2(0.34f, 0.34f), t * 1.3f, OverlayShape.Glint,
                                    new Vector3(0.22f, 0.3f, 0.08f), Color.white, 0.95f, ctx.Lobes);
            float ft = t % 1.2f;
            if (ft < CutFlash.Duration)
            {
                float u = ft / CutFlash.Duration;
                const float half = 1.2f;
                float r = 0.32f + 0.6f * Mathf.Sqrt(u);
                ctx.Overlays.AddOverlay(mid + new Vector2(1.4f, 0f), new Vector2(half, half), 0f, OverlayShape.Flash,
                                        new Vector3(r / half, 0.045f / half, 0.45f), Color.white, CutFlash.Intensity(ft), ctx.Lobes);
            }

            // Edge indicators: ring icon on the left edge, spark chevron (glow in player 0's color) on the right edge.
            Rect ir = ctx.IndicatorRect;
            RingIndicator.DrawAt(ctx, new Vector2(ir.xMin, ir.center.y), Vector2.left, rt);
            float pulse = 0.5f + 0.5f * Mathf.Sin(2f * Mathf.PI * 3f * rt);
            SparkEdgeIndicator.DrawAt(ctx, new Vector2(ir.xMax, ir.center.y - ir.height * 0.15f), new Vector2(0.94f, -0.34f).normalized, ctx.LinearColor(0), pulse);
        }
    }
}
