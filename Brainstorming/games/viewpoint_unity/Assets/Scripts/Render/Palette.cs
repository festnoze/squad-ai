using System.Collections.Generic;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// Named colors of the game (PRD 14.1). Every material color goes through
    /// here so the whole look can be retuned in one place, and so tests can
    /// assert that photo and level definitions only reference colors that exist.
    ///
    /// The values are sRGB components. The project renders in Linear color
    /// space, so they are handed to Unity as a <see cref="Color"/> and Unity
    /// converts them on upload: that is why the numbers below are copied from
    /// the PRD table unchanged.
    /// </summary>
    public static class Palette
    {
        private static readonly Dictionary<string, Color> ColorsByKey = new Dictionary<string, Color>
        {
            // GROUND LANGUAGE, read at a glance and never explained in words:
            // grey stays, pale goes. A grey slab survives any photo placed over
            // it (the photo is added to it); a pale slab is carved away by the
            // frame, like the lavender walls and crates it belongs to.
            { "platform", new Color(0.70f, 0.71f, 0.75f) },
            { "platform_side", new Color(0.53f, 0.54f, 0.59f) },
            { "platform_soft", new Color(0.93f, 0.92f, 0.97f) },
            { "platform_soft_side", new Color(0.80f, 0.78f, 0.88f) },

            // SEALED MATTER, the same language pushed one step further: grey
            // that has gone to steel and lead. A steel cage no photo ever
            // breaks, a leaden battery no film ever prints. Darker than the
            // permanent ground, and with no life of its own (a sealed battery
            // neither bobs nor turns).
            { "sealed", new Color(0.58f, 0.60f, 0.66f) },
            { "sealed_dark", new Color(0.40f, 0.42f, 0.48f) },
            { "battery_sealed", new Color(0.50f, 0.52f, 0.57f) },

            { "accent", new Color(0.91f, 0.45f, 0.35f) },
            { "accent_dark", new Color(0.72f, 0.32f, 0.24f) },
            { "teal", new Color(0.25f, 0.65f, 0.63f) },
            { "teal_dark", new Color(0.18f, 0.50f, 0.48f) },
            { "frame", new Color(0.98f, 0.97f, 0.95f) },
            { "photo_back", new Color(0.88f, 0.86f, 0.82f) },
            { "battery", new Color(1.0f, 0.76f, 0.29f) },
            { "battery_tip", new Color(0.35f, 0.35f, 0.38f) },
            { "teleporter", new Color(0.36f, 0.36f, 0.84f) },
            { "teleporter_ring", new Color(0.55f, 0.78f, 1.0f) },
            { "erasable", new Color(0.69f, 0.62f, 0.86f) },
            { "wood", new Color(0.62f, 0.47f, 0.34f) },
            { "wood_dark", new Color(0.48f, 0.36f, 0.26f) },
            { "stone", new Color(0.78f, 0.77f, 0.75f) },
            { "sky_top", new Color(0.53f, 0.72f, 0.87f) },
            { "sky_horizon", new Color(0.87f, 0.91f, 0.93f) },
            { "backdrop_top", new Color(0.62f, 0.79f, 0.90f) },
            { "backdrop_bottom", new Color(0.93f, 0.90f, 0.84f) },
        };

        /// <summary>True when the key names a color of the palette.</summary>
        public static bool Has(string key)
        {
            return key != null && ColorsByKey.ContainsKey(key);
        }

        /// <summary>
        /// The color behind a key. An unknown key is a data bug, so it warns
        /// and returns magenta: the missing color has to be visible in game,
        /// not silently replaced by something plausible.
        /// </summary>
        public static Color Get(string key)
        {
            Color color;
            if (key != null && ColorsByKey.TryGetValue(key, out color))
            {
                return color;
            }

            Debug.LogWarning("Palette: unknown color key '" + key + "'");
            return Color.magenta;
        }

        /// <summary>
        /// Every key of the palette. Callers must not depend on the order: a
        /// dictionary yields insertion order only by accident.
        /// </summary>
        public static IEnumerable<string> Keys
        {
            get { return ColorsByKey.Keys; }
        }
    }
}
