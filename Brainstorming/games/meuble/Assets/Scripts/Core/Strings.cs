using System;
using System.Collections.Generic;

namespace OutOfSight.Core
{
    /// <summary>
    /// Every string shown to the player, in English (the default) and French. Each member returns the text of the current
    /// <see cref="Language"/>; <see cref="Get(string)"/> looks a string up by its key the same way. <see cref="SetLanguage"/>
    /// switches the language and raises <see cref="LanguageChanged"/>, so the views relabel what they show at once.
    /// The game's title is "Out of Sight" in both languages; PlayerSettings productName keeps the old name (the save folder
    /// depends on it).
    /// </summary>
    public static class Strings
    {
        public const string English = "en";
        public const string French = "fr";

        /// <summary>The language in use, <see cref="English"/> or <see cref="French"/>.</summary>
        public static string Language { get; private set; } = English;

        /// <summary>Raised after the language changed, with the previous language.</summary>
        public static event Action<string> LanguageChanged;

        /// <summary>"fr" stays French; anything else (null, missing, unknown) is English.</summary>
        public static string NormalizeLanguage(string id) => id == French ? French : English;

        /// <summary>Switches the language (normalized) and raises <see cref="LanguageChanged"/> when it changed.</summary>
        public static void SetLanguage(string id)
        {
            string next = NormalizeLanguage(id);
            if (next == Language)
            {
                return;
            }
            string previous = Language;
            Language = next;
            LanguageChanged?.Invoke(previous);
        }

        /// <summary>A language's own name, shown on the Options row ("English", "Français").</summary>
        public static string LanguageName(string id) => NormalizeLanguage(id) == French ? "Français" : "English";

