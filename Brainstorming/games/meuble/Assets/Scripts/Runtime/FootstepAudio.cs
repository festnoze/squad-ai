using Meuble.Core;
using UnityEngine;

namespace Meuble
{
    /// <summary>
    /// The footsteps of one inhabitant (docs/CONTRACT_M3.md 7). Added by <see cref="Sfx"/> with AddComponent on the
    /// inhabitant root, together with its 3D AudioSource, so no GameObject or Transform is created and the object
    /// count of probe step 09 holds. It plays a recorded step variant, never the same twice in a row, on every
    /// increment of <see cref="Inhabitant.FootstepCount"/> (counted by the rig from the fixed step walk phase).
    /// Tests read <see cref="StepsPlayed"/> and <see cref="LastVariant"/>, never isPlaying: batch mode may have no
    /// audio device.
    /// </summary>
    public sealed class FootstepAudio : MonoBehaviour
    {
        /// <summary>Linear rolloff: full volume up to MinDistance, silent from MaxDistance (meters).</summary>
        public const float MinDistance = 1f;
        public const float MaxDistance = 10f;

        // A carried chair makes a heavier, slower gait: its steps are pitched down a little.
        private const float CarryPitch = Tuning.FootstepCarryPitch;
        private const float PitchJitter = Tuning.FootstepPitchJitter;

        public Inhabitant Owner { get; private set; }
        public AudioSource Source { get; private set; }

        /// <summary>Steps played since the component was added.</summary>
        public int StepsPlayed { get; private set; }

        /// <summary>Index in the library's footsteps of the last step played, -1 before the first.</summary>
        public int LastVariant { get; private set; } = -1;

        /// <summary>Volume of the last step: exactly the clip's gain times the footstep mix (never clamped).</summary>
        public float LastVolume { get; private set; }

        private AudioLibrary.Entry[] clips;
        private float mix;
        private int lastCount;
        private System.Random random;

        public void Init(Inhabitant owner, AudioLibrary.Entry[] footsteps, float mixLevel, int seed)
        {
            Owner = owner;
            clips = footsteps;
            mix = mixLevel;
            random = new System.Random(seed);
            lastCount = owner != null ? owner.FootstepCount : 0;
            if (Source == null)
            {
                Source = gameObject.AddComponent<AudioSource>();
            }
            Source.playOnAwake = false;
            Source.loop = false;
            Source.spatialBlend = 1f;
            Source.rolloffMode = AudioRolloffMode.Linear;
            Source.minDistance = MinDistance;
            Source.maxDistance = MaxDistance;
            // The camera orbits fast: no Doppler pitch bend on a step.
            Source.dopplerLevel = 0f;
            Source.spread = 0f;
            Source.volume = 1f;
        }

        private void FixedUpdate()
        {
            if (!GamePause.IsPaused)
            {
                Poll();
            }
        }

        /// <summary>Plays one step when <see cref="Inhabitant.FootstepCount"/> grew since the last poll.</summary>
        public void Poll()
        {
            if (Owner == null)
            {
                return;
            }
            int count = Owner.FootstepCount;
            if (count > lastCount)
            {
                PlayStep();
            }
            lastCount = count;
        }

        /// <summary>One step, a variant other than the last one (the poll, and tests).</summary>
        public void PlayStep()
        {
            if (Source == null || !AudioLibrary.HasAll(clips))
            {
                return;
            }
            int v = Sfx.PickVariant(random, clips.Length, LastVariant);
            LastVariant = v;
            AudioLibrary.Entry entry = clips[v];
            bool carrying = Owner != null && Owner.Routine != null && Owner.Routine.LastActivity == RoutineActivity.Carrying;
            float pitch = 1f + PitchJitter * (2f * (float)random.NextDouble() - 1f);
            Source.pitch = carrying ? pitch * CarryPitch : pitch;
            // M3.1: no level jitter, the gain already matches the variants: the pitch varies, the level does not.
            LastVolume = Sfx.Mix(entry, mix);
            Source.PlayOneShot(entry.clip, LastVolume);
            StepsPlayed++;
        }
    }
}
