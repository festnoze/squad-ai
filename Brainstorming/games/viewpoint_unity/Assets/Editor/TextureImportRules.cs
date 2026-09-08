using UnityEditor;
using UnityEngine;

namespace Viewpoint.Editor
{
    /// <summary>
    /// Import settings for the CC0 PBR sets under <c>Assets/Textures</c>.
    ///
    /// This exists because Unity's DEFAULT texture import is wrong for three of
    /// the four maps in a PBR set, and wrong in ways that produce a plausible
    /// looking picture rather than an error:
    ///
    ///   - a normal map imported as a colour texture is fed to the shader as raw
    ///     RGB. It still shades, it just shades WRONG, and the surface reads as
    ///     dirty rather than bumpy. Unity wants Type = NormalMap, which also
    ///     lets it swizzle into the packed two channel format the platform uses;
    ///   - roughness, metalness, height and ambient occlusion are DATA, not
    ///     colour. Imported with sRGB on (the default) every value is gamma
    ///     decoded on sample, so a roughness of 0.5 arrives as roughness 0.21 and
    ///     everything in the game turns glossy;
    ///   - only the colour map is actually sRGB.
    ///
    /// Doing it here rather than by hand in the inspector matters for the same
    /// reason everything else in this project is generated: a fresh checkout
    /// imports these 46 files with no human in the loop, and a CI or headless
    /// import has no inspector to click in. An AssetPostprocessor is the one
    /// hook that runs on that path.
    ///
    /// The file names are the contract, produced by the extraction step that
    /// pulled them out of the ambientCG archives:
    ///   &lt;Set&gt;_Color.jpg  &lt;Set&gt;_Normal.jpg  &lt;Set&gt;_Rough.jpg
    ///   &lt;Set&gt;_Metal.jpg  &lt;Set&gt;_Height.jpg  &lt;Set&gt;_AO.jpg
    /// Normal is the OpenGL convention map (ambientCG ships DX and GL; Unity
    /// wants GL, and picking DX inverts the green channel so every bump becomes
    /// a dent).
    /// </summary>
    public sealed class TextureImportRules : AssetPostprocessor
    {
        /// <summary>
        /// Under Resources, and that is not a filing preference. This game
        /// references no asset from a scene (one scene, one object, everything
        /// built in code), and Unity STRIPS from a player any asset nothing
        /// references. Resources.Load is the one runtime path that survives
        /// that, which is why the level data and the font already live here.
        /// A texture parked in a plain Assets/Textures/ folder would import
        /// perfectly, look right in the editor, and be absent from the build.
        /// </summary>
        const string Root = "Assets/Resources/Textures/";

        /// <summary>
        /// Anisotropic filtering, because almost every textured surface in this
        /// game is a large flat plane seen at a grazing angle (a platform top
        /// under the player's feet). That is the one case where trilinear alone
        /// blurs into mush a few metres out.
        /// </summary>
        const int Anisotropy = 8;

        void OnPreprocessTexture()
        {
            if (!assetPath.StartsWith(Root, System.StringComparison.Ordinal))
            {
                return;
            }

            var importer = (TextureImporter)assetImporter;
            string name = System.IO.Path.GetFileNameWithoutExtension(assetPath);
            int underscore = name.LastIndexOf('_');
            string map = underscore >= 0 ? name.Substring(underscore + 1) : string.Empty;

            importer.textureType = map == "Normal"
                ? TextureImporterType.NormalMap
                : TextureImporterType.Default;

            // Colour is the ONLY sRGB map. A normal map's sRGB flag is ignored
            // once the type is NormalMap, but it is set false anyway so the
            // rule reads the same way for every non colour map.
            importer.sRGBTexture = map == "Color";

            importer.wrapMode = TextureWrapMode.Repeat;
            importer.filterMode = FilterMode.Trilinear;
            importer.anisoLevel = Anisotropy;
            importer.mipmapEnabled = true;
            // Nothing reads these back on the CPU, and a readable texture keeps
            // a second copy in system memory for the life of the run.
            importer.isReadable = false;
            importer.streamingMipmaps = true;

            // 1K is the authored size and the size the look was tuned at; the
            // cap is stated rather than left at Unity's 2048 default so a set
            // accidentally downloaded at 4K cannot quietly cost sixteen times
            // the memory.
            importer.maxTextureSize = 1024;
            importer.textureCompression = TextureImporterCompression.Compressed;
        }
    }
}
