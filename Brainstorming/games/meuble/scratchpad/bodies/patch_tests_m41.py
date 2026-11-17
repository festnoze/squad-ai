import io

p = "Assets/Tests/PlayMode/ProbeTestsM4Bodies.cs"
s = io.open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:90])
    s = s.replace(a, b)


rep("""    /// lamp's range.""", """    /// lamp's range. M4.1 (CONTRACT_M4 10.3, 10.4, 10.7): the stool's warning band and head-on rule, its lying
    /// samples, the lit range during a lamp switch, and the roll gated by GameRules.Bodies.""")

# Trace: the range factor.
rep("""            public bool Seen;
            public bool Caught;
        }""", """            public bool Seen;
            public bool Caught;
            public float Factor;
        }""")
rep("""                Caught = Game.State == PlayState.Caught,
            });""", """                Caught = Game.State == PlayState.Caught,
                Factor = c.SightRangeFactor,
            });""")

# Step 29: rolls, no hops (GameRules.Bodies on).
rep("""        public IEnumerator Step29_OfficeChairGlidesToAStopInExactlyFourTenths()
        {
            PinAway();
            yield return DriveOfficeChairToSpeed();""", """        public IEnumerator Step29_OfficeChairGlidesToAStopInExactlyFourTenths()
        {
            PinAway();
            int hops = Chair.HopCount;
            int rolls = Chair.RollCount;
            int driveStart = trace.Count;
            yield return DriveOfficeChairToSpeed();""")
rep("""            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.Less(Chair.transform.position.x, 2.5f, "premise: the glide ended before the far wall");
            AssertClean();
        }""", """            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.Less(Chair.transform.position.x, 2.5f, "premise: the glide ended before the far wall");
            // It rolls (a tick every RollNoiseInterval of rolling), it never hops.
            int rolling = 0;
            for (int i = driveStart; i < trace.Count; i++)
            {
                rolling += trace[i].Speed > Tuning.MovingSpeedThreshold ? 1 : 0;
            }
            Assert.Greater(rolling, 30, "premise: the office chair rolled for more than 0.6 s");
            Assert.AreEqual(Mathf.FloorToInt(rolling * Dt / Tuning.RollNoiseInterval + 1e-3f), Chair.RollCount - rolls, "roll ticks");
            Assert.AreEqual(hops, Chair.HopCount, "the office chair hopped under GameRules.Bodies");
            AssertClean();
        }""")

# Step 29f: the stage speed from the body; the office chair hops without GameRules.Bodies.
rep("""                // Max speed: the plateau.
                yield return Steps(60);
                Assert.AreEqual(def.MaxSpeed, Chair.PlanarSpeed, 0.02f, kind + ": max speed");""", """                // Max speed: the plateau. Without GameRules.Bodies every body hops, the office chair too, and none rolls.
                int hops = Chair.HopCount;
                int rolls = Chair.RollCount;
                yield return Steps(60);
                Assert.AreEqual(def.MaxSpeed, Chair.PlanarSpeed, 0.02f, kind + ": max speed");
                Assert.Greater(Chair.HopCount, hops, kind + ": no hops without GameRules.Bodies");
                Assert.AreEqual(rolls, Chair.RollCount, kind + ": rolls without GameRules.Bodies");""")
rep("""            // The stool's two stages: fast up to StageSpeed, then StoolHighAccel.
            Place("stool", LaneStart, 90f);
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Chair.PlanarSpeed > Tuning.StoolTipSpeed + 0.01f, 30);
            float v0 = Chair.PlanarSpeed;
            Assert.Less(v0, Tuning.StoolTipSpeed + 0.05f, "the stool shot past the stage speed");""", """            // The stool's two stages: fast up to StageSpeed, then StoolHighAccel.
            Place("stool", LaneStart, 90f);
            float stage = Chair.Body.StageSpeed;
            Chair.ScriptedDirection = Vector3.right;
            yield return Until(() => Chair.PlanarSpeed > stage + 0.01f, 30);
            float v0 = Chair.PlanarSpeed;
            Assert.Less(v0, stage + 0.05f, "the stool shot past the stage speed");""")

# Step 29h: the switch uses the lit range, for its 15 steps.
rep("""            Assert.IsFalse(lamp.On, "the lamp is still on");
            Assert.IsFalse(lamp.Light.enabled, "the light still shines");
            Assert.AreEqual(Tuning.LampOffLight, Chair.SightRangeFactor, 1e-6f, "the dark range factor");
            Assert.Less(RenderSettings.ambientSkyColor.grayscale, ambientOn.grayscale, "the room did not dim");""", """            Assert.IsFalse(lamp.On, "the lamp is still on");
            Assert.IsFalse(lamp.Light.enabled, "the light still shines");
            Assert.Less(RenderSettings.ambientSkyColor.grayscale, ambientOn.grayscale, "the room did not dim");
            // CONTRACT_M4 10.4: the rules keep the lit range until the switch ends.
            Assert.AreEqual(1f, Chair.SightRangeFactor, 1e-6f, "the switch does not use the lit range");""")
