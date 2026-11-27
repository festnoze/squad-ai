// Owned by FIRE (wave B-2, phase 2). Contract 25.3 and 25.5: the extra effects of the Feu biome, on top of what the
// composite (FireComposite), the beads (FireBead) and the shared overlays (FireOverlay) already draw:
// - embers shed by every fireball (pearl), more while it is out of its territory;
// - the lit fuse: a shower of white-hot sparks at each live retraction front (ActorViews.TryGetFront);
// - the burnt fuse: the droplet chain behind the spark (RetractionView, drawn with FireBead as hot embers) cools to grey
//   ash over EmberCoolSeconds. FireFx knows when the spark passed each droplet (RetractionView.DropletS / DropletRadius
//   give their place and size), so it draws the cooling over each droplet with FireOverlay shape 12, and lets small
//   smoke puffs rise from the cooling chain. It follows the droplets through the saved-return evaporation (same drift
//   as RetractionView) and the catch fade;
// - a saved chased return (contract 24, no capture): the remaining fuse burns out into ash and smoke;
// - cut, exit and capturing return: a small burst of sparks at the point;
// - elimination: the fireball bursts into sparks and the territory burns out to smoking ash (the composite cools and
//   dissolves the bed while _PIO_PlayerFade drops; FireFx releases smoke over the cells the player owned);
// - wave C: the spreading fire throws sparks up from its advancing front: during a fill, cells the territory field has
//   just revealed (TerritoryField.RevealTimeOf against RevealNow) are the front, and FireFx spawns FillSparkRate sparks
//   per second from them (about FillSparkRate x SparkLifeMax live at most). The lit fuse keeps its shower at the live
//   front (SparkRate x SparkLifeMax <= MaxFrontSparks live per front) under a warm orange glow; the white disc, orange
//   halo and rays of the spark itself are FireOverlay shape 3.
// Budget: at most MaxParticles (200) live particles (embers, sparks, smoke); the ash overlays are one per existing droplet
// of a chain, never more. Everything is drawn in two code-built QuadBatches with the biome's Overlay shader
// (BiomeTheme.ResolveOverlay, never Shader.Find): the ash just above the droplets, the particles above the splash and
// under the pearls. Pure C# simulation, preallocated arrays, no per-frame managed allocation once warmed up.
using System;
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    [DefaultExecutionOrder(160)]   // after ActorViews (150): this frame's retraction fronts are published
    public class FireFx : BiomeFxBehaviour
    {
        public override BiomeId Biome => BiomeId.Fire;

        /// <summary>Contract 25.5: extra particles of a biome are capped at 200.</summary>
        public const int MaxParticles = 200;

        /// <summary>Contract 25.3: the burnt fuse droplets cool from orange to grey ash over this time.</summary>
        public const float EmberCoolSeconds = 1.0f;

        /// <summary>FireOverlay shape ids used by FireFx (UV1.x).</summary>
        public const int ShapeEmber = 10, ShapeSmoke = 11, ShapeAsh = 12;

        /// <summary>Embers shed per second by a fireball out of / in its territory.</summary>
        public const float EmberRateOut = 11f, EmberRateHome = 4f;

        /// <summary>Sparks per second at a live retraction front.</summary>
        public const float SparkRate = 46f;

        /// <summary>Lifetime range of a fuse spark (seconds).</summary>
        public const float SparkLifeMin = 0.18f, SparkLifeMax = 0.4f;

        /// <summary>Most sparks alive at once in the shower of one live front (SparkRate x SparkLifeMax stays below).</summary>
        public const int MaxFrontSparks = 20;

        /// <summary>Sparks per second thrown up from the advancing front of the fire fills (all fills together).</summary>
        public const float FillSparkRate = 42f;

        /// <summary>Lifetime range of a fill spark (seconds).</summary>
        public const float FillSparkLifeMin = 0.25f, FillSparkLifeMax = 0.5f;

        /// <summary>A fill is followed for its theme FillDuration plus this margin (seconds).</summary>
        public const float FillFollowMargin = 0.2f;

        /// <summary>Fills followed at once (a newer one replaces the oldest).</summary>
        public const int MaxFills = 4;

        /// <summary>Ash overlays drawn at most per frame (all chains together).</summary>
        public const int MaxAshQuads = 400;

        /// <summary>Sorting orders: just above the droplets (10), between the splash (20) and the pearls (30).</summary>
        public const int AshSortingOrder = 15, ParticleSortingOrder = 25;

        // Spark travel speed relative to the trail: the spark at SparkSpeedFactor x PawnSpeed (contract 4).
        private const float SparkWorldSpeed = (float)(Tuning.SparkSpeedFactor * Tuning.PawnSpeed);
        // RetractionView draws droplet k once the bulb's back is 0.1 u past it: about 0.7 u behind the front.
        private const float DropletLag = 0.7f;
        private const float TerritorySampleSeconds = 0.5f;
        private const int TerritorySamples = 40;
        private const int MaxPendingSmoke = 48;

        public enum Kind : byte { Ember = 0, Spark = 1, Smoke = 2 }

        private enum FuseMode { None, Live, Absorb, Burst }

        private sealed class Fuse
        {
            public double SCut = double.NaN;
            public int Count;
            public readonly Vector2[] Pos = new Vector2[RetractionView.MaxDroplets];
            public readonly float[] Radius = new float[RetractionView.MaxDroplets];
            public readonly float[] Passed = new float[RetractionView.MaxDroplets];
            public readonly bool[] Smoked = new bool[RetractionView.MaxDroplets];
            public FuseMode Mode;
            public float ModeStart;
            public readonly Vector2[] Rest = new Vector2[24];   // samples of the fuse still burning (front to head)
            public int RestCount;

            public void Clear()
            {
                SCut = double.NaN;
                Count = 0;
                Mode = FuseMode.None;
                RestCount = 0;
            }
        }

        private struct PendingSmoke
        {
            public Vector2 Pos;
            public float At;
            public int Player;
        }

        // A capture being filled: its cells (the Return event's array, read only) and its owner.
        private struct FillFront
        {
            public int[] Cells;
            public int Player;
            public float Until;
        }

        // Particles (structure of arrays).
        private readonly Vector2[] pos = new Vector2[MaxParticles];
        private readonly Vector2[] vel = new Vector2[MaxParticles];
        private readonly float[] age = new float[MaxParticles];
        private readonly float[] life = new float[MaxParticles];
        private readonly float[] size = new float[MaxParticles];
        private readonly float[] seed = new float[MaxParticles];
        private readonly Kind[] kind = new Kind[MaxParticles];
        private readonly Color[] color = new Color[MaxParticles];
        private int count;

        private readonly Fuse[] fuses = new Fuse[Tuning.PlayerCount];
        private readonly float[] emberDebt = new float[Tuning.PlayerCount];
        private readonly float[] sparkDebt = new float[Tuning.PlayerCount];
        private readonly Vector2[][] territory = new Vector2[Tuning.PlayerCount][];
        private readonly int[] territoryCount = new int[Tuning.PlayerCount];
        private readonly Vector2[] lastPearl = new Vector2[Tuning.PlayerCount];
        private readonly bool[] hadPearl = new bool[Tuning.PlayerCount];
        private readonly bool[] detachShown = new bool[Tuning.PlayerCount];
        private readonly int[] seenScratch = new int[Tuning.PlayerCount];
        private readonly List<PendingSmoke> pending = new List<PendingSmoke>(MaxPendingSmoke);
        private readonly FillFront[] fills = new FillFront[MaxFills];
        private int fillCount;
        private float fillDebt;
        private readonly int[] frontCells = new int[FrontSamples];
        private readonly byte[] frontOwner = new byte[FrontSamples];
        private const int FrontSamples = 64;

        private QuadBatch ashBatch, particleBatch;
        private Simulation boundSim;
        private float clock, territoryClock;
        private uint rng = 0x2545F491u;
        private bool hidden = true;
        private bool errorLogged;

        /// <summary>Live particles (embers, sparks, smoke), never above MaxParticles.</summary>
        public int ParticleCount => count;

        /// <summary>Ash overlays drawn in the last frame.</summary>
        public int AshCount { get; private set; }

        /// <summary>The effects clock (follows the session: stops in pause, slows in slow motion).</summary>
        public float Clock => clock;

        protected override void OnAttached()
        {
            for (int i = 0; i < fuses.Length; i++)
            {
                fuses[i] = new Fuse();
                territory[i] = new Vector2[TerritorySamples];
            }
        }

        protected override void OnBind(GameSession session)
        {
            ResetAll();
        }

        private void OnDestroy()
        {
            ashBatch?.Destroy();
            particleBatch?.Destroy();
            ashBatch = null;
            particleBatch = null;
        }

        private void ResetAll()
        {
            count = 0;
            pending.Clear();
            for (int i = 0; i < fills.Length; i++) fills[i] = default;
            fillCount = 0;
            fillDebt = 0f;
            for (int i = 0; i < fuses.Length; i++)
            {
                fuses[i]?.Clear();
                emberDebt[i] = 0f;
                sparkDebt[i] = 0f;
                territoryCount[i] = 0;
                hadPearl[i] = false;
                detachShown[i] = false;
            }
            territoryClock = 0f;
            boundSim = Session != null ? Session.Sim : null;
            ashBatch?.Hide();
            particleBatch?.Hide();
        }

        // ------------------------------------------------------------------------------------------------------------
        // Sim events (forwarded by BiomeFxHost after each Step, in resolution order).

        public override void OnSimEvent(SimEvent e)
        {
            if (e == null) return;
            GameSession s = Session;
            if (s == null || s.Sim == null) return;
            int p = e.Player;
            bool valid = p >= 0 && p < fuses.Length && p < s.Sim.Players.Count;
            switch (e.Type)
            {
                case SimEventType.Cut:
                    Burst(ToVector(e.Point), Kind.Spark, 12, 2.6f, valid ? p : 0, true);
                    break;
                case SimEventType.Return:
                    if (!valid) break;
                    if (e.Chased) OnSavedReturn(p);
                    else if (e.Cells != null && e.Cells.Length > 0)
                    {
                        Burst(ToVector(e.Point), Kind.Spark, 14, 2.2f, p, false);
                        FollowFill(e.Cells, p);
                    }
                    break;
                case SimEventType.SparkCaught:
                    if (valid) StartBurstFade(p);
                    break;
                case SimEventType.Eliminated:
                    if (valid) OnEliminated(s, p);
                    break;
            }
        }

        private void OnSavedReturn(int p)
        {
            Fuse f = fuses[p];
            // Contract 24: the remaining fuse burns out into ash and smoke; the chain evaporates with RetractionView.
            for (int k = 0; k < f.RestCount; k++)
            {
                SpawnSmoke(f.Rest[k] + Jitter(0.08f), p, 0.9f + 0.5f * Next01(), 0.16f + 0.08f * Next01(), 0.32f);
                if ((k & 1) == 0) Spawn(Kind.Ember, f.Rest[k], new Vector2(0f, 0.6f) + Jitter(0.5f), 0.35f + 0.3f * Next01(), 0.05f, p);
            }
            for (int k = 0; k < f.Count; k += 3) SpawnSmoke(f.Pos[k] + Jitter(0.05f), p, 0.8f + 0.4f * Next01(), 0.12f, 0.26f);
            if (f.Mode == FuseMode.Live || f.Count > 0)
            {
                f.Mode = FuseMode.Absorb;
                f.ModeStart = clock;
            }
            f.RestCount = 0;
        }

        private void FollowFill(int[] cells, int p)
        {
            float duration = Theme != null ? Theme.FillDuration : 0.6f;
            var f = new FillFront { Cells = cells, Player = p, Until = clock + duration + FillFollowMargin };
            if (fillCount < fills.Length)
            {
                fills[fillCount++] = f;
                return;
            }
            // Full: the newest replaces the one that ends first.
            int oldest = 0;
            for (int i = 1; i < fills.Length; i++) if (fills[i].Until < fills[oldest].Until) oldest = i;
            fills[oldest] = f;
        }

        private void StartBurstFade(int p)
        {
            Fuse f = fuses[p];
            if (f.Mode == FuseMode.Live || f.Mode == FuseMode.Absorb)
            {
                f.Mode = FuseMode.Burst;
                f.ModeStart = clock;
            }
        }

        private void OnEliminated(GameSession s, int p)
        {
            StartBurstFade(p);
            Vector2 at = hadPearl[p] ? lastPearl[p] : s.RenderPos(p);
            // The fireball bursts into sparks.
            Burst(at, Kind.Spark, 26, 3.4f, p, false);
            Burst(at, Kind.Ember, 10, 1.6f, p, false);
            SpawnSmoke(at, p, 1.3f, 0.45f, 0.4f);
            // The territory burns out to smoking ash: puffs rise from the cells it owned while the bed cools.
            int n = territoryCount[p];
            for (int k = 0; k < n && pending.Count < MaxPendingSmoke; k++)
            {
                pending.Add(new PendingSmoke { Pos = territory[p][k], At = clock + 0.05f + 0.6f * Next01(), Player = p });
            }
            territoryCount[p] = 0;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Frame.

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
                Debug.LogError("[PainterIO] FireFx failed: " + e);
            }
        }

        private void Tick()
        {
            GameSession s = Session;
            if (BiomeTheme.Current.Id != BiomeId.Fire || s == null || s.IsClosed || s.Sim == null)
            {
                HideAll();
                return;
            }
            if (s.Sim != boundSim) ResetAll();   // an attract restart replaced the Simulation
            EnsureBatches();
            hidden = false;

            float scale = s.Runner.Paused ? 0f : Mathf.Max(0f, s.Runner.TimeScale);
            float dt = Mathf.Min(Mathf.Max(0f, Time.unscaledDeltaTime), 0.1f) * scale;
            clock += dt;
            Simulation sim = s.Sim;
            int n = Mathf.Min(sim.Players.Count, fuses.Length);

            if (clock - territoryClock >= TerritorySampleSeconds || territoryClock <= 0f)
            {
                territoryClock = clock;
                SampleTerritories(sim, n);
            }

            for (int p = 0; p < n; p++)
            {
                PlayerState ps = sim.Players[p];
                TickPearl(s, ps, p, dt);
                TickFuse(s, ps, p, dt);
            }
            for (int k = pending.Count - 1; k >= 0; k--)
            {
                if (pending[k].At > clock) continue;
                SpawnSmoke(pending[k].Pos, pending[k].Player, 1.1f + 0.6f * Next01(), 0.22f + 0.12f * Next01(), 0.36f);
                if (Next01() < 0.5f) Spawn(Kind.Ember, pending[k].Pos, new Vector2(0f, 0.5f) + Jitter(0.4f), 0.5f, 0.05f, pending[k].Player);
                pending.RemoveAt(k);
            }
            TickFills(dt);
            StepParticles(dt);
            Draw(s, n);
        }

        // The spreading fire throws sparks up from its advancing front: the cells of a followed fill that the territory
        // field revealed within the last frame (or a little more) are the front.
        private void TickFills(float dt)
        {
            for (int i = fillCount - 1; i >= 0; i--)
            {
                if (fills[i].Until > clock && fills[i].Cells != null) continue;
                fills[i] = fills[fillCount - 1];
                fills[fillCount - 1] = default;
                fillCount--;
            }
            if (fillCount == 0 || dt <= 0f)
            {
                fillDebt = 0f;
                return;
            }
            LiquidRenderer lr = LiquidRenderer.Instance;
            TerritoryField tf = lr != null ? lr.Territory : null;
            if (tf == null) return;
            int sizeCells = tf.Size;
            float now = tf.RevealNow;
            float look = Mathf.Max(dt * 1.5f, 0.03f);
            // Reservoir sample of the front cells (allocation free).
            int seen = 0, kept = 0;
            for (int i = 0; i < fillCount; i++)
            {
                int[] cells = fills[i].Cells;
                byte owner = (byte)(fills[i].Player + 1);
                for (int k = 0; k < cells.Length; k++)
                {
                    int c = cells[k];
                    float age = now - tf.RevealTimeOf(c);
                    if (age < 0f || age >= look || tf.VisualOwner(c) != owner) continue;
                    seen++;
                    int slot = kept < FrontSamples ? kept++ : (int)(Next01() * seen);
                    if (slot >= FrontSamples) continue;
                    frontCells[slot] = c;
                    frontOwner[slot] = owner;
                }
            }
            if (kept == 0) return;
            fillDebt = Mathf.Min(fillDebt + FillSparkRate * dt, 4f);
            float cell = (float)Tuning.CellSize;
            float min = -sizeCells * cell * 0.5f;
            while (fillDebt >= 1f)
            {
                fillDebt -= 1f;
                int pick = Mathf.Min((int)(Next01() * kept), kept - 1);
                int c = frontCells[pick];
                var at = new Vector2(min + (c % sizeCells + 0.5f) * cell, min + (c / sizeCells + 0.5f) * cell);
                Vector2 v = new Vector2((Next01() - 0.5f) * 1.4f, 1.1f + 1.5f * Next01());
                float life = FillSparkLifeMin + (FillSparkLifeMax - FillSparkLifeMin) * Next01();
                Spawn(Kind.Spark, at + Jitter(cell * 0.5f), v, life, 0.03f + 0.025f * Next01(), frontOwner[pick] - 1);
            }
        }

        private void TickPearl(GameSession s, PlayerState ps, int p, float dt)
        {
            if (!ps.Alive)
            {
                hadPearl[p] = false;
                return;
            }
            Vector2 at = s.RenderPos(p);
            lastPearl[p] = at;
            hadPearl[p] = true;
            // Exit pop (23.3 debounce: only once the detach is visible): a puff of embers where the fireball leaves.
            if (ps.Home) detachShown[p] = false;
            else if (!detachShown[p] && s.HasVisibleDetach(p))
            {
                detachShown[p] = true;
                Burst(at, Kind.Ember, 6, 1.5f, p, false);
            }
            if (dt <= 0f) return;
            emberDebt[p] += (ps.Home ? EmberRateHome : EmberRateOut) * dt;
            var dir = new Vector2(Mathf.Cos((float)ps.Heading), Mathf.Sin((float)ps.Heading));
            float head = (float)Tuning.HeadRadius;
            while (emberDebt[p] >= 1f)
            {
                emberDebt[p] -= 1f;
                Vector2 from = at - dir * head * (0.4f + 0.5f * Next01()) + Jitter(head * 0.55f);
                Vector2 v = -dir * (0.4f + 0.6f * Next01()) + new Vector2(0f, 0.7f + 0.6f * Next01()) + Jitter(0.45f);
                Spawn(Kind.Ember, from, v, 0.45f + 0.45f * Next01(), 0.045f + 0.035f * Next01(), p);
            }
        }

        private void TickFuse(GameSession s, PlayerState ps, int p, float dt)
        {
            Fuse f = fuses[p];
            bool live = ps.Alive && !ps.Home && ps.Spark != null && ps.Trail != null && ps.Trail.Count >= 2;
            if (!live)
            {
                if (f.Mode == FuseMode.Live)
                {
                    // The chase ended without an event we saw: let the chain evaporate like RetractionView does.
                    f.Mode = FuseMode.Absorb;
                    f.ModeStart = clock;
                }
                float duration = f.Mode == FuseMode.Absorb ? RetractionView.AbsorbSeconds : RetractionView.CatchFadeSeconds;
                if ((f.Mode == FuseMode.Absorb || f.Mode == FuseMode.Burst) && clock - f.ModeStart >= duration) f.Clear();
                return;
            }

            IReadOnlyList<Vec2d> points = ps.Trail.Points;
            IReadOnlyList<double> arc = ps.Trail.Arc;
            double sCut = ps.Spark.SCut;
            if (f.Mode != FuseMode.Live || double.IsNaN(f.SCut) || Math.Abs(f.SCut - sCut) > 1e-9)
            {
                f.Clear();
                f.SCut = sCut;
            }
            f.Mode = FuseMode.Live;
            double sr = s.RenderSparkS(p);
            if (double.IsNaN(sr)) sr = ps.Spark.S;

            // Droplets the bulb has left behind since the last frame: their place, size and the time the spark passed.
            int seg = -1;
            while (f.Count < RetractionView.MaxDroplets)
            {
                double sk = RetractionView.DropletS(sCut, f.Count);
                double behind = sr - DropletLag - sk;
                if (behind < 0.0) break;
                int k = f.Count;
                f.Pos[k] = TrailCurve.Evaluate(points, arc, sk, ref seg);
                f.Radius[k] = RetractionView.DropletRadius(p, k);
                f.Passed[k] = clock - (float)(behind / SparkWorldSpeed);
                f.Smoked[k] = false;
                f.Count++;
            }
            // Smoke from the cooling chain (about one droplet in three).
            for (int k = 0; k < f.Count; k++)
            {
                if (f.Smoked[k]) continue;
                float heat = 1f - (clock - f.Passed[k]) / EmberCoolSeconds;
                if (heat > 0.55f) break;
                f.Smoked[k] = true;
                if (RetractionView.Hash01(k * 11 + p * 97 + 5) < 0.36f)
                {
                    SpawnSmoke(f.Pos[k] + Jitter(0.04f), p, 0.9f + 0.5f * Next01(), 0.1f + 0.05f * Next01(), 0.28f);
                }
            }

            // The rest of the fuse (from the front to the head), for the saved-return burn-out.
            Vector2 tip = s.RenderPos(p);
            double lr = TrailCurve.RenderLength(ps, tip);
            f.RestCount = 0;
            int rseg = -1;
            for (double sk = sr; sk < lr && f.RestCount < f.Rest.Length; sk += 0.6)
            {
                f.Rest[f.RestCount++] = TrailCurve.Evaluate(points, arc, sk, ref rseg);
            }

            // The lit fuse: a shower of white-hot sparks at the front.
            if (dt > 0f && ActorViews.Instance != null && ActorViews.Instance.TryGetFront(p, out Vector2 front))
            {
                sparkDebt[p] += SparkRate * dt;
                while (sparkDebt[p] >= 1f)
                {
                    sparkDebt[p] -= 1f;
                    float a = Next01() * Mathf.PI * 2f;
                    float speed = 1.4f + 2.4f * Next01();
                    Vector2 v = new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * speed + new Vector2(0f, 0.8f);
                    Spawn(Kind.Spark, front + Jitter(0.05f), v, SparkLifeMin + (SparkLifeMax - SparkLifeMin) * Next01(), 0.035f + 0.025f * Next01(), p);
                }
            }
        }

        private void SampleTerritories(Simulation sim, int players)
        {
            OwnerGrid grid = sim.Grid;
            if (grid == null) return;
            byte[] cells = grid.Cells;
            int sizeCells = grid.Size;
            if (cells == null || sizeCells <= 0) return;
            for (int p = 0; p < players; p++) territoryCount[p] = 0;
            int[] seen = seenScratch;
            Array.Clear(seen, 0, seen.Length);
            const int stride = 6;
            int offset = (int)(Next01() * stride);
            float cell = (float)Tuning.CellSize;
            float min = -sizeCells * cell * 0.5f;
            for (int j = offset; j < sizeCells; j += stride)
            {
                for (int i = (j * 7 + offset) % stride; i < sizeCells; i += stride)
                {
                    int o = cells[j * sizeCells + i] - 1;
                    if (o < 0 || o >= players || !sim.Players[o].Alive) continue;
                    seen[o]++;
                    var w = new Vector2(min + (i + 0.5f) * cell, min + (j + 0.5f) * cell);
                    if (territoryCount[o] < TerritorySamples) territory[o][territoryCount[o]++] = w;
                    else
                    {
                        int r = (int)(Next01() * seen[o]);
                        if (r < TerritorySamples) territory[o][r] = w;
                    }
                }
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Particles.

        private void Burst(Vector2 at, Kind k, int n, float speed, int player, bool hot)
        {
            for (int i = 0; i < n; i++)
            {
                float a = (i + Next01()) / n * Mathf.PI * 2f;
                float sp = speed * (0.45f + 0.75f * Next01());
                Vector2 v = new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * sp + new Vector2(0f, 0.5f);
                float l = k == Kind.Spark ? 0.25f + 0.3f * Next01() : 0.5f + 0.4f * Next01();
                float sz = k == Kind.Spark ? 0.04f + 0.03f * Next01() : 0.05f + 0.035f * Next01();
                Spawn(hot ? Kind.Spark : k, at + Jitter(0.08f), v, l, sz, player);
            }
        }

        private void SpawnSmoke(Vector2 at, int player, float lifetime, float startSize, float density)
        {
            int i = Spawn(Kind.Smoke, at, new Vector2(0.08f * (Next01() - 0.5f), 0.35f + 0.25f * Next01()), lifetime, startSize, player);
            if (i >= 0) color[i] = new Color(0.16f, 0.14f, 0.13f, density);
        }

        /// <summary>Adds a particle; returns its slot, or -1 when the cap is reached (contract 25.5).</summary>
        private int Spawn(Kind k, Vector2 at, Vector2 v, float lifetime, float startSize, int player)
        {
            if (count >= MaxParticles || !(lifetime > 0f)) return -1;
            if (float.IsNaN(at.x) || float.IsNaN(at.y)) return -1;
            int i = count++;
            pos[i] = at;
            vel[i] = v;
            age[i] = 0f;
            life[i] = lifetime;
            size[i] = startSize;
            seed[i] = Next01();
            kind[i] = k;
            Color c = player >= 0 && player < Tuning.PlayerCount ? Palette.LinearColorOf(player) : new Color(1f, 0.5f, 0.2f);
            c.a = 1f;
            color[i] = c;
            return i;
        }

        private void StepParticles(float dt)
        {
            if (dt <= 0f) return;
            int w = 0;
            for (int i = 0; i < count; i++)
            {
                float a = age[i] + dt;
                if (a >= life[i]) continue;
                Vector2 v = vel[i];
                switch (kind[i])
                {
                    case Kind.Smoke:
                        v *= 1f - Mathf.Min(1f, 0.8f * dt);
                        v.y += 0.25f * dt;
                        size[i] += 0.32f * dt;
                        break;
                    case Kind.Spark:
                        v *= 1f - Mathf.Min(1f, 2.6f * dt);
                        v.y += 0.4f * dt;
                        break;
                    default:
                        v *= 1f - Mathf.Min(1f, 1.4f * dt);
                        v.y += 0.9f * dt;
                        v.x += 0.6f * dt * Mathf.Sin(a * 7f + seed[i] * 20f);
                        break;
                }
                if (w != i)
                {
                    life[w] = life[i];
                    size[w] = size[i];
                    seed[w] = seed[i];
                    kind[w] = kind[i];
                    color[w] = color[i];
                }
                age[w] = a;
                vel[w] = v;
                pos[w] = pos[i] + v * dt;
                w++;
            }
            count = w;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Drawing.

        private void EnsureBatches()
        {
            if (ashBatch != null && particleBatch != null) return;
            Shader overlay = Theme.ResolveOverlay();
            // The ash must draw after the droplets whatever the sorting criteria: a later queue AND a higher sorting order.
            if (ashBatch == null) ashBatch = new QuadBatch("FireAsh", transform, overlay, QuadBatch.QueueSplash, AshSortingOrder, QuadBatchKind.Overlay);
            if (particleBatch == null) particleBatch = new QuadBatch("FireParticles", transform, overlay, QuadBatch.QueueSplash, ParticleSortingOrder, QuadBatchKind.Overlay);
        }

        private void Draw(GameSession s, int players)
        {
            ashBatch.Begin();
            int ash = 0;
            for (int p = 0; p < players && ash < MaxAshQuads; p++)
            {
                Fuse f = fuses[p];
                if (f.Count == 0 || f.Mode == FuseMode.None) continue;
                Color c = Palette.LinearColorOf(p);
                float u = 0f;
                if (f.Mode == FuseMode.Absorb) u = Mathf.Clamp01((clock - f.ModeStart) / RetractionView.AbsorbSeconds);
                else if (f.Mode == FuseMode.Burst) u = Mathf.Clamp01((clock - f.ModeStart) / RetractionView.CatchFadeSeconds);
                float lift = 1f - (1f - u) * (1f - u);
                for (int k = 0; k < f.Count && ash < MaxAshQuads; k++)
                {
                    float heat = Mathf.Clamp01(1f - (clock - f.Passed[k]) / EmberCoolSeconds);
                    if (heat >= 0.995f) continue;
                    Vector2 at = f.Pos[k];
                    float r = f.Radius[k];
                    float opacity = 1f;
                    if (f.Mode == FuseMode.Absorb)
                    {
                        // The same evaporation as RetractionView.DrawEvaporation (delay, shrink, drift, fade).
                        float delay = 0.25f * RetractionView.Hash01(k * 5 + p * 61 + 9);
                        float v = Mathf.Clamp01((u - delay) / (1f - delay));
                        r *= Mathf.Pow(1f - v, 0.7f);
                        opacity = v < 0.6f ? 1f : (1f - v) / 0.4f;
                        at += new Vector2(0.06f * (RetractionView.Hash01(k * 5 + p * 61 + 10) - 0.5f), 0.08f) * lift;
                    }
                    else if (f.Mode == FuseMode.Burst)
                    {
                        float fade = 1f - u;
                        r *= Mathf.Lerp(0.55f, 1f, fade);
                        opacity = fade;
                    }
                    if (r < 0.004f || opacity < 0.01f) continue;
                    float half = r * 1.32f;
                    ashBatch.AddOverlay(at, new Vector2(half, half), 0f, (OverlayShape)ShapeAsh,
                                        new Vector3(heat, RetractionView.Hash01(k * 3 + p * 17 + 1), 0f), c, opacity, 1f);
                    ash++;
                }
            }
            AshCount = ash;
            ashBatch.End();

            particleBatch.Begin();
            // The lit fuse: a warm orange pool of light around each live spark (FireOverlay's spark, white disc over an
            // orange halo, is drawn on top: the brightest moving thing on screen during a chase, contract 25.5). A
            // saturated orange, never a pale yellow that would read as grey fog without bloom.
            if (ActorViews.Instance != null)
            {
                for (int p = 0; p < players; p++)
                {
                    if (!ActorViews.Instance.TryGetFront(p, out Vector2 front)) continue;
                    float flicker = 0.8f + 0.2f * Mathf.Sin(clock * 47f + p) * Mathf.Sin(clock * 29f + 2f * p);
                    particleBatch.AddOverlay(front, new Vector2(0.9f, 0.9f), 0f, OverlayShape.Halo, new Vector3(0f, 0.42f, 0f),
                                             new Color(1f, 0.3f, 0.05f, 1f), 0.42f * flicker, 1f);
                }
            }
            // Smoke first (under), then embers and sparks.
            for (int i = 0; i < count; i++)
            {
                if (kind[i] != Kind.Smoke) continue;
                float t = age[i] / life[i];
                float fadeIn = Mathf.Clamp01(t / 0.15f);
                float alpha = color[i].a * fadeIn * (1f - t) * (1f - t);
                if (alpha < 0.005f) continue;
                var c = new Color(color[i].r, color[i].g, color[i].b, 1f);
                particleBatch.AddOverlay(pos[i], new Vector2(size[i], size[i]), seed[i] * 6.2832f, (OverlayShape)ShapeSmoke,
                                         new Vector3(seed[i], 1f, 0f), c, alpha, 1f);
            }
            for (int i = 0; i < count; i++)
            {
                if (kind[i] == Kind.Smoke) continue;
                float t = age[i] / life[i];
                float heat = kind[i] == Kind.Spark ? 1f - t * 0.9f : 0.95f - t * 0.95f;
                float alpha = t < 0.7f ? 1f : (1f - t) / 0.3f;
                float sz = size[i] * (kind[i] == Kind.Spark ? 1f : 1f - 0.5f * t);
                Vector2 v = vel[i];
                float speed = v.magnitude;
                float streak = 1f + Mathf.Min(3f, speed * (kind[i] == Kind.Spark ? 0.55f : 0.2f));
                float angle = speed > 1e-4f ? Mathf.Atan2(v.y, v.x) : 0f;
                particleBatch.AddOverlay(pos[i], new Vector2(sz * streak, sz), angle, (OverlayShape)ShapeEmber,
                                         new Vector3(heat, 0f, seed[i]), color[i], alpha, 1f);
            }
            particleBatch.End();
        }

        private void HideAll()
        {
            if (hidden) return;
            hidden = true;
            ashBatch?.Hide();
            particleBatch?.Hide();
        }

        // ------------------------------------------------------------------------------------------------------------
        // Helpers.

        private static Vector2 ToVector(Vec2d v)
        {
            return new Vector2((float)v.X, (float)v.Y);
        }

        private float Next01()
        {
            // xorshift32: deterministic per component, no allocation.
            rng ^= rng << 13;
            rng ^= rng >> 17;
            rng ^= rng << 5;
            return (rng & 0xFFFFFF) / 16777216f;
        }

        private Vector2 Jitter(float r)
        {
            return new Vector2((Next01() - 0.5f) * 2f * r, (Next01() - 0.5f) * 2f * r);
        }
    }
}
