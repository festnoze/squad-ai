using System;
using System.Collections.Generic;
using Meuble.Core;
using UnityEngine;
using UnityEngine.UI;

namespace Meuble
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5_v3.md 6 and 15.10, CONTRACT_M5 16.10): the level select, a page of the title screen opened
    /// by "Niveaux". One card per entry of <see cref="GameState.LevelOrder"/> (never a fixed count), laid out in rows of
    /// <see cref="Tuning.LevelSelectColumns"/>: the level number in play order, its name (levelN.name), its best time
    /// ("{0} s", one decimal) or "-"; a locked card shows "Verrouillé" instead of the time and is not interactable.
    /// Unlocking is the save's rule (<see cref="SaveStore.IsUnlocked"/>): index 0, or the previous level won; every
    /// level under UnlockAll. An unlocked card loads its level and closes the menus; "Retour" (and Escape, gamepad B,
    /// read by <see cref="Menu"/>) goes back to the title.
    /// Navigation is explicit and runs over the playable cards and "Retour" only (a locked card can never take the
    /// selection): left and right follow the play order, up and down keep the column as well as they can, and "Retour"
    /// closes the loop. The first unlocked card is the default selection (<see cref="DefaultSelectable"/>).
    /// The page has its own Canvas, enabled only while it is open (never its GameObject, PRD 8.4).
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
        }

        public bool IsOpen { get; private set; }

        /// <summary>The cards, in play order.</summary>
        public IReadOnlyList<Card> Cards => cards;
        public int CardCount => cards.Count;

        /// <summary>"Retour".</summary>
        public Button BackButton { get; private set; }

        /// <summary>The first unlocked card (the default selection while the page is open), or Retour.</summary>
        public Selectable DefaultSelectable
        {
            get
            {
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
        private GameState game;
        private Action<string> choose;
        private Dictionary<string, Text> labels;

        // Reference pixels (1920 x 1080) from the screen center.
        private const float CardWidth = 240f;
        private const float CardHeight = 168f;
        private const float GapX = 20f;
        private const float GapY = 22f;
        private const float GridTop = 300f;
        private const float GridBottom = -320f;
        private const float HeaderY = 400f;
        private const float BackY = -420f;
        private static readonly Color Cream = new Color(1f, 0.92f, 0.75f, 1f);
        private static readonly Color LockedInk = new Color(1f, 0.55f, 0.45f, 0.95f);
        private static readonly Color DimInk = new Color(1f, 1f, 1f, 0.55f);

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
            labels = labelMap;
            choose = onChoose;
            var rect = (RectTransform)transform;
            Stretch(rect);
            canvas = gameObject.AddComponent<Canvas>();
            // A nested Canvas raycasts its own graphics only.
            gameObject.AddComponent<GraphicRaycaster>();
            canvas.enabled = false;

            Stretch(NewImage(transform, "Dim", null, new Color(0.03f, 0.03f, 0.05f, 0.55f)).rectTransform);
            Stretch(NewImage(transform, "Edges", ProceduralArt.Vignette, new Color(0.02f, 0.02f, 0.03f, 0.6f)).rectTransform);
            Text header = NewText(transform, "SelectTitle", Strings.TitleLevels, 96, Cream);
            Place(header.rectTransform, new Vector2(0f, HeaderY), new Vector2(1600f, 120f));

            var gridGo = new GameObject("Grid", typeof(RectTransform));
            gridGo.transform.SetParent(transform, false);
            grid = (RectTransform)gridGo.transform;
            Stretch(grid);

            BackButton = Hud.MenuButton(transform, "SelectBack", Strings.SelectBack, font, labels);
            Place((RectTransform)BackButton.transform, new Vector2(0f, BackY), new Vector2(420f, 88f));
            BackButton.onClick.AddListener(() => onBack?.Invoke());
            Refresh();
        }

        /// <summary>Opens or closes the page; opening refreshes every card from the save first.</summary>
        public void SetOpen(bool open)
        {
            if (open)
            {
                Refresh();
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
            foreach (Card card in cards)
            {
                bool playable = IsPlayable(card.Index);
                card.Button.interactable = playable;
                card.Best.enabled = playable;
                card.Locked.enabled = !playable;
                // M7 design (CONTRACT_M7 4.1): the record of the current difficulty.
                card.Best.text = SaveStore.TryGetBest(card.LevelId, SaveStore.Options.DifficultyId, out float seconds) // MUTATION:SELECT_DIFFICULTY_RECORD
                    ? string.Format(Strings.SelectBest, Strings.FormatSeconds(seconds))
                    : Strings.SelectNone;
                card.Number.color = playable ? Color.white : DimInk;
                card.Name.color = playable ? Color.white : DimInk;
            }
            Navigate();
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
            // Rows of 6 hold 18 cards at full height; more rows shrink the cards to stay between the header and Retour.
            float height = Mathf.Min(CardHeight, (GridTop - GridBottom - (rows - 1) * GapY) / rows);
            float left = -(columns * CardWidth + (columns - 1) * GapX) * 0.5f + CardWidth * 0.5f;
            for (int i = 0; i < order.Count; i++)
            {
                int row = i / columns;
                int column = i % columns;
                var at = new Vector2(left + column * (CardWidth + GapX), GridTop - height * 0.5f - row * (height + GapY));
                cards.Add(NewCard(i, order[i], at, height));
            }
        }

        private Card NewCard(int index, string levelId, Vector2 at, float height)
        {
            string name = "Card" + (index + 1);
            Button button = Hud.MenuButton(grid, name, (index + 1).ToString(), font, labels);
            Place((RectTransform)button.transform, at, new Vector2(CardWidth, height));
            var card = new Card { LevelId = levelId, Index = index, Button = button };
            card.Number = button.transform.Find(name + "Label").GetComponent<Text>();
            card.Number.fontSize = 50;
            Band(card.Number.rectTransform, 0.64f, 1f);
            card.Name = CardText(button.transform, name + "Name", LevelName(levelId), 28, Color.white);
            // Long names ("Le fauteuil à bascule") wrap on two lines and shrink to fit the card.
            card.Name.horizontalOverflow = HorizontalWrapMode.Wrap;
            card.Name.verticalOverflow = VerticalWrapMode.Truncate;
            card.Name.resizeTextForBestFit = true;
            card.Name.resizeTextMinSize = 16;
            card.Name.resizeTextMaxSize = 28;
            Band(card.Name.rectTransform, 0.3f, 0.66f);
            card.Best = CardText(button.transform, name + "Best", Strings.SelectNone, 30, Color.white);
            Band(card.Best.rectTransform, 0.04f, 0.32f);
            card.Locked = CardText(button.transform, name + "Locked", Strings.SelectLocked, 28, LockedInk);
            Band(card.Locked.rectTransform, 0.04f, 0.32f);
            button.onClick.AddListener(() => Choose(index));
            return card;
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
                    selectOnDown = (Selectable)NearestInRow(playable, row, column, +1, columns) ?? BackButton,
                };
            }
            Button first = playable.Count > 0 ? playable[0].Button : null;
            Button last = playable.Count > 0 ? playable[playable.Count - 1].Button : null;
            BackButton.navigation = new Navigation
            {
                mode = Navigation.Mode.Explicit,
                selectOnUp = last,
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

        // ----- Construction helpers -----

        private Text CardText(Transform parent, string name, string value, int size, Color color)
        {
            Text text = NewText(parent, name, value, size, color);
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            return text;
        }

        /// <summary>Stretches a card text across the card, between two heights (fractions of the card, from the bottom).</summary>
        private static void Band(RectTransform rect, float bottom, float top)
        {
            rect.anchorMin = new Vector2(0f, bottom);
            rect.anchorMax = new Vector2(1f, top);
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.offsetMin = new Vector2(8f, 0f);
            rect.offsetMax = new Vector2(-8f, 0f);
        }

        private Text NewText(Transform parent, string name, string value, int size, Color color)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var text = go.AddComponent<Text>();
            text.font = font;
            text.fontSize = size;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = color;
            text.text = value;
            text.raycastTarget = false;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            var shadow = go.AddComponent<Shadow>();
            shadow.effectColor = new Color(0f, 0f, 0f, 0.7f);
            shadow.effectDistance = new Vector2(2f, -3f);
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

        private static void Place(RectTransform rect, Vector2 offset, Vector2 size)
        {
            rect.anchorMin = rect.anchorMax = new Vector2(0.5f, 0.5f);
            rect.pivot = new Vector2(0.5f, 0.5f);
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
