using UnityEngine;
using UnityEngine.UI;

namespace Viewpoint
{
    /// <summary>
    /// How a label is separated from whatever is behind it.
    ///
    /// The distinction exists because this game has two kinds of label and they
    /// need different things. A label lying on its own dark panel (the menu, and
    /// the HUD panels of V-HUD-02 to 04) already has its contrast from the panel
    /// and only wants a hint of depth, which is TextEdge.Shadow. A label that
    /// floats straight on the world can end up over the pale sky, where white
    /// on sky is about 1.2:1 and only the dark edge does any work at all, so
    /// that edge has to surround the glyph rather than sit on one side of it:
    /// TextEdge.Contour. The full form of Apply below carries the numbers.
    /// </summary>
    public enum TextEdge
    {
        /// <summary>Nothing added. For labels on a panel that dims with them.</summary>
        None,

        /// <summary>One offset drop shadow (1 px). Depth, not legibility.</summary>
        Shadow,

        /// <summary>The same shadow on all four diagonals. Legibility anywhere.</summary>
        Contour
    }

    /// <summary>
    /// The two weights the interface asks for. Read Fonts.StyleFor before
    /// believing the second one: with the font this project ships, both come
    /// out the same, and the comment there says why a real semibold is not
    /// available.
    /// </summary>
    public enum TextWeight
    {
        /// <summary>Body copy: counters, prompts, hints, level names.</summary>
        Regular,

        /// <summary>Titles: the game name, the banner title, menu headings.</summary>
        Title
    }

    /// <summary>
    /// The one font of the game, and the reason the UI is legacy uGUI Text
    /// rather than TextMeshPro.
    ///
    /// TMP cannot run without its TMP_Settings asset, which only exists once
    /// someone imports "TMP Essential Resources" into the project. That import
    /// drops a font asset and a baked SDF ATLAS TEXTURE into Assets.
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
    /// engine's own builtin font is compiled into every player.
    ///
    /// V-HUD-01 then bought the interface a real typeface, and that is the third
    /// thing this class has to get right. The rules it follows:
    ///
    /// - The file is an OFL variable Manrope of 165 KB at
    ///   Assets/Resources/Fonts/Manrope.ttf with its licence beside it. It is
    ///   Manrope and not the Inter the PRD names because Inter is now published
    ///   only as an 876 KB variable file, three times the budget of PRD_VISUAL
    ///   3.2 (Appendix C.8).
    /// - It lives under Resources/ because nothing in this game references an
    ///   asset from a scene (one scene, one object, everything built in code)
    ///   and Unity strips whatever nothing references. A font in a plain
    ///   Assets/Fonts/ imports perfectly, looks right in the editor, and is
    ///   absent from the player: the same failure as the stripped shaders in the
    ///   README. Resources.Load is the only runtime path that survives a build.
    /// - It is imported with Include Font Data on, so it is a DYNAMIC font whose
    ///   outlines travel inside the player. That is the opposite of failure 2
    ///   above: the refusal there was about reading the OS font tables, not
    ///   about rasterising at run time, which a project font does fine.
    /// - Loading it is allowed to fail. PRD_VISUAL 3.2 requires that a checkout
    ///   with the file removed still boots and draws text, so the builtin font
    ///   stays the fallback and the OS font stays the editor-only last resort.
    /// </summary>
    public static class Fonts
    {
        /// <summary>
        /// The project font, as Resources.Load wants it: no "Assets/Resources"
        /// prefix and NO EXTENSION. "Fonts/Manrope.ttf" returns null, silently,
        /// which would look exactly like the file being missing.
        /// </summary>
        const string ProjectFontPath = "Fonts/Manrope";

        /// <summary>
        /// Unity's builtin font, present in every player because it is an
        /// ENGINE resource and not a project asset. Named Arial.ttf before
        /// Unity 2022 and LegacyRuntime.ttf since, so both are tried.
        /// </summary>
        static readonly string[] BuiltinNames = { "LegacyRuntime.ttf", "Arial.ttf" };

        /// <summary>
        /// V-HUD-01's edge: black at 60 percent. Callers that have tuned their
        /// own alpha (the HUD runs a softer edge on the hints than on the
        /// counters) pass their own colour instead and this is only the default.
        /// </summary>
        public static readonly Color EdgeColor = new Color(0f, 0f, 0f, 0.6f);

        /// <summary>
        /// V-HUD-01's one pixel, at the 1600 x 900 reference the canvas scales
        /// from. Y is negative because uGUI's y axis points up and a shadow
        /// falls down. Outline mirrors the pair on both axes by itself.
        /// </summary>
        static readonly Vector2 EdgeDistance = new Vector2(1f, -1f);

