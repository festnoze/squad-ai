using UnityEngine;
using NUnit.Framework;

namespace Viewpoint.Tests
{
    /// <summary>
    /// The material factory: the cache every box of the same color shares, and
    /// the painted backdrop gradient. Port of the Godot suite
    /// <c>tests/test_materials.gd</c> (PRD 14.2 and 17.2, materials).
    ///
    /// The original's <c>test_ghost</c> case has no counterpart here: the Unity
    /// factory exposes <c>Solid</c> and <c>Backdrop</c> only, the placement
    /// preview being handled elsewhere. Everything else is ported case for case.
    ///
    /// Every case tears the cache down, or the first case to ask for a material
    /// would decide what the next one gets and the caching assertions would pass
    /// or fail depending on the order the runner picked.
    ///
    /// The assertion messages are the original French ones, kept verbatim.
    /// </summary>
    public sealed class MaterialsTests
    {
        const string LitShaderName = "Universal Render Pipeline/Lit";
        const string UnlitShaderName = "Universal Render Pipeline/Unlit";

        [SetUp]
        public void SetUp()
        {
            // A missing URP shader turns the whole game magenta and makes every
            // assertion below meaningless, so it is stated first and in words
            // rather than surfacing as a null shader deep inside the factory.
            Assert.IsNotNull(Shader.Find(LitShaderName), "le shader URP Lit est disponible");
            Assert.IsNotNull(Shader.Find(UnlitShaderName), "le shader URP Unlit est disponible");
            Materials.ClearCache();
        }

        [TearDown]
        public void TearDown()
        {
            Materials.ClearCache();
        }

        static float ComponentDistance(Color a, Color b)
        {
            return Mathf.Abs(a.r - b.r) + Mathf.Abs(a.g - b.g) + Mathf.Abs(a.b - b.b);
        }

        [Test]
        public void Le_solide_est_mis_en_cache_par_cle_et_emission()
        {
            Material a = Materials.Solid("platform");
            Material b = Materials.Solid("platform");
            Assert.AreSame(a, b, "meme cle : meme instance");

            Material c = Materials.Solid("platform", 1f);
            Assert.AreNotSame(a, c, "variante emissive : instance distincte");
            Assert.AreSame(c, Materials.Solid("platform", 1f), "la variante emissive est mise en cache");

            // Two emission energies are two materials, or a battery would glow
            // with the strength of whichever cell was built first.
            Assert.AreNotSame(c, Materials.Solid("platform", 0.25f),
                "deux energies d'emission : deux instances");

            // And two colors are never the same material, whatever the cache key
            // looks like.
            Assert.AreNotSame(a, Materials.Solid("wood"), "deux cles : deux instances");

            // The default IS zero energy: a caller writing the 0 out must land on
            // the same material as one leaving it off, or half the world would
            // hold a duplicate of every plain material.
            Assert.AreSame(a, Materials.Solid("platform", 0f), "l'energie par defaut est zero");

            // Every energy the game actually ships (PRD 14.1 and 14.2: lavender
            // 0.25, teleporter ring 0.15 and 2.0, live battery 0.8, filled cell
            // 1.2, camera lens 0.4) must come out as its own material. The cache
            // key rounds the energy to two decimals, so this is the assertion
            // that would catch a coarser rounding merging two of them.
            float[] shipped = { 0.15f, 0.25f, 0.4f, 0.8f, 1.2f, 2f };
            for (var i = 0; i < shipped.Length; i++)
            {
                Material glow = Materials.Solid("battery", shipped[i]);
                Assert.AreSame(glow, Materials.Solid("battery", shipped[i]),
                    "energie " + shipped[i] + " mise en cache");
                for (var j = i + 1; j < shipped.Length; j++)
                {
                    Assert.AreNotSame(glow, Materials.Solid("battery", shipped[j]),
                        "energies " + shipped[i] + " et " + shipped[j] + " : deux instances");
                }
            }
        }

