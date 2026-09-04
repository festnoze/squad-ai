using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;

namespace Viewpoint.Tests
{
    /// <summary>
    /// Campaign and battery logic of <see cref="GameState"/> (PRD section 9).
    ///
    /// Every case drives a BARE instance: the class references no scene object,
    /// so <c>new GameState()</c> is the whole fixture and no level, player or
    /// scene is ever loaded. The shared <see cref="GameState.Instance"/> is
    /// cleared around each case as well, otherwise an instance built by an
    /// earlier test would still be holding in memory the progress this one
    /// deletes from disk.
    ///
    /// The progression key is deleted BEFORE and AFTER each case, and both
    /// halves matter: a run must not inherit a real player's unlocks (the case
    /// asserting that level 2 starts locked would then pass or fail depending
    /// on who last played), and it must not leave its own behind either, since
    /// cases here reach the last level of the campaign.
    /// </summary>
    public sealed class GameStateTests
    {
        GameState _game;

        readonly List<(int carried, int inserted, int required)> _batteryEvents =
            new List<(int carried, int inserted, int required)>();

        readonly List<int> _filmEvents = new List<int>();
        readonly List<int> _levelStarts = new List<int>();

        /// <summary>
        /// The three events in the order they actually arrived. The order is
        /// part of the contract (PRD 9) because the HUD reads them in sequence,
        /// and a count alone cannot see it.
        /// </summary>
        readonly List<string> _order = new List<string>();

        [SetUp]
        public void SetUp()
        {
            PlayerPrefs.DeleteKey(GameState.ProgressKey);
            PlayerPrefs.Save();
            GameState.Instance = null;
            _batteryEvents.Clear();
            _filmEvents.Clear();
            _levelStarts.Clear();
            _order.Clear();
            _game = new GameState();
        }

        [TearDown]
        public void TearDown()
        {
            PlayerPrefs.DeleteKey(GameState.ProgressKey);
            PlayerPrefs.Save();
            GameState.Instance = null;
            _game = null;
        }

        /// <summary>
        /// Records the events of the state under test from this point on. Some
        /// cases subscribe late on purpose, so that the count below is the
        /// emissions of one action and not of the whole setup.
        /// </summary>
        void Watch(GameState state)
        {
            state.BatteriesChanged += (carried, inserted, required) =>
            {
                _batteryEvents.Add((carried, inserted, required));
                _order.Add("batteries");
            };
            state.FilmsChanged += films =>
            {
                _filmEvents.Add(films);
                _order.Add("films");
            };
            state.LevelStarted += index =>
            {
                _levelStarts.Add(index);
                _order.Add("level");
            };
        }

        [Test]
        public void Le_cycle_complet()
        {
            _game.Reset();
            _game.BeginLevel(0, 2);
            Assert.AreEqual(2, _game.RequiredBatteries, "exigence enregistree");
            Assert.IsFalse(_game.CanTeleport(), "pas de teleportation a vide");
            _game.CollectBattery();
            _game.CollectBattery();
            Assert.AreEqual(2, _game.CarriedBatteries, "deux piles portees");
            Assert.AreEqual(2, _game.InsertBatteries(), "deux piles inserees");
            Assert.AreEqual(0, _game.CarriedBatteries, "plus rien en main");
            Assert.AreEqual(2, _game.InsertedBatteries, "deux piles dans le teleporteur");
            Assert.IsTrue(_game.CanTeleport(), "teleporteur charge");
            Assert.IsTrue(_game.HasNextLevel(), "il reste des niveaux");
            _game.AdvanceLevel();
            Assert.AreEqual(1, _game.LevelIndex, "niveau suivant");
        }

        [Test]
        public void Le_nombre_de_niveaux_suit_la_donnee()
        {
            _game.BeginLevel(LevelDefs.Count - 2, 1);
            Assert.IsTrue(_game.HasNextLevel(), "l'avant-dernier niveau a un suivant");
        }

        [Test]
        public void Les_bornes_d_insertion()
        {
            _game.BeginLevel(1, 1);
            Assert.AreEqual(0, _game.InsertBatteries(), "insertion sans pile : zero");
            _game.CollectBattery();
            _game.CollectBattery();
            _game.CollectBattery();
            Assert.AreEqual(1, _game.InsertBatteries(), "insertion bornee au requis");
            Assert.AreEqual(2, _game.CarriedBatteries, "le surplus reste porte");
            Assert.AreEqual(0, _game.InsertBatteries(), "reinsertion sur un teleporteur plein : zero");
            Assert.AreEqual(2, _game.CarriedBatteries, "un refus n'avale pas le surplus");
            Assert.IsTrue(_game.CanTeleport(), "charge atteinte");
        }

