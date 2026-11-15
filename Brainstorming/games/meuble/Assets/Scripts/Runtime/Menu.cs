using System.Collections;
using System.Collections.Generic;
using System.IO;
using Meuble.Core;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Meuble
{
    /// <summary>
    /// Title screen and pause menu (docs/CONTRACT_M3.md 6).
    /// - The title shows UN, DEUX, TROIS, MEUBLE, Jouer, Quitter and the credits over the first level of
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

        /// <summary>The cursor must stay free: a menu is open, or the end screen offers its button.</summary>
        public bool WantsCursor => IsOpen || (Hud != null && Hud.EndVisible);

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

        /// <summary>Niveaux: opens the level select over the title (ignored when the title is not up).</summary>
        public void OpenLevelSelect()
        {
            if (!TitleOpen || LevelSelectOpen || LevelSelect == null)
            {
                return;
            }
            LevelSelectOpen = true;
            Apply();
            SelectLater(null);
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

        private static readonly Color Cream = new Color(1f, 0.92f, 0.75f, 1f);

        public void Init(GameState game, Hud hud, OrbitCamera camera, Sfx sfx)
        {
            Game = game;
            Hud = hud;
            Camera = camera;
            Sfx = sfx;
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
            Apply();
        }

        private void BuildTitle()
        {
            titleCanvas = Panel("Title");
            // The level shows through: a light dim, darker toward the edges. The panel holds the upper half; the
            // showcase camera frames the red chair in the lower third, under the buttons (OrbitCamera).
            Stretch(NewImage(titleCanvas.transform, "Dim", null, new Color(0.03f, 0.03f, 0.05f, 0.22f)).rectTransform);
            Stretch(NewImage(titleCanvas.transform, "Edges", ProceduralArt.Vignette, new Color(0.02f, 0.02f, 0.03f, 0.6f)).rectTransform);
            // M5: the band grows down by one button row for Niveaux (the chair still shows in the lower third).
            Image band = NewImage(titleCanvas.transform, "Band", ProceduralArt.Rounded, new Color(0.06f, 0.06f, 0.08f, 0.66f));
            band.type = Image.Type.Sliced;
            Place(band.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, 150f), new Vector2(1320f, 620f));
            Image chair = NewImage(titleCanvas.transform, "Emblem", ProceduralArt.Chair, Color.white);
            chair.preserveAspect = true;
            Place(chair.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, 372f), new Vector2(118f, 118f));
            Text title = NewText(titleCanvas.transform, "Title", Strings.Title, 100, Cream);
            Place(title.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, 244f), new Vector2(1700f, 130f));
            PlayButton = Hud.MenuButton(titleCanvas.transform, "Play", Strings.TitlePlay, font, Labels);
            Place((RectTransform)PlayButton.transform, new Vector2(0.5f, 0.5f), new Vector2(0f, 104f), new Vector2(480f, 88f));
            LevelsButton = Hud.MenuButton(titleCanvas.transform, "Levels", Strings.TitleLevels, font, Labels);
            Place((RectTransform)LevelsButton.transform, new Vector2(0.5f, 0.5f), new Vector2(0f, 2f), new Vector2(480f, 88f));
            QuitButton = Hud.MenuButton(titleCanvas.transform, "Quit", Strings.TitleQuit, font, Labels);
            Place((RectTransform)QuitButton.transform, new Vector2(0.5f, 0.5f), new Vector2(0f, -100f), new Vector2(480f, 88f));
            Text credits = NewText(titleCanvas.transform, "Credits", Strings.TitleCredits, 28, new Color(1f, 1f, 1f, 0.8f));
            Place(credits.rectTransform, new Vector2(0.5f, 0f), new Vector2(0f, 36f), new Vector2(1800f, 44f));
            Chain(PlayButton, LevelsButton, QuitButton);
            PlayButton.onClick.AddListener(() =>
            {
                Click();
                Play();
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
        }

        private void BuildPause()
        {
            pauseCanvas = Panel("Pause");
            Stretch(NewImage(pauseCanvas.transform, "Dim", null, new Color(0.03f, 0.03f, 0.05f, 0.6f)).rectTransform);
            Text title = NewText(pauseCanvas.transform, "PauseTitle", Strings.PauseTitle, 130, Cream);
            Place(title.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0f, 220f), new Vector2(1600f, 170f));
            ResumeButton = Hud.MenuButton(pauseCanvas.transform, "Resume", Strings.PauseResume, font, Labels);
            Place((RectTransform)ResumeButton.transform, new Vector2(0.5f, 0.5f), new Vector2(0f, 40f), new Vector2(520f, 96f));
            RestartButton = Hud.MenuButton(pauseCanvas.transform, "Restart", Strings.PauseRestart, font, Labels);
            Place((RectTransform)RestartButton.transform, new Vector2(0.5f, 0.5f), new Vector2(0f, -80f), new Vector2(520f, 96f));
            MainMenuButton = Hud.MenuButton(pauseCanvas.transform, "MainMenu", Strings.PauseMenu, font, Labels);
            Place((RectTransform)MainMenuButton.transform, new Vector2(0.5f, 0.5f), new Vector2(0f, -200f), new Vector2(520f, 96f));
            Chain(ResumeButton, RestartButton, MainMenuButton);
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
            PauseOpen = false;
            TitleOpen = true;
            LevelSelectOpen = false;
            string first = Game.FirstLevelId;
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
            if (!TitleOpen || LevelSelectOpen)
            {
                return;
            }
            TitleOpen = false;
            closedFrame = Time.frameCount;
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
            PauseOpen = false;
            OpenTitle(true);
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
        /// The default button of what is open (the level select's first unlocked card, title, pause, end screen), or null.
        /// </summary>
        public Selectable DefaultButton => LevelSelectOpen && LevelSelect != null ? LevelSelect.DefaultSelectable
            : TitleOpen ? PlayButton : PauseOpen ? ResumeButton : Hud != null && Hud.EndVisible ? Hud.EndButton : null;

        private void Update()
        {
            // M5: Escape or gamepad B leaves the level select. Read every frame, so a press made elsewhere never waits
            // for the select to open.
            if (InputReader.BackPressed() && LevelSelectOpen)
            {
                Click();
                CloseLevelSelect();
            }
            EventSystem events = EventSystem.current;
            Selectable wanted = pendingFocus != null && IsShown(pendingFocus.gameObject) ? pendingFocus : DefaultButton;
            if (events == null || wanted == null || Time.frameCount <= openedFrame)
            {
                return;
            }
            pendingFocus = null;
            GameObject current = events.currentSelectedGameObject;
            if (current == null || !IsShown(current))
            {
                events.SetSelectedGameObject(wanted.gameObject);
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
            bool open = IsOpen;
            if (!TitleOpen)
            {
                LevelSelectOpen = false;
            }
            SetEnabled(titleCanvas, TitleOpen && !LevelSelectOpen);
            SetEnabled(pauseCanvas, PauseOpen);
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

        /// <summary>Back in the game: a player captures the cursor again (the editor leaves it to the click).</summary>
        private void CaptureCursor()
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
