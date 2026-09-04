using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;

namespace Viewpoint.Tests
{
    /// <summary>
    /// The box-minus-box decomposition that powers partial erasure (carving),
    /// plus the identity a fragment must inherit (PRD 5.2).
    ///
    /// <see cref="ErasableBlock.Decompose"/> is static and pure, so most cases
    /// here are arithmetic with no object at all. The few that do build a block
    /// build it through the real factory and take it down again in TearDown: a
    /// leaked block would stay registered in <see cref="Groups"/> and poison
    /// whatever suite runs next.
    /// </summary>
    public sealed class ErasableBlockTests
    {
        const float Epsilon = 0.0001f;

        readonly List<GameObject> _spawned = new List<GameObject>();

        [SetUp]
        public void SetUp()
        {
            // Whatever the suite before left registered is none of this one's
            // business, and a block built here must be the only thing the
            // registry holds while the case runs.
            Groups.Clear();
        }

        [TearDown]
        public void TearDown()
        {
            for (int i = 0; i < _spawned.Count; i++)
            {
                if (_spawned[i] != null)
                {
                    UnityEngine.Object.DestroyImmediate(_spawned[i]);
                }
            }
            _spawned.Clear();
            // Edit mode may or may not have run OnEnable on those blocks; either
            // way the registry starts empty for the next suite.
            Groups.Clear();
            // Building a block asks the factory for a material, which caches it.
            // Dropped here (never destroyed, see Materials.ClearCache) so the
            // caching assertions of the materials suite start from a cold cache
            // whatever order the runner picked.
            Materials.ClearCache();
        }

        /// <summary>Builds a block through the real factory and schedules its removal.</summary>
        ErasableBlock Make(Vector3 size, string color, float emissive = 0f, string[] extraGroups = null, bool canCarve = true)
        {
            // A block asks Materials.Solid for its material, and a missing URP
            // shader makes that log an error, which the framework turns into an
            // unrelated failure. Name the real cause here rather than there.
            Assert.IsNotNull(Shader.Find("Universal Render Pipeline/Lit"),
                "le shader URP Lit est disponible");
            Assert.IsTrue(Palette.Has(color), "la couleur du bloc existe dans la palette");
            ErasableBlock block = ErasableBlock.Create(size, color, emissive, extraGroups, canCarve);
            Assert.IsNotNull(block, "le bloc est construit");
            _spawned.Add(block.gameObject);
            return block;
        }

        static float TotalVolume(List<(Vector3 center, Vector3 size)> pieces)
        {
            float total = 0f;
            for (int i = 0; i < pieces.Count; i++)
            {
                Vector3 size = pieces[i].size;
                total += size.x * size.y * size.z;
            }
            return total;
        }

        static void AssertVector(Vector3 expected, Vector3 actual, string message)
        {
            Assert.AreEqual(expected.x, actual.x, Epsilon, message);
            Assert.AreEqual(expected.y, actual.y, Epsilon, message);
            Assert.AreEqual(expected.z, actual.z, Epsilon, message);
        }

        static bool Inside(Vector3 point, Vector3 min, Vector3 max)
        {
            return point.x >= min.x - Epsilon && point.x <= max.x + Epsilon
                && point.y >= min.y - Epsilon && point.y <= max.y + Epsilon
                && point.z >= min.z - Epsilon && point.z <= max.z + Epsilon;
        }

        /// <summary>True when two boxes share no volume; touching faces do not count.</summary>
        static bool Disjoint(Vector3 aMin, Vector3 aMax, Vector3 bMin, Vector3 bMax)
        {
            return Mathf.Min(aMax.x, bMax.x) - Mathf.Max(aMin.x, bMin.x) <= Epsilon
                || Mathf.Min(aMax.y, bMax.y) - Mathf.Max(aMin.y, bMin.y) <= Epsilon
                || Mathf.Min(aMax.z, bMax.z) - Mathf.Max(aMin.z, bMin.z) <= Epsilon;
        }

