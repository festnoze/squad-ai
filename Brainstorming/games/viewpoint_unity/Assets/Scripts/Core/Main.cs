using System;
using System.Collections;
using System.Reflection;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.UI;

namespace Viewpoint
{
    /// <summary>
    /// Entry point (PRD section 11). Wires the subsystems, owns the level
    /// lifecycle (build, fade, teleport, victory) and the pause flow.
    ///
    /// The scene it lives in holds ONE object, this one: everything else is
    /// built here at runtime, exactly as the original's main.tscn is a bare
    /// skeleton. That keeps the whole game reviewable as text and means no
    /// scene edit can silently unwire a reference.
    /// </summary>
    public sealed class Main : MonoBehaviour
    {
        /// <summary>Attached when "--smoke" or "--shot" is on the command line.</summary>
        const string SmokeProbeType = "Viewpoint.Tests.SmokeProbe";
        const string ShotProbeType = "Viewpoint.ShotProbe";

        /// <summary>
        /// Below this downward speed nothing is a fall (PRD_VISUAL V-POST-06).
        /// It is there to keep a body that is merely settling on a platform out
        /// of a division: a walk off a kerb passes it, but the blur still needs
        /// the kill plane within a third of a second to show at all.
        /// </summary>
        const float FallSpeedFloor = 4f;

        // ---- Menu diorama (PRD_VISUAL 4.12 V-MENU-01) -----------------------
        // The numbers of the little world the title and victory screens float
        // over. What each one is for is on the member; the section that BUILDS
        // it, far below, carries the reasoning that spans all of them.

        /// <summary>
        /// The layer the diorama lives on, and it is a literal here rather than
        /// a <see cref="Layers"/> constant because Layers.cs and
        /// ProjectSettings/TagManager.asset both belong to someone else this
        /// round. Layers 6 to 9 are taken (World, Player, Interact,
        /// PhotoStudio); 10 to 31 have no NAME in TagManager, which costs
        /// nothing here: an integer layer works for culling and for a volume
        /// mask whether or not it is named, and nothing in this file ever asks
        /// LayerMask.NameToLayer.
        ///
        /// WHAT THE LAYER DOES AND DOES NOT BUY. It is what keeps the diorama
        /// out of every other camera: the diorama camera below sees this bit and
        /// nothing else, the picture studio's camera sees PhotoStudio and
        /// nothing else (PhotoSnaps sets cullingMask = Layers.PhotoStudioMask,
        /// which is why no polaroid can ever contain a menu prop), and the
        /// player camera excludes only PhotoStudio, so it WOULD see this - the
        /// parking distance below and the fact that the whole subtree is
        /// inactive during play are what handle that.
        ///
        /// It buys nothing at all from physics. Row 10 of
        /// ProjectSettings/DynamicsManager.asset's collision matrix is
        /// fffcffff, i.e. it pairs with everything except Interact and
        /// PhotoStudio - so it pairs with World and with Player. That file is
        /// not mine to change, so the diorama is safe by CONSTRUCTION instead:
        /// it carries NO COLLIDER of any kind, on any object, and the one Volume
        /// it builds is global precisely so it needs no trigger box. Nothing
        /// here can be hit by the interaction ray, stood on, or found by a
        /// Physics query, because there is nothing to hit.
        /// </summary>
        const int DioramaLayer = 10;

        /// <summary>Everything the diorama camera is allowed to see.</summary>
        const int DioramaMask = 1 << DioramaLayer;

        /// <summary>
        /// The volume layers the diorama camera reads: Default, where every
        /// Volume this game builds at runtime used to land, plus its own layer
        /// for the blur of V-MENU-01. Both default profiles apply to every
        /// camera whatever its mask (PhotoSnaps says the same where it sets
        /// this), so this is not what gets the diorama the game's grading; what
        /// it does is keep PostFx's four bands OUT, since those sit on
        /// Layers.Player. A title screen must not inherit a rewind's
        /// desaturation or a fall's motion blur.
        /// </summary>
        const int DioramaVolumeLayers = 1 | DioramaMask;

