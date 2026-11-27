namespace PainterIO.Core
{
    /// <summary>
    /// Every gameplay constant (contract 3.1). These are the defaults: a round reads them through a SimConfig, which the
    /// runtime may override (round duration, spark factor and ring delay are adjustable test settings, brief closing
    /// paragraph). Distances in world units (u), times in seconds, angles in degrees where the name says Deg.
    /// </summary>
    public static class Tuning
    {
        // Arena (R1).
        public const double ArenaHalfSize = 32.0;      // rounded square [-32, 32]^2
        public const double ArenaCornerRadius = 10.0;
        public const double ArenaMargin = 0.45;        // head center stays inside the shape inset by this (= HeadRadius)
        public const double CellSize = 0.125;          // ownership grid cell; grid is 512 x 512

        // Players and start (R2).
        public const int PlayerCount = 4;              // one human + three bots
        public const double StartDiscRadius = 3.5;
        public const double StartDiscOffset = 16.0;    // disc centers (-16,-16), (16,-16), (16,16), (-16,16) for players 0..3

        // Motion (R3, R4).
        public const double PawnSpeed = 6.0;           // u/s, constant
        public const double TurnRateDeg = 540.0;       // max heading change per second; 0 means instant turns (tests)
        public const double BorderHoldAngleDeg = 10.0; // pushing within this angle of the outward normal holds the head

        // Contacts and La Revanche (R10 to R13).
        public const double HeadRadius = 0.45;         // pearl radius (cuts and pickups)
        public const double TrailHalfWidth = 0.18;     // cut contact distance = HeadRadius + TrailHalfWidth = 0.63
        public const double HeadGrace = 1.0;           // last 1.0 u of arc behind the own head is not exposed
        public const double SparkSpeedFactor = 1.8;    // spark speed = 1.8 x PawnSpeed

        // Round (R19).
        public const double RoundDuration = 90.0;

        // Le Lasso (R15 to R17).
        public const bool LassoEnabled = true;         // Core default (tests); the runtime default is OFF (SaveData.LassoOn)
        public const double LassoFirstSpawn = 15.0;
        public const double LassoRespawn = 15.0;       // after each pickup
        public const double RingRadius = 0.6;          // pickup distance = HeadRadius + RingRadius
        public const double RingMinHeadDistance = 4.0;
        public const double RingClearance = 1.0;       // arena cells within this radius of the spawn point must be neutral
        public const double LassoMinArc = 1.0;
        public const double LassoMinArea = 0.75;       // u^2 of non-zero-winding cells needed for a pocket

        // Event engine (section 6).
        public const int TickRate = 60;                // supported range 30..240
        public const double EventEpsilonSeconds = 1e-7;
        public const int MaxEventsPerTick = 64;

        // Bots (section 9).
        public const int BotCount = 3;
    }
}
