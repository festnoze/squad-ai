namespace Viewpoint
{
    /// <summary>
    /// Physics layer indices and their bitmasks. The indices mirror the layer
    /// names already declared in ProjectSettings (PRD section 15.3).
    ///
    /// Collision matrix, set in the project settings, not here: World collides
    /// with World (crates rest on the ground and on each other) and with Player.
    /// Interact collides with nothing: its trigger colliders exist only to be
    /// found by the interaction raycast. PhotoStudio collides with nothing and is
    /// culled from the main camera and the main light.
    /// </summary>
    public static class Layers
    {
        public const int World = 6, Player = 7, Interact = 8, PhotoStudio = 9;

        public const int WorldMask = 1 << World;
        public const int PlayerMask = 1 << Player;
        public const int InteractMask = 1 << Interact;
        public const int PhotoStudioMask = 1 << PhotoStudio;
    }
}
