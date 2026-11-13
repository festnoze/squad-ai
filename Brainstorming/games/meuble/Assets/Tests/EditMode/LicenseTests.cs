using System.IO;
using System.Linq;
using NUnit.Framework;

namespace Meuble.Tests
{
    /// <summary>
    /// PRD 11 M3 gate: a licence file lists every imported model and sound. Every file under
    /// Assets/ThirdParty must be named in docs/LICENSES.md, with its licence.
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
                StringAssert.Contains("CC0", row, "an asset is not CC0: " + row);
            }
        }
    }
}
