using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>
    /// Procedural primitives (PRD 7.1): generated low poly meshes and one shared URP material per color.
    /// Unity's built in primitives are not used: their sphere alone is 768 triangles, and they come with
    /// colliders nobody asked for.
    ///
    /// Caches are static and survive level rebuilds. Every cached object is flagged DontUnloadUnusedAsset
    /// and checked for null before reuse, because a scene load may unload unreferenced runtime assets.
    ///
    /// M4.2 textures (<see cref="TextureLibrary"/>): every generated mesh carries UVs in metres (boxes and quads per
    /// size, V along the longer side of each face). M7 real colours (CONTRACT_M7 5): <see cref="Detail(Renderer, int, Surface)"/>
    /// shows a surface's image in its own colours on one renderer slot, through one material per surface
    /// (<see cref="SurfaceMaterial"/>), the player furniture through its own red one (<see cref="PlayerMaterial"/>).
    /// </summary>
    public static class PrimitiveKit
    {
        public const string LitShaderName = "Universal Render Pipeline/Lit";
        public const string UnlitShaderName = "Universal Render Pipeline/Unlit";

        private static readonly Dictionary<Color32, Material> LitCache = new Dictionary<Color32, Material>();
        private static readonly Dictionary<Color32, Material> UnlitCache = new Dictionary<Color32, Material>();
        private static readonly Dictionary<Color32, Material> TransparentCache = new Dictionary<Color32, Material>();
        // M6 (CONTRACT_M6 2.4): a few colours (the near-black frame, the robot's shell) are reused across several
        // surfaces that each need their own fixed finish (TextureLibrary.FinishOf): keyed by colour AND surface, so
        // LitSurface never collides with an unrelated Lit(color, smoothness) call for the same colour (the project
        // reuses a handful of colours everywhere to stay under the PRD 7.4 material cap, each at its own smoothness).
        private static readonly Dictionary<(Color32 color, Surface surface), Material> SurfaceCache =
            new Dictionary<(Color32, Surface), Material>();
        private static readonly Dictionary<string, Mesh> MeshCache = new Dictionary<string, Mesh>();

        // ----- Materials -----

        /// <summary>
        /// The URP Lit material of a palette colour (one per colour, PRD 7.4). M4.2: its base colour is the palette
        /// divided by <see cref="Tuning.DetailMean"/> (TextureLibrary.Compensate) and its base map the flat map of that
        /// mean, so it shows the palette colour exactly; <see cref="Detail(Renderer, int, Surface)"/> swaps in a detail
        /// texture of the same mean per renderer slot. M6 (CONTRACT_M6 2.4): <paramref name="metallic"/>, as
        /// <paramref name="smoothness"/> always was, a caller asking for a colour already cached (at another smoothness
        /// or metallic) gets the cached material: deliberate reuse keeps the level under its material cap. A surface
        /// whose finish must never be silently overridden this way (Grass, Lacquer, Metal, Plastic, Foliage, Soil) goes
        /// through <see cref="LitSurface"/> instead, cached apart by colour and surface.
        /// </summary>
        public static Material Lit(Color color, float smoothness = 0.25f, float metallic = 0f)
        {
            Color32 key = color;
            if (LitCache.TryGetValue(key, out Material cached) && cached != null)
            {
                return cached;
            }
            Material m = NewLit(color, smoothness, metallic);
            LitCache[key] = m;
            return m;
        }

        /// <summary>
        /// M6 (CONTRACT_M6 2.4): the URP Lit material of a palette colour shown with <paramref name="surface"/>'s own
        /// fixed finish (<see cref="TextureLibrary.FinishOf"/>), cached by colour AND surface: never shares a material
        /// with an ordinary <see cref="Lit(Color, float, float)"/> call for the same colour, however many of those
        /// already exist (the frame, the robot's shell and bumper, the garden and the player's own furniture all reuse
        /// colours a level already draws elsewhere at a different smoothness). Falls back to Lit's own default (logged
        /// once) for a surface with no fixed finish: a caller error, never a silently wrong finish.
        /// </summary>
        public static Material LitSurface(Color color, Surface surface)
        {
            Color32 color32 = color;
            var key = (color32, surface); // MUTATION:LIT_SURFACE_KEY
            if (SurfaceCache.TryGetValue(key, out Material cached) && cached != null)
            {
                return cached;
            }
            if (!TextureLibrary.FinishOf(surface, out float smoothness, out float metallic))
            {
                ReportOnce("finish " + surface, $"[PrimitiveKit] {surface} has no fixed finish (TextureLibrary.FinishOf): LitSurface falls back to Lit's default");
                smoothness = 0.25f;
                metallic = 0f;
            }
            Material m = NewLit(color, smoothness, metallic, surface);
            SurfaceCache[key] = m;
            return m;
        }

        // ----- M7 real colours (CONTRACT_M7 5): one material per surface, and the player's own -----

        private static readonly Dictionary<Surface, Material> ColourCache = new Dictionary<Surface, Material>();
        private static readonly Dictionary<Color32, Material> PlayerCache = new Dictionary<Color32, Material>();

        /// <summary>
        /// M7 real colours (CONTRACT_M7 5): the one URP Lit material of a textured surface, whatever palette colour its
        /// callers asked for: a white base colour, the surface's colour map as base map (TextureLibrary.ColourOf), so the
        /// image shows in its own colours, at the surface's one finish (TextureLibrary.ColourFinishOf).
        /// <see cref="Detail(Renderer, int, Surface)"/> puts it in the slot. Its <see cref="PaletteOf"/> is white (the image
        /// carries the colour). Null for Plain or a surface the library has no colour map for.
        /// </summary>
        public static Material SurfaceMaterial(Surface surface)
        {
            if (ColourCache.TryGetValue(surface, out Material cached) && cached != null)
            {
                return cached;
            }
            Texture2D colour = TextureLibrary.ColourOf(surface);
            if (colour == null)
            {
                return null;
            }
            TextureLibrary.ColourFinishOf(surface, out float smoothness, out float metallic);
            Material m = NewLit(Color.white, smoothness, metallic, surface, colour, "Colour " + surface);
            ColourCache[surface] = m;
            return m;
        }

        /// <summary>
        /// M7 real colours (CONTRACT_M7 5, PRD 7.2): the material of the player furniture's red slots: a white base
        /// colour, the owner's red painted metal image as base map (TextureLibrary.PlayerColour), the painted metal finish
        /// (Tuning.PlayerSmoothness, Tuning.PlayerMetallic). One per red (a level has one); its <see cref="PaletteOf"/> is
        /// that red. Null when the library has no player image (the slot then keeps its red palette material).
        /// </summary>
        public static Material PlayerMaterial(Color red)
        {
            Color32 key = red;
            if (PlayerCache.TryGetValue(key, out Material cached) && cached != null)
            {
                return cached;
            }
            Texture2D colour = TextureLibrary.PlayerColour;
            if (colour == null)
            {
                return null;
            }
            Material m = NewLit(red, Tuning.PlayerSmoothness, Tuning.PlayerMetallic, Surface.Lacquer, colour,
                "Player " + ColorUtility.ToHtmlStringRGB(red));
            PlayerCache[key] = m;
            return m;
        }

        private static readonly Dictionary<Texture2D, Material> MapCache = new Dictionary<Texture2D, Material>();

        /// <summary>
        /// DOGBIG: the one URP Lit material showing a painted colour map on a model's own UV0 (the dog's fur texture,
        /// ModelKit.ApplyPetFurMap): a white base colour and <paramref name="colourMap"/> as base map, one per map. Its
        /// <see cref="PaletteOf"/> is white (the picture carries the colours).
        /// </summary>
        public static Material MapMaterial(Texture2D colourMap, float smoothness)
        {
            if (colourMap == null)
            {
                return null;
            }
            if (MapCache.TryGetValue(colourMap, out Material cached) && cached != null)
            {
                return cached;
            }
            Material m = NewLit(Color.white, smoothness, 0f, null, colourMap, "Map " + colourMap.name);
            MapCache[colourMap] = m;
            return m;
        }

        /// <summary>
        /// A URP Lit material registered with its palette colour <paramref name="color"/>. Without a colour map: the M4.2
        /// palette material (base colour compensated, the flat base map). With one (M7 real colours): a white base colour
        /// and that map as base map, so the image's own colours show.
        /// </summary>
        private static Material NewLit(Color color, float smoothness, float metallic, Surface? taggedSurface = null,
            Texture2D colourMap = null, string colourName = null)
        {
            Shader shader = Shader.Find(LitShaderName);
            if (shader == null)
            {
                Debug.LogError("[PrimitiveKit] URP Lit shader not found (is it in Always Included Shaders?)");
                shader = Shader.Find("Hidden/InternalErrorShader");
            }
            string name = colourName ?? "Lit " + ColorUtility.ToHtmlStringRGB(color) + (taggedSurface.HasValue ? " " + taggedSurface.Value : "");
            var m = new Material(shader) { name = name, enableInstancing = true };
            m.SetColor("_BaseColor", colourMap != null ? Color.white : TextureLibrary.Compensate(color));
            m.SetTexture(BaseMapId, colourMap != null ? colourMap : TextureLibrary.Flat);
            m.SetFloat("_Smoothness", smoothness);
            m.SetFloat("_Metallic", metallic);
            // M6 polish: a smooth finish (Lacquer) needs its specular highlight and reflection probe to actually show;
            // explicit, never left to the shader default.
            m.SetFloat("_SpecularHighlights", 1f);
            m.SetFloat("_EnvironmentReflections", 1f);
            // M7 textures (CONTRACT_M7 1.2): every Lit material can show a normal map, always through the per-renderer
            // property block (Detail below), never a material level texture: Detail already swaps the base map per
            // slot on a material shared by several surfaces (the six M4.2 ones have no fixed finish), so the bump map
            // follows the same path. Left unset here, _BumpMap keeps the shader's own neutral default (flat normal,
            // "bump"): a slot without a normal map in the library renders exactly as before.
            m.EnableKeyword("_NORMALMAP");
            m.hideFlags = HideFlags.DontUnloadUnusedAsset;
            Palette[m] = color;
            return m;
        }

        private static readonly Dictionary<Material, Color32> Palette = new Dictionary<Material, Color32>();

        /// <summary>
        /// M7 real colours (CONTRACT_M7 5): the mean colour (sRGB) slot <paramref name="slot"/> of <paramref name="renderer"/>
        /// is built with, before light: its material's base colour times the mean of the base map it shows (its property
        /// block's, else its material's; TextureLibrary.MeanColourOf, white for a map the library does not know). Clear
        /// for an empty slot or a material without a base colour. Tests read PRD 7.2 (the player furniture is the one
        /// saturated red) off it.
        /// </summary>
        public static Color ShownColour(Renderer renderer, int slot)
        {
            Material[] materials = renderer != null ? renderer.sharedMaterials : null;
            Material m = materials != null && slot >= 0 && slot < materials.Length ? materials[slot] : null;
            if (m == null || !m.HasProperty("_BaseColor"))
            {
                return Color.clear;
            }
            Texture map = m.HasProperty(BaseMapId) ? m.GetTexture(BaseMapId) : null;
            shownBlock ??= new MaterialPropertyBlock();
            renderer.GetPropertyBlock(shownBlock, slot);
            if (!shownBlock.isEmpty && shownBlock.GetTexture(BaseMapId) != null)
            {
                map = shownBlock.GetTexture(BaseMapId);
            }
            Color mean = TextureLibrary.MeanColourOf(map) ?? Color.white;
            Color baseColour = m.GetColor("_BaseColor").linear;
            return new Color(baseColour.r * mean.r, baseColour.g * mean.g, baseColour.b * mean.b, baseColour.a).gamma;
        }

        private static MaterialPropertyBlock shownBlock;

        /// <summary>M4.2: the palette colour a <see cref="Lit"/> material was made for (tests), or null for another material.</summary>
        public static Color? PaletteOf(Material material)
        {
            return material != null && Palette.TryGetValue(material, out Color32 c) ? (Color)c : (Color?)null;
        }

        // ----- M4.2 textures: the detail of a renderer slot -----

        private static readonly int BaseMapId = Shader.PropertyToID("_BaseMap");
        private static readonly int BaseMapStId = Shader.PropertyToID("_BaseMap_ST");
        // M7 textures (CONTRACT_M7 1.2): the normal map and its strength, set through the same property block as the
        // base map, at the base map's own UV transform (the URP Lit shader computes one uv from _BaseMap_ST and
        // reuses it for every map of the slot, so a separate _BumpMap_ST would do nothing).
        private static readonly int BumpMapId = Shader.PropertyToID("_BumpMap");
        private static readonly int BumpScaleId = Shader.PropertyToID("_BumpScale");
        private static MaterialPropertyBlock detailBlock;
        private static readonly HashSet<string> ReportedProblems = new HashSet<string>();
        private static readonly Dictionary<(int mesh, int slot, Vector3Int scale), float> DensityCache =
            new Dictionary<(int, int, Vector3Int), float>();

        /// <summary>Every slot of <paramref name="renderer"/> shows <paramref name="surface"/>.</summary>
        public static void Detail(Renderer renderer, Surface surface)
        {
            if (renderer == null)
            {
                return;
            }
            int slots = renderer.sharedMaterials.Length;
            for (int i = 0; i < slots; i++)
            {
                Detail(renderer, i, surface);
            }
        }

        /// <summary>
        /// Slot <paramref name="slot"/> of <paramref name="renderer"/> shows <paramref name="surface"/>. M7 real colours
        /// (CONTRACT_M7 5, product owner decision of 2026-11-18), by what the slot's palette material stands for:
        /// - the player furniture's red (PRD 7.2: the one red thing): <see cref="PlayerMaterial"/>, the owner's red image;
        /// - any other palette colour: <see cref="SurfaceMaterial"/>, the surface's image in its own colours;
        /// - an inhabitant (<paramref name="keepPalette"/>, or a renderer on the Inhabitant layer: CharacterLook owns the
        ///   clothes) or a material that is not a PrimitiveKit Lit one: the M4.2 rule, its palette material kept with the
        ///   grayscale detail over it.
        /// A MaterialPropertyBlock on that slot sets the base map and a tiling so one repeat spans
        /// <see cref="TextureLibrary.TileMetres"/> of the renderer as it stands now (the metres per UV are measured on its
        /// mesh: procedural meshes carry UVs in metres, Kenney's are a planar projection in inches of its native units,
        /// the humans' are generated by ModelKit), and the surface's normal map. Plain does nothing. Never touches the
        /// base colour: a renderer's property blocks also apply when the x-ray's RenderObjects passes draw it with their
        /// override materials, and the stencil-only one must stay transparent. A missing texture or unmeasurable UVs log
        /// one error (the built player's probe fails on it) and leave the slot as it was.
        /// </summary>
        public static void Detail(Renderer renderer, int slot, Surface surface)
        {
            Detail(renderer, slot, surface, false);
        }

        /// <summary>
        /// M7 real colours (CONTRACT_M7 5): the material <see cref="Detail(Renderer, int, Surface, bool)"/> puts in a slot
        /// that holds <paramref name="material"/> to show <paramref name="surface"/>: the player's own for the player's red
        /// (PRD 7.2), the surface's one for any other palette colour, or <paramref name="material"/> itself (Plain, the
        /// textures off, a slot that keeps its palette, a material that is not a PrimitiveKit Lit one, or a library
        /// without that colour map). LevelBuilder's combiner groups its parts by it, so two palette colours of one surface
        /// draw as one renderer.
        /// </summary>
        public static Material ShownMaterial(Material material, Surface surface, bool keepPalette = false)
        {
            if (material == null || surface == Surface.Plain || TextureLibrary.Disabled || keepPalette)
            {
                return material;
            }
            Color? palette = PaletteOf(material);
            if (!palette.HasValue)
            {
                return material;
            }
            if (ModelMath.IsRed(palette.Value)) // MUTATION:PLAYER_COLOUR
            {
                return PlayerMaterial(palette.Value) ?? material;
            }
            return SurfaceMaterial(surface) ?? material; // MUTATION:REAL_COLOUR
        }

        /// <summary><see cref="Detail(Renderer, int, Surface)"/>; <paramref name="keepPalette"/> keeps the slot's palette material (an inhabitant's).</summary>
        public static void Detail(Renderer renderer, int slot, Surface surface, bool keepPalette)
        {
            if (renderer == null || surface == Surface.Plain || TextureLibrary.Disabled)
            {
                return;
            }
            Material[] materials = renderer.sharedMaterials;
            Material current = slot >= 0 && slot < materials.Length ? materials[slot] : null;
            // Walls 4 (WallArray): the wall material shows the finish each vertex names; no property block, no detail.
            if (WallArray.IsWallMaterial(current))
            {
                return;
            }
            keepPalette |= renderer.gameObject.layer == Layers.Inhabitant;
            Material shown = ShownMaterial(current, surface, keepPalette);
            Texture2D texture;
            Texture2D normal;
            float tile;
            if (shown != null && PlayerCache.ContainsValue(shown))
            {
                texture = TextureLibrary.PlayerColour;
                normal = null; // painted metal is optically flat: its finish is the material's
                tile = TextureLibrary.TileMetres(Surface.Lacquer);
            }
            else if (shown != null && ColourCache.TryGetValue(surface, out Material colourMaterial) && shown == colourMaterial)
            {
                texture = TextureLibrary.ColourOf(surface);
                normal = TextureLibrary.NormalOf(surface);
                tile = TextureLibrary.TileMetres(surface);
            }
            else
            {
                Color? palette = PaletteOf(current);
                if (!keepPalette && palette.HasValue)
                {
                    ReportOnce("colour " + surface, ModelMath.IsRed(palette.Value)
                        ? $"[PrimitiveKit] no player colour map (Resources/{TextureLibrary.ResourcePath}): the player furniture keeps its palette red"
                        : $"[PrimitiveKit] no colour map for {surface} (Resources/{TextureLibrary.ResourcePath}): the slot keeps its palette colour");
                }
                texture = TextureLibrary.TextureOf(surface);
                normal = TextureLibrary.NormalOf(surface);
                tile = TextureLibrary.TileMetres(surface);
            }
            if (texture == null)
            {
                ReportOnce("texture " + surface, $"[PrimitiveKit] no detail texture for {surface} (Resources/{TextureLibrary.ResourcePath}): the slot stays flat");
                return;
            }
            float metresPerUv = MetresPerUv(renderer, slot);
            if (!(metresPerUv > 0f) || float.IsInfinity(metresPerUv))
            {
                ReportOnce("uv " + renderer.name + slot,
                    $"[PrimitiveKit] {renderer.name} slot {slot}: its mesh has no measurable UVs, {surface} cannot be shown");
                return;
            }
            if (shown != current)
            {
                materials[slot] = shown;
                renderer.sharedMaterials = materials;
            }
            float repeat = metresPerUv / tile;
            if (detailBlock == null)
            {
                detailBlock = new MaterialPropertyBlock();
            }
            detailBlock.Clear();
            detailBlock.SetTexture(BaseMapId, texture); // MUTATION:DETAIL
            detailBlock.SetVector(BaseMapStId, new Vector4(repeat, repeat, 0f, 0f));
            // M7 textures (CONTRACT_M7 1.2): a surface with a derived normal map also shows it, at its own modest
            // scale; a surface without one (Plastic, Foliage, Soil, Plain, the player's painted metal) leaves the
            // material's own neutral default.
            if (normal != null) // MUTATION:DETAIL_NORMAL
            {
                detailBlock.SetTexture(BumpMapId, normal);
                detailBlock.SetFloat(BumpScaleId, TextureLibrary.BumpScaleOf(surface));
            }
            renderer.SetPropertyBlock(detailBlock, slot);
        }

        /// <summary>
        /// M7 rug image (product owner, 2026-11-18): slot <paramref name="slot"/> of <paramref name="renderer"/> shows
        /// the rug's own picture (<see cref="TextureLibrary.RugColour"/>) exactly once over its own UV 0 to 1, never
        /// tiled: unlike <see cref="Detail(Renderer, int, Surface)"/>, no <see cref="MetresPerUv"/> measurement and no
        /// repeat, so the mesh must already carry UV0 in the 0 to 1 range over the whole visible surface (BuildRug and
        /// BuildExit's own dedicated mesh, <see cref="RugNineSliceMesh"/>, never <see cref="QuadMeshSized"/> or a box).
        /// Drawn through the same shared Surface.Carpet material
        /// (<see cref="SurfaceMaterial"/>) as the "soft" room floor and the rug's own tiled skirt or border below it,
        /// unchanged (PRD 7.4: one material, not a second one for rugs); no normal map (a stretched tiling bump would
        /// look wrong on a picture that is never tiled). Does nothing for a null renderer, with
        /// <see cref="TextureLibrary.Disabled"/>, or when the library has no rug image (one error logged, the slot
        /// keeps its palette colour, as every other <see cref="Detail(Renderer, int, Surface)"/> miss).
        /// </summary>
        public static void RugDetail(Renderer renderer, int slot)
        {
            if (renderer == null || TextureLibrary.Disabled)
            {
                return;
            }
            Texture2D texture = TextureLibrary.RugColour;
            if (texture == null)
            {
                ReportOnce("rug texture", $"[PrimitiveKit] no rug colour map (Resources/{TextureLibrary.ResourcePath}): the rug keeps its palette colour");
                return;
            }
            Material[] materials = renderer.sharedMaterials;
            Material current = slot >= 0 && slot < materials.Length ? materials[slot] : null;
            Material shown = ShownMaterial(current, Surface.Carpet);
            if (shown != current)
            {
                materials[slot] = shown;
                renderer.sharedMaterials = materials;
            }
            SetUnitMap(renderer, slot, texture);
        }

        /// <summary>Use the whole leaf chart once on each blade, over the existing foliage finish.</summary>
        public static void BananaLeafDetail(Renderer renderer)
        {
            if (renderer == null || TextureLibrary.Disabled)
            {
                return;
            }
            Texture2D texture = TextureLibrary.BananaLeafColour;
            if (texture == null)
            {
                ReportOnce("banana leaf texture", "[PrimitiveKit] missing Resources/BananaLeaf");
                return;
            }
            SetUnitMap(renderer, 0, texture);
        }

        private static void SetUnitMap(Renderer renderer, int slot, Texture2D texture)
        {
            if (detailBlock == null)
            {
                detailBlock = new MaterialPropertyBlock();
            }
            detailBlock.Clear();
            detailBlock.SetTexture(BaseMapId, texture);
            detailBlock.SetVector(BaseMapStId, new Vector4(1f, 1f, 0f, 0f)); // UV 0 to 1 exactly once: the mesh's own unit UV.
            renderer.SetPropertyBlock(detailBlock, slot);
        }

        private static void ReportOnce(string key, string message)
        {
            if (ReportedProblems.Add(key))
            {
                Debug.LogError(message);
            }
        }

        /// <summary>
        /// M4.2: world metres per UV unit on slot <paramref name="slot"/> of <paramref name="renderer"/>, as it stands:
        /// the median, over the edges of the slot's triangles, of the edge's world length over its UV length. A
        /// skinned mesh is measured on its baked pose (BakeMesh with its scale, then the renderer's matrix, as the model
        /// catalog measures it). Cached by mesh, slot and scale. NaN when the mesh has no UVs or cannot be read.
        /// </summary>
        public static float MetresPerUv(Renderer renderer, int slot)
        {
            Mesh mesh = ModelKit.MeshOf(renderer);
            if (mesh == null || slot < 0 || slot >= mesh.subMeshCount || !mesh.isReadable
                || !mesh.HasVertexAttribute(VertexAttribute.TexCoord0))
            {
                return float.NaN;
            }
            Vector3Int scale = Vector3Int.RoundToInt(renderer.transform.lossyScale * 10000f);
            if (DensityCache.TryGetValue((mesh.GetInstanceID(), slot, scale), out float cached))
            {
                return cached;
            }
            MeasureDensities(renderer, mesh, scale);
            return DensityCache.TryGetValue((mesh.GetInstanceID(), slot, scale), out float measured) ? measured : float.NaN;
        }

        /// <summary>Measures and caches <see cref="MetresPerUv"/> for every slot of the renderer's mesh in one pass.</summary>
        private static void MeasureDensities(Renderer renderer, Mesh mesh, Vector3Int scale)
        {
            Vector3[] vertices;
            if (renderer is SkinnedMeshRenderer skinned)
            {
                var baked = new Mesh();
                skinned.BakeMesh(baked, true);
                vertices = baked.vertices;
                Object.DestroyImmediate(baked);
            }
            else
            {
                vertices = mesh.vertices;
            }
            var uvs = new List<Vector2>(mesh.vertexCount);
            mesh.GetUVs(0, uvs);
            Matrix4x4 toWorld = renderer.transform.localToWorldMatrix;
            var ratios = new List<float>();
            for (int slot = 0; slot < mesh.subMeshCount; slot++)
            {
                float result = float.NaN;
                if (uvs.Count == vertices.Length)
                {
                    int[] triangles = mesh.GetTriangles(slot);
                    ratios.Clear();
                    for (int t = 0; t + 2 < triangles.Length; t += 3)
                    {
                        for (int e = 0; e < 3; e++)
                        {
                            int a = triangles[t + e];
                            int b = triangles[t + (e + 1) % 3];
                            float uv = (uvs[b] - uvs[a]).magnitude;
                            float world = toWorld.MultiplyVector(vertices[b] - vertices[a]).magnitude;
                            if (uv > 1e-6f && world > 1e-6f)
                            {
                                ratios.Add(world / uv);
                            }
                        }
                    }
                    if (ratios.Count > 0)
                    {
                        ratios.Sort();
                        result = ratios[ratios.Count / 2];
                    }
                }
                DensityCache[(mesh.GetInstanceID(), slot, scale)] = result;
            }
        }

        public static Material Unlit(Color color)
        {
            Color32 key = color;
            if (UnlitCache.TryGetValue(key, out Material cached) && cached != null)
            {
                return cached;
            }
            var m = new Material(FindUnlit()) { name = "Unlit " + ColorUtility.ToHtmlStringRGB(color), enableInstancing = true };
            m.SetColor("_BaseColor", color);
            m.hideFlags = HideFlags.DontUnloadUnusedAsset;
            UnlitCache[key] = m;
            return m;
        }

        /// <summary>Alpha blended, double sided, no depth write: the floor vision cone.</summary>
        public static Material UnlitTransparent(Color color)
        {
            Color32 key = color;
            if (TransparentCache.TryGetValue(key, out Material cached) && cached != null)
            {
                return cached;
            }
            var m = new Material(FindUnlit()) { name = "Transparent " + ColorUtility.ToHtmlStringRGBA(color) };
            m.SetFloat("_Surface", 1f);
            m.SetFloat("_Blend", 0f);
            m.SetFloat("_Cull", (float)CullMode.Off);
            m.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            m.SetFloat("_DstBlend", (float)BlendMode.OneMinusSrcAlpha);
            m.SetFloat("_SrcBlendAlpha", (float)BlendMode.One);
            m.SetFloat("_DstBlendAlpha", (float)BlendMode.OneMinusSrcAlpha);
            m.SetFloat("_ZWrite", 0f);
            m.SetOverrideTag("RenderType", "Transparent");
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            m.renderQueue = (int)RenderQueue.Transparent;
            m.SetColor("_BaseColor", color);
            m.hideFlags = HideFlags.DontUnloadUnusedAsset;
            TransparentCache[key] = m;
            return m;
        }

        /// <summary>
        /// M3: an unlit material whose colour is <paramref name="color"/> (sRGB) times <paramref name="intensity"/>,
        /// so it can rise above 1 and feed the bloom (the window pane). Cached by colour and intensity only (as
        /// <see cref="Lit(Color, float, float)"/>: a caller asking for a smoothness or a metallic already cached gets
        /// the cached material; deliberate reuse keeps the level under its material cap). Harmless for the shader is
        /// Unlit (no lighting, so smoothness and metallic never render), but still read back exactly by a probe.
        /// </summary>
        public static Material Emissive(Color color, float intensity)
        {
            return Emissive(color, intensity, 0f, 0f);
        }

        /// <summary>
        /// <see cref="Emissive(Color, float)"/>, carrying its own smoothness and metallic (M6, CONTRACT_M6 2.4: the
        /// window pane, smoothness 0.95, no texture). The window is always built before any robot that might reuse its
        /// colour (LevelBuilder.Build builds the walls, so every window, before BuildRobots), so it always sets the
        /// shared material first.
        /// </summary>
        public static Material Emissive(Color color, float intensity, float smoothness, float metallic)
        {
            string key = ColorUtility.ToHtmlStringRGB(color) + "x" + intensity.ToString("0.###", System.Globalization.CultureInfo.InvariantCulture);
            if (EmissiveCache.TryGetValue(key, out Material cached) && cached != null)
            {
                return cached;
            }
            var m = new Material(FindUnlit()) { name = "Emissive " + key, enableInstancing = true };
            m.SetColor("_BaseColor", new Color(color.r * intensity, color.g * intensity, color.b * intensity, 1f));
            m.SetFloat("_Smoothness", smoothness);
            m.SetFloat("_Metallic", metallic);
            m.hideFlags = HideFlags.DontUnloadUnusedAsset;
            EmissiveCache[key] = m;
            return m;
        }

        private static readonly Dictionary<string, Material> EmissiveCache = new Dictionary<string, Material>();

        private static Shader FindUnlit()
        {
            Shader shader = Shader.Find(UnlitShaderName);
            if (shader == null)
            {
                Debug.LogError("[PrimitiveKit] URP Unlit shader not found (is it in Always Included Shaders?)");
                shader = Shader.Find("Hidden/InternalErrorShader");
            }
            return shader;
        }

        /// <summary>Number of distinct materials created so far (budget check, PRD 7.4).</summary>
        public static int MaterialCount =>
            LitCache.Count + UnlitCache.Count + TransparentCache.Count + EmissiveCache.Count + SurfaceCache.Count
            + ColourCache.Count + PlayerCache.Count;

        // ----- Meshes (unit size, scaled by the transform) -----

        /// <summary>Unit cube centered on the origin: 24 vertices, 12 triangles.</summary>
        public static Mesh BoxMesh
        {
            get
            {
                if (MeshCache.TryGetValue("box", out Mesh cached) && cached != null)
                {
                    return cached;
                }
                Mesh mesh = BuildBox();
                MeshCache["box"] = mesh;
                return mesh;
            }
        }

        /// <summary>Unit quad in the xy plane, front face toward -z (Unity's built in quad orientation).</summary>
        public static Mesh QuadMesh
        {
            get
            {
                if (MeshCache.TryGetValue("quad", out Mesh cached) && cached != null)
                {
                    return cached;
                }
                var mesh = new Mesh { name = "Quad" };
                mesh.vertices = new[]
                {
                    new Vector3(-0.5f, -0.5f, 0f), new Vector3(-0.5f, 0.5f, 0f),
                    new Vector3(0.5f, 0.5f, 0f), new Vector3(0.5f, -0.5f, 0f),
                };
                mesh.normals = new[] { Vector3.back, Vector3.back, Vector3.back, Vector3.back };
                mesh.uv = new[] { new Vector2(0, 0), new Vector2(0, 1), new Vector2(1, 1), new Vector2(1, 0) };
                mesh.triangles = new[] { 0, 1, 2, 0, 2, 3 };
                mesh.RecalculateBounds();
                Keep(mesh);
                MeshCache["quad"] = mesh;
                return mesh;
            }
        }

        /// <summary>
        /// M4.2: the unit box (24 vertices, 12 triangles, scaled by its transform like <see cref="BoxMesh"/>) with UVs in
        /// metres for a box of <paramref name="size"/>: on each face the texture's V runs along the face's longer side
        /// (wood grain along a leg, a shelf, a plank). Same vertices as the unit box, so a BoxCollider added next to it
        /// keeps its size. Cached by size.
        /// </summary>
        public static Mesh BoxMeshSized(Vector3 size)
        {
            string key = "box" + SizeKey(size);
            if (MeshCache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Mesh unit = BoxMesh;
            Vector3[] vertices = unit.vertices;
            Vector3[] normals = unit.normals;
            var mesh = new Mesh { name = "Box" };
            mesh.vertices = vertices;
            mesh.normals = normals;
            mesh.uv = BoxUvs(vertices, normals, size, Vector3.zero);
            mesh.triangles = unit.triangles;
            mesh.RecalculateBounds();
            Keep(mesh);
            MeshCache[key] = mesh;
            return mesh;
        }

        /// <summary>
        /// M4.2: the unit quad of <see cref="QuadMesh"/> (scaled by its transform to <paramref name="size"/>) with UVs in
        /// metres, V along the longer side. Cached by size.
        /// </summary>
        public static Mesh QuadMeshSized(Vector2 size)
        {
            string key = "quad" + SizeKey(new Vector3(size.x, size.y, 0f));
            if (MeshCache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Mesh unit = QuadMesh;
            Vector3[] vertices = unit.vertices;
            var uv = new Vector2[vertices.Length];
            bool swap = size.x > size.y;
            for (int i = 0; i < vertices.Length; i++)
            {
                float x = (vertices[i].x + 0.5f) * size.x;
                float y = (vertices[i].y + 0.5f) * size.y;
                uv[i] = swap ? new Vector2(y, x) : new Vector2(x, y);
            }
            var mesh = new Mesh { name = "Quad" };
            mesh.vertices = vertices;
            mesh.normals = unit.normals;
            mesh.uv = uv;
            mesh.triangles = unit.triangles;
            mesh.RecalculateBounds();
            Keep(mesh);
            MeshCache[key] = mesh;
            return mesh;
        }

        // Rug nine-slice (product owner, 2026-11-19): rug_modern_inset_border.png's own border, measured once on the
        // 1536x1024 source (a sharp cream-to-content brightness edge found on dozens of scan lines per side, median
        // taken): left 93px, right 93px, bottom 96px, top 103px.
        private const float RugImageWidthPx = 1536f;
        private const float RugImageHeightPx = 1024f;
        private const float RugBorderLeftPx = 93f;
        private const float RugBorderRightPx = 93f;
        private const float RugBorderBottomPx = 96f;
        private const float RugBorderTopPx = 103f;

        /// <summary>
        /// M7 rug image, nine-slice (product owner, 2026-11-19): a 4x4 grid (9 quads, one mesh, one renderer) over the
        /// unit quad <see cref="QuadMesh"/> occupies (-0.5 to 0.5, scaled by the transform to <paramref name="size"/>
        /// exactly like the single quad it replaces), so <see cref="RugDetail"/>'s picture nine-slices instead of
        /// stretching in one piece: the four corners keep the image's own border pixels (<see cref="RugBorderLeftPx"/>
        /// and siblings) at their own undistorted ratio (never stretched, the same single local <c>scale</c>
        /// applies to both axes), the four edge quads stretch only along their own length, and
        /// the centre quad fills whatever is left (stretched: the field is not a repeatable pattern, so tiling it
        /// would show a seam). <c>scale</c> is <c>min(size.x / 1536, size.y / 1024)</c>: on a rug whose
        /// aspect is the image's own (1.5), this is exactly <c>size.x / 1536 == size.y / 1024</c>, so every one of
        /// the nine quads is an undistorted piece of the plain stretched quad and the result is pixel identical to it
        /// (CONTRACT: "a 1.5:1 rug looks exactly as today"); on any other aspect it is the tighter axis's own scale,
        /// so corners never grow past half of either side. UVs keep <see cref="QuadMesh"/>'s own axes (U along x,
        /// V along y, no swap: unlike <see cref="QuadMeshSized"/>, the rug's picture never rotates with the rug's own
        /// proportions). Cached by size.
        /// </summary>
        public static Mesh RugNineSliceMesh(Vector2 size)
        {
            string key = "rug9" + SizeKey(new Vector3(size.x, size.y, 0f));
            if (MeshCache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            float scale = Mathf.Min(size.x / RugImageWidthPx, size.y / RugImageHeightPx);
            float left = Mathf.Clamp01(RugBorderLeftPx * scale / size.x);
            float right = Mathf.Clamp01(RugBorderRightPx * scale / size.x);
            float bottom = Mathf.Clamp01(RugBorderBottomPx * scale / size.y);
            float top = Mathf.Clamp01(RugBorderTopPx * scale / size.y);
            if (left + right > 1f)
            {
                float sum = left + right;
                left /= sum;
                right /= sum;
            }
            if (bottom + top > 1f)
            {
                float sum = bottom + top;
                bottom /= sum;
                top /= sum;
            }
            float[] xs = { -0.5f, -0.5f + left, 0.5f - right, 0.5f };
            float[] ys = { -0.5f, -0.5f + bottom, 0.5f - top, 0.5f };
            float[] us = { 0f, RugBorderLeftPx / RugImageWidthPx, 1f - RugBorderRightPx / RugImageWidthPx, 1f };
            float[] vs = { 0f, RugBorderBottomPx / RugImageHeightPx, 1f - RugBorderTopPx / RugImageHeightPx, 1f };
            var vertices = new Vector3[16];
            var uv = new Vector2[16];
            var normals = new Vector3[16];
            for (int row = 0; row < 4; row++)
            {
                for (int col = 0; col < 4; col++)
                {
                    int i = row * 4 + col;
                    vertices[i] = new Vector3(xs[col], ys[row], 0f);
                    uv[i] = new Vector2(us[col], vs[row]);
                    normals[i] = Vector3.back;
                }
            }
            var triangles = new int[9 * 6];
            int t = 0;
            for (int row = 0; row < 3; row++)
            {
                for (int col = 0; col < 3; col++)
                {
                    int a = row * 4 + col;
                    int b = a + 1;
                    int c = a + 4;
                    int d = c + 1;
                    triangles[t++] = a;
                    triangles[t++] = c;
                    triangles[t++] = d;
                    triangles[t++] = a;
                    triangles[t++] = d;
                    triangles[t++] = b;
                }
            }
            var mesh = new Mesh { name = "RugNineSlice" };
            mesh.vertices = vertices;
            mesh.normals = normals;
            mesh.uv = uv;
            mesh.triangles = triangles;
            mesh.RecalculateBounds();
            Keep(mesh);
            MeshCache[key] = mesh;
            return mesh;
        }

        /// <summary>
        /// Wall finishes (2026-11-19): a wall face's quad, as <see cref="QuadMeshSized"/> (the unit quad scaled by its
        /// transform to <paramref name="size"/>, UVs in metres, named "Quad") but always U along the wall and V up, whatever
        /// side is longer (a wallpaper's stripes and a grasscloth's fibres must not turn with the face's proportions), and
        /// shifted by <paramref name="uvOffset"/> metres so the pieces of one wall (beside and over a door) continue one
        /// pattern. Cached by size and offset.
        /// </summary>
        public static Mesh WallQuadMesh(Vector2 size, Vector2 uvOffset)
        {
            string key = "wall quad" + SizeKey(new Vector3(size.x, size.y, 0f)) + "+" + SizeKey(new Vector3(uvOffset.x, uvOffset.y, 0f));
            if (MeshCache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Mesh unit = QuadMesh;
            Vector3[] vertices = unit.vertices;
            var uv = new Vector2[vertices.Length];
            for (int i = 0; i < vertices.Length; i++)
            {
                uv[i] = new Vector2((vertices[i].x + 0.5f) * size.x + uvOffset.x, (vertices[i].y + 0.5f) * size.y + uvOffset.y);
            }
            var mesh = new Mesh { name = "Quad" };
            mesh.vertices = vertices;
            mesh.normals = unit.normals;
            mesh.uv = uv;
            mesh.triangles = unit.triangles;
            mesh.RecalculateBounds();
            Keep(mesh);
            MeshCache[key] = mesh;
            return mesh;
        }

        private static string SizeKey(Vector3 size)
        {
            System.Globalization.CultureInfo c = System.Globalization.CultureInfo.InvariantCulture;
            return size.x.ToString("0.####", c) + "x" + size.y.ToString("0.####", c) + "x" + size.z.ToString("0.####", c);
        }

        /// <summary>
        /// M4.2: UVs in metres for the vertices of a unit box (each normal is a face's), as the box of
        /// <paramref name="size"/> they are scaled to: each face projects on its own plane, V along its longer side
        /// (the vertical on a square side face). <paramref name="offset"/> is added to the metric position (merged boxes
        /// keep their place in the mesh, so neighbours do not all start the pattern at the same point).
        /// </summary>
        private static Vector2[] BoxUvs(Vector3[] unitVertices, Vector3[] normals, Vector3 size, Vector3 offset)
        {
            var uv = new Vector2[unitVertices.Length];
            for (int i = 0; i < unitVertices.Length; i++)
            {
                Vector3 p = Vector3.Scale(unitVertices[i], size) + offset;
                Vector3 n = normals[i];
                // The two axes of the face plane: (u axis, v axis) with v the vertical on a side face.
                int a;
                int b;
                if (Mathf.Abs(n.y) > 0.5f)
                {
                    a = 0;
                    b = 2;
                }
                else if (Mathf.Abs(n.x) > 0.5f)
                {
                    a = 2;
                    b = 1;
                }
                else
                {
                    a = 0;
                    b = 1;
                }
                if (size[a] > size[b])
                {
                    (a, b) = (b, a);
                }
                uv[i] = new Vector2(p[a], p[b]);
            }
            return uv;
        }

        /// <summary>
        /// M3.1: one mesh made of axis aligned boxes (each a centre and a size in the mesh frame), so many static decor
        /// boxes draw as one renderer. Cached by geometry: a rebuilt level reuses its meshes instead of leaking new ones.
        /// M4.2: with UVs in metres (<see cref="BoxUvs"/>).
        /// </summary>
        public static Mesh BoxesMesh(IList<Bounds> boxes)
        {
            var key = new System.Text.StringBuilder("boxes");
            System.Globalization.CultureInfo c = System.Globalization.CultureInfo.InvariantCulture;
            foreach (Bounds b in boxes)
            {
                key.Append('|').Append(b.center.x.ToString("0.####", c)).Append(',').Append(b.center.y.ToString("0.####", c))
                    .Append(',').Append(b.center.z.ToString("0.####", c)).Append(',').Append(b.size.x.ToString("0.####", c))
                    .Append(',').Append(b.size.y.ToString("0.####", c)).Append(',').Append(b.size.z.ToString("0.####", c));
            }
            string k = key.ToString();
            if (MeshCache.TryGetValue(k, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Mesh unit = BoxMesh;
            Vector3[] unitVertices = unit.vertices;
            Vector3[] unitNormals = unit.normals;
            int[] unitTriangles = unit.triangles;
            var vertices = new List<Vector3>(unitVertices.Length * boxes.Count);
            var normals = new List<Vector3>(unitVertices.Length * boxes.Count);
            var uvs = new List<Vector2>(unitVertices.Length * boxes.Count);
            var triangles = new List<int>(unitTriangles.Length * boxes.Count);
            foreach (Bounds b in boxes)
            {
                int start = vertices.Count;
                for (int i = 0; i < unitVertices.Length; i++)
                {
                    // A positive per axis scale keeps both the winding and the face normals of a box.
                    vertices.Add(b.center + Vector3.Scale(unitVertices[i], b.size));
                    normals.Add(unitNormals[i]);
                }
                uvs.AddRange(BoxUvs(unitVertices, unitNormals, b.size, b.center));
                foreach (int t in unitTriangles)
                {
                    triangles.Add(start + t);
                }
            }
            var mesh = new Mesh { name = "Boxes" };
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            Keep(mesh);
            MeshCache[k] = mesh;
            return mesh;
        }

        /// <summary>
        /// M5 (docs/CONTRACT_M5_v3.md 15.4): a ramp wedge in its own frame: <paramref name="width"/> across x, centred,
        /// <paramref name="length"/> along z from its foot (z = -length / 2, y = 0) to its head (z = +length / 2, top at
        /// <paramref name="height"/>), resting on y = 0: the sloped top, the vertical head face, the bottom and two side
        /// triangles, with UVs in metres. Convex: a MeshCollider takes it as is. Cached by size.
        /// </summary>
        public static Mesh WedgeMesh(float width, float length, float height)
        {
            string key = "wedge" + SizeKey(new Vector3(width, height, length));
            if (MeshCache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            float hw = width * 0.5f;
            float hl = length * 0.5f;
            float slope = Mathf.Sqrt(length * length + height * height);
            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var uvs = new List<Vector2>();
            var triangles = new List<int>();
            void Quad(Vector3 a, Vector3 b, Vector3 c, Vector3 d, Vector3 n, Vector2 ua, Vector2 ub, Vector2 uc, Vector2 ud)
            {
                int s = vertices.Count;
                vertices.AddRange(new[] { a, b, c, d });
                normals.AddRange(new[] { n, n, n, n });
                uvs.AddRange(new[] { ua, ub, uc, ud });
                triangles.AddRange(new[] { s, s + 1, s + 2, s, s + 2, s + 3 });
            }
            void Triangle(Vector3 a, Vector3 b, Vector3 c, Vector3 n, Vector2 ua, Vector2 ub, Vector2 uc)
            {
                int s = vertices.Count;
                vertices.AddRange(new[] { a, b, c });
                normals.AddRange(new[] { n, n, n });
                uvs.AddRange(new[] { ua, ub, uc });
                triangles.AddRange(new[] { s, s + 1, s + 2 });
            }
            // The slope: U across, V up the slope (its length in metres).
            Vector3 up = new Vector3(0f, length, -height).normalized;
            Quad(new Vector3(-hw, 0f, -hl), new Vector3(hw, 0f, -hl), new Vector3(hw, height, hl), new Vector3(-hw, height, hl), up,
                new Vector2(-hw, 0f), new Vector2(hw, 0f), new Vector2(hw, slope), new Vector2(-hw, slope));
            // The head face, the bottom.
            Quad(new Vector3(-hw, 0f, hl), new Vector3(hw, 0f, hl), new Vector3(hw, height, hl), new Vector3(-hw, height, hl), Vector3.forward,
                new Vector2(-hw, 0f), new Vector2(hw, 0f), new Vector2(hw, height), new Vector2(-hw, height));
            Quad(new Vector3(-hw, 0f, -hl), new Vector3(hw, 0f, -hl), new Vector3(hw, 0f, hl), new Vector3(-hw, 0f, hl), Vector3.down,
                new Vector2(-hw, -hl), new Vector2(hw, -hl), new Vector2(hw, hl), new Vector2(-hw, hl));
            // The sides.
            foreach (float side in new[] { -1f, 1f })
            {
                float x = side * hw;
                Triangle(new Vector3(x, 0f, -hl), new Vector3(x, 0f, hl), new Vector3(x, height, hl), Vector3.right * side,
                    new Vector2(-hl, 0f), new Vector2(hl, 0f), new Vector2(hl, height));
            }
            var mesh = new Mesh { name = "Wedge" };
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            FixWinding(mesh);
            Keep(mesh);
            MeshCache[key] = mesh;
            return mesh;
        }

        /// <summary>One mesh placed in a common frame, for <see cref="CombinedMesh"/>.</summary>
        public struct CombinePart
        {
            public Mesh Mesh;
            /// <summary>From the part's mesh to the combined mesh's frame.</summary>
            public Matrix4x4 Matrix;
        }

        /// <summary>
        /// M5 (docs/CONTRACT_M5_v3.md 15.8): many static meshes as one, each placed by its matrix (positions, normals by the
        /// inverse transpose, the winding flipped under a mirroring matrix), keeping their UV0. Every PrimitiveKit mesh
        /// carries UVs in metres of its size, and a part's matrix is its size scale, so the combined UVs stay in metres
        /// and a combined renderer's detail repeats at its tile. Named "Boxes", as <see cref="BoxesMesh"/>: static decor in
        /// metres. Cached by its parts (mesh and matrix): a rebuilt level reuses its meshes instead of leaking new ones.
        /// </summary>
        public static Mesh CombinedMesh(IList<CombinePart> parts)
        {
            var key = new System.Text.StringBuilder("combined");
            System.Globalization.CultureInfo c = System.Globalization.CultureInfo.InvariantCulture;
            foreach (CombinePart part in parts)
            {
                key.Append('|').Append(part.Mesh.GetInstanceID());
                for (int i = 0; i < 12; i++)
                {
                    key.Append(',').Append(part.Matrix[i % 3, i / 3].ToString("0.####", c));
                }
            }
            string k = key.ToString();
            if (MeshCache.TryGetValue(k, out Mesh cached) && cached != null)
            {
                return cached;
            }
            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var uvs = new List<Vector2>();
            var triangles = new List<int>();
            var partUvs = new List<Vector2>();
            // Walls 4 (docs/m9/FLOORS_WALLS.md section 7): a wall part names its finish per vertex (WallArray.Tag, UV1 and
            // UV2); kept, so the faces of several finishes combine into one renderer of the one wall material.
            bool tagged = false;
            foreach (CombinePart part in parts)
            {
                tagged |= part.Mesh.HasVertexAttribute(VertexAttribute.TexCoord1);
            }
            List<Vector4> finishes = tagged ? new List<Vector4>() : null;
            List<Vector4> bands = tagged ? new List<Vector4>() : null;
            var partFinishes = new List<Vector4>();
            var partBands = new List<Vector4>();
            foreach (CombinePart part in parts)
            {
                Mesh m = part.Mesh;
                int start = vertices.Count;
                Matrix4x4 normalMatrix = part.Matrix.inverse.transpose;
                Vector3[] v = m.vertices;
                Vector3[] n = m.normals;
                partUvs.Clear();
                m.GetUVs(0, partUvs);
                partFinishes.Clear();
                partBands.Clear();
                if (tagged)
                {
                    m.GetUVs(WallArray.FinishChannel, partFinishes);
                    m.GetUVs(WallArray.BandChannel, partBands);
                }
                for (int i = 0; i < v.Length; i++)
                {
                    vertices.Add(part.Matrix.MultiplyPoint3x4(v[i]));
                    normals.Add(i < n.Length ? normalMatrix.MultiplyVector(n[i]).normalized : Vector3.up);
                    uvs.Add(i < partUvs.Count ? partUvs[i] : Vector2.zero);
                    if (tagged)
                    {
                        finishes.Add(i < partFinishes.Count ? partFinishes[i] : Vector4.zero);
                        bands.Add(i < partBands.Count ? partBands[i] : Vector4.zero);
                    }
                }
                bool mirrored = part.Matrix.determinant < 0f;
                for (int sub = 0; sub < m.subMeshCount; sub++)
                {
                    int[] t = m.GetTriangles(sub);
                    for (int i = 0; i + 2 < t.Length; i += 3)
                    {
                        triangles.Add(start + t[i]);
                        triangles.Add(start + (mirrored ? t[i + 2] : t[i + 1]));
                        triangles.Add(start + (mirrored ? t[i + 1] : t[i + 2]));
                    }
                }
            }
            var mesh = new Mesh { name = "Boxes" };
            if (vertices.Count > 65000)
            {
                mesh.indexFormat = IndexFormat.UInt32;
            }
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetUVs(0, uvs);
            if (tagged)
            {
                mesh.SetUVs(WallArray.FinishChannel, finishes);
                mesh.SetUVs(WallArray.BandChannel, bands);
            }
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            Keep(mesh);
            MeshCache[k] = mesh;
            return mesh;
        }

        /// <summary>UV sphere of unit diameter.</summary>
        public static Mesh SphereMesh(int segments, int rings)
        {
            string key = $"sphere{segments}x{rings}";
            if (MeshCache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Mesh mesh = BuildCapsule(0.5f, 1f, segments, rings);
            mesh.name = "Sphere";
            MeshCache[key] = mesh;
            return mesh;
        }

        /// <summary>Capsule of the given radius and total height, resting on y = 0.</summary>
        public static Mesh CapsuleMesh(float radius, float height, int segments, int capRings)
        {
            string key = $"capsule{radius:0.###}x{height:0.###}x{segments}x{capRings}";
            if (MeshCache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Mesh mesh = BuildCapsule(radius, height, segments, capRings * 2);
            // Rest the capsule on the floor instead of centering it.
            Vector3[] v = mesh.vertices;
            for (int i = 0; i < v.Length; i++)
            {
                v[i].y += height * 0.5f;
            }
            mesh.vertices = v;
            mesh.RecalculateBounds();
            mesh.name = "Capsule";
            MeshCache[key] = mesh;
            return mesh;
        }

        private static Mesh BuildBox()
        {
            var vertices = new List<Vector3>(24);
            var normals = new List<Vector3>(24);
            var triangles = new List<int>(36);
            Vector3[] faceNormals = { Vector3.right, Vector3.left, Vector3.up, Vector3.down, Vector3.forward, Vector3.back };
            foreach (Vector3 n in faceNormals)
            {
                // Two axes spanning the face, chosen so the winding is clockwise seen from outside.
                Vector3 u = n.y != 0f ? Vector3.right : Vector3.up;
                Vector3 w = Vector3.Cross(n, u);
                int start = vertices.Count;
                Vector3 c = n * 0.5f;
                vertices.Add(c - u * 0.5f - w * 0.5f);
                vertices.Add(c + u * 0.5f - w * 0.5f);
                vertices.Add(c + u * 0.5f + w * 0.5f);
                vertices.Add(c - u * 0.5f + w * 0.5f);
                for (int i = 0; i < 4; i++)
                {
                    normals.Add(n);
                }
                triangles.AddRange(new[] { start, start + 1, start + 2, start, start + 2, start + 3 });
            }
            var mesh = new Mesh { name = "Box" };
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            // M4.2: UVs in metres for a 1 m cube (BoxMeshSized carries them for any size).
            mesh.uv = BoxUvs(vertices.ToArray(), normals.ToArray(), Vector3.one, Vector3.zero);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            FixWinding(mesh);
            Keep(mesh);
            return mesh;
        }

        /// <summary>Flips any triangle whose geometric normal disagrees with its vertex normal.</summary>
        private static void FixWinding(Mesh mesh)
        {
            Vector3[] v = mesh.vertices;
            Vector3[] n = mesh.normals;
            int[] t = mesh.triangles;
            for (int i = 0; i < t.Length; i += 3)
            {
                Vector3 face = Vector3.Cross(v[t[i + 1]] - v[t[i]], v[t[i + 2]] - v[t[i]]);
                if (Vector3.Dot(face, n[t[i]]) < 0f)
                {
                    (t[i + 1], t[i + 2]) = (t[i + 2], t[i + 1]);
                }
            }
            mesh.triangles = t;
        }

        /// <summary>
        /// Capsule (or sphere when height == 2 * radius) centered on the origin, axis along y.
        /// <paramref name="rings"/> is the number of latitude bands over both caps together.
        /// </summary>
        private static Mesh BuildCapsule(float radius, float height, int segments, int rings)
        {
            rings = Mathf.Max(2, rings + (rings % 2));
            float half = Mathf.Max(0f, height * 0.5f - radius);
            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var uvs = new List<Vector2>();
            var triangles = new List<int>();
            // Latitudes from the north pole to the south pole. The equator is duplicated to open the cylinder.
            var latitudes = new List<(float angle, float offset)>();
            for (int r = 0; r <= rings / 2; r++)
            {
                latitudes.Add((Mathf.PI * 0.5f - Mathf.PI * 0.5f * r / (rings / 2), half));
            }
            for (int r = 0; r <= rings / 2; r++)
            {
                latitudes.Add((-Mathf.PI * 0.5f * r / (rings / 2), -half));
            }
            for (int l = 0; l < latitudes.Count; l++)
            {
                (float phi, float offset) = latitudes[l];
                for (int s = 0; s <= segments; s++)
                {
                    float theta = 2f * Mathf.PI * s / segments;
                    var n = new Vector3(Mathf.Cos(phi) * Mathf.Sin(theta), Mathf.Sin(phi), Mathf.Cos(phi) * Mathf.Cos(theta));
                    Vector3 v = n * radius + new Vector3(0f, offset, 0f);
                    vertices.Add(v);
                    normals.Add(n);
                    // M4.2: cylindrical UVs in mesh units, the arc length around and the height along.
                    uvs.Add(new Vector2(theta * radius, v.y));
                }
            }
            int stride = segments + 1;
            for (int l = 0; l < latitudes.Count - 1; l++)
            {
                for (int s = 0; s < segments; s++)
                {
                    int a = l * stride + s;
                    int b = a + 1;
                    int c = a + stride;
                    int d = c + 1;
                    // Skip the degenerate triangles at the poles and in a zero height cylinder band.
                    if (Area(vertices[a], vertices[b], vertices[c]) > 1e-10f)
                    {
                        triangles.AddRange(new[] { a, b, c });
                    }
                    if (Area(vertices[b], vertices[d], vertices[c]) > 1e-10f)
                    {
                        triangles.AddRange(new[] { b, d, c });
                    }
                }
            }
            var mesh = new Mesh { name = "Capsule" };
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            FixWinding(mesh);
            Keep(mesh);
            return mesh;
        }

        private static float Area(Vector3 a, Vector3 b, Vector3 c)
        {
            return Vector3.Cross(b - a, c - a).sqrMagnitude;
        }

        private static void Keep(Object o)
        {
            o.hideFlags = HideFlags.DontUnloadUnusedAsset;
        }

        // ----- Object helpers -----

        public static GameObject Group(Transform parent, string name, Vector3 localPosition, float yawDeg = 0f)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.transform.localPosition = localPosition;
            go.transform.localRotation = Quaternion.Euler(0f, yawDeg, 0f);
            if (parent != null)
            {
                go.layer = parent.gameObject.layer;
            }
            return go;
        }

        /// <summary>
        /// A box of <paramref name="size"/> whose center sits at <paramref name="localCenter"/>. M4.2: its mesh is the unit
        /// box with UVs in metres for that size (<see cref="BoxMeshSized"/>); it shows no detail (Plain).
        /// </summary>
        public static GameObject Box(Transform parent, string name, Vector3 localCenter, Vector3 size, Material material,
            int layer, bool collider)
        {
            GameObject go = Part(parent, name, BoxMeshSized(size), localCenter, Quaternion.identity, size, material, layer);
            if (collider)
            {
                go.AddComponent<BoxCollider>();
            }
            return go;
        }

        /// <summary>M4.2: <see cref="Box(Transform, string, Vector3, Vector3, Material, int, bool)"/> showing <paramref name="surface"/>.</summary>
        public static GameObject Box(Transform parent, string name, Vector3 localCenter, Vector3 size, Material material,
            int layer, bool collider, Surface surface)
        {
            GameObject go = Box(parent, name, localCenter, size, material, layer, collider);
            Detail(go.GetComponent<MeshRenderer>(), surface);
            return go;
        }

        /// <summary>M4.2: <see cref="Box(Transform, string, Vector3, Vector3, Material, int, bool, bool)"/> showing <paramref name="surface"/> when drawn.</summary>
        public static GameObject Box(Transform parent, string name, Vector3 localCenter, Vector3 size, Material material,
            int layer, bool collider, bool visual, Surface surface)
        {
            GameObject go = Box(parent, name, localCenter, size, material, layer, collider, visual);
            if (visual && go != null)
            {
                Detail(go.GetComponent<MeshRenderer>(), surface);
            }
            return go;
        }

        /// <summary>
        /// M3 (docs/CONTRACT_M3.md 1): with <paramref name="visual"/> false, a box that carried a collider is built
        /// as a collider-only GameObject (same name, transform, scale, layer and BoxCollider, but no MeshFilter and
        /// no MeshRenderer: the budget counters walk MeshFilters), and a box without a collider is not built at all
        /// (returns null). With <paramref name="visual"/> true this is <see cref="Box(Transform, string, Vector3, Vector3, Material, int, bool)"/>.
        /// </summary>
        public static GameObject Box(Transform parent, string name, Vector3 localCenter, Vector3 size, Material material,
            int layer, bool collider, bool visual)
        {
            if (visual)
            {
                return Box(parent, name, localCenter, size, material, layer, collider);
            }
            if (!collider)
            {
                return null;
            }
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            go.transform.localPosition = localCenter;
            go.transform.localRotation = Quaternion.identity;
            go.transform.localScale = size;
            go.AddComponent<BoxCollider>();
            return go;
        }

        public static GameObject Part(Transform parent, string name, Mesh mesh, Vector3 localPosition, Quaternion localRotation,
            Vector3 localScale, Material material, int layer)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            go.transform.localPosition = localPosition;
            go.transform.localRotation = localRotation;
            go.transform.localScale = localScale;
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = go.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = material;
            renderer.shadowCastingMode = ShadowCastingMode.On;
            renderer.receiveShadows = true;
            return go;
        }

        /// <summary>M4.2: <see cref="Part(Transform, string, Mesh, Vector3, Quaternion, Vector3, Material, int)"/> showing <paramref name="surface"/>.</summary>
        public static GameObject Part(Transform parent, string name, Mesh mesh, Vector3 localPosition, Quaternion localRotation,
            Vector3 localScale, Material material, int layer, Surface surface)
        {
            GameObject go = Part(parent, name, mesh, localPosition, localRotation, localScale, material, layer);
            Detail(go.GetComponent<MeshRenderer>(), surface);
            return go;
        }
    }
}
