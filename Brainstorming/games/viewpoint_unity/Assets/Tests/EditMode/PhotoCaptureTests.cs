using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;

namespace Viewpoint.Tests
{
    /// <summary>
    /// The in-game camera: world candidates filtered by the capture frustum and
    /// re-expressed in camera space. Since v4 the film captures EVERYTHING it
    /// frames, the void included, so Capture never returns an empty definition.
    /// Since v5.1 blocks are captured BY VOLUME, clipped to the frame, the same
    /// way a placement carves them. Port of tests/test_photo_capture.gd
    /// (PRD 7.2, 7.3, 7.4 and 17.2).
    ///
    /// SPACES. Everything the original suite authors is DESIGN space (x right,
    /// y up, -z forward) and everything PhotoCapture returns is DESIGN space
    /// too, because a PhotoDef is design data. The runtime, on the other hand,
    /// is fed Unity matrices: the anchor arrives as a world to anchor matrix and
    /// a candidate carries a Unity world transform. So every number below is
    /// written exactly as the original wrote it, and the mirror on z is applied
    /// once, inside the builders of this file, on the way INTO the runtime.
    /// Nothing is mirrored on the way out, since what comes out is already
    /// design space.
    ///
    /// Assertion messages are the original's French on purpose: they are the
    /// readable record of what broke.
    /// </summary>
    public sealed class PhotoCaptureTests
    {
        const float Tol = 0.001f;

        /// <summary>
        /// A previous suite must not be able to make this one pass or fail:
        /// Capture walks Groups, and the dynamic registry is global.
        /// </summary>
        [SetUp]
        public void SetUp()
        {
            Groups.Clear();
            PhotoDefs.ClearDynamic();
        }

        [TearDown]
        public void TearDown()
        {
            Groups.Clear();
            PhotoDefs.ClearDynamic();
        }

        // ------------------------------------------------------------------
        // Builders. The one place the z mirror happens.
        // ------------------------------------------------------------------

        /// <summary>
        /// The world to anchor matrix for a camera authored in design space.
        /// The original built Transform3D(Basis(Vector3.UP, yaw), pos) and let
        /// props_from take its affine_inverse; PropsFrom takes the inverse
        /// directly, so it is taken here.
        /// </summary>
        static Matrix4x4 AnchorInverse(Vector3 designPos, float designYawRadians)
        {
            Quaternion rotation = Quaternion.Euler(0f, DesignSpace.YawToUnityDegrees(designYawRadians), 0f);
            return Matrix4x4.TRS(DesignSpace.ToUnity(designPos), rotation, Vector3.one).inverse;
        }

        /// <summary>
        /// A box candidate authored by its design-space center. The box is axis
        /// aligned, so mirroring its center mirrors the whole volume; sizes are
        /// never mirrored, a mirror does not change an extent.
        /// </summary>
        static PhotoCapture.CaptureCandidate Box(Vector3 designCenter, Vector3 size, string color)
        {
            PhotoCapture.CaptureCandidate candidate = new PhotoCapture.CaptureCandidate();
            candidate.IsBattery = false;
            candidate.Xform = Matrix4x4.TRS(DesignSpace.ToUnity(designCenter), Quaternion.identity, Vector3.one);
            candidate.Size = size;
            candidate.Color = color;
            return candidate;
        }

        /// <summary>A battery candidate authored by the design position of its BASE.</summary>
        static PhotoCapture.CaptureCandidate BatteryAt(Vector3 designBase)
        {
            PhotoCapture.CaptureCandidate candidate = new PhotoCapture.CaptureCandidate();
            candidate.IsBattery = true;
            candidate.Pos = DesignSpace.ToUnity(designBase);
            candidate.Size = Vector3.zero;
            candidate.Color = "battery";
            return candidate;
        }

        static List<PhotoCapture.CaptureCandidate> Candidates(params PhotoCapture.CaptureCandidate[] items)
        {
            return new List<PhotoCapture.CaptureCandidate>(items);
        }

