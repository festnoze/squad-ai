using System.Collections.Generic;
using UnityEngine;
using UnityEngine.TestTools;
using NUnit.Framework;

namespace Viewpoint.Tests
{
    /// <summary>
    /// The named color table every material goes through. Port of the Godot
    /// suite <c>tests/test_palette.gd</c> (PRD 14.1 and 17.2, palette).
    ///
    /// Half of this file is not about color at all: it is about the two rules
    /// the player is never told in words and reads in the tint alone. Grey
    /// stays, pale goes (PRD 5.1); grey gone to steel and lead refuses harder
    /// still. Retuning the art is allowed, breaking those readings is not, so
    /// they are asserted as relations between colors and never as fixed values.
    /// The one thing pinned outright is the KEY SET of the PRD 14.1 table, which
    /// is vocabulary and not art: a renamed key turns everything that names it
    /// magenta.
    ///
    /// The assertion messages are the original French ones, kept verbatim.
    /// </summary>
    public sealed class PaletteTests
    {
        /// <summary>
        /// Rec. 709 relative luminance, the formula behind Godot's
        /// <c>Color.get_luminance()</c> the original suite compared against.
        /// Unity's own <c>Color.grayscale</c> uses the older Rec. 601 weights,
        /// so it is not used here: the thresholds below were tuned against 709.
        /// </summary>
        static float Luminance(Color c)
        {
            return 0.2126f * c.r + 0.7152f * c.g + 0.0722f * c.b;
        }

        /// <summary>
        /// Max component minus min component: zero for a pure grey, and the
        /// measure PRD 14.1 uses to say "this is a grey, not a color".
        /// </summary>
        static float Spread(Color c)
        {
            return Mathf.Max(c.r, Mathf.Max(c.g, c.b)) - Mathf.Min(c.r, Mathf.Min(c.g, c.b));
        }

        /// <summary>Sum of the per component distances, PRD 14.1 wording.</summary>
        static float ComponentDistance(Color a, Color b)
        {
            return Mathf.Abs(a.r - b.r) + Mathf.Abs(a.g - b.g) + Mathf.Abs(a.b - b.b);
        }

        /// <summary>
        /// The keys of the PRD 14.1 table, and only those. The VALUES are
        /// deliberately not listed: the whole point of the cases below is that
        /// the art can be retuned as long as the readings survive. But the key
        /// SET is not art, it is vocabulary: a renamed or dropped key sends
        /// every definition that names it to the magenta sentinel, and a key the
        /// table does not document is a color nobody agreed to.
        /// </summary>
        static readonly string[] Prd141Keys =
        {
            "platform", "platform_side", "platform_soft", "platform_soft_side",
            "sealed", "sealed_dark", "battery_sealed",
            "accent", "accent_dark", "teal", "teal_dark",
            "frame", "photo_back",
            "battery", "battery_tip",
            "teleporter", "teleporter_ring",
            "erasable", "wood", "wood_dark", "stone",
            "sky_top", "sky_horizon", "backdrop_top", "backdrop_bottom",
        };

        [Test]
        public void Le_vocabulaire_est_celui_du_tableau_14_1()
        {
            foreach (string key in Prd141Keys)
            {
                Assert.IsTrue(Palette.Has(key), "la couleur " + key + " du tableau 14.1 existe");
            }

            // And nothing else: an undocumented color is a color the PRD never
            // agreed to. Named in the message, because "expected 25 got 26" is
            // no help at all when it fires.
            var documented = new HashSet<string>(Prd141Keys);
            var undocumented = new List<string>();
            foreach (string key in Palette.Keys)
            {
                if (!documented.Contains(key))
                {
                    undocumented.Add(key);
                }
            }

            Assert.AreEqual(0, undocumented.Count,
                "couleurs hors du tableau 14.1 : " + string.Join(", ", undocumented));
            Assert.AreEqual(Prd141Keys.Length, documented.Count, "aucune cle dupliquee dans le tableau 14.1");
        }

