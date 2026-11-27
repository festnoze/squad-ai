// Owned by BI since wave B-2 (written by B4). Contract 15.3: the in-round HUD, mirroring docs/reference_gouttes.png ("28 %  00:37  24 %"): human area in
// the human color on the left, countdown in light text at the center, best rival area in that rival's color on the right.
// Area labels show one decimal below 10 %. The human label counts up over FillDuration in sync with the fill and pops; each
// capture of at least 0.1 % raises a "+2,1 %" text from the return point. The timer pulses in the last 10 s. Round "II"
// pause button (96 px, 60 % opacity) under the area label. The rival label is a Button toggling a 4-row leaderboard.
// Toasts (1.6 s, one at a time, queue of 2, entries older than 3 s dropped, only toasts about the human while the human
// has a spark) and a pulsing danger vignette while the human is chased.
// Contract 25.2: the timer and the highlights use BiomeTheme.Current.UiAccent (the UI light in Liquide), the player colors
// come from the biome (Palette.ColorOf) and the count-up lasts the biome's FillDuration. Contract 24: a saved chased
// return shows the saved line and no '+x %' (its Cells are empty).
// Wave C: toasts never shrink below 0.85; with the leaderboard open a toast that would overlap it moves below it (and
// below a visible tutorial bubble), and a line too long for the screen wraps to two lines (rules-02, ToastLayout). The
// rival chevron is more opaque, a bit bigger and outlined in navy so it reads over bright beds (layout unchanged).
using System;
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.UI;

namespace PainterIO.Runtime
{
    public sealed class Hud : UiScreen
    {
        /// <summary>Duration of the fill wave (contract 12.3, B1's LiquidRenderer.FillDuration): the human's label counts up over it.</summary>
        public const float FillDuration = LiquidRenderer.FillDuration;
        public const float PopSeconds = 0.2f;
        public const float PopScale = 1.15f;
        public const float GainSeconds = 0.8f;
        public const double GainMinPercent = 0.1;
        public const float ToastSeconds = 1.6f;
        public const float ToastMaxAge = 3f;
        public const int ToastQueueSize = 2;
        public const float PauseButtonSize = 96f;
        public const float PauseButtonOpacity = 0.6f;
        public const float LastSeconds = 10f;
        public const int AreaFontSize = 70;
        /// <summary>Top bar labels: center below the safe top and rect height.</summary>
        public const float TopBarY = 84f;
        public const float TopBarHeight = 110f;
        public const float BoardWidth = 440f;
        public const float BoardRight = 28f;
        /// <summary>Distance from the safe area's top to the leaderboard's top edge.</summary>
        public const float BoardTop = 158f;
        public const float BoardRowHeight = 64f;
        public const float BoardPadding = 28f;
        /// <summary>Width of the danger vignette's glowing edge, in reference pixels.</summary>
        public const float VignetteBand = 84f;
        /// <summary>Toast pill: center height below the safe top, height, and the two-line height.</summary>
        public const float ToastY = -330f;
        public const float ToastHeight = 96f;
        public const float ToastWrapHeight = 150f;
        /// <summary>rules-02: a toast is never scaled below this.</summary>
        public const float MinToastScale = 0.85f;
        /// <summary>A single-line toast fits in the safe width minus this; a two-line toast is the safe width minus ToastWrapMargin.</summary>
        public const float ToastSideMargin = 40f;
        public const float ToastWrapMargin = 64f;
        /// <summary>Gap kept between a toast and the leaderboard (or the tutorial bubble) it moved below.</summary>
        public const float ToastGap = 24f;
        /// <summary>Rival chevron: opacity and size (visuals-hud-contrast-over-bright-beds).</summary>
        public const float ChevronAlpha = 0.9f;
        public static readonly Vector2 ChevronSize = new Vector2(28f, 18f);

        /// <summary>Height of the expanded leaderboard.</summary>
        public static float BoardHeight => Tuning.PlayerCount * BoardRowHeight + BoardPadding;

        private static readonly Color TimerDanger = new Color32(0xFF, 0x5E, 0x52, 0xFF);
        private static readonly Color VignetteRed = new Color32(0xFF, 0x30, 0x3C, 0xFF);

        private readonly Text humanLabel, timerLabel, rivalLabel;
        private readonly RectTransform humanRect, timerRect;
        private readonly Image rivalChevron;
        private readonly CanvasGroup pauseGroup;
        private readonly CanvasGroup boardGroup;
        private readonly Row[] rows = new Row[Tuning.PlayerCount];
        private readonly CanvasGroup toastGroup;
        private readonly RectTransform toastRect;
        private readonly Text toastText;
        private float toastNaturalWidth = 300f;
        private bool toastWrapped;
        private readonly Gain[] gains = new Gain[4];
        private readonly Image vignette;