        /// <summary>
        /// A box-to-anchor matrix for a box whose center is given directly in
        /// DESIGN camera space. ClipToFrustum is handed a Unity anchor-space
        /// matrix and mirrors the corners itself, so the center goes in
        /// mirrored: the exact analogue of the original passing
        /// Transform3D().translated(...) straight to clip_to_frustum.
        /// </summary>
        static Matrix4x4 InCameraAt(Vector3 designCenter)
        {
            return Matrix4x4.TRS(DesignSpace.ToUnity(designCenter), Quaternion.identity, Vector3.one);
        }

        /// <summary>
        /// A design-space world point expressed in DESIGN camera space. Two
        /// mirrors, one per space crossing: design world to Unity world going
        /// in, Unity anchor to design camera coming out. Not a double mirror
        /// cancelling itself out, since anchorInverse sits between them.
        /// </summary>
        static Vector3 ToDesignCamera(Matrix4x4 anchorInverse, Vector3 designPoint)
        {
            return DesignSpace.ToUnity(anchorInverse.MultiplyPoint3x4(DesignSpace.ToUnity(designPoint)));
        }

        /// <summary>
        /// Component-wise, with a tolerance. The original compared Vector3
        /// exactly, which a matrix product cannot promise here; the tolerance is
        /// a thousandth of a meter, far below anything a level can notice.
        /// </summary>
        static void AssertNear(Vector3 actual, Vector3 expected, string message)
        {
            Assert.AreEqual(expected.x, actual.x, Tol, message);
            Assert.AreEqual(expected.y, actual.y, Tol, message);
            Assert.AreEqual(expected.z, actual.z, Tol, message);
        }

        static List<string> ColorsOf(List<PhotoProp> props)
        {
            List<string> colors = new List<string>();
            for (int i = 0; i < props.Count; i++)
            {
                colors.Add(props[i].Color);
            }
            return colors;
        }

        static List<string> KindsOf(List<PhotoProp> props)
        {
            List<string> kinds = new List<string>();
            for (int i = 0; i < props.Count; i++)
            {
                kinds.Add(props[i].Kind);
            }
            return kinds;
        }

        // ------------------------------------------------------------------
        // Cases
        // ------------------------------------------------------------------

        [Test]
        public void Le_filtre_du_cadre()
        {
            // Camera at the origin looking down -z: one box in frame, one behind,
            // one beyond the capture depth, one far off to the side.
            Matrix4x4 anchorInverse = AnchorInverse(new Vector3(0f, 1.62f, 0f), 0f);
            List<PhotoCapture.CaptureCandidate> candidates = Candidates(
                Box(new Vector3(0f, 1.0f, -4f), new Vector3(1f, 1f, 1f), "erasable"),
                Box(new Vector3(0f, 1.0f, 4f), new Vector3(1f, 1f, 1f), "erasable"),
                Box(new Vector3(0f, 1.0f, -20f), new Vector3(1f, 1f, 1f), "erasable"),
                Box(new Vector3(9f, 1.0f, -4f), new Vector3(1f, 1f, 1f), "erasable"));

            List<PhotoProp> props = PhotoCapture.PropsFrom(candidates, anchorInverse);
            Assert.AreEqual(1, props.Count, "seule la boite cadree est capturee");

            PhotoProp prop = props[0];
            Assert.AreEqual("box", prop.Kind, "genre conserve");
            Assert.AreEqual(-4.0f, prop.Pos.z, Tol, "profondeur exprimee dans l'espace camera");
            Assert.AreEqual(-0.62f, prop.Pos.y, Tol, "hauteur relative a l'oeil");
            Assert.AreEqual(0.0f, prop.Pos.x, Tol, "position laterale exacte");
            // A fully framed object is copied AS IT IS: same size, same place.
            AssertNear(prop.Size, new Vector3(1f, 1f, 1f), "taille exacte d'une boite entierement cadree");
        }

