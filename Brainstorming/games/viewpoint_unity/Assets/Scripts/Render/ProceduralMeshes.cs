using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// The meshes Unity has no primitive for, plus the one it does have but
    /// draws with sharp edges. All of them are cached: the game builds them per
    /// level and per photo, and identical rings, panels and blocks must share
    /// one mesh.
    /// </summary>
    public static class ProceduralMeshes
    {
        private static readonly Dictionary<string, Mesh> Cache = new Dictionary<string, Mesh>();

        // Below this a bevel is not geometry any more, it is a rounding error:
        // 10 microns is a hundredth of the smallest feature the game builds
        // (the 0.06 m marker slab), and the chamfer of such a box would be
        // thinner than a shading sample.
        private const float BevelEpsilon = 1e-5f;

        /// <summary>
        /// The rock mass hanging under a platform (PRD_VISUAL 4.6 V-GEO-02).
        ///
        /// Today every island's underside is a darker BOX, which section 1.1 of
        /// that document calls out by name: "the one thing meant to say terrain
        /// says second box". This replaces it with a tapered, irregular,
        /// flat-shaded frustum: widest at the top where it meets the slab,
        /// narrowing as it falls, its silhouette pushed in and out by a
        /// low-frequency hash so no two islands share a profile.
        ///
        /// Geometry contract, because callers depend on all three:
        ///   - the TOP ring sits exactly at y = 0 and spans <paramref name="footprint"/>,
        ///     so the mesh drops under a slab of that size with no gap and no
        ///     overhang, whatever the taper does below;
        ///   - it descends to y = -depth;
        ///   - THE TRANSFORM ORIGIN MUST BE THE TOP OF THE MASS, which it is by
        ///     construction since the top ring is at local y = 0. The Rock style
        ///     of Viewpoint/Surface darkens a surface by how far it sits BELOW
        ///     its object origin (RockFadeDepth 3 m, down to RockFadeFloor 0.45),
        ///     which is how an island fades into the abyss. That needs no vertex
        ///     colour and no per-island property, but it does mean an object
        ///     placed by its centre instead of its top would fade wrongly.
        ///
        /// FLAT SHADED on purpose: facets are the point. A smooth-normalled
        /// frustum reads as a cone, and the PRD asks for a mass "breaking into a
        /// few facets". That means no vertex is shared between two sides, which
        /// is why this builds independent triangles rather than a vertex ring.
        ///
        /// <paramref name="seed"/> is hashed, never used as a random source: the
        /// same island must come back identical after a level reload
        /// (PlayMode Stage11Reload) and after a rewind (Stage12Rewind).
        /// </summary>
        public static Mesh IslandSkirt(Vector3 footprint, float depth, int seed, int sides = 10)
        {
            if (sides < 5)
            {
                sides = 5;
            }
            if (sides > 16)
            {
                sides = 16;
            }
            if (depth < 0.01f)
            {
                depth = 0.01f;
            }

            // THE SEED IS QUANTISED TO EIGHT VARIANTS, and that is a cache
            // decision rather than an artistic one.
            //
            // The cache below is static and never cleared, deliberately: a
            // renderer somewhere may still be pointing at a mesh, so dropping
            // one would leave a hole in the world. That is fine while the KEY
            // takes a small number of values, and fatal when it does not. Keyed
            // on the raw per-position seed, every platform of every level got
            // its own permanent mesh: PlayMode's Stage23 rebuilds all
            // twenty-five levels, and the editor climbed to 2.1 GB doing it.
            //
            // Eight shapes per (footprint, depth) is plenty of variety - no two
            // islands in a level look alike - and it bounds the cache at eight
            // times the number of distinct platform sizes, which is a few dozen
            // entries rather than a few hundred meshes that never go away.
            int shape = seed & 7;
            string cacheKey = "skirt:" + Exact(footprint.x) + ":" + Exact(footprint.z) + ":"
                + Exact(depth) + ":" + shape + ":" + sides;
            Mesh cached;
            if (Cache.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            // The taper: three rings down the drop, so the silhouette can bend
            // rather than run straight from top to bottom. Widths are fractions
            // of the footprint, and the top one is EXACTLY 1 so the contract
            // above holds.
            float[] ringY = { 0f, -depth * 0.35f, -depth * 0.72f, -depth };
            float[] ringWidth = { 1f, 0.86f, 0.62f, 0.28f };
            int rings = ringY.Length;

            // Per-side, per-ring radial jitter, hashed from the seed so the
            // shape is a function of the level data and nothing else. The top
            // ring is deliberately NOT jittered: it has to match the slab.
            float[,] jitter = new float[rings, sides];
            for (int r = 1; r < rings; r++)
            {
                for (int s = 0; s < sides; s++)
                {
                    // PRD_VISUAL 4.6: displaced by about 12 percent of the
                    // footprint. Growing with depth, so the mass is orderly
                    // where it meets the architecture and rough where it does
                    // not.
                    float amount = 0.12f * (r / (float)(rings - 1));
                    // 'shape', not 'seed': the cache key is the quantised
                    // shape, so the geometry has to be a function of the same
                    // thing or a cached mesh would not match the key that
                    // fetched it.
                    jitter[r, s] = (Hash01(shape, r * 131 + s) - 0.5f) * 2f * amount;
                }
            }

            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var triangles = new List<int>();

            // A ring's corner in the xz plane, footprint-shaped rather than
            // circular, so a long thin platform gets a long thin island.
            Vector3 Corner(int ring, int side)
            {
                float angle = (side / (float)sides) * Mathf.PI * 2f;
                float w = ringWidth[ring] + jitter[ring, side];
                return new Vector3(
                    Mathf.Cos(angle) * footprint.x * 0.5f * w,
                    ringY[ring],
                    Mathf.Sin(angle) * footprint.z * 0.5f * w);
            }

            // The sides, as independent flat quads.
            for (int r = 0; r < rings - 1; r++)
            {
                for (int s = 0; s < sides; s++)
                {
                    int next = (s + 1) % sides;
                    Vector3 a = Corner(r, s);
                    Vector3 b = Corner(r, next);
                    Vector3 c = Corner(r + 1, next);
                    Vector3 d = Corner(r + 1, s);

                    // One normal for the whole quad: that IS the faceting.
                    // Cross order chosen so it points AWAY from the y axis,
                    // verified by hand at side 0 of the top band, where the
                    // corner lies on +x and the normal must have a positive x.
                    Vector3 normal = Vector3.Cross(b - a, d - a).normalized;
                    if (Vector3.Dot(normal, new Vector3(a.x, 0f, a.z)) < 0f)
                    {
                        normal = -normal;
                    }

                    int baseIndex = vertices.Count;
                    vertices.Add(a); vertices.Add(b); vertices.Add(c); vertices.Add(d);
                    for (int i = 0; i < 4; i++)
                    {
                        normals.Add(normal);
                    }

                    triangles.Add(baseIndex); triangles.Add(baseIndex + 2); triangles.Add(baseIndex + 1);
                    triangles.Add(baseIndex); triangles.Add(baseIndex + 3); triangles.Add(baseIndex + 2);
                }
            }

            // A flat cap on the bottom, so looking up from the abyss does not
            // see straight into a hollow shell. No top cap: the slab covers it.
            int centreIndex = vertices.Count;
            vertices.Add(new Vector3(0f, ringY[rings - 1], 0f));
            normals.Add(Vector3.down);
            for (int s = 0; s < sides; s++)
            {
                int next = (s + 1) % sides;
                int start = vertices.Count;
                vertices.Add(Corner(rings - 1, s));
                vertices.Add(Corner(rings - 1, next));
                normals.Add(Vector3.down); normals.Add(Vector3.down);
                triangles.Add(centreIndex); triangles.Add(start); triangles.Add(start + 1);
            }

            Mesh mesh = new Mesh();
            mesh.name = "IslandSkirt_" + Exact(footprint.x) + "x" + Exact(footprint.z) + "_" + seed;
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetTriangles(triangles, 0);
            // No RecalculateNormals: the flat per-quad normals above ARE the
            // look, and averaging them would turn the facets into a cone.
            mesh.RecalculateBounds();

            Cache[cacheKey] = mesh;
            return mesh;
        }

        /// <summary>
        /// A stable pseudo-random value in 0..1 from two integers. Not
        /// UnityEngine.Random on purpose: an island's shape must survive a level
        /// reload and a rewind unchanged, so it can only ever be a function of
        /// the level data.
        /// </summary>
        private static float Hash01(int a, int b)
        {
            unchecked
            {
                uint h = (uint)(a * 73856093) ^ (uint)(b * 19349663);
                h ^= h >> 13;
                h *= 0x85ebca6b;
                h ^= h >> 16;
                return (h & 0xFFFFFF) / (float)0x1000000;
            }
        }

        /// <summary>
        /// Torus lying flat, its axis along +y, centered on the origin: the
        /// teleporter ring of PRD 5.7 (inner 1.05, outer 1.25), which spins in
        /// yaw. Unity ships no torus primitive, and Godot's TorusMesh that the
        /// original used has the same flat orientation.
        /// </summary>
        /// <summary>
        /// A FLAT annulus of real thickness: a band, not a doughnut
        /// (PRD_VISUAL 4.7 V-PROP-05). <see cref="Torus"/> is round in section
        /// and is what the teleporter's floating ring already uses; this is the
        /// square-sectioned version the machine wants for its inlaid ground
        /// track and for the segmented charge readout.
        ///
        /// <paramref name="arcTurns"/> is the fraction of a full circle to
        /// build, from 0 to 1, and it is the reason this exists rather than a
        /// scaled Torus. The charge readout lights ONE SEGMENT per inserted
        /// battery, so a caller needs a mesh that is a slice of a ring, rotated
        /// into place. An arc of 1 closes the loop and shares no seam; anything
        /// less is capped at both ends so a segment reads as a discrete piece
        /// of metal rather than a gap in a band.
        ///
        /// Lying flat, axis along +y, centred on the origin, so it drops onto a
        /// pad or hangs at a height with no rotation. Smooth normals around the
        /// curve, hard normals on the four flat surfaces, because a band should
        /// read as bent sheet and not as a faceted tube.
        /// </summary>
        public static Mesh Ring(float innerRadius, float outerRadius, float thickness,
            int segments = 48, float arcTurns = 1f)
        {
            if (segments < 3)
            {
                segments = 3;
            }
            arcTurns = Mathf.Clamp(arcTurns, 0.02f, 1f);
            float inner = Mathf.Min(innerRadius, outerRadius);
            float outer = Mathf.Max(innerRadius, outerRadius);
            float half = Mathf.Max(thickness, 1e-4f) * 0.5f;

            string cacheKey = "ring:" + Exact(inner) + ":" + Exact(outer) + ":" + Exact(thickness)
                + ":" + segments + ":" + Exact(arcTurns);
            Mesh cached;
            if (Cache.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            bool closed = arcTurns >= 0.999f;
            // One extra column so an open arc has both ends, and so a closed
            // ring duplicates its seam rather than wrapping the last quad
            // backwards (the same reason Torus adds one).
            int columns = segments + 1;
            float sweep = Mathf.PI * 2f * arcTurns;

            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var triangles = new List<int>();

            // Four surfaces, each with its own vertices so the normals stay
            // hard between them: top, bottom, outer wall, inner wall.
            // Emitted as independent strips, which costs vertices and buys the
            // crisp edge a machined band needs.
            for (int face = 0; face < 4; face++)
            {
                int start = vertices.Count;
                for (int i = 0; i < columns; i++)
                {
                    float a = (i / (float)segments) * sweep;
                    float c = Mathf.Cos(a);
                    float s = Mathf.Sin(a);
                    // Radially outward in the xz plane: the normal of both walls
                    // and the tangent basis for the flat faces.
                    Vector3 radial = new Vector3(c, 0f, s);

                    switch (face)
                    {
                        case 0: // top
                            vertices.Add((radial * inner) + (Vector3.up * half));
                            vertices.Add((radial * outer) + (Vector3.up * half));
                            normals.Add(Vector3.up); normals.Add(Vector3.up);
                            break;
                        case 1: // bottom
                            vertices.Add((radial * outer) - (Vector3.up * half));
                            vertices.Add((radial * inner) - (Vector3.up * half));
                            normals.Add(Vector3.down); normals.Add(Vector3.down);
                            break;
                        case 2: // outer wall
                            vertices.Add((radial * outer) + (Vector3.up * half));
                            vertices.Add((radial * outer) - (Vector3.up * half));
                            normals.Add(radial); normals.Add(radial);
                            break;
                        default: // inner wall, facing the axis
                            vertices.Add((radial * inner) - (Vector3.up * half));
                            vertices.Add((radial * inner) + (Vector3.up * half));
                            normals.Add(-radial); normals.Add(-radial);
                            break;
                    }
                }

                for (int i = 0; i < segments; i++)
                {
                    int a = start + (i * 2);
                    int b = a + 1;
                    int c = a + 2;
                    int d = a + 3;
                    // Verified by hand on the TOP face at i = 0, where the
                    // winding must put the front face along +y: with the inner
                    // vertex first and the sweep running counter-clockwise in
                    // xz, this order is the one whose cross product is up.
                    triangles.Add(a); triangles.Add(c); triangles.Add(b);
                    triangles.Add(b); triangles.Add(c); triangles.Add(d);
                }
            }

            // Caps on an open arc, so a segment is a solid piece rather than an
            // open shell seen end-on.
            if (!closed)
            {
                for (int end = 0; end < 2; end++)
                {
                    float a = end == 0 ? 0f : sweep;
                    Vector3 radial = new Vector3(Mathf.Cos(a), 0f, Mathf.Sin(a));
                    // The cap faces along the ring's tangent, outward at each end.
                    Vector3 tangent = new Vector3(-Mathf.Sin(a), 0f, Mathf.Cos(a));
                    Vector3 normal = end == 0 ? -tangent : tangent;

                    int start = vertices.Count;
                    vertices.Add((radial * inner) - (Vector3.up * half));
                    vertices.Add((radial * outer) - (Vector3.up * half));
                    vertices.Add((radial * outer) + (Vector3.up * half));
                    vertices.Add((radial * inner) + (Vector3.up * half));
                    for (int i = 0; i < 4; i++)
                    {
                        normals.Add(normal);
                    }
                    if (end == 0)
                    {
                        triangles.Add(start); triangles.Add(start + 2); triangles.Add(start + 1);
                        triangles.Add(start); triangles.Add(start + 3); triangles.Add(start + 2);
                    }
                    else
                    {
                        triangles.Add(start); triangles.Add(start + 1); triangles.Add(start + 2);
                        triangles.Add(start); triangles.Add(start + 2); triangles.Add(start + 3);
                    }
                }
            }

            Mesh mesh = new Mesh();
            mesh.name = "Ring_" + Exact(inner) + "_" + Exact(outer) + "_" + Exact(arcTurns);
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetTriangles(triangles, 0);
            // Authored normals: no RecalculateNormals, which would round the
            // four hard edges into a tube.
            mesh.RecalculateBounds();

            Cache[cacheKey] = mesh;
            return mesh;
        }

        /// <summary>
        /// A flat rectangular frame with rounded corners and a rectangular hole
        /// through it: the instant print of PRD_VISUAL 4.7 V-PROP-02, whose
        /// current state that item records as "a white box".
        ///
        /// <see cref="Ring"/> is this mesh's round sibling and the two are built
        /// the same way, as four independent surfaces with hard normals between
        /// them, for the same reason: a sheet of paper and a bent metal band both
        /// read as sheet, and both stop reading as sheet the moment their edge is
        /// smoothed into their face.
        ///
        /// It lies in the xy plane, centred on the origin, spanning EXACTLY
        /// <paramref name="outer"/> across its widest points and
        /// <paramref name="thickness"/> in z, so it drops straight into the place
        /// a unit cube scaled by (outer.x, outer.y, thickness) used to occupy and
        /// no silhouette moves. The front face is at -z and carries the normal
        /// (0, 0, -1), like <see cref="Quad"/> and like Unity's own quad
        /// primitive, because the pictures this frame surrounds face that way.
        ///
        /// Geometry contract, because a caller has to line a picture up with the
        /// hole:
        ///   - the aperture spans <paramref name="inner"/> and is centred in x;
        ///   - it is NOT centred in y. The top margin equals the side margin and
        ///     the whole of the remaining slack goes to the BOTTOM. That wide
        ///     caption border is the one feature nobody recognises an instant
        ///     print without, and it is what V-PROP-02 means by "the wider bottom
        ///     margin";
        ///   - <see cref="RoundedFrameApertureCenterY"/> returns that offset, so
        ///     a caller reads the rule instead of repeating it and the two cannot
        ///     drift apart.
        ///
        /// Normals are authored, never recalculated, and they are of two kinds:
        /// hard between the four surfaces, so the paper edge is allowed its own
        /// shading and catches the light the item asks for; smooth AROUND the
        /// corner arcs, so a corner reads as a curve and not as three facets.
        /// The arc normals are also the first normals a polaroid has that are not
        /// axis aligned, and that is why the caller must draw this at localScale
        /// one: an axis-aligned face normal survives a non-uniform scale (the
        /// normal matrix is the inverse transpose, which leaves it pointing the
        /// same way), an arc normal does not, and neither does a corner radius
        /// that gets 0.72 on one axis and 0.035 on another.
        ///
        /// At the default tessellation the loop is 24 points, which comes out at
        /// 200 vertices and 192 triangles. That is a lot for a prop and it is
        /// affordable: a level holds one to three polaroids, they all share this
        /// one cached mesh, and the alternative is the box the item exists to
        /// replace.
        /// </summary>
        /// <param name="outer">Outer extents. The mesh spans exactly this.</param>
        /// <param name="inner">
        /// The aperture. Clamped to <paramref name="outer"/>; equal to it means a
        /// frame of zero width, whose quads are all zero-area and which the GPU
        /// drops, and an aperture of zero means a solid slab with a degenerate
        /// hole. Neither is useful, and neither is a crash.
        /// </param>
        /// <param name="cornerRadius">
        /// In-plane corner radius, used by BOTH loops and clamped to half the
        /// smallest side of either. See the body for why the two loops share one
        /// radius rather than taking one each.
        /// </param>
        /// <param name="cornerSegments">
        /// Segments per corner arc. 1 turns a corner into a single chamfer.
        /// </param>
        public static Mesh RoundedFrame(Vector2 outer, Vector2 inner, float cornerRadius,
            float thickness, int cornerSegments = 5)
        {
            // Absolute values first, for the reason BeveledBox states: a negative
            // extent is a mirrored instance rather than a smaller frame, this
            // mesh is symmetric about x, and the caller's transform keeps the
            // mirror.
            float outerX = Mathf.Abs(outer.x);
            float outerY = Mathf.Abs(outer.y);
            float innerX = Mathf.Min(Mathf.Abs(inner.x), outerX);
            float innerY = Mathf.Min(Mathf.Abs(inner.y), outerY);
            float half = Mathf.Max(Mathf.Abs(thickness), 1e-4f) * 0.5f;
            cornerSegments = Mathf.Clamp(cornerSegments, 1, 16);

            // ONE radius for both loops, and that is a shape decision before it
            // is a safety one. With equal radii the inner loop is the outer loop
            // TRANSLATED inward across a corner, so the paper keeps a constant
            // width around it, which is what a die-cut print looks like. Two
            // radii would pinch or bulge the corner and, worse, could cross the
            // two loops over each other whenever their difference exceeded the
            // margin between them: a frame turned inside out at four points, from
            // an input that looks perfectly reasonable.
            //
            // Clamped to half the smallest side of EITHER rectangle so neither
            // loop can fold through itself.
            float radius = Mathf.Abs(cornerRadius);
            radius = Mathf.Min(radius, 0.5f * Mathf.Min(outerX, outerY));
            radius = Mathf.Min(radius, 0.5f * Mathf.Min(innerX, innerY));

            // QUANTISED TO A MILLIMETRE, exactly as BeveledBox is, and for the
            // same reason rather than by imitation. This cache is static and
            // never cleared on purpose (a live renderer may still be sampling a
            // mesh, so dropping one would leave a hole in the world), which is
            // safe only while the key takes a bounded number of values. An exact
            // float key is right for authored round numbers and wrong for
            // anything computed, and this mesh's aperture IS computed: its caller
            // derives the aperture height from a pixel ratio (PhotoSnaps.Border
            // over PhotoSnaps.SnapSize), so it is 0.587931 and not 0.6, and the
            // next caller may well derive one of these from gameplay. This file
            // already records two leaks that were an exact key on a continuous
            // input; this is the third one not happening.
            //
            // The key is the SANITISED values, so two calls that differ only in
            // something the clamps above threw away share one mesh instead of
            // building two identical ones. The mesh is still built at the exact
            // size asked for: only the key is rounded, so at worst a frame shares
            // the mesh of a frame within a millimetre of it.
            string cacheKey = "roundedframe:" + Mm(outerX) + ":" + Mm(outerY)
                + ":" + Mm(innerX) + ":" + Mm(innerY) + ":" + Mm(radius)
                + ":" + Mm(half * 2f) + ":" + cornerSegments;
            Mesh cached;
            if (Cache.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            // The wide bottom border, read from the one place that decides it.
            float apertureCenterY = RoundedFrameApertureCenterY(
                new Vector2(outerX, outerY), new Vector2(innerX, innerY));

            // Both loops are sampled on the SAME schedule: four corner arcs of
            // (cornerSegments + 1) points each, at the same angles. That is what
            // makes point i of one loop the partner of point i of the other, so
            // the paper between them stitches into well-formed quads with no
            // search and no risk of a crossed strip.
            int loopCount = 4 * (cornerSegments + 1);
            Vector2[] outerLoop = new Vector2[loopCount];
            Vector2[] innerLoop = new Vector2[loopCount];
            Vector2[] radial = new Vector2[loopCount];

            int point = 0;
            for (int corner = 0; corner < 4; corner++)
            {
                // Counter-clockwise from the +x edge: top right, top left, bottom
                // left, bottom right. The two signs place the arc's centre in its
                // quadrant and cos/sin walk the arc inside it, which has one
                // property worth spelling out: the LAST sample of one corner and
                // the FIRST sample of the next are the two ends of a straight
                // side, and they carry the same normal, so the quad between them
                // IS that side and comes out flat. The loop therefore needs no
                // separate pass for the four straight edges.
                float signX = (corner == 0 || corner == 3) ? 1f : -1f;
                float signY = (corner == 0 || corner == 1) ? 1f : -1f;

                for (int j = 0; j <= cornerSegments; j++)
                {
                    float angle = Mathf.PI * 0.5f * (corner + (j / (float)cornerSegments));
                    float cos = Mathf.Cos(angle);
                    float sin = Mathf.Sin(angle);

                    // The outward normal of a rounded rectangle is the arc's own
                    // direction, and at the junction angles it is exactly the
                    // straight side's axis normal, so this one expression is
                    // correct on the curve and on the flat. Analytic, like Torus:
                    // nothing here needs RecalculateNormals.
                    radial[point] = new Vector2(cos, sin);
                    outerLoop[point] = new Vector2(
                        (signX * ((outerX * 0.5f) - radius)) + (cos * radius),
                        (signY * ((outerY * 0.5f) - radius)) + (sin * radius));
                    innerLoop[point] = new Vector2(
                        (signX * ((innerX * 0.5f) - radius)) + (cos * radius),
                        apertureCenterY + (signY * ((innerY * 0.5f) - radius)) + (sin * radius));
                    point++;
                }
            }

            // One extra column duplicates the seam, as Ring and Torus do, so the
            // uv runs 0..1 around the loop instead of backwards across the last
            // quad.
            int columns = loopCount + 1;

            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var uvs = new List<Vector2>();
            var triangles = new List<int>();

            // Planar uv for the two flat faces, over the OUTER rectangle, so the
            // front and the back agree and the aperture lands where it is.
            // Viewpoint/Surface is triplanar from world position and reads no uv
            // at all (PRD_VISUAL 4.5); these exist so the mesh is not a trap for
            // anything that does expect a texture coordinate, which is the same
            // reason BeveledBox carries them.
            Vector2 FaceUv(Vector2 p)
            {
                return new Vector2(
                    outerX > 0f ? ((p.x + (outerX * 0.5f)) / outerX) : 0.5f,
                    outerY > 0f ? ((p.y + (outerY * 0.5f)) / outerY) : 0.5f);
            }

            // Four surfaces, each with its own vertices so the normals stay hard
            // between them: front face, back face, outer wall, inner wall. Each
            // is a two-row strip, and each row is ordered so that Ring's winding
            // below, which walks the quad (rowA i, rowA i+1, rowB i+1, rowB i),
            // comes out facing the way that surface has to face. All four were
            // derived from Cross(v1 - v0, v2 - v0) at the +x side of the loop,
            // where the answer is known by hand.
            for (int face = 0; face < 4; face++)
            {
                int start = vertices.Count;
                for (int i = 0; i < columns; i++)
                {
                    int p = i % loopCount;
                    Vector3 outerFront = new Vector3(outerLoop[p].x, outerLoop[p].y, -half);
                    Vector3 outerBack = new Vector3(outerLoop[p].x, outerLoop[p].y, half);
                    Vector3 innerFront = new Vector3(innerLoop[p].x, innerLoop[p].y, -half);
                    Vector3 innerBack = new Vector3(innerLoop[p].x, innerLoop[p].y, half);
                    Vector3 outward = new Vector3(radial[p].x, radial[p].y, 0f);
                    float u = i / (float)loopCount;

                    switch (face)
                    {
                        case 0: // front face, at -z: the inner row leads
                            vertices.Add(innerFront); vertices.Add(outerFront);
                            normals.Add(Vector3.back); normals.Add(Vector3.back);
                            uvs.Add(FaceUv(innerLoop[p])); uvs.Add(FaceUv(outerLoop[p]));
                            break;
                        case 1: // back face, at +z: the outer row leads
                            vertices.Add(outerBack); vertices.Add(innerBack);
                            normals.Add(Vector3.forward); normals.Add(Vector3.forward);
                            uvs.Add(FaceUv(outerLoop[p])); uvs.Add(FaceUv(innerLoop[p]));
                            break;
                        case 2: // outer wall, facing away from the frame
                            vertices.Add(outerFront); vertices.Add(outerBack);
                            normals.Add(outward); normals.Add(outward);
                            uvs.Add(new Vector2(u, 0f)); uvs.Add(new Vector2(u, 1f));
                            break;
                        default: // inner wall, facing into the aperture
                            vertices.Add(innerBack); vertices.Add(innerFront);
                            normals.Add(-outward); normals.Add(-outward);
                            uvs.Add(new Vector2(u, 1f)); uvs.Add(new Vector2(u, 0f));
                            break;
                    }
                }

                for (int i = 0; i < loopCount; i++)
                {
                    int a = start + (i * 2);
                    int b = a + 1;
                    int c = a + 2;
                    int d = a + 3;
                    triangles.Add(a); triangles.Add(c); triangles.Add(b);
                    triangles.Add(b); triangles.Add(c); triangles.Add(d);
                }
            }

            Mesh mesh = new Mesh();
            mesh.name = "RoundedFrame_" + Exact(outerX) + "x" + Exact(outerY)
                + "_a" + Exact(innerX) + "x" + Exact(innerY) + "_r" + Exact(radius);
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(triangles, 0);
            // Authored normals: RecalculateNormals here would average the four
            // surfaces back together at every edge and delete both the crisp
            // paper edge and the smooth corner in one call.
            mesh.RecalculateBounds();

            Cache[cacheKey] = mesh;
            return mesh;
        }

        /// <summary>
        /// Where <see cref="RoundedFrame"/> puts the centre of its aperture, in
        /// the mesh's own local space (x is always 0, so only y is returned).
        ///
        /// This exists so the rule lives in ONE place. The frame's signature
        /// takes two sizes and no offset, so the mesh has to decide where the
        /// hole goes; a caller that puts a picture behind the hole has to know
        /// where it went, and a caller that computes it a second time is a caller
        /// whose picture slides off the aperture the day the rule changes.
        ///
        /// The rule: the top margin matches the side margin and the bottom keeps
        /// everything left over. Capped at half the vertical slack, so the bottom
        /// border can never come out NARROWER than the top - a print with its
        /// caption border at the top reads instantly as upside down, and that is
        /// the one mistake a "wider at the bottom" rule can make.
        /// </summary>
        public static float RoundedFrameApertureCenterY(Vector2 outer, Vector2 inner)
        {
            float outerX = Mathf.Abs(outer.x);
            float outerY = Mathf.Abs(outer.y);
            float innerX = Mathf.Min(Mathf.Abs(inner.x), outerX);
            float innerY = Mathf.Min(Mathf.Abs(inner.y), outerY);

            float sideMargin = (outerX - innerX) * 0.5f;
            float topMargin = Mathf.Min(sideMargin, (outerY - innerY) * 0.5f);
            return (outerY * 0.5f) - topMargin - (innerY * 0.5f);
        }

        public static Mesh Torus(float innerRadius, float outerRadius, int majorSegments = 48, int minorSegments = 16)
        {
            if (majorSegments < 3)
            {
                majorSegments = 3;
            }

            if (minorSegments < 3)
            {
                minorSegments = 3;
            }

            string cacheKey = "torus:" + Exact(innerRadius) + ":" + Exact(outerRadius) + ":" + majorSegments + ":" + minorSegments;
            Mesh cached;
            if (Cache.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            float ringRadius = (outerRadius + innerRadius) * 0.5f;
            float tubeRadius = Mathf.Abs(outerRadius - innerRadius) * 0.5f;

            // One extra column and row duplicate the seam so the uv wraps
            // cleanly instead of running backwards across the last quad.
            int columns = majorSegments + 1;
            int rows = minorSegments + 1;

            Vector3[] vertices = new Vector3[columns * rows];
            Vector3[] normals = new Vector3[columns * rows];
            Vector2[] uvs = new Vector2[columns * rows];

            for (int i = 0; i < columns; i++)
            {
                float major = (i / (float)majorSegments) * Mathf.PI * 2f;
                float majorCos = Mathf.Cos(major);
                float majorSin = Mathf.Sin(major);

                for (int j = 0; j < rows; j++)
                {
                    float minor = (j / (float)minorSegments) * Mathf.PI * 2f;
                    float minorCos = Mathf.Cos(minor);
                    float minorSin = Mathf.Sin(minor);

                    // The surface normal of a torus is the unit vector from the
                    // point of the ring circle to the surface point, so the
                    // vertex is just that circle plus the normal times the tube
                    // radius. No RecalculateNormals needed.
                    Vector3 normal = new Vector3(majorCos * minorCos, minorSin, majorSin * minorCos);
                    Vector3 ringPoint = new Vector3(majorCos * ringRadius, 0f, majorSin * ringRadius);

                    int index = (i * rows) + j;
                    normals[index] = normal;
                    vertices[index] = ringPoint + (normal * tubeRadius);
                    uvs[index] = new Vector2(i / (float)majorSegments, j / (float)minorSegments);
                }
            }

            int[] triangles = new int[majorSegments * minorSegments * 6];
            int cursor = 0;
            for (int i = 0; i < majorSegments; i++)
            {
                for (int j = 0; j < minorSegments; j++)
                {
                    int a = (i * rows) + j;
                    int b = a + 1;
                    int c = a + rows;
                    int d = c + 1;

                    // This winding puts the front faces outward under Unity's
                    // clockwise convention (checked by hand at major = 0,
                    // minor = 0, where the normal must be +x).
                    triangles[cursor++] = a;
                    triangles[cursor++] = b;
                    triangles[cursor++] = c;
                    triangles[cursor++] = b;
                    triangles[cursor++] = d;
                    triangles[cursor++] = c;
                }
            }

            Mesh mesh = new Mesh();
            mesh.name = "Torus_" + Exact(innerRadius) + "_" + Exact(outerRadius);
            mesh.vertices = vertices;
            mesh.normals = normals;
            mesh.uv = uvs;
            mesh.triangles = triangles;
            mesh.RecalculateBounds();

            Cache[cacheKey] = mesh;
            return mesh;
        }

        /// <summary>
        /// Flat panel in the xy plane, used for the painted backdrop of a photo.
        /// Its normal is (0, 0, -1), like Unity's own Quad primitive: the
        /// backdrop sits in front of the eye along +z (design space -z after the
        /// mirror) and must face back at it.
        /// </summary>
        public static Mesh Quad(Vector2 size)
        {
            string cacheKey = "quad:" + Exact(size.x) + ":" + Exact(size.y);
            Mesh cached;
            if (Cache.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            float halfX = size.x * 0.5f;
            float halfY = size.y * 0.5f;

            Vector3[] vertices =
            {
                new Vector3(-halfX, -halfY, 0f),
                new Vector3(halfX, -halfY, 0f),
                new Vector3(-halfX, halfY, 0f),
                new Vector3(halfX, halfY, 0f),
            };

            Vector3 normal = new Vector3(0f, 0f, -1f);
            Vector3[] normals = { normal, normal, normal, normal };

            // v = 0 at the bottom, matching the backdrop gradient texture.
            Vector2[] uvs =
            {
                new Vector2(0f, 0f),
                new Vector2(1f, 0f),
                new Vector2(0f, 1f),
                new Vector2(1f, 1f),
            };

            int[] triangles = { 0, 2, 1, 2, 3, 1 };

            Mesh mesh = new Mesh();
            mesh.name = "Quad_" + Exact(size.x) + "x" + Exact(size.y);
            mesh.vertices = vertices;
            mesh.normals = normals;
            mesh.uv = uvs;
            mesh.triangles = triangles;
            mesh.RecalculateBounds();

            Cache[cacheKey] = mesh;
            return mesh;
        }

        /// <summary>
        /// Box centered on the origin, EXACTLY <paramref name="size"/> across
        /// its outer extents, with every edge chamfered: PRD_VISUAL 4.6
        /// V-GEO-01. It drops straight into the place a unit cube scaled by
        /// size used to occupy, and the box collider beside it is untouched -
        /// PRD_VISUAL 4.6 and its risk table both pin "colliders stay exact
        /// boxes; only the mesh bevels", and the physics stages of the PlayMode
        /// probe are what verify that.
        ///
        /// Why the mesh exists at all: a chamfer is the only cheap way to make
        /// a box stop reading as a primitive. It gives the light a narrow band
        /// at a third angle along every edge, which is also the geometry
        /// V-MAT-02 (edge wear) leans on to find the edges in the shader.
        ///
        /// Topology, per PRD_VISUAL Appendix A: 6 face quads, 12 edge strips,
        /// 8 corner patches. Normals are authored, not recalculated:
        ///   - the six faces carry their exact face normal, so a flat box stays
        ///     flat and a wall does not bend toward its own edges;
        ///   - the bevel band (strips plus corner patches) carries smooth
        ///     normals, shared between the strips and the patches that meet, so
        ///     the chamfer reads as one rounded band and not as twenty facets.
        /// Those two demands disagree at the face/bevel boundary, so every one
        /// of the 24 boundary points exists TWICE: once with the face normal,
        /// once with the bevel normal. That crease is the highlight line the
        /// item is asking for. RecalculateNormals would average the two back
        /// together and delete the whole effect, so it is never called here.
        ///
        /// A 1 x 1 x 1 at the default bevel comes out at 48 vertices and 44
        /// triangles.
        /// </summary>
        /// <param name="size">Outer extents. The mesh spans exactly this.</param>
        /// <param name="bevel">
        /// Requested chamfer width, clamped as described in the body: 2.5 cm by
        /// default, or 12 percent of the smallest dimension when that is
        /// smaller.
        /// </param>
        /// <param name="bevelTop">
        /// V-GEO-04's paved lip: a LARGER chamfer on the four edges that touch
        /// the top face. Default 0, which means "no lip, the top edges use the
        /// ordinary bevel like every other edge" - the item is opt-in.
        /// </param>
        public static Mesh BeveledBox(Vector3 size, float bevel = 0.025f, float bevelTop = 0f)
        {
            // Keyed on what the CALLER asked for, not on the clamped result:
            // the clamp is a pure function of these three, so two calls that
            // agree here can never want different meshes, and a caller reading
            // the key back sees the values it passed.
            //
            // QUANTISED TO A MILLIMETRE, and that is what keeps this cache
            // finite. The cache is static and never cleared on purpose (a live
            // renderer may still be sampling a mesh, so dropping one would
            // leave a hole in the world), which is safe only while the key
            // takes a bounded number of values. Level geometry is authored in
            // round numbers and would have been fine, but CARVE FRAGMENTS ARE
            // NOT: ErasableBlock.Decompose cuts a block at wherever the photo
            // frustum happened to fall, so fragment sizes are continuous and
            // every carve in a session would have added three to six permanent
            // meshes that nothing ever frees. A player who carves for an hour
            // would grow the cache without limit.
            //
            // A millimetre is far below what any of this is visible at (the
            // bevel itself is 25 mm) and it collapses the continuum into a grid
            // that repeats, so a level's worth of carving reuses meshes instead
            // of hoarding them. The mesh is still built at the EXACT size the
            // caller asked for; only the key is rounded, so a fragment is never
            // drawn at the wrong size, at worst it shares the mesh of a
            // fragment within a millimetre of it.
            string cacheKey = "beveledbox:" + Mm(size.x) + ":" + Mm(size.y) + ":" + Mm(size.z)
                + ":" + Mm(bevel) + ":" + Mm(bevelTop);
            Mesh cached;
            if (Cache.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            // A negative extent is a mirrored instance, not a smaller box: the
            // mesh is symmetric about the origin, so the magnitude is all that
            // matters here and the caller's transform keeps the mirror.
            float[] sizeAxis = { Mathf.Abs(size.x), Mathf.Abs(size.y), Mathf.Abs(size.z) };
            float[] half = { sizeAxis[0] * 0.5f, sizeAxis[1] * 0.5f, sizeAxis[2] * 0.5f };
            float smallest = Mathf.Min(sizeAxis[0], Mathf.Min(sizeAxis[1], sizeAxis[2]));

            // V-GEO-01's rule verbatim: 2.5 cm, or 12 percent of the smallest
            // dimension when that is smaller. The 12 percent is not decoration,
            // it is the safety clamp. Across the smallest axis two bevels face
            // each other, so together they eat 24 percent of it and the face
            // left between them can never close up or turn inside out. A 0.06 m
            // marker gets 7.2 mm, a 0.2 m platform slab gets 2.4 cm.
            float side = Mathf.Min(Mathf.Abs(bevel), 0.12f * smallest);
            if (!(side > 0f))
            {
                // Catches a negative product, a zero size and NaN in one test,
                // because every comparison with NaN is false.
                side = 0f;
            }

            // V-GEO-04 asks for 6 cm on a 20 cm slab, which is 30 percent of the
            // smallest dimension and so is deliberately outside the rule above.
            // It gets its own clamp, from the three ways it can actually break:
            //   - the side faces must keep a positive height, so the ordinary
            //     bevel at the bottom plus the lip at the top must fit inside
            //     the y size (0.9 leaves the face a tenth of the slab);
            //   - the top face must keep a positive width on both of its own
            //     axes, and it is inset by the lip on all four sides, so the
            //     lip must stay under half of each (0.45 leaves a margin).
            float top = Mathf.Abs(bevelTop);
            if (!(top > 0f))
            {
                top = 0f;
            }

            top = Mathf.Min(top, 0.9f * Mathf.Max(0f, sizeAxis[1] - side));
            top = Mathf.Min(top, 0.45f * sizeAxis[0]);
            top = Mathf.Min(top, 0.45f * sizeAxis[2]);

            // bevelTop = 0 means "the top edges are ordinary edges", NOT "the
            // top edges are sharp": the lip is an addition to V-GEO-01, never a
            // subtraction from it. Taking the max also keeps the three clamps
            // above satisfied, because the side bevel already passes all of
            // them by the 12 percent rule.
            top = Mathf.Max(side, top);

            // Everything collapsed (a zero size, or bevel = 0 asked for
            // explicitly). The 12 strips and 8 patches would all be zero-area,
            // so skip them and emit the plain box the caller is entitled to
            // rather than a mesh full of degenerate triangles. When only ONE of
            // the two widths is zero the full topology is still built: the
            // strips that lose their width become zero-area triangles, the GPU
            // drops them, and the normals are authored analytically so none of
            // them can go NaN. That is what makes bevel = 0 with bevelTop > 0 a
            // usable "chamfer the top only" box.
            bool bevelled = top > BevelEpsilon;

            // 8 corners times 3 faces = the 24 points where a face has a corner.
            // Each becomes a face vertex (hard normal) and, when bevelled, a
            // bevel vertex (smooth normal) at the very same position.
            int pointCount = 24;
            int vertexCount = bevelled ? (pointCount * 2) : pointCount;

            Vector3[] vertices = new Vector3[vertexCount];
            Vector3[] normals = new Vector3[vertexCount];
            Vector2[] uvs = new Vector2[vertexCount];

            int[] signs = new int[3];
            for (int corner = 0; corner < 8; corner++)
            {
                signs[0] = CornerSign(corner, 0);
                signs[1] = CornerSign(corner, 1);
                signs[2] = CornerSign(corner, 2);

                for (int face = 0; face < 3; face++)
                {
                    int inPlaneU = (face + 1) % 3;
                    int inPlaneV = (face + 2) % 3;

                    // On its own axis the point sits at the full extent: that is
                    // what makes the mesh exactly 'size' across, and what lets
                    // it replace a scaled unit cube without moving anything. On
                    // the other two it is pulled in by the bevel of the edge it
                    // shares with the face on that side, which is how one face
                    // can be inset by the lip along its top border and by the
                    // ordinary bevel along the other three.
                    Vector3 point = Vector3.zero;
                    point[face] = signs[face] * half[face];
                    point[inPlaneU] = signs[inPlaneU] * (half[inPlaneU] - BevelWidth(face, signs[face], inPlaneU, signs[inPlaneU], side, top));
                    point[inPlaneV] = signs[inPlaneV] * (half[inPlaneV] - BevelWidth(face, signs[face], inPlaneV, signs[inPlaneV], side, top));

                    // Viewpoint/Surface is triplanar from world position and
                    // reads neither uv nor tangent (PRD_VISUAL 4.5: "nothing
                    // depends on UVs"). These exist so the mesh is not a trap
                    // for anything that DOES expect a texture coordinate - a URP
                    // Lit or Unlit fallback material, a debug shader, the
                    // inspector preview - which would otherwise sample one texel
                    // over the whole box. They are a plain per-face mapping onto
                    // [0, 1], landing slightly inside it at the bevel.
                    float u = sizeAxis[inPlaneU] > 0f ? ((point[inPlaneU] + half[inPlaneU]) / sizeAxis[inPlaneU]) : 0.5f;
                    float v = sizeAxis[inPlaneV] > 0f ? ((point[inPlaneV] + half[inPlaneV]) / sizeAxis[inPlaneV]) : 0.5f;
                    Vector2 uv = new Vector2(u, v);

                    int point3 = (corner * 3) + face;
                    vertices[point3] = point;
                    normals[point3] = AxisNormal(face, signs[face]);
                    uvs[point3] = uv;

                    if (bevelled)
                    {
                        vertices[pointCount + point3] = point;
                        normals[pointCount + point3] = BevelNormal(face, signs);
                        uvs[pointCount + point3] = uv;
                    }
                }
            }

            // 6 quads + 12 quads + 8 triangles = 44 triangles when bevelled,
            // 6 quads = 12 triangles when not.
            int[] triangles = new int[bevelled ? (44 * 3) : (12 * 3)];
            int cursor = 0;

            // The winding rule used everywhere below, derived once and checked
            // against Quad above (whose declared normal is (0, 0, -1)): under
            // Unity's clockwise-from-the-front convention, a triangle
            // (v0, v1, v2) faces along Cross(v1 - v0, v2 - v0). So a quad wound
            // (-U, -V), (+U, -V), (+U, +V), (-U, +V) faces along Cross(U, V),
            // and picking U and V with Cross(U, V) = the outward normal is all
            // there is to it.
            for (int face = 0; face < 3; face++)
            {
                int axisU = (face + 1) % 3;
                int axisV = (face + 2) % 3;

                for (int s = 0; s < 2; s++)
                {
                    int faceSign = (s == 0) ? -1 : 1;

                    // Cross(e[face+1], e[face+2]) = e[face] by the cyclic
                    // identity, so the positive face takes U along face+1 and V
                    // along face+2; the negative face swaps them, because
                    // Cross(e[face+2], e[face+1]) = -e[face].
                    int quadU = (faceSign > 0) ? axisU : axisV;
                    int quadV = (faceSign > 0) ? axisV : axisU;

                    signs[face] = faceSign;

                    signs[quadU] = -1;
                    signs[quadV] = -1;
                    int q0 = (CornerIndex(signs) * 3) + face;

                    signs[quadU] = 1;
                    signs[quadV] = -1;
                    int q1 = (CornerIndex(signs) * 3) + face;

                    signs[quadU] = 1;
                    signs[quadV] = 1;
                    int q2 = (CornerIndex(signs) * 3) + face;

                    signs[quadU] = -1;
                    signs[quadV] = 1;
                    int q3 = (CornerIndex(signs) * 3) + face;

                    triangles[cursor++] = q0;
                    triangles[cursor++] = q1;
                    triangles[cursor++] = q2;
                    triangles[cursor++] = q0;
                    triangles[cursor++] = q2;
                    triangles[cursor++] = q3;
                }
            }

            if (bevelled)
            {
                // The 12 edge strips. An edge is named by the axis it runs
                // along plus the signs of the two faces it separates; taking
                // those two faces in cyclic order (edge+1, edge+2) turns the
                // winding into a one-line rule instead of twelve cases.
                //
                // Derivation. Let A and B be the two outward face normals and E
                // the edge axis. The strip faces along A + B and crosses the
                // chamfer along U = B - A, so V has to satisfy
                // Cross(B - A, V) proportional to A + B, with a POSITIVE factor.
                // With A = signA * e[faceA], B = signB * e[faceB] and the cyclic
                // identities, Cross(B - A, c * E) = c*signB * e[faceA]
                // + c*signA * e[faceB], which is a positive multiple of A + B
                // exactly when c = signA * signB. So the strip runs from
                // -signA*signB to +signA*signB along the edge axis.
                for (int edgeAxis = 0; edgeAxis < 3; edgeAxis++)
                {
                    int faceA = (edgeAxis + 1) % 3;
                    int faceB = (edgeAxis + 2) % 3;

                    for (int a = 0; a < 2; a++)
                    {
                        for (int b = 0; b < 2; b++)
                        {
                            int signA = (a == 0) ? -1 : 1;
                            int signB = (b == 0) ? -1 : 1;
                            int along = signA * signB;

                            signs[faceA] = signA;
                            signs[faceB] = signB;

                            signs[edgeAxis] = -along;
                            int nearCorner = CornerIndex(signs);
                            signs[edgeAxis] = along;
                            int farCorner = CornerIndex(signs);

                            int q0 = pointCount + (nearCorner * 3) + faceA;
                            int q1 = pointCount + (nearCorner * 3) + faceB;
                            int q2 = pointCount + (farCorner * 3) + faceB;
                            int q3 = pointCount + (farCorner * 3) + faceA;

                            triangles[cursor++] = q0;
                            triangles[cursor++] = q1;
                            triangles[cursor++] = q2;
                            triangles[cursor++] = q0;
                            triangles[cursor++] = q2;
                            triangles[cursor++] = q3;
                        }
                    }
                }

                // The 8 corner patches: one triangle joining the three bevel
                // points of a corner, one point per face that meets there.
                //
                // Checked by hand at the corner (+x, +y, +z) of a 1 x 1 x 1 at
                // the default bevel b = 0.025, whose three points are
                //   Px = (0.5, 0.475, 0.475)
                //   Py = (0.475, 0.5, 0.475)
                //   Pz = (0.475, 0.475, 0.5)
                // Cross(Py - Px, Pz - Px) = Cross((-b, b, 0), (-b, 0, b))
                //                         = (b*b, b*b, b*b),
                // which points along (1, 1, 1): outward, so (Px, Py, Pz) is the
                // right order there. Flipping any single sign mirrors the corner
                // and reverses its orientation, so a corner with an odd number
                // of negative signs takes (Px, Pz, Py) instead.
                for (int corner = 0; corner < 8; corner++)
                {
                    int parity = CornerSign(corner, 0) * CornerSign(corner, 1) * CornerSign(corner, 2);
                    int px = pointCount + (corner * 3);
                    int py = px + 1;
                    int pz = px + 2;

                    triangles[cursor++] = px;
                    triangles[cursor++] = (parity > 0) ? py : pz;
                    triangles[cursor++] = (parity > 0) ? pz : py;
                }
            }

            Mesh mesh = new Mesh();
            mesh.name = "BeveledBox_" + Exact(size.x) + "x" + Exact(size.y) + "x" + Exact(size.z)
                + "_b" + Exact(bevel) + "_t" + Exact(bevelTop);
            mesh.vertices = vertices;
            mesh.normals = normals;
            mesh.uv = uvs;
            mesh.triangles = triangles;

            // Bounds only. RecalculateNormals here would be the bug: it averages
            // per position, so it would merge every hard face normal back into
            // the bevel band those vertices were duplicated to stay out of, and
            // the chamfer would stop catching the light at all.
            mesh.RecalculateBounds();

            Cache[cacheKey] = mesh;
            return mesh;
        }

        /// <summary>
        /// Capped cylinder along +y, centered on the origin: the round bar that
        /// PRD_VISUAL 4.6 V-GEO-05 wants in place of the cage's square ones, and
        /// the body of the battery of V-PROP-01. Collision is unaffected in both
        /// cases (the cage collides with its wall boxes, not with its bars).
        ///
        /// The wall carries smooth radial normals so the bar reads as round at
        /// 10 sides; the two caps carry their own hard +y / -y normals, from
        /// their own copy of the ring, so the rim stays a rim.
        /// </summary>
        public static Mesh Rod(float radius, float height, int sides = 10)
        {
            if (sides < 3)
            {
                sides = 3;
            }

            string cacheKey = "rod:" + Exact(radius) + ":" + Exact(height) + ":" + sides;
            Mesh cached;
            if (Cache.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            float r = Mathf.Abs(radius);
            float halfHeight = Mathf.Abs(height) * 0.5f;

            // The wall gets one extra column so the uv seam duplicates instead
            // of running backwards over the last quad, exactly as Torus does.
            int wallColumns = sides + 1;
            int wallBottom = 0;
            int wallTop = wallColumns;
            int topRing = wallColumns * 2;
            int topCenter = topRing + sides;
            int bottomRing = topCenter + 1;
            int bottomCenter = bottomRing + sides;

            Vector3[] vertices = new Vector3[bottomCenter + 1];
            Vector3[] normals = new Vector3[bottomCenter + 1];
            Vector2[] uvs = new Vector2[bottomCenter + 1];

            for (int i = 0; i < wallColumns; i++)
            {
                float angle = (i / (float)sides) * Mathf.PI * 2f;
                float cos = Mathf.Cos(angle);
                float sin = Mathf.Sin(angle);
                Vector3 radial = new Vector3(cos, 0f, sin);

                vertices[wallBottom + i] = new Vector3(cos * r, -halfHeight, sin * r);
                vertices[wallTop + i] = new Vector3(cos * r, halfHeight, sin * r);
                normals[wallBottom + i] = radial;
                normals[wallTop + i] = radial;
                uvs[wallBottom + i] = new Vector2(i / (float)sides, 0f);
                uvs[wallTop + i] = new Vector2(i / (float)sides, 1f);

                if (i < sides)
                {
                    // The caps repeat the ring rather than sharing it: a shared
                    // vertex could only carry one normal, and a rod whose rim is
                    // smoothed into its own cap looks inflated.
                    vertices[topRing + i] = new Vector3(cos * r, halfHeight, sin * r);
                    normals[topRing + i] = Vector3.up;
                    uvs[topRing + i] = new Vector2(0.5f + (cos * 0.5f), 0.5f + (sin * 0.5f));

                    vertices[bottomRing + i] = new Vector3(cos * r, -halfHeight, sin * r);
                    normals[bottomRing + i] = Vector3.down;
                    uvs[bottomRing + i] = new Vector2(0.5f + (cos * 0.5f), 0.5f - (sin * 0.5f));
                }
            }

            vertices[topCenter] = new Vector3(0f, halfHeight, 0f);
            normals[topCenter] = Vector3.up;
            uvs[topCenter] = new Vector2(0.5f, 0.5f);

            vertices[bottomCenter] = new Vector3(0f, -halfHeight, 0f);
            normals[bottomCenter] = Vector3.down;
            uvs[bottomCenter] = new Vector2(0.5f, 0.5f);

            int[] triangles = new int[sides * 4 * 3];
            int cursor = 0;
            for (int i = 0; i < sides; i++)
            {
                int next = i + 1;

                // Checked by hand at i = 0 with 4 sides, where the quad runs from
                // (r, y, 0) to (0, y, r): Cross(top0 - bottom0, top1 - bottom0)
                // = Cross((0, 2h, 0), (-r, 2h, r)) = (2h*r, 0, 2h*r), which
                // points outward between those two columns. Going the other way
                // round the quad would light the inside of the bar.
                triangles[cursor++] = wallBottom + i;
                triangles[cursor++] = wallTop + i;
                triangles[cursor++] = wallTop + next;
                triangles[cursor++] = wallBottom + i;
                triangles[cursor++] = wallTop + next;
                triangles[cursor++] = wallBottom + next;

                int ringNext = (i + 1) % sides;

                // The two fans wind opposite ways because their normals do: with
                // x before z, Cross(ring0 - center, ring1 - center) points at -y,
                // so the top cap walks its ring backwards and the bottom cap
                // walks it forwards.
                triangles[cursor++] = topCenter;
                triangles[cursor++] = topRing + ringNext;
                triangles[cursor++] = topRing + i;

                triangles[cursor++] = bottomCenter;
                triangles[cursor++] = bottomRing + i;
                triangles[cursor++] = bottomRing + ringNext;
            }

            Mesh mesh = new Mesh();
            mesh.name = "Rod_" + Exact(radius) + "_" + Exact(height) + "_" + sides;
            mesh.vertices = vertices;
            mesh.normals = normals;
            mesh.uv = uvs;
            mesh.triangles = triangles;
            mesh.RecalculateBounds();

            Cache[cacheKey] = mesh;
            return mesh;
        }

        /// <summary>
        /// Drops every cached mesh so the next call rebuilds one. Used by the
        /// tests. The meshes themselves are not destroyed: a renderer somewhere
        /// may still be pointing at one.
        /// </summary>
        public static void ClearCache()
        {
            Cache.Clear();
        }

        // The outward normal of one of the six faces: the unit vector along
        // 'axis' (0 = x, 1 = y, 2 = z) with the given sign.
        private static Vector3 AxisNormal(int axis, int sign)
        {
            Vector3 normal = Vector3.zero;
            normal[axis] = sign;
            return normal;
        }

        // The smooth normal carried by a bevel-band vertex. The point belongs to
        // face 'face', and three pieces of the band meet there: the two edge
        // strips that leave that face along its two in-plane axes, and the
        // corner patch. Averaging those three unit normals is what makes the
        // band shade as one surface along a strip AND across the patch at its
        // end. The result leans toward the face it came from, so the pair of
        // vertices facing each other across a strip straddle the true chamfer
        // normal and the highlight lands in the middle of the band instead of on
        // one of its lips.
        private static Vector3 BevelNormal(int face, int[] signs)
        {
            int axisU = (face + 1) % 3;
            int axisV = (face + 2) % 3;

            Vector3 onFace = AxisNormal(face, signs[face]);
            Vector3 onU = AxisNormal(axisU, signs[axisU]);
            Vector3 onV = AxisNormal(axisV, signs[axisV]);

            Vector3 sum = (onFace + onU).normalized
                + (onFace + onV).normalized
                + (onFace + onU + onV).normalized;
            return sum.normalized;
        }

        // Width of the chamfer between face (faceAxis, faceSign) and the face
        // (otherAxis, otherSign) beside it. V-GEO-04's lip belongs to the four
        // edges that touch the top face, so an edge is a top edge as soon as
        // either of the two faces it separates is +y - which is what lets one
        // side face be inset by the lip along its upper border and by the
        // ordinary bevel along the other three.
        private static float BevelWidth(int faceAxis, int faceSign, int otherAxis, int otherSign, float side, float top)
        {
            bool touchesTop = (faceAxis == 1 && faceSign > 0) || (otherAxis == 1 && otherSign > 0);
            return touchesTop ? top : side;
        }

        // Corners are numbered by their three signs, x in the high bit, so a
        // number and a sign triple convert both ways without a table.
        private static int CornerSign(int corner, int axis)
        {
            return ((corner & (1 << (2 - axis))) != 0) ? 1 : -1;
        }

        private static int CornerIndex(int[] signs)
        {
            return (signs[0] > 0 ? 4 : 0) | (signs[1] > 0 ? 2 : 0) | (signs[2] > 0 ? 1 : 0);
        }

        // Round trip formatting under the invariant culture: a cache key must
        // not change with the machine's decimal separator, and two sizes that
        // differ in the last bit must not collide.
        private static string Exact(float value)
        {
            return value.ToString("R", CultureInfo.InvariantCulture);
        }

        /// <summary>
        /// A cache key quantised to the millimetre, for meshes whose size comes
        /// from gameplay rather than from authored data.
        ///
        /// <see cref="Exact"/> is the right key for anything built from level
        /// data, because those numbers are authored and repeat. It is the WRONG
        /// key for a carve fragment: ErasableBlock cuts a block wherever the
        /// photo frustum fell, so fragment sizes form a continuum and an exact
        /// key makes every single carve add permanent entries to a cache that is
        /// never cleared. An integer count of millimetres collapses that
        /// continuum onto a grid, so carving reuses meshes instead of hoarding
        /// them, and a millimetre is two orders of magnitude below the 25 mm
        /// bevel it describes.
        ///
        /// Integer formatting, so there is no decimal separator to vary with the
        /// machine's culture.
        /// </summary>
        private static string Mm(float value)
        {
            return Mathf.RoundToInt(value * 1000f).ToString(CultureInfo.InvariantCulture);
        }
    }
}
