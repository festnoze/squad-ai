import io
p = "Assets/Tests/PlayMode/ProbeTestsM4Game.cs"
s = io.open(p, encoding="utf-8").read()
def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:80])
    s = s.replace(a, b, 1)
rep("""            Assert.IsTrue(Furniture.Tipped, "premise: the stool is down");
            Vector3 lying = Furniture.transform.position;
            for (int k = 0; k < StepsFor(2f); k++)
            {
                yield return new WaitForFixedUpdate();
                Assert.IsTrue(Furniture.Tipped, $"the stool got up by itself after {k * Dt:0.00} s");
                Assert.IsFalse(Furniture.IsMoving, "a stool lying still counts as moving");
                Assert.IsFalse(Furniture.ActionActive, "an action runs on a stool lying still");
            }
            Assert.Less(Planar(Furniture.transform.position, lying), 1e-4f, "the lying stool moved");
""", """            Assert.IsTrue(Furniture.Tipped, "premise: the stool is down");
            Assert.IsFalse(FurnitureMemory.WithinTolerance(Furniture.Pose, Game.MemoryOf(Habitant).PlayerSlot),
                "premise: the stool lies away from where it belongs (its ghost would show)");
            Vector3 lying = Furniture.transform.position;
            for (int k = 0; k < StepsFor(2f); k++)
            {
                yield return new WaitForFixedUpdate();
                Assert.IsTrue(Furniture.Tipped, $"the stool got up by itself after {k * Dt:0.00} s");
                Assert.IsFalse(Furniture.IsMoving, "a stool lying still counts as moving");
                Assert.IsFalse(Furniture.ActionActive, "an action runs on a stool lying still");
                // M4.1 (CONTRACT_M4 10.3): the HUD says how to get up, and no ghost points at a place meanwhile.
                Assert.IsTrue(main.Hud.TippedVisible, "no tipped line on the HUD while the stool lies");
                Assert.IsFalse(Game.Ghost.Visible, "the remembered-pose ghost shows while the stool lies");
                Assert.IsFalse(Game.Ghost.RingsVisible, "the decoy rings show while the stool lies");
            }
            Assert.Less(Planar(Furniture.transform.position, lying), 1e-4f, "the lying stool moved");
            Assert.IsTrue(main.Hud.Labels.TryGetValue("TippedLine", out UnityEngine.UI.Text line) && line.text == Strings.HudTipped,
                "the tipped line does not carry hud.tipped");
""")
rep("""            Assert.Less(Planar(Furniture.transform.position, lying), 1e-3f, "the righting moved the stool");
            yield return Steps(2);
            Assert.IsFalse(Furniture.IsMoving, "the righted stool keeps moving");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertNoErrors();
        }""", """            Assert.Less(Planar(Furniture.transform.position, lying), 1e-3f, "the righting moved the stool");
            yield return Steps(2);
            Assert.IsFalse(Furniture.IsMoving, "the righted stool keeps moving");
            Assert.IsFalse(main.Hud.TippedVisible, "the tipped line outlived the righting");
            Assert.IsTrue(Game.Ghost.Visible, "upright and out of place, the ghost does not come back");
            Assert.AreEqual(PlayState.Playing, Game.State);
            AssertNoErrors();
        }""")
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("ok")
