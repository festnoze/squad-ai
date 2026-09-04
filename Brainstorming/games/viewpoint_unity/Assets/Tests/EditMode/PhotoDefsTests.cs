using System;
using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;

namespace Viewpoint.Tests
{
    /// <summary>
    /// Validity of the photo catalog and coherence of the computed thumbnails
    /// (port of the original tests/test_photo_defs.gd, PRD sections 6.1 to 6.3,
    /// 6.7 and 6.9).
    ///
    /// The catalog is data, and the data is the contract: every number checked
    /// here is one a puzzle depends on. A photo whose backdrop capped its own
    /// carve, or a door whose wall left a gap, would still load and still look
    /// right, and would only show up as a level the player walks straight
    /// through.
    ///
    /// The assertion messages are the original's, in French, on purpose: they
    /// are the readable record of what broke, and the Godot run and the Unity
    /// run must report a break in the same words.
    /// </summary>
    public sealed class PhotoDefsTests
    {
        /// The authored prop kinds of PRD 6.1. Anything else is a data bug.
        static readonly string[] KnownKinds =
        {
            "box", "cylinder", "battery", "bridge", "stairs", "arch", "photo"
        };

        /// What an expansion may yield (PRD 6.2): never a compound kind.
        static readonly string[] ElementaryKinds =
        {
            "box", "cylinder", "battery", "photo_item"
        };

        /// <summary>
        /// Eye height of the player (PlayerController.EyeHeight). Photo space has
        /// its origin at the eye, so a prop's height above the FEET is
        /// <c>EyeHeight + center.y</c>: that is the number the jump budget of
        /// docs/LEVELS_V2.md section 2 is expressed in.
        /// </summary>
        const float EyeHeight = 1.62f;

        [SetUp]
        public void SetUp()
        {
            // Photos taken in game share the GetDef lookup with the static
            // catalog, so a leftover cliche_N from another suite must not be
            // visible from here. AllIds is static-only either way; this keeps the
            // unknown-id case honest as well.
            PhotoDefs.ClearDynamic();
        }

        [TearDown]
        public void TearDown()
        {
            // Thumbnails registers throwaway definitions to isolate the painted
            // content from the painted backdrop; they must not outlive the case,
            // and neither must their cached textures.
            PhotoDefs.ClearDynamic();
        }

        // ------------------------------------------------------------- catalog

        [Test]
        public void Catalog()
        {
            string[] ids = PhotoDefs.AllIds();
            Assert.AreEqual(8, ids.Length, "huit photos au catalogue");
            foreach (string id in ids)
            {
                PhotoDef def = PhotoDefs.GetDef(id);
                Assert.IsNotNull(def, "definition presente pour " + id);
                Assert.IsFalse(string.IsNullOrEmpty(def.Title), id + " : titre non vide");
                Assert.IsTrue(def.Props.Count > 0, id + " : au moins un prop");
                Assert.IsTrue(def.EraseDepth > 0f, id + " : profondeur d'effacement positive");
            }
            // The original returns an empty dictionary, the port returns null:
            // the same statement, that nothing is known about this id.
            Assert.IsNull(PhotoDefs.GetDef("inexistante"), "id inconnu : definition vide");
        }

        [Test]
        public void PropsValid()
        {
            foreach (string id in PhotoDefs.AllIds())
            {
                PhotoDef def = PhotoDefs.GetDef(id);
                foreach (PhotoProp prop in def.Props)
                {
                    Assert.IsTrue(Array.IndexOf(KnownKinds, prop.Kind) >= 0,
                        id + " : genre de prop connu (" + prop.Kind + ")");
                    Assert.IsTrue(Palette.Has(prop.Color), id + " : couleur connue");
                    // DESIGN space, -z forward: a prop behind the lens would be
                    // invisible in the picture and would still be built.
                    Assert.IsTrue(prop.Pos.z < 0f,
                        id + " : prop devant la camera (z = " + prop.Pos.z + ")");
                    if (prop.Kind == "photo")
                    {
                        Assert.IsNotNull(PhotoDefs.GetDef(prop.Id),
                            id + " : photo imbriquee " + prop.Id + " au catalogue");
                    }
                }
            }
        }

