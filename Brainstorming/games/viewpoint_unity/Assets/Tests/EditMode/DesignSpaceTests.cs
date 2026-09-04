using NUnit.Framework;
using UnityEngine;

namespace Viewpoint.Tests
{
    /// <summary>
    /// The one conversion between DESIGN space (every authored number: x right,
    /// y up, -z forward) and Unity space (+z forward). PRD 4.2 and 17.2, last
    /// paragraph: this suite is new for the Unity port, the Godot original could
    /// not have it because it had nothing to convert.
    ///
    /// It exists because the mirror is the single most dangerous line of the
    /// port: applied twice it is the identity, so a double conversion does not
    /// crash and does not look wrong in code, it just puts the world back to
    /// front. What is pinned here is the algebra everything else relies on.
    ///
    /// The last case is the other half of the same danger and the other half of
    /// the same PRD 17.2 bullet: the roll direction of section 6.4. Every
    /// rotation sign flips under a mirror, so a roll ported by copying the Godot
    /// sign turns the picture the wrong way while still turning by 90 degrees.
    ///
    /// The assertion messages are French, like the rest of the harness.
    /// </summary>
    public sealed class DesignSpaceTests
    {
        // Sample points chosen so no coordinate can be confused with another and
        // so both signs of z are covered, plus the degenerate z = 0 plane.
        static readonly Vector3[] Samples =
        {
            new Vector3(1f, 2f, 3f),
            new Vector3(-4.5f, 0.05f, -7.25f),
            new Vector3(0f, 0f, 0f),
            new Vector3(2.5f, -1.62f, 0f),
            new Vector3(0f, 1.67f, -24f),
        };

        [Test]
        public void Le_miroir_inverse_z_et_rien_d_autre()
        {
            Vector3 unity = DesignSpace.ToUnity(new Vector3(1f, 2f, 3f));
            Assert.AreEqual(1f, unity.x, 0.0001f, "x inchange par le miroir");
            Assert.AreEqual(2f, unity.y, 0.0001f, "y inchange par le miroir");
            Assert.AreEqual(-3f, unity.z, 0.0001f, "z inverse par le miroir");

            // The algebra the whole port rests on, on every sample: only z moves.
            foreach (Vector3 design in Samples)
            {
                Vector3 mirrored = DesignSpace.ToUnity(design);
                Assert.AreEqual(design.x, mirrored.x, 0.0001f, "x intact pour " + design);
                Assert.AreEqual(design.y, mirrored.y, 0.0001f, "y intact pour " + design);
                Assert.AreEqual(-design.z, mirrored.z, 0.0001f, "z mirroite pour " + design);
            }
        }

        [Test]
        public void Le_miroir_est_une_involution()
        {
            // Which is exactly why the same function serves both directions, and
            // why applying it twice is a silent bug and not an error.
            foreach (Vector3 design in Samples)
            {
                Vector3 back = DesignSpace.ToUnity(DesignSpace.ToUnity(design));
                Assert.AreEqual(design.x, back.x, 0.0001f, "double miroir : x revient pour " + design);
                Assert.AreEqual(design.y, back.y, 0.0001f, "double miroir : y revient pour " + design);
                Assert.AreEqual(design.z, back.z, 0.0001f, "double miroir : z revient pour " + design);
            }

            Vector3 twiceForward = DesignSpace.ToUnity(DesignSpace.ToUnity(DesignSpace.DesignForward));
            Assert.AreEqual(DesignSpace.DesignForward.z, twiceForward.z, 0.0001f,
                "convertir deux fois remet le monde a l'envers, donc a l'endroit");
        }

