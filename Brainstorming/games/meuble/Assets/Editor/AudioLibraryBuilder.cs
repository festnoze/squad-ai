using System.IO;
using UnityEditor;
using UnityEngine;

namespace Meuble.Editor
{
    /// <summary>
    /// Builds Assets/Resources/AudioLibrary.asset from the clips of Assets/ThirdParty/Audio (docs/CONTRACT_M3.md 7,
    /// docs/M3_AUDIO.md), and applies their import settings first. Idempotent: an importer is only reimported
    /// when a setting differs, and the asset is only written when its content changes.
    ///
    /// Import settings (the clips are mono 44.1 kHz 16-bit already, docs/M3_AUDIO.md section 3):
    /// - short percussive one-shots (hops, scrapes, footsteps, thump, short creak, UI click): Decompress On
    ///   Load, ADPCM. No decode at trigger time, 3.5:1 on disk, and ADPCM noise hides under a transient;
    /// - tonal one-shots (stings, long creak, vocal): Decompress On Load, Vorbis, where ADPCM hiss would show
    ///   on a sustained tone;
    /// - the two loops: Compressed In Memory, Vorbis (a few KB resident, decoded while playing).
    /// Force To Mono is on with Normalize off: a mono clip passes through untouched, and Normalize would peak
    /// normalize the clip and undo the RMS matching below. Preload Audio Data is on: without it a clip must be
    /// loaded by script before it plays.
    /// </summary>
    public static class AudioLibraryBuilder
    {
        public const string AudioFolder = "Assets/ThirdParty/Audio";
        public const string AssetPath = "Assets/Resources/AudioLibrary.asset";

        private const float TonalQuality = 0.7f;
        private const float LoopQuality = 0.5f;

        private enum Kind
        {
            OneShot,
            Tonal,
            Loop,
        }

        private readonly struct Spec
        {
            public readonly string File;
            public readonly Kind Kind;
            public readonly float ActiveRmsDb;

            public Spec(string file, Kind kind, float activeRmsDb)
            {
                File = file;
                Kind = kind;
                ActiveRmsDb = activeRmsDb;
            }
        }

        // Active RMS of each imported file in dBFS, from docs/M3_AUDIO.md section 3 (re-measured on the files of
        // Assets/ThirdParty/Audio on 2026-11-12: identical to 0.1 dB).
        private static readonly Spec[] Specs =
        {
            new Spec("hop_01", Kind.OneShot, -17.1f),
            new Spec("hop_02", Kind.OneShot, -16.0f),
            new Spec("hop_03", Kind.OneShot, -20.1f),
            new Spec("hop_04", Kind.OneShot, -16.0f),
            new Spec("scrape_01", Kind.OneShot, -18.0f),
            new Spec("scrape_02", Kind.OneShot, -18.0f),
            new Spec("scrape_03", Kind.OneShot, -18.0f),
            new Spec("creak_long", Kind.Tonal, -18.0f),
            new Spec("creak_short", Kind.OneShot, -18.0f),
            new Spec("footstep_01", Kind.OneShot, -20.0f),
            new Spec("footstep_02", Kind.OneShot, -18.1f),
            new Spec("footstep_03", Kind.OneShot, -20.5f),
            new Spec("footstep_04", Kind.OneShot, -19.7f),
            new Spec("footstep_05", Kind.OneShot, -18.0f),
            new Spec("roomtone_airvent_loop", Kind.Loop, -30.0f),
            new Spec("roomtone_clock_loop", Kind.Loop, -30.0f),
            new Spec("thump", Kind.OneShot, -17.1f),
            new Spec("sting_caught", Kind.Tonal, -16.0f),
            new Spec("sting_caught_long", Kind.Tonal, -16.0f),
            new Spec("vocal_huh", Kind.Tonal, -18.0f),
            new Spec("ui_click", Kind.OneShot, -19.2f),
        };

