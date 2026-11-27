// Owned by B4. Contract 15.5: the results, shown by GameDirector only (after the 1.0 s death beat, or 0.6 s after a round end
// with the human alive). Reads GameDirector.LastOutcome only, never Simulation.Result, and never updates later. Big rank
// ("1er", "Ex æquo 1er"), final area, the cause line and the WHY line (saved margin, caught by whom and how far from home,
// territory lost, time up, last survivor, all eliminated), the stats line, a "réglages modifiés" tag when the test settings
// (or a command-line override) differ from Tuning, and REJOUER / MENU. Buttons ignore input for 0.5 s after the panel
// appears. The background match keeps playing behind a navy dim.
// Wave C (feel-11): a darker dim (0.86) behind the key numbers, cause and WHY paragraphs 880 units wide, and the lines below
// the area stacked from their measured heights, so an empty WHY line leaves no empty band (StackLines).
// Wave D-2 (traits-ui, docs/BIOME_TRAITS.md 7.2): when the human earned kill rewards this round, the stats block gains a
// second line ("1 terrain pris · vitesse +20 % · 2 boucliers", from Hud.Rewards); a saved return whose spark a shield put out
// reads "Étincelle éteinte : boucle perdue." instead of "Sauvé de justesse" (its margin is 0). Nothing changes otherwise.
// Rule v1.7 (contract 31): the area is the conquest percentage ("territoire conquis"), a conquest win reads "Territoire
// conquis à 100 % !" (a rival's: "Safran a conquis tout le territoire."), a time-up end adds "Le plus grand territoire
// l'emporte.", and the buttons are PAYS SUIVANT (the country screen, GameDirector.ToCountryScreen) and REJOUER (the same
// country again).
using PainterIO.Core;
using UnityEngine;
using UnityEngine.UI;

namespace PainterIO.Runtime
{
    public sealed class ResultsScreen : UiScreen
    {
        public const float InputGuardSeconds = 0.5f;
        /// <summary>Navy dim over the background match.</summary>
        public const float DimAlpha = 0.86f;
        /// <summary>Width of the cause and WHY paragraphs (wrap on).</summary>
        public const float ParagraphWidth = 880f;
        /// <summary>Top of the cause paragraph, below the area caption (TopCenter, y up).</summary>
        public const float CauseTop = -815f;
        /// <summary>Vertical gap between the cause, WHY and stats blocks, and between the stats and the tuning tag.</summary>
        public const float LineGap = 40f;
        public const float TagGap = 30f;
        public const float TagHeight = 64f;
        /// <summary>The main button (PAYS SUIVANT since rule v1.7): center above the safe bottom and size (its light rim adds 6 units around it).</summary>
        public const float ReplayY = 440f;
        public static readonly Vector2 ReplaySize = new Vector2(640f, 170f);

        private static readonly Color Saffron = UiKit.Saffron;

        private readonly Text rankShadow, rankHighlight, rankText, areaText, areaCaption, causeLine, whyLine, statsLine, tagText;
        private readonly Image tagBg;
        private readonly Text replayLabel, menuLabel;
        private readonly Image replayBg;
        private readonly RectTransform panel;
        private HumanOutcome outcome;
        private float shownAt = -10f;
        private float appear;