rep("""                if (trace[i].Action)
                {
                    actionSteps++;
                    Assert.IsTrue(trace[i].Moving, "an action step was not moving");
                }
                Assert.Less(Planar(trace[i].Position, at), 1e-4f, "the lamp travelled during its switch");
            }
            Assert.AreEqual(Mathf.RoundToInt(Tuning.LampToggleTime / Dt), actionSteps, "the switch did not last LampToggleTime");
            Assert.IsFalse(Chair.IsMoving, "moving after the switch");""", """                if (trace[i].Action)
                {
                    actionSteps++;
                    Assert.IsTrue(trace[i].Moving, "an action step was not moving");
                    Assert.AreEqual(1f, trace[i].Factor, 1e-6f, $"switch step {actionSteps}: not the lit range");
                }
                else
                {
                    Assert.AreEqual(Tuning.LampOffLight, trace[i].Factor, 1e-6f, "after the switch: not the dark range");
                }
                Assert.Less(Planar(trace[i].Position, at), 1e-4f, "the lamp travelled during its switch");
            }
            Assert.AreEqual(Mathf.RoundToInt(Tuning.LampToggleTime / Dt), actionSteps, "the switch did not last LampToggleTime");
            Assert.Less(actionSteps, trace.Count - start, "premise: steps after the switch were recorded");
            Assert.IsFalse(Chair.IsMoving, "moving after the switch");
            Assert.AreEqual(Tuning.LampOffLight, Chair.SightRangeFactor, 1e-6f, "the dark range factor");""")
rep("""            Assert.AreEqual(ambientOn, RenderSettings.ambientSkyColor, "the ambient was not restored");
            yield return Steps(12);
            Assert.AreEqual(1f, vision.RangeFactor, 1e-6f);""", """            Assert.AreEqual(ambientOn, RenderSettings.ambientSkyColor, "the ambient was not restored");
            yield return Steps(20);
            Assert.IsFalse(Chair.ActionActive, "premise: the switch is over before the next presses");
            Assert.AreEqual(1f, vision.RangeFactor, 1e-6f);""")

# Step 29i: lying samples, and the tell strength.
rep("""            Assert.Greater(Chair.Velocity.magnitude, Tuning.StoolTipSpeed, "premise: the stool goes faster than the threshold");
            Assert.IsTrue(Chair.TellActive, "no tell above the threshold");
            int topples = Chair.ToppleCount;""", """            Assert.Greater(Chair.Velocity.magnitude, Tuning.StoolTipSpeed, "premise: the stool goes faster than the threshold");
            Assert.IsTrue(Chair.TellActive, "no tell above the threshold");
            Assert.AreEqual(1f, Chair.TellStrength, 1e-6f, "the tell is not full above the threshold");
            int topples = Chair.ToppleCount;
            var samples = new Vector3[Tuning.SampleCount];
            Vector3 size = Chair.Size;
            Chair.GetSamplePoints(samples);
            Assert.AreEqual(size.y - Tuning.SampleInset, samples[1].y - Chair.transform.position.y, 1e-4f, "premise: upright samples");""")
rep("""            Assert.IsFalse(Chair.TellActive, "the tell shows while it falls");
            yield return Until(() => !Chair.ActionActive, 30);""", """            Assert.IsFalse(Chair.TellActive, "the tell shows while it falls");
            Chair.GetSamplePoints(samples);
            Assert.AreEqual(size.y - Tuning.SampleInset, samples[1].y - Chair.transform.position.y, 1e-4f,
                "a falling stool lost its upright samples (the fall keeps the taller box)");
            yield return Until(() => !Chair.ActionActive, 30);""")
rep("""            yield return Steps(50);
            Assert.IsTrue(Chair.LyingDown && !Chair.IsMoving, "the stool got up by itself");""", """            yield return Steps(50);
            Assert.IsTrue(Chair.LyingDown && !Chair.IsMoving, "the stool got up by itself");
            // CONTRACT_M4 10.3: lying, it is seen from the lying box: as high as it is wide, as long as it is tall.
            Chair.GetSamplePoints(samples);
            Vector3 b = Chair.transform.position;
            Assert.AreEqual(size.x * 0.5f, samples[0].y - b.y, 1e-4f, "lying: center sample height");
            float lyingCorner = new Vector2(size.y * 0.5f - Tuning.SampleInset, size.z * 0.5f - Tuning.SampleInset).magnitude;
            for (int i = 1; i < samples.Length; i++)
            {
                Assert.AreEqual(size.x - Tuning.SampleInset, samples[i].y - b.y, 1e-4f, "lying: top sample height");
                Assert.AreEqual(lyingCorner, Planar(samples[i], b), 1e-4f, "lying: top corner distance");
            }""")
rep("""            Assert.IsFalse(Chair.Tipped, "still tipped after righting");
            Assert.AreEqual(topples + 1, Chair.ToppleCount);""", """            Assert.IsFalse(Chair.Tipped, "still tipped after righting");
            Assert.AreEqual(topples + 1, Chair.ToppleCount);
            Chair.GetSamplePoints(samples);
            Assert.AreEqual(size.y - Tuning.SampleInset, samples[1].y - Chair.transform.position.y, 1e-4f, "upright again: upright samples");""")

# Step 29l: the switch in sight is caught; the dark range out of it.
start = s.index("        [UnityTest]\n        public IEnumerator Step29l_")
end = s.index("    }\n}", start)
s = s[:start] + io.open("scratchpad/bodies/tests_m41_new.txt", encoding="utf-8").read() + s[end:]

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
