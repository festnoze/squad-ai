using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// HUD sprites drawn in code at startup (no texture asset). The open and closed eyes differ by shape,
    /// not only by color, so the seen state never relies on color alone.
    /// </summary>
    public static class ProceduralArt
    {
        private static Sprite eyeOpen;
        private static Sprite eyeClosed;
        private static Sprite vignette;
        private static Sprite disc;
        private static Sprite question;
        private static Sprite exclamation;
        private static Sprite creak;

        public static Sprite EyeOpen => eyeOpen != null ? eyeOpen : eyeOpen = Draw(192, 112, OpenEye, "EyeOpen");
        public static Sprite EyeClosed => eyeClosed != null ? eyeClosed : eyeClosed = Draw(192, 112, ClosedEye, "EyeClosed");
        public static Sprite Vignette => vignette != null ? vignette : vignette = Draw(128, 128, VignetteAlpha, "Vignette");
        public static Sprite Disc => disc != null ? disc : disc = Draw(128, 128, DiscAlpha, "Disc");

        private static Sprite pulsePattern;

        /// <summary>
        /// M6 (docs/CONTRACT_M6.md 2.3): a dashed/striped border over the seen-moving edge pulse, so it carries a
        /// pattern as well as its colour (the calm and suspicious states never show it: Hud only shows it while
        /// seen moving).
        /// </summary>
        public static Sprite PulsePattern => pulsePattern != null ? pulsePattern : pulsePattern = Draw(128, 128, PulseStripes, "PulsePattern");

        /// <summary>M2: the floating "?" of an alerted inhabitant (and the suspicion icon of the HUD).</summary>
        public static Sprite Question => question != null ? question : question = Draw(96, 96, QuestionGlyph, "Question");

        /// <summary>M2: the "!" of an inhabitant who investigates or carries the furniture back.</summary>
        public static Sprite Exclamation => exclamation != null ? exclamation : exclamation = Draw(96, 96, ExclamationGlyph, "Exclamation");

        /// <summary>M2: a wood crack zigzag, the icon of the creak gauge.</summary>
        public static Sprite Creak => creak != null ? creak : creak = Draw(64, 64, CreakGlyph, "Creak");

        private static Sprite eyeAlarm;
        private static Sprite magnifier;

        /// <summary>
        /// M2.1: the alarm eye (seen and moving, or suspect). The open eye with alert strokes around it: it
        /// differs from the calm open eye by shape, not only by the backdrop color.
        /// </summary>
        public static Sprite EyeAlarm => eyeAlarm != null ? eyeAlarm : eyeAlarm = Draw(192, 112, AlarmEye, "EyeAlarm");

        /// <summary>M2.1: a magnifying glass, the icon of the suspicion bar (no longer the Alerted "?").</summary>
        public static Sprite Magnifier => magnifier != null ? magnifier : magnifier = Draw(64, 64, MagnifierGlyph, "Magnifier");

        private static Sprite rounded;
        private static Sprite chair;

        /// <summary>
        /// M3: a white rounded plate with a soft rim, nine sliced (24 px corners): menu buttons and panels, tinted
        /// by their color.
        /// </summary>
        public static Sprite Rounded => rounded != null ? rounded : rounded = Draw(64, 64, RoundedPlate, "Rounded", new Vector4(24f, 24f, 24f, 24f));

        /// <summary>M3: the red chair seen from the side, the title screen's emblem (the player is the red chair).</summary>
        public static Sprite Chair => chair != null ? chair : chair = Draw(128, 128, ChairGlyph, "Chair");

        private static Sprite sideFade;

        /// <summary>
        /// M7 title: a horizontal white ramp, opaque on its left half and easing to clear on the right (a smoothstep), the
        /// title page's translucent side panel once tinted and stretched over the left of the screen.
        /// </summary>
        public static Sprite SideFade => sideFade != null ? sideFade : sideFade = Draw(256, 8, SideFadeAlpha, "SideFade");

        private static Sprite chevron;

        /// <summary>
        /// M3.1: a filled, notched arrowhead (a chevron closed at the back) pointing up the sprite (+y), white over
        /// the dark outline so an Image tints the fill only. In front of an inhabitant's face, it shows where the
        /// inhabitant looks; filled, it still reads as a direction when it points diagonally (an open chevron then
        /// reads as the letter L).
        /// </summary>
        public static Sprite Chevron => chevron != null ? chevron : chevron = Draw(128, 128, ChevronGlyph, "Chevron");

        // ----- M4 HUD icons (docs/CONTRACT_M4.md amendment 9.12) -----

        private static Sprite slow;
        private static Sprite bulb;
        private static Sprite satOn;

        /// <summary>M4: a speed dial with its needle low, the icon of the careful hint (hud.careful).</summary>
        public static Sprite Slow => slow != null ? slow : slow = Draw(64, 64, SlowGlyph, "Slow");

        /// <summary>M4: a light bulb, the icon of the lamp hint (hud.lamp).</summary>
        public static Sprite Bulb => bulb != null ? bulb : bulb = Draw(64, 64, BulbGlyph, "Bulb");

        /// <summary>M4: the red chair under a heavy down arrow, the icon of the sat-on line (hud.satOn).</summary>
        public static Sprite SatOn => satOn != null ? satOn : satOn = Draw(96, 96, SatOnGlyph, "SatOn");

        private static Sprite tipped;

        /// <summary>M4.1: a stool on its side under a curved arrow (get back up), the icon of the tipped line (hud.tipped).</summary>
        public static Sprite Tipped => tipped != null ? tipped : tipped = Draw(96, 96, TippedGlyph, "Tipped");

        // ----- M5 HUD icons (docs/CONTRACT_M5_v3.md 4 and 15.5) -----

        private static Sprite eyeDog;
        private static Sprite door;

        /// <summary>
        /// M5: the dog eye (only the dog sees the furniture, HudEye.Dog). The open eye, smaller and lower, under two pointed
        /// dog ears: it differs from the calm and the alarm eyes by shape (the ears), not only by the backdrop colour.
        /// </summary>
        public static Sprite EyeDog => eyeDog != null ? eyeDog : eyeDog = Draw(192, 112, DogEye, "EyeDog");

        /// <summary>M5: a door ajar in its frame, with its knob, the icon of the door hint (hud.door).</summary>
        public static Sprite Door => door != null ? door : door = Draw(96, 96, DoorGlyph, "Door");

        private static Sprite balance;

        /// <summary>
        /// M5 wave 5B (CONTRACT_M5 6, 16.5): a vase leaning on a tilted plank over its fulcrum, the icon of the balance gauge
        /// (hud.balance).
        /// </summary>
        public static Sprite Balance => balance != null ? balance : balance = Draw(64, 64, BalanceGlyph, "Balance");

        /// <summary>
        /// Tests (the sprite textures are not readable once drawn): the alpha of an eye state's drawing on a
        /// <paramref name="width"/> x <paramref name="height"/> grid, row by row, with the same function and the same
        /// coordinates as its sprite. Two states differ by shape when their coverages differ, colour aside.
        /// </summary>
        public static float[] EyeCoverage(HudEye state, int width, int height)
        {
            PixelFn shader;
            switch (state)
            {
                case HudEye.Closed:
                    shader = ClosedEye;
                    break;
                case HudEye.Calm:
                    shader = OpenEye;
                    break;
                case HudEye.Dog:
                    shader = DogEye;
                    break;
                default:
                    shader = AlarmEye;
                    break;
            }
            var alpha = new float[width * height];
            // The eye sprites are 192 x 112: the same aspect, so the same shapes at any resolution.
            float aspect = 192f / 112f;
            float pixel = 2f / height;
            for (int y = 0; y < height; y++)
            {
                for (int x = 0; x < width; x++)
                {
                    float u = ((x + 0.5f) / width * 2f - 1f) * aspect;
                    float v = (y + 0.5f) / height * 2f - 1f;
                    alpha[y * width + x] = shader(u, v, pixel).a;
                }
            }
            return alpha;
        }

        private delegate Color PixelFn(float u, float v, float pixel);

        private static Sprite Draw(int width, int height, PixelFn shader, string name)
        {
            return Draw(width, height, shader, name, Vector4.zero);
        }

        private static Sprite Draw(int width, int height, PixelFn shader, string name, Vector4 border)
        {
            var texture = new Texture2D(width, height, TextureFormat.RGBA32, false)
            {
                name = name,
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear,
                hideFlags = HideFlags.DontUnloadUnusedAsset,
            };
            var pixels = new Color[width * height];
            float aspect = (float)width / height;
            float pixel = 2f / height;
            for (int y = 0; y < height; y++)
            {
                for (int x = 0; x < width; x++)
                {
                    // v in [-1, 1] vertically, u scaled by the aspect so circles stay round.
                    float u = ((x + 0.5f) / width * 2f - 1f) * aspect;
                    float v = (y + 0.5f) / height * 2f - 1f;
                    pixels[y * width + x] = shader(u, v, pixel);
                }
            }
            texture.SetPixels(pixels);
            texture.Apply(false, true);
            Sprite sprite = Sprite.Create(texture, new Rect(0, 0, width, height), new Vector2(0.5f, 0.5f), 100f, 0,
                SpriteMeshType.FullRect, border);
            sprite.name = name;
            sprite.hideFlags = HideFlags.DontUnloadUnusedAsset;
            return sprite;
        }

        private static float Cover(float signedDistance, float pixel)
        {
            // 1 inside, 0 outside, a one pixel smooth edge.
            return Mathf.Clamp01(0.5f - signedDistance / pixel);
        }

        private static Color Over(Color under, Color over, float alpha)
        {
            Color c = Color.Lerp(under, over, alpha);
            c.a = Mathf.Max(under.a, alpha * over.a);
            return c;
        }

        /// <summary>
        /// Almond shaped eye: white, dark outline, iris, pupil, highlight. <paramref name="openness"/> scales how far
        /// the lid opens (CONTRACT_M6 2.3): 1 is the original fully open eye (the alarm state keeps it, "wide open"),
        /// under 1 a half open eye (the calm/suspicious state), so the two differ by shape as well as by colour and
        /// by the badge each one overlays ("?" or "!", see <see cref="OpenEye"/> and <see cref="AlarmEye"/>).
        /// </summary>
        private static Color EyeShape(float u, float v, float pixel, float openness)
        {
            const float w = 1.45f;
            float x = u / w;
            float lid = openness * 0.78f * (1f - x * x);
            // Signed distance approximated by the vertical gap, good enough at this size.
            float almond = Mathf.Abs(x) >= 1f ? 1f : Mathf.Abs(v) - lid;
            float outline = 0.13f;
            Color ink = new Color(0.08f, 0.08f, 0.1f, 1f);
            Color c = new Color(0f, 0f, 0f, 0f);
            c = Over(c, ink, Cover(almond - outline, pixel));
            c = Over(c, new Color(0.98f, 0.98f, 0.96f, 1f), Cover(almond, pixel));
            float r = Mathf.Sqrt(u * u + v * v);
            float insideLid = Cover(almond, pixel);
            c = Over(c, new Color(0.16f, 0.36f, 0.62f, 1f), Cover(r - 0.52f, pixel) * insideLid);
            c = Over(c, ink, Cover(r - 0.26f, pixel) * insideLid);
            float hr = Mathf.Sqrt((u - 0.17f) * (u - 0.17f) + (v - 0.17f) * (v - 0.17f));
            c = Over(c, Color.white, Cover(hr - 0.09f, pixel) * insideLid);
            return c;
        }

        // M6 2.3: the corner badge every open eye overlays ("?" for calm/suspicious, "!" for alarm), upper right so
        // it never overlaps the lid at either openness nor AlarmEye's own alert strokes.
        private const float BadgeX = 1.05f;
        private const float BadgeY = 0.75f;
        private const float BadgeScale = 0.28f;

        /// <summary>
        /// The calm/suspicious eye: half open (CONTRACT_M6 2.3), with a "?" badge, so it differs from the alarm eye by
        /// shape (how far it opens, and the badge) as well as by colour.
        /// </summary>
        private static Color OpenEye(float u, float v, float pixel)
        {
            Color c = EyeShape(u, v, pixel, 0.55f);
            float mark = QuestionMarkSdf(new Vector2(u - BadgeX, v - BadgeY) / BadgeScale) * BadgeScale;
            return Over(c, new Color(1f, 0.84f, 0.22f, 1f), Cover(mark - 0.05f, pixel));
        }

        /// <summary>Signed distance (local, a roughly 2 unit tall glyph) to a "?": a hooked arc, a stem and a dot.</summary>
        private static float QuestionMarkSdf(Vector2 p)
        {
            Vector2 center = new Vector2(0f, 0.36f);
            const float radius = 0.3f;
            const float half = 0.085f;
            Vector2 d = p - center;
            float angle = Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg;
            float arc;
            // The arc runs from the bottom of the circle (-90 deg) counterclockwise over the top to 160 deg.
            if (angle >= -90f && angle <= 160f)
            {
                arc = Mathf.Abs(d.magnitude - radius) - half;
            }
            else
            {
                Vector2 capA = center + new Vector2(Mathf.Cos(160f * Mathf.Deg2Rad), Mathf.Sin(160f * Mathf.Deg2Rad)) * radius;
                Vector2 capB = center + new Vector2(0f, -radius);
                arc = Mathf.Min((p - capA).magnitude, (p - capB).magnitude) - half;
            }
            float stem = SegmentDistance(p, new Vector2(0f, center.y - radius), new Vector2(0f, -0.3f)) - half;
            float dot = (p - new Vector2(0f, -0.64f)).magnitude - 0.12f;
            return Mathf.Min(arc, Mathf.Min(stem, dot));
        }

        /// <summary>Signed distance (local units) to a "!": a tapered bar and a dot.</summary>
        private static float ExclamationMarkSdf(Vector2 p)
        {
            float t = Mathf.Clamp01((0.78f - p.y) / 1.08f);
            float bar = SegmentDistance(p, new Vector2(0f, 0.78f), new Vector2(0f, -0.3f)) - Mathf.Lerp(0.14f, 0.09f, t);
            float dot = (p - new Vector2(0f, -0.64f)).magnitude - 0.13f;
            return Mathf.Min(bar, dot);
        }

        /// <summary>Closed eye: a thick lower lid arc with three lashes.</summary>
        private static Color ClosedEye(float u, float v, float pixel)
        {
            const float w = 1.45f;
            float x = u / w;
            Color ink = new Color(0.9f, 0.9f, 0.88f, 1f);
            Color c = new Color(0f, 0f, 0f, 0f);
            if (Mathf.Abs(x) < 1.02f)
            {
                float arc = 0.25f - 0.55f * (1f - x * x);
                c = Over(c, ink, Cover(Mathf.Abs(v - arc) - 0.1f, pixel));
            }
            for (int i = -1; i <= 1; i++)
            {
                float lx = i * 0.62f;
                float baseY = 0.25f - 0.55f * (1f - (lx / w) * (lx / w));
                // Lash: a short segment from the lid downward and outward.
                Vector2 a = new Vector2(lx, baseY);
                Vector2 b = new Vector2(lx * 1.25f, baseY - 0.42f);
                float d = SegmentDistance(new Vector2(u, v), a, b) - 0.07f;
                c = Over(c, ink, Cover(d, pixel));
            }
            return c;
        }

        private static float SegmentDistance(Vector2 p, Vector2 a, Vector2 b)
        {
            Vector2 ab = b - a;
            float t = Mathf.Clamp01(Vector2.Dot(p - a, ab) / ab.sqrMagnitude);
            return (p - (a + ab * t)).magnitude;
        }

        /// <summary>Transparent center, opaque rounded edges: tinted red for the seen and moving pulse.</summary>
        private static Color VignetteAlpha(float u, float v, float pixel)
        {
            float r = Mathf.Pow(Mathf.Pow(Mathf.Abs(u), 6f) + Mathf.Pow(Mathf.Abs(v), 6f), 1f / 6f);
            float a = Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.62f, 1.0f, r));
            return new Color(1f, 1f, 1f, a);
        }

        private static Color DiscAlpha(float u, float v, float pixel)
        {
            float r = Mathf.Sqrt(u * u + v * v);
            return new Color(1f, 1f, 1f, Cover(r - 0.97f, pixel));
        }

        /// <summary>
        /// M6 (CONTRACT_M6 2.3): the same rounded border band as <see cref="VignetteAlpha"/>, cut into diagonal
        /// stripes (a 50 percent duty cycle): a pattern, not a plain glow, over the seen-moving pulse.
        /// </summary>
        private static Color PulseStripes(float u, float v, float pixel)
        {
            float r = Mathf.Pow(Mathf.Pow(Mathf.Abs(u), 6f) + Mathf.Pow(Mathf.Abs(v), 6f), 1f / 6f);
            float band = Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.62f, 1.0f, r));
            float stripe = Mathf.Repeat((u + v) * 9f, 1f) < 0.5f ? 1f : 0f;
            return new Color(1f, 1f, 1f, band * stripe);
        }

        // ----- M2 glyphs. Each is a signed distance shape: a dark outline under a colored fill, so the
        // glyph reads on a light wall as well as on a dark floor, in the world and on the HUD. -----

        private static readonly Color GlyphInk = new Color(0.08f, 0.07f, 0.09f, 1f);
        private const float GlyphOutline = 0.11f;

        private static Color Glyph(float distance, Color fill, float pixel)
        {
            Color c = new Color(0f, 0f, 0f, 0f);
            c = Over(c, GlyphInk, Cover(distance - GlyphOutline, pixel));
            return Over(c, fill, Cover(distance, pixel));
        }

        /// <summary>"?": a hook (an arc ending at its bottom point), a stem, and a dot.</summary>
        private static Color QuestionGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            Vector2 center = new Vector2(0f, 0.36f);
            const float radius = 0.3f;
            const float half = 0.085f;
            Vector2 d = p - center;
            float angle = Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg;
            float arc;
            // The arc runs from the bottom of the circle (-90 deg) counterclockwise over the top to 160 deg.
            if (angle >= -90f && angle <= 160f)
            {
                arc = Mathf.Abs(d.magnitude - radius) - half;
            }
            else
            {
                Vector2 capA = center + new Vector2(Mathf.Cos(160f * Mathf.Deg2Rad), Mathf.Sin(160f * Mathf.Deg2Rad)) * radius;
                Vector2 capB = center + new Vector2(0f, -radius);
                arc = Mathf.Min((p - capA).magnitude, (p - capB).magnitude) - half;
            }
            float stem = SegmentDistance(p, new Vector2(0f, center.y - radius), new Vector2(0f, -0.3f)) - half;
            float dot = (p - new Vector2(0f, -0.64f)).magnitude - 0.12f;
            return Glyph(Mathf.Min(arc, Mathf.Min(stem, dot)), new Color(1f, 0.84f, 0.22f, 1f), pixel);
        }

        /// <summary>"!": a tapered bar and a dot.</summary>
        private static Color ExclamationGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            // Wider at the top: the half width goes from 0.14 at the top to 0.09 at the bottom of the bar.
            float t = Mathf.Clamp01((0.78f - v) / 1.08f);
            float bar = SegmentDistance(p, new Vector2(0f, 0.78f), new Vector2(0f, -0.3f)) - Mathf.Lerp(0.14f, 0.09f, t);
            float dot = (p - new Vector2(0f, -0.64f)).magnitude - 0.13f;
            return Glyph(Mathf.Min(bar, dot), new Color(1f, 0.32f, 0.22f, 1f), pixel);
        }

        /// <summary>
        /// The alarm eye: wide open (CONTRACT_M6 2.3, full openness, slightly smaller) with three alert strokes above
        /// it and one on each side, and a "!" badge, so it differs from the calm/suspicious eye by openness and by
        /// badge, never only by the backdrop colour.
        /// </summary>
        private static Color AlarmEye(float u, float v, float pixel)
        {
            // Wide open, drawn at 80 % so the strokes fit around it.
            Color c = EyeShape(u / 0.8f, v / 0.8f + 0.12f, pixel / 0.8f, 1f);
            Color stroke = new Color(1f, 0.95f, 0.85f, 1f);
            Vector2 p = new Vector2(u, v);
            float d = float.MaxValue;
            d = Mathf.Min(d, SegmentDistance(p, new Vector2(0f, 0.64f), new Vector2(0f, 0.92f)));
            d = Mathf.Min(d, SegmentDistance(p, new Vector2(-0.5f, 0.56f), new Vector2(-0.68f, 0.82f)));
            d = Mathf.Min(d, SegmentDistance(p, new Vector2(0.5f, 0.56f), new Vector2(0.68f, 0.82f)));
            d = Mathf.Min(d, SegmentDistance(p, new Vector2(-1.32f, 0.02f), new Vector2(-1.62f, 0.1f)));
            d = Mathf.Min(d, SegmentDistance(p, new Vector2(1.32f, 0.02f), new Vector2(1.62f, 0.1f)));
            c = Over(c, stroke, Cover(d - 0.06f, pixel));
            float mark = ExclamationMarkSdf(new Vector2(u - BadgeX, v - BadgeY) / BadgeScale) * BadgeScale;
            return Over(c, new Color(1f, 0.32f, 0.22f, 1f), Cover(mark - 0.05f, pixel));
        }

        /// <summary>A magnifying glass: a lens ring and a handle.</summary>
        private static Color MagnifierGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            Vector2 lens = new Vector2(-0.18f, 0.18f);
            float ring = Mathf.Abs((p - lens).magnitude - 0.42f) - 0.1f;
            float handle = SegmentDistance(p, lens + new Vector2(0.36f, -0.36f), new Vector2(0.72f, -0.72f)) - 0.14f;
            return Glyph(Mathf.Min(ring, handle), new Color(0.98f, 0.62f, 0.3f, 1f), pixel);
        }

        /// <summary>A rounded square (radius 0.7 of the half size) with a lighter inner rim, white so it tints.</summary>
        private static Color RoundedPlate(float u, float v, float pixel)
        {
            const float half = 0.97f;
            const float radius = 0.72f;
            Vector2 q = new Vector2(Mathf.Abs(u), Mathf.Abs(v)) - new Vector2(half - radius, half - radius);
            float outside = new Vector2(Mathf.Max(q.x, 0f), Mathf.Max(q.y, 0f)).magnitude + Mathf.Min(Mathf.Max(q.x, q.y), 0f) - radius;
            float cover = Cover(outside, pixel);
            // A thin rim 0.08 inside the edge reads as a bevel once tinted.
            float rim = Cover(Mathf.Abs(outside + 0.1f) - 0.04f, pixel);
            float shade = Mathf.Lerp(0.86f, 1f, rim);
            return new Color(shade, shade, shade, cover);
        }

        private static Color SideFadeAlpha(float u, float v, float pixel)
        {
            // u spans [-32, 32] on the 256 x 8 sprite: t runs 0 (left edge) to 1 (right edge).
            float t = (u / 32f + 1f) * 0.5f;
            float k = Mathf.Clamp01((t - 0.45f) / 0.55f);
            return new Color(1f, 1f, 1f, 1f - k * k * (3f - 2f * k));
        }

        /// <summary>A chair in profile: a backrest post, a seat, two legs, in the player red over the dark outline.</summary>
        private static Color ChairGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            float back = SegmentDistance(p, new Vector2(-0.38f, 0.78f), new Vector2(-0.38f, -0.02f)) - 0.1f;
            float seat = SegmentDistance(p, new Vector2(-0.38f, -0.02f), new Vector2(0.42f, -0.02f)) - 0.1f;
            float legBack = SegmentDistance(p, new Vector2(-0.36f, -0.02f), new Vector2(-0.4f, -0.8f)) - 0.07f;
            float legFront = SegmentDistance(p, new Vector2(0.4f, -0.02f), new Vector2(0.44f, -0.8f)) - 0.07f;
            // A point, not a segment: SegmentDistance divides by the segment's length.
            float rail = (p - new Vector2(-0.38f, 0.5f)).magnitude - 0.13f;
            float d = Mathf.Min(Mathf.Min(back, seat), Mathf.Min(Mathf.Min(legBack, legFront), rail));
            return Glyph(d, new Color(0.84f, 0.12f, 0.12f, 1f), pixel);
        }

        private static readonly Vector2[] ArrowHead =
        {
            new Vector2(0f, 0.8f), new Vector2(0.62f, -0.72f), new Vector2(0f, -0.3f), new Vector2(-0.62f, -0.72f),
        };

        /// <summary>The notched arrowhead: signed distance to the polygon (negative inside), white over the glyph ink.</summary>
        private static Color ChevronGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            float distance = float.MaxValue;
            bool inside = false;
            for (int i = 0, j = ArrowHead.Length - 1; i < ArrowHead.Length; j = i++)
            {
                Vector2 a = ArrowHead[i];
                Vector2 b = ArrowHead[j];
                distance = Mathf.Min(distance, SegmentDistance(p, a, b));
                // Even-odd crossing test along +x.
                if ((a.y > p.y) != (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x)
                {
                    inside = !inside;
                }
            }
            return Glyph(inside ? -distance : distance, Color.white, pixel);
        }

        /// <summary>A crack: a zigzag of four segments, in warm wood.</summary>
        private static Color CreakGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            Vector2 a = new Vector2(-0.3f, 0.8f);
            Vector2 b = new Vector2(0.25f, 0.25f);
            Vector2 c = new Vector2(-0.25f, -0.05f);
            Vector2 d = new Vector2(0.3f, -0.4f);
            Vector2 e = new Vector2(-0.05f, -0.8f);
            float dist = Mathf.Min(Mathf.Min(SegmentDistance(p, a, b), SegmentDistance(p, b, c)),
                Mathf.Min(SegmentDistance(p, c, d), SegmentDistance(p, d, e))) - 0.1f;
            return Glyph(dist, new Color(0.93f, 0.68f, 0.38f, 1f), pixel);
        }

        // ----- M4 glyphs -----

        /// <summary>A half dial (an arc over a base line) with its needle pointing low, to the left.</summary>
        private static Color SlowGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            Vector2 center = new Vector2(0f, -0.35f);
            Vector2 d = p - center;
            float arc = d.y >= 0f ? Mathf.Abs(d.magnitude - 0.72f) - 0.09f : float.MaxValue;
            float baseLine = SegmentDistance(p, center + new Vector2(-0.81f, 0f), center + new Vector2(0.81f, 0f)) - 0.09f;
            // The needle at 160 deg: almost flat, pointing at the slow end of the dial.
            Vector2 tip = center + new Vector2(Mathf.Cos(160f * Mathf.Deg2Rad), Mathf.Sin(160f * Mathf.Deg2Rad)) * 0.6f;
            float needle = SegmentDistance(p, center, tip) - 0.08f;
            float hub = (p - center).magnitude - 0.15f;
            float dist = Mathf.Min(Mathf.Min(arc, baseLine), Mathf.Min(needle, hub));
            return Glyph(dist, new Color(0.62f, 0.86f, 1f, 1f), pixel);
        }

        /// <summary>A bulb: a round glass over a narrow neck and a screw base, warm yellow.</summary>
        private static Color BulbGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            float glass = (p - new Vector2(0f, 0.22f)).magnitude - 0.5f;
            float neck = SegmentDistance(p, new Vector2(0f, -0.1f), new Vector2(0f, -0.42f)) - 0.22f;
            float screw = SegmentDistance(p, new Vector2(-0.16f, -0.62f), new Vector2(0.16f, -0.62f)) - 0.1f;
            float dist = Mathf.Min(Mathf.Min(glass, neck), screw);
            Color c = Glyph(dist, new Color(1f, 0.86f, 0.32f, 1f), pixel);
            // The screw base in grey over the yellow glass.
            float metal = Mathf.Min(SegmentDistance(p, new Vector2(-0.18f, -0.44f), new Vector2(0.18f, -0.44f)) - 0.07f, screw);
            return Over(c, new Color(0.62f, 0.6f, 0.58f, 1f), Cover(metal, pixel));
        }

        /// <summary>The player's red chair, lower in the sprite, under a thick downward arrow (someone sits on it).</summary>
        private static Color SatOnGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            Vector2 c = new Vector2(0.08f, -0.42f);
            const float s = 0.55f;
            float back = SegmentDistance(p, c + s * new Vector2(-0.38f, 0.78f), c + s * new Vector2(-0.38f, -0.02f)) - 0.07f;
            float seat = SegmentDistance(p, c + s * new Vector2(-0.38f, -0.02f), c + s * new Vector2(0.42f, -0.02f)) - 0.07f;
            float legBack = SegmentDistance(p, c + s * new Vector2(-0.36f, -0.02f), c + s * new Vector2(-0.4f, -0.8f)) - 0.05f;
            float legFront = SegmentDistance(p, c + s * new Vector2(0.4f, -0.02f), c + s * new Vector2(0.44f, -0.8f)) - 0.05f;
            float chairShape = Mathf.Min(Mathf.Min(back, seat), Mathf.Min(legBack, legFront));
            Color color = Glyph(chairShape, new Color(0.84f, 0.12f, 0.12f, 1f), pixel);
            // The arrow: a shaft and a head pointing down onto the seat. The head is the triangle above its tip
            // (|x| below 0.89 times the height over the tip) and under its base line, 0.36 above the tip.
            Vector2 tipAt = new Vector2(0.1f, -0.1f);
            float shaft = SegmentDistance(p, new Vector2(0.1f, 0.82f), tipAt + new Vector2(0f, 0.3f)) - 0.1f;
            Vector2 q = p - tipAt;
            float head = Mathf.Max((Mathf.Abs(q.x) - 0.89f * q.y) / 1.338f, q.y - 0.36f);
            Color arrow = Glyph(Mathf.Min(shaft, head), new Color(1f, 0.93f, 0.75f, 1f), pixel);
            return Over(color, arrow, arrow.a);
        }

        /// <summary>
        /// A red stool lying on its side (its seat on the left, three legs pointing right), under an arc arrow turning
        /// it back upright (counterclockwise, from its legs to over its seat).
        /// </summary>
        private static Color TippedGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            // The seat: a short vertical bar at the left; the legs: three bars to the right, slightly splayed.
            float seat = SegmentDistance(p, new Vector2(-0.55f, -0.78f), new Vector2(-0.55f, -0.18f)) - 0.09f;
            float leg1 = SegmentDistance(p, new Vector2(-0.5f, -0.28f), new Vector2(0.62f, -0.18f)) - 0.05f;
            float leg2 = SegmentDistance(p, new Vector2(-0.5f, -0.48f), new Vector2(0.62f, -0.48f)) - 0.05f;
            float leg3 = SegmentDistance(p, new Vector2(-0.5f, -0.68f), new Vector2(0.62f, -0.78f)) - 0.05f;
            float stool = Mathf.Min(Mathf.Min(seat, leg1), Mathf.Min(leg2, leg3));
            Color color = Glyph(stool, new Color(0.84f, 0.12f, 0.12f, 1f), pixel);
            // The arc: a quarter circle above, from the legs' end (right) round to the top left, with its head there.
            Vector2 center = new Vector2(0f, -0.2f);
            Vector2 d = p - center;
            float angle = Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg;
            float arc = angle >= 15f && angle <= 140f ? Mathf.Abs(d.magnitude - 0.68f) - 0.07f : float.MaxValue;
            Vector2 tipAt = center + new Vector2(Mathf.Cos(150f * Mathf.Deg2Rad), Mathf.Sin(150f * Mathf.Deg2Rad)) * 0.68f;
            float head = (p - tipAt).magnitude - 0.17f;
            Color arrow = Glyph(Mathf.Min(arc, head), new Color(1f, 0.93f, 0.75f, 1f), pixel);
            return Over(color, arrow, arrow.a);
        }

        // ----- M5 glyphs -----

        // The dog's ears: two pointed triangles above the eye (sprite units, v up), the outer one leaning out.
        private static readonly Vector2[] LeftEar =
        {
            new Vector2(-1.32f, 0.22f), new Vector2(-1.2f, 0.97f), new Vector2(-0.5f, 0.4f),
        };

        private static readonly Vector2[] RightEar =
        {
            new Vector2(1.32f, 0.22f), new Vector2(0.5f, 0.4f), new Vector2(1.2f, 0.97f),
        };

        private static readonly Vector2[] LeftInnerEar =
        {
            new Vector2(-1.15f, 0.36f), new Vector2(-1.13f, 0.76f), new Vector2(-0.78f, 0.45f),
        };

        private static readonly Vector2[] RightInnerEar =
        {
            new Vector2(1.15f, 0.36f), new Vector2(0.78f, 0.45f), new Vector2(1.13f, 0.76f),
        };

        /// <summary>The dog eye: two pointed ears (warm orange, pink inside) behind the open eye drawn at 78 %, lower.</summary>
        private static Color DogEye(float u, float v, float pixel)
        {
            var p = new Vector2(u, v);
            float ears = Mathf.Min(PolygonDistance(p, LeftEar), PolygonDistance(p, RightEar));
            Color c = Glyph(ears, new Color(0.96f, 0.6f, 0.24f, 1f), pixel);
            float inner = Mathf.Min(PolygonDistance(p, LeftInnerEar), PolygonDistance(p, RightInnerEar));
            c = Over(c, new Color(0.98f, 0.78f, 0.72f, 1f), Cover(inner, pixel) * c.a);
            // M6: the fully open eye with no badge (never OpenEye's calm/suspicious half open "?": the dog's own shape
            // is the ears, not a badge shared with another state).
            Color eye = EyeShape(u / 0.78f, (v + 0.2f) / 0.78f, pixel / 0.78f, 1f);
            return Over(c, eye, eye.a);
        }

        /// <summary>A door ajar: the frame (posts and lintel), the leaf turned toward the viewer, and its knob.</summary>
        private static Color DoorGlyph(float u, float v, float pixel)
        {
            var p = new Vector2(u, v);
            float frame = Mathf.Min(
                Mathf.Min(SegmentDistance(p, new Vector2(-0.52f, -0.86f), new Vector2(-0.52f, 0.84f)),
                    SegmentDistance(p, new Vector2(0.52f, -0.86f), new Vector2(0.52f, 0.84f))),
                SegmentDistance(p, new Vector2(-0.52f, 0.84f), new Vector2(0.52f, 0.84f))) - 0.07f;
            Color c = Glyph(frame, new Color(0.93f, 0.9f, 0.84f, 1f), pixel);
            // The leaf hinged on the left post, swung toward the viewer: its free edge comes out to the right and lower.
            float leaf = PolygonDistance(p, DoorLeafShape);
            Color wood = Glyph(leaf, new Color(0.86f, 0.62f, 0.34f, 1f), pixel);
            c = Over(c, wood, wood.a);
            float knob = (p - new Vector2(0.38f, -0.06f)).magnitude - 0.08f;
            return Over(c, GlyphInk, Cover(knob, pixel));
        }

        private static readonly Vector2[] DoorLeafShape =
        {
            new Vector2(-0.45f, -0.8f), new Vector2(-0.45f, 0.78f), new Vector2(0.52f, 0.62f), new Vector2(0.52f, -0.96f),
        };

        // M5 wave 5B: the balance icon's fulcrum, a triangle under the plank.
        private static readonly Vector2[] BalanceFulcrum =
        {
            new Vector2(0f, -0.38f), new Vector2(-0.26f, -0.86f), new Vector2(0.26f, -0.86f),
        };

        /// <summary>
        /// The balance icon: a cream plank tilted up to the right over its fulcrum, and a blue vase (a round body, a neck and a
        /// lip) leaning to the right on it, as a load about to slide off.
        /// </summary>
        private static Color BalanceGlyph(float u, float v, float pixel)
        {
            var p = new Vector2(u, v);
            float plank = SegmentDistance(p, new Vector2(-0.86f, -0.5f), new Vector2(0.86f, -0.22f)) - 0.07f;
            float fulcrum = PolygonDistance(p, BalanceFulcrum);
            Color c = Glyph(Mathf.Min(plank, fulcrum), new Color(0.93f, 0.9f, 0.84f, 1f), pixel);
            // The vase stands on the plank left of the fulcrum, its neck leaning right.
            float body = (p - new Vector2(-0.12f, -0.02f)).magnitude - 0.27f;
            float neck = SegmentDistance(p, new Vector2(-0.08f, 0.2f), new Vector2(0.06f, 0.58f)) - 0.08f;
            float lip = SegmentDistance(p, new Vector2(-0.07f, 0.64f), new Vector2(0.2f, 0.58f)) - 0.06f;
            Color vase = Glyph(Mathf.Min(body, Mathf.Min(neck, lip)), new Color(0.36f, 0.58f, 0.85f, 1f), pixel);
            return Over(c, vase, vase.a);
        }

        /// <summary>The signed distance from a point to a simple polygon (negative inside): even-odd crossings, edge distance.</summary>
        private static float PolygonDistance(Vector2 p, Vector2[] polygon)
        {
            float distance = float.MaxValue;
            bool inside = false;
            for (int i = 0, j = polygon.Length - 1; i < polygon.Length; j = i++)
            {
                Vector2 a = polygon[i];
                Vector2 b = polygon[j];
                distance = Mathf.Min(distance, SegmentDistance(p, a, b));
                if ((a.y > p.y) != (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x)
                {
                    inside = !inside;
                }
            }
            return inside ? -distance : distance;
        }

        /// <summary>Signed distance to a rounded box (negative inside), the same shape as <see cref="RoundedPlate"/> but
        /// reusable at any size and corner radius: a mouse body, a speaker's driver box, a quality bar.</summary>
        private static float RoundedBoxDistance(Vector2 p, Vector2 half, float radius)
        {
            Vector2 q = new Vector2(Mathf.Abs(p.x), Mathf.Abs(p.y)) - (half - new Vector2(radius, radius));
            return new Vector2(Mathf.Max(q.x, 0f), Mathf.Max(q.y, 0f)).magnitude + Mathf.Min(Mathf.Max(q.x, q.y), 0f) - radius;
        }

        // ----- M7 options page icons (Menu.OptionsRow): one small glyph per row, warm palette, 64 x 64. -----

        private static Sprite optionMouse;
        private static Sprite optionSpeaker;
        private static Sprite optionSightCone;
        private static Sprite optionQualityBars;
        private static Sprite optionDifficultyGauge;
        private static Sprite optionGlobe;

        /// <summary>Sensitivity: a mouse seen from above (a capsule body, a scroll wheel notch, a button split).</summary>
        public static Sprite OptionMouse => optionMouse != null ? optionMouse : optionMouse = Draw(64, 64, OptionMouseGlyph, "OptionMouse");

        /// <summary>Volume: a speaker (driver box and cone) with two sound arcs.</summary>
        public static Sprite OptionSpeaker => optionSpeaker != null ? optionSpeaker : optionSpeaker = Draw(64, 64, OptionSpeakerGlyph, "OptionSpeaker");

        /// <summary>Audio overhaul, Music: two beamed eighth notes (two tilted heads, their stems, one thick beam).</summary>
        public static Sprite OptionMusicNote => optionMusicNote != null ? optionMusicNote : optionMusicNote = Draw(64, 64, OptionMusicGlyph, "OptionMusicNote");

        private static Sprite optionMusicNote;

        private static Color OptionMusicGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            float heads = float.MaxValue;
            float stems = float.MaxValue;
            Vector2[] at = { new Vector2(-0.42f, -0.5f), new Vector2(0.38f, -0.36f) };
            foreach (Vector2 c in at)
            {
                // A head: an ellipse tilted up to the right, like engraved note heads.
                Vector2 d = p - c;
                float cos = Mathf.Cos(0.45f);
                float sin = Mathf.Sin(0.45f);
                Vector2 r = new Vector2(d.x * cos + d.y * sin, -d.x * sin + d.y * cos);
                float head = (new Vector2(r.x / 0.24f, r.y / 0.16f).magnitude - 1f) * 0.16f;
                heads = Mathf.Min(heads, head);
                Vector2 top = new Vector2(c.x + 0.2f, c.y + 1.02f);
                stems = Mathf.Min(stems, SegmentDistance(p, new Vector2(c.x + 0.2f, c.y + 0.05f), top) - 0.05f);
            }
            float beam = SegmentDistance(p, new Vector2(at[0].x + 0.2f, at[0].y + 0.94f), new Vector2(at[1].x + 0.2f, at[1].y + 0.94f)) - 0.1f;
            float dist = Mathf.Min(heads, Mathf.Min(stems, beam));
            return Glyph(dist, new Color(0.98f, 0.74f, 0.42f, 1f), pixel);
        }

        /// <summary>Vision cone: a spotlight cone opening upward from a small eye at its point.</summary>
        public static Sprite OptionSightCone => optionSightCone != null ? optionSightCone : optionSightCone = Draw(64, 64, OptionSightConeGlyph, "OptionSightCone");

        /// <summary>Quality: three ascending bars, like a level meter.</summary>
        public static Sprite OptionQualityBars => optionQualityBars != null ? optionQualityBars : optionQualityBars = Draw(64, 64, OptionQualityGlyph, "OptionQualityBars");

        /// <summary>Difficulty: a warning gauge (arc, three ticks, a needle toward the hard end).</summary>
        public static Sprite OptionDifficultyGauge => optionDifficultyGauge != null ? optionDifficultyGauge : optionDifficultyGauge = Draw(64, 64, OptionDifficultyGlyph, "OptionDifficultyGauge");

        /// <summary>Language: a globe (an outer ring, an equator, a meridian).</summary>
        public static Sprite OptionGlobe => optionGlobe != null ? optionGlobe : optionGlobe = Draw(64, 64, OptionGlobeGlyph, "OptionGlobe");

        private static Color OptionMouseGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            // A tall capsule (radius equal to the half width rounds both ends fully): the mouse's body.
            float body = RoundedBoxDistance(p, new Vector2(0.44f, 0.8f), 0.44f);
            Color c = Glyph(body, new Color(0.93f, 0.86f, 0.72f, 1f), pixel);
            float wheel = SegmentDistance(p, new Vector2(0f, 0.5f), new Vector2(0f, 0.2f)) - 0.05f;
            float divide = SegmentDistance(p, new Vector2(0f, 0.3f), new Vector2(0f, -0.68f)) - 0.025f;
            c = Over(c, GlyphInk, Cover(wheel, pixel));
            c = Over(c, GlyphInk, Cover(divide, pixel));
            return c;
        }

        private static Color OptionSpeakerGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            float box = RoundedBoxDistance(p - new Vector2(-0.42f, 0f), new Vector2(0.18f, 0.32f), 0.06f);
            var cone = new[]
            {
                new Vector2(-0.24f, 0.32f), new Vector2(0.32f, 0.72f), new Vector2(0.32f, -0.72f), new Vector2(-0.24f, -0.32f),
            };
            float coneDist = PolygonDistance(p, cone);
            Color fill = new Color(1f, 0.82f, 0.36f, 1f);
            Color c = Glyph(Mathf.Min(box, coneDist), fill, pixel);
            // Two sound arcs to the right, each only drawn on its forward-facing half.
            Vector2 center = new Vector2(0.1f, 0f);
            Vector2 d = p - center;
            float angle = Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg;
            float arc1 = Mathf.Abs(angle) < 55f ? Mathf.Abs(d.magnitude - 0.5f) - 0.045f : float.MaxValue;
            float arc2 = Mathf.Abs(angle) < 42f ? Mathf.Abs(d.magnitude - 0.72f) - 0.045f : float.MaxValue;
            Color arcs = Glyph(Mathf.Min(arc1, arc2), fill, pixel);
            return Over(c, arcs, arcs.a);
        }

        private static readonly Vector2[] SightConeShape =
        {
            new Vector2(0f, -0.74f), new Vector2(0.52f, 0.68f), new Vector2(-0.52f, 0.68f),
        };

        private static Color OptionSightConeGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            float cone = PolygonDistance(p, SightConeShape);
            Color c = Glyph(cone, new Color(0.98f, 0.68f, 0.3f, 1f), pixel);
            Vector2 eyeAt = new Vector2(0f, -0.74f);
            float ring = (p - eyeAt).magnitude - 0.15f;
            c = Over(c, GlyphInk, Cover(ring, pixel));
            float pupil = (p - eyeAt).magnitude - 0.07f;
            c = Over(c, new Color(0.97f, 0.95f, 0.9f, 1f), Cover(pupil, pixel));
            return c;
        }

        private static Color OptionQualityGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            float bar1 = RoundedBoxDistance(p - new Vector2(-0.44f, -0.52f), new Vector2(0.15f, 0.25f), 0.05f);
            float bar2 = RoundedBoxDistance(p - new Vector2(0f, -0.28f), new Vector2(0.15f, 0.49f), 0.05f);
            float bar3 = RoundedBoxDistance(p - new Vector2(0.44f, 0.04f), new Vector2(0.15f, 0.73f), 0.05f);
            float dist = Mathf.Min(bar1, Mathf.Min(bar2, bar3));
            return Glyph(dist, new Color(0.95f, 0.56f, 0.24f, 1f), pixel);
        }

        private static Color OptionDifficultyGlyph(float u, float v, float pixel)
        {
            // The same half dial as SlowGlyph, ticked at three stops and needled toward the hard (right) end.
            Vector2 p = new Vector2(u, v);
            Vector2 center = new Vector2(0f, -0.35f);
            Vector2 d = p - center;
            float arc = d.y >= 0f ? Mathf.Abs(d.magnitude - 0.72f) - 0.09f : float.MaxValue;
            float baseLine = SegmentDistance(p, center + new Vector2(-0.81f, 0f), center + new Vector2(0.81f, 0f)) - 0.09f;
            float ticks = float.MaxValue;
            for (int i = 0; i < 3; i++)
            {
                float angle = Mathf.Lerp(20f, 160f, i / 2f);
                Vector2 dir = new Vector2(Mathf.Cos(angle * Mathf.Deg2Rad), Mathf.Sin(angle * Mathf.Deg2Rad));
                ticks = Mathf.Min(ticks, (p - (center + dir * 0.72f)).magnitude - 0.06f);
            }
            Vector2 tip = center + new Vector2(Mathf.Cos(35f * Mathf.Deg2Rad), Mathf.Sin(35f * Mathf.Deg2Rad)) * 0.6f;
            float needle = SegmentDistance(p, center, tip) - 0.08f;
            float hub = (p - center).magnitude - 0.15f;
            float dist = Mathf.Min(Mathf.Min(arc, baseLine), Mathf.Min(Mathf.Min(needle, hub), ticks));
            return Glyph(dist, new Color(0.84f, 0.18f, 0.14f, 1f), pixel);
        }

        private static Color OptionGlobeGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            float ring = Mathf.Abs(p.magnitude - 0.75f) - 0.07f;
            float equator = SegmentDistance(p, new Vector2(-0.75f, 0f), new Vector2(0.75f, 0f)) - 0.035f;
            // The meridian: a thin band around an ellipse through the poles, narrow across so it reads as a curve on each side.
            float nx = p.x / 0.3f;
            float ny = p.y / 0.75f;
            float ellipse = (Mathf.Sqrt(nx * nx + ny * ny) - 1f) * 0.3f;
            float meridian = Mathf.Abs(ellipse) - 0.035f;
            float dist = Mathf.Min(ring, Mathf.Min(equator, meridian));
            return Glyph(dist, new Color(0.46f, 0.64f, 0.86f, 1f), pixel);
        }

        // ----- M7 walls pass: the Walls and Wall opacity rows (Menu.OptionsRow) -----

        private static Sprite optionWalls;
        private static Sprite optionWallOpacity;

        /// <summary>Walls: a standing wall beside a lowered one (its stub solid, its full height a thin outline).</summary>
        public static Sprite OptionWalls => optionWalls != null ? optionWalls : optionWalls = Draw(64, 64, OptionWallsGlyph, "OptionWalls");

        /// <summary>Wall opacity: a wall pane half solid, half faded, with a thin outline around the faded half.</summary>
        public static Sprite OptionWallOpacity => optionWallOpacity != null ? optionWallOpacity : optionWallOpacity = Draw(64, 64, OptionWallOpacityGlyph, "OptionWallOpacity");

        private static readonly Color WallGlyphFill = new Color(0.93f, 0.84f, 0.68f, 1f);

        private static Color OptionWallsGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            float standing = RoundedBoxDistance(p - new Vector2(-0.42f, 0f), new Vector2(0.3f, 0.78f), 0.04f);
            float stub = RoundedBoxDistance(p - new Vector2(0.42f, -0.6f), new Vector2(0.3f, 0.18f), 0.04f);
            Color c = Glyph(Mathf.Min(standing, stub), WallGlyphFill, pixel);
            float outline = Mathf.Abs(RoundedBoxDistance(p - new Vector2(0.42f, 0f), new Vector2(0.3f, 0.78f), 0.04f)) - 0.03f;
            return Over(c, WallGlyphFill, Cover(outline, pixel) * 0.8f);
        }

        private static Color OptionWallOpacityGlyph(float u, float v, float pixel)
        {
            Vector2 p = new Vector2(u, v);
            float solid = RoundedBoxDistance(p - new Vector2(-0.38f, 0f), new Vector2(0.34f, 0.78f), 0.04f);
            Color c = Glyph(solid, WallGlyphFill, pixel);
            float faded = RoundedBoxDistance(p - new Vector2(0.38f, 0f), new Vector2(0.34f, 0.78f), 0.04f);
            c = Over(c, WallGlyphFill, Cover(faded, pixel) * 0.35f);
            float outline = Mathf.Abs(faded) - 0.03f;
            return Over(c, WallGlyphFill, Cover(outline, pixel) * 0.9f);
        }
    }
}