        [Test]
        public void Commencer_un_niveau_remet_les_piles_a_zero()
        {
            // Every counter is non zero when the next level starts, so each
            // assertion below has something the reset has to clear: insert
            // first, then take the lead and the film, or insertion would have
            // spent the lead itself and the sealed check could not fail.
            _game.BeginLevel(0, 1);
            _game.CollectBattery();
            Assert.AreEqual(1, _game.InsertBatteries(), "une pile entre avant de changer de niveau");
            _game.CollectBattery(true);
            _game.AddFilms(4);
            Assert.AreEqual(1, _game.CarriedSealed, "un plomb en main avant de changer de niveau");
            _game.BeginLevel(1, 3);
            Assert.AreEqual(0, _game.CarriedBatteries, "les piles ne traversent pas les niveaux");
            Assert.AreEqual(0, _game.CarriedSealed, "le plomb ne traverse pas non plus");
            Assert.AreEqual(0, _game.CameraFilms, "la pellicule ne traverse pas les niveaux");
            Assert.AreEqual(0, _game.InsertedBatteries, "l'insertion repart de zero");
            Assert.AreEqual(3, _game.RequiredBatteries, "nouvelle exigence");
            Assert.AreEqual(1, _game.LevelIndex, "l'index de niveau suit");
            Assert.IsFalse(_game.CanTeleport(), "nouveau teleporteur decharge");
        }

        [Test]
        public void Le_dernier_niveau_n_a_pas_de_suivant()
        {
            _game.BeginLevel(LevelDefs.Count - 1, 4);
            Assert.IsFalse(_game.HasNextLevel(), "le dernier niveau n'a pas de suivant");
        }

        [Test]
        public void Le_deverrouillage_des_niveaux()
        {
            // A bare instance has loaded nothing: the progression starts empty
            // whatever this machine has played.
            Assert.IsTrue(_game.IsLevelUnlocked(0), "le niveau 1 est toujours accessible");
            Assert.IsFalse(_game.IsLevelUnlocked(1), "le niveau 2 commence verrouille");
            Assert.IsFalse(_game.IsLevelUnlocked(-1), "index negatif verrouille");
            Assert.IsFalse(_game.IsLevelUnlocked(LevelDefs.Count), "index hors borne verrouille");
            _game.BeginLevel(3, 2);
            Assert.IsTrue(_game.IsLevelUnlocked(3), "atteindre un niveau le debloque");
            Assert.IsTrue(_game.IsLevelUnlocked(2), "les niveaux precedents aussi");
            Assert.IsFalse(_game.IsLevelUnlocked(4), "pas les suivants");
            _game.BeginLevel(1, 2);
            Assert.AreEqual(3, _game.FurthestLevel, "rejouer un vieux niveau ne reduit pas la progression");
            _game.Reset();
            Assert.AreEqual(3, _game.FurthestLevel, "reset ne touche pas la progression");
            Assert.AreEqual(0, _game.LevelIndex, "reset ramene au premier niveau");
            Assert.AreEqual(0, _game.RequiredBatteries, "reset vide l'exigence");
        }

