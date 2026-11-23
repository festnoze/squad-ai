using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>
    /// GRIP (product owner, 2026-11-22): where carriers hold each player furniture body (GripDef), and the dog's head
    /// lowered onto its bite (GripMath). The human's arm is the Quaternius man's, measured on its GLB at the game's 1.6 m eye
    /// (scratchpad man.py): the upper arm joint 1.357 m up, 0.17 m out and 0.045 m ahead of the feet, the arm 0.559 m from that
    /// joint to the wrist (0.263 upper, 0.296 fore), the spine's pivot (Abdomen) 0.825 m up; the belly at most 0.15 m ahead
    /// of the feet. The dog's neck chain is the Husky's rest pose at its fitted size (scratchpad dog.py).
    /// </summary>
    public sealed class GripTests
    {
        private static readonly string[] Kinds = { "chair", "stool", "armchair", "floor_lamp", "office_chair", "rocking_chair" };

        private const float ShoulderHeight = 1.357f;
        private const float ShoulderOut = 0.17f;
        private const float ShoulderAhead = 0.045f;
        private const float ArmReach = 0.559f;
        private const float SpinePivot = 0.825f;
        private const float BellyAhead = 0.15f;

        // The Husky's rest neck chain in its body plane (x forward, y up, metres): Neck1, then to Neck2, Neck3 and the head bone.
        private static readonly Vector2 NeckBase = new Vector2(0.257f, 0.376f);
        private static readonly Vector2[] NeckSegments = { new Vector2(0.034f, 0.044f), new Vector2(0.030f, 0.050f), new Vector2(0.033f, 0.046f) };
        private static readonly Vector2 SnoutFromHead = new Vector2(0.077f, -Tuning.DogSnoutDrop) * Tuning.DogHeadScale;

        [Test]
        public void Every_body_kind_has_its_own_grip_and_unknown_kinds_get_the_chairs()
        {
            foreach (string kind in Kinds)
            {
                Assert.AreEqual(kind, GripDef.For(kind).Kind, kind);
            }
            Assert.AreEqual("chair", GripDef.For(null).Kind);
            Assert.AreEqual("chair", GripDef.For("piano").Kind);
            Assert.AreNotSame(GripDef.For("chair"), GripDef.For("chair"), "a shared instance could be changed by a caller");
        }

        [Test]
        public void Human_hands_rest_on_the_furniture_within_reach_with_the_body_clear_of_it()
        {
            foreach (string kind in Kinds)
            {
                GripDef g = GripDef.For(kind);
                BodyDef body = BodyDef.For(kind);
                // The furniture as the carrier sees it: its centre HumanStand ahead of his feet, lifted CarryHeight.
                foreach ((Vector3 wrist, float side) in new[] { (g.LeftWrist, -1f), (g.RightWrist, 1f) })
                {
                    Assert.LessOrEqual(Mathf.Abs(wrist.x), 0.5f * body.Size.x + 0.08f, $"{kind}: a hand is beside the furniture, not on it");
                    Assert.LessOrEqual(Mathf.Abs(wrist.z), 0.5f * body.Size.z + 0.08f, $"{kind}: a hand is in front of or behind the furniture");
                    Assert.LessOrEqual(wrist.y, body.Size.y + 0.06f, $"{kind}: a hand floats above the furniture");
                    Assert.Less(wrist.z, 0.05f, $"{kind}: a hand reaches past the furniture's middle");
                    // The shoulder, leaned forward about the spine's pivot.
                    float lean = g.HumanLean * Mathf.Deg2Rad;
                    float up = ShoulderHeight - SpinePivot;
                    var shoulder = new Vector3(side * ShoulderOut, SpinePivot + up * Mathf.Cos(lean), ShoulderAhead + up * Mathf.Sin(lean));
                    var target = new Vector3(wrist.x, wrist.y + Tuning.CarryHeight, g.HumanStand + wrist.z);
                    Assert.LessOrEqual(Vector3.Distance(shoulder, target), ArmReach, $"{kind}: a hand cannot reach its place ({Vector3.Distance(shoulder, target):0.000} m)");
                    Assert.Greater(Vector3.Distance(shoulder, target), 0.2f, $"{kind}: a hand is crushed against the shoulder");
                }
                // The body clear of the furniture: its near face at least a forearm ahead of the feet, the belly well behind it.
                float nearFace = g.HumanStand - 0.5f * body.Size.z;
                Assert.GreaterOrEqual(nearFace - BellyAhead, 0.07f, $"{kind}: the carrier's body stands inside the furniture ({nearFace:0.000} m)");
                Assert.That(g.HumanHoldBack(body.CarryForward), Is.InRange(-0.1f, 0.15f), $"{kind}: the model strays too far from its rule position");
            }
        }

        [Test]
        public void The_human_carrying_the_chair_stands_a_step_behind_where_the_rules_put_him()
        {
            // The product owner's shot: his torso inside the chair's back. The backrest's top rail is 0.18 to 0.225 m behind
            // the chair's centre; the rules hold the centre CarryForward (0.45 m) ahead of him.
            GripDef g = GripDef.For("chair");
            Assert.Greater(g.HumanHoldBack(Tuning.CarryForward), 0.05f, "the carrier's model is not stepped back from the chair");
            Assert.That(g.LeftWrist.y, Is.InRange(0.88f, 0.96f), "the left hand is not on the backrest's top rail (0.82 to 0.90 m)");
            Assert.That(g.RightWrist.y, Is.InRange(0.88f, 0.96f), "the right hand is not on the backrest's top rail");
            Assert.Less(g.LeftWrist.z, -0.2f, "the left hand is not at the backrest");
            Assert.AreEqual(-g.LeftWrist.x, g.RightWrist.x, 1e-5f, "the hands are not placed symmetrically on the rail");
        }

        [Test]
        public void The_dog_bites_the_stool_by_a_leg_below_its_seat()
        {
            // The product owner's shot: the dog held the stool by the top of its seat. The seat's cushion starts at 0.45 m;
            // the dog must bite a leg low down, at most 0.3 m up, inside the stool's footprint, on its near side.
            GripDef g = GripDef.For("stool");
            Vector3 size = BodyDef.For("stool").Size;
            Assert.LessOrEqual(g.Snout.y, 0.30f, $"the dog bites the stool at {g.Snout.y:0.00} m, not by a leg low down");
            Assert.Greater(g.Snout.y, 0.05f, "the dog bites the floor");
            Assert.Less(g.Snout.z, 0f, "the dog bites the far side of the stool");
            Assert.LessOrEqual(Mathf.Abs(g.Snout.x), 0.5f * size.x, "the dog bites beside the stool");
        }

        [Test]
        public void The_dog_never_bites_the_top_of_a_seat_and_bites_on_the_near_side()
        {
            foreach (string kind in Kinds)
            {
                GripDef g = GripDef.For(kind);
                Vector3 size = BodyDef.For(kind).Size;
                Assert.Less(g.Snout.y, 0.45f, $"{kind}: the dog bites too high ({g.Snout.y:0.00} m)");
                Assert.Less(g.Snout.z, 0f, $"{kind}: the dog bites the far side");
                Assert.LessOrEqual(Mathf.Abs(g.Snout.z), 0.5f * size.z + 0.02f, $"{kind}: the dog bites behind the furniture");
                Assert.LessOrEqual(Mathf.Abs(g.Snout.x), 0.5f * size.x + 0.02f, $"{kind}: the dog bites beside the furniture");
            }
        }

        [Test]
        public void The_dogs_neck_brings_its_snout_down_to_every_bite()
        {
            float rest = GripMath.Tip(NeckBase, NeckSegments, SnoutFromHead, 0f, Tuning.DogGripHeadFollow).y;
            Assert.That(rest, Is.InRange(0.45f, 0.55f), "premise: the Husky's snout is not at its rest height");
            foreach (string kind in Kinds)
            {
                float height = GripDef.For(kind).Snout.y + Tuning.DogDragLift;
                float bend = GripMath.SolveNeckBend(NeckBase, NeckSegments, SnoutFromHead, Tuning.DogGripHeadFollow, height);
                Vector2 tip = GripMath.Tip(NeckBase, NeckSegments, SnoutFromHead, bend, Tuning.DogGripHeadFollow);
                Assert.Less(bend, GripMath.MaxNeckBend, $"{kind}: the dog cannot get its head down to its bite");
                Assert.AreEqual(height, tip.y, 0.01f, $"{kind}: the snout misses the bite's height (bend {bend:0.0} deg)");
                Assert.Greater(tip.x, NeckBase.x, $"{kind}: the snout folds back under the neck");
            }
            // Above the snout's own height: no bend; out of reach: the most it bends.
            Assert.AreEqual(0f, GripMath.SolveNeckBend(NeckBase, NeckSegments, SnoutFromHead, 1f, rest + 0.1f));
            Assert.AreEqual(GripMath.MaxNeckBend, GripMath.SolveNeckBend(NeckBase, NeckSegments, SnoutFromHead, 1f, 0f));
            // The tip only comes down as the bend grows (what the bisection relies on).
            float previous = rest;
            for (float b = 2f; b <= GripMath.MaxNeckBend; b += 2f)
            {
                float y = GripMath.Tip(NeckBase, NeckSegments, SnoutFromHead, b, 1f).y;
                Assert.Less(y, previous, $"the snout rises again at a {b:0} deg bend");
                previous = y;
            }
        }

        [Test]
        public void Down_turns_forward_toward_the_floor()
        {
            Vector2 d = GripMath.Down(new Vector2(1f, 0f), 90f);
            Assert.AreEqual(0f, d.x, 1e-5f);
            Assert.AreEqual(-1f, d.y, 1e-5f);
            Vector2 up = GripMath.Down(new Vector2(0f, 1f), 90f);
            Assert.AreEqual(1f, up.x, 1e-5f, "the neck's up does not tilt forward as it bends");
        }

        [Test]
        public void The_title_loops_alternate_the_dog_and_the_human()
        {
            float act = 1f - Tuning.TitleLogoStillFraction;
            bool dogInFirst = false;
            bool humanInSecond = false;
            for (int i = 0; i <= 400; i++)
            {
                float u = Tuning.TitleLogoStillFraction + act * i / 400f;
                TitleLogo.Pose first = TitleLogo.Sample(u);
                TitleLogo.Pose second = TitleLogo.Sample(1f + u);
                Assert.AreEqual(0f, first.HumanAlpha, $"a human in the dog's loop at {u:0.000}");
                Assert.IsFalse(first.Holding, $"a human holds the chair in the dog's loop at {u:0.000}");
                Assert.AreEqual(0f, second.DogAlpha, $"the dog in the human's loop at {u:0.000}");
                Assert.IsFalse(second.DogBite, $"the dog bites in the human's loop at {u:0.000}");
                dogInFirst |= first.DogAlpha >= 1f && first.DogBite;
                humanInSecond |= second.HumanAlpha >= 1f && second.Holding;
                // Same choreography for the chair and the light up to the carrier's arrival.
                if (u < Tuning.TitleLogoStillFraction + act * TitleLogo.TrotStart)
                {
                    Assert.AreEqual(first.Chair, second.Chair, 1e-6f, $"the chair's hops differ between the loops at {u:0.000}");
                    Assert.AreEqual(first.Light, second.Light, 1e-6f, $"the light differs between the loops at {u:0.000}");
                }
            }
            Assert.IsTrue(dogInFirst, "the dog never bites the chair in the first loop");
            Assert.IsTrue(humanInSecond, "the human never holds the chair in the second loop");
            Assert.AreEqual(TitleLogo.Rest, TitleLogo.Sample(2f), "two loops do not come back to the start");
            Assert.AreEqual(TitleLogo.Rest, TitleLogo.Sample(1f), "the human's loop does not start on the still pose");
        }
    }
}
