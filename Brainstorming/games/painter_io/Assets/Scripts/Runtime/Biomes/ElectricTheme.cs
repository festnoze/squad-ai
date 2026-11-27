// Written by BI (wave B-2); owned by ELEC from phase 2 on, by elec-arcs in wave D. Contract 25.4: the Électricité biome
// (id 2), electrified neon plasma on a dark circuit board, drawn by ElectricComposite / ElectricBead / ElectricOverlay
// (Resources/Shaders), with ElectricFx (arcs, current packet, dead cable, sparks) and ElectricSfx (hum, zap, crackle,
// buzz, discharge, fizzle). The liquid shaders draw it with these colors only if an electric shader is missing
// (BiomeTheme fallback).
// Wave D (docs/WAVE_D_FEEDBACK.md F3): ShaderParams carries the interior arcs of the territory to ElectricComposite as
// the _PIO_BiomeParams global (published by LiquidRenderer at creation and on every biome change).
using UnityEngine;

namespace PainterIO.Runtime
{
    public static class ElectricTheme
    {
        /// <summary>
        /// Interior arcs, High tier: probability that a cell of the composite's arc grid (1.46 u) holds an arc in a spawn
        /// slot (0.8 s). Medium draws half of it, Low a quarter (slow, static-ish arcs). 0 turns the arcs off.
        /// </summary>
        public const float ArcDensity = 0.8f;

        /// <summary>Extra probability added within about 0.6 u of the territory edge (F3: a few more near the rim).</summary>
        public const float ArcRimDensity = 0.4f;

        /// <summary>
        /// Core level: the white-hot core is the player's secondary color pushed halfway to white, times this. At 0.82
        /// every electric core stays at or below sRGB luma 231 (below the 235 readability threshold), so the chase packet
        /// stays the brightest moving thing (contract 25.5, 26.3).
        /// </summary>
        public const float ArcCoreLevel = 0.82f;

        /// <summary>
        /// Glow level: how far the neon halo around the core pulls the surface toward the glow color (the player color
        /// boosted 1.3 x and moved 45 % toward the core color, its luminance capped at 0.92 x the core's), at the core,
        /// falling to 0 at 0.17 u. A blend, never an addition: the halo cannot outshine the core, even on a bright neon
        /// such as cyan.
        /// </summary>
        public const float ArcGlowLevel = 0.75f;

        /// <summary>The arc parameters as published in _PIO_BiomeParams: (density, rim density, core level, glow level).</summary>
        public static Vector4 ArcParams => new Vector4(ArcDensity, ArcRimDensity, ArcCoreLevel, ArcGlowLevel);

        public static BiomeTheme Create()
        {
            var t = new BiomeTheme
            {
                Id = BiomeId.Electric,
                NameKey = "biome.electric",
                CompositeShader = "ElectricComposite",
                BeadShader = "ElectricBead",
                OverlayShader = "ElectricOverlay",
                // Neon (contract 25.4): 0 red-pink, 1 cyan, 2 electric yellow, 3 violet.
                PlayerColors = new Color[]
                {
                    new Color32(0xFF, 0x4D, 0x6D, 0xFF),
                    new Color32(0x2E, 0xF2, 0xFF, 0xFF),
                    new Color32(0xFF, 0xE8, 0x4D, 0xFF),
                    new Color32(0xA9, 0x74, 0xFF, 0xFF),
                },
                // White-hot cores of the live wires, rims and arcs (published as _PIO_SecondaryColors).
                SecondaryColors = new Color[]
                {
                    new Color32(0xFF, 0xD6, 0xE0, 0xFF),
                    new Color32(0xD8, 0xFD, 0xFF, 0xFF),
                    new Color32(0xFF, 0xFA, 0xD6, 0xFF),
                    new Color32(0xE6, 0xD8, 0xFF, 0xFF),
                },
                Ground = new Color32(0x0B, 0x0F, 0x1E, 0xFF),          // very dark blue-black circuit board
                OutsideArena = new Color32(0x07, 0x09, 0x12, 0xFF),
                UiAccent = new Color32(0xB8, 0xF6, 0xFF, 0xFF),        // cool neon white
                FillDuration = 0.25f,
                // Emissive look: cores, rims, arcs and the current packet go above 1 and bloom on the High tier.
                BloomOnHigh = true,
                BloomThreshold = 1.1f,
                BloomIntensity = 0.85f,
                BloomScatter = 0.6f,
                // Interior arcs of the territory (wave D, F3), read by ElectricComposite as _PIO_BiomeParams.
                ShaderParams = ArcParams,
            };
            return t;
        }
    }
}
