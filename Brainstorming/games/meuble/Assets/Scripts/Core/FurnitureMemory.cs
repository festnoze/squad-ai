using System;
using System.Collections.Generic;
using UnityEngine;

namespace Meuble.Core
{
    /// <summary>A furniture pose on the floor: planar position and yaw.</summary>
    public struct FurniturePose
    {
        public Vector3 Position;
        public float Yaw;

        public FurniturePose(Vector3 position, float yaw)
        {
            Position = position;
            Yaw = yaw;
        }
    }

    /// <summary>Outcome of one sighting (docs/CONTRACT_M2.md 3.1 and 11).</summary>
    public enum Observation
    {
        /// <summary>The inhabitant does not see the player furniture this step.</summary>
        NotSeen,

        /// <summary>Seen within tolerance of the player slot: the slot takes the seen pose.</summary>
        Confirmed,

        /// <summary>Seen away from the player slot, but within tolerance of a decoy of the same kind.</summary>
        ExplainedByDecoy,

        /// <summary>
        /// Seen out of place for <see cref="Tuning.DiscoveryGrace"/> in a row: fires once per incident.
        /// The return pose is <see cref="FurnitureMemory.PlayerSlot"/>.
        /// </summary>
        Discovery,

        /// <summary>Seen out of place, either before the grace has run out or after this incident's discovery.</summary>
        Suspect,
    }

    /// <summary>
    /// Displacement memory of one inhabitant (PRD 4.4, docs/CONTRACT_M2.md 3.1 as amended by 11). One slot per
    /// piece of furniture: the player slot P, seeded at the spawn pose, and one fixed slot per decoy. A sighting
    /// never creates a slot, and a decoy slot never moves. The tolerance is position only, and per inhabitant since M5
    /// (<see cref="Tolerance"/>).
    /// <para>
    /// An incident is a run of consecutive observed steps in which the chair is seen out of place. It ends on a
    /// step where the chair is not seen, seen in place, or explained by a decoy, and on <see cref="ResetGrace"/>
    /// or <see cref="SetPlayerSlot"/>. Within an incident, <see cref="Observe(bool, FurniturePose, float)"/>
    /// returns Suspect until the chair has been seen out of place for <see cref="Tuning.DiscoveryGrace"/>, then
    /// Discovery on exactly one step, then Suspect again until the incident ends.
    /// </para>
    /// </summary>
    public sealed class FurnitureMemory
    {
        // Ten steps of 0.02 s sum to 0.19999999 in float: the epsilon makes "0.20 s out of place" a discovery,
        // as in CaughtRule.
        private const float GraceEpsilon = 1e-4f;

        // Rounding margin only: a pose authored exactly on the tolerance stays within it despite float error.
        private const float DistanceEpsilon = 1e-4f;

        private readonly FurniturePose[] decoys;
        private readonly bool[] decoyOfPlayerKind;

        /// <summary>Seconds seen out of place in a row, in the current incident.</summary>
        private float outOfPlace;

        /// <summary>True once the current incident has given its discovery.</summary>
        private bool discovered;

        /// <summary>M6: the player slot was found empty (its discovery given), until the furniture is seen again.</summary>
        private bool spotKnownEmpty;

        /// <summary>The last pose at which this inhabitant saw the player furniture in place, and the carry back target.</summary>
        public FurniturePose PlayerSlot { get; private set; }

        /// <summary>
        /// M5 (CONTRACT_M5 3, PersonalityDef.Tolerance): the displacement tolerance of this inhabitant's memory, in metres,
        /// default <see cref="Tuning.DisplacementTolerance"/> (0.75); the tidy one notices 0.4 m and the watchful one 0.5 m.
        /// <see cref="Observe(bool, FurniturePose, float)"/> uses it for the player slot and for the decoys of the
        /// player's kind alike. Set it before the first observation.
        /// </summary>
        public float Tolerance { get; set; } = Tuning.DisplacementTolerance;

        /// <param name="playerSpawn">The pose where the household knows the player furniture belongs.</param>
        /// <param name="decoys">Decoy poses, fixed for the whole level. Null means no decoy.</param>
        /// <param name="decoyKinds">Kind of each decoy, parallel to <paramref name="decoys"/>.</param>
        /// <param name="playerKind">Kind of the player furniture. Kinds compare ignoring case.</param>
        public FurnitureMemory(FurniturePose playerSpawn, IReadOnlyList<FurniturePose> decoys, IReadOnlyList<string> decoyKinds,
            string playerKind)
        {
            int count = decoys?.Count ?? 0;
            if ((decoyKinds?.Count ?? 0) != count)
            {
                throw new ArgumentException($"{count} decoys but {decoyKinds?.Count ?? 0} decoy kinds", nameof(decoyKinds));
            }
            PlayerSlot = playerSpawn;
            this.decoys = new FurniturePose[count];
            decoyOfPlayerKind = new bool[count];
            for (int i = 0; i < count; i++)
            {
                this.decoys[i] = decoys[i];
                decoyOfPlayerKind[i] = string.Equals(decoyKinds[i], playerKind, StringComparison.OrdinalIgnoreCase);
            }
        }

        /// <summary>M5: the memory of an inhabitant whose personality has its own <paramref name="tolerance"/> (CONTRACT_M5 3).</summary>
        public FurnitureMemory(FurniturePose playerSpawn, IReadOnlyList<FurniturePose> decoys, IReadOnlyList<string> decoyKinds,
            string playerKind, float tolerance)
            : this(playerSpawn, decoys, decoyKinds, playerKind)
        {
            Tolerance = tolerance;
        }

