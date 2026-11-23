using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>
    /// Levels v2 (C4, LEVELS_V2 D26, wave1/code_features.json "Lit zones"): one lit zone of a level, made visible. Under a
    /// ceiling light the dark does not hide the floor lamp: FurnitureController.SightRangeFactor is 1 while the lamp's centre
    /// stands in a <see cref="LitZoneDef"/>, switched on or off. That rule lives in FurnitureController; this component only
    /// shows where it applies and hands the zones to the player furniture (<see cref="Build"/>).
    ///
    /// Per zone: a ceiling fixture (a thin glowing ring at the light's height, hollow and double sided so it never hides the
    /// player furniture from the high camera), an unshadowed spot light straight down that covers the zone, and a soft
    /// additive floor pool a little larger than the zone, whose fade starts at the zone's edge. Visual only: no collider,
    /// Default layer, no shadow (the sun stays the one shadowed light, Main.LookProblems), so vision, the NavMesh and the
    /// x-ray never see it.
    ///
    /// The light carries this component in its parents, the marker <see cref="IsZoneLight"/> reads: LampLight's room dimming
    /// skips it (a lamp switched off in that room must not dim the very light that exposes it). Quality tiers follow
    /// RoomLights: Bas switches the spot off (the ring and the pool still show the zone), Moyen and Haut keep it.
    ///
    /// Budgets: two renderers per zone (ring and pool). The ring uses the floor lamp's glow material (LampLight), which a lit
    /// zone level always has (the validator wants the floor lamp), and the pool one shared transparent material: a level
    /// gains at most one material, whatever its zone count. LevelAudit.CheckBudgets counts them with the rest of the level.
    /// </summary>
    public sealed class LitZoneView : MonoBehaviour
    {
        /// <summary>The name of the root under the level root.</summary>
        public const string RootName = "LitZones";

        // Not in Tuning: presentation only, the rules never read any of it.
        // The source hangs this far under the top of the walls (there is no ceiling), and never higher than SourceMax.
        private const float UnderWallTop = 0.12f;
        private const float SourceMax = 2.6f;
        // The light its pool centre gets (added linear light, the sun gives a lit floor about 1): a little more than the
        // brightest room light (RoomLights moods, 0.7), so the zone reads as the brightest floor of its room.
        private const float PoolLight = 0.9f;
        // RoomLights' falloff numbers: the range ends at RangeOverReach times the height, where its smooth window keeps
        // about RangeKeep of the inverse square light.
        private const float RangeOverReach = 1.9f;
        private const float RangeKeep = 0.82f;
        // The cone covers the zone's corners with this margin, within these angles.
        private const float ConeMargin = 1.2f;
        private const float MinSpotAngle = 50f;
        private const float MaxSpotAngle = 140f;
        private static readonly Color LightColour = new Color(1f, 0.93f, 0.8f);

        // The ring: radius, band width and segments. Its material is the floor lamp's glow (LampLight.GlowColor x 1.9).
        private const float RingRadius = 0.32f;
        private const float RingBand = 0.05f;
        private const int RingSegments = 32;
        private static readonly Color RingColour = new Color(1f, 0.8f, 0.46f);
        private const float RingIntensity = 1.9f;

        // The pool: PoolMargin past the zone on every side (the fade), PoolLift over the floor (over a rug), its colour and
        // peak alpha (additive), and the texture size of its profile.
        private const float PoolMargin = 0.3f;
        private const float PoolLift = 0.018f;
        private static readonly Color PoolColour = new Color(1f, 0.86f, 0.6f, 0.22f);
        private const int PoolTexels = 64;

        private static Material poolMaterial;
        private static Texture2D poolTexture;

        /// <summary>The zone this view shows.</summary>
        public LitZoneDef Zone { get; private set; }

        /// <summary>The room the zone stands in (null when it stands in none: the validator reports that).</summary>
        public RoomDef Room { get; private set; }

        /// <summary>The zone's unshadowed spot light.</summary>
        public Light Light { get; private set; }

        /// <summary>The light's intensity as built (nothing dims it: LampLight skips it).</summary>
        public float Intensity { get; private set; }

        /// <summary>The ceiling fixture's ring renderer.</summary>
        public MeshRenderer Fixture { get; private set; }

        /// <summary>The floor pool's renderer.</summary>
        public MeshRenderer Pool { get; private set; }

        /// <summary>The tier applied last ("low", "medium" or "high").</summary>
        public string Tier { get; private set; }

        private string seenTier;

        /// <summary>
        /// The one LevelBuilder hook (after RoomLights.Build): hands <paramref name="def"/>'s lit zones to the player furniture
        /// (the rule, FurnitureController.SightRangeFactor) and builds one view per zone under a "LitZones" root. Builds
        /// nothing for a level without zones. Returns the views, in level order.
        /// </summary>
        public static List<LitZoneView> Build(LevelDef def, Transform root, FurnitureController furniture)
        {
            var views = new List<LitZoneView>();
            if (furniture != null)
            {
                furniture.LitZones = def?.LitZones;
            }
            if (def == null || root == null || def.LitZones == null || def.LitZones.Count == 0)
            {
                return views;
            }
            var group = new GameObject(RootName) { layer = 0 };
            group.transform.SetParent(root, false);
            for (int i = 0; i < def.LitZones.Count; i++)
            {
                LitZoneDef zone = def.LitZones[i];
                if (zone == null || zone.SizeX <= 0f || zone.SizeZ <= 0f)
                {
                    continue;
                }
                views.Add(BuildZone(def, zone, i, group.transform));
            }
            return views;
        }

        /// <summary>True for a light that belongs to a lit zone (LampLight's room dimming leaves it alone).</summary>
        public static bool IsZoneLight(Light light)
        {
            return light != null && light.GetComponentInParent<LitZoneView>() != null;
        }

        private static LitZoneView BuildZone(LevelDef def, LitZoneDef zone, int index, Transform parent)
        {
            Vector3 centre = def.Floor.OnFloor(zone.Position);
            RoomDef room = def.RoomAt(zone.Position);
            float wallHeight = room != null && room.WallHeight > 0f ? room.WallHeight : 2.7f;
            float height = Mathf.Min(SourceMax, wallHeight - UnderWallTop);

            string name = string.IsNullOrEmpty(zone.Name) ? "#" + (index + 1) : zone.Name;
            var go = new GameObject("LitZone " + name) { layer = 0 };
            go.transform.SetParent(parent, false);
            go.transform.position = centre;
            var view = go.AddComponent<LitZoneView>();
            view.Zone = zone;
            view.Room = room;

            // The spot, straight down from the ring's centre, wide enough for the zone's corners.
            var lightGo = new GameObject("LitZoneLight") { layer = 0 };
            lightGo.transform.SetParent(go.transform, false);
            lightGo.transform.localPosition = new Vector3(0f, height, 0f);
            lightGo.transform.rotation = Quaternion.LookRotation(Vector3.down, Vector3.forward);
            Light l = lightGo.AddComponent<Light>();
            float halfDiagonal = 0.5f * Mathf.Sqrt(zone.SizeX * zone.SizeX + zone.SizeZ * zone.SizeZ);
            float angle = Mathf.Clamp(2f * Mathf.Atan(ConeMargin * halfDiagonal / height) * Mathf.Rad2Deg, MinSpotAngle, MaxSpotAngle);
            l.type = LightType.Spot;
            l.shadows = LightShadows.None;
            l.color = LightColour;
            l.intensity = PoolLight * height * height / RangeKeep;
            l.range = RangeOverReach * height;
            l.bounceIntensity = 0f;
            l.renderMode = LightRenderMode.Auto;
            l.spotAngle = angle;
            l.innerSpotAngle = angle * 0.55f;
            view.Light = l;
            view.Intensity = l.intensity;

            // The ceiling fixture: a thin glowing ring at the light's height.
            GameObject ring = PrimitiveKit.Part(go.transform, "LitZoneFixture", RingMesh(), new Vector3(0f, height, 0f), Quaternion.identity,
                Vector3.one, PrimitiveKit.Emissive(RingColour, RingIntensity), 0);
            view.Fixture = Quiet(ring.GetComponent<MeshRenderer>());

            // The floor pool: the zone plus its fade, just over the floor (and over a rug).
            GameObject pool = PrimitiveKit.Part(go.transform, "LitZonePool", PoolMesh(zone.SizeX + 2f * PoolMargin, zone.SizeZ + 2f * PoolMargin),
                new Vector3(0f, PoolLift, 0f), Quaternion.identity, Vector3.one, PoolMaterial(), 0);
            view.Pool = Quiet(pool.GetComponent<MeshRenderer>());

            view.ApplyTier(QualityTier.Applied);
            view.seenTier = QualityTier.Applied;
            return view;
        }

        private static MeshRenderer Quiet(MeshRenderer renderer)
        {
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            renderer.receiveShadows = false;
            renderer.lightProbeUsage = LightProbeUsage.Off;
            renderer.reflectionProbeUsage = ReflectionProbeUsage.Off;
            return renderer;
        }

        /// <summary>Bas switches the spot off; Moyen and Haut keep it (and edit mode, no tier). Never touches the intensity.</summary>
        public void ApplyTier(string quality)
        {
            Tier = string.IsNullOrEmpty(quality) ? SaveOptions.QualityHigh : quality;
            bool on = Tier != SaveOptions.QualityLow;
            if (Light != null && Light.enabled != on)
            {
                Light.enabled = on;
            }
        }

        private void LateUpdate()
        {
            // The Qualite option can change while a level is played: follow it (a string compare, no allocation).
            string tier = QualityTier.Applied;
            if (tier != seenTier)
            {
                seenTier = tier;
                ApplyTier(tier);
            }
        }

        // ----- Meshes and the pool material (build time only) -----

        /// <summary>A flat ring at y = 0, facing up and down (both windings), RingBand wide out to RingRadius.</summary>
        private static Mesh RingMesh()
        {
            float outer = RingRadius;
            float inner = RingRadius - RingBand;
            var vertices = new Vector3[2 * RingSegments];
            var normals = new Vector3[vertices.Length];
            var triangles = new int[12 * RingSegments];
            for (int s = 0; s < RingSegments; s++)
            {
                float a = 2f * Mathf.PI * s / RingSegments;
                var dir = new Vector3(Mathf.Sin(a), 0f, Mathf.Cos(a));
                vertices[2 * s] = dir * inner;
                vertices[2 * s + 1] = dir * outer;
                normals[2 * s] = normals[2 * s + 1] = Vector3.up;
                int n = (s + 1) % RingSegments;
                int i0 = 2 * s, o0 = 2 * s + 1, i1 = 2 * n, o1 = 2 * n + 1;
                int t = 12 * s;
                // One side (seen from below, clockwise there: Unity's front face) ...
                triangles[t] = i0; triangles[t + 1] = i1; triangles[t + 2] = o0;
                triangles[t + 3] = o0; triangles[t + 4] = i1; triangles[t + 5] = o1;
                // ... and the other, seen from above (the same quads, reversed).
                triangles[t + 6] = i0; triangles[t + 7] = o0; triangles[t + 8] = i1;
                triangles[t + 9] = o0; triangles[t + 10] = o1; triangles[t + 11] = i1;
            }
            var mesh = new Mesh { name = "LitZone ring" };
            mesh.vertices = vertices;
            mesh.normals = normals;
            mesh.triangles = triangles;
            mesh.RecalculateBounds();
            return mesh;
        }

        /// <summary>A flat quad of <paramref name="sizeX"/> by <paramref name="sizeZ"/> at y = 0, facing up, uv 0 to 1.</summary>
        private static Mesh PoolMesh(float sizeX, float sizeZ)
        {
            float hx = sizeX * 0.5f;
            float hz = sizeZ * 0.5f;
            var mesh = new Mesh { name = "LitZone pool" };
            mesh.vertices = new[] { new Vector3(-hx, 0f, -hz), new Vector3(-hx, 0f, hz), new Vector3(hx, 0f, hz), new Vector3(hx, 0f, -hz) };
            mesh.normals = new[] { Vector3.up, Vector3.up, Vector3.up, Vector3.up };
            mesh.uv = new[] { new Vector2(0f, 0f), new Vector2(0f, 1f), new Vector2(1f, 1f), new Vector2(1f, 0f) };
            mesh.triangles = new[] { 0, 1, 2, 0, 2, 3 };
            mesh.RecalculateBounds();
            return mesh;
        }

        /// <summary>
        /// The pool's alpha at (u, v) in [0, 1]: full over a rounded rectangle, fading to nothing at the quad's edge. The fade
        /// is in uv, so on a quad PoolMargin larger than its zone it starts about at the zone's edge whatever the zone size.
        /// </summary>
        public static float PoolProfile(float u, float v)
        {
            float x = Mathf.Abs(2f * u - 1f);
            float y = Mathf.Abs(2f * v - 1f);
            // A superellipse (power 4): a rectangle with soft corners.
            float r = Mathf.Pow(Mathf.Pow(x, 4f) + Mathf.Pow(y, 4f), 0.25f);
            return 1f - Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.72f, 1f, r));
        }

        /// <summary>The one material of every pool: additive, unlit, no depth write, its base map <see cref="PoolProfile"/>.</summary>
        private static Material PoolMaterial()
        {
            if (poolMaterial != null)
            {
                return poolMaterial;
            }
            var m = new Material(PrimitiveKit.UnlitTransparent(PoolColour)) { name = "LitZone pool" };
            // Additive: the pool adds light to the floor, it never greys it.
            m.SetFloat("_Blend", 2f);
            m.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            m.SetFloat("_DstBlend", (float)BlendMode.One);
            m.SetFloat("_SrcBlendAlpha", (float)BlendMode.Zero);
            m.SetFloat("_DstBlendAlpha", (float)BlendMode.One);
            m.SetFloat("_Cull", (float)CullMode.Back);
            m.SetTexture("_BaseMap", PoolTexture());
            m.SetColor("_BaseColor", PoolColour);
            m.hideFlags = HideFlags.DontUnloadUnusedAsset;
            poolMaterial = m;
            return m;
        }

        private static Texture2D PoolTexture()
        {
            if (poolTexture != null)
            {
                return poolTexture;
            }
            var t = new Texture2D(PoolTexels, PoolTexels, TextureFormat.RGBA32, false)
            {
                name = "LitZone pool profile",
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear,
                hideFlags = HideFlags.DontUnloadUnusedAsset,
            };
            var texels = new Color[PoolTexels * PoolTexels];
            for (int j = 0; j < PoolTexels; j++)
            {
                for (int i = 0; i < PoolTexels; i++)
                {
                    float a = PoolProfile((i + 0.5f) / PoolTexels, (j + 0.5f) / PoolTexels);
                    texels[j * PoolTexels + i] = new Color(1f, 1f, 1f, a);
                }
            }
            t.SetPixels(texels);
            t.Apply(false, true);
            poolTexture = t;
            return t;
        }
    }
}
