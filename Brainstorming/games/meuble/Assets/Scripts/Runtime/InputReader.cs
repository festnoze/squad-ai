using System;
using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.Controls;

namespace OutOfSight
{
    /// <summary>
    /// Device reads (Input System package only). Keys are read by physical position: wKey is the key in
    /// the W position, which an AZERTY keyboard labels Z, so ZQSD works with no separate binding (PRD 9).
    /// </summary>
    public static class InputReader
    {
        /// <summary>
        /// Movement intent, x right and y forward, magnitude at most 1. The arrow keys count exactly like WASD/ZQSD
        /// (same v.x/v.y accumulation), and the gamepad D-pad exactly like the left stick: either moves the furniture.
        /// While <see cref="InjectMoveVector"/> set a value (PlayMode tests cannot drive a keyboard device headless),
        /// it is returned instead of reading any device; <see cref="ClearMoveVector"/> (or <see cref="ResetInjections"/>)
        /// goes back to reading one.
        /// </summary>
        public static Vector2 Move()
        {
            if (injectedMoveVector.HasValue)
            {
                return Vector2.ClampMagnitude(injectedMoveVector.Value, 1f);
            }
            Vector2 v = Vector2.zero;
            Keyboard k = Keyboard.current;
            if (k != null)
            {
                if (k.wKey.isPressed || k.upArrowKey.isPressed) v.y += 1f;
                if (k.sKey.isPressed || k.downArrowKey.isPressed) v.y -= 1f;
                if (k.dKey.isPressed || k.rightArrowKey.isPressed) v.x += 1f;
                if (k.aKey.isPressed || k.leftArrowKey.isPressed) v.x -= 1f;
            }
            Gamepad g = Gamepad.current;
            if (g != null)
            {
                Vector2 stick = g.leftStick.ReadValue();
                if (stick.sqrMagnitude > 0.04f)
                {
                    v += stick;
                }
                Vector2 dpad = g.dpad.ReadValue();
                if (dpad.sqrMagnitude > 0.04f)
                {
                    v += dpad;
                }
            }
            // M7 (CONTRACT_M7 1.5): the floating touch stick, with the left stick's dead zone.
            if (touchStick.sqrMagnitude > StickDeadZoneSq)
            {
                v += touchStick;
            }
            return Vector2.ClampMagnitude(v, 1f);
        }

        private static Vector2? injectedMoveVector;

        /// <summary>
        /// Tests: <see cref="Move"/> returns this value until <see cref="ClearMoveVector"/>, with no real device read.
        /// Proves the furniture reacts to a move vector exactly as it would to a real key or stick, with no real
        /// keyboard or gamepad device to drive headlessly: inject the same vector the arrow keys (or the D-pad) would
        /// produce to prove they move the furniture like any other move key.
        /// </summary>
        public static void InjectMoveVector(Vector2 value)
        {
            injectedMoveVector = value;
        }

        /// <summary>Tests: <see cref="Move"/> goes back to reading a real device.</summary>
        public static void ClearMoveVector()
        {
            injectedMoveVector = null;
        }

        /// <summary>Mouse motion this frame in pixels (zero when the window has no focus).</summary>
        public static Vector2 LookDeltaPixels()
        {
            Mouse m = Mouse.current;
            if (m == null || !Application.isFocused)
            {
                return Vector2.zero;
            }
            return m.delta.ReadValue();
        }

        private static Vector2? injectedLookStick;

        /// <summary>
        /// Right stick, for gamepad camera control. M6 (docs/CONTRACT_M6.md 2.1): while <see cref="InjectLookStick"/>
        /// set a value (tests: the sensitivity option scales this, and there is no real gamepad in a PlayMode test),
        /// it is returned instead of a real device's; <see cref="ClearLookStick"/> (or <see cref="ResetInjections"/>)
        /// goes back to reading one.
        /// </summary>
        public static Vector2 LookStick()
        {
            if (injectedLookStick.HasValue)
            {
                return injectedLookStick.Value;
            }
            Gamepad g = Gamepad.current;
            if (g == null)
            {
                return Vector2.zero;
            }
            Vector2 stick = g.rightStick.ReadValue();
            return stick.sqrMagnitude > 0.04f ? stick : Vector2.zero;
        }

        /// <summary>Tests: the right stick reads as <paramref name="value"/> until <see cref="ClearLookStick"/>.</summary>
        public static void InjectLookStick(Vector2 value)
        {
            injectedLookStick = value;
        }

