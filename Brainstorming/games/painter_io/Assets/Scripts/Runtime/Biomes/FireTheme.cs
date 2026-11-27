// Written by BI (wave B-2); owned by FIRE from phase 2 on. Contract 25.3: the Feu biome (id 1): glowing embers and live
// flames on charred stone, drawn by FireComposite / FireBead / FireOverlay (Resources/Shaders) and FireFx, heard through
// FireSfx. The shaders read PlayerColors and SecondaryColors (the hot cores) through _PIO_Colors / _PIO_SecondaryColors.
using UnityEngine;

namespace PainterIO.Runtime
{
    public static class FireTheme
    {
        public static BiomeTheme Create()
        {
            var t = new BiomeTheme
            {
                Id = BiomeId.Fire,
                NameKey = "biome.fire",
                CompositeShader = "FireComposite",
                BeadShader = "FireBead",
                OverlayShader = "FireOverlay",
                // Chemical flames: 0 orange-red, 1 copper green-teal, 2 gold, 3 potassium violet.
                PlayerColors = new Color[]
                {
                    new Color32(0xFF, 0x5A, 0x2A, 0xFF),
                    new Color32(0x22, 0xE0, 0xB8, 0xFF),
                    new Color32(0xFF, 0xC2, 0x1F, 0xFF),
                    new Color32(0xB4, 0x72, 0xFF, 0xFF),
                },
                // Hot cores: #FFD08A for the orange-red flame, a white-hot tint of each flame for the others.
                SecondaryColors = new Color[]
                {
                    new Color32(0xFF, 0xD0, 0x8A, 0xFF),
                    new Color32(0xC8, 0xFF, 0xEC, 0xFF),
                    new Color32(0xFF, 0xF1, 0xB0, 0xFF),
                    new Color32(0xE8, 0xD2, 0xFF, 0xFF),
                },
                Ground = new Color32(0x1A, 0x14, 0x12, 0xFF),          // charred stone (#1A1412 to #241A16)
                OutsideArena = new Color32(0x10, 0x0C, 0x0B, 0xFF),
                UiAccent = new Color32(0xFF, 0xD2, 0x9A, 0xFF),        // warm ember white
                FillDuration = 0.60f,
                BloomOnHigh = true,
                BloomThreshold = 1.1f,
                BloomIntensity = 0.85f,
                BloomScatter = 0.65f,
                ShaderParams = Vector4.zero,
            };
            return t;
        }
    }
}
