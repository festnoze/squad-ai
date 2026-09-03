using System.Collections.Generic;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// Holds the photo the player carries and turns it into world geometry.
    ///
    /// This component sits on a child of the player camera whose local
    /// transform is identity apart from the roll, so its world transform IS the
    /// placement anchor (PRD 6.4): eye position, full yaw and pitch, plus the
    /// roll. There is no 3D ghost preview and this object owns no child: the
    /// player raises the 2D picture (right click), turns it (wheel), and only
    /// discovers the 3D result at placement.
    /// </summary>
    public sealed class PhotoPlacer : MonoBehaviour
    {
        /// <summary>Where the dropped photo lands, PRD 6.8.</summary>
        private const float DropForward = 1.4f;
        private const float DropDownward = 0.4f;

        private Transform _levelRoot;

        /// <summary>Id of the photo in hand, "" when the hand is empty.</summary>
        public string HeldId { get; private set; } = "";

        /// <summary>Roll of the held photo around the view axis, 0 to 3 steps
        /// of 90 degrees. Applied to this object itself, so the anchor turns
        /// with the picture the HUD shows.</summary>
        public int RollSteps { get; private set; }

        /// <summary>True while the photo is raised to the eye (right click).
        /// The HUD then draws the picture over the exact screen region the
        /// placement frustum covers (PRD 12.2).</summary>
        public bool Raised { get; private set; }

        private void Awake()
        {
            // The world transform of this object is the anchor, so its local
            // transform must stay identity apart from the roll.
            transform.localPosition = Vector3.zero;
            transform.localScale = Vector3.one;
            SetRoll(RollSteps);
        }

        public void Setup(Transform levelRoot)
        {
            _levelRoot = levelRoot;
        }

        /// <summary>Takes a photo in hand. Fails when the hand is full or the
        /// id is unknown (PRD 6.8).</summary>
        public bool Hold(string id)
        {
            if (!string.IsNullOrEmpty(HeldId) || string.IsNullOrEmpty(id))
            {
                return false;
            }
            if (PhotoDefs.GetDef(id) == null)
            {
                return false;
            }
            HeldId = id;
            SetRoll(0);
            return true;
        }

        /// <summary>Turns the held photo by steps of 90 degrees (mouse wheel):
        /// direction +1 is wheel down, one quarter turn clockwise on screen.
        /// </summary>
        public void RotateHeld(int direction)
        {
            if (string.IsNullOrEmpty(HeldId))
            {
                return;
            }
            // C# modulo keeps the sign of the dividend, unlike Godot's posmod:
            // a wheel step up from roll 0 would land on -1 without this.
            SetRoll(((RollSteps + direction) % 4 + 4) % 4);
        }

        /// <summary>Raises or lowers the held photo (right click).</summary>
        public void RaiseToggle()
        {
            if (string.IsNullOrEmpty(HeldId))
            {
                return;
            }
            Raised = !Raised;
        }

        /// <summary>
        /// Materializes the held photo at the current anchor, PRD 6.5: the
        /// frustum content is REPLACED, then the photo content is built.
        /// Returns false when the hand is empty.
        /// </summary>
        public bool Place()
        {
            if (string.IsNullOrEmpty(HeldId))
            {
                return false;
            }
            PhotoDef def = PhotoDefs.GetDef(HeldId);
            if (def == null)
            {
                return false;
            }
            if (_levelRoot == null)
            {
                // Setup was never called: the content would be parented to the
                // scene root and survive the next level load.
                Debug.LogError("PhotoPlacer.Place without a level root: call Setup first.");
                return false;
            }

            Vector3 anchorPosition = transform.position;
            Quaternion anchorRotation = transform.rotation;
            // Rebuilt rather than read from worldToLocalMatrix so that a scale
            // anywhere on the camera rig can never leak into the frustum test.
            Matrix4x4 anchorInverse = Matrix4x4.TRS(anchorPosition, anchorRotation, Vector3.one).inverse;
            // A missing depth means the catalog default, as in the original.
            float depth = def.EraseDepth > 0f ? def.EraseDepth : PhotoMath.DefaultEraseDepth;

            // Pass 1, carve: every carvable block (platforms, decor, lavender,
            // placed content, backdrops) loses the part of its volume caught in
            // the frustum and survives as fragments. The list is a snapshot, so
            // the fragments spawned during the pass are not revisited.
            List<ErasableBlock> carvables = Groups.Snapshot<ErasableBlock>(Groups.Carvable);
            for (int i = 0; i < carvables.Count; i++)
            {
                ErasableBlock block = carvables[i];
                if (block == null || !block.gameObject.activeInHierarchy)
                {
                    continue;
                }
                block.CarveWithFrustum(anchorInverse, PhotoMath.PhotoFovDeg, PhotoMath.PhotoAspect, depth);
            }

            // Pass 2, break: every breakable body (cages) whose origin falls in
            // the frustum vanishes whole. Never replaced: the teleporter, the
            // batteries, the photo items, the camera, the player, and the loose
            // rigid bodies, which is what lets a stack of crates survive.
            List<Component> breakables = Groups.Snapshot<Component>(Groups.Breakable);
            for (int i = 0; i < breakables.Count; i++)
            {
                Component body = breakables[i];
                if (body == null || !body.gameObject.activeInHierarchy)
                {
                    continue;
                }
                Vector3 localUnity = anchorInverse.MultiplyPoint3x4(body.transform.position);
                // PhotoMath reads design space (-z forward) and the z mirror is
                // its own inverse, so the same call takes an anchor-space point
                // back into photo space.
                Vector3 localPhoto = DesignSpace.ToUnity(localUnity);
                if (PhotoMath.PointInFrustum(localPhoto, PhotoMath.PhotoFovDeg, PhotoMath.PhotoAspect, 0f, depth))
                {
                    Rewind.Retire(body.gameObject);
                }
            }

            GameObject contentObject = new GameObject("PhotoContent");
            contentObject.transform.SetParent(_levelRoot, false);
            // The world transform is set before the content builds itself, so
            // the rigid bodies it spawns start life at the right place.
            contentObject.transform.SetPositionAndRotation(anchorPosition, anchorRotation);
            PhotoContent content = contentObject.AddComponent<PhotoContent>();
            content.Setup(def, false);
            Rewind.NoticeSpawn(contentObject);

            ClearHeld();
            return true;
        }

        /// <summary>Puts the held photo back into the world as a pickable item
        /// in front of the player, so no photo is ever lost (PRD 6.8).
        /// </summary>
        public bool Drop()
        {
            if (string.IsNullOrEmpty(HeldId))
            {
                return false;
            }
            if (_levelRoot == null)
            {
                Debug.LogError("PhotoPlacer.Drop without a level root: call Setup first.");
                return false;
            }

            // This object sits at the eye and the roll turns it about the view
            // axis, which leaves that axis alone: its forward IS the camera's.
            Vector3 eye = transform.position;
            Vector3 flatForward = transform.forward;
            flatForward.y = 0f;
            // Vector3.forward is the mirror of the original's Vector3.FORWARD:
            // the fallback matters only when the player looks straight down.
            flatForward = flatForward.magnitude > 0.01f ? flatForward.normalized : Vector3.forward;

            GameObject itemObject = new GameObject("PhotoItem");
            itemObject.transform.SetParent(_levelRoot, false);
            itemObject.transform.position = eye + flatForward * DropForward - new Vector3(0f, DropDownward, 0f);
            PhotoItem item = itemObject.AddComponent<PhotoItem>();
            item.Setup(HeldId);
            Rewind.NoticeSpawn(itemObject);

            ClearHeld();
            return true;
        }

        /// <summary>Title of the held photo, "" when the hand is empty.
        /// </summary>
        public string HeldTitle()
        {
            if (string.IsNullOrEmpty(HeldId))
            {
                return "";
            }
            PhotoDef def = PhotoDefs.GetDef(HeldId);
            if (def != null && !string.IsNullOrEmpty(def.Title))
            {
                return def.Title;
            }
            return HeldId;
        }

        /// <summary>Puts the hand back where a rewind sample found it: a photo
        /// placed a moment ago is in hand again, lowered (PRD 10).</summary>
        public void RestoreHeld(string id, int roll)
        {
            string wanted = id == null ? "" : id;
            if (HeldId != wanted)
            {
                HeldId = wanted;
                Raised = false;
            }
            SetRoll(roll);
        }

        private void ClearHeld()
        {
            HeldId = "";
            Raised = false;
            SetRoll(0);
        }

        private void SetRoll(int steps)
        {
            RollSteps = steps;
            transform.localRotation = RollRotation(steps);
        }

        /// <summary>
        /// THE ONE DIRECTION OF THE WHEEL. One step down turns the picture 90
        /// degrees CLOCKWISE as the player sees it, and that has to be true of
        /// the world as well as of the HUD, or the promise of the game is
        /// broken: what you see raised is what you place (PRD 6.4, D1).
        ///
        /// The minus is a derivation, not a taste. In Unity a positive rotation
        /// about an axis reads clockwise when seen from the positive end of
        /// that axis looking back at the origin (Quaternion.Euler(0, 90, 0)
        /// turns forward into right, clockwise seen from above). This object is
        /// a child of the camera, so its local +z is the view direction, aimed
        /// AWAY from the player: the player watches that axis from its negative
        /// end, where the same positive rotation reads counter-clockwise.
        /// Hence -90 degrees per step to read clockwise on screen.
        ///
        /// Check against the test of PRD 6.4: at one step, a prop offset of
        /// (1.6, -0.6) must land at (-0.6, -1.6). With cos(-90) = 0 and
        /// sin(-90) = -1, x' = x cos - y sin = y = -0.6 and
        /// y' = x sin + y cos = -x = -1.6. It holds. At two steps the offset
        /// is simply negated, (-1.6, +0.6), which is the other half of the
        /// same test.
        /// </summary>
        public static Quaternion RollRotation(int steps)
        {
            return Quaternion.AngleAxis(-90f * steps, Vector3.forward);
        }
    }
}