        /// <summary>M5: <see cref="WithinTolerance(FurniturePose, FurniturePose)"/> with an explicit tolerance.</summary>
        public static bool WithinTolerance(FurniturePose a, FurniturePose b, float tolerance)
        {
            return YawMath.Planar(a.Position - b.Position).magnitude <= tolerance + DistanceEpsilon;
        }

        /// <summary>
        /// True when the planar distance is at most <see cref="Tuning.DisplacementTolerance"/>. Position only since
        /// M2.1: yaw and height are ignored, because the chair turns toward its motion.
        /// </summary>
        public static bool WithinTolerance(FurniturePose a, FurniturePose b)
        {
            return YawMath.Planar(a.Position - b.Position).magnitude <= Tuning.DisplacementTolerance + DistanceEpsilon;
        }

        /// <summary>
        /// M4 (docs/CONTRACT_M4.md 2.1, amendment 9.12): a tipped stool seen lying down is out of place wherever it
        /// is, even on its slot or next to a decoy of its kind. It is Suspect, then Discovery once the grace has run
        /// out, then Suspect again, exactly like an out of place sighting, and the slot does not take its pose. With
        /// <paramref name="lyingDown"/> false this is <see cref="Observe(bool, FurniturePose, float)"/>.
        /// </summary>
        public Observation Observe(bool playerSeen, FurniturePose player, float dt, bool lyingDown)
        {
            if (!lyingDown)
            {
                return Observe(playerSeen, player, dt);
            }
            if (!playerSeen)
            {
                ResetGrace(); // grace reset: not seen
                return Observation.NotSeen;
            }
            spotKnownEmpty = false;
            return SeenOutOfPlace(dt);
        }

        /// <summary>
        /// One observation, once per fixed step of <paramref name="dt"/> seconds, for an inhabitant that observes
        /// this step. On a step where the inhabitant does not observe at all (not in Routine or Alerted, frozen
        /// pinned, or the furniture is carried), call <see cref="ResetGrace"/> instead, so the grace only ever
        /// measures an unbroken sighting.
        /// </summary>
        public Observation Observe(bool playerSeen, FurniturePose player, float dt)
        {
            if (!playerSeen)
            {
                ResetGrace(); // grace reset: not seen
                return Observation.NotSeen;
            }
            spotKnownEmpty = false;
            if (WithinTolerance(player, PlayerSlot, Tolerance)) // MUTATION:TIDY_TOLERANCE
            {
                PlayerSlot = player;
                ResetGrace(); // grace reset: in place
                return Observation.Confirmed;
            }
            for (int i = 0; i < decoys.Length; i++)
            {
                // Seen or not, a chair of the same kind belongs there: "one chair among several".
                if (decoyOfPlayerKind[i] && WithinTolerance(player, decoys[i], Tolerance))
                {
                    ResetGrace(); // grace reset: explained
                    return Observation.ExplainedByDecoy;
                }
            }
            return SeenOutOfPlace(dt);
        }

        /// <summary>One step of the current incident: Suspect until the grace runs out, then Discovery once.</summary>
        private Observation SeenOutOfPlace(float dt)
        {
            if (discovered)
            {
                return Observation.Suspect;
            }
            outOfPlace += dt;
            if (outOfPlace >= Tuning.DiscoveryGrace - GraceEpsilon) // MUTATION:GRACE (mutation.sh makes it instant)
            {
                outOfPlace = 0f;
                discovered = true;
                return Observation.Discovery;
            }
            return Observation.Suspect;
        }

        /// <summary>
        /// Ends the current incident: the out of place timer restarts from 0 and the next incident can give a new
        /// discovery. GameState calls it on every step this inhabitant does not observe (pinned, startled,
        /// investigating, carrying, or the furniture is carried).
        /// </summary>
        public void ResetGrace()
        {
            outOfPlace = 0f;
            discovered = false;
        }

        /// <summary>
        /// Moves the player slot: after a put down, or when an investigation with no path gives up (CONTRACT 11.4).
        /// It also ends the current incident, since the pose it was measured against is gone.
        /// </summary>
        public void SetPlayerSlot(FurniturePose pose)
        {
            PlayerSlot = pose;
            spotKnownEmpty = false;
            ResetGrace();
        }

        // ----- M6 (docs/CONTRACT_M6.md 2.5): the remembered spot seen empty -----

        /// <summary>
        /// M6: true once this inhabitant found the player slot empty (its discovery given), until it sees the furniture again
        /// (any <see cref="Observe(bool, FurniturePose, float)"/> with the furniture seen) or the slot moves.
        /// </summary>
        public bool SpotKnownEmpty => spotKnownEmpty;

        /// <summary>
        /// M6 (CONTRACT_M6 2.5): one observation while the player furniture is hidden in a wardrobe (it has no samples, so it
        /// is never seen). <paramref name="spotSeen"/>: the player slot's sample box is inside this inhabitant's view. Seen
        /// empty, the slot is an incident exactly like a furniture seen out of place: Suspect until
        /// <see cref="Tuning.DiscoveryGrace"/>, then Discovery once (the caller investigates the slot). After that discovery
        /// the slot is known empty: NotSeen until the furniture is seen again, so a spot gives one discovery per hiding.
        /// </summary>
        public Observation ObserveEmptySpot(bool spotSeen, float dt)
        {
            bool blind = !spotSeen || spotKnownEmpty;
            if (blind) // MUTATION:EMPTY_SPOT
            {
                ResetGrace(); // grace reset: the slot not seen, or already known empty
                return Observation.NotSeen;
            }
            Observation o = SeenOutOfPlace(dt);
            if (o == Observation.Discovery)
            {
                spotKnownEmpty = true;
            }
            return o;
        }
    }
}
