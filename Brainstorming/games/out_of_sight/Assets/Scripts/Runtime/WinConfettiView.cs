using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// CONFETTI (2026-11-27, docs/next/progress/STARSANIM.md "Confetti"): the festive shower over the win panel and the end
    /// screen when a level earns three stars. <see cref="Play"/> fires it (the HUD does, as the third star lands, or at once
    /// when a skip completes a three star reveal): two cannons at the bottom corners shoot paper up and inward while a lighter
    /// rain starts from the top edge. Each piece (a rectangle, a streamer strip, a dot, a curled ribbon or a wavy streamer, in
    /// gold, red, teal, white or soft blue) slows with air drag, falls under gravity, sways sideways once it flutters, spins,
    /// flips in 3D (its width swings through edge-on, darker as it turns away from the light) and fades out at the end of its
    /// life: about 3.3 s in all (<see cref="Duration"/>).
    /// Not a component: <see cref="Hud"/> owns one and drives it with unscaled time (the end screen may be paused), and stops
    /// it when the panel goes (Next level, Retry, Menu, a menu over the panel, an ad). Cheap on a phone: a pool of
    /// <see cref="Tuning.ConfettiPieces"/> images built once under one nested Canvas, every shape in one small atlas
    /// (<see cref="ProceduralArt.ConfettiShapes"/>), so the whole shower is one draw call; raycast off on every piece (and
    /// no raycaster on the canvas), so the buttons drawn above it stay clickable; nothing is allocated per frame.
    /// </summary>
    public sealed class WinConfettiView
    {
        // Physics in reference units for a 1080 unit high canvas, scaled by the canvas's height at Play (so the shower fills
        // every aspect ratio the same way): the cannons' shots reach 60 to 95 % of the screen's height in about a second,
        // then the paper flutters down at about 330 units per second.
        private const float ReferenceHeight = 1080f;
        private const float Gravity = 600f;
        private const float FadeSeconds = 0.6f;
        private const float CannonInset = 40f;
        private const float CannonBelow = 24f;
        // Under this speed a piece flutters (sways sideways), fully once it nearly hangs in the air.
        private const float FlutterSpeed = 900f;

        // Gold like the stars, red like the player's furniture, teal, white and soft blue.
        private static readonly Color[] Palette =
        {
            Stars.Gold,
            LevelMiniature.ChairRed,
            new Color(0.16f, 0.76f, 0.7f, 1f),
            new Color(1f, 0.98f, 0.94f, 1f),
            new Color(0.48f, 0.7f, 1f, 1f),
        };

        /// <summary>The shower's root, stretched over the whole panel (pieces are placed from its centre).</summary>
        public RectTransform Root { get; }

        /// <summary>The shower's own nested Canvas: enabled only while it plays (the HUD also turns it off with the panel).</summary>
        public Canvas Canvas { get; }

        /// <summary>The shower is falling now (from <see cref="Play"/> to its end or <see cref="Stop"/>).</summary>
        public bool Playing { get; private set; }

        /// <summary>Showers fired since startup (tests: one per three star result, never on a refresh).</summary>
        public int Bursts { get; private set; }

        /// <summary>Seconds since the last <see cref="Play"/> (unscaled), and that shower's whole length.</summary>
        public float Clock => clock;
        public float Duration { get; private set; }

        /// <summary>The pieces of the pool, and their images (tests: raycast off, one atlas).</summary>
        public int PieceCount => images.Length;
        public IReadOnlyList<Image> Images => images;

        /// <summary>The pieces on screen now.</summary>
        public int LivePieces
        {
            get
            {
                int live = 0;
                for (int i = 0; i < images.Length; i++)
                {
                    if (images[i].enabled)
                    {
                        live++;
                    }
                }
                return live;
            }
        }

        private readonly Image[] images;
        private readonly RectTransform[] rects;
        private readonly Color[] tints;
        private readonly Vector2[] pos;
        private readonly Vector2[] vel;
        private readonly float[] delay;
        private readonly float[] life;
        private readonly float[] linearDrag;
        private readonly float[] quadDrag;
        private readonly float[] spin;
        private readonly float[] angle;
        private readonly float[] flipPhase;
        private readonly float[] flipSpeed;
        private readonly float[] swayPhase;
        private readonly float[] swayFreq;
        private readonly float[] swayAmp;
        private readonly System.Random random = new System.Random(2711);
        private float clock;
        private float scale = 1f;
        private float gravity = Gravity;

        /// <summary>Builds the pool under <paramref name="parent"/> (stretched over it), hidden until <see cref="Play"/>.</summary>
        public WinConfettiView(Transform parent, string name)
        {
            int n = Mathf.Max(1, Tuning.ConfettiPieces);
            images = new Image[n];
            rects = new RectTransform[n];
            tints = new Color[n];
            pos = new Vector2[n];
            vel = new Vector2[n];
            delay = new float[n];
            life = new float[n];
            linearDrag = new float[n];
            quadDrag = new float[n];
            spin = new float[n];
            angle = new float[n];
            flipPhase = new float[n];
            flipSpeed = new float[n];
            swayPhase = new float[n];
            swayFreq = new float[n];
            swayAmp = new float[n];

            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            Root = (RectTransform)go.transform;
            Root.anchorMin = Vector2.zero;
            Root.anchorMax = Vector2.one;
            Root.pivot = new Vector2(0.5f, 0.5f);
            Root.offsetMin = Vector2.zero;
            Root.offsetMax = Vector2.zero;
            // Its own Canvas: the pieces move every frame, so only this one rebuilds, never the panel's texts.
            Canvas = go.AddComponent<Canvas>();

            Sprite[] shapes = ProceduralArt.ConfettiShapes;
            for (int i = 0; i < n; i++)
            {
                var piece = new GameObject(name + i, typeof(RectTransform));
                piece.transform.SetParent(Root, false);
                Image image = piece.AddComponent<Image>();
                image.raycastTarget = false;
                image.canvasRenderer.cullTransparentMesh = true;
                // The mix: rectangles 34 %, streamer strips 22 %, dots 20 %, curled ribbons 14 %, wavy streamers 10 %.
                double kind = random.NextDouble();
                int shape;
                Vector2 size;
                if (kind < 0.34)
                {
                    shape = ProceduralArt.ConfettiSquare;
                    size = new Vector2(Range(11f, 16f), Range(15f, 22f));
                }
                else if (kind < 0.56)
                {
                    shape = ProceduralArt.ConfettiSquare;
                    size = new Vector2(Range(5.5f, 7.5f), Range(28f, 44f));
                }
                else if (kind < 0.76)
                {
                    shape = ProceduralArt.ConfettiDisc;
                    float d = Range(10f, 15f);
                    size = new Vector2(d, d);
                }
                else if (kind < 0.9)
                {
                    shape = ProceduralArt.ConfettiCurl;
                    float d = Range(18f, 26f);
                    size = new Vector2(d, d);
                }
                else
                {
                    shape = ProceduralArt.ConfettiWave;
                    size = new Vector2(Range(10f, 13f), Range(26f, 36f));
                }
                image.sprite = shapes[shape];
                RectTransform rect = image.rectTransform;
                rect.anchorMin = rect.anchorMax = new Vector2(0.5f, 0.5f);
                rect.pivot = new Vector2(0.5f, 0.5f);
                rect.sizeDelta = size;
                tints[i] = Palette[random.Next(Palette.Length)];
                image.color = tints[i];
                image.enabled = false;
                images[i] = image;
                rects[i] = rect;
            }
            Canvas.enabled = false;
        }

        /// <summary>
        /// Fires a new shower (a playing one starts over): the first <see cref="Tuning.ConfettiCannonShare"/> of the pool from the
        /// two bottom corner cannons in turn (up and inward, 56 to 84 degrees, within 0.16 s), the rest rained from just above
        /// the top edge between 0.2 and 0.7 s. The cannons sit inside <see cref="Screen.safeArea"/>'s side insets.
        /// </summary>
        public void Play()
        {
            Rect area = Root.rect;
            float w = area.width > 100f ? area.width : 1920f;
            float h = area.height > 100f ? area.height : ReferenceHeight;
            scale = h / ReferenceHeight;
            gravity = Gravity * scale;
            Vector4 safe = TouchLayout.SafeInsets();
            int n = images.Length;
            int cannons = Mathf.Clamp(Mathf.RoundToInt(n * Tuning.ConfettiCannonShare), 0, n);
            float end = 0f;
            for (int i = 0; i < n; i++)
            {
                if (i < cannons)
                {
                    bool left = (i & 1) == 0;
                    float x = left ? -w * 0.5f + CannonInset + safe.x : w * 0.5f - CannonInset - safe.y;
                    pos[i] = new Vector2(x + Range(-14f, 14f), -h * 0.5f - CannonBelow + Range(-10f, 10f));
                    float elevation = Range(56f, 84f) * Mathf.Deg2Rad;
                    float speed = Range(2300f, 3400f) * scale;
                    vel[i] = new Vector2(Mathf.Cos(elevation) * (left ? 1f : -1f), Mathf.Sin(elevation)) * speed;
                    delay[i] = Range(0f, 0.16f);
                    life[i] = Range(2.4f, 3f);
                }
                else
                {
                    pos[i] = new Vector2(Range(-0.47f, 0.47f) * w, h * 0.5f + Range(20f, 70f));
                    vel[i] = new Vector2(Range(-70f, 70f), Range(-260f, -110f)) * scale;
                    delay[i] = Range(0.2f, 0.7f);
                    life[i] = Range(2.1f, 2.6f);
                }
                // Drag: linear plus quadratic (the fast shot slows hard, then the paper hangs); the quadratic term divided by
                // the scale keeps the paths in proportion to the canvas.
                linearDrag[i] = Range(1.2f, 1.9f);
                quadDrag[i] = Range(0.0008f, 0.0013f) / scale;
                spin[i] = Range(120f, 620f) * (random.NextDouble() < 0.5 ? -1f : 1f);
                angle[i] = Range(0f, 360f);
                flipPhase[i] = Range(0f, 2f * Mathf.PI);
                flipSpeed[i] = Range(5f, 13f);
                swayPhase[i] = Range(0f, 2f * Mathf.PI);
                swayFreq[i] = Range(2.4f, 4.8f);
                swayAmp[i] = Range(50f, 120f) * scale;
                images[i].enabled = false;
                end = Mathf.Max(end, delay[i] + life[i]);
            }
            Duration = end;
            clock = 0f;
            Playing = true;
            Bursts++;
            Canvas.enabled = true;
        }

        /// <summary>Ends the shower at once: every piece hidden, the canvas off. Nothing to do when it is not playing.</summary>
        public void Stop()
        {
            if (!Playing)
            {
                return;
            }
            Playing = false;
            for (int i = 0; i < images.Length; i++)
            {
                if (images[i].enabled)
                {
                    images[i].enabled = false;
                }
            }
            Canvas.enabled = false;
        }

        /// <summary>
        /// Advances the shower by <paramref name="dt"/> unscaled seconds: each piece shows once its delay passed, moves, spins,
        /// flips and fades, and hides at the end of its life; the shower stops itself after <see cref="Duration"/>. No work
        /// when it is not playing.
        /// </summary>
        public void Animate(float dt)
        {
            if (!Playing)
            {
                return;
            }
            dt = Mathf.Max(0f, dt);
            clock += dt;
            float flutterSpeed = FlutterSpeed * scale;
            for (int i = 0; i < images.Length; i++)
            {
                float age = clock - delay[i];
                if (age < 0f)
                {
                    continue;
                }
                Image image = images[i];
                if (age >= life[i])
                {
                    if (image.enabled)
                    {
                        image.enabled = false;
                    }
                    continue;
                }
                if (!image.enabled)
                {
                    image.enabled = true;
                }
                // A piece that just appeared moves only for the time since its own start.
                float step = Mathf.Min(dt, age);
                Vector2 v = vel[i];
                float speed = v.magnitude;
                v *= Mathf.Exp(-(linearDrag[i] + quadDrag[i] * speed) * step);
                v.y -= gravity * step;
                vel[i] = v;
                float flutter = 1f - Mathf.Clamp01(speed / flutterSpeed);
                float sway = Mathf.Sin(swayPhase[i] + age * swayFreq[i]) * swayAmp[i] * flutter;
                pos[i] += new Vector2(v.x + sway, v.y) * step;
                angle[i] += spin[i] * step;
                // The 3D flip: the width swings through edge-on (a negative scale shows the back), darker as it turns away.
                float flip = Mathf.Cos(flipPhase[i] + age * flipSpeed[i]);
                RectTransform rect = rects[i];
                rect.anchoredPosition = pos[i];
                rect.localRotation = Quaternion.Euler(0f, 0f, angle[i]);
                rect.localScale = new Vector3(flip, 1f, 1f);
                Color c = tints[i];
                float light = 0.6f + 0.4f * Mathf.Abs(flip);
                c.r *= light;
                c.g *= light;
                c.b *= light;
                c.a = Mathf.Clamp01((life[i] - age) / FadeSeconds);
                image.color = c;
            }
            if (clock >= Duration)
            {
                Stop();
            }
        }

        private float Range(float min, float max) => min + (float)random.NextDouble() * (max - min);
    }
}
