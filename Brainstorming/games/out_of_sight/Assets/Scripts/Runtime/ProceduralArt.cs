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

        // ----- STARSANIM (docs/next/progress/STARSANIM.md): the end screen's star burst (WinStarsView), white to tint. -----
        private static Sprite burstRing;
        private static Sprite softGlow;
        private static Sprite sparkle;

        /// <summary>STARSANIM: a thin ring with soft edges, expanded and faded around a star as it fills.</summary>
        public static Sprite BurstRing => burstRing != null ? burstRing : burstRing = Draw(128, 128, BurstRingAlpha, "BurstRing");

        /// <summary>STARSANIM: a soft round glow (bright at the centre, nothing at the rim), the flash behind a filling star.</summary>
        public static Sprite SoftGlow => softGlow != null ? softGlow : softGlow = Draw(64, 64, SoftGlowAlpha, "SoftGlow");

        /// <summary>STARSANIM: a four point twinkle with a round core, the sparkles flying out of a filling star.</summary>
        public static Sprite Sparkle => sparkle != null ? sparkle : sparkle = Draw(64, 64, SparkleAlpha, "Sparkle");

        // ----- CONFETTI (2026-11-27, docs/next/progress/STARSANIM.md "Confetti"): the shower's pieces, white to tint. -----
        private static Sprite[] confettiShapes;

        /// <summary>CONFETTI: the index of each piece shape in <see cref="ConfettiShapes"/>.</summary>
        public const int ConfettiSquare = 0;
        public const int ConfettiDisc = 1;
        public const int ConfettiCurl = 2;
        public const int ConfettiWave = 3;

        /// <summary>
        /// CONFETTI: the confetti pieces' shapes, four 32 x 32 cells of one 128 x 32 texture (so the whole shower batches into
        /// one draw call): a paper square (stretched into rectangles and streamer strips), a disc, a curled ribbon (an open
        /// ring) and a wavy streamer. Each keeps a clear texel all round, so the bilinear filter never bleeds a neighbour in.
        /// </summary>
        public static Sprite[] ConfettiShapes => confettiShapes ?? (confettiShapes = DrawCells(32, "Confetti",
            ConfettiSquareAlpha, ConfettiDiscAlpha, ConfettiCurlAlpha, ConfettiWaveAlpha));

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

        /// <summary>
        /// CONFETTI: one texture holding a row of <paramref name="cell"/> square cells, one per shader, and a sprite per cell
        /// (no mipmaps, bilinear, not readable). Each shader sees u and v in [-1, 1] over its own cell.
        /// </summary>
        private static Sprite[] DrawCells(int cell, string name, params PixelFn[] shaders)
        {
            int count = shaders.Length;
            int width = cell * count;
            var texture = new Texture2D(width, cell, TextureFormat.RGBA32, false)
            {
                name = name,
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear,
                hideFlags = HideFlags.DontUnloadUnusedAsset,
            };
            var pixels = new Color[width * cell];
            float pixel = 2f / cell;
            for (int k = 0; k < count; k++)
            {
                for (int y = 0; y < cell; y++)
                {
                    for (int x = 0; x < cell; x++)
                    {
                        float u = (x + 0.5f) / cell * 2f - 1f;
                        float v = (y + 0.5f) / cell * 2f - 1f;
                        pixels[y * width + k * cell + x] = shaders[k](u, v, pixel);
                    }
                }
            }
            texture.SetPixels(pixels);
            texture.Apply(false, true);
            var sprites = new Sprite[count];
            for (int k = 0; k < count; k++)
            {
                Sprite sprite = Sprite.Create(texture, new Rect(k * cell, 0, cell, cell), new Vector2(0.5f, 0.5f), 100f, 0,
                    SpriteMeshType.FullRect);
                sprite.name = name + k;
                sprite.hideFlags = HideFlags.DontUnloadUnusedAsset;
                sprites[k] = sprite;
            }
            return sprites;
        }

        /// <summary>CONFETTI: a paper square to the cell's edge (less one texel), a faint sheen brighter at the top.</summary>
        private static Color ConfettiSquareAlpha(float u, float v, float pixel)
        {
            float a = Cover(Mathf.Max(Mathf.Abs(u), Mathf.Abs(v)) - 0.88f, pixel);
            float l = 0.88f + 0.12f * (v + 1f) * 0.5f;
            return new Color(l, l, l, a);
        }

        /// <summary>CONFETTI: a round paper dot.</summary>
        private static Color ConfettiDiscAlpha(float u, float v, float pixel)
        {
            return new Color(1f, 1f, 1f, Cover(Mathf.Sqrt(u * u + v * v) - 0.86f, pixel));
        }

        /// <summary>CONFETTI: a curled ribbon, three quarters of a thick ring with rounded ends (open at the right).</summary>
        private static Color ConfettiCurlAlpha(float u, float v, float pixel)
        {
            const float radius = 0.6f;
            const float half = 0.17f;
            float r = Mathf.Sqrt(u * u + v * v);
            float band = Mathf.Abs(r - radius) - half;
            // The open quarter (angles -45 to 45 degrees): the band ends there in two round caps.
            float angle = Mathf.Atan2(v, u) * Mathf.Rad2Deg;
            if (angle > -45f && angle < 45f)
            {
                float c = 0.70710678f * radius;
                float end1 = Mathf.Sqrt((u - c) * (u - c) + (v - c) * (v - c)) - half;
                float end2 = Mathf.Sqrt((u - c) * (u - c) + (v + c) * (v + c)) - half;
                band = Mathf.Min(end1, end2);
            }
            return new Color(1f, 1f, 1f, Cover(band, pixel));
        }

        /// <summary>CONFETTI: a wavy streamer, a band snaking up the cell (one and a half waves), its ends cut square.</summary>
        private static Color ConfettiWaveAlpha(float u, float v, float pixel)
        {
            float centre = 0.42f * Mathf.Sin(v * Mathf.PI * 1.5f);
            float band = Mathf.Abs(u - centre) - 0.24f;
            float ends = Mathf.Abs(v) - 0.88f;
            return new Color(1f, 1f, 1f, Cover(Mathf.Max(band, ends), pixel));
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

        // Eye redesign (2026-11-20): the open eyes are drawn in the closed eye's line (ClosedEye): its cream ink, its 0.1
        // lid stroke and its three 0.07 lashes leaning out, on an almond as wide as its arc (EyeHalfWidth). The lids meet
        // at the corners (EyeCorner); the lower lid's curve is EyeLowLid, the upper lid's the eye's openness.
        private const float EyeHalfWidth = 1.45f;
        private const float EyeCorner = -0.18f;
        private const float EyeLowLid = 0.34f;
        private static readonly Color EyeInk = new Color(0.9f, 0.9f, 0.88f, 1f);

        private static Sprite eyeHalf;

        /// <summary>
        /// Eye redesign (2026-11-20): the half open eye, lids nearly shut and the iris peeking: the blink's in-between frame
        /// that Hud shows for an instant when the eye opens or closes. Never a state of its own.
        /// </summary>
        public static Sprite EyeHalf => eyeHalf != null ? eyeHalf : eyeHalf = Draw(192, 112, HalfEye, "EyeHalf");

        /// <summary>Distance to a lid: the curve y = EyeCorner + height (1 - x^2), x = u / EyeHalfWidth, round at the corners.</summary>
        private static float LidDistance(float u, float v, float height)
        {
            float x = u / EyeHalfWidth;
            if (Mathf.Abs(x) >= 1f)
            {
                return new Vector2(Mathf.Abs(u) - EyeHalfWidth, v - EyeCorner).magnitude;
            }
            float y = EyeCorner + height * (1f - x * x);
            // The vertical gap over the slope's length: an even stroke weight along the whole curve.
            float slope = -2f * height * x / EyeHalfWidth;
            return Mathf.Abs(v - y) / Mathf.Sqrt(1f + slope * slope);
        }

        /// <summary>
        /// The open eye in the closed eye's line: a dark almond between a cream upper and lower lid that meet in round
        /// corners, a two tone amber iris (a darker rim), a round pupil of radius <paramref name="pupil"/> and two glints,
        /// and the closed eye's three lashes turned up on the upper lid (<paramref name="lashLength"/> long, leaning out by
        /// <paramref name="lashSpread"/>; none at 0). <paramref name="openness"/> is how high the upper lid arches
        /// (CONTRACT_M6 2.3): the calm eye is half open, the alarm eye wide open, so they differ by shape.
        /// </summary>
        private static Color EyeShape(float u, float v, float pixel, float openness, float pupil, float lashLength, float lashSpread)
        {
            float x = u / EyeHalfWidth;
            float upper = EyeCorner + openness * (1f - x * x);
            float lower = EyeCorner - EyeLowLid * (1f - x * x);
            float inside = Cover(Mathf.Abs(x) >= 1f ? 1f : Mathf.Max(v - upper, lower - v), pixel);
            Color c = new Color(0f, 0f, 0f, 0f);
            c = Over(c, new Color(0.06f, 0.055f, 0.075f, 0.92f), inside);
            // The iris sits between the lids (a nearly shut eye keeps it where the open eye has it: it peeks out).
            float irisY = EyeCorner + (Mathf.Max(openness, 0.3f) - EyeLowLid) * 0.5f + 0.02f;
            float r = new Vector2(u, v - irisY).magnitude;
            c = Over(c, new Color(0.93f, 0.56f, 0.16f, 1f), Cover(r - 0.42f, pixel) * inside);
            c = Over(c, new Color(1f, 0.8f, 0.34f, 1f), Cover(r - 0.34f, pixel) * inside);
            c = Over(c, new Color(0.05f, 0.04f, 0.07f, 1f), Cover(r - pupil, pixel) * inside);
            float glint = new Vector2(u - 0.15f, v - irisY - 0.14f).magnitude;
            c = Over(c, Color.white, Cover(glint - 0.075f, pixel) * inside);
            float glint2 = new Vector2(u + 0.11f, v - irisY + 0.15f).magnitude;
            c = Over(c, new Color(1f, 1f, 1f, 0.85f), Cover(glint2 - 0.035f, pixel) * inside);
            float lids = Mathf.Min(LidDistance(u, v, openness) - 0.1f, LidDistance(u, v, -EyeLowLid) - 0.085f);
            c = Over(c, EyeInk, Cover(lids, pixel));
            if (lashLength > 0f)
            {
                for (int i = -1; i <= 1; i++)
                {
                    float lx = i * 0.62f;
                    float xl = lx / EyeHalfWidth;
                    float baseY = EyeCorner + openness * (1f - xl * xl);
                    float d = SegmentDistance(new Vector2(u, v), new Vector2(lx, baseY), new Vector2(lx * lashSpread, baseY + lashLength)) - 0.07f;
                    c = Over(c, EyeInk, Cover(d, pixel));
                }
            }
            return c;
        }

        /// <summary>The blink's in-between frame: the eye nearly shut, with shorter lashes (<see cref="EyeHalf"/>).</summary>
        private static Color HalfEye(float u, float v, float pixel)
        {
            return EyeShape(u, v, pixel, 0.12f, 0.18f, 0.3f, 1.25f);
        }

        // M6 2.3: the corner badge every open eye overlays ("?" for calm/suspicious, "!" for alarm). Eye redesign: upper
        // right beside the outer lash, clear of the lid at either openness and of AlarmEye's strokes, with a dark outline.
        private const float BadgeX = 1.4f;
        private const float BadgeY = 0.56f;
        private const float BadgeScale = 0.3f;

        /// <summary>The badge's point (u, v) in the glyph's own local units.</summary>
        private static Vector2 BadgeLocal(float u, float v) => new Vector2(u - BadgeX, v - BadgeY) / BadgeScale;

        /// <summary>A badge glyph (its local signed distance <paramref name="markLocal"/>) in <paramref name="fill"/>, outlined in the glyph ink.</summary>
        private static Color EyeBadge(Color c, float markLocal, float pixel, Color fill)
        {
            float mark = markLocal * BadgeScale;
            c = Over(c, GlyphInk, Cover(mark - 0.085f, pixel));
            return Over(c, fill, Cover(mark - 0.03f, pixel));
        }

        /// <summary>
        /// The calm/suspicious eye: half open (CONTRACT_M6 2.3), with a "?" badge, so it differs from the alarm eye by
        /// shape (how far it opens, and the badge) as well as by colour.
        /// </summary>
        private static Color OpenEye(float u, float v, float pixel)
        {
            Color c = EyeShape(u, v, pixel, 0.46f, 0.18f, 0.34f, 1.25f);
            return EyeBadge(c, QuestionMarkSdf(BadgeLocal(u, v)), pixel, new Color(1f, 0.84f, 0.22f, 1f));
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

        /// <summary>STARSANIM: a ring of radius 0.8 and half width 0.07, its edges fading over 0.08 on both sides.</summary>
        private static Color BurstRingAlpha(float u, float v, float pixel)
        {
            float r = Mathf.Sqrt(u * u + v * v);
            float band = Mathf.Abs(r - 0.8f);
            float a = 1f - Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.07f, 0.15f, band));
            return new Color(1f, 1f, 1f, a);
        }

        /// <summary>STARSANIM: a radial glow, (1 - r)^2 smoothed, so the quad never shows its edge.</summary>
        private static Color SoftGlowAlpha(float u, float v, float pixel)
        {
            float r = Mathf.Clamp01(Mathf.Sqrt(u * u + v * v));
            float a = (1f - r) * (1f - r);
            return new Color(1f, 1f, 1f, a * a * (3f - 2f * a));
        }

        /// <summary>
        /// STARSANIM: a twinkle, four thin rays (an astroid like falloff along both axes) over a round core, soft edged.
        /// </summary>
        private static Color SparkleAlpha(float u, float v, float pixel)
        {
            float x = Mathf.Abs(u);
            float y = Mathf.Abs(v);
            // The rays: thin near the tips, wider at the centre (x^0.5 + y^0.5 under 1 is a concave four point star).
            float ray = Mathf.Sqrt(x) + Mathf.Sqrt(y);
            float rays = 1f - Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.82f, 1f, ray));
            float r = Mathf.Sqrt(u * u + v * v);
            float core = 1f - Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.14f, 0.34f, r));
            return new Color(1f, 1f, 1f, Mathf.Max(rays, core));
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
        /// The alarm eye: wide open (CONTRACT_M6 2.3) with a small pupil and longer, wider spread lashes, two shock strokes
        /// beside each corner, and a "!" badge, so it differs from the calm/suspicious eye by openness, strokes and badge,
        /// never only by the backdrop colour.
        /// </summary>
        private static Color AlarmEye(float u, float v, float pixel)
        {
            // Wide open, drawn at 86 % so the side strokes fit beside its corners.
            const float k = 0.86f;
            Color c = EyeShape(u / k, (v + 0.06f) / k, pixel / k, 0.64f, 0.12f, 0.4f, 1.4f);
            Color stroke = new Color(1f, 0.95f, 0.85f, 1f);
            Vector2 p = new Vector2(u, v);
            float d = float.MaxValue;
            d = Mathf.Min(d, SegmentDistance(p, new Vector2(-1.38f, 0f), new Vector2(-1.6f, 0.1f)));
            d = Mathf.Min(d, SegmentDistance(p, new Vector2(1.38f, 0f), new Vector2(1.6f, 0.1f)));
            d = Mathf.Min(d, SegmentDistance(p, new Vector2(-1.38f, -0.3f), new Vector2(-1.6f, -0.4f)));
            d = Mathf.Min(d, SegmentDistance(p, new Vector2(1.38f, -0.3f), new Vector2(1.6f, -0.4f)));
            c = Over(c, stroke, Cover(d - 0.06f, pixel));
            return EyeBadge(c, ExclamationMarkSdf(BadgeLocal(u, v)), pixel, stroke);
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
            // is the ears, not a badge shared with another state). Eye redesign: no lashes, they would touch the ears.
            Color eye = EyeShape(u / 0.78f, (v + 0.2f) / 0.78f, pixel / 0.78f, 0.62f, 0.15f, 0f, 1f);
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

        // ----- TOUCHTUTO (docs/next/progress/TOUCHTUTO.md): the level 1 touch tutorial's art (TouchTutorial). White, so an
        // Image tints it the tutorial's cream, the alpha holding each part's own opacity. Drawn from the validated mockup's
        // SVG (tuto.html): the coordinates below are its viewBox units, y down, one unit per texture pixel. Drawn the first
        // time the tutorial shows, so a PC never pays for them. -----

        private static Sprite tutorialStick;
        private static Sprite tutorialDrag;
        private static Sprite tutorialPinch;
        private static Sprite tutorialZone;

        /// <summary>
        /// TOUCHTUTO: the move stick, 300 x 300: a base ring with a faint fill, its knob pushed up and right, four chevrons on
        /// the rim, and two small dashed landing spots (the stick appears wherever the thumb lands).
        /// </summary>
        public static Sprite TutorialStick => tutorialStick != null ? tutorialStick : tutorialStick = Draw(300, 300, TutorialStickGlyph, "TutorialStick");

        /// <summary>TOUCHTUTO: drag to turn, 260 x 260: a finger dot in a faint ring under a curved two-way arrow.</summary>
        public static Sprite TutorialDrag => tutorialDrag != null ? tutorialDrag : tutorialDrag = Draw(260, 260, TutorialDragGlyph, "TutorialDrag");

        /// <summary>TOUCHTUTO: pinch to zoom, 260 x 260: two finger dots on a diagonal, with arrows pointing apart.</summary>
        public static Sprite TutorialPinch => tutorialPinch != null ? tutorialPinch : tutorialPinch = Draw(260, 260, TutorialPinchGlyph, "TutorialPinch");

        /// <summary>
        /// TOUCHTUTO: a zone panel, nine sliced with 56 px borders (one texture pixel per canvas unit at the default
        /// multiplier): a 3 px outline with 48 px corners around a faint fill, the fill at 0.05 / 0.18 of the outline's
        /// opacity, so a 0.18 tint gives the mockup's outline (0.18) and fill (0.05).
        /// </summary>
        public static Sprite TutorialZone => tutorialZone != null ? tutorialZone : tutorialZone = Draw(128, 128, TutorialZoneFrame, "TutorialZone", new Vector4(56f, 56f, 56f, 56f));

        // The drag arrow's ellipse (the mockup's "M40 120 A 100 70 0 0 1 220 120"): its two ends at y 120, 90 units either
        // side of its centre, so the centre is 70 * sqrt(1 - 0.9^2) below them.
        private const float DragArcRadiusX = 100f;
        private const float DragArcRadiusY = 70f;
        private static readonly float DragArcCentreY = 120f + DragArcRadiusY * Mathf.Sqrt(1f - 0.81f);

        /// <summary>A sprite pixel's centre in SVG viewBox units (y down) for a square sprite <paramref name="half"/> x 2 units wide.</summary>
        private static Vector2 SvgPoint(float u, float v, float half)
        {
            return new Vector2((u + 1f) * half, (1f - v) * half);
        }

        /// <summary>Alpha <paramref name="over"/> laid over alpha <paramref name="under"/> (white over white: only the alpha adds up).</summary>
        private static float Stack(float under, float over)
        {
            return over + under * (1f - over);
        }

        /// <summary>The distance to a two-segment polyline: round caps and a round join, like the mockup's strokes.</summary>
        private static float PolylineDistance(Vector2 p, Vector2 a, Vector2 b, Vector2 c)
        {
            return Mathf.Min(SegmentDistance(p, a, b), SegmentDistance(p, b, c));
        }

        /// <summary>
        /// The coverage of a dashed circle's stroke: <paramref name="dashes"/> dashes and as many gaps, each half of a period of
        /// the circumference, <paramref name="halfWidth"/> either side of <paramref name="radius"/>.
        /// </summary>
        private static float DashedRing(Vector2 p, Vector2 centre, float radius, float halfWidth, int dashes, float pixel)
        {
            Vector2 d = p - centre;
            float ring = Mathf.Abs(d.magnitude - radius) - halfWidth;
            if (ring > pixel)
            {
                return 0f;
            }
            float period = 2f * Mathf.PI * radius / dashes;
            float along = Mathf.Repeat((Mathf.Atan2(d.y, d.x) + Mathf.PI) * radius, period);
            // Each dash is centred in its period: negative on the dash, continuous across the period's wrap.
            float dash = Mathf.Abs(along - period * 0.5f) - period * 0.25f;
            return Cover(Mathf.Max(ring, dash), pixel);
        }

        /// <summary>
        /// The distance to the upper arc (y down: above the centre) of an axis-aligned ellipse between two points of it, with
        /// round caps at both ends. A first order distance (the implicit function over its gradient), exact enough for a
        /// stroke a few pixels wide.
        /// </summary>
        private static float UpperEllipseArcDistance(Vector2 p, Vector2 centre, float rx, float ry, Vector2 from, Vector2 to)
        {
            var q = new Vector2((p.x - centre.x) / rx, (p.y - centre.y) / ry);
            float length = q.magnitude;
            float angle = Mathf.Atan2(q.y, q.x);
            float start = Mathf.Atan2((from.y - centre.y) / ry, (from.x - centre.x) / rx);
            float end = Mathf.Atan2((to.y - centre.y) / ry, (to.x - centre.x) / rx);
            if (length > 1e-4f && angle >= start && angle <= end)
            {
                float gradient = new Vector2(q.x / rx, q.y / ry).magnitude / length;
                return Mathf.Abs(length - 1f) / Mathf.Max(gradient, 1e-6f);
            }
            return Mathf.Min((p - from).magnitude, (p - to).magnitude);
        }

        private static Color TutorialStickGlyph(float u, float v, float pixel)
        {
            const float half = 150f;
            Vector2 p = SvgPoint(u, v, half);
            float px = pixel * half;
            // Two dashed landing spots (r 16, 4 wide, at 0.35).
            float a = DashedRing(p, new Vector2(40f, 60f), 16f, 2f, 8, px) * 0.35f;
            a = Stack(a, DashedRing(p, new Vector2(268f, 250f), 16f, 2f, 8, px) * 0.35f);
            // The base: a faint fill (0.12) and its ring (r 110, 6 wide).
            float r = (p - new Vector2(150f, 150f)).magnitude;
            a = Stack(a, Cover(r - 110f, px) * 0.12f);
            a = Stack(a, Cover(Mathf.Abs(r - 110f) - 3f, px));
            // The knob (r 46, at 0.9), pushed up and right.
            a = Stack(a, Cover((p - new Vector2(185f, 125f)).magnitude - 46f, px) * 0.9f);
            // Four chevrons on the rim, 8 wide.
            float up = PolylineDistance(p, new Vector2(132f, 58f), new Vector2(150f, 40f), new Vector2(168f, 58f));
            float down = PolylineDistance(p, new Vector2(132f, 242f), new Vector2(150f, 260f), new Vector2(168f, 242f));
            float left = PolylineDistance(p, new Vector2(58f, 132f), new Vector2(40f, 150f), new Vector2(58f, 168f));
            float right = PolylineDistance(p, new Vector2(242f, 132f), new Vector2(260f, 150f), new Vector2(242f, 168f));
            a = Stack(a, Cover(Mathf.Min(Mathf.Min(up, down), Mathf.Min(left, right)) - 4f, px));
            return new Color(1f, 1f, 1f, a);
        }

        private static Color TutorialDragGlyph(float u, float v, float pixel)
        {
            const float half = 130f;
            Vector2 p = SvgPoint(u, v, half);
            float px = pixel * half;
            // The curved two-way arrow, 8 wide: the ellipse's upper arc from (40, 120) to (220, 120), a head at each end.
            float arc = UpperEllipseArcDistance(p, new Vector2(130f, DragArcCentreY), DragArcRadiusX, DragArcRadiusY,
                new Vector2(40f, 120f), new Vector2(220f, 120f));
            float heads = Mathf.Min(PolylineDistance(p, new Vector2(22f, 98f), new Vector2(40f, 124f), new Vector2(66f, 108f)),
                PolylineDistance(p, new Vector2(194f, 108f), new Vector2(220f, 124f), new Vector2(238f, 98f)));
            float a = Cover(Mathf.Min(arc, heads) - 4f, px);
            // The finger: a faint ring (r 54, 5 wide, at 0.4) around its dot (r 34, at 0.9).
            float r = (p - new Vector2(130f, 170f)).magnitude;
            a = Stack(a, Cover(Mathf.Abs(r - 54f) - 2.5f, px) * 0.4f);
            a = Stack(a, Cover(r - 34f, px) * 0.9f);
            return new Color(1f, 1f, 1f, a);
        }

        private static Color TutorialPinchGlyph(float u, float v, float pixel)
        {
            const float half = 130f;
            Vector2 p = SvgPoint(u, v, half);
            float px = pixel * half;
            // Two arrows pointing apart along the diagonal, 8 wide.
            float lowArrow = Mathf.Min(SegmentDistance(p, new Vector2(62f, 198f), new Vector2(26f, 234f)),
                PolylineDistance(p, new Vector2(26f, 204f), new Vector2(26f, 234f), new Vector2(56f, 234f)));
            float highArrow = Mathf.Min(SegmentDistance(p, new Vector2(198f, 62f), new Vector2(234f, 26f)),
                PolylineDistance(p, new Vector2(204f, 26f), new Vector2(234f, 26f), new Vector2(234f, 56f)));
            float a = Cover(Mathf.Min(lowArrow, highArrow) - 4f, px);
            // The two finger dots (r 30, at 0.9).
            a = Stack(a, Cover((p - new Vector2(90f, 170f)).magnitude - 30f, px) * 0.9f);
            a = Stack(a, Cover((p - new Vector2(170f, 90f)).magnitude - 30f, px) * 0.9f);
            return new Color(1f, 1f, 1f, a);
        }

        private static Color TutorialZoneFrame(float u, float v, float pixel)
        {
            const float half = 64f;
            Vector2 p = SvgPoint(u, v, half) - new Vector2(half, half);
            float px = pixel * half;
            // The outer edge half a pixel inside the texture's, so the slices meet the rect's edge with a smooth rim.
            float outside = RoundedBoxDistance(p, new Vector2(half - 0.5f, half - 0.5f), 48f);
            float outline = Cover(Mathf.Max(outside, -outside - 3f), px);
            float fill = Cover(outside + 3f, px) * (0.05f / 0.18f);
            return new Color(1f, 1f, 1f, Stack(fill, outline));
        }
    }
}
