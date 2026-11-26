using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>
    /// The static prop kinds (<see cref="PropDef.Kind"/>). M8 room variety (docs/m8/ROOMS_PLAN.md 3) adds the ten room
    /// objects below to the M2 to M6 kinds. Every kind is a static prop: the procedural parts of FurnitureKit give it its
    /// colliders on the Occluder layer when the level sets <see cref="PropDef.Occluder"/> (the default), none otherwise, it is
    /// never player furniture and never a hiding spot (only the wardrobe hides). A new kind's front is its local -z face (the
    /// sofa's seat side, the cabinet's doors), its back on +z against a wall, at yaw 0.
    /// A <see cref="Bed"/> builds exactly the colliders of a "sofa" of the same size (the M2 beds are sofas named "Lit"),
    /// so swapping the kind changes the look only. The level validator rejects an unknown kind (a typo would otherwise build
    /// a plain box silently); null or empty stays the plain box of M1 data.
    /// </summary>
    public static class PropKinds
    {
        // ----- M2 to M6 kinds -----
        public const string Sofa = "sofa";
        public const string Bookshelf = "bookshelf";
        public const string Table = "table";
        public const string Cabinet = "cabinet";
        public const string Counter = "counter";
        public const string Plant = "plant";
        public const string Box = "box";

        // ----- M8 room objects (ROOMS_PLAN 3) -----
        public const string Bathtub = "bathtub";
        /// <summary>A vanity with its ceramic basin, and a mirror above it when the box is tall enough.</summary>
        public const string Washbasin = "washbasin";
        public const string Toilet = "toilet";
        /// <summary>The kitchen sink unit: a counter with a basin and a tap.</summary>
        public const string KitchenSink = "kitchen_sink";
        /// <summary>The cooker: an oven under a hob.</summary>
        public const string Stove = "stove";
        public const string Fridge = "fridge";
        public const string CoffeeTable = "coffee_table";
        public const string TvUnit = "tv_unit";
        public const string Bed = "bed";
        public const string Nightstand = "nightstand";

        /// <summary>The ten M8 kinds, in the order of ROOMS_PLAN 3.</summary>
        public static readonly string[] RoomObjects =
        {
            Bathtub, Washbasin, Toilet, KitchenSink, Stove, Fridge, CoffeeTable, TvUnit, Bed, Nightstand,
        };

        /// <summary>Every known prop kind: the M2 to M6 ones (armchair and wardrobe included), then the M8 ones.</summary>
        public static readonly string[] All =
        {
            Sofa, Bookshelf, Table, Cabinet, Counter, Plant, BodyKinds.Armchair, WardrobeRule.Kind, Box,
            Bathtub, Washbasin, Toilet, KitchenSink, Stove, Fridge, CoffeeTable, TvUnit, Bed, Nightstand,
        };

        /// <summary>True for a kind the builder knows; null or empty counts (the plain box of M1 data).</summary>
        public static bool IsKnown(string kind)
        {
            return string.IsNullOrEmpty(kind) || System.Array.IndexOf(All, kind) >= 0;
        }

        /// <summary>
        /// The size (metres) an M8 kind is drawn for, the one to put in the level unless the room asks for another: every
        /// part is proportioned on it and scales with the box. Zero for any other kind.
        /// <list type="bullet">
        /// <item>bathtub 1.7 x 0.6 x 0.75: the rim at 0.56, the tap on the back rim reaches the top;</item>
        /// <item>washbasin 0.6 x 1.8 x 0.45: the basin top at 0.85, the mirror above it up to 1.75 (no mirror under 1.3 m);</item>
        /// <item>toilet 0.4 x 0.8 x 0.65: the closed lid at 0.42, the cistern on the back up to the top;</item>
        /// <item>kitchen_sink 1.2 x 1.08 x 0.6: the worktop at 0.9 (the height minus the 0.18 m tap), as a counter;</item>
        /// <item>stove 0.6 x 0.9 x 0.6, fridge 0.7 x 1.8 x 0.7 (the M2 "Frigo" cabinet), coffee_table 1.0 x 0.42 x 0.55;</item>
        /// <item>tv_unit 1.4 x 1.1 x 0.45: a low cabinet with the screen standing on it;</item>
        /// <item>bed 1.6 x 0.55 x 2.0 (the M2 "Lit" sofa), nightstand 0.45 x 0.55 x 0.4.</item>
        /// </list>
        /// </summary>
        public static Vector3 DefaultSize(string kind)
        {
            switch (kind)
            {
                case Bathtub: return new Vector3(1.7f, 0.6f, 0.75f);
                case Washbasin: return new Vector3(0.6f, 1.8f, 0.45f);
                case Toilet: return new Vector3(0.4f, 0.8f, 0.65f);
                case KitchenSink: return new Vector3(1.2f, 1.08f, 0.6f);
                case Stove: return new Vector3(0.6f, 0.9f, 0.6f);
                case Fridge: return new Vector3(0.7f, 1.8f, 0.7f);
                case CoffeeTable: return new Vector3(1.0f, 0.42f, 0.55f);
                case TvUnit: return new Vector3(1.4f, 1.1f, 0.45f);
                case Bed: return new Vector3(1.6f, 0.55f, 2.0f);
                case Nightstand: return new Vector3(0.45f, 0.55f, 0.4f);
                default: return Vector3.zero;
            }
        }
    }
}
