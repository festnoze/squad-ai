using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;

namespace Viewpoint.Tests
{
    /// <summary>
    /// The pure playback helpers of the rewind (PRD section 10): finding where a
    /// time falls in the history, and reading the state at that moment.
    ///
    /// Both are static, so nothing is instantiated here: no Rewind component, no
    /// player, no scene. What the recording side does with them (freezing bodies,
    /// reviving retired objects) belongs to the PlayMode probe; what is checked
    /// here is the arithmetic those depend on.
    /// </summary>
    public sealed class RewindTests
    {
        /// One tracked body, so the pose table can be followed through a blend.
        const int BodyId = 7;

        /// <summary>
        /// A snapshot whose every field is derived from x, each with its OWN
        /// slope, so a blended sample betrays itself at once if a discrete field
        /// was interpolated: the midpoint of two of these values matches
        /// neither neighbour. A field held constant across the history could not
        /// tell the difference, which is why none of them is.
        /// The history below steps x by 10 per sample, so step runs 0, 1, 2.
        /// </summary>
        static RewindSample Sample(float t, float x, float yaw = 0f, string held = "")
        {
            int step = (int)x / 10;
            RewindSample sample = new RewindSample();
            sample.T = t;
            sample.PlayerPos = new Vector3(x, 0f, 0f);
            sample.Yaw = yaw;
            sample.Pitch = 0f;
            sample.Carried = (int)x;
            sample.Sealed = step;
            sample.Inserted = step * 2;
            sample.Required = 2 + step;
            sample.Films = 1 + step * 3;
            sample.HeldId = held;
            // Kept inside the four quarter turns a held photo can take.
            sample.Roll = (step * 2) % 4;
            sample.Bodies = new Dictionary<int, (Vector3 pos, Quaternion rot)>();
            sample.Bodies[BodyId] = (new Vector3(x, 0f, 0f), Quaternion.identity);
            return sample;
        }

        static List<RewindSample> History()
        {
            List<RewindSample> samples = new List<RewindSample>();
            samples.Add(Sample(0f, 0f));
            samples.Add(Sample(1f, 10f, 0f, "pile"));
            samples.Add(Sample(2f, 20f));
            return samples;
        }

        [Test]
        public void Situer_une_date_dans_l_historique()
        {
            List<RewindSample> samples = History();
            Assert.AreEqual(0, Rewind.Locate(samples, 0f), "le debut tombe sur le premier echantillon");
            Assert.AreEqual(0, Rewind.Locate(samples, 0.9f), "avant le deuxieme, on reste sur le premier");
            Assert.AreEqual(1, Rewind.Locate(samples, 1f), "une date exacte prend son echantillon");
            Assert.AreEqual(1, Rewind.Locate(samples, 1.5f), "entre deux, on prend le precedent");
            Assert.AreEqual(2, Rewind.Locate(samples, 9f), "au dela de l'historique, le dernier");
            Assert.AreEqual(0, Rewind.Locate(samples, -5f), "avant l'historique, le premier");
            Assert.AreEqual(-1, Rewind.Locate(new List<RewindSample>(), 1f), "historique vide : aucun index");
            Assert.AreEqual(-1, Rewind.Locate(null, 1f), "historique absent : aucun index");
        }

        [Test]
        public void La_recherche_reste_juste_sur_un_long_historique()
        {
            // The lookup is a binary search: a single sample is a special case,
            // and every other index must still come back exactly.
            List<RewindSample> one = new List<RewindSample>();
            one.Add(Sample(3f, 5f));
            Assert.AreEqual(0, Rewind.Locate(one, 0f), "un seul echantillon : avant lui, lui");
            Assert.AreEqual(0, Rewind.Locate(one, 3f), "un seul echantillon : a sa date, lui");
            Assert.AreEqual(0, Rewind.Locate(one, 99f), "un seul echantillon : apres lui, lui");

            List<RewindSample> samples = new List<RewindSample>();
            for (int i = 0; i < 40; i++)
            {
                samples.Add(Sample(i * 0.05f, i));
            }
            for (int i = 0; i < 40; i++)
            {
                float exact = i * 0.05f;
                Assert.AreEqual(i, Rewind.Locate(samples, exact), "une date exacte prend son echantillon");
                Assert.AreEqual(i, Rewind.Locate(samples, exact + 0.02f), "entre deux, on prend le precedent");
            }
        }

