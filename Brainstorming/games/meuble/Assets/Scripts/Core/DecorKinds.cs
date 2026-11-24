using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>
    /// DRESSING (2026-11-24, docs/next/progress/DRESSING.md): the decor a level may set on its furniture ("decor", <see cref="DecorDef"/>)
    /// and the furniture looks a prop may wear ("dress", <see cref="PropDef.Dress"/>). Pure data: the validator checks levels
    /// against it without any asset. The footprints are those of the delivered GLBs in Unity space (glTF x negated, metres,
    /// root on the contact point), from ArtHandoff/RoomDressing and ArtHandoff/LivingRoomFurniture inventory.json; the baked
    /// meshes (DressingLibrary) are measured again at build time and the probe compares the two.
    ///
    /// Decor is visual only: no collider, never an occluder, a NavMesh source or a noise; it changes no route.
    /// </summary>
    public static partial class DecorKinds
    {
        // ----- Decor items (pack RoomDressing, then the two small items of pack LivingRoomFurniture) -----
        public const string OpenBook = "open_book";
        public const string PhotoFrame = "photo_frame";
        public const string SofaThrow = "sofa_throw";
        public const string CeramicMug = "ceramic_mug";
        public const string MagazineStack = "magazine_stack";
        public const string TvRemote = "tv_remote";
        public const string KeyDish = "key_dish";
        public const string Pothos = "tabletop_pothos";
        public const string TableLamp = "linen_table_lamp";

        // ----- Furniture looks (pack LivingRoomFurniture) and the TV the media console carries -----
        public const string WalnutCoffeeTable = "walnut_coffee_table";
        public const string WalnutMediaConsole = "walnut_media_console";
        public const string FlatScreenTv = "flat_screen_tv";

        // ----- KITCHEN (docs/next/progress/KITCHEN.md, ArtHandoff/Kitchen): utensils (decor) and furniture modules (looks) -----
        public const string Saucepan = "saucepan";
        public const string FryingPan = "frying_pan";
        public const string StockPot = "stock_pot";
        public const string Kettle = "kettle";
        public const string CuttingBoard = "cutting_board";
        public const string KitchenBaseCabinet = "kitchen_base_cabinet";
        public const string KitchenDrawerCabinet = "kitchen_drawer_cabinet";
        public const string KitchenSinkCabinet = "kitchen_sink_cabinet";
        public const string KitchenRange = "kitchen_range";
        public const string KitchenTallCabinet = "kitchen_tall_cabinet";

        /// <summary>Every decor kind a level's "decor" may name.</summary>
        public static readonly string[] Items =
        {
            OpenBook, PhotoFrame, SofaThrow, CeramicMug, MagazineStack, TvRemote, KeyDish, Pothos, TableLamp,
            Saucepan, FryingPan, StockPot, Kettle, CuttingBoard,
            // BEDROOM (DecorKindsBedroom): on tops, then on the floor (host "floor").
            BedsideLamp, AlarmClock, ClothesHeap, OddSocks, Slippers, LaundryBasket, FloorBookStack, TeddyBear,
        };

        /// <summary>Every look a prop's "dress" may name.</summary>
        public static readonly string[] Looks =
        {
            WalnutCoffeeTable, WalnutMediaConsole,
            KitchenBaseCabinet, KitchenDrawerCabinet, KitchenSinkCabinet, KitchenRange, KitchenTallCabinet,
            BedsideTable,
        };

        /// <summary>Every mesh the dressing library bakes: the items, the looks and the TV.</summary>
        public static readonly string[] Meshes =
        {
            OpenBook, PhotoFrame, SofaThrow, CeramicMug, MagazineStack, TvRemote, KeyDish, Pothos, TableLamp,
            WalnutCoffeeTable, WalnutMediaConsole, FlatScreenTv,
            Saucepan, FryingPan, StockPot, Kettle, CuttingBoard,
            KitchenBaseCabinet, KitchenDrawerCabinet, KitchenSinkCabinet, KitchenRange, KitchenTallCabinet,
            BedsideTable, BedsideLamp, AlarmClock, ClothesHeap, OddSocks, Slippers, LaundryBasket, FloorBookStack, TeddyBear,
        };

        /// <summary>The kitchen looks: drawn as a run of modules along the prop (<see cref="KitchenRun"/>), not box fitted whole.</summary>
        public static bool IsKitchenLook(string look) =>
            look == KitchenBaseCabinet || look == KitchenDrawerCabinet || look == KitchenSinkCabinet || look == KitchenRange || look == KitchenTallCabinet;

        /// <summary>The native width of the base modules (base, drawer, range, tall) and of the sink module, metres.</summary>
        public const float KitchenModuleWidth = 0.6f;
        public const float KitchenSinkWidth = 0.8f;

        /// <summary>
        /// The modules a kitchen look lays along a prop of length <paramref name="length"/> (its longer horizontal side), in
        /// order. A base or drawer look fills the length with about 0.6 m modules, alternating doors and drawers (starting
        /// with its own); a sink look puts the sink module in the middle and base modules on either side when the prop is
        /// 0.3 m or more longer than it; the range and the tall cabinet are one module. The builder then scales the run to
        /// the exact length.
        /// </summary>
        public static string[] KitchenRun(string look, float length)
        {
            if (look == KitchenBaseCabinet || look == KitchenDrawerCabinet)
            {
                int n = Mathf.Max(1, Mathf.RoundToInt(length / KitchenModuleWidth));
                string other = look == KitchenBaseCabinet ? KitchenDrawerCabinet : KitchenBaseCabinet;
                var run = new string[n];
                for (int i = 0; i < n; i++)
                {
                    run[i] = i % 2 == 0 ? look : other;
                }
                return run;
            }
            if (look == KitchenSinkCabinet)
            {
                float rest = length - KitchenSinkWidth;
                int n = rest < 0.3f ? 0 : Mathf.Max(1, Mathf.RoundToInt(rest / KitchenModuleWidth));
                int left = n / 2;
                var run = new string[n + 1];
                for (int i = 0; i <= n; i++)
                {
                    run[i] = i == left ? KitchenSinkCabinet : (i % 2 == 0 ? KitchenDrawerCabinet : KitchenBaseCabinet);
                }
                return run;
            }
            return IsKitchenLook(look) ? new[] { look } : new string[0];
        }

        /// <summary>The prop heights a kitchen look may dress (metres, inclusive): it is never squashed or stretched past these.</summary>
        public static void KitchenHeights(string look, out float min, out float max)
        {
            switch (look)
            {
                case KitchenSinkCabinet: min = 0.85f; max = 1.15f; return;
                case KitchenTallCabinet: min = 1.5f; max = 2.3f; return;
                default: min = 0.75f; max = 1.0f; return;
            }
        }

        public static bool IsItem(string kind) => kind != null && System.Array.IndexOf(Items, kind) >= 0;

        public static bool IsLook(string look) => look != null && System.Array.IndexOf(Looks, look) >= 0;

        /// <summary>
        /// The planar footprint of an item in its own frame (x min, z min, x max, z max; +z is the item's front: the reader's
        /// side of the book, the photo, the throw's long side) and its height above its contact point. False for an unknown kind.
        /// </summary>
        public static bool TryFootprint(string kind, out Rect footprint, out float height)
        {
            switch (kind)
            {
                case OpenBook: return Set(-0.171f, -0.116f, 0.171f, 0.116f, 0.034f, out footprint, out height);
                case PhotoFrame: return Set(-0.078f, -0.076f, 0.078f, 0.0373f, 0.1905f, out footprint, out height);
                // The throw's pivot is the crest of its fold on the backrest top; it hangs 0.44 m down its long side (+z).
                case SofaThrow: return Set(-0.28f, -0.113f, 0.28f, 0.1407f, 0.0037f, out footprint, out height);
                // The handle is on -x after import.
                case CeramicMug: return Set(-0.076f, -0.0429f, 0.044f, 0.0429f, 0.084f, out footprint, out height);
                case MagazineStack: return Set(-0.1263f, -0.0909f, 0.117f, 0.0869f, 0.0283f, out footprint, out height);
                case TvRemote: return Set(-0.0235f, -0.077f, 0.0235f, 0.077f, 0.0219f, out footprint, out height);
                case KeyDish: return Set(-0.079f, -0.0593f, 0.079f, 0.0593f, 0.026f, out footprint, out height);
                case Pothos: return Set(-0.1241f, -0.136f, 0.1015f, 0.1482f, 0.2383f, out footprint, out height);
                case TableLamp: return Set(-0.115f, -0.1121f, 0.115f, 0.1121f, 0.35f, out footprint, out height);
                // KITCHEN: the pan handles are on -x after import; the board carries its knife and carrot slices.
                case Saucepan: return Set(-0.25f, -0.109f, 0.109f, 0.109f, 0.15f, out footprint, out height);
                case FryingPan: return Set(-0.3f, -0.1336f, 0.137f, 0.1336f, 0.045f, out footprint, out height);
                case StockPot: return Set(-0.154f, -0.125f, 0.154f, 0.125f, 0.247f, out footprint, out height);
                case Kettle: return Set(-0.1682f, -0.1f, 0.1f, 0.1f, 0.253f, out footprint, out height);
                case CuttingBoard: return Set(-0.19f, -0.125f, 0.2073f, 0.125f, 0.034f, out footprint, out height);
                default: return TryBedroomFootprint(kind, out footprint, out height);
            }
        }

        private static bool Set(float xMin, float zMin, float xMax, float zMax, float h, out Rect footprint, out float height)
        {
            footprint = Rect.MinMaxRect(xMin, zMin, xMax, zMax);
            height = h;
            return true;
        }

        /// <summary>
        /// The prop kinds an item may stand on (the delivery's placement rules): the throw on a sofa back, the book and the mug on
        /// a side table or a desk (the mug also on a counter), the frame on a console, a shelf or a bedside table, the magazines
        /// and the remote on a coffee table (or a low shelf, a console), the keys on a console by the entrance, the pothos on a
        /// table or a wardrobe top, the lamp on a bedside or side table.
        /// </summary>
        public static string[] HostKinds(string kind)
        {
            switch (kind)
            {
                case SofaThrow: return new[] { PropKinds.Sofa };
                case OpenBook: return new[] { PropKinds.Table, PropKinds.CoffeeTable, PropKinds.Nightstand, PropKinds.Cabinet };
                case CeramicMug: return new[] { PropKinds.Table, PropKinds.CoffeeTable, PropKinds.Nightstand, PropKinds.Cabinet, PropKinds.Counter };
                case PhotoFrame: return new[] { PropKinds.Cabinet, PropKinds.Counter, PropKinds.Nightstand, PropKinds.Bookshelf, PropKinds.Table };
                case MagazineStack: return new[] { PropKinds.CoffeeTable, PropKinds.Bookshelf, PropKinds.Table, PropKinds.Cabinet, PropKinds.Counter };
                case TvRemote: return new[] { PropKinds.CoffeeTable, PropKinds.Table, PropKinds.Counter, PropKinds.Cabinet };
                case KeyDish: return new[] { PropKinds.Cabinet, PropKinds.Counter, PropKinds.Table, PropKinds.Nightstand, PropKinds.Bookshelf };
                case Pothos: return new[] { PropKinds.Table, PropKinds.CoffeeTable, PropKinds.Nightstand, PropKinds.Cabinet, PropKinds.Counter, "wardrobe", PropKinds.Bookshelf };
                case TableLamp: return new[] { PropKinds.Nightstand, PropKinds.Table, PropKinds.Cabinet };
                // KITCHEN: the pans on a stove's hob or a counter; the kettle and the board also on a (kitchen) table. Never
                // on a kitchen_sink: its box top is the tap's, 0.18 m above the worktop.
                case Saucepan:
                case FryingPan:
                case StockPot: return new[] { PropKinds.Stove, PropKinds.Counter };
                case Kettle: return new[] { PropKinds.Stove, PropKinds.Counter, PropKinds.Table };
                case CuttingBoard: return new[] { PropKinds.Counter, PropKinds.Table };
                default: return BedroomHostKinds(kind);
            }
        }

        /// <summary>The prop kinds a look may dress: the coffee table a coffee table, the media console a TV unit or a low counter or cabinet.</summary>
        public static string[] LookKinds(string look)
        {
            switch (look)
            {
                case WalnutCoffeeTable: return new[] { PropKinds.CoffeeTable };
                case WalnutMediaConsole: return new[] { PropKinds.TvUnit, PropKinds.Counter, PropKinds.Cabinet };
                // KITCHEN: the base runs a counter, the sink unit a kitchen_sink, the range a stove, the pantry a tall cabinet.
                case KitchenBaseCabinet:
                case KitchenDrawerCabinet: return new[] { PropKinds.Counter };
                case KitchenSinkCabinet: return new[] { PropKinds.KitchenSink };
                case KitchenRange: return new[] { PropKinds.Stove };
                case KitchenTallCabinet: return new[] { PropKinds.Cabinet, "wardrobe" };
                default: return BedroomLookKinds(look);
            }
        }

        /// <summary>The tallest prop a media console look may dress (a TV unit may be taller: its TV fills the rest).</summary>
        public const float ConsoleMaxHeight = 0.7f;

        /// <summary>COHERENCE: the farthest the key dish's host may stand from the exit (the front door).</summary>
        public const float KeyDishMaxExitDistance = 4.5f;

        /// <summary>The delivered flat screen TV's bounds (width, height, depth; LivingRoomFurniture inventory.json).</summary>
        public static readonly Vector3 TvNativeSize = new Vector3(1.056f, 0.647f, 0.221f);

        /// <summary>
        /// COHERENCE (docs/next/progress/COHERENCE.md): true when a prop of <paramref name="kind"/> wearing <paramref name="dress"/>
        /// carries the TV on its top: the media console look on a counter or cabinet (a TV unit draws its TV inside its own box).
        /// </summary>
        public static bool CarriesTopTv(string kind, string dress) => dress == WalnutMediaConsole && kind != PropKinds.TvUnit;

        /// <summary>TVBIG (docs/next/progress/TVBIG.md): the largest scale of the TV on a console top (twice the delivered model).</summary>
        public const float TopTvMaxScale = 2f;

        /// <summary>TVBIG: the strip of a console top kept clear in front of the TV's foot, for the remote and other small items.</summary>
        public const float TopTvFrontStrip = 0.12f;

        /// <summary>
        /// The width and height scale of the TV standing on a console top of size <paramref name="hostSize"/>: twice native at
        /// most (TVBIG), within 90 % of the console's width.
        /// </summary>
        public static float TopTvScale(Vector3 hostSize)
        {
            return Mathf.Min(TopTvMaxScale, hostSize.x * 0.9f / TvNativeSize.x);
        }

        /// <summary>
        /// TVBIG: the depth scale of the TV on a console top of size <paramref name="hostSize"/>: its width and height scale,
        /// or less when the console is too shallow, so its foot stays on the top (1 cm off the back) and leaves
        /// <see cref="TopTvFrontStrip"/> in front of it. A thinner foot does not show; a foot hanging off the top would.
        /// </summary>
        public static float TopTvDepthScale(Vector3 hostSize)
        {
            return Mathf.Min(TopTvScale(hostSize), Mathf.Max(hostSize.z - 0.01f - TopTvFrontStrip, 0.01f) / TvNativeSize.z);
        }

        /// <summary>
        /// The TV's footprint on a console top of size <paramref name="hostSize"/>, in the host's frame (x min, z min, x max, z max):
        /// centred in x, against the back (local +z, 1 cm in), its screen facing the console's front (local -z). Decor items on
        /// that console must stay out of it (LevelValidator).
        /// </summary>
        public static Rect TopTvFootprint(Vector3 hostSize)
        {
            float k = TopTvScale(hostSize);
            float back = hostSize.z * 0.5f - 0.01f;
            float halfWidth = TvNativeSize.x * k * 0.5f;
            return Rect.MinMaxRect(-halfWidth, back - TvNativeSize.z * TopTvDepthScale(hostSize), halfWidth, back);
        }

        /// <summary>
        /// The most items on hosts one level may set ("a lived-in feel without clutter"). ROOMS (docs/next/progress/ROOMS.md)
        /// raised it from 6 to 10: the living room set plus 2 or 3 kitchen utensils and a bedside lamp and clock.
        /// </summary>
        public const int MaxPerLevel = 10;

        /// <summary>
        /// The backrest thickness of the procedural sofa of size <paramref name="size"/> (FurnitureKit.Sofa builds exactly this
        /// one, on local +z). A model sofa's own backrest is measured on its mesh (ModelCatalog.Entry.backrestSpan, THROWFIX);
        /// the Kenney lounge sofa's comes out within 2 cm of it.
        /// </summary>
        public static float SofaBackDepth(Vector3 size) => Mathf.Min(0.22f, size.z * 0.25f);

        /// <summary>The inner gap of the throw's two hanging sides (measured on the GLB): the backrest depth it fits unscaled.</summary>
        public const float ThrowNativeGap = 0.15f;

        /// <summary>The largest depth scale the throw takes to fit a thick backrest.</summary>
        public const float ThrowMaxDepthScale = 1.6f;

        /// <summary>
        /// THROWFIX: how far the draped throw's flat top lies above the backrest's top (the delivered crest's own 3.7 mm, so
        /// the throw never fights the backrest's top face).
        /// </summary>
        public const float ThrowClearance = 0.0037f;

        /// <summary>
        /// The throw's depth scale on a backrest <paramref name="backrestDepth"/> thick ("adjust the depth to the backrest
        /// thickness"): never below 1, never above <see cref="ThrowMaxDepthScale"/>.
        /// </summary>
        public static float ThrowDepthScale(float backrestDepth)
        {
            return Mathf.Clamp(backrestDepth / ThrowNativeGap, 1f, ThrowMaxDepthScale);
        }

        /// <summary>
        /// The local z of the backrest's centre line of the procedural sofa of size <paramref name="size"/> (on +z). The builder
        /// uses the drawn sofa's real backrest (LevelBuilder.SofaBackrest); the validator, which has no model, this one.
        /// </summary>
        public static float BackrestCentre(Vector3 size)
        {
            return size.z * 0.5f - SofaBackDepth(size) * 0.5f;
        }
    }

    /// <summary>
    /// DRESSING: one decor item on a host prop. <see cref="X"/>, <see cref="Z"/> and <see cref="Yaw"/> are in the host's frame
    /// (metres from its centre, degrees from its yaw); the item stands on the host's top. A throw's <see cref="Z"/> is measured
    /// from the backrest's centre line (0: centred on it), its yaw 0 hangs the long side behind the back, 180 in front.
    /// </summary>
    public sealed class DecorDef
    {
        public string Kind;
        /// <summary>The <see cref="PropDef.Name"/> of the host prop.</summary>
        public string Host;
        public float X;
        public float Z;
        public float Yaw;
    }
}
