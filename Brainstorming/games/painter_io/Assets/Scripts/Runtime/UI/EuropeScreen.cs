// The Pays screen: the 3D Europe map (EuropeMapView), the country bar and "Jouer ce pays", driven by the campaign of
// EuropeProgress (docs/europe/PROGRESSION.md). Locked countries are dimmed, skipped by the arrows and cannot be played
// (a tap selects them and shows the hint); unlocked ones carry a floating flag; won ones are shown as conquered. When
// first wins unlocked countries since the last visit, the map selects the first one and plays the reveal of their flags.
// Hidden reset: five taps on the "Europe" title within TitleTapWindow seconds show "Réinitialiser la progression"
// (a second tap confirms).
using System;
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.EventSystems;

namespace PainterIO.Runtime
{
    public sealed class EuropeScreen : UiScreen
    {
        public const int TitleTapsToReveal = 5;
        public const float TitleTapWindow = 1.5f;
        /// <summary>The reset button hides itself after this many seconds without a confirmation.</summary>
        public const float ResetVisibleSeconds = 8f;

        private static readonly Color StatusOpen = new Color32(135, 171, 204, 255);
        private static readonly Color StatusLocked = new Color32(0xF5, 0xB7, 0x31, 0xFF);

        private readonly EuropeCatalog.Country[] entries;
        private readonly UnityEngine.UI.Text title, progress, name, status, back, play, resetLabel;
        private readonly UnityEngine.UI.RawImage mapImage, flagImage;
        private readonly RectTransform viewport;
        private readonly CanvasGroup launchGroup;
        private readonly GameObject resetButton;
        private readonly HashSet<string> justRevealed = new HashSet<string>(StringComparer.Ordinal);
        private EuropeMapView map;
        private int selected;
        private bool progressDirty;
        private int titleTaps;
        private float lastTitleTap = -10f, resetShownAt = -100f;
        private bool resetArmed;

        public EuropeScreen(UiRoot root) : base(root, "Europe", UiRoot.MenuOrder + 1)
        {
            entries = (EuropeCatalog.Country[])EuropeCatalog.Load().countries.Clone();
            Array.Sort(entries, (a, b) => StringComparer.CurrentCultureIgnoreCase.Compare(a.DisplayName, b.DisplayName));
            selected = Mathf.Max(0, IndexOf(EuropeProgression.StartCountry));
            UiKit.FullScreen(CanvasRect, "Ocean", new Color32(13, 25, 45, 255), true).rectTransform.SetAsFirstSibling();
            title = UiKit.Label(Safe, "Heading", 82, UiKit.Light, TextAnchor.MiddleCenter, false, true);
            UiKit.Place(title.rectTransform, new Vector2(0.5f, 0.94f), Vector2.zero, new Vector2(900, 120));
            // Invisible tap target over the title (hidden reset).
            var titleTapTarget = UiKit.Btn(Safe, "Heading taps", new Vector2(420, 110), new Color(1, 1, 1, 0), 0, 20,
                new Color(1, 1, 1, 0), OnTitleTap, out _);
            UiKit.Place((RectTransform)titleTapTarget.transform, new Vector2(0.5f, 0.94f), Vector2.zero, new Vector2(420, 110));
            progress = UiKit.Label(Safe, "Progress", 34, StatusOpen, TextAnchor.MiddleCenter, false);
            UiKit.Place(progress.rectTransform, new Vector2(0.5f, 0.897f), Vector2.zero, new Vector2(900, 50));
            var previousScreen = UiKit.Btn(Safe, "Back", new Vector2(190, 78), UiKit.PanelNavy, 30, 33,
                UiKit.Light, root.CloseEurope, out back);
            UiKit.Place((RectTransform)previousScreen.transform, new Vector2(0.13f, 0.94f), Vector2.zero, new Vector2(190, 78));

            viewport = UiKit.Rect("Map viewport", Safe);
            viewport.anchorMin = new Vector2(0.02f, 0.28f);
            viewport.anchorMax = new Vector2(0.98f, 0.87f);
            viewport.offsetMin = viewport.offsetMax = Vector2.zero;
            // The render texture follows the viewport's aspect (MatchViewport), so the image simply fills it.
            var imageRect = UiKit.Rect("Map render", viewport);
            UiKit.Stretch(imageRect);
            mapImage = imageRect.gameObject.AddComponent<UnityEngine.UI.RawImage>();
            var trigger = imageRect.gameObject.AddComponent<EventTrigger>();
            var click = new EventTrigger.Entry { eventID = EventTriggerType.PointerClick };
            click.callback.AddListener(data => SelectAt((PointerEventData)data));
            trigger.triggers.Add(click);

            var reset = UiKit.Btn(Safe, "Reset progress", new Vector2(700, 92), new Color32(150, 52, 52, 235), 46, 34,
                UiKit.Light, OnResetTap, out resetLabel);
            UiKit.Place((RectTransform)reset.transform, new Vector2(0.5f, 0.835f), Vector2.zero, new Vector2(700, 92));
            resetButton = reset.gameObject;
            resetButton.SetActive(false);

            var countryBar = UiKit.Rounded(Safe, "Country controls", UiKit.PanelNavy, 38);
            UiKit.Place(countryBar.rectTransform, new Vector2(0.5f, 0.225f), Vector2.zero, new Vector2(920, 168));
            var flagRect = UiKit.Rect("Flag preview", countryBar.transform);
            UiKit.Place(flagRect, UiKit.Center, new Vector2(-245, 0), new Vector2(96, 68));
            flagImage = flagRect.gameObject.AddComponent<UnityEngine.UI.RawImage>();
            flagImage.raycastTarget = false;
            name = UiKit.Label(countryBar.transform, "Country name", 59, UiKit.Light, TextAnchor.MiddleCenter, false, true);
            name.resizeTextForBestFit = true;
            name.resizeTextMinSize = 33;
            name.resizeTextMaxSize = 59;
            UiKit.Place(name.rectTransform, UiKit.Center, new Vector2(52, 23), new Vector2(480, 74));
            status = UiKit.Label(countryBar.transform, "Country status", 32, StatusOpen, TextAnchor.MiddleCenter);
            status.resizeTextForBestFit = true;
            status.resizeTextMinSize = 20;
            status.resizeTextMaxSize = 32;
            UiKit.Place(status.rectTransform, UiKit.Center, new Vector2(62, -44), new Vector2(500, 44));
            AddArrow(countryBar.rectTransform, -1, "‹");
            AddArrow(countryBar.rectTransform, 1, "›");

            var launch = UiKit.PrimaryButton(Safe, "PlayCountry", new Vector2(540, 144),
                new Color32(34, 154, 148, 255), 56, () => PlaySelected(), out _, out play);
            UiKit.Place(launch, new Vector2(0.5f, 0.095f), Vector2.zero, new Vector2(540, 144));
            launchGroup = launch.gameObject.AddComponent<CanvasGroup>();
            EuropeProgress.Changed += () => progressDirty = true;
            Relabel();
            Active = this;
        }

