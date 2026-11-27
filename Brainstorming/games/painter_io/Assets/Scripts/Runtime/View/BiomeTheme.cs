// Owned by BI (wave B-2). Contract 25.1 and 25.2: a biome is a complete visual and audio theme for a round (Liquide,
// Feu, Électricité). The rules and the whole Core are identical in every biome; a biome only changes shading, beads,
// overlays, extra effects, palette, fill timing and sounds.
//
// Every view reads BiomeTheme.Current (never a hard-coded shader name or color) and re-binds its materials on
// BiomeTheme.Changed without a restart. GameDirector sets Current when a session starts (GameSession.Biome, else the
// "-biome liquid|fire|electric" command line, else SaveData.Biome) and when a biome card is picked in the menu.
//
// The values of each biome live in their own file (Biomes/LiquidTheme.cs, FireTheme.cs, ElectricTheme.cs, one static
// Create() each), so the biome agents never edit the same file.
//
// Shader resolution with fallback: a biome whose shader is missing from Resources/Shaders (or not supported on the
// device) uses the liquid one instead and logs it once, so every biome is playable at all times.
using System;
using System.Collections.Generic;
using UnityEngine;

namespace PainterIO.Runtime
{
    public enum BiomeId { Liquid = 0, Fire = 1, Electric = 2 }

    public sealed class BiomeTheme
    {
        /// <summary>Number of biomes (BiomeId values 0..Count-1).</summary>
        public const int Count = 3;

        /// <summary>Liquid shader names, the fallback of every biome shader.</summary>
        public const string LiquidCompositeShader = "LiquidComposite";
        public const string LiquidBeadShader = "Bead";
        public const string LiquidOverlayShader = "Overlay";

        public BiomeId Id;

        /// <summary>Strings key of the biome name: biome.liquid / biome.fire / biome.electric.</summary>
        public string NameKey;

        /// <summary>Resources/Shaders name of the composite: "LiquidComposite" | "FireComposite" | "ElectricComposite".</summary>
        public string CompositeShader;

        /// <summary>Resources/Shaders name of the bead impostor: "Bead" | "FireBead" | "ElectricBead".</summary>
        public string BeadShader;

        /// <summary>Resources/Shaders name of the overlay shapes: "Overlay" | "FireOverlay" | "ElectricOverlay".</summary>
        public string OverlayShader;

        /// <summary>4 sRGB colors, index = palette index (Palette.ColorIndexOf still applies).</summary>
        public Color[] PlayerColors;

        /// <summary>
        /// 4 sRGB secondary colors, index = palette index (BI addition): the fire's hot cores, the electric's white-hot
        /// cores, the liquid's highlight tints. Published as _PIO_SecondaryColors (linear, per sim player like _PIO_Colors).
        /// </summary>
        public Color[] SecondaryColors;

        /// <summary>Arena ground, outside the arena (and camera clear color), HUD accent (timer and highlights). sRGB.</summary>
        public Color Ground, OutsideArena, UiAccent;

        /// <summary>Seconds a capture takes to fill in: Liquid 0.35, Fire 0.60, Electric 0.25.</summary>
        public float FillDuration;

        /// <summary>Bloom on the High tier (emissive look): Fire and Electric true, Liquid false (section 12).</summary>
        public bool BloomOnHigh;

        /// <summary>Bloom settings used when BloomOnHigh applies (BI addition; threshold stays >= 1.1 per contract 12.1).</summary>
        public float BloomThreshold = 1.1f, BloomIntensity = 0.8f, BloomScatter = 0.65f;

        /// <summary>Free per-biome shader parameters, published as the _PIO_BiomeParams global (BI addition).</summary>
        public Vector4 ShaderParams;

        /// <summary>Lower-case id used on the command line and in DevShot file names: liquid, fire, electric.</summary>
        public string CommandName => CommandNameOf(Id);

        private static readonly BiomeTheme[] cache = new BiomeTheme[Count];
        private static readonly HashSet<string> fallbackLogged = new HashSet<string>();
        private static BiomeTheme current;

        /// <summary>The theme of the current session (Liquid until GameDirector sets another one). Never null.</summary>
        public static BiomeTheme Current
        {
            get
            {
                if (current == null) current = Get(BiomeId.Liquid);
                return current;
            }
        }

        /// <summary>Raised after Current changed (views re-bind their materials, sounds and colors).</summary>
        public static event Action<BiomeTheme> Changed;

        /// <summary>The (cached) theme of a biome; an unknown id gives Liquid.</summary>
        public static BiomeTheme Get(BiomeId id)
        {
            int k = (int)Clamp((int)id);
            BiomeTheme t = cache[k];
            if (t != null) return t;
            switch ((BiomeId)k)
            {
                case BiomeId.Fire: t = FireTheme.Create(); break;
                case BiomeId.Electric: t = ElectricTheme.Create(); break;
                default: t = LiquidTheme.Create(); break;
            }
            Sanitize(t, (BiomeId)k);
            cache[k] = t;
            return t;
        }

