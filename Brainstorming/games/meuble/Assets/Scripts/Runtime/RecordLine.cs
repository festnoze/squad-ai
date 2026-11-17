using Meuble.Core;
using UnityEngine;
using UnityEngine.UI;

namespace Meuble
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5_v3.md 6 and 15.10): records every win in the save and shows the record line under the win
    /// panel: "Record : 12,3 s" (win.best, one decimal, the French comma of the win time) and, when this win set it,
    /// "Nouveau record !" (win.newBest). The end screen after the last level shows it too, below its button.
    /// GameState knows nothing of the save: this component subscribes to <see cref="GameState.StateChanged"/> (and
    /// unsubscribes in OnDestroy). On Won it records <see cref="GameState.Def"/>.Id and <see cref="GameState.Elapsed"/>
    /// (the fixed step time) through <see cref="SaveStore.RecordWin"/>; any other state hides the line.
    /// The texts are graphics of the win panel's own Canvas (<see cref="Hud.WinPanel"/>), so they show exactly when the
    /// panel does; a hidden line only disables its Text components.
    /// </summary>
    public sealed class RecordLine : MonoBehaviour
    {
        /// <summary>A win was recorded and its line is up (the win panel itself may be hidden by a menu).</summary>
        public bool HasRecord { get; private set; }

        /// <summary>The outcome of the last recorded win.</summary>
        public RecordResult Last { get; private set; }

        /// <summary>The line shows on screen: a recorded win, under a visible win panel.</summary>
        public bool Shown => HasRecord && best != null && best.enabled && (hud == null || hud.WinVisible);

        /// <summary>"Nouveau record !" shows with the line.</summary>
        public bool NewBestShown => Shown && newBest != null && newBest.enabled;

        /// <summary>The line is placed for the end screen (the last level of levels.json).</summary>
        public bool OnEndScreen { get; private set; }

        public string BestText => best != null ? best.text : null;
        public string NewBestText => newBest != null ? newBest.text : null;
        public RectTransform BestRect => best != null ? best.rectTransform : null;
        public RectTransform NewBestRect => newBest != null ? newBest.rectTransform : null;

        private GameState game;
        private Hud hud;
        private Text best;
        private Text newBest;

        // Reference pixels (1920 x 1080), from the win panel's center: below win.next on the win panel, below the
        // "Menu principal" button on the end screen (Hud: win.next at -170, the end button at -250, 88 high).
        private const float WinY = -236f;
        private const float EndY = -340f;
        private const float RowHeight = 56f;
        private const float Gap = 40f;
        private const int FontSize = 40;
        private static readonly Color BestInk = new Color(1f, 1f, 1f, 0.95f);
        private static readonly Color NewBestInk = new Color(1f, 0.82f, 0.3f, 1f);

        /// <summary>Builds the line under the HUD's win panel (or under <paramref name="fallbackParent"/> without a HUD).</summary>
        public static RecordLine Create(GameState game, Hud hud, Font font, Transform fallbackParent)
        {
            var go = new GameObject("RecordLine", typeof(RectTransform));
            Transform parent = hud != null && hud.WinPanel != null ? hud.WinPanel : fallbackParent;
            go.transform.SetParent(parent, false);
            var rect = (RectTransform)go.transform;
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
            var line = go.AddComponent<RecordLine>();
            line.Init(game, hud, font);
            return line;
        }

        private void Init(GameState gameState, Hud hudView, Font font)
        {
            game = gameState;
            hud = hudView;
            best = NewText("RecordBest", font, BestInk);
            newBest = NewText("RecordNew", font, NewBestInk);
            newBest.text = Strings.WinNewBest;
            Hide();
            if (game != null)
            {
                game.StateChanged += OnStateChanged;
            }
        }

        private void OnDestroy()
        {
            if (game != null)
            {
                game.StateChanged -= OnStateChanged;
            }
        }

        private void OnStateChanged(PlayState state)
        {
            if (state != PlayState.Won || game == null || game.Def == null)
            {
                Hide();
                return;
            }
            // M7 design (CONTRACT_M7 4.1): under the difficulty the level was built and played with.
            RecordResult result = SaveStore.RecordWin(game.Def.Id, game.Elapsed, game.Difficulty.Id);
            Show(result, game.IsLastLevel);
        }

        /// <summary>Shows the line for <paramref name="result"/>, placed for the win panel or the end screen.</summary>
        public void Show(RecordResult result, bool endScreen)
        {
            Last = result;
            HasRecord = true;
            OnEndScreen = endScreen;
            best.text = string.Format(Strings.WinBest, Strings.FormatSeconds(result.Best));
            best.enabled = true;
            newBest.enabled = result.NewBest;
            Layout(endScreen ? EndY : WinY, result.NewBest);
        }

        public void Hide()
        {
            HasRecord = false;
            if (best != null)
            {
                best.enabled = false;
            }
            if (newBest != null)
            {
                newBest.enabled = false;
            }
        }

        /// <summary>One centered row: the record alone, or the record then "Nouveau record !" side by side.</summary>
        private void Layout(float y, bool withNew)
        {
            float bestWidth = Mathf.Max(1f, best.preferredWidth);
            float newWidth = withNew ? Mathf.Max(1f, newBest.preferredWidth) : 0f;
            float total = bestWidth + (withNew ? Gap + newWidth : 0f);
            Place(best.rectTransform, -total * 0.5f + bestWidth * 0.5f, y, bestWidth);
            Place(newBest.rectTransform, total * 0.5f - newWidth * 0.5f, y, Mathf.Max(1f, newWidth));
        }

        private static void Place(RectTransform rect, float x, float y, float width)
        {
            rect.anchorMin = rect.anchorMax = new Vector2(0.5f, 0.5f);
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = new Vector2(x, y);
            rect.sizeDelta = new Vector2(width + 8f, RowHeight);
        }

        private Text NewText(string name, Font font, Color color)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(transform, false);
            var text = go.AddComponent<Text>();
            text.font = font != null ? font : Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            text.fontSize = FontSize;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = color;
            text.raycastTarget = false;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            var shadow = go.AddComponent<Shadow>();
            shadow.effectColor = new Color(0f, 0f, 0f, 0.65f);
            shadow.effectDistance = new Vector2(2f, -3f);
            return text;
        }
    }
}
