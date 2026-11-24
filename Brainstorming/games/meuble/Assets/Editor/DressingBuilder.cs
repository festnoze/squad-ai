using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Newtonsoft.Json.Linq;
using OutOfSight.Core;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using Object = UnityEngine.Object;

namespace OutOfSight.Editor
{
    /// <summary>
    /// DRESSING (2026-11-24, docs/next/progress/DRESSING.md): bakes Assets/Resources/DressingLibrary.asset from the delivered
    /// GLBs (Assets/ThirdParty/Models/RoomDressing and LivingRoomFurniture, extracted from Build/room-dressing/RoomDressing.zip
    /// and Build/living-room-furniture/LivingRoomFurniture.zip). Called by ModelCatalogBuilder.Build (SetupAndCompile and every
    /// player build), after the wall arrays it relies on. Idempotent: rebakes only when a GLB or the slice list changed.
    ///
    /// The GLBs are read directly (glTF 2.0 binary, one mesh node at identity, float attributes), not through glTFast's
    /// materials, so the result is exact and needs no importer: x is negated into Unity's left-handed frame (the winding turned
    /// over with it) and V is flipped for Unity's texture origin. Each vertex then names how the wall material draws it:
    /// <list type="bullet">
    /// <item>a vertex of a textured material samples its dressing slice (WallArray.DressingSlices) at its own UV, tinted by its
    /// vertex colour (UV1 = slice + 1, 1, smoothness, 0; UV2 = WallArray.DressingTint, the linear tint);</item>
    /// <item>any other vertex is a flat colour, its vertex colour times the base colour (UV1 = WallArray.FlatFinish, metallic,
    /// smoothness, 0; UV2 = the linear colour and its glow: only the table lamp's bulb glows). A red colour (ModelMath.IsRed:
    /// the remote's power button) is mapped away from red, as ModelKit maps model colours (PRD 7.2: only the player is red).</item>
    /// </list>
    /// The leaves, the lamp shade and the throw are thin open sheets drawn two sided in the GLB; the wall shader culls back faces,
    /// so their triangles are doubled, turned over.
    /// </summary>
    public static class DressingBuilder
    {
        public const string LibraryPath = "Assets/Resources/DressingLibrary.asset";

        /// <summary>Bumped when the bake itself changes, so every library rebakes once.</summary>
        private const string BakeVersion = "dressing-1";

        /// <summary>
        /// Every baked mesh, its GLB stem and the dressing image its textured material shows when the GLB image is not itself a
        /// dressing slice (null: the GLB image names the slice, else the material is drawn flat).
        /// </summary>
        private static readonly (string id, string image)[] Sources =
        {
            (DecorKinds.OpenBook, "book_spread"),
            (DecorKinds.PhotoFrame, "family_photo"),
            (DecorKinds.SofaThrow, "plaid_weave"),
            (DecorKinds.CeramicMug, null),
            (DecorKinds.MagazineStack, null),
            (DecorKinds.TvRemote, null),
            (DecorKinds.KeyDish, null),
            (DecorKinds.Pothos, "pothos_leaf"),
            (DecorKinds.TableLamp, "ivory_linen"),
            (DecorKinds.WalnutCoffeeTable, "walnut_veneer"),
            (DecorKinds.WalnutMediaConsole, "walnut_veneer"),
            (DecorKinds.FlatScreenTv, null),
            // KITCHEN (docs/next/progress/KITCHEN.md): each textured material names its own image in the GLB (steel, worktop, oak).
            (DecorKinds.Saucepan, null),
            (DecorKinds.FryingPan, null),
            (DecorKinds.StockPot, null),
            (DecorKinds.Kettle, null),
            (DecorKinds.CuttingBoard, null),
            (DecorKinds.KitchenBaseCabinet, null),
            (DecorKinds.KitchenDrawerCabinet, null),
            (DecorKinds.KitchenSinkCabinet, null),
            (DecorKinds.KitchenRange, null),
            (DecorKinds.KitchenTallCabinet, null),
            // BEDROOM (docs/next/progress/BEDROOM.md): the textured parts name the atlas bedroom_textiles in the GLB.
            (DecorKinds.BedsideTable, null),
            (DecorKinds.BedsideLamp, null),
            (DecorKinds.AlarmClock, null),
            (DecorKinds.ClothesHeap, null),
            (DecorKinds.OddSocks, null),
            (DecorKinds.Slippers, null),
            (DecorKinds.LaundryBasket, null),
            (DecorKinds.FloorBookStack, null),
            (DecorKinds.TeddyBear, null),
        };

        /// <summary>The materials drawn two sided whose sheets are open (their triangles are doubled).</summary>
        private static readonly string[] TwoSided = { "Pothos leaf", "Linen shade", "Woven plaid", "Pleated shade" };