        public static void Build()
        {
            int reimported = 0;
            foreach (Spec spec in Specs)
            {
                if (ApplyImportSettings(spec))
                {
                    reimported++;
                }
            }

            AudioLibrary library = AssetDatabase.LoadAssetAtPath<AudioLibrary>(AssetPath);
            bool created = library == null;
            if (created)
            {
                string folder = Path.GetDirectoryName(AssetPath)?.Replace('\\', '/');
                if (!string.IsNullOrEmpty(folder) && !AssetDatabase.IsValidFolder(folder))
                {
                    AssetDatabase.CreateFolder("Assets", "Resources");
                }
                library = ScriptableObject.CreateInstance<AudioLibrary>();
            }
            string before = created ? string.Empty : EditorJsonUtility.ToJson(library);

            library.hops = Entries("hop_01", "hop_02", "hop_03", "hop_04");
            library.scrapes = Entries("scrape_01", "scrape_02", "scrape_03");
            library.creakLong = Entry("creak_long");
            library.creakShort = Entry("creak_short");
            library.footsteps = Entries("footstep_01", "footstep_02", "footstep_03", "footstep_04", "footstep_05");
            library.roomTone = Entry("roomtone_airvent_loop");
            library.clockLoop = Entry("roomtone_clock_loop");
            library.thump = Entry("thump");
            library.stingCaught = Entry("sting_caught");
            library.stingCaughtLong = Entry("sting_caught_long");
            library.vocalHuh = Entry("vocal_huh");
            library.uiClick = Entry("ui_click");

            if (created)
            {
                AssetDatabase.CreateAsset(library, AssetPath);
            }
            else if (EditorJsonUtility.ToJson(library) != before)
            {
                EditorUtility.SetDirty(library);
            }
            AssetDatabase.SaveAssets();
            Debug.Log($"[AudioLibraryBuilder] {AssetPath}: {library.ClipCount} clips by role, {reimported} importer(s) updated{(created ? ", asset created" : string.Empty)}.");
        }

        private static AudioLibrary.Entry[] Entries(params string[] files)
        {
            var entries = new AudioLibrary.Entry[files.Length];
            for (int i = 0; i < files.Length; i++)
            {
                entries[i] = Entry(files[i]);
            }
            return entries;
        }

        private static AudioLibrary.Entry Entry(string file)
        {
            Spec spec = Find(file);
            string path = PathOf(file);
            var clip = AssetDatabase.LoadAssetAtPath<AudioClip>(path);
            if (clip == null)
            {
                // A missing clip leaves the role empty: Sfx then synthesizes it, or stays silent for a new sound.
                Debug.LogWarning($"[AudioLibraryBuilder] missing clip {path}: the role stays empty.");
            }
            else if (clip.channels != 1)
            {
                Debug.LogWarning($"[AudioLibraryBuilder] {path} has {clip.channels} channels, expected mono.");
            }
            return new AudioLibrary.Entry
            {
                clip = clip,
                activeRmsDb = spec.ActiveRmsDb,
                gain = AudioLibrary.GainFor(spec.ActiveRmsDb),
            };
        }

        private static Spec Find(string file)
        {
            foreach (Spec spec in Specs)
            {
                if (spec.File == file)
                {
                    return spec;
                }
            }
            throw new System.ArgumentException("no audio spec for " + file);
        }

        private static string PathOf(string file) => AudioFolder + "/" + file + ".wav";

        /// <summary>Applies the import settings of one clip. Returns true when the importer had to be reimported.</summary>
        private static bool ApplyImportSettings(Spec spec)
        {
            string path = PathOf(spec.File);
            if (!(AssetImporter.GetAtPath(path) is AudioImporter importer))
            {
                return false;
            }
            AudioImporterSampleSettings wanted = importer.defaultSampleSettings;
            wanted.loadType = spec.Kind == Kind.Loop ? AudioClipLoadType.CompressedInMemory : AudioClipLoadType.DecompressOnLoad;
            wanted.compressionFormat = spec.Kind == Kind.OneShot ? AudioCompressionFormat.ADPCM : AudioCompressionFormat.Vorbis;
            wanted.quality = spec.Kind == Kind.Loop ? LoopQuality : spec.Kind == Kind.Tonal ? TonalQuality : 1f;
            wanted.sampleRateSetting = AudioSampleRateSetting.PreserveSampleRate;
            wanted.preloadAudioData = true;

            AudioImporterSampleSettings current = importer.defaultSampleSettings;
            bool changed = current.loadType != wanted.loadType
                || current.compressionFormat != wanted.compressionFormat
                || (wanted.compressionFormat == AudioCompressionFormat.Vorbis && !Mathf.Approximately(current.quality, wanted.quality))
                || current.sampleRateSetting != wanted.sampleRateSetting
                || current.preloadAudioData != wanted.preloadAudioData;
            if (changed)
            {
                importer.defaultSampleSettings = wanted;
            }
            if (importer.loadInBackground)
            {
                importer.loadInBackground = false;
                changed = true;
            }

            // Normalize is not on the AudioImporter API: it is a serialized field. Mono is forced only once
            // Normalize is known to be off; otherwise the clips, mono already, are left as they are.
            var serialized = new SerializedObject(importer);
            SerializedProperty normalize = serialized.FindProperty("m_Normalize") ?? serialized.FindProperty("normalize");
            if (normalize != null && normalize.boolValue)
            {
                normalize.boolValue = false;
                serialized.ApplyModifiedPropertiesWithoutUndo();
                changed = true;
            }
            bool forceMono = normalize != null;
            if (importer.forceToMono != forceMono)
            {
                importer.forceToMono = forceMono;
                changed = true;
            }

            if (changed)
            {
                importer.SaveAndReimport();
            }
            return changed;
        }
    }
}