        static Font _default;
        static bool _attempted;
        static bool _isProjectFont;

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
        /// True when Default is the project's Manrope and not a fallback. Read
        /// it for diagnostics (the shot probe prints which font the player
        /// actually got, which is how a stripped asset gets caught); the weight
        /// logic below reads it because the two fonts need different treatment.
        /// </summary>
        public static bool IsProjectFont
        {
            get
            {
                // Through the property, so asking this question is enough to
                // resolve the font and the answer is never a stale false.
                return Default != null && _isProjectFont;
            }
        }

        /// <summary>
        /// Gives a label the font, an alignment and, when asked, an edge that
        /// keeps it readable over anything. This is the signature the HUD and
        /// the menu have always called; "outline" now means "this label has no
        /// panel behind it, give it whatever edge it needs", which is
        /// TextEdge.Contour. Callers that know their label sits on a panel
        /// should ask for TextEdge.Shadow through the overload below.
        /// </summary>
        public static void Apply(Text label, int sizePx, Color color, TextAnchor alignment,
            bool outline, Color outlineColor)
        {
            Apply(label, sizePx, color, alignment,
                outline ? TextEdge.Contour : TextEdge.None, outlineColor, TextWeight.Regular);
        }

        /// <summary>
        /// The same, with the edge chosen explicitly and the edge colour left at
        /// V-HUD-01's 60 percent black.
        /// </summary>
        public static void Apply(Text label, int sizePx, Color color, TextAnchor alignment,
            TextEdge edge)
        {
            Apply(label, sizePx, color, alignment, edge, EdgeColor, TextWeight.Regular);
        }

        /// <summary>
        /// The same, with the edge and its colour chosen and the regular
        /// weight. This is the form a restyled HUD wants: it keeps the alphas
        /// the HUD already tuned per label and only changes the shape of the
        /// edge.
        /// </summary>
        public static void Apply(Text label, int sizePx, Color color, TextAnchor alignment,
            TextEdge edge, Color edgeColor)
        {
            Apply(label, sizePx, color, alignment, edge, edgeColor, TextWeight.Regular);
        }

        /// <summary>
        /// The full form: font, size, colour, alignment, edge and weight.
        ///
        /// On the edge, which V-HUD-01 asks to change from an Outline to a
        /// Shadow of 1 px at 60 percent. The original drew a Godot text outline
        /// so labels read against both a bright sky and dark ground, and that
        /// LEGIBILITY is the point, not the decoration, so the swap only holds
        /// if a shadow delivers it. It does not, for the labels over the world:
        ///
        ///   The sky at the horizon is (0.87, 0.91, 0.93) and at the zenith
        ///   (0.53, 0.72, 0.87), and the HUD sits at the TOP of the frame where
        ///   the pale end of that gradient is. A white glyph on the pale sky is
        ///   a contrast ratio of about 1.24:1, against the 3:1 that large text
        ///   needs to be read at a glance: the white body of the glyph carries
        ///   NOTHING. All of the contrast comes from the dark edge, which at 60
        ///   percent over that sky lands near 2.8:1 and is exactly enough. A
        ///   drop shadow puts that edge on one side only, so every stroke has
        ///   one boundary that works and one that dissolves into the sky, and
        ///   thin strokes fuse into each other. That is worse than the outline
        ///   it replaced, not cleaner.
        ///
        /// So the item is honoured in its NUMBERS and split in its component:
        /// one pixel at 60 percent, as a drop shadow where a panel already
        /// carries the contrast (TextEdge.Shadow), and as the same shadow on the
        /// four diagonals where it does not (TextEdge.Contour). A contour of one
        /// pixel is half the two pixel outline this replaced, so the "cleaner
        /// look" the item wants is real: the labels lose the heavy letterpress
        /// ring and keep the separation. uGUI's Outline IS a Shadow subclass
        /// that draws four copies, so this is one component either way.
        /// </summary>
        public static void Apply(Text label, int sizePx, Color color, TextAnchor alignment,
            TextEdge edge, Color edgeColor, TextWeight weight)
        {
            label.font = Default;
            label.fontSize = sizePx;
            label.fontStyle = StyleFor(weight);
            label.color = color;
            label.alignment = alignment;
            label.horizontalOverflow = HorizontalWrapMode.Overflow;
            label.verticalOverflow = VerticalWrapMode.Overflow;
            label.raycastTarget = false;
            label.supportRichText = false;
            label.text = string.Empty;

            ApplyEdge(label, edge, edgeColor);
        }

