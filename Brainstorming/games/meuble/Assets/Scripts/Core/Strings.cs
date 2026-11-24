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
            { "title.tagline", new[] { "Unseen, uncaught!", "Pas vu, pas pris !" } },
            { "title.play", new[] { "Play", "Jouer" } },
            { "title.quit", new[] { "Quit", "Quitter" } },
            { "title.credits", new[] { "Created by Etienne. Upskill 2026", "Crée par Etienne. Upskill 2026" } },
            { "title.levels", new[] { "Levels", "Niveaux" } },

            { "hud.controls", new[] { "WASD/Arrows: move    Mouse: camera    R: restart    Esc: pause",
                "ZQSD/Flèches : avancer    Souris : caméra    R : recommencer    Échap : pause" } },
            { "hud.controlsGamepad", new[] { "Left stick/D-pad: move    Right stick: camera    Y: restart    Start: pause",
                "Stick gauche/croix : avancer    Stick droit : caméra    Y : recommencer    Start : pause" } },
            // DOORAUTO: no action button on touch any more (a door opens when pushed toward, the lamp is tapped).
            { "hud.controlsTouch", new[] { "Left thumb: move    Swipe right side: camera    II: pause",
                "Pouce gauche : avancer    Glisser à droite : caméra    II : pause" } },
            { "hud.creak", new[] { "Creak", "Grincement" } },
            { "hud.suspicion", new[] { "Suspicion", "Soupçon" } },
            { "hud.balance", new[] { "Balance", "Équilibre" } },
            { "hud.careful", new[] { "Shift: tiptoe", "Maj : au ralenti" } },
            { "hud.lamp", new[] { "E: lights off / on", "E : éteindre / allumer" } },
            // DOORAUTO: the lamp hint per device (E stays the keyboard's lamp switch, X the gamepad's, a tap on the lamp on touch).
            { "hud.lampPad", new[] { "X: lights off / on", "X : éteindre / allumer" } },
            { "hud.lampTouch", new[] { "Tap the lamp: off / on", "Touche la lampe : éteindre / allumer" } },
            { "hud.satOn", new[] { "Someone is sitting on you. Stay strong.", "Quelqu'un est assis sur toi." } },
            { "hud.dogHold", new[] { "The dog has you! Back to your place...", "Le chien te tient ! Retour à ta place..." } },
            { "hud.tipped", new[] { "Knocked over: press a direction to get back on your feet.", "Renversé : appuie sur une direction pour te relever." } },
            // DOORAUTO: doors and wardrobes open by pushing the move input toward them, on every device (no key named).
            { "hud.door", new[] { "Push toward the door to open it", "Pousse vers la porte pour l'ouvrir" } },
            { "hud.hide", new[] { "Push into the wardrobe to hide", "Pousse vers l'armoire pour te cacher" } },
            { "hud.leave", new[] { "Push away to come out", "Pousse vers l'extérieur pour sortir" } },
            // Levels v2 (LEVELS_V2.md 8): the held intro card's start line, one variant per device like the controls
            // line; the door hint of a leaf only the household opens; the lamp's hint inside a lit zone; and the intro
            // card's line per inhabitant ({0} the data name, {1} the personality label).
            // STARTFIX: the start press (Space, gamepad A, a tap) starts without moving, so a spawn inside a cone can wait.
            // STARTTAP: one short line per device (keyboard and mouse, gamepad, touch); moving still starts too.
            { "hud.start", new[] { "Space or click to start", "Espace ou clic pour commencer" } },
            { "hud.startGamepad", new[] { "Press A to start", "Appuie sur A pour commencer" } },
            { "hud.startTouch", new[] { "Tap the screen to start", "Touche l'écran pour commencer" } },
            { "hud.door.locked", new[] { "Locked", "Fermée à clé" } },
            { "hud.lit", new[] { "In the light: the dark won't hide you", "Dans la lumière : le noir ne te cache plus" } },
            { "hud.person", new[] { "{0}, {1}", "{0}, {1}" } },

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

            // Levels v2 act names (levels.json "acts" nameKey), shown as the act tag of the level select.
            { "act1.name", new[] { "One piece, one rule", "Un meuble, une règle" } },
            { "act2.name", new[] { "The household", "La maisonnée" } },
            { "act3.name", new[] { "Far from home", "Loin de chez soi" } },

            // Level names and hints. Levels v2 (LEVELS_V2.md 8, D22, D29): hints describe the threat, never the route,
            // use the inhabitant names exactly as in the level data, say "tu" in French, and name no key: {action} (the lamp
            // switch; DOORAUTO: doors and wardrobes are a push, never {action}) and {careful} are replaced per device by the HUD. level10, level16 and level23 are cut from the line-up but
            // their files still load by id, so their entries stay.
            { "level1.name", new[] { "The Living Room", "Le salon" } },
            { "level1.hint", new[] { "Only move when nobody's looking.", "Ne bouge que lorsque personne ne regarde." } },
            { "level2.name", new[] { "The Hallway", "Le couloir" } },
            { "level2.hint", new[] { "On a rug, nobody can hear you creep.", "Sur un tapis, personne ne t'entend." } },
            { "level3.name", new[] { "The Dining Room", "La salle à manger" } },
            { "level3.hint", new[] { "They remember where you stood. Park beside another chair and nobody counts.",
                "Ils se souviennent de ta place. Gare-toi à côté d'une autre chaise : personne ne compte." } },
            { "level4.name", new[] { "The Stool", "Le tabouret" } },
            { "level4.hint", new[] { "Too fast and the stool topples. Hold {careful} to tiptoe.",
                "Trop vite, et le tabouret tombe. Maintiens {careful} pour aller doucement." } },
            { "level5.name", new[] { "The Armchair", "Le fauteuil" } },
            { "level5.hint", new[] { "Be back in your spot when someone wants to sit down.", "Sois à ta place quand quelqu'un veut s'asseoir." } },
            { "level6.name", new[] { "The Lamp", "La lampe" } },
            { "level6.hint", new[] { "Eyes don't reach far in the dark. Switch off ({action}) when nobody's looking.",
                "Dans le noir, on voit moins loin. Éteins-toi ({action}) quand personne ne regarde." } },
            { "level7.name", new[] { "The Office", "Le bureau" } },
            { "level7.hint", new[] { "An office chair never stops on a dime.", "Une chaise à roulettes ne s'arrête jamais tout de suite." } },
            { "level8.name", new[] { "The Doors", "Les portes" } },
            { "level8.hint", new[] { "Two closed doors, two ways out. A door seen swinging gives you away.",
                "Deux portes fermées, deux chemins. Une porte qu'on voit bouger te trahit." } },
            { "level9.name", new[] { "The Robot", "Le robot" } },
            { "level9.hint", new[] { "Claire hears every hop on the parquet, except right beside the robot. Don't let it bump into you.",
                "Claire entend chaque saut sur le parquet, sauf tout près du robot. Ne le laisse pas te cogner." } },
            { "level10.name", new[] { "The Rocking Chair", "Le fauteuil à bascule" } },
            { "level10.hint", new[] { "It keeps rocking after every stop: brake early.", "Il se balance après chaque arrêt : arrête-toi tôt." } },
            { "level11.name", new[] { "The Vase", "Le vase" } },
            { "level11.hint", new[] { "Slow down ({careful}) before every turn or the vase falls. Lea faces the wall first, then makes her rounds.",
                "Ralentis ({careful}) avant chaque virage, sinon le vase tombe. Lea fait d'abord face au mur, puis elle fait sa ronde." } },
            { "level12.name", new[] { "The Dog", "Le chien" } },
            { "level12.hint", new[] { "Rex sees low: the sofas hide you from him. Paul sees over them.",
                "Rex voit bas : les canapés te cachent de lui. Paul, lui, voit par-dessus." } },
            { "level13.name", new[] { "Wheels and a Vase", "Roulettes et vase" } },
            { "level13.hint", new[] { "Ease into every start and turn ({careful}): the vase falls at the slightest jolt. Max takes you for one of the desk chairs; Claire does not.",
                "Démarre et tourne en douceur ({careful}) : le vase tombe à la moindre secousse. Max te prend pour une chaise de bureau parmi d'autres ; Claire, non." } },
            { "level14.name", new[] { "The Mezzanine", "La mezzanine" } },
            { "level14.hint", new[] { "Mamie sits on you first, then walks through the bathroom to the living room window: let her go ahead, and cross the mezzanine while her back is turned.",
                "Mamie s'assoit d'abord sur toi, puis passe par la salle de bain jusqu'à la fenêtre du séjour : laisse-la prendre de l'avance, et traverse la mezzanine pendant qu'elle te tourne le dos." } },
            { "level15.name", new[] { "Let Sleeping Dogs Lie", "Chien qui dort" } },
            { "level15.hint", new[] { "The rocker swings a moment after every stop, less if you brake gently ({careful}). Rex only sees what moves.",
                "Le fauteuil se balance un instant après chaque arrêt, moins si tu freines en douceur ({careful}). Rex ne voit que ce qui bouge." } },
            { "level16.name", new[] { "Night Shift", "La nuit" } },
            { "level16.hint", new[] { "Switch yourself off when nobody's looking. The dog never sleeps.",
                "Éteins-toi quand personne ne regarde. Le chien veille." } },
            { "level17.name", new[] { "The Whole House", "La maison" } },
            { "level17.hint", new[] { "Mamie sits first. Rex sees the bridge. Lea hears everything the robot doesn't cover.",
                "Mamie s'assoit d'abord. Rex voit le pont. Lea entend tout ce que le robot ne couvre pas." } },
            { "level18.name", new[] { "The Wardrobe", "L'armoire" } },
            { "level18.hint", new[] { "The stool fits in the wardrobe: push into it to hide inside, push away to come back out.",
                "Le tabouret tient dans l'armoire : pousse vers elle pour t'y cacher, pousse dans l'autre sens pour en sortir." } },
            { "level20.name", new[] { "Midnight Munchies", "Fringale de minuit" } },
            { "level20.hint", new[] { "Switched off, you are only seen up close, and some eyes reach further than others. Maman keeps watch at the end of the corridor and notices every door you open.",
                "Éteinte, on ne te voit que de près, et certains yeux portent plus loin que d'autres. Maman monte la garde au bout du couloir et remarque chaque porte que tu ouvres." } },
            { "level23.name", new[] { "Upstairs, Downstairs", "Le haut et le bas" } },
            { "level23.hint", new[] { "Hugo opens the hall door for you. Odile looks away, but not long enough: hide halfway.", "Hugo t'ouvre le couloir. Odile détourne les yeux, mais pas assez longtemps : cache-toi à mi-chemin." } },
            { "level19.name", new[] { "Hide and Seek, Family Size", "Cache-cache en famille" } },
            { "level19.hint", new[] { "Maman watches the gallery, regular as clockwork. Now and then Papa leaves the sofa for the kitchen, and he takes the gallery too.",
                "Maman surveille la galerie, réglée comme une horloge. De temps en temps, Papa quitte le canapé pour la cuisine, et lui aussi passe par la galerie." } },
            { "level21.name", new[] { "The Catwalk", "La passerelle" } },
            { "level21.hint", new[] { "Bertrand and Sofia watch the catwalk from their desks. Kevin runs between the hall and the cafeteria, and a robot hums by the photocopier.",
                "Bertrand et Sofia surveillent la passerelle depuis leurs bureaux. Kevin court entre l'accueil et la cafétéria, et un robot ronronne près de la photocopieuse." } },
            { "level22.name", new[] { "Skeletons in the Closet", "Des cadavres dans le placard" } },
            { "level22.hint", new[] { "Alfred watches the east corridor and looks away now and then. Mamie never stays in one room. The Comtesse remembers every door in her house.",
                "Alfred surveille le couloir est et détourne parfois le regard. Mamie change sans cesse de pièce. La Comtesse se souvient de chaque porte de sa maison." } },
            { "level25.name", new[] { "The Showroom", "Le magasin de meubles" } },
            // If LV12 falls back to a loop for Marcel, drop "at random" / "au hasard" (LEVELS_V2.md 8).
            { "level25.hint", new[] { "Marcel zigzags through the shop, Nina sweeps by the door, and the lights stay on. Freeze only where a chair belongs.",
                "Marcel zigzague dans la boutique, Nina passe et repasse près de la porte, et les lumières restent allumées. Ne t'arrête que là où une chaise a sa place." } },
            { "level24.name", new[] { "The Great Escape", "La grande évasion" } },
            { "level24.hint", new[] { "Rex watches the long corridor: stay behind the sideboards. Hide among the dining chairs while Theo and Mamie look away. Behind Theo the runner starts a step too late: cross that bare floor while the robot hums close by. Lea watches the doormat; go when she turns her head.",
                "Rex surveille le long couloir : reste derrière les buffets. Cache-toi parmi les chaises de la salle à manger pendant que Theo et Mamie regardent ailleurs. Derrière Theo, le tapis commence un pas trop tard : traverse ce parquet nu quand le robot ronronne tout près. Lea surveille le paillasson ; file quand elle tourne la tête." } },

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
            { "person.dog.trait", new[] { "Sees low, barks and pins you the second you move.", "Il voit bas, aboie et te bloque si tu bouges." } },
            { "intro.here", new[] { "Here: {0}", "Ici : {0}" } },

            { "select.locked", new[] { "Locked", "Verrouillé" } },
            { "select.back", new[] { "Back", "Retour" } },
            // SPECTATOR: the level select's checkbox, the HUD's tag and controls line per device, and the pause menu's way
            // back to the level select. The keyboard line names the physical keys: Q on QWERTY is A on AZERTY.
            { "select.spectator", new[] { "Spectator mode", "Mode spectateur" } },
            { "hud.spectatorTag", new[] { "SPECTATOR", "SPECTATEUR" } },
            { "hud.spectator", new[] { "WASD/Arrows: fly    Space/E: up    Ctrl/Q: down    Shift: faster    Wheel: speed    Mouse: look    Esc: pause",
                "ZQSD/Flèches : voler    Espace/E : monter    Ctrl/A : descendre    Maj : plus vite    Molette : vitesse    Souris : regarder    Échap : pause" } },
            { "hud.spectatorGamepad", new[] { "Left stick: fly    Right stick: look    RT/LT: up/down    L3: faster    Start: pause",
                "Stick gauche : voler    Stick droit : regarder    RT/LT : monter/descendre    L3 : plus vite    Start : pause" } },
            { "hud.spectatorTouch", new[] { "Left thumb: fly    Swipe right side: look    Pinch: up/down    II: pause",
                "Pouce gauche : voler    Glisser à droite : regarder    Pincer : monter/descendre    II : pause" } },
            { "pause.levels", new[] { "Level select", "Choix du niveau" } },
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
            // M7 walls pass (product owner, 2026-11-19): how the walls in the way get out of it, and their opacity.
            { "options.walls", new[] { "Walls: {0}", "Murs : {0}" } },
            { "options.wallsLowered", new[] { "Lowered", "Baissés" } },
            { "options.wallsSeeThrough", new[] { "See-through", "Transparents" } },
            { "options.wallsBoth", new[] { "Both", "Les deux" } },
            { "options.wallsNone", new[] { "Off", "Aucun" } },
            { "options.wallOpacity", new[] { "Wall opacity: {0}%", "Opacité des murs : {0} %" } },
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
            // Credits cleanup (2026-11-19, product owner): the music's CC BY 4.0 attribution, moved off the title
            // (which now shows only the author line) to a small line at the bottom of the Options page. The
            // attribution requirement itself is unchanged (docs/LICENSES.md, section Music).
            { "options.musicCredits", new[] {
                "Music: \"Sneaky Snitch\", \"Investigations\" by Kevin MacLeod (incompetech.com), licensed under CC BY 4.0 (creativecommons.org/licenses/by/4.0)",
                "Musique : \"Sneaky Snitch\", \"Investigations\" de Kevin MacLeod (incompetech.com), sous licence CC BY 4.0 (creativecommons.org/licenses/by/4.0)" } },
            // Credits page (2026-11-19): the title page's button and the page's own heading; the lines are Core.Credits.
            { "credits.title", new[] { "Credits", "Crédits" } },

            // DOORAUTO: the touch name of the lamp switch in a hint's {action} (the action button is gone).
            { "touch.lamp", new[] { "tap the lamp", "touche la lampe" } },
            { "touch.careful", new[] { "Careful", "Prudence" } },
            { "touch.pause", new[] { "II", "II" } },

            // Stars (idea 5, docs/next/progress/STARS.md): the level select's total line ({0} the stars earned at the current
            // difficulty, {1} the levels times three) and the win panel's line under the stars when this win raised them.
            { "stars.total", new[] { "{0} / {1} stars", "{0} / {1} étoiles" } },
            { "stars.newBest", new[] { "New stars!", "Nouvelles étoiles !" } },

            // Onboarding tips (idea 3, docs/next/progress/TIPS.md): one sentence each, shown once per save on levels 1 to 3
            // when the situation first happens (Core.TipDef, Runtime.Tips). "tu" register, no key named: {move} is the
            // device's move control (tips.move.*), {action} and {careful} resolve like the hints.
            { "tips.eye", new[] { "The eye opens when someone sees you: stay still and you are just furniture.",
                "L'œil s'ouvre quand on te voit : reste immobile et tu n'es qu'un meuble." } },
            { "tips.freeze", new[] { "Someone is turning your way: let go of {move} until the eye closes.",
                "Quelqu'un se tourne vers toi : lâche {move} jusqu'à ce que l'œil se ferme." } },
            { "tips.creak", new[] { "Moving fills the creak gauge: pause before it is full, or everyone hears you.",
                "Bouger remplit la jauge de grincement : fais une pause avant qu'elle soit pleine, sinon tout le monde t'entend." } },
            { "tips.suspicion", new[] { "Seen out of place: suspicion rises, and a full gauge means you are caught.",
                "Vu hors de ta place : le soupçon monte, et jauge pleine, tu es pris." } },
            { "tips.rug", new[] { "On the rug your hops make no sound.", "Sur le tapis, tes sauts ne font aucun bruit." } },
            { "tips.decoy", new[] { "Park beside an identical piece: nobody counts them.",
                "Gare-toi à côté d'un meuble identique : personne ne les compte." } },
            { "tips.move.keyboard", new[] { "the keys", "les touches" } },
            { "tips.move.gamepad", new[] { "the stick", "le stick" } },
            { "tips.move.touch", new[] { "your thumb", "le pouce" } },

            // Speech bubbles (idea 7, docs/next/progress/BUBBLES.md): the comic lines over the inhabitants' heads, 1 to 5
            // words each. Key: react.<kind>.<personality>.<n> (Core.Reactions reads the table; n from 1, 3 to 6 per group).
            // A personality without a group of its own for a kind says the default lines. "dog" is the dog, "robot" the
            // robot vacuum. Never an em-dash in a line.
            // Near miss: the cone swept over the furniture standing still, and saw nothing wrong.
            { "react.nearMiss.default.1", new[] { "Hm?", "Hm ?" } },
            { "react.nearMiss.default.2", new[] { "Nothing there.", "Rien là." } },
            { "react.nearMiss.default.3", new[] { "Must be the wind.", "C'est le vent." } },
            { "react.nearMiss.default.4", new[] { "I'm seeing things.", "Je rêve." } },
            { "react.nearMiss.dreamer.1", new[] { "Huh? Oh, nothing.", "Hein ? Oh, rien." } },
            { "react.nearMiss.dreamer.2", new[] { "Where was I...", "Où j'en étais..." } },
            { "react.nearMiss.dreamer.3", new[] { "Pretty wallpaper.", "Joli papier peint." } },
            { "react.nearMiss.watchful.1", new[] { "Something moved?", "Ça a bougé ?" } },
            { "react.nearMiss.watchful.2", new[] { "I'm watching you.", "Je t'ai à l'œil." } },
            { "react.nearMiss.watchful.3", new[] { "Hm. Suspicious.", "Hm. Louche." } },
            { "react.nearMiss.hurried.1", new[] { "No time!", "Pas le temps !" } },
            { "react.nearMiss.hurried.2", new[] { "Late, late, late!", "Vite, vite, vite !" } },
            { "react.nearMiss.hurried.3", new[] { "Out of my way.", "Dégagez le passage." } },
            { "react.nearMiss.granny.1", new[] { "Where are my glasses?", "Où sont mes lunettes ?" } },
            { "react.nearMiss.granny.2", new[] { "Eh? Who's there?", "Hein ? Qui est là ?" } },
            { "react.nearMiss.granny.3", new[] { "My poor eyes.", "Mes pauvres yeux." } },
            { "react.nearMiss.teen.1", new[] { "Whatever.", "Osef." } },
            { "react.nearMiss.teen.2", new[] { "Nice selfie.", "Beau selfie." } },
            { "react.nearMiss.teen.3", new[] { "Did it buzz?", "Ça a vibré ?" } },
            { "react.nearMiss.tidy.1", new[] { "Everything in place?", "Tout est en place ?" } },
            { "react.nearMiss.tidy.2", new[] { "Dust. Again.", "Encore la poussière." } },
            { "react.nearMiss.tidy.3", new[] { "Hm. Looks tidy.", "Hm. C'est rangé." } },
            // Noticed: the furniture seen out of place (a discovery).
            { "react.noticed.default.1", new[] { "Huh? That furniture...", "Tiens ? Ce meuble..." } },
            { "react.noticed.default.2", new[] { "Who moved that?", "Qui a bougé ça ?" } },
            { "react.noticed.default.3", new[] { "That wasn't there.", "C'était pas là." } },
            { "react.noticed.default.4", new[] { "Hey now...", "Eh ben..." } },
            { "react.noticed.dreamer.1", new[] { "Did I move that?", "J'ai bougé ça, moi ?" } },
            { "react.noticed.dreamer.2", new[] { "Funny. Oh well.", "Marrant. Bon." } },
            { "react.noticed.dreamer.3", new[] { "Was it always there?", "C'était là avant ?" } },
            { "react.noticed.watchful.1", new[] { "I KNEW it.", "Je le SAVAIS." } },
            { "react.noticed.watchful.2", new[] { "Someone's been here.", "Quelqu'un est passé." } },
            { "react.noticed.watchful.3", new[] { "Not on my watch.", "Pas sous mes yeux." } },
            { "react.noticed.hurried.1", new[] { "Ugh, not now!", "Rah, pas maintenant !" } },
            { "react.noticed.hurried.2", new[] { "Who left that there?", "Qui a laissé ça là ?" } },
            { "react.noticed.hurried.3", new[] { "No time for this!", "Pas le temps pour ça !" } },
            { "react.noticed.granny.1", new[] { "Did I do that?", "C'est moi, ça ?" } },
            { "react.noticed.granny.2", new[] { "Goodness me.", "Mon Dieu." } },
            { "react.noticed.granny.3", new[] { "Well I never!", "Ça alors !" } },
            { "react.noticed.teen.1", new[] { "Mom moved it again.", "Maman l'a encore bougé." } },
            { "react.noticed.teen.2", new[] { "Weird. Anyway.", "Chelou. Bref." } },
            { "react.noticed.teen.3", new[] { "Not my problem.", "Pas mon problème." } },
            { "react.noticed.tidy.1", new[] { "WHO moved this?", "QUI a bougé ça ?" } },
            { "react.noticed.tidy.2", new[] { "Two centimetres off!", "Deux centimètres de travers !" } },
            { "react.noticed.tidy.3", new[] { "Not. In. Place.", "Pas. À. Sa. Place." } },
            // Spot empty: the remembered spot found empty while the furniture hides in a wardrobe.
            { "react.spotEmpty.default.1", new[] { "Where did it go?", "Où est-il passé ?" } },
            { "react.spotEmpty.default.2", new[] { "It was right here.", "Il était juste là." } },
            { "react.spotEmpty.default.3", new[] { "Gone? How?", "Disparu ? Comment ?" } },
            { "react.spotEmpty.default.4", new[] { "Burglars!", "Des cambrioleurs !" } },
            // Put back: the carrier set the furniture down on its slot.
            { "react.putBack.default.1", new[] { "There. Better.", "Voilà. Mieux." } },
            { "react.putBack.default.2", new[] { "Back you go.", "Allez, hop." } },
            { "react.putBack.default.3", new[] { "Done.", "Et voilà." } },
            { "react.putBack.default.4", new[] { "Where it belongs.", "À sa place." } },
            { "react.putBack.dreamer.1", new[] { "There... I think.", "Voilà... je crois." } },
            { "react.putBack.dreamer.2", new[] { "Close enough.", "À peu près." } },
            { "react.putBack.dreamer.3", new[] { "Hm, like that?", "Hm, comme ça ?" } },
            { "react.putBack.watchful.1", new[] { "Stay. Put.", "Tu. Restes. Là." } },
            { "react.putBack.watchful.2", new[] { "I'm keeping an eye out.", "Je surveille." } },
            { "react.putBack.watchful.3", new[] { "Back where I know.", "Là où je sais." } },
            { "react.putBack.hurried.1", new[] { "Done, moving on!", "Bon, au suivant !" } },
            { "react.putBack.hurried.2", new[] { "There. No time.", "Voilà. Pas le temps." } },
            { "react.putBack.hurried.3", new[] { "Quick fix.", "Vite fait." } },
            { "react.putBack.granny.1", new[] { "My poor back.", "Mon pauvre dos." } },
            { "react.putBack.granny.2", new[] { "There, dearie.", "Voilà, mon petit." } },
            { "react.putBack.granny.3", new[] { "Heavy, that one.", "Lourd, celui-là." } },
            { "react.putBack.teen.1", new[] { "Ugh. Fine.", "Pff. Bon." } },
            { "react.putBack.teen.2", new[] { "Happy now?", "Content ?" } },
            { "react.putBack.teen.3", new[] { "So heavy, wow.", "Trop lourd, sérieux." } },
            { "react.putBack.tidy.1", new[] { "Perfect. Perfect.", "Parfait. Parfait." } },
            { "react.putBack.tidy.2", new[] { "Aligned at last.", "Enfin aligné." } },
            { "react.putBack.tidy.3", new[] { "Don't move. Ever.", "Ne bouge plus. Jamais." } },
            // Sat on: a sitter settled on the player furniture (Granny has her own).
            { "react.satOn.default.1", new[] { "Ahh, comfy.", "Ahh, confortable." } },
            { "react.satOn.default.2", new[] { "Finally, a seat.", "Enfin assis." } },
            { "react.satOn.default.3", new[] { "Oof.", "Ouf." } },
            { "react.satOn.default.4", new[] { "Hm, lumpy.", "Hm, ça bosse." } },
            { "react.satOn.granny.1", new[] { "Ahh, my knees.", "Ahh, mes genoux." } },
            { "react.satOn.granny.2", new[] { "Nice and warm.", "Bien chaud." } },
            { "react.satOn.granny.3", new[] { "It wobbles a little.", "Ça branle un peu." } },
            { "react.satOn.granny.4", new[] { "Tea time.", "L'heure du thé." } },
            // The dog: its bark at the moving furniture, and every bark of its hold.
            { "react.dogBark.dog.1", new[] { "WOOF!", "WOUF !" } },
            { "react.dogBark.dog.2", new[] { "WOOF WOOF!", "WOUF WOUF !" } },
            { "react.dogBark.dog.3", new[] { "Grrr...", "Grrr..." } },
            { "react.dogBark.dog.4", new[] { "ARF!", "WAF !" } },
            // Dog drag (DOGCARRY): the dog grips the furniture and drags it home itself.
            { "react.dogDrag.dog.1", new[] { "Mmmf! Mmmf!", "Mmmf ! Mmmf !" } },
            { "react.dogDrag.dog.2", new[] { "Grmf... heavy...", "Grmf... lourd..." } },
            { "react.dogDrag.dog.3", new[] { "Bad! Back home!", "Vilain ! Au panier !" } },
            { "react.dogDrag.dog.4", new[] { "Wuff... hnngh!", "Wouf... hnngh !" } },
            // Dog call: the human the dog called is on its way (DOGCARRY: only when the dog has no path home).
            { "react.dogCall.default.1", new[] { "What is it, boy?", "Qu'est-ce qu'il y a ?" } },
            { "react.dogCall.default.2", new[] { "Coming, coming.", "J'arrive, j'arrive." } },
            { "react.dogCall.default.3", new[] { "What now?", "Quoi encore ?" } },
            { "react.dogCall.default.4", new[] { "Quiet, you!", "Chut, toi !" } },
            // Caught: the fail panel's moment, said by the inhabitant that saw it.
            { "react.caught.default.1", new[] { "GOTCHA!", "VU !" } },
            { "react.caught.default.2", new[] { "It MOVED!", "Ça a BOUGÉ !" } },
            { "react.caught.default.3", new[] { "AAAH!", "AAAH !" } },
            { "react.caught.default.4", new[] { "It walks?!", "Ça marche ?!" } },
            { "react.caught.dreamer.1", new[] { "Am I dreaming?!", "Je rêve ?!" } },
            { "react.caught.dreamer.2", new[] { "Whoa. Whoa!", "Oh. Oh !" } },
            { "react.caught.dreamer.3", new[] { "Furniture... moves?", "Les meubles... bougent ?" } },
            { "react.caught.watchful.1", new[] { "I SAW THAT!", "JE L'AI VU !" } },
            { "react.caught.watchful.2", new[] { "Caught you!", "Je te tiens !" } },
            { "react.caught.watchful.3", new[] { "Ha! Knew it!", "Ha ! Je le savais !" } },
            { "react.caught.hurried.1", new[] { "WHAT? No time!", "QUOI ? Pas le temps !" } },
            { "react.caught.hurried.2", new[] { "Stop right there!", "Arrête-toi là !" } },
            { "react.caught.hurried.3", new[] { "Not today!", "Pas aujourd'hui !" } },
            { "react.caught.granny.1", new[] { "Saints preserve us!", "Sainte Marie !" } },
            { "react.caught.granny.2", new[] { "My heart!", "Mon cœur !" } },
            { "react.caught.granny.3", new[] { "The furniture is haunted!", "Le meuble est hanté !" } },
            { "react.caught.teen.1", new[] { "Dude. DUDE.", "Mec. MEC." } },
            { "react.caught.teen.2", new[] { "Filming this!", "Je filme !" } },
            { "react.caught.teen.3", new[] { "No way!", "Pas possible !" } },
            { "react.caught.tidy.1", new[] { "IT MOVED ITSELF!", "ÇA A BOUGÉ TOUT SEUL !" } },
            { "react.caught.tidy.2", new[] { "Unacceptable!", "Inadmissible !" } },
            { "react.caught.tidy.3", new[] { "Out of place AND alive!", "Déplacé ET vivant !" } },
            // Door opened: an inhabitant opened a household door on its walk.
            { "react.doorOpened.default.1", new[] { "After you!", "Après vous !" } },
            { "react.doorOpened.default.2", new[] { "Door's open.", "Porte ouverte." } },
            { "react.doorOpened.default.3", new[] { "Draughty in here.", "Y a un courant d'air." } },
            { "react.doorOpened.default.4", new[] { "La la la.", "La la la." } },
            // Robot bump: the robot vacuum ran into the furniture.
            { "react.robotBump.robot.1", new[] { "BEEP.", "BIP." } },
            { "react.robotBump.robot.2", new[] { "Obstacle.", "Obstacle." } },
            { "react.robotBump.robot.3", new[] { "Rerouting...", "Recalcul..." } },
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
        /// <summary>The author line, the only credit left on the title page (credits cleanup, 2026-11-19).</summary>
        public static string TitleCredits => Get("title.credits");
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
        public static string HudDogHold => Get("hud.dogHold");
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

        /// <summary>SPECTATOR: the level select's checkbox label.</summary>
        public static string SelectSpectator => Get("select.spectator");

        /// <summary>SPECTATOR: the HUD's tag while a level is watched in spectator mode.</summary>
        public static string HudSpectatorTag => Get("hud.spectatorTag");

        /// <summary>SPECTATOR: the free camera's controls line (keyboard and mouse).</summary>
        public static string HudSpectator => Get("hud.spectator");

        /// <summary>SPECTATOR: the free camera's controls line (gamepad).</summary>
        public static string HudSpectatorGamepad => Get("hud.spectatorGamepad");

        /// <summary>SPECTATOR: the free camera's controls line (touch).</summary>
        public static string HudSpectatorTouch => Get("hud.spectatorTouch");

        /// <summary>SPECTATOR: the pause menu's "Main menu" button in spectator mode, which goes back to the level select.</summary>
        public static string PauseLevels => Get("pause.levels");
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

        // M6 gameplay: the wardrobe prompt (DOORAUTO: a push, the same sentence on every device).
        public static string HudHide => Get("hud.hide");
        public static string HudLeave => Get("hud.leave");
        /// <summary>DOORAUTO: the lamp hint on a gamepad (X) and on touch (a tap on the lamp); hud.lamp is the keyboard's (E).</summary>
        public static string HudLampPad => Get("hud.lampPad");
        public static string HudLampTouch => Get("hud.lampTouch");

        // Levels v2 (LEVELS_V2.md 8): the held card's start line per device, the locked-door and lit-zone hints, the
        // intro card's person format, and the new level slot.
        /// <summary>The held intro card's start line, keyboard (the gamepad and touch variants follow the controls line).</summary>
        public static string HudStart => Get("hud.start");
        public static string HudStartGamepad => Get("hud.startGamepad");
        public static string HudStartTouch => Get("hud.startTouch");
        /// <summary>The door hint of a closed playerLocked leaf in reach, instead of hud.door.</summary>
        public static string HudDoorLocked => Get("hud.door.locked");
        /// <summary>The body hint while the floor lamp is switched off inside a lit zone.</summary>
        public static string HudLit => Get("hud.lit");
        /// <summary>The intro card's line per inhabitant: {0} the data name, {1} the personality label.</summary>
        public static string HudPerson => Get("hud.person");
        public static string Level25Name => Get("level25.name");
        public static string Level25Hint => Get("level25.hint");

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
        /// <summary>M7 walls pass: the Walls row ({0}: one of the four looks below) and the Wall opacity row ({0}: percent).</summary>
        public static string OptionsWalls => Get("options.walls");
        public static string OptionsWallsLowered => Get("options.wallsLowered");
        public static string OptionsWallsSeeThrough => Get("options.wallsSeeThrough");
        public static string OptionsWallsBoth => Get("options.wallsBoth");
        public static string OptionsWallsNone => Get("options.wallsNone");
        public static string OptionsWallOpacity => Get("options.wallOpacity");
        public static string OptionsDefault => Get("options.default");
        /// <summary>hud.controls when the last input came from a gamepad: the same four commands, gamepad names.</summary>
        public static string HudControlsGamepad => Get("hud.controlsGamepad");

        // M7 touch: the controls line and the button labels of the touch controls.
        /// <summary>hud.controls while the touch controls show: the same commands, touch names (restart is in the pause menu).</summary>
        public static string HudControlsTouch => Get("hud.controlsTouch");
        /// <summary>DOORAUTO: the touch name of the lamp switch, written into a hint's {action} on touch.</summary>
        public static string TouchLamp => Get("touch.lamp");
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

        /// <summary>Credits cleanup: the music's CC BY 4.0 attribution, a small line at the bottom of the Options page.</summary>
        public static string OptionsMusicCredits => Get("options.musicCredits");

        /// <summary>"Crédits", the title page's button and the Credits page's heading (its lines are <see cref="Credits"/>).</summary>
        public static string CreditsTitle => Get("credits.title");

        // Stars (idea 5): the level select's total line and the win panel's "New stars!".
        public static string StarsTotal => Get("stars.total");
        public static string StarsNewBest => Get("stars.newBest");

        // Onboarding tips (idea 3): the six first-time sentences (raw, tokens unresolved; Runtime.Tips resolves them).
        public static string TipsEye => Get("tips.eye");
        public static string TipsFreeze => Get("tips.freeze");
        public static string TipsCreak => Get("tips.creak");
        public static string TipsSuspicion => Get("tips.suspicion");
        public static string TipsRug => Get("tips.rug");
        public static string TipsDecoy => Get("tips.decoy");

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
