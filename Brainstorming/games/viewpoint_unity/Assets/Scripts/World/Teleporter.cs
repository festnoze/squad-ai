using System;
using System.Collections.Generic;
using TMPro;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// Level exit. Shows "inserted / required" batteries, accepts insertion, and
    /// once charged raises DepartRequested on the next interaction. The origin is
    /// the center of the pad, on the floor. Never carved, never photographed,
    /// never broken.
    /// </summary>
    public sealed class Teleporter : MonoBehaviour, IInteractable
    {
        // Every number below comes from PRD 5.7.
        private const float PadTopRadius = 1.3f;
        private const float PadBottomRadius = 1.5f;
        private const float PadHeight = 0.22f;
        private const float PadY = 0.11f;
        private const float RingInnerRadius = 1.05f;
        private const float RingOuterRadius = 1.25f;
        private const float RingY = 2.3f;
        private const float RingSpinIdle = 0.5f;
        private const float RingSpinCharged = 2.2f;
        private const float RingBobSpeed = 1.5f;
        private const float RingBobAmplitude = 0.12f;
        private const float PillarX = 1.9f;
        private const float PillarHalfHeight = 0.7f;
        private static readonly Vector3 PillarSize = new Vector3(0.4f, 1.4f, 0.4f);
        private static readonly Vector3 CellSize = new Vector3(0.44f, 0.18f, 0.44f);
        private const float CellBaseY = 1.55f;
        private const float CellStep = 0.24f;
        private const float LabelY = 3.2f;
        private const float LabelFontSize = 64f;
        // Godot drove a Label3D at 0.006 world units per font pixel; TextMeshPro
        // sizes its 3D mesh in world units, so the same ratio becomes a scale.
        private const float LabelPixelSize = 0.006f;
        // Godot outline width 12 has no direct equivalent: TMP outlines are a
        // fraction of the SDF spread. 0.2 matches the original by eye (PRD 12).
        private const float LabelOutlineWidth = 0.2f;
        private const float TriggerRadius = 1.8f;
        private const float TriggerY = 1.2f;

        /// Raised when the pad is charged and the player interacts with nothing
        /// left to insert. Main listens and runs the level transition.
        public event Action DepartRequested;

        private int _required;
        private Transform _ring;
        private Renderer _ringRenderer;
        private readonly List<Renderer> _cells = new List<Renderer>();
        private TextMeshPro _label;
        private Transform _labelTransform;
        private Camera _billboardCamera;
        private float _spin;

        // The very instance we subscribed to. GameState is one object owned by
        // Main, but a test may install another between enable and disable, and
        // unsubscribing from the wrong one would leave a live handler on a pad
        // that has already been retired.
        private GameState _state;

        /// <summary>
        /// How many batteries this level asks for. The caller may run it before or
        /// after Awake, so the cells are grown here rather than assumed built.
        /// </summary>
        public void Setup(int required)
        {
            _required = required;
            EnsureCells();
            GameState state = GameState.Instance;
            Refresh(state.CarriedBatteries, state.InsertedBatteries, state.RequiredBatteries);
        }

        private void Awake()
        {
            Build();
            EnsureCells();
        }

        private void OnEnable()
        {
            Groups.Add(this, Groups.Teleporter);
            _state = GameState.Instance;
            _state.BatteriesChanged += OnBatteriesChanged;
            Refresh(_state.CarriedBatteries, _state.InsertedBatteries, _state.RequiredBatteries);
        }

        private void OnDisable()
        {
            Groups.Remove(this, Groups.Teleporter);
            if (_state != null)
            {
                _state.BatteriesChanged -= OnBatteriesChanged;
                _state = null;
            }
        }

        private void Update()
        {
            if (_ring == null)
            {
                return;
            }
            bool charged = GameState.Instance.CanTeleport();
            _spin += Time.deltaTime * (charged ? RingSpinCharged : RingSpinIdle);
            // The spin is authored in design space, so its sign goes through the
            // one mirror like every other rotation.
            _ring.localRotation = Quaternion.Euler(0f, DesignSpace.YawToUnityDegrees(_spin), 0f);
            Vector3 local = _ring.localPosition;
            local.y = RingY + (charged ? Mathf.Sin(_spin * RingBobSpeed) * RingBobAmplitude : 0f);
            _ring.localPosition = local;
        }

        private void LateUpdate()
        {
            if (_labelTransform == null)
            {
                return;
            }
            if (_billboardCamera == null)
            {
                _billboardCamera = Camera.main;
            }
            if (_billboardCamera == null)
            {
                return;
            }
            // Godot's Label3D billboard is view-plane aligned, so copy the camera
            // basis instead of aiming at the camera position.
            _labelTransform.rotation = _billboardCamera.transform.rotation;
        }

        public void Interact(PlayerController player)
        {
            GameState state = GameState.Instance;
            if (state.InsertBatteries() > 0)
            {
                return;
            }
            if (state.CanTeleport())
            {
                DepartRequested?.Invoke();
            }
        }

        public string PromptText(PlayerController player)
        {
            GameState state = GameState.Instance;
            if (state.CanTeleport())
            {
                return "E : se teleporter";
            }
            if (state.CarriedBatteries > 0)
            {
                return "E : inserer les piles";
            }
            int missing = state.RequiredBatteries - state.InsertedBatteries;
            return string.Format("Il manque {0} pile{1}", missing, missing > 1 ? "s" : "");
        }

        private void OnBatteriesChanged(int carried, int inserted, int required)
        {
            Refresh(carried, inserted, required);
        }

        /// Repaints the cells, the label and the ring. Only the inserted count is
        /// read; the other two arrive with the event and are kept for symmetry.
        private void Refresh(int carried, int inserted, int required)
        {
            for (int i = 0; i < _cells.Count; i++)
            {
                Renderer cell = _cells[i];
                if (cell == null)
                {
                    continue;
                }
                bool filled = i < inserted;
                cell.sharedMaterial = filled ? Materials.Solid("battery", 1.2f) : Materials.Solid("battery_tip");
            }

            bool charged = GameState.Instance.CanTeleport();
            if (_label != null)
            {
                if (charged)
                {
                    _label.text = "PRET";
                    _label.color = Palette.Get("teleporter_ring");
                }
                else
                {
                    _label.text = string.Format("{0} / {1} piles", inserted, _required);
                    _label.color = Color.white;
                }
            }
            if (_ringRenderer != null)
            {
                _ringRenderer.sharedMaterial = Materials.Solid("teleporter_ring", charged ? 2f : 0.15f);
            }
        }

        private void Build()
        {
            // The interaction ray only sees the Interact layer, and the component it
            // looks for sits on the trigger object itself (PRD 15.3).
            gameObject.layer = Layers.Interact;

            // Godot tapered the pad (top 1.3, bottom 1.5); Unity's cylinder is
            // straight, so it takes the mean radius. Ten centimetres of taper on a
            // 22 cm disc is invisible and no generated mesh is worth it here.
            // The primitive is 2 units tall with a radius of 0.5, so the horizontal
            // scale is the mean diameter.
            float padDiameter = PadTopRadius + PadBottomRadius;
            Renderer pad = SpawnPart(
                transform, PrimitiveType.Cylinder, "Pad",
                new Vector3(0f, PadY, 0f),
                new Vector3(padDiameter, PadHeight * 0.5f, padDiameter));
            pad.sharedMaterial = Materials.Solid("teleporter");

            GameObject ringGo = new GameObject("Ring");
            _ring = ringGo.transform;
            _ring.SetParent(transform, false);
            _ring.localPosition = new Vector3(0f, RingY, 0f);
            MeshFilter ringFilter = ringGo.AddComponent<MeshFilter>();
            ringFilter.sharedMesh = ProceduralMeshes.Torus(RingInnerRadius, RingOuterRadius);
            _ringRenderer = ringGo.AddComponent<MeshRenderer>();
            _ringRenderer.sharedMaterial = Materials.Solid("teleporter_ring", 0.15f);

            BuildPillar();

            // TMP_Text drives a RectTransform. Building the object with one from
            // the start avoids swapping its Transform out from under a cached
            // reference, which is what AddComponent<RectTransform> would do.
            GameObject labelGo = new GameObject("Label", typeof(RectTransform));
            _labelTransform = labelGo.transform;
            _labelTransform.SetParent(transform, false);
            RectTransform labelRect = _labelTransform as RectTransform;
            if (labelRect != null)
            {
                // The rect is measured in the same local units as the font size,
                // BEFORE the 0.006 scale below: wide enough that the longest label
                // ("<n> / <n> piles" at size 64) never wraps.
                labelRect.sizeDelta = new Vector2(LabelFontSize * 12f, LabelFontSize * 2f);
            }
            _label = labelGo.AddComponent<TextMeshPro>();
            _label.fontSize = LabelFontSize;
            _label.alignment = TextAlignmentOptions.Center;
            if (_label.font != null)
            {
                // Reading fontMaterial first forces TextMeshPro to clone the shared
                // font material, so the outline never leaks onto every other label.
                _ = _label.fontMaterial;
                _label.outlineColor = new Color32(13, 15, 26, 255);
                _label.outlineWidth = LabelOutlineWidth;
            }
            _labelTransform.localPosition = new Vector3(0f, LabelY, 0f);
            _labelTransform.localScale = new Vector3(LabelPixelSize, LabelPixelSize, LabelPixelSize);

            SphereCollider trigger = gameObject.AddComponent<SphereCollider>();
            trigger.isTrigger = true;
            trigger.radius = TriggerRadius;
            trigger.center = new Vector3(0f, TriggerY, 0f);
        }

        /// The side pillar is the only solid part of the teleporter: it carries the
        /// battery cells and the player can lean on it.
        private void BuildPillar()
        {
            GameObject pillar = new GameObject("Pillar");
            pillar.layer = Layers.World;
            pillar.transform.SetParent(transform, false);
            pillar.transform.localPosition = new Vector3(PillarX, 0f, 0f);
            BoxCollider box = pillar.AddComponent<BoxCollider>();
            box.size = PillarSize;
            box.center = new Vector3(0f, PillarHalfHeight, 0f);

            Renderer mesh = SpawnPart(
                pillar.transform, PrimitiveType.Cube, "PillarMesh",
                new Vector3(0f, PillarHalfHeight, 0f),
                PillarSize);
            mesh.sharedMaterial = Materials.Solid("stone");
        }

        /// Grows the cell stack to the required count and hides any surplus. Cells
        /// are never destroyed: Setup can run twice and the count only ever moves.
        private void EnsureCells()
        {
            for (int i = _cells.Count; i < _required; i++)
            {
                Renderer cell = SpawnPart(
                    transform, PrimitiveType.Cube, "Cell" + i,
                    new Vector3(PillarX, CellBaseY + i * CellStep, 0f),
                    CellSize);
                cell.sharedMaterial = Materials.Solid("battery_tip");
                _cells.Add(cell);
            }
            for (int i = 0; i < _cells.Count; i++)
            {
                if (_cells[i] != null)
                {
                    _cells[i].gameObject.SetActive(i < _required);
                }
            }
        }

        private static Renderer SpawnPart(Transform parent, PrimitiveType shape, string name, Vector3 localPosition, Vector3 localScale)
        {
            GameObject go = GameObject.CreatePrimitive(shape);
            go.name = name;
            Collider col = go.GetComponent<Collider>();
            if (col != null)
            {
                // CreatePrimitive always attaches a collider; these parts are pure
                // decoration and the pillar box is the only solid wanted. Disabling
                // bites at once, the destroy only at the end of the frame.
                col.enabled = false;
                UnityEngine.Object.Destroy(col);
            }
            Transform t = go.transform;
            t.SetParent(parent, false);
            t.localPosition = localPosition;
            t.localScale = localScale;
            return go.GetComponent<Renderer>();
        }
    }
}
