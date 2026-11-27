// Owned by B4. Contract 15.7: the pause panel (shown while GameDirector.IsPaused): navy dim at 60 %, title "Pause", buttons
// REPRENDRE (SetPaused(false)), RECOMMENCER (StartRound) and MENU (ToMenu), plus the Son and Vibrations switches. The quit
// panel (Menu, Escape / Android back): "Quitter ?" with OUI (Application.Quit) and NON.
using UnityEngine;
using UnityEngine.UI;

namespace PainterIO.Runtime
{
    public sealed class PausePanel : UiScreen
    {
        /// <summary>Title center above the screen center and its rect height (wave C: clear of the HUD timer at every aspect
        /// once the canvas is at least 1920 high, CanvasScaler Expand).</summary>
        public const float TitleY = 470f;
        public const float TitleHeight = 190f;

        private readonly Text title, resumeLabel, restartLabel, menuLabel, soundLabel, hapticsLabel;
        private readonly Image resumeBg;
        private readonly UiSwitch sound, haptics;

        public PausePanel(UiRoot root) : base(root, "Pause", UiRoot.PauseOrder)
        {
            Image dim = UiKit.FullScreen(CanvasRect, "Dim", UiKit.WithAlpha(UiKit.Navy, 0.6f), false);
            dim.rectTransform.SetAsFirstSibling();

            title = UiKit.Label(Safe, "Title", 130, UiKit.Light, TextAnchor.MiddleCenter, true, true);
            UiKit.Place(title.rectTransform, UiKit.Center, new Vector2(0f, TitleY), new Vector2(1000f, TitleHeight));

            RectTransform resume = UiKit.PrimaryButton(Safe, "Resume", new Vector2(640f, 160f), Palette.ColorOf(0), 64, OnResume,
                                                       out resumeBg, out resumeLabel);
            UiKit.Place(resume, UiKit.Center, new Vector2(0f, 190f), new Vector2(640f, 160f));
            Button restart = UiKit.Btn(Safe, "Restart", new Vector2(640f, 136f), UiKit.NavyLight, 68f, 54, UiKit.Light, OnRestart, out restartLabel);
            UiKit.Place((RectTransform)restart.transform, UiKit.Center, new Vector2(0f, 0f), new Vector2(640f, 136f));
            Button menu = UiKit.Btn(Safe, "Menu", new Vector2(640f, 136f), UiKit.NavyLight, 68f, 54, UiKit.Light, OnMenu, out menuLabel);
            UiKit.Place((RectTransform)menu.transform, UiKit.Center, new Vector2(0f, -170f), new Vector2(640f, 136f));

            RectTransform toggles = UiKit.Rect("Toggles", Safe);
            UiKit.Place(toggles, UiKit.Center, new Vector2(0f, -400f), new Vector2(760f, 240f));
            soundLabel = UiKit.Label(toggles, "SoundLabel", 46, UiKit.Light, TextAnchor.MiddleCenter);
            UiKit.Place(soundLabel.rectTransform, UiKit.TopCenter, new Vector2(-190f, -40f), new Vector2(360f, 70f));
            sound = new UiSwitch(toggles, new Vector2(-190f, -130f), v => SaveData.SoundOn = v);
            hapticsLabel = UiKit.Label(toggles, "HapticsLabel", 46, UiKit.Light, TextAnchor.MiddleCenter);
            UiKit.Place(hapticsLabel.rectTransform, UiKit.TopCenter, new Vector2(190f, -40f), new Vector2(360f, 70f));
            haptics = new UiSwitch(toggles, new Vector2(190f, -130f), v => SaveData.HapticsOn = v);
        }

        public override void Relabel()
        {
            title.text = Strings.Get("pause.title");
            resumeLabel.text = Strings.Get("pause.resume");
            restartLabel.text = Strings.Get("pause.restart");
            menuLabel.text = Strings.Get("pause.menu");
            soundLabel.text = Strings.Get("options.sound");
            hapticsLabel.text = Strings.Get("options.haptics");
            sound.Set(SaveData.SoundOn);
            haptics.Set(SaveData.HapticsOn);
        }

        protected override void OnShow()
        {
            sound.Set(SaveData.SoundOn);
            haptics.Set(SaveData.HapticsOn);
        }

        public override void Tick(float dt)
        {
            int h = Session != null && Session.HumanIndex >= 0 ? Session.HumanIndex : 0;
            resumeBg.color = Palette.ColorOf(h);
            sound.Tick(dt);
            haptics.Tick(dt);
        }

        private void OnResume()
        {
            GameDirector d = Director;
            if (d != null) d.SetPaused(false);
        }

        private void OnRestart()
        {
            GameDirector d = Director;
            if (d != null) d.StartRound();
        }

        private void OnMenu()
        {
            GameDirector d = Director;
            if (d != null) d.ToMenu();
        }
    }

    /// <summary>The "Quitter ?" panel (Menu, Escape / Android back): OUI quits the application, NON closes the panel.</summary>
    public sealed class QuitPanel : UiScreen
    {
        private readonly Text title, yesLabel, noLabel;
        private Image noBg;

        public QuitPanel(UiRoot root) : base(root, "Quit", UiRoot.QuitOrder)
        {
            Image dim = UiKit.FullScreen(CanvasRect, "Dim", UiKit.WithAlpha(UiKit.Navy, 0.72f), false);
            dim.rectTransform.SetAsFirstSibling();
            title = UiKit.Label(Safe, "Title", 110, UiKit.Light, TextAnchor.MiddleCenter, true, true);
            UiKit.Place(title.rectTransform, UiKit.Center, new Vector2(0f, 190f), new Vector2(1000f, 170f));
            Button yes = UiKit.Btn(Safe, "Yes", new Vector2(360f, 150f), UiKit.NavyLight, 75f, 60, UiKit.Light, OnYes, out yesLabel);
            UiKit.Place((RectTransform)yes.transform, UiKit.Center, new Vector2(-200f, -40f), new Vector2(360f, 150f));
            Button no = UiKit.Btn(Safe, "No", new Vector2(360f, 150f), Palette.ColorOf(0), 75f, 60, UiKit.Light, OnNo, out noLabel);
            UiKit.Place((RectTransform)no.transform, UiKit.Center, new Vector2(200f, -40f), new Vector2(360f, 150f));
            noBg = (Image)no.targetGraphic;
        }

        public override void Tick(float dt)
        {
            noBg.color = Palette.ColorAt(Palette.HumanColor);
        }

        public override void Relabel()
        {
            title.text = Strings.Get("quit.title");
            yesLabel.text = Strings.Get("quit.yes");
            noLabel.text = Strings.Get("quit.no");
        }

        private static void OnYes()
        {
            SaveData.Flush();
            Debug.Log("[PainterIO] quit requested from the menu");
            Application.Quit(0);
        }

        private void OnNo()
        {
            if (Root != null) Root.HideQuitPanel();
        }
    }
}
