using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Serialization;

namespace OutOfSight
{
    /// <summary>
    /// Recorded clips by role (docs/CONTRACT_M3.md 7), at Assets/Resources/AudioLibrary.asset, built by
    /// OutOfSight.Editor.AudioLibraryBuilder from Assets/ThirdParty/Audio (docs/M3_AUDIO.md). Being referenced
    /// from Resources is what ships the clips in the player.
    ///
    /// Every entry carries the loudness measured on its file and the gain that brings it to the common
    /// <see cref="ReferenceLufs"/>. Sfx multiplies that gain by its per role mix level, so a role sounds the same
    /// whichever variant plays, and a clip swap only needs a new measurement.
    ///
    /// Audio overhaul (docs/audio/AUDIO_REPORT.md): the loudness is BS.1770 (K-weighted, LUFS scale), measured by
    /// tools/audio/audio_pipeline.py: the max over a 100 ms window for a one-shot, the integrated loudness for a loop and
    /// for the music. New roles fill the silent events (the win, the wardrobe, the menu selection) and replace synthesized
    /// cues with recordings (the room door, the fallen load's crash, the stool's topple, the lamp switch, a muffled hop
    /// for the rugs). The two music loops are entries too, outside <see cref="Roles"/> (stereo and streamed).
    /// </summary>
    public sealed class AudioLibrary : ScriptableObject
    {
        public const string ResourcePath = "AudioLibrary";

        /// <summary>
        /// The common reference loudness every clip's gain brings it to, LUFS. Equal to the pipeline's one-shot file
        /// target, so the playback volume of a role is exactly 10^((target - file loudness) / 20), below 1 for every
        /// playback target under its files' loudness (Tuning: each mix is 10^((playback target - reference) / 20)).
        /// </summary>
        public const float ReferenceLufs = -12f;

        [Serializable]
        public sealed class Entry
        {
            public AudioClip clip;

            /// <summary>Loudness of the file in LUFS (100 ms max for a one-shot, integrated for a loop), docs/audio/AUDIO_REPORT.md.</summary>
            [FormerlySerializedAs("activeRmsDb")] public float loudness;

            /// <summary>Linear gain from <see cref="loudness"/> to <see cref="ReferenceLufs"/> (above 1 for the quiet loops).</summary>
            public float gain = 1f;
        }

        public Entry[] hops = new Entry[0];

        /// <summary>The hops muffled (a 700 Hz low pass of the same recordings): a hop on a rug or in a soft room.</summary>
        public Entry[] softHops = new Entry[0];

        public Entry[] scrapes = new Entry[0];
        public Entry creakLong;
        public Entry creakShort;
        public Entry[] footsteps = new Entry[0];
        public Entry roomTone;
        public Entry clockLoop;
        public Entry thump;
        public Entry stingCaught;
        public Entry stingCaughtLong;
        public Entry vocalHuh;
        public Entry uiClick;

        /// <summary>The menu's selection tick (a new button selected by the mouse, the arrows or the D-pad).</summary>
        public Entry uiHover;

        /// <summary>The win: a rising pizzicato jingle.</summary>
        public Entry stingWin;

        /// <summary>A room door swings open (replaces the synthesized latch and hinge).</summary>
        public Entry doorOpen;

        /// <summary>The wardrobe's doors open as the furniture goes in or out, and shut at the end of the action.</summary>
        public Entry wardrobeOpen;
        public Entry wardrobeClose;

        /// <summary>The fallen load breaks (replaces the synthesized knock and shards).</summary>
        public Entry crash;

        /// <summary>The stool tips over (replaces the synthesized clatter).</summary>
        public Entry topple;

        /// <summary>The floor lamp's switch (replaces the synthesized press and release).</summary>
        public Entry lampClick;

        /// <summary>Music (<see cref="MusicPlayer"/>): the title page loop and the in-level loop, stereo, streamed.</summary>
        public Entry musicTitle;
        public Entry musicLevel;

        /// <summary>The gain that brings a clip measured at <paramref name="loudnessLufs"/> to <see cref="ReferenceLufs"/>.</summary>
        public static float GainFor(float loudnessLufs)
        {
            return Mathf.Pow(10f, (ReferenceLufs - loudnessLufs) / 20f);
        }

