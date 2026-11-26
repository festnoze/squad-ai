using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>
    /// Garden backdrop (product owner images, docs/LICENSES.md, docs/m9/backdrop/NOTES.md): a ring around every house (and
    /// the title house), a cylinder showing the owner's garden panorama on its inside, repeated around the circle, closed
    /// at its top by a round sky ceiling, so the horizon closes on a garden and the sky above it instead of grass running
    /// into the void. 2026-11-19: the ring and Assets/Art/Environment/garden_open_horizontal_tile.png; 2026-11-20: the wide
    /// panorama garden_open_horizontal_tile_wide.png and the ceiling showing sky_disc_sun_glow.png.
    ///
    /// <list type="bullet">
    /// <item>Default size (<see cref="RingFor"/>, the size "defined by config"): centred on the house's interior centre (as
    /// the garden quad); GARDENFIT (2026-11-24): its radius is the house's farthest point (<see cref="HouseReach"/>: the
    /// interior, the props, the exit zone) times 1 + Tuning.GardenRingHouseMargin. The camera space
    /// (<see cref="Ring.CameraRadius"/>) keeps the old bound: the farthest point the camera's focus can reach
    /// (<see cref="FocusReach"/>) plus the camera's longest horizontal arm (OrbitCamera.MaxDistanceFor at the arm's lowest
    /// pitch, Tuning.OrbitArmPitchMin); its height is at least the camera's highest eye (the highest floor, half the
    /// player's body, Tuning.CameraTargetHeight, the arm at Tuning.PitchMax) plus <see cref="HeadRoom"/>. The picture keeps
    /// its aspect: its repeat count is the circumference over <see cref="PictureRatio"/> of the radius times the picture's
    /// aspect, rounded (three on every level), its height then follows (<see cref="Ring.PictureHeight"/>, 0.52 of the
    /// radius); the straight wall is at least the picture's height, and where it is taller the band above the picture
    /// shows its uniform top sky (the texture is clamped in V).
    /// OrbitCamera fences the camera into its space (<see cref="ClampArm"/>) and sets its far clip past the largest ring
    /// (<see cref="Ring.FarClip"/>).</item>
    /// <item>Zoom fit (GARDENZOOM, 2026-11-25, user request: the camera stays inside the ring whatever the zoom): the
    /// ring is no longer fixed at its default size. <see cref="GardenBackdropFit"/>, on the ring, scales it every frame
    /// (one uniform transform scale about the centre of its foot, which stays on the ground; no mesh rebuilt, the picture
    /// keeps its aspect) to the smallest size, never below the default, that holds the game camera
    /// (<see cref="ScaleToHold(Ring, Vector3)"/>): the radius is max(the default, the camera's horizontal distance from the
    /// axis + Tuning.GardenRingCameraMargin) and the ceiling stays <see cref="HeadRoom"/> above the camera, its rounded rim
    /// included. Zoomed in again, it eases back to exactly the default. The largest size any camera of the level can ask
    /// for (<see cref="Ring.MaxScale"/>: the orbit camera's space and the spectator's flight box) sizes the far clip and the
    /// lawn (LevelBuilder: 2 x <see cref="Ring.MaxRadius"/> + 20).</item>
    /// <item>Ceiling (<see cref="SkyMesh"/>): a flat disc whose rim rounds down onto the ring's top edge (a quarter circle of
    /// <see cref="Fillet"/>: no crease for the screen space ambient occlusion, which URP's Unlit shader also applies, to
    /// darken), seen from below, its lowest vertices the ring's own top vertices (no gap), the sky picture projected once
    /// over its diameter (no stretch). The picture's sun is moved
    /// toward image right (tools/assets/make_garden_backdrop.py), which the mapping turns toward the scene's directional
    /// light (<see cref="SunAzimuth"/>).</item>
    /// <item>Look: unlit (no shadow cast or received, no dark side). The garden's top sky and the disc's rim are one
    /// uniform colour (<see cref="SkyTop"/>), so the seam between the ring and its ceiling does not show; the camera's
    /// clear colour (<see cref="ClearColour"/>, Main) is that colour too.</item>
    /// <item>Budget (PRD 7.4): two renderers of one slot each (the ring and its ceiling), both drawn with the cached unlit
    /// pane material (LevelBuilder.PaneMaterial, shared with the cool fixture glows) through a property block each
    /// (<see cref="Block"/>, <see cref="SkyBlock"/>): two draw calls. WINDOWS3D (2026-11-24): the windows no longer draw
    /// with that material (the 3D window's glass has its own), so a level without a cool fixture now pays it for the ring;
    /// the ring is what the windows show through their glass.</item>
    /// <item>Gameplay: no collider, the Default layer (no occluder, chair blocker or NavMesh source), never registered
    /// with the wall fader: vision, raycasts and navigation never see it (so its zoom fit changes no rule).</item>
    /// </list>
    ///
    /// Shipped files: Assets/Resources/GardenBackdrop.png (4096 x 1024, wraps horizontally, repeat in U and clamp in V)
    /// and Assets/Resources/GardenSky.png (1024 x 1024, the disc filling the square, clamped). With TextureLibrary.Disabled
    /// or without the garden picture there is no ring; without the sky picture the ring stands open (the clear colour).
    /// </summary>
    public static class GardenBackdrop
    {
        /// <summary>The garden picture's path under Resources.</summary>
        public const string ResourcePath = "GardenBackdrop";

        /// <summary>The sky picture's path under Resources.</summary>
        public const string SkyResourcePath = "GardenSky";

        /// <summary>The ring's renderer name under the level root.</summary>
        public const string RendererName = "GardenBackdrop";

        /// <summary>The ceiling's renderer name (a child of the ring).</summary>
        public const string SkyRendererName = "GardenBackdropSky";

        /// <summary>Facets around the circle (the ring: 2 x (Segments + 1) vertices; the ceiling: rings of Segments + 1, same angles).</summary>
        public const int Segments = 72;

        /// <summary>
        /// The radius of the ceiling's rounded rim, in metres: the wall ends this far below the ceiling and a quarter circle
        /// joins them. A right angle there was a concave crease, which the screen space ambient occlusion (0.3 m) drew as a
        /// dark band all round the sky (2026-11-20, docs/m9/backdrop/NOTES.md v8); a 2.5 m round leaves it nothing to darken.
        /// </summary>
        public const float Fillet = 2.5f;

        /// <summary>Facets along the rounded rim's quarter circle.</summary>
        public const int FilletSegments = 6;

        /// <summary>The garden picture's width over its height (4096 x 1024).</summary>
        public const float ImageAspect = 4f;

        /// <summary>
        /// The garden picture's wanted height over the ring's radius: with the wide panorama, three repeats round every
        /// ring (twelve garden stretches, never the same one twice in a view), the picture 0.52 of the radius high, so every
        /// house sees its garden at the same angle (the 2026-11-19 rings stood 0.52 to 0.57 of their radius high).
        /// </summary>
        public const float PictureRatio = 0.5f;

        /// <summary>Added around the focus footprint (walls, the chair stepping out on the exit, the smoothing lag).</summary>
        public const float FootprintMargin = 1.5f;

        /// <summary>Between the camera's farthest reach and the ring, in metres.</summary>
        public const float CameraClearance = 2.5f;

        /// <summary>Between the camera's highest eye and the ring's top, in metres.</summary>
        public const float HeadRoom = 1.5f;

        /// <summary>The ring's foot below y = 0 (under the garden quad at -0.02, so no gap shows).</summary>
        public const float Sink = 0.06f;

        /// <summary>The pictures' colour factor (sRGB, the base colour through the blocks): at most 1, never in the bloom.</summary>
        public const float Intensity = 1f;

        /// <summary>
        /// The garden picture's uniform sky at its top and the sky picture's rim (sRGB, tools/assets/make_garden_backdrop.py
        /// SKY, the sky source's own rim colour), times <see cref="Intensity"/> the camera's clear colour.
        /// </summary>
        public static readonly Color SkyTop = new Color32(130, 191, 253, 255);

        /// <summary>
        /// The light the sky picture's sun goes toward without a sun in the scene (edit mode tools): Main's sun of
        /// 2026-11-20 (Euler 44, 32), whose light comes from this direction.
        /// </summary>
        public static Vector3 DefaultSunDirection
        {
            get
            {
                // -(Quaternion.Euler(44, 32, 0) * forward), written out (no engine call in a static initializer).
                float pitch = 44f * Mathf.Deg2Rad;
                float yaw = 32f * Mathf.Deg2Rad;
                return new Vector3(-Mathf.Sin(yaw) * Mathf.Cos(pitch), Mathf.Sin(pitch), -Mathf.Cos(yaw) * Mathf.Cos(pitch));
            }
        }

        /// <summary>
        /// Levels v2 (D25, C10): the night preset's tint of the garden picture (sRGB factor, the base colour through the
        /// block instead of a neutral <see cref="Intensity"/>): a dark blue garden under the moon. Visual only.
        /// </summary>
        public static readonly Color NightTint = new Color(0.2f, 0.27f, 0.48f, 1f);

        /// <summary>The night preset's tint of the sky ceiling (darker than the garden: the sky picture is bright).</summary>
        public static readonly Color NightSkyTint = new Color(0.12f, 0.16f, 0.33f, 1f);

        /// <summary>The garden picture's colour factor under the preset applied last (<see cref="Main.Night"/>).</summary>
        public static Color Tint => Main.Night ? NightTint : new Color(Intensity, Intensity, Intensity, 1f); // MUTATION:NIGHT_BACKDROP

        /// <summary>The sky ceiling's colour factor under the preset applied last.</summary>
        public static Color SkyTint => Main.Night ? NightSkyTint : new Color(Intensity, Intensity, Intensity, 1f);

        /// <summary>The camera's clear colour: the ring's top sky as the unlit ring draws it (night: tinted as the ring).</summary>
        public static Color ClearColour
        {
            get
            {
                Color k = Tint.linear;
                Color sky = SkyTop.linear;
                return new Color(sky.r * k.r, sky.g * k.g, sky.b * k.b, 1f).gamma;
            }
        }

        private static readonly int BaseMapId = Shader.PropertyToID("_BaseMap");
        private static readonly int BaseMapStId = Shader.PropertyToID("_BaseMap_ST");
        private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");

        private static readonly Dictionary<string, Mesh> Meshes = new Dictionary<string, Mesh>();
        private static Texture2D texture;
        private static bool loaded;
        private static Texture2D skyTexture;
        private static bool skyLoaded;
        private static MaterialPropertyBlock block;
        private static MaterialPropertyBlock skyBlock;

        /// <summary>The size of one level's ring (see <see cref="RingFor"/>).</summary>
        public readonly struct Ring
        {
            /// <summary>The ring's axis at the ground (y = 0).</summary>
            public readonly Vector3 Center;
            public readonly float Radius;
            /// <summary>From the foot (y = -<see cref="Sink"/>) to the top (the ceiling).</summary>
            public readonly float Height;
            /// <summary>The garden picture's height from the foot (at most <see cref="Height"/>; its aspect is exact).</summary>
            public readonly float PictureHeight;
            public readonly int Repeats;
            /// <summary>The camera may stand this far from the axis at most (OrbitCamera's clamp).</summary>
            public readonly float CameraRadius;
            /// <summary>The camera's eye may stand this high at most.</summary>
            public readonly float CameraTop;
            /// <summary>
            /// GARDENZOOM: the largest zoom fit scale (<see cref="GardenBackdropFit"/>) a camera of this level can ask for:
            /// the orbit camera anywhere in its space and the spectator's free camera anywhere in its flight box. At least 1.
            /// </summary>
            public readonly float MaxScale;

            public Ring(Vector3 center, float radius, float height, float pictureHeight, int repeats, float cameraRadius, float cameraTop,
                float maxScale = 1f)
            {
                Center = center;
                Radius = radius;
                Height = height;
                PictureHeight = pictureHeight;
                Repeats = repeats;
                CameraRadius = cameraRadius;
                CameraTop = cameraTop;
                MaxScale = Mathf.Max(1f, maxScale);
            }

            /// <summary>GARDENZOOM: the radius of the ring at its largest zoom fit (<see cref="MaxScale"/>).</summary>
            public float MaxRadius => Radius * MaxScale;

            /// <summary>GARDENZOOM: the height (foot to top) of the ring at its largest zoom fit.</summary>
            public float MaxHeight => Height * MaxScale;

            /// <summary>The ceiling's height (y), its flat part.</summary>
            public float Top => Height - Sink;

            /// <summary>Where the straight wall ends and the ceiling's rounded rim begins (y).</summary>
            public float WallTop => Top - Fillet;

            /// <summary>The closed volume's inside radius at height <paramref name="y"/>: the ring's up to the wall's top, then the rounded rim's.</summary>
            public float InnerRadiusAt(float y)
            {
                if (y <= WallTop)
                {
                    return Radius;
                }
                float up = Mathf.Min(y - WallTop, Fillet);
                return Radius - Fillet + Mathf.Sqrt(Mathf.Max(0f, Fillet * Fillet - up * up));
            }

            /// <summary>
            /// GARDENZOOM: the closed volume's inside radius at height <paramref name="y"/> once the ring is scaled by
            /// <paramref name="scale"/> about the centre of its foot (the zoom fit, <see cref="GardenBackdropFit"/>).
            /// </summary>
            public float InnerRadiusAt(float y, float scale)
            {
                float s = Mathf.Max(1e-3f, scale);
                return s * InnerRadiusAt((y + Sink) / s - Sink);
            }

            /// <summary>
            /// A far clip that holds the whole ring and its ceiling from any camera inside it. GARDENZOOM: the ring at its
            /// largest zoom fit (<see cref="MaxRadius"/>, <see cref="MaxHeight"/>), the camera anywhere inside it: across
            /// its diameter and its whole height.
            /// </summary>
            public float FarClip => Mathf.Sqrt(4f * MaxRadius * MaxRadius + MaxHeight * MaxHeight) + 2f;

            /// <summary>True when <paramref name="point"/> lies inside the ring's camera space (radius and top).</summary>
            public bool HoldsCamera(Vector3 point)
            {
                Vector2 d = new Vector2(point.x - Center.x, point.z - Center.z);
                return d.magnitude <= CameraRadius + 1e-3f && point.y <= CameraTop + 1e-3f;
            }
        }

        /// <summary>
        /// The ring of <paramref name="def"/>: centre, radius, height, picture height and repeats (see the class summary).
        /// Pure: the same level always gives the same ring (LevelBuilder builds it, OrbitCamera fences the camera with it).
        /// </summary>
        public static Ring RingFor(LevelDef def)
        {
            Rect interior = def.InteriorBounds();
            Vector2 c = interior.center;
            float reach = FocusReach(def, c);
            float arm = OrbitCamera.MaxDistanceFor(def);
            // The arm's lowest pitch gives its longest horizontal reach (the view may tilt higher, the camera does not move).
            float horizontal = arm * Mathf.Cos(Mathf.Clamp(Tuning.OrbitArmPitchMin, 0f, Tuning.PitchMax) * Mathf.Deg2Rad);
            // GARDENFIT (2026-11-24): the ring hugs the house (Tuning.GardenRingHouseMargin), not the camera's reach: the
            // camera space below keeps the old bound. GARDENZOOM (2026-11-25): this is the default size; the ring grows
            // past it with the camera (GardenBackdropFit), up to MaxScale below.
            float radius = HouseReach(def, c) * (1f + Tuning.GardenRingHouseMargin);
            float eye = FocusTop(def) + arm * Mathf.Sin(Tuning.PitchMax * Mathf.Deg2Rad);
            float wanted = eye + HeadRoom + Sink;
            float circumference = 2f * Mathf.PI * radius;
            int repeats = Mathf.Max(1, Mathf.RoundToInt(circumference / (PictureRatio * radius * ImageAspect))); // MUTATION:BACKDROP_REPEATS
            float picture = circumference / (repeats * ImageAspect);
            // The straight wall holds the whole picture (its uniform top sky meets the rounded rim), the ceiling the highest eye.
            float height = Mathf.Max(picture + Fillet, wanted);
            var center = new Vector3(c.x, 0f, c.y);
            float cameraRadius = reach + horizontal + 0.5f * CameraClearance;
            float cameraTop = eye + 0.5f * HeadRoom;
            var ring = new Ring(center, radius, height, picture, repeats, cameraRadius, cameraTop);
            // GARDENZOOM: the largest zoom fit a camera of this level can ask for, which the far clip and the lawn cover. The
            // orbit camera: its farthest reach and its highest eye together (a bound: no pose has both). The spectator's free
            // camera (SpectatorCamera.Clamp): the interior grown by its margin, up to its ceiling, the box's corner.
            float orbit = ScaleToHold(ring, cameraRadius, cameraTop);
            float halfX = interior.width * 0.5f + SpectatorCamera.BoundsMargin;
            float halfZ = interior.height * 0.5f + SpectatorCamera.BoundsMargin;
            float spectator = ScaleToHold(ring, Mathf.Sqrt(halfX * halfX + halfZ * halfZ), SpectatorCamera.MaxHeight);
            return new Ring(center, radius, height, picture, repeats, cameraRadius, cameraTop, Mathf.Max(orbit, spectator));
        }

        /// <summary>
        /// GARDENZOOM: the zoom fit scale (at least 1) of <paramref name="ring"/> that holds a camera at
        /// <paramref name="eye"/> (in the ring's parent space, the level root's): the radius at least the camera's horizontal
        /// distance from the axis plus Tuning.GardenRingCameraMargin, the ceiling at least <see cref="HeadRoom"/> above it.
        /// </summary>
        public static float ScaleToHold(Ring ring, Vector3 eye)
        {
            return ScaleToHold(ring, Mathf.Sqrt(HorizontalSqr(ring, eye)), eye.y);
        }

        /// <summary>GARDENZOOM: <see cref="ScaleToHold(Ring, Vector3)"/> for a camera <paramref name="horizontal"/> metres from the axis, <paramref name="height"/> high.</summary>
        public static float ScaleToHold(Ring ring, float horizontal, float height)
        {
            return ScaleToHold(ring, horizontal, height, Tuning.GardenRingCameraMargin, HeadRoom);
        }

        /// <summary>
        /// GARDENZOOM: the smallest scale, at least 1, of <paramref name="ring"/>, uniform about the centre of its foot
        /// (which stays at y = -<see cref="Sink"/>), whose closed volume holds the point <paramref name="horizontal"/>
        /// metres from the axis and <paramref name="height"/> high grown by <paramref name="side"/> toward the wall and
        /// <paramref name="above"/> toward the ceiling. The grown point is checked against the volume's profile (the wall,
        /// the rounded rim, the flat ceiling): the radius at the camera's height is then at least its distance plus
        /// <paramref name="side"/>, the ceiling at least <paramref name="above"/> over it. Continuous and monotonic in both
        /// distances (the profile is convex and holds its foot's centre: this is its gauge), so a smooth camera gives a
        /// smooth ring. Pure, a few float operations, no allocation.
        /// </summary>
        public static float ScaleToHold(Ring ring, float horizontal, float height, float side, float above)
        {
            // The grown point, measured from the foot's centre (the scale's fixed point).
            float q = Mathf.Max(0f, horizontal) + Mathf.Max(0f, side);
            float h = Mathf.Max(0f, height + Sink + Mathf.Max(0f, above));
            float radius = Mathf.Max(1e-3f, ring.Radius);
            float tall = Mathf.Max(1e-3f, ring.Height);
            float wall = tall - Fillet;
            // The square profile's answer: the scale at which the wall or the flat ceiling reaches the point.
            float s = Mathf.Max(q / radius, h / tall);
            float inner = radius - Fillet;
            if (q > s * inner && h > s * wall)
            {
                // There the ray from the foot's centre meets the rounded rim first, a quarter circle of centre
                // c = (inner, wall) and radius Fillet: |P - s c| = s Fillet, i.e. a s^2 - 2 b s + cc = 0, whose smaller
                // root is its outer arc; written cc / (b + sqrt(b^2 - a cc)) (the same root, without cancellation).
                float a = inner * inner + wall * wall - Fillet * Fillet;
                float b = q * inner + h * wall;
                if (a > 1e-6f && b > 1e-6f)
                {
                    float cc = q * q + h * h;
                    s = cc / (b + Mathf.Sqrt(Mathf.Max(0f, b * b - a * cc))); // MUTATION:GARDENZOOM_RIM
                }
            }
            return Mathf.Max(1f, s);
        }

        /// <summary>The squared horizontal distance from <paramref name="ring"/>'s axis to <paramref name="point"/>.</summary>
        public static float HorizontalSqr(Ring ring, Vector3 point)
        {
            float dx = point.x - ring.Center.x;
            float dz = point.z - ring.Center.z;
            return dx * dx + dz * dz;
        }

        /// <summary>The farthest the camera's focus can be from <paramref name="c"/> (horizontal), margin included.</summary>
        public static float FocusReach(LevelDef def, Vector2 c)
        {
            return HouseReach(def, c) + FootprintMargin;
        }

        /// <summary>GARDENFIT: the house's farthest point from <paramref name="c"/> (horizontal): the interior, the exit, the props.</summary>
        public static float HouseReach(LevelDef def, Vector2 c)
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
            return reach;
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

        /// <summary>The garden picture, or null with <see cref="TextureLibrary.Disabled"/> or when it is missing (one error logged).</summary>
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

        /// <summary>The sky picture, or null with <see cref="TextureLibrary.Disabled"/> or when it is missing (one error logged).</summary>
        public static Texture2D SkyTexture
        {
            get
            {
                if (TextureLibrary.Disabled)
                {
                    return null;
                }
                if (!skyLoaded || skyTexture == null)
                {
                    bool first = !skyLoaded;
                    skyLoaded = true;
                    skyTexture = Resources.Load<Texture2D>(SkyResourcePath);
                    if (skyTexture == null && first)
                    {
                        Debug.LogError($"[GardenBackdrop] no sky picture at Resources/{SkyResourcePath}: the rings stand open");
                    }
                    else if (skyTexture != null)
                    {
                        skyTexture.wrapMode = TextureWrapMode.Clamp;
                    }
                }
                return skyTexture;
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
                Fill(block, t, Tint);
                return block;
            }
        }

        /// <summary>The ceiling's property block: the sky picture, a neutral colour of <see cref="Intensity"/>.</summary>
        public static MaterialPropertyBlock SkyBlock
        {
            get
            {
                Texture2D t = SkyTexture;
                if (t == null)
                {
                    return null;
                }
                if (skyBlock == null)
                {
                    skyBlock = new MaterialPropertyBlock();
                }
                Fill(skyBlock, t, SkyTint);
                return skyBlock;
            }
        }

        private static void Fill(MaterialPropertyBlock properties, Texture2D t, Color tint)
        {
            properties.Clear();
            properties.SetTexture(BaseMapId, t); // MUTATION:BACKDROP_IMAGE
            properties.SetVector(BaseMapStId, new Vector4(1f, 1f, 0f, 0f));
            properties.SetColor(BaseColorId, tint);
        }

        /// <summary>
        /// The azimuth (radians, from +x toward +z) the scene's directional light comes from: RenderSettings.sun, else
        /// Main's sun, else <see cref="DefaultSunDirection"/>.
        /// </summary>
        public static float SunAzimuth()
        {
            Light sun = RenderSettings.sun;
            if (sun == null && Main.Instance != null)
            {
                sun = Main.Instance.Sun;
            }
            Vector3 toward = sun != null ? -sun.transform.forward : DefaultSunDirection;
            if (new Vector2(toward.x, toward.z).sqrMagnitude < 1e-6f)
            {
                toward = DefaultSunDirection;
            }
            return Mathf.Atan2(toward.z, toward.x);
        }

        /// <summary>
        /// Builds the ring of <paramref name="def"/> under <paramref name="root"/> with <paramref name="material"/> (the window
        /// pane's unlit one) and the picture's block, and its sky ceiling as a child; null without the garden picture.
        /// </summary>
        public static MeshRenderer Build(LevelDef def, Transform root, Material material)
        {
            // Levels v2 (C10): the level's lighting preset is applied here, the first level build step that sees the level
            // (LevelBuilder.BuildFloors, before the walls), so the windows, the ring and the sky all read the right one.
            Main.ApplyLighting(def);
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
            MeshRenderer renderer = Unlit(go, material, properties);
            MaterialPropertyBlock sky = SkyBlock;
            if (sky != null)
            {
                var ceiling = new GameObject(SkyRendererName) { layer = 0 };
                ceiling.transform.SetParent(go.transform, false);
                ceiling.AddComponent<MeshFilter>().sharedMesh = SkyMesh(ring, SunAzimuth());
                Unlit(ceiling, material, sky);
            }
            // GARDENZOOM: the ring (and its ceiling, a child) follows the game camera's zoom (play mode only).
            go.AddComponent<GardenBackdropFit>().Init(ring);
            return renderer;
        }

        private static MeshRenderer Unlit(GameObject go, Material material, MaterialPropertyBlock properties)
        {
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

        private static string Key(string kind, Ring ring)
        {
            System.Globalization.CultureInfo ci = System.Globalization.CultureInfo.InvariantCulture;
            return kind + ring.Radius.ToString("0.###", ci) + "x" + ring.Height.ToString("0.###", ci) + "x"
                + ring.PictureHeight.ToString("0.###", ci) + "x" + ring.Repeats;
        }

        /// <summary>The angle of the rim vertex <paramref name="i"/> (ring and ceiling share them, so their edges meet).</summary>
        private static Vector3 RimDirection(int i)
        {
            float angle = 2f * Mathf.PI * i / Segments;
            return new Vector3(Mathf.Cos(angle), 0f, Mathf.Sin(angle));
        }

        /// <summary>
        /// The ring's mesh around its own axis: a cylinder of <see cref="Segments"/> facets from y = -<see cref="Sink"/>
        /// to the wall's top (<see cref="Ring.WallTop"/>), its faces toward the axis (seen from inside only), U running
        /// <see cref="Ring.Repeats"/> times round left to right as seen from inside, V from 0 at the foot to 1 at the
        /// picture's top (above 1 up the band over the picture: the clamped texture repeats its uniform top sky there).
        /// Cached by size.
        /// </summary>
        public static Mesh Mesh(Ring ring)
        {
            string key = Key("ring", ring);
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
            float top = ring.WallTop;
            float vTop = (top + Sink) / Mathf.Max(1e-3f, ring.PictureHeight);
            for (int i = 0; i <= n; i++)
            {
                Vector3 dir = RimDirection(i);
                // Angles grow toward +z, the viewer's left from inside: U runs the other way so the picture is not mirrored.
                float u = ring.Repeats * (float)(n - i) / n;
                vertices[2 * i] = dir * ring.Radius + Vector3.up * bottom;
                vertices[2 * i + 1] = dir * ring.Radius + Vector3.up * top;
                normals[2 * i] = -dir;
                normals[2 * i + 1] = -dir;
                uvs[2 * i] = new Vector2(u, 0f);
                uvs[2 * i + 1] = new Vector2(u, vTop);
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

        /// <summary>
        /// The ceiling's mesh around the ring's axis, seen from inside only: from the ring's own top vertices (the wall's
        /// top) a quarter circle of <see cref="Fillet"/> in <see cref="FilletSegments"/> rings rounds up and in onto a flat
        /// fan at <see cref="Ring.Top"/>, its normals the surface's own (they feed the depth normals the ambient occlusion
        /// reads). The sky picture is projected from below over the ring's diameter (UV 0 to 1 from the horizontal position:
        /// exact on the flat part, no stretch), image right turned toward <paramref name="sunAzimuth"/> (radians from +x
        /// toward +z), where the picture's sun stands. Cached by size and azimuth.
        /// </summary>
        public static Mesh SkyMesh(Ring ring, float sunAzimuth)
        {
            System.Globalization.CultureInfo ci = System.Globalization.CultureInfo.InvariantCulture;
            string key = Key("sky", ring) + "@" + (sunAzimuth * Mathf.Rad2Deg).ToString("0.0", ci);
            if (Meshes.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            int n = Segments;
            int rings = FilletSegments + 1;
            int centre = rings * (n + 1);
            var vertices = new Vector3[centre + 1];
            var normals = new Vector3[vertices.Length];
            var uvs = new Vector2[vertices.Length];
            var triangles = new int[6 * n * FilletSegments + 3 * n];
            float fillet = Mathf.Min(Fillet, ring.Radius);
            for (int j = 0; j < rings; j++)
            {
                // Ring 0 is the wall's top (outward normal angle 0), the last ring the flat part's edge (90 degrees).
                float theta = 0.5f * Mathf.PI * j / FilletSegments;
                float radial = ring.Radius - fillet + fillet * Mathf.Cos(theta);
                float y = ring.WallTop + fillet * Mathf.Sin(theta);
                for (int i = 0; i <= n; i++)
                {
                    Vector3 dir = RimDirection(i);
                    // The angle measured from the sun's azimuth: image right (+U) points at the sun.
                    float a = 2f * Mathf.PI * i / n - sunAzimuth;
                    float r = 0.5f * radial / ring.Radius;
                    int k = j * (n + 1) + i;
                    vertices[k] = dir * radial + Vector3.up * y;
                    normals[k] = -(dir * Mathf.Cos(theta) + Vector3.up * Mathf.Sin(theta));
                    uvs[k] = new Vector2(0.5f + r * Mathf.Cos(a), 0.5f + r * Mathf.Sin(a));
                }
            }
            vertices[centre] = Vector3.up * ring.Top;
            normals[centre] = Vector3.down;
            uvs[centre] = new Vector2(0.5f, 0.5f);
            int t = 0;
            for (int j = 0; j < FilletSegments; j++)
            {
                for (int i = 0; i < n; i++)
                {
                    // As the ring's facets (lower ring b, upper ring t): clockwise as seen from inside, Unity's front face.
                    int b0 = j * (n + 1) + i, b1 = b0 + 1, t0 = b0 + n + 1, t1 = t0 + 1;
                    triangles[t++] = t1;
                    triangles[t++] = t0;
                    triangles[t++] = b0;
                    triangles[t++] = t1;
                    triangles[t++] = b0;
                    triangles[t++] = b1;
                }
            }
            int last = FilletSegments * (n + 1);
            for (int i = 0; i < n; i++)
            {
                // Clockwise as seen from below (Unity's front face): the underside shows, the top is culled.
                triangles[t++] = centre;
                triangles[t++] = last + i;
                triangles[t++] = last + i + 1;
            }
            var mesh = new Mesh { name = "GardenBackdropSky" };
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
