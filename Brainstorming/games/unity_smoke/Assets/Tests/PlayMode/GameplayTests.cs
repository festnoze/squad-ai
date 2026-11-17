using System.Collections;
using NUnit.Framework;
using Smoke;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace Smoke.Tests.PlayMode
{
    public sealed class GameplayTests
    {
        private const int ExpectedCoins = 8;

        [UnitySetUp]
        public IEnumerator LoadMainScene()
        {
            yield return SceneManager.LoadSceneAsync("Main", LoadSceneMode.Single);
            // Start() runs on the first frame after load.
            yield return null;
        }

        [UnityTest]
        public IEnumerator Scene_has_player_coins_and_hud()
        {
            Assert.IsNotNull(Object.FindFirstObjectByType<PlayerController>(), "player missing");
            Assert.IsNotNull(GameManager.Instance, "game manager missing");
            Assert.AreEqual(ExpectedCoins, GameManager.Instance.Counter.Total);
            yield break;
        }

        [UnityTest]
        public IEnumerator Player_does_not_fall_through_the_ground()
        {
            PlayerController player = Object.FindFirstObjectByType<PlayerController>();
            // Physics steps, not rendered frames: at high fps a frame count says nothing about simulated time.
            for (int i = 0; i < 100; i++)
            {
                yield return new WaitForFixedUpdate();
            }
            Assert.That(player.transform.position.y, Is.InRange(0.4f, 0.6f));
        }

        [UnityTest]
        public IEnumerator Autopilot_collects_every_coin_and_wins()
        {
            PlayerController player = Object.FindFirstObjectByType<PlayerController>();
            player.Autopilot = true;
            float start = Time.time;
            while (!GameManager.Instance.Won && Time.time - start < 60f)
            {
                yield return new WaitForFixedUpdate();
            }
            Assert.IsTrue(GameManager.Instance.Won, $"only {GameManager.Instance.Counter.Collected}/{ExpectedCoins} coins after 60 s");
            Assert.AreEqual(ExpectedCoins, GameManager.Instance.Counter.Collected);
            Assert.Greater(GameManager.Instance.WinTime, 0f);
        }
    }
}