        /// <summary>
        /// Where the diorama is parked, and the axis is the interesting part.
        ///
        /// The picture studio parks itself at (0, -500, 0) and this could have
        /// followed it down, but it must not: Viewpoint/Surface's height fog
        /// (V-SKY-04 stage two) thickens by how far a surface sits BELOW y = 2,
        /// saturating 12 m down. At y = -500 every island here would sit at the
        /// bottom of that ramp, and the one thing this item asks for is that the
        /// diorama look like the game rather than like a hazed cut-out of it. So
        /// it is parked SIDEWAYS instead, at the walking height the fog is tuned
        /// for, where every shading term (height fog, the rock fade measured
        /// from an object's own origin, the sky's abyss darkening) gives exactly
        /// what it gives in a level.
        ///
        /// 1200 m is far enough by any measure: the widest level's decor reaches
        /// some 60 m, the player camera's far plane is 400 m, and the sun's
        /// shadow distance is 50 m, so no camera and no cascade can hold both
        /// this and the world at once.
        /// </summary>
        static readonly Vector3 DioramaOrigin = new Vector3(1200f, 0f, 0f);

        /// <summary>V-MENU-01, verbatim: "rotating at 2 degrees per second".</summary>
        const float DioramaSpinDegreesPerSecond = 2f;

        /// <summary>
        /// The eye, in the diorama's own local space. Set once and never
        /// animated: the turntable turns, the camera holds still, so the slow
        /// orbit costs one transform write a frame.
        /// </summary>
        static readonly Vector3 DioramaEyePosition = new Vector3(0f, 4.8f, -15f);
        static readonly Vector3 DioramaEyeTarget = new Vector3(0f, 0.3f, 0f);

        /// <summary>
        /// 34 degrees, not the player's 75. A long lens is what makes a small
        /// scene read as a place seen from outside rather than as a room the
        /// viewer is standing in, and it keeps the three islands inside the
        /// frame through a whole revolution (their bounding radius is 7.5 m,
        /// against a half width of 8.2 m at this distance and a 16:9 aspect).
        /// </summary>
        const float DioramaFovDegrees = 34f;
        const float DioramaNear = 0.3f;

        /// <summary>
        /// 60 m: the content ends at 21 m and the sky is drawn by the clear, not
        /// by geometry, so nothing further away exists to clip.
        /// </summary>
        const float DioramaFar = 60f;

        /// <summary>
        /// ABOVE the player camera's 0, and the brief for this item asked for
        /// below, so here is why it cannot be. A lower depth renders FIRST and
        /// the player camera then clears the colour buffer over it
        /// (clearFlags Skybox), so a diorama drawn behind would be erased every
        /// frame by a camera that is looking at an empty world. PRD_VISUAL
        /// 4.12's own wording is the one that works ("or directly with depth
        /// 1"), and what keeps the two cameras from fighting is not the order
        /// but the SWITCH: this whole subtree is active only while a title or
        /// victory screen is up, which is exactly when the player camera has
        /// nothing to say. The camera is also left Untagged, so
        /// PlayerController's "MainCamera" stays the one Camera.main finds.
        /// </summary>
        const float DioramaCameraDepth = 1f;

        /// <summary>
        /// The slight depth of field V-MENU-01 asks for behind the text.
        /// Gaussian, keyed in metres from the eye: content sits between 13 and
        /// 21 m, so the near island keeps some definition (27 percent of the
        /// radius) while the far one goes soft (73 percent). A uniform blur
        /// would read as a blurred picture; a ramp reads as depth.
        /// </summary>
        const float DioramaBlurStart = 9f;
        const float DioramaBlurEnd = 24f;
        const float DioramaBlurRadius = 1f;