        // Key, English, French. The French texts are the ones the game shipped with.
        private static readonly Dictionary<string, string[]> Table = new Dictionary<string, string[]>
        {
            { "title", new[] { "Out of Sight", "Out of Sight" } },
            { "title.tagline", new[] { "Don't Get Caught Moving", "Ne te fais pas prendre à bouger" } },
            { "title.play", new[] { "Play", "Jouer" } },
            { "title.quit", new[] { "Quit", "Quitter" } },
            { "title.credits", new[] { "Created and designed by Etienne 2026", "Created and designed by Etienne 2026" } },
            // Audio overhaul: the attribution CC BY 4.0 requires for the music (docs/LICENSES.md, section Music).
            { "title.musicCredits", new[] {
                "Music: \"Sneaky Snitch\", \"Investigations\" by Kevin MacLeod (incompetech.com), licensed under CC BY 4.0 (creativecommons.org/licenses/by/4.0)",
                "Musique : \"Sneaky Snitch\", \"Investigations\" de Kevin MacLeod (incompetech.com), sous licence CC BY 4.0 (creativecommons.org/licenses/by/4.0)" } },
            { "title.levels", new[] { "Levels", "Niveaux" } },

            { "hud.controls", new[] { "WASD/Arrows: move    Mouse: camera    R: restart    Esc: pause",
                "ZQSD/Flèches : avancer    Souris : caméra    R : recommencer    Échap : pause" } },
            { "hud.controlsGamepad", new[] { "Left stick/D-pad: move    Right stick: camera    Y: restart    Start: pause",
                "Stick gauche/croix : avancer    Stick droit : caméra    Y : recommencer    Start : pause" } },
            { "hud.controlsTouch", new[] { "Left thumb: move    Swipe right side: camera    Action: act    II: pause",
                "Pouce gauche : avancer    Glisser à droite : caméra    Action : agir    II : pause" } },
            { "hud.creak", new[] { "Creak", "Grincement" } },
            { "hud.suspicion", new[] { "Suspicion", "Soupçon" } },
            { "hud.balance", new[] { "Balance", "Équilibre" } },
            { "hud.careful", new[] { "Shift: tiptoe", "Maj : au ralenti" } },
            { "hud.lamp", new[] { "E: lights off / on", "E : éteindre / allumer" } },
            { "hud.satOn", new[] { "Someone is sitting on you. Stay strong.", "Quelqu'un est assis sur toi." } },
            { "hud.tipped", new[] { "Knocked over: press a direction to get back on your feet.", "Renversé : appuie sur une direction pour te relever." } },
            { "hud.door", new[] { "E: open the door", "E : ouvrir la porte" } },
            { "hud.hide", new[] { "E: hide", "E : se cacher" } },
            { "hud.leave", new[] { "E: come out", "E : sortir" } },
            { "hud.hidePad", new[] { "X: hide", "X : se cacher" } },
            { "hud.leavePad", new[] { "X: come out", "X : sortir" } },

            { "fail.title", new[] { "SPOTTED!", "VU !" } },
            { "fail.body", new[] { "Furniture doesn't just wander off on its own.", "Un meuble ne bouge pas tout seul." } },
            { "fail.action", new[] { "Press R to try again", "Appuie sur R pour recommencer" } },
            // M8 touch redesign: the fail panel's own Retry button (a phone has no R key), and the hint line shown
            // instead of fail.action while the touch controls are up.
            { "fail.retry", new[] { "Retry", "Réessayer" } },
            { "fail.action.touch", new[] { "Tap Retry to try again", "Appuie sur Réessayer pour recommencer" } },
            { "fail.suspicion.title", new[] { "SUSPICIOUS!", "LOUCHE !" } },
            { "fail.suspicion.body", new[] { "This furniture gets around a little too much.", "Ce meuble se promène un peu trop." } },
            { "win.title", new[] { "ESCAPED!", "DEHORS !" } },
            { "win.body", new[] { "Time: {0} s", "Temps : {0} s" } },
            { "win.action", new[] { "Press R to play again", "Appuie sur R pour rejouer" } },
            { "win.next", new[] { "Press Enter for the next level", "Appuie sur Entrée pour le niveau suivant" } },
            { "win.best", new[] { "Best: {0} s", "Record : {0} s" } },
            { "win.newBest", new[] { "New record!", "Nouveau record !" } },
            // M8 touch redesign: the win panel's own buttons (a phone has neither Enter nor R), and the hint lines
            // shown instead of win.action and win.next while the touch controls are up.
            { "win.replay", new[] { "Replay", "Rejouer" } },
            { "win.action.touch", new[] { "Tap Replay to play again", "Appuie sur Rejouer pour rejouer" } },
            { "win.nextButton", new[] { "Next level", "Niveau suivant" } },
            { "win.next.touch", new[] { "Tap Next level to continue", "Appuie sur Niveau suivant pour continuer" } },

            { "pause.title", new[] { "PAUSE", "PAUSE" } },
            { "pause.resume", new[] { "Resume", "Reprendre" } },
            { "pause.restart", new[] { "Restart", "Recommencer" } },
            { "pause.menu", new[] { "Main menu", "Menu principal" } },
            { "end.title", new[] { "THE END", "FIN" } },
            { "end.body", new[] { "Every room is behind you. Freedom smells of fresh air.", "Toutes les pièces sont derrière toi." } },

            { "level1.name", new[] { "The Living Room", "Le salon" } },
            { "level1.hint", new[] { "Only move when nobody's looking.", "Ne bouge que lorsque personne ne regarde." } },
            { "level2.name", new[] { "The Hallway", "Le couloir" } },
            { "level2.hint", new[] { "On a rug, nobody can hear you creep.", "Sur un tapis, personne ne t'entend." } },
            { "level3.name", new[] { "The Dining Room", "La salle à manger" } },
            { "level3.hint", new[] { "One more chair at the table? Nobody counts.", "Une chaise parmi d'autres ne surprend personne." } },
            { "level4.name", new[] { "The Stool", "Le tabouret" } },
            { "level4.hint", new[] { "Too fast and the stool topples. Hold Shift to tiptoe.", "Trop vite, et le tabouret tombe. Maj pour aller doucement." } },
            { "level5.name", new[] { "The Armchair", "Le fauteuil" } },
            { "level5.hint", new[] { "Be back in your spot when someone wants to sit down.", "Sois à ta place quand quelqu'un veut s'asseoir." } },
            { "level6.name", new[] { "The Lamp", "La lampe" } },
            { "level6.hint", new[] { "Eyes don't reach far in the dark. Switch off (E) when nobody's looking.",
                "Dans le noir, on voit moins loin. Éteins (E) quand personne ne regarde." } },
            { "level7.name", new[] { "The Office", "Le bureau" } },
            { "level7.hint", new[] { "An office chair never stops on a dime.", "Une chaise à roulettes ne s'arrête jamais tout de suite." } },
            { "level8.name", new[] { "The Doors", "Les portes" } },
            { "level8.hint", new[] { "A closed door hides everything. Open it (E) when nobody's looking.",
                "Une porte fermée cache tout. Ouvre-la (E) quand personne ne regarde." } },
            { "level9.name", new[] { "The Robot", "Le robot" } },
            { "level9.hint", new[] { "The robot shoves whatever it bumps, but its racket drowns out yours.",
                "Le robot pousse ce qu'il touche, mais son bruit couvre le tien." } },
            { "level10.name", new[] { "The Rocking Chair", "Le fauteuil à bascule" } },
            { "level10.hint", new[] { "It keeps rocking after every stop: brake early.", "Il se balance après chaque arrêt : arrête-toi tôt." } },
            { "level11.name", new[] { "The Vase", "Le vase" } },
            { "level11.hint", new[] { "No sharp turns with a vase aboard. Hold Shift to go gently.",
                "Pas de virage brusque avec le vase. Maj pour aller doucement." } },
            { "level12.name", new[] { "The Dog", "Le chien" } },
            { "level12.hint", new[] { "The dog sees low: the sofa hides you from him. Catch his eye moving and he barks.",
                "Le chien voit bas : le canapé te cache de lui. S'il te voit bouger, il aboie." } },
            { "level13.name", new[] { "Wheels and a Vase", "Roulettes et vase" } },
            { "level13.hint", new[] { "Shift to start and to turn: every stop slides, and the vase falls at the slightest jolt.",
                "Maj pour démarrer et tourner : chaque arrêt glisse, et le vase tombe au moindre à-coup." } },
            { "level14.name", new[] { "The Mezzanine", "La mezzanine" } },
            { "level14.hint", new[] { "Take the ramp up. Granny sits down a lot: be in your spot.",
                "Monte par la rampe. Mamie s'assoit souvent : sois à ta place." } },
            { "level15.name", new[] { "The Rocker and the Robot", "La bascule et le robot" } },
            { "level15.hint", new[] { "Near the robot, nobody hears you. The rocker keeps swinging after every stop.",
                "Près du robot, on n'entend pas tes pas. Le fauteuil se balance après chaque arrêt." } },
            { "level16.name", new[] { "Night Shift", "La nuit" } },
            { "level16.hint", new[] { "Switch yourself off when nobody's looking. The dog never sleeps.",
                "Éteins-toi quand personne ne regarde. Le chien veille." } },
            { "level17.name", new[] { "The Whole House", "La maison" } },
            { "level17.hint", new[] { "Everything you've learned, in one big house.", "Tout ce que tu as appris, dans une grande maison." } },
            { "level18.name", new[] { "The Wardrobe", "L'armoire" } },
            { "level18.hint", new[] { "The stool fits in the wardrobe: E to hide inside, E to come back out.",
                "Le tabouret tient dans l'armoire : E pour t'y cacher, E pour ressortir." } },
            { "level20.name", new[] { "Midnight Munchies", "Fringale de minuit" } },
            { "level20.hint", new[] { "Stay switched off. Let Dad open the kitchen door himself: a door you open, Mum will notice.", "Reste éteint. Laisse Papa ouvrir la porte de la cuisine : une porte que tu ouvres, Maman le remarquera." } },
            { "level23.name", new[] { "Upstairs, Downstairs", "Le haut et le bas" } },
            { "level23.hint", new[] { "Hugo opens the hall door for you. Odile looks away, but not long enough: hide halfway.", "Hugo t'ouvre le couloir. Odile détourne les yeux, mais pas assez longtemps : cache-toi à mi-chemin." } },
            { "level19.name", new[] { "Hide and Seek, Family Size", "Cache-cache en famille" } },
            { "level19.hint", new[] { "Up on the mezzanine the shelves hide you. In the gallery, hop from wardrobe to wardrobe while Mum looks away.", "Sur la mezzanine, les étagères te cachent. Dans la galerie, saute d'armoire en armoire quand Maman détourne les yeux." } },
            { "level21.name", new[] { "The Catwalk", "La passerelle" } },
            { "level21.hint", new[] { "Go over the desks, not between them. The filing cabinets hide the catwalk; the way down does not.", "Passez au-dessus des bureaux, pas entre eux. Les armoires cachent la passerelle, pas la descente." } },
            { "level22.name", new[] { "Skeletons in the Closet", "Des cadavres dans le placard" } },
            { "level22.hint", new[] { "Let the butler pass from inside a wardrobe. And leave the doors as you found them: the countess remembers.", "Laissez passer le majordome depuis une armoire. Et laissez les portes comme elles étaient : la comtesse s'en souvient." } },
            { "level24.name", new[] { "The Great Escape", "La grande évasion" } },
            { "level24.hint", new[] { "Rex sees low, not high: hug the sideboards, then take the bridge while Lea is away.", "Rex voit bas : longe les bahuts, puis prends la passerelle quand Lea s'absente." } },

            { "person.dreamer", new[] { "The Daydreamer", "Le rêveur" } },
            { "person.dreamer.trait", new[] { "Dawdles along and hardly looks around.", "Il traîne et regarde peu autour de lui." } },
            { "person.watchful", new[] { "The Suspicious One", "La méfiante" } },
            { "person.watchful.trait", new[] { "Always glancing over her shoulder.", "Elle jette souvent un œil autour d'elle." } },
            { "person.hurried", new[] { "The Rusher", "Le pressé" } },
            { "person.hurried.trait", new[] { "Walks fast and hears next to nothing.", "Il marche vite et entend mal." } },
            { "person.granny", new[] { "Granny", "Mamie" } },
            { "person.granny.trait", new[] { "Can't see far, and sits down every chance she gets.", "Elle voit mal de loin et s'assoit souvent." } },
            { "person.teen", new[] { "The Teen", "L'ado" } },
            { "person.teen.trait", new[] { "Glued to his phone: sees little, and only up close.", "Le nez sur son téléphone : il voit peu, et de près." } },
            { "person.tidy", new[] { "The Neat Freak", "La maniaque" } },
            { "person.tidy.trait", new[] { "Move one chair an inch and she'll notice.", "Le moindre meuble déplacé, elle le remarque." } },
            { "person.dog", new[] { "The Dog", "Le chien" } },
            { "person.dog.trait", new[] { "Sees low, and barks the second you move.", "Il voit bas et aboie quand tu bouges." } },
            { "intro.here", new[] { "Here: {0}", "Ici : {0}" } },

            { "select.locked", new[] { "Locked", "Verrouillé" } },
            { "select.back", new[] { "Back", "Retour" } },
            { "select.best", new[] { "{0} s", "{0} s" } },
            { "select.none", new[] { "-", "-" } },
            // M7 level select: the title column's progress line and its legend of the miniatures.
            { "select.progress", new[] { "{0} of {1} solved", "{0} sur {1} réussis" } },
            { "select.legend.you", new[] { "You, at the start", "Vous, au départ" } },
            { "select.legend.exit", new[] { "The way out", "La sortie" } },
            { "select.legend.people", new[] { "Inhabitant", "Habitant" } },
            { "select.legend.pet", new[] { "Pet", "Animal" } },
            { "select.legend.robot", new[] { "Robot vacuum", "Robot aspirateur" } },

            { "options.title", new[] { "Options", "Options" } },
            { "options.sensitivity", new[] { "Sensitivity: {0}", "Sensibilité : {0}" } },
            { "options.volume", new[] { "Volume: {0}%", "Volume : {0} %" } },
            { "options.music", new[] { "Music: {0}%", "Musique : {0} %" } },
            { "options.cone", new[] { "Vision cones: {0}", "Cône de vision : {0}" } },
            { "options.coneAlways", new[] { "Always", "Toujours" } },
            { "options.coneNever", new[] { "Never", "Jamais" } },
            { "options.default", new[] { "Defaults", "Par défaut" } },
            { "options.quality", new[] { "Quality: {0}", "Qualité : {0}" } },
            { "options.qualityLow", new[] { "Low", "Bas" } },
            { "options.qualityMedium", new[] { "Medium", "Moyen" } },
            { "options.qualityHigh", new[] { "High", "Haut" } },
            { "options.difficulty", new[] { "Difficulty: {0}", "Difficulté : {0}" } },
            { "difficulty.facile", new[] { "Easy", "Facile" } },
            { "difficulty.normal", new[] { "Normal", "Normal" } },
            { "difficulty.difficile", new[] { "Hard", "Difficile" } },
            { "options.language", new[] { "Language / Langue: {0}", "Language / Langue : {0}" } },

            { "touch.action", new[] { "Action", "Action" } },
            { "touch.careful", new[] { "Careful", "Prudence" } },
            { "touch.pause", new[] { "II", "II" } },
        };

