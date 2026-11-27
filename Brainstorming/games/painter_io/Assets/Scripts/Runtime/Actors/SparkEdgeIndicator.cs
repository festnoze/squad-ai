// Owned by B2 (actors). Contract 12.3 Spark edge indicator: when the human's retraction front (at RenderSparkS) is off
// screen, a chevron on the screen edge points at it; its pulse rate rises as SimView.SparkCatchEta drops. It exposes its
// screen position for the tutorial pointer (contract 15.4): the static IsVisible and ScreenPosition (pixels, origin bottom
// left; static so TutorialOverlay can read them without an instance), also through ActorViews.TryGetSparkPointer.
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    public sealed class SparkEdgeIndicator
    {
        /// <summary>Chevron half size in pixels at the 1920 px reference height.</summary>
        public const float HalfSizeReferencePixels = 34f;
        public const float SlowHz = 1.6f;
        public const float FastHz = 7f;

        private float clock;

        /// <summary>True when the chevron is drawn this frame (the human's front is off screen). Static: one ActorViews.</summary>
        public static bool IsVisible { get; private set; }

        /// <summary>Screen position of the chevron in pixels (origin bottom left) while IsVisible.</summary>
        public static Vector2 ScreenPosition { get; private set; }

        /// <summary>World position of the chevron while IsVisible.</summary>
        public static Vector2 WorldPosition { get; private set; }

        /// <summary>Pulse frequency for a catch ETA (seconds): faster as the spark gets closer.</summary>
        public static float PulseHz(double eta)
        {
            if (double.IsNaN(eta) || double.IsInfinity(eta)) return SlowHz;
            float urgency = 1f - Mathf.Clamp01(((float)eta - 0.4f) / 2.6f);
            return Mathf.Lerp(SlowHz, FastHz, urgency);
        }

        public void Reset()
        {
            IsVisible = false;
            clock = 0f;
        }

        public void Tick(ActorContext ctx, RetractionView[] retractions)
        {
            IsVisible = false;
            int h = ctx.Human;
            if (h < 0 || retractions == null || h >= retractions.Length || retractions[h] == null || !retractions[h].HasFront) return;
            if (!ctx.HasCamera) return;
            Vector2 front = retractions[h].FrontWorld;
            if (ctx.IsOnScreen(front, -0.25f)) return;
            if (!ctx.EdgePlacement(front, out Vector2 edge, out Vector2 dir)) return;
            double eta = ctx.Sim.View.SparkCatchEta(h);
            clock += ctx.RealDt * PulseHz(eta);
            float pulse = 0.5f + 0.5f * Mathf.Sin(2f * Mathf.PI * clock);
            Vector2 world = DrawAt(ctx, edge, dir, ctx.LinearColor(h), pulse);
            IsVisible = true;
            ScreenPosition = edge;
            WorldPosition = world;
        }

        /// <summary>Draws the edge chevron (glow in the given color) at a screen position; returns its world position.</summary>
        public static Vector2 DrawAt(ActorContext ctx, Vector2 edgeScreen, Vector2 dirScreen, Color glow, float pulse)
        {
            float halfPx = HalfSizeReferencePixels * ctx.UiScale * (1f + 0.18f * pulse);
            float half = halfPx / Mathf.Max(1e-3f, ctx.PixelsPerUnit);
            Vector2 world = ctx.ScreenToWorld(edgeScreen);
            float angle = Mathf.Atan2(dirScreen.y, dirScreen.x);
            if (ctx.Indicators != null)
            {
                ctx.Indicators.AddOverlay(world, new Vector2(half * 1.9f, half * 1.9f), 0f, OverlayShape.Halo,
                                          new Vector3(0.18f, 0.32f, 0f), glow, 0.55f + 0.35f * pulse, ctx.Lobes);
                ctx.Indicators.AddOverlay(world, new Vector2(half, half), angle, OverlayShape.Chevron,
                                          new Vector3(0.15f, 0.1f, 0.65f), Color.white, 0.85f + 0.15f * pulse, ctx.Lobes);
            }
            return world;
        }
    }
}
