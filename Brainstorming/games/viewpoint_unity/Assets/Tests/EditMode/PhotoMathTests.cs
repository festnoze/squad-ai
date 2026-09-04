using NUnit.Framework;
using UnityEngine;

namespace Viewpoint.Tests
{
    /// <summary>
    /// Pure geometry of the photo frustum and the thumbnail projection. Port of
    /// the Godot suite <c>tests/test_photo_math.gd</c> (PRD 17.2, photo_math).
    ///
    /// Everything here speaks DESIGN space: x right, y up, -z forward, so the
    /// depth of a point is <c>-local.z</c>. Nothing in this file mirrors z, and
    /// nothing in PhotoMath does either: that is the whole point of keeping the
    /// mirror in one place (see DesignSpaceTests).
    ///
    /// The assertion messages are the original French ones, kept verbatim: they
    /// are the readable record of what broke.
    /// </summary>
    public sealed class PhotoMathTests
    {
        // The photo frustum of the game: square frame, 50 deg vertical fov, and
        // a 12 m reach. Written out rather than read from PhotoMath so that a
        // change to the constants shows up as a failure and not as a silently
        // retuned test.
        const float Fov = 50f;
        const float Aspect = 1f;
        const float Near = 0f;
        const float Far = 12f;

        [Test]
        public void La_demi_hauteur_du_cone()
        {
            Assert.AreEqual(5f * Mathf.Tan(25f * Mathf.Deg2Rad), PhotoMath.HalfExtentAt(5f, Fov), 0.0001f,
                "demi-hauteur a 5 m");
            Assert.AreEqual(0f, PhotoMath.HalfExtentAt(0f, Fov), 0.0001f,
                "demi-hauteur nulle a l'apex");

            // Linear in depth: twice the distance, twice the frame. The backdrop
            // sizing and the carve both rest on this.
            Assert.AreEqual(2f * PhotoMath.HalfExtentAt(5f, Fov), PhotoMath.HalfExtentAt(10f, Fov), 0.001f,
                "la demi-hauteur est lineaire en profondeur");

            // A 90 deg frame opens exactly as wide as it is deep, since tan 45
            // is 1. Written without trigonometry on purpose: it pins the half
            // angle convention (the tangent is taken of fov / 2, never of fov)
            // with a number no retune can shift.
            Assert.AreEqual(10f, PhotoMath.HalfExtentAt(10f, 90f), 0.001f,
                "un cone de 90 deg s'ouvre autant qu'il est profond");
        }

        [Test]
        public void L_appartenance_au_cone()
        {
            Assert.IsTrue(PhotoMath.PointInFrustum(new Vector3(0f, 0f, -5f), Fov, Aspect, Near, Far),
                "le centre a 5 m est dedans");
            Assert.IsFalse(PhotoMath.PointInFrustum(new Vector3(0f, 0f, -13f), Fov, Aspect, Near, Far),
                "au dela du plan lointain, dehors");
            Assert.IsFalse(PhotoMath.PointInFrustum(new Vector3(0f, 0f, 3f), Fov, Aspect, Near, Far),
                "derriere la camera, dehors");

            // Both planes are inclusive, and the near one is not decoration:
            // PhotoCapture holds it at 0.5 so a box pressed against the lens is
            // ignored instead of filling the whole frame, and it clips at
            // exactly 12 so a wall standing on the far plane is still kept.
            Assert.IsFalse(PhotoMath.PointInFrustum(new Vector3(0f, 0f, -0.2f), Fov, Aspect, 0.5f, Far),
                "en deca du plan proche, dehors");
            Assert.IsTrue(PhotoMath.PointInFrustum(new Vector3(0f, 0f, -0.5f), Fov, Aspect, 0.5f, Far),
                "juste sur le plan proche, dedans");
            Assert.IsTrue(PhotoMath.PointInFrustum(new Vector3(0f, 0f, -Far), Fov, Aspect, Near, Far),
                "juste sur le plan lointain, dedans");

            float edge = PhotoMath.HalfExtentAt(5f, Fov);
            Assert.IsTrue(PhotoMath.PointInFrustum(new Vector3(edge - 0.01f, 0f, -5f), Fov, Aspect, Near, Far),
                "juste sous le bord lateral, dedans");
            Assert.IsFalse(PhotoMath.PointInFrustum(new Vector3(edge + 0.01f, 0f, -5f), Fov, Aspect, Near, Far),
                "juste au dela du bord lateral, dehors");
            Assert.IsFalse(PhotoMath.PointInFrustum(new Vector3(0f, edge + 0.01f, -5f), Fov, Aspect, Near, Far),
                "juste au dela du bord haut, dehors");
            Assert.IsTrue(PhotoMath.PointInFrustum(new Vector3(0f, -edge + 0.01f, -5f), Fov, Aspect, Near, Far),
                "pres du bord bas, dedans");
        }

