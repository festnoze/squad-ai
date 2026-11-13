import io
p = "Assets/Tests/PlayMode/ProbeTestsM4Game.cs"
s = io.open(p, encoding="utf-8").read()
def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:80])
    s = s.replace(a, b, 1)
rep("""            // The tell: on every step clearly above the tip speed, and on none clearly below.
            int above = 0, below = 0;
            foreach ((float speed, bool on, bool rattle) in tell)
            {
                Assert.AreEqual(on, rattle, $"the rattle loop does not follow the tell at {speed:0.00} m/s");
                if (speed > Tuning.StoolTipSpeed + 0.02f)
                {
                    above++;
                    Assert.IsTrue(on, $"no tell at {speed:0.00} m/s");
                }
                else if (speed < Tuning.StoolTipSpeed - 0.02f)
                {
                    below++;
                    Assert.IsFalse(on, $"the tell shows at {speed:0.00} m/s");
                }
            }
            Assert.Greater(above, 20, "premise: too few steps above the tip speed");
            Assert.Greater(below, 2, "premise: too few steps below the tip speed");""", """            // M4.1 (CONTRACT_M4 10.3): the tell is a warning band. It shows on every step clearly above the tell speed
            // (1.0 m/s), so it is on for the 0.25 s climb to the tip speed (1.3 m/s), and on none clearly below.
            int above = 0, below = 0, band = 0;
            foreach ((float speed, bool on, bool rattle) in tell)
            {
                Assert.AreEqual(on, rattle, $"the rattle loop does not follow the tell at {speed:0.00} m/s");
                if (speed > Tuning.StoolTellSpeed + 0.02f)
                {
                    above++;
                    band += speed < Tuning.StoolTipSpeed ? 1 : 0;
                    Assert.IsTrue(on, $"no tell at {speed:0.00} m/s");
                }
                else if (speed < Tuning.StoolTellSpeed - 0.02f)
                {
                    below++;
                    Assert.IsFalse(on, $"the tell shows at {speed:0.00} m/s");
                }
            }
            Assert.Greater(above, 20, "premise: too few steps above the tell speed");
            Assert.GreaterOrEqual(below, 2, "premise: too few steps below the tell speed");
            Assert.GreaterOrEqual(band, StepsOf(0.25f) - 2, "the warning band (tell on, below the tip speed) is shorter than 0.25 s");""")
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("ok")
