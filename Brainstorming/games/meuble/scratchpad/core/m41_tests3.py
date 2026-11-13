p = 'Assets/Tests/EditMode/CoreM4Tests.cs'
s = open(p, encoding='utf-8').read()


def rep(old, new, count=1):
    global s
    assert s.count(old) == count, (s.count(old), old[:90])
    s = s.replace(old, new)


# ---- A shared check of the sit down slide ----
rep('''        // ----- Sitting on a prop (gate step 31) -----
''', '''        /// <summary>
        /// CONTRACT_M4 10.2: from the moment of sitting (record <paramref name="sat"/>), over SitSteps records, the body
        /// slides from <paramref name="stand"/> to <paramref name="seat"/> with the same interpolation as the eye, so
        /// the rule eye never jumps; on the last of them it is on the seat home with the eye down. Returns the length.
        /// </summary>
        private static float AssertSlide(Recorder rec, int sat, Vector3 stand, Vector3 seat, string context)
        {
            Assert.GreaterOrEqual(rec.Log.Count, sat + SitSteps, context + ": premise: the sit down was recorded");
            float length = YawMath.Planar(seat - stand).magnitude;
            Assert.AreEqual(YawMath.Planar(stand), YawMath.Planar(rec.Log[sat - 1].Pos), context + ": premise: it stood at the seat front");
            for (int k = 0; k < SitSteps; k++)
            {
                Rec x = rec.Log[sat + k];
                float t = (k + 1f) / SitSteps;
                Assert.AreEqual(Mathf.Lerp(Tuning.EyeHeight, Tuning.SitEyeHeight, t), x.Eye, 1e-4f, $"{context}: eye at sit step {k}");
                Assert.AreEqual(x.Eye, x.EyePos.y, 1e-5f, context + ": EyePosition must use EyeHeight");
                Vector3 expected = Vector3.Lerp(YawMath.Planar(stand), YawMath.Planar(seat), t);
                Assert.Less((YawMath.Planar(x.Pos) - expected).magnitude, 1e-4f, $"{context}: the body is not where the slide puts it at sit step {k}");
                float step = (rec.Log[sat + k].Pos - rec.Log[sat + k - 1].Pos).magnitude;
                Assert.LessOrEqual(step, length / SitSteps + 1e-4f, $"{context}: jumped {step:0.000} m at sit step {k}");
            }
            Rec down = rec.Log[sat + SitSteps - 1];
            Assert.AreEqual(Tuning.SitEyeHeight, down.Eye, context + ": the eye is not down at the end of the sit down");
            Assert.Less((YawMath.Planar(down.Pos) - YawMath.Planar(seat)).magnitude, 1e-5f, context + ": not on the seat home at the end of the sit down");
            Assert.Greater(rec.Log[sat + SitSteps - 2].Eye, Tuning.SitEyeHeight + 1e-3f, context + ": lowered too early");
            return length;
        }

        // ----- Sitting on a prop (gate step 31) -----
''')

