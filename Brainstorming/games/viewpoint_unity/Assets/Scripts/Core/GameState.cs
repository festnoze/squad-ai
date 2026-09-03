using System;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// Campaign progression: which level is running, how many batteries are
    /// carried and inserted, how much film is left, and how far the player has
    /// ever reached (persisted).
    /// <para>
    /// A plain C# class on purpose: it references no scene node and no
    /// <see cref="UnityEngine.Object"/>, so an EditMode test can drive it bare
    /// with <c>new GameState()</c>. The running game shares a single one
    /// through <see cref="Instance"/>, which is how the world objects (battery,
    /// camera item, teleporter) reach it: they have no other way.
    /// </para>
    /// <para>
    /// The constructor deliberately does NOT read the saved progress, because
    /// clamping it needs the level count and that would pull the level catalog
    /// (and Resources) into every unit test. Production goes through
    /// <see cref="Instance"/>, which loads once; a bare instance starts at zero
    /// until someone calls <see cref="LoadProgress"/>.
    /// </para>
    /// </summary>
    public sealed class GameState
    {
        /// <summary>
        /// PlayerPrefs key holding the furthest level ever reached. The Godot
        /// original wrote the same number to <c>user://progress.cfg</c>.
        /// Public so a test can clear it before checking the fresh-save case.
        /// </summary>
        public const string ProgressKey = "viewpoint.furthest_level";

        /// <summary>Raised on every accepted change of the battery counters: (carried, inserted, required).</summary>
        public event Action<int, int, int> BatteriesChanged;

        /// <summary>Raised whenever the film count actually changes.</summary>
        public event Action<int> FilmsChanged;

        /// <summary>Raised by <see cref="BeginLevel"/> with the level index.</summary>
        public event Action<int> LevelStarted;

        private static GameState _instance;

        /// <summary>
        /// The instance the running game shares. READING it is the production
        /// path: the first read builds one and calls <see cref="LoadProgress"/>,
        /// so the title screen sees the persisted unlocks without anyone having
        /// to remember. The setter exists for tests (assign null to start from a
        /// clean slate); a caller that installs its own instance is responsible
        /// for calling <see cref="LoadProgress"/> on it, because a state that
        /// never loaded reports every level but the first as locked.
        /// </summary>
        public static GameState Instance
        {
            get
            {
                if (_instance == null)
                {
                    _instance = new GameState();
                    _instance.LoadProgress();
                }
                return _instance;
            }
            set { _instance = value; }
        }

        /// <summary>
        /// Where the level count comes from. Swappable so a unit test can drive
        /// the unlocking and clamping rules without loading the level catalog.
        /// </summary>
        public Func<int> LevelCountProvider = DefaultLevelCount;

        /// <summary>Number of levels in the campaign, never negative.</summary>
        public int LevelCount
        {
            get
            {
                if (LevelCountProvider == null)
                {
                    return 0;
                }
                int count = LevelCountProvider();
                return count > 0 ? count : 0;
            }
        }

        private int _levelIndex;
        private int _carriedBatteries;
        private int _carriedSealed;
        private int _insertedBatteries;
        private int _requiredBatteries;
        private int _cameraFilms;
        private int _furthestLevel;

        /// <summary>Index of the level being played, 0 based.</summary>
        public int LevelIndex { get { return _levelIndex; } }

        /// <summary>Batteries in hand, leaden ones included.</summary>
        public int CarriedBatteries { get { return _carriedBatteries; } }

        /// <summary>
        /// How many of the carried batteries are leaden. Tracked because a
        /// battery keeps its nature through the hands: without this, picking a
        /// sealed battery up and putting it down again would launder it into a
        /// copyable one and the whole mechanic would be a formality (7.4).
        /// </summary>
        public int CarriedSealed { get { return _carriedSealed; } }

        /// <summary>Batteries already inside the teleporter.</summary>
        public int InsertedBatteries { get { return _insertedBatteries; } }

        /// <summary>Batteries the teleporter asks for on this level.</summary>
        public int RequiredBatteries { get { return _requiredBatteries; } }

        /// <summary>
        /// Shots left on the current level. Zero means no camera (or no film):
        /// the HUD shows the film line only above zero (7.1).
        /// </summary>
        public int CameraFilms { get { return _cameraFilms; } }

        /// <summary>Highest level index ever reached, persisted across sessions.</summary>
        public int FurthestLevel { get { return _furthestLevel; } }

        /// <summary>
        /// Zeroes the run. Never touches <see cref="FurthestLevel"/>: starting
        /// a run from the level grid keeps the other unlocked levels unlocked.
        /// Emits nothing, like the original: the level about to load emits.
        /// </summary>
        public void Reset()
        {
            _levelIndex = 0;
            _carriedBatteries = 0;
            _carriedSealed = 0;
            _insertedBatteries = 0;
            _requiredBatteries = 0;
            _cameraFilms = 0;
        }

        /// <summary>
        /// Enters a level: hands empty, teleporter empty, no film.
        /// The emission order (films, then the unlock, then the level, then the
        /// batteries) is observable by the HUD and by the tests, so keep it.
        /// </summary>
        /// <param name="index">Level index, 0 based.</param>
        /// <param name="required">Batteries the teleporter asks for.</param>
        public void BeginLevel(int index, int required)
        {
            _levelIndex = index;
            _carriedBatteries = 0;
            _carriedSealed = 0;
            _insertedBatteries = 0;
            _requiredBatteries = required;
            _cameraFilms = 0;
            RaiseFilmsChanged();
            if (index > _furthestLevel)
            {
                _furthestLevel = index;
                SaveProgress();
            }
            if (LevelStarted != null)
            {
                LevelStarted(index);
            }
            RaiseBatteriesChanged();
        }

        /// <summary>Takes one battery into the hands.</summary>
        /// <param name="isSealed">True for a leaden battery (one that came out of a photo).</param>
        public void CollectBattery(bool isSealed = false)
        {
            _carriedBatteries += 1;
            if (isSealed)
            {
                _carriedSealed += 1;
            }
            RaiseBatteriesChanged();
        }

        /// <summary>
        /// Puts one carried battery back down (the caller spawns the matching
        /// pickup). Returns "" when nothing is carried, "sealed" or "normal"
        /// otherwise.
        /// <para>
        /// Leaden batteries go down FIRST, deliberately: whichever order the
        /// player picked them up in, what he sets down is the leaden one for as
        /// long as he holds any, so putting a battery down can never turn lead
        /// into film-ready amber (7.4).
        /// </para>
        /// </summary>
        public string DropBattery()
        {
            if (_carriedBatteries <= 0)
            {
                return "";
            }
            _carriedBatteries -= 1;
            string kind = "normal";
            if (_carriedSealed > 0)
            {
                _carriedSealed -= 1;
                kind = "sealed";
            }
            RaiseBatteriesChanged();
            return kind;
        }

        /// <summary>
        /// Moves carried batteries into the teleporter, up to the requirement.
        /// Returns how many actually moved (0 changes nothing and emits nothing).
        /// Spends lead first, same order as <see cref="DropBattery"/>, which is
        /// also the kind thing to do: the copyable one stays in hand longest.
        /// </summary>
        public int InsertBatteries()
        {
            int wanted = _requiredBatteries - _insertedBatteries;
            if (wanted < 0)
            {
                wanted = 0;
            }
            int moved = _carriedBatteries < wanted ? _carriedBatteries : wanted;
            if (moved <= 0)
            {
                return 0;
            }
            _carriedBatteries -= moved;
            _carriedSealed = _carriedSealed - moved;
            if (_carriedSealed < 0)
            {
                _carriedSealed = 0;
            }
            _insertedBatteries += moved;
            RaiseBatteriesChanged();
            return moved;
        }

        /// <summary>True once the teleporter holds everything it asked for.</summary>
        public bool CanTeleport()
        {
            return _requiredBatteries > 0 && _insertedBatteries >= _requiredBatteries;
        }

        /// <summary>Grants shots (the camera item).</summary>
        public void AddFilms(int count)
        {
            _cameraFilms += count;
            RaiseFilmsChanged();
        }

        /// <summary>Consumes one shot. Returns false when there is no film left.</summary>
        public bool UseFilm()
        {
            if (_cameraFilms <= 0)
            {
                return false;
            }
            _cameraFilms -= 1;
            RaiseFilmsChanged();
            return true;
        }

        /// <summary>
        /// Puts the counters back where a rewind snapshot found them. Silent
        /// about how it happened: the HUD just follows the events. Film only
        /// reports when it really changed, so a rewind that does not touch the
        /// camera does not flicker the film line.
        /// </summary>
        /// <param name="carried">Batteries in hand at that instant.</param>
        /// <param name="inserted">Batteries in the teleporter at that instant.</param>
        /// <param name="required">The level requirement at that instant.</param>
        /// <param name="films">Shots left at that instant.</param>
        /// <param name="sealedCount">Leaden ones among the carried, clamped into [0, carried].</param>
        public void RestoreCounters(int carried, int inserted, int required, int films, int sealedCount = 0)
        {
            _carriedBatteries = carried;
            _carriedSealed = Mathf.Clamp(sealedCount, 0, carried > 0 ? carried : 0);
            _insertedBatteries = inserted;
            _requiredBatteries = required;
            if (_cameraFilms != films)
            {
                _cameraFilms = films;
                RaiseFilmsChanged();
            }
            RaiseBatteriesChanged();
        }

        /// <summary>True when another level follows the current one.</summary>
        public bool HasNextLevel()
        {
            return _levelIndex + 1 < LevelCount;
        }

        /// <summary>Steps to the next level index (the caller loads it).</summary>
        public void AdvanceLevel()
        {
            _levelIndex += 1;
        }

        /// <summary>
        /// A level is playable once it has been reached, which drives the level
        /// grid of the menus.
        /// </summary>
        public bool IsLevelUnlocked(int index)
        {
            return index >= 0 && index < LevelCount && index <= _furthestLevel;
        }

        /// <summary>
        /// Reads the persisted progress. An absurd or corrupt value is clamped
        /// into the campaign range rather than refused.
        /// </summary>
        public void LoadProgress()
        {
            int saved = PlayerPrefs.GetInt(ProgressKey, 0);
            int highest = LevelCount - 1;
            if (highest < 0)
            {
                highest = 0;
            }
            _furthestLevel = Mathf.Clamp(saved, 0, highest);
        }

        /// <summary>Writes the progress out immediately (levels are rare events).</summary>
        public void SaveProgress()
        {
            PlayerPrefs.SetInt(ProgressKey, _furthestLevel);
            PlayerPrefs.Save();
        }

        private void RaiseBatteriesChanged()
        {
            if (BatteriesChanged != null)
            {
                BatteriesChanged(_carriedBatteries, _insertedBatteries, _requiredBatteries);
            }
        }

        private void RaiseFilmsChanged()
        {
            if (FilmsChanged != null)
            {
                FilmsChanged(_cameraFilms);
            }
        }

        // Named method rather than a lambda in the field initializer so the
        // catalog is touched only when the count is actually asked for.
        private static int DefaultLevelCount()
        {
            return LevelDefs.Count;
        }
    }
}
