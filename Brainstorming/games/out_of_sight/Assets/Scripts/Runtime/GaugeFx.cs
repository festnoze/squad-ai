using UnityEngine;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// HUD gauge danger animation (2026-11-20): what a capsule gauge of the bottom band shows once its fill is past its
    /// threshold marker (the creak warning, the discovery that would lose, the balance gauge in the red), in place of the
    /// old red and cream flashing. Four layers, chosen from prototypes compared frame by frame (docs/m9/hud/NOTES.md):
    /// a wide soft bloom of the fill's colour that breathes behind the capsule, a laser sheen that sweeps along the fill
    /// to a flickering hot spot on its leading edge, and, on crossing into the danger zone, a shockwave ring and a spray
    /// of spark streaks from that edge (the creak itself, the full gauge emptying at once, bursts every spark).
    ///
    /// Built once per gauge from the procedural sprites of <see cref="GaugeArt"/>, then driven by <see cref="Animate"/>
    /// every frame with no allocation: every image is created up front, an idle layer or a dead spark is only made
    /// transparent (its CanvasRenderer culls a transparent mesh), the spark state lives in fixed arrays. UI only: no
    /// material, no particle system.
    /// </summary>
    public sealed class GaugeFx
    {
        private const int SparkCount = 14;
        private const int CrossingSparks = 12;
        // Heat eases toward 1 in danger (0.2 s) and back to 0 after it (0.4 s).
        private const float HeatRise = 5f;
        private const float HeatFall = 2.5f;
        private const float BreathHz = 0.85f;
        // The sheen sweeps from the track's left end to the fill's head in SweepShare of every SweepPeriod, then rests.
        private const float SweepPeriod = 1.3f;
        private const float SweepShare = 0.5f;
        private const float SheenWidth = 56f;
        private const float FlareWidth = 40f;
        private const float FlareExtra = 30f;
        private const float BloomHalo = 26f;
        private const float RingLife = 0.5f;
        private const float RingFrom = 12f;
        private const float RingTo = 104f;
        private const float Gravity = -300f;
        private const float Drag = 2.5f;

        private static readonly Color Pale = new Color(1f, 0.96f, 0.8f, 1f);
        // The sparks', the ring's and the head's hot core: a saturated yellow that still reads over a green lawn.
        private static readonly Color Spark = new Color(1f, 0.86f, 0.36f, 1f);
        private static readonly Color Clear = new Color(1f, 1f, 1f, 0f);

        private readonly Vector2 trackOrigin;
        private readonly Vector2 trackSize;
        private readonly Image bloom;
        private readonly Image sheen;
        private readonly Image head;
        private readonly Image ring;
        private readonly Image[] sparks = new Image[SparkCount];
        private readonly RectTransform[] sparkRects = new RectTransform[SparkCount];
        private readonly Vector2[] sparkPos = new Vector2[SparkCount];
        private readonly Vector2[] sparkVel = new Vector2[SparkCount];
        private readonly float[] sparkAge = new float[SparkCount];
        private readonly float[] sparkLife = new float[SparkCount];
        private readonly float[] sparkLength = new float[SparkCount];
        private bool wasDanger;
        // Set by the creak burst until the fill is back under its marker: the heat stays off while the fill drains.
        private bool spent;
        private float ringAge = 99f;
        private Vector2 ringAt;
        private uint seed;

        /// <summary>0 to 1: how far into its danger look the gauge is (eases in and out).</summary>
        public float Heat { get; private set; }

        /// <summary>0 to 1, a slow breath (0.85 Hz) that the bloom and the gauge's glow follow.</summary>
        public float Breath { get; private set; }

        /// <summary>The live sparks now (tests).</summary>
        public int LiveSparks
        {
            get
            {
                int n = 0;
                for (int i = 0; i < SparkCount; i++)
                {
                    n += sparkAge[i] < sparkLife[i] ? 1 : 0;
                }
                return n;
            }
        }

        /// <summary>
        /// Builds the effect's images: the bloom behind <paramref name="plate"/>, the sheen right over <paramref name="fill"/>
        /// in the track, the head flare on top of the track, the shockwave ring and the sparks on top of the gauge.
        /// <paramref name="capsuleOrigin"/> and <paramref name="trackOrigin"/> are the bottom-left corners of the capsule
        /// and of the track in <paramref name="body"/>'s units (from its bottom-left).
        /// </summary>
        public GaugeFx(RectTransform body, Image plate, RectTransform track, Image fill, Vector2 capsuleOrigin, Vector2 capsuleSize,
            Vector2 trackOrigin, Vector2 trackSize, uint seed)
        {
            this.trackOrigin = trackOrigin;
            this.trackSize = trackSize;
            this.seed = seed == 0 ? 0x9E3779B9u : seed;

            bloom = NewImage(body, body.name + "Bloom", GaugeArt.Bloom);
            bloom.type = Image.Type.Sliced;
            bloom.pixelsPerUnitMultiplier = GaugeArt.BloomMultiplier(capsuleSize.y, BloomHalo);
            RectTransform b = bloom.rectTransform;
            b.anchorMin = b.anchorMax = Vector2.zero;
            b.pivot = new Vector2(0.5f, 0.5f);
            b.sizeDelta = capsuleSize + new Vector2(2f * BloomHalo, 2f * BloomHalo);
            b.anchoredPosition = capsuleOrigin + capsuleSize * 0.5f;
            bloom.transform.SetSiblingIndex(plate.transform.GetSiblingIndex());

            sheen = NewImage(track, track.name + "Sheen", GaugeArt.Sheen);
            sheen.type = Image.Type.Filled;
            sheen.fillMethod = Image.FillMethod.Horizontal;
            sheen.fillOrigin = (int)Image.OriginHorizontal.Left;
            RectTransform s = sheen.rectTransform;
            s.anchorMin = s.anchorMax = new Vector2(0f, 0.5f);
            s.pivot = new Vector2(0f, 0.5f);
            s.sizeDelta = new Vector2(SheenWidth, trackSize.y);
            sheen.transform.SetSiblingIndex(fill.transform.GetSiblingIndex() + 1);

            head = NewImage(track, track.name + "Head", GaugeArt.Flare);
            RectTransform h = head.rectTransform;
            h.anchorMin = h.anchorMax = new Vector2(0f, 0.5f);
            h.pivot = new Vector2(0.5f, 0.5f);
            h.sizeDelta = new Vector2(FlareWidth, trackSize.y + FlareExtra);

            ring = NewImage(body, body.name + "Ring", GaugeArt.Ring);
            ring.rectTransform.anchorMin = ring.rectTransform.anchorMax = Vector2.zero;
            ring.rectTransform.pivot = new Vector2(0.5f, 0.5f);

            for (int i = 0; i < SparkCount; i++)
            {
                sparks[i] = NewImage(body, body.name + "Spark" + i, GaugeArt.Spark);
                RectTransform r = sparks[i].rectTransform;
                r.anchorMin = r.anchorMax = Vector2.zero;
                // The streak's round head (14 texels from the sprite's right end) sits on the spark's position.
                r.pivot = new Vector2(50f / 64f, 0.5f);
                sparkRects[i] = r;
            }
        }

        private static Image NewImage(Transform parent, string name, Sprite sprite)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var image = go.AddComponent<Image>();
            image.sprite = sprite;
            image.color = Clear;
            image.raycastTarget = false;
            image.canvasRenderer.cullTransparentMesh = true;
            return image;
        }

        private float Random01()
        {
            // xorshift32: no allocation, and the same sparks on every run (the shots).
            seed ^= seed << 13;
            seed ^= seed >> 17;
            seed ^= seed << 5;
            return (seed & 0xFFFFFF) / 16777216f;
        }

        private float Range(float a, float b) => a + (b - a) * Random01();

        private static float Smooth(float a, float b, float x)
        {
            float t = Mathf.Clamp01((x - a) / (b - a));
            return t * t * (3f - 2f * t);
        }

        private static void SetColour(Image image, Color colour, float alpha)
        {
            colour.a = Mathf.Clamp01(alpha);
            if (image.color != colour)
            {
                image.color = colour;
            }
        }

        /// <summary>
        /// One frame: <paramref name="fill"/> is the drawn fill (0 to 1), <paramref name="danger"/> whether the gauge is past
        /// its threshold, <paramref name="level"/> the fill's colour now. Returns <see cref="Heat"/>.
        /// </summary>
        public float Animate(float dt, float time, float fill, bool danger, Color level)
        {
            spent &= danger;
            bool hot = danger && !spent;
            Heat = Mathf.MoveTowards(Heat, hot ? 1f : 0f, dt * (hot ? HeatRise : HeatFall));
            Breath = 0.5f - 0.5f * Mathf.Cos(time * BreathHz * 2f * Mathf.PI);
            bool crossed = danger && !wasDanger;
            wasDanger = danger;
            float fillPx = fill * trackSize.x;
            Vector2 headAt = trackOrigin + new Vector2(fillPx, trackSize.y * 0.5f);

            // The bloom: a wide soft halo of the fill's colour, breathing in alpha and a touch in size.
            float bloomScale = 1f + 0.05f * Breath;
            bloom.rectTransform.localScale = new Vector3(bloomScale, bloomScale, 1f);
            SetColour(bloom, level, Heat * (0.18f + 0.42f * Breath));

            // The sheen: a light running from the left end to the head, then a rest; clipped at the fill's straight edge
            // by its own horizontal fill, faded in while it leaves the track's round left end.
            float cycle = Mathf.Repeat(time / SweepPeriod, 1f);
            float sweep = cycle / SweepShare;
            float sheenAlpha = 0f;
            if (Heat > 0f && fillPx > SheenWidth * 0.6f && sweep < 1f)
            {
                float e = sweep * sweep * (3f - 2f * sweep);
                float x0 = Mathf.Lerp(-SheenWidth * 0.35f, fillPx - SheenWidth * 0.55f, e);
                sheen.rectTransform.anchoredPosition = new Vector2(x0, 0f);
                sheen.fillAmount = Mathf.Clamp01((fillPx - x0) / SheenWidth);
                sheenAlpha = Heat * Smooth(0f, 0.18f, sweep) * (1f - Smooth(0.86f, 1f, sweep));
            }
            SetColour(sheen, Pale, sheenAlpha * 0.95f);

            // The head: a hot spot on the fill's leading edge, flickering, flaring as the sheen arrives.
            float arrive = Mathf.Exp(-Mathf.Pow((cycle - SweepShare) / 0.06f, 2f));
            float flicker = 0.5f + 0.25f * Mathf.Sin(time * 31f) + 0.25f * Mathf.Sin(time * 17.3f);
            head.rectTransform.anchoredPosition = new Vector2(fillPx, 0f);
            head.rectTransform.sizeDelta = new Vector2(FlareWidth * (1f + 0.35f * arrive), trackSize.y + FlareExtra);
            SetColour(head, Color.Lerp(Spark, level, 0.2f), fillPx > 2f ? Heat * (0.65f + 0.25f * flicker + 0.4f * arrive) : 0f);

            // The burst: crossing into danger sends a shockwave ring and a spray of sparks from the head.
            if (crossed && fill > 0.02f)
            {
                ringAge = 0f;
                ringAt = headAt;
                Burst(headAt, CrossingSparks);
            }
            ringAge += dt;
            if (ringAge < RingLife)
            {
                float t = ringAge / RingLife;
                float size = Mathf.Lerp(RingFrom, RingTo, 1f - (1f - t) * (1f - t) * (1f - t));
                ring.rectTransform.anchoredPosition = ringAt;
                ring.rectTransform.sizeDelta = new Vector2(size, size);
                SetColour(ring, Color.Lerp(Spark, level, t), Mathf.Pow(1f - t, 1.5f));
            }
            else
            {
                SetColour(ring, Spark, 0f);
            }

            UpdateSparks(dt, level);
            return Heat;
        }

        /// <summary>
        /// The big burst: a shockwave and every spark from <paramref name="fill"/> along the track (the creak itself, when the
        /// full creak gauge empties at once).
        /// </summary>
        public void Explode(float fill)
        {
            Vector2 at = trackOrigin + new Vector2(Mathf.Clamp01(fill) * trackSize.x, trackSize.y * 0.5f);
            // The danger is spent: the sheen and the hot spot do not follow the fill as it drains, and its last frames
            // past the marker neither heat again nor send a second burst (wasDanger stays set).
            Heat = 0f;
            spent = true;
            ringAge = 0f;
            ringAt = at;
            Burst(at, SparkCount);
        }

        private void Burst(Vector2 at, int count)
        {
            for (int k = 0; k < count; k++)
            {
                // Mostly up and out: the band sits on the screen's bottom edge.
                float angle = Range(-35f, 215f) * Mathf.Deg2Rad;
                float speed = Range(170f, 330f);
                Spawn(at, new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * speed, Range(0.45f, 0.8f), Range(34f, 52f));
            }
        }

        private void Spawn(Vector2 at, Vector2 velocity, float life, float length)
        {
            for (int i = 0; i < SparkCount; i++)
            {
                if (sparkAge[i] >= sparkLife[i])
                {
                    sparkPos[i] = at;
                    sparkVel[i] = velocity;
                    sparkAge[i] = 0f;
                    sparkLife[i] = life;
                    sparkLength[i] = length;
                    return;
                }
            }
        }

        private void UpdateSparks(float dt, Color level)
        {
            float drag = Mathf.Exp(-Drag * dt);
            for (int i = 0; i < SparkCount; i++)
            {
                if (sparkAge[i] >= sparkLife[i])
                {
                    if (sparks[i].color.a > 0f)
                    {
                        SetColour(sparks[i], Spark, 0f);
                    }
                    continue;
                }
                sparkAge[i] += dt;
                Vector2 v = sparkVel[i] * drag;
                v.y += Gravity * dt;
                sparkVel[i] = v;
                sparkPos[i] += v * dt;
                float t = Mathf.Clamp01(sparkAge[i] / sparkLife[i]);
                RectTransform r = sparkRects[i];
                r.anchoredPosition = sparkPos[i];
                r.localRotation = Quaternion.Euler(0f, 0f, Mathf.Atan2(v.y, v.x) * Mathf.Rad2Deg);
                float stretch = Mathf.Clamp(v.magnitude / 200f, 0.5f, 1f);
                r.sizeDelta = new Vector2(sparkLength[i] * stretch * (1f - 0.4f * t), 19f * (1f - 0.45f * t));
                SetColour(sparks[i], Color.Lerp(Spark, level, Mathf.Clamp01(t * 1.4f)), 1f - t * t);
            }
        }
    }
}
