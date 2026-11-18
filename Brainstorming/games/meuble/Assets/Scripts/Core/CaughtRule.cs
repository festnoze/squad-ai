namespace OutOfSight.Core
{
    /// <summary>
    /// PRD 4.2: a timer accumulates while the furniture is both seen and moving, resets on any step where
    /// either is false, and the player is caught when it reaches the grace.
    /// </summary>
    public sealed class CaughtRule
    {
        // Ten steps of 0.02 s sum to 0.19999999 in float: the epsilon makes "0.20 s gives caught" hold.
        private const float Epsilon = 1e-4f;

        /// <summary>M7 (CONTRACT_M7 4.1): settable, GameState sets the difficulty's grace when it builds a level.</summary>
        public float Grace { get; set; }
        public float SeenMoving { get; private set; }
        public bool Caught { get; private set; }

        public CaughtRule(float grace = Tuning.CaughtGrace)
        {
            Grace = grace;
        }

        /// <summary>Advances one fixed step and returns whether the player is caught.</summary>
        public bool Step(bool seen, bool moving, float dt)
        {
            if (Caught)
            {
                return true;
            }
            if (seen && moving)
            {
                SeenMoving += dt;
                if (SeenMoving >= Grace - Epsilon)
                {
                    Caught = true;
                }
            }
            else
            {
                SeenMoving = 0f; // MUTATION:RESET (mutation.sh removes this line)
            }
            return Caught;
        }

        public void Reset()
        {
            SeenMoving = 0f;
            Caught = false;
        }
    }
}