        [Test]
        public void La_progression_persiste()
        {
            // FRESH INSTALL. Nothing has ever been saved (SetUp deleted the key),
            // and loading must land on the first level rather than on whatever
            // PlayerPrefs hands back for a missing key. This is the case the key
            // is public for, and it runs before anything writes.
            GameState virgin = new GameState();
            virgin.LoadProgress();
            Assert.AreEqual(0, virgin.FurthestLevel,
                "sans sauvegarde, la progression part du premier niveau");
            Assert.IsTrue(virgin.IsLevelUnlocked(0), "le premier niveau est accessible sans sauvegarde");
            Assert.IsFalse(virgin.IsLevelUnlocked(1), "et le second reste verrouille");

            // FurthestLevel has no setter on purpose: reaching a level is the
            // only thing that grows it, and BeginLevel saves as it grows.
            GameState writer = new GameState();
            writer.BeginLevel(7, 1);
            Assert.AreEqual(7, writer.FurthestLevel, "atteindre le niveau 8 fait la progression");
            writer.SaveProgress();

            GameState reader = new GameState();
            Assert.AreEqual(0, reader.FurthestLevel, "instance neuve : progression vierge");
            reader.LoadProgress();
            Assert.AreEqual(7, reader.FurthestLevel, "la progression relue correspond a l'ecriture");
            Assert.IsTrue(reader.IsLevelUnlocked(7), "le niveau relu est accessible");
            Assert.IsFalse(reader.IsLevelUnlocked(8), "et pas celui d'apres");

            // A corrupt or absurd saved value is clamped into the valid level
            // range rather than refused.
            PlayerPrefs.SetInt(GameState.ProgressKey, 999);
            PlayerPrefs.Save();
            GameState clamped = new GameState();
            clamped.LoadProgress();
            Assert.AreEqual(LevelDefs.Count - 1, clamped.FurthestLevel,
                "valeur aberrante bornee au dernier niveau");

            PlayerPrefs.SetInt(GameState.ProgressKey, -5);
            PlayerPrefs.Save();
            GameState negative = new GameState();
            negative.LoadProgress();
            Assert.AreEqual(0, negative.FurthestLevel, "valeur negative bornee au premier niveau");

            // No campaign at all: the clamp range must not invert into [0, -1].
            PlayerPrefs.SetInt(GameState.ProgressKey, 999);
            PlayerPrefs.Save();
            GameState empty = new GameState();
            empty.LevelCountProvider = () => 0;
            empty.LoadProgress();
            Assert.AreEqual(0, empty.FurthestLevel, "campagne vide : progression ramenee a zero");
        }

        [Test]
        public void Reposer_une_pile()
        {
            // E with nothing aimed at puts one carried battery back down (the
            // player spawns the pickup). The count is floored at zero: no
            // phantom battery.
            _game.BeginLevel(0, 3);
            Assert.AreEqual("", _game.DropBattery(), "reposer les mains vides est refuse");
            Assert.AreEqual(0, _game.CarriedBatteries, "le compte reste a zero");
            _game.CollectBattery();
            _game.CollectBattery();
            Assert.AreEqual("normal", _game.DropBattery(), "reposer une pile portee est accepte");
            Assert.AreEqual(1, _game.CarriedBatteries, "une seule pile reposee a la fois");
            Assert.AreEqual("normal", _game.DropBattery(), "seconde repose acceptee");
            Assert.AreEqual(0, _game.CarriedBatteries, "plus rien en main");
            Assert.AreEqual("", _game.DropBattery(), "troisieme repose refusee");
            Assert.AreEqual(0, _game.CarriedBatteries, "le compte ne passe jamais sous zero");
            // Dropping does not give the teleporter anything back.
            Assert.AreEqual(0, _game.InsertedBatteries, "reposer ne remplit pas le teleporteur");
            Assert.IsFalse(_game.CanTeleport(), "et ne le charge donc pas");
        }

        [Test]
        public void Le_signal_de_repose()
        {
            _game.BeginLevel(0, 2);
            _game.CollectBattery();
            // Subscribed here, so what follows counts the drop alone.
            Watch(_game);
            Assert.AreEqual("normal", _game.DropBattery(), "repose acceptee");
            Assert.AreEqual(1, _batteryEvents.Count, "une emission de batteries_changed a la repose");
            Assert.AreEqual(0, _batteryEvents[0].carried, "etat emis : 0 portee, 0 inseree, 2 requises");
            Assert.AreEqual(0, _batteryEvents[0].inserted, "etat emis : 0 portee, 0 inseree, 2 requises");
            Assert.AreEqual(2, _batteryEvents[0].required, "etat emis : 0 portee, 0 inseree, 2 requises");
            Assert.AreEqual("", _game.DropBattery(), "repose a vide refusee");
            Assert.AreEqual(1, _batteryEvents.Count, "une repose refusee n'emet rien");
        }

