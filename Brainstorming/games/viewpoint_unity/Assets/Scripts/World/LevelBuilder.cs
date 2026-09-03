using System.Collections.Generic;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// Turns a LevelDef into GameObjects under a level root (PRD section 5.8).
    /// Everything a level owns lives under that root, so unloading a level is
    /// destroying the root's children, placed photo content included.
    ///
    /// This is the only place where authored level data crosses from design
    /// space into Unity space: every position goes through DesignSpace.ToUnity
    /// at the moment it is set, and nowhere else. Sizes are never mirrored.
    /// </summary>
    public static class LevelBuilder
    {
        public static Teleporter Build(Transform root, LevelDef def)
        {
            if (root == null || def == null)
            {
                Debug.LogError("LevelBuilder.Build needs a root and a definition.");
                return null;
            }

            if (def.Platforms != null)
            {
                for (int i = 0; i < def.Platforms.Count; i++)
                {
                    AddPlatform(root, def.Platforms[i]);
                }
            }

            if (def.Decor != null)
            {
                for (int i = 0; i < def.Decor.Count; i++)
                {
                    AddDecor(root, def.Decor[i]);
                }
            }

            if (def.Erasables != null)
            {
                for (int i = 0; i < def.Erasables.Count; i++)
                {
                    AddErasable(root, def.Erasables[i]);
                }
            }

            if (def.Cages != null)
            {
                for (int i = 0; i < def.Cages.Count; i++)
                {
                    AddCage(root, def.Cages[i]);
                }
            }

            if (def.Photos != null)
            {
                for (int i = 0; i < def.Photos.Count; i++)
                {
                    AddPhotoItem(root, def.Photos[i]);
                }
            }

            if (def.Batteries != null)
            {
                for (int i = 0; i < def.Batteries.Count; i++)
                {
                    AddBattery(root, def.Batteries[i], false);
                }
            }

            if (def.SealedBatteries != null)
            {
                // Same battery, same value to a teleporter, but no film prints it.
                for (int i = 0; i < def.SealedBatteries.Count; i++)
                {
                    AddBattery(root, def.SealedBatteries[i], true);
                }
            }

            if (def.Camera != null)
            {
                AddCamera(root, def.Camera);
            }

            IReadOnlyList<IslandDef> islands = LevelDefs.DecorIslands;
            if (islands != null)
            {
                for (int i = 0; i < islands.Count; i++)
                {
                    AddIsland(root, islands[i]);
                }
            }

            if (def.Teleporter == null)
            {
                Debug.LogError("LevelBuilder: level \"" + def.Name + "\" has no teleporter.");
                return null;
            }
            GameObject exit = NewObject("Teleporter");
            Teleporter teleporter = exit.AddComponent<Teleporter>();
            teleporter.Setup(def.Teleporter.Required);
            Place(exit, root, def.Teleporter.Pos);
            return teleporter;
        }

        /// Ground. Grey by default and PERMANENT: a photo placed over it is
        /// added to it, the slab stays. A "soft" platform is pale instead and
        /// the frame carves it like a lavender wall: that is the whole
        /// language, said in color.
        static void AddPlatform(Transform root, PlatformDef platform)
        {
            string[] groups = platform.Soft
                ? new string[] { Groups.Platform, Groups.Erasable }
                : new string[] { Groups.Platform };
            ErasableBlock block = ErasableBlock.Create(
                platform.Size,
                platform.Soft ? "platform_soft" : "platform",
                0f,
                groups,
                platform.Soft);
            block.gameObject.name = platform.Soft ? "PlatformSoft" : "Platform";
            Place(block.gameObject, root, platform.Pos);

            // Sand-colored skirt hanging under the slab, so islands read as
            // terrain. Child of the block: it vanishes with the block, and
            // carved fragments have none.
            MakeBox(
                "Skirt",
                block.transform,
                new Vector3(platform.Size.x * 0.9f, platform.Size.y * 1.6f, platform.Size.z * 0.9f),
                new Vector3(0f, -platform.Size.y * 1.1f, 0f),
                Materials.Solid(platform.Soft ? "platform_soft_side" : "platform_side"));
        }

        /// Decor is part of the fixed world: photographable, permanent, never
        /// carved, like the grey ground. The thin tinted slabs are the
        /// placement markers; their photo, aim and roll fields are read by the
        /// design audit and change nothing here.
        static void AddDecor(Transform root, DecorDef decor)
        {
            string color = string.IsNullOrEmpty(decor.Color) ? "wood" : decor.Color;
            ErasableBlock block = ErasableBlock.Create(decor.Size, color, 0f, null, false);
            block.gameObject.name = "Decor";
            Place(block.gameObject, root, decor.Pos);
        }

        /// The "erasable" group is only a lavender marker (readability and
        /// tests): every block of the ephemeral half is carvable anyway.
        static void AddErasable(Transform root, ErasableDef erasable)
        {
            ErasableBlock block = ErasableBlock.Create(
                erasable.Size,
                "erasable",
                0.25f,
                new string[] { Groups.Erasable },
                true);
            block.gameObject.name = "Erasable";
            Place(block.gameObject, root, erasable.Pos);
        }

        static void AddCage(Transform root, CageDef cage)
        {
            Cage body = Cage.Create(cage.Size, cage.Erasable, cage.Roof, cage.Sealed);
            // pos is the center of the cage FLOOR; the body sits half a cage
            // higher, on the volumetric center the breakable test reads.
            Place(body.gameObject, root, cage.Pos + new Vector3(0f, cage.Size.y * 0.5f, 0f));
        }

        static void AddPhotoItem(Transform root, PhotoPlacementDef photo)
        {
            if (string.IsNullOrEmpty(photo.Id))
            {
                Debug.LogError("LevelBuilder: a photo placement has no id.");
                return;
            }
            GameObject go = NewObject("PhotoItem");
            PhotoItem item = go.AddComponent<PhotoItem>();
            item.Setup(photo.Id);
            Place(go, root, photo.Pos);
        }

        static void AddBattery(Transform root, Vector3 pos, bool isSealed)
        {
            GameObject go = NewObject(isSealed ? "SealedBattery" : "Battery");
            Battery battery = go.AddComponent<Battery>();
            battery.Setup(isSealed);
            Place(go, root, pos);
        }

        static void AddCamera(Transform root, CameraDef camera)
        {
            GameObject go = NewObject("CameraItem");
            CameraItem item = go.AddComponent<CameraItem>();
            item.Setup(camera.Films);
            Place(go, root, camera.Pos);
        }

        /// Scenery beyond the world: mesh only, no collision, no group. The
        /// camera must not photograph them and the player must never land on
        /// one.
        static void AddIsland(Transform root, IslandDef island)
        {
            MakeBox("DecorIsland", root, island.Size, island.Pos, Materials.Solid("platform_side"));
            MakeBox(
                "DecorIslandTop",
                root,
                new Vector3(island.Size.x * 1.05f, 0.3f, island.Size.z * 1.05f),
                island.Pos + new Vector3(0f, island.Size.y * 0.5f + 0.1f, 0f),
                Materials.Solid("platform"));
        }

        /// A GameObject that is not live yet: Setup must run, and the position
        /// must be set, before the component builds itself and registers its
        /// groups on enable (several of them read their own position to pick
        /// an idle phase).
        static GameObject NewObject(string name)
        {
            GameObject go = new GameObject(name);
            go.SetActive(false);
            return go;
        }

        /// Parents a finished object under the level root, converts its
        /// authored position once, then wakes it up.
        static void Place(GameObject go, Transform root, Vector3 designPos)
        {
            go.transform.SetParent(root, false);
            go.transform.localPosition = DesignSpace.ToUnity(designPos);
            go.SetActive(true);
        }

        /// A plain visible box: no collider, no group, nothing to interact
        /// with. Used for the platform skirts and the decor islands.
        static GameObject MakeBox(string name, Transform parent, Vector3 size, Vector3 designLocalPos, Material material)
        {
            GameObject box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.name = name;
            box.layer = Layers.World;

            // CreatePrimitive hands out a collider these boxes must not have.
            // This runs while the box is being built, never on a live world
            // object, so it is not a removal in the sense of Rewind.Retire.
            // Disabling comes first because Destroy only bites at the end of the
            // frame: a level built from Start would otherwise expose these
            // skirts and islands to the frame's physics steps as solid ground
            // (the same order Teleporter.SpawnPart uses).
            Collider extra = box.GetComponent<Collider>();
            if (extra != null)
            {
                extra.enabled = false;
                if (Application.isPlaying)
                {
                    UnityEngine.Object.Destroy(extra);
                }
                else
                {
                    UnityEngine.Object.DestroyImmediate(extra);
                }
            }

            box.transform.SetParent(parent, false);
            box.transform.localPosition = DesignSpace.ToUnity(designLocalPos);
            // The primitive cube is one meter on every axis, so the scale IS
            // the size.
            box.transform.localScale = size;
            box.GetComponent<MeshRenderer>().sharedMaterial = material;
            return box;
        }
    }
}