        /// <summary>Tests: the right stick goes back to reading a real device.</summary>
        public static void ClearLookStick()
        {
            injectedLookStick = null;
        }

        /// <summary>Mouse wheel notches this frame (positive away from the user).</summary>
        public static float ZoomNotches()
        {
            Mouse m = Mouse.current;
            if (m == null)
            {
                return 0f;
            }
            float y = m.scroll.ReadValue().y;
            // Windows reports 120 per notch, other platforms 1: normalize both to notches.
            return Mathf.Abs(y) >= 20f ? y / 120f : y;
        }

        // ----- SPECTATOR (docs/next/progress/SPECTATOR.md): the free camera's own reads -----
        // The free camera also reads Move (fly), LookDeltaPixels, LookStick, TouchLookDelta, ZoomNotches (speed) and
        // ReadTouches (the pinch). Keys by physical position as everywhere: eKey is E on both layouts, qKey is Q on QWERTY
        // and A on AZERTY, so neither clashes with WASD/ZQSD.

        private static float? injectedSpectatorVertical;

        /// <summary>
        /// SPECTATOR: up (positive) or down (negative), -1 to 1: Space or E up, Ctrl or Q (A on AZERTY) down, the gamepad's
        /// right trigger up and left trigger down. An injected value (<see cref="InjectSpectatorVertical"/>) wins.
        /// </summary>
        public static float SpectatorVertical()
        {
            if (injectedSpectatorVertical.HasValue)
            {
                return Mathf.Clamp(injectedSpectatorVertical.Value, -1f, 1f);
            }
            float v = 0f;
            Keyboard k = Keyboard.current;
            if (k != null)
            {
                if (k.spaceKey.isPressed || k.eKey.isPressed) v += 1f;
                if (k.leftCtrlKey.isPressed || k.rightCtrlKey.isPressed || k.qKey.isPressed) v -= 1f;
            }
            Gamepad g = Gamepad.current;
            if (g != null)
            {
                v += g.rightTrigger.ReadValue() - g.leftTrigger.ReadValue();
            }
            return Mathf.Clamp(v, -1f, 1f);
        }

        /// <summary>Tests: <see cref="SpectatorVertical"/> returns this value until <see cref="ResetInjections"/>.</summary>
        public static void InjectSpectatorVertical(float value)
        {
            injectedSpectatorVertical = value;
        }

        /// <summary>SPECTATOR: Shift (either) or the gamepad's left stick press: the free camera flies faster.</summary>
        public static bool SpectatorFast()
        {
            Keyboard k = Keyboard.current;
            Gamepad g = Gamepad.current;
            return (k != null && (k.leftShiftKey.isPressed || k.rightShiftKey.isPressed)) || (g != null && g.leftStickButton.isPressed);
        }

        /// <summary>SPECTATOR: the right mouse button is held (mouse look with a free cursor).</summary>
        public static bool LookButtonHeld()
        {
            Mouse m = Mouse.current;
            return m != null && m.rightButton.isPressed;
        }

        // ----- M4 (docs/CONTRACT_M4.md 2 and amendment 9.7) -----
        // Careful mode is a held state, read in the fixed step. The action key (E, gamepad X = buttonWest; task DOORAUTO: it
        // only switches the floor lamp now, doors and wardrobes open by pushing toward them) and the
        // move presses that right a tipped stool are edges: a press can start and end between two fixed steps, so
        // they are latched every rendered frame (LatchPresses, called from FurnitureController.Update) and consumed
        // by the next fixed step (ActionPressed, MovePressed). A press made while an action runs is dropped, never
        // queued for after it.

        // The left stick dead zone of Move(), squared.
        private const float StickDeadZoneSq = 0.04f;

        private static bool injectedAction;
        private static bool injectedDoorPush;
        private static bool injectedCareful;
        private static bool injectedMove;
        private static bool latchedAction;
        private static bool latchedMove;
        private static bool stickWasActive;

        /// <summary>Left Shift or the gamepad left trigger held (or an injected hold): careful mode.</summary>
        public static bool CarefulHeld()
        {
            if (injectedCareful || touchCareful)
            {
                return true;
            }
            Keyboard k = Keyboard.current;
            if (k != null && k.leftShiftKey.isPressed)
            {
                return true;
            }
            Gamepad g = Gamepad.current;
            return g != null && g.leftTrigger.ReadValue() > Tuning.TriggerHeld;
        }

