using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

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
    ///
    /// The studio owns as little of the LOOK as it possibly can, which is the
    /// same identity read from the other end (PRD_VISUAL 3.4 and V-SNAP-01):
    /// its sun's colour and intensity are copied from the world's sun before
    /// every render, its ambient and its fog are the world's by construction
    /// (RenderSettings is global), its materials are the world's shared ones,
    /// its sky is RenderSettings.skybox, and its camera renders the world's
    /// post-processing minus the vignette. All the studio keeps of its own is
    /// the 40 degree sun pitch PRD 14.5 asks for.
    ///
    /// The studio has a SECOND job since PRD_VISUAL 4.12 V-MENU-02: the level
    /// grid's thumbnails. Same principle, one step larger - instead of the
    /// display content of one photo it builds a WHOLE LEVEL in the same private
    /// corner, shoots it at 160 x 90 from the spawn the player would wake at,
    /// and tears it down. It is the same studio because it is the same promise:
    /// a thumbnail lit, graded and skied like the level it stands for is a
    /// picture of that level, and a thumbnail lit by anything else is a poster.
    /// See RequestLevelThumbnail, which is the whole of that half's public
    /// surface, and BuildThumbnailLevel, which says how a level can stand in the
    /// studio for two frames without the running game ever noticing.
    /// </summary>
    public sealed class PhotoSnaps : MonoBehaviour
    {
        /// Square render size, and the polaroid border in pixels: 24 on the
        /// left, right and top, 48 at the bottom (PRD 6.9).
        /// <summary>
        /// V-SNAP-03: raised from 512 to 768, so a raised picture shown at
        /// 547 px on a 900 px tall window is no longer upscaled. The render
        /// target also carries antiAliasing 4 from Tier 0's V-PIPE-01 fix.
        ///
        /// Memory: a 768 square ARGB32 readback is 2.25 MB against 1.0 MB at
        /// 512, and the catalogue holds 8 photos, so the cache grows from 8 MB
        /// to 18 MB. Affordable, and stated here rather than discovered later.
        /// </summary>
        public const int SnapSize = 768;

        /// <summary>
        /// The polaroid border, in pixels: 24 on the left, right and top and 48
        /// at the bottom AT 512 (PRD 6.9). What that section actually pins is
        /// the RATIO, not the pixel counts, so both are now DERIVED from
        /// SnapSize instead of written out.
        ///
        /// That matters because PaintPolaroidPrint paints these straight onto
        /// the readback: raising SnapSize while leaving them at 24 and 48 would
        /// have made the frame visibly thinner and, worse, would have put the
        /// picture's proportions out of step with the physical polaroid mesh
        /// that V-PROP-02 builds to the same ratio. Derived, the two cannot
        /// drift apart again.
        ///
        /// 768 * 24 / 512 = 36 and 768 * 48 / 512 = 72, both exact, so the
        /// ratio is preserved to the pixel rather than to a rounding.
        /// </summary>
        public const int Border = (SnapSize * 24) / 512;
        public const int BottomBorder = (SnapSize * 48) / 512;

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
        ///
        /// The ANGLE is the only thing about that sun the studio still decides.
        /// Its colour and its intensity are the world's, copied by SyncSunToWorld
        /// before every render (PRD_VISUAL V-SNAP-01): a picture is a promise
        /// about how the placed content will look, so a lighting change applied
        /// to the level and not here would make every polaroid lie. The two
        /// values below are the fallback for a studio with no world to copy, and
        /// they are the ones the studio owned before it read the world.
        static readonly Vector3 SunEuler = new Vector3(40f, -30f, 0f);
        // The PRE-upgrade key was (1, 0.96, 0.88) at 1.15. These now mirror what
        // SceneEnvironment actually builds (PRD_VISUAL V-LIGHT-01), so the one
        // path where no world sun is found lights the picture like the current
        // world rather than like the world of two tiers ago.
        static readonly Color FallbackSunColor = new Color(1f, 0.94f, 0.84f);
        const float FallbackSunIntensity = 1.3f;

        /// The volume layers the studio camera reads. Layer 0 (Default) is where
        /// every Volume this game builds at runtime lands, and it is the only
        /// layer the player camera reads too (nothing sets its volumeLayerMask,
        /// and URP's default is exactly this bit), so keeping it here is what
        /// makes the picture's grading the world's grading. PhotoStudio is added
        /// for the studio's own vignette veto, which no other camera can see.
        const int VolumeLayers = 1 | Layers.PhotoStudioMask;

        /// Side of the vignette veto's trigger box, in meters. URP decides a
        /// local volume applies by measuring the camera against the volume's
        /// colliders, and the studio camera sits at the exact centre of this one
        /// (see BuildVignetteVolume), so any positive side works: 8 m leaves the
        /// camera 4 m of margin in every direction should a later item move it
        /// about inside the studio.
        const float VolumeBoxSide = 8f;

        /// <summary>
        /// PRD_VISUAL V-PROP-03 (and V-SNAP-02, which points at it): the
        /// readback has to look PRINTED rather than rendered. Four numbers do
        /// it, and all four are TONE: not one of them moves a pixel, because
        /// the polaroid's whole job is that the picture IS the view the placed
        /// content will produce (gameplay PRD 6.9), and a player checks that by
        /// raising the print against the world. Resampling, rescaling, cropping
        /// or shifting by a single pixel would break the identity the game is
        /// built on; darkening a corner by 3 percent cannot.
        ///
        /// BlackLift is the paper's floor. A print has no black, only the
        /// darkest density its emulsion reaches, so the curve maps 0 to 0.02
        /// (5 levels of 255) and leaves 1 at exactly 1:
        ///
        ///     out = BlackLift + (1 - BlackLift) * in
        ///
        /// White being a FIXED POINT of that curve matters beyond taste: check
        /// 6.3's emissive isolation thresholds the graded frame at 0.98 and
        /// fails on any survivor outside an emissive's bounds, so a curve that
        /// lifted the top end could turn a raised polaroid into a bloom leak.
        /// This one cannot brighten any pixel that was not already there.
        ///
        /// VignetteStrength is the fall-off of the print itself and NOT the
        /// screen vignette: BuildVignetteVolume vetoes that one for the studio
        /// camera, on purpose, because a post vignette would double with the
        /// white frame and go muddy in the corners. 3 percent at the corner is
        /// an order of magnitude under the world's and reads as paper, not as a
        /// lens.
        /// </summary>
        const float BlackLift = 0.02f;
        const float VignetteStrength = 0.03f;

        /// <summary>
        /// The hairline chemical border: the 2 outermost pixels of the APERTURE
        /// go 15 percent darker, which is the denser line an instant print
        /// carries where the developer pooled against the mask.
        ///
        /// Inside the aperture and never into the border, as V-PROP-03 asks: the
        /// frame is the white paper of the physical polaroid mesh V-PROP-02
        /// builds to the same ratio, and eating 2 px of it would put the two out
        /// of step. So this darkens image pixels, which is a tone change on
        /// pixels that stay exactly where they were.
        /// </summary>
        const int HairlineWidth = 2;
        const float HairlineGain = 0.85f;

        /// <summary>
        /// Paper grain. GrainLevels is the amplitude in LEVELS OF 255, so the
        /// noise is uniform over -2..+2: sub-perceptual on any one pixel and
        /// visible as texture over a field of them, which is what V-PROP-03
        /// asks for ("faint"). Anything larger stops being paper and starts
        /// being a broken decode.
        ///
        /// GrainCell is why it survives being looked at. A raised picture is
        /// drawn at 547 px from this 768 px readback (V-SNAP-03), and bilinear
        /// minification averages roughly two source pixels per screen pixel,
        /// which would halve a per-pixel white noise of two levels into nothing.
        /// Hashing 2 x 2 blocks instead puts the grain's period above the
        /// sampling rate, so it reads at 1.4 px on screen and stays paper.
        ///
        /// One delta per pixel, shared by r, g and b. Three independent deltas
        /// would be CHROMA noise, which is the look of a bad sensor; paper grain
        /// is achromatic.
        /// </summary>
        const int GrainCell = 2;
        const int GrainLevels = 2;

        /// <summary>
        /// PRD_VISUAL 4.12 V-MENU-02: the level grid's thumbnail, at the size
        /// the item pins, 160 x 90. Sixteen by nine and not the square of a
        /// polaroid, because a level thumbnail is a view of the WORLD and the
        /// game is played in 16:9; Menu centre-crops whatever shape it gets into
        /// a 16:9 box, so a square readback would silently lose 44 percent of
        /// its height on the way to the button.
        ///
        /// Memory: 160 x 90 RGBA32 is 57.6 kB, so the whole cache of 25 is
        /// 1.4 MB against the 18 MB of the polaroid cache. Stated here rather
        /// than discovered later, like SnapSize's own figure above.
        /// </summary>
        public const int ThumbnailWidth = 160;
        public const int ThumbnailHeight = 90;

        /// <summary>
        /// The budget V-MENU-02 accepts for the whole grid: "building all 25 for
        /// thumbnails takes under 2 s in total at first launch". It is not a
        /// throttle, it is a MEASUREMENT threshold: see ReportThumbnailBudget,
        /// which times what was actually built and says in the player log
        /// whether the full grid would fit. A budget nobody measures is a
        /// sentence in a document, and this project has learned what those cost.
        /// </summary>
        const float ThumbnailBudgetSeconds = 2f;

        /// <summary>
        /// The volume layers a thumbnail camera reads: layer 0 (Default) and
        /// nothing else.
        ///
        /// Deliberately NOT the studio's VolumeLayers. The vignette veto of
        /// BuildVignetteVolume exists because a post vignette doubles with the
        /// white polaroid frame, and a level thumbnail has no frame: it is a
        /// small window on the world and it should be graded exactly as the
        /// world is, vignette included. Worse, that veto is a LOCAL volume in an
        /// 8 m box at the studio origin, while a thumbnail camera stands at the
        /// level's spawn, which is a different distance away in every level - so
        /// reading the PhotoStudio layer here would hand the veto to some levels
        /// and not to others, which is the kind of difference nobody could ever
        /// explain from the pictures.
        /// </summary>
        const int ThumbnailVolumeLayers = 1;

        /// <summary>
        /// Every group a level's components join, so that a level built for a
        /// thumbnail can be taken straight back out of them (see ScrubGroups).
        ///
        /// The CONSTANTS and never the literals, so a rename in Groups follows
        /// here instead of leaving a string that matches nothing. The known
        /// maintenance cost is that a NEW group would have to be added to this
        /// list too; the follow-up that removes the cost for good is a
        /// Groups.RemoveAll(Component), which lives in a file this pass does not
        /// own.
        /// </summary>
        static readonly string[] LevelGroups =
        {
            Groups.Photographable,
            Groups.Carvable,
            Groups.Breakable,
            Groups.Cage,
            Groups.Erasable,
            Groups.Platform,
            Groups.PlacedContent,
            Groups.PhotoItem,
            Groups.Battery,
            Groups.CopyableBattery,
            Groups.CameraItem,
            Groups.Teleporter,
        };

        static PhotoSnaps _instance;

        readonly Dictionary<string, Texture2D> _cache = new Dictionary<string, Texture2D>();
        readonly List<string> _queue = new List<string>();

        /// The level thumbnails of V-MENU-02, and the levels still waiting for
        /// one. Keyed by the zero based level index the menu speaks in, and kept
        /// for the whole life of this studio, which is the whole life of the
        /// run: the item asks for the result to be "cached for the session" and
        /// Main builds exactly one PhotoSnaps at boot and never replaces it.
        readonly Dictionary<int, Texture2D> _levelCache = new Dictionary<int, Texture2D>();
        readonly List<int> _levelQueue = new List<int>();

        /// Reused by ScrubGroups so that twenty-five sweeps allocate one list.
        readonly List<MonoBehaviour> _scrubBuffer = new List<MonoBehaviour>();

        Camera _camera;
        Light _sun;
        Volume _vignetteVolume;
        VolumeProfile _vignetteProfile;

        /// The world sun found last time, kept so the search is not redone for
        /// every snap of the boot queue. Unity's == reports a destroyed object as
        /// null, so a sun that is rebuilt mid run drops out of here by itself and
        /// the next sync goes looking again.
        Light _worldSun;

        Transform _contentRoot;
        RenderTexture _target;
        GameObject _current;
        WaitForEndOfFrame _endOfFrame;
        bool _ready;
        bool _draining;

        /// The second camera and the second target, for the level thumbnails.
        /// Built on the first request rather than in BuildStudio: every run has
        /// a studio, only some runs open the level grid, and the polaroid path
        /// is left exactly as it was rather than having its camera borrowed and
        /// handed back (a restore that goes wrong once leaves every polaroid
        /// framed like a level, which is the sort of coupling this file avoids).
        Camera _levelCamera;
        RenderTexture _levelTarget;

        /// Set once a thumbnail render has thrown: the grid then stays text
        /// only for the rest of the run rather than trying the same broken
        /// build twenty-five times, and the polaroids carry on regardless.
        bool _levelThumbnailsOff;

        /// What ReportThumbnailBudget measures. _levelWork is the time spent
        /// INSIDE this class (building the level, reading the pixels back,
        /// tearing it down); _levelWall is the clock the player experiences,
        /// which also contains the two frames every shot has to wait for.
        ///
        /// The wall clock is summed SHOT BY SHOT rather than taken from the
        /// first shot to the last. A player who opens the grid, plays for ten
        /// minutes and opens it again would otherwise have those ten idle
        /// minutes counted as the cost of two pictures, and the budget line
        /// below would report a catastrophe that never happened.
        int _levelShots;
        float _levelShotStart;
        float _levelWallSeconds;
        float _levelWorkSeconds;

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

        /// <summary>
        /// The thumbnail of one level for the grid of PRD_VISUAL 4.12
        /// V-MENU-02, by its zero based index: the picture once it exists, null
        /// while it does not, and a render queued the first time it is asked
        /// for. The name is the one the item pins.
        ///
        /// POLLING IS REQUESTING, which is what makes this one method enough.
        /// Menu binds this half of the item by reflection (appendix C.23: the
        /// two halves are two files, and a compile-time call to a method whose
        /// shape was still being written would take the whole game down if it
        /// slipped a round), and it accepts either a Get / Request pair or a
        /// single method that does both. A single method is the honest shape
        /// here: a caller that polls every frame until a picture arrives has
        /// already said everything a separate request would say.
        ///
        /// A caller may therefore call this every frame for every cell, and
        /// does. Nothing accumulates: the queue refuses duplicates and the cache
        /// answers straight away once a level has been shot.
        ///
        /// LOCKED LEVELS ARE NOT PRE-WARMED, and that is a decision rather than
        /// an omission. The item says "cache 25 textures at first title screen",
        /// but the studio renders exactly what it is ASKED for, and the menu
        /// asks only for unlocked levels on purpose (a picture of a level the
        /// player has never reached is a spoiler nobody requested). Three
        /// reasons to leave it that way rather than pre-warm here:
        ///   - at a first launch only level 1 is unlocked, so pre-warming would
        ///     build twenty-four levels whose pictures are never drawn;
        ///   - the work would land on the one frame of the game the player is
        ///     watching an animation on, which is the very thing the menu's own
        ///     pacing avoids;
        ///   - the 2 s the item budgets is a budget for pictures the player
        ///     SEES, and it is measured either way (ReportThumbnailBudget times
        ///     what was built and projects the full twenty-five).
        /// A run that unlocks everything therefore ends up with all 25 cached
        /// for the session, which is the state the acceptance describes.
        ///
        /// Null is a supported answer forever: a headless run has no rasterizer
        /// and never builds a studio at all, and the grid it draws is the grid
        /// of before this tier (same strings, same twenty-five buttons).
        /// </summary>
        public static Texture2D RequestLevelThumbnail(int index)
        {
            if (_instance == null)
            {
                return null;
            }
            return _instance.LevelThumbnail(index);
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
            // The vignette veto's profile is made at runtime and belongs to
            // nobody else, so it is destroyed by hand like the target above. The
            // volume drops its reference first: were this component removed
            // without its object, a Volume left holding a destroyed profile would
            // still be handed to the volume manager every frame.
            if (_vignetteVolume != null)
            {
                _vignetteVolume.sharedProfile = null;
                _vignetteVolume = null;
            }
            if (_vignetteProfile != null)
            {
                Destroy(_vignetteProfile);
                _vignetteProfile = null;
            }
            // The thumbnail half, torn down exactly like the polaroid half
            // above: its camera lets its target go before the target is
            // released, and the pictures it read back belong to nobody else.
            if (_levelCamera != null)
            {
                _levelCamera.targetTexture = null;
            }
            if (_levelTarget != null)
            {
                _levelTarget.Release();
                Destroy(_levelTarget);
                _levelTarget = null;
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
            foreach (KeyValuePair<int, Texture2D> level in _levelCache)
            {
                if (level.Value != null)
                {
                    Destroy(level.Value);
                }
            }
            _levelCache.Clear();
            _levelQueue.Clear();
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
            // The studio half of PRD_VISUAL V-PIPE-01, and it has to be set HERE
            // rather than on the camera: for a camera that renders to a target,
            // URP takes the sample count from the TARGET TEXTURE and ignores the
            // pipeline asset's m_MSAA entirely. So a studio left at the default
            // renders every polaroid with the aliased edges the world has just
            // stopped having, and the picture stops matching the world it
            // promises (PRD_VISUAL 3.4). Four to match PC_RPAsset's m_MSAA: 4.
            _target.antiAliasing = 4;
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
            // HDR on, and the read back is STILL plain LDR bytes. Bloom's
            // threshold sits above 1.0 (PRD_VISUAL V-POST-01) and HDR grading
            // works above 1 too, so an LDR camera target would clamp every
            // emissive to white before post ever saw it and no battery would ever
            // glow on a polaroid. With HDR on, URP renders and grades into a
            // floating point intermediate and resolves that into this ARGB32
            // target at the end of the frame, so ReadBack still reads 8 bit sRGB
            // bytes in the same layout PaintPolaroidPrint writes into. The flag
            // is only a request: it does nothing unless the render pipeline asset
            // supports HDR, which PC_RPAsset does (m_SupportsHDR: 1).
            _camera.allowHDR = true;
            // Was false, and it had to change with the antiAliasing: 4 on the
            // target above: allowMSAA is an opt-OUT, so leaving it false would
            // have thrown away the multisampled target this studio now allocates
            // and kept the polaroid aliased anyway.
            _camera.allowMSAA = true;
            _camera.useOcclusionCulling = false;
            _camera.targetTexture = _target;
            // Assigning a target texture derives the aspect from it; forcing it
            // makes the square framing independent of the target for good.
            _camera.aspect = PhotoMath.PhotoAspect;
            _camera.enabled = false;

            // Post-processing, so the picture is graded like the world it
            // promises (PRD_VISUAL 3.4 and V-SNAP-01). Nothing else is needed to
            // get it: the ambient occlusion is a renderer feature on PC_Renderer,
            // which this camera uses because it overrides no renderer, and bloom,
            // tonemapping and colour adjustments live in the URP default volume
            // profile and in the pipeline asset's own profile, which are the base
            // of EVERY camera's volume stack whatever its layer mask. renderType
            // is left at Base on purpose: this is not an overlay, it renders a
            // frame of its own into a texture.
            UniversalAdditionalCameraData cameraData = _camera.GetUniversalAdditionalCameraData();
            cameraData.renderPostProcessing = true;
            cameraData.volumeLayerMask = VolumeLayers;
            // Which point URP measures against a local volume's colliders. It
            // already defaults to the camera transform; naming it makes the box
            // in BuildVignetteVolume verifiable by reading the code instead of by
            // trusting a default.
            cameraData.volumeTrigger = _camera.transform;

            BuildVignetteVolume();

            GameObject sunObject = new GameObject("SnapSun");
            sunObject.transform.SetParent(transform, false);
            sunObject.transform.localRotation = Quaternion.Euler(SunEuler);
            sunObject.layer = Layers.PhotoStudio;
            _sun = sunObject.AddComponent<Light>();
            _sun.type = LightType.Directional;
            _sun.shadows = LightShadows.None; // as in the original studio
            // Camera level exclusion: a light sharing no layer with a camera's
            // culling mask is dropped at culling time, so this sun never
            // touches the level and the level's sun must in turn exclude the
            // PhotoStudio layer. (Per object light masks would need URP
            // rendering layers; this coarser exclusion needs nothing.)
            _sun.cullingMask = Layers.PhotoStudioMask;
            // Colour and intensity are deliberately NOT written here: they belong
            // to the world's sun. This first copy leaves the studio right for
            // anyone who reads it before a render, and RenderOne copies again for
            // every snap.
            SyncSunToWorld();

            // The sun is the only piece of the original studio environment that
            // survives the port, and it is now the only one that needs code:
            // ambient and fog are the other half of the identity and Unity hands
            // them over for free. RenderSettings is global, so the studio
            // breathes the very ambient and fog the level does and cannot drift
            // from them, which is exactly what PRD_VISUAL V-SNAP-01 asks of it.
            //
            // What that same sharing costs is the one deviation from Godot the
            // port accepted: PRD 14.5 wanted a BRIGHTER ambient in the studio
            // (Godot sky contribution 0.7 and energy 1.1, against 0.5 and 0.8 in
            // the level) and no fog at all, and neither can be given to a single
            // camera in Unity. The level's values stand, so the picture is a
            // touch darker and hazier than Godot's. PRD 16 rules that
            // acceptable, and matching THIS world matters more than matching the
            // original's studio.

            GameObject contentObject = new GameObject("SnapContent");
            contentObject.transform.SetParent(transform, false);
            contentObject.layer = Layers.PhotoStudio;
            _contentRoot = contentObject.transform;
        }

        /// <summary>
        /// The studio's own Volume: everything the world's post-processing does,
        /// minus the vignette (PRD_VISUAL 3.4, V-POST-02 and appendix A). A
        /// vignette on the picture would double with the white polaroid frame
        /// PaintPolaroidPrint paints around it, and the corners of every photo
        /// would go muddy for no reason a player could read.
        ///
        /// It is a LOCAL volume and not a global one, because a global volume is
        /// seen by every camera whose layer mask contains its layer and this
        /// override must reach the studio camera alone. URP decides that a local
        /// volume applies by asking the volume's OWN colliders for the point
        /// closest to the camera, which has two consequences worth stating: the
        /// collider has to sit on this very object (a collider on a child is not
        /// read), and the camera has to be inside it. It is, by construction:
        /// this object and the SnapCamera are both children of this transform,
        /// both left at their parent's origin, so both stand at exactly
        /// StudioOrigin and the camera is dead centre of the box below.
        /// </summary>
        void BuildVignetteVolume()
        {
            GameObject volumeObject = new GameObject("SnapVignetteVeto");
            volumeObject.transform.SetParent(transform, false);
            // Set BEFORE the Volume component is added, as everywhere else in
            // this studio: a Volume registers itself with the volume manager
            // under the layer its object carries when it is enabled, and the
            // camera above reads PhotoStudio and Default and nothing else.
            volumeObject.layer = Layers.PhotoStudio;

            BoxCollider box = volumeObject.AddComponent<BoxCollider>();
            box.center = Vector3.zero;
            box.size = Vector3.one * VolumeBoxSide;
            // A trigger, on a layer the collision matrix pairs with nothing
            // (PRD 15.3): this box exists to be measured against a camera
            // position, never to be touched. A solid one would be an invisible
            // floor hanging 500 m under the level.
            box.isTrigger = true;

            _vignetteProfile = ScriptableObject.CreateInstance<VolumeProfile>();
            _vignetteProfile.name = "SnapVignetteVeto";
            // Added with no overrides, then one parameter overridden: the studio
            // keeps the world's vignette colour, centre and smoothness (at
            // intensity 0 it never sees them), so a later change to those in the
            // default profile does not have to be repeated here.
            Vignette vignette = _vignetteProfile.Add<Vignette>(false);
            vignette.active = true;
            vignette.intensity.overrideState = true;
            vignette.intensity.value = 0f;

            _vignetteVolume = volumeObject.AddComponent<Volume>();
            _vignetteVolume.isGlobal = false;
            _vignetteVolume.priority = 5f;
            // No blend distance: half a vignette on a picture is still a vignette
            // on a picture. Inside the box the override lands whole, and outside
            // it there is no studio camera to speak of.
            _vignetteVolume.blendDistance = 0f;
            _vignetteVolume.weight = 1f;
            _vignetteVolume.sharedProfile = _vignetteProfile;
        }

        /// <summary>
        /// Copies the world sun's colour and intensity onto the studio's sun.
        ///
        /// The studio keeps its own 40 degree pitch, which PRD 14.5 asks for and
        /// which is therefore a documented difference rather than drift. What may
        /// never differ is the LIGHT itself: the polaroid IS the view the placed
        /// content will produce (PRD 6.9), so the picture has to be lit exactly
        /// as the level is (PRD_VISUAL V-SNAP-01).
        ///
        /// Called before every render rather than once at build time, for two
        /// reasons. The studio can exist before the world's sun does: Main builds
        /// the environment before the studio today, but nothing in this class may
        /// depend on that order, and a studio built with no sun at all must still
        /// render rather than throw. And a lighting change made mid run has to
        /// reach the NEXT picture, not the next boot.
        /// </summary>
        void SyncSunToWorld()
        {
            if (_sun == null)
            {
                return;
            }
            Light world = WorldSun();
            _sun.color = world != null ? world.color : FallbackSunColor;
            _sun.intensity = world != null ? world.intensity : FallbackSunIntensity;
        }

        /// <summary>
        /// The world's sun, or null when the world has none yet. Never returns
        /// one of the studio's own lights, which would make the sync a tautology.
        /// </summary>
        Light WorldSun()
        {
            if (IsWorldSun(_worldSun))
            {
                return _worldSun;
            }

            // RenderSettings.sun is the scene's DECLARED sun. Nothing declares
            // one today (SceneEnvironment builds a directional light and leaves
            // it at that), so this is normally null and the search below answers
            // instead; it is read first because whoever does set it means it.
            if (IsWorldSun(RenderSettings.sun))
            {
                _worldSun = RenderSettings.sun;
                return _worldSun;
            }

            // Otherwise the brightest directional light that is not the studio's,
            // which is the rule Unity itself uses to pick a sun when
            // RenderSettings.sun is empty. Brightest rather than first, because
            // FindObjectsByType promises no order and the same shot taken twice
            // must come out the same picture (PhotoCapture breaks its own ties
            // for exactly that reason).
            Light[] lights = FindObjectsByType<Light>(FindObjectsSortMode.None);
            Light best = null;
            for (int i = 0; i < lights.Length; i++)
            {
                Light candidate = lights[i];
                if (!IsWorldSun(candidate))
                {
                    continue;
                }
                if (best == null || candidate.intensity > best.intensity)
                {
                    best = candidate;
                }
            }
            _worldSun = best;
            return best;
        }

        /// <summary>
        /// A live directional light that belongs to the world and not to this
        /// studio. The layer is what tells the two apart, since every studio
        /// child is put on PhotoStudio; the parent test is the belt and braces,
        /// so that a studio child which somehow lost its layer still cannot be
        /// mistaken for the sun.
        /// </summary>
        bool IsWorldSun(Light light)
        {
            if (light == null || !light.enabled || !light.gameObject.activeInHierarchy)
            {
                return false;
            }
            if (light.type != LightType.Directional)
            {
                return false;
            }
            if (light.gameObject.layer == Layers.PhotoStudio)
            {
                return false;
            }
            return !light.transform.IsChildOf(transform);
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

        /// <summary>
        /// One queue walker for both kinds of picture, and never two.
        ///
        /// A polaroid and a level thumbnail share the sun, the sky, the ambient
        /// and the fog, and a second coroutine would be free to build a level
        /// into the studio in the middle of a polaroid's two frame exposure.
        /// Serial, that cannot happen: one picture is finished before the next
        /// is begun, whichever kind it is.
        ///
        /// Polaroids go first, always. A polaroid is the picture on an item the
        /// player is about to pick up (gameplay PRD 6.9) and a thumbnail is a
        /// decoration on a menu; a player who opens the grid mid run must not
        /// push the game's own pictures behind twenty-five level builds.
        /// </summary>
        IEnumerator Drain()
        {
            _draining = true;
            while (_queue.Count > 0 || _levelQueue.Count > 0)
            {
                if (_queue.Count > 0)
                {
                    string id = _queue[0];
                    _queue.RemoveAt(0);
                    yield return RenderOne(id);
                    continue;
                }
                int index = _levelQueue[0];
                _levelQueue.RemoveAt(0);
                yield return RenderLevelThumbnail(index);
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

            // The world's light, copied onto the studio's just before the
            // shutter: whatever the level's lighting has become since this studio
            // was built, the picture is lit by it (PRD_VISUAL V-SNAP-01).
            SyncSunToWorld();

            _camera.enabled = true;
            // Two waits, as the original waited twice on frame_post_draw: the
            // first ends the frame the camera was switched on in, the second
            // guarantees a full render of the new content landed in the target.
            yield return null;
            yield return _endOfFrame;

            // The id travels with the readback because the print finish is
            // hashed from it: see PaintPolaroidPrint.
            Texture2D snap = ReadBack(id);
            _camera.enabled = false;
            ClearContent();

            snap.name = "snap_" + id;
            _cache[id] = snap;
        }

        // ---- Level thumbnails (PRD_VISUAL 4.12 V-MENU-02) --------------------

        /// <summary>The cached thumbnail, or null with a render queued.</summary>
        Texture2D LevelThumbnail(int index)
        {
            Texture2D ready;
            // Unity's == reports a destroyed texture as null, so a cache entry
            // that somehow died is re-rendered rather than handed out as a hole.
            if (_levelCache.TryGetValue(index, out ready) && ready != null)
            {
                return ready;
            }
            EnqueueLevel(index);
            return null;
        }

        /// <summary>
        /// Queues one level. Silently ignored with no studio (headless), out of
        /// range, already rendered, already queued, or once a build has thrown.
        /// </summary>
        void EnqueueLevel(int index)
        {
            if (!_ready || _levelThumbnailsOff)
            {
                return;
            }
            if (index < 0 || index >= LevelDefs.Count)
            {
                return;
            }
            if (_levelCache.ContainsKey(index) || _levelQueue.Contains(index))
            {
                return;
            }
            _levelQueue.Add(index);
            if (!_draining)
            {
                StartCoroutine(Drain());
            }
        }

        /// <summary>
        /// One level thumbnail: build the level in the studio, shoot it from its
        /// own spawn, tear it down. That is the technique V-MENU-02 names, and
        /// the rhythm is RenderOne's: two waits, because the first ends the
        /// frame the camera was switched on in and the second guarantees a full
        /// render of the new content landed in the target.
        ///
        /// The two frames are also what makes the picture COMPLETE. A level's
        /// pieces build their visuals in Awake (the teleporter's pad, a battery's
        /// body) or in Start (a polaroid item's picture, a block's texture seed,
        /// which both need the position the builder gives them AFTER the object
        /// wakes), and Start only runs on the frame after the build. Shooting in
        /// the same frame would photograph a level with its polaroids missing.
        /// </summary>
        IEnumerator RenderLevelThumbnail(int index)
        {
            LevelDef def = LevelDefs.GetDef(index);
            if (def == null)
            {
                yield break;
            }

            float started = Time.realtimeSinceStartup;
            _levelShotStart = started;

            GameObject root = BuildThumbnailLevel(index, def);
            if (root == null)
            {
                yield break;
            }
            _levelWorkSeconds += Time.realtimeSinceStartup - started;

            yield return null;
            SettleThumbnailLevel(root);
            yield return _endOfFrame;

            FinishThumbnail(index, root);
        }

        /// <summary>
        /// The pass that has to happen AFTER the level's Start methods and
        /// before the shot: a second layering, and a second scrub.
        ///
        /// The layering is not belt and braces here, it is load bearing.
        /// PhotoItem builds its picture in Start and puts ITSELF back on the
        /// Interact layer while doing it (its trigger has to be found by the
        /// interaction ray in a real level), so a polaroid item laid on
        /// PhotoStudio at build time is back on Interact by the time the shutter
        /// opens - culled out of the very frame it was waited for, and carrying
        /// a trigger collider on a gameplay layer while it waits. Re-applied
        /// here, both go away.
        ///
        /// The scrub is the belt: nothing registers in Start today, and the day
        /// something does, this is where it stops being the live game's problem.
        /// </summary>
        void SettleThumbnailLevel(GameObject root)
        {
            if (root == null)
            {
                return;
            }
            try
            {
                ScrubGroups(root.transform);
                SetLayerRecursive(root.transform, Layers.PhotoStudio);
            }
            catch (System.Exception e)
            {
                Debug.LogError("[PhotoSnaps] Level thumbnail could not be settled: " + e);
            }
        }

        /// <summary>
        /// Builds one level into the studio and aims the thumbnail camera at its
        /// spawn. Returns the root that has to be torn down, or null when
        /// nothing was built.
        ///
        /// THE LEVEL LEAVES THE GROUPS BEFORE ANY OTHER SCRIPT CAN SEE IT, and
        /// that is the whole reason this is a method of its own. A level's
        /// components register in OnEnable (PRD 15.3), so LevelBuilder.Build
        /// puts a second teleporter, a second set of platforms and a second set
        /// of batteries into the global registry the game plays by: with a live
        /// level loaded that is a level counted twice, and BootTests asserts
        /// those counts to the unit. ScrubGroups runs here, in the same
        /// synchronous block as the build and before the first yield, so no
        /// Update, no probe and no test ever observes a frame in which the
        /// studio's copy is a member of anything.
        ///
        /// Scrubbed rather than DISABLED, for the reason the two frames above
        /// exist: `enabled = false` would also cancel Start, and with it the
        /// polaroid items' pictures and the blocks' texture seeds. The copy
        /// therefore lives its two frames complete but unregistered, animating
        /// its own ring and its own batteries and touching nothing outside
        /// itself.
        /// </summary>
        GameObject BuildThumbnailLevel(int index, LevelDef def)
        {
            GameObject root = null;
            try
            {
                EnsureLevelCamera();

                root = new GameObject("LevelThumb_" + (index + 1));
                root.layer = Layers.PhotoStudio;
                // Under the studio itself and not under _contentRoot, which
                // belongs to the polaroids and is emptied by ClearContent.
                // Left at the parent's origin, so a piece placed at a design
                // position lands at exactly the same offset from the studio as
                // it does from the world's own level root, and the camera below
                // can be aimed with the level's own spawn.
                root.transform.SetParent(transform, false);

                LevelBuilder.Build(root.transform, def);
                ScrubGroups(root.transform);
                // The snap cameras cull everything but PhotoStudio, so a single
                // piece left on World would be a hole in the picture. Done after
                // the build, like RenderOne does for photo content, and done
                // AGAIN after the level's Start methods have run: see
                // SettleThumbnailLevel, which is where the pass that matters is.
                SetLayerRecursive(root.transform, Layers.PhotoStudio);

                // The level's own first frame: the player's eye height above the
                // spawn, the spawn's yaw, no pitch. PlayerController.Respawn
                // poses the body from the same three numbers through the same
                // one mirror (DesignSpace), so this is the view the player gets
                // when the level opens rather than a view invented for a menu -
                // which is what makes a thumbnail "recognisably that level".
                _levelCamera.transform.localPosition =
                    DesignSpace.ToUnity(def.Spawn) + new Vector3(0f, PlayerController.EyeHeight, 0f);
                _levelCamera.transform.localRotation =
                    Quaternion.Euler(0f, DesignSpace.YawToUnityDegrees(def.SpawnYaw), 0f);

                // The world's light, on the studio's sun, before the shutter:
                // the same copy RenderOne makes and for the same reason
                // (PRD_VISUAL V-SNAP-01).
                //
                // A thumbnail therefore inherits the two documented differences
                // the studio's sun already carries, and it inherits them rather
                // than fixing them because fixing either one here would change
                // what the POLAROIDS look like, which is a promise about
                // placement and not a menu decoration. The sun is pitched at 40
                // degrees where the level's is at 45 (PRD 14.5), and it casts no
                // shadow, so a thumbnail is a shadowless picture of its level.
                // A second light of the studio's own would double the lighting
                // instead of replacing it, since both would share the PhotoStudio
                // layer, so this is a follow-up for whoever owns the studio's
                // lighting next and not a line to sneak in here.
                SyncSunToWorld();
                _levelCamera.enabled = true;
                return root;
            }
            catch (System.Exception e)
            {
                // A level that cannot be built is the end of the thumbnails and
                // of nothing else. Without this the coroutine would die with
                // _draining stuck true, and no polaroid would ever render again
                // for the rest of the run - a menu decoration taking the game's
                // own pictures down with it.
                _levelThumbnailsOff = true;
                _levelQueue.Clear();
                if (_levelCamera != null)
                {
                    _levelCamera.enabled = false;
                }
                if (root != null)
                {
                    DestroyImmediate(root);
                }
                Debug.LogError("[PhotoSnaps] Level thumbnails off, level " + (index + 1)
                    + " could not be built in the studio: " + e);
                return null;
            }
        }

        /// <summary>
        /// Reads the shot back, tears the level down and books the time.
        ///
        /// DestroyImmediate and not Destroy, for the reason Main.ClearLevel
        /// gives: Unity defers Destroy to the end of the frame, and a level left
        /// standing for one more frame is one more frame of a second teleporter
        /// in a studio that is about to build the next level into the same
        /// space. Groups.Clear is NOT called here, and must not be: the registry
        /// is global, so clearing it would empty the LIVE level the player is
        /// paused in. This copy took itself out of the groups at build time, so
        /// there is nothing left to clear.
        /// </summary>
        void FinishThumbnail(int index, GameObject root)
        {
            float started = Time.realtimeSinceStartup;
            try
            {
                Texture2D shot = ReadBackLevel(index);
                _levelCamera.enabled = false;
                DestroyImmediate(root);

                _levelCache[index] = shot;
                _levelShots++;
                _levelWorkSeconds += Time.realtimeSinceStartup - started;
                _levelWallSeconds += Time.realtimeSinceStartup - _levelShotStart;
                if (_levelQueue.Count == 0)
                {
                    ReportThumbnailBudget();
                }
            }
            catch (System.Exception e)
            {
                _levelThumbnailsOff = true;
                _levelQueue.Clear();
                if (_levelCamera != null)
                {
                    _levelCamera.enabled = false;
                }
                if (root != null)
                {
                    DestroyImmediate(root);
                }
                Debug.LogError("[PhotoSnaps] Level thumbnails off, level " + (index + 1)
                    + " could not be read back: " + e);
            }
        }

        /// <summary>
        /// The second camera and its 160 x 90 target, built on first use.
        ///
        /// Everything it shares with the polaroid camera is shared on purpose
        /// (the PhotoStudio culling mask, the sky, HDR, MSAA, the world's
        /// post-processing), and the three things it does not share are the
        /// three that make it a window on a level rather than a print: the
        /// player's own field of view instead of the placement frustum's, a
        /// 16:9 aspect instead of a square, and the Default volume layer alone
        /// instead of the studio's vignette veto.
        /// </summary>
        void EnsureLevelCamera()
        {
            if (_levelCamera != null)
            {
                return;
            }

            _levelTarget = new RenderTexture(ThumbnailWidth, ThumbnailHeight, 24, RenderTextureFormat.ARGB32);
            _levelTarget.name = "LevelThumbTarget";
            _levelTarget.filterMode = FilterMode.Bilinear;
            _levelTarget.wrapMode = TextureWrapMode.Clamp;
            // Four samples, as on the polaroid target and for the same reason
            // (PRD_VISUAL V-PIPE-01): URP takes the sample count from the TARGET
            // TEXTURE for a camera that renders into one. It matters more here
            // than anywhere: at 160 x 90 a platform edge is one pixel wide, and
            // an aliased one reads as a broken picture rather than as a level.
            _levelTarget.antiAliasing = 4;
            _levelTarget.Create();

            GameObject cameraObject = new GameObject("LevelThumbCamera");
            cameraObject.transform.SetParent(transform, false);
            cameraObject.layer = Layers.PhotoStudio;
            _levelCamera = cameraObject.AddComponent<Camera>();
            _levelCamera.orthographic = false;
            _levelCamera.fieldOfView = PlayerController.CameraFov;
            _levelCamera.nearClipPlane = CameraNear;
            // The studio's own far plane, which is beyond the player camera's:
            // nothing the game would draw at the horizon is clipped out of a
            // thumbnail. The player's figure is private to PlayerController, and
            // copying the number here is exactly the drift this project has
            // learned to refuse (README, the viewfinder square).
            _levelCamera.farClipPlane = CameraFar;
            _levelCamera.cullingMask = Layers.PhotoStudioMask;
            _levelCamera.clearFlags = CameraClearFlags.Skybox;
            _levelCamera.backgroundColor = Palette.Get("sky_horizon");
            _levelCamera.allowHDR = true;
            _levelCamera.allowMSAA = true;
            _levelCamera.useOcclusionCulling = false;
            _levelCamera.targetTexture = _levelTarget;
            _levelCamera.aspect = (float)ThumbnailWidth / ThumbnailHeight;
            _levelCamera.enabled = false;

            UniversalAdditionalCameraData cameraData = _levelCamera.GetUniversalAdditionalCameraData();
            cameraData.renderPostProcessing = true;
            cameraData.volumeLayerMask = ThumbnailVolumeLayers;
            cameraData.volumeTrigger = _levelCamera.transform;
        }

        /// <summary>
        /// Takes every component of a freshly built studio level out of every
        /// group it just joined. See BuildThumbnailLevel for why this runs
        /// before the first yield and why it scrubs instead of disabling.
        ///
        /// Groups.Remove is silent on a member that is not there, so asking for
        /// all twelve groups on every component is both correct and cheaper to
        /// read than a table of which type joins which group - a table that
        /// would be a second copy of what each component's OnEnable already
        /// says, free to drift from it.
        /// </summary>
        void ScrubGroups(Transform root)
        {
            root.GetComponentsInChildren(true, _scrubBuffer);
            for (int i = 0; i < _scrubBuffer.Count; i++)
            {
                MonoBehaviour member = _scrubBuffer[i];
                if (member == null)
                {
                    continue;
                }
                for (int g = 0; g < LevelGroups.Length; g++)
                {
                    Groups.Remove(member, LevelGroups[g]);
                }
            }
            _scrubBuffer.Clear();
        }

        /// <summary>
        /// The thumbnail readback. No print finish: PaintPolaroidPrint's grain,
        /// black lift, vignette and hairline describe a PAPER PRINT of a
        /// placement, and a level thumbnail is a window on a level, shown on a
        /// menu button with no white frame around it.
        /// </summary>
        Texture2D ReadBackLevel(int index)
        {
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = _levelTarget;
            Texture2D shot = new Texture2D(ThumbnailWidth, ThumbnailHeight, TextureFormat.RGBA32, false);
            shot.ReadPixels(new Rect(0f, 0f, ThumbnailWidth, ThumbnailHeight), 0, 0, false);
            RenderTexture.active = previous;
            shot.wrapMode = TextureWrapMode.Clamp;
            shot.filterMode = FilterMode.Bilinear;
            shot.name = "level_thumb_" + (index + 1);
            shot.Apply(false, false);
            return shot;
        }

        /// <summary>
        /// What the thumbnails actually cost, in the player's log, every time
        /// the queue empties. This is V-MENU-02's "under 2 s in total at first
        /// launch" turned into evidence instead of a hope.
        ///
        /// Two clocks, because they answer two different questions. The WORK is
        /// what this class spends building levels and reading pixels, and it is
        /// the number a future change to LevelBuilder would move. The WALL is
        /// what the player waits, and it is dominated by the two frames every
        /// shot has to wait for: twenty-five levels cannot arrive in less than
        /// fifty frames, which is 0.8 s at 60 Hz whatever the work costs.
        ///
        /// The projection to the full grid is an extrapolation from the levels
        /// actually built, and it is deliberately pessimistic in one way and
        /// optimistic in another: the FIRST level pays for every shared material
        /// and decal texture the builder caches, while a run that has unlocked
        /// two levels says nothing about the twenty-five level case beyond an
        /// average. It is a smoke alarm, not a benchmark, and it is the only one
        /// a player run can produce without building levels nobody asked for.
        /// </summary>
        void ReportThumbnailBudget()
        {
            if (_levelShots <= 0)
            {
                return;
            }
            int total = LevelDefs.Count;
            float projected = (_levelWallSeconds / _levelShots) * total;
            string line = "[PhotoSnaps] Level thumbnails: " + _levelShots + " of " + total
                + " in " + _levelWallSeconds.ToString("0.000") + " s wall, "
                + _levelWorkSeconds.ToString("0.000") + " s of it building and reading back; all "
                + total + " would be about " + projected.ToString("0.000") + " s (V-MENU-02 budget "
                + ThumbnailBudgetSeconds.ToString("0.0") + " s).";
            if (projected > ThumbnailBudgetSeconds)
            {
                Debug.LogWarning(line + " Over budget.");
            }
            else
            {
                Debug.Log(line);
            }
        }

        Texture2D ReadBack(string id)
        {
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = _target;
            Texture2D snap = new Texture2D(SnapSize, SnapSize, TextureFormat.RGBA32, false);
            snap.ReadPixels(new Rect(0f, 0f, SnapSize, SnapSize), 0, 0, false);
            RenderTexture.active = previous;
            snap.wrapMode = TextureWrapMode.Clamp;
            snap.filterMode = FilterMode.Bilinear;
            PaintPolaroidPrint(snap, id);
            snap.Apply(false, false);
            return snap;
        }

        /// <summary>
        /// Paints the white polaroid border straight onto the render, and gives
        /// the render itself the print finish of PRD_VISUAL V-PROP-03: paper
        /// grain, lifted blacks, a 3 percent vignette and the hairline chemical
        /// border. One pass, because the border pass already owns the only
        /// GetPixels32 / SetPixels32 round trip a snap can afford.
        ///
        /// GEOMETRY IS UNTOUCHED. Every source pixel ends up at its own index,
        /// r, g and b changed and nothing else: no resample, no rescale, no crop,
        /// no shift, not even by one pixel. That is not tidiness, it is the trick
        /// the game is made of (gameplay PRD 6.9, and the class summary above):
        /// the picture is the exact view the placed content produces, and the
        /// player verifies it by raising the print against the world. Tone may
        /// drift by a few percent and the eye forgives it; a single pixel of
        /// parallax and the promise is broken.
        ///
        /// DETERMINISM. The grain is a hash of the pixel block and the photo id,
        /// never UnityEngine.Random and never Time, for the same reason
        /// Atmosphere seeds its motes and ProceduralMeshes hashes its islands:
        /// PlayMode Stage11Reload rebuilds a level and Stage12Rewind undoes one,
        /// and the same photo may not come back a different picture. Both hashes
        /// are FNV-1a followed by the same avalanche Materials.SeedFor uses, and
        /// the id is hashed CHARACTER BY CHARACTER rather than through
        /// string.GetHashCode, which is free to differ between processes and
        /// between runtimes and would make the grain unreproducible across runs
        /// (so also across the reference frames of PRD_VISUAL 6.1).
        /// </summary>
        static void PaintPolaroidPrint(Texture2D texture, string id)
        {
            Color32 frame = Palette.Get("frame");
            Color32[] pixels = texture.GetPixels32();
            int width = texture.width;
            int height = texture.height;

            // The aperture: what the frame does NOT cover. 696 x 660 at
            // SnapSize 768, wider than it is tall because the bottom band is
            // the double one, and derived from Border and BottomBorder so it
            // cannot drift from them (see their own comment).
            int left = Border;
            int right = width - Border;             // exclusive
            int bottom = BottomBorder;
            int top = height - Border;              // exclusive

            // Vignette space: -1 at the first visible pixel of the aperture and
            // +1 at the last, per axis, so r2 below is exactly 1 at the four
            // corners of the aperture whatever its aspect. The centre is the
            // APERTURE's centre and not the texture's, which are 18 px apart in
            // y: the paper's fall-off belongs to the window the player sees.
            float centreX = (left + right - 1) * 0.5f;
            float centreY = (bottom + top - 1) * 0.5f;
            float invHalfWidth = 2f / (right - 1 - left);
            float invHalfHeight = 2f / (top - 1 - bottom);

            uint idHash = PhotoIdHash(id);

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

                // The rest of the row is the print. The frame keeps its flat
                // palette colour on purpose: the grain is asked of the RENDER,
                // and "frame" is a value PaletteTests and the physical polaroid
                // mesh both read, so it is left exactly as it was written above.
                float v = (y - centreY) * invHalfHeight;
                float v2 = v * v;
                int edgeY = Mathf.Min(y - bottom, top - 1 - y);
                int cellY = y / GrainCell;

                for (int x = left; x < right; x++)
                {
                    float u = (x - centreX) * invHalfWidth;
                    // Averaged, not summed, so the corner lands on 1 and the
                    // strength constant means what it says at the corner.
                    float r2 = ((u * u) + v2) * 0.5f;
                    float gain = 1f - (VignetteStrength * r2);

                    int edge = Mathf.Min(edgeY, Mathf.Min(x - left, right - 1 - x));
                    if (edge < HairlineWidth)
                    {
                        gain *= HairlineGain;
                    }

                    int grain = GrainDelta(x / GrainCell, cellY, idHash);
                    int index = rowStart + x;
                    Color32 source = pixels[index];
                    // Alpha is left strictly alone. Nothing downstream reads it
                    // (PhotoItem hands the texture to a material as mainTexture)
                    // and a print look has no business inventing coverage.
                    source.r = Print(source.r, gain, grain);
                    source.g = Print(source.g, gain, grain);
                    source.b = Print(source.b, gain, grain);
                    pixels[index] = source;
                }
            }
            texture.SetPixels32(pixels);
        }

        /// <summary>
        /// One channel through the print: the paper's fall-off, then its density
        /// floor, then its grain.
        ///
        /// The order is the physical one and it is not interchangeable. The
        /// vignette is light reaching the emulsion, so it multiplies the image;
        /// the black lift is what the emulsion can DO with it, so it applies
        /// after and a vignetted corner still cannot go under 5 levels; the
        /// grain is the paper under both, so it is added at the end in levels
        /// rather than scaled by a tone it knows nothing about.
        ///
        /// The maths runs in the readback's own sRGB byte space rather than in
        /// linear. That is deliberate: these four numbers describe how a PRINT
        /// looks, which is a statement about display values, and V-PROP-03 gives
        /// them as such ("blacks lifted by 0.02", "a 3 percent vignette"). The
        /// bytes are already sRGB encoded, because the studio target is an
        /// ARGB32 with sRGB read/write like the computed thumbnail it stands in
        /// for, so no conversion is needed and none is done.
        /// </summary>
        static byte Print(byte channel, float gain, int grain)
        {
            float lit = (channel / 255f) * gain;
            lit = BlackLift + ((1f - BlackLift) * lit);
            int level = Mathf.RoundToInt(lit * 255f) + grain;
            return (byte)Mathf.Clamp(level, 0, 255);
        }

        /// <summary>
        /// A stable hash of a photo id, FNV-1a over its characters.
        ///
        /// Not string.GetHashCode: the runtime is allowed to randomise it per
        /// process (and .NET does), which would give the same photo a different
        /// grain on every boot. Nothing on screen would look wrong and the
        /// reference frames of PRD_VISUAL 6.1 would stop being comparable, which
        /// is the sort of failure this project has learned to spell out rather
        /// than discover.
        /// </summary>
        static uint PhotoIdHash(string id)
        {
            unchecked
            {
                uint h = 2166136261u;
                if (id != null)
                {
                    for (int i = 0; i < id.Length; i++)
                    {
                        h = (h ^ id[i]) * 16777619u;
                    }
                }
                return h;
            }
        }

        /// <summary>
        /// The grain of one GrainCell block, uniform over -GrainLevels ..
        /// +GrainLevels levels of 255.
        ///
        /// FNV-1a over the two block coordinates, seeded with the photo id so
        /// two photos do not share a grain field, then the avalanche
        /// Materials.SeedFor documents: FNV mixes the LOW bits well and leaves
        /// neighbours correlated in the HIGH ones, and the modulo below reads
        /// the low bits, so without the avalanche a row of blocks would come out
        /// as a visible ramp instead of a scatter. Five buckets out of 2^32
        /// divide evenly enough that the bias is far under one level.
        /// </summary>
        static int GrainDelta(int cellX, int cellY, uint idHash)
        {
            unchecked
            {
                uint h = idHash;
                h = (h ^ (uint)cellX) * 16777619u;
                h = (h ^ (uint)cellY) * 16777619u;
                h ^= h >> 16;
                h *= 2246822507u;
                h ^= h >> 13;
                h *= 3266489909u;
                h ^= h >> 16;
                return (int)(h % (uint)((2 * GrainLevels) + 1)) - GrainLevels;
            }
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