        public ResultsScreen(UiRoot root) : base(root, "Results", UiRoot.ResultsOrder)
        {
            Image dim = UiKit.FullScreen(CanvasRect, "Dim", UiKit.WithAlpha(UiKit.Navy, DimAlpha), false);
            dim.rectTransform.SetAsFirstSibling();

            panel = UiKit.Rect("Panel", Safe);
            UiKit.Stretch(panel);

            rankShadow = UiKit.Label(panel, "RankShadow", 230, UiKit.WithAlpha(UiKit.Navy, 0.85f), TextAnchor.MiddleCenter, false, true);
            UiKit.Place(rankShadow.rectTransform, UiKit.TopCenter, new Vector2(7f, -440f - 13f), new Vector2(1000f, 300f));
            rankHighlight = UiKit.Label(panel, "RankHighlight", 230, Color.white, TextAnchor.MiddleCenter, false, true);
            UiKit.Place(rankHighlight.rectTransform, UiKit.TopCenter, new Vector2(-4f, -440f + 4f), new Vector2(1000f, 300f));
            rankText = UiKit.Label(panel, "Rank", 230, Palette.ColorOf(0), TextAnchor.MiddleCenter, false, true);
            UiKit.Place(rankText.rectTransform, UiKit.TopCenter, new Vector2(0f, -440f), new Vector2(1000f, 300f));

            areaText = UiKit.Label(panel, "Area", 120, UiKit.Light, TextAnchor.MiddleCenter);
            UiKit.Place(areaText.rectTransform, UiKit.TopCenter, new Vector2(0f, -650f), new Vector2(900f, 150f));
            areaCaption = UiKit.Label(panel, "AreaCaption", 38, UiKit.WithAlpha(UiKit.Light, 0.7f), TextAnchor.MiddleCenter);
            UiKit.Place(areaCaption.rectTransform, UiKit.TopCenter, new Vector2(0f, -740f), new Vector2(900f, 56f));

            // Vertical positions are set by Layout() from the measured line heights; these are the defaults.
            causeLine = UiKit.Paragraph(panel, "Cause", 48, UiKit.Light, TextAnchor.MiddleCenter, ParagraphWidth);
            UiKit.Place(causeLine.rectTransform, UiKit.TopCenter, new Vector2(0f, -880f), new Vector2(ParagraphWidth, 140f));
            whyLine = UiKit.Paragraph(panel, "Why", 44, Saffron, TextAnchor.MiddleCenter, ParagraphWidth);
            UiKit.Place(whyLine.rectTransform, UiKit.TopCenter, new Vector2(0f, -1020f), new Vector2(ParagraphWidth, 130f));
            statsLine = UiKit.Paragraph(panel, "Stats", 38, UiKit.WithAlpha(UiKit.Light, 0.85f), TextAnchor.MiddleCenter, 980f);
            UiKit.Place(statsLine.rectTransform, UiKit.TopCenter, new Vector2(0f, -1150f), new Vector2(980f, 110f));

            tagBg = UiKit.Rounded(panel, "TuningTag", UiKit.WithAlpha(Saffron, 0.22f), 32f);
            UiKit.Place(tagBg.rectTransform, UiKit.TopCenter, new Vector2(0f, -1240f), new Vector2(380f, TagHeight));
            tagText = UiKit.Label(tagBg.transform, "Text", 32, Saffron, TextAnchor.MiddleCenter, false);
            UiKit.Stretch(tagText.rectTransform);

            // Rule v1.7: the main button goes on to the country screen ("PAYS SUIVANT", where a win plays the reveal of the
            // newly unlocked flags); the second one replays the same country ("REJOUER").
            RectTransform next = UiKit.PrimaryButton(Safe, "NextCountry", ReplaySize, Palette.ColorOf(0), 72, OnNextCountry,
                                                     out replayBg, out replayLabel);
            UiKit.Place(next, UiKit.BottomCenter, new Vector2(0f, ReplayY), ReplaySize);
            Button replay = UiKit.Btn(Safe, "Replay", new Vector2(440f, 124f), UiKit.WithAlpha(UiKit.NavyLight, 0.95f), 62f, 52, UiKit.Light, OnReplay, out menuLabel);
            UiKit.Place((RectTransform)replay.transform, UiKit.BottomCenter, new Vector2(0f, 250f), new Vector2(440f, 124f));
        }

        /// <summary>Buttons ignore input for 0.5 s after the panel appears.</summary>
        protected override bool AcceptsInput => Time.unscaledTime - shownAt >= InputGuardSeconds;

        /// <summary>The cause line currently shown (tests, probe).</summary>
        public string CauseText => causeLine.text;

        /// <summary>The WHY line currently shown, or null when hidden.</summary>
        public string WhyText => whyLine.enabled ? whyLine.text : null;

        public void ShowOutcome(HumanOutcome o)
        {
            outcome = o;
            shownAt = Time.unscaledTime;
            appear = 0f;
            Fill();
        }

        protected override void OnShow()
        {
            if (Time.unscaledTime - shownAt > 0.1f)
            {
                shownAt = Time.unscaledTime;
                appear = 0f;
                if (outcome == null && Director != null) outcome = Director.LastOutcome;
                Fill();
            }
        }

        public override void Relabel()
        {
            Fill();
        }

        public override void Tick(float dt)
        {
            appear = Mathf.Min(1f, appear + dt / 0.35f);
            float k = 1f - (1f - appear) * (1f - appear);
            float s = Mathf.Lerp(0.82f, 1f, k);
            panel.localScale = new Vector3(s, s, 1f);
        }

