using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.UI;

namespace Viewpoint
{
    /// <summary>
    /// Screenshot and diagnostic probe (PRD section 14.6). Lives in the RUNTIME
    /// assembly, not the test assembly, precisely so it works in a built player:
    /// a player is the only place with a real graphics device, and every claim
    /// about what the game LOOKS like has to be made there.
    ///
    /// Run it with:  VIEWPOINT.exe --shot
    ///
    /// It writes PNGs and a diagnostics.txt next to the executable, then quits.
    /// The diagnostics matter as much as the pictures: a black frame tells you
    /// something is wrong, the dump tells you whether the shader resolved, the
    /// font built, the meshes exist and the camera is pointing at the level.
    /// </summary>
    public sealed class ShotProbe : MonoBehaviour
    {
        Main _main;
        string _dir;
        readonly StringBuilder _log = new StringBuilder();

        public void Setup(Main main)
        {
            _main = main;
        }

        void Start()
        {
            _dir = Path.Combine(Application.dataPath, "..", "Shots");
            _dir = Path.GetFullPath(_dir);
            Directory.CreateDirectory(_dir);
            StartCoroutine(Run());
        }

        IEnumerator Run()
        {
            Line("VIEWPOINT shot probe");
            Line("graphics device: " + SystemInfo.graphicsDeviceType);
            Line("screen: " + Screen.width + "x" + Screen.height);
            Line("");

            yield return Frames(10);

            DumpRender();
            DumpFont();
            yield return Shot("01_title");
            DumpMenu();

            _main.StartAt(0);
            // 90 fixed steps is a second and a half of gravity: enough for the
            // spawn drop to finish on every level in the game.
            yield return Settle(90);
            yield return Frames(2);
            Line("");
            Line("--- level 1 ---");
            DumpLevel();
            DumpCamera();
            yield return Shot("02_level1");

            // Look straight down: if the ground renders at all, this frame is
            // solid platform. It separates "nothing is drawn" from "the camera
            // is aimed at empty sky".
            _main.Player.SetLook(0f, 80f);
            yield return Frames(5);
            yield return Shot("03_level1_looking_down");
            _main.Player.SetLook(0f, 0f);
            yield return Frames(5);

            foreach (int index in new[] { 3, 5, 15 })
            {
                _main.LoadLevel(index);
                yield return Settle(90);
                yield return Frames(2);
                Line("");
                Line("--- level " + (index + 1) + " ---");
                DumpLevel();
                DumpCamera();
                yield return Shot("04_level" + (index + 1));
            }

            File.WriteAllText(Path.Combine(_dir, "diagnostics.txt"), _log.ToString());
            Debug.Log("[ShotProbe] wrote " + _dir);
            yield return Frames(2);
            Application.Quit(0);
        }

        // ---- Diagnostics ----------------------------------------------------

        void DumpRender()
        {
            Line("--- render ---");
            Shader lit = Shader.Find("Universal Render Pipeline/Lit");
            Shader unlit = Shader.Find("Universal Render Pipeline/Unlit");
            Shader sky = Shader.Find("Viewpoint/GradientSky");
            Line("shader URP/Lit    : " + Describe(lit));
            Line("shader URP/Unlit  : " + Describe(unlit));
            Line("shader GradientSky: " + Describe(sky));

            Material solid = Materials.Solid("platform");
            Line("Materials.Solid(platform): " + Describe(solid)
                + (solid != null ? " shader=" + Describe(solid.shader) : ""));
            Material glow = Materials.Solid("battery", 0.8f);
            Line("Materials.Solid(battery,0.8): " + Describe(glow)
                + (glow != null ? " shader=" + Describe(glow.shader) : ""));
            Line("RenderSettings.skybox: " + Describe(RenderSettings.skybox));
            Line("ambientMode: " + RenderSettings.ambientMode + " fog: " + RenderSettings.fog);
            Line("cube mesh: " + Describe(Resources.GetBuiltinResource<Mesh>("Cube.fbx")));
        }

