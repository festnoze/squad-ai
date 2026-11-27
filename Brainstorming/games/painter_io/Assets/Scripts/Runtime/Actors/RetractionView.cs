// Owned by B2 (actors). Contract 12.3 Retraction = spark: after a cut the thread retracts from the pinch toward the
// pearl. ThreadView draws [0, s_cut - 0.25] (pinched taper) and [RenderSparkS, L]; this view draws the front at
// Sr = GameSession.RenderSparkS (same Alpha as RenderPos, so the drawn gap equals the sim gap): a teardrop FieldBlob bulb
// (visible radius 0.26) whose leading edge is at Sr and whose round back trails behind it, with a fast jitter and a
// flickering white glint (overlay). Between s_cut and the bulb a chain of bead droplets is left every 0.45 u (visible
// radius 0.07 to 0.12, deterministic per index), shivering slightly; all droplets of the chain are ONE dynamic mesh.
// On a saved return (contract 24, v1.4: it captures nothing and has no fill wave) the front stops where it was and,
// with the droplet chain, dissolves into small evaporating beads (0.4 s); on a catch they fade while the splash plays at
// the pearl. The bulb never overlaps the pearl: within 0.03 u of the pearl rim it is absorbed (V7).
// Wave C (visuals-chase-front-not-brightest): the glint is 0.5 u half size (a value the fire and electric overlays design
// their shape 3 for), its flicker stays between 0.8 and 1.0 opacity (floor 0.7), and a soft halo in the front color is
// drawn under it, so the front is the brightest moving thing on screen (contract 25.5).
using System;
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    public sealed class RetractionView
    {
        public const float BulbRadius = 0.26f;
        public const float BulbStretch = 1.32f;
        public const float DropletSpacing = 0.45f;
        public const float DropletFirstOffset = 0.14f;
        public const float DropletMinRadius = 0.07f;
        public const float DropletMaxRadius = 0.12f;
        /// <summary>Contract 24: on a saved chased return the droplets and the front evaporate over this time.</summary>
        public const float AbsorbSeconds = 0.4f;
        public const float CatchFadeSeconds = 0.3f;
        public const float PearlClearance = 0.03f;
        /// <summary>Free liquid-less gap between the bulb's round back and the newest droplet (world units).</summary>
        public const float DropletGapBehindBulb = 0.1f;
        public const int MaxDroplets = 600;

        /// <summary>Half size of the front glint quad (world units). Cross-package value: the fire and electric overlay
        /// shaders design their shape 3 (Glint) interior for this size (wave C fix plan).</summary>
        public const float GlintHalfSize = 0.5f;
        /// <summary>Glint shape parameters (core size, ray length, ray half width), local units of the quad. The fire and
        /// electric overlays receive these unchanged (their shape 3 is designed for them and the 0.5 u half size).</summary>
        public static readonly Vector3 GlintShape = new Vector3(0.22f, 0.3f, 0.08f);
        /// <summary>Liquid glint parameters: the shared Overlay.hlsl sparkle is a plain Gaussian core, so the liquid front
        /// gets a wider core (0.2 u) and slightly longer, wider rays to stay the brightest moving thing (contract 25.5).</summary>
        public static readonly Vector3 LiquidGlintShape = new Vector3(0.4f, 0.36f, 0.1f);
        /// <summary>The glint flicker re-rolls its level at this rate (Hz).</summary>
        public const float GlintFlickerHz = 15f;
        public const float GlintMinOpacity = 0.8f;
        public const float GlintMaxOpacity = 1f;
        /// <summary>Absolute floor of the glint opacity.</summary>
        public const float GlintFloor = 0.7f;
        /// <summary>Soft halo under the glint, in the front color (world half size of its quad, opacity).</summary>
        public const float GlintHaloHalfSize = 1.2f;
        public const float GlintHaloOpacity = 0.35f;
        /// <summary>Halo shape parameters (glow peak radius, glow width), local units: the glow peaks just outside the
        /// bulb's visible edge (0.34 u) and stays faint over the bulb so its own specular highlight keeps its punch.</summary>
        public static readonly Vector3 GlintHaloShape = new Vector3(0.28f, 0.3f, 0f);

        private enum Mode { None, Live, Absorb, Burst }

        private readonly int player;
        private readonly FieldBlobDrawer bulb;
        private readonly QuadBatch droplets;
        private readonly Vector2[] dropPos = new Vector2[MaxDroplets];
        private readonly float[] dropRadius = new float[MaxDroplets];
        private int dropCount;

        private Mode mode;
        private float fadeStart;
        private Vector2 bulbCenter, bulbDir;
        private float bulbRadius, bulbAmplitude = 1f, bulbStretch = BulbStretch;

        public RetractionView(int player, Transform parent, Material blobMaterial, Shader beadShader)
        {
            this.player = player;
            bulb = new FieldBlobDrawer("RetractionBulb" + player, parent, blobMaterial);
            droplets = new QuadBatch("Droplets" + player, parent, beadShader, QuadBatch.QueueDroplets, 10);
        }

        /// <summary>True while this player's retraction front is live (chased and drawn).</summary>
        public bool HasFront { get; private set; }

        /// <summary>World position of the spark (the bulb's leading edge, at RenderSparkS) while HasFront.</summary>
        public Vector2 FrontWorld { get; private set; }

        /// <summary>Center of the bulb in the last frame (world).</summary>
        public Vector2 BulbCenter => bulbCenter;

        /// <summary>Droplets drawn in the last frame.</summary>
        public int DropletCount => dropCount;

        /// <summary>Arc length of the bulb's leading edge in the last live frame (Sr, or less once it meets the pearl).</summary>
        public double LeadS { get; private set; }

        /// <summary>Arc length of the interpolated head in the last live frame.</summary>
        public double RenderLength { get; private set; }

        /// <summary>Deterministic droplet radius for chain index k (visible radius 0.07 to 0.12). As in the reference, the
        /// droplets grow along the chain: small next to the cut point, larger toward the retraction front, with a small
        /// per-index jitter (+/- 0.01 u).</summary>
        public static float DropletRadius(int player, int k)
        {
            float grow = 1f - Mathf.Exp(-Mathf.Max(0, k) / 3f);
            float jitter = (Hash01(k * 7 + player * 131 + 3) - 0.5f) * 0.02f;
            float r = DropletMinRadius + 0.005f + (DropletMaxRadius - DropletMinRadius - 0.01f) * grow + jitter;
            return Mathf.Clamp(r, DropletMinRadius, DropletMaxRadius);
        }

        /// <summary>Arc length of droplet k of a chain cut at sCut.</summary>
        public static double DropletS(double sCut, int k)
        {
            return sCut + DropletFirstOffset + k * DropletSpacing;
        }

        public void Reset()
        {
            mode = Mode.None;
            HasFront = false;
            dropCount = 0;
            bulb.Hide();
            droplets.Hide();
        }

        public void Hide()
        {
            HasFront = false;
            bulb.Hide();
            droplets.Hide();
        }

        public void Destroy()
        {
            bulb.Destroy();
            droplets.Destroy();
        }

        public void OnCut(SimEvent e, float now)
        {
            // The live state is read from PlayerState.Spark in Tick; nothing to store.
        }

        public void OnReturn(SimEvent e, float now)
        {
            if (mode != Mode.Live) return;
            mode = Mode.Absorb;
            fadeStart = now;
        }

        public void OnCaught(float now)
        {
            if (mode == Mode.Live || mode == Mode.Absorb)
            {
                mode = Mode.Burst;
                fadeStart = now;
            }
        }

        public void OnEliminated(float now)
        {
            OnCaught(now);
        }

        public void Tick(ActorContext ctx)
        {
            Simulation sim = ctx.Sim;
            if (player >= sim.Players.Count)
            {
                Hide();
                return;
            }
            PlayerState p = sim.Players[player];
            float now = ctx.Time;
            if (p.Alive && !p.Home && p.Spark != null && p.Trail.Count >= 2)
            {
                mode = Mode.Live;
                TickLive(ctx, p, now);
                return;
            }
            HasFront = false;
            if (mode == Mode.Live)
            {
                // The chase ended without an event we saw (session hiccup): absorb what is on screen.
                mode = Mode.Absorb;
                fadeStart = now;
            }
            if (mode == Mode.Absorb || mode == Mode.Burst)
            {
                float duration = mode == Mode.Absorb ? AbsorbSeconds : CatchFadeSeconds;
                float t = now - fadeStart;
                if (t >= duration)
                {
                    mode = Mode.None;
                    bulb.Hide();
                    droplets.Hide();
                    dropCount = 0;
                    return;
                }
                float u = t / duration;
                if (mode == Mode.Absorb)
                {
                    // Contract 24: the front stops where it was; its liquid leaves the field quickly and lives on as a bead
                    // that evaporates with the droplets (shrinking, drifting slightly, fading).
                    // Fire and electricity draw no liquid neck here: the bulb leaves the field at once (no residual glow).
                    BiomeTheme theme = BiomeTheme.Current;
                    bool liquid = theme == null || theme.Id == BiomeId.Liquid;
                    float fieldF = liquid ? Mathf.Clamp01(1f - t / 0.12f) : 0f;
                    if (fieldF > 0.01f) bulb.Show(player, bulbCenter, bulbRadius, bulbAmplitude * fieldF, bulbStretch, Angle(bulbDir));
                    else bulb.Hide();
                    DrawEvaporation(ctx, u);
                    return;
                }
                // Catch: the front fades twice as fast while the splash plays at the pearl.
                float f = 1f - u;
                float bulbF = Mathf.Clamp01(1f - 2f * u);
                if (bulbF > 0.01f) bulb.Show(player, bulbCenter, bulbRadius * Mathf.Lerp(0.6f, 1f, bulbF), bulbAmplitude * bulbF, bulbStretch, Angle(bulbDir));
                else bulb.Hide();
                DrawDroplets(ctx, f, Mathf.Lerp(0.55f, 1f, f));
                return;
            }
            bulb.Hide();
            droplets.Hide();
            dropCount = 0;
        }

        /// <summary>
        /// Opacity of the front glint at animation time t (seconds): a steady flicker between GlintMinOpacity and
        /// GlintMaxOpacity, re-rolled every 1 / GlintFlickerHz s with a smooth shimmer on top, never below GlintFloor
        /// (wave C: the old flicker dropped to 0.25 on about a third of its steps and the spark stopped reading as the
        /// brightest moving thing, contract 25.5).
        /// </summary>
        public static float GlintOpacity(float t, int player)
        {
            if (float.IsNaN(t) || float.IsInfinity(t)) t = 0f;
            int step = Mathf.FloorToInt(t * GlintFlickerHz);
            float stepLevel = Hash01(step * 13 + player * 7);
            float shimmer = 0.5f + 0.5f * Mathf.Sin(t * 47f + player);
            float u = 0.6f * stepLevel + 0.4f * shimmer;
            float opacity = GlintMinOpacity + (GlintMaxOpacity - GlintMinOpacity) * u;
            return Mathf.Clamp(opacity, GlintFloor, GlintMaxOpacity);
        }

        /// <summary>
        /// The front glint (overlay batch), drawn above droplets, threads and pearls (QueueOverlays): first a soft halo in
        /// the front color (OverlayShape.Halo, the shared soft glow id the edge indicator and the ring use), then the white
        /// sparkle (OverlayShape.Glint) at a constant half size of GlintHalfSize; the fire and electric overlays design
        /// their shape 3 interior for that size.
        /// </summary>
        public void DrawGlint(ActorContext ctx)
        {
            if (!HasFront || ctx.Overlays == null) return;
            float t = ctx.Time;
            Vector2 light = new Vector2(-0.45f, 0.6f).normalized;
            Vector2 at = bulbCenter + light * bulbRadius * 0.45f;
            ctx.Overlays.AddOverlay(at, new Vector2(GlintHaloHalfSize, GlintHaloHalfSize), 0f, OverlayShape.Halo,
                                    GlintHaloShape, ctx.LinearColor(player), GlintHaloOpacity, ctx.Lobes);
            ctx.Overlays.AddOverlay(at, new Vector2(GlintHalfSize, GlintHalfSize), t * 1.3f, OverlayShape.Glint,
                                    GlintShapeFor(BiomeTheme.Current), Color.white, GlintOpacity(t, player), ctx.Lobes);
        }

        /// <summary>The glint shape parameters for a biome (LiquidGlintShape for Liquid or no theme, else GlintShape).</summary>
        public static Vector3 GlintShapeFor(BiomeTheme theme)
        {
            return theme == null || theme.Id == BiomeId.Liquid ? LiquidGlintShape : GlintShape;
        }

        private void TickLive(ActorContext ctx, PlayerState p, float now)
        {
            Trail trail = p.Trail;
            IReadOnlyList<Vec2d> points = trail.Points;
            IReadOnlyList<double> arc = trail.Arc;
            double sCut = p.Spark.SCut;
            double sr = ctx.Session.RenderSparkS(player);
            if (double.IsNaN(sr)) sr = p.Spark.S;
            Vector2 tip = ctx.Session.RenderPos(player);
            double lr = TrailCurve.RenderLength(p, tip);
            float headRadius = (float)ctx.Sim.Config.HeadRadius;

            // Bulb: leading edge at Sr, round back behind it; it grows during the first 0.3 u after the cut.
            float grow = Mathf.Lerp(0.45f, 1f, Mathf.Clamp01((float)((sr - sCut) / 0.3)));
            double lead = sr;
            double maxLead = lr - headRadius - PearlClearance;
            float shrink = 1f;
            if (lead > maxLead)
            {
                shrink = Mathf.Clamp01(1f - (float)((lead - maxLead) / 0.25));
                lead = maxLead;
            }
            float jitterA = Mathf.Sin(now * 2f * Mathf.PI * 17f + player * 1.7f);
            float jitterB = Mathf.Sin(now * 2f * Mathf.PI * 12.5f + player * 0.9f);
            float jitterC = Mathf.Sin(now * 2f * Mathf.PI * 21f + player * 2.3f);
            bulbStretch = BulbStretch * (1f + 0.07f * jitterB);
            bulbRadius = BulbRadius * grow * shrink * (1f + 0.04f * jitterC);
            float semiMajor = bulbRadius * bulbStretch;
            LeadS = lead;
            RenderLength = lr;
            double centerS = Math.Max(sCut + 0.02, lead - 0.82 * semiMajor);
            int segment = -1;
            Vector2 center = TrailCurve.Evaluate(points, arc, centerS, ref segment);
            bulbDir = TrailCurve.Direction(points, arc, centerS, ref segment);
            var perp = new Vector2(-bulbDir.y, bulbDir.x);
            bulbCenter = center + perp * (0.018f * jitterA) + bulbDir * (0.012f * jitterB);
            bulbAmplitude = 1.05f + 0.08f * jitterA;
            if (bulbRadius > 0.01f) bulb.Show(player, bulbCenter, bulbRadius, bulbAmplitude, bulbStretch, Angle(bulbDir));
            else bulb.Hide();
            int seg2 = -1;
            FrontWorld = TrailCurve.Evaluate(points, arc, Math.Min(sr, lr), ref seg2);
            HasFront = shrink > 0.05f;

            // Droplets left behind the bulb's back edge, every 0.45 u from the cut point.
            double back = centerS - 0.95 * semiMajor;   // the bulb's round back
            dropCount = 0;
            int dseg = -1;
            for (int k = 0; k < MaxDroplets; k++)
            {
                double s = DropletS(sCut, k);
                if (s > back - DropletGapBehindBulb) break;
                float appear = Mathf.Clamp01((float)((back - s) / 0.2));
                float r = DropletRadius(player, k) * Mathf.Lerp(0.5f, 1f, appear * appear * (3f - 2f * appear));
                Vector2 c = TrailCurve.Evaluate(points, arc, s, ref dseg);
                float phase = k * 2.1f + player * 0.37f;
                c += new Vector2(Mathf.Sin(now * 29f + phase), Mathf.Cos(now * 23f + phase * 0.7f)) * 0.008f;
                r *= 1f + 0.05f * Mathf.Sin(now * 19f + phase * 1.3f);
                dropPos[dropCount] = c;
                dropRadius[dropCount] = r;
                dropCount++;
            }
            DrawDroplets(ctx, 1f, 1f);
        }

        /// <summary>Contract 24 saved chased return: droplets and the front bead shrink, drift upward a little and fade.</summary>
        private void DrawEvaporation(ActorContext ctx, float u)
        {
            droplets.Begin();
            Color color = ctx.LinearColor(player);
            float lift = 1f - (1f - u) * (1f - u);
            for (int k = 0; k < dropCount; k++)
            {
                float delay = 0.25f * Hash01(k * 5 + player * 61 + 9);
                float v = Mathf.Clamp01((u - delay) / (1f - delay));
                float r = dropRadius[k] * Mathf.Pow(1f - v, 0.7f);
                if (r < 0.004f) continue;
                float opacity = v < 0.6f ? 1f : (1f - v) / 0.4f;
                var drift = new Vector2(0.06f * (Hash01(k * 5 + player * 61 + 10) - 0.5f), 0.08f) * lift;
                droplets.AddBead(dropPos[k] + drift, r, Vector2.right, 1f, color, opacity, 0.3f, ctx.Lobes, 0.5f);
            }
            float br = bulbRadius * 0.85f * Mathf.Pow(1f - u, 0.7f);
            if (br > 0.004f)
            {
                droplets.AddBead(bulbCenter + new Vector2(0f, 0.08f) * lift, br, bulbDir, Mathf.Lerp(1.25f, 1f, u), color,
                                 u < 0.6f ? 1f : (1f - u) / 0.4f, 0.32f, ctx.Lobes, 0.55f);
            }
            droplets.End();
        }

        private void DrawDroplets(ActorContext ctx, float opacity, float radiusScale)
        {
            droplets.Begin();
            Color color = ctx.LinearColor(player);
            for (int k = 0; k < dropCount; k++)
            {
                droplets.AddBead(dropPos[k], dropRadius[k] * radiusScale, Vector2.right, 1f, color, opacity, 0.34f, ctx.Lobes, 0.55f);
            }
            droplets.End();
        }

        private static float Angle(Vector2 d)
        {
            return Mathf.Atan2(d.y, d.x);
        }

        /// <summary>Deterministic hash of an integer to [0, 1).</summary>
        public static float Hash01(int k)
        {
            unchecked
            {
                uint h = (uint)k * 2654435761u;
                h ^= h >> 15;
                h *= 2246822519u;
                h ^= h >> 13;
                h *= 3266489917u;
                h ^= h >> 16;
                return (h & 0xFFFFFF) / 16777216f;
            }
        }
    }
}
