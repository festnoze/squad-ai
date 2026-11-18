using System.Collections.Generic;

namespace OutOfSight.Core
{
    /// <summary>M6: what one sighting of a door leaf gave (docs/CONTRACT_M6.md 2.6).</summary>
    public enum DoorSighting
    {
        /// <summary>The leaf was not seen this step.</summary>
        NotSeen,

        /// <summary>Seen in the remembered state.</summary>
        Confirmed,

        /// <summary>Seen in another state than remembered, for the first time since the memory last changed: a Suspect.</summary>
        Suspect,

        /// <summary>Seen in another state than remembered, already noticed (no new suspicion).</summary>
        Known,
    }

    /// <summary>
    /// M6 (docs/CONTRACT_M6.md 2.6): one inhabitant's memory of the level's door leaves, leaf k in LevelDef.LeafDoors order.
    /// It starts at the authored states (the household knows its doors). A leaf seen in another state than remembered is a
    /// <see cref="DoorSighting.Suspect"/> once, then <see cref="DoorSighting.Known"/> until the memory changes
    /// (<see cref="Remember"/>: a door the household changed, opened on a walk or put back). Seeing a leaf as remembered
    /// changes nothing. Pure logic, no Unity object.
    /// </summary>
    public sealed class DoorMemory
    {
        private readonly bool[] open;
        private readonly bool[] noticed;

        public DoorMemory(IReadOnlyList<bool> openAtStart)
        {
            int n = openAtStart?.Count ?? 0;
            open = new bool[n];
            noticed = new bool[n];
            for (int k = 0; k < n; k++)
            {
                open[k] = openAtStart[k];
            }
        }

        /// <summary>The number of leaves remembered.</summary>
        public int Count => open.Length;

        /// <summary>True when leaf <paramref name="leaf"/> is remembered open (false out of range).</summary>
        public bool RemembersOpen(int leaf) => leaf >= 0 && leaf < open.Length && open[leaf];

        /// <summary>True once a mismatch of leaf <paramref name="leaf"/> gave its Suspect, until the memory changes.</summary>
        public bool Noticed(int leaf) => leaf >= 0 && leaf < noticed.Length && noticed[leaf];

        /// <summary>The leaf's state <paramref name="isOpen"/> differs from the remembered one (false out of range).</summary>
        public bool Differs(int leaf, bool isOpen) => leaf >= 0 && leaf < open.Length && open[leaf] != isOpen;

        /// <summary>The household changed the leaf: it is remembered <paramref name="isOpen"/>, and not noticed.</summary>
        public void Remember(int leaf, bool isOpen)
        {
            if (leaf < 0 || leaf >= open.Length)
            {
                return;
            }
            open[leaf] = isOpen;
            noticed[leaf] = false;
        }

        /// <summary>One sighting of leaf <paramref name="leaf"/> (seen or not this step) in state <paramref name="isOpen"/>.</summary>
        public DoorSighting Observe(int leaf, bool seen, bool isOpen)
        {
            if (!seen || leaf < 0 || leaf >= open.Length)
            {
                return DoorSighting.NotSeen;
            }
            if (open[leaf] == isOpen) // MUTATION:DOOR_MEMORY
            {
                return DoorSighting.Confirmed;
            }
            if (noticed[leaf])
            {
                return DoorSighting.Known;
            }
            noticed[leaf] = true;
            return DoorSighting.Suspect;
        }
    }
}