        /// <summary>
        /// One action press (E, gamepad X, or a tap on the player lamp) since the last call, latched or injected. Consumes it.
        /// Task DOORAUTO: the action only switches the floor lamp; doors and wardrobes take a push (FurnitureController).
        /// </summary>
        public static bool ActionPressed()
        {
            bool pressed = injectedAction || latchedAction;
            injectedAction = false;
            latchedAction = false;
            return pressed;
        }

        /// <summary>
        /// Task DOORAUTO, tests: one door push since the last call (<see cref="InjectDoorPush"/>). Consumes it.
        /// </summary>
        public static bool DoorPushPressed()
        {
            bool pressed = injectedDoorPush;
            injectedDoorPush = false;
            return pressed;
        }

        /// <summary>
        /// Task DOORAUTO, tests: one door push already held for <see cref="Tuning.PushConfirmTime"/>, read by the next fixed
        /// step that takes input, which hands it to the game (FurnitureController.DoorPushClaimed) exactly as the E press of
        /// M5 and M6 did for a door or a wardrobe: no direction is needed, the game picks the leaf or the wardrobe. It skips
        /// only the confirm hold (tested on its own with a real push through FurnitureController.ScriptedDirection); dropped
        /// like an action press during an action, on a menu and by <see cref="ResetInjections"/>.
        /// </summary>
        public static void InjectDoorPush()
        {
            injectedDoorPush = true;
        }

        /// <summary>
        /// One move press since the last call: a move key (including an arrow key) pressed, the left stick or the
        /// D-pad leaving its dead zone, or an injected press. Consumes it. Rights a tipped stool (CONTRACT_M4 2.1).
        /// </summary>
        public static bool MovePressed()
        {
            bool pressed = injectedMove || latchedMove;
            injectedMove = false;
            latchedMove = false;
            return pressed;
        }

        /// <summary>
        /// Levels v2 (C3a, the held start): this fixed step carries an input that starts a held level: a move vector past
        /// the dead zone (<see cref="Move"/>: keys, stick, D-pad, touch stick, or an injected vector), a move press, an
        /// action press (E, gamepad X, a tap on the player lamp, or injected), an injected door push (DOORAUTO), or (task STARTFIX) a start press
        /// (<see cref="StartPressPending"/>: Space, Enter, a left click off the UI buttons, gamepad A, a tap outside the touch buttons, or injected), which
        /// starts the level without moving. Peeks only: nothing is consumed, so the furniture's step that runs next still
        /// reads the press. Camera input (mouse, wheel, right stick, touch orbit), the careful key, Escape, Start and R are
        /// not start inputs.
        /// </summary>
        public static bool AnyStartInput()
        {
            return Move().sqrMagnitude > StickDeadZoneSq || injectedAction || latchedAction || injectedMove || latchedMove || injectedDoorPush
                || StartPressPending; // MUTATION:START_PRESS
        }

        // ----- Task STARTFIX: the start press, which releases a held start without moving. -----
        // A spawn can stand inside a watcher's cone at t = 0, and being seen still is allowed: the player must be able to
        // start the clock and wait. Space, Enter (main or keypad), a left click (STARTTAP), gamepad A (south) and a touch tap outside the buttons
        // are latched every rendered frame (LatchPresses) and consumed by the held FixedUpdate (ConsumeStartPress). None of
        // them is a gameplay verb (the action is E / X, a door is a push), so the press never also acts. A press on the frame a level is
        // built or a menu closes (the Enter or A that pressed Play, Resume or Next level) is dropped (BlockStartPresses).

        private static bool injectedStart;
        private static bool latchedStart;
        private static bool touchStartPending;
        private static int startBlockFrame = -1;

        /// <summary>A start press is latched or injected and not consumed yet (peek).</summary>
        public static bool StartPressPending => injectedStart || latchedStart;

        /// <summary>Tests: one start press (as Space, Enter, gamepad A or a tap), read by the next held fixed step.</summary>
        public static void InjectStartPress()
        {
            injectedStart = true;
        }

        /// <summary>The held fixed step: drops the start press it read (used or not), so a stale one never fires later.</summary>
        public static void ConsumeStartPress()
        {
            injectedStart = false;
            latchedStart = false;
        }

