using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using Meuble.Core;
using UnityEngine;

namespace Meuble.Tests
{
    /// <summary>
    /// The shared designer route replay (docs/CONTRACT_M5_v3.md 15.9, CONTRACT_M5.md 16.11), used by the M4 level replays
    /// (step 35), the M5 level replays (step 45) and the full playthrough (step 40). It plays the current level's
    /// designerRoute through the real game, as ProbeTestsM2 step 20 does: at game time "at" (shifted by the offset), drive
    /// straight toward (x, z) at full input, release within 0.1 m, then wait for the next "at" (a passed "at" starts the
    /// next leg on the same step). The route step fields:
    /// <list type="bullet">
    /// <item>"careful" holds the careful key for the leg (FurnitureController.ScriptedCareful, CONTRACT_M4 9.3);</item>
    /// <item>a gliding body that stops at a waypoint releases at max(0.1, v * 0.2 + 0.1) m, so the glide ends there;</item>
    /// <item>"toggle" presses E at "at" (InputReader.InjectAction) and the next leg waits for the switch to end;</item>
    /// <item>"rightup" presses a move key (InputReader.InjectMovePress) and waits for the stool to stand;</item>
    /// <item>M5 "open" (with "door") waits for the furniture to be still (E acts only then, CONTRACT_M5_v3 15.2), presses
    /// E, and waits for the opening (an External action) to end. A press that starts no action is pressed again, at most
    /// <see cref="MaxOpenPresses"/> times; then the replay goes on and the result counts the failure.</item>
    /// <item>M6 "hide" and "leave" (LevelAudit.RouteHide and RouteLeave, CONTRACT_M6 2.5) are played like "open": the
    /// furniture still at (x, z), E is pressed at "at" and the next leg waits for the 0.5 s wardrobe action to end.</item>
    /// </list>
    /// CONTRACT_M4 9.8: no scripted input while the furniture is pinned (sat on), and for one step after.
    /// M5 wave 5B: the rocking chair's rock and the robot's shove are actions that ignore input; the replay keeps steering
    /// toward its waypoint through them, so the leg simply resumes when they end. The result counts the 5B events (crashes,
    /// shoves, robot contacts, rocks and noises the hum masked) and whether the load still rides at the end.
    /// The input is decided at the end of each fixed step (GameState.FixedStepped), so the replay does not depend on
    /// timeScale. A run ends when the level is won or lost, or at the route end + <see cref="CapAfterRoute"/> s of game
    /// time (CONTRACT_M5 16.11). A real time guard only protects the test run if game time stops advancing.
    /// The result also records what the run showed, up to and including the step that ended it: the openings (when the
    /// first one started), a swinging leaf seen by a watcher that counts for the catch, the furniture seen before the
    /// first opening, and the highest floor the furniture stood on.
    /// </summary>
    public static class RouteReplayer
    {
        /// <summary>CONTRACT_M5 16.11: a run stops this many seconds of game time after the last "at" (plus the offset).</summary>
        public const float CapAfterRoute = 30f;
        /// <summary>An "open" press that starts no action is pressed again, at most this many presses in all.</summary>
        public const int MaxOpenPresses = 5;
        /// <summary>Fixed steps to wait for a press to start its action before pressing again.</summary>
        public const int PressWaitSteps = 2;
        /// <summary>Real seconds after which a run stops even if game time did not reach the cap (a stalled game).</summary>
        public const float RealTimeGuard = 900f;
        /// <summary>M6: the route action that enters the wardrobe (LevelAudit.RouteHide).</summary>
        public const string ActionHide = "hide";
        /// <summary>M6: the route action that leaves the wardrobe (LevelAudit.RouteLeave).</summary>
        public const string ActionLeave = "leave";

        /// <summary>The route actions that press E and wait for an External action: "open", "hide" and "leave".</summary>
        public static bool IsPress(string action) =>
            action == RouteStepDef.ActionOpen || action == ActionHide || action == ActionLeave;

