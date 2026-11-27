// Owned by B4. Contract 15.1: keeps a full-screen RectTransform inside Screen.safeArea (notches, rounded corners, gesture
// bars). Every UI canvas holds its content under one of these.
using UnityEngine;

namespace PainterIO.Runtime
{
    [DisallowMultipleComponent]
    public sealed class SafeArea : MonoBehaviour
    {
        private RectTransform rect;
        private Rect lastSafe;
        private Vector2Int lastScreen;

        /// <summary>The safe rect as anchors (0..1) of the screen, from Screen.safeArea; the whole screen when invalid.</summary>
        public static void Anchors(out Vector2 min, out Vector2 max)
        {
            float w = Mathf.Max(1, Screen.width), h = Mathf.Max(1, Screen.height);
            Rect s = Screen.safeArea;
            if (s.width <= 1f || s.height <= 1f)
            {
                min = Vector2.zero;
                max = Vector2.one;
                return;
            }
            min = new Vector2(Mathf.Clamp01(s.xMin / w), Mathf.Clamp01(s.yMin / h));
            max = new Vector2(Mathf.Clamp01(s.xMax / w), Mathf.Clamp01(s.yMax / h));
            if (max.x - min.x < 0.2f || max.y - min.y < 0.2f)
            {
                min = Vector2.zero;
                max = Vector2.one;
            }
        }

        private void Awake()
        {
            rect = transform as RectTransform;
            Apply();
        }

        private void LateUpdate()
        {
            Rect s = Screen.safeArea;
            if (s != lastSafe || Screen.width != lastScreen.x || Screen.height != lastScreen.y) Apply();
        }

        private void Apply()
        {
            if (rect == null) return;
            lastSafe = Screen.safeArea;
            lastScreen = new Vector2Int(Screen.width, Screen.height);
            Anchors(out Vector2 min, out Vector2 max);
            rect.anchorMin = min;
            rect.anchorMax = max;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
        }
    }
}
