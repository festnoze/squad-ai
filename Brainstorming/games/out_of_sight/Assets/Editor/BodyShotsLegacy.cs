using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight.Editor
{
    /// <summary>
    /// The procedural bodies as they were before the soft movers pass (2026-11-20): boxes, a capsule and spheres. Editor only,
    /// for BodyShots' "before" pictures; the game never builds them.
    /// </summary>
    internal static class BodyShotsLegacy
    {
        private static Material Main(Color color) => ModelMath.IsRed(color) ? PrimitiveKit.LitSurface(color, Surface.Lacquer) : PrimitiveKit.Lit(color, 0.35f);

        private static Surface MainSurface(Color color, Surface normal) => ModelMath.IsRed(color) ? Surface.Lacquer : normal;

        public static void Body(string kind, Transform parent, Vector3 size, Color color, int layer)
        {
            switch (BodyKinds.Of(kind))
            {
                case BodyKinds.Stool:
                    Stool(parent, size, color, layer);
                    break;
                case BodyKinds.Armchair:
                    Armchair(parent, size, color, layer);
                    break;
                case BodyKinds.FloorLamp:
                    FloorLamp(parent, size, color, layer);
                    break;
                case BodyKinds.OfficeChair:
                    OfficeChair(parent, size, color, layer);
                    break;
                case BodyKinds.RockingChair:
                    PrimitiveKit.Part(parent, "RockingChair", RockingChairMesh(size), Vector3.zero, Quaternion.identity, Vector3.one, Main(color), layer,
                        MainSurface(color, Surface.Wood));
                    break;
                default:
                    Chair(parent, size, color, layer);
                    break;
            }
        }

        private static void Chair(Transform parent, Vector3 size, Color color, int layer)
        {
            Material m = Main(color);
            Surface wood = MainSurface(color, Surface.Wood);
            float seatTop = size.y * 0.53f;
            const float seat = 0.05f;
            const float leg = 0.05f;
            const float back = 0.05f;
            float lx = size.x * 0.5f - leg * 0.5f - 0.01f;
            float lz = size.z * 0.5f - leg * 0.5f - 0.01f;
            float legHeight = seatTop - seat;
            PrimitiveKit.Box(parent, "Seat", new Vector3(0f, seatTop - seat * 0.5f, 0f), new Vector3(size.x, seat, size.z), m, layer, false, wood);
            foreach (Vector2 at in new[] { new Vector2(-lx, lz), new Vector2(lx, lz), new Vector2(-lx, -lz), new Vector2(lx, -lz) })
            {
                PrimitiveKit.Box(parent, "Leg", new Vector3(at.x, legHeight * 0.5f, at.y), new Vector3(leg, legHeight, leg), m, layer, false, wood);
            }
            float backHeight = size.y - seatTop;
            PrimitiveKit.Box(parent, "Backrest", new Vector3(0f, seatTop + backHeight * 0.5f, -size.z * 0.5f + back * 0.5f),
                new Vector3(size.x, backHeight, back), m, layer, false, wood);
        }

        private static void Stool(Transform parent, Vector3 size, Color color, int layer)
        {
            Material m = Main(color);
            Surface wood = MainSurface(color, Surface.Wood);
            const float seat = 0.06f;
            const float leg = 0.04f;
            float legHeight = size.y - seat;
            float lx = size.x * 0.5f - leg * 0.5f - 0.02f;
            float lz = size.z * 0.5f - leg * 0.5f - 0.02f;
            PrimitiveKit.Box(parent, "Seat", new Vector3(0f, size.y - seat * 0.5f, 0f), new Vector3(size.x, seat, size.z), m, layer, false, wood);
            foreach (Vector2 at in new[] { new Vector2(-lx, lz), new Vector2(lx, lz), new Vector2(-lx, -lz), new Vector2(lx, -lz) })
            {
                PrimitiveKit.Box(parent, "Leg", new Vector3(at.x, legHeight * 0.5f, at.y), new Vector3(leg, legHeight, leg), m, layer, false, wood);
            }
        }

        private static void FloorLamp(Transform parent, Vector3 size, Color color, int layer)
        {
            Material frame = PrimitiveKit.LitSurface(FurnitureKit.FrameColor, Surface.Metal);
            const float foot = 0.04f;
            const float pole = 0.035f;
            float shadeHeight = size.y * 0.22f;
            float poleTop = size.y - shadeHeight;
            PrimitiveKit.Box(parent, "Foot", new Vector3(0f, foot * 0.5f, 0f), new Vector3(size.x * 0.8f, foot, size.z * 0.8f), frame, layer, false, Surface.Metal);
            PrimitiveKit.Box(parent, "Pole", new Vector3(0f, (foot + poleTop) * 0.5f, 0f), new Vector3(pole, poleTop - foot, pole), frame, layer, false, Surface.Metal);
            PrimitiveKit.Box(parent, "Shade", new Vector3(0f, poleTop + shadeHeight * 0.5f, 0f), new Vector3(size.x, shadeHeight, size.z), Main(color), layer, false,
                MainSurface(color, Surface.Linen));
        }

        private static void Armchair(Transform p, Vector3 s, Color color, int layer)
        {
            Material body = ModelMath.IsRed(color) ? PrimitiveKit.LitSurface(color, Surface.Lacquer) : PrimitiveKit.Lit(color, 0.15f);
            Surface surface = MainSurface(color, Surface.Upholstery);
            float seatH = s.y * 0.5f;
            float armH = s.y * 0.75f;
            float armW = s.x * 0.19f;
            float backD = s.z * 0.22f;
            float armDepth = s.z - backD;
            float frontZ = backD * 0.5f;
            PrimitiveKit.Box(p, "Base", new Vector3(0f, seatH * 0.5f, 0f), new Vector3(s.x, seatH, s.z), body, layer, false, surface);
            PrimitiveKit.Box(p, "Backrest", new Vector3(0f, seatH + (s.y - seatH) * 0.5f, -s.z * 0.5f + backD * 0.5f), new Vector3(s.x, s.y - seatH, backD), body, layer, false,
                surface);
            PrimitiveKit.Box(p, "ArmL", new Vector3(-s.x * 0.5f + armW * 0.5f, seatH + (armH - seatH) * 0.5f, frontZ), new Vector3(armW, armH - seatH, armDepth), body,
                layer, false, surface);
            PrimitiveKit.Box(p, "ArmR", new Vector3(s.x * 0.5f - armW * 0.5f, seatH + (armH - seatH) * 0.5f, frontZ), new Vector3(armW, armH - seatH, armDepth), body,
                layer, false, surface);
            float cushionH = Mathf.Min(0.1f, armH - seatH - 0.02f);
            PrimitiveKit.Box(p, "Cushion", new Vector3(0f, seatH + cushionH * 0.5f, frontZ), new Vector3(s.x - 2f * armW - 0.02f, cushionH, armDepth - 0.04f), body,
                layer, false, surface);
        }

        private static void OfficeChair(Transform parent, Vector3 size, Color color, int layer)
        {
            Material m = Main(color);
            Surface upholstery = MainSurface(color, Surface.Upholstery);
            Material frame = PrimitiveKit.LitSurface(FurnitureKit.FrameColor, Surface.Metal);
            const float seat = 0.07f;
            const float backDepth = 0.06f;
            float seatTop = size.y * 0.5f;
            float backBottom = seatTop + 0.12f;
            float backZ = -size.z * 0.5f + backDepth * 0.5f;
            PrimitiveKit.Part(parent, "Frame", OfficeChairFrame(size), Vector3.zero, Quaternion.identity, Vector3.one, frame, layer, Surface.Metal);
            PrimitiveKit.Box(parent, "Seat", new Vector3(0f, seatTop - seat * 0.5f, 0f), new Vector3(size.x, seat, size.z), m, layer, false, upholstery);
            PrimitiveKit.Box(parent, "Backrest", new Vector3(0f, (backBottom + size.y) * 0.5f, backZ), new Vector3(size.x * 0.9f, size.y - backBottom, backDepth),
                m, layer, false, upholstery);
        }

        private static Mesh OfficeChairFrame(Vector3 size)
        {
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
            CombineInstance Piece(Mesh mesh, Vector3 position, Quaternion rotation, Vector3 scale) =>
                new CombineInstance { mesh = mesh, transform = Matrix4x4.TRS(position, rotation, scale) };
            var parts = new List<CombineInstance>
            {
                Piece(box, new Vector3(0f, spokeY, 0f), Quaternion.identity, new Vector3(0.08f, spokeHeight + 0.01f, 0.08f)),
                Piece(PrimitiveKit.CapsuleMesh(0.025f, columnHeight, 6, 1), new Vector3(0f, columnBottom, 0f), Quaternion.identity, Vector3.one),
                Piece(box, new Vector3(0f, (seatTop + backBottom) * 0.5f + 0.02f, backZ), Quaternion.identity, new Vector3(post, backBottom - seatTop + 0.04f, post * 0.6f)),
            };
            for (int i = 0; i < FurnitureKit.OfficeChairSpokes; i++)
            {
                float yaw = 180f + i * 360f / FurnitureKit.OfficeChairSpokes;
                Vector3 direction = YawMath.Forward(yaw);
                parts.Add(Piece(box, direction * (reach * 0.5f) + Vector3.up * spokeY, Quaternion.Euler(0f, yaw, 0f), new Vector3(spokeWidth, spokeHeight, reach)));
                parts.Add(Piece(sphere, direction * reach + Vector3.up * (wheel * 0.5f), Quaternion.identity, Vector3.one * wheel));
            }
            var mesh = new Mesh { name = "LegacyOfficeChairFrame" };
            mesh.CombineMeshes(parts.ToArray(), true, true);
            mesh.RecalculateBounds();
            return mesh;
        }

        private static Mesh legacyShell;

        /// <summary>The robot's old shell: a lathe of 20 sides with one chamfer at its bottom and one at its top edge, normals per profile segment.</summary>
        public static Mesh RobotShell()
        {
            if (legacyShell != null)
            {
                return legacyShell;
            }
            const int segments = 20;
            float r = Tuning.RobotRadius - 0.006f;
            const float clearance = 0.012f;
            float top = Tuning.RobotHeight - 0.012f;
            Vector2[] profile = { new Vector2(r - 0.01f, clearance), new Vector2(r, clearance + 0.01f), new Vector2(r, top - 0.008f), new Vector2(r - 0.008f, top) };
            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var uvs = new List<Vector2>();
            var triangles = new List<int>();
            void Quad(int a, int b, int c, int d, Vector3 facing)
            {
                foreach ((int i, int j, int k) in new[] { (a, b, c), (a, c, d) })
                {
                    Vector3 n = Vector3.Cross(vertices[j] - vertices[i], vertices[k] - vertices[i]);
                    triangles.AddRange(Vector3.Dot(n, facing) >= 0f ? new[] { i, j, k } : new[] { i, k, j });
                }
            }
            for (int p = 0; p + 1 < profile.Length; p++)
            {
                Vector2 a = profile[p];
                Vector2 b = profile[p + 1];
                Vector2 along = (b - a).normalized;
                var n2 = new Vector2(along.y, -along.x);
                int start = vertices.Count;
                for (int s = 0; s <= segments; s++)
                {
                    float angle = 2f * Mathf.PI * s / segments;
                    var dir = new Vector3(Mathf.Sin(angle), 0f, Mathf.Cos(angle));
                    Vector3 normal = (dir * n2.x + Vector3.up * n2.y).normalized;
                    vertices.Add(dir * a.x + Vector3.up * a.y);
                    vertices.Add(dir * b.x + Vector3.up * b.y);
                    normals.Add(normal);
                    normals.Add(normal);
                    uvs.Add(new Vector2(angle * a.x, a.y));
                    uvs.Add(new Vector2(angle * b.x, b.y));
                }
                for (int s = 0; s < segments; s++)
                {
                    int i0 = start + 2 * s;
                    float mid = 2f * Mathf.PI * (s + 0.5f) / segments;
                    Quad(i0, i0 + 2, i0 + 3, i0 + 1, new Vector3(Mathf.Sin(mid), 0f, Mathf.Cos(mid)) * n2.x + Vector3.up * n2.y);
                }
            }
            foreach ((Vector2 ring, bool up) in new[] { (profile[0], false), (profile[profile.Length - 1], true) })
            {
                Vector3 n = up ? Vector3.up : Vector3.down;
                int centre = vertices.Count;
                vertices.Add(new Vector3(0f, ring.y, 0f));
                normals.Add(n);
                uvs.Add(Vector2.zero);
                for (int s = 0; s <= segments; s++)
                {
                    float angle = 2f * Mathf.PI * s / segments;
                    var at = new Vector3(Mathf.Sin(angle) * ring.x, ring.y, Mathf.Cos(angle) * ring.x);
                    vertices.Add(at);
                    normals.Add(n);
                    uvs.Add(new Vector2(at.x, at.z));
                }
                for (int s = 0; s < segments; s++)
                {
                    int a = centre;
                    int b = centre + 1 + s;
                    int c = centre + 2 + s;
                    Vector3 face = Vector3.Cross(vertices[b] - vertices[a], vertices[c] - vertices[a]);
                    triangles.AddRange(Vector3.Dot(face, n) >= 0f ? new[] { a, b, c } : new[] { a, c, b });
                }
            }
            legacyShell = new Mesh { name = "LegacyRobotShell" };
            legacyShell.SetVertices(vertices);
            legacyShell.SetNormals(normals);
            legacyShell.SetUVs(0, uvs);
            legacyShell.SetTriangles(triangles, 0);
            legacyShell.RecalculateBounds();
            return legacyShell;
        }

        private static Mesh RockingChairMesh(Vector3 size)
        {
            float w = size.x;
            float h = size.y;
            float d = size.z;
            const float runner = 0.04f;
            const float leg = 0.04f;
            const float seat = 0.05f;
            const float post = 0.04f;
            const float lean = 12f;
            const int segments = 4;
            var parts = new List<PrimitiveKit.CombinePart>();
            void Add(Vector3 center, Quaternion rotation, Vector3 box)
            {
                parts.Add(new PrimitiveKit.CombinePart { Mesh = PrimitiveKit.BoxMeshSized(box), Matrix = Matrix4x4.TRS(center, rotation, box) });
            }
            float half = d * 0.5f - 0.01f;
            float RunnerY(float z) => runner * 0.5f + FurnitureKit.RockerRise * (2f * z / d) * (2f * z / d);
            float sideX = w * 0.5f - runner * 0.5f;
            foreach (float side in new[] { -1f, 1f })
            {
                for (int i = 0; i < segments; i++)
                {
                    float z0 = -half + 2f * half * i / segments;
                    float z1 = -half + 2f * half * (i + 1) / segments;
                    var a = new Vector3(side * sideX, RunnerY(z0), z0);
                    var b = new Vector3(side * sideX, RunnerY(z1), z1);
                    Vector3 along = b - a;
                    Add((a + b) * 0.5f, Quaternion.LookRotation(along.normalized, Vector3.up), new Vector3(runner, runner, along.magnitude + 0.01f));
                }
            }
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
            float armY = seatTop + 0.2f;
            float armBack = -legZ - (armY - legTop) / up.y * Mathf.Sin(lean * Mathf.Deg2Rad);
            float armFront = d * 0.3f;
            float armX = w * 0.5f - 0.025f;
            foreach (float side in new[] { -1f, 1f })
            {
                Add(new Vector3(side * armX, armY, (armBack + armFront) * 0.5f), Quaternion.identity, new Vector3(0.05f, 0.03f, armFront - armBack));
                float supportTop = armY - 0.015f;
                Add(new Vector3(side * armX, (seatTop + supportTop) * 0.5f, armFront - 0.04f), Quaternion.identity, new Vector3(0.03f, supportTop - seatTop, 0.03f));
            }
            return PrimitiveKit.CombinedMesh(parts);
        }
    }
}
