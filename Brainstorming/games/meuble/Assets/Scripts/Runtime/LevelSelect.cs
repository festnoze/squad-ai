using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5_v3.md 6 and 15.10, CONTRACT_M5 16.10): the level select, a page of the title screen opened
    /// by "Niveaux". One card per entry of <see cref="GameState.LevelOrder"/> (never a fixed count), laid out in rows of
    /// <see cref="Tuning.LevelSelectColumns"/>: the level number in play order, its name (levelN.name), its best time
    /// ("{0} s", one decimal) or "-"; a locked card shows "Verrouillé" instead of the time and is not interactable.
    /// Unlocking is the save's rule (<see cref="SaveStore.IsUnlocked"/>): index 0, the level won, the previous level won,
    /// or opened by the levels v2 order migration; every level under UnlockAll. An unlocked card loads its level and
    /// closes the menus; "Retour" (and Escape, gamepad B, read by <see cref="Menu"/>) goes back to the title.
    /// Navigation is explicit and runs over the playable cards and "Retour" only (a locked card can never take the
    /// selection): left and right follow the play order, up and down keep the column as well as they can, and "Retour"
    /// closes the loop. The card of Jouer's level (<see cref="SaveStore.FirstUnwonLevel"/>) is the default selection
    /// (<see cref="DefaultSelectable"/>).
    /// Levels v2 (docs/levels_v2/LEVELS_V2.md 7): the best time is read under the level's RecordId, and the first card of
    /// each act of levels.json wears an act tag with the act's name.
    /// The page has its own Canvas, enabled only while it is open (never its GameObject, PRD 8.4).
    /// M7 level select redesign: the title page's look. A left column (the page title in the display face, the red rule,
    /// the difficulty and the progress, a legend of the miniatures, Retour) over the warm translucent side panel, and a
    /// grid of portrait cards right of it, sized by anchors so it fits any aspect. Each card shows a top-down miniature
    /// of its level (<see cref="LevelMiniature"/>, drawn once and cached), its number and name, one icon per watcher
    /// (people, pets and robots apart), the player's furniture, the record of the current difficulty, and its won or
    /// locked state.
    /// </summary>
    public sealed class LevelSelect : MonoBehaviour
    {
        /// <summary>One card of the grid (tests read every part).</summary>
        public sealed class Card
        {
            public string LevelId;
            public int Index;
            public Button Button;
            public Text Number;
            public Text Name;
            public Text Best;
            public Text Locked;
            /// <summary>M7: the level's top-down miniature, its frame, the won badge and the lock over the miniature.</summary>
            public Image Miniature;
            public Image Frame;
            public Image WonBadge;
            public Image LockIcon;
            /// <summary>M7: the watcher icons, the "+n" past the last one, and the player furniture.</summary>
            public readonly List<Image> Watchers = new List<Image>();
            public Text MoreWatchers;
            public Image Furniture;
            public bool ArtReady;
            /// <summary>
            /// Levels v2 (LEVELS_V2.md 7): the key the card reads its best time under, the level's
            /// <see cref="LevelDef.RecordId"/> ("level6~1"); null until the page first opens (the level is parsed then).
            /// </summary>
            public string RecordId;
            /// <summary>Levels v2: the act tag over the miniature of the first card of each act (null on the other cards).</summary>
            public Image ActTag;
            public Text Act;
            /// <summary>Levels v2: the act this card opens, 1 for the first; 0 when it opens none.</summary>
            public int ActNumber;
            public string ActNameKey;
            /// <summary>Stars (idea 5): the three small stars at the right of the record line, the saved count at the current difficulty lit.</summary>
            public StarRow Stars;
        }

        /// <summary>Stars: the stars earned over the line-up at the current difficulty, as the total line shows them.</summary>
        public int StarsEarned { get; private set; }

        /// <summary>Stars: the stars the line-up can hold (levels times <see cref="Tuning.StarsPerLevel"/>).</summary>
        public int StarsPossible => Stars.Possible(order.Count);

        /// <summary>Stars: the total line's text ("12 / 66 étoiles"), or null before the column is built.</summary>
        public string StarsLineText => starsLine != null ? starsLine.text : null;

        public bool IsOpen { get; private set; }

        /// <summary>The cards, in play order.</summary>
        public IReadOnlyList<Card> Cards => cards;
        public int CardCount => cards.Count;

        /// <summary>"Retour".</summary>
        public Button BackButton { get; private set; }

        /// <summary>SPECTATOR: the "Mode spectateur" checkbox, above Retour (a button that toggles its tick).</summary>
        public Button SpectatorButton { get; private set; }

        /// <summary>
        /// SPECTATOR: the checkbox is ticked: a card pressed now loads its level in spectator mode (Menu.PlayLevel). Kept for
        /// the session (a static, never saved); off at every launch.
        /// </summary>
        public bool SpectatorChecked
        {
            get => spectatorWanted;
            set
            {
                spectatorWanted = value;
                ShowSpectatorTick();
            }
        }

        private static bool spectatorWanted;
        private Image spectatorTick;
        private Text spectatorLabel;

        /// <summary>
        /// The default selection while the page is open. Levels v2 (LEVELS_V2.md 7, IDEAS bug 20): the card of
        /// <see cref="SaveStore.FirstUnwonLevel"/> (Jouer's level), else the first playable card, else Retour.
        /// </summary>
        public Selectable DefaultSelectable
        {
            get
            {
                string target = SaveStore.FirstUnwonLevel(order);
                foreach (Card card in cards)
                {
                    if (card.LevelId == target && IsPlayable(card.Index))
                    {
                        return card.Button;
                    }
                }
                foreach (Card card in cards)
                {
                    if (IsPlayable(card.Index))
                    {
                        return card.Button;
                    }
                }
                return BackButton;
            }
        }

        private readonly List<Card> cards = new List<Card>();
        private readonly List<string> order = new List<string>();
        private Canvas canvas;
        private RectTransform grid;
        private Font font;
        private Font display;
        private GameState game;
        private Action<string> choose;
        private Dictionary<string, Text> labels;
        private Text difficultyLine;
        private Text progressLine;
        private Text starsLine;
        private readonly List<KeyValuePair<Text, Func<string>>> legend = new List<KeyValuePair<Text, Func<string>>>();
        // True while SetOpen(true) refreshes the page: the cards may then parse their level for its RecordId.
        private bool opening;
        private static readonly Color ActPlate = new Color(0.8f, 0.2f, 0.16f, 0.94f);

        // ----- The title page's palette and column (Menu's M7 title redesign), 1920 x 1080 reference pixels. -----
        private static readonly Color PageDim = new Color(0.07f, 0.045f, 0.032f, 0.62f);
        private static readonly Color SidePanel = new Color(0.1f, 0.066f, 0.05f, 0.86f);
        private static readonly Color TitleInk = new Color(1f, 0.94f, 0.82f, 1f);
        private static readonly Color TaglineInk = new Color(0.96f, 0.8f, 0.58f, 0.95f);
        private static readonly Color SoftInk = new Color(1f, 0.94f, 0.82f, 0.72f);
        private static readonly Color LockedInk = new Color(1f, 0.62f, 0.5f, 0.95f);
        private static readonly Color DimInk = new Color(1f, 0.94f, 0.82f, 0.45f);
        private const float Margin = 150f;
        private const float SidePanelWidth = 1240f;
        private static readonly Vector2 BackSize = new Vector2(420f, 78f);
        // Stars (idea 5): the total line under the progress line (y 178, 40 tall) and above the legend (its first row at
        // y 92, 36 tall), a gold star where the legend puts its icons; on a card, three 16 px stars in the 60 px the record
        // line leaves free at its right (its rect ends 60 px before the card's edge), centred 33 px from that edge.
        private const float StarsLineY = 136f;
        private const float CardStarSize = 16f;
        private const float CardStarGap = 3f;
        private const float CardStarsInset = 33f;
        private const float CardStarsAnchorY = 0.08f;

        /// <summary>
        /// Builds the page under <paramref name="parent"/> (the Menu's root Canvas). <paramref name="onChoose"/> receives
        /// the id of a playable card that was pressed, <paramref name="onBack"/> the press of Retour.
        /// </summary>
        public static LevelSelect Create(Transform parent, GameState game, Font font, Dictionary<string, Text> labels,
            Action<string> onChoose, Action onBack)
        {
            var go = new GameObject("LevelSelect", typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var select = go.AddComponent<LevelSelect>();
            select.Build(game, font, labels, onChoose, onBack);
            return select;
        }

        private void Build(GameState gameState, Font textFont, Dictionary<string, Text> labelMap, Action<string> onChoose, Action onBack)
        {
            game = gameState;
            font = textFont;
            display = Hud.DisplayFont;
            labels = labelMap;
            choose = onChoose;
            var rect = (RectTransform)transform;
            Stretch(rect);
            canvas = gameObject.AddComponent<Canvas>();
            // A nested Canvas raycasts its own graphics only.
            gameObject.AddComponent<GraphicRaycaster>();
            canvas.enabled = false;

            // The title page's backdrop, a little darker so the cards stand off the moving scene: a warm dim, soft
            // edges, and the espresso panel fading in from the left under the column.
            Stretch(NewImage(transform, "Dim", null, PageDim).rectTransform);
            Stretch(NewImage(transform, "Edges", ProceduralArt.Vignette, new Color(0.04f, 0.025f, 0.02f, 0.55f)).rectTransform);
            Image side = NewImage(transform, "Band", ProceduralArt.SideFade, SidePanel);
            side.rectTransform.anchorMin = new Vector2(0f, 0f);
            side.rectTransform.anchorMax = new Vector2(0f, 1f);
            side.rectTransform.pivot = new Vector2(0f, 0.5f);
            side.rectTransform.anchoredPosition = Vector2.zero;
            side.rectTransform.sizeDelta = new Vector2(SidePanelWidth, 0f);

            BuildColumn(onBack);

            var gridGo = new GameObject("Grid", typeof(RectTransform));
            gridGo.transform.SetParent(transform, false);
            grid = (RectTransform)gridGo.transform;
            grid.anchorMin = Vector2.zero;
            grid.anchorMax = Vector2.one;
            grid.pivot = new Vector2(0.5f, 0.5f);
            grid.offsetMin = new Vector2(Tuning.LevelSelectGridLeft, Tuning.LevelSelectGridBottom);
            grid.offsetMax = new Vector2(-Tuning.LevelSelectGridRight, -Tuning.LevelSelectGridTop);
            Refresh();
        }

        /// <summary>The left column, on the title page's margin: title, red rule, difficulty, progress, legend, Retour.</summary>
        private void BuildColumn(Action onBack)
        {
            var left = new Vector2(0f, 0.5f);
            Text header = NewText(transform, "SelectTitle", Strings.TitleLevels, 120, TitleInk, display);
            header.alignment = TextAnchor.MiddleLeft;
            PlaceLeft(header.rectTransform, left, new Vector2(Margin, 352f), new Vector2(560f, 150f));
            Image rule = NewImage(transform, "SelectRule", null, LevelMiniature.ChairRed);
            PlaceLeft(rule.rectTransform, left, new Vector2(Margin + 4f, 268f), new Vector2(84f, 6f));
            difficultyLine = NewText(transform, "SelectDifficulty", DifficultyText(), 34, TaglineInk, font);
            difficultyLine.alignment = TextAnchor.MiddleLeft;
            PlaceLeft(difficultyLine.rectTransform, left, new Vector2(Margin, 222f), new Vector2(460f, 48f));
            progressLine = NewText(transform, "SelectProgress", ProgressText(), 28, SoftInk, font);
            progressLine.alignment = TextAnchor.MiddleLeft;
            PlaceLeft(progressLine.rectTransform, left, new Vector2(Margin, 178f), new Vector2(460f, 40f));
            // Stars: the total at the current difficulty, a gold star then "12 / 66 étoiles", laid out like a legend row.
            Image starsIcon = NewImage(transform, "SelectStarsIcon", Stars.Star, Stars.Gold);
            starsIcon.preserveAspect = true;
            PlaceLeft(starsIcon.rectTransform, left, new Vector2(Margin, StarsLineY), new Vector2(36f, 36f));
            starsLine = NewText(transform, "SelectStars", StarsText(), 28, SoftInk, font);
            starsLine.alignment = TextAnchor.MiddleLeft;
            PlaceLeft(starsLine.rectTransform, left, new Vector2(Margin + 54f, StarsLineY), new Vector2(400f, 40f));

            // The legend of the miniatures and the watcher icons, one row each.
            float y = 92f;
            LegendRow("SelectLegendYou", LevelMiniature.Dot, () => Strings.SelectLegendYou, y);
            LegendRow("SelectLegendExit", LevelMiniature.ExitMark, () => Strings.SelectLegendExit, y -= 50f);
            LegendRow("SelectLegendPeople", LevelMiniature.Person, () => Strings.SelectLegendPeople, y -= 50f);
            LegendRow("SelectLegendPet", LevelMiniature.Pet, () => Strings.SelectLegendPet, y -= 50f);
            LegendRow("SelectLegendRobot", LevelMiniature.Robot, () => Strings.SelectLegendRobot, y -= 50f);

            BackButton = Hud.MenuButton(transform, "SelectBack", Strings.SelectBack, display, labels);
            PlaceLeft((RectTransform)BackButton.transform, left, new Vector2(Margin, -366f), BackSize);
            StyleWarm(BackButton);
            if (labels != null && labels.TryGetValue("SelectBackLabel", out Text back))
            {
                back.fontSize = 44;
                back.alignment = TextAnchor.MiddleLeft;
                back.color = TitleInk;
                back.rectTransform.offsetMin = new Vector2(36f, 0f);
                back.rectTransform.offsetMax = new Vector2(-24f, 0f);
            }
            BackButton.onClick.AddListener(() => onBack?.Invoke());
            BuildSpectatorBox(left);
        }

        /// <summary>
        /// SPECTATOR: the "Mode spectateur" checkbox, a warm column button above Retour with a box on its left whose chair
        /// red tick shows while it is ticked. A click, a tap, Enter or gamepad A toggles it (a Button, so the input module
        /// submits it like Retour); it sits in the page's explicit navigation between the grid and Retour.
        /// </summary>
        private void BuildSpectatorBox(Vector2 left)
        {
            SpectatorButton = Hud.MenuButton(transform, "SelectSpectator", Strings.SelectSpectator, font, labels);
            PlaceLeft((RectTransform)SpectatorButton.transform, left, new Vector2(Margin, -262f), new Vector2(BackSize.x, 64f));
            StyleWarm(SpectatorButton);
            if (labels != null && labels.TryGetValue("SelectSpectatorLabel", out Text label))
            {
                spectatorLabel = label;
                label.fontSize = 30;
                label.alignment = TextAnchor.MiddleLeft;
                label.color = TitleInk;
                label.rectTransform.offsetMin = new Vector2(84f, 0f);
                label.rectTransform.offsetMax = new Vector2(-16f, 0f);
            }
            Image frame = NewImage(SpectatorButton.transform, "SelectSpectatorBox", null, TitleInk);
            PlaceLeft(frame.rectTransform, left, new Vector2(28f, 0f), new Vector2(36f, 36f));
            Image inner = NewImage(frame.transform, "SelectSpectatorBoxInner", null, new Color(0.1f, 0.066f, 0.05f, 1f));
            Anchor(inner.rectTransform, Vector2.zero, Vector2.one, new Vector2(4f, 4f), new Vector2(-4f, -4f));
            spectatorTick = NewImage(frame.transform, "SelectSpectatorTick", null, LevelMiniature.ChairRed);
            Anchor(spectatorTick.rectTransform, Vector2.zero, Vector2.one, new Vector2(8f, 8f), new Vector2(-8f, -8f));
            SpectatorButton.onClick.AddListener(() => SpectatorChecked = !SpectatorChecked);
            ShowSpectatorTick();
        }

        private void ShowSpectatorTick()
        {
            if (spectatorTick != null)
            {
                spectatorTick.enabled = spectatorWanted;
            }
        }

        private void LegendRow(string name, Sprite icon, Func<string> text, float y)
        {
            var left = new Vector2(0f, 0.5f);
            Image image = NewImage(transform, name + "Icon", icon, Color.white);
            image.preserveAspect = true;
            PlaceLeft(image.rectTransform, left, new Vector2(Margin, y), new Vector2(36f, 36f));
            Text label = NewText(transform, name, text(), 28, SoftInk, font);
            label.alignment = TextAnchor.MiddleLeft;
            PlaceLeft(label.rectTransform, left, new Vector2(Margin + 54f, y), new Vector2(400f, 40f));
            legend.Add(new KeyValuePair<Text, Func<string>>(label, text));
        }

        private string DifficultyText() => string.Format(Strings.OptionsDifficulty, Strings.DifficultyName(SaveStore.Options.DifficultyId));

        private string ProgressText()
        {
            int won = 0;
            foreach (string id in order)
            {
                if (SaveStore.IsWon(id))
                {
                    won++;
                }
            }
            return string.Format(Strings.SelectProgress, won, order.Count);
        }

        /// <summary>
        /// Stars: the total line, the saved stars of every card's level at the current difficulty over the line-up's
        /// possible stars. The record ids resolve only while the page opens (<see cref="RecordIdOf"/>), as the records do.
        /// </summary>
        private string StarsText()
        {
            string difficulty = SaveStore.Options.DifficultyId;
            int earned = 0;
            foreach (Card card in cards)
            {
                earned += SaveStore.Current.StarsOf(RecordIdOf(card, IsOpen || opening), difficulty);
            }
            StarsEarned = earned;
            return string.Format(Strings.StarsTotal, earned, StarsPossible);
        }

        private void Start()
        {
            // "--levelshot <dir>" (a built player): a screenshot of this page, then quit.
            string dir = Probe.ArgValue("--levelshot");
            if (!Application.isEditor && !string.IsNullOrEmpty(dir))
            {
                StartCoroutine(Shot(dir));
            }
        }

        // LOADDOTS: the next level of the play order WarmStep works on.
        private int warmIndex;

        /// <summary>
        /// LOADDOTS: the first-open work is done, so <see cref="SetOpen"/> only reads caches. That work is, for every level
        /// of the play order, reading and parsing its JSON (<see cref="LevelMiniature.Def"/>, also the card's RecordId and
        /// stars) and drawing its miniature on the CPU (<see cref="LevelMiniature.MiniatureOf"/>); both are cached for the
        /// whole run.
        /// </summary>
        public bool Warm => warmIndex >= WarmOrder.Count;

        private IReadOnlyList<string> WarmOrder => game != null && game.LevelOrder != null ? game.LevelOrder : order;

        /// <summary>
        /// LOADDOTS: one small piece of the first-open work, so <see cref="Menu"/> can spread it over frames: the next
        /// level's parse, or (once parsed) its miniature and summary. Returns <see cref="Warm"/>.
        /// </summary>
        public bool WarmStep()
        {
            IReadOnlyList<string> levels = WarmOrder;
            if (warmIndex >= levels.Count)
            {
                return true;
            }
            string id = levels[warmIndex];
            if (!LevelMiniature.IsParsed(id))
            {
                LevelMiniature.Def(id);
                return false;
            }
            LevelMiniature.MiniatureOf(id);
            LevelMiniature.SummaryOf(id);
            warmIndex++;
            return warmIndex >= levels.Count;
        }

        /// <summary>Opens or closes the page; opening refreshes every card from the save first.</summary>
        public void SetOpen(bool open)
        {
            if (open)
            {
                opening = true;
                try
                {
                    Refresh();
                    EnsureArt();
                }
                finally
                {
                    opening = false;
                }
            }
            IsOpen = open;
            if (canvas != null && canvas.enabled != open)
            {
                canvas.enabled = open;
            }
        }

        /// <summary>
        /// The card at <paramref name="index"/> may be played: its level is unlocked. The single gate of the page: the
        /// card's interactable state and a press both go through it.
        /// </summary>
        public bool IsPlayable(int index) => SaveStore.IsUnlocked(order, index); // MUTATION:LOCKED_PLAYABLE

        /// <summary>A press of the card at <paramref name="index"/>: loads its level when it is playable, else nothing.</summary>
        public void Choose(int index)
        {
            if (index < 0 || index >= order.Count || !IsPlayable(index))
            {
                return;
            }
            choose?.Invoke(order[index]);
        }

        /// <summary>Rebuilds the cards when the play order changed, then refreshes texts, locks and navigation.</summary>
        public void Refresh()
        {
            IReadOnlyList<string> levels = game != null ? game.LevelOrder : null;
            if (!SameOrder(levels))
            {
                Rebuild(levels);
            }
            if (spectatorLabel != null)
            {
                spectatorLabel.text = Strings.SelectSpectator;
            }
            ShowSpectatorTick();
            foreach (Card card in cards)
            {
                bool playable = IsPlayable(card.Index);
                card.Button.interactable = playable;
                card.Best.enabled = playable;
                card.Locked.enabled = !playable;
                // M7 design (CONTRACT_M7 4.1): the record of the current difficulty. Levels v2: under the level's RecordId.
                string recordId = RecordIdOf(card, IsOpen || opening);
                card.Best.text = SaveStore.TryGetBest(recordId, SaveStore.Options.DifficultyId, out float seconds) // MUTATION:SELECT_DIFFICULTY_RECORD
                    ? string.Format(Strings.SelectBest, Strings.FormatSeconds(seconds))
                    : Strings.SelectNone;
                // The name and the lock in the current language (the language may have changed since the cards were built).
                card.Name.text = LevelName(card.LevelId);
                card.Locked.text = Strings.SelectLocked;
                card.Number.color = playable ? TitleInk : DimInk;
                card.Name.color = playable ? TitleInk : DimInk;
                card.Best.color = seconds > 0f && playable ? TitleInk : SoftInk;
                // Stars: the saved count at the current difficulty, lit at once (no reveal on a card); hidden under a lock.
                if (card.Stars != null)
                {
                    card.Stars.Set(SaveStore.Current.StarsOf(recordId, SaveStore.Options.DifficultyId), false);
                    card.Stars.SetVisible(playable);
                }
                // M7: the miniature dims under a lock; a won level wears the green check.
                card.Miniature.color = playable ? Color.white : new Color(0.55f, 0.5f, 0.46f, 0.5f);
                card.LockIcon.enabled = !playable;
                card.WonBadge.enabled = playable && SaveStore.IsWon(card.LevelId);
                Color iconTint = playable ? Color.white : new Color(1f, 1f, 1f, 0.45f);
                foreach (Image icon in card.Watchers)
                {
                    icon.color = iconTint;
                }
                card.Furniture.color = iconTint;
                card.MoreWatchers.color = playable ? TitleInk : DimInk;
                // Levels v2: the act tag, in the current language, dimmed under a lock like the rest of the card.
                if (card.ActTag != null)
                {
                    card.Act.text = ActLabel(card.ActNumber, card.ActNameKey);
                    card.ActTag.color = playable ? ActPlate : new Color(ActPlate.r, ActPlate.g, ActPlate.b, 0.45f);
                    card.Act.color = playable ? TitleInk : DimInk;
                }
            }
            if (difficultyLine != null)
            {
                difficultyLine.text = DifficultyText();
                progressLine.text = ProgressText();
            }
            if (starsLine != null)
            {
                starsLine.text = StarsText();
            }
            foreach (KeyValuePair<Text, Func<string>> row in legend)
            {
                row.Key.text = row.Value();
            }
            Navigate();
        }

        /// <summary>M7: draws (once, cached by LevelMiniature) the miniature, watchers and furniture of every card.</summary>
        private void EnsureArt()
        {
            foreach (Card card in cards)
            {
                if (card.ArtReady)
                {
                    continue;
                }
                card.ArtReady = true;
                Sprite miniature = LevelMiniature.MiniatureOf(card.LevelId);
                card.Miniature.sprite = miniature;
                card.Miniature.enabled = miniature != null;
                LevelMiniature.Summary summary = LevelMiniature.SummaryOf(card.LevelId);
                var kinds = new List<Sprite>();
                for (int i = 0; i < summary.Humans; i++) kinds.Add(LevelMiniature.Person);
                for (int i = 0; i < summary.Pets; i++) kinds.Add(LevelMiniature.Pet);
                for (int i = 0; i < summary.Robots; i++) kinds.Add(LevelMiniature.Robot);
                int shown = Mathf.Min(kinds.Count, Mathf.Max(1, Tuning.LevelSelectMaxWatcherIcons));
                if (kinds.Count > shown)
                {
                    // Keep room for "+n": the last icon slot becomes the count, but the kinds that differ stay visible.
                    shown--;
                }
                for (int i = 0; i < card.Watchers.Count; i++)
                {
                    bool on = i < shown;
                    card.Watchers[i].enabled = on;
                    card.Watchers[i].sprite = on ? kinds[i] : null;
                }
                card.MoreWatchers.enabled = kinds.Count > shown;
                card.MoreWatchers.text = "+" + (kinds.Count - shown);
                card.Furniture.sprite = LevelMiniature.Furniture(summary.PlayerKind);
                card.Furniture.enabled = true;
            }
        }

        private bool SameOrder(IReadOnlyList<string> levels)
        {
            int count = levels != null ? levels.Count : 0;
            if (count != order.Count)
            {
                return false;
            }
            for (int i = 0; i < count; i++)
            {
                if (levels[i] != order[i])
                {
                    return false;
                }
            }
            return true;
        }

        private void Rebuild(IReadOnlyList<string> levels)
        {
            foreach (Card card in cards)
            {
                if (card.Button != null)
                {
                    Destroy(card.Button.gameObject);
                }
            }
            cards.Clear();
            order.Clear();
            if (levels != null)
            {
                order.AddRange(levels);
            }
            int columns = Mathf.Max(1, Tuning.LevelSelectColumns);
            int rows = Mathf.Max(1, (order.Count + columns - 1) / columns);
            // Levels v2 (LEVELS_V2.md 7): the acts of levels.json, matched by the id of each act's first level (so a play
            // order that differs from the manifest still tags the right cards, and an act whose level is not shown is skipped).
            var actStarts = new Dictionary<string, KeyValuePair<int, string>>();
            ManifestDef manifest = LevelLoader.LoadManifestDef();
            for (int a = 0; a < manifest.Acts.Count; a++)
            {
                ActDef act = manifest.Acts[a];
                if (act != null && act.From >= 0 && act.From < manifest.Levels.Count && !actStarts.ContainsKey(manifest.Levels[act.From]))
                {
                    actStarts[manifest.Levels[act.From]] = new KeyValuePair<int, string>(a + 1, act.NameKey);
                }
            }
            for (int i = 0; i < order.Count; i++)
            {
                Card card = NewCard(i, order[i], i / columns, i % columns, rows, columns);
                if (actStarts.TryGetValue(order[i], out KeyValuePair<int, string> act))
                {
                    AddActTag(card, act.Key, act.Value);
                }
                cards.Add(card);
            }
            if (IsOpen)
            {
                EnsureArt();
            }
        }

        /// <summary>
        /// A portrait card, placed by anchors in the grid (so the grid fills the area right of the column on any aspect):
        /// the miniature on top in its dark frame, then the number and the name, the watchers and the furniture, and the
        /// record or the lock at the bottom.
        /// </summary>
        private Card NewCard(int index, string levelId, int row, int column, int rows, int columns)
        {
            string name = "Card" + (index + 1);
            Button button = Hud.MenuButton(grid, name, CardNumber(index).ToString(), display, labels);
            var rect = (RectTransform)button.transform;
            rect.anchorMin = new Vector2((float)column / columns, 1f - (float)(row + 1) / rows);
            rect.anchorMax = new Vector2((float)(column + 1) / columns, 1f - (float)row / rows);
            rect.pivot = new Vector2(0.5f, 0.5f);
            float gap = Tuning.LevelSelectCardGap * 0.5f;
            rect.offsetMin = new Vector2(gap, gap);
            rect.offsetMax = new Vector2(-gap, -gap);
            StyleWarm(button);

            var card = new Card { LevelId = levelId, Index = index, Button = button };
            Transform t = button.transform;
            float top = 1f - Tuning.LevelSelectMiniatureShare;

            // The miniature in its dark frame (dark paper whatever the plate colour, so it reads selected or not).
            card.Frame = NewImage(t, name + "Frame", ProceduralArt.Rounded, LevelMiniature.Paper);
            card.Frame.type = Image.Type.Sliced;
            Anchor(card.Frame.rectTransform, new Vector2(0f, top), Vector2.one, new Vector2(8f, 0f), new Vector2(-8f, -8f));
            card.Miniature = NewImage(card.Frame.transform, name + "Miniature", null, Color.white);
            card.Miniature.preserveAspect = true;
            card.Miniature.enabled = false;
            Anchor(card.Miniature.rectTransform, Vector2.zero, Vector2.one, new Vector2(5f, 5f), new Vector2(-5f, -5f));
            card.LockIcon = NewImage(card.Frame.transform, name + "Lock", LevelMiniature.Lock, Color.white);
            card.LockIcon.preserveAspect = true;
            Centered(card.LockIcon.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(64f, 64f), Vector2.zero);
            card.WonBadge = NewImage(card.Frame.transform, name + "Won", LevelMiniature.Check, Color.white);
            card.WonBadge.preserveAspect = true;
            Centered(card.WonBadge.rectTransform, new Vector2(1f, 1f), new Vector2(38f, 38f), new Vector2(-6f, -6f), new Vector2(1f, 1f));

            // The number, large in the display face, and the name beside it.
            card.Number = t.Find(name + "Label").GetComponent<Text>();
            card.Number.fontSize = 48;
            card.Number.alignment = TextAnchor.MiddleLeft;
            card.Number.color = TitleInk;
            Anchor(card.Number.rectTransform, new Vector2(0f, 0.29f), new Vector2(0f, top), new Vector2(14f, 0f), new Vector2(76f, 0f));
            card.Name = NewText(t, name + "Name", LevelName(levelId), 24, TitleInk, display);
            card.Name.alignment = TextAnchor.MiddleLeft;
            // Long names ("Le fauteuil à bascule") wrap on two lines and shrink to fit the card.
            card.Name.horizontalOverflow = HorizontalWrapMode.Wrap;
            card.Name.verticalOverflow = VerticalWrapMode.Truncate;
            card.Name.resizeTextForBestFit = true;
            card.Name.resizeTextMinSize = 15;
            card.Name.resizeTextMaxSize = 25;
            card.Name.lineSpacing = 0.85f;
            Anchor(card.Name.rectTransform, new Vector2(0f, 0.29f), new Vector2(1f, top), new Vector2(72f, 2f), new Vector2(-8f, -2f));

            // The watchers, one icon each, and the player's furniture in a dark chip at the right.
            for (int i = 0; i < Mathf.Max(1, Tuning.LevelSelectMaxWatcherIcons); i++)
            {
                Image icon = NewImage(t, name + "Watcher" + i, null, Color.white);
                icon.preserveAspect = true;
                icon.enabled = false;
                Centered(icon.rectTransform, new Vector2(0f, 0.22f), new Vector2(26f, 26f), new Vector2(26f + i * 26f, 0f));
                card.Watchers.Add(icon);
            }
            card.MoreWatchers = NewText(t, name + "More", "+0", 22, TitleInk, font);
            card.MoreWatchers.alignment = TextAnchor.MiddleLeft;
            card.MoreWatchers.enabled = false;
            Centered(card.MoreWatchers.rectTransform, new Vector2(0f, 0.22f), new Vector2(40f, 28f),
                new Vector2(30f + (Tuning.LevelSelectMaxWatcherIcons - 1) * 26f, 0f));
            Image chip = NewImage(t, name + "Chip", ProceduralArt.Rounded, LevelMiniature.Paper);
            chip.type = Image.Type.Sliced;
            Centered(chip.rectTransform, new Vector2(1f, 0.18f), new Vector2(46f, 46f), new Vector2(-30f, 0f));
            card.Furniture = NewImage(chip.transform, name + "Furniture", null, Color.white);
            card.Furniture.preserveAspect = true;
            card.Furniture.enabled = false;
            Anchor(card.Furniture.rectTransform, Vector2.zero, Vector2.one, new Vector2(6f, 6f), new Vector2(-6f, -6f));

            // The record of the current difficulty, or the lock line.
            card.Best = NewText(t, name + "Best", Strings.SelectNone, 26, TitleInk, font);
            card.Best.alignment = TextAnchor.MiddleLeft;
            Anchor(card.Best.rectTransform, new Vector2(0f, 0.02f), new Vector2(1f, 0.14f), new Vector2(14f, 0f), new Vector2(-60f, 0f));
            card.Locked = NewText(t, name + "Locked", Strings.SelectLocked, 24, LockedInk, font);
            card.Locked.alignment = TextAnchor.MiddleLeft;
            Anchor(card.Locked.rectTransform, new Vector2(0f, 0.02f), new Vector2(1f, 0.14f), new Vector2(14f, 0f), new Vector2(-60f, 0f));
            // Stars: three small stars at the right end of the record line (Refresh lights the saved count).
            card.Stars = new StarRow(t, name + "Stars", CardStarSize, CardStarGap);
            card.Stars.Place(new Vector2(1f, CardStarsAnchorY), new Vector2(-CardStarsInset, 0f));
            card.Stars.SetVisible(false);
            button.onClick.AddListener(() => Choose(index));
            return card;
        }

        /// <summary>
        /// Levels v2 (LEVELS_V2.md 7): the act tag of the first card of an act, a chair-red plate across the top of the
        /// miniature (clear of the won badge in its top right corner) with the act's name.
        /// </summary>
        private void AddActTag(Card card, int number, string nameKey)
        {
            string name = "Card" + (card.Index + 1);
            card.ActNumber = number;
            card.ActNameKey = nameKey;
            card.ActTag = NewImage(card.Frame.transform, name + "ActTag", ProceduralArt.Rounded, ActPlate);
            card.ActTag.type = Image.Type.Sliced;
            Anchor(card.ActTag.rectTransform, new Vector2(0f, 1f), new Vector2(1f, 1f), new Vector2(6f, -38f), new Vector2(-48f, -6f));
            card.Act = NewText(card.ActTag.transform, name + "Act", ActLabel(number, nameKey), 20, TitleInk, font);
            card.Act.alignment = TextAnchor.MiddleLeft;
            card.Act.horizontalOverflow = HorizontalWrapMode.Wrap;
            card.Act.verticalOverflow = VerticalWrapMode.Truncate;
            card.Act.resizeTextForBestFit = true;
            card.Act.resizeTextMinSize = 11;
            card.Act.resizeTextMaxSize = 20;
            Anchor(card.Act.rectTransform, Vector2.zero, Vector2.one, new Vector2(10f, 0f), new Vector2(-8f, 0f));
        }

        /// <summary>LEVELNUM: the number a card shows for the level at <paramref name="index"/> of the play order (1 based).</summary>
        public static int CardNumber(int index) => index + 1;

        /// <summary>
        /// LEVELNUM: the number the level select shows for <paramref name="levelId"/> (its card position in the levels.json
        /// "levels" order, never the file name: level19 is 18 since rev 3), or 0 when the level is not in that order (a test level).
        /// The intro card shows the same number (Hud.ShowLevel).
        /// </summary>
        public static int DisplayNumber(IReadOnlyList<string> order, string levelId)
        {
            if (order == null || string.IsNullOrEmpty(levelId))
            {
                return 0;
            }
            for (int i = 0; i < order.Count; i++)
            {
                if (order[i] == levelId)
                {
                    return CardNumber(i);
                }
            }
            return 0;
        }

        /// <summary>
        /// Levels v2: the text of an act tag, the act's name from Strings (act2.name: "La maisonnée"). When Strings has a
        /// "select.act" format ({0} the act number, {1} its name), the tag uses it instead.
        /// </summary>
        public static string ActLabel(int number, string nameKey)
        {
            string name = string.IsNullOrEmpty(nameKey) ? string.Empty : Strings.Get(nameKey);
            const string formatKey = "select.act";
            string format = Strings.Get(formatKey);
            return format != formatKey ? string.Format(format, number, name) : name;
        }

        /// <summary>
        /// Levels v2: the key the card's best time is read under, its level's <see cref="LevelDef.RecordId"/>. The level is
        /// parsed (once, cached by LevelMiniature) only when <paramref name="resolve"/> is true, that is while the page
        /// opens; before that the bare id stands in (the page is closed, nobody reads it).
        /// </summary>
        private static string RecordIdOf(Card card, bool resolve)
        {
            if (card.RecordId == null && resolve)
            {
                LevelDef def = LevelMiniature.Def(card.LevelId);
                card.RecordId = def != null && !string.IsNullOrEmpty(def.RecordId) ? def.RecordId : card.LevelId;
            }
            return card.RecordId ?? card.LevelId;
        }

        /// <summary>The level's name: its levelN.name string, or the id itself when Strings has none.</summary>
        public static string LevelName(string levelId)
        {
            string key = levelId + ".name";
            string name = Strings.Get(key);
            return name == key ? levelId : name;
        }

        /// <summary>
        /// Explicit navigation over the playable cards and Retour. Left and right step through the play order (and wrap
        /// across rows), up and down move to the nearest playable card of the next row up or down (the closest column),
        /// and past the last row (or above the first) to Retour, whose up and down lead back into the grid.
        /// </summary>
        private void Navigate()
        {
            int columns = Mathf.Max(1, Tuning.LevelSelectColumns);
            var playable = new List<Card>();
            foreach (Card card in cards)
            {
                if (IsPlayable(card.Index))
                {
                    playable.Add(card);
                }
                else
                {
                    card.Button.navigation = new Navigation { mode = Navigation.Mode.None };
                }
            }
            for (int k = 0; k < playable.Count; k++)
            {
                Card card = playable[k];
                int row = card.Index / columns;
                int column = card.Index % columns;
                card.Button.navigation = new Navigation
                {
                    mode = Navigation.Mode.Explicit,
                    selectOnLeft = k > 0 ? playable[k - 1].Button : null,
                    selectOnRight = k + 1 < playable.Count ? playable[k + 1].Button : null,
                    selectOnUp = (Selectable)NearestInRow(playable, row, column, -1, columns) ?? BackButton,
                    // SPECTATOR: down past the last row reaches the checkbox, then Retour.
                    selectOnDown = (Selectable)NearestInRow(playable, row, column, +1, columns) ?? (Selectable)SpectatorButton ?? BackButton,
                };
            }
            Button first = playable.Count > 0 ? playable[0].Button : null;
            Button last = playable.Count > 0 ? playable[playable.Count - 1].Button : null;
            if (SpectatorButton != null)
            {
                // SPECTATOR: the column reads checkbox then Retour; right goes back into the grid.
                SpectatorButton.navigation = new Navigation
                {
                    mode = Navigation.Mode.Explicit,
                    selectOnUp = last,
                    selectOnDown = BackButton,
                    selectOnRight = first,
                };
            }
            BackButton.navigation = new Navigation
            {
                mode = Navigation.Mode.Explicit,
                selectOnUp = SpectatorButton != null ? (Selectable)SpectatorButton : last,
                selectOnDown = first,
            };
        }

        /// <summary>The playable card closest to <paramref name="column"/> in the nearest row in <paramref name="step"/>'s direction.</summary>
        private static Button NearestInRow(List<Card> playable, int row, int column, int step, int columns)
        {
            int lastRow = -1;
            foreach (Card card in playable)
            {
                lastRow = Mathf.Max(lastRow, card.Index / columns);
            }
            for (int r = row + step; r >= 0 && r <= lastRow; r += step)
            {
                Button best = null;
                int bestDistance = int.MaxValue;
                foreach (Card card in playable)
                {
                    if (card.Index / columns != r)
                    {
                        continue;
                    }
                    int distance = Mathf.Abs(card.Index % columns - column);
                    if (distance < bestDistance)
                    {
                        bestDistance = distance;
                        best = card.Button;
                    }
                }
                if (best != null)
                {
                    return best;
                }
            }
            return null;
        }

        // ----- The screenshot run -----

        /// <summary>
        /// "--levelshot &lt;dir&gt;": opens this page over the title with a few records seeded in memory (the save is
        /// pointed at the shot folder first, so the real one is never touched), selects the second card, writes
        /// levels_page.png and quits. Nothing is written: the records live in memory only.
        /// </summary>
        private IEnumerator Shot(string dir)
        {
            Directory.CreateDirectory(dir);
            SaveStore.PathOverride = Path.Combine(dir, "levelshot_save.json");
            Menu menu = GetComponentInParent<Menu>();
            float until = Time.realtimeSinceStartup + 20f;
            while ((menu == null || !menu.TitleOpen) && Time.realtimeSinceStartup < until)
            {
                yield return null;
            }
            yield return new WaitForSecondsRealtime(2.5f);
            string difficulty = SaveStore.Options.DifficultyId;
            // A fresh save in memory (three levels won), so the shot shows won, open and locked cards together.
            SaveStore.Current.Won?.Clear();
            SaveStore.Current.Best?.Clear();
            float[] times = { 21.4f, 38.9f, 47.2f };
            for (int i = 0; i < times.Length && i < order.Count && i < cards.Count; i++)
            {
                SaveStore.Current.RecordWin(order[i], RecordIdOf(cards[i], true), times[i], difficulty);
                // Stars: three, two and one, so the shot shows every count and a total.
                SaveStore.Current.RecordStars(RecordIdOf(cards[i], true), Tuning.StarsPerLevel - i, difficulty);
            }
            if (menu != null)
            {
                menu.OpenLevelSelect();
                // LOADDOTS: the first open may load over a few frames (the dots on Niveaux) before the page shows.
                while (menu.LevelSelectLoading)
                {
                    yield return null;
                }
            }
            yield return new WaitForSecondsRealtime(0.5f);
            if (cards.Count > 1 && EventSystem.current != null)
            {
                EventSystem.current.SetSelectedGameObject(cards[1].Button.gameObject);
            }
            yield return new WaitForSecondsRealtime(1f);
            ScreenCapture.CaptureScreenshot(Path.Combine(dir, "levels_page.png"));
            yield return new WaitForSecondsRealtime(1f);
            Application.Quit();
        }

        // ----- Construction helpers -----

        /// <summary>The title page's button colours: a warm translucent plate, lighter brown under the mouse, chair red selected.</summary>
        private static void StyleWarm(Button button)
        {
            ColorBlock colors = button.colors;
            colors.normalColor = new Color(0.17f, 0.115f, 0.085f, 0.82f);
            colors.highlightedColor = new Color(0.36f, 0.25f, 0.18f, 0.94f);
            colors.selectedColor = new Color(0.8f, 0.2f, 0.16f, 0.97f);
            colors.pressedColor = new Color(0.55f, 0.12f, 0.09f, 1f);
            colors.disabledColor = new Color(0.12f, 0.08f, 0.06f, 0.62f);
            button.colors = colors;
        }

        private Text NewText(Transform parent, string name, string value, int size, Color color, Font face)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var text = go.AddComponent<Text>();
            text.font = face != null ? face : font;
            text.fontSize = size;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = color;
            text.text = value;
            text.raycastTarget = false;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            var shadow = go.AddComponent<Shadow>();
            shadow.effectColor = new Color(0.05f, 0.03f, 0.02f, 0.6f);
            shadow.effectDistance = new Vector2(2f, -2f);
            if (labels != null)
            {
                labels[name] = text;
            }
            return text;
        }

        private static Image NewImage(Transform parent, string name, Sprite sprite, Color color)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var image = go.AddComponent<Image>();
            image.sprite = sprite;
            image.color = color;
            image.raycastTarget = false;
            return image;
        }

        /// <summary>Places a rect by its left edge at <paramref name="offset"/> from <paramref name="anchor"/>.</summary>
        private static void PlaceLeft(RectTransform rect, Vector2 anchor, Vector2 offset, Vector2 size)
        {
            rect.anchorMin = rect.anchorMax = anchor;
            rect.pivot = new Vector2(0f, 0.5f);
            rect.anchoredPosition = offset;
            rect.sizeDelta = size;
        }

        /// <summary>Stretches a rect between two anchors, inset by pixel offsets.</summary>
        private static void Anchor(RectTransform rect, Vector2 min, Vector2 max, Vector2 offsetMin, Vector2 offsetMax)
        {
            rect.anchorMin = min;
            rect.anchorMax = max;
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.offsetMin = offsetMin;
            rect.offsetMax = offsetMax;
        }

        /// <summary>A fixed size rect centred on <paramref name="anchor"/> plus <paramref name="offset"/> (or on <paramref name="pivot"/>).</summary>
        private static void Centered(RectTransform rect, Vector2 anchor, Vector2 size, Vector2 offset, Vector2? pivot = null)
        {
            rect.anchorMin = rect.anchorMax = anchor;
            rect.pivot = pivot ?? new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = offset;
            rect.sizeDelta = size;
        }

        private static void Stretch(RectTransform rect)
        {
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
        }
    }
}
