// Owned by B2 (actors). Contract 12.3 Home arrow: while the human is chased, a small chevron around the pearl points to
// GridQueries.NearestOwned (the nearest own cell), pulsing at 4 Hz together with the pearl (PearlView scales 1.0 to 1.08);
// no ring or outline around the pearl. Keeps the way home readable.
// Wave C (feel-08): the chevron keeps a constant SCREEN size through the chase zoom (its half size and its distance from
// the pearl rim scale with ActorContext.ViewScale, the CameraRig view scale), and it is drawn in three layers so it reads
// over the red chase vignette and bright beds: a soft halo disc in the human color, a navy drop-shadow chevron, then the
// white chevron.
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    public sealed class HomeArrow
    {
        public const float QueryInterval = 0.1f;
        public const double MaxSearchRadius = 100.0;

        /// <summary>Chevron center distance from the pearl rim at view scale 1 (world units, times ViewScale).</summary>
        public const float Distance = 0.65f;

        /// <summary>Chevron quad half size at view scale 1 (world units, times ViewScale): 18.6 px at 540 px width.</summary>
        public const float HalfSize = 0.62f;

        /// <summary>The chevron grows by this fraction at the top of its 4 Hz pulse.</summary>
        public const float PulseGrow = 0.15f;

        /// <summary>The chevron moves out by this much at the top of its pulse (world units, times ViewScale).</summary>
        public const float PulseOut = 0.06f;

        /// <summary>Halo disc quad half size relative to the chevron half size.</summary>
        public const float HaloScale = 1.3f;

        /// <summary>Halo disc opacity (human color).</summary>
        public const float HaloOpacity = 0.45f;

        /// <summary>Drop-shadow offset (world units, times ViewScale): down and to the right, away from the light.</summary>
        public static readonly Vector2 ShadowOffset = new Vector2(0.05f, -0.05f);

        /// <summary>Drop-shadow opacity.</summary>
        public const float ShadowOpacity = 0.6f;

        /// <summary>Navy of the drop shadow (linear), the same navy as the chevron outline of Overlay.hlsl.</summary>
        public static readonly Color ShadowColor = new Color(0.0075f, 0.0123f, 0.0399f, 1f);

        /// <summary>Chevron fill (linear): an off-white (sRGB about 229) that reads as white over the navy floor and the red
        /// vignette but stays below the pure white of the spark glint, which must remain the brightest moving thing on
        /// screen during a chase (contract 25.5; the chevron sits within 1.5 u of the pearl).</summary>
        public static readonly Color ChevronColor = new Color(0.78f, 0.78f, 0.78f, 1f);

        /// <summary>Chevron shape parameters (arm half thickness, outline width, outline opacity), local units.</summary>
        public static readonly Vector3 ChevronShape = new Vector3(0.16f, 0.1f, 0.6f);

        /// <summary>Drop-shadow shape: one arm as thick as the chevron with its outline, no outline of its own.</summary>
        public static readonly Vector3 ShadowShape = new Vector3(0.26f, 0f, 0f);

        /// <summary>Halo shape parameters (glow peak radius, glow width), local units: a soft disc fading before the border.</summary>
        public static readonly Vector3 HaloShape = new Vector3(0f, 0.55f, 0f);

        private float nextQuery;
        private Vector2 queryPos;

        /// <summary>True while the human is chased and a nearest own cell exists.</summary>
        public bool HasTarget { get; private set; }

        /// <summary>Center of the nearest own cell (world) while HasTarget (also read by the camera framing).</summary>
        public Vector2 Target { get; private set; }

        public void Reset()
        {
            HasTarget = false;
            nextQuery = 0f;
        }

        public bool HumanChased(ActorContext ctx)
        {
            int h = ctx.Human;
            if (h < 0 || h >= ctx.Sim.Players.Count) return false;
            PlayerState p = ctx.Sim.Players[h];
            return p.Alive && !p.Home && p.Spark != null;
        }

        public void Tick(ActorContext ctx, PearlView[] pearls)
        {
            if (!HumanChased(ctx))
            {
                HasTarget = false;
                return;
            }
            int h = ctx.Human;
            PlayerState p = ctx.Sim.Players[h];
            Vector2 pos = ctx.Session.RenderPos(h);
            if (ctx.RealTime >= nextQuery || (pos - queryPos).sqrMagnitude > 0.25f || !HasTarget)
            {
                nextQuery = ctx.RealTime + QueryInterval;
                queryPos = pos;
                if (GridQueries.NearestOwned(ctx.Sim.Grid, p.Id, p.Pos, MaxSearchRadius, out Vec2d target, out double _))
                {
                    HasTarget = true;
                    Target = new Vector2((float)target.X, (float)target.Y);
                }
                else HasTarget = false;
            }
            if (!HasTarget || ctx.Overlays == null) return;
            Vector2 d = Target - pos;
            if (d.sqrMagnitude < 1e-6f) return;
            d.Normalize();
            float radius = pearls != null && h < pearls.Length && pearls[h] != null ? pearls[h].LastRadius : (float)Tuning.HeadRadius;
            DrawChevron(ctx, pos, d, radius, ctx.RealTime);
        }

        /// <summary>The 4 Hz pulse of the chevron (0 to 1), in phase with the pearl pulse.</summary>
        public static float Pulse(float time)
        {
            return 0.5f * (1f - Mathf.Cos(2f * Mathf.PI * PearlView.ChasePulseHz * time));
        }

        /// <summary>A sane view scale (1 when the value is missing or absurd).</summary>
        public static float SafeViewScale(float viewScale)
        {
            return viewScale > 0.05f && viewScale < 20f ? viewScale : 1f;
        }

        /// <summary>Chevron quad half size (world units) at a view scale and pulse: constant on screen through the zoom.</summary>
        public static float ChevronHalfSize(float viewScale, float pulse)
        {
            return HalfSize * SafeViewScale(viewScale) * (1f + PulseGrow * Mathf.Clamp01(pulse));
        }

        /// <summary>Distance from the pearl center to the chevron center (world units).</summary>
        public static float ChevronDistance(float pearlRadius, float viewScale, float pulse)
        {
            return Mathf.Max(0f, pearlRadius) + (Distance + PulseOut * Mathf.Clamp01(pulse)) * SafeViewScale(viewScale);
        }

        /// <summary>
        /// Draws the pulsing home chevron around a pearl (center, unit direction, pearl radius) into the overlays, in three
        /// quads: the halo disc (human color), the navy drop shadow, the white chevron. Sizes follow ctx.ViewScale.
        /// </summary>
        public static void DrawChevron(ActorContext ctx, Vector2 pearl, Vector2 dir, float pearlRadius, float time)
        {
            if (ctx == null || ctx.Overlays == null) return;
            float scale = SafeViewScale(ctx.ViewScale);
            float pulse = Pulse(time);
            float half = ChevronHalfSize(scale, pulse);
            Vector2 at = pearl + dir * ChevronDistance(pearlRadius, scale, pulse);
            float angle = Mathf.Atan2(dir.y, dir.x);
            Color human = ctx.Human >= 0 ? ctx.LinearColor(ctx.Human) : Color.white;
            float haloHalf = half * HaloScale;
            ctx.Overlays.AddOverlay(at, new Vector2(haloHalf, haloHalf), 0f, OverlayShape.Halo, HaloShape, human,
                                    HaloOpacity, ctx.Lobes);
            ctx.Overlays.AddOverlay(at + ShadowOffset * scale, new Vector2(half, half), angle, OverlayShape.Chevron, ShadowShape,
                                    ShadowColor, ShadowOpacity, ctx.Lobes);
            ctx.Overlays.AddOverlay(at, new Vector2(half, half), angle, OverlayShape.Chevron, ChevronShape, ChevronColor,
                                    0.82f + 0.18f * pulse, ctx.Lobes);
        }
    }
}