        private static int Column(string language) => NormalizeLanguage(language) == French ? 1 : 0;

        /// <summary>Looks a string up by its key in the current language. An unknown key returns the key itself, visibly.</summary>
        public static string Get(string key) => Get(key, Language);

        /// <summary>Looks a string up by its key in <paramref name="language"/> (normalized).</summary>
        public static string Get(string key, string language)
        {
            return key != null && Table.TryGetValue(key, out string[] texts) ? texts[Column(language)] : key ?? string.Empty;
        }

        /// <summary>Every key of the table (tests check that each one has both languages).</summary>
        public static IEnumerable<string> Keys => Table.Keys;

        // Reverse index per language: a text to its key, or null when two keys share that text but differ in the other language.
        private static readonly Dictionary<string, string>[] Reverse = new Dictionary<string, string>[2];

        /// <summary>
        /// Translates a label that shows exactly the <paramref name="from"/> text of some key into the current language. False
        /// for a text that is no table entry (a formatted line, a number) or is shared by keys that translate differently.
        /// </summary>
        public static bool TryTranslate(string text, string from, out string translated)
        {
            translated = null;
            if (string.IsNullOrEmpty(text))
            {
                return false;
            }
            int column = Column(from);
            if (Reverse[column] == null)
            {
                var index = new Dictionary<string, string>();
                foreach (KeyValuePair<string, string[]> entry in Table)
                {
                    string source = entry.Value[column];
                    if (index.TryGetValue(source, out string other))
                    {
                        if (other != null && Table[other][1 - column] != entry.Value[1 - column])
                        {
                            index[source] = null;
                        }
                        continue;
                    }
                    index[source] = entry.Key;
                }
                Reverse[column] = index;
            }
            if (!Reverse[column].TryGetValue(text, out string key) || key == null)
            {
                return false;
            }
            translated = Get(key);
            return true;
        }

