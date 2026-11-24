using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight.Tests
{
    /// <summary>
    /// DRESSING (2026-11-24, docs/next/progress/DRESSING.md): the room dressing data and its baked library.
    /// <list type="bullet">
    /// <item>Dressing_Levels: every played level and the title house validate with their decor and looks, each carries 2 to
    /// DecorKinds.MaxPerLevel (10) items on hosts and at most DecorKinds.MaxFloorPerLevel on the floor, never in a bathroom,
    /// and only the planned props wear a look.</item>
    /// <item>Dressing_Validator: every new rule has a failing case (unknown kind, unknown host, wrong host kind, off the top,
    /// two items overlapping, a bathroom, a look on the wrong kind, a look with a model, too tall a console).</item>
    /// <item>Dressing_Library: every decor kind, look and the TV is baked, readable, drawn by the wall material's channels, its
    /// bounds those of DecorKinds; the arrays hold the dressing slices.</item>
    /// </list>
    /// Run: --filter Dressing_.
    /// </summary>
    public sealed class DressingTests
    {
        private const string Folder = "Assets/Resources/Levels/";

        private static LevelDef Load(string id) => LevelJson.Parse(File.ReadAllText(Folder + id + ".json"));

        private static IEnumerable<string> Dressed()
        {
            JObject manifest = JObject.Parse(File.ReadAllText(Folder + "levels.json"));
            return manifest["levels"].Select(t => (string)t).Concat(new[] { "title_house" });
        }

        private static List<string> DressingIssues(LevelDef level)
        {
            return LevelValidator.Validate(level).Where(i => i.Contains("decor") || i.Contains("dress") || i.Contains("look")).ToList();
        }

        [Test]
        public void Dressing_Levels_ValidateWithTwoToFiveItems()
        {
            var looks = new Dictionary<string, string>();
            foreach (string id in Dressed())
            {
                LevelDef level = Load(id);
                CollectionAssert.IsEmpty(DressingIssues(level), id);
                // ROOMS: the items on hosts and the floor items have their own caps.
                int onFloor = level.Decor.Count(d => DecorKinds.IsFloor(d.Host));
                Assert.That(level.Decor.Count - onFloor, Is.InRange(2, DecorKinds.MaxPerLevel), $"{id}: decor items on hosts");
                Assert.That(onFloor, Is.LessThanOrEqualTo(DecorKinds.MaxFloorPerLevel), $"{id}: decor items on the floor");
                foreach (PropDef p in level.Props.Where(p => p.Dress != null))
                {
                    looks[id + "/" + p.Name] = p.Dress;
                }
                // A round trip keeps the decor and the looks.
                LevelDef again = LevelJson.Parse(LevelJson.Serialize(level));
                Assert.AreEqual(level.Decor.Count, again.Decor.Count, id + ": decor round trip");
                Assert.AreEqual(level.Props.Count(p => p.Dress != null), again.Props.Count(p => p.Dress != null), id + ": looks round trip");
            }
            var expected = new Dictionary<string, string>
            {
                { "level5/CoffeeTable", DecorKinds.WalnutCoffeeTable }, { "level5/TV", DecorKinds.WalnutMediaConsole },
                { "level6/CoffeeTable", DecorKinds.WalnutCoffeeTable }, { "level8/MeubleTV", DecorKinds.WalnutMediaConsole },
                { "level9/TableBasse", DecorKinds.WalnutCoffeeTable }, { "level9/Television", DecorKinds.WalnutMediaConsole },
                { "level12/Television", DecorKinds.WalnutMediaConsole }, { "level11/TableBasse", DecorKinds.WalnutCoffeeTable },
                { "level19/TableBasse", DecorKinds.WalnutCoffeeTable }, { "level19/MeubleTV", DecorKinds.WalnutMediaConsole },
                // COHERENCE: the TV stands and coffee tables added facing the sofas.
                { "level6/MeubleTV", DecorKinds.WalnutMediaConsole }, { "level12/TableBasse", DecorKinds.WalnutCoffeeTable },
                { "level15/TableBasse", DecorKinds.WalnutCoffeeTable }, { "level15/MeubleTV", DecorKinds.WalnutMediaConsole },
                { "title_house/TableBasse", DecorKinds.WalnutCoffeeTable }, { "title_house/MeubleTV", DecorKinds.WalnutMediaConsole },
                // ROOMS: the kitchen modules on the kitchens' counters, sinks and stoves, the bedside table on the nightstands.
                { "level3/Counter", DecorKinds.KitchenSinkCabinet }, { "level8/Plan", DecorKinds.KitchenBaseCabinet },
                { "level12/Plan", DecorKinds.KitchenBaseCabinet }, { "level11/Plan", DecorKinds.KitchenBaseCabinet },
                { "level15/Plan", DecorKinds.KitchenSinkCabinet }, { "level13/Comptoir", DecorKinds.KitchenSinkCabinet },
                { "level14/Plan", DecorKinds.KitchenSinkCabinet }, { "level18/Plan", DecorKinds.KitchenBaseCabinet },
                { "level17/Plan", DecorKinds.KitchenSinkCabinet }, { "level19/Plan", DecorKinds.KitchenBaseCabinet },
                { "level19/Evier", DecorKinds.KitchenSinkCabinet }, { "level19/Cuisiniere", DecorKinds.KitchenRange },
                { "level22/Evier", DecorKinds.KitchenSinkCabinet }, { "level22/Cuisiniere", DecorKinds.KitchenRange },
                { "level22/Comptoir", DecorKinds.KitchenBaseCabinet }, { "level24/Evier", DecorKinds.KitchenSinkCabinet },
                { "level24/Cuisiniere", DecorKinds.KitchenRange }, { "level24/Plan", DecorKinds.KitchenBaseCabinet },
                { "title_house/Plan", DecorKinds.KitchenSinkCabinet },
                { "level2/Nightstand", DecorKinds.BedsideTable }, { "level9/TableDeChevet", DecorKinds.BedsideTable },
                { "level19/Chevet", DecorKinds.BedsideTable }, { "level22/ChevetChambre", DecorKinds.BedsideTable },
                { "level22/ChevetBoudoir", DecorKinds.BedsideTable },
            };
            CollectionAssert.AreEquivalent(expected, looks, "the props wearing a look");
            // A level without any decor still writes no "decor" key (an untouched fixture stays byte identical).
            Assert.IsFalse(LevelJson.Serialize(Load("test_rooms")).Contains("\"decor\""), "an empty decor list is written");
        }

        [Test]
        public void Dressing_Validator_RejectsEveryBadItem()
        {
            LevelDef Fresh()
            {
                LevelDef l = Load("level1");
                l.Decor = new List<DecorDef>();
                return l;
            }

            void Expect(LevelDef l, string fragment, string why)
            {
                List<string> issues = DressingIssues(l);
                Assert.IsTrue(issues.Any(i => i.Contains(fragment)), $"{why}: expected an issue with '{fragment}', got [{string.Join("; ", issues)}]");
            }

            LevelDef ok = Fresh();
            ok.Decor.Add(new DecorDef { Kind = DecorKinds.OpenBook, Host = "Table", X = 0f, Z = 0f, Yaw = 0f });
            ok.Decor.Add(new DecorDef { Kind = DecorKinds.SofaThrow, Host = "Sofa", X = 0.3f, Z = 0f, Yaw = 0f });
            CollectionAssert.IsEmpty(DressingIssues(ok), "a valid book and throw");

            LevelDef l = Fresh();
            l.Decor.Add(new DecorDef { Kind = "vase", Host = "Table" });
            Expect(l, "not a decor kind", "unknown kind");

            l = Fresh();
            l.Decor.Add(new DecorDef { Kind = DecorKinds.OpenBook, Host = "Nowhere" });
            Expect(l, "no prop of that name", "unknown host");

            l = Fresh();
            l.Decor.Add(new DecorDef { Kind = DecorKinds.SofaThrow, Host = "Table" });
            Expect(l, "cannot hold it", "a throw on a table");

            l = Fresh();
            l.Decor.Add(new DecorDef { Kind = DecorKinds.OpenBook, Host = "Table", X = 0.65f });
            Expect(l, "not within its host's top", "a book hanging off the table");

            l = Fresh();
            l.Decor.Add(new DecorDef { Kind = DecorKinds.SofaThrow, Host = "Sofa", Z = 0.3f });
            Expect(l, "not within its host's top", "a throw off the backrest");

            l = Fresh();
            l.Decor.Add(new DecorDef { Kind = DecorKinds.OpenBook, Host = "Table" });
            l.Decor.Add(new DecorDef { Kind = DecorKinds.CeramicMug, Host = "Table", X = 0.05f });
            Expect(l, "overlaps decor 1", "a mug in the book");

            l = Fresh();
            for (int i = 0; i <= DecorKinds.MaxPerLevel; i++)
            {
                l.Decor.Add(new DecorDef { Kind = DecorKinds.TvRemote, Host = "Table", X = -0.6f + 0.1f * i, Z = 0.3f });
            }
            Expect(l, "decor items, more than", "too many items");

            // A bathroom: level14's bathroom "salle" holds a washbasin; any host there is refused.
            LevelDef bath = Load("level14");
            RoomDef bathroom = bath.AllRooms().First(r => RoomTypes.Of(r) == RoomTypes.Bathroom);
            PropDef inBath = bath.Props.FirstOrDefault(p => bathroom.Contains(p.Position) && DecorKinds.HostKinds(DecorKinds.Pothos).Contains(p.Kind));
            if (inBath == null)
            {
                inBath = new PropDef { Name = "BathShelf", Kind = PropKinds.Cabinet, X = bathroom.X, Z = bathroom.Z, SizeX = 0.6f, SizeY = 0.9f, SizeZ = 0.4f };
                bath.Props.Add(inBath);
            }
            bath.Decor = new List<DecorDef> { new DecorDef { Kind = DecorKinds.Pothos, Host = inBath.Name } };
            Expect(bath, "bathroom", "decor in a bathroom");

            l = Fresh();
            l.Props.Find(p => p.Name == "Table").Dress = DecorKinds.WalnutCoffeeTable;
            Expect(l, "cannot wear the look", "a coffee table look on a dining table");

            l = Fresh();
            l.Props.Find(p => p.Name == "Sofa").Dress = "chesterfield";
            Expect(l, "is not a furniture look", "unknown look");

            l = Fresh();
            PropDef cabinet = new PropDef { Name = "Tall", Kind = PropKinds.Cabinet, X = 3f, Z = 2f, SizeX = 1f, SizeY = 1.2f, SizeZ = 0.4f, Dress = DecorKinds.WalnutMediaConsole };
            l.Props.Add(cabinet);
            Expect(l, "too tall for the look", "a tall cabinet as a media console");

            l = Fresh();
            PropDef table = new PropDef { Name = "Low", Kind = PropKinds.CoffeeTable, X = 3f, Z = 2f, SizeX = 1f, SizeY = 0.42f, SizeZ = 0.55f, Dress = DecorKinds.WalnutCoffeeTable, Model = "kenney.coffee_table" };
            l.Props.Add(table);
            Expect(l, "both a model and a dress", "a look and a model");

            // COHERENCE: a TV stand (a low counter wearing the media console look) carries its TV on its top; nothing stands in
            // it, the key dish never goes on it, and a remote needs a TV in its room.
            l = Fresh();
            PropDef stand = new PropDef { Name = "Stand", Kind = PropKinds.Counter, X = -0.75f, Z = -2.6f, SizeX = 1.2f, SizeY = 0.55f, SizeZ = 0.4f, Dress = DecorKinds.WalnutMediaConsole };
            l.Props.Add(stand);
            l.Decor.Add(new DecorDef { Kind = DecorKinds.TvRemote, Host = "Stand", X = 0f, Z = 0.05f });
            Expect(l, "stands in the TV", "a remote inside the TV");
            l.Decor[0].Z = -0.155f;
            l.Decor[0].Yaw = 90f;
            Assert.IsFalse(DressingIssues(l).Any(i => i.Contains("stands in the TV") || i.Contains("room with a TV")), "a remote in front of the TV");
            l.Decor.Add(new DecorDef { Kind = DecorKinds.KeyDish, Host = "Stand", X = 0.4f, Z = -0.13f });
            Expect(l, "never goes on a TV stand", "the key dish on the TV stand");

            l = Fresh();
            l.Decor.Add(new DecorDef { Kind = DecorKinds.TvRemote, Host = "Table" });
            Expect(l, "room with a TV", "a remote without a TV");

            l = Fresh();
            l.Props.Find(p => p.Name == "Bookshelf").X = -3.6f;
            l.Props.Find(p => p.Name == "Bookshelf").Z = -2.6f;
            l.Decor.Add(new DecorDef { Kind = DecorKinds.KeyDish, Host = "Bookshelf" });
            Expect(l, "by the front door", "the key dish far from the exit");
        }

        [Test]
        public void Dressing_TopTv_SitsAgainstTheBackOfTheConsole()
        {
            // TVBIG: a 2.4 m console carries the TV at twice its native width and height, its foot fitted to the top's depth.
            var size = new Vector3(2.4f, 0.7f, 0.4f);
            Rect tv = DecorKinds.TopTvFootprint(size);
            Assert.AreEqual(2f, DecorKinds.TopTvScale(size), 1e-4f, "a 2.4 m console carries the TV at twice its native size");
            Assert.That(DecorKinds.TopTvDepthScale(size), Is.LessThanOrEqualTo(DecorKinds.TopTvScale(size)), "the foot never deeper than the scale");
            Assert.That(tv.yMax, Is.LessThanOrEqualTo(size.z * 0.5f), "within the top, at the back");
            Assert.That(tv.yMin, Is.GreaterThan(-size.z * 0.5f + 0.1f), "a front strip is left for small items");
            Assert.That(tv.xMax - tv.xMin, Is.LessThanOrEqualTo(size.x * 0.9f + 1e-4f), "within 90 % of the width");
            Assert.IsTrue(DecorKinds.CarriesTopTv(PropKinds.Counter, DecorKinds.WalnutMediaConsole));
            Assert.IsFalse(DecorKinds.CarriesTopTv(PropKinds.TvUnit, DecorKinds.WalnutMediaConsole), "a TV unit draws its TV in its box");
        }

        [Test]
        public void Dressing_Library_BakedForEveryKind()
        {
            var library = Resources.Load<DressingLibrary>(DressingLibrary.ResourcePath);
            Assert.IsNotNull(library, "no Resources/DressingLibrary: run SetupAndCompile (DressingBuilder)");
            foreach (string id in DecorKinds.Meshes)
            {
                DressingLibrary.Entry e = library.Find(id);
                Assert.IsNotNull(e, id + " is not baked");
                Assert.IsTrue(e.mesh.isReadable, id + ": the combiner reads the mesh at run time");
                Assert.IsTrue(e.mesh.HasVertexAttribute(VertexAttribute.TexCoord1) && e.mesh.HasVertexAttribute(VertexAttribute.TexCoord2),
                    id + ": no finish or colour channel");
                Assert.Greater(e.triangles, 0, id);
                var finish = new List<Vector4>();
                e.mesh.GetUVs(WallArray.FinishChannel, finish);
                foreach (Vector4 f in finish)
                {
                    int slice = Mathf.RoundToInt(f.x) - 1;
                    Assert.IsTrue(f.x == WallArray.FlatFinish || (slice >= WallArray.Slices.Length && slice < WallArray.Depth),
                        $"{id}: a vertex names finish {f.x}, neither flat nor a dressing slice");
                    Assert.AreEqual(Surface.Plain, WallArray.SurfaceOf(f), id + ": a dressing vertex reads as a room surface");
                }
                if (DecorKinds.TryFootprint(id, out Rect foot, out float height))
                {
                    Assert.That(e.boundsMin.x, Is.EqualTo(foot.xMin).Within(0.004f), id + " x min");
                    Assert.That(e.boundsMax.x, Is.EqualTo(foot.xMax).Within(0.004f), id + " x max");
                    Assert.That(e.boundsMin.z, Is.EqualTo(foot.yMin).Within(0.004f), id + " z min");
                    Assert.That(e.boundsMax.z, Is.EqualTo(foot.yMax).Within(0.004f), id + " z max");
                    Assert.That(e.boundsMax.y, Is.EqualTo(height).Within(0.004f), id + " height");
                }
            }
            var textures = Resources.Load<TextureLibrary>("TextureLibrary");
            Assert.IsNotNull(textures, "premise: no TextureLibrary");
            Assert.AreEqual(WallArray.Depth, textures.wallColours.depth, "the colour array holds the dressing slices");
            Assert.AreEqual(WallArray.Depth, textures.wallNormals.depth, "the normal array holds the dressing slices");
        }
    }
}
