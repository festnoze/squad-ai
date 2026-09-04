using System;
using System.Collections;
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

        public Transform LevelRoot { get; private set; }
        public PlayerController Player { get; private set; }
        public Hud Hud { get; private set; }
        public Menu Menu { get; private set; }
        public Rewind Rewind { get; private set; }

        bool _transitioning;
        Teleporter _teleporter;

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
            }
            else
            {
                Hud.SetPrompt(string.Empty);
                Hud.SetPhotoView(null);
                Hud.SetViewfinder(false);
            }
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
            yield return Hud.FadeOut();

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
            _transitioning = false;
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
