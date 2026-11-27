// Owned by B4. Contract 11.1 entry point of the uGUI (15: menu, HUD, results, tutorial, options, pause and quit panels).
// Everything is built in code: one Screen Space Overlay canvas per screen (UiKit.CreateCanvas), an EventSystem with
// InputSystemUIInputModule, and plain C# screen classes driven by this component's LateUpdate. Screens are shown and hidden
// by toggling their Canvas and CanvasGroup (never the GameObject).
//
// Integration API (see the B4 report):
// - UiRoot.Instance: the live UiRoot (null before GameDirector.Awake builds it).
// - HandleBack(): the Escape / Android back action in Menu (closes Options, else toggles the "Quitter ?" panel). SteeringInput
//   (B3) may call it; UiRoot also reacts to Keyboard.escapeKey in Menu itself, and both paths are deduplicated per frame,
//   so calling it from B3 is safe. ShowQuitPanel / HideQuitPanel / IsQuitPanelOpen / IsOptionsOpen are also public.
// - Every UI button click calls Sfx.PlayUiClick and raises UiRoot.ButtonClicked (static event).
// - Every toast that becomes visible calls Sfx.PlayToastTick and raises UiRoot.ToastShown (static event, with its text).
using System;
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.UI;

namespace PainterIO.Runtime
{
    [DefaultExecutionOrder(300)]
    public sealed class UiRoot : MonoBehaviour
    {
        public const int HudOrder = 10;
        public const int TutorialOrder = 15;
        public const int MenuOrder = 20;
        public const int ResultsOrder = 30;
        public const int OptionsOrder = 40;
        public const int PauseOrder = 50;
        public const int QuitOrder = 60;

        /// <summary>The live UiRoot (null before GameDirector.Awake built it, or after it was destroyed).</summary>
        public static UiRoot Instance { get; private set; }

        /// <summary>Raised on every UI button click, before its action (B5: UI click sound).</summary>
        public static event Action ButtonClicked;

        /// <summary>Raised when a toast becomes visible, with its text (B5: toast tick).</summary>
        public static event Action<string> ToastShown;

        private GameDirector director;
        private GameSession boundSession;
        private readonly List<UiScreen> screens = new List<UiScreen>();
        private readonly HashSet<string> failedScreens = new HashSet<string>();
        private bool relabelPending = true;
        private bool optionsOpen, quitOpen, europeOpen;
        private EuropeScreen europe;
        private int backFrame = -1;
        private GameState stateLastFrame = GameState.Boot;
        private bool escapeErrorLogged;

        public GameDirector Director => director;
        public Hud Hud { get; private set; }
        public MenuScreen Menu { get; private set; }
        public ResultsScreen Results { get; private set; }
        public TutorialOverlay Tutorial { get; private set; }
        public SettingsPanel Settings { get; private set; }
        public PausePanel Pause { get; private set; }
        public QuitPanel Quit { get; private set; }

        /// <summary>
        /// Dev aid for screenshots: "-uidemo options,quit,pause,board,hint,selfcross" forces those screens visible (visual only: the pause
        /// overlay does not pause, Options and quit show in Menu, the leaderboard starts expanded, the step 0 steering hint shows during play,
        /// TutorialOverlay shows the self-crossing bubble during play) so a DevShot run can
        /// capture them. Never used by the game itself.
        /// </summary>
        public static bool DemoShows(string screen)
        {
            if (demoScreens == null)
            {
                string v = LaunchArgs.Value("-uidemo");
                demoScreens = string.IsNullOrEmpty(v) || v.StartsWith("-", StringComparison.Ordinal)
                    ? new string[0]
                    : v.ToLowerInvariant().Split(',');
            }
            return Array.IndexOf(demoScreens, screen) >= 0;
        }

        private static string[] demoScreens;

        public bool IsQuitPanelOpen => quitOpen;
        public bool IsOptionsOpen => optionsOpen;

