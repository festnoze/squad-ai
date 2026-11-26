using System.Collections;
using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Levels v2 (C4, LEVELS_V2 D26): the lit zones on the real Boot scene and the throwaway level test_v2_litzone (one 12 x 4
    /// m living room, the floor lamp, a watcher at x = 5 looking down the room toward -x, and a 1.5 x 1.5 m zone centred at
    /// x = -3, 8 m from the watcher). A switched-off lamp in the zone is seen at the full range (8 m); outside it only within
    /// Tuning.LampOffLight x ViewRange (4 m). The zone's view (ceiling ring, unshadowed spot, floor pool) is visual only, and
    /// its light is never dimmed by the lamp while the room's own lights are.
    /// </summary>
    public sealed class ProbeTestsLitZone
    {
        private const string TestLevel = "test_v2_litzone";

        // The watcher's pinned eye and the three lamp spots, all on the room's axis z = 0.
        private static readonly Vector3 EyeSpot = new Vector3(5f, 0f, 0f);
        private const float EyeYaw = 270f;
        private static readonly Vector3 InZone = new Vector3(-3f, 0f, 0f); // 8 m, the zone's centre
        private static readonly Vector3 OutFar = new Vector3(-1f, 0f, 0f); // 6 m, outside the zone
        private static readonly Vector3 OutNear = new Vector3(2f, 0f, 0f); // 3 m, outside the zone
        // Just past the zone's +x edge (x = -2.25), still 7 m away.
        private static readonly Vector3 PastEdge = new Vector3(-2.15f, 0f, 0f);

        private Main main;
        private GameState Game => main.Game;
        private readonly List<string> errors = new List<string>();

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            RoomLights.Disabled = false;
            errors.Clear();
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.IsNotNull(Game.Level, "the level was never built");
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            RoomLights.Disabled = false;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
            }
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            yield return null;
        }

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                errors.Add(condition);
            }
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private IEnumerator LoadFixture()
        {
            Game.LoadLevel(TestLevel);
            Assert.AreEqual(TestLevel, Game.LevelId);
            yield return Steps(2);
            // No rule runs while the lamp is moved around (nobody catches it, no restart): the vision is stepped by hand.
            Game.Paused = true;
            yield return Steps(1);
        }

        private List<LitZoneView> Views => Game.Level.Root.GetComponentsInChildren<LitZoneView>(true).ToList();

        // ----- a: the rule, a dark lamp in the zone is seen at the full range -----

        [UnityTest]
        public IEnumerator LitZone_a_DarkLampIsSeenAtFullRangeInTheZoneAndShortOutside()
        {
            yield return LoadFixture();
            CollectionAssert.IsEmpty(LevelValidator.Validate(Game.Def), "premise: test_v2_litzone validates");
            Assert.AreEqual(1, Game.Def.LitZones.Count, "premise: one lit zone");
            FurnitureController lamp = Game.Furniture;
            Assert.IsNotNull(lamp.Lamp, "premise: the player is the floor lamp");
            Assert.IsTrue(lamp.Rules != null && lamp.Rules.Lamp, "premise: the lamp rule is on");
            Assert.AreSame(Game.Def.LitZones, lamp.LitZones, "the builder did not hand the zones to the player furniture");
            Inhabitant watcher = Game.MainInhabitant;
            watcher.Pin(EyeSpot, EyeYaw);
            Vision vision = Game.Level.Visions[0];
            float range = watcher.Routine.ViewRange;
            Assert.GreaterOrEqual(range, 8.5f, "premise: the watcher sees past 8 m when the lamp is lit");
            Assert.Less(range * Tuning.LampOffLight, 5.9f, "premise: a dark lamp is not seen at 6 m outside a zone");

            // Lit, in the zone and outside: seen at 8 m and 6 m (the premise of the dark cases below).
            Assert.IsTrue(See(lamp, vision, InZone, out _), "premise: the lit lamp is seen at 8 m");
            Assert.IsTrue(See(lamp, vision, OutFar, out _), "premise: the lit lamp is seen at 6 m");

            lamp.Lamp.SetOn(false);
            Assert.IsFalse(lamp.Lamp.On, "premise: the lamp is off");

            // In the zone: the dark gives no cover.
            Assert.IsTrue(See(lamp, vision, InZone, out float factor), "the dark lamp in the lit zone is not seen at 8 m");
            Assert.AreEqual(1f, factor, 1e-6f, "the range factor in the zone");
            Assert.IsTrue(lamp.InLitZone, "InLitZone at the zone's centre");
            Assert.AreEqual(range, vision.Range, 1e-4f, "the range used in the zone");

            // Outside: the short range only.
            Assert.IsFalse(See(lamp, vision, OutFar, out factor), "the dark lamp outside the zone is seen at 6 m");
            Assert.AreEqual(Tuning.LampOffLight, factor, 1e-6f, "the range factor outside the zone");
            Assert.IsFalse(See(lamp, vision, PastEdge, out factor), "the dark lamp just past the zone's edge is seen at 7 m");
            Assert.AreEqual(Tuning.LampOffLight, factor, 1e-6f, "the range factor just past the zone's edge");
            Assert.IsTrue(See(lamp, vision, OutNear, out factor), "the dark lamp outside the zone is not seen at 3 m");
            Assert.AreEqual(range * Tuning.LampOffLight, vision.Range, 1e-4f, "the short range outside the zone");

            // Switched on again, the zone changes nothing: 1 everywhere.
            lamp.Lamp.SetOn(true);
            Assert.IsTrue(See(lamp, vision, InZone, out factor) && factor == 1f, "the lit lamp in the zone");
            Assert.IsTrue(See(lamp, vision, OutFar, out factor) && factor == 1f, "the lit lamp outside the zone");

            // A level without zones: none handed over, the dark lamp keeps its short range everywhere.
            lamp.LitZones = null;
            lamp.Lamp.SetOn(false);
            Assert.IsFalse(See(lamp, vision, InZone, out factor), "without zones, the dark lamp is seen at 8 m");
            Assert.AreEqual(Tuning.LampOffLight, factor, 1e-6f, "without zones, the range factor");
            lamp.LitZones = Game.Def.LitZones;
            lamp.Lamp.SetOn(true);
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        /// <summary>Teleports the furniture to <paramref name="spot"/> and steps the watcher's vision of it once, by hand.</summary>
        private static bool See(FurnitureController furniture, Vision vision, Vector3 spot, out float factor)
        {
            furniture.Teleport(spot, 0f);
            Physics.SyncTransforms();
            bool sees = vision.Step(furniture);
            factor = vision.RangeFactor;
            return sees;
        }

        // ----- b: the view, and the lamp never dims the zone's light -----

        [UnityTest]
        public IEnumerator LitZone_b_TheZoneLightIsNotDimmedByTheLampAndIsVisualOnly()
        {
            yield return LoadFixture();
            List<LitZoneView> views = Views;
            Assert.AreEqual(1, views.Count, "one view per zone");
            LitZoneView view = views[0];
            LitZoneDef zone = Game.Def.LitZones[0];
            Assert.AreSame(zone, view.Zone);
            Light light = view.Light;
            Assert.IsNotNull(light, "the zone has no light");
            Assert.IsTrue(light.enabled, "premise: Haut (the editor default) keeps the zone light on");
            Assert.AreEqual(LightType.Spot, light.type, "the zone light is a spot");
            Assert.AreEqual(LightShadows.None, light.shadows, "the zone light casts shadows");
            Assert.IsTrue(zone.Contains(light.transform.position), "the zone light does not hang over its zone");
            Assert.Greater(Vector3.Dot(light.transform.forward, Vector3.down), 0.999f, "the zone light does not point down");
            Assert.AreEqual(Game.Def.RoomAt(zone.Position), Game.Def.RoomAt(light.transform.position), "the zone light stands in another room");
            Assert.Less(light.transform.position.y, view.Room.WallHeight, "the zone light stands above the walls");
            Assert.IsTrue(LitZoneView.IsZoneLight(light), "the zone light carries no marker");

            // Visual only: no collider, Default layer, no shadow; the sun stays the one shadowed light.
            Assert.IsEmpty(view.GetComponentsInChildren<Collider>(true), "the zone carries a collider");
            foreach (Transform t in view.GetComponentsInChildren<Transform>(true))
            {
                Assert.AreEqual(0, t.gameObject.layer, $"{t.name} is on layer {LayerMask.LayerToName(t.gameObject.layer)}");
            }
            Renderer[] renderers = view.GetComponentsInChildren<Renderer>(true);
            Assert.AreEqual(2, renderers.Length, "a zone draws as two renderers (ring and pool)");
            foreach (Renderer r in renderers)
            {
                Assert.AreEqual(ShadowCastingMode.Off, r.shadowCastingMode, $"{r.name} casts a shadow");
            }
            Assert.IsNotNull(view.Fixture, "no ceiling fixture");
            Assert.IsNotNull(view.Pool, "no floor pool");
            Assert.AreSame(PrimitiveKit.Emissive(new Color(1f, 0.8f, 0.46f), 1.9f), view.Fixture.sharedMaterial, "the ring is not the lamp glow's material");
            Bounds pool = view.Pool.bounds;
            Assert.IsTrue(pool.size.x > zone.SizeX && pool.size.z > zone.SizeZ, "the pool does not cover its zone");
            Assert.AreEqual(Game.Def.Floor.HeightAt(zone.Position), pool.center.y, 0.05f, "the pool is not on the floor");
            CollectionAssert.IsEmpty(main.LookProblems(), "the look's checks (one shadowed light, the sun)");

            // The lamp, in the same room, switched off: the room's lights dim, the zone's does not.
            FurnitureController lamp = Game.Furniture;
            Assert.AreEqual(view.Room, Game.Def.RoomAt(lamp.transform.position), "premise: the lamp stands in the zone's room");
            RoomLights roomLights = Game.Level.Root.GetComponentInChildren<RoomLights>(true);
            List<RoomLights.Fixture> inRoom = roomLights != null
                ? roomLights.Fixtures.Where(f => f.Room == view.Room && f.Light != null && f.Light.enabled).ToList()
                : new List<RoomLights.Fixture>();
            Assert.IsNotEmpty(inRoom, "premise: the living room has a secondary light the lamp dims");
            Assert.AreEqual(view.Intensity, light.intensity, 1e-6f, "premise: the zone light at its own intensity");

            lamp.Lamp.SetOn(false);
            Assert.IsTrue(lamp.Lamp.Dimming, "premise: the dark lamp dims its room");
            foreach (RoomLights.Fixture f in inRoom)
            {
                Assert.AreEqual(f.Intensity * Tuning.LampOffLight, f.Light.intensity, 1e-5f, $"premise: {f.Light.name} was dimmed with the lamp");
            }
            Assert.AreEqual(view.Intensity, light.intensity, 1e-6f, "the lamp dimmed the zone light");
            Assert.IsTrue(light.enabled, "the lamp switched the zone light off");
            // Carried into the zone while off (LampLight re-dims the room it stands in): still not dimmed.
            lamp.Teleport(InZone, 0f);
            Physics.SyncTransforms();
            yield return null;
            Assert.AreEqual(view.Intensity, light.intensity, 1e-6f, "the lamp dimmed the zone light from inside the zone");
            lamp.Lamp.SetOn(true);
            Assert.AreEqual(view.Intensity, light.intensity, 1e-6f, "the zone light was not left at its own intensity");
            foreach (RoomLights.Fixture f in inRoom)
            {
                Assert.AreEqual(f.Intensity, f.Light.intensity, 1e-6f, $"{f.Light.name} was not restored exactly");
            }
            CollectionAssert.IsEmpty(errors, "no error logged");
        }

        // ----- c: quality tiers, restarts, and a level without zones -----

        [UnityTest]
        public IEnumerator LitZone_c_TiersRestartsAndLevelsWithoutZones()
        {
            yield return LoadFixture();
            QualityTier.Apply(new SaveOptions { Quality = SaveOptions.QualityLow });
            yield return null;
            yield return null;
            Assert.IsFalse(Views[0].Light.enabled, "Bas keeps the zone light on");
            Assert.IsTrue(Views[0].Fixture.enabled && Views[0].Pool.enabled, "Bas hides the ring or the pool");
            QualityTier.Apply(new SaveOptions { Quality = SaveOptions.QualityHigh });
            yield return null;
            yield return null;
            Assert.IsTrue(Views[0].Light.enabled, "Haut switches the zone light off");

            Game.Paused = false;
            Game.Restart();
            yield return Steps(2);
            Assert.AreEqual(1, Views.Count, "a restart rebuilds exactly one zone");
            Assert.AreSame(Game.Def.LitZones, Game.Furniture.LitZones, "a restart lost the zones of the player furniture");

            Game.LoadLevel("level1");
            yield return Steps(2);
            Assert.IsEmpty(Views, "a level without zones has a lit zone view");
            Assert.IsNull(Game.Level.Root.transform.Find(LitZoneView.RootName), "a level without zones has a LitZones root");
            Assert.IsFalse(Game.Furniture.InLitZone, "a level without zones puts the player in one");
            CollectionAssert.IsEmpty(errors, "no error logged");
        }
    }
}