        /// <summary>
        /// The three invariants a volume total cannot see: every piece stays
        /// inside the original box, no piece reaches into the hole, and no two
        /// pieces overlap (or the player would see doubled faces and the physics
        /// would fight itself).
        /// </summary>
        static void AssertPiecesAreClean(Vector3 size, Vector3 holeMin, Vector3 holeMax,
            List<(Vector3 center, Vector3 size)> pieces, string what)
        {
            Vector3 boxMin = -size * 0.5f;
            Vector3 boxMax = size * 0.5f;
            // The hole is clamped to the box before the cut, so compare against
            // the clamped one.
            Vector3 lo = Vector3.Min(Vector3.Max(holeMin, boxMin), boxMax);
            Vector3 hi = Vector3.Min(Vector3.Max(holeMax, boxMin), boxMax);
            for (int i = 0; i < pieces.Count; i++)
            {
                Vector3 pieceMin = pieces[i].center - pieces[i].size * 0.5f;
                Vector3 pieceMax = pieces[i].center + pieces[i].size * 0.5f;
                Assert.IsTrue(Inside(pieceMin, boxMin, boxMax) && Inside(pieceMax, boxMin, boxMax),
                    what + " : chaque morceau reste dans la boite");
                Assert.IsTrue(Disjoint(pieceMin, pieceMax, lo, hi),
                    what + " : aucun morceau ne mord dans le trou");
                Assert.IsTrue(pieces[i].size.x >= ErasableBlock.MinFragment
                    && pieces[i].size.y >= ErasableBlock.MinFragment
                    && pieces[i].size.z >= ErasableBlock.MinFragment,
                    what + " : aucun morceau plus mince que le fragment minimal");
                for (int j = i + 1; j < pieces.Count; j++)
                {
                    Vector3 otherMin = pieces[j].center - pieces[j].size * 0.5f;
                    Vector3 otherMax = pieces[j].center + pieces[j].size * 0.5f;
                    Assert.IsTrue(Disjoint(pieceMin, pieceMax, otherMin, otherMax),
                        what + " : les morceaux ne se chevauchent pas");
                }
            }
        }

        [Test]
        public void La_creation_garde_l_identite()
        {
            // Fragments are rebuilt with the same color, emissive and extra
            // groups, so a carved platform stays a platform and a lavender block
            // stays lavender.
            ErasableBlock plain = Make(new Vector3(2, 1, 3), "wood");
            AssertVector(new Vector3(2, 1, 3), plain.BlockSize, "taille memorisee");
            Assert.AreEqual("wood", plain.ColorKey, "couleur memorisee");
            Assert.AreEqual(0f, plain.Emissive, Epsilon, "pas d'emission par defaut");
            Assert.IsNotNull(plain.ExtraGroups, "la liste de groupes n'est jamais nulle");
            Assert.AreEqual(0, plain.ExtraGroups.Length, "aucun groupe supplementaire par defaut");
            Assert.IsTrue(plain.ShowMesh, "un bloc est visible par defaut");
            Assert.IsTrue(plain.Carvable, "un bloc se decoupe par defaut");

            ErasableBlock marked = Make(Vector3.one, "erasable", 0.25f, new[] { Groups.Erasable });
            Assert.AreEqual("erasable", marked.ColorKey, "couleur lavande memorisee");
            Assert.AreEqual(0.25f, marked.Emissive, Epsilon, "emission lavande memorisee");
            CollectionAssert.AreEqual(new[] { Groups.Erasable }, marked.ExtraGroups,
                "groupe marqueur memorise");

            ErasableBlock platform = Make(new Vector3(10, 1, 10), "platform", 0f, new[] { Groups.Platform });
            CollectionAssert.AreEqual(new[] { Groups.Platform }, platform.ExtraGroups,
                "la plateforme garde son groupe");

            // The permanent half of the ground language: photographable, never
            // carved (5.1).
            ErasableBlock permanent = Make(new Vector3(4, 1, 4), "platform", 0f, new[] { Groups.Platform }, false);
            Assert.IsFalse(permanent.Carvable, "un bloc permanent refuse la decoupe");
        }

        [Test]
        public void Un_bloc_porte_son_volume_et_sa_couche()
        {
            ErasableBlock block = Make(new Vector3(4, 1.5f, 2), "stone");
            Assert.AreEqual(Layers.World, block.gameObject.layer, "un bloc vit sur la couche monde");
            BoxCollider box = block.GetComponent<BoxCollider>();
            Assert.IsNotNull(box, "un bloc est solide");
            AssertVector(new Vector3(4, 1.5f, 2), box.size, "le collider reprend la taille du bloc");

            // The invisible stairs ramp keeps its collision and its carvability
            // and shows nothing.
            MeshRenderer mesh = block.GetComponentInChildren<MeshRenderer>(true);
            Assert.IsNotNull(mesh, "un bloc porte un maillage");
            Assert.IsTrue(mesh.enabled, "le maillage est allume par defaut");
            block.ShowMesh = false;
            Assert.IsFalse(block.ShowMesh, "la rampe invisible retient son etat");
            Assert.IsFalse(mesh.enabled, "la rampe invisible n'affiche aucune boite");
            Assert.IsNotNull(block.GetComponent<BoxCollider>(), "et reste solide");
            block.ShowMesh = true;
            Assert.IsTrue(mesh.enabled, "rallumer le maillage le rend visible");
        }