        [Test]
        public void Le_miroir_est_lineaire()
        {
            // A mirror is linear, so it maps directions the way it maps points:
            // that is the licence for using one function for positions, offsets
            // and directions alike.
            Vector3 a = new Vector3(1f, 2f, 3f);
            Vector3 b = new Vector3(-0.5f, 4f, -6f);

            Vector3 sum = DesignSpace.ToUnity(a + b);
            Vector3 sumOfParts = DesignSpace.ToUnity(a) + DesignSpace.ToUnity(b);
            Assert.AreEqual(sumOfParts.x, sum.x, 0.0001f, "additivite du miroir en x");
            Assert.AreEqual(sumOfParts.y, sum.y, 0.0001f, "additivite du miroir en y");
            Assert.AreEqual(sumOfParts.z, sum.z, 0.0001f, "additivite du miroir en z");

            Vector3 scaled = DesignSpace.ToUnity(a * 3f);
            Vector3 scaledAfter = DesignSpace.ToUnity(a) * 3f;
            Assert.AreEqual(scaledAfter.z, scaled.z, 0.0001f, "homogeneite du miroir");

            Vector3 zero = DesignSpace.ToUnity(Vector3.zero);
            Assert.AreEqual(0f, zero.magnitude, 0.0001f, "l'origine reste l'origine");

            // A mirror is an isometry: it changes no distance, which is why a
            // level keeps its proportions through the conversion.
            Assert.AreEqual((a - b).magnitude,
                (DesignSpace.ToUnity(a) - DesignSpace.ToUnity(b)).magnitude, 0.0001f,
                "le miroir ne change aucune distance");
        }

        [Test]
        public void Les_avants_se_correspondent()
        {
            Assert.AreEqual(-1f, DesignSpace.DesignForward.z, 0.0001f, "l'avant du design est -z");
            Assert.AreEqual(1f, DesignSpace.UnityForward.z, 0.0001f, "l'avant d'Unity est +z");

            Vector3 forward = DesignSpace.ToUnity(DesignSpace.DesignForward);
            Assert.AreEqual(DesignSpace.UnityForward.x, forward.x, 0.0001f, "l'avant converti n'a pas de x");
            Assert.AreEqual(DesignSpace.UnityForward.y, forward.y, 0.0001f, "l'avant converti n'a pas de y");
            Assert.AreEqual(DesignSpace.UnityForward.z, forward.z, 0.0001f,
                "l'avant du design devient l'avant d'Unity");

            // A prop authored at design (0, -1.72, -5) is 5 m IN FRONT of the
            // camera in Unity, at local z = +5 (PRD 4.2).
            Vector3 prop = DesignSpace.ToUnity(new Vector3(0f, -1.72f, -5f));
            Assert.AreEqual(5f, prop.z, 0.0001f, "un accessoire a -5 en design est a +5 devant la camera");
            Assert.AreEqual(-1.72f, prop.y, 0.0001f, "la hauteur d'un accessoire ne bouge pas");
        }

        [Test]
        public void Une_taille_ne_passe_pas_par_le_miroir()
        {
            // Sizes are never converted, because a mirror does not change an
            // extent. This case states what the mirror would do to one, so the
            // reason is on the record: a negative thickness on a box.
            Vector3 size = new Vector3(0.6f, 1.3f, 2.4f);
            Vector3 mirrored = DesignSpace.ToUnity(size);

            Assert.Less(mirrored.z, 0f,
                "une taille passee au miroir donnerait une epaisseur negative");
            Assert.AreEqual(Mathf.Abs(size.z), Mathf.Abs(mirrored.z), 0.0001f,
                "le miroir ne change que le signe, jamais l'etendue");
            Assert.AreEqual(size.x, mirrored.x, 0.0001f, "la largeur serait intacte");
            Assert.AreEqual(size.y, mirrored.y, 0.0001f, "la hauteur serait intacte");
        }

