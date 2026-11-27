// Owned by B3. EditMode tests of the pure math of contract 13 (SteeringInput) and 14 (CameraRig): dpi clamp, stick
// mapping, dead zone, leash, keyboard directions, hover dead radius and arming, spring half-lives, chase framing width,
// view sizes and the arena clamp.
using System;
using NUnit.Framework;
using PainterIO.Runtime;
using UnityEngine;

namespace PainterIO.Tests
{
    public class InputCameraMathTests
    {
        private const float PortraitAspect = 540f / 960f;

        // ------------------------------------------------------------------------------------------------------------
        // Contract 13: touch stick.

        [TestCase(0f, 160f)]
        [TestCase(-5f, 160f)]
        [TestCase(float.NaN, 160f)]
        [TestCase(96f, 120f)]
        [TestCase(120f, 120f)]
        [TestCase(326f, 326f)]
        [TestCase(560f, 560f)]
        [TestCase(800f, 560f)]
        public void Input_DpiIsClampedAndDefaultsTo160(float reported, float expected)
        {
            Assert.AreEqual(expected, SteeringInput.ClampDpi(reported), 1e-4f);
        }

        [Test]
        public void Input_DeadZoneAndLeashInPixels()
        {
            Assert.AreEqual(8f, SteeringInput.InchesToPixels(SteeringInput.DeadZoneInches, 0f), 1e-4f, "0.05 in at 160 dpi");
            Assert.AreEqual(32f, SteeringInput.InchesToPixels(SteeringInput.MaxRadiusInches, 0f), 1e-4f, "0.20 in at 160 dpi");
            Assert.AreEqual(28f, SteeringInput.InchesToPixels(SteeringInput.DeadZoneInches, 1000f), 1e-4f, "clamped to 560 dpi");
            Assert.AreEqual(24f, SteeringInput.InchesToPixels(SteeringInput.MaxRadiusInches, 96f), 1e-4f, "clamped to 120 dpi");
        }

        [Test]
        public void Input_StickInsideTheDeadZoneKeepsTheCourse()
        {
            var anchor = new Vector2(100f, 200f);
            Assert.IsFalse(SteeringInput.StepStick(ref anchor, new Vector2(107.9f, 200f), 8f, 32f, out _), "7.9 px < 8 px");
            Assert.AreEqual(new Vector2(100f, 200f), anchor, "the anchor does not move inside the leash");
            Assert.IsFalse(SteeringInput.StepStick(ref anchor, anchor, 8f, 32f, out _), "no movement");
        }

        [Test]
        public void Input_StickHeadingIsAtan2OfTheDelta()
        {
            var anchor = new Vector2(100f, 200f);
            Assert.IsTrue(SteeringInput.StepStick(ref anchor, new Vector2(108f, 200f), 8f, 32f, out double h), "exactly the dead zone steers");
            Assert.AreEqual(0.0, h, 1e-6);
            anchor = new Vector2(100f, 200f);
            Assert.IsTrue(SteeringInput.StepStick(ref anchor, new Vector2(100f, 220f), 8f, 32f, out h));
            Assert.AreEqual(Math.PI * 0.5, h, 1e-6, "screen up = world up");
            anchor = new Vector2(100f, 200f);
            Assert.IsTrue(SteeringInput.StepStick(ref anchor, new Vector2(90f, 190f), 8f, 32f, out h));
            Assert.AreEqual(-Math.PI * 0.75, h, 1e-6, "down-left diagonal");
            Assert.AreEqual(new Vector2(100f, 200f), anchor, "inside the leash the anchor stays");
        }

        [Test]
        public void Input_StickLeashDragsTheAnchor()
        {
            var anchor = new Vector2(0f, 0f);
            Assert.IsTrue(SteeringInput.StepStick(ref anchor, new Vector2(30f, 40f), 8f, 32f, out double h));
            Assert.AreEqual(Math.Atan2(40.0, 30.0), h, 1e-6, "heading from the original delta");
            Assert.AreEqual(32f, (new Vector2(30f, 40f) - anchor).magnitude, 1e-3f, "anchor at MaxRadius behind the finger");
            Assert.AreEqual(30f - 32f * 0.6f, anchor.x, 1e-3f);
            Assert.AreEqual(40f - 32f * 0.8f, anchor.y, 1e-3f);

            // A reversal after the leash turns the pawn at once: the anchor is only 32 px behind.
            Vector2 finger = new Vector2(30f, 40f) - new Vector2(0.6f, 0.8f) * 42f;   // 10 px beyond the anchor, other side
            Assert.IsTrue(SteeringInput.StepStick(ref anchor, finger, 8f, 32f, out h));
            Assert.AreEqual(Math.Atan2(-0.8, -0.6), h, 1e-4, "reversed");
        }

