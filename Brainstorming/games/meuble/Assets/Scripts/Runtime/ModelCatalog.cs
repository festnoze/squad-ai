using System;
using System.Collections.Generic;
using UnityEngine;

namespace Meuble
{
    /// <summary>
    /// Model catalog (docs/CONTRACT_M3.md 3), at Assets/Resources/ModelCatalog.asset, built by
    /// Meuble.Editor.ModelCatalogBuilder. Being referenced from Resources is what ships the GLBs in the player.
    ///
    /// Every size and position is in the model's native root space (root at the origin, no rotation, unit
    /// scale), measured from the imported prefab, never typed by hand. Only the yaw offsets of the static
    /// models come from the contract table: facing cannot be measured from bounds.
    /// </summary>
    public sealed class ModelCatalog : ScriptableObject
    {
        public const string ResourcePath = "ModelCatalog";

        [Serializable]
        public sealed class Entry
        {
            public string id;
            /// <summary>The imported GLB main asset.</summary>
            public GameObject prefab;
            /// <summary>Size of the renderer bounds, unrotated (a skinned model: its baked rest pose).</summary>
            public Vector3 nativeSize;
            /// <summary>Center of those bounds: recentres Kenney's corner pivot.</summary>
            public Vector3 boundsCenter;
            /// <summary>Yaw (multiple of 90) that turns the model to face +z like the procedural visual it replaces.</summary>
            public float yawOffset;
            public bool rigged;
            /// <summary>Rigged only: name of the head bone in the skeleton.</summary>
            public string headBone;
            /// <summary>Rigged only: centroid of the eyes in head bone space.</summary>
            public Vector3 eyeLocal;
            /// <summary>Rigged only: height of the eyes above the root, native units (mean over the Idle clip).</summary>
            public float eyeHeight;

            // ----- M5 (docs/CONTRACT_M5_v3.md 15.5, CONTRACT_M5 3) -----

            /// <summary>"human" or "pet" for a character (rigged) model; empty for a static model.</summary>
            public string kind;

            /// <summary>
            /// The height ModelKit's Uniform fit puts the eyes at, metres above the root: 0 means Tuning.EyeHeight (the humans);
            /// the dog's is Tuning.DogEyeHeight.
            /// </summary>
            public float targetEyeHeight;

            /// <summary>
            /// Pets only, the clip map: the exact state names of Idle and Walk (a pet has no "_Jump": Startled falls back to
            /// Idle, and it never sits). Empty for the humans, whose clips InhabitantRig finds by suffix.
            /// </summary>
            public string idleClip;
            public string walkClip;

            public bool IsHuman => kind == KindHuman;
            public bool IsPet => kind == KindPet;

            /// <summary>The eye height of the fitted model above its root: <see cref="targetEyeHeight"/>, or Tuning.EyeHeight.</summary>
            public float TargetEye => targetEyeHeight > 0f ? targetEyeHeight : Meuble.Core.Tuning.EyeHeight;
        }

        /// <summary>The kinds of a character entry (M5).</summary>
        public const string KindHuman = "human";
        public const string KindPet = "pet";

        public List<Entry> entries = new List<Entry>();

        public Entry Find(string id)
        {
            if (string.IsNullOrEmpty(id))
            {
                return null;
            }
            foreach (Entry e in entries)
            {
                if (e != null && e.id == id)
                {
                    return e;
                }
            }
            return null;
        }

        private static ModelCatalog loaded;

        /// <summary>The catalog in Resources, or null when it does not exist yet.</summary>
        public static ModelCatalog Load()
        {
            if (loaded == null)
            {
                loaded = Resources.Load<ModelCatalog>(ResourcePath);
            }
            return loaded;
        }

        /// <summary>The entry of <paramref name="id"/> in the catalog of Resources, or null.</summary>
        public static Entry Lookup(string id)
        {
            ModelCatalog catalog = Load();
            return catalog != null ? catalog.Find(id) : null;
        }

        // ----- The ids of M3 (docs/CONTRACT_M3.md 3) -----

        public const string KenneyChair = "kenney.chair";
        public const string KenneySofa = "kenney.sofa";
        public const string KenneyRug = "kenney.rug";
        public const string KenneyDoormat = "kenney.doormat";
        public const string KenneyArmchair = "kenney.armchair";
        public const string KenneyStool = "kenney.stool";
        public const string KenneyFloorLamp = "kenney.floorlamp";
        public const string QuaterniusMan = "quaternius.man";
        public const string QuaterniusWoman = "quaternius.woman";

        // ----- M5 (docs/CONTRACT_M5.md 3 and 16.11): one model per personality, and the dog -----

        /// <summary>The man in a t-shirt and shorts (the dreamer).</summary>
        public const string QuaterniusManShorts = "quaternius.man_shorts";
        /// <summary>The man in a suit (the hurried one).</summary>
        public const string QuaterniusManSuit = "quaternius.man_suit";
        /// <summary>The blond man in a t-shirt (the teen).</summary>
        public const string QuaterniusManTshirt = "quaternius.man_tshirt";
        /// <summary>The woman in a jacket (the watchful one).</summary>
        public const string QuaterniusWomanJacket = "quaternius.woman_jacket";
        /// <summary>The woman in a dress (granny).</summary>
        public const string QuaterniusWomanDress = "quaternius.woman_dress";
        /// <summary>The Shiba Inu (the dog, a pet: 46 bones, eyes at Tuning.DogEyeHeight).</summary>
        public const string QuaterniusShiba = "quaternius.shiba";

        /// <summary>Every id the catalog must resolve, in contract order (M5 appends the personalities' models and the dog).</summary>
        public static readonly string[] Ids =
        {
            KenneyChair, KenneySofa, KenneyRug, KenneyDoormat, KenneyArmchair, KenneyStool, KenneyFloorLamp,
            QuaterniusMan, QuaterniusWoman,
            QuaterniusManShorts, QuaterniusManSuit, QuaterniusManTshirt, QuaterniusWomanJacket, QuaterniusWomanDress, QuaterniusShiba,
        };
    }
}
