using System.Collections.Generic;

namespace Meuble.Core
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5_v3.md 4 and 15.6): who sits on which seat. A seat is a prop name, or "player"
    /// (<see cref="InhabitantRoutine.PlayerSeat"/>) for the player furniture, and holds at most one sitter. Shared by
    /// GameState and the level audit, one registry per level; a sitter is its inhabitant index
    /// (<see cref="InhabitantRoutine.SeatOwner"/>).
    /// <para>
    /// The routine claims its seat at the moment of sitting, and releases it on the first stand-up step and on any
    /// reset (Pin, Startle). A pratfall claims nothing. A sit station whose seat is taken by someone else is a plain
    /// standing dwell.
    /// </para>
    /// <para>
    /// <see cref="IsTaken"/> (an inhabitant sits there) is not <see cref="InhabitantRoutine.SeatOccupied"/> (M4: the
    /// player furniture stands at its seat home, so there is something to sit on). A "player" seat needs both: free in
    /// this registry, and occupied by the furniture; otherwise it is a standing dwell or a pratfall.
    /// </para>
    /// </summary>
    public sealed class SeatRegistry
    {
        private readonly Dictionary<string, int> sitters = new Dictionary<string, int>();

        /// <summary>Claims the seat for <paramref name="who"/>; false when someone else holds it (or the seat is null).</summary>
        public bool TryClaim(string seat, int who)
        {
            if (seat == null)
            {
                return false;
            }
            if (sitters.TryGetValue(seat, out int holder) && holder != who)
            {
                return false;
            }
            sitters[seat] = who;
            return true;
        }

        /// <summary>Frees the seat if <paramref name="who"/> holds it; a release by anyone else does nothing.</summary>
        public void Release(string seat, int who)
        {
            if (seat != null && sitters.TryGetValue(seat, out int holder) && holder == who)
            {
                sitters.Remove(seat);
            }
        }

        /// <summary>True while an inhabitant sits on the seat.</summary>
        public bool IsTaken(string seat) => seat != null && sitters.ContainsKey(seat);

        /// <summary>The sitter of a seat, or -1 when it is free.</summary>
        public int SitterOf(string seat) => seat != null && sitters.TryGetValue(seat, out int holder) ? holder : -1;

        /// <summary>The number of seats held.</summary>
        public int Count => sitters.Count;

        public void Clear() => sitters.Clear();
    }
}
