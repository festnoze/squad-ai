using System.IO;
using System.Linq;
using NUnit.Framework;
using OutOfSight.Core;

namespace OutOfSight.Tests
{
    /// <summary>
    /// PRD 11 M3 gate: a licence file lists every imported model and sound. Every file under
    /// Assets/ThirdParty must be named in docs/LICENSES.md, with its licence.
    /// Audio overhaul: the music is CC BY 4.0 (Kevin MacLeod), the only attribution licence allowed; its rows must sit
    /// under Music/ and every credited title must be in the game's own attribution line (title.musicCredits).
    /// </summary>
    public sealed class LicenseTests
    {
        private const string ThirdParty = "Assets/ThirdParty";
        private const string Licenses = "docs/LICENSES.md";

        [Test]
        public void Every_third_party_file_is_in_the_licence_file()
        {
            Assert.IsTrue(File.Exists(Licenses), "docs/LICENSES.md is missing");
            string text = File.ReadAllText(Licenses);
            string[] files = Directory.Exists(ThirdParty)
                ? Directory.GetFiles(ThirdParty, "*", SearchOption.AllDirectories)
                    .Where(f => !f.EndsWith(".meta")).ToArray()
                : new string[0];
            // Premise: M3 imports models and sounds; an empty folder would make this test vacuous.
            Assert.GreaterOrEqual(files.Length, 10, "fewer third party files than expected: the check would prove nothing");
            var missing = files.Select(Path.GetFileName).Where(name => !text.Contains("`" + name + "`")
                && !text.Contains("/" + name + "`")).ToList();
            Assert.IsEmpty(missing, "files without a line in docs/LICENSES.md: " + string.Join(", ", missing));
        }

        [Test]
        public void Every_listed_asset_is_cc0()
        {
            string[] rows = File.ReadAllLines(Licenses).Where(l => l.StartsWith("| `")).ToArray();
            Assert.GreaterOrEqual(rows.Length, 10, "no asset rows found in docs/LICENSES.md");
            foreach (string row in rows)
            {
                // M7 title redesign: the title font is under the SIL Open Font License. Audio overhaul: the music is CC BY 4.0,
                // checked by Music_is_cc_by_and_credited_in_game.
                bool music = row.StartsWith("| `Music/") && row.Contains("CC BY 4.0");
                Assert.IsTrue(row.Contains("CC0") || row.Contains("SIL OFL 1.1") || music,
                    "an asset is neither CC0, SIL OFL 1.1 nor CC BY 4.0 music: " + row);
            }
        }

        [Test]
        public void Music_is_cc_by_and_credited_in_game()
        {
            string[] rows = File.ReadAllLines(Licenses).Where(l => l.StartsWith("| `") && l.Contains("CC BY")).ToArray();
            Assert.GreaterOrEqual(rows.Length, 2, "premise: the two music loops are listed as CC BY 4.0");
            foreach (string language in new[] { Strings.English, Strings.French })
            {
                string credits = Strings.Get("title.musicCredits", language);
                StringAssert.Contains("Kevin MacLeod", credits, language + ": the in-game credit names no author");
                StringAssert.Contains("incompetech.com", credits, language + ": the in-game credit names no source");
                StringAssert.Contains("CC BY 4.0", credits, language + ": the in-game credit names no licence");
                foreach (string row in rows)
                {
                    StringAssert.StartsWith("| `Music/", row, "a CC BY asset outside the music");
                    // The row's title column carries the track's title in double quotes.
                    string[] cells = row.Split('|');
                    Assert.Greater(cells.Length, 3, "malformed row: " + row);
                    string title = cells[2].Trim();
                    int open = title.IndexOf('"');
                    int close = title.IndexOf('"', open + 1);
                    Assert.IsTrue(open >= 0 && close > open, "the title of a music row is not quoted: " + row);
                    StringAssert.Contains(title.Substring(open, close - open + 1), credits, language + ": a credited track is missing in game");
                }
            }
        }
    }
}
