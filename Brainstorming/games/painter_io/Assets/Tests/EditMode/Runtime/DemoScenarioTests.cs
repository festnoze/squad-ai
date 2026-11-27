// Owned by BI since wave B-2 (written by B0a). Proves the v1.4 DemoScenario (contract 23.3, 18.2 step 2, 24.1) headless
// inside Unity: a clean capture without a spark first, then a cut near the loop origin and a saved chased return that
// captures nothing (territory unchanged), then a LassoPocket over the rival's puddle next to the human's puddle, and the
// human is eliminated by the spark; every checkpoint shows what its name promises. The same round driven as a GameSession
// at two display cadences gives the same StateHash as the headless run.
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;

namespace PainterIO.Tests
{
    public class DemoScenarioTests
    {
        [Test]
        public void Demo_HeadlessRunHasTheExpectedEventsAndCheckpoints()
        {
            Simulation sim = DemoScenario.CreateSimulation(out DemoScenario.Monitor monitor);
            while (sim.Tick < DemoScenario.EndTick && !sim.Ended) sim.Step();
            monitor.Finish();
            bool pass = monitor.Evaluate(out List<string> failures);
            Assert.IsTrue(pass, string.Join("\n", failures) + "\n" + monitor.Report());

            // The named facts, spelled out.
            Assert.That(monitor.FirstReturnCells, Is.GreaterThan(500), "phase 1: the clean capture fills a loop");
            Assert.IsFalse(monitor.FirstReturnChased, "phase 1: no spark at the clean capture");
            Assert.That(monitor.FirstCutTick, Is.GreaterThan(monitor.FirstReturnTick), "phase 2: the cut comes after the clean capture");
            Assert.That(monitor.SavedReturnTick, Is.GreaterThan(monitor.FirstCutTick), "phase 2: saved chased return");
            Assert.IsTrue(monitor.SavedReturnChased);
            Assert.AreEqual(0, monitor.SavedReturnCells, "contract 24: a chased return captures nothing");
            Assert.That(monitor.SavedReturnMargin, Is.GreaterThan(0.1), "a readable margin (the toast shows it)");
            Assert.AreEqual(monitor.CellsBeforeSavedReturn, monitor.CellsAfterSavedReturn, "territory unchanged by the saved return");
            Assert.That(monitor.PocketTick, Is.GreaterThan(monitor.SavedReturnTick), "phase 3: LassoPocket after the saved return");
            Assert.That(monitor.PocketCellsOverRival, Is.GreaterThan(0), "pocket over the rival puddle");
            Assert.That(monitor.PocketDistanceToHome, Is.LessThanOrEqualTo(1.5), "pocket next to the human's puddle");
            Assert.AreEqual(EliminationCause.Spark, monitor.HumanCause, "the human is eliminated by the spark");
            Assert.AreEqual(0, sim.EventCapHits);
        }

        [Test]
        public void Demo_CheckpointsAreOrderedAndInsideTheRun()
        {
            long previous = 0;
            for (int k = 0; k < DemoScenario.CheckpointTicks.Length; k++)
            {
                Assert.That(DemoScenario.CheckpointTicks[k], Is.GreaterThan(previous), DemoScenario.CheckpointNames[k]);
                previous = DemoScenario.CheckpointTicks[k];
            }
            Assert.That(DemoScenario.EndTick, Is.GreaterThan(DemoScenario.Caught));
            Assert.That(DemoScenario.ChargeTick, Is.GreaterThan(DemoScenario.SavedReturn));
            Assert.That(DemoScenario.ChargeTick, Is.LessThan(DemoScenario.PocketPending));
            Assert.AreEqual(DemoScenario.CheckpointNames.Length, DemoScenario.CheckpointTicks.Length);
            // Every named checkpoint, in the v1.4 story order.
            string[] order = { "ThreadOut", "MidFill", "CutDroplets", "SavedReturn", "PocketPending", "Caught" };
            CollectionAssert.AreEqual(order, DemoScenario.CheckpointNames);
            long[] ticks = { DemoScenario.ThreadOut, DemoScenario.MidFill, DemoScenario.CutDroplets, DemoScenario.SavedReturn,
                             DemoScenario.PocketPending, DemoScenario.Caught };
            CollectionAssert.AreEqual(ticks, DemoScenario.CheckpointTicks);
            for (int k = 0; k < order.Length; k++) Assert.AreEqual(k, DemoScenario.CheckpointIndex(order[k]));
            Assert.AreEqual(-1, DemoScenario.CheckpointIndex("Nope"));
        }

