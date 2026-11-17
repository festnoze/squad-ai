namespace Meuble.Core
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5.md 3 and 16.12, PRD 5.4): the per-inhabitant values of a personality, or of the dog. Data rows
    /// like BodyDef: the table of CONTRACT_M5 3, verbatim. The default row equals the M1 to M4 constants field by field
    /// (CoreM5Tests checks every field), so levels 1 to 7 behave exactly as before.
    /// <para>
    /// Column meanings: <see cref="HearingFactor"/> scales every noise radius this inhabitant hears,
    /// <see cref="SuspicionFactor"/> every suspicion gain, <see cref="Tolerance"/> replaces
    /// <see cref="Tuning.DisplacementTolerance"/> in its memory, and <see cref="CarryFactor"/> scales its carry speed.
    /// The dog's "-" columns are 0 (it never hears, suspects or carries), and its tolerance stays the default one (it
    /// has no memory). <see cref="Model"/> and <see cref="Tint"/> are the watchers agent's (<see cref="Look"/>).
    /// </para>
    /// </summary>
    public sealed class PersonalityDef
    {
        public const string Default = "default";
        public const string Dreamer = "dreamer";
        public const string Watchful = "watchful";
        public const string Hurried = "hurried";
        public const string Granny = "granny";
        public const string Teen = "teen";
        public const string Tidy = "tidy";
        public const string Dog = "dog";

        public static readonly string[] All = { Default, Dreamer, Watchful, Hurried, Granny, Teen, Tidy, Dog };

        public string Id;
        /// <summary>Strings key of the shown name (null for default).</summary>
        public string NameKey;
        /// <summary>Strings key of the one-line habit shown on the intro card (null for default).</summary>
        public string TraitKey;
        /// <summary>Catalog model id; an explicit InhabitantDef.Model wins.</summary>
        public string Model;
        /// <summary>Clothes tint (hex); an explicit InhabitantDef.BodyColor wins.</summary>
        public string Tint;
        public float WalkSpeed;
        public float ViewRange;
        public float HalfAngle;
        public float EyeHeight;
        public float HearingFactor;
        public float SuspicionFactor;
        public float Tolerance;
        public float CarryFactor;
        /// <summary>Displacement memory, suspicion, investigations, carries and the lamp switch-on.</summary>
        public bool Memory;
        public bool Hears;
        public bool CountsForCatch;
        public bool CountsForExit;
        public bool Sits;
        public bool Barks;

        /// <summary>The row of an id, a new instance on every call; null or unknown gives default.</summary>
        public static PersonalityDef For(string id)
        {
            switch (id)
            {
                case Dreamer:
                    return Look(Human(Dreamer, 0.9f, 8f, 45f, 0.7f, 0.7f, Tuning.DisplacementTolerance, 1.0f), "quaternius.man_shorts", "#6FA8DC");
                case Watchful:
                    return Look(Human(Watchful, 1.2f, 10f, 60f, 1.0f, 1.5f, 0.5f, 1.0f), "quaternius.woman_jacket", "#2E8B7A");
                case Hurried:
                    return Look(Human(Hurried, 1.7f, 10f, 50f, 0.5f, 1.0f, Tuning.DisplacementTolerance, 1.2f), "quaternius.man_suit", "#3D5A80");
                case Granny:
                    return Look(Human(Granny, 0.8f, 7f, 55f, 0.6f, 1.0f, Tuning.DisplacementTolerance, 0.8f), "quaternius.woman_dress", "#A88BC7");
                case Teen:
                    return Look(Human(Teen, 1.1f, 6f, 35f, 0.4f, 0.8f, Tuning.DisplacementTolerance, 1.0f), "quaternius.man_tshirt", "#8DBF3F");
                case Tidy:
                    return Look(Human(Tidy, 1.2f, 10f, 55f, 1.0f, 1.3f, 0.4f, 1.3f), "quaternius.woman", "#F4D35E");
                case Dog:
                    return new PersonalityDef
                    {
                        Id = Dog, NameKey = "person.dog", TraitKey = "person.dog.trait", Model = "quaternius.shiba", Tint = "#4F6670",
                        WalkSpeed = 1.4f, ViewRange = 6f, HalfAngle = 70f, EyeHeight = Tuning.DogEyeHeight,
                        HearingFactor = 0f, SuspicionFactor = 0f, Tolerance = Tuning.DisplacementTolerance, CarryFactor = 0f,
                        Memory = false, Hears = false, CountsForCatch = false, CountsForExit = false, Sits = false, Barks = true,
                    };
                default:
                    // The M1 to M4 inhabitant, field for field.
                    return new PersonalityDef
                    {
                        Id = Default, WalkSpeed = Tuning.WalkSpeed, ViewRange = Tuning.ViewRange, HalfAngle = Tuning.ViewHalfAngle,
                        EyeHeight = Tuning.EyeHeight, HearingFactor = 1f, SuspicionFactor = 1f, Tolerance = Tuning.DisplacementTolerance,
                        CarryFactor = 1f, Memory = true, Hears = true, CountsForCatch = true, CountsForExit = true, Sits = true,
                        Barks = false,
                    };
            }
        }

        /// <summary>
        /// The visual identity of a row (CONTRACT_M5 3, filled by the watchers agent): its catalog model and its clothes tint
        /// (sRGB hex, never red: PRD 7.2), each distinct from every other personality's. The default row has neither: the
        /// inhabitants of levels 1 to 7 name their model in the level data and keep its own clothes.
        /// </summary>
        private static PersonalityDef Look(PersonalityDef row, string model, string tint)
        {
            row.Model = model;
            row.Tint = tint;
            return row;
        }

        /// <summary>A human row: the 1.6 m eye, every role, and its name and trait keys "person.id" and "person.id.trait".</summary>
        private static PersonalityDef Human(string id, float walk, float range, float halfAngle, float hearing, float suspicion,
            float tolerance, float carry)
        {
            return new PersonalityDef
            {
                Id = id, NameKey = "person." + id, TraitKey = "person." + id + ".trait",
                WalkSpeed = walk, ViewRange = range, HalfAngle = halfAngle, EyeHeight = Tuning.EyeHeight,
                HearingFactor = hearing, SuspicionFactor = suspicion, Tolerance = tolerance, CarryFactor = carry,
                Memory = true, Hears = true, CountsForCatch = true, CountsForExit = true, Sits = true, Barks = false,
            };
        }

        /// <summary>
        /// The personality of an inhabitant, a new instance: a "dog" kind wins over any personality. An explicit
        /// <see cref="InhabitantDef.Model"/> or <see cref="InhabitantDef.BodyColor"/> wins over the row's
        /// <see cref="Model"/> and <see cref="Tint"/> (the head colour has no row counterpart).
        /// </summary>
        public static PersonalityDef ForInhabitant(InhabitantDef def)
        {
            if (def == null)
            {
                return For(null);
            }
            PersonalityDef p = def.Kind == Dog ? For(Dog) : For(def.Personality);
            if (!string.IsNullOrEmpty(def.Model))
            {
                p.Model = def.Model;
            }
            if (!string.IsNullOrEmpty(def.BodyColor))
            {
                p.Tint = def.BodyColor;
            }
            return p;
        }
    }
}