        /// <summary>
        /// Above both default profiles, which have no priority of their own.
        /// The same 10 PostFx uses, and the two can never meet: its bands are on
        /// Layers.Player and this camera does not read that bit.
        /// </summary>
        const float DioramaBlurPriority = 10f;

        public Transform LevelRoot { get; private set; }
        public PlayerController Player { get; private set; }
        public Hud Hud { get; private set; }
        public Menu Menu { get; private set; }
        public Rewind Rewind { get; private set; }

        /// <summary>
        /// The state-driven post-processing of PRD_VISUAL 4.2 (V-POST-04 to
        /// V-POST-06). Null when its boot step failed, and every call site here
        /// tolerates that: a missing render pipeline costs the transitions, never
        /// the game.
        /// </summary>
        public PostFx PostFx { get; private set; }

        /// <summary>
        /// The little world behind the title and victory screens (PRD_VISUAL
        /// 4.12 V-MENU-01), or null when its boot step failed - in which case
        /// the game is exactly what it was before this item: a plain dimmed
        /// menu over the live sky.
        ///
        /// READ ONLY, and deliberately so: there is no setter and no Show call
        /// for <see cref="Menu"/> to reach for. Main already reads Menu.Mode
        /// every frame to drive the HUD and the post-processing, and it drives
        /// the diorama from that same read (see DriveMenuDiorama), so the two
        /// cannot disagree about whether a title screen is up and no half of
        /// this item can go missing the way appendix C.23 describes. The menu's
        /// side of the contract is to LOOK at these three members - lighten the
        /// dim while <see cref="MenuDioramaShowing"/> is true, keep the strong
        /// dim for pause, where the live level is what the player wants to see.
        /// </summary>
        public Transform MenuDiorama { get; private set; }

        /// <summary>
        /// The second camera that renders the diorama, or null with it. Exposed
        /// because it is the one object a menu might legitimately want to ask
        /// something of (its field of view, to place text against the framing,
        /// or its transform, to park a decoration in the same space).
        /// </summary>
        public Camera MenuDioramaCamera { get; private set; }

        /// <summary>
        /// True on the frames the diorama is actually on screen: a title or
        /// victory screen is up AND the diorama was built. False during play,
        /// during a transition and on the pause screen, which keeps the live
        /// level behind a stronger dim.
        /// </summary>
        public bool MenuDioramaShowing { get; private set; }

        bool _transitioning;
        Teleporter _teleporter;

        /// <summary>
        /// The kill plane of the level in play, kept because PostFx measures the
        /// fall against it. Read-only here: the plane the game ENFORCES is the
        /// one handed to the player controller in LoadLevel, and this is a copy
        /// of the same number for the look of the last third of a second.
        /// </summary>
        float _killY = -10f;

        /// <summary>
        /// Hud's colour-taking fade, bound by reflection ONCE. See FadeOutTo.
        /// </summary>
        MethodInfo _colourFade;
        bool _colourFadeResolved;

        /// <summary>
        /// The turning half of the diorama. The camera and the blur volume are
        /// children of the ROOT and hold still; only this one turns, so the sky
        /// and its sun disc stay put behind a scene on a turntable rather than
        /// swinging around with it.
        /// </summary>
        Transform _dioramaTable;

        /// <summary>
        /// Degrees turned so far, kept rather than read back off the transform
        /// so the rate is a rate and not an accumulation of quaternion rounding.
        /// </summary>
        float _dioramaSpinDegrees;

        /// <summary>
        /// The runtime profile carrying the menu blur. Held for one reason: a
        /// ScriptableObject made with CreateInstance is not collected on its
        /// own, so OnDestroy has to let it go (PhotoSnaps does the same with its
        /// vignette veto).
        /// </summary>
        VolumeProfile _dioramaBlurProfile;

        static GameState State
        {
            get { return GameState.Instance; }
        }