        [Test]
        public void Les_objets_cadres_sont_exacts()
        {
            // Fidelity of the shot: whatever is entirely in frame comes back at
            // its real size and its real place, with no margin added by the
            // clipping.
            Matrix4x4 anchorInverse = AnchorInverse(new Vector3(0f, 1.62f, 0f), 0f);
            Vector3[] sizes =
            {
                new Vector3(1f, 1f, 1f),
                new Vector3(0.4f, 2.2f, 0.4f),
                new Vector3(1.3f, 1.3f, 1.3f),
                new Vector3(2.0f, 0.3f, 2.0f),
            };
            float[] depths = { 2.0f, 4.0f, 6.0f, 9.0f };

            for (int i = 0; i < sizes.Length; i++)
            {
                Vector3 size = sizes[i];
                float depth = depths[i];
                Vector3 center = new Vector3(0.2f, 1.62f, -depth);
                List<PhotoProp> props = PhotoCapture.PropsFrom(
                    Candidates(Box(center, size, "wood")), anchorInverse);

                string where = "la boite " + i;
                Assert.AreEqual(1, props.Count, where + " est cadree");
                AssertNear(props[0].Size, size, "taille inchangee pour " + where);
                Assert.AreEqual(0.2f, props[0].Pos.x, Tol, "abscisse exacte pour " + where);
                Assert.AreEqual(0.0f, props[0].Pos.y, Tol, "hauteur exacte pour " + where);
                Assert.AreEqual(-depth, props[0].Pos.z, Tol, "profondeur exacte pour " + where);
            }
        }

        [Test]
        public void Le_sol_sous_les_pieds_est_capture()
        {
            // THE case that volume clipping fixes. A 12 m platform seen from its
            // surface has its center behind and below the camera, so a center
            // test never copies it, while placing the photo WOULD carve the
            // framed piece away: the player would blow a hole in his own floor.
            // The clip captures the slab of ground that is actually in frame.
            Matrix4x4 anchorInverse = AnchorInverse(new Vector3(0f, 1.62f, 4f), 0f);
            Vector3 groundCenter = new Vector3(0f, -0.5f, 0f);
            PhotoCapture.CaptureCandidate ground = Box(groundCenter, new Vector3(12f, 1f, 8f), "platform");

            Vector3 centerInCamera = ToDesignCamera(anchorInverse, groundCenter);
            Assert.IsFalse(
                PhotoMath.PointInFrustum(centerInCamera, PhotoMath.PhotoFovDeg, PhotoMath.PhotoAspect,
                    PhotoCapture.CaptureNear, PhotoCapture.CaptureDepth),
                "le centre de la plateforme est bien hors cadre (l'ancien test le ratait)");

            List<PhotoProp> props = PhotoCapture.PropsFrom(Candidates(ground), anchorInverse);
            Assert.AreEqual(1, props.Count, "le sol cadre est capture malgre son centre hors champ");

            PhotoProp piece = props[0];
            Assert.AreEqual("platform", piece.Color, "c'est bien le sol");
            Assert.Less(piece.Size.x, 12.0f, "le sol est decoupe au cadre, pas copie en entier");
            Assert.AreEqual(1.0f, piece.Size.y, Tol, "l'epaisseur du sol est exacte, sans marge ajoutee");

            // The exact slab PRD 7.2 asks for, which the loose "< 12" above cannot
            // see. The frame is measured at the DEEPEST kept point, the far edge of
            // the 8 m deep platform, and the piece is centered on what it kept: the
            // depth range runs from that far edge to the near plane at 0.5 m, so the
            // center sits at -4.25 and the height stays the floor's own. A clip that
            // sampled the frame at the near edge instead, or that slid the piece off
            // the floor, would still satisfy "< 12" and would carve a hole the photo
            // no longer fills.
            Assert.AreEqual(2f * PhotoMath.HalfExtentAt(8f, PhotoMath.PhotoFovDeg), piece.Size.x, Tol,
                "la largeur gardee est celle du cadre au bord lointain du sol");
            Assert.AreEqual(-4.25f, piece.Pos.z, Tol,
                "le morceau est centre entre le plan proche et le bord lointain");
            Assert.AreEqual(-2.12f, piece.Pos.y, Tol, "le morceau reste a la hauteur du sol");

            Assert.Greater(-piece.Pos.z, 0.5f, "le morceau capture est devant la camera");
            Assert.IsFalse(piece.Loose, "un morceau de sol reste solidaire, il ne tombe pas");
        }