        /// <summary>The table lamp's bulb (inventory anchor bulb_center) and the glow its bright vertices get within this radius.</summary>
        private static readonly Vector3 BulbCentre = new Vector3(0f, 0.244f, 0f);
        private const float BulbRadius = 0.06f;
        private const float BulbGlow = 0.6f;

        /// <summary>BEDROOM: the bedside lamp's bulb (DecorKinds.BedsideLampBulbY), glowing within this radius.</summary>
        private static readonly Vector3 BedsideBulbCentre = new Vector3(0f, DecorKinds.BedsideLampBulbY, 0f);
        private const float BedsideBulbRadius = 0.035f;

        /// <summary>The PNG of a dressing image in the first of WallArray.DressingFolders that holds it, or null.</summary>
        public static string ImagePath(string image)
        {
            foreach (string folder in WallArray.DressingFolders)
            {
                string path = folder + image + ".png";
                if (File.Exists(path))
                {
                    return path;
                }
            }
            return null;
        }

        /// <summary>True for the path of a dressing image (its size is not the arrays' 512: resampled on purpose).</summary>
        public static bool IsDressingImage(string path)
        {
            return path != null && Array.IndexOf(WallArray.DressingSlices, Path.GetFileNameWithoutExtension(path)) >= 0
                && Array.Exists(WallArray.DressingFolders, f => path.Replace('\\', '/').StartsWith(f, StringComparison.Ordinal));
        }

        private static string GlbPath(string id)
        {
            foreach (string folder in WallArray.DressingFolders)
            {
                string path = folder + id + ".glb";
                if (File.Exists(path))
                {
                    return path;
                }
            }
            return null;
        }

        [MenuItem("OutOfSight/Build Dressing Library")]
        public static void Build()
        {
            var log = new StringBuilder("[DressingBuilder]\n");
            Build(log);
            AssetDatabase.SaveAssets();
            Debug.Log(log.ToString());
        }

        public static void Build(StringBuilder log)
        {
            string hash = SourceHash();
            var library = AssetDatabase.LoadAssetAtPath<DressingLibrary>(LibraryPath);
            if (library != null && library.sourceHash == hash && library.entries.Count == Sources.Length
                && library.entries.TrueForAll(e => e != null && e.mesh != null))
            {
                log.Append("  unchanged ").Append(LibraryPath).Append('\n');
                return;
            }
            if (library == null)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(LibraryPath) ?? "Assets/Resources");
                library = ScriptableObject.CreateInstance<DressingLibrary>();
                AssetDatabase.CreateAsset(library, LibraryPath);
            }
            foreach (Object o in AssetDatabase.LoadAllAssetsAtPath(LibraryPath))
            {
                if (o is Mesh)
                {
                    Object.DestroyImmediate(o, true);
                }
            }
            library.entries = new List<DressingLibrary.Entry>();
            foreach ((string id, string image) in Sources)
            {
                string path = GlbPath(id);
                if (path == null)
                {
                    Debug.LogError($"[DressingBuilder] {id}.glb is in none of {string.Join(", ", WallArray.DressingFolders)}");
                    continue;
                }
                Mesh mesh = Bake(id, path, image, out int triangles);
                AssetDatabase.AddObjectToAsset(mesh, library);
                library.entries.Add(new DressingLibrary.Entry
                {
                    id = id, mesh = mesh, boundsMin = mesh.bounds.min, boundsMax = mesh.bounds.max, triangles = triangles,
                });
                log.Append($"  {id}: {mesh.vertexCount} vertices, {triangles} triangles, bounds {mesh.bounds.min.ToString("0.###")} to {mesh.bounds.max.ToString("0.###")}\n");
            }
            library.sourceHash = hash;
            EditorUtility.SetDirty(library);
            log.Append("  baked ").Append(LibraryPath).Append('\n');
        }

        private static string SourceHash()
        {
            using (var sha = System.Security.Cryptography.SHA1.Create())
            {
                var all = new List<byte>(Encoding.UTF8.GetBytes(BakeVersion + "|" + string.Join(",", WallArray.DressingSlices) + "|" + WallArray.Slices.Length));
                foreach ((string id, string _) in Sources)
                {
                    string path = GlbPath(id);
                    if (path != null)
                    {
                        all.AddRange(File.ReadAllBytes(path));
                    }
                }
                return BitConverter.ToString(sha.ComputeHash(all.ToArray())).Replace("-", string.Empty);
            }
        }

        // ----- The GLB reader and the bake -----