        /// <summary>
        /// Builds the game. Every step is wrapped, and that is not defensive
        /// habit: an exception thrown inside one AddComponent aborts the REST
        /// of Awake, so a single broken subsystem takes the whole game down
        /// with it and leaves a window showing nothing but a default skybox.
        /// That is precisely what happened when TextMeshPro threw while
        /// building the HUD: the player, the level root and the rewind were
        /// never created, and the symptom looked like "the levels are empty"
        /// rather than "the text is broken". A subsystem that fails now says so
        /// and the rest still comes up.
        /// </summary>
        void Awake()
        {
            Application.targetFrameRate = -1;

            Step("environment", () => SceneEnvironment.Apply(transform));

            Step("level root", () =>
            {
                var levelRoot = new GameObject("LevelRoot");
                levelRoot.transform.SetParent(transform, false);
                LevelRoot = levelRoot.transform;
            });

            // One EventSystem for the whole game. Two log an error every frame,
            // which is why neither the HUD nor the Menu makes its own.
            Step("event system", () =>
            {
                if (EventSystem.current != null)
                {
                    return;
                }
                var events = new GameObject("EventSystem");
                events.transform.SetParent(transform, false);
                events.AddComponent<EventSystem>();
                // InputSystemUIInputModule, not StandaloneInputModule: the
                // project's active input handling is the Input System package,
                // and the legacy module throws from UnityEngine.Input the first
                // time the EventSystem ticks.
                events.AddComponent<InputSystemUIInputModule>();
            });

            Step("player", () =>
            {
                var playerObject = new GameObject("Player");
                playerObject.transform.SetParent(transform, false);
                Player = playerObject.AddComponent<PlayerController>();
            });

            Step("hud", () =>
            {
                var hudObject = new GameObject("Hud");
                hudObject.transform.SetParent(transform, false);
                Hud = hudObject.AddComponent<Hud>();
            });

            Step("menu", () =>
            {
                var menuObject = new GameObject("Menu");
                menuObject.transform.SetParent(transform, false);
                Menu = menuObject.AddComponent<Menu>();
            });

            Step("photo studio", () =>
            {
                var snapsObject = new GameObject("PhotoSnaps");
                snapsObject.transform.SetParent(transform, false);
                snapsObject.AddComponent<PhotoSnaps>();
            });

            Step("rewind", () =>
            {
                var rewindObject = new GameObject("Rewind");
                rewindObject.transform.SetParent(transform, false);
                Rewind = rewindObject.AddComponent<Rewind>();
            });

            // Last, and isolated like the rest: PostFx builds four runtime
            // Volumes, and a project whose active pipeline is not URP has no use
            // for any of them. It wires nothing at boot (Update and the
            // transitions drive it), so nothing above depends on it existing.
            Step("post effects", () =>
            {
                var postObject = new GameObject("PostFx");
                postObject.transform.SetParent(transform, false);
                PostFx = postObject.AddComponent<PostFx>();
            });
        }

        static void Step(string what, Action build)
        {
            try
            {
                build();
            }
            catch (Exception e)
            {
                Debug.LogError("[Main] Could not build the " + what + ": " + e);
            }
        }

        void Start()
        {
            Player.Setup(LevelRoot);
            Player.ControlEnabled = false;
            Player.FellOut += OnPlayerFell;

            Rewind.Setup(Player, LevelRoot);

            // After Player.Setup, because that is what builds the rig: the
            // camera the volume stack has to read does not exist before it.
            if (PostFx != null)
            {
                PostFx.Bind(Player.Camera);
            }

            Menu.StartRequested += StartGame;
            Menu.ResumeRequested += Resume;
            Menu.RestartRequested += StartGame;
            Menu.LevelSelected += StartAt;
            Menu.ShowTitle();

            Cursor.lockState = CursorLockMode.None;
            Cursor.visible = true;

            AttachProbes();
        }

        void OnDestroy()
        {
            if (Player != null)
            {
                Player.FellOut -= OnPlayerFell;
            }
            if (Menu != null)
            {
                Menu.StartRequested -= StartGame;
                Menu.ResumeRequested -= Resume;
                Menu.RestartRequested -= StartGame;
                Menu.LevelSelected -= StartAt;
            }
            UnsubscribeTeleporter();
        }

