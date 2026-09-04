using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace Viewpoint.Tests
{
    /// <summary>
    /// Does the game actually start, and does a level actually get built.
    ///
    /// This is deliberately the first test written: everything else in the
    /// harness is worth nothing if Main throws in Awake, and a compile is no
    /// evidence at all that it does not. Each case loads the real scene through
    /// the real boot path, so what is under test is the game and not a fixture.
    /// </summary>
    public sealed class BootTests
    {
        const string ScenePath = "Assets/Scenes/Main.unity";

        Main _main;

        [UnitySetUp]
        public IEnumerator SetUp()
        {
            // A test run must not inherit the previous one's progression: the
            // level grid would unlock levels this case never reached.
            PlayerPrefs.DeleteKey(GameState.ProgressKey);
            GameState.Instance = null;

            SceneManager.LoadScene(ScenePath, LoadSceneMode.Single);
            yield return null;
            yield return null;

            _main = Object.FindAnyObjectByType<Main>();
            Assert.IsNotNull(_main, "la scene Main ne porte pas de composant Main");
        }

        [UnityTest]
        public IEnumerator Le_jeu_demarre_sur_le_titre()
        {
            yield return null;
            Assert.IsNotNull(_main.Player, "le joueur est construit");
            Assert.IsNotNull(_main.Hud, "le HUD est construit");
            Assert.IsNotNull(_main.Menu, "le menu est construit");
            Assert.IsNotNull(_main.Rewind, "le rembobinage est construit");
            Assert.IsNotNull(_main.LevelRoot, "la racine de niveau existe");
            Assert.AreEqual(MenuMode.Title, _main.Menu.Mode, "on demarre sur l'ecran titre");
            Assert.IsFalse(_main.Player.ControlEnabled, "la main est coupee sur le titre");
        }

        [UnityTest]
        public IEnumerator Le_niveau_1_se_construit()
        {
            _main.StartAt(0);
            yield return null;
            yield return null;

            LevelDef def = LevelDefs.GetDef(0);
            Assert.IsNotNull(def, "le niveau 1 existe dans la donnee");

            // The counts the original's probe checks first (PRD 17.3 step 1).
            Assert.AreEqual(def.Platforms.Count, Groups.Count(Groups.Platform), "plateformes construites");
            Assert.AreEqual(def.Photos.Count, Groups.Count(Groups.PhotoItem), "photos construites");
            Assert.AreEqual(def.Batteries.Count + def.SealedBatteries.Count,
                Groups.Count(Groups.Battery), "piles construites");
            Assert.AreEqual(1, Groups.Count(Groups.Teleporter), "un teleporteur");
            Assert.IsTrue(_main.Player.ControlEnabled, "le joueur a la main en jeu");
        }

        [UnityTest]
        public IEnumerator Le_sol_gris_ne_se_decoupe_pas_mais_se_photographie()
        {
            _main.StartAt(0);
            yield return null;

            // THE GROUND LANGUAGE (PRD 5.1). Grey stays, pale goes: a platform is
            // photographable but never carvable, and everything carvable is
            // photographable, or a photo would lie about what was in frame.
            List<ErasableBlock> carvable = Groups.Snapshot<ErasableBlock>(Groups.Carvable);
            List<ErasableBlock> photographable = Groups.Snapshot<ErasableBlock>(Groups.Photographable);

            Assert.Greater(photographable.Count, carvable.Count,
                "on photographie plus de choses qu'on n'en decoupe");
            foreach (ErasableBlock block in carvable)
            {
                Assert.Contains(block, photographable,
                    "tout ce qui est decoupable est aussi photographiable");
            }
            foreach (ErasableBlock platform in Groups.Snapshot<ErasableBlock>(Groups.Platform))
            {
                Assert.IsFalse(carvable.Contains(platform),
                    "le sol gris n'est pas decoupable : une photo s'y ajoute");
                Assert.Contains(platform, photographable,
                    "une plateforme reste photographiable");
            }
        }

        [UnityTest]
        public IEnumerator Les_vingt_cinq_niveaux_se_construisent()
        {
            _main.StartAt(0);
            yield return null;

            Assert.AreEqual(25, LevelDefs.Count, "vingt-cinq niveaux");

            for (var i = 0; i < LevelDefs.Count; i++)
            {
                _main.LoadLevel(i);
                yield return null;

                LevelDef def = LevelDefs.GetDef(i);
                string where = "niveau " + (i + 1);

                // Rebuilding must leave NOTHING of the level just left. This is
                // the assertion that catches the deferred-destroy trap: Unity
                // defers Destroy and its OnDisable to the end of the frame, so a
                // teardown that used it would leave every group double counted
                // here while the game still looked fine on screen.
                Assert.AreEqual(def.Platforms.Count, Groups.Count(Groups.Platform),
                    where + " : plateformes construites");
                Assert.AreEqual(def.Photos.Count, Groups.Count(Groups.PhotoItem),
                    where + " : photos construites");
                Assert.AreEqual(def.Batteries.Count + def.SealedBatteries.Count,
                    Groups.Count(Groups.Battery), where + " : piles construites");
                Assert.AreEqual(def.Batteries.Count, Groups.Count(Groups.CopyableBattery),
                    where + " : le plomb reste hors de la pellicule");
                Assert.AreEqual(1, Groups.Count(Groups.Teleporter),
                    where + " : un seul teleporteur");
                Assert.AreEqual(def.Cages.Count, Groups.Count(Groups.Cage),
                    where + " : cages construites");

                var breakable = 0;
                foreach (CageDef cage in def.Cages)
                {
                    if (!cage.Sealed)
                    {
                        breakable++;
                    }
                }
                Assert.AreEqual(breakable, Groups.Count(Groups.Breakable),
                    where + " : cages cassables construites");
            }
        }
    }
}