        /// <summary>The mix level that plays a role at <paramref name="playbackLufs"/>: 10^((playback - reference) / 20).</summary>
        public static float MixFor(float playbackLufs)
        {
            return Mathf.Pow(10f, (playbackLufs - ReferenceLufs) / 20f);
        }

        /// <summary>True when the entry exists and has a clip.</summary>
        public static bool Has(Entry entry)
        {
            return entry != null && entry.clip != null;
        }

        /// <summary>True when every entry of the array has a clip (and there is at least one).</summary>
        public static bool HasAll(Entry[] entries)
        {
            if (entries == null || entries.Length == 0)
            {
                return false;
            }
            foreach (Entry e in entries)
            {
                if (!Has(e))
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>Every sound effect role slot with a readable name ("hops[0]", "roomTone"...), for the builder and the tests.</summary>
        public IEnumerable<KeyValuePair<string, Entry>> Roles()
        {
            foreach (KeyValuePair<string, Entry> pair in Slots("hops", hops))
            {
                yield return pair;
            }
            foreach (KeyValuePair<string, Entry> pair in Slots("softHops", softHops))
            {
                yield return pair;
            }
            foreach (KeyValuePair<string, Entry> pair in Slots("scrapes", scrapes))
            {
                yield return pair;
            }
            yield return new KeyValuePair<string, Entry>("creakLong", creakLong);
            yield return new KeyValuePair<string, Entry>("creakShort", creakShort);
            foreach (KeyValuePair<string, Entry> pair in Slots("footsteps", footsteps))
            {
                yield return pair;
            }
            yield return new KeyValuePair<string, Entry>("roomTone", roomTone);
            yield return new KeyValuePair<string, Entry>("clockLoop", clockLoop);
            yield return new KeyValuePair<string, Entry>("thump", thump);
            yield return new KeyValuePair<string, Entry>("stingCaught", stingCaught);
            yield return new KeyValuePair<string, Entry>("stingCaughtLong", stingCaughtLong);
            yield return new KeyValuePair<string, Entry>("vocalHuh", vocalHuh);
            yield return new KeyValuePair<string, Entry>("uiClick", uiClick);
            yield return new KeyValuePair<string, Entry>("uiHover", uiHover);
            yield return new KeyValuePair<string, Entry>("stingWin", stingWin);
            yield return new KeyValuePair<string, Entry>("doorOpen", doorOpen);
            yield return new KeyValuePair<string, Entry>("wardrobeOpen", wardrobeOpen);
            yield return new KeyValuePair<string, Entry>("wardrobeClose", wardrobeClose);
            yield return new KeyValuePair<string, Entry>("crash", crash);
            yield return new KeyValuePair<string, Entry>("topple", topple);
            yield return new KeyValuePair<string, Entry>("lampClick", lampClick);
        }

        /// <summary>The music slots ("musicTitle", "musicLevel"), apart from <see cref="Roles"/>: stereo and streamed.</summary>
        public IEnumerable<KeyValuePair<string, Entry>> MusicRoles()
        {
            yield return new KeyValuePair<string, Entry>("musicTitle", musicTitle);
            yield return new KeyValuePair<string, Entry>("musicLevel", musicLevel);
        }

        /// <summary>Number of sound effect role slots that hold a clip.</summary>
        public int ClipCount
        {
            get
            {
                int n = 0;
                foreach (KeyValuePair<string, Entry> pair in Roles())
                {
                    if (Has(pair.Value))
                    {
                        n++;
                    }
                }
                return n;
            }
        }

        private static IEnumerable<KeyValuePair<string, Entry>> Slots(string name, Entry[] entries)
        {
            if (entries == null)
            {
                yield break;
            }
            for (int i = 0; i < entries.Length; i++)
            {
                yield return new KeyValuePair<string, Entry>(name + "[" + i + "]", entries[i]);
            }
        }

        private static AudioLibrary loaded;

        /// <summary>The library in Resources, or null when it does not exist yet (every sound is then synthesized).</summary>
        public static AudioLibrary Load()
        {
            if (loaded == null)
            {
                loaded = Resources.Load<AudioLibrary>(ResourcePath);
            }
            return loaded;
        }
    }
}