        // ---- Frame ----------------------------------------------------------

        void Update()
        {
            // Fullscreen works EVERYWHERE, so it is handled before the menu and
            // transition guards: in a menu, mid fade, during a rewind.
            if (ViewpointInput.FullscreenPressed)
            {
                Screen.fullScreenMode = Screen.fullScreenMode == FullScreenMode.Windowed
                    ? FullScreenMode.FullScreenWindow
                    : FullScreenMode.Windowed;
            }

            bool playing = Menu.Mode == MenuMode.Hidden && !_transitioning;

            if (playing && ViewpointInput.PausePressed)
            {
                Pause();
                playing = false;
            }

            Hud.SetVisible(Menu.Mode == MenuMode.Hidden);

            if (playing)
            {
                Hud.SetPrompt(Player.InteractPrompt);
                PhotoPlacer placer = Player.Placer;
                string heldId = placer.HeldId;
                Texture2D picture = string.IsNullOrEmpty(heldId) ? null : PhotoSnaps.GetTexture(heldId);
                Hud.SetHeld(placer.HeldTitle(), picture, placer.Raised);
                Hud.SetPhotoView(placer.Raised ? picture : null, placer.RollSteps);
                Hud.SetViewfinder(Player.Viewfinder);
                DrivePostFx(true, placer.Raised);
            }
            else
            {
                Hud.SetPrompt(string.Empty);
                Hud.SetPhotoView(null);
                Hud.SetViewfinder(false);
                // A menu, a fade or a title screen releases every state
                // treatment: none of them describes a world the player is in.
                DrivePostFx(false, false);
            }
        }

        /// <summary>
        /// Hands the frame's state to the post-processing of PRD_VISUAL 4.2
        /// (V-POST-04 and V-POST-05, and the fall half of V-POST-06). It reads
        /// only what this Update already holds, so there is no second source of
        /// truth to drift and nothing new is polled for a look.
        ///
        /// The rewind flag comes from Rewind and not from the R key: FixedUpdate
        /// owns that decision, and asking the key here would light the treatment
        /// on a frame where the rewind had already refused to start (no history
        /// left, for one). Reading the subsystem's own state cannot disagree with
        /// what the world is doing.
        /// </summary>
        void DrivePostFx(bool playing, bool photoRaised)
        {
            if (PostFx == null)
            {
                return;
            }
            bool rewinding = playing && Rewind != null && Rewind.IsRewinding;
            float fallSeconds = playing ? FallSecondsLeft() : float.PositiveInfinity;
            PostFx.Drive(rewinding, photoRaised, fallSeconds);
        }

        /// <summary>
        /// Seconds of fall left before the kill plane, at the speed the body is
        /// falling right now, and positive infinity when it is not falling toward
        /// it. Both numbers are ones the player controller already publishes and
        /// neither is written: this decides how a frame LOOKS in the last third
        /// of a second of a fall (V-POST-06) and it must not be able to change
        /// when the fall ends, which is the controller's business alone.
        /// </summary>
        float FallSecondsLeft()
        {
            float speed = -Player.Velocity.y;
            if (speed < FallSpeedFloor)
            {
                return float.PositiveInfinity;
            }
            float drop = Player.transform.position.y - _killY;
            return drop <= 0f ? 0f : drop / speed;
        }

        /// <summary>
        /// Rewind rides the PHYSICS clock, like the recording does, so holding R
        /// unwinds the same amount of history whatever the frame rate.
        /// </summary>
        void FixedUpdate()
        {
            bool wanted = ViewpointInput.RewindHeld
                && Menu.Mode == MenuMode.Hidden
                && !_transitioning;

            if (wanted && !Rewind.IsRewinding)
            {
                Rewind.StartRewind();
                Player.ControlEnabled = false;
            }

            if (wanted)
            {
                Rewind.StepRewind(Time.fixedDeltaTime);
            }
            else if (Rewind.IsRewinding)
            {
                Rewind.StopRewind();
                Player.ControlEnabled = Menu.Mode == MenuMode.Hidden && !_transitioning;
            }

            Hud.SetRewinding(Rewind.IsRewinding, Rewind.AvailableSeconds());
        }