        [Test]
        public void La_variante_emissive_est_allumee()
        {
            Material plain = Materials.Solid("battery");
            Material glowing = Materials.Solid("battery", 0.8f);

            Assert.IsTrue(glowing.IsKeywordEnabled("_EMISSION"), "variante emissive allumee");
            Assert.IsFalse(plain.IsKeywordEnabled("_EMISSION"), "sans energie, pas d'emission");

            // PRD 14.2: emissionColor = color * emissive, alpha untouched, so
            // reading the color back cannot make the material look transparent.
            Color color = Palette.Get("battery");
            Color emission = glowing.GetColor("_EmissionColor");
            Assert.AreEqual(color.r * 0.8f, emission.r, 0.001f, "emission = couleur x energie (r)");
            Assert.AreEqual(color.g * 0.8f, emission.g, 0.001f, "emission = couleur x energie (g)");
            Assert.AreEqual(color.b * 0.8f, emission.b, 0.001f, "emission = couleur x energie (b)");
            Assert.AreEqual(1f, emission.a, 0.001f, "l'emission ne rend pas le materiau transparent");

            // Read as a bitmask, which is what the enum is (AnyEmissive is
            // RealtimeEmissive | BakedEmissive): the meaning asserted is "this
            // glow is computed at runtime and never baked", not one exact
            // integer, so an added flag bit cannot turn a correct material red.
            MaterialGlobalIlluminationFlags glowFlags = glowing.globalIlluminationFlags;
            Assert.IsTrue((glowFlags & MaterialGlobalIlluminationFlags.RealtimeEmissive) != 0,
                "emission temps reel, non precalculee");
            Assert.IsTrue((glowFlags & MaterialGlobalIlluminationFlags.BakedEmissive) == 0,
                "emission temps reel, non precalculee");
            Assert.IsTrue((glowFlags & MaterialGlobalIlluminationFlags.EmissiveIsBlack) == 0,
                "une variante emissive n'est pas declaree noire");
            Assert.IsTrue((plain.globalIlluminationFlags & MaterialGlobalIlluminationFlags.EmissiveIsBlack) != 0,
                "sans emission, rien a precalculer");

            Color plainEmission = plain.GetColor("_EmissionColor");
            Assert.AreEqual(0f, plainEmission.r + plainEmission.g + plainEmission.b, 0.001f,
                "emission noire sans energie");

            // The glow must not repaint the albedo: a battery lit at 0.8 is still
            // the same amber as a dead one, and PRD 14.2 scales the EMISSION
            // color by the energy, never the base color.
            Color glowBase = glowing.GetColor("_BaseColor");
            Assert.AreEqual(color.r, glowBase.r, 0.001f, "l'emission ne reteinte pas l'albedo");
            Assert.AreEqual(color.g, glowBase.g, 0.001f, "l'emission ne reteinte pas l'albedo");
            Assert.AreEqual(color.b, glowBase.b, 0.001f, "l'emission ne reteinte pas l'albedo");
            Assert.AreEqual(1f, glowBase.a, 0.001f, "une variante emissive reste opaque");

            // An energy above 1 is legal and must stay above 1 in the emission
            // color: clamping it to white is what kills a charged teleporter ring
            // (2.0) and a filled cell (1.2), which are meant to bloom.
            Material hot = Materials.Solid("teleporter_ring", 2f);
            Color hotEmission = hot.GetColor("_EmissionColor");
            Color ring = Palette.Get("teleporter_ring");
            Assert.AreEqual(ring.r * 2f, hotEmission.r, 0.001f, "l'energie superieure a 1 n'est pas ecretee");
            Assert.Greater(hotEmission.g, 1f, "un anneau charge deborde en HDR");
        }

        [Test]
        public void Le_solide_prend_sa_couleur_dans_la_palette()
        {
            Material a = Materials.Solid("platform");
            Color expected = Palette.Get("platform");
            Color actual = a.GetColor("_BaseColor");
            Assert.AreEqual(expected.r, actual.r, 0.001f, "couleur d'albedo depuis la palette");
            Assert.AreEqual(expected.g, actual.g, 0.001f, "couleur d'albedo depuis la palette");
            Assert.AreEqual(expected.b, actual.b, 0.001f, "couleur d'albedo depuis la palette");
            Assert.AreEqual(1f, actual.a, 0.001f, "un solide est opaque");

            // PRD 14.2: Godot roughness 0.85 is URP smoothness 0.15, metallic 0.
            // A metallic solid goes black in the shadow of these levels.
            Assert.AreEqual(0.15f, a.GetFloat("_Smoothness"), 0.001f, "rugosite 0.85 : lissage 0.15");
            Assert.AreEqual(0f, a.GetFloat("_Metallic"), 0.001f, "aucun solide n'est metallique");
            Assert.AreEqual(LitShaderName, a.shader.name, "un solide est eclaire");

            // The lavender of what disappears, and the grey of what stays, must
            // not come out of the factory as the same material.
            Material lavender = Materials.Solid("erasable");
            Assert.Greater(ComponentDistance(lavender.GetColor("_BaseColor"), actual), 0.1f,
                "effacable et plateforme restent distincts apres fabrication");
        }

