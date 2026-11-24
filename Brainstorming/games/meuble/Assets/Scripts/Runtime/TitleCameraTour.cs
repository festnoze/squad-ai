using System.Collections;
using System.Collections.Generic;
using System.IO;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>
    /// M7 title camera: behind the title page, the camera travels endlessly through every room of a dedicated house
    /// (Resources/Levels/title_house.json, not in levels.json, never played) at a piece of furniture's eye level
    /// (Tuning.TitleTourHeight), along a closed centripetal Catmull-Rom loop through hand placed waypoints, at constant
    /// speed by arc length, slowing in turns, looking ahead along the path.
    /// - The level stays passive exactly as the old orbit background did: the title pauses the game (Menu.Apply), so no
    ///   rule runs (no catch, no win) and the inhabitants and the robot hold their start pose. The orbit camera keeps its
    ///   showcase mode; this component runs after it (execution order 250) and overrides the camera pose.
    /// - Clearance: every waypoint keeps at least 0.6 m from walls and door jambs and about 1 m from props, the
    ///   inhabitants' start stations and the robot; each doorway is crossed through its centre, square to its wall, with
    ///   a waypoint on either side. The waypoints belong to title_house.json: edit both together.
    /// - Framing: a horizontal lens shift (Tuning.TitleTourLensShift) puts the vanishing point right of centre, clear of
    ///   the title column on the left.
    /// - While the tour runs over the title house, its vision cones are hidden, the wall fader never hides a wall (its
    ///   target follows the camera) and the rooms' own ceilings (RoomCeilings, CEILING 2026-11-24) close them above the
    ///   camera, which is always below them; an unlit title ceiling is built only when those are switched off
    ///   (RoomCeilings.Disabled). All of it belongs to the level instance, rebuilt when Jouer or the level select loads a level.
    /// - "--titletour &lt;dir&gt;" (a built player): screenshots of the title at several points of the loop, then quits.
    /// </summary>
    [DefaultExecutionOrder(250)] // after OrbitCamera (200), before WallFader (300)
    public sealed class TitleCameraTour : MonoBehaviour
    {
        /// <summary>The title background's level id (Resources/Levels/title_house.json).</summary>
        public const string LevelId = "title_house";

        // The loop, (x, z) in metres, through the six rooms of title_house.json: bureau, chambre, couloir, cuisine,
        // entree, salon, and back into the bureau. Doorways: bureau-chambre (2.25, 4.95), chambre-couloir (4.45, 8.25),
        // couloir-cuisine (11.75, 7.45), cuisine-entree (11.75, 1.95), entree-salon (8.25, 1.95), salon-bureau (4.45, 3.25).
        // The turns round a door jamb follow an arc of about 0.6 m about that jamb.
        private static readonly Vector2[] Waypoints =
        {
            // Bureau, from the salon doorway, heading west then north.
            new Vector2(4.45f, 3.25f), new Vector2(3.75f, 3.3f), new Vector2(2.85f, 3.75f), new Vector2(2.3f, 4.35f),
            new Vector2(2.25f, 4.95f),
            // Chambre, north then east, clear of the bed (west) and the chest of drawers (south east).
            new Vector2(2.4f, 5.6f), new Vector2(2.9f, 6.4f), new Vector2(3.45f, 7.5f), new Vector2(3.9f, 8.15f),
            new Vector2(4.45f, 8.25f),
            // Couloir, on its centre line, then round the jamb into the kitchen doorway.
            new Vector2(5.1f, 8.22f), new Vector2(6.6f, 8.2f), new Vector2(8.6f, 8.2f), new Vector2(10.4f, 8.15f),
            new Vector2(11.25f, 8.1f), new Vector2(11.62f, 7.92f), new Vector2(11.76f, 7.45f),
            // Cuisine, south between the fridge and the counter.
            new Vector2(11.76f, 6.8f), new Vector2(11.55f, 5.3f), new Vector2(11.65f, 3.7f), new Vector2(11.76f, 2.6f),
            new Vector2(11.76f, 1.95f),
            // Entree, round the jamb westward past the console, then round the next jamb north into the salon.
            new Vector2(11.7f, 1.5f), new Vector2(11.2f, 1.22f), new Vector2(10.2f, 1.12f), new Vector2(9.3f, 1.15f),
            new Vector2(8.75f, 1.3f), new Vector2(8.38f, 1.5f), new Vector2(8.25f, 1.95f),
            // Salon, north then west between the robot (south) and Claire (north), back to the bureau doorway.
            new Vector2(8.22f, 2.6f), new Vector2(7.6f, 3.15f), new Vector2(6.6f, 3.3f), new Vector2(5.15f, 3.27f),
        };

        private static readonly Color CeilingColor = new Color(0.56f, 0.48f, 0.4f);

        /// <summary>True while the tour drives the camera (the title is open over the title house).</summary>
        public bool Active { get; private set; }

        /// <summary>Distance travelled along the loop, in metres, in [0, <see cref="Length"/>).</summary>
        public float Distance { get; set; }

        /// <summary>The loop's length, in metres.</summary>
        public float Length { get; private set; }

        private Menu menu;
        private GameState game;
        private Camera view;
        private LevelInstance prepared;
        private Vector2[] samples;
        private float[] cumulative;
        private static bool? hasLevel;

        /// <summary>Adds the tour to the orbit camera's object (once) and wires it to the menu and the game.</summary>
        public static TitleCameraTour Attach(Menu menu, GameState game, OrbitCamera camera)
        {
            if (camera == null)
            {
                return null;
            }
            TitleCameraTour tour = camera.GetComponent<TitleCameraTour>();
            if (tour == null)
            {
                tour = camera.gameObject.AddComponent<TitleCameraTour>();
            }
            tour.menu = menu;
            tour.game = game;
            // FISHEYE: the barrel distortion of this background, on this camera only while the tour runs.
            MenuFisheye.Attach(tour);
            return tour;
        }

        /// <summary>The level the title opens over: the title house, or the first level of levels.json without it.</summary>
        public static string LevelFor(GameState game)
        {
            hasLevel ??= Resources.Load<TextAsset>(LevelLoader.Folder + "/" + LevelId) != null;
            return hasLevel.Value || game == null ? LevelId : game.FirstLevelId;
        }

        private void Awake()
        {
            view = GetComponent<Camera>();
            BuildTable();
        }

        private void Start()
        {
            string dir = Probe.ArgValue("--titletour");
            if (!Application.isEditor && !string.IsNullOrEmpty(dir))
            {
                StartCoroutine(Shots(dir));
            }
        }

        private void LateUpdate()
        {
            bool want = menu != null && game != null && menu.TitleOpen && game.Level != null && game.LevelId == LevelId;
            if (!want)
            {
                if (Active)
                {
                    Active = false;
                    if (view != null)
                    {
                        view.ResetProjectionMatrix();
                    }
                }
                return;
            }
            if (!Active || prepared != game.Level)
            {
                Prepare(game.Level);
            }
            Active = true;
            FollowCeilingTier();
            float dt = Mathf.Min(Time.unscaledDeltaTime, 0.1f);
            Distance = Wrap(Distance + Tuning.TitleTourSpeed * SpeedFactor(Distance) * dt);
            Pose(Distance, out Vector3 position, out Quaternion rotation);
            transform.SetPositionAndRotation(position, rotation);
            if (view != null)
            {
                view.ResetProjectionMatrix();
                Matrix4x4 m = view.projectionMatrix;
                m[0, 2] = -Tuning.TitleTourLensShift;
                view.projectionMatrix = m;
            }
        }

        /// <summary>The camera pose at <paramref name="distance"/> along the loop: eye height, aimed ahead, a little down.</summary>
        public void Pose(float distance, out Vector3 position, out Quaternion rotation)
        {
            Vector2 p = PointAt(distance);
            float ahead = Tuning.TitleTourLookAhead;
            Vector2 aim = (PointAt(distance + ahead * 0.5f) + PointAt(distance + ahead) + PointAt(distance + ahead * 1.5f)) / 3f - p;
            if (aim.sqrMagnitude < 1e-6f)
            {
                aim = PointAt(distance + 0.05f) - p;
            }
            float yaw = Mathf.Atan2(aim.x, aim.y) * Mathf.Rad2Deg;
            position = new Vector3(p.x, Tuning.TitleTourHeight, p.y);
            rotation = Quaternion.Euler(Tuning.TitleTourPitch, yaw, 0f);
        }

        /// <summary>The planar point (x, z) at <paramref name="distance"/> along the loop (wrapped).</summary>
        public Vector2 PointAt(float distance)
        {
            float d = Wrap(distance);
            int lo = 0;
            int hi = cumulative.Length - 1;
            while (hi - lo > 1)
            {
                int mid = (lo + hi) / 2;
                if (cumulative[mid] <= d)
                {
                    lo = mid;
                }
                else
                {
                    hi = mid;
                }
            }
            float span = cumulative[hi] - cumulative[lo];
            float u = span > 1e-6f ? (d - cumulative[lo]) / span : 0f;
            return Vector2.Lerp(samples[lo], samples[hi], u);
        }

        /// <summary>The loop's duration in seconds at the tour speed, turns included.</summary>
        public float LoopSeconds()
        {
            float seconds = 0f;
            const float step = 0.05f;
            for (float d = 0f; d < Length; d += step)
            {
                seconds += step / (Tuning.TitleTourSpeed * SpeedFactor(d));
            }
            return seconds;
        }

        // The speed factor: 1 on straight stretches, Tuning.TitleTourTurnSpeedFactor where the heading turns by 90 degrees
        // or more over Tuning.TitleTourTurnProbe, centred on the point.
        private float SpeedFactor(float distance)
        {
            float half = Tuning.TitleTourTurnProbe * 0.5f;
            Vector2 before = PointAt(distance) - PointAt(distance - half);
            Vector2 after = PointAt(distance + half) - PointAt(distance);
            float angle = Vector2.Angle(before, after);
            return Mathf.Lerp(1f, Tuning.TitleTourTurnSpeedFactor, Mathf.Clamp01(angle / 90f));
        }

        private float Wrap(float d)
        {
            if (Length <= 0f)
            {
                return 0f;
            }
            d %= Length;
            return d < 0f ? d + Length : d;
        }

        // The arc length table of the closed spline: Tuning.TitleTourSamplesPerSegment samples per waypoint segment.
        private void BuildTable()
        {
            int n = Waypoints.Length;
            int per = Mathf.Max(2, Tuning.TitleTourSamplesPerSegment);
            samples = new Vector2[n * per + 1];
            cumulative = new float[samples.Length];
            for (int i = 0; i < n; i++)
            {
                Vector2 p0 = Waypoints[(i - 1 + n) % n];
                Vector2 p1 = Waypoints[i];
                Vector2 p2 = Waypoints[(i + 1) % n];
                Vector2 p3 = Waypoints[(i + 2) % n];
                for (int k = 0; k < per; k++)
                {
                    samples[i * per + k] = CatmullRom(p0, p1, p2, p3, k / (float)per);
                }
            }
            samples[samples.Length - 1] = samples[0];
            for (int i = 1; i < samples.Length; i++)
            {
                cumulative[i] = cumulative[i - 1] + Vector2.Distance(samples[i - 1], samples[i]);
            }
            Length = cumulative[cumulative.Length - 1];
        }

        /// <summary>Centripetal Catmull-Rom (alpha 0.5, Barry and Goldman): no cusp and no overshoot on uneven spacing.</summary>
        private static Vector2 CatmullRom(Vector2 p0, Vector2 p1, Vector2 p2, Vector2 p3, float u)
        {
            float t0 = 0f;
            float t1 = t0 + Mathf.Sqrt(Mathf.Max(Vector2.Distance(p0, p1), 1e-4f));
            float t2 = t1 + Mathf.Sqrt(Mathf.Max(Vector2.Distance(p1, p2), 1e-4f));
            float t3 = t2 + Mathf.Sqrt(Mathf.Max(Vector2.Distance(p2, p3), 1e-4f));
            float t = Mathf.Lerp(t1, t2, u);
            Vector2 a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1;
            Vector2 a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2;
            Vector2 a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3;
            Vector2 b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2;
            Vector2 b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3;
            return (t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2;
        }

        // Once per level instance: hide the cones, keep every wall drawn, close the rooms with a ceiling.
        private void Prepare(LevelInstance level)
        {
            prepared = level;
            foreach (VisionConeView cone in level.Cones)
            {
                if (cone != null)
                {
                    cone.gameObject.SetActive(false);
                }
            }
            WallFader fader = level.Root != null ? level.Root.GetComponent<WallFader>() : null;
            if (fader != null)
            {
                // The camera and the "player" on the same side of every wall plane: no wall is ever hidden.
                fader.Target = transform;
                fader.Furniture = null;
            }
            BuildCeiling(level);
        }

        private void BuildCeiling(LevelInstance level)
        {
            ceiling = null;
            ceilingTier = null;
            // CEILING (2026-11-24): every level now has its own lit ceiling per room (RoomCeilings), which shows from the
            // tour's eye level; the unlit title lid below is only the fallback when those are switched off.
            if (level.Root == null || level.Def == null || RoomCeilings.Of(level) != null)
            {
                return;
            }
            List<RoomDef> rooms = level.Def.AllRooms();
            if (rooms.Count == 0)
            {
                return;
            }
            float minX = float.MaxValue, minZ = float.MaxValue, maxX = float.MinValue, maxZ = float.MinValue, height = 0f;
            foreach (RoomDef r in rooms)
            {
                minX = Mathf.Min(minX, r.X - r.SizeX * 0.5f);
                maxX = Mathf.Max(maxX, r.X + r.SizeX * 0.5f);
                minZ = Mathf.Min(minZ, r.Z - r.SizeZ * 0.5f);
                maxZ = Mathf.Max(maxZ, r.Z + r.SizeZ * 0.5f);
                height = Mathf.Max(height, r.WallHeight > 0f ? r.WallHeight : 2.7f);
            }
            var go = new GameObject("TitleCeiling");
            go.transform.SetParent(level.Root.transform, false);
            go.transform.position = new Vector3((minX + maxX) * 0.5f, height + 0.03f, (minZ + maxZ) * 0.5f);
            go.transform.localScale = new Vector3(maxX - minX + 0.4f, 0.06f, maxZ - minZ + 0.4f);
            go.AddComponent<MeshFilter>().sharedMesh = PrimitiveKit.BoxMesh;
            var renderer = go.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = PrimitiveKit.Unlit(CeilingColor);
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            renderer.receiveShadows = false;
            ceiling = renderer;
            ceilingRooms = rooms;
            ceilingRect = new Rect(minX - 0.2f, minZ - 0.2f, maxX - minX + 0.4f, maxZ - minZ + 0.4f);
            RefreshCeiling();
        }

        // ----- Room lighting on Haut (2026-11-20): the ceiling's corners -----

        // The ceiling is unlit (nothing lights its underside, and it must not go black), so the SSAO of the Haut renderer,
        // which darkens the walls and floors where they meet, never reaches it. On Haut its underside is a quad textured
        // with its own contact shade instead: darker along every wall of each room below, the corners taking the shade of
        // both walls, as a lit ceiling would be where it meets the walls. Bas and Moyen keep the plain box (unchanged).
        // The shade at a wall face, multiplied over the ceiling colour as 1 - CeilingShade, falls off with the distance to
        // that face over CeilingShadeReach (metres, exponential).
        public const float CeilingShade = 0.45f;
        public const float CeilingShadeReach = 0.4f;
        private const float CeilingTexelsPerMetre = 16f;

        /// <summary>Tools (the lighting look tool): the ceiling shade at a wall and its reach instead of the built in ones (0: none).</summary>
        public static float? CeilingShadeOverride;
        public static float? CeilingShadeReachOverride;

        private MeshRenderer ceiling;
        private List<RoomDef> ceilingRooms;
        private Rect ceilingRect;
        private string ceilingTier;
        // One shaded material for the title house (its texture rebuilt only when the house or the shade changes).
        private static Material shadedCeiling;
        private static string shadedKey;
        private static Mesh ceilingQuad;

        /// <summary>The title ceiling's renderer while the tour has built one (tests and tools); null over room ceilings (RoomCeilings).</summary>
        public MeshRenderer Ceiling => ceiling;

        /// <summary>True while the ceiling shows its Haut contact shade (tests and tools).</summary>
        public bool CeilingShaded => ceiling != null && ceiling.sharedMaterial == shadedCeiling && shadedCeiling != null;

        /// <summary>Applies the tier (and the tools' overrides) to the ceiling now (tests and tools; the tour follows the tier by itself).</summary>
        public void RefreshCeiling()
        {
            ceilingTier = "?";
            FollowCeilingTier();
        }

        /// <summary>The Haut contact shade on the ceiling, or the plain box on Bas and Moyen. A string compare per frame, no allocation.</summary>
        private void FollowCeilingTier()
        {
            string tier = QualityTier.Applied;
            if (ceiling == null || (tier == ceilingTier && ceilingTier != "?"))
            {
                return;
            }
            ceilingTier = tier;
            bool high = string.IsNullOrEmpty(tier) || tier == SaveOptions.QualityHigh;
            float shade = CeilingShadeOverride ?? CeilingShade;
            float reach = CeilingShadeReachOverride ?? CeilingShadeReach;
            MeshFilter filter = ceiling.GetComponent<MeshFilter>();
            if (!high || shade <= 0f)
            {
                filter.sharedMesh = PrimitiveKit.BoxMesh;
                ceiling.sharedMaterial = PrimitiveKit.Unlit(CeilingColor);
                return;
            }
            filter.sharedMesh = CeilingQuad();
            ceiling.sharedMaterial = ShadedCeiling(ceilingRooms, ceilingRect, shade, reach);
        }

        /// <summary>The box's underside alone (the unit box's bottom face, facing down), its UV the ceiling's rectangle.</summary>
        private static Mesh CeilingQuad()
        {
            if (ceilingQuad != null)
            {
                return ceilingQuad;
            }
            ceilingQuad = new Mesh { name = "TitleCeilingQuad" };
            ceilingQuad.vertices = new[]
            {
                new Vector3(-0.5f, -0.5f, -0.5f), new Vector3(0.5f, -0.5f, -0.5f), new Vector3(0.5f, -0.5f, 0.5f), new Vector3(-0.5f, -0.5f, 0.5f),
            };
            ceilingQuad.normals = new[] { Vector3.down, Vector3.down, Vector3.down, Vector3.down };
            ceilingQuad.uv = new[] { new Vector2(0f, 0f), new Vector2(1f, 0f), new Vector2(1f, 1f), new Vector2(0f, 1f) };
            ceilingQuad.triangles = new[] { 0, 1, 2, 0, 2, 3 };
            ceilingQuad.RecalculateBounds();
            ceilingQuad.hideFlags = HideFlags.DontUnloadUnusedAsset;
            return ceilingQuad;
        }

        /// <summary>
        /// The ceiling's Haut contact shade (the factor on its colour) over the point (<paramref name="x"/>, <paramref name="z"/>):
        /// in the first room of <paramref name="rooms"/> holding it, the product over the room's four wall faces (its sides,
        /// half a wall thickness in) of 1 - shade * exp(-distance / reach); 1 - shade outside every room (inside a wall).
        /// </summary>
        public static float CeilingShadeAt(IList<RoomDef> rooms, float x, float z, float shade, float reach)
        {
            float k = 1f / Mathf.Max(0.01f, reach);
            foreach (RoomDef r in rooms)
            {
                float half = Mathf.Max(0f, r.WallThickness) * 0.5f;
                float left = x - (r.X - r.SizeX * 0.5f) - half;
                float right = r.X + r.SizeX * 0.5f - half - x;
                float near = z - (r.Z - r.SizeZ * 0.5f) - half;
                float far = r.Z + r.SizeZ * 0.5f - half - z;
                if (left < 0f || right < 0f || near < 0f || far < 0f)
                {
                    continue;
                }
                return (1f - shade * Mathf.Exp(-left * k)) * (1f - shade * Mathf.Exp(-right * k))
                    * (1f - shade * Mathf.Exp(-near * k)) * (1f - shade * Mathf.Exp(-far * k));
            }
            return 1f - shade;
        }

        /// <summary>
        /// The unlit ceiling colour times a small linear texture over <paramref name="rect"/> (x, z): in each room, the product
        /// over its four wall faces of 1 - shade * exp(-distance / reach); outside every room (inside a wall) the shade at a
        /// face. Cached by house and shade.
        /// </summary>
        private static Material ShadedCeiling(List<RoomDef> rooms, Rect rect, float shade, float reach)
        {
            string key = string.Format(System.Globalization.CultureInfo.InvariantCulture, "{0:0.###},{1:0.###},{2:0.###},{3:0.###},{4},{5:0.###},{6:0.###}",
                rect.x, rect.y, rect.width, rect.height, rooms.Count, shade, reach);
            if (shadedCeiling != null && shadedKey == key)
            {
                return shadedCeiling;
            }
            int w = Mathf.Clamp(Mathf.CeilToInt(rect.width * CeilingTexelsPerMetre), 4, 512);
            int h = Mathf.Clamp(Mathf.CeilToInt(rect.height * CeilingTexelsPerMetre), 4, 512);
            var pixels = new Color32[w * h];
            for (int y = 0; y < h; y++)
            {
                float z = rect.y + (y + 0.5f) / h * rect.height;
                for (int x = 0; x < w; x++)
                {
                    float px = rect.x + (x + 0.5f) / w * rect.width;
                    byte b = (byte)Mathf.RoundToInt(Mathf.Clamp01(CeilingShadeAt(rooms, px, z, shade, reach)) * 255f);
                    pixels[y * w + x] = new Color32(b, b, b, 255);
                }
            }
            if (shadedCeiling != null)
            {
                Texture old = shadedCeiling.GetTexture("_BaseMap");
                Destroy(shadedCeiling);
                if (old != null)
                {
                    Destroy(old);
                }
            }
            var texture = new Texture2D(w, h, TextureFormat.RGBA32, false, true)
            {
                name = "TitleCeilingShade", wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear,
            };
            texture.SetPixels32(pixels);
            texture.Apply(false, true);
            texture.hideFlags = HideFlags.DontUnloadUnusedAsset;
            shadedCeiling = new Material(PrimitiveKit.Unlit(CeilingColor)) { name = "Title Ceiling Shaded" };
            shadedCeiling.SetTexture("_BaseMap", texture);
            shadedCeiling.hideFlags = HideFlags.DontUnloadUnusedAsset;
            shadedKey = key;
            return shadedCeiling;
        }

        // "--titletour <dir>": the title at six points of the loop, a text report, then quit.
        private IEnumerator Shots(string dir)
        {
            Directory.CreateDirectory(dir);
            var lines = new List<string>();
            var asset = Resources.Load<TextAsset>(LevelLoader.Folder + "/" + LevelId);
            List<string> issues = asset != null ? LevelValidator.Validate(LevelJson.Parse(asset.text)) : new List<string> { "missing" };
            lines.Add($"{LevelId} issues: " + (issues.Count == 0 ? "none" : string.Join(" | ", issues)));
            float start = Time.realtimeSinceStartup;
            while (!Active && Time.realtimeSinceStartup - start < 20f)
            {
                yield return null;
            }
            yield return new WaitForSecondsRealtime(1.5f);
            lines.Add($"active={Active} level={(game != null ? game.LevelId : "none")} length={Length:0.00} m loop={LoopSeconds():0.0} s"
                + $" screen={Screen.width}x{Screen.height}");
            MenuFisheye fisheye = GetComponent<MenuFisheye>();
            lines.Add(fisheye == null ? "fisheye: none"
                : $"fisheye: active={fisheye.Active} file={MenuCameraSettings.FilePath} {fisheye.Settings} loads={fisheye.Loads}"
                    + $" enqueued frame {MenuFisheye.EnqueuedFrame} recorded frame {MenuFisheye.RecordedFrame} params {MenuFisheye.LastParams} lens {MenuFisheye.LastLens}");
            float[] at = { 0.03f, 0.19f, 0.35f, 0.52f, 0.68f, 0.85f };
            for (int i = 0; i < at.Length; i++)
            {
                Distance = at[i] * Length;
                yield return new WaitForSecondsRealtime(0.5f);
                yield return new WaitForEndOfFrame();
                string name = $"title_tour_{i + 1}.png";
                ScreenCapture.CaptureScreenshot(Path.Combine(dir, name));
                lines.Add($"{name}: d={Distance:0.00} at={transform.position} yaw={transform.eulerAngles.y:0}");
                yield return null;
                yield return null;
            }
            yield return new WaitForSecondsRealtime(0.5f);
            File.WriteAllLines(Path.Combine(dir, "titletour.txt"), lines);
            Application.Quit();
        }
    }
}
