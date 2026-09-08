using System;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Viewpoint
{
    /// <summary>
    /// The four screen treatments of PRD_VISUAL 4.2 that belong to a game STATE
    /// rather than to the look of the world: the rewind (V-POST-04), the softened
    /// background behind a raised photo (V-POST-05) and the two level transitions
    /// (V-POST-06, the depart's white bloom-up and the fall's downward blur).
    ///
    /// WHY THIS IS CODE AT ALL, given SceneEnvironment.ApplyPost's comment that
    /// post-processing belongs in the asset. That comment is about the GLOBAL
    /// grading (tonemapping, bloom, vignette, colour adjustments): it is the same
    /// on every frame the game ever draws, so a URP project keeps it in
    /// DefaultVolumeProfile where it can be seen and retuned without a compile.
    /// The treatments here are the opposite kind of thing. They are transient,
    /// they answer to what the player is doing this instant, and no asset can
    /// express "while R is held". A Volume built at runtime whose WEIGHT is
    /// driven from 0 to 1 is URP's own answer to that, and it composes with the
    /// asset instead of fighting it: VolumeManager skips a volume of weight 0
    /// outright, so a frame with nothing happening is exactly the frame the two
    /// default profiles describe, and the values here blend FROM those profiles
    /// rather than replacing them.
    ///
    /// WHICH TWO PROFILES, because this one cost an entire inert round and the
    /// warning belongs anywhere post values are authored: Assets/Settings/
    /// DefaultVolumeProfile.asset (the project-wide global default) is applied
    /// FIRST and Assets/Settings/SampleSceneProfile.asset (named by both RP
    /// assets) SECOND. The base values these bands blend from are the result of
    /// both. Before changing a number here, read both files.
    ///
    /// WHAT THIS MAY NEVER DO. It is presentation and nothing else. PRD_VISUAL
    /// 4.8's V-VFX-01 states the tier's rule ("colliders are present from frame
    /// one; only the look resolves over time") and V-VFX-06 repeats it for the
    /// photo in hand. Nothing in this file touches a collider, a group, a
    /// counter, an event or a duration the gameplay PRD pins: it reads state
    /// Main already holds and it writes volume weights. The transitions are
    /// STILL 0.6 s because Hud owns the fade and this only decorates it.
    ///
    /// WHICH LAYER, and why the picture studio never sees a frame of it. Every
    /// other Volume this game builds at runtime lands on Default, because Default
    /// is the one volume layer BOTH cameras read, and that sharing is what makes
    /// a polaroid carry the world's grading (PRD_VISUAL 3.4; PhotoSnaps says so
    /// where it sets volumeLayerMask). These four bands are the one case where
    /// the sharing would be wrong. The studio camera's mask is Default plus
    /// PhotoStudio, so a global volume on Default DOES reach it, and PhotoSnaps
    /// renders a snap over the two frames after a shutter or a level load: a
    /// photo taken a frame before R goes down, or one re-rendered while a depart
    /// is blowing the frame out, would be read back desaturated or white and
    /// CACHED that way for the rest of the run. A polaroid is a promise about
    /// the geometry it shows (PRD 6.9); it cannot carry the player's state.
    ///
    /// So the bands sit on Layers.Player, and Bind adds that one bit to the
    /// player camera's volumeLayerMask. The studio camera reads Default and
    /// PhotoStudio and nothing else, so it cannot see them at all: no veto
    /// volume to keep in step with the profiles, no timing rule to respect. A
    /// global Volume carries no collider and no renderer, so the layer means
    /// nothing to physics or to culling here; it is a mask token, and Player is
    /// the honest one to use, since all four treatments belong to the player's
    /// own eye.
    ///
    /// WHY THE HUD IS SAFE FROM ALL OF IT, and this is what makes two of the
    /// acceptance criteria true by construction rather than by tuning: Hud and
    /// Menu both build a ScreenSpaceOverlay canvas, and an overlay canvas is
    /// composited AFTER the camera's post chain. So the rewind label is never
    /// desaturated, grained or split (V-POST-04 asks that it stay legible), and
    /// the raised print is never blurred by the depth of field that softens the
    /// world behind it (V-POST-05 asks for exactly that separation). Anything
    /// that later moves those canvases to ScreenSpaceCamera breaks both.
    ///
    /// WHAT KEEPS THESE EFFECTS IN A BUILT PLAYER, which is the stripping trap
    /// of this tier and it is NOT solved by Always Included Shaders. URP's global
    /// settings have m_StripUnusedPostProcessingVariants on, and URP decides what
    /// to keep by scanning every VolumeProfile ASSET under Assets/ and asking
    /// whether it merely HAS a component (values are ignored: see the editor's
    /// ShaderBuildPreprocessor.GetSupportedFeaturesFromVolumes). A profile built
    /// at runtime is invisible to that scan, so the five effects below survive
    /// only because DefaultVolumeProfile.asset carries a DepthOfField, a
    /// MotionBlur, a FilmGrain, a ChromaticAberration and a LensDistortion
    /// component, all at neutral values. Tidying any of them out of that asset
    /// would strip the variant and leave this file compiling, running, logging
    /// nothing and showing nothing IN A PLAYER ONLY. Do not remove them.
    ///
    /// EVERY OVERRIDE NEEDS BOTH HALVES: overrideState true AND a value. A value
    /// written with overrideState false does nothing whatsoever and looks exactly
    /// like a value that did not help, which is the single likeliest way an item
    /// like this ships inert. That is what Override() below exists for, and
    /// PhotoSnaps.BuildVignetteVolume is the worked example in this project.
    /// </summary>
    public sealed class PostFx : MonoBehaviour
    {
        // ---- V-POST-04, the rewind (numbers pinned by PRD_VISUAL 4.2) --------
        private const float RewindChromatic = 0.4f;
        private const float RewindSaturation = -60f;
        private const float RewindGrain = 0.25f;
        private const float RewindDistortion = -0.08f;
        private const float RewindSeconds = 0.25f;

        // ---- V-POST-05, the raised photo ------------------------------------
        private const float FocusStart = 6f;
        private const float FocusEnd = 30f;
        private const float FocusRadius = 0.6f;
        private const float FocusSeconds = 0.2f;

        /// <summary>
        /// Where the softening's far plane starts from while the band ramps in.
        /// Past the camera's 400 m far clip in effect, so the first frames of a
        /// raise carry a blur of a few percent instead of a full one. See
        /// ShapeFocus for why the ramp needs it at all.
        /// </summary>
        private const float FocusReach = 300f;

        // ---- V-POST-06, departing --------------------------------------------
        /// <summary>
        /// The bloom-up. The base profile holds intensity 0.35 at threshold 1.05
        /// so that ONLY emissives cross it (V-POST-01); pulling the threshold
        /// under 1 and the intensity up is what turns the teleporter's light into
        /// a glow that swallows the frame rather than a lamp in a corner.
        ///
        /// It rises in 0.35 s rather than over the fade's 0.6 s on purpose: the
        /// glow can only be SEEN while the fade quad is still translucent, so a
        /// ramp that finished with the fade would peak behind an opaque screen.
        /// </summary>
        private const float DepartBloomIntensity = 2.4f;
        private const float DepartBloomThreshold = 0.45f;
        private const float DepartBloomScatter = 0.85f;
        private const float DepartExposure = 1.2f;
        private const float DepartRiseSeconds = 0.35f;
        private const float DepartFallSeconds = 0.5f;

        // ---- V-POST-06, falling ----------------------------------------------
        /// <summary>
        /// "A Motion Blur volume weight ramped to 0.5 during the fall's last
        /// 0.3 s". URP's motion blur is CAMERA motion blur, derived from the
        /// change in the view-projection matrix between two frames, so the
        /// downward direction the item asks for comes free from the body falling
        /// and there is nothing to point by hand. CameraOnly, not
        /// CameraAndObjects: object blur wants a motion vector pass this renderer
        /// does not run, and during a fall the whole frame is the motion.
        ///
        /// One landmine to know about: SampleSceneProfile carries a MotionBlur
        /// component with intensity 0.6 and active OFF. VolumeManager skips
        /// inactive components, so the base intensity is DefaultVolumeProfile's
        /// 0 and this band is the only motion blur in the game. Tick that
        /// component on and the whole game blurs and this ramp stops reading.
        /// </summary>
        private const float FallBlurIntensity = 0.5f;
        private const float FallWindowSeconds = 0.3f;
        private const float FallRiseSeconds = 0.1f;
        private const float FallReleaseSeconds = 0.15f;

        /// <summary>
        /// Above both default profiles, which have no priority of their own (URP
        /// applies them as the base of the stack), and above the studio's own
        /// vignette veto at 5. Nothing else in this game builds a Volume.
        /// </summary>
        private const float BandPriority = 10f;

        private Band _rewind;
        private Band _focus;
        private Band _depart;
        private Band _fall;

        /// The focus band's own override, kept because ShapeFocus writes to it
        /// every frame the band is up.
        private DepthOfField _focusDof;

        private UniversalAdditionalCameraData _cameraData;
        private bool _cameraWarned;
        private bool _departing;

        /// <summary>
        /// The weight each treatment is actually drawing with this frame.
        /// Exposed because the alternative way to verify this item is to look at
        /// a screenshot by hand: a PlayMode case can hold R, wait a quarter of a
        /// second and assert that RewindWeight crossed a half.
        /// </summary>
        public float RewindWeight { get { return WeightOf(_rewind); } }

        /// <summary>Weight of the raised-photo focus (V-POST-05).</summary>
        public float FocusWeight { get { return WeightOf(_focus); } }

        /// <summary>Weight of the departing bloom-up (V-POST-06).</summary>
        public float DepartWeight { get { return WeightOf(_depart); } }

        /// <summary>Weight of the fall's downward blur (V-POST-06).</summary>
        public float FallWeight { get { return WeightOf(_fall); } }

        /// <summary>
        /// Each band is built in isolation, for the reason Main.Awake gives at
        /// length: an exception thrown building one would otherwise cancel the
        /// rest of this Awake and take the other three treatments with it. A band
        /// that fails is null for the rest of the run and every caller tolerates
        /// a null band, so the worst case is "no rewind treatment", never "no
        /// post-processing" and certainly never "no game".
        /// </summary>
        private void Awake()
        {
            _rewind = Build("rewind", BuildRewind);
            _focus = Build("photo focus", BuildFocus);
            _depart = Build("depart", BuildDepart);
            _fall = Build("fall", BuildFall);
        }

        private void OnDestroy()
        {
            // Runtime profiles belong to nobody else, so they are destroyed by
            // hand exactly as PhotoSnaps destroys its veto profile, and the
            // volume drops its reference FIRST: a Volume left holding a destroyed
            // profile is still handed to the volume manager every frame.
            Dispose(ref _rewind);
            Dispose(ref _focus);
            Dispose(ref _depart);
            Dispose(ref _fall);
        }

        // ---- Driven from Main ------------------------------------------------

        /// <summary>
        /// Points the player camera's volume stack at the bands' layer. Called by
        /// Main once the player rig exists and again on every level load, which
        /// is the same place Main re-subscribes the teleporter: a camera rebuilt
        /// mid run would come back with URP's default mask (Default alone) and
        /// the treatments would go quietly inert.
        ///
        /// Everything the player camera read before is still read: the bit is
        /// ORed in, never assigned, so Default stays in the mask and the global
        /// grading a polaroid shares with the world is untouched.
        /// </summary>
        public void Bind(UnityEngine.Camera camera)
        {
            _cameraData = null;
            if (camera == null)
            {
                return;
            }
            try
            {
                // Adds the component when it is missing. It is not: the player
                // controller already put one there to turn post-processing on.
                _cameraData = camera.GetUniversalAdditionalCameraData();
            }
            catch (Exception e)
            {
                // A run whose active pipeline is not URP degrades to "no
                // transitions", as PlayerController's own catch degrades to "no
                // post". Warned once, because this would otherwise print every
                // level load, and a warning rather than an error because the
                // game is entirely playable without any of this.
                if (!_cameraWarned)
                {
                    _cameraWarned = true;
                    Debug.LogWarning("[PostFx] No URP camera data, the state treatments "
                        + "of PRD_VISUAL 4.2 are inert: " + e);
                }
                return;
            }
            KeepVolumeLayer();
        }

        /// <summary>
        /// One call per frame from Main, with the state Main already holds. No
        /// polling and no second source of truth: whether a rewind is running,
        /// whether a photo is raised and how close the body is to the kill plane
        /// are all things Main reads for the HUD anyway.
        ///
        /// <paramref name="fallSeconds"/> is the time left before the kill plane
        /// at the speed the body falls this frame, or positive infinity when it
        /// is not falling toward it. Seconds rather than a bool because the item
        /// asks for the fall's LAST 0.3 s and only the caller knows the plane.
        /// </summary>
        public void Drive(bool rewinding, bool photoRaised, float fallSeconds)
        {
            // Unscaled, for the reason Hud.Fade gives: a treatment must reach its
            // target even if something has stopped or slowed time. Nothing in
            // this game writes Time.timeScale today, so the two agree, and this
            // is the same belt the HUD and the teleporter already wear.
            float delta = Time.unscaledDeltaTime;

            KeepVolumeLayer();

            if (_rewind != null)
            {
                _rewind.Drive(rewinding ? 1f : 0f, delta);
            }
            if (_focus != null)
            {
                _focus.Drive(photoRaised ? 1f : 0f, delta);
                ShapeFocus(_focus.Weight);
            }
            if (_fall != null)
            {
                _fall.Drive(FallTarget(fallSeconds), delta);
            }
            if (_depart != null)
            {
                _depart.Drive(_departing ? 1f : 0f, delta);
            }
        }

        /// <summary>
        /// The teleporter has taken the player: the bloom-up rises under the
        /// fade. Sets no timing of its own, so a depart lasts exactly as long as
        /// it did before this file existed.
        /// </summary>
        public void BeginDepart()
        {
            _departing = true;
        }

        /// <summary>Releases the bloom-up once the new level (or the victory screen) is up.</summary>
        public void EndDepart()
        {
            _departing = false;
        }

        /// <summary>
        /// Drops the fall's blur to nothing THIS frame instead of releasing it
        /// over FallReleaseSeconds. Main calls this from LoadLevel, where the
        /// body has just been teleported to a spawn: URP's camera motion blur
        /// reads the view-projection delta between two frames, so a weight still
        /// on the way down would smear the entire first frame of the new level
        /// across the screen from the place the player died.
        /// </summary>
        public void CutFallBlur()
        {
            if (_fall != null)
            {
                _fall.Cut();
            }
        }

        // ---- The bands -------------------------------------------------------

        /// <summary>
        /// V-POST-04. The blue tint quad and the label stay where they are (Hud
        /// owns both, and the label has to stay legible, which is why nothing
        /// here darkens or veils the frame): this adds what the item asks for on
        /// top, a world that reads as running backwards.
        ///
        /// Saturation lands at -60 from the base profile's +5, so the ramp is a
        /// real drain of colour rather than a jump to grey. The lens distortion
        /// is NEGATIVE, a slight pincushion, which pulls the frame in at the
        /// corners the way a scrubbed tape does.
        /// </summary>
        private Band BuildRewind()
        {
            Band band = new Band(transform, "RewindTreatment", RewindSeconds, RewindSeconds);

            ChromaticAberration split = band.Add<ChromaticAberration>();
            Override(split.intensity, RewindChromatic);

            ColorAdjustments colour = band.Add<ColorAdjustments>();
            // Saturation ONLY. Contrast and post exposure stay where the profile
            // put them, so a rewound frame is the graded frame minus its colour
            // and not a second grade fighting the first.
            Override(colour.saturation, RewindSaturation);

            FilmGrain grain = band.Add<FilmGrain>();
            // Thin1 is a URP preset and its texture comes from the renderer's
            // PostProcessData, which PC_Renderer names: no asset to add, and
            // nothing to strip. A Custom type with no texture would be silently
            // skipped (FilmGrain.IsActive tests for exactly that).
            Override(grain.type, FilmGrainLookup.Thin1);
            Override(grain.intensity, RewindGrain);

            LensDistortion lens = band.Add<LensDistortion>();
            Override(lens.intensity, RewindDistortion);

            return band;
        }

        /// <summary>
        /// V-POST-05. Gaussian depth of field, 6 m to 30 m, max radius 0.6,
        /// weighted in over 0.2 s while a photo is raised.
        ///
        /// A WEIGHT RAMP ALONE CANNOT FADE THIS ONE IN, which is why ShapeFocus
        /// exists. Two things fight it. The mode is an ENUM, and a volume
        /// parameter that cannot be interpolated snaps to the override the
        /// instant the weight leaves zero (Core: VolumeParameter.Interp). And
        /// every parameter blends FROM the stack's base, where max radius is
        /// already 1.0 (DefaultVolumeProfile) against the 0.6 asked for here, so
        /// the weight ramp makes the far field LESS blurred as it rises. Left
        /// alone, raising a photo would pop a full blur on in one frame and then
        /// ease it off, which is the reverse of what the item asks for and the
        /// opposite of subtle.
        /// </summary>
        private Band BuildFocus()
        {
            Band band = new Band(transform, "PhotoFocus", FocusSeconds, FocusSeconds);

            _focusDof = band.Add<DepthOfField>();
            Override(_focusDof.mode, DepthOfFieldMode.Gaussian);
            Override(_focusDof.gaussianStart, FocusStart);
            Override(_focusDof.gaussianEnd, FocusEnd);
            Override(_focusDof.gaussianMaxRadius, FocusRadius);

            return band;
        }

        /// <summary>V-POST-06, departing: the teleporter's light swallowing the frame.</summary>
        private Band BuildDepart()
        {
            Band band = new Band(transform, "DepartBloom", DepartRiseSeconds, DepartFallSeconds);

            Bloom bloom = band.Add<Bloom>();
            Override(bloom.intensity, DepartBloomIntensity);
            Override(bloom.threshold, DepartBloomThreshold);
            Override(bloom.scatter, DepartBloomScatter);

            ColorAdjustments colour = band.Add<ColorAdjustments>();
            // A stop and a bit of exposure, so the frame washes toward the white
            // the fade is going to rather than merely glowing on the way to it.
            // Post exposure and not colour filter: the filter would tint the
            // palette on the way out, and a wash is a brightness, not a hue.
            Override(colour.postExposure, DepartExposure);

            return band;
        }

        /// <summary>V-POST-06, falling: the downward blur of the last 0.3 s.</summary>
        private Band BuildFall()
        {
            Band band = new Band(transform, "FallBlur", FallRiseSeconds, FallReleaseSeconds);

            MotionBlur blur = band.Add<MotionBlur>();
            Override(blur.mode, MotionBlurMode.CameraOnly);
            Override(blur.quality, MotionBlurQuality.Medium);
            Override(blur.intensity, FallBlurIntensity);

            return band;
        }

        // ---- Plumbing --------------------------------------------------------

        /// <summary>
        /// Makes the raised-photo softening actually FADE IN, by walking its far
        /// plane in from a distance nothing in the level occupies.
        ///
        /// The arithmetic, because a formula in a render file deserves its
        /// derivation. URP blends a parameter as effective = lerp(base, mine, w),
        /// and the base far plane is the same 30 m this item pins. So writing
        ///
        ///     mine = 30 + (FocusReach - 30) * (1 - w) / w
        ///
        /// gives effective = lerp(FocusReach, 30, w) exactly: at a weight of a
        /// few percent the far plane sits out near 300 m, so the blur a platform
        /// at 30 m receives is a few percent of full, and it closes to the pinned
        /// 30 m as the weight reaches 1. Blur at a given depth is (depth - start)
        /// (end - start), capped, times the max radius, so sliding the end plane
        /// scales the whole far field smoothly where the weight alone could not.
        ///
        /// The value at FULL weight is untouched by any of this: at w = 1 the
        /// expression is 30 and every number the item pins is what lands. Only
        /// the SHAPE of the ramp depends on the base profile still saying 30.
        /// </summary>
        private void ShapeFocus(float weight)
        {
            if (_focusDof == null)
            {
                return;
            }
            if (weight <= 0f)
            {
                // The band is skipped by VolumeManager at weight 0, so there is
                // nothing to shape and nothing to divide by.
                return;
            }
            _focusDof.gaussianEnd.value = weight >= 1f
                ? FocusEnd
                : FocusEnd + (FocusReach - FocusEnd) * (1f - weight) / weight;
        }

        /// <summary>
        /// The weight the fall's blur wants, from the seconds left before the
        /// kill plane. Written so a NaN (a zero velocity divided into a zero
        /// drop, one frame after a teleport) reads as "not falling" instead of
        /// poisoning the ramp: the test is inverted for exactly that, because
        /// every comparison against NaN is false.
        /// </summary>
        private static float FallTarget(float fallSeconds)
        {
            if (!(fallSeconds < FallWindowSeconds))
            {
                return 0f;
            }
            if (fallSeconds <= 0f)
            {
                return 1f;
            }
            return 1f - (fallSeconds / FallWindowSeconds);
        }

        /// <summary>
        /// Writes a volume parameter's value AND arms it. Both halves are needed
        /// and only the pair does anything: see the class comment.
        ///
        /// URP's own VolumeParameter.Override(T) sets the same pair, but it
        /// assigns the backing field and so walks past the setters the clamped
        /// parameters define. This goes through the property, so a value edited
        /// out of a parameter's legal range lands clamped rather than out of
        /// bounds inside the shader.
        /// </summary>
        private static void Override<T>(VolumeParameter<T> parameter, T value)
        {
            parameter.overrideState = true;
            parameter.value = value;
        }

        private static float WeightOf(Band band)
        {
            return band == null ? 0f : band.Weight;
        }

        private Band Build(string what, Func<Band> build)
        {
            try
            {
                return build();
            }
            catch (Exception e)
            {
                Debug.LogWarning("[PostFx] Could not build the " + what + " treatment: " + e);
                return null;
            }
        }

        private static void Dispose(ref Band band)
        {
            if (band == null)
            {
                return;
            }
            band.Dispose();
            band = null;
        }

        /// <summary>
        /// Re-arms the bit Bind added, if something has taken it off. One int
        /// test per frame against a cached component: the cost is nothing and the
        /// failure it prevents is the whole tier silently doing nothing.
        /// </summary>
        private void KeepVolumeLayer()
        {
            if (_cameraData == null)
            {
                return;
            }
            int mask = _cameraData.volumeLayerMask.value;
            if ((mask & Layers.PlayerMask) != 0)
            {
                return;
            }
            _cameraData.volumeLayerMask = mask | Layers.PlayerMask;
        }

        /// <summary>
        /// One treatment: a global Volume, the runtime profile it reads and the
        /// ramp its weight is on. Rise and release are separate because a
        /// treatment that appears in a quarter of a second may still want to
        /// leave in a half (the depart does).
        /// </summary>
        private sealed class Band
        {
            private readonly float _riseSeconds;
            private readonly float _releaseSeconds;

            private Volume _volume;
            private VolumeProfile _profile;

            /// Linear position along the ramp, before easing. Kept apart from the
            /// weight so the easing curve can change without the ramp's timing
            /// changing with it.
            private float _progress;
            private float _weight;

            public Band(Transform parent, string name, float riseSeconds, float releaseSeconds)
            {
                _riseSeconds = riseSeconds;
                _releaseSeconds = releaseSeconds;

                GameObject host = new GameObject(name);
                // The layer goes on BEFORE the component, as everywhere else in
                // this project: Volume.OnEnable registers with the volume manager
                // under whatever layer its object carries at that instant, and a
                // volume registered on Default would be read by the picture
                // studio's camera too.
                host.layer = Layers.Player;
                host.transform.SetParent(parent, false);

                _profile = ScriptableObject.CreateInstance<VolumeProfile>();
                _profile.name = name;

                _volume = host.AddComponent<Volume>();
                // Global, so no trigger collider is needed and none is wanted:
                // a local volume decides by measuring the camera against its own
                // colliders, and an 8 m trigger box riding along with the player
                // would be in the way of every raycast the game casts.
                _volume.isGlobal = true;
                _volume.priority = BandPriority;
                _volume.weight = 0f;
                _volume.sharedProfile = _profile;
            }

            public float Weight
            {
                get { return _weight; }
            }

            public T Add<T>() where T : VolumeComponent
            {
                // Added with no overrides, then armed one parameter at a time, so
                // this band carries ONLY what it means to change and everything
                // else keeps coming from the default profiles.
                T component = _profile.Add<T>(false);
                // The first thing VolumeManager tests when it walks a profile.
                // It defaults to true; it is written anyway, because a component
                // with active false is skipped in complete silence.
                component.active = true;
                return component;
            }

            public void Drive(float target, float deltaSeconds)
            {
                float seconds = target > _progress ? _riseSeconds : _releaseSeconds;
                _progress = seconds <= 0f
                    ? target
                    : Mathf.MoveTowards(_progress, target, deltaSeconds / seconds);
                Apply();
            }

            public void Cut()
            {
                _progress = 0f;
                Apply();
            }

            public void Dispose()
            {
                if (_volume != null)
                {
                    _volume.weight = 0f;
                    _volume.sharedProfile = null;
                    _volume = null;
                }
                if (_profile != null)
                {
                    UnityEngine.Object.Destroy(_profile);
                    _profile = null;
                }
            }

            private void Apply()
            {
                // Smoothstep, hand written because this project has no tweening
                // library and needs none: neither end of a ramp should start or
                // stop on a hard edge, and a treatment that reaches its target
                // at full speed reads as a switch being flipped.
                _weight = _progress * _progress * (3f - 2f * _progress);
                if (_volume != null)
                {
                    _volume.weight = _weight;
                }
            }
        }
    }
}
