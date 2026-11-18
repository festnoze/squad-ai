using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// M7 (docs/CONTRACT_M7.md 1.5): the touch controls, on their own overlay canvas, shown while
    /// <see cref="InputReader.TouchUIActive"/> holds and the game is not paused (the menus are uGUI, driven by tap through
    /// the InputSystemUIInputModule). Left half of the screen: a floating stick that appears where the thumb lands and
    /// moves the furniture like the left stick. Right half: a drag orbits the camera. Bottom right: the action button (E)
    /// and the careful toggle; top right: the pause button.
    ///
    /// Nothing here is a raycast target: the fingers are read through <see cref="InputReader.ReadTouches"/> (the real
    /// touchscreen plus the fingers a test injects) and hit tested here, so the overlay never takes a tap from a menu, and
    /// with no touch it writes nothing (the keyboard, the mouse and the gamepad are untouched). The object is created once
    /// per run and survives scene loads; every per test state lives in InputReader and is cleared by ResetInjections.
    /// </summary>
    [DefaultExecutionOrder(-50)]
    public sealed class TouchControls : MonoBehaviour
    {
        public static TouchControls Instance { get; private set; }

        /// <summary>The overlay shows (tests).</summary>
        public bool Visible => overlay != null && overlay.activeSelf;

        public RectTransform ActionButton { get; private set; }
        public RectTransform CarefulButton { get; private set; }
        public RectTransform PauseButton { get; private set; }

        /// <summary>The screen pixel at the centre of <paramref name="button"/> (tests tap there).</summary>
        public static Vector2 ScreenCenter(RectTransform button)
        {
            return RectTransformUtility.WorldToScreenPoint(null, button.TransformPoint(button.rect.center));
        }

        private const float ReferenceHeight = 1080f;
        private static readonly Color Idle = new Color(1f, 1f, 1f, 0.22f);
        private static readonly Color Held = new Color(1f, 1f, 1f, 0.45f);
        private static readonly Color CarefulOn = new Color(0.98f, 0.78f, 0.3f, 0.75f);

        private GameObject overlay;
        private RectTransform stickBase;
        private RectTransform stickKnob;
        private Image stickBaseImage;
        private Image stickKnobImage;
        private Image carefulImage;

        private readonly List<InputReader.TouchPoint> points = new List<InputReader.TouchPoint>();
        private readonly HashSet<int> known = new HashSet<int>();
        private readonly HashSet<int> current = new HashSet<int>();
        // Fingers that steer nothing until they lift: those on a button, those down while the overlay was hidden, extra ones.
        private readonly HashSet<int> ignored = new HashSet<int>();
        private int stickFinger = int.MinValue;
        private Vector2 stickOrigin;
        private int orbitFinger = int.MinValue;
        private Vector2 orbitLast;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Create()
        {
            if (Instance != null)
            {
                return;
            }
            var go = new GameObject("TouchControls");
            DontDestroyOnLoad(go);
            go.AddComponent<TouchControls>();
        }

        private void Awake()
        {
            Instance = this;
            Build();
            overlay.SetActive(false);
        }

        private void OnDestroy()
        {
            if (Instance == this)
            {
                Instance = null;
            }
        }

        private void Update()
        {
            bool show = InputReader.TouchUIActive && !GamePause.IsPaused;
            if (show != overlay.activeSelf)
            {
                overlay.SetActive(show);
            }
            InputReader.ReadTouches(points);
            current.Clear();
            foreach (InputReader.TouchPoint p in points)
            {
                current.Add(p.Id);
            }
            // Lifted fingers free their role.
            foreach (int id in known)
            {
                if (!current.Contains(id))
                {
                    ignored.Remove(id);
                    if (id == stickFinger)
                    {
                        stickFinger = int.MinValue;
                    }
                    if (id == orbitFinger)
                    {
                        orbitFinger = int.MinValue;
                    }
                }
            }
            known.Clear();
            known.UnionWith(current);

            if (!show)
            {
                // Hidden (no touch, or a menu is open): every finger down now is ignored until it lifts, and nothing steers.
                ignored.UnionWith(current);
                stickFinger = int.MinValue;
                orbitFinger = int.MinValue;
                InputReader.SetTouchStick(Vector2.zero);
                InputReader.SetTouchLook(Vector2.zero);
                if (!InputReader.TouchUIActive)
                {
                    InputReader.SetTouchCareful(false);
                }
                return;
            }

            float scale = Mathf.Max(1f, Screen.height) / ReferenceHeight;
            Vector2 look = Vector2.zero;
            Vector2 stick = Vector2.zero;
            foreach (InputReader.TouchPoint p in points)
            {
                if (ignored.Contains(p.Id))
                {
                    continue;
                }
                if (p.Id == stickFinger)
                {
                    stick = (p.Position - stickOrigin) / (Tuning.TouchStickRadius * scale);
                    PlaceStick(stickOrigin, stickOrigin + Vector2.ClampMagnitude(p.Position - stickOrigin, Tuning.TouchStickRadius * scale));
                }
                else if (p.Id == orbitFinger)
                {
                    look += (p.Position - orbitLast) / scale;
                    orbitLast = p.Position;
                }
                else
                {
                    Land(p);
                    if (p.Id == stickFinger)
                    {
                        PlaceStick(stickOrigin, stickOrigin);
                    }
                }
            }
            InputReader.SetTouchStick(stick);
            InputReader.SetTouchLook(look);

            bool stickHeld = stickFinger != int.MinValue;
            stickBaseImage.color = stickHeld ? Held : Idle;
            stickKnobImage.color = stickHeld ? Held : Idle;
            if (!stickHeld)
            {
                stickBase.anchoredPosition = new Vector2(300f, 330f);
                stickKnob.anchoredPosition = stickBase.anchoredPosition;
            }
            carefulImage.color = InputReader.TouchCareful ? CarefulOn : Idle;
        }

        /// <summary>A finger lands: a button, else the stick on the left half or the orbit on the right half.</summary>
        private void Land(InputReader.TouchPoint p)
        {
            if (Hit(ActionButton, p.Position))
            {
                ignored.Add(p.Id);
                InputReader.PressTouchAction();
                return;
            }
            if (Hit(CarefulButton, p.Position))
            {
                ignored.Add(p.Id);
                InputReader.SetTouchCareful(!InputReader.TouchCareful); // MUTATION:TOUCH_CAREFUL_TOGGLE
                return;
            }
            if (Hit(PauseButton, p.Position))
            {
                ignored.Add(p.Id);
                InputReader.PressTouchPause();
                return;
            }
            bool left = p.Position.x < Screen.width * 0.5f; // MUTATION:TOUCH_HALF_SPLIT
            if (left && stickFinger == int.MinValue)
            {
                stickFinger = p.Id;
                stickOrigin = p.Position;
            }
            else if (!left && orbitFinger == int.MinValue)
            {
                orbitFinger = p.Id;
                orbitLast = p.Position;
            }
            else
            {
                ignored.Add(p.Id);
            }
        }

        private static bool Hit(RectTransform button, Vector2 screen)
        {
            return RectTransformUtility.RectangleContainsScreenPoint(button, screen, null);
        }

        private void PlaceStick(Vector2 baseScreen, Vector2 knobScreen)
        {
            stickBase.position = baseScreen;
            stickKnob.position = knobScreen;
        }

        // ----- Construction -----

        private void Build()
        {
            overlay = new GameObject("TouchOverlay", typeof(RectTransform));
            overlay.transform.SetParent(transform, false);
            var canvas = overlay.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            // Over the HUD (10 and 20), under the menus (50): hidden anyway while a menu pauses the game.
            canvas.sortingOrder = 30;
            var scaler = overlay.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920f, ReferenceHeight);
            // Matched on the height: a size here is that many pixels on a 1080 pixel high screen, whatever its width.
            scaler.matchWidthOrHeight = 1f;
            Font font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

            float stickSize = Tuning.TouchStickRadius * 2f;
            stickBase = Disc("StickBase", new Vector2(0f, 0f), new Vector2(300f, 330f), stickSize, out stickBaseImage);
            stickKnob = Disc("StickKnob", new Vector2(0f, 0f), new Vector2(300f, 330f), stickSize * 0.45f, out stickKnobImage);

            ActionButton = Disc("ActionButton", new Vector2(1f, 0f), new Vector2(-200f, 330f), Tuning.TouchActionSize, out _);
            Label(ActionButton, Strings.TouchAction, 34, font);
            CarefulButton = Disc("CarefulButton", new Vector2(1f, 0f), new Vector2(-420f, 230f), Tuning.TouchButtonSize, out carefulImage);
            Label(CarefulButton, Strings.TouchCareful, 28, font);
            PauseButton = Disc("PauseButton", new Vector2(1f, 1f), new Vector2(-130f, -130f), Tuning.TouchButtonSize, out _);
            Label(PauseButton, Strings.TouchPause, 48, font);
        }

        private RectTransform Disc(string name, Vector2 anchor, Vector2 position, float size, out Image image)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(overlay.transform, false);
            image = go.AddComponent<Image>();
            image.sprite = ProceduralArt.Disc;
            image.color = Idle;
            image.raycastTarget = false;
            var rt = (RectTransform)go.transform;
            rt.anchorMin = anchor;
            rt.anchorMax = anchor;
            rt.pivot = new Vector2(0.5f, 0.5f);
            rt.sizeDelta = new Vector2(size, size);
            rt.anchoredPosition = position;
            return rt;
        }

        private static void Label(RectTransform parent, string value, int size, Font font)
        {
            var go = new GameObject("Label", typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var text = go.AddComponent<Text>();
            text.font = font;
            text.fontSize = size;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = new Color(1f, 1f, 1f, 0.95f);
            text.text = value;
            text.raycastTarget = false;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            var shadow = go.AddComponent<Shadow>();
            shadow.effectColor = new Color(0f, 0f, 0f, 0.65f);
            var rt = (RectTransform)go.transform;
            rt.anchorMin = Vector2.zero;
            rt.anchorMax = Vector2.one;
            rt.offsetMin = Vector2.zero;
            rt.offsetMax = Vector2.zero;
        }
    }
}
