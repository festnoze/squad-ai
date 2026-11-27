// Owned by B2 (actors). Contract 12.3 Ring: the lasso ring as a glossy white torus-like ring (Overlay shape Ring: fake
// tube normal shaded by PIO_ShadeLiquid, soft shadow ring), bobbing 0.08 u, spinning slowly (a slightly tilted ring whose
// axis turns), with a soft pulsing halo. It pops in when it spawns and flies onto the picker's pearl when picked up.
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    public sealed class RingView
    {
        /// <summary>Centerline radius and tube half width of the ring (world units; RingRadius 0.6 is the outer edge).</summary>
        public const float CenterRadius = 0.48f;
        public const float TubeHalfWidth = 0.12f;
        public const float Bob = 0.08f;
        public const float BobHz = 0.55f;
        public const float SpinRadPerSecond = 0.55f;
        public const float PopSeconds = 0.35f;
        public const float FlySeconds = 0.22f;

        /// <summary>Pearl white, linear.</summary>
        public static readonly Color RingColor = new Color(0.93f, 0.93f, 0.96f, 1f);

        private Ring lastRing;
        private Vector2 lastPos;
        private float spawnStart = -100f;
        private bool flying;
        private float flyStart;
        private int flyTarget = -1;
        private Vector2 flyFrom;

        public void Reset()
        {
            lastRing = null;
            spawnStart = -100f;
            flying = false;
        }

        public void OnSpawned(float now)
        {
            spawnStart = now;
        }

        public void OnPicked(int player, float now)
        {
            flying = true;
            flyStart = now;
            flyTarget = player;
            flyFrom = lastPos;
        }

        public void Tick(ActorContext ctx, PearlView[] pearls)
        {
            float now = ctx.Time;
            Ring ring = ctx.Sim.Ring;
            if (ring != lastRing)
            {
                if (ring != null && spawnStart < now - PopSeconds) spawnStart = now;
                lastRing = ring;
            }
            if (ring != null && ctx.Overlays != null)
            {
                Vector2 pos = new Vector2((float)ring.Pos.X, (float)ring.Pos.Y + Bob * Mathf.Sin(2f * Mathf.PI * BobHz * now));
                float scale = PopScale(now - spawnStart);
                DrawRing(ctx, pos, scale, now, 1f, true);
                lastPos = pos;
            }
            if (flying)
            {
                float u = (now - flyStart) / FlySeconds;
                if (u >= 1f || flyTarget < 0 || pearls == null || flyTarget >= pearls.Length || pearls[flyTarget] == null || !pearls[flyTarget].WasVisible)
                {
                    flying = false;
                }
                else if (ctx.Overlays != null)
                {
                    float e = 1f - (1f - u) * (1f - u);
                    Vector2 pos = Vector2.Lerp(flyFrom, pearls[flyTarget].LastPosition, e);
                    float target = (pearls[flyTarget].LastRadius + ChargeRing.Gap) / CenterRadius;
                    DrawRing(ctx, pos, Mathf.Lerp(1f, target, e), now, 1f - 0.3f * u, false);
                }
            }
        }

        /// <summary>Elastic pop-in scale over PopSeconds.</summary>
        public static float PopScale(float t)
        {
            if (t >= PopSeconds) return 1f;
            if (t <= 0f) return 0f;
            float u = t / PopSeconds;
            float grow = 1f - (1f - u) * (1f - u) * (1f - u);
            return grow * (1f + 0.2f * Mathf.Sin(Mathf.PI * u));
        }

        /// <summary>Draws the ring (and its halo) at pos into the overlay batch.</summary>
        public static void DrawRing(ActorContext ctx, Vector2 pos, float scale, float now, float opacity, bool halo)
        {
            if (scale <= 0.01f) return;
            if (halo)
            {
                float hh = 1.35f * scale;
                float pulse = 0.5f + 0.5f * Mathf.Sin(now * 3.1f);
                ctx.Overlays.AddOverlay(pos, new Vector2(hh, hh), 0f, OverlayShape.Halo,
                                        new Vector3(CenterRadius * scale / hh, 0.26f * scale / hh, 0f),
                                        RingColor, (0.22f + 0.12f * pulse) * opacity, ctx.Lobes);
            }
            float half = (CenterRadius + TubeHalfWidth + 0.2f) * scale;
            float tilt = 0.86f + 0.05f * Mathf.Sin(now * 1.15f);
            ctx.Overlays.AddOverlay(pos, new Vector2(half, half * tilt), now * SpinRadPerSecond, OverlayShape.Ring,
                                    new Vector3(CenterRadius * scale / half, TubeHalfWidth * scale / half, 0.42f),
                                    RingColor, opacity, 2f);
        }
    }
}
