using System.IO;
using UnityEditor;
using UnityEngine;

namespace OutOfSight.Editor
{
    /// <summary>
    /// HUD gauge redesign (2026-11-19): builds Assets/Resources/UiIconLibrary.asset (<see cref="UiIconLibrary"/>) from the
    /// PNG icons of <see cref="IconFolder"/> present now, and applies their import settings first: a single Sprite with
    /// transparent alpha, mipmaps (the icons are drawn far smaller than their file), trilinear, clamped, uncompressed (no
    /// block artefacts on thin strokes), at most <see cref="MaxSize"/> texels. A missing file leaves its slot empty, so the
    /// HUD keeps the procedural icon. Idempotent: an importer is only reimported when a setting differs, and the asset is
    /// only written when its content changes.
    /// </summary>
    public static class UiIconLibraryBuilder
    {
        public const string IconFolder = "Assets/Art/UI/Icons";
        public const string CreakIconPath = IconFolder + "/creak.png";
        public const string SuspicionIconPath = IconFolder + "/suspicion.png";
        public const string AssetPath = "Assets/Resources/UiIconLibrary.asset";
        public const int MaxSize = 256;

        [MenuItem("OutOfSight/Build UI Icon Library")]
        public static void Build()
        {
            int reimported = 0;
            Sprite creak = Icon(CreakIconPath, ref reimported);
            Sprite suspicion = Icon(SuspicionIconPath, ref reimported);

            UiIconLibrary library = AssetDatabase.LoadAssetAtPath<UiIconLibrary>(AssetPath);
            bool created = library == null;
            if (created)
            {
                if (!AssetDatabase.IsValidFolder("Assets/Resources"))
                {
                    AssetDatabase.CreateFolder("Assets", "Resources");
                }
                library = ScriptableObject.CreateInstance<UiIconLibrary>();
            }
            string before = created ? string.Empty : EditorJsonUtility.ToJson(library);
            library.creak = creak;
            library.suspicion = suspicion;
            if (created)
            {
                AssetDatabase.CreateAsset(library, AssetPath);
            }
            else if (EditorJsonUtility.ToJson(library) != before)
            {
                EditorUtility.SetDirty(library);
            }
            AssetDatabase.SaveAssets();
            Debug.Log($"[UiIconLibraryBuilder] {AssetPath}: creak {(creak != null ? "drawn" : "procedural")}, suspicion "
                + $"{(suspicion != null ? "drawn" : "procedural")}, {reimported} importer(s) updated{(created ? ", asset created" : string.Empty)}.");
        }

        /// <summary>The sprite of the PNG at <paramref name="path"/> with the icon import settings, or null without the file.</summary>
        private static Sprite Icon(string path, ref int reimported)
        {
            if (!File.Exists(path))
            {
                return null;
            }
            var importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null)
            {
                AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
                importer = AssetImporter.GetAtPath(path) as TextureImporter;
                if (importer == null)
                {
                    Debug.LogError($"[UiIconLibraryBuilder] {path} is not imported as a texture: the HUD keeps the procedural icon");
                    return null;
                }
            }
            bool dirty = false;
            if (importer.textureType != TextureImporterType.Sprite)
            {
                importer.textureType = TextureImporterType.Sprite;
                dirty = true;
            }
            if (importer.spriteImportMode != SpriteImportMode.Single)
            {
                importer.spriteImportMode = SpriteImportMode.Single;
                dirty = true;
            }
            if (!importer.alphaIsTransparency)
            {
                importer.alphaIsTransparency = true;
                dirty = true;
            }
            if (!importer.mipmapEnabled)
            {
                importer.mipmapEnabled = true;
                dirty = true;
            }
            if (!importer.sRGBTexture)
            {
                importer.sRGBTexture = true;
                dirty = true;
            }
            if (importer.wrapMode != TextureWrapMode.Clamp)
            {
                importer.wrapMode = TextureWrapMode.Clamp;
                dirty = true;
            }
            if (importer.filterMode != FilterMode.Trilinear)
            {
                importer.filterMode = FilterMode.Trilinear;
                dirty = true;
            }
            if (importer.textureCompression != TextureImporterCompression.Uncompressed)
            {
                importer.textureCompression = TextureImporterCompression.Uncompressed;
                dirty = true;
            }
            if (importer.maxTextureSize != MaxSize)
            {
                importer.maxTextureSize = MaxSize;
                dirty = true;
            }
            if (dirty)
            {
                importer.SaveAndReimport();
                reimported++;
            }
            return AssetDatabase.LoadAssetAtPath<Sprite>(path);
        }
    }
}
