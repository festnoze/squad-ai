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
    /// Title screen and pause menu (docs/CONTRACT_M3.md 6).
    /// - The title shows the game title (Strings.Title), Jouer, Quitter and the author line over the first level of
    ///   levels.json, with the camera in a slow orbit. Main shows it at start only in a player and not under
    ///   --probe; a test may call <see cref="ShowTitle"/>. Editor runs never see it by themselves.
    /// - The pause menu (Escape or gamepad Start, read by GameState) shows PAUSE, Reprendre, Recommencer and
    ///   Menu principal.
    /// While a menu is open the game is paused (no fixed step rule runs, the audio listener pauses), the cursor
    /// is free and the HUD Canvas is disabled. Buttons are uGUI Buttons driven by the InputSystemUIInputModule:
    /// arrows and Enter, the gamepad and the mouse all work. Navigation is explicit inside each panel, so the
    /// arrows never reach a button of a hidden panel.
    /// M3.1: a panel's default button is selected one frame after the panel opens, so the Enter that opened it
    /// (the end screen's button opens the title) can never also submit the new panel's button; and a lost
    /// selection (a click on nothing) comes back to the default button, so the keyboard always has a target.
    /// M5 (docs/CONTRACT_M5_v3.md 6 and 15.10, CONTRACT_M5 16.10): the title gains "Niveaux" between Jouer and Quitter,
    /// which opens the level select (<see cref="LevelSelect"/>), a page of the title screen: <see cref="TitleOpen"/> stays
    /// true under it, so the game stays paused and a pause press is still ignored; Retour, Escape or gamepad B
    /// (<see cref="InputReader.BackPressed"/>) come back to the title. Jouer starts the first level that is unlocked but
    /// not won (<see cref="SaveStore.FirstUnwonLevel"/>). The record line under the win panel (<see cref="RecordLine"/>)
    /// is built here too; it records every win in the save.
    /// Credits page (2026-11-19): "Crédits" on the title, between Options and Quitter, opens a scrollable page of
    /// <see cref="Credits.All"/> (the licence attributions of docs/LICENSES.md); Retour, Escape or gamepad B come back.
    /// </summary>
    public sealed class Menu : MonoBehaviour
    {
        public bool IsOpen => TitleOpen || PauseOpen;

        /// <summary>The title screen is up: its main page, or the level select (<see cref="LevelSelectOpen"/>).</summary>
        public bool TitleOpen { get; private set; }
        public bool PauseOpen { get; private set; }

        /// <summary>The title's main page (Jouer, Niveaux, Quitter) shows: the title is up and the level select is not.</summary>
        public bool TitlePageShown => titleCanvas != null && titleCanvas.enabled;

        /// <summary>True on the frame a menu closed: its Enter must not also act on the game (GameState reads it).</summary>
        public bool ClosedThisFrame => closedFrame == Time.frameCount;

        /// <summary>
        /// The cursor must stay free: a menu is open, or the end, win or fail panel offers its own buttons (M8 touch
        /// redesign: Retry, Replay, Next level and Menu need a visible mouse pointer to be clickable, not just tappable).
        /// </summary>
        public bool WantsCursor => IsOpen || (Hud != null && (Hud.EndVisible || Hud.FailVisible || Hud.WinButtonsVisible));

        /// <summary>
        /// M3.1: the end screen leads back to the title (a player) instead of restarting the first level (the
        /// editor, where the title never shows by itself). Tests set it to run the player branch in the editor.
        /// </summary>
        public bool TitleAfterEnd { get; set; }

        public Button PlayButton { get; private set; }
        public Button QuitButton { get; private set; }
        public Button ResumeButton { get; private set; }
        public Button RestartButton { get; private set; }
        public Button MainMenuButton { get; private set; }

        // ----- M5 (docs/CONTRACT_M5.md 16.12): the level select and the record line. -----

        /// <summary>"Niveaux" on the title, between Jouer and Quitter.</summary>
        public Button LevelsButton { get; private set; }

        /// <summary>The level select is open (a page of the title: <see cref="TitleOpen"/> is true as well).</summary>
        public bool LevelSelectOpen { get; private set; }

        /// <summary>The level select page.</summary>
        public LevelSelect LevelSelect { get; private set; }

        /// <summary>The record line under the win panel; it records every win in the save.</summary>
        public RecordLine RecordLine { get; private set; }

        // ----- M6 (docs/CONTRACT_M6.md 2.1): Options, a page reachable from the title's main page and from the pause menu. -----

        /// <summary>Options is open: a page of whichever menu opened it (<see cref="TitleOpen"/> or <see cref="PauseOpen"/> stays true under it).</summary>
        public bool OptionsOpen { get; private set; }

        public Button TitleOptionsButton { get; private set; }
        public Button PauseOptionsButton { get; private set; }
        public Button OptionsSensitivityButton { get; private set; }
        public Button OptionsVolumeButton { get; private set; }
        /// <summary>Audio overhaul: the Music row, right under Volume (0 to 100 % by 10).</summary>
        public Button OptionsMusicButton { get; private set; }
        public Button OptionsConeButton { get; private set; }
        /// <summary>M7 walls pass: Murs / Walls, cycling Lowered, See-through, Both, Off (applied at once).</summary>
        public Button OptionsWallsButton { get; private set; }
        /// <summary>M7 walls pass: the wall opacity of See-through and Both, cycling 10, 20, 35, 50 % (dimmed otherwise).</summary>
        public Button OptionsWallOpacityButton { get; private set; }
        /// <summary>M7 (docs/CONTRACT_M7.md 1.4): Qualité, cycling Bas, Moyen, Haut.</summary>
        public Button OptionsQualityButton { get; private set; }
        /// <summary>M7 design (CONTRACT_M7 4.1): the Difficulté row (Facile, Normal, Difficile; applies at the next level load).</summary>
        public Button OptionsDifficultyButton { get; private set; }
        /// <summary>The Language / Langue row (English, Français; applied at once).</summary>
        public Button OptionsLanguageButton { get; private set; }
        public Button OptionsResetButton { get; private set; }
        public Button OptionsBackButton { get; private set; }

        private Canvas optionsCanvas;
        private Text optionsSensitivityText;
        private Text optionsVolumeText;
        private Text optionsMusicText;
        private Text optionsConeText;
        private Text optionsWallsText;
        private Text optionsWallOpacityText;
        private Text optionsQualityText;
        private Text optionsDifficultyText;
        private Text optionsLanguageText;
        /// <summary>The Language row's icon: the flag of the chosen language (UiIconLibrary.LanguageFlag), swapped live.</summary>
        public Image OptionsLanguageIcon { get; private set; }
        // True when Options was opened from the pause menu (Retour then goes back there, not to the title).
        private bool optionsFromPause;

        // ----- Credits page (2026-11-19): reachable from the title's main page only, its lines are Core.Credits. -----

        /// <summary>The Credits page is open (a page of the title: <see cref="TitleOpen"/> stays true under it).</summary>
        public bool CreditsOpen { get; private set; }

        /// <summary>"Crédits" on the title, between Options and Quitter (Quitter stays last).</summary>
        public Button TitleCreditsButton { get; private set; }

        /// <summary>Retour on the Credits page, its only button (the default selection; up and down scroll the page).</summary>
        public Button CreditsBackButton { get; private set; }

        /// <summary>The Credits page's scroll view (mouse wheel, drag, touch swipe, its scrollbar, up and down).</summary>
        public ScrollRect CreditsScroll { get; private set; }

        private Canvas creditsCanvas;
        // One label per Core.Credits.All entry, in order (relabelled in place when the language changes).
        private readonly List<Text> creditsLines = new List<Text>();

        /// <summary>Crédits: opens the Credits page over the title's main page, scrolled to the top (ignored otherwise).</summary>
        public void OpenCredits()
        {
            if (!TitleOpen || LevelSelectOpen || OptionsOpen || CreditsOpen || creditsCanvas == null)
            {
                return;
            }
            CancelLevelSelectLoad();
            CreditsOpen = true;
            RefreshCreditsTexts();
            CreditsScroll.StopMovement();
            CreditsScroll.content.anchoredPosition = Vector2.zero;
            Apply();
            SelectLater(null);
        }

        /// <summary>Retour, Escape or gamepad B: from the Credits page back to the title's main page, on Crédits.</summary>
        public void CloseCredits()
        {
            if (!CreditsOpen)
            {
                return;
            }
            CreditsOpen = false;
            Apply();
            SelectLater(TitleCreditsButton);
        }

        /// <summary>
        /// Scrolls the Credits page by <paramref name="units"/> reference units (positive: down the list, toward the end),
        /// clamped to its ends; nothing when the page is closed or its lines all fit.
        /// </summary>
        public void ScrollCredits(float units)
        {
            if (!CreditsOpen || CreditsScroll == null)
            {
                return;
            }
            Canvas.ForceUpdateCanvases();
            float range = CreditsScroll.content.rect.height - CreditsScroll.viewport.rect.height;
            if (range <= 0f)
            {
                return;
            }
            CreditsScroll.StopMovement();
            CreditsScroll.verticalNormalizedPosition = Mathf.Clamp01(CreditsScroll.verticalNormalizedPosition - units / range);
        }

        /// <summary>Opens Options over the title's main page or the pause menu; ignored otherwise (the level select open,
        /// already open, or neither menu up).</summary>
        public void OpenOptions()
        {
            bool fromTitle = TitleOpen && !LevelSelectOpen && !CreditsOpen;
            if (OptionsOpen || (!fromTitle && !PauseOpen))
            {
                return;
            }
            CancelLevelSelectLoad();
            optionsFromPause = PauseOpen;
            OptionsOpen = true;
            RefreshOptionsTexts();
            Apply();
            SelectLater(null);
        }

        /// <summary>Retour, Escape or gamepad B: closes Options, back to whichever menu opened it.</summary>
        public void CloseOptions()
        {
            if (!OptionsOpen)
            {
                return;
            }
            OptionsOpen = false;
            Apply();
            SelectLater(optionsFromPause ? PauseOptionsButton : TitleOptionsButton);
        }

        private void CycleSensitivity()
        {
            SaveOptions o = SaveStore.Options;
            float next = o.Sensitivity + Tuning.SensitivityStep;
            if (next > Tuning.SensitivityMax + 1e-3f)
            {
                next = Tuning.SensitivityMin;
            }
            SaveStore.SetOptions(new SaveOptions { Sensitivity = next, Volume = o.Volume, Music = o.Music, Cone = o.Cone, Quality = o.Quality, Difficulty = o.Difficulty, Language = o.Language, Walls = o.Walls, WallOpacity = o.WallOpacity });
            RefreshOptionsTexts();
        }

        private void CycleVolume()
        {
            SaveOptions o = SaveStore.Options;
            int next = o.Volume + Tuning.VolumeStep;
            if (next > Tuning.VolumeMax)
            {
                next = Tuning.VolumeMin;
            }
            SaveStore.SetOptions(new SaveOptions { Sensitivity = o.Sensitivity, Volume = next, Music = o.Music, Cone = o.Cone, Quality = o.Quality, Difficulty = o.Difficulty, Language = o.Language, Walls = o.Walls, WallOpacity = o.WallOpacity });
            RefreshOptionsTexts();
        }

        // Audio overhaul: the music's own level, 0 to 100 % by 10, then back to 0 (MusicPlayer reads it every frame).
        private void CycleMusic()
        {
            SaveOptions o = SaveStore.Options;
            int next = o.Music + Tuning.MusicStep;
            if (next > Tuning.MusicMax)
            {
                next = Tuning.MusicMin;
            }
            SaveStore.SetOptions(new SaveOptions
            {
                Sensitivity = o.Sensitivity, Volume = o.Volume, Music = next, Cone = o.Cone, Quality = o.Quality, Difficulty = o.Difficulty,
                Language = o.Language, Walls = o.Walls, WallOpacity = o.WallOpacity,
            });
            RefreshOptionsTexts();
        }

        private void ToggleCone()
        {
            SaveOptions o = SaveStore.Options;
            string next = o.Cone == SaveOptions.ConeAlways ? SaveOptions.ConeNever : SaveOptions.ConeAlways;
            SaveStore.SetOptions(new SaveOptions { Sensitivity = o.Sensitivity, Volume = o.Volume, Music = o.Music, Cone = next, Quality = o.Quality, Difficulty = o.Difficulty, Language = o.Language, Walls = o.Walls, WallOpacity = o.WallOpacity });
            RefreshOptionsTexts();
        }

        // M7 (CONTRACT_M7 1.4): Bas, Moyen, Haut, from the tier in use (the platform default when none was chosen);
        // SaveStore.SetOptions applies it at once (QualityTier).
        private void CycleQuality()
        {
            SaveOptions o = SaveStore.Options;
            string next = SaveOptions.NextQuality(o.QualityFor(Application.isMobilePlatform));
            SaveStore.SetOptions(new SaveOptions { Sensitivity = o.Sensitivity, Volume = o.Volume, Music = o.Music, Cone = o.Cone, Quality = next, Difficulty = o.Difficulty, Language = o.Language, Walls = o.Walls, WallOpacity = o.WallOpacity });
            RefreshOptionsTexts();
        }

        // M7 design (CONTRACT_M7 4.1): Facile, Normal, Difficile; the level in play keeps its own until the next load.
        private void CycleDifficulty()
        {
            SaveOptions o = SaveStore.Options;
            SaveStore.SetOptions(new SaveOptions
            {
                Sensitivity = o.Sensitivity, Volume = o.Volume, Music = o.Music, Cone = o.Cone, Quality = o.Quality, Difficulty = DifficultyDef.Next(o.DifficultyId),
                Language = o.Language, Walls = o.Walls, WallOpacity = o.WallOpacity,
            });
            RefreshOptionsTexts();
        }

        // English and Français, applied at once: SaveStore.SetOptions switches Strings, whose LanguageChanged relabels every view.
        private void CycleLanguage()
        {
            SaveOptions o = SaveStore.Options;
            string next = o.LanguageId == Strings.French ? Strings.English : Strings.French;
            SaveStore.SetOptions(new SaveOptions
            {
                Sensitivity = o.Sensitivity, Volume = o.Volume, Music = o.Music, Cone = o.Cone, Quality = o.Quality, Difficulty = o.Difficulty, Language = next, Walls = o.Walls, WallOpacity = o.WallOpacity,
            });
            RefreshOptionsTexts();
        }

        // M7 walls pass (product owner, 2026-11-19): Lowered, See-through, Both, Off; the wall fader reads it every frame,
        // so it applies at once over the level in play.
        private void CycleWalls()
        {
            SaveOptions o = SaveStore.Options;
            SaveStore.SetOptions(new SaveOptions
            {
                Sensitivity = o.Sensitivity, Volume = o.Volume, Music = o.Music, Cone = o.Cone, Quality = o.Quality, Difficulty = o.Difficulty,
                Language = o.Language, Walls = SaveOptions.NextWalls(o.Walls), WallOpacity = o.WallOpacity,
            });
            RefreshOptionsTexts();
        }

        // M7 walls pass: 10, 20, 35, 50 %, then 10 % again; used by See-through and Both (dimmed otherwise, still cycles).
        private void CycleWallOpacity()
        {
            SaveOptions o = SaveStore.Options;
            SaveStore.SetOptions(new SaveOptions
            {
                Sensitivity = o.Sensitivity, Volume = o.Volume, Music = o.Music, Cone = o.Cone, Quality = o.Quality, Difficulty = o.Difficulty,
                Language = o.Language, Walls = o.Walls, WallOpacity = SaveOptions.NextWallOpacity(o.WallOpacity),
            });
            RefreshOptionsTexts();
        }

        private static string WallsLabel(string walls)
        {
            return walls == SaveOptions.WallsSeeThrough ? Strings.OptionsWallsSeeThrough
                : walls == SaveOptions.WallsBoth ? Strings.OptionsWallsBoth
                : walls == SaveOptions.WallsNone ? Strings.OptionsWallsNone : Strings.OptionsWallsLowered;
        }

        /// <summary>
        /// Strings.LanguageChanged: every label that shows a table string verbatim is translated in place (menus, HUD, hints,
        /// touch buttons), then the views whose lines are formatted or composed rebuild them (the options rows, the intro card
        /// and its people, the end panels, the record line, the level select).
        /// </summary>
        private void OnLanguageChanged(string previous)
        {
            foreach (Text label in FindObjectsByType<Text>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                if (label != null && Strings.TryTranslate(label.text, previous, out string translated))
                {
                    label.text = translated;
                }
            }
            RefreshOptionsTexts();
            RefreshCreditsTexts();
            if (Hud != null)
            {
                Hud.Relocalize();
            }
            if (RecordLine != null)
            {
                RecordLine.Relocalize();
            }
            if (LevelSelectOpen && LevelSelect != null)
            {
                LevelSelect.Refresh();
            }
        }

        private void OnDestroy()
        {
            Strings.LanguageChanged -= OnLanguageChanged;
        }

        // LOADDOTS: a disabled behaviour loses its coroutines; never leave the dots or the loading flag behind.
        private void OnDisable()
        {
            CancelLevelSelectLoad();
        }

        private static string QualityLabel(string quality)
        {
            return quality == SaveOptions.QualityLow ? Strings.OptionsQualityLow
                : quality == SaveOptions.QualityMedium ? Strings.OptionsQualityMedium : Strings.OptionsQualityHigh;
        }

        private void ResetOptionsClicked()
        {
            SaveStore.ResetOptions();
            RefreshOptionsTexts();
        }

        private void RefreshOptionsTexts()
        {
            SaveOptions o = SaveStore.Options;
            if (optionsSensitivityText != null)
            {
                optionsSensitivityText.text = string.Format(Strings.OptionsSensitivity,
                    o.Sensitivity.ToString("0.00", System.Globalization.CultureInfo.InvariantCulture));
            }
            if (optionsVolumeText != null)
            {
                optionsVolumeText.text = string.Format(Strings.OptionsVolume, o.Volume);
            }
            if (optionsMusicText != null)
            {
                optionsMusicText.text = string.Format(Strings.OptionsMusic, o.Music);
            }
            if (optionsConeText != null)
            {
                optionsConeText.text = string.Format(Strings.OptionsCone,
                    o.Cone == SaveOptions.ConeAlways ? Strings.OptionsConeAlways : Strings.OptionsConeNever);
            }
            if (optionsWallsText != null)
            {
                optionsWallsText.text = string.Format(Strings.OptionsWalls, WallsLabel(o.Walls));
            }
            if (optionsWallOpacityText != null)
            {
                optionsWallOpacityText.text = string.Format(Strings.OptionsWallOpacity, o.WallOpacity);
                // Dimmed while the look in use ignores it (Lowered, Off): still selectable and cycling, so the chain stays whole.
                Color ink = TitleInk;
                ink.a = o.WallOpacityApplies ? 1f : Tuning.OptionsUnusedAlpha;
                optionsWallOpacityText.color = ink;
            }
            if (optionsDifficultyText != null)
            {
                optionsDifficultyText.text = string.Format(Strings.OptionsDifficulty, Strings.DifficultyName(o.DifficultyId));
            }
            if (optionsQualityText != null)
            {
                optionsQualityText.text = string.Format(Strings.OptionsQuality, QualityLabel(o.QualityFor(Application.isMobilePlatform)));
            }
            if (optionsLanguageText != null)
            {
                optionsLanguageText.text = string.Format(Strings.OptionsLanguage, Strings.LanguageName(o.LanguageId));
            }
            if (OptionsLanguageIcon != null)
            {
                // The flag of the language the row shows (2026-11-20): French flag in French, US flag in English.
                OptionsLanguageIcon.sprite = UiIconLibrary.LanguageFlag(o.LanguageId);
            }
        }

        /// <summary>Every Credits line in the current language (Core.Credits, one label per entry).</summary>
        private void RefreshCreditsTexts()
        {
            for (int i = 0; i < creditsLines.Count && i < Credits.All.Count; i++)
            {
                creditsLines[i].text = Credits.All[i].Text(Strings.Language);
            }
        }

        // ----- LOADDOTS: the first open of the level select, spread over frames behind "Niveaux..." -----

        /// <summary>
        /// LOADDOTS: Niveaux was pressed and the level select's first-open work (<see cref="LevelSelect.WarmStep"/>: every
        /// level's JSON parsed and its miniature drawn) is being done a slice per frame while the button's label cycles
        /// ".", "..", "...". The page opens when it is done; Escape or gamepad B, Jouer, Options, Crédits or leaving the
        /// title cancel it (the work already done stays cached). Niveaux keeps the selection all along.
        /// </summary>
        public bool LevelSelectLoading { get; private set; }

        /// <summary>
        /// LOADDOTS: Niveaux opens the level select on the click's frame, with no dots and no pre-warm on the title (the
        /// pre-LOADDOTS behaviour). Default (<see cref="DefaultInstantLevelSelect"/>): on under --probe, --look and in batch
        /// mode; the PlayMode suite turns it on for every test (HeldStartTestRun), since its tests read
        /// <see cref="LevelSelectOpen"/> right after the click. <see cref="ResetInstantLevelSelect"/> goes back to the default.
        /// </summary>
        public static bool InstantLevelSelect
        {
            get => instantLevelSelectOverride ?? DefaultInstantLevelSelect;
            set => instantLevelSelectOverride = value;
        }

        private static bool? instantLevelSelectOverride;

        /// <summary>LOADDOTS: <see cref="InstantLevelSelect"/>'s default (probe, look agent, batch mode).</summary>
        public static bool DefaultInstantLevelSelect => Probe.Requested || SaveStore.LookRequested || Application.isBatchMode;

        /// <summary>Tests: <see cref="InstantLevelSelect"/> goes back to <see cref="DefaultInstantLevelSelect"/>.</summary>
        public static void ResetInstantLevelSelect()
        {
            instantLevelSelectOverride = null;
        }

        // The dots change every LoadDotSeconds; the load works at most LoadFrameBudgetMs per frame (one step at least).
        private const float LoadDotSeconds = 0.3f;
        private const double LoadFrameBudgetMs = 8.0;
        // Pre-warm: once the title's main page has shown for PrewarmDelaySeconds, one step every PrewarmEveryFrames frames.
        private const float PrewarmDelaySeconds = 1.5f;
        private const int PrewarmEveryFrames = 3;
        // Invisible dots that pad the label to three, so its width never changes while the dots cycle.
        private const string HiddenDotsOpen = "<color=#00000000>";
        private const string HiddenDotsClose = "</color>";

        private Coroutine levelSelectLoad;
        private Text levelsLabel;
        // The label's text before the dots (null while no dots show).
        private string levelsLabelText;
        private int levelsDots;
        // Realtime the title's main page started showing (-1 while hidden), and the pre-warm's measures.
        private float titleShownSince = -1f;
        private int prewarmSteps;
        private double prewarmMs;
        private double prewarmWorstMs;
        private bool prewarmLogged;

        /// <summary>
        /// Niveaux: opens the level select over the title (ignored when the title is not up). LOADDOTS: when the page's
        /// first-open work is not done yet (and <see cref="InstantLevelSelect"/> is off) the page opens a few frames later,
        /// behind the loading dots (<see cref="LevelSelectLoading"/>); a second press meanwhile is ignored.
        /// </summary>
        public void OpenLevelSelect()
        {
            if (LevelSelectLoading || !TitleOpen || LevelSelectOpen || CreditsOpen || LevelSelect == null)
            {
                return;
            }
            if (InstantLevelSelect || LevelSelect.Warm || !isActiveAndEnabled)
            {
                OpenLevelSelectNow();
                return;
            }
            levelSelectLoad = StartCoroutine(LoadLevelSelect());
        }

        private void OpenLevelSelectNow()
        {
            var watch = System.Diagnostics.Stopwatch.StartNew();
            LevelSelectOpen = true;
            Apply();
            SelectLater(null);
            Debug.Log($"[LevelSelect] open took {watch.Elapsed.TotalMilliseconds:0.0} ms");
        }

        /// <summary>
        /// LOADDOTS: the first dot shows and renders first, then the first-open work runs a slice per frame (dots cycling)
        /// and the page opens on the frame it ends. Stops itself when the title's main page is no longer what shows.
        /// </summary>
        private IEnumerator LoadLevelSelect()
        {
            LevelSelectLoading = true;
            float start = Time.realtimeSinceStartup;
            var total = System.Diagnostics.Stopwatch.StartNew();
            var slice = new System.Diagnostics.Stopwatch();
            double work = 0.0;
            double worst = 0.0;
            int frames = 0;
            ShowLoadDots(1);
            // One frame first, so the first dot is on screen before any heavy work.
            yield return null;
            while (true)
            {
                if (!LoadStillWanted)
                {
                    EndLevelSelectLoad();
                    yield break;
                }
                slice.Restart();
                bool done;
                do
                {
                    done = LevelSelect.WarmStep();
                }
                while (!done && slice.Elapsed.TotalMilliseconds < LoadFrameBudgetMs);
                double ms = slice.Elapsed.TotalMilliseconds;
                work += ms;
                worst = System.Math.Max(worst, ms);
                frames++;
                if (done)
                {
                    break;
                }
                ShowLoadDots(1 + (int)((Time.realtimeSinceStartup - start) / LoadDotSeconds) % 3);
                yield return null;
            }
            EndLevelSelectLoad();
            OpenLevelSelectNow();
            Debug.Log($"[LevelSelect] loaded behind the dots in {total.Elapsed.TotalMilliseconds:0} ms: {work:0.0} ms of work over "
                + $"{frames} frames (worst frame {worst:0.0} ms)");
        }

        // The load goes on while the title's main page is what shows (nothing opened over it, the title not left).
        private bool LoadStillWanted => TitleOpen && !PauseOpen && !LevelSelectOpen && !CreditsOpen && !OptionsOpen && LevelSelect != null;

        /// <summary>LOADDOTS: stops a level select load in progress (nothing when none runs) and restores Niveaux's label.</summary>
        private void CancelLevelSelectLoad()
        {
            if (levelSelectLoad != null)
            {
                StopCoroutine(levelSelectLoad);
            }
            EndLevelSelectLoad();
        }

        private void EndLevelSelectLoad()
        {
            levelSelectLoad = null;
            LevelSelectLoading = false;
            if (levelsLabel != null && levelsLabelText != null)
            {
                levelsLabel.text = levelsLabelText;
            }
            levelsLabelText = null;
            levelsDots = 0;
        }

        /// <summary>Niveaux's label with <paramref name="dots"/> visible dots (1 to 3), padded to three with invisible ones.</summary>
        private void ShowLoadDots(int dots)
        {
            if (levelsLabel == null && LevelsButton != null)
            {
                levelsLabel = LevelsButton.GetComponentInChildren<Text>(true);
            }
            if (levelsLabel == null || dots == levelsDots)
            {
                return;
            }
            if (levelsLabelText == null)
            {
                levelsLabelText = levelsLabel.text;
            }
            levelsDots = dots;
            // Two spaces between the label and the dots (user request, 2026-11-24).
            levelsLabel.text = levelsLabelText + "  " + new string('.', dots)
                + (dots < 3 ? HiddenDotsOpen + new string('.', 3 - dots) + HiddenDotsClose : string.Empty);
        }

        /// <summary>
        /// LOADDOTS pre-warm: once the title's main page has shown for <see cref="PrewarmDelaySeconds"/>, one step of the
        /// level select's first-open work (one parse or one miniature) every <see cref="PrewarmEveryFrames"/> frames, so a
        /// later Niveaux opens at once. Off under <see cref="InstantLevelSelect"/>, during a load, and once warm.
        /// </summary>
        private void PrewarmLevelSelect()
        {
            if (LevelSelect == null || LevelSelectLoading || InstantLevelSelect)
            {
                return;
            }
            if (LevelSelect.Warm)
            {
                if (!prewarmLogged && prewarmSteps > 0)
                {
                    prewarmLogged = true;
                    Debug.Log($"[LevelSelect] pre-warm done: {prewarmMs:0.0} ms of work over {prewarmSteps} steps (worst step {prewarmWorstMs:0.0} ms)");
                }
                return;
            }
            float now = Time.realtimeSinceStartup;
            if (!TitlePageShown || OptionsOpen || CreditsOpen)
            {
                titleShownSince = -1f;
                return;
            }
            if (titleShownSince < 0f)
            {
                titleShownSince = now;
            }
            if (now - titleShownSince < PrewarmDelaySeconds || Time.frameCount % PrewarmEveryFrames != 0)
            {
                return;
            }
            var watch = System.Diagnostics.Stopwatch.StartNew();
            LevelSelect.WarmStep();
            double ms = watch.Elapsed.TotalMilliseconds;
            prewarmMs += ms;
            prewarmWorstMs = System.Math.Max(prewarmWorstMs, ms);
            prewarmSteps++;
        }

        /// <summary>Retour, Escape or gamepad B: from the level select back to the title's main page, on Niveaux.</summary>
        public void CloseLevelSelect()
        {
            if (!LevelSelectOpen)
            {
                return;
            }
            LevelSelectOpen = false;
            Apply();
            SelectLater(LevelsButton);
        }

        /// <summary>A playable card of the level select: closes the menus and starts that level afresh.</summary>
        public void PlayLevel(string levelId)
        {
            if (!TitleOpen || Game == null || string.IsNullOrEmpty(levelId))
            {
                return;
            }
            LevelSelectOpen = false;
            TitleOpen = false;
            closedFrame = Time.frameCount;
            // SPECTATOR: the level select's checkbox decides whether the level is played or watched.
            Game.Spectator = LevelSelect != null && LevelSelect.SpectatorChecked;
            Apply();
            Game.LoadLevel(levelId);
            CaptureCursor();
        }

        /// <summary>Every menu label by name (tests check the strings).</summary>
        public readonly Dictionary<string, Text> Labels = new Dictionary<string, Text>();

        public GameState Game;
        public Hud Hud;
        public OrbitCamera Camera;
        public Sfx Sfx;

        private Canvas titleCanvas;
        private Canvas pauseCanvas;
        private Font font;
        private int closedFrame = -1;
        private int openedFrame = -1;
        // M5: the selectable to take the selection after the next panel change instead of the default one (Niveaux
        // after Retour), or null.
        private Selectable pendingFocus;

        // ----- M7 title redesign: the title page's warm palette and its column metrics (1920 x 1080 reference). -----
        private static readonly Color TitleDim = new Color(0.08f, 0.05f, 0.035f, 0.16f);
        private static readonly Color TitlePanel = new Color(0.1f, 0.066f, 0.05f, 0.84f);
        private static readonly Color TitleInk = new Color(1f, 0.94f, 0.82f, 1f);
        private static readonly Color TaglineInk = new Color(0.96f, 0.8f, 0.58f, 0.95f);
        private static readonly Color CreditsInk = new Color(1f, 0.94f, 0.82f, 0.6f);
        // The Credits page's detail lines (licences, sources): quieter than a main line, still easy to read on the band.
        private static readonly Color CreditsDetailInk = new Color(1f, 0.94f, 0.82f, 0.78f);
        private static readonly Color ChairRed = new Color(0.82f, 0.2f, 0.16f, 1f);
        private const float TitlePanelWidth = 1240f;
        private const float TitleMargin = 150f;
        private const float TitleButtonStep = 92f;
        private static readonly Vector2 TitleButtonSize = new Vector2(420f, 78f);
        // Credits page (2026-11-19): five title buttons now (Jouer, Niveaux, Options, Crédits, Quitter). They were four, 92
        // apart and 78 high from -84; at that pitch the fifth would leave the bottom of a 20:9 phone (966 reference units
        // high at match 0.5). The title column alone moved to 80 apart, 70 high, from -66: Quitter's bottom sits at -421,
        // still clear of the author line (its top at -437 on a 20:9 phone). The pause menu keeps its own metrics.
        private const float TitleColumnTop = -66f;
        private const float TitleColumnStep = 80f;
        private const float TitleColumnButtonHeight = 70f;

        // Pause menu consistency pass (the product owner's "blurry pause menu" report, 2026-11-18): the pause menu
        // was never updated for the M7 title redesign, so it still used the plain built-in font, grey buttons and a
        // flat dim with no panel behind the text, which read as soft/out of place next to the title. It now reuses
        // the title's own warm palette, display face and column button style; only the dim is its own (stronger
        // than TitleDim, which is tuned for the mostly static title house) but keeps the same warm tint. There is
        // no blur or depth of field anywhere in this project (Main.BuildVolume never adds one): the level stays
        // visible, only dimmed, behind the panel.
        private static readonly Color PauseDim = new Color(0.05f, 0.035f, 0.025f, 0.55f);

        public void Init(GameState game, Hud hud, OrbitCamera camera, Sfx sfx)
        {
            Game = game;
            Hud = hud;
            Camera = camera;
            Sfx = sfx;
            // M7 title camera: the eye level tour of the title house behind the title page (TitleCameraTour).
            TitleCameraTour.Attach(this, game, camera);
            TitleAfterEnd = !Application.isEditor;
            font = hud != null && hud.Font != null ? hud.Font : Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

            var root = gameObject.AddComponent<Canvas>();
            root.renderMode = RenderMode.ScreenSpaceOverlay;
            root.sortingOrder = 50;
            var scaler = gameObject.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920f, 1080f);
            scaler.matchWidthOrHeight = 0.5f;
            gameObject.AddComponent<GraphicRaycaster>();

            BuildTitle();
            BuildPause();
            BuildOptions();
            BuildCredits();
            LevelSelect = LevelSelect.Create(transform, Game, font, Labels, id =>
            {
                Click();
                PlayLevel(id);
            }, () =>
            {
                Click();
                CloseLevelSelect();
            });
            RecordLine = RecordLine.Create(Game, Hud, font, transform);
            if (Hud != null && Hud.EndButton != null)
            {
                Hud.EndButton.onClick.AddListener(() =>
                {
                    Click();
                    ReturnToTitle();
                });
            }
            // M8 touch redesign: the fail, win and end panels' own buttons (a phone has neither Enter nor R).
            BindMenuButton(Hud?.FailMenuButton);
            BindMenuButton(Hud?.WinMenuButton);
            BindRestartButton(Hud?.FailRetryButton);
            BindRestartButton(Hud?.WinReplayButton);
            BindRestartButton(Hud?.EndReplayButton);
            if (Hud != null && Hud.WinNextLevelButton != null)
            {
                Hud.WinNextLevelButton.onClick.AddListener(() =>
                {
                    Click();
                    Game.NextLevel();
                });
            }
            Strings.LanguageChanged -= OnLanguageChanged;
            Strings.LanguageChanged += OnLanguageChanged;
            Apply();
        }

        private void BuildTitle()
        {
            titleCanvas = Panel("Title");
            // M7 title redesign: the level still shows through, orbiting behind a translucent overlay. A light warm dim
            // over the whole screen, soft dark edges, and a warm espresso panel fading in from the left that carries the
            // title column; the right of the screen stays open on the scene (the showcase camera frames the red chair in
            // the lower third, right of the column).
            Stretch(NewImage(titleCanvas.transform, "Dim", null, TitleDim).rectTransform);
            Stretch(NewImage(titleCanvas.transform, "Edges", ProceduralArt.Vignette, new Color(0.04f, 0.025f, 0.02f, 0.5f)).rectTransform);
            Image side = NewImage(titleCanvas.transform, "Band", ProceduralArt.SideFade, TitlePanel);
            side.rectTransform.anchorMin = new Vector2(0f, 0f);
            side.rectTransform.anchorMax = new Vector2(0f, 1f);
            side.rectTransform.pivot = new Vector2(0f, 0.5f);
            side.rectTransform.anchoredPosition = Vector2.zero;
            side.rectTransform.sizeDelta = new Vector2(TitlePanelWidth, 0f);

            // The column, every element left aligned on the same margin: emblem, title, a short red rule, the subtitle
            // ("Don't Get Caught Moving"),
            // then the five buttons (top to bottom: Jouer, Niveaux, Options, Crédits, Quitter), and the author line at the bottom.
            var left = new Vector2(0f, 0.5f);
            Image chair = NewImage(titleCanvas.transform, "Emblem", ProceduralArt.Chair, Color.white);
            chair.preserveAspect = true;
            Place(chair.rectTransform, left, new Vector2(TitleMargin - 6f, 418f), new Vector2(76f, 76f));
            // M7 title logo: the red chair in 3D with its long low-sun shadow, baked once when the page first shows
            // (TitleLogo); the flat icon above stays hidden and comes back only if the bake fails.
            TitleLogo logo = TitleLogo.Create(titleCanvas.transform, this, chair);
            Place(logo.Image.rectTransform, left, new Vector2(Tuning.TitleLogoUiX, Tuning.TitleLogoUiY),
                new Vector2(Tuning.TitleLogoUiWidth, Tuning.TitleLogoUiHeight));
            Font display = Hud.DisplayFont;
            // The title wraps in a narrow box, so "Out of Sight" stacks as two lines; the label keeps the exact string.
            Text title = NewText(titleCanvas.transform, "Title", Strings.Title, 136, TitleInk, display);
            title.alignment = TextAnchor.MiddleLeft;
            title.horizontalOverflow = HorizontalWrapMode.Wrap;
            title.lineSpacing = 0.82f;
            SoftShadow(title);
            Place(title.rectTransform, left, new Vector2(TitleMargin, 222f), new Vector2(585f, 300f));
            Image rule = NewImage(titleCanvas.transform, "Rule", null, ChairRed);
            Place(rule.rectTransform, left, new Vector2(TitleMargin + 4f, 66f), new Vector2(84f, 6f));
            // The product owner's "blurry tagline" report (2026-11-19): this line used the plain built-in font
            // while the headline right above it uses the display face, which read as soft/mismatched next to the
            // crisp title. The display face at a smaller size and the warm accent ink keep it a subtitle.
            Text tagline = NewText(titleCanvas.transform, "Tagline", Strings.TitleTagline, 34, TaglineInk, display);
            tagline.alignment = TextAnchor.MiddleLeft;
            SoftShadow(tagline);
            Place(tagline.rectTransform, left, new Vector2(TitleMargin, 22f), new Vector2(900f, 50f));

            PlayButton = TitleButton("Play", Strings.TitlePlay, display, 0);
            LevelsButton = TitleButton("Levels", Strings.TitleLevels, display, 1);
            // M6 (CONTRACT_M6 2.1): "Options", between Niveaux and Quitter (the product owner asked for Quitter last).
            TitleOptionsButton = TitleButton("TitleOptions", Strings.OptionsTitle, display, 2);
            // Credits page (2026-11-19): "Crédits", between Options and Quitter, so Quitter stays last.
            TitleCreditsButton = TitleButton("TitleCredits", Strings.CreditsTitle, display, 3);
            QuitButton = TitleButton("Quit", Strings.TitleQuit, display, 4);

            // Credits cleanup (2026-11-19, product owner): the title shows only the author line now; the music's CC BY
            // 4.0 attribution moved to the bottom of the Options page (OptionsMusicCredits in BuildOptions), still
            // required by the licence (docs/LICENSES.md) but less prominent. Centred in the margin the two lines
            // used to share, so removing one line left no empty gap.
            Text credits = NewText(titleCanvas.transform, "Credits", Strings.TitleCredits, 24, CreditsInk);
            credits.alignment = TextAnchor.MiddleLeft;
            SoftShadow(credits);
            Place(credits.rectTransform, new Vector2(0f, 0f), new Vector2(TitleMargin, 28f), new Vector2(900f, 36f));
            Chain(PlayButton, LevelsButton, TitleOptionsButton, TitleCreditsButton, QuitButton);
            PlayButton.onClick.AddListener(() =>
            {
                Click();
                Play();
            });
            TitleCreditsButton.onClick.AddListener(() =>
            {
                Click();
                OpenCredits();
            });
            LevelsButton.onClick.AddListener(() =>
            {
                Click();
                OpenLevelSelect();
            });
            QuitButton.onClick.AddListener(() =>
            {
                Click();
                Quit();
            });
            TitleOptionsButton.onClick.AddListener(() =>
            {
                Click();
                OpenOptions();
            });
        }

        /// <summary>
        /// Pause menu consistency pass: the same warm side panel, display face and column buttons as the title
        /// (<see cref="BuildTitle"/>), so Reprendre, Recommencer, Menu principal and Options read as one design with
        /// Jouer, Niveaux, Options and Quitter. The level keeps rendering and shows through <see cref="PauseDim"/>
        /// (dimmed, never blurred); the band gives the text a solid backdrop instead of floating directly over the
        /// moving scene, which is what made the pre-M7 text look soft.
        /// </summary>
        private void BuildPause()
        {
            pauseCanvas = Panel("Pause");
            Stretch(NewImage(pauseCanvas.transform, "Dim", null, PauseDim).rectTransform);
            Image band = NewImage(pauseCanvas.transform, "Band", ProceduralArt.SideFade, TitlePanel);
            band.rectTransform.anchorMin = new Vector2(0f, 0f);
            band.rectTransform.anchorMax = new Vector2(0f, 1f);
            band.rectTransform.pivot = new Vector2(0f, 0.5f);
            band.rectTransform.anchoredPosition = Vector2.zero;
            band.rectTransform.sizeDelta = new Vector2(TitlePanelWidth, 0f);

            var left = new Vector2(0f, 0.5f);
            Font display = Hud.DisplayFont;
            Text title = NewText(pauseCanvas.transform, "PauseTitle", Strings.PauseTitle, 120, TitleInk, display);
            title.alignment = TextAnchor.MiddleLeft;
            SoftShadow(title);
            Place(title.rectTransform, left, new Vector2(TitleMargin, 220f), new Vector2(900f, 150f));
            Image rule = NewImage(pauseCanvas.transform, "PauseRule", null, ChairRed);
            Place(rule.rectTransform, left, new Vector2(TitleMargin + 4f, 130f), new Vector2(84f, 6f));

            ResumeButton = ColumnButton(pauseCanvas.transform, "Resume", Strings.PauseResume, display, TitleMargin, 40f);
            RestartButton = ColumnButton(pauseCanvas.transform, "Restart", Strings.PauseRestart, display, TitleMargin, 40f - TitleButtonStep);
            MainMenuButton = ColumnButton(pauseCanvas.transform, "MainMenu", Strings.PauseMenu, display, TitleMargin, 40f - 2f * TitleButtonStep);
            // M6 (CONTRACT_M6 2.1): "Options", below Menu principal.
            PauseOptionsButton = ColumnButton(pauseCanvas.transform, "PauseOptions", Strings.OptionsTitle, display, TitleMargin, 40f - 3f * TitleButtonStep);
            Chain(ResumeButton, RestartButton, MainMenuButton, PauseOptionsButton);
            ResumeButton.onClick.AddListener(() =>
            {
                Click();
                SetPaused(false);
            });
            RestartButton.onClick.AddListener(() =>
            {
                Click();
                RestartFromPause();
            });
            MainMenuButton.onClick.AddListener(() =>
            {
                Click();
                ToTitleFromPause();
            });
            PauseOptionsButton.onClick.AddListener(() =>
            {
                Click();
                OpenOptions();
            });
        }

        /// <summary>
        /// M7 options redesign: the Options page in the title page's own style (a dark translucent band behind a left
        /// column, the display face for the heading under a short red rule). A single column of rows (each a button
        /// that cycles its value on A/click), each with its own small icon and its value shown within the row, plus
        /// decorative left/right arrows hinting that it cycles. Reachable from the title's main page and the pause menu.
        /// </summary>
        private void BuildOptions()
        {
            optionsCanvas = Panel("Options");
            Stretch(NewImage(optionsCanvas.transform, "Dim", null, TitleDim).rectTransform);
            Image band = NewImage(optionsCanvas.transform, "Band", ProceduralArt.SideFade, TitlePanel);
            band.rectTransform.anchorMin = new Vector2(0f, 0f);
            band.rectTransform.anchorMax = new Vector2(0f, 1f);
            band.rectTransform.pivot = new Vector2(0f, 0.5f);
            band.rectTransform.anchoredPosition = Vector2.zero;
            band.rectTransform.sizeDelta = new Vector2(Tuning.OptionsPanelWidth, 0f);

            var left = new Vector2(0f, 0.5f);
            Font display = Hud.DisplayFont;
            Text title = NewText(optionsCanvas.transform, "OptionsTitle", Strings.OptionsTitle, 92, TitleInk, display);
            title.alignment = TextAnchor.MiddleLeft;
            SoftShadow(title);
            Place(title.rectTransform, left, new Vector2(Tuning.OptionsMargin, OptionsTop + 155f), new Vector2(760f, 110f));
            Image rule = NewImage(optionsCanvas.transform, "OptionsRule", null, ChairRed);
            Place(rule.rectTransform, left, new Vector2(Tuning.OptionsMargin + 4f, OptionsTop + 95f), new Vector2(84f, 6f));

            OptionsSensitivityButton = OptionsRow("OptionsSensitivity", 0, ProceduralArt.OptionMouse, out optionsSensitivityText);
            OptionsVolumeButton = OptionsRow("OptionsVolume", 1, ProceduralArt.OptionSpeaker, out optionsVolumeText);
            // Audio overhaul: the music's own level, next to Volume.
            OptionsMusicButton = OptionsRow("OptionsMusic", 2, ProceduralArt.OptionMusicNote, out optionsMusicText);
            OptionsConeButton = OptionsRow("OptionsCone", 3, ProceduralArt.OptionSightCone, out optionsConeText);
            // M7 walls pass (product owner, 2026-11-19): the Murs / Walls row and its Wall opacity row.
            OptionsWallsButton = OptionsRow("OptionsWalls", 4, ProceduralArt.OptionWalls, out optionsWallsText);
            OptionsWallOpacityButton = OptionsRow("OptionsWallOpacity", 5, ProceduralArt.OptionWallOpacity, out optionsWallOpacityText);
            // M7 (CONTRACT_M7 1.4): the Qualité row.
            OptionsQualityButton = OptionsRow("OptionsQuality", 6, ProceduralArt.OptionQualityBars, out optionsQualityText);
            // M7 design (CONTRACT_M7 4.1): the Difficulté row.
            OptionsDifficultyButton = OptionsRow("OptionsDifficulty", 7, ProceduralArt.OptionDifficultyGauge, out optionsDifficultyText);
            // Language / Langue, English or Français. Its icon is the chosen language's flag (2026-11-20), swapped live by
            // RefreshOptionsTexts (the globe only while the flags do not ship).
            OptionsLanguageButton = OptionsRow("OptionsLanguage", 8, UiIconLibrary.LanguageFlag(SaveStore.Options.LanguageId), out optionsLanguageText);
            Transform languageIcon = OptionsLanguageButton.transform.Find("OptionsLanguageIcon");
            OptionsLanguageIcon = languageIcon != null ? languageIcon.GetComponent<Image>() : null;

            // 2026-11-20: Par défaut and Retour carry an icon too (a reset arrow, a back arrow), in the rows' column.
            OptionsResetButton = OptionsPlainButton("OptionsReset", Strings.OptionsDefault, 9, UiIconLibrary.Reset);
            OptionsBackButton = OptionsPlainButton("OptionsBack", Strings.SelectBack, 10, UiIconLibrary.Back);

            // Credits cleanup (2026-11-19, product owner): the music's CC BY 4.0 attribution (docs/LICENSES.md), moved
            // here from the title page, a small, less prominent line under Retour, clear of it on a 20:9 phone
            // (Step28c_OptionsMusicRowCyclesSavesAndFits checks Retour's own clearance).
            Text optionsCredits = NewText(optionsCanvas.transform, "OptionsMusicCredits", Strings.OptionsMusicCredits, 15, CreditsInk);
            optionsCredits.alignment = TextAnchor.MiddleLeft;
            SoftShadow(optionsCredits);
            Place(optionsCredits.rectTransform, new Vector2(0f, 0f), new Vector2(Tuning.OptionsMargin, 14f), new Vector2(1600f, 22f));

            Chain(OptionsSensitivityButton, OptionsVolumeButton, OptionsMusicButton, OptionsConeButton, OptionsWallsButton, OptionsWallOpacityButton,
                OptionsQualityButton, OptionsDifficultyButton, OptionsLanguageButton, OptionsResetButton, OptionsBackButton);
            OptionsWallsButton.onClick.AddListener(() =>
            {
                Click();
                CycleWalls();
            });
            OptionsWallOpacityButton.onClick.AddListener(() =>
            {
                Click();
                CycleWallOpacity();
            });
            OptionsMusicButton.onClick.AddListener(() =>
            {
                Click();
                CycleMusic();
            });
            OptionsLanguageButton.onClick.AddListener(() =>
            {
                Click();
                CycleLanguage();
            });
            OptionsSensitivityButton.onClick.AddListener(() =>
            {
                Click();
                CycleSensitivity();
            });
            OptionsVolumeButton.onClick.AddListener(() =>
            {
                Click();
                CycleVolume();
            });
            OptionsConeButton.onClick.AddListener(() =>
            {
                Click();
                ToggleCone();
            });
            OptionsQualityButton.onClick.AddListener(() =>
            {
                Click();
                CycleQuality();
            });
            OptionsDifficultyButton.onClick.AddListener(() =>
            {
                Click();
                CycleDifficulty();
            });
            OptionsResetButton.onClick.AddListener(() =>
            {
                Click();
                ResetOptionsClicked();
            });
            OptionsBackButton.onClick.AddListener(() =>
            {
                Click();
                CloseOptions();
            });
            RefreshOptionsTexts();
        }

        // The Options rows: the first row's centre, the step between rows and a row's height (nine value rows, then Par
        // défaut and Retour). Audio overhaul: the Music row made it nine rows; the step went from 90 to 80 and the rows from
        // 84 to 72 high so the last one still clears the bottom of a 20:9 phone (966 reference units high at match 0.5).
        // M7 walls pass: the Walls and Wall opacity rows made it eleven; the step went to 68 and the rows to 62 high, so
        // Retour still clears the music credits line at the bottom of a 20:9 phone (and of a 16:10 screen, taller).
        private const float OptionsTop = 270f;
        private const float OptionsStep = 68f;
        private const float OptionsRowHeight = 62f;

        /// <summary>
        /// A value row of the Options page at <paramref name="index"/> (0 is the top one): the row's icon at its left
        /// (the row's own small identification), its label and value text (unchanged: still the one string, value
        /// included, that <see cref="RefreshOptionsTexts"/> sets), and two small decorative arrows at the right
        /// hinting that a click cycles it.
        /// </summary>
        private Button OptionsRow(string name, int index, Sprite icon, out Text label)
        {
            Button row = Hud.MenuButton(optionsCanvas.transform, name, "", font, Labels);
            Place((RectTransform)row.transform, new Vector2(0f, 0.5f), new Vector2(Tuning.OptionsMargin, OptionsTop - index * OptionsStep), new Vector2(820f, OptionsRowHeight));
            StyleOptionsButton(row);
            Image glyph = NewImage(row.transform, name + "Icon", icon, Color.white);
            glyph.preserveAspect = true;
            Place(glyph.rectTransform, new Vector2(0f, 0.5f), new Vector2(Tuning.OptionsIconInset, 0f),
                new Vector2(Tuning.OptionsIconSize, Tuning.OptionsIconSize));
            OptionsArrows(row.transform);
            label = Labels.TryGetValue(name + "Label", out Text text) ? text : null;
            if (label != null)
            {
                label.alignment = TextAnchor.MiddleLeft;
                label.fontSize = 34;
                label.color = TitleInk;
                // Clear of the icon on the left and the two arrows on the right (their reserved band, see OptionsArrows).
                label.rectTransform.offsetMin = new Vector2(Tuning.OptionsLabelOffset, 0f);
                label.rectTransform.offsetMax = new Vector2(-100f, 0f);
            }
            return row;
        }

        /// <summary>
        /// M7 options redesign: a plain row (Par défaut, Retour) in the same left column, without the value rows' arrows.
        /// 2026-11-20: with an <paramref name="icon"/> (white, tinted the label's cream), it sits where the value rows'
        /// icons sit and the label starts where theirs start, so the column reads as one; without one (the icon does not
        /// ship), the label stays centred as before.
        /// </summary>
        private Button OptionsPlainButton(string name, string label, int index, Sprite icon)
        {
            Button button = Hud.MenuButton(optionsCanvas.transform, name, label, font, Labels);
            Place((RectTransform)button.transform, new Vector2(0f, 0.5f), new Vector2(Tuning.OptionsMargin, OptionsTop - index * OptionsStep),
                new Vector2(420f, OptionsRowHeight));
            StyleOptionsButton(button);
            Labels.TryGetValue(name + "Label", out Text text);
            if (text != null)
            {
                text.color = TitleInk;
            }
            if (icon != null)
            {
                Image glyph = NewImage(button.transform, name + "Icon", icon, TitleInk);
                glyph.preserveAspect = true;
                glyph.raycastTarget = false;
                Place(glyph.rectTransform, new Vector2(0f, 0.5f), new Vector2(Tuning.OptionsIconInset, 0f),
                    new Vector2(Tuning.OptionsIconSize, Tuning.OptionsIconSize));
                if (text != null)
                {
                    text.alignment = TextAnchor.MiddleLeft;
                    text.rectTransform.offsetMin = new Vector2(Tuning.OptionsLabelOffset, 0f);
                    text.rectTransform.offsetMax = new Vector2(-Tuning.OptionsIconInset, 0f);
                }
            }
            return button;
        }

        /// <summary>M7 options redesign: the shared menu button restyled warm brown at rest, the chair's red when
        /// selected or under the mouse (never the same as the other, so the two never look alike), matching the
        /// title page's own buttons.</summary>
        private static void StyleOptionsButton(Button button)
        {
            ColorBlock colors = button.colors;
            colors.normalColor = new Color(0.17f, 0.115f, 0.085f, 0.74f);
            colors.highlightedColor = new Color(0.36f, 0.25f, 0.18f, 0.92f);
            colors.selectedColor = new Color(0.8f, 0.2f, 0.16f, 0.97f);
            colors.pressedColor = new Color(0.55f, 0.12f, 0.09f, 1f);
            button.colors = colors;
        }

        /// <summary>
        /// M7 options redesign: two small chevrons at the row's right edge (the shared arrowhead glyph, rotated to
        /// point left and right), a purely decorative hint that a click on the row cycles its value; never a
        /// separate target, so the keyboard/gamepad/touch chain is untouched.
        /// </summary>
        private void OptionsArrows(Transform parent)
        {
            // Text chevrons: the rotated Chevron sprite is not centred on its pivot, so turning it shifted the two arrows
            // apart diagonally (the product owner's 2026-11-18 screenshot).
            Color tint = new Color(0.96f, 0.8f, 0.58f, 0.8f);
            int size = Mathf.RoundToInt(Tuning.OptionsArrowSize * 1.6f);
            Text right = NewText(parent, "ArrowRight", "›", size, tint);
            right.alignment = TextAnchor.MiddleCenter;
            right.raycastTarget = false;
            Place(right.rectTransform, new Vector2(1f, 0.5f), new Vector2(-Tuning.OptionsArrowInset, 0f),
                new Vector2(Tuning.OptionsArrowSize, Tuning.OptionsArrowSize * 2f));
            Text left = NewText(parent, "ArrowLeft", "‹", size, tint);
            left.alignment = TextAnchor.MiddleCenter;
            left.raycastTarget = false;
            Place(left.rectTransform, new Vector2(1f, 0.5f),
                new Vector2(-(Tuning.OptionsArrowInset + Tuning.OptionsArrowSize + 8f), 0f),
                new Vector2(Tuning.OptionsArrowSize, Tuning.OptionsArrowSize * 2f));
        }

        // ----- Credits page (2026-11-19) -----

        // The Credits page's metrics (1920 x 1080 reference, left middle anchor). The scroll view runs from just under the
        // red rule down to above Retour, which sits where the Options page's own Retour sits (so it clears the bottom of a
        // 20:9 phone the same way).
        private const float CreditsViewTop = OptionsTop + 60f;
        private const float CreditsViewBottom = OptionsTop - 10f * OptionsStep + 50f;
        // Wide enough that the longest source URL (one unbreakable word) stays on one line at the detail size.
        private const float CreditsViewWidth = 960f;
        private const float CreditsBackY = OptionsTop - 10f * OptionsStep;
        private const float CreditsScrollbarWidth = 12f;
        /// <summary>Reference units scrolled per up or down press (keyboard, D-pad, left stick).</summary>
        public const float CreditsScrollStep = 110f;

        /// <summary>
        /// The Credits page, in the Options page's own style (the same dim, band, display face heading under the short red
        /// rule, and the same plain Retour row). Its lines (<see cref="Credits.All"/>) sit in a vertical scroll view: the
        /// mouse wheel, a drag or a touch swipe, its slim scrollbar, and up and down on the keyboard, D-pad or left stick
        /// (<see cref="CreditsScrollKeys"/> on Retour, the page's only selectable) all scroll it.
        /// </summary>
        private void BuildCredits()
        {
            creditsCanvas = Panel("CreditsPage");
            // The pause menu's stronger dim, not the title's: many small lines read better over a quieter scene.
            Stretch(NewImage(creditsCanvas.transform, "Dim", null, PauseDim).rectTransform);
            Image band = NewImage(creditsCanvas.transform, "Band", ProceduralArt.SideFade, TitlePanel);
            band.rectTransform.anchorMin = new Vector2(0f, 0f);
            band.rectTransform.anchorMax = new Vector2(0f, 1f);
            band.rectTransform.pivot = new Vector2(0f, 0.5f);
            band.rectTransform.anchoredPosition = Vector2.zero;
            band.rectTransform.sizeDelta = new Vector2(Tuning.OptionsPanelWidth, 0f);

            var left = new Vector2(0f, 0.5f);
            Font display = Hud.DisplayFont;
            Text title = NewText(creditsCanvas.transform, "CreditsTitle", Strings.CreditsTitle, 92, TitleInk, display);
            title.alignment = TextAnchor.MiddleLeft;
            SoftShadow(title);
            Place(title.rectTransform, left, new Vector2(Tuning.OptionsMargin, OptionsTop + 155f), new Vector2(760f, 110f));
            Image rule = NewImage(creditsCanvas.transform, "CreditsRule", null, ChairRed);
            Place(rule.rectTransform, left, new Vector2(Tuning.OptionsMargin + 4f, OptionsTop + 95f), new Vector2(84f, 6f));

            // The scroll view: a transparent viewport (it takes the wheel, the drag and the swipe) clipped by a RectMask2D.
            var scrollGo = new GameObject("CreditsScroll", typeof(RectTransform));
            scrollGo.transform.SetParent(creditsCanvas.transform, false);
            var scrollRect = (RectTransform)scrollGo.transform;
            scrollRect.anchorMin = scrollRect.anchorMax = left;
            scrollRect.pivot = new Vector2(0f, 1f);
            scrollRect.anchoredPosition = new Vector2(Tuning.OptionsMargin, CreditsViewTop);
            scrollRect.sizeDelta = new Vector2(CreditsViewWidth + 20f + CreditsScrollbarWidth, CreditsViewTop - CreditsViewBottom);
            ScrollRect scroll = scrollGo.AddComponent<ScrollRect>();

            var viewportGo = new GameObject("CreditsViewport", typeof(RectTransform));
            viewportGo.transform.SetParent(scrollGo.transform, false);
            var viewport = (RectTransform)viewportGo.transform;
            viewport.anchorMin = new Vector2(0f, 0f);
            viewport.anchorMax = new Vector2(0f, 1f);
            viewport.pivot = new Vector2(0f, 1f);
            viewport.anchoredPosition = Vector2.zero;
            viewport.sizeDelta = new Vector2(CreditsViewWidth, 0f);
            var catcher = viewportGo.AddComponent<Image>();
            catcher.color = new Color(0f, 0f, 0f, 0f);
            catcher.raycastTarget = true;
            viewportGo.AddComponent<RectMask2D>();

            var contentGo = new GameObject("CreditsContent", typeof(RectTransform));
            contentGo.transform.SetParent(viewport, false);
            var content = (RectTransform)contentGo.transform;
            content.anchorMin = new Vector2(0f, 1f);
            content.anchorMax = new Vector2(1f, 1f);
            content.pivot = new Vector2(0.5f, 1f);
            content.anchoredPosition = Vector2.zero;
            content.sizeDelta = Vector2.zero;
            var column = contentGo.AddComponent<VerticalLayoutGroup>();
            column.padding = new RectOffset(4, 8, 4, 28);
            column.spacing = 4f;
            column.childAlignment = TextAnchor.UpperLeft;
            column.childControlWidth = true;
            column.childControlHeight = true;
            column.childForceExpandWidth = true;
            column.childForceExpandHeight = false;
            var fitter = contentGo.AddComponent<ContentSizeFitter>();
            fitter.verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            fitter.horizontalFit = ContentSizeFitter.FitMode.Unconstrained;

            creditsLines.Clear();
            for (int i = 0; i < Credits.All.Count; i++)
            {
                Credits.Entry entry = Credits.All[i];
                if (entry.Kind == Credits.Kind.Heading && i > 0)
                {
                    // Air above every section but the first.
                    var gap = new GameObject("CreditsGap" + i, typeof(RectTransform));
                    gap.transform.SetParent(content, false);
                    gap.AddComponent<LayoutElement>().minHeight = 22f;
                }
                bool heading = entry.Kind == Credits.Kind.Heading;
                bool detail = entry.Kind == Credits.Kind.Detail;
                Text line = NewText(content, "CreditsLine" + i, entry.Text(Strings.Language),
                    heading ? 40 : detail ? 24 : 28,
                    heading ? TaglineInk : detail ? CreditsDetailInk : TitleInk,
                    heading ? display : font);
                line.alignment = TextAnchor.UpperLeft;
                line.horizontalOverflow = HorizontalWrapMode.Wrap;
                line.verticalOverflow = VerticalWrapMode.Overflow;
                line.lineSpacing = 1.05f;
                // A lighter, closer shadow than SoftShadow: at 24 to 28 units the title's shadow smeared the glyphs.
                Shadow shadow = line.GetComponent<Shadow>();
                shadow.effectColor = new Color(0.05f, 0.03f, 0.02f, 0.5f);
                shadow.effectDistance = new Vector2(1f, -1.5f);
                creditsLines.Add(line);
            }

            // The slim scrollbar at the right of the viewport: draggable with the mouse, never on the keyboard path.
            var barGo = new GameObject("CreditsScrollbar", typeof(RectTransform));
            barGo.transform.SetParent(scrollGo.transform, false);
            var barRect = (RectTransform)barGo.transform;
            barRect.anchorMin = new Vector2(1f, 0f);
            barRect.anchorMax = new Vector2(1f, 1f);
            barRect.pivot = new Vector2(1f, 0.5f);
            barRect.anchoredPosition = Vector2.zero;
            barRect.sizeDelta = new Vector2(CreditsScrollbarWidth, 0f);
            Image track = barGo.AddComponent<Image>();
            track.sprite = ProceduralArt.Rounded;
            track.type = Image.Type.Sliced;
            track.color = new Color(0.17f, 0.115f, 0.085f, 0.6f);
            var slidingGo = new GameObject("SlidingArea", typeof(RectTransform));
            slidingGo.transform.SetParent(barGo.transform, false);
            Stretch((RectTransform)slidingGo.transform);
            var handleGo = new GameObject("Handle", typeof(RectTransform));
            handleGo.transform.SetParent(slidingGo.transform, false);
            var handleRect = (RectTransform)handleGo.transform;
            Stretch(handleRect);
            Image handle = handleGo.AddComponent<Image>();
            handle.sprite = ProceduralArt.Rounded;
            handle.type = Image.Type.Sliced;
            handle.color = new Color(TaglineInk.r, TaglineInk.g, TaglineInk.b, 0.85f);
            Scrollbar bar = barGo.AddComponent<Scrollbar>();
            bar.handleRect = handleRect;
            bar.targetGraphic = handle;
            bar.direction = Scrollbar.Direction.BottomToTop;
            bar.navigation = new Navigation { mode = Navigation.Mode.None };

            scroll.viewport = viewport;
            scroll.content = content;
            scroll.horizontal = false;
            scroll.vertical = true;
            scroll.movementType = ScrollRect.MovementType.Clamped;
            scroll.inertia = true;
            scroll.scrollSensitivity = 15f;
            scroll.verticalScrollbar = bar;
            scroll.verticalScrollbarVisibility = ScrollRect.ScrollbarVisibility.Permanent;
            CreditsScroll = scroll;

            CreditsBackButton = Hud.MenuButton(creditsCanvas.transform, "CreditsBack", Strings.SelectBack, font, Labels);
            Place((RectTransform)CreditsBackButton.transform, left, new Vector2(Tuning.OptionsMargin, CreditsBackY), new Vector2(420f, OptionsRowHeight));
            StyleOptionsButton(CreditsBackButton);
            if (Labels.TryGetValue("CreditsBackLabel", out Text backLabel))
            {
                backLabel.color = TitleInk;
            }
            // Retour is the page's only selectable: up and down have nowhere to go, so they scroll the page instead.
            CreditsBackButton.navigation = new Navigation { mode = Navigation.Mode.Explicit };
            CreditsBackButton.gameObject.AddComponent<CreditsScrollKeys>().Menu = this;
            CreditsBackButton.onClick.AddListener(() =>
            {
                Click();
                CloseCredits();
            });
        }

        /// <summary>
        /// On the Credits page's Retour: a real keyboard, D-pad or left stick move (the UI input module's move event, repeated
        /// while held) scrolls the page, up toward the top, down toward the end. Injected test input goes through
        /// <see cref="Update"/> instead.
        /// </summary>
        private sealed class CreditsScrollKeys : MonoBehaviour, IMoveHandler
        {
            public Menu Menu;

            public void OnMove(AxisEventData eventData)
            {
                if (Menu == null)
                {
                    return;
                }
                if (eventData.moveDir == MoveDirection.Down)
                {
                    Menu.ScrollCredits(CreditsScrollStep);
                }
                else if (eventData.moveDir == MoveDirection.Up)
                {
                    Menu.ScrollCredits(-CreditsScrollStep);
                }
            }
        }

        private void Start()
        {
            // "--optionsshot <dir>" (a built player): a screenshot of this page over the title, then quit (the same
            // pattern as LevelSelect's own "--levelshot").
            string dir = Probe.ArgValue("--optionsshot");
            if (!Application.isEditor && !string.IsNullOrEmpty(dir))
            {
                StartCoroutine(OptionsShot(dir));
            }
            // LEVELNUM: "-autoShot <dir> [-autoLevel <id>]" (a built player): shots of a level's intro card, then quit.
            string autoShot = Probe.ArgValue("-autoShot");
            if (!Application.isEditor && !string.IsNullOrEmpty(autoShot))
            {
                StartCoroutine(AutoShot(autoShot, Probe.ArgValue("-autoLevel")));
            }
        }

        /// <summary>
        /// LEVELNUM: "-autoShot &lt;dir&gt; [-autoLevel &lt;id&gt;]" (a built player only, never without the argument): waits
        /// for the title, plays the level (level13 by default) the way a level select card does, and writes screen
        /// captures of its held intro card when the number's zoom reaches 0.1, 0.5 and 1.0 s and once it has settled
        /// (&lt;id&gt;_t010.png, _t050, _t100, _settled), with a line per shot in the player log; then quits.
        /// </summary>
        private IEnumerator AutoShot(string dir, string levelId)
        {
            Directory.CreateDirectory(dir);
            levelId = string.IsNullOrEmpty(levelId) ? "level13" : levelId;
            float until = Time.realtimeSinceStartup + 20f;
            while (!TitleOpen && Time.realtimeSinceStartup < until)
            {
                yield return null;
            }
            yield return new WaitForSecondsRealtime(1.5f);
            PlayLevel(levelId);
            Debug.Log($"[AutoShot] {levelId}: number {Hud.LevelNumberShown}, holes ready {Hud.LevelNumberHolesReady}, "
                + $"face {Hud.LevelNumberFont}, easing {Hud.CardSettings.Easing}, "
                + $"screen {Screen.width} x {Screen.height}, held {Hud.CardHeld}");
            float[] ages = { 0.1f, 0.5f, 1f, Hud.NumberZoomSeconds + 1f };
            string[] names = { "t010", "t050", "t100", "settled" };
            for (int i = 0; i < ages.Length; i++)
            {
                float guard = Time.realtimeSinceStartup + 15f;
                while (Hud.LevelNumberAge < ages[i] && Time.realtimeSinceStartup < guard)
                {
                    yield return null;
                }
                yield return new WaitForEndOfFrame();
                Texture2D shot = ScreenCapture.CaptureScreenshotAsTexture();
                string path = Path.Combine(dir, $"{levelId}_{names[i]}.png");
                File.WriteAllBytes(path, shot.EncodeToPNG());
                Destroy(shot);
                Debug.Log($"[AutoShot] {path}: age {Hud.LevelNumberAge:0.000} s, scale {Hud.LevelNumberScale:0.000} "
                    + $"(final {Hud.LevelNumberFinalScale:0.000}), ink {Hud.LevelNumberInkRect}, card alpha {Hud.TitleCardAlpha:0.00}");
            }
            yield return new WaitForSecondsRealtime(0.5f);
            Application.Quit();
        }

        /// <summary>
        /// "--optionsshot &lt;dir&gt;": waits for the title, opens Options over it, selects the Volume row (so the
        /// selection's chair red shows in the shot) and writes options_page.png, then quits.
        /// </summary>
        private IEnumerator OptionsShot(string dir)
        {
            Directory.CreateDirectory(dir);
            float until = Time.realtimeSinceStartup + 20f;
            while (!TitleOpen && Time.realtimeSinceStartup < until)
            {
                yield return null;
            }
            yield return new WaitForSecondsRealtime(2.5f);
            OpenOptions();
            yield return new WaitForSecondsRealtime(0.5f);
            if (OptionsVolumeButton != null && EventSystem.current != null)
            {
                EventSystem.current.SetSelectedGameObject(OptionsVolumeButton.gameObject);
            }
            yield return new WaitForSecondsRealtime(1f);
            ScreenCapture.CaptureScreenshot(Path.Combine(dir, "options_page.png"));
            yield return new WaitForSecondsRealtime(1f);
            Application.Quit();
        }

        // ----- Flow -----

        /// <summary>
        /// Opens the title over the first level of levels.json (loaded if another level is up), with the camera in
        /// its slow orbit. The game is paused until Play.
        /// </summary>
        public void ShowTitle()
        {
            OpenTitle(false);
        }

        /// <summary><paramref name="reload"/>: the first level is built afresh even when it is already up.</summary>
        private void OpenTitle(bool reload)
        {
            if (Game == null)
            {
                return;
            }
            CancelLevelSelectLoad();
            PauseOpen = false;
            TitleOpen = true;
            LevelSelectOpen = false;
            CreditsOpen = false;
            string first = TitleCameraTour.LevelFor(Game); // M7 title camera: the title house, never played
            // SPECTATOR: the title house is never watched with the free camera; a spectator level is always rebuilt.
            if (Game.Spectator)
            {
                Game.Spectator = false;
                reload = true;
            }
            if (reload || Game.Level == null || Game.LevelId != first)
            {
                Game.LoadLevel(first);
            }
            Apply();
            SelectLater(null);
        }

        /// <summary>
        /// Opens or closes the pause menu. The title screen keeps the game paused and ignores it, and so does its level
        /// select (Escape closes the select, it never also pauses).
        /// </summary>
        public void SetPaused(bool paused)
        {
            if (TitleOpen || LevelSelectOpen || PauseOpen == paused)
            {
                return;
            }
            PauseOpen = paused;
            if (!paused)
            {
                closedFrame = Time.frameCount;
            }
            else if (Labels.TryGetValue("MainMenuLabel", out Text mainMenu))
            {
                // SPECTATOR: from a watched level, "Menu principal" goes back to the level select and says so.
                mainMenu.text = Game != null && Game.Spectator ? Strings.PauseLevels : Strings.PauseMenu;
            }
            Apply();
            if (paused)
            {
                Select(ResumeButton);
            }
            else
            {
                CaptureCursor();
            }
        }

        /// <summary>
        /// Jouer: closes the title and starts afresh the first level of levels.json that is unlocked but not won (level 1
        /// on a fresh save, the last level when every one is won). Ignored while the level select is open.
        /// </summary>
        public void Play()
        {
            if (!TitleOpen || LevelSelectOpen || CreditsOpen)
            {
                return;
            }
            CancelLevelSelectLoad();
            TitleOpen = false;
            closedFrame = Time.frameCount;
            Game.Spectator = false; // SPECTATOR: Jouer always plays
            Apply();
            Game.LoadLevel(PlayTarget);
            CaptureCursor();
        }

        /// <summary>The level Jouer starts: the first unlocked level not won yet (<see cref="SaveStore.FirstUnwonLevel"/>).</summary>
        public string PlayTarget => Game == null ? null : SaveStore.FirstUnwonLevel(Game.LevelOrder) ?? Game.FirstLevelId;

        /// <summary>Recommencer: resumes and restarts the current level.</summary>
        public void RestartFromPause()
        {
            SetPaused(false);
            Game.Restart();
        }

        /// <summary>
        /// Menu principal: from the pause menu back to the title, over the first level built afresh (M3.1: never the
        /// level as it was left, chair moved and clock stopped).
        /// </summary>
        public void ToTitleFromPause()
        {
            // SPECTATOR: from a watched level the button goes back to the level select (over the title house), with the
            // checkbox still ticked for the next pick.
            bool spectator = Game != null && Game.Spectator;
            PauseOpen = false;
            OpenTitle(true);
            if (spectator)
            {
                OpenLevelSelect();
            }
        }

        public void Quit()
        {
            Application.Quit();
        }

        /// <summary>
        /// The end screen's button (Enter submits it): back to the title in a player (<see cref="TitleAfterEnd"/>);
        /// in the editor, where the title never shows by itself, the first level again. Safe to call twice.
        /// </summary>
        public void ReturnToTitle()
        {
            if (Game == null || TitleOpen)
            {
                return;
            }
            if (!TitleAfterEnd)
            {
                if (Game.State == PlayState.Won && Game.IsLastLevel)
                {
                    Game.LoadLevel(Game.FirstLevelId);
                }
                return;
            }
            OpenTitle(true);
        }

        /// <summary>The end screen is up (GameState.Win): free the cursor; its button is selected on the next frame.</summary>
        public void OnEndScreen()
        {
            Cursor.lockState = CursorLockMode.None;
            Cursor.visible = true;
            SelectLater(null);
        }

        /// <summary>
        /// M8 touch redesign: the win panel (not the end screen) is up (GameState.Win): free the cursor so Next
        /// level, Replay and Menu can be clicked. None of them is selected (<see cref="Hud.WinButtonsVisible"/> doc):
        /// Enter and gamepad A keep loading the next level exactly as GameState already reads them.
        /// </summary>
        public void OnWinScreen()
        {
            Cursor.lockState = CursorLockMode.None;
            Cursor.visible = true;
        }

        /// <summary>M8 touch redesign: the fail panel is up (GameState.Lose): free the cursor; Retry is selected on the next frame.</summary>
        public void OnFailScreen()
        {
            Cursor.lockState = CursorLockMode.None;
            Cursor.visible = true;
            SelectLater(null);
        }

        /// <summary>M8 touch redesign: Retry, Replay (fail, win and end panels) all restart the current level the same way.</summary>
        private void BindRestartButton(Button button)
        {
            if (button == null)
            {
                return;
            }
            button.onClick.AddListener(() =>
            {
                Click();
                Game.Restart();
            });
        }

        /// <summary>M8 touch redesign: Menu (the fail and win panels) is the same "back to the title" as the pause menu's.</summary>
        private void BindMenuButton(Button button)
        {
            if (button == null)
            {
                return;
            }
            button.onClick.AddListener(() =>
            {
                Click();
                ToTitleFromPause();
            });
        }

        /// <summary>
        /// Clears the selection now; <see cref="Update"/> selects <paramref name="focus"/> (when shown), else the open
        /// panel's default button, next frame.
        /// </summary>
        private void SelectLater(Selectable focus)
        {
            openedFrame = Time.frameCount;
            pendingFocus = focus;
            if (EventSystem.current != null)
            {
                EventSystem.current.SetSelectedGameObject(null);
            }
        }

        /// <summary>
        /// The default button of what is open (Options, the level select's first unlocked card, title, pause, end
        /// screen, the fail panel), or null. M8 touch redesign: the win panel's own buttons are deliberately left out
        /// (Hud.WinButtonsVisible doc): Enter and gamepad A already load the next level the way GameState reads them,
        /// and selecting a button here would make the same press submit it too.
        /// </summary>
        public Selectable DefaultButton => OptionsOpen ? OptionsSensitivityButton
            : CreditsOpen ? CreditsBackButton
            : LevelSelectOpen && LevelSelect != null ? LevelSelect.DefaultSelectable
            : TitleOpen ? PlayButton
            : PauseOpen ? ResumeButton
            : Hud != null && Hud.EndVisible ? Hud.EndButton
            : Hud != null && Hud.FailVisible ? Hud.FailRetryButton
            : null;

        private void Update()
        {
            // M5 (M6: and Options): Escape or gamepad B leaves the topmost page. Read every frame, so a press made
            // elsewhere never waits for a page to open.
            if (InputReader.BackPressed())
            {
                if (OptionsOpen)
                {
                    Click();
                    CloseOptions();
                }
                else if (CreditsOpen)
                {
                    Click();
                    CloseCredits();
                }
                else if (LevelSelectOpen)
                {
                    Click();
                    CloseLevelSelect();
                }
                else if (LevelSelectLoading)
                {
                    // LOADDOTS: Escape or B during the dots cancels the load; Niveaux keeps the selection.
                    Click();
                    CancelLevelSelectLoad();
                }
            }
            PrewarmLevelSelect();
            // M6 (CONTRACT_M6 2.2): a test drives every menu with injected gamepad input alone (InputReader has no real
            // device to read here): D-pad/left stick moves the EventSystem selection along the same explicit
            // Navigation links a real press would follow, A invokes the selected widget. A real gamepad already
            // navigates through the InputSystemUIInputModule directly; this never conflicts with it (it only acts on an
            // injected flag, which a real device never sets).
            EventSystem events = EventSystem.current;
            if (events != null)
            {
                MenuDirection dir = InputReader.MenuMovePressed();
                if (CreditsOpen && (dir == MenuDirection.Up || dir == MenuDirection.Down))
                {
                    // The Credits page: up and down scroll it (CreditsScrollKeys does the same for a real device).
                    ScrollCredits(dir == MenuDirection.Down ? CreditsScrollStep : -CreditsScrollStep);
                }
                else if (dir != MenuDirection.None)
                {
                    Selectable current = events.currentSelectedGameObject != null
                        ? events.currentSelectedGameObject.GetComponent<Selectable>()
                        : null;
                    Selectable next = current != null ? NavigationStep(current, dir) : null;
                    if (next != null && IsShown(next.gameObject))
                    {
                        events.SetSelectedGameObject(next.gameObject);
                    }
                }
                if (InputReader.MenuSubmitPressed() && events.currentSelectedGameObject != null)
                {
                    ExecuteEvents.Execute(events.currentSelectedGameObject, new BaseEventData(events), ExecuteEvents.submitHandler);
                }
            }
            Selectable wanted = pendingFocus != null && IsShown(pendingFocus.gameObject) ? pendingFocus : DefaultButton;
            if (events == null || wanted == null || Time.frameCount <= openedFrame)
            {
                return;
            }
            pendingFocus = null;
            GameObject selected = events.currentSelectedGameObject;
            if (selected == null || !IsShown(selected))
            {
                events.SetSelectedGameObject(wanted.gameObject);
            }
        }

        /// <summary>The explicit Navigation link of <paramref name="from"/> in <paramref name="dir"/>, or null.</summary>
        private static Selectable NavigationStep(Selectable from, MenuDirection dir)
        {
            Navigation nav = from.navigation;
            switch (dir)
            {
                case MenuDirection.Up:
                    return nav.selectOnUp;
                case MenuDirection.Down:
                    return nav.selectOnDown;
                case MenuDirection.Left:
                    return nav.selectOnLeft;
                case MenuDirection.Right:
                    return nav.selectOnRight;
                default:
                    return null;
            }
        }

        /// <summary>A selectable is shown when it is active and its nearest Canvas is enabled.</summary>
        private static bool IsShown(GameObject go)
        {
            if (!go.activeInHierarchy)
            {
                return false;
            }
            Canvas canvas = go.GetComponentInParent<Canvas>();
            return canvas != null && canvas.isActiveAndEnabled;
        }

        /// <summary>Applies the open panels: canvases, pause, HUD, camera and cursor.</summary>
        private void Apply()
        {
            // M6: Options is a page of whichever menu opened it; it closes itself if that menu went away meanwhile
            // (e.g. Menu principal from the pause menu while Options was open over it).
            if (OptionsOpen && !(optionsFromPause ? PauseOpen : TitleOpen && !LevelSelectOpen))
            {
                OptionsOpen = false;
            }
            bool open = IsOpen;
            if (!TitleOpen)
            {
                LevelSelectOpen = false;
            }
            // The Credits page is a page of the title's main page: it closes with the title or under the level select.
            if (CreditsOpen && (!TitleOpen || LevelSelectOpen))
            {
                CreditsOpen = false;
            }
            SetEnabled(titleCanvas, TitleOpen && !LevelSelectOpen && !CreditsOpen && !(OptionsOpen && !optionsFromPause));
            SetEnabled(pauseCanvas, PauseOpen && !(OptionsOpen && optionsFromPause));
            SetEnabled(optionsCanvas, OptionsOpen);
            SetEnabled(creditsCanvas, CreditsOpen);
            if (LevelSelect != null && LevelSelect.IsOpen != LevelSelectOpen)
            {
                LevelSelect.SetOpen(LevelSelectOpen);
            }
            if (Game != null)
            {
                Game.Paused = open;
            }
            Hud?.SetVisible(!open);
            Camera?.SetShowcase(TitleOpen);
            if (open)
            {
                Cursor.lockState = CursorLockMode.None;
                Cursor.visible = true;
            }
            else if (EventSystem.current != null)
            {
                EventSystem.current.SetSelectedGameObject(null);
            }
        }

        /// <summary>
        /// Back in the game: a player captures the cursor again (the editor leaves it to the click). Public so
        /// GameState.Restart/NextLevel can call it too (M8 touch redesign: a real Restart/NextLevel press no longer
        /// leaves the mouse cursor free from the panel it just left).
        /// </summary>
        public void CaptureCursor()
        {
            if (!Application.isEditor && !WantsCursor)
            {
                Cursor.lockState = CursorLockMode.Locked;
            }
        }

        private void Click()
        {
            if (Sfx != null)
            {
                Sfx.PlayUiClick();
            }
        }

        private static void Select(Selectable selectable)
        {
            if (selectable != null && EventSystem.current != null)
            {
                EventSystem.current.SetSelectedGameObject(selectable.gameObject);
            }
        }

        private static void SetEnabled(Canvas canvas, bool enabled)
        {
            if (canvas != null && canvas.enabled != enabled)
            {
                canvas.enabled = enabled;
            }
        }

        /// <summary>Up and down move through <paramref name="buttons"/> in order, and wrap.</summary>
        private static void Chain(params Button[] buttons)
        {
            for (int i = 0; i < buttons.Length; i++)
            {
                var nav = new Navigation
                {
                    mode = Navigation.Mode.Explicit,
                    selectOnUp = buttons[(i + buttons.Length - 1) % buttons.Length],
                    selectOnDown = buttons[(i + 1) % buttons.Length],
                };
                buttons[i].navigation = nav;
            }
        }

        // ----- Construction helpers -----

        /// <summary>
        /// The title page's button at <paramref name="index"/> (0 is Jouer, the top one), a <see cref="ColumnButton"/> on the
        /// title's own left margin, <see cref="TitleColumnStep"/> apart and <see cref="TitleColumnButtonHeight"/> high.
        /// </summary>
        private Button TitleButton(string name, string label, Font display, int index)
        {
            Button button = ColumnButton(titleCanvas.transform, name, label, display, TitleMargin, TitleColumnTop - index * TitleColumnStep);
            ((RectTransform)button.transform).sizeDelta = new Vector2(TitleButtonSize.x, TitleColumnButtonHeight);
            return button;
        }

        /// <summary>
        /// The shared column button of the title and the pause menu (pause reuses it for its own consistency pass):
        /// the title column's button (<see cref="Hud.MenuButton"/>, so the same navigation and label naming)
        /// restyled left aligned in the display face on a warm translucent plate; under the mouse a lighter brown,
        /// selected the chair's red, so the two never look alike. <paramref name="x"/> and <paramref name="y"/> are
        /// the anchored position on the panel's left edge, in <see cref="TitleButtonSize"/>.
        /// </summary>
        private Button ColumnButton(Transform parent, string name, string label, Font display, float x, float y)
        {
            Button button = Hud.MenuButton(parent, name, label, display, Labels);
            Place((RectTransform)button.transform, new Vector2(0f, 0.5f), new Vector2(x, y), TitleButtonSize);
            ColorBlock colors = button.colors;
            colors.normalColor = new Color(0.17f, 0.115f, 0.085f, 0.62f);
            colors.highlightedColor = new Color(0.36f, 0.25f, 0.18f, 0.9f);
            colors.selectedColor = new Color(0.8f, 0.2f, 0.16f, 0.97f);
            colors.pressedColor = new Color(0.55f, 0.12f, 0.09f, 1f);
            button.colors = colors;
            if (Labels.TryGetValue(name + "Label", out Text text))
            {
                text.fontSize = 44;
                text.alignment = TextAnchor.MiddleLeft;
                text.color = TitleInk;
                text.rectTransform.offsetMin = new Vector2(36f, 0f);
                text.rectTransform.offsetMax = new Vector2(-24f, 0f);
            }
            return button;
        }

        /// <summary>A soft, low drop shadow: readable over the moving scene without the hard offset of the HUD text.</summary>
        private static void SoftShadow(Text text)
        {
            var shadow = text.GetComponent<Shadow>();
            if (shadow != null)
            {
                shadow.effectColor = new Color(0.05f, 0.03f, 0.02f, 0.55f);
                shadow.effectDistance = new Vector2(2f, -3f);
            }
        }

        private Canvas Panel(string name)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(transform, false);
            Stretch((RectTransform)go.transform);
            var canvas = go.AddComponent<Canvas>();
            // A nested Canvas raycasts its own graphics only.
            go.AddComponent<GraphicRaycaster>();
            canvas.enabled = false;
            return canvas;
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

        private Text NewText(Transform parent, string name, string value, int size, Color color)
        {
            return NewText(parent, name, value, size, color, font);
        }

        private Text NewText(Transform parent, string name, string value, int size, Color color, Font face)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var text = go.AddComponent<Text>();
            text.font = face;
            text.fontSize = size;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = color;
            text.text = value;
            text.raycastTarget = false;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            var shadow = go.AddComponent<Shadow>();
            shadow.effectColor = new Color(0f, 0f, 0f, 0.7f);
            shadow.effectDistance = new Vector2(3f, -4f);
            Labels[name] = text;
            return text;
        }

        private static void Place(RectTransform rect, Vector2 anchor, Vector2 offset, Vector2 size)
        {
            rect.anchorMin = rect.anchorMax = anchor;
            rect.pivot = anchor;
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

    /// <summary>
    /// The look agent's screenshots of what the probe never shows (a built player only, "--look &lt;dir&gt;"): the
    /// title, the pause menu, the x-ray of every two-room level, a marker under the HUD band, the end screen and
    /// the way back to the title. Writes the PNGs and look.txt (luminance, x-ray check, marker clamp), then quits.
    /// </summary>
    internal static class LookShots
    {
        public static IEnumerator Run(Main main, string dir)
        {
            Directory.CreateDirectory(dir);
            var lines = new List<string>();
            GameState game = main.Game;
            Menu menu = main.Menu;
            Hud hud = main.Hud;
            List<string> problems = main.LookProblems();
            lines.Add("look problems: " + (problems.Count == 0 ? "none" : string.Join(" | ", problems)));

            // 1. The title, as a player first sees it.
            if (!menu.TitleOpen)
            {
                menu.ShowTitle();
            }
            yield return new WaitForSecondsRealtime(2f);
            yield return Shoot(dir, "L1_title.png", lines);

            // 1b. M5: the level select (a fresh save: only the first card unlocked), then back to the title.
            menu.OpenLevelSelect();
            yield return new WaitForSecondsRealtime(0.5f);
            lines.Add($"levels: open={menu.LevelSelectOpen} cards={(menu.LevelSelect != null ? menu.LevelSelect.CardCount : 0)}"
                + $" order={game.LevelOrder.Count} save={SaveStore.FilePath}");
            yield return Shoot(dir, "L1b_levels.png", lines);
            menu.CloseLevelSelect();
            yield return new WaitForSecondsRealtime(0.2f);

            // 2. The pause menu over the first level.
            menu.Play();
            yield return Fixed(50);
            InputReader.InjectPausePress();
            yield return Fixed(3);
            lines.Add($"pause: paused={game.Paused} pauseOpen={menu.PauseOpen} hudVisible={hud.Visible} listenerPaused={AudioListener.pause}");
            yield return new WaitForSecondsRealtime(0.5f);
            yield return Shoot(dir, "L2_pause.png", lines);
            menu.SetPaused(false);

            // 3. The x-ray: on every level with two rooms, the camera behind the chair looks across the shared
            // wall at an alerted inhabitant standing in the other room.
            int shot = 3;
            foreach (string id in new List<string>(game.LevelOrder))
            {
                game.LoadLevel(id);
                yield return Fixed(2);
                List<RoomDef> rooms = game.Def.AllRooms();
                FurnitureController chair = game.Furniture;
                RoomDef home = game.Def.RoomAt(chair.transform.position);
                RoomDef other = rooms.Find(r => r != home);
                if (other == null || game.MainInhabitant == null)
                {
                    continue;
                }
                Vector3 chairAt = YawMath.Planar(chair.transform.position);
                Vector3 there = new Vector3(other.X, 0f, other.Z);
                // Let the level title card fade first (real time).
                yield return new WaitForSecondsRealtime(5.2f);
                Inhabitant inhabitant = game.MainInhabitant;
                inhabitant.Pin(there, YawMath.YawOf(chairAt - there), 0f, true);
                inhabitant.Routine.Alert(chairAt, NoiseKind.Hop);
                game.Camera.SetView(YawMath.YawOf(there - chairAt), 24f);
                yield return Fixed(10);
                lines.Add($"xray {id}: inhabitant {inhabitant.Marker} at {there}, chair at {chairAt}");
                yield return Shoot(dir, $"L{shot}_xray_{id}.png", lines);
                shot++;
            }

            // 4. A "?" whose head projects where the M3 suspicion gauge was: M3.1 keeps the HUD band at the bottom.
            game.LoadLevel(game.FirstLevelId);
            yield return new WaitForSecondsRealtime(5.2f);
            {
                Inhabitant inhabitant = game.MainInhabitant;
                FurnitureController chair = game.Furniture;
                Vector3 chairAt = YawMath.Planar(chair.transform.position);
                inhabitant.Pin(inhabitant.Routine.Position, YawMath.YawOf(chairAt - inhabitant.Routine.Position), 0f, true);
                inhabitant.Routine.Alert(chairAt, NoiseKind.Hop);
                yield return Fixed(3);
                Canvas marker = hud.MarkerCanvases.Count > 0 ? hud.MarkerCanvases[0] : null;
                float height = marker != null ? marker.transform.position.y - inhabitant.transform.position.y : 2.1f;
                Camera cam = main.Camera;
                var under = new Vector2(Screen.width * 0.5f + 290f * Scale(), Screen.height - 70f * Scale());
                Ray ray = cam.ScreenPointToRay(under);
                if (Mathf.Abs(ray.direction.y) > 1e-3f)
                {
                    float t = (height - ray.origin.y) / ray.direction.y;
                    Vector3 spot = YawMath.Planar(ray.origin + ray.direction * t);
                    inhabitant.Pin(spot, YawMath.YawOf(chairAt - spot), 0f, true);
                    inhabitant.Routine.Alert(chairAt, NoiseKind.Hop);
                }
                yield return Fixed(10);
                Rect r = marker != null ? hud.ScreenRectOf((RectTransform)marker.transform) : Rect.zero;
                Rect band = hud.BandScreenRect;
                lines.Add($"marker: rect={r} band={band} overlap={r.Overlaps(band)} screen={Screen.width}x{Screen.height}");
                yield return Shoot(dir, $"L{shot}_marker_hud.png", lines);
                shot++;
            }

            // 5. The end screen: the last level won.
            string last = game.LevelOrder[game.LevelOrder.Count - 1];
            game.LoadLevel(last);
            yield return Fixed(2);
            {
                FurnitureController chair = game.Furniture;
                ZoneDef exit = game.Def.Exit;
                var exitCenter = new Vector3(exit.X, 0f, exit.Z);
                foreach (Inhabitant h in game.Level.Inhabitants)
                {
                    Vector3 at = h.Routine.Position;
                    h.Pin(at, YawMath.YawOf(at - exitCenter));
                }
                Vector3 approach = ExitApproach(game.Def, exitCenter);
                chair.Teleport(exitCenter - approach * 0.9f, YawMath.YawOf(approach));
                game.Camera.Snap();
                chair.ScriptedDirection = approach;
                int guard = 0;
                while (game.State == PlayState.Playing && guard++ < 200)
                {
                    yield return new WaitForFixedUpdate();
                }
                chair.ScriptedDirection = null;
            }
            yield return new WaitForSecondsRealtime(0.5f);
            lines.Add($"end: state={game.State} endVisible={hud.EndVisible} title='{hud.WinTitleText}' body='{hud.WinBodyText}'");
            yield return Shoot(dir, $"L{shot}_end.png", lines);
            shot++;

            // 6. Enter on the end screen (the UI submit of its selected button): back to the title.
            GameObject selected = EventSystem.current != null ? EventSystem.current.currentSelectedGameObject : null;
            lines.Add("end selection: " + (selected != null ? selected.name : "none"));
            if (selected != null)
            {
                ExecuteEvents.Execute(selected, new BaseEventData(EventSystem.current), ExecuteEvents.submitHandler);
            }
            yield return Fixed(5);
            yield return new WaitForSecondsRealtime(1f);
            lines.Add($"back: titleOpen={menu.TitleOpen} level={game.LevelId} paused={game.Paused}");
            yield return Shoot(dir, $"L{shot}_back_to_title.png", lines);

            File.WriteAllLines(Path.Combine(dir, "look.txt"), lines);
            Application.Quit(0);
        }

        private static float Scale()
        {
            // The HUD's CanvasScaler: 1920 x 1080 reference, width and height matched half and half.
            float w = Screen.width / 1920f;
            float h = Screen.height / 1080f;
            return Mathf.Sqrt(w * h);
        }

        private static IEnumerator Fixed(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        /// <summary>From the room center onto the doormat, axis aligned (as the probe does).</summary>
        private static Vector3 ExitApproach(LevelDef def, Vector3 exitCenter)
        {
            RoomDef room = def.RoomAt(exitCenter) ?? (def.AllRooms().Count > 0 ? def.AllRooms()[0] : null);
            Vector3 roomCenter = room != null ? new Vector3(room.X, 0f, room.Z) : Vector3.zero;
            Vector3 d = YawMath.Planar(exitCenter - roomCenter);
            Vector3 axis = Mathf.Abs(d.x) * (room != null ? room.SizeZ : 1f) >= Mathf.Abs(d.z) * (room != null ? room.SizeX : 1f)
                ? new Vector3(Mathf.Sign(d.x), 0f, 0f)
                : new Vector3(0f, 0f, Mathf.Sign(d.z));
            return axis.sqrMagnitude > 0f ? axis : Vector3.right;
        }

        private static IEnumerator Shoot(string dir, string file, List<string> lines)
        {
            yield return new WaitForEndOfFrame();
            Texture2D texture = ScreenCapture.CaptureScreenshotAsTexture();
            Color32[] pixels = texture.GetPixels32();
            double sum = 0;
            foreach (Color32 p in pixels)
            {
                sum += (0.2126 * p.r + 0.7152 * p.g + 0.0722 * p.b) / 255.0;
            }
            File.WriteAllBytes(Path.Combine(dir, file), texture.EncodeToPNG());
            lines.Add($"{file}: mean luminance {(pixels.Length > 0 ? sum / pixels.Length : 0):0.000}");
            Object.Destroy(texture);
        }
    }
}
