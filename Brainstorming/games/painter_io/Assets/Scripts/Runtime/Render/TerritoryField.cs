// Owned by BI since wave B-2 (written by B1). Contract 12.2 item 1 (territory field), 12.3 (fill wave on return,
// evaporation on elimination, pending pockets) and 25.2 (per-biome FillDuration, reveal times for moving fronts).
//
// CPU side: a VisualMask (grid-sized RGBA32 linear texture, channel c = player c owns the cell, 255 / 0) that follows the
// sim grid with a visual lag: captured cells appear over FillDuration in order of distance from the return point (cells
// taken from a rival leave it when the wave reaches them), an eliminated player's channel fades out through
// _PIO_PlayerFade over EvaporationSeconds and is then cleared. Every grid change comes with a Return (captured cells) or
// an Eliminated event; a reconciliation pass after each grid change repairs anything else. The pocket mask follows
// PlayerState.Pocket (CellMask.Version driven).
//
// GPU side, only when the VisualMask changed: TerritoryBlur passes in one CommandBuffer executed with
// Graphics.ExecuteCommandBuffer, each limited with EnableScissorRect to the dirty rectangle (changed cells grown by
// 4 sigma + 2 cells); the full-texture path runs only when a session is bound or a render texture was lost:
//   mask -(blur x)-> ping A -(blur y)-> ping B -(B-spline x2)-> _PIO_TerritoryField (contour and color, sigma 0.16 u)
//   ping B -(wide x)-> ping A -(wide y)-> ping C -(B-spline x2, height)-> _PIO_TerritoryHeight (relief, sigma 0.26 u)
//   mask -(dome x, 2 x 2 box down)-> dome H -(dome y)-> dome V -(B-spline x2, gradient)-> _PIO_TerritoryDome
//   (wave D liq-drop, contract 28 F2: the domed body of the liquid, sigma 0.8 u on a half-size grid, with its own
//   render textures and its own wider scissor rectangle; the first six passes and their textures are unchanged).
//
// The visual clock is the render time of the sim, Time - (1 - Alpha) * Dt (the instant RenderPos shows), so pausing or
// slowing the runner pauses or slows the waves, and a screenshot at a given tick always shows the same fill.
//
// Reveal times (contract 25.2): _PIO_RevealTime is a grid-sized RHalf world texture (over _PIO_ArenaRect, like the
// masks) holding, per cell, the visual clock time at which the cell was last revealed or changed owner visually (a fill
// wave cell gets its exact scheduled time), and -1000 for cells present when the session was bound. _PIO_Now is the same
// clock now, so a composite draws a moving front where _PIO_Now - reveal is small (liquid ripple, fire front, electric
// crackle). Both share a rolling epoch (rebased every RevealRebaseSeconds) so half precision stays finer than 1/60 s:
// only the difference _PIO_Now - reveal is meaningful. The fill of a capture lasts BiomeTheme.Current.FillDuration
// (taken when the wave starts).
using System;
using System.Collections.Generic;
using PainterIO.Core;
using Unity.Collections;
using UnityEngine;
using UnityEngine.Experimental.Rendering;
using UnityEngine.Rendering;

namespace PainterIO.Runtime
{
    public sealed class TerritoryField : IDisposable
    {
        /// <summary>Seconds a capture takes to fill in (contract 12.3); the HUD counts up over the same time.</summary>
        public const float FillDuration = 0.35f;
        /// <summary>Seconds an eliminated player's puddle takes to evaporate (contract 12.3).</summary>
        public const float EvaporationSeconds = 0.6f;
        /// <summary>Gaussian sigma of the territory blur, in mask texels (cells): 0.16 u.</summary>
        public const float BlurSigmaCells = 1.28f;
        /// <summary>Gaussian sigma of the second (relief) blur applied after the first one, in cells.</summary>
        public const float WideSigmaCells = 1.6f;
        /// <summary>Dirty rectangle growth: ceil(4 sigma) + 2 cells with the total relief sigma sqrt(1.28^2 + 1.6^2) = 2.05.</summary>
        public const int DirtyGrowCells = 11;
        /// <summary>Upsampling factor of the field and height textures (512 mask -> 1024 field).</summary>
        public const int FieldScale = 2;
        /// <summary>Reveal value of cells present at bind time (and of reveals older than RevealForgetSeconds after a rebase).</summary>
        public const float RevealNever = -1000f;
        /// <summary>The reveal epoch moves to now when the clock is this far from it (keeps half precision under 1/64 s).</summary>
        public const double RevealRebaseSeconds = 16.0;
        /// <summary>On a rebase, reveals older than this become RevealNever.</summary>
        public const float RevealForgetSeconds = 30f;
        /// <summary>Gaussian sigma of the dome field (wave D F2), world units (3.2 texels of the half-size dome grid).</summary>
        public const float DomeSigmaUnits = 0.8f;
        /// <summary>Downsampling of the dome blur grid against the mask (512 cells -> 256 dome texels).</summary>
        public const int DomeDownscale = 2;
        /// <summary>
        /// Dirty rectangle growth of the dome passes, in cells: the 21-tap Gaussian reaches 20 cells, the 2 x 2 box 1,
        /// the B-spline reconstruction 4, the shadow sample 3 (0.32 u), plus a margin.
        /// </summary>
        public const int DomeGrowCells = 32;

