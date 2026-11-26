using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// DOGBIG v4 (product owner, 2026-11-21: "in game the textures do not look applied, the bite does not work"): a look test
    /// on the REAL runtime path, no editor shortcut. The Boot scene, the real level 12 through GameState.LoadLevel, its real
    /// rules; every human frozen (so only the dog watches), the chair put in the dog's view and moved until the dog barks,
    /// runs, pins it, grips it and drags it home. Frames are shot from the game camera and from a close camera during the
    /// grip and the drag (Build/shots/dog/runtime_*.png, or OOS_SHOT_DIR), and the dog's renderer, materials, texture, bite
    /// and bones are logged. It asserts what the shots rely on: the fur map on the dog's slots, the bite weight up during the
    /// grip and the drag, the head rolled and the jaw open in the rendered pose.
    /// </summary>
    public sealed class ProbeTestsDogLook
    {
        private static string ShotDir
        {
            get
            {
                string dir = System.Environment.GetEnvironmentVariable("OOS_SHOT_DIR");
                return string.IsNullOrEmpty(dir) ? "Build/shots/dog" : dir;
            }
        }

        private Main main;
        private int fixedSteps;
        private readonly List<string> logged = new List<string>();
        private GameState Game => main.Game;
        private FurnitureController Chair => Game.Furniture;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            logged.Clear();
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

        private static Transform FindDeep(Transform t, string name)
        {
            if (t.name == name)
            {
                return t;
            }
            for (int i = 0; i < t.childCount; i++)
            {
                Transform found = FindDeep(t.GetChild(i), name);
                if (found != null)
                {
                    return found;
                }
            }
            return null;
        }

        /// <summary>Renders <paramref name="cam"/> into a PNG after the frame (its LateUpdate poses included).</summary>
        private IEnumerator Shoot(Camera cam, string file, int width = 1280, int height = 800)
        {
            // Not WaitForEndOfFrame: it never comes in a batch mode editor. After a plain frame the bones still hold the last
            // LateUpdate pose (this frame's animation has not run yet), so the render shows the posed dog.
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

        private Camera closeCamera;

        /// <summary>A close camera beside the dog's head, looking at it.</summary>
        private Camera CloseCamera(Inhabitant dog, float side, float distance)
        {
            if (closeCamera == null)
            {
                closeCamera = new GameObject("DogLookCamera").AddComponent<Camera>();
                closeCamera.fieldOfView = 40f;
                closeCamera.nearClipPlane = 0.03f;
                closeCamera.enabled = false;
            }
            Transform frame = dog.Visual != null ? dog.Visual : dog.transform;
            Vector3 head = dog.Rig != null && dog.Rig.Head != null ? dog.Rig.Head.position : frame.position + Vector3.up * 0.5f;
            Vector3 eye = head + frame.right * (side * distance) + frame.forward * (0.6f * distance) + Vector3.up * (0.35f * distance);
            closeCamera.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(head - eye));
            return closeCamera;
        }

        /// <summary>
        /// DOGFACE: the lower jaw's skin (every vertex the Jaw joint drives alone), skinned as the renderer does
        /// (bone.localToWorld * bindpose), as a direction from the hinge in the head's frame; <paramref name="count"/> the vertices.
        /// </summary>
        private static Vector3 JawSkinDirection(InhabitantRig rig, Transform jaw, out int count)
        {
            count = 0;
            var skin = rig.Skin as SkinnedMeshRenderer;
            int bone = skin != null ? System.Array.IndexOf(skin.bones, jaw) : -1;
            if (bone < 0)
            {
                return Vector3.zero;
            }
            Mesh mesh = skin.sharedMesh;
            Vector3[] vertices = mesh.vertices;
            BoneWeight[] weights = mesh.boneWeights;
            Vector3 sum = Vector3.zero;
            for (int i = 0; i < vertices.Length && i < weights.Length; i++)
            {
                BoneWeight w = weights[i];
                float onJaw = (w.boneIndex0 == bone ? w.weight0 : 0f) + (w.boneIndex1 == bone ? w.weight1 : 0f)
                    + (w.boneIndex2 == bone ? w.weight2 : 0f) + (w.boneIndex3 == bone ? w.weight3 : 0f);
                if (onJaw >= 0.99f)
                {
                    sum += vertices[i];
                    count++;
                }
            }
            if (count == 0)
            {
                return Vector3.zero;
            }
            Vector3 world = jaw.localToWorldMatrix.MultiplyPoint3x4(mesh.bindposes[bone].MultiplyPoint3x4(sum / count));
            return rig.Head.InverseTransformDirection(world - jaw.position);
        }

        private static string Describe(Inhabitant dog)
        {
            var sb = new StringBuilder();
            InhabitantRig rig = dog.Rig;
            sb.Append($"model {(rig != null ? rig.Entry.id : "none")}, fur map {(ModelKit.PetFurMap != null ? ModelKit.PetFurMap.name + " " + ModelKit.PetFurMap.width + "px mipBias " + ModelKit.PetFurMap.mipMapBias : "MISSING")}, "
                + $"head atlas {(ModelKit.PetHeadMap != null ? ModelKit.PetHeadMap.name + " " + ModelKit.PetHeadMap.width + "px" : "MISSING")}; ");
            if (rig != null && rig.Skin != null)
            {
                Renderer r = rig.Skin;
                sb.Append($"skin '{r.name}' property block {r.HasPropertyBlock()}, mesh {rig.Skin.sharedMesh.name} uv {rig.Skin.sharedMesh.uv.Length}/{rig.Skin.sharedMesh.vertexCount}: ");
                foreach (Material m in r.sharedMaterials)
                {
                    sb.Append($"[{(m != null ? m.name : "null")} shader {(m != null ? m.shader.name : "-")} base {(m != null && m.HasProperty("_BaseColor") ? m.GetColor("_BaseColor").ToString() : "-")} map {(m != null && m.HasProperty("_BaseMap") && m.GetTexture("_BaseMap") != null ? m.GetTexture("_BaseMap").name : "none")}] ");
                }
            }
            return sb.ToString();
        }

        [UnityTest]
        [Timeout(300000)]
        public IEnumerator DogLook_RuntimeGripAndDragOnLevel12()
        {
            Game.LoadLevel("level12");
            yield return Until(null, 0.2f);
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: level 12 plays");
            Inhabitant dog = Game.Level.Inhabitants.FirstOrDefault(h => h != null && h.IsDog);
            Assert.IsNotNull(dog, "premise: level 12 has a dog");
            Debug.Log("[DogLook] at load: " + Describe(dog));
            Assert.IsNotNull(dog.Rig, "the dog shows no model");
            Assert.IsNotNull(ModelKit.PetFurMap, "the fur map is not in the build's Resources");
            Material fur = dog.Rig.Skin.sharedMaterials.FirstOrDefault(m => m != null && m.HasProperty("_BaseMap") && m.GetTexture("_BaseMap") == ModelKit.PetFurMap);
            Assert.IsNotNull(fur, "no slot of the dog shows the fur map: " + Describe(dog));
            // LABRADOR: the final Labrador's head shows its own atlas (the painted eyes), untinted, beside the fur map.
            Assert.IsNotNull(ModelKit.PetHeadMap, "the head atlas is not in the build's Resources");
            Material headAtlas = dog.Rig.Skin.sharedMaterials.FirstOrDefault(m => m != null && m.HasProperty("_BaseMap") && m.GetTexture("_BaseMap") == ModelKit.PetHeadMap);
            Assert.IsNotNull(headAtlas, "no slot of the dog shows the head atlas: " + Describe(dog));
            Assert.AreEqual(Color.white, headAtlas.GetColor("_BaseColor"), "the head atlas is tinted");
            Assert.AreEqual(Color.white, fur.GetColor("_BaseColor"), "the fur map is tinted");
            Debug.Log($"[DogLook] snout reach {dog.Rig.SnoutReach:0.000} m (rest {ModelKit.ForwardReach(dog.Rig.Entry):0.000}), jaw {dog.Rig.HasJaw}, hold back {dog.DogHoldBack:0.000} m");

            // Only the dog watches: every human frozen where it stands (a frozen pin observes nothing).
            foreach (Inhabitant h in Game.Level.Inhabitants.Where(h => h != null && !h.IsDog))
            {
                h.Pin(h.Routine.Position, h.Routine.BodyYaw);
            }
            yield return Until(null, 0.1f);
            // DOGFACE: the shut jaw's skin direction from the hinge and the dog's right, both in the head's frame.
            Transform jawAtRest = FindDeep(dog.Rig.Model.transform, "Jaw");
            Assert.IsNotNull(jawAtRest, "the dog's model has no Jaw joint");
            Vector3 jawShut = JawSkinDirection(dog.Rig, jawAtRest, out int jawVertices);
            Vector3 headRight = dog.Rig.Head.InverseTransformDirection((dog.Visual != null ? dog.Visual : dog.transform).right);
            Debug.Log($"[DogLook] lower jaw: {jawVertices} vertices on the Jaw alone, shut direction {jawShut} (head frame), bite {dog.ShownBite:0.00}");
            Assert.GreaterOrEqual(jawVertices, 20, "the lower jaw is not skinned to the Jaw joint");
            Camera game = main.Camera;
            yield return Shoot(game, "runtime_level12_start_game.png");
            yield return Shoot(CloseCamera(dog, 1f, 1.1f), "runtime_level12_start_close.png");

            // The chair in the dog's view, then moved sideways until the dog barks.
            Vector3 forward = YawMath.Forward(dog.Routine.EyeYaw);
            Vector3 spot = Vector3.zero;
            bool found = false;
            foreach (float d in new[] { 2.2f, 1.8f, 2.6f, 1.5f })
            {
                foreach (float turn in new[] { 0f, 25f, -25f, 45f, -45f })
                {
                    Vector3 p = YawMath.Planar(dog.Routine.Position) + Quaternion.Euler(0f, turn, 0f) * forward * d;
                    RoomDef room = Game.Def.RoomAt(p);
                    if (room != null && room == Game.Def.RoomAt(dog.Routine.Position)
                        && Mathf.Abs(p.x - room.X) < room.SizeX * 0.5f - 0.7f && Mathf.Abs(p.z - room.Z) < room.SizeZ * 0.5f - 0.7f)
                    {
                        spot = p;
                        found = true;
                        break;
                    }
                }
                if (found)
                {
                    break;
                }
            }
            Assert.IsTrue(found, "premise: no free spot in the dog's view");
            Chair.Teleport(spot, YawMath.YawOf(dog.Routine.Position - spot));
            yield return Until(null, 0.1f);
            Vector3 side = Vector3.Cross(Vector3.up, forward).normalized;
            float flip = 1f;
            float runStart = Time.realtimeSinceStartup;
            while (Game.BarkCount == 0 && Game.HoldingDog == null && Game.State == PlayState.Playing && Time.realtimeSinceStartup - runStart < 30f)
            {
                Chair.ScriptedDirection = side * flip;
                yield return Until(() => Game.BarkCount > 0 || Game.HoldingDog != null, 0.6f);
                flip = -flip;
            }
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Playing, Game.State, $"premise: the level was lost ({Game.LoseReason})");
            Assert.IsNotNull(Game.HoldingDog, "premise: the dog never barked at the chair");

            // The pin and the grip: the bite pose shows (head rolled, jaw open) before the drag.
            yield return Until(() => Game.HeldByDog, 6f);
            Assert.IsTrue(Game.HeldByDog, "premise: the dog never pinned the chair");
            yield return Until(null, 0.3f);
            yield return null;
            Transform jaw = FindDeep(dog.Rig.Model.transform, "Jaw");
            float roll = Vector3.Angle(dog.Rig.Head.up, Vector3.up);
            float jawAngle = jaw != null ? Quaternion.Angle(Quaternion.identity, jaw.localRotation) : -1f;
            Debug.Log($"[DogLook] grip: Biting {dog.Biting}, shown bite {dog.ShownBite:0.00}, rig bite {dog.Rig.Bite:0.00}, head up off the vertical {roll:0.0} deg, "
                + $"jaw {jawAngle:0.0} deg, head scale {dog.Rig.Head.localScale.x:0.00}; " + Describe(dog));
            yield return Shoot(game, "runtime_level12_grip_game.png");
            yield return Shoot(CloseCamera(dog, 1f, 1.0f), "runtime_level12_grip_close.png");
            yield return Shoot(CloseCamera(dog, -1f, 1.0f), "runtime_level12_grip_close_left.png");
            Assert.IsTrue(dog.Biting, "the game state did not set the dog biting during the grip");
            Assert.Greater(dog.ShownBite, 0.9f, "the bite pose did not ease in during the grip");
            Assert.IsNotNull(jaw, "the dog's model has no Jaw joint");
            Assert.Greater(jawAngle, 0.5f * Tuning.DogJawOpenDegrees, "the jaw is not open in the rendered pose");
            // DOGFACE: the lower jaw's skin swings DOWN from the upper jaw (not up into the muzzle), by about the opening.
            Vector3 jawOpen = JawSkinDirection(dog.Rig, jaw, out _);
            float swing = Vector3.Angle(jawShut, jawOpen);
            float down = Vector3.Dot(Vector3.Cross(jawShut, jawOpen), headRight);
            Debug.Log($"[DogLook] grip: lower jaw skin swung {swing:0.0} deg, about the dog's right {down:0.0000} (positive = down)");
            foreach (float s in new[] { 1f, -1f })
            {
                Transform frame = dog.Visual != null ? dog.Visual : dog.transform;
                Vector3 head = dog.Rig.Head.position;
                Camera cam = CloseCamera(dog, s, 0.8f);
                Vector3 eye = head + frame.right * (0.6f * s) + frame.forward * 0.25f + Vector3.up * 0.05f;
                cam.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(head + frame.forward * 0.12f - eye));
                yield return Shoot(cam, s > 0f ? "runtime_level12_grip_mouth_right.png" : "runtime_level12_grip_mouth_left.png");
            }
            Assert.Greater(swing, 0.5f * Tuning.DogJawOpenDegrees, "the lower jaw's skin does not follow the open jaw");
            Assert.Greater(down, 0f, "the jaw opens upward, into the muzzle");

            // The drag.
            yield return Until(() => Game.DraggedByDog || Game.State != PlayState.Playing, Tuning.DogGripTime + 2f);
            Assert.IsTrue(Game.DraggedByDog, $"premise: the dog never dragged the chair ({Game.State})");
            yield return Until(null, 1.0f);
            yield return null;
            jawAngle = jaw != null ? Quaternion.Angle(Quaternion.identity, jaw.localRotation) : -1f;
            Debug.Log($"[DogLook] drag: shown bite {dog.ShownBite:0.00}, jaw {jawAngle:0.0} deg, hold back shown {dog.ShownHoldBack:0.000} m");
            yield return Shoot(game, "runtime_level12_drag_game.png");
            yield return Shoot(CloseCamera(dog, 1f, 1.2f), "runtime_level12_drag_close.png");
            yield return Shoot(CloseCamera(dog, -1f, 1.2f), "runtime_level12_drag_close_left.png");
            // Profiles at muzzle height, both sides: the open mouth on the edge.
            foreach (float s in new[] { 1f, -1f })
            {
                Transform frame = dog.Visual != null ? dog.Visual : dog.transform;
                Vector3 head = dog.Rig.Head.position;
                Camera cam = CloseCamera(dog, s, 0.8f);
                Vector3 eye = head + frame.right * (0.75f * s) + frame.forward * 0.12f + Vector3.up * 0.02f;
                cam.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(head + frame.forward * 0.12f - eye));
                yield return Shoot(cam, s > 0f ? "runtime_level12_drag_profile_right.png" : "runtime_level12_drag_profile_left.png");
            }
            Assert.Greater(dog.ShownBite, 0.9f, "the bite pose is not held during the drag");

            // The drop: the bite lets go.
            yield return Until(() => Game.HoldingDog == null || Game.State != PlayState.Playing, 30f);
            yield return Until(null, 0.6f);
            Debug.Log($"[DogLook] after the drop: Biting {dog.Biting}, shown bite {dog.ShownBite:0.00}");
            yield return Shoot(game, "runtime_level12_after_game.png");
            yield return Shoot(CloseCamera(dog, 1f, 1.1f), "runtime_level12_after_close.png");
            Assert.IsFalse(dog.Biting, "the dog still bites after the drop");
            Debug.Log("[DogLook] errors logged: " + string.Join(" | ", logged));
        }
    }
}
