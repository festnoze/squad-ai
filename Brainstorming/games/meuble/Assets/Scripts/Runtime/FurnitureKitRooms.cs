using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// M8 room variety (docs/m8/ROOMS_PLAN.md 3): the ten room objects, static props built from boxes like the M2 ones.
    /// <list type="bullet">
    /// <item>Gameplay: every collider is a collider-only object on the prop's layer, built whether the prop shows this
    /// procedural visual or a catalog model (M3), and only when the level sets <see cref="PropDef.Occluder"/>. The colliders
    /// follow the solid body (the worktop, the basin, the rim, never a tap or the mirror on the wall); the bed builds exactly
    /// the colliders of a sofa of its size (the M2 beds are sofas named "Lit").</item>
    /// <item>Facing: the front is on local -z (doors, oven, the foot of the bed), the back on +z against a wall, as the
    /// sofa's backrest and the cabinet's doors; every part stays inside the box.</item>
    /// <item>Look: the parts combine into one renderer per material (as the bookshelf, CONTRACT_M5 17). Every kind adds at most
    /// one material: white ceramic (<see cref="CeramicMaterial"/>, plain, shared by the bathroom, the stove and the fridge);
    /// everything else reuses a surface the levels already draw (Wood, Plaster, Linen, Upholstery, Metal) or the near-black
    /// of the household (<see cref="DarkMaterial"/>: screens, the oven window, the hob). Never red. At most 216 triangles.</item>
    /// <item>M9 soft shapes: the bed, the bathtub, the washbasin, the toilet, the kitchen sink, the stove and the fridge draw
    /// their main parts as rounded meshes (<see cref="RoundedMesh"/>: rounded corners and edges, an oval tub and bowls, soft
    /// pillows), in the same groups, so with the same renderers and materials; their colliders are unchanged. Each stays
    /// within the furniture budget of 400 triangles (Tuning.BudgetFurnitureTriangles).</item>
    /// </list>
    /// </summary>
    public static partial class FurnitureKit
    {
        /// <summary>The white of the ceramic, the enamel and the fridge (sRGB): cool and slightly off white, never pure white.</summary>
        public static readonly Color CeramicColor = new Color32(0xEE, 0xF1, 0xF2, 0xFF);

        /// <summary>Glazed ceramic is glossy.</summary>
        public const float CeramicSmoothness = 0.7f;

        /// <summary>
        /// The plain material of <see cref="CeramicColor"/> (no detail: glaze shows no grain). ModelKit paints the Kenney
        /// "metalLight" slots with it too, so a model and a procedural room object share it.
        /// </summary>
        public static Material CeramicMaterial => PrimitiveKit.Lit(CeramicColor, CeramicSmoothness);

        /// <summary>
        /// The plain near-black of every model of the household (ModelMath.NearBlack at the models' smoothness, the material
        /// ModelKit gives their dark slots): screens, the oven window, the hob, a mirror frame. No new material in a level
        /// with a Quaternius inhabitant.
        /// </summary>
        public static Material DarkMaterial => PrimitiveKit.Lit(FrameColor, Tuning.ModelSmoothness);

        /// <summary>
        /// Builds an M8 room object (<see cref="PropKinds.RoomObjects"/>) under <paramref name="parent"/>; false for any other
        /// kind (nothing built). <paramref name="visual"/> false builds the colliders only (a catalog model is the visual).
        /// </summary>
        private static bool RoomObject(PropDef prop, Transform parent, int layer, bool visual, bool combine)
        {
            if (string.IsNullOrEmpty(prop.Kind) || System.Array.IndexOf(PropKinds.RoomObjects, prop.Kind) < 0)
            {
                return false;
            }
            Vector3 s = prop.Size;
            Color main = LevelJson.ParseColor(prop.Color, Color.gray);
            Color accent = AccentOf(prop);
            var parts = new PartBatch(parent, layer, combine && visual);
            var k = new RoomKit(parent, parts, layer, prop.Occluder, visual, main, accent);
            switch (prop.Kind)
            {
                case PropKinds.Bathtub:
                    Bathtub(k, s);
                    break;
                case PropKinds.Washbasin:
                    Washbasin(k, s);
                    break;
                case PropKinds.Toilet:
                    Toilet(k, s);
                    break;
                case PropKinds.KitchenSink:
                    KitchenSink(k, s);
                    break;
                case PropKinds.Stove:
                    Stove(k, s);
                    break;
                case PropKinds.Fridge:
                    Fridge(k, s);
                    break;
                case PropKinds.CoffeeTable:
                    CoffeeTable(k, s);
                    break;
                case PropKinds.TvUnit:
                    TvUnit(k, s);
                    break;
                case PropKinds.Bed:
                    // Gameplay first: exactly the colliders of a sofa of this size, collider-only whatever the visual.
                    Sofa(parent, s, main, accent, layer, prop.Occluder, false);
                    Bed(k, s);
                    break;
                case PropKinds.Nightstand:
                    Nightstand(k, s);
                    break;
            }
            parts.Flush();
            return true;
        }

        /// <summary>The parts of one room object: its materials by surface, its batch and its colliders.</summary>
        private sealed class RoomKit
        {
            private readonly Transform parent;
            private readonly PartBatch parts;
            private readonly int layer;
            private readonly bool collide;
            private readonly bool visual;
            private readonly Material wood;
            private readonly Material plaster;
            private readonly Material linen;
            private readonly Material upholstery;
            private readonly Material ceramic;
            private readonly Material dark;
            private readonly Material metal;

            public RoomKit(Transform parent, PartBatch parts, int layer, bool collide, bool visual, Color main, Color accent)
            {
                this.parent = parent;
                this.parts = parts;
                this.layer = layer;
                this.collide = collide;
                this.visual = visual;
                // One palette material per textured surface (M7 real colours: the surface's image shows, whatever the
                // palette), so each surface is one renderer of the prop.
                wood = Mat(main, 0.25f, visual);
                upholstery = Mat(main, 0.15f, visual);
                plaster = Mat(accent, 0.5f, visual);
                linen = Mat(accent, 0.1f, visual);
                ceramic = visual ? CeramicMaterial : null;
                dark = visual ? DarkMaterial : null;
                // M6 (CONTRACT_M6 2.4): metal is always the frame's Metal, as the floor lamp's pole.
                metal = visual ? PrimitiveKit.LitSurface(FrameColor, Surface.Metal) : null;
            }

            public void Wood(string name, Vector3 center, Vector3 size) => parts.Box(name, "Wood", center, size, wood, visual, Surface.Wood);

            public void Plaster(string name, Vector3 center, Vector3 size) => parts.Box(name, "Worktop", center, size, plaster, visual, Surface.Plaster);

            public void Linen(string name, Vector3 center, Vector3 size) => parts.Box(name, "Linen", center, size, linen, visual, Surface.Linen);

            public void Upholstery(string name, Vector3 center, Vector3 size) => parts.Box(name, "Duvet", center, size, upholstery, visual, Surface.Upholstery);

            public void Ceramic(string name, Vector3 center, Vector3 size) => parts.Box(name, "Ceramic", center, size, ceramic, visual, Surface.Plain);

            public void Dark(string name, Vector3 center, Vector3 size) => parts.Box(name, "Dark", center, size, dark, visual, Surface.Plain);

            public void Metal(string name, Vector3 center, Vector3 size) => parts.Box(name, "Metal", center, size, metal, visual, Surface.Metal);

            // M9 soft shapes: the same surfaces (same groups, so the same renderers) drawn by a RoundedMesh placed at `at`,
            // turned by `turn` (a panel facing -z is a slab turned by Facing).
            public void Wood(string name, Mesh mesh, Vector3 at) => parts.Shape(name, "Wood", mesh, at, Quaternion.identity, wood, visual, Surface.Wood);

            public void Plaster(string name, Mesh mesh, Vector3 at) => parts.Shape(name, "Worktop", mesh, at, Quaternion.identity, plaster, visual, Surface.Plaster);

            public void Linen(string name, Mesh mesh, Vector3 at) => parts.Shape(name, "Linen", mesh, at, Quaternion.identity, linen, visual, Surface.Linen);

            public void Upholstery(string name, Mesh mesh, Vector3 at) => parts.Shape(name, "Duvet", mesh, at, Quaternion.identity, upholstery, visual, Surface.Upholstery);

            public void Ceramic(string name, Mesh mesh, Vector3 at) => Ceramic(name, mesh, at, Quaternion.identity);

            public void Ceramic(string name, Mesh mesh, Vector3 at, Quaternion turn) => parts.Shape(name, "Ceramic", mesh, at, turn, ceramic, visual, Surface.Plain);

            public void Dark(string name, Mesh mesh, Vector3 at) => Dark(name, mesh, at, Quaternion.identity);

            public void Dark(string name, Mesh mesh, Vector3 at, Quaternion turn) => parts.Shape(name, "Dark", mesh, at, turn, dark, visual, Surface.Plain);

            public void Metal(string name, Mesh mesh, Vector3 at) => Metal(name, mesh, at, Quaternion.identity);

            public void Metal(string name, Mesh mesh, Vector3 at, Quaternion turn) => parts.Shape(name, "Metal", mesh, at, turn, metal, visual, Surface.Metal);

            /// <summary>A collider-only box on the prop's layer, when the level makes the prop an occluder.</summary>
            public void Solid(string name, Vector3 center, Vector3 size)
            {
                if (!collide)
                {
                    return;
                }
                var go = new GameObject(name) { layer = layer };
                go.transform.SetParent(parent, false);
                var box = go.AddComponent<BoxCollider>();
                box.center = center;
                box.size = size;
            }
        }

        /// <summary>
        /// A built-in bathtub along x: one ceramic shell (M9: rounded outer corners, the rim rolled over into an oval basin
        /// with a rounded bottom), the mixer (spout and two handles) lying on the back rim at the +x end. Solid up to its rim.
        /// 374 triangles.
        /// </summary>
        private static void Bathtub(RoomKit k, Vector3 s)
        {
            float spout = Mathf.Min(0.045f, s.y * 0.1f);
            float rim = s.y - spout;
            float wall = Mathf.Clamp(Mathf.Min(s.x, s.z) * 0.1f, 0.04f, 0.09f);
            float floor = Mathf.Min(0.12f, rim * 0.25f);
            float innerX = s.x - 2f * wall;
            float innerZ = s.z - 2f * wall;
            k.Ceramic("Tub", TubMesh(s, rim, wall, floor), Vector3.zero);
            float x = s.x * 0.5f - wall - Mathf.Min(0.18f, innerX * 0.2f);
            float back = s.z * 0.5f - wall * 0.25f;
            float length = wall * 0.75f + Mathf.Min(0.16f, innerZ * 0.35f);
            k.Metal("Spout", new Vector3(x, rim + spout * 0.5f, back - length * 0.5f), new Vector3(0.05f, spout, length));
            float handleZ = s.z * 0.5f - wall * 0.5f;
            k.Metal("HandleL", new Vector3(x - 0.09f, rim + spout * 0.4f, handleZ), new Vector3(0.04f, spout * 0.8f, 0.04f));
            k.Metal("HandleR", new Vector3(x + 0.09f, rim + spout * 0.4f, handleZ), new Vector3(0.04f, spout * 0.8f, 0.04f));
            k.Solid("Collider", new Vector3(0f, rim * 0.5f, 0f), new Vector3(s.x, rim, s.z));
        }

        /// <summary>A slab built by RoundedMesh along +y, turned to stand as a panel facing -z (its +y), its +z up.</summary>
        private static readonly Quaternion Facing = Quaternion.Euler(-90f, 0f, 0f);

        /// <summary>
        /// The bathtub's shell (M9): the outer walls (corners rounded in plan), the rim rolled over in a half circle of half the
        /// wall, the inner wall leaning in down to a rounded bottom and the basin floor at <paramref name="floor"/>. The
        /// basin is almost a stadium in plan (an oval), the outside a rounded rectangle; the rim blends one into the other.
        /// </summary>
        private static Mesh TubMesh(Vector3 s, float rim, float wall, float floor)
        {
            float hx = s.x * 0.5f;
            float hz = s.z * 0.5f;
            float outer = Mathf.Min(0.12f, Mathf.Min(hx, hz) * 0.4f);
            float lip = wall * 0.5f;
            float slope = Mathf.Min(0.04f, (hz - wall) * 0.2f);
            float bottom = Mathf.Max(0.01f, Mathf.Min(0.07f, (rim - lip - floor) * 0.4f));
            float Oval(float inset) => 0.92f * Mathf.Min(hx - inset, hz - inset);
            var rings = new List<RoundedMesh.Ring> { RoundedMesh.At(hx, hz, 0f, outer, 1f, 0f) };
            for (int i = 0; i <= 4; i++)
            {
                float t = i / 4f;
                float theta = 180f * t * Mathf.Deg2Rad;
                float inset = lip - lip * Mathf.Cos(theta);
                float radius = Mathf.Lerp(Mathf.Max(outer - inset, 0.02f), Oval(inset), t);
                rings.Add(RoundedMesh.At(hx - inset, hz - inset, rim - lip + lip * Mathf.Sin(theta), radius, Mathf.Cos(theta), Mathf.Sin(theta)));
            }
            // The inner wall leans in a little, down to the bottom's quarter circle (concave: its normal points at its centre).
            float a = wall + slope;
            Vector2 wallNormal = new Vector2(-(rim - lip - floor - bottom), slope).normalized;
            for (int i = 0; i <= 2; i++)
            {
                float alpha = -45f * i * Mathf.Deg2Rad;
                float inset = a + bottom - bottom * Mathf.Cos(alpha);
                Vector2 n = i == 0 ? wallNormal : new Vector2(-Mathf.Cos(alpha), -Mathf.Sin(alpha));
                rings.Add(RoundedMesh.At(hx - inset, hz - inset, floor + bottom + bottom * Mathf.Sin(alpha), Oval(inset), n.x, n.y));
            }
            return RoundedMesh.Sweep(rings, 4, false, true);
        }

        /// <summary>
        /// A washbasin: a wooden vanity with two doors, a ceramic basin block hollowed by its bowl (a deck at the back carries
        /// the tap), and, when the box is at least 1.3 m tall, a mirror in a dark frame against the wall above (basin top at
        /// 0.85 m). Solid up to the basin top; the mirror has no collider and its frame stands on the back deck (M7 walls pass:
        /// once the wall behind it is lowered, it never hangs in mid-air). M9: a rounded vanity, a rounded basin block with an
        /// oval bowl, a rounded mirror. 378 triangles.
        /// </summary>
        private static void Washbasin(RoomKit k, Vector3 s)
        {
            const float tap = 0.12f;
            const float bowl = 0.16f;
            bool mirror = s.y >= 1.3f;
            float top = mirror ? Mathf.Min(0.85f, s.y * 0.5f) : Mathf.Max(bowl + 0.1f, s.y - tap);
            float wall = Mathf.Clamp(Mathf.Min(s.x, s.z) * 0.12f, 0.03f, 0.06f);
            float deck = Mathf.Min(wall + 0.07f, s.z * 0.35f);
            float cabinet = top - bowl;

            // The vanity's walls only: the basin block covers its top.
            k.Wood("Vanity", RoundedMesh.Slab(new Vector3(s.x - 0.04f, cabinet, s.z - 0.04f), 0.03f, 0f, 0, 0f, 0, 2, false, false), new Vector3(0f, 0f, 0.02f));
            float doorW = (s.x - 0.04f) * 0.5f - 0.02f;
            float doorH = Mathf.Max(0.05f, cabinet - 0.1f);
            float doorZ = -s.z * 0.5f + 0.04f - 0.0075f;
            for (int i = 0; i < 2; i++)
            {
                float x = (i == 0 ? -1f : 1f) * (doorW * 0.5f + 0.01f);
                k.Wood("Door" + i, new Vector3(x, 0.06f + doorH * 0.5f, doorZ), new Vector3(doorW, doorH, 0.015f));
            }
            // Handles (2026-11-19): a brushed pull on each door, in the tap's Metal renderer (16 triangles).
            Handles.Pulls(k.Metal, doorW, 0.01f, 0.06f, 0.06f + doorH, doorZ - 0.0075f, -1f);

            float innerZ = s.z - wall - deck;
            float zIn = (wall - deck) * 0.5f;
            k.Ceramic("Basin", BasinMesh(s, top, bowl, wall, innerZ, zIn), Vector3.zero);

            float postZ = s.z * 0.5f - deck * 0.5f;
            k.Metal("TapPost", new Vector3(0f, top + tap * 0.5f, postZ), new Vector3(0.035f, tap, 0.035f));
            k.Metal("TapSpout", new Vector3(0f, top + tap - 0.015f, postZ - 0.05f), new Vector3(0.03f, 0.03f, 0.12f));

            // The frame (0.02 m wider than the mirror all round) rests on the back deck.
            float mirrorBottom = top + 0.02f;
            float mirrorTop = s.y - 0.05f;
            if (mirror && mirrorTop - mirrorBottom > 0.2f)
            {
                float width = s.x * 0.85f;
                float h = mirrorTop - mirrorBottom;
                float my = (mirrorBottom + mirrorTop) * 0.5f;
                // M9: rounded panels against the wall (their back at the box's back), the mirror proud of its frame.
                k.Dark("MirrorFrame", RoundedMesh.Slab(new Vector3(width + 0.04f, 0.016f, h + 0.04f), 0.07f, 0f, 0, 0f, 0, 2, false, true),
                    new Vector3(0f, my, s.z * 0.5f), Facing);
                k.Metal("Mirror", RoundedMesh.Slab(new Vector3(width, 0.01f, h), 0.05f, 0f, 0, 0f, 0, 2, false, true),
                    new Vector3(0f, my, s.z * 0.5f - 0.016f), Facing);
            }
            k.Solid("Collider", new Vector3(0f, top * 0.5f, 0f), new Vector3(s.x, top, s.z));
        }

        /// <summary>
        /// The washbasin's ceramic block (M9): rounded corners and top edge, a flat deck (the tap stands on its back part), then
        /// the bowl, an oval rolled in at its edge and sinking as a half ellipsoid to a small flat drain, as deep as the boxes'
        /// bowl was (its floor a quarter of <paramref name="bowl"/> above the block's bottom).
        /// </summary>
        private static Mesh BasinMesh(Vector3 s, float top, float bowl, float wall, float innerZ, float zIn)
        {
            float hx = s.x * 0.5f;
            float hz = s.z * 0.5f;
            float corner = Mathf.Min(0.06f, Mathf.Min(hx, hz) * 0.35f);
            float roll = Mathf.Min(0.025f, bowl * 0.2f);
            float bx = hx - wall;
            float bz = innerZ * 0.5f;
            float lip = Mathf.Min(0.012f, Mathf.Min(bx, bz) * 0.2f);
            float depth = bowl * 0.75f - lip;
            float oval = Mathf.Min(bx, bz);
            var rings = new List<RoundedMesh.Ring>
            {
                RoundedMesh.At(hx, hz, top - bowl, corner, 1f, 0f),
                RoundedMesh.At(hx, hz, top - roll, corner, 1f, 0f),
                RoundedMesh.At(hx - roll, hz - roll, top, Mathf.Max(corner - roll, corner * 0.5f), 0f, 1f),
                RoundedMesh.At(bx, bz, 0f, zIn, top, oval, 0f, 1f),
                RoundedMesh.At(bx - lip, bz - lip, 0f, zIn, top - lip, oval - lip, -0.7071f, 0.7071f),
            };
            const float drain = 0.2f;
            float across = 0.5f * (bx + bz) - lip;
            foreach (float degrees in new[] { 35f, 65f, 90f })
            {
                float phi = degrees * Mathf.Deg2Rad;
                float scale = drain + (1f - drain) * Mathf.Cos(phi);
                Vector2 n = new Vector2(-Mathf.Cos(phi) / across, Mathf.Sin(phi) / depth).normalized;
                rings.Add(RoundedMesh.At((bx - lip) * scale, (bz - lip) * scale, 0f, zIn, top - lip - depth * Mathf.Sin(phi), (oval - lip) * scale, n.x, n.y));
            }
            return RoundedMesh.Sweep(rings, 3, false, true);
        }

        /// <summary>
        /// A toilet: the cistern on the back up to the top (a metal flush button on it), the bowl on its foot, the closed lid
        /// at 0.42 m. Solid up to the lid over the whole footprint, and the cistern up to the top. M9: a rounded cistern, and
        /// the foot, the oval bowl and the lid as one soft shape. 344 triangles.
        /// </summary>
        private static void Toilet(RoomKit k, Vector3 s)
        {
            const float button = 0.012f;
            const float lid = 0.04f;
            float seat = Mathf.Min(0.42f, s.y * 0.55f);
            float tankD = Mathf.Min(0.2f, s.z * 0.3f);
            float tankBottom = seat - 0.05f;
            float tankTop = s.y - button;
            float zTank = s.z * 0.5f - tankD * 0.5f;
            k.Ceramic("Cistern", RoundedMesh.Slab(new Vector3(s.x, tankTop - tankBottom, tankD), Mathf.Min(0.05f, tankD * 0.3f), 0f, 0,
                Mathf.Min(0.035f, tankD * 0.25f), 1, 2, false, true), new Vector3(0f, tankBottom, zTank));
            k.Metal("Flush", new Vector3(0f, s.y - button * 0.5f, zTank), new Vector3(Mathf.Min(0.07f, s.x * 0.2f), button, Mathf.Min(0.05f, tankD * 0.3f)));

            float bowlBack = s.z * 0.5f - tankD + 0.03f;
            float bowlD = bowlBack + s.z * 0.5f;
            float zBowl = (bowlBack - s.z * 0.5f) * 0.5f;
            float bowlTop = seat - lid;
            float rimH = Mathf.Min(0.16f, bowlTop * 0.45f);
            k.Ceramic("Bowl", ToiletMesh(s, seat, lid, bowlTop, rimH, bowlD, zBowl), Vector3.zero);
            k.Solid("Base", new Vector3(0f, seat * 0.5f, 0f), new Vector3(s.x, seat, s.z));
            k.Solid("Cistern", new Vector3(0f, s.y * 0.5f, zTank), new Vector3(s.x, s.y, tankD));
        }

        /// <summary>
        /// The toilet below its cistern as one shape (M9), every ring an oval in plan: the foot (its base a little wider) up
        /// to the bowl's flared underside, the bowl at its widest, its top under the lid, then the lid (wider than the bowl,
        /// its underside, its rounded edge and its top at <paramref name="seat"/>). The parts keep the boxes' extents.
        /// </summary>
        private static Mesh ToiletMesh(Vector3 s, float seat, float lid, float bowlTop, float rimH, float bowlD, float zBowl)
        {
            float footX = s.x * 0.55f * 0.5f;
            float footZ = bowlD * 0.62f * 0.5f;
            float footC = zBowl + bowlD * 0.12f;
            float bowlX = s.x * 0.86f * 0.5f;
            float bowlZ = (bowlD - 0.03f) * 0.5f;
            float bowlC = zBowl + 0.015f;
            float lidX = s.x * 0.94f * 0.5f;
            float lidZ = (bowlD - 0.01f) * 0.5f;
            float lidC = zBowl - 0.005f;
            float under = bowlTop - rimH;
            float edge = Mathf.Min(0.015f, lid * 0.4f);
            RoundedMesh.Ring Oval(float hx, float hz, float c, float y, float nOut, float nUp) =>
                RoundedMesh.At(hx, hz, 0f, c, y, 0.95f * Mathf.Min(hx, hz), nOut, nUp);
            var rings = new List<RoundedMesh.Ring>
            {
                Oval(footX * 1.08f, footZ * 1.04f, footC, 0f, 0.97f, 0.25f),
                Oval(footX * 0.94f, footZ * 0.97f, footC, under * 0.6f, 1f, 0.05f),
                Oval(Mathf.Lerp(footX, bowlX, 0.7f), Mathf.Lerp(footZ, bowlZ, 0.7f), Mathf.Lerp(footC, bowlC, 0.7f), under, 0.6f, -0.8f),
                Oval(bowlX, bowlZ, bowlC, bowlTop - rimH * 0.35f, 1f, 0f),
                Oval(bowlX * 0.97f, bowlZ * 0.97f, bowlC, bowlTop, 0.6f, 0.8f),
                // The lid: a crease under it, its underside out to its edge, the edge rounded up to its top.
                Oval(bowlX * 0.97f, bowlZ * 0.97f, bowlC, bowlTop, 0f, -1f),
                Oval(lidX - edge, lidZ - edge, lidC, bowlTop, 0f, -1f),
                Oval(lidX, lidZ, lidC, bowlTop + lid * 0.5f, 1f, 0f),
                Oval(lidX - edge, lidZ - edge, lidC, seat, 0f, 1f),
            };
            return RoundedMesh.Sweep(rings, 4, false, true);
        }

        /// <summary>
        /// The kitchen sink unit: a counter (wooden cabinet, two doors, plaster worktop) whose worktop opens on a metal basin
        /// 16 cm deep, the tap behind it. The box height is the tap's top: the worktop stands 0.18 m lower (0.9 m in a 1.08 m
        /// box). Solid up to the worktop. M9: the cabinet's rounded walls, a worktop with a rounded edge around a rounded
        /// opening, a pressed metal basin (its lip on the worktop, rounded corners and bottom). 318 triangles.
        /// </summary>
        private static void KitchenSink(RoomKit k, Vector3 s)
        {
            const float tap = 0.18f;
            const float worktop = 0.04f;
            const float basinDepth = 0.16f;
            float top = Mathf.Max(worktop + basinDepth + 0.2f, s.y - tap);
            float tapH = s.y - top;
            float bw = Mathf.Min(0.55f, s.x * 0.5f);
            float bd = Mathf.Min(0.4f, s.z * 0.62f);
            float bodyTop = top - worktop;
            float under = bodyTop - basinDepth;

            // The cabinet, set back 1 cm from the worktop's edges: its walls only (the worktop covers it, the basin hangs inside).
            k.Wood("Body", RoundedMesh.Slab(new Vector3(s.x - 0.02f, bodyTop, s.z - 0.02f), 0.02f, 0f, 0, 0f, 0, 2, false, false), new Vector3(0f, 0f, 0.01f));
            float doorW = (s.x - 0.02f) * 0.5f - 0.03f;
            float doorH = Mathf.Max(0.05f, bodyTop - 0.13f);
            for (int i = 0; i < 2; i++)
            {
                float x = (i == 0 ? -1f : 1f) * (doorW * 0.5f + 0.015f);
                k.Wood("Door" + i, new Vector3(x, 0.1f + doorH * 0.5f, -s.z * 0.5f + 0.0125f), new Vector3(doorW, doorH, 0.015f));
            }
            // Handles (2026-11-19): a brushed pull on each door, in the basin's Metal renderer (16 triangles).
            Handles.Pulls(k.Metal, doorW, 0.015f, 0.1f, 0.1f + doorH, -s.z * 0.5f + 0.005f, -1f);

            // The worktop around the opening, and the basin hanging from it.
            float stripD = (s.z - bd) * 0.5f;
            k.Plaster("Worktop", SinkWorktopMesh(s, top, worktop, bw, bd), Vector3.zero);
            k.Metal("Basin", SinkBasinMesh(top, under, bw, bd), Vector3.zero);

            if (tapH > 0.05f)
            {
                float postZ = bd * 0.5f + Mathf.Min(0.05f, stripD * 0.5f);
                k.Metal("TapPost", new Vector3(0f, top + tapH * 0.5f, postZ), new Vector3(0.03f, tapH, 0.03f));
                k.Metal("TapSpout", new Vector3(0f, s.y - 0.0125f, postZ - 0.06f), new Vector3(0.025f, 0.025f, 0.14f));
            }
            k.Solid("Collider", new Vector3(0f, top * 0.5f, 0f), new Vector3(s.x, top, s.z));
        }

        /// <summary>The corner radius in plan of the kitchen sink's opening and of its basin's walls.</summary>
        private static float SinkHole(float bw, float bd) => Mathf.Min(0.05f, Mathf.Min(bw, bd) * 0.25f);

        /// <summary>
        /// The kitchen sink's worktop (M9): its outside with rounded corners, its top edge rounded, the flat top down to the
        /// opening's edge (the basin's lip covers the opening's own walls).
        /// </summary>
        private static Mesh SinkWorktopMesh(Vector3 s, float top, float worktop, float bw, float bd)
        {
            float hx = s.x * 0.5f;
            float hz = s.z * 0.5f;
            // As the counter's worktop (FurnitureKit.Counter), so a run of them stays one soft line.
            float corner = Mathf.Min(0.02f, Mathf.Min(hx, hz) * 0.2f);
            float edge = Mathf.Min(0.015f, worktop * 0.4f);
            var rings = new List<RoundedMesh.Ring>
            {
                RoundedMesh.At(hx, hz, top - worktop, corner, 1f, 0f),
                RoundedMesh.At(hx, hz, top - edge, corner, 1f, 0f),
                RoundedMesh.At(hx - edge, hz - edge, top, Mathf.Max(corner - edge, corner * 0.5f), 0f, 1f),
                RoundedMesh.At(bw * 0.5f, bd * 0.5f, top, SinkHole(bw, bd), 0f, 1f),
            };
            return RoundedMesh.Sweep(rings, 2, false, false);
        }

        /// <summary>
        /// The kitchen sink's pressed metal basin (M9): a thin lip lying on the worktop around the opening, rolled into walls
        /// that lean in a centimetre down to a rounded bottom at <paramref name="under"/> (as deep as the boxes' basin).
        /// </summary>
        private static Mesh SinkBasinMesh(float top, float under, float bw, float bd)
        {
            const float rim = 0.012f;
            const float lift = 0.003f;
            const float slope = 0.01f;
            float hx = bw * 0.5f;
            float hz = bd * 0.5f;
            float hole = SinkHole(bw, bd);
            float bottom = Mathf.Min(0.04f, (top - under) * 0.3f);
            var rings = new List<RoundedMesh.Ring>
            {
                RoundedMesh.At(hx + rim, hz + rim, top, hole + rim, 0.6f, 0.8f),
                RoundedMesh.At(hx + rim * 0.3f, hz + rim * 0.3f, top + lift, hole + rim * 0.3f, 0f, 1f),
                RoundedMesh.At(hx - 0.004f, hz - 0.004f, top - 0.004f, hole, -0.7071f, 0.7071f),
                RoundedMesh.At(hx - slope, hz - slope, under + bottom, hole - slope, -1f, 0.06f),
                RoundedMesh.At(hx - slope - bottom * 0.2929f, hz - slope - bottom * 0.2929f, under + bottom * 0.2929f,
                    Mathf.Max(0.01f, hole - slope - bottom * 0.2929f), -0.7071f, 0.7071f),
                RoundedMesh.At(hx - slope - bottom, hz - slope - bottom, under, Mathf.Max(0.01f, hole - slope - bottom), 0f, 1f),
            };
            return RoundedMesh.Sweep(rings, 3, false, true);
        }

        /// <summary>
        /// A cooker: a white enamel body, a black glass hob with four metal plates, the oven door on the front (its dark
        /// window, its handle bar), four knobs on the band above and the drawer line below. Solid over the whole box.
        /// M9: rounded body and hob corners, round plates and knobs, a rounded oven window. About 360 triangles.
        /// </summary>
        private static void Stove(RoomKit k, Vector3 s)
        {
            const float plate = 0.006f;
            const float hob = 0.02f;
            const float corner = 0.025f;
            float hobTop = s.y - plate;
            float bodyTop = hobTop - hob;
            float front = -s.z * 0.5f + 0.03f;
            k.Ceramic("Body", RoundedMesh.Slab(new Vector3(s.x, bodyTop, s.z - 0.03f), corner, 0f, 0, 0f, 0, 2, false, false), new Vector3(0f, 0f, 0.015f));
            k.Dark("Hob", RoundedMesh.Slab(new Vector3(s.x, hob, s.z), corner, 0f, 0, 0.006f, 1, 2, false, true), new Vector3(0f, bodyTop, 0f));
            float big = Mathf.Min(s.x, s.z) * 0.3f;
            float small = big * 0.75f;
            float px = s.x * 0.23f;
            float pz = s.z * 0.22f;
            Mesh bigPlate = RoundedMesh.Slab(new Vector3(big, plate, big), big * 0.5f, 0f, 0, 0f, 0, 3, false, true);
            Mesh smallPlate = RoundedMesh.Slab(new Vector3(small, plate, small), small * 0.5f, 0f, 0, 0f, 0, 3, false, true);
            k.Metal("PlateFL", bigPlate, new Vector3(-px, hobTop, -pz));
            k.Metal("PlateBR", bigPlate, new Vector3(px, hobTop, pz));
            k.Metal("PlateFR", smallPlate, new Vector3(px, hobTop, -pz));
            k.Metal("PlateBL", smallPlate, new Vector3(-px, hobTop, pz));

            float doorTop = bodyTop - 0.1f;
            float doorBottom = Mathf.Min(0.12f, doorTop * 0.2f);
            float window = (doorTop - doorBottom) * 0.55f;
            k.Dark("Window", RoundedMesh.Slab(new Vector3(s.x * 0.7f, 0.008f, window), Mathf.Min(0.03f, window * 0.25f), 0f, 0, 0f, 0, 2, false, true),
                new Vector3(0f, doorBottom + (doorTop - doorBottom) * 0.42f, front), Facing);
            k.Metal("Handle", new Vector3(0f, doorTop - 0.04f, front - 0.0125f), new Vector3(s.x * 0.78f, 0.022f, 0.025f));
            k.Dark("DrawerLine", new Vector3(0f, doorBottom - 0.02f, front - 0.003f), new Vector3(s.x * 0.92f, 0.008f, 0.006f));
            Mesh knob = RoundedMesh.Slab(new Vector3(0.04f, 0.025f, 0.04f), 0.02f, 0f, 0, 0f, 0, 2, false, true);
            for (int i = 0; i < 4; i++)
            {
                k.Metal("Knob" + i, knob, new Vector3(s.x * (-0.3f + 0.2f * i), bodyTop - 0.05f, front), Facing);
            }
            k.Solid("Collider", new Vector3(0f, s.y * 0.5f, 0f), s);
        }

        /// <summary>
        /// A fridge freezer: a white body, the fridge door below and the freezer door above (split by a dark line), a dark
        /// plinth, two metal handles on the +x side. Solid over the whole box. M9: a body with rounded corners and top, two
        /// doors as rounded panels. 246 triangles.
        /// </summary>
        private static void Fridge(RoomKit k, Vector3 s)
        {
            const float door = 0.03f;
            const float gap = 0.012f;
            const float plinth = 0.07f;
            float front = -s.z * 0.5f + 0.04f;
            float round = Mathf.Min(0.04f, Mathf.Min(s.x, s.z) * 0.1f);
            k.Ceramic("Body", RoundedMesh.Slab(new Vector3(s.x, s.y, s.z - 0.04f), round, 0f, 0, round, 2, 2, false, true), new Vector3(0f, 0f, 0.02f));
            float split = s.y * 0.68f;
            float w = s.x - 0.01f;
            float fridgeTop = split - gap * 0.5f;
            float freezerBottom = split + gap * 0.5f;
            float freezerTop = s.y - 0.015f;
            // The doors: panels standing on the body's front (their back), their corners and front edges rounded.
            k.Ceramic("FridgeDoor", RoundedMesh.Slab(new Vector3(w, door, fridgeTop - plinth), 0.035f, 0f, 0, 0.012f, 1, 2, false, true),
                new Vector3(0f, (plinth + fridgeTop) * 0.5f, front), Facing);
            k.Ceramic("FreezerDoor", RoundedMesh.Slab(new Vector3(w, door, freezerTop - freezerBottom), 0.035f, 0f, 0, 0.012f, 1, 2, false, true),
                new Vector3(0f, (freezerBottom + freezerTop) * 0.5f, front), Facing);
            k.Dark("Split", new Vector3(0f, split, front - 0.004f), new Vector3(w, gap, 0.008f));
            k.Dark("Plinth", new Vector3(0f, plinth * 0.5f, front - 0.004f), new Vector3(s.x - 0.04f, plinth, 0.008f));
            float hx = s.x * 0.5f - 0.07f;
            float hz = -s.z * 0.5f + 0.005f;
            float upper = Mathf.Min(0.3f, (freezerTop - freezerBottom) * 0.5f);
            float lower = Mathf.Min(0.5f, (fridgeTop - plinth) * 0.45f);
            k.Metal("FreezerHandle", new Vector3(hx, freezerBottom + 0.05f + upper * 0.5f, hz), new Vector3(0.025f, upper, 0.01f));
            k.Metal("FridgeHandle", new Vector3(hx, fridgeTop - 0.05f - lower * 0.5f, hz), new Vector3(0.025f, lower, 0.01f));
            k.Solid("Collider", new Vector3(0f, s.y * 0.5f, 0f), s);
        }

        /// <summary>A low wooden coffee table: its top on four legs, a shelf below. Solid over the whole box. 6 boxes, 72 triangles.</summary>
        private static void CoffeeTable(RoomKit k, Vector3 s)
        {
            const float top = 0.04f;
            const float leg = 0.05f;
            const float inset = 0.03f;
            const float shelf = 0.02f;
            k.Wood("Top", new Vector3(0f, s.y - top * 0.5f, 0f), new Vector3(s.x, top, s.z));
            float lx = s.x * 0.5f - inset - leg * 0.5f;
            float lz = s.z * 0.5f - inset - leg * 0.5f;
            float lh = s.y - top;
            for (int i = 0; i < 4; i++)
            {
                float x = (i % 2 == 0 ? -1f : 1f) * lx;
                float z = (i < 2 ? -1f : 1f) * lz;
                k.Wood("Leg" + i, new Vector3(x, lh * 0.5f, z), new Vector3(leg, lh, leg));
            }
            k.Wood("Shelf", new Vector3(0f, Mathf.Min(0.12f, lh * 0.35f), 0f), new Vector3(s.x - 2f * inset, shelf, s.z - 2f * inset));
            k.Solid("Collider", new Vector3(0f, s.y * 0.5f, 0f), s);
        }

        /// <summary>
        /// A TV unit: a low wooden cabinet (two doors either side of a dark open niche), and, when the box leaves at least
        /// 0.25 m above it, a 16:9 screen standing on a metal foot, its top at the box's top. Solid: the cabinet, and the
        /// screen itself. 8 boxes, 96 triangles.
        /// </summary>
        private static void TvUnit(RoomKit k, Vector3 s)
        {
            const float slab = 0.03f;
            const float stand = 0.06f;
            const float panel = 0.015f;
            const float screenD = 0.04f;
            float cabinet = Mathf.Clamp(s.y * 0.45f, 0.25f, 0.55f);
            bool tv = s.y - cabinet >= 0.25f;
            if (!tv)
            {
                cabinet = s.y;
            }
            float front = -s.z * 0.5f + 0.02f;
            k.Wood("Body", new Vector3(0f, (cabinet - slab) * 0.5f, 0.01f), new Vector3(s.x, cabinet - slab, s.z - 0.02f));
            k.Wood("Top", new Vector3(0f, cabinet - slab * 0.5f, 0f), new Vector3(s.x, slab, s.z));
            float niche = s.x * 0.3f;
            float doorW = (s.x - niche) * 0.5f - 0.04f;
            float doorH = Mathf.Max(0.05f, cabinet - slab - 0.08f);
            float doorY = 0.04f + doorH * 0.5f;
            for (int i = 0; i < 2; i++)
            {
                float x = (i == 0 ? -1f : 1f) * (niche * 0.5f + 0.02f + doorW * 0.5f);
                k.Wood("Door" + i, new Vector3(x, doorY, front - panel * 0.5f), new Vector3(doorW, doorH, panel));
            }
            k.Dark("Niche", new Vector3(0f, doorY, front - 0.002f), new Vector3(niche - 0.02f, doorH, 0.004f));
            // Handles (2026-11-19): a dark metal pull on each door by the niche, in the niche's Dark renderer (16 triangles).
            Handles.Pulls(k.Dark, doorW, niche * 0.5f + 0.02f, doorY - doorH * 0.5f, doorY + doorH * 0.5f, front - panel, -1f);
            if (tv)
            {
                float width = Mathf.Min(s.x * 0.85f, (s.y - cabinet - stand) * 16f / 9f);
                float height = width * 9f / 16f;
                float bottom = s.y - height;
                float z = s.z * 0.12f;
                k.Dark("Screen", new Vector3(0f, bottom + height * 0.5f, z), new Vector3(width, height, screenD));
                k.Metal("Foot", new Vector3(0f, cabinet + 0.0075f, z), new Vector3(Mathf.Min(0.4f, width * 0.4f), 0.015f, Mathf.Min(0.2f, s.z * 0.45f)));
                float neckTop = bottom + Mathf.Min(0.05f, height * 0.3f);
                k.Metal("Neck", new Vector3(0f, (cabinet + neckTop) * 0.5f, z + screenD * 0.5f + 0.012f), new Vector3(0.06f, neckTop - cabinet, 0.024f));
                k.Solid("Screen", new Vector3(0f, bottom + height * 0.5f, z), new Vector3(width, height, screenD));
            }
            k.Solid("Cabinet", new Vector3(0f, cabinet * 0.5f, 0f), new Vector3(s.x, cabinet, s.z));
        }

        /// <summary>
        /// A bed, its headboard on +z (the sofa's backrest side): a wooden frame and headboard, the linen mattress, the duvet
        /// over the foot two thirds with the sheet folded over its edge, one pillow (narrower than 1.2 m) or two. Its colliders
        /// are the sofa's (<see cref="RoomObject"/>). M9 soft shapes: the frame and the mattress with rounded corners and top
        /// edges, a bullnosed headboard, a duvet with a rounded edge, the sheet's fold rolled, the pillows rounded all over.
        /// At most 376 triangles.
        /// </summary>
        private static void Bed(RoomKit k, Vector3 s)
        {
            float head = Mathf.Min(0.08f, s.z * 0.05f);
            float frame = s.y * 0.42f;
            float mattress = s.y * 0.8f;
            float pillow = s.y * 0.92f;
            float inner = s.z - head;
            float z = -head * 0.5f;
            k.Wood("Frame", RoundedMesh.Slab(new Vector3(s.x, frame, inner), 0.06f, 0f, 0, 0.025f, 1, 2, false, true), new Vector3(0f, 0f, z));
            k.Wood("Headboard", RoundedMesh.Slab(new Vector3(s.x, s.y, head), head * 0.5f, 0f, 0, head * 0.5f, 1, 2, false, true),
                new Vector3(0f, 0f, s.z * 0.5f - head * 0.5f));
            k.Linen("Mattress", RoundedMesh.Slab(new Vector3(s.x - 0.06f, mattress - frame, inner - 0.04f), 0.08f, 0f, 0, 0.04f, 1, 2, false, true),
                new Vector3(0f, frame, z));

            float duvetD = inner * 0.66f;
            float duvetTop = Mathf.Min(s.y - 0.006f, mattress + 0.035f);
            float duvetBottom = frame + 0.03f;
            float foot = -s.z * 0.5f + 0.005f;
            k.Upholstery("Duvet", RoundedMesh.Slab(new Vector3(s.x - 0.02f, duvetTop - duvetBottom, duvetD), 0.07f, 0f, 0, 0.05f, 1, 2, false, true),
                new Vector3(0f, duvetBottom, foot + duvetD * 0.5f));
            k.Linen("Fold", RoundedMesh.Slab(new Vector3(s.x - 0.015f, 0.03f, 0.13f), 0.015f, 0.015f, 1, 0.015f, 1, 1, false, true),
                new Vector3(0f, duvetTop - 0.024f, foot + duvetD - 0.055f));

            int count = s.x >= 1.2f ? 2 : 1;
            float pw = (s.x - 0.16f) / count - 0.06f;
            float pd = Mathf.Min(0.4f, inner * 0.2f);
            float pz = s.z * 0.5f - head - 0.04f - pd * 0.5f;
            float ph = pillow - mattress;
            Mesh soft = RoundedMesh.Slab(new Vector3(pw, ph, pd), Mathf.Min(pw, pd) * 0.3f, ph * 0.5f, 1, ph * 0.5f, 1, 2, false, true);
            for (int i = 0; i < count; i++)
            {
                float x = count == 1 ? 0f : (i == 0 ? -1f : 1f) * (pw * 0.5f + 0.03f);
                k.Linen("Pillow" + i, soft, new Vector3(x, mattress, pz));
            }
        }

        /// <summary>
        /// A nightstand: a wooden body under its top, a drawer above a door on the front, a metal knob on each. Solid over
        /// the whole box. 6 boxes, 72 triangles.
        /// </summary>
        private static void Nightstand(RoomKit k, Vector3 s)
        {
            const float top = 0.03f;
            const float panel = 0.015f;
            const float knob = 0.015f;
            float front = -s.z * 0.5f + knob + panel;
            float bodyH = s.y - top;
            k.Wood("Body", new Vector3(0f, bodyH * 0.5f, (front + s.z * 0.5f) * 0.5f), new Vector3(s.x - 0.02f, bodyH, s.z * 0.5f - front));
            k.Wood("Top", new Vector3(0f, s.y - top * 0.5f, 0f), new Vector3(s.x, top, s.z));
            float w = s.x - 0.06f;
            float drawerH = bodyH * 0.26f;
            float doorH = Mathf.Max(0.05f, bodyH - drawerH - 0.09f);
            float drawerY = bodyH - 0.025f - drawerH * 0.5f;
            float doorY = 0.04f + doorH * 0.5f;
            float zPanel = front - panel * 0.5f;
            k.Wood("Drawer", new Vector3(0f, drawerY, zPanel), new Vector3(w, drawerH, panel));
            k.Wood("Door", new Vector3(0f, doorY, zPanel), new Vector3(w, doorH, panel));
            float zKnob = -s.z * 0.5f + knob * 0.5f;
            k.Metal("KnobDrawer", new Vector3(0f, drawerY, zKnob), new Vector3(0.06f, 0.015f, knob));
            k.Metal("KnobDoor", new Vector3(w * 0.5f - 0.05f, doorY + doorH * 0.25f, zKnob), new Vector3(0.015f, 0.06f, knob));
            k.Solid("Collider", new Vector3(0f, s.y * 0.5f, 0f), s);
        }
    }
}