        [Test]
        public void BackdropUniversal()
        {
            // v4: a photo is ALWAYS the 2D picture of a 3D space, so every def
            // paints a backdrop, and it stands far behind the carve rather than
            // capping it.
            foreach (string id in PhotoDefs.AllIds())
            {
                PhotoDef def = PhotoDefs.GetDef(id);
                PhotoBackdrop backdrop = def.Backdrop;

                // One documented exception: a photo whose own geometry paves the
                // frame is sealed by it. The door is the case, and it MUST be: a
                // backdrop is a solid wall, so one behind the opening would plug
                // the doorway.
                if (def.Seal == "content")
                {
                    Assert.IsNull(backdrop, id + " : scelle par son contenu, donc sans fond solide");
                    continue;
                }
                Assert.IsNotNull(backdrop, id + " : fond peint obligatoire");
                Assert.IsTrue(backdrop.Depth > 0f, id + " : backdrop a distance positive");
                Assert.IsTrue(Palette.Has(backdrop.Top), id + " : couleur haute du backdrop connue");
                Assert.IsTrue(Palette.Has(backdrop.Bottom), id + " : couleur basse du backdrop connue");

                // v6.1: the backdrop is no longer the lid of the carve, it is the
                // distant view of the picture. It stands VERY far behind the erase
                // plane, or we fall back on the defect that motivated the change:
                // crossing a chasm by walking inside a wall of sky.
                Assert.IsTrue(backdrop.Depth > def.EraseDepth * 2.5f,
                    id + " : le fond peint est un lointain, pas un couvercle ("
                        + backdrop.Depth.ToString("0.0") + " m pour une decoupe de "
                        + def.EraseDepth.ToString("0.0") + " m)");
            }
        }

        [Test]
        public void NoPhotoPatchesTheGround()
        {
            // The ground language (PRD 5.1): grey ground is PERMANENT, a photo
            // placed over it is added to it. So no photo carries a slab of grey
            // ground: a bridge photo lays a bridge, it does not repave the floor.
            // Patching would only stack a second floor on the first.
            foreach (string id in PhotoDefs.AllIds())
            {
                foreach (PhotoProp prop in PhotoDefs.GetDef(id).Props)
                {
                    Assert.AreNotEqual("platform", prop.Color,
                        id + " : aucune photo ne rapiece le sol permanent");
                }
            }
        }

        // ----------------------------------------------------------- expansion

        [Test]
        public void LooseProps()
        {
            // Loose box props materialize as falling rigid bodies. The other props
            // hold exact positions the puzzles depend on and must stay static.
            PhotoProp crate = PhotoDefs.GetDef("caisse").Props[0];
            Assert.AreEqual("box", crate.Kind, "la caisse est une boite");
            Assert.IsTrue(crate.Loose, "la caisse est un objet libre : elle tombe");

            foreach (string id in new[] { "pile", "coffret" })
            {
                PhotoProp socle = PhotoDefs.GetDef(id).Props[0];
                Assert.IsFalse(socle.Loose, id + " : le socle reste statique");
            }
            foreach (string id in new[] { "console", "corniche" })
            {
                PhotoProp slab = PhotoDefs.GetDef(id).Props[0];
                Assert.IsFalse(slab.Loose, id + " : la dalle reste statique");
            }

            // The expansion carries the key over to the primitives actually built.
            List<Primitive> prims = PhotoDefs.ExpandProp(crate);
            Assert.AreEqual(1, prims.Count, "la caisse s'etend en une primitive");
            Assert.IsTrue(prims[0].Loose, "l'expansion propage la cle loose");

            PhotoProp fixedBox = new PhotoProp
            {
                Kind = "box",
                Pos = new Vector3(0f, -1f, -3f),
                Size = new Vector3(2f, 0.3f, 2f),
                Color = "stone"
            };
            List<Primitive> fixedPrims = PhotoDefs.ExpandProp(fixedBox);
            Assert.AreEqual(1, fixedPrims.Count, "une boite s'etend en une primitive");
            Assert.IsFalse(fixedPrims[0].Loose, "une boite non libre n'herite d'aucune cle loose");

            // A flight of stairs must never fall, whatever the data claims: the
            // steps are the only way up and a physics body would slide off.
            List<Primitive> stairs = PhotoDefs.ExpandProp(new PhotoProp
            {
                Kind = "stairs",
                Pos = new Vector3(0f, -1.6f, -1.2f),
                Size = new Vector3(2.2f, 4.6f, 7.0f),
                Color = "stone",
                Loose = true
            });
            Assert.AreEqual(8, stairs.Count, "l'escalier libre s'etend quand meme en huit marches");
            foreach (Primitive step in stairs)
            {
                Assert.IsFalse(step.Loose, "seules les boites propagent loose, pas les marches");
            }
        }