        void DumpFont()
        {
            Line("--- font ---");
            Font font = Fonts.Default;
            Line("Fonts.Default: " + Describe(font));
            if (font != null)
            {
                Line("  dynamic: " + font.dynamic + " material: " + Describe(font.material));
            }
            Line("builtin LegacyRuntime.ttf: " + Describe(Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf")));
            Line("OS fonts installed: " + (Font.GetOSInstalledFontNames() ?? new string[0]).Length);
        }

        void DumpMenu()
        {
            Line("--- menu labels ---");
            var labels = new List<Text>();
            _main.Menu.GetComponentsInChildren(true, labels);
            Line("Text under Menu: " + labels.Count);
            var shown = 0;
            foreach (Text label in labels)
            {
                if (shown >= 10)
                {
                    break;
                }
                string text = label.text ?? "";
                Line("  [" + label.name + "] font=" + (label.font != null ? label.font.name : "NULL")
                    + " size=" + label.fontSize
                    + " chars=" + text.Length
                    + " visible=" + label.isActiveAndEnabled
                    + " alpha=" + label.color.a.ToString("0.00")
                    + " text=\"" + Clip(text) + "\"");
                shown++;
            }
        }

        void DumpLevel()
        {
            Line("groups: platform=" + Groups.Count(Groups.Platform)
                + " carvable=" + Groups.Count(Groups.Carvable)
                + " photographable=" + Groups.Count(Groups.Photographable)
                + " photo_item=" + Groups.Count(Groups.PhotoItem)
                + " battery=" + Groups.Count(Groups.Battery)
                + " teleporter=" + Groups.Count(Groups.Teleporter));

            // The question the pictures cannot answer on their own: is there
            // geometry, does it have a material, and is it where the camera is.
            var renderers = new List<MeshRenderer>();
            _main.LevelRoot.GetComponentsInChildren(true, renderers);
            var enabledCount = 0;
            var nullMaterial = 0;
            var nullMesh = 0;
            Bounds bounds = new Bounds();
            var haveBounds = false;
            foreach (MeshRenderer r in renderers)
            {
                if (r.enabled && r.gameObject.activeInHierarchy)
                {
                    enabledCount++;
                    if (!haveBounds)
                    {
                        bounds = r.bounds;
                        haveBounds = true;
                    }
                    else
                    {
                        bounds.Encapsulate(r.bounds);
                    }
                }
                if (r.sharedMaterial == null)
                {
                    nullMaterial++;
                }
                MeshFilter f = r.GetComponent<MeshFilter>();
                if (f == null || f.sharedMesh == null)
                {
                    nullMesh++;
                }
            }
            Line("renderers: " + renderers.Count + " enabled=" + enabledCount
                + " nullMaterial=" + nullMaterial + " nullMesh=" + nullMesh);
            Line("world bounds: " + (haveBounds ? bounds.center + " size " + bounds.size : "NONE"));

            // Anything the player is meant to walk up to and interact with:
            // where it is, whether it draws, and whether the camera can see it.
            // A pickup that exists in a group but has no visible renderer is the
            // failure the pictures alone cannot explain.
            Camera cam = _main.Player.Camera;
            foreach (PhotoItem item in Groups.Snapshot<PhotoItem>(Groups.PhotoItem))
            {
                DumpPickup("photo " + item.DefId, item.transform, cam);
            }
            foreach (Battery battery in Groups.Snapshot<Battery>(Groups.Battery))
            {
                DumpPickup(battery.IsSealed ? "battery(lead)" : "battery", battery.transform, cam);
            }
        }

        void DumpPickup(string what, Transform t, Camera cam)
        {
            var renderers = new List<Renderer>();
            t.GetComponentsInChildren(true, renderers);
            var drawn = 0;
            Bounds b = new Bounds(t.position, Vector3.zero);
            foreach (Renderer r in renderers)
            {
                if (r.enabled && r.gameObject.activeInHierarchy && r.sharedMaterial != null)
                {
                    drawn++;
                    b.Encapsulate(r.bounds);
                }
            }
            string where = "offscreen";
            if (cam != null)
            {
                Vector3 v = cam.WorldToViewportPoint(t.position);
                where = v.z > 0f && v.x > 0f && v.x < 1f && v.y > 0f && v.y < 1f
                    ? "ON SCREEN at " + v.x.ToString("0.00") + "," + v.y.ToString("0.00")
                    : "offscreen (viewport " + v.x.ToString("0.00") + "," + v.y.ToString("0.00") + "," + v.z.ToString("0.0") + ")";
            }
            Line("  " + what + " at " + t.position + " renderers=" + renderers.Count
                + " drawn=" + drawn + " extent=" + b.size.magnitude.ToString("0.00") + " " + where);
        }

        void DumpCamera()
        {
            Camera cam = _main.Player.Camera;
            if (cam == null)
            {
                Line("camera: NULL");
                return;
            }
            Transform t = cam.transform;
            Line("camera pos " + t.position + " forward " + t.forward
                + " fov " + cam.fieldOfView + " mask 0x" + cam.cullingMask.ToString("X")
                + " clear " + cam.clearFlags + " enabled " + cam.enabled
                + " depth " + cam.depth);
            Line("player pos " + _main.Player.transform.position);
            RaycastHit ground;
            if (Physics.Raycast(_main.Player.transform.position + Vector3.up * 0.1f,
                    Vector3.down, out ground, 50f, Layers.WorldMask))
            {
                float feet = _main.Player.transform.position.y;
                Line("standing on " + ground.collider.name + " top y=" + ground.point.y.ToString("0.000")
                    + " feet y=" + feet.ToString("0.000")
                    + " eye above ground=" + (t.position.y - ground.point.y).ToString("0.000")
                    + " (expected " + PlayerController.EyeHeight.ToString("0.00") + ")");
            }
            else
            {
                Line("standing on NOTHING (feet y=" + _main.Player.transform.position.y.ToString("0.000") + ")");
            }
            Line("cameras alive: " + Camera.allCamerasCount);
            foreach (Camera other in Camera.allCameras)
            {
                Line("  cam[" + other.name + "] depth=" + other.depth
                    + " mask=0x" + other.cullingMask.ToString("X")
                    + " target=" + (other.targetTexture != null ? "RT" : "screen"));
            }

            // What is actually in front of the eye, measured rather than judged.
            RaycastHit hit;
            bool forward = Physics.Raycast(t.position, t.forward, out hit, 100f, Layers.WorldMask);
            Line("ray forward: " + (forward ? hit.collider.name + " at " + hit.distance.ToString("0.00") + " m" : "nothing within 100 m"));
            bool down = Physics.Raycast(t.position, Vector3.down, out hit, 100f, Layers.WorldMask);
            Line("ray down   : " + (down ? hit.collider.name + " at " + hit.distance.ToString("0.00") + " m" : "nothing within 100 m"));
        }

        // ---- Helpers --------------------------------------------------------

        IEnumerator Shot(string name)
        {
            yield return new WaitForEndOfFrame();
            var texture = new Texture2D(Screen.width, Screen.height, TextureFormat.RGB24, false);
            texture.ReadPixels(new Rect(0, 0, Screen.width, Screen.height), 0, 0);
            texture.Apply();
            File.WriteAllBytes(Path.Combine(_dir, name + ".png"), texture.EncodeToPNG());
            // The mean colour separates "a picture of the sky" from "a black
            // frame" without anyone having to open the file.
            Color32[] pixels = texture.GetPixels32();
            long r = 0, g = 0, b = 0;
            for (var i = 0; i < pixels.Length; i += 97)
            {
                r += pixels[i].r;
                g += pixels[i].g;
                b += pixels[i].b;
            }
            int n = (pixels.Length + 96) / 97;
            Line("shot " + name + ": mean rgb " + (r / n) + "," + (g / n) + "," + (b / n));
            Destroy(texture);
        }

        IEnumerator Frames(int count)
        {
            for (var i = 0; i < count; i++)
            {
                yield return null;
            }
        }

        /// <summary>
        /// Waits on PHYSICS steps, not render frames, and everything about a
        /// settled player has to go through here.
        ///
        /// The reason, learned the embarrassing way: this scene runs at several
        /// hundred frames a second, so thirty render frames is about sixty
        /// milliseconds, in which a player falling from its 1.2 m spawn covers
        /// two and a half centimetres. The first run of this probe duly
        /// reported the eye at 2.61 m instead of 1.62 and it looked exactly
        /// like a broken character controller. Gravity advances on the fixed
        /// step and nothing else.
        /// </summary>
        IEnumerator Settle(int fixedSteps)
        {
            for (var i = 0; i < fixedSteps; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        static string Describe(Object o)
        {
            return o == null ? "NULL" : o.name;
        }

        static string Clip(string s)
        {
            s = s.Replace("\n", "\\n");
            return s.Length <= 60 ? s : s.Substring(0, 60) + "...";
        }

        void Line(string text)
        {
            _log.AppendLine(text);
            Debug.Log("[ShotProbe] " + text);
        }
    }
}
