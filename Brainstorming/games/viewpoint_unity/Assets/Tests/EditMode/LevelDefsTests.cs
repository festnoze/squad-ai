using System;
using System.Collections.Generic;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;

namespace Viewpoint.Tests
{
    /// <summary>
    /// Solvability invariants of the twenty five levels (PRD 13.4, port of
    /// <c>tests/test_level_defs.gd</c>): everything the player must reach stands
    /// on a platform, and enough batteries exist (world + duplicable via photos +
    /// camera films) to charge every teleporter.
    /// <para>
    /// The v4 rules the data has to honor as well: a visual standing cue in every
    /// level (there is no 3D preview anymore), showcase niches shallow enough for
    /// the 1.7 m interact range, and at least one level where the only tool is
    /// the camera (the empty sky photo as a piercing tool).
    /// </para>
    /// <para>
    /// The assertion messages are the original's, in French: they are the
    /// readable record of what broke, and a defect found here is read by whoever
    /// authored the level, not by whoever wrote the test.
    /// </para>
    /// <para>
    /// Every position is DESIGN space (PRD 4.1). Nothing here mirrors z: no
    /// assertion touches a Unity transform, so the data is compared to itself in
    /// the space it was authored in.
    /// </para>
    /// </summary>
    public sealed class LevelDefsTests
    {
        /// <summary>Decorative slabs that mark where a precision placement is meant to be shot.</summary>
        static readonly string[] MarkerColors = { "teal", "accent" };

        /// <summary>Interact range is 1.7 m, so a niche may not be deeper than this.</summary>
        const float MaxNicheDepth = 1.2f;

        /// <summary>
        /// A block at most this big on every axis comes out of the film as a loose
        /// crate, so it is a legitimate subject. Same threshold as
        /// <see cref="PhotoCapture.LooseMaxExtent"/>, and one case below pins the
        /// two together so the rule cannot drift on one side only.
        /// </summary>
        const float LooseMaxExtent = 1.6f;

        const int LevelCount = 25;

        // ---------------------------------------------------------- isolation

        // Nothing here writes to a registry, but everything here READS the photo
        // catalog through PhotoDefs.GetDef, which answers from the in game
        // registry first. A suite that ran before this one and left a cliche
        // behind would be answering questions asked of the catalog, so the
        // registry is emptied on both sides of every case. Groups, Materials,
        // GameState and PlayerPrefs are untouched by this suite, so they are left
        // to the suites that own them.

        [SetUp]
        public void SetUp()
        {
            PhotoDefs.ClearDynamic();
        }

        [TearDown]
        public void TearDown()
        {
            PhotoDefs.ClearDynamic();
        }

        // ---------------------------------------------------------- the shape

        [Test]
        public void Le_catalogue_compte_vingt_cinq_niveaux()
        {
            Assert.AreEqual(LevelCount, LevelDefs.Count, "vingt-cinq niveaux");
            // The original returns an empty dictionary out of range; the Unity
            // loader returns null, so a caller can probe past the last level.
            Assert.IsNull(LevelDefs.GetDef(-1), "index negatif : vide");
            Assert.IsNull(LevelDefs.GetDef(LevelCount), "index hors borne : vide");
        }

        [Test]
        public void Chaque_niveau_est_bien_forme()
        {
            for (int i = 0; i < LevelDefs.Count; i++)
            {
                LevelDef def = LevelDefs.GetDef(i);
                string where = "niveau " + (i + 1);
                Assert.IsNotNull(def, where + " : existe");
                Assert.IsFalse(string.IsNullOrEmpty(def.Name), where + " : nom");
                Assert.IsFalse(string.IsNullOrEmpty(def.Subtitle), where + " : sous-titre");
                Assert.Greater(def.Platforms.Count, 0, where + " : au moins une plateforme");
                Assert.IsNotNull(def.Teleporter, where + " : teleporteur");
                Assert.Greater(def.Teleporter.Required, 0, where + " : le teleporteur exige des piles");
            }
        }