        [Test]
        public void Les_couleurs_sont_definies_et_opaques()
        {
            var count = 0;
            foreach (string key in Palette.Keys)
            {
                count++;
                Color c = Palette.Get(key);
                Assert.AreEqual(1f, c.a, 0.001f, "couleur " + key + " opaque");

                // Keys and Has must agree, or a def could reference a color the
                // lookup refuses while the table lists it.
                Assert.IsTrue(Palette.Has(key), "cle " + key + " reconnue par Has");

                // sRGB components, so nothing outside [0, 1]: a value above 1
                // would saturate on upload instead of glowing.
                Assert.GreaterOrEqual(Mathf.Min(c.r, Mathf.Min(c.g, c.b)), 0f,
                    "couleur " + key + " sans composante negative");
                Assert.LessOrEqual(Mathf.Max(c.r, Mathf.Max(c.g, c.b)), 1f,
                    "couleur " + key + " dans [0, 1]");
            }

            Assert.GreaterOrEqual(count, 15, "au moins quinze couleurs nommees");
        }

        [Test]
        public void La_lecture_et_le_magenta_sentinelle()
        {
            Assert.IsTrue(Palette.Has("platform"), "platform existe");
            Assert.IsFalse(Palette.Has("nimporte_quoi"), "cle inconnue refusee");
            Assert.IsFalse(Palette.Has(null), "cle nulle refusee");

            // An unknown key is a data bug: it has to warn AND be visible in
            // game, so the warning is part of the contract and not noise.
            LogAssert.Expect(LogType.Warning, "Palette: unknown color key 'nimporte_quoi'");
            Color sentinel = Palette.Get("nimporte_quoi");
            Assert.AreEqual(Color.magenta.r, sentinel.r, 0.001f, "cle inconnue rend le magenta sentinelle");
            Assert.AreEqual(Color.magenta.g, sentinel.g, 0.001f, "cle inconnue rend le magenta sentinelle");
            Assert.AreEqual(Color.magenta.b, sentinel.b, 0.001f, "cle inconnue rend le magenta sentinelle");
            Assert.AreEqual(1f, sentinel.a, 0.001f, "le magenta sentinelle est opaque");

            LogAssert.Expect(LogType.Warning, "Palette: unknown color key ''");
            Color fromNull = Palette.Get(null);
            Assert.AreEqual(Color.magenta.r, fromNull.r, 0.001f, "cle nulle rend le magenta sentinelle");
            Assert.AreEqual(Color.magenta.b, fromNull.b, 0.001f, "cle nulle rend le magenta sentinelle");

            // The original compared against Palette.COLORS directly; the Unity
            // table is private, so the reference is the PRD 14.1 row itself.
            Color battery = Palette.Get("battery");
            Assert.AreEqual(1.0f, battery.r, 0.001f, "lecture directe coherente");
            Assert.AreEqual(0.76f, battery.g, 0.001f, "lecture directe coherente");
            Assert.AreEqual(0.29f, battery.b, 0.001f, "lecture directe coherente");

            // Reading twice must not drift: the table is data, not a generator.
            Color again = Palette.Get("battery");
            Assert.AreEqual(battery.r, again.r, 0.0001f, "la lecture est stable");
            Assert.AreEqual(battery.g, again.g, 0.0001f, "la lecture est stable");
            Assert.AreEqual(battery.b, again.b, 0.0001f, "la lecture est stable");
        }