        private static Mesh Bake(string id, string path, string image, out int triangleCount)
        {
            byte[] glb = File.ReadAllBytes(path);
            if (glb.Length < 20 || BitConverter.ToUInt32(glb, 0) != 0x46546C67)
            {
                throw new InvalidOperationException($"[DressingBuilder] {path} is not a binary glTF");
            }
            int jsonLength = BitConverter.ToInt32(glb, 12);
            JObject gltf = JObject.Parse(Encoding.UTF8.GetString(glb, 20, jsonLength));
            int bin = 20 + jsonLength + 8;
            int slice = image != null ? WallArray.DressingSliceOf(image) : -1;
            var materials = (JArray)gltf["materials"];

            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var uvs = new List<Vector2>();
            var finishes = new List<Vector4>();
            var bands = new List<Vector4>();
            var triangles = new List<int>();
            foreach (JToken node in gltf["nodes"])
            {
                if (node["mesh"] == null)
                {
                    continue;
                }
                if (node["translation"] != null || node["rotation"] != null || node["scale"] != null || node["matrix"] != null)
                {
                    Debug.LogWarning($"[DressingBuilder] {path}: node {node["name"]} has a transform, ignored (the delivery says identity)");
                }
                foreach (JToken primitive in gltf["meshes"][(int)node["mesh"]]["primitives"])
                {
                    JToken attributes = primitive["attributes"];
                    float[] p = Read(gltf, glb, bin, (int)attributes["POSITION"], out _);
                    float[] n = Read(gltf, glb, bin, (int)attributes["NORMAL"], out _);
                    float[] t = attributes["TEXCOORD_0"] != null ? Read(gltf, glb, bin, (int)attributes["TEXCOORD_0"], out _) : null;
                    float[] c = attributes["COLOR_0"] != null ? Read(gltf, glb, bin, (int)attributes["COLOR_0"], out _) : null;
                    int colourComponents = c != null ? c.Length / (p.Length / 3) : 0;
                    int[] indices = ReadIndices(gltf, glb, bin, (int)primitive["indices"]);
                    JToken material = primitive["material"] != null ? materials[(int)primitive["material"]] : null;
                    JToken pbr = material?["pbrMetallicRoughness"];
                    int materialSlice = TextureSlice(gltf, pbr, slice);
                    bool textured = materialSlice >= 0;
                    Color factor = Color.white;
                    if (pbr?["baseColorFactor"] is JArray f && f.Count >= 3)
                    {
                        factor = new Color((float)f[0], (float)f[1], (float)f[2], 1f);
                    }
                    // glTF defaults: metallic 1, roughness 1.
                    float metallic = pbr?["metallicFactor"] != null ? (float)pbr["metallicFactor"] : 1f;
                    float smoothness = 1f - (pbr?["roughnessFactor"] != null ? (float)pbr["roughnessFactor"] : 1f);
                    string materialName = (string)material?["name"] ?? string.Empty;
                    int count = p.Length / 3;
                    int start = vertices.Count;
                    for (int k = 0; k < count; k++)
                    {
                        vertices.Add(new Vector3(-p[3 * k], p[3 * k + 1], p[3 * k + 2]));
                        normals.Add(new Vector3(-n[3 * k], n[3 * k + 1], n[3 * k + 2]));
                        Color colour = factor;
                        if (c != null)
                        {
                            colour *= new Color(c[colourComponents * k], c[colourComponents * k + 1], c[colourComponents * k + 2], 1f);
                        }
                        if (textured)
                        {
                            uvs.Add(t != null ? new Vector2(t[2 * k], 1f - t[2 * k + 1]) : Vector2.zero);
                            finishes.Add(new Vector4(materialSlice + 1, 1f, smoothness, 0f));
                            bands.Add(new Vector4(WallArray.DressingTint, colour.r, colour.g, colour.b));
                        }
                        else
                        {
                            colour = NotRed(colour);
                            bool bulb = colour.maxColorComponent > 0.5f
                                && (id == DecorKinds.TableLamp && (vertices[vertices.Count - 1] - BulbCentre).magnitude < BulbRadius
                                    || id == DecorKinds.BedsideLamp && (vertices[vertices.Count - 1] - BedsideBulbCentre).magnitude < BedsideBulbRadius);
                            uvs.Add(Vector2.zero);
                            finishes.Add(new Vector4(WallArray.FlatFinish, metallic, smoothness, 0f));
                            bands.Add(new Vector4(colour.r, colour.g, colour.b, bulb ? BulbGlow : 0f));
                        }
                    }
                    // Mirrored by the x flip: the winding turns over.
                    for (int i = 0; i + 2 < indices.Length; i += 3)
                    {
                        triangles.Add(start + indices[i]);
                        triangles.Add(start + indices[i + 2]);
                        triangles.Add(start + indices[i + 1]);
                    }
                    if (Array.IndexOf(TwoSided, materialName) >= 0)
                    {
                        int back = vertices.Count;
                        for (int k = 0; k < count; k++)
                        {
                            vertices.Add(vertices[start + k]);
                            normals.Add(-normals[start + k]);
                            uvs.Add(uvs[start + k]);
                            finishes.Add(finishes[start + k]);
                            bands.Add(bands[start + k]);
                        }
                        for (int i = 0; i + 2 < indices.Length; i += 3)
                        {
                            triangles.Add(back + indices[i]);
                            triangles.Add(back + indices[i + 1]);
                            triangles.Add(back + indices[i + 2]);
                        }
                    }
                }
            }
            var mesh = new Mesh { name = "Dressing " + id };
            if (vertices.Count > 65535)
            {
                mesh.indexFormat = IndexFormat.UInt32;
            }
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetUVs(0, uvs);
            mesh.SetUVs(WallArray.FinishChannel, finishes);
            mesh.SetUVs(WallArray.BandChannel, bands);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            // Left readable: the level builder combines it with the floors at run time (PrimitiveKit.CombinedMesh).
            triangleCount = triangles.Count / 3;
            return mesh;
        }

