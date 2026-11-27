using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// Stars (idea 5, docs/next/progress/STARS.md): three stars per level and difficulty, earned by the win time against the
    /// audit's earliest exit. The reference is the "at" of the last point of the level's designer route for the played
    /// difficulty (designerRouteHard at Difficile, designerRoute otherwise: Facile has no route of its own and is judged
    /// against Normal's, which is the more generous side) plus <see cref="Tuning.StarsReferenceSlack"/>; a level without a
    /// route has nothing to beat and gives three stars. Three stars at or under the reference times
    /// <see cref="Tuning.StarsThreeFactor"/>, two under <see cref="Tuning.StarsTwoFactor"/>, one for any other win. The best
    /// count is kept in the save under the record key (<see cref="SaveData.RecordStars"/>), so a redesigned level (a new
    /// RecordId) starts again, as its records do. The star sprites are drawn once in code (no texture asset), like GaugeArt;
    /// <see cref="StarRow"/> lays three flat ones out on every level select card, and <see cref="WinStarsView"/> (STARSANIM,
    /// docs/next/progress/STARSANIM.md) is the end screen's animated hero row, with bevelled 3D stars since STAR3D.
    /// </summary>
    public static class Stars
    {
        /// <summary>The earned star's tint: the record line's gold.</summary>
        public static readonly Color Gold = new Color(1f, 0.82f, 0.3f, 1f);

        /// <summary>An unearned star: the title's cream, faint.</summary>
        public static readonly Color Empty = new Color(1f, 0.94f, 0.82f, 0.28f);

        /// <summary>The route the stars of <paramref name="difficulty"/> are judged against (see the class summary); null for a null level.</summary>
        public static List<RouteStepDef> RouteFor(LevelDef def, string difficulty)
        {
            if (def == null)
            {
                return null;
            }
            bool hard = DifficultyDef.Normalize(difficulty) == DifficultyDef.Difficile;
            if (hard && def.DesignerRouteHard != null && def.DesignerRouteHard.Count > 0) // MUTATION:STARS_HARD_ROUTE
            {
                return def.DesignerRouteHard;
            }
            return def.DesignerRoute;
        }

        /// <summary>
        /// The reference time in seconds: the latest "at" of <see cref="RouteFor"/> plus <see cref="Tuning.StarsReferenceSlack"/>;
        /// a negative value when the level has no route for that difficulty (nothing to beat).
        /// </summary>
        public static float Reference(LevelDef def, string difficulty)
        {
            List<RouteStepDef> route = RouteFor(def, difficulty);
            if (route == null || route.Count == 0)
            {
                return -1f;
            }
            float last = 0f;
            foreach (RouteStepDef step in route)
            {
                if (step != null && step.At > last)
                {
                    last = step.At;
                }
            }
            return last + Tuning.StarsReferenceSlack;
        }

        /// <summary>The slowest time that still earns three stars for <paramref name="reference"/>.</summary>
        public static float ThreeStarsUpTo(float reference) => reference * Tuning.StarsThreeFactor;

        /// <summary>Times under this (and over <see cref="ThreeStarsUpTo"/>) earn two stars.</summary>
        public static float TwoStarsUnder(float reference) => reference * Tuning.StarsTwoFactor;

        /// <summary>
        /// The stars of a win of <paramref name="seconds"/> against <paramref name="reference"/>: three at or under
        /// <see cref="ThreeStarsUpTo"/>, two under <see cref="TwoStarsUnder"/>, one otherwise; three when the reference is not
        /// positive (no route).
        /// </summary>
        public static int Count(float seconds, float reference)
        {
            if (reference <= 0f)
            {
                return Tuning.StarsPerLevel;
            }
            if (seconds <= ThreeStarsUpTo(reference)) // MUTATION:STARS_THREE
            {
                return 3;
            }
            if (seconds < TwoStarsUnder(reference)) // MUTATION:STARS_TWO
            {
                return 2;
            }
            return 1;
        }

        /// <summary>The stars of a win of <paramref name="seconds"/> on <paramref name="def"/> at <paramref name="difficulty"/>.</summary>
        public static int CountFor(LevelDef def, float seconds, string difficulty) => Count(seconds, Reference(def, difficulty));

        /// <summary>The stars saved over <paramref name="recordIds"/> at <paramref name="difficulty"/>, summed (0 for a null list or save).</summary>
        public static int Total(SaveData save, IReadOnlyList<string> recordIds, string difficulty)
        {
            if (save == null || recordIds == null)
            {
                return 0;
            }
            int total = 0;
            for (int i = 0; i < recordIds.Count; i++)
            {
                total += save.StarsOf(recordIds[i], difficulty);
            }
            return total;
        }

        /// <summary>The stars a line-up of <paramref name="levels"/> levels can hold.</summary>
        public static int Possible(int levels) => Mathf.Max(0, levels) * Tuning.StarsPerLevel;

        // ----- Art: a five point star, white to tint, with a dark outline so it reads on the panels and on the cards. -----

        private static Sprite star;
        private static Sprite starLarge;
        private static Sprite starSlot;
        private static Sprite starFlash;
        private const int StarTexels = 96;
        private static readonly Color Outline = new Color(0.1f, 0.07f, 0.05f, 1f);

        /// <summary>
        /// The flat star sprite (drawn once): a white fill, a little brighter at the top, ringed in dark ink. Kept for the small
        /// uses (the level select cards' 56 unit stars, the level select's total icon), where it is tinted gold or faint cream.
        /// </summary>
        public static Sprite Star => star != null ? star : star = DrawStar(StarTexels, "Star");

        /// <summary>
        /// STAR3D (2026-11-27, docs/next/progress/STARSANIM.md): the end screen's hero star, a chunky bevelled 3D gold star
        /// drawn in its own colours (show it white, <see cref="WinStarsView.FilledTint"/>): ten facets split down each arm's
        /// ridge, lit from the top-left over a gradient from bright yellow at the top to deep amber at the bottom, a thick
        /// rounded bevel along the edges, a dark amber rim and outline, a glossy streak and a specular sheen at the top-left,
        /// and a soft drop shadow down-right baked in (the sprite's padding holds it).
        /// </summary>
        public static Sprite StarLarge => starLarge != null ? starLarge : starLarge = DrawHeroStar(HeroTexels, "StarLarge");

        /// <summary>
        /// STAR3D: an empty slot of the hero row, in its own colours (draw it white): the same star shape recessed into the panel
        /// in a dark desaturated grey-blue (the walls in shadow at the top, a light lip at the bottom, the top-left wall's shadow
        /// cast on the floor), so <see cref="StarLarge"/> covers it exactly and pops out of it.
        /// </summary>
        public static Sprite StarSlot => starSlot != null ? starSlot : starSlot = DrawHeroSlot(HeroTexels, "StarSlot");

        /// <summary>
        /// STAR3D: the hero star's silhouette in plain white with a soft edge, laid over a filling star and faded out: the
        /// white-hot flash of its punch (a tint can only darken the baked colours of <see cref="StarLarge"/>).
        /// </summary>
        public static Sprite StarFlash => starFlash != null ? starFlash : starFlash = DrawHeroFlash(FlashTexels, "StarFlash");

        private static Sprite DrawStar(int size, string name)
        {
            var pixels = new Color[size * size];
            float pixel = 2f / size;
            const float outline = 0.09f;
            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    var p = new Vector2((x + 0.5f) / size * 2f - 1f, (y + 0.5f) / size * 2f - 1f);
                    float d = StarDistance(p, 0.88f, 0.47f);
                    float outer = Mathf.Clamp01(0.5f - (d - outline) / pixel);
                    float inner = Mathf.Clamp01(0.5f - d / pixel);
                    float v = (y + 0.5f) / size;
                    float l = 0.86f + 0.14f * v;
                    Color c = Color.Lerp(Outline, new Color(l, l, l, 1f), inner);
                    c.a = outer;
                    pixels[y * size + x] = c;
                }
            }
            return ToSprite(pixels, size, name);
        }

        /// <summary>One sprite from <paramref name="pixels"/> (square, row by row from the bottom): no mipmaps, bilinear, not readable.</summary>
        private static Sprite ToSprite(Color[] pixels, int size, string name)
        {
            var texture = new Texture2D(size, size, TextureFormat.RGBA32, false)
            {
                name = name,
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear,
                hideFlags = HideFlags.DontUnloadUnusedAsset,
            };
            texture.SetPixels(pixels);
            texture.Apply(false, true);
            Sprite sprite = Sprite.Create(texture, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect);
            sprite.name = name;
            sprite.hideFlags = HideFlags.DontUnloadUnusedAsset;
            return sprite;
        }

        // ----- STAR3D (2026-11-27): the hero row's bevelled 3D stars, drawn once (no texture asset, nothing per frame). -----
        // The hero stars show up to 184 units wide (about 206 px on a 20:9 phone, 245 px on a 1440p monitor; 1.8x for an
        // instant during the punch): 256 texels keep them crisp at rest (256 KB each, two textures), the flash 128 (64 KB).
        // Shape: the cards' star, a little chunkier (inner ratio 0.5) and smaller (outer radius 0.84 of the half box) to leave
        // the outline and the drop shadow room inside the box, so the boxes and the layout stay as they were.
        private const int HeroTexels = 256;
        private const int FlashTexels = 128;
        private const float HeroRadius = 0.84f;
        private const float HeroInner = 0.5f;
        // The bevel (sprite units, the half box is 1): its width, the slope at the very edge and the facets' slope beyond it.
        private const float HeroBevel = 0.15f;
        private const float HeroEdgeSlope = 2.4f;
        private const float HeroRoofSlope = 0.42f;
        private const float HeroRim = 0.03f;
        private const float HeroOutlineWidth = 0.028f;
        private const float HeroShadowAlpha = 0.5f;
        private static readonly Vector2 HeroShadowOffset = new Vector2(0.05f, -0.065f);
        // The slot: its outer lip, the walls' width and slopes, and the reach of the top-left wall's shadow on the floor.
        private const float SlotLip = 0.045f;
        private const float SlotWall = 0.1f;
        private const float SlotEdgeSlope = 2f;
        private const float SlotFloorSlope = 0.25f;
        private const float SlotLipSlope = 1.4f;
        private static readonly Vector2 SlotCastOffset = new Vector2(-0.07f, 0.08f);
        // The light comes from the top-left, toward the viewer; the half vector gives the specular sheen.
        private static readonly Vector3 HeroLight = new Vector3(-0.52f, 0.62f, 0.59f).normalized;
        private static readonly Vector3 HeroHalf = (new Vector3(-0.52f, 0.62f, 0.59f).normalized + Vector3.forward).normalized;
        private static readonly Color HeroTop = new Color(1f, 0.93f, 0.36f, 1f);
        private static readonly Color HeroMid = new Color(1f, 0.74f, 0.12f, 1f);
        private static readonly Color HeroBottom = new Color(0.86f, 0.38f, 0.03f, 1f);
        private static readonly Color HeroRimColor = new Color(0.55f, 0.22f, 0.02f, 1f);
        private static readonly Color HeroOutlineColor = new Color(0.32f, 0.12f, 0.02f, 1f);
        private static readonly Color HeroShadowColor = new Color(0.05f, 0.03f, 0.02f, 1f);
        private static readonly Color SlotBase = new Color(0.27f, 0.31f, 0.4f, 1f);

        /// <summary>
        /// The filled hero star (see <see cref="StarLarge"/>). Per texel: the distance to the star's edge, its inward direction
        /// (the distance's gradient: constant over each facet, so each arm splits down its ridge into a lit and a shaded half),
        /// a height slope steep at the edge (the rounded bevel) easing to the facets' gentle slope, lit by Lambert plus a
        /// Blinn sheen, over the vertical gold gradient; then the gloss streak, the dark rim, the outline and the drop shadow.
        /// </summary>
        private static Sprite DrawHeroStar(int size, string name)
        {
            float[] field = HeroField(size);
            float pixel = 2f / size;
            int sx = Mathf.RoundToInt(HeroShadowOffset.x / pixel);
            int sy = Mathf.RoundToInt(HeroShadowOffset.y / pixel);
            var pixels = new Color[size * size];
            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    var p = new Vector2((x + 0.5f) / size * 2f - 1f, (y + 0.5f) / size * 2f - 1f);
                    float d = FieldAt(field, size, x, y);
                    // The drop shadow: the outlined star's shape moved down-right, soft edged.
                    float ds = FieldAt(field, size, x - sx, y - sy);
                    float shadow = HeroShadowAlpha * (1f - Smooth(-0.02f, 0.07f, ds - HeroOutlineWidth));
                    float outer = Mathf.Clamp01(0.5f - (d - HeroOutlineWidth) / pixel);
                    Color star = HeroOutlineColor;
                    float body = Mathf.Clamp01(0.5f - d / pixel);
                    if (body > 0f)
                    {
                        float inside = -d;
                        float t = Mathf.Clamp01(inside / HeroBevel);
                        float slope = HeroRoofSlope + (HeroEdgeSlope - HeroRoofSlope) * (1f - t) * (1f - t);
                        // Raised: the surface leans outward, away from the inward direction.
                        float diffuse = Lit(-Inward(field, size, x, y), slope, out float sheen);
                        Color col = GoldGradient(p.y) * (0.36f + 0.9f * diffuse);
                        float gloss = Gloss(p) * Smooth(0.02f, 0.07f, inside);
                        col = Color.Lerp(col, Color.white, Mathf.Clamp01(sheen * 0.55f + gloss));
                        float rim = 1f - Smooth(HeroRim * 0.4f, HeroRim, inside);
                        col = Color.Lerp(col, HeroRimColor, rim * 0.85f);
                        star = Color.Lerp(HeroOutlineColor, col, body);
                    }
                    pixels[y * size + x] = OverShadow(star, outer, shadow);
                }
            }
            return ToSprite(pixels, size, name);
        }

        /// <summary>
        /// The empty slot (see <see cref="StarSlot"/>): the same field, the surface leaning inward (a hole): the outer lip slopes
        /// into it, the walls are steep, the floor's facets are the star's turned upside down; lit by the same light, so the top
        /// walls are in shadow and the bottom ones catch the light; the top-left wall casts its shadow on the floor.
        /// </summary>
        private static Sprite DrawHeroSlot(int size, string name)
        {
            float[] field = HeroField(size);
            float pixel = 2f / size;
            int lx = Mathf.RoundToInt(SlotCastOffset.x / pixel);
            int ly = Mathf.RoundToInt(SlotCastOffset.y / pixel);
            var pixels = new Color[size * size];
            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    float d = FieldAt(field, size, x, y);
                    float alpha = Mathf.Clamp01(0.5f - (d - SlotLip) / pixel);
                    if (alpha <= 0f)
                    {
                        pixels[y * size + x] = Color.clear;
                        continue;
                    }
                    float inside = -d;
                    float slope = d > 0f
                        ? SlotLipSlope * (1f - Mathf.Clamp01(d / SlotLip))
                        : SlotFloorSlope + (SlotEdgeSlope - SlotFloorSlope) * Sq(1f - Mathf.Clamp01(inside / SlotWall));
                    float diffuse = Lit(Inward(field, size, x, y), slope, out _);
                    Color col = SlotBase * (0.3f + 0.95f * diffuse);
                    if (inside > 0f)
                    {
                        // The floor lies in the top-left wall's shadow where the point toward the light is out of the hole.
                        float cast = Smooth(-0.04f, 0.03f, FieldAt(field, size, x + lx, y + ly));
                        col *= 1f - 0.45f * cast;
                    }
                    if (d > 0f)
                    {
                        alpha *= 1f - 0.55f * Smooth(0f, SlotLip, d);
                    }
                    col.a = alpha * 0.95f;
                    pixels[y * size + x] = col;
                }
            }
            return ToSprite(pixels, size, name);
        }

        /// <summary>The flash (see <see cref="StarFlash"/>): white, opaque over the star and its outline, fading just outside it.</summary>
        private static Sprite DrawHeroFlash(int size, string name)
        {
            var pixels = new Color[size * size];
            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    var p = new Vector2((x + 0.5f) / size * 2f - 1f, (y + 0.5f) / size * 2f - 1f);
                    float d = StarDistance(p, HeroRadius, HeroInner);
                    pixels[y * size + x] = new Color(1f, 1f, 1f, 1f - Smooth(-0.02f, 0.05f, d));
                }
            }
            return ToSprite(pixels, size, name);
        }

        /// <summary>
        /// The hero star's signed distances on a (<paramref name="size"/> + 2) square grid, row by row from the bottom: the
        /// texels plus one of padding all round, so every texel has the four neighbours of its gradient.
        /// </summary>
        private static float[] HeroField(int size)
        {
            int w = size + 2;
            var field = new float[w * w];
            for (int y = 0; y < w; y++)
            {
                for (int x = 0; x < w; x++)
                {
                    var p = new Vector2((x - 0.5f) / size * 2f - 1f, (y - 0.5f) / size * 2f - 1f);
                    field[y * w + x] = StarDistance(p, HeroRadius, HeroInner);
                }
            }
            return field;
        }

        /// <summary>The distance at texel (<paramref name="x"/>, <paramref name="y"/>), -1 to size; far outside the star beyond the grid.</summary>
        private static float FieldAt(float[] field, int size, int x, int y)
        {
            int w = size + 2;
            x++;
            y++;
            if (x < 0 || y < 0 || x >= w || y >= w)
            {
                return 1f;
            }
            return field[y * w + x];
        }

        /// <summary>The unit direction toward the star's inside at a texel (minus the distance's gradient), zero on a flat spot.</summary>
        private static Vector2 Inward(float[] field, int size, int x, int y)
        {
            var g = new Vector2(FieldAt(field, size, x - 1, y) - FieldAt(field, size, x + 1, y),
                FieldAt(field, size, x, y - 1) - FieldAt(field, size, x, y + 1));
            float m = g.magnitude;
            return m > 1e-6f ? g / m : Vector2.zero;
        }

        /// <summary>
        /// The diffuse light (0 to 1) of a surface rising <paramref name="slope"/> per unit toward <paramref name="lean"/>'s
        /// opposite (its normal leans toward <paramref name="lean"/>), and its Blinn sheen in <paramref name="sheen"/>.
        /// </summary>
        private static float Lit(Vector2 lean, float slope, out float sheen)
        {
            Vector3 n = new Vector3(lean.x * slope, lean.y * slope, 1f).normalized;
            sheen = Mathf.Pow(Mathf.Max(0f, Vector3.Dot(n, HeroHalf)), 36f);
            return Mathf.Max(0f, Vector3.Dot(n, HeroLight));
        }

        /// <summary>The gold from deep amber at the bottom tips (y -0.66) through orange gold to bright yellow at the top tip (0.84).</summary>
        private static Color GoldGradient(float y)
        {
            float k = Mathf.Clamp01((y + 0.66f) / 1.5f);
            return k < 0.5f ? Color.Lerp(HeroBottom, HeroMid, Smooth(0f, 0.5f, k)) : Color.Lerp(HeroMid, HeroTop, Smooth(0.5f, 1f, k));
        }

        /// <summary>The glossy streak: a soft ellipse across the upper-left of the star (0 to 0.55).</summary>
        private static float Gloss(Vector2 p)
        {
            const float cos = 0.6156615f;
            const float sin = 0.7880108f;
            float dx = p.x + 0.2f;
            float dy = p.y - 0.3f;
            float u = (dx * cos + dy * sin) / 0.3f;
            float v = (-dx * sin + dy * cos) / 0.075f;
            return (1f - Smooth(0.35f, 1f, u * u + v * v)) * 0.55f;
        }

        /// <summary>The star (<paramref name="star"/>, coverage <paramref name="cover"/>) over the drop shadow's alpha.</summary>
        private static Color OverShadow(Color star, float cover, float shadow)
        {
            float under = shadow * (1f - cover);
            float a = cover + under;
            if (a <= 1e-5f)
            {
                return Color.clear;
            }
            Color c = (star * cover + HeroShadowColor * under) / a;
            c.a = a;
            return c;
        }

        private static float Smooth(float from, float to, float x)
        {
            float t = Mathf.Clamp01((x - from) / (to - from));
            return t * t * (3f - 2f * t);
        }

        private static float Sq(float x) => x * x;

        /// <summary>Signed distance (negative inside) to a five point star of outer radius <paramref name="r"/> and inner ratio <paramref name="rf"/>.</summary>
        private static float StarDistance(Vector2 p, float r, float rf)
        {
            var k1 = new Vector2(0.809016994f, -0.587785252f);
            var k2 = new Vector2(-k1.x, k1.y);
            p.x = Mathf.Abs(p.x);
            p -= 2f * Mathf.Max(Vector2.Dot(k1, p), 0f) * k1;
            p -= 2f * Mathf.Max(Vector2.Dot(k2, p), 0f) * k2;
            p.x = Mathf.Abs(p.x);
            p.y -= r;
            Vector2 ba = rf * new Vector2(-k1.y, k1.x) - new Vector2(0f, 1f);
            float h = Mathf.Clamp(Vector2.Dot(p, ba) / Vector2.Dot(ba, ba), 0f, r);
            Vector2 q = p - ba * h;
            return q.magnitude * Mathf.Sign(p.y * ba.x - p.x * ba.y);
        }
    }

    /// <summary>
    /// A row of <see cref="Tuning.StarsPerLevel"/> star images under one centred root: <see cref="Set"/> lights the first
    /// <c>count</c> in gold and leaves the rest faint; with <c>reveal</c> the lit ones pop in one after the other
    /// (<see cref="Animate"/>, driven by its owner's Update, no allocation per frame: scales and colours are structs).
    /// Not a component: the level select owns one per card (the end screen has its own hero row, <see cref="WinStarsView"/>).
    /// </summary>
    public sealed class StarRow
    {
        /// <summary>The row's centred root (its size is the three stars and their gaps).</summary>
        public RectTransform Root { get; }

        /// <summary>The stars lit by the last <see cref="Set"/>.</summary>
        public int Count { get; private set; }

        /// <summary>The reveal is still playing.</summary>
        public bool Revealing { get; private set; }

        /// <summary>The row's images, left to right (tests read their scale and colour).</summary>
        public IReadOnlyList<Image> Images => images;

        private readonly Image[] images;
        private readonly float size;
        private float clock;

        /// <summary>Builds the row under <paramref name="parent"/>: stars <paramref name="starSize"/> units wide, <paramref name="gap"/> apart.</summary>
        public StarRow(Transform parent, string name, float starSize, float gap)
        {
            size = starSize;
            int n = Mathf.Max(1, Tuning.StarsPerLevel);
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            Root = (RectTransform)go.transform;
            Root.anchorMin = Root.anchorMax = new Vector2(0.5f, 0.5f);
            Root.pivot = new Vector2(0.5f, 0.5f);
            Root.sizeDelta = new Vector2(n * starSize + (n - 1) * gap, starSize);
            images = new Image[n];
            float x = -Root.sizeDelta.x * 0.5f + starSize * 0.5f;
            for (int i = 0; i < n; i++)
            {
                var child = new GameObject(name + i, typeof(RectTransform));
                child.transform.SetParent(Root, false);
                var image = child.AddComponent<Image>();
                image.sprite = Stars.Star;
                image.preserveAspect = true;
                image.raycastTarget = false;
                image.color = Stars.Empty;
                var rect = image.rectTransform;
                rect.anchorMin = rect.anchorMax = new Vector2(0.5f, 0.5f);
                rect.pivot = new Vector2(0.5f, 0.5f);
                rect.anchoredPosition = new Vector2(x, 0f);
                rect.sizeDelta = new Vector2(starSize, starSize);
                images[i] = image;
                x += starSize + gap;
            }
        }

        /// <summary>Places the root's centre at <paramref name="offset"/> from <paramref name="anchor"/> of its parent.</summary>
        public void Place(Vector2 anchor, Vector2 offset)
        {
            Root.anchorMin = Root.anchorMax = anchor;
            Root.anchoredPosition = offset;
        }

        /// <summary>Shows or hides the whole row (the images are disabled, never the GameObject).</summary>
        public void SetVisible(bool visible)
        {
            foreach (Image image in images)
            {
                image.enabled = visible;
            }
            if (!visible)
            {
                Revealing = false;
            }
        }

        /// <summary>
        /// Lights the first <paramref name="count"/> stars (clamped to the row) in gold, the rest faint, and shows the row.
        /// With <paramref name="reveal"/> the lit stars start at nothing and pop in one after the other
        /// (<see cref="Tuning.StarsRevealStagger"/> apart, each over <see cref="Tuning.StarsRevealSeconds"/>); without it
        /// they show at once.
        /// </summary>
        public void Set(int count, bool reveal)
        {
            Count = Mathf.Clamp(count, 0, images.Length);
            clock = 0f;
            Revealing = reveal && Count > 0;
            for (int i = 0; i < images.Length; i++)
            {
                bool lit = i < Count;
                images[i].enabled = true;
                images[i].rectTransform.localScale = Vector3.one;
                Color tint = lit ? Stars.Gold : Stars.Empty;
                if (lit && Revealing)
                {
                    tint.a = 0f;
                    images[i].rectTransform.localScale = Vector3.zero;
                }
                images[i].color = tint;
            }
        }

        /// <summary>Advances the reveal by <paramref name="dt"/> seconds; nothing once it is over (no work on a settled row).</summary>
        public void Animate(float dt)
        {
            if (!Revealing)
            {
                return;
            }
            clock += Mathf.Max(0f, dt);
            float stagger = Mathf.Max(0.01f, Tuning.StarsRevealStagger);
            float length = Mathf.Max(0.01f, Tuning.StarsRevealSeconds);
            bool done = true;
            for (int i = 0; i < Count; i++)
            {
                float t = Mathf.Clamp01((clock - i * stagger) / length);
                if (t < 1f)
                {
                    done = false;
                }
                // Ease out with a small overshoot: the star lands a touch larger than life, then settles.
                float u = t - 1f;
                float s = 1f + 2.70158f * u * u * u + 1.70158f * u * u;
                images[i].rectTransform.localScale = new Vector3(s, s, 1f);
                Color tint = Stars.Gold;
                tint.a = Mathf.Clamp01(t * 3f);
                images[i].color = tint;
            }
            if (done)
            {
                Revealing = false;
                for (int i = 0; i < Count; i++)
                {
                    images[i].rectTransform.localScale = Vector3.one;
                    images[i].color = Stars.Gold;
                }
            }
        }
    }
}
