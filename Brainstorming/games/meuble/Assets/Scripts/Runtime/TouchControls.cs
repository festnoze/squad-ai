using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// M7 (docs/CONTRACT_M7.md 1.5): the touch controls, on their own overlay canvas, shown while
    /// <see cref="InputReader.TouchUIActive"/> holds, the game is not paused and no fail or win panel is up (the menus and
    /// those panels are uGUI, driven by tap through
    /// the InputSystemUIInputModule). Left half of the screen: a floating stick that appears where the thumb lands and
    /// moves the furniture like the left stick. Right half: a drag orbits the camera. Bottom right: the careful toggle;
    /// top right: the pause button. Task DOORAUTO: there is no action button any more (doors and wardrobes open by pushing
    /// the stick toward them); the floor lamp is switched by a tap on the player lamp itself (<see cref="OnPlayerLamp"/>),
    /// which is the E key.
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

        // STARTFIX: a tap outside the buttons (a stick or orbit finger that lifts soon, having barely travelled) is a start
        // press: it releases a held level without moving. A drag (orbit) or a stick push past the slop is never a tap.
        private const float TapSlop = 20f; // pixels of a 1080 pixel high screen, under the stick dead zone (0.2 x 120)
        private const float TapMaxSeconds = 0.35f;

        private struct Tap
        {
            public Vector2 Origin;
            public float Landed;
            public bool Travelled;
        }

        private readonly Dictionary<int, Tap> taps = new Dictionary<int, Tap>();

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
            // End panel emphasis (2026-11-19): hidden under the fail and win panels too. This overlay draws over the HUD
            // (sorting 30 over 20), and on a 20:9 phone the idle stick sat over Next level and the careful toggle over
            // Menu; a tap there also toggled careful, as the overlay reads every finger itself.
            Hud hud = Main.Instance != null ? Main.Instance.Hud : null;
            bool endPanel = hud != null && (hud.FailVisible || hud.WinVisible);
            bool show = InputReader.TouchUIActive && !GamePause.IsPaused && !endPanel;
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
                    if (taps.TryGetValue(id, out Tap tap))
                    {
                        taps.Remove(id);
                        if (!tap.Travelled && Time.unscaledTime - tap.Landed <= TapMaxSeconds) // MUTATION:TOUCH_TAP_START
                        {
                            // DOORAUTO: a tap on the player lamp switches it (the E key, also a start input); any other
                            // tap is the start press.
                            if (OnPlayerLamp(tap.Origin))
                            {
                                InputReader.PressTouchAction();
                            }
                            else
                            {
                                InputReader.PressTouchStart();
                            }
                        }
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
                taps.Clear();
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
                if (taps.TryGetValue(p.Id, out Tap tracked) && !tracked.Travelled
                    && (p.Position - tracked.Origin).sqrMagnitude > TapSlop * scale * TapSlop * scale)
                {
                    tracked.Travelled = true;
                    taps[p.Id] = tracked;
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

        /// <summary>
        /// A finger lands: a button, else the stick on the left half or the orbit on the right half (a short tap of either,
        /// on lift: the player lamp's switch, or the start press).
        /// </summary>
        private void Land(InputReader.TouchPoint p)
        {
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
                taps[p.Id] = new Tap { Origin = p.Position, Landed = Time.unscaledTime };
            }
            else if (!left && orbitFinger == int.MinValue)
            {
                orbitFinger = p.Id;
                orbitLast = p.Position;
                taps[p.Id] = new Tap { Origin = p.Position, Landed = Time.unscaledTime };
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

        /// <summary>
        /// Task DOORAUTO: the screen rectangle (pixels, origin bottom left) of the player furniture's box as the game camera
        /// sees it, grown by <see cref="Tuning.TouchLampTapMargin"/> pixels of a 1080 pixel high screen, while the player body
        /// is a floor lamp whose switch the rules allow (GameRules.Lamp) and the box is in front of the camera. False
        /// otherwise (any other body, no level, no camera).
        /// </summary>
        public static bool PlayerLampScreenRect(out Rect rect)
        {
            rect = default;
            Main main = Main.Instance;
            GameState game = main != null ? main.Game : null;
            FurnitureController f = game != null ? game.Furniture : null;
            Camera view = main != null ? main.Camera : null;
            if (f == null || view == null || f.Body == null || !f.Body.HasLight || f.Lamp == null || f.Hidden
                || f.Rules == null || !f.Rules.Lamp)
            {
                return false;
            }
            Vector3 size = f.Size;
            Vector3 c = f.transform.position + Vector3.up * (size.y * 0.5f);
            Quaternion r = Quaternion.Euler(0f, f.Yaw, 0f);
            float minX = float.MaxValue, minY = float.MaxValue, maxX = float.MinValue, maxY = float.MinValue;
            for (int k = 0; k < 8; k++)
            {
                var corner = new Vector3((k & 1) == 0 ? -0.5f : 0.5f, (k & 2) == 0 ? -0.5f : 0.5f, (k & 4) == 0 ? -0.5f : 0.5f);
                Vector3 s = view.WorldToScreenPoint(c + r * Vector3.Scale(corner, size));
                if (s.z <= 0f)
                {
                    return false;
                }
                minX = Mathf.Min(minX, s.x);
                minY = Mathf.Min(minY, s.y);
                maxX = Mathf.Max(maxX, s.x);
                maxY = Mathf.Max(maxY, s.y);
            }
            float margin = Tuning.TouchLampTapMargin * Mathf.Max(1f, Screen.height) / ReferenceHeight;
            rect = Rect.MinMaxRect(minX - margin, minY - margin, maxX + margin, maxY + margin);
            return true;
        }

        /// <summary>Task DOORAUTO: a tap at <paramref name="screen"/> (pixels) lands on the player lamp (<see cref="PlayerLampScreenRect"/>).</summary>
        public static bool OnPlayerLamp(Vector2 screen)
        {
            return PlayerLampScreenRect(out Rect rect) && rect.Contains(screen); // MUTATION:TOUCH_LAMP_TAP
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
