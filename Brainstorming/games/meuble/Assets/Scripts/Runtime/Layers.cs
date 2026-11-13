using UnityEngine;

namespace Meuble
{
    /// <summary>
    /// The gameplay layers of PRD 8.3 (plus Furniture, docs/CONTRACT_M2.md 6), declared in
    /// ProjectSettings/TagManager.asset by Meuble.Editor.ProjectSetup. Vision raycasts use the Occluder
    /// mask only. Furniture (decoys) collides with the player and is a NavMesh source, but never occludes.
    /// </summary>
    public static class Layers
    {
        public const string OccluderName = "Occluder";
        public const string PlayerName = "Player";
        public const string InhabitantName = "Inhabitant";
        public const string FloorName = "Floor";
        public const string FurnitureName = "Furniture";

        private static bool resolved;
        private static int occluder = 6;
        private static int player = 7;
        private static int inhabitant = 8;
        private static int floor = 9;
        private static int furniture = 10;

        public static int Occluder { get { Resolve(); return occluder; } }
        public static int Player { get { Resolve(); return player; } }
        public static int Inhabitant { get { Resolve(); return inhabitant; } }
        public static int Floor { get { Resolve(); return floor; } }
        public static int Furniture { get { Resolve(); return furniture; } }
        public static int OccluderMask => 1 << Occluder;

        /// <summary>Layers whose physics colliders feed the runtime NavMesh (docs/CONTRACT_M2.md 6).</summary>
        public static int NavMeshSourceMask => (1 << Occluder) | (1 << Floor) | (1 << Furniture);

        /// <summary>What blocks the chair: walls, props and decoys (the level audit's walkable test).</summary>
        public static int ChairBlockerMask => (1 << Occluder) | (1 << Furniture);

        public static void Resolve()
        {
            if (resolved)
            {
                return;
            }
            resolved = true;
            occluder = Find(OccluderName, occluder);
            player = Find(PlayerName, player);
            inhabitant = Find(InhabitantName, inhabitant);
            floor = Find(FloorName, floor);
            furniture = Find(FurnitureName, furniture);
        }

        private static int Find(string name, int fallback)
        {
            int layer = LayerMask.NameToLayer(name);
            if (layer < 0)
            {
                Debug.LogError($"[Layers] Layer '{name}' is not declared; run Meuble > Project Setup. Using {fallback}.");
                return fallback;
            }
            return layer;
        }
    }
}
