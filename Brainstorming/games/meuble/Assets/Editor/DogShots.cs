using System;
using System.IO;
using OutOfSight.Core;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight.Editor
{
    /// <summary>
    /// DOGBIG (2026-11-21): a look tool, not a check. Renders the house dog to PNGs under the game's sun and ambient:
    /// <list type="bullet">
    /// <item>a lineup on a plain floor: the old Shiba at its old size (its GLB, grey-blue), the new dog (the dog row's model
    /// and tint through ModelKit, as the game builds it), a human and the player chair, front three quarters and side;</item>
    /// <item>from above, the new dog between two door jambs 1.0 m apart (the dog levels' doors);</item>
    /// <item>the drag pose: the chair held at the carry anchor (CarryForward ahead, lifted DogDragLift), the dog's model
    /// stepped back by its hold back (Inhabitant.DogHoldBack's formula), side and three quarters;</item>
    /// <item>the dog levels (12, 15, 17, 20, 24 by default): the dog where the level builds it, from the game camera's
    /// distance and pitch, and a close-up.</item>
    /// </list>
    /// -executeMethod OutOfSight.Editor.DogShots.Shoot [-dogShots &lt;dir&gt;] [-dogLevels level12,level24]
    /// </summary>
    public static class DogShots
    {
        private const string ShibaPath = "Assets/ThirdParty/Models/Quaternius/quaternius_shiba.glb";
        private static readonly Color OldTint = new Color32(0x4F, 0x66, 0x70, 0xFF);
        private static readonly Color Red = new Color32(0xD7, 0x26, 0x3D, 0xFF);

        public static void Shoot()
        {
            int code = 0;
            try
            {
                string dir = Arg("-dogShots") ?? Path.Combine("Build", "shots", "dog");
                Directory.CreateDirectory(dir);
                ModelCatalogBuilder.Build();
                Lineup(dir);
                Fur(dir);
                Drag(dir);
                string levels = Arg("-dogLevels") ?? "level12,level15,level17,level20,level24";
                foreach (string id in levels.Split(','))
                {
                    ShootLevel(dir, id.Trim());
                }
            }
            catch (Exception e)
            {
                Debug.LogError("[DogShots] threw: " + e);
                code = 1;
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        private static string DogModel => PersonalityDef.For(PersonalityDef.Dog).Model;

        private static Color DogTint
        {
            get
            {
                ColorUtility.TryParseHtmlString(PersonalityDef.For(PersonalityDef.Dog).Tint, out Color c);
                return new Color(c.r, c.g, c.b, 1f);
            }
        }

        // The last dog's head bone, metres ahead of its root (Idle), for the snout reach.
        private static float HeadForward;

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

        /// <summary>The new dog as the game builds it (ModelKit fit and paint, then the tint), under a fresh holder.</summary>
        private static GameObject NewDog(Vector3 at, float yaw, float bite = 0f)
        {
            var holder = new GameObject("NewDog");
            holder.transform.SetPositionAndRotation(at, Quaternion.Euler(0f, yaw, 0f));
            var box = new Vector3(2f * Tuning.DogCapsuleRadius, Tuning.DogCapsuleHeight, 2f * Tuning.DogCapsuleRadius);
            GameObject model = ModelKit.Instantiate(DogModel, holder.transform, box, ModelFit.Uniform, new ModelPaint { Main = DogTint });
            if (model == null)
            {
                throw new InvalidOperationException("the dog model " + DogModel + " did not load");
            }
            ModelCatalog.Entry entry = ModelCatalog.Lookup(DogModel);
            ModelKit.TintClothes(model, entry, DogTint);
            SampleIdle(model, entry);
            PetPose pose = PetPose.Find(model.transform, holder.transform.rotation);
            pose.Bite = bite;
            pose.Apply(holder.transform.rotation, holder.transform.rotation);
            Transform head = FindDeep(model.transform, "Head");
            HeadForward = head != null ? holder.transform.InverseTransformPoint(head.position).z : 0f;
            Debug.Log($"[DogShots] jaw joint {(pose.HasJaw ? "found" : "MISSING")}, head bone {HeadForward:0.000} m ahead of the root");
            Debug.Log($"[DogShots] new dog {DogModel}: scale {ModelKit.RiggedScale(entry):0.0000}, height {entry.nativeSize.y * ModelKit.RiggedScale(entry):0.000} m, "
                + $"length {entry.nativeSize.z * ModelKit.RiggedScale(entry):0.000} m, width {entry.nativeSize.x * ModelKit.RiggedScale(entry):0.000} m, "
                + $"snout reach {ModelKit.ForwardReach(entry):0.000} m, triangles {ModelKit.Triangles(model.GetComponentInChildren<SkinnedMeshRenderer>().sharedMesh)}");
            return holder;
        }

        private static void SampleIdle(GameObject model, ModelCatalog.Entry entry)
        {
            Animation animation = model.GetComponentInChildren<Animation>(true);
            if (animation == null || entry == null || string.IsNullOrEmpty(entry.idleClip) || animation[entry.idleClip] == null)
            {
                return;
            }
            animation.playAutomatically = false;
            animation.Stop();
            animation[entry.idleClip].clip.SampleAnimation(animation.gameObject, 0f);
        }

        /// <summary>The old Shiba at its old size (eyes at 0.35 m: 0.35 / 2.709 native units), in the old grey-blue.</summary>
        private static GameObject OldShiba(Vector3 at, float yaw)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(ShibaPath);
            if (prefab == null)
            {
                return null;
            }
            GameObject shiba = UnityEngine.Object.Instantiate(prefab);
            shiba.name = "OldShiba";
            shiba.transform.SetPositionAndRotation(at, Quaternion.Euler(0f, yaw, 0f));
            shiba.transform.localScale = Vector3.one * (Tuning.DogEyeHeight / 2.709f);
            foreach (Renderer r in shiba.GetComponentsInChildren<Renderer>(true))
            {
                var slots = r.sharedMaterials;
                for (int i = 0; i < slots.Length; i++)
                {
                    string n = slots[i] != null ? slots[i].name : "";
                    slots[i] = PrimitiveKit.Lit(n.StartsWith("Main_Light") || n.StartsWith("Eyes_White") ? Tuning.CharacterPalette[5]
                        : n == "Main" ? OldTint : Tuning.CharacterPalette[0], 0.25f);
                }
                r.sharedMaterials = slots;
            }
            Animation animation = shiba.GetComponentInChildren<Animation>(true);
            if (animation != null && animation["Idle"] != null)
            {
                animation.playAutomatically = false;
                animation.Stop();
                animation["Idle"].clip.SampleAnimation(animation.gameObject, 0f);
            }
            return shiba;
        }

        private static void Floor(float sizeX, float sizeZ, Color colour)
        {
            var floor = new GameObject("Floor");
            floor.AddComponent<MeshFilter>().sharedMesh = PrimitiveKit.BoxMesh;
            floor.AddComponent<MeshRenderer>().sharedMaterial = PrimitiveKit.Lit(colour, 0.2f);
            floor.transform.localScale = new Vector3(sizeX, 0.02f, sizeZ);
            floor.transform.position = new Vector3(0f, -0.01f, 0f);
        }

        private static void Lineup(string dir)
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Floor(8f, 6f, new Color32(0xB0, 0x7A, 0x4E, 0xFF));
            OldShiba(new Vector3(-1.6f, 0f, 0f), 90f);
            NewDog(new Vector3(-0.5f, 0f, 0f), 90f);
            var man = new GameObject("Man");
            man.transform.position = new Vector3(0.7f, 0f, 0f);
            ModelKit.Instantiate(ModelCatalog.QuaterniusMan, man.transform, new Vector3(0.5f, Tuning.InhabitantHeight, 0.5f), ModelFit.Uniform, default);
            var chair = new GameObject("Chair");
            chair.transform.position = new Vector3(1.7f, 0f, 0f);
            ModelKit.Instantiate(ModelCatalog.KenneyChair, chair.transform, new Vector3(0.45f, 0.9f, 0.45f), ModelFit.Box, new ModelPaint { Main = Red, Red = Red });
            Camera cam = Stage();
            Render(cam, new Vector3(1.2f, 1.9f, 4.6f), new Vector3(0f, 0.55f, 0f), Path.Combine(dir, "lineup_front.png"));
            Render(cam, new Vector3(0f, 0.6f, 5.2f), new Vector3(0f, 0.55f, 0f), Path.Combine(dir, "lineup_side.png"));

            // From above: the new dog between two jambs 1.0 m apart (the dog levels' doors), walking through.
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Floor(4f, 4f, new Color32(0xD8, 0xD4, 0xCC, 0xFF));
            foreach (float x in new[] { -0.55f, 0.55f })
            {
                var jamb = new GameObject("Jamb");
                jamb.AddComponent<MeshFilter>().sharedMesh = PrimitiveKit.BoxMesh;
                jamb.AddComponent<MeshRenderer>().sharedMaterial = PrimitiveKit.Lit(new Color(0.9f, 0.9f, 0.88f), 0.2f);
                jamb.transform.localScale = new Vector3(0.1f, 2.1f, 0.1f);
                jamb.transform.position = new Vector3(x, 1.05f, 0f);
            }
            NewDog(new Vector3(0f, 0f, -0.1f), 0f);
            NewDog(new Vector3(-0.15f, 0f, -1.2f), 35f);
            cam = Stage();
            Render(cam, new Vector3(0f, 4.2f, -0.45f), new Vector3(0f, 0f, -0.45f), Path.Combine(dir, "door_top.png"));
        }

        /// <summary>Close views of the fur's direction (flank, back, legs) and of the face, the dog alone facing +z.</summary>
        private static void Fur(string dir)
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Floor(4f, 4f, new Color32(0xD8, 0xD4, 0xCC, 0xFF));
            NewDog(Vector3.zero, 0f);
            Camera cam = Stage();
            Render(cam, new Vector3(1.05f, 0.42f, 0.05f), new Vector3(0f, 0.36f, 0.05f), Path.Combine(dir, "fur_flank.png"));
            Render(cam, new Vector3(0.25f, 1.35f, 0.0f), new Vector3(0f, 0.3f, 0.05f), Path.Combine(dir, "fur_back.png"));
            Render(cam, new Vector3(0.75f, 0.2f, 0.45f), new Vector3(0f, 0.15f, 0.1f), Path.Combine(dir, "fur_legs.png"));
            Render(cam, new Vector3(0.1f, 0.5f, 1.15f), new Vector3(0f, 0.5f, 0.35f), Path.Combine(dir, "face_front.png"));
            Render(cam, new Vector3(-0.75f, 0.62f, 0.95f), new Vector3(0f, 0.42f, 0.15f), Path.Combine(dir, "face_three_quarter.png"));
            Render(cam, new Vector3(-0.9f, 0.55f, -1.2f), new Vector3(0f, 0.35f, 0f), Path.Combine(dir, "rear_three_quarter.png"));
            // The game camera's distance and pitch (Tuning.OrbitDistance, PitchDefault), three quarters ahead of the dog.
            Vector3 target = new Vector3(0f, 0.3f, 0.1f);
            Vector3 eye = target - Quaternion.Euler(Tuning.PitchDefault, 200f, 0f) * Vector3.forward * Tuning.OrbitDistance;
            cam.fieldOfView = 55f;
            Render(cam, eye, target, Path.Combine(dir, "game_distance.png"));
            cam.fieldOfView = 40f;
        }

        private static void Drag(string dir)
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Floor(6f, 6f, new Color32(0xB0, 0x7A, 0x4E, 0xFF));
            ModelCatalog.Entry entry = ModelCatalog.Lookup(DogModel);
            float near = Tuning.CarryForward - 0.5f * 0.45f;
            // The dog's root at the origin facing +z, biting; its model stepped back by Inhabitant.DogHoldBack's formula
            // (InhabitantRig.SnoutReach: the rest reach plus what the grown head adds ahead of the head bone).
            GameObject dog = NewDog(Vector3.zero, 0f, 1f);
            float reach = ModelKit.ForwardReach(entry);
            float snout = reach + (Tuning.DogHeadScale - 1f) * Mathf.Max(0f, reach - HeadForward);
            float holdBack = Mathf.Max(0f, snout - near);
            dog.transform.position = new Vector3(0f, 0f, -holdBack);
            Debug.Log($"[DogShots] drag: snout reach {snout:0.000} m (rest {reach:0.000}), chair near edge {near:0.000} m, hold back {holdBack:0.000} m");
            var chair = new GameObject("Chair");
            chair.transform.SetPositionAndRotation(new Vector3(0f, Tuning.DogDragLift, Tuning.CarryForward), Quaternion.identity);
            ModelKit.Instantiate(ModelCatalog.KenneyChair, chair.transform, new Vector3(0.45f, 0.9f, 0.45f), ModelFit.Box, new ModelPaint { Main = Red, Red = Red });
            Camera cam = Stage();
            Render(cam, new Vector3(2.6f, 0.7f, 0.2f), new Vector3(0f, 0.35f, 0.2f), Path.Combine(dir, "drag_side.png"));
            Render(cam, new Vector3(1.6f, 1.5f, 1.9f), new Vector3(0f, 0.35f, 0.15f), Path.Combine(dir, "drag_front.png"));
            Render(cam, new Vector3(0.9f, 0.55f, 0.75f), new Vector3(0f, 0.4f, 0.1f), Path.Combine(dir, "bite_close.png"));
            Render(cam, new Vector3(-0.75f, 0.5f, 0.2f), new Vector3(0f, 0.42f, 0.05f), Path.Combine(dir, "bite_left.png"));
            // The same dog not biting, from the same place (the head's roll and the open jaw against the rest).
            NewDog(new Vector3(2f, 0f, -holdBack), 0f, 0f);
            Render(cam, new Vector3(1.25f, 0.5f, 0.2f), new Vector3(2f, 0.42f, 0.05f), Path.Combine(dir, "bite_left_rest.png"));
            NewDog(new Vector3(-2f, 0f, -holdBack), 0f, 1f);
            Render(cam, new Vector3(-1.2f, 0.5f, 0.75f), new Vector3(-2f, 0.42f, 0.05f), Path.Combine(dir, "bite_alone.png"));
            Vector3 target = new Vector3(0f, 0.3f, 0.1f);
            Vector3 eye = target - Quaternion.Euler(Tuning.PitchDefault, 240f, 0f) * Vector3.forward * Tuning.OrbitDistance;
            cam.fieldOfView = 55f;
            Render(cam, eye, target, Path.Combine(dir, "drag_game.png"));
        }

        private static void ShootLevel(string dir, string id)
        {
            LevelDef def = LevelJson.Parse(File.ReadAllText(Path.Combine(LevelAudit.LevelsFolder, id + ".json")));
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            LevelInstance level = LevelBuilder.Build(def);
            try
            {
                Inhabitant dog = level.Inhabitants.Find(h => h != null && h.IsDog);
                if (dog == null)
                {
                    Debug.LogWarning($"[DogShots] {id}: no dog");
                    return;
                }
                Camera cam = Stage();
                cam.fieldOfView = 55f;
                var fader = level.Root.GetComponent<WallFader>();
                Vector3 target = dog.transform.position + Vector3.up * 0.3f;
                float yaw = dog.transform.eulerAngles.y;
                Debug.Log($"[DogShots] {id}: dog at {dog.transform.position}, model {(dog.Rig != null ? dog.Rig.Entry.id : "none")}, tinted slots {dog.TintedSlots}");
                foreach ((string side, float offset) in new[] { ("a", 140f), ("b", -100f) })
                {
                    Quaternion orbit = Quaternion.Euler(Tuning.PitchDefault, yaw + offset, 0f);
                    Vector3 eye = target - orbit * Vector3.forward * Tuning.OrbitDistance;
                    Render(cam, eye, target, Path.Combine(dir, $"{id}_game_{side}.png"), fader);
                }
                cam.fieldOfView = 40f;
                Quaternion turn = Quaternion.Euler(0f, yaw, 0f);
                Render(cam, target + turn * new Vector3(1.0f, 0.55f, 1.1f), target, Path.Combine(dir, $"{id}_close.png"), fader);
            }
            finally
            {
                LevelBuilder.Teardown(level);
            }
        }

        private static Camera Stage()
        {
            var sun = new GameObject("Sun").AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.color = new Color(1f, 0.87f, 0.67f);
            sun.intensity = 1.35f;
            sun.shadows = LightShadows.Soft;
            sun.shadowStrength = 0.78f;
            sun.transform.rotation = Quaternion.Euler(50f, 20f, 0f);
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.58f, 0.63f, 0.73f);
            RenderSettings.ambientEquatorColor = new Color(0.52f, 0.47f, 0.42f);
            RenderSettings.ambientGroundColor = new Color(0.28f, 0.23f, 0.19f);
            var cam = new GameObject("ShotCamera").AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.15f, 0.16f, 0.19f);
            cam.fieldOfView = 40f;
            cam.nearClipPlane = 0.03f;
            cam.farClipPlane = 80f;
            // The first render of a fresh editor comes out tinted while the shaders warm up: throw one away.
            var warm = new RenderTexture(64, 64, 24);
            cam.targetTexture = warm;
            cam.Render();
            cam.targetTexture = null;
            UnityEngine.Object.DestroyImmediate(warm);
            return cam;
        }

        private static void Render(Camera cam, Vector3 position, Vector3 look, string file, WallFader fader = null)
        {
            cam.transform.SetPositionAndRotation(position, Quaternion.LookRotation(look - position));
            if (fader != null)
            {
                fader.Apply(position);
                fader.DrawFaded(cam);
            }
            var rt = new RenderTexture(1280, 800, 24) { antiAliasing = 4 };
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
            tex.Apply();
            File.WriteAllBytes(file, tex.EncodeToPNG());
            RenderTexture.active = null;
            cam.targetTexture = null;
            UnityEngine.Object.DestroyImmediate(rt);
            UnityEngine.Object.DestroyImmediate(tex);
            Debug.Log($"[DogShots] {file}");
        }

        private static string Arg(string flag)
        {
            string[] args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == flag)
                {
                    return args[i + 1];
                }
            }
            return null;
        }
    }
}
