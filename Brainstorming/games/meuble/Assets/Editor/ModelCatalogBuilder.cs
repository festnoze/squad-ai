using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using OutOfSight.Core;
using UnityEditor;
using UnityEngine;

namespace OutOfSight.Editor
{
    /// <summary>
    /// Builds Assets/Resources/ModelCatalog.asset from the imported models (docs/CONTRACT_M3.md 3). Called by
    /// Builder.SetupAndCompile and before every player build. Idempotent: the asset is written only when a
    /// measured value changed.
    ///
    /// Everything is measured on a temporary instance of the imported GLB, never typed by hand:
    /// - static models: the bounds of every renderer in root space (native size and centre);
    /// - rigged models: the bounds of the skinned mesh baked in its rest pose, the head bone, the eye centroid
    ///   (the vertices of the "Eyes" material) in head bone space, the facing (eyes ahead of the head bone),
    ///   and the eye height, averaged over the Idle clip (the pose of a dwelling inhabitant).
    /// Only the yaw offsets of the static models come from the contract table: facing cannot be measured from
    /// bounds (the facing test of probe step 22 checks them against the procedural backrests).
    ///
    /// M5 (docs/CONTRACT_M5_v3.md 15.5, CONTRACT_M5 3 and 16.11): every rigged entry has a kind ("human" or "pet") and a
    /// target eye height (0 for the humans: Tuning.EyeHeight; the dog: Tuning.DogEyeHeight). A pet's eyes are the vertices
    /// of its "Eyes_*" materials (anywhere on the body: a dog's head is not on top), and its clip map names its Idle and
    /// Walk exactly (the Shiba stores every clip twice, plain and "AnimalArmature|": the plain set is used). Bones and
    /// triangles are checked against PRD 7.4 (a pet: Tuning.BudgetPetBones), with a warning when over.
    ///
    /// M4.2: it also builds Assets/Resources/TextureLibrary.asset (the detail textures and their measured means) and
    /// enforces their import settings (<see cref="BuildTextureLibrary()"/>).
    /// </summary>
    public static class ModelCatalogBuilder
    {
        public const string AssetPath = "Assets/Resources/ModelCatalog.asset";
        private const string Kenney = "Assets/ThirdParty/Models/Kenney/";
        private const string Quaternius = "Assets/ThirdParty/Models/Quaternius/";
        private const string RoundedHumans = "Assets/Art/Characters/Models/";

        /// <summary>The head bone of the Quaternius HumanArmature skeleton (M3_ASSETS 6.1, read from the GLB).</summary>
        public const string HeadBoneName = "Head";

        /// <summary>The material of the eyes in the Quaternius humans: its submesh gives the eye centroid.</summary>
        public const string EyeMaterialName = "Eyes";

        /// <summary>The clip whose mean pose calibrates the eye height (matched with EndsWith, as InhabitantRig does).</summary>
        public const string IdleSuffix = "_Idle";

        private const int IdleSamples = 24;

        /// <summary>The eyes are looked for in this top fraction of the body height.</summary>
        private const float HeadRegion = 0.2f;

        private struct Spec
        {
            public string Id;
            public string Path;
            public float Yaw;
            public bool Rigged;
            // M5: the character kind, the target eye height (0: Tuning.EyeHeight), the eye material (a prefix for a pet),
            // the head region fraction where the eyes are looked for, and a pet's exact Idle and Walk clip names.
            public string Kind;
            public float TargetEye;
            public bool PetEyes;
            public string IdleClip;
            public string WalkClip;

            public Spec(string id, string path, float yaw, bool rigged)
            {
                Id = id;
                Path = path;
                Yaw = yaw;
                Rigged = rigged;
                Kind = rigged ? ModelCatalog.KindHuman : null;
                TargetEye = 0f;
                PetEyes = false;
                IdleClip = null;
                WalkClip = null;
            }

            /// <summary>A pet: eyes from the "Eyes_*" materials, eyes fitted at <paramref name="targetEye"/>, its clip map.</summary>
            public static Spec Pet(string id, string path, float targetEye, string idleClip, string walkClip)
            {
                return new Spec(id, path, 0f, true)
                {
                    Kind = ModelCatalog.KindPet, TargetEye = targetEye, PetEyes = true, IdleClip = idleClip, WalkClip = walkClip,
                };
            }
        }

        /// <summary>M5: the prefix of a pet's eye materials (the Shiba: Eyes_White, Eyes_Pupil, Eyes_Black).</summary>
        public const string PetEyeMaterialPrefix = "Eyes_";

