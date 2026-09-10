using System;
using System.Collections.Generic;
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
        // Godot drove a Label3D at 0.006 world units per font pixel, and a
        // TextMesh sizes its glyphs in font pixels too, so the same ratio
        // carries over as a uniform scale on the label transform.
        private const float LabelPixelSize = 0.006f;
        private const float TriggerRadius = 1.8f;
        private const float TriggerY = 1.2f;

        // The pad light of PRD_VISUAL 4.4 (V-LIGHT-03). A look decision and no
        // part of PRD 5.7, which is why it stands apart from the block above. The
        // range and the two intensities are fixed there, the height is not, and
        // the height decides whether the criterion is met at all. A point light
        // sitting on the pad top (y 0.22) meets the floor two metres out at a
        // grazing six degrees, so N.L drops to 0.11 and the ground reads unlit; a
        // metre up, those same two metres out get about 0.45 and the pool is
        // actually there. It also stays well under the ring at y 2.3, so the ring
        // remains the brightest thing on the object.
        // The machine of PRD_VISUAL 4.7 (V-PROP-05). Look decisions, no part of
        // PRD 5.7, which is why they stand apart from the pinned block above.
        // Everything here sits AT or JUST ABOVE the pad face (PadHeight 0.22) so
        // nothing changes the silhouette the player walks onto, and nothing
        // reaches the trigger at TriggerY 1.2.
        private const float RimWidth = 0.16f;
        private const float RimThickness = 0.07f;
        private const float RimY = 0.05f;

        // The inlaid track, a whisker above the pad face so it cannot z-fight
        // with it at a grazing angle.
        private const float TrackInnerRadius = 0.82f;
        private const float TrackOuterRadius = 1.02f;
        private const float TrackThickness = 0.03f;
        private const float TrackY = PadHeight + 0.012f;
        private const float TrackIdleEnergy = 0.15f;

        // The charge readout, laid in the track's circle and a touch above it.
        private const float SegmentInnerRadius = 0.85f;
        private const float SegmentOuterRadius = 0.99f;
        private const float SegmentThickness = 0.05f;
        private const float SegmentY = PadHeight + 0.03f;

        /// <summary>
        /// The gap between two charge segments, as a fraction of a full circle.
        /// Segments have to be COUNTABLE from a distance, and a band with no gaps
        /// is one object however many pieces it is made of.
        /// </summary>
        private const float SegmentGapTurns = 0.035f;

        /// <summary>
        /// Emission energy of a segment. Dark is not zero: an unlit segment must
        /// still be visible as a socket waiting to be filled, or a level that
        /// needs three batteries looks like a level that needs none.
        /// </summary>
        private const float SegmentEmptyEnergy = 0.1f;
        private const float SegmentFilledEnergy = 1.6f;

        private const float PadLightY = 1f;
        private const float PadLightRange = 6f;
        private const float PadLightIntensityIdle = 0.6f;
        private const float PadLightIntensityCharged = 2f;

        /// <summary>
        /// The step of PRD_VISUAL 4.8 (V-VFX-05)'s "rising pitch of brightness":
        /// a filled segment is brighter than the one before it, so the readout
        /// climbs as the pad fills instead of stamping the same value five
        /// times. Five is the largest requirement in the catalogue, so the top
        /// segment lands at 1.6 + 4 x 0.28 = 2.72, well inside the range the
        /// ring itself already reaches when charged.
        /// </summary>
        private const float SegmentPitchStep = 0.28f;

        // The mote column of PRD_VISUAL 4.8 (V-VFX-05): "when charged, a column
        // of slowly rising indigo motes fills the ring and the ground ring track
        // glows; on departure, the column brightens to white over 0.4 s and the
        // fade to white takes over". The item pins the count, the life and the
        // rise; everything else below is geometry read off the machine.
        private const int ColumnMoteCount = 60;
        private const float ColumnMoteLife = 3f;
        private const float ColumnMoteRise = 0.4f;

        /// <summary>
        /// Emitter radius. Inside RingInnerRadius (1.05) with enough margin that
        /// no mote crosses the torus it is meant to fill: a speck popping
        /// through the ring reads as a sorting bug, not as light.
        /// </summary>
        private const float ColumnRadius = 0.88f;

        /// <summary>Just clear of the charge segments, which are the highest thing on the pad face.</summary>
        private const float ColumnBaseY = SegmentY + 0.05f;

        /// <summary>
        /// Height of the emitter VOLUME, which is not the height of the column.
        /// A mote is born anywhere in this cylinder and then rises
        /// ColumnMoteRise * ColumnMoteLife (1.2 m) before it dies, so the band
        /// motes actually occupy runs from ColumnBaseY to exactly RingY. That
        /// arithmetic is the reason the column is CONTAINED without relying on
        /// the fade of colorOverLifetime, which the URP/Unlit fallback path
        /// throws away with the rest of the vertex colour (Appendix C.20): even
        /// with no fade at all, nothing is drawn above the ring.
        /// </summary>
        private const float ColumnEmitterHeight = RingY - ColumnBaseY - (ColumnMoteRise * ColumnMoteLife);

        /// <summary>
        /// A mote reads as a speck of light, not as a firefly. Small enough that
        /// sixty of them are a column rather than a swarm of dots.
        /// </summary>
        private const float ColumnMoteSize = 0.07f;

        // Mote alpha, which is what carries the charge (see ApplyColumn for why
        // it cannot be carried by the start colour). First battery in: present
        // but faint. Charged: the column the item asks for. Departing: full.
        private const float ColumnAlphaFirst = 0.16f;
        private const float ColumnAlphaCharged = 0.5f;
        private const float ColumnAlphaDeparting = 1f;

        /// <summary>
        /// Emission rate at charge zero-plus, as a fraction of the full rate, so
        /// a partly charged pad has a thinner column and not just a dimmer one.
        /// </summary>
        private const float ColumnRateFloor = 0.45f;

        /// <summary>
        /// Deterministic seed. PlayMode Stage11Reload rebuilds a level and
        /// Stage12Rewind undoes one, and neither may come back looking
        /// different, so the system is seeded exactly as Atmosphere's dust is.
        /// </summary>
        private const uint ColumnSeed = 20260908u;

        /// <summary>
        /// The window V-VFX-05 pins for the departure flash: "the column
        /// brightens to white over 0.4 s and the fade to white (V-POST-06)
        /// takes over". Public because the owner of that fade has to know how
        /// long this half lasts; see <see cref="DepartureFlash"/>.
        /// </summary>
        public const float DepartureFlashSeconds = 0.4f;

        /// Raised when the pad is charged and the player interacts with nothing
        /// left to insert. Main listens and runs the level transition.
        public event Action DepartRequested;

        private int _required;
        private Transform _ring;
        private Renderer _ringRenderer;
        private readonly List<Renderer> _cells = new List<Renderer>();
        private TextMesh _label;
        private Transform _labelTransform;
        private Camera _billboardCamera;
        private Light _padLight;
        private MeshRenderer _trackRenderer;
        private MeshRenderer[] _chargeSegments;
        private float _spin;

        private ParticleSystem _column;

        /// <summary>
        /// The column's own material, one per teleporter and not one shared by
        /// the class. The charge and the departure flash are written INTO it
        /// (see <see cref="ApplyColumn"/>), so a shared material would make two
        /// pads on one level tell the same lie; there is exactly one pad per
        /// level today, which is precisely how a shared instance would survive
        /// review and break the day a second one appeared. Destroyed with the
        /// component, or a level change would leak one material per level.
        /// </summary>
        private Material _columnMaterial;

        /// <summary>
        /// The mote sprite, generated once and shared by every pad ever built.
        /// Unlike the material nothing writes to it, and it is an asset-shaped
        /// object with no owner, so it is never destroyed - the same call the
        /// gradient cache in <c>Materials</c> makes, and for the same reason.
        /// </summary>
        private static Texture2D _moteSprite;

        private static readonly int ColumnColorId = Shader.PropertyToID("_BaseColor");

        private bool _departing;
        private float _departFlash;

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

        /// <summary>
        /// Progress of the departure flash: 0 while the pad is idle, then 0 to 1
        /// over <see cref="DepartureFlashSeconds"/> from the frame the player
        /// asked to leave, and held at 1 afterwards.
        /// <para>
        /// This is the ONE thing the fade to white (V-POST-06) needs from the
        /// pad, and it is a value to read rather than a callback: the timing
        /// signal already exists and is <see cref="DepartRequested"/>, raised on
        /// exactly the frame it always was. A second event fired at the same
        /// instant would be a second truth about when a departure starts.
        /// </para>
        /// </summary>
        public float DepartureFlash
        {
            get { return _departing ? _departFlash : 0f; }
        }

        /// <summary>True from the frame <see cref="DepartRequested"/> is raised.</summary>
        public bool IsDeparting
        {
            get { return _departing; }
        }

        /// <summary>
        /// Lights the column white over <see cref="DepartureFlashSeconds"/>.
        /// Called by <see cref="Interact"/> on the frame the departure is
        /// requested, and public so a departure triggered by another route (a
        /// scripted ending, a test) can light the pad the same way. Idempotent:
        /// a second call while the flash is running is ignored, so nothing can
        /// restart the ramp halfway through the fade.
        /// <para>
        /// PRESENTATION ONLY. It moves no counter, no collider and no group, and
        /// it does not gate the departure: the level transition runs whether or
        /// not this ever gets a frame to draw in.
        /// </para>
        /// </summary>
        public void BeginDepartureFlash()
        {
            if (_departing)
            {
                return;
            }
            _departing = true;
            _departFlash = 0f;
            ApplyColumn();
        }

        private void Update()
        {
            AdvanceDepartureFlash();
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

        /// <summary>
        /// Walks the flash forward. Deliberately the FIRST thing
        /// <see cref="Update"/> does and not part of its ring block, which
        /// returns early on a pad whose ring was never built.
        /// <para>
        /// Unscaled time, like <c>Hud.Fade</c> and like the dust: the flash has
        /// to hand over to a fade that is itself unscaled, and a pad that froze
        /// mid flash because something slowed the game would leave the screen
        /// half white with nothing moving. Nothing in this game touches
        /// timeScale today; this is the same belt Hud wears for the same reason.
        /// </para>
        /// </summary>
        private void AdvanceDepartureFlash()
        {
            if (!_departing || _departFlash >= 1f)
            {
                return;
            }
            _departFlash = Mathf.Min(1f, _departFlash + (Time.unscaledDeltaTime / DepartureFlashSeconds));
            ApplyColumn();
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
                // The flash starts BEFORE the event and in the same frame. Two
                // reasons for the order and neither is cosmetic: a listener runs
                // the level transition and may tear this object down, and an
                // exception thrown by a listener must not be what decides
                // whether the pad lit up. Nothing here reads or writes a
                // counter, so the moment Main hears about the departure is
                // exactly the moment it always was.
                BeginDepartureFlash();
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

        /// Repaints everything the charge drives: the cells, the label, the ring,
        /// the readout segments, the ground track, the pad light and the mote
        /// column. Only the inserted count is read; the other two arrive with the
        /// event and are kept for symmetry.
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

            // THE charge fraction: every moving part of this object reads this
            // one line. It rides the counter this class already listens to,
            // because a "charge" field of our own would be a second truth and it
            // would drift the first time a rewind put the counters back behind
            // our back (RestoreCounters emits BatteriesChanged, so this path
            // covers a rewind for free). _required rather than the event's
            // required, so the light, the label, the segments and the mote
            // column always tell the same story; InverseLerp answers 0 when its
            // two bounds are equal, so a level that asks for nothing leaves the
            // pad idle instead of dividing by zero.
            float charge = Mathf.InverseLerp(0f, _required, inserted);

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
            // V-PROP-05's charge readout, off the SAME counter as everything
            // else on this object. One filled segment per inserted battery, in
            // order, so the player reads a count and not a pattern.
            if (_chargeSegments != null)
            {
                for (int i = 0; i < _chargeSegments.Length; i++)
                {
                    if (_chargeSegments[i] == null)
                    {
                        continue;
                    }
                    bool filled = i < inserted;
                    // V-VFX-05 asks for "a rising pitch of brightness" as the
                    // pad fills, so a filled segment's energy climbs with its
                    // index instead of every filled segment stamping the same
                    // value. The count is still what the player reads; the pitch
                    // is what makes an insertion an EVENT rather than one more
                    // identical light coming on.
                    float energy = filled
                        ? SegmentFilledEnergy + (i * SegmentPitchStep)
                        : SegmentEmptyEnergy;
                    _chargeSegments[i].sharedMaterial = Materials.Solid("teleporter_ring", energy);
                }
            }

            // The track brightens with the whole thing, so a charged pad glows
            // on the ground rather than only in its segments. It RAMPS with the
            // charge rather than switching at the last battery: the acceptance
            // criterion is that the charge state reads "from anywhere on the
            // level", and at forty metres the ground glow is legible long after
            // the individual segments have stopped being countable.
            if (_trackRenderer != null)
            {
                _trackRenderer.sharedMaterial = Materials.Solid(
                    "teleporter_ring", Mathf.Lerp(TrackIdleEnergy, SegmentFilledEnergy, charge));
            }

            ApplyColumn();

            if (_padLight != null)
            {
                // The intensity rides the charge fraction above and nothing
                // else, so the pool on the floor and the label over it can never
                // disagree. Range, colour and culling are set once in
                // BuildPadLight and are V-LIGHT-03's, not ours to move.
                _padLight.intensity = Mathf.Lerp(PadLightIntensityIdle, PadLightIntensityCharged, charge);
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

            // V-PROP-05: the machine, over the pad the original had. Purely
            // additive - it adds a stepped rim, an inlaid track and the charge
            // readout, and moves nothing that already existed.
            BuildMachine();

            // Before the trigger, on purpose: see the note on the label below for
            // what happens to a level when a decoration throws in here. Nothing in
            // this call can (no asset, no Shader.Find, and Palette.Get answers
            // magenta instead of raising on a bad key), so the trigger is still
            // the last thing built and is still the last thing that can be lost.
            BuildPadLight();

            BuildPillar();

            // A legacy TextMesh, which is the real analogue of the Godot
            // Label3D this ports, and the only 3D text that needs no imported
            // asset: it takes a Font and the font's own material.
            //
            // It replaces a TextMeshPro label that threw a NullReferenceException
            // in a built player (TMP cannot start without its settings asset,
            // see Fonts). That exception aborted the rest of this method, so the
            // teleporter came up with NO INTERACTION TRIGGER and the level could
            // not be finished. The trigger is built last, which is what made a
            // text bug into an unplayable game.
            GameObject labelGo = new GameObject("Label");
            _labelTransform = labelGo.transform;
            _labelTransform.SetParent(transform, false);

            _label = labelGo.AddComponent<TextMesh>();
            _label.fontSize = Mathf.RoundToInt(LabelFontSize);
            _label.anchor = TextAnchor.MiddleCenter;
            _label.alignment = TextAlignment.Center;
            _label.color = Color.white;
            ApplyLabelFont(labelGo);

            _labelTransform.localPosition = new Vector3(0f, LabelY, 0f);
            _labelTransform.localScale = new Vector3(LabelPixelSize, LabelPixelSize, LabelPixelSize);

            SphereCollider trigger = gameObject.AddComponent<SphereCollider>();
            trigger.isTrigger = true;
            trigger.radius = TriggerRadius;
            trigger.center = new Vector3(0f, TriggerY, 0f);

            // AFTER the trigger, and that placement is the whole point. Read the
            // note on the label above: this method builds the interaction
            // trigger last, so anything that throws before it takes the trigger
            // with it and the level cannot be finished. The pad light is allowed
            // to run early because nothing in it can throw; the column loads a
            // shader, generates a texture and builds a material, which is three
            // times more surface than the label bug that already cost this
            // project a playable game. Built last, a broken column is a pad with
            // no motes and nothing worse.
            BuildChargeColumn();
        }

        /// <summary>
        /// Gives the label the game's one typeface, which is the last clause of
        /// PRD_VISUAL 4.11 (V-HUD-01): the HUD, the menus and this 3D label all
        /// draw with whatever <c>Fonts.Default</c> hands out, so there is one
        /// typeface in the game and one place that decides which.
        /// <para>
        /// BOTH the font AND the renderer's material are set, and that is the
        /// part that is easy to get wrong. A TextMesh is two halves: the
        /// component builds a quad per glyph with UVs into the font's ATLAS,
        /// and its own MeshRenderer draws those quads with whatever material it
        /// happens to hold. Setting <c>textMesh.font</c> alone re-cuts the UVs
        /// for the new atlas while the renderer keeps sampling the OLD font's
        /// texture, so the label comes out as the wrong glyphs, as confetti, or
        /// as nothing at all - and it does so with no error anywhere. The
        /// font's own material is used rather than a copy of it for a second
        /// reason: a dynamic font rebuilds its atlas whenever a new character
        /// is asked for, which swaps the TEXTURE on that material, and a copy
        /// made once at build time would go on pointing at the atlas the font
        /// has already thrown away.
        /// </para>
        /// <para>
        /// A null font leaves the label exactly as it is today, on purpose.
        /// <c>Fonts.Default</c> documents that callers must tolerate null (a
        /// headless run has no use for a font), and this runs inside
        /// <see cref="Build"/>: throwing here would abort the rest of the
        /// method the way the TextMeshPro label once did, and the interaction
        /// trigger is built after this point. A pad with an unstyled label is
        /// nothing; a pad with no trigger is an unfinishable level.
        /// </para>
        /// </summary>
        private void ApplyLabelFont(GameObject labelGo)
        {
            Font font = Fonts.Default;
            if (font == null)
            {
                return;
            }

            _label.font = font;

            // Same guard as the font itself, one level down: handing the
            // renderer a null material would draw the label in the error shader
            // (or in nothing at all), which is strictly worse than leaving it
            // with the material the engine gave the component.
            Material fontMaterial = font.material;
            if (fontMaterial == null)
            {
                return;
            }

            MeshRenderer labelRenderer = labelGo.GetComponent<MeshRenderer>();
            if (labelRenderer != null)
            {
                labelRenderer.sharedMaterial = fontMaterial;
            }
        }

        /// <summary>
        /// V-VFX-05's rising column: about sixty motes on a cylinder emitter,
        /// 3 s life, drifting up at 0.4 m/s, driven by the SAME GameState
        /// counter as the segments, the track, the cells and the pad light.
        ///
        /// Everything here is DECOR, built the way Atmosphere's dust is built:
        ///   - it joins no group, so nothing in Groups can find it;
        ///   - it carries no collider, so no raycast, no interaction ray and no
        ///     photo frustum can touch it (a ParticleSystem brings none, and the
        ///     collision and trigger modules stay off);
        ///   - it is a child of the pad, so Main's teardown takes it with the
        ///     level and the rewind graveyard carries it whole;
        ///   - it is culled from the picture studio. A teleporter is never in a
        ///     photo, but the rule is the rule, and it costs one line: the snap
        ///     camera sees the PhotoStudio layer and nothing else, so taking the
        ///     root's layer (Interact) keeps that decision in the one place
        ///     BuildPadLight already put it.
        ///
        /// Silent and harmless with no rasterizer: a headless run has no use for
        /// particles and the EditMode suites must not pay for a texture and a
        /// material each. ApplyColumn answers for the missing system.
        /// </summary>
        private void BuildChargeColumn()
        {
            if (SystemInfo.graphicsDeviceType == UnityEngine.Rendering.GraphicsDeviceType.Null)
            {
                return;
            }

            GameObject go = new GameObject("ChargeColumn");
            // Set before the component exists, as everywhere else in this
            // project: a system that registered on the wrong layer would be
            // culled by the wrong cameras.
            go.layer = gameObject.layer;
            go.transform.SetParent(transform, false);
            // On the axis of the pad, so the one z mirror has nothing to flip.
            go.transform.localPosition = new Vector3(0f, ColumnBaseY, 0f);

            _column = go.AddComponent<ParticleSystem>();
            // Stopped while it is configured. A ParticleSystem starts playing
            // the moment it is added, and a system that emits during setup
            // spits its first burst from an unconfigured shape at the origin.
            _column.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);

            // EVERY MODULE HERE IS A STRUCT AND MUST BE WRITTEN THROUGH. The
            // properties return a view whose setters write to the system, which
            // is why assigning to a local's field works at all; ps.main.x = y
            // does not compile and the tempting "simplification" of copying a
            // module into a plain struct silently does nothing.
            ParticleSystem.MainModule main = _column.main;
            main.duration = ColumnMoteLife;
            main.loop = true;
            main.startLifetime = ColumnMoteLife;
            main.startSpeed = ColumnMoteRise;
            main.startSize = ColumnMoteSize;
            main.maxParticles = ColumnMoteCount;
            main.simulationSpace = ParticleSystemSimulationSpace.Local;
            main.gravityModifier = 0f;
            main.playOnAwake = false;
            // Unscaled, like the dust and like the HUD: the departure flash has
            // to keep moving whatever happens to timeScale, and a column that
            // froze while the screen went white would read as a hitch.
            main.useUnscaledTime = true;
            // FULL white here and the real colour on the MATERIAL. The start
            // colour reaches the shader as the vertex COLOR stream, and plain
            // URP/Unlit - the fallback taken in a player today, where the
            // particle shader is stripped - declares no COLOR input at all
            // (Appendix C.20). Anything the charge has to say therefore lives on
            // _BaseColor, which BOTH paths multiply into colour and alpha.
            main.startColor = Color.white;

            ParticleSystem.EmissionModule emission = _column.emission;
            emission.enabled = true;
            // Nothing until a battery goes in; ApplyColumn owns this from here.
            emission.rateOverTime = 0f;

            // A cylinder, which the shape module spells "a cone with no angle".
            // The cone axis is local +z (that is why Unity's own default
            // particle system sits at -90 on x), so the shape is rotated rather
            // than the emitter object: keeping the object at identity means the
            // pad's single z mirror still has nothing to say about it.
            ParticleSystem.ShapeModule shape = _column.shape;
            shape.enabled = true;
            shape.shapeType = ParticleSystemShapeType.ConeVolume;
            shape.angle = 0f;
            shape.radius = ColumnRadius;
            // Fill the disc rather than emit from its edge.
            shape.radiusThickness = 1f;
            // Max as a belt: the height is arithmetic off four other constants
            // (see ColumnEmitterHeight) and a zero or negative length would be
            // a flat emitter, i.e. a ring of motes instead of a column.
            shape.length = Mathf.Max(0.15f, ColumnEmitterHeight);
            shape.rotation = new Vector3(-90f, 0f, 0f);
            shape.randomDirectionAmount = 0f;
            shape.alignToDirection = false;

            // A slow wander so the column shimmers instead of rising like a
            // barcode. Cheap: one curve, no noise texture.
            ParticleSystem.NoiseModule noise = _column.noise;
            noise.enabled = true;
            noise.strength = 0.06f;
            noise.frequency = 0.25f;
            noise.scrollSpeed = 0.35f;
            noise.damping = true;

            // Fade in and out, so a mote arrives and leaves instead of popping.
            // This gradient travels as vertex COLOR and is therefore ignored on
            // the fallback path, exactly like the dust's: there the motes hold a
            // steady alpha and simply stop at the ring. That is why the emitter
            // height above is derived from the rise, and not the other way
            // round - the column is contained by geometry, not by this fade.
            ParticleSystem.ColorOverLifetimeModule fade = _column.colorOverLifetime;
            fade.enabled = true;
            var gradient = new Gradient();
            gradient.SetKeys(
                new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                new[]
                {
                    new GradientAlphaKey(0f, 0f),
                    new GradientAlphaKey(1f, 0.2f),
                    new GradientAlphaKey(1f, 0.7f),
                    new GradientAlphaKey(0f, 1f),
                });
            fade.color = new ParticleSystem.MinMaxGradient(gradient);

            ParticleSystemRenderer columnRenderer = go.GetComponent<ParticleSystemRenderer>();
            columnRenderer.renderMode = ParticleSystemRenderMode.Billboard;
            columnRenderer.alignment = ParticleSystemRenderSpace.View;
            _columnMaterial = ColumnMaterial();
            columnRenderer.sharedMaterial = _columnMaterial;
            // A mote is light. Putting sixty translucent billboards through the
            // shadow pass would cost six shadow faces of the pad light for
            // nothing, and the pad light casts none anyway.
            columnRenderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            columnRenderer.receiveShadows = false;
            columnRenderer.sortingFudge = 0f;

            // Deterministic, so a reload and a rewind reproduce the same column.
            _column.randomSeed = ColumnSeed;
            _column.useAutoRandomSeed = false;
            // Playing from here at a rate of zero, and NEVER stopped and
            // restarted as the charge moves: Play() restarts the system's own
            // timeline, so a pad that stopped and played again on every
            // insertion would re-emit from a fresh clock each time and pulse.
            // The rate alone decides whether anything comes out.
            _column.Play(true);
            ApplyColumn();
        }

        /// <summary>
        /// Writes the charge and the departure flash onto the column. The only
        /// place either is presented, and it reads the counter rather than a
        /// cached copy of it, so there is nothing here that a rewind could leave
        /// stale.
        /// <para>
        /// Two levers and no others. The emission RATE thins the column as the
        /// charge drops, so a pad waiting for its last battery is visibly less
        /// than a charged one from across the level; and the material's
        /// _BaseColor carries the colour and the alpha, which is the one input
        /// both the URP particle shader and the plain-Unlit fallback multiply
        /// (Appendix C.20). Neither start colour nor colour-over-lifetime can be
        /// used for anything load bearing here for exactly that reason.
        /// </para>
        /// </summary>
        private void ApplyColumn()
        {
            if (_column == null)
            {
                return;
            }

            float charge = Mathf.InverseLerp(0f, _required, GameState.Instance.InsertedBatteries);
            ParticleSystem.EmissionModule emission = _column.emission;
            emission.rateOverTime = charge <= 0f
                ? 0f
                : (ColumnMoteCount / ColumnMoteLife) * Mathf.Lerp(ColumnRateFloor, 1f, charge);
            // Motes already in the air are left to die on their own when the
            // charge falls back (a rewind that takes a battery out): three
            // seconds of thinning column reads as the machine winding down,
            // where a Clear() would blink the whole thing out of existence.

            if (_columnMaterial == null)
            {
                return;
            }

            // The indigo of the item. PRD_VISUAL calls the pad light of 4.4 "a
            // soft indigo pool" and that light is Palette teleporter_ring, so
            // this is the same indigo the rest of the machine already glows in;
            // picking a colour off the palette here would make the column a
            // second light source inside the ring it belongs to.
            Color tint = Palette.Get("teleporter_ring");
            float alpha = charge <= 0f ? 0f : Mathf.Lerp(ColumnAlphaFirst, ColumnAlphaCharged, charge);

            if (_departing)
            {
                // Quadratic, not linear: the flash has to stay under the ring
                // for the first fifth of a second and then run away, so that it
                // hands over to the fade to white instead of arriving before it.
                float t = _departFlash * _departFlash;
                tint = Color.Lerp(tint, Color.white, t);
                alpha = Mathf.Lerp(alpha, ColumnAlphaDeparting, t);
            }

            _columnMaterial.SetColor(ColumnColorId, new Color(tint.r, tint.g, tint.b, alpha));
        }

        /// <summary>
        /// The mote material: unlit, additive, one per pad. A speck of light
        /// does not want to be shaded, and an unlit particle cannot be dragged
        /// around by the level's own lighting.
        /// <para>
        /// Generated rather than loaded. PRD_VISUAL 3.2 as amended (Appendix
        /// C.11) allows the ten CC0 PBR sets and the one font and nothing else,
        /// and V-VFX-05's technique note says "no texture" - which is honoured
        /// here as no texture ASSET: the sprite is DRAWN IN CODE, because a
        /// billboard with no texture at all is a hard SQUARE and the dust of
        /// V-VFX-08 already shipped that bug once (see MoteSprite in
        /// Atmosphere, whose approach this follows deliberately).
        /// </para>
        /// </summary>
        private static Material ColumnMaterial()
        {
            Shader shader = Shader.Find("Universal Render Pipeline/Particles/Unlit");
            if (shader == null)
            {
                // The particle shader is not one of the shaders this project
                // puts in Always Included Shaders, so it IS stripped from the
                // player today. Fall back to plain Unlit, which is always
                // included, rather than handing the renderer a null material and
                // drawing sixty magenta squares over the exit.
                shader = Shader.Find("Universal Render Pipeline/Unlit");
            }
            if (shader == null)
            {
                Debug.LogWarning("[Teleporter] No unlit shader for the charge column; the pad will not have one.");
                return null;
            }

            var material = new Material(shader);
            material.name = "TeleporterColumnMote";
            // ApplyColumn owns this the moment a count is known. Starting at
            // zero alpha rather than at the charged colour means a pad whose
            // Setup never ran shows no column instead of a charged one.
            material.SetColor(ColumnColorId, new Color(1f, 1f, 1f, 0f));

            Texture2D sprite = MoteSprite();
            material.SetTexture("_BaseMap", sprite);
            // The particle shader and the unlit fallback both read _BaseMap;
            // _MainTex is set too where it exists, for the same one assignment.
            if (material.HasProperty("_MainTex"))
            {
                material.SetTexture("_MainTex", sprite);
            }

            // THE BLEND STATE HAS TO BE SET AS _SrcBlend AND _DstBlend.
            // _Surface and _Blend are what the material INSPECTOR reads; the
            // shader's actual blend comes from these two plus the surface
            // keyword. Left at their opaque defaults, the soft alpha of the
            // generated sprite is discarded and every mote is a hard white quad.
            // SrcAlpha / One is additive through alpha: a mote brightens what it
            // is in front of and can never darken it, which is what a speck of
            // light in a beam does, and it is also what lets the departure flash
            // saturate towards white by stacking rather than by turning grey.
            material.SetFloat("_Surface", 1f);
            material.SetFloat("_Blend", 1f);
            material.SetFloat("_SrcBlend", (float)UnityEngine.Rendering.BlendMode.SrcAlpha);
            material.SetFloat("_DstBlend", (float)UnityEngine.Rendering.BlendMode.One);
            material.SetFloat("_ZWrite", 0f);
            material.SetFloat("_AlphaClip", 0f);
            material.SetOverrideTag("RenderType", "Transparent");
            material.renderQueue = (int)UnityEngine.Rendering.RenderQueue.Transparent;
            material.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            material.DisableKeyword("_ALPHATEST_ON");
            return material;
        }

        /// <summary>
        /// A soft round speck, 32 px square, generated once and shared. Only the
        /// alpha matters: the material tints it and scales it down, so all this
        /// has to supply is a falloff from opaque at the centre to nothing at
        /// the rim. Squared rather than linear, because a linear ramp leaves a
        /// visible disc edge once the alpha is low.
        /// </summary>
        private static Texture2D MoteSprite()
        {
            if (_moteSprite != null)
            {
                return _moteSprite;
            }

            const int size = 32;
            var texture = new Texture2D(size, size, TextureFormat.RGBA32, true, false);
            texture.name = "TeleporterMoteSprite";
            texture.wrapMode = TextureWrapMode.Clamp;
            texture.filterMode = FilterMode.Bilinear;

            var pixels = new Color32[size * size];
            float centre = (size - 1) * 0.5f;
            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    float dx = (x - centre) / centre;
                    float dy = (y - centre) / centre;
                    float d = Mathf.Sqrt((dx * dx) + (dy * dy));
                    float a = Mathf.Clamp01(1f - d);
                    a *= a;
                    pixels[(y * size) + x] = new Color32(255, 255, 255, (byte)Mathf.RoundToInt(a * 255f));
                }
            }
            texture.SetPixels32(pixels);
            // Mipmaps on, so a mote seen from across the level resolves to its
            // average instead of shimmering.
            texture.Apply(true, true);
            _moteSprite = texture;
            return _moteSprite;
        }

        /// <summary>
        /// The column's material is an instance and has no owner but this
        /// component, so it goes when the component does. Without this, every
        /// level change leaks one material: Main tears the level down with
        /// DestroyImmediate and Unity does not collect materials.
        /// The SPRITE is static and shared and is deliberately not touched here
        /// (destroying it would blank the columns of every pad still alive).
        /// </summary>
        private void OnDestroy()
        {
            if (_columnMaterial == null)
            {
                return;
            }
            if (Application.isPlaying)
            {
                Destroy(_columnMaterial);
            }
            else
            {
                DestroyImmediate(_columnMaterial);
            }
            _columnMaterial = null;
        }

        /// <summary>
        /// The machine of PRD_VISUAL 4.7 (V-PROP-05). The exit was a cylinder, a
        /// torus, a pillar and a text label; the item's target is "the most
        /// visually inviting object in every level", whose PRET state "is
        /// obvious from 15 m without reading the label".
        ///
        /// Three additions, all decor, none of them touching the pad, the ring,
        /// the pillar, the label, the trigger or the counter:
        ///   - a stepped rim around the pad, so it reads as machined rather than
        ///     as a disc dropped on the floor;
        ///   - an inlaid track just above the pad face, emissive, which is what
        ///     gives the exit a glow on the ground even seen from behind;
        ///   - the CHARGE READOUT: one ring segment per required battery, laid
        ///     in the track's circle. Segments light as batteries go in, so the
        ///     charge is legible from across the level without the label.
        ///
        /// The readout is driven from <see cref="Refresh"/>, off the same
        /// GameState counter the pillar cells and the pad light already use. A
        /// second count would drift the first time a rewind restored the
        /// counters behind our back.
        /// </summary>
        private void BuildMachine()
        {
            // The stepped rim. Flat band, sitting at the pad's own height and a
            // little wider, so the silhouette gains a shoulder.
            Mesh rim = ProceduralMeshes.Ring(PadBottomRadius, PadBottomRadius + RimWidth, RimThickness);
            if (rim != null)
            {
                GameObject rimGo = new GameObject("PadRim");
                rimGo.layer = gameObject.layer;
                rimGo.transform.SetParent(transform, false);
                rimGo.transform.localPosition = new Vector3(0f, RimY, 0f);
                rimGo.AddComponent<MeshFilter>().sharedMesh = rim;
                rimGo.AddComponent<MeshRenderer>().sharedMaterial = Materials.Solid("teleporter");
            }

            // The inlaid track. Emissive at the idle energy the ring uses, so it
            // is present but quiet until the segments above it light.
            Mesh track = ProceduralMeshes.Ring(TrackInnerRadius, TrackOuterRadius, TrackThickness);
            if (track != null)
            {
                GameObject trackGo = new GameObject("PadTrack");
                trackGo.layer = gameObject.layer;
                trackGo.transform.SetParent(transform, false);
                trackGo.transform.localPosition = new Vector3(0f, TrackY, 0f);
                trackGo.AddComponent<MeshFilter>().sharedMesh = track;
                _trackRenderer = trackGo.AddComponent<MeshRenderer>();
                _trackRenderer.sharedMaterial = Materials.Solid("teleporter_ring", TrackIdleEnergy);
            }

            BuildChargeSegments();
        }

        /// <summary>
        /// One arc per required battery, evenly spaced around the track with a
        /// gap between them, so a player counts segments rather than reading a
        /// label. Built once at Setup time because the requirement is fixed for
        /// the level; only their MATERIAL changes as batteries go in.
        ///
        /// Zero and one required are both real cases in the catalogue and both
        /// have to look deliberate: with one segment the arc is most of the
        /// circle, and with none there is no readout at all and the track alone
        /// carries the glow.
        /// </summary>
        private void BuildChargeSegments()
        {
            _chargeSegments = null;
            if (_required <= 0)
            {
                return;
            }

            // Each segment gets its share of the circle minus a gap, so the
            // divisions are visible. A single segment still leaves a gap, or it
            // would close into a plain band and count as nothing.
            float share = 1f / _required;
            float arc = Mathf.Max(share - SegmentGapTurns, share * 0.35f);
            Mesh mesh = ProceduralMeshes.Ring(
                SegmentInnerRadius, SegmentOuterRadius, SegmentThickness, 24, arc);
            if (mesh == null)
            {
                return;
            }

            _chargeSegments = new MeshRenderer[_required];
            for (int i = 0; i < _required; i++)
            {
                GameObject go = new GameObject("ChargeSegment");
                go.layer = gameObject.layer;
                go.transform.SetParent(transform, false);
                go.transform.localPosition = new Vector3(0f, SegmentY, 0f);
                // Spread around the circle. The rotation is about y only, so the
                // one z mirror of this port has nothing to say about it, and the
                // segments read the same way whichever side the player stands.
                go.transform.localRotation = Quaternion.Euler(0f, (i * share) * 360f, 0f);
                go.transform.localScale = Vector3.one;
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                _chargeSegments[i] = go.AddComponent<MeshRenderer>();
            }
        }

        /// <summary>
        /// The pad light of PRD_VISUAL 4.4 (V-LIGHT-03): a soft indigo pool at the
        /// exit, so a charged teleporter is a warm spot in the level even seen
        /// from behind. A plain child built once here, exactly like the ring and
        /// the label, so it has their lifetime: it goes down with the pad when
        /// Main tears the level down and it rides the rewind graveyard whole.
        /// The intensity is not set from here; <see cref="Refresh"/> owns it,
        /// because the charge is the only thing that moves it.
        /// <para>
        /// One point light per level, and the PC renderer is Forward+ (its
        /// m_RenderingMode is 2), where the per object additional light limit does
        /// not apply at all. The mobile renderer is plain forward and does cap at
        /// four lights per object, which one pad light is nowhere near.
        /// </para>
        /// </summary>
        private void BuildPadLight()
        {
            GameObject lightGo = new GameObject("PadLight");
            // Keeping the picture studio out of it. The exclusion that actually
            // bites is the coarse one PhotoSnaps documents: a light whose OBJECT
            // layer falls outside a camera's culling mask is dropped at culling
            // time, and the snap camera sees the PhotoStudio layer and nothing
            // else. Taking the root's layer (Interact, set at the top of Build)
            // keeps that decision in one place, and it is free: a light carries no
            // collider, so sitting on the interaction layer cannot be raycast.
            lightGo.layer = gameObject.layer;
            lightGo.transform.SetParent(transform, false);
            // On the axis of the pad, so the one z mirror has nothing to flip.
            lightGo.transform.localPosition = new Vector3(0f, PadLightY, 0f);

            _padLight = lightGo.AddComponent<Light>();
            _padLight.type = LightType.Point;
            _padLight.range = PadLightRange;
            _padLight.color = Palette.Get("teleporter_ring");
            // Refresh overwrites this the moment a count is known. Starting idle
            // rather than at zero means a pad whose Setup never ran is still lit.
            _padLight.intensity = PadLightIntensityIdle;
            // Shadows off, as PRD_VISUAL fixes: a shadow casting point light costs
            // six shadow map faces for a glow nobody reads as a shadow, and the
            // pillar and the cells would stripe the very pool they stand in.
            _padLight.shadows = LightShadows.None;
            // The same belt the level sun wears (SceneEnvironment.ApplySun), for
            // the day the pipeline starts honouring per light masks.
            _padLight.cullingMask = ~Layers.PhotoStudioMask;
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