        /// <summary>
        /// Makes id the current biome (BI addition; GameDirector calls it at each session start and on a menu pick, tests
        /// may call it). Raises Changed when the biome actually changes, or always when force is true.
        /// </summary>
        public static void SetCurrent(BiomeId id, bool force = false)
        {
            BiomeTheme next = Get(id);
            if (next == current && !force) return;
            current = next;
            Action<BiomeTheme> handler = Changed;
            if (handler == null) return;
            foreach (Delegate d in handler.GetInvocationList())
            {
                try
                {
                    ((Action<BiomeTheme>)d)(next);
                }
                catch (Exception e)
                {
                    Debug.LogError("[PainterIO] BiomeTheme.Changed subscriber failed: " + e);
                }
            }
        }

        /// <summary>An int (SaveData.Biome) as a valid BiomeId (out of range gives Liquid).</summary>
        public static BiomeId Clamp(int value)
        {
            return value >= 0 && value < Count ? (BiomeId)value : BiomeId.Liquid;
        }

        /// <summary>"liquid" / "fire" / "electric".</summary>
        public static string CommandNameOf(BiomeId id)
        {
            switch (id)
            {
                case BiomeId.Fire: return "fire";
                case BiomeId.Electric: return "electric";
                default: return "liquid";
            }
        }

        /// <summary>
        /// Parses a command-line biome: liquid|fire|electric (also liquide, feu, electricite, elec, water) or 0|1|2,
        /// case-insensitive. Null when the text is not a biome.
        /// </summary>
        public static BiomeId? Parse(string text)
        {
            if (string.IsNullOrEmpty(text)) return null;
            string v = text.Trim().ToLowerInvariant();
            switch (v)
            {
                case "0": case "liquid": case "liquide": case "water": return BiomeId.Liquid;
                case "1": case "fire": case "feu": return BiomeId.Fire;
                case "2": case "electric": case "electricity": case "elec": case "electricite": case "électricité": return BiomeId.Electric;
                default: return null;
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Shader resolution with the liquid fallback.

        /// <summary>The composite shader of this biome, LiquidComposite when missing (logged once).</summary>
        public Shader ResolveComposite()
        {
            return LoadShader(CompositeShader, LiquidCompositeShader);
        }

        /// <summary>The bead shader of this biome, Bead when missing (logged once).</summary>
        public Shader ResolveBead()
        {
            return LoadShader(BeadShader, LiquidBeadShader);
        }

        /// <summary>The overlay shader of this biome, Overlay when missing (logged once).</summary>
        public Shader ResolveOverlay()
        {
            return LoadShader(OverlayShader, LiquidOverlayShader);
        }

        /// <summary>True when Resources/Shaders holds a supported shader of that name (no fallback, no log).</summary>
        public static bool HasShader(string name)
        {
            Shader s = TryLoad(name);
            return s != null && s.isSupported;
        }

        /// <summary>
        /// Resources.Load&lt;Shader&gt;("Shaders/" + name) (never Shader.Find); when it is missing or unsupported, the fallback
        /// shader instead, logged once per name (an information line, not an error: the biome stays playable).
        /// </summary>
        public static Shader LoadShader(string name, string fallback)
        {
            Shader s = TryLoad(name);
            if (s != null && s.isSupported) return s;
            if (string.IsNullOrEmpty(fallback) || fallback == name)
            {
                if (s == null && fallbackLogged.Add(name ?? "<null>")) Debug.LogError("[PainterIO] Biome: shader Shaders/" + name + " not found");
                return s;
            }
            if (fallbackLogged.Add(name ?? "<null>"))
            {
                Debug.Log("[PainterIO] Biome: shader Shaders/" + name + (s == null ? " not found" : " not supported")
                          + ", using " + fallback + " instead");
            }
            Shader f = TryLoad(fallback);
            return f != null ? f : s;
        }

        private static Shader TryLoad(string name)
        {
            if (string.IsNullOrEmpty(name)) return null;
            try
            {
                return Resources.Load<Shader>("Shaders/" + name);
            }
            catch (Exception)
            {
                return null;
            }
        }

        // A theme file that forgot a value still yields a playable biome.
        private static void Sanitize(BiomeTheme t, BiomeId id)
        {
            t.Id = id;
            if (string.IsNullOrEmpty(t.NameKey)) t.NameKey = "biome." + CommandNameOf(id);
            if (string.IsNullOrEmpty(t.CompositeShader)) t.CompositeShader = LiquidCompositeShader;
            if (string.IsNullOrEmpty(t.BeadShader)) t.BeadShader = LiquidBeadShader;
            if (string.IsNullOrEmpty(t.OverlayShader)) t.OverlayShader = LiquidOverlayShader;
            if (t.PlayerColors == null || t.PlayerColors.Length < 4) t.PlayerColors = (Color[])Palette.Colors.Clone();
            if (t.SecondaryColors == null || t.SecondaryColors.Length < 4)
            {
                t.SecondaryColors = new Color[4];
                for (int i = 0; i < 4; i++) t.SecondaryColors[i] = Color.Lerp(t.PlayerColors[i], Color.white, 0.5f);
            }
            if (!(t.FillDuration > 0.01f)) t.FillDuration = 0.35f;
            if (t.BloomThreshold < 1.1f) t.BloomThreshold = 1.1f;
        }
    }
}
