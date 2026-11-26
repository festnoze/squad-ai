using System;
using System.IO;
using OutOfSight.Core;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight.Editor
{
    /// <summary>
    /// M7 walls pass: a look tool, not a check. Builds a few levels in an editor scene and renders the see-through walls to PNGs
    /// from a high camera behind the player (the view of the product owner's report, 2026-11-18) and from the three other
    /// sides, the wall fader applied for each camera, under the game's sun and ambient (no post processing).
    /// -executeMethod OutOfSight.Editor.WallShots.Shoot -wallShots &lt;dir&gt; -wallLevels level4,level12 [-wallLegacy]
    /// Every view in each look of the Walls option (WallLook): _lowered, _translucent (20 %), _translucent50, _both, _none.
    /// With -wallLegacy every view is also rendered "before": the level built part by part, its floor under the walls, its
    /// fills and closures hidden, a faded wall not drawn at all, and the pre M7 rules put back (an outer wall's cap cut only
    /// when its plane separates the camera from the player, outer door frames never cut), an emulation of the old walls.
    /// M9 floors (2026-11-19): `-wallLooks lowered,both` renders only these looks (by file tag); `-wallRooms` adds one high
    /// view centred on each room (`<id>_room_<room>_<tag>.png`), to look at every floor and wall finish of a level.
    /// Tiled walls (2026-11-19): `-wallRoomPitch 35` lowers that per-room view (files `..._p35.png`); `-wallInside
    /// cuisine,sdb` adds four eye-level views from inside each room of these ids, one per wall (with `-wallLooks none`).
    /// </summary>
    public static class WallShots
    {
        public static void Shoot()
        {
            int code = 0;
            try
            {
                string dir = Arg("-wallShots") ?? Path.Combine("TestResults", "walls");
                string[] ids = (Arg("-wallLevels") ?? "level4,level12,level19").Split(',');
                bool legacy = Array.IndexOf(Environment.GetCommandLineArgs(), "-wallLegacy") >= 0;
                rooms = Array.IndexOf(Environment.GetCommandLineArgs(), "-wallRooms") >= 0;
                roomPitch = float.TryParse(Arg("-wallRoomPitch"), System.Globalization.NumberStyles.Float,
                    System.Globalization.CultureInfo.InvariantCulture, out float pitch) ? pitch : DefaultRoomPitch;
                inside = Arg("-wallInside")?.Split(',');
                game = Array.IndexOf(Environment.GetCommandLineArgs(), "-wallGame") >= 0;
                noOverview = Array.IndexOf(Environment.GetCommandLineArgs(), "-wallNoOverview") >= 0;
                string[] only = Arg("-wallLooks")?.Split(',');
                Directory.CreateDirectory(dir);
                foreach (string id in ids)
                {
                    if (legacy)
                    {
                        WallFader.LookOverride = WallLook.Lowered;
                        ShootLevel(dir, id, true, "before");
                    }
                    foreach ((string tag, WallLook look, float opacity) in Looks)
                    {
                        if (only != null && Array.IndexOf(only, tag) < 0)
                        {
                            continue;
                        }
                        WallFader.LookOverride = look;
                        WallFader.OpacityOverride = opacity;
                        ShootLevel(dir, id, false, tag);
                    }
                }
            }
            catch (Exception e)
            {
                Debug.LogError("[WallShots] threw: " + e);
                code = 1;
            }
            finally
            {
                LevelBuilder.CombineRenderers = true;
                WallFader.LookOverride = null;
                WallFader.OpacityOverride = null;
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        /// <summary>The Walls option's four looks (the opacity at the default, and see-through again at 50 %), by file tag.</summary>
        private static readonly (string tag, WallLook look, float opacity)[] Looks =
        {
            ("lowered", WallLook.Lowered, 0.2f), ("translucent", WallLook.SeeThrough, 0.2f), ("translucent50", WallLook.SeeThrough, 0.5f),
            ("both", WallLook.Both, 0.2f), ("none", WallLook.None, 0.2f),
        };

        /// <summary>M9 floors: whether `-wallRooms` asked for one view per room too.</summary>
        private static bool rooms;

        /// <summary>The per-room view's pitch: a steep look down on the floor by default.</summary>
        private const float DefaultRoomPitch = 62f;

        /// <summary>
        /// Tiled walls (2026-11-19): `-wallRoomPitch 35` lowers the per-room view, to see a wall's height (where a tiled
        /// wall's trim sits against the furniture) rather than the floor; such files end in `_p35`.
        /// </summary>
        private static float roomPitch = DefaultRoomPitch;

        /// <summary>
        /// Tiled walls (2026-11-19): `-wallInside cuisine,sdb` renders, for every room of these ids, four eye-level views
        /// from inside it, one toward each wall (`<id>_inside_<room>_<north|east|south|west>_<tag>.png`), a wall seen
        /// whole from the floor to its top. Best with `-wallLooks none`, which never cuts a wall.
        /// </summary>
        private static string[] inside;

        /// <summary>
        /// Walls 4 (2026-11-19): `-wallGame` adds, for every room, the game camera's own view (Tuning.PitchDefault, the
        /// orbit distance) with the player furniture moved to the room's centre, from the four sides, so the Walls option
        /// cuts the walls in front exactly as in play (`<id>_game_<room>_<back|right|front|left>_<tag>.png`).
        /// `-wallInside all` takes every room for the eye-level views.
        /// </summary>
        private static bool game;

        /// <summary>Walls 4: `-wallNoOverview` skips the four high views and the start view (only the per-room views).</summary>
        private static bool noOverview;

        private static void ShootLevel(string dir, string id, bool legacy, string tag)
        {
            LevelDef def = LevelJson.Parse(File.ReadAllText(Path.Combine(LevelAudit.LevelsFolder, id + ".json")));
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            LevelBuilder.CombineRenderers = !legacy;
            LevelInstance level = LevelBuilder.Build(def);
            LevelBuilder.CombineRenderers = true;
            try
            {
                var sun = new GameObject("Sun").AddComponent<Light>();
                sun.type = LightType.Directional;
                sun.color = new Color(1f, 0.87f, 0.67f);
                sun.intensity = 1.35f;
                sun.shadows = LightShadows.Soft;
                sun.shadowStrength = 0.78f;
                sun.transform.rotation = Quaternion.Euler(44f, 32f, 0f);
                RenderSettings.ambientMode = AmbientMode.Trilight;
                RenderSettings.ambientSkyColor = new Color(0.58f, 0.63f, 0.73f);
                RenderSettings.ambientEquatorColor = new Color(0.52f, 0.47f, 0.42f);
                RenderSettings.ambientGroundColor = new Color(0.28f, 0.23f, 0.19f);
                var cam = new GameObject("ShotCamera").AddComponent<Camera>();
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0.15f, 0.16f, 0.19f);
                cam.fieldOfView = 55f;
                cam.nearClipPlane = 0.05f;
                cam.farClipPlane = 80f;
                var fader = level.Root.GetComponent<WallFader>();
                // The first render of a fresh editor comes out tinted while the shaders warm up: throw one away.
                var warm = new RenderTexture(64, 64, 24);
                cam.targetTexture = warm;
                cam.Render();
                cam.targetTexture = null;
                UnityEngine.Object.DestroyImmediate(warm);

                Vector3 player = def.Player.Position;
                Vector3 focus = player + Vector3.up * 0.5f;
                string[] sides = { "back", "right", "front", "left" };
                if (!noOverview)
                {
                    for (int i = 0; i < sides.Length; i++)
                    {
                        Quaternion orbit = Quaternion.Euler(48f, def.Player.Yaw + 90f * i, 0f);
                        Render(cam, level, fader, legacy, player, focus - orbit * Vector3.forward * 9f, orbit, Path.Combine(dir, $"{id}_high_{sides[i]}_{tag}.png"));
                    }
                    Quaternion near = Quaternion.Euler(Tuning.PitchDefault, def.Player.Yaw, 0f);
                    Render(cam, level, fader, legacy, player, focus - near * Vector3.forward * Tuning.OrbitDistance * 1.3f, near,
                        Path.Combine(dir, $"{id}_start_{tag}.png"));
                }
                // Walls 4: the game views in a look that cuts walls, the eye-level views in "none" (nothing cut), so one
                // run with `-wallLooks lowered,none` renders both.
                if (game && WallFader.LookOverride != WallLook.None)
                {
                    // Walls 4: the game camera on each room, the player furniture at its centre (the fader's target).
                    Transform chair = level.Furniture.transform;
                    Vector3 home = chair.position;
                    foreach (RoomDef room in def.AllRooms())
                    {
                        var centre = new Vector3(room.X, home.y, room.Z);
                        chair.position = centre;
                        for (int i = 0; i < sides.Length; i++)
                        {
                            Quaternion view = Quaternion.Euler(Tuning.PitchDefault, def.Player.Yaw + 90f * i, 0f);
                            Vector3 aim = centre + Vector3.up * 0.5f;
                            Render(cam, level, fader, legacy, centre, aim - view * Vector3.forward * Tuning.OrbitDistance * 1.3f, view,
                                Path.Combine(dir, $"{id}_game_{room.Id ?? "room"}_{sides[i]}_{tag}.png"));
                        }
                    }
                    chair.position = home;
                }
                if (rooms)
                {
                    // M9 floors: a steep view down on each room, far enough to frame its larger side.
                    Quaternion down = Quaternion.Euler(roomPitch, def.Player.Yaw, 0f);
                    string suffix = Mathf.Approximately(roomPitch, DefaultRoomPitch) ? "" : "_p" + Mathf.RoundToInt(roomPitch);
                    foreach (RoomDef room in def.AllRooms())
                    {
                        var centre = new Vector3(room.X, 0f, room.Z);
                        float distance = Mathf.Max(5f, Mathf.Max(room.SizeX, room.SizeZ) * 1.15f);
                        Render(cam, level, fader, legacy, centre, centre - down * Vector3.forward * distance, down,
                            Path.Combine(dir, $"{id}_room_{room.Id ?? "room"}_{tag}{suffix}.png"));
                    }
                }
                if (inside != null && (WallFader.LookOverride == WallLook.None || !game))
                {
                    string[] names = { "north", "east", "south", "west" };
                    foreach (RoomDef room in def.AllRooms())
                    {
                        if (room.Id == null || (Array.IndexOf(inside, room.Id) < 0 && Array.IndexOf(inside, "all") < 0))
                        {
                            continue;
                        }
                        var centre = new Vector3(room.X, 0f, room.Z);
                        for (int k = 0; k < names.Length; k++)
                        {
                            // From just inside the opposite wall, at eye height, a little down: the far wall from the floor to its top.
                            float yaw = 90f * k;
                            Vector3 forward = Quaternion.Euler(0f, yaw, 0f) * Vector3.forward;
                            float depth = k % 2 == 0 ? room.SizeZ : room.SizeX;
                            Vector3 eye = centre - forward * Mathf.Max(0f, depth * 0.5f - 0.35f) + Vector3.up * 1.7f;
                            Render(cam, level, fader, legacy, centre, eye, Quaternion.Euler(8f, yaw, 0f),
                                Path.Combine(dir, $"{id}_inside_{room.Id}_{names[k]}_{tag}.png"));
                        }
                    }
                }
            }
            finally
            {
                LevelBuilder.Teardown(level);
            }
        }

        private static void Render(Camera cam, LevelInstance level, WallFader fader, bool legacy, Vector3 player, Vector3 position, Quaternion rotation,
            string file)
        {
            cam.transform.SetPositionAndRotation(position, rotation);
            fader.Apply(position);
            if (legacy)
            {
                Legacy(level, fader, position, player);
            }
            else
            {
                fader.DrawFaded(cam);
            }
            // Walls 4: `-wallSize 960x600` renders smaller, `-wallJpg` writes a JPEG (quality 88) instead of a PNG.
            int width = 1600;
            int height = 1000;
            string size = Arg("-wallSize");
            if (size != null && size.Split('x') is string[] wh && wh.Length == 2 && int.TryParse(wh[0], out int w) && int.TryParse(wh[1], out int h))
            {
                width = w;
                height = h;
            }
            bool jpg = Array.IndexOf(Environment.GetCommandLineArgs(), "-wallJpg") >= 0;
            if (jpg)
            {
                file = Path.ChangeExtension(file, ".jpg");
            }
            var rt = new RenderTexture(width, height, 24) { antiAliasing = 4 };
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
            tex.Apply();
            File.WriteAllBytes(file, jpg ? tex.EncodeToJPG(88) : tex.EncodeToPNG());
            RenderTexture.active = null;
            cam.targetTexture = null;
            UnityEngine.Object.DestroyImmediate(rt);
            UnityEngine.Object.DestroyImmediate(tex);
            Debug.Log($"[WallShots] {file} (parts cut: {fader.HiddenCount})");
        }

        /// <summary>
        /// The old walls on a level built part by part: no floor under the walls, no fill, no closure, a faded wall not drawn;
        /// an outer wall's cap cut only when its plane separates the camera from the player; outer door frames and a shared
        /// line's windows never cut; a shared wall's baseboards cut with it.
        /// </summary>
        private static void Legacy(LevelInstance level, WallFader fader, Vector3 camera, Vector3 player)
        {
            foreach (MeshRenderer r in level.Root.GetComponentsInChildren<MeshRenderer>(true))
            {
                if (r.name == "WallFloor" || r.name == "Fill" || r.name == LevelBuilder.StubName)
                {
                    r.enabled = false;
                    continue;
                }
                Transform wall = r.transform.parent;
                if (wall == null || !wall.name.StartsWith("Wall ", StringComparison.Ordinal))
                {
                    continue;
                }
                bool separates = Vector3.Dot(camera - wall.position, wall.forward) * Vector3.Dot(player - wall.position, wall.forward) < 0f;
                MeshRenderer cap = null;
                float capHeight = float.MinValue;
                foreach (Transform child in wall)
                {
                    if (child.name == "Cap" && Mathf.Abs(child.localRotation.eulerAngles.x - 90f) < 1f)
                    {
                        cap = cap != null ? cap : child.GetComponent<MeshRenderer>();
                        capHeight = Mathf.Max(capHeight, child.localPosition.y);
                    }
                }
                bool outer = cap != null && fader.IsOuter(cap);
                if (r.name == "Cap")
                {
                    // The closures: an end quad (turned about y) or a cap over a crossing band (just under the line's cap).
                    bool end = Mathf.Abs(r.transform.localRotation.eulerAngles.x - 90f) >= 1f;
                    if (end || r.transform.localPosition.y < capHeight - 1e-3f)
                    {
                        r.enabled = false;
                        continue;
                    }
                    if (outer)
                    {
                        r.shadowCastingMode = separates ? ShadowCastingMode.ShadowsOnly : ShadowCastingMode.Off;
                    }
                }
                else if (outer && r.name.StartsWith("Door", StringComparison.Ordinal))
                {
                    r.shadowCastingMode = ShadowCastingMode.On;
                }
                else if (!outer && r.name == "Baseboards")
                {
                    r.shadowCastingMode = separates ? ShadowCastingMode.ShadowsOnly : ShadowCastingMode.Off;
                }
                else if (!outer && (r.name.StartsWith("Frame", StringComparison.Ordinal) || r.name == "Mullion" || r.name == "Transom"
                    || r.name == "WindowPane"))
                {
                    r.shadowCastingMode = ShadowCastingMode.Off;
                }
            }
        }

        private static string Arg(string flag)
        {
            string[] args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == flag)
                {
                    return args[i + 1];
                }
            }
            return null;
        }
    }
}
