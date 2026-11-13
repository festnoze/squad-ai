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
    }
}