        [Test]
        public void Tout_ce_qui_compte_est_pose_au_dessus_d_une_plateforme()
        {
            for (int i = 0; i < LevelDefs.Count; i++)
            {
                LevelDef def = LevelDefs.GetDef(i);
                string where = "niveau " + (i + 1);

                Assert.IsTrue(AbovePlatform(def, def.Spawn, 3f),
                    where + " : spawn au dessus d'une plateforme");
                Assert.IsTrue(AbovePlatform(def, def.Teleporter.Pos, 0.5f),
                    where + " : teleporteur pose sur une plateforme");

                foreach (Vector3 batteryPos in AllBatteries(def))
                {
                    Assert.IsTrue(AbovePlatform(def, batteryPos, 0.5f),
                        where + " : pile posee sur une plateforme");
                }

                foreach (PhotoPlacementDef photo in def.Photos)
                {
                    Assert.IsTrue(AbovePlatform(def, photo.Pos, 2f),
                        where + " : photo au dessus d'une plateforme");
                    Assert.IsNotNull(PhotoDefs.GetDef(photo.Id),
                        where + " : photo " + photo.Id + " au catalogue");
                }

                foreach (CageDef cage in def.Cages)
                {
                    Assert.IsTrue(AbovePlatform(def, cage.Pos, 0.5f),
                        where + " : cage posee sur une plateforme");
                    Assert.IsTrue(cage.Size.x > 0f && cage.Size.y > 0f && cage.Size.z > 0f,
                        where + " : cage de taille positive");
                }

                if (def.Camera != null)
                {
                    Assert.IsTrue(AbovePlatform(def, def.Camera.Pos, 0.5f),
                        where + " : appareil pose sur une plateforme");
                    Assert.Greater(def.Camera.Films, 0, where + " : l'appareil a de la pellicule");
                    Assert.IsTrue(HasASubject(def), where + " : l'appareil a quelque chose a photographier");
                }
            }
        }

        [Test]
        public void Le_seuil_de_la_caisse_lachee_suit_celui_de_la_pellicule()
        {
            // A camera is worth carrying when the level holds a battery to print
            // OR a block small enough to come back as a loose crate. That second
            // door is opened by exactly one number, and it lives in the runtime:
            // if PhotoCapture ever changes it, this suite must change with it,
            // not keep certifying level 23 against a stale 1.6.
            Assert.AreEqual(PhotoCapture.LooseMaxExtent, LooseMaxExtent, 0.0001f,
                "le seuil de caisse lachee suit PhotoCapture");
        }

        // ---------------------------------------------------------- solvability

        [Test]
        public void Chaque_teleporteur_a_de_quoi_etre_charge()
        {
            // Conservative solvability count. What the player can actually hold:
            //   - every battery standing in the open, leaden ones included (lead is
            //     worth exactly as much to a teleporter, it just never becomes two);
            //   - NOT the batteries locked in a steel cage, which no placement opens:
            //     those are models to photograph, never pickups;
            //   - the batteries a placed photo materializes, following photo-in-photo
            //     chains;
            //   - one copy per film, and only when SOME battery can be printed at all
            //     (a level whose only batteries are leaden gets nothing from its films).
            for (int i = 0; i < LevelDefs.Count; i++)
            {
                LevelDef def = LevelDefs.GetDef(i);
                int available = 0;
                int copyable = 0;

                foreach (Vector3 batteryPos in def.Batteries)
                {
                    copyable++;
                    if (!InSealedCage(def, batteryPos))
                    {
                        available++;
                    }
                }
                foreach (Vector3 sealedPos in def.SealedBatteries)
                {
                    if (!InSealedCage(def, sealedPos))
                    {
                        available++;
                    }
                }
                foreach (PhotoPlacementDef photo in def.Photos)
                {
                    available += PhotoDefs.BatteryCountRecursive(photo.Id);
                }
                if (def.Camera != null && copyable > 0)
                {
                    available += def.Camera.Films;
                }

                int required = def.Teleporter.Required;
                Assert.GreaterOrEqual(available, required, string.Format(
                    "niveau {0} : {1} piles accessibles pour {2} requises", i + 1, available, required));
            }
        }