        /// <summary>The last EuropeScreen built (EuropeShot and tests drive it through the methods below).</summary>
        public static EuropeScreen Active { get; private set; }

        /// <summary>ISO code of the selected country.</summary>
        public string SelectedCode => entries[selected].code;

        /// <summary>The map view (null until the screen was shown once).</summary>
        public EuropeMapView Map => map;

        /// <summary>The list index of a country code (the order of the arrows), -1 when unknown.</summary>
        public int IndexOf(string code) => Array.FindIndex(entries, country => country.code == code);

        /// <summary>What the arrow buttons do: the previous (-1) or next (+1) playable country; locked ones are skipped.</summary>
        public void StepSelection(int sign)
        {
            int step = sign < 0 ? -1 : 1;
            for (int k = 1; k <= entries.Length; k++)
            {
                int index = ((selected + step * k) % entries.Length + entries.Length) % entries.Length;
                if (StateAt(index) == CountryProgress.Locked) continue;
                Select(index);
                return;
            }
        }

        /// <summary>Selects a country by ISO code, as a tap on the map would (locked ones too). False when unknown.</summary>
        public bool SelectCode(string code)
        {
            int index = IndexOf(code);
            if (index < 0) return false;
            Select(index);
            return true;
        }

        /// <summary>"Jouer ce pays": starts the selected country when it is unlocked or won. False (and nothing) when locked.</summary>
        public bool PlaySelected()
        {
            if (StateAt(selected) == CountryProgress.Locked)
            {
                status.transform.localScale = Vector3.one * 1.15f;   // eased back in Tick: points at the hint
                return false;
            }
            Director.StartCountry(entries[selected]);
            return true;
        }

        /// <summary>Close framing of the selected flag (EuropeShot frames).</summary>
        public void SetCloseUp(bool on)
        {
            if (map != null) map.SetCloseUp(on);
        }

        private CountryProgress StateAt(int index) => EuropeProgress.Current.StateOf(entries[index].code);

        private void AddArrow(RectTransform parent, int sign, string glyph)
        {
            var button = UiKit.Btn(parent, sign < 0 ? "Previous" : "Next", new Vector2(112, 110),
                UiKit.NavyLight, 35, 66, UiKit.Light,
                () => StepSelection(sign), out var label);
            UiKit.Place((RectTransform)button.transform, UiKit.Center, new Vector2(sign * 380, 0), new Vector2(112, 110));
            label.text = glyph;
        }

