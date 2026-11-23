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
    /// RecordId) starts again, as its records do. The star sprite is drawn once in code (no texture asset), like GaugeArt;
    /// <see cref="StarRow"/> lays three of them out on the win panel and on every level select card.
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
        private const int StarTexels = 96;
        private static readonly Color Outline = new Color(0.1f, 0.07f, 0.05f, 1f);

        /// <summary>The star sprite (drawn once): a white fill, a little brighter at the top, ringed in dark ink.</summary>
        public static Sprite Star => star != null ? star : star = DrawStar();

        private static Sprite DrawStar()
        {
            int size = StarTexels;
            var texture = new Texture2D(size, size, TextureFormat.RGBA32, false)
            {
                name = "Star",
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear,
                hideFlags = HideFlags.DontUnloadUnusedAsset,
            };
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
            texture.SetPixels(pixels);
            texture.Apply(false, true);
            Sprite sprite = Sprite.Create(texture, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect);
            sprite.name = "Star";
            sprite.hideFlags = HideFlags.DontUnloadUnusedAsset;
            return sprite;
        }

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
    /// Not a component: the HUD and the level select own one each and call Animate themselves.
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