        [Test]
        public void Le_fond_peint_est_mis_en_cache_et_non_ombre()
        {
            Material m = Materials.Backdrop("backdrop_top", "backdrop_bottom");
            Assert.AreSame(m, Materials.Backdrop("backdrop_top", "backdrop_bottom"),
                "backdrop mis en cache");
            Assert.AreNotSame(m, Materials.Backdrop("sky_top", "sky_horizon"),
                "deux degrades : deux instances");

            Texture texture = m.GetTexture("_BaseMap");
            Assert.IsNotNull(texture, "backdrop texture en degrade");
            Assert.AreEqual(UnlitShaderName, m.shader.name, "backdrop non ombre");

            // White base color, or the ramp would be tinted twice.
            Color tint = m.GetColor("_BaseColor");
            Assert.AreEqual(1f, tint.r, 0.001f, "le degrade n'est pas reteinte");
            Assert.AreEqual(1f, tint.g, 0.001f, "le degrade n'est pas reteinte");
            Assert.AreEqual(1f, tint.b, 0.001f, "le degrade n'est pas reteinte");

            // PRD 14.2: a 4 x 64 vertical ramp generated in code, no asset.
            Assert.AreEqual(4, texture.width, "degrade de 4 pixels de large");
            Assert.AreEqual(64, texture.height, "degrade de 64 pixels de haut");
        }

        [Test]
        public void Le_degrade_varie_du_haut_vers_le_bas()
        {
            Material m = Materials.Backdrop("backdrop_top", "backdrop_bottom");
            Texture2D ramp = m.GetTexture("_BaseMap") as Texture2D;
            Assert.IsNotNull(ramp, "le degrade est une texture 2D lisible");

            Color first = ramp.GetPixel(0, 0);
            Color last = ramp.GetPixel(0, ramp.height - 1);
            Assert.Greater(ComponentDistance(first, last), 0.05f,
                "le degrade varie du haut vers le bas");

            // THE PORT TRAP: Unity texture rows run bottom up where Godot images
            // run top down, so row 0 must carry the BOTTOM color. Get it backwards
            // and every painted backdrop in the game is upside down while still
            // looking like a plausible sky.
            Color top = Palette.Get("backdrop_top");
            Color bottom = Palette.Get("backdrop_bottom");
            Assert.Less(ComponentDistance(first, bottom), ComponentDistance(first, top),
                "la ligne 0 porte la couleur du bas");
            Assert.Less(ComponentDistance(last, top), ComponentDistance(last, bottom),
                "la derniere ligne porte la couleur du haut");

            // Stated once more as a channel comparison, which survives any
            // color space conversion the sampler may apply on the way back.
            Assert.Less(last.r, first.r, "le haut du fond peint est plus froid que le bas");

            // A ramp, not two flat halves: the middle sits between the ends.
            Color middle = ramp.GetPixel(0, ramp.height / 2);
            Assert.Less(ComponentDistance(middle, first), ComponentDistance(last, first),
                "le milieu du degrade est entre les deux extremites");
        }

        [Test]
        public void Le_vidage_du_cache_reconstruit()
        {
            // The cache is real (same instance twice) and it is droppable, which
            // is what lets a case start from a known state. Without this, the
            // TearDown above would be a no-op nobody noticed.
            Material before = Materials.Solid("stone");
            Assert.AreSame(before, Materials.Solid("stone"), "le cache rend bien la meme instance");

            Materials.ClearCache();
            Material after = Materials.Solid("stone");
            Assert.AreNotSame(before, after, "apres vidage, le materiau est refabrique");

            // ClearCache drops references, it must never destroy: a renderer
            // somewhere may still point at the old material, and a destroyed one
            // would turn it magenta. Unity's == is what reports a destroyed
            // object, a plain null check would pass either way. Checked before
            // the read below, which would throw on a destroyed material.
            Assert.IsFalse(before == null, "l'ancien materiau n'est pas detruit sous les renderers");

            // Refabricated, not reinvented: the color still comes from the palette.
            Assert.AreEqual(before.GetColor("_BaseColor").r, after.GetColor("_BaseColor").r, 0.001f,
                "le materiau refabrique garde sa couleur");
        }
    }
}
