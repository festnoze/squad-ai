using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>
    /// Garden backdrop (product owner image of 2026-11-19, Assets/Art/Environment/garden_open_horizontal_tile.png,
    /// docs/LICENSES.md, docs/m9/backdrop/NOTES.md): a ring around every house (and the title house), an open cylinder
    /// showing the owner's garden panorama on its inside, repeated around the circle, so the horizon closes on a garden
    /// instead of grass running into the dark void.
    ///
    /// <list type="bullet">
    /// <item>Size (<see cref="RingFor"/>): centred on the house's interior centre (as the garden quad); its radius is the
    /// farthest point the camera's focus can reach (the interior, the props, the exit zone, plus
    /// <see cref="FootprintMargin"/>) plus the camera's longest horizontal arm (OrbitCamera.MaxDistanceFor at
    /// Tuning.PitchMin) plus <see cref="CameraClearance"/>; its height is at least the camera's highest eye (the highest
    /// floor, half the player's body, Tuning.CameraTargetHeight, the arm at Tuning.PitchMax) plus <see cref="HeadRoom"/>, so
    /// the camera never sees over it. The picture keeps its aspect: the repeat count is the circumference over the wanted
    /// height times the picture's aspect, rounded down, and the height then follows from it (never lower than wanted).
    /// OrbitCamera keeps the camera inside (<see cref="ClampArm"/>) and its far clip past the ring (<see cref="Ring.FarClip"/>).</item>
    /// <item>Look: unlit (no shadow cast or received, no dark side), the picture's sky made uniform at its top
    /// (<see cref="SkyTop"/>, tools/assets/make_garden_backdrop.py), which is also the camera's clear colour
    /// (<see cref="ClearColour"/>, Main), so the ring's top edge melts into the sky.</item>
    /// <item>Budget (PRD 7.4): one renderer of one slot, drawn with the window pane's own material (the cached unlit
    /// PrimitiveKit.Emissive one every level already has for its windows) through a property block (<see cref="Block"/>),
    /// as <see cref="WindowImage"/>: no level gains a material, one draw call.</item>
    /// <item>Gameplay: no collider, the Default layer (no occluder, chair blocker or NavMesh source), never registered
    /// with the wall fader: vision, raycasts and navigation never see it.</item>
    /// </list>
    ///
    /// Shipped file: Assets/Resources/GardenBackdrop.png (1024 x 1024, wraps horizontally, repeat in U and clamp in V).
    /// With TextureLibrary.Disabled or without the picture there is no ring.
    /// </summary>
    public static class GardenBackdrop
    {
        /// <summary>The picture's path under Resources.</summary>
        public const string ResourcePath = "GardenBackdrop";

        /// <summary>The ring's renderer name under the level root.</summary>
        public const string RendererName = "GardenBackdrop";

        /// <summary>Facets around the circle (one mesh: 2 x (Segments + 1) vertices, 2 x Segments triangles).</summary>
        public const int Segments = 72;

        /// <summary>The picture's width over its height (1024 x 1024).</summary>
        public const float ImageAspect = 1f;

        /// <summary>Added around the focus footprint (walls, the chair stepping out on the exit, the smoothing lag).</summary>
        public const float FootprintMargin = 1.5f;

        /// <summary>Between the camera's farthest reach and the ring, in metres.</summary>
        public const float CameraClearance = 2.5f;

        /// <summary>Between the camera's highest eye and the ring's top, in metres.</summary>
        public const float HeadRoom = 1.5f;

        /// <summary>The ring's foot below y = 0 (under the garden quad at -0.02, so no gap shows).</summary>
        public const float Sink = 0.06f;

        /// <summary>The picture's colour factor (sRGB, the base colour through the block): at most 1, never in the bloom.</summary>
        public const float Intensity = 1f;

        /// <summary>
        /// The picture's uniform sky at its top (sRGB, tools/assets/make_garden_backdrop.py SKY), times
        /// <see cref="Intensity"/> the camera's clear colour.
        /// </summary>
        public static readonly Color SkyTop = new Color32(127, 190, 253, 255);

        /// <summary>The camera's clear colour: the ring's top sky as the unlit ring draws it.</summary>
        public static Color ClearColour
        {
            get
            {
                float k = new Color(Intensity, Intensity, Intensity).linear.r;
                Color sky = SkyTop.linear;
                return new Color(sky.r * k, sky.g * k, sky.b * k, 1f).gamma;
            }
        }

        private static readonly int BaseMapId = Shader.PropertyToID("_BaseMap");
        private static readonly int BaseMapStId = Shader.PropertyToID("_BaseMap_ST");
        private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");

        private static readonly Dictionary<string, Mesh> Meshes = new Dictionary<string, Mesh>();
        private static Texture2D texture;
        private static bool loaded;
        private static MaterialPropertyBlock block;

        /// <summary>The size of one level's ring (see <see cref="RingFor"/>).</summary>
        public readonly struct Ring
        {
            /// <summary>The ring's axis at the ground (y = 0).</summary>
            public readonly Vector3 Center;
            public readonly float Radius;
            /// <summary>From the foot (y = -<see cref="Sink"/>) to the top.</summary>
            public readonly float Height;
            public readonly int Repeats;
            /// <summary>The camera may stand this far from the axis at most (OrbitCamera's clamp).</summary>
            public readonly float CameraRadius;
            /// <summary>The camera's eye may stand this high at most.</summary>
            public readonly float CameraTop;

            public Ring(Vector3 center, float radius, float height, int repeats, float cameraRadius, float cameraTop)
            {
                Center = center;
                Radius = radius;
                Height = height;
                Repeats = repeats;
                CameraRadius = cameraRadius;
                CameraTop = cameraTop;
            }

            /// <summary>The top edge's height (y).</summary>
            public float Top => Height - Sink;

            /// <summary>A far clip that holds the whole ring from any camera inside it.</summary>
            public float FarClip => Mathf.Sqrt(4f * Radius * Radius + Height * Height) + 2f;

            /// <summary>True when <paramref name="point"/> lies inside the ring's camera space (radius and top).</summary>
            public bool HoldsCamera(Vector3 point)
            {
                Vector2 d = new Vector2(point.x - Center.x, point.z - Center.z);
                return d.magnitude <= CameraRadius + 1e-3f && point.y <= CameraTop + 1e-3f;
            }
        }

        /// <summary>
        /// The ring of <paramref name="def"/>: centre, radius, height and repeats (see the class summary). Pure: the same
        /// level always gives the same ring (LevelBuilder builds it, OrbitCamera fences the camera with it).
        /// </summary>
        public static Ring RingFor(LevelDef def)
        {
            Rect interior = def.InteriorBounds();
            Vector2 c = interior.center;
            float reach = FocusReach(def, c);
            float arm = OrbitCamera.MaxDistanceFor(def);
            float horizontal = arm * Mathf.Cos(Tuning.PitchMin * Mathf.Deg2Rad);
            float radius = reach + horizontal + CameraClearance;
            float eye = FocusTop(def) + arm * Mathf.Sin(Tuning.PitchMax * Mathf.Deg2Rad);
            float wanted = eye + HeadRoom + Sink;
            float circumference = 2f * Mathf.PI * radius;
            // Rounded down, so the height that keeps the aspect is never below the wanted one.
            int repeats = Mathf.Max(3, Mathf.FloorToInt(circumference / (wanted * ImageAspect))); // MUTATION:BACKDROP_REPEATS
            float height = circumference / (repeats * ImageAspect);
            return new Ring(new Vector3(c.x, 0f, c.y), radius, height, repeats, reach + horizontal + 0.5f * CameraClearance, eye + 0.5f * HeadRoom);
        }

        /// <summary>The farthest the camera's focus can be from <paramref name="c"/> (horizontal), margin included.</summary>
        public static float FocusReach(LevelDef def, Vector2 c)
        {
            Rect interior = def.InteriorBounds();
            float reach = Corner(interior, c);
            if (def.Exit != null)
            {
                reach = Mathf.Max(reach, Corner(new Rect(def.Exit.X - def.Exit.SizeX * 0.5f, def.Exit.Z - def.Exit.SizeZ * 0.5f, def.Exit.SizeX, def.Exit.SizeZ), c));
            }
            foreach (PropDef p in def.Props)
            {
                float half = 0.5f * Mathf.Sqrt(p.SizeX * p.SizeX + p.SizeZ * p.SizeZ);
                reach = Mathf.Max(reach, Vector2.Distance(new Vector2(p.X, p.Z), c) + half);
            }
            return reach + FootprintMargin;
        }

        /// <summary>The highest the camera's focus can be: the highest floor, half the player's body, the target height.</summary>
        public static float FocusTop(LevelDef def)
        {
            float floor = 0f;
            if (def.Platforms != null)
            {
                foreach (PlatformDef p in def.Platforms)
                {
                    floor = Mathf.Max(floor, p.Height);
                }
            }
            BodyDef body = def.PlayerBody();
            float half = body != null ? body.Size.y * 0.5f : 1f;
            return floor + half + Tuning.CameraTargetHeight;
        }

        private static float Corner(Rect r, Vector2 c)
        {
            float dx = Mathf.Max(Mathf.Abs(r.xMin - c.x), Mathf.Abs(r.xMax - c.x));
            float dz = Mathf.Max(Mathf.Abs(r.yMin - c.y), Mathf.Abs(r.yMax - c.y));
            return Mathf.Sqrt(dx * dx + dz * dz);
        }

        /// <summary>
        /// The arm length, at most <paramref name="distance"/>, that keeps a camera at <paramref name="focus"/> +
        /// <paramref name="back"/> x arm inside the ring's camera space (<see cref="Ring.HoldsCamera"/>). The ring is sized
        /// so this never shortens the arm in play; it guards any zoom bound set beyond the level's own.
        /// </summary>
        public static float ClampArm(Ring ring, Vector3 focus, Vector3 back, float distance)
        {
            float arm = distance;
            if (back.y > 1e-4f)
            {
                arm = Mathf.Min(arm, Mathf.Max(0f, (ring.CameraTop - focus.y) / back.y));
            }
            // |o + b t| <= R on the ground plane: the positive root of |b|^2 t^2 + 2 (o.b) t + |o|^2 - R^2 = 0.
            var o = new Vector2(focus.x - ring.Center.x, focus.z - ring.Center.z);
            var b = new Vector2(back.x, back.z);
            float a = b.sqrMagnitude;
            if (a > 1e-8f)
            {
                float half = Vector2.Dot(o, b);
                float cc = o.sqrMagnitude - ring.CameraRadius * ring.CameraRadius;
                float disc = half * half - a * cc;
                float t = disc > 0f ? (-half + Mathf.Sqrt(disc)) / a : 0f;
                arm = Mathf.Min(arm, Mathf.Max(0f, t)); // MUTATION:BACKDROP_CAMERA_FENCE
            }
            return arm;
        }

        /// <summary>The picture, or null with <see cref="TextureLibrary.Disabled"/> or when it is missing (one error logged).</summary>
        public static Texture2D Texture
        {
            get
            {
                if (TextureLibrary.Disabled)
                {
                    return null;
                }
                if (!loaded || texture == null)
                {
                    bool first = !loaded;
                    loaded = true;
                    texture = Resources.Load<Texture2D>(ResourcePath);
                    if (texture == null && first)
                    {
                        Debug.LogError($"[GardenBackdrop] no garden picture at Resources/{ResourcePath}: the levels have no backdrop");
                    }
                    else if (texture != null)
                    {
                        // The ring repeats the picture around the circle, its sky and lawn never wrap (the importer's settings too).
                        texture.wrapModeU = TextureWrapMode.Repeat;
                        texture.wrapModeV = TextureWrapMode.Clamp;
                    }
                }
                return texture;
            }
        }

        /// <summary>The ring's property block: the picture (its repeats are in the mesh's UVs), a neutral colour of <see cref="Intensity"/>.</summary>
        public static MaterialPropertyBlock Block
        {
            get
            {
                Texture2D t = Texture;
                if (t == null)
                {
                    return null;
                }
                if (block == null)
                {
                    block = new MaterialPropertyBlock();
                }
                block.Clear();
                block.SetTexture(BaseMapId, t); // MUTATION:BACKDROP_IMAGE
                block.SetVector(BaseMapStId, new Vector4(1f, 1f, 0f, 0f));
                block.SetColor(BaseColorId, new Color(Intensity, Intensity, Intensity, 1f));
                return block;
            }
        }

        /// <summary>
        /// Builds the ring of <paramref name="def"/> under <paramref name="root"/> with <paramref name="material"/> (the window
        /// pane's unlit one) and the picture's block; null without the picture.
        /// </summary>
        public static MeshRenderer Build(LevelDef def, Transform root, Material material)
        {
            MaterialPropertyBlock properties = Block;
            if (properties == null || material == null)
            {
                return null;
            }
            Ring ring = RingFor(def);
            var go = new GameObject(RendererName) { layer = 0 };
            go.transform.SetParent(root, false);
            go.transform.localPosition = ring.Center;
            go.AddComponent<MeshFilter>().sharedMesh = Mesh(ring);
            var renderer = go.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = material;
            renderer.SetPropertyBlock(properties);
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            renderer.receiveShadows = false;
            renderer.lightProbeUsage = LightProbeUsage.Off;
            renderer.reflectionProbeUsage = ReflectionProbeUsage.Off;
            renderer.allowOcclusionWhenDynamic = false;
            return renderer;
        }

        /// <summary>
        /// The ring's mesh around its own axis: a cylinder of <see cref="Segments"/> facets from y = -<see cref="Sink"/>
        /// to its top, its faces toward the axis (seen from inside only), U running <see cref="Ring.Repeats"/> times round
        /// left to right as seen from inside, V from 0 at the foot to 1 at the top. Cached by size.
        /// </summary>
        public static Mesh Mesh(Ring ring)
        {
            System.Globalization.CultureInfo ci = System.Globalization.CultureInfo.InvariantCulture;
            string key = ring.Radius.ToString("0.###", ci) + "x" + ring.Height.ToString("0.###", ci) + "x" + ring.Repeats;
            if (Meshes.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            int n = Segments;
            var vertices = new Vector3[2 * (n + 1)];
            var normals = new Vector3[vertices.Length];
            var uvs = new Vector2[vertices.Length];
            var triangles = new int[6 * n];
            float bottom = -Sink;
            float top = ring.Height - Sink;
            for (int i = 0; i <= n; i++)
            {
                float angle = 2f * Mathf.PI * i / n;
                var dir = new Vector3(Mathf.Cos(angle), 0f, Mathf.Sin(angle));
                // Angles grow toward +z, the viewer's left from inside: U runs the other way so the picture is not mirrored.
                float u = ring.Repeats * (float)(n - i) / n;
                vertices[2 * i] = dir * ring.Radius + Vector3.up * bottom;
                vertices[2 * i + 1] = dir * ring.Radius + Vector3.up * top;
                normals[2 * i] = -dir;
                normals[2 * i + 1] = -dir;
                uvs[2 * i] = new Vector2(u, 0f);
                uvs[2 * i + 1] = new Vector2(u, 1f);
            }
            for (int i = 0; i < n; i++)
            {
                int b0 = 2 * i, t0 = 2 * i + 1, b1 = 2 * i + 2, t1 = 2 * i + 3;
                // Clockwise as seen from the axis (Unity's front face): the inside shows, the outside is culled.
                triangles[6 * i] = t1;
                triangles[6 * i + 1] = t0;
                triangles[6 * i + 2] = b0;
                triangles[6 * i + 3] = t1;
                triangles[6 * i + 4] = b0;
                triangles[6 * i + 5] = b1;
            }
            var mesh = new Mesh { name = "GardenBackdrop" };
            mesh.vertices = vertices;
            mesh.normals = normals;
            mesh.uv = uvs;
            mesh.triangles = triangles;
            mesh.RecalculateBounds();
            mesh.hideFlags = HideFlags.DontUnloadUnusedAsset;
            Meshes[key] = mesh;
            return mesh;
        }
    }
}
