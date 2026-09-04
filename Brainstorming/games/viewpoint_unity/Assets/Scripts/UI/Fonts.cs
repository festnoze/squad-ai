using UnityEngine;
using UnityEngine.UI;

namespace Viewpoint
{
    /// <summary>
    /// The one font of the game, and the reason the UI is legacy uGUI Text
    /// rather than TextMeshPro.
    ///
    /// TMP cannot run without its TMP_Settings asset, which only exists once
    /// someone imports "TMP Essential Resources" into the project. That import
    /// drops a font asset and a baked SDF ATLAS TEXTURE into Assets, and this
    /// project ships no binary asset: the Godot original generates every mesh,
    /// material, texture and thumbnail in code.
    ///
    /// Two attempts failed before this one, and both are worth recording
    /// because both looked fine in the editor:
    ///
    /// 1. TMP with no settings asset. In the EDITOR TMP quietly tolerates it;
    ///    in a PLAYER, TextMeshProUGUI.Awake throws a NullReferenceException
    ///    out of TMP_Settings the moment the component is added. Every label
    ///    threw, Hud.Awake died with them, and Main.Awake died after that, so
    ///    the whole game came up with nothing but a default skybox.
    /// 2. Generating a TMP font asset at run time from an OS font. Also fine in
    ///    the editor, and in a player Font.CreateDynamicFontFromOSFont refuses:
    ///    "Unable to load font face for [Segoe UI]. Make sure Include Font Data
    ///    is enabled" - a build has no access to the OS font tables Unity wants.
    ///
    /// uGUI Text has neither problem: it needs no settings asset, and the
    /// engine's own builtin font is compiled into every player. The original's
    /// UI is outlined labels and nothing more, so nothing is lost.
    /// </summary>
    public static class Fonts
    {
        /// <summary>
        /// Unity's builtin font, present in every player because it is an
        /// ENGINE resource and not a project asset. Named Arial.ttf before
        /// Unity 2022 and LegacyRuntime.ttf since, so both are tried.
        /// </summary>
        static readonly string[] BuiltinNames = { "LegacyRuntime.ttf", "Arial.ttf" };

        static Font _default;
        static bool _attempted;

        /// <summary>
        /// The font every label uses. Callers must tolerate null: it is not
        /// worth a crash, and a headless run has no use for it.
        /// </summary>
        public static Font Default
        {
            get
            {
                if (!_attempted)
                {
                    _attempted = true;
                    _default = Build();
                }

                return _default;
            }
        }

        /// <summary>
        /// Gives a label the font and, when asked, a dark outline. The outline
        /// is a real uGUI Outline component: the original drew its labels with
        /// a Godot text outline so they read against both a bright sky and dark
        /// ground, and that legibility is the point, not the decoration.
        /// </summary>
        public static void Apply(Text label, int sizePx, Color color, TextAnchor alignment,
            bool outline, Color outlineColor)
        {
            label.font = Default;
            label.fontSize = sizePx;
            label.color = color;
            label.alignment = alignment;
            label.horizontalOverflow = HorizontalWrapMode.Overflow;
            label.verticalOverflow = VerticalWrapMode.Overflow;
            label.raycastTarget = false;
            label.supportRichText = false;
            label.text = string.Empty;

            if (outline)
            {
                Outline effect = label.gameObject.AddComponent<Outline>();
                effect.effectColor = outlineColor;
                // Two pixels of spread at the 1600 x 900 reference, which is
                // what the original's 6 to 8 pixel Godot outline reads like
                // once the canvas has scaled it.
                effect.effectDistance = new Vector2(2f, -2f);
                effect.useGraphicAlpha = false;
            }
        }

        static Font Build()
        {
            foreach (string name in BuiltinNames)
            {
                Font font = Resources.GetBuiltinResource<Font>(name);
                if (font != null)
                {
                    return font;
                }
            }

            // Last resort, and only useful in the editor: a dynamic OS font. A
            // player refuses these (see the class comment), so this is a
            // convenience for editor tooling, never the shipping path.
            string[] installed = Font.GetOSInstalledFontNames();
            if (installed != null && installed.Length > 0)
            {
                Font font = Font.CreateDynamicFontFromOSFont(installed[0], 32);
                if (font != null)
                {
                    return font;
                }
            }

            Debug.LogWarning("[Fonts] No font available; the UI will draw no text.");
            return null;
        }
    }
}
