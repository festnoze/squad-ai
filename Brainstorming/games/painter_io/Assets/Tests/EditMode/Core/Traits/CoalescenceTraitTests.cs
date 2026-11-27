// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 2: Coalescence (behaviour trait), P1 = MaxHoleArea
// (2.0 u^2): after an UNCHASED return, every neutral hole enclosed by the territory after the capture and smaller than
// MaxHoleArea is filled and joins the Return's Cells. Cross-rate equality required (section 6).
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class CoalescenceTraitTests
    {
        /// <summary>The neutral holes cut into player 0's land [-12, 0] x [-4, 4].</summary>
        internal sealed class Holes
        {
            public int[] Small;      // [-6, -5] x [0, 1]: 64 cells = 1 u^2, filled
            public int[] Big;        // [-10, -8] x [-3, -1]: 256 cells = 4 u^2, kept
            public int[] Exact;      // [-4, -3] x [-3, -1]: 128 cells = exactly 2 u^2, kept (strictly smaller only)
            public int[] Almost;     // [-4, -3] x [1, 3] minus its corner cell: 127 cells, filled
            public int[] Rival;      // [-8, -7] x [2, 3] with one cell of player 1 inside: not enclosed, kept
            public int RivalCell, AlmostCorner;
        }

        /// <summary>
        /// Player 0 owns [-12, 0] x [-4, 4] minus the holes and loops East 4, North 2, West from (-1 + H, H): exit at x = 0
        /// at t = 0.15625, unchased return at x = 0 at t = 1 + 3.0625 / 6. Player 1 idles at (23, 0) on [20, 26] x [-3, 3]
        /// and owns one cell of the Rival hole. With islandPlayer, player 2 owns the Small hole at the start and is
        /// eliminated at t = 0 (forced catch on a far trail), so the Small hole is freed (and scorched with ScorchedEarth).
        /// </summary>
        internal static Simulation Scene(int rate, RuleTraits traits, out Holes holes, bool islandPlayer = false)
        {
            var h = new Holes();
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.Add(V(-1 + H, H), East, Legs((East, 4), (North, 2), (West, 20)), (g, id) =>
            {
                FillRect(g, id, -12, -4, 0, 4);
                h.Small = TraitTestKit.RectCells(g, -6, 0, -5, 1);
                h.Big = TraitTestKit.RectCells(g, -10, -3, -8, -1);
                h.Exact = TraitTestKit.RectCells(g, -4, -3, -3, -1);
                int[] almostRect = TraitTestKit.RectCells(g, -4, 1, -3, 3);
                h.Rival = TraitTestKit.RectCells(g, -8, 2, -7, 3);
                foreach (int[] hole in new[] { h.Small, h.Big, h.Exact, almostRect, h.Rival }) TraitTestKit.SetCells(g, hole, OwnerGrid.Neutral);
                h.AlmostCorner = almostRect[0];
                g.Set(h.AlmostCorner, id);
                h.Almost = new int[almostRect.Length - 1];
                System.Array.Copy(almostRect, 1, h.Almost, 0, h.Almost.Length);
                h.RivalCell = CellIndex(g, -7.4375, 2.4375);
            });
            sb.Add(V(23, 0), East, new HomeCirclerController(V(23, 0)), (g, id) =>
            {
                FillRect(g, id, 20, -3, 26, 3);
                g.Set(CellIndex(g, -7.4375, 2.4375), id);
            });
            if (islandPlayer)
            {
                sb.Add(V(-5.4375, 0.4375), East, new ConstantHeadingController(East), (g, id) => FillRect(g, id, -6, 0, -5, 1));
            }
            Simulation sim = sb.Build();
            if (islandPlayer)
            {
                sim.BeforeTick += s =>
                {
                    if (s.Tick != 0) return;
                    s.DebugSetTrail(2, new[] { V(20 + H, 20 + H), V(22 + H, 20 + H) });
                    s.DebugForceCut(2, 3.0, 1);
                };
            }
            holes = h;
            return sim;
        }

        private const double ReturnTime = 1.0 + 3.0625 / 6.0;

        [Test]
        public void Coalescence_FillsSmallEnclosedNeutralHolesOnAnUnchasedReturnAtEveryRate()
        {
            TraitTestKit.CrossRate("Coalescence", rate => Scene(rate, TraitTestKit.One(TraitId.Coalescence), out Holes _), 1.8, run =>
            {
                Simulation sim = run.Sim;
                Scene(run.Rate, RuleTraits.Classic, out Holes h);   // the hole cells (same grid layout)
                SimEvent ret = run.Log.Single(SimEventType.Return, 0);
                Assert.IsFalse(ret.Chased);
                Assert.That(ret.Time, Is.EqualTo(ReturnTime).Within(1e-6));
                Assert.AreEqual(64, h.Small.Length);
                Assert.AreEqual(127, h.Almost.Length);
                Assert.AreEqual(64, TraitTestKit.CountIn(ret.Cells, h.Small), "the 1 u^2 hole joins the Return's Cells");
                Assert.AreEqual(127, TraitTestKit.CountIn(ret.Cells, h.Almost), "127 cells < 128 = 2 u^2: filled");
                Assert.AreEqual(0, TraitTestKit.CountIn(ret.Cells, h.Big), "4 u^2: too big");
                Assert.AreEqual(0, TraitTestKit.CountIn(ret.Cells, h.Exact), "exactly 2 u^2: not strictly smaller");
                Assert.AreEqual(0, TraitTestKit.CountIn(ret.Cells, h.Rival), "a hole touching a rival cell is not enclosed");
                Assert.AreEqual(64, TraitTestKit.CountOwned(sim.Grid, h.Small, 1));
                Assert.AreEqual(0, TraitTestKit.CountOwned(sim.Grid, h.Big, 1));
                Assert.AreEqual(2, sim.Grid.Cells[h.RivalCell]);
                Assert.AreEqual(1, sim.Players[0].Captures);
            });
        }

        [Test]
        public void Coalescence_AddsExactlyTheHolesToTheClassicCapture()
        {
            Simulation with = Scene(60, TraitTestKit.One(TraitId.Coalescence), out Holes h);
            Simulation without = Scene(60, RuleTraits.Classic, out Holes _);
            var logWith = new EventLog(with);
            var logWithout = new EventLog(without);
            RunUntilTime(with, 1.8);
            RunUntilTime(without, 1.8);
            int[] a = logWith.Single(SimEventType.Return, 0).Cells;
            int[] b = logWithout.Single(SimEventType.Return, 0).Cells;
            Assert.That(b.Length, Is.GreaterThan(300), "the loop itself captures (about 6 u^2)");
            Assert.AreEqual(b.Length + 64 + 127, a.Length, "classic capture + the two small holes");
            Assert.IsTrue(IsSubset(b, a));
            Assert.AreEqual(0, TraitTestKit.CountIn(b, h.Small), "classic: the hole stays (C4)");
            Assert.AreEqual(0, TraitTestKit.CountOwned(without.Grid, h.Small, 1));
        }

        [Test]
        public void Coalescence_AChasedReturnFillsNothing()
        {
            Simulation sim = Scene(60, TraitTestKit.One(TraitId.Coalescence), out Holes h);
            var log = new EventLog(sim);
            // At t = 4/3 the trail is 7.0625 long: a cut 2 u behind the head is caught at t + 2 / 4.8 = 1.75 s, after the
            // return at 1.51 s: saved, captures nothing (contract 24), and no hole is filled either.
            sim.BeforeTick += s =>
            {
                if (s.Tick == 80) s.DebugForceCut(0, s.Players[0].Trail.Length - 2.0, 1);
            };
            RunUntilTime(sim, 1.8);
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.IsTrue(ret.Chased);
            Assert.AreEqual(0, ret.Cells.Length);
            Assert.AreEqual(0, TraitTestKit.CountOwned(sim.Grid, h.Small, 1), "the hole stays neutral");
            Assert.IsTrue(sim.Players[0].Alive);
        }

        [Test]
        public void Coalescence_MaxHoleAreaParameter()
        {
            Simulation sim = Scene(60, TraitTestKit.One(TraitId.Coalescence, 5.0), out Holes h);
            var log = new EventLog(sim);
            RunUntilTime(sim, 1.8);
            int[] cells = log.Single(SimEventType.Return, 0).Cells;
            Assert.AreEqual(256, TraitTestKit.CountIn(cells, h.Big), "4 u^2 < 5 u^2: filled");
            Assert.AreEqual(128, TraitTestKit.CountIn(cells, h.Exact));
            Assert.AreEqual(0, TraitTestKit.CountIn(cells, h.Rival), "still not enclosed");

            Simulation none = Scene(60, TraitTestKit.One(TraitId.Coalescence, 0.0), out Holes _);
            var noneLog = new EventLog(none);
            RunUntilTime(none, 1.8);
            Assert.AreEqual(0, TraitTestKit.CountIn(noneLog.Single(SimEventType.Return, 0).Cells, h.Small), "MaxHoleArea 0 fills nothing");
        }

        [Test]
        public void Coalescence_NeverFillsScorchedCells()
        {
            // The Small hole is the land of player 2, eliminated at t = 0: freed, neutral and (with ScorchedEarth) scorched.
            Simulation scorched = Scene(60, RuleTraits.Parse("Coalescence;ScorchedEarth"), out Holes h, true);
            Simulation plain = Scene(60, TraitTestKit.One(TraitId.Coalescence), out Holes _, true);
            var logScorched = new EventLog(scorched);
            var logPlain = new EventLog(plain);
            RunUntilTime(scorched, 1.8);
            RunUntilTime(plain, 1.8);
            Assert.IsFalse(scorched.Players[2].Alive);
            int[] a = logScorched.Single(SimEventType.Return, 0).Cells;
            int[] b = logPlain.Single(SimEventType.Return, 0).Cells;
            Assert.AreEqual(0, TraitTestKit.CountIn(a, h.Small), "scorched cells are never filled");
            Assert.AreEqual(127, TraitTestKit.CountIn(a, h.Almost), "other holes still are");
            Assert.AreEqual(64, TraitTestKit.CountIn(b, h.Small), "without ScorchedEarth the freed island is filled");
            foreach (int c in h.Small) Assert.IsTrue(scorched.View.IsScorched(c));
        }
    }
}
