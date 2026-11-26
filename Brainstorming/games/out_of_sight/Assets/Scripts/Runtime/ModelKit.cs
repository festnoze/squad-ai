using System;
using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using Object = UnityEngine.Object;

namespace OutOfSight
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
    /// - A character draws its catalog mesh with its own slots (CONTRACT_M5 19: no slot merge; every level holds its draw
    ///   call budget with the unmerged characters).
    /// - DOGBIG and LABRADOR: the dog's slots then show its painted maps (<see cref="ApplyPetFurMap"/>: the fur map on "Main",
    ///   the head atlas on "Tete profil et face"), whatever its tint and palette colours were.
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

        /// <summary>PRD 12.2 open question 28: a temporary "-finish metal" command line switch for the player's own
        /// finish (the two comparison shots the look agent takes); lacquer stays the default, read once.</summary>
        private static readonly Surface DebugMainFinish = Probe.ArgValue("-finish") == "metal" ? Surface.Metal : Surface.Lacquer;

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
                // Soft movers (2026-11-20): a body model (chair, stool, armchair, lamp) draws its rounded design instead,
                // before the paint, so the detail and the main colour are taken on the meshes it draws.
                if (fit == ModelFit.Box)
                {
                    SoftBodies.ApplyToModel(id, instance, parent, boxSize);
                }
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
        // DOGBIG: a pet's light fur (the Husky's mask and belly) and eye whites are the white: a classic two-tone coat with
        // its charcoal tint, never the mid grey its 0.58 source would pick.
        private static readonly int[] PetLightColours = { 6 };
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
                // LABRADOR: the final Labrador's head and neck seam (its head atlas). Without its maps the whole coat wears
                // the dog's tint, so the head never shows a palette colour against a tinted body.
                case "tete profil et face":
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
                    allowed = pet ? PetLightColours : LightColours;
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
            // DOGBIG: once the dog's fur texture exists, it wins over the tint (the picture carries the colours). LABRADOR: so
            // does its head atlas on the head slot.
            ApplyPetFurMap(instance, entry);
            return count;
        }

        // ----- DOGBIG: the dog's fur texture (docs/next/progress/DOGBIG.md); LABRADOR: and its head atlas -----

        /// <summary>
        /// LABRADOR (2026-11-25): the final Labrador's head material in its GLB: the head and the neck seam, painted in its head
        /// atlas (<see cref="PetHeadMap"/>). Its other material, "Main" (the body and the mouth's inside), shows the fur map.
        /// </summary>
        public const string PetHeadMaterial = "Tete profil et face";

        private static bool petFurLooked;
        private static Texture2D petFurMap;
        private static bool petHeadLooked;
        private static Texture2D petHeadMap;
        private static bool petHeadMissingReported;

        /// <summary>
        /// The dog's fur texture (Resources/<see cref="Tuning.DogFurTextureResource"/>, painted on the dog's UV0 atlas: the
        /// Labrador's body and mouth), or null while none is in the project (the dog then keeps its plain tint: no new material).
        /// </summary>
        public static Texture2D PetFurMap
        {
            get
            {
                if (!petFurLooked)
                {
                    petFurLooked = true;
                    petFurMap = LoadPetMap(Tuning.DogFurTextureResource);
                }
                return petFurMap;
            }
        }

        /// <summary>
        /// LABRADOR: the dog's head and neck atlas (Resources/<see cref="Tuning.DogHeadAtlasResource"/>, the eyes, nose and
        /// muzzle painted on the UV0 of its <see cref="PetHeadMaterial"/> slot), or null while none is in the project.
        /// </summary>
        public static Texture2D PetHeadMap
        {
            get
            {
                if (!petHeadLooked)
                {
                    petHeadLooked = true;
                    petHeadMap = LoadPetMap(Tuning.DogHeadAtlasResource);
                }
                return petHeadMap;
            }
        }

        private static Texture2D LoadPetMap(string resource)
        {
            var map = Resources.Load<Texture2D>(resource);
            if (map != null)
            {
                // DOGBIG v3: a sharper mip at game distance and anisotropic filtering at the camera's slant, so the strands
                // are not averaged into flat black (LABRADOR: and the painted eyes stay readable).
                map.mipMapBias = Tuning.DogFurMipBias;
                map.anisoLevel = Mathf.Max(map.anisoLevel, 4);
            }
            return map;
        }

        /// <summary>
        /// LABRADOR: the painted map a pet slot shows, by its source material's name: the head atlas for the Labrador's head
        /// (<see cref="PetHeadMaterial"/>, case ignored), the fur map for every other slot ("Main"; the old Husky's
        /// Main_Light, Black and Eyes_Black). Null without the fur map. A head slot without its atlas falls back to the fur map
        /// (logged once).
        /// </summary>
        public static Texture2D PetSlotMap(string sourceMaterial)
        {
            if (IsPetHead(sourceMaterial))
            {
                Texture2D head = PetHeadMap;
                if (head != null)
                {
                    return head;
                }
                if (!petHeadMissingReported)
                {
                    petHeadMissingReported = true;
                    Debug.LogWarning($"[ModelKit] no dog head atlas at Resources/{Tuning.DogHeadAtlasResource}: the dog's head shows the fur map");
                }
            }
            return PetFurMap;
        }

        /// <summary>LABRADOR: a pet's head slot (by its source material's name), shown with the head atlas.</summary>
        public static bool IsPetHead(string sourceMaterial)
        {
            return string.Equals((sourceMaterial ?? "").Trim(), PetHeadMaterial, StringComparison.OrdinalIgnoreCase);
        }

        /// <summary>
        /// DOGBIG: with a fur texture in the project (<see cref="PetFurMap"/>), every material slot of a pet instance takes the
        /// URP Lit material that shows its painted map (<see cref="PetSlotMap"/>: white base colour, the texture as base map, on
        /// the model's own UV0, one shared material per map), so the coat, face, nose and eyes come from the paintings, never
        /// from the tint or the palette. LABRADOR (2026-11-25): the final Labrador's "Main" slot shows the fur map (its body and
        /// the mouth's inside), its "Tete profil et face" slot the head atlas (its head and the neck seam). No property block is
        /// involved: the materials carry the maps, so a copy of the renderer's sharedMaterials (the title logo's baked frames)
        /// shows the same dog. Returns true when the maps were applied; without the fur map nothing changes. Called after the
        /// paint and after the tint, so the game, the catalog prefab's instances and the title logo's baked dog all pick it up.
        /// </summary>
        public static bool ApplyPetFurMap(GameObject instance, ModelCatalog.Entry entry)
        {
            if (instance == null || entry == null || !entry.IsPet)
            {
                return false;
            }
            if (PetFurMap == null)
            {
                return false;
            }
            var sources = new Dictionary<(Renderer, int), string>();
            foreach ((Renderer r, int slot, string source) in SourceSlots(instance, entry))
            {
                sources[(r, slot)] = source;
            }
            foreach (Renderer r in instance.GetComponentsInChildren<Renderer>(true))
            {
                Material[] slots = r.sharedMaterials;
                for (int i = 0; i < slots.Length; i++)
                {
                    sources.TryGetValue((r, i), out string source);
                    // DOGBIG v3: the old Husky's eye whites keep their palette white, so its eyes read at game distance (the
                    // Labrador has none: its eyes are painted in its head atlas).
                    if (IsPetEyeWhite(source))
                    {
                        continue;
                    }
                    slots[i] = PrimitiveKit.MapMaterial(PetSlotMap(source), Tuning.DogFurSmoothness);
                }
                r.sharedMaterials = slots;
            }
            return true;
        }

        /// <summary>DOGBIG v3: a pet's eye white slot (by its source material's name), kept out of the fur map.</summary>
        public static bool IsPetEyeWhite(string sourceMaterial)
        {
            return string.Equals((sourceMaterial ?? "").Trim(), "Eyes_White", StringComparison.OrdinalIgnoreCase);
        }

        /// <summary>
        /// DOGBIG: how far ahead of its root a fitted rigged model reaches, metres along its facing: the front of the catalog's
        /// rest pose bounds (native units, root space), turned by the entry's yaw as the instance is, at
        /// <see cref="RiggedScale"/>. For the dog, its snout (the Husky: 0.43 m; LABRADOR, the final Labrador: 0.429 m). 0 for a static model.
        /// </summary>
        public static float ForwardReach(ModelCatalog.Entry entry)
        {
            if (entry == null || !entry.rigged)
            {
                return 0f;
            }
            Quaternion turn = Quaternion.Euler(0f, ModelMath.SnapYaw(entry.yawOffset), 0f);
            Vector3 half = entry.nativeSize * 0.5f;
            float reach = float.MinValue;
            for (int c = 0; c < 8; c++)
            {
                var corner = new Vector3((c & 1) == 0 ? -half.x : half.x, (c & 2) == 0 ? -half.y : half.y, (c & 4) == 0 ? -half.z : half.z);
                reach = Mathf.Max(reach, (turn * (entry.boundsCenter + corner)).z);
            }
            return reach * RiggedScale(entry);
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
        /// upholstery on a seat and carpet on a flat model (rug, doormat: its own tiled skirt, unchanged by the M7 rug
        /// image of 2026-11-18, which adds the picture on its own separate quad instead, see BuildRug/BuildRugImage),
        /// the lamp shade is linen. Quaternius: the clothes are linen; skin, eyes, hair and shoes stay plain (nothing
        /// harsh on a face). Any other name stays plain.
        /// M6 (CONTRACT_M6 2.4): metal (the floor lamp's pole and foot) is now Surface.Metal instead of staying plain.
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
                // M8 (docs/m8/ROOMS_PLAN.md 3): the Kenney bed's sheets and pillows.
                case "carpetwhite":
                    return flat ? Surface.Carpet : Surface.Linen;
                case "lamp":
                    return Surface.Linen;
                case "metal":
                    return Surface.Metal;
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

        /// <summary>
        /// M8 (docs/m8/ROOMS_PLAN.md 3): the plain material a static model's slot takes by its source material's name, instead
        /// of its own quantised colour, or null: Kenney's "metalLight" (the fridge's enamel) is the room objects' white ceramic,
        /// its "glass", "metalDark" and "_defaultMat" (behind a fridge door, the fridge's back, the back of a drawer) the
        /// household's near-black ("metalDark" is a dark teal just above ModelMath.NearBlackMax, its own material otherwise). So
        /// the Kenney room models add no material of their own. No M3 to M6 model uses these names.
        /// </summary>
        public static Material PropSlotMaterial(string sourceMaterial)
        {
            switch ((sourceMaterial ?? "").Trim().ToLowerInvariant())
            {
                case "metallight":
                    return FurnitureKit.CeramicMaterial;
                case "glass":
                case "metaldark":
                case "_defaultmat":
                    return FurnitureKit.DarkMaterial;
                default:
                    return null;
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
        /// the detail of its source material (<see cref="SurfaceOf"/>), at the model's fitted scale. M6 (CONTRACT_M6 2.4,
        /// PRD 7.2): the main material of the player's own furniture (never a character, always red: <see cref="ModelPaint.Main"/>
        /// exactly, and only the player is red) shows the glossy lacquer finish instead; a Metal slot (the floor lamp's
        /// pole and foot) gets its own metal finish wherever it draws.
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
            // M6 (CONTRACT_M6 2.4, PRD 7.2): a character is never the player's own furniture; only the player passes a
            // literally red Main (a decoy's BuildDecoy steers its colour away from the player's before it gets here).
            bool lacquerMain = !character && paint.Main.HasValue && ModelMath.IsRed(paint.Main.Value);
            var mapped = new Material[sources.Count];
            var sourceSurfaces = new Surface[sources.Count];
            for (int k = 0; k < sources.Count; k++)
            {
                // M8: a static model's white enamel and dark glass take the room objects' own plain materials.
                Material fixedMaterial = character || (lacquerMain && k == main) ? null : PropSlotMaterial(sources[k].name);
                if (fixedMaterial != null)
                {
                    mapped[k] = fixedMaterial;
                    sourceSurfaces[k] = Surface.Plain;
                    continue;
                }
                Color color = character
                    ? CharacterColor(sources[k].name, colors[k], pet, paint.Main, redReference)
                    : ModelMath.MapColor(colors[k], k == main, redReference, paint);
                Surface surface = lacquerMain && k == main ? DebugMainFinish : SurfaceOf(sources[k].name, flat);
                sourceSurfaces[k] = surface;
                // M6 (CONTRACT_M6 2.4): Metal (the floor lamp's pole and foot) and Lacquer (the player's own main
                // slot) take their own fixed finish, cached apart from every other use of this colour at Smoothness
                // (characters' near-black eyes and hair, among others); everything else is unchanged.
                mapped[k] = TextureLibrary.FinishOf(surface, out _, out _)
                    ? PrimitiveKit.LitSurface(color, surface)
                    : PrimitiveKit.Lit(color, Smoothness);
            }
            // Pass 2: swap the slots, then give each slot the detail of its source material.
            foreach (Renderer r in renderers)
            {
                Material[] slots = r.sharedMaterials;
                var replaced = new Material[slots.Length];
                var surfaces = new Surface[slots.Length];
                for (int i = 0; i < slots.Length; i++)
                {
                    int k = sources.IndexOf(slots[i]);
                    replaced[i] = mapped[k];
                    surfaces[i] = sourceSurfaces[k];
                }
                r.sharedMaterials = replaced;
                r.shadowCastingMode = flat ? ShadowCastingMode.Off : ShadowCastingMode.On;
                r.receiveShadows = true;
                for (int i = 0; i < slots.Length; i++)
                {
                    // M7 real colours (CONTRACT_M7 5): a character keeps its palette materials (CharacterLook owns the
                    // clothes); every other model shows its surfaces' images in their own colours.
                    PrimitiveKit.Detail(r, i, surfaces[i], character);
                }
            }
            if (pet)
            {
                // DOGBIG: the dog's fur texture, once it exists, replaces its palette slots.
                ApplyPetFurMap(instance, entry);
            }
            return null;
        }
    }
}
