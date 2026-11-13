using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using Meuble.Core;
using UnityEditor;
using UnityEngine;

namespace Meuble.Editor
{
    /// <summary>
    /// Builds Assets/Resources/ModelCatalog.asset from the imported models (docs/CONTRACT_M3.md 3). Called by
    /// Builder.SetupAndCompile and before every player build. Idempotent: the asset is written only when a
    /// measured value changed.
    ///
    /// Everything is measured on a temporary instance of the imported GLB, never typed by hand:
    /// - static models: the bounds of every renderer in root space (native size and centre);
    /// - rigged models: the bounds of the skinned mesh baked in its rest pose, the head bone, the eye centroid
    ///   (the vertices of the "Eyes" material) in head bone space, the facing (eyes ahead of the head bone),
    ///   and the eye height, averaged over the Idle clip (the pose of a dwelling inhabitant).
    /// Only the yaw offsets of the static models come from the contract table: facing cannot be measured from
    /// bounds (the facing test of probe step 22 checks them against the procedural backrests).
    /// </summary>
    public static class ModelCatalogBuilder
    {
        public const string AssetPath = "Assets/Resources/ModelCatalog.asset";
        private const string Kenney = "Assets/ThirdParty/Models/Kenney/";
        private const string Quaternius = "Assets/ThirdParty/Models/Quaternius/";

        /// <summary>The head bone of the Quaternius HumanArmature skeleton (M3_ASSETS 6.1, read from the GLB).</summary>
        public const string HeadBoneName = "Head";

        /// <summary>The material of the eyes in the Quaternius humans: its submesh gives the eye centroid.</summary>
        public const string EyeMaterialName = "Eyes";

        /// <summary>The clip whose mean pose calibrates the eye height (matched with EndsWith, as InhabitantRig does).</summary>
        public const string IdleSuffix = "_Idle";

        private const int IdleSamples = 24;

        /// <summary>The eyes are looked for in this top fraction of the body height.</summary>
        private const float HeadRegion = 0.2f;

        private struct Spec
        {
            public string Id;
            public string Path;
            public float Yaw;
            public bool Rigged;

            public Spec(string id, string path, float yaw, bool rigged)
            {
                Id = id;
                Path = path;
                Yaw = yaw;
                Rigged = rigged;
            }
        }

        // CONTRACT_M3 3: Kenney seats face -Z in glTF (backrest on +Z). The procedural chair's backrest is on -z,
        // so the chair and the armchair turn 180; the procedural sofa's backrest is on +z, so the sofa keeps 0.
        // M4 bodies (CONTRACT_M4 2): the armchair body and the "armchair" prop face +z with their backrest on -z
        // (FurnitureKit.Armchair), as the chair: 180. The bar stool and the round floor lamp have no back: the top
        // 15 % of their vertices is centred on the footprint (measured from the GLBs), so any quarter turn fits and
        // they keep 0. The office chair has no model (procedural, FurnitureKit.OfficeChair).
        // The rigged humans' yaw is measured (Yaw is ignored for them).
        private static readonly Spec[] Specs =
        {
            new Spec(ModelCatalog.KenneyChair, Kenney + "kenney_chair.glb", 180f, false),
            new Spec(ModelCatalog.KenneySofa, Kenney + "kenney_lounge_sofa.glb", 0f, false),
            new Spec(ModelCatalog.KenneyRug, Kenney + "kenney_rug_rectangle.glb", 0f, false),
            new Spec(ModelCatalog.KenneyDoormat, Kenney + "kenney_rug_square.glb", 0f, false),
            new Spec(ModelCatalog.KenneyArmchair, Kenney + "kenney_lounge_chair.glb", 180f, false),
            new Spec(ModelCatalog.KenneyStool, Kenney + "kenney_bar_stool.glb", 0f, false),
            new Spec(ModelCatalog.KenneyFloorLamp, Kenney + "kenney_lamp_round_floor.glb", 0f, false),
            new Spec(ModelCatalog.QuaterniusMan, Quaternius + "quaternius_man.glb", 0f, true),
            new Spec(ModelCatalog.QuaterniusWoman, Quaternius + "quaternius_woman.glb", 0f, true),
        };

