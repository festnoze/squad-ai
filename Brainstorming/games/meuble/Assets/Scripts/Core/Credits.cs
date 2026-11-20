using System.Collections.Generic;
using System.Text;

namespace OutOfSight.Core
{
    /// <summary>
    /// The Credits page's content (Menu.BuildCredits), in English and French: one list, so the screen and the licence
    /// check read the same text. docs/LICENSES.md stays the source of truth for every third party asset; the EditMode
    /// test CreditsTests fails when a CC BY or SIL OFL row of it (title, author, licence, and the source URL CC BY asks
    /// for) or a CC0 author or pack is missing here. Third party names and titles are kept exactly as their pages give them.
    /// </summary>
    public static class Credits
    {
        /// <summary>How a line shows: a section heading, a main line, or a smaller detail line under it.</summary>
        public enum Kind
        {
            Heading,
            Line,
            Detail,
        }

        /// <summary>One line of the page: its kind and its English and French text.</summary>
        public readonly struct Entry
        {
            public readonly Kind Kind;
            public readonly string English;
            public readonly string French;

            public Entry(Kind kind, string english, string french)
            {
                Kind = kind;
                English = english;
                French = french;
            }

            /// <summary>The text in <paramref name="language"/> (normalized: anything but French is English).</summary>
            public string Text(string language) => Strings.NormalizeLanguage(language) == Strings.French ? French : English;
        }

        private static Entry H(string en, string fr) => new Entry(Kind.Heading, en, fr);
        private static Entry L(string en, string fr) => new Entry(Kind.Line, en, fr);
        private static Entry L(string both) => new Entry(Kind.Line, both, both);
        private static Entry D(string en, string fr) => new Entry(Kind.Detail, en, fr);
        private static Entry D(string both) => new Entry(Kind.Detail, both, both);

        private const string CcBy = "https://creativecommons.org/licenses/by/4.0/";

