using System.Collections.Generic;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// The port of Godot scene groups: a flat, static, name to member registry.
    /// PRD section 15.3.
    ///
    /// Members register in OnEnable and unregister in OnDisable, never in Awake or
    /// OnDestroy. That is not a detail: nothing is destroyed during a level, and
    /// Rewind.Retire removes an object by parenting it to an inactive graveyard and
    /// deactivating it. Only OnDisable runs then, so only OnDisable takes the
    /// object out of every group the way a real free would, while leaving it whole
    /// for a rewind to put back.
    ///
    /// Insertion order is preserved on purpose. PhotoCapture caps a shot at 32
    /// props, so a stable order keeps a capture reproducible from one run to the
    /// next.
    /// </summary>
    public static class Groups
    {
        public const string Photographable = "photographable";
        public const string Carvable = "carvable";
        public const string Breakable = "breakable";
        public const string Cage = "cage";
        public const string Erasable = "erasable";
        public const string Platform = "platform";
        public const string PlacedContent = "placed_content";
        public const string PhotoItem = "photo_item";
        public const string Battery = "battery";
        public const string CopyableBattery = "copyable_battery";
        public const string CameraItem = "camera_item";
        public const string Teleporter = "teleporter";

        private static readonly Dictionary<string, List<Component>> Members =
            new Dictionary<string, List<Component>>();

        /// <summary>
        /// Registers a member. Idempotent per (component, group): a Retire followed
        /// by a rewind restore runs OnEnable a second time, and a double entry would
        /// let the same block be carved or captured twice.
        /// </summary>
        public static void Add(Component c, string group)
        {
            if (c == null || string.IsNullOrEmpty(group))
            {
                return;
            }

            List<Component> list;
            if (!Members.TryGetValue(group, out list))
            {
                list = new List<Component>();
                Members[group] = list;
            }

            for (int i = 0; i < list.Count; i++)
            {
                // ReferenceEquals, not ==: Unity's operator would report two already
                // destroyed objects as equal and swallow a legitimate registration.
                if (ReferenceEquals(list[i], c))
                {
                    return;
                }
            }

            list.Add(c);
        }

        /// <summary>Unregisters a member. Silent when the member or the group is absent.</summary>
        public static void Remove(Component c, string group)
        {
            if (c == null || string.IsNullOrEmpty(group))
            {
                return;
            }

            List<Component> list;
            if (!Members.TryGetValue(group, out list))
            {
                return;
            }

            for (int i = 0; i < list.Count; i++)
            {
                if (ReferenceEquals(list[i], c))
                {
                    list.RemoveAt(i);
                    return;
                }
            }
        }

        /// <summary>
        /// A FRESH list of the live, active members of a group that are a T. A fresh
        /// list is required, not an enumerator: callers mutate the world while they
        /// walk it (carving spawns fragments, placing retires cages), and a snapshot
        /// is what makes "fragments spawned during the pass are not revisited" true.
        /// Dead entries are pruned as we walk, otherwise a level reload leaks.
        /// </summary>
        public static List<T> Snapshot<T>(string group) where T : Component
        {
            List<T> result = new List<T>();

            List<Component> list;
            if (string.IsNullOrEmpty(group) || !Members.TryGetValue(group, out list))
            {
                return result;
            }

            int write = 0;
            for (int read = 0; read < list.Count; read++)
            {
                Component c = list[read];
                // Unity's == reports a destroyed object as null. Such an entry can only
                // come from a real Destroy (a level unload), so drop it for good.
                if (c == null)
                {
                    continue;
                }

                list[write] = c;
                write++;

                // Deactivated means retired: out of the world, out of every group,
                // until a rewind puts it back.
                if (!c.gameObject.activeInHierarchy)
                {
                    continue;
                }

                T typed = c as T;
                if (typed != null)
                {
                    result.Add(typed);
                }
            }

            if (write < list.Count)
            {
                list.RemoveRange(write, list.Count - write);
            }

            return result;
        }

        /// <summary>
        /// How many live, active members a group holds, over the same set Snapshot
        /// walks and pruned the same way. No type filter: it counts every member.
        /// </summary>
        public static int Count(string group)
        {
            List<Component> list;
            if (string.IsNullOrEmpty(group) || !Members.TryGetValue(group, out list))
            {
                return 0;
            }

            int alive = 0;
            int write = 0;
            for (int read = 0; read < list.Count; read++)
            {
                Component c = list[read];
                if (c == null)
                {
                    continue;
                }

                list[write] = c;
                write++;

                if (c.gameObject.activeInHierarchy)
                {
                    alive++;
                }
            }

            if (write < list.Count)
            {
                list.RemoveRange(write, list.Count - write);
            }

            return alive;
        }

        /// <summary>
        /// Forgets every group, destroying nothing. Mandatory when a level is
        /// unloaded, and not merely hygiene: the original freed the old level's
        /// nodes immediately (main.gd) precisely so that the groups were empty
        /// before the new level queried them, while Unity defers Destroy, and with
        /// it OnDisable, to the end of the frame. Without this call LevelBuilder
        /// would run with every group still holding the level just left.
        /// </summary>
        public static void Clear()
        {
            Members.Clear();
        }

        /// <summary>
        /// Entering play mode must start from an empty registry. Static state
        /// survives a domain reload when the editor is set to disable it, and a
        /// leftover entry from the previous session would poison the first capture.
        /// </summary>
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetOnEnterPlayMode()
        {
            Members.Clear();
        }
    }

    /// <summary>
    /// What the interaction raycast can act on. Implemented by PhotoItem, Battery,
    /// CameraItem and Teleporter. Their trigger colliders sit on the Interact layer
    /// with the component on the same GameObject or on its parent (PRD 15.3).
    /// </summary>
    public interface IInteractable
    {
        void Interact(PlayerController player);

        /// <summary>The French line the HUD shows while the object is aimed at.</summary>
        string PromptText(PlayerController player);
    }
}