        /// <summary>What one replay did. Counters are the differences over the run.</summary>
        public sealed class Result
        {
            public string Level;
            public float Offset;
            public PlayState State;
            public LoseReason Reason;
            /// <summary>Game time at the end of the run (GameState.Elapsed).</summary>
            public float Time;
            /// <summary>The game time cap of the run (the route end + offset + CapAfterRoute).</summary>
            public float Cap;
            /// <summary>The run reached its game time cap while still playing.</summary>
            public bool TimedOut;
            /// <summary>The run hit the real time guard (game time stalled).</summary>
            public bool Stalled;
            public int Discoveries;
            public int Alerts;
            public int Creaks;
            public int Explained;
            public int Topples;
            public int Toggles;
            public int SwitchOns;
            public int SatOn;
            public int Pratfalls;
            public int Barks;
            /// <summary>M5: External actions started (door openings) during the run. Wave 5B: a rock of the rocking chair (an
            /// External action GameState starts on its rest step) is not an opening.</summary>
            public int Opens;
            /// <summary>M5: E presses made for "open" steps (retries included).</summary>
            public int OpenPresses;
            /// <summary>M5: "open" steps given up after <see cref="MaxOpenPresses"/> presses that started nothing.</summary>
            public int OpenFailures;
            /// <summary>M5: doors GameState counts as opened by the player during the run (GameState.DoorOpenCount).</summary>
            public int DoorOpens;
            /// <summary>M5: game time at which the first opening (an External action) started, or -1.</summary>
            public float FirstOpenAt = -1f;
            /// <summary>M5: a watcher that counts for the catch saw a swinging leaf on some step (GameState.LeafSeen).</summary>
            public bool LeafSeen;
            /// <summary>M5: the furniture's own samples were seen (GameState.Seen) on a step before the first opening.</summary>
            public bool SeenBeforeOpen;
            /// <summary>M5: the highest floor the furniture stood on (its transform's y, FloorMap height on a platform).</summary>
            public float TopY;
            public bool Pinned;
            /// <summary>The game time the furniture was first sat on (pinned), -1 when never.</summary>
            public float FirstSatAt = -1f;
            public float TopSpeed;
            /// <summary>M5 wave 5B: load falls (GameState.CrashCount) during the run.</summary>
            public int Crashes;
            /// <summary>M5 wave 5B: robot shoves accepted (GameState.ShoveCount) during the run.</summary>
            public int Shoves;
            /// <summary>M5 wave 5B: robot contacts (GameState.RobotContactCount), shoved or not, during the run.</summary>
            public int RobotContacts;
            /// <summary>M5 wave 5B: rocks of the rocking chair (GameState.RockCount) during the run.</summary>
            public int Rocks;
            /// <summary>M5 wave 5B: hops, rolls and clicks the robot's hum masked (GameState.MaskedNoiseCount) during the run.</summary>
            public int MaskedNoises;
            /// <summary>M5 wave 5B: the level has a load (GameState.Load) and it still rides at the end of the run.</summary>
            public bool LoadHeld;
            /// <summary>M5 wave 5B: the level gave the player a load (GameState.Load is not null).</summary>
            public bool HasLoad;
            /// <summary>M6: wardrobe hides completed (GameState.HideCount) and leaves started (GameState.LeaveCount).</summary>
            public int Hides;
            public int Leaves;
            /// <summary>The route step reached (the count of steps done) and the route length.</summary>
            public int Waypoint;
            public int Waypoints;

            public bool Won => State == PlayState.Won;

            public string Label => string.Format(CultureInfo.InvariantCulture, "{0} (offset {1:+0.0;-0.0;0} s)", Level, Offset);

