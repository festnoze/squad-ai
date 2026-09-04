using UnityEngine;
using UnityEngine.UI;

namespace Viewpoint
{
    /// <summary>
    /// The little tilted polaroid of the held photo, bottom right of the HUD
    /// (PRD section 12.3).
    ///
    /// It is drawn by hand rather than by tilting a RectTransform, and that is
    /// not stubbornness. A Screen Space Overlay canvas projects orthographically,
    /// so a 3D-rotated RectTransform under one comes out sheared with no
    /// perspective at all: the card would read as a parallelogram, not as a
    /// photo lying back. Rendering it through a Screen Space Camera canvas would
    /// buy real perspective at the price of a second canvas and a camera that
    /// has to agree with the first about scaling. Projecting a subdivided quad
    /// costs thirty lines and no coupling, which is also exactly what the
    /// original does (a Godot Control can only spin on Z, so it hand projected
    /// the same grid).
    ///
    /// The subdivision is the point: a single textured quad maps its texture
    /// AFFINELY, which shears the picture. A 6 x 6 grid of quads, each projected
    /// independently, keeps the perspective honest.
    /// </summary>
    public static class PhotoCardGeometry
    {
        /// <summary>Roll, degrees. Positive leans the top of the card right.</summary>
        public const float TiltZ = 9f;

        /// <summary>Pitch, degrees. Positive pushes the top of the card away.</summary>
        public const float TiltX = 26f;

        /// <summary>Side of the drawn picture in pixels, before the tilt shrinks it.</summary>
        public const float CardSize = 62f;

        /// <summary>Pinhole distance in card widths. Smaller means more perspective.</summary>
        public const float ViewDistance = 2.4f;

        /// <summary>Cells per side. One quad would shear the texture (see above).</summary>
        public const int Grid = 6;

        /// <summary>
        /// Shadow offset in pixels. The original used (3, 4) with a y-down
        /// screen, so in a y-up canvas the vertical component flips.
        /// </summary>
        public static readonly Vector2 ShadowOffset = new Vector2(3f, -4f);

        public static readonly Color ShadowColor = new Color(0.05f, 0.06f, 0.10f, 0.35f);

        /// <summary>
        /// Projects a point of the card, given as a uv with (0, 0) at the TOP
        /// LEFT, to a local canvas offset from the card's centre.
        ///
        /// The two rotations are written out as explicit matrices instead of
        /// Quaternion.AngleAxis calls, because the sign of a Unity quaternion
        /// rotation is exactly the kind of convention this port keeps getting
        /// bitten by. Here the behaviour is readable from the algebra:
        ///   roll  maps (0, 1, 0) to (sin rz, cos rz, 0)     - top leans right
        ///   pitch maps (0, 1, 0) to (0, cos rx, -sin rx)    - top goes away
        /// The eye sits at the origin looking down -z and the card is pushed out
        /// to z = -ViewDistance, so a point's screen scale is focal / -p.z.
        /// </summary>
        public static Vector2 Project(Vector2 uv)
        {
            float rz = TiltZ * Mathf.Deg2Rad;
            float rx = TiltX * Mathf.Deg2Rad;
            float cz = Mathf.Cos(rz);
            float sz = Mathf.Sin(rz);
            float cx = Mathf.Cos(rx);
            float sx = Mathf.Sin(rx);

            // Card space: x right, y up, origin at the centre, side 1.
            float x = uv.x - 0.5f;
            float y = 0.5f - uv.y;
            const float z = 0f;

            // Pitch about x, then roll about z.
            float px = x;
            float py = y * cx + z * sx;
            float pz = -y * sx + z * cx;

            float qx = px * cz + py * sz;
            float qy = -px * sz + py * cz;
            float qz = pz;

            qz -= ViewDistance;

            // Focal chosen so an untilted card spans exactly CardSize pixels.
            float focal = ViewDistance * CardSize;
            float scale = focal / -qz;
            return new Vector2(qx * scale, qy * scale);
        }

