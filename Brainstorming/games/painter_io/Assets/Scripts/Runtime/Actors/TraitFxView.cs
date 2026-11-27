// Owned by traits-fx (wave D-2). docs/BIOME_TRAITS.md section 5 (generic visuals) and 7.2 (kill reward presentation):
// the actor-side visuals of the biome traits, drawn with the current biome's Overlay shader (trait shapes 16 - 21, see
// OverlayShape), so every biome styles them its own way. Nothing here tests the biome or a biome id: each visual follows
// the round's traits and the sim state only (SimView / PlayerState), so any trait shows in any biome.
// - Conduction: while a pearl runs on its own territory with the trait on, a short speed streak behind it (shape 16)
//   and a brighter glow around it (shape 1).
// - ArcReach: when an enemy head is within ContactRadius x ReachScale of an exposed point of a trail (arc length up to
//   L - HeadGrace) and the contact is widened (ContactScale > 1), a small flickering spark line between them (shape 17),
//   so the larger reach is visible before it cuts. A shielded trail draws none (it cannot be cut).
// - KillSpeedBoost: an aura around the pearl, stronger per level (SpeedMultiplier - 1) / PerKill (shape 18), with a burst
//   on each SpeedBoosted event.
// - KillShield: a glossy film around the pearl (shape 19) that pops in on ShieldStarted, shimmers and blinks in its
//   last ShieldWarnSeconds and bursts on ShieldEnded; a small timer ring beside the pearl (shape 20); a shimmering strip
//   along the whole uncuttable trail (shape 21, a strip mesh drawn under the pearls).
// Every shape stays below sRGB luma 235 (contract 25.5: the chase front stays the brightest moving thing).
using System;
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace PainterIO.Runtime
{
    public sealed class TraitFxView
    {
        /// <summary>Overlay shape ids of the trait visuals (shared by the three biome overlay shaders).</summary>
        public const int ShapeStreak = 16;
        public const int ShapeArc = 17;
        public const int ShapeAura = 18;
        public const int ShapeFilm = 19;
        public const int ShapeTimer = 20;
        public const int ShapeShimmer = 21;

        /// <summary>The reach arc shows within this multiple of the cut contact radius (BIOME_TRAITS 5).</summary>
        public const double ReachScale = 1.25;
        /// <summary>Conduction streak: length and half width behind the pearl (world units).</summary>
        public const float StreakLength = 1.3f;
        public const float StreakHalfWidth = 0.3f;
        /// <summary>Conduction streak level rate (per second) when it switches on or off.</summary>
        public const float StreakRate = 7f;
        /// <summary>Speed aura quad half size, as a multiple of the pearl radius.</summary>
        public const float AuraScale = 2f;
        /// <summary>Seconds of the aura burst on SpeedBoosted.</summary>
        public const float BoostBurstSeconds = 0.45f;
        /// <summary>Shield film radius, as a multiple of the pearl radius.</summary>
        public const float FilmScale = 1.5f;
        /// <summary>Seconds of the film pop on ShieldStarted and of its burst on ShieldEnded.</summary>
        public const float FilmPopSeconds = 0.28f;
        /// <summary>The film blinks during the last ShieldWarnSeconds of the shield.</summary>
        public const float ShieldWarnSeconds = 0.8f;
        /// <summary>Timer ring: radius, tube half width and distance of its center from the pearl rim (world units).</summary>
        public const float TimerRadius = 0.2f;
        public const float TimerTube = 0.055f;
        public const float TimerGap = 0.3f;
        /// <summary>Shimmer strip half width (world units; the thread's visible radius is 0.17) and sample spacing.</summary>
        public const float ShimmerHalfWidth = 0.26f;
        public const float ShimmerSpacing = 0.15f;
        /// <summary>Render queue of the shimmer strip: after the composite, under droplets, pearls and overlays.</summary>
        public const int QueueShimmer = QuadBatch.QueueDroplets - 1;

        /// <summary>Border ride (rule v1.9): the streak tint (linear neon yellow, as the arena frame's glow) ...</summary>
        public static readonly Color RideNeon = new Color(1f, 0.80f, 0.03f, 1f);
        /// <summary>... how far the pearl color moves toward it, and how much longer the streak gets while riding.</summary>
        public const float RideTint = 0.55f;
        public const float RideStretch = 0.8f;

        private sealed class PlayerFx
        {
            public float Conduct;
            public float Ride;
            public float BoostStart = -100f;
            public float ShieldStart = -100f;
            public float ShieldEndStart = -100f;
            public Vector2 ShieldEndPos;
            public float ShieldEndRadius;
        }

        private readonly PlayerFx[] players = new PlayerFx[Tuning.PlayerCount];
        private readonly ShimmerStrip strip;

        public TraitFxView(Transform parent, Shader overlayShader)
        {
            for (int i = 0; i < players.Length; i++) players[i] = new PlayerFx();
            strip = new ShimmerStrip(parent, overlayShader);
        }

        /// <summary>Quads drawn in the last frame (tests and logs).</summary>
        public int LastQuads { get; private set; }

        /// <summary>Reach arcs drawn in the last frame.</summary>
        public int LastArcs { get; private set; }

        /// <summary>Shimmer strip vertices uploaded in the last frame.</summary>
        public int LastStripVertices => strip.VertexCount;

        public void Reset()
        {
            for (int i = 0; i < players.Length; i++) players[i] = new PlayerFx();
            strip.Clear();
            LastQuads = 0;
            LastArcs = 0;
        }

        public void Hide()
        {
            strip.Clear();
        }

        public void Destroy()
        {
            strip.Destroy();
        }

        /// <summary>SpeedBoosted, ShieldStarted and ShieldEnded drive the bursts and pops (now = ActorContext.Time).</summary>
        public void OnEvent(SimEvent e, float now, Vector2 lastPearl, float lastRadius)
        {
            if (e == null || e.Player < 0 || e.Player >= players.Length) return;
            PlayerFx fx = players[e.Player];
            switch (e.Type)
            {
                case SimEventType.SpeedBoosted:
                    fx.BoostStart = now;
                    break;
                case SimEventType.ShieldStarted:
                    fx.ShieldStart = now;
                    fx.ShieldEndStart = -100f;
                    break;
                case SimEventType.ShieldEnded:
                    fx.ShieldEndStart = now;
                    fx.ShieldEndPos = lastPearl;
                    fx.ShieldEndRadius = lastRadius;
                    break;
            }
        }

        public void Tick(ActorContext ctx, PearlView[] pearls)
        {
            int quads = ctx.Overlays != null ? ctx.Overlays.Count : 0;
            LastArcs = 0;
            strip.Begin(ctx.OverlayShader);
            Simulation sim = ctx.Sim;
            SimView view = sim.View;
            RuleTraits traits = sim.Config.Traits ?? RuleTraits.Classic;
            int n = Mathf.Min(sim.Players.Count, players.Length);
            float now = ctx.Time;
            double renderTime = sim.Time - (1.0 - ctx.Session.Alpha) * sim.Config.Dt;
            bool conduction = view.HomeSpeed > sim.Config.PawnSpeed * (1.0 + 1e-9);
            double perKill = PerKill(traits);

            for (int i = 0; i < n; i++)
            {
                PlayerState p = sim.Players[i];
                PlayerFx fx = players[i];
                PearlView pearl = pearls != null && i < pearls.Length ? pearls[i] : null;
                bool visible = p.Alive && pearl != null && pearl.WasVisible;
                Vector2 pos = visible ? pearl.LastPosition : ctx.Session.RenderPos(i);
                float radius = visible ? pearl.LastRadius : (float)sim.Config.HeadRadius;
                Color color = ctx.LinearColor(i);

                // Shield end burst (plays where the pearl was, also after the pearl died).
                float endAge = now - fx.ShieldEndStart;
                if (endAge >= 0f && endAge < FilmPopSeconds)
                {
                    float k = endAge / FilmPopSeconds;
                    Vector2 at = p.Alive ? pos : fx.ShieldEndPos;
                    float r = (fx.ShieldEndRadius > 0f ? fx.ShieldEndRadius : radius) * FilmScale * (1f + 0.35f * k);
                    float half = r / 0.86f;
                    ctx.Overlays?.AddOverlay(at, new Vector2(half, half), 0f, OverlayShape.Film,
                                             new Vector3(0.86f, 1f, 1f - k), color, (1f - k) * (1f - k), ctx.Lobes);
                }
                if (!p.Alive)
                {
                    fx.Conduct = 0f;
                    continue;
                }

                // Conduction: speed streak and brighter glow while home with the trait on. Rule v1.9 border ride: the same
                // streak, longer and tinted toward the border's neon yellow, while the pearl rides the boundary.
                bool riding = view.IsBorderRiding(i);
                float target = (conduction && p.Home) || riding ? 1f : 0f;
                fx.Conduct = Mathf.MoveTowards(fx.Conduct, target, StreakRate * Mathf.Max(ctx.Dt, 0f));
                fx.Ride = Mathf.MoveTowards(fx.Ride, riding ? 1f : 0f, StreakRate * Mathf.Max(ctx.Dt, 0f));
                Color streakColor = fx.Ride > 0.01f ? Color.Lerp(color, RideNeon, RideTint * fx.Ride) : color;
                if (fx.Conduct > 0.01f && visible && ctx.IsOnScreen(pos, 2f))
                {
                    var dir = new Vector2(Mathf.Cos((float)p.Heading), Mathf.Sin((float)p.Heading));
                    float len = StreakLength * (1f + RideStretch * fx.Ride);
                    Vector2 center = pos - dir * (radius * 0.75f + len * 0.5f);
                    float angle = Mathf.Atan2(dir.y, dir.x);
                    ctx.Overlays?.AddOverlay(center, new Vector2(len * 0.5f, StreakHalfWidth), angle, OverlayShape.Streak,
                                             new Vector3(0.85f * fx.Conduct, StreakHalfWidth / (len * 0.5f), i * 0.37f), streakColor, 1f, ctx.Lobes);
                    float halo = radius * 1.9f;
                    ctx.Overlays?.AddOverlay(pos, new Vector2(halo, halo), 0f, OverlayShape.Halo,
                                             new Vector3(radius * 1.12f / halo, 0.2f, 0f), Color.Lerp(streakColor, Color.white, 0.5f), 0.4f * fx.Conduct, ctx.Lobes);
                }

                // KillSpeedBoost: aura per level, burst on each boost.
                double multiplier = p.SpeedMultiplier;
                float burstAge = now - fx.BoostStart;
                float burst = burstAge >= 0f && burstAge < BoostBurstSeconds ? 1f - burstAge / BoostBurstSeconds : 0f;
                if ((multiplier > 1.0 + 1e-6 || burst > 0f) && visible && ctx.IsOnScreen(pos, 2f))
                {
                    float level = (float)Math.Max(0.0, (multiplier - 1.0) / perKill);
                    float half = radius * AuraScale;
                    ctx.Overlays?.AddOverlay(pos, new Vector2(half, half), 0f, OverlayShape.Aura,
                                             new Vector3(Mathf.Max(level, burst), radius / half, burst), color, 1f, ctx.Lobes);
                }

                // KillShield: film, timer ring, shimmering trail.
                if (view.IsShielded(i))
                {
                    double end = view.ShieldEndTime(i);
                    float remaining = (float)Math.Max(0.0, end - renderTime);
                    float duration = ShieldDuration(traits);
                    float popAge = now - fx.ShieldStart;
                    float pop = popAge >= 0f && popAge < FilmPopSeconds ? 1f - popAge / FilmPopSeconds : 0f;
                    float scale = popAge >= 0f && popAge < FilmPopSeconds ? PopScale(popAge / FilmPopSeconds) : 1f;
                    bool warn = remaining < ShieldWarnSeconds;
                    float blink = warn ? 0.45f + 0.55f * (Mathf.Sin(now * Mathf.PI * 2f * 7f) > 0f ? 1f : 0f) : 1f;
                    if (visible && ctx.IsOnScreen(pos, 2f))
                    {
                        float r = radius * FilmScale * scale;
                        float half = r / 0.86f;
                        ctx.Overlays?.AddOverlay(pos, new Vector2(half, half), (float)p.Heading, OverlayShape.Film,
                                                 new Vector3(0.86f, warn ? 1f : 0.3f, pop), color, blink, ctx.Lobes);
                        float timerHalf = (TimerRadius + TimerTube) * 1.25f;
                        Vector2 at = pos + new Vector2(0.7071f, 0.7071f) * (radius + TimerGap);
                        ctx.Overlays?.AddOverlay(at, new Vector2(timerHalf, timerHalf), 0f, OverlayShape.Timer,
                                                 new Vector3(TimerRadius / timerHalf, TimerTube / timerHalf, duration > 1e-3f ? Mathf.Clamp01(remaining / duration) : 0f),
                                                 color, 0.95f, ctx.Lobes);
                    }
                    if (!p.Home && p.Trail.Count >= 2) strip.AddTrail(p, pos, color, (warn ? 0.6f : 1f) * blink, ctx.Lobes);
                }
            }

            // ArcReach: spark lines between enemy heads and exposed trail points within the widened reach.
            double contact = sim.Config.ContactRadius;
            if (sim.Config.ContactScale > 1.0 + 1e-9)
            {
                double reach = contact * ReachScale;
                double grace = sim.Config.HeadGrace;
                for (int v = 0; v < n; v++)
                {
                    PlayerState victim = sim.Players[v];
                    if (!victim.Alive || victim.Home || victim.Trail.Length <= grace || view.IsShielded(v)) continue;
                    for (int a = 0; a < n; a++)
                    {
                        if (a == v) continue;
                        PlayerState attacker = sim.Players[a];
                        if (!attacker.Alive) continue;
                        if (!victim.Trail.ClosestPointWithin(attacker.Pos, reach, victim.Trail.Length - grace, out double s, out double dist)) continue;
                        Vector2 head = pearls != null && a < pearls.Length && pearls[a] != null && pearls[a].WasVisible
                            ? pearls[a].LastPosition : ctx.Session.RenderPos(a);
                        int segment = -1;
                        Vector2 point = TrailCurve.Evaluate(victim.Trail.Points, victim.Trail.Arc, s, ref segment);
                        if (!ctx.IsOnScreen((head + point) * 0.5f, 1.5f)) continue;
                        float closeness = 1f - Mathf.Clamp01((float)((dist - contact) / Math.Max(reach - contact, 1e-6)));
                        DrawArc(ctx, head, point, (float)sim.Config.HeadRadius, ctx.LinearColor(a), closeness, a * 4 + v);
                    }
                }
            }

            strip.End();
            LastQuads = (ctx.Overlays != null ? ctx.Overlays.Count : 0) - quads;
        }

        private void DrawArc(ActorContext ctx, Vector2 head, Vector2 point, float headRadius, Color color, float closeness, int seed)
        {
            Vector2 d = point - head;
            float len = d.magnitude;
            if (len < 1e-4f) return;
            Vector2 dir = d / len;
            Vector2 a = head + dir * Mathf.Min(headRadius * 0.85f, len * 0.5f);   // leaves from the pearl rim
            Vector2 seg = point - a;
            float segLen = seg.magnitude;
            if (segLen < 0.04f) return;
            float halfX = segLen * 0.5f / 0.88f;
            float halfY = Mathf.Max(0.14f, halfX * 0.35f);
            float tick = Mathf.Floor(ctx.Time * 22f + seed * 3.1f);
            float flicker = 0.62f + 0.38f * Hash01(tick * 7.13f + seed);
            ctx.Overlays?.AddOverlay((a + point) * 0.5f, new Vector2(halfX, halfY), Mathf.Atan2(dir.y, dir.x), OverlayShape.Arc,
                                     new Vector3(seed * 0.173f + 0.31f, halfY / halfX, 0.022f), color,
                                     (0.55f + 0.45f * closeness) * flicker, ctx.Lobes);
            LastArcs++;
        }

        /// <summary>Overshooting pop of the film (0.6 -> 1.08 -> 1 over the pop).</summary>
        public static float PopScale(float k)
        {
            k = Mathf.Clamp01(k);
            if (k < 0.6f) return Mathf.Lerp(0.6f, 1.08f, Mathf.SmoothStep(0f, 1f, k / 0.6f));
            return Mathf.Lerp(1.08f, 1f, Mathf.SmoothStep(0f, 1f, (k - 0.6f) / 0.4f));
        }

        /// <summary>KillSpeedBoost's PerKill of the round (its default when unset).</summary>
        public static double PerKill(RuleTraits traits)
        {
            TraitSpec spec = traits?.Get(TraitId.KillSpeedBoost);
            double v = spec != null ? spec.P1 : double.NaN;
            return v > 1e-6 && !double.IsInfinity(v) ? v : TraitDefaults.KillSpeedBoostPerKill;
        }

        /// <summary>KillShield's Duration of the round (its default when unset), for the timer ring.</summary>
        public static float ShieldDuration(RuleTraits traits)
        {
            TraitSpec spec = traits?.Get(TraitId.KillShield);
            double v = spec != null ? spec.P1 : double.NaN;
            return (float)(v > 1e-6 && !double.IsInfinity(v) ? v : TraitDefaults.KillShieldDuration);
        }

        private static float Hash01(float x)
        {
            uint h = (uint)(int)Mathf.Floor(x) * 2654435761u;
            h ^= h >> 15;
            h *= 2246822519u;
            h ^= h >> 13;
            return (h & 0xFFFFFF) / 16777216f;
        }

        /// <summary>
        /// The shimmering strips of the shielded trails: ONE dynamic mesh (all players), the current Overlay shader with
        /// trait shape 21, drawn after the composite and under the droplets, pearls and overlays. Vertex data as
        /// Overlay.hlsl shape 21: UV0 = (0, cross coordinate, half width, arc length), UV1 = (21, intensity, 0, 0),
        /// UV2 = (1, 0, 0, lobes), color = (linear rgb, opacity).
        /// </summary>
        private sealed class ShimmerStrip
        {
            private readonly GameObject go;
            private readonly Mesh mesh;
            private readonly MeshRenderer renderer;
            private readonly List<Vector3> vertices = new List<Vector3>(256);
            private readonly List<Color> colors = new List<Color>(256);
            private readonly List<Vector4> uv0 = new List<Vector4>(256);
            private readonly List<Vector4> uv1 = new List<Vector4>(256);
            private readonly List<Vector4> uv2 = new List<Vector4>(256);
            private readonly List<int> indices = new List<int>(768);
            private readonly List<Vector2> centers = new List<Vector2>(256);
            private readonly List<float> arcs = new List<float>(256);
            private Material material;
            private Vector2 min, max;

            public ShimmerStrip(Transform parent, Shader shader)
            {
                go = new GameObject("TraitShimmer");
                go.transform.SetParent(parent, false);
                mesh = new Mesh { name = "TraitShimmer" };
                mesh.MarkDynamic();
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                renderer = go.AddComponent<MeshRenderer>();
                renderer.shadowCastingMode = ShadowCastingMode.Off;
                renderer.receiveShadows = false;
                renderer.lightProbeUsage = LightProbeUsage.Off;
                renderer.reflectionProbeUsage = ReflectionProbeUsage.Off;
                renderer.motionVectorGenerationMode = MotionVectorGenerationMode.ForceNoMotion;
                renderer.allowOcclusionWhenDynamic = false;
                renderer.enabled = false;
                SetShader(shader);
            }

            public int VertexCount { get; private set; }

            private void SetShader(Shader shader)
            {
                if (shader == null) return;
                if (material == null)
                {
                    material = new Material(shader) { name = "TraitShimmer", renderQueue = QueueShimmer };
                    renderer.sharedMaterial = material;
                    return;
                }
                if (material.shader != shader) material.shader = shader;
                material.renderQueue = QueueShimmer;
            }

            public void Begin(Shader shader)
            {
                SetShader(shader);   // follows the biome's Overlay shader (contract 25.2)
                vertices.Clear();
                colors.Clear();
                uv0.Clear();
                uv1.Clear();
                uv2.Clear();
                indices.Clear();
                min = new Vector2(float.MaxValue, float.MaxValue);
                max = new Vector2(float.MinValue, float.MinValue);
            }

            /// <summary>One strip along the display curve of the trail (sampled every ShimmerSpacing), ending at the head.</summary>
            public void AddTrail(PlayerState p, Vector2 head, Color color, float opacity, float lobes)
            {
                Trail trail = p.Trail;
                double length = TrailCurve.RenderLength(p, head);
                if (length < 0.05) return;
                centers.Clear();
                arcs.Clear();
                int segment = -1;
                int steps = Mathf.Clamp(Mathf.CeilToInt((float)(length / ShimmerSpacing)), 1, 2000);
                for (int k = 0; k < steps; k++)
                {
                    double s = length * k / steps;
                    centers.Add(TrailCurve.Evaluate(trail.Points, trail.Arc, s, ref segment));
                    arcs.Add((float)s);
                }
                centers.Add(head);
                arcs.Add((float)length);
                if (vertices.Count + centers.Count * 2 > 60000) return;
                var c = new Color(color.r, color.g, color.b, Mathf.Clamp01(opacity));
                var a1 = new Vector4(ShapeShimmer, 1f, 0f, 0f);
                var a2 = new Vector4(1f, 0f, 0f, lobes);
                int start = vertices.Count;
                int count = centers.Count;
                for (int k = 0; k < count; k++)
                {
                    Vector2 prev = centers[Mathf.Max(0, k - 1)];
                    Vector2 next = centers[Mathf.Min(count - 1, k + 1)];
                    Vector2 t = next - prev;
                    t = t.sqrMagnitude > 1e-10f ? t.normalized : Vector2.right;
                    var nrm = new Vector2(-t.y, t.x);
                    // Tapered over the first and last 0.2 u, so the strip never ends with a hard edge.
                    float taper = Mathf.Clamp01(arcs[k] / 0.2f) * Mathf.Clamp01(((float)length - arcs[k]) / 0.2f + 0.25f);
                    float hw = ShimmerHalfWidth * Mathf.Lerp(0.4f, 1f, taper);
                    Vector2 ctr = centers[k];
                    for (int side = -1; side <= 1; side += 2)
                    {
                        Vector2 pos = ctr + nrm * (hw * side);
                        vertices.Add(new Vector3(pos.x, pos.y, 0f));
                        uv0.Add(new Vector4(0f, side, hw, arcs[k]));
                        uv1.Add(a1);
                        uv2.Add(a2);
                        colors.Add(new Color(c.r, c.g, c.b, c.a * taper));
                    }
                    if (ctr.x - hw < min.x) min.x = ctr.x - hw;
                    if (ctr.y - hw < min.y) min.y = ctr.y - hw;
                    if (ctr.x + hw > max.x) max.x = ctr.x + hw;
                    if (ctr.y + hw > max.y) max.y = ctr.y + hw;
                    if (k == 0) continue;
                    int b = start + 2 * (k - 1);
                    indices.Add(b);
                    indices.Add(b + 2);
                    indices.Add(b + 1);
                    indices.Add(b + 2);
                    indices.Add(b + 3);
                    indices.Add(b + 1);
                }
            }

            public void End()
            {
                VertexCount = vertices.Count;
                if (vertices.Count == 0 || material == null)
                {
                    Clear();
                    return;
                }
                mesh.Clear(true);
                mesh.indexFormat = vertices.Count > 65000 ? IndexFormat.UInt32 : IndexFormat.UInt16;
                mesh.SetVertices(vertices);
                mesh.SetColors(colors);
                mesh.SetUVs(0, uv0);
                mesh.SetUVs(1, uv1);
                mesh.SetUVs(2, uv2);
                mesh.SetTriangles(indices, 0, false);
                Vector2 center = (min + max) * 0.5f;
                Vector2 size = max - min;
                mesh.bounds = new Bounds(new Vector3(center.x, center.y, 0f), new Vector3(size.x + 0.2f, size.y + 0.2f, 1f));
                if (!renderer.enabled) renderer.enabled = true;
            }

            public void Clear()
            {
                VertexCount = 0;
                if (renderer != null && renderer.enabled) renderer.enabled = false;
                if (mesh != null && mesh.vertexCount > 0) mesh.Clear(true);
            }

            public void Destroy()
            {
                LiquidRenderer.SafeDestroy(material);
                LiquidRenderer.SafeDestroy(mesh);
                LiquidRenderer.SafeDestroy(go);
            }
        }
    }
}
