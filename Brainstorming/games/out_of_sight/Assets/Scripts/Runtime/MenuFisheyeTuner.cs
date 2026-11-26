using System;
using System.Globalization;
using System.IO;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// FISHEYEUI (docs/next/progress/FISHEYE.md): on Windows (standalone player and the editor, never Android), the "I" key
    /// toggles a panel of sliders along the bottom of the title's main page that changes <see cref="MenuFisheye"/>'s
    /// values live (one slider per key of menu_camera.json), with Save (writes the file, "_help" kept), Reset (the built-in
    /// defaults) and Copy (the values as JSON on the clipboard).
    /// - While the panel is shown, <see cref="MenuFisheye.HoldFile"/> pauses the 2 s file check, so the file never snaps
    ///   the sliders back; Save writes the file and reads it again.
    /// - Hidden, the panel's objects are inactive: no raycast, no navigation target. Shown, its sliders and buttons have
    ///   no navigation links and a click on them hands the selection back to the menu button selected before as soon as
    ///   the mouse button is up, so the keyboard and the gamepad keep driving the menu.
    /// - It hides itself when the title's main page goes away (Jouer, Niveaux, Options, Crédits, a level).
    /// - Unsaved values stay in use until the title next opens (the file is read again then).
    /// </summary>
    [DefaultExecutionOrder(270)] // after MenuFisheye (260)
    public sealed class MenuFisheyeTuner : MonoBehaviour
    {
        /// <summary>The panel exists on a Windows player and in the editor only.</summary>
        public static bool Supported => Application.isEditor || Application.platform == RuntimePlatform.WindowsPlayer;

        /// <summary>True while the panel is shown.</summary>
        public bool Shown { get; private set; }

        private static readonly string[] Keys =
        {
            "fisheyeStrength", "fisheyeZoom", "fisheyeVignette", "peripheralBlur", "peripheralBlurRadius", "peripheralBlurMotion",
        };
        private static readonly float[] Min = { 0f, MenuCameraSettings.MinZoom, 0f, 0f, 0f, 0f };
        private static readonly float[] Max = { MenuCameraSettings.MaxStrength, MenuCameraSettings.MaxZoom, 1f, 1f, 1f, 1f };

        private static readonly Color PanelColor = new Color(0.06f, 0.045f, 0.04f, 0.84f);
        private static readonly Color Ink = new Color(1f, 0.94f, 0.82f, 1f);
        private static readonly Color SoftInk = new Color(1f, 0.94f, 0.82f, 0.65f);
        private static readonly Color Track = new Color(0.22f, 0.18f, 0.16f, 0.95f);
        private static readonly Color Red = new Color(0.82f, 0.2f, 0.16f, 1f);
        private static readonly Color ButtonColor = new Color(0.32f, 0.23f, 0.18f, 0.95f);

        // Reference pixels (1920 x 1080, like the menu canvas): the panel starts right of the title's button column
        // (150 + 420), so it never covers a menu button.
        private const float PanelLeft = 620f;
        private const float PanelRight = 24f;
        private const float PanelBottom = 12f;
        private const float PanelHeight = 146f;
        private const float ButtonsWidth = 130f;

        private readonly float[] values = new float[6];
        private readonly Slider[] sliders = new Slider[6];
        private readonly Text[] readouts = new Text[6];
        private MenuFisheye fisheye;
        private Menu menu;
        private GameObject root;
        private Text status;
        private Font font;
        private GameObject lastMenuSelection;

        /// <summary>Adds the tuner next to <paramref name="fisheye"/> (once), on a supported platform only.</summary>
        public static MenuFisheyeTuner Attach(MenuFisheye fisheye)
        {
            if (fisheye == null || !Supported)
            {
                return null;
            }
            MenuFisheyeTuner tuner = fisheye.GetComponent<MenuFisheyeTuner>();
            if (tuner == null)
            {
                tuner = fisheye.gameObject.AddComponent<MenuFisheyeTuner>();
            }
            return tuner;
        }

        private void Awake()
        {
            fisheye = GetComponent<MenuFisheye>();
        }

        private void OnDisable()
        {
            if (Shown)
            {
                Hide();
            }
        }

        private void OnDestroy()
        {
            if (root != null)
            {
                Destroy(root);
            }
        }

        /// <summary>The title's main page is open (not the level select, Options, Credits, the pause menu or a level).</summary>
        private bool Allowed => menu != null && fisheye != null && menu.TitleOpen && menu.TitlePageShown && !menu.PauseOpen
            && !menu.LevelSelectOpen && !menu.OptionsOpen && !menu.CreditsOpen;

        private void Update()
        {
            if (Shown && !Allowed)
            {
                Hide();
            }
            Keyboard keyboard = Keyboard.current;
            if (keyboard == null || !keyboard.iKey.wasPressedThisFrame)
            {
                return;
            }
            // Found on the first press only: no search per frame.
            if (menu == null)
            {
                menu = FindAnyObjectByType<Menu>();
            }
            if (Shown)
            {
                Hide();
            }
            else if (Allowed)
            {
                Show();
            }
        }

        private void LateUpdate()
        {
            EventSystem events = EventSystem.current;
            if (!Shown || events == null)
            {
                return;
            }
            GameObject selected = events.currentSelectedGameObject;
            if (selected != null && selected.transform.IsChildOf(root.transform))
            {
                // A slider or a button of the panel took the selection with a click: give it back to the menu once the
                // mouse button is up, so the arrows and the gamepad keep moving through the menu buttons.
                Mouse mouse = Mouse.current;
                if (mouse == null || !mouse.leftButton.isPressed)
                {
                    events.SetSelectedGameObject(lastMenuSelection != null && lastMenuSelection.activeInHierarchy ? lastMenuSelection : null);
                }
            }
            else
            {
                lastMenuSelection = selected;
            }
        }

        private void Show()
        {
            if (root == null)
            {
                Build();
            }
            Sync(fisheye.Settings);
            SetStatus("I hides. Changes are live; Save writes menu_camera.json.");
            root.SetActive(true);
            fisheye.HoldFile = true;
            Shown = true;
        }

        private void Hide()
        {
            Shown = false;
            if (fisheye != null)
            {
                fisheye.HoldFile = false;
            }
            if (root == null)
            {
                return;
            }
            EventSystem events = EventSystem.current;
            GameObject selected = events != null ? events.currentSelectedGameObject : null;
            if (selected != null && selected.transform.IsChildOf(root.transform))
            {
                events.SetSelectedGameObject(lastMenuSelection != null && lastMenuSelection.activeInHierarchy ? lastMenuSelection : null);
            }
            root.SetActive(false);
        }

        private MenuCameraSettings Current => MenuCameraSettings.From(values[0], values[1], values[2], values[3], values[4], values[5]);

        private void OnSlider(int index, float value)
        {
            values[index] = value;
            readouts[index].text = Readout(index);
            // Read by MenuFisheye's beginCameraRendering hook: the change shows on this very frame.
            fisheye.Override(Current);
        }

        private void Sync(MenuCameraSettings s)
        {
            values[0] = s.FisheyeStrength;
            values[1] = s.FisheyeZoom;
            values[2] = s.FisheyeVignette;
            values[3] = s.PeripheralBlur;
            values[4] = s.PeripheralBlurRadius;
            values[5] = s.PeripheralBlurMotion;
            for (int i = 0; i < values.Length; i++)
            {
                if (sliders[i] != null)
                {
                    sliders[i].SetValueWithoutNotify(values[i]);
                    readouts[i].text = Readout(i);
                }
            }
        }

        private string Readout(int i)
        {
            return string.Format(CultureInfo.InvariantCulture, "{0:0.00}   ({1:0.#} - {2:0.#})", values[i], Min[i], Max[i]);
        }

        private void Save()
        {
            string path = MenuCameraSettings.FilePath;
            if (string.IsNullOrEmpty(path))
            {
                SetStatus("No menu_camera.json on this platform.");
                return;
            }
            try
            {
                string existing = File.Exists(path) ? File.ReadAllText(path) : null;
                File.WriteAllText(path, Current.ToJson(existing));
                // Read it back: the file's write time is now the known one, so the 2 s check will not reload it.
                fisheye.Reload();
                Sync(fisheye.Settings);
                SetStatus("Saved to " + path);
                Debug.Log($"[MenuCamera] saved {path}: {fisheye.Settings}");
            }
            catch (Exception e)
            {
                SetStatus("Save failed: " + e.Message);
                Debug.LogWarning($"[MenuCamera] cannot save {path}: {e.Message}");
            }
        }

        private void ResetValues()
        {
            fisheye.Override(MenuCameraSettings.Defaults);
            Sync(MenuCameraSettings.Defaults);
            SetStatus("Built-in defaults (not saved).");
        }

        private void Copy()
        {
            GUIUtility.systemCopyBuffer = Current.ToJson(null);
            SetStatus("Values copied to the clipboard as JSON.");
        }

        private void SetStatus(string text)
        {
            if (status != null)
            {
                status.text = "Menu fish-eye. " + text;
            }
        }

        // ---- UI construction (code only, like the rest of the menu) ----

        private void Build()
        {
            font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            root = new GameObject("FisheyeTuner", typeof(RectTransform));
            var canvas = root.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 60; // above the menu (50)
            var scaler = root.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920f, 1080f);
            scaler.matchWidthOrHeight = 0.5f;
            root.AddComponent<GraphicRaycaster>();

            RectTransform panel = NewRect("Panel", root.transform);
            panel.anchorMin = new Vector2(0f, 0f);
            panel.anchorMax = new Vector2(1f, 0f);
            panel.pivot = new Vector2(0.5f, 0f);
            panel.offsetMin = new Vector2(PanelLeft, PanelBottom);
            panel.offsetMax = new Vector2(-PanelRight, PanelBottom + PanelHeight);
            panel.gameObject.AddComponent<Image>().color = PanelColor;

            status = NewText(panel, "Status", 16, SoftInk, TextAnchor.MiddleLeft);
            Fill(status.rectTransform, new Vector2(0f, 1f), new Vector2(1f, 1f), new Vector2(14f, -26f), new Vector2(-(ButtonsWidth + 24f), -4f));

            RectTransform grid = NewRect("Sliders", panel);
            Fill(grid, Vector2.zero, Vector2.one, new Vector2(8f, 8f), new Vector2(-(ButtonsWidth + 24f), -28f));
            for (int i = 0; i < Keys.Length; i++)
            {
                int col = i % 3;
                int row = i / 3;
                RectTransform cell = NewRect(Keys[i], grid);
                Fill(cell, new Vector2(col / 3f, 1f - (row + 1) / 2f), new Vector2((col + 1) / 3f, 1f - row / 2f), new Vector2(8f, 2f), new Vector2(-8f, -2f));
                BuildCell(cell, i);
            }

            RectTransform buttons = NewRect("Buttons", panel);
            Fill(buttons, new Vector2(1f, 0f), new Vector2(1f, 1f), new Vector2(-(ButtonsWidth + 12f), 10f), new Vector2(-12f, -10f));
            NewButton(buttons, "Save", 0, Save);
            NewButton(buttons, "Reset", 1, ResetValues);
            NewButton(buttons, "Copy", 2, Copy);
            root.SetActive(false);
        }

        private void BuildCell(RectTransform cell, int index)
        {
            Text label = NewText(cell, "Label", 17, Ink, TextAnchor.MiddleLeft);
            label.text = Keys[index];
            Fill(label.rectTransform, new Vector2(0f, 0.5f), Vector2.one, Vector2.zero, Vector2.zero);
            Text readout = NewText(cell, "Value", 17, SoftInk, TextAnchor.MiddleRight);
            Fill(readout.rectTransform, new Vector2(0f, 0.5f), Vector2.one, Vector2.zero, Vector2.zero);
            readouts[index] = readout;

            RectTransform area = NewRect("Slider", cell);
            Fill(area, Vector2.zero, new Vector2(1f, 0.5f), new Vector2(0f, 2f), new Vector2(0f, -2f));
            Image track = NewRect("Background", area).gameObject.AddComponent<Image>();
            track.color = Track;
            Fill(track.rectTransform, new Vector2(0f, 0.3f), new Vector2(1f, 0.7f), Vector2.zero, Vector2.zero);
            RectTransform fillArea = NewRect("Fill Area", area);
            Fill(fillArea, new Vector2(0f, 0.3f), new Vector2(1f, 0.7f), new Vector2(5f, 0f), new Vector2(-9f, 0f));
            Image fill = NewRect("Fill", fillArea).gameObject.AddComponent<Image>();
            fill.color = Red;
            fill.rectTransform.sizeDelta = new Vector2(4f, 0f);
            RectTransform handleArea = NewRect("Handle Slide Area", area);
            Fill(handleArea, Vector2.zero, Vector2.one, new Vector2(7f, 0f), new Vector2(-7f, 0f));
            Image handle = NewRect("Handle", handleArea).gameObject.AddComponent<Image>();
            handle.color = Ink;
            handle.rectTransform.sizeDelta = new Vector2(14f, 0f);

            Slider slider = area.gameObject.AddComponent<Slider>();
            slider.fillRect = fill.rectTransform;
            slider.handleRect = handle.rectTransform;
            slider.targetGraphic = handle;
            slider.direction = Slider.Direction.LeftToRight;
            slider.minValue = Min[index];
            slider.maxValue = Max[index];
            slider.navigation = new Navigation { mode = Navigation.Mode.None };
            slider.onValueChanged.AddListener(v => OnSlider(index, v));
            sliders[index] = slider;
        }

        private void NewButton(RectTransform parent, string label, int index, Action action)
        {
            RectTransform rect = NewRect(label, parent);
            float top = 1f - index / 3f;
            float bottom = 1f - (index + 1) / 3f;
            Fill(rect, new Vector2(0f, bottom), new Vector2(1f, top), new Vector2(0f, 3f), new Vector2(0f, -3f));
            Image image = rect.gameObject.AddComponent<Image>();
            image.color = ButtonColor;
            Button button = rect.gameObject.AddComponent<Button>();
            button.targetGraphic = image;
            button.navigation = new Navigation { mode = Navigation.Mode.None };
            button.onClick.AddListener(() => action());
            Text text = NewText(rect, "Label", 18, Ink, TextAnchor.MiddleCenter);
            text.text = label;
            Fill(text.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
        }

        private Text NewText(Transform parent, string name, int size, Color color, TextAnchor alignment)
        {
            Text text = NewRect(name, parent).gameObject.AddComponent<Text>();
            text.font = font;
            text.fontSize = size;
            text.color = color;
            text.alignment = alignment;
            text.raycastTarget = false;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            return text;
        }

        private static RectTransform NewRect(string name, Transform parent)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            return (RectTransform)go.transform;
        }

        private static void Fill(RectTransform rect, Vector2 anchorMin, Vector2 anchorMax, Vector2 offsetMin, Vector2 offsetMax)
        {
            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.offsetMin = offsetMin;
            rect.offsetMax = offsetMax;
        }
    }
}
