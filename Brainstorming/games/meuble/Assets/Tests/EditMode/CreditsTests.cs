using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using OutOfSight.Core;

namespace OutOfSight.Tests
{
    /// <summary>
    /// The Credits page (Core.Credits) against docs/LICENSES.md, the source of truth: every attribution licence row
    /// (CC BY 4.0, SIL OFL 1.1) has its title, its authors and its licence on the page, a CC BY row its source URL too;
    /// every third party CC0 row has its author and its pack (the sound effects their pack title), credited anyway. In
    /// English and in French.
    /// </summary>
    public sealed class CreditsTests
    {
        private const string Licenses = "docs/LICENSES.md";
        private static readonly string[] Languages = { Strings.English, Strings.French };
        // Rows whose assets are not third party (LICENSES.md sections Environment and Characters).
        private static readonly string[] OwnAuthors = { "Product owner", "Out of Sight team" };

        private sealed class Row
        {
            public string Line;
            public string File;
            public string Title;
            public string Author;
            public string Source;
            public string Licence;
        }

        private static List<Row> Rows()
        {
            Assert.IsTrue(File.Exists(Licenses), "docs/LICENSES.md is missing");
            var rows = new List<Row>();
            foreach (string line in File.ReadAllLines(Licenses).Where(l => l.StartsWith("| `")))
            {
                string[] cells = line.Split('|').Select(c => c.Trim()).ToArray();
                Assert.GreaterOrEqual(cells.Length, 7, "malformed row: " + line);
                rows.Add(new Row { Line = line, File = cells[1], Title = cells[2], Author = cells[3], Source = cells[4], Licence = cells[5] });
            }
            return rows;
        }

        /// <summary>The text before the first " (" (a parenthetical detail of the cell).</summary>
        private static string Head(string cell)
        {
            int open = cell.IndexOf(" (");
            return (open >= 0 ? cell.Substring(0, open) : cell).Trim();
        }

        /// <summary>The text inside the cell's first parentheses, or null.</summary>
        private static string Inside(string cell)
        {
            int open = cell.IndexOf('(');
            int close = cell.IndexOf(')', open + 1);
            return open >= 0 && close > open ? cell.Substring(open + 1, close - open - 1).Trim() : null;
        }

        private static void AssertOnPage(string expected, string what, Row row)
        {
            foreach (string language in Languages)
            {
                StringAssert.Contains(expected, Credits.FullText(language), $"{language}: the Credits page misses the {what} of {row.Line}");
            }
        }

        [Test]
        public void Every_cc_by_row_is_fully_attributed()
        {
            List<Row> rows = Rows().Where(r => r.Licence.Contains("CC BY")).ToList();
            Assert.GreaterOrEqual(rows.Count, 2, "premise: the two music loops are listed as CC BY 4.0");
            foreach (Row row in rows)
            {
                int open = row.Title.IndexOf('"');
                int close = row.Title.IndexOf('"', open + 1);
                Assert.IsTrue(open >= 0 && close > open, "the title of a CC BY row is not quoted: " + row.Line);
                AssertOnPage(row.Title.Substring(open, close - open + 1), "title", row);
                AssertOnPage(Head(row.Author), "author", row);
                AssertOnPage("CC BY 4.0", "licence", row);
                AssertOnPage("https://creativecommons.org/licenses/by/4.0/", "licence link", row);
                string url = row.Source.Split(' ').FirstOrDefault(token => token.StartsWith("http"));
                Assert.IsNotNull(url, "a CC BY row has no source URL: " + row.Line);
                AssertOnPage(url, "source URL", row);
            }
        }

        [Test]
        public void Every_ofl_row_is_attributed()
        {
            List<Row> rows = Rows().Where(r => r.Licence.Contains("SIL OFL")).ToList();
            Assert.GreaterOrEqual(rows.Count, 1, "premise: the title font is listed under the SIL OFL 1.1");
            foreach (Row row in rows)
            {
                // The font family: the title's first three words ("DM Serif Display").
                string family = string.Join(" ", row.Title.Split(' ').Take(3));
                AssertOnPage(family, "font name", row);
                foreach (string author in Head(row.Author).Split(','))
                {
                    AssertOnPage(author.Trim(), "author", row);
                }
                AssertOnPage("SIL Open Font License 1.1", "licence", row);
            }
        }

        [Test]
        public void Every_third_party_cc0_author_and_pack_is_credited()
        {
            List<Row> rows = Rows().Where(r => r.Licence.Contains("CC0") && !OwnAuthors.Contains(Head(r.Author))).ToList();
            Assert.GreaterOrEqual(rows.Count, 20, "premise: the CC0 models and sounds are listed");
            foreach (Row row in rows)
            {
                AssertOnPage(Head(row.Author), "author", row);
                string pack = Inside(row.Author);
                if (pack != null)
                {
                    AssertOnPage("\"" + pack + "\"", "pack", row);
                }
                if (row.File.Contains(".wav`"))
                {
                    AssertOnPage("\"" + Head(row.Title) + "\"", "sound pack", row);
                }
            }
        }

        [Test]
        public void Credits_name_the_creators_tools_and_engine_without_em_dash()
        {
            foreach (string language in Languages)
            {
                string text = Credits.FullText(language);
                StringAssert.Contains("Etienne & Louis", text, language);
                StringAssert.Contains("Claude Code (Anthropic)", text, language);
                StringAssert.Contains("Unity", text, language);
                StringAssert.Contains("Universal Render Pipeline", text, language);
                Assert.IsFalse(text.Contains('\u2014') || text.Contains('\u2013'), language + ": an em or en dash on the Credits page");
            }
            Assert.AreNotEqual(Credits.FullText(Strings.English), Credits.FullText(Strings.French), "the French page is not translated");
            Assert.AreEqual("Credits", Strings.Get("credits.title", Strings.English));
            Assert.AreEqual("Crédits", Strings.Get("credits.title", Strings.French));
        }
    }
}