        /// <summary>
        /// A level was built, or a menu closed, on this frame: every start press so far is dropped, and so is a device press
        /// of this frame (the Enter or gamepad A that submitted Play, Resume or Next level must not also start the level).
        /// </summary>
        public static void BlockStartPresses()
        {
            injectedStart = false;
            latchedStart = false;
            touchStartPending = false;
            injectedClick = null;
            startBlockFrame = Time.frameCount;
        }

        /// <summary>TouchControls: a tap (a short touch that did not travel) outside every touch button.</summary>
        public static void PressTouchStart()
        {
            touchStartPending = true;
        }

        // STARTTAP: an injected left click (tests), read by the next LatchPresses exactly as a real one at that position.
        private static Vector2? injectedClick;

        /// <summary>Tests: one left click at <paramref name="screenPosition"/> (pixels), read by the next frame's latch.</summary>
        public static void InjectClick(Vector2 screenPosition)
        {
            injectedClick = screenPosition;
        }

        private static readonly List<UnityEngine.EventSystems.RaycastResult> uiHits = new List<UnityEngine.EventSystems.RaycastResult>();

        /// <summary>
        /// STARTTAP: an interactable UI button (any Selectable) is under <paramref name="screenPosition"/>. Only a Selectable
        /// counts: a raycast-target image or plate with no button (a full-screen catcher, a HUD backdrop) never swallows
        /// the start click.
        /// </summary>
        public static bool PointerOverButton(Vector2 screenPosition)
        {
            UnityEngine.EventSystems.EventSystem es = UnityEngine.EventSystems.EventSystem.current;
            if (es == null)
            {
                return false;
            }
            var data = new UnityEngine.EventSystems.PointerEventData(es) { position = screenPosition };
            uiHits.Clear();
            es.RaycastAll(data, uiHits);
            foreach (UnityEngine.EventSystems.RaycastResult hit in uiHits)
            {
                UnityEngine.UI.Selectable button = hit.gameObject != null ? hit.gameObject.GetComponentInParent<UnityEngine.UI.Selectable>() : null;
                if (button != null && button.isActiveAndEnabled && button.IsInteractable())
                {
                    return true;
                }
            }
            return false;
        }

        public static void InjectAction()
        {
            injectedAction = true;
        }

        public static void InjectCareful(bool held)
        {
            injectedCareful = held;
        }

        /// <summary>Tests and replays: one press of a move key, read by the next <see cref="MovePressed"/>.</summary>
        public static void InjectMovePress()
        {
            injectedMove = true;
        }

        /// <summary>
        /// Latches this frame's device presses for the next fixed step. With <paramref name="ignore"/> true (an
        /// action is running, or the furniture is pinned) the presses are dropped, and so is anything latched.
        /// Called once per rendered frame by the player furniture.
        /// </summary>
        public static void LatchPresses(bool ignore)
        {
            Keyboard k = Keyboard.current;
            Gamepad g = Gamepad.current;
            bool action = (k != null && k.eKey.wasPressedThisFrame) || (g != null && g.buttonWest.wasPressedThisFrame);
            bool move = k != null && (k.wKey.wasPressedThisFrame || k.sKey.wasPressedThisFrame || k.aKey.wasPressedThisFrame
                || k.dKey.wasPressedThisFrame || k.upArrowKey.wasPressedThisFrame || k.downArrowKey.wasPressedThisFrame
                || k.leftArrowKey.wasPressedThisFrame || k.rightArrowKey.wasPressedThisFrame);
            bool stick = g != null && (g.leftStick.ReadValue().sqrMagnitude > StickDeadZoneSq
                || g.dpad.ReadValue().sqrMagnitude > StickDeadZoneSq);
            move |= stick && !stickWasActive;
            stickWasActive = stick;
            // M7: a touch action (DOORAUTO: a tap on the player lamp) is the E key, and the touch stick leaving its dead zone
            // is a move press.
            action |= touchActionPending;
            touchActionPending = false;
            bool touchMove = touchStick.sqrMagnitude > StickDeadZoneSq;
            move |= touchMove && !touchStickWasActive;
            touchStickWasActive = touchMove;
            // STARTFIX: the start press, latched whatever ignore says (it only matters while held, when nothing acts), never
            // on the frame a level was built or a menu closed (BlockStartPresses).
            bool start = (k != null && (k.spaceKey.wasPressedThisFrame || k.enterKey.wasPressedThisFrame
                    || k.numpadEnterKey.wasPressedThisFrame))
                || (g != null && g.buttonSouth.wasPressedThisFrame) || touchStartPending;
            touchStartPending = false;
            // STARTTAP: a left click anywhere on the game view is a start press too, unless a UI button is under the pointer
            // (that button does its job instead). With the touch controls up, the overlay reads the fingers itself (and a
            // Windows touch also arrives as a mouse click), so the mouse is not read then.
            Vector2? click = injectedClick;
            injectedClick = null;
            Mouse m = Mouse.current;
            if (!click.HasValue && m != null && m.leftButton.wasPressedThisFrame && !TouchUIActive)
            {
                click = m.position.ReadValue();
            }
            if (click.HasValue && !PointerOverButton(click.Value)) // MUTATION:CLICK_START
            {
                start = true;
            }
            if (start && Time.frameCount > startBlockFrame)
            {
                latchedStart = true;
            }
            if (ignore)
            {
                latchedAction = false;
                latchedMove = false;
                injectedAction = false;
                injectedMove = false;
                injectedDoorPush = false;
                return;
            }
            latchedAction |= action;
            latchedMove |= move;
        }