        [Test]
        public void Expansion()
        {
            foreach (string id in PhotoDefs.AllIds())
            {
                List<Primitive> prims = PhotoDefs.ExpandProps(PhotoDefs.GetDef(id));
                Assert.IsTrue(prims.Count > 0, id + " : expansion non vide");
                foreach (Primitive prim in prims)
                {
                    Assert.IsTrue(Array.IndexOf(ElementaryKinds, prim.Kind) >= 0,
                        id + " : primitive elementaire");
                    Vector3 size = prim.Size;
                    Assert.IsTrue(size.x > 0f && size.y > 0f && size.z > 0f,
                        id + " : primitive de taille positive");
                    Assert.IsTrue(Palette.Has(prim.Color), id + " : couleur de primitive connue");
                }
            }

            List<Primitive> stairs = PhotoDefs.ExpandProp(new PhotoProp
            {
                Kind = "stairs",
                Pos = new Vector3(0f, -1.6f, -1.2f),
                Size = new Vector3(2.2f, 4.6f, 7.0f),
                Color = "stone"
            });
            Assert.AreEqual(8, stairs.Count, "l'escalier fait huit marches");
            for (var i = 1; i < stairs.Count; i++)
            {
                // Each step is a pillar from the ground up to its own top, so the
                // flight is solid from below: the heights grow, and every step
                // sits further from the lens than the one before it.
                Assert.IsTrue(stairs[i].Size.y > stairs[i - 1].Size.y,
                    "marche " + i + " plus haute que la precedente");
                Assert.IsTrue(stairs[i].Center.z < stairs[i - 1].Center.z,
                    "marche " + i + " plus loin que la precedente");
            }
            Primitive top = stairs[stairs.Count - 1];
            Near(top.Center.y + top.Size.y * 0.5f, -1.6f + 4.6f, 0.001f,
                "le sommet atteint la hauteur totale");
        }

        // -------------------------------------------------------- derived data

        [Test]
        public void BatteryCounts()
        {
            Assert.AreEqual(1, PhotoDefs.BatteryCount("pile"), "la photo Pile contient une pile");
            Assert.AreEqual(0, PhotoDefs.BatteryCount("passerelle"), "la Passerelle n'en contient pas");
            Assert.AreEqual(0, PhotoDefs.BatteryCount("escalier"), "l'Escalier n'en contient pas");
            Assert.AreEqual(0, PhotoDefs.BatteryCount("porte"), "la Porte n'en contient pas");
            Assert.AreEqual(0, PhotoDefs.BatteryCount("coffret"), "le Coffret n'a pas de pile directe");
            Assert.AreEqual(1, PhotoDefs.BatteryCountRecursive("coffret"),
                "le Coffret vaut une pile via la photo Pile");
            Assert.AreEqual(1, PhotoDefs.BatteryCountRecursive("pile"),
                "compte recursif stable sur une photo simple");
            // The visited guard: feeding an already-visited id returns zero
            // instead of looping forever, which is what protects a hypothetical
            // cyclic catalog.
            Assert.AreEqual(0, PhotoDefs.BatteryCountRecursive("pile", new HashSet<string> { "pile" }),
                "garde anti-cycle active");
        }

        [Test]
        public void RotationGeometry()
        {
            // The design contract of the flips (docs/LEVELS_V2.md section 2): a
            // console slab is boardable at roll 0 (top under the 1.5 jump) and NOT
            // boardable from its own placement spot at roll 180.
            Primitive slab = PhotoDefs.ExpandProps(PhotoDefs.GetDef("console"))[0];
            float topRoll0 = EyeHeight + slab.Center.y + slab.Size.y * 0.5f;
            Between(topRoll0, 0.6f, 1.5f, "console 0 deg sautable depuis le sol");

            // A roll of 180 mirrors the slab about the view axis, so its offset
            // below the eye becomes the same offset above it.
            float topRoll180 = EyeHeight - slab.Center.y + slab.Size.y * 0.5f;
            Assert.IsTrue(topRoll180 > 1.5f, "console 180 deg exige un appui intermediaire");
            Assert.IsTrue(topRoll180 < topRoll0 + 1.5f,
                "console 180 deg atteignable depuis la console 0 deg");

            Primitive ledge = PhotoDefs.ExpandProps(PhotoDefs.GetDef("corniche"))[0];
            Assert.IsTrue(Mathf.Abs(ledge.Center.x) > 0.5f,
                "corniche decalee lateralement : la rotation change le cote");
        }