        [Test]
        public void Input_KeyboardGivesEightDirections()
        {
            Assert.IsNull(SteeringInput.KeyboardHeading(false, false, false, false));
            Assert.IsNull(SteeringInput.KeyboardHeading(true, true, false, false), "opposite keys cancel");
            Assert.IsNull(SteeringInput.KeyboardHeading(false, false, true, true), "opposite keys cancel");
            Assert.AreEqual(0.0, SteeringInput.KeyboardHeading(false, false, false, true).Value, 1e-9, "right");
            Assert.AreEqual(Math.PI * 0.5, SteeringInput.KeyboardHeading(true, false, false, false).Value, 1e-9, "up");
            Assert.AreEqual(Math.PI, SteeringInput.KeyboardHeading(false, false, true, false).Value, 1e-9, "left");
            Assert.AreEqual(-Math.PI * 0.5, SteeringInput.KeyboardHeading(false, true, false, false).Value, 1e-9, "down");
            Assert.AreEqual(Math.PI * 0.25, SteeringInput.KeyboardHeading(true, false, false, true).Value, 1e-9, "up-right");
            Assert.AreEqual(Math.PI * 0.75, SteeringInput.KeyboardHeading(true, false, true, false).Value, 1e-9, "up-left");
            Assert.AreEqual(-Math.PI * 0.75, SteeringInput.KeyboardHeading(false, true, true, false).Value, 1e-9, "down-left");
            Assert.AreEqual(-Math.PI * 0.25, SteeringInput.KeyboardHeading(false, true, false, true).Value, 1e-9, "down-right");
            Assert.AreEqual(0.0, SteeringInput.KeyboardHeading(true, true, false, true).Value, 1e-9, "up+down cancel, right stays");
        }

        // ------------------------------------------------------------------------------------------------------------
        // Contract 13: mouse hover.

        [Test]
        public void Input_HoverDeadRadiusUsesTheCameraScale()
        {
            // 540 x 960 portrait: orthographicSize 16 (18 u wide), 960 px high -> 30 px per u -> 2.5 u = 75 px.
            float ortho = CameraRig.BaseOrthoSize(PortraitAspect);
            Assert.AreEqual(16f, ortho, 1e-4f);
            Assert.AreEqual(75f, SteeringInput.HoverDeadRadiusPixels(SteeringInput.HoverDeadRadius, ortho, 960f), 1e-3f);
            // Zoomed out to 26 u wide the same 2.5 u covers fewer pixels.
            float wide = CameraRig.OrthoSizeFor(PortraitAspect, CameraRig.MaxChaseScale);
            Assert.AreEqual(75f * 18f / 26f, SteeringInput.HoverDeadRadiusPixels(2.5f, wide, 960f), 1e-3f);
            Assert.IsTrue(float.IsPositiveInfinity(SteeringInput.HoverDeadRadiusPixels(2.5f, 0f, 960f)), "no camera, no hover");
        }

        [Test]
        public void Input_HoverSteersOnlyBeyondTheDeadRadius()
        {
            var pawn = new Vector2(270f, 480f);
            Assert.IsFalse(SteeringInput.HoverHeading(pawn, pawn + new Vector2(75f, 0f), 75f, out _), "exactly 2.5 u does not steer");
            Assert.IsFalse(SteeringInput.HoverHeading(pawn, pawn + new Vector2(30f, 40f), 75f, out _), "inside");
            Assert.IsTrue(SteeringInput.HoverHeading(pawn, pawn + new Vector2(0f, 75.5f), 75f, out double h));
            Assert.AreEqual(Math.PI * 0.5, h, 1e-6, "toward the cursor");
            Assert.IsTrue(SteeringInput.HoverHeading(pawn, pawn + new Vector2(-100f, -100f), 75f, out h));
            Assert.AreEqual(-Math.PI * 0.75, h, 1e-6);
        }

