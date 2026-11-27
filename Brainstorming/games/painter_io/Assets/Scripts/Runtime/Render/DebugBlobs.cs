// Owned by B1. Debug-only stand-in for the actor field contributors of B2 (command line "-debugblobs"), so the liquid
// look of threads, necks and retraction fronts can be judged before the real actor views exist. It follows the mesh
// conventions of contract 12.2 (FieldBlob on LiquidLayers.QuadMesh, FieldStroke as a world-space triangle list with
// uv0 = (amplitude multiplier, cross coordinate)) and the shapes of 12.3 (thread visible radius 0.17 with the 2.2x neck
// over the first 0.3 u, pearl neck blob of visible radius 0.8 x HeadRadius, retraction bulb of visible radius 0.26).
// It never draws beads (pearls and droplets are B2's Bead graph) and disables itself as soon as a real ActorViews (one
// whose root is not named "(stub)") exists.
using System.Collections.Generic;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace PainterIO.Runtime
{
    public sealed class DebugBlobs : MonoBehaviour
    {
        public const string Flag = "-debugblobs";
        private const float ThreadRadius = 0.17f;
        private const float NeckLength = 0.3f;
        private const float NeckWidening = 2.2f;
        private const float SampleSpacing = 0.15f;
        private const float BulbRadius = 0.26f;
        private const float CutGap = 0.25f;

        private static readonly int IdChannel = Shader.PropertyToID("_Channel");
        private static readonly int IdAmplitude = Shader.PropertyToID("_Amplitude");

        private sealed class PlayerParts
        {
            public MeshRenderer Neck;
            public MeshRenderer Bulb;
            public MeshRenderer Stroke;
            public Mesh StrokeMesh;
        }

        private readonly List<PlayerParts> parts = new List<PlayerParts>();
        private readonly List<Vector3> verts = new List<Vector3>();
        private readonly List<Vector2> uvs = new List<Vector2>();
        private readonly List<int> tris = new List<int>();
        private readonly List<Vector2> samples = new List<Vector2>();
        private readonly List<float> radii = new List<float>();
        private GameDirector director;
        private GameSession session;
        private Material blobMaterial, strokeMaterial;
        private bool realViewsChecked;

        public static DebugBlobs TryCreate(Transform parent, GameDirector d)
        {
            if (!LaunchArgs.Has(Flag)) return null;
            var go = new GameObject("DebugBlobs");
            if (parent != null) go.transform.SetParent(parent, false);
            var b = go.AddComponent<DebugBlobs>();
            b.director = d;
            b.blobMaterial = new Material(Resources.Load<Shader>("Shaders/FieldBlob")) { name = "PIO DebugBlob" };
            b.strokeMaterial = new Material(Resources.Load<Shader>("Shaders/FieldStroke")) { name = "PIO DebugStroke" };
            for (int p = 0; p < 4; p++) b.parts.Add(b.BuildParts(p));
            Debug.Log("[PainterIO] DebugBlobs on (-debugblobs): B1 stand-in actor field contributors");
            return b;
        }

        public void Bind(GameSession s)
        {
            session = s;
        }

        private PlayerParts BuildParts(int p)
        {
            var pp = new PlayerParts();
            var block = new MaterialPropertyBlock();
            block.SetVector(IdChannel, LiquidLayers.ChannelMask(p));
            block.SetFloat(IdAmplitude, 1f);
            pp.Neck = NewRenderer("DebugNeck" + p, LiquidLayers.QuadMesh, blobMaterial, block);
            pp.Bulb = NewRenderer("DebugBulb" + p, LiquidLayers.QuadMesh, blobMaterial, block);
            pp.StrokeMesh = new Mesh { name = "DebugStroke" + p, hideFlags = HideFlags.HideAndDontSave };
            pp.StrokeMesh.MarkDynamic();
            pp.Stroke = NewRenderer("DebugStroke" + p, pp.StrokeMesh, strokeMaterial, block);
            return pp;
        }

        private MeshRenderer NewRenderer(string name, Mesh mesh, Material material, MaterialPropertyBlock block)
        {
            var go = new GameObject(name) { layer = LiquidLayers.Field };
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = material;
            r.SetPropertyBlock(block);
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            r.lightProbeUsage = LightProbeUsage.Off;
            r.reflectionProbeUsage = ReflectionProbeUsage.Off;
            r.enabled = false;
            return r;
        }

        private void LateUpdate()
        {
            if (!realViewsChecked && director != null)
            {
                foreach (Component c in director.Subsystems)
                {
                    if (c is ActorViews && !c.gameObject.name.Contains("(stub)"))
                    {
                        Debug.Log("[PainterIO] DebugBlobs off: the real ActorViews exists");
                        gameObject.SetActive(false);
                        return;
                    }
                }
                realViewsChecked = true;
            }
            GameSession s = director != null ? director.Session : session;
            if (s == null) return;
            Simulation sim = s.Sim;
            for (int p = 0; p < parts.Count; p++)
            {
                PlayerParts pp = parts[p];
                if (p >= sim.Players.Count || !sim.Players[p].Alive)
                {
                    pp.Neck.enabled = pp.Bulb.enabled = pp.Stroke.enabled = false;
                    continue;
                }
                UpdatePlayer(s, sim.Players[p], pp);
            }
        }

        private void UpdatePlayer(GameSession s, PlayerState player, PlayerParts pp)
        {
            Vector2 head = s.RenderPos(player.Index);
            float support = LiquidLayers.SupportForVisibleRadius(0.8f * (float)Tuning.HeadRadius, 1f);
            pp.Neck.transform.SetPositionAndRotation(new Vector3(head.x, head.y, 0f), Quaternion.identity);
            pp.Neck.transform.localScale = new Vector3(2f * support, 2f * support, 1f);
            pp.Neck.enabled = true;

            Trail trail = player.Trail;
            if (player.Home || trail.Count < 2)
            {
                pp.Stroke.enabled = false;
                pp.Bulb.enabled = false;
                return;
            }
            float lead = Vector2.Distance(head, new Vector2((float)player.Pos.X, (float)player.Pos.Y));
            double end = System.Math.Max(0.0, trail.Length - lead);
            verts.Clear();
            uvs.Clear();
            tris.Clear();
            double sr = s.RenderSparkS(player.Index);
            if (double.IsNaN(sr))
            {
                AddPiece(trail, 0.0, end, head, true, false);
                pp.Bulb.enabled = false;
            }
            else
            {
                double sCut = player.Spark.SCut;
                if (sCut - CutGap > 0.05) AddPiece(trail, 0.0, sCut - CutGap, head, false, true);
                if (sr < end - 0.05) AddPiece(trail, sr, end, head, true, false);
                Vec2d front = trail.PointAt(System.Math.Min(sr, end));
                Vec2d dir = trail.DirectionAt(System.Math.Min(sr, end));
                float bulbSupport = LiquidLayers.SupportForVisibleRadius(BulbRadius, 1f);
                const float stretch = 1.25f;
                pp.Bulb.transform.SetPositionAndRotation(new Vector3((float)front.X, (float)front.Y, 0f),
                    Quaternion.Euler(0f, 0f, Mathf.Rad2Deg * Mathf.Atan2((float)dir.Y, (float)dir.X)));
                pp.Bulb.transform.localScale = new Vector3(2f * bulbSupport * stretch, 2f * bulbSupport / stretch, 1f);
                pp.Bulb.enabled = sr < end;
            }
            Mesh m = pp.StrokeMesh;
            m.Clear();
            if (tris.Count == 0)
            {
                pp.Stroke.enabled = false;
                return;
            }
            m.SetVertices(verts);
            m.SetUVs(0, uvs);
            m.SetTriangles(tris, 0, false);
            Bounds b = new Bounds(verts[0], Vector3.zero);
            for (int k = 1; k < verts.Count; k++) b.Encapsulate(verts[k]);
            b.Expand(new Vector3(2f, 2f, 1f));
            m.bounds = b;
            pp.Stroke.enabled = true;
        }

        // One strip on [s0, s1]; neck = widen the first 0.3 u (piece starting at the exit point); taper = pinched end.
        private void AddPiece(Trail trail, double s0, double s1, Vector2 head, bool endsAtHead, bool taper)
        {
            if (s1 <= s0) return;
            samples.Clear();
            radii.Clear();
            int n = Mathf.Max(2, Mathf.CeilToInt((float)((s1 - s0) / SampleSpacing)) + 1);
            for (int k = 0; k < n; k++)
            {
                double s = s0 + (s1 - s0) * k / (n - 1);
                Vec2d p = trail.PointAt(s);
                Vector2 v = new Vector2((float)p.X, (float)p.Y);
                if (endsAtHead && k == n - 1) v = head;
                samples.Add(v);
                float r = ThreadRadius;
                if (s0 <= 1e-6 && s < NeckLength) r *= Mathf.Lerp(NeckWidening, 1f, (float)(s / NeckLength));
                if (endsAtHead && s1 - s < 0.4) r *= Mathf.Lerp(0.85f, 1f, (float)((s1 - s) / 0.4));
                if (taper && s1 - s < 0.3) r *= Mathf.Lerp(0.35f, 1f, (float)((s1 - s) / 0.3));
                radii.Add(r);
            }
            int baseIndex = verts.Count;
            for (int k = 0; k < n; k++)
            {
                Vector2 a = samples[Mathf.Max(0, k - 1)];
                Vector2 b = samples[Mathf.Min(n - 1, k + 1)];
                Vector2 t = b - a;
                if (t.sqrMagnitude < 1e-12f) t = Vector2.right;
                t.Normalize();
                Vector2 nrm = new Vector2(-t.y, t.x);
                float w = LiquidLayers.SupportForVisibleRadius(radii[k], 1f);
                Vector2 c = samples[k];
                verts.Add(new Vector3(c.x + nrm.x * w, c.y + nrm.y * w, 0f));
                uvs.Add(new Vector2(1f, 1f));
                verts.Add(new Vector3(c.x - nrm.x * w, c.y - nrm.y * w, 0f));
                uvs.Add(new Vector2(1f, -1f));
            }
            for (int k = 0; k < n - 1; k++)
            {
                int i0 = baseIndex + 2 * k;
                tris.Add(i0);
                tris.Add(i0 + 2);
                tris.Add(i0 + 1);
                tris.Add(i0 + 1);
                tris.Add(i0 + 2);
                tris.Add(i0 + 3);
            }
        }

        private void OnDestroy()
        {
            foreach (PlayerParts pp in parts) LiquidRenderer.SafeDestroy(pp.StrokeMesh);
            LiquidRenderer.SafeDestroy(blobMaterial);
            LiquidRenderer.SafeDestroy(strokeMaterial);
        }
    }
}
