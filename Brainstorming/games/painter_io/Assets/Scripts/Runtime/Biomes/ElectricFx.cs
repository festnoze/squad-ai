// Owned by ELEC (wave B-2, phase 2). Contract 25.4 and 25.5: the extra effects of the Électricité biome, drawn with
// the biome's Overlay shader (ElectricOverlay, its ElectricFx shapes 6 to 10) in code-built meshes:
// - plasma orb arcs: small lightning arcs jump from each pearl to its own territory when it is within 1.5 u (out of
//   home: toward the nearest own cell; at home: short arcs onto the territory around it), flickering;
// - the cut (La Revanche): a packet of current (white-blue hot head, short glow tail along the wire) races up the wire
//   at the retraction front, shedding sparks; behind it the wire is dead: a dim grey cable from the cut point to the
//   front, under the droplet chain (the droplets are drawn by ElectricBead as fading spark dots). A saved chased return
//   (contract 24, no capture): the dead wire fizzles out (sparks along it, the cable flickers and fades);
// - the fill: branching lightning bolts grow from the return point over the captured area during FillDuration (the
//   composite adds the crackling discharge and the hex pulse from _PIO_RevealTime);
// - elimination: short circuit, the orb explodes in sparks with a few arcs (the composite flickers and blacks out the
//   territory through _PIO_PlayerFade).
// Budget: at most MaxParticles (200) quads per frame in the effects batch, plus two strip meshes (cables, tails).
// Everything is created lazily in play mode (edit-mode tests only attach and destroy the component) and destroyed in
// OnDestroy; a biome change hides everything at once (the host destroys this component at the end of the frame).
using System;
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace PainterIO.Runtime
{
    public class ElectricFx : BiomeFxBehaviour
    {
        public override BiomeId Biome => BiomeId.Electric;

        /// <summary>Contract 25.5: at most this many extra particles (quads of the effects batch) per frame.</summary>
        public const int MaxParticles = 200;

        /// <summary>Contract 25.4: arcs jump from the orb to its own territory within this distance of its rim (u).</summary>
        public const float ArcReach = 1.5f;

        /// <summary>ElectricOverlay shape ids of the ElectricFx shapes.</summary>
        public const int ShapeBolt = 6, ShapeCable = 7, ShapeGlow = 8, ShapeSpark = 9, ShapePacket = 10;

        /// <summary>Queue of the dead cables: under the droplet chain (QuadBatch.QueueDroplets = 3001).</summary>
        public const int QueueCables = 3000;

        public const float FizzleSeconds = 0.45f;
        public const float CatchFadeSeconds = 0.25f;
        public const float FillBoltFade = 0.2f;
        public const float BurstSeconds = 0.6f;
        public const float PacketTailLength = 0.75f;
        public const float CableHalfWidth = 0.045f;
        public const float CableSampleSpacing = 0.15f;

        /// <summary>Opacity of the white-blue halo around the current packet (wave C: 0.4 -> 0.8, contract 25.5).</summary>
        public const float PacketHaloOpacity = 0.8f;

        /// <summary>Half size of the current packet quad (ShapePacket), world units (wave C: 1.5 x the B-2 size 0.8 x 0.46).</summary>
        public static readonly Vector2 PacketHalfSize = new Vector2(1.2f, 0.69f);

        private const int MaxCablePoints = 1024;
        private const int MaxFillBolts = 24;
        private const int MaxBursts = 8;
        private const float OrbQueryInterval = 0.08f;

        private static readonly int QualityId = Shader.PropertyToID("_PIO_Quality");
        private static readonly Color CableColor =new Color(0.075f, 0.08f, 0.095f, 1f);   // linear, dim grey
        private static readonly Color Cool = new Color(0.72f, 0.9f, 1f, 1f);
        private static readonly Color HaloBlue = new Color(0.25f, 0.6f, 1f, 1f);

        private struct Particle
        {
            public Vector2 Pos, Vel;
            public float Born, Life, Size;
            public Color Color;
        }

        private struct FillBolt
        {
            public Vector2 From, To;
            public float Start, Grow, Seed;
            public Color Color;
        }

        private struct Burst
        {
            public Vector2 Pos;
            public float Start, Seed;
            public Color Color;
        }

        private sealed class PlayerFx
        {
            public readonly Vector2[] Cable = new Vector2[MaxCablePoints];
            public readonly float[] Levels = new float[MaxCablePoints];
            public int CableCount;
            public bool Chased;
            public float EndStart = -100f;
            public float EndDuration;
            public float NextQuery;
            public bool HasTarget;
            public Vector2 Target;
            public float NextShed;
        }

        private QuadBatch fx;
        private StripMesh cables;
        private StripMesh tails;
        private bool built, buildFailed, customShapes, hidden = true, errorLogged;
        private readonly PlayerFx[] players = { new PlayerFx(), new PlayerFx(), new PlayerFx(), new PlayerFx() };
        private readonly Particle[] particles = new Particle[MaxParticles];
        private int particleCount;
        private readonly FillBolt[] fillBolts = new FillBolt[MaxFillBolts];
        private int fillBoltCount;
        private readonly Burst[] bursts = new Burst[MaxBursts];
        private int burstCount;
        private readonly Vector2[] tailPts = new Vector2[16];
        private readonly float[] tailLevels = new float[16];
        private readonly System.Random rng = new System.Random(0xE1EC);
        private Simulation boundSim;
        private float now;
        private int quadsThisFrame;
        private Rect view;
        private bool hasView;

        /// <summary>Quads drawn in the effects batch in the last frame (contract 25.5 cap, for tests and logs).</summary>
        public int LastQuadCount { get; private set; }

        /// <summary>Live particles (sparks) in the last frame.</summary>
        public int ParticleCount => particleCount;

        // ------------------------------------------------------------------------------------------------------------
        // BiomeFxBehaviour hooks.

        protected override void OnAttached()
        {
            BiomeTheme.Changed += OnBiomeChanged;
        }

        protected override void OnBind(GameSession session)
        {
            ResetAll();
            boundSim = session != null ? session.Sim : null;
        }

        public override void OnSimEvent(SimEvent e)
        {
            if (e == null || Session == null) return;
            int p = e.Player;
            bool valid = p >= 0 && p < players.Length;
            switch (e.Type)
            {
                case SimEventType.Return:
                    if (!valid) break;
                    if (e.Chased) StartEnd(p, FizzleSeconds);
                    else if (e.Cells != null && e.Cells.Length > 0) SpawnFillBolts(p, e);
                    break;
                case SimEventType.SparkCaught:
                    if (valid) StartEnd(p, CatchFadeSeconds);
                    break;
                case SimEventType.Eliminated:
                    if (!valid) break;
                    StartEnd(p, CatchFadeSeconds);
                    SpawnBurst(p);
                    break;
            }
        }

        public override void OnStateChanged(GameState state)
        {
        }

        // ------------------------------------------------------------------------------------------------------------
        // Lifecycle.

        private void OnDestroy()
        {
            BiomeTheme.Changed -= OnBiomeChanged;
            fx?.Destroy();
            cables?.Destroy();
            tails?.Destroy();
            fx = null;
            cables = null;
            tails = null;
        }

        private void OnBiomeChanged(BiomeTheme theme)
        {
            if (this == null)
            {
                BiomeTheme.Changed -= OnBiomeChanged;
                return;
            }
            if (theme != null && theme.Id != BiomeId.Electric) HideAll();
        }

        private void LateUpdate()
        {
            try
            {
                Tick();
            }
            catch (Exception e)
            {
                if (errorLogged) return;
                errorLogged = true;
                Debug.LogError("[PainterIO] ElectricFx failed: " + e);
            }
        }

        private void Tick()
        {
            GameSession s = Session;
            if (s == null || s.IsClosed || BiomeTheme.Current.Id != BiomeId.Electric)
            {
                HideAll();
                return;
            }
            if (!EnsureBuilt()) return;
            if (s.Sim != boundSim)
            {
                // An attract restart replaced the Simulation.
                ResetAll();
                boundSim = s.Sim;
            }
            float realDt = Mathf.Max(0f, Time.unscaledDeltaTime);
            float scale = s.Runner.Paused ? 0f : Mathf.Max(0f, s.Runner.TimeScale);
            float dt = Mathf.Min(realDt, 0.1f) * scale;
            now += dt;
            UpdateView();
            hidden = false;

            fx.Begin();
            cables.Begin();
            tails.Begin();
            quadsThisFrame = 0;
            Simulation sim = s.Sim;
            int n = Mathf.Min(sim.Players.Count, players.Length);
            float lobes = Shader.GetGlobalVector(QualityId).x > 1.5f ? 2f : 1f;
            for (int i = 0; i < n; i++) DrawPlayer(s, sim, i, lobes);
            DrawFillBolts(lobes);
            DrawBursts(lobes);
            StepParticles(dt, lobes);
            fx.End();
            cables.End();
            tails.End();
            LastQuadCount = quadsThisFrame;
        }

        private bool EnsureBuilt()
        {
            if (built) return true;
            if (buildFailed || !Application.isPlaying) return false;
            try
            {
                Shader overlay = Theme.ResolveOverlay();
                customShapes = overlay != null && overlay.name.EndsWith("ElectricOverlay", StringComparison.Ordinal);
                fx = new QuadBatch("ElectricFx", transform, overlay, QuadBatch.QueueOverlays, 45, QuadBatchKind.Overlay);
                cables = new StripMesh("ElectricCables", transform, overlay, QueueCables, 5);
                tails = new StripMesh("ElectricTails", transform, overlay, QuadBatch.QueueOverlays, 44);
                built = true;
                if (!customShapes) Debug.Log("[PainterIO] ElectricFx: ElectricOverlay missing, the electric effects are off");
            }
            catch (Exception e)
            {
                buildFailed = true;
                Debug.LogError("[PainterIO] ElectricFx setup failed: " + e);
            }
            return built;
        }

        private void HideAll()
        {
            if (hidden) return;
            hidden = true;
            fx?.Hide();
            cables?.Hide();
            tails?.Hide();
        }

        private void ResetAll()
        {
            particleCount = 0;
            fillBoltCount = 0;
            burstCount = 0;
            foreach (PlayerFx p in players)
            {
                p.CableCount = 0;
                p.Chased = false;
                p.EndStart = -100f;
                p.HasTarget = false;
                p.NextQuery = 0f;
            }
        }

        private void UpdateView()
        {
            Camera cam = Camera.main;
            hasView = cam != null;
            if (!hasView) return;
            float halfH = cam.orthographicSize;
            float halfW = halfH * cam.aspect;
            Vector3 c = cam.transform.position;
            view = new Rect(c.x - halfW, c.y - halfH, 2f * halfW, 2f * halfH);
        }

        private bool OnScreen(Vector2 p, float margin)
        {
            if (!hasView) return true;
            return p.x >= view.xMin - margin && p.x <= view.xMax + margin && p.y >= view.yMin - margin && p.y <= view.yMax + margin;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Per player: orb arcs, the current packet, the dead cable.

        private void DrawPlayer(GameSession s, Simulation sim, int i, float lobes)
        {
            PlayerState p = sim.Players[i];
            PlayerFx st = players[i];
            Color color = Palette.LinearColorOf(i);
            float headRadius = (float)sim.Config.HeadRadius;
            if (p.Alive)
            {
                Vector2 pos = s.RenderPos(i);
                if (OnScreen(pos, 2f)) DrawOrbArcs(sim, p, st, i, pos, headRadius, color, lobes);
            }

            bool live = p.Alive && !p.Home && p.Spark != null && p.Trail.Count >= 2;
            if (live)
            {
                st.Chased = true;
                st.EndStart = -100f;
                DrawChase(s, p, st, i, headRadius, color, lobes);
                return;
            }
            if (st.Chased && st.EndStart < -50f) StartEnd(i, FizzleSeconds);   // ended without an event we saw
            st.Chased = false;
            DrawCableEnd(st, i, color, lobes);
        }

        private void DrawOrbArcs(Simulation sim, PlayerState p, PlayerFx st, int i, Vector2 pos, float headRadius, Color color, float lobes)
        {
            if (!customShapes) return;
            if (p.Home)
            {
                // At home: short arcs from the orb onto the territory around it, one random spot per 0.22 s slot.
                int slot = Mathf.FloorToInt(now / 0.22f);
                float h = Hash01(slot * 31 + i * 7 + 1);
                float phase = now / 0.22f - slot;
                if (h < 0.55f && phase < 0.55f)
                {
                    float angle = Hash01(slot * 17 + i * 3 + 2) * 2f * Mathf.PI;
                    var d = new Vector2(Mathf.Cos(angle), Mathf.Sin(angle));
                    float len = 0.35f + 0.45f * Hash01(slot * 13 + i + 3);
                    Vector2 a = pos + d * (headRadius * 0.92f);
                    AddBolt(a, a + d * len, Hash01(slot * 7 + i * 11), color, 0.75f * (1f - phase / 0.55f), 0.011f, lobes);
                }
                return;
            }
            if (now >= st.NextQuery)
            {
                st.NextQuery = now + OrbQueryInterval;
                st.HasTarget = GridQueries.NearestOwned(sim.Grid, p.Id, p.Pos, ArcReach + headRadius, out Vec2d target, out double dist)
                               && dist - headRadius <= ArcReach;
                if (st.HasTarget) st.Target = new Vector2((float)target.X, (float)target.Y);
            }
            if (!st.HasTarget) return;
            Vector2 toTarget = st.Target - pos;
            float distance = toTarget.magnitude;
            if (distance < headRadius + 0.05f) return;
            Vector2 dir = toTarget / distance;
            // Two arcs flickering at about 8 Hz, each visible on part of its slots; closer means more often.
            float closeness = 1f - Mathf.Clamp01((distance - headRadius) / ArcReach);
            for (int k = 0; k < 2; k++)
            {
                int slot = Mathf.FloorToInt(now * 8f + k * 0.5f);
                if (Hash01(slot * 23 + i * 5 + k * 101) > 0.35f + 0.5f * closeness) continue;
                float spread = (Hash01(slot * 19 + k * 7 + i) - 0.5f) * 0.9f;
                Vector2 d = Rotate(dir, spread);
                Vector2 a = pos + d * (headRadius * 0.92f);
                Vector2 b = st.Target + new Vector2(Hash01(slot * 3 + k) - 0.5f, Hash01(slot * 5 + k + 9) - 0.5f) * 0.3f;
                AddBolt(a, b, Hash01(slot * 11 + k * 37 + i * 3), color, 0.9f, 0.013f, lobes);
            }
        }

        private void DrawChase(GameSession s, PlayerState p, PlayerFx st, int i, float headRadius, Color color, float lobes)
        {
            Trail trail = p.Trail;
            IReadOnlyList<Vec2d> points = trail.Points;
            IReadOnlyList<double> arc = trail.Arc;
            double sCut = p.Spark.SCut;
            double sr = s.RenderSparkS(i);
            if (double.IsNaN(sr)) sr = p.Spark.S;
            Vector2 tip = s.RenderPos(i);
            double lr = TrailCurve.RenderLength(p, tip);
            double lead = Math.Min(sr, lr - headRadius - RetractionView.PearlClearance);
            if (lead < sCut) lead = sCut;

            // The dead cable from the cut point to just behind the bulb's back (the droplets sit on it).
            double cableEnd = lead - RetractionView.BulbRadius * RetractionView.BulbStretch * 1.6;
            st.CableCount = 0;
            int seg = -1;
            if (cableEnd > sCut + 0.05)
            {
                double length = cableEnd - sCut;
                int samples = Mathf.Clamp((int)Math.Ceiling(length / CableSampleSpacing) + 1, 2, MaxCablePoints);
                for (int k = 0; k < samples; k++)
                {
                    double sk = sCut + length * k / (samples - 1);
                    st.Cable[k] = TrailCurve.Evaluate(points, arc, sk, ref seg);
                    st.Levels[k] = 1f;
                }
                st.CableCount = samples;
                if (OnScreenPolyline(st.Cable, samples)) cables.AddStrip(st.Cable, st.Levels, samples, CableHalfWidth, ShapeCable, CableColor, lobes);
            }

            if (!customShapes) return;
            int fseg = -1;
            Vector2 front = TrailCurve.Evaluate(points, arc, lead, ref fseg);
            if (!OnScreen(front, 1.5f)) return;
            int dseg = -1;
            Vector2 dir = TrailCurve.Direction(points, arc, lead, ref dseg);
            Color packetColor = Color.Lerp(color, Cool, 0.65f);

            // Glow tail behind the packet, along the wire.
            double tailStart = Math.Max(sCut, lead - PacketTailLength);
            int tailCount = tailPts.Length;
            int tseg = -1;
            for (int k = 0; k < tailCount; k++)
            {
                double sk = tailStart + (lead - tailStart) * k / (tailCount - 1);
                tailPts[k] = TrailCurve.Evaluate(points, arc, sk, ref tseg);
                float u = k / (float)(tailCount - 1);
                tailLevels[k] = u * u;
            }
            if (lead - tailStart > 0.05) tails.AddStrip(tailPts, tailLevels, tailCount, 0.17f, ShapeGlow, packetColor, lobes);

            // The packet head in a white-blue halo, flickering slightly: always the brightest moving thing (contract 25.5;
            // wave C: stronger halo, larger head).
            float flicker = 0.9f + 0.1f * Hash01(Mathf.FloorToInt(now * 30f) + i * 3);
            AddQuad(front, new Vector2(0.95f, 0.95f), 0f, (int)OverlayShape.Halo, new Vector3(0f, 0.4f, 1f),
                    Color.Lerp(color, HaloBlue, 0.6f), PacketHaloOpacity * flicker, lobes);
            // The head (local x = 0.3 of the half length) sits exactly on the front; the shape falls off faster ahead of
            // the head, so nothing bright reaches past the front further than before the 1.5 x size (V7).
            AddQuad(front - dir * (0.3f * PacketHalfSize.x), PacketHalfSize, Mathf.Atan2(dir.y, dir.x), ShapePacket,
                    new Vector3(flicker, 0f, 0f), packetColor, 1f, lobes);

            // Sparks shed backward from the packet.
            if (now >= st.NextShed)
            {
                st.NextShed = now + 0.045f;
                float side = NextFloat() < 0.5f ? -1f : 1f;
                Vector2 perp = new Vector2(-dir.y, dir.x) * side;
                Vector2 vel = (-dir * (1.2f + 1.5f * NextFloat()) + perp * (1.0f + 2.0f * NextFloat()));
                SpawnParticle(front, vel, 0.22f + 0.12f * NextFloat(), 0.16f + 0.08f * NextFloat(), Color.Lerp(color, Color.white, 0.5f));
            }
        }

        /// <summary>The dead wire after the chase: fizzle (saved return) or quick fade (catch, elimination).</summary>
        private void DrawCableEnd(PlayerFx st, int i, Color color, float lobes)
        {
            if (st.CableCount < 2 || st.EndStart < -50f) return;
            float t = now - st.EndStart;
            float duration = Mathf.Max(0.05f, st.EndDuration);
            if (t >= duration)
            {
                st.CableCount = 0;
                st.EndStart = -100f;
                return;
            }
            float u = t / duration;
            int step = Mathf.FloorToInt(now * 18f);
            float flicker = Hash01(step * 7 + i * 13) > 0.25f ? 1f : 0.4f;
            for (int k = 0; k < st.CableCount; k++)
            {
                // The fizzle eats the cable from both ends toward random spots.
                float local = Mathf.Clamp01(u * 1.3f - 0.3f * Hash01(k * 3 + i * 17 + 5));
                st.Levels[k] = (1f - local) * flicker;
            }
            if (OnScreenPolyline(st.Cable, st.CableCount))
            {
                cables.AddStrip(st.Cable, st.Levels, st.CableCount, CableHalfWidth * (1f - 0.4f * u), ShapeCable, CableColor, lobes);
                if (customShapes && st.EndDuration >= FizzleSeconds - 1e-3f && NextFloat() < 0.6f)
                {
                    // Fizzling sparks popping along the dead wire.
                    int k = (int)(NextFloat() * (st.CableCount - 1));
                    Vector2 at = st.Cable[k];
                    float angle = NextFloat() * 2f * Mathf.PI;
                    Vector2 vel = new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * (0.6f + 1.2f * NextFloat()) + new Vector2(0f, 0.4f);
                    SpawnParticle(at, vel, 0.18f + 0.15f * NextFloat(), 0.12f + 0.06f * NextFloat(), Color.Lerp(color, Color.white, 0.6f));
                }
            }
        }

        private void StartEnd(int player, float duration)
        {
            PlayerFx st = players[player];
            if (st.CableCount < 2) return;
            if (st.EndStart > -50f && duration >= st.EndDuration) return;   // already ending (keep the faster fade)
            st.EndStart = now;
            st.EndDuration = duration;
            st.Chased = false;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Fill discharge bolts.

        private void SpawnFillBolts(int player, SimEvent e)
        {
            if (Session == null || !customShapes) return;
            var origin = new Vector2((float)e.Point.X, (float)e.Point.Y);
            if (!OnScreen(origin, 4f)) return;
            OwnerGrid g = Session.Sim.Grid;
            const int sectors = 7;
            var best = new Vector2[sectors];
            var bestDist = new float[sectors];
            int[] cells = e.Cells;
            int stride = Mathf.Max(1, cells.Length / 600);
            for (int k = 0; k < cells.Length; k += stride)
            {
                int c = cells[k];
                Vec2d cc = g.CellCenter(c % g.Size, c / g.Size);
                var v = new Vector2((float)cc.X, (float)cc.Y) - origin;
                float d = v.magnitude;
                if (d < 0.8f) continue;
                float angle = Mathf.Atan2(v.y, v.x) + Mathf.PI;
                int sector = Mathf.Clamp((int)(angle / (2f * Mathf.PI) * sectors), 0, sectors - 1);
                if (d > bestDist[sector])
                {
                    bestDist[sector] = d;
                    best[sector] = origin + v;
                }
            }
            float grow = Mathf.Max(0.05f, Theme.FillDuration);
            Color color = Palette.LinearColorOf(player);
            for (int k = 0; k < sectors; k++)
            {
                if (bestDist[k] <= 0f) continue;
                if (fillBoltCount >= MaxFillBolts) break;
                fillBolts[fillBoltCount++] = new FillBolt
                {
                    From = origin, To = best[k], Start = now, Grow = grow * Mathf.Lerp(0.8f, 1.05f, NextFloat()),
                    Seed = NextFloat(), Color = color,
                };
            }
        }

        private void DrawFillBolts(float lobes)
        {
            int w = 0;
            for (int k = 0; k < fillBoltCount; k++)
            {
                FillBolt b = fillBolts[k];
                float t = now - b.Start;
                if (t >= b.Grow + FillBoltFade) continue;
                fillBolts[w++] = b;
                float reach = Mathf.Clamp01(t / b.Grow);
                float fade = t <= b.Grow ? 1f : 1f - (t - b.Grow) / FillBoltFade;
                Vector2 to = Vector2.Lerp(b.From, b.To, reach);
                if ((to - b.From).sqrMagnitude < 0.04f) continue;
                AddBolt(b.From, to, b.Seed, b.Color, fade, 0.02f, lobes);
            }
            fillBoltCount = w;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Short circuit (elimination): sparks and arcs at the orb.

        private void SpawnBurst(int player)
        {
            if (Session == null) return;
            Vector2 pos = Session.RenderPos(player);
            if (!OnScreen(pos, 2f)) return;
            Color color = Palette.LinearColorOf(player);
            if (burstCount < MaxBursts)
            {
                bursts[burstCount++] = new Burst { Pos = pos, Start = now, Seed = NextFloat(), Color = color };
            }
            Color hot = Color.Lerp(color, Color.white, 0.55f);
            for (int k = 0; k < 22; k++)
            {
                float angle = (k + NextFloat()) / 22f * 2f * Mathf.PI;
                var dir = new Vector2(Mathf.Cos(angle), Mathf.Sin(angle));
                float speed = 2.5f + 4.5f * NextFloat();
                SpawnParticle(pos + dir * 0.3f, dir * speed, 0.35f + 0.3f * NextFloat(), 0.2f + 0.12f * NextFloat(), hot);
            }
        }

        private void DrawBursts(float lobes)
        {
            int w = 0;
            for (int k = 0; k < burstCount; k++)
            {
                Burst b = bursts[k];
                float t = now - b.Start;
                if (t >= BurstSeconds) continue;
                bursts[w++] = b;
                if (!customShapes) continue;
                float u = t / BurstSeconds;
                int step = Mathf.FloorToInt(t * 16f);
                for (int a = 0; a < 5; a++)
                {
                    if (Hash01(step * 13 + a * 7 + (int)(b.Seed * 1000f)) > 0.7f - 0.4f * u) continue;
                    float angle = (a + Hash01(step * 5 + a)) / 5f * 2f * Mathf.PI;
                    var dir = new Vector2(Mathf.Cos(angle), Mathf.Sin(angle));
                    float len = (0.8f + 1.0f * Hash01(step * 3 + a * 11)) * (0.6f + 0.6f * u);
                    AddBolt(b.Pos + dir * 0.25f, b.Pos + dir * (0.25f + len), Hash01(step * 17 + a), b.Color, 1f - u, 0.016f, lobes);
                }
                if (t < 0.12f)
                {
                    float f = 1f - t / 0.12f;
                    AddQuad(b.Pos, new Vector2(1.1f, 1.1f), 0f, (int)OverlayShape.Glint, new Vector3(0.28f, 0.35f, 0.07f), Color.white, f, lobes);
                }
            }
            burstCount = w;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Particles (sparks).

        private void SpawnParticle(Vector2 pos, Vector2 vel, float life, float size, Color color)
        {
            if (particleCount >= MaxParticles) return;
            particles[particleCount++] = new Particle { Pos = pos, Vel = vel, Born = now, Life = life, Size = size, Color = color };
        }

        private void StepParticles(float dt, float lobes)
        {
            int w = 0;
            for (int k = 0; k < particleCount; k++)
            {
                Particle p = particles[k];
                float age = now - p.Born;
                if (age >= p.Life) continue;
                p.Pos += p.Vel * dt;
                p.Vel *= Mathf.Max(0f, 1f - 3.5f * dt);
                particles[w++] = p;
                if (!customShapes) continue;
                float u = age / p.Life;
                float speed = p.Vel.magnitude;
                float length = p.Size * (1f + 0.25f * Mathf.Min(speed, 6f));
                float angle = speed > 1e-3f ? Mathf.Atan2(p.Vel.y, p.Vel.x) : 0f;
                if (OnScreen(p.Pos, 0.5f))
                {
                    AddQuad(p.Pos, new Vector2(length, p.Size * 0.45f), angle, ShapeSpark, new Vector3(1f - 0.5f * u, 0f, 0f),
                            p.Color, 1f - u * u, lobes);
                }
            }
            particleCount = w;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Drawing helpers.

        private void AddBolt(Vector2 a, Vector2 b, float seed, Color color, float opacity, float coreHalfWidth, float lobes)
        {
            Vector2 d = b - a;
            float length = d.magnitude;
            if (length < 0.05f) return;
            float halfX = length * 0.5f;
            float halfY = Mathf.Max(0.12f, length * 0.2f);
            AddQuad((a + b) * 0.5f, new Vector2(halfX, halfY), Mathf.Atan2(d.y, d.x), ShapeBolt,
                    new Vector3(seed * 10f, halfY / halfX, coreHalfWidth), color, opacity, lobes);
        }

        private void AddQuad(Vector2 center, Vector2 halfSize, float rotation, int shape, Vector3 abc, Color color, float opacity, float lobes)
        {
            if (fx == null || quadsThisFrame >= MaxParticles || opacity <= 0.001f) return;
            fx.AddOverlay(center, halfSize, rotation, (OverlayShape)shape, abc, color, opacity, lobes);
            quadsThisFrame++;
        }

        private bool OnScreenPolyline(Vector2[] pts, int count)
        {
            if (!hasView) return true;
            for (int k = 0; k < count; k++)
            {
                if (OnScreen(pts[k], 0.5f)) return true;
            }
            return false;
        }

        private float NextFloat()
        {
            return (float)rng.NextDouble();
        }

        private static Vector2 Rotate(Vector2 v, float angle)
        {
            float c = Mathf.Cos(angle), s = Mathf.Sin(angle);
            return new Vector2(v.x * c - v.y * s, v.x * s + v.y * c);
        }

        private static float Hash01(int k)
        {
            return RetractionView.Hash01(k);
        }

        // ------------------------------------------------------------------------------------------------------------

        /// <summary>
        /// A dynamic mesh of ribbons along polylines for the ElectricOverlay strip shapes (Cable, Glow): per vertex
        /// UV0 = (along, cross -1 / +1, half width, level), UV1 = (shape, 0, 0, 0), UV2 = (1, 0, 0, lobes), vertex color.
        /// One continuous ribbon per polyline, so a fading strip never doubles its alpha at the joints.
        /// </summary>
        private sealed class StripMesh
        {
            private readonly GameObject go;
            private readonly Mesh mesh;
            private readonly MeshRenderer renderer;
            private readonly Material material;
            private readonly List<Vector3> vertices = new List<Vector3>(256);
            private readonly List<Color> colors = new List<Color>(256);
            private readonly List<Vector4> uv0 = new List<Vector4>(256);
            private readonly List<Vector4> uv1 = new List<Vector4>(256);
            private readonly List<Vector4> uv2 = new List<Vector4>(256);
            private readonly List<int> indices = new List<int>(512);
            private Vector2 min, max;

            public StripMesh(string name, Transform parent, Shader shader, int queue, int sortingOrder)
            {
                go = new GameObject(name);
                go.transform.SetParent(parent, false);
                go.transform.position = Vector3.zero;
                go.transform.rotation = Quaternion.identity;
                go.transform.localScale = Vector3.one;
                mesh = new Mesh { name = name };
                mesh.MarkDynamic();
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                renderer = go.AddComponent<MeshRenderer>();
                renderer.shadowCastingMode = ShadowCastingMode.Off;
                renderer.receiveShadows = false;
                renderer.lightProbeUsage = LightProbeUsage.Off;
                renderer.reflectionProbeUsage = ReflectionProbeUsage.Off;
                renderer.motionVectorGenerationMode = MotionVectorGenerationMode.ForceNoMotion;
                renderer.allowOcclusionWhenDynamic = false;
                renderer.sortingOrder = sortingOrder;
                if (shader != null)
                {
                    material = new Material(shader) { name = name, renderQueue = queue };
                    renderer.sharedMaterial = material;
                }
                renderer.enabled = false;
            }

            public void Begin()
            {
                vertices.Clear();
                colors.Clear();
                uv0.Clear();
                uv1.Clear();
                uv2.Clear();
                indices.Clear();
                min = new Vector2(float.MaxValue, float.MaxValue);
                max = new Vector2(float.MinValue, float.MinValue);
            }

            public void AddStrip(Vector2[] pts, float[] levels, int count, float halfWidth, int shape, Color color, float lobes)
            {
                if (count < 2 || vertices.Count + count * 2 > 65000) return;
                var c = new Color(color.r, color.g, color.b, 1f);
                var a = new Vector4(shape, 0f, 0f, 0f);
                var b = new Vector4(1f, 0f, 0f, lobes);
                int start = vertices.Count;
                float along = 0f;
                for (int k = 0; k < count; k++)
                {
                    Vector2 prev = pts[Mathf.Max(0, k - 1)];
                    Vector2 next = pts[Mathf.Min(count - 1, k + 1)];
                    Vector2 t = next - prev;
                    t = t.sqrMagnitude > 1e-12f ? t.normalized : Vector2.right;
                    var n = new Vector2(-t.y, t.x) * halfWidth;
                    if (k > 0) along += (pts[k] - pts[k - 1]).magnitude;
                    float level = levels != null ? levels[k] : 1f;
                    Vector2 p = pts[k];
                    vertices.Add(new Vector3(p.x - n.x, p.y - n.y, 0f));
                    vertices.Add(new Vector3(p.x + n.x, p.y + n.y, 0f));
                    uv0.Add(new Vector4(along, -1f, halfWidth, level));
                    uv0.Add(new Vector4(along, 1f, halfWidth, level));
                    uv1.Add(a);
                    uv1.Add(a);
                    uv2.Add(b);
                    uv2.Add(b);
                    colors.Add(c);
                    colors.Add(c);
                    if (p.x - halfWidth < min.x) min.x = p.x - halfWidth;
                    if (p.y - halfWidth < min.y) min.y = p.y - halfWidth;
                    if (p.x + halfWidth > max.x) max.x = p.x + halfWidth;
                    if (p.y + halfWidth > max.y) max.y = p.y + halfWidth;
                }
                for (int k = 0; k < count - 1; k++)
                {
                    int i0 = start + 2 * k;
                    indices.Add(i0);
                    indices.Add(i0 + 2);
                    indices.Add(i0 + 1);
                    indices.Add(i0 + 2);
                    indices.Add(i0 + 3);
                    indices.Add(i0 + 1);
                }
            }

            public void End()
            {
                if (mesh == null || renderer == null) return;
                if (indices.Count == 0 || material == null)
                {
                    if (renderer.enabled) renderer.enabled = false;
                    if (mesh.vertexCount > 0) mesh.Clear(true);
                    return;
                }
                mesh.Clear(true);
                mesh.SetVertices(vertices);
                mesh.SetColors(colors);
                mesh.SetUVs(0, uv0);
                mesh.SetUVs(1, uv1);
                mesh.SetUVs(2, uv2);
                mesh.SetTriangles(indices, 0, false);
                Vector2 center = (min + max) * 0.5f;
                Vector2 size = max - min;
                mesh.bounds = new Bounds(new Vector3(center.x, center.y, 0f), new Vector3(size.x + 0.1f, size.y + 0.1f, 1f));
                if (!renderer.enabled) renderer.enabled = true;
            }

            public void Hide()
            {
                Begin();
                End();
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