        /// <summary>FillDuration of the current biome (Liquid 0.35, Fire 0.60, Electric 0.25 s).</summary>
        public static float CurrentFillDuration
        {
            get
            {
                float d = BiomeTheme.Current.FillDuration;
                return d > 0.01f ? d : FillDuration;
            }
        }

        private const int PassBlurH = 0;
        private const int PassBlurV = 1;
        private const int PassUpsample = 2;
        private const int PassHeight = 3;
        private const int PassWideH = 4;
        private const int PassWideV = 5;
        private const int PassDomeH = 6;
        private const int PassDomeV = 7;
        private const int PassDomeField = 8;

        private static readonly int IdField = Shader.PropertyToID("_PIO_TerritoryField");
        private static readonly int IdHeight = Shader.PropertyToID("_PIO_TerritoryHeight");
        private static readonly int IdTexel = Shader.PropertyToID("_PIO_TerritoryTexel");
        private static readonly int IdArenaRect = Shader.PropertyToID("_PIO_ArenaRect");
        private static readonly int IdUnorm = Shader.PropertyToID("_PIO_TerritoryUnorm");
        private static readonly int IdBlurSource = Shader.PropertyToID("_PIO_BlurSource");
        private static readonly int IdBlurTexel = Shader.PropertyToID("_PIO_BlurTexel");
        private static readonly int IdPocket = Shader.PropertyToID("_PIO_PocketMask");
        private static readonly int IdPocketTexel = Shader.PropertyToID("_PIO_PocketTexel");
        private static readonly int IdFade = Shader.PropertyToID("_PIO_PlayerFade");
        private static readonly int IdReveal = Shader.PropertyToID("_PIO_RevealTime");
        private static readonly int IdRevealTexel = Shader.PropertyToID("_PIO_RevealTexel");
        private static readonly int IdNow = Shader.PropertyToID("_PIO_Now");
        private static readonly int IdDome = Shader.PropertyToID("_PIO_TerritoryDome");
        private static readonly int IdDomeTexel = Shader.PropertyToID("_PIO_TerritoryDomeTexel");

        private sealed class Wave
        {
            public int Id;
            public byte Owner;
            public int[] Cells;
            public double[] Times;
            public int Next;
        }

        private readonly Material blurMaterial;
        private readonly CommandBuffer cmd = new CommandBuffer { name = "PIO TerritoryField" };
        private readonly List<Wave> waves = new List<Wave>();
        private readonly List<int>[] pocketCells = new List<int>[4];
        private readonly CellMask[] pocketRef = new CellMask[4];
        private readonly int[] pocketVersion = new int[4];
        private readonly int[] pocketCount = new int[4];
        private readonly float[] fade = { 1f, 1f, 1f, 1f };
        private readonly double[] fadeStart = { double.NaN, double.NaN, double.NaN, double.NaN };
        private readonly List<int> scratch = new List<int>();

        private int size;                    // grid (mask) size in cells
        private Texture2D visualMask;
        private Texture2D pocketMask;
        private Texture2D revealTex;
        private bool revealHalf;             // R16_SFloat (else R32_SFloat)
        private float[] reveal;              // CPU copy of the reveal times (relative to revealEpoch)
        private NativeArray<ushort> revealPxHalf;
        private NativeArray<float> revealPxFloat;
        private double revealEpoch;
        private float revealStamp;           // the current reveal time (relative), used by SetVisual outside the waves
        private bool revealDirty;
        private NativeArray<Color32> maskPx, pocketPx;
        private RenderTexture pingA, pingB, pingC, field, height;
        private RenderTexture domeH, domeV, dome;   // wave D: dome grid after x, after y, and _PIO_TerritoryDome
        private GraphicsFormat fieldFormat;
        private bool unorm;
        private byte[] visual;               // displayed owner per cell (0 neutral, 1..4 players)
        private int[] cellWave;              // id of the latest wave that will reveal the cell, 0 when none
        private int nextWaveId = 1;

        private GameSession session;
        private Simulation sim;
        private double endedExtra;
        private int reconciledVersion = -1;
        private bool reconcileRequested;
        private bool mismatchLogged;
        private bool maskDirty, fullRebuild, pocketDirty;
        private int dirtyX0, dirtyY0, dirtyX1, dirtyY1;
        private bool disposed;

