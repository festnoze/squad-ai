using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// START SPLASH (docs/next/progress/SPLASH.md): the start poster, Assets/Art/UI/out-of-sight-affiche-fr.png, referenced by
    /// Assets/Resources/SplashArt.asset so the player can load it by name without moving the file into a Resources folder.
    /// OutOfSight.Editor.ProjectSetup writes the asset and enforces the poster's import settings (Builder.SetupAndCompile and
    /// every player build). <see cref="StartSplash"/> loads it once at launch and unloads the texture when it is gone.
    /// </summary>
    public sealed class SplashArt : ScriptableObject
    {
        /// <summary>The asset's path under Resources.</summary>
        public const string ResourcePath = "SplashArt";

        /// <summary>The poster (1024 x 1536, portrait 2:3), or null when the file is missing (the game then starts without it).</summary>
        public Texture2D poster;
    }
}