        /// <summary>The four projected corners, clockwise from the top left.</summary>
        public static void Corners(Vector2[] into)
        {
            into[0] = Project(new Vector2(0f, 0f));
            into[1] = Project(new Vector2(1f, 0f));
            into[2] = Project(new Vector2(1f, 1f));
            into[3] = Project(new Vector2(0f, 1f));
        }
    }

    /// <summary>
    /// The card itself: the photo picture, projected through
    /// <see cref="PhotoCardGeometry"/>.
    /// </summary>
    public sealed class PhotoCard : MaskableGraphic
    {
        private Texture2D _texture;

        /// <summary>
        /// The picture to draw, or null to draw nothing. Setting it rebuilds the
        /// mesh, so callers may assign it every frame: the setter short circuits
        /// when the texture has not actually changed.
        /// </summary>
        public Texture2D Texture
        {
            get { return _texture; }
            set
            {
                if (_texture == value)
                {
                    return;
                }
                _texture = value;
                SetVerticesDirty();
                SetMaterialDirty();
            }
        }

        public override Texture mainTexture
        {
            get { return _texture != null ? (Texture)_texture : s_WhiteTexture; }
        }

        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            if (_texture == null)
            {
                return;
            }

            const int grid = PhotoCardGeometry.Grid;
            var quad = new UIVertex[4];
            for (var gx = 0; gx < grid; gx++)
            {
                for (var gy = 0; gy < grid; gy++)
                {
                    // Corner order must wind the same way as a UI quad:
                    // bottom left, top left, top right, bottom right in canvas
                    // space, which in card uv (y down) is (0,1) (0,0) (1,0) (1,1).
                    AddCorner(quad, 0, gx, gy + 1);
                    AddCorner(quad, 1, gx, gy);
                    AddCorner(quad, 2, gx + 1, gy);
                    AddCorner(quad, 3, gx + 1, gy + 1);
                    vh.AddUIVertexQuad(quad);
                }
            }
        }

        private void AddCorner(UIVertex[] quad, int slot, int cellX, int cellY)
        {
            var uv = new Vector2(
                (float)cellX / PhotoCardGeometry.Grid,
                (float)cellY / PhotoCardGeometry.Grid);
            var vertex = UIVertex.simpleVert;
            vertex.position = PhotoCardGeometry.Project(uv);
            // The texture's v axis runs up, the card's uv runs down.
            vertex.uv0 = new Vector2(uv.x, 1f - uv.y);
            vertex.color = color;
            quad[slot] = vertex;
        }
    }

    /// <summary>
    /// The card's shadow: the same projected outline, as ONE flat quad, offset
    /// and drawn behind. One quad and not one per cell, deliberately: per cell
    /// the shadow of a cell would land on top of its neighbours' picture, which
    /// is a bug the original hit and documented.
    /// </summary>
    public sealed class PhotoCardShadow : MaskableGraphic
    {
        private readonly Vector2[] _corners = new Vector2[4];
        private bool _visible;

        /// <summary>Draws the shadow only while the card has something to cast one.</summary>
        public bool Visible
        {
            get { return _visible; }
            set
            {
                if (_visible == value)
                {
                    return;
                }
                _visible = value;
                SetVerticesDirty();
            }
        }

        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            if (!_visible)
            {
                return;
            }

            PhotoCardGeometry.Corners(_corners);
            var quad = new UIVertex[4];
            // Same winding as the card: bottom left, top left, top right, bottom right.
            SetVertex(quad, 0, _corners[3]);
            SetVertex(quad, 1, _corners[0]);
            SetVertex(quad, 2, _corners[1]);
            SetVertex(quad, 3, _corners[2]);
            vh.AddUIVertexQuad(quad);
        }

        private void SetVertex(UIVertex[] quad, int slot, Vector2 point)
        {
            var vertex = UIVertex.simpleVert;
            vertex.position = point + PhotoCardGeometry.ShadowOffset;
            vertex.color = PhotoCardGeometry.ShadowColor;
            quad[slot] = vertex;
        }
    }
}
