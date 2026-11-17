p = 'Assets/Tests/EditMode/CoreM4Tests.cs'
s = open(p, encoding='utf-8').read()


def rep(old, new, count=1):
    global s
    assert s.count(old) == count, (s.count(old), old[:90])
    s = s.replace(old, new)


# ---- BodyDef: stool row and the tell band (10.3) ----
rep('''                Row("stool", new Vector3(0.35f, 0.55f, 0.35f), 0.22f, 2.4f, 14f, Tuning.StoolHighAccel, Tuning.StoolTipSpeed, 540f, 0.45f,''',
    '''                Row("stool", new Vector3(0.35f, 0.55f, 0.35f), 0.22f, 2.4f, 14f, Tuning.StoolHighAccel, Tuning.StoolTellSpeed, 540f, 0.45f,''')
rep('''            // Amendment 9.5 and section 2.1: the stage speed is the tip threshold, and careful mode stays below it.
            BodyDef s = BodyDef.For("stool");
            Assert.AreEqual(1.3f, s.StageSpeed);
            Assert.AreEqual(1.2f, s.AccelHigh);
            Assert.Less(s.MaxSpeed * Tuning.CarefulFactor, s.StageSpeed, "careful mode would tip the stool");
            Assert.Greater(s.MaxSpeed, s.StageSpeed, "premise: full speed is above the tip threshold");''',
    '''            // CONTRACT_M4 10.3: the fast stage ends at the tell speed, 1.0 m/s; the climb to the unchanged 1.3 m/s tip
            // speed at 1.2 m/s2 is 0.25 s of visible tell. Careful mode stays below the tip speed.
            BodyDef s = BodyDef.For("stool");
            Assert.AreEqual(1.0f, s.StageSpeed, "the fast stage must end at the tell speed");
            Assert.AreEqual(1.2f, s.AccelHigh);
            Assert.AreEqual(1.3f, Tuning.StoolTipSpeed, "the tip speed is unchanged");
            Assert.AreEqual(0.25f, (Tuning.StoolTipSpeed - s.StageSpeed) / s.AccelHigh, 1e-4f, "the tell band is not 0.25 s");
            Assert.Less(s.StageSpeed, Tuning.StoolTipSpeed, "no tell before the tip");
            Assert.Less(s.MaxSpeed * Tuning.CarefulFactor, Tuning.StoolTipSpeed, "careful mode would tip the stool");
            Assert.Greater(s.MaxSpeed, Tuning.StoolTipSpeed, "premise: full speed is above the tip threshold");''')

# ---- Fixtures: prop seats resolved like real levels ----
rep('''        /// <summary>A plain station, then a sofa seat reached with a 90 deg back turn, with one glance while seated.</summary>
        private static List<StationDef> PropLoop(string sit = "sofa") => new List<StationDef>
        {
            Plain(3f, 0f, 90f, 1f),
            OnProp(0f, 0f, 0f, 2f, sit, Glance(0.5f, 60f, 0.3f)),
        };''',
    '''        /// <summary>
        /// A plain station, then a sofa seat reached with a 90 deg back turn, with one glance while seated. Read with
        /// LevelJson, like a real level, so the seat is resolved by LevelDef.ResolveSeats: the sofa center, 0.6 m
        /// behind the seat front (CONTRACT_M4 10.2).
        /// </summary>
        private const string PropLevelJson = @"{
  ""id"": ""core_m4_prop_sit"",
  ""props"": [ { ""name"": ""Sofa"", ""kind"": ""sofa"", ""x"": 0.0, ""z"": -0.6, ""yaw"": 0.0, ""sizeX"": 1.8, ""sizeY"": 0.8, ""sizeZ"": 0.8 } ],
  ""inhabitants"": [ {
    ""name"": ""Habitant"",
    ""startStation"": 0,
    ""stations"": [
      { ""x"": 3.0, ""z"": 0.0, ""facing"": 90.0, ""dwell"": 1.0 },
      { ""x"": 0.0, ""z"": 0.0, ""facing"": 0.0, ""dwell"": 2.0, ""sit"": ""Sofa"", ""glances"": [ { ""offset"": 0.5, ""yaw"": 60.0, ""hold"": 0.3 } ] }
    ]
  } ]
}";

        private static readonly Vector3 SofaCenter = new Vector3(0f, 0f, -0.6f);

        private static List<StationDef> PropLoop() => LevelJson.Parse(PropLevelJson).Inhabitants[0].Stations;

        /// <summary>Resolves the prop seats of hand-made stations against <paramref name="props"/>, as a real level does.</summary>
        private static List<StationDef> Resolved(List<StationDef> stations, params PropDef[] props)
        {
            var level = new LevelDef();
            level.Props.AddRange(props);
            level.Inhabitants.Add(new InhabitantDef { Name = "Habitant", Stations = stations });
            level.ResolveSeats();
            return stations;
        }

        private static PropDef Sofa(string name, float x, float z) =>
            new PropDef { Name = name, Kind = "sofa", X = x, Z = z, SizeX = 1.8f, SizeY = 0.8f, SizeZ = 0.8f };

        /// <summary>The largest slide from a seat front to its seat home that a valid level allows (CONTRACT_M4 10.2).</summary>
        private const float MaxSlide = 0.8f;''')