        // ---- Level lifecycle ------------------------------------------------

        public void StartGame()
        {
            StartAt(0);
        }

        /// <summary>
        /// Entry point of the level grid. Reset clears the run, not the
        /// persisted progression, so the other unlocked levels stay unlocked.
        /// </summary>
        public void StartAt(int index)
        {
            if (!State.IsLevelUnlocked(index))
            {
                return;
            }
            State.Reset();
            Menu.HideMenu();
            CaptureCursor(true);
            LoadLevel(index);
            Player.ControlEnabled = true;
        }

        public void LoadLevel(int index)
        {
            LevelDef def = LevelDefs.GetDef(index);
            if (def == null)
            {
                Debug.LogError("[Main] No level at index " + index);
                return;
            }

            UnsubscribeTeleporter();
            ClearLevel();

            // A held photo does not survive the jump: photos belong to their
            // level. Dropping it spawns an item, so the root is cleared again.
            if (!string.IsNullOrEmpty(Player.Placer.HeldId))
            {
                Player.Placer.Drop();
                ClearLevel();
            }

            // Photos taken with the camera belong to their level, like placed
            // content.
            PhotoDefs.ClearDynamic();

            _teleporter = LevelBuilder.Build(LevelRoot, def);
            if (_teleporter != null)
            {
                _teleporter.DepartRequested += OnDepart;
            }

            Player.SetSpawn(def.Spawn, def.SpawnYaw, def.KillY);

            // The kill plane travels with the level, like the spawn does, and so
            // does the blur that anticipates it.
            _killY = def.KillY;
            if (PostFx != null)
            {
                // SetSpawn has just teleported the body. URP's camera motion blur
                // reads the change in the view-projection matrix between two
                // frames, so a fall blur still on its way down would smear the
                // new level's first frame across the screen from wherever the
                // player died: it is cut here rather than released.
                PostFx.CutFallBlur();
                // Re-pointed at the camera the rig holds now. Cheap, and it is
                // the only place that would notice a camera rebuilt mid run,
                // which is exactly why the teleporter is re-subscribed here too.
                PostFx.Bind(Player.Camera);
            }

            State.BeginLevel(index, def.Teleporter != null ? def.Teleporter.Required : 0);
            Hud.ShowBanner("Niveau " + (index + 1) + " : " + def.Name, def.Subtitle);
            Hud.FadeIn();

            // History belongs to a level: a fresh one starts from this state.
            Rewind.BeginLevel();
        }

        /// <summary>
        /// Tears the current level down. Two things here are load bearing.
        ///
        /// DestroyImmediate, not Destroy: the original freed the old level's
        /// nodes immediately precisely so the scene groups were empty before the
        /// new level queried them, while Unity defers Destroy, and with it
        /// OnDisable, to the end of the frame. Deferred, LevelBuilder would run
        /// with every group still holding the level just left.
        ///
        /// Groups.Clear() after it, as a belt: a retired node lives in the
        /// rewind graveyard OUTSIDE this root, so clearing the root alone would
        /// leave the graveyard's registrations behind.
        /// </summary>
        void ClearLevel()
        {
            for (int i = LevelRoot.childCount - 1; i >= 0; i--)
            {
                DestroyImmediate(LevelRoot.GetChild(i).gameObject);
            }
            Groups.Clear();
        }

        void UnsubscribeTeleporter()
        {
            if (_teleporter != null)
            {
                _teleporter.DepartRequested -= OnDepart;
                _teleporter = null;
            }
        }

        void OnDepart()
        {
            if (_transitioning)
            {
                return;
            }
            StartCoroutine(Depart());
        }