        /// <summary>Clears every injected input and every latched press. Called in every PlayMode TearDown (M1 to M4).</summary>
        public static void ResetInjections()
        {
            injectedAction = false;
            injectedDoorPush = false;
            injectedCareful = false;
            injectedMove = false;
            injectedMoveVector = null;
            injectedPause = false;
            injectedRestart = false;
            injectedNextLevel = false;
            latchedAction = false;
            latchedMove = false;
            // STARTFIX: the start press and its block frame.
            injectedStart = false;
            latchedStart = false;
            touchStartPending = false;
            injectedClick = null;
            startBlockFrame = -1;
            injectedBack = false;
            // SPECTATOR: the free camera's vertical override.
            injectedSpectatorVertical = null;
            // M6: menu navigation injections, the right stick override and the last device (back to the keyboard,
            // hud.controls' default).
            injectedLookStick = null;
            injectedMenuUp = false;
            injectedMenuDown = false;
            injectedMenuLeft = false;
            injectedMenuRight = false;
            injectedMenuSubmit = false;
            lastWasGamepad = false;
            // M7: the touch fingers, the touch outputs and the forced overlay.
            injectedTouches.Clear();
            touchStick = Vector2.zero;
            touchLook = Vector2.zero;
            touchCareful = false;
            touchActionPending = false;
            touchPausePending = false;
            touchStickWasActive = false;
            lastWasTouch = false;
            ForceTouchUI = false;
        }

        // ----- M5 (docs/CONTRACT_M5.md 16.12, v3 15.9): the back command, which closes the level select. -----
        private static bool injectedBack;
        // The frame whose back press was already returned: a device press stays "pressed this frame" for every call of
        // its frame, so only the first call of that frame gets it (two readers never both act on one press).
        private static int backFrame = -1;

        /// <summary>Tests: one back press, read by the next <see cref="BackPressed"/> exactly as an Escape press.</summary>
        public static void InjectBack()
        {
            injectedBack = true;
        }

        /// <summary>
        /// M5: Escape on the keyboard or B (east) on the gamepad pressed this frame, or an injected press
        /// (<see cref="InjectBack"/>). Each press counts once: an injected press is consumed, and a device press is
        /// returned by the first call of its frame only. <see cref="PausePressed"/> still reads Escape too: the Menu
        /// decides which of the two Escape means (Back while the level select is open).
        /// </summary>
        public static bool BackPressed()
        {
            int frame = Time.frameCount;
            if (injectedBack)
            {
                injectedBack = false;
                backFrame = frame;
                return true;
            }
            Keyboard k = Keyboard.current;
            Gamepad g = Gamepad.current;
            bool device = (k != null && k.escapeKey.wasPressedThisFrame) || (g != null && g.buttonEast.wasPressedThisFrame);
            if (!device || backFrame == frame)
            {
                return false;
            }
            backFrame = frame;
            return true;
        }

        private static bool injectedPause;
        private static bool injectedRestart;

        /// <summary>M3: a pause press for headless tests, consumed by the next PausePressed() call.</summary>
        public static void InjectPausePress()
        {
            injectedPause = true;
        }

        /// <summary>
        /// M3 (docs/CONTRACT_M3.md 6): Escape on the keyboard or Start on the gamepad pauses and unpauses. An
        /// injected press (<see cref="InjectPausePress"/>) counts once.
        /// </summary>
        public static bool PausePressed()
        {
            bool pressed = injectedPause || touchPausePending;
            injectedPause = false;
            touchPausePending = false;
            Keyboard k = Keyboard.current;
            Gamepad g = Gamepad.current;
            return pressed
                || (k != null && k.escapeKey.wasPressedThisFrame)
                || (g != null && g.startButton.wasPressedThisFrame);
        }