        [Test]
        public void Input_HoverArmsAfterEightPixels()
        {
            var origin = new Vector2(500f, 500f);
            Assert.IsFalse(SteeringInput.IsHoverArmed(origin, origin));
            Assert.IsFalse(SteeringInput.IsHoverArmed(origin, origin + new Vector2(7.9f, 0f)));
            Assert.IsFalse(SteeringInput.IsHoverArmed(origin, origin + new Vector2(5f, 6f)), "7.8 px");
            Assert.IsTrue(SteeringInput.IsHoverArmed(origin, origin + new Vector2(8f, 0f)));
            Assert.IsTrue(SteeringInput.IsHoverArmed(origin, origin + new Vector2(-6f, -6f)), "8.49 px");
        }

        // ------------------------------------------------------------------------------------------------------------
        // Contract 14: view size.

        [Test]
        public void Camera_PortraitShows18UnitsWideAndLandscape20UnitsHigh()
        {
            Assert.AreEqual(16f, CameraRig.BaseOrthoSize(PortraitAspect), 1e-4f, "540 x 960: 9 / 0.5625");
            Assert.AreEqual(18f, CameraRig.ViewWidthFor(PortraitAspect, 1f), 1e-4f);
            Assert.AreEqual(18f, CameraRig.ViewWidthFor(1f, 1f), 1e-4f, "square counts as portrait");
            Assert.AreEqual(10f, CameraRig.BaseOrthoSize(16f / 9f), 1e-4f, "landscape: 20 u high");
            Assert.AreEqual(26f, CameraRig.ViewWidthFor(PortraitAspect, CameraRig.MaxChaseScale), 1e-3f);
            Assert.AreEqual(16f, CameraRig.BaseOrthoSize(0f), 1e-4f, "unknown aspect falls back to 9:16");
        }

        // ------------------------------------------------------------------------------------------------------------
        // Contract 14: springs.

        [TestCase(CameraRig.FollowHalfLife)]
        [TestCase(CameraRig.LookaheadHalfLife)]
        [TestCase(CameraRig.AttractHalfLife)]
        public void Camera_CriticalSpringCoversHalfTheDistanceInOneHalfLife(float halfLife)
        {
            float x = 10f, v = 0f;
            CameraRig.CriticalSpring(ref x, ref v, 0f, halfLife, halfLife);
            Assert.AreEqual(5f, x, 1e-3f, "half way after one half-life");
            Assert.That(v, Is.LessThan(0f), "still moving toward the target");
            for (int k = 0; k < 40; k++) CameraRig.CriticalSpring(ref x, ref v, 0f, halfLife, halfLife);
            Assert.AreEqual(0f, x, 1e-3f, "settles");
        }

        [Test]
        public void Camera_CriticalSpringNeverOvershootsAndIsFrameRateIndependent()
        {
            const float halfLife = CameraRig.FollowHalfLife;
            float coarseX = 3f, coarseV = 0f;
            CameraRig.CriticalSpring(ref coarseX, ref coarseV, 0f, halfLife, 0.3f);
            float fineX = 3f, fineV = 0f;
            float minX = float.MaxValue;
            for (int k = 0; k < 300; k++)
            {
                CameraRig.CriticalSpring(ref fineX, ref fineV, 0f, halfLife, 0.001f);
                minX = Mathf.Min(minX, fineX);
            }
            Assert.AreEqual(coarseX, fineX, 1e-4f, "one 0.3 s step equals 300 steps of 1 ms");
            Assert.AreEqual(coarseV, fineV, 1e-3f);
            Assert.That(minX, Is.GreaterThanOrEqualTo(0f), "critically damped: no overshoot");
        }

        [Test]
        public void Camera_SpringFollowsAMovingTargetWithBoundedLag()
        {
            // The human moves at PawnSpeed = 6 u/s; the 0.12 s follow lags by 2 v / y (about 0.86 u), well inside the view.
            const float speed = 6f, dt = 1f / 60f;
            Vector2 x = Vector2.zero, v = Vector2.zero;
            for (int k = 1; k <= 600; k++) CameraRig.CriticalSpring(ref x, ref v, new Vector2(speed * k * dt, 0f), CameraRig.FollowHalfLife, dt);
            float lag = speed * 600 * dt - x.x;
            float expected = 2f * speed * CameraRig.FollowHalfLife / CameraRig.SpringHalfLifeConstant;
            Assert.AreEqual(expected, lag, 0.11f, "steady lag about 2 v / y (minus about half a frame of target motion)");
            Assert.That(lag, Is.LessThan(1f));
        }