        public TerritoryField(Shader blurShader)
        {
            if (blurShader == null) throw new ArgumentNullException(nameof(blurShader), "TerritoryBlur shader missing");
            if (!blurShader.isSupported) Debug.LogError("[PainterIO] TerritoryBlur shader is not supported on this device");
            blurMaterial = new Material(blurShader) { name = "PIO TerritoryBlur", hideFlags = HideFlags.HideAndDontSave };
            for (int p = 0; p < 4; p++) pocketCells[p] = new List<int>();
            fieldFormat = SystemInfo.IsFormatSupported(GraphicsFormat.R16G16B16A16_SFloat, GraphicsFormatUsage.Render)
                ? GraphicsFormat.R16G16B16A16_SFloat
                : GraphicsFormat.R8G8B8A8_UNorm;
            unorm = fieldFormat == GraphicsFormat.R8G8B8A8_UNorm;
            Allocate(Mathf.RoundToInt((float)(2.0 * Tuning.ArenaHalfSize / Tuning.CellSize)));
            ClearAll();
            Publish();
        }

        /// <summary>The bound session (null before the first SessionStarted).</summary>
        public GameSession Session => session;

        /// <summary>Mask and grid size in cells (512 with the default tuning).</summary>
        public int Size => size;

        /// <summary>The CPU-side visual mask (RGBA32 linear, channel per player).</summary>
        public Texture2D VisualMask => visualMask;

        /// <summary>The pocket mask (RGBA32 linear, channel per player).</summary>
        public Texture2D PocketMask => pocketMask;

        /// <summary>_PIO_TerritoryField (t_i per channel).</summary>
        public RenderTexture Field => field;

        /// <summary>_PIO_TerritoryHeight (H_T, dH/dx, dH/dy, max t).</summary>
        public RenderTexture Height => height;

        /// <summary>
        /// _PIO_TerritoryDome (wave D): mask-sized (t_dome = max over the channels, dt_dome/dx, dt_dome/dy per world unit,
        /// t_dome at PIO_DOME_SHADOW_REACH toward the key light), in the field format.
        /// </summary>
        public RenderTexture Dome => dome;

        /// <summary>Format of the field and height textures (R16G16B16A16_SFloat, or R8G8B8A8_UNorm as fallback).</summary>
        public GraphicsFormat FieldFormat => fieldFormat;

        /// <summary>Current per-channel fade (_PIO_PlayerFade).</summary>
        public Vector4 PlayerFade => new Vector4(fade[0], fade[1], fade[2], fade[3]);

        /// <summary>Number of fill waves still running.</summary>
        public int ActiveWaves => waves.Count;

        /// <summary>Times the GPU passes ran (full or scissored), for tests and the probe.</summary>
        public int PassRuns { get; private set; }

        /// <summary>The _PIO_RevealTime texture (grid-sized, R16_SFloat or R32_SFloat).</summary>
        public Texture2D RevealTexture => revealTex;

        /// <summary>
        /// The reveal time of a cell relative to the current epoch (RevealNever for cells present at bind time); compare it
        /// with RevealNow, as the shaders do with _PIO_Now.
        /// </summary>
        public float RevealTimeOf(int cellIndex)
        {
            return reveal != null && cellIndex >= 0 && cellIndex < reveal.Length ? reveal[cellIndex] : RevealNever;
        }

        /// <summary>_PIO_Now: the visual clock relative to the reveal epoch.</summary>
        public float RevealNow => (float)(VisualTime() - revealEpoch);

        /// <summary>Cells the last reconciliation had to repair (0 when the event-driven state was right).</summary>
        public int LastReconcileFixes { get; private set; }

        /// <summary>The displayed owner of a cell (0 neutral, 1..4 = player index + 1).</summary>
        public byte VisualOwner(int cellIndex)
        {
            return visual != null && cellIndex >= 0 && cellIndex < visual.Length ? visual[cellIndex] : (byte)0;
        }

        /// <summary>The render time of the bound sim, the clock of the fill waves and of the evaporation.</summary>
        public double VisualTime()
        {
            if (session == null || sim == null) return 0.0;
            if (sim.Ended) return sim.Time + endedExtra;
            return sim.Time - (1.0 - session.Alpha) * sim.Config.Dt;
        }

