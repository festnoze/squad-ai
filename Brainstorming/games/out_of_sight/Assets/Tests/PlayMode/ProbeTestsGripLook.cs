using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// GRIP (product owner, 2026-11-22: the dog bit the stool at the top of its seat; a man carrying the chair stood inside
    /// its back, his hands sunk into it): a look test on the REAL runtime path. The Boot scene and real levels through
    /// GameState.LoadLevel, their real rules. For each body (level 1 chair, 4 stool, 5 armchair, 6 floor lamp, 7 office chair,
    /// 10 rocking chair) the furniture is put out of place in a human's view until he carries it back; for the dog (level 12
    /// stool, level 17 chair) the furniture is moved in its view until it pins, grips and drags it. Frames from the game camera
    /// and close cameras (Build/shots/grip, or OOS_SHOT_DIR), the hands' distance to their targets, the body's distance to
    /// the furniture and the dog's neck bend are logged. Every shot is taken before any check fails.
    /// </summary>
    public sealed class ProbeTestsGripLook
    {
        private static string ShotDir
        {
            get
            {
                string dir = System.Environment.GetEnvironmentVariable("OOS_SHOT_DIR");
                return string.IsNullOrEmpty(dir) ? "Build/shots/grip" : dir;
            }
        }

        private Main main;
        private int fixedSteps;
        private readonly List<string> logged = new List<string>();
        private readonly List<string> problems = new List<string>();
        private Camera lookCamera;
        private GameState Game => main.Game;
        private FurnitureController Furniture => Game.Furniture;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            logged.Clear();
            problems.Clear();
            fixedSteps = 0;
            GamePause.IsPaused = false;
            Time.timeScale = 1f;
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Application.logMessageReceived += OnLog;
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Game.FixedStepped += Count;
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.FixedStepped -= Count;
                if (main.Game.Furniture != null)
                {
                    main.Game.Furniture.ScriptedDirection = null;
                }
            }
            if (lookCamera != null)
            {
                Object.Destroy(lookCamera.gameObject);
            }
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            yield return null;
        }

        private void Count() => fixedSteps++;

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                logged.Add(condition);
            }
        }

        private IEnumerator Until(System.Func<bool> until, float seconds)
        {
            int end = fixedSteps + Mathf.CeilToInt(seconds / Tuning.FixedStep);
            float realStart = Time.realtimeSinceStartup;
            while (fixedSteps < end && (until == null || !until()) && Time.realtimeSinceStartup - realStart < 120f)
            {
                yield return null;
            }
        }

        /// <summary>Renders <paramref name="cam"/> into a PNG (after a plain frame: WaitForEndOfFrame never comes in batch mode).</summary>
        private IEnumerator Shoot(Camera cam, string file, int width = 1280, int height = 800)
        {
            yield return null;
            var rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32) { antiAliasing = 4 };
            RenderTexture previousTarget = cam.targetTexture;
            cam.targetTexture = rt;
            cam.aspect = width / (float)height;
            try
            {
                var request = new RenderPipeline.StandardRequest { destination = rt };
                if (RenderPipeline.SupportsRenderRequest(cam, request))
                {
                    RenderPipeline.SubmitRenderRequest(cam, request);
                }
                else
                {
                    cam.Render();
                }
                RenderTexture previous = RenderTexture.active;
                RenderTexture.active = rt;
                var shot = new Texture2D(width, height, TextureFormat.RGB24, false);
                shot.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                shot.Apply();
                RenderTexture.active = previous;
                Directory.CreateDirectory(ShotDir);
                File.WriteAllBytes(Path.Combine(ShotDir, file), shot.EncodeToPNG());
                Object.Destroy(shot);
            }
            finally
            {
                cam.targetTexture = previousTarget;
                cam.ResetAspect();
                rt.Release();
                Object.Destroy(rt);
            }
        }

        /// <summary>A free camera at <paramref name="eye"/> looking at <paramref name="target"/>.</summary>
        private Camera Look(Vector3 eye, Vector3 target, float fov = 40f)
        {
            if (lookCamera == null)
            {
                lookCamera = new GameObject("GripLookCamera").AddComponent<Camera>();
                lookCamera.nearClipPlane = 0.03f;
                lookCamera.enabled = false;
            }
            lookCamera.fieldOfView = fov;
            lookCamera.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(target - eye));
            return lookCamera;
        }

        /// <summary>A free spot <paramref name="distances"/> ahead of <paramref name="from"/> (turned a little either way), in
        /// its room and <paramref name="clear"/> metres clear of the room's walls.</summary>
        private bool FreeSpot(Vector3 from, float yaw, float[] distances, out Vector3 spot, float clear = 0.7f)
        {
            Vector3 forward = YawMath.Forward(yaw);
            foreach (float d in distances)
            {
                foreach (float turn in new[] { 0f, 25f, -25f, 45f, -45f, 70f, -70f })
                {
                    Vector3 p = YawMath.Planar(from) + Quaternion.Euler(0f, turn, 0f) * forward * d;
                    RoomDef room = Game.Def.RoomAt(p);
                    if (room != null && room == Game.Def.RoomAt(from)
                        && Mathf.Abs(p.x - room.X) < room.SizeX * 0.5f - clear && Mathf.Abs(p.z - room.Z) < room.SizeZ * 0.5f - clear)
                    {
                        spot = p;
                        return true;
                    }
                }
            }
            spot = default;
            return false;
        }

        [UnityTest]
        [Timeout(900000)]
        public IEnumerator GripLook_HumansCarryEveryBodyByItsGrip()
        {
            foreach ((string level, string kind) in new[] { ("level1", "chair"), ("level4", "stool"), ("level5", "armchair"), ("level6", "floor_lamp"),
                ("level7", "office_chair"), ("level10", "rocking_chair") })
            {
                yield return HumanCarry(level, kind);
            }
            Debug.Log("[GripLook] errors logged: " + string.Join(" | ", logged));
            Assert.IsEmpty(problems, string.Join("\n", problems));
        }

        private IEnumerator HumanCarry(string level, string kind)
        {
            Game.LoadLevel(level);
            yield return Until(null, 0.2f);
            if (Game.State != PlayState.Playing || Furniture == null || Furniture.Kind != kind)
            {
                problems.Add($"{level}: premise: not playing a {kind} ({Game.State}, {Furniture?.Kind})");
                yield break;
            }
            Inhabitant h = Game.Level.Inhabitants.FirstOrDefault(i => i != null && !i.IsDog && i.Rig != null);
            if (h == null)
            {
                problems.Add($"{level}: premise: no human with a model");
                yield break;
            }
            foreach (Inhabitant other in Game.Level.Inhabitants.Where(i => i != null && i != h))
            {
                other.Pin(other.Routine.Position, other.Routine.BodyYaw);
            }
            Vector3 spot;
            if (level == "level1")
            {
                // Level 1's room is too small for the search: Step24's known setup (ProbeTestsM3Rig), the man at the window.
                h.Pin(new Vector3(0f, 0f, -2.3f), 0f);
                spot = new Vector3(-3.2f, 0f, -0.8f);
            }
            else if (!FreeSpot(h.Routine.Position, h.Routine.EyeYaw, new[] { 2.6f, 2.2f, 1.8f, 1.4f, 1.1f }, out spot, 0.5f))
            {
                problems.Add($"{level}: premise: no free spot in the human's view");
                yield break;
            }
            Furniture.Teleport(spot, YawMath.YawOf(spot - h.Routine.Position) + 30f);
            h.Pin(h.Routine.Position, YawMath.YawOf(spot - h.Routine.Position), 0f, true);
            InhabitantRoutine routine = h.Routine;
            yield return Until(() => (routine.IsCarrying && routine.LastActivity == RoutineActivity.Carrying) || Game.State != PlayState.Playing, 20f);
            if (!routine.IsCarrying)
            {
                problems.Add($"{level}: premise: no carry ({Game.State} {Game.LoseReason}, mode {routine.Mode}, activity {routine.LastActivity})");
                yield break;
            }
            yield return Until(null, 0.35f);
            // Measured on the pose that renders: in a LateUpdate after the rig's (a coroutine runs after the rig's Update put
            // its driven bones back to their rest).
            InhabitantRig rig = h.Rig;
            Vector3 palmLeft = default;
            Vector3 palmRight = default;
            Vector3 spine = default;
            var watcher = new GameObject("GripWatcher").AddComponent<RigWatcher>();
            watcher.Late = () =>
            {
                palmLeft = rig.PalmLeft.position;
                palmRight = rig.PalmRight.position;
                spine = rig.Spine.position;
            };
            yield return null;
            yield return null;
            Object.Destroy(watcher.gameObject);
            GripDef g = h.Grip;
            Furniture.InterpolatedBase(1f, out Vector3 at, out float yaw);
            Quaternion frame = Quaternion.Euler(0f, yaw, 0f);
            Vector3 left = at + frame * g.LeftWrist;
            Vector3 right = at + frame * g.RightWrist;
            float straight = Mathf.Max(Vector3.Distance(palmLeft, left), Vector3.Distance(palmRight, right));
            float crossed = Mathf.Max(Vector3.Distance(palmLeft, right), Vector3.Distance(palmRight, left));
            float miss = Mathf.Min(straight, crossed);
            Transform body = h.Visual != null ? h.Visual : h.transform;
            Vector3 forward = body.forward;
            Vector3 nearFace = at - frame * Vector3.forward * (0.5f * Furniture.Size.z);
            float bellyGap = Vector3.Dot(nearFace - spine, forward);
            float bodyToCentre = Vector3.Dot(at - body.position, forward);
            Debug.Log($"[GripLook] {level} {kind}: hand grip {h.ShownHandGrip:0.00} (rig {rig.HandGripWeight:0.00}), hands {miss:0.000} m from their targets"
                + $" ({(straight <= crossed ? "left/right" : "crossed")}), hold {h.ShownHold} m, body {bodyToCentre:0.000} m behind the centre (grip {g.HumanStand:0.00}),"
                + $" near face {bellyGap:0.000} m ahead of the spine, furniture lifted {at.y - Game.Def.Floor.HeightAt(at):0.000} m");

            Vector3 middle = 0.5f * (body.position + at) + Vector3.up * 0.8f;
            Vector3 side = body.right;
            yield return Shoot(main.Camera, $"human_{kind}_game.png");
            yield return Shoot(Look(middle + side * 1.4f + Vector3.up * 0.3f, middle, 55f), $"human_{kind}_side.png");
            yield return Shoot(Look(middle - side * 1.0f - forward * 1.1f + Vector3.up * 0.8f, middle, 55f), $"human_{kind}_back.png");
            yield return Shoot(Look(middle + side * 1.3f + forward * 1.6f + Vector3.up * 0.5f, middle - Vector3.up * 0.1f), $"human_{kind}_front.png");
            if (h.ShownHandGrip < 0.9f)
            {
                problems.Add($"{level} {kind}: the hand grip does not show while carrying ({h.ShownHandGrip:0.00})");
            }
            if (miss > 0.08f)
            {
                problems.Add($"{level} {kind}: the hands are {miss:0.000} m off their places on the furniture");
            }
            if (bellyGap < 0.12f)
            {
                problems.Add($"{level} {kind}: the body stands too close to the furniture ({bellyGap:0.000} m from the spine)");
            }
        }

        [UnityTest]
        [Timeout(900000)]
        public IEnumerator GripLook_DogBitesTheStoolAndTheChairLow()
        {
            yield return DogDrag("level12", "stool");
            yield return DogDrag("level17", "chair");
            Debug.Log("[GripLook] errors logged: " + string.Join(" | ", logged));
            Assert.IsEmpty(problems, string.Join("\n", problems));
        }

        private IEnumerator DogDrag(string level, string kind)
        {
            Game.LoadLevel(level);
            yield return Until(null, 0.2f);
            Inhabitant dog = Game.Level.Inhabitants.FirstOrDefault(i => i != null && i.IsDog);
            if (Game.State != PlayState.Playing || dog == null || dog.Rig == null || Furniture.Kind != kind)
            {
                problems.Add($"{level}: premise: no dog with a model or not a {kind} ({Game.State}, {Furniture?.Kind})");
                yield break;
            }
            Debug.Log($"[GripLook] {level} dog: neck chain {dog.Rig.HasNeck}, jaw {dog.Rig.HasJaw}, snout target {dog.Grip.Snout}");
            foreach (Inhabitant h in Game.Level.Inhabitants.Where(i => i != null && !i.IsDog))
            {
                h.Pin(h.Routine.Position, h.Routine.BodyYaw);
            }
            yield return Until(null, 0.1f);
            if (!FreeSpot(dog.Routine.Position, dog.Routine.EyeYaw, new[] { 2.2f, 1.8f, 2.6f, 1.5f }, out Vector3 spot))
            {
                problems.Add($"{level}: premise: no free spot in the dog's view");
                yield break;
            }
            Furniture.Teleport(spot, YawMath.YawOf(dog.Routine.Position - spot));
            yield return Until(null, 0.1f);
            Vector3 across = Vector3.Cross(Vector3.up, YawMath.Forward(dog.Routine.EyeYaw)).normalized;
            float flip = 1f;
            float runStart = Time.realtimeSinceStartup;
            while (Game.BarkCount == 0 && Game.HoldingDog == null && Game.State == PlayState.Playing && Time.realtimeSinceStartup - runStart < 30f)
            {
                Furniture.ScriptedDirection = across * flip;
                yield return Until(() => Game.BarkCount > 0 || Game.HoldingDog != null, 0.6f);
                flip = -flip;
            }
            Furniture.ScriptedDirection = null;
            if (Game.HoldingDog == null)
            {
                problems.Add($"{level}: premise: the dog never barked at the {kind} ({Game.State} {Game.LoseReason})");
                yield break;
            }
            yield return Until(() => Game.HeldByDog, 6f);
            yield return Until(null, 0.35f);
            yield return null;
            Debug.Log($"[GripLook] {level} {kind} grip: bite {dog.ShownBite:0.00}, neck {dog.Rig.GripNeck:0.0} deg, hold {dog.ShownHold} m");
            yield return DogShots(dog, $"dog_{kind}_grip");

            yield return Until(() => Game.DraggedByDog || Game.State != PlayState.Playing, Tuning.DogGripTime + 2f);
            if (!Game.DraggedByDog)
            {
                problems.Add($"{level}: premise: the dog never dragged the {kind} ({Game.State})");
                yield break;
            }
            yield return Until(null, 1.0f);
            yield return null;
            Furniture.InterpolatedBase(1f, out Vector3 at, out float yaw);
            Vector3 target = at + Quaternion.Euler(0f, yaw, 0f) * dog.Grip.Snout;
            Debug.Log($"[GripLook] {level} {kind} drag: bite {dog.ShownBite:0.00}, neck {dog.Rig.GripNeck:0.0} deg, hold {dog.ShownHold} m, "
                + $"bite point {target.y - Game.Def.Floor.HeightAt(target):0.000} m over the floor, head bone {dog.Rig.Head.position.y - Game.Def.Floor.HeightAt(target):0.000} m");
            yield return DogShots(dog, $"dog_{kind}_drag");
            if (dog.ShownBite < 0.9f)
            {
                problems.Add($"{level} {kind}: the bite pose does not show during the drag");
            }
            if (dog.Rig.HasNeck && dog.Rig.GripNeck < 20f)
            {
                problems.Add($"{level} {kind}: the dog does not lower its head to the low bite ({dog.Rig.GripNeck:0.0} deg)");
            }
        }

        private IEnumerator DogShots(Inhabitant dog, string name)
        {
            Transform frame = dog.Visual != null ? dog.Visual : dog.transform;
            Vector3 head = dog.Rig.Head.position;
            Vector3 middle = head + frame.forward * 0.25f - Vector3.up * 0.1f;
            yield return Shoot(main.Camera, name + "_game.png");
            yield return Shoot(Look(middle + frame.right * 1.3f + Vector3.up * 0.15f, middle), name + "_right.png");
            yield return Shoot(Look(middle - frame.right * 1.3f + Vector3.up * 0.15f, middle), name + "_left.png");
            yield return Shoot(Look(middle - frame.right * 1.0f - frame.forward * 0.9f + Vector3.up * 0.8f, middle), name + "_back.png");
        }
    }
}
