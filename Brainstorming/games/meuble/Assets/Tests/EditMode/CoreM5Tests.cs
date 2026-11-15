using System;
using System.Collections.Generic;
using System.Reflection;
using Meuble.Core;
using NUnit.Framework;
using UnityEngine;

namespace Meuble.Tests
{
    /// <summary>Shared fixtures, recorder and telegraph analyzer of the M5 core tests (docs/CONTRACT_M5.md 3, 16.7).</summary>
    internal static class M5
    {
        public const float Dt = Tuning.FixedStep;
        public static readonly int TelegraphSteps = Mathf.RoundToInt(Tuning.TelegraphDuration / Dt);
        public static readonly int WakeSteps = Mathf.RoundToInt(Tuning.WakeTelegraph / Dt);
        public static readonly int SitSteps = Mathf.RoundToInt(Tuning.SitEyeRiseTime / Dt);
        public static readonly int GraceSteps = Mathf.RoundToInt(Tuning.DiscoveryGrace / Dt);

        public static GlanceDef Glance(float offset, float yaw, float hold) => new GlanceDef { Offset = offset, Yaw = yaw, Hold = hold };

        public static StationDef Plain(float x, float z, float facing, float dwell, params GlanceDef[] glances)
        {
            var s = new StationDef { X = x, Z = z, Facing = facing, Dwell = dwell };
            s.Glances.AddRange(glances);
            return s;
        }

        public static InhabitantDef Def(List<StationDef> stations, int start = 0, string personality = null, string kind = null,
            string pattern = null, int seed = 0)
        {
            return new InhabitantDef
            {
                Name = "Habitant", Stations = stations, StartStation = start, Personality = personality, Kind = kind,
                Pattern = pattern, Seed = seed,
            };
        }

        /// <summary>The def of a personality id: the dog by its kind, the others by their personality.</summary>
        public static InhabitantDef DefOf(string id, List<StationDef> stations, int start = 0)
        {
            bool dog = id == PersonalityDef.Dog;
            return Def(stations, start, dog ? null : id, dog ? PersonalityDef.Dog : null);
        }

        /// <summary>Four corners of a 2 m square, each facing outward, so every arrival and departure turn is large.</summary>
        public static List<StationDef> Square(float dwell) => new List<StationDef>
        {
            Plain(0f, 0f, -135f, dwell),
            Plain(2f, 0f, 135f, dwell),
            Plain(2f, 2f, 45f, dwell),
            Plain(0f, 2f, -45f, dwell),
        };

        /// <summary>The stations of level 1 (a copy, so these tests do not depend on the level file).</summary>
        public static List<StationDef> Level1() => new List<StationDef>
        {
            Plain(-1.5f, 2.2f, 0f, 6f, Glance(3f, -70f, 1f)),
            Plain(1.2f, 1.4f, 180f, 3f, Glance(1f, 60f, 0.8f)),
            Plain(0f, -2.3f, 180f, 5f),
            Plain(2.2f, -0.7f, 180f, 4f, Glance(2f, -80f, 1f)),
        };

        /// <summary>
        /// A plain station, then a sofa seat reached with a 90 deg back turn (no glance). Read with LevelJson so the seat
        /// is resolved like a real level: the sofa center, 0.6 m behind the seat front.
        /// </summary>
        private const string SofaJson = @"{
  ""id"": ""core_m5_sofa"",
  ""props"": [ { ""name"": ""Sofa"", ""kind"": ""sofa"", ""x"": 0.0, ""z"": -0.6, ""yaw"": 0.0, ""sizeX"": 1.8, ""sizeY"": 0.8, ""sizeZ"": 0.8 } ],
  ""inhabitants"": [ {
    ""name"": ""Habitant"",
    ""startStation"": 0,
    ""stations"": [
      { ""x"": 3.0, ""z"": 0.0, ""facing"": 90.0, ""dwell"": 1.0 },
      { ""x"": 0.0, ""z"": 0.0, ""facing"": 0.0, ""dwell"": 2.0, ""sit"": ""Sofa"" }
    ]
  } ]
}";

        public const string Sofa = "Sofa";

        public static List<StationDef> SofaLoop() => LevelJson.Parse(SofaJson).Inhabitants[0].Stations;

        /// <summary>A plain station, then the player's seat at the origin (facing +z), its front 0.5 m ahead of it.</summary>
        public static List<StationDef> PlayerLoop()
        {
            StationDef seat = Plain(0f, 0.5f, 0f, 2f);
            seat.Sit = InhabitantRoutine.PlayerSeat;
            seat.Seat = new SeatDef { X = 0f, Z = 0f, Yaw = 0f };
            return new List<StationDef> { Plain(3f, 0f, 90f, 1f), seat };
        }

        /// <summary>Along x first (or z first), then the other axis; counts its calls.</summary>
        public sealed class LPlanner : IPathPlanner
        {
            public readonly bool XFirst;
            public int Calls;

            public LPlanner(bool xFirst = true)
            {
                XFirst = xFirst;
            }

