using System;
using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// STARSANIM (docs/next/progress/STARSANIM.md): the end screen's hero stars, three big stars centred on the win panel
    /// (the middle one bigger and raised), revealed the way many mobile games do it. On <see cref="Set"/> with an animation:
    /// <list type="number">
    /// <item>the three empty slots pop in (scale 0 to 1 with a slight overshoot, <see cref="Tuning.StarsAnimSlotStagger"/>
    /// apart);</item>
    /// <item>from <see cref="Tuning.StarsAnimFirstFill"/>, each earned star fills one after the other
    /// (<see cref="Tuning.StarsAnimFillGap"/> apart): it punches in from <see cref="Tuning.StarsAnimPunchScale"/> down to 1 with an
    /// overshoot, flashing white to gold, over a glow, inside an expanding ring, with sparkles flying out and a short shake
    /// of the row; the owner plays the rising chime (<see cref="Sfx.PlayStarChime"/>). The third star's finish is bigger:
    /// more and faster sparkles, a wider ring, a stronger shake, a pulse of the whole row and the chord chime;</item>
    /// <item>an unearned star stays empty: a small squash of its slot and a soft tick (<see cref="Sfx.PlayStarDull"/>).</item>
    /// </list>
    /// <see cref="Complete"/> settles everything at once (a tap, a click, Enter: the HUD calls it), with at most one chime.
    /// Not a component: <see cref="Hud"/> owns one and drives it from its Update with unscaled time, like the gauges.
    /// Cheap on a phone: 12 star, ring and glow images and a pool of <see cref="SparklePool"/> sparkles, built once under a
    /// nested Canvas of their own (only it rebuilds while the reveal plays); nothing is allocated per frame (scales, colours,
    /// positions and rotations are structs, the random draws come from one System.Random built here).
    /// </summary>
    public sealed class WinStarsView
    {
        // ----- Geometry, reference units (1920 x 1080). The row is 540 wide: it fits a 4:3 tablet's 1663 with room. -----

        /// <summary>The side stars' size.</summary>
        public const float SideSize = 150f;

        /// <summary>The middle star's size (bigger, and raised by <see cref="MiddleRaise"/>).</summary>
        public const float MiddleSize = 184f;

        /// <summary>The gap between two stars' boxes.</summary>
        public const float StarGap = 28f;

        /// <summary>How far the middle star sits above the side stars' centres.</summary>
        public const float MiddleRaise = 16f;

        /// <summary>The sparkles shared by the three stars (10 per star, 14 for the third; the oldest is reused).</summary>
        public const int SparklePool = 24;

        private const int SparklesPerStar = 10;
        private const int SparklesFinal = 14;
        private const float GlowSeconds = 0.35f;
        private const float RingSeconds = 0.45f;
        private const float MissSquashSeconds = 0.24f;
        private const float PulseSeconds = 0.32f;
        private const float SparkleDrag = 3.2f;
        private const float SparkleGravity = 520f;

        private static readonly Color FlashWhite = new Color(1f, 0.98f, 0.9f, 1f);
        private static readonly Color GlowTint = new Color(1f, 0.86f, 0.45f, 1f);
        private static readonly Color RingTint = new Color(1f, 0.93f, 0.7f, 1f);
        private static readonly Color[] SparkleTints =
        {
            Stars.Gold, new Color(1f, 0.97f, 0.86f, 1f), new Color(1f, 0.66f, 0.3f, 1f),
        };

        /// <summary>The row's root, centred on its place (the shake moves it, the third star's pulse scales it).</summary>
        public RectTransform Root { get; }

        /// <summary>The row's own nested Canvas: the HUD enables it with the win panel.</summary>
        public Canvas Canvas { get; }

        /// <summary>The stars earned by the last <see cref="Set"/> (0 to 3).</summary>
        public int Count { get; private set; }

        /// <summary>The reveal is playing (slots, fills, effects): false once it settled or was completed.</summary>
        public bool Revealing { get; private set; }

        /// <summary>The row is set for the panel up now (from <see cref="Set"/> to <see cref="Hide"/>).</summary>
        public bool Shown { get; private set; }

        /// <summary>The last reveal was completed early (<see cref="Complete"/> with a skip).</summary>
        public bool Skipped { get; private set; }

        /// <summary>Seconds into the reveal (unscaled), and the reveal's whole length for the current count.</summary>
        public float Clock => clock;
        public float Duration { get; private set; }

        /// <summary>The fill events fired so far (one per earned star), and the unearned ticks.</summary>
        public int FillsFired { get; private set; }
        public int MissesFired { get; private set; }

        /// <summary>The gold stars, left to right (an unearned one stays disabled); tests read their scale and colour.</summary>
        public IReadOnlyList<Image> Images => fills;

        /// <summary>The empty slots under them, left to right.</summary>
        public IReadOnlyList<Image> Slots => slots;

        /// <summary>The sparkles flying now (tests).</summary>
        public int LiveSparkles
        {
            get
            {
                int live = 0;
                for (int i = 0; i < SparklePool; i++)
                {
                    if (sparkleAge[i] < sparkleLife[i])
                    {
                        live++;
                    }
                }
                return live;
            }
        }

        /// <summary>
        /// How far the "New stars!" line has faded in (0 to 1): from just after the last star event, so the line arrives
        /// with the result; 1 once the reveal settled.
        /// </summary>
        public float AfterAlpha => Revealing ? Mathf.Clamp01((clock - eventTimes[eventTimes.Length - 1] - 0.15f) / 0.3f) : 1f;

        private readonly Image[] slots;
        private readonly Image[] fills;
        private readonly Image[] glows;
        private readonly Image[] rings;
        private readonly Image[] sparkles = new Image[SparklePool];
        private readonly RectTransform[] sparkleRects = new RectTransform[SparklePool];
        private readonly Vector2[] sparklePos = new Vector2[SparklePool];
        private readonly Vector2[] sparkleVel = new Vector2[SparklePool];
        private readonly float[] sparkleAge = new float[SparklePool];
        private readonly float[] sparkleLife = new float[SparklePool];
        private readonly float[] sparkleSpin = new float[SparklePool];
        private readonly float[] sparkleAngle = new float[SparklePool];
        private readonly float[] sparkleSize = new float[SparklePool];
        private readonly Vector2[] centres;
        private readonly float[] sizes;
        private readonly float[] eventTimes;
        private readonly bool[] fired;
        private readonly Action<int> onFill;
        private readonly Action<int> onMiss;
        private readonly System.Random random = new System.Random(5150);
        private int nextSparkle;
        private float clock;
        private Vector2 basePosition;
        private float shakeClock = 99f;
        private float shakeAmplitude;
        private float pulseClock = 99f;
        private int owedChime = -1;
        private int owedChimeFrame;

        /// <summary>
        /// Builds the row under <paramref name="parent"/> (hidden): <paramref name="onFill"/> is told the index of each star
        /// that fills (0, 1, 2; and once after a skip), <paramref name="onMiss"/> the index of each star left empty.
        /// </summary>
        public WinStarsView(Transform parent, string name, Action<int> onFill, Action<int> onMiss)
        {
            this.onFill = onFill;
            this.onMiss = onMiss;
            int n = Mathf.Max(1, Tuning.StarsPerLevel);
            slots = new Image[n];
            fills = new Image[n];
            glows = new Image[n];
            rings = new Image[n];
            centres = new Vector2[n];
            sizes = new float[n];
            eventTimes = new float[n];
            fired = new bool[n];

            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            Root = (RectTransform)go.transform;
            Root.anchorMin = Root.anchorMax = new Vector2(0.5f, 0.5f);
            Root.pivot = new Vector2(0.5f, 0.5f);
            // The root's rect is the row's bounding box: the middle star's box (the side stars, MiddleRaise lower, end
            // inside it as long as the raise stays under half the size difference, 17 units).
            Root.sizeDelta = new Vector2(2f * (MiddleSize * 0.5f + StarGap) + SideSize, Mathf.Max(MiddleSize, SideSize + 2f * MiddleRaise));
            // Its own Canvas: the reveal's per-frame changes rebuild these few images only, never the panel's texts.
            Canvas = go.AddComponent<Canvas>();

            // Three stars: the middle one (the second of three) bigger, at the root's centre, the side ones lower; any other
            // count stays a plain row.
            float side = MiddleSize * 0.5f + StarGap + SideSize * 0.5f;
            for (int i = 0; i < n; i++)
            {
                bool middle = n == 3 && i == 1;
                sizes[i] = middle ? MiddleSize : SideSize;
                centres[i] = n == 3
                    ? new Vector2((i - 1) * side, middle ? 0f : -MiddleRaise)
                    : new Vector2((i - (n - 1) * 0.5f) * (SideSize + StarGap), 0f);
            }
            // Drawing order: glows behind everything, then the slots, the gold stars, the rings, the sparkles in front.
            for (int i = 0; i < n; i++)
            {
                glows[i] = NewImage(name + "Glow" + i, ProceduralArt.SoftGlow, centres[i], sizes[i] * 1.6f);
            }
            for (int i = 0; i < n; i++)
            {
                slots[i] = NewImage(name + "Slot" + i, Stars.StarSlot, centres[i], sizes[i]);
                slots[i].preserveAspect = true;
            }
            for (int i = 0; i < n; i++)
            {
                fills[i] = NewImage(name + i, Stars.StarLarge, centres[i], sizes[i]);
                fills[i].preserveAspect = true;
            }
            for (int i = 0; i < n; i++)
            {
                rings[i] = NewImage(name + "Ring" + i, ProceduralArt.BurstRing, centres[i], sizes[i]);
            }
            for (int i = 0; i < SparklePool; i++)
            {
                sparkles[i] = NewImage(name + "Sparkle" + i, ProceduralArt.Sparkle, Vector2.zero, 1f);
                sparkleRects[i] = sparkles[i].rectTransform;
                sparkleLife[i] = 0f;
                sparkleAge[i] = 1f;
            }
            Hide();
        }

        /// <summary>A skip still owes its one chime (played on the next <see cref="Animate"/>).</summary>
        public bool ChimeOwed => owedChime >= 0;

        /// <summary>Settles the reveal with no sound at all and drops an owed chime (the panel went under a menu).</summary>
        public void Silence()
        {
            Complete(false);
            owedChime = -1;
        }

        /// <summary>
        /// Places the row's centre (the middle star's centre) <paramref name="y"/> units above the panel's centre; the shake
        /// stays relative to it.
        /// </summary>
        public void Place(float y)
        {
            basePosition = new Vector2(0f, y);
            Root.anchoredPosition = basePosition;
        }

        /// <summary>
        /// Shows the row for a win of <paramref name="count"/> stars. With <paramref name="animate"/> the reveal starts (see the
        /// class summary); without it (or under <see cref="Hud.ReducedMotion"/>) the row shows settled at once, with one chime
        /// on the next frame.
        /// </summary>
        public void Set(int count, bool animate)
        {
            int n = slots.Length;
            Count = Mathf.Clamp(count, 0, n);
            Shown = true;
            Skipped = false;
            clock = 0f;
            FillsFired = 0;
            MissesFired = 0;
            owedChime = -1;
            float t = Tuning.StarsAnimFirstFill;
            for (int k = 0; k < n; k++)
            {
                if (k > 0)
                {
                    t += k < Count ? Tuning.StarsAnimFillGap : Tuning.StarsAnimMissGap;
                }
                eventTimes[k] = t;
                fired[k] = false;
            }
            Duration = t + Tuning.StarsAnimTail;
            KillEffects();
            for (int i = 0; i < n; i++)
            {
                slots[i].enabled = true;
                fills[i].enabled = false;
            }
            Root.anchoredPosition = basePosition;
            Root.localScale = Vector3.one;
            if (!animate || Hud.ReducedMotion)
            {
                Revealing = true;
                Complete(true);
                Skipped = false;
                return;
            }
            Revealing = true;
            for (int i = 0; i < n; i++)
            {
                slots[i].rectTransform.localScale = Vector3.zero;
                slots[i].color = Color.white;
            }
        }

        /// <summary>Hides the row (a new win, a retry, another panel): nothing shows, plays or is owed any more.</summary>
        public void Hide()
        {
            Shown = false;
            Revealing = false;
            Skipped = false;
            owedChime = -1;
            KillEffects();
            for (int i = 0; i < slots.Length; i++)
            {
                slots[i].enabled = false;
                fills[i].enabled = false;
            }
            Root.anchoredPosition = basePosition;
            Root.localScale = Vector3.one;
        }

        /// <summary>
        /// Settles the reveal now: every slot full size, every earned star gold at scale 1, the effects gone. With
        /// <paramref name="skipped"/> (a tap or a key) and an earned star still owed its fill, exactly one chime plays, the
        /// highest earned star's, on the next frame (so a press that also leaves the panel, Enter on Next level, rings
        /// nothing over the next level); without it nothing plays. Nothing happens once settled.
        /// </summary>
        public void Complete(bool skipped)
        {
            if (!Revealing)
            {
                return;
            }
            int last = Count - 1;
            bool owed = skipped && last >= 0 && !fired[last];
            clock = Duration;
            for (int k = 0; k < fired.Length; k++)
            {
                fired[k] = true;
            }
            Settle();
            Skipped = skipped;
            if (owed)
            {
                owedChime = last;
                owedChimeFrame = Time.frameCount;
            }
        }

        /// <summary>
        /// Advances the reveal by <paramref name="dt"/> unscaled seconds and plays a chime owed by a skip. Nothing to do on a
        /// settled row (no work, no rebuild). The HUD calls it only while its win panel is up.
        /// </summary>
        public void Animate(float dt)
        {
            if (owedChime >= 0 && Time.frameCount > owedChimeFrame)
            {
                int chime = owedChime;
                owedChime = -1;
                onFill?.Invoke(chime);
            }
            if (!Revealing)
            {
                return;
            }
            dt = Mathf.Max(0f, dt);
            clock += dt;
            int n = slots.Length;
            for (int k = 0; k < n; k++)
            {
                if (!fired[k] && clock >= eventTimes[k])
                {
                    Fire(k);
                }
            }
            for (int i = 0; i < n; i++)
            {
                AnimateSlot(i);
                if (i < Count)
                {
                    AnimateFill(i);
                }
            }
            AnimateSparkles(dt);
            AnimateRow(dt);
            if (clock >= Duration)
            {
                Settle();
            }
        }

        /// <summary>The star event <paramref name="k"/>: an earned star fills (burst, chime, shake), an unearned one ticks.</summary>
        private void Fire(int k)
        {
            fired[k] = true;
            if (k >= Count)
            {
                MissesFired++;
                onMiss?.Invoke(k);
                return;
            }
            FillsFired++;
            bool final = k == slots.Length - 1 && slots.Length == 3;
            fills[k].enabled = true;
            glows[k].enabled = true;
            rings[k].enabled = true;
            SpawnSparkles(k, final ? SparklesFinal : SparklesPerStar, final);
            shakeClock = 0f;
            shakeAmplitude = final ? Tuning.StarsAnimShakeFinal : Tuning.StarsAnimShake;
            if (final)
            {
                pulseClock = 0f;
            }
            onFill?.Invoke(k);
        }

        private void AnimateSlot(int i)
        {
            float p = Mathf.Clamp01((clock - i * Tuning.StarsAnimSlotStagger) / Mathf.Max(0.01f, Tuning.StarsAnimSlotPop));
            float s = p > 0f ? EaseOutBack(p) : 0f;
            // An unearned star: a small squash of its slot as its tick plays ("not this one").
            if (i >= Count && fired[i])
            {
                float u = (clock - eventTimes[i]) / MissSquashSeconds;
                if (u < 1f)
                {
                    s *= 1f - 0.14f * Mathf.Sin(Mathf.PI * u);
                }
            }
            slots[i].rectTransform.localScale = new Vector3(s, s, 1f);
            Color c = Color.white;
            c.a = Mathf.Clamp01(p * 2.5f);
            slots[i].color = c;
        }

        private void AnimateFill(int i)
        {
            if (!fired[i])
            {
                return;
            }
            float age = clock - eventTimes[i];
            bool final = i == slots.Length - 1 && slots.Length == 3;
            // The punch: from the big scale down to 1, dipping a little under 1 (the ease's overshoot), then back.
            float u = Mathf.Clamp01(age / Mathf.Max(0.01f, Tuning.StarsAnimPunchSeconds));
            float s = Mathf.LerpUnclamped(Tuning.StarsAnimPunchScale, 1f, EaseOutBack(u));
            fills[i].rectTransform.localScale = new Vector3(s, s, 1f);
            Color c = Color.Lerp(FlashWhite, Stars.Gold, Mathf.Clamp01(u * 1.5f));
            c.a = Mathf.Clamp01(u * 5f);
            fills[i].color = c;

            float g = age / GlowSeconds;
            if (g < 1f)
            {
                float gs = 0.7f + 1.3f * EaseOutCubic(g);
                glows[i].rectTransform.localScale = new Vector3(gs, gs, 1f);
                Color gc = GlowTint;
                gc.a = (final ? 0.95f : 0.8f) * (1f - g) * (1f - g);
                glows[i].color = gc;
            }
            else if (glows[i].enabled)
            {
                glows[i].enabled = false;
            }

            float r = age / RingSeconds;
            if (r < 1f)
            {
                float rs = 0.5f + (final ? 2.1f : 1.6f) * EaseOutCubic(r);
                rings[i].rectTransform.localScale = new Vector3(rs, rs, 1f);
                Color rc = RingTint;
                rc.a = 0.9f * Mathf.Pow(1f - r, 1.5f);
                rings[i].color = rc;
            }
            else if (rings[i].enabled)
            {
                rings[i].enabled = false;
            }
        }

        /// <summary>Sends <paramref name="count"/> sparkles out of star <paramref name="k"/>, evenly around it with some jitter.</summary>
        private void SpawnSparkles(int k, int count, bool final)
        {
            Vector2 origin = centres[k];
            float step = 360f / Mathf.Max(1, count);
            float offset = (float)random.NextDouble() * step;
            for (int j = 0; j < count; j++)
            {
                int i = TakeSparkle();
                float angle = (offset + j * step + Range(-12f, 12f)) * Mathf.Deg2Rad;
                var dir = new Vector2(Mathf.Cos(angle), Mathf.Sin(angle));
                float speed = final ? Range(440f, 780f) : Range(360f, 620f);
                sparklePos[i] = origin + dir * (sizes[k] * 0.22f);
                sparkleVel[i] = dir * speed;
                sparkleAge[i] = 0f;
                sparkleLife[i] = Range(0.45f, 0.65f);
                sparkleSpin[i] = Range(-540f, 540f);
                sparkleAngle[i] = Range(0f, 360f);
                sparkleSize[i] = final ? Range(22f, 42f) : Range(18f, 34f);
                sparkleRects[i].sizeDelta = new Vector2(sparkleSize[i], sparkleSize[i]);
                sparkles[i].color = SparkleTints[j % SparkleTints.Length];
                sparkles[i].enabled = true;
            }
        }

        /// <summary>A free sparkle, else the next one round the pool (the oldest, nearly faded).</summary>
        private int TakeSparkle()
        {
            for (int n = 0; n < SparklePool; n++)
            {
                int i = (nextSparkle + n) % SparklePool;
                if (sparkleAge[i] >= sparkleLife[i])
                {
                    nextSparkle = (i + 1) % SparklePool;
                    return i;
                }
            }
            int oldest = nextSparkle;
            nextSparkle = (nextSparkle + 1) % SparklePool;
            return oldest;
        }

        private void AnimateSparkles(float dt)
        {
            float drag = Mathf.Exp(-SparkleDrag * dt);
            for (int i = 0; i < SparklePool; i++)
            {
                if (sparkleAge[i] >= sparkleLife[i])
                {
                    continue;
                }
                sparkleAge[i] += dt;
                float t = sparkleAge[i] / sparkleLife[i];
                if (t >= 1f)
                {
                    sparkles[i].enabled = false;
                    continue;
                }
                Vector2 v = sparkleVel[i] * drag;
                v.y -= SparkleGravity * dt;
                sparkleVel[i] = v;
                sparklePos[i] += v * dt;
                sparkleAngle[i] += sparkleSpin[i] * dt;
                float s = Mathf.Clamp01(t / 0.12f) * (1f - 0.55f * t);
                RectTransform rect = sparkleRects[i];
                rect.anchoredPosition = sparklePos[i];
                rect.localRotation = Quaternion.Euler(0f, 0f, sparkleAngle[i]);
                rect.localScale = new Vector3(s, s, 1f);
                Color c = sparkles[i].color;
                c.a = 1f - t * t;
                sparkles[i].color = c;
            }
        }

        /// <summary>The row's shake after each fill (decaying fast) and the third star's pulse of the whole row.</summary>
        private void AnimateRow(float dt)
        {
            Vector2 offset = Vector2.zero;
            float shakeSeconds = Mathf.Max(0.01f, Tuning.StarsAnimShakeSeconds);
            if (shakeClock < shakeSeconds)
            {
                shakeClock += dt;
                float e = Mathf.Clamp01(1f - shakeClock / shakeSeconds);
                float a = shakeAmplitude * e * e;
                offset = new Vector2(Mathf.Sin(shakeClock * 95f) * a, Mathf.Cos(shakeClock * 77f) * a * 0.6f);
            }
            Root.anchoredPosition = basePosition + offset;
            float scale = 1f;
            if (pulseClock < PulseSeconds)
            {
                pulseClock += dt;
                scale = 1f + 0.07f * Mathf.Sin(Mathf.PI * Mathf.Clamp01(pulseClock / PulseSeconds));
            }
            Root.localScale = new Vector3(scale, scale, 1f);
        }

        /// <summary>The settled row: slots full size, earned stars gold at scale 1, unearned ones empty, no effect left.</summary>
        private void Settle()
        {
            Revealing = false;
            KillEffects();
            for (int i = 0; i < slots.Length; i++)
            {
                slots[i].enabled = true;
                slots[i].rectTransform.localScale = Vector3.one;
                slots[i].color = Color.white;
                bool lit = i < Count;
                fills[i].enabled = lit;
                fills[i].rectTransform.localScale = Vector3.one;
                fills[i].color = lit ? Stars.Gold : Color.clear;
            }
            Root.anchoredPosition = basePosition;
            Root.localScale = Vector3.one;
        }

        /// <summary>Every glow, ring and sparkle gone, the shake and the pulse stopped.</summary>
        private void KillEffects()
        {
            for (int i = 0; i < glows.Length; i++)
            {
                glows[i].enabled = false;
                rings[i].enabled = false;
            }
            for (int i = 0; i < SparklePool; i++)
            {
                sparkleAge[i] = 1f;
                sparkleLife[i] = 0f;
                sparkles[i].enabled = false;
            }
            shakeClock = 99f;
            pulseClock = 99f;
        }

        private Image NewImage(string name, Sprite sprite, Vector2 position, float size)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(Root, false);
            var image = go.AddComponent<Image>();
            image.sprite = sprite;
            image.color = Color.white;
            image.raycastTarget = false;
            // A transparent image (a faded effect) costs no draw at all.
            image.canvasRenderer.cullTransparentMesh = true;
            RectTransform rect = image.rectTransform;
            rect.anchorMin = rect.anchorMax = new Vector2(0.5f, 0.5f);
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = position;
            rect.sizeDelta = new Vector2(size, size);
            image.enabled = false;
            return image;
        }

        private float Range(float min, float max) => min + (float)random.NextDouble() * (max - min);

        /// <summary>An ease out with an overshoot (about 10 % past 1 near the end), 0 at 0 and 1 at 1.</summary>
        private static float EaseOutBack(float t)
        {
            const float c1 = 1.70158f;
            const float c3 = c1 + 1f;
            float u = t - 1f;
            return 1f + c3 * u * u * u + c1 * u * u;
        }

        private static float EaseOutCubic(float t)
        {
            float u = 1f - t;
            return 1f - u * u * u;
        }
    }
}
