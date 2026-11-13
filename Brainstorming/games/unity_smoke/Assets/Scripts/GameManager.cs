using UnityEngine;
using UnityEngine.UI;

namespace Smoke
{
    /// <summary>Counts the coins present in the scene, updates the HUD and declares the win.</summary>
    public sealed class GameManager : MonoBehaviour
    {
        public static GameManager Instance { get; private set; }

        [SerializeField] private Text scoreText;
        [SerializeField] private Text messageText;

        private CoinCounter counter;
        private float startTime;

        public CoinCounter Counter => counter;
        public bool Won => counter != null && counter.IsComplete;
        public float WinTime { get; private set; } = -1f;

        private void Awake()
        {
            Instance = this;
        }

        private void Start()
        {
            counter = new CoinCounter(FindObjectsByType<Coin>(FindObjectsSortMode.None).Length);
            startTime = Time.time;
            RefreshHud();
            if (messageText != null)
            {
                messageText.text = "ZQSD / fleches pour ramasser les pieces";
            }
        }

        private void OnDestroy()
        {
            if (Instance == this)
            {
                Instance = null;
            }
        }

        public void Collect(Coin coin)
        {
            if (counter == null || !counter.Collect())
            {
                return;
            }
            coin.gameObject.SetActive(false);
            RefreshHud();
            if (counter.IsComplete)
            {
                WinTime = Time.time - startTime;
                if (messageText != null)
                {
                    messageText.text = $"Gagne ! ({WinTime:0.0} s)";
                }
                Debug.Log($"[Smoke] All {counter.Total} coins collected in {WinTime:0.00} s");
            }
        }

        private void RefreshHud()
        {
            if (scoreText != null && counter != null)
            {
                scoreText.text = counter.Label;
            }
        }
    }
}