        [Test]
        public void Le_decoupage_au_cadre()
        {
            // The pure clip: a wall wider than the frame comes back narrowed to it.
            Vector3 center;
            Vector3 clipped;
            bool kept = PhotoCapture.ClipToFrustum(new Vector3(20f, 4f, 0.5f),
                InCameraAt(new Vector3(0f, 0f, -6f)), out center, out clipped);
            Assert.IsTrue(kept, "un mur cadre est capture");

            float half = PhotoMath.HalfExtentAt(6.0f, PhotoMath.PhotoFovDeg);
            Assert.Less(clipped.x, 20.0f, "le mur est retreci au cadre");
            Assert.GreaterOrEqual(clipped.x, half, "la largeur retenue est celle de la trame");
            Assert.LessOrEqual(clipped.x, half * 2.5f, "la largeur retenue est celle de la trame");

            // WHERE the frame is measured, which the band above is far too wide to
            // see. PRD 7.2 takes the half extent at the DEEPEST kept point: here the
            // back face of the wall, 6.25 m away (6 m plus half of its 0.5 m
            // thickness). Sampling it at the nearest kept point instead would look
            // like a tightening of "a photo never holds anything outside its own
            // borders", would shave real geometry off every straddling box, and
            // would still land inside the band above.
            Assert.AreEqual(2f * PhotoMath.HalfExtentAt(6.25f, PhotoMath.PhotoFovDeg), clipped.x, Tol,
                "la largeur est mesuree au point le plus profond garde");
            // Nothing else is touched: at that depth the frame is taller than the
            // 4 m wall, and the whole 0.5 m of thickness sits inside the depth range.
            Assert.AreEqual(4.0f, clipped.y, Tol, "la hauteur du mur tient dans le cadre, sans rognage");
            Assert.AreEqual(0.5f, clipped.z, Tol, "l'epaisseur du mur est exacte");
            AssertNear(center, new Vector3(0f, 0f, -6f), "le morceau garde le centre du mur");

            // Out of frame entirely: nothing at all. A refused clip must not leave a
            // plausible box behind it either: the Unity port answers through out
            // parameters, which the caller reads whatever the return value was. Each
            // refusal gets its own pair, because a stale piece left by the first
            // would be overwritten on entry to the second and go unseen.
            Vector3 behindCenter;
            Vector3 behindClipped;
            Assert.IsFalse(
                PhotoCapture.ClipToFrustum(new Vector3(1f, 1f, 1f),
                    InCameraAt(new Vector3(0f, 0f, 6f)), out behindCenter, out behindClipped),
                "derriere la camera : rien a capturer");
            AssertNear(behindClipped, Vector3.zero, "un refus ne rend aucun volume");
            AssertNear(behindCenter, Vector3.zero, "un refus ne rend aucun centre");

            Vector3 farCenter;
            Vector3 farClipped;
            Assert.IsFalse(
                PhotoCapture.ClipToFrustum(new Vector3(1f, 1f, 1f),
                    InCameraAt(new Vector3(0f, 0f, -30f)), out farCenter, out farClipped),
                "au dela de la portee : rien a capturer");
            AssertNear(farClipped, Vector3.zero, "un refus ne rend aucun volume");
            AssertNear(farCenter, Vector3.zero, "un refus ne rend aucun centre");
        }

        [Test]
        public void Le_lacet_est_relatif()
        {
            // Camera looking +x (yaw -90): a box 4 m along +x is straight ahead.
            Matrix4x4 anchorInverse = AnchorInverse(new Vector3(0f, 1.62f, 0f), -Mathf.PI * 0.5f);
            List<PhotoProp> props = PhotoCapture.PropsFrom(
                Candidates(Box(new Vector3(4f, 1.62f, 0f), new Vector3(1f, 1f, 1f), "erasable")),
                anchorInverse);

            Assert.AreEqual(1, props.Count, "la boite face a la camera tournee est capturee");
            Assert.AreEqual(-4.0f, props[0].Pos.z, Tol, "devant la camera quelle que soit l'orientation");
            Assert.AreEqual(0.0f, props[0].Pos.x, Tol, "centree dans le cadre");
            AssertNear(props[0].Size, new Vector3(1f, 1f, 1f),
                "taille conservee quelle que soit l'orientation");
        }

