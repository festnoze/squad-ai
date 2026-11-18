using System.IO;
using UnityEditor;
using UnityEngine;

namespace OutOfSight.Editor
{
    /// <summary>
    /// Builds Assets/Resources/AudioLibrary.asset from the clips of Assets/ThirdParty/Audio (docs/CONTRACT_M3.md 7,
    /// docs/audio/AUDIO_REPORT.md), and applies their import settings first. Idempotent: an importer is only reimported
    /// when a setting differs, and the asset is only written when its content changes.
    ///
    /// Import settings (the effects are mono 44.1 kHz 16-bit already, made by tools/audio/audio_pipeline.py):
    /// - short percussive one-shots (hops, scrapes, footsteps, thump, short creak, UI, door, wardrobe, crash, topple, lamp):
    ///   Decompress On Load, ADPCM. No decode at trigger time, 3.5:1 on disk, and ADPCM noise hides under a transient;
    /// - tonal one-shots (stings, long creak, vocal): Decompress On Load, Vorbis, where ADPCM hiss would show on a
    ///   sustained tone;
    /// - the two ambience loops: Compressed In Memory, Vorbis (a few KB resident, decoded while playing);
    /// - the two music loops (stereo, Assets/ThirdParty/Audio/Music): Streaming, Vorbis at <see cref="MusicQuality"/>
    ///   (<see cref="MusicQualityAndroid"/> on Android, where the APK size counts), never forced to mono.
    /// Force To Mono is on for the effects with Normalize off: a mono clip passes through untouched, and Normalize would
    /// peak normalize the clip and undo the loudness matching below. Preload Audio Data is on for the effects (without it
    /// a clip must be loaded by script before it plays) and off for the streamed music.
    /// </summary>
    public static class AudioLibraryBuilder
    {
        public const string AudioFolder = "Assets/ThirdParty/Audio";
        public const string MusicFolder = AudioFolder + "/Music";
        public const string AssetPath = "Assets/Resources/AudioLibrary.asset";

        private const float TonalQuality = 0.7f;
        private const float LoopQuality = 0.5f;

        /// <summary>
        /// Music Vorbis quality (AUDIO_REPORT.md 6): 0.4 measured 62 to 71 kbps stereo in the PC build, audibly thin for
        /// plucked strings; 0.7 on PC and 0.5 on Android keep both loops near 1.5 MB, far under the APK budget.
        /// </summary>
        public const float MusicQuality = 0.7f;
        public const float MusicQualityAndroid = 0.5f;

        private enum Kind
        {
            OneShot,
            Tonal,
            Loop,
            Music,
        }

        private readonly struct Spec
        {
            public readonly string File;
            public readonly Kind Kind;
            public readonly float Loudness;

            public Spec(string file, Kind kind, float loudness)
            {
                File = file;
                Kind = kind;
                Loudness = loudness;
            }
        }

