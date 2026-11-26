using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5.md 4, 16.8 and 16.12, PRD 4.8): the robot vacuum's visual and transform. Watchers draws it, the
    /// game steps it: GameState reads <see cref="Path"/> (the <see cref="RobotPath"/> of its <see cref="RobotDef"/>, built here)
    /// and calls <see cref="SetPose"/> once per fixed step; LevelBuilder calls <see cref="Create"/> and lists it in
    /// LevelInstance.Robots.
    /// <para>m15 (CONTRACT_M5 19): the root transform holds the rule pose exactly as set. The drawn <see cref="Body"/> is
    /// interpolated in LateUpdate between the poses of the last two fixed steps, and turns toward the heading at most
    /// <see cref="Tuning.RobotTurnRate"/>, so a loop end's 180 degree reversal is a short spin, never a one-frame flip. A pose
    /// farther than <see cref="Tuning.RobotSnapDistance"/> from the last one (a teleport) snaps the body.</para>
    /// <list type="bullet">
    /// <item>A procedural disc of radius <see cref="Tuning.RobotRadius"/> and height <see cref="Tuning.RobotHeight"/>, its
    /// front on its local +z (the heading): a light shell, a dark bumper around the front half and a small lidar turret,
    /// and a pale status light near the front that pulses (visual only, held while paused).</item>
    /// <item>No collider (inhabitants walk across it, 16.8), not on the Occluder layer (it hides nothing from a watcher),
    /// no NavMesh source (the NavMesh reads colliders only).</item>
    /// <item>Budgets: 3 material slots (shell, bumper, light); the light reuses the window pane's glow colour (CONTRACT_M6
    /// 2.4: the shell and the bumper now carry their own metal and plastic finish, Metal009 and Plastic006, so they no
    /// longer share a material with the window trim or the frame).</item>
    /// <item>Levels v2 C8 (docs/levels_v2/LEVELS_V2.md, wave1 code_features "Robot hum disc and matched audio rolloff"):
    /// the hum disc, a faint floor ring of radius <see cref="Tuning.RobotHumRadius"/> (the radius within which the hum
    /// masks hops, rolls and clicks, Hearing.IsMasked) that follows the drawn body and pulses at the hum loop's period
    /// (<see cref="Sfx.HumLoopSeconds"/>). One renderer, one material slot, one material shared by every robot, no
    /// collider, no shadow. It is a sibling of the robot under the same parent (the level root), not its child, so the
    /// level budgets count it while the robot's own hierarchy keeps its 3 slots and its RobotRadius footprint.</item>
    /// </list>
    /// </summary>
    public sealed class Robot : MonoBehaviour
    {
        // The decor colours it reuses (LevelBuilder's window trim and pane, FurnitureKit's frame).
        private static readonly Color ShellColour = new Color32(0xF7, 0xF4, 0xEE, 0xFF);
        private static readonly Color LightColour = new Color32(0xBF, 0xE3, 0xF5, 0xFF);

        // The shape (metres): the shell sits on a small clearance, the bumper wraps the front half, the turret tops it.
        private const float Clearance = 0.012f;
        private const float ShellTop = Tuning.RobotHeight - 0.012f;
        private const float BumperWidth = 0.006f;
        private const float BumperSweep = 200f;
        private const float TurretRadius = 0.045f;
        private const float TurretBack = 0.025f;
        private const float LightRadius = 0.012f;
        private const float LightAhead = 0.115f;
        private const int Segments = 20;

        // C8 hum disc: a pale lilac (apart from the cyan memory ghost, the amber seat ghost and the cones' yellow and red),
        // lifted above a rug's printed top (Tuning.RugHeight + 0.002) and under the vision cone's 0.015 m. The band runs from
        // HumDiscBand inside the radius to the radius: a very faint fill rising to a soft rim at the edge (HumDiscTexture).
        private static readonly Color HumDiscColour = new Color(0.80f, 0.76f, 1f, 1f);
        private const float HumDiscLift = 0.014f;
        private const float HumDiscBand = 0.6f;
        private const int HumDiscSegments = 72;
        private const int HumDiscTexels = 64;
        /// <summary>The disc's alpha at the top of its pulse (times the band's profile, 1 on the rim).</summary>
        public const float HumDiscAlpha = 0.3f;
        /// <summary>The bottom of the pulse, as a fraction of <see cref="HumDiscAlpha"/>.</summary>
        public const float HumDiscPulseMin = 0.55f;
        public const string HumDiscName = "HumDisc";
        private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        private static Material humDiscMaterial;
        private static Texture2D humDiscTexture;

        public RobotDef Def { get; private set; }

        /// <summary>The robot's timeline (core): the game reads its position and heading at each step.</summary>
        public RobotPath Path { get; private set; }

        /// <summary>The yaw of the last <see cref="SetPose"/> (YawMath: 0 faces +z).</summary>
        public float Yaw { get; private set; }

        /// <summary>The planar position of the last <see cref="SetPose"/> (its y as given).</summary>
        public Vector3 Position => transform.position;

        /// <summary>The status light (its scale pulses).</summary>
        public Transform StatusLight { get; private set; }

        /// <summary>m15: the drawn body (shell, bumper and light), smoothed toward the rule pose of the root.</summary>
        public Transform Body { get; private set; }

        /// <summary>m15: the drawn body's yaw, degrees (YawMath), turning toward <see cref="Yaw"/>.</summary>
        public float VisualYaw { get; private set; }

        /// <summary>The number of <see cref="SetPose"/> calls (tests).</summary>
        public int PoseCount { get; private set; }

        /// <summary>C8: the hum disc (a sibling of the robot under its parent), centred under the drawn body.</summary>
        public Transform HumDisc { get; private set; }

        /// <summary>C8: the hum disc's renderer (one material slot).</summary>
        public MeshRenderer HumDiscRenderer { get; private set; }

        /// <summary>C8: the outer radius of the hum disc as built, metres (<see cref="Tuning.RobotHumRadius"/>).</summary>
        public float HumDiscRadius { get; private set; }

        /// <summary>C8: the disc's current pulse, from <see cref="HumDiscPulseMin"/> to 1 (its alpha is HumDiscAlpha times it).</summary>
        public float HumDiscPulse { get; private set; } = 1f;

        private float clock;
        private float humClock;
        private MaterialPropertyBlock humBlock;
        // m15: the pose before the last fixed step's (the interpolation's start), the fixed time of the last pose, and the
        // body's drawn position.
        private Vector3 fromPosition;
        private float poseFixedTime = float.NegativeInfinity;
        private bool posed;
        private Vector3 drawnPosition;

        /// <summary>
        /// The robot of <paramref name="def"/> under <paramref name="parent"/> (the level root), its <see cref="Path"/> built
        /// from the def, posed where the path starts (time 0).
        /// </summary>
        public static Robot Create(RobotDef def, Transform parent)
        {
            var go = new GameObject("Robot " + (def != null && !string.IsNullOrEmpty(def.Name) ? def.Name : "")) { layer = 0 };
            go.transform.SetParent(parent, false);
            Robot robot = go.AddComponent<Robot>();
            robot.Def = def;
            robot.Path = new RobotPath(def);
            robot.Build();
            robot.BuildHumDisc(parent);
            robot.SetPose(robot.Path.PositionAt(0f), robot.Path.HeadingAt(0f));
            robot.PoseCount = 0;
            return robot;
        }

        /// <summary>
        /// Puts the robot at <paramref name="position"/> (world), facing <paramref name="yaw"/> (degrees, YawMath): the root at
        /// once (the rule pose), the drawn <see cref="Body"/> from its next LateUpdate (it snaps on the first pose, outside play
        /// mode and past <see cref="Tuning.RobotSnapDistance"/>). Several poses in one fixed step interpolate from the pose
        /// before that step.
        /// </summary>
        public void SetPose(Vector3 position, float yaw)
        {
            float now = Time.fixedTime;
            bool snap = !posed || !Application.isPlaying || (position - transform.position).magnitude > Tuning.RobotSnapDistance;
            if (posed && now != poseFixedTime)
            {
                fromPosition = transform.position;
            }
            Yaw = yaw;
            transform.SetPositionAndRotation(position, Quaternion.Euler(0f, yaw, 0f)); // MUTATION:ROBOT_POSE
            PoseCount++;
            poseFixedTime = now;
            posed = true;
            if (snap)
            {
                fromPosition = position;
                drawnPosition = position;
                VisualYaw = yaw;
            }
            // The body keeps its drawn pose while the root moves under it.
            if (Body != null)
            {
                Body.SetPositionAndRotation(drawnPosition, Quaternion.Euler(0f, VisualYaw, 0f));
            }
            PlaceHumDisc();
        }

        /// <summary>C8: the hum disc under the drawn body, level, at the floor height of the pose plus its lift.</summary>
        private void PlaceHumDisc()
        {
            if (HumDisc != null)
            {
                HumDisc.SetPositionAndRotation(drawnPosition + Vector3.up * HumDiscLift, Quaternion.identity); // MUTATION:HUM_DISC_FOLLOW
            }
        }

        private void OnDestroy()
        {
            // The disc is a sibling: it goes with the robot (a level rebuild destroys both with the root anyway; outside
            // play mode the parent's DestroyImmediate takes it).
            if (HumDisc != null && Application.isPlaying)
            {
                Destroy(HumDisc.gameObject);
            }
        }

        private void LateUpdate()
        {
            float dt = Application.isPlaying && !GamePause.IsPaused ? Time.deltaTime : 0f;
            if (StatusLight != null)
            {
                clock += dt;
                float pulse = 0.5f + 0.5f * Mathf.Sin(clock * Tuning.RobotLightPulseRate * 2f * Mathf.PI);
                StatusLight.localScale = Vector3.one * Mathf.Lerp(Tuning.RobotLightPulseMin, Tuning.RobotLightPulseMax, pulse);
            }
            PulseHumDisc(dt);
            if (Body == null || !posed)
            {
                return;
            }
            // One step behind the rule: from the pose before the last fixed step to its pose, by the time since that step.
            float alpha = Time.fixedTime > poseFixedTime || Time.fixedDeltaTime <= 0f
                ? 1f
                : Mathf.Clamp01((Time.time - Time.fixedTime) / Time.fixedDeltaTime);
            drawnPosition = Vector3.Lerp(fromPosition, transform.position, alpha);
            VisualYaw = Mathf.MoveTowardsAngle(VisualYaw, Yaw, Tuning.RobotTurnRate * dt); // MUTATION:ROBOT_TURN_CAP
            Body.SetPositionAndRotation(drawnPosition, Quaternion.Euler(0f, VisualYaw, 0f));
            PlaceHumDisc();
        }

        /// <summary>
        /// C8: the hum disc's alpha swells once per hum loop (<see cref="Sfx.HumLoopSeconds"/>), from
        /// <see cref="HumDiscPulseMin"/> to 1 of <see cref="HumDiscAlpha"/>, held while paused (dt 0). A property block, so
        /// the one shared material is never changed.
        /// </summary>
        private void PulseHumDisc(float dt)
        {
            if (HumDiscRenderer == null)
            {
                return;
            }
            humClock = Mathf.Repeat(humClock + dt, Sfx.HumLoopSeconds);
            float swell = 0.5f + 0.5f * Mathf.Cos(humClock / Sfx.HumLoopSeconds * 2f * Mathf.PI);
            HumDiscPulse = Mathf.Lerp(HumDiscPulseMin, 1f, swell);
            humBlock ??= new MaterialPropertyBlock();
            Color c = HumDiscColour;
            c.a = HumDiscAlpha * HumDiscPulse;
            humBlock.SetColor(BaseColorId, c);
            HumDiscRenderer.SetPropertyBlock(humBlock);
        }

        /// <summary>
        /// C8: the hum disc, a sibling of the robot under <paramref name="parent"/> (the level root: the budgets count it), in
        /// world space, placed by <see cref="SetPose"/> and LateUpdate. No collider, not an occluder, no shadow.
        /// </summary>
        private void BuildHumDisc(Transform parent)
        {
            var go = new GameObject(HumDiscName) { layer = gameObject.layer };
            go.transform.SetParent(parent, false);
            Mesh mesh = LoadView.CachedMesh("robot hum disc", HumDiscMesh);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = go.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = HumDiscMaterial();
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            renderer.receiveShadows = false;
            renderer.lightProbeUsage = LightProbeUsage.Off;
            renderer.reflectionProbeUsage = ReflectionProbeUsage.Off;
            HumDisc = go.transform;
            HumDiscRenderer = renderer;
            HumDiscRadius = Tuning.RobotHumRadius;
            PulseHumDisc(0f);
        }

        /// <summary>
        /// C8: the one material of every hum disc: alpha blended, unlit, double sided, no depth write (the floor cone's
        /// setup), its base map the band's radial profile (<see cref="HumDiscTexture"/>). The colour comes from each disc's
        /// property block.
        /// </summary>
        public static Material HumDiscMaterial()
        {
            if (humDiscMaterial != null)
            {
                return humDiscMaterial;
            }
            var m = new Material(PrimitiveKit.UnlitTransparent(HumDiscColour)) { name = "Robot hum disc" };
            m.SetTexture("_BaseMap", HumDiscTexture());
            m.SetColor(BaseColorId, new Color(HumDiscColour.r, HumDiscColour.g, HumDiscColour.b, HumDiscAlpha));
            m.hideFlags = HideFlags.DontUnloadUnusedAsset;
            humDiscMaterial = m;
            return m;
        }

        /// <summary>
        /// The band's radial alpha, u = 0 at the inner edge (HumDiscBand inside the radius) to u = 1 on the radius: a fill that
        /// rises from nothing to a fifth, then a soft rim at full alpha over the outer 6 % of the band.
        /// </summary>
        public static float HumDiscProfile(float u)
        {
            u = Mathf.Clamp01(u);
            float fill = 0.2f * u * u;
            float rim = Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.8f, 0.94f, u));
            return Mathf.Max(fill, rim);
        }

        private static Texture2D HumDiscTexture()
        {
            if (humDiscTexture != null)
            {
                return humDiscTexture;
            }
            var t = new Texture2D(HumDiscTexels, 1, TextureFormat.RGBA32, false)
            {
                name = "Robot hum disc band",
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear,
                hideFlags = HideFlags.DontUnloadUnusedAsset,
            };
            var texels = new Color[HumDiscTexels];
            for (int i = 0; i < HumDiscTexels; i++)
            {
                texels[i] = new Color(1f, 1f, 1f, HumDiscProfile(i / (HumDiscTexels - 1f)));
            }
            t.SetPixels(texels);
            t.Apply(false, true);
            humDiscTexture = t;
            return t;
        }

        /// <summary>
        /// The disc's flat band (metres, local: the floor at y = 0, centred on the robot): HumDiscSegments quads from
        /// <see cref="HumDiscBand"/> inside <see cref="Tuning.RobotHumRadius"/> out to it, facing up, u running outward.
        /// </summary>
        private static Mesh HumDiscMesh()
        {
            float outer = Tuning.RobotHumRadius; // MUTATION:HUM_DISC_RADIUS
            float inner = outer - HumDiscBand;
            var vertices = new Vector3[2 * HumDiscSegments];
            var normals = new Vector3[vertices.Length];
            var uv = new Vector2[vertices.Length];
            var triangles = new int[6 * HumDiscSegments];
            for (int s = 0; s < HumDiscSegments; s++)
            {
                float a = 2f * Mathf.PI * s / HumDiscSegments;
                var dir = new Vector3(Mathf.Sin(a), 0f, Mathf.Cos(a));
                vertices[2 * s] = dir * inner;
                vertices[2 * s + 1] = dir * outer;
                normals[2 * s] = normals[2 * s + 1] = Vector3.up;
                uv[2 * s] = new Vector2(0f, 0.5f);
                uv[2 * s + 1] = new Vector2(1f, 0.5f);
                int n = (s + 1) % HumDiscSegments;
                int k = 6 * s;
                // (inner, outer, next outer) and (inner, next outer, next inner): both face +y.
                triangles[k] = 2 * s;
                triangles[k + 1] = 2 * s + 1;
                triangles[k + 2] = 2 * n + 1;
                triangles[k + 3] = 2 * s;
                triangles[k + 4] = 2 * n + 1;
                triangles[k + 5] = 2 * n;
            }
            var mesh = new Mesh { vertices = vertices, normals = normals, uv = uv, triangles = triangles };
            mesh.RecalculateBounds();
            return mesh;
        }

        private void Build()
        {
            int layer = gameObject.layer;
            var body = new GameObject("Body") { layer = layer };
            body.transform.SetParent(transform, false);
            Body = body.transform;
            // M6 (CONTRACT_M6 2.4): the shell is metal (Metal009), the bumper plastic (Plastic006); LitSurface keeps
            // each its own material, apart from the window trim and the frame that otherwise share these colours.
            Part("Shell", LoadView.CachedMesh("robot shell", ShellMesh), PrimitiveKit.LitSurface(ShellColour, Surface.Metal), layer, Surface.Metal, true);
            Part("Bumper", LoadView.CachedMesh("robot bumper", BumperMesh), PrimitiveKit.LitSurface(FurnitureKit.FrameColor, Surface.Plastic), layer,
                Surface.Plastic, true);
            GameObject light = Part("Light", LoadView.CachedMesh("robot light", LightMesh),
                PrimitiveKit.Emissive(LightColour, Tuning.WindowPaneEmission), layer, Surface.Plain, false);
            light.transform.localPosition = new Vector3(0f, ShellTop, LightAhead);
            StatusLight = light.transform;
        }

        private GameObject Part(string name, Mesh mesh, Material material, int layer, Surface surface, bool shadows)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(Body, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = go.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = material;
            renderer.shadowCastingMode = shadows ? ShadowCastingMode.On : ShadowCastingMode.Off;
            renderer.receiveShadows = true;
            PrimitiveKit.Detail(renderer, surface);
            return go;
        }

        // ----- Meshes (metres, local: the floor at y = 0, the front on +z) -----

        /// <summary>
        /// The white shell, a lathe. Soft movers (2026-11-20): its bottom edge and its top edge are rounded (a quarter circle
        /// of 1.6 cm in two steps on top) instead of a single chamfer each, as the furniture bodies' edges.
        /// </summary>
        private static Mesh ShellMesh()
        {
            float r = Tuning.RobotRadius - BumperWidth;
            const float round = 0.016f;
            float diagonal = round * (1f - Mathf.Sqrt(0.5f));
            var b = new MeshBuilder();
            b.AddLathe(Matrix4x4.identity, new[]
            {
                new Vector2(r - 0.008f, Clearance), new Vector2(r - 0.002f, Clearance + 0.003f), new Vector2(r, Clearance + 0.009f),
                new Vector2(r, ShellTop - round), new Vector2(r - diagonal, ShellTop - diagonal), new Vector2(r - round, ShellTop),
            }, Segments, true, true);
            return b.Build();
        }

        /// <summary>The bumper band around the front half, and the lidar turret on top, in the frame's near-black.</summary>
        private static Mesh BumperMesh()
        {
            var b = new MeshBuilder();
            float outer = Tuning.RobotRadius;
            float inner = Tuning.RobotRadius - BumperWidth;
            float bottom = Clearance + 0.012f;
            float top = ShellTop - 0.022f;
            int steps = Mathf.CeilToInt(Segments * BumperSweep / 360f);
            for (int s = 0; s < steps; s++)
            {
                float a0 = (-0.5f * BumperSweep + BumperSweep * s / steps) * Mathf.Deg2Rad;
                float a1 = (-0.5f * BumperSweep + BumperSweep * (s + 1) / steps) * Mathf.Deg2Rad;
                float mid = 0.5f * (a0 + a1);
                Vector3 centre = new Vector3(Mathf.Sin(mid), 0f, Mathf.Cos(mid)) * (0.5f * (outer + inner) * Mathf.Cos(0.5f * (a1 - a0)));
                float chord = 2f * outer * Mathf.Sin(0.5f * (a1 - a0));
                b.AddBox(Matrix4x4.TRS(centre + Vector3.up * (0.5f * (bottom + top)), Quaternion.Euler(0f, mid * Mathf.Rad2Deg, 0f), Vector3.one),
                    new Vector3(chord, top - bottom, outer - inner));
            }
            b.AddLathe(Matrix4x4.Translate(new Vector3(0f, 0f, -TurretBack)), new[]
            {
                new Vector2(TurretRadius, ShellTop - 0.004f), new Vector2(TurretRadius, Tuning.RobotHeight - 0.002f),
                new Vector2(TurretRadius - 0.004f, Tuning.RobotHeight),
            }, Segments, false, true);
            return b.Build();
        }

        private static Mesh LightMesh()
        {
            var b = new MeshBuilder();
            b.AddLathe(Matrix4x4.identity, new[] { new Vector2(LightRadius, -0.001f), new Vector2(LightRadius, 0.003f) }, 10, false, true);
            return b.Build();
        }
    }
}