        // ------------------------------------------------------------ the door

        [Test]
        public void PorteSeal()
        {
            // The airtightness rule (PRD 6.7): a photo with a seal wall only
            // erases up to the seal plane, and the seal covers the whole frustum
            // cross-section there. Otherwise the carved hole is wider than the
            // placed wall and the player slips through the gap (the reported
            // "interstice" bug).
            PhotoDef def = PhotoDefs.GetDef("porte");
            Assert.IsNotNull(def, "la porte est au catalogue");

            const float wallDepth = 6f;
            // The carve runs a little past the wall so the ground continues behind
            // the doorway, but not so far that it eats what the wall does not cover.
            Between(def.EraseDepth, wallDepth, wallDepth + 1.6f,
                "la porte decoupe juste ce qu'il faut derriere son mur");
            Assert.AreEqual("content", def.Seal,
                "la porte est scellee par son mur, pas par un fond solide");
            Assert.IsFalse(def.HasBackdrop, "aucun fond solide ne bouche l'ouverture");

            float half = PhotoMath.HalfExtentAt(wallDepth, PhotoMath.PhotoFovDeg);
            Between(half, 2.7f, 2.8f, "demi-trame du frustum a 6 m connue");

            // Sample the frustum cross-section at the seal plane: every point must
            // be either inside the door opening or covered by a wall panel.
            List<PhotoProp> walls = new List<PhotoProp>();
            foreach (PhotoProp prop in def.Props)
            {
                if (prop.Color == "frame")
                {
                    walls.Add(prop);
                }
            }
            // Without this, a door that had lost all its panels would still fail
            // the sweep below, but it would fail for the wrong reason and the
            // message would not say what actually happened.
            Assert.IsTrue(walls.Count > 0, "la porte porte des panneaux 'frame'");

            var uncovered = 0;
            const int steps = 21;
            for (var ix = 0; ix < steps; ix++)
            {
                for (var iy = 0; iy < steps; iy++)
                {
                    float x = ((float)ix / (steps - 1) * 2f - 1f) * half;
                    float y = ((float)iy / (steps - 1) * 2f - 1f) * half;
                    bool inOpening = Mathf.Abs(x) < 0.8f && y < 0.98f;
                    if (inOpening)
                    {
                        continue;
                    }
                    var covered = false;
                    foreach (PhotoProp wall in walls)
                    {
                        Vector3 pos = wall.Pos;
                        Vector3 size = wall.Size;
                        if (Mathf.Abs(x - pos.x) <= size.x * 0.5f + 0.02f
                            && Mathf.Abs(y - pos.y) <= size.y * 0.5f + 0.02f)
                        {
                            covered = true;
                            break;
                        }
                    }
                    if (!covered)
                    {
                        uncovered++;
                    }
                }
            }
            Assert.AreEqual(0, uncovered, "le mur de la porte pave toute la trame hors ouverture");
        }

        // ---------------------------------------------------------- thumbnails

