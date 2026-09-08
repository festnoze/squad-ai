using System;
using System.Collections;
using System.Reflection;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
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

        /// <summary>
        /// The white a depart fades to (PRD_VISUAL V-POST-06: "leaving a level
        /// fades to white"). A paper white rather than 1,1,1 so the HUD's banner
        /// stays readable against it while the quad closes.
        /// </summary>
        static readonly Color DepartWhite = new Color(0.97f, 0.97f, 0.99f);

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
            yield return FadeOutTo(DepartWhite);

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
        /// The fade out of a departure, in the colour V-POST-06 asks for. Falls
        /// back to the plain fade when the HUD has no colour-taking form of it,
        /// in which case a depart is still told apart from a fall by the bloom-up
        /// PostFx puts under it.
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
            yield return null;
            LoadLevel(State.LevelIndex);
            Player.ControlEnabled = Menu.Mode == MenuMode.Hidden;
            Hud.ShowToast("Chute : le niveau recommence a zero.");
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
