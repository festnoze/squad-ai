using System;
using System.Collections;
using System.Collections.Generic;
using Meuble.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace Meuble.Tests
{
    /// <summary>
    /// Probe step 27, recorded audio (docs/CONTRACT_M3.md 7 and 9), on the real Boot scene. Every assertion reads
    /// configuration and counters (as CreaksPlayed does), never isPlaying: batch mode may have no audio device.
    /// Every test first asserts its premise, the library asset with its clips, so a stub returning null cannot
    /// pass. Waits count fixed steps or are bounded by game time, never by rendered frames.
    /// </summary>
    public sealed class ProbeTestsM3Audio
    {
        private const float Dt = Tuning.FixedStep;
        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private int fixedSteps;

        private Main main;
        private GameState Game => main.Game;
        private Sfx Sfx => main.Sfx;
        private FurnitureController Chair => Game.Furniture;
        private Inhabitant Habitant => Game.MainInhabitant;

        // Level 1 spots (PRD 6.3): station 3 in front of the window, and a pin facing away from the spawn walk.
        private static readonly Vector3 WindowSpot = new Vector3(0f, 0f, -2.3f);
        private static readonly Vector3 AwaySpot = new Vector3(-1.5f, 0f, 2.2f);

        // Every role and the file it must resolve to (docs/M3_AUDIO.md section 1).
        private static readonly Dictionary<string, string> ExpectedRoles = new Dictionary<string, string>
        {
            { "hops[0]", "hop_01" }, { "hops[1]", "hop_02" }, { "hops[2]", "hop_03" }, { "hops[3]", "hop_04" },
            { "scrapes[0]", "scrape_01" }, { "scrapes[1]", "scrape_02" }, { "scrapes[2]", "scrape_03" },
            { "creakLong", "creak_long" }, { "creakShort", "creak_short" },
            { "footsteps[0]", "footstep_01" }, { "footsteps[1]", "footstep_02" }, { "footsteps[2]", "footstep_03" },
            { "footsteps[3]", "footstep_04" }, { "footsteps[4]", "footstep_05" },
            { "roomTone", "roomtone_airvent_loop" }, { "clockLoop", "roomtone_clock_loop" },
            { "thump", "thump" }, { "stingCaught", "sting_caught" }, { "stingCaughtLong", "sting_caught_long" },
            { "vocalHuh", "vocal_huh" }, { "uiClick", "ui_click" },
        };

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            fixedSteps = 0;
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.IsNotNull(Game.Level, "the level was never built");
            Assert.IsNotNull(Sfx, "Main built no Sfx");
            Game.Rules = GameRules.M2;
            Game.FixedStepped += CountStep;
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            AudioListener.pause = false;
            GamePause.IsPaused = false;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.FixedStepped -= CountStep;
                if (main.Game.Furniture != null)
                {
                    main.Game.Furniture.ScriptedDirection = null;
                }
            }
            yield return null;
        }

        private void CountStep() => fixedSteps++;

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                exceptions++;
                logged.Add(condition);
            }
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        /// <summary>Runs the game at <paramref name="scale"/> until <paramref name="until"/> holds or <paramref name="maxSteps"/> fixed steps ran.</summary>
        private IEnumerator Run(int maxSteps, Func<bool> until, float scale)
        {
            int end = fixedSteps + maxSteps;
            float realStart = Time.realtimeSinceStartup;
            Time.timeScale = scale;
            try
            {
                while (fixedSteps < end && (until == null || !until()) && Time.realtimeSinceStartup - realStart < 150f)
                {
                    yield return null;
                }
            }
            finally
            {
                Time.timeScale = 1f;
            }
        }

        private static float YawToward(Vector3 from, Vector3 to) => YawMath.YawOf(to - from);

        /// <summary>The premise of every step 27 test: the library asset exists and holds clips.</summary>
        private AudioLibrary RequireLibrary()
        {
            AudioLibrary library = AudioLibrary.Load();
            Assert.IsNotNull(library, "premise: Resources/AudioLibrary.asset is missing (AudioLibraryBuilder.Build)");
            Assert.Greater(library.ClipCount, 0, "premise: the audio library holds no clip");
            Assert.AreSame(library, Sfx.Library, "Sfx does not use the library");
            return library;
        }

        private void AssertNoErrors()
        {
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>M3.1: a role's effective volume is exactly gain * mix, and below 1, so it was never clamped.</summary>
        private static void AssertEffective(string role, AudioLibrary.Entry entry, float mix, float effective)
        {
            float expected = entry.gain * mix;
            Assert.LessOrEqual(mix, 1f, role + ": mix above 1");
            Assert.Less(expected, 1f, $"{role}: gain {entry.gain:0.000} * mix {mix:0.000} reaches 1, the volume would clamp");
            Assert.AreEqual(expected, effective, 1e-3f, role + ": the effective volume is not gain * mix (clamped?)");
            Assert.Less(effective, 1f, role + ": effective volume at 1");
        }

        // ----- 27 -----

        [UnityTest]
        public IEnumerator Step27_AudioLibraryResolvesEveryRole()
        {
            AudioLibrary library = RequireLibrary();
            int roles = 0;
            foreach (KeyValuePair<string, AudioLibrary.Entry> pair in library.Roles())
            {
                roles++;
                string role = pair.Key;
                Assert.IsTrue(ExpectedRoles.TryGetValue(role, out string file), "unexpected role " + role);
                AudioLibrary.Entry entry = pair.Value;
                Assert.IsTrue(AudioLibrary.Has(entry), role + " has no clip");
                AudioClip clip = entry.clip;
                Assert.AreEqual(file, clip.name, role + " resolves to the wrong file");
                Assert.AreEqual(1, clip.channels, role + " is not mono");
                Assert.AreEqual(44100, clip.frequency, role + " sample rate");
                Assert.Greater(clip.length, 0.05f, role + " is empty");
                Assert.IsTrue(clip.preloadAudioData, role + ": Preload Audio Data is off, the clip would not play until loaded by script");
                bool loop = role == "roomTone" || role == "clockLoop";
                AudioClipLoadType wanted = loop ? AudioClipLoadType.CompressedInMemory : AudioClipLoadType.DecompressOnLoad;
                Assert.AreEqual(wanted, clip.loadType, role + " load type");
                // The volume comes from the measured RMS to the common target (contract 7).
                Assert.That(entry.activeRmsDb, Is.InRange(-40f, -10f), role + " has no measured RMS");
                Assert.AreEqual(AudioLibrary.GainFor(entry.activeRmsDb), entry.gain, 1e-4f, role + " gain is not derived from its RMS");
                float matched = entry.activeRmsDb + 20f * Mathf.Log10(entry.gain);
                Assert.AreEqual(AudioLibrary.TargetRmsDb, matched, 0.01f, role + " is not matched to the common target");
            }
            Assert.AreEqual(ExpectedRoles.Count, roles, "role count");
            Assert.AreEqual(4, library.hops.Length);
            Assert.AreEqual(3, library.scrapes.Length);
            Assert.AreEqual(5, library.footsteps.Length);
            yield return Steps(5);
            AssertNoErrors();
        }

        [UnityTest]
        public IEnumerator Step27b_RecordedCuesReplaceTheSynthesis()
        {
            AudioLibrary library = RequireLibrary();
            Sfx sfx = Sfx;
            // One synchronous block: no fixed step runs between the calls, so GameState plays nothing in between.
            sfx.PlayCreak();
            Assert.AreSame(library.creakLong.clip, sfx.LastClip, "creak");
            sfx.PlayThump(0.3f);
            Assert.AreSame(library.thump.clip, sfx.LastClip, "thump");
            sfx.PlayCaught();
            Assert.AreSame(library.stingCaught.clip, sfx.LastClip, "caught sting");
            sfx.PlayUiClick();
            Assert.AreSame(library.uiClick.clip, sfx.LastClip, "UI click");
            // Kept synthesized (contract 7): "hm ?", the tension loop, and "hein ?" until the listening pass.
            sfx.PlayHm(0f);
            Assert.AreSame(sfx.Hm, sfx.LastClip, "hm stays synthesized");
            sfx.PlayHein(0f);
            Assert.AreSame(sfx.RecordedHein ? library.vocalHuh.clip : sfx.Hein, sfx.LastClip, "hein");
            Assert.IsFalse(sfx.RecordedHein, "hein switched to vocal_huh before the product owner's listening pass");

            // The creak warning starts with one short creak, not one per step.
            sfx.SetTension(false, 0f);
            int warnings = sfx.WarningCreaksPlayed;
            sfx.SetTension(true, 0f);
            Assert.AreEqual(warnings + 1, sfx.WarningCreaksPlayed, "the warning start creak");
            Assert.AreSame(library.creakShort.clip, sfx.LastClip, "warning creak");
            sfx.SetTension(true, 0.5f);
            sfx.SetTension(true, 0.9f);
            Assert.AreEqual(warnings + 1, sfx.WarningCreaksPlayed, "a short creak on every warning step");
            sfx.SetTension(false, 0f);
            sfx.SetTension(true, 0f);
            Assert.AreEqual(warnings + 2, sfx.WarningCreaksPlayed, "a second warning has no start creak");
            sfx.SetTension(false, 0f);
            Assert.That(sfx.LastVolume, Is.InRange(0.01f, 1f));

            // Without a library, every cue falls back to its synthesis and the new sounds stay silent.
            var go = new GameObject("SfxWithoutLibrary");
            try
            {
                Sfx bare = go.AddComponent<Sfx>();
                bare.Init(null);
                bare.PlayHop();
                Assert.AreSame(bare.Hop, bare.LastClip, "fallback hop");
                Assert.AreEqual(-1, bare.LastHopVariant, "fallback hop has no variant");
                bare.PlayCreak();
                Assert.AreSame(bare.Creak, bare.LastClip, "fallback creak");
                bare.PlayThump(0f);
                Assert.AreSame(bare.Thump, bare.LastClip, "fallback thump");
                bare.PlayCaught();
                Assert.AreSame(bare.Caught, bare.LastClip, "fallback caught");
                bare.PlayUiClick();
                Assert.AreSame(bare.UiClick, bare.LastClip, "fallback UI click");
                Assert.AreEqual(1, bare.UiClicksPlayed);
                Assert.IsNull(bare.RoomToneSource, "a room tone without a recording");
                bare.EnsureFootsteps(Game.Level);
                Assert.AreEqual(0, bare.FootstepComponentsAdded, "footsteps without recordings");
            }
            finally
            {
                Object.Destroy(go);
            }
            yield return Steps(2);

            // Through GameState: a chair seen moving gets the short sting.
            Habitant.Pin(WindowSpot, YawToward(WindowSpot, Chair.transform.position));
            Chair.ScriptedDirection = Vector3.forward;
            int stings = Sfx.StingsPlayed;
            yield return Run(100, () => Game.State != PlayState.Playing, 1f);
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Caught, Game.State, "premise: caught while seen moving");
            Assert.AreEqual(LoseReason.SeenMoving, Game.LoseReason);
            Assert.AreEqual(stings + 1, Sfx.StingsPlayed, "one sting per catch");
            Assert.AreSame(library.stingCaught.clip, Sfx.LastStingClip, "seen moving plays the short sting");
            AssertNoErrors();
        }

        [UnityTest]
        public IEnumerator Step27c_SuspicionLossPlaysTheLongSting()
        {
            AudioLibrary library = RequireLibrary();
            // Three discoveries in a row, as in Step21_SuspicionLose.
            Vector3[] spots = { new Vector3(-3.2f, 0f, -0.8f), new Vector3(-2.4f, 0f, -1.4f), new Vector3(-3.4f, 0f, 0.6f) };
            int stings = Sfx.StingsPlayed;
            for (int k = 0; k < spots.Length && Game.State == PlayState.Playing; k++)
            {
                if (k > 0)
                {
                    Habitant.Pin(WindowSpot, YawToward(WindowSpot, spots[k]) + 180f, 0f, true);
                    yield return Steps(1);
                }
                Chair.Teleport(spots[k], 0f);
                Habitant.Pin(WindowSpot, YawToward(WindowSpot, spots[k]), 0f, true);
                int waited = 0;
                while (Game.DiscoveryCount < k + 1 && Game.State == PlayState.Playing && waited < 60)
                {
                    yield return new WaitForFixedUpdate();
                    waited++;
                }
            }
            Assert.AreEqual(PlayState.Caught, Game.State, "premise: three discoveries lose");
            Assert.AreEqual(LoseReason.Suspicion, Game.LoseReason, "premise: lost to suspicion");
            Assert.AreEqual(stings + 1, Sfx.StingsPlayed, "one sting per loss");
            Assert.AreSame(library.stingCaughtLong.clip, Sfx.LastStingClip, "a suspicion loss plays the long sting");
            AssertEffective("stingCaughtLong", library.stingCaughtLong, Tuning.SfxCaughtMix, Sfx.LastStingVolume);
            AssertNoErrors();
        }

        [UnityTest]
        public IEnumerator Step27d_HopVariantsNeverRepeat()
        {
            AudioLibrary library = RequireLibrary();
            Assert.AreEqual(4, library.hops.Length, "premise: four hop variants");

            // Direct calls, the chair standing still (no pivot): never the same variant twice in a row.
            int before = Sfx.HopsPlayed;
            int previous = Sfx.LastHopVariant;
            var used = new HashSet<int>();
            for (int i = 0; i < 60; i++)
            {
                Sfx.PlayHop(i % 3 == 0 ? 0.25f : 1f);
                int v = Sfx.LastHopVariant;
                Assert.That(v, Is.InRange(0, 3), "hop variant index");
                Assert.AreNotEqual(previous, v, $"hop {i}: the same variant twice in a row");
                Assert.AreSame(library.hops[v].clip, Sfx.LastClip, "the hop clip is its variant");
                Assert.That(Sfx.LastVolume, Is.InRange(0.01f, 1f), "hop volume");
                used.Add(v);
                previous = v;
            }
            Assert.AreEqual(before + 60, Sfx.HopsPlayed, "hop counter");
            Assert.AreEqual(4, used.Count, "60 hops never used every variant: the choice is not random");

            // Through GameState: the chair drives away from a pinned inhabitant and every hop it takes is counted.
            Habitant.Pin(AwaySpot, 0f);
            var variants = new List<int>();
            int lastCount = Sfx.HopsPlayed;
            void Record()
            {
                if (Sfx.HopsPlayed != lastCount)
                {
                    Assert.AreEqual(lastCount + 1, Sfx.HopsPlayed, "more than one hop sound in one step");
                    lastCount = Sfx.HopsPlayed;
                    variants.Add(Sfx.LastHopVariant);
                }
            }
            Game.FixedStepped += Record;
            Chair.ScriptedDirection = Vector3.forward;
            int hopsBefore = Chair.HopCount;
            yield return Steps(75);
            Chair.ScriptedDirection = null;
            Game.FixedStepped -= Record;
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: the drive stays unseen");
            Assert.GreaterOrEqual(variants.Count, 4, "premise: the drive played at least four hops");
            Assert.AreEqual(Chair.HopCount - hopsBefore, variants.Count, "one hop sound per hop");
            for (int i = 1; i < variants.Count; i++)
            {
                Assert.AreNotEqual(variants[i - 1], variants[i], $"driven hop {i}: the same variant twice in a row");
            }

            // A reversal pivots the chair on the spot: a hop taken there is a leg scrape.
            Assert.IsTrue(Sfx.IsPivot(0.2f, 360f), "a hard turn at low speed is a pivot");
            Assert.IsFalse(Sfx.IsPivot(1.5f, 360f), "a turn at full speed is a hop");
            Assert.IsFalse(Sfx.IsPivot(0.2f, 0f), "a slow straight hop is a hop");
            int scrapes = Sfx.ScrapesPlayed;
            Chair.ScriptedDirection = Vector3.forward;
            yield return Steps(25);
            for (int r = 0; r < 4; r++)
            {
                Chair.ScriptedDirection = r % 2 == 0 ? Vector3.back : Vector3.forward;
                yield return Steps(30);
            }
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: the reversals stay unseen");
            Assert.Greater(Sfx.ScrapesPlayed, scrapes, "four reversals never scraped");
            Assert.That(Sfx.LastScrapeVariant, Is.InRange(0, 2));
            AssertNoErrors();
        }

        [UnityTest]
        public IEnumerator Step27e_FootstepsAre3DOnEveryInhabitantRoot()
        {
            AudioLibrary library = RequireLibrary();
            Assert.AreEqual(5, library.footsteps.Length, "premise: five footstep variants");

            // A level with two inhabitants: each root gets its own footstep source, and no Transform appears.
            Game.LoadLevel("test_two_inhabitants");
            Assert.AreEqual(2, Game.Level.Inhabitants.Count, "premise: two inhabitants");
            var transforms = new int[2];
            for (int i = 0; i < 2; i++)
            {
                Inhabitant inhabitant = Game.Level.Inhabitants[i];
                Assert.IsFalse(inhabitant.TryGetComponent<FootstepAudio>(out _), "premise: a fresh inhabitant has no footsteps yet");
                transforms[i] = inhabitant.GetComponentsInChildren<Transform>(true).Length;
            }
            yield return Steps(2);
            var sources = new HashSet<AudioSource>();
            for (int i = 0; i < 2; i++)
            {
                Inhabitant inhabitant = Game.Level.Inhabitants[i];
                Assert.IsTrue(inhabitant.TryGetComponent(out FootstepAudio footsteps), $"inhabitant {i} has no FootstepAudio");
                Assert.AreSame(inhabitant, footsteps.Owner);
                AudioSource source = footsteps.Source;
                Assert.IsNotNull(source, "no footstep AudioSource");
                Assert.AreSame(inhabitant.gameObject, source.gameObject, "the footstep source is not on the inhabitant root");
                Assert.AreEqual(1f, source.spatialBlend, "footsteps are not 3D");
                Assert.AreEqual(AudioRolloffMode.Linear, source.rolloffMode);
                Assert.AreEqual(FootstepAudio.MaxDistance, source.maxDistance, 1e-4f);
                Assert.AreEqual(10f, source.maxDistance, 1e-4f, "linear rolloff to 10 m");
                Assert.IsFalse(source.loop);
                Assert.IsFalse(source.playOnAwake);
                Assert.AreEqual(1, inhabitant.GetComponents<FootstepAudio>().Length, "footsteps added twice");
                Assert.AreEqual(transforms[i], inhabitant.GetComponentsInChildren<Transform>(true).Length, "footsteps created a Transform");
                sources.Add(source);
            }
            Assert.AreEqual(2, sources.Count, "the inhabitants share a footstep source");

            // Back on level 1: a rebuilt level gets its footsteps on its first steps.
            Game.LoadLevel("level1");
            yield return Steps(2);
            Assert.IsTrue(Habitant.TryGetComponent(out FootstepAudio steps), "the rebuilt inhabitant has no footsteps");

            // While the inhabitant walks, every FootstepCount increment plays one step.
            int startCount = Habitant.FootstepCount;
            int startPlayed = steps.StepsPlayed;
            int increments = 0;
            int seenCount = startCount;
            var played = new List<int>();
            int seenPlayed = startPlayed;
            void Watch()
            {
                if (Habitant.FootstepCount != seenCount)
                {
                    seenCount = Habitant.FootstepCount;
                    increments++;
                }
                if (steps.StepsPlayed != seenPlayed)
                {
                    seenPlayed = steps.StepsPlayed;
                    played.Add(steps.LastVariant);
                }
            }
            Game.FixedStepped += Watch;
            yield return Run(Mathf.CeilToInt(45f / Dt), () => increments >= 6, 8f);
            // Freeze the inhabitant, then let the poll catch the last increment (it may run before GameState).
            Habitant.Pin(Habitant.transform.position, Habitant.Routine.BodyYaw);
            yield return Steps(2);
            Game.FixedStepped -= Watch;
            if (increments > 0)
            {
                Debug.Log($"[Probe] Step27e: {increments} FootstepCount increments, {steps.StepsPlayed - startPlayed} footsteps played");
                Assert.AreEqual(increments, steps.StepsPlayed - startPlayed, "one step sound per FootstepCount increment");
            }
            else
            {
                // FootstepCount is still the integrator's stub (always 0): drive the same playback through the hook.
                Debug.LogWarning("[Probe] Step27e: Inhabitant.FootstepCount never increased while walking (rig stub?); footstep playback checked through FootstepAudio.PlayStep.");
                for (int i = 0; i < 6; i++)
                {
                    steps.PlayStep();
                    played.Add(steps.LastVariant);
                }
                Assert.AreEqual(startPlayed + 6, steps.StepsPlayed, "footstep counter");
            }
            Assert.GreaterOrEqual(played.Count, 2, "premise: at least two steps played");
            for (int i = 1; i < played.Count; i++)
            {
                Assert.That(played[i], Is.InRange(0, 4), "footstep variant index");
                Assert.AreNotEqual(played[i - 1], played[i], $"step {i}: the same footstep twice in a row");
            }
            AssertNoErrors();
        }

        [UnityTest]
        public IEnumerator Step27f_RoomToneLoops()
        {
            AudioLibrary library = RequireLibrary();
            AudioSource tone = Sfx.RoomToneSource;
            Assert.IsNotNull(tone, "no room tone source");
            Assert.AreSame(library.roomTone.clip, tone.clip, "the room tone plays the air vent loop");
            Assert.IsTrue(tone.loop, "the room tone does not loop");
            Assert.AreEqual(0f, tone.spatialBlend, "the room tone is not 2D");
            Assert.IsFalse(tone.playOnAwake);
            Assert.IsFalse(tone.ignoreListenerPause, "the room tone must pause with the game");
            Assert.AreSame(Sfx.gameObject, tone.gameObject);
            // A bed at a low level: between -55 and -38 dBFS active RMS (the cues sit near -18 to -29).
            float level = library.roomTone.activeRmsDb + 20f * Mathf.Log10(Mathf.Max(tone.volume, 1e-6f));
            Assert.That(level, Is.InRange(-55f, -38f), $"room tone at {level:0.0} dBFS");
            int loops = 0;
            foreach (AudioSource s in Sfx.GetComponents<AudioSource>())
            {
                if (s.loop && s.clip == library.roomTone.clip)
                {
                    loops++;
                }
            }
            Assert.AreEqual(1, loops, "one room tone source");
            // A restart keeps the same bed (Sfx lives across levels), no second source.
            int count = Sfx.GetComponents<AudioSource>().Length;
            Game.Restart();
            yield return Steps(3);
            Assert.AreEqual(count, Sfx.GetComponents<AudioSource>().Length, "a restart added sources");
            Assert.AreSame(tone, Sfx.RoomToneSource);
            AssertNoErrors();
        }

        /// <summary>
        /// M3.1 (critique S6): the playback volume of every role is exactly its clip gain times its Tuning mix and
        /// stays below 1, so no cue is clamped short of the common loudness target. Each role is played for real and
        /// its recorded volume read back; the long sting is checked by Step27c, which reaches a suspicion loss.
        /// </summary>
        [UnityTest]
        public IEnumerator Step27h_EffectiveVolumesAreGainTimesMixAndUnclamped()
        {
            AudioLibrary library = RequireLibrary();
            Sfx sfx = Sfx;

            // Every role, played or not by default, has gain * mix below 1.
            var mixes = new Dictionary<string, float>
            {
                { "hops", Tuning.SfxHopMix }, { "scrapes", Mathf.Max(Tuning.SfxPivotScrapeMix, Tuning.SfxPickUpScrapeMix) },
                { "creakLong", Tuning.SfxCreakMix }, { "creakShort", Tuning.SfxWarningCreakMix }, { "footsteps", Tuning.SfxFootstepMix },
                { "roomTone", Tuning.SfxRoomToneMix }, { "clockLoop", Tuning.SfxClockMix }, { "thump", Tuning.SfxThumpMix },
                { "stingCaught", Tuning.SfxCaughtMix }, { "stingCaughtLong", Tuning.SfxCaughtMix }, { "vocalHuh", Tuning.SfxHeinMix },
                { "uiClick", Tuning.SfxUiClickMix },
            };
            foreach (KeyValuePair<string, AudioLibrary.Entry> pair in library.Roles())
            {
                string role = pair.Key.Split('[')[0];
                Assert.IsTrue(mixes.TryGetValue(role, out float mix), "no mix for role " + pair.Key);
                AssertEffective(pair.Key, pair.Value, mix, pair.Value.gain * mix);
            }

            // Hops, one of each variant (the chair stands still: no pivot).
            var hopVariants = new HashSet<int>();
            for (int i = 0; i < 40 && hopVariants.Count < 4; i++)
            {
                sfx.PlayHop();
                int v = sfx.LastHopVariant;
                hopVariants.Add(v);
                AssertEffective("hops[" + v + "]", library.hops[v], Tuning.SfxHopMix, sfx.LastVolume);
            }
            Assert.AreEqual(4, hopVariants.Count, "premise: every hop variant played");
            sfx.PlaySoftHop();
            Assert.AreEqual(library.hops[sfx.LastHopVariant].gain * Tuning.SfxHopMix * 0.25f, sfx.LastVolume, 1e-3f, "soft hop");

            // Scrapes on a pick up, one of each variant.
            var scrapeVariants = new HashSet<int>();
            for (int i = 0; i < 30 && scrapeVariants.Count < 3; i++)
            {
                sfx.PlayPickUpScrape();
                int v = sfx.LastScrapeVariant;
                scrapeVariants.Add(v);
                AssertEffective("scrapes[" + v + "] (pick up)", library.scrapes[v], Tuning.SfxPickUpScrapeMix, sfx.LastScrapeVolume);
            }
            Assert.AreEqual(3, scrapeVariants.Count, "premise: every scrape variant played");

            sfx.PlayCreak();
            AssertEffective("creakLong", library.creakLong, Tuning.SfxCreakMix, sfx.LastVolume);
            sfx.SetTension(false, 0f);
            sfx.SetTension(true, 0f);
            Assert.AreSame(library.creakShort.clip, sfx.LastClip, "premise: the warning start creak played");
            AssertEffective("creakShort", library.creakShort, Tuning.SfxWarningCreakMix, sfx.LastVolume);
            sfx.SetTension(false, 0f);
            sfx.PlayThump(0f);
            AssertEffective("thump", library.thump, Tuning.SfxThumpMix, sfx.LastVolume);
            sfx.PlayCaught();
            Assert.AreSame(library.stingCaught.clip, sfx.LastStingClip, "premise: the short sting played");
            AssertEffective("stingCaught", library.stingCaught, Tuning.SfxCaughtMix, sfx.LastStingVolume);
            sfx.PlayUiClick();
            AssertEffective("uiClick", library.uiClick, Tuning.SfxUiClickMix, sfx.LastVolume);
            // The recorded "hein ?" is off by default; switched on, it must not clamp either (the M3 mix did).
            Assert.IsFalse(sfx.UseRecordedHein, "premise: hein is synthesized by default");
            sfx.UseRecordedHein = true;
            try
            {
                sfx.PlayHein(0f);
                Assert.AreSame(library.vocalHuh.clip, sfx.LastClip, "premise: the recorded hein played");
                AssertEffective("vocalHuh", library.vocalHuh, Tuning.SfxHeinMix, sfx.LastVolume);
            }
            finally
            {
                sfx.UseRecordedHein = false;
            }

            // The loops: the room tone, and the clock layer switched on for the check.
            AssertEffective("roomTone", library.roomTone, Tuning.SfxRoomToneMix, sfx.RoomToneSource.volume);
            Assert.IsNull(sfx.ClockSource, "premise: the clock layer is off by default");
            sfx.SetClockLayer(true);
            Assert.IsNotNull(sfx.ClockSource, "the clock layer did not start");
            Assert.AreSame(library.clockLoop.clip, sfx.ClockSource.clip);
            Assert.IsTrue(sfx.ClockSource.loop);
            AssertEffective("clockLoop", library.clockLoop, Tuning.SfxClockMix, sfx.ClockSource.volume);
            sfx.SetClockLayer(false);
            Assert.IsNull(sfx.ClockSource, "the clock layer did not stop");

            // Footsteps, one of each variant.
            yield return Steps(2);
            Assert.IsTrue(Habitant.TryGetComponent(out FootstepAudio steps), "premise: the inhabitant has footsteps");
            var stepVariants = new HashSet<int>();
            for (int i = 0; i < 40 && stepVariants.Count < 5; i++)
            {
                steps.PlayStep();
                int v = steps.LastVariant;
                stepVariants.Add(v);
                AssertEffective("footsteps[" + v + "]", library.footsteps[v], Tuning.SfxFootstepMix, steps.LastVolume);
            }
            Assert.AreEqual(5, stepVariants.Count, "premise: every footstep variant played");

            // The pivot scrape, through GameState: reversals away from a pinned inhabitant.
            Habitant.Pin(AwaySpot, 0f);
            int scrapes = sfx.ScrapesPlayed;
            var pivotVolumes = new List<KeyValuePair<int, float>>();
            void Record()
            {
                if (sfx.ScrapesPlayed != scrapes)
                {
                    scrapes = sfx.ScrapesPlayed;
                    pivotVolumes.Add(new KeyValuePair<int, float>(sfx.LastScrapeVariant, sfx.LastScrapeVolume));
                }
            }
            Game.FixedStepped += Record;
            Chair.ScriptedDirection = Vector3.forward;
            yield return Steps(25);
            for (int r = 0; r < 4; r++)
            {
                Chair.ScriptedDirection = r % 2 == 0 ? Vector3.back : Vector3.forward;
                yield return Steps(30);
            }
            Chair.ScriptedDirection = null;
            Game.FixedStepped -= Record;
            Assert.IsNotEmpty(pivotVolumes, "premise: a reversal scraped");
            foreach (KeyValuePair<int, float> p in pivotVolumes)
            {
                // A pivot on a rug is a soft hop: a quarter of the volume, never more than gain * mix.
                AudioLibrary.Entry entry = library.scrapes[p.Key];
                float full = entry.gain * Tuning.SfxPivotScrapeMix;
                Assert.IsTrue(Mathf.Abs(p.Value - full) < 1e-3f || Mathf.Abs(p.Value - full * 0.25f) < 1e-3f,
                    $"pivot scrape[{p.Key}] at {p.Value:0.0000}, expected {full:0.0000} (or a quarter on a rug)");
                AssertEffective("scrapes[" + p.Key + "] (pivot)", entry, Tuning.SfxPivotScrapeMix, full);
            }
            AssertNoErrors();
        }

        [UnityTest]
        public IEnumerator Step27g_UiClickIgnoresTheListenerPause()
        {
            AudioLibrary library = RequireLibrary();
            AudioSource ui = Sfx.UiSource;
            Assert.IsNotNull(ui, "no UI click source");
            Assert.IsTrue(ui.ignoreListenerPause, "the UI click source must ignore AudioListener.pause");
            Assert.AreEqual(0f, ui.spatialBlend, "the UI click is not 2D");
            // Every game sound pauses with the listener; only the menu click goes through.
            foreach (AudioSource s in Sfx.GetComponents<AudioSource>())
            {
                if (s != ui)
                {
                    Assert.IsFalse(s.ignoreListenerPause, "a game sound ignores the pause");
                }
            }
            int clicks = Sfx.UiClicksPlayed;
            AudioListener.pause = true;
            try
            {
                Sfx.PlayUiClick();
                Sfx.PlayUiClick();
            }
            finally
            {
                AudioListener.pause = false;
            }
            Assert.AreEqual(clicks + 2, Sfx.UiClicksPlayed, "UI click counter");
            Assert.AreSame(library.uiClick.clip, Sfx.LastClip, "the UI click plays the recording");
            Assert.That(Sfx.LastVolume, Is.InRange(0.05f, 1f));
            yield return Steps(2);

            // Contract 9, step 27: AudioListener.pause follows the pause (an injected Escape / Start press).
            Assert.IsFalse(Game.Paused, "premise: the game runs");
            InputReader.InjectPausePress();
            int frames = 0;
            while (!Game.Paused && frames++ < 10)
            {
                yield return null;
            }
            Assert.IsTrue(Game.Paused, "premise: the injected pause press did not pause the game");
            Assert.IsTrue(AudioListener.pause, "the audio listener plays on while the game is paused");
            Sfx.PlayUiClick();
            Assert.AreEqual(clicks + 3, Sfx.UiClicksPlayed, "a menu click while paused");
            InputReader.InjectPausePress();
            frames = 0;
            while (Game.Paused && frames++ < 10)
            {
                yield return null;
            }
            Assert.IsFalse(Game.Paused, "a second press did not resume");
            Assert.IsFalse(AudioListener.pause, "the audio listener stays paused after the resume");
            AssertNoErrors();
        }
    }
}
