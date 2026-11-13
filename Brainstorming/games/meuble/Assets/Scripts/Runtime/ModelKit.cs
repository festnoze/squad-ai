using System;
using System.Collections.Generic;
using Meuble.Core;
using UnityEngine;
using UnityEngine.Rendering;
using Object = UnityEngine.Object;

namespace Meuble
{
    /// <summary>How a model is scaled into the gameplay box (docs/CONTRACT_M3.md 3).</summary>
    public enum ModelFit
    {
        /// <summary>Per axis scale so the model bounds fill the box exactly (bottom on y = 0, centered).</summary>
        Box,

        /// <summary>One scale from the height only, then centered.</summary>
        Uniform,
    }

    /// <summary>
    /// Instantiates catalog models as visuals (docs/CONTRACT_M3.md 3). A model is a visual only: it never
    /// carries a collider, and the caller keeps the procedural colliders.
    ///
    /// - Box fit (static models only): a per axis scale so the bounds fill the box, bottom on y = 0, centred.
    /// - Uniform fit: a rigged model is scaled by Tuning.EyeHeight / eyeHeight (its eyes at the routine's eye),
    ///   root kept at the parent origin; a static one by the box height, then centred.
    /// - The root takes the yaw offset of its entry; the layer of the parent is set on every child.
    /// - Every material slot is replaced by PrimitiveKit.Lit of the mapped colour (ModelMath.MapColor): glTFast's
    ///   own materials are never rendered.
    /// - Any failure returns null after exactly one warning, so the caller falls back to the procedural visual.
    /// </summary>
    public static class ModelKit
    {
        /// <summary>When true, Instantiate returns null: every level builds its procedural visuals (probe step 23).</summary>
        public static bool Disabled;

        /// <summary>The name of every model root starts with this, followed by the catalog id.</summary>
        public const string RootPrefix = "Model ";

        /// <summary>
        /// Smoothness of every model material. Wanted in Tuning as ModelSmoothness (integrator). The Lit cache is
        /// keyed by colour, so a colour already used by a procedural part keeps that part's smoothness.
        /// </summary>
        private const float Smoothness = Tuning.ModelSmoothness;

        /// <summary>A model flatter than this (rugs, the doormat) casts no shadow, like the M2 rugs.</summary>
        private const float FlatHeight = 0.05f;

        /// <summary>glTFast's URP and built-in materials store the gamma converted base colour under this name.</summary>
        private const string GltfBaseColor = "baseColorFactor";

        /// <summary>Warnings logged since the domain loaded (one per failed instantiate).</summary>
        public static int WarningCount { get; private set; }

        public static GameObject Instantiate(string id, Transform parent, Vector3 boxSize, ModelFit fit)
        {
            return Instantiate(id, parent, boxSize, fit, default);
        }

        public static GameObject Instantiate(string id, Transform parent, Vector3 boxSize, ModelFit fit, ModelPaint paint)
        {
            if (Disabled)
            {
                return null;
            }
            GameObject instance = null;
            try
            {
                ModelCatalog catalog = ModelCatalog.Load();
                if (catalog == null)
                {
                    return Fail(id, $"no catalog at Resources/{ModelCatalog.ResourcePath}");
                }
                ModelCatalog.Entry entry = catalog.Find(id);
                if (entry == null)
                {
                    return Fail(id, "unknown id");
                }
                if (entry.prefab == null)
                {
                    return Fail(id, "the entry has no prefab");
                }
                if (!ModelMath.IsValidSize(entry.nativeSize))
                {
                    return Fail(id, $"invalid native size {entry.nativeSize}");
                }
                if (!ModelMath.IsRightAngle(entry.yawOffset))
                {
                    return Fail(id, $"yaw offset {entry.yawOffset} is not a multiple of 90");
                }
                if (entry.rigged && fit == ModelFit.Box)
                {
                    return Fail(id, "a rigged model is never box fitted (a non uniform scale shears the bones)");
                }
                if (entry.rigged && !(entry.eyeHeight > 1e-4f))
                {
                    return Fail(id, $"invalid eye height {entry.eyeHeight}");
                }
                if (!entry.rigged && !ModelMath.IsValidSize(boxSize))
                {
                    return Fail(id, $"invalid box {boxSize}");
                }

                float yaw = ModelMath.SnapYaw(entry.yawOffset); // MUTATION:FACING
                Vector3 scale;
                Vector3 position;
                if (fit == ModelFit.Box)
                {
                    scale = ModelMath.BoxScale(entry.nativeSize, boxSize, yaw);
                    position = ModelMath.FitPosition(entry.boundsCenter, entry.nativeSize, scale, yaw);
                }
                else if (entry.rigged)
                {
                    // The root stays on the parent origin (the feet): only the eyes must sit at the routine's eye.
                    scale = Vector3.one * ModelMath.UniformScale(entry.eyeHeight, Tuning.EyeHeight);
                    position = Vector3.zero;
                }
                else
                {
                    scale = Vector3.one * ModelMath.UniformScale(entry.nativeSize.y, boxSize.y);
                    position = ModelMath.FitPosition(entry.boundsCenter, entry.nativeSize, scale, yaw);
                }

                instance = Object.Instantiate(entry.prefab, parent, false);
                instance.name = RootPrefix + id;
                Transform t = instance.transform;
                t.localPosition = position;
                t.localRotation = Quaternion.Euler(0f, yaw, 0f);
                t.localScale = scale;
                SetLayer(t, parent != null ? parent.gameObject.layer : 0);
                string problem = Paint(instance, paint, fit == ModelFit.Box && boxSize.y < FlatHeight);
                if (problem != null)
                {
                    Discard(instance);
                    return Fail(id, problem);
                }
                return instance;
            }
            catch (Exception e)
            {
                Discard(instance);
                return Fail(id, e.GetType().Name + ": " + e.Message);
            }
        }