            public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners)
            {
                Calls++;
                corners.Clear();
                Vector3 a = YawMath.Planar(from);
                Vector3 b = YawMath.Planar(to);
                Vector3 corner = XFirst ? new Vector3(b.x, 0f, a.z) : new Vector3(a.x, 0f, b.z);
                if ((corner - a).sqrMagnitude > 1e-6f && (corner - b).sqrMagnitude > 1e-6f)
                {
                    corners.Add(corner);
                }
                corners.Add(b);
                return true;
            }
        }

        /// <summary>The L corner the planner would give from a to b.</summary>
        public static Vector3 Corner(bool xFirst, Vector3 a, Vector3 b) => xFirst ? new Vector3(b.x, 0f, a.z) : new Vector3(a.x, 0f, b.z);

        // ----- The analyzer: every turn over 30 deg comes right after a full telegraph -----

        public static int CountBefore(List<M5Rec> s, int index, RoutineActivity act)
        {
            int n = 0;
            for (int k = index - 1; k >= 0 && s[k].Act == act; k--)
            {
                n++;
            }
            return n;
        }

        public static int CountLeading(List<M5Rec> s, int from, RoutineActivity act)
        {
            int n = 0;
            while (from + n < s.Count && s[from + n].Act == act)
            {
                n++;
            }
            return n;
        }

        /// <summary>
        /// Cuts body and head yaw changes into turn segments, exactly as the M2 and M4 analyzers do, and returns the first
        /// segment over 30 deg that was not preceded, immediately, by at least 0.6 s of telegraph (null when none). Also
        /// fails a yaw change outside a turning step.
        /// </summary>
        public static string TelegraphViolation(List<M5Rec> s, out int large)
        {
            large = 0;
            for (int i = 1; i < s.Count && s[i].Act != RoutineActivity.Startled; i++)
            {
                float db = Mathf.Abs(Mathf.DeltaAngle(s[i - 1].Body, s[i].Body));
                float dh = Mathf.Abs(Mathf.DeltaAngle(s[i - 1].Head, s[i].Head));
                if (db >= 1e-3f && s[i].Act != RoutineActivity.TurningBody)
                {
                    return $"body yaw changed during {s[i].Act} at record {i}";
                }
                if (dh >= 1e-3f && s[i].Act != RoutineActivity.TurningBody && s[i].Act != RoutineActivity.TurningHead)
                {
                    return $"head yaw changed during {s[i].Act} at record {i}";
                }
            }
            return Segments(s, x => x.Body, "body", ref large) ?? Segments(s, x => x.Head, "head", ref large);
        }

        private static string Segments(List<M5Rec> s, Func<M5Rec, float> yaw, string label, ref int large)
        {
            int i = 1;
            while (i < s.Count && s[i].Act != RoutineActivity.Startled)
            {
                if (Mathf.Abs(Mathf.DeltaAngle(yaw(s[i - 1]), yaw(s[i]))) < 1e-3f)
                {
                    i++;
                    continue;
                }
                int start = i;
                float total = 0f;
                while (i < s.Count && s[i].Act != RoutineActivity.Startled && Mathf.Abs(Mathf.DeltaAngle(yaw(s[i - 1]), yaw(s[i]))) >= 1e-3f)
                {
                    total += Mathf.Abs(Mathf.DeltaAngle(yaw(s[i - 1]), yaw(s[i])));
                    i++;
                }
                if (total > Tuning.TelegraphMinTurn)
                {
                    large++;
                    int tele = CountBefore(s, start, RoutineActivity.Telegraph);
                    if (tele < TelegraphSteps)
                    {
                        return $"{label} turn of {total:0.0} deg at record {start} was preceded by only {tele * Dt:0.00} s of telegraph";
                    }
                }
            }
            return null;
        }

        public static int AssertTelegraphs(List<M5Rec> s, string context)
        {
            string violation = TelegraphViolation(s, out int large);
            Assert.IsNull(violation, context + ": " + violation);
            return large;
        }
    }

    /// <summary>One step of a routine, as the M5 tests read it.</summary>
    internal struct M5Rec
    {
        public Vector3 Pos;
        public float Body;
        public float Head;
        public float Eye;
        public Vector3 EyePos;
        public Vector3 Anchor;
        public RoutineActivity Act;
        public InhabitantMode Mode;
        public int Station;
        public int Visit;
        public bool InDwell;
        public bool Asleep;
        public bool Sitting;
        public bool Lowered;
        public bool JustSat;
        public bool Targets;
        public bool SeesProbe;
        public int Telegraphs;
        public int Loops;
    }

    internal sealed class M5Recorder
    {
        public readonly InhabitantRoutine R;
        public readonly List<M5Rec> Log = new List<M5Rec>();
        /// <summary>A point whose <see cref="InhabitantRoutine.InCone"/> each record stores (null: none).</summary>
        public Vector3? Probe;

        public M5Recorder(InhabitantRoutine r, Vector3? probe = null)
        {
            R = r;
            Probe = probe;
            Log.Add(Snap());
        }

        public M5Rec Last => Log[Log.Count - 1];
        public int Index => Log.Count - 1;

        private M5Rec Snap() => new M5Rec
        {
            Pos = R.Position,
            Body = R.BodyYaw,
            Head = R.HeadYaw,
            Eye = R.EyeHeight,
            EyePos = R.EyePosition,
            Anchor = R.CarryAnchor,
            Act = R.LastActivity,
            Mode = R.Mode,
            Station = R.StationIndex,
            Visit = R.VisitIndex,
            InDwell = R.InDwell,
            Asleep = R.Asleep,
            Sitting = R.IsSitting,
            Lowered = R.IsLowered,
            JustSat = R.JustSat,
            Targets = R.SitTargetsPlayer,
            SeesProbe = Probe.HasValue && R.InCone(Probe.Value),
            Telegraphs = R.TelegraphCount,
            Loops = R.LoopsCompleted,
        };

        /// <summary>The number of dwell starts so far (a replayed dwell counts twice).</summary>
        public int DwellCount { get; private set; }

        /// <summary>The number of distinct visits dwelt so far (a replayed dwell counts once).</summary>
        public int VisitCount { get; private set; }

        private Vector2Int lastVisit = new Vector2Int(-1, -1);

        public void Step(int count = 1)
        {
            for (int i = 0; i < count; i++)
            {
                R.Step(M5.Dt);
                M5Rec r = Snap();
                if (r.InDwell && !Log[Log.Count - 1].InDwell)
                {
                    DwellCount++;
                    var v = new Vector2Int(r.Visit, r.Station);
                    if (v != lastVisit)
                    {
                        VisitCount++;
                        lastVisit = v;
                    }
                }
                Log.Add(r);
            }
        }

        public void StepUntil(Func<InhabitantRoutine, bool> done, int max, string what)
        {
            int guard = 0;
            while (!done(R))
            {
                Assert.Less(guard++, max, "never happened: " + what);
                Step();
            }
        }

        public List<M5Rec> Since(int index) => Log.GetRange(index, Log.Count - index);

        /// <summary>(visit, station) at every dwell start, in order (a replayed dwell appears twice).</summary>
        public List<Vector2Int> DwellStarts()
        {
            var starts = new List<Vector2Int>();
            for (int i = 1; i < Log.Count; i++)
            {
                if (Log[i].InDwell && !Log[i - 1].InDwell)
                {
                    starts.Add(new Vector2Int(Log[i].Visit, Log[i].Station));
                }
            }
            return starts;
        }

        /// <summary><see cref="DwellStarts"/> with consecutive repeats of a visit (a replayed dwell) kept once.</summary>
        public List<Vector2Int> Visits()
        {
            var visits = new List<Vector2Int>();
            foreach (Vector2Int v in DwellStarts())
            {
                if (visits.Count == 0 || visits[visits.Count - 1] != v)
                {
                    visits.Add(v);
                }
            }
            return visits;
        }
    }

    /// <summary>
    /// docs/CONTRACT_M5.md 3 and 16.12: the personality table. The default row must equal the M1 to M4 constants field by
    /// field (every public field of PersonalityDef is checked, so a new field cannot slip past the test).
    /// </summary>
    public sealed class CoreM5PersonalityTests
    {
        private static Dictionary<string, object> Row(string id, string name, string trait, string model, string tint, float walk, float range,
            float half, float eye, float hearing, float suspicion, float tolerance, float carry, bool memory, bool hears, bool catches,
            bool exits, bool sits, bool barks)
        {
            return new Dictionary<string, object>
            {
                { "Id", id }, { "NameKey", name }, { "TraitKey", trait }, { "Model", model }, { "Tint", tint },
                { "WalkSpeed", walk }, { "ViewRange", range }, { "HalfAngle", half }, { "EyeHeight", eye },
                { "HearingFactor", hearing }, { "SuspicionFactor", suspicion }, { "Tolerance", tolerance }, { "CarryFactor", carry },
                { "Memory", memory }, { "Hears", hears }, { "CountsForCatch", catches }, { "CountsForExit", exits },
                { "Sits", sits }, { "Barks", barks },
            };
        }

        /// <summary>The M1 to M4 inhabitant: Tuning's M1 and M2 constants, every role, no keys.</summary>
        private static Dictionary<string, object> DefaultRow() => Row("default", null, null, null, null, Tuning.WalkSpeed, Tuning.ViewRange,
            Tuning.ViewHalfAngle, Tuning.EyeHeight, 1f, 1f, Tuning.DisplacementTolerance, 1f, true, true, true, true, true, false);

        // The model and tint of each personality are the watchers' identity (CONTRACT_M5 16.12), pinned here as data.
        private static Dictionary<string, object> Human(string id, string model, string tint, float walk, float range, float half,
            float hearing, float suspicion, float tolerance, float carry) => Row(id, "person." + id, "person." + id + ".trait", model,
            tint, walk, range, half, 1.6f, hearing,
            suspicion, tolerance, carry, true, true, true, true, true, false);

        /// <summary>The first field that differs (exact float equality), or a field the row does not cover; null when equal.</summary>
        private static string FirstMismatch(PersonalityDef p, Dictionary<string, object> expected)
        {
            FieldInfo[] fields = typeof(PersonalityDef).GetFields(BindingFlags.Public | BindingFlags.Instance);
            if (fields.Length != expected.Count)
            {
                return $"PersonalityDef has {fields.Length} public fields, the row lists {expected.Count}";
            }
            foreach (FieldInfo f in fields)
            {
                if (!expected.TryGetValue(f.Name, out object want))
                {
                    return $"field {f.Name} is not covered by the row";
                }
                object got = f.GetValue(p);
                if (!Equals(want, got))
                {
                    return $"{p.Id}.{f.Name} is {Show(got)}, expected {Show(want)}";
                }
            }
            return null;
        }

        private static string Show(object o) => o is float f ? f.ToString("R") : o?.ToString() ?? "null";

        [Test]
        public void Default_row_equals_the_M1_to_M4_constants_field_by_field()
        {
            Dictionary<string, object> row = DefaultRow();
            Assert.IsNull(FirstMismatch(PersonalityDef.For(PersonalityDef.Default), row));
            // Premises: the M1 values, as the PRD gives them, and a comparison that catches a change in any field.
            Assert.AreEqual(1.2f, Tuning.WalkSpeed);
            Assert.AreEqual(10f, Tuning.ViewRange);
            Assert.AreEqual(55f, Tuning.ViewHalfAngle);
            Assert.AreEqual(1.6f, Tuning.EyeHeight);
            Assert.AreEqual(0.75f, Tuning.DisplacementTolerance);
            PersonalityDef changed = PersonalityDef.For(null);
            changed.ViewRange += 0.5f;
            StringAssert.Contains("ViewRange", FirstMismatch(changed, row));
            changed = PersonalityDef.For(null);
            changed.Tolerance = 0.4f;
            StringAssert.Contains("Tolerance", FirstMismatch(changed, row));
            changed = PersonalityDef.For(null);
            changed.Sits = false;
            StringAssert.Contains("Sits", FirstMismatch(changed, row));
            changed = PersonalityDef.For(null);
            changed.NameKey = "person.default";
            StringAssert.Contains("NameKey", FirstMismatch(changed, row));
        }

        [Test]
        public void Personality_table_matches_the_contract()
        {
            var rows = new[]
            {
                Human(PersonalityDef.Dreamer, "quaternius.man_shorts", "#6FA8DC", 0.9f, 8f, 45f, 0.7f, 0.7f, 0.75f, 1.0f),
                Human(PersonalityDef.Watchful, "quaternius.woman_jacket", "#2E8B7A", 1.2f, 10f, 60f, 1.0f, 1.5f, 0.5f, 1.0f),
                Human(PersonalityDef.Hurried, "quaternius.man_suit", "#3D5A80", 1.7f, 10f, 50f, 0.5f, 1.0f, 0.75f, 1.2f),
                Human(PersonalityDef.Granny, "quaternius.woman_dress", "#A88BC7", 0.8f, 7f, 55f, 0.6f, 1.0f, 0.75f, 0.8f),
                Human(PersonalityDef.Teen, "quaternius.man_tshirt", "#8DBF3F", 1.1f, 6f, 35f, 0.4f, 0.8f, 0.75f, 1.0f),
                Human(PersonalityDef.Tidy, "quaternius.woman", "#F4D35E", 1.2f, 10f, 55f, 1.0f, 1.3f, 0.4f, 1.3f),
                Row(PersonalityDef.Dog, "person.dog", "person.dog.trait", "quaternius.shiba", "#4F6670", 1.4f, 6f, 70f, 0.35f, 0f, 0f, 0.75f, 0f,
                    false, false, false, false, false, true),
            };
            foreach (Dictionary<string, object> row in rows)
            {
                string id = (string)row["Id"];
                Assert.IsNull(FirstMismatch(PersonalityDef.For(id), row), id);
            }
            Assert.AreEqual(Tuning.DogEyeHeight, PersonalityDef.For(PersonalityDef.Dog).EyeHeight, "the dog's eye is Tuning.DogEyeHeight");
            Assert.AreEqual(rows.Length + 1, PersonalityDef.All.Length, "every row is listed in All, default included");
            foreach (string id in PersonalityDef.All)
            {
                Assert.AreEqual(id, PersonalityDef.For(id).Id, id + " does not give its own row");
            }
        }

        [Test]
        public void For_null_or_unknown_is_default_and_a_new_instance_on_every_call()
        {
            Dictionary<string, object> row = DefaultRow();
            foreach (string id in new[] { null, "", "Dreamer", "robot", "default", "human" })
            {
                PersonalityDef a = PersonalityDef.For(id);
                PersonalityDef b = PersonalityDef.For(id);
                Assert.AreNotSame(a, b, $"'{id}': the same instance twice");
                Assert.IsNull(FirstMismatch(a, row), $"'{id}' is not the default row");
            }
            PersonalityDef mine = PersonalityDef.For(null);
            mine.WalkSpeed = 99f;
            Assert.IsNull(FirstMismatch(PersonalityDef.For(null), row), "a caller's change leaked into the next instance");
            PersonalityDef teen = PersonalityDef.For(PersonalityDef.Teen);
            teen.ViewRange = 10f;
            Assert.AreEqual(6f, PersonalityDef.For(PersonalityDef.Teen).ViewRange, "a caller's change leaked into the next teen");
        }

        [Test]
        public void ForInhabitant_a_dog_kind_wins_and_an_explicit_model_or_body_colour_wins()
        {
            Assert.AreEqual(PersonalityDef.Default, PersonalityDef.ForInhabitant(null).Id);
            Assert.AreEqual(PersonalityDef.Teen, PersonalityDef.ForInhabitant(new InhabitantDef { Personality = "teen" }).Id);
            Assert.AreEqual(PersonalityDef.Default, PersonalityDef.ForInhabitant(new InhabitantDef { Kind = "human" }).Id);
            Assert.AreEqual(PersonalityDef.Dog, PersonalityDef.ForInhabitant(new InhabitantDef { Kind = "dog", Personality = "teen" }).Id,
                "a dog kind must win over its personality");
            PersonalityDef dog = PersonalityDef.ForInhabitant(new InhabitantDef { Kind = "dog" });
            Assert.AreEqual(Tuning.DogEyeHeight, dog.EyeHeight);
            Assert.AreEqual("quaternius.shiba", dog.Model);

            PersonalityDef dressed = PersonalityDef.ForInhabitant(new InhabitantDef
            {
                Personality = "granny", Model = "quaternius.woman", BodyColor = "#123456",
            });
            Assert.AreEqual(PersonalityDef.Granny, dressed.Id);
            Assert.AreEqual("quaternius.woman", dressed.Model, "an explicit model must win");
            Assert.AreEqual("#123456", dressed.Tint, "an explicit body colour must win over the tint");
            Assert.AreEqual(0.8f, dressed.WalkSpeed, "the row values stay the personality's");
            Assert.AreEqual("quaternius.woman_dress", PersonalityDef.For(PersonalityDef.Granny).Model, "premise: the row has its own model");
            Assert.AreEqual("quaternius.man", PersonalityDef.ForInhabitant(new InhabitantDef { Kind = "dog", Model = "quaternius.man" }).Model);
            Assert.AreEqual("quaternius.shiba", PersonalityDef.ForInhabitant(new InhabitantDef { Kind = "dog", Model = "" }).Model,
                "an empty model is not explicit");
        }

        [Test]
        public void Every_name_and_trait_key_is_a_shown_string()
        {
            int keys = 0;
            foreach (string id in PersonalityDef.All)
            {
                PersonalityDef p = PersonalityDef.For(id);
                if (id == PersonalityDef.Default)
                {
                    Assert.IsNull(p.NameKey, "default has no name on the intro card");
                    Assert.IsNull(p.TraitKey);
                    continue;
                }
                Assert.AreEqual("person." + id, p.NameKey);
                Assert.AreEqual("person." + id + ".trait", p.TraitKey);
                foreach (string key in new[] { p.NameKey, p.TraitKey })
                {
                    string text = Strings.Get(key);
                    Assert.IsFalse(string.IsNullOrEmpty(text), key);
                    Assert.AreNotEqual(key, text, key + " is not in Strings");
                    keys++;
                }
            }
            Assert.AreEqual(14, keys, "premise: 7 named personalities, 2 keys each");
        }
    }

    /// <summary>docs/CONTRACT_M5.md 3 and 16.7: loop, pingpong and wander, indexed by visit.</summary>
    public sealed class CoreM5PatternTests
    {
        // From the contract LCG, x = (1103515245 x + 12345) and 0x7FFFFFFF, advanced before each draw (computed apart).
        private static readonly int[] Wander12345 = { 0, 1, 2, 1, 0, 2, 1, 2, 3, 1, 0, 2, 1, 3, 0, 1, 2, 1, 3, 0 };
        private static readonly int[] Wander7 = { 0, 2, 3, 2, 0, 3, 2, 0, 3, 2, 3, 2, 1, 3, 2, 3, 1, 2, 3, 1 };
        private static readonly int[] Wander0 = { 0, 1, 0, 2, 1, 0, 2, 1, 2, 3, 1, 0, 2, 1, 3, 0, 1, 2, 1, 3 };
        private static readonly int[] WanderMaxFive = { 2, 1, 2, 3, 2, 1, 3, 0, 4, 0, 3, 1, 2, 4, 0, 2, 3, 4, 2, 4 };
        private static readonly int[] PingPong0 = { 0, 1, 2, 3, 2, 1, 0, 1, 2, 3, 2, 1, 0, 1, 2, 3, 2, 1, 0, 1 };
        private static readonly int[] Loop1 = { 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3, 0 };

        private static int[] Draw(string pattern, int n, int start, int seed, int visits)
        {
            var order = new StationOrder(pattern, n, start, seed);
            var result = new int[visits];
            for (int k = 0; k < visits; k++)
            {
                result[k] = order.StationOf(k);
            }
            return result;
        }

        [Test]
        public void WanderNext_is_the_contract_generator_and_never_stays()
        {
            int x = 12345;
            Assert.AreEqual(1, RoutinePatterns.WanderNext(ref x, 0, 4));
            Assert.AreEqual(1406932606, x, "the generator must advance before the draw");
            Assert.AreEqual(2, RoutinePatterns.WanderNext(ref x, 1, 4));
            Assert.AreEqual(654583775, x);
            Assert.AreEqual(1, RoutinePatterns.WanderNext(ref x, 2, 4));
            Assert.AreEqual(1449466924, x);
            x = int.MaxValue;
            RoutinePatterns.WanderNext(ref x, 0, 5);
            Assert.AreEqual(1043980748, x, "the largest seed must not overflow");

            // Never the current station, always in range, and every other station reachable.
            for (int n = 3; n <= 6; n++)
            {
                var hits = new int[n, n];
                int state = 99;
                int current = 0;
                for (int i = 0; i < 4000; i++)
                {
                    int next = RoutinePatterns.WanderNext(ref state, current, n);
                    Assert.That(next, Is.InRange(0, n - 1));
                    Assert.AreNotEqual(current, next, $"n {n}: stayed on {current}");
                    Assert.GreaterOrEqual(state, 0, "x must stay in [0, 2^31 - 1]");
                    hits[current, next]++;
                    current = next;
                }
                for (int a = 0; a < n; a++)
                {
                    for (int b = 0; b < n; b++)
                    {
                        if (a != b)
                        {
                            Assert.Greater(hits[a, b], 0, $"n {n}: {a} to {b} never drawn");
                        }
                    }
                }
            }
        }

        [Test]
        public void StationOrder_draws_each_pattern_in_the_contract_order()
        {
            CollectionAssert.AreEqual(Loop1, Draw(RoutinePatterns.Loop, 4, 1, 0, 20), "loop");
            CollectionAssert.AreEqual(Loop1, Draw(null, 4, 1, 0, 20), "null is a loop");
            CollectionAssert.AreEqual(Loop1, Draw("zigzag", 4, 1, 0, 20), "unknown is a loop");
            CollectionAssert.AreEqual(PingPong0, Draw(RoutinePatterns.PingPong, 4, 0, 0, 20), "pingpong from 0");
            CollectionAssert.AreEqual(new[] { 3, 2, 1, 0, 1, 2, 3, 2, 1 }, Draw(RoutinePatterns.PingPong, 4, 3, 0, 9), "pingpong from the last");
            CollectionAssert.AreEqual(new[] { 2, 3, 2, 1, 0, 1, 2, 3 }, Draw(RoutinePatterns.PingPong, 4, 2, 0, 8), "pingpong from the middle");
            CollectionAssert.AreEqual(new[] { 0, 1, 0, 1, 0 }, Draw(RoutinePatterns.PingPong, 2, 0, 0, 5), "pingpong of two");
            CollectionAssert.AreEqual(Wander12345, Draw(RoutinePatterns.Wander, 4, 0, 12345, 20), "wander 12345");
            CollectionAssert.AreEqual(Wander7, Draw(RoutinePatterns.Wander, 4, 0, 7, 20), "wander 7");
            CollectionAssert.AreEqual(Wander0, Draw(RoutinePatterns.Wander, 4, 0, 0, 20), "wander 0");
            CollectionAssert.AreEqual(WanderMaxFive, Draw(RoutinePatterns.Wander, 5, 2, int.MaxValue, 20), "wander, the largest seed");
            CollectionAssert.AreNotEqual(Wander12345, Wander0, "premise: the seed matters");
            CollectionAssert.AreEqual(new[] { 0, 0, 0 }, Draw(RoutinePatterns.Wander, 1, 0, 5, 3), "one station");

            // Asked out of order, or twice, a visit is the same station: draws are indexed by visit.
            var order = new StationOrder(RoutinePatterns.Wander, 4, 0, 12345);
            Assert.AreEqual(Wander12345[15], order.StationOf(15));
            Assert.AreEqual(Wander12345[3], order.StationOf(3));
            Assert.AreEqual(Wander12345[15], order.StationOf(15));
            Assert.AreEqual(Wander12345[19], order.StationOf(19));
            Assert.AreEqual(Wander12345[0], order.StationOf(-1), "a negative visit reads as the start");
        }

        [Test]
        public void ReachablePairs_cover_every_walk_each_pattern_can_produce()
        {
            Assert.AreEqual(4, RoutinePatterns.ReachablePairs(RoutinePatterns.Loop, 4).Count, "n for a loop");
            Assert.AreEqual(6, RoutinePatterns.ReachablePairs(RoutinePatterns.PingPong, 4).Count, "2 (n - 1) for pingpong");
            Assert.AreEqual(12, RoutinePatterns.ReachablePairs(RoutinePatterns.Wander, 4).Count, "n (n - 1) for wander");
            Assert.AreEqual(20, RoutinePatterns.ReachablePairs(RoutinePatterns.Wander, 5).Count);
            Assert.AreEqual(0, RoutinePatterns.ReachablePairs(RoutinePatterns.Loop, 0).Count);
            foreach (string pattern in RoutinePatterns.All)
            {
                foreach (int n in new[] { 3, 4, 5 })
                {
                    var pairs = new HashSet<Vector2Int>(RoutinePatterns.ReachablePairs(pattern, n));
                    var produced = new HashSet<Vector2Int>();
                    for (int start = 0; start < n; start++)
                    {
                        var order = new StationOrder(pattern, n, start, 31 * start + 5);
                        for (int k = 0; k < 300; k++)
                        {
                            var pair = new Vector2Int(order.StationOf(k), order.StationOf(k + 1));
                            Assert.IsTrue(pairs.Contains(pair), $"{pattern} n {n} start {start}: the walk {pair} is not a reachable pair");
                            produced.Add(pair);
                        }
                    }
                    Assert.AreEqual(pairs.Count, produced.Count, $"{pattern} n {n}: a listed pair is never produced");
                }
            }
        }

        private static int[] Expected(string pattern, out int start, out int seed)
        {
            switch (pattern)
            {
                case RoutinePatterns.PingPong:
                    start = 0;
                    seed = 0;
                    return PingPong0;
                case RoutinePatterns.Wander:
                    start = 0;
                    seed = 12345;
                    return Wander12345;
                default:
                    start = 1;
                    seed = 0;
                    return Loop1;
            }
        }

        [TestCase(RoutinePatterns.Loop)]
        [TestCase(RoutinePatterns.PingPong)]
        [TestCase(RoutinePatterns.Wander)]
        public void Routine_visits_follow_the_pattern_over_20_visits(string pattern)
        {
            int[] expected = Expected(pattern, out int start, out int seed);
            InhabitantRoutine r = RoutineFactory.Create(M5.Def(M5.Square(0.2f), start, pattern: pattern, seed: seed), null,
                StraightPlanner.Instance);
            Assert.AreEqual(pattern, r.Pattern);
            Assert.AreEqual(seed, r.Seed);
            Assert.AreEqual(0, r.VisitIndex, "visit 0 is the start station");
            var rec = new M5Recorder(r);
            rec.StepUntil(x => rec.DwellCount >= 20 && !x.InDwell, 40000, "20 visits");
            List<Vector2Int> dwells = rec.DwellStarts();
            for (int k = 0; k < 20; k++)
            {
                Assert.AreEqual(new Vector2Int(k, expected[k]), dwells[k], $"{pattern}: visit {k} (visit, station)");
                Assert.AreEqual(expected[k], r.StationOfVisit(k));
            }
            // The visit index only ever moves up by one, when the walk to the next station starts.
            for (int i = 1; i < rec.Log.Count; i++)
            {
                int d = rec.Log[i].Visit - rec.Log[i - 1].Visit;
                Assert.That(d, Is.InRange(0, 1), $"the visit index jumped by {d} at record {i}");
                if (d == 1)
                {
                    Assert.IsFalse(rec.Log[i].InDwell, $"the visit index moved inside a dwell at record {i}");
                }
            }
            Assert.Greater(M5.AssertTelegraphs(rec.Log, pattern), 20, "premise: the square has large turns");
        }

        [TestCase(RoutinePatterns.PingPong)]
        [TestCase(RoutinePatterns.Wander)]
        public void Interruptions_never_advance_the_visit_and_the_resume_reuses_its_station(string pattern)
        {
            int[] expected = Expected(pattern, out int start, out int seed);
            List<StationDef> stations = M5.Square(0.2f);
            InhabitantRoutine r = RoutineFactory.Create(M5.Def(stations, start, pattern: pattern, seed: seed), null, StraightPlanner.Instance);
            var rec = new M5Recorder(r);

            // 1. An alert, then an investigation, during the walk to visit 4 (pingpong: the walk back from 3 to 2).
            rec.StepUntil(x => x.VisitIndex == 4 && x.LastActivity == RoutineActivity.Walking, 20000, "the walk to visit 4");
            rec.Step(10);
            Assert.IsTrue(r.LastActivity == RoutineActivity.Walking && !r.InDwell, "premise: walking to visit 4");
            int interrupted = rec.Index;
            r.Alert(r.Position + YawMath.Forward(r.EyeYaw + 120f) * 2f, NoiseKind.Hop);
            Assert.AreEqual(InhabitantMode.Alerted, r.Mode, "premise: alerted");
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 1000, "the end of the alert");
            rec.Step(5);
            r.Investigate(r.Position + new Vector3(-3f, 0f, 2.5f));
            Assert.AreEqual(InhabitantMode.Investigating, r.Mode, "premise: investigating");
            rec.StepUntil(x => x.ReachedTarget, 3000, "the investigation target");
            Assert.Greater((r.Position - stations[expected[4]].Position).magnitude, 1f, "premise: it walked away");
            r.CancelInvestigation();
            rec.StepUntil(x => x.InDwell, 3000, "the resumed dwell");
            Assert.IsTrue(rec.Since(interrupted).TrueForAll(x => x.Visit == 4), "an interruption moved the visit index");
            Assert.AreEqual(expected[4], r.StationIndex, "the resume did not go back to the station drawn for visit 4");
            Assert.AreEqual(4, r.VisitIndex);
            Assert.Less((r.Position - stations[expected[4]].Position).magnitude, 1e-4f);

            // 2. An investigation and a carry from the dwell of visit 9: the dwell of visit 9 is replayed in full.
            rec.StepUntil(x => x.VisitIndex == 9 && x.InDwell, 20000, "the dwell of visit 9");
            int dwell9 = rec.Index;
            r.Investigate(r.Position + new Vector3(1.5f, 0f, 0f));
            rec.StepUntil(x => x.ReachedTarget, 3000, "the second target");
            r.BeginCarry(new FurniturePose(r.Position + new Vector3(0f, 0f, -2f), 0f));
            Assert.AreEqual(InhabitantMode.Carrying, r.Mode, "premise: carrying");
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 5000, "the end of the carry");
            rec.StepUntil(x => x.InDwell, 3000, "the replayed dwell");
            Assert.IsTrue(rec.Since(dwell9).TrueForAll(x => x.Visit == 9), "the carry moved the visit index");
            Assert.AreEqual(expected[9], r.StationIndex, "the replayed dwell is not visit 9's station");

            // 3. The order goes on exactly as without the interruptions.
            rec.StepUntil(x => rec.VisitCount >= 20 && !x.InDwell, 40000, "20 visits");
            List<Vector2Int> visits = rec.Visits();
            for (int k = 0; k < 20; k++)
            {
                Assert.AreEqual(new Vector2Int(k, expected[k]), visits[k], $"{pattern}: visit {k} after the interruptions");
            }
            List<Vector2Int> starts = rec.DwellStarts();
            Assert.AreEqual(2, starts.FindAll(v => v.x == 9).Count, "premise: the dwell of visit 9 was replayed once");
            M5.AssertTelegraphs(rec.Log, pattern + " interrupted");
        }

        /// <summary>Steps a wander routine with the same scripted interruptions at the same steps.</summary>
        private static List<M5Rec> ScriptedRun(int seed, int steps)
        {
            InhabitantRoutine r = RoutineFactory.Create(M5.Def(M5.Square(0.3f), 0, pattern: RoutinePatterns.Wander, seed: seed), null,
                new M5.LPlanner());
            var rec = new M5Recorder(r);
            bool investigating = false;
            for (int i = 0; i < steps; i++)
            {
                if (i == 700)
                {
                    r.Alert(r.Position + new Vector3(1f, 0f, 1.5f), NoiseKind.Creak);
                }
                if (i == 1500 && r.Mode == InhabitantMode.Routine)
                {
                    r.Investigate(new Vector3(-1f, 0f, 3f));
                    investigating = true;
                }
                if (investigating && r.ReachedTarget)
                {
                    r.CancelInvestigation();
                    investigating = false;
                }
                rec.Step();
            }
            return rec.Log;
        }

        [Test]
        public void Two_runs_of_the_same_wander_are_identical_step_for_step_and_another_seed_differs()
        {
            const int steps = 6000;
            List<M5Rec> a = ScriptedRun(7, steps);
            List<M5Rec> b = ScriptedRun(7, steps);
            List<M5Rec> other = ScriptedRun(8, steps);
            Assert.AreEqual(a.Count, b.Count);
            int firstDifference = -1;
            for (int i = 0; i < a.Count; i++)
            {
                string at = "step " + i;
                Assert.AreEqual(a[i].Pos, b[i].Pos, at);
                Assert.AreEqual(a[i].Body, b[i].Body, at);
                Assert.AreEqual(a[i].Head, b[i].Head, at);
                Assert.AreEqual(a[i].Act, b[i].Act, at);
                Assert.AreEqual(a[i].Station, b[i].Station, at);
                Assert.AreEqual(a[i].Visit, b[i].Visit, at);
                Assert.AreEqual(a[i].Telegraphs, b[i].Telegraphs, at);
                if (firstDifference < 0 && a[i].Pos != other[i].Pos)
                {
                    firstDifference = i;
                }
            }
            Assert.Greater(a[a.Count - 1].Visit, 15, "premise: the runs cover more than 15 visits");
            Assert.IsTrue(a.Exists(x => x.Mode == InhabitantMode.Alerted) && a.Exists(x => x.Mode == InhabitantMode.Investigating),
                "premise: the script interrupted the runs");
            Assert.GreaterOrEqual(firstDifference, 0, "the seed changed nothing: wander ignores its seed");
        }
    }

    /// <summary>
    /// docs/CONTRACT_M5.md 3 and 16, CONTRACT_M5_v3 15.1 and 15.4 to 15.6: the personality in the routine, the dog's sleep,
    /// hearing, memory and suspicion per personality, the two planners, the floor, the seat registry, the factory and the
    /// fairness invariant. Every scenario asserts its premise, so it cannot pass on nothing.
    /// </summary>
    public sealed class CoreM5RoutineTests
    {
        private const float Dt = M5.Dt;

        // ----- Personality in the routine -----

        /// <summary>
        /// The M1 walk snaps onto its target once within 1e-4 m (sqrMagnitude below 1e-8), so the last step of a walk may be
        /// up to that much longer than speed times dt.
        /// </summary>
        private const float ArrivalSnap = 1e-4f + 1e-5f;

        [Test]
        public void Walk_and_carry_speeds_follow_the_personality()
        {
            var carried = new Dictionary<string, float>();
            foreach (string id in PersonalityDef.All)
            {
                PersonalityDef p = PersonalityDef.For(id);
                var stations = new List<StationDef> { M5.Plain(0f, 0f, 90f, 0.5f), M5.Plain(6f, 0f, 90f, 1f) };
                InhabitantRoutine r = RoutineFactory.Create(M5.DefOf(id, stations), null, StraightPlanner.Instance);
                Assert.AreEqual(id, r.Personality.Id, "premise: the factory gave the personality");
                var rec = new M5Recorder(r);
                rec.StepUntil(x => x.LastActivity == RoutineActivity.Walking, 2000, id + ": the first walk");
                int from = rec.Index;
                rec.StepUntil(x => x.LastActivity != RoutineActivity.Walking, 2000, id + ": the end of the walk");
                int full = 0;
                for (int i = from; i < rec.Index; i++)
                {
                    float step = (rec.Log[i].Pos - rec.Log[i - 1].Pos).magnitude;
                    Assert.LessOrEqual(step, p.WalkSpeed * Dt + ArrivalSnap, id + ": faster than its walk speed");
                    full += Mathf.Abs(step - p.WalkSpeed * Dt) < 1e-5f ? 1 : 0;
                }
                Assert.Greater(full, 100, id + ": did not walk at its own speed");

                if (!p.Memory)
                {
                    r.Investigate(r.Position + Vector3.right);
                    Assert.AreEqual(InhabitantMode.Routine, r.Mode, id + ": a personality without memory investigated");
                    continue;
                }
                r.Investigate(r.Position + Vector3.right * 0.5f);
                rec.StepUntil(x => x.ReachedTarget, 500, id + ": the investigation");
                r.BeginCarry(new FurniturePose(r.Position + new Vector3(-4f, 0f, 0f), 0f));
                Assert.IsTrue(r.IsCarrying, id + ": premise: carrying");
                int carry = rec.Index;
                rec.StepUntil(x => x.JustPutDown, 5000, id + ": the put down");
                float speed = Tuning.CarrySpeed * p.CarryFactor;
                int carriedSteps = 0;
                for (int i = carry + 1; i <= rec.Index; i++)
                {
                    if (rec.Log[i].Act != RoutineActivity.Carrying)
                    {
                        continue;
                    }
                    float step = (rec.Log[i].Pos - rec.Log[i - 1].Pos).magnitude;
                    Assert.LessOrEqual(step, speed * Dt + ArrivalSnap, id + ": carried faster than its carry speed");
                    carriedSteps += Mathf.Abs(step - speed * Dt) < 1e-5f ? 1 : 0;
                }
                Assert.Greater(carriedSteps, 50, id + ": did not carry at CarrySpeed times its carry factor");
                carried[id] = speed;
            }
            Assert.AreEqual(7, carried.Count, "premise: every human carried");
            Assert.Greater(carried[PersonalityDef.Tidy], carried[PersonalityDef.Granny] + 0.4f, "premise: carry factors differ");
        }

        /// <summary>A personality whose eye is not the default one, to see every reset use it.</summary>
        private static PersonalityDef TallEye()
        {
            PersonalityDef p = PersonalityDef.For(null);
            p.EyeHeight = 1.5f;
            return p;
        }

        [Test]
        public void Eye_height_follows_the_personality_through_every_reset()
        {
            // The dog: 0.35 m from the start, and after a pin and a startle.
            InhabitantRoutine dog = RoutineFactory.Create(M5.DefOf(PersonalityDef.Dog, M5.SofaLoop()), null, StraightPlanner.Instance);
            Assert.AreEqual(Tuning.DogEyeHeight, dog.EyeHeight, "the dog's eye before the first step");
            Assert.AreEqual(Tuning.DogEyeHeight, dog.EyePosition.y, 1e-6f);
            for (int i = 0; i < 300; i++)
            {
                dog.Step(Dt);
                Assert.AreEqual(Tuning.DogEyeHeight, dog.EyeHeight, $"the dog's eye moved at step {i}");
            }
            dog.Pin(dog.Position, dog.BodyYaw, 0f, true);
            Assert.AreEqual(Tuning.DogEyeHeight, dog.EyeHeight, "Pin reset the dog's eye to a human one");
            dog.Startle(Vector3.zero);
            Assert.AreEqual(Tuning.DogEyeHeight, dog.EyeHeight, "Startle reset the dog's eye to a human one");
            Assert.AreEqual(Tuning.EyeHeight, RoutineFactory.Create(M5.DefOf(PersonalityDef.Default, M5.SofaLoop()), null, null).EyeHeight,
                "premise: a human's eye is 1.6 m");

            // A 1.5 m eye sits down from 1.5 m, stands back up to 1.5 m, and every reset goes back to 1.5 m.
            foreach (int reset in new[] { 0, 1, 2 })
            {
                var r = new InhabitantRoutine(M5.SofaLoop(), 0) { Personality = TallEye() };
                Assert.AreEqual(1.5f, r.EyeHeight, "setting the personality sets the standing eye");
                var rec = new M5Recorder(r);
                rec.StepUntil(x => x.JustSat, 3000, "the moment of sitting");
                int sat = rec.Index;
                rec.Step(M5.SitSteps);
                for (int k = 0; k < M5.SitSteps; k++)
                {
                    float t = (k + 1f) / M5.SitSteps;
                    Assert.AreEqual(Mathf.Lerp(1.5f, Tuning.SitEyeHeight, t), rec.Log[sat + k].Eye, 1e-4f, $"the sit down eye at step {k}");
                }
                Assert.AreEqual(Tuning.SitEyeHeight, r.EyeHeight, "premise: seated");
                if (reset == 0)
                {
                    rec.StepUntil(x => !x.IsLowered, 2000, "the stand up");
                    Assert.AreEqual(1.5f, r.EyeHeight, "the stand up rose to 1.6 m instead of the personality's eye");
                }
                else if (reset == 1)
                {
                    r.Pin(r.Position, r.BodyYaw, 0f);
                    Assert.AreEqual(1.5f, r.EyeHeight, "Pin reset the eye to 1.6 m");
                }
                else
                {
                    r.Startle(Vector3.zero);
                    Assert.AreEqual(1.5f, r.EyeHeight, "Startle reset the eye to 1.6 m");
                }
                Assert.IsFalse(r.IsLowered);
            }
        }

        [Test]
        public void The_dog_never_sits_never_hears_never_investigates()
        {
            foreach (bool player in new[] { false, true })
            {
                List<StationDef> stations = player ? M5.PlayerLoop() : M5.SofaLoop();
                InhabitantRoutine dog = RoutineFactory.Create(M5.DefOf(PersonalityDef.Dog, stations), null, StraightPlanner.Instance);
                InhabitantRoutine human = RoutineFactory.Create(M5.DefOf(PersonalityDef.Granny, player ? M5.PlayerLoop() : M5.SofaLoop()), null,
                    StraightPlanner.Instance);
                bool humanSat = false;
                bool humanTargets = false;
                for (int i = 0; i < 3000; i++)
                {
                    dog.Step(Dt);
                    human.Step(Dt);
                    Assert.IsFalse(dog.JustSat || dog.IsSitting || dog.IsLowered || dog.SitTargetsPlayer, $"the dog sat (step {i})");
                    Assert.AreEqual(Tuning.DogEyeHeight, dog.EyeHeight);
                    humanSat |= human.JustSat;
                    humanTargets |= human.SitTargetsPlayer;
                }
                Assert.IsTrue(humanSat, "premise: a human sits on the same loop");
                Assert.AreEqual(player, humanTargets, "premise: a human targets the player seat");
                Assert.Greater(dog.LoopsCompleted, 0, "premise: the dog went round its loop");
            }

            var d = RoutineFactory.Create(M5.DefOf(PersonalityDef.Dog, M5.SofaLoop()), null, StraightPlanner.Instance);
            d.Step(Dt);
            foreach (NoiseKind k in Enum.GetValues(typeof(NoiseKind)))
            {
                d.Alert(d.Position + Vector3.right * 2f, k);
                Assert.AreEqual(InhabitantMode.Routine, d.Mode, $"the dog heard a {k}");
            }
            d.Investigate(d.Position + Vector3.right * 2f);
            Assert.AreEqual(InhabitantMode.Routine, d.Mode, "the dog investigated");
            d.BeginSwitchOn(d.Position + Vector3.right * 2f);
            Assert.AreEqual(InhabitantMode.Routine, d.Mode, "the dog switched a lamp on");
            Assert.AreEqual(0f, d.HearingFactor);
            var h = RoutineFactory.Create(M5.DefOf(PersonalityDef.Default, M5.SofaLoop()), null, StraightPlanner.Instance);
            h.Step(Dt);
            h.Alert(h.Position + Vector3.right * 2f, NoiseKind.Hop);
            Assert.AreEqual(InhabitantMode.Alerted, h.Mode, "premise: a human hears");
        }

        [Test]
        public void Each_personality_sees_with_its_own_range_and_angle_through_the_routine()
        {
            foreach (string id in PersonalityDef.All)
            {
                PersonalityDef p = PersonalityDef.For(id);
                var stations = new List<StationDef> { M5.Plain(0f, 0f, 0f, 100f) };
                InhabitantRoutine r = RoutineFactory.Create(M5.DefOf(id, stations), null, StraightPlanner.Instance);
                Assert.AreEqual(p.ViewRange, r.ViewRange, id);
                Assert.AreEqual(p.HalfAngle, r.HalfAngle, id);
                Vector3 eye = r.EyePosition;
                Assert.IsTrue(r.InCone(eye + Vector3.forward * (p.ViewRange - 0.1f)), id + ": just inside its range");
                Assert.IsFalse(r.InCone(eye + Vector3.forward * (p.ViewRange + 0.1f)), id + ": just beyond its range");
                Assert.IsTrue(r.InCone(eye + YawMath.Forward(p.HalfAngle - 2f) * 3f), id + ": just inside its half angle");
                Assert.IsFalse(r.InCone(eye + YawMath.Forward(p.HalfAngle + 2f) * 3f), id + ": just outside its half angle");
                Assert.IsFalse(r.InCone(eye + Vector3.forward * (p.ViewRange * Tuning.LampOffLight + 0.1f), Tuning.LampOffLight),
                    id + ": the lamp factor must scale its range");
            }
            // CONTRACT_M5 12, "a personality's range is ignored": the teen sees 6 m, not 10.
            InhabitantRoutine teen = RoutineFactory.Create(M5.DefOf(PersonalityDef.Teen, new List<StationDef> { M5.Plain(0f, 0f, 0f, 9f) }),
                null, StraightPlanner.Instance);
            InhabitantRoutine man = RoutineFactory.Create(M5.DefOf(PersonalityDef.Default, new List<StationDef> { M5.Plain(0f, 0f, 0f, 9f) }),
                null, StraightPlanner.Instance);
            Vector3 sevenAhead = teen.EyePosition + Vector3.forward * 7f;
            Assert.IsTrue(man.InCone(sevenAhead), "premise: the default inhabitant sees 7 m ahead");
            Assert.IsFalse(teen.InCone(sevenAhead), "the teen saw 7 m ahead: its range is ignored");
            Assert.AreEqual(6f, teen.ViewRange);
        }

        // ----- The dog's sleep (CONTRACT_M5_v3 4 and 15.5) -----

        [Test]
        public void Sleep_station_closes_the_eye_for_the_dwell_and_the_wake_telegraph()
        {
            StationDef bed = M5.Plain(0f, 0f, 0f, 2f);
            bed.Sleep = true;
            var stations = new List<StationDef> { bed, M5.Plain(3f, 0f, 90f, 1f) };
            InhabitantRoutine r = RoutineFactory.Create(M5.DefOf(PersonalityDef.Dog, stations), null, StraightPlanner.Instance);
            Vector3 ahead = r.EyePosition + Vector3.forward * 2f;
            var rec = new M5Recorder(r, ahead);
            Assert.IsTrue(r.Asleep, "a level that starts in a sleep dwell starts asleep");
            Assert.IsFalse(rec.Last.SeesProbe, "asleep, it saw");

            rec.StepUntil(x => !x.Asleep, 1000, "the eye opening");
            int w = rec.Index;
            int dwellSteps = Mathf.RoundToInt(bed.Dwell / Dt);
            Assert.AreEqual(dwellSteps + M5.WakeSteps, w - 1, "asleep for the dwell and the wake telegraph, exactly");
            for (int i = 0; i < w; i++)
            {
                Assert.IsTrue(rec.Log[i].Asleep, $"the eye opened at record {i}");
                Assert.IsFalse(rec.Log[i].SeesProbe, $"asleep, it saw at record {i}");
            }
            Assert.AreEqual(M5.WakeSteps, M5.CountBefore(rec.Log, w, RoutineActivity.Telegraph),
                "the dwell must end with the wake telegraph, eye closed: no wake telegraph");
            Assert.AreEqual(RoutineActivity.Waiting, rec.Log[w - M5.WakeSteps - 1].Act, "premise: the dwell waits before the wake");
            Assert.AreEqual(rec.Log[w - M5.WakeSteps - 1].Telegraphs + 1, rec.Log[w - M5.WakeSteps].Telegraphs, "the wake beat is a telegraph");
            for (int i = 1; i < w - M5.WakeSteps; i++)
            {
                Assert.AreEqual(RoutineActivity.Waiting, rec.Log[i].Act, $"the sleep is not a still dwell at record {i}");
            }

            // Then the departure, with its own telegraph (90 deg), eye open.
            Assert.AreEqual(0f, rec.Log[w].Body, 1e-4f, "premise: still facing the bed's facing when the eye opens");
            Assert.IsTrue(rec.Log[w].SeesProbe, "awake and facing the probe, it must see it");
            rec.Step(M5.TelegraphSteps + 1);
            Assert.AreEqual(M5.TelegraphSteps, M5.CountLeading(rec.Log, w, RoutineActivity.Telegraph), "the departure turn's own telegraph");
            Assert.AreEqual(RoutineActivity.TurningBody, r.LastActivity, "the departure turn follows its telegraph");

            // The next visit to the bed closes the eye again.
            rec.StepUntil(x => x.LoopsCompleted >= 1, 5000, "back at the bed");
            Assert.IsTrue(r.Asleep, "asleep again at the bed");
            rec.StepUntil(x => !x.Asleep, 1000, "the second waking");
            Assert.AreEqual(M5.WakeSteps, M5.CountBefore(rec.Log, rec.Index, RoutineActivity.Telegraph), "the second wake telegraph");
            M5.AssertTelegraphs(rec.Log, "sleep");

            // A pin wakes a sleeper at once.
            InhabitantRoutine pinned = RoutineFactory.Create(M5.DefOf(PersonalityDef.Dog, stations), null, StraightPlanner.Instance);
            pinned.Step(Dt);
            Assert.IsTrue(pinned.Asleep, "premise: asleep");
            pinned.Pin(pinned.Position, 0f, 0f);
            Assert.IsFalse(pinned.Asleep, "a pinned dog stayed asleep");
        }

        // ----- Hearing (CONTRACT_M5 3, v3 15.5) -----

        [Test]
        public void Hears_with_a_factor_scales_the_radius_and_zero_hears_nothing()
        {
            var hop = new NoiseEvent(Vector3.zero, Hearing.RadiusOf(NoiseKind.Hop), NoiseKind.Hop);
            var creak = new NoiseEvent(Vector3.zero, Hearing.RadiusOf(NoiseKind.Creak), NoiseKind.Creak);
            for (float d = 0f; d <= 8f; d += 0.05f)
            {
                var at = new Vector3(d, 1.6f, 0f);
                Assert.AreEqual(Hearing.Hears(at, hop), Hearing.Hears(at, hop, 1f), $"factor 1 is not the M2 rule at {d} m");
                Assert.AreEqual(Hearing.Hears(at, creak), Hearing.Hears(at, creak, 1f), $"factor 1 is not the M2 rule at {d} m");
            }
            Assert.IsTrue(Hearing.Hears(new Vector3(0.99f, 0f, 0f), hop, 0.5f), "the hurried hears a hop at 0.99 m");
            Assert.IsFalse(Hearing.Hears(new Vector3(1.01f, 0f, 0f), hop, 0.5f), "the hurried hears a hop at 1.01 m");
            Assert.IsTrue(Hearing.Hears(new Vector3(2.79f, 0f, 0f), creak, 0.4f), "the teen hears a creak at 2.79 m");
            Assert.IsFalse(Hearing.Hears(new Vector3(2.81f, 0f, 0f), creak, 0.4f), "the teen hears a creak at 2.81 m");
            Assert.IsFalse(Hearing.Hears(Vector3.zero, creak, 0f), "a factor of 0 heard the creak at its source");
            Assert.IsTrue(Hearing.Hears(new Vector3(1.5f, 0f, 0f), hop), "premise: the M2 rule hears a hop at 1.5 m");
            Assert.AreEqual(Tuning.BarkRadius, Hearing.RadiusOf(NoiseKind.Bark));
            Assert.AreEqual(6f, Hearing.RadiusOf(NoiseKind.Bark));
            Assert.AreEqual(Tuning.CrashRadius, Hearing.RadiusOf(NoiseKind.Crash));
            Assert.AreEqual(6f, Hearing.RadiusOf(NoiseKind.Crash));

            foreach (string id in PersonalityDef.All)
            {
                PersonalityDef p = PersonalityDef.For(id);
                InhabitantRoutine r = RoutineFactory.Create(M5.DefOf(id, M5.SofaLoop()), null, StraightPlanner.Instance);
                Assert.AreEqual(p.Hears ? p.HearingFactor : 0f, r.HearingFactor, id);
            }
        }

        [Test]
        public void Bark_crash_and_creak_retarget_an_alerted_routine_and_nothing_else_does()
        {
            Assert.IsTrue(Hearing.RetargetsAlerted(NoiseKind.Creak));
            Assert.IsTrue(Hearing.RetargetsAlerted(NoiseKind.Bark));
            Assert.IsTrue(Hearing.RetargetsAlerted(NoiseKind.Crash));
            foreach (NoiseKind k in new[] { NoiseKind.Hop, NoiseKind.Topple, NoiseKind.Click, NoiseKind.Roll })
            {
                Assert.IsFalse(Hearing.RetargetsAlerted(k), k + " retargets");
            }
            int retargets = 0;
            foreach (NoiseKind k in Enum.GetValues(typeof(NoiseKind)))
            {
                // In Routine, every kind alerts.
                var calm = new InhabitantRoutine(M5.Level1(), 0);
                calm.Step(Dt);
                calm.Alert(calm.Position + Vector3.right * 2f, k);
                Assert.AreEqual(InhabitantMode.Alerted, calm.Mode, $"a {k} did not alert in Routine");

                // Alerted, the routine follows Hearing.RetargetsAlerted, the one rule.
                var r = new InhabitantRoutine(M5.Level1(), 0);
                r.Step(Dt);
                r.Alert(r.Position + YawMath.Forward(r.EyeYaw + 120f) * 2f, NoiseKind.Hop);
                for (int i = 0; i < 50; i++)
                {
                    r.Step(Dt);
                }
                Assert.AreEqual(InhabitantMode.Alerted, r.Mode, "premise: alerted");
                Vector3 first = r.AlertSource;
                r.Alert(first + new Vector3(1f, 0f, 1f), k);
                bool moved = r.AlertSource != first;
                Assert.AreEqual(Hearing.RetargetsAlerted(k), moved, $"a {k} {(moved ? "retargeted" : "did not retarget")} an alerted routine");
                retargets += moved ? 1 : 0;
            }
            Assert.AreEqual(3, retargets, "premise: creak, bark and crash retarget");
        }

        // ----- Memory and suspicion per personality -----

        [Test]
        public void Tidy_memory_notices_0_4_m_where_the_default_one_confirms()
        {
            var spawn = new FurniturePose(Vector3.zero, 0f);
            var decoy = new FurniturePose(new Vector3(3f, 0f, 0f), 0f);
            var tidy = new FurnitureMemory(spawn, new[] { decoy }, new[] { "chair" }, "chair", PersonalityDef.For(PersonalityDef.Tidy).Tolerance);
            var plain = new FurnitureMemory(spawn, new[] { decoy }, new[] { "chair" }, "chair");
            Assert.AreEqual(0.4f, tidy.Tolerance);
            Assert.AreEqual(Tuning.DisplacementTolerance, plain.Tolerance);

            var half = new FurniturePose(new Vector3(0.5f, 0f, 0f), 30f);
            Assert.AreEqual(Observation.Confirmed, plain.Observe(true, half, Dt), "premise: 0.5 m is in place for the default memory");
            for (int i = 1; i < M5.GraceSteps; i++)
            {
                Assert.AreEqual(Observation.Suspect, tidy.Observe(true, half, Dt), "the tidy one did not notice 0.5 m: its tolerance is ignored");
            }
            Assert.AreEqual(Observation.Discovery, tidy.Observe(true, half, Dt), "0.5 m out for the grace is a discovery for the tidy one");
            Assert.AreEqual(spawn.Position, tidy.PlayerSlot.Position, "an out of place sighting moved the slot");
            Assert.AreEqual(Observation.Confirmed, tidy.Observe(true, new FurniturePose(new Vector3(0.39f, 0f, 0f), 0f), Dt), "0.39 m is in place");

            // The decoys use the same tolerance: 0.5 m from the decoy is explained for the default one only.
            var nearDecoy = new FurniturePose(new Vector3(3f, 0f, 0.5f), 0f);
            Assert.AreEqual(Observation.ExplainedByDecoy, plain.Observe(true, nearDecoy, Dt));
            tidy.ResetGrace();
            Assert.AreEqual(Observation.Suspect, tidy.Observe(true, nearDecoy, Dt), "a decoy 0.5 m away explained the chair for the tidy one");
            Assert.AreEqual(Observation.ExplainedByDecoy, tidy.Observe(true, new FurniturePose(new Vector3(3f, 0f, 0.35f), 0f), Dt));

            // The property works like the constructor (the watchful one notices 0.5 m), and the static rule stays 0.75 m.
            var watchful = new FurnitureMemory(spawn, null, null, "chair") { Tolerance = PersonalityDef.For(PersonalityDef.Watchful).Tolerance };
            Assert.AreEqual(Observation.Suspect, watchful.Observe(true, new FurniturePose(new Vector3(0.6f, 0f, 0f), 0f), Dt));
            Assert.IsTrue(FurnitureMemory.WithinTolerance(spawn, half), "the static overload is the 0.75 m rule");
            Assert.IsFalse(FurnitureMemory.WithinTolerance(spawn, half, 0.4f));
        }

        [Test]
        public void Suspicion_gain_factor_scales_every_discovery()
        {
            foreach (string id in PersonalityDef.All)
            {
                float factor = PersonalityDef.For(id).SuspicionFactor;
                var meter = new SuspicionMeter { GainFactor = factor };
                int count = 0;
                while (!meter.Lost && count < 20)
                {
                    meter.AddDiscovery();
                    count++;
                    Assert.AreEqual(count * Tuning.SuspicionPerDiscovery * factor, meter.Value, 1e-4f, $"{id}: not 0.34 times its factor per discovery");
                }
                int expected = factor <= 0f ? 20 : Mathf.CeilToInt(Tuning.SuspicionLose / (Tuning.SuspicionPerDiscovery * factor) - 1e-3f);
                Assert.AreEqual(expected, count, $"{id}: discoveries to lose");
                Assert.AreEqual(factor > 0f, meter.Lost, id);
            }
            Assert.AreEqual(3, Count(1f), "premise: three discoveries lose by default");
            Assert.AreEqual(2, Count(1.5f), "the watchful one loses on the second discovery");
            Assert.AreEqual(5, Count(0.7f), "the dreamer loses on the fifth discovery");
            Assert.AreEqual(3, Count(1.3f), "the tidy one loses on the third (0.442 a time)");
            Assert.AreEqual(1f, new SuspicionMeter().GainFactor, "the default gain factor");
        }

        private static int Count(float factor)
        {
            var meter = new SuspicionMeter { GainFactor = factor };
            int n = 0;
            while (!meter.Lost && n < 20)
            {
                meter.AddDiscovery();
                n++;
            }
            return n;
        }

        // ----- InvestigatePlanner and frozen station walks (CONTRACT_M5_v3 15.1) -----

        private static bool OnL(Vector3 p, Vector3 a, Vector3 b, bool xFirst)
        {
            Vector3 c = M5.Corner(xFirst, a, b);
            return OnSegment(p, a, c) || OnSegment(p, c, b);
        }

        private static bool OnSegment(Vector3 p, Vector3 a, Vector3 b)
        {
            Vector3 ab = b - a;
            float t = ab.sqrMagnitude < 1e-8f ? 0f : Mathf.Clamp01(Vector3.Dot(p - a, ab) / ab.sqrMagnitude);
            return (a + ab * t - p).magnitude < 1e-4f;
        }

        /// <summary>Every walking step of a station walk lies on the station planner's L between the two stations.</summary>
        private static void AssertStationWalksOnL(List<M5Rec> log, int from, List<StationDef> stations, bool xFirst, string context)
        {
            int checkedSteps = 0;
            for (int i = Mathf.Max(from, 1); i < log.Count; i++)
            {
                if (log[i].Act != RoutineActivity.Walking || log[i].Mode != InhabitantMode.Routine)
                {
                    continue;
                }
                bool any = false;
                for (int a = 0; a < stations.Count && !any; a++)
                {
                    for (int b = 0; b < stations.Count && !any; b++)
                    {
                        any = a != b && OnL(log[i].Pos, stations[a].Position, stations[b].Position, xFirst);
                    }
                }
                Assert.IsTrue(any, $"{context}: a station walk left the station planner's path at record {i} ({log[i].Pos})");
                checkedSteps++;
            }
            Assert.Greater(checkedSteps, 100, context + ": premise: station walks were checked");
        }

        [Test]
        public void Station_walks_are_frozen_with_the_station_planner_and_every_other_walk_uses_the_investigate_planner()
        {
            var a = new M5.LPlanner(true);
            var b = new M5.LPlanner(false);
            var stations = new List<StationDef> { M5.Plain(0f, 0f, 0f, 1f), M5.Plain(4f, 3f, 90f, 1f) };
            InhabitantRoutine r = RoutineFactory.Create(M5.Def(stations), null, a, b, null, 0, RoutineFactory.AllAreas);
            Assert.AreEqual(2, a.Calls, "the loop's two station walks are frozen at creation, with the station planner");
            Assert.AreEqual(0, b.Calls, "the investigate planner planned a station walk");
            Assert.AreEqual(2, r.FrozenWalkCount);
            var rec = new M5Recorder(r);
            rec.StepUntil(x => x.LoopsCompleted >= 2, 10000, "two loops");
            Assert.AreEqual(2, a.Calls, "a station walk was planned again");
            Assert.AreEqual(0, b.Calls, "a station walk used the investigate planner");
            AssertStationWalksOnL(rec.Log, 0, stations, true, "before any interruption");

            // Investigate: planned by the investigate planner (z first), never the station one.
            rec.StepUntil(x => x.LastActivity == RoutineActivity.Walking, 2000, "a station walk");
            rec.Step(20);
            Vector3 start = r.Position;
            var target = new Vector3(-2f, 0f, 2.5f);
            int investigate = rec.Index;
            r.Investigate(target);
            Assert.AreEqual(1, b.Calls, "the investigation did not plan with the investigate planner");
            rec.StepUntil(x => x.ReachedTarget, 3000, "the target");
            Vector3 bCorner = M5.Corner(false, start, target);
            Assert.IsTrue(rec.Since(investigate).Exists(x => (x.Pos - bCorner).sqrMagnitude < 1e-8f), "the investigation did not follow the investigate planner");

            // The carry: its approach yaw and its path. Then the resume, back to the station.
            r.BeginCarry(new FurniturePose(new Vector3(1f, 0f, -2f), 0f));
            Assert.AreEqual(3, b.Calls, "the carry's approach yaw and path must use the investigate planner");
            rec.StepUntil(x => x.JustPutDown, 5000, "the put down");
            rec.Step();
            Assert.AreEqual(InhabitantMode.Routine, r.Mode, "premise: resumed");
            Assert.AreEqual(4, b.Calls, "the resume must plan with the investigate planner");

            // The switch-on.
            rec.StepUntil(x => x.InDwell, 5000, "the resumed dwell");
            r.BeginSwitchOn(r.Position + new Vector3(2f, 0f, 2f));
            Assert.AreEqual(5, b.Calls, "the switch-on must use the investigate planner");
            rec.StepUntil(x => x.JustSwitchedOn, 3000, "the switch-on");
            rec.Step();
            Assert.AreEqual(6, b.Calls, "the resume after the switch-on must use the investigate planner");
            Assert.AreEqual(2, a.Calls, "an investigation, a carry or a resume planned with the station planner");
            rec.StepUntil(x => x.InDwell, 5000, "back in the station cycle");

            // A later change of the investigate planner never changes a station walk.
            var c = new M5.LPlanner(false);
            r.InvestigatePlanner = c;
            int changed = rec.Index;
            int loops = r.LoopsCompleted;
            rec.StepUntil(x => x.LoopsCompleted >= loops + 2, 10000, "two loops after the change");
            Assert.AreEqual(2, a.Calls, "a station walk was planned again after the change");
            Assert.AreEqual(0, c.Calls, "a station walk used the new investigate planner");
            AssertStationWalksOnL(rec.Log, changed, stations, true, "after the change");
            M5.AssertTelegraphs(rec.Log, "two planners");

            // Null means the station planner, as in M4.
            r.InvestigatePlanner = null;
            rec.StepUntil(x => x.Mode == InhabitantMode.Routine, 100, "routine");
            r.Investigate(new Vector3(-1f, 0f, -1f));
            Assert.AreEqual(3, a.Calls, "with no investigate planner, the station planner plans the investigation");

            // The pinned branch of the resume.
            var a2 = new M5.LPlanner(true);
            var b2 = new M5.LPlanner(false);
            InhabitantRoutine pinned = RoutineFactory.Create(M5.Def(stations), null, a2, b2, null, 0, RoutineFactory.AllAreas);
            pinned.Pin(new Vector3(1f, 0f, 1f), 0f, 0f, true);
            pinned.Step(Dt);
            pinned.Investigate(new Vector3(-2f, 0f, 3f));
            Assert.AreEqual(1, b2.Calls);
            for (int i = 0; i < 3000 && !pinned.ReachedTarget; i++)
            {
                pinned.Step(Dt);
            }
            Assert.IsTrue(pinned.ReachedTarget, "premise: the pinned one reached its target");
            pinned.CancelInvestigation();
            Assert.AreEqual(2, b2.Calls, "the walk back to the pin must use the investigate planner");
            Assert.AreEqual(2, a2.Calls, "the pinned branch used the station planner");

            // Without the factory, each walk is frozen the first time it is walked, then reused.
            var a3 = new M5.LPlanner(true);
            var lazy = new InhabitantRoutine(stations, 0, a3);
            Assert.AreEqual(0, a3.Calls, "premise: nothing planned before the first step");
            for (int i = 0; i < 20000 && lazy.LoopsCompleted < 3; i++)
            {
                lazy.Step(Dt);
            }
            Assert.AreEqual(3, lazy.LoopsCompleted, "premise: three loops");
            Assert.AreEqual(2, a3.Calls, "a station walk was planned more than once");
        }

        // ----- The floor (CONTRACT_M5_v3 15.4) -----

        [Test]
        public void Flat_floor_changes_nothing_step_for_step()
        {
            var plain = new InhabitantRoutine(M5.Level1(), 0);
            var flat = new InhabitantRoutine(M5.Level1(), 0) { Floor = FloorMap.Flat };
            var nulled = new InhabitantRoutine(M5.Level1(), 0) { Floor = null };
            var level = new LevelDef();
            InhabitantRoutine leveled = RoutineFactory.Create(M5.Def(M5.Level1()), level, StraightPlanner.Instance);
            Assert.AreSame(FloorMap.Flat, plain.Floor, "the default floor is flat");
            Assert.AreSame(FloorMap.Flat, nulled.Floor, "a null floor is flat");
            Assert.AreSame(level.Floor, leveled.Floor, "the factory must give the level's floor");
            plain.Investigate(new Vector3(1f, 0f, 1f));
            flat.Investigate(new Vector3(1f, 0f, 1f));
            nulled.Investigate(new Vector3(1f, 0f, 1f));
            leveled.Investigate(new Vector3(1f, 0f, 1f));
            bool carried = false;
            for (int i = 0; i < 4000; i++)
            {
                foreach (InhabitantRoutine r in new[] { plain, flat, nulled, leveled })
                {
                    if (r.ReachedTarget)
                    {
                        r.BeginCarry(new FurniturePose(new Vector3(-1f, 0f, -2f), 0f));
                    }
                    r.Step(Dt);
                }
                carried |= plain.IsCarrying;
                foreach (InhabitantRoutine r in new[] { flat, nulled, leveled })
                {
                    Assert.AreEqual(plain.Position, r.Position, $"step {i}");
                    Assert.AreEqual(plain.EyePosition, r.EyePosition, $"step {i}");
                    Assert.AreEqual(plain.CarryAnchor, r.CarryAnchor, $"step {i}");
                }
                Assert.AreEqual(plain.Position.y + plain.EyeHeight, plain.EyePosition.y, $"the flat eye moved at step {i}");
                Assert.AreEqual(Tuning.CarryHeight, plain.CarryAnchor.y, $"the flat anchor moved at step {i}");
            }
            Assert.IsTrue(carried, "premise: the run carried");
        }

        [Test]
        public void Eye_and_carry_anchor_add_the_level_floor_height()
        {
            // A platform under station 1 (0.8 m): the routine reaches it, so the eye and the carry anchor must add it.
            var level = new LevelDef();
            level.Platforms.Add(new PlatformDef { Name = "Mezzanine", X = 3f, Z = 0f, SizeX = 2f, SizeZ = 2f, Height = 0.8f });
            var stations = new List<StationDef> { M5.Plain(0f, 0f, 90f, 1f), M5.Plain(3f, 0f, 90f, 1f) };
            InhabitantRoutine r = RoutineFactory.Create(M5.Def(stations), level, StraightPlanner.Instance);
            Assert.AreSame(level.Floor, r.Floor, "premise: the routine reads the level's floor");
            float highest = 0f;
            for (int i = 0; i < 1500; i++)
            {
                r.Step(Dt);
                float h = level.FloorHeightAt(r.Position.x, r.Position.z);
                Assert.AreEqual(h, r.FloorHeight, $"step {i}");
                Assert.AreEqual(r.EyeHeight + h, r.EyePosition.y, 1e-5f, $"the eye ignores the floor at step {i}");
                Assert.AreEqual(Tuning.CarryHeight + h, r.CarryAnchor.y, 1e-5f, $"the carry anchor ignores the floor at step {i}");
                highest = Mathf.Max(highest, h);
            }
            Assert.AreEqual(0.8f, highest, 1e-4f, "premise: the routine reached the platform, so the floor sum was checked for real");
        }

        // ----- The seat registry (CONTRACT_M5_v3 15.6) -----

        [Test]
        public void Seat_is_claimed_at_the_moment_of_sitting_and_released_on_the_first_stand_up_step()
        {
            var seats = new SeatRegistry();
            var r = new InhabitantRoutine(M5.SofaLoop(), 0) { Seats = seats, SeatOwner = 3 };
            int guard = 0;
            while (!r.JustSat)
            {
                Assert.Less(guard++, 3000, "never sat");
                Assert.IsFalse(seats.IsTaken(M5.Sofa), "claimed before the moment of sitting");
                r.Step(Dt);
            }
            Assert.AreEqual(SitResult.OnProp, r.LastSitResult);
            Assert.AreEqual(3, seats.SitterOf(M5.Sofa), "the seat is claimed at the moment of sitting");
            Assert.AreEqual(M5.Sofa, r.HeldSeat);
            guard = 0;
            while (r.LastActivity != RoutineActivity.StandingUp)
            {
                Assert.Less(guard++, 3000, "never stood up");
                Assert.AreEqual(3, seats.SitterOf(M5.Sofa), "released before the stand up");
                r.Step(Dt);
            }
            Assert.IsFalse(seats.IsTaken(M5.Sofa), "the seat must be free from the first stand-up step");
            Assert.IsNull(r.HeldSeat);
            Assert.AreEqual(0, seats.Count);

            // Pin and Startle release it at once.
            foreach (bool pin in new[] { true, false })
            {
                var s = new SeatRegistry();
                var x = new InhabitantRoutine(M5.SofaLoop(), 0) { Seats = s, SeatOwner = 1 };
                for (int i = 0; i < 3000 && !x.JustSat; i++)
                {
                    x.Step(Dt);
                }
                x.Step(Dt);
                Assert.IsTrue(s.IsTaken(M5.Sofa), "premise: seated");
                if (pin)
                {
                    x.Pin(x.Position, x.BodyYaw, 0f);
                }
                else
                {
                    x.Startle(Vector3.zero);
                }
                Assert.IsFalse(s.IsTaken(M5.Sofa), (pin ? "Pin" : "Startle") + " kept the seat");
            }
        }

        [Test]
        public void A_pratfall_claims_nothing()
        {
            foreach (bool home in new[] { false, true })
            {
                var seats = new SeatRegistry();
                var r = new InhabitantRoutine(M5.PlayerLoop(), 0) { Seats = seats, SeatOwner = 2, SeatOccupied = () => home };
                for (int i = 0; i < 3000 && !r.JustSat; i++)
                {
                    r.Step(Dt);
                }
                Assert.IsTrue(r.JustSat, "premise: the moment of sitting");
                Assert.AreEqual(home ? SitResult.OnPlayer : SitResult.Pratfall, r.LastSitResult);
                if (home)
                {
                    Assert.AreEqual(2, seats.SitterOf(InhabitantRoutine.PlayerSeat), "premise: a sit on the player claims the seat");
                    continue;
                }
                for (int i = 0; i < 400; i++)
                {
                    Assert.IsFalse(seats.IsTaken(InhabitantRoutine.PlayerSeat), $"a pratfall claimed the seat ({i})");
                    r.Step(Dt);
                }
            }
        }

        [Test]
        public void A_taken_seat_is_a_standing_dwell_with_no_back_turn_no_lowered_eye_and_no_stand_up_telegraph()
        {
            List<StationDef> stations = M5.SofaLoop();
            float walkYaw = YawMath.YawOf(stations[1].Position - stations[0].Position);
            float dwellSteps = stations[1].Dwell / Dt;

            // Control: the seat is free, so it turns its back and sits.
            var free = new M5Recorder(new InhabitantRoutine(M5.SofaLoop(), 0) { Seats = new SeatRegistry(), SeatOwner = 0 });
            free.StepUntil(x => x.LoopsCompleted >= 1, 5000, "the free loop");
            Assert.AreEqual(1, free.Log.FindAll(x => x.JustSat).Count, "premise: it sits when the seat is free");
            Assert.Greater(free.Log.FindAll(x => x.InDwell && x.Station == 1).Count, dwellSteps + M5.SitSteps, "premise: a seated dwell is longer");

            // Taken by inhabitant 7 before the walk.
            var seats = new SeatRegistry();
            Assert.IsTrue(seats.TryClaim(M5.Sofa, 7));
            var rec = new M5Recorder(new InhabitantRoutine(stations, 0) { Seats = seats, SeatOwner = 0 });
            rec.StepUntil(x => x.LoopsCompleted >= 1, 5000, "the loop");
            Assert.IsFalse(rec.Log.Exists(x => x.JustSat || x.Sitting || x.Lowered), "sat on a seat someone else holds");
            Assert.IsTrue(rec.Log.TrueForAll(x => x.Eye == Tuning.EyeHeight), "the eye lowered on a taken seat");
            Assert.AreEqual(7, seats.SitterOf(M5.Sofa), "the holder lost its seat");
            int first = rec.Log.FindIndex(x => x.InDwell && x.Station == 1);
            Assert.Greater(first, 0, "premise: it dwelt at the seat station");
            Assert.AreEqual(RoutineActivity.Walking, rec.Log[first].Act, "a turn came between the walk and the standing dwell: a back turn");
            List<M5Rec> dwell = rec.Log.FindAll(x => x.InDwell && x.Station == 1);
            Assert.IsTrue(dwell.TrueForAll(x => Mathf.Abs(Mathf.DeltaAngle(x.Body, walkYaw)) < 1e-3f), "it turned its back on a taken seat");
            Assert.IsFalse(dwell.Exists(x => x.Act == RoutineActivity.Telegraph || x.Act == RoutineActivity.StandingUp),
                "a standing dwell has no stand-up telegraph");
            Assert.That(dwell.Count, Is.InRange(dwellSteps - 1, dwellSteps + 1), "the standing dwell is not the plain dwell");
            M5.AssertTelegraphs(rec.Log, "taken seat");

            // The player seat held by someone else: no seat ghost, no sit.
            var held = new SeatRegistry();
            held.TryClaim(InhabitantRoutine.PlayerSeat, 7);
            var player = new M5Recorder(new InhabitantRoutine(M5.PlayerLoop(), 0) { Seats = held, SeatOwner = 0 });
            player.StepUntil(x => x.LoopsCompleted >= 1, 5000, "the player loop");
            Assert.IsFalse(player.Log.Exists(x => x.Targets || x.JustSat), "a held player seat showed the ghost or was sat on");
            var open = new M5Recorder(new InhabitantRoutine(M5.PlayerLoop(), 0) { Seats = new SeatRegistry(), SeatOwner = 0 });
            open.StepUntil(x => x.LoopsCompleted >= 1, 5000, "the open player loop");
            Assert.IsTrue(open.Log.Exists(x => x.Targets) && open.Log.Exists(x => x.JustSat), "premise: a free player seat shows the ghost and is sat on");
        }

        [Test]
        public void A_seat_taken_during_the_back_turn_leaves_the_rest_of_the_dwell_standing()
        {
            var seats = new SeatRegistry();
            List<StationDef> stations = M5.SofaLoop();
            var rec = new M5Recorder(new InhabitantRoutine(stations, 0) { Seats = seats, SeatOwner = 0 });
            InhabitantRoutine r = rec.R;
            rec.StepUntil(x => x.Position == stations[1].Position && x.LastActivity == RoutineActivity.Telegraph, 3000, "the back turn");
            Assert.IsTrue(seats.TryClaim(M5.Sofa, 9), "premise: the rival sits first");
            int from = rec.Index;
            rec.StepUntil(x => !x.InDwell && x.StationIndex == 1 && x.LastActivity != RoutineActivity.TurningBody
                                && x.LastActivity != RoutineActivity.Telegraph, 3000, "the end of the visit");
            List<M5Rec> visit = rec.Since(from);
            Assert.IsTrue(visit.Exists(x => x.InDwell), "premise: it dwelt");
            Assert.IsFalse(visit.Exists(x => x.JustSat || x.Sitting || x.Lowered), "sat on the rival");
            Assert.IsFalse(visit.Exists(x => x.Act == RoutineActivity.StandingUp), "stood up without sitting");
            Assert.IsFalse(visit.Exists(x => x.InDwell && x.Act == RoutineActivity.Telegraph), "the stand-up telegraph was kept");
            Assert.AreEqual(9, seats.SitterOf(M5.Sofa));

            // The rival leaves: the next visit sits.
            seats.Release(M5.Sofa, 9);
            rec.StepUntil(x => x.JustSat, 5000, "the next sit");
            Assert.AreEqual(0, seats.SitterOf(M5.Sofa));
            M5.AssertTelegraphs(rec.Log, "seat race");
        }

        [Test]
        public void Two_routines_sharing_a_registry_never_sit_on_the_same_seat()
        {
            var seats = new SeatRegistry();
            var a = new InhabitantRoutine(M5.SofaLoop(), 0) { Seats = seats, SeatOwner = 0 };
            var b = new InhabitantRoutine(M5.SofaLoop(), 1) { Seats = seats, SeatOwner = 1 };
            var ra = new M5Recorder(a);
            var rb = new M5Recorder(b);
            int both = 0;
            int sitsA = 0;
            int sitsB = 0;
            int standingA = 0;
            int standingB = 0;
            bool wasDwellingA = false;
            bool wasDwellingB = false;
            bool satThisVisitA = false;
            bool satThisVisitB = false;
            for (int i = 0; i < 9000; i++)
            {
                ra.Step();
                rb.Step();
                Assert.IsFalse(a.IsSitting && b.IsSitting, $"both sat on the sofa at step {i}");
                if (a.IsSitting)
                {
                    Assert.AreEqual(0, seats.SitterOf(M5.Sofa), $"step {i}");
                }
                if (b.IsSitting)
                {
                    Assert.AreEqual(1, seats.SitterOf(M5.Sofa), $"step {i}");
                }
                sitsA += a.JustSat ? 1 : 0;
                sitsB += b.JustSat ? 1 : 0;
                satThisVisitA |= a.JustSat;
                satThisVisitB |= b.JustSat;
                bool dwellingA = a.InDwell && a.StationIndex == 1;
                bool dwellingB = b.InDwell && b.StationIndex == 1;
                if (wasDwellingA && !dwellingA)
                {
                    standingA += satThisVisitA ? 0 : 1;
                    satThisVisitA = false;
                }
                if (wasDwellingB && !dwellingB)
                {
                    standingB += satThisVisitB ? 0 : 1;
                    satThisVisitB = false;
                }
                wasDwellingA = dwellingA;
                wasDwellingB = dwellingB;
                both += dwellingA && dwellingB ? 1 : 0;
            }
            TestContext.WriteLine($"sits A {sitsA}, B {sitsB}; standing dwells A {standingA}, B {standingB}; steps both at the sofa {both}");
            Assert.Greater(sitsA, 0, "premise: A sat");
            Assert.Greater(sitsB, 0, "premise: B sat");
            Assert.Greater(standingA + standingB, 0, "premise: a seat was found taken");
            Assert.Greater(both, 0, "premise: both were at the sofa at once");
            M5.AssertTelegraphs(ra.Log, "A");
            M5.AssertTelegraphs(rb.Log, "B");
        }

        // ----- The factory -----

        private sealed class MaskPlanner : IAreaMaskPlanner
        {
            public readonly List<int> Masks = new List<int>();
            public int Plain;

            public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners)
            {
                Plain++;
                return StraightPlanner.Instance.TryPlan(from, to, corners);
            }

            public bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners, int areaMask)
            {
                Masks.Add(areaMask);
                return StraightPlanner.Instance.TryPlan(from, to, corners);
            }
        }

        [Test]
        public void Factory_sets_every_field_before_the_first_step()
        {
            var level = new LevelDef();
            var station = new MaskPlanner();
            var investigate = new M5.LPlanner(false);
            var seats = new SeatRegistry();
            InhabitantDef def = M5.Def(M5.Square(0.5f), 2, PersonalityDef.Tidy, null, RoutinePatterns.Wander, 99);
            InhabitantRoutine r = RoutineFactory.Create(def, level, station, investigate, seats, 2, 5);
            Assert.AreEqual(PersonalityDef.Tidy, r.Personality.Id);
            Assert.AreEqual(RoutinePatterns.Wander, r.Pattern);
            Assert.AreEqual(99, r.Seed);
            Assert.AreSame(investigate, r.InvestigatePlanner);
            Assert.AreSame(seats, r.Seats);
            Assert.AreEqual(2, r.SeatOwner);
            Assert.AreSame(level.Floor, r.Floor);
            Assert.AreEqual(5, r.StationAreaMask);
            Assert.AreEqual(12, r.FrozenWalkCount, "every ordered pair of a 4-station wander is frozen at creation");
            Assert.AreEqual(12, station.Masks.Count, "the frozen walks must plan with the station area mask");
            Assert.IsTrue(station.Masks.TrueForAll(m => m == 5), "a frozen walk used another mask");
            Assert.AreEqual(0, station.Plain, "a frozen walk ignored the area mask");
            Assert.AreEqual(0, investigate.Calls);
            Assert.AreEqual(2, r.StationIndex, "the start station");
            Assert.AreEqual(def.Stations[2].Position, r.Position);
            Assert.AreEqual(Tuning.EyeHeight, r.EyeHeight);

            // Every area: the planner is used as given.
            var unmasked = new MaskPlanner();
            RoutineFactory.Create(M5.Def(M5.Square(0.5f), pattern: RoutinePatterns.PingPong), null, unmasked, null, null, 0, RoutineFactory.AllAreas);
            Assert.AreEqual(6, unmasked.Plain, "pingpong freezes 2 (n - 1) walks");
            Assert.AreEqual(0, unmasked.Masks.Count);

            // A dog kind wins, no level is a flat floor, defaults are the M4 routine.
            InhabitantRoutine dog = RoutineFactory.Create(M5.Def(M5.Square(0.5f), personality: PersonalityDef.Teen, kind: PersonalityDef.Dog), null, null);
            Assert.AreEqual(PersonalityDef.Dog, dog.Personality.Id);
            Assert.AreSame(FloorMap.Flat, dog.Floor);
            Assert.AreEqual(Tuning.DogEyeHeight, dog.EyeHeight);
            InhabitantRoutine plain = RoutineFactory.Create(M5.Def(M5.Square(0.5f)), null, null);
            Assert.AreEqual(PersonalityDef.Default, plain.Personality.Id);
            Assert.AreEqual(RoutinePatterns.Loop, plain.Pattern);
            Assert.IsNull(plain.InvestigatePlanner);
            Assert.IsNull(plain.Seats);
            Assert.AreEqual(RoutineFactory.AllAreas, plain.StationAreaMask);
            Assert.AreEqual(4, plain.FrozenWalkCount);
            Assert.Throws<ArgumentNullException>(() => RoutineFactory.Create(null, level, null));
        }

        [TestCase(0)]
        [TestCase(2)]
        public void Factory_default_loop_is_the_M1_routine_step_for_step(int start)
        {
            var reference = new M1ReferenceRoutine(M5.Level1(), start);
            InhabitantRoutine r = RoutineFactory.Create(M5.Def(M5.Level1(), start), new LevelDef(), StraightPlanner.Instance, null,
                new SeatRegistry(), 0, RoutineFactory.AllAreas);
            int steps = 0;
            int visit = 0;
            while (reference.LoopsCompleted < 2)
            {
                Assert.Less(steps++, 40000, "the reference routine never looped twice");
                reference.Step(Dt);
                r.Step(Dt);
                string at = $"step {steps}";
                Assert.AreEqual(reference.Position, r.Position, at + ": position");
                Assert.AreEqual(reference.BodyYaw, r.BodyYaw, at + ": body yaw");
                Assert.AreEqual(reference.HeadYaw, r.HeadYaw, at + ": head yaw");
                Assert.AreEqual(reference.LastActivity, r.LastActivity, at + ": activity");
                Assert.AreEqual(reference.InDwell, r.InDwell, at + ": in dwell");
                Assert.AreEqual(reference.StationIndex, r.StationIndex, at + ": station");
                Assert.AreEqual(reference.LoopsCompleted, r.LoopsCompleted, at + ": loops");
                Assert.AreEqual(reference.TelegraphCount, r.TelegraphCount, at + ": telegraph count");
                Assert.AreEqual(reference.Position + Vector3.up * Tuning.EyeHeight, r.EyePosition, at + ": eye position");
                Assert.IsFalse(r.Asleep, at);
                Assert.That(r.VisitIndex - visit, Is.InRange(0, 1), at + ": visit index");
                visit = r.VisitIndex;
            }
            Assert.Greater(steps, 1000, "premise: two loops are long");
            Assert.AreEqual(8, visit, "premise: two loops of four stations end on visit 8");
        }

        // ----- Fairness: the same telegraph for every personality (CONTRACT_M5 3) -----

        /// <summary>Large turns, glances, and a resolved sofa seat.</summary>
        private static List<StationDef> HumanLoop()
        {
            var level = new LevelDef();
            level.Props.Add(new PropDef { Name = "Sofa", Kind = "sofa", X = 1.2f, Z = 2.0f, SizeX = 1.8f, SizeY = 0.8f, SizeZ = 0.8f });
            StationDef seat = M5.Plain(1.2f, 1.4f, 180f, 2.5f, M5.Glance(0.5f, 60f, 0.5f));
            seat.Sit = "Sofa";
            var stations = new List<StationDef>
            {
                M5.Plain(-1.5f, 2.2f, 0f, 3f, M5.Glance(1f, -70f, 1f)),
                seat,
                M5.Plain(0f, -2.3f, 180f, 2f),
                M5.Plain(2.2f, -0.7f, 180f, 2f, M5.Glance(2f, -80f, 1f)),
            };
            level.Inhabitants.Add(new InhabitantDef { Name = "Habitant", Stations = stations });
            level.ResolveSeats();
            return stations;
        }

        /// <summary>A sleep station and two others, every turn large.</summary>
        private static List<StationDef> DogLoop()
        {
            StationDef bed = M5.Plain(0f, 0f, 0f, 1.5f);
            bed.Sleep = true;
            return new List<StationDef> { bed, M5.Plain(3f, 0f, 180f, 1f), M5.Plain(3f, 3f, -90f, 0.5f) };
        }

        [Test]
        public void Every_personality_telegraphs_every_turn_over_30_deg_for_0_6_s()
        {
            var kinds = new[] { NoiseKind.Hop, NoiseKind.Creak, NoiseKind.Bark, NoiseKind.Crash, NoiseKind.Click };
            for (int p = 0; p < PersonalityDef.All.Length; p++)
            {
                string id = PersonalityDef.All[p];
                bool dog = id == PersonalityDef.Dog;
                var rng = new System.Random(17 + p);
                InhabitantRoutine r = RoutineFactory.Create(M5.DefOf(id, dog ? DogLoop() : HumanLoop()), null, new M5.LPlanner(),
                    new M5.LPlanner(false), new SeatRegistry(), 0, RoutineFactory.AllAreas);
                var rec = new M5Recorder(r);
                int alerts = 0;
                for (int step = 0; step < 7000; step++)
                {
                    rec.Step();
                    if (r.Mode == InhabitantMode.Investigating && r.ReachedTarget)
                    {
                        r.CancelInvestigation();
                    }
                    double roll = rng.NextDouble();
                    if (roll < 0.006)
                    {
                        InhabitantMode before = r.Mode;
                        r.Alert(r.Position + YawMath.Forward((float)(rng.NextDouble() * 360.0)) * 3f, kinds[rng.Next(kinds.Length)]);
                        alerts += before != InhabitantMode.Alerted && r.Mode == InhabitantMode.Alerted ? 1 : 0;
                    }
                    else if (roll < 0.0075 && r.Mode == InhabitantMode.Routine)
                    {
                        r.Investigate(r.Position + YawMath.Forward((float)(rng.NextDouble() * 360.0)) * 2.5f);
                    }
                }
                int large = M5.AssertTelegraphs(rec.Log, id);
                TestContext.WriteLine($"{id}: {large} large turns, {alerts} alerts");
                Assert.Greater(large, 30, id + ": premise: too few large turns");
                if (dog)
                {
                    Assert.AreEqual(0, alerts, "the dog was alerted");
                    Assert.IsTrue(rec.Log.Exists(x => x.Asleep), "premise: the dog slept");
                }
                else
                {
                    Assert.Greater(alerts, 5, id + ": premise: too few alerts");
                    Assert.IsTrue(rec.Log.Exists(x => x.JustSat), id + ": premise: it sat");
                }
            }
        }
    }

    /// <summary>docs/CONTRACT_M5_v3.md 6 and 15.7: the save content and its rules (the file handling is SaveStore's).</summary>
    public sealed class CoreM5SaveTests
    {
        [Test]
        public void RecordWin_replaces_a_best_time_only_with_a_strictly_lower_one()
        {
            var save = new SaveData();
            RecordResult first = save.RecordWin("level1", 30f);
            Assert.IsTrue(first.NewBest, "a first win is a new best");
            Assert.Less(first.PreviousBest, 0f, "no previous best");
            Assert.AreEqual(30f, first.Best);
            CollectionAssert.AreEqual(new[] { "level1" }, save.Won);

            RecordResult slower = save.RecordWin("level1", 35f);
            Assert.IsFalse(slower.NewBest, "a slower time is not a best");
            Assert.AreEqual(30f, slower.Best, "a slower time overwrote the best");
            Assert.AreEqual(30f, save.Best["level1"], "a slower time overwrote the best");
            Assert.AreEqual(30f, slower.PreviousBest);

            RecordResult equal = save.RecordWin("level1", 30f);
            Assert.IsFalse(equal.NewBest, "an equal time is not strictly lower");
            Assert.AreEqual(30f, save.Best["level1"]);

            RecordResult faster = save.RecordWin("level1", 25.5f);
            Assert.IsTrue(faster.NewBest);
            Assert.AreEqual(25.5f, faster.Best);
            Assert.AreEqual(30f, faster.PreviousBest);
            Assert.AreEqual(25.5f, save.Best["level1"]);
            CollectionAssert.AreEqual(new[] { "level1" }, save.Won, "a level is won once");

            save.RecordWin("level3", 40f);
            CollectionAssert.AreEqual(new[] { "level1", "level3" }, save.Won);
            foreach (string id in new[] { null, "" })
            {
                RecordResult none = save.RecordWin(id, 1f);
                Assert.IsFalse(none.NewBest);
                Assert.Less(none.PreviousBest, 0f);
            }
            Assert.AreEqual(2, save.Won.Count, "an empty id was recorded");
            Assert.AreEqual(2, save.Best.Count);
        }

        [Test]
        public void IsUnlocked_opens_a_level_once_the_one_before_it_is_won()
        {
            var order = new List<string> { "level1", "level2", "level8" };
            var save = new SaveData();
            Assert.IsTrue(save.IsUnlocked(order, 0), "the first level is always open");
            Assert.IsFalse(save.IsUnlocked(order, 1));
            Assert.IsFalse(save.IsUnlocked(order, 2));
            Assert.IsFalse(save.IsUnlocked(order, -1));
            Assert.IsFalse(save.IsUnlocked(order, 3));
            Assert.IsFalse(save.IsUnlocked(null, 0));
            save.RecordWin("level8", 10f);
            Assert.IsFalse(save.IsUnlocked(order, 1), "winning a later level opened an earlier one");
            save.RecordWin("level1", 10f);
            Assert.IsTrue(save.IsUnlocked(order, 1));
            Assert.IsFalse(save.IsUnlocked(order, 2), "level 8 is open before level 2 is won");
            save.RecordWin("level2", 10f);
            Assert.IsTrue(save.IsUnlocked(order, 2));
        }

        [Test]
        public void Parse_round_trips_and_never_throws()
        {
            var save = new SaveData();
            save.RecordWin("level1", 12.5f);
            save.RecordWin("level12", 70.25f);
            SaveData back = SaveData.Parse(save.ToJson(), out string problem);
            Assert.IsNotNull(back, problem);
            Assert.IsNull(problem);
            Assert.AreEqual(SaveData.CurrentVersion, back.Version);
            CollectionAssert.AreEqual(save.Won, back.Won);
            CollectionAssert.AreEquivalent(save.Best, back.Best);
            StringAssert.Contains("\"version\": 1", save.ToJson());

            // Missing lists are empty ones; a level listed twice is kept once.
            SaveData bare = SaveData.Parse("{ \"version\": 1 }", out problem);
            Assert.IsNotNull(bare, problem);
            Assert.IsEmpty(bare.Won);
            Assert.IsEmpty(bare.Best);
            SaveData nulls = SaveData.Parse("{ \"version\": 1, \"won\": null, \"best\": null }", out problem);
            Assert.IsNotNull(nulls, problem);
            Assert.IsEmpty(nulls.Won);
            SaveData twice = SaveData.Parse("{ \"version\": 1, \"won\": [\"level1\", \"level1\"], \"best\": { \"level1\": 3 } }", out problem);
            Assert.IsNotNull(twice, problem);
            CollectionAssert.AreEqual(new[] { "level1" }, twice.Won);
            Assert.AreEqual(3f, twice.Best["level1"]);

            var corrupt = new[]
            {
                null, "", "   ", "{", "not json", "[]", "42", "null", "\"text\"",
                "{ \"won\": [], \"best\": {} }",
                "{ \"version\": 0, \"won\": [] }",
                "{ \"version\": 2, \"won\": [] }",
                "{ \"version\": -1 }",
                "{ \"version\": \"1\" }",
                "{ \"version\": 1.5 }",
                "{ \"version\": 99999999999999999999999 }",
                "{ \"version\": 1, \"won\": \"level1\" }",
                "{ \"version\": 1, \"won\": [1, 2] }",
                "{ \"version\": 1, \"best\": [] }",
                "{ \"version\": 1, \"best\": { \"level1\": \"fast\" } }",
                "{ \"version\": 1, \"best\": { \"level1\": -3 } }",
                "{ \"version\": 1, \"won\": [] ",
            };
            foreach (string json in corrupt)
            {
                SaveData parsed = null;
                string why = null;
                Assert.DoesNotThrow(() => parsed = SaveData.Parse(json, out why), json ?? "null");
                Assert.IsNull(parsed, $"'{json}' was accepted");
                Assert.IsFalse(string.IsNullOrEmpty(why), $"'{json}' gave no problem");
            }
        }
    }
}