        [Test]
        public void Le_langage_du_sol()
        {
            // The rule the player reads without a word of explanation: grey
            // stays, pale goes. The two must be told apart at a glance, and the
            // ephemeral one must be the lighter of the two.
            Assert.IsTrue(Palette.Has("platform"), "sol permanent defini");
            Assert.IsTrue(Palette.Has("platform_soft"), "sol effacable defini");
            Assert.IsTrue(Palette.Has("platform_side"), "flanc du sol permanent defini");
            Assert.IsTrue(Palette.Has("platform_soft_side"), "flanc du sol effacable defini");

            Color solid = Palette.Get("platform");
            Color soft = Palette.Get("platform_soft");
            Assert.Less(Spread(solid), 0.12f, "le sol permanent est gris, pas colore");
            Assert.Greater(Luminance(soft), Luminance(solid) + 0.12f,
                "le sol effacable est nettement plus clair");
            Assert.Greater(Luminance(Palette.Get("platform_soft_side")),
                Luminance(Palette.Get("platform_side")),
                "les flancs suivent le meme langage");

            // The ephemeral ground belongs to the lavender family it shares a
            // fate with.
            Color lavender = Palette.Get("erasable");
            Assert.Greater(soft.b, soft.g, "le sol effacable tire vers le lavande comme les murs effacables");
            Assert.Greater(lavender.b, lavender.g, "le lavande reste la couleur de ce qui disparait");

            // A skirt is darker than the slab it hangs under, or the ground
            // reads as a floating sheet instead of a block.
            Assert.Less(Luminance(Palette.Get("platform_side")), Luminance(solid),
                "le flanc est plus sombre que la dalle");
            Assert.Less(Luminance(Palette.Get("platform_soft_side")), Luminance(soft),
                "le flanc pale est plus sombre que la dalle pale");
        }

        [Test]
        public void Le_langage_scelle()
        {
            // One step past the permanent ground: steel and lead. Same grey
            // family, so the eye files them under "this will not move", but
            // darker, so they read as a harder refusal than a plain platform.
            string[] keys = { "sealed", "sealed_dark", "battery_sealed" };
            foreach (string key in keys)
            {
                Assert.IsTrue(Palette.Has(key), "couleur " + key + " definie");
                Assert.Less(Spread(Palette.Get(key)), 0.12f, key + " est un gris, pas une couleur");
            }

            Assert.Less(Luminance(Palette.Get("sealed")), Luminance(Palette.Get("platform")),
                "l'acier est plus sombre que le sol permanent");
            Assert.Less(Luminance(Palette.Get("sealed_dark")), Luminance(Palette.Get("sealed")),
                "les accents d'acier sont plus sombres encore");

            // A leaden battery must never be mistaken for a live one at a glance.
            Color live = Palette.Get("battery");
            Color lead = Palette.Get("battery_sealed");
            Assert.Greater(ComponentDistance(live, lead), 0.5f,
                "la pile plombee ne se confond pas avec la pile vive");
            Assert.Greater(Luminance(live), Luminance(lead) + 0.2f,
                "la pile vive est nettement plus lumineuse");

            // And the lead is grey where the live one is warm: the hue carries
            // the reading even for a player who cannot compare brightnesses.
            Assert.Greater(Spread(live), 0.12f, "la pile vive est une couleur, pas un gris");
        }

        [Test]
        public void La_lisibilite()
        {
            // The erasable tint must stand out from the regular platform color,
            // or the player cannot tell what a photo can erase.
            Assert.Greater(ComponentDistance(Palette.Get("erasable"), Palette.Get("platform")), 0.1f,
                "effacable distinct des plateformes");
            Assert.Greater(Palette.Get("sky_top").b, Palette.Get("sky_horizon").b - 0.2f,
                "ciel bleute vers le haut");

            // The original's 0.2 of slack above lets almost anything through, so
            // "bluer" is also stated the way an eye reads it: how far the blue
            // runs ahead of the red. A washed out zenith would pass the line
            // above and fail this one.
            Color zenith = Palette.Get("sky_top");
            Color horizon = Palette.Get("sky_horizon");
            Assert.Greater(zenith.b - zenith.r, horizon.b - horizon.r,
                "le zenith est plus bleu que l'horizon, pas seulement plus fonce");

            // The horizon is the pale end of the sky, so a distant silhouette
            // stands out against it.
            Assert.Greater(Luminance(Palette.Get("sky_horizon")), Luminance(Palette.Get("sky_top")),
                "l'horizon est plus pale que le zenith");

            // The painted backdrop of a photo must not be mistaken for the real
            // sky behind it, or a photo stops reading as a photo.
            Assert.Greater(ComponentDistance(Palette.Get("backdrop_top"), Palette.Get("sky_top")), 0.05f,
                "le fond peint ne se confond pas avec le ciel");
        }
    }
}
