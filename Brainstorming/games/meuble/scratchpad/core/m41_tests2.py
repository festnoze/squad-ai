p = 'Assets/Tests/EditMode/CoreM4Tests.cs'
s = open(p, encoding='utf-8').read()


def rep(old, new, count=1):
    global s
    assert s.count(old) == count, (s.count(old), old[:90])
    s = s.replace(old, new)


rep('''        public void Analyzer_premise_catches_an_untelegraphed_stand_up_a_seated_body_turn_and_a_slide_while_seated()
        {
            Assert.IsNull(FindViolation(SyntheticSit(TelegraphSteps), out _), "the clean sit");
            StringAssert.Contains("stand up", FindViolation(SyntheticSit(TelegraphSteps - 1), out _));

            List<Rec> turned = SyntheticSit(TelegraphSteps);
            Rec t = turned[5];
            t.Act = RoutineActivity.TurningBody;
            t.Body = 10f;
            turned[5] = t;
            StringAssert.Contains("while lowered", FindViolation(turned, out _));

            List<Rec> slid = SyntheticSit(TelegraphSteps);
            Rec m = slid[6];
            m.Pos += new Vector3(0.01f, 0f, 0f);
            m.EyePos = m.Pos + Vector3.up * m.Eye;
            slid[6] = m;
            StringAssert.Contains("moved during Sitting", FindViolation(slid, out _));

            // Record 15 is in the stand up telegraph: seated, the eye still.
            List<Rec> walked = SyntheticSit(TelegraphSteps);
            Rec w = walked[15];
            w.Act = RoutineActivity.Walking;
            walked[15] = w;
            StringAssert.Contains("Walking while lowered", FindViolation(walked, out _));
        }''',
    '''        public void Analyzer_premise_catches_a_sit_jump_an_untelegraphed_stand_up_a_seated_body_turn_and_a_slide_while_seated()
        {
            // Records: 0 standing, 1 to SitSteps the sit down slide, then the stand up telegraph, then the stand up.
            int seated = SitSteps + 3;
            Assert.IsNull(FindViolation(SyntheticSit(TelegraphSteps), out _), "the clean sit");
            StringAssert.Contains("stand up", FindViolation(SyntheticSit(TelegraphSteps - 1), out _));

            // The M4 behavior that 10.2 removed: the body jumps onto the seat home at the moment of sitting.
            List<Rec> jump = SyntheticSit(TelegraphSteps);
            for (int i = 1; i <= SitSteps; i++)
            {
                Rec j = jump[i];
                j.Pos = j.SeatHome.Position;
                j.EyePos = j.Pos + Vector3.up * j.Eye;
                jump[i] = j;
            }
            StringAssert.Contains("in one step during Sitting", FindViolation(jump, out _));

            // A slide longer than 0.8 m over 0.5 s.
            List<Rec> far = SyntheticSit(TelegraphSteps);
            for (int i = 0; i <= SitSteps; i++)
            {
                Rec f = far[i];
                f.Pos = Vector3.Lerp(new Vector3(0f, 0f, MaxSlide + 0.1f), f.SeatHome.Position, (float)i / SitSteps);
                f.EyePos = f.Pos + Vector3.up * f.Eye;
                far[i] = f;
            }
            StringAssert.Contains("in one step during Sitting", FindViolation(far, out _));

            List<Rec> turned = SyntheticSit(TelegraphSteps);
            Rec t = turned[5];
            t.Act = RoutineActivity.TurningBody;
            t.Body = 10f;
            turned[5] = t;
            StringAssert.Contains("while lowered", FindViolation(turned, out _));

            List<Rec> slid = SyntheticSit(TelegraphSteps);
            Rec m = slid[seated];
            m.Pos += new Vector3(0.01f, 0f, 0f);
            m.EyePos = m.Pos + Vector3.up * m.Eye;
            slid[seated] = m;
            StringAssert.Contains("moved during Telegraph", FindViolation(slid, out _));

            List<Rec> walked = SyntheticSit(TelegraphSteps);
            Rec w = walked[seated];
            w.Act = RoutineActivity.Walking;
            walked[seated] = w;
            StringAssert.Contains("Walking while lowered", FindViolation(walked, out _));
        }''')
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print("ok")
