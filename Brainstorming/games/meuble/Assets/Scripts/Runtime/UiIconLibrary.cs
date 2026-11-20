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
    }
}