        [Test]
        public void L_aspect_elargit_le_cone()
        {
            float edge = PhotoMath.HalfExtentAt(5f, Fov);
            Assert.IsTrue(PhotoMath.PointInFrustum(new Vector3(edge * 1.5f, 0f, -5f), Fov, 2f, Near, Far),
                "aspect 2 : deux fois plus large");
            Assert.IsFalse(PhotoMath.PointInFrustum(new Vector3(edge * 1.5f, 0f, -5f), Fov, 1f, Near, Far),
                "aspect 1 : le meme point est dehors");

            // A wide frame is wider, never taller: the vertical fov owns the
            // height whatever the aspect.
            Assert.IsFalse(PhotoMath.PointInFrustum(new Vector3(0f, edge * 1.5f, -5f), Fov, 2f, Near, Far),
                "aspect 2 : la hauteur ne change pas");
        }

        [Test]
        public void La_projection_pinhole()
        {
            Vector2 center = PhotoMath.ProjectPoint(new Vector3(0f, 0f, -5f), Fov, Aspect);
            Assert.AreEqual(0f, center.x, 0.0001f, "le centre se projette en x = 0");
            Assert.AreEqual(0f, center.y, 0.0001f, "le centre se projette en y = 0");

            float edge = PhotoMath.HalfExtentAt(5f, Fov);
            Vector2 right = PhotoMath.ProjectPoint(new Vector3(edge, 0f, -5f), Fov, Aspect);
            Assert.AreEqual(1f, right.x, 0.001f, "le bord droit se projette en x = 1");

            Vector2 sym = PhotoMath.ProjectPoint(new Vector3(-edge, edge, -5f), Fov, Aspect);
            Assert.AreEqual(-1f, sym.x, 0.001f, "symetrie gauche");
            Assert.AreEqual(1f, sym.y, 0.001f, "le haut se projette en y = 1");

            // The same lateral offset projects smaller when it is further away.
            Vector2 nearPoint = PhotoMath.ProjectPoint(new Vector3(1f, 0f, -4f), Fov, Aspect);
            Vector2 farPoint = PhotoMath.ProjectPoint(new Vector3(1f, 0f, -8f), Fov, Aspect);
            Assert.Less(farPoint.x, nearPoint.x, "la perspective retrecit avec la distance");
            Assert.AreEqual(2f, nearPoint.x / farPoint.x, 0.001f,
                "deux fois plus loin, deux fois plus pres du centre");

            // The aspect divides x and leaves y untouched: a wide frame brings
            // the same point closer to the center horizontally and not at all
            // vertically. Nothing else in the suite projects with aspect != 1,
            // so a swapped divide would go unnoticed.
            Vector2 wide = PhotoMath.ProjectPoint(new Vector3(edge, edge, -5f), Fov, 2f);
            Assert.AreEqual(0.5f, wide.x, 0.001f, "aspect 2 : le bord droit tombe a x = 0.5");
            Assert.AreEqual(1f, wide.y, 0.001f, "aspect 2 : la hauteur ne change pas");
        }

        [Test]
        public void La_taille_du_fond_peint()
        {
            Vector2 size = PhotoMath.BackdropSize(8f, Fov, 1f);
            Assert.AreEqual(size.y, size.x, 0.0001f, "backdrop carre en aspect 1");
            Assert.AreEqual(2f * 8f * Mathf.Tan(25f * Mathf.Deg2Rad), size.y, 0.001f,
                "hauteur du backdrop a 8 m");

            Vector2 wide = PhotoMath.BackdropSize(8f, Fov, 2f);
            Assert.AreEqual(wide.y * 2f, wide.x, 0.001f, "aspect 2 : deux fois plus large");
            Assert.AreEqual(size.y, wide.y, 0.0001f, "aspect 2 : la hauteur est inchangee");

            // A quad of exactly this size fills the frame: its corner is on the
            // edge of the frustum, which is what makes a backdrop hide the void
            // behind a photo without overshooting it.
            Assert.AreEqual(2f * PhotoMath.HalfExtentAt(8f, Fov), size.y, 0.0001f,
                "le backdrop remplit exactement le cadre");
        }

        [Test]
        public void Les_constantes_du_cadre()
        {
            Assert.AreEqual(50f, PhotoMath.PhotoFovDeg, 0.0001f, "champ de vision de la photo : 50 deg");
            Assert.AreEqual(1f, PhotoMath.PhotoAspect, 0.0001f, "la photo est carree comme un polaroid");
            Assert.AreEqual(12f, PhotoMath.DefaultEraseDepth, 0.0001f, "portee d'effacement par defaut : 12 m");
        }
    }
}