        [MenuItem("Meuble/Build Model Catalog")]
        public static void Build()
        {
            var entries = new List<ModelCatalog.Entry>();
            var log = new StringBuilder("[ModelCatalogBuilder] catalog:\n");
            foreach (Spec spec in Specs)
            {
                ModelCatalog.Entry entry = Measure(spec, log);
                if (entry != null)
                {
                    entries.Add(entry);
                }
            }

            var catalog = AssetDatabase.LoadAssetAtPath<ModelCatalog>(AssetPath);
            if (catalog == null)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(AssetPath) ?? "Assets/Resources");
                catalog = ScriptableObject.CreateInstance<ModelCatalog>();
                catalog.entries = entries;
                AssetDatabase.CreateAsset(catalog, AssetPath);
                log.Append("  created ").Append(AssetPath).Append('\n');
            }
            else if (!SameEntries(catalog.entries, entries))
            {
                catalog.entries = entries;
                EditorUtility.SetDirty(catalog);
                log.Append("  updated ").Append(AssetPath).Append('\n');
            }
            else
            {
                log.Append("  unchanged ").Append(AssetPath).Append('\n');
            }
            AssetDatabase.SaveAssets();
            Debug.Log(log.ToString());
        }

        // ----- Measuring -----

        private static ModelCatalog.Entry Measure(Spec spec, StringBuilder log)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(spec.Path);
            if (prefab == null)
            {
                Debug.LogWarning($"[ModelCatalogBuilder] {spec.Id}: no imported GameObject at {spec.Path}; the id is left out and falls back at run time");
                return null;
            }
            GameObject probe = Object.Instantiate(prefab);
            probe.hideFlags = HideFlags.HideAndDontSave;
            try
            {
                Transform root = probe.transform;
                root.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
                root.localScale = Vector3.one;
                var entry = new ModelCatalog.Entry { id = spec.Id, prefab = prefab, rigged = spec.Rigged };
                log.Append($"  {spec.Id}: prefab root local {Fmt(prefab.transform.localPosition)} {Fmt(prefab.transform.localEulerAngles)} {Fmt(prefab.transform.localScale)}");
                if (!spec.Rigged)
                {
                    if (!StaticBounds(probe, out Bounds b))
                    {
                        Debug.LogWarning($"[ModelCatalogBuilder] {spec.Id}: no renderer in {spec.Path}");
                        return null;
                    }
                    entry.nativeSize = b.size;
                    entry.boundsCenter = b.center;
                    entry.yawOffset = ModelMath.SnapYaw(spec.Yaw);
                    log.Append($", size {Fmt(b.size)}, centre {Fmt(b.center)}, yaw {entry.yawOffset}, renderers {probe.GetComponentsInChildren<Renderer>(true).Length}\n");
                    return entry;
                }
                return MeasureRigged(spec, prefab, probe, entry, log);
            }
            finally
            {
                Object.DestroyImmediate(probe);
            }
        }

        /// <summary>Union of the renderer bounds (the root is at the origin: world space is root space).</summary>
        private static bool StaticBounds(GameObject probe, out Bounds bounds)
        {
            bounds = default;
            bool any = false;
            foreach (Renderer r in probe.GetComponentsInChildren<Renderer>(true))
            {
                if (r is SkinnedMeshRenderer)
                {
                    continue;
                }
                if (!any)
                {
                    bounds = r.bounds;
                    any = true;
                }
                else
                {
                    bounds.Encapsulate(r.bounds);
                }
            }
            return any;
        }

        private static ModelCatalog.Entry MeasureRigged(Spec spec, GameObject prefab, GameObject probe, ModelCatalog.Entry entry, StringBuilder log)
        {
            SkinnedMeshRenderer skin = probe.GetComponentInChildren<SkinnedMeshRenderer>(true);
            Transform head = FindDeep(probe.transform, HeadBoneName);
            if (skin == null || skin.sharedMesh == null || head == null)
            {
                Debug.LogWarning($"[ModelCatalogBuilder] {spec.Id}: skinned mesh or bone '{HeadBoneName}' missing in {spec.Path}");
                return null;
            }
            int eyeSlot = -1;
            Material[] slots = skin.sharedMaterials;
            for (int i = 0; i < slots.Length; i++)
            {
                if (slots[i] != null && slots[i].name == EyeMaterialName)
                {
                    eyeSlot = i;
                }
            }
            if (eyeSlot < 0 || eyeSlot >= skin.sharedMesh.subMeshCount)
            {
                Debug.LogWarning($"[ModelCatalogBuilder] {spec.Id}: no '{EyeMaterialName}' material on the skinned mesh");
                return null;
            }

            // The rest pose, baked: every vertex where it is drawn.
            var baked = new Mesh();
            try
            {
                // With useScale, the baked vertices are in the renderer's local space, its scale included (the
                // Quaternius mesh node carries scale 100): its full local to world matrix brings them to root space.
                skin.BakeMesh(baked, true);
                Matrix4x4 toRoot = skin.transform.localToWorldMatrix;
                Vector3[] vertices = baked.vertices;
                var bounds = new Bounds(toRoot.MultiplyPoint3x4(vertices[0]), Vector3.zero);
                foreach (Vector3 v in vertices)
                {
                    bounds.Encapsulate(toRoot.MultiplyPoint3x4(v));
                }
                // The "Eyes" material is the near-black of the model: the man's shoes use it too. Only its vertices
                // in the head region (the top fifth of the body) are eyes.
                float headRegion = bounds.min.y + (1f - HeadRegion) * bounds.size.y;
                var eyeVertices = new HashSet<int>();
                foreach (int i in baked.GetIndices(eyeSlot))
                {
                    if (toRoot.MultiplyPoint3x4(vertices[i]).y >= headRegion)
                    {
                        eyeVertices.Add(i);
                    }
                }
                if (eyeVertices.Count == 0)
                {
                    Debug.LogWarning($"[ModelCatalogBuilder] {spec.Id}: no '{EyeMaterialName}' vertex in the head region");
                    return null;
                }
                Vector3 eyeSum = Vector3.zero;
                foreach (int i in eyeVertices)
                {
                    eyeSum += toRoot.MultiplyPoint3x4(vertices[i]);
                }
                Vector3 eyeRest = eyeSum / eyeVertices.Count;

                entry.nativeSize = bounds.size;
                entry.boundsCenter = bounds.center;
                entry.headBone = HeadBoneName;
                entry.eyeLocal = head.InverseTransformPoint(eyeRest);
                // Facing: the eyes stand ahead of the head bone.
                Vector3 ahead = YawMath.Planar(eyeRest - head.position);
                entry.yawOffset = ModelMath.YawOffsetFacing(ahead);

                // Eye height: mean over the Idle clip when it samples, else the rest pose.
                float restHeight = eyeRest.y;
                float idleHeight = IdleEyeHeight(spec.Path, probe, head, entry.eyeLocal, out string clipName);
                entry.eyeHeight = idleHeight > 0f ? idleHeight : restHeight;
                log.Append($", size {Fmt(bounds.size)}, centre {Fmt(bounds.center)}, head '{head.name}' lossy scale {Fmt(head.lossyScale)}, ")
                    .Append($"head y {F(head.position.y)}, eye {Fmt(eyeRest)} local {Fmt(entry.eyeLocal, "0.#####")} ({eyeVertices.Count} vertices), ")
                    .Append($"facing {Fmt(ahead)} so yaw {entry.yawOffset}, ")
                    .Append($"eye height rest {F(restHeight)} idle {F(idleHeight)} ({clipName ?? "no clip"}), bones {skin.bones.Length}, ")
                    .Append($"triangles {ModelKit.Triangles(skin.sharedMesh)}, slots {slots.Length}\n");
                return entry;
            }
            finally
            {
                Object.DestroyImmediate(baked);
            }
        }

        /// <summary>
        /// The mean eye height over the Idle clip (root space) with the head held in its bind-pose orientation, as
        /// InhabitantRig holds it (M3.1 N4: the glTF rest pose tilts the head by 3.5 to 4.8 deg), or 0 when there is
        /// no such clip.
        /// </summary>
        private static float IdleEyeHeight(string path, GameObject probe, Transform head, Vector3 eyeLocal, out string clipName)
        {
            clipName = null;
            AnimationClip idle = null;
            foreach (Object o in AssetDatabase.LoadAllAssetsAtPath(path))
            {
                if (o is AnimationClip clip && clip.name.EndsWith(IdleSuffix, System.StringComparison.Ordinal))
                {
                    idle = clip;
                }
            }
            if (idle == null || idle.length <= 0f)
            {
                return 0f;
            }
            clipName = idle.name;
            return ModelKit.IdleEyeHeight(probe, idle, head, eyeLocal, null, IdleSamples);
        }

        private static Transform FindDeep(Transform t, string name)
        {
            if (t.name == name)
            {
                return t;
            }
            for (int i = 0; i < t.childCount; i++)
            {
                Transform found = FindDeep(t.GetChild(i), name);
                if (found != null)
                {
                    return found;
                }
            }
            return null;
        }

        // ----- Idempotence -----

        private static bool SameEntries(List<ModelCatalog.Entry> a, List<ModelCatalog.Entry> b)
        {
            if (a == null || a.Count != b.Count)
            {
                return false;
            }
            for (int i = 0; i < a.Count; i++)
            {
                ModelCatalog.Entry x = a[i];
                ModelCatalog.Entry y = b[i];
                if (x == null || x.id != y.id || x.prefab != y.prefab || x.rigged != y.rigged || x.headBone != y.headBone
                    || !Near(x.nativeSize, y.nativeSize) || !Near(x.boundsCenter, y.boundsCenter) || !Near(x.eyeLocal, y.eyeLocal)
                    || Mathf.Abs(x.yawOffset - y.yawOffset) > 1e-4f || Mathf.Abs(x.eyeHeight - y.eyeHeight) > 1e-5f)
                {
                    return false;
                }
            }
            return true;
        }

        private static bool Near(Vector3 a, Vector3 b) => (a - b).sqrMagnitude < 1e-10f;

        private static string F(float v) => v.ToString("0.####", CultureInfo.InvariantCulture);

        private static string Fmt(Vector3 v, string f = "0.####")
        {
            CultureInfo c = CultureInfo.InvariantCulture;
            return $"({v.x.ToString(f, c)}, {v.y.ToString(f, c)}, {v.z.ToString(f, c)})";
        }
    }
}