        /// <summary>True for the root GameObject of a model visual.</summary>
        public static bool IsModelRoot(Transform t)
        {
            return t != null && t.name.StartsWith(RootPrefix, StringComparison.Ordinal);
        }

        /// <summary>The model root that <paramref name="t"/> belongs to, or null for a procedural object.</summary>
        public static Transform ModelRootOf(Transform t)
        {
            for (Transform c = t; c != null; c = c.parent)
            {
                if (IsModelRoot(c))
                {
                    return c;
                }
            }
            return null;
        }

        /// <summary>Every model root under <paramref name="root"/>, inactive ones included.</summary>
        public static List<Transform> ModelRootsUnder(Transform root)
        {
            var found = new List<Transform>();
            if (root == null)
            {
                return found;
            }
            foreach (Transform t in root.GetComponentsInChildren<Transform>(true))
            {
                if (IsModelRoot(t) && (t.parent == null || ModelRootOf(t.parent) == null))
                {
                    found.Add(t);
                }
            }
            return found;
        }

        /// <summary>The colour glTFast stored for a material (sRGB), or null when it has none.</summary>
        public static Color? SourceColor(Material material)
        {
            if (material == null)
            {
                return null;
            }
            if (material.HasProperty(GltfBaseColor))
            {
                Vector4 v = material.GetVector(GltfBaseColor);
                return new Color(v.x, v.y, v.z, 1f);
            }
            if (material.HasProperty("_BaseColor"))
            {
                return material.GetColor("_BaseColor");
            }
            if (material.HasProperty("_Color"))
            {
                return material.GetColor("_Color");
            }
            return null;
        }

        /// <summary>The mesh a renderer draws: a MeshFilter's or a SkinnedMeshRenderer's.</summary>
        public static Mesh MeshOf(Renderer renderer)
        {
            if (renderer is SkinnedMeshRenderer skinned)
            {
                return skinned.sharedMesh;
            }
            MeshFilter filter = renderer != null ? renderer.GetComponent<MeshFilter>() : null;
            return filter != null ? filter.sharedMesh : null;
        }

        /// <summary>
        /// The world rotation of a bone in the skin's bind pose (from the bindposes), the orientation InhabitantRig
        /// holds the head in: LookRotation of the bind matrix's z and y axes. False when the bone is not skinned.
        /// </summary>
        public static bool TryBindRotation(SkinnedMeshRenderer skin, Transform bone, out Quaternion rotation)
        {
            rotation = Quaternion.identity;
            if (skin == null || skin.sharedMesh == null || bone == null)
            {
                return false;
            }
            int index = Array.IndexOf(skin.bones, bone);
            Matrix4x4[] bindposes = skin.sharedMesh.bindposes;
            if (index < 0 || index >= bindposes.Length)
            {
                return false;
            }
            Matrix4x4 world = skin.transform.localToWorldMatrix * bindposes[index].inverse;
            Vector3 forward = world.GetColumn(2);
            Vector3 up = world.GetColumn(1);
            if (forward.sqrMagnitude < 1e-12f || up.sqrMagnitude < 1e-12f)
            {
                return false;
            }
            rotation = Quaternion.LookRotation(forward, up);
            return true;
        }