        IEnumerator Depart()
        {
            _transitioning = true;
            Player.ControlEnabled = false;
            // Before the fade and not with it: the bloom-up can only be SEEN
            // while the quad is still translucent (PRD_VISUAL V-POST-06). It
            // sets no duration of its own, so a depart still takes the 0.6 s the
            // gameplay PRD pins.
            if (PostFx != null)
            {
                PostFx.BeginDepart();
            }
            // Viewpoint.Hud and not Hud: this class's own Hud property shadows
            // the TYPE name, so "Hud.FadeWhite" binds to the instance and a
            // static read through an instance is CS0176. The namespace
            // qualification is what makes the two transition colours readable
            // from the one file that owns them (Hud.cs) instead of a third copy
            // of the same white living here.
            yield return FadeOutTo(Viewpoint.Hud.FadeWhite);

            if (State.HasNextLevel())
            {
                State.AdvanceLevel();
                LoadLevel(State.LevelIndex);
                Player.ControlEnabled = true;
            }
            else
            {
                CaptureCursor(false);
                Menu.ShowVictory();
                Hud.FadeIn();
            }
            // Released once the next level (or the victory screen) is up, so the
            // glow drains away under the fade coming back in.
            if (PostFx != null)
            {
                PostFx.EndDepart();
            }
            _transitioning = false;
        }

        /// <summary>
        /// The fade out of a transition, in the colour V-POST-06 asks for (white
        /// for a depart, black for a fall). Falls back to the plain fade when the
        /// HUD has no colour-taking form of it, in which case a depart is still
        /// told apart from a fall by the bloom-up PostFx puts under it.
        ///
        /// Bound BY REFLECTION, for the same reason AttachProbes below binds the
        /// probes by name: Main must not fail to compile over a method that is
        /// not there. Hud owns the fade quad and its colour (this file must not
        /// touch Hud.cs), the two files land in the same compile, and a direct
        /// call to an API that arrives a round later does not degrade to "no
        /// white fade", it degrades to "no build". One lookup, cached, on the
        /// first departure of a run.
        /// </summary>
        IEnumerator FadeOutTo(Color color)
        {
            MethodInfo fade = ColourFade();
            if (fade == null)
            {
                yield return Hud.FadeOut();
                yield break;
            }
            yield return (IEnumerator)fade.Invoke(Hud, new object[] { color });
        }

        /// <summary>
        /// Hud's public coroutine that fades to a given colour, or null when it
        /// has none. "FadeOut(Color)" is preferred by name; any other public
        /// Fade* coroutine taking a single Color is accepted, so a HUD that calls
        /// it FadeTo still gets used.
        /// </summary>
        MethodInfo ColourFade()
        {
            if (_colourFadeResolved)
            {
                return _colourFade;
            }
            if (Hud == null)
            {
                // Not resolved: ask again when there is a HUD to ask about.
                return null;
            }
            _colourFadeResolved = true;

            MethodInfo[] methods = Hud.GetType().GetMethods(BindingFlags.Public | BindingFlags.Instance);
            for (var i = 0; i < methods.Length; i++)
            {
                if (!TakesOneColour(methods[i]))
                {
                    continue;
                }
                if (methods[i].Name == "FadeOut")
                {
                    _colourFade = methods[i];
                    break;
                }
                if (_colourFade == null && methods[i].Name.StartsWith("Fade", StringComparison.Ordinal))
                {
                    _colourFade = methods[i];
                }
            }

            Debug.Log("[Main] Depart fade: " + (_colourFade != null
                ? "Hud." + _colourFade.Name + "(Color)"
                : "Hud has no colour fade, falling back to FadeOut()"));
            return _colourFade;
        }

        static bool TakesOneColour(MethodInfo method)
        {
            if (method.ReturnType != typeof(IEnumerator))
            {
                return false;
            }
            ParameterInfo[] parameters = method.GetParameters();
            return parameters.Length == 1 && parameters[0].ParameterType == typeof(Color);
        }

