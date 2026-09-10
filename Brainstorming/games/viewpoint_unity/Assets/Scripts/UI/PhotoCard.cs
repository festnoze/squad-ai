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
    ///
    /// Since V-HUD-04 the grid is not quite a full grid: the four corner cells
    /// are replaced by fans that follow the rounded corner of the paper
    /// (CornerCellFan), because V-PROP-02 asks that the card read as the same
    /// printed object the world shows and a print has no square corners. The
    /// fans tile exactly with the cells that are left whole, so the card is
    /// still one continuous surface.
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

        // ---- The print's own proportions -------------------------------------

        /// <summary>
        /// Where the picture stops and the paper starts, in card uv (x right,
        /// y DOWN, the convention Project takes), for the sides and the top.
        ///
        /// DERIVED FROM THE STUDIO and never written out. PhotoSnaps paints the
        /// polaroid frame straight onto the readback this card draws, so these
        /// two numbers already describe what is IN the texture: a paper white
        /// frame of Border px on the left, right and top and BottomBorder px at
        /// the bottom of a SnapSize square. Gameplay PRD 6.9 pins that as a
        /// RATIO (24 and 48 at 512), and Tier 3 raised the studio to 768 with
        /// both borders scaled by the same ratio, which is why the studio
        /// derives them too.
        ///
        /// Reading the ratio back off the studio's own constants is what stops
        /// the card and the print from drifting apart the next time SnapSize
        /// moves. A card that spelt out 24 / 512 would have gone quietly wrong
        /// on that change, and the error would have surfaced as a hairline in
        /// the wrong place, which nobody reads as a units bug.
        ///
        /// Both are compile-time constant expressions, so this is a dependency
        /// on two numbers and not on the studio object: nothing here loads,
        /// instantiates or waits for PhotoSnaps.
        /// </summary>
        public const float ApertureInset = (float)PhotoSnaps.Border / PhotoSnaps.SnapSize;

        /// <summary>
        /// The wide bottom margin of the print, in card uv. Double the other
        /// three (PRD 6.9), and derived from the studio for the same reason.
        /// </summary>
        public const float ApertureBottomInset = (float)PhotoSnaps.BottomBorder / PhotoSnaps.SnapSize;

        /// <summary>
        /// Corner radius of the paper, in card uv (V-PROP-02, "slightly rounded
        /// corners").
        ///
        /// Three quarters of the narrow border, which lands at 3.5 percent of
        /// the side: an instant print is 88 mm across with a corner radius near
        /// 3 mm, so this is the real object's proportion rather than a taste.
        ///
        /// It is expressed against the border for a reason that outlives the
        /// number. The rounding is a CUT, and a cut deeper than the frame is
        /// wide would eat into the picture, which is the one thing on this card
        /// that may not move by a pixel (gameplay PRD 6.9, and PhotoSnaps'
        /// PaintPolaroidPrint says the same at length). Bound to the narrow
        /// border, the corner can only ever remove paper.
        /// </summary>
        public const float CornerRadiusUv = ApertureInset * 0.75f;

        /// <summary>
        /// Segments per quarter turn. Four is round at the 2 px radius a 62 px
        /// card gives, and the arc is cheap enough that the number is not worth
        /// tuning below that.
        /// </summary>
        public const int CornerSegments = 4;

        /// <summary>
        /// Points CornerCellFan writes: the apex, the two straight ends, and
        /// the arc's CornerSegments + 1 points.
        /// </summary>
        public const int CornerFanCount = CornerSegments + 4;

        /// <summary>
        /// How far the soft shadow reaches beyond the paper, in pixels. It is
        /// larger than the drop offset (3, 4) on purpose: a shadow that reaches
        /// a little way out on the LIT side as well reads as paper lifted off
        /// the panel, where a shadow that only ever trails behind reads as a
        /// sticker with a smear under one edge.
        /// </summary>
        public const float ShadowSpreadPx = 5f;

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

        /// <summary>
        /// The corner radius actually drawn, in card uv: CornerRadiusUv bounded
        /// by the cell the fan replaces.
        ///
        /// ONE function, because the card CUTS this corner and the shadow
        /// sprite DRAWS the same corner, and two copies of one Mathf.Min are
        /// two chances of a rounded card under a square shadow. The bound is
        /// impossible to reach today (0.035 against 0.167) and is not there to
        /// be reached: a future Grid or border change should cost a blunter
        /// corner, never a fan folded inside out over its neighbours.
        /// </summary>
        public static float CornerRadius()
        {
            return Mathf.Min(CornerRadiusUv, 1f / Grid);
        }

        /// <summary>
        /// One rounded corner of the paper, as a triangle fan in card uv.
        ///
        /// The rounding is GEOMETRY and not a mask texture, and that is forced
        /// rather than preferred. The card's one texture unit is already the
        /// print (mainTexture), a UI graphic samples exactly one texture, and a
        /// second sampler would need a shader of its own: the README's most
        /// expensive lesson is that a shader this game only ever reaches
        /// through Shader.Find is STRIPPED from the player, so a card that
        /// needed one would look right in the editor and lose its corners in
        /// the build. Cut vertices cost nothing and cannot be stripped.
        ///
        /// into[0] is the apex, which is the cell's INNER corner. into[1] to
        /// into[CornerFanCount - 1] is the cell's outer boundary, walked in the
        /// same rotational order the grid quads use, and it includes the cell's
        /// two inner edges as the fan's closing spokes: that is what makes the
        /// fan tile exactly with the 32 cells that stay whole, with no seam and
        /// no overlap.
        ///
        /// `corner` indexes as Corners does: 0 top left, 1 top right, 2 bottom
        /// right, 3 bottom left.
        /// </summary>
        public static void CornerCellFan(int corner, Vector2[] into)
        {
            const float cell = 1f / Grid;
            float radius = CornerRadius();

            // The cell's outer corner, and the direction from it into the card.
            float ox = (corner == 1 || corner == 2) ? 1f : 0f;
            float oy = corner >= 2 ? 1f : 0f;
            float sx = ox > 0.5f ? -1f : 1f;
            float sy = oy > 0.5f ? -1f : 1f;

            into[0] = new Vector2(ox + (sx * cell), oy + (sy * cell));

            // The end of the straight run along the y edge, then the arc, then
            // the end of the straight run along the x edge. The arc is centred
            // at (ox + sx r, oy + sy r), so theta = 0 lands on the y edge and
            // theta = 90 degrees on the x edge, both exactly on the straight
            // runs they continue.
            into[1] = new Vector2(ox, oy + (sy * cell));
            for (var k = 0; k <= CornerSegments; k++)
            {
                float theta = Mathf.PI * 0.5f * k / CornerSegments;
                into[2 + k] = new Vector2(
                    ox + (sx * radius) - (sx * radius * Mathf.Cos(theta)),
                    oy + (sy * radius) - (sy * radius * Mathf.Sin(theta)));
            }
            into[CornerFanCount - 1] = new Vector2(ox + (sx * cell), oy);

            // Two of the four corners come out of that construction walked the
            // other way round (the handedness is exactly the sign of sx * sy),
            // so they are reversed and all four wind like the grid. UI/Default
            // draws with Cull Off, so this changes nothing on screen today; it
            // is here so that a reader comparing this fan with the grid quads
            // is not told two different stories about which way a UI triangle
            // goes.
            if (sx * sy < 0f)
            {
                for (int a = 1, b = CornerFanCount - 1; a < b; a++, b--)
                {
                    Vector2 swap = into[a];
                    into[a] = into[b];
                    into[b] = swap;
                }
            }
        }

        /// <summary>
        /// The soft shadow's quad: the card's own four corners grown by
        /// ShadowSpreadPx on both axes so the sprite has room for its falloff.
        /// WITHOUT the drop offset, which the shadow graphic still adds itself.
        ///
        /// Fed by Corners rather than by projecting uvs of its own, so the
        /// shadow can never come to disagree with the card about where the
        /// paper is.
        /// </summary>
        public static void ShadowQuad(Vector2[] into)
        {
            Corners(into);
            Vector2 centre = 0.25f * (into[0] + into[1] + into[2] + into[3]);
            for (var i = 0; i < 4; i++)
            {
                // A sign and not a normalized direction: growing by the same
                // pixels on each axis is what lets the sprite's margin be one
                // fraction of the quad on both axes (see PhotoCardShadow).
                // The roll is 9 degrees on a near square card, so every corner
                // is still well inside its own quadrant and no sign here is a
                // coin toss.
                Vector2 d = into[i] - centre;
                into[i] += new Vector2(
                    Mathf.Sign(d.x) * ShadowSpreadPx,
                    Mathf.Sign(d.y) * ShadowSpreadPx);
            }
        }
    }

    /// <summary>
    /// The card itself: the photo picture, projected through
    /// <see cref="PhotoCardGeometry"/> and finished as paper (V-HUD-04, and
    /// V-PROP-02's paper look as it applies to the HUD).
    ///
    /// WHAT THE TEXTURE ALREADY GIVES. The card does not draw the paper white
    /// frame or the wide bottom margin, and must not: the studio paints both
    /// straight into the picture it hands over (PhotoSnaps.PaintPolaroidPrint),
    /// so they are pixels of the texture and they are already in the exact
    /// ratio PRD 6.9 pins. Drawing a second frame on top would be a frame that
    /// could drift from the print, which is the whole failure the studio's own
    /// comment on Border warns about.
    ///
    /// WHAT THIS CLASS ADDS on top of the projected grid:
    ///   - rounded corners, cut out of the paper (PhotoCardGeometry);
    ///   - the hairline shadow gap between the frame and the picture, redrawn
    ///     at CARD scale because the studio's own is sub-pixel there;
    ///   - a faint paper shading across the print, lit from where the drop
    ///     shadow says the light is.
    /// Its shadow (PhotoCardShadow) carries the soft drop shadow.
    ///
    /// It therefore assumes its texture IS a studio print, which is the only
    /// thing the HUD ever hands it (Hud passes PhotoSnaps.GetTexture straight
    /// through). The one piece of that assumption that would look broken rather
    /// than merely different on some other picture is the hairline, so the
    /// hairline is the one piece that checks.
    /// </summary>
    public sealed class PhotoCard : MaskableGraphic
    {
        /// <summary>
        /// The darkest the paper shading goes, as a multiplier on the print
        /// (V-PROP-02's "faint gloss on the picture"). Six percent across the
        /// diagonal is what makes a 62 px thumbnail read as a sheet lying under
        /// a light instead of a flat sticker.
        ///
        /// It only ever DARKENS: the multiplier is exactly 1 at the lit corner.
        /// That is deliberate and not just conservative. Section 6.3's emissive
        /// isolation check thresholds the graded frame at 0.98 and fails on any
        /// survivor outside an emissive's bounds, so a HUD element that pushed
        /// paper white UP would be a new way to fail a colour check. The shot
        /// probe hides the HUD before it measures, so this is belt and braces
        /// today, and it stays true whatever a later frame is measured with.
        /// </summary>
        const float SheenFloor = 0.94f;

        /// <summary>
        /// The hairline shadow gap of V-PROP-02, one pixel wide in card uv.
        ///
        /// The studio already paints this line (PhotoSnaps' HairlineWidth and
        /// HairlineGain: the two outermost pixels of the aperture go 15 percent
        /// darker), but it paints it in PRINT pixels. Two pixels of a 768 square
        /// are 0.16 px on a 62 px card, so at HUD size the line is filtered out
        /// of existence and the picture reads as printed flush with the paper.
        /// Redrawing it here at one pixel is the same decision expressed at the
        /// size the player actually sees, with the same 15 percent: a quad at
        /// full alpha whose rgb is the print times SeamGain resolves to exactly
        /// print * SeamGain, which is what the studio writes into its pixels.
        ///
        /// The number is repeated rather than shared because the studio's own
        /// constants are private to it; see the FOLLOW-UP in this round's notes.
        /// </summary>
        const float SeamWidthUv = 1f / PhotoCardGeometry.CardSize;

        const float SeamGain = 0.85f;

        /// <summary>
        /// Where the light is, read off the drop shadow so that the two can
        /// never disagree: the paper darkens toward the corner the shadow falls
        /// into. Canvas y is up and card uv y is down, hence the flip on y.
        /// </summary>
        static readonly float SheenX = Mathf.Sign(PhotoCardGeometry.ShadowOffset.x);
        static readonly float SheenY = -Mathf.Sign(PhotoCardGeometry.ShadowOffset.y);

        // Kept as fields rather than allocated per call: the HUD reassigns this
        // graphic's colour every frame while the card fades out to the raised
        // picture (Hud.StepHeldCard), and every one of those rebuilds the mesh.
        readonly UIVertex[] _quad = new UIVertex[4];
        readonly Vector2[] _fan = new Vector2[PhotoCardGeometry.CornerFanCount];

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
            for (var gx = 0; gx < grid; gx++)
            {
                for (var gy = 0; gy < grid; gy++)
                {
                    // The four corner cells belong to the fans below. The
                    // radius is a fifth of a cell, so a fan never reaches into
                    // the cell beside it and this is the only exception the
                    // grid needs.
                    bool cornerCell = (gx == 0 || gx == grid - 1) && (gy == 0 || gy == grid - 1);
                    if (cornerCell)
                    {
                        continue;
                    }

                    // Corner order must wind the same way as a UI quad:
                    // bottom left, top left, top right, bottom right in canvas
                    // space, which in card uv (y down) is (0,1) (0,0) (1,0) (1,1).
                    AddCorner(_quad, 0, gx, gy + 1);
                    AddCorner(_quad, 1, gx, gy);
                    AddCorner(_quad, 2, gx + 1, gy);
                    AddCorner(_quad, 3, gx + 1, gy + 1);
                    vh.AddUIVertexQuad(_quad);
                }
            }

            for (var corner = 0; corner < 4; corner++)
            {
                AddCornerFan(vh, corner);
            }

            AddApertureSeam(vh);
        }

        private void AddCorner(UIVertex[] quad, int slot, int cellX, int cellY)
        {
            var uv = new Vector2(
                (float)cellX / PhotoCardGeometry.Grid,
                (float)cellY / PhotoCardGeometry.Grid);
            quad[slot] = MakeVertex(uv, 1f);
        }

        /// <summary>
        /// One rounded corner, as a fan around the cell's inner corner. Drawn
        /// after the grid and never over it: the fan's own closing spokes ARE
        /// the cell's inner edges, so the two meet along a shared line.
        /// </summary>
        private void AddCornerFan(VertexHelper vh, int corner)
        {
            PhotoCardGeometry.CornerCellFan(corner, _fan);
            int first = vh.currentVertCount;
            for (var i = 0; i < PhotoCardGeometry.CornerFanCount; i++)
            {
                vh.AddVert(MakeVertex(_fan[i], 1f));
            }
            for (var i = 1; i < PhotoCardGeometry.CornerFanCount - 1; i++)
            {
                vh.AddTriangle(first + i, first + i + 1, first);
            }
        }

        /// <summary>
        /// The hairline shadow gap between the frame and the picture, drawn as
        /// four thin runs just INSIDE the aperture (see SeamWidthUv for why it
        /// is redrawn at all, and PhotoSnaps' HairlineWidth for why it never
        /// touches the paper: the frame is the same white the physical polaroid
        /// mesh of V-PROP-02 is built from, and eating a pixel of it would put
        /// the two out of step).
        ///
        /// Skipped unless the texture is square, which every studio print is by
        /// construction (SnapSize x SnapSize). This class is a public component
        /// and its aperture is a fact about a print, so on some other picture
        /// the line would be a dark rectangle across the middle of it: a
        /// failure that is silent, ugly, and cheap to rule out.
        /// </summary>
        private void AddApertureSeam(VertexHelper vh)
        {
            if (_texture.width != _texture.height)
            {
                return;
            }

            const float w = SeamWidthUv;
            const float x0 = PhotoCardGeometry.ApertureInset;
            const float x1 = 1f - PhotoCardGeometry.ApertureInset;
            const float y0 = PhotoCardGeometry.ApertureInset;
            const float y1 = 1f - PhotoCardGeometry.ApertureBottomInset;

            // The horizontal runs take the four corners and the vertical ones
            // stop short of them. Overlapping instead would darken each corner
            // twice and print four dark dots, which is the same class of bug
            // the shadow's own comment records.
            AddSeamRun(vh, x0, y0, x1, y0 + w, true);
            AddSeamRun(vh, x0, y1 - w, x1, y1, true);
            AddSeamRun(vh, x0, y0 + w, x0 + w, y1 - w, false);
            AddSeamRun(vh, x1 - w, y0 + w, x1, y1 - w, false);
        }

        /// <summary>
        /// One run of the seam, subdivided along its length like the grid and
        /// for the reason the class summary gives: one long quad would map its
        /// texture affinely, so its darkening would drift off the pixels it
        /// belongs to by up to a pixel near the tilted end. Perspective maps
        /// straight lines to straight lines, so the POSITION of the run needs
        /// no subdivision; only what it samples does.
        /// </summary>
        private void AddSeamRun(VertexHelper vh, float x0, float y0, float x1, float y1, bool horizontal)
        {
            const int steps = PhotoCardGeometry.Grid;
            for (var i = 0; i < steps; i++)
            {
                float a = (float)i / steps;
                float b = (float)(i + 1) / steps;
                float ax = horizontal ? Mathf.Lerp(x0, x1, a) : x0;
                float bx = horizontal ? Mathf.Lerp(x0, x1, b) : x1;
                float ay = horizontal ? y0 : Mathf.Lerp(y0, y1, a);
                float by = horizontal ? y1 : Mathf.Lerp(y0, y1, b);

                // Same winding as the grid cells above.
                _quad[0] = MakeVertex(new Vector2(ax, by), SeamGain);
                _quad[1] = MakeVertex(new Vector2(ax, ay), SeamGain);
                _quad[2] = MakeVertex(new Vector2(bx, ay), SeamGain);
                _quad[3] = MakeVertex(new Vector2(bx, by), SeamGain);
                vh.AddUIVertexQuad(_quad);
            }
        }

        /// <summary>
        /// A vertex of the card: projected position, the print's uv, and the
        /// graphic's colour with the paper shading and `tint` folded in.
        /// </summary>
        private UIVertex MakeVertex(Vector2 uv, float tint)
        {
            var vertex = UIVertex.simpleVert;
            vertex.position = PhotoCardGeometry.Project(uv);
            // The texture's v axis runs up, the card's uv runs down.
            vertex.uv0 = new Vector2(uv.x, 1f - uv.y);
            vertex.color = PaperColor(uv, tint);
            return vertex;
        }

        /// <summary>
        /// The paper shading: 1 at the lit corner, SheenFloor at the corner the
        /// drop shadow falls into, linear across the diagonal between them.
        ///
        /// Per vertex and not per pixel, which is what makes it free: the grid
        /// already lays down a 7 x 7 lattice, and a linear ramp interpolated
        /// over that lattice IS the ramp. The alpha is left strictly alone, so
        /// the HUD's fade of the card (Hud.StepHeldCard) still owns it.
        /// </summary>
        private Color PaperColor(Vector2 uv, float tint)
        {
            float t = 0.5f + (0.5f * ((SheenX * (uv.x - 0.5f)) + (SheenY * (uv.y - 0.5f))));
            float k = tint * Mathf.Lerp(1f, SheenFloor, Mathf.Clamp01(t));
            Color c = color;
            return new Color(c.r * k, c.g * k, c.b * k, c.a);
        }
    }

    /// <summary>
    /// The card's shadow: the same projected outline, as ONE flat quad, offset
    /// and drawn behind. One quad and not one per cell, deliberately: per cell
    /// the shadow of a cell would land on top of its neighbours' picture, which
    /// is a bug the original hit and documented.
    ///
    /// V-PROP-02 asks for a SOFT drop shadow, and softness is the one thing a
    /// flat quad of one colour cannot do. It gets it from a generated sprite
    /// (Sprite below) rather than from more geometry, which keeps the "one
    /// quad" rule above intact: a feathered skirt of triangles round the
    /// outline would be exactly the many-pieces shadow that comment forbids.
    /// The sprite is drawn in code and cached, so it adds no asset to a project
    /// whose whole interface is code (PRD_VISUAL 3.2 as amended by C.11).
    /// </summary>
    public sealed class PhotoCardShadow : MaskableGraphic
    {
        /// <summary>
        /// Side of the generated sprite. The quad it covers is about 72 px
        /// across, so 64 is near enough to 1:1 that the falloff needs no
        /// mipmaps, and 16 KB is cheap enough to keep for the life of the
        /// process.
        /// </summary>
        const int SpriteSize = 64;

        /// <summary>
        /// How far INSIDE the paper's outline the falloff starts, as a fraction
        /// of ShadowSpreadPx. A shadow with a hard core and a soft skirt reads
        /// as a halo drawn around the card; starting a little early is what
        /// makes it read as one soft shadow of a sheet lifted off the panel.
        /// </summary>
        const float CoreSoftening = 0.3f;

        static Texture2D _sprite;

        private readonly Vector2[] _corners = new Vector2[4];
        private readonly UIVertex[] _quad = new UIVertex[4];
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

        /// <summary>
        /// The soft rounded rectangle, in place of the white texture a Graphic
        /// defaults to. Generated on first use, which is when the canvas asks
        /// for the material, so nothing is built for a shadow that never shows.
        /// </summary>
        public override Texture mainTexture
        {
            get { return Sprite(); }
        }

        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            if (!_visible)
            {
                return;
            }

            PhotoCardGeometry.ShadowQuad(_corners);
            // Same winding as the card: bottom left, top left, top right,
            // bottom right, and the sprite's uv follows the canvas (v up).
            SetVertex(_quad, 0, _corners[3], new Vector2(0f, 0f));
            SetVertex(_quad, 1, _corners[0], new Vector2(0f, 1f));
            SetVertex(_quad, 2, _corners[1], new Vector2(1f, 1f));
            SetVertex(_quad, 3, _corners[2], new Vector2(1f, 0f));
            vh.AddUIVertexQuad(_quad);
        }

        private void SetVertex(UIVertex[] quad, int slot, Vector2 point, Vector2 uv)
        {
            var vertex = UIVertex.simpleVert;
            vertex.position = point + PhotoCardGeometry.ShadowOffset;
            vertex.uv0 = uv;
            // Modulated by this Graphic's own colour so the shadow can be faded
            // with the card it belongs to (V-ANIM-03 forbids a HUD element
            // appearing or vanishing in one frame, and the held card leaves as
            // the raised picture takes over). Graphic.color defaults to white,
            // so every existing caller multiplies by 1 and keeps the tuned
            // ShadowColor exactly as it was.
            vertex.color = PhotoCardGeometry.ShadowColor * color;
            quad[slot] = vertex;
        }

        /// <summary>
        /// The shadow's shape and its softness, drawn once into a small
        /// texture: the card's rounded rectangle, full alpha inside, fading to
        /// nothing by the edge of the quad.
        ///
        /// The falloff is measured with the signed distance to the rounded
        /// rectangle rather than per axis, which is what makes it the same
        /// width along an edge and round a corner. Everything is computed in
        /// CARD uv, so the radius is the very one the card cuts
        /// (PhotoCardGeometry.CornerRadius) and the shadow cannot end up square
        /// under rounded paper.
        ///
        /// The sprite is generated for the UNTILTED card and then stretched by
        /// the projection with its quad, so the pitch compresses its falloff
        /// along y by about a tenth. That is invisible on a blurred edge, and
        /// it is the price of the one quad this class is careful to stay at.
        ///
        /// Static and kept: it depends on nothing but constants, so one copy
        /// serves every card that ever exists. Unity reports a destroyed
        /// texture as null (an unloaded asset pass could take it), so the check
        /// below is a real check and not a first-run flag.
        /// </summary>
        private static Texture2D Sprite()
        {
            if (_sprite != null)
            {
                return _sprite;
            }

            var texture = new Texture2D(SpriteSize, SpriteSize, TextureFormat.RGBA32, false, false);
            texture.name = "PhotoCardShadowSprite";
            texture.wrapMode = TextureWrapMode.Clamp;
            texture.filterMode = FilterMode.Bilinear;

            // The quad is the card grown by ShadowSpreadPx on both axes, so the
            // paper occupies the middle (1 - 2 * margin) of the sprite.
            const float spreadUv = PhotoCardGeometry.ShadowSpreadPx / PhotoCardGeometry.CardSize;
            const float margin = spreadUv / (1f + (2f * spreadUv));
            float radius = PhotoCardGeometry.CornerRadius();
            float core = spreadUv * CoreSoftening;

            var pixels = new Color32[SpriteSize * SpriteSize];
            for (var y = 0; y < SpriteSize; y++)
            {
                int row = y * SpriteSize;
                for (var x = 0; x < SpriteSize; x++)
                {
                    // Pixel centre in the quad, then in card uv.
                    float qx = (x + 0.5f) / SpriteSize;
                    float qy = (y + 0.5f) / SpriteSize;
                    float cx = (qx - margin) / (1f - (2f * margin));
                    float cy = (qy - margin) / (1f - (2f * margin));

                    // Signed distance to the rounded rectangle [0, 1] square:
                    // negative inside the paper, positive outside.
                    float ex = Mathf.Abs(cx - 0.5f) - 0.5f + radius;
                    float ey = Mathf.Abs(cy - 0.5f) - 0.5f + radius;
                    float outX = Mathf.Max(ex, 0f);
                    float outY = Mathf.Max(ey, 0f);
                    float d = Mathf.Sqrt((outX * outX) + (outY * outY))
                        + Mathf.Min(Mathf.Max(ex, ey), 0f) - radius;

                    float t = Mathf.Clamp01((d + core) / (spreadUv + core));
                    float a = 1f - (t * t * (3f - (2f * t)));
                    pixels[row + x] = new Color32(255, 255, 255, (byte)Mathf.RoundToInt(a * 255f));
                }
            }
            texture.SetPixels32(pixels);
            // No mipmaps to update, and the CPU copy is dropped: the sprite is
            // never read back and never regenerated from itself.
            texture.Apply(false, true);
            _sprite = texture;
            return _sprite;
        }
    }
}