        /// <summary>
        /// The mean height of the eyes (<paramref name="eyeLocal"/> in head space) above <paramref name="frame"/>,
        /// sampled over <paramref name="idle"/> with the head held in its bind orientation, as InhabitantRig drives a
        /// dwelling inhabitant (docs/CONTRACT_M3.md 5). Leaves the model in the last sampled pose.
        /// </summary>
        public static float IdleEyeHeight(GameObject model, AnimationClip idle, Transform head, Vector3 eyeLocal, Transform frame, int samples)
        {
            SkinnedMeshRenderer skin = model.GetComponentInChildren<SkinnedMeshRenderer>(true);
            bool bind = TryBindRotation(skin, head, out Quaternion bindRotation);
            float baseY = frame != null ? frame.position.y : 0f;
            float sum = 0f;
            samples = Mathf.Max(1, samples);
            for (int i = 0; i < samples; i++)
            {
                idle.SampleAnimation(model, idle.length * i / samples);
                if (bind)
                {
                    head.rotation = bindRotation;
                }
                sum += head.TransformPoint(eyeLocal).y - baseY;
            }
            return sum / samples;
        }

        /// <summary>Triangles of a mesh, every submesh counted.</summary>
        public static long Triangles(Mesh mesh)
        {
            long total = 0;
            if (mesh == null)
            {
                return total;
            }
            for (int sub = 0; sub < mesh.subMeshCount; sub++)
            {
                total += mesh.GetIndexCount(sub) / 3;
            }
            return total;
        }

        // ----- Internals -----

        private static GameObject Fail(string id, string why)
        {
            WarningCount++;
            Debug.LogWarning($"[ModelKit] model '{id}' falls back to the procedural visual: {why}");
            return null;
        }

        private static void Discard(GameObject instance)
        {
            if (instance != null)
            {
                Object.DestroyImmediate(instance);
            }
        }

        private static void SetLayer(Transform t, int layer)
        {
            t.gameObject.layer = layer;
            for (int i = 0; i < t.childCount; i++)
            {
                SetLayer(t.GetChild(i), layer);
            }
        }

        /// <summary>Replaces every material slot by PrimitiveKit.Lit. Returns null, or what went wrong.</summary>
        private static string Paint(GameObject instance, ModelPaint paint, bool flat)
        {
            Renderer[] renderers = instance.GetComponentsInChildren<Renderer>(true);
            if (renderers.Length == 0)
            {
                return "the prefab has no renderer";
            }
            // Pass 1: the source materials, their colours and their triangles (to find the main material).
            var sources = new List<Material>();
            var colors = new List<Color>();
            var triangles = new List<long>();
            foreach (Renderer r in renderers)
            {
                Mesh mesh = MeshOf(r);
                if (mesh == null)
                {
                    return $"renderer {r.name} has no mesh";
                }
                Material[] slots = r.sharedMaterials;
                for (int i = 0; i < slots.Length; i++)
                {
                    Color? c = SourceColor(slots[i]);
                    if (c == null)
                    {
                        return $"renderer {r.name} slot {i} has no base colour";
                    }
                    int k = sources.IndexOf(slots[i]);
                    if (k < 0)
                    {
                        sources.Add(slots[i]);
                        colors.Add(c.Value);
                        triangles.Add(0);
                        k = sources.Count - 1;
                    }
                    if (i < mesh.subMeshCount)
                    {
                        triangles[k] += mesh.GetIndexCount(i) / 3;
                    }
                }
            }
            int main = ModelMath.IndexOfMax(triangles);
            float redReference = ModelMath.RedReference(colors);
            var mapped = new Material[sources.Count];
            for (int k = 0; k < sources.Count; k++)
            {
                mapped[k] = PrimitiveKit.Lit(ModelMath.MapColor(colors[k], k == main, redReference, paint), Smoothness);
            }
            // Pass 2: swap the slots.
            foreach (Renderer r in renderers)
            {
                Material[] slots = r.sharedMaterials;
                var replaced = new Material[slots.Length];
                for (int i = 0; i < slots.Length; i++)
                {
                    replaced[i] = mapped[sources.IndexOf(slots[i])];
                }
                r.sharedMaterials = replaced;
                r.shadowCastingMode = flat ? ShadowCastingMode.Off : ShadowCastingMode.On;
                r.receiveShadows = true;
            }
            return null;
        }
    }
}
