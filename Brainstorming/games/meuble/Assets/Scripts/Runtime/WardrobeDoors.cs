using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// M7 polish (docs/CONTRACT_M6.md 2.5): a quick, presentation-only open-slip-close animation for one wardrobe's
    /// two doors (FurnitureKit.Wardrobe's "Door0" and "Door1" boxes), played the instant the entry or exit action
    /// starts (GameState calls <see cref="Begin"/> from the same step as the E press, not at the end of the action),
    /// so the player sees the doors swing open at once instead of waiting for the action to finish.
    /// <list type="bullet">
    /// <item>Visual only: the wardrobe keeps its one whole-box collider and GameState keeps its own hide/show timing
    /// (<see cref="FurnitureController.SetHidden"/>, the rule that matters) exactly as before. This component never
    /// touches a collider and is never read by any rule, the audit included.</item>
    /// <item>Each door swings on its outer hinge (the vertical edge away from the wardrobe's centre line, real
    /// world wardrobe doors): ease-out open to <see cref="Tuning.WardrobeDoorSwingDegrees"/>, a short hold, ease-in
    /// closed, all within <see cref="Tuning.WardrobeActionTime"/> real seconds (Time.deltaTime: a cosmetic animation,
    /// not a fixed step rule).</item>
    /// <item>While it plays, <see cref="FurnitureController.WardrobeSlideOffset"/> nudges the furniture's visual
    /// along the wardrobe's own axis (inward entering, outward leaving) so it visibly slips through the doorway.</item>
    /// <item>Handles (2026-11-19, PRD 7.4 budgets): a combined wardrobe is drawn at rest by its "Closed" and
    /// "ClosedHandles" renderers (FurnitureKit.Wardrobe); its separate body, cornice and doors (their handles with them)
    /// are drawn only while the doors swing, then hidden again.</item>
    /// </list>
    /// </summary>
    public sealed class WardrobeDoors : MonoBehaviour
    {
        /// <summary>The renderers that draw the wardrobe at rest (empty when it was built without combining).</summary>
        private Renderer[] still = new Renderer[0];
        /// <summary>The renderers of the parts that swing (the body and cornice with them), drawn while the doors move.</summary>
        private Renderer[] moving = new Renderer[0];

        /// <summary>Share of the animation spent easing the doors open.</summary>
        private const float OpenShare = 0.4f;
        /// <summary>Normalized time the doors start easing closed again.</summary>
        private const float CloseStart = 0.6f;

        private Transform door0;
        private Transform door1;
        private Vector3 door0ClosedLocalPos;
        private Vector3 door1ClosedLocalPos;
        private float door0HalfWidth;
        private float door1HalfWidth;

        private FurnitureController furniture;
        private bool entering;
        private float elapsed;
        private bool animating;

        /// <summary>
        /// Adds a WardrobeDoors to <paramref name="wardrobeRoot"/> (the prop's own transform, as FurnitureKit.Build
        /// built it) when it finds procedural "Door0" and "Door1" children to animate; null (nothing added) for a
        /// wardrobe shown by a model visual instead, which has no such children.
        /// </summary>
        public static WardrobeDoors Attach(Transform wardrobeRoot)
        {
            Transform d0 = wardrobeRoot.Find("Door0");
            Transform d1 = wardrobeRoot.Find("Door1");
            if (d0 == null || d1 == null)
            {
                return null;
            }
            var doors = wardrobeRoot.gameObject.AddComponent<WardrobeDoors>();
            doors.door0 = d0;
            doors.door1 = d1;
            doors.door0ClosedLocalPos = d0.localPosition;
            doors.door1ClosedLocalPos = d1.localPosition;
            // PrimitiveKit.Box sets localScale to the box size: scale.x is the door's own width.
            doors.door0HalfWidth = d0.localScale.x * 0.5f;
            doors.door1HalfWidth = d1.localScale.x * 0.5f;
            var still = new System.Collections.Generic.List<Renderer>();
            var moving = new System.Collections.Generic.List<Renderer>();
            foreach (Transform child in wardrobeRoot)
            {
                Renderer r = child.GetComponent<Renderer>();
                if (r != null && (child.name == "Closed" || child.name == "ClosedHandles"))
                {
                    still.Add(r);
                }
                else if (child.name == "Body" || child.name == "Cornice" || child == d0 || child == d1)
                {
                    moving.AddRange(child.GetComponentsInChildren<Renderer>(true));
                }
            }
            if (still.Count > 0)
            {
                doors.still = still.ToArray();
                doors.moving = moving.ToArray();
            }
            return doors;
        }

        /// <summary>Shows the swinging parts (<paramref name="swinging"/>) or the wardrobe at rest, never both.</summary>
        private void ShowSwinging(bool swinging)
        {
            if (still.Length == 0)
            {
                return;
            }
            foreach (Renderer r in still)
            {
                if (r != null)
                {
                    r.enabled = !swinging;
                }
            }
            foreach (Renderer r in moving)
            {
                if (r != null)
                {
                    r.enabled = swinging;
                }
            }
        }

        /// <summary>
        /// Starts the entry (furniture slips in) or exit (slips out) animation at once, on the same step as the key
        /// press that began the real action. Restarts from the beginning if one was already playing.
        /// </summary>
        public void Begin(bool isEntering, FurnitureController player)
        {
            entering = isEntering;
            furniture = player;
            elapsed = 0f;
            animating = true;
            ShowSwinging(true);
            Apply(0f);
        }

        private void Update()
        {
            if (!animating)
            {
                return;
            }
            elapsed += Time.deltaTime;
            float t = Mathf.Clamp01(elapsed / Mathf.Max(Tuning.WardrobeActionTime, 0.01f));
            Apply(t);
            if (t >= 1f)
            {
                EndAnimation();
            }
        }

        private void OnDisable()
        {
            animating = false;
            EndAnimation();
            Apply(0f);
        }

        private void EndAnimation()
        {
            animating = false;
            ShowSwinging(false);
            if (furniture != null)
            {
                furniture.WardrobeSlideOffset = Vector3.zero;
            }
            furniture = null;
        }

        /// <summary>Poses both doors and the furniture's slide offset at normalized animation time <paramref name="t"/> (0 to 1).</summary>
        private void Apply(float t)
        {
            float openDegrees = Tuning.WardrobeDoorSwingDegrees * DoorOpenEnvelope(t);
            // Doors swing on their outer hinge, away from each other (CONTRACT_M6 2.5, FurnitureKit.Wardrobe): the
            // left door (Door0, negative local x) opens toward negative angles, the right door (Door1) toward
            // positive ones, mirrored about the wardrobe's centre line.
            PoseDoor(door0, door0ClosedLocalPos, door0HalfWidth, -openDegrees);
            PoseDoor(door1, door1ClosedLocalPos, door1HalfWidth, openDegrees);
            if (furniture != null)
            {
                float slide = entering ? t : 1f - t;
                furniture.WardrobeSlideOffset = -transform.forward * (Tuning.WardrobeSlideDistance * slide);
            }
        }

        /// <summary>0 (closed) to 1 (fully open) door envelope: ease-out open, a short hold, ease-in close.</summary>
        private static float DoorOpenEnvelope(float t)
        {
            if (t < OpenShare)
            {
                float p = t / OpenShare;
                return 1f - (1f - p) * (1f - p);
            }
            if (t < CloseStart)
            {
                return 1f;
            }
            float close = (t - CloseStart) / (1f - CloseStart);
            return 1f - close * close;
        }

        /// <summary>
        /// Rotates one door by <paramref name="degrees"/> about its outer hinge: the vertical edge <paramref
        /// name="halfWidth"/> from its closed centre, on the side away from the wardrobe's middle (the sign of
        /// <paramref name="closedLocalPos"/>'s x).
        /// </summary>
        private static void PoseDoor(Transform door, Vector3 closedLocalPos, float halfWidth, float degrees)
        {
            if (door == null)
            {
                return;
            }
            float outerSide = Mathf.Sign(closedLocalPos.x);
            Vector3 hinge = closedLocalPos + new Vector3(outerSide * halfWidth, 0f, 0f);
            Quaternion rotation = Quaternion.Euler(0f, degrees, 0f);
            door.localPosition = hinge + rotation * (closedLocalPos - hinge);
            door.localRotation = rotation;
        }
    }
}