        [Test]
        public void Une_pile_sous_acier_exige_un_objectif()
        {
            // A battery inside a steel cage can only ever leave it as a copy, so the
            // level MUST hand out a camera with film. Without this the level would
            // simply be a locked box, and the test suite would happily call it solvable.
            int cagedInTheGame = 0;
            int leadInTheGame = 0;

            for (int i = 0; i < LevelDefs.Count; i++)
            {
                LevelDef def = LevelDefs.GetDef(i);
                string where = "niveau " + (i + 1);
                int caged = 0;

                foreach (Vector3 batteryPos in def.Batteries)
                {
                    if (InSealedCage(def, batteryPos))
                    {
                        caged++;
                    }
                }
                cagedInTheGame += caged;
                leadInTheGame += def.SealedBatteries.Count;
                // A leaden battery in a steel cage is lost for good: no film prints it
                // and no placement opens the cage. It must never happen.
                foreach (Vector3 sealedPos in def.SealedBatteries)
                {
                    Assert.IsFalse(InSealedCage(def, sealedPos),
                        where + " : aucune pile plombee enfermee dans l'acier");
                }
                if (caged == 0)
                {
                    continue;
                }
                Assert.IsTrue(def.Camera != null && def.Camera.Films > 0,
                    where + " : une pile sous acier exige un appareil et de la pellicule");
            }

            // Both halves of the rule are conditional, so both can go quiet: with
            // no battery under steel anywhere the camera clause never runs, and
            // with no lead anywhere the lost-for-good clause never runs. The
            // mechanics are in the game (PRD 13.4), so say so here rather than let
            // the case pass on two skipped branches. 7 caged and 11 leaden on the
            // shipped data.
            Assert.Greater(cagedInTheGame, 0, "une pile sous acier existe quelque part dans le jeu");
            Assert.Greater(leadInTheGame, 0, "une pile plombee existe quelque part dans le jeu");
        }

        // ---------------------------------------------------------- teaching

        [Test]
        public void L_acier_et_le_plomb_sont_enseignes_seuls()
        {
            // Each refusal gets one level where it is the only new thing, before any
            // level combines them. Steel and lead are the two that need teaching; the
            // gravity of a placed crate is taught by the crate itself.
            int firstSteel = -1;
            int firstLead = -1;
            int both = -1;

            for (int i = 0; i < LevelDefs.Count; i++)
            {
                LevelDef def = LevelDefs.GetDef(i);
                bool steel = false;
                foreach (CageDef cage in def.Cages)
                {
                    steel = steel || cage.Sealed;
                }
                bool lead = def.SealedBatteries.Count > 0;

                if (steel && firstSteel < 0)
                {
                    firstSteel = i;
                }
                if (lead && firstLead < 0)
                {
                    firstLead = i;
                }
                if (steel && lead && both < 0)
                {
                    both = i;
                }
            }

            Assert.GreaterOrEqual(firstSteel, 0, "l'acier existe quelque part");
            Assert.GreaterOrEqual(firstLead, 0, "le plomb existe quelque part");
            Assert.IsTrue(both < 0 || both > firstSteel, "l'acier est enseigne seul avant d'etre combine");
            Assert.IsTrue(both < 0 || both > firstLead, "le plomb est enseigne seul avant d'etre combine");
        }

        [Test]
        public void Chaque_niveau_marque_une_place_au_sol()
        {
            // No 3D ghost preview since v4: each level marks at least one standing spot
            // with a thin tinted slab, otherwise a precision placement is pure guessing.
            for (int i = 0; i < LevelDefs.Count; i++)
            {
                LevelDef def = LevelDefs.GetDef(i);
                string where = "niveau " + (i + 1);
                int markers = 0;

                foreach (DecorDef decor in def.Decor)
                {
                    if (!IsMarkerColor(decor.Color))
                    {
                        continue;
                    }
                    markers++;
                    Assert.LessOrEqual(decor.Size.y, 0.2f, where + " : le repere est une dalle plate");
                }
                Assert.Greater(markers, 0, where + " : au moins un repere de pose au sol");
            }
        }