        [Test]
        public void Camera_ExpApproachAndSmoothReturn()
        {
            Assert.AreEqual(1.5f, CameraRig.ExpApproach(1f, 2f, CameraRig.ChaseInHalfLife, CameraRig.ChaseInHalfLife), 1e-5f, "chase ease-in half-life");
            float a = 1f;
            for (int k = 0; k < 25; k++) a = CameraRig.ExpApproach(a, 2f, 0.25f, 0.01f);
            Assert.AreEqual(1.5f, a, 1e-4f, "subdivision independent");
            Assert.AreEqual(2f, CameraRig.ExpApproach(1f, 2f, 0f, 0.01f), "zero half-life snaps");
            float from = CameraRig.MaxChaseScale;
            Assert.AreEqual(from, CameraRig.SmoothReturn(from, 1f, 0f, CameraRig.ChaseOutSeconds), 1e-6f);
            Assert.AreEqual((from + 1f) * 0.5f, CameraRig.SmoothReturn(from, 1f, 0.3f, CameraRig.ChaseOutSeconds), 1e-5f, "half way at half time");
            Assert.AreEqual(1f, CameraRig.SmoothReturn(from, 1f, 0.6f, CameraRig.ChaseOutSeconds), 1e-6f, "back to 18 u after 0.6 s");
            Assert.AreEqual(1f, CameraRig.SmoothReturn(from, 1f, 5f, CameraRig.ChaseOutSeconds), 1e-6f);
        }

