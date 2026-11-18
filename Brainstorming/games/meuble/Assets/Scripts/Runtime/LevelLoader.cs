using System;
using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>Reads a <see cref="LevelDef"/> from Resources/Levels and validates it (PRD 6.1, 8.3).</summary>
    public static class LevelLoader
    {
        public const string Folder = "Levels";

        /// <summary>M2: Resources/Levels/levels.json, the play order (docs/CONTRACT_M2.md 4). It is not a level.</summary>
        public const string ManifestName = "levels";

        /// <summary>Loads and validates a level. Throws with every validation issue listed when it is invalid.</summary>
        public static LevelDef Load(string id)
        {
            var asset = Resources.Load<TextAsset>(Folder + "/" + id);
            if (asset == null)
            {
                throw new InvalidOperationException($"Level '{id}' not found in Resources/{Folder}");
            }
            LevelDef level = LevelJson.Parse(asset.text);
            List<string> issues = LevelValidator.Validate(level);
            if (issues.Count > 0)
            {
                throw new InvalidOperationException($"Level '{id}' is invalid:\n - " + string.Join("\n - ", issues));
            }
            return level;
        }

        /// <summary>True when Resources/Levels/levels.json exists.</summary>
        public static bool HasManifest => Resources.Load<TextAsset>(Folder + "/" + ManifestName) != null;

        /// <summary>
        /// The play order of levels.json. Without the file, the game has a single level: the one given
        /// (<paramref name="fallback"/>), so a missing manifest never breaks a level that loads on its own.
        /// </summary>
        public static List<string> LoadManifest(string fallback)
        {
            var asset = Resources.Load<TextAsset>(Folder + "/" + ManifestName);
            List<string> order = asset != null ? LevelManifest.Parse(asset.text) : null;
            if (order == null || order.Count == 0)
            {
                order = new List<string>();
                if (!string.IsNullOrEmpty(fallback))
                {
                    order.Add(fallback);
                }
            }
            return order;
        }
    }
}
