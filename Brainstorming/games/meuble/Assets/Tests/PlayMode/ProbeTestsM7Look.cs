using System.Collections;
using System.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace Meuble.Tests
{
    /// <summary>
    /// M7 lighting polish (docs/CONTRACT_M7.md 1.1, polish round 2). Step60a_ guards what the before/after shots
    /// cannot: the key light still casts soft shadows, the Volume still carries an active tonemapper and a
    /// thresholded bloom, and the player furniture, read straight off every renderer's own _BaseColor (never a
    /// screenshot: PRD 7.2's rule is about the colour every object is built with, and a pixel readback would only
    /// add noise and cost), stays the most saturated thing in level5's start view. Step60b_ guards the new floor
    /// lamp glow: it follows the lamp's own switch, on the one level whose player is a floor lamp.
    /// </summary>
    public sealed class ProbeTestsM7Look
    {
        private Main main;
        private GameState Game => main.Game;
        private FurnitureController Chair => Game.Furniture;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
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
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            yield return null;
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        /// <summary>The HSV saturation of a renderer's own _BaseColor, or -1 for a material without one (never black).</summary>
        private static float Saturation(Renderer r)
        {
            Material m = r != null ? r.sharedMaterial : null;
            if (m == null || !m.HasProperty("_BaseColor"))
            {
                return -1f;
            }
            Color.RGBToHSV(m.GetColor("_BaseColor"), out _, out float s, out float v);
            return v > 0.02f ? s : -1f;
        }

        [UnityTest]
        public IEnumerator Step60a_KeyLightSoftShadowsBloomAndChairStaysTheMostSaturatedRed()
        {
            Game.LoadLevel("level5");
            yield return Steps(5);

            Assert.IsNotNull(main.Sun, "premise: Main built no sun");
            Assert.AreEqual(LightType.Directional, main.Sun.type, "the key light is not directional");
            Assert.AreEqual(LightShadows.Soft, main.Sun.shadows, "the key light does not cast soft shadows");
            // main.PostProcessing is a Volume (Unity.RenderPipelines.Core.Runtime), not referenced by
            // Tests.PlayMode's asmdef, so the Volume is only ever read through this bool, never named here.
            Assert.IsTrue(main.VolumeHasTonemapperAndBloom(), "the Volume has no active tonemapper or no active, thresholded bloom");

            MeshRenderer[] chairRenderers = Chair.GetComponentsInChildren<MeshRenderer>(true);
            Assert.IsNotEmpty(chairRenderers, "premise: the player furniture has no renderer");
            float chairSat = chairRenderers.Select(Saturation).DefaultIfEmpty(-1f).Max();
            Assert.Greater(chairSat, 0.3f, "premise: the player furniture's own colour does not read as saturated red");

            int compared = 0;
            foreach (MeshRenderer r in Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None))
            {
                if (r == null || !r.enabled || !r.gameObject.activeInHierarchy || r.transform.IsChildOf(Chair.transform))
                {
                    continue;
                }
                float s = Saturation(r);
                if (s < 0f)
                {
                    continue;
                }
                compared++;
                Assert.Less(s, chairSat, $"{r.name} (saturation {s:0.00}) is at least as saturated as the player furniture ({chairSat:0.00})");
            }
            Assert.Greater(compared, 5, "premise: too few other renderers to compare the player furniture against");
        }

        [UnityTest]
        public IEnumerator Step60b_LampGlowFollowsItsSwitch()
        {
            Game.LoadLevel("level16");
            yield return Steps(5);
            Assert.AreEqual("floor_lamp", Chair.Kind, "premise: level16's player is not the floor lamp");
            LampLight lamp = Chair.Lamp;
            Assert.IsNotNull(lamp, "premise: the floor lamp body has no LampLight");
            Transform glow = lamp.transform.Find("Glow");
            Assert.IsNotNull(glow, "premise: the lamp has no glow child");
            var glowRenderer = glow.GetComponent<Renderer>();
            Assert.IsNotNull(glowRenderer, "premise: the glow has no renderer");

            Assert.IsTrue(lamp.On, "premise: a lamp starts switched on");
            Assert.IsTrue(glowRenderer.enabled, "the glow is off while the lamp is on");
            lamp.SetOn(false);
            Assert.IsFalse(glowRenderer.enabled, "the glow stays on while the lamp is off");
            lamp.SetOn(true);
            Assert.IsTrue(glowRenderer.enabled, "the glow did not come back with the lamp");
        }
    }
}