        /// <summary>Formats a duration with one decimal: 37.4 in English, 37,4 in French.</summary>
        public static string FormatSeconds(float seconds)
        {
            string text = seconds.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture);
            return Language == French ? text.Replace('.', ',') : text;
        }

        // ----- Named members (the code reads these; each returns the current language). -----
        public static string Title => Get("title");
        /// <summary>The subtitle under the title on the title page.</summary>
        public static string TitleTagline => Get("title.tagline");
        public static string Level1Name => Get("level1.name");
        public static string Level1Hint => Get("level1.hint");
        public static string HudControls => Get("hud.controls");
        public static string FailTitle => Get("fail.title");
        public static string FailBody => Get("fail.body");
        public static string FailAction => Get("fail.action");
        public static string WinTitle => Get("win.title");
        public static string WinBody => Get("win.body");
        public static string WinAction => Get("win.action");
        public static string FailSuspicionTitle => Get("fail.suspicion.title");
        public static string FailSuspicionBody => Get("fail.suspicion.body");
        public static string WinNext => Get("win.next");
        // M8 touch redesign: the fail and win panels' own buttons, and the touch variants of their hint lines.
        public static string FailRetry => Get("fail.retry");
        public static string FailActionTouch => Get("fail.action.touch");
        public static string WinReplay => Get("win.replay");
        public static string WinActionTouch => Get("win.action.touch");
        public static string WinNextButton => Get("win.nextButton");
        public static string WinNextTouch => Get("win.next.touch");
        public static string Level2Name => Get("level2.name");
        public static string Level2Hint => Get("level2.hint");
        public static string Level3Name => Get("level3.name");
        public static string Level3Hint => Get("level3.hint");
        public static string HudCreak => Get("hud.creak");
        public static string HudSuspicion => Get("hud.suspicion");
        public static string TitlePlay => Get("title.play");
        public static string TitleQuit => Get("title.quit");
        /// <summary>The author line (the asset licences stay in docs/LICENSES.md).</summary>
        public static string TitleCredits => Get("title.credits");
        /// <summary>Audio overhaul: the music's CC BY 4.0 attribution, under the credits of the title page.</summary>
        public static string TitleMusicCredits => Get("title.musicCredits");
        public static string PauseTitle => Get("pause.title");
        public static string PauseResume => Get("pause.resume");
        public static string PauseRestart => Get("pause.restart");
        public static string PauseMenu => Get("pause.menu");
        public static string EndTitle => Get("end.title");
        public static string EndBody => Get("end.body");
        public static string Level4Name => Get("level4.name");
        public static string Level4Hint => Get("level4.hint");
        public static string Level5Name => Get("level5.name");
        public static string Level5Hint => Get("level5.hint");
        public static string Level6Name => Get("level6.name");
        public static string Level6Hint => Get("level6.hint");
        public static string Level7Name => Get("level7.name");
        public static string Level7Hint => Get("level7.hint");
        public static string HudCareful => Get("hud.careful");
        public static string HudLamp => Get("hud.lamp");
        public static string HudSatOn => Get("hud.satOn");
        public static string HudTipped => Get("hud.tipped");
        public static string Level8Name => Get("level8.name");
        public static string Level8Hint => Get("level8.hint");
        public static string Level9Name => Get("level9.name");
        public static string Level9Hint => Get("level9.hint");
        public static string Level10Name => Get("level10.name");
        public static string Level10Hint => Get("level10.hint");
        public static string Level11Name => Get("level11.name");
        public static string Level11Hint => Get("level11.hint");
        public static string Level12Name => Get("level12.name");
        public static string Level12Hint => Get("level12.hint");
        public static string Level13Name => Get("level13.name");
        public static string Level13Hint => Get("level13.hint");
        public static string Level14Name => Get("level14.name");
        public static string Level14Hint => Get("level14.hint");
        public static string Level15Name => Get("level15.name");
        public static string Level15Hint => Get("level15.hint");
        public static string Level16Name => Get("level16.name");
        public static string Level16Hint => Get("level16.hint");
        public static string Level17Name => Get("level17.name");
        public static string Level17Hint => Get("level17.hint");
        public static string Level18Name => Get("level18.name");
        public static string Level18Hint => Get("level18.hint");
        public static string PersonDreamer => Get("person.dreamer");
        public static string PersonDreamerTrait => Get("person.dreamer.trait");
        public static string PersonWatchful => Get("person.watchful");
        public static string PersonWatchfulTrait => Get("person.watchful.trait");
        public static string PersonHurried => Get("person.hurried");
        public static string PersonHurriedTrait => Get("person.hurried.trait");
        public static string PersonGranny => Get("person.granny");
        public static string PersonGrannyTrait => Get("person.granny.trait");
        public static string PersonTeen => Get("person.teen");
        public static string PersonTeenTrait => Get("person.teen.trait");
        public static string PersonTidy => Get("person.tidy");
        public static string PersonTidyTrait => Get("person.tidy.trait");
        public static string PersonDog => Get("person.dog");
        public static string PersonDogTrait => Get("person.dog.trait");
        public static string IntroHere => Get("intro.here");
        public static string HudBalance => Get("hud.balance");
        public static string HudDoor => Get("hud.door");
        public static string TitleLevels => Get("title.levels");
        public static string SelectLocked => Get("select.locked");
        public static string SelectBack => Get("select.back");
        public static string SelectBest => Get("select.best");
        public static string SelectNone => Get("select.none");
        public static string SelectProgress => Get("select.progress");
        public static string SelectLegendYou => Get("select.legend.you");
        public static string SelectLegendExit => Get("select.legend.exit");
        public static string SelectLegendPeople => Get("select.legend.people");
        public static string SelectLegendPet => Get("select.legend.pet");
        public static string SelectLegendRobot => Get("select.legend.robot");
        public static string WinBest => Get("win.best");
        public static string WinNewBest => Get("win.newBest");