        [Test]
        public void L_etat_entre_deux_echantillons()
        {
            List<RewindSample> samples = History();
            RewindSample mid = Rewind.SampleAt(samples, 1.5f);
            Assert.IsNotNull(mid, "un etat est rendu");
            Assert.AreEqual(15f, mid.PlayerPos.x, 0.001f, "la position est interpolee entre deux echantillons");
            Assert.AreEqual(1.5f, mid.T, 0.001f, "la date rendue est celle demandee");
            // Discrete state does not interpolate: a photo is held or it is not.
            // The expected values are the EARLIER sample's (x = 10, step 1); the
            // midpoint of the two neighbours would be 15, 1.5, 3, 3.5, 5.5 and 1.
            Assert.AreEqual("pile", mid.HeldId, "l'etat discret vient de l'echantillon precedent");
            Assert.AreEqual(10, mid.Carried, "les compteurs ne s'interpolent pas");
            Assert.AreEqual(1, mid.Sealed, "le plomb porte vient de l'echantillon precedent");
            Assert.AreEqual(2, mid.Inserted, "les piles inserees viennent de l'echantillon precedent");
            Assert.AreEqual(3, mid.Required, "l'exigence vient de l'echantillon precedent");
            Assert.AreEqual(4, mid.Films, "la pellicule vient de l'echantillon precedent");
            Assert.AreEqual(2, mid.Roll, "la rotation tenue vient de l'echantillon precedent");
            Assert.IsNotNull(mid.Bodies, "la table des corps suit l'echantillon precedent");
            Assert.AreEqual(10f, mid.Bodies[BodyId].pos.x, 0.001f, "les corps suivis viennent de l'echantillon precedent");

            // A read must not rewrite the history it read.
            Assert.AreNotSame(samples[1], mid, "l'etat rendu est une copie");
            Assert.AreEqual(1f, samples[1].T, 0.001f, "la date de l'echantillon d'origine est intacte");
            Assert.AreEqual(10f, samples[1].PlayerPos.x, 0.001f, "sa position aussi");
        }

        [Test]
        public void Les_bords_de_l_historique()
        {
            List<RewindSample> samples = History();
            RewindSample first = Rewind.SampleAt(samples, 0f);
            Assert.IsNotNull(first, "un etat est rendu au debut");
            Assert.AreEqual(0f, first.PlayerPos.x, 0.001f, "au debut, l'etat initial");
            RewindSample last = Rewind.SampleAt(samples, 5f);
            Assert.IsNotNull(last, "un etat est rendu au dela");
            Assert.AreEqual(20f, last.PlayerPos.x, 0.001f, "au dela, le dernier etat connu");
            Assert.AreEqual(20, last.Carried, "et ses compteurs avec");
            Assert.AreEqual(2, last.Sealed, "le plomb du dernier etat connu");
            Assert.AreEqual(4, last.Inserted, "les piles inserees du dernier etat connu");
            Assert.AreEqual(4, last.Required, "l'exigence du dernier etat connu");
            Assert.AreEqual(7, last.Films, "la pellicule du dernier etat connu");
            // Past the end there is nothing to blend, so the sample comes back
            // as it was recorded, DATE INCLUDED: unlike the blended path, the
            // date is not moved to the one asked for. A caller that needs the
            // requested date must restamp it, which is what CaptureAt does.
            Assert.AreEqual(2f, last.T, 0.001f, "au dela, la date reste celle du dernier echantillon");
            RewindSample before = Rewind.SampleAt(samples, -3f);
            Assert.IsNotNull(before, "un etat est rendu avant le debut");
            Assert.AreEqual(0f, before.PlayerPos.x, 0.001f, "avant le debut, l'etat initial");
            Assert.IsNull(Rewind.SampleAt(new List<RewindSample>(), 1f), "historique vide : etat vide");
            Assert.IsNull(Rewind.SampleAt(null, 1f), "historique absent : etat vide");
        }