        [Test]
        public void Le_lacet_change_de_signe()
        {
            Assert.AreEqual(0f, DesignSpace.YawToUnityDegrees(0f), 0.0001f,
                "lacet nul : aucun niveau ne fixe le signe, la suite le fixe");
            Assert.AreEqual(-90f, DesignSpace.YawToUnityDegrees(Mathf.PI * 0.5f), 0.001f,
                "un quart de tour design devient -90 deg Unity");
            Assert.AreEqual(90f, DesignSpace.YawToUnityDegrees(-Mathf.PI * 0.5f), 0.001f,
                "le miroir inverse le sens de rotation");
            Assert.AreEqual(-180f, DesignSpace.YawToUnityDegrees(Mathf.PI), 0.001f,
                "un demi-tour reste un demi-tour");

            // The general rule, on values no level authors so nothing else can
            // pin them, stated as BEHAVIOUR and not as the formula: asserting
            // -yaw * Rad2Deg would only restate the implementation and would
            // still pass if the sign convention were wrong on screen. What has
            // to hold is that turning Unity's forward by the converted yaw lands
            // exactly where the mirror sends the design forward turned by the
            // original yaw. Godot turns about +y right handed, so
            // v' = (x cos + z sin, y, -x sin + z cos).
            float[] yaws = { 0.3f, -1.4f, 2.7f, 6.28318f };
            foreach (float yaw in yaws)
            {
                Vector3 turned = Quaternion.Euler(0f, DesignSpace.YawToUnityDegrees(yaw), 0f)
                    * DesignSpace.UnityForward;
                Vector3 d = DesignSpace.DesignForward;
                Vector3 expected = DesignSpace.ToUnity(new Vector3(
                    d.x * Mathf.Cos(yaw) + d.z * Mathf.Sin(yaw),
                    d.y,
                    -d.x * Mathf.Sin(yaw) + d.z * Mathf.Cos(yaw)));
                Assert.AreEqual(expected.x, turned.x, 0.001f, "lacet converti : x du regard pour " + yaw);
                Assert.AreEqual(expected.y, turned.y, 0.001f, "lacet converti : y du regard pour " + yaw);
                Assert.AreEqual(expected.z, turned.z, 0.001f, "lacet converti : z du regard pour " + yaw);
            }
        }

        [Test]
        public void Le_roulis_tourne_dans_le_sens_des_aiguilles()
        {
            // PRD 6.4, D1: ONE WHEEL STEP DOWN TURNS THE PICTURE 90 DEG
            // CLOCKWISE AS THE PLAYER SEES IT, in the world exactly as on the
            // HUD, or the promise of the game (what you see raised is what you
            // place) is broken. The sign is a derivation, not a taste: the
            // placer is a child of the camera and the player watches its local
            // +z from the negative end, where a positive rotation reads counter
            // clockwise. So it is pinned by WHERE A KNOWN OFFSET LANDS and never
            // by a number of degrees, which is the one form a mirrored port
            // cannot get right by accident.
            //
            // The worked example of PRD 6.4 is the cornice slab: its design
            // offset (1.6, -0.6), right of the frame and slightly low, must land
            // at (-0.6, -1.6) after one step and at (-1.6, +0.6) after two.
            Vector3 offset = new Vector3(1.6f, -0.6f, 3.2f);

            Vector3 zero = PhotoPlacer.RollRotation(0) * offset;
            Assert.AreEqual(offset.x, zero.x, 0.0001f, "sans roulis, rien ne bouge en x");
            Assert.AreEqual(offset.y, zero.y, 0.0001f, "sans roulis, rien ne bouge en y");

            Vector3 one = PhotoPlacer.RollRotation(1) * offset;
            Assert.AreEqual(-0.6f, one.x, 0.001f, "un cran : ce qui etait bas passe a gauche");
            Assert.AreEqual(-1.6f, one.y, 0.001f, "un cran : ce qui etait a droite passe en bas");
            Assert.AreEqual(offset.z, one.z, 0.001f, "le roulis tourne autour de l'axe du regard");

            Vector3 two = PhotoPlacer.RollRotation(2) * offset;
            Assert.AreEqual(-1.6f, two.x, 0.001f, "deux crans : l'offset est simplement inverse en x");
            Assert.AreEqual(0.6f, two.y, 0.001f, "deux crans : et inverse en y");
            Assert.AreEqual(offset.z, two.z, 0.001f, "un demi-tour reste dans le plan de l'image");

            // Four steps is the identity, which is what makes the wheel's modulo
            // 4 legal, and a step up must undo a step down.
            Vector3 four = PhotoPlacer.RollRotation(4) * offset;
            Assert.AreEqual(offset.x, four.x, 0.001f, "quatre crans : tour complet en x");
            Assert.AreEqual(offset.y, four.y, 0.001f, "quatre crans : tour complet en y");

            Vector3 back = PhotoPlacer.RollRotation(-1) * one;
            Assert.AreEqual(offset.x, back.x, 0.001f, "la molette vers le haut defait la molette vers le bas");
            Assert.AreEqual(offset.y, back.y, 0.001f, "la molette vers le haut defait la molette vers le bas");
        }
    }
}