        [Test]
        public void Un_niveau_n_a_que_l_appareil_pour_percer()
        {
            // The empty photo is a tool, not a failure: at least one level hands out a
            // camera and NO catalog photo, so piercing has to come from a sky shot.
            int cameraOnly = 0;
            int withCamera = 0;

            for (int i = 0; i < LevelDefs.Count; i++)
            {
                LevelDef def = LevelDefs.GetDef(i);
                if (def.Camera == null)
                {
                    continue;
                }
                withCamera++;
                if (def.Photos.Count == 0)
                {
                    cameraOnly++;
                }
            }

            Assert.Greater(withCamera, 0, "au moins un niveau donne un appareil photo");
            Assert.Greater(cameraOnly, 0, "au moins un niveau n'a que l'appareil pour percer");
        }

        // ---------------------------------------------------------- geometry rules

        [Test]
        public void Les_vitrines_restent_a_portee_de_main()
        {
            // Interact range dropped to 1.7 m: no more picking a battery up through a
            // deep showcase. Niche panels stay within MaxNicheDepth.
            int niches = 0;
            for (int i = 0; i < LevelDefs.Count; i++)
            {
                LevelDef def = LevelDefs.GetDef(i);
                foreach (DecorDef decor in def.Decor)
                {
                    if (decor.Color != "battery_tip")
                    {
                        continue;
                    }
                    niches++;
                    Assert.LessOrEqual(Mathf.Min(decor.Size.x, decor.Size.z), MaxNicheDepth,
                        "niveau " + (i + 1) + " : niche de vitrine a portee de main");
                }
            }
            // The rule is vacuous if the data grew out of every showcase: say so
            // rather than pass on an empty loop.
            Assert.Greater(niches, 0, "la vitrine existe quelque part dans le jeu");
        }

        [Test]
        public void Les_cages_sont_bien_formees()
        {
            // Any cage that is not steel breaks under a placement catching its center;
            // the lavender/dark tint is lore only. Steel is the one real difference,
            // and it is declared, not inferred.
            int cages = 0;

            for (int i = 0; i < LevelDefs.Count; i++)
            {
                LevelDef def = LevelDefs.GetDef(i);
                string where = "niveau " + (i + 1);

                foreach (CageDef cage in def.Cages)
                {
                    cages++;
                    Assert.IsTrue(cage.Size.x >= 1f && cage.Size.z >= 1f,
                        where + " : cage assez large pour son contenu");
                    Assert.IsTrue(AbovePlatform(def, cage.Pos, 0.5f),
                        where + " : cage posee sur une plateforme");
                    // Steel and lavender are opposites: a cage is never both. The
                    // loader already resolves steel over lavender (PRD 13.1), so
                    // this holds the resolution to its promise rather than trusting it.
                    Assert.IsFalse(cage.Sealed && cage.Erasable,
                        where + " : une cage d'acier n'est pas lavande");
                }
            }
            Assert.Greater(cages, 0, "les cages existent quelque part dans le jeu");
        }

        [Test]
        public void Chaque_cage_declare_son_toit()
        {
            // The loader defaults an absent roof to TRUE (PRD 13.1), so by the time
            // a cage reaches CageDef a silent omission and a stated true look
            // identical: only the authored text can say which it was, and the rule
            // is that the level STATES it. This assembly cannot reference Newtonsoft
            // (its asmdef overrides precompiled references down to nunit alone), so
            // the count is read from the text: in levels.json "roof" is a cage key
            // and nothing else, written once per cage.
            TextAsset asset = Resources.Load<TextAsset>(PhotoJson.LevelsResource);
            Assert.IsNotNull(asset, "Resources/" + PhotoJson.LevelsResource + ".json est lisible");

            int declared = CountOccurrences(asset.text, "\"roof\"");
            int cages = 0;
            for (int i = 0; i < LevelDefs.Count; i++)
            {
                cages += LevelDefs.GetDef(i).Cages.Count;
            }

            Assert.Greater(cages, 0, "les cages existent quelque part dans le jeu");
            Assert.AreEqual(cages, declared, "chaque cage declare son toit");
        }