        /// <summary>
        /// R on the keyboard, Y (north) on the gamepad. M3: Start no longer restarts, it pauses. An injected press
        /// (<see cref="InjectRestartPress"/>) counts once.
        /// </summary>
        public static bool RestartPressed()
        {
            bool injected = injectedRestart;
            injectedRestart = false;
            Keyboard k = Keyboard.current;
            Gamepad g = Gamepad.current;
            return injected
                || (k != null && k.rKey.wasPressedThisFrame)
                || (g != null && g.buttonNorth.wasPressedThisFrame);
        }

        /// <summary>M3 tests: one press of the restart command, read by the next <see cref="RestartPressed"/>.</summary>
        public static void InjectRestartPress()
        {
            injectedRestart = true;
        }

        /// <summary>
        /// M3: drops the injected restart and next level presses. A key pressed while the game is paused is lost,
        /// so an injected one must not wait for the resume either.
        /// </summary>
        public static void DiscardGameplayPresses()
        {
            injectedRestart = false;
            injectedNextLevel = false;
            // M4: an action or move press made on a menu or while paused is lost too.
            latchedAction = false;
            latchedMove = false;
            injectedAction = false;
            injectedMove = false;
            injectedDoorPush = false;
            touchActionPending = false;
            // STARTFIX: a start press made on a menu, while paused or on the frame a menu closed is lost too, and so is a
            // device press of this frame read later in the frame (FurnitureController.Update may run after GameState.Update).
            BlockStartPresses();
        }

        /// <summary>M2: Enter (main or keypad) or the gamepad south button loads the next level after a win.</summary>
        public static bool NextLevelPressed()
        {
            Keyboard k = Keyboard.current;
            Gamepad g = Gamepad.current;
            bool injected = injectedNextLevel;
            injectedNextLevel = false;
            return injected
                || (k != null && (k.enterKey.wasPressedThisFrame || k.numpadEnterKey.wasPressedThisFrame))
                || (g != null && g.buttonSouth.wasPressedThisFrame);
        }

        private static bool injectedNextLevel;

        /// <summary>
        /// Probe and tests: one press of the next level command, read by the next <see cref="NextLevelPressed"/>
        /// exactly as an Enter key press (the PlayMode tests cannot drive a keyboard device headless).
        /// </summary>
        public static void InjectNextLevelPress()
        {
            injectedNextLevel = true;
        }

        public static bool ReleaseCursorPressed()
        {
            Keyboard k = Keyboard.current;
            return k != null && k.escapeKey.wasPressedThisFrame;
        }

        public static bool CaptureCursorPressed()
        {
            Mouse m = Mouse.current;
            return m != null && m.leftButton.wasPressedThisFrame;
        }

        // ----- M6 (docs/CONTRACT_M6.md 2.2): menu navigation and the last device used. -----
        // Every real menu (Title, Pause, Options, LevelSelect) is already driven by the InputSystemUIInputModule, which
        // reads a real device's D-pad, stick, Enter and gamepad south/east directly: a human with a gamepad already
        // navigates every menu with it. These hooks exist so a PlayMode test can do the same with no real gamepad
        // device attached (the project's style: every input is read through InputReader, never a device directly, so
        // it can be injected); Menu.Update reads them and moves the EventSystem selection along the same explicit
        // Navigation links a real D-pad press would follow.

        private static bool injectedMenuUp;
        private static bool injectedMenuDown;
        private static bool injectedMenuLeft;
        private static bool injectedMenuRight;
        private static bool injectedMenuSubmit;

        public static void InjectMenuUp() => injectedMenuUp = true;
        public static void InjectMenuDown() => injectedMenuDown = true;
        public static void InjectMenuLeft() => injectedMenuLeft = true;
        public static void InjectMenuRight() => injectedMenuRight = true;

        /// <summary>Tests: one A (south) press on the selected menu widget, read by the next <see cref="MenuSubmitPressed"/>.</summary>
        public static void InjectMenuSubmit() => injectedMenuSubmit = true;