        // CONTRACT_M3 3: Kenney seats face -Z in glTF (backrest on +Z). The procedural chair's backrest is on -z,
        // so the chair and the armchair turn 180; the procedural sofa's backrest is on +z, so the sofa keeps 0.
        // M4 bodies (CONTRACT_M4 2): the armchair body and the "armchair" prop face +z with their backrest on -z
        // (FurnitureKit.Armchair), as the chair: 180. The bar stool and the round floor lamp have no back: the top
        // 15 % of their vertices is centred on the footprint (measured from the GLBs), so any quarter turn fits and
        // they keep 0. The office chair has no model (procedural, FurnitureKit.OfficeChair).
        // The rigged humans' yaw is measured (Yaw is ignored for them).
        private static readonly Spec[] Specs =
        {
            new Spec(ModelCatalog.KenneyChair, Kenney + "kenney_chair.glb", 180f, false),
            new Spec(ModelCatalog.KenneySofa, Kenney + "kenney_lounge_sofa.glb", 0f, false),
            new Spec(ModelCatalog.KenneyRug, Kenney + "kenney_rug_rectangle.glb", 0f, false),
            new Spec(ModelCatalog.KenneyDoormat, Kenney + "kenney_rug_square.glb", 0f, false),
            new Spec(ModelCatalog.KenneyArmchair, Kenney + "kenney_lounge_chair.glb", 180f, false),
            new Spec(ModelCatalog.KenneyStool, Kenney + "kenney_bar_stool.glb", 0f, false),
            new Spec(ModelCatalog.KenneyFloorLamp, Kenney + "kenney_lamp_round_floor.glb", 0f, false),
            new Spec(ModelCatalog.QuaterniusMan, RoundedHumans + "quaternius_man.glb", 0f, true),
            new Spec(ModelCatalog.QuaterniusWoman, RoundedHumans + "quaternius_woman.glb", 0f, true),
            // M5: the personalities' humans (the same 31 bone HumanArmature rig and 11 clips) and the dog.
            new Spec(ModelCatalog.QuaterniusManShorts, RoundedHumans + "quaternius_man_shorts.glb", 0f, true),
            new Spec(ModelCatalog.QuaterniusManSuit, RoundedHumans + "quaternius_man_suit.glb", 0f, true),
            new Spec(ModelCatalog.QuaterniusManTshirt, RoundedHumans + "quaternius_man_tshirt.glb", 0f, true),
            new Spec(ModelCatalog.QuaterniusWomanJacket, RoundedHumans + "quaternius_woman_jacket.glb", 0f, true),
            new Spec(ModelCatalog.QuaterniusWomanDress, RoundedHumans + "quaternius_woman_dress.glb", 0f, true),
            Spec.Pet(ModelCatalog.QuaterniusShiba, Quaternius + "quaternius_shiba.glb", Tuning.DogEyeHeight, "Idle", "Walk"),
        };

