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
    /// - Uniform fit: a rigged model is scaled by its target eye height / eyeHeight (its eyes at the routine's eye: the
    ///   humans' Tuning.EyeHeight, M5 the dog's Tuning.DogEyeHeight, <see cref="RiggedScale"/>), root kept at the parent
    ///   origin; a static one by the box height, then centred.
    /// - The root takes the yaw offset of its entry; the layer of the parent is set on every child.
    /// - Every material slot is replaced by PrimitiveKit.Lit of the mapped colour (ModelMath.MapColor): glTFast's
    ///   own materials are never rendered.
    /// - M5 characters (an entry of kind human or pet, CONTRACT_M5 16.11): every slot maps onto the character palette
    ///   (<see cref="Tuning.CharacterPalette"/>, 8 shared colours, <see cref="CharacterColor"/>) except the clothes, which
    ///   take the personality's tint (<see cref="ModelPaint.Main"/> at instantiate time, or <see cref="TintClothes"/> later),
    ///   so 3 humans and a dog add at most 12 materials. Without a tint the clothes keep their M4 colour: a default
    ///   inhabitant of levels 1 to 7 looks exactly as before.
    /// - M4.2: each slot then shows the detail of its source material (<see cref="SurfaceOf"/>) through
    ///   PrimitiveKit.Detail; a mesh without UVs gets them in place first (<see cref="EnsureUvs"/>).
    /// - Any failure returns null after exactly one warning, so the caller falls back to the procedural visual.
    /// - M5B (CONTRACT_M5 17: a draw call is a material slot): <see cref="MergeSlots"/> merges the submeshes of a tinted
    ///   character that draw the same material with the same detail into one (a shared mesh per model and grouping), behind
    ///   <see cref="MergeCharacterSlots"/>; <see cref="SourceSlots"/> still names every source material of a merged slot.
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
                    scale = Vector3.one * RiggedScale(entry);
                    position = Vector3.zero;
                }
                else
                {
                    scale = Vector3.one * ModelMath.UniformScale(entry.nativeSize.y, boxSize.y);
                    position = ModelMath.FitPosition(entry.boundsCenter, entry.nativeSize, scale, yaw);
                }

                // M4.2: the meshes are completed before the first instance draws them (a skinned mesh without UVs). M5: a
                // human's own UVs (the suit's atlas) are replaced too, so every human's clothes show the detail in metres.
                EnsureUvs(entry.prefab, entry.IsHuman);
                instance = Object.Instantiate(entry.prefab, parent, false);
                instance.name = RootPrefix + id;
                Transform t = instance.transform;
                t.localPosition = position;
                t.localRotation = Quaternion.Euler(0f, yaw, 0f);
                t.localScale = scale;
                SetLayer(t, parent != null ? parent.gameObject.layer : 0);
                string problem = Paint(instance, paint, fit == ModelFit.Box && boxSize.y < FlatHeight, entry);
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

        /// <summary>
        /// The one scale of a rigged model's Uniform fit: its eyes (the catalog's mean over Idle, native units) at the entry's
        /// target eye height (<see cref="ModelCatalog.Entry.TargetEye"/>: 1.6 m for a human, 0.35 m for the dog).
        /// </summary>
        public static float RiggedScale(ModelCatalog.Entry entry)
        {
            return ModelMath.UniformScale(entry.eyeHeight, entry.TargetEye); // MUTATION:PET_EYE_TARGET
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

        // ----- M5 characters (docs/CONTRACT_M5.md 3 and 16.11) -----

        /// <summary>What a character's source material is, from its name in the GLB: it picks its palette colours.</summary>
        public enum CharacterPart
        {
            /// <summary>The clothes (a pet: its main fur): the personality's tint.</summary>
            Clothes,
            Skin,
            Hair,
            /// <summary>Trousers, socks and shoes.</summary>
            Legs,
            /// <summary>White details: the suit's shirt and tie, the dog's eye whites and light fur.</summary>
            Light,
            /// <summary>Eyes and black details: always the near-black.</summary>
            Dark,
            /// <summary>Any other name: the nearest of the 8 shared colours.</summary>
            Other,
        }

        // Indices into Tuning.CharacterPalette: near-black, mid skin, light skin, denim, blond, grey, white, plum.
        private static readonly int[] SkinColours = { 1, 2 };
        private static readonly int[] HairColours = { 0, 4, 5, 7 };
        private static readonly int[] LegColours = { 0, 3, 5, 6 };
        private static readonly int[] LightColours = { 6, 5 };
        private static readonly int[] DarkColours = { 0 };
        private static readonly int[] AnyColour = { 0, 1, 2, 3, 4, 5, 6, 7 };

        /// <summary>The part of a character's source material (its name in the GLB, case ignored).</summary>
        public static CharacterPart PartOf(string sourceMaterial, bool pet)
        {
            switch ((sourceMaterial ?? "").Trim().ToLowerInvariant())
            {
                case "shirt":
                case "shirt2":
                case "jacket":
                case "lightjacket":
                case "dress":
                    return CharacterPart.Clothes;
                case "main":
                    return pet ? CharacterPart.Clothes : CharacterPart.Other;
                case "skin":
                    return CharacterPart.Skin;
                case "hair":
                case "hair2":
                case "hairbase":
                case "eyebrows":
                    return CharacterPart.Hair;
                case "pants":
                case "socks":
                case "shoes":
                    return CharacterPart.Legs;
                case "details":
                case "tietexture":
                case "eyes_white":
                case "main_light":
                    return CharacterPart.Light;
                case "eyes":
                case "eyes_black":
                case "eyes_pupil":
                case "black":
                    return CharacterPart.Dark;
                default:
                    return CharacterPart.Other;
            }
        }

        /// <summary>
        /// The colour of a character's slot (CONTRACT_M5 16.11), sRGB:
        /// <list type="number">
        /// <item>the clothes take <paramref name="tint"/> exactly; without a tint, their M4 colour (ModelMath.MapColor);</item>
        /// <item>any near-black source takes the near-black (palette 0, as M3.1 merged them);</item>
        /// <item>anything else the nearest (sRGB distance) of the palette colours its part allows: skin tones for the skin,
        /// hair colours for hair, and so on, so a face never takes a hair colour.</item>
        /// </list>
        /// Every result but the tint is one of <see cref="Tuning.CharacterPalette"/>; none is red.
        /// </summary>
        public static Color CharacterColor(string sourceMaterial, Color source, bool pet, Color? tint, float redReference = 0f)
        {
            CharacterPart part = PartOf(sourceMaterial, pet);
            if (part == CharacterPart.Clothes)
            {
                return tint.HasValue ? ModelMath.Opaque(tint.Value) : ModelMath.MapColor(source, false, redReference, default);
            }
            Color[] palette = Tuning.CharacterPalette;
            if (ModelMath.IsNearBlack(source))
            {
                return palette[0];
            }
            int[] allowed;
            switch (part)
            {
                case CharacterPart.Skin:
                    allowed = SkinColours;
                    break;
                case CharacterPart.Hair:
                    allowed = HairColours;
                    break;
                case CharacterPart.Legs:
                    allowed = LegColours;
                    break;
                case CharacterPart.Light:
                    allowed = LightColours;
                    break;
                case CharacterPart.Dark:
                    allowed = DarkColours;
                    break;
                default:
                    allowed = AnyColour;
                    break;
            }
            int best = allowed[0];
            float bestDistance = float.MaxValue;
            foreach (int i in allowed)
            {
                Color c = palette[i];
                float d = (c.r - source.r) * (c.r - source.r) + (c.g - source.g) * (c.g - source.g) + (c.b - source.b) * (c.b - source.b);
                if (d < bestDistance)
                {
                    bestDistance = d;
                    best = i;
                }
            }
            return palette[best];
        }

        /// <summary>
        /// Every material slot of a model instance with the name of its source material in the catalog prefab (renderers
        /// matched by their path under the root; a renderer the prefab lacks, such as the rig's brows, is skipped).
        /// </summary>
        public static List<(Renderer renderer, int slot, string source)> SourceSlots(GameObject instance, ModelCatalog.Entry entry)
        {
            var found = new List<(Renderer, int, string)>();
            if (instance == null || entry == null || entry.prefab == null)
            {
                return found;
            }
            Dictionary<string, Renderer> sources = PrefabRenderers(entry);
            foreach (Renderer r in instance.GetComponentsInChildren<Renderer>(true))
            {
                if (!sources.TryGetValue(PathUnder(r.transform, instance.transform), out Renderer original))
                {
                    continue;
                }
                Material[] names = original.sharedMaterials;
                // M5B: a merged slot names every source material it draws.
                Mesh drawnMesh = MeshOf(r);
                if (drawnMesh != null && Merged.TryGetValue(drawnMesh, out MergedMesh merged))
                {
                    int count = Mathf.Min(merged.Groups.Length, r.sharedMaterials.Length);
                    for (int j = 0; j < count; j++)
                    {
                        foreach (int o in merged.Groups[j])
                        {
                            if (o < names.Length)
                            {
                                found.Add((r, j, names[o] != null ? names[o].name : string.Empty));
                            }
                        }
                    }
                    continue;
                }
                int slots = Mathf.Min(names.Length, r.sharedMaterials.Length);
                for (int i = 0; i < slots; i++)
                {
                    found.Add((r, i, names[i] != null ? names[i].name : string.Empty));
                }
            }
            return found;
        }

        /// <summary>
        /// M5: the clothes slots of a character instance (a pet: its main fur) take <paramref name="tint"/>, a shared Lit
        /// material; the detail of each slot (its property block) is kept. Returns the number of clothes slots (0 for a
        /// model that is not a character). Idempotent.
        /// </summary>
        public static int TintClothes(GameObject instance, ModelCatalog.Entry entry, Color tint)
        {
            if (entry == null || !(entry.IsHuman || entry.IsPet))
            {
                return 0;
            }
            Material lit = PrimitiveKit.Lit(ModelMath.Opaque(tint), Smoothness);
            int count = 0;
            var changed = new Dictionary<Renderer, Material[]>();
            foreach ((Renderer r, int slot, string source) in SourceSlots(instance, entry))
            {
                if (PartOf(source, entry.IsPet) != CharacterPart.Clothes)
                {
                    continue;
                }
                count++;
                if (!changed.TryGetValue(r, out Material[] slots))
                {
                    slots = r.sharedMaterials;
                    changed[r] = slots;
                }
                slots[slot] = lit;
            }
            foreach (KeyValuePair<Renderer, Material[]> pair in changed)
            {
                pair.Key.sharedMaterials = pair.Value;
            }
            return count;
        }

        /// <summary>The catalog prefab's renderers by their path under its root.</summary>
        private static Dictionary<string, Renderer> PrefabRenderers(ModelCatalog.Entry entry)
        {
            var sources = new Dictionary<string, Renderer>();
            foreach (Renderer r in entry.prefab.GetComponentsInChildren<Renderer>(true))
            {
                sources[PathUnder(r.transform, entry.prefab.transform)] = r;
            }
            return sources;
        }

        // ----- M5B: merged character slots (CONTRACT_M5 16.11 and 17) -----

        /// <summary>
        /// M5B: when true, <see cref="MergeSlots"/> merges a tinted character's slots (Inhabitant applies it after the tint).
        /// Its default is <see cref="Tuning.CharacterSlotMerge"/>; tests may switch it.
        /// </summary>
        public static bool MergeCharacterSlots = Tuning.CharacterSlotMerge;

        /// <summary>A merged mesh: the source mesh it was cut from and, per merged slot, the source slots it draws.</summary>
        private sealed class MergedMesh
        {
            public Mesh Source;
            public int[][] Groups;
        }

        private static readonly Dictionary<Mesh, MergedMesh> Merged = new Dictionary<Mesh, MergedMesh>();
        private static readonly Dictionary<string, Mesh> MergedCache = new Dictionary<string, Mesh>();

        /// <summary>M5B: true when <paramref name="mesh"/> is a merged character mesh.</summary>
        public static bool IsMerged(Mesh mesh) => mesh != null && Merged.ContainsKey(mesh);

        /// <summary>M5B: the catalog mesh a merged mesh was cut from (any other mesh: itself).</summary>
        public static Mesh SourceMeshOf(Mesh mesh) => mesh != null && Merged.TryGetValue(mesh, out MergedMesh m) ? m.Source : mesh;

        /// <summary>M5B: the source slots each slot of <paramref name="mesh"/> draws (a plain mesh: one each).</summary>
        public static int[][] SlotGroups(Mesh mesh)
        {
            if (mesh != null && Merged.TryGetValue(mesh, out MergedMesh m))
            {
                return m.Groups;
            }
            int count = mesh != null ? mesh.subMeshCount : 0;
            var groups = new int[count][];
            for (int i = 0; i < count; i++)
            {
                groups[i] = new[] { i };
            }
            return groups;
        }

        /// <summary>
        /// M5B (CONTRACT_M5 17: a draw call is a material slot): the slots of a character instance (a human or a pet) that
        /// draw the same material with the same detail (<see cref="SurfaceOf"/>) become one slot, drawn from one submesh that
        /// holds all their triangles: it renders exactly as before, in fewer draw calls. Clothes never share a slot with
        /// anything else, so a later <see cref="TintClothes"/> still tints the clothes only. The merged mesh is a copy of the
        /// catalog mesh (its UVs, bones and bind poses included), made once per model and grouping and shared by every
        /// instance. Idempotent; nothing happens unless <see cref="MergeCharacterSlots"/>. Returns the slots saved.
        /// </summary>
        public static int MergeSlots(GameObject instance, ModelCatalog.Entry entry)
        {
            if (!MergeCharacterSlots || instance == null || entry == null || entry.prefab == null || !(entry.IsHuman || entry.IsPet))
            {
                return 0;
            }
            int saved = 0;
            Dictionary<string, Renderer> sources = PrefabRenderers(entry);
            foreach (Renderer r in instance.GetComponentsInChildren<Renderer>(true))
            {
                if (!sources.TryGetValue(PathUnder(r.transform, instance.transform), out Renderer original))
                {
                    continue;
                }
                Mesh mesh = MeshOf(r);
                Mesh source = SourceMeshOf(mesh);
                int[][] current = SlotGroups(mesh);
                Material[] slots = r.sharedMaterials;
                Material[] names = original.sharedMaterials;
                if (source == null || !source.isReadable || slots.Length != current.Length || names.Length != source.subMeshCount)
                {
                    continue;
                }
                // Each source slot: the material it draws now, its detail, and whether it is clothes.
                int count = source.subMeshCount;
                var drawn = new Material[count];
                var surfaces = new Surface[count];
                var clothes = new bool[count];
                for (int j = 0; j < current.Length; j++)
                {
                    foreach (int o in current[j])
                    {
                        drawn[o] = slots[j];
                        string name = names[o] != null ? names[o].name : string.Empty;
                        surfaces[o] = SurfaceOf(name, false);
                        clothes[o] = PartOf(name, entry.IsPet) == CharacterPart.Clothes;
                    }
                }
                var groups = new List<List<int>>();
                for (int o = 0; o < count; o++)
                {
                    int g = groups.FindIndex(list => SameSlot(list[0], o, drawn, surfaces, clothes));
                    if (g < 0)
                    {
                        groups.Add(new List<int> { o });
                    }
                    else
                    {
                        groups[g].Add(o);
                    }
                }
                if (groups.Count >= slots.Length)
                {
                    continue;
                }
                int[][] grouping = groups.ConvertAll(list => list.ToArray()).ToArray();
                Mesh merged = MergedMeshFor(source, grouping);
                var materials = new Material[grouping.Length];
                var details = new Surface[grouping.Length];
                for (int j = 0; j < grouping.Length; j++)
                {
                    materials[j] = drawn[grouping[j][0]];
                    details[j] = surfaces[grouping[j][0]];
                }
                // The old slots' detail blocks go; each merged slot gets its own detail on the merged submesh.
                var empty = new MaterialPropertyBlock();
                for (int i = 0; i < slots.Length; i++)
                {
                    r.SetPropertyBlock(empty, i);
                }
                if (r is SkinnedMeshRenderer skinned)
                {
                    skinned.sharedMesh = merged;
                }
                else
                {
                    r.GetComponent<MeshFilter>().sharedMesh = merged;
                }
                r.sharedMaterials = materials;
                for (int j = 0; j < grouping.Length; j++)
                {
                    PrimitiveKit.Detail(r, j, details[j]);
                }
                saved += slots.Length - grouping.Length;
            }
            return saved;
        }

        /// <summary>Two source slots share a merged slot: the same material, the same detail, and clothes only with clothes.</summary>
        private static bool SameSlot(int a, int b, Material[] drawn, Surface[] surfaces, bool[] clothes)
        {
            return drawn[a] == drawn[b] && surfaces[a] == surfaces[b] && clothes[a] == clothes[b]; // MUTATION:SLOT_MERGE_KEY
        }

        /// <summary>The merged copy of <paramref name="source"/> for <paramref name="grouping"/>, made once and shared.</summary>
        private static Mesh MergedMeshFor(Mesh source, int[][] grouping)
        {
            var key = new System.Text.StringBuilder();
            key.Append(source.GetInstanceID()).Append(':');
            foreach (int[] g in grouping)
            {
                key.Append(string.Join(",", g)).Append('|');
            }
            string k = key.ToString();
            if (MergedCache.TryGetValue(k, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Mesh merged = Object.Instantiate(source);
            merged.name = source.name + " (merged)";
            merged.hideFlags = HideFlags.DontUnloadUnusedAsset;
            merged.subMeshCount = grouping.Length;
            var indices = new List<int>();
            for (int j = 0; j < grouping.Length; j++)
            {
                indices.Clear();
                foreach (int o in grouping[j])
                {
                    indices.AddRange(source.GetIndices(o));
                }
                merged.SetIndices(indices, MeshTopology.Triangles, j, false);
            }
            merged.bounds = source.bounds;
            MergedCache[k] = merged;
            Merged[merged] = new MergedMesh { Source = source, Groups = grouping };
            return merged;
        }

        /// <summary>Material slots (draw calls) of the enabled renderers under <paramref name="root"/>.</summary>
        public static int SlotsUnder(Transform root)
        {
            int slots = 0;
            if (root == null)
            {
                return slots;
            }
            foreach (Renderer r in root.GetComponentsInChildren<Renderer>(false))
            {
                if (r.enabled)
                {
                    slots += r.sharedMaterials.Length;
                }
            }
            return slots;
        }

        private static string PathUnder(Transform t, Transform root)
        {
            var parts = new List<string>();
            for (Transform c = t; c != null && c != root; c = c.parent)
            {
                parts.Add(c.name);
            }
            parts.Reverse();
            return string.Join("/", parts);
        }

        // ----- M4.2 textures -----

        /// <summary>
        /// The surface a source material shows (by its name in the GLB, case ignored). Kenney: wood is wood, carpet is
        /// upholstery on a seat and carpet on a flat model (rug, doormat), the lamp shade is linen, metal stays plain.
        /// Quaternius: the clothes are linen; skin, eyes, hair and shoes stay plain (nothing harsh on a face). Any other
        /// name stays plain.
        /// </summary>
        public static Surface SurfaceOf(string sourceMaterial, bool flat)
        {
            switch ((sourceMaterial ?? "").Trim().ToLowerInvariant())
            {
                case "wood":
                    return Surface.Wood;
                case "carpet":
                case "carpetdarker":
                case "carpetblue":
                    return flat ? Surface.Carpet : Surface.Upholstery;
                case "lamp":
                    return Surface.Linen;
                case "shirt":
                case "pants":
                case "socks":
                // M5: the other clothes of the personalities' humans (CONTRACT_M5 3).
                case "shirt2":
                case "jacket":
                case "lightjacket":
                case "dress":
                    return Surface.Linen;
                default:
                    return Surface.Plain;
            }
        }

        private static readonly HashSet<Mesh> UvChecked = new HashSet<Mesh>();

        /// <summary>
        /// M4.2: every mesh of <paramref name="prefab"/> without UVs (the Quaternius humans have none; Kenney's carry a
        /// planar projection) gets UV0 IN PLACE: each vertex projected, in mesh units, on the plane its normal faces
        /// most (a box projection of the bind pose, so a texture never swims on a moving limb). In place, because the
        /// skinned mesh is shared by every inhabitant and by the catalog prefab (probe step 25 checks the instance draws
        /// the prefab's own mesh): one more vertex channel, no vertex, weight or index changes. A mesh that cannot be read
        /// logs one error (the built player's probe fails on it).
        /// </summary>
        public static void EnsureUvs(GameObject prefab)
        {
            EnsureUvs(prefab, false);
        }

        /// <summary>
        /// <see cref="EnsureUvs(GameObject)"/>, and with <paramref name="replace"/> (M5, the humans) a mesh that has UVs gets
        /// the same box projection over them: the man in a suit carries an atlas in UV0 (0 to 1 over the whole body), which
        /// would stretch one linen repeat over his jacket. No texture of the GLB is ever drawn, so nothing else reads UV0.
        /// </summary>
        public static void EnsureUvs(GameObject prefab, bool replace)
        {
            if (prefab == null)
            {
                return;
            }
            foreach (Renderer r in prefab.GetComponentsInChildren<Renderer>(true))
            {
                Mesh mesh = MeshOf(r);
                if (mesh == null || UvChecked.Contains(mesh))
                {
                    continue;
                }
                if (replace || !mesh.HasVertexAttribute(VertexAttribute.TexCoord0))
                {
                    if (!mesh.isReadable)
                    {
                        Debug.LogError($"[ModelKit] mesh {mesh.name} of {prefab.name} has no UVs and cannot be read: its detail cannot show");
                    }
                    else
                    {
                        mesh.SetUVs(0, BoxProjectedUvs(mesh.vertices, mesh.normals));
                    }
                }
                UvChecked.Add(mesh);
            }
        }

        /// <summary>Box projection: each vertex on the axis plane its normal faces most, in the vertices' own units.</summary>
        public static Vector2[] BoxProjectedUvs(Vector3[] vertices, Vector3[] normals)
        {
            var uv = new Vector2[vertices.Length];
            for (int i = 0; i < vertices.Length; i++)
            {
                Vector3 v = vertices[i];
                Vector3 n = i < normals.Length ? normals[i] : Vector3.up;
                float ax = Mathf.Abs(n.x);
                float ay = Mathf.Abs(n.y);
                float az = Mathf.Abs(n.z);
                if (ax >= ay && ax >= az)
                {
                    uv[i] = new Vector2(v.z, v.y);
                }
                else if (ay >= az)
                {
                    uv[i] = new Vector2(v.x, v.z);
                }
                else
                {
                    uv[i] = new Vector2(v.x, v.y);
                }
            }
            return uv;
        }

        /// <summary>
        /// Replaces every material slot by PrimitiveKit.Lit. Returns null, or what went wrong. M4.2: then each slot shows
        /// the detail of its source material (<see cref="SurfaceOf"/>), at the model's fitted scale.
        /// </summary>
        private static string Paint(GameObject instance, ModelPaint paint, bool flat, ModelCatalog.Entry entry)
        {
            bool character = entry != null && (entry.IsHuman || entry.IsPet);
            bool pet = entry != null && entry.IsPet;
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
                Color color = character
                    ? CharacterColor(sources[k].name, colors[k], pet, paint.Main, redReference)
                    : ModelMath.MapColor(colors[k], k == main, redReference, paint);
                mapped[k] = PrimitiveKit.Lit(color, Smoothness);
            }
            // Pass 2: swap the slots, then give each slot the detail of its source material.
            foreach (Renderer r in renderers)
            {
                Material[] slots = r.sharedMaterials;
                var replaced = new Material[slots.Length];
                var surfaces = new Surface[slots.Length];
                for (int i = 0; i < slots.Length; i++)
                {
                    replaced[i] = mapped[sources.IndexOf(slots[i])];
                    surfaces[i] = SurfaceOf(slots[i].name, flat);
                }
                r.sharedMaterials = replaced;
                r.shadowCastingMode = flat ? ShadowCastingMode.Off : ShadowCastingMode.On;
                r.receiveShadows = true;
                for (int i = 0; i < slots.Length; i++)
                {
                    PrimitiveKit.Detail(r, i, surfaces[i]);
                }
            }
            return null;
        }
    }
}