        /// <summary>
        /// KITCHEN: the dressing slice a material samples: the slice named by its base colour image (glTF images[].name, the PNG
        /// stem) when that is a dressing slice, else <paramref name="fallback"/>; -1 for an untextured material.
        /// </summary>
        private static int TextureSlice(JObject gltf, JToken pbr, int fallback)
        {
            JToken texture = pbr?["baseColorTexture"];
            if (texture == null)
            {
                return -1;
            }
            JToken source = gltf["textures"]?[(int)texture["index"]]?["source"];
            string name = source != null ? (string)gltf["images"]?[(int)source]?["name"] : null;
            int named = name != null ? WallArray.DressingSliceOf(name) : -1;
            return named >= 0 ? named : fallback;
        }

        /// <summary>A colour ModelMath reads as red is mapped as ModelKit maps a model's red (linear in, linear out).</summary>
        private static Color NotRed(Color linear)
        {
            Color srgb = linear.gamma;
            return ModelMath.IsRed(srgb) ? ModelMath.MapColor(srgb, false, 0f, default).linear : linear;
        }

        /// <summary>An accessor's components as floats (float, or normalised unsigned byte or short), and its component count.</summary>
        private static float[] Read(JObject gltf, byte[] glb, int bin, int accessorIndex, out int components)
        {
            JToken accessor = gltf["accessors"][accessorIndex];
            JToken view = gltf["bufferViews"][(int)accessor["bufferView"]];
            components = Components((string)accessor["type"]);
            int type = (int)accessor["componentType"];
            int size = type == 5126 ? 4 : type == 5123 ? 2 : 1;
            int count = (int)accessor["count"];
            int stride = view["byteStride"] != null ? (int)view["byteStride"] : size * components;
            int offset = bin + (view["byteOffset"] != null ? (int)view["byteOffset"] : 0) + (accessor["byteOffset"] != null ? (int)accessor["byteOffset"] : 0);
            var values = new float[count * components];
            for (int i = 0; i < count; i++)
            {
                for (int k = 0; k < components; k++)
                {
                    int at = offset + i * stride + k * size;
                    values[i * components + k] = type == 5126 ? BitConverter.ToSingle(glb, at)
                        : type == 5123 ? BitConverter.ToUInt16(glb, at) / 65535f
                        : glb[at] / 255f;
                }
            }
            return values;
        }

        private static int[] ReadIndices(JObject gltf, byte[] glb, int bin, int accessorIndex)
        {
            JToken accessor = gltf["accessors"][accessorIndex];
            JToken view = gltf["bufferViews"][(int)accessor["bufferView"]];
            int type = (int)accessor["componentType"];
            int size = type == 5125 ? 4 : type == 5123 ? 2 : 1;
            int count = (int)accessor["count"];
            int offset = bin + (view["byteOffset"] != null ? (int)view["byteOffset"] : 0) + (accessor["byteOffset"] != null ? (int)accessor["byteOffset"] : 0);
            var indices = new int[count];
            for (int i = 0; i < count; i++)
            {
                int at = offset + i * size;
                indices[i] = type == 5125 ? (int)BitConverter.ToUInt32(glb, at) : type == 5123 ? BitConverter.ToUInt16(glb, at) : glb[at];
            }
            return indices;
        }

        private static int Components(string type)
        {
            switch (type)
            {
                case "SCALAR": return 1;
                case "VEC2": return 2;
                case "VEC3": return 3;
                case "VEC4": return 4;
                default: throw new InvalidOperationException("[DressingBuilder] accessor type " + type);
            }
        }
    }
}