        private GameSession session;
        private double areaShown, areaFrom, areaTo;
        private float areaT = 1f, popT = 1f;
        private float countUpSeconds = FillDuration;
        private double lastRenderTime = double.NaN;
        private int bestRival = 1;
        private bool boardOpen;
        private float boardAlpha, vignetteAlpha, vignettePhase;

        // Toasts.
        private readonly List<Toast> queue = new List<Toast>();
        private Toast current;
        private float toastT;

        // Text caches (avoid rebuilding strings every frame).
        private long humanKey = long.MinValue, rivalKey = long.MinValue, timerKey = long.MinValue;
        private readonly long[] rowKeys = new long[Tuning.PlayerCount];

        private sealed class Row
        {
            public RectTransform Rect;
            public Image Highlight, Dot;
            public Text Name, Area;
        }

        private sealed class Gain
        {
            public Text Text;
            public Vector2 World;
            public float T = 1f;
            public bool Active;
        }

        private sealed class Toast
        {
            public string Text;
            public bool AboutHuman;
            public float Time;
        }

        public Hud(UiRoot root) : base(root, "Hud", UiRoot.HudOrder)
        {
            // Danger vignette under everything, over the whole screen (outside the safe area).
            vignette = UiKit.Img(CanvasRect, "DangerVignette", UiKit.VignetteSprite, new Color(1f, 1f, 1f, 0f));
            vignette.type = Image.Type.Sliced;
            vignette.fillCenter = false;
            vignette.pixelsPerUnitMultiplier = UiKit.VignetteBorderPixels / VignetteBand;
            UiKit.Stretch(vignette.rectTransform);
            // The top band mostly sits above the screen so the top bar stays readable.
            vignette.rectTransform.offsetMax = new Vector2(0f, VignetteBand * 0.55f);
            vignette.rectTransform.SetAsFirstSibling();
            vignette.enabled = false;

            // Top bar.
            humanLabel = UiKit.Label(Safe, "HumanArea", AreaFontSize, Palette.ColorOf(0), TextAnchor.MiddleLeft);
            humanRect = humanLabel.rectTransform;
            humanRect.anchorMin = humanRect.anchorMax = UiKit.TopLeft;
            humanRect.pivot = new Vector2(0f, 0.5f);
            humanRect.sizeDelta = new Vector2(400f, 110f);
            humanRect.anchoredPosition = new Vector2(52f, -84f);

            timerLabel = UiKit.Label(Safe, "Countdown", AreaFontSize, UiKit.Light, TextAnchor.MiddleCenter);
            timerRect = timerLabel.rectTransform;
            UiKit.Place(timerRect, UiKit.TopCenter, new Vector2(0f, -TopBarY), new Vector2(360f, TopBarHeight));

            Button rivalButton = UiKit.Btn(Safe, "RivalArea", new Vector2(340f, 130f), new Color(1f, 1f, 1f, 0f), 30f, 0,
                                           UiKit.Light, ToggleBoard, out _);
            RectTransform rb = (RectTransform)rivalButton.transform;
            rb.anchorMin = rb.anchorMax = UiKit.TopRight;
            rb.pivot = new Vector2(1f, 0.5f);
            rb.anchoredPosition = new Vector2(-30f, -84f);
            rivalLabel = UiKit.Label(rb, "Label", AreaFontSize, Palette.ColorOf(1), TextAnchor.MiddleRight);
            UiKit.Stretch(rivalLabel.rectTransform);
            rivalLabel.rectTransform.offsetMax = new Vector2(-22f, 0f);
            rivalChevron = UiKit.Img(rb, "Chevron", UiKit.TriangleSprite, UiKit.WithAlpha(UiKit.Light, ChevronAlpha));
            UiKit.Place(rivalChevron.rectTransform, new Vector2(1f, 0f), new Vector2(-60f, -2f), ChevronSize);
            rivalChevron.rectTransform.localEulerAngles = new Vector3(0f, 0f, 180f);
            // A navy outline keeps the chevron readable over gold, neon-yellow and saffron beds.
            Outline chevronOutline = rivalChevron.gameObject.AddComponent<Outline>();
            chevronOutline.effectColor = UiKit.WithAlpha(UiKit.Navy, 0.8f);
            chevronOutline.effectDistance = new Vector2(2f, -2f);
            chevronOutline.useGraphicAlpha = true;

            // Pause button: round, "II", 96 px, 60 % opacity, under the area label.
            Button pause = UiKit.Btn(Safe, "PauseButton", new Vector2(PauseButtonSize, PauseButtonSize), UiKit.WithAlpha(UiKit.Navy, 0.85f),
                                     PauseButtonSize * 0.5f, 0, UiKit.Light, OnPauseClicked, out _);
            RectTransform pr = (RectTransform)pause.transform;
            UiKit.Place(pr, UiKit.TopLeft, new Vector2(52f + PauseButtonSize * 0.5f, -84f - 55f - 26f - PauseButtonSize * 0.5f),
                        new Vector2(PauseButtonSize, PauseButtonSize));
            ((Image)pause.targetGraphic).sprite = UiKit.CircleSprite;
            ((Image)pause.targetGraphic).type = Image.Type.Simple;
            for (int k = 0; k < 2; k++)
            {
                Image bar = UiKit.Rounded(pr, "Bar" + k, UiKit.Light, 6f);
                UiKit.Place(bar.rectTransform, UiKit.Center, new Vector2(k == 0 ? -11f : 11f, 0f), new Vector2(13f, 40f));
            }
            pauseGroup = pause.gameObject.AddComponent<CanvasGroup>();
            pauseGroup.alpha = PauseButtonOpacity;

            // Leaderboard (collapsed by default).
            RectTransform board = UiKit.Rect("Leaderboard", Safe);
            board.anchorMin = board.anchorMax = UiKit.TopRight;
            board.pivot = new Vector2(1f, 1f);
            board.sizeDelta = new Vector2(BoardWidth, rows.Length * BoardRowHeight + BoardPadding);
            board.anchoredPosition = new Vector2(-BoardRight, -BoardTop);
            boardGroup = board.gameObject.AddComponent<CanvasGroup>();
            boardGroup.alpha = 0f;
            boardGroup.blocksRaycasts = false;
            boardGroup.interactable = false;
            Image boardBg = UiKit.Rounded(board, "Background", UiKit.WithAlpha(UiKit.Navy, 0.82f), 34f);
            UiKit.Stretch(boardBg.rectTransform);
            for (int i = 0; i < rows.Length; i++)
            {
                var r = new Row();
                r.Rect = UiKit.Rect("Row" + i, board);
                r.Rect.anchorMin = r.Rect.anchorMax = new Vector2(0.5f, 1f);
                r.Rect.pivot = new Vector2(0.5f, 0.5f);
                r.Rect.sizeDelta = new Vector2(412f, 58f);
                r.Rect.anchoredPosition = new Vector2(0f, -14f - 32f - i * 64f);
                r.Highlight = UiKit.Rounded(r.Rect, "Highlight", UiKit.WithAlpha(UiKit.Light, 0.10f), 29f);
                UiKit.Stretch(r.Highlight.rectTransform);
                r.Dot = UiKit.Img(r.Rect, "Dot", UiKit.CircleSprite, Palette.ColorOf(i));
                UiKit.Place(r.Dot.rectTransform, new Vector2(0f, 0.5f), new Vector2(34f, 0f), new Vector2(30f, 30f));
                r.Name = UiKit.Label(r.Rect, "Name", 38, UiKit.Light, TextAnchor.MiddleLeft);
                UiKit.Stretch(r.Name.rectTransform);
                r.Name.rectTransform.offsetMin = new Vector2(64f, 0f);
                r.Area = UiKit.Label(r.Rect, "Area", 38, UiKit.Light, TextAnchor.MiddleRight);
                UiKit.Stretch(r.Area.rectTransform);
                r.Area.rectTransform.offsetMax = new Vector2(-20f, 0f);
                rows[i] = r;
            }

            // Toast pill (center-top).
            toastRect = UiKit.Rect("Toast", Safe);
            UiKit.Place(toastRect, UiKit.TopCenter, new Vector2(0f, ToastY), new Vector2(600f, ToastHeight));
            toastGroup = toastRect.gameObject.AddComponent<CanvasGroup>();
            toastGroup.alpha = 0f;
            toastGroup.blocksRaycasts = false;
            toastGroup.interactable = false;
            Image toastBg = UiKit.Rounded(toastRect, "Background", UiKit.WithAlpha(UiKit.Navy, 0.86f), 48f);
            UiKit.Stretch(toastBg.rectTransform);
            toastText = UiKit.Label(toastRect, "Text", 44, UiKit.Light, TextAnchor.MiddleCenter, false);
            UiKit.Stretch(toastText.rectTransform);

            // "+x %" capture gains, pooled; their Text is disabled while idle.
            for (int i = 0; i < gains.Length; i++)
            {
                Text t = UiKit.Label(CanvasRect, "Gain" + i, 62, Palette.ColorOf(0), TextAnchor.MiddleCenter);
                UiKit.AddOutline(t.gameObject, 3f, 0.9f);   // readable over the human's own puddle
                UiKit.Place(t.rectTransform, UiKit.Center, Vector2.zero, new Vector2(320f, 90f));
                t.enabled = false;
                gains[i] = new Gain { Text = t };
            }
        }