        // M6 gameplay: the wardrobe prompt, keyboard and gamepad.
        public static string HudHide => Get("hud.hide");
        public static string HudLeave => Get("hud.leave");
        public static string HudHidePad => Get("hud.hidePad");
        public static string HudLeavePad => Get("hud.leavePad");

        // M6 options.
        /// <summary>"Options", the button on the title and the pause menu, and the page's own title.</summary>
        public static string OptionsTitle => Get("options.title");
        public static string OptionsSensitivity => Get("options.sensitivity");
        public static string OptionsVolume => Get("options.volume");
        /// <summary>Audio overhaul: the Music row, a percentage like Volume.</summary>
        public static string OptionsMusic => Get("options.music");
        public static string OptionsCone => Get("options.cone");
        public static string OptionsConeAlways => Get("options.coneAlways");
        public static string OptionsConeNever => Get("options.coneNever");
        public static string OptionsDefault => Get("options.default");
        /// <summary>hud.controls when the last input came from a gamepad: the same four commands, gamepad names.</summary>
        public static string HudControlsGamepad => Get("hud.controlsGamepad");

        // M7 touch: the controls line and the button labels of the touch controls.
        /// <summary>hud.controls while the touch controls show: the same commands, touch names (restart is in the pause menu).</summary>
        public static string HudControlsTouch => Get("hud.controlsTouch");
        public static string TouchAction => Get("touch.action");
        public static string TouchCareful => Get("touch.careful");
        public static string TouchPause => Get("touch.pause");

        // M7 android: the quality option.
        public static string OptionsQuality => Get("options.quality");
        public static string OptionsQualityLow => Get("options.qualityLow");
        public static string OptionsQualityMedium => Get("options.qualityMedium");
        public static string OptionsQualityHigh => Get("options.qualityHigh");

        // M7 design: the difficulty option.
        public static string OptionsDifficulty => Get("options.difficulty");
        public static string DifficultyFacile => Get("difficulty.facile");
        public static string DifficultyNormal => Get("difficulty.normal");
        public static string DifficultyDifficile => Get("difficulty.difficile");

        /// <summary>The Language / Langue row of the Options page ("{0}" is the language's own name).</summary>
        public static string OptionsLanguage => Get("options.language");

        /// <summary>The shown name of a difficulty id (DifficultyDef.Facile, Normal, Difficile); anything else is Normal.</summary>
        public static string DifficultyName(string id)
        {
            switch (DifficultyDef.Normalize(id))
            {
                case DifficultyDef.Facile:
                    return DifficultyFacile;
                case DifficultyDef.Difficile:
                    return DifficultyDifficile;
                default:
                    return DifficultyNormal;
            }
        }
    }
}