        /// <summary>
        /// The weight of a label, and the honest version of what that means
        /// here.
        ///
        /// Manrope is a VARIABLE font: one file carrying a wght axis from 200 to
        /// 800. Unity's legacy Font importer has no axis support and hands
        /// FreeType the file's DEFAULT INSTANCE, and Manrope's default instance
        /// is wght 200, ExtraLight (its OS/2 usWeightClass is 200 and its family
        /// name is "Manrope ExtraLight"). So there is no semibold to ask for,
        /// and there is not even a regular: left alone, every label in the game
        /// would draw in hairlines, which at 14 to 22 px over a pale sky is the
        /// legibility problem of the edge note above made twice as bad.
        ///
        /// uGUI Text has fontStyle = Bold, which for a dynamic font with no bold
        /// face is a SYNTHESISED weight: FreeType thickens the outline, it is
        /// not a designed cut, and the shapes are slightly heavier and rounder
        /// at the joins than a real Manrope SemiBold would be. It is used here
        /// anyway, and used for EVERY label rather than only for titles, because
        /// on ExtraLight it does not read as bold at all: it reads as about the
        /// regular weight the interface was designed for.
        ///
        /// That leaves the title weight with nothing above it: under Manrope,
        /// Regular and Title come out identically and the hierarchy is carried
        /// by size (72 px against 14 to 22 px) and colour, which is how the
        /// menu was laid out anyway. Under the FALLBACK font the distinction is
        /// real, because the builtin is a true 400 with a true bold, and there
        /// Regular must stay Normal or the whole interface would shout.
        ///
        /// The only way to get a second real weight is a second static TTF
        /// (Manrope-Regular and Manrope-SemiBold as separate files), which is a
        /// new binary asset and a decision for the asset policy, not for this
        /// file. It is recorded as a follow-up.
        ///
        /// Public because the teleporter's label is a TextMesh and not a Text,
        /// so it cannot go through Apply and still needs the same answer.
        /// </summary>
        public static FontStyle StyleFor(TextWeight weight)
        {
            if (weight == TextWeight.Title)
            {
                return FontStyle.Bold;
            }

            // Regular: synthesised up to a usable weight on the ExtraLight
            // default instance, left alone on a font that has a real 400.
            return IsProjectFont ? FontStyle.Bold : FontStyle.Normal;
        }

        /// <summary>
        /// Puts the one edge component the label is allowed on it.
        ///
        /// Nothing is destroyed here, and that is deliberate: Apply can be
        /// called a second time on a label that is being restyled, Destroy is
        /// illegal outside play mode (this class is exercised by EditMode
        /// tests), and DestroyImmediate on a component mid-build is worse than
        /// an idle component. So an effect of the wrong kind is switched off and
        /// one of the right kind is reused, which also keeps the call
        /// idempotent: two Applies never stack two edges.
        ///
        /// useGraphicAlpha stays off so the edge keeps its own alpha instead of
        /// inheriting the label's. Hud fades its labels through a CanvasGroup
        /// for exactly that reason and its comment says so; do not turn this on
        /// without reading it.
        /// </summary>
        static void ApplyEdge(Text label, TextEdge edge, Color edgeColor)
        {
            // Outline derives from Shadow, so this finds both kinds.
            Shadow[] existing = label.gameObject.GetComponents<Shadow>();
            Shadow reused = null;
            System.Type wanted = edge == TextEdge.Contour ? typeof(Outline) : typeof(Shadow);

            for (int i = 0; i < existing.Length; i++)
            {
                Shadow effect = existing[i];
                if (effect == null)
                {
                    continue;
                }

                if (reused == null && edge != TextEdge.None && effect.GetType() == wanted)
                {
                    reused = effect;
                    continue;
                }

                effect.enabled = false;
            }

            if (edge == TextEdge.None)
            {
                return;
            }

            if (reused == null)
            {
                reused = edge == TextEdge.Contour
                    ? label.gameObject.AddComponent<Outline>()
                    : label.gameObject.AddComponent<Shadow>();
            }

            reused.enabled = true;
            reused.effectColor = edgeColor;
            reused.effectDistance = EdgeDistance;
            reused.useGraphicAlpha = false;
        }

        static Font Build()
        {
            // The project font first. A missing file is a supported state, not
            // an error: PRD_VISUAL 3.2 asks that a checkout without it still
            // runs, so this logs nothing and falls through to the builtin. The
            // shot probe prints which font the player ended up with, and that
            // line is how a stripped or misplaced asset gets caught.
            Font project = Resources.Load<Font>(ProjectFontPath);
            if (project != null)
            {
                _isProjectFont = true;
                return project;
            }

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