        public static UiRoot Create(GameDirector d)
        {
            var go = new GameObject("UiRoot");
            var ui = go.AddComponent<UiRoot>();
            ui.director = d;
            Instance = ui;
            ui.Guard("EventSystem", () => EnsureEventSystem(go.transform));
            ui.Build("Hud", () => ui.Hud = new Hud(ui));
            ui.Build("Tutorial", () => ui.Tutorial = new TutorialOverlay(ui));
            ui.Build("Menu", () => ui.Menu = new MenuScreen(ui));
            ui.Build("Results", () => ui.Results = new ResultsScreen(ui));
            ui.Build("Settings", () => ui.Settings = new SettingsPanel(ui));
            ui.Build("Pause", () => ui.Pause = new PausePanel(ui));
            ui.Build("Quit", () => ui.Quit = new QuitPanel(ui));
            if (d != null)
            {
                d.SessionStarted += ui.OnSessionStarted;
                d.StateChanged += ui.OnStateChanged;
                d.PausedChanged += ui.OnPausedChanged;
            }
            SaveData.Changed += ui.OnSaveChanged;
            ui.RelabelAll();
            ui.ApplyVisibility(true);
            return ui;
        }

        private void OnDestroy()
        {
            SaveData.Changed -= OnSaveChanged;
            if (boundSession != null) boundSession.EventRaised -= OnSimEvent;
            boundSession = null;
            if (director != null)
            {
                director.SessionStarted -= OnSessionStarted;
                director.StateChanged -= OnStateChanged;
                director.PausedChanged -= OnPausedChanged;
            }
            if (Instance == this) Instance = null;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Public API.

        /// <summary>
        /// Escape / Android back in Menu: closes Options if open, else toggles the "Quitter ?" panel. Deduplicated per
        /// frame (UiRoot's own Escape handling and SteeringInput may both call it). Returns false outside Menu.
        /// </summary>
        public bool HandleBack()
        {
            if (director == null || director.State != GameState.Menu) return false;
            if (backFrame == Time.frameCount) return true;
            backFrame = Time.frameCount;
            if (europeOpen) CloseEurope();
            else if (optionsOpen) CloseOptions();
            else if (quitOpen) HideQuitPanel();
            else
            {
                quitOpen = true;
                ApplyVisibility(false);
            }
            return true;
        }

        public void OpenEurope()
        {
            if (director == null || director.State != GameState.Menu) return;
            if (europe == null) europe = new EuropeScreen(this);
            europeOpen = true;
            ApplyVisibility(false);
        }

        public void CloseEurope()
        {
            europeOpen = false;
            ApplyVisibility(false);
        }

        /// <summary>Opens the "Quitter ?" panel (Menu only; closes Options). Deduplicated per frame with HandleBack.</summary>
        public void ShowQuitPanel()
        {
            if (director == null || director.State != GameState.Menu) return;
            if (backFrame == Time.frameCount) return;
            backFrame = Time.frameCount;
            if (optionsOpen) CloseOptions();
            quitOpen = true;
            ApplyVisibility(false);
        }

        public void HideQuitPanel()
        {
            quitOpen = false;
            ApplyVisibility(false);
        }

        public void OpenOptions()
        {
            if (director != null && director.State != GameState.Menu) return;
            quitOpen = false;
            optionsOpen = true;
            if (Settings != null) Settings.OnOpened();
            ApplyVisibility(false);
        }

        public void CloseOptions()
        {
            if (!optionsOpen) return;
            optionsOpen = false;
            SaveData.Flush();
            ApplyVisibility(false);
        }

        internal static void RaiseButtonClicked()
        {
            try
            {
                Sfx.PlayUiClick();   // B5's UI click (no-op without Sfx or with sound off)
            }
            catch (Exception e)
            {
                LogSoundOnce(e);
            }
            Action handler = ButtonClicked;
            if (handler == null) return;
            foreach (Delegate d in handler.GetInvocationList())
            {
                try
                {
                    ((Action)d)();
                }
                catch (Exception e)
                {
                    Debug.LogError("[PainterIO] UiRoot.ButtonClicked subscriber failed: " + e);
                }
            }
        }

        internal static void RaiseToastShown(string text)
        {
            try
            {
                Sfx.PlayToastTick();   // B5's toast tick
            }
            catch (Exception e)
            {
                LogSoundOnce(e);
            }
            Action<string> handler = ToastShown;
            if (handler == null) return;
            foreach (Delegate d in handler.GetInvocationList())
            {
                try
                {
                    ((Action<string>)d)(text);
                }
                catch (Exception e)
                {
                    Debug.LogError("[PainterIO] UiRoot.ToastShown subscriber failed: " + e);
                }
            }
        }

        private static bool soundErrorLogged;

        private static void LogSoundOnce(Exception e)
        {
            if (soundErrorLogged) return;
            soundErrorLogged = true;
            Debug.LogWarning("[PainterIO] UI sound failed: " + e.Message);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Director and session events.

        private void OnSessionStarted(GameSession s)
        {
            if (boundSession != null && boundSession != s) boundSession.EventRaised -= OnSimEvent;
            if (s != null)
            {
                s.EventRaised -= OnSimEvent;
                s.EventRaised += OnSimEvent;
            }
            boundSession = s;
            if (Hud != null) Safe("Hud", () => Hud.Bind(s));
            if (Tutorial != null) Safe("Tutorial", () => Tutorial.Bind(s));
        }

        private void OnStateChanged(GameState state)
        {
            if (state != GameState.Menu)
            {
                optionsOpen = false;
                quitOpen = false;
            }
            if (state == GameState.Results && Results != null) Safe("Results", () => Results.ShowOutcome(director != null ? director.LastOutcome : null));
            ApplyVisibility(false);
            // Gate B: never keep a selected Selectable into play, or arrows / WASD would also navigate the UI.
            if (state == GameState.Playing) UiKit.Deselect();
        }

        private void OnPausedChanged(bool paused)
        {
            ApplyVisibility(false);
            if (!paused) UiKit.Deselect();
        }

        private void OnSaveChanged()
        {
            relabelPending = true;
        }

        private void OnSimEvent(SimEvent e)
        {
            GameSession s = director != null ? director.Session : null;
            if (s == null || s != boundSession || s.IsAttract || e == null) return;
            bool lassoBubble = false;
            if (Tutorial != null)
            {
                try
                {
                    lassoBubble = Tutorial.OnSimEvent(s, e);
                }
                catch (Exception ex)
                {
                    LogScreenOnce("Tutorial.OnSimEvent", ex);
                }
            }
            if (Hud != null)
            {
                try
                {
                    Hud.OnSimEvent(s, e, lassoBubble);
                }
                catch (Exception ex)
                {
                    LogScreenOnce("Hud.OnSimEvent", ex);
                }
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Frame.

        private void Update()
        {
            try
            {
                Keyboard kb = Keyboard.current;
                bool esc = kb != null && kb.escapeKey.wasPressedThisFrame;
                // Only when the state was already Menu last frame: an Escape that just took Results back to the menu
                // (SteeringInput) must not also open the quit panel.
                if (esc && director != null && director.State == GameState.Menu && stateLastFrame == GameState.Menu) HandleBack();
            }
            catch (Exception e)
            {
                if (!escapeErrorLogged)
                {
                    escapeErrorLogged = true;
                    Debug.LogError("[PainterIO] UiRoot escape handling failed: " + e);
                }
            }
        }

        private void LateUpdate()
        {
            float dt = Mathf.Min(Time.unscaledDeltaTime, 0.1f);
            if (relabelPending) RelabelAll();
            ApplyVisibility(false);
            for (int i = 0; i < screens.Count; i++)
            {
                UiScreen sc = screens[i];
                try
                {
                    sc.Tick(dt);
                    sc.UpdateFade(dt);
                }
                catch (Exception e)
                {
                    LogScreenOnce(sc.Name, e);
                }
            }
            stateLastFrame = director != null ? director.State : GameState.Boot;
        }

        private void RelabelAll()
        {
            relabelPending = false;
            for (int i = 0; i < screens.Count; i++)
            {
                UiScreen sc = screens[i];
                try
                {
                    sc.Relabel();
                }
                catch (Exception e)
                {
                    LogScreenOnce(sc.Name + ".Relabel", e);
                }
            }
        }

        private void ApplyVisibility(bool instant)
        {
            GameState st = director != null ? director.State : GameState.Boot;
            bool paused = director != null && director.IsPaused;
            if (st != GameState.Menu)
            {
                optionsOpen = false;
                quitOpen = false;
                europeOpen = false;
            }
            else if (DemoShows("options"))
            {
                if (!optionsOpen && Settings != null) Settings.RevealTests();
                optionsOpen = true;
            }
            else if (DemoShows("quit")) quitOpen = true;
            Show(Menu, (st == GameState.Menu || st == GameState.Boot) && !europeOpen, instant);
            Show(europe, st == GameState.Menu && europeOpen, instant);
            Show(Hud, st == GameState.Playing, instant);
            Show(Tutorial, st == GameState.Playing, instant);
            Show(Results, st == GameState.Results, instant);
            Show(Settings, st == GameState.Menu && optionsOpen, instant);
            Show(Pause, st == GameState.Playing && (paused || DemoShows("pause")), instant);
            Show(Quit, st == GameState.Menu && quitOpen, instant);
            if (Menu != null) Menu.SetInteractable(!optionsOpen && !quitOpen && !europeOpen);
        }

        private static void Show(UiScreen s, bool visible, bool instant)
        {
            if (s != null) s.SetVisible(visible, instant);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Construction helpers.

        internal void Register(UiScreen s)
        {
            if (s != null && !screens.Contains(s)) screens.Add(s);
        }

        private void Build(string name, Action build)
        {
            try
            {
                build();
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] UI " + name + " failed: " + e);
            }
        }

        private void Guard(string name, Action action)
        {
            try
            {
                action();
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] UI " + name + " failed: " + e);
            }
        }

        private void Safe(string name, Action action)
        {
            try
            {
                action();
            }
            catch (Exception e)
            {
                LogScreenOnce(name, e);
            }
        }

        private void LogScreenOnce(string name, Exception e)
        {
            if (failedScreens.Add(name)) Debug.LogError("[PainterIO] UI " + name + " failed: " + e);
        }

        private static void EnsureEventSystem(Transform parent)
        {
            EventSystem es = EventSystem.current;
            if (es == null) es = FindAnyObjectByType<EventSystem>();
            if (es == null)
            {
                var go = new GameObject("EventSystem");
                go.transform.SetParent(parent, false);
                es = go.AddComponent<EventSystem>();
            }
            var legacy = es.GetComponent<StandaloneInputModule>();
            if (legacy != null) Destroy(legacy);
            if (es.GetComponent<InputSystemUIInputModule>() == null) es.gameObject.AddComponent<InputSystemUIInputModule>();
            es.sendNavigationEvents = false;
        }
    }

    /// <summary>
    /// Base of the code-built screens: one canvas (with CanvasGroup and SafeArea child), shown and hidden with a short alpha
    /// fade by toggling the Canvas and the CanvasGroup only.
    /// </summary>
    public abstract class UiScreen
    {
        public const float FadeSeconds = 0.16f;

        protected readonly UiRoot Root;
        public readonly string Name;
        public readonly Canvas Canvas;
        public readonly CanvasGroup Group;
        public readonly RectTransform Safe;
        public readonly RectTransform CanvasRect;
        private float alpha;

        public bool Visible { get; private set; }

        protected UiScreen(UiRoot root, string name, int sortingOrder)
        {
            Root = root;
            Name = name;
            Canvas = UiKit.CreateCanvas(root.transform, name, sortingOrder, out CanvasGroup group, out RectTransform safe);
            Group = group;
            Safe = safe;
            CanvasRect = (RectTransform)Canvas.transform;
            Canvas.enabled = false;
            Group.alpha = 0f;
            Group.interactable = false;
            Group.blocksRaycasts = false;
            root.Register(this);
        }

        protected GameDirector Director => Root != null ? Root.Director : null;

        protected GameSession Session => Director != null ? Director.Session : null;

        /// <summary>False keeps the screen visible but ignores input (results guard, modal on top).</summary>
        protected virtual bool AcceptsInput => true;

        /// <summary>False for overlays that must never block steering (tutorial).</summary>
        protected virtual bool BlocksRaycasts => true;

        public void SetVisible(bool visible, bool instant)
        {
            if (visible != Visible)
            {
                Visible = visible;
                if (visible)
                {
                    Canvas.enabled = true;
                    OnShow();
                }
                else OnHide();
            }
            if (instant)
            {
                alpha = Visible ? 1f : 0f;
                ApplyAlpha();
            }
        }

        public void UpdateFade(float dt)
        {
            float target = Visible ? 1f : 0f;
            alpha = Mathf.MoveTowards(alpha, target, dt / FadeSeconds);
            ApplyAlpha();
        }

        private void ApplyAlpha()
        {
            Group.alpha = alpha;
            Group.blocksRaycasts = Visible && BlocksRaycasts;
            Group.interactable = Visible && AcceptsInput;
            if (!Visible && alpha <= 0f && Canvas.enabled) Canvas.enabled = false;
        }

        protected virtual void OnShow() { }

        protected virtual void OnHide() { }

        public virtual void Relabel() { }

        public virtual void Tick(float dt) { }
    }
}
