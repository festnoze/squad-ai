using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// HUD gauge redesign (2026-11-19): the drawn UI icons shipped as PNG files (Assets/Art/UI/Icons, rendered from their
    /// SVG sources), referenced by Assets/Resources/UiIconLibrary.asset. OutOfSight.Editor.UiIconLibraryBuilder writes the
    /// asset from the files present and enforces their import settings (Builder.SetupAndCompile and every player build),
    /// the way AudioLibrary ships the clips. Each icon falls back to its procedural one (<see cref="ProceduralArt"/>) while
    /// its file, or the library, is missing, so the HUD always has an icon.
    /// </summary>
    public sealed class UiIconLibrary : ScriptableObject
    {
        /// <summary>The library's path under Resources.</summary>
        public const string ResourcePath = "UiIconLibrary";

        /// <summary>The creak gauge's icon (Assets/Art/UI/Icons/creak.png), or null.</summary>
        public Sprite creak;

        /// <summary>The suspicion gauge's icon (Assets/Art/UI/Icons/suspicion.png), or null.</summary>
        public Sprite suspicion;

        // Options icons (product owner, 2026-11-20; docs/m9/icons/NOTES.md): the Par défaut and Retour buttons (white, tinted
        // by the menu) and the Language row's flag, the French one in French, the US one in English (drawn in colour).

        /// <summary>The Options page's Par défaut / Defaults button icon (Assets/Art/UI/Icons/reset.png), or null.</summary>
        public Sprite reset;

        /// <summary>The Options page's Retour / Back button icon (Assets/Art/UI/Icons/back.png), or null.</summary>
        public Sprite back;

        /// <summary>The Language row's icon in French (Assets/Art/UI/Icons/flag_fr.png), or null.</summary>
        public Sprite flagFrench;

        /// <summary>The Language row's icon in English (Assets/Art/UI/Icons/flag_us.png), or null.</summary>
        public Sprite flagEnglish;

        private static UiIconLibrary loaded;
        private static bool tried;

        /// <summary>The library in Resources, or null when it was never built.</summary>
        public static UiIconLibrary Load()
        {
            if (loaded == null && !tried)
            {
                tried = true;
                loaded = Resources.Load<UiIconLibrary>(ResourcePath);
            }
            return loaded;
        }

        /// <summary>The drawn creak icon ships (white, to tint; the procedural fallback has its own colours).</summary>
        public static bool HasCreak
        {
            get
            {
                UiIconLibrary library = Load();
                return library != null && library.creak != null;
            }
        }

        /// <summary>The drawn suspicion icon ships (white, to tint).</summary>
        public static bool HasSuspicion
        {
            get
            {
                UiIconLibrary library = Load();
                return library != null && library.suspicion != null;
            }
        }

        /// <summary>The creak gauge's icon: the drawn one when shipped, else the procedural crack.</summary>
        public static Sprite Creak
        {
            get
            {
                UiIconLibrary library = Load();
                return library != null && library.creak != null ? library.creak : ProceduralArt.Creak;
            }
        }

        /// <summary>The suspicion gauge's icon: the drawn one when shipped, else the procedural magnifier.</summary>
        public static Sprite Suspicion
        {
            get
            {
                UiIconLibrary library = Load();
                return library != null && library.suspicion != null ? library.suspicion : ProceduralArt.Magnifier;
            }
        }

        /// <summary>The Par défaut button's icon (white, to tint), or null when it does not ship (the button then has none).</summary>
        public static Sprite Reset
        {
            get
            {
                UiIconLibrary library = Load();
                return library != null ? library.reset : null;
            }
        }

        /// <summary>The Retour button's icon (white, to tint), or null when it does not ship (the button then has none).</summary>
        public static Sprite Back
        {
            get
            {
                UiIconLibrary library = Load();
                return library != null ? library.back : null;
            }
        }

        /// <summary>
        /// The Language row's icon for <paramref name="language"/> (a Strings language id): the French flag for French, the
        /// US flag otherwise (English); the procedural globe while that flag, or the library, is missing.
        /// </summary>
        public static Sprite LanguageFlag(string language)
        {
            UiIconLibrary library = Load();
            Sprite flag = library == null ? null : Strings.NormalizeLanguage(language) == Strings.French ? library.flagFrench : library.flagEnglish;
            return flag != null ? flag : ProceduralArt.OptionGlobe;
        }
    }
}
