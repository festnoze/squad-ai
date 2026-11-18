using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// The footsteps of one inhabitant (docs/CONTRACT_M3.md 7). Added by <see cref="Sfx"/> with AddComponent on the
    /// inhabitant root, together with its 3D AudioSource, so no GameObject or Transform is created and the object
    /// count of probe step 09 holds. It plays a recorded step variant, never the same twice in a row, on every
    /// increment of <see cref="Inhabitant.FootstepCount"/> (counted by the rig from the fixed step walk phase).
    /// Tests read <see cref="StepsPlayed"/> and <see cref="LastVariant"/>, never isPlaying: batch mode may have no
    /// audio device.
    ///
    /// M5 (docs/CONTRACT_M5_v3.md 15.9): the dog patters. Its steps are <see cref="DogPatter"/>, synthesized once at run
    /// time (no recording, no file): two light paw ticks <see cref="Tuning.DogPatterGap"/> apart (a hind paw, then a front
    /// one), on each of its foot contacts, softer than a human's step (<see cref="Tuning.DogPatterGain"/>).
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

        /// <summary>M5: the clip of the last step (null before the first).</summary>
        public AudioClip LastClip { get; private set; }

        /// <summary>M5: true when the owner is the dog: its steps are the synthesized <see cref="DogPatter"/>.</summary>
        public bool IsPatter { get; private set; }

        private AudioLibrary.Entry[] clips;
        private float mix;
        private int lastCount;
        private System.Random random;

        public void Init(Inhabitant owner, AudioLibrary.Entry[] footsteps, float mixLevel, int seed)
        {
            Owner = owner;
            // M5: the dog patters instead of walking in shoes.
            IsPatter = owner != null && owner.IsDog;
            clips = IsPatter ? DogPatter : footsteps;
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
            LastClip = entry.clip;
            Source.PlayOneShot(entry.clip, LastVolume);
            StepsPlayed++;
        }

        // ----- M5: the dog's patter -----

        public const string PatterClipPrefix = "DogPatter";
        private const int PatterRate = 44100;
        private static AudioLibrary.Entry[] dogPatter;

        /// <summary>
        /// The dog's step variants (<see cref="Tuning.DogPatterVariants"/>), made once per run: each is two short ticks of
        /// high passed noise with a fast decay (a claw on a hard floor), the second one a little softer and lower, at
        /// <see cref="Tuning.DogPatterGap"/>. Deterministic (a fixed seed per variant).
        /// </summary>
        public static AudioLibrary.Entry[] DogPatter
        {
            get
            {
                if (dogPatter != null && AudioLibrary.HasAll(dogPatter))
                {
                    return dogPatter;
                }
                var entries = new AudioLibrary.Entry[Mathf.Max(1, Tuning.DogPatterVariants)];
                for (int v = 0; v < entries.Length; v++)
                {
                    entries[v] = new AudioLibrary.Entry { clip = SynthesizePatter(v), loudness = AudioLibrary.ReferenceLufs, gain = Tuning.DogPatterGain };
                }
                dogPatter = entries;
                return dogPatter;
            }
        }

        private static AudioClip SynthesizePatter(int variant)
        {
            float gap = Tuning.DogPatterGap * (1f + 0.12f * (variant - 1));
            int length = Mathf.CeilToInt((gap + 0.06f) * PatterRate);
            var data = new float[length];
            var random = new System.Random(4211 + 97 * variant);
            Tick(data, 0, 0.55f, 0.010f, 0.86f + 0.03f * variant, random);
            Tick(data, Mathf.RoundToInt(gap * PatterRate), 0.42f, 0.012f, 0.80f + 0.03f * variant, random);
            AudioClip clip = AudioClip.Create(PatterClipPrefix + variant, length, 1, PatterRate, false);
            clip.SetData(data, 0);
            clip.hideFlags = HideFlags.DontUnloadUnusedAsset;
            return clip;
        }

        /// <summary>One tick: white noise through a one pole high pass of coefficient <paramref name="highPass"/>, decaying over <paramref name="decay"/> s.</summary>
        private static void Tick(float[] data, int start, float amplitude, float decay, float highPass, System.Random random)
        {
            float previousIn = 0f;
            float previousOut = 0f;
            int samples = Mathf.Min(data.Length - start, Mathf.CeilToInt(decay * 6f * PatterRate));
            for (int i = 0; i < samples; i++)
            {
                float noise = (float)(random.NextDouble() * 2.0 - 1.0);
                float filtered = highPass * (previousOut + noise - previousIn);
                previousIn = noise;
                previousOut = filtered;
                float t = i / (float)PatterRate;
                float attack = Mathf.Clamp01(i / (0.0008f * PatterRate));
                data[start + i] += amplitude * attack * Mathf.Exp(-t / decay) * filtered;
            }
        }
    }
}