        [Test]
        public void La_capture_d_une_pile()
        {
            Matrix4x4 anchorInverse = AnchorInverse(new Vector3(0f, 1.62f, 0f), 0f);
            List<PhotoProp> props = PhotoCapture.PropsFrom(
                Candidates(BatteryAt(new Vector3(0.5f, 0.0f, -3f))), anchorInverse);

            Assert.AreEqual(1, props.Count, "la pile cadree est capturee");
            Assert.AreEqual("battery", props[0].Kind, "elle reste une pile (donc dupliquee a la pose)");
            Assert.AreEqual(-1.62f, props[0].Pos.y, Tol, "position de base conservee");
        }

        [Test]
        public void Trop_pres_est_ignore()
        {
            // The near plane (0.5) keeps the shot from capturing what the player
            // is standing inside of.
            Matrix4x4 anchorInverse = AnchorInverse(new Vector3(0f, 1.62f, 0f), 0f);
            List<PhotoProp> props = PhotoCapture.PropsFrom(
                Candidates(Box(new Vector3(0f, 1.62f, -0.2f), new Vector3(0.3f, 0.3f, 0.3f), "erasable")),
                anchorInverse);

            Assert.AreEqual(0, props.Count, "trop pres : hors cliche");
        }

        [Test]
        public void Le_registre_dynamique()
        {
            PhotoProp battery = new PhotoProp();
            battery.Kind = "battery";
            battery.Pos = new Vector3(0f, -1f, -3f);
            battery.Size = Vector3.zero;
            battery.Color = "battery";

            PhotoDef def = new PhotoDef();
            def.Title = "Cliche";
            def.Props = new List<PhotoProp> { battery };
            def.Backdrop = null;
            def.EraseDepth = 12f;

            string id = PhotoDefs.RegisterDynamic(def);
            Assert.IsTrue(id.StartsWith("cliche_"), "id dynamique nomme cliche_N");
            Assert.IsNotNull(PhotoDefs.GetDef(id), "le cliche se lit comme une photo du catalogue");
            Assert.AreEqual(1, PhotoDefs.BatteryCount(id), "le compte de piles fonctionne sur un cliche");

            // The static catalog must be loadable for this check to mean
            // anything: an empty catalog would contain no id at all and the
            // assertion below would pass without testing the separation.
            string[] catalog = PhotoDefs.AllIds();
            Assert.Greater(catalog.Length, 0, "le catalogue statique est bien charge");
            bool inCatalog = false;
            for (int i = 0; i < catalog.Length; i++)
            {
                if (catalog[i] == id)
                {
                    inCatalog = true;
                }
            }
            Assert.IsFalse(inCatalog, "le catalogue statique n'est pas pollue");

            PhotoDefs.ClearDynamic();
            Assert.IsNull(PhotoDefs.GetDef(id), "ClearDynamic purge les cliches");
        }

        [Test]
        public void La_regle_de_l_objet_libre()
        {
            // A captured box is loose (it falls when placed) only when the
            // ORIGINAL object is small on EVERY axis: crates fall, walls and
            // grounds do not, whatever size the clipped piece ends up being.
            Matrix4x4 anchorInverse = AnchorInverse(new Vector3(0f, 1.62f, 0f), 0f);
            List<PhotoCapture.CaptureCandidate> candidates = Candidates(
                Box(new Vector3(0f, 1.62f, -3f), new Vector3(1.5f, 1.5f, 1.5f), "wood"),
                Box(new Vector3(0f, 1.62f, -4f), new Vector3(1.7f, 1.0f, 1.0f), "wood"),
                Box(new Vector3(0f, 1.62f, -5f), new Vector3(1.0f, 1.0f, 4.0f), "wood"),
                Box(new Vector3(0f, 1.62f, -6f), new Vector3(1.0f, 3.5f, 0.6f), "erasable"),
                BatteryAt(new Vector3(0f, 1.0f, -7f)));

            List<PhotoProp> props = PhotoCapture.PropsFrom(candidates, anchorInverse);
            Assert.AreEqual(5, props.Count, "les cinq candidats sont cadres");
            Assert.IsTrue(props[0].Loose, "cube de 1.5 m : objet libre");
            Assert.IsFalse(props[1].Loose, "1.7 m sur un axe : solidaire");
            Assert.IsFalse(props[2].Loose, "planche de 4 m : solidaire");
            Assert.IsFalse(props[3].Loose, "pan de mur de 3.5 m de haut : solidaire");
            Assert.IsFalse(props[4].Loose, "une pile n'a pas de cle loose (elle est toujours physique)");
            Assert.AreEqual(1.6f, PhotoCapture.LooseMaxExtent, Tol, "seuil d'objet libre a 1.6 m");
        }