        /// <summary>Binds a session (also on attract restarts): full rebuild of the masks and of the field.</summary>
        public void Bind(GameSession s)
        {
            if (disposed) return;
            session = s;
            sim = s != null ? s.Sim : null;
            endedExtra = 0.0;
            waves.Clear();
            for (int p = 0; p < 4; p++)
            {
                fade[p] = 1f;
                fadeStart[p] = double.NaN;
            }
            mismatchLogged = false;
            LastReconcileFixes = 0;
            if (sim == null)
            {
                ClearAll();
                return;
            }
            OwnerGrid g = sim.Grid;
            if (g.Size != size) Allocate(g.Size);
            Array.Clear(cellWave, 0, cellWave.Length);
            byte[] cells = g.Cells;
            AcquirePixels();
            NativeArray<Color32> px = maskPx;
            for (int c = 0; c < visual.Length; c++)
            {
                byte o = cells[c];
                if (o == OwnerGrid.Void || o > 4) o = 0;
                visual[c] = o;
                px[c] = ChannelColor(o);
            }
            reconciledVersion = g.Version;
            reconcileRequested = false;
            ClearPockets();
            ResetReveal();
            maskDirty = true;
            fullRebuild = true;
        }

        /// <summary>Forwarded sim events (Return with cells starts a fill wave, Eliminated starts the evaporation).</summary>
        public void OnSimEvent(SimEvent e)
        {
            if (disposed || sim == null || e == null) return;
            revealStamp = (float)(VisualTime() - revealEpoch);
            switch (e.Type)
            {
                case SimEventType.Return:
                    if (e.Cells != null && e.Cells.Length > 0) AddWave(e.Player, e.Point, e.Cells, e.Time);
                    break;
                case SimEventType.Eliminated:
                    StartEvaporation(e.Player, e.Time);
                    break;
            }
        }

        /// <summary>Per frame (LiquidRenderer.LateUpdate): waves, evaporation, reconciliation, pockets, uploads, passes.</summary>
        public void Update(float unscaledDeltaTime)
        {
            if (disposed) return;
            if (RenderTexturesLost())
            {
                AllocateTargets();
                fullRebuild = true;
                maskDirty = true;
            }
            AcquirePixels();
            if (sim != null && session != null && session.Sim != sim) Bind(session);   // attract restart missed
            if (sim != null)
            {
                if (sim.Ended) endedExtra += Mathf.Max(0f, unscaledDeltaTime);
                double now = VisualTime();
                if (now - revealEpoch > RevealRebaseSeconds) RebaseReveal(now);
                revealStamp = (float)(now - revealEpoch);
                AdvanceWaves(now);
                AdvanceEvaporation(now);
                if (sim.Grid.Version != reconciledVersion || reconcileRequested) Reconcile();
                UpdatePockets();
            }
            if (maskDirty)
            {
                visualMask.Apply(false, false);
                RunPasses(fullRebuild);
                maskDirty = false;
                fullRebuild = false;
            }
            if (pocketDirty)
            {
                pocketMask.Apply(false, false);
                pocketDirty = false;
            }
            if (revealDirty && revealTex != null)
            {
                revealTex.Apply(false, false);
                revealDirty = false;
            }
            Publish();
        }

