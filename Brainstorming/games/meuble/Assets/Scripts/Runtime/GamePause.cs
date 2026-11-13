namespace Meuble
{
    /// <summary>
    /// Global pause flag (docs/CONTRACT_M3.md 6), set by GameState.Paused. Interpolated visuals hold their
    /// last fixed step pose (alpha 1) and animations stop while it is true. Owned by the integrator.
    /// </summary>
    public static class GamePause
    {
        public static bool IsPaused;
    }
}