            public override string ToString()
            {
                return string.Format(CultureInfo.InvariantCulture,
                    "{0}: {1} ({2}) after {3:0.0} s (cap {4:0.0} s{5}), waypoint {6}/{7}, {8} discoveries, {9} alerts, {10} creaks, "
                    + "{11} explained steps, {12} topples, top speed {13:0.00} m/s, {14} toggles, {15} switch-ons, sat on {16}, {17} pratfalls, "
                    + "{18} barks, {19} opens ({20} presses, {21} failed, {22} doors, first at {23:0.0} s), leaf seen {24}, seen before opening {25}, "
                    + "top floor {26:0.00} m, first sat on at {27:0.0} s, {28} crashes (load {29}), {30} shoves, {31} robot contacts, {32} rocks, "
                    + "{33} noises masked by the hum, {34} hides, {35} leaves",
                    Label, State, Reason, Time, Cap, TimedOut ? ", timed out" : Stalled ? ", stalled" : "", Waypoint, Waypoints, Discoveries,
                    Alerts, Creaks, Explained, Topples, TopSpeed, Toggles, SwitchOns, SatOn, Pratfalls, Barks, Opens, OpenPresses, OpenFailures,
                    DoorOpens, FirstOpenAt, LeafSeen, SeenBeforeOpen, TopY, FirstSatAt, Crashes,
                    HasLoad ? (LoadHeld ? "held" : "fell") : "none", Shoves, RobotContacts, Rocks, MaskedNoises, Hides, Leaves);
            }
        }

        /// <summary>The game time cap of a route replayed at <paramref name="offset"/>: its last "at" + offset + 30 s.</summary>
        public static float CapOf(IList<RouteStepDef> route, float offset)
        {
            float end = 0f;
            if (route != null)
            {
                foreach (RouteStepDef s in route)
                {
                    end = Mathf.Max(end, s.At);
                }
            }
            return Mathf.Max(0f, end + offset) + CapAfterRoute;
        }

