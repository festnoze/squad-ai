// Owned by B2 (actors). Contract 12.3 Thread and 12.2 item 2 (FieldStroke mesh conventions): the liquid thread of a
// trailing player as a FieldStroke triangle list on layer 31, along the sim trail smoothed for display (uniform
// Catmull-Rom sampled every 0.15 u; the sim trail stays exact). Visible radius 0.17 u, a neck widened up to 2.2x over
// the first 0.3 u from the exit point, a slight thinning over the last 0.45 u before the pearl (inside HeadGrace, never
// exposed), the tip at GameSession.RenderPos. After a cut (RetractionView) the thread is drawn on [0, s_cut - 0.25]
// (pinched taper) and [RenderSparkS, L]. After a return the last mesh lingers as a ghost while the fill wave arrives.
using System;
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace PainterIO.Runtime
{
    /// <summary>The display curve of a trail: uniform Catmull-Rom through the sim points (reflected phantom end points),
    /// addressed by sim arc length.</summary>
    public static class TrailCurve
    {
        /// <summary>
        /// Point at arc length s on the Catmull-Rom curve through the trail points (clamped to [0, Length]). segment is a
        /// cursor: pass the value returned by the previous call for increasing s (any value works, it is validated).
        /// </summary>
        public static Vector2 Evaluate(IReadOnlyList<Vec2d> points, IReadOnlyList<double> arc, double s, ref int segment)
        {
            int n = points.Count;
            if (n == 0) return Vector2.zero;
            if (n == 1 || s <= 0.0) return ToVector(points[0]);
            double length = arc[n - 1];
            if (s >= length) return ToVector(points[n - 1]);
            int k = segment;
            if (k < 0 || k > n - 2 || arc[k] > s) k = Find(arc, s);
            while (k < n - 2 && arc[k + 1] < s) k++;
            segment = k;
            double a0 = arc[k], a1 = arc[k + 1];
            double t = a1 - a0 > 1e-12 ? (s - a0) / (a1 - a0) : 0.0;
            // Phantom end points (reflections) keep the end segments straight and uniformly parameterized.
            Vec2d p1 = points[k], p2 = points[k + 1];
            Vec2d p0 = k > 0 ? points[k - 1] : 2.0 * p1 - p2;
            Vec2d p3 = k + 2 < n ? points[k + 2] : 2.0 * p2 - p1;
            double t2 = t * t, t3 = t2 * t;
            double x = 0.5 * (2.0 * p1.X + (p2.X - p0.X) * t + (2.0 * p0.X - 5.0 * p1.X + 4.0 * p2.X - p3.X) * t2
                              + (3.0 * p1.X - p0.X - 3.0 * p2.X + p3.X) * t3);
            double y = 0.5 * (2.0 * p1.Y + (p2.Y - p0.Y) * t + (2.0 * p0.Y - 5.0 * p1.Y + 4.0 * p2.Y - p3.Y) * t2
                              + (3.0 * p1.Y - p0.Y - 3.0 * p2.Y + p3.Y) * t3);
            return new Vector2((float)x, (float)y);
        }

        /// <summary>Unit tangent of the sim polyline at arc length s (direction of increasing s).</summary>
        public static Vector2 Direction(IReadOnlyList<Vec2d> points, IReadOnlyList<double> arc, double s, ref int segment)
        {
            int n = points.Count;
            if (n < 2) return Vector2.right;
            int k = segment;
            double sc = s < 0.0 ? 0.0 : (s > arc[n - 1] ? arc[n - 1] : s);
            if (k < 0 || k > n - 2 || arc[k] > sc) k = Find(arc, sc);
            while (k < n - 2 && arc[k + 1] < sc) k++;
            segment = k;
            // Average over about 0.3 u for a stable direction on dense trails.
            int a = k, b = k + 1;
            while (a > 0 && sc - arc[a] < 0.15) a--;
            while (b < n - 1 && arc[b] - sc < 0.15) b++;
            Vec2d d = points[b] - points[a];
            double len = d.Length;
            return len > 1e-9 ? new Vector2((float)(d.X / len), (float)(d.Y / len)) : Vector2.right;
        }

        /// <summary>Arc length of the interpolated head on its trail: L - |Pos - RenderPos|, clamped to [0, L].</summary>
        public static double RenderLength(PlayerState p, Vector2 renderPos)
        {
            double length = p.Trail.Length;
            double dx = p.Pos.X - renderPos.x, dy = p.Pos.Y - renderPos.y;
            double back = Math.Sqrt(dx * dx + dy * dy);
            double l = length - back;
            return l < 0.0 ? 0.0 : (l > length ? length : l);
        }

        public static Vector2 ToVector(Vec2d v)
        {
            return new Vector2((float)v.X, (float)v.Y);
        }

        private static int Find(IReadOnlyList<double> arc, double s)
        {
            int lo = 0, hi = arc.Count - 2;
            while (lo < hi)
            {
                int mid = (lo + hi + 1) >> 1;
                if (arc[mid] <= s) lo = mid;
                else hi = mid - 1;
            }
            return lo;
        }
    }

    /// <summary>Builds FieldStroke triangle lists (contract 12.2 item 2) from sampled pieces, without managed garbage.</summary>
    public sealed class StrokeBuilder
    {
        /// <summary>Segments of each round end cap (half disc).</summary>
        public const int CapSegments = 6;

        /// <summary>Samples of every piece since Begin (world centers and visible radii), pieces back to back.</summary>
        public readonly List<Vector2> Centers = new List<Vector2>(512);
        public readonly List<float> Radii = new List<float>(512);
        /// <summary>Per-sample amplitude multiplier (uv0.x of the FieldStroke vertices), 1 for a live thread.</summary>
        public readonly List<float> Amplitudes = new List<float>(512);
        /// <summary>Index in Centers of the first sample of each piece.</summary>
        public readonly List<int> PieceStarts = new List<int>(4);
        public readonly List<Vector3> Vertices = new List<Vector3>(1024);
        public readonly List<Vector2> Uvs = new List<Vector2>(1024);
        public readonly List<int> Indices = new List<int>(3072);
        private Vector2 min, max;
        private int pieceStart;

        public int PieceCount => PieceStarts.Count;

        /// <summary>Number of samples of piece k.</summary>
        public int PieceLength(int k)
        {
            int end = k + 1 < PieceStarts.Count ? PieceStarts[k + 1] : Centers.Count;
            return end - PieceStarts[k];
        }

        public Bounds Bounds
        {
            get
            {
                if (Vertices.Count == 0) return new Bounds(Vector3.zero, Vector3.one);
                Vector2 c = (min + max) * 0.5f, size = max - min;
                // Contract 12.2: the trail bounding box grown by 1 u.
                return new Bounds(new Vector3(c.x, c.y, 0f), new Vector3(size.x + 2f, size.y + 2f, 1f));
            }
        }

        public void Begin()
        {
            Centers.Clear();
            Radii.Clear();
            Amplitudes.Clear();
            PieceStarts.Clear();
            Vertices.Clear();
            Uvs.Clear();
            Indices.Clear();
            pieceStart = 0;
            min = new Vector2(float.MaxValue, float.MaxValue);
            max = new Vector2(float.MinValue, float.MinValue);
        }

        public void BeginPiece()
        {
            pieceStart = Centers.Count;
        }

        /// <summary>Adds one sample of the current piece: world center, visible radius at amplitude 1, amplitude multiplier.</summary>
        public void AddSample(Vector2 center, float visibleRadius, float amplitude = 1f)
        {
            if (Centers.Count > pieceStart && (Centers[Centers.Count - 1] - center).sqrMagnitude < 1e-10f) return;
            Centers.Add(center);
            Radii.Add(Mathf.Max(0.004f, visibleRadius));
            Amplitudes.Add(Mathf.Max(0f, amplitude));
        }

        /// <summary>Emits the current piece as a strip with a half-disc cap at each end.</summary>
        public void EndPiece()
        {
            int s0 = pieceStart;
            int n = Centers.Count - s0;
            if (n < 2)
            {
                // Too short to draw: drop its samples.
                Centers.RemoveRange(s0, n);
                Radii.RemoveRange(s0, n);
                Amplitudes.RemoveRange(s0, n);
                return;
            }
            PieceStarts.Add(s0);
            int first = Vertices.Count;
            Vector2 tPrev = Vector2.right;
            for (int j = 0; j < n; j++)
            {
                Vector2 a = Centers[s0 + (j > 0 ? j - 1 : 0)];
                Vector2 b = Centers[s0 + (j < n - 1 ? j + 1 : n - 1)];
                Vector2 t = b - a;
                float len = t.magnitude;
                t = len > 1e-7f ? t / len : tPrev;
                tPrev = t;
                var normal = new Vector2(-t.y, t.x);
                Vector2 c = Centers[s0 + j];
                float h = LiquidLayers.SupportForVisibleRadius(Radii[s0 + j], 1f);
                Vector2 l = c + normal * h, r = c - normal * h;
                float m = Amplitudes[s0 + j];
                Vertices.Add(new Vector3(l.x, l.y, 0f));
                Uvs.Add(new Vector2(m, -1f));
                Vertices.Add(new Vector3(r.x, r.y, 0f));
                Uvs.Add(new Vector2(m, 1f));
                Grow(c, h);
                if (j > 0)
                {
                    int l0 = first + 2 * (j - 1), r0 = l0 + 1, l1 = l0 + 2, r1 = l0 + 3;
                    Indices.Add(l0);
                    Indices.Add(l1);
                    Indices.Add(r0);
                    Indices.Add(r0);
                    Indices.Add(l1);
                    Indices.Add(r1);
                }
            }
            Cap(Centers[s0], Centers[s0 + 1] - Centers[s0], Radii[s0], Amplitudes[s0], true);
            Cap(Centers[s0 + n - 1], Centers[s0 + n - 1] - Centers[s0 + n - 2], Radii[s0 + n - 1], Amplitudes[s0 + n - 1], false);
        }

        /// <summary>Uploads the triangle list to mesh (identity transform, world-space vertices).</summary>
        public void Upload(Mesh mesh)
        {
            mesh.Clear(true);
            if (Vertices.Count == 0) return;
            mesh.SetVertices(Vertices);
            mesh.SetUVs(0, Uvs);
            mesh.SetTriangles(Indices, 0, false);
            mesh.bounds = Bounds;
        }

        private void Cap(Vector2 c, Vector2 tangent, float visibleRadius, float amplitude, bool start)
        {
            float len = tangent.magnitude;
            Vector2 t = len > 1e-7f ? tangent / len : Vector2.right;
            var normal = new Vector2(-t.y, t.x);
            Vector2 back = start ? -t : t;
            float h = LiquidLayers.SupportForVisibleRadius(visibleRadius, 1f);
            int center = Vertices.Count;
            Vertices.Add(new Vector3(c.x, c.y, 0f));
            Uvs.Add(new Vector2(amplitude, 0f));
            for (int m = 0; m <= CapSegments; m++)
            {
                float a = Mathf.PI * m / CapSegments;
                Vector2 p = c + (normal * Mathf.Cos(a) + back * Mathf.Sin(a)) * h;
                Vertices.Add(new Vector3(p.x, p.y, 0f));
                Uvs.Add(new Vector2(amplitude, 1f));
                if (m > 0)
                {
                    Indices.Add(center);
                    Indices.Add(center + m);
                    Indices.Add(center + m + 1);
                }
            }
        }

        private void Grow(Vector2 c, float h)
        {
            if (c.x - h < min.x) min.x = c.x - h;
            if (c.y - h < min.y) min.y = c.y - h;
            if (c.x + h > max.x) max.x = c.x + h;
            if (c.y + h > max.y) max.y = c.y + h;
        }
    }

    /// <summary>The liquid thread of one player (FieldStroke on layer 31, MaterialPropertyBlock _Channel / _Amplitude).</summary>
    public sealed class ThreadView
    {
        public const float VisibleRadius = 0.17f;
        public const float SampleSpacing = 0.15f;
        public const float NeckLength = 0.3f;
        public const float NeckWiden = 2.2f;
        public const float TipThinLength = 0.45f;
        public const float TipThinFactor = 0.74f;
        /// <summary>The upstream piece of a cut thread ends this far before s_cut (contract 12.3).</summary>
        public const float CutGap = 0.25f;
        public const float TaperLength = 0.6f;
        public const float TaperEndFactor = 0.16f;
        /// <summary>
        /// After a return with cells, the last thread lingers as a ghost that dissolves where the fill wave arrives (B1's
        /// TerritoryField rule: a cell at distance d from the return point appears FillDuration * d / dMax after the Return,
        /// on the sim render clock), through the per-vertex amplitude multiplier: no thread over the fresh puddle, no gap
        /// before the wave reaches the far side of the loop.
        /// </summary>
        public const float FillDuration = 0.35f;
        /// <summary>Width of the dissolve band behind and ahead of the fill front (world units).</summary>
        public const float DissolveBehind = 0.1f;
        public const float DissolveAhead = 0.35f;
        /// <summary>Fade of whatever remains once the wave is complete, and of a ghost without cells.</summary>
        public const float GhostTailFade = 0.1f;
        public const float EmptyReturnFade = 0.15f;
        public const float DeathFade = 0.22f;
        public const float GhostTimeout = 1.2f;
        /// <summary>Pieces shorter than this are not drawn.</summary>
        public const float MinPiece = 0.04f;
        /// <summary>
        /// Contract 24 (v1.4): a saved chased return captures nothing and has no fill wave; the remaining thread pieces
        /// dissolve into small evaporating beads over EvaporateSeconds while the field thread fades out quickly.
        /// </summary>
        public const float EvaporateSeconds = 0.4f;
        public const float EvaporateSpacing = 0.24f;
        public const float EvaporateRadiusFactor = 0.85f;
        public const float EvaporateMaxDelay = 0.12f;
        public const float EvaporateFieldFade = 0.1f;
        public const int MaxEvaporatingBeads = 2000;

        private static readonly int ChannelId = Shader.PropertyToID("_Channel");
        private static readonly int AmplitudeId = Shader.PropertyToID("_Amplitude");

        private readonly int player;
        private readonly StrokeBuilder builder = new StrokeBuilder();
        private readonly Stroke live;
        private readonly Stroke ghost;
        private readonly StrokeBuilder ghostBuilder = new StrokeBuilder();
        private readonly List<Vector2> ghostCenters = new List<Vector2>(512);
        private readonly List<float> ghostRadii = new List<float>(512);
        private readonly List<int> ghostStarts = new List<int>(4);
        private float ghostStart = -100f;
        private float ghostFade;
        private bool ghostActive;
        private bool ghostSynced;
        private Vector2 ghostOrigin;
        private double ghostSimStart;
        private double ghostReach;
        private float ghostFillDuration = FillDuration;   // the fill time of the wave the ghost follows (biome, 25.2)
        private float ghostTailStart = -1f;
        private readonly QuadBatch beads;
        private readonly Vector2[] evapPos = new Vector2[MaxEvaporatingBeads];
        private readonly Vector2[] evapDrift = new Vector2[MaxEvaporatingBeads];
        private readonly float[] evapRadius = new float[MaxEvaporatingBeads];
        private readonly float[] evapDelay = new float[MaxEvaporatingBeads];
        private int evapCount;
        private float evapStart;
        private bool evaporating;

        public ThreadView(int player, Transform parent, Material strokeMaterial, Shader beadShader)
        {
            this.player = player;
            live = new Stroke("Thread" + player, parent, strokeMaterial, player);
            ghost = new Stroke("ThreadGhost" + player, parent, strokeMaterial, player);
            beads = new QuadBatch("ThreadBeads" + player, parent, beadShader, QuadBatch.QueueDroplets, 10);
        }

        /// <summary>Evaporating beads alive in the last frame (contract 24 saved chased return).</summary>
        public int EvaporatingBeads => evaporating ? evapCount : 0;

        /// <summary>Visible radius at arc length s of a piece [pieceStart, pieceEnd] (contract 12.3 profile).</summary>
        public static float RadiusAt(double s, double pieceStart, double pieceEnd, bool neck, bool tipEnd, bool taperEnd)
        {
            float r = VisibleRadius;
            if (neck && s < NeckLength)
            {
                float x = 1f - (float)(s / NeckLength);
                r *= 1f + (NeckWiden - 1f) * Smooth(x);
            }
            float toEnd = (float)(pieceEnd - s);
            if (tipEnd && toEnd < TipThinLength)
            {
                r *= Mathf.Lerp(TipThinFactor, 1f, Smooth(Mathf.Clamp01(toEnd / TipThinLength)));
            }
            if (taperEnd && toEnd < TaperLength)
            {
                // Pinched: narrows slowly at first, then fast toward the end.
                float x = Mathf.Clamp01(toEnd / TaperLength);
                r *= Mathf.Lerp(TaperEndFactor, 1f, Mathf.Pow(x, 0.55f));
            }
            return r;
        }

        public void Reset()
        {
            ghostActive = false;
            evaporating = false;
            builder.Begin();
            live.Hide();
            ghost.Hide();
            beads.Hide();
        }

        public void Hide()
        {
            live.Hide();
            ghost.Hide();
            beads.Hide();
        }

        public void Destroy()
        {
            live.Destroy();
            ghost.Destroy();
            beads.Destroy();
        }

        public void OnExit(SimEvent e)
        {
            // The live stroke is rebuilt from the new trail in the next LateUpdate.
        }

        public void OnReturn(SimEvent e, float now, Simulation sim)
        {
            if (e.Chased)
            {
                StartEvaporation(now);
                return;
            }
            if (!StartGhost(now)) return;
            int[] cells = e.Cells;
            if (cells == null || cells.Length == 0 || sim == null)
            {
                ghostSynced = false;
                ghostFade = EmptyReturnFade;
                return;
            }
            // The farthest captured cell from the return point: the fill wave reaches it after FillDuration.
            OwnerGrid g = sim.Grid;
            int size = g.Size;
            double cs = g.CellSize, org = g.Origin, best = 0.0;
            for (int k = 0; k < cells.Length; k++)
            {
                int c = cells[k];
                double dx = org + (c % size + 0.5) * cs - e.Point.X;
                double dy = org + (c / size + 0.5) * cs - e.Point.Y;
                double d2 = dx * dx + dy * dy;
                if (d2 > best) best = d2;
            }
            ghostSynced = true;
            ghostFillDuration = TerritoryField.CurrentFillDuration;
            ghostReach = Math.Sqrt(best);
            ghostOrigin = new Vector2((float)e.Point.X, (float)e.Point.Y);
            ghostSimStart = e.Time;
        }

        public void OnEliminated(float now)
        {
            if (!StartGhost(now)) return;
            ghostSynced = false;
            ghostFade = DeathFade;
        }

        public void Tick(ActorContext ctx)
        {
            UpdateGhost(ctx);
            UpdateEvaporation(ctx);
            Simulation sim = ctx.Sim;
            if (player >= sim.Players.Count)
            {
                live.Hide();
                return;
            }
            PlayerState p = sim.Players[player];
            Trail trail = p.Trail;
            if (!p.Alive || p.Home || trail.Count < 2)
            {
                live.Hide();
                return;
            }
            Vector2 tip = ctx.Session.RenderPos(player);
            BuildPieces(builder, p, tip, ctx.Session.RenderSparkS(player));
            if (builder.Vertices.Count == 0)
            {
                live.Hide();
                return;
            }
            live.Show(builder, 1f);
        }

        /// <summary>
        /// Fills builder with the thread of a trailing player whose interpolated head is at tip: one piece [0, L_render]
        /// without a spark; with a spark, [0, s_cut - 0.25] (neck, pinched taper) and [renderSparkS, L_render] (tip end).
        /// Returns the number of pieces.
        /// </summary>
        public static int BuildPieces(StrokeBuilder builder, PlayerState p, Vector2 tip, double renderSparkS)
        {
            builder.Begin();
            Trail trail = p.Trail;
            if (trail.Count < 2) return 0;
            double lr = TrailCurve.RenderLength(p, tip);
            if (p.Spark == null)
            {
                AddPiece(builder, trail, 0.0, lr, true, true, false, tip);
            }
            else
            {
                double upEnd = Math.Min(p.Spark.SCut - CutGap, lr);
                if (upEnd > MinPiece) AddPiece(builder, trail, 0.0, upEnd, true, false, true, tip);
                double sr = double.IsNaN(renderSparkS) ? p.Spark.S : renderSparkS;
                if (lr - sr > MinPiece) AddPiece(builder, trail, Math.Max(0.0, sr), lr, false, true, false, tip);
            }
            return builder.PieceCount;
        }

        private static void AddPiece(StrokeBuilder builder, Trail trail, double sa, double sb, bool neck, bool tipEnd,
                                     bool taperEnd, Vector2 tip)
        {
            double span = sb - sa;
            if (span < MinPiece) return;
            IReadOnlyList<Vec2d> points = trail.Points;
            IReadOnlyList<double> arc = trail.Arc;
            int n = Math.Max(1, (int)Math.Ceiling(span / SampleSpacing));
            int segment = -1;
            builder.BeginPiece();
            for (int j = 0; j <= n; j++)
            {
                double s = j == n ? sb : sa + span * j / n;
                Vector2 c = j == n && tipEnd ? tip : TrailCurve.Evaluate(points, arc, s, ref segment);
                builder.AddSample(c, RadiusAt(s, sa, sb, neck, tipEnd, taperEnd));
            }
            builder.EndPiece();
        }

        /// <summary>Copies the last live thread into the ghost samples. False when no thread was on screen.</summary>
        private bool StartGhost(float now)
        {
            if (!live.Visible || builder.Centers.Count == 0) return false;
            ghostCenters.Clear();
            ghostRadii.Clear();
            ghostStarts.Clear();
            ghostCenters.AddRange(builder.Centers);
            ghostRadii.AddRange(builder.Radii);
            ghostStarts.AddRange(builder.PieceStarts);
            live.Hide();
            ghostStart = now;
            ghostTailStart = -1f;
            ghostActive = true;
            ghostSynced = false;
            ghostFade = EmptyReturnFade;
            RebuildGhost(false, Vector2.zero, 0.0);
            ghost.Show(ghostBuilder, 1f);
            return true;
        }

        private void UpdateGhost(ActorContext ctx)
        {
            if (!ghostActive) return;
            float t = ctx.Time - ghostStart;
            if (t >= GhostTimeout)
            {
                EndGhost();
                return;
            }
            if (!ghostSynced)
            {
                if (t >= ghostFade)
                {
                    EndGhost();
                    return;
                }
                ghost.SetVisible(1f - t / ghostFade);
                return;
            }
            // The fill front on the sim render clock (the instant RenderPos shows), as TerritoryField does.
            Simulation sim = ctx.Sim;
            double renderTime = sim.Time - (1.0 - ctx.Session.Alpha) * sim.Config.Dt;
            double front = ghostReach * (renderTime - ghostSimStart) / ghostFillDuration;
            if (front >= ghostReach + DissolveAhead && ghostTailStart < 0f) ghostTailStart = ctx.Time;
            float tail = 1f;
            if (ghostTailStart >= 0f)
            {
                tail = 1f - (ctx.Time - ghostTailStart) / GhostTailFade;
                if (tail <= 0f)
                {
                    EndGhost();
                    return;
                }
            }
            RebuildGhost(true, ghostOrigin, front);
            if (ghostBuilder.Vertices.Count == 0)
            {
                EndGhost();
                return;
            }
            ghost.Show(ghostBuilder, tail);
        }

        /// <summary>Rebuilds the ghost mesh; when dissolving, samples behind the fill front get amplitude 0.</summary>
        private void RebuildGhost(bool dissolve, Vector2 origin, double front)
        {
            ghostBuilder.Begin();
            int pieces = ghostStarts.Count;
            for (int k = 0; k < pieces; k++)
            {
                int start = ghostStarts[k];
                int end = k + 1 < pieces ? ghostStarts[k + 1] : ghostCenters.Count;
                ghostBuilder.BeginPiece();
                for (int j = start; j < end; j++)
                {
                    float m = 1f;
                    if (dissolve)
                    {
                        float d = Vector2.Distance(ghostCenters[j], origin);
                        m = Smooth(Mathf.InverseLerp((float)front - DissolveBehind, (float)front + DissolveAhead, d));
                    }
                    ghostBuilder.AddSample(ghostCenters[j], ghostRadii[j], m);
                }
                ghostBuilder.EndPiece();
            }
        }

        private void EndGhost()
        {
            ghostActive = false;
            ghost.Hide();
        }

        /// <summary>Contract 24: the last thread breaks into beads every EvaporateSpacing that shrink, drift and fade.</summary>
        private void StartEvaporation(float now)
        {
            if (!StartGhost(now)) return;
            ghostSynced = false;
            ghostFade = EvaporateFieldFade;
            evapCount = 0;
            int pieces = ghostStarts.Count;
            for (int k = 0; k < pieces && evapCount < MaxEvaporatingBeads; k++)
            {
                int start = ghostStarts[k];
                int end = k + 1 < pieces ? ghostStarts[k + 1] : ghostCenters.Count;
                float carry = EvaporateSpacing * 0.5f;
                for (int j = start + 1; j < end && evapCount < MaxEvaporatingBeads; j++)
                {
                    Vector2 a = ghostCenters[j - 1], b = ghostCenters[j];
                    float len = Vector2.Distance(a, b);
                    while (carry <= len && evapCount < MaxEvaporatingBeads)
                    {
                        float f = len > 1e-6f ? carry / len : 0f;
                        int n = evapCount;
                        float h0 = RetractionView.Hash01(n * 3 + player * 977 + 11);
                        float h1 = RetractionView.Hash01(n * 3 + player * 977 + 12);
                        Vector2 tangent = len > 1e-6f ? (b - a) / len : Vector2.right;
                        var normal = new Vector2(-tangent.y, tangent.x);
                        evapPos[n] = Vector2.Lerp(a, b, f);
                        evapRadius[n] = Mathf.Lerp(ghostRadii[j - 1], ghostRadii[j], f) * EvaporateRadiusFactor * Mathf.Lerp(0.85f, 1.1f, h1);
                        evapDelay[n] = EvaporateMaxDelay * h0;
                        evapDrift[n] = normal * (0.14f * (h1 - 0.5f)) + new Vector2(0f, 0.07f);
                        evapCount++;
                        carry += EvaporateSpacing;
                    }
                    carry -= len;
                }
            }
            evapStart = now;
            evaporating = evapCount > 0;
        }

        private void UpdateEvaporation(ActorContext ctx)
        {
            if (!evaporating) return;
            float t = ctx.Time - evapStart;
            if (t >= EvaporateSeconds)
            {
                evaporating = false;
                beads.Hide();
                return;
            }
            Color color = ctx.LinearColor(player);
            beads.Begin();
            for (int k = 0; k < evapCount; k++)
            {
                float life = Mathf.Max(0.05f, EvaporateSeconds - evapDelay[k]);
                float u = Mathf.Clamp01((t - evapDelay[k]) / life);
                float r = evapRadius[k] * Mathf.Pow(1f - u, 0.7f);
                if (r < 0.004f) continue;
                float move = 1f - (1f - u) * (1f - u);
                float opacity = u < 0.6f ? 1f : (1f - u) / 0.4f;
                beads.AddBead(evapPos[k] + evapDrift[k] * move, r, Vector2.right, 1f, color, opacity, 0.28f, ctx.Lobes, 0.45f);
            }
            beads.End();
        }

        private static float Smooth(float x)
        {
            x = Mathf.Clamp01(x);
            return x * x * (3f - 2f * x);
        }

        /// <summary>One FieldStroke renderer (layer 31) with its own dynamic mesh and property block.</summary>
        private sealed class Stroke
        {
            private readonly GameObject go;
            private readonly MeshFilter filter;
            private readonly MeshRenderer renderer;
            private readonly MaterialPropertyBlock block = new MaterialPropertyBlock();
            private readonly Vector4 channel;
            private Mesh mesh;
            private float amplitude = -1f;

            public Stroke(string name, Transform parent, Material material, int player)
            {
                go = new GameObject(name) { layer = LiquidLayers.Field };
                go.transform.SetParent(parent, false);
                go.transform.localPosition = Vector3.zero;
                go.transform.localRotation = Quaternion.identity;
                go.transform.localScale = Vector3.one;
                mesh = NewMesh(name);
                filter = go.AddComponent<MeshFilter>();
                filter.sharedMesh = mesh;
                renderer = go.AddComponent<MeshRenderer>();
                renderer.shadowCastingMode = ShadowCastingMode.Off;
                renderer.receiveShadows = false;
                renderer.lightProbeUsage = LightProbeUsage.Off;
                renderer.reflectionProbeUsage = ReflectionProbeUsage.Off;
                renderer.motionVectorGenerationMode = MotionVectorGenerationMode.ForceNoMotion;
                renderer.allowOcclusionWhenDynamic = false;
                renderer.sharedMaterial = material;
                renderer.enabled = false;
                channel = LiquidLayers.ChannelMask(player);
            }

            public bool Visible { get; private set; }

            public void Show(StrokeBuilder b, float amplitudeValue)
            {
                if (renderer.sharedMaterial == null)
                {
                    Hide();
                    return;
                }
                b.Upload(mesh);
                SetVisible(amplitudeValue);
            }

            public void SetVisible(float amplitudeValue)
            {
                if (renderer.sharedMaterial == null || mesh.vertexCount == 0 || !(amplitudeValue > 0.001f))
                {
                    Hide();
                    return;
                }
                if (!Mathf.Approximately(amplitude, amplitudeValue))
                {
                    amplitude = amplitudeValue;
                    block.SetVector(ChannelId, channel);
                    block.SetFloat(AmplitudeId, amplitude);
                    renderer.SetPropertyBlock(block);
                }
                if (!renderer.enabled) renderer.enabled = true;
                Visible = true;
            }

            public void Hide()
            {
                if (renderer != null && renderer.enabled) renderer.enabled = false;
                Visible = false;
            }


            public void Destroy()
            {
                if (mesh != null) UnityEngine.Object.Destroy(mesh);
                if (go != null) UnityEngine.Object.Destroy(go);
            }

            private static Mesh NewMesh(string name)
            {
                var m = new Mesh { name = name, indexFormat = IndexFormat.UInt32 };
                m.MarkDynamic();
                return m;
            }
        }
    }
}