        [Test]
        public void Le_plafond_de_props()
        {
            // Forty framed boxes, capped at 32, closest kept first: a shot of a
            // dense level stays a placeable photo instead of a scene dump.
            Matrix4x4 anchorInverse = AnchorInverse(new Vector3(0f, 1.62f, 0f), 0f);
            List<PhotoCapture.CaptureCandidate> candidates = new List<PhotoCapture.CaptureCandidate>();
            for (int i = 0; i < 40; i++)
            {
                candidates.Add(Box(new Vector3(0f, 1.62f, -1.0f - i * 0.25f),
                    new Vector3(0.5f, 0.5f, 0.5f), "stone"));
            }

            List<PhotoProp> props = PhotoCapture.PropsFrom(candidates, anchorInverse);
            Assert.AreEqual(PhotoCapture.MaxProps, props.Count, "plafond de 32 props");
            for (int i = 1; i < props.Count; i++)
            {
                Assert.GreaterOrEqual(-props[i].Pos.z, -props[i - 1].Pos.z,
                    "props tries par profondeur croissante");
            }
            Assert.Less(-props[0].Pos.z, -props[props.Count - 1].Pos.z,
                "les plus proches sont gardes, les lointains coupes");

            // WHICH props the cap drops when depths tie. The original sorted on
            // depth alone, and GDScript's sort_custom happened to leave small
            // equal runs alone; List.Sort is an introsort and shuffles equal keys
            // outright, so the port breaks ties on the input rank to keep a shot
            // reproducible (the same frame photographed twice must give the same
            // photo, or a rewind replays a different picture). Forty boxes at ONE
            // depth, told apart by their size, pin that: the fully framed branch
            // returns the box's own center, so every depth here is identical to
            // the bit.
            List<PhotoCapture.CaptureCandidate> tied = new List<PhotoCapture.CaptureCandidate>();
            for (int i = 0; i < 40; i++)
            {
                float side = 0.3f + i * 0.01f;
                tied.Add(Box(new Vector3(0f, 1.62f, -4f), new Vector3(side, side, side), "stone"));
            }

            List<PhotoProp> tiedProps = PhotoCapture.PropsFrom(tied, anchorInverse);
            Assert.AreEqual(PhotoCapture.MaxProps, tiedProps.Count, "plafond de 32 props a profondeur egale");
            for (int i = 0; i < tiedProps.Count; i++)
            {
                Assert.AreEqual(-4.0f, tiedProps[i].Pos.z, Tol, "les quarante boites sont a la meme profondeur");
                Assert.AreEqual(0.3f + i * 0.01f, tiedProps[i].Size.x, Tol,
                    "a profondeur egale, l'ordre d'entree decide : le meme cliche deux fois donne la meme photo");
            }
        }