        /// <summary>
        /// Replays the designerRoute of the level <paramref name="game"/> is playing, from its current state (load or restart
        /// the level first), at <paramref name="timeScale"/>, every "at" shifted by <paramref name="offset"/> seconds.
        /// Fills <paramref name="result"/>; the caller asserts.
        /// </summary>
        public static IEnumerator Replay(GameState game, float offset, Result result, float timeScale = Tuning.PlaythroughTimeScale,
            List<RouteStepDef> routeOverride = null)
        {
            // M7 design (CONTRACT_M7 4.1): Step64b_ replays the level's designerRouteHard at Difficile through this override.
            List<RouteStepDef> route = routeOverride ?? game.Def.DesignerRoute ?? new List<RouteStepDef>();
            FurnitureController furniture = game.Furniture;
            result.Level = game.LevelId;
            result.Offset = offset;
            result.Waypoints = route.Count;
            result.Cap = CapOf(route, offset);
            int k = 0;
            bool driving = false;
            bool acting = false;
            bool started = false;
            int waited = 0;
            int presses = 0;
            int afterPin = 0;
            bool wasExternal = false;
            bool ended = false;
            int toggles0 = furniture.ToggleCount;
            int topples0 = furniture.ToppleCount;
            int discoveries0 = game.DiscoveryCount;
            int alerts0 = game.AlertCount;
            int creaks0 = game.CreakCount;
            int explained0 = game.ExplainedByDecoySteps;
            int switchOns0 = game.SwitchOnCount;
            int satOn0 = game.SatOnPlayerCount;
            int pratfalls0 = game.PratfallCount;
            int barks0 = game.BarkCount;
            int doorOpens0 = game.DoorOpenCount;
            int crashes0 = game.CrashCount;
            int shoves0 = game.ShoveCount;
            int contacts0 = game.RobotContactCount;
            int rocks0 = game.RockCount;
            int masked0 = game.MaskedNoiseCount;
            int hides0 = game.HideCount;
            int leaves0 = game.LeaveCount;
            int rocksSeen = game.RockCount;
            bool rockedLastStep = false;
            result.TopY = furniture.transform.position.y;

            // E acts on a door only when the furniture is still, upright, free and in no action (CONTRACT_M5_v3 15.2).
            bool Still(FurnitureController f) => !f.IsMoving && !f.Gliding && !f.ActionActive && !f.Tipped && !f.Pinned && !f.Carried;

            void Drive()
            {
                FurnitureController f = game.Furniture;
                if (ended)
                {
                    // Steps that run after the level ended (several fixed steps can run in one frame) record nothing.
                    f.ScriptedDirection = null;
                    return;
                }
                // What this step showed, recorded before the state check: the step that ends the run counts too.
                bool external = f.ActionActive && f.Action == FurnitureController.BodyAction.External;
                // Wave 5B: the rock starts as an External action on the step GameState counts it (or the next one).
                bool rockNow = game.RockCount != rocksSeen;
                bool rockStarted = rockNow || rockedLastStep;
                rockedLastStep = rockNow;
                rocksSeen = game.RockCount;
                // M6: a wardrobe entry or exit is an External action too, but not an opening.
                bool wardrobe = game.Wardrobe != GameState.WardrobeStage.None;
                if (external && !wasExternal && !rockStarted && !wardrobe)
                {
                    result.Opens++;
                    if (result.FirstOpenAt < 0f)
                    {
                        result.FirstOpenAt = game.Elapsed;
                    }
                }
                wasExternal = external;
                result.LeafSeen |= game.LeafSeen;
                result.SeenBeforeOpen |= game.Seen && result.FirstOpenAt < 0f;
                result.TopY = Mathf.Max(result.TopY, f.transform.position.y);
                if (game.State != PlayState.Playing)
                {
                    ended = true;
                    f.ScriptedDirection = null;
                    return;
                }
                result.TopSpeed = Mathf.Max(result.TopSpeed, f.PlanarSpeed);
                result.Pinned |= f.Pinned;
                if (f.Pinned && result.FirstSatAt < 0f)
                {
                    result.FirstSatAt = game.Elapsed;
                }
                if (f.Pinned)
                {
                    // CONTRACT_M4 9.8: no scripted input while sat on, and for one step after.
                    f.ScriptedDirection = null;
                    afterPin = 1;
                    return;
                }
                if (afterPin > 0)
                {
                    afterPin--;
                    f.ScriptedDirection = null;
                    return;
                }
                if (acting)
                {
                    f.ScriptedDirection = null;
                    if (f.ActionActive || f.Tipped)
                    {
                        started = true;
                        return;
                    }
                    if (!started && k < route.Count && IsPress(route[k].Action))
                    {
                        // The press started nothing (refused or not claimed): wait a little, then press again when still.
                        if (++waited < PressWaitSteps)
                        {
                            return;
                        }
                        if (presses < MaxOpenPresses)
                        {
                            if (Still(f))
                            {
                                InputReader.InjectAction();
                                presses++;
                                result.OpenPresses++;
                                waited = 0;
                            }
                            return;
                        }
                        result.OpenFailures++;
                    }
                    acting = false;
                    k++;
                }
                while (k < route.Count)
                {
                    RouteStepDef w = route[k];
                    f.ScriptedCareful = w.Careful;
                    if (!driving)
                    {
                        if (game.Elapsed < Mathf.Max(0f, w.At + offset) - 1e-4f)
                        {
                            f.ScriptedDirection = null;
                            return;
                        }
                        driving = true;
                    }
                    if (IsPress(w.Action))
                    {
                        f.ScriptedDirection = null;
                        if (!Still(f))
                        {
                            return;
                        }
                        InputReader.InjectAction();
                        presses = 1;
                        result.OpenPresses++;
                        waited = 0;
                        started = false;
                        acting = true;
                        driving = false;
                        return;
                    }
                    if (w.Action == RouteStepDef.ActionToggle || w.Action == RouteStepDef.ActionRightUp)
                    {
                        // CONTRACT_M4 9.3, as in M4: pressed at "at", the next leg waits for the action to end.
                        f.ScriptedDirection = null;
                        if (w.Action == RouteStepDef.ActionToggle)
                        {
                            InputReader.InjectAction();
                        }
                        else
                        {
                            InputReader.InjectMovePress();
                        }
                        started = true;
                        acting = true;
                        driving = false;
                        return;
                    }
                    Vector3 to = YawMath.Planar(new Vector3(w.X, 0f, w.Z) - f.transform.position);
                    bool stops = k + 1 >= route.Count || game.Elapsed < route[k + 1].At + offset - 1e-4f;
                    float release = f.Body.Glides && stops
                        ? Mathf.Max(0.1f, f.Velocity.magnitude * Tuning.OfficeChairStopTime * 0.5f + 0.1f)
                        : 0.1f;
                    if (to.magnitude > release)
                    {
                        f.ScriptedDirection = to.normalized;
                        return;
                    }
                    driving = false;
                    k++;
                }
                f.ScriptedDirection = null;
            }

            game.FixedStepped += Drive;
            var stalled = new bool[1];
            try
            {
                yield return RunUntil(game, result.Cap, () => game.State != PlayState.Playing, timeScale, stalled);
                result.Stalled = stalled[0];
            }
            finally
            {
                game.FixedStepped -= Drive;
                if (game.Furniture != null)
                {
                    game.Furniture.ScriptedDirection = null;
                    game.Furniture.ScriptedCareful = null;
                }
            }
            FurnitureController end = game.Furniture;
            result.State = game.State;
            result.Reason = game.LoseReason;
            result.Time = game.Elapsed;
            result.TimedOut = game.State == PlayState.Playing && game.Elapsed >= result.Cap - 1e-4f;
            result.Discoveries = game.DiscoveryCount - discoveries0;
            result.Alerts = game.AlertCount - alerts0;
            result.Creaks = game.CreakCount - creaks0;
            result.Explained = game.ExplainedByDecoySteps - explained0;
            result.Topples = end.ToppleCount - topples0;
            result.Toggles = end.ToggleCount - toggles0;
            result.SwitchOns = game.SwitchOnCount - switchOns0;
            result.SatOn = game.SatOnPlayerCount - satOn0;
            result.Pratfalls = game.PratfallCount - pratfalls0;
            result.Barks = game.BarkCount - barks0;
            result.DoorOpens = game.DoorOpenCount - doorOpens0;
            result.Crashes = game.CrashCount - crashes0;
            result.Shoves = game.ShoveCount - shoves0;
            result.RobotContacts = game.RobotContactCount - contacts0;
            result.Rocks = game.RockCount - rocks0;
            result.MaskedNoises = game.MaskedNoiseCount - masked0;
            result.Hides = game.HideCount - hides0;
            result.Leaves = game.LeaveCount - leaves0;
            result.HasLoad = game.Load != null;
            result.LoadHeld = game.CarryingLoad;
            result.Waypoint = k;
        }

