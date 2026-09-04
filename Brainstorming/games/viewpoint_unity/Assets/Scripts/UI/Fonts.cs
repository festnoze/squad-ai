using TMPro;
using UnityEngine;
using UnityEngine.TextCore.LowLevel;

namespace Viewpoint
{
    /// <summary>
    /// The one font of the game, built at runtime.
    ///
    /// TextMeshPro normally resolves TMP_Settings.defaultFontAsset, which only
    /// exists once someone has imported "TMP Essential Resources" into the
    /// project. That import drops a font asset and its baked atlas TEXTURE into
    /// Assets, and this project ships no binary asset: the Godot original
    /// generates every mesh, material, texture and thumbnail in code, and the
    /// port keeps that promise.
    ///
    /// So the font is generated instead: an OS font, wrapped in a TMP font asset
    /// with a DYNAMIC atlas, so glyphs are rasterized on demand at run time and
    /// nothing is committed. That also fixed a real crash, which is how the
    /// missing font was found in the first place: setting an outline on a label
    /// that has no font asset throws inside TMP, because the outline needs a
    /// material instance and there is no source material to instance from.
    /// </summary>
    public static class Fonts
    {
        /// <summary>
        /// Candidates in preference order. The first four are the usual Windows
        /// and Linux sans faces; the search falls through to whatever the machine
        /// actually has, so a missing one is never fatal.
        /// </summary>
        static readonly string[] Preferred =
        {
            "Segoe UI",
            "Arial",
            "Liberation Sans",
            "DejaVu Sans",
            "Helvetica",
            "Verdana",
        };

        /// <summary>Sampling size of the generated SDF. 90 is TMP's own default.</summary>
        const int SamplingPointSize = 90;
        const int AtlasPadding = 9;
        const int AtlasSize = 1024;

        static TMP_FontAsset _default;
        static bool _attempted;

        /// <summary>
        /// The font every label uses, or null when this machine has no usable
        /// font at all. Callers MUST tolerate null: a headless run on a bare
        /// container is a legitimate case, and text is not worth a crash.
        /// </summary>
        public static TMP_FontAsset Default
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
        /// Applies the font to a label and, only if that worked, its outline.
        /// The order matters: TMP builds a material instance when the outline is
        /// set, and without a font there is nothing to instance.
        /// </summary>
        public static void Apply(TMP_Text label, Color outlineColor, float outlineWidth)
        {
            TMP_FontAsset font = Default;
            if (font == null)
            {
                return;
            }
            label.font = font;
            if (outlineWidth > 0f)
            {
                label.outlineColor = outlineColor;
                label.outlineWidth = outlineWidth;
            }
        }

        static TMP_FontAsset Build()
        {
            // If someone does import TMP Essential Resources later, defer to it:
            // a hand-tuned asset beats a generated one.
            if (TMP_Settings.instance != null && TMP_Settings.defaultFontAsset != null)
            {
                return TMP_Settings.defaultFontAsset;
            }

            Font source = LoadOsFont();
            if (source == null)
            {
                Debug.LogWarning("[Fonts] No usable OS font found; the UI will draw no text.");
                return null;
            }

            try
            {
                TMP_FontAsset asset = TMP_FontAsset.CreateFontAsset(
                    source,
                    SamplingPointSize,
                    AtlasPadding,
                    GlyphRenderMode.SDFAA,
                    AtlasSize,
                    AtlasSize,
                    AtlasPopulationMode.Dynamic,
                    true);
                if (asset == null)
                {
                    Debug.LogWarning("[Fonts] CreateFontAsset returned null for " + source.name);
                    return null;
                }
                asset.name = "Viewpoint Generated SDF";
                return asset;
            }
            catch (System.Exception e)
            {
                Debug.LogWarning("[Fonts] Could not build a font asset from "
                    + source.name + ": " + e.Message);
                return null;
            }
        }

        static Font LoadOsFont()
        {
            string[] installed = Font.GetOSInstalledFontNames();
            if (installed != null && installed.Length > 0)
            {
                foreach (string wanted in Preferred)
                {
                    foreach (string available in installed)
                    {
                        if (string.Equals(available, wanted, System.StringComparison.OrdinalIgnoreCase))
                        {
                            Font font = Font.CreateDynamicFontFromOSFont(available, SamplingPointSize);
                            if (font != null)
                            {
                                return font;
                            }
                        }
                    }
                }

                // Nothing preferred: take the first one that loads rather than
                // giving up, so an unusual machine still gets readable text.
                foreach (string available in installed)
                {
                    Font font = Font.CreateDynamicFontFromOSFont(available, SamplingPointSize);
                    if (font != null)
                    {
                        return font;
                    }
                }
            }

            // Last resort: the legacy font that ships inside the engine. It is a
            // builtin resource, not a project asset, so it commits nothing.
            return Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        }
    }
}