        [Test]
        public void Toutes_les_familles_sont_capturees()
        {
            // The film sees both families of subject: blocks of every color
            // (permanent platforms as well as lavender ones) and batteries.
            // Cages are NOT a family any more: bars are a lattice the lens goes
            // through, so what the film keeps of a cage is whatever stands
            // behind its bars.
            Matrix4x4 anchorInverse = AnchorInverse(new Vector3(0f, 1.62f, 0f), 0f);
            List<PhotoCapture.CaptureCandidate> candidates = Candidates(
                Box(new Vector3(0f, -1f, -8f), new Vector3(6f, 1f, 6f), "platform"),
                Box(new Vector3(1f, 1f, -4f), new Vector3(1.2f, 1.2f, 1.2f), "erasable"),
                BatteryAt(new Vector3(0.5f, 0f, -3f)),
                Box(new Vector3(0f, 1f, 6f), new Vector3(1f, 1f, 1f), "wood"));

            List<PhotoProp> props = PhotoCapture.PropsFrom(candidates, anchorInverse);
            Assert.AreEqual(3, props.Count, "trois sujets cadres, le bloc derriere la camera exclu");

            List<string> colors = ColorsOf(props);
            Assert.Contains("platform", colors, "la plateforme non lavande est capturee");
            Assert.Contains("erasable", colors, "le bloc lavande est capture");
            Assert.IsFalse(colors.Contains("wood"), "ce qui est derriere la camera reste hors du cliche");

            List<string> kinds = KindsOf(props);
            Assert.Contains("battery", kinds, "la pile est capturee comme une pile");
            Assert.AreEqual(-3.0f, props[0].Pos.z, Tol, "le sujet le plus proche vient en tete");
        }

        [Test]
        public void Une_cage_n_est_pas_un_genre_capturable()
        {
            // A caged battery must come out of the film as a battery and nothing
            // else. If a cage were copied as a solid box, the copy would
            // materialize AROUND the copied battery and seal it in: the one
            // puzzle a steel cage exists for would be unsolvable. Feeding a
            // cage-shaped candidate now yields a clipped box like any other
            // volume, and the scene never produces one (the group walk in
            // Capture does not read cages at all: see the smoke probe).
            Matrix4x4 anchorInverse = AnchorInverse(new Vector3(0f, 1.62f, 0f), 0f);
            List<PhotoProp> props = PhotoCapture.PropsFrom(
                Candidates(BatteryAt(new Vector3(0f, 0f, -5f))), anchorInverse);

            Assert.AreEqual(1, props.Count, "seule la pile en cage est sur la pellicule");
            Assert.AreEqual("battery", props[0].Kind, "et elle en sort comme une pile, libre");
        }

        [Test]
        public void Un_cliche_vide_reste_valide()
        {
            // Framing nothing but the sky is not a failure: the shot is an empty
            // photo of sky, and placed it pierces the world.
            //
            // An EditMode test has no scene, so the group registry Capture walks
            // is empty. That emptiness is asserted first, or this case would be
            // reading a shot of an unknown world and calling it a shot of sky.
            Assert.AreEqual(0, Groups.Count(Groups.Photographable),
                "aucun bloc enregistre : le cliche est bien un cliche de ciel");
            Assert.AreEqual(0, Groups.Count(Groups.CopyableBattery),
                "aucune pile enregistree : le cliche est bien un cliche de ciel");

            PhotoDef def = PhotoCapture.Capture(AnchorInverse(new Vector3(0f, 1.62f, 0f), 0f));
            Assert.IsNotNull(def, "un cliche vide reste une definition valide");
            Assert.IsFalse(string.IsNullOrEmpty(def.Title), "le cliche vide a un titre");
            Assert.IsNotNull(def.Props, "un cliche porte toujours une liste de props");
            Assert.AreEqual(0, def.Props.Count, "aucun prop sur le cliche du ciel");

            Assert.IsNotNull(def.Backdrop, "le cliche du ciel porte un fond");
            Assert.AreEqual(36.0f, def.Backdrop.Depth, Tol, "fond peint loin derriere, a 36 m");
            Assert.AreEqual(PhotoCapture.CaptureDepth, def.EraseDepth, Tol,
                "le cliche efface juste ce qu'il a capture");
            Assert.Greater(def.Backdrop.Depth, def.EraseDepth * 2.5f,
                "le ciel du cliche est un lointain, pas un mur au bout du bras");
            Assert.IsTrue(Palette.Has(def.Backdrop.Top), "couleur haute du fond connue");
            Assert.IsTrue(Palette.Has(def.Backdrop.Bottom), "couleur basse du fond connue");
        }
    }
}