        public override void Relabel()
        {
            bool fr = Strings.Language == 0;
            EuropeProgression campaign = EuropeProgress.Current;
            title.text = "Europe";
            progress.text = fr ? $"{campaign.WonCount} / {entries.Length} pays conquis" : $"{campaign.WonCount} / {entries.Length} countries conquered";
            back.text = fr ? "Retour" : "Back";
            play.text = fr ? "Jouer ce pays" : "Play this country";
            name.text = entries[selected].DisplayName;
            CountryProgress state = StateAt(selected);
            switch (state)
            {
                case CountryProgress.Locked:
                    status.text = fr ? "Verrouillé : gagne un pays voisin" : "Locked: win a neighboring country";
                    status.color = StatusLocked;
                    break;
                case CountryProgress.Won:
                    status.text = fr ? "Conquis" : "Conquered";
                    status.color = UiKit.Lighten(Palette.ColorOf(0), 0.25f);
                    break;
                default:
                    bool fresh = justRevealed.Contains(entries[selected].code);
                    status.text = fr ? (fresh ? "Nouveau ! À conquérir" : "À conquérir") : (fresh ? "New! To conquer" : "To conquer");
                    status.color = StatusOpen;
                    break;
            }
            launchGroup.alpha = state == CountryProgress.Locked ? 0.4f : 1f;
            flagImage.color = state == CountryProgress.Locked ? new Color(0.5f, 0.5f, 0.5f, 1f) : Color.white;
            resetLabel.text = resetArmed
                ? (fr ? "Confirmer la réinitialisation ?" : "Confirm the reset?")
                : (fr ? "Réinitialiser la progression" : "Reset progress");
        }

        protected override void OnShow()
        {
            if (map == null) map = EuropeMapView.Create(Root.transform, entries);
            map.gameObject.SetActive(true);
            MatchViewport();
            mapImage.texture = map.Display;
            map.ShowOverview();
            ApplyStates();

            // Countries unlocked since the last visit: select the first one and raise their flags.
            var reveal = new List<int>();
            justRevealed.Clear();
            foreach (string code in EuropeProgress.Current.PendingReveal)
            {
                int index = IndexOf(code);
                if (index < 0) continue;
                reveal.Add(index);
                justRevealed.Add(code);
            }
            if (reveal.Count > 0) selected = reveal[0];
            else if (StateAt(selected) == CountryProgress.Locked) selected = DefaultSelection();
            Select(selected);
            if (reveal.Count > 0)
            {
                map.PlayReveal(reveal);
                EuropeProgress.ConsumeReveal();
            }
            progressDirty = false;
        }

        protected override void OnHide()
        {
            if (map != null)
            {
                map.SetCloseUp(false);
                map.gameObject.SetActive(false);
            }
            HideReset();
        }

        public override void Tick(float dt)
        {
            if (!Visible || map == null) return;
            if (MatchViewport()) mapImage.texture = map.Display;
            if (progressDirty)
            {
                progressDirty = false;
                ApplyStates();
                Select(selected);
            }
            status.transform.localScale = Vector3.MoveTowards(status.transform.localScale, Vector3.one, dt * 0.8f);
            if (resetButton.activeSelf && Time.unscaledTime - resetShownAt > ResetVisibleSeconds) HideReset();
        }

        /// <summary>Keeps the map render texture at the viewport's aspect (portrait phones, tablets, resized windows).</summary>
        private bool MatchViewport()
        {
            Rect rect = viewport.rect;
            return rect.width > 1f && rect.height > 1f && map.SetAspect(rect.width / rect.height);
        }

        private void ApplyStates()
        {
            var states = new CountryProgress[entries.Length];
            for (int i = 0; i < entries.Length; i++) states[i] = StateAt(i);
            map.ApplyStates(states, Palette.ColorOf(0));
        }

        /// <summary>The first unlocked, not won country in list order, else the start country.</summary>
        private int DefaultSelection()
        {
            for (int i = 0; i < entries.Length; i++)
            {
                if (StateAt(i) == CountryProgress.Unlocked) return i;
            }
            return Mathf.Max(0, IndexOf(EuropeProgression.StartCountry));
        }

        private void Select(int index)
        {
            selected = index;
            Relabel();
            Texture2D texture = map.Select(index, entries[index]);
            flagImage.texture = texture;
            flagImage.enabled = texture != null;
            if (texture != null)
            {
                float size = Mathf.Min(96f / texture.width, 68f / texture.height);
                flagImage.rectTransform.sizeDelta = new Vector2(texture.width * size, texture.height * size);
            }
        }

        private void SelectAt(PointerEventData click)
        {
            RectTransform rect = mapImage.rectTransform;
            if (!RectTransformUtility.ScreenPointToLocalPointInRectangle(rect, click.position, click.pressEventCamera, out Vector2 point))
                return;
            int index = map.Pick(Rect.PointToNormalized(rect.rect, point), entries);
            if (index >= 0) Select(index);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Hidden reset.

        private void OnTitleTap()
        {
            float now = Time.unscaledTime;
            titleTaps = now - lastTitleTap <= TitleTapWindow ? titleTaps + 1 : 1;
            lastTitleTap = now;
            if (titleTaps < TitleTapsToReveal) return;
            titleTaps = 0;
            resetArmed = false;
            resetShownAt = now;
            resetButton.SetActive(true);
            Relabel();
        }

        private void OnResetTap()
        {
            if (!resetArmed)
            {
                resetArmed = true;
                resetShownAt = Time.unscaledTime;
                Relabel();
                return;
            }
            HideReset();
            EuropeProgress.ResetProgress();
            justRevealed.Clear();
            ApplyStates();
            Select(Mathf.Max(0, IndexOf(EuropeProgression.StartCountry)));
        }

        private void HideReset()
        {
            resetArmed = false;
            if (resetButton.activeSelf) resetButton.SetActive(false);
            Relabel();
        }
    }
}
