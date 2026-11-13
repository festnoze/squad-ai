import io

p = "Assets/Scripts/Runtime/GameState.cs"
s = io.open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:80])
    s = s.replace(a, b, 1)


# --- the silent floor flag, for every furniture noise ---
rep("""        private bool rollSilent;
""", """        // M4.1 (CONTRACT_M4 10.6): the furniture stands on a rug or in a soft room this step: none of its noises is heard.
        private bool floorSilent;
""")
rep("""            // 7. Noise: hop events on a hard floor, M4's topple, click and roll, then the creak gauge.
            int hops = furniture.HopCount;
            hoppedThisStep = hops != lastHopCount;
            lastHopCount = hops;
            hopSilent = hoppedThisStep && Level.IsSilentAt(furniture.transform.position);""", """            // 7. Noise: hop events, M4's topple, click and roll (all silent on a rug or in a soft room), then the creak gauge.
            floorSilent = Level.IsSilentAt(furniture.transform.position);
            int hops = furniture.HopCount;
            hoppedThisStep = hops != lastHopCount;
            lastHopCount = hops;
            hopSilent = hoppedThisStep && floorSilent;""")
rep("""            lastRollCount = rolls;
            rollSilent = rolledThisStep && Level.IsSilentAt(furniture.transform.position);
""", """            lastRollCount = rolls;
""")
rep("""            // M4 (CONTRACT_M4 2.1 to 2.4): the topple and the click are heard on any floor (a topple alerts like a
            // hop, in Routine only); the roll is silent on a rug or in a soft room.
            if (rules.Hearing && !furniture.Carried)
            {""", """            // M4 (CONTRACT_M4 2.1 to 2.4): the topple (it alerts like a hop, in Routine only), the click and the roll.
            // M4.1 (10.6): like the hop, each of them is silent on a rug or in a soft room.
            if (rules.Hearing && !furniture.Carried && !floorSilent)
            {""")
rep("""                if (rolledThisStep && !rollSilent)
                {""", """                if (rolledThisStep)
                {""")
rep("""            if (toppledThisStep)
            {
                Sfx.PlayTopple(pan);
            }""", """            if (toppledThisStep)
            {
                Sfx.PlayTopple(pan, floorSilent);
            }""")
rep("""                Sfx.PlayRoll(rollSilent);""", """                Sfx.PlayRoll(floorSilent);""")
rep("""            bool rattle = State == PlayState.Playing && furniture.TellActive;
            float span = furniture.Body != null ? furniture.Body.MaxSpeed - Tuning.StoolTipSpeed : 0f;
            Sfx.SetRattle(rattle, span > 1e-3f ? (furniture.PlanarSpeed - Tuning.StoolTipSpeed) / span : 0f);""", """            // M4.1 (CONTRACT_M4 10.3): the tell grows from the tell speed (1.0 m/s) to full at the tip speed (1.3 m/s).
            bool rattle = State == PlayState.Playing && furniture.TellActive;
            const float band = Tuning.StoolTipSpeed - Tuning.StoolTellSpeed;
            Sfx.SetRattle(rattle, Mathf.Clamp01((furniture.PlanarSpeed - Tuning.StoolTellSpeed) / band));""")

# --- the HUD tipped line ---
rep("""                // M4: the hints of the current body only, and the sat-on line while pinned.
                Hud.SetBodyHints(rules.Bodies, rules.Lamp && furniture.Body != null && furniture.Body.HasLight);
                Hud.SetSatOn(State == PlayState.Playing && furniture.Pinned);""", """                // M4: the hints of the current body only, and the sat-on line while pinned. M4.1 (10.3): the tipped line
                // while the stool lies on its side.
                Hud.SetBodyHints(rules.Bodies, rules.Lamp && furniture.Body != null && furniture.Body.HasLight);
                Hud.SetSatOn(State == PlayState.Playing && furniture.Pinned);
                Hud.SetTipped(State == PlayState.Playing && furniture.LyingDown && !furniture.Carried);""")

# --- the ghost hidden while the stool lies ---
rep("""        /// <summary>
        /// While the chair is on the floor and out of place: the rings around the decoys of its kind (the safe
        /// spots), and the ghost at the last seer's remembered pose unless a decoy already explains the chair.
        /// </summary>""", """        /// <summary>
        /// While the chair is on the floor and out of place: the rings around the decoys of its kind (the safe
        /// spots), and the ghost at the last seer's remembered pose unless a decoy already explains the chair.
        /// M4.1 (CONTRACT_M4 10.3): a stool on its side is out of place wherever it lies, but its ghost and rings are
        /// hidden: the HUD's tipped line says what to do (get up) instead of pointing at a place.
        /// </summary>""")
rep("""            Ghost?.ShowRings(OutOfPlace);
            if (OutOfPlace && !AtDecoy)
            {""", """            bool lying = furniture.Tipped;
            Ghost?.ShowRings(OutOfPlace && !lying);
            if (OutOfPlace && !AtDecoy && !lying)
            {""")

