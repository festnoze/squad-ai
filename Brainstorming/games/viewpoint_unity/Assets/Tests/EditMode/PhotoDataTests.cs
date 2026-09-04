using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Viewpoint.Tests
{
    /// <summary>
    /// The port's own invariant, the one the nine ported suites cannot state:
    /// the data the game ships IS the data exported from the original.
    ///
    /// docs/data/*.json is the source of truth, exported verbatim from
    /// games/viewpoint/src (PRD 19.1). Assets/Resources/Data/*.json is the copy
    /// Unity actually loads (PRD 15.5). Every other test in this harness reads
    /// the copy, so a silent divergence between the two would make every one of
    /// them pass while the port had quietly become a different game: different
    /// erase depths, different platforms, different puzzles. Hence a byte for
    /// byte comparison, not a semantic one - a reformat, a rounded literal or a
    /// changed line ending are all divergences worth failing on, because they
    /// all mean somebody edited the copy instead of the source.
    ///
    /// EditMode only: docs/ is a sibling of Assets/ in the repository and does
    /// not exist in a built player.
    /// </summary>
    public sealed class PhotoDataTests
    {
        const string PhotosFile = "photos.json";
        const string LevelsFile = "levels.json";

        /// <summary>What Unity loads: Assets/Resources/Data/&lt;file&gt;.</summary>
        static string ShippedPath(string file)
        {
            return Path.Combine(Application.dataPath, "Resources", "Data", file);
        }

        /// <summary>The source of truth: &lt;project&gt;/docs/data/&lt;file&gt;.</summary>
        static string SourcePath(string file)
        {
            // Application.dataPath is <project>/Assets, so its parent is the
            // project root, which is where docs/ lives.
            string root = Path.GetDirectoryName(Application.dataPath);
            return Path.Combine(root, "docs", "data", file);
        }

        [Test]
        public void PhotosJsonIsTheExportedSource()
        {
            AssertIdentical(PhotosFile);
        }

        [Test]
        public void LevelsJsonIsTheExportedSource()
        {
            AssertIdentical(LevelsFile);
        }

        [Test]
        public void LoaderShape()
        {
            // The two files behind these three numbers are the ones compared
            // above: this is the other half of the invariant, that the bytes are
            // not merely identical but actually parsed into the game.
            Assert.AreEqual(8, PhotoDefs.AllIds().Length, "huit photos chargees");
            Assert.AreEqual(25, LevelDefs.Count, "vingt-cinq niveaux charges");
            Assert.AreEqual(6, LevelDefs.DecorIslands.Count, "six ilots de decor");

            Assert.IsNotNull(LevelDefs.GetDef(0), "le premier niveau est charge");
            Assert.IsNotNull(LevelDefs.GetDef(24), "le dernier niveau est charge");
            Assert.IsNull(LevelDefs.GetDef(25), "rien au dela du dernier niveau");
            Assert.IsNull(LevelDefs.GetDef(-1), "rien avant le premier niveau");

            // The byte comparison rests on a path convention, and nothing above
            // says the loader reads THAT path (PRD 15.5). Without these two, the
            // suite would stay green with PhotoJson pointed at another resource,
            // which is exactly the divergence the whole file exists to catch.
            AssertResourceIsTheShippedFile(PhotoJson.PhotosResource, PhotosFile);
            AssertResourceIsTheShippedFile(PhotoJson.LevelsResource, LevelsFile);
        }

        [Test]
        public void CommentKeysAreIgnored()
        {
            // Both files carry a "_comment" key saying where they were exported
            // from. The loader reads the keys it knows and steps over that one; a
            // stricter reader would have thrown at load, and the game would not
            // boot at all rather than boot with a wrong level.
            List<string> levelKeys = TopLevelKeys(LevelsFile);
            Assert.AreEqual(3, levelKeys.Count, "levels.json porte trois cles de premier niveau");
            Assert.IsTrue(levelKeys.Contains("_comment"), "levels.json documente sa provenance dans _comment");
            Assert.IsTrue(levelKeys.Contains("decor_islands"), "levels.json porte la cle decor_islands");
            Assert.IsTrue(levelKeys.Contains("levels"), "levels.json porte la cle levels");
            Assert.AreEqual(25, LevelDefs.Count, "la cle _comment n'empeche pas le chargement des niveaux");

            List<string> photoKeys = TopLevelKeys(PhotosFile);
            Assert.AreEqual(2, photoKeys.Count, "photos.json porte deux cles de premier niveau");
            Assert.IsTrue(photoKeys.Contains("_comment"), "photos.json documente sa provenance dans _comment");
            Assert.IsTrue(photoKeys.Contains("photos"), "photos.json porte la cle photos");
            Assert.AreEqual(8, PhotoDefs.AllIds().Length, "la cle _comment n'empeche pas le chargement du catalogue");
        }

        // --------------------------------------------------------------- tools

        /// <summary>
        /// What Resources.Load hands PhotoJson is the file under
        /// Assets/Resources/Data that the byte comparison checked. Compared as
        /// parsed JSON rather than as raw text: the byte test already owns the
        /// formatting of that file, and this one owns the identity of the asset.
        /// </summary>
        static void AssertResourceIsTheShippedFile(string resource, string file)
        {
            TextAsset asset = Resources.Load<TextAsset>(resource);
            Assert.IsNotNull(asset, "Resources/" + resource + " est chargeable");
            JObject loaded = JObject.Parse(asset.text);
            JObject onDisk = JObject.Parse(File.ReadAllText(ShippedPath(file)));
            Assert.IsTrue(JToken.DeepEquals(loaded, onDisk),
                resource + " : la ressource chargee est bien " + file);
        }

        static List<string> TopLevelKeys(string file)
        {
            string path = ShippedPath(file);
            Assert.IsTrue(File.Exists(path), "Assets/Resources/Data/" + file + " est present");
            JObject root = JObject.Parse(File.ReadAllText(path));
            List<string> keys = new List<string>();
            foreach (JProperty property in root.Properties())
            {
                keys.Add(property.Name);
            }
            return keys;
        }

        static void AssertIdentical(string file)
        {
            string shipped = ShippedPath(file);
            string source = SourcePath(file);
            Assert.IsTrue(File.Exists(shipped), "Assets/Resources/Data/" + file + " est present");
            Assert.IsTrue(File.Exists(source), "docs/data/" + file + " est present");

            byte[] shippedBytes = File.ReadAllBytes(shipped);
            byte[] sourceBytes = File.ReadAllBytes(source);

            // A run where both files had been emptied would otherwise pass.
            Assert.IsTrue(sourceBytes.Length > 0, "docs/data/" + file + " n'est pas vide");
            Assert.AreEqual(sourceBytes.Length, shippedBytes.Length,
                file + " : meme taille que la source exportee dans docs/data");

            // Report the offset rather than dumping two files' worth of bytes: it
            // is the one number that says where to look.
            var divergence = -1;
            for (var i = 0; i < sourceBytes.Length; i++)
            {
                if (sourceBytes[i] != shippedBytes[i])
                {
                    divergence = i;
                    break;
                }
            }
            Assert.AreEqual(-1, divergence,
                file + " : identique octet pour octet a docs/data (premier octet divergent : "
                    + divergence + ")");
        }
    }
}