        [Test]
        public void Deux_echantillons_a_la_meme_date()
        {
            // Two snapshots stamped at the same instant (a fixed step that
            // recorded twice) must resolve, not throw: the lookup lands on the
            // later of the two, which is also why the zero span of SampleAt is
            // never divided.
            List<RewindSample> samples = new List<RewindSample>();
            samples.Add(Sample(1f, 4f));
            samples.Add(Sample(1f, 9f));
            RewindSample state = Rewind.SampleAt(samples, 1f);
            Assert.IsNotNull(state, "un etat est rendu malgre la date double");
            Assert.AreEqual(9f, state.PlayerPos.x, 0.001f, "a date egale, le dernier echantillon situe gagne");
        }

        [Test]
        public void Le_lacet_prend_le_raccourci()
        {
            // Rewinding across the +PI / -PI seam must not spin the player.
            List<RewindSample> samples = new List<RewindSample>();
            samples.Add(Sample(0f, 0f, -3f));
            samples.Add(Sample(1f, 0f, 3f));
            RewindSample mid = Rewind.SampleAt(samples, 0.5f);
            Assert.IsNotNull(mid, "un etat est rendu sur la couture");
            Assert.IsTrue(Mathf.Abs(mid.Yaw) > 3f, "le lacet passe par le raccourci, pas par zero");
            // -3 to 3 the short way is an arc of 0.283 rad crossing the seam, so
            // the halfway point is the seam itself. A tolerance loose enough to
            // accept the long way (0.0) would prove nothing.
            Assert.AreEqual(-Mathf.PI, mid.Yaw, 0.001f,
                "le milieu du raccourci tombe sur la couture");

            // Away from the seam it is a plain interpolation.
            List<RewindSample> plain = new List<RewindSample>();
            plain.Add(Sample(0f, 0f, 0f));
            plain.Add(Sample(1f, 0f, 1f));
            RewindSample half = Rewind.SampleAt(plain, 0.5f);
            Assert.AreEqual(0.5f, half.Yaw, 0.001f, "loin de la couture, le lacet s'interpole droit");
        }

        [Test]
        public void Le_tangage_s_interpole()
        {
            RewindSample down = Sample(0f, 0f);
            down.Pitch = -1f;
            RewindSample up = Sample(1f, 0f);
            up.Pitch = 1f;
            List<RewindSample> samples = new List<RewindSample>();
            samples.Add(down);
            samples.Add(up);
            RewindSample mid = Rewind.SampleAt(samples, 0.5f);
            Assert.AreEqual(0f, mid.Pitch, 0.001f, "le tangage est interpole entre deux echantillons");
        }

        [Test]
        public void Les_constantes()
        {
            Assert.IsTrue(Rewind.SampleHz >= 10f, "au moins dix echantillons par seconde");
            Assert.IsTrue(Rewind.RewindSpeed > 1f, "le rembobinage remonte plus vite que le temps");
            Assert.IsTrue(Rewind.MaxSamples >= (int)(Rewind.SampleHz * 120f),
                "au moins deux minutes d'historique");

            // The exact values of PRD 10, because the window is a design
            // promise and not a tuning knob: a photo wasted more than five
            // minutes ago is lost for good, and the levels are built for it.
            Assert.AreEqual(20f, Rewind.SampleHz, 0.001f, "vingt echantillons par seconde");
            Assert.AreEqual(2.5f, Rewind.RewindSpeed, 0.001f,
                "deux secondes et demie d'histoire par seconde de touche");
            Assert.AreEqual(6000, Rewind.MaxSamples, "six mille echantillons d'historique");
            Assert.AreEqual(300f, Rewind.MaxSamples / Rewind.SampleHz, 0.001f,
                "cinq minutes d'historique");
        }
    }
}