rep('''        /// <summary>Level 1's loop with a sofa seat and the player's seat (behind the sitter, facing 180).</summary>
        private static List<StationDef> Mixed() => new List<StationDef>
        {
            Plain(-1.5f, 2.2f, 0f, 3f, Glance(1f, -70f, 1f)),
            OnProp(1.2f, 1.4f, 180f, 2.5f, "sofa", Glance(0.5f, 60f, 0.5f)),
            OnPlayer(0f, -2.3f, 180f, 2f, 0f, -1.8f, 180f),
            Plain(2.2f, -0.7f, 180f, 2f, Glance(2f, -80f, 1f)),
        };''',
    '''        /// <summary>
        /// Level 1's loop with a sofa seat (its center 0.6 m behind the sitter, resolved) and the player's seat (0.5 m
        /// behind the sitter, facing 180).
        /// </summary>
        private static List<StationDef> Mixed() => Resolved(new List<StationDef>
        {
            Plain(-1.5f, 2.2f, 0f, 3f, Glance(1f, -70f, 1f)),
            OnProp(1.2f, 1.4f, 180f, 2.5f, "sofa", Glance(0.5f, 60f, 0.5f)),
            OnPlayer(0f, -2.3f, 180f, 2f, 0f, -1.8f, 180f),
            Plain(2.2f, -0.7f, 180f, 2f, Glance(2f, -80f, 1f)),
        }, Sofa("sofa", 1.2f, 2.0f));''')

# ---- Analyzer: no sit jump whitelist; a bounded slide that goes with the eye ----
rep('''        /// at least 0.6 s of telegraph, the head within its limit), extended to M4: motion only while walking,
        /// carrying or standing up, plus the one step jump onto the seat home at the moment of sitting; no body turn
        /// while lowered (a seated look is head only); the eye lowers only while sitting down or falling, rises only
        /// while standing up, and every stand up comes right after a full telegraph; never walking, carrying or
        /// switching on while lowered; seated means on the seat home, and the pin flag means seated.''',
    '''        /// at least 0.6 s of telegraph, the head within its limit), extended to M4: motion only while walking,
        /// carrying or standing up, or while sitting down or falling on a step where the eye goes down too (the slide
        /// of CONTRACT_M4 10.2: no jump is whitelisted, and a sit or stand slide moves at most 0.8 m over 0.5 s); no
        /// body turn while lowered (a seated look is head only); the eye lowers only while sitting down or falling,
        /// rises only while standing up, and every stand up comes right after a full telegraph; never walking,
        /// carrying or switching on while lowered; seated with the eye down means on the seat home, and the pin flag
        /// means seated.''')
rep('''                bool moved = (b.Pos - a.Pos).sqrMagnitude > 1e-12f;
                bool snap = b.JustSat && (YawMath.Planar(b.Pos) - YawMath.Planar(b.SeatHome.Position)).sqrMagnitude < 1e-10f;
                if (moved && b.Act != RoutineActivity.Walking && b.Act != RoutineActivity.Carrying && b.Act != RoutineActivity.StandingUp && !snap)
                {
                    return $"moved during {b.Act} at record {i}";
                }''',
    '''                float step = (b.Pos - a.Pos).magnitude;
                bool moved = step > 1e-6f;
                bool sitSlide = (b.Act == RoutineActivity.Sitting || b.Act == RoutineActivity.Pratfall) && b.Eye < a.Eye - 1e-5f;
                if (moved && b.Act != RoutineActivity.Walking && b.Act != RoutineActivity.Carrying && b.Act != RoutineActivity.StandingUp && !sitSlide)
                {
                    return $"moved during {b.Act} at record {i}";
                }
                if ((sitSlide || b.Act == RoutineActivity.StandingUp) && step > MaxSlide / SitSteps + 1e-4f)
                {
                    return $"slid {step:0.000} m in one step during {b.Act} at record {i} (at most {MaxSlide} m over {Tuning.SitEyeRiseTime} s)";
                }''')
rep('''                if (b.Sitting && (YawMath.Planar(b.Pos) - YawMath.Planar(b.SeatHome.Position)).sqrMagnitude > 1e-10f)
                {
                    return $"seated away from the seat home at record {i}";
                }''',
    '''                if (b.Sitting && b.Eye <= Tuning.SitEyeHeight + 1e-5f
                    && (YawMath.Planar(b.Pos) - YawMath.Planar(b.SeatHome.Position)).sqrMagnitude > 1e-10f)
                {
                    return $"seated away from the seat home at record {i}";
                }''')

# ---- Synthetic sit: a real slide over SitSteps, both ways ----
rep('''            for (int i = 1; i <= 10; i++)
            {
                r = new Rec
                {
                    Pos = seat.Position, Eye = Mathf.Lerp(Tuning.EyeHeight, Tuning.SitEyeHeight, i / 10f), Act = RoutineActivity.Sitting,
                    Sitting = true, Lowered = true, JustSat = i == 1, SeatHome = seat,
                };''',
    '''            for (int i = 1; i <= SitSteps; i++)
            {
                float t = (float)i / SitSteps;
                r = new Rec
                {
                    Pos = Vector3.Lerp(stand, seat.Position, t), Eye = Mathf.Lerp(Tuning.EyeHeight, Tuning.SitEyeHeight, t),
                    Act = RoutineActivity.Sitting, Sitting = true, Lowered = true, JustSat = i == 1, SeatHome = seat,
                };''')
rep('''            for (int i = 1; i <= 5; i++)
            {
                r = new Rec
                {
                    Pos = Vector3.Lerp(seat.Position, stand, i / 5f), Eye = Mathf.Lerp(Tuning.SitEyeHeight, Tuning.EyeHeight, i / 5f),
                    Act = RoutineActivity.StandingUp, Lowered = i < 5, SeatHome = seat,
                };''',
    '''            for (int i = 1; i <= SitSteps; i++)
            {
                float t = (float)i / SitSteps;
                r = new Rec
                {
                    Pos = Vector3.Lerp(seat.Position, stand, t), Eye = Mathf.Lerp(Tuning.SitEyeHeight, Tuning.EyeHeight, t),
                    Act = RoutineActivity.StandingUp, Lowered = i < SitSteps, SeatHome = seat,
                };''')
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print("ok")
