import io

p = "Assets/Scripts/Runtime/FurnitureController.cs"
s = io.open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:90])
    s = s.replace(a, b)


# --- docs ---
rep("""        /// <summary>Increments each time the hop lands (drives the hop tick sound). The office chair rolls: no hops.</summary>""",
    """        /// <summary>
        /// Increments each time the hop lands (drives the hop tick sound). The office chair rolls instead under
        /// GameRules.Bodies (no hops); without it, it hops like the chair.
        /// </summary>""")
rep("""        /// True on every step of an action (fall, righting, switch), from the step it starts for its whole duration
        /// (0.2 s = 10 steps). It turns false at the start of the step after the last one.""",
    """        /// True on every step of an action (fall, righting, switch), from the step it starts for its whole duration
        /// (round(duration / dt) steps: a 0.3 s switch is 15). It turns false at the start of the step after the last one.""")
rep("""        /// <summary>The stool's tell: it goes faster than StoolTipSpeed (it leans back and rattles).</summary>
        public bool TellActive { get; private set; }""",
    """        /// <summary>
        /// The stool's tell (CONTRACT_M4 10.3): it goes faster than StoolTellSpeed, the start of the warning band below
        /// the StoolTipSpeed threshold. It leans back and rattles, more and more up to the threshold.
        /// </summary>
        public bool TellActive { get; private set; }

        /// <summary>How strong the tell is: 0 at StoolTellSpeed and below, 1 at StoolTipSpeed and above.</summary>
        public float TellStrength { get; private set; }""")
rep("""        /// <summary>Increments every RollNoiseInterval of rolling (office chair), whatever the floor: GameState decides silence.</summary>""",
    """        /// <summary>
        /// Increments every RollNoiseInterval of rolling (office chair, under GameRules.Bodies), whatever the floor:
        /// GameState decides silence.
        /// </summary>""")

# --- 10.4: the toggle uses the lit range ---
rep("""        /// <summary>
        /// What every inhabitant's ViewRange is multiplied by for this furniture's sample points: LampOffLight for
        /// a lamp body whose light is off under GameRules.Lamp, 1 otherwise (Vision.Step).
        /// </summary>
        public float SightRangeFactor => Body.HasLight && Lamp != null && Rules != null && Rules.Lamp ? Lamp.RangeFactor : 1f;""",
    """        /// <summary>
        /// What every inhabitant's ViewRange is multiplied by for this furniture's sample points: LampOffLight for
        /// a lamp body whose light is off under GameRules.Lamp, 1 otherwise (Vision.Step). CONTRACT_M4 10.4: during
        /// the switch itself the rules use the lit range, whichever way it goes (the light changes visually at the
        /// start), so a switch seen for its whole duration is caught.
        /// </summary>
        public float SightRangeFactor
        {
            get
            {
                if (!Body.HasLight || Lamp == null || Rules == null || !Rules.Lamp)
                {
                    return 1f;
                }
                if (Action == BodyAction.Toggle) return 1f; // MUTATION:TOGGLE_LIT
                return Lamp.RangeFactor;
            }
        }

        /// <summary>
        /// The box the vision samples come from: the body size, or, while the stool lies on its side (CONTRACT_M4
        /// 10.3), the lying box: as long as the stool is tall, as high as it is wide. Its fall and its righting keep
        /// the upright box, the taller one, so a stool going down or up in sight is never hidden by its own motion.
        /// </summary>
        public Vector3 SampleSize => LyingDown ? new Vector3(Size.y, Size.x, Size.z) : Size;""")

# --- 10.7 constants ---
rep("""        // Below this remaining glide time the glide is over (ten 0.02 s steps sum to 0.19999999 in float).
        private const float GlideEpsilon = 1e-4f;
        // A wall stops the furniture when it travels less than half (squared: a quarter) of the intended distance.
        private const float BlockedFraction = 0.25f;
        // Presentation only""", """        // Tuning.GlideEpsilon: below this remaining glide time the glide is over (float sums of 0.02 s steps).
        // Tuning.BlockedFraction: a wall stops the furniture when it travels less than half (squared: a quarter) of
        // the intended distance.
        // Presentation only""")
s = s.replace("<= GlideEpsilon", "<= Tuning.GlideEpsilon")
s = s.replace("(rollTime + GlideEpsilon)", "(rollTime + Tuning.GlideEpsilon)")
s = s.replace("(before + GlideEpsilon)", "(before + Tuning.GlideEpsilon)")
rep("(Velocity * dt).sqrMagnitude * BlockedFraction)", "(Velocity * dt).sqrMagnitude * Tuning.BlockedFraction)")
assert "GlideEpsilon" not in s.replace("Tuning.GlideEpsilon", "")
assert "BlockedFraction" not in s.replace("Tuning.BlockedFraction", "")

