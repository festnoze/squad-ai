// Owned by B2 (actors). Contract 12.3 Pearl, Exit pop and Home arrow pulse, 23.3 debounce: the pawn head as an analytic
// bead impostor (Bead graph, visible radius HeadRadius) plus a FieldBlob neck (A = 1.0, visible radius 0.8 HeadRadius)
// that forms the necks with its thread and puddle. Squash and stretch along the velocity (1.15 / 0.9 at most), springy
// wobble on turns, a 0.15 s pop when the detach becomes visible, a 0.2 s merge squash (1.15 / 0.85) exactly on the
// Return event (only for a Return with cells or after a visible detach), and the 1.0 to 1.08 pulse at 4 Hz while chased.
using System;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    public sealed class PearlView
    {
        public const float NeckRadiusFactor = 0.8f;
        public const float PopSeconds = 0.15f;
        public const float MergeSeconds = 0.2f;
        public const float MaxStretch = 1.15f;
        public const float MinStretch = 0.88f;
        public const float MovingStretch = 1.04f;
        public const float ChasePulseHz = 4f;
        public const float ChasePulseScale = 1.08f;
        public const float ShadowStrength = 0.58f;
        public const float HighlightBoost = 0.7f;

        private readonly int player;
        private readonly FieldBlobDrawer neck;

        private bool detachShown;
        private float popStart = -100f;
        private float mergeStart = -100f;
        private float spring, springVelocity;
        private float lastHeading;
        private bool hasHeading;
        private float chaseClock;

        public PearlView(int player, Transform parent, Material blobMaterial)
        {
            this.player = player;
            neck = new FieldBlobDrawer("PearlNeck" + player, parent, blobMaterial);
        }

        /// <summary>The bead was drawn in the last frame.</summary>
        public bool WasVisible { get; private set; }

        /// <summary>Where the bead was drawn in the last frame (world).</summary>
        public Vector2 LastPosition { get; private set; }

        /// <summary>Visible radius of the bead in the last frame (world units, pulses included).</summary>
        public float LastRadius { get; private set; } = (float)Tuning.HeadRadius;

        /// <summary>True between the Return event and the end of the merge squash.</summary>
        public bool Merging(float now) => now - mergeStart < MergeSeconds;

        public void Reset()
        {
            detachShown = false;
            popStart = mergeStart = -100f;
            spring = springVelocity = 0f;
            hasHeading = false;
            WasVisible = false;
            neck.Hide();
        }

        public void Hide()
        {
            WasVisible = false;
            neck.Hide();
        }

        public void Destroy()
        {
            neck.Destroy();
        }

        public void OnExit(SimEvent e)
        {
            detachShown = false;
        }

        /// <summary>23.3: the merge pulse plays only for a Return with cells or after a visible detach.</summary>
        public void OnReturn(GameSession session, SimEvent e, float now)
        {
            bool cells = e.Cells != null && e.Cells.Length > 0;
            if (cells || detachShown) mergeStart = now;
            detachShown = false;
        }

        public void OnEliminated()
        {
            WasVisible = false;
            neck.Hide();
        }

        public void Tick(ActorContext ctx, bool chased)
        {
            Simulation sim = ctx.Sim;
            if (player >= sim.Players.Count)
            {
                Hide();
                return;
            }
            PlayerState p = sim.Players[player];
            if (!p.Alive)
            {
                Hide();
                return;
            }
            float now = ctx.Time;
            Vector2 pos = ctx.Session.RenderPos(player);

            // 23.3: the detach (pop) starts when the trail is longer than 0.35 u or the exit lasted 0.25 s.
            if (!p.Home && !detachShown && ctx.Session.HasVisibleDetach(player))
            {
                detachShown = true;
                popStart = now;
                springVelocity += 2.2f;
            }

            // Springy wobble driven by the turn rate.
            float heading = (float)p.Heading;
            float turnRate = 0f;
            if (hasHeading && ctx.Dt > 1e-5f) turnRate = Mathf.Abs(Mathf.DeltaAngle(lastHeading * Mathf.Rad2Deg, heading * Mathf.Rad2Deg)) * Mathf.Deg2Rad / ctx.Dt;
            lastHeading = heading;
            hasHeading = true;
            float target = (MovingStretch - 1f) - Mathf.Min(0.1f, 0.011f * turnRate);
            StepSpring(target, ctx.Dt);

            float pop = Envelope(now - popStart, PopSeconds);
            float merge = Envelope(now - mergeStart, MergeSeconds);
            float stretch = 1f + spring + 0.12f * pop + 0.15f * merge;
            stretch = Mathf.Clamp(stretch, MinStretch, MaxStretch);

            float scale = 1f;
            if (chased)
            {
                chaseClock += ctx.RealDt;
                scale = 1f + (ChasePulseScale - 1f) * 0.5f * (1f - Mathf.Cos(2f * Mathf.PI * ChasePulseHz * chaseClock));
            }
            else chaseClock = 0f;

            float radius = (float)sim.Config.HeadRadius * scale;
            var dir = new Vector2(Mathf.Cos(heading), Mathf.Sin(heading));
            Color color = ctx.LinearColor(player);
            ctx.Pearls?.AddBead(pos, radius, dir, stretch, color, 1f, ShadowStrength, ctx.Lobes, HighlightBoost);

            float neckAmplitude = 1f + 0.45f * pop + 0.6f * merge;
            neck.Show(player, pos, radius * NeckRadiusFactor, neckAmplitude, stretch, heading);

            WasVisible = true;
            LastPosition = pos;
            LastRadius = radius;
        }

        private void StepSpring(float target, float dt)
        {
            // Critically under-damped spring (about 7 Hz, damping ratio 0.35), semi-implicit Euler in small substeps.
            const float omega = 2f * Mathf.PI * 7f;
            const float k = omega * omega;
            const float c = 2f * 0.35f * omega;
            float remaining = Mathf.Min(dt, 0.1f);
            while (remaining > 1e-6f)
            {
                float h = Mathf.Min(remaining, 1f / 240f);
                springVelocity += (-k * (spring - target) - c * springVelocity) * h;
                spring += springVelocity * h;
                remaining -= h;
            }
            if (float.IsNaN(spring) || float.IsNaN(springVelocity))
            {
                spring = 0f;
                springVelocity = 0f;
            }
        }

        /// <summary>sin(pi t / duration) on [0, duration], 0 elsewhere.</summary>
        private static float Envelope(float t, float duration)
        {
            if (t < 0f || t >= duration) return 0f;
            return Mathf.Sin(Mathf.PI * t / duration);
        }
    }
}
