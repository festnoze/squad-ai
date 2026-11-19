using System;
using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>Fits the wrapped head and projects clothing artwork onto the rounded human model.
    /// The head is sewn onto the original neck. Material slots and animation bindings stay in place.
    /// A single projected mesh is shared by all instances of the same model.
    /// </summary>
    public static class CharacterLook
    {
        private static readonly int BaseMapId = Shader.PropertyToID("_BaseMap");
        private static readonly int BaseMapStId = Shader.PropertyToID("_BaseMap_ST");
        private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");

        private enum Chart { Original, Skin, ShirtFront, ShirtBack, PantsFront, PantsBack }
        private sealed class Projection
        {
            public Mesh Mesh;
            public readonly List<int> Skin = new List<int>();
            public readonly List<int> Clothes = new List<int>();
        }

        private static readonly Dictionary<Mesh, Projection> Projections = new Dictionary<Mesh, Projection>();
        private static readonly Dictionary<(Color32, bool), Texture2D> ClothesVariants = new Dictionary<(Color32, bool), Texture2D>();
        private static readonly HashSet<string> Reported = new HashSet<string>();
        private static Texture2D clothes;
        private static Color32[] clothesPixels;
        private static MaterialPropertyBlock block;

        public static bool IsFemale(ModelCatalog.Entry entry) =>
            entry?.id != null && entry.id.StartsWith(ModelCatalog.QuaterniusWoman, StringComparison.Ordinal);

        public static Texture2D ClothesAtlas
        {
            get
            {
                if (clothes == null)
                {
                    clothes = Resources.Load<Texture2D>(Tuning.ClothesAtlasResource);
                    if (clothes == null)
                    {
                        ReportOnce("clothes", $"[CharacterLook] missing Resources/{Tuning.ClothesAtlasResource}");
                    }
                }
                return clothes;
            }
        }

        public static bool IsCharacterTexture(Texture texture) =>
            texture != null && (CharacterHead.IsWrap(texture) || IsClothesTexture(texture));

        public static bool IsClothesTexture(Texture texture) =>
            texture != null && (texture == clothes || ClothesVariants.ContainsValue(texture as Texture2D));

        public static bool UsesProjection(Mesh source, Mesh displayed) =>
            (Projections.TryGetValue(source, out Projection full) && full.Mesh == displayed)
            || (PlainProjections.TryGetValue(source, out Projection plain) && plain.Mesh == displayed);

        public static void Apply(InhabitantRig rig)
        {
            if (rig == null || rig.IsPet || rig.Skin == null || rig.BrowPivot == null || rig.Entry == null || !rig.Entry.IsHuman)
            {
                return;
            }

            Mesh source = rig.Skin.sharedMesh;
            bool dressed = !TextureLibrary.Disabled && ClothesAtlas != null;
            // Keep a separate projection when the visual comparison probe disables detail textures.
            var variants = dressed ? Projections : PlainProjections;
            if (!variants.TryGetValue(source, out Projection look) || look.Mesh == null)
            {
                look = Project(rig, source, dressed);
                if (look == null)
                {
                    return;
                }
                variants[source] = look;
            }
            rig.Skin.sharedMesh = look.Mesh;
            // The head image in its real colours (a white base colour): no per-character skin or hair tint.
            Texture2D head = look.Skin.Count > 0 ? CharacterHead.Wrap(IsFemale(rig.Entry)) : null;
            if (head != null)
            {
                foreach (int slot in look.Skin)
                {
                    SetPrint(rig.Skin, slot, head, Color.white);
                }
            }
            ShowClothes(rig, look.Clothes, rig.Owner != null ? rig.Owner.Tint : null);
            if (head != null)
            {
                rig.SetPaintedHead();
            }
        }

        private static readonly Dictionary<Mesh, Projection> PlainProjections = new Dictionary<Mesh, Projection>();

        public static void Identify(InhabitantRig rig, Color? tint)
        {
            if (rig == null || rig.Skin == null || TextureLibrary.Disabled)
            {
                return;
            }
            foreach (Projection look in Projections.Values)
            {
                if (look.Mesh == rig.Skin.sharedMesh)
                {
                    ShowClothes(rig, look.Clothes, tint);
                    return;
                }
            }
        }

        private static void SetPrint(Renderer renderer, int slot, Texture2D texture, Color? colour)
        {
            block ??= new MaterialPropertyBlock();
            block.Clear();
            block.SetTexture(BaseMapId, texture);
            block.SetVector(BaseMapStId, new Vector4(1f, 1f, 0f, 0f));
            if (colour.HasValue)
            {
                block.SetColor(BaseColorId, colour.Value);
            }
            renderer.SetPropertyBlock(block, slot);
        }

        private static Projection Project(InhabitantRig rig, Mesh mesh, bool dressed)
        {
            int head = Array.IndexOf(rig.Skin.bones, rig.Head);
            Matrix4x4[] bindposes = mesh.bindposes;
            if (!mesh.isReadable || head < 0 || head >= bindposes.Length)
            {
                ReportOnce(rig.Entry.id, $"[CharacterLook] cannot project {rig.Entry.id}: missing mesh data or head bone");
                return null;
            }

            bool female = IsFemale(rig.Entry);
            Transform pivot = rig.BrowPivot;
            Matrix4x4 toFace = Matrix4x4.TRS(pivot.localPosition, pivot.localRotation, pivot.localScale).inverse * bindposes[head];
            Transform frame = rig.Model.transform.parent != null ? rig.Model.transform.parent : rig.Model.transform;
            Quaternion toBody = Quaternion.Inverse(Quaternion.Euler(0f, frame.eulerAngles.y, 0f));
            Matrix4x4 toWorld = rig.Skin.transform.localToWorldMatrix;
            Vector3[] vertices = mesh.vertices;
            Vector3[] normals = mesh.normals;
            Vector4[] tangents = mesh.tangents;
            Vector2[] uv = mesh.uv;
            BoneWeight[] weights = mesh.boneWeights;
            Transform[] bones = rig.Skin.bones;
            var body = new Vector3[vertices.Length];
            var face = new Vector3[vertices.Length];
            var headWeight = new float[vertices.Length];
            for (int i = 0; i < vertices.Length; i++)
            {
                body[i] = toBody * (toWorld.MultiplyPoint3x4(vertices[i]) - frame.position);
                face[i] = toFace.MultiplyPoint3x4(vertices[i]);
                BoneWeight w = weights[i];
                headWeight[i] = (w.boneIndex0 == head ? w.weight0 : 0f) + (w.boneIndex1 == head ? w.weight1 : 0f)
                    + (w.boneIndex2 == head ? w.weight2 : 0f) + (w.boneIndex3 == head ? w.weight3 : 0f);
            }

            Material[] sources = rig.Entry.prefab.GetComponentInChildren<SkinnedMeshRenderer>(true).sharedMaterials;
            var look = new Projection();
            Matrix4x4 fromFace = toFace.inverse;
            int neckBone = Array.FindIndex(bones, b => b != null && b.name == "Neck");
            var sourceTris = new int[mesh.subMeshCount][];
            float upperHalf = 0f, neck = float.MinValue, waist = float.MaxValue;
            float lowerHalf = 0f, hip = float.MinValue;
            int skinSlot = -1;
            for (int slot = 0; slot < sourceTris.Length; slot++)
            {
                string name = sources[slot].name;
                int[] indices = sourceTris[slot] = mesh.GetTriangles(slot);
                if (ModelKit.PartOf(name, false) == ModelKit.CharacterPart.Skin)
                {
                    skinSlot = slot;
                }
                foreach (int i in indices)
                {
                    if (IsUpper(name) && IsTrunk(DominantBone(weights, bones, i)))
                    {
                        upperHalf = Mathf.Max(upperHalf, Mathf.Abs(body[i].x));
                        neck = Mathf.Max(neck, body[i].y);
                        waist = Mathf.Min(waist, body[i].y);
                    }
                    if (IsLower(name))
                    {
                        lowerHalf = Mathf.Max(lowerHalf, Mathf.Abs(body[i].x));
                        hip = Mathf.Max(hip, body[i].y);
                    }
                }
            }
            List<int> collar = skinSlot >= 0 && CharacterHead.HasSource(female)
                ? CharacterHead.Collar(sourceTris[skinSlot], face, headWeight, female) : null;
            bool wrapHead = collar != null;
            if (!wrapHead)
            {
                ReportOnce(rig.Entry.id, $"[CharacterLook] {rig.Entry.id}: head wrap or neck boundary unavailable");
            }

            var remap = new Dictionary<(int, Chart), int>();
            // glTF stores many copies for the original flat normals. Weld only when all vertex data
            // agrees, so UV seams, hard edges and skinned joints keep the correct independent vertices.
            var welded = new Dictionary<(Vector3, Vector3, Vector4, Vector2, BoneWeight), int>();
            bool hasTangents = tangents.Length == vertices.Length;
            var positions = new List<Vector3>();
            var newNormals = new List<Vector3>();
            var newTangents = new List<Vector4>();
            var coords = new List<Vector2>();
            var skinning = new List<BoneWeight>();
            int[][] triangles = new int[sourceTris.Length][];
            for (int slot = 0; slot < sourceTris.Length; slot++)
            {
                string name = sources[slot].name;
                var part = ModelKit.PartOf(name, false);
                bool skin = part == ModelKit.CharacterPart.Skin;
                bool hair = part == ModelKit.CharacterPart.Hair;
                bool shirt = dressed && upperHalf > 0f && neck > waist && IsUpper(name);
                bool pants = dressed && lowerHalf > 0f && IsLower(name);
                if (skin && wrapHead) { look.Skin.Add(slot); }
                if (shirt || pants) { look.Clothes.Add(slot); }
                var indices = new List<int>(sourceTris[slot].Length);
                int[] input = sourceTris[slot];
                for (int k = 0; k < input.Length; k += 3)
                {
                    int a = input[k], b = input[k + 1], c = input[k + 2];
                    bool cutHead = wrapHead && ((skin && CharacterHead.CutsSkin(headWeight[a], headWeight[b], headWeight[c], female))
                        || hair || (name == "Eyes" && Mathf.Min(headWeight[a], Mathf.Min(headWeight[b], headWeight[c])) > 0.5f));
                    if (cutHead)
                    {
                        continue;
                    }
                    Chart chart = skin && wrapHead ? Chart.Skin : Chart.Original;
                    if (shirt || pants)
                    {
                        Vector3 normal = Vector3.Cross(vertices[b] - vertices[a], vertices[c] - vertices[a]);
                        Vector3 average = normals[a] + normals[b] + normals[c];
                        if (Vector3.Dot(normal, average) < 0f) { normal = -normal; }
                        bool front = (toBody * toWorld.MultiplyVector(normal)).z >= 0f;
                        chart = shirt ? (front ? Chart.ShirtFront : Chart.ShirtBack) : (front ? Chart.PantsFront : Chart.PantsBack);
                    }

                    for (int corner = k; corner < k + 3; corner++)
                    {
                        int v = input[corner];
                        if (!remap.TryGetValue((v, chart), out int copy))
                        {
                            Vector2 coord = ProjectUv(chart, uv[v], body[v], upperHalf, neck, waist, lowerHalf, hip);
                            Vector4 tangent = hasTangents ? tangents[v] : default;
                            var key = (vertices[v], normals[v], tangent, coord, weights[v]);
                            if (!welded.TryGetValue(key, out copy))
                            {
                                copy = positions.Count;
                                welded.Add(key, copy);
                                positions.Add(vertices[v]);
                                newNormals.Add(normals[v]);
                                if (hasTangents) { newTangents.Add(tangent); }
                                skinning.Add(weights[v]);
                                coords.Add(coord);
                            }
                            remap.Add((v, chart), copy);
                        }
                        indices.Add(copy);
                    }
                }
                if (wrapHead && slot == skinSlot)
                {
                    int Append(Vector3 point, Vector3 normal, Vector4 tangent, Vector2 coord, BoneWeight weight)
                    {
                        int index = positions.Count;
                        positions.Add(point);
                        newNormals.Add(normal);
                        if (hasTangents) { newTangents.Add(tangent); }
                        coords.Add(coord);
                        skinning.Add(weight);
                        return index;
                    }
                    CharacterHead.Append(indices, collar, face, female,
                        (point, normal, coord, tuck) =>
                        {
                            Vector3 vertexNormal = fromFace.MultiplyVector(normal).normalized;
                            Vector3 tv = Vector3.Cross(vertexNormal, fromFace.MultiplyVector(Vector3.up)).normalized;
                            // The face and the jaw follow the head; what tucks into the neck partly follows the neck.
                            float neckShare = neckBone >= 0 ? 0.4f * tuck : 0f;
                            var weight = new BoneWeight
                            {
                                boneIndex0 = head, weight0 = 1f - neckShare,
                                boneIndex1 = Mathf.Max(0, neckBone), weight1 = neckShare,
                            };
                            return Append(fromFace.MultiplyPoint3x4(point), vertexNormal,
                                new Vector4(tv.x, tv.y, tv.z, 1f), coord, weight);
                        },
                        (v, coord) => Append(vertices[v], normals[v], hasTangents ? tangents[v] : default, coord, weights[v]));
                }
                triangles[slot] = indices.ToArray();
            }

            var result = new Mesh { name = mesh.name + " (portrait and clothes)", bindposes = bindposes };
            result.SetVertices(positions);
            result.SetNormals(newNormals);
            if (newTangents.Count == positions.Count) { result.SetTangents(newTangents); }
            result.SetUVs(0, coords);
            result.boneWeights = skinning.ToArray();
            result.subMeshCount = triangles.Length;
            for (int slot = 0; slot < triangles.Length; slot++)
            {
                result.SetTriangles(triangles[slot], slot, false);
            }
            result.bounds = mesh.bounds;
            look.Mesh = result;
            return look;
        }

        private static Vector2 ProjectUv(Chart chart, Vector2 original, Vector3 body,
            float upperHalf, float neck, float waist, float lowerHalf, float hip)
        {
            switch (chart)
            {
                case Chart.Skin:
                    return CharacterHead.BodyUv;
                case Chart.ShirtFront:
                case Chart.ShirtBack:
                    bool shirtFront = chart == Chart.ShirtFront;
                    float u = 0.5f + (shirtFront ? -body.x : body.x) / (2f * upperHalf);
                    float v = Mathf.Clamp01((neck - body.y) / (neck - waist));
                    return Tile(shirtFront ? 0 : 1, 0, Mathf.Clamp(u, 0.025f, 0.975f), v);
                case Chart.PantsFront:
                case Chart.PantsBack:
                    bool pantsFront = chart == Chart.PantsFront;
                    float p = 0.5f + (pantsFront ? -body.x : body.x) / (2.18f * lowerHalf);
                    return Tile(pantsFront ? 0 : 1, 1, Mathf.Clamp(p, 0.015f, 0.985f),
                        Mathf.Clamp01((hip - body.y) / Tuning.ClothesTrousersLength));
                default:
                    return original;
            }
        }

        private static bool IsUpper(string source) => ModelKit.PartOf(source, false) == ModelKit.CharacterPart.Clothes;
        private static bool IsLower(string source) => string.Equals(source, "pants", StringComparison.OrdinalIgnoreCase);

        /// <summary>The garment slots show the prints in their real colours: a white base colour and the (banded) atlas.</summary>
        private static void ShowClothes(InhabitantRig rig, List<int> garments, Color? tint)
        {
            if (garments.Count == 0)
            {
                return;
            }
            Texture2D texture = ClothesTexture(tint, rig.Entry.id == ModelCatalog.QuaterniusWomanDress);
            if (texture == null)
            {
                return;
            }
            foreach (int slot in garments)
            {
                SetPrint(rig.Skin, slot, texture, Color.white);
            }
        }

        /// <summary>Share one compact atlas per personality colour and outfit layout.</summary>
        private static Texture2D ClothesTexture(Color? tint, bool dress)
        {
            Texture2D atlas = ClothesAtlas;
            if (atlas == null || (!tint.HasValue && !dress))
            {
                return atlas;
            }
            Color colour = tint.GetValueOrDefault();
            var key = ((Color32)colour, dress);
            if (ClothesVariants.TryGetValue(key, out Texture2D cached) && cached != null)
            {
                return cached;
            }
            if (!atlas.isReadable)
            {
                ReportOnce("clothes read", $"[CharacterLook] Resources/{Tuning.ClothesAtlasResource} is not readable");
                return atlas;
            }
            // A 256 px view is enough for the on-screen size. Keep the original atlas for unmodified garments.
            int w = atlas.width / 2;
            int h = atlas.height / 2;
            if (clothesPixels == null)
            {
                Color32[] source = atlas.GetPixels32();
                clothesPixels = new Color32[w * h];
                for (int y = 0; y < h; y++)
                {
                    for (int x = 0; x < w; x++)
                    {
                        int i = 2 * y * atlas.width + 2 * x;
                        clothesPixels[y * w + x] = (Color32)(((Color)source[i] + (Color)source[i + 1]
                            + (Color)source[i + atlas.width] + (Color)source[i + atlas.width + 1]) * 0.25f);
                    }
                }
            }
            var pixels = (Color32[])clothesPixels.Clone();
            const float dressWaist = 0.52f;
            if (dress)
            {
                // The lower half of the dress uses the corresponding front/back trouser fabric,
                // sampled below its pockets and above the hem so the skirt keeps its own silhouette.
                int bottom = h / 2;
                int top = Mathf.RoundToInt(TileV(0, dressWaist) * h);
                for (int y = bottom; y < top; y++)
                {
                    int from = Mathf.RoundToInt(TileV(1, Mathf.Lerp(0.95f, 0.34f, (y - bottom) / (float)(top - bottom))) * h);
                    for (int column = 0; column < 2; column++)
                    {
                        for (int x = 0; x < w / 2; x++)
                        {
                            int fabric = Mathf.RoundToInt(Mathf.Lerp(w * 0.29f, w * 0.46f, 2f * x / w));
                            int offset = column * w / 2;
                            pixels[y * w + offset + x] = clothesPixels[from * w + offset + fabric];
                        }
                    }
                }
            }
            if (tint.HasValue)
            {
                Color target = colour.linear;
                PaintBand(pixels, w, h, TileV(0, Tuning.ClothesCollarBand), 1f, target);
                float hem = dress ? dressWaist : 1f;
                PaintBand(pixels, w, h, dress ? TileV(0, hem) : 0.5f, TileV(0, hem - Tuning.ClothesHemBand), target);
            }
            var texture = new Texture2D(w, h, TextureFormat.RGB24, true)
            {
                name = (dress ? "Dress " : "Clothes ") + ColorUtility.ToHtmlStringRGB(colour),
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Trilinear,
                anisoLevel = 2,
            };
            texture.SetPixels32(pixels);
            texture.Apply(true, true);
            ClothesVariants[key] = texture;
            return texture;
        }

        /// <summary>
        /// The rows from <paramref name="vFrom"/> to <paramref name="vTo"/> (UV) in <paramref name="target"/> (linear),
        /// each half of the width (front, back) shaded by its fabric's luminance over the band's mean.
        /// </summary>
        private static void PaintBand(Color32[] pixels, int w, int h, float vFrom, float vTo, Color target)
        {
            int y0 = Mathf.Clamp(Mathf.FloorToInt(vFrom * h), 0, h);
            int y1 = Mathf.Clamp(Mathf.CeilToInt(vTo * h), 0, h);
            for (int column = 0; column < 2; column++)
            {
                int x0 = column * w / 2;
                int x1 = (column + 1) * w / 2;
                double sum = 0;
                int n = 0;
                for (int y = y0; y < y1; y++)
                {
                    for (int x = x0; x < x1; x++)
                    {
                        sum += LumaOf(pixels[y * w + x]);
                        n++;
                    }
                }
                if (n == 0)
                {
                    continue;
                }
                float mean = Mathf.Max((float)(sum / n), 1e-4f);
                for (int y = y0; y < y1; y++)
                {
                    for (int x = x0; x < x1; x++)
                    {
                        int i = y * w + x;
                        float shade = Mathf.Clamp(Mathf.Pow(LumaOf(pixels[i]) / mean, Tuning.ClothesBandContrast), 0.6f, 1.4f);
                        Color c = new Color(target.r * shade, target.g * shade, target.b * shade, 1f).gamma;
                        pixels[i] = c;
                    }
                }
            }
        }

        private static float LumaOf(Color32 p)
        {
            return 0.2126f * Mathf.GammaToLinearSpace(p.r / 255f) + 0.7152f * Mathf.GammaToLinearSpace(p.g / 255f)
                + 0.0722f * Mathf.GammaToLinearSpace(p.b / 255f);
        }

        private const float TileInset = 2f / 512f;

        /// <summary>A point of a tile of the clothes atlas: column 0 front, 1 back; row 0 shirt (top half), 1 trousers.</summary>
        private static Vector2 Tile(int column, int row, float u, float fromTop)
        {
            float u0 = 0.5f * column + TileInset;
            float span = 0.5f - 2f * TileInset;
            return new Vector2(u0 + span * u, TileV(row, fromTop));
        }

        /// <summary>The V of a tile's row at <paramref name="fromTop"/> (0 its top, 1 its bottom).</summary>
        private static float TileV(int row, float fromTop)
        {
            float top = (row == 0 ? 1f : 0.5f) - TileInset;
            float span = 0.5f - 2f * TileInset;
            return top - span * fromTop;
        }

        private static string DominantBone(BoneWeight[] weights, Transform[] bones, int v)
        {
            if (v >= weights.Length)
            {
                return string.Empty;
            }
            BoneWeight w = weights[v];
            int index = w.boneIndex0;
            float best = w.weight0;
            if (w.weight1 > best) { best = w.weight1; index = w.boneIndex1; }
            if (w.weight2 > best) { best = w.weight2; index = w.boneIndex2; }
            if (w.weight3 > best) { index = w.boneIndex3; }
            return index >= 0 && index < bones.Length && bones[index] != null ? bones[index].name : string.Empty;
        }

        private static bool IsTrunk(string bone)
        {
            return bone == "Body" || bone == "Abdomen" || bone == "Torso" || bone == "Hips" || bone == "Neck"
                || bone.StartsWith("UpperLeg", StringComparison.Ordinal);
        }

        private static void ReportOnce(string key, string message)
        {
            if (Reported.Add(key))
            {
                Debug.LogWarning(message);
            }
        }
    }
}
