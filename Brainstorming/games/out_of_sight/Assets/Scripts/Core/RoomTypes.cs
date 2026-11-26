using System.Text;

namespace OutOfSight.Core
{
    /// <summary>
    /// M8 room types (docs/m8/ROOMS_PLAN.md 2): the values of a room's optional "type" field, and the type a room without
    /// one gets from its id (<see cref="Infer"/>). A type is presentation and level dressing only: no rule reads it (the
    /// secondary lights of RoomLights and the phase 2 level dressing do).
    /// </summary>
    public static class RoomTypes
    {
        public const string Bathroom = "bathroom";
        public const string Kitchen = "kitchen";
        public const string Dining = "dining";
        public const string Living = "living";
        public const string Bedroom = "bedroom";
        public const string Study = "study";
        public const string Hall = "hall";
        public const string Corridor = "corridor";
        public const string Other = "other";

        /// <summary>Every accepted "type" value, in the order of the plan's table.</summary>
        public static readonly string[] All = { Bathroom, Kitchen, Dining, Living, Bedroom, Study, Hall, Corridor, Other };

        // The plan's inference table (section 2). Longest keys first, so "salle_de_bain" wins over "salle" and "cafeteria"
        // over "cafet". A key matches an id equal to it or starting with it and then anything but a letter ("couloir_est",
        // "chambre2", "sdb-haut"); a stem key (couloir, galerie: "couloir*" in the plan; salle_de_bain, for "salle_de_bains")
        // matches any id that starts with it.
        private static readonly (string key, string type, bool stem)[] Table =
        {
            ("salle_a_manger", Dining, false),
            ("salle_de_bain", Bathroom, true),
            ("bibliotheque", Study, false),
            ("cafeteria", Kitchen, false),
            ("vestibule", Hall, false),
            ("direction", Study, false),
            ("openspace", Study, false),
            ("archives", Study, false),
            ("couloir", Corridor, true),
            ("galerie", Corridor, true),
            ("cuisine", Kitchen, false),
            ("chambre", Bedroom, false),
            ("boudoir", Bedroom, false),
            ("plateau", Study, false),
            ("reunion", Study, false),
            ("veranda", Living, false),
            ("accueil", Hall, false),
            ("office", Kitchen, false),
            ("bureau", Study, false),
            ("entree", Hall, false),
            ("sejour", Living, false),
            ("salon", Living, false),
            ("salle", Dining, false),
            ("cafet", Kitchen, false),
            ("bain", Bathroom, false),
            ("hall", Hall, false),
            ("sdb", Bathroom, false),
        };

        /// <summary>True for one of <see cref="All"/> (exact, lower case).</summary>
        public static bool IsKnown(string type)
        {
            return type != null && System.Array.IndexOf(All, type) >= 0;
        }

        /// <summary>
        /// The type of a room whose data gives none, from its id: case and accents ignored ("Entrée" is a hall), then the
        /// plan's table; <see cref="Other"/> for an id the table does not know, or no id (an M1 single room).
        /// </summary>
        public static string Infer(string id)
        {
            string s = Normalize(id);
            if (s.Length == 0)
            {
                return Other;
            }
            foreach ((string key, string type, bool stem) in Table)
            {
                if (!s.StartsWith(key, System.StringComparison.Ordinal))
                {
                    continue;
                }
                if (stem || s.Length == key.Length || !char.IsLetter(s[key.Length]))
                {
                    return type;
                }
            }
            return Other;
        }

        /// <summary>The type of <paramref name="room"/>: its own when it gives one, else <see cref="Infer"/> of its id.</summary>
        public static string Of(RoomDef room)
        {
            return room == null ? Other : room.Type;
        }

        /// <summary>
        /// Lower case, trimmed, the French accents folded ("Entrée " is "entree"). By hand rather than string.Normalize, whose
        /// tables a stripped IL2CPP player may not carry.
        /// </summary>
        private static string Normalize(string id)
        {
            if (string.IsNullOrEmpty(id))
            {
                return string.Empty;
            }
            string lower = id.Trim().ToLowerInvariant();
            var sb = new StringBuilder(lower.Length);
            foreach (char c in lower)
            {
                sb.Append(Fold(c));
            }
            return sb.ToString();
        }

        private static char Fold(char c)
        {
            switch (c)
            {
                case 'à': case 'â': case 'ä': return 'a';
                case 'é': case 'è': case 'ê': case 'ë': return 'e';
                case 'î': case 'ï': return 'i';
                case 'ô': case 'ö': return 'o';
                case 'ù': case 'û': case 'ü': return 'u';
                case 'ç': return 'c';
                default: return c;
            }
        }
    }
}
