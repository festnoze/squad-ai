using System.Collections.Generic;

namespace Meuble.Core
{
    /// <summary>Strings shown to the player, verbatim from PRD section 9.</summary>
    public static class Strings
    {
        public const string Title = "UN, DEUX, TROIS, MEUBLE";
        public const string Level1Name = "Le salon";
        public const string Level1Hint = "Ne bouge que lorsque personne ne regarde.";
        public const string HudControls = "ZQSD : avancer    Souris : caméra    R : recommencer    Échap : pause";
        public const string FailTitle = "VU !";
        public const string FailBody = "Un meuble ne bouge pas tout seul.";
        public const string FailAction = "Appuie sur R pour recommencer";
        public const string WinTitle = "DEHORS !";
        public const string WinBody = "Temps : {0} s";
        public const string WinAction = "Appuie sur R pour rejouer";

        // M2 (docs/CONTRACT_M2.md section 8).
        public const string FailSuspicionTitle = "LOUCHE !";
        public const string FailSuspicionBody = "Ce meuble se promène un peu trop.";
        public const string WinNext = "Appuie sur Entrée pour le niveau suivant";
        public const string Level2Name = "Le couloir";
        public const string Level2Hint = "Sur un tapis, personne ne t'entend.";
        public const string Level3Name = "La salle à manger";
        public const string Level3Hint = "Une chaise parmi d'autres ne surprend personne.";
        // M2.1 (CONTRACT_M2 section 11.6).
        public const string HudCreak = "Grincement";
        public const string HudSuspicion = "Soupçon";
        // M3 (docs/CONTRACT_M3.md 6).
        public const string TitlePlay = "Jouer";
        public const string TitleQuit = "Quitter";
        public const string TitleCredits = "Modèles 3D : Kenney et Quaternius (CC0). Sons : OpenGameArt (CC0).";
        public const string PauseTitle = "PAUSE";
        public const string PauseResume = "Reprendre";
        public const string PauseRestart = "Recommencer";
        public const string PauseMenu = "Menu principal";
        public const string EndTitle = "FIN";
        public const string EndBody = "Toutes les pièces sont derrière toi.";
        // M4 (docs/CONTRACT_M4.md section 4).
        public const string Level4Name = "Le tabouret";
        public const string Level4Hint = "Trop vite, et le tabouret tombe. Maj pour aller doucement.";
        public const string Level5Name = "Le fauteuil";
        public const string Level5Hint = "Sois à ta place quand quelqu'un veut s'asseoir.";
        public const string Level6Name = "La lampe";
        public const string Level6Hint = "Dans le noir, on voit moins loin. Éteins (E) quand personne ne regarde.";
        public const string Level7Name = "Le bureau";
        public const string Level7Hint = "Une chaise à roulettes ne s'arrête jamais tout de suite.";
        public const string HudCareful = "Maj : au ralenti";
        public const string HudLamp = "E : éteindre / allumer";
        public const string HudSatOn = "Quelqu'un est assis sur toi.";
        public const string HudTipped = "Renversé : appuie sur une direction pour te relever.";
        // M5 (docs/CONTRACT_M5.md 14 and 16.10).
        public const string Level8Name = "Les portes";
        public const string Level8Hint = "Une porte fermée cache tout. Ouvre-la (E) quand personne ne regarde.";
        public const string Level9Name = "Le robot";
        public const string Level9Hint = "Le robot pousse ce qu'il touche, mais son bruit couvre le tien.";
        public const string Level10Name = "Le fauteuil à bascule";
        public const string Level10Hint = "Il se balance après chaque arrêt : arrête-toi tôt.";
        public const string Level11Name = "Le vase";
        public const string Level11Hint = "Pas de virage brusque avec le vase. Maj pour aller doucement.";
        public const string Level12Name = "Le chien";
        public const string Level12Hint = "Le chien voit bas : le canapé te cache de lui. S'il te voit bouger, il aboie.";
        public const string Level13Name = "Roulettes et vase";
        public const string Level13Hint = "Maj pour démarrer et tourner : chaque arrêt glisse, et le vase tombe au moindre à-coup.";
        public const string Level14Name = "La mezzanine";
        public const string Level14Hint = "Monte par la rampe. Mamie s'assoit souvent : sois à ta place.";
        public const string Level15Name = "La bascule et le robot";
        public const string Level15Hint = "Près du robot, on n'entend pas tes pas. Le fauteuil se balance après chaque arrêt.";
        public const string Level16Name = "La nuit";
        public const string Level16Hint = "Éteins-toi quand personne ne regarde. Le chien veille.";
        public const string Level17Name = "La maison";
        public const string Level17Hint = "Tout ce que tu as appris, dans une grande maison.";
        public const string PersonDreamer = "Le rêveur";
        public const string PersonDreamerTrait = "Il traîne et regarde peu autour de lui.";
        public const string PersonWatchful = "La méfiante";
        public const string PersonWatchfulTrait = "Elle jette souvent un œil autour d'elle.";
        public const string PersonHurried = "Le pressé";
        public const string PersonHurriedTrait = "Il marche vite et entend mal.";
        public const string PersonGranny = "Mamie";
        public const string PersonGrannyTrait = "Elle voit mal de loin et s'assoit souvent.";
        public const string PersonTeen = "L'ado";
        public const string PersonTeenTrait = "Le nez sur son téléphone : il voit peu, et de près.";
        public const string PersonTidy = "La maniaque";
        public const string PersonTidyTrait = "Le moindre meuble déplacé, elle le remarque.";
        public const string PersonDog = "Le chien";
        public const string PersonDogTrait = "Il voit bas et aboie quand tu bouges.";
        public const string IntroHere = "Ici : {0}";
        public const string HudBalance = "Équilibre";
        public const string HudDoor = "E : ouvrir la porte";
        public const string TitleLevels = "Niveaux";
        public const string SelectLocked = "Verrouillé";
        public const string SelectBack = "Retour";
        public const string SelectBest = "{0} s";
        public const string SelectNone = "-";
        public const string WinBest = "Record : {0} s";
        public const string WinNewBest = "Nouveau record !";