        static int CountOccurrences(string text, string needle)
        {
            int total = 0;
            int at = text.IndexOf(needle, StringComparison.Ordinal);
            while (at >= 0)
            {
                total++;
                at = text.IndexOf(needle, at + needle.Length, StringComparison.Ordinal);
            }
            return total;
        }

        [Test]
        public void Le_sol_pale_reste_l_exception()
        {
            // The pale ground is the exception, so it has to be rare and it has to be
            // taught: exactly the levels that need a pierceable floor declare one, and
            // at least one level does, or the language would never be shown.
            int softLevels = 0;
            int softSlabs = 0;

            for (int i = 0; i < LevelDefs.Count; i++)
            {
                LevelDef def = LevelDefs.GetDef(i);
                int here = 0;
                foreach (PlatformDef platform in def.Platforms)
                {
                    if (!platform.Soft)
                    {
                        continue;
                    }
                    here++;
                    Assert.IsTrue(platform.Size.x > 0f && platform.Size.y > 0f && platform.Size.z > 0f,
                        "niveau " + (i + 1) + " : sol pale de taille positive");
                }
                if (here > 0)
                {
                    softLevels++;
                    softSlabs += here;
                }
            }

            Assert.GreaterOrEqual(softLevels, 1, "au moins un niveau enseigne le sol effacable");
            Assert.LessOrEqual(softLevels, 5, "le sol effacable reste l'exception, pas la regle");
            Assert.GreaterOrEqual(softSlabs, softLevels, "chaque niveau concerne a au moins une dalle pale");
        }

        [Test]
        public void Le_plan_de_mort_passe_sous_les_plateformes()
        {
            int slabs = 0;
            for (int i = 0; i < LevelDefs.Count; i++)
            {
                LevelDef def = LevelDefs.GetDef(i);
                float killY = def.KillY;
                foreach (PlatformDef platform in def.Platforms)
                {
                    slabs++;
                    float bottom = platform.Pos.y - platform.Size.y * 0.5f;
                    Assert.Less(killY, bottom, "niveau " + (i + 1) + " : kill_y sous les plateformes");
                }
            }
            // Every assertion above lives inside the platform loop, so a data load
            // that returned levels without platforms would make this case pass
            // having compared nothing. 57 slabs on the shipped data.
            Assert.Greater(slabs, 0, "les plateformes existent quelque part dans le jeu");
        }

        // ---------------------------------------------------------- the audit gate

        [Test]
        public void L_audit_de_level_design_ne_trouve_aucun_defaut()
        {
            // The geometric audit of PRD 17.4 lives in the Editor assembly, which
            // the test assembly does not reference, so it is reached by name. A
            // missing audit is a FAILURE and not a skip: an audit nobody runs is an
            // audit nobody has to satisfy.
            Type audit = FindType("Viewpoint.Editor.DesignAudit");
            Assert.IsNotNull(audit, "l'audit de level design est introuvable : Viewpoint.Editor.DesignAudit");

            MethodInfo collect = audit.GetMethod("Collect", BindingFlags.Public | BindingFlags.Static);
            Assert.IsNotNull(collect, "l'audit expose Collect() pour le harnais");

            object result = collect.Invoke(null, null);
            IEnumerable<string> reported = result as IEnumerable<string>;
            Assert.IsNotNull(reported, "l'audit rend la liste de ses defauts");
            List<string> defects = new List<string>(reported);

            // Zero defects only counts as a pass when the audit actually walked the
            // levels. An empty list from an audit that examined nothing is the exact
            // shape of a green run that verified nothing.
            int levelsAudited = ReadInt(audit, "LastLevelsAudited");
            int inspections = ReadInt(audit, "LastInspections");
            // Against the CONSTANT, not against LevelDefs.Count: a data load that
            // produced no level at all would make the two counts agree at zero and
            // the gate would certify an empty catalog.
            Assert.AreEqual(LevelCount, levelsAudited,
                "l'audit a bien parcouru les " + LevelCount + " niveaux");
            // 340 on the shipped data (25 levels, 128 poses, 51 reperes, 116
            // surfaces, 14 piles imprimables, 6 poses declarees).
            Assert.Greater(inspections, 300,
                "l'audit a bien examine les poses, les reperes et les surfaces (" + inspections + " controles)");

            Assert.AreEqual(0, defects.Count,
                "audit de level design : " + defects.Count + " defaut(s)\n"
                + string.Join("\n", defects.ToArray()));
        }

