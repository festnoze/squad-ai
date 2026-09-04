using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace Viewpoint.Tests
{
    /// <summary>
    /// THE INTEGRATION PROBE (port of tests/smoke_probe.gd, PRD 17.3).
    ///
    /// It drives the real game through the real boot path and MEASURES what
    /// happens: the bridge decking a gap, a door walked through on foot, two
    /// crates stacked, a photo of a plank matching its original to the
    /// centimetre, a rewind putting a broken cage back. Nothing here is a paper
    /// argument about geometry; every claim of the design is answered by a
    /// raycast or a counter read out of the running world.
    ///
    /// Two mechanics of this file are load bearing.
    ///
    /// PHYSICS FRAMES, NEVER RENDER FRAMES, wherever gravity or the controller
    /// has to advance: the fixed step is 1/60 s (ProjectSettings), while a
    /// headless run renders far faster than real time, so counting render frames
    /// would measure nothing at all. The original made that mistake and
    /// documented it. Render frames are used only where the thing under test
    /// really is a render frame quantity (the HUD, which Main pushes in Update,
    /// and the unscaled fade of a level transition).
    ///
    /// GROUPS, NEVER A SCENE SWEEP, to count what exists: destruction during a
    /// level goes through Rewind.Retire, which deactivates and reparents instead
    /// of destroying, so a "removed" object is still findable by
    /// FindObjectsByType. Groups is activation driven and answers the question
    /// the game asks.
    ///
    /// Two ways to run it:
    ///   Unity -batchmode -nographics -projectPath . -runTests -testPlatform PlayMode
    ///   the player (or the editor) with "--smoke", which makes Main attach this
    ///   component and call Setup(Main); the run then exits 0 or 1 by itself.
    ///
    /// Every assertion message is the original's French, copied from the
    /// GDScript: it is the readable record of what broke.
    /// </summary>
    public sealed class SmokeProbe : MonoBehaviour
    {
        /// <summary>
        /// Wall clock budget of the whole autorun. The original counted 3600
        /// process frames; frames are not a clock in Unity (a headless run can
        /// spin thousands per second), so the watchdog counts seconds instead.
        /// It exists for one reason: a silent runtime error aborts the coroutine,
        /// and a run that never concludes must still exit, and exit red.
        /// </summary>
        const float WatchdogSeconds = 900f;

        /// <summary>Half a crate: the catalog crate is 1.3 m on every axis.</summary>
        const float CrateHalf = 0.65f;

        static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

        readonly List<string> _failures = new List<string>();

        /// <summary>Stages already run, so a stage can pull its prerequisites in
        /// without running them twice when the whole scenario plays in order.</summary>
        readonly HashSet<int> _ran = new HashSet<int>();

        Main _main;
        PlayerController _player;
        PhotoPlacer _placer;

        int _checks;
        bool _autoRun;
        bool _concluded;
        float _startedAt;

        public int Checks
        {
            get { return _checks; }
        }

        public int Failures
        {
            get { return _failures.Count; }
        }

        static GameState State
        {
            get { return GameState.Instance; }
        }

        // ---- Entry points ---------------------------------------------------

        /// <summary>
        /// Called by Main (by reflection) when "--smoke" is on the command line.
        /// This path runs the whole scenario on its own and exits the process.
        /// </summary>
        public void Setup(Main main)
        {
            Bind(main);
            _autoRun = true;
        }

        /// <summary>
        /// Called by the NUnit cases, which run ONE stage each and judge it
        /// themselves: no autorun, no process exit.
        /// </summary>
        public void Bind(Main main)
        {
            _main = main;
        }

        void Start()
        {
            _startedAt = Time.realtimeSinceStartup;
            if (_autoRun)
            {
                StartCoroutine(RunAllAndQuit());
            }
        }

        void Update()
        {
            if (!_autoRun || _concluded)
            {
                return;
            }
            if (Time.realtimeSinceStartup - _startedAt > WatchdogSeconds)
            {
                Fail("sonde interrompue avant sa conclusion (erreur runtime probable, voir ci-dessus)");
                Conclude();
            }
        }

        // ---- Bookkeeping ----------------------------------------------------

        void Check(bool condition, string message)
        {
            _checks++;
            if (!condition)
            {
                _failures.Add(message);
            }
        }

        void Fail(string message)
        {
            _checks++;
            _failures.Add(message);
        }

        void CheckBetween(float value, float low, float high, string message)
        {
            Check(value >= low && value <= high, string.Format(Inv,
                "{0} (attendu dans [{1:F6}, {2:F6}], obtenu {3:F6})", message, low, high, value));
        }

        /// <summary>
        /// What the NUnit cases call after a stage. It reports EVERY failure of
        /// the stage, not just the first, and it refuses a stage that measured
        /// nothing: a run with zero checks exits 0 and looks exactly like a pass.
        /// </summary>
        public void AssertNoFailures()
        {
            Assert.Greater(_checks, 0, "la sonde n'a rien verifie du tout");
            if (_failures.Count == 0)
            {
                return;
            }
            string joined = string.Join("\n  ", _failures.ToArray());
            int count = _failures.Count;
            _failures.Clear();
            Assert.Fail(string.Format(Inv, "{0} echec(s) :\n  {1}", count, joined));
        }

        void Conclude()
        {
            if (_concluded)
            {
                return;
            }
            _concluded = true;
            for (int i = 0; i < _failures.Count; i++)
            {
                Debug.Log("  ECHEC  " + _failures[i]);
            }
            Debug.Log(string.Format(Inv, "  {0} verifications, {1} echecs", _checks, _failures.Count));
            Debug.Log("=======================");
            int code = _failures.Count > 0 ? 1 : 0;
            ViewpointInput.ResetSimulation();
            Quit(code);
        }

        /// <summary>
        /// Exits the process with the verdict, the way the original's
        /// get_tree().quit(code) does. EditorApplication is reached BY NAME, like
        /// Main reaches the probes: a batch editor run is the only place that can
        /// exit at all, and a compile time reference to it would tie this test
        /// assembly to the editor.
        /// </summary>
        static void Quit(int code)
        {
            Type editorApplication = Type.GetType("UnityEditor.EditorApplication, UnityEditor");
            if (editorApplication != null)
            {
                MethodInfo exit = editorApplication.GetMethod("Exit", new Type[] { typeof(int) });
                if (exit != null)
                {
                    exit.Invoke(null, new object[] { code });
                    return;
                }
            }
            Application.Quit(code);
        }

        // ---- Waiting --------------------------------------------------------

        /// <summary>
        /// Physics steps. Gravity, the character controller and the rewind all
        /// ride the fixed clock, so this is the unit the probe measures in.
        /// </summary>
        static IEnumerator WaitPhysics(int steps)
        {
            for (int i = 0; i < steps; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        /// <summary>Render frames, for the HUD and for Main's Update only.</summary>
        static IEnumerator WaitFrames(int frames)
        {
            for (int i = 0; i < frames; i++)
            {
                yield return null;
            }
        }

        /// <summary>
        /// Waits for a condition rather than for a duration, bounded by a real
        /// time budget: a level transition is driven by an UNSCALED fade, so no
        /// number of frames is the right thing to count.
        /// </summary>
        static IEnumerator WaitUntil(Func<bool> condition, float seconds)
        {
            float deadline = Time.realtimeSinceStartup + seconds;
            while (!condition())
            {
                if (Time.realtimeSinceStartup > deadline)
                {
                    yield break;
                }
                yield return null;
            }
        }

        // ---- Space, rays, bodies --------------------------------------------

        /// <summary>
        /// Puts the player at a DESIGN position, looking level and forward. Goes
        /// through Teleport and SetLook, never through the transform: the
        /// controller keeps its own copy of the pose, and the placement anchor is
        /// the camera it carries.
        /// </summary>
        void Stand(Vector3 designPos)
        {
            _player.Teleport(DesignSpace.ToUnity(designPos));
            _player.SetLook(0f, 0f);
        }

        /// <summary>The player's feet in DESIGN space (the mirror is its own inverse).</summary>
        Vector3 PlayerDesign()
        {
            return DesignSpace.ToUnity(_player.transform.position);
        }

        /// <summary>
        /// A ray between two DESIGN points, against the world only. The mirror is
        /// applied exactly once, here, on the way in; the hit comes back in Unity
        /// space, where y is shared and z needs DesignZ.
        /// </summary>
        static bool RayDesign(Vector3 designFrom, Vector3 designTo, out RaycastHit hit)
        {
            hit = new RaycastHit();
            Vector3 from = DesignSpace.ToUnity(designFrom);
            Vector3 to = DesignSpace.ToUnity(designTo);
            Vector3 delta = to - from;
            float distance = delta.magnitude;
            if (distance <= 0.0001f)
            {
                return false;
            }
            return Physics.Raycast(from, delta / distance, out hit, distance,
                Layers.WorldMask, QueryTriggerInteraction.Ignore);
        }

        static float DesignZ(RaycastHit hit)
        {
            return -hit.point.z;
        }

        /// <summary>
        /// The rigid body of the LAST placed content that has one. The loose
        /// props (crates, placed batteries) materialize as physical shells inside
        /// the placed content; asking for the newest one is what keeps a
        /// measurement from picking up a crate left by an earlier stage.
        /// </summary>
        static Rigidbody NewestPlacedBody()
        {
            List<PhotoContent> contents = Groups.Snapshot<PhotoContent>(Groups.PlacedContent);
            for (int i = contents.Count - 1; i >= 0; i--)
            {
                Rigidbody body = contents[i].GetComponentInChildren<Rigidbody>();
                if (body != null)
                {
                    return body;
                }
            }
            return null;
        }

        static List<Rigidbody> PlacedBodies()
        {
            List<Rigidbody> bodies = new List<Rigidbody>();
            List<PhotoContent> contents = Groups.Snapshot<PhotoContent>(Groups.PlacedContent);
            for (int i = 0; i < contents.Count; i++)
            {
                Rigidbody[] found = contents[i].GetComponentsInChildren<Rigidbody>();
                for (int j = 0; j < found.Length; j++)
                {
                    if (found[j] != null && found[j].gameObject.activeInHierarchy)
                    {
                        bodies.Add(found[j]);
                    }
                }
            }
            return bodies;
        }

        static int CountProps(PhotoDef def, string kind)
        {
            if (def == null || def.Props == null)
            {
                return 0;
            }
            int total = 0;
            for (int i = 0; i < def.Props.Count; i++)
            {
                if (def.Props[i].Kind == kind)
                {
                    total++;
                }
            }
            return total;
        }

        /// <summary>A live, active member of a group, or null.</summary>
        static T First<T>(string group) where T : Component
        {
            List<T> members = Groups.Snapshot<T>(group);
            return members.Count > 0 ? members[0] : null;
        }

        static bool Alive(Component c)
        {
            return c != null && c.gameObject.activeInHierarchy;
        }

        /// <summary>
        /// The raised picture on the HUD. Reached by name because the HUD keeps
        /// its widgets private, which is right: the probe is a client of the
        /// screen, not of the field.
        /// </summary>
        RectTransform FindPhotoView()
        {
            if (_main == null || _main.Hud == null)
            {
                return null;
            }
            Transform found = _main.Hud.transform.Find("HudCanvas/PhotoView");
            return found == null ? null : found as RectTransform;
        }

        void Rig()
        {
            if (_main == null)
            {
                return;
            }
            _player = _main.Player;
            _placer = _player == null ? null : _player.Placer;
        }

        bool Ready()
        {
            Rig();
            if (_main != null && _player != null && _placer != null)
            {
                return true;
            }
            Fail("la sonde n'a pas trouve le jeu (Main, joueur et placeur)");
            return false;
        }

        // ---- The scenario ---------------------------------------------------

        public IEnumerator RunAll()
        {
            Debug.Log("=== VIEWPOINT smoke ===");
            yield return Stage01Boot();
            yield return Stage02TakeBridgePhoto();
            yield return Stage03PlaceBridge();
            yield return Stage04BatteryAndTeleporter();
            yield return Stage05DuplicateBattery();
            yield return Stage06Door();
            yield return Stage07Cage();
            yield return Stage08RolledConsole();
            yield return Stage08bQuarterTurn();
            yield return Stage09PhotoInPhoto();
            yield return Stage10BackdropFloor();
            yield return Stage11Reload();
            yield return Stage12Rewind();
            yield return Stage13FallingCrate();
            yield return Stage14StackedCrates();
            yield return Stage15DropBattery();
            yield return Stage16RaisedPicture();
            yield return Stage17SkyShot();
            yield return Stage18PlankCopy();
            yield return Stage19ThroughTheBars();
            yield return Stage20Steel();
            yield return Stage21Lead();
            yield return Stage22TwoFlights();
            yield return Stage23EveryLevel();
            yield return Stage24Fall();
        }

        IEnumerator RunAllAndQuit()
        {
            yield return RunAll();
            Conclude();
        }

        /// <summary>
        /// Stage 1. Boot into level 1 through the same path as the Enter key, and
        /// let the player LAND: he spawns 1.2 m over the slab, which is 0.41 s of
        /// falling, so this wait is in physics steps or it measures nothing.
        /// </summary>
        public IEnumerator Stage01Boot()
        {
            if (!_ran.Add(1))
            {
                yield break;
            }
            // The probe drives the game with no device: every reader answers from
            // the simulated fields from here on.
            ViewpointInput.ResetSimulation();
            ViewpointInput.SimulatedInput = true;
            yield return WaitFrames(2);
            if (_main == null)
            {
                Fail("la sonde n'a pas de Main a piloter");
                yield break;
            }

            _main.StartGame();
            yield return WaitFrames(2);
            if (!Ready())
            {
                yield break;
            }
            yield return WaitPhysics(60);

            Check(State.LevelIndex == 0, "niveau 1 actif au demarrage");
            Check(Groups.Count(Groups.Platform) == 2, "niveau 1 : deux plateformes");
            Check(Groups.Count(Groups.PhotoItem) == 1, "niveau 1 : une photo au sol");
            Check(Groups.Count(Groups.Battery) == 1, "niveau 1 : une pile au sol");
            Check(Groups.Count(Groups.Teleporter) == 1, "niveau 1 : un teleporteur");
            Check(_player.IsGrounded, "le joueur a atterri sur la plateforme");
            // Read by REFLECTION and not as PlayerController.InteractRange: a C#
            // const is inlined into this assembly when it compiles, so the direct
            // comparison would literally be 1.7f == 1.7f, an assertion that stays
            // green whatever the runtime constant becomes. Reflection reads the
            // value the runtime assembly actually declares, so widening the reach
            // turns this red the way the original's did. GetValue rather than
            // GetRawConstantValue, so a const promoted to static readonly answers
            // instead of throwing.
            FieldInfo rangeField = typeof(PlayerController).GetField(
                "InteractRange", BindingFlags.Public | BindingFlags.Static);
            float declaredRange = rangeField != null && rangeField.FieldType == typeof(float)
                ? (float)rangeField.GetValue(null)
                : float.NaN;
            Check(Mathf.Abs(declaredRange - 1.7f) < 0.0001f,
                "portee d'interaction reduite a 1.7 m");
            // The ground language itself (grey is never carvable, everything
            // carvable is photographable) is owned by BootTests: not repeated here.
        }

        /// <summary>
        /// Stage 2. There is NO 3D ghost anymore: the placer stays an empty
        /// anchor node and the picture is raised on the HUD instead.
        /// </summary>
        public IEnumerator Stage02TakeBridgePhoto()
        {
            if (!_ran.Add(2))
            {
                yield break;
            }
            yield return Stage01Boot();
            if (!Ready())
            {
                yield break;
            }

            PhotoItem photo = First<PhotoItem>(Groups.PhotoItem);
            if (photo == null)
            {
                Fail("photo Passerelle en main");
                yield break;
            }
            photo.Interact(_player);
            Check(_placer.HeldId == "passerelle", "photo Passerelle en main");
            Check(_placer.transform.childCount == 0, "aucun fantome 3D sous le placeur");
        }

        /// <summary>
        /// Stage 3. THE OPTICAL CONTRACT: standing at the edge of platform A and
        /// placing the bridge must leave solid deck over the void, at the height
        /// the picture promised. A downward ray in the middle of the gap settles
        /// it; nothing about the photo's numbers is trusted.
        /// </summary>
        public IEnumerator Stage03PlaceBridge()
        {
            if (!_ran.Add(3))
            {
                yield break;
            }
            yield return Stage02TakeBridgePhoto();
            if (!Ready())
            {
                yield break;
            }

            Stand(new Vector3(0f, 0.05f, -2.2f));
            Check(_placer.Place(), "pose acceptee");
            Check(_placer.HeldId == "", "photo consommee par la pose");
            yield return WaitPhysics(3);
            Check(Groups.Count(Groups.PlacedContent) == 1, "contenu materialise dans le niveau");

            RaycastHit deck;
            bool onDeck = RayDesign(new Vector3(0f, 1f, -5.5f), new Vector3(0f, -2f, -5.5f), out deck);
            Check(onDeck, "la passerelle enjambe le vide (rayon au milieu du trou)");
            if (onDeck)
            {
                Check(Mathf.Abs(deck.point.y - (-0.04f)) < 0.35f,
                    "tablier a la hauteur prevue par la photo");
            }
        }

        /// <summary>Stage 4. Battery, insertion, departure, progression.</summary>
        public IEnumerator Stage04BatteryAndTeleporter()
        {
            if (!_ran.Add(4))
            {
                yield break;
            }
            yield return Stage03PlaceBridge();
            if (!Ready())
            {
                yield break;
            }

            Battery battery = First<Battery>(Groups.Battery);
            if (battery == null)
            {
                Fail("pile ramassee");
                yield break;
            }
            battery.Interact(_player);
            Check(State.CarriedBatteries == 1, "pile ramassee");

            Teleporter exit = First<Teleporter>(Groups.Teleporter);
            if (exit == null)
            {
                Fail("pile inseree");
                yield break;
            }
            exit.Interact(_player);
            Check(State.InsertedBatteries == 1, "pile inseree");
            Check(State.CanTeleport(), "teleporteur charge");
            exit.Interact(_player);

            // The departure runs a 0.6 s UNSCALED fade before the load: waiting on
            // the level index is the only honest wait here.
            yield return WaitUntil(delegate { return State.LevelIndex == 1; }, 15f);
            yield return WaitFrames(2);
            Check(State.LevelIndex == 1, "arrivee au niveau 2 apres teleportation");
            Check(State.FurthestLevel >= 1, "la progression retient le niveau atteint");
            Check(State.IsLevelUnlocked(1), "le niveau 2 est desormais selectionnable au menu");
            Check(Groups.Count(Groups.PhotoItem) == 1, "niveau 2 : la photo Pile est la");
        }

        /// <summary>
        /// Stage 5. Duplication: placing the battery photo must yield a REAL
        /// battery, physical since v4, which falls onto its socle.
        /// </summary>
        public IEnumerator Stage05DuplicateBattery()
        {
            if (!_ran.Add(5))
            {
                yield break;
            }
            yield return Stage04BatteryAndTeleporter();
            if (!Ready())
            {
                yield break;
            }

            int before = Groups.Count(Groups.Battery);
            PhotoItem pilePhoto = First<PhotoItem>(Groups.PhotoItem);
            if (pilePhoto == null)
            {
                Fail("pose de la photo Pile acceptee");
                yield break;
            }
            pilePhoto.Interact(_player);
            Stand(new Vector3(0f, 0.05f, 0f));
            Check(_placer.Place(), "pose de la photo Pile acceptee");
            yield return WaitPhysics(3);
            Check(Groups.Count(Groups.Battery) == before + 1, "une vraie pile dupliquee par la photo");
            Check(NewestPlacedBody() != null, "la pile posee est portee par une coquille physique");
        }

        /// <summary>
        /// Stage 6. THE DOOR, and the stage that has to be walked rather than
        /// argued. The frame dips under the standing plane past 3.47 m, so the
        /// placement carves the floor exactly where the player must walk: the
        /// photo shows that ground and puts it back, or the door opens onto a pit.
        /// Five sample depths answer for the floor, and then the player really
        /// walks through, on his feet, and comes out the far side. The interstice
        /// between the carved hole and the photo's wall is sealed at x = 2.5,
        /// which is the regression this stage exists for.
        /// </summary>
        public IEnumerator Stage06Door()
        {
            if (!_ran.Add(6))
            {
                yield break;
            }
            yield return Stage01Boot();
            if (!Ready())
            {
                yield break;
            }

            _main.LoadLevel(3);
            yield return WaitPhysics(10);
            Check(State.LevelIndex == 3, "niveau 4 charge");
            int erasables = Groups.Count(Groups.Erasable);
            Check(erasables == 2, "niveau 4 : deux objets effacables");
            Check(_placer.Hold("porte"), "photo Porte en main");

            // The door only erases up to its own seal wall (6.2 m): stand close.
            Stand(new Vector3(0f, 0.05f, 1.5f));
            Check(_placer.Place(), "pose de la Porte acceptee");
            yield return WaitPhysics(3);
            // The 10 m wall is wider than the frustum at 5.5 m: its two flanks
            // survive as fragments, nothing vanished whole.
            Check(Groups.Count(Groups.Erasable) == erasables + 1,
                "le mur est decoupe en fragments, pas efface en bloc");

            // Straight through the opening: the original wall is gone there and
            // NOTHING plugs the doorway. A backdrop is a solid wall, so the door
            // has none: its own wall is the seal, and the way through stays open.
            RaycastHit through;
            if (!RayDesign(new Vector3(0f, 1.67f, 1f), new Vector3(0f, 1.67f, -11f), out through))
            {
                Check(true, "l'ouverture de la porte est franche, rien ne la bouche");
            }
            else
            {
                Check(DesignZ(through) < -6.0f, string.Format(Inv,
                    "rien ne bouche l'ouverture de la porte (obstacle a {0:F2})", DesignZ(through)));
            }

            float[] probes = new float[] { -2.5f, -3.5f, -4.4f, -5.2f, -5.8f };
            for (int i = 0; i < probes.Length; i++)
            {
                float probeZ = probes[i];
                RaycastHit under;
                bool hasFloor = RayDesign(new Vector3(0f, 1.2f, probeZ), new Vector3(0f, -1.5f, probeZ), out under);
                Check(hasFloor, string.Format(Inv,
                    "du sol sous les pieds en z = {0:F1} apres la pose de la porte", probeZ));
                if (hasFloor)
                {
                    CheckBetween(under.point.y, -0.4f, 0.35f, string.Format(Inv,
                        "le sol de la photo affleure le plan de marche (z = {0:F1})", probeZ));
                }
            }

            // And the player really walks it: stand him before the door, walk him
            // forward, and check he ends up on the far side, still on his feet.
            _player.Teleport(DesignSpace.ToUnity(new Vector3(0f, 0.3f, -3.0f)));
            _player.SetLook(0f, 0f);
            _player.ControlEnabled = true;
            yield return WaitPhysics(20);
            Check(_player.IsGrounded, "le joueur a bien un sol sous les pieds devant la porte");
            ViewpointInput.SimulatedMove = new Vector2(0f, 1f);
            yield return WaitPhysics(120);
            ViewpointInput.SimulatedMove = Vector2.zero;
            yield return WaitPhysics(20);
            Vector3 arrival = PlayerDesign();
            Check(arrival.z < -4.8f, string.Format(Inv,
                "le joueur a franchi la porte (z = {0:F2})", arrival.z));
            Check(arrival.y > -1.0f, "il ne tombe pas en la franchissant");
            Check(_player.IsGrounded, "il retombe sur du sol de l'autre cote");
            _player.ControlEnabled = false;

            RaycastHit side;
            bool hitSide = RayDesign(new Vector3(1.5f, 1.67f, 1f), new Vector3(1.5f, 1.67f, -11f), out side);
            Check(hitSide, "le mur autour de la porte bloque a cote de l'ouverture");
            if (hitSide)
            {
                CheckBetween(DesignZ(side), -4.7f, -4.0f, "le mur de la photo est plaque sur la decoupe");
            }

            // THE interstice regression: between the door opening (0.8) and the
            // hole edge (about 2.7), the seal wall or the original wall must
            // block. Before the fix this ray sailed through the gap.
            RaycastHit interstice;
            bool hitInterstice = RayDesign(new Vector3(2.5f, 1.67f, 1f), new Vector3(2.5f, 1.67f, -11f), out interstice);
            Check(hitInterstice, "aucun interstice entre la decoupe et le mur de la photo");
            if (hitInterstice)
            {
                CheckBetween(DesignZ(interstice), -4.7f, -3.4f, "l'interstice est scelle au niveau du mur");
            }

            RaycastHit flank;
            bool hitFlank = RayDesign(new Vector3(4.7f, 1.67f, 1f), new Vector3(4.7f, 1.67f, -11f), out flank);
            Check(hitFlank, "le flanc du mur d'origine subsiste hors du cadre");
            if (hitFlank)
            {
                CheckBetween(DesignZ(flank), -4.5f, -3.2f, "le fragment est reste a la place du mur");
            }
        }

        /// <summary>
        /// Stage 7. Level 6, a wide open platform with a cage. A cage is
        /// BREAKABLE, not erasable: it vanishes whole when a frame catches its
        /// centre, and the batteries it held stay exactly where they were.
        /// </summary>
        public IEnumerator Stage07Cage()
        {
            if (!_ran.Add(7))
            {
                yield break;
            }
            yield return Stage01Boot();
            if (!Ready())
            {
                yield break;
            }

            _main.LoadLevel(5);
            yield return WaitPhysics(10);
            // The stages that follow measure geometry from an exact stance: with
            // the controls live the player would drift or fall out between a
            // teleport and a raycast, and the kill plane would reload the level
            // under the measurement.
            _player.ControlEnabled = false;

            List<Cage> cages = Groups.Snapshot<Cage>(Groups.Breakable);
            Check(cages.Count == 1, "niveau 6 : la cage est dans le groupe cassable");
            Check(Groups.Count(Groups.Erasable) == 0, "une cage n'est plus marquee effacable");
            LevelDef def = LevelDefs.GetDef(5);
            if (cages.Count == 1 && def != null && def.Cages.Count == 1)
            {
                Check((cages[0].CageSize - def.Cages[0].Size).magnitude < 0.001f,
                    "la cage porte sa taille pour l'objectif");
            }
            else
            {
                Fail("la cage porte sa taille pour l'objectif");
            }

            Check(_placer.Hold("porte"), "photo Porte en main pour la cage");
            Stand(new Vector3(4f, 0.05f, 2f));
            Check(_placer.Place(), "pose face a la cage acceptee");
            yield return WaitPhysics(3);
            Check(Groups.Count(Groups.Breakable) == 0, "la cage encadree a disparu");
            Check(Groups.Count(Groups.Battery) == 2,
                "les piles encagees sont toujours la, desormais accessibles");
        }

        /// <summary>
        /// Stage 8. Rotation: a console rolled 180 must materialize its slab
        /// HIGH, at +2.37 above the feet, and the roll must fall back to zero
        /// once the photo is spent.
        /// </summary>
        public IEnumerator Stage08RolledConsole()
        {
            if (!_ran.Add(8))
            {
                yield break;
            }
            yield return Stage07Cage();
            if (!Ready())
            {
                yield break;
            }

            Check(_placer.Hold("console"), "photo Console en main");
            _placer.RotateHeld(1);
            _placer.RotateHeld(1);
            Check(_placer.RollSteps == 2, "deux crans de molette : 180 degres");
            Stand(new Vector3(-4f, 0.05f, 2f));
            Check(_placer.Place(), "pose de la console tournee acceptee");
            Check(_placer.RollSteps == 0, "le roulis revient a zero apres la pose");
            yield return WaitPhysics(3);

            RaycastHit slab;
            bool hasSlab = RayDesign(new Vector3(-4f, 4f, -1f), new Vector3(-4f, 1f, -1f), out slab);
            Check(hasSlab, "la dalle tournee existe en hauteur");
            if (hasSlab)
            {
                Check(Mathf.Abs(slab.point.y - 2.42f) < 0.3f, string.Format(Inv,
                    "dalle a 180 degres a +2.37 des pieds (obtenu {0:F2})", slab.point.y));
            }
        }

        /// <summary>
        /// Stage 8b (the original's quarter turn, kept because it is the only
        /// roll that can tell the two conventions apart: a 180 looks the same
        /// either way, which is why the bug lived through twenty-five levels).
        /// The corniche slab starts low on the RIGHT at (1.6, -0.6); one step
        /// down on the wheel must take it low on the LEFT, at (-0.6, -1.6),
        /// where the raised picture shows it. Standing at z = 5 with the eye at
        /// 1.67, that is design (-0.6, 0.07, 1.8), a panel on edge whose top is
        /// at 0.97. And nowhere else: the old counter-clockwise placer put it
        /// high on the right instead, at y = 3.27, so nothing may answer there.
        /// </summary>
        public IEnumerator Stage08bQuarterTurn()
        {
            if (!_ran.Add(108))
            {
                yield break;
            }
            yield return Stage08RolledConsole();
            if (!Ready())
            {
                yield break;
            }

            Check(_placer.Hold("corniche"), "photo Corniche en main pour le quart de tour");
            _placer.RotateHeld(1);
            Check(_placer.RollSteps == 1, "un cran de molette");
            Stand(new Vector3(0f, 0.05f, 5f));
            Check(_placer.Place(), "pose de la corniche au quart de tour acceptee");
            yield return WaitPhysics(3);

            RaycastHit clockwise;
            bool onLeft = RayDesign(new Vector3(-0.6f, 3.0f, 1.8f), new Vector3(-0.6f, 0.5f, 1.8f), out clockwise);
            Check(onLeft, "la corniche tournee d'un cran est passee a GAUCHE, comme sur l'image");
            if (onLeft)
            {
                Check(Mathf.Abs(clockwise.point.y - 0.97f) < 0.35f, string.Format(Inv,
                    "sommet du panneau la ou l'image le montre (obtenu {0:F2})", clockwise.point.y));
            }

            RaycastHit wrongWay;
            Check(!RayDesign(new Vector3(0.6f, 4.6f, 1.8f), new Vector3(0.6f, 2.0f, 1.8f), out wrongWay),
                "rien en haut a droite : le monde ne tourne plus a l'envers de l'image");
        }

        /// <summary>
        /// Stage 9. Photo in photo: placing the coffret materializes a pickable
        /// Pile photo.
        /// </summary>
        public IEnumerator Stage09PhotoInPhoto()
        {
            if (!_ran.Add(9))
            {
                yield break;
            }
            yield return Stage07Cage();
            if (!Ready())
            {
                yield break;
            }

            int before = Groups.Count(Groups.PhotoItem);
            Check(_placer.Hold("coffret"), "photo Coffret en main");
            Stand(new Vector3(2f, 0.05f, 3f));
            Check(_placer.Place(), "pose du coffret acceptee");
            yield return WaitPhysics(3);

            List<PhotoItem> now = Groups.Snapshot<PhotoItem>(Groups.PhotoItem);
            Check(now.Count == before + 1, "le coffret a materialise une photo ramassable");
            bool foundPile = false;
            for (int i = 0; i < now.Count; i++)
            {
                if (now[i].DefId == "pile")
                {
                    foundPile = true;
                }
            }
            Check(foundPile, "la photo materialisee est bien la photo Pile");
        }

        /// <summary>
        /// Stage 10. Backdrop as floor: aiming down, the pile photo's painted
        /// back becomes walkable ground. Since v6.1 that back stands three times
        /// further out, so this floor is a DISTANT ramp rather than a step under
        /// the feet, and the expected place is computed FROM THE PHOTO'S OWN
        /// DEPTH: no number is written down twice.
        /// </summary>
        public IEnumerator Stage10BackdropFloor()
        {
            if (!_ran.Add(10))
            {
                yield break;
            }
            yield return Stage07Cage();
            if (!Ready())
            {
                yield break;
            }

            // Design pitch, negative looks down; Unity's sign is the opposite.
            const float designPitch = -1.4f;
            PhotoDef pileDef = PhotoDefs.GetDef("pile");
            Check(pileDef != null && pileDef.HasBackdrop, "la photo Pile porte un fond peint");
            if (pileDef == null || pileDef.Backdrop == null)
            {
                // A depth of zero collapses the expected place onto the player's
                // own feet, where the platform he stands on would answer the
                // downward ray and the claim would pass for entirely the wrong
                // reason. Report both measurements as lost instead.
                Fail("le backdrop vise au sol est devenu un plancher");
                Fail("le fond peint est bien un lointain, pas un couvercle");
                yield break;
            }
            float depth = pileDef.Backdrop.Depth;
            float eyeY = 0.05f + PlayerController.EyeHeight;
            float expectY = eyeY - depth * Mathf.Sin(-designPitch);
            float expectZ = -depth * Mathf.Cos(-designPitch);

            Check(_placer.Hold("pile"), "photo Pile en main");
            _player.Teleport(DesignSpace.ToUnity(new Vector3(0f, 0.05f, 0f)));
            _player.SetLook(0f, -designPitch * Mathf.Rad2Deg);
            Check(_placer.Place(), "pose piquee vers le bas acceptee");
            _player.SetLook(0f, 0f);
            yield return WaitPhysics(3);

            RaycastHit floorHit;
            bool hasFloor = RayDesign(
                new Vector3(0f, expectY + 6.0f, expectZ),
                new Vector3(0f, expectY - 6.0f, expectZ), out floorHit);
            Check(hasFloor, "le backdrop vise au sol est devenu un plancher");
            if (hasFloor)
            {
                CheckBetween(floorHit.point.y, expectY - 1.5f, expectY + 1.5f,
                    "plancher de backdrop a la profondeur que dicte la photo");
            }
            Check(depth > 20.0f, "le fond peint est bien un lointain, pas un couvercle");
        }

        /// <summary>
        /// Stage 11. Reloading the current level clears every placement and every
        /// consumption.
        /// </summary>
        public IEnumerator Stage11Reload()
        {
            if (!_ran.Add(11))
            {
                yield break;
            }
            yield return Stage07Cage();
            if (!Ready())
            {
                yield break;
            }

            _main.LoadLevel(5);
            yield return WaitPhysics(5);
            Check(Groups.Count(Groups.PlacedContent) == 0, "reset : plus aucun contenu pose");
            LevelDef def = LevelDefs.GetDef(5);
            int level6Photos = def == null ? -1 : def.Photos.Count;
            Check(Groups.Count(Groups.PhotoItem) == level6Photos, "reset : les photos du niveau sont de retour");
            Check(Groups.Count(Groups.Breakable) == 1, "reset : la cage est reconstruite");

            // The port of "InputMap.has_action(rewind)". There is no input map in
            // Unity: asking the reader whether it answers the field the probe
            // just wrote would restate one line of ViewpointInput and could never
            // go red. The claim worth measuring is the one the original was
            // making, that the R action is WIRED INTO THE GAME, so the key is
            // held for real and the rewind Main drives from its own FixedUpdate
            // is watched. Done after the reset checks and on a level rebuilt a
            // moment ago, whose whole history is a single sample: this scrub
            // changes nothing in the world.
            Rewind rewind = _main.Rewind;
            if (rewind == null)
            {
                Fail("l'action R (rembobiner) est enregistree");
                yield break;
            }
            ViewpointInput.SimulatedRewindHeld = true;
            yield return WaitPhysics(2);
            Check(rewind.IsRewinding, "l'action R (rembobiner) est enregistree");
            ViewpointInput.SimulatedRewindHeld = false;
            yield return WaitPhysics(2);
            Check(!rewind.IsRewinding, "relacher R arrete le rembobinage");
        }

        /// <summary>
        /// Stage 12. REWIND. Take the photo, break the cage with it, then hold R
        /// and watch the cage come back whole, the placement come undone, the
        /// photo return to the decor and the player walk backwards to where he
        /// stood. Then the same for a battery: rewinding a pickup gives the
        /// battery back to the world.
        ///
        /// The hold is a REAL key hold on the simulated device, because Main
        /// drives the rewind from its own FixedUpdate: calling StepRewind here
        /// would test the rewind and not the game.
        /// </summary>
        public IEnumerator Stage12Rewind()
        {
            if (!_ran.Add(12))
            {
                yield break;
            }
            yield return Stage01Boot();
            if (!Ready())
            {
                yield break;
            }
            Rewind rewind = _main.Rewind;
            if (rewind == null)
            {
                Fail("le rembobinage est construit");
                yield break;
            }
            LevelDef def = LevelDefs.GetDef(5);
            int level6Photos = def == null ? -1 : def.Photos.Count;

            _main.LoadLevel(5);
            yield return WaitPhysics(40);
            Vector3 start = new Vector3(0f, 0.05f, 5f);
            Stand(start);
            yield return WaitPhysics(30);

            // Take the door specifically: the level hands out more than one photo
            // now, and the group order is not the level order.
            PhotoItem cagePhoto = null;
            List<PhotoItem> items = Groups.Snapshot<PhotoItem>(Groups.PhotoItem);
            for (int i = 0; i < items.Count; i++)
            {
                if (items[i].DefId == "porte")
                {
                    cagePhoto = items[i];
                }
            }
            Check(cagePhoto != null, "la photo Porte est dans le decor");
            if (cagePhoto != null)
            {
                cagePhoto.Interact(_player);
            }
            Check(_placer.HeldId == "porte", "photo prise avant le rembobinage");
            Check(Groups.Count(Groups.PhotoItem) == level6Photos - 1, "la photo ramassee a quitte le decor");

            yield return WaitPhysics(30);
            _player.Teleport(DesignSpace.ToUnity(new Vector3(4f, 0.05f, 0f)));
            yield return WaitPhysics(30);
            Check(_placer.Place(), "pose faite, la cage est cassee");
            yield return WaitPhysics(30);
            Check(Groups.Count(Groups.Breakable) == 0, "cage cassee avant le rembobinage");
            Check(Groups.Count(Groups.PlacedContent) == 1, "contenu pose avant le rembobinage");
            Check(_placer.HeldId == "", "les mains sont vides apres la pose");
            Check(rewind.AvailableSeconds() > 1.0f, "l'historique couvre les actions faites");
            Check(rewind.SampleCount > 20, "la piste de mouvement s'est remplie");
            // Photo taken, cage broken, content placed: every structural change of
            // the level is on the undo track.
            Check(rewind.EventCount >= 3, "les changements de structure sont traces");

            // 2.5 s of history per second held, so a generous scrub goes back past
            // the placement AND past the pickup.
            ViewpointInput.SimulatedRewindHeld = true;
            yield return WaitPhysics(2);
            Check(rewind.IsRewinding, "le rembobinage est actif");
            yield return WaitPhysics(150);
            Check(Groups.Count(Groups.Breakable) == 1, "la cage est revenue entiere");
            Check(Groups.Count(Groups.PlacedContent) == 0, "le contenu pose a ete defait");
            Check(Groups.Count(Groups.PhotoItem) == level6Photos, "la photo est de retour dans le decor");
            Check(_placer.HeldId == "", "les mains sont vides comme avant la prise");
            Check(Vector3.Distance(PlayerDesign(), start) < 1.5f, "le joueur est revenu a son point de depart");
            ViewpointInput.SimulatedRewindHeld = false;
            yield return WaitPhysics(2);
            Check(!rewind.IsRewinding, "le rembobinage s'arrete au relachement");

            // The rewound future is gone: history restarts here, and the world
            // stays exactly as the rewind left it.
            yield return WaitPhysics(20);
            Check(Groups.Count(Groups.Breakable) == 1, "la cage reste entiere apres le relachement");
            Check(Groups.Count(Groups.PhotoItem) == level6Photos, "la photo reste dans le decor");
            yield return WaitPhysics(20);

            int batteryBefore = Groups.Count(Groups.Battery);
            Battery someBattery = First<Battery>(Groups.Battery);
            if (someBattery == null)
            {
                Fail("pile ramassee avant le rembobinage");
                yield break;
            }
            someBattery.Interact(_player);
            Check(State.CarriedBatteries == 1, "pile ramassee avant le rembobinage");
            Check(Groups.Count(Groups.Battery) == batteryBefore - 1, "la pile ramassee a quitte le sol");
            yield return WaitPhysics(30);
            ViewpointInput.SimulatedRewindHeld = true;
            yield return WaitPhysics(60);
            ViewpointInput.SimulatedRewindHeld = false;
            yield return WaitPhysics(2);
            Check(State.CarriedBatteries == 0, "le rembobinage rend la pile portee");
            Check(Groups.Count(Groups.Battery) == batteryBefore, "la pile est de retour a sa place");
        }

        /// <summary>
        /// Stage 13. Physics of loose objects: a crate placed upside down from
        /// the ground materializes above the head and FALLS. Hanging boxes in the
        /// air is over.
        /// </summary>
        public IEnumerator Stage13FallingCrate()
        {
            if (!_ran.Add(13))
            {
                yield break;
            }
            yield return Stage07Cage();
            if (!Ready())
            {
                yield break;
            }
            // The crate is measured from an exact stance, and the rewind stage
            // that runs before this one in the full scenario hands the controls
            // back: without this the player would be walking his own gravity
            // through the measurement in one order and parked in the other.
            _player.ControlEnabled = false;

            Check(_placer.Hold("caisse"), "photo Caisse en main");
            _placer.RotateHeld(1);
            _placer.RotateHeld(1);
            Check(_placer.RollSteps == 2, "caisse retournee a 180 degres");
            Stand(new Vector3(0f, 0.05f, 5f));
            Check(_placer.Place(), "pose de la caisse retournee acceptee");
            yield return WaitPhysics(1);

            Rigidbody crate = NewestPlacedBody();
            Check(crate != null, "la caisse posee est un corps physique");
            if (crate == null)
            {
                yield break;
            }
            float spawnY = crate.transform.position.y;
            Check(spawnY > 2.0f, string.Format(Inv,
                "la caisse retournee apparait en hauteur (obtenu {0:F2})", spawnY));
            yield return WaitPhysics(60);
            if (Alive(crate))
            {
                float restY = crate.transform.position.y;
                Check(restY < spawnY - 0.5f, string.Format(Inv,
                    "la caisse est tombee sous sa hauteur de pose ({0:F2} puis {1:F2})", spawnY, restY));
                Check(restY > -5.0f, "la caisse a fini sa chute sur la plateforme");
            }
            else
            {
                Fail("la caisse posee a disparu pendant sa chute");
            }
        }

        /// <summary>
        /// Stage 14. STACKING, the whole point of the falling crate and the load
        /// bearing move of levels 23 and 25. A crate placed the right way up
        /// lands at the player's feet, top at 1.3. A second one placed UPSIDE
        /// DOWN from the same spot appears a metre above the eye, 2.6 m ahead,
        /// and drops ONTO the first: top at 2.6, which a jump turns into 4.1.
        /// Placing it the right way up would only ever give 1.3, so this is the
        /// one move that cannot be improvised. And the first crate must SURVIVE:
        /// a placement never carves a rigid body.
        /// </summary>
        public IEnumerator Stage14StackedCrates()
        {
            if (!_ran.Add(14))
            {
                yield break;
            }
            yield return Stage01Boot();
            if (!Ready())
            {
                yield break;
            }

            _main.LoadLevel(0);
            yield return WaitPhysics(20);
            _player.ControlEnabled = false;
            Stand(new Vector3(0f, 0.05f, 4f));
            yield return WaitPhysics(4);

            Check(_placer.Hold("caisse"), "premiere caisse en main");
            Check(_placer.Place(), "premiere caisse posee a l'endroit");
            yield return WaitPhysics(60);
            Rigidbody firstCrate = NewestPlacedBody();
            float firstTop = 0f;
            if (firstCrate == null)
            {
                Fail("la premiere caisse n'a pas ete construite");
            }
            else
            {
                firstTop = firstCrate.transform.position.y + CrateHalf;
                CheckBetween(firstTop, 1.1f, 1.5f, string.Format(Inv,
                    "la premiere caisse repose au sol, sommet a {0:F2} m", firstTop));
            }

            // Same spot, same aim, photo turned over: the target is the crate.
            Check(_placer.Hold("caisse"), "seconde caisse en main");
            _placer.RotateHeld(1);
            _placer.RotateHeld(1);
            Check(_placer.RollSteps == 2, "seconde caisse retournee");
            Check(_placer.Place(), "seconde caisse posee retournee");
            yield return WaitPhysics(90);

            // Placing a photo never carves a crate: they are rigid bodies, not
            // blocks, so a stack survives the next placement. Measured on the body
            // captured BEFORE the second placement, and outside the branch below:
            // PlacedBodies only ever reports ACTIVE bodies, so picking the
            // survivor out of that list could not contradict the claim it makes.
            Check(Alive(firstCrate), "la premiere caisse a survecu a la pose de la seconde");

            List<Rigidbody> bodies = PlacedBodies();
            if (bodies.Count < 2)
            {
                Fail("les deux caisses ne coexistent pas apres la seconde pose");
            }
            else
            {
                bodies.Sort(delegate (Rigidbody a, Rigidbody b)
                {
                    return b.transform.position.y.CompareTo(a.transform.position.y);
                });
                Rigidbody topCrate = bodies[0];
                float stackTop = topCrate.transform.position.y + CrateHalf;
                CheckBetween(stackTop, 2.3f, 2.9f, string.Format(Inv,
                    "la pile de deux caisses culmine a {0:F2} m", stackTop));
                Check(stackTop > firstTop + 1.0f, string.Format(Inv,
                    "la seconde caisse est retombee SUR la premiere, pas a cote ({0:F2} puis {1:F2})",
                    firstTop, stackTop));
                // A jump from the top of the stack clears 4.1 m: that is the
                // number the towers of levels 23 and 25 are cut to.
                Check(stackTop + 1.5f >= 4.0f, "l'empilement plus un saut atteint bien 4 m");
            }
        }

        /// <summary>
        /// Stage 15. E without a target puts one carried battery back on the
        /// ground: the prompt only appears when the ray finds nothing, so stand
        /// in an empty corner. And the lead never launders itself: carried
        /// leaden, put back leaden, still invisible to film on the floor.
        /// </summary>
        public IEnumerator Stage15DropBattery()
        {
            if (!_ran.Add(15))
            {
                yield break;
            }
            yield return Stage14StackedCrates();
            if (!Ready())
            {
                yield break;
            }

            _player.ControlEnabled = false;
            Stand(new Vector3(7f, 0.05f, 6f));
            yield return WaitFrames(2);

            int before = Groups.Count(Groups.Battery);
            State.CollectBattery();
            _player.UpdateInteractTarget();
            Check(_player.InteractPrompt == "E : reposer une pile", "invite de repose affichee les mains pleines");
            Check(State.DropBattery() == "normal", "drop_battery accepte avec une pile portee");
            _player.SpawnDroppedBattery(false);
            yield return WaitFrames(3);
            Check(Groups.Count(Groups.Battery) == before + 1, "la pile reposee est de retour au sol");
            Check(Groups.Count(Groups.CopyableBattery) == Groups.Count(Groups.Battery),
                "une pile ordinaire reposee reste photocopiable");
            Check(State.CarriedBatteries == 0, "plus rien en main apres la repose");
            Check(State.DropBattery() == "", "reposer sans pile est refuse");

            int copyableBeforeLead = Groups.Count(Groups.CopyableBattery);
            State.CollectBattery(true);
            Check(State.CarriedSealed == 1, "une pile plombee en main est comptee comme telle");
            Check(State.DropBattery() == "sealed", "c'est bien du plomb qui redescend");
            _player.SpawnDroppedBattery(true);
            yield return WaitFrames(3);
            Check(Groups.Count(Groups.Battery) == before + 2, "la pile plombee est au sol");
            Check(Groups.Count(Groups.CopyableBattery) == copyableBeforeLead,
                "une pile plombee reposee reste hors de portee de la pellicule");
        }

        /// <summary>
        /// Stage 16. The raised picture (right click) replaces the old 3D ghost:
        /// it turns with the wheel ON THE HUD, one step reading clockwise, and
        /// placing while raised lowers it.
        /// </summary>
        public IEnumerator Stage16RaisedPicture()
        {
            if (!_ran.Add(16))
            {
                yield break;
            }
            yield return Stage14StackedCrates();
            if (!Ready())
            {
                yield break;
            }

            _player.ControlEnabled = false;
            Check(_placer.Hold("passerelle"), "photo en main pour la levee");
            _placer.RaiseToggle();
            Check(_placer.Raised, "clic droit : photo levee");
            _placer.RaiseToggle();
            Check(!_placer.Raised, "second clic droit : photo baissee");
            _placer.RaiseToggle();
            _placer.RotateHeld(1);
            // Main pushes the picture to the HUD in Update: render frames here.
            yield return WaitFrames(3);

            RectTransform view = FindPhotoView();
            if (view == null)
            {
                Fail("l'image levee s'affiche sur le HUD");
            }
            else
            {
                Check(view.gameObject.activeInHierarchy, "l'image levee s'affiche sur le HUD");
                // One wheel step down is a quarter turn CLOCKWISE on screen,
                // which in Unity is a NEGATIVE rotation about z.
                float roll = Mathf.DeltaAngle(0f, view.localEulerAngles.z);
                Check(Mathf.Abs(roll + 90f) < 0.5f, "l'image levee est tournee d'un cran de molette");
                Check(Mathf.Abs(view.pivot.x - 0.5f) < 0.001f && Mathf.Abs(view.pivot.y - 0.5f) < 0.001f,
                    "pivot de rotation place au centre de l'image");
            }

            _placer.RotateHeld(-1);
            Stand(new Vector3(0f, 0.05f, 4f));
            Check(_placer.Place(), "pose acceptee pendant que la photo est levee");
            Check(!_placer.Raised, "la photo levee retombe apres la pose");
            yield return WaitFrames(3);
            // AND, not OR: a HUD with no picture widget at all must fail this
            // claim rather than satisfy it by absence.
            Check(view != null && !view.gameObject.activeInHierarchy,
                "l'image disparait du HUD une fois posee");
        }

        /// <summary>
        /// Stage 17. Level 16, the camera. The sky is a legitimate subject, the
        /// film is always consumed, and the empty photo pierces whatever it
        /// frames: here it mows down the cage around the teleporter.
        /// </summary>
        public IEnumerator Stage17SkyShot()
        {
            if (!_ran.Add(17))
            {
                yield break;
            }
            yield return Stage01Boot();
            if (!Ready())
            {
                yield break;
            }

            _main.LoadLevel(15);
            yield return WaitPhysics(10);
            _player.ControlEnabled = false;
            Check(State.LevelIndex == 15, "niveau 16 charge");
            Check(State.CameraFilms == 0, "pellicule vide avant l'appareil");
            List<CameraItem> cameras = Groups.Snapshot<CameraItem>(Groups.CameraItem);
            Check(cameras.Count == 1, "niveau 16 : un appareil photo");
            if (cameras.Count == 1)
            {
                cameras[0].Interact(_player);
            }
            Check(State.CameraFilms == 2, "pellicule chargee : 2 vues");

            _player.Teleport(DesignSpace.ToUnity(new Vector3(0f, 0.05f, 0.5f)));
            // Design pitch +1.2 rad is UP; Unity's positive pitch looks down.
            _player.SetLook(0f, -1.2f * Mathf.Rad2Deg);
            // The shutter answers only through the viewfinder: aim first, shoot
            // second.
            Check(!_player.CapturePhoto(), "declencher sans viser est refuse");
            Check(State.CameraFilms == 2, "un declenchement refuse ne coute pas de pellicule");
            Check(_player.ToggleViewfinder(), "clic droit mains vides : appareil a l'oeil");
            Check(_player.Viewfinder, "le viseur est actif");
            Check(_player.CapturePhoto(), "cliche du ciel accepte : le vide est un sujet");
            Check(!_player.Viewfinder, "le viseur se referme apres le declenchement");
            Check(State.CameraFilms == 1, "la photo vide consomme bien une vue");
            Check(_placer.Raised, "le cliche sort leve, comme un polaroid frais");

            PhotoDef skyDef = PhotoDefs.GetDef(_placer.HeldId);
            Check(skyDef != null, "le cliche du ciel est une definition valide");
            if (skyDef != null)
            {
                Check(skyDef.Props == null || skyDef.Props.Count == 0, "le cliche du ciel ne contient aucun prop");
                Check(skyDef.Backdrop != null && Mathf.Abs(skyDef.Backdrop.Depth - 36.0f) < 0.001f,
                    "fond peint du cliche a 36 m");
                Check(Mathf.Abs(skyDef.EraseDepth - 12.0f) < 0.001f,
                    "le cliche efface sur les 12 m qu'il a captures");
            }

            _player.SetLook(0f, 0f);
            Check(Groups.Count(Groups.Breakable) == 1, "niveau 16 : le teleporteur est encage");
            Check(_placer.Place(), "pose de la photo vide acceptee");
            yield return WaitPhysics(3);
            Check(Groups.Count(Groups.Breakable) == 0, "la photo vide a fauche la cage");
        }

        /// <summary>
        /// Stage 18. Capture is a COPY, and it is FAITHFUL: an object entirely in
        /// frame is on the photo at its real size and its real place, so placing
        /// the shot from where it was taken lays the copy exactly over the
        /// original. The lavender plank must match within 0.01 m in position and
        /// in size, the original must survive, and the GROUND in the frame must
        /// be on the photo too: without it, placing the shot would carve the
        /// floor away and drop the player through his own picture (capture tested
        /// centres while placement carves volumes). That last claim is measured
        /// by walking the player on it.
        /// </summary>
        public IEnumerator Stage18PlankCopy()
        {
            if (!_ran.Add(18))
            {
                yield break;
            }
            yield return Stage17SkyShot();
            if (!Ready())
            {
                yield break;
            }

            Check(Groups.Count(Groups.Erasable) == 1, "niveau 16 : une planche lavande");
            ErasableBlock plank = First<ErasableBlock>(Groups.Erasable);
            if (plank == null)
            {
                Fail("cliche pris sur la planche lavande");
                yield break;
            }
            Vector3 plankWorld = plank.transform.position;
            Vector3 plankSize = plank.BlockSize;

            _player.Teleport(DesignSpace.ToUnity(new Vector3(4f, 0.05f, 7.6f)));
            _player.SetLook(0f, 0f);
            // The anchor of the shot is the camera transform, so its inverse is
            // what maps the world onto the film.
            Matrix4x4 anchorInverse = _player.Camera.transform.worldToLocalMatrix;
            _player.ToggleViewfinder();
            Check(_player.CapturePhoto(), "cliche pris sur la planche lavande");
            Check(_placer.HeldId.StartsWith("cliche_"), "le cliche est en main");
            Check(State.CameraFilms == 0, "seconde vue consommee");

            PhotoDef shot = PhotoDefs.GetDef(_placer.HeldId);
            if (shot == null || shot.Props == null)
            {
                Fail("la planche lavande figure sur le cliche");
            }
            else
            {
                // The film speaks DESIGN space, so the expectation is mirrored
                // exactly once on the way out of the anchor.
                Vector3 expected = DesignSpace.ToUnity(anchorInverse.MultiplyPoint3x4(plankWorld));
                int lavenderProps = 0;
                int groundProps = 0;
                for (int i = 0; i < shot.Props.Count; i++)
                {
                    PhotoProp prop = shot.Props[i];
                    if (prop.Color == "erasable")
                    {
                        lavenderProps++;
                        Check(!prop.Loose, "une planche de 4 m reste solidaire sur le cliche");
                        float offset = Vector3.Distance(prop.Pos, expected);
                        Check(offset < 0.01f, string.Format(Inv,
                            "la planche est au bon endroit sur le cliche (ecart {0:F3} m)", offset));
                        float sizeError = Vector3.Distance(prop.Size, plankSize);
                        Check(sizeError < 0.01f, string.Format(Inv,
                            "la planche est a la bonne taille sur le cliche (ecart {0:F3} m)", sizeError));
                    }
                    else if (prop.Color == "platform")
                    {
                        groundProps++;
                        Check(!prop.Loose, "un morceau de sol reste solidaire");
                    }
                }
                Check(lavenderProps == 1, "la planche lavande figure sur le cliche");
                Check(groundProps > 0, "le sol cadre figure sur le cliche");
            }

            _player.Teleport(DesignSpace.ToUnity(new Vector3(0f, 0.05f, 1.5f)));
            _player.SetLook(0f, 0f);
            Check(_placer.Place(), "pose du cliche acceptee");
            yield return WaitPhysics(3);

            RaycastHit copyHit;
            Check(RayDesign(new Vector3(0f, 1f, -1.5f), new Vector3(0f, -1f, -1.5f), out copyHit),
                "la copie de la planche enjambe le vide");
            Check(Groups.Count(Groups.Erasable) > 0, "l'originale n'a pas ete detruite : c'est une copie");
            // The reported symptom, guarded: the ground framed by the shot is
            // part of the shot, so placing it cannot drop the player through his
            // own picture.
            RaycastHit floorHit;
            Check(RayDesign(new Vector3(0f, 1.5f, 1.5f), new Vector3(0f, -2.0f, 1.5f), out floorHit),
                "le sol reste sous les pieds apres la pose du cliche");
            _player.ControlEnabled = true;
            yield return WaitPhysics(40);
            Check(PlayerDesign().y > -1.0f, "le joueur ne tombe pas a travers sa propre photo");
            Check(_player.IsGrounded, "le joueur tient toujours debout sur le sol");
            _player.ControlEnabled = false;
        }

        /// <summary>
        /// Stage 19. Level 19: the capture is geometric, bars do not block it,
        /// and the cage itself is NOT copied (a copied cage would materialize
        /// around the copied batteries and seal them in). FILM DOES NOT PRINT
        /// FILM: the copies come out leaden, so the count of subjects does not
        /// move, or a player photographs a copy next to its original and doubles
        /// his batteries at every shot.
        /// </summary>
        public IEnumerator Stage19ThroughTheBars()
        {
            if (!_ran.Add(19))
            {
                yield break;
            }
            yield return Stage01Boot();
            if (!Ready())
            {
                yield break;
            }

            _main.LoadLevel(18);
            yield return WaitPhysics(10);
            _player.ControlEnabled = false;
            CameraItem cameraItem = First<CameraItem>(Groups.CameraItem);
            Check(cameraItem != null, "niveau 19 : un appareil photo");
            if (cameraItem != null)
            {
                cameraItem.Interact(_player);
            }
            Check(State.CameraFilms == 2, "niveau 19 : 2 vues");
            int batteriesBefore = Groups.Count(Groups.Battery);
            Check(batteriesBefore == 3, "niveau 19 : trois piles dont deux encagees");

            _player.Teleport(DesignSpace.ToUnity(new Vector3(0f, 0.05f, -2f)));
            _player.SetLook(0f, 0f);
            _player.ToggleViewfinder();
            Check(_player.CapturePhoto(), "cliche pris a travers les barreaux");
            PhotoDef shot = PhotoDefs.GetDef(_placer.HeldId);
            int capturedBatteries = 0;
            int capturedCage = 0;
            if (shot != null && shot.Props != null)
            {
                for (int i = 0; i < shot.Props.Count; i++)
                {
                    PhotoProp prop = shot.Props[i];
                    if (prop.Kind == "battery")
                    {
                        capturedBatteries++;
                    }
                    if (prop.Color == "battery_tip" || prop.Color == "sealed")
                    {
                        capturedCage++;
                    }
                }
            }
            Check(capturedBatteries == 2, "les deux piles encagees sont sur le cliche");
            Check(capturedCage == 0, "la cage elle-meme n'est pas copiee");

            _player.Teleport(DesignSpace.ToUnity(new Vector3(-4f, 0.05f, 2f)));
            _player.SetLook(0f, 0f);
            int copyableBeforeShot = Groups.Count(Groups.CopyableBattery);
            Check(_placer.Place(), "pose du cliche de piles acceptee");
            yield return WaitPhysics(3);
            Check(Groups.Count(Groups.Battery) == batteriesBefore + 2,
                "deux vraies piles dupliquees hors de la cage");
            Check(Groups.Count(Groups.CopyableBattery) == copyableBeforeShot,
                "les copies ne sont pas elles-memes photographiables");
        }

        /// <summary>
        /// Stage 20. Level 21: steel. No placement opens it, not even one that
        /// catches its centre squarely, the interaction ray does not pass either,
        /// and the way out is the lens: both caged batteries in a single frame,
        /// which is the entire point of the level that teaches it.
        /// </summary>
        public IEnumerator Stage20Steel()
        {
            if (!_ran.Add(20))
            {
                yield break;
            }
            yield return Stage01Boot();
            if (!Ready())
            {
                yield break;
            }

            _main.LoadLevel(20);
            yield return WaitPhysics(10);
            _player.ControlEnabled = false;
            Check(Groups.Count(Groups.Cage) == 1, "niveau 21 : une cage");
            Check(Groups.Count(Groups.Breakable) == 0, "niveau 21 : l'acier n'est pas cassable");
            Cage steelCage = First<Cage>(Groups.Cage);

            _player.Teleport(DesignSpace.ToUnity(new Vector3(0f, 0.05f, -2.6f)));
            _player.SetLook(0f, 0f);
            yield return WaitPhysics(2);
            // A placement squarely on the cage: a lavender one would vanish here.
            Check(_placer.Hold("caisse"), "photo en main face a l'acier");
            Check(_placer.Place(), "pose acceptee face a l'acier");
            yield return WaitPhysics(3);
            Check(Alive(steelCage), "la cage d'acier survit a une pose qui attrape son centre");

            // The interaction ray does not pass either: the caged battery is a
            // model, not a pickup.
            _player.UpdateInteractTarget();
            Check(_player.InteractPrompt != "E : ramasser la pile", "la pile sous acier reste hors de portee");

            // But the lens does pass.
            CameraItem cameraItem = First<CameraItem>(Groups.CameraItem);
            Check(cameraItem != null, "niveau 21 : un appareil photo");
            if (cameraItem != null)
            {
                cameraItem.Interact(_player);
            }
            _player.ToggleViewfinder();
            Check(_player.CapturePhoto(), "cliche pris a travers l'acier");
            PhotoDef steelShot = PhotoDefs.GetDef(_placer.HeldId);
            Check(CountProps(steelShot, "battery") == 2, "les deux piles sous acier tiennent dans un seul cliche");
            _placer.Drop();
        }

        /// <summary>
        /// Stage 21. Level 22: lead. The battery is there, three metres in front
        /// of the lens, and the film comes back without it.
        /// </summary>
        public IEnumerator Stage21Lead()
        {
            if (!_ran.Add(21))
            {
                yield break;
            }
            yield return Stage01Boot();
            if (!Ready())
            {
                yield break;
            }

            _main.LoadLevel(21);
            yield return WaitPhysics(10);
            _player.ControlEnabled = false;
            LevelDef def = LevelDefs.GetDef(21);
            if (def == null)
            {
                Fail("niveau 22 : toutes les piles construites, plombees comprises");
                yield break;
            }
            Check(Groups.Count(Groups.Battery) == def.Batteries.Count + def.SealedBatteries.Count,
                "niveau 22 : toutes les piles construites, plombees comprises");
            Check(Groups.Count(Groups.CopyableBattery) == def.Batteries.Count,
                "niveau 22 : seules les piles vives sont photocopiables");

            Battery lead = null;
            List<Battery> batteries = Groups.Snapshot<Battery>(Groups.Battery);
            for (int i = 0; i < batteries.Count; i++)
            {
                if (batteries[i].IsSealed)
                {
                    lead = batteries[i];
                }
            }
            Check(lead != null, "la pile plombee est dans le decor");
            if (lead == null)
            {
                yield break;
            }

            // Stand right in front of it and shoot: the film comes back empty.
            Vector3 leadDesign = DesignSpace.ToUnity(lead.transform.position);
            _player.Teleport(DesignSpace.ToUnity(leadDesign + new Vector3(0f, 0.05f, 3.2f)));
            _player.SetLook(0f, 0f);
            yield return WaitFrames(2);
            CameraItem cameraItem = First<CameraItem>(Groups.CameraItem);
            Check(cameraItem != null, "niveau 22 : un appareil photo");
            if (cameraItem != null)
            {
                cameraItem.Interact(_player);
            }
            _player.ToggleViewfinder();
            Check(_player.CapturePhoto(), "cliche pris sur la pile plombee");
            PhotoDef leadShot = PhotoDefs.GetDef(_placer.HeldId);
            Check(CountProps(leadShot, "battery") == 0, "aucune pile plombee ne s'imprime sur la pellicule");
            _placer.Drop();
        }

        /// <summary>
        /// Stage 22. Level 13: A FLIGHT PLACED FROM THE LANDING OF A FLIGHT.
        /// This is the whole level, and it is the kind of claim that has to be
        /// measured rather than asserted: the sky ramp it used to be built on
        /// died when the painted back moved out to three times its old distance,
        /// and nothing but a run in the engine proves what replaced it actually
        /// carries the player.
        /// </summary>
        public IEnumerator Stage22TwoFlights()
        {
            if (!_ran.Add(22))
            {
                yield break;
            }
            yield return Stage01Boot();
            if (!Ready())
            {
                yield break;
            }

            _main.LoadLevel(12);
            yield return WaitPhysics(10);
            const float towerTop = 8.0f;
            // Standing ON the first flight is part of the claim, so the controls
            // stay live for this stage.
            _player.ControlEnabled = true;
            Stand(new Vector3(0f, 0.05f, 3.0f));
            yield return WaitPhysics(4);
            Check(_placer.Hold("escalier"), "premiere volee en main");
            Check(_placer.Place(), "premiere volee posee depuis le sol");
            yield return WaitPhysics(10);

            // The invisible walkable ramp of a flight, sampled near its top.
            RaycastHit rampHit;
            bool hasRamp = RayDesign(new Vector3(0f, 7.0f, -4.6f), new Vector3(0f, 0.5f, -4.6f), out rampHit);
            Check(hasRamp, "la premiere volee offre une surface ou marcher");
            float landing = 0f;
            if (hasRamp)
            {
                landing = rampHit.point.y;
                CheckBetween(landing, 3.5f, 5.2f, "palier de la premiere volee a la hauteur prevue");
            }

            // Stand ON that landing and place the second flight from there.
            _player.Teleport(DesignSpace.ToUnity(new Vector3(0f, landing + 0.1f, -4.6f)));
            _player.SetLook(0f, 0f);
            yield return WaitPhysics(8);
            Check(_player.IsGrounded, "le joueur tient debout sur la volee posee");
            Check(_placer.Hold("escalier"), "seconde volee en main");
            Check(_placer.Place(), "seconde volee posee depuis le palier de la premiere");
            yield return WaitPhysics(10);

            // Somewhere along the second flight there must be ground high enough
            // that a jump reaches the tower. Sample it in front of the tower face.
            RaycastHit highHit;
            bool hasHigh = RayDesign(new Vector3(0f, 12.0f, -9.8f), new Vector3(0f, 4.0f, -9.8f), out highHit);
            Check(hasHigh, "la seconde volee monte bien au dessus de la premiere");
            if (hasHigh)
            {
                float reached = highHit.point.y;
                Check(reached > landing + 1.0f, string.Format(Inv,
                    "la seconde volee gagne de la hauteur sur la premiere ({0:F2} puis {1:F2})", landing, reached));
                Check(reached + 1.509f >= towerTop, string.Format(Inv,
                    "depuis la seconde volee, un saut atteint le sommet de la tour ({0:F2} + 1.51 pour {1:F2})",
                    reached, towerTop));
            }
            _player.ControlEnabled = false;
        }

        /// <summary>
        /// Stage 23. Every level must build without error and honor its own
        /// definition, and it must do so here, at the end of a session that
        /// placed, carved, broke, rewound and fell: a rebuild that only works
        /// from a clean boot is not a rebuild.
        /// </summary>
        public IEnumerator Stage23EveryLevel()
        {
            if (!_ran.Add(23))
            {
                yield break;
            }
            yield return Stage01Boot();
            if (!Ready())
            {
                yield break;
            }
            _player.ControlEnabled = false;

            // Counted, because a loop over an empty catalog would assert nothing
            // at all and the stage would look exactly like a pass.
            int rebuilt = 0;
            for (int i = 0; i < LevelDefs.Count; i++)
            {
                rebuilt++;
                _main.LoadLevel(i);
                yield return WaitFrames(2);
                LevelDef def = LevelDefs.GetDef(i);
                if (def == null)
                {
                    Fail(string.Format(Inv, "niveau {0} : definition absente", i + 1));
                    continue;
                }
                int breakableCages = 0;
                for (int c = 0; c < def.Cages.Count; c++)
                {
                    if (!def.Cages[c].Sealed)
                    {
                        breakableCages++;
                    }
                }
                string where = string.Format(Inv, "niveau {0}", i + 1);
                Check(Groups.Count(Groups.PhotoItem) == def.Photos.Count, where + " : photos construites");
                Check(Groups.Count(Groups.Battery) == def.Batteries.Count + def.SealedBatteries.Count,
                    where + " : piles construites");
                Check(Groups.Count(Groups.CopyableBattery) == def.Batteries.Count,
                    where + " : le plomb reste hors de la pellicule");
                Check(Groups.Count(Groups.Teleporter) == 1, where + " : teleporteur construit");
                Check(Groups.Count(Groups.Platform) == def.Platforms.Count, where + " : plateformes construites");
                Check(Groups.Count(Groups.Cage) == def.Cages.Count, where + " : cages construites");
                Check(Groups.Count(Groups.Breakable) == breakableCages, where + " : cages cassables construites");
            }
            Check(rebuilt > 0 && rebuilt == LevelDefs.Count,
                "toute la campagne a ete reconstruite au moins une fois");
            Check(State.RequiredBatteries == 5, "niveau 25 : cinq piles requises");
        }

        /// <summary>
        /// Stage 24. Losing costs the level: falling below killY rebuilds it from
        /// scratch, so nothing the player had placed or carried survives the fall.
        /// </summary>
        public IEnumerator Stage24Fall()
        {
            if (!_ran.Add(24))
            {
                yield break;
            }
            yield return Stage01Boot();
            if (!Ready())
            {
                yield break;
            }

            _main.LoadLevel(0);
            yield return WaitPhysics(20);
            // The fall is detected in the controller's own step: the controls have
            // to be live or nothing falls out at all.
            _player.ControlEnabled = true;
            Check(_placer.Hold("passerelle"), "photo en main avant la chute");
            Stand(new Vector3(0f, 0.05f, -2.2f));
            Check(_placer.Place(), "pose faite avant la chute");
            Battery battery = First<Battery>(Groups.Battery);
            if (battery == null)
            {
                Fail("pile portee avant la chute");
                yield break;
            }
            battery.Interact(_player);
            Check(State.CarriedBatteries == 1, "pile portee avant la chute");
            yield return WaitPhysics(3);
            Check(Groups.Count(Groups.PlacedContent) == 1, "contenu pose present avant la chute");

            _player.Teleport(DesignSpace.ToUnity(new Vector3(0f, -50f, 0f)));
            yield return WaitPhysics(4);
            yield return WaitUntil(delegate
            {
                return Groups.Count(Groups.PlacedContent) == 0 && _player.transform.position.y > -10f;
            }, 15f);
            yield return WaitFrames(2);

            Check(_player.transform.position.y > -10.0f, "chute rattrapee : le joueur est revenu au depart");
            Check(Groups.Count(Groups.PlacedContent) == 0, "la chute efface les poses du niveau");
            Check(Groups.Count(Groups.PhotoItem) == 1, "la chute rend la photo consommee");
            Check(Groups.Count(Groups.Battery) == 1, "la chute remet la pile ramassee dans le decor");
            Check(State.CarriedBatteries == 0, "la chute vide l'inventaire de piles");
            Check(_player.ControlEnabled, "le joueur reprend la main apres la chute");
        }
    }

    /// <summary>
    /// The probe as NUnit cases: one per stage, so a failure names the stage
    /// that broke instead of failing one giant test. Each case loads the real
    /// scene through the real boot path, then runs its stage; a stage pulls in
    /// whatever earlier stage it needs to be meaningful (the door stage needs a
    /// booted game, the stacking stage needs level 1 loaded), which is why the
    /// heavier ones are given a generous timeout.
    /// </summary>
    public sealed class SmokeTests
    {
        const string ScenePath = "Assets/Scenes/Main.unity";
        const int StageTimeoutMs = 300000;

        SmokeProbe _probe;

        [UnitySetUp]
        public IEnumerator SetUp()
        {
            // A test run must not inherit the previous one's progression: the
            // level grid would unlock levels this case never reached.
            PlayerPrefs.DeleteKey(GameState.ProgressKey);
            GameState.Instance = null;

            // The registries the game keeps in STATIC fields outlive a scene
            // load, so they are reset HERE and not in the teardown: a case that
            // died mid stage must not hand the next one its groups, the shots it
            // took or a key it left held down. Before the load and not after,
            // because the load is deferred to the end of the frame: the scene
            // this clears is the previous one, and nothing the new Main builds in
            // Awake registers in any of them.
            ViewpointInput.ResetSimulation();
            Groups.Clear();
            PhotoDefs.ClearDynamic();
            // The material cache is deliberately NOT cleared: it already answers
            // for a destroyed entry by rebuilding, and clearing it would leak a
            // full set of materials per case.

            SceneManager.LoadScene(ScenePath, LoadSceneMode.Single);
            yield return null;
            yield return null;

            // Fully qualified: this file also imports System, where Object is a
            // different type entirely.
            Main main = UnityEngine.Object.FindAnyObjectByType<Main>();
            Assert.IsNotNull(main, "la scene Main ne porte pas de composant Main");

            // Created after the scene load, or the single-mode load would take it
            // down with the previous scene.
            GameObject host = new GameObject("SmokeProbe");
            _probe = host.AddComponent<SmokeProbe>();
            // Bind, not Setup: Setup is the command line path, which runs the
            // whole scenario by itself and exits the process.
            _probe.Bind(main);
            yield return null;
        }

        [UnityTearDown]
        public IEnumerator TearDown()
        {
            // The same statics as the setup, cleared on the way out as well: the
            // suite that runs next may not be this one, and no other suite should
            // inherit a level's groups or a shot this probe took. No live
            // component reads either of them per frame, so clearing them under a
            // scene that is about to be torn down is safe.
            ViewpointInput.ResetSimulation();
            Groups.Clear();
            PhotoDefs.ClearDynamic();
            // Stage 4 and stage 23 reach level 2 and level 25, and GameState
            // PERSISTS that: BeginLevel writes the furthest level to PlayerPrefs
            // and saves it to disk at once. Cleared on the way out as well as on
            // the way in, so the suite leaves neither the next suite nor the
            // developer's own save file with a campaign it never played.
            PlayerPrefs.DeleteKey(GameState.ProgressKey);
            PlayerPrefs.Save();
            if (_probe != null)
            {
                UnityEngine.Object.Destroy(_probe.gameObject);
                _probe = null;
            }
            yield return null;
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_01_le_jeu_demarre_sur_le_niveau_1()
        {
            yield return _probe.Stage01Boot();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_02_la_photo_passerelle_se_ramasse()
        {
            yield return _probe.Stage02TakeBridgePhoto();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_03_la_passerelle_enjambe_le_vide()
        {
            yield return _probe.Stage03PlaceBridge();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_04_la_pile_et_le_teleporteur()
        {
            yield return _probe.Stage04BatteryAndTeleporter();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_05_la_photo_pile_duplique_une_pile()
        {
            yield return _probe.Stage05DuplicateBattery();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_06_la_porte_se_traverse_a_pied()
        {
            yield return _probe.Stage06Door();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_07_la_cage_encadree_disparait()
        {
            yield return _probe.Stage07Cage();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_08_la_console_tournee_passe_en_hauteur()
        {
            yield return _probe.Stage08RolledConsole();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_08b_le_quart_de_tour_va_dans_le_sens_de_l_image()
        {
            yield return _probe.Stage08bQuarterTurn();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_09_le_coffret_materialise_une_photo()
        {
            yield return _probe.Stage09PhotoInPhoto();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_10_le_fond_peint_devient_un_plancher()
        {
            yield return _probe.Stage10BackdropFloor();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_11_recharger_le_niveau_efface_tout()
        {
            yield return _probe.Stage11Reload();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_12_le_rembobinage_defait_le_monde()
        {
            yield return _probe.Stage12Rewind();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_13_la_caisse_retournee_tombe()
        {
            yield return _probe.Stage13FallingCrate();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_14_deux_caisses_s_empilent()
        {
            yield return _probe.Stage14StackedCrates();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_15_reposer_une_pile()
        {
            yield return _probe.Stage15DropBattery();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_16_la_photo_levee_tourne_sur_le_hud()
        {
            yield return _probe.Stage16RaisedPicture();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_17_le_cliche_du_ciel_fauche_la_cage()
        {
            yield return _probe.Stage17SkyShot();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_18_le_cliche_de_la_planche_est_fidele()
        {
            yield return _probe.Stage18PlankCopy();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_19_l_objectif_passe_entre_les_barreaux()
        {
            yield return _probe.Stage19ThroughTheBars();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_20_l_acier_ne_cede_qu_a_l_objectif()
        {
            yield return _probe.Stage20Steel();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_21_le_plomb_ne_s_imprime_pas()
        {
            yield return _probe.Stage21Lead();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_22_une_volee_posee_depuis_une_volee()
        {
            yield return _probe.Stage22TwoFlights();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_23_les_vingt_cinq_niveaux_se_reconstruisent()
        {
            yield return _probe.Stage23EveryLevel();
            _probe.AssertNoFailures();
        }

        [UnityTest]
        [NUnit.Framework.Timeout(StageTimeoutMs)]
        public IEnumerator Etape_24_la_chute_recommence_le_niveau()
        {
            yield return _probe.Stage24Fall();
            _probe.AssertNoFailures();
        }
    }
}