# ---- The prop sit test, on a level read by LevelJson ----
rep('''            List<StationDef> stations = PropLoop();
            StationDef seat = stations[1];
            var rec = new Recorder(new InhabitantRoutine(stations, 0));
            InhabitantRoutine r = rec.R;
            rec.StepUntil(x => x.JustSat, 3000, "the moment of sitting");
            int sat = rec.Index;
''', '''            List<StationDef> stations = PropLoop();
            StationDef seat = stations[1];
            Assert.IsTrue(seat.PropSeat.HasValue, "premise: LevelJson resolved the prop seat");
            Assert.AreEqual(SofaCenter, seat.PropSeat.Value.Position, "premise: ResolveSeats gives the sofa center");
            float slide = YawMath.Planar(seat.Position - SofaCenter).magnitude;
            Assert.That(slide, Is.InRange(0.3f, MaxSlide), "premise: a valid seat front, 0.3 to 0.8 m from the prop center");
            var rec = new Recorder(new InhabitantRoutine(stations, 0));
            InhabitantRoutine r = rec.R;
            rec.StepUntil(x => x.JustSat, 3000, "the moment of sitting");
            int sat = rec.Index;
''')
rep('''            Assert.AreEqual(RoutineActivity.Sitting, r.LastActivity);
            Assert.AreEqual(seat.Position, r.Position, "sits where it stood (the prop seat is the station pose)");
            Assert.AreEqual(seat.Position, r.SeatHome.Position);
            Assert.AreEqual(seat.Facing, r.SeatHome.Yaw);
            Assert.AreEqual(0f, Mathf.DeltaAngle(seat.Facing, r.BodyYaw), 1e-3f, "seated facing the station facing");

            // The eye lowers over SitEyeRiseTime, exactly.
            for (int k = 0; k < SitSteps; k++)
            {
                Rec x = rec.Log[sat + k];
                Assert.AreEqual(Mathf.Lerp(Tuning.EyeHeight, Tuning.SitEyeHeight, (k + 1f) / SitSteps), x.Eye, 1e-4f, $"eye at sit step {k}");
                Assert.AreEqual(x.Eye, x.EyePos.y, 1e-5f, "EyePosition must use EyeHeight");
                if (k < SitSteps - 1)
                {
                    rec.Step();
                }
            }
            Assert.AreEqual(Tuning.SitEyeHeight, r.EyeHeight, "lowered in full");
            Assert.Greater(rec.Log[sat + SitSteps - 2].Eye, Tuning.SitEyeHeight + 1e-3f, "lowered too early");

            rec.StepUntil(x => !x.IsSitting, 1000, "the end of the sitting");
            int up = rec.Index;
            List<Rec> seated = rec.Log.GetRange(sat, up - sat);
            Assert.IsTrue(seated.TrueForAll(x => x.Sitting && x.Pos == seat.Position), "left the seat while seated");''',
    '''            Assert.AreEqual(RoutineActivity.Sitting, r.LastActivity);
            Assert.AreEqual(SofaCenter, r.SeatHome.Position, "the seat home of a prop is the prop center (CONTRACT_M4 10.2)");
            Assert.AreEqual(seat.Facing, r.SeatHome.Yaw, "facing the station's facing");
            Assert.AreEqual(0f, Mathf.DeltaAngle(seat.Facing, r.BodyYaw), 1e-3f, "seated facing the station facing");
            Assert.Less(YawMath.Planar(r.Position - seat.Position).magnitude, slide / SitSteps + 1e-4f, "jumped at the moment of sitting");

            // The body slides onto the sofa center while the eye lowers, over SitEyeRiseTime, exactly.
            rec.Step(SitSteps - 1);
            AssertSlide(rec, sat, seat.Position, SofaCenter, "prop sit");

            rec.StepUntil(x => !x.IsSitting, 1000, "the end of the sitting");
            int up = rec.Index;
            List<Rec> seated = rec.Log.GetRange(sat, up - sat);
            Assert.IsTrue(seated.TrueForAll(x => x.Sitting), "IsSitting dropped while seated");
            Assert.IsTrue(seated.GetRange(SitSteps - 1, seated.Count - SitSteps + 1).TrueForAll(x => x.Pos == SofaCenter), "left the seat while seated");''')
rep('''            Assert.AreEqual(Tuning.EyeHeight, r.EyeHeight);
            Assert.IsFalse(r.IsLowered);
            rec.Step();
            Assert.AreNotEqual(RoutineActivity.StandingUp, r.LastActivity, "the stand up is longer than SitEyeRiseTime");''',
    '''            Assert.AreEqual(Tuning.EyeHeight, r.EyeHeight);
            Assert.IsFalse(r.IsLowered);
            Assert.AreEqual(seat.Position, r.Position, "stood up back at the seat front");
            rec.Step();
            Assert.AreNotEqual(RoutineActivity.StandingUp, r.LastActivity, "the stand up is longer than SitEyeRiseTime");''')

# ---- The player sit: slide instead of a jump ----
rep('''            Assert.AreEqual(stations[1].Position, rec.Log[sat - 1].Pos, "premise: it stood at the seat front");
            Assert.AreEqual(PlayerSeatHome, r.Position, "seated: Position is the seat home");
''', '''            Assert.AreEqual(stations[1].Position, rec.Log[sat - 1].Pos, "premise: it stood at the seat front");
            rec.Step(SitSteps - 1);
            AssertSlide(rec, sat, stations[1].Position, PlayerSeatHome, "sit on the player");
''')

