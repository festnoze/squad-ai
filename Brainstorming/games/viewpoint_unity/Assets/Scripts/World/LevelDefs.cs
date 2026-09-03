using System.Collections.Generic;

namespace Viewpoint
{
    /// <summary>
    /// The levels and the decor islands of Resources/Data/levels.json (schema in
    /// PRD section 13.1), read once through PhotoJson and kept in DESIGN space:
    /// LevelBuilder is the single place that mirrors them into Unity space.
    ///
    /// A malformed file raises PhotoDataException here, at load. That is
    /// deliberate: a silent default would only be noticed later as a puzzle that
    /// cannot be solved.
    /// </summary>
    public static class LevelDefs
    {
        static List<LevelDef> _levels;
        static List<IslandDef> _islands;

        public static int Count
        {
            get
            {
                EnsureLoaded();
                return _levels.Count;
            }
        }

        /// The scenery boxes floating around every level, the same for all of them.
        public static IReadOnlyList<IslandDef> DecorIslands
        {
            get
            {
                EnsureLoaded();
                return _islands;
            }
        }

        /// Null out of range, so a caller can probe past the last level.
        public static LevelDef GetDef(int index)
        {
            EnsureLoaded();
            if (index < 0 || index >= _levels.Count)
            {
                return null;
            }
            return _levels[index];
        }

        static void EnsureLoaded()
        {
            if (_levels != null)
            {
                return;
            }
            (List<LevelDef> levels, List<IslandDef> islands) loaded = PhotoJson.LoadLevels();
            _levels = loaded.levels;
            _islands = loaded.islands;
        }
    }
}