        /// <summary>
        /// One D-pad/left stick press moving the menu selection since the last call (at most one direction per call),
        /// consumed by it. Injected only: no real device is read here (see the section note above).
        /// </summary>
        public static MenuDirection MenuMovePressed()
        {
            if (injectedMenuUp) { injectedMenuUp = false; return MenuDirection.Up; }
            if (injectedMenuDown) { injectedMenuDown = false; return MenuDirection.Down; }
            if (injectedMenuLeft) { injectedMenuLeft = false; return MenuDirection.Left; }
            if (injectedMenuRight) { injectedMenuRight = false; return MenuDirection.Right; }
            return MenuDirection.None;
        }

        /// <summary>One A (south) press on the selected menu widget since the last call. Consumes it. Injected only.</summary>
        public static bool MenuSubmitPressed()
        {
            bool pressed = injectedMenuSubmit;
            injectedMenuSubmit = false;
            return pressed;
        }

        private static bool lastWasGamepad;

        /// <summary>
        /// True when the last input activity (a key, the mouse, or a gamepad control) came from a gamepad: hud.controls
        /// shows the gamepad names while this holds, the keyboard names otherwise. Updated by <see cref="PollLastDevice"/>.
        /// </summary>
        public static bool LastInputWasGamepad => lastWasGamepad;

        /// <summary>
        /// Updates which device produced the last input: a key held, mouse motion, a click or the wheel sets the
        /// keyboard/mouse; a stick past its dead zone, a trigger past Tuning.TriggerHeld, the D-pad or a face/start
        /// button sets the gamepad. Neither active keeps the last device. Called once a rendered frame (Hud.Update),
        /// so no gameplay code needs to read a device directly.
        /// </summary>
        public static void PollLastDevice()
        {
            Keyboard k = Keyboard.current;
            Mouse m = Mouse.current;
            bool keyboardMouse = (k != null && k.anyKey.isPressed)
                || (m != null && (m.delta.ReadValue().sqrMagnitude > 0.01f || m.leftButton.isPressed || m.rightButton.isPressed
                    || Mathf.Abs(m.scroll.ReadValue().y) > 0.01f));
            Gamepad g = Gamepad.current;
            bool gamepad = g != null && (g.leftStick.ReadValue().sqrMagnitude > StickDeadZoneSq
                || g.rightStick.ReadValue().sqrMagnitude > StickDeadZoneSq || g.leftTrigger.ReadValue() > Tuning.TriggerHeld
                || g.rightTrigger.ReadValue() > Tuning.TriggerHeld || g.dpad.ReadValue().sqrMagnitude > 0.01f
                || g.buttonSouth.isPressed || g.buttonNorth.isPressed || g.buttonEast.isPressed || g.buttonWest.isPressed
                || g.startButton.isPressed);
            if (keyboardMouse)
            {
                lastWasGamepad = false;
            }
            else if (gamepad)
            {
                lastWasGamepad = true;
            }
            // M7 (CONTRACT_M7 1.5): a finger on the touchscreen makes touch the active input (checked first: Windows also
            // turns a touch into mouse input); a key, the mouse or the gamepad with no finger down ends it.
            Touchscreen ts = Touchscreen.current;
            if (ts != null && ts.primaryTouch.isInProgress)
            {
                lastWasTouch = true;
            }
            else if (keyboardMouse || gamepad)
            {
                lastWasTouch = false;
            }
        }

        /// <summary>Tests: forces the last device read by <see cref="LastInputWasGamepad"/>, with no real device.</summary>
        public static void InjectLastDevice(bool gamepad)
        {
            lastWasGamepad = gamepad;
        }

        // ----- M7 (docs/CONTRACT_M7.md 1.5): touch. -----
        // TouchControls (its own overlay) reads the fingers through ReadTouches (the real Touchscreen plus the fingers a
        // test injects), turns them into a floating stick, an orbit drag, two buttons (careful, pause) and a tap on the
        // player lamp (DOORAUTO: it replaced the action button), and writes those back here.
        // The game reads them through the same calls as the keyboard and the gamepad (Move, CarefulHeld, the latched
        // action, PausePressed); the camera reads TouchLookDelta. Nothing here changes the keyboard, mouse or gamepad.

        /// <summary>A finger on the screen: its id and its position in screen pixels (origin bottom left).</summary>
        public struct TouchPoint
        {
            public int Id;
            public Vector2 Position;
        }