        [MenuItem("OutOfSight/Build Model Catalog")]
        public static void Build()
        {
            var entries = new List<ModelCatalog.Entry>();
            var log = new StringBuilder("[ModelCatalogBuilder] catalog:\n");
            foreach (Spec spec in Specs)
            {
                ModelCatalog.Entry entry = Measure(spec, log);
                if (entry != null)
                {
                    entries.Add(entry);
                }
            }

            var catalog = AssetDatabase.LoadAssetAtPath<ModelCatalog>(AssetPath);
            if (catalog == null)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(AssetPath) ?? "Assets/Resources");
                catalog = ScriptableObject.CreateInstance<ModelCatalog>();
                catalog.entries = entries;
                AssetDatabase.CreateAsset(catalog, AssetPath);
                log.Append("  created ").Append(AssetPath).Append('\n');
            }
            else if (!SameEntries(catalog.entries, entries))
            {
                catalog.entries = entries;
                EditorUtility.SetDirty(catalog);
                log.Append("  updated ").Append(AssetPath).Append('\n');
            }
            else
            {
                log.Append("  unchanged ").Append(AssetPath).Append('\n');
            }
            BuildTextureLibrary(log);
            AssetDatabase.SaveAssets();
            Debug.Log(log.ToString());
        }

        // ----- M4.2 textures -----

        public const string TextureLibraryPath = "Assets/Resources/TextureLibrary.asset";
        /// <summary>
        /// Where the shipped details and normal maps live: derived by tools/assets/derive_env_textures.py from the
        /// product owner's environment images (Assets/Art/Environment/&lt;surface&gt;.png, docs/LICENSES.md). They
        /// replaced the ambientCG derived ones (Assets/ThirdParty/Textures/ambientCG, left on disk, no longer shipped).
        /// </summary>
        private const string DetailFolder = "Assets/Art/Environment/Detail/";

        /// <summary>
        /// M7 real colours (CONTRACT_M7 5): where the shipped colour maps live, derived by tools/assets/derive_env_colours.py
        /// from the same images (seamless, 512, sRGB, in phase with the normal maps), plus the player furniture's own
        /// colour map from the owner's red painted metal image (<see cref="PlayerSource"/>).
        /// </summary>
        private const string ColourFolder = "Assets/Art/Environment/Colour/";

        private const string PlayerColourFile = "colour_player.png";

        /// <summary>The owner's red image the player's colour map comes from (its file stem in Assets/Art/Environment).</summary>
        private const string PlayerSource = "red_metal_source";

        /// <summary>Import size of every detail texture: they tile, so 512 is plenty at the game's camera distance.</summary>
        public const int DetailMaxSize = 512;

        /// <summary>
        /// The detail of each surface: a 512 x 512 grayscale derivative of the product owner's image of that surface
        /// (its file stem is the source), mean 240 / 255, highlights capped at 1.0, seamless. M7 (CONTRACT_M7 1.2):
        /// <c>normalFile</c> is the matching 512 tangent space normal map (a gentle one derived from the detail itself),
        /// or null where the surface is not in the 1.2 list (Plastic, Foliage, Soil stay bump-free).
        /// </summary>
        private static readonly (Surface surface, string file, string source, string normalFile)[] Details =
        {
            (Surface.Wood, "detail_wood.png", "wood", "normal_wood.png"),
            (Surface.Parquet, "detail_parquet.png", "parquet", "normal_parquet.png"),
            (Surface.Plaster, "detail_plaster.png", "plaster", "normal_plaster.png"),
            (Surface.Upholstery, "detail_upholstery.png", "upholstery", "normal_upholstery.png"),
            (Surface.Linen, "detail_linen.png", "linen", "normal_linen.png"),
            (Surface.Carpet, "detail_carpet.png", "carpet", "normal_carpet.png"),
            // M6 texture pass 2 (CONTRACT_M6 2.4, docs/M6_TEXTURES_RESEARCH.md).
            (Surface.Grass, "detail_grass.png", "grass", "normal_grass.png"),
            (Surface.Lacquer, "detail_lacquer.png", "lacquer", "normal_lacquer.png"),
            (Surface.Metal, "detail_metal.png", "metal", "normal_metal.png"),
            (Surface.Plastic, "detail_plastic.png", "plastic", null),
            (Surface.Foliage, "detail_foliage.png", "foliage", null),
            (Surface.Soil, "detail_soil.png", "soil", null),
            // M7 textures (CONTRACT_M7 1.2): the kitchen and bathroom floor tiles.
            (Surface.Tile, "detail_tile.png", "tile", "normal_tile.png"),
        };

        /// <summary>
        /// Builds Assets/Resources/TextureLibrary.asset (what ships the textures in the player) and enforces the import
        /// settings of every detail: linear (a texel is a multiplier, not a colour), mipmaps, repeat, trilinear, 512, high
        /// quality platform compression, not readable. M7 real colours (CONTRACT_M7 5): every surface's colour map and the
        /// player's, the same settings but sRGB, with their measured mean colours. Idempotent: reimports and writes only
        /// what changed.
        /// </summary>
        [MenuItem("OutOfSight/Build Texture Library")]
        public static void BuildTextureLibrary()
        {
            var log = new StringBuilder("[ModelCatalogBuilder] texture library:\n");
            BuildTextureLibrary(log);
            AssetDatabase.SaveAssets();
            Debug.Log(log.ToString());
        }

        private static void BuildTextureLibrary(StringBuilder log)
        {
            var entries = new List<TextureLibrary.Entry>();
            foreach ((Surface surface, string file, string source, string normalFile) in Details)
            {
                string path = DetailFolder + file;
                if (!(AssetImporter.GetAtPath(path) is TextureImporter importer))
                {
                    Debug.LogWarning($"[ModelCatalogBuilder] {surface}: no texture at {path}; the surface stays flat at run time");
                    continue;
                }
                if (ConfigureDetailImporter(importer))
                {
                    importer.SaveAndReimport();
                    log.Append("  reimported ").Append(path).Append('\n');
                }
                var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(path);
                float mean = MeanTexel(path);
                // M7 textures (CONTRACT_M7 1.2): the matching normal map, imported as Unity's Normal map type.
                Texture2D normal = null;
                if (!string.IsNullOrEmpty(normalFile))
                {
                    string normalPath = DetailFolder + normalFile;
                    if (AssetImporter.GetAtPath(normalPath) is TextureImporter normalImporter)
                    {
                        if (ConfigureNormalImporter(normalImporter))
                        {
                            normalImporter.SaveAndReimport();
                            log.Append("  reimported ").Append(normalPath).Append('\n');
                        }
                        normal = AssetDatabase.LoadAssetAtPath<Texture2D>(normalPath);
                    }
                    else
                    {
                        Debug.LogWarning($"[ModelCatalogBuilder] {surface}: no normal map at {normalPath}; the surface stays bump-free at run time");
                    }
                }
                // M7 real colours (CONTRACT_M7 5): the surface's colour map, imported sRGB.
                Texture2D colour = LoadColourMap(ColourFolder + "colour_" + source + ".png", log);
                if (colour == null)
                {
                    Debug.LogWarning($"[ModelCatalogBuilder] {surface}: no colour map at {ColourFolder}colour_{source}.png; the surface keeps its palette colour at run time");
                }
                Color colourMean = colour != null ? MeanColour(ColourFolder + "colour_" + source + ".png") : Color.clear;
                entries.Add(new TextureLibrary.Entry
                {
                    surface = surface, texture = texture, mean = mean, source = source, normal = normal, colour = colour, colourMean = colourMean,
                });
                log.Append($"  {surface}: {file}, mean {F(mean)}, {(texture != null ? texture.width + " px, " + texture.mipmapCount + " mips, " + texture.graphicsFormat : "not loaded")}" +
                    $"{(normal != null ? ", normal " + normalFile : "")}{(colour != null ? ", colour " + colour.graphicsFormat : "")}\n");
            }
            Texture2D playerColour = LoadColourMap(ColourFolder + PlayerColourFile, log);
            if (playerColour == null)
            {
                Debug.LogWarning($"[ModelCatalogBuilder] no player colour map at {ColourFolder}{PlayerColourFile}; the player furniture keeps its palette red at run time");
            }
            string playerSource = playerColour != null ? PlayerSource : null;
            Color playerMean = playerColour != null ? MeanColour(ColourFolder + PlayerColourFile) : Color.clear;

            var library = AssetDatabase.LoadAssetAtPath<TextureLibrary>(TextureLibraryPath);
            if (library == null)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(TextureLibraryPath) ?? "Assets/Resources");
                library = ScriptableObject.CreateInstance<TextureLibrary>();
                library.entries = entries;
                library.playerColour = playerColour;
                library.playerSource = playerSource;
                library.playerMean = playerMean;
                AssetDatabase.CreateAsset(library, TextureLibraryPath);
                log.Append("  created ").Append(TextureLibraryPath).Append('\n');
            }
            else if (!SameDetails(library.entries, entries) || library.playerColour != playerColour || library.playerSource != playerSource
                || library.playerMean != playerMean)
            {
                library.entries = entries;
                library.playerColour = playerColour;
                library.playerSource = playerSource;
                library.playerMean = playerMean;
                EditorUtility.SetDirty(library);
                log.Append("  updated ").Append(TextureLibraryPath).Append('\n');
            }
            else
            {
                log.Append("  unchanged ").Append(TextureLibraryPath).Append('\n');
            }
        }

        /// <summary>
        /// Sets the detail import settings (a colour map: the same, but <paramref name="srgb"/>); true when anything
        /// changed (a reimport is needed).
        /// </summary>
        private static bool ConfigureDetailImporter(TextureImporter t, bool srgb = false)
        {
            bool changed = false;
            if (t.textureType != TextureImporterType.Default) { t.textureType = TextureImporterType.Default; changed = true; }
            if (t.textureShape != TextureImporterShape.Texture2D) { t.textureShape = TextureImporterShape.Texture2D; changed = true; }
            if (t.sRGBTexture != srgb) { t.sRGBTexture = srgb; changed = true; }
            if (t.alphaSource != TextureImporterAlphaSource.None) { t.alphaSource = TextureImporterAlphaSource.None; changed = true; }
            if (!t.mipmapEnabled) { t.mipmapEnabled = true; changed = true; }
            if (t.isReadable) { t.isReadable = false; changed = true; }
            if (t.wrapMode != TextureWrapMode.Repeat) { t.wrapMode = TextureWrapMode.Repeat; changed = true; }
            if (t.filterMode != FilterMode.Trilinear) { t.filterMode = FilterMode.Trilinear; changed = true; }
            if (t.anisoLevel != 2) { t.anisoLevel = 2; changed = true; }
            if (t.maxTextureSize != DetailMaxSize) { t.maxTextureSize = DetailMaxSize; changed = true; }
            if (t.textureCompression != TextureImporterCompression.CompressedHQ) { t.textureCompression = TextureImporterCompression.CompressedHQ; changed = true; }
            if (t.npotScale != TextureImporterNPOTScale.ToNearest) { t.npotScale = TextureImporterNPOTScale.ToNearest; changed = true; }
            changed |= ConfigureAndroidOverride(t);
            return changed;
        }

        /// <summary>
        /// M7 real colours (CONTRACT_M7 5): imports a colour map (sRGB, otherwise as a detail: mipmaps, repeat, trilinear,
        /// 512, high quality compression, not readable) and loads it; null when there is no texture at that path.
        /// </summary>
        private static Texture2D LoadColourMap(string path, StringBuilder log)
        {
            if (!(AssetImporter.GetAtPath(path) is TextureImporter importer))
            {
                return null;
            }
            if (ConfigureDetailImporter(importer, true))
            {
                importer.SaveAndReimport();
                log.Append("  reimported ").Append(path).Append('\n');
            }
            return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
        }

        /// <summary>
        /// M7 (CONTRACT_M7 1.2): sets a normal map's import settings (Unity's Normal map type, so the platform
        /// compressor and the shader's UnpackNormal pick the right encoding whatever the target); true when anything
        /// changed (a reimport is needed). The source PNG already encodes a tangent space normal (OpenGL convention,
        /// derived offline by tools/assets/derive_env_textures.py): "create from grayscale" stays off.
        /// </summary>
        private static bool ConfigureNormalImporter(TextureImporter t)
        {
            bool changed = false;
            if (t.textureType != TextureImporterType.NormalMap) { t.textureType = TextureImporterType.NormalMap; changed = true; }
            if (t.textureShape != TextureImporterShape.Texture2D) { t.textureShape = TextureImporterShape.Texture2D; changed = true; }
            if (t.alphaSource != TextureImporterAlphaSource.None) { t.alphaSource = TextureImporterAlphaSource.None; changed = true; }
            if (!t.mipmapEnabled) { t.mipmapEnabled = true; changed = true; }
            if (t.isReadable) { t.isReadable = false; changed = true; }
            if (t.wrapMode != TextureWrapMode.Repeat) { t.wrapMode = TextureWrapMode.Repeat; changed = true; }
            if (t.filterMode != FilterMode.Trilinear) { t.filterMode = FilterMode.Trilinear; changed = true; }
            if (t.anisoLevel != 2) { t.anisoLevel = 2; changed = true; }
            if (t.maxTextureSize != DetailMaxSize) { t.maxTextureSize = DetailMaxSize; changed = true; }
            if (t.textureCompression != TextureImporterCompression.CompressedHQ) { t.textureCompression = TextureImporterCompression.CompressedHQ; changed = true; }
            if (t.npotScale != TextureImporterNPOTScale.ToNearest) { t.npotScale = TextureImporterNPOTScale.ToNearest; changed = true; }
            changed |= ConfigureAndroidOverride(t);
            return changed;
        }

        /// <summary>
        /// Compact APK: an Android only override (ASTC 6x6 at the 512 px source size) for the tiling detail and
        /// normal maps. The default (PC) settings are untouched; on a phone screen 6x6 blocks are not visible on these
        /// low contrast tiling maps, and they take less than half the bytes of the default 4x4.
        /// </summary>
        private static bool ConfigureAndroidOverride(TextureImporter t)
        {
            TextureImporterPlatformSettings android = t.GetPlatformTextureSettings("Android");
            if (android.overridden && android.maxTextureSize == DetailMaxSize && android.format == TextureImporterFormat.ASTC_6x6)
            {
                return false;
            }
            android.overridden = true;
            android.maxTextureSize = DetailMaxSize;
            android.format = TextureImporterFormat.ASTC_6x6;
            t.SetPlatformTextureSettings(android);
            return true;
        }

        /// <summary>The mean texel (red channel, r = g = b) of the source PNG, read from the file, as a linear multiplier.</summary>
        private static float MeanTexel(string path)
        {
            var image = new Texture2D(2, 2, TextureFormat.RGBA32, false, true);
            try
            {
                if (!image.LoadImage(File.ReadAllBytes(path)))
                {
                    return float.NaN;
                }
                Color32[] pixels = image.GetPixels32();
                double sum = 0;
                foreach (Color32 p in pixels)
                {
                    sum += p.r;
                }
                return pixels.Length > 0 ? (float)(sum / pixels.Length / 255.0) : float.NaN;
            }
            finally
            {
                Object.DestroyImmediate(image);
            }
        }

        /// <summary>M7 real colours: the mean texel of an sRGB colour map PNG, in linear (each texel decoded, then averaged).</summary>
        private static Color MeanColour(string path)
        {
            var image = new Texture2D(2, 2, TextureFormat.RGBA32, false, true);
            try
            {
                if (!image.LoadImage(File.ReadAllBytes(path)))
                {
                    return Color.clear;
                }
                var lut = new double[256];
                for (int i = 0; i < 256; i++)
                {
                    lut[i] = Mathf.GammaToLinearSpace(i / 255f);
                }
                Color32[] pixels = image.GetPixels32();
                double r = 0, g = 0, b = 0;
                foreach (Color32 p in pixels)
                {
                    r += lut[p.r];
                    g += lut[p.g];
                    b += lut[p.b];
                }
                int n = Mathf.Max(1, pixels.Length);
                // Rounded to 1e-4 so an unchanged PNG compares equal across builds (no needless asset write).
                return new Color(Round4(r / n), Round4(g / n), Round4(b / n), 1f);
            }
            finally
            {
                Object.DestroyImmediate(image);
            }
        }

        private static float Round4(double v) => (float)System.Math.Round(v, 4);

        private static bool SameDetails(List<TextureLibrary.Entry> a, List<TextureLibrary.Entry> b)
        {
            if (a == null || a.Count != b.Count)
            {
                return false;
            }
            for (int i = 0; i < a.Count; i++)
            {
                if (a[i] == null || a[i].surface != b[i].surface || a[i].texture != b[i].texture || a[i].source != b[i].source
                    || a[i].normal != b[i].normal || a[i].colour != b[i].colour || a[i].colourMean != b[i].colourMean
                    || Mathf.Abs(a[i].mean - b[i].mean) > 1e-6f)
                {
                    return false;
                }
            }
            return true;
        }

        // ----- Measuring -----

        private static ModelCatalog.Entry Measure(Spec spec, StringBuilder log)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(spec.Path);
            if (prefab == null)
            {
                Debug.LogWarning($"[ModelCatalogBuilder] {spec.Id}: no imported GameObject at {spec.Path}; the id is left out and falls back at run time");
                return null;
            }
            GameObject probe = Object.Instantiate(prefab);
            probe.hideFlags = HideFlags.HideAndDontSave;
            try
            {
                Transform root = probe.transform;
                root.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
                root.localScale = Vector3.one;
                var entry = new ModelCatalog.Entry
                {
                    id = spec.Id, prefab = prefab, rigged = spec.Rigged, kind = spec.Kind ?? string.Empty, targetEyeHeight = spec.TargetEye,
                    idleClip = spec.IdleClip ?? string.Empty, walkClip = spec.WalkClip ?? string.Empty,
                };
                log.Append($"  {spec.Id}: prefab root local {Fmt(prefab.transform.localPosition)} {Fmt(prefab.transform.localEulerAngles)} {Fmt(prefab.transform.localScale)}");
                if (!spec.Rigged)
                {
                    if (!StaticBounds(probe, out Bounds b))
                    {
                        Debug.LogWarning($"[ModelCatalogBuilder] {spec.Id}: no renderer in {spec.Path}");
                        return null;
                    }
                    entry.nativeSize = b.size;
                    entry.boundsCenter = b.center;
                    entry.yawOffset = ModelMath.SnapYaw(spec.Yaw);
                    log.Append($", size {Fmt(b.size)}, centre {Fmt(b.center)}, yaw {entry.yawOffset}, renderers {probe.GetComponentsInChildren<Renderer>(true).Length}\n");
                    return entry;
                }
                return MeasureRigged(spec, prefab, probe, entry, log);
            }
            finally
            {
                Object.DestroyImmediate(probe);
            }
        }

        /// <summary>Union of the renderer bounds (the root is at the origin: world space is root space).</summary>
        private static bool StaticBounds(GameObject probe, out Bounds bounds)
        {
            bounds = default;
            bool any = false;
            foreach (Renderer r in probe.GetComponentsInChildren<Renderer>(true))
            {
                if (r is SkinnedMeshRenderer)
                {
                    continue;
                }
                if (!any)
                {
                    bounds = r.bounds;
                    any = true;
                }
                else
                {
                    bounds.Encapsulate(r.bounds);
                }
            }
            return any;
        }

        private static ModelCatalog.Entry MeasureRigged(Spec spec, GameObject prefab, GameObject probe, ModelCatalog.Entry entry, StringBuilder log)
        {
            SkinnedMeshRenderer skin = probe.GetComponentInChildren<SkinnedMeshRenderer>(true);
            Transform head = FindDeep(probe.transform, HeadBoneName);
            if (skin == null || skin.sharedMesh == null || head == null)
            {
                Debug.LogWarning($"[ModelCatalogBuilder] {spec.Id}: skinned mesh or bone '{HeadBoneName}' missing in {spec.Path}");
                return null;
            }
            // The eye materials: "Eyes" for a human, every "Eyes_*" for a pet (M5).
            var eyeSlots = new List<int>();
            Material[] slots = skin.sharedMaterials;
            for (int i = 0; i < slots.Length && i < skin.sharedMesh.subMeshCount; i++)
            {
                string n = slots[i] != null ? slots[i].name : string.Empty;
                if (spec.PetEyes ? n.StartsWith(PetEyeMaterialPrefix, System.StringComparison.Ordinal) : n == EyeMaterialName)
                {
                    eyeSlots.Add(i);
                }
            }
            if (eyeSlots.Count == 0)
            {
                Debug.LogWarning($"[ModelCatalogBuilder] {spec.Id}: no '{(spec.PetEyes ? PetEyeMaterialPrefix + "*" : EyeMaterialName)}' material on the skinned mesh");
                return null;
            }

            // The rest pose, baked: every vertex where it is drawn.
            var baked = new Mesh();
            try
            {
                // With useScale, the baked vertices are in the renderer's local space, its scale included (the
                // Quaternius mesh node carries scale 100): its full local to world matrix brings them to root space.
                skin.BakeMesh(baked, true);
                Matrix4x4 toRoot = skin.transform.localToWorldMatrix;
                Vector3[] vertices = baked.vertices;
                var bounds = new Bounds(toRoot.MultiplyPoint3x4(vertices[0]), Vector3.zero);
                foreach (Vector3 v in vertices)
                {
                    bounds.Encapsulate(toRoot.MultiplyPoint3x4(v));
                }
                // The "Eyes" material is the near-black of the model: the man's shoes use it too. Only its vertices
                // in the head region (the top fifth of the body) are eyes. A pet's "Eyes_*" are only eyes (its head is
                // at the front, not on top): all of their vertices.
                float headRegion = spec.PetEyes ? float.MinValue : bounds.min.y + (1f - HeadRegion) * bounds.size.y;
                var eyeVertices = new HashSet<int>();
                foreach (int eyeSlot in eyeSlots)
                {
                    foreach (int i in baked.GetIndices(eyeSlot))
                    {
                        if (toRoot.MultiplyPoint3x4(vertices[i]).y >= headRegion)
                        {
                            eyeVertices.Add(i);
                        }
                    }
                }
                if (eyeVertices.Count == 0)
                {
                    Debug.LogWarning($"[ModelCatalogBuilder] {spec.Id}: no '{EyeMaterialName}' vertex in the head region");
                    return null;
                }
                Vector3 eyeSum = Vector3.zero;
                foreach (int i in eyeVertices)
                {
                    eyeSum += toRoot.MultiplyPoint3x4(vertices[i]);
                }
                Vector3 eyeRest = eyeSum / eyeVertices.Count;

                entry.nativeSize = bounds.size;
                entry.boundsCenter = bounds.center;
                entry.headBone = HeadBoneName;
                entry.eyeLocal = head.InverseTransformPoint(eyeRest);
                // Facing: the eyes stand ahead of the head bone.
                Vector3 ahead = YawMath.Planar(eyeRest - head.position);
                entry.yawOffset = ModelMath.YawOffsetFacing(ahead);

                // Eye height: mean over the Idle clip when it samples, else the rest pose.
                float restHeight = eyeRest.y;
                float idleHeight = IdleEyeHeight(spec.Path, probe, head, entry.eyeLocal, spec.IdleClip, out string clipName);
                entry.eyeHeight = idleHeight > 0f ? idleHeight : restHeight;
                log.Append($", size {Fmt(bounds.size)}, centre {Fmt(bounds.center)}, head '{head.name}' lossy scale {Fmt(head.lossyScale)}, ")
                    .Append($"head y {F(head.position.y)}, eye {Fmt(eyeRest)} local {Fmt(entry.eyeLocal, "0.#####")} ({eyeVertices.Count} vertices), ")
                    .Append($"facing {Fmt(ahead)} so yaw {entry.yawOffset}, ")
                    .Append($"eye height rest {F(restHeight)} idle {F(idleHeight)} ({clipName ?? "no clip"}), bones {skin.bones.Length}, ")
                    .Append($"triangles {ModelKit.Triangles(skin.sharedMesh)}, slots {slots.Length}\n");
                CheckBudgets(spec, prefab, skin, log);
                return entry;
            }
            finally
            {
                Object.DestroyImmediate(baked);
            }
        }

        /// <summary>
        /// The mean eye height over the Idle clip (root space) with the head held in its bind-pose orientation, as
        /// InhabitantRig holds it (M3.1 N4: the glTF rest pose tilts the head by 3.5 to 4.8 deg), or 0 when there is
        /// no such clip.
        /// </summary>
        private static float IdleEyeHeight(string path, GameObject probe, Transform head, Vector3 eyeLocal, string exactIdle, out string clipName)
        {
            clipName = null;
            AnimationClip idle = null;
            foreach (Object o in AssetDatabase.LoadAllAssetsAtPath(path))
            {
                if (o is AnimationClip clip && (string.IsNullOrEmpty(exactIdle)
                    ? clip.name.EndsWith(IdleSuffix, System.StringComparison.Ordinal)
                    : clip.name == exactIdle))
                {
                    idle = clip;
                }
            }
            if (idle == null || idle.length <= 0f)
            {
                return 0f;
            }
            clipName = idle.name;
            return ModelKit.IdleEyeHeight(probe, idle, head, eyeLocal, null, IdleSamples);
        }

        /// <summary>
        /// M5: PRD 7.4 on the imported character, at build time: at most Tuning.BudgetInhabitantTriangles triangles, and at
        /// most 40 bones (a pet: Tuning.BudgetPetBones), counted as the skin's distinct bones. A warning when over; the
        /// probe and the audit fail on it in the levels (and ModelM5Tests on the catalog).
        /// </summary>
        private static void CheckBudgets(Spec spec, GameObject prefab, SkinnedMeshRenderer skin, StringBuilder log)
        {
            var bones = new HashSet<Transform>();
            foreach (Transform b in skin.bones)
            {
                if (b != null)
                {
                    bones.Add(b);
                }
            }
            long triangles = ModelKit.Triangles(skin.sharedMesh);
            int boneBudget = spec.Kind == ModelCatalog.KindPet ? Tuning.BudgetPetBones : Tuning.BudgetInhabitantBones;
            log.Append($"    {spec.Id} ({spec.Kind}): {bones.Count} bones of {boneBudget}, {triangles} triangles of {Tuning.BudgetInhabitantTriangles}\n");
            if (bones.Count > boneBudget || triangles > Tuning.BudgetInhabitantTriangles)
            {
                Debug.LogWarning($"[ModelCatalogBuilder] {spec.Id} ({prefab.name}) is over budget: {bones.Count} bones (max {boneBudget}), {triangles} triangles (max {Tuning.BudgetInhabitantTriangles})");
            }
        }

        private static Transform FindDeep(Transform t, string name)
        {
            if (t.name == name)
            {
                return t;
            }
            for (int i = 0; i < t.childCount; i++)
            {
                Transform found = FindDeep(t.GetChild(i), name);
                if (found != null)
                {
                    return found;
                }
            }
            return null;
        }

        // ----- Idempotence -----

        private static bool SameEntries(List<ModelCatalog.Entry> a, List<ModelCatalog.Entry> b)
        {
            if (a == null || a.Count != b.Count)
            {
                return false;
            }
            for (int i = 0; i < a.Count; i++)
            {
                ModelCatalog.Entry x = a[i];
                ModelCatalog.Entry y = b[i];
                if (x == null || x.id != y.id || x.prefab != y.prefab || x.rigged != y.rigged || x.headBone != y.headBone
                    || !Near(x.nativeSize, y.nativeSize) || !Near(x.boundsCenter, y.boundsCenter) || !Near(x.eyeLocal, y.eyeLocal)
                    || Mathf.Abs(x.yawOffset - y.yawOffset) > 1e-4f || Mathf.Abs(x.eyeHeight - y.eyeHeight) > 1e-5f
                    || (x.kind ?? string.Empty) != (y.kind ?? string.Empty) || Mathf.Abs(x.targetEyeHeight - y.targetEyeHeight) > 1e-6f
                    || (x.idleClip ?? string.Empty) != (y.idleClip ?? string.Empty) || (x.walkClip ?? string.Empty) != (y.walkClip ?? string.Empty))
                {
                    return false;
                }
            }
            return true;
        }

        private static bool Near(Vector3 a, Vector3 b) => (a - b).sqrMagnitude < 1e-10f;

        private static string F(float v) => v.ToString("0.####", CultureInfo.InvariantCulture);

        private static string Fmt(Vector3 v, string f = "0.####")
        {
            CultureInfo c = CultureInfo.InvariantCulture;
            return $"({v.x.ToString(f, c)}, {v.y.ToString(f, c)}, {v.z.ToString(f, c)})";
        }
    }
}
