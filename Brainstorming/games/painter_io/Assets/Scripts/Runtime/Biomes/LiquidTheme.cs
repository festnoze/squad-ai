// Owned by BI (wave B-2); the LIQ agent may retune the values. Contract 25.1: the Liquide biome (id 0, default) is the
// look of contract 12: glossy liquid paint on a deep navy table (palette of 11.3).
// Wave D (liq-drop, contract 28 F2): ShaderParams.x is the strength of the drop look of LiquidComposite (the domed body
// from the _PIO_TerritoryDome field: depth absorption, dome diffuse, broad highlight band, hot spot, soft dome shadow),
// published as _PIO_BiomeParams.x. 1 is the wave D look, 0 gives back the wave C puddles exactly.
using UnityEngine;

namespace PainterIO.Runtime
{
    public static class LiquidTheme
    {
        /// <summary>Strength of the drop look (wave D F2), published as _PIO_BiomeParams.x: 1 = domed drops, 0 = wave C.</summary>
        public const float DropStrength = 1f;

        public static BiomeTheme Create()
        {
            var t = new BiomeTheme
            {
                Id = BiomeId.Liquid,
                NameKey = "biome.liquid",
                CompositeShader = BiomeTheme.LiquidCompositeShader,
                BeadShader = BiomeTheme.LiquidBeadShader,
                OverlayShader = BiomeTheme.LiquidOverlayShader,
                PlayerColors = (Color[])Palette.Colors.Clone(),       // Coral, Teal, Saffron, Lilac (11.3)
                Ground = Palette.Background,                           // #1E2A4D
                OutsideArena = Palette.OutsideArena,                   // #151D38
                UiAccent = new Color32(0xF3, 0xEE, 0xE8, 0xFF),       // the UI light: the HUD looks exactly as in wave B-1
                FillDuration = 0.35f,
                BloomOnHigh = false,
                ShaderParams = new Vector4(DropStrength, 0f, 0f, 0f), // x: drop strength (LiquidComposite), yzw unused
            };
            t.SecondaryColors = new Color[4];
            for (int i = 0; i < 4; i++) t.SecondaryColors[i] = Color.Lerp(t.PlayerColors[i], Color.white, 0.55f);
            return t;
        }
    }
}