        private static readonly Dictionary<int, Vector2> injectedTouches = new Dictionary<int, Vector2>();
        private static Vector2 touchStick;
        private static Vector2 touchLook;
        private static bool touchCareful;
        private static bool touchActionPending;
        private static bool touchPausePending;
        private static bool touchStickWasActive;
        private static bool lastWasTouch;
        private static int touchArgument = -1;

        /// <summary>Tests: shows the touch controls with no touchscreen, as the -touch argument does in a player.</summary>
        public static bool ForceTouchUI;

        /// <summary>
        /// The touch controls show: forced (<see cref="ForceTouchUI"/>), the -touch argument, or a finger was the last
        /// input on a touchscreen (<see cref="PollLastDevice"/>).
        /// </summary>
        public static bool TouchUIActive => ForceTouchUI || lastWasTouch || HasTouchArgument; // MUTATION:TOUCH_UI_GATE

        private static bool HasTouchArgument
        {
            get
            {
                if (touchArgument < 0)
                {
                    touchArgument = Array.IndexOf(Environment.GetCommandLineArgs(), "-touch") >= 0 ? 1 : 0;
                }
                return touchArgument == 1;
            }
        }

        /// <summary>Tests: finger <paramref name="finger"/> lands on, or moves to, <paramref name="screenPosition"/> (pixels).</summary>
        public static void InjectTouch(int finger, Vector2 screenPosition)
        {
            injectedTouches[finger] = screenPosition;
        }

        /// <summary>Tests: finger <paramref name="finger"/> lifts.</summary>
        public static void ReleaseTouch(int finger)
        {
            injectedTouches.Remove(finger);
        }

        /// <summary>
        /// The fingers down this frame: the real touchscreen's (a tap that began and ended within the frame included)
        /// and the injected ones, whose ids are negative (-1 - finger) so they never meet a real touch id.
        /// </summary>
        public static void ReadTouches(List<TouchPoint> into)
        {
            into.Clear();
            Touchscreen ts = Touchscreen.current;
            if (ts != null)
            {
                foreach (TouchControl t in ts.touches)
                {
                    if (t.isInProgress || t.press.wasPressedThisFrame)
                    {
                        into.Add(new TouchPoint { Id = t.touchId.ReadValue(), Position = t.position.ReadValue() });
                    }
                }
            }
            foreach (KeyValuePair<int, Vector2> f in injectedTouches)
            {
                into.Add(new TouchPoint { Id = -1 - f.Key, Position = f.Value });
            }
        }

        /// <summary>TouchControls: the floating stick, x right and y forward, magnitude at most 1.</summary>
        public static void SetTouchStick(Vector2 value)
        {
            touchStick = Vector2.ClampMagnitude(value, 1f);
        }

        /// <summary>TouchControls: this frame's orbit drag, in pixels of a 1080 pixel high screen.</summary>
        public static void SetTouchLook(Vector2 delta)
        {
            touchLook = delta;
        }

        /// <summary>TouchControls: the careful toggle.</summary>
        public static void SetTouchCareful(bool on)
        {
            touchCareful = on;
        }

        /// <summary>TouchControls: one tap on the player lamp (DOORAUTO), latched as an E press by the next <see cref="LatchPresses"/>.</summary>
        public static void PressTouchAction()
        {
            touchActionPending = true;
        }

        /// <summary>TouchControls: one tap of the pause button, read by the next <see cref="PausePressed"/>.</summary>
        public static void PressTouchPause()
        {
            touchPausePending = true;
        }

        public static Vector2 TouchStick => touchStick;

        public static bool TouchCareful => touchCareful;

        /// <summary>The orbit drag of this frame, in pixels of a 1080 pixel high screen (zero with no touch).</summary>
        public static Vector2 TouchLookDelta()
        {
            return touchLook;
        }

        private static float touchPinch;

        /// <summary>PINCH: TouchControls: this frame's change in the pinching fingers' distance, pixels of a 1080 pixel high screen.</summary>
        public static void SetTouchPinch(float delta)
        {
            touchPinch = delta;
        }

        /// <summary>PINCH: this frame's pinch, pixels of a 1080 pixel high screen (spread apart: positive, zoom in; zero with no pinch).</summary>
        public static float TouchPinchDelta()
        {
            return touchPinch;
        }
    }

    /// <summary>M6 (docs/CONTRACT_M6.md 2.2): a menu navigation direction injected by a test (see <see cref="InputReader.MenuMovePressed"/>).</summary>
    public enum MenuDirection
    {
        None,
        Up,
        Down,
        Left,
        Right,
    }
}