        private static readonly Dictionary<string, string> ByKey = new Dictionary<string, string>
        {
            { "title", Title },
            { "level1.name", Level1Name },
            { "level1.hint", Level1Hint },
            { "hud.controls", HudControls },
            { "fail.title", FailTitle },
            { "fail.body", FailBody },
            { "fail.action", FailAction },
            { "win.title", WinTitle },
            { "win.body", WinBody },
            { "win.action", WinAction },
            { "fail.suspicion.title", FailSuspicionTitle },
            { "fail.suspicion.body", FailSuspicionBody },
            { "win.next", WinNext },
            { "level2.name", Level2Name },
            { "level2.hint", Level2Hint },
            { "level3.name", Level3Name },
            { "level3.hint", Level3Hint },
            { "hud.creak", HudCreak },
            { "hud.suspicion", HudSuspicion },
            { "title.play", TitlePlay },
            { "title.quit", TitleQuit },
            { "title.credits", TitleCredits },
            { "pause.title", PauseTitle },
            { "pause.resume", PauseResume },
            { "pause.restart", PauseRestart },
            { "pause.menu", PauseMenu },
            { "end.title", EndTitle },
            { "end.body", EndBody },
            { "level4.name", Level4Name },
            { "level4.hint", Level4Hint },
            { "level5.name", Level5Name },
            { "level5.hint", Level5Hint },
            { "level6.name", Level6Name },
            { "level6.hint", Level6Hint },
            { "level7.name", Level7Name },
            { "level7.hint", Level7Hint },
            { "hud.careful", HudCareful },
            { "hud.lamp", HudLamp },
            { "hud.satOn", HudSatOn },
            { "hud.tipped", HudTipped },
            { "level8.name", Level8Name },
            { "level8.hint", Level8Hint },
            { "level9.name", Level9Name },
            { "level9.hint", Level9Hint },
            { "level10.name", Level10Name },
            { "level10.hint", Level10Hint },
            { "level11.name", Level11Name },
            { "level11.hint", Level11Hint },
            { "level12.name", Level12Name },
            { "level12.hint", Level12Hint },
            { "level13.name", Level13Name },
            { "level13.hint", Level13Hint },
            { "level14.name", Level14Name },
            { "level14.hint", Level14Hint },
            { "level15.name", Level15Name },
            { "level15.hint", Level15Hint },
            { "level16.name", Level16Name },
            { "level16.hint", Level16Hint },
            { "level17.name", Level17Name },
            { "level17.hint", Level17Hint },
            { "person.dreamer", PersonDreamer },
            { "person.dreamer.trait", PersonDreamerTrait },
            { "person.watchful", PersonWatchful },
            { "person.watchful.trait", PersonWatchfulTrait },
            { "person.hurried", PersonHurried },
            { "person.hurried.trait", PersonHurriedTrait },
            { "person.granny", PersonGranny },
            { "person.granny.trait", PersonGrannyTrait },
            { "person.teen", PersonTeen },
            { "person.teen.trait", PersonTeenTrait },
            { "person.tidy", PersonTidy },
            { "person.tidy.trait", PersonTidyTrait },
            { "person.dog", PersonDog },
            { "person.dog.trait", PersonDogTrait },
            { "intro.here", IntroHere },
            { "hud.balance", HudBalance },
            { "hud.door", HudDoor },
            { "title.levels", TitleLevels },
            { "select.locked", SelectLocked },
            { "select.back", SelectBack },
            { "select.best", SelectBest },
            { "select.none", SelectNone },
            { "win.best", WinBest },
            { "win.newBest", WinNewBest },
        };