# --- the furniture visual settles onto the seat ---
rep("""        private void SitOnPlayer(InhabitantRoutine routine)
        {
            FurnitureController furniture = Level.Furniture;
            var seat = new FurniturePose(YawMath.Planar(routine.SeatHome.Position), routine.SeatHome.Yaw);
            furniture.Teleport(seat.Position, seat.Yaw);""", """        private void SitOnPlayer(InhabitantRoutine routine)
        {
            FurnitureController furniture = Level.Furniture;
            var seat = new FurniturePose(YawMath.Planar(routine.SeatHome.Position), routine.SeatHome.Yaw);
            Vector3 from = furniture.transform.position;
            float fromYaw = furniture.Yaw;
            furniture.Teleport(seat.Position, seat.Yaw);
            // M4.1 (CONTRACT_M4 10.7): the rule pose snaps, the visual slides there over SeatSettleTime.
            SeatSettleView settle = furniture.GetComponent<SeatSettleView>();
            if (settle == null)
            {
                settle = furniture.gameObject.AddComponent<SeatSettleView>();
            }
            settle.Begin(furniture, from, fromYaw, SeatSettleTime);""")
rep("""        /// <summary>The seat home a "sit": "player" inhabitant is walking to (its ghost shows), or null.</summary>""", """        /// <summary>M4.1: the furniture's visual is still sliding onto the seat home after a sit on the player.</summary>
        public bool SeatSettling
        {
            get
            {
                SeatSettleView settle = Level != null && Level.Furniture != null ? Level.Furniture.GetComponent<SeatSettleView>() : null;
                return settle != null && settle.Active;
            }
        }

        /// <summary>
        /// M4.1 (CONTRACT_M4 10.7): how long the furniture's visual takes to slide onto the seat home (presentation;
        /// wanted in Tuning as SeatSettleTime).
        /// </summary>
        public const float SeatSettleTime = 0.3f;

        /// <summary>The seat home a "sit": "player" inhabitant is walking to (its ghost shows), or null.</summary>""")

# --- the SeatSettleView class at the end of the file ---
s = s.rstrip()
assert s.endswith("}")
s = s[:-1].rstrip() + """

    /// <summary>
    /// M4.1 (docs/CONTRACT_M4.md 10.7): when an inhabitant sits on the player furniture, its rule pose snaps to the seat
    /// home (GameState teleports it), and this slides its visual there from where it stood over the given time, eased.
    /// It runs after the LateUpdate of FurnitureController (which places the visual at the rule pose), keeps whatever
    /// offset the controller added (hop, tremble) and only replaces the base pose. It stops by itself when the furniture
    /// is moved again. Added on demand to the furniture's own GameObject: no Transform is created (probe step 09).
    /// </summary>
    [DefaultExecutionOrder(50)]
    public sealed class SeatSettleView : MonoBehaviour
    {
        private FurnitureController furniture;
        private Vector3 from;
        private float fromYaw;
        private Vector3 to;
        private float toYaw;
        private float elapsed;
        private float duration;

        /// <summary>True while the visual is still on its way to the seat home.</summary>
        public bool Active => furniture != null && elapsed < duration;

        /// <summary>The base pose the visual was given on the last frame (tests).</summary>
        public Vector3 VisualBase { get; private set; }

        public void Begin(FurnitureController target, Vector3 fromPosition, float fromYawDegrees, float seconds)
        {
            furniture = target;
            from = fromPosition;
            fromYaw = fromYawDegrees;
            to = target.transform.position;
            toYaw = target.Yaw;
            elapsed = 0f;
            duration = Mathf.Max(1e-3f, seconds);
            VisualBase = from;
            if (YawMath.Planar(to - from).sqrMagnitude < 1e-8f && Mathf.Abs(Mathf.DeltaAngle(fromYaw, toYaw)) < 1e-3f)
            {
                // Already home: nothing to slide.
                elapsed = duration;
                VisualBase = to;
            }
        }

        private void LateUpdate()
        {
            if (!Active || furniture.Visual == null)
            {
                return;
            }
            if ((furniture.transform.position - to).sqrMagnitude > 1e-8f)
            {
                // Moved since (released and driven, carried): the controller owns the visual again.
                elapsed = duration;
                return;
            }
            if (!GamePause.IsPaused)
            {
                elapsed += Time.deltaTime;
            }
            float t = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(elapsed / duration));
            Transform visual = furniture.Visual;
            Vector3 offset = visual.position - to;
            Vector3 basePosition = Vector3.Lerp(from, to, t);
            float yaw = Mathf.LerpAngle(fromYaw, toYaw, t);
            VisualBase = basePosition;
            visual.SetPositionAndRotation(basePosition + offset, Quaternion.Euler(0f, yaw - toYaw, 0f) * visual.rotation);
        }
    }
}
"""
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("ok")
