using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;
using Object = UnityEngine.Object;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Step 74 (title chair, 2026-11-19), on the real Boot scene: the baked title logo (TitleLogo), the red chair standing
    /// in a soft warm pool of light on the floor that holds its short shadow, framed a little right of the column's margin.
    /// Checks the bake, the pool (lit, soft edged, fading to nothing before the frame's edges) and the shadow inside it,
    /// the logo's fit on a 20:9 phone, then (2026-11-20, reworked 2026-11-21) the loop: still in the light most of the
    /// time, hopping off to the right while the spot looks away to the left, caught and gliding home slowly in the light,
    /// seamless, and clear of the screen's top and the title's letters.
    /// Shots go to the folder in the OOS_SHOT_DIR environment variable, or to Build/shots/titlechair (never under docs/).
    /// </summary>
    public sealed class ProbeTestsTitleChair
    {
        // A 20:9 phone at the menu's CanvasScaler (1920 x 1080 reference, match 0.5): 966 reference units high.
        private const float PhoneHalfHeight = 966f / 2f;

        private static string ShotDir
        {
            get
            {
                string dir = Environment.GetEnvironmentVariable("OOS_SHOT_DIR");
                return string.IsNullOrEmpty(dir) ? "Build/shots/titlechair" : dir;
            }
        }

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private Texture2D lastShot;
        private Menu Menu => main.Menu;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.IsNotNull(Menu, "premise: Main built no Menu");
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Application.logMessageReceived -= OnLog;
            if (lastShot != null)
            {
                Object.Destroy(lastShot);
                lastShot = null;
            }
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
            }
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            Cursor.lockState = CursorLockMode.None;
            yield return null;
        }

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                exceptions++;
                logged.Add(condition);
            }
        }

        /// <summary>Opens the title page and waits for the logo's bake and fade in.</summary>
        private IEnumerator BakedLogo(Action<TitleLogo> found)
        {
            Strings.SetLanguage(Strings.French);
            Menu.ShowTitle();
            TitleLogo logo = Menu.GetComponentInChildren<TitleLogo>(true);
            Assert.IsNotNull(logo, "the title has no TitleLogo");
            // GRIP: the bake now renders and composes the dog's and the human's frames too: wait in real time, not frames.
            float bakeStart = Time.realtimeSinceStartup;
            while (!logo.Ready && Time.realtimeSinceStartup - bakeStart < 30f)
            {
                yield return null;
            }
            Assert.IsTrue(logo.Ready, "the title logo was never baked");
            // The fade in.
            for (float t = 0f; t < 0.8f; t += Time.unscaledDeltaTime)
            {
                yield return null;
            }
            Assert.IsNotNull(logo.Chair, "premise: the logo has no chair layer");
            Assert.IsNotNull(logo.Shadow, "premise: the logo has no shadow layer");
            found(logo);
        }

        [UnityTest]
        public IEnumerator Step74a_TitleChairStandsInAPoolOfLight()
        {
            TitleLogo logo = null;
            yield return BakedLogo(l => logo = l);
            // The still pose, in the light (the loop is held there for the shots and the look checks).
            logo.Pin(0f);
            Color32[] pixels = logo.RestFrame();
            Assert.IsNotNull(pixels, "premise: the logo's rest frame cannot be read");
            int w = Tuning.TitleLogoWidth;
            int h = Tuning.TitleLogoHeight;
            Assert.AreEqual(w * h, pixels.Length, "premise: the rest frame is not the logo's frame");
            // The shots first, so a failing look check still leaves the pictures to look at.
            Directory.CreateDirectory(ShotDir);
            var still = new Texture2D(w, h, TextureFormat.RGBA32, false);
            still.SetPixels32(pixels);
            still.Apply();
            File.WriteAllBytes(Path.Combine(ShotDir, "title_chair_logo.png"), still.EncodeToPNG());
            Object.Destroy(still);
            yield return Shoot("title_chair_1920x1080.png", 1920, 1080);
            yield return Shoot("title_chair_2400x1080.png", 2400, 1080);

            // Nothing at the frame's edges: the pool fades out inside it, never cut by the image's frame.
            float edge = 0f;
            for (int x = 0; x < w; x++)
            {
                edge = Mathf.Max(edge, Mathf.Max(pixels[x].a, pixels[(h - 1) * w + x].a));
            }
            for (int y = 0; y < h; y++)
            {
                edge = Mathf.Max(edge, Mathf.Max(pixels[y * w].a, pixels[y * w + w - 1].a));
            }
            Assert.Less(edge, 8f, "the logo is cut by its frame (alpha on its border)");

            // The pool: a lit warm centre, the shadow darker inside it, a soft edge (many partly covering pixels).
            Vector2Int centre = logo.PoolPixel;
            Vector2Int shadow = logo.ShadowPixel;
            Color pool = pixels[centre.y * w + centre.x];
            Color dark = pixels[shadow.y * w + shadow.x];
            TestContext.WriteLine($"[Step74a] pool {centre} {pool}, shadow {shadow} {dark}, least pool light under the shadow {logo.ShadowInPool:0.00}");
            Assert.Greater(logo.ShadowInPool, 0.2f, "part of the chair's shadow falls outside the pool of light");
            Assert.Greater(pool.a, 0.5f, "the pool of light is not there under the chair");
            Assert.Greater(pool.r, pool.b + 0.15f, "the pool of light is not warm");
            Assert.Greater(pool.r * 0.3f + pool.g * 0.59f + pool.b * 0.11f, 0.55f, "the pool does not read as light");
            Assert.Greater(dark.a, 0.5f, "the shadow falls outside the pool of light");
            float poolLuma = pool.r * 0.3f + pool.g * 0.59f + pool.b * 0.11f;
            float darkLuma = dark.r * 0.3f + dark.g * 0.59f + dark.b * 0.11f;
            Assert.Less(darkLuma, poolLuma * 0.75f, "the chair's shadow does not show in the pool");
            int soft = 0;
            foreach (Color32 p in pixels)
            {
                if (p.a > 20 && p.a < 200)
                {
                    soft++;
                }
            }
            Assert.Greater(soft, w * h / 20, "the pool's edge is not soft");

            // On screen on a 20:9 phone: the logo's chair and pool stay below the top edge.
            var rect = logo.Image.rectTransform;
            float top = rect.anchoredPosition.y + rect.sizeDelta.y * (1f - rect.pivot.y);
            int firstRow = h;
            for (int y = h - 1; y >= 0 && firstRow == h; y--)
            {
                for (int x = 0; x < w; x++)
                {
                    if (pixels[y * w + x].a > 8)
                    {
                        firstRow = y;
                        break;
                    }
                }
            }
            float drawnTop = top - rect.sizeDelta.y * (h - 1 - firstRow) / h;
            TestContext.WriteLine($"[Step74a] logo top {top:0}, drawn top {drawnTop:0} reference units");
            Assert.Less(drawnTop, PhoneHalfHeight - 4f, "the chair leaves the top of a 20:9 phone");
            logo.Unpin();
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// The loop (2026-11-20, reworked 2026-11-21; GRIP 2026-11-22: two loops that alternate): the choreography itself
        /// (TitleLogo.Sample) is still in the full light for at least 15 s; then the spot slides away to the left, the chair
        /// hops off to the right in a few gentle hops only once the light has left it, the light comes back onto it, it jumps
        /// once, startled. In the first loop the dog trots in from the left edge, bites the chair's leg (its head lowered) and
        /// drags it home; in the second a human walks in from the left edge, puts his hands on the backrest's top rail and
        /// pulls it home; in the full light that follows it (the only way it comes back); then the carrier lets go and leaves
        /// through the left edge; every value continuous, each loop ending exactly where it started. On the title page, the
        /// chair's picture only slides sideways and lifts (its shadow stays on the floor, its shape never changes), the chair,
        /// the dog and the human never reach the top of a 20:9 phone or the title's letters, and the carriers, once fully
        /// visible, stay inside the frame. Writes a frame sequence across both loops and the menu at their key moments.
        /// </summary>
        [UnityTest]
        public IEnumerator Step74b_TitleChairHopsAndTheDogOrAHumanBringsItBack()
        {
            // The choreography, sampled finely over both loops (the dog's, then the human's).
            const int samples = 12000;
            Assert.AreEqual(TitleLogo.Rest, TitleLogo.Sample(0f), "the loop does not start on the still pose");
            Assert.AreEqual(TitleLogo.Rest, TitleLogo.Sample(1f), "the human's loop does not start on the still pose");
            Assert.AreEqual(TitleLogo.Rest, TitleLogo.Sample(2f), "the two loops' end is not their start");
            foreach (float last in new[] { 1f - 1e-5f, 2f - 1e-5f })
            {
                TitleLogo.Pose end = TitleLogo.Sample(last);
                float gap = Mathf.Abs(end.Chair) + Mathf.Abs(end.Spot) + Mathf.Abs(end.Lean) * 0.01f + (1f - end.Light) + end.Hop + end.DogAlpha + end.HumanAlpha;
                Assert.Less(gap, 1e-3f, $"the loop does not come back to its start just before it ends ({last:0.00000}): " + end);
            }
            int still = 0;
            int hops = 0;
            int startles = 0;
            float farthest = 0f;
            float highestHop = 0f;
            float startleTop = 0f;
            float maxStep = 0f;
            float maxLight = 0f;
            float maxBody = 0f;
            float mostDog = 0f;
            float mostHuman = 0f;
            bool dogTurns = false;
            bool humanTurns = false;
            bool dragged = false;
            bool pulled = false;
            bool bit = false;
            TitleLogo.Pose previous = TitleLogo.Sample(0f);
            for (int i = 1; i <= samples; i++)
            {
                float u = 2f * i / samples;
                TitleLogo.Pose pose = TitleLogo.Sample(u);
                if (pose.Equals(TitleLogo.Rest))
                {
                    still++;
                }
                float step = pose.Chair - previous.Chair;
                if (step > 0f)
                {
                    // Off to the right only once the spot has mostly left it.
                    Assert.Less(pose.Light, 0.5f, $"the chair moves off while the spot is still on it at {u:0.0000}: {pose}");
                }
                else if (step < 0f)
                {
                    // Home only in the dog's mouth or the human's hands, in the full light that follows it.
                    bool byDog = previous.Dog == previous.Chair && previous.DogAlpha >= 1f && previous.DogBite;
                    bool byHuman = previous.Holding && previous.Human == previous.Chair && previous.HumanAlpha >= 1f;
                    Assert.IsTrue(byDog || byHuman, $"the chair comes home with nobody holding it at {u:0.0000}: {pose}");
                    Assert.IsTrue(previous.Light >= 1f && previous.Spot == previous.Chair, $"the chair is brought home out of the light at {u:0.0000}: {previous}");
                    dragged |= byDog;
                    pulled |= byHuman;
                }
                bool nobody = pose.DogAlpha == 0f && pose.HumanAlpha == 0f;
                if (pose.Hop > 0f && previous.Hop == 0f)
                {
                    if (pose.Light < 0.5f)
                    {
                        hops++;
                    }
                    else if (nobody)
                    {
                        // Caught in the light, before the carrier comes: the startled jump, on the spot.
                        startles++;
                    }
                }
                if (pose.Light < 0.5f)
                {
                    highestHop = Mathf.Max(highestHop, pose.Hop);
                }
                else if (nobody)
                {
                    startleTop = Mathf.Max(startleTop, pose.Hop);
                }
                Assert.IsFalse(pose.DogAlpha > 0f && pose.HumanAlpha > 0f, $"the dog and the human show together at {u:0.0000}: {pose}");
                if (pose.DogAlpha > 0f)
                {
                    // The dog shows up only once the light has caught the chair, and is opaque only well inside the frame.
                    Assert.GreaterOrEqual(pose.Light, 1f, $"the dog comes while the spot is away at {u:0.0000}: {pose}");
                    if (pose.DogAlpha >= 1f)
                    {
                        Assert.GreaterOrEqual(pose.Dog, TitleLogo.DogEdge + Tuning.TitleLogoDogFade - 1e-4f, $"the dog is opaque across the frame's edge at {u:0.0000}: {pose}");
                    }
                    dogTurns |= pose.DogFacing < 0f;
                    bit |= pose.DogBite;
                }
                else
                {
                    Assert.IsFalse(pose.DogBite, $"a hidden dog bites at {u:0.0000}: {pose}");
                    // Never a tilt without the dog (the hops, the startle and the human's pull keep the chair upright).
                    Assert.AreEqual(0f, pose.Lean, $"the chair tilts with no dog at {u:0.0000}: {pose}");
                }
                if (pose.HumanAlpha > 0f)
                {
                    Assert.GreaterOrEqual(pose.Light, 1f, $"the human comes while the spot is away at {u:0.0000}: {pose}");
                    if (pose.HumanAlpha >= 1f)
                    {
                        Assert.GreaterOrEqual(pose.Human, TitleLogo.HumanEdge + Tuning.TitleLogoDogFade - 1e-4f, $"the human is opaque across the frame's edge at {u:0.0000}: {pose}");
                    }
                    if (pose.Holding)
                    {
                        // His picture holds the chair's: it must lie exactly on the chair's layer.
                        Assert.AreEqual(pose.Chair, pose.Human, 1e-6f, $"the human holds the chair away from it at {u:0.0000}: {pose}");
                        Assert.AreEqual(0f, pose.Hop, $"the chair lifts in the human's hands at {u:0.0000}: {pose}");
                        Assert.AreEqual(0f, pose.HumanHop, $"the human bobs while he holds the chair at {u:0.0000}: {pose}");
                    }
                    humanTurns |= pose.HumanFacing < 0f;
                }
                else
                {
                    Assert.IsFalse(pose.Holding, $"a hidden human holds the chair at {u:0.0000}: {pose}");
                }
                Assert.LessOrEqual(Mathf.Abs(pose.Lean), Tuning.TitleLogoDragWobble + 1e-4f, $"the chair tilts too far at {u:0.0000}: {pose}");
                float dogStep = pose.DogAlpha > 0f && previous.DogAlpha > 0f ? Mathf.Abs(pose.Dog - previous.Dog) : 0f;
                float humanStep = pose.HumanAlpha > 0f && previous.HumanAlpha > 0f ? Mathf.Abs(pose.Human - previous.Human) : 0f;
                maxStep = Mathf.Max(maxStep, Mathf.Max(Mathf.Abs(step), Mathf.Max(Mathf.Abs(pose.Spot - previous.Spot), Mathf.Max(Mathf.Abs(pose.Hop - previous.Hop), Mathf.Max(dogStep, humanStep)))));
                maxLight = Mathf.Max(maxLight, Mathf.Max(Mathf.Abs(pose.Light - previous.Light), Mathf.Max(Mathf.Abs(pose.DogAlpha - previous.DogAlpha), Mathf.Abs(pose.HumanAlpha - previous.HumanAlpha))));
                maxBody = Mathf.Max(maxBody, Mathf.Max(Mathf.Abs(pose.Lean - previous.Lean), Mathf.Abs(pose.DogWag - previous.DogWag)) * 0.01f);
                farthest = Mathf.Max(farthest, pose.Chair);
                mostDog = Mathf.Max(mostDog, pose.DogAlpha);
                mostHuman = Mathf.Max(mostHuman, pose.HumanAlpha);
                previous = pose;
            }
            float stillShare = still / (float)samples;
            float loopSeconds = Tuning.TitleLogoCycleSeconds;
            TestContext.WriteLine($"[Step74b] loop {loopSeconds:0.0} s: still {stillShare:P1} ({stillShare * loopSeconds:0.0} s), act {(1f - stillShare) * loopSeconds:0.0} s; "
                + $"{hops} hops up to {highestHop:0.000} m, {startles} startled jumps up to {startleTop:0.000} m over both loops; farthest {farthest:0.000} m right; "
                + $"largest step {maxStep:0.0000} m, light {maxLight:0.0000}, tilt {maxBody * 100f:0.00} deg per 1/{samples / 2} loop; human root {TitleLogo.HumanRoot}, edge {TitleLogo.HumanEdge:0.000}");
            Assert.GreaterOrEqual(stillShare * loopSeconds, 14.95f, "the still pose does not hold 15 s after the chair is back");
            Assert.That((1f - stillShare) * loopSeconds, Is.InRange(8f, 13f), "the act does not last about 11 s");
            Assert.Less(maxStep, 0.02f, "the loop jumps (chair, spot, hop, dog or human)");
            Assert.Less(maxLight, 0.03f, "the light or a carrier's fade jumps");
            Assert.Less(maxBody, 0.03f, "the chair's tilt or the dog's wag jumps");
            Assert.AreEqual(2 * Tuning.TitleLogoChairHops, hops, "the chair does not make its hops in the dark in both loops");
            Assert.AreEqual(2, startles, "the chair does not jump exactly once per loop when the light catches it");
            Assert.Greater(highestHop, 0.02f, "the hops do not leave the floor");
            Assert.Greater(startleTop, highestHop, "the startled jump is not higher than the hops");
            Assert.Greater(farthest, 0.25f, "the chair barely moves");
            Assert.IsTrue(dragged, "the dog never drags the chair home");
            Assert.IsTrue(bit, "the dog never bites the chair's leg");
            Assert.IsTrue(pulled, "the human never pulls the chair home");
            Assert.AreEqual(1f, mostDog, "the dog never fully shows");
            Assert.AreEqual(1f, mostHuman, "the human never fully shows");
            Assert.IsTrue(dogTurns, "the dog never turns round to leave");
            Assert.IsTrue(humanTurns, "the human never turns round to leave");

            TitleLogo logo = null;
            yield return BakedLogo(l => logo = l);
            Assert.IsNotNull(logo.Dog, "the dog was not baked (see the [TitleLogo] warning)");
            Assert.IsNotNull(logo.DogShadow, "premise: the dog has no shadow layer");
            Assert.IsNotNull(logo.Human, "the human was not baked (see the [TitleLogo] warning)");
            Assert.IsNotNull(logo.HumanPair, "premise: the human has no pair layer");
            Assert.IsNotNull(logo.HumanShadow, "premise: the human has no shadow layer");
            RectTransform canvas = (RectTransform)Menu.GetComponent<Canvas>().transform;
            RectTransform chair = logo.Chair.rectTransform;
            RectTransform shadow = logo.Shadow.rectTransform;
            RectTransform dog = logo.Dog.rectTransform;
            RectTransform human = logo.Human.rectTransform;
            RectTransform pair = logo.HumanPair.rectTransform;
            RectTransform frame = logo.Image.rectTransform;

            // The title's letters: the top of the highest glyph, in the menu canvas's reference units.
            Assert.IsTrue(Menu.Labels.TryGetValue("Title", out Text title), "premise: no title label");
            Canvas.ForceUpdateCanvases();
            float glyphTop = float.MinValue;
            foreach (UIVertex v in title.cachedTextGenerator.verts)
            {
                Vector3 local = new Vector3(v.position.x, v.position.y, 0f) / title.pixelsPerUnit;
                glyphTop = Mathf.Max(glyphTop, canvas.InverseTransformPoint(title.rectTransform.TransformPoint(local)).y);
            }
            Assert.Greater(glyphTop, float.MinValue, "premise: the title has no glyphs");

            // The chair, the dog and the human through both acts: sideways on the floor plus their lifts, under the top of a
            // 20:9 phone, above the letters; the chair's shadow stays on the floor line, the chair keeps its shape; the
            // carriers, opaque, stay inside the logo's frame (at rest).
            logo.Pin(0f);
            var corners = new Vector3[4];
            frame.GetWorldCorners(corners);
            float frameLeft = canvas.InverseTransformPoint(corners[0]).x;
            float frameRight = canvas.InverseTransformPoint(corners[2]).x;
            float restY = canvas.InverseTransformPoint(chair.position).y;
            float shadowY = canvas.InverseTransformPoint(shadow.position).y;
            float top = float.MinValue;
            float bottom = float.MaxValue;
            float right = float.MinValue;
            float rightAtRest = float.MinValue;
            float topAtRest = float.MinValue;
            chair.GetWorldCorners(corners);
            foreach (Vector3 c in corners)
            {
                Vector3 p = canvas.InverseTransformPoint(c);
                rightAtRest = Mathf.Max(rightAtRest, p.x);
                topAtRest = Mathf.Max(topAtRest, p.y);
            }
            float dogTop = float.MinValue;
            float dogBottom = float.MaxValue;
            float dogLeft = float.MaxValue;
            float dogRight = float.MinValue;
            float humanTop = float.MinValue;
            float humanBottom = float.MaxValue;
            float humanLeft = float.MaxValue;
            float humanRight = float.MinValue;
            // Finely enough to catch each jump's top (the startled jump peaks within 0.1 s).
            const int steps = 1100;
            float act = 1f - Tuning.TitleLogoStillFraction;
            for (int loop = 0; loop < 2; loop++)
            {
                for (int k = 0; k <= steps; k++)
                {
                    logo.Pin(loop + Tuning.TitleLogoStillFraction + act * k / steps);
                    TitleLogo.Pose pose = logo.Current;
                    float y = canvas.InverseTransformPoint(chair.position).y;
                    Assert.AreEqual(restY + pose.Hop * logo.UiPerMetre, y, 0.01f, $"the chair leaves its line by more than its lift at loop {loop} step {k}: {pose}");
                    Assert.AreEqual(shadowY, canvas.InverseTransformPoint(shadow.position).y, 0.01f, $"the shadow leaves the floor at loop {loop} step {k}: {pose}");
                    Assert.AreEqual(Vector3.one, chair.localScale, $"the chair changes shape at loop {loop} step {k}: {pose}");
                    chair.GetWorldCorners(corners);
                    foreach (Vector3 c in corners)
                    {
                        Vector3 p = canvas.InverseTransformPoint(c);
                        top = Mathf.Max(top, p.y);
                        bottom = Mathf.Min(bottom, p.y);
                        right = Mathf.Max(right, p.x);
                    }
                    if (pose.DogAlpha > 0.01f)
                    {
                        Extent(dog, canvas, corners, pose.DogAlpha >= 0.99f, ref dogTop, ref dogBottom, ref dogLeft, ref dogRight);
                    }
                    if (pose.HumanAlpha > 0.01f)
                    {
                        Extent(pose.Holding ? pair : human, canvas, corners, pose.HumanAlpha >= 0.99f, ref humanTop, ref humanBottom, ref humanLeft, ref humanRight);
                        if (pose.Holding)
                        {
                            // The pair's chair lies on the chair's layer: same place.
                            Assert.AreEqual(logo.HumanPair.color.a, pose.HumanAlpha, 0.01f, $"the pair does not show while he holds the chair at step {k}: {pose}");
                            Assert.Less(logo.Human.color.a, 0.01f, $"the walking human shows while he holds the chair at step {k}: {pose}");
                        }
                    }
                }
            }
            float travel = right - rightAtRest;
            float screenRight = canvas.rect.width * 0.5f;
            TestContext.WriteLine($"[Step74b] chair between y {bottom:0.0} and {top:0.0} (at rest top {topAtRest:0.0}; title glyphs top {glyphTop:0.0}, phone top {PhoneHalfHeight:0}), "
                + $"travels {travel:0.0} units right, right edge {screenRight - right:0.0} from the screen's right; dog between y {dogBottom:0.0} and {dogTop:0.0}, "
                + $"opaque between x {dogLeft:0.0} and {dogRight:0.0}; human between y {humanBottom:0.0} and {humanTop:0.0}, opaque between x {humanLeft:0.0} "
                + $"and {humanRight:0.0} (frame {frameLeft:0.0} to {frameRight:0.0})");
            // (The layers' rects carry 2 transparent logo pixels, about 1.2 units, around their pictures.)
            Assert.Less(top, PhoneHalfHeight - 2f, "the jumping chair reaches the top of a 20:9 phone");
            Assert.Greater(bottom, glyphTop + 2f, "the moving chair touches the title's letters");
            Assert.Greater(travel, 20f, "the chair's motion is too small to read at the logo's size");
            Assert.Greater(screenRight - right, 16f, "the chair leaves the screen on the right");
            Assert.Less(dogTop, PhoneHalfHeight - 2f, "the dog reaches the top of a 20:9 phone");
            Assert.Greater(dogBottom, glyphTop + 2f, "the dog covers the title's letters");
            Assert.GreaterOrEqual(dogLeft, frameLeft - 2f, "the opaque dog leaves the logo's frame on the left");
            Assert.LessOrEqual(dogRight, frameRight + 2f, "the opaque dog leaves the logo's frame on the right");
            Assert.Less(humanTop, PhoneHalfHeight - 2f, "the human reaches the top of a 20:9 phone");
            Assert.Greater(humanBottom, glyphTop + 2f, "the human covers the title's letters");
            Assert.GreaterOrEqual(humanLeft, frameLeft - 2f, "the opaque human leaves the logo's frame on the left");
            Assert.LessOrEqual(humanRight, frameRight + 2f, "the opaque human leaves the logo's frame on the right");

            // Seamless on screen too: each loop's last moment draws what its first does.
            logo.Pin(0f);
            Vector3 first = chair.position;
            Vector3 firstFrame = frame.position;
            Color firstColour = logo.Chair.color;
            foreach (float last in new[] { 1f - 1e-5f, 2f - 1e-5f })
            {
                logo.Pin(last);
                Assert.Less(Vector3.Distance(first, chair.position), 0.05f, $"the chair is not back on its mark at the loop's end ({last:0.00000})");
                Assert.Less(Vector3.Distance(firstFrame, frame.position), 0.05f, "the light is not centred back on the mark at the loop's end");
                Assert.Less(Mathf.Abs(firstColour.r - logo.Chair.color.r), 0.01f, "the chair is not back in the full light at the loop's end");
                Assert.Less(logo.Dog.color.a, 0.01f, "the dog is still there at the loop's end");
                Assert.Less(logo.Human.color.a + logo.HumanPair.color.a, 0.01f, "the human is still there at the loop's end");
            }
            // In the dark, after its hops, it has moved right and darkened, with the pool dimmed away to the left.
            logo.Pin(Tuning.TitleLogoStillFraction + act * 0.29f);
            Assert.Greater(chair.position.x - first.x, 1f, "the chair does not hop off to the right during the act");
            Assert.Less(frame.position.x, firstFrame.x - 1f, "the light does not slide away to the left");
            Assert.Less(logo.Chair.color.r, 0.8f, "the chair does not darken out of the light");
            Assert.Less(logo.Image.color.a, 0.5f, "the pool of light does not dim while the spot is away");
            // Caught: the light is back on the chair where it stands, and it jumps.
            logo.Pin(Tuning.TitleLogoStillFraction + act * 0.37f);
            Assert.Greater(logo.Image.color.a, 0.99f, "the light does not come back onto the chair");
            Assert.AreEqual(chair.position.x - first.x, frame.position.x - firstFrame.x, 0.05f, "the light does not land on the chair where it stands");
            Assert.Greater(logo.Current.Hop, 0.5f * Tuning.TitleLogoChairStartle, "the chair does not jump when the light catches it");
            // Dragged home by the dog (first loop) and pulled home by the human (second): the carrier holds it, the light follows.
            for (int loop = 0; loop < 2; loop++)
            {
                logo.Pin(loop + Tuning.TitleLogoStillFraction + act * 0.72f);
                float homeward = chair.position.x - first.x;
                Assert.Greater(homeward, 1f, $"the chair is already home early in the drag (loop {loop})");
                Assert.AreEqual(homeward, frame.position.x - firstFrame.x, 0.05f, $"the light does not follow the chair home (loop {loop})");
                Assert.Greater(logo.Chair.color.r, 0.99f, $"the chair is not lit on its way home (loop {loop})");
                if (loop == 0)
                {
                    Assert.Greater(logo.Dog.color.a, 0.99f, "the dog is not there while the chair comes home");
                    Assert.IsTrue(logo.Current.DogBite, "the dog does not bite the chair on its way home");
                }
                else
                {
                    Assert.Greater(logo.HumanPair.color.a, 0.99f, "the human is not holding the chair while it comes home");
                }
            }
            // The pair lies exactly on the chair: its picture moves with the chair's.
            logo.Pin(1f + Tuning.TitleLogoStillFraction + act * 0.62f);
            float pairToChair = pair.position.x - chair.position.x;
            logo.Pin(1f + Tuning.TitleLogoStillFraction + act * 0.80f);
            Assert.AreEqual(pairToChair, pair.position.x - chair.position.x, 0.05f, "the pair's picture slides off the chair's");

            // The frame sequence: one still moment, then each act (leaving, hops, the light back, the startle, the carrier in,
            // the grab, the drag, home, the beat, the carrier out), the dog's loop then the human's.
            float[] moments = { 0.03f, 0.065f, 0.2f, 0.37f, 0.48f, 0.55f, 0.62f, 0.72f, 0.88f, 0.95f };
            var phases = new List<float> { 0.5f };
            for (int loop = 0; loop < 2; loop++)
            {
                foreach (float m in moments)
                {
                    phases.Add(loop + Tuning.TitleLogoStillFraction + act * m);
                }
            }
            phases.Add(1.5f);
            // The crop around the logo at 1920 x 1080, where a reference unit is a pixel: the frame, plus the spot's way
            // left and the chair's (and the spot's) way right.
            logo.Pin(0f);
            frame.GetWorldCorners(corners);
            Vector3 lo = canvas.InverseTransformPoint(corners[0]);
            Vector3 hi = canvas.InverseTransformPoint(corners[2]);
            // (x from the canvas's left edge, which the logo is anchored to; y from its centre.)
            float leftEdge = canvas.rect.width * 0.5f;
            float farUi = Tuning.TitleLogoChairHops * Tuning.TitleLogoChairHopStride * logo.UiPerMetre;
            int x0 = Mathf.Clamp(Mathf.RoundToInt(lo.x + leftEdge - Tuning.TitleLogoSpotDrift * logo.UiPerMetre - 16f), 0, 1919);
            int x1 = Mathf.Clamp(Mathf.RoundToInt(hi.x + leftEdge + Mathf.Max(travel, farUi) + 16f), 0, 1919);
            int y0 = Mathf.Clamp(Mathf.RoundToInt(lo.y + 540f - 40f), 0, 1079);
            int y1 = Mathf.Clamp(Mathf.RoundToInt(hi.y + 540f + 8f), 0, 1079);
            int cw = x1 - x0;
            int ch = y1 - y0;
            const int columns = 4;
            const int margin = 6;
            int rows = (phases.Count + columns - 1) / columns;
            var sheet = new Texture2D(columns * cw + (columns + 1) * margin, rows * ch + (rows + 1) * margin, TextureFormat.RGB24, false);
            var fill = new Color32[sheet.width * sheet.height];
            for (int i = 0; i < fill.Length; i++)
            {
                fill[i] = new Color32(40, 40, 44, 255);
            }
            sheet.SetPixels32(fill);
            for (int k = 0; k < phases.Count; k++)
            {
                logo.Pin(phases[k]);
                yield return Capture(1920, 1080);
                int col = k % columns;
                int row = rows - 1 - k / columns;
                sheet.SetPixels(margin + col * (cw + margin), margin + row * (ch + margin), cw, ch, lastShot.GetPixels(x0, y0, cw, ch));
                TestContext.WriteLine($"[Step74b] frame {k + 1}: phase {phases[k]:0.000}, {logo.Current}");
            }
            sheet.Apply();
            Directory.CreateDirectory(ShotDir);
            File.WriteAllBytes(Path.Combine(ShotDir, "title_chair_loop_sheet.png"), sheet.EncodeToPNG());
            Object.Destroy(sheet);
            // The whole menu at the key moments: away in the dark, caught, dragged home by the dog, pulled home by the human
            // (both ratios for the extremes), and a close crop of each carrier holding the chair.
            logo.Pin(Tuning.TitleLogoStillFraction + act * 0.30f);
            yield return Shoot("title_chair_away_1920x1080.png", 1920, 1080);
            yield return Shoot("title_chair_away_2400x1080.png", 2400, 1080);
            logo.Pin(Tuning.TitleLogoStillFraction + act * 0.37f);
            yield return Shoot("title_chair_caught_1920x1080.png", 1920, 1080);
            logo.Pin(Tuning.TitleLogoStillFraction + act * 0.62f);
            yield return Shoot("title_chair_dog_1920x1080.png", 1920, 1080);
            yield return Shoot("title_chair_dog_2400x1080.png", 2400, 1080);
            yield return Crop("title_chair_dog_close.png", x0, y0, cw, ch);
            logo.Pin(1f + Tuning.TitleLogoStillFraction + act * 0.62f);
            yield return Shoot("title_chair_human_1920x1080.png", 1920, 1080);
            yield return Shoot("title_chair_human_2400x1080.png", 2400, 1080);
            yield return Crop("title_chair_human_close.png", x0, y0, cw, ch);
            logo.Pin(1f + Tuning.TitleLogoStillFraction + act * 0.50f);
            yield return Crop("title_chair_human_walkin_close.png", x0, y0, cw, ch);

            // Unpinned, the loop runs on its own clock.
            logo.Unpin();
            yield return null;
            float phase = logo.Phase;
            for (float t = 0f; t < 0.3f; t += Time.unscaledDeltaTime)
            {
                yield return null;
            }
            Assert.AreNotEqual(phase, logo.Phase, "the loop does not run on its own");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>A layer's extent on the canvas (and, when <paramref name="opaque"/>, its left and right edges).</summary>
        private static void Extent(RectTransform layer, RectTransform canvas, Vector3[] corners, bool opaque, ref float top, ref float bottom,
            ref float left, ref float right)
        {
            layer.GetWorldCorners(corners);
            float l = float.MaxValue;
            float r = float.MinValue;
            foreach (Vector3 c in corners)
            {
                Vector3 p = canvas.InverseTransformPoint(c);
                top = Mathf.Max(top, p.y);
                bottom = Mathf.Min(bottom, p.y);
                l = Mathf.Min(l, p.x);
                r = Mathf.Max(r, p.x);
            }
            if (opaque)
            {
                left = Mathf.Min(left, l);
                right = Mathf.Max(right, r);
            }
        }

        /// <summary>Captures the menu at 1920 x 1080 and writes the logo's crop, doubled, to <paramref name="file"/>.</summary>
        private IEnumerator Crop(string file, int x, int y, int width, int height)
        {
            yield return Capture(1920, 1080);
            var crop = new Texture2D(width * 2, height * 2, TextureFormat.RGB24, false);
            for (int j = 0; j < height * 2; j++)
            {
                for (int i = 0; i < width * 2; i++)
                {
                    crop.SetPixel(i, j, lastShot.GetPixel(x + i / 2, y + j / 2));
                }
            }
            crop.Apply();
            Directory.CreateDirectory(ShotDir);
            File.WriteAllBytes(Path.Combine(ShotDir, file), crop.EncodeToPNG());
            Object.Destroy(crop);
        }

        private IEnumerator Shoot(string file, int width, int height)
        {
            yield return Capture(width, height);
            Directory.CreateDirectory(ShotDir);
            File.WriteAllBytes(Path.Combine(ShotDir, file), lastShot.EncodeToPNG());
        }

        /// <summary>
        /// Renders the menu canvas over the scene into <see cref="lastShot"/>, <paramref name="width"/> x
        /// <paramref name="height"/> (ProbeTestsCredits' helper): the menu's root canvas switches to Screen Space Camera on
        /// the game camera, which renders into a texture of that size, then everything is put back.
        /// </summary>
        private IEnumerator Capture(int width, int height)
        {
            Camera cam = main.Camera;
            Canvas root = Menu.GetComponent<Canvas>();
            Assert.IsNotNull(cam, "premise: Main has no camera");
            Assert.IsNotNull(root, "premise: the menu has no root canvas");
            var rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32);
            RenderTexture previousTarget = cam.targetTexture;
            float previousPlane = root.planeDistance;
            cam.targetTexture = rt;
            cam.aspect = width / (float)height;
            root.renderMode = RenderMode.ScreenSpaceCamera;
            root.worldCamera = cam;
            root.planeDistance = cam.nearClipPlane + 0.01f;
            try
            {
                yield return null;
                yield return null;
                Canvas.ForceUpdateCanvases();
                cam.ResetProjectionMatrix();
                var request = new RenderPipeline.StandardRequest { destination = rt };
                Assert.IsTrue(RenderPipeline.SupportsRenderRequest(cam, request), "premise: the pipeline cannot render the camera to a texture");
                RenderPipeline.SubmitRenderRequest(cam, request);
                RenderTexture previous = RenderTexture.active;
                RenderTexture.active = rt;
                if (lastShot != null)
                {
                    Object.Destroy(lastShot);
                }
                lastShot = new Texture2D(width, height, TextureFormat.RGB24, false);
                lastShot.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                lastShot.Apply();
                RenderTexture.active = previous;
            }
            finally
            {
                root.renderMode = RenderMode.ScreenSpaceOverlay;
                root.worldCamera = null;
                root.planeDistance = previousPlane;
                cam.targetTexture = previousTarget;
                cam.ResetAspect();
                rt.Release();
                Object.Destroy(rt);
            }
            yield return null;
            Canvas.ForceUpdateCanvases();
        }
    }
}
