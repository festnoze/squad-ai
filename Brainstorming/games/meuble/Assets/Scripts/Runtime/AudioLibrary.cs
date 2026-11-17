using System;
using System.Collections.Generic;
using UnityEngine;

namespace Meuble
{
    /// <summary>
    /// Recorded clips by role (docs/CONTRACT_M3.md 7), at Assets/Resources/AudioLibrary.asset, built by
    /// Meuble.Editor.AudioLibraryBuilder from Assets/ThirdParty/Audio (docs/M3_AUDIO.md). Being referenced
    /// from Resources is what ships the clips in the player.
    ///
    /// Every entry carries the active RMS measured on its file (docs/M3_AUDIO.md section 3) and the gain that
    /// brings it to the common <see cref="TargetRmsDb"/>. Sfx multiplies that gain by its per role mix level,
    /// so a role sounds the same whichever variant plays, and a clip swap only needs a new measurement.
    /// </summary>
    public sealed class AudioLibrary : ScriptableObject
    {
        public const string ResourcePath = "AudioLibrary";

        /// <summary>The common loudness every clip is matched to: active RMS in dBFS (20 ms frames within 30 dB of the loudest).</summary>
        public const float TargetRmsDb = -20f;

        [Serializable]
        public sealed class Entry
        {
            public AudioClip clip;

            /// <summary>Active RMS of the file in dBFS, as measured in docs/M3_AUDIO.md section 3.</summary>
            public float activeRmsDb;

            /// <summary>Linear gain from <see cref="activeRmsDb"/> to <see cref="TargetRmsDb"/> (above 1 for the quiet loops).</summary>
            public float gain = 1f;
        }

        public Entry[] hops = new Entry[0];
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

        /// <summary>The gain that brings a clip measured at <paramref name="activeRmsDb"/> to <see cref="TargetRmsDb"/>.</summary>
        public static float GainFor(float activeRmsDb)
        {
            return Mathf.Pow(10f, (TargetRmsDb - activeRmsDb) / 20f);
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

        /// <summary>Every role slot with a readable name ("hops[0]", "roomTone"...), for the builder and the tests.</summary>
        public IEnumerable<KeyValuePair<string, Entry>> Roles()
        {
            foreach (KeyValuePair<string, Entry> pair in Slots("hops", hops))
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
        }

        /// <summary>Number of role slots that hold a clip.</summary>
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
