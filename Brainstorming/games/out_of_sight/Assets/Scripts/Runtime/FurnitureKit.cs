using System.Collections.Generic;
using System.Globalization;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// Furniture compositions (PRD 7.1). Every part stays inside the box given by the level data, so the
    /// data stays the truth for validation and audit. Parts are built in the local frame of the prop:
    /// x and z centered, y from the floor up. The sofa's back is on +z; the chair, the armchair and the office
    /// chair face +z with their backrest on -z, as the furniture bodies move (and as the Kenney chair and armchair
    /// models stand with their yaw offset of 180).
    ///
    /// M4 (docs/CONTRACT_M4.md 2): every furniture body has a procedural visual (<see cref="Body"/>), used when its
    /// model is missing and always for the office chair, which has no model. A body visual has no collider (the
    /// player has its CharacterController, a decoy one box on its root) and stays within 400 triangles (PRD 7.4).
    ///
    /// M4.2 textures: every drawn part shows the detail of what it is made of (<see cref="Surface"/>): wood for frames,
    /// legs, shelves, cabinets and table tops, upholstery for sofas, armchairs and seats, linen for table cloths and the
    /// lamp shade, plaster for worktops and pots. Books stay plain.
    ///
    /// M6 texture pass 2 (CONTRACT_M6 2.4): the metal frame (office chair, lamp pole and base) and the potted plant's
    /// foliage get their own detail; the player's own furniture (always red, PRD 7.2) shows a glossy lacquer finish
    /// instead of its usual surface and smoothness wherever it would otherwise be wood or upholstery
    /// (<see cref="MainSurface"/>, <see cref="MainMaterial"/>), a decoy or a prop (never red) unaffected.
    ///
    /// M5 wave 5B (docs/CONTRACT_M5.md 5, 16.11 and 17): the procedural rocking chair (<see cref="RockingChair"/>), and the
    /// budgets counted as material slots: a level build combines a bookshelf's visual parts per material (its frame, then
    /// its books colour by colour), the prop's one collider unchanged.
    ///
    /// M8 room variety (docs/m8/ROOMS_PLAN.md 3): the ten room objects (bathtub to nightstand) are in FurnitureKitRooms.cs.
    /// </summary>
    public static partial class FurnitureKit
    {
        // Book colors reuse colors already present in the room: every new color is a new material, and
        // the level budget is 24 materials (PRD 7.4). Never red: red belongs to the player chair. M7 walls pass: the last
        // slot repeats the blue (it was a dark green of its own), one material fewer for the see-through walls' material; a
        // shelf reaches that slot only when it also shows the blue's own slot (the first book after the accent, bottom row).
        private static readonly Color[] BookColors =
        {
            new Color32(0xE3, 0xB2, 0x3C, 0xFF), new Color32(0x5B, 0x93, 0xD9, 0xFF), new Color32(0xF7, 0xF4, 0xEE, 0xFF),
            new Color32(0x3F, 0x8F, 0x4F, 0xFF), new Color32(0x8C, 0x5A, 0x36, 0xFF), new Color32(0x5B, 0x93, 0xD9, 0xFF),
        };

        /// <summary>
        /// The player chair (PRD 7.1), facing +z, backrest on the -z side. Soft movers (2026-11-20): the rounded design of
        /// the Kenney chair it stands in for (SoftBodies.Chair: a cushion of a seat, tapered legs, the backrest's posts and
        /// rails, an H of stretchers), still 6 renderers named as the M1 boxes were (the stretchers join the legs, the rails
        /// the backrest), 342 triangles.
        /// </summary>
        public static void Chair(Transform parent, Vector3 size, Color color, int layer)
        {
            Material m = MainMaterial(color, 0.35f);
            Surface wood = MainSurface(color, Surface.Wood);
            List<SoftBodies.Piece> pieces = SoftBodies.Chair(size);
            foreach (string part in ChairParts)
            {
                SoftBodies.Build(parent, pieces, part, m, layer, wood);
            }
        }

        private static readonly string[] ChairParts = { "Seat", "LegFL", "LegFR", "LegBL", "LegBR", "Backrest" };

        /// <summary>
        /// M6 (CONTRACT_M6 2.4, PRD 7.2): only the player's own furniture is ever red (every level's player colour is
        /// #D7263D, a decoy is always steered away from it), so a red main colour always means this is it: it shows the
        /// glossy lacquer finish (PaintedWood006C, metallic 0) instead of its usual surface and smoothness. A decoy or a
        /// prop body (never red) keeps <paramref name="normal"/>.
        /// </summary>
        private static Surface MainSurface(Color color, Surface normal) => ModelMath.IsRed(color) ? DebugMainFinish : normal; // MUTATION:LACQUER_RED

        /// <summary>
        /// The material that goes with <see cref="MainSurface"/>: the player's own furniture (never a decoy or a prop,
        /// which are never red) takes <see cref="PrimitiveKit.LitSurface"/> (its own cache, apart from every other use of
        /// the same colour at <paramref name="normalSmoothness"/>), so it never inherits a stray smoothness, and never
        /// forces one on them either.
        /// </summary>
        private static Material MainMaterial(Color color, float normalSmoothness) =>
            ModelMath.IsRed(color) ? PrimitiveKit.LitSurface(color, DebugMainFinish) : PrimitiveKit.Lit(color, normalSmoothness);

        /// <summary>PRD 12.2 open question 28: a temporary "-finish metal" command line switch for the player's own
        /// finish (the two comparison shots the look agent takes); lacquer stays the default, read once.</summary>
        private static readonly Surface DebugMainFinish = Probe.ArgValue("-finish") == "metal" ? Surface.Metal : Surface.Lacquer;

        // ----- M4 bodies (docs/CONTRACT_M4.md 2) -----

        /// <summary>
        /// The procedural visual of a furniture body of <paramref name="kind"/> (null or empty is the chair), filling
        /// <paramref name="size"/>, in <paramref name="color"/>, with no collider. False for an unknown kind (nothing built).
        /// </summary>
        public static bool Body(string kind, Transform parent, Vector3 size, Color color, int layer)
        {
            switch (BodyKinds.Of(kind))
            {
                case BodyKinds.Chair:
                    Chair(parent, size, color, layer);
                    return true;
                case BodyKinds.Stool:
                    Stool(parent, size, color, layer);
                    return true;
                case BodyKinds.Armchair:
                    // One colour: a body visual adds at most one material besides the frame near-black.
                    Armchair(parent, size, color, color, layer, false, true);
                    return true;
                case BodyKinds.FloorLamp:
                    FloorLamp(parent, size, color, layer);
                    return true;
                case BodyKinds.OfficeChair:
                    OfficeChair(parent, size, color, layer);
                    return true;
                case BodyKinds.RockingChair:
                    RockingChair(parent, size, color, layer);
                    return true;
                case BodyKinds.PlantStand:
                    PlantStand(parent, size, color, layer);
                    return true;
                default:
                    return false;
            }
        }

        /// <summary>
        /// The frame colour of the metal parts (office chair base, lamp pole): the near-black every model of the
        /// household already uses (ModelMath.NearBlack), so it costs no new material in a level with the man.
        /// </summary>
        public static Color FrameColor => ModelMath.NearBlack;

        /// <summary>
        /// A stool (fallback of the Kenney bar stool). Soft movers (2026-11-20): the rounded design of the bar stool
        /// (SoftBodies.Stool: a round plump cushion on four round legs splaying a little, a foot ring), in one colour, still
        /// 5 renderers (the seat and the four legs, the ring's sides joining them), 268 triangles.
        /// </summary>
        public static void Stool(Transform parent, Vector3 size, Color color, int layer)
        {
            Material m = MainMaterial(color, 0.35f);
            Surface wood = MainSurface(color, Surface.Wood);
            List<SoftBodies.Piece> pieces = SoftBodies.Stool(size);
            foreach (string part in StoolParts)
            {
                SoftBodies.Build(parent, pieces, part, m, layer, wood);
            }
        }

        private static readonly string[] StoolParts = { "Seat", "LegFL", "LegFR", "LegBL", "LegBR" };

        /// <summary>
        /// A floor lamp (fallback of the Kenney lamp): a foot, a pole and the shade on top, 3 renderers. Soft movers
        /// (2026-11-20): the rounded design of the round floor lamp (SoftBodies.FloorLamp: a domed round foot, a round pole,
        /// a tapered round shade with rolled lips, its inside showing), 290 triangles.
        /// </summary>
        public static void FloorLamp(Transform parent, Vector3 size, Color color, int layer)
        {
            Material shade = MainMaterial(color, 0.35f);
            // M6 (CONTRACT_M6 2.4): the pole and the foot are always metal (Metal009), player or decoy alike.
            Material frame = PrimitiveKit.LitSurface(FrameColor, Surface.Metal);
            List<SoftBodies.Piece> pieces = SoftBodies.FloorLamp(size);
            SoftBodies.Build(parent, pieces, "Foot", frame, layer, Surface.Metal);
            SoftBodies.Build(parent, pieces, "Pole", frame, layer, Surface.Metal);
            SoftBodies.Build(parent, pieces, "Shade", shade, layer, MainSurface(color, Surface.Linen));
        }

        /// <summary>The number of spokes and wheels of the office chair base.</summary>
        public const int OfficeChairSpokes = 5;

        /// <summary>
        /// The office chair (no model, CONTRACT_M4 2): a seat, a backrest on -z on its post, a gas column and a
        /// five-spoke base on wheels. Seat and back in <paramref name="color"/>; the metal (hub, spokes, wheels, column,
        /// post) is one mesh in <see cref="FrameColor"/>, so a chair is 3 renderers (level 7 has five of them).
        /// Soft movers (2026-11-20): a padded seat (rounded corners, a rolled top edge), a padded backrest panel (rounded
        /// corners, its face toward the sitter rolled), and the rounded frame (<see cref="OfficeChairFrame"/>). 380 triangles:
        /// the seat 58, the backrest 68, the frame 254.
        /// </summary>
        public static void OfficeChair(Transform parent, Vector3 size, Color color, int layer)
        {
            Material m = MainMaterial(color, 0.35f);
            Surface upholstery = MainSurface(color, Surface.Upholstery);
            // M6 (CONTRACT_M6 2.4): the frame (hub, post, spokes, wheels, column) is always metal (Metal009).
            Material frame = PrimitiveKit.LitSurface(FrameColor, Surface.Metal);
            const float seat = 0.07f;
            const float backDepth = 0.06f;
            float seatTop = size.y * 0.5f;
            float backBottom = seatTop + 0.12f;
            float backHeight = size.y - backBottom;
            PrimitiveKit.Part(parent, "Frame", OfficeChairFrame(size), Vector3.zero, Quaternion.identity, Vector3.one, frame, layer, Surface.Metal);
            PrimitiveKit.Part(parent, "Seat", RoundedMesh.Slab(new Vector3(size.x, seat, size.z), 0.09f, 0f, 0, 0.03f, 1, 2, false, true),
                new Vector3(0f, seatTop - seat, 0f), Quaternion.identity, Vector3.one, m, layer, upholstery);
            // The backrest is built lying (its rounded corners in plan) and stood up, its rolled face (the slab's top) toward +z.
            PrimitiveKit.Part(parent, "Backrest", RoundedMesh.Slab(new Vector3(size.x * 0.9f, backDepth, backHeight), 0.08f, 0f, 0, 0.02f, 1, 2, true, true),
                new Vector3(0f, backBottom + backHeight * 0.5f, -size.z * 0.5f), Quaternion.Euler(90f, 0f, 0f), Vector3.one, m, layer, upholstery);
        }

        private static readonly Dictionary<string, Mesh> FrameCache = new Dictionary<string, Mesh>();

        /// <summary>
        /// The metal of an office chair of <paramref name="size"/> as one mesh in the chair's frame (cached by size, kept
        /// across level rebuilds like PrimitiveKit's meshes): the hub, <see cref="OfficeChairSpokes"/> spokes with a wheel
        /// under each tip, the gas column up to the seat, and the backrest post. Soft movers (2026-11-20): a round hub with
        /// a rolled top (22 triangles), a round column (16), a backrest post of round section (16), five tapered spokes of
        /// round section arching down from the hub into their casters (80), five ball casters (120): 254 triangles.
        /// </summary>
        public static Mesh OfficeChairFrame(Vector3 size)
        {
            string key = string.Format(CultureInfo.InvariantCulture, "{0:0.###}x{1:0.###}x{2:0.###}", size.x, size.y, size.z);
            if (FrameCache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            float radius = Mathf.Min(size.x, size.z) * 0.5f;
            float wheel = Mathf.Min(0.06f, radius * 0.25f);
            const float seat = 0.07f;
            const float backDepth = 0.06f;
            float seatTop = size.y * 0.5f;
            float hubY = wheel + 0.015f;
            float reach = radius - wheel * 0.5f;
            float backBottom = seatTop + 0.12f;
            float backZ = -size.z * 0.5f + backDepth * 0.5f;
            var pieces = new List<SoftBodies.Piece>
            {
                Soft(SoftBodies.Revolve(new[] { new Vector4(0.045f, hubY - 0.022f, 1f, 0f), new Vector4(0.04f, hubY + 0.018f, 0.6f, 0.8f) }, 2, false, true), Matrix4x4.identity),
                Soft(SoftBodies.Revolve(new[] { new Vector4(0.025f, hubY, 1f, 0f), new Vector4(0.025f, seatTop - seat * 0.5f, 1f, 0f) }, 2, false, false), Matrix4x4.identity),
                SoftBodies.Bar(SoftBodies.Metal, "Frame", new Vector3(0f, seatTop - seat * 0.5f, backZ), new Vector3(0f, backBottom + 0.08f, backZ), Vector3.right,
                    new Vector2(0.025f, 0.014f), new Vector2(0.025f, 0.014f), 0.5f, 1, 0f, 0, 0f, 0, false, false),
            };
            Mesh ball = PrimitiveKit.SphereMesh(4, 4);
            for (int i = 0; i < OfficeChairSpokes; i++)
            {
                Vector3 direction = YawMath.Forward(180f + i * 360f / OfficeChairSpokes);
                Vector3 caster = direction * reach + Vector3.up * (wheel * 0.5f);
                // From inside the hub down into the caster, whose ball hides the tip.
                pieces.Add(SoftBodies.Bar(SoftBodies.Metal, "Frame", direction * 0.02f + Vector3.up * hubY, caster - direction * 0.005f, Vector3.up,
                    new Vector2(0.014f, 0.02f), new Vector2(0.009f, 0.013f), 0.5f, 1, 0f, 0, 0f, 0, false, false));
                pieces.Add(Soft(ball, Matrix4x4.TRS(caster, Quaternion.identity, Vector3.one * wheel)));
            }
            Mesh mesh = SoftBodies.Assemble(pieces, new[] { "Frame" }, true, Matrix4x4.identity, "OfficeChairFrame");
            FrameCache[key] = mesh;
            return mesh;
        }

        // ----- NEWFURN (docs/next/progress/NEWFURN.md): the plant stand and its banana pot -----

        /// <summary>The number of splayed legs of the plant stand.</summary>
        public const int PlantStandLegs = 3;

        private static readonly Dictionary<string, Mesh> StandCache = new Dictionary<string, Mesh>();

        /// <summary>
        /// The plant stand ("la sellette", no model): a round tray with a raised rim on three slender legs that splay out to the
        /// floor, braced by a round shelf a third of the way up. One mesh ("Stand", <see cref="PlantStandMesh"/>) in the main
        /// colour, so one renderer and one material (the player's red lacquer, or a decoy's wood); the banana pot it carries is
        /// the level's load (LoadView "banana").
        /// </summary>
        public static void PlantStand(Transform parent, Vector3 size, Color color, int layer)
        {
            PrimitiveKit.Part(parent, "Stand", PlantStandMesh(size), Vector3.zero, Quaternion.identity, Vector3.one, MainMaterial(color, 0.35f), layer,
                MainSurface(color, Surface.Wood));
        }

        /// <summary>
        /// The plant stand's mesh for a box of <paramref name="size"/> (cached by size, kept across level rebuilds): the tray, a
        /// shallow dish from 0.92 of the height to the top (rim 0.49 of the width, its floor 0.04 below the rim); the shelf, a
        /// round slab at a third of the height; three tapered round legs from under the tray's edge to the floor at 0.45 of the
        /// width, each with a small round foot. Everything stays inside the box. About 230 triangles (PRD 7.4: 400).
        /// </summary>
        public static Mesh PlantStandMesh(Vector3 size)
        {
            string key = string.Format(CultureInfo.InvariantCulture, "{0:0.###}x{1:0.###}x{2:0.###}", size.x, size.y, size.z);
            if (StandCache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            float w = Mathf.Min(size.x, size.z);
            float h = size.y;
            float rim = w * 0.49f;
            float trayBottom = h * 0.92f;
            float trayFloor = h - 0.04f;
            var b = new MeshBuilder();
            // The tray: under side, flared edge up to the rim, the rim's top, and the inside down to the dish's floor.
            b.AddLathe(Matrix4x4.identity, new[]
            {
                new Vector2(rim * 0.78f, trayBottom), new Vector2(rim * 0.97f, trayBottom + (h - trayBottom) * 0.45f), new Vector2(rim, h),
                new Vector2(rim * 0.9f, h), new Vector2(rim * 0.86f, trayFloor),
            }, 14, true, true);
            // The shelf.
            float shelfY = h * 0.33f;
            float shelf = w * 0.36f;
            b.AddLathe(Matrix4x4.identity, new[] { new Vector2(shelf, shelfY - 0.012f), new Vector2(shelf, shelfY + 0.012f) }, 12, true, true);
            // The legs: from under the tray's edge, splayed out to the floor, each on a small round foot.
            float legTop = rim * 0.72f;
            float legFoot = w * 0.45f;
            for (int i = 0; i < PlantStandLegs; i++)
            {
                Vector3 direction = YawMath.Forward(180f + i * 360f / PlantStandLegs);
                Vector3 top = direction * legTop + Vector3.up * (trayBottom + 0.005f);
                Vector3 foot = direction * legFoot + Vector3.up * 0.018f;
                b.AddRod(foot, top, 0.012f, 0.016f, 6);
                b.AddLathe(Matrix4x4.Translate(direction * legFoot), new[] { new Vector2(0.016f, 0f), new Vector2(0.018f, 0.009f), new Vector2(0.012f, 0.02f) },
                    6, true, false);
            }
            Mesh mesh = b.Build();
            mesh.name = "PlantStand";
            mesh.hideFlags = HideFlags.DontUnloadUnusedAsset;
            StandCache[key] = mesh;
            return mesh;
        }

        /// <summary>The banana pot's colours: the level plants' leaves and pot (lvlib's plant colours), so it shares their materials.</summary>
        public static readonly Color BananaPotLeaves = new Color32(0x3F, 0x8F, 0x4F, 0xFF);
        public static readonly Color BananaPotClay = new Color32(0x8C, 0x5A, 0x36, 0xFF);

        /// <summary>
        /// NEWFURN: the plant stand's banana pot (LoadView "banana", carried and fallen): the banana plant of the level props
        /// (<see cref="BananaMeshes"/>, 396 triangles) for a box of <paramref name="size"/>, placed at <paramref name="position"/>
        /// and <paramref name="rotation"/> under <paramref name="parent"/>: the pot ("PotShape"), the soil and stems ("Trunk") and
        /// the blades ("Leaves", with the banana leaf chart), with the materials of a banana prop in the default plant colours,
        /// so a level with banana plants pays nothing new for it. No collider.
        /// </summary>
        public static void BananaPot(Transform parent, Vector3 size, Vector3 position, Quaternion rotation, int layer)
        {
            Mesh[] meshes = BananaMeshes(size, 1);
            PrimitiveKit.Part(parent, "PotShape", meshes[0], position, rotation, Vector3.one, PrimitiveKit.Lit(BananaPotClay, 0.6f), layer);
            PrimitiveKit.Part(parent, "Trunk", meshes[1], position, rotation, Vector3.one, PrimitiveKit.LitSurface(BarkColor, Surface.Soil), layer, Surface.Soil);
            GameObject leaves = PrimitiveKit.Part(parent, "Leaves", meshes[2], position, rotation, Vector3.one,
                PrimitiveKit.LitSurface(BananaPotLeaves, Surface.Foliage), layer, Surface.Foliage);
            PrimitiveKit.BananaLeafDetail(leaves.GetComponent<MeshRenderer>());
        }

        private static SoftBodies.Piece Soft(Mesh mesh, Matrix4x4 matrix)
        {
            return new SoftBodies.Piece { Source = SoftBodies.Metal, Part = "Frame", Mesh = mesh, Matrix = matrix };
        }

        public static void Build(PropDef prop, Transform parent, int layer)
        {
            Build(prop, parent, layer, true);
        }

        /// <summary>
        /// <see cref="Build(PropDef, Transform, int, bool)"/>; with <paramref name="combine"/> (the level builder passes
        /// LevelBuilder.CombineRenderers) a bookshelf draws its visual parts combined per material (CONTRACT_M5 17).
        /// </summary>
        public static void Build(PropDef prop, Transform parent, int layer, bool visual, bool combine)
        {
            if (prop.Kind == "bookshelf")
            {
                Bookshelf(parent, prop.Size, LevelJson.ParseColor(prop.Color, Color.gray), AccentOf(prop), layer, prop.Occluder, visual, combine);
                return;
            }
            // M8: a room object combines its visual parts per material, as the bookshelf.
            if (RoomObject(prop, parent, layer, visual, combine))
            {
                return;
            }
            // Handles (2026-11-19): a cabinet and a wardrobe combine their wood and their handles too (Handles).
            if (prop.Kind == "cabinet" || prop.Kind == WardrobeRule.Kind)
            {
                Color main = LevelJson.ParseColor(prop.Color, Color.gray);
                if (prop.Kind == "cabinet")
                {
                    Cabinet(parent, prop.Size, main, AccentOf(prop), layer, prop.Occluder, visual, combine);
                }
                else
                {
                    Wardrobe(parent, prop.Size, main, AccentOf(prop), layer, prop.Occluder, visual, combine);
                }
                return;
            }
            Build(prop, parent, layer, visual);
        }

        /// <summary>
        /// M3 (docs/CONTRACT_M3.md 1): with <paramref name="visual"/> false the prop is built for a model visual:
        /// every part that carries a collider becomes a collider-only GameObject (same transform, scale and
        /// layer, no MeshFilter, no MeshRenderer) and the purely visual parts are skipped. The colliders are
        /// exactly those of the procedural prop, so vision, the NavMesh and the audit do not change.
        /// </summary>
        public static void Build(PropDef prop, Transform parent, int layer, bool visual)
        {
            if (RoomObject(prop, parent, layer, visual, false))
            {
                return;
            }
            Color main = LevelJson.ParseColor(prop.Color, Color.gray);
            Color accent = AccentOf(prop);
            bool col = prop.Occluder;
            switch (prop.Kind)
            {
                case "sofa":
                    Sofa(parent, prop.Size, main, accent, layer, col, visual);
                    break;
                case "bookshelf":
                    Bookshelf(parent, prop.Size, main, accent, layer, col, visual, false);
                    break;
                case "table":
                    Table(parent, prop.Size, main, accent, layer, col, visual);
                    break;
                case "cabinet":
                    Cabinet(parent, prop.Size, main, accent, layer, col, visual, false);
                    break;
                case "counter":
                    Counter(parent, prop.Size, main, accent, layer, col, visual);
                    break;
                case "plant":
                    Plant(parent, prop.Size, main, accent, layer, col, visual, PlantStyleOf(prop), PlantVariant(prop));
                    break;
                case BodyKinds.Armchair:
                    Armchair(parent, prop.Size, main, accent, layer, col, visual);
                    break;
                case WardrobeRule.Kind:
                    Wardrobe(parent, prop.Size, main, accent, layer, col, visual, false);
                    break;
                default:
                    PrimitiveKit.Box(parent, "Body", new Vector3(0f, prop.SizeY * 0.5f, 0f), prop.Size, Mat(main, 0.25f, visual), layer, col, visual,
                        MainSurface(main, Surface.Wood));
                    break;
            }
        }

        /// <summary>The accent colour of a prop, as the procedural parts use it (the model red remap target).</summary>
        public static Color AccentOf(PropDef prop)
        {
            Color main = LevelJson.ParseColor(prop.Color, Color.gray);
            return LevelJson.ParseColor(prop.AccentColor, main * 0.8f);
        }

        /// <summary>
        /// No material is created for a part that will not be drawn. M6: the player's own furniture (always red,
        /// <see cref="MainMaterial"/>) takes the lacquer finish instead of <paramref name="smoothness"/>.
        /// </summary>
        private static Material Mat(Color color, float smoothness, bool visual) => visual ? MainMaterial(color, smoothness) : null;

        /// <summary>Base, backrest on +z, two arms, two cushions. Colliders on the structural parts.</summary>
        private static void Sofa(Transform p, Vector3 s, Color main, Color accent, int layer, bool col, bool visual)
        {
            Material body = Mat(main, 0.15f, visual);
            Material cushion = Mat(accent, 0.15f, visual);
            float baseH = s.y * 0.5f;
            float backD = DecorKinds.SofaBackDepth(s);
            float armW = Mathf.Min(0.2f, s.x * 0.1f);
            float armH = s.y * 0.72f;
            PrimitiveKit.Box(p, "Base", new Vector3(0f, baseH * 0.5f, 0f), new Vector3(s.x, baseH, s.z), body, layer, col, visual, Surface.Upholstery);
            PrimitiveKit.Box(p, "Backrest", new Vector3(0f, baseH + (s.y - baseH) * 0.5f, s.z * 0.5f - backD * 0.5f),
                new Vector3(s.x, s.y - baseH, backD), body, layer, col, visual, Surface.Upholstery);
            float armDepth = s.z - backD;
            PrimitiveKit.Box(p, "ArmL", new Vector3(-s.x * 0.5f + armW * 0.5f, baseH + (armH - baseH) * 0.5f, -backD * 0.5f),
                new Vector3(armW, armH - baseH, armDepth), body, layer, col, visual, Surface.Upholstery);
            PrimitiveKit.Box(p, "ArmR", new Vector3(s.x * 0.5f - armW * 0.5f, baseH + (armH - baseH) * 0.5f, -backD * 0.5f),
                new Vector3(armW, armH - baseH, armDepth), body, layer, col, visual, Surface.Upholstery);
            float seatW = (s.x - 2f * armW) * 0.5f - 0.02f;
            float cushionH = Mathf.Min(0.09f, armH - baseH - 0.02f);
            for (int i = 0; i < 2; i++)
            {
                float x = (i == 0 ? -1f : 1f) * (seatW * 0.5f + 0.01f);
                PrimitiveKit.Box(p, "Cushion" + i, new Vector3(x, baseH + cushionH * 0.5f, -backD * 0.5f),
                    new Vector3(seatW, cushionH, armDepth - 0.04f), cushion, layer, false, visual, Surface.Upholstery);
            }
        }

        // Armchair proportions, measured on the Kenney lounge chair (the model it stands in for): seat at half the height,
        // arms up to three quarters, arms 19 % of the width each, a backrest 22 % of the depth.
        private const float ArmchairSeat = 0.5f;
        private const float ArmchairArm = 0.75f;
        private const float ArmchairArmWidth = 0.19f;
        private const float ArmchairBackDepth = 0.22f;

        /// <summary>
        /// M4 armchair, the player body and the "armchair" prop (docs/CONTRACT_M4.md 2.2): a base up to the seat, a
        /// backrest on -z up to the full height, two arms, a cushion. Colliders (a prop) on the base, the backrest and
        /// the arms: a solid low block with a tall back, cover for a stool (top at 0.52 m) behind it or beside it.
        /// Soft movers (2026-11-20): the visual is the rounded lounge chair (SoftBodies.Armchair: soft upholstered blocks,
        /// rolled arms and back, a cushion on the seat), 5 renderers, 372 triangles; the colliders stay these boxes, as
        /// collider-only objects (exactly as under a model, M9's counter does the same), the visual parts next to them
        /// named with "Shape" (the cushion, which has no collider, keeps its name). A body (no collider) names its parts
        /// as before.
        /// </summary>
        private static void Armchair(Transform p, Vector3 s, Color main, Color accent, int layer, bool col, bool visual)
        {
            float seatH = s.y * ArmchairSeat;
            float armH = s.y * ArmchairArm;
            float armW = s.x * ArmchairArmWidth;
            float backD = s.z * ArmchairBackDepth;
            float armDepth = s.z - backD;
            // The arms and the cushion run from the front of the backrest to the front edge: centred at +backD / 2.
            float frontZ = backD * 0.5f;
            if (col)
            {
                PrimitiveKit.Box(p, "Base", new Vector3(0f, seatH * 0.5f, 0f), new Vector3(s.x, seatH, s.z), null, layer, true, false);
                PrimitiveKit.Box(p, "Backrest", new Vector3(0f, seatH + (s.y - seatH) * 0.5f, -s.z * 0.5f + backD * 0.5f),
                    new Vector3(s.x, s.y - seatH, backD), null, layer, true, false);
                PrimitiveKit.Box(p, "ArmL", new Vector3(-s.x * 0.5f + armW * 0.5f, seatH + (armH - seatH) * 0.5f, frontZ),
                    new Vector3(armW, armH - seatH, armDepth), null, layer, true, false);
                PrimitiveKit.Box(p, "ArmR", new Vector3(s.x * 0.5f - armW * 0.5f, seatH + (armH - seatH) * 0.5f, frontZ),
                    new Vector3(armW, armH - seatH, armDepth), null, layer, true, false);
            }
            if (!visual)
            {
                return;
            }
            Material body = Mat(main, 0.15f, true);
            Surface bodySurface = MainSurface(main, Surface.Upholstery);
            List<SoftBodies.Piece> pieces = SoftBodies.Armchair(s, false);
            string suffix = col ? "Shape" : string.Empty;
            foreach (string part in ArmchairParts)
            {
                SoftBodies.Build(p, part + suffix, pieces, part, SoftBodies.Pivot(pieces, part), body, layer, bodySurface);
            }
            SoftBodies.Build(p, pieces, "Cushion", Mat(accent, 0.15f, true), layer, MainSurface(accent, Surface.Upholstery));
        }

        private static readonly string[] ArmchairParts = { "Base", "Backrest", "ArmL", "ArmR" };

        /// <summary>
        /// A full occluder (PRD 6.3): one collider over the whole box, open shelves and books for the look. M5 wave 5B: with
        /// <paramref name="combine"/>, its parts draw as one renderer per material ("Frame", then "Books" and the colour).
        /// M9 soft shapes (bookshelf pass, FurnitureKitShelf.cs): the frame is one mesh of its visible faces only, its front
        /// edges shaded round (<see cref="ShelfFrameMesh"/>, 54 triangles), and the shelves stay as full as the M5 blocks made
        /// them, each block now a row of books with rounded spines, varied heights and colours, a leaning book or two, and a
        /// round jar and vase (<see cref="ShelfContents"/>), in the colours the books always had, within
        /// Tuning.FurnitureTriangleBudget (400 per 1.6 m of width).
        /// </summary>
        private static void Bookshelf(Transform p, Vector3 s, Color wood, Color accent, int layer, bool col, bool visual, bool combine)
        {
            Material m = Mat(wood, 0.2f, visual);
            const float panel = 0.04f;
            const float shelf = 0.03f;
            const int levels = 4;
            float innerW = s.x - 2f * panel;
            float pitch = (s.y - shelf) / levels;
            var parts = new PartBatch(p, layer, combine && visual); // MUTATION:SHELF_COMBINE
            Mesh frame = ShelfFrameMesh(s, panel, shelf, pitch, levels);
            parts.Shape("Frame", "Frame", frame, Vector3.zero, Quaternion.identity, m, visual, Surface.Wood);
            int budget = Tuning.FurnitureTriangleBudget(PropKinds.Bookshelf, s.x) - (int)ModelKit.Triangles(frame);
            ShelfContents(parts, s, innerW, shelf, pitch, levels, accent, visual, budget);
            parts.Flush();
            if (col)
            {
                var collider = new GameObject("Collider") { layer = layer };
                collider.transform.SetParent(p, false);
                var box = collider.AddComponent<BoxCollider>();
                box.center = new Vector3(0f, s.y * 0.5f, 0f);
                box.size = s;
            }
        }

        /// <summary>
        /// The visual parts of one prop (M5 wave 5B, CONTRACT_M5 17: draw calls are material slots). Combined, every part joins
        /// the group of its material and surface, and <see cref="Flush"/> draws each group as one renderer under the prop,
        /// named by the group of its first part ("Books" groups stay plain, as each book did); a part with a collider never
        /// comes here. Not combined, each part is built as its own box, exactly as before.
        /// </summary>
        private sealed class PartBatch
        {
            private sealed class Group
            {
                public Material Material;
                public Surface Surface;
                public string Name;
                public readonly List<PrimitiveKit.CombinePart> Parts = new List<PrimitiveKit.CombinePart>();
            }

            private readonly Transform parent;
            private readonly int layer;
            private readonly bool combine;
            private readonly List<Group> groups = new List<Group>();

            public PartBatch(Transform parent, int layer, bool combine)
            {
                this.parent = parent;
                this.layer = layer;
                this.combine = combine;
            }

            /// <summary>A visual-only box: <paramref name="name"/> on its own, or into the group named <paramref name="group"/>.</summary>
            public void Box(string name, string group, Vector3 center, Vector3 size, Material material, bool visual, Surface surface)
            {
                if (!combine)
                {
                    PrimitiveKit.Box(parent, name, center, size, material, layer, false, visual, surface);
                    return;
                }
                Group g = groups.Find(x => x.Material == material && x.Surface == surface);
                if (g == null)
                {
                    g = new Group { Material = material, Surface = surface, Name = group };
                    groups.Add(g);
                }
                g.Parts.Add(new PrimitiveKit.CombinePart { Mesh = PrimitiveKit.BoxMeshSized(size), Matrix = Matrix4x4.TRS(center, Quaternion.identity, size) });
            }

            /// <summary>
            /// M9 soft shapes: a visual-only mesh in metres (RoundedMesh), its origin at <paramref name="position"/> turned by
            /// <paramref name="rotation"/>: <paramref name="name"/> on its own, or into the group named <paramref name="group"/>,
            /// exactly as <see cref="Box"/>.
            /// </summary>
            public void Shape(string name, string group, Mesh mesh, Vector3 position, Quaternion rotation, Material material, bool visual, Surface surface)
            {
                if (!combine)
                {
                    if (visual)
                    {
                        PrimitiveKit.Part(parent, name, mesh, position, rotation, Vector3.one, material, layer, surface);
                    }
                    return;
                }
                Group g = groups.Find(x => x.Material == material && x.Surface == surface);
                if (g == null)
                {
                    g = new Group { Material = material, Surface = surface, Name = group };
                    groups.Add(g);
                }
                g.Parts.Add(new PrimitiveKit.CombinePart { Mesh = mesh, Matrix = Matrix4x4.TRS(position, rotation, Vector3.one) });
            }

            /// <summary>Draws every group as one renderer under the prop (nothing when not combined).</summary>
            public void Flush()
            {
                foreach (Group g in groups)
                {
                    PrimitiveKit.Part(parent, g.Name, PrimitiveKit.CombinedMesh(g.Parts), Vector3.zero, Quaternion.identity, Vector3.one, g.Material, layer,
                        g.Surface);
                }
                groups.Clear();
            }
        }

        // ----- M5 wave 5B: the rocking chair (docs/CONTRACT_M5.md 5) -----

        /// <summary>The segments of each curved runner of the procedural rocking chair (an even number: a ring at the middle, where it touches the floor).</summary>
        public const int RockerSegments = 4;

        /// <summary>How far the runners' ends rise above their middle (metres): the curve the chair rocks on.</summary>
        public const float RockerRise = 0.06f;

        /// <summary>
        /// The procedural rocking chair (CONTRACT_M5 5, used when no model exists): two curved runners along z (each
        /// <see cref="RockerSegments"/> segments on a parabola, lowest and touching the floor at the middle, <see cref="RockerRise"/>
        /// higher at the ends), the seat, two back posts leaning back from the runners up past the seat to the full height and
        /// the back panel between them on -z, two front legs from the runners up to the arms, two arms from the posts to the
        /// front. Facing +z with its back on -z, within its box, in one colour of wood and one mesh: one renderer (one draw call).
        /// Soft movers (2026-11-20): runners of round section bending along the curve with flat ends, a seat with rounded
        /// corners and a rolled top edge, posts, legs and arms of round section, a back panel with rounded corners: 374
        /// triangles (PRD 7.4: 400).
        /// </summary>
        public static void RockingChair(Transform parent, Vector3 size, Color color, int layer)
        {
            PrimitiveKit.Part(parent, "RockingChair", RockingChairMesh(size), Vector3.zero, Quaternion.identity, Vector3.one,
                MainMaterial(color, 0.35f), layer, MainSurface(color, Surface.Wood));
        }

        /// <summary>The parts of <see cref="RockingChair"/> as one mesh in the chair's frame (UVs in metres; cached by its parts).</summary>
        public static Mesh RockingChairMesh(Vector3 size)
        {
            float w = size.x;
            float h = size.y;
            float d = size.z;
            const float runner = 0.04f;
            const float seat = 0.05f;
            const float post = 0.04f;
            const float lean = 12f;
            const string part = "RockingChair";
            var pieces = new List<SoftBodies.Piece>();
            // The runners: their centre line at y = runner / 2 + rise * (2 z / d)^2, ending just inside the box.
            float half = d * 0.5f - 0.012f;
            float RunnerY(float z) => runner * 0.5f + RockerRise * (2f * z / d) * (2f * z / d);
            float sideX = w * 0.5f - runner * 0.5f;
            var round = new Vector2(runner * 0.5f, runner * 0.5f);
            foreach (float side in new[] { -1f, 1f })
            {
                var path = new Vector3[RockerSegments + 1];
                for (int i = 0; i <= RockerSegments; i++)
                {
                    float z = -half + 2f * half * i / RockerSegments;
                    path[i] = new Vector3(side * sideX, RunnerY(z), z);
                }
                pieces.Add(new SoftBodies.Piece { Source = SoftBodies.Wood, Part = part, Mesh = SoftBodies.Tube(path, Vector3.right, round, 0.5f, 1, true, true),
                    Matrix = Matrix4x4.identity });
            }
            // The seat.
            float seatTop = h * 0.45f;
            pieces.Add(new SoftBodies.Piece { Source = SoftBodies.Wood, Part = part,
                Mesh = RoundedMesh.Slab(new Vector3(w, seat, d * 0.6f), 0.06f, 0f, 0, 0.02f, 1, 2, false, true),
                Matrix = Matrix4x4.Translate(new Vector3(0f, seatTop - seat, d * 0.05f)) });
            float legZ = d * 0.22f;
            float legTop = seatTop - seat;
            float armY = seatTop + 0.2f;
            var stick = new Vector2(post * 0.5f, post * 0.5f);
            // The front legs, from inside the runners up into the arms.
            foreach (float side in new[] { -1f, 1f })
            {
                var foot = new Vector3(side * sideX, RunnerY(legZ) + runner * 0.5f - 0.012f, legZ);
                pieces.Add(SoftBodies.Bar(SoftBodies.Wood, part, foot, new Vector3(side * sideX, armY, legZ), Vector3.right, stick, stick, 0.5f, 1,
                    0f, 0, 0f, 0, false, false));
            }
            // The back posts lean back by `lean` degrees through the seat's back corners (legTop at -legZ), from inside the
            // runners up to the full height; the panel spans their upper part.
            Quaternion tilt = Quaternion.Euler(-lean, 0f, 0f);
            Vector3 up = tilt * Vector3.up;
            float postLength = (h - 0.01f - legTop) / up.y;
            float bottom = legTop;
            for (int i = 0; i < 2; i++)
            {
                float z = -legZ + (legTop - bottom) * Mathf.Tan(lean * Mathf.Deg2Rad);
                bottom = RunnerY(z) + runner * 0.5f - 0.012f;
            }
            float below = (legTop - bottom) / up.y;
            foreach (float side in new[] { -1f, 1f })
            {
                var through = new Vector3(side * sideX, legTop, -legZ);
                pieces.Add(SoftBodies.Bar(SoftBodies.Wood, part, through - up * below, through + up * postLength, Vector3.right, stick, stick, 0.5f, 1,
                    0f, 0, 0f, 0, false, true));
            }
            float panelFrom = (seatTop + 0.15f - legTop) / up.y;
            float panelTo = postLength - 0.03f;
            Vector3 panelCenter = new Vector3(0f, legTop, -legZ) + up * ((panelFrom + panelTo) * 0.5f);
            const float panel = 0.025f;
            // Built lying (its rounded corners in plan) and stood up along the posts, its sides just inside them.
            pieces.Add(new SoftBodies.Piece { Source = SoftBodies.Wood, Part = part,
                Mesh = RoundedMesh.Slab(new Vector3(w - 2f * post + 0.01f, panel, panelTo - panelFrom), 0.04f, 0f, 0, 0f, 0, 2, true, true),
                Matrix = Matrix4x4.TRS(panelCenter + tilt * new Vector3(0f, 0f, -panel * 0.5f), tilt * Quaternion.Euler(90f, 0f, 0f), Vector3.one) });
            // The arms, from inside the back posts to the front, over the front legs.
            float armBack = -legZ - (armY - legTop) / up.y * Mathf.Sin(lean * Mathf.Deg2Rad);
            float armFront = d * 0.3f;
            var arm = new Vector2(0.015f, post * 0.5f);
            foreach (float side in new[] { -1f, 1f })
            {
                pieces.Add(SoftBodies.Bar(SoftBodies.Wood, part, new Vector3(side * sideX, armY, armBack), new Vector3(side * sideX, armY, armFront), Vector3.up,
                    arm, arm, 0.6f, 1, 0f, 0, 0f, 0, false, true));
            }
            return SoftBodies.Assemble(pieces, new[] { part }, true, Matrix4x4.identity, "RockingChair");
        }

        /// <summary>
        /// A dresser or tall cupboard (M2): a full occluder up to its height, one collider over the whole box,
        /// two door panels on the front (-z), each with a vertical bar pull by the middle (Handles). Combined (the level
        /// builder's <paramref name="combine"/>), its wood draws as one renderer (the body, top and doors all show the Wood
        /// image) and its handles as one more in the household's dark metal: 2 draw calls instead of 4. 10 boxes, 120
        /// triangles.
        /// </summary>
        private static void Cabinet(Transform p, Vector3 s, Color wood, Color accent, int layer, bool col, bool visual, bool combine)
        {
            Material body = Mat(wood, 0.25f, visual);
            Material doors = Mat(accent, 0.3f, visual);
            if (combine)
            {
                // Grouped by the material they show: one Wood renderer while the textures are on, the two palettes otherwise.
                body = PrimitiveKit.ShownMaterial(body, Surface.Wood);
                doors = PrimitiveKit.ShownMaterial(doors, Surface.Wood);
            }
            Material handle = visual ? Handles.Material : null;
            const float top = 0.04f;
            const float panel = 0.02f;
            var parts = new PartBatch(p, layer, combine && visual);
            parts.Box("Body", "Wood", new Vector3(0f, (s.y - top) * 0.5f, 0f), new Vector3(s.x, s.y - top, s.z), body, visual, Surface.Wood);
            parts.Box("Top", "Wood", new Vector3(0f, s.y - top * 0.5f, 0f), new Vector3(s.x, top, s.z), doors, visual, Surface.Wood);
            float doorW = s.x * 0.5f - 0.05f;
            float doorH = (s.y - top) * 0.82f;
            float doorY = (s.y - top) * 0.5f + 0.02f;
            float handleY = Handles.HeightOn(doorY - doorH * 0.5f, doorY + doorH * 0.5f, 0.1f);
            float handleLength = Mathf.Min(0.2f, doorH * 0.3f);
            for (int i = 0; i < 2; i++)
            {
                float side = i == 0 ? -1f : 1f;
                float x = side * (doorW * 0.5f + 0.02f);
                // The doors stand proud of the body by their own thickness: flush, their front face was coplanar with the
                // body's and z-fought (the colour flickered as the camera moved, the product owner's 2026-11-18 report).
                parts.Box("Door" + i, "Wood", new Vector3(x, doorY, -s.z * 0.5f - panel * 0.5f), new Vector3(doorW, doorH, panel), doors, visual,
                    Surface.Wood);
                // The pull by the doors' meeting edge, on the door's front face.
                var onFace = new Vector3(side * (0.02f + Mathf.Min(0.07f, doorW * 0.25f)), handleY, -s.z * 0.5f - panel);
                Handles.Bar((name, center, size) => parts.Box(name + i, "Handles", center, size, handle, visual, Surface.Plain), "Handle", onFace, -1f,
                    handleLength);
            }
            parts.Flush();
            if (col)
            {
                var collider = new GameObject("Collider") { layer = layer };
                collider.transform.SetParent(p, false);
                var box = collider.AddComponent<BoxCollider>();
                box.center = new Vector3(0f, s.y * 0.5f, 0f);
                box.size = s;
            }
        }

        /// <summary>
        /// M6 gameplay (docs/CONTRACT_M6.md 2.5 and 2.4): the wardrobe, a full occluder with one collider over its whole box,
        /// its two doors on the front (local +z, WardrobeRule.Front), a cornice on top, all Wood (Wood049). 4 boxes, 48
        /// triangles, the prop's colour and its accent.
        /// Handles (2026-11-19): each door carries a vertical bar pull by the middle (a child of the door, so it swings with
        /// it). Combined (the level builder's <paramref name="combine"/>), the wardrobe at rest is drawn by "Closed" (its wood,
        /// one renderer) and "ClosedHandles" (the household's dark metal): 2 draw calls instead of 4. The parts above are
        /// built as before but their renderers wait disabled until WardrobeDoors swings the doors, and go back after. 22 boxes
        /// built, 132 triangles drawn at rest.
        /// </summary>
        private static void Wardrobe(Transform p, Vector3 s, Color wood, Color accent, int layer, bool col, bool visual, bool combine)
        {
            Material body = Mat(wood, 0.25f, visual);
            Material doors = Mat(accent, 0.3f, visual);
            const float top = 0.06f;
            const float panel = 0.02f;
            var bodyCenter = new Vector3(0f, (s.y - top) * 0.5f, -panel * 0.5f);
            var bodySize = new Vector3(s.x, s.y - top, s.z - panel);
            var corniceCenter = new Vector3(0f, s.y - top * 0.5f, 0f);
            var corniceSize = new Vector3(s.x, top, s.z);
            GameObject bodyGo = PrimitiveKit.Box(p, "Body", bodyCenter, bodySize, body, layer, false, visual, Surface.Wood);
            GameObject corniceGo = PrimitiveKit.Box(p, "Cornice", corniceCenter, corniceSize, doors, layer, false, visual, Surface.Wood);
            float doorW = s.x * 0.5f - 0.015f;
            float doorH = s.y - top - 0.06f;
            float handleY = Handles.HeightOn(0.03f, 0.03f + doorH, 0.12f);
            float handleLength = Mathf.Min(0.24f, doorH * 0.3f);
            bool rest = combine && visual;
            var closed = new PartBatch(p, layer, true);
            Material closedBody = rest ? PrimitiveKit.ShownMaterial(body, Surface.Wood) : null;
            Material closedDoors = rest ? PrimitiveKit.ShownMaterial(doors, Surface.Wood) : null;
            if (rest)
            {
                closed.Box("Body", "Closed", bodyCenter, bodySize, closedBody, true, Surface.Wood);
                closed.Box("Cornice", "Closed", corniceCenter, corniceSize, closedDoors, true, Surface.Wood);
            }
            var animated = new List<GameObject> { bodyGo, corniceGo };
            for (int i = 0; i < 2; i++)
            {
                float side = i == 0 ? -1f : 1f;
                float x = side * (doorW * 0.5f + 0.0075f);
                var doorCenter = new Vector3(x, 0.03f + doorH * 0.5f, s.z * 0.5f - panel * 0.5f);
                var doorSize = new Vector3(doorW, doorH, panel);
                GameObject door = PrimitiveKit.Box(p, "Door" + i, doorCenter, doorSize, doors, layer, false, visual, Surface.Wood);
                animated.Add(door);
                if (!visual)
                {
                    continue;
                }
                // The pull by the doors' meeting edge, on the door's front face (+z).
                var onFace = new Vector3(side * (0.0075f + 0.07f), handleY, s.z * 0.5f);
                Handles.Bar((name, center, size) => Handles.ChildBox(door.transform, name, center, size, layer), "Handle", onFace, 1f, handleLength);
                if (rest)
                {
                    closed.Box("Door" + i, "Closed", doorCenter, doorSize, closedDoors, true, Surface.Wood);
                    Handles.Bar((name, center, size) => closed.Box(name + i, "ClosedHandles", center, size, Handles.Material, true, Surface.Plain), "Handle",
                        onFace, 1f, handleLength);
                }
            }
            if (rest)
            {
                closed.Flush();
                foreach (GameObject part in animated)
                {
                    foreach (Renderer r in part.GetComponentsInChildren<Renderer>(true))
                    {
                        r.enabled = false;
                    }
                }
            }
            if (col)
            {
                var collider = new GameObject("Collider") { layer = layer };
                collider.transform.SetParent(p, false);
                var box = collider.AddComponent<BoxCollider>();
                box.center = new Vector3(0f, s.y * 0.5f, 0f);
                box.size = s;
            }
        }

        /// <summary>
        /// A kitchen counter (M2): a body and a worktop, solid up to its height. M9 soft shapes: the two boxes stay as
        /// collider-only objects (exactly as under a model) and the visual is two rounded meshes, the body's walls with
        /// rounded corners and the worktop with rounded corners and edges, 106 triangles.
        /// </summary>
        private static void Counter(Transform p, Vector3 s, Color main, Color top, int layer, bool col, bool visual)
        {
            const float worktop = 0.04f;
            var bodySize = new Vector3(s.x - 0.02f, s.y - worktop, s.z - 0.02f);
            PrimitiveKit.Box(p, "Body", new Vector3(0f, (s.y - worktop) * 0.5f, 0.01f), bodySize, null, layer, col, false, Surface.Wood);
            PrimitiveKit.Box(p, "Worktop", new Vector3(0f, s.y - worktop * 0.5f, 0f), new Vector3(s.x, worktop, s.z), null, layer, col, false, Surface.Plaster);
            if (visual)
            {
                PrimitiveKit.Part(p, "BodyShape", RoundedMesh.Slab(bodySize, 0.02f, 0f, 0, 0f, 0, 2, false, false), new Vector3(0f, 0f, 0.01f),
                    Quaternion.identity, Vector3.one, Mat(main, 0.2f, true), layer, Surface.Wood);
                PrimitiveKit.Part(p, "WorktopShape", RoundedMesh.Slab(new Vector3(s.x, worktop, s.z), 0.02f, 0.008f, 1, 0.015f, 1, 2, false, true),
                    new Vector3(0f, s.y - worktop, 0f), Quaternion.identity, Vector3.one, Mat(top, 0.5f, true), layer, Surface.Plaster);
            }
        }

        /// <summary>
        /// A potted plant (M2): a pot and a block of foliage, each with its collider. PLANT (2026-11-24): the two boxes
        /// stay as collider-only objects (exactly as under a model, so sight, hearing and the audit are unchanged, whatever
        /// the style) and the visual is one of two plants (<see cref="PropDef.Style"/>, else picked by position): a ficus
        /// (<see cref="FicusMeshes"/>) or a banana plant with seven broad leaf blades (<see cref="BananaMeshes"/>). Both
        /// stand in the same plain glazed round pot in the pot colour (PotShape, no detail: a glaze shows no grain), with
        /// the dark soil and the wood (Trunk, Surface.Soil) and the leaves (Canopy, Surface.Foliage; the banana's blades
        /// carry the leaf chart once each). 3 renderers, meshes cached per size, style and variant.
        /// </summary>
        private static void Plant(Transform p, Vector3 s, Color leaves, Color pot, int layer, bool col, bool visual, string style, int variant)
        {
            float potH = s.y * 0.3f;
            PrimitiveKit.Box(p, "Pot", new Vector3(0f, potH * 0.5f, 0f), new Vector3(s.x * 0.6f, potH, s.z * 0.6f), null, layer, col, false, Surface.Plaster);
            PrimitiveKit.Box(p, "Leaves", new Vector3(0f, potH + (s.y - potH) * 0.5f, 0f), new Vector3(s.x, s.y - potH, s.z),
                null, layer, col, false, Surface.Foliage);
            if (!visual)
            {
                return;
            }
            bool banana = style == PropDef.PlantStyleBanana;
            Mesh[] meshes = banana ? BananaMeshes(s, variant) : FicusMeshes(s, variant);
            PrimitiveKit.Part(p, "PotShape", meshes[0], Vector3.zero, Quaternion.identity, Vector3.one, PrimitiveKit.Lit(pot, 0.6f), layer);
            PrimitiveKit.Part(p, "Trunk", meshes[1], Vector3.zero, Quaternion.identity, Vector3.one, PrimitiveKit.LitSurface(BarkColor, Surface.Soil),
                layer, Surface.Soil);
            GameObject canopy = PrimitiveKit.Part(p, "Canopy", meshes[2], Vector3.zero, Quaternion.identity, Vector3.one,
                PrimitiveKit.LitSurface(leaves, Surface.Foliage), layer, Surface.Foliage);
            if (banana)
            {
                PrimitiveKit.BananaLeafDetail(canopy.GetComponent<MeshRenderer>());
            }
        }

        /// <summary>The shared finish for the stalks and soil.</summary>
        private static readonly Color BarkColor = new Color(0.30f, 0.22f, 0.15f);

        /// <summary>The plant's style: the level's own, else ficus or banana from the prop's position (a deterministic mix).</summary>
        public static string PlantStyleOf(PropDef prop)
        {
            if (!string.IsNullOrEmpty(prop.Style))
            {
                return prop.Style;
            }
            int h = Mathf.RoundToInt(prop.X * 10f) * 13 + Mathf.RoundToInt(prop.Z * 10f) * 7;
            return (h & 1) == 0 ? PropDef.PlantStyleFicus : PropDef.PlantStyleBanana;
        }

        /// <summary>
        /// The round pot both plants stand in, filling the pot box's width: a flared body, a rim band, the rim's top and
        /// its inner lip down to the soil (10 around, as the banana's own pot: 110 triangles), and where the soil disc sits.
        /// </summary>
        private static MeshBuilder PotBuilder(Vector3 s, out float soilY, out float soilR)
        {
            float w = Mathf.Min(s.x, s.z);
            float potH = s.y * 0.3f;
            float top = w * 0.3f;
            float foot = top * 0.74f;
            float rim = Mathf.Min(0.03f, potH * 0.1f);
            soilY = potH - rim * 1.4f;
            soilR = top * 0.85f;
            var pot = new MeshBuilder();
            pot.AddLathe(Matrix4x4.identity, new[]
            {
                new Vector2(foot, 0f), new Vector2(top * 0.94f, potH - rim), new Vector2(top, potH - rim), new Vector2(top, potH),
                new Vector2(top * 0.87f, potH), new Vector2(soilR, soilY),
            }, 10, true, false);
            return pot;
        }

        /// <summary>Names the plant's three meshes, keeps them across level rebuilds and caches them under <paramref name="key"/>.</summary>
        private static Mesh[] KeepPlant(string key, MeshBuilder pot, MeshBuilder wood, MeshBuilder canopy)
        {
            var meshes = new[] { pot.Build(), wood.Build(), canopy.Build() };
            string[] names = { "Plant pot", "Plant trunk", "Plant canopy" };
            for (int i = 0; i < meshes.Length; i++)
            {
                meshes[i].name = names[i];
                meshes[i].hideFlags = HideFlags.DontUnloadUnusedAsset;
            }
            PlantCache[key] = meshes;
            return meshes;
        }

        /// <summary>
        /// A ficus of <paramref name="s"/>: the pot (110 triangles); the soil, a thin trunk up to a fork, a leader to the
        /// crown's top and three branches into its lower clusters (Trunk, 46); a rounded crown of twelve small overlapping
        /// faceted leaf clusters (20 triangles each) spread over an ellipsoid shell (golden angle around, jittered by
        /// <paramref name="variant"/>) inside the leaves box (Canopy, 240): 396 triangles, within the PRD 7.4 furniture
        /// budget (Tuning.BudgetFurnitureTriangles) the audit and the built player probe check on every prop.
        /// </summary>
        private static Mesh[] FicusMeshes(Vector3 s, int variant)
        {
            string key = string.Format(CultureInfo.InvariantCulture, "ficus {0:0.###}x{1:0.###}x{2:0.###}v{3}", s.x, s.y, s.z, variant);
            if (PlantCache.TryGetValue(key, out Mesh[] cached) && cached[0] != null && cached[1] != null && cached[2] != null)
            {
                return cached;
            }
            float w = Mathf.Min(s.x, s.z);
            float potH = s.y * 0.3f;
            float h = s.y - potH;
            MeshBuilder pot = PotBuilder(s, out float soilY, out float soilR);

            const int clusters = 12;
            float radius = w * 0.21f;
            float crownY = s.y - h * 0.33f;
            float shellH = w * 0.5f - radius * 1.1f;
            float shellV = s.y - crownY - radius * 0.9f;
            var centres = new Vector3[clusters];
            var canopy = new MeshBuilder();
            for (int i = 0; i < clusters; i++)
            {
                float j0 = PlantNoise(variant, i, 0);
                float j1 = PlantNoise(variant, i, 1);
                float j2 = PlantNoise(variant, i, 2);
                // From the top down to well under the crown's middle (the bottom of the shell is left to the branches).
                float y = 1f - 1.75f * (i + 0.5f) / clusters;
                float ring = Mathf.Sqrt(Mathf.Max(0f, 1f - y * y));
                float bearing = 137.5f * i + 90f * variant + (j0 - 0.5f) * 30f;
                centres[i] = YawMath.Forward(bearing) * (ring * shellH * (0.85f + 0.3f * j1)) + Vector3.up * (crownY + y * shellV);
                float size = 0.85f + 0.3f * j2;
                var r = new Vector3(radius * size, radius * size * 0.8f, radius * size * (0.9f + 0.2f * j0));
                int cluster = i;
                Matrix4x4 m = Matrix4x4.TRS(centres[i], Quaternion.Euler(0f, PlantNoise(variant, i, 3) * 360f, 0f), Vector3.one);
                canopy.AddBlob(m, r, 5, 3, (band, seg) => 0.86f + 0.28f * PlantNoise(variant, 100 + cluster, band * 16 + seg));
            }

            float trunk = w * 0.035f;
            var fork = new Vector3(0f, potH + h * 0.3f, 0f);
            var wood = new MeshBuilder();
            wood.AddDisc(Matrix4x4.Translate(new Vector3(0f, soilY, 0f)), soilR, 10);
            wood.AddRod(new Vector3(0f, soilY - 0.01f, 0f), fork, trunk, trunk * 0.8f, 5);
            wood.AddRod(fork, Vector3.Lerp(fork, centres[0], 0.8f), trunk * 0.7f, trunk * 0.4f, 4);
            for (int b = 0; b < 3; b++)
            {
                wood.AddRod(fork, Vector3.Lerp(fork, centres[clusters - 1 - b], 0.85f), trunk * 0.6f, trunk * 0.35f, 3);
            }
            return KeepPlant(key, pot, wood, canopy);
        }

        /// <summary>How many shapes of canopy the plants pick from (by their position), so two plants rarely look the same.</summary>
        private const int PlantVariants = 4;

        /// <summary>The canopy shape of a plant prop, from its position (deterministic, the same on every load).</summary>
        private static int PlantVariant(PropDef prop)
        {
            int h = Mathf.RoundToInt(prop.X * 10f) * 31 + Mathf.RoundToInt(prop.Z * 10f) * 17;
            return ((h % PlantVariants) + PlantVariants) % PlantVariants;
        }

        /// <summary>A deterministic value in [0, 1] for (variant, a, b): the plant's jitter.</summary>
        private static float PlantNoise(int variant, int a, int b)
        {
            unchecked
            {
                uint h = (uint)((variant + 1) * 73856093) ^ (uint)((a + 7) * 19349663) ^ (uint)((b + 13) * 83492791);
                h ^= h >> 13;
                h *= 0x5bd1e995;
                h ^= h >> 15;
                return (h & 0xFFFF) / 65535f;
            }
        }

        private static readonly Dictionary<string, Mesh[]> PlantCache = new Dictionary<string, Mesh[]>();

        /// <summary>
        /// BANANA (2026-11-24): the banana plant of <paramref name="s"/>, an open rosette. The pot (110 triangles, its width
        /// capped at <see cref="BananaPotWidth"/> so a wide canopy keeps a sensible pot); the soil, a short pseudostem up to
        /// the crown and one petiole per blade (Trunk, 62); seven broad rounded blades (32 triangles each) that rise from the
        /// crown, arch over and droop outward, the lowest tips down to the pot rim (Canopy, 224): 396 triangles, within the
        /// PRD 7.4 furniture budget (Tuning.BudgetFurnitureTriangles). The blades are laid out in the prop's footprint (a
        /// disc of about 0.93 of its width), so the canopy always stays inside the Leaves box: a banana prop is sized to its
        /// canopy (about 1 x 1 m in the levels, BANANA in docs/next/progress).
        /// </summary>
        private static Mesh[] BananaMeshes(Vector3 s, int variant)
        {
            string key = string.Format(CultureInfo.InvariantCulture, "banana {0:0.###}x{1:0.###}x{2:0.###}v{3}", s.x, s.y, s.z, variant);
            if (PlantCache.TryGetValue(key, out Mesh[] cached) && cached[0] != null && cached[1] != null && cached[2] != null)
            {
                return cached;
            }
            float potW = Mathf.Min(Mathf.Min(s.x, s.z), BananaPotWidth);
            float potH = s.y * 0.3f;
            float h = s.y - potH;
            MeshBuilder pot = PotBuilder(new Vector3(potW, s.y, potW), out float soilY, out float soilR);

            var canopy = new MeshBuilder();
            var wood = new MeshBuilder();
            wood.AddDisc(Matrix4x4.Translate(new Vector3(0f, soilY, 0f)), soilR, 10);
            float trunk = potW * 0.05f;
            Vector3 crown = Vector3.up * (potH + h * 0.45f);
            wood.AddRod(Vector3.up * soilY, crown, trunk, trunk * 0.7f, 5);
            for (int i = 0; i < 7; i++)
            {
                Vector3[] ribs = BananaBlade(s, variant, i, potH, h);
                canopy.AddLeafBlade(ribs);
                Vector3 stem = Vector3.Lerp(Vector3.up * (potH + h * 0.12f), crown, 0.4f + i * 0.1f);
                wood.AddRod(stem, ribs[1], trunk * 0.45f, trunk * 0.22f, 3);
            }
            return KeepPlant(key, pot, wood, canopy);
        }

        /// <summary>The widest pot box (metres) a banana plant stands in, however wide its canopy.</summary>
        private const float BananaPotWidth = 0.6f;

        /// <summary>The blade's half width along its length, base to tip: full and rounded, a blunt tip.</summary>
        private static readonly float[] LeafWidths = { 0f, 0.8f, 1f, 0.98f, 0.8f, 0f };

        /// <summary>
        /// One banana blade as ribs (left edge, midrib, right edge per row, base to tip). Every blade leaves the crown
        /// outward, rises, arches over and droops toward its tip: the outer (first) blades reach to 0.46 of the footprint
        /// and droop to the pot rim, the inner ones stay a little higher and shorter, so the plant reads as a wide open
        /// rosette rather than an upright bunch. Coordinates are fractions of the footprint (x, z) and of the height above
        /// the pot (y), so the whole canopy stays inside the prop's Leaves box.
        /// </summary>
        private static Vector3[] BananaBlade(Vector3 size, int variant, int index, float potHeight, float height)
        {
            float tier = index / 6f;
            float turn = 77f * variant + 137.5f * index + 18f * (PlantNoise(variant, index, 0) - 0.5f);
            Vector3 outward = YawMath.Forward(turn);
            var across = new Vector3(outward.z, 0f, -outward.x);
            float halfWidth = Mathf.Lerp(0.17f, 0.21f, PlantNoise(variant, index, 1));
            float twist = 0.27f * (2f * PlantNoise(variant, index, 2) - 1f);
            float sweep = 0.05f * Mathf.Sin(turn * Mathf.Deg2Rad);
            float reach = Mathf.Lerp(0.46f, 0.34f, tier) - 0.04f * PlantNoise(variant, index, 3);
            float start = Mathf.Lerp(0.40f, 0.70f, tier);
            float rise = Mathf.Lerp(0.30f, 0.28f, tier);
            float droop = Mathf.Lerp(0.40f, 0.34f, tier);
            var ribs = new Vector3[LeafWidths.Length * 3];
            for (int row = 0; row < LeafWidths.Length; row++)
            {
                float t = row / (float)(LeafWidths.Length - 1);
                float spread = Mathf.Lerp(0.07f, reach, t * (1.25f - 0.25f * t));
                float lift = start + rise * Mathf.Sin(Mathf.PI * t) - droop * t * t;
                float width = LeafWidths[row] * halfWidth;
                Vector3 centre = outward * spread + across * (sweep * t * t);
                for (int bladeSide = -1; bladeSide <= 1; bladeSide++)
                {
                    Vector3 footprint = centre + across * (bladeSide * width);
                    float curl = (0.24f * Mathf.Abs(bladeSide) + twist * bladeSide * t) * width;
                    ribs[3 * row + bladeSide + 1] = new Vector3(footprint.x * size.x, potHeight + (lift - curl) * height, footprint.z * size.z);
                }
            }
            return ribs;
        }

        /// <summary>Dining table under a floor length cloth: solid up to its height, as the PRD occluder says.</summary>
        private static void Table(Transform p, Vector3 s, Color cloth, Color wood, int layer, bool col, bool visual)
        {
            const float top = 0.04f;
            PrimitiveKit.Box(p, "Top", new Vector3(0f, s.y - top * 0.5f, 0f), new Vector3(s.x, top, s.z), Mat(wood, 0.45f, visual), layer, col, visual, Surface.Wood);
            PrimitiveKit.Box(p, "Cloth", new Vector3(0f, (s.y - top) * 0.5f + 0.005f, 0f), new Vector3(s.x - 0.04f, s.y - top - 0.01f, s.z - 0.04f),
                Mat(cloth, 0.1f, visual), layer, col, visual, Surface.Linen);
        }
    }
}