        [Test]
        public void Le_plomb_reste_du_plomb()
        {
            // A leaden battery keeps its nature through the hands. Setting one
            // down and photographing what comes back must not launder it into a
            // copyable one, so what goes down first is always the lead (7.4).
            _game.BeginLevel(0, 4);
            Assert.AreEqual(0, _game.CarriedSealed, "on demarre sans plomb");
            _game.CollectBattery();
            _game.CollectBattery(true);
            Assert.AreEqual(2, _game.CarriedBatteries, "deux piles en main");
            Assert.AreEqual(1, _game.CarriedSealed, "dont une plombee");
            Assert.AreEqual("sealed", _game.DropBattery(), "c'est le plomb qui redescend en premier");
            Assert.AreEqual(0, _game.CarriedSealed, "le plomb n'est plus en main");
            Assert.AreEqual("normal", _game.DropBattery(), "la pile vive ensuite");
            Assert.AreEqual(0, _game.CarriedBatteries, "les mains sont vides");

            // A teleporter does not care: lead is worth exactly one battery, and
            // it is spent first so the copyable one stays available as long as
            // possible.
            _game.BeginLevel(0, 2);
            _game.CollectBattery(true);
            _game.CollectBattery();
            Assert.AreEqual(2, _game.InsertBatteries(), "les deux piles entrent dans le teleporteur");
            Assert.AreEqual(0, _game.CarriedSealed, "plus de plomb en main apres insertion");
            Assert.IsTrue(_game.CanTeleport(), "le plomb alimente le teleporteur comme le reste");

            // A partial insertion spends the lead and leaves the copyable one in
            // hand, which is the whole point of the order.
            _game.BeginLevel(2, 1);
            _game.CollectBattery(true);
            _game.CollectBattery();
            Assert.AreEqual(1, _game.InsertBatteries(), "une seule pile entre dans un teleporteur qui en veut une");
            Assert.AreEqual(1, _game.CarriedBatteries, "une pile reste en main");
            Assert.AreEqual(0, _game.CarriedSealed, "le plomb est parti le premier");
            Assert.AreEqual("normal", _game.DropBattery(), "la pile qui reste est la pile vive");

            // Rewind restores the leaden count too, and can never claim more
            // lead than there are batteries in hand.
            _game.RestoreCounters(1, 0, 2, 0, 5);
            Assert.AreEqual(1, _game.CarriedSealed, "le compte de plomb est borne au nombre de piles portees");
            _game.RestoreCounters(0, 0, 2, 0, 3);
            Assert.AreEqual(0, _game.CarriedSealed, "les mains vides ne portent aucun plomb");
            _game.RestoreCounters(2, 0, 2, 0, -1);
            Assert.AreEqual(0, _game.CarriedSealed, "un compte de plomb negatif est ramene a zero");
            Assert.AreEqual(2, _game.CarriedBatteries, "les piles portees sont restaurees telles quelles");
        }

        [Test]
        public void Les_signaux_de_piles()
        {
            Watch(_game);
            _game.BeginLevel(0, 2);
            _game.CollectBattery();
            _game.InsertBatteries();
            Assert.AreEqual(3, _batteryEvents.Count, "trois emissions de batteries_changed");
            Assert.AreEqual(0, _batteryEvents[2].carried, "dernier etat : 0 portee, 1 inseree, 2 requises");
            Assert.AreEqual(1, _batteryEvents[2].inserted, "dernier etat : 0 portee, 1 inseree, 2 requises");
            Assert.AreEqual(2, _batteryEvents[2].required, "dernier etat : 0 portee, 1 inseree, 2 requises");
            Assert.AreEqual(1, _levelStarts.Count, "une annonce de debut de niveau");
            Assert.AreEqual(0, _levelStarts[0], "le niveau annonce est le premier");

            int emitted = _batteryEvents.Count;
            _game.Reset();
            Assert.AreEqual(emitted, _batteryEvents.Count,
                "reset n'emet rien : c'est le niveau suivant qui annonce");
        }

        [Test]
        public void Le_nombre_de_niveaux_suit_le_fournisseur()
        {
            // The count is injected, which is what lets these rules be checked
            // without the level catalog, and what turns a missing catalog into a
            // locked campaign instead of a crash.
            _game.LevelCountProvider = () => 3;
            Assert.AreEqual(3, _game.LevelCount, "le fournisseur donne le nombre de niveaux");
            _game.BeginLevel(2, 1);
            Assert.IsFalse(_game.HasNextLevel(), "le dernier niveau du fournisseur n'a pas de suivant");
            Assert.IsTrue(_game.IsLevelUnlocked(2), "le niveau atteint est accessible");
            Assert.IsFalse(_game.IsLevelUnlocked(3), "hors borne du fournisseur : verrouille");

            _game.LevelCountProvider = () => -4;
            Assert.AreEqual(0, _game.LevelCount, "un nombre negatif de niveaux vaut zero");

            _game.LevelCountProvider = null;
            Assert.AreEqual(0, _game.LevelCount, "sans fournisseur : aucun niveau");
            Assert.IsFalse(_game.IsLevelUnlocked(0), "aucun niveau : rien n'est accessible");
            Assert.IsFalse(_game.HasNextLevel(), "aucun niveau : aucun suivant");
        }

