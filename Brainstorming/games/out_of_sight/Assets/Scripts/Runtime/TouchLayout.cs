using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// BIGBUTTONS (docs/next/progress/BIGBUTTONS.md): the switch and the helpers of the touch layout of the menus. While
    /// <see cref="Active"/> holds, the title page, the pause menu, the Options, Credits and Shop pages (Menu, ShopPage) and
    /// the fail, win and end panels (Hud) lay their buttons out bigger and rearranged for fingers; otherwise they keep
    /// their PC layout exactly. Each screen polls a <see cref="Watch"/> once a frame and lays itself out again when it says so.
    /// </summary>
    public static class TouchLayout
    {
        /// <summary>
        /// The touch layout is wanted: the touch UI is active (<see cref="InputReader.TouchUIActive"/>: forced by a test,
        /// the -touch argument of a PC player, or a finger was the last input), or this is a phone or tablet build (Android,
        /// iOS), where the very first tap of a session must not land on a layout that changes under the finger.
        /// </summary>
        public static bool Active => InputReader.TouchUIActive || MobileBuild; // MUTATION:TOUCH_LAYOUT_GATE

        /// <summary>A phone or tablet player (never the editor, whatever the build target).</summary>
        public static bool MobileBuild => Application.platform == RuntimePlatform.Android || Application.platform == RuntimePlatform.IPhonePlayer;

        /// <summary>
        /// A finger or the left mouse button is down. A change of layout waits for its release, so the tap that turned the
        /// touch UI on (a Windows touchscreen) still lands, on release, on the button it pressed.
        /// </summary>
        public static bool PointerHeld
        {
            get
            {
                Touchscreen touchscreen = Touchscreen.current;
                if (touchscreen != null && touchscreen.primaryTouch.isInProgress)
                {
                    return true;
                }
                Mouse mouse = Mouse.current;
                return mouse != null && mouse.leftButton.isPressed;
            }
        }

        /// <summary>
        /// The unsafe margins of the screen (<see cref="Screen.safeArea"/>: notch, rounded corners, system bars) in the
        /// reference units of the game's canvases (1920 x 1080 reference, width and height matched half and half):
        /// x left, y right, z bottom, w top. Zero in the editor and on a plain monitor.
        /// </summary>
        public static Vector4 SafeInsets()
        {
            float width = Screen.width;
            float height = Screen.height;
            if (width <= 0f || height <= 0f)
            {
                return Vector4.zero;
            }
            float scale = Mathf.Sqrt(width / 1920f * (height / 1080f));
            Rect safe = Screen.safeArea;
            return new Vector4(Mathf.Max(0f, safe.xMin), Mathf.Max(0f, width - safe.xMax), Mathf.Max(0f, safe.yMin),
                Mathf.Max(0f, height - safe.yMax)) / scale;
        }

        /// <summary>
        /// The height of the game's canvases in reference units for the current screen (966 on a 20:9 phone, 1080 at
        /// 16:9, 1247 on a 4:3 tablet): a touch layout shrinks its rows only when they would not fit it.
        /// </summary>
        public static float CanvasHeight()
        {
            float width = Mathf.Max(1f, Screen.width);
            float height = Mathf.Max(1f, Screen.height);
            return height / Mathf.Sqrt(width / 1920f * (height / 1080f));
        }

        /// <summary>
        /// The height of each of <paramref name="rows"/> rows <paramref name="gap"/> apart between <paramref name="top"/>
        /// and <paramref name="bottom"/> (reference units, y up): <paramref name="max"/> when they fit, smaller when not,
        /// never under <paramref name="min"/>.
        /// </summary>
        public static float FitRows(float top, float bottom, int rows, float gap, float max, float min)
        {
            float fit = (top - bottom - (rows - 1) * gap) / Mathf.Max(1, rows);
            return Mathf.Clamp(fit, min, max);
        }

        /// <summary>
        /// Tells a screen when to lay itself out again: the wanted mode changed (once no finger or mouse button is held),
        /// or the touch layout is on and the screen size or its safe area changed (a rotation to the other landscape side
        /// moves the notch). It starts in the PC layout, so a PC run with no touch never lays anything out again.
        /// </summary>
        public sealed class Watch
        {
            /// <summary>The layout last applied: true for the touch layout.</summary>
            public bool Touch { get; private set; }

            private Rect safe;
            private Vector2Int screen;

            /// <summary>True when the layout must be applied again; <see cref="Touch"/> is then the one to apply.</summary>
            public bool Changed()
            {
                bool wanted = Active;
                var size = new Vector2Int(Screen.width, Screen.height);
                Rect area = Screen.safeArea;
                if (wanted != Touch)
                {
                    if (PointerHeld)
                    {
                        return false;
                    }
                }
                else if (!wanted || (size == screen && area == safe))
                {
                    return false;
                }
                Touch = wanted;
                screen = size;
                safe = area;
                return true;
            }
        }

        /// <summary>
        /// Remembers the PC layout of what a touch layout changes (a rect's anchors, pivot, position and size; a label's size
        /// and alignment) the first time it is kept, and puts it all back exactly with <see cref="Restore"/>.
        /// </summary>
        public sealed class Memory
        {
            private struct RectState
            {
                public RectTransform Rect;
                public Vector2 AnchorMin;
                public Vector2 AnchorMax;
                public Vector2 Pivot;
                public Vector2 Position;
                public Vector2 Size;
            }

            private struct TextState
            {
                public Text Text;
                public int Size;
                public TextAnchor Alignment;
            }

            private readonly List<RectState> rects = new List<RectState>();
            private readonly List<TextState> texts = new List<TextState>();
            private readonly HashSet<Object> kept = new HashSet<Object>();

            /// <summary>Remembers <paramref name="rect"/> (once) and returns it.</summary>
            public RectTransform Keep(RectTransform rect)
            {
                if (rect != null && kept.Add(rect))
                {
                    rects.Add(new RectState
                    {
                        Rect = rect, AnchorMin = rect.anchorMin, AnchorMax = rect.anchorMax, Pivot = rect.pivot,
                        Position = rect.anchoredPosition, Size = rect.sizeDelta,
                    });
                }
                return rect;
            }

            /// <summary>Remembers <paramref name="text"/>'s size, alignment and rect (once) and returns it.</summary>
            public Text Keep(Text text)
            {
                if (text != null && kept.Add(text))
                {
                    texts.Add(new TextState { Text = text, Size = text.fontSize, Alignment = text.alignment });
                    Keep(text.rectTransform);
                }
                return text;
            }

            /// <summary>Puts back everything kept, then forgets it.</summary>
            public void Restore()
            {
                foreach (RectState state in rects)
                {
                    if (state.Rect == null)
                    {
                        continue;
                    }
                    state.Rect.anchorMin = state.AnchorMin;
                    state.Rect.anchorMax = state.AnchorMax;
                    state.Rect.pivot = state.Pivot;
                    state.Rect.anchoredPosition = state.Position;
                    state.Rect.sizeDelta = state.Size;
                }
                foreach (TextState state in texts)
                {
                    if (state.Text == null)
                    {
                        continue;
                    }
                    state.Text.fontSize = state.Size;
                    state.Text.alignment = state.Alignment;
                }
                rects.Clear();
                texts.Clear();
                kept.Clear();
            }
        }

        /// <summary>
        /// Places <paramref name="rect"/> by one anchor, its pivot on the same point (the menus' own Place convention):
        /// <paramref name="offset"/> from that anchor, <paramref name="size"/> big.
        /// </summary>
        public static void Place(RectTransform rect, Vector2 anchor, Vector2 offset, Vector2 size)
        {
            rect.anchorMin = rect.anchorMax = anchor;
            rect.pivot = anchor;
            rect.anchoredPosition = offset;
            rect.sizeDelta = size;
        }
    }
}
