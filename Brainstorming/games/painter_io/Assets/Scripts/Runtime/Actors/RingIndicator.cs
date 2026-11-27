// Owned by B2 (actors). Contract 12.3 Ring indicator: when the ring exists, is off screen and lies within 24 u of the
// human, a small white ring icon on the screen edge points at it with a gentle bob. Hidden while the human is chased or
// charged. No text (the brief presents the lasso only at the first pickup).
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    public sealed class RingIndicator
    {
        public const float MaxDistance = 24f;
        /// <summary>Icon radius in pixels at the 1920 px reference height.</summary>
        public const float IconReferencePixels = 26f;

        /// <summary>True when the icon is drawn this frame.</summary>
        public bool IsVisible { get; private set; }

        /// <summary>Screen position of the icon (pixels, origin bottom left) while IsVisible.</summary>
        public Vector2 ScreenPosition { get; private set; }

        public void Reset()
        {
            IsVisible = false;
        }

        public void Tick(ActorContext ctx)
        {
            IsVisible = false;
            Ring ring = ctx.Sim.Ring;
            int h = ctx.Human;
            if (ring == null || h < 0 || h >= ctx.Sim.Players.Count || !ctx.HasCamera) return;
            PlayerState p = ctx.Sim.Players[h];
            if (!p.Alive || p.Charged || p.Spark != null) return;
            var target = new Vector2((float)ring.Pos.X, (float)ring.Pos.Y);
            Vector2 head = ctx.Session.RenderPos(h);
            if ((target - head).sqrMagnitude > MaxDistance * MaxDistance) return;
            if (ctx.IsOnScreen(target, -0.3f)) return;
            if (!ctx.EdgePlacement(target, out Vector2 edge, out Vector2 dir)) return;
            ScreenPosition = DrawAt(ctx, edge, dir, ctx.RealTime);
            IsVisible = true;
        }

        /// <summary>Draws the ring icon and its chevron at an edge position; returns the icon's screen position.</summary>
        public static Vector2 DrawAt(ActorContext ctx, Vector2 edge, Vector2 dir, float time)
        {
            float ppu = Mathf.Max(1e-3f, ctx.PixelsPerUnit);
            float iconPx = IconReferencePixels * ctx.UiScale;
            float bobPx = 6f * ctx.UiScale * Mathf.Sin(2f * Mathf.PI * 1.1f * time);
            Vector2 iconScreen = edge - dir * (iconPx * 0.6f) + dir * bobPx;
            Vector2 iconWorld = ctx.ScreenToWorld(iconScreen);
            float iconHalf = iconPx * 1.4f / ppu;
            if (ctx.Indicators != null)
            {
                ctx.Indicators.AddOverlay(iconWorld, new Vector2(iconHalf, iconHalf), 0f, OverlayShape.Ring,
                                          new Vector3(0.62f, 0.15f, 0.35f), RingView.RingColor, 1f, 2f);
                Vector2 chevronScreen = iconScreen + dir * (iconPx * 1.55f);
                float chevronHalf = iconPx * 0.75f / ppu;
                ctx.Indicators.AddOverlay(ctx.ScreenToWorld(chevronScreen), new Vector2(chevronHalf, chevronHalf),
                                          Mathf.Atan2(dir.y, dir.x), OverlayShape.Chevron, new Vector3(0.14f, 0.1f, 0.6f),
                                          RingView.RingColor, 0.95f, ctx.Lobes);
            }
            return iconScreen;
        }
    }
}