        [Test]
        public void L_audit_de_level_design_sait_encore_trouver_un_defaut()
        {
            // The gate above asserts an EMPTY report, which is also what an audit
            // whose checks had all been gutted would return: same empty list, same
            // green run, nothing verified. The counters prove the walk happened;
            // they cannot prove it still judges anything. So the audit is handed
            // three levels it has never seen, and has to answer differently on
            // each. Nothing else in the harness can catch a silently blind audit.
            Type audit = FindType("Viewpoint.Editor.DesignAudit");
            Assert.IsNotNull(audit, "l'audit de level design est introuvable : Viewpoint.Editor.DesignAudit");

            MethodInfo collectFor = audit.GetMethod("CollectFor", BindingFlags.Public | BindingFlags.Static);
            Assert.IsNotNull(collectFor, "l'audit expose CollectFor(LevelDef) pour le harnais");

            // A 20 x 20 slab with its top at y = 0, the spawn and the teleporter on
            // it, and one battery standing on it 3 m in front: nothing to report.
            List<string> clean = AuditProbe(collectFor, Probe(new Vector3(0f, 0f, 3f)));
            Assert.AreEqual(0, clean.Count,
                "le niveau temoin est sain : " + string.Join("\n", clean.ToArray()));

            // The same battery pushed 50 m sideways, off every surface of the
            // level: there is nothing under it at all.
            List<string> nowhere = AuditProbe(collectFor, Probe(new Vector3(50f, 0f, 0f)));
            Assert.AreEqual(1, nowhere.Count,
                "une pile hors de toute surface : un defaut et un seul (" + string.Join("\n", nowhere.ToArray()) + ")");
            Assert.IsTrue(nowhere[0].Contains("[VIDE]"),
                "une pile hors de toute surface est signalee VIDE : " + nowhere[0]);
            Assert.IsTrue(nowhere[0].Contains("une pile"),
                "le defaut nomme la pile en cause : " + nowhere[0]);

            // And back over the slab, but 3 m up: it has a support, out of reach of
            // it. STANDING_SLACK is 0.5 m, so this is the other side of the same
            // rule and it must not be answered with silence.
            List<string> floating = AuditProbe(collectFor, Probe(new Vector3(0f, 3f, 0f)));
            Assert.AreEqual(1, floating.Count,
                "une pile a 3 m de son appui : un defaut et un seul (" + string.Join("\n", floating.ToArray()) + ")");
            Assert.IsTrue(floating[0].Contains("[FLOTTE]"),
                "une pile trop haut sur son appui est signalee FLOTTE : " + floating[0]);
        }

        static List<string> AuditProbe(MethodInfo collectFor, LevelDef def)
        {
            object result = collectFor.Invoke(null, new object[] { def });
            IEnumerable<string> reported = result as IEnumerable<string>;
            Assert.IsNotNull(reported, "l'audit rend la liste de ses defauts");
            return new List<string>(reported);
        }

        /// <summary>
        /// The smallest level the audit can call sound: one slab, the spawn and the
        /// teleporter standing on it, one battery wherever the caller wants it. No
        /// photo and no camera, so the TRIVIALE checks stay out of the way; the
        /// teleporter sits inside the slab footprint, so the single surface is not
        /// read as a dead end either.
        /// </summary>
        static LevelDef Probe(Vector3 batteryPos)
        {
            LevelDef def = new LevelDef();
            def.Name = "sonde";
            def.Subtitle = "sonde";
            def.Spawn = new Vector3(0f, 0f, 0f);
            def.KillY = -20f;

            PlatformDef ground = new PlatformDef();
            ground.Pos = new Vector3(0f, -0.5f, 0f);
            ground.Size = new Vector3(20f, 1f, 20f);
            def.Platforms.Add(ground);

            def.Batteries.Add(batteryPos);

            def.Teleporter = new TeleporterDef();
            def.Teleporter.Pos = new Vector3(0f, 0f, -5f);
            def.Teleporter.Required = 1;
            return def;
        }

