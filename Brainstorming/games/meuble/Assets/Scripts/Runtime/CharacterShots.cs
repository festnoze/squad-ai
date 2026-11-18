using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace OutOfSight
{
    /// <summary>
    /// M7 faces: <c>--charshots &lt;dir&gt;</c> (built player only) photographs the humans of the first level shown (the
    /// title page's house): a close-up of each face and of the back of its head, the whole body from the front and from
    /// the back, a three-quarter view from above at play distance and one at the title tour's height, then quits.
    /// <c>--charlevels a,b</c> adds the humans of those levels (files prefixed with the level id).
    /// Only the Inhabitant layer is drawn (no wall or prop in the way), over a plain backdrop, with the game's own post
    /// processing. A review aid for the faces and clothes of <see cref="CharacterLook"/>; never runs in a normal game.
    /// </summary>
    internal sealed class CharacterShots : MonoBehaviour
    {
        private const int Width = 1280;
        private const int Height = 960;
        private static readonly Color Backdrop = new Color(0.80f, 0.77f, 0.72f);

        private string dir;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Boot()
        {
            string dir = Probe.ArgValue("--charshots");
            if (Application.isEditor || string.IsNullOrEmpty(dir))
            {
                return;
            }
            var go = new GameObject("CharacterShots");
            DontDestroyOnLoad(go);
            go.AddComponent<CharacterShots>().dir = dir;
        }

        private IEnumerator Start()
        {
            Directory.CreateDirectory(dir);
            var lines = new List<string>();
            List<Inhabitant> humans = null;
            float deadline = Time.realtimeSinceStartup + 90f;
            while (Time.realtimeSinceStartup < deadline)
            {
                GameState game = Main.Instance != null ? Main.Instance.Game : null;
                if (game != null && game.Level != null)
                {
                    humans = game.Level.Inhabitants.Where(h => h != null && h.Rig != null && !h.Rig.IsPet).ToList();
                    if (humans.Count > 0)
                    {
                        break;
                    }
                }
                yield return null;
            }
            for (int i = 0; i < 60; i++)
            {
                yield return null; // let the clips settle into a pose
            }
            if (System.Environment.GetCommandLineArgs().Contains("--charlow"))
            {
                QualitySettings.SetQualityLevel(System.Array.IndexOf(QualitySettings.names, QualityTier.LevelLow), true);
                yield return null;
            }
            lines.Add("Quality: " + QualitySettings.names[QualitySettings.GetQualityLevel()]);
            yield return ShootHumans(humans, "", lines);
            // "--charlevels a,b": the humans of those levels too (the other models and personalities).
            string more = Probe.ArgValue("--charlevels");
            foreach (string id in (more ?? "").Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries))
            {
                GameState game = Main.Instance != null ? Main.Instance.Game : null;
                if (game == null)
                {
                    break;
                }
                game.LoadLevel(id.Trim());
                for (int i = 0; i < 60; i++)
                {
                    yield return null;
                }
                List<Inhabitant> found = game.Level != null
                    ? game.Level.Inhabitants.Where(h => h != null && h.Rig != null && !h.Rig.IsPet).ToList()
                    : null;
                yield return ShootHumans(found, Safe(id.Trim()) + "_", lines);
            }
            File.WriteAllLines(Path.Combine(dir, "charshots.txt"), lines);
            Application.Quit();
        }

        private IEnumerator ShootHumans(List<Inhabitant> humans, string prefix, List<string> lines)
        {
            if (humans == null || humans.Count == 0)
            {
                lines.Add(prefix + "no human inhabitant found");
            }
            else
            {
                // Only the bodies: the markers and cones on the inhabitants' layer step aside for the shots.
                var keep = new HashSet<Renderer>();
                GameState game = Main.Instance != null ? Main.Instance.Game : null;
                if (game != null && game.Level != null)
                {
                    foreach (Inhabitant any in game.Level.Inhabitants)
                    {
                        if (any != null && any.Rig != null && any.Rig.Model != null)
                        {
                            // The skinned bodies and brows. The gameplay marker can also hang under the head.
                            keep.UnionWith(any.Rig.Model.GetComponentsInChildren<SkinnedMeshRenderer>(true));
                            if (any.Rig.BrowLeft != null) { keep.Add(any.Rig.BrowLeft.GetComponent<Renderer>()); }
                            if (any.Rig.BrowRight != null) { keep.Add(any.Rig.BrowRight.GetComponent<Renderer>()); }
                        }
                    }
                }
                var moved = new List<GameObject>();
                foreach (Renderer r in FindObjectsByType<Renderer>(FindObjectsSortMode.None))
                {
                    if (r.gameObject.layer == Layers.Inhabitant && !keep.Contains(r))
                    {
                        r.gameObject.layer = 2; // Ignore Raycast: never drawn by the shot camera
                        moved.Add(r.gameObject);
                    }
                }
                var hiddenCanvases = new List<GameObject>();
                foreach (Canvas c in FindObjectsByType<Canvas>(FindObjectsSortMode.None))
                {
                    if (c.enabled && c.renderMode == RenderMode.WorldSpace)
                    {
                        c.gameObject.SetActive(false);
                        hiddenCanvases.Add(c.gameObject);
                    }
                }
                foreach (Inhabitant h in humans.Take(3))
                {
                    InhabitantRig rig = h.Rig;
                    Renderer[] subjects = h.GetComponentsInChildren<Renderer>(true);
                    var hidden = keep.Where(r => r != null && !r.forceRenderingOff && !subjects.Contains(r)).ToList();
                    foreach (Renderer r in hidden) { r.forceRenderingOff = true; }
                    string name = prefix + Safe(h.name);
                    lines.Add($"{h.name}: model {rig.Entry?.id}, face {(rig.HasPaintedHead ? "yes" : "no")}, "
                        + $"female {CharacterLook.IsFemale(rig.Entry)}, tint {(h.Tint.HasValue ? "#" + ColorUtility.ToHtmlStringRGB(h.Tint.Value) : "none")}, "
                        + $"triangles {Probe.TrianglesUnder(h.transform)}, vertices {rig.Skin.sharedMesh.vertexCount}, animation {rig.CurrentClip}");
                    Vector3 look = Planar(rig.HeadForward);
                    Vector3 eye = rig.EyePosition;
                    yield return Shoot(eye + look * 0.62f + Vector3.up * 0.06f, eye - Vector3.up * 0.035f, 26f, $"face_{name}.png");
                    Vector3 profile = Quaternion.Euler(0f, 90f, 0f) * look;
                    yield return Shoot(eye + profile * 0.68f + Vector3.up * 0.06f, eye - Vector3.up * 0.035f, 28f, $"profile_{name}.png");
                    // Slight elevation shows the rear projection over the hair and nape.
                    yield return Shoot(eye - look * 0.62f + Vector3.up * 0.12f, eye - Vector3.up * 0.04f, 30f, $"head_back_{name}.png");
                    Vector3 body = Planar(h.Visual != null ? h.Visual.forward : h.transform.forward);
                    Vector3 feet = h.transform.position;
                    yield return Shoot(feet + body * 3.0f + Vector3.up * 1.25f, feet + Vector3.up * 0.88f, 33f, $"body_front_{name}.png");
                    yield return Shoot(feet - body * 3.0f + Vector3.up * 1.25f, feet + Vector3.up * 0.88f, 33f, $"body_back_{name}.png");
                    // Play distance: several metres away, a three-quarter view from above (the clothes and the
                    // personality's bands must read there); then the title tour's height (1 m), closer.
                    Vector3 side = Quaternion.Euler(0f, 40f, 0f) * body;
                    yield return Shoot(feet + side * 4.2f + Vector3.up * 4.6f, feet + Vector3.up * 0.9f, 34f, $"play_{name}.png");
                    yield return Shoot(feet + side * 2.4f + Vector3.up * 1.0f, feet + Vector3.up * 1.0f, 50f, $"tour_{name}.png");
                    foreach (Renderer r in hidden) { r.forceRenderingOff = false; }
                }
                foreach (GameObject g in moved)
                {
                    if (g != null)
                    {
                        g.layer = Layers.Inhabitant;
                    }
                }
                foreach (GameObject canvasRoot in hiddenCanvases)
                {
                    if (canvasRoot != null)
                    {
                        canvasRoot.SetActive(true);
                    }
                }
            }
        }

        private static Vector3 Planar(Vector3 v)
        {
            v.y = 0f;
            return v.sqrMagnitude > 1e-6f ? v.normalized : Vector3.forward;
        }

        private static string Safe(string s)
        {
            return new string((s ?? "x").Select(c => char.IsLetterOrDigit(c) ? c : '_').ToArray());
        }

        private IEnumerator Shoot(Vector3 from, Vector3 at, float fov, string file)
        {
            var rt = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32);
            var go = new GameObject("CharacterShotCamera");
            var cam = go.AddComponent<Camera>();
            go.transform.position = from;
            go.transform.LookAt(at);
            cam.fieldOfView = fov;
            cam.nearClipPlane = 0.05f;
            cam.farClipPlane = 60f;
            cam.cullingMask = 1 << Layers.Inhabitant;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = Backdrop;
            cam.enabled = false;
            cam.GetUniversalAdditionalCameraData().renderPostProcessing = true;
            // A diffuse fill for the inspection angles, independent of which way the room light points.
            if (!file.StartsWith("play_") && !file.StartsWith("tour_"))
            {
                var fillObject = new GameObject("Portrait fill");
                fillObject.transform.SetParent(go.transform);
                fillObject.transform.position = at + (from - at).normalized * 1.8f;
                var fill = fillObject.AddComponent<Light>();
                fill.type = LightType.Point;
                fill.intensity = 0.65f;
                fill.range = 5f;
                fill.cullingMask = cam.cullingMask;
            }
            yield return null;
            RenderPipeline.SubmitRenderRequest(cam, new UniversalRenderPipeline.SingleCameraRequest { destination = rt });
            var texture = new Texture2D(Width, Height, TextureFormat.RGB24, false);
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = rt;
            texture.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
            texture.Apply();
            RenderTexture.active = previous;
            File.WriteAllBytes(Path.Combine(dir, file), texture.EncodeToPNG());
            Destroy(texture);
            Destroy(go);
            rt.Release();
            Destroy(rt);
        }
    }
}
