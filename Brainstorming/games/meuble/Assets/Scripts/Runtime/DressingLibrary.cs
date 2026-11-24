using System;
using System.Collections.Generic;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// DRESSING (2026-11-24, docs/next/progress/DRESSING.md): the baked meshes of the room dressing, at
    /// Assets/Resources/DressingLibrary.asset, built by OutOfSight.Editor.DressingBuilder from the delivered GLBs (being referenced
    /// from Resources is what ships them). Each mesh is in its GLB's own frame (metres, root on the contact point, Unity axes)
    /// and is drawn with the wall material (<see cref="WallArray"/>): every vertex names either a flat colour (UV1.x
    /// <see cref="WallArray.FlatFinish"/>, UV2 the linear colour) or a dressing slice of the arrays tinted by its vertex colour
    /// (UV1.x slice + 1, UV2.x <see cref="WallArray.DressingTint"/>). So the whole dressing of a level costs no material.
    /// </summary>
    public sealed class DressingLibrary : ScriptableObject
    {
        public const string ResourcePath = "DressingLibrary";

        [Serializable]
        public sealed class Entry
        {
            /// <summary>A <see cref="Core.DecorKinds.Meshes"/> id.</summary>
            public string id;
            public Mesh mesh;
            /// <summary>The mesh bounds, measured at bake time.</summary>
            public Vector3 boundsMin;
            public Vector3 boundsMax;
            public int triangles;

            public Vector3 Size => boundsMax - boundsMin;
        }

        public List<Entry> entries = new List<Entry>();

        /// <summary>The hash of the sources the meshes were baked from (the builder rebakes when it changes).</summary>
        public string sourceHash;

        /// <summary>When true, nothing is dressed: every prop keeps its procedural visual and no decor is built (tests).</summary>
        public static bool Disabled;

        private static DressingLibrary loaded;

        public static DressingLibrary Load()
        {
            if (loaded == null)
            {
                loaded = Resources.Load<DressingLibrary>(ResourcePath);
            }
            return loaded;
        }

        public Entry Find(string id)
        {
            foreach (Entry e in entries)
            {
                if (e != null && e.id == id && e.mesh != null)
                {
                    return e;
                }
            }
            return null;
        }

        /// <summary>The entry of <paramref name="id"/>, or null when dressing is off, the library is missing or the id unknown.</summary>
        public static Entry Lookup(string id)
        {
            if (Disabled)
            {
                return null;
            }
            DressingLibrary library = Load();
            return library != null ? library.Find(id) : null;
        }
    }

    /// <summary>DRESSING: one dressed element of a built level (a decor item, a furniture look, the TV), for the probe and the audit.</summary>
    public sealed class DressingPlacement
    {
        /// <summary>The <see cref="Core.DecorKinds.Meshes"/> id.</summary>
        public string Id;
        /// <summary>The host prop's name.</summary>
        public string Host;
        /// <summary>True for a furniture look or the TV (the prop's visual); false for a decor item.</summary>
        public bool Look;
        /// <summary>The level root space bounds of the placed mesh.</summary>
        public Bounds Bounds;
        /// <summary>The level root space height of the host's top it stands on (a throw: the backrest top).</summary>
        public float HostTop;
    }
}
