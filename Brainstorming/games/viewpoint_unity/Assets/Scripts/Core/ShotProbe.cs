using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.UI;
// Aliased rather than imported wholesale: only a handful of types are wanted
// out of UnityEngine.Rendering and UnityEngine.Rendering.Universal, and a whole
// URP namespace opened beside UnityEngine and UnityEngine.UI is an ambiguity
// waiting for the next edit.
using DecalProjector = UnityEngine.Rendering.Universal.DecalProjector;
using UniversalAdditionalCameraData = UnityEngine.Rendering.Universal.UniversalAdditionalCameraData;
using Volume = UnityEngine.Rendering.Volume;
using VolumeProfile = UnityEngine.Rendering.VolumeProfile;

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
            DumpFeedback();
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
                DumpFeedback();
                yield return Shot("04_level" + (index + 1));
            }

            // The moments PRD_VISUAL 6.1 asks this list to grow with, and the
            // only frames in the run where the feedback of section 4.8 is on
            // screen at all.
            //
            // They come LAST because reaching them costs the level: the camera
            // pickup is retired, a film is spent and the rewind then rolls the
            // world back over both. Nothing after this point needs a pristine
            // level, and every level census above has already been taken.
            //
            // Level 16 is still loaded, and it is the first level that hands out
            // a camera (levels.json, index 15, two films), so the viewfinder,
            // the picture it produces and the rewind that undoes them are all
            // reachable from here through the same public API a player drives.
            Line("");
            Line("--- feedback moments ---");
            yield return FeedbackViewfinder();
            yield return FeedbackRaisedPhoto();
            yield return FeedbackRewind();

            File.WriteAllText(Path.Combine(_dir, "diagnostics.txt"), _log.ToString());
            Debug.Log("[ShotProbe] wrote " + _dir);
            yield return Frames(2);
            Application.Quit(0);
        }

        // ---- Feedback moments -----------------------------------------------

        /// <summary>
        /// The viewfinder up (V-VFX-06), reached the way the player reaches it:
        /// the level's camera pickup hands out its film through the very
        /// Interact() the interaction ray calls, and ToggleViewfinder is the
        /// right click. Nothing here touches private state, and nothing here
        /// exists only for the probe.
        ///
        /// EVERY WAIT IN THIS SECTION IS ON FIXED STEPS, for the reason Settle
        /// gives below and not a new one. A render frame in this player lasts
        /// well under a millisecond, so the 0.15 s the brackets take to slide in
        /// would still be in its first few percent after Frames(30): the picture
        /// would show an animation that has not started, which is exactly what
        /// an animation nobody wrote looks like. A fixed step is 20 ms of REAL
        /// time, so fifteen of them are 0.3 s of it.
        /// </summary>
        IEnumerator FeedbackViewfinder()
        {
            List<CameraItem> cameras = Groups.Snapshot<CameraItem>(Groups.CameraItem);
            if (cameras.Count > 0)
            {
                cameras[0].Interact(_main.Player);
                Line("camera pickup: taken, films=" + GameState.Instance.CameraFilms);
            }
            else
            {
                // Not expected on this level, and not worth losing three frames
                // of the shot list over: what is being verified here is that the
                // viewfinder state reaches the screen, so the film comes from the
                // same public counter the pickup would have filled and the log
                // says which of the two paths ran.
                GameState.Instance.AddFilms(1);
                Line("camera pickup: none in this level, film granted directly");
            }

            bool up = _main.Player.ToggleViewfinder();
            Line("viewfinder: " + up + " films=" + GameState.Instance.CameraFilms);
            yield return Settle(15);
            DumpFeedback();
            yield return Shot("05_viewfinder");
        }

        /// <summary>
        /// The raised picture (V-VFX-06's slide and V-ANIM-04's ease), taken
        /// with the camera rather than lifted off the ground, because the
        /// shutter is the one path that produces a photo AND raises it: PRD 7.1
        /// says a fresh polaroid comes out raised.
        ///
        /// The placer line of DumpFeedback matters most here of anywhere: this
        /// is the one frame in the run where the anchor is actually carrying a
        /// picture, so a placer that has been offset to animate the card shows
        /// up as a non-zero offset with the hand full.
        /// </summary>
        IEnumerator FeedbackRaisedPhoto()
        {
            bool taken = _main.Player.CapturePhoto();
            PhotoPlacer placer = _main.Player.Placer;
            Line("capture: " + taken + " held=\"" + placer.HeldId + "\""
                + " raised=" + placer.Raised + " roll=" + placer.RollSteps
                + " films=" + GameState.Instance.CameraFilms);

            // Long enough for the studio to render the snap (it drains its queue
            // at the end of a frame, and a fresh photo is a request, not a
            // thumbnail) and for the 0.35 s slide of V-VFX-06 on top.
            yield return Settle(30);
            Texture2D picture = PhotoSnaps.GetTexture(placer.HeldId);
            Line("held picture: " + Describe(picture)
                + (picture != null ? " " + picture.width + "x" + picture.height : ""));
            DumpFeedback();
            yield return Shot("06_raised_photo");
        }

        /// <summary>
        /// The rewind mid-scrub, driven through the SIMULATED input and not by
        /// calling Rewind.StartRewind, because Main.FixedUpdate owns the rewind:
        /// it calls StopRewind on the first fixed step where R is not held, so a
        /// scrub started by hand would already be over on the step before the
        /// frame it was meant to photograph, and the shot would show an ordinary
        /// level. ViewpointInput's simulation is the door the PlayMode probe
        /// uses for exactly this and it costs no new public surface.
        /// </summary>
        IEnumerator FeedbackRewind()
        {
            Rewind rewind = _main.Rewind;
            if (rewind == null)
            {
                // Main builds every subsystem inside its own try, so a rewind
                // that threw on the way up leaves the rest of the game running.
                // The shot is still taken: the list of frames has to keep its
                // length (verify-player.ps1 counts them), and a frame of the
                // level with no rewind tint on it is precisely the evidence.
                Line("rewind: NO REWIND, this frame is an ordinary one");
                DumpFeedback();
                yield return Shot("07_rewind_mid_scrub");
                yield break;
            }
            Line("rewind before: samples=" + rewind.SampleCount
                + " events=" + rewind.EventCount
                + " history=" + Num2(rewind.AvailableSeconds()) + " s");

            ViewpointInput.SimulatedInput = true;
            ViewpointInput.SimulatedRewindHeld = true;
            yield return Settle(15);
            Line("rewind mid-scrub: rewinding=" + rewind.IsRewinding
                + " samples=" + rewind.SampleCount
                + " history=" + Num2(rewind.AvailableSeconds()) + " s"
                + " held=\"" + _main.Player.Placer.HeldId + "\"");
            DumpFeedback();
            yield return Shot("07_rewind_mid_scrub");

            // Released before anything else, and then given three steps to take
            // effect: Main brings the controls back on the fixed step after the
            // key drops, and a run must not end with the game held in a state no
            // player could ever leave.
            ViewpointInput.ResetSimulation();
            yield return Settle(3);
            Line("rewind after: rewinding=" + rewind.IsRewinding
                + " control=" + _main.Player.ControlEnabled);
        }

        // ---- Diagnostics ----------------------------------------------------

        void DumpRender()
        {
            Line("--- render ---");
            Shader lit = Shader.Find("Universal Render Pipeline/Lit");
            Shader unlit = Shader.Find("Universal Render Pipeline/Unlit");
            Shader sky = Shader.Find("Viewpoint/GradientSky");
            // The alignment of these labels is load-bearing: verify-player.ps1
            // matches each of them with a literal Contains(), padding included.
            Shader surface = Shader.Find("Viewpoint/Surface");
            // V-MAT-08's painted panel. It is in the same list for the same
            // reason as the four above (PRD_VISUAL appendix A, "Always Included
            // Shaders"): nothing in the project REFERENCES it, the factory finds
            // it by name at run time, and a shader no asset references is
            // stripped from the player. Stripped, every placed backdrop draws
            // nothing and a photographed sky becomes a hole in the level.
            Shader backdrop = Shader.Find("Viewpoint/Backdrop");
            Line("shader URP/Lit    : " + Describe(lit));
            Line("shader URP/Unlit  : " + Describe(unlit));
            Line("shader GradientSky: " + Describe(sky));
            Line("shader Surface    : " + Describe(surface));
            Line("shader Backdrop   : " + Describe(backdrop));

            Material solid = Materials.Solid("platform");
            Line("Materials.Solid(platform): " + Describe(solid)
                + (solid != null ? " shader=" + Describe(solid.shader) : ""));
            // What the CC0 sets of PRD_VISUAL appendix C.11 became in THIS
            // player, which is the only place the question can be answered. A
            // material whose _BaseMap came back null still draws: it draws the
            // flat palette color the game had before Tier 2, so the failure
            // reads as "the textures were not worth it" rather than as an
            // absent asset. Textures live under Resources for the same reason
            // the shaders live in Always Included Shaders, and this line is the
            // proof that the reason worked.
            Line("platform surface: " + DescribeSurface(solid));
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

            DumpMarkers();

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

        /// <summary>
        /// The census V-PROP-06 needs, and the only witness its failure has.
        ///
        /// The item hides the physical marker slab and draws a DecalProjector in
        /// its place, so the two counts are unremarkable apart and damning
        /// together: slabs hidden with ZERO decals in the level means nothing is
        /// drawn where the player is meant to stand, and the level has lost the
        /// only thing that tells them. Every test still passes. The design audit
        /// still finds its markers, because it reads level DATA and the data is
        /// untouched (the marker is a decor slab and stays one).
        ///
        /// The failure mode is real and silent. The Decal Renderer Feature lives
        /// in PC_Renderer.asset as text YAML, and a feature whose m_Script guid
        /// does not resolve is DROPPED by Unity on load without a word: no
        /// exception, no warning, no null anywhere in code. Printing both numbers
        /// is what lets verify-player.ps1 fail on it.
        ///
        /// "Hidden" is measured on the RENDERERS and not read off
        /// ErasableBlock.ShowMesh, because a slab can leave the picture in more
        /// ways than that one property (a disabled renderer, a deactivated visual
        /// child, a material dropped) and every one of them costs the marker just
        /// the same. Slabs that are inactive in the hierarchy are not counted at
        /// all: a block is inactive because the rewind is holding it, which is
        /// not a hidden marker.
        /// </summary>
        void DumpMarkers()
        {
            var projectors = new List<DecalProjector>();
            _main.LevelRoot.GetComponentsInChildren(true, projectors);

            // Split out so a level whose decals are all pickup halos cannot read
            // as a level whose markers are drawn (V-VFX's contact shadow puts one
            // projector under each hovering pickup).
            //
            // TWO REASONS this walks the level tree instead of the groups, and
            // both of them inflate "painted" (decals - halos), which is the
            // number verify-player.ps1 turns red on. Over-count it and the check
            // reports OK on precisely the build it exists to catch.
            //
            //   1. THE CAMERA IS A PICKUP TOO. LevelBuilder.AddCamera puts a
            //      halo under each CameraItem exactly as it does for photos and
            //      batteries, and counting only PhotoItem and Battery left that
            //      projector on the marker side of the subtraction.
            //   2. GROUPS HOLD ONLY LIVE MEMBERS. Groups.Snapshot returns what
            //      is registered between OnEnable and OnDisable, while the
            //      projector total above is GetComponentsInChildren(true) and so
            //      includes the inactive. A Rewind.Retire moves a collected
            //      pickup to the graveyard rather than destroying it, so its
            //      halo keeps counting in the total and stops counting here: the
            //      two figures have to be read off the same tree or a rewind
            //      alone would make a healthy level look unpainted.
            var pickups = new List<Component>();
            var photos = new List<PhotoItem>();
            _main.LevelRoot.GetComponentsInChildren(true, photos);
            pickups.AddRange(photos);
            var batteries = new List<Battery>();
            _main.LevelRoot.GetComponentsInChildren(true, batteries);
            pickups.AddRange(batteries);
            var cameras = new List<CameraItem>();
            _main.LevelRoot.GetComponentsInChildren(true, cameras);
            pickups.AddRange(cameras);

            var halos = 0;
            for (int i = 0; i < pickups.Count; i++)
            {
                halos += CountDecals(pickups[i].transform);
            }

            var blocks = new List<ErasableBlock>();
            _main.LevelRoot.GetComponentsInChildren(true, blocks);
            var slabs = 0;
            var hidden = 0;
            foreach (ErasableBlock block in blocks)
            {
                if (!IsMarkerColor(block.ColorKey) || !block.gameObject.activeInHierarchy)
                {
                    continue;
                }
                slabs++;
                if (!DrawsAnything(block.transform))
                {
                    hidden++;
                }
            }

            Line("markers: slabs=" + slabs + " hidden=" + hidden
                + " decals=" + projectors.Count + " halos=" + halos);
        }

        static int CountDecals(Transform t)
        {
            var projectors = new List<DecalProjector>();
            t.GetComponentsInChildren(true, projectors);
            return projectors.Count;
        }

        /// <summary>
        /// Whether anything under this transform reaches the screen. Four ways
        /// it does not, and each of them is a way a marker slab can be taken out
        /// of the picture: the object is inactive, the renderer is disabled, the
        /// renderer has forceRenderingOff, or it has no material. All four are
        /// tested because hiding the slab is somebody else's code and any of
        /// them would be a reasonable way to write it.
        /// </summary>
        static bool DrawsAnything(Transform t)
        {
            var renderers = new List<Renderer>();
            t.GetComponentsInChildren(true, renderers);
            foreach (Renderer r in renderers)
            {
                if (r.enabled && !r.forceRenderingOff
                    && r.gameObject.activeInHierarchy && r.sharedMaterial != null)
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>
        /// The palette keys the level data gives a placement marker. They are
        /// the four keys Materials.cs maps to its Marker style (flat, saturated,
        /// untextured paint), and the reason this is a list of keys rather than a
        /// group lookup is that a marker is decor in the data and nothing about
        /// that changes for V-PROP-06.
        /// </summary>
        static bool IsMarkerColor(string key)
        {
            return key == "teal" || key == "teal_dark"
                || key == "accent" || key == "accent_dark";
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

        /// <summary>
        /// The STATE of the feedback systems of PRD_VISUAL 4.8 and 4.9, and the
        /// one line that would catch this tier's worst regression.
        ///
        /// Every item in this tier is an ANIMATION, and an animation that never
        /// runs looks exactly like an animation nobody has written yet. A
        /// screenshot cannot tell those apart (both show a still world), and
        /// neither can a test that only asks whether the effect's object was
        /// created. So this reports what the systems ARE - how many particle
        /// systems the level carries and whether they are alive, which volumes
        /// are stacked and in what order, whether the camera even opts into
        /// post-processing - and leaves the pictures to say what they look like.
        ///
        /// The volumes are printed with their priorities because of appendix
        /// C.5: two default profiles apply and the SECOND one wins, which is how
        /// a correctly authored bloom spent a whole round being overwritten with
        /// no error anywhere. The camera line is appendix C.6, the most
        /// expensive discovery of Tier 0: with renderPostProcessing false, every
        /// post value in every profile is inert and nothing says so.
        ///
        /// THE PLACER LINE IS THE IMPORTANT ONE. The photo placer is a child of
        /// the camera at an identity local transform, and that alone is what
        /// makes the camera pose BE the placement anchor (gameplay PRD 6.4).
        /// V-ANIM-01 adds head bob, a landing dip and a sprint FOV to that same
        /// camera transform, which is correct and wanted (the bob rides into the
        /// anchor exactly as it already does in the viewfinder), but the first
        /// tempting way to write any of it is to offset the CHILD instead. That
        /// would break the game's central illusion - what you framed is no
        /// longer what you place - while crashing nothing, blackening no frame
        /// and failing no test that does not look. Printing the local transform
        /// is what makes it visible.
        /// </summary>
        void DumpFeedback()
        {
            Line("--- feedback ---");

            var systems = new List<ParticleSystem>();
            _main.LevelRoot.GetComponentsInChildren(true, systems);
            var playing = 0;
            var emitting = 0;
            var alive = 0;
            foreach (ParticleSystem ps in systems)
            {
                if (ps.isPlaying)
                {
                    playing++;
                }
                if (ps.isEmitting)
                {
                    emitting++;
                }
                alive += ps.particleCount;
            }
            // "alive" is reported and never asserted on: a sparse field with a
            // 12 s life legitimately reads zero for its first fraction of a
            // second, and an emitter that is deliberately idle (the teleporter
            // column before the ring is charged) reads zero for the whole level.
            Line("particles: systems=" + systems.Count + " playing=" + playing
                + " emitting=" + emitting + " alive=" + alive);

            Volume[] volumes = FindObjectsByType<Volume>(
                FindObjectsInactive.Include, FindObjectsSortMode.None);
            Line("volumes: " + volumes.Length);
            foreach (Volume volume in volumes)
            {
                VolumeProfile profile = volume.sharedProfile;
                Line("  volume[" + volume.name + "] priority=" + Num1(volume.priority)
                    + " global=" + volume.isGlobal
                    + " weight=" + Num2(volume.weight)
                    + " enabled=" + volume.isActiveAndEnabled
                    + " profile=" + Describe(profile)
                    + " overrides=" + (profile != null ? profile.components.Count : 0));
            }

            // Found by TYPE NAME rather than by reference on purpose. The post
            // component of this tier belongs to another file and may not exist
            // yet; a compile-time reference would make this probe refuse to
            // build until it does, and a probe that does not compile reports
            // nothing at all about anything else.
            var posts = 0;
            MonoBehaviour[] behaviours = FindObjectsByType<MonoBehaviour>(
                FindObjectsInactive.Include, FindObjectsSortMode.None);
            foreach (MonoBehaviour behaviour in behaviours)
            {
                string type = behaviour.GetType().Name;
                if (!type.Contains("Post") && !type.Contains("Fx"))
                {
                    continue;
                }
                posts++;
                Line("post component: " + type + " on " + behaviour.gameObject.name
                    + " enabled=" + behaviour.enabled
                    + " active=" + behaviour.isActiveAndEnabled);
            }
            if (posts == 0)
            {
                Line("post component: NONE (no MonoBehaviour type name carries \"Post\" or \"Fx\")");
            }

            Camera cam = _main.Player.Camera;
            if (cam == null)
            {
                Line("post on camera: NO CAMERA");
                Line("camera fov: NO CAMERA");
            }
            else
            {
                UniversalAdditionalCameraData data = cam.GetComponent<UniversalAdditionalCameraData>();
                Line("post on camera: " + (data == null
                    ? "NO UniversalAdditionalCameraData (nothing post-processes, appendix C.6)"
                    : "renderPostProcessing=" + data.renderPostProcessing
                        + " antialiasing=" + data.antialiasing
                        + " quality=" + data.antialiasingQuality));
                // V-ANIM-01 widens this by two degrees while sprinting, so the
                // base is printed beside it: a fov stuck at 77 (or eased and
                // never returned) is a frame that no longer matches the square
                // the HUD derives from CameraFov.
                Line("camera fov: " + Num2(cam.fieldOfView)
                    + " (base " + Num2(PlayerController.CameraFov) + ")");
            }

            DumpPlacer();
        }

        /// <summary>
        /// The placement anchor, measured rather than trusted.
        ///
        /// The roll is NOT drift: PhotoPlacer applies the wheel's quarter turns
        /// to this very object, deliberately, so that the anchor turns with the
        /// picture the HUD shows. The comparison is therefore against
        /// PhotoPlacer.RollRotation(RollSteps), read from the placer's own
        /// derivation instead of recopied here - the sign of that rotation is
        /// argued for at length in PhotoPlacer and is exactly the kind of thing
        /// a second copy gets wrong.
        /// </summary>
        void DumpPlacer()
        {
            PhotoPlacer placer = _main.Player.Placer;
            if (placer == null)
            {
                Line("placer anchor: NO PLACER");
                return;
            }
            Transform t = placer.transform;
            Vector3 pos = t.localPosition;
            Quaternion rot = t.localRotation;
            Vector3 scale = t.localScale;
            float drift = Quaternion.Angle(rot, PhotoPlacer.RollRotation(placer.RollSteps));
            Line("placer anchor: parent=" + (t.parent != null ? t.parent.name : "NONE")
                + " local pos (" + Num3(pos.x) + ", " + Num3(pos.y) + ", " + Num3(pos.z) + ")"
                + " offset " + pos.magnitude.ToString("0.0000", CultureInfo.InvariantCulture) + " m"
                + " roll=" + placer.RollSteps
                + " local rot (" + Num3(rot.x) + ", " + Num3(rot.y) + ", "
                + Num3(rot.z) + ", " + Num3(rot.w) + ")"
                + " drift " + Num3(drift) + " deg"
                + " scale (" + Num3(scale.x) + ", " + Num3(scale.y) + ", " + Num3(scale.z) + ")");
        }

        // ---- Helpers --------------------------------------------------------

        /// <summary>
        /// Invariant culture on every number this dump adds, so the script that
        /// reads them back needs no repair. A player started on a French machine
        /// writes "0,000" otherwise: the eye-height line predates the rule and
        /// verify-player.ps1 un-commas it by hand, which is a patch nothing new
        /// should need.
        /// </summary>
        static string Num1(float value)
        {
            return value.ToString("0.0", CultureInfo.InvariantCulture);
        }

        static string Num2(float value)
        {
            return value.ToString("0.00", CultureInfo.InvariantCulture);
        }

        static string Num3(float value)
        {
            return value.ToString("0.000", CultureInfo.InvariantCulture);
        }

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

        /// <summary>
        /// The style, the seed and the two maps of a Viewpoint/Surface material,
        /// in the one shape verify-player.ps1 parses.
        ///
        /// Every read is guarded by HasFloat / HasTexture rather than tried and
        /// caught: the backdrop, and anything still on URP Lit, carries none of
        /// these properties, and Unity logs an error per missing property. The
        /// distinction the guard buys is worth the lines: ABSENT means the
        /// material is not on the new shader at all, NULL means it is but the
        /// texture never arrived (stripped, or not under Resources), and those
        /// two failures are fixed in different files.
        ///
        /// Invariant culture on the numbers because a player started on a French
        /// machine writes "0,5" otherwise, and the script reads these back.
        /// </summary>
        static string DescribeSurface(Material material)
        {
            if (material == null)
            {
                return "NULL";
            }
            string style = material.HasFloat("_Style")
                ? material.GetFloat("_Style").ToString("0.##", CultureInfo.InvariantCulture)
                : "ABSENT";
            string seed = material.HasFloat("_Seed")
                ? material.GetFloat("_Seed").ToString("0.###", CultureInfo.InvariantCulture)
                : "ABSENT";
            return "_Style=" + style + " _Seed=" + seed
                + " _BaseMap=" + DescribeMap(material, "_BaseMap")
                + " _NormalMap=" + DescribeMap(material, "_NormalMap");
        }

        /// <summary>
        /// A texture slot as "name WxH", or why it is not one. The size is part
        /// of the report because a 1 x 1 placeholder resolves, samples and looks
        /// exactly like the flat color it replaced.
        /// </summary>
        static string DescribeMap(Material material, string property)
        {
            if (!material.HasTexture(property))
            {
                return "ABSENT";
            }
            Texture texture = material.GetTexture(property);
            return texture == null
                ? "NULL"
                : texture.name + " " + texture.width + "x" + texture.height;
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
