using System;
using System.Collections;
using System.IO;
using UnityEngine;
using UnityEngine.UI;

namespace Smoke
{
    /// <summary>
    /// Built-player self check. Inactive unless the player is launched with "-smoke".
    /// Usage: unity_smoke.exe -smoke -shot C:\path\shot.png
    /// It enables the autopilot, waits for the win, audits renderers and fonts, captures a
    /// screenshot, logs one "[SmokeResult]" line and quits with 0 (pass) or 1 (fail).
    /// </summary>
    public sealed class SmokeProbe : MonoBehaviour
    {
        private const float TimeoutSeconds = 90f;

        private void Start()
        {
            string[] args = Environment.GetCommandLineArgs();
            if (Array.IndexOf(args, "-smoke") < 0)
            {
                return;
            }
            string shot = ArgValue(args, "-shot") ?? Path.Combine(Application.persistentDataPath, "smoke.png");
            StartCoroutine(Run(shot));
        }

        private static string ArgValue(string[] args, string name)
        {
            int i = Array.IndexOf(args, name);
            return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
        }

        private IEnumerator Run(string shotPath)
        {
            // Audit and capture the untouched level first: collected coins are deactivated,
            // so an end-of-game audit alone would never see their renderers.
            for (int i = 0; i < 10; i++)
            {
                yield return new WaitForFixedUpdate();
            }
            int startBadRenderers = CountBadRenderers(out int startRenderers);
            string startShot = Path.Combine(Path.GetDirectoryName(shotPath) ?? "",
                Path.GetFileNameWithoutExtension(shotPath) + "_start.png");
            yield return Capture(startShot);
            bool startShotOk = File.Exists(startShot);

            PlayerController player = FindFirstObjectByType<PlayerController>();
            if (player != null)
            {
                player.Autopilot = true;
            }

            float start = Time.time;
            while (Time.time - start < TimeoutSeconds && (GameManager.Instance == null || !GameManager.Instance.Won))
            {
                yield return new WaitForFixedUpdate();
            }
            // Let the win message render before capturing.
            yield return new WaitForSeconds(0.5f);

            int badRenderers = startBadRenderers + CountBadRenderers(out _);
            int badTexts = 0;
            foreach (Text t in FindObjectsByType<Text>(FindObjectsSortMode.None))
            {
                if (t.font == null || string.IsNullOrEmpty(t.text))
                {
                    badTexts++;
                    Debug.LogError($"[Smoke] Text without font or content on {t.name}");
                }
            }

            yield return Capture(shotPath);

            GameManager gm = GameManager.Instance;
            bool won = gm != null && gm.Won;
            bool shotOk = File.Exists(shotPath) && startShotOk;
            // 4 walls + ground + player + 8 coins: fewer means the level did not build.
            bool levelOk = startRenderers >= 14;
            bool pass = won && levelOk && badRenderers == 0 && badTexts == 0 && shotOk;
            string coins = gm != null && gm.Counter != null ? $"{gm.Counter.Collected}/{gm.Counter.Total}" : "n/a";
            Debug.Log($"[SmokeResult] pass={pass} won={won} coins={coins} winTime={(gm != null ? gm.WinTime : -1f):0.00} " +
                      $"startRenderers={startRenderers} badRenderers={badRenderers} badTexts={badTexts} shots={shotOk} " +
                      $"gfx={SystemInfo.graphicsDeviceType}");
            Application.Quit(pass ? 0 : 1);
        }

        private static int CountBadRenderers(out int total)
        {
            int bad = 0;
            Renderer[] renderers = FindObjectsByType<Renderer>(FindObjectsSortMode.None);
            total = renderers.Length;
            foreach (Renderer r in renderers)
            {
                Material m = r.sharedMaterial;
                if (m == null || m.shader == null || !m.shader.isSupported || m.shader.name.Contains("InternalErrorShader"))
                {
                    bad++;
                    Debug.LogError($"[Smoke] Broken material on {r.name}");
                }
            }
            return bad;
        }

        private static IEnumerator Capture(string path)
        {
            string dir = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(dir))
            {
                Directory.CreateDirectory(dir);
            }
            if (File.Exists(path))
            {
                File.Delete(path);
            }
            ScreenCapture.CaptureScreenshot(path);
            float start = Time.realtimeSinceStartup;
            while (!File.Exists(path) && Time.realtimeSinceStartup - start < 5f)
            {
                yield return null;
            }
            // The file appears before it is fully flushed; give the writer a moment.
            yield return new WaitForSecondsRealtime(0.2f);
        }
    }
}
