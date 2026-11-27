// Owned by BI since wave B-2 (written by B0a). Contract 11.3: player colors (sRGB), table colors, the human's color choice
// (index swap) and the Strings keys of the player names. Contract 25.2: ColorOf returns the current biome's PlayerColors
// (BiomeTheme.Current); Colors, Background and OutsideArena keep the liquid values of 11.3 (the Liquide theme uses them).
using UnityEngine;

namespace PainterIO.Runtime
{
    public static class Palette
    {
        /// <summary>Liquid palette colors (sRGB) by palette index: 0 Coral, 1 Teal, 2 Saffron, 3 Lilac (see ColorAt for the current biome).</summary>
        public static readonly Color[] Colors =
        {
            new Color32(0xF2, 0x67, 0x4F, 0xFF),
            new Color32(0x22, 0xC4, 0xB6, 0xFF),
            new Color32(0xF5, 0xB7, 0x31, 0xFF),
            new Color32(0x8E, 0x6C, 0xEF, 0xFF),
        };

        /// <summary>Table (arena ground) navy #1E2A4D.</summary>
        public static readonly Color Background = new Color32(0x1E, 0x2A, 0x4D, 0xFF);

        /// <summary>Outside the arena (and the camera clear color) #B4B9C1: a flat, slightly cool light grey shared by every
        /// biome so the outside reads as "not playable" (the composites draw a yellow neon line on the edge).</summary>
        public static readonly Color OutsideArena = new Color32(0xB4, 0xB9, 0xC1, 0xFF);

        /// <summary>Light UI text #F3EEE8.</summary>
        public static readonly Color UiText = new Color32(0xF3, 0xEE, 0xE8, 0xFF);

        /// <summary>Danger flash white #FFFFFF.</summary>
        public static readonly Color DangerFlash = new Color32(0xFF, 0xFF, 0xFF, 0xFF);

        /// <summary>Strings key of the human's name ("Toi", EN "You").</summary>
        public const string HumanNameKey = "name.you";

        /// <summary>0..3, backed by SaveData.ColorIndex.</summary>
        public static int HumanColor
        {
            get => Wrap(SaveData.ColorIndex);
            set => SaveData.ColorIndex = Wrap(value);
        }

        /// <summary>Palette index shown for a sim player: 0 and HumanColor swapped (every session, attract included).</summary>
        public static int ColorIndexOf(int playerIndex)
        {
            int p = Wrap(playerIndex);
            int h = HumanColor;
            if (p == 0) return h;
            if (p == h) return 0;
            return p;
        }

        /// <summary>sRGB color of ColorIndexOf(playerIndex) in the current biome (BiomeTheme.Current.PlayerColors).</summary>
        public static Color ColorOf(int playerIndex)
        {
            return ColorAt(ColorIndexOf(playerIndex));
        }

        /// <summary>sRGB color of a palette index (0..3) in the current biome (menu swatches, buttons in the human color).</summary>
        public static Color ColorAt(int colorIndex)
        {
            Color[] colors = BiomeTheme.Current.PlayerColors;
            int k = Wrap(colorIndex);
            return colors != null && colors.Length > k ? colors[k] : Colors[k];
        }

        /// <summary>sRGB secondary color (hot core, highlight tint) of a sim player in the current biome.</summary>
        public static Color SecondaryColorOf(int playerIndex)
        {
            Color[] colors = BiomeTheme.Current.SecondaryColors;
            int k = ColorIndexOf(playerIndex);
            return colors != null && colors.Length > k ? colors[k] : Color.Lerp(ColorAt(k), Color.white, 0.5f);
        }

        /// <summary>Arena ground of the current biome (sRGB; Background in Liquide).</summary>
        public static Color GroundColor => BiomeTheme.Current.Ground;

        /// <summary>Outside the arena and camera clear color of the current biome (sRGB; OutsideArena in Liquide).</summary>
        public static Color OutsideColor => BiomeTheme.Current.OutsideArena;

        /// <summary>Linear color of ColorIndexOf(playerIndex) (for shader globals such as _PIO_Colors).</summary>
        public static Color LinearColorOf(int playerIndex)
        {
            return ColorOf(playerIndex).linear;
        }

        /// <summary>Strings key of the name of a palette color: "name.color0".."name.color3" (Corail, Lagon, Safran, Lilas).</summary>
        public static string ColorNameKey(int colorIndex)
        {
            return "name.color" + Wrap(colorIndex);
        }

        private static int Wrap(int i)
        {
            int m = i % 4;
            return m < 0 ? m + 4 : m;
        }
    }
}
