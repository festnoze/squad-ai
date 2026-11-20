using System;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// The product owner's request: no sound while tests run. Muted in batch mode (every tools/unity.sh run, so the
    /// EditMode and PlayMode suites), in the player's probe (--probe, --look), with the "-mute" argument
    /// (OutOfSight.exe -mute) or the OUTOFSIGHT_MUTE=1 environment variable. Muting only sets AudioListener.volume to 0: every
    /// AudioSource still plays, so the tests that count sounds stay meaningful.
    /// </summary>
    public static class AudioMute
    {
        private static bool? muted;

        public static bool Muted
        {
            get
            {
                if (muted == null)
                {
                    string[] args = Environment.GetCommandLineArgs();
                    muted = Application.isBatchMode
                        || Array.IndexOf(args, "--probe") >= 0
                        || Array.IndexOf(args, "--look") >= 0
                        || Array.IndexOf(args, "-mute") >= 0
                        || Environment.GetEnvironmentVariable("OUTOFSIGHT_MUTE") == "1";
                }
                return muted.Value;
            }
        }

        /// <summary>The listener volume for an options volume: 0 while muted.</summary>
        public static float Apply(float volume)
        {
            return Muted ? 0f : volume;
        }
    }
}
