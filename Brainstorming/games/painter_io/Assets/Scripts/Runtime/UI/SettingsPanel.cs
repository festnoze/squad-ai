// Owned by B4. Contract 15.2: the Options panel (opened from the menu). Son, Vibrations, Bonus lasso (default OFF, saved),
// Langue FR/EN, Qualité Auto/Haute/Moyenne/Basse and a version label. Five taps on the version label reveal the hidden
// "Réglages de test" section: Vitesse étincelle 1,4 to 2,4 step 0,1, Durée de manche 60 / 90 / 120 s, Délai anneau 10 to 30 s
// step 5, Réinitialiser (SaveData test settings, 11.5). Closing the panel flushes SaveData.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace PainterIO.Runtime
{
    public sealed class SettingsPanel : UiScreen
    {
        public const int VersionTapsToReveal = 5;
        public const float VersionTapWindow = 1.5f;
        public const float PanelWidth = 920f;
        public const float RowHeight = 112f;

        /// <summary>Stays true for the rest of the app session once revealed.</summary>
        private static bool testsRevealed;

        private readonly RectTransform panel;
        private readonly Image panelBg;
        private readonly Text title, versionText, testsTitle, closeLabel;
        private readonly List<KeyValuePair<Text, string>> rowLabels = new List<KeyValuePair<Text, string>>();
        private readonly UiSwitch sound, haptics, lasso;
        private readonly UiSegments language, quality;
        private readonly Text sparkValue, roundValue, ringValue, resetLabel;
        private readonly RectTransform tests, closeRect, versionRect;
        private readonly CanvasGroup testsGroup;
        private int versionTaps;
        private float lastTap = -10f;

        public SettingsPanel(UiRoot root) : base(root, "Options", UiRoot.OptionsOrder)
        {
            Image dim = UiKit.FullScreen(CanvasRect, "Dim", UiKit.WithAlpha(UiKit.Navy, 0.7f), false);
            dim.rectTransform.SetAsFirstSibling();

            panel = UiKit.Rect("Panel", Safe);
            UiKit.Place(panel, UiKit.Center, Vector2.zero, new Vector2(PanelWidth, 1000f));
            Image shadow = UiKit.Rounded(panel, "Shadow", UiKit.WithAlpha(UiKit.Navy, 0.7f), 60f);
            UiKit.Stretch(shadow.rectTransform);
            shadow.rectTransform.offsetMin = new Vector2(-4f, -18f);
            shadow.rectTransform.offsetMax = new Vector2(4f, -6f);
            Image edge = UiKit.Rounded(panel, "Edge", UiKit.WithAlpha(UiKit.Light, 0.16f), 59f);
            UiKit.Stretch(edge.rectTransform);
            edge.rectTransform.offsetMin = new Vector2(-3f, -3f);
            edge.rectTransform.offsetMax = new Vector2(3f, 3f);
            panelBg = UiKit.Rounded(panel, "Background", new Color32(0x22, 0x2F, 0x57, 0xFF), 56f);
            UiKit.Stretch(panelBg.rectTransform);

            title = UiKit.Label(panel, "Title", 72, UiKit.Light, TextAnchor.MiddleCenter, true, true);
            float y = -90f;
            UiKit.Place(title.rectTransform, UiKit.TopCenter, new Vector2(0f, y), new Vector2(PanelWidth, 110f));
            y -= 120f;

            sound = Switch(panel, "options.sound", ref y, v => SaveData.SoundOn = v);
            haptics = Switch(panel, "options.haptics", ref y, v => SaveData.HapticsOn = v);
            lasso = Switch(panel, "options.lasso", ref y, v => SaveData.LassoOn = v);
            language = Segments(panel, "options.language", ref y, new[] { "options.lang_fr", "options.lang_en" }, 110f,
                                i => Strings.Language = i);
            Text qLabel = RowLabel(panel, "options.quality", y);
            qLabel.rectTransform.anchoredPosition = new Vector2(qLabel.rectTransform.anchoredPosition.x, y);
            y -= 92f;
            quality = new UiSegments(panel, new Vector2(0f, y), new[] { "options.quality_auto", "options.quality_high", "options.quality_medium", "options.quality_low" },
                                     196f, 92f, i => SaveData.Quality = i);
            y -= RowHeight;

            // Version label (tap 5 times).
            Button version = UiKit.Btn(panel, "Version", new Vector2(420f, 80f), new Color(1f, 1f, 1f, 0f), 30f, 34,
                                       UiKit.WithAlpha(UiKit.Light, 0.55f), OnVersionTap, out versionText);
            versionRect = (RectTransform)version.transform;
            UiKit.Place(versionRect, UiKit.TopCenter, new Vector2(0f, y + 10f), new Vector2(420f, 80f));

            // Hidden test settings (positioned under the version label by Layout).
            tests = UiKit.Rect("TestSettings", panel);
            tests.anchorMin = tests.anchorMax = UiKit.TopCenter;
            tests.pivot = new Vector2(0.5f, 1f);
            tests.sizeDelta = new Vector2(PanelWidth, 560f);
            testsGroup = tests.gameObject.AddComponent<CanvasGroup>();
            float ty = -50f;
            testsTitle = UiKit.Label(tests, "Title", 46, new Color32(0xF5, 0xB7, 0x31, 0xFF), TextAnchor.MiddleCenter);
            UiKit.Place(testsTitle.rectTransform, UiKit.TopCenter, new Vector2(0f, ty), new Vector2(PanelWidth, 70f));
            ty -= 100f;
            sparkValue = Stepper(tests, "options.spark", ty, () => SaveData.SparkFactor -= SaveData.SparkFactorStep,
                                 () => SaveData.SparkFactor += SaveData.SparkFactorStep);
            ty -= RowHeight;
            roundValue = Stepper(tests, "options.round", ty, () => StepRound(-1), () => StepRound(1));
            ty -= RowHeight;
            ringValue = Stepper(tests, "options.ring", ty, () => SaveData.RingDelay -= SaveData.RingDelayStep,
                                () => SaveData.RingDelay += SaveData.RingDelayStep);
            ty -= RowHeight + 10f;
            Button reset = UiKit.Btn(tests, "Reset", new Vector2(420f, 96f), UiKit.NavyLight, 48f, 40, UiKit.Light,
                                     SaveData.ResetTestSettings, out resetLabel);
            UiKit.Place((RectTransform)reset.transform, UiKit.TopCenter, new Vector2(0f, ty), new Vector2(420f, 96f));

            // Close.
            Button close = UiKit.Btn(panel, "Close", new Vector2(460f, 130f), Palette.ColorOf(0), 65f, 56, UiKit.Light, OnClose, out closeLabel);
            closeRect = (RectTransform)close.transform;
            closeRect.anchorMin = closeRect.anchorMax = new Vector2(0.5f, 0f);
            closeRect.pivot = new Vector2(0.5f, 0f);
            closeRect.anchoredPosition = new Vector2(0f, 50f);

            Layout();
        }

        /// <summary>True when the hidden test settings are revealed.</summary>
        public bool TestsRevealed => testsRevealed;

        /// <summary>Reveals the hidden test settings (as five taps on the version label do).</summary>
        public void RevealTests()
        {
            testsRevealed = true;
            Layout();
        }

        public void OnOpened()
        {
            versionTaps = 0;
            Refresh();
            Layout();
        }

        public override void Relabel()
        {
            title.text = Strings.Get("options.title");
            foreach (KeyValuePair<Text, string> kv in rowLabels) kv.Key.text = Strings.Get(kv.Value);
            versionText.text = Strings.Format("options.version", Application.version);
            testsTitle.text = Strings.Get("options.test_settings");
            resetLabel.text = Strings.Get("options.reset");
            closeLabel.text = Strings.Get("options.close");
            language.Relabel();
            quality.Relabel();
            Refresh();
        }

        public override void Tick(float dt)
        {
            // Fit the panel inside the safe area (landscape windows, small screens).
            float availH = Safe.rect.height - 60f, availW = Safe.rect.width - 40f;
            float h = panel.sizeDelta.y, w = panel.sizeDelta.x;
            float s = 1f;
            if (h > 0f && availH > 0f) s = Mathf.Min(s, availH / h);
            if (w > 0f && availW > 0f) s = Mathf.Min(s, availW / w);
            panel.localScale = new Vector3(s, s, 1f);
            ((Image)closeRect.GetComponent<Button>().targetGraphic).color = Palette.ColorAt(Palette.HumanColor);
            sound.Tick(dt);
            haptics.Tick(dt);
            lasso.Tick(dt);
        }

        // ------------------------------------------------------------------------------------------------------------

        private void Refresh()
        {
            sound.Set(SaveData.SoundOn);
            haptics.Set(SaveData.HapticsOn);
            lasso.Set(SaveData.LassoOn);
            language.Select(Strings.Language);
            quality.Select(SaveData.Quality);
            sparkValue.text = Strings.Format("options.factor_value", Strings.Decimal(SaveData.SparkFactor, 1));
            roundValue.text = Strings.Format("options.seconds_value", Strings.Decimal(SaveData.RoundSeconds, 0));
            ringValue.text = Strings.Format("options.seconds_value", Strings.Decimal(SaveData.RingDelay, 0));
        }

        private void Layout()
        {
            float versionY = versionRect.anchoredPosition.y;
            float top = -versionY + 50f;            // distance from the panel top to just under the version label
            float testsH = testsRevealed ? tests.sizeDelta.y : 0f;
            tests.anchoredPosition = new Vector2(0f, -top);
            testsGroup.alpha = testsRevealed ? 1f : 0f;
            testsGroup.interactable = testsRevealed;
            testsGroup.blocksRaycasts = testsRevealed;
            float height = top + testsH + 210f;
            panel.sizeDelta = new Vector2(PanelWidth, height);
        }

        private void OnVersionTap()
        {
            float now = Time.unscaledTime;
            versionTaps = now - lastTap <= VersionTapWindow ? versionTaps + 1 : 1;
            lastTap = now;
            if (versionTaps >= VersionTapsToReveal && !testsRevealed)
            {
                testsRevealed = true;
                Layout();
            }
        }

        private void OnClose()
        {
            if (Root != null) Root.CloseOptions();
        }

        private static void StepRound(int direction)
        {
            float[] choices = SaveData.RoundSecondsChoices;
            float cur = SaveData.RoundSeconds;
            int k = 0;
            for (int i = 0; i < choices.Length; i++) if (Mathf.Abs(choices[i] - cur) < 0.5f) k = i;
            k = Mathf.Clamp(k + direction, 0, choices.Length - 1);
            SaveData.RoundSeconds = choices[k];
        }

        private Text RowLabel(RectTransform parent, string key, float y)
        {
            Text t = UiKit.Label(parent, key, 46, UiKit.Light, TextAnchor.MiddleLeft);
            t.rectTransform.anchorMin = t.rectTransform.anchorMax = new Vector2(0f, 1f);
            t.rectTransform.pivot = new Vector2(0f, 0.5f);
            t.rectTransform.sizeDelta = new Vector2(480f, 80f);
            t.rectTransform.anchoredPosition = new Vector2(64f, y);
            rowLabels.Add(new KeyValuePair<Text, string>(t, key));
            return t;
        }

        private UiSwitch Switch(RectTransform parent, string key, ref float y, System.Action<bool> onChange)
        {
            RowLabel(parent, key, y);
            var sw = new UiSwitch(parent, new Vector2(PanelWidth * 0.5f - 64f - 80f, y), onChange);
            y -= RowHeight;
            return sw;
        }

        private UiSegments Segments(RectTransform parent, string key, ref float y, string[] keys, float width, System.Action<int> onPick)
        {
            RowLabel(parent, key, y);
            float total = keys.Length * width + (keys.Length - 1) * 12f;
            var seg = new UiSegments(parent, new Vector2(PanelWidth * 0.5f - 64f - total * 0.5f, y), keys, width, 84f, onPick);
            y -= RowHeight;
            return seg;
        }

        private Text Stepper(RectTransform parent, string key, float y, UnityEngine.Events.UnityAction minus, UnityEngine.Events.UnityAction plus)
        {
            RowLabel(parent, key, y);
            float right = PanelWidth * 0.5f - 64f;
            Button bp = UiKit.Btn(parent, key + ".plus", new Vector2(84f, 84f), UiKit.NavyLight, 42f, 54, UiKit.Light, plus, out Text pl);
            pl.text = "+";
            UiKit.Place((RectTransform)bp.transform, UiKit.TopCenter, new Vector2(right - 42f, y), new Vector2(84f, 84f));
            Text value = UiKit.Label(parent, key + ".value", 44, UiKit.Light, TextAnchor.MiddleCenter);
            UiKit.Place(value.rectTransform, UiKit.TopCenter, new Vector2(right - 84f - 80f, y), new Vector2(150f, 80f));
            Button bm = UiKit.Btn(parent, key + ".minus", new Vector2(84f, 84f), UiKit.NavyLight, 42f, 54, UiKit.Light, minus, out Text ml);
            ml.text = "-";
            UiKit.Place((RectTransform)bm.transform, UiKit.TopCenter, new Vector2(right - 84f - 160f - 42f, y), new Vector2(84f, 84f));
            return value;
        }
    }

    /// <summary>An on/off pill switch (track + knob), language neutral. Used by the Options and Pause panels.</summary>
    public sealed class UiSwitch
    {
        public const float Width = 150f, Height = 80f;
        private readonly Image track;
        private readonly RectTransform knob;
        private readonly System.Action<bool> onChange;
        private bool on;
        private float knobX;

        public UiSwitch(RectTransform parent, Vector2 topCenterPos, System.Action<bool> onChange)
        {
            this.onChange = onChange;
            Button b = UiKit.Btn(parent, "Switch", new Vector2(Width, Height), UiKit.NavyLight, Height * 0.5f, 0, UiKit.Light, Toggle, out _);
            RectTransform rt = (RectTransform)b.transform;
            UiKit.Place(rt, UiKit.TopCenter, topCenterPos, new Vector2(Width, Height));
            track = (Image)b.targetGraphic;
            Image k = UiKit.Img(rt, "Knob", UiKit.CircleSprite, UiKit.Light);
            knob = k.rectTransform;
            UiKit.Place(knob, UiKit.Center, Vector2.zero, new Vector2(Height - 14f, Height - 14f));
            UiKit.AddShadow(k.gameObject);
            Set(false);
            knob.anchoredPosition = new Vector2(knobX, 0f);
        }

        public bool On => on;

        public void Set(bool value)
        {
            on = value;
            track.color = on ? Palette.ColorAt(Palette.HumanColor) : UiKit.NavyLight;
            knobX = on ? (Width - Height) * 0.5f : -(Width - Height) * 0.5f;
        }

        public void Tick(float dt)
        {
            Vector2 p = knob.anchoredPosition;
            p.x = Mathf.MoveTowards(p.x, knobX, dt * 900f);
            knob.anchoredPosition = p;
            if (on) track.color = Palette.ColorAt(Palette.HumanColor);
        }

        private void Toggle()
        {
            Set(!on);
            onChange?.Invoke(on);
        }
    }

    /// <summary>A row of exclusive pill buttons (Langue FR/EN, Qualité Auto/Haute/Moyenne/Basse).</summary>
    public sealed class UiSegments
    {
        private readonly Image[] bgs;
        private readonly Text[] labels;
        private readonly string[] keys;
        private readonly System.Action<int> onPick;
        private int selected = -1;

        public UiSegments(RectTransform parent, Vector2 topCenterPos, string[] keys, float width, float height, System.Action<int> onPick)
        {
            this.keys = keys;
            this.onPick = onPick;
            bgs = new Image[keys.Length];
            labels = new Text[keys.Length];
            float total = keys.Length * width + (keys.Length - 1) * 12f;
            for (int i = 0; i < keys.Length; i++)
            {
                int index = i;
                Button b = UiKit.Btn(parent, "Segment" + i, new Vector2(width, height), UiKit.NavyLight, height * 0.5f, 38, UiKit.Light,
                                     () => Pick(index), out Text label);
                float x = topCenterPos.x - total * 0.5f + width * 0.5f + i * (width + 12f);
                UiKit.Place((RectTransform)b.transform, UiKit.TopCenter, new Vector2(x, topCenterPos.y), new Vector2(width, height));
                bgs[i] = (Image)b.targetGraphic;
                labels[i] = label;
            }
            Relabel();
        }

        public int Selected => selected;

        public void Relabel()
        {
            for (int i = 0; i < keys.Length; i++) labels[i].text = Strings.Get(keys[i]);
        }

        public void Select(int index)
        {
            selected = index;
            for (int i = 0; i < bgs.Length; i++)
            {
                bool sel = i == index;
                bgs[i].color = sel ? UiKit.Light : UiKit.NavyLight;
                labels[i].color = sel ? UiKit.Navy : UiKit.Light;
            }
        }

        private void Pick(int index)
        {
            Select(index);
            onPick?.Invoke(index);
        }
    }
}
