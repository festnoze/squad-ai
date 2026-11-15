using Meuble.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace Meuble
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5.md 4, 16.8 and 16.12, PRD 4.8): the robot vacuum's visual and transform. Watchers draws it, the
    /// game steps it: GameState reads <see cref="Path"/> (the <see cref="RobotPath"/> of its <see cref="RobotDef"/>, built here)
    /// and calls <see cref="SetPose"/> once per fixed step; LevelBuilder calls <see cref="Create"/> and lists it in
    /// LevelInstance.Robots.
    /// <list type="bullet">
    /// <item>A procedural disc of radius <see cref="Tuning.RobotRadius"/> and height <see cref="Tuning.RobotHeight"/>, its
    /// front on its local +z (the heading): a light shell, a dark bumper around the front half and a small lidar turret,
    /// and a pale status light near the front that pulses (visual only, held while paused).</item>
    /// <item>No collider (inhabitants walk across it, 16.8), not on the Occluder layer (it hides nothing from a watcher),
    /// no NavMesh source (the NavMesh reads colliders only).</item>
    /// <item>Budgets: 3 material slots (shell, bumper, light), in colours every level already draws (the window trim, the
    /// near-black frame, the window pane's glow), so it adds no material where a level has a window.</item>
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

        public RobotDef Def { get; private set; }

        /// <summary>The robot's timeline (core): the game reads its position and heading at each step.</summary>
        public RobotPath Path { get; private set; }

        /// <summary>The yaw of the last <see cref="SetPose"/> (YawMath: 0 faces +z).</summary>
        public float Yaw { get; private set; }

        /// <summary>The planar position of the last <see cref="SetPose"/> (its y as given).</summary>
        public Vector3 Position => transform.position;

        /// <summary>The status light (its scale pulses).</summary>
        public Transform StatusLight { get; private set; }

        /// <summary>The number of <see cref="SetPose"/> calls (tests).</summary>
        public int PoseCount { get; private set; }

        private float clock;

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
            robot.SetPose(robot.Path.PositionAt(0f), robot.Path.HeadingAt(0f));
            robot.PoseCount = 0;
            return robot;
        }

        /// <summary>Puts the robot at <paramref name="position"/> (world), facing <paramref name="yaw"/> (degrees, YawMath).</summary>
        public void SetPose(Vector3 position, float yaw)
        {
            Yaw = yaw;
            transform.SetPositionAndRotation(position, Quaternion.Euler(0f, yaw, 0f)); // MUTATION:ROBOT_POSE
            PoseCount++;
        }

        private void LateUpdate()
        {
            if (StatusLight == null)
            {
                return;
            }
            clock += Application.isPlaying && !GamePause.IsPaused ? Time.deltaTime : 0f;
            float pulse = 0.5f + 0.5f * Mathf.Sin(clock * Tuning.RobotLightPulseRate * 2f * Mathf.PI);
            StatusLight.localScale = Vector3.one * Mathf.Lerp(0.75f, 1.15f, pulse);
        }

        private void Build()
        {
            int layer = gameObject.layer;
            Part("Shell", LoadView.CachedMesh("robot shell", ShellMesh), PrimitiveKit.Lit(ShellColour), layer, Surface.Plaster, true);
            Part("Bumper", LoadView.CachedMesh("robot bumper", BumperMesh), PrimitiveKit.Lit(FurnitureKit.FrameColor), layer, Surface.Plain, true);
            GameObject light = Part("Light", LoadView.CachedMesh("robot light", LightMesh),
                PrimitiveKit.Emissive(LightColour, Tuning.WindowPaneEmission), layer, Surface.Plain, false);
            light.transform.localPosition = new Vector3(0f, ShellTop, LightAhead);
            StatusLight = light.transform;
        }

        private GameObject Part(string name, Mesh mesh, Material material, int layer, Surface surface, bool shadows)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = go.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = material;
            renderer.shadowCastingMode = shadows ? ShadowCastingMode.On : ShadowCastingMode.Off;
            renderer.receiveShadows = true;
            PrimitiveKit.Detail(renderer, surface);
            return go;
        }

        // ----- Meshes (metres, local: the floor at y = 0, the front on +z) -----

        private static Mesh ShellMesh()
        {
            float r = Tuning.RobotRadius - BumperWidth;
            var b = new MeshBuilder();
            b.AddLathe(Matrix4x4.identity, new[]
            {
                new Vector2(r - 0.01f, Clearance), new Vector2(r, Clearance + 0.01f), new Vector2(r, ShellTop - 0.008f),
                new Vector2(r - 0.008f, ShellTop),
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