        /// <summary>Looks a string up by its PRD key. An unknown key returns the key itself, visibly.</summary>
        public static string Get(string key)
        {
            return key != null && ByKey.TryGetValue(key, out string value) ? value : key ?? string.Empty;
        }

        /// <summary>Formats a duration the French way, one decimal and a comma: 37,4.</summary>
        public static string FormatSeconds(float seconds)
        {
            return seconds.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture).Replace('.', ',');
        }

        // ----- M6 gameplay (docs/CONTRACT_M6.md 2.5): the wardrobe prompt, keyboard and gamepad. -----
        public const string HudHide = "E : se cacher";
        public const string HudLeave = "E : sortir";
        public const string HudHidePad = "X : se cacher";
        public const string HudLeavePad = "X : sortir";

        // ----- M6 options (docs/CONTRACT_M6.md 2.1 and 2.2) -----
        /// <summary>"Options", the button on the title and the pause menu, and the page's own title.</summary>
        public const string OptionsTitle = "Options";
        public const string OptionsSensitivity = "Sensibilité : {0}";
        public const string OptionsVolume = "Volume : {0} %";
        public const string OptionsCone = "Cône de vision : {0}";
        public const string OptionsConeAlways = "Toujours";
        public const string OptionsConeNever = "Jamais";
        public const string OptionsDefault = "Par défaut";
        /// <summary>hud.controls when the last input came from a gamepad (2.2): the same four commands, gamepad names.</summary>
        public const string HudControlsGamepad = "Stick gauche : avancer    Stick droit : caméra    Y : recommencer    Start : pause";

        // ----- M6 levels (docs/CONTRACT_M6.md 1.8 and 5): level 18 "L'armoire", its name and hint. -----
        public const string Level18Name = "L'armoire";
        public const string Level18Hint = "Le tabouret tient dans l'armoire : E pour t'y cacher, E pour ressortir.";
        // Registered here (static initializers run in text order, after ByKey) so this block stays self-contained.
        internal static readonly bool M6LevelsRegistered = RegisterM6Levels();

        private static bool RegisterM6Levels()
        {
            ByKey["level18.name"] = Level18Name;
            ByKey["level18.hint"] = Level18Hint;
            return true;
        }

        // ----- M7 touch (docs/CONTRACT_M7.md 1.5): the controls line and the button labels of the touch controls. -----
        /// <summary>hud.controls while the touch controls show: the same commands, touch names (restart is in the pause menu).</summary>
        public const string HudControlsTouch = "Pouce gauche : avancer    Glisser à droite : caméra    Action : agir    II : pause";
        public const string TouchAction = "Action";
        public const string TouchCareful = "Prudence";
        public const string TouchPause = "II";

        // ----- M7 android (docs/CONTRACT_M7.md 1.4): the Qualité option of the Options screen. -----
        public const string OptionsQuality = "Qualité : {0}";
        public const string OptionsQualityLow = "Bas";
        public const string OptionsQualityMedium = "Moyen";
        public const string OptionsQualityHigh = "Haut";

        // ----- M7 design (docs/CONTRACT_M7.md 4.1): the Difficulté option of the Options screen. -----
        public const string OptionsDifficulty = "Difficulté : {0}";
        public const string DifficultyFacile = "Facile";
        public const string DifficultyNormal = "Normal";
        public const string DifficultyDifficile = "Difficile";

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