        /// <summary>Runs the game for <paramref name="gameSeconds"/> of game time from now, or until <paramref name="until"/>.</summary>
        public static IEnumerator RunFor(GameState game, float gameSeconds, Func<bool> until, float timeScale)
        {
            return RunUntil(game, game.Elapsed + gameSeconds, until, timeScale, new bool[1]);
        }

        /// <summary>
        /// Runs the game at <paramref name="timeScale"/> until <paramref name="until"/> holds or the game time
        /// (GameState.Elapsed) reaches <paramref name="gameTimeCap"/>. A real time guard (<see cref="RealTimeGuard"/>) stops
        /// a stalled game and sets <paramref name="stalled"/>[0]. timeScale is restored to 1.
        /// </summary>
        public static IEnumerator RunUntil(GameState game, float gameTimeCap, Func<bool> until, float timeScale, bool[] stalled)
        {
            float realStart = UnityEngine.Time.realtimeSinceStartup;
            UnityEngine.Time.timeScale = timeScale;
            try
            {
                while (!until() && game.Elapsed < gameTimeCap - 1e-4f)
                {
                    if (UnityEngine.Time.realtimeSinceStartup - realStart > RealTimeGuard)
                    {
                        stalled[0] = true;
                        Debug.LogWarning($"[RouteReplayer] {game.LevelId}: real time guard after {RealTimeGuard} s at game time {game.Elapsed:0.0} s");
                        break;
                    }
                    yield return null;
                }
            }
            finally
            {
                UnityEngine.Time.timeScale = 1f;
            }
        }
    }
}