        [Test]
        public void Camera_AttractScaleTargetZoomsOutTheMenuMatch()
        {
            // Wave C (feel-06): the attract match behind the menu eases to view scale 1.4 (25.2 u wide in 9:16).
            Assert.AreEqual(1.4f, CameraRig.AttractZoom, 1e-6f);
            Assert.AreEqual(CameraRig.AttractZoom, CameraRig.ZoomTargetFor(CameraMode.Attract), 1e-6f);
            Assert.AreEqual(CameraRig.ResultsZoom, CameraRig.ZoomTargetFor(CameraMode.ResultsHold), 1e-6f);
            Assert.AreEqual(1f, CameraRig.ZoomTargetFor(CameraMode.Follow), 1e-6f);
            Assert.AreEqual(1f, CameraRig.ZoomTargetFor(CameraMode.DeathHold), 1e-6f);
            Assert.AreEqual(1f, CameraRig.ZoomTargetFor(CameraMode.Chase), 1e-6f, "the chase scale is computed on top of 1");
            Assert.AreEqual(25.2f, CameraRig.ViewWidthFor(PortraitAspect, CameraRig.AttractZoom), 1e-3f);
            // From the play view the attract zoom is reached with the non-chase ease (half way after one half-life).
            float s = CameraRig.ExpApproach(1f, CameraRig.AttractZoom, CameraRig.ResultsZoomHalfLife, CameraRig.ResultsZoomHalfLife);
            Assert.AreEqual(1.2f, s, 1e-4f);
            // The zoomed-out view still fits the 4 u overscan clamp on 9:16, 21:9 and landscape (no forced centering).
            foreach (float aspect in new[] { PortraitAspect, 1080f / 2520f, 1280f / 720f })
            {
                float ortho = CameraRig.OrthoSizeFor(aspect, CameraRig.AttractZoom);
                Assert.That(ortho, Is.LessThan(36f), "half height at aspect " + aspect);
                Assert.That(ortho * aspect, Is.LessThan(36f), "half width at aspect " + aspect);
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Contract 14: chase framing.

        [Test]
        public void Camera_ChaseFramingStaysAt18WhenEverythingIsClose()
        {
            Vector2 c = Vector2.zero;
            float w = CameraRig.ChaseViewWidth(c, c, new Vector2(2f, 1f), true, new Vector2(-1f, -2f), PortraitAspect);
            Assert.AreEqual(18f, w, 1e-4f, "1.15 x 7 u < 18 u");
        }

        [Test]
        public void Camera_ChaseFramingIs115TimesTheNeededWidth()
        {
            Vector2 c = Vector2.zero;
            // Horizontal spread: front 8 u to the right, home 2 u to the left: needed half width 8 + 1.5 -> width 19.
            float w = CameraRig.ChaseViewWidth(c, c, new Vector2(8f, 0f), true, new Vector2(-2f, 0f), PortraitAspect);
            Assert.AreEqual(1.15f * 19f, w, 1e-3f);
            // The home target can be the farthest point.
            w = CameraRig.ChaseViewWidth(c, c, new Vector2(1f, 0f), true, new Vector2(-9f, 0f), PortraitAspect);
            Assert.AreEqual(1.15f * 21f, w, 1e-3f);
            // Without a home target only the head and the front count.
            w = CameraRig.ChaseViewWidth(c, c, new Vector2(1f, 0f), false, new Vector2(-9f, 0f), PortraitAspect);
            Assert.AreEqual(18f, w, 1e-4f);
        }

        [Test]
        public void Camera_ChaseFramingAccountsForTheVerticalExtentThroughTheAspect()
        {
            // Portrait 540 x 960: the base view is 18 x 32 u. A front 20 u below needs a half height of 21.5 u, i.e. a view
            // 43 u high = 24.19 u wide; x 1.15 = 27.8 u -> clamped to 26.
            Vector2 c = Vector2.zero;
            float w = CameraRig.ChaseViewWidth(c, c, new Vector2(0f, -20f), false, c, PortraitAspect);
            Assert.AreEqual(26f, w, 1e-3f, "clamped at 26");
            // 14 u below: half height 15.5 -> 31 u high = 17.44 u wide; x 1.15 = 20.05 u.
            w = CameraRig.ChaseViewWidth(c, c, new Vector2(0f, -14f), false, c, PortraitAspect);
            Assert.AreEqual(1.15f * 31f * PortraitAspect, w, 1e-3f);
        }

        [Test]
        public void Camera_ChaseFramingIsClampedBetween18And26()
        {
            Vector2 c = new Vector2(10f, -5f);
            float far = CameraRig.ChaseViewWidth(c, c, c + new Vector2(30f, 0f), true, c - new Vector2(0f, 30f), PortraitAspect);
            Assert.AreEqual(CameraRig.ChaseMaxWidth, far, 1e-3f);
            float scale = CameraRig.ChaseScale(c, c, c + new Vector2(30f, 0f), false, c, PortraitAspect);
            Assert.AreEqual(26f / 18f, scale, 1e-5f);
            Assert.AreEqual(1f, CameraRig.ChaseScale(c, c, c, false, c, PortraitAspect), 1e-6f);
        }

        [Test]
        public void Camera_ChaseFramingInLandscapeScalesThe20UnitHeight()
        {
            const float aspect = 16f / 9f;
            Vector2 c = Vector2.zero;
            // Front 10 u above: half height 11.5 -> 23 u; x 1.15 = 26.45 u high -> scale 1.3225 of the 20 u base.
            float scale = CameraRig.ChaseScale(c, c, new Vector2(0f, 10f), false, c, aspect);
            Assert.AreEqual(1.15f * 23f / 20f, scale, 1e-4f);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Contract 14: arena clamp.

        [Test]
        public void Camera_ClampKeepsTheViewWithin4UnitsOfTheArena()
        {
            // Portrait base view: half extents 9 x 16. The limit is 32 + 4 = 36.
            Vector2 p = CameraRig.ClampCenter(new Vector2(31f, -30f), 9f, 16f);
            Assert.AreEqual(27f, p.x, 1e-4f, "36 - 9");
            Assert.AreEqual(-20f, p.y, 1e-4f, "-36 + 16");
            p = CameraRig.ClampCenter(new Vector2(5f, 7f), 9f, 16f);
            Assert.AreEqual(new Vector2(5f, 7f), p, "inside: untouched");
            p = CameraRig.ClampCenter(new Vector2(-40f, 40f), 13f, 23.1f);
            Assert.AreEqual(-23f, p.x, 1e-4f);
            Assert.AreEqual(12.9f, p.y, 1e-4f);
            p = CameraRig.ClampCenter(new Vector2(10f, 10f), 40f, 10f);
            Assert.AreEqual(0f, p.x, 1e-6f, "a view wider than the limit is centered");
            Assert.AreEqual(10f, p.y, 1e-6f);
        }

        [Test]
        public void Camera_ClampAtTheWidestChaseViewStillCoversOnlyTheCompositeQuad()
        {
            // The composite quad covers [-40, 40]^2 (contract 12.2): any clamped view stays inside it.
            float ortho = CameraRig.OrthoSizeFor(PortraitAspect, CameraRig.MaxChaseScale);
            float halfW = ortho * PortraitAspect;
            foreach (Vector2 want in new[] { new Vector2(100f, 100f), new Vector2(-100f, 3f), new Vector2(0f, -100f) })
            {
                Vector2 p = CameraRig.ClampCenter(want, halfW, ortho);
                Assert.That(Mathf.Abs(p.x) + halfW, Is.LessThanOrEqualTo(36f + 1e-3f));
                Assert.That(Mathf.Abs(p.y) + ortho, Is.LessThanOrEqualTo(36f + 1e-3f));
            }
        }
    }
}