        [Test]
        public void Thumbnails()
        {
            // The picture geometry of PRD 6.9, written out as literals rather
            // than read back from PhotoDefs: the two pixels sampled below only
            // mean anything while (2, 2) sits in the polaroid border and
            // (128, 110) sits inside the picture, and a retuned constant would
            // otherwise move them without failing anything.
            Assert.AreEqual(256, PhotoDefs.ThumbSize, "vignette de 256 px de cote");
            Assert.AreEqual(24, PhotoDefs.ThumbInnerX, "bord gauche du polaroid : 24 px");
            Assert.AreEqual(16, PhotoDefs.ThumbInnerY, "bord haut du polaroid : 16 px");
            Assert.AreEqual(208, PhotoDefs.ThumbInnerSize, "image interieure de 208 px de cote");

            foreach (string id in PhotoDefs.AllIds())
            {
                Texture2D texture = PhotoDefs.Thumbnail(id);
                Assert.IsNotNull(texture, id + " : vignette produite");
                Assert.AreEqual(256, texture.width, id + " : vignette de 256 px de large");
                Assert.AreEqual(256, texture.height, id + " : vignette de 256 px de haut");

                // The frame corner must differ from the picture center: the
                // drawing actually painted something inside the polaroid.
                Color corner = ImagePixel(texture, 2, 2);
                Color center = ImagePixel(texture, 128, 110);
                Assert.IsTrue(MaxChannelDelta(corner, center) > 0.01f, id + " : image non uniforme");

                // The two pixels above only prove the backdrop gradient was
                // painted: a build that dropped every primitive would still pass
                // them. This says the CONTENT is drawn, by repainting the same
                // definition stripped of its props: same backdrop, same
                // gradient, so whatever differs is this photo's own geometry.
                Assert.IsTrue(ContentIsPainted(id, texture),
                    id + " : le contenu de la photo est dessine, pas seulement le fond");
            }
            Assert.AreSame(PhotoDefs.Thumbnail("pile"), PhotoDefs.Thumbnail("pile"),
                "vignette mise en cache");
        }

        // --------------------------------------------------------------- tools

        /// <summary>
        /// A pixel addressed in IMAGE space, row 0 at the TOP, the way the
        /// original reads its Image. A Unity Texture2D stores row 0 at the
        /// BOTTOM, so the row index is flipped here, exactly once (PRD 6.9).
        /// The flip is taken from the texture itself, not from a constant, so a
        /// wrong size shows up as a wrong size and never as a wrong pixel.
        /// </summary>
        static Color ImagePixel(Texture2D texture, int x, int y)
        {
            return texture.GetPixel(x, texture.height - 1 - y);
        }

        /// <summary>
        /// True when the picture of <paramref name="id"/> differs anywhere from
        /// the picture of the same definition with no props at all.
        ///
        /// The twin carries the same backdrop, so both pictures get the exact
        /// same gradient, and the primitives are clipped to the picture area, so
        /// both get the same polaroid border: any difference in the buffer is the
        /// photo's own content. The twin is registered as a dynamic photo, which
        /// TearDown drops along with its cached texture.
        /// </summary>
        static bool ContentIsPainted(string id, Texture2D painted)
        {
            PhotoDef def = PhotoDefs.GetDef(id);
            PhotoDef bare = new PhotoDef();
            bare.Title = def.Title;
            bare.Hint = def.Hint;
            bare.Seal = def.Seal;
            bare.EraseDepth = def.EraseDepth;
            bare.Backdrop = def.Backdrop;
            bare.Props = new List<PhotoProp>();

            Texture2D empty = PhotoDefs.Thumbnail(PhotoDefs.RegisterDynamic(bare));
            Color32[] withContent = painted.GetPixels32();
            Color32[] withoutContent = empty.GetPixels32();
            if (withContent.Length != withoutContent.Length)
            {
                return true;
            }
            for (var i = 0; i < withContent.Length; i++)
            {
                Color32 a = withContent[i];
                Color32 b = withoutContent[i];
                if (a.r != b.r || a.g != b.g || a.b != b.b || a.a != b.a)
                {
                    return true;
                }
            }
            return false;
        }

        /// Largest per-channel difference, alpha ignored: both pixels are opaque.
        static float MaxChannelDelta(Color a, Color b)
        {
            return Mathf.Max(Mathf.Abs(a.r - b.r),
                Mathf.Max(Mathf.Abs(a.g - b.g), Mathf.Abs(a.b - b.b)));
        }

        /// <summary>
        /// The original harness's <c>near</c>: absolute tolerance, and the same
        /// failure message shape, so a break reads like the Godot run.
        /// </summary>
        static void Near(float actual, float expected, float tolerance, string message)
        {
            Assert.IsTrue(Mathf.Abs(actual - expected) <= tolerance,
                message + " (attendu " + expected + " +/- " + tolerance + ", obtenu " + actual + ")");
        }

        /// The original harness's <c>between</c>: both bounds included.
        static void Between(float actual, float low, float high, string message)
        {
            Assert.IsTrue(actual >= low && actual <= high,
                message + " (attendu dans [" + low + ", " + high + "], obtenu " + actual + ")");
        }
    }
}
