namespace OutOfSight.Core
{
    /// <summary>
    /// Rule switches (docs/CONTRACT_M2.md 3.7). M1 and M2 return a new instance on every call, so a test
    /// can change its copy without touching anybody else's.
    /// </summary>
    public sealed class GameRules
    {
        public bool DisplacementMemory;
        public bool Hearing;
        public bool Creak;
        public bool ExitOnlyUnseen;
        // M4 (docs/CONTRACT_M4.md amendment 9.9): only the special rules are gated; BodyDef constants always apply.
        public bool Bodies;
        public bool Sitting;
        public bool Lamp;

        public static GameRules M1 => new GameRules();

        public static GameRules M4 => new GameRules
        {
            DisplacementMemory = true,
            Hearing = true,
            Creak = true,
            ExitOnlyUnseen = true,
            Bodies = true,
            Sitting = true,
            Lamp = true,
        };

        public static GameRules M2 => new GameRules
        {
            DisplacementMemory = true,
            Hearing = true,
            Creak = true,
            ExitOnlyUnseen = true,
        };
    }
}