        [Test]
        public void Un_trou_pleine_hauteur_dans_un_mur_mince()
        {
            // A door-sized hole through a thin wall, full height: only the two
            // flanks survive.
            Vector3 size = new Vector3(10, 3.5f, 0.6f);
            Vector3 holeMin = new Vector3(-2, -1.75f, -0.3f);
            Vector3 holeMax = new Vector3(2, 1.75f, 0.3f);
            List<(Vector3 center, Vector3 size)> pieces = ErasableBlock.Decompose(size, holeMin, holeMax);
            Assert.AreEqual(2, pieces.Count, "trou pleine hauteur : deux flancs");
            Assert.AreEqual((10f - 4f) * 3.5f * 0.6f, TotalVolume(pieces), 0.001f,
                "volume conserve hors du trou");
            for (int i = 0; i < pieces.Count; i++)
            {
                Assert.AreEqual(3.5f, Mathf.Abs(pieces[i].center.x), 0.001f,
                    "flancs centres de part et d'autre");
                Assert.AreEqual(0f, pieces[i].center.y, 0.001f, "flancs centres en hauteur");
                Assert.AreEqual(0f, pieces[i].center.z, 0.001f, "flancs centres en epaisseur");
                Assert.AreEqual(3f, pieces[i].size.x, 0.001f, "flancs de la bonne largeur");
                Assert.AreEqual(3.5f, pieces[i].size.y, 0.001f, "flancs pleine hauteur");
                Assert.AreEqual(0.6f, pieces[i].size.z, 0.001f, "flancs pleine epaisseur");
            }
            // An absolute value alone would accept two flanks stacked on the
            // same side of the doorway, which is a wall with no door in it.
            Assert.AreEqual(0f, pieces[0].center.x + pieces[1].center.x, 0.001f,
                "un flanc de chaque cote du trou");
            AssertPiecesAreClean(size, holeMin, holeMax, pieces, "mur mince");
        }

        [Test]
        public void Un_trou_en_coin()
        {
            // A hole in one corner of a cube: three slabs remain, volumes add up.
            Vector3 size = new Vector3(4, 4, 4);
            Vector3 holeMin = new Vector3(0, 0, 0);
            Vector3 holeMax = new Vector3(2, 2, 2);
            List<(Vector3 center, Vector3 size)> pieces = ErasableBlock.Decompose(size, holeMin, holeMax);
            Assert.AreEqual(3, pieces.Count, "trou en coin : trois morceaux");
            Assert.AreEqual(64f - 8f, TotalVolume(pieces), 0.001f, "volume total = boite moins trou");
            AssertPiecesAreClean(size, holeMin, holeMax, pieces, "trou en coin");
        }

        [Test]
        public void Un_trou_interieur()
        {
            // A hole strictly inside the volume: all six slabs.
            Vector3 size = new Vector3(4, 4, 4);
            Vector3 holeMin = new Vector3(-1, -1, -1);
            Vector3 holeMax = new Vector3(1, 1, 1);
            List<(Vector3 center, Vector3 size)> pieces = ErasableBlock.Decompose(size, holeMin, holeMax);
            Assert.AreEqual(6, pieces.Count, "trou interieur : six morceaux");
            Assert.AreEqual(64f - 8f, TotalVolume(pieces), 0.001f, "volume total = boite moins trou");
            AssertPiecesAreClean(size, holeMin, holeMax, pieces, "trou interieur");
        }