        private void Fill()
        {
            HumanOutcome o = outcome;
            replayLabel.text = Strings.Get("results.next_country");
            menuLabel.text = Strings.Get("results.replay");
            int human = Session != null && Session.HumanIndex >= 0 ? Session.HumanIndex : 0;
            Color hc = Palette.ColorOf(human);
            replayBg.color = hc;
            rankText.color = hc;
            rankHighlight.color = UiKit.Lighten(hc, 0.6f);
            areaCaption.text = Strings.Get("results.area_caption");
            tagText.text = Strings.Get("results.tuning_modified");
            bool tuned = SaveData.TuningModified || LaunchArgs.HasTuningOverride;
            tagBg.enabled = tuned;
            tagText.enabled = tuned;
            tagBg.rectTransform.sizeDelta = new Vector2(Mathf.Max(260f, tagText.preferredWidth + 56f), TagHeight);

            if (o == null)
            {
                SetRank(Strings.Rank(1, false));
                areaText.text = Strings.Area(0.0);
                causeLine.text = Strings.Get("results.time_up");
                SetWhy(null);
                statsLine.text = Strings.Format("results.stats", Strings.Count("results.stat.captures", 0), Strings.Count("results.stat.cuts", 0),
                                                Strings.Count("results.stat.kills", 0), Strings.Count("results.stat.pockets", 0), Strings.Duration(0.0));
                Layout();
                return;
            }

            SetRank(Strings.Rank(o.Rank, o.SharedRank));
            areaText.text = Strings.Area(o.AreaPercent);
            BuildLines(o, out string cause, out string why);
            RewardTally rewards = Root != null && Root.Hud != null ? Root.Hud.Rewards : null;
            // Wave D-2: the saved line of a return whose spark a shield put out (margin 0) says so.
            if (rewards != null && rewards.LastChasedReturnQuenched && o.Cause == EliminationCause.None && o.HadSavedReturn)
                why = Strings.Get("toast.quenched_return");
            causeLine.text = cause;
            SetWhy(why);
            statsLine.text = StatsLine(o, rewards, Strings.Language);
            Layout();
        }

        /// <summary>
        /// The stats line of 15.5, plus (wave D-2) the human's kill rewards on a second line when it earned some:
        /// "7 captures · 2 coupes · 1 élimination · 1 poche · 1:12" then "1 terrain pris · vitesse +20 %" (a line of its own,
        /// so no reward item is split by the wrap). Public static for tests.
        /// </summary>
        public static string StatsLine(HumanOutcome o, RewardTally rewards, int language)
        {
            string line = Strings.FormatIn(language, "results.stats",
                Strings.Count("results.stat.captures", o.Captures, language),
                Strings.Count("results.stat.cuts", o.CutsMade, language),
                Strings.Count("results.stat.kills", o.Kills, language),
                Strings.Count("results.stat.pockets", o.PocketsMade, language),
                Strings.Duration(o.SurvivedSeconds));
            string extra = rewards != null ? rewards.StatsItems(language) : null;
            return string.IsNullOrEmpty(extra) ? line : line + "\n" + extra;
        }

        /// <summary>Vertical centers (TopCenter, y up) of the lines below the area, from StackLines.</summary>
        internal struct LineStack
        {
            public float CauseY, WhyY, StatsY, TagY;
            /// <summary>Bottom edge of the tuning tag (the lowest element of the stack).</summary>
            public float Bottom;
        }

        /// <summary>
        /// feel-11: stacks the cause, WHY (skipped when whyHeight &lt;= 0, so no empty slot remains), stats and tag blocks
        /// from CauseTop down, LineGap apart (TagGap above the tag). Heights are the measured text heights.
        /// </summary>
        internal static LineStack StackLines(float causeHeight, float whyHeight, float statsHeight)
        {
            var s = new LineStack();
            float y = CauseTop;
            causeHeight = Mathf.Max(1f, causeHeight);
            s.CauseY = y - causeHeight * 0.5f;
            y -= causeHeight + LineGap;
            if (whyHeight > 0f)
            {
                s.WhyY = y - whyHeight * 0.5f;
                y -= whyHeight + LineGap;
            }
            else s.WhyY = s.CauseY;
            statsHeight = Mathf.Max(1f, statsHeight);
            s.StatsY = y - statsHeight * 0.5f;
            y -= statsHeight + TagGap;
            s.TagY = y - TagHeight * 0.5f;
            s.Bottom = y - TagHeight;
            return s;
        }

