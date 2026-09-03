using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Viewpoint
{
    /// <summary>
    /// Offscreen renderer of the polaroid pictures (PRD 6.9 and 15.6).
    ///
    /// For each photo definition the studio builds the DISPLAY variant of the
    /// content in a private corner of the world and renders it with a square
    /// camera whose fov, aspect and near plane are the ones of the PLACEMENT
    /// frustum. The picture on the polaroid is therefore the exact same view
    /// the solid content produces once placed, and that identity is what makes
    /// the raised picture (right click) blend into the world at the moment of
    /// placement. Any drift between this camera and PhotoMath breaks the trick.
    ///
    /// The studio degrades gracefully: while a render is pending, and for the
    /// whole life of a run with no rasterizer (-batchmode -nographics), the
    /// deterministic drawn thumbnail from PhotoDefs is served instead. That
    /// fallback carries the headless test harness, exactly as the original
    /// GDScript version carried it under --headless.
    /// </summary>
    public sealed class PhotoSnaps : MonoBehaviour
    {
        /// Square render size, and the polaroid border in pixels: 24 on the
        /// left, right and top, 48 at the bottom (PRD 6.9).
        public const int SnapSize = 512;
        public const int Border = 24;
        public const int BottomBorder = 48;

        /// The studio sits far under the world (PRD 15.6). The PhotoStudio
        /// layer already keeps the studio and the level invisible to each
        /// other's camera; the distance is belt and braces, so that no level
        /// ever shares the volume and no stray shadow or reflection mixes them.
        public static readonly Vector3 StudioOrigin = new Vector3(0f, -500f, 0f);

        const float CameraNear = 0.05f;

        /// Far enough for the deepest painted backdrop in the catalog (36 m for
        /// a shot, 28.5 m for `passerelle`) with room to spare.
        const float CameraFar = 500f;

        /// PRD 14.5: the studio has its OWN sun, close to the level's but not
        /// the same one. It is pitched 40 deg down where the level sun is at 45
        /// (PRD 14.3), and it casts no shadow. The yaw is the mirrored value the
        /// PRD already spells out as a Unity Euler, so it is copied, not derived.
        static readonly Vector3 SunEuler = new Vector3(40f, -30f, 0f);
        static readonly Color SunColor = new Color(1f, 0.96f, 0.88f);
        const float SunIntensity = 1.15f;

        static PhotoSnaps _instance;

        readonly Dictionary<string, Texture2D> _cache = new Dictionary<string, Texture2D>();
        readonly List<string> _queue = new List<string>();

        Camera _camera;
        Transform _contentRoot;
        RenderTexture _target;
        GameObject _current;
        WaitForEndOfFrame _endOfFrame;
        bool _ready;
        bool _draining;

        /// <summary>The rendered snap when it is ready, the computed thumbnail otherwise.</summary>
        public static Texture2D GetTexture(string id)
        {
            if (_instance != null && !string.IsNullOrEmpty(id))
            {
                Texture2D snap;
                if (_instance._cache.TryGetValue(id, out snap) && snap != null)
                {
                    return snap;
                }
            }
            return PhotoDefs.Thumbnail(id);
        }

        /// <summary>Queues a render. Silently ignored when there is no studio (headless).</summary>
        public static void Request(string id)
        {
            if (_instance != null)
            {
                _instance.Enqueue(id);
            }
        }

        void Awake()
        {
            if (_instance != null && _instance != this)
            {
                Debug.LogWarning("PhotoSnaps: a studio already exists, this one stays idle.");
                enabled = false;
                return;
            }
            _instance = this;
            _endOfFrame = new WaitForEndOfFrame();

            // No rasterizer means no pixels to read back: the studio does
            // nothing at all and GetTexture keeps serving thumbnails.
            if (SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null)
            {
                return;
            }

            BuildStudio();
            _ready = true;
        }

        void Start()
        {
            if (!_ready)
            {
                return;
            }
            // The whole static catalog is queued at boot so a photo item picked
            // up in the first seconds already shows its real picture. Shots
            // taken in game queue themselves through Request at shutter time.
            string[] ids = PhotoDefs.AllIds();
            if (ids == null)
            {
                return;
            }
            for (int i = 0; i < ids.Length; i++)
            {
                Enqueue(ids[i]);
            }
        }

        void OnDestroy()
        {
            if (_instance == this)
            {
                _instance = null;
            }
            ClearContent();
            if (_camera != null)
            {
                _camera.targetTexture = null;
            }
            if (_target != null)
            {
                _target.Release();
                Destroy(_target);
                _target = null;
            }
            foreach (KeyValuePair<string, Texture2D> entry in _cache)
            {
                if (entry.Value != null)
                {
                    Destroy(entry.Value);
                }
            }
            _cache.Clear();
            _queue.Clear();
        }

        void BuildStudio()
        {
            transform.position = StudioOrigin;
            transform.rotation = Quaternion.identity;
            gameObject.layer = Layers.PhotoStudio;

            // 24 bits of depth: the studio renders real 3D props, a colour only
            // target would sort them by draw order. sRGB read/write (the default
            // for ARGB32 in a linear project) keeps the read back bytes encoded
            // the same way the computed thumbnail paints its own.
            _target = new RenderTexture(SnapSize, SnapSize, 24, RenderTextureFormat.ARGB32);
            _target.name = "PhotoSnapTarget";
            _target.filterMode = FilterMode.Bilinear;
            _target.wrapMode = TextureWrapMode.Clamp;
            _target.Create();

            GameObject cameraObject = new GameObject("SnapCamera");
            cameraObject.transform.SetParent(transform, false);
            cameraObject.layer = Layers.PhotoStudio;
            _camera = cameraObject.AddComponent<Camera>();
            _camera.orthographic = false;
            // The frustum of the placement, to the digit: see the class summary.
            _camera.fieldOfView = PhotoMath.PhotoFovDeg;
            _camera.nearClipPlane = CameraNear;
            _camera.farClipPlane = CameraFar;
            _camera.cullingMask = Layers.PhotoStudioMask;
            _camera.clearFlags = CameraClearFlags.Skybox;
            // Falls back to a flat horizon colour if no skybox material is set
            // yet: the camera resolves RenderSettings.skybox at render time, so
            // the game's gradient sky is picked up whenever the environment
            // installs it, even after this studio was built.
            _camera.backgroundColor = Palette.Get("sky_horizon");
            _camera.allowHDR = false; // the read back is plain LDR bytes
            _camera.allowMSAA = false;
            _camera.useOcclusionCulling = false;
            _camera.targetTexture = _target;
            // Assigning a target texture derives the aspect from it; forcing it
            // makes the square framing independent of the target for good.
            _camera.aspect = PhotoMath.PhotoAspect;
            _camera.enabled = false;

            GameObject sunObject = new GameObject("SnapSun");
            sunObject.transform.SetParent(transform, false);
            sunObject.transform.localRotation = Quaternion.Euler(SunEuler);
            sunObject.layer = Layers.PhotoStudio;
            Light sun = sunObject.AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.color = SunColor;
            sun.intensity = SunIntensity;
            sun.shadows = LightShadows.None; // as in the original studio
            // Camera level exclusion: a light sharing no layer with a camera's
            // culling mask is dropped at culling time, so this sun never
            // touches the level and the level's sun must in turn exclude the
            // PhotoStudio layer. (Per object light masks would need URP
            // rendering layers; this coarser exclusion needs nothing.)
            sun.cullingMask = Layers.PhotoStudioMask;

            // The sun is the only piece of the original studio environment that
            // survives the port. PRD 14.5 also wants a brighter ambient here
            // (Godot: sky contribution 0.7 and energy 1.1, against 0.5 and 0.8
            // in the level), and the original studio carried no fog while the
            // level does. Unity keeps both in RenderSettings, which is global:
            // neither can be given to this camera alone, so the level's values
            // stand and the picture is a touch darker and hazier than Godot's.
            // PRD 16 rules that acceptable.

            GameObject contentObject = new GameObject("SnapContent");
            contentObject.transform.SetParent(transform, false);
            contentObject.layer = Layers.PhotoStudio;
            _contentRoot = contentObject.transform;
        }

        void Enqueue(string id)
        {
            if (!_ready || string.IsNullOrEmpty(id))
            {
                return;
            }
            if (_cache.ContainsKey(id) || _queue.Contains(id))
            {
                return;
            }
            _queue.Add(id);
            if (!_draining)
            {
                StartCoroutine(Drain());
            }
        }

        IEnumerator Drain()
        {
            _draining = true;
            while (_queue.Count > 0)
            {
                string id = _queue[0];
                _queue.RemoveAt(0);
                yield return RenderOne(id);
            }
            _draining = false;
        }

        IEnumerator RenderOne(string id)
        {
            PhotoDef def = PhotoDefs.GetDef(id);
            if (def == null)
            {
                yield break;
            }

            ClearContent();
            _current = new GameObject("Snap_" + id);
            // Set BEFORE Setup, because a display mesh copies the layer of the
            // node it is built under: this alone already lands the whole content
            // on PhotoStudio, which is what PhotoContent counts on.
            _current.layer = Layers.PhotoStudio;
            _current.transform.SetParent(_contentRoot, false);
            PhotoContent content = _current.AddComponent<PhotoContent>();
            content.Setup(def, true);
            // Second pass in case a piece of content picked a layer of its own:
            // the snap camera culls everything but PhotoStudio, so one stray
            // mesh left on Default is a hole in the picture.
            SetLayerRecursive(_current.transform, Layers.PhotoStudio);

            _camera.enabled = true;
            // Two waits, as the original waited twice on frame_post_draw: the
            // first ends the frame the camera was switched on in, the second
            // guarantees a full render of the new content landed in the target.
            yield return null;
            yield return _endOfFrame;

            Texture2D snap = ReadBack();
            _camera.enabled = false;
            ClearContent();

            snap.name = "snap_" + id;
            _cache[id] = snap;
        }

        Texture2D ReadBack()
        {
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = _target;
            Texture2D snap = new Texture2D(SnapSize, SnapSize, TextureFormat.RGBA32, false);
            snap.ReadPixels(new Rect(0f, 0f, SnapSize, SnapSize), 0, 0, false);
            RenderTexture.active = previous;
            snap.wrapMode = TextureWrapMode.Clamp;
            snap.filterMode = FilterMode.Bilinear;
            PaintPolaroidBorder(snap);
            snap.Apply(false, false);
            return snap;
        }

        /// <summary>Paints the white polaroid border straight onto the render.</summary>
        static void PaintPolaroidBorder(Texture2D texture)
        {
            Color32 frame = Palette.Get("frame");
            Color32[] pixels = texture.GetPixels32();
            int width = texture.width;
            int height = texture.height;
            for (int y = 0; y < height; y++)
            {
                int rowStart = y * width;
                // Texture2D rows run BOTTOM up, so the wide 48 px band of the
                // polaroid (its bottom, where a caption would be written) is the
                // low rows and the 24 px band is the high ones. Godot's Image
                // had it the other way round.
                bool fullRow = y < BottomBorder || y >= height - Border;
                if (fullRow)
                {
                    for (int x = 0; x < width; x++)
                    {
                        pixels[rowStart + x] = frame;
                    }
                    continue;
                }
                for (int x = 0; x < Border; x++)
                {
                    pixels[rowStart + x] = frame;
                }
                for (int x = width - Border; x < width; x++)
                {
                    pixels[rowStart + x] = frame;
                }
            }
            texture.SetPixels32(pixels);
        }

        void ClearContent()
        {
            if (_current == null)
            {
                return;
            }
            // Studio content is not level content, so it is destroyed and not
            // retired: no rewind ever puts a picture set back. Destroy is
            // deferred to the end of the frame though, and the next snap must
            // not be rendered with the previous one still standing, so it is
            // deactivated at once as well.
            _current.SetActive(false);
            Destroy(_current);
            _current = null;
        }

        static void SetLayerRecursive(Transform root, int layer)
        {
            root.gameObject.layer = layer;
            for (int i = 0; i < root.childCount; i++)
            {
                SetLayerRecursive(root.GetChild(i), layer);
            }
        }
    }
}
