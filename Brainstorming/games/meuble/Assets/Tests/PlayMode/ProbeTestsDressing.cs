using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// DRESSING (2026-11-24, docs/next/progress/DRESSING.md), on the real Boot scene and every played level plus the title house:
    /// <list type="bullet">
    /// <item>Dressing_a: every decor item and look is built (none skipped, none in a lamp); each item stands on its host's top
    /// (its bottom at the top height, a throw's crest on the backrest top) and within its host's footprint; the decor is drawn
    /// by the wall material, merged into the floor renderer; no dressing renderer carries a collider.</item>
    /// <item>Dressing_b: zero gameplay effect: the level's colliders (name, layer, enabled, bounds) are exactly those of the same
    /// level built with the dressing off (DressingLibrary.Disabled), and the budgets hold: no more materials than undressed,
    /// at most one more draw call (the looks' renderer), within the PRD 7.4 caps.</item>
    /// </list>
    /// Run: --filter Dressing_.
    /// </summary>
    public sealed class ProbeTestsDressing
    {
        private Main main;
        private GameState Game => main.Game;

        private static IEnumerable<string> Levels()
        {
            string json = File.ReadAllText(Path.Combine(Application.dataPath, "Resources", "Levels", "levels.json"));
            return LevelManifest.Parse(json).Concat(new[] { "title_house" });
        }

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            DressingLibrary.Disabled = false;
            RoomLights.Disabled = false;
            Time.timeScale = 1f;
            SaveStore.ResetForTests();
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            DressingLibrary.Disabled = false;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
            }
            SaveStore.ResetForTests();
            yield return null;
        }

        private IEnumerator Build(string id)
        {
            Game.Paused = false;
            if (Game.LevelId != id || Game.Def == null)
            {
                Game.LoadLevel(id);
            }
            Game.Restart();
            Game.Paused = true;
            yield return new WaitForFixedUpdate();
            yield return null;
        }

        [UnityTest, Timeout(600000)]
        public IEnumerator Dressing_a_EveryItemOnItsHostTop()
        {
            Material wall = WallArray.Material;
            Assert.IsNotNull(wall, "premise: no wall material (textures off?)");
            foreach (string id in Levels())
            {
                yield return Build(id);
                LevelInstance level = Game.Level;
                LevelDef def = Game.Def;
                CollectionAssert.IsEmpty(level.DressingProblems, id + ": dressing problems");
                Assert.AreEqual(def.Decor.Count, level.Dressing.Count(p => !p.Look), id + ": decor items built");
                int looks = def.Props.Count(p => p.Dress != null);
                Assert.GreaterOrEqual(level.Dressing.Count(p => p.Look), looks, id + ": looks built");
                Transform root = level.Root.transform;
                foreach (DressingPlacement p in level.Dressing.Where(p => !p.Look))
                {
                    string what = $"{id}: {p.Id} on {p.Host}";
                    if (p.Id == DecorKinds.SofaThrow)
                    {
                        Assert.That(p.Bounds.max.y, Is.EqualTo(p.HostTop + 0.0037f).Within(0.01f), what + ": the crest is not on the backrest top");
                    }
                    else
                    {
                        Assert.That(p.Bounds.min.y, Is.EqualTo(p.HostTop).Within(0.005f), what + ": floating or sunk");
                    }
                    if (p.Host == DecorKinds.FloorHost)
                    {
                        // BEDROOM: a floor item has no host group; LevelValidator.CheckFloorDecor keeps it in its room.
                        continue;
                    }
                    PropDef host = def.Props.Find(h => h.Name == p.Host);
                    Transform hostGroup = root.Find(p.Host);
                    Assert.IsNotNull(hostGroup, what + ": premise: no host group");
                    foreach (Vector3 corner in Corners(p.Bounds))
                    {
                        Vector3 local = hostGroup.InverseTransformPoint(root.TransformPoint(corner));
                        Assert.LessOrEqual(Mathf.Abs(local.x), host.SizeX * 0.5f + 0.02f, what + ": off the host's width");
                        if (p.Id != DecorKinds.SofaThrow)
                        {
                            Assert.LessOrEqual(Mathf.Abs(local.z), host.SizeZ * 0.5f + 0.02f, what + ": off the host's depth");
                        }
                    }
                }
                foreach (Renderer r in level.Root.GetComponentsInChildren<Renderer>(true)
                    .Where(r => r.name == LevelBuilder.DressingName || r.name.StartsWith(LevelBuilder.DecorPrefix)))
                {
                    Assert.IsTrue(WallArray.IsWallMaterial(r.sharedMaterial), $"{id}: {r.name} is not drawn with the wall material");
                    Assert.IsNull(r.GetComponent<Collider>(), $"{id}: {r.name} carries a collider");
                }
                if (def.Decor.Count > 0)
                {
                    // Merged into the floor renderer: some floor vertex names a dressing slice or a flat colour.
                    bool merged = level.Root.GetComponentsInChildren<MeshRenderer>(false).Where(r => r.gameObject.layer == Layers.Floor && WallArray.IsWallMaterial(r.sharedMaterial))
                        .Any(r =>
                        {
                            var finish = new List<Vector4>();
                            r.GetComponent<MeshFilter>().sharedMesh.GetUVs(WallArray.FinishChannel, finish);
                            return finish.Any(f => f.x == WallArray.FlatFinish || f.x > WallArray.Slices.Length + 0.5f);
                        });
                    Assert.IsTrue(merged, id + ": the decor is not in the floor renderer");
                }
            }
        }

        [UnityTest, Timeout(900000)]
        public IEnumerator Dressing_b_NoGameplayEffectWithinBudgets()
        {
            foreach (string id in Levels())
            {
                DressingLibrary.Disabled = true;
                yield return Build(id);
                List<string> bare = Colliders(Game.Level);
                Probe.RenderCount bareCount = Probe.CountRenderers(Game.Level.Root.GetComponentsInChildren<Renderer>(false));
                DressingLibrary.Disabled = false;
                yield return Build(id);
                List<string> dressed = Colliders(Game.Level);
                CollectionAssert.AreEqual(bare, dressed, id + ": the dressing changed a collider");
                Probe.RenderCount count = Probe.CountRenderers(Game.Level.Root.GetComponentsInChildren<Renderer>(false));
                Assert.LessOrEqual(count.Materials.Count, bareCount.Materials.Count, id + ": the dressing added a material");
                Assert.LessOrEqual(count.MaterialSlots, bareCount.MaterialSlots + 1, id + ": the dressing added more than one draw call");
                bool house = Game.Def.AllRooms().Count >= Tuning.HouseBudgetRooms;
                Assert.LessOrEqual(count.MaterialSlots, house ? Tuning.BudgetHouseRenderers : Tuning.BudgetRenderers, id + ": draw calls over budget");
            }
        }

        private static List<string> Colliders(LevelInstance level)
        {
            return level.Root.GetComponentsInChildren<Collider>(true)
                .Select(c => $"{c.name}|{c.gameObject.layer}|{c.enabled}|{c.isTrigger}|{Round(c.bounds.center)}|{Round(c.bounds.size)}")
                .OrderBy(s => s, System.StringComparer.Ordinal).ToList();
        }

        private static string Round(Vector3 v) => $"{v.x:0.###},{v.y:0.###},{v.z:0.###}";

        private static IEnumerable<Vector3> Corners(Bounds b)
        {
            for (int i = 0; i < 8; i++)
            {
                yield return new Vector3((i & 1) != 0 ? b.max.x : b.min.x, (i & 2) != 0 ? b.max.y : b.min.y, (i & 4) != 0 ? b.max.z : b.min.z);
            }
        }
    }
}