        // Loudness of each imported file in LUFS, from tools/audio/audio_report.json (written by
        // tools/audio/audio_pipeline.py on 2026-11-18): the 100 ms max for a one-shot, the integrated loudness for a loop
        // or the music. Rerunning the pipeline on new picks means copying its new numbers here.
        private static readonly Spec[] Specs =
        {
            new Spec("hop_01", Kind.OneShot, -14.3f),
            new Spec("hop_02", Kind.OneShot, -12.0f),
            new Spec("hop_03", Kind.OneShot, -17.4f),
            new Spec("hop_04", Kind.OneShot, -12.0f),
            new Spec("hop_soft_01", Kind.OneShot, -14.1f),
            new Spec("hop_soft_02", Kind.OneShot, -12.0f),
            new Spec("hop_soft_03", Kind.OneShot, -17.2f),
            new Spec("hop_soft_04", Kind.OneShot, -12.0f),
            new Spec("scrape_01", Kind.OneShot, -12.0f),
            new Spec("scrape_02", Kind.OneShot, -12.0f),
            new Spec("scrape_03", Kind.OneShot, -12.0f),
            new Spec("creak_long", Kind.Tonal, -12.0f),
            new Spec("creak_short", Kind.OneShot, -12.0f),
            new Spec("footstep_01", Kind.OneShot, -14.6f),
            new Spec("footstep_02", Kind.OneShot, -14.3f),
            new Spec("footstep_03", Kind.OneShot, -14.4f),
            new Spec("footstep_04", Kind.OneShot, -16.0f),
            new Spec("footstep_05", Kind.OneShot, -12.3f),
            new Spec("roomtone_airvent_loop", Kind.Loop, -30.0f),
            new Spec("roomtone_clock_loop", Kind.Loop, -30.0f),
            new Spec("thump", Kind.OneShot, -12.0f),
            new Spec("sting_caught", Kind.Tonal, -12.0f),
            new Spec("sting_caught_long", Kind.Tonal, -12.0f),
            new Spec("vocal_huh", Kind.Tonal, -12.0f),
            new Spec("ui_click", Kind.OneShot, -23.1f),
            new Spec("ui_hover", Kind.OneShot, -23.3f),
            new Spec("sting_win", Kind.Tonal, -12.0f),
            new Spec("door_open", Kind.OneShot, -12.0f),
            new Spec("wardrobe_open", Kind.OneShot, -14.3f),
            new Spec("wardrobe_close", Kind.OneShot, -14.2f),
            new Spec("crash", Kind.OneShot, -13.8f),
            new Spec("topple", Kind.OneShot, -15.8f),
            new Spec("lamp_click", Kind.OneShot, -18.0f),
            new Spec("music_title", Kind.Music, -18.0f),
            new Spec("music_level", Kind.Music, -18.2f),
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
            library.softHops = Entries("hop_soft_01", "hop_soft_02", "hop_soft_03", "hop_soft_04");
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
            library.uiHover = Entry("ui_hover");
            library.stingWin = Entry("sting_win");
            library.doorOpen = Entry("door_open");
            library.wardrobeOpen = Entry("wardrobe_open");
            library.wardrobeClose = Entry("wardrobe_close");
            library.crash = Entry("crash");
            library.topple = Entry("topple");
            library.lampClick = Entry("lamp_click");
            library.musicTitle = Entry("music_title");
            library.musicLevel = Entry("music_level");

            if (created)
            {
                AssetDatabase.CreateAsset(library, AssetPath);
            }
            else if (EditorJsonUtility.ToJson(library) != before)
            {
                EditorUtility.SetDirty(library);
            }
            AssetDatabase.SaveAssets();
            Debug.Log($"[AudioLibraryBuilder] {AssetPath}: {library.ClipCount} effect clips by role, music "
                + $"{(AudioLibrary.Has(library.musicTitle) ? 1 : 0) + (AudioLibrary.Has(library.musicLevel) ? 1 : 0)}/2, {reimported} importer(s) updated"
                + $"{(created ? ", asset created" : string.Empty)}.");
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
            string path = PathOf(spec);
            var clip = AssetDatabase.LoadAssetAtPath<AudioClip>(path);
            if (clip == null)
            {
                // A missing clip leaves the role empty: Sfx then synthesizes it, or stays silent for a new sound.
                Debug.LogWarning($"[AudioLibraryBuilder] missing clip {path}: the role stays empty.");
            }
            else if (spec.Kind != Kind.Music && clip.channels != 1)
            {
                Debug.LogWarning($"[AudioLibraryBuilder] {path} has {clip.channels} channels, expected mono.");
            }
            return new AudioLibrary.Entry
            {
                clip = clip,
                loudness = spec.Loudness,
                gain = AudioLibrary.GainFor(spec.Loudness),
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

        private static string PathOf(Spec spec) => spec.Kind == Kind.Music ? MusicFolder + "/" + spec.File + ".ogg" : AudioFolder + "/" + spec.File + ".wav";

        /// <summary>Applies the import settings of one clip. Returns true when the importer had to be reimported.</summary>
        private static bool ApplyImportSettings(Spec spec)
        {
            string path = PathOf(spec);
            if (!(AssetImporter.GetAtPath(path) is AudioImporter importer))
            {
                return false;
            }
            bool music = spec.Kind == Kind.Music;
            AudioImporterSampleSettings wanted = importer.defaultSampleSettings;
            wanted.loadType = music ? AudioClipLoadType.Streaming
                : spec.Kind == Kind.Loop ? AudioClipLoadType.CompressedInMemory : AudioClipLoadType.DecompressOnLoad;
            wanted.compressionFormat = spec.Kind == Kind.OneShot ? AudioCompressionFormat.ADPCM : AudioCompressionFormat.Vorbis;
            wanted.quality = music ? MusicQuality : spec.Kind == Kind.Loop ? LoopQuality : spec.Kind == Kind.Tonal ? TonalQuality : 1f;
            wanted.sampleRateSetting = AudioSampleRateSetting.PreserveSampleRate;
            wanted.preloadAudioData = !music;

            AudioImporterSampleSettings current = importer.defaultSampleSettings;
            bool changed = !SameSettings(current, wanted);
            if (changed)
            {
                importer.defaultSampleSettings = wanted;
            }
            if (music)
            {
                // Android: the same streamed Vorbis at a lower quality (the APK budget, AUDIO_REPORT.md 6).
                AudioImporterSampleSettings android = wanted;
                android.quality = MusicQualityAndroid;
                bool hasOverride = importer.ContainsSampleSettingsOverride("Android");
                if (!hasOverride || !SameSettings(importer.GetOverrideSampleSettings("Android"), android))
                {
                    importer.SetOverrideSampleSettings("Android", android);
                    changed = true;
                }
            }
            if (importer.loadInBackground != music)
            {
                // The music may load in the background (it streams); an effect must be ready the instant it plays.
                importer.loadInBackground = music;
                changed = true;
            }

            // Normalize is not on the AudioImporter API: it is a serialized field. Mono is forced only once
            // Normalize is known to be off; otherwise the clips, mono already, are left as they are. Never on the music.
            var serialized = new SerializedObject(importer);
            SerializedProperty normalize = serialized.FindProperty("m_Normalize") ?? serialized.FindProperty("normalize");
            if (normalize != null && normalize.boolValue)
            {
                normalize.boolValue = false;
                serialized.ApplyModifiedPropertiesWithoutUndo();
                changed = true;
            }
            bool forceMono = normalize != null && !music;
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

        private static bool SameSettings(AudioImporterSampleSettings a, AudioImporterSampleSettings b)
        {
            return a.loadType == b.loadType
                && a.compressionFormat == b.compressionFormat
                && (b.compressionFormat != AudioCompressionFormat.Vorbis || Mathf.Approximately(a.quality, b.quality))
                && a.sampleRateSetting == b.sampleRateSetting
                && a.preloadAudioData == b.preloadAudioData;
        }
    }
}