# ---- The pratfall: slide onto the empty seat ----
rep('''            Assert.AreEqual(RoutineActivity.Pratfall, r.LastActivity);
            Assert.AreEqual(PlayerSeatHome, r.Position, "falls where the seat should be");

            rec.StepUntil(x => x.Mode == InhabitantMode.Alerted, 1000, "the look");
            List<Rec> s = rec.Log;
            int i = fall;
            Assert.AreEqual(PratfallSteps, CountLeading(s, i, RoutineActivity.Pratfall), "the fall is not PratfallTime long");''',
    '''            Assert.AreEqual(RoutineActivity.Pratfall, r.LastActivity);

            rec.StepUntil(x => x.Mode == InhabitantMode.Alerted, 1000, "the look");
            AssertSlide(rec, fall, stations[1].Position, PlayerSeatHome, "pratfall");
            List<Rec> s = rec.Log;
            int i = fall;
            Assert.AreEqual(PratfallSteps, CountLeading(s, i, RoutineActivity.Pratfall), "the fall is not PratfallTime long");
            Assert.IsTrue(s.GetRange(fall + SitSteps - 1, PratfallSteps - SitSteps + 1).TrueForAll(x => x.Pos == PlayerSeatHome),
                "the fall does not end where the seat should be");''')

# ---- Alert while seated: the seat home is the sofa center ----
rep('''            Assert.IsTrue(look.TrueForAll(x => x.Sitting && x.Eye == Tuning.SitEyeHeight && x.Pos == stations[1].Position), "left the seat during the look");''',
    '''            Assert.IsTrue(look.TrueForAll(x => x.Sitting && x.Eye == Tuning.SitEyeHeight && x.Pos == SofaCenter), "left the seat during the look");''')

# ---- Real data: every shipped level ----
rep('''        // ----- Investigate, alert and switch on while seated -----
''', '''        [Test]
        public void Shipped_levels_sit_on_the_prop_center_or_the_player_seat_and_slide_there_without_a_jump()
        {
            int props = 0;
            int players = 0;
            var lengths = new List<string>();
            foreach (string path in Directory.GetFiles("Assets/Resources/Levels", "*.json"))
            {
                string file = Path.GetFileName(path);
                if (file == LevelManifest.FileName + ".json")
                {
                    continue;
                }
                LevelDef level = LevelJson.Parse(File.ReadAllText(path));
                foreach (InhabitantDef h in level.Inhabitants)
                {
                    var sitStations = new HashSet<int>();
                    for (int i = 0; i < h.Stations.Count; i++)
                    {
                        if (!string.IsNullOrEmpty(h.Stations[i].Sit))
                        {
                            sitStations.Add(i);
                        }
                    }
                    if (sitStations.Count == 0)
                    {
                        continue;
                    }
                    // The routine as the audit steps it: no GameState, so a player seat counts as occupied.
                    var rec = new Recorder(new InhabitantRoutine(h.Stations, h.StartStation));
                    var done = new HashSet<int>();
                    int guard = 0;
                    while (done.Count < sitStations.Count)
                    {
                        Assert.Less(guard++, 40000, $"{file} {h.Name}: never sat at every sit station");
                        rec.Step();
                        if (!rec.R.JustSat || !done.Add(rec.R.StationIndex))
                        {
                            continue;
                        }
                        int sat = rec.Index;
                        StationDef st = h.Stations[rec.R.StationIndex];
                        string context = $"{file} {h.Name} station {rec.R.StationIndex}";
                        Vector3 seat;
                        if (st.SitsOnPlayer)
                        {
                            Assert.IsNotNull(st.Seat, context + ": a player sit without a seat home");
                            seat = new Vector3(st.Seat.X, 0f, st.Seat.Z);
                            players++;
                        }
                        else
                        {
                            PropDef prop = level.Props.Find(p => p.Name == st.Sit);
                            Assert.IsNotNull(prop, $"{context}: no prop named {st.Sit}");
                            seat = prop.Position;
                            props++;
                        }
                        Assert.Less((YawMath.Planar(rec.R.SeatHome.Position) - YawMath.Planar(seat)).magnitude, 1e-4f,
                            context + ": the seat home is not the prop center or the player seat");
                        rec.Step(SitSteps - 1);
                        float length = AssertSlide(rec, sat, st.Position, seat, context);
                        lengths.Add($"{context} ({st.Sit}): {length:0.00} m");
                    }
                }
            }
            TestContext.WriteLine("sit slides: " + string.Join("; ", lengths));
            Assert.Greater(props, 0, "premise: no shipped level sits on a prop");
            Assert.Greater(players, 0, "premise: no shipped level sits on the player");
        }

        // ----- Investigate, alert and switch on while seated -----
''')
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print("ok")
