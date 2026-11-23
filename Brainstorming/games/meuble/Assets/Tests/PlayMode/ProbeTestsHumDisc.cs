using System.Collections;
using System.Collections.Generic;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Levels v2 C8 (docs/levels_v2/LEVELS_V2.md, wave1 code_features "Robot hum disc and matched audio rolloff"): the robot's
    /// hum disc on level9 is a faint floor ring of radius <see cref="Tuning.RobotHumRadius"/> (the hum's masking rule) that
    /// follows the robot's drawn body and pulses, one renderer and one slot counted in the level budgets; the hum's audio
    /// fades out at about 3.5 m, just past that radius. Every scenario asserts its premise first; waits are bounded.
    /// </summary>
    public sealed class ProbeTestsHumDisc
    {
        private const float Dt = Tuning.FixedStep;
        private const string RobotLevel = "level9";

        private readonly List<string> logged = new List<string>();
        private Main main;
        private GameState Game => main.Game;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            logged.Clear();
            ModelKit.Disabled = false;
            GamePause.IsPaused = false;
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
            GamePause.IsPaused = false;
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            GamePause.IsPaused = false;
            Application.logMessageReceived -= OnLog;
            yield return null;
        }

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
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

        private static float Planar(Vector3 a, Vector3 b) => YawMath.Planar(a - b).magnitude;

        private IEnumerator LoadRobotLevel()
        {
            Game.LoadLevel(RobotLevel);
            Game.Rules = GameRules.M1;
            yield return Steps(2);
            yield return null;
            Assert.AreEqual(RobotLevel, Game.Def.Id, "premise: level9 did not load");
            Assert.AreEqual(1, Game.Robots.Count, "premise: level9 has one robot");
        }

        /// <summary>
        /// The disc is one renderer with one slot under the level root (so the budgets count it), no collider, no shadow, not
        /// an occluder; its band's outer edge is exactly RobotHumRadius from its centre; it stays under the drawn body
        /// (and so within a step's travel of the rule pose) while the robot runs, at the floor plus its small lift.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator HumDisc_a_RadiusIsTheHumRuleAndFollowsTheRobotOnLevel9()
        {
            yield return LoadRobotLevel();
            Robot robot = Game.Robots[0];
            Transform disc = robot.HumDisc;
            Assert.IsNotNull(disc, "the robot has no hum disc");
            Assert.AreEqual(Robot.HumDiscName, disc.name, "the disc's name");
            Assert.AreSame(Game.Level.Root.transform, disc.parent, "the disc is not under the level root (the budgets would miss it)");
            Assert.IsFalse(disc.IsChildOf(robot.transform), "the disc is inside the robot's own hierarchy");

            // One renderer, one slot, drawn; nothing physical.
            MeshRenderer renderer = robot.HumDiscRenderer;
            Assert.IsNotNull(renderer, "the disc has no renderer");
            Assert.AreEqual(1, disc.GetComponentsInChildren<Renderer>(true).Length, "the disc's renderers");
            Assert.AreEqual(1, renderer.sharedMaterials.Length, "the disc's material slots");
            Assert.AreSame(Robot.HumDiscMaterial(), renderer.sharedMaterial, "the disc does not use the shared hum disc material");
            Assert.IsTrue(renderer.enabled && renderer.gameObject.activeInHierarchy, "the disc is not drawn");
            Assert.AreEqual(ShadowCastingMode.Off, renderer.shadowCastingMode, "the disc casts a shadow");
            Assert.IsEmpty(disc.GetComponentsInChildren<Collider>(true), "the disc carries a collider");
            Assert.IsNull(disc.GetComponent<AudioSource>(), "the hum source moved to the disc");
            Assert.AreNotEqual(Layers.Occluder, disc.gameObject.layer, "the disc is an occluder");
            Assert.AreEqual(0, Layers.NavMeshSourceMask & (1 << disc.gameObject.layer), "the disc is on a NavMesh source layer");
            Color? palette = PrimitiveKit.PaletteOf(renderer.sharedMaterial);
            Assert.IsFalse(palette.HasValue && ModelMath.IsRed(palette.Value), "the disc is red (PRD 7.2)");

            // Counted in the level budgets (what the audit's budget line counts), and the level stays within its class.
            Probe.RenderCount count = Probe.CountRenderers(Game.Level.Root.GetComponentsInChildren<Renderer>(false));
            Assert.IsTrue(count.Materials.Contains(renderer.sharedMaterial), "the level's material count misses the disc");
            bool house = Game.Def.AllRooms().Count >= Tuning.HouseBudgetRooms;
            Assert.LessOrEqual(count.MaterialSlots, house ? Tuning.BudgetHouseRenderers : Tuning.BudgetRenderers, "level9: draw calls with the disc");
            Assert.LessOrEqual(count.Materials.Count, house ? Tuning.BudgetHouseMaterials : Tuning.BudgetMaterials, "level9: materials with the disc");

            // The radius, measured on the mesh as drawn (world), from the disc's centre.
            Mesh mesh = disc.GetComponent<MeshFilter>().sharedMesh;
            Assert.IsNotNull(mesh, "the disc has no mesh");
            float outer = 0f;
            float inner = float.MaxValue;
            float flat = 0f;
            foreach (Vector3 v in mesh.vertices)
            {
                Vector3 p = disc.TransformPoint(v);
                float r = Planar(p, disc.position);
                outer = Mathf.Max(outer, r);
                inner = Mathf.Min(inner, r);
                flat = Mathf.Max(flat, Mathf.Abs(p.y - disc.position.y));
            }
            Debug.Log($"[HumDisc_a] level9: disc band {inner:0.000} to {outer:0.000} m, {count.MaterialSlots} draw calls, {count.Materials.Count} materials");
            Assert.That(outer, Is.EqualTo(Tuning.RobotHumRadius).Within(1e-3f), "the disc's radius is not the hum's masking radius");
            Assert.AreEqual(Tuning.RobotHumRadius, robot.HumDiscRadius, 1e-6f, "the disc reports another radius");
            Assert.Greater(inner, 0.5f * Tuning.RobotHumRadius, "the disc is a filled plate, not a faint band toward the edge");
            Assert.Less(flat, 1e-4f, "the disc is not flat");

            // It follows the robot while it runs: under the drawn body every frame, within a step's travel of the rule pose.
            Vector3 start = robot.Position;
            float moved = 0f;
            int checks = 0;
            float realStart = Time.realtimeSinceStartup;
            float speed = robot.Path.Speed;
            Assert.Greater(speed, 0.1f, "premise: level9's robot moves");
            while (moved < 1f && Time.realtimeSinceStartup - realStart < 60f)
            {
                yield return null;
                Assert.Less(Planar(disc.position, robot.Body.position), 1e-4f, $"check {checks}: the disc is not under the drawn body");
                Assert.AreEqual(robot.Body.position.y + 0.014f, disc.position.y, 1e-4f, $"check {checks}: the disc is not on the floor under the robot");
                Assert.LessOrEqual(Planar(disc.position, robot.Position), speed * (2f * Dt + Time.deltaTime) + 1e-3f,
                    $"check {checks}: the disc lags the robot");
                Assert.Less(Quaternion.Angle(Quaternion.identity, disc.rotation), 0.01f, $"check {checks}: the disc turns");
                moved = Planar(robot.Position, start);
                checks++;
            }
            Debug.Log($"[HumDisc_a] the disc followed the robot over {moved:0.00} m in {checks} frames");
            Assert.GreaterOrEqual(moved, 1f, "premise: the robot never travelled a metre (is the world held?)");
            Assert.Greater(checks, 5, "premise: too few frames checked");
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        /// <summary>
        /// The disc's alpha swells and fades once per hum loop through a property block (the shared material untouched),
        /// and holds while the game is paused.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator HumDisc_b_PulsesWithTheHumAndHoldsWhilePaused()
        {
            yield return LoadRobotLevel();
            Robot robot = Game.Robots[0];
            MeshRenderer renderer = robot.HumDiscRenderer;
            Assert.IsNotNull(renderer, "the robot has no hum disc");
            Material shared = renderer.sharedMaterial;
            float sharedAlpha = shared.GetColor("_BaseColor").a;
            var block = new MaterialPropertyBlock();
            float low = float.MaxValue;
            float high = float.MinValue;
            float realStart = Time.realtimeSinceStartup;
            while (Time.realtimeSinceStartup - realStart < 1.5f * Sfx.HumLoopSeconds + 0.5f)
            {
                yield return null;
                float pulse = robot.HumDiscPulse;
                low = Mathf.Min(low, pulse);
                high = Mathf.Max(high, pulse);
                Assert.That(pulse, Is.InRange(Robot.HumDiscPulseMin - 1e-4f, 1f + 1e-4f), "the pulse leaves its range");
                renderer.GetPropertyBlock(block);
                Assert.AreEqual(Robot.HumDiscAlpha * pulse, block.GetColor("_BaseColor").a, 1e-4f, "the drawn alpha is not the pulse's");
            }
            Debug.Log($"[HumDisc_b] pulse {low:0.000} to {high:0.000} over {Time.realtimeSinceStartup - realStart:0.0} s");
            Assert.Greater(high - low, 0.25f * (1f - Robot.HumDiscPulseMin), "the disc does not pulse");
            Assert.AreEqual(sharedAlpha, shared.GetColor("_BaseColor").a, 1e-6f, "the pulse changed the shared material");

            GamePause.IsPaused = true;
            yield return null;
            float held = robot.HumDiscPulse;
            for (int i = 0; i < 10; i++)
            {
                yield return null;
            }
            Assert.AreEqual(held, robot.HumDiscPulse, 1e-6f, "the disc pulses while paused");
            GamePause.IsPaused = false;
            CollectionAssert.IsEmpty(logged, "no error logged");
        }

        /// <summary>
        /// The hum's audio range matches the rule: still heard on the disc's edge, silent from about 3.5 m (it was 7 m), and
        /// the robot's source states that rolloff and plays at the volume of the furniture's distance.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator HumDisc_c_HumAudioFadesOutJustPastTheHumRadius()
        {
            Assert.That(Tuning.SfxHumMaxDistance, Is.InRange(3.25f, 3.75f), "the hum's audible range is not about 3.5 m");
            Assert.Greater(Tuning.SfxHumMaxDistance, Tuning.RobotHumRadius, "the hum falls silent inside its own masking radius");
            Assert.Greater(Sfx.HumVolumeAt(Tuning.RobotHumRadius), 0f, "the hum is silent on the disc's edge");
            Assert.Greater(Sfx.HumVolumeAt(Tuning.RobotHumRadius), Sfx.HumVolumeAt(3.2f), "the hum does not fade past the disc");
            Assert.AreEqual(0f, Sfx.HumVolumeAt(3.6f), 1e-6f, "the hum is still heard 3.6 m away");
            Assert.AreEqual(0f, Sfx.HumVolumeAt(Tuning.SfxHumMaxDistance), 1e-6f, "the hum is heard at its max distance");

            yield return LoadRobotLevel();
            yield return Steps(2);
            Robot robot = Game.Robots[0];
            AudioSource source = Sfx.HumOf(robot);
            Assert.IsNotNull(source, "the robot has no hum source");
            Assert.AreEqual(Tuning.SfxHumMaxDistance, source.maxDistance, 1e-6f, "the hum source's max distance");
            Assert.AreEqual(Tuning.SfxHumMinDistance, source.minDistance, 1e-6f, "the hum source's min distance");
            Assert.AreEqual(AudioRolloffMode.Linear, source.rolloffMode, "the hum source's rolloff");
            Assert.IsNotNull(Game.Furniture, "premise: level9 has a player furniture");
            float d = Planar(robot.Position, Game.Furniture.transform.position);
            Assert.AreEqual(Sfx.HumVolumeAt(d), source.volume, 1e-3f, $"the hum's volume with the furniture {d:0.00} m from the robot");
            CollectionAssert.IsEmpty(logged, "no error logged");
        }
    }
}