        static int ReadInt(Type type, string propertyName)
        {
            PropertyInfo property = type.GetProperty(propertyName, BindingFlags.Public | BindingFlags.Static);
            Assert.IsNotNull(property, "l'audit expose " + propertyName);
            return Convert.ToInt32(property.GetValue(null, null));
        }

        static Type FindType(string fullName)
        {
            foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type found;
                try
                {
                    found = assembly.GetType(fullName, false);
                }
                catch (Exception)
                {
                    // A dynamic or unloadable assembly is simply not the one.
                    continue;
                }
                if (found != null)
                {
                    return found;
                }
            }
            return null;
        }

        // ---------------------------------------------------------- helpers

        /// <summary>
        /// True when the point stands on top of one of the level's platform slabs,
        /// no higher than maxHeight above its surface.
        /// </summary>
        static bool AbovePlatform(LevelDef def, Vector3 point, float maxHeight)
        {
            foreach (PlatformDef platform in def.Platforms)
            {
                Vector3 pos = platform.Pos;
                Vector3 size = platform.Size;
                float top = pos.y + size.y * 0.5f;
                if (Mathf.Abs(point.x - pos.x) <= size.x * 0.5f
                    && Mathf.Abs(point.z - pos.z) <= size.z * 0.5f
                    && point.y >= top - 0.05f
                    && point.y <= top + maxHeight)
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>
        /// True when the point stands inside the volume of a cage no placement
        /// breaks. Cage Pos is the center of the cage FLOOR, Size the whole
        /// enclosure (PRD 13.1).
        /// </summary>
        static bool InSealedCage(LevelDef def, Vector3 point)
        {
            foreach (CageDef cage in def.Cages)
            {
                if (!cage.Sealed)
                {
                    continue;
                }
                if (Mathf.Abs(point.x - cage.Pos.x) <= cage.Size.x * 0.5f
                    && Mathf.Abs(point.z - cage.Pos.z) <= cage.Size.z * 0.5f
                    && point.y >= cage.Pos.y - 0.05f
                    && point.y <= cage.Pos.y + cage.Size.y)
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>Every battery of a level, whatever list it comes from.</summary>
        static List<Vector3> AllBatteries(LevelDef def)
        {
            List<Vector3> all = new List<Vector3>();
            all.AddRange(def.Batteries);
            all.AddRange(def.SealedBatteries);
            return all;
        }

        /// <summary>
        /// A camera is only worth carrying when something in the level is worth
        /// printing. That used to mean a battery, and it no longer does: a level may
        /// hand out film purely to copy a CRATE and stack it (level 23 is built on
        /// exactly that, and its two batteries are leaden on purpose). So the subject
        /// can be either a battery a film can print, or a block small enough on every
        /// axis to come back as a loose crate.
        /// </summary>
        static bool HasASubject(LevelDef def)
        {
            if (def.Batteries.Count > 0)
            {
                return true;
            }
            foreach (DecorDef decor in def.Decor)
            {
                if (IsCrateSized(decor.Size))
                {
                    return true;
                }
            }
            foreach (ErasableDef erasable in def.Erasables)
            {
                if (IsCrateSized(erasable.Size))
                {
                    return true;
                }
            }
            return false;
        }

        static bool IsCrateSized(Vector3 size)
        {
            return size.x <= LooseMaxExtent && size.y <= LooseMaxExtent && size.z <= LooseMaxExtent;
        }

        static bool IsMarkerColor(string color)
        {
            for (int i = 0; i < MarkerColors.Length; i++)
            {
                if (MarkerColors[i] == color)
                {
                    return true;
                }
            }
            return false;
        }
    }
}
