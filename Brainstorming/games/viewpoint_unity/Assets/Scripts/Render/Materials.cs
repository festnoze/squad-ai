using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// Material factory with a cache (PRD 14.2), so every box of the same color
    /// and emission shares one material. Nothing in the game builds a material
    /// by hand: the palette is the only source of color.
    /// </summary>
    public static class Materials
    {
        // PRD 14.2: the original sets Godot roughness 0.85, which is smoothness
        // 0.15 for a URP Lit material.
        private const float SolidSmoothness = 0.15f;
        private const float SolidMetallic = 0f;

        // 4 x 64 vertical ramp, the size used by the original. Four pixels wide
        // because a one pixel wide texture is awkward to inspect and costs the
        // same in practice.
        private const int GradientWidth = 4;
        private const int GradientHeight = 64;

        private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        private static readonly int BaseMapId = Shader.PropertyToID("_BaseMap");
        private static readonly int SmoothnessId = Shader.PropertyToID("_Smoothness");
        private static readonly int MetallicId = Shader.PropertyToID("_Metallic");
        private static readonly int EmissionColorId = Shader.PropertyToID("_EmissionColor");

        private static readonly Dictionary<string, Material> Cache = new Dictionary<string, Material>();

        private static Shader _litShader;
        private static Shader _unlitShader;

        /// <summary>
        /// Lit material for a palette key, cached per (key, emissive).
        /// <paramref name="emissive"/> is the Godot emission energy multiplier:
        /// the emission color is the base color scaled by it.
        /// </summary>
        public static Material Solid(string key, float emissive = 0f)
        {
            string cacheKey = "s:" + key + ":" + Round2(emissive);
            Material cached;
            if (Cache.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            Color color = Palette.Get(key);
            Material material = new Material(LitShader());
            material.name = emissive > 0f
                ? "Solid_" + key + "_e" + Round2(emissive)
                : "Solid_" + key;
            material.SetColor(BaseColorId, color);
            material.SetFloat(SmoothnessId, SolidSmoothness);
            material.SetFloat(MetallicId, SolidMetallic);

            if (emissive > 0f)
            {
                // Alpha stays at 1: an HDR emission color scales rgb only, and a
                // scaled alpha would make the material look transparent to any
                // code that reads the color back.
                material.SetColor(EmissionColorId, new Color(color.r * emissive, color.g * emissive, color.b * emissive, 1f));
                // The keyword is what puts the glow on screen; the flag below
                // only tells the lightmapper how to treat this material, and is
                // the value Unity's own emissive fixup writes when the emission
                // is not baked.
                material.EnableKeyword("_EMISSION");
                material.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
            }
            else
            {
                material.SetColor(EmissionColorId, Color.black);
                material.DisableKeyword("_EMISSION");
                material.globalIlluminationFlags = MaterialGlobalIlluminationFlags.EmissiveIsBlack;
            }

            Cache[cacheKey] = material;
            return material;
        }

        /// <summary>
        /// Unlit material carrying the painted backdrop gradient, cached per
        /// (top, bottom). Both arguments are palette keys, not colors. Unlit on
        /// purpose: a painted sky must not react to the sun, or the illusion of
        /// depth behind the photo breaks.
        /// </summary>
        public static Material Backdrop(string top, string bottom)
        {
            string cacheKey = "b:" + top + ":" + bottom;
            Material cached;
            if (Cache.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            Material material = new Material(UnlitShader());
            material.name = "Backdrop_" + top + "_" + bottom;
            material.SetColor(BaseColorId, Color.white);
            material.SetTexture(BaseMapId, GradientTexture(Palette.Get(top), Palette.Get(bottom)));

            Cache[cacheKey] = material;
            return material;
        }

        /// <summary>
        /// Drops every cached material so the next call rebuilds from the
        /// current palette. Used by the tests. The materials themselves are not
        /// destroyed: a renderer somewhere may still be pointing at one, and a
        /// destroyed material would turn it magenta.
        /// </summary>
        public static void ClearCache()
        {
            Cache.Clear();
        }

        /// <summary>
        /// Vertical ramp used as the backdrop albedo. Unity texture rows go
        /// bottom up, so row 0 is the BOTTOM of the panel and the ramp runs
        /// bottom (v = 0) to top (v = 1). The Godot original filled row 0 with
        /// the TOP color because its images are y down.
        /// </summary>
        private static Texture2D GradientTexture(Color top, Color bottom)
        {
            // linear: false, so the sRGB palette values are stored as authored
            // and the sampler converts them, exactly like a Color on a material.
            Texture2D texture = new Texture2D(GradientWidth, GradientHeight, TextureFormat.RGBA32, false, false);
            texture.name = "BackdropGradient";
            texture.filterMode = FilterMode.Bilinear;
            texture.wrapMode = TextureWrapMode.Clamp;

            Color[] pixels = new Color[GradientWidth * GradientHeight];
            for (int y = 0; y < GradientHeight; y++)
            {
                Color row = Color.Lerp(bottom, top, y / (float)(GradientHeight - 1));
                for (int x = 0; x < GradientWidth; x++)
                {
                    pixels[y * GradientWidth + x] = row;
                }
            }

            texture.SetPixels(pixels);
            // Keep it readable: the unit tests sample the ramp back out.
            texture.Apply(false, false);
            return texture;
        }

        private static Shader LitShader()
        {
            if (_litShader == null)
            {
                _litShader = FindShader("Universal Render Pipeline/Lit");
            }

            return _litShader;
        }

        private static Shader UnlitShader()
        {
            if (_unlitShader == null)
            {
                _unlitShader = FindShader("Universal Render Pipeline/Unlit");
            }

            return _unlitShader;
        }

        private static Shader FindShader(string name)
        {
            Shader shader = Shader.Find(name);
            if (shader == null)
            {
                // A URP project always ships these. A miss means the pipeline
                // package is absent, or the shader was stripped from a build
                // because nothing references it: say so loudly rather than
                // silently drawing the whole game in magenta.
                Debug.LogError("Materials: shader not found: " + name);
            }

            return shader;
        }

        // Invariant culture: a cache key must not change with the machine's
        // decimal separator.
        private static string Round2(float value)
        {
            return value.ToString("F2", CultureInfo.InvariantCulture);
        }
    }
}
