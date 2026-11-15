using System.Collections.Generic;
using System.Globalization;
using Meuble.Core;
using UnityEngine;

namespace Meuble
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
    /// lamp shade, plaster for worktops and pots. Books, leaves and metal stay plain.
    ///
    /// M5 wave 5B (docs/CONTRACT_M5.md 5, 16.11 and 17): the procedural rocking chair (<see cref="RockingChair"/>), and the
    /// budgets counted as material slots: a level build combines a bookshelf's visual parts per material (its frame, then
    /// its books colour by colour), the prop's one collider unchanged.
    /// </summary>
    public static class FurnitureKit
    {
        // Book colors reuse colors already present in the room: every new color is a new material, and
        // the level budget is 24 materials (PRD 7.4). Never red: red belongs to the player chair.
        private static readonly Color[] BookColors =
        {
            new Color32(0xE3, 0xB2, 0x3C, 0xFF), new Color32(0x5B, 0x93, 0xD9, 0xFF), new Color32(0xF7, 0xF4, 0xEE, 0xFF),
            new Color32(0x3F, 0x8F, 0x4F, 0xFF), new Color32(0x8C, 0x5A, 0x36, 0xFF), new Color32(0x2F, 0x6E, 0x4E, 0xFF),
        };

        /// <summary>The player chair: 6 boxes, 72 triangles (PRD 7.1). Facing +z, backrest on the -z side.</summary>
        public static void Chair(Transform parent, Vector3 size, Color color, int layer)
        {
            Material m = PrimitiveKit.Lit(color, 0.35f);
            float seatTop = size.y * 0.53f;
            const float seat = 0.05f;
            const float leg = 0.05f;
            const float back = 0.05f;
            float lx = size.x * 0.5f - leg * 0.5f - 0.01f;
            float lz = size.z * 0.5f - leg * 0.5f - 0.01f;
            float legHeight = seatTop - seat;
            PrimitiveKit.Box(parent, "Seat", new Vector3(0f, seatTop - seat * 0.5f, 0f), new Vector3(size.x, seat, size.z), m, layer, false, Surface.Wood);
            PrimitiveKit.Box(parent, "LegFL", new Vector3(-lx, legHeight * 0.5f, lz), new Vector3(leg, legHeight, leg), m, layer, false, Surface.Wood);
            PrimitiveKit.Box(parent, "LegFR", new Vector3(lx, legHeight * 0.5f, lz), new Vector3(leg, legHeight, leg), m, layer, false, Surface.Wood);
            PrimitiveKit.Box(parent, "LegBL", new Vector3(-lx, legHeight * 0.5f, -lz), new Vector3(leg, legHeight, leg), m, layer, false, Surface.Wood);
            PrimitiveKit.Box(parent, "LegBR", new Vector3(lx, legHeight * 0.5f, -lz), new Vector3(leg, legHeight, leg), m, layer, false, Surface.Wood);
            float backHeight = size.y - seatTop;
            PrimitiveKit.Box(parent, "Backrest", new Vector3(0f, seatTop + backHeight * 0.5f, -size.z * 0.5f + back * 0.5f),
                new Vector3(size.x, backHeight, back), m, layer, false, Surface.Wood);
        }

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
                default:
                    return false;
            }
        }

        /// <summary>
        /// The frame colour of the metal parts (office chair base, lamp pole): the near-black every model of the
        /// household already uses (ModelMath.NearBlack), so it costs no new material in a level with the man.
        /// </summary>
        public static Color FrameColor => ModelMath.NearBlack;

        /// <summary>A stool (fallback of the Kenney bar stool): a seat on four legs, 5 boxes, 60 triangles.</summary>
        public static void Stool(Transform parent, Vector3 size, Color color, int layer)
        {
            Material m = PrimitiveKit.Lit(color, 0.35f);
            const float seat = 0.06f;
            const float leg = 0.04f;
            float legHeight = size.y - seat;
            float lx = size.x * 0.5f - leg * 0.5f - 0.02f;
            float lz = size.z * 0.5f - leg * 0.5f - 0.02f;
            PrimitiveKit.Box(parent, "Seat", new Vector3(0f, size.y - seat * 0.5f, 0f), new Vector3(size.x, seat, size.z), m, layer, false, Surface.Wood);
            PrimitiveKit.Box(parent, "LegFL", new Vector3(-lx, legHeight * 0.5f, lz), new Vector3(leg, legHeight, leg), m, layer, false, Surface.Wood);
            PrimitiveKit.Box(parent, "LegFR", new Vector3(lx, legHeight * 0.5f, lz), new Vector3(leg, legHeight, leg), m, layer, false, Surface.Wood);
            PrimitiveKit.Box(parent, "LegBL", new Vector3(-lx, legHeight * 0.5f, -lz), new Vector3(leg, legHeight, leg), m, layer, false, Surface.Wood);
            PrimitiveKit.Box(parent, "LegBR", new Vector3(lx, legHeight * 0.5f, -lz), new Vector3(leg, legHeight, leg), m, layer, false, Surface.Wood);
        }

        /// <summary>A floor lamp (fallback of the Kenney lamp): a foot, a pole and the shade on top, 3 boxes, 36 triangles.</summary>
        public static void FloorLamp(Transform parent, Vector3 size, Color color, int layer)
        {
            Material shade = PrimitiveKit.Lit(color, 0.35f);
            Material frame = PrimitiveKit.Lit(FrameColor, Tuning.ModelSmoothness);
            const float foot = 0.04f;
            const float pole = 0.035f;
            float shadeHeight = size.y * 0.22f;
            float poleTop = size.y - shadeHeight;
            PrimitiveKit.Box(parent, "Foot", new Vector3(0f, foot * 0.5f, 0f), new Vector3(size.x * 0.8f, foot, size.z * 0.8f), frame, layer, false);
            PrimitiveKit.Box(parent, "Pole", new Vector3(0f, (foot + poleTop) * 0.5f, 0f), new Vector3(pole, poleTop - foot, pole), frame, layer, false);
            PrimitiveKit.Box(parent, "Shade", new Vector3(0f, poleTop + shadeHeight * 0.5f, 0f), new Vector3(size.x, shadeHeight, size.z), shade, layer, false, Surface.Linen);
        }

        /// <summary>The number of spokes and wheels of the office chair base.</summary>
        public const int OfficeChairSpokes = 5;

        /// <summary>
        /// The office chair (no model, CONTRACT_M4 2): a seat, a backrest on -z on its post, a gas column and a
        /// five-spoke base on wheels. Seat and back in <paramref name="color"/>; the metal (hub, spokes, wheels, column,
        /// post) is one mesh in <see cref="FrameColor"/>, so a chair is 3 renderers (level 7 has five of them).
        /// 312 triangles: seat and backrest (24), and the frame: hub and post (24), 5 spokes (60), the column (24),
        /// 5 wheels (180).
        /// </summary>
        public static void OfficeChair(Transform parent, Vector3 size, Color color, int layer)
        {
            Material m = PrimitiveKit.Lit(color, 0.35f);
            Material frame = PrimitiveKit.Lit(FrameColor, Tuning.ModelSmoothness);
            const float seat = 0.07f;
            const float backDepth = 0.06f;
            float seatTop = size.y * 0.5f;
            float backBottom = seatTop + 0.12f;
            float backZ = -size.z * 0.5f + backDepth * 0.5f;
            PrimitiveKit.Part(parent, "Frame", OfficeChairFrame(size), Vector3.zero, Quaternion.identity, Vector3.one, frame, layer);
            PrimitiveKit.Box(parent, "Seat", new Vector3(0f, seatTop - seat * 0.5f, 0f), new Vector3(size.x, seat, size.z), m, layer, false, Surface.Upholstery);
            PrimitiveKit.Box(parent, "Backrest", new Vector3(0f, (backBottom + size.y) * 0.5f, backZ), new Vector3(size.x * 0.9f, size.y - backBottom, backDepth),
                m, layer, false, Surface.Upholstery);
        }

        private static readonly Dictionary<string, Mesh> FrameCache = new Dictionary<string, Mesh>();

        /// <summary>
        /// The metal of an office chair of <paramref name="size"/> as one mesh in the chair's frame (cached by size, kept
        /// across level rebuilds like PrimitiveKit's meshes): the hub, <see cref="OfficeChairSpokes"/> spokes with a wheel
        /// under each tip, the gas column up to the seat, and the backrest post.
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
            const float spokeHeight = 0.03f;
            const float spokeWidth = 0.04f;
            const float seat = 0.07f;
            const float backDepth = 0.06f;
            const float post = 0.05f;
            float seatTop = size.y * 0.5f;
            float spokeY = wheel + spokeHeight * 0.5f;
            float reach = radius - wheel * 0.5f;
            float columnBottom = spokeY + spokeHeight * 0.5f;
            float columnHeight = Mathf.Max(0.06f, seatTop - seat - columnBottom);
            float backBottom = seatTop + 0.12f;
            float backZ = -size.z * 0.5f + backDepth * 0.5f;
            Mesh box = PrimitiveKit.BoxMesh;
            Mesh sphere = PrimitiveKit.SphereMesh(6, 4);
            var parts = new List<CombineInstance>
            {
                Piece(box, new Vector3(0f, spokeY, 0f), Quaternion.identity, new Vector3(0.08f, spokeHeight + 0.01f, 0.08f)),
                Piece(PrimitiveKit.CapsuleMesh(0.025f, columnHeight, 6, 1), new Vector3(0f, columnBottom, 0f), Quaternion.identity, Vector3.one),
                Piece(box, new Vector3(0f, (seatTop + backBottom) * 0.5f + 0.02f, backZ), Quaternion.identity,
                    new Vector3(post, backBottom - seatTop + 0.04f, post * 0.6f)),
            };
            for (int i = 0; i < OfficeChairSpokes; i++)
            {
                float yaw = 180f + i * 360f / OfficeChairSpokes;
                Vector3 direction = YawMath.Forward(yaw);
                parts.Add(Piece(box, direction * (reach * 0.5f) + Vector3.up * spokeY, Quaternion.Euler(0f, yaw, 0f), new Vector3(spokeWidth, spokeHeight, reach)));
                parts.Add(Piece(sphere, direction * reach + Vector3.up * (wheel * 0.5f), Quaternion.identity, Vector3.one * wheel));
            }
            var mesh = new Mesh { name = "OfficeChairFrame" };
            mesh.CombineMeshes(parts.ToArray(), true, true);
            mesh.RecalculateBounds();
            mesh.hideFlags = HideFlags.DontUnloadUnusedAsset;
            FrameCache[key] = mesh;
            return mesh;
        }

        private static CombineInstance Piece(Mesh mesh, Vector3 position, Quaternion rotation, Vector3 scale)
        {
            return new CombineInstance { mesh = mesh, transform = Matrix4x4.TRS(position, rotation, scale) };
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
                    Cabinet(parent, prop.Size, main, accent, layer, col, visual);
                    break;
                case "counter":
                    Counter(parent, prop.Size, main, accent, layer, col, visual);
                    break;
                case "plant":
                    Plant(parent, prop.Size, main, accent, layer, col, visual);
                    break;
                case BodyKinds.Armchair:
                    Armchair(parent, prop.Size, main, accent, layer, col, visual);
                    break;
                default:
                    PrimitiveKit.Box(parent, "Body", new Vector3(0f, prop.SizeY * 0.5f, 0f), prop.Size, Mat(main, 0.25f, visual), layer, col, visual, Surface.Wood);
                    break;
            }
        }

        /// <summary>The accent colour of a prop, as the procedural parts use it (the model red remap target).</summary>
        public static Color AccentOf(PropDef prop)
        {
            Color main = LevelJson.ParseColor(prop.Color, Color.gray);
            return LevelJson.ParseColor(prop.AccentColor, main * 0.8f);
        }

        /// <summary>No material is created for a part that will not be drawn.</summary>
        private static Material Mat(Color color, float smoothness, bool visual) => visual ? PrimitiveKit.Lit(color, smoothness) : null;

        /// <summary>Base, backrest on +z, two arms, two cushions. Colliders on the structural parts.</summary>
        private static void Sofa(Transform p, Vector3 s, Color main, Color accent, int layer, bool col, bool visual)
        {
            Material body = Mat(main, 0.15f, visual);
            Material cushion = Mat(accent, 0.15f, visual);
            float baseH = s.y * 0.5f;
            float backD = Mathf.Min(0.22f, s.z * 0.25f);
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
        /// 5 boxes, 60 triangles.
        /// </summary>
        private static void Armchair(Transform p, Vector3 s, Color main, Color accent, int layer, bool col, bool visual)
        {
            Material body = Mat(main, 0.15f, visual);
            Material cushion = Mat(accent, 0.15f, visual);
            float seatH = s.y * ArmchairSeat;
            float armH = s.y * ArmchairArm;
            float armW = s.x * ArmchairArmWidth;
            float backD = s.z * ArmchairBackDepth;
            float armDepth = s.z - backD;
            // The arms and the cushion run from the front of the backrest to the front edge: centred at +backD / 2.
            float frontZ = backD * 0.5f;
            PrimitiveKit.Box(p, "Base", new Vector3(0f, seatH * 0.5f, 0f), new Vector3(s.x, seatH, s.z), body, layer, col, visual, Surface.Upholstery);
            PrimitiveKit.Box(p, "Backrest", new Vector3(0f, seatH + (s.y - seatH) * 0.5f, -s.z * 0.5f + backD * 0.5f),
                new Vector3(s.x, s.y - seatH, backD), body, layer, col, visual, Surface.Upholstery);
            PrimitiveKit.Box(p, "ArmL", new Vector3(-s.x * 0.5f + armW * 0.5f, seatH + (armH - seatH) * 0.5f, frontZ),
                new Vector3(armW, armH - seatH, armDepth), body, layer, col, visual, Surface.Upholstery);
            PrimitiveKit.Box(p, "ArmR", new Vector3(s.x * 0.5f - armW * 0.5f, seatH + (armH - seatH) * 0.5f, frontZ),
                new Vector3(armW, armH - seatH, armDepth), body, layer, col, visual, Surface.Upholstery);
            float cushionH = Mathf.Min(0.1f, armH - seatH - 0.02f);
            PrimitiveKit.Box(p, "Cushion", new Vector3(0f, seatH + cushionH * 0.5f, frontZ),
                new Vector3(s.x - 2f * armW - 0.02f, cushionH, armDepth - 0.04f), cushion, layer, false, visual, Surface.Upholstery);
        }

        /// <summary>
        /// A full occluder (PRD 6.3): one collider over the whole box, open shelves and books for the look. M5 wave 5B: with
        /// <paramref name="combine"/>, its 24 boxes draw as one renderer per material ("Frame", then "Books" and the colour),
        /// 7 draw calls instead of 24, the same triangles.
        /// </summary>
        private static void Bookshelf(Transform p, Vector3 s, Color wood, Color accent, int layer, bool col, bool visual, bool combine)
        {
            Material m = Mat(wood, 0.2f, visual);
            const float panel = 0.04f;
            const float shelf = 0.03f;
            float innerW = s.x - 2f * panel;
            var parts = new PartBatch(p, layer, combine && visual); // MUTATION:SHELF_COMBINE
            parts.Box("SideL", "Frame", new Vector3(-s.x * 0.5f + panel * 0.5f, s.y * 0.5f, 0f), new Vector3(panel, s.y, s.z), m, visual, Surface.Wood);
            parts.Box("SideR", "Frame", new Vector3(s.x * 0.5f - panel * 0.5f, s.y * 0.5f, 0f), new Vector3(panel, s.y, s.z), m, visual, Surface.Wood);
            parts.Box("Back", "Frame", new Vector3(0f, s.y * 0.5f, s.z * 0.5f - 0.01f), new Vector3(innerW, s.y, 0.02f), m, visual, Surface.Wood);
            const int levels = 4;
            float pitch = (s.y - shelf) / levels;
            for (int i = 0; i <= levels; i++)
            {
                parts.Box("Shelf" + i, "Frame", new Vector3(0f, shelf * 0.5f + i * pitch, -0.01f), new Vector3(innerW, shelf, s.z - 0.02f), m, visual, Surface.Wood);
            }
            // Four books per level, deterministic widths and heights, so every build looks the same.
            float[] widths = { 0.30f, 0.22f, 0.34f, 0.26f };
            float[] heights = { 0.78f, 0.62f, 0.86f, 0.70f };
            for (int level = 0; level < levels; level++)
            {
                float x = -innerW * 0.5f + 0.04f + 0.05f * (level % 2);
                for (int b = 0; b < 4; b++)
                {
                    float w = widths[(b + level) % 4] * innerW / 1.52f * 0.95f;
                    float h = (pitch - shelf) * heights[(b + 2 * level) % 4];
                    if (x + w > innerW * 0.5f - 0.02f)
                    {
                        break;
                    }
                    Color c = b == 0 ? accent : BookColors[(b + level * 2) % BookColors.Length];
                    parts.Box($"Books{level}_{b}", "Books " + ColorUtility.ToHtmlStringRGB(c),
                        new Vector3(x + w * 0.5f, shelf + level * pitch + h * 0.5f, 0.0f),
                        new Vector3(w - 0.01f, h, s.z * 0.7f), Mat(c, 0.3f, visual), visual, Surface.Plain);
                    x += w + 0.03f;
                }
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

        /// <summary>The boxes of each curved runner of the procedural rocking chair.</summary>
        public const int RockerSegments = 4;

        /// <summary>How far the runners' ends rise above their middle (metres): the curve the chair rocks on.</summary>
        public const float RockerRise = 0.06f;

        /// <summary>
        /// The procedural rocking chair (CONTRACT_M5 5, used when no model exists): two curved runners along z (each
        /// <see cref="RockerSegments"/> boxes on a parabola, lowest and touching the floor at the middle, <see cref="RockerRise"/>
        /// higher at the ends), four legs from the runners to the seat, the seat, two back posts leaning back from the rear legs
        /// and the back panel between them on -z, two arms on their front posts. Facing +z with its back on -z, within its box,
        /// in one colour of wood and one mesh: one renderer (one draw call), 20 boxes, 240 triangles (PRD 7.4: 400).
        /// </summary>
        public static void RockingChair(Transform parent, Vector3 size, Color color, int layer)
        {
            PrimitiveKit.Part(parent, "RockingChair", RockingChairMesh(size), Vector3.zero, Quaternion.identity, Vector3.one,
                PrimitiveKit.Lit(color, 0.35f), layer, Surface.Wood);
        }

        /// <summary>The boxes of <see cref="RockingChair"/> as one mesh in the chair's frame (UVs in metres; cached by its parts).</summary>
        public static Mesh RockingChairMesh(Vector3 size)
        {
            float w = size.x;
            float h = size.y;
            float d = size.z;
            const float runner = 0.04f;
            const float leg = 0.04f;
            const float seat = 0.05f;
            const float post = 0.04f;
            const float lean = 12f;
            var parts = new List<PrimitiveKit.CombinePart>();
            void Add(Vector3 center, Quaternion rotation, Vector3 box)
            {
                parts.Add(new PrimitiveKit.CombinePart { Mesh = PrimitiveKit.BoxMeshSized(box), Matrix = Matrix4x4.TRS(center, rotation, box) });
            }
            // The runners: their centre line at y = runner / 2 + rise * (2 z / d)^2, ending a centimetre inside the box.
            float half = d * 0.5f - 0.01f;
            float RunnerY(float z) => runner * 0.5f + RockerRise * (2f * z / d) * (2f * z / d);
            float sideX = w * 0.5f - runner * 0.5f;
            foreach (float side in new[] { -1f, 1f })
            {
                for (int i = 0; i < RockerSegments; i++)
                {
                    float z0 = -half + 2f * half * i / RockerSegments;
                    float z1 = -half + 2f * half * (i + 1) / RockerSegments;
                    var a = new Vector3(side * sideX, RunnerY(z0), z0);
                    var b = new Vector3(side * sideX, RunnerY(z1), z1);
                    Vector3 along = b - a;
                    // Each box overlaps its neighbour by a centimetre, so the bend shows no gap.
                    Add((a + b) * 0.5f, Quaternion.LookRotation(along.normalized, Vector3.up), new Vector3(runner, runner, along.magnitude + 0.01f));
                }
            }
            // The seat, and the four legs from the runners' tops up to it.
            float seatTop = h * 0.45f;
            Add(new Vector3(0f, seatTop - seat * 0.5f, d * 0.05f), Quaternion.identity, new Vector3(w, seat, d * 0.6f));
            float legZ = d * 0.22f;
            float legBottom = RunnerY(legZ) + runner * 0.5f;
            float legTop = seatTop - seat;
            foreach (float side in new[] { -1f, 1f })
            {
                foreach (float z in new[] { -legZ, legZ })
                {
                    Add(new Vector3(side * sideX, (legBottom + legTop) * 0.5f, z), Quaternion.identity, new Vector3(leg, legTop - legBottom, leg));
                }
            }
            // The back posts lean back by `lean` degrees from the rear legs up to the full height; the panel spans their upper part.
            Quaternion tilt = Quaternion.Euler(-lean, 0f, 0f);
            Vector3 up = tilt * Vector3.up;
            float postLength = (h - 0.01f - legTop) / up.y;
            foreach (float side in new[] { -1f, 1f })
            {
                var start = new Vector3(side * sideX, legTop, -legZ);
                Add(start + up * (postLength * 0.5f), tilt, new Vector3(post, postLength, post));
            }
            float panelFrom = (seatTop + 0.15f - legTop) / up.y;
            float panelTo = postLength - 0.03f;
            Vector3 panelCenter = new Vector3(0f, legTop, -legZ) + up * ((panelFrom + panelTo) * 0.5f);
            Add(panelCenter, tilt, new Vector3(w - 2f * post, panelTo - panelFrom, 0.025f));
            // The arms, from the back posts to the front, each on its front post.
            float armY = seatTop + 0.2f;
            float armBack = -legZ - (armY - legTop) / up.y * Mathf.Sin(lean * Mathf.Deg2Rad);
            float armFront = d * 0.3f;
            float armX = w * 0.5f - 0.025f;
            foreach (float side in new[] { -1f, 1f })
            {
                Add(new Vector3(side * armX, armY, (armBack + armFront) * 0.5f), Quaternion.identity, new Vector3(0.05f, 0.03f, armFront - armBack));
                float supportTop = armY - 0.015f;
                Add(new Vector3(side * armX, (seatTop + supportTop) * 0.5f, armFront - 0.04f), Quaternion.identity,
                    new Vector3(0.03f, supportTop - seatTop, 0.03f));
            }
            return PrimitiveKit.CombinedMesh(parts);
        }

        /// <summary>
        /// A dresser or tall cupboard (M2): a full occluder up to its height, one collider over the whole box,
        /// two door panels on the front (-z). 4 boxes, 48 triangles.
        /// </summary>
        private static void Cabinet(Transform p, Vector3 s, Color wood, Color accent, int layer, bool col, bool visual)
        {
            Material body = Mat(wood, 0.25f, visual);
            Material doors = Mat(accent, 0.3f, visual);
            const float top = 0.04f;
            const float panel = 0.02f;
            PrimitiveKit.Box(p, "Body", new Vector3(0f, (s.y - top) * 0.5f, 0f), new Vector3(s.x, s.y - top, s.z), body, layer, false, visual, Surface.Wood);
            PrimitiveKit.Box(p, "Top", new Vector3(0f, s.y - top * 0.5f, 0f), new Vector3(s.x, top, s.z), doors, layer, false, visual, Surface.Wood);
            float doorW = s.x * 0.5f - 0.05f;
            float doorH = (s.y - top) * 0.82f;
            for (int i = 0; i < 2; i++)
            {
                float x = (i == 0 ? -1f : 1f) * (doorW * 0.5f + 0.02f);
                PrimitiveKit.Box(p, "Door" + i, new Vector3(x, (s.y - top) * 0.5f + 0.02f, -s.z * 0.5f + panel * 0.5f),
                    new Vector3(doorW, doorH, panel), doors, layer, false, visual, Surface.Wood);
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

        /// <summary>A kitchen counter (M2): a body and a worktop, solid up to its height. 2 boxes.</summary>
        private static void Counter(Transform p, Vector3 s, Color main, Color top, int layer, bool col, bool visual)
        {
            const float worktop = 0.04f;
            PrimitiveKit.Box(p, "Body", new Vector3(0f, (s.y - worktop) * 0.5f, 0.01f), new Vector3(s.x - 0.02f, s.y - worktop, s.z - 0.02f),
                Mat(main, 0.2f, visual), layer, col, visual, Surface.Wood);
            PrimitiveKit.Box(p, "Worktop", new Vector3(0f, s.y - worktop * 0.5f, 0f), new Vector3(s.x, worktop, s.z), Mat(top, 0.5f, visual), layer, col, visual, Surface.Plaster);
        }

        /// <summary>A potted plant (M2): a pot and a block of foliage, each with its collider. 2 boxes.</summary>
        private static void Plant(Transform p, Vector3 s, Color leaves, Color pot, int layer, bool col, bool visual)
        {
            float potH = s.y * 0.3f;
            PrimitiveKit.Box(p, "Pot", new Vector3(0f, potH * 0.5f, 0f), new Vector3(s.x * 0.6f, potH, s.z * 0.6f), Mat(pot, 0.3f, visual), layer, col, visual, Surface.Plaster);
            PrimitiveKit.Box(p, "Leaves", new Vector3(0f, potH + (s.y - potH) * 0.5f, 0f), new Vector3(s.x, s.y - potH, s.z),
                Mat(leaves, 0.15f, visual), layer, col, visual);
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