        [Test]
        public void Demo_AsAGameSessionMatchesTheHeadlessRunAtTwoDisplayCadences()
        {
            Simulation reference = DemoScenario.CreateSimulation(out _);
            while (reference.Tick < DemoScenario.EndTick && !reference.Ended) reference.Step();
            ulong expected = reference.StateHash();

            foreach (float delta in new[] { 1f / 30f, 1f / 144f })
            {
                GameSession session = DemoScenario.CreateSession(out DemoScenario.Monitor monitor);
                Assert.IsFalse(session.IsAttract);
                Assert.IsFalse(session.AwaitingStart, "scripted sessions start at once");
                Assert.IsFalse(session.CountsForStats, "the demo never records stats");
                Assert.AreEqual(DemoScenario.Human, session.HumanIndex);
                int frames = 0;
                while (session.Sim.Tick < DemoScenario.EndTick && !session.Sim.Ended)
                {
                    session.Runner.Advance(delta);
                    Assert.Less(++frames, 200000, "runaway");
                }
                // 1/30 s frames step two ticks at a time: bring the reference to the same tick if it overshot.
                Simulation same = reference;
                if (session.Sim.Tick != reference.Tick)
                {
                    same = DemoScenario.CreateSimulation(out _);
                    while (same.Tick < session.Sim.Tick && !same.Ended) same.Step();
                }
                Assert.AreEqual(same.StateHash(), session.Sim.StateHash(), "display " + delta);
                if (session.Sim.Tick == reference.Tick) Assert.AreEqual(expected, session.Sim.StateHash());
                monitor.Finish();
                Assert.IsTrue(monitor.Evaluate(out List<string> failures), "display " + delta + ": " + string.Join("; ", failures));
            }
        }

        [Test]
        public void Demo_CheckpointStatesMatchTheV14Story()
        {
            Simulation sim = DemoScenario.CreateSimulation(out DemoScenario.Monitor monitor);
            while (sim.Tick < DemoScenario.EndTick && !sim.Ended) sim.Step();
            monitor.Finish();
            DemoScenario.CheckpointState thread = monitor.Checkpoint("ThreadOut");
            Assert.IsTrue(thread.Recorded && thread.Alive && !thread.Home && !thread.HasSpark, "ThreadOut: an uncut thread");
            DemoScenario.CheckpointState fill = monitor.Checkpoint("MidFill");
            Assert.IsTrue(fill.Recorded && fill.Home && !fill.HasSpark, "MidFill: home after the clean capture");
            DemoScenario.CheckpointState cut = monitor.Checkpoint("CutDroplets");
            Assert.IsTrue(cut.Recorded && cut.HasSpark && !cut.Home, "CutDroplets: chased");
            DemoScenario.CheckpointState saved = monitor.Checkpoint("SavedReturn");
            Assert.IsTrue(saved.Recorded && saved.Alive && saved.Home && !saved.HasSpark, "SavedReturn: home, alive, no spark");
            Assert.That(DemoScenario.SavedReturn - monitor.SavedReturnTick, Is.InRange(2L, 12L), "the dissolve of 0.4 s is under way");
            DemoScenario.CheckpointState pocket = monitor.Checkpoint("PocketPending");
            Assert.That(pocket.PocketCells, Is.GreaterThan(0), "PocketPending: a pending pocket");
            DemoScenario.CheckpointState caught = monitor.Checkpoint("Caught");
            Assert.IsTrue(caught.Recorded && !caught.Alive, "Caught: the human is out");
            Assert.IsFalse(monitor.Checkpoint("Unknown").Recorded);
        }

        [Test]
        public void Demo_SessionCanForceABiome()
        {
            GameSession plain = DemoScenario.CreateSession(out _);
            Assert.IsNull(plain.Biome, "a plain demo session follows -biome / SaveData.Biome");
            GameSession fire = DemoScenario.CreateSession(out DemoScenario.Monitor monitor, BiomeId.Fire);
            Assert.AreEqual(BiomeId.Fire, fire.Biome);
            Assert.IsNotNull(monitor);
            Assert.AreEqual(DemoScenario.Human, fire.HumanIndex);
            plain.Close();
            fire.Close();
        }
    }
}