        [Test]
        public void Un_trou_en_tranche()
        {
            // A hole spanning the whole width and height, biting a slice out of
            // the thickness: the front and back panels survive, nothing else.
            Vector3 size = new Vector3(4, 4, 4);
            Vector3 holeMin = new Vector3(-2, -2, -1);
            Vector3 holeMax = new Vector3(2, 2, 1);
            List<(Vector3 center, Vector3 size)> pieces = ErasableBlock.Decompose(size, holeMin, holeMax);
            Assert.AreEqual(2, pieces.Count, "trou en tranche : deux dalles");
            Assert.AreEqual(64f - 32f, TotalVolume(pieces), 0.001f, "volume total = boite moins tranche");
            for (int i = 0; i < pieces.Count; i++)
            {
                Assert.AreEqual(4f, pieces[i].size.x, 0.001f, "chaque dalle garde toute la largeur");
                Assert.AreEqual(4f, pieces[i].size.y, 0.001f, "chaque dalle garde toute la hauteur");
                Assert.AreEqual(1f, pieces[i].size.z, 0.001f, "chaque dalle garde son epaisseur");
                Assert.AreEqual(1.5f, Mathf.Abs(pieces[i].center.z), 0.001f,
                    "dalles centrees de part et d'autre de la tranche");
            }
            Assert.AreEqual(0f, pieces[0].center.z + pieces[1].center.z, 0.001f,
                "une dalle de chaque cote de la tranche");
            AssertPiecesAreClean(size, holeMin, holeMax, pieces, "trou en tranche");
        }

        [Test]
        public void Un_trou_plus_grand_que_la_boite()
        {
            Vector3 size = new Vector3(1.2f, 1.2f, 1.2f);
            List<(Vector3 center, Vector3 size)> pieces = ErasableBlock.Decompose(size,
                new Vector3(-3, -3, -3), new Vector3(3, 3, 3));
            Assert.AreEqual(0, pieces.Count, "trou plus grand que la boite : plus rien");
            Assert.AreEqual(0f, TotalVolume(pieces), 0.001f, "et donc plus aucun volume");
        }

        [Test]
        public void Un_trou_hors_de_la_boite()
        {
            // A hole entirely off the box clamps to a zero-thickness slice on the
            // boundary: the whole box survives as one piece.
            Vector3 size = new Vector3(2, 2, 2);
            Vector3 holeMin = new Vector3(5, -1, -1);
            Vector3 holeMax = new Vector3(7, 1, 1);
            List<(Vector3 center, Vector3 size)> pieces = ErasableBlock.Decompose(size, holeMin, holeMax);
            Assert.AreEqual(1, pieces.Count, "trou hors de la boite : un seul morceau");
            Assert.AreEqual(8f, TotalVolume(pieces), 0.001f, "la boite entiere subsiste");
            AssertVector(Vector3.zero, pieces[0].center, "le morceau reste centre sur la boite");
            AssertVector(size, pieces[0].size, "et garde sa taille");
            AssertPiecesAreClean(size, holeMin, holeMax, pieces, "trou hors de la boite");
        }

        [Test]
        public void Une_pellicule_est_abandonnee()
        {
            // Remainders thinner than MinFragment are dropped instead of leaving
            // unplayable films floating in the level.
            Vector3 size = new Vector3(4, 4, 4);
            List<(Vector3 center, Vector3 size)> pieces = ErasableBlock.Decompose(size,
                new Vector3(-1.98f, -2, -2), new Vector3(2, 2, 2));
            Assert.AreEqual(0, pieces.Count, "pellicule de 2 cm : aucun fragment");

            // Just above the threshold the flank does survive, so the drop is a
            // threshold and not a rounding accident.
            Vector3 keptMin = new Vector3(-1.8f, -2, -2);
            Vector3 keptMax = new Vector3(2, 2, 2);
            List<(Vector3 center, Vector3 size)> kept = ErasableBlock.Decompose(size, keptMin, keptMax);
            Assert.AreEqual(1, kept.Count, "flanc de 20 cm : un fragment");
            Assert.AreEqual(0.2f, kept[0].size.x, 0.001f, "le fragment garde son epaisseur");
            AssertVector(new Vector3(-1.9f, 0f, 0f), kept[0].center,
                "le fragment reste plaque contre la face du bloc");
            Assert.AreEqual(0.2f * 4f * 4f, TotalVolume(kept), 0.001f,
                "et son volume est celui du flanc, pas celui de la boite");
            AssertPiecesAreClean(size, keptMin, keptMax, kept, "flanc de 20 cm");
        }

        [Test]
        public void Les_constantes()
        {
            Assert.AreEqual(0.15f, ErasableBlock.SampleSpacing, Epsilon,
                "un echantillon tous les 15 cm");
            Assert.AreEqual(36, ErasableBlock.MaxSteps, "au plus 36 pas par axe");
            Assert.AreEqual(0.08f, ErasableBlock.MinFragment, Epsilon,
                "pas de fragment sous 8 cm");
            Assert.IsTrue(ErasableBlock.MinFragment < ErasableBlock.SampleSpacing,
                "un fragment minimal plus fin que le pas d'echantillonnage");
        }
    }
}
