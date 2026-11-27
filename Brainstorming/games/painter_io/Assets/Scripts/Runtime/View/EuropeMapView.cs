using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace PainterIO.Runtime
{
    /// <summary>
    /// The 3D Europe map of the Pays screen, rendered by its own camera into a texture (docs/europe/PROGRESSION.md).
    /// Extruded country meshes are tinted by campaign state: locked = dimmed slate, unlocked = map palette with a floating
    /// flag on a pole, won = the human's color with a gold medal. The selected country is lifted and framed by an easing
    /// camera; a selected micro-state also gets a pulsing ring; newly unlocked flags rise in a short reveal.
    /// Every flag shares one cloth mesh, one pole mesh and one material: the cloth waves in the vertex shader
    /// (EuropeMap.shader) and each flag gets its texture and wave phase through a MaterialPropertyBlock, so nothing is
    /// rebuilt on the CPU per frame.
    /// </summary>
    public sealed class EuropeMapView : MonoBehaviour
    {
        private const float MapScale = 0.01f;
        private const float LandHeight = 0.35f;
        private const float SelectedLift = 0.42f;
        private const int MapLayer = 30;
        private static readonly int MainTexture = Shader.PropertyToID("_MainTex");
        private static readonly int Tint = Shader.PropertyToID("_Tint");
        private static readonly int Wave = Shader.PropertyToID("_Wave");
        private static readonly int Phase = Shader.PropertyToID("_Phase");
        private static readonly int Cutout = Shader.PropertyToID("_Cutout");

        /// <summary>Unlocked countries (the original map palette, cycled by list index).</summary>
        private static readonly Color[] LandColors =
        {
            new Color32(49, 111, 125, 255), new Color32(66, 103, 151, 255),
            new Color32(83, 113, 143, 255), new Color32(70, 131, 126, 255),
            new Color32(98, 118, 156, 255)
        };
        /// <summary>Locked countries: dark desaturated slate, clearly below the unlocked palette.</summary>
        public static readonly Color LockedColor = new Color32(40, 48, 61, 255);
        public static readonly Color LockedSelectedColor = new Color32(84, 96, 116, 255);
        /// <summary>The selected unlocked country.</summary>
        public static readonly Color SelectedColor = new Color32(71, 205, 191, 255);
        /// <summary>Won countries take the human's color, mixed this much toward LockedColor (full color when selected).</summary>
        public const float WonColorMute = 0.22f;

        /// <summary>Focus framing: half height of the view around the selected country = extent * gain + margin...</summary>
        public const float FocusGain = 1.45f;
        public const float FocusMargin = 2.6f;
        /// <summary>...never closer than this (micro-states keep their region in view)...</summary>
        public const float MinFocusSize = 8.0f;
        /// <summary>...and reached with this exponential rate (1/s).</summary>
        public const float FocusRate = 6.0f;
        /// <summary>Half height of the view in close-up (SetCloseUp, EuropeShot's flag frames).</summary>
        public const float CloseUpSize = 4.5f;
        /// <summary>Countries whose footprint is below this (map units) are micro-states: pulsing ring, smaller flag.</summary>
        public const float SmallCountryExtent = 0.45f;
        /// <summary>Longest side of the map render texture, in pixels.</summary>
        public const int DisplayMaxSide = 960;

        /// <summary>Cloth height of a floating flag (map units; the width follows the texture's aspect).</summary>
        public const float FlagHeight = 0.95f;
        /// <summary>Pole height; each country gets 0.85x, 1x or 1.15x of it (from its code) so close flags stack.</summary>
        public const float PoleHeight = 2.0f;
        public const float MicroFlagScale = 0.6f;
        public const float SelectedFlagScale = 1.3f;
        /// <summary>The cloth leans back by this angle (degrees) to face the tilted map camera.</summary>
        public const float ClothTilt = 28f;
        public const float MedalSize = 1.15f;

        /// <summary>Reveal of a newly unlocked flag: rise time, and delay between two flags.</summary>
        public const float RevealRiseSeconds = 0.9f;
        public const float RevealStagger = 0.35f;
        /// <summary>Duration of the reveal of two flags (the usual case).</summary>
        public const float RevealSeconds = RevealRiseSeconds + RevealStagger;
        /// <summary>The camera keeps framing the revealed flags this long after the last one rose.</summary>
        public const float RevealHoldSeconds = 0.9f;

        private sealed class Pin
        {
            public Transform Root;
            public float RevealStart = -1f;
        }

        private readonly List<Mesh> meshes = new List<Mesh>();
        private readonly List<Texture2D> flags = new List<Texture2D>();
        private EuropeCatalog.Country[] entries;
        private Material material;
        private Camera mapCamera;
        private RenderTexture display;
        private MeshRenderer[] countries;
        private CountryProgress[] states;
        private bool[] micro;
        private Pin[] pins;
        private MeshRenderer[] medals;
        private Transform flagRoot;
        private Mesh clothMesh, poleMesh, medalMesh;
        private Texture2D medalTexture;
        private Transform ring;
        private Color wonColor = Palette.Colors[0];
        private int selected = -1;
        private bool closeUp;
        private float revealFrameUntil = -1f;
        private float aspect = 1f;
        private Bounds overview;
        private Vector3 focusCenter, viewCenter;
        private float focusSize, viewSize;

        public RenderTexture Display => display;

        /// <summary>Width / height of the render texture (follows the screen's map viewport).</summary>
        public float Aspect => aspect;

        /// <summary>Floating flags currently shown (unlocked, not won countries).</summary>
        public int ActiveFlagCount => CountActive(pins);

        /// <summary>Medals currently shown (won countries).</summary>
        public int ActiveMedalCount
        {
            get
            {
                int n = 0;
                foreach (MeshRenderer m in medals) if (m != null && m.gameObject.activeSelf) n++;
                return n;
            }
        }

        /// <summary>True while a newly unlocked flag is still rising.</summary>
        public bool IsRevealing
        {
            get
            {
                foreach (Pin pin in pins) if (pin != null && pin.RevealStart >= 0f) return true;
                return false;
            }
        }

        /// <summary>True when the country of this list index shows a floating flag.</summary>
        public bool HasFlag(int index) => pins[index] != null && pins[index].Root.gameObject.activeSelf;

        public static EuropeMapView Create(Transform parent, EuropeCatalog.Country[] entries)
        {
            var go = new GameObject("Europe 3D");
            go.transform.SetParent(parent, false);
            go.transform.position = new Vector3(0, 1000, 0);
            var view = go.AddComponent<EuropeMapView>();
            try
            {
                view.Build(entries);
                return view;
            }
            catch
            {
                Destroy(go);
                throw;
            }
        }

        private void Build(EuropeCatalog.Country[] list)
        {
            entries = list;
            var shader = Resources.Load<Shader>("Shaders/EuropeMap");
            if (shader == null) throw new System.InvalidOperationException("EuropeMap shader introuvable.");
            material = new Material(shader);
            countries = new MeshRenderer[entries.Length];
            states = new CountryProgress[entries.Length];
            micro = new bool[entries.Length];
            pins = new Pin[entries.Length];
            medals = new MeshRenderer[entries.Length];
            var bounds = new Bounds();
            for (int i = 0; i < entries.Length; i++)
            {
                var entry = entries[i];
                flags.Add(null);
                states[i] = CountryProgress.Locked;   // until ApplyStates
                countries[i] = AddMesh(transform, entry.code + " " + entry.name, BuildLand(entry));
                Vector3 footprint = countries[i].bounds.size;
                micro[i] = Mathf.Max(footprint.x, footprint.z) < SmallCountryExtent;
                if (i == 0) bounds = countries[i].bounds;
                else bounds.Encapsulate(countries[i].bounds);
            }

            mapCamera = new GameObject("Europe camera").AddComponent<Camera>();
            mapCamera.transform.SetParent(transform, false);
            mapCamera.transform.rotation = Quaternion.Euler(62f, -8f, 0);
            mapCamera.clearFlags = CameraClearFlags.SolidColor;
            mapCamera.backgroundColor = new Color32(13, 25, 45, 255);
            mapCamera.orthographic = true;
            mapCamera.cullingMask = 1 << MapLayer;
            mapCamera.allowHDR = false;
            mapCamera.allowMSAA = false;
            mapCamera.nearClipPlane = 1;
            mapCamera.farClipPlane = 230;
            overview = bounds;
            SetAspect(1f);

            flagRoot = new GameObject("Flags").transform;
            flagRoot.SetParent(transform, false);
            BuildSharedMeshes();
            BuildRing();
            for (int i = 0; i < entries.Length; i++) RefreshCountry(i);
            focusCenter = viewCenter = overview.center;
            focusSize = viewSize = HalfHeight(overview, 1.10f, 1.0f);
            ApplyView();
        }

        // ------------------------------------------------------------------------------------------------------------
        // Campaign state.

        /// <summary>
        /// Shows the campaign: one state per list index, and the human's color for the won countries. Flags and medals are
        /// created on first need and then only shown or hidden.
        /// </summary>
        public void ApplyStates(CountryProgress[] newStates, Color humanColor)
        {
            wonColor = Color.Lerp(humanColor, LockedColor, WonColorMute);
            for (int i = 0; i < entries.Length && i < newStates.Length; i++) states[i] = newStates[i];
            for (int i = 0; i < entries.Length; i++) RefreshCountry(i);
        }

        /// <summary>The flags of these list indices rise one after the other (RevealStagger apart), their land flashing.</summary>
        /// <remarks>The camera frames all of them (and the selection) until RevealHoldSeconds after the last one rose.</remarks>
        public void PlayReveal(IReadOnlyList<int> indices)
        {
            float now = Time.unscaledTime;
            int k = 0;
            Bounds frame = default;
            foreach (int i in indices)
            {
                if (i < 0 || i >= entries.Length || states[i] != CountryProgress.Unlocked) continue;
                Pin pin = GetPin(i);
                pin.RevealStart = now + k * RevealStagger;
                pin.Root.localScale = Vector3.zero;
                Bounds bounds = LandBounds(i);
                if (k == 0) frame = bounds;
                else frame.Encapsulate(bounds);
                k++;
            }
            if (k == 0) return;
            if (selected >= 0) frame.Encapsulate(LandBounds(selected));
            revealFrameUntil = now + (k - 1) * RevealStagger + RevealRiseSeconds + RevealHoldSeconds;
            float full = HalfHeight(overview, 1.10f, 1.0f);
            focusSize = Mathf.Clamp(HalfHeight(frame, 1.15f, FocusMargin + PoleHeight * 0.5f), MinFocusSize, full);
            focusCenter = new Vector3(frame.center.x, transform.position.y + LandHeight + PoleHeight * 0.4f, frame.center.z);
        }

        /// <summary>World bounds of a country's land, without the selection lift.</summary>
        private Bounds LandBounds(int index)
        {
            Bounds bounds = countries[index].bounds;
            bounds.center -= countries[index].transform.position - transform.position;
            return bounds;
        }

        /// <summary>Close framing of the selected country's flag (EuropeShot frames); false goes back to the region view.</summary>
        public void SetCloseUp(bool on)
        {
            closeUp = on;
            if (selected >= 0) Focus(selected);
        }

        private Color ColorFor(int i)
        {
            bool isSelected = i == selected;
            switch (states[i])
            {
                case CountryProgress.Locked: return isSelected ? LockedSelectedColor : LockedColor;
                case CountryProgress.Won: return isSelected ? Color.Lerp(wonColor, Color.white, 0.25f) : wonColor;
                default: return isSelected ? SelectedColor : LandColors[i % LandColors.Length];
            }
        }

        private void RefreshCountry(int i)
        {
            bool isSelected = i == selected;
            Vector3 lift = isSelected ? Vector3.up * SelectedLift : Vector3.zero;
            countries[i].transform.localPosition = lift;
            TintMesh(countries[i], ColorFor(i));

            if (states[i] == CountryProgress.Unlocked)
            {
                Pin pin = GetPin(i);
                pin.Root.gameObject.SetActive(true);
                pin.Root.localPosition = Position(entries[i].label, LandHeight) + lift;
                if (pin.RevealStart < 0f) pin.Root.localScale = Vector3.one * FlagScale(i);
            }
            else if (pins[i] != null)
            {
                pins[i].RevealStart = -1f;
                pins[i].Root.gameObject.SetActive(false);
            }

            if (states[i] == CountryProgress.Won)
            {
                MeshRenderer medal = GetMedal(i);
                medal.gameObject.SetActive(true);
                float size = MedalSize * (micro[i] ? MicroFlagScale : 1f);
                medal.transform.localPosition = Position(entries[i].label, LandHeight + 0.15f + size * 0.5f) + lift;
                medal.transform.rotation = mapCamera.transform.rotation;
                medal.transform.localScale = Vector3.one * size;
            }
            else if (medals[i] != null) medals[i].gameObject.SetActive(false);
        }

        private float FlagScale(int i) => (micro[i] ? MicroFlagScale : 1f) * (i == selected ? SelectedFlagScale : 1f);

        // ------------------------------------------------------------------------------------------------------------
        // Selection and camera.

        public Texture2D Select(int index, EuropeCatalog.Country entry)
        {
            int previous = selected;
            selected = index;
            if (previous >= 0 && previous != index) RefreshCountry(previous);
            RefreshCountry(index);
            Focus(index);
            ring.gameObject.SetActive(micro[index]);
            ring.localPosition = Position(entry.label, LandHeight + SelectedLift + 0.04f);
            return FlagTexture(index);
        }

        private Texture2D FlagTexture(int index)
        {
            if (flags[index] == null) flags[index] = Resources.Load<Texture2D>("EuropeFlags/" + entries[index].code);
            return flags[index];
        }

        /// <summary>
        /// Matches the render texture to the screen's map viewport (width / height). Returns true when the texture was
        /// replaced (the caller re-binds Display).
        /// </summary>
        public bool SetAspect(float widthOverHeight)
        {
            widthOverHeight = Mathf.Clamp(widthOverHeight, 0.4f, 2.5f);
            if (display != null && Mathf.Abs(widthOverHeight - aspect) < 0.01f) return false;
            aspect = widthOverHeight;
            int width = aspect >= 1f ? DisplayMaxSide : Mathf.RoundToInt(DisplayMaxSide * aspect);
            int height = aspect >= 1f ? Mathf.RoundToInt(DisplayMaxSide / aspect) : DisplayMaxSide;
            RenderTexture old = display;
            display = new RenderTexture(width, height, 24) { name = "Europe map", antiAliasing = 1 };
            mapCamera.targetTexture = display;
            mapCamera.aspect = aspect;
            if (old != null)
            {
                old.Release();
                Destroy(old);
            }
            focusSize = Mathf.Min(focusSize, HalfHeight(overview, 1.10f, 1.0f));
            return true;
        }

        /// <summary>Half height of the orthographic view that frames the bounds, for the current aspect.</summary>
        private float HalfHeight(Bounds bounds, float gain, float margin)
        {
            Vector3 right = mapCamera.transform.right;
            Vector3 up = mapCamera.transform.up;
            Vector3 half = bounds.extents;
            Vector3 xz = new Vector3(half.x, 0, half.z);
            float horizontal = Vector3.Dot(xz, new Vector3(Mathf.Abs(right.x), 0, Mathf.Abs(right.z)));
            float vertical = Vector3.Dot(xz, new Vector3(Mathf.Abs(up.x), 0, Mathf.Abs(up.z)));
            return Mathf.Max(horizontal / aspect, vertical) * gain + margin;
        }

        /// <summary>Frames the selected country and its region (or its flag in close-up); the view eases there.</summary>
        private void Focus(int index)
        {
            if (closeUp)
            {
                revealFrameUntil = -1f;
                float pole = PoleHeight * PoleFactor(entries[index].code) * FlagScale(index);
                focusSize = CloseUpSize;
                focusCenter = transform.position + Position(entries[index].label, LandHeight + SelectedLift + pole * 0.8f);
                return;
            }
            revealFrameUntil = -1f;
            Bounds bounds = LandBounds(index);
            float full = HalfHeight(overview, 1.10f, 1.0f);
            focusSize = Mathf.Clamp(HalfHeight(bounds, FocusGain, FocusMargin), MinFocusSize, full);
            focusCenter = new Vector3(bounds.center.x, transform.position.y + LandHeight, bounds.center.z);
        }

        /// <summary>Jumps to the overview of the whole map; the next Select eases from there (used when the screen opens).</summary>
        public void ShowOverview()
        {
            viewCenter = overview.center;
            viewSize = HalfHeight(overview, 1.10f, 1.0f);
            ApplyView();
        }

        private void ApplyView()
        {
            mapCamera.orthographicSize = viewSize;
            mapCamera.transform.position = viewCenter - mapCamera.transform.forward * 95;
        }

        private void LateUpdate()
        {
            float dt = Mathf.Min(Time.unscaledDeltaTime, 0.1f);
            float k = 1f - Mathf.Exp(-FocusRate * dt);
            viewCenter = Vector3.Lerp(viewCenter, focusCenter, k);
            viewSize = Mathf.Lerp(viewSize, focusSize, k);
            ApplyView();
            if (ring.gameObject.activeSelf)
            {
                float pulse = 1f + 0.12f * Mathf.Sin(Time.unscaledTime * 5f);
                float size = 0.11f * viewSize * pulse;
                ring.localScale = new Vector3(size, 1, size);
            }
            AnimateReveal();
            if (revealFrameUntil > 0f && Time.unscaledTime > revealFrameUntil && selected >= 0) Focus(selected);
        }

        private void AnimateReveal()
        {
            float now = Time.unscaledTime;
            for (int i = 0; i < pins.Length; i++)
            {
                Pin pin = pins[i];
                if (pin == null || pin.RevealStart < 0f) continue;
                float t = (now - pin.RevealStart) / RevealRiseSeconds;
                if (t >= 1f)
                {
                    pin.RevealStart = -1f;
                    pin.Root.localScale = Vector3.one * FlagScale(i);
                    TintMesh(countries[i], ColorFor(i));
                    continue;
                }
                float rise = t <= 0f ? 0f : EaseOutBack(t);
                pin.Root.localScale = Vector3.one * (FlagScale(i) * rise);
                float flash = t <= 0f ? 0f : 1f - t;
                TintMesh(countries[i], Color.Lerp(ColorFor(i), new Color(0.96f, 1f, 0.97f), flash * 0.85f));
            }
        }

        private static float EaseOutBack(float t)
        {
            const float c1 = 1.70158f, c3 = c1 + 1f;
            float u = t - 1f;
            return 1f + c3 * u * u * u + c1 * u * u;
        }

        public int Pick(Vector2 uv, EuropeCatalog.Country[] list)
        {
            Ray ray = mapCamera.ViewportPointToRay(uv);
            var plane = new Plane(Vector3.up, transform.position + Vector3.up * LandHeight);
            if (!plane.Raycast(ray, out float hit)) return -1;
            Vector3 world = ray.GetPoint(hit) - transform.position;
            var point = new Vector2(world.x, world.z) / MapScale;
            int nearest = -1;
            float best = 110 * 110;
            for (int i = 0; i < list.Length; i++)
            {
                var entry = list[i];
                foreach (var part in entry.parts)
                {
                    if (!Contains(part.outer, point)) continue;
                    bool inHole = false;
                    foreach (var hole in part.holes) inHole |= Contains(hole.points, point);
                    if (!inHole) return i;
                }
                float distance = (entry.label.Vector - point).sqrMagnitude;
                if (distance >= best) continue;
                best = distance;
                nearest = i;
            }
            return nearest;
        }

        private static bool Contains(EuropeCatalog.Point[] ring, Vector2 p)
        {
            bool inside = false;
            for (int i = 0, j = ring.Length - 1; i < ring.Length; j = i++)
            {
                var a = ring[i];
                var b = ring[j];
                if ((a.y > p.y) != (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x)
                    inside = !inside;
            }
            return inside;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Construction.

        private Mesh BuildLand(EuropeCatalog.Country country)
        {
            var positions = new List<Vector3>();
            var indices = new List<int>();
            var outlines = new List<int>();
            var colors = new List<Color32>();
            foreach (var part in country.parts)
            {
                int top = positions.Count;
                foreach (var point in part.vertices)
                {
                    positions.Add(Position(point, LandHeight));
                    colors.Add(new Color32(255, 255, 255, 255));
                }
                foreach (int index in part.triangles) indices.Add(top + index);
                AddWall(part.outer, positions, colors, indices, outlines);
                foreach (var hole in part.holes) AddWall(hole.points, positions, colors, indices, outlines);
            }
            var mesh = new Mesh { name = country.code, indexFormat = positions.Count > 65535 ? IndexFormat.UInt32 : IndexFormat.UInt16 };
            mesh.SetVertices(positions);
            mesh.SetColors(colors);
            mesh.subMeshCount = 2;
            mesh.SetTriangles(indices, 0);
            mesh.SetIndices(outlines, MeshTopology.Lines, 1);
            return mesh;
        }

        private static void AddWall(EuropeCatalog.Point[] points, List<Vector3> vertices, List<Color32> colors,
            List<int> indices, List<int> outlines)
        {
            for (int i = 0; i < points.Length; i++)
            {
                Vector3 a = Position(points[i], LandHeight);
                Vector3 b = Position(points[(i + 1) % points.Length], LandHeight);
                float length = Vector3.Distance(a, b);
                if (length < 0.00001f) continue;
                int first = vertices.Count;
                vertices.Add(a);
                vertices.Add(b);
                vertices.Add(new Vector3(b.x, 0, b.z));
                vertices.Add(new Vector3(a.x, 0, a.z));
                byte shade = (byte)(120 + 45 * Mathf.Abs((b.x - a.x) / length));
                for (int j = 0; j < 4; j++) colors.Add(new Color32(shade, shade, shade, 255));
                Quad(indices, first, first + 1, first + 2, first + 3);
                outlines.Add(vertices.Count);
                vertices.Add(a + Vector3.up * 0.004f);
                outlines.Add(vertices.Count);
                vertices.Add(b + Vector3.up * 0.004f);
                colors.Add(new Color32(92, 108, 118, 255));
                colors.Add(new Color32(92, 108, 118, 255));
            }
        }

        /// <summary>The cloth (pole edge at u = 0, hanging from y = 0 to -1), the pole and the medal quad, shared by all flags.</summary>
        private void BuildSharedMeshes()
        {
            var vertices = new List<Vector3>();
            var uvs = new List<Vector2>();
            var indices = new List<int>();
            const int segments = 16;
            for (int i = 0; i <= segments; i++)
            {
                float u = i / (float)segments;
                vertices.Add(new Vector3(u, -1, 0));
                vertices.Add(new Vector3(u, 0, 0));
                uvs.Add(new Vector2(u, 0));
                uvs.Add(new Vector2(u, 1));
                if (i < segments) Quad(indices, i * 2, i * 2 + 2, i * 2 + 3, i * 2 + 1);
            }
            clothMesh = new Mesh { name = "Flag cloth" };
            clothMesh.SetVertices(vertices);
            clothMesh.SetUVs(0, uvs);
            clothMesh.SetTriangles(indices, 0);
            clothMesh.bounds = new Bounds(new Vector3(0.5f, -0.5f, 0), new Vector3(1.2f, 1.4f, 0.6f));   // room for the wave
            meshes.Add(clothMesh);

            var primitive = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            poleMesh = Instantiate(primitive.GetComponent<MeshFilter>().sharedMesh);
            DestroyImmediate(primitive);   // never rendered by the game camera, not even for one frame
            var poleColors = new Color32[poleMesh.vertexCount];
            for (int i = 0; i < poleColors.Length; i++) poleColors[i] = new Color32(219, 228, 235, 255);
            poleMesh.colors32 = poleColors;
            poleMesh.name = "Flagpole";
            meshes.Add(poleMesh);

            medalMesh = new Mesh { name = "Medal" };
            medalMesh.SetVertices(new List<Vector3> { new Vector3(-0.5f, -0.5f, 0), new Vector3(0.5f, -0.5f, 0), new Vector3(0.5f, 0.5f, 0), new Vector3(-0.5f, 0.5f, 0) });
            medalMesh.SetUVs(0, new List<Vector2> { new Vector2(0, 0), new Vector2(1, 0), new Vector2(1, 1), new Vector2(0, 1) });
            medalMesh.SetColors(new List<Color32> { Color.white, Color.white, Color.white, Color.white });
            medalMesh.SetTriangles(new[] { 0, 2, 1, 0, 3, 2 }, 0);
            meshes.Add(medalMesh);
            medalTexture = BuildMedalTexture();
        }

        /// <summary>The conquered medal: a gold disc with a darker rim and a white check mark (alpha 0 outside the disc).</summary>
        private static Texture2D BuildMedalTexture()
        {
            const int size = 64;
            var texture = new Texture2D(size, size, TextureFormat.RGBA32, false) { name = "Europe medal", wrapMode = TextureWrapMode.Clamp };
            var pixels = new Color32[size * size];
            var gold = new Color32(250, 196, 60, 255);
            var rim = new Color32(166, 104, 22, 255);
            var check = new Color32(255, 255, 255, 255);
            Vector2 center = new Vector2(size * 0.5f, size * 0.5f);
            Vector2 a = new Vector2(18, 33), b = new Vector2(28, 22), c = new Vector2(46, 43);
            for (int y = 0; y < size; y++)
            for (int x = 0; x < size; x++)
            {
                var p = new Vector2(x + 0.5f, y + 0.5f);
                float r = Vector2.Distance(p, center);
                Color32 color = new Color32(0, 0, 0, 0);
                if (r <= 30f)
                {
                    color = r > 25.5f ? rim : gold;
                    if (Mathf.Min(SegmentDistance(p, a, b), SegmentDistance(p, b, c)) < 3.4f) color = check;
                }
                pixels[y * size + x] = color;
            }
            texture.SetPixels32(pixels);
            texture.Apply(false, true);
            return texture;
        }

        private static float SegmentDistance(Vector2 p, Vector2 a, Vector2 b)
        {
            Vector2 ab = b - a;
            float t = Mathf.Clamp01(Vector2.Dot(p - a, ab) / ab.sqrMagnitude);
            return Vector2.Distance(p, a + ab * t);
        }

        /// <summary>The floating flag of a country (created on first need): a pole and a GPU-waved cloth.</summary>
        private Pin GetPin(int i)
        {
            if (pins[i] != null) return pins[i];
            string code = entries[i].code;
            var root = new GameObject("Flag " + code) { layer = MapLayer }.transform;
            root.SetParent(flagRoot, false);
            float pole = PoleHeight * PoleFactor(code);

            var poleRenderer = AddRenderer(root, "Pole", poleMesh);
            poleRenderer.transform.localPosition = Vector3.up * (pole * 0.5f);
            poleRenderer.transform.localScale = new Vector3(0.07f, pole * 0.5f, 0.07f);

            Texture2D texture = FlagTexture(i);
            float width = texture != null ? FlagHeight * texture.width / texture.height : FlagHeight * 1.5f;
            var cloth = AddRenderer(root, "Cloth", clothMesh);
            cloth.transform.localPosition = Vector3.up * pole;
            cloth.transform.localRotation = Quaternion.Euler(ClothTilt, 0, 0);
            cloth.transform.localScale = new Vector3(width, FlagHeight, FlagHeight);
            var properties = new MaterialPropertyBlock();
            if (texture != null) properties.SetTexture(MainTexture, texture);
            properties.SetFloat(Wave, 1f);
            properties.SetFloat(Phase, (Hash(code) % 7) * 0.9f);
            properties.SetColor(Tint, Color.white);
            cloth.SetPropertyBlock(properties);

            pins[i] = new Pin { Root = root };
            return pins[i];
        }

        private MeshRenderer GetMedal(int i)
        {
            if (medals[i] != null) return medals[i];
            var medal = AddRenderer(flagRoot, "Medal " + entries[i].code, medalMesh);
            var properties = new MaterialPropertyBlock();
            properties.SetTexture(MainTexture, medalTexture);
            properties.SetFloat(Cutout, 1f);
            properties.SetColor(Tint, Color.white);
            medal.SetPropertyBlock(properties);
            medals[i] = medal;
            return medal;
        }

        /// <summary>0.85, 1 or 1.15, from the country code: neighboring flags stand at different heights.</summary>
        private static float PoleFactor(string code) => 0.85f + 0.15f * (Hash(code) % 3);

        private static int Hash(string code)
        {
            int h = 17;
            foreach (char ch in code) h = h * 31 + ch;
            return h & 0x7fffffff;
        }

        /// <summary>Flat pulsing ring that marks a selected micro-state (its land is a few pixels at most).</summary>
        private void BuildRing()
        {
            const int segments = 48;
            var vertices = new List<Vector3>();
            var colors = new List<Color32>();
            var indices = new List<int>();
            for (int i = 0; i <= segments; i++)
            {
                float a = i * Mathf.PI * 2f / segments;
                var dir = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a));
                vertices.Add(dir * 0.70f);
                vertices.Add(dir);
                colors.Add(new Color32(255, 255, 255, 255));
                colors.Add(new Color32(255, 255, 255, 255));
                if (i < segments) Quad(indices, i * 2, i * 2 + 1, i * 2 + 3, i * 2 + 2);
            }
            var mesh = new Mesh { name = "Selection ring" };
            mesh.SetVertices(vertices);
            mesh.SetColors(colors);
            mesh.SetTriangles(indices, 0);
            var renderer = AddMesh(transform, "Selection ring", mesh);
            TintMesh(renderer, new Color32(120, 255, 236, 255));
            ring = renderer.transform;
            ring.gameObject.SetActive(false);
        }

        private static void Quad(List<int> indices, int a, int b, int c, int d)
        {
            indices.Add(a); indices.Add(b); indices.Add(c);
            indices.Add(a); indices.Add(c); indices.Add(d);
        }

        /// <summary>A renderer of an owned mesh (destroyed with the view).</summary>
        private MeshRenderer AddMesh(Transform parent, string name, Mesh mesh)
        {
            meshes.Add(mesh);
            return AddRenderer(parent, name, mesh);
        }

        /// <summary>A renderer of a shared mesh, on the map layer, without shadows.</summary>
        private MeshRenderer AddRenderer(Transform parent, string name, Mesh mesh)
        {
            var go = new GameObject(name) { layer = MapLayer };
            go.transform.SetParent(parent, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = go.AddComponent<MeshRenderer>();
            renderer.sharedMaterials = mesh.subMeshCount == 2 ? new[] { material, material } : new[] { material };
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            renderer.receiveShadows = false;
            renderer.lightProbeUsage = LightProbeUsage.Off;
            return renderer;
        }

        private static void TintMesh(Renderer renderer, Color color)
        {
            var properties = new MaterialPropertyBlock();
            renderer.GetPropertyBlock(properties);
            properties.SetColor(Tint, color);
            renderer.SetPropertyBlock(properties);
        }

        private static int CountActive(Pin[] list)
        {
            int n = 0;
            foreach (Pin pin in list) if (pin != null && pin.Root.gameObject.activeSelf) n++;
            return n;
        }

        private static Vector3 Position(EuropeCatalog.Point point, float height) =>
            new Vector3(point.x * MapScale, height, point.y * MapScale);

        private void OnDestroy()
        {
            if (display != null)
            {
                display.Release();
                Destroy(display);
            }
            if (material != null) Destroy(material);
            if (medalTexture != null) Destroy(medalTexture);
            foreach (Mesh mesh in meshes) Destroy(mesh);
        }
    }
}
