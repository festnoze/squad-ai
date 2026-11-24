using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>
    /// BEDROOM (docs/next/progress/BEDROOM.md, ArtHandoff/Bedroom): the bedroom pack. One furniture look (the bedside table,
    /// dressing a nightstand), two items on host tops (the bedside lamp, the alarm clock) and the floor items, which stand on
    /// the floor instead of a host: <see cref="DecorDef.Host"/> is <see cref="FloorHost"/> and X, Z, Yaw are absolute level
    /// coordinates (the props' frame). Floor items are visual only like every decor item: no collider, never an occluder or a
    /// NavMesh source, so they block no sight and change no route, audit or doorway.
    /// Footprints are the GLB bounds in Unity space (glTF x negated), from ArtHandoff/Bedroom/inventory.json.
    /// </summary>
    public static partial class DecorKinds
    {
        public const string BedsideTable = "bedside_table";
        public const string BedsideLamp = "bedside_lamp";
        public const string AlarmClock = "alarm_clock";
        public const string ClothesHeap = "clothes_heap";
        public const string OddSocks = "odd_socks";
        public const string Slippers = "slippers";
        public const string LaundryBasket = "laundry_basket";
        public const string FloorBookStack = "floor_book_stack";
        public const string TeddyBear = "teddy_bear";

        /// <summary>The <see cref="DecorDef.Host"/> of an item lying on the floor (X, Z, Yaw absolute).</summary>
        public const string FloorHost = "floor";

        /// <summary>The most floor items one level may set (on top of <see cref="MaxPerLevel"/> items on hosts).</summary>
        public const int MaxFloorPerLevel = 4;

        /// <summary>The clearance a floor item keeps from its room's bounds (half a wall and a little air).</summary>
        public const float FloorWallClearance = 0.06f;

        /// <summary>The largest nightstand the bedside table look dresses (width, height): beyond, it would read stretched.</summary>
        public const float BedsideTableMaxWidth = 0.7f;
        public const float BedsideTableMaxHeight = 0.75f;

        /// <summary>The bedside lamp's bulb centre above its contact point and the glow RoomLights puts in it (diameter).</summary>
        public const float BedsideLampBulbY = 0.2f;
        public const float BedsideLampBulbSize = 0.05f;

        public static bool IsFloor(string host) => host == FloorHost;

        /// <summary>True for a kind that may lie on the floor (<see cref="FloorHost"/>).</summary>
        public static bool AllowsFloor(string kind) => System.Array.IndexOf(HostKinds(kind), FloorHost) >= 0;

        /// <summary>True when the bedside table look fits a nightstand of size <paramref name="size"/> without reading stretched.</summary>
        public static bool BedsideTableFits(Vector3 size) =>
            size.x <= BedsideTableMaxWidth + LevelDef.Eps && size.y <= BedsideTableMaxHeight + LevelDef.Eps;

        private static bool TryBedroomFootprint(string kind, out Rect footprint, out float height)
        {
            switch (kind)
            {
                case BedsideLamp: return Set(-0.115f, -0.115f, 0.115f, 0.115f, 0.3f, out footprint, out height);
                // The dial faces +z.
                case AlarmClock: return Set(-0.056f, -0.026f, 0.056f, 0.0245f, 0.129f, out footprint, out height);
                case ClothesHeap: return Set(-0.44f, -0.2972f, 0.3443f, 0.2893f, 0.09f, out footprint, out height);
                case OddSocks: return Set(-0.1802f, -0.1224f, 0.1159f, 0.167f, 0.0234f, out footprint, out height);
                // The toes point +z.
                case Slippers: return Set(-0.124f, -0.1293f, 0.1118f, 0.149f, 0.076f, out footprint, out height);
                case LaundryBasket: return Set(-0.219f, -0.219f, 0.219f, 0.219f, 0.4733f, out footprint, out height);
                case FloorBookStack: return Set(-0.12f, -0.0909f, 0.12f, 0.0909f, 0.13f, out footprint, out height);
                // Sitting, facing +z (its feet reach forward).
                case TeddyBear: return Set(-0.1009f, -0.062f, 0.0977f, 0.1276f, 0.272f, out footprint, out height);
                default:
                    footprint = default;
                    height = 0f;
                    return false;
            }
        }

        /// <summary>The bedroom items' hosts: the lamp and the clock on a bedside top, the rest on the floor (books and bear also on tops).</summary>
        private static string[] BedroomHostKinds(string kind)
        {
            switch (kind)
            {
                case BedsideLamp: return new[] { PropKinds.Nightstand, PropKinds.Cabinet, PropKinds.Table };
                case AlarmClock: return new[] { PropKinds.Nightstand, PropKinds.Cabinet, PropKinds.Bookshelf, PropKinds.Table };
                case ClothesHeap:
                case OddSocks:
                case Slippers:
                case LaundryBasket: return new[] { FloorHost };
                case FloorBookStack: return new[] { FloorHost, PropKinds.Nightstand, PropKinds.Cabinet, PropKinds.Table };
                case TeddyBear: return new[] { FloorHost, PropKinds.Nightstand, PropKinds.Cabinet, PropKinds.Bookshelf };
                default: return new string[0];
            }
        }

        private static string[] BedroomLookKinds(string look)
        {
            return look == BedsideTable ? new[] { PropKinds.Nightstand } : new string[0];
        }
    }
}