        /// <summary>
        /// Falling out is losing, and it costs the whole level. Deferred to the
        /// next frame on purpose: this arrives from inside the physics step, and
        /// tearing down collision bodies there is not allowed.
        /// </summary>
        void OnPlayerFell()
        {
            if (_transitioning)
            {
                return;
            }
            StartCoroutine(RestartAfterFall());
        }

        IEnumerator RestartAfterFall()
        {
            // Set here and not after the yield: StartCoroutine runs the body up
            // to the first yield at once, so the flag is up before this frame's
            // Update can treat a body that has already died as playing.
            _transitioning = true;
            yield return null;

            // The other half of V-POST-06. A fall used to be a HARD CUT: the
            // blur ramped, the kill plane passed, and the next frame was the
            // rebuilt level. LoadLevel's Hud.FadeIn() could not cover it either,
            // because it fades to the alpha the quad already has, which on a
            // fall is 0: it lerped 0 to 0 for 0.6 s and drew nothing. So the
            // fade out has to happen HERE, and in black, which is what tells a
            // fall apart from a depart's white (PRD_VISUAL V-POST-06). Hud owns
            // the 0.6 s and the colour; see the note on the qualified name in
            // Depart above. Coming back out of black is then LoadLevel's
            // FadeIn(), which keeps whatever colour is on the screen.
            yield return FadeOutTo(Viewpoint.Hud.FadeBlack);

            LoadLevel(State.LevelIndex);
            Player.ControlEnabled = Menu.Mode == MenuMode.Hidden;
            Hud.ShowToast("Chute : le niveau recommence a zero.");
            _transitioning = false;
        }

        // ---- Pause ----------------------------------------------------------

        void Pause()
        {
            Player.ControlEnabled = false;
            CaptureCursor(false);
            Menu.ShowPause();
        }

        void Resume()
        {
            Menu.HideMenu();
            CaptureCursor(true);
            Player.ControlEnabled = true;
        }

        static void CaptureCursor(bool captured)
        {
            Cursor.lockState = captured ? CursorLockMode.Locked : CursorLockMode.None;
            Cursor.visible = !captured;
        }

        // ---- Probes ---------------------------------------------------------

        /// <summary>
        /// Attaches the integration probe or the screenshot probe when asked for
        /// on the command line. Looked up BY NAME rather than referenced: the
        /// probes live in a test assembly that the runtime cannot see, and a
        /// direct reference would not compile in a player build.
        /// </summary>
        void AttachProbes()
        {
            string[] args = System.Environment.GetCommandLineArgs();
            string wanted = null;
            for (var i = 0; i < args.Length; i++)
            {
                if (args[i] == "--smoke")
                {
                    wanted = SmokeProbeType;
                }
                else if (args[i] == "--shot")
                {
                    wanted = ShotProbeType;
                }
            }

            if (wanted == null)
            {
                return;
            }

            Type probe = FindType(wanted);
            if (probe == null)
            {
                Debug.LogWarning("[Main] Probe requested but not present: " + wanted);
                return;
            }

            var host = new GameObject(probe.Name);
            host.transform.SetParent(transform, false);
            var component = host.AddComponent(probe) as MonoBehaviour;
            if (component == null)
            {
                Debug.LogError("[Main] " + wanted + " is not a MonoBehaviour.");
                return;
            }

            // The probes take the Main they drive through a Setup(Main) method,
            // called by reflection for the same reason the type is.
            var setup = probe.GetMethod("Setup", new[] { typeof(Main) });
            if (setup != null)
            {
                setup.Invoke(component, new object[] { this });
            }
        }

        static Type FindType(string fullName)
        {
            Type direct = Type.GetType(fullName);
            if (direct != null)
            {
                return direct;
            }
            foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type found = assembly.GetType(fullName);
                if (found != null)
                {
                    return found;
                }
            }
            return null;
        }
    }
}