        /// <summary>True while the leaderboard is expanded.</summary>
        public bool LeaderboardOpen => boardOpen;

        /// <summary>The text of the toast on screen, or null.</summary>
        public string CurrentToast => current != null ? current.Text : null;

        public void Bind(GameSession s)
        {
            session = s;
            queue.Clear();
            current = null;
            toastGroup.alpha = 0f;
            for (int i = 0; i < gains.Length; i++)
            {
                gains[i].Active = false;
                gains[i].Text.enabled = false;
            }
            boardOpen = UiRoot.DemoShows("board");
            bestRival = 1;
            popT = 1f;
            areaT = 1f;
            areaShown = areaFrom = areaTo = HumanArea(s);
            lastRenderTime = double.NaN;
            humanKey = rivalKey = timerKey = long.MinValue;
            for (int i = 0; i < rowKeys.Length; i++) rowKeys[i] = long.MinValue;
        }

        public override void Relabel()
        {
            humanKey = rivalKey = timerKey = long.MinValue;
            for (int i = 0; i < rowKeys.Length; i++) rowKeys[i] = long.MinValue;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Events (forwarded by UiRoot after each Step).

        public void OnSimEvent(GameSession s, SimEvent e, bool lassoBubbleShown)
        {
            if (s != session || s.IsAttract) return;
            int h = s.HumanIndex;
            if (h < 0) return;
            Simulation sim = s.Sim;
            switch (e.Type)
            {
                case SimEventType.Return:
                    if (e.Player != h) break;
                    if (e.Cells != null && e.Cells.Length > 0)
                    {
                        popT = 0f;
                        int arena = sim.Grid.ArenaCellCount;
                        double gain = arena > 0 ? 100.0 * e.Cells.Length / arena : 0.0;
                        if (gain >= GainMinPercent) SpawnGain(gain, e.Point);
                    }
                    if (e.Chased && !s.IsFlickerReturn(e)) Enqueue(SavedLine(e.Margin), true);
                    break;
                case SimEventType.Cut:
                    if (e.Other == h && e.Player != h) Enqueue(Strings.Format("toast.cut", Strings.PlayerName(e.Player, h)), true);
                    break;
                case SimEventType.Eliminated:
                    if (e.Player == h) break;
                    if (e.Cause == EliminationCause.Spark && e.Other == h)
                        Enqueue(Strings.Format("toast.spark_kill", Strings.PlayerName(e.Player, h)), true);
                    else Enqueue(Strings.Format("toast.eliminated", Strings.PlayerName(e.Player, h)), e.Other == h);
                    break;
                case SimEventType.RingPicked:
                    if (e.Player == h && !lassoBubbleShown) Enqueue(Strings.Get("toast.lasso_ready"), true);
                    break;
            }
        }

        /// <summary>
        /// The saved line of 15.5 as changed by contract 24 (v1.4): "Rentré 0,4 s avant l'étincelle : boucle perdue.", or
        /// "Sauvé de justesse : boucle perdue." below 0.05 s.
        /// </summary>
        public static string SavedLine(double margin)
        {
            if (double.IsNaN(margin) || margin < 0.05) return Strings.Get("results.saved_close");
            return Strings.Format("results.saved", Strings.Decimal(margin, 1));
        }

        /// <summary>Queues a toast (15.3 rules). Public for tests and for other packages that need a toast.</summary>
        public void Enqueue(string text, bool aboutHuman)
        {
            if (string.IsNullOrEmpty(text)) return;
            if (HumanChased() && !aboutHuman) return;
            var t = new Toast { Text = text, AboutHuman = aboutHuman, Time = Time.unscaledTime };
            if (current == null)
            {
                ShowToast(t);
                return;
            }
            queue.Add(t);
            while (queue.Count > ToastQueueSize) queue.RemoveAt(0);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Frame.

        public override void Tick(float dt)
        {
            GameSession s = session;
            if (s == null || s != Session || s.IsAttract) return;
            Simulation sim = s.Sim;
            int h = s.HumanIndex;
            bool hasHuman = h >= 0 && h < sim.Players.Count;
            GameDirector d = Director;

            // The count-up and the pop run on the sim render clock (Time - (1 - Alpha) Dt), the clock of B1's fill wave, so
            // they slow down with slow motion and stop while paused, in sync with the fill.
            double renderTime = sim.Time - (1.0 - s.Alpha) * sim.Config.Dt;
            float simDt = double.IsNaN(lastRenderTime) ? 0f : Mathf.Clamp((float)(renderTime - lastRenderTime), 0f, 0.1f);
            lastRenderTime = renderTime;

            // Human area with the count-up and the pop.
            if (hasHuman)
            {
                PlayerState hp = sim.Players[h];
                if (hp.Alive)
                {
                    double target = sim.AreaPercent(h);
                    if (Math.Abs(target - areaTo) > 1e-9)
                    {
                        areaFrom = areaShown;
                        areaTo = target;
                        areaT = 0f;
                        countUpSeconds = TerritoryField.CurrentFillDuration;
                    }
                }
                areaT = Mathf.Min(1f, areaT + simDt / Mathf.Max(0.05f, countUpSeconds));
                float k = 1f - (1f - areaT) * (1f - areaT);
                areaShown = areaFrom + (areaTo - areaFrom) * k;
                humanLabel.color = Palette.ColorOf(h);
                long key = (long)Math.Round(areaShown * 10.0) * 4 + Strings.Language;
                if (key != humanKey)
                {
                    humanKey = key;
                    humanLabel.text = Strings.Area(areaShown);
                }
            }
            popT = Mathf.Min(1f, popT + simDt / PopSeconds);
            float pop = 1f + (PopScale - 1f) * Mathf.Sin(Mathf.PI * popT);
            humanRect.localScale = new Vector3(pop, pop, 1f);

            // Countdown (full round time while the round waits for the human).
            double remaining = Math.Max(0.0, sim.Config.RoundDuration - sim.Time);
            long tkey = (long)Math.Ceiling(remaining - 1e-6);
            if (tkey != timerKey)
            {
                timerKey = tkey;
                timerLabel.text = Strings.Clock(remaining);
            }
            Color accent = BiomeTheme.Current.UiAccent;
            bool running = !sim.Ended && !s.AwaitingStart && remaining > 0.0 && remaining <= LastSeconds;
            if (running)
            {
                float frac = (float)(remaining - Math.Floor(remaining));
                float p = frac * frac * frac * frac;
                timerRect.localScale = Vector3.one * (1f + 0.22f * p);
                timerLabel.color = Color.Lerp(accent, TimerDanger, 0.35f + 0.65f * p);
            }
            else
            {
                timerRect.localScale = Vector3.one;
                timerLabel.color = remaining <= 0.0 ? TimerDanger : accent;
            }

            // Best rival.
            int best = BestRival(sim, h);
            if (best >= 0) bestRival = best;
            if (bestRival >= 0 && bestRival < sim.Players.Count)
            {
                rivalLabel.color = Palette.ColorOf(bestRival);
                double ra = sim.Players[bestRival].Alive ? sim.AreaPercent(bestRival) : 0.0;
                long rkey = ((long)Math.Round(ra * 10.0) * 8 + bestRival) * 4 + Strings.Language;
                if (rkey != rivalKey)
                {
                    rivalKey = rkey;
                    rivalLabel.text = Strings.Area(ra);
                }
            }

            // Leaderboard.
            boardAlpha = Mathf.MoveTowards(boardAlpha, boardOpen ? 1f : 0f, dt / 0.15f);
            boardGroup.alpha = boardAlpha;
            rivalChevron.rectTransform.localEulerAngles = new Vector3(0f, 0f, boardOpen ? 0f : 180f);
            rivalChevron.color = UiKit.WithAlpha(accent, ChevronAlpha);
            if (boardAlpha > 0f) UpdateBoard(sim, h);

            // Pause button.
            bool canPause = d != null && d.State == GameState.Playing && s.HumanAlive && !sim.Ended && !d.InResultsBeat && !d.IsPaused;
            pauseGroup.alpha = canPause ? PauseButtonOpacity : 0f;
            pauseGroup.blocksRaycasts = canPause;
            pauseGroup.interactable = canPause;

            TickToasts(dt);
            TickGains(dt);
            TickVignette(dt, s, sim, h);
        }

        private void UpdateBoard(Simulation sim, int h)
        {
            int n = Mathf.Min(sim.Players.Count, rows.Length);
            var order = new int[n];
            for (int i = 0; i < n; i++) order[i] = i;
            Array.Sort(order, (a, b) =>
            {
                PlayerState pa = sim.Players[a], pb = sim.Players[b];
                if (pa.Alive != pb.Alive) return pa.Alive ? -1 : 1;
                if (pa.Alive)
                {
                    int c = sim.Grid.CountOf(pb.Id).CompareTo(sim.Grid.CountOf(pa.Id));
                    if (c != 0) return c;
                }
                else
                {
                    int c = pb.EliminatedAt.CompareTo(pa.EliminatedAt);
                    if (c != 0) return c;
                }
                return a.CompareTo(b);
            });
            for (int r = 0; r < rows.Length; r++)
            {
                Row row = rows[r];
                bool used = r < n;
                row.Rect.gameObject.transform.localScale = used ? Vector3.one : Vector3.zero;
                if (!used) continue;
                int i = order[r];
                PlayerState p = sim.Players[i];
                int rank = sim.RankOf(i);
                double area = p.Alive ? sim.AreaPercent(i) : 0.0;
                long key = (((long)Math.Round(area * 10.0) * 8 + i) * 8 + rank) * 8 + (p.Alive ? 1 : 0) * 4 + Strings.Language;
                row.Dot.color = Palette.ColorOf(i);
                row.Highlight.enabled = i == h;
                row.Highlight.color = UiKit.WithAlpha(BiomeTheme.Current.UiAccent, 0.10f);
                row.Area.color = p.Alive ? Palette.ColorOf(i) : UiKit.WithAlpha(UiKit.Light, 0.45f);
                row.Name.color = p.Alive ? UiKit.Light : UiKit.WithAlpha(UiKit.Light, 0.45f);
                if (key == rowKeys[r]) continue;
                rowKeys[r] = key;
                row.Name.text = rank.ToString(System.Globalization.CultureInfo.InvariantCulture) + "   " + Strings.PlayerName(i, h);
                row.Area.text = p.Alive ? Strings.Area(area) : Strings.Get("hud.out");
            }
        }

        private void TickToasts(float dt)
        {
            bool chased = HumanChased();
            if (current != null)
            {
                toastT += dt;
                if (chased && !current.AboutHuman && toastT < ToastSeconds - 0.15f) toastT = ToastSeconds - 0.15f;
                if (toastT >= ToastSeconds) current = null;
            }
            if (current == null)
            {
                float now = Time.unscaledTime;
                while (queue.Count > 0)
                {
                    Toast t = queue[0];
                    queue.RemoveAt(0);
                    if (now - t.Time > ToastMaxAge) continue;
                    if (chased && !t.AboutHuman) continue;
                    ShowToast(t);
                    break;
                }
            }
            float a = 0f;
            if (current != null)
            {
                a = Mathf.Min(1f, toastT / 0.15f) * Mathf.Clamp01((ToastSeconds - toastT) / 0.2f);
                float avoidTop = float.NaN, avoidBottom = float.NaN;
                TutorialBubbleBand(ref avoidTop, ref avoidBottom);
                ToastPlacement p = ToastLayout(Safe.rect.width, toastNaturalWidth, boardOpen, avoidTop, avoidBottom);
                SetToastWrap(p.Wrap);
                if (toastRect.sizeDelta != p.Size) toastRect.sizeDelta = p.Size;
                toastRect.localScale = new Vector3(p.Scale, p.Scale, 1f);
                toastRect.anchoredPosition = p.Position + new Vector2(0f, 14f * (1f - Mathf.Min(1f, toastT / 0.15f)));
            }
            toastGroup.alpha = a;
        }

        private void ShowToast(Toast t)
        {
            current = t;
            toastT = 0f;
            SetToastWrap(false);   // single-line sizing first: the natural width decides the layout
            toastText.text = t.Text;
            toastNaturalWidth = Mathf.Max(toastText.preferredWidth + 84f, 300f);
            toastRect.sizeDelta = new Vector2(toastNaturalWidth, ToastHeight);
            UiRoot.RaiseToastShown(t.Text);
        }

        private void SetToastWrap(bool wrap)
        {
            if (wrap == toastWrapped) return;
            toastWrapped = wrap;
            toastText.horizontalOverflow = wrap ? HorizontalWrapMode.Wrap : HorizontalWrapMode.Overflow;
            toastText.rectTransform.offsetMin = wrap ? new Vector2(36f, 10f) : Vector2.zero;
            toastText.rectTransform.offsetMax = wrap ? new Vector2(-36f, -10f) : Vector2.zero;
        }

        /// <summary>
        /// The visible tutorial bubble's vertical band in the toast's coordinates (y up, 0 at the safe top), if any. Read
        /// only, from TutorialOverlay.BubbleRect and BubbleAlpha (TopCenter anchored like the toast, in a safe area of the
        /// same size).
        /// </summary>
        private void TutorialBubbleBand(ref float top, ref float bottom)
        {
            TutorialOverlay overlay = Root != null ? Root.Tutorial : null;
            if (overlay == null || !overlay.Visible) return;
            RectTransform bubble = overlay.BubbleRect;
            if (bubble == null || overlay.BubbleAlpha < 0.02f) return;
            float half = bubble.sizeDelta.y * 0.5f;
            top = bubble.anchoredPosition.y + half;
            bottom = bubble.anchoredPosition.y - half - 10f;   // its drop shadow
        }

        /// <summary>Where a toast goes (rules-02): scale, TopCenter anchored position, unscaled size and the two-line switch.</summary>
        internal struct ToastPlacement
        {
            public float Scale;
            public Vector2 Position;
            public Vector2 Size;
            public bool Wrap;

            /// <summary>The scaled rectangle in safe-area coordinates (x from the center, y up, 0 at the safe top).</summary>
            public Rect Bounds
            {
                get
                {
                    float w = Size.x * Scale, h = Size.y * Scale;
                    return new Rect(Position.x - w * 0.5f, Position.y - h * 0.5f, w, h);
                }
            }
        }

        /// <summary>The expanded leaderboard in the toast's coordinates (x from the safe center, y up, 0 at the safe top).</summary>
        internal static Rect BoardRect(float safeWidth)
        {
            float width = safeWidth > 1f ? safeWidth : UiKit.RefWidth;
            float right = width * 0.5f - BoardRight;
            return new Rect(right - BoardWidth, -BoardTop - BoardHeight, BoardWidth, BoardHeight);
        }

        internal static ToastPlacement ToastLayout(float safeWidth, float toastWidth, bool boardOpen)
        {
            return ToastLayout(safeWidth, toastWidth, boardOpen, float.NaN, float.NaN);
        }

        /// <summary>
        /// rules-02: the toast layout for a safe area safeWidth wide and a toast of natural width toastWidth. The scale is
        /// min(1, (width - 40) / w) but never below MinToastScale; a toast that does not fit at that scale wraps to two lines
        /// (width - 64 by ToastWrapHeight, scale 1). The toast sits at ToastY, centered; when the leaderboard is open and
        /// would be covered, it moves below the board (board bottom - ToastGap - half its height), and below the band
        /// [avoidBottom, avoidTop] (the tutorial bubble, NaN when none) if it would cover it there.
        /// </summary>
        internal static ToastPlacement ToastLayout(float safeWidth, float toastWidth, bool boardOpen, float avoidTop, float avoidBottom)
        {
            float width = safeWidth > 1f ? safeWidth : UiKit.RefWidth;
            float avail = width - ToastSideMargin;
            float w = Mathf.Max(1f, toastWidth);
            var p = new ToastPlacement();
            if (w * MinToastScale > avail)
            {
                p.Wrap = true;
                p.Scale = 1f;
                p.Size = new Vector2(Mathf.Max(100f, width - ToastWrapMargin), ToastWrapHeight);
            }
            else
            {
                p.Scale = Mathf.Clamp(avail / w, MinToastScale, 1f);
                p.Size = new Vector2(w, ToastHeight);
            }
            float halfH = p.Size.y * p.Scale * 0.5f;
            float y = ToastY;
            if (boardOpen)
            {
                Rect board = BoardRect(width);
                Rect toast = new Rect(-p.Size.x * p.Scale * 0.5f, y - halfH, p.Size.x * p.Scale, 2f * halfH);
                if (Overlaps(toast, board, ToastGap)) y = board.yMin - ToastGap - halfH;
                if (!float.IsNaN(avoidTop) && !float.IsNaN(avoidBottom) && y - halfH < avoidTop + ToastGap && y + halfH > avoidBottom - ToastGap)
                    y = avoidBottom - ToastGap - halfH;
            }
            p.Position = new Vector2(0f, y);
            return p;
        }

        private static bool Overlaps(Rect a, Rect b, float margin)
        {
            return a.xMin < b.xMax + margin && a.xMax > b.xMin - margin && a.yMin < b.yMax + margin && a.yMax > b.yMin - margin;
        }

        private void SpawnGain(double gain, Vec2d point)
        {
            Gain g = null;
            for (int i = 0; i < gains.Length; i++)
            {
                if (!gains[i].Active)
                {
                    g = gains[i];
                    break;
                }
            }
            if (g == null)
            {
                g = gains[0];
                for (int i = 1; i < gains.Length; i++) if (gains[i].T > g.T) g = gains[i];
            }
            g.Active = true;
            g.T = 0f;
            g.World = new Vector2((float)point.X, (float)point.Y);
            g.Text.text = Strings.Gain(gain);
            g.Text.color = UiKit.Lighten(session != null && session.HumanIndex >= 0 ? Palette.ColorOf(session.HumanIndex) : Palette.ColorOf(0), 0.25f);
            g.Text.enabled = true;
        }

        private void TickGains(float dt)
        {
            Camera cam = Camera.main;
            for (int i = 0; i < gains.Length; i++)
            {
                Gain g = gains[i];
                if (!g.Active) continue;
                g.T += dt / GainSeconds;
                if (g.T >= 1f || cam == null)
                {
                    g.Active = false;
                    g.Text.enabled = false;
                    continue;
                }
                Vector3 sp = cam.WorldToScreenPoint(new Vector3(g.World.x, g.World.y, 0f));
                RectTransformUtility.ScreenPointToLocalPointInRectangle(CanvasRect, sp, null, out Vector2 local);
                float rise = 1f - (1f - g.T) * (1f - g.T);
                g.Text.rectTransform.anchoredPosition = local + new Vector2(0f, 60f + 150f * rise);
                float scale = g.T < 0.15f ? Mathf.Lerp(0.6f, 1.1f, g.T / 0.15f) : Mathf.Lerp(1.1f, 1f, Mathf.Clamp01((g.T - 0.15f) / 0.2f));
                g.Text.rectTransform.localScale = new Vector3(scale, scale, 1f);
                Color c = g.Text.color;
                c.a = Mathf.Clamp01((1f - g.T) / 0.35f);
                g.Text.color = c;
            }
        }

        private void TickVignette(float dt, GameSession s, Simulation sim, int h)
        {
            bool chased = HumanChased();
            vignetteAlpha = Mathf.MoveTowards(vignetteAlpha, chased ? 1f : 0f, dt / (chased ? 0.12f : 0.3f));
            if (vignetteAlpha <= 0f)
            {
                vignette.enabled = false;
                vignettePhase = 0f;
                return;
            }
            double eta = h >= 0 && h < sim.Players.Count ? sim.View.SparkCatchEta(h) : double.PositiveInfinity;
            float urgency = double.IsInfinity(eta) || double.IsNaN(eta) ? 0f : Mathf.Clamp01(1f - (float)eta / 2.5f);
            float hz = Mathf.Lerp(2.2f, 6f, urgency);
            vignettePhase += dt * hz;
            float pulse = 0.5f + 0.5f * Mathf.Sin(vignettePhase * Mathf.PI * 2f);
            Color c = Color.Lerp(Color.white, VignetteRed, 0.45f + 0.55f * pulse);
            c.a = vignetteAlpha * (0.32f + 0.3f * pulse + 0.18f * urgency);
            vignette.color = c;
            vignette.enabled = true;
        }

        // ------------------------------------------------------------------------------------------------------------

        private void ToggleBoard()
        {
            boardOpen = !boardOpen;
            for (int i = 0; i < rowKeys.Length; i++) rowKeys[i] = long.MinValue;
        }

        private void OnPauseClicked()
        {
            GameDirector d = Director;
            if (d != null) d.SetPaused(true);
        }

        private bool HumanChased()
        {
            GameSession s = session;
            if (s == null || s.IsAttract || s.HumanIndex < 0) return false;
            PlayerState p = s.Sim.Players[s.HumanIndex];
            return p.Alive && p.Spark != null;
        }

        private static int BestRival(Simulation sim, int h)
        {
            int best = -1, bestCells = -1;
            for (int i = 0; i < sim.Players.Count; i++)
            {
                if (i == h) continue;
                PlayerState p = sim.Players[i];
                if (!p.Alive) continue;
                int c = sim.Grid.CountOf(p.Id);
                if (c > bestCells)
                {
                    bestCells = c;
                    best = i;
                }
            }
            return best;
        }

        private static double HumanArea(GameSession s)
        {
            if (s == null || s.IsAttract || s.HumanIndex < 0) return 0.0;
            return s.Sim.AreaPercent(s.HumanIndex);
        }
    }
}