        public void Dispose()
        {
            if (disposed) return;
            disposed = true;
            session = null;
            sim = null;
            cmd.Release();
            ReleaseTargets();
            DestroyObject(visualMask);
            DestroyObject(pocketMask);
            DestroyObject(revealTex);
            DestroyObject(blurMaterial);
            visualMask = null;
            pocketMask = null;
            revealTex = null;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Fill waves and evaporation.

        private void AddWave(int player, Vec2d origin, int[] cells, double startTime)
        {
            if (player < 0 || player >= 4) return;
            OwnerGrid g = sim.Grid;
            int n = cells.Length;
            var keys = new double[n];
            var items = new int[n];
            double cs = g.CellSize, org = g.Origin;
            double dMax = 0.0;
            for (int k = 0; k < n; k++)
            {
                int c = cells[k];
                int i = c % size, j = c / size;
                double dx = org + (i + 0.5) * cs - origin.X;
                double dy = org + (j + 0.5) * cs - origin.Y;
                double d = Math.Sqrt(dx * dx + dy * dy);
                keys[k] = d;
                items[k] = c;
                if (d > dMax) dMax = d;
            }
            Array.Sort(keys, items);
            double fill = CurrentFillDuration;
            var wave = new Wave { Id = nextWaveId++, Owner = (byte)(player + 1), Cells = items, Times = keys };
            if (nextWaveId == int.MaxValue) nextWaveId = 1;
            for (int k = 0; k < n; k++)
            {
                keys[k] = startTime + (dMax > 1e-9 ? fill * keys[k] / dMax : 0.0);
                int c = items[k];
                if (c >= 0 && c < cellWave.Length) cellWave[c] = wave.Id;
            }
            waves.Add(wave);
        }

        private void AdvanceWaves(double now)
        {
            for (int w = waves.Count - 1; w >= 0; w--)
            {
                Wave wave = waves[w];
                while (wave.Next < wave.Cells.Length && wave.Times[wave.Next] <= now)
                {
                    int c = wave.Cells[wave.Next++];
                    if (c < 0 || c >= cellWave.Length || cellWave[c] != wave.Id) continue;   // a later wave owns it
                    cellWave[c] = 0;
                    SetVisual(c, wave.Owner, (float)(wave.Times[wave.Next - 1] - revealEpoch));
                }
                if (wave.Next >= wave.Cells.Length)
                {
                    waves.RemoveAt(w);
                    reconcileRequested = true;
                }
            }
        }

        private void StartEvaporation(int player, double time)
        {
            if (player < 0 || player >= 4) return;
            byte id = (byte)(player + 1);
            // Cells still waiting in this player's waves show its color at once and evaporate with it.
            for (int w = waves.Count - 1; w >= 0; w--)
            {
                Wave wave = waves[w];
                if (wave.Owner != id) continue;
                for (int k = wave.Next; k < wave.Cells.Length; k++)
                {
                    int c = wave.Cells[k];
                    if (c < 0 || c >= cellWave.Length || cellWave[c] != wave.Id) continue;
                    cellWave[c] = 0;
                    SetVisual(c, id);
                }
                waves.RemoveAt(w);
            }
            if (double.IsNaN(fadeStart[player])) fadeStart[player] = time;
        }

        private void AdvanceEvaporation(double now)
        {
            for (int p = 0; p < 4; p++)
            {
                if (double.IsNaN(fadeStart[p])) continue;
                double k = (now - fadeStart[p]) / EvaporationSeconds;
                if (k < 1.0)
                {
                    fade[p] = Mathf.Clamp01((float)(1.0 - k));
                    continue;
                }
                byte id = (byte)(p + 1);
                for (int c = 0; c < visual.Length; c++)
                {
                    if (visual[c] == id) SetVisual(c, 0);
                }
                fade[p] = 1f;
                fadeStart[p] = double.NaN;
                reconcileRequested = true;
            }
        }

        private void Reconcile()
        {
            reconcileRequested = false;
            OwnerGrid g = sim.Grid;
            reconciledVersion = g.Version;
            byte[] cells = g.Cells;
            int fixes = 0;
            for (int c = 0; c < visual.Length; c++)
            {
                if (cellWave[c] != 0) continue;
                byte v = visual[c];
                if (v != 0 && !double.IsNaN(fadeStart[v - 1])) continue;
                byte o = cells[c];
                if (o == OwnerGrid.Void || o > 4) o = 0;
                if (o == v) continue;
                SetVisual(c, o);
                fixes++;
            }
            LastReconcileFixes = fixes;
            if (fixes > 0 && !mismatchLogged)
            {
                mismatchLogged = true;
                Debug.Log("[PainterIO] TerritoryField reconciled " + fixes + " cell(s) with the grid");
            }
        }

        private void SetVisual(int c, byte owner)
        {
            SetVisual(c, owner, revealStamp);
        }

        private void SetVisual(int c, byte owner, float revealTime)
        {
            if (visual[c] == owner) return;
            visual[c] = owner;
            maskPx[c] = ChannelColor(owner);
            WriteReveal(c, revealTime);
            MarkDirty(c % size, c / size);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Reveal times (contract 25.2).

        private void WriteReveal(int c, float value)
        {
            if (reveal == null || c < 0 || c >= reveal.Length) return;
            reveal[c] = value;
            if (revealHalf) revealPxHalf[c] = Mathf.FloatToHalf(value);
            else revealPxFloat[c] = value;
            revealDirty = true;
        }

        private void ResetReveal()
        {
            revealEpoch = VisualTime();
            revealStamp = 0f;
            if (reveal == null) return;
            ushort never = Mathf.FloatToHalf(RevealNever);
            for (int c = 0; c < reveal.Length; c++)
            {
                reveal[c] = RevealNever;
                if (revealHalf) revealPxHalf[c] = never;
                else revealPxFloat[c] = RevealNever;
            }
            revealDirty = true;
        }

        // Moves the epoch to now; every stored time shifts by the same amount (reveals older than RevealForgetSeconds are
        // forgotten), so _PIO_Now - reveal is unchanged.
        private void RebaseReveal(double now)
        {
            float shift = (float)(now - revealEpoch);
            revealEpoch = now;
            if (reveal == null) return;
            for (int c = 0; c < reveal.Length; c++)
            {
                float v = reveal[c];
                if (v <= RevealNever + 1f) continue;
                v -= shift;
                if (v < -RevealForgetSeconds) v = RevealNever;
                reveal[c] = v;
                if (revealHalf) revealPxHalf[c] = Mathf.FloatToHalf(v);
                else revealPxFloat[c] = v;
            }
            revealDirty = true;
        }

        private void MarkDirty(int i, int j)
        {
            if (!maskDirty)
            {
                maskDirty = true;
                dirtyX0 = dirtyX1 = i;
                dirtyY0 = dirtyY1 = j;
                return;
            }
            if (i < dirtyX0) dirtyX0 = i;
            if (i > dirtyX1) dirtyX1 = i;
            if (j < dirtyY0) dirtyY0 = j;
            if (j > dirtyY1) dirtyY1 = j;
        }

        private static Color32 ChannelColor(byte owner)
        {
            switch (owner)
            {
                case 1: return new Color32(255, 0, 0, 0);
                case 2: return new Color32(0, 255, 0, 0);
                case 3: return new Color32(0, 0, 255, 0);
                case 4: return new Color32(0, 0, 0, 255);
                default: return new Color32(0, 0, 0, 0);
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Pockets.

        private void UpdatePockets()
        {
            int n = Math.Min(4, sim.Players.Count);
            for (int p = 0; p < 4; p++)
            {
                CellMask m = p < n ? sim.Players[p].Pocket : null;
                int version = m != null ? m.Version : 0;
                int count = m != null ? m.Count : 0;
                if (m == pocketRef[p] && version == pocketVersion[p] && count == pocketCount[p]) continue;
                pocketRef[p] = m;
                pocketVersion[p] = version;
                pocketCount[p] = count;
                RebuildPocket(p, m);
            }
        }

        private void RebuildPocket(int p, CellMask m)
        {
            NativeArray<Color32> px = pocketPx;
            List<int> previous = pocketCells[p];
            for (int k = 0; k < previous.Count; k++)
            {
                int c = previous[k];
                Color32 v = px[c];
                SetChannel(ref v, p, 0);
                px[c] = v;
            }
            previous.Clear();
            if (m != null && m.Count > 0)
            {
                scratch.Clear();
                m.CopyIndices(scratch);
                for (int k = 0; k < scratch.Count; k++)
                {
                    int c = scratch[k];
                    if (c < 0 || c >= px.Length) continue;
                    Color32 v = px[c];
                    SetChannel(ref v, p, 255);
                    px[c] = v;
                    previous.Add(c);
                }
            }
            pocketDirty = true;
        }

        private static void SetChannel(ref Color32 v, int channel, byte value)
        {
            switch (channel)
            {
                case 0: v.r = value; break;
                case 1: v.g = value; break;
                case 2: v.b = value; break;
                default: v.a = value; break;
            }
        }

        private void ClearPockets()
        {
            NativeArray<Color32> px = pocketPx;
            var zero = new Color32(0, 0, 0, 0);
            for (int c = 0; c < px.Length; c++) px[c] = zero;
            for (int p = 0; p < 4; p++)
            {
                pocketCells[p].Clear();
                pocketRef[p] = null;
                pocketVersion[p] = -1;
                pocketCount[p] = -1;
            }
            pocketDirty = true;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Textures and GPU passes.

        private void Allocate(int gridSize)
        {
            size = Mathf.Max(8, gridSize);
            int cellCount = size * size;
            visual = new byte[cellCount];
            cellWave = new int[cellCount];
            DestroyObject(visualMask);
            DestroyObject(pocketMask);
            visualMask = NewMask("PIO VisualMask");
            pocketMask = NewMask("PIO PocketMask");
            DestroyObject(revealTex);
            revealHalf = SystemInfo.IsFormatSupported(GraphicsFormat.R16_SFloat, GraphicsFormatUsage.Sample);
            revealTex = new Texture2D(size, size, revealHalf ? GraphicsFormat.R16_SFloat : GraphicsFormat.R32_SFloat, TextureCreationFlags.None)
            {
                name = "PIO RevealTime",
                filterMode = revealHalf ? FilterMode.Bilinear : FilterMode.Point,
                wrapMode = TextureWrapMode.Clamp,
                anisoLevel = 0,
                hideFlags = HideFlags.HideAndDontSave,
            };
            reveal = new float[cellCount];
            AcquirePixels();
            ResetReveal();
            AllocateTargets();
            for (int p = 0; p < 4; p++)
            {
                pocketCells[p].Clear();
                pocketRef[p] = null;
                pocketVersion[p] = -1;
                pocketCount[p] = -1;
            }
        }

        private void AllocateTargets()
        {
            ReleaseTargets();
            pingA = NewTarget("PIO TerritoryPingA", size, fieldFormat);
            pingB = NewTarget("PIO TerritoryPingB", size, fieldFormat);
            pingC = NewTarget("PIO TerritoryPingC", size, fieldFormat);
            field = NewTarget("PIO TerritoryField", size * FieldScale, fieldFormat);
            height = NewTarget("PIO TerritoryHeight", size * FieldScale, fieldFormat);
            int domeGrid = DomeGridSize(size);
            domeH = NewTarget("PIO TerritoryDomeH", domeGrid, fieldFormat);
            domeV = NewTarget("PIO TerritoryDomeV", domeGrid, fieldFormat);
            dome = NewTarget("PIO TerritoryDome", size, fieldFormat);
        }

        /// <summary>Side of the dome blur grid for a mask of the given side (half of it, rounded up).</summary>
        public static int DomeGridSize(int maskSize)
        {
            return Mathf.Max(4, (maskSize + DomeDownscale - 1) / DomeDownscale);
        }

        // Views into the CPU copies of the masks (refreshed once per frame and after any reallocation).
        private void AcquirePixels()
        {
            maskPx = visualMask.GetRawTextureData<Color32>();
            pocketPx = pocketMask.GetRawTextureData<Color32>();
            if (revealTex != null)
            {
                if (revealHalf) revealPxHalf = revealTex.GetRawTextureData<ushort>();
                else revealPxFloat = revealTex.GetRawTextureData<float>();
            }
        }

        private Texture2D NewMask(string name)
        {
            var t = new Texture2D(size, size, GraphicsFormat.R8G8B8A8_UNorm, TextureCreationFlags.None)
            {
                name = name,
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp,
                anisoLevel = 0,
                hideFlags = HideFlags.HideAndDontSave,
            };
            return t;
        }

        private static RenderTexture NewTarget(string name, int side, GraphicsFormat format)
        {
            var desc = new RenderTextureDescriptor(side, side, format, 0)
            {
                useMipMap = false,
                autoGenerateMips = false,
                msaaSamples = 1,
                sRGB = false,
            };
            var rt = new RenderTexture(desc)
            {
                name = name,
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp,
                anisoLevel = 0,
                hideFlags = HideFlags.HideAndDontSave,
            };
            rt.Create();
            return rt;
        }

        private bool RenderTexturesLost()
        {
            return pingA == null || pingB == null || pingC == null || field == null || height == null
                   || !pingA.IsCreated() || !pingB.IsCreated() || !pingC.IsCreated() || !field.IsCreated() || !height.IsCreated()
                   || domeH == null || domeV == null || dome == null
                   || !domeH.IsCreated() || !domeV.IsCreated() || !dome.IsCreated();
        }

        private void ReleaseTargets()
        {
            ReleaseTarget(ref pingA);
            ReleaseTarget(ref pingB);
            ReleaseTarget(ref pingC);
            ReleaseTarget(ref field);
            ReleaseTarget(ref height);
            ReleaseTarget(ref domeH);
            ReleaseTarget(ref domeV);
            ReleaseTarget(ref dome);
        }

        private static void ReleaseTarget(ref RenderTexture rt)
        {
            if (rt == null) return;
            rt.Release();
            DestroyObject(rt);
            rt = null;
        }

        private void ClearAll()
        {
            Array.Clear(visual, 0, visual.Length);
            Array.Clear(cellWave, 0, cellWave.Length);
            NativeArray<Color32> px = maskPx;
            var zero = new Color32(0, 0, 0, 0);
            for (int c = 0; c < px.Length; c++) px[c] = zero;
            ClearPockets();
            ResetReveal();
            maskDirty = true;
            fullRebuild = true;
        }

        private void RunPasses(bool full)
        {
            RectInt cells;
            if (full) cells = new RectInt(0, 0, size, size);
            else
            {
                int x0 = Mathf.Max(0, dirtyX0 - DirtyGrowCells);
                int y0 = Mathf.Max(0, dirtyY0 - DirtyGrowCells);
                int x1 = Mathf.Min(size - 1, dirtyX1 + DirtyGrowCells);
                int y1 = Mathf.Min(size - 1, dirtyY1 + DirtyGrowCells);
                cells = new RectInt(x0, y0, x1 - x0 + 1, y1 - y0 + 1);
                if (cells.width >= size && cells.height >= size) full = true;
            }
            var maskTexel = new Vector4(1f / size, 1f / size, size, size);
            int big = size * FieldScale;
            var bigCells = new RectInt(cells.x * FieldScale, cells.y * FieldScale, cells.width * FieldScale, cells.height * FieldScale);

            cmd.Clear();
            cmd.SetGlobalVector(IdArenaRect, ArenaRect());
            cmd.SetGlobalFloat(IdUnorm, unorm ? 1f : 0f);
            Pass(visualMask, maskTexel, pingA, PassBlurH, cells, full);
            Pass(pingA, maskTexel, pingB, PassBlurV, cells, full);
            Pass(pingB, maskTexel, field, PassUpsample, bigCells, full);
            Pass(pingB, maskTexel, pingA, PassWideH, cells, full);
            Pass(pingA, maskTexel, pingC, PassWideV, cells, full);
            Pass(pingC, maskTexel, height, PassHeight, bigCells, full);

            // Wave D dome field: its own wider rectangle (the dome kernel reaches DomeGrowCells), on its own textures,
            // so a scissored pass always reads, outside its rectangle, values the same pass wrote earlier from an
            // unchanged mask.
            RectInt domeCells;
            bool domeFull = full;
            if (domeFull) domeCells = new RectInt(0, 0, size, size);
            else
            {
                int x0 = Mathf.Max(0, dirtyX0 - DomeGrowCells);
                int y0 = Mathf.Max(0, dirtyY0 - DomeGrowCells);
                int x1 = Mathf.Min(size - 1, dirtyX1 + DomeGrowCells);
                int y1 = Mathf.Min(size - 1, dirtyY1 + DomeGrowCells);
                domeCells = new RectInt(x0, y0, x1 - x0 + 1, y1 - y0 + 1);
                if (domeCells.width >= size && domeCells.height >= size) domeFull = true;
            }
            int grid = DomeGridSize(size);
            var gridTexel = new Vector4(1f / grid, 1f / grid, grid, grid);
            int gx0 = domeCells.xMin / DomeDownscale, gy0 = domeCells.yMin / DomeDownscale;
            int gx1 = Mathf.Min(grid, (domeCells.xMax + DomeDownscale - 1) / DomeDownscale);
            int gy1 = Mathf.Min(grid, (domeCells.yMax + DomeDownscale - 1) / DomeDownscale);
            var gridCells = new RectInt(gx0, gy0, gx1 - gx0, gy1 - gy0);
            Pass(visualMask, maskTexel, domeH, PassDomeH, gridCells, domeFull);
            Pass(domeH, gridTexel, domeV, PassDomeV, gridCells, domeFull);
            Pass(domeV, gridTexel, dome, PassDomeField, domeCells, domeFull);
            Graphics.ExecuteCommandBuffer(cmd);
            cmd.Clear();
            PassRuns++;
        }

        private void Pass(Texture source, Vector4 sourceTexel, RenderTexture target, int pass, RectInt scissor, bool full)
        {
            cmd.SetGlobalTexture(IdBlurSource, source);
            cmd.SetGlobalVector(IdBlurTexel, sourceTexel);
            cmd.SetRenderTarget(target, full ? RenderBufferLoadAction.DontCare : RenderBufferLoadAction.Load, RenderBufferStoreAction.Store);
            if (!full) cmd.EnableScissorRect(new Rect(scissor.x, scissor.y, scissor.width, scissor.height));
            cmd.DrawProcedural(Matrix4x4.identity, blurMaterial, pass, MeshTopology.Triangles, 3);
            if (!full) cmd.DisableScissorRect();
        }

        private Vector4 ArenaRect()
        {
            if (sim != null)
            {
                OwnerGrid g = sim.Grid;
                float o = (float)g.Origin;
                float s = (float)(g.Size * g.CellSize);
                return new Vector4(o, o, s, s);
            }
            float h = (float)Tuning.ArenaHalfSize;
            return new Vector4(-h, -h, 2f * h, 2f * h);
        }

        private void Publish()
        {
            if (field == null || height == null) return;
            int big = size * FieldScale;
            Shader.SetGlobalTexture(IdField, field);
            Shader.SetGlobalTexture(IdHeight, height);
            Shader.SetGlobalVector(IdTexel, new Vector4(1f / big, 1f / big, big, big));
            Shader.SetGlobalVector(IdArenaRect, ArenaRect());
            Shader.SetGlobalFloat(IdUnorm, unorm ? 1f : 0f);
            Shader.SetGlobalTexture(IdPocket, pocketMask);
            Shader.SetGlobalVector(IdPocketTexel, new Vector4(1f / size, 1f / size, size, size));
            Shader.SetGlobalVector(IdFade, PlayerFade);
            if (revealTex != null)
            {
                Shader.SetGlobalTexture(IdReveal, revealTex);
                Shader.SetGlobalVector(IdRevealTexel, new Vector4(1f / size, 1f / size, size, size));
            }
            Shader.SetGlobalFloat(IdNow, (float)(VisualTime() - revealEpoch));
            if (dome != null)
            {
                Shader.SetGlobalTexture(IdDome, dome);
                Shader.SetGlobalVector(IdDomeTexel, new Vector4(1f / size, 1f / size, size, size));
            }
        }

        private static void DestroyObject(UnityEngine.Object o)
        {
            if (o == null) return;
            if (Application.isPlaying) UnityEngine.Object.Destroy(o);
            else UnityEngine.Object.DestroyImmediate(o);
        }
    }
}