        private void Layout()
        {
            float causeH = LineHeight(causeLine);
            float whyH = whyLine.enabled ? LineHeight(whyLine) : 0f;
            float statsH = LineHeight(statsLine);
            LineStack s = StackLines(causeH, whyH, statsH);
            Place(causeLine, s.CauseY, causeH);
            if (whyLine.enabled) Place(whyLine, s.WhyY, whyH);
            Place(statsLine, s.StatsY, statsH);
            tagBg.rectTransform.anchoredPosition = new Vector2(0f, s.TagY);
        }

        /// <summary>The wrapped height of a paragraph at its width (one line at least).</summary>
        private static float LineHeight(Text t)
        {
            float h = t.preferredHeight;
            float oneLine = t.fontSize * 1.2f;
            return float.IsNaN(h) || h < oneLine ? oneLine : h;
        }

        private static void Place(Text t, float centerY, float height)
        {
            RectTransform rt = t.rectTransform;
            rt.sizeDelta = new Vector2(rt.sizeDelta.x, height + 8f);
            rt.anchoredPosition = new Vector2(0f, centerY);
        }

        /// <summary>
        /// The cause line and the WHY line of 15.5 for an outcome (why is null when there is none). Public static for tests.
        /// </summary>
        public static void BuildLines(HumanOutcome o, out string cause, out string why)
        {
            why = null;
            if (o == null)
            {
                cause = Strings.Get("results.time_up");
                return;
            }
            bool eliminated = o.Cause != EliminationCause.None;
            if (eliminated)
            {
                if (o.Cause == EliminationCause.Spark)
                {
                    bool hasDistance = o.CaughtDistance >= 0.0 && !double.IsNaN(o.CaughtDistance);
                    string dist = hasDistance ? Strings.Decimal(o.CaughtDistance, 1) : null;
                    if (o.Attacker >= 0)
                    {
                        string name = Strings.PlayerName(o.Attacker, -1);
                        cause = hasDistance ? Strings.Format("results.caught", name, dist) : Strings.Format("results.caught_nodist", name);
                    }
                    else cause = hasDistance ? Strings.Format("results.caught_unknown", dist) : Strings.Format("results.caught_unknown", "?");
                }
                else cause = Strings.Get("results.territory_lost");
                if (o.Reason == RoundEndReason.AllEliminated) why = Strings.Get("results.all_eliminated");
                return;
            }
            switch (o.Reason)
            {
                case RoundEndReason.LastSurvivor:
                    cause = Strings.Get("results.last_survivor");
                    break;
                case RoundEndReason.AllEliminated:
                    cause = Strings.Get("results.all_eliminated");
                    break;
                case RoundEndReason.Conquest:
                    // Rule v1.7: the human conquered the goal, or a rival did while the human was still alive.
                    bool mine = o.Rank == 1 || o.Winner < 0;
                    cause = mine ? Strings.Get("results.conquest") : Strings.Format("results.conquest_rival", Strings.PlayerName(o.Winner, -1));
                    break;
                default:
                    cause = Strings.Get("results.time_up");
                    break;
            }
            if (o.HadSavedReturn) why = Hud.SavedLine(o.LastSavedMargin);
            else if (o.Reason == RoundEndReason.TimeUp) why = Strings.Get("results.time_up_winner");
        }

        private void SetRank(string rank)
        {
            rankText.text = rank;
            rankShadow.text = rank;
            rankHighlight.text = rank;
            int size = rank.Length > 6 ? 150 : 230;
            rankText.fontSize = rankShadow.fontSize = rankHighlight.fontSize = size;
        }

        private void SetWhy(string why)
        {
            whyLine.enabled = !string.IsNullOrEmpty(why);
            whyLine.text = string.IsNullOrEmpty(why) ? " " : why;
        }

        private void OnReplay()
        {
            if (!AcceptsInput) return;
            GameDirector d = Director;
            if (d != null) d.StartRound();
        }

        /// <summary>Rule v1.7: "PAYS SUIVANT" goes on to the country screen, whatever the outcome.</summary>
        private void OnNextCountry()
        {
            if (!AcceptsInput) return;
            GameDirector d = Director;
            if (d != null) d.ToCountryScreen();
        }
    }
}