        /// <summary>Every line of the page, top to bottom.</summary>
        public static readonly IReadOnlyList<Entry> All = new[]
        {
            H("A game by", "Un jeu de"),
            L("Etienne & Louis"),

            H("Development", "Développement"),
            L("Developed with Claude Code (Anthropic)", "Développé avec Claude Code (Anthropic)"),
            D("AI-assisted development, directed by Etienne & Louis", "Développement assisté par IA, piloté par Etienne & Louis"),

            H("Engine", "Moteur"),
            L("Made with Unity (Unity Technologies)", "Réalisé avec Unity (Unity Technologies)"),
            D("Universal Render Pipeline (URP), Input System, Unity UI"),

            // docs/LICENSES.md, section Music: CC BY 4.0 asks for the title, the author, the source, the licence with its
            // link, and an indication of the changes made.
            H("Music", "Musique"),
            L("\"Sneaky Snitch\" (title screen), Kevin MacLeod (incompetech.com)",
                "\"Sneaky Snitch\" (écran titre), Kevin MacLeod (incompetech.com)"),
            // The source URL alone on its line (an unbreakable word: a prefix would push it to a line of its own anyway).
            D("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sneaky%20Snitch.mp3"),
            D("Licensed under Creative Commons: By Attribution 4.0 License (CC BY 4.0), " + CcBy,
                "Sous licence Creative Commons Attribution 4.0 (CC BY 4.0), " + CcBy),
            D("Changes: cut to a seamless loop (11.52 to 77.72 s), loudness normalised",
                "Modifications : coupé en boucle (11,52 à 77,72 s), volume normalisé"),
            L("\"Investigations\" (levels), Kevin MacLeod (incompetech.com)",
                "\"Investigations\" (niveaux), Kevin MacLeod (incompetech.com)"),
            D("https://incompetech.com/music/royalty-free/mp3-royaltyfree/Investigations.mp3"),
            D("Licensed under Creative Commons: By Attribution 4.0 License (CC BY 4.0), " + CcBy,
                "Sous licence Creative Commons Attribution 4.0 (CC BY 4.0), " + CcBy),
            D("Changes: cut to a seamless loop (18.11 to 58.53 s), loudness normalised",
                "Modifications : coupé en boucle (18,11 à 58,53 s), volume normalisé"),

            // docs/LICENSES.md, section Audio: every recording is CC0 1.0 (no attribution required, credited anyway).
            H("Sound effects", "Effets sonores"),
            D("CC0 1.0 (public domain), from OpenGameArt.org; cut, filtered and normalised for the game",
                "CC0 1.0 (domaine public), sur OpenGameArt.org ; coupés, filtrés et normalisés pour le jeu"),
            L("rubberduck: \"75 CC0 breaking / falling / hit sfx\", \"100 CC0 metal and wood SFX\", \"100 CC0 SFX\"",
                "rubberduck : \"75 CC0 breaking / falling / hit sfx\", \"100 CC0 metal and wood SFX\", \"100 CC0 SFX\""),
            L("Kenney (kenney.nl): \"50 RPG sound effects\", \"85 Short music jingles\", \"Interface Sounds\"",
                "Kenney (kenney.nl) : \"50 RPG sound effects\", \"85 Short music jingles\", \"Interface Sounds\""),
            L("StarNinjas: \"Saw or Wood Impact\"", "StarNinjas : \"Saw or Wood Impact\""),
            L("Longor: \"Airvent Loop\"", "Longor : \"Airvent Loop\""),
            L("bart: \"Ticking clock.\"", "bart : \"Ticking clock.\""),
            L("qubodup: \"Door open, door close\"", "qubodup : \"Door open, door close\""),
            L("0new4y: \"Game Over Trumpet SFX\"", "0new4y : \"Game Over Trumpet SFX\""),
            L("TinyWorlds: \"huh?\"", "TinyWorlds : \"huh?\""),
            D("The other sounds (dog, robot, voices, creaks) are synthesized by the game.",
                "Les autres sons (chien, robot, voix, grincements) sont synthétisés par le jeu."),

            // docs/LICENSES.md, section Models: CC0 1.0, through poly.pizza.
            H("3D models", "Modèles 3D"),
            D("CC0 1.0 (public domain), via poly.pizza", "CC0 1.0 (domaine public), via poly.pizza"),
            L("Kenney (kenney.nl): \"Furniture Kit\"", "Kenney (kenney.nl) : \"Furniture Kit\""),
            L("Quaternius: \"Animated Men Pack\", \"Animated Women Pack\", \"Animated Animal Pack\"",
                "Quaternius : \"Animated Men Pack\", \"Animated Women Pack\", \"Animated Animal Pack\""),
            D("The inhabitants are rounded versions of the Quaternius models.",
                "Les habitants sont des versions arrondies des modèles de Quaternius."),

            // docs/LICENSES.md, section Fonts: SIL OFL 1.1, its licence text ships next to the font.
            H("Fonts", "Polices"),
            L("DM Serif Display, Colophon Foundry (from Adobe's Source Serif)",
                "DM Serif Display, Colophon Foundry (d'après Source Serif d'Adobe)"),
            D("Copyright 2014-2018 Adobe, Copyright 2019 Google LLC. SIL Open Font License 1.1 (openfontlicense.org), licence text included with the game",
                "Copyright 2014-2018 Adobe, Copyright 2019 Google LLC. SIL Open Font License 1.1 (openfontlicense.org), texte de la licence fourni avec le jeu"),
            D("Interface text: Unity's built-in font", "Texte de l'interface : police intégrée de Unity"),

            // docs/LICENSES.md, sections Environment and Characters: not third party.
            H("Textures and images", "Textures et images"),
            L("Environment, character and clothing images: provided for the game by its creators",
                "Images des décors, des personnages et des vêtements : fournies pour le jeu par ses créateurs"),
            D("Wall and floor finishes: procedural, own creation; the bathroom and kitchen tiles, the travertine and the arches and pinstripe wallpapers: provided by the game's creators",
                "Finitions des murs et des sols : procédurales, création originale ; carrelages des salles de bain et des cuisines, travertin, papiers peints à arches et à rayures : fournis par les créateurs du jeu"),

            H("Thank you for playing!", "Merci d'avoir joué !"),
        };

        /// <summary>Every line in <paramref name="language"/>, one per line (the licence check reads this).</summary>
        public static string FullText(string language)
        {
            var text = new StringBuilder();
            foreach (Entry entry in All)
            {
                text.AppendLine(entry.Text(language));
            }
            return text.ToString();
        }
    }
}