        [Test]
        public void Le_film_se_compte_et_se_consomme()
        {
            Watch(_game);
            _game.BeginLevel(0, 1);
            Assert.AreEqual(0, _game.CameraFilms, "un niveau commence sans pellicule");
            Assert.AreEqual(1, _filmEvents.Count, "commencer un niveau annonce la pellicule");
            Assert.AreEqual(0, _filmEvents[0], "zero vue annoncee");
            _game.AddFilms(3);
            Assert.AreEqual(3, _game.CameraFilms, "l'appareil donne trois vues");
            Assert.AreEqual(2, _filmEvents.Count, "une emission par don de pellicule");
            Assert.IsTrue(_game.UseFilm(), "premiere vue disponible");
            Assert.IsTrue(_game.UseFilm(), "deuxieme vue disponible");
            Assert.IsTrue(_game.UseFilm(), "troisieme vue disponible");
            Assert.AreEqual(0, _game.CameraFilms, "plus de pellicule");
            Assert.IsFalse(_game.UseFilm(), "sans pellicule, pas de declenchement");
            Assert.AreEqual(5, _filmEvents.Count, "un declenchement refuse n'emet rien");

            // A rewind that does not touch the camera must not flicker the film
            // line of the HUD.
            int emitted = _filmEvents.Count;
            _game.RestoreCounters(0, 0, 1, 0);
            Assert.AreEqual(emitted, _filmEvents.Count, "restaurer la meme pellicule n'emet rien");
            _game.RestoreCounters(0, 0, 1, 2);
            Assert.AreEqual(emitted + 1, _filmEvents.Count, "restaurer une autre pellicule emet");
            Assert.AreEqual(2, _game.CameraFilms, "la pellicule restauree est celle de l'instant relu");
        }

        [Test]
        public void Reset_vide_le_niveau_sans_toucher_la_progression()
        {
            // PRD 9, first row: Reset zeroes everything EXCEPT the furthest
            // level, and announces nothing. Every counter is deliberately non
            // zero beforehand, so each assertion below has something to clear.
            _game.BeginLevel(4, 1);
            _game.CollectBattery();
            Assert.AreEqual(1, _game.InsertBatteries(), "une pile entre dans le teleporteur");
            _game.CollectBattery(true);
            _game.AddFilms(2);
            Assert.IsTrue(_game.CanTeleport(), "le teleporteur est charge avant le reset");

            // Subscribed here, so what follows counts the reset alone.
            Watch(_game);
            _game.Reset();
            Assert.AreEqual(0, _game.LevelIndex, "reset ramene au premier niveau");
            Assert.AreEqual(0, _game.CarriedBatteries, "reset vide les mains");
            Assert.AreEqual(0, _game.CarriedSealed, "reset vide le plomb porte");
            Assert.AreEqual(0, _game.InsertedBatteries, "reset vide le teleporteur");
            Assert.AreEqual(0, _game.RequiredBatteries, "reset vide l'exigence");
            Assert.AreEqual(0, _game.CameraFilms, "reset vide la pellicule");
            Assert.IsFalse(_game.CanTeleport(), "un teleporteur remis a zero ne part pas");
            Assert.AreEqual(4, _game.FurthestLevel, "reset ne touche pas la progression");
            Assert.AreEqual(0, _order.Count, "reset n'emet rien : c'est le niveau suivant qui annonce");
        }

        [Test]
        public void L_ordre_des_annonces_de_debut_de_niveau()
        {
            // PRD 9: BeginLevel announces the film, THEN the level, THEN the
            // batteries. The HUD follows that sequence, so a battery line
            // arriving before the level line would paint the counters of the
            // level just left. A count of emissions cannot see this.
            Watch(_game);
            _game.BeginLevel(2, 3);
            CollectionAssert.AreEqual(new[] { "films", "level", "batteries" }, _order,
                "l'ordre des annonces : pellicule, niveau, piles");
            Assert.AreEqual(0, _filmEvents[0], "la pellicule annoncee est vide");
            Assert.AreEqual(2, _levelStarts[0], "le niveau annonce est celui demande");
            Assert.AreEqual(0, _batteryEvents[0].carried, "etat emis : 0 portee, 0 inseree, 3 requises");
            Assert.AreEqual(0, _batteryEvents[0].inserted, "etat emis : 0 portee, 0 inseree, 3 requises");
            Assert.AreEqual(3, _batteryEvents[0].required, "etat emis : 0 portee, 0 inseree, 3 requises");
        }
    }
}