# --- 10.3 head-on and the warning band ---
rep("""            // CONTRACT_M4 2.1: a head-on wall hit faster than the threshold tips the stool on the next step.
            if (bodies && Body.Tips && !Tipped && !ActionActive && wallHitInto > Tuning.StoolTipSpeed)
            {
                pendingTip = true;
            }
            TellActive = bodies && Body.Tips && !Tipped && !Pinned && Velocity.magnitude > Tuning.StoolTipSpeed;

            // Hops (and their sound) only while the body really travels or turns: an action is not a hop. The office
            // chair rolls: a roll tick every RollNoiseInterval of rolling instead of hops.
            hopping = !Body.Glides && MotionRule.IsMoving(PlanarSpeed, YawRate);""",
    """            // CONTRACT_M4 2.1 and 10.3: a head-on wall hit (within StoolHeadOnDegrees of the wall normal) faster than
            // the threshold against the wall tips the stool on the next step. A graze along a wall never does.
            if (bodies && Body.Tips && !Tipped && !ActionActive && wallHitInto > Tuning.StoolTipSpeed)
            {
                pendingTip = true;
            }
            // CONTRACT_M4 10.3: the warning band. The tell starts at StoolTellSpeed and is full at StoolTipSpeed.
            bool tellable = bodies && Body.Tips && !Tipped && !Pinned;
            float speedNow = Velocity.magnitude;
            TellActive = tellable && speedNow > Tuning.StoolTellSpeed; // MUTATION:TELL_SPEED
            TellStrength = TellActive ? Mathf.Clamp01((speedNow - Tuning.StoolTellSpeed) / (Tuning.StoolTipSpeed - Tuning.StoolTellSpeed)) : 0f;

            // Hops (and their sound) only while the body really travels or turns: an action is not a hop. Under
            // GameRules.Bodies the office chair rolls: a roll tick every RollNoiseInterval of rolling instead of hops.
            bool rolls = bodies && Body.Glides;
            hopping = !rolls && MotionRule.IsMoving(PlanarSpeed, YawRate);""")
rep("""            if (Body.Glides && PlanarSpeed > Tuning.MovingSpeedThreshold)
            {
                float before = rollTime;""", """            if (rolls && PlanarSpeed > Tuning.MovingSpeedThreshold)
            {
                float before = rollTime;""")
rep("""        /// <summary>Drops the glide, a pending tip, the tell and the predicted stop.</summary>
        private void ClearMotionState()
        {
            Gliding = false;
            pendingTip = false;
            TellActive = false;""", """        /// <summary>Drops the glide, a pending tip, the tell and the predicted stop.</summary>
        private void ClearMotionState()
        {
            Gliding = false;
            pendingTip = false;
            TellActive = false;
            TellStrength = 0f;""")
rep("""        /// <summary>The stool's head-on hit: the velocity against the hit normal, kept at its largest over the move.</summary>
        private void OnControllerColliderHit(ControllerColliderHit hit)
        {
            Vector3 n = YawMath.Planar(hit.normal);
            if (n.sqrMagnitude < 0.25f)
            {
                return;
            }
            float into = -Vector3.Dot(YawMath.Planar(moveVelocity), n.normalized);
            if (into > wallHitInto)
            {
                wallHitInto = into;
            }
        }""", """        /// <summary>
        /// The stool's head-on hit: the velocity against the hit normal, kept at its largest over the move, for hits
        /// within StoolHeadOnDegrees of head-on only (CONTRACT_M4 10.3). The hit normal points out of the wall, toward
        /// the stool: the wall's inward normal.
        /// </summary>
        private void OnControllerColliderHit(ControllerColliderHit hit)
        {
            Vector3 n = YawMath.Planar(hit.normal);
            Vector3 v = YawMath.Planar(moveVelocity);
            float speed = v.magnitude;
            if (n.sqrMagnitude < 0.25f || speed < 1e-4f)
            {
                return;
            }
            float into = -Vector3.Dot(v, n.normalized);
            bool headOn = into >= speed * Mathf.Cos(Tuning.StoolHeadOnDegrees * Mathf.Deg2Rad);
            if (headOn && into > wallHitInto)
            {
                wallHitInto = into;
            }
        }""")

# --- 10.3 lying samples ---
rep("""        /// <summary>Fills a length 5 array with the sample points of PRD 4.1, at the fixed step pose.</summary>
        public void GetSamplePoints(Vector3[] output)
        {
            VisionMath.SamplePoints(transform.position, Yaw, Size, Tuning.SampleInset, output);
        }""", """        /// <summary>
        /// Fills a length 5 array with the sample points of PRD 4.1, at the fixed step pose, from <see cref="SampleSize"/>
        /// (the lying box while the stool lies on its side).
        /// </summary>
        public void GetSamplePoints(Vector3[] output)
        {
            VisionMath.SamplePoints(transform.position, Yaw, SampleSize, Tuning.SampleInset, output);
        }""")

# --- visual: the lean follows the strength ---
rep("""            // M4 stool tell: it leans back and rattles while it goes too fast (visual only).
            leanBlend = Mathf.MoveTowards(leanBlend, TellActive ? 1f : 0f, LeanResponse * Time.deltaTime);""",
    """            // M4.1 stool tell: from StoolTellSpeed it leans back and rattles, fully at StoolTipSpeed (visual only).
            leanBlend = Mathf.MoveTowards(leanBlend, TellStrength, LeanResponse * Time.deltaTime);""")
rep("""        // How fast the tell lean follows the rule (per second, visual smoothing only).
        private const float LeanResponse = 14f;""", """        // How fast the tell lean follows TellStrength (per second, visual smoothing only; the strength itself rises
        // from 0 to 1 over the 0.25 s of the warning band).
        private const float LeanResponse = 14f;""")

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
