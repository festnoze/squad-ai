using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// Collectible battery. The origin is the BASE of the battery so level data
    /// can place it directly on a floor. A battery duplicated out of a photo uses
    /// this very same component: a copy is a normal battery.
    ///
    /// A SEALED battery ("pile plombee") is worth exactly as much to a teleporter,
    /// but film does not print it: it stays out of the "copyable_battery" group
    /// the camera reads, so framing it copies nothing. It says so without a word,
    /// in the language the ground already speaks: it is leaden grey instead of
    /// amber, it casts no amber pool on the floor it stands on, and it is inert
    /// (it neither bobs nor turns while the others do).
    /// </summary>
    public sealed class Battery : MonoBehaviour, IInteractable
    {
        // Every number below comes from PRD 5.4.
        private const float BodyRadius = 0.16f;
        private const float BodyHeight = 0.5f;
        private const float BodyY = 0.35f;
        private const float TipRadius = 0.06f;
        private const float TipHeight = 0.08f;
        private const float TipY = 0.64f;
        private const float TriggerRadius = 0.55f;
        private const float BobSpeed = 2f;
        private const float BobBase = 0.08f;
        private const float BobAmplitude = 0.06f;
        private const float SpinSpeed = 1.2f;

        // Phase hash from the world position: batteries dropped on a grid must not
        // bob in unison, so x and z are weighted by two unrelated factors.
        private const float PhaseWeightX = 1.7f;
        private const float PhaseWeightZ = 2.3f;

        // The amber pool under a LIVE battery, from PRD_VISUAL 4.4 V-LIGHT-04.
        // The range is deliberately short: this is a pool on the floor the
        // battery stands on and not a lamp that lights the room, which is also
        // what keeps it affordable when a level holds five of them at once.
        private const float GlowRange = 1.6f;
        private const float GlowIntensity = 0.5f;

        // V-PROP-01, the cell as an object. Look decisions, no part of PRD 5.4,
        // and none of them touches the trigger radius or the bob.
        //
        // BandProud is how far the band and the cap stand out from the body:
        // 8 mm on a 16 cm radius, enough to catch a highlight and read as a
        // wrap rather than as a painted stripe, small enough that the
        // silhouette is still the cylinder the original had.
        private const float BandProud = 0.008f;
        private const float BandHeight = 0.19f;

        /// <summary>
        /// Emission of the label band on a LIVE cell. Lower than the body's 0.8
        /// so the band reads as paper over a glowing shell; not zero, or it
        /// would read as a dark belt cutting the cell in half and break the
        /// "amber, glowing" tell of gameplay PRD 5.1.
        /// </summary>
        private const float BandEnergy = 0.35f;

        // The crimped metal cap at the top of the body. Inner radius leaves the
        // terminal room to sit proud of it.
        private const float CapHeight = 0.05f;
        private const float CapInnerRadius = 0.075f;

        // V-VFX-04 and V-ANIM-02, and EVERY ONE OF THEM IS GATED ON IsSealed.
        // That is not tidiness, it is the rule of PRD_VISUAL 3.1: "live amber
        // stays the only thing that is warm and animated among pickups, lead
        // stays still and cold". A leaden cell gets no burst, no dust and no
        // breath, and the player learns from the MISSING event that no film
        // prints it, exactly as they learn it from the missing amber pool.

        /// <summary>
        /// V-VFX-04 asks for "a brief amber burst of 8 sparks toward the
        /// camera". Eight comes from the item and is not rounded up: this is a
        /// comment on a pickup, not a firework.
        /// </summary>
        private const int SparkCount = 8;

        /// <summary>
        /// The whole burst is over in a third of a second. "Instant" is the
        /// word the item uses for the action, and an effect that outlasts the
        /// player's next step would start commenting on the wrong moment.
        /// </summary>
        private const float SparkLife = 0.32f;

        // 1.9 m/s over 0.32 s is about 60 cm of travel, which is a third of the
        // 1.7 m interaction reach: the sparks come at the eye and die before
        // they reach it, so they never wash over the screen.
        private const float SparkSpeed = 1.9f;
        private const float SparkSize = 0.05f;

        /// A narrow cone. Wider than about 20 degrees and the burst reads as a
        /// puff around the cell instead of as something thrown at the player.
        private const float SparkConeAngle = 16f;
        private const float SparkAlpha = 0.9f;

        /// <summary>
        /// A little gravity, so the sparks arc instead of flying dead straight.
        /// Small: at 0.35 g over a third of a second they fall about 2 cm, just
        /// enough to bend the line.
        /// </summary>
        private const float SparkGravity = 0.35f;

        // The drop half of V-VFX-04: "the battery lands with a tiny dust ring".
        // Tiny is the operative word. Ten motes, half a second, grey, and a
        // ring barely wider than the cell itself.
        private const int DustCount = 10;
        private const float DustLife = 0.5f;
        private const float DustSpeed = 0.5f;
        private const float DustSize = 0.08f;
        private const float DustRingRadius = 0.14f;
        private const float DustAlpha = 0.18f;

        /// <summary>
        /// The ring is born a few centimetres up, or half of every mote would
        /// spawn under the floor it is meant to be lifting off.
        /// </summary>
        private const float DustLift = 0.03f;

        /// <summary>
        /// A slow rise over the mote's life, in WORLD space (see the comment at
        /// the rotation in <see cref="SpawnDustRing"/>: the emitter is turned on
        /// its face, so its local up is not the world's).
        /// </summary>
        private const float DustRise = 0.12f;

        /// <summary>
        /// How long an effect object outlives the life of its own particles
        /// before it is destroyed. The alternative, ParticleSystemStopAction
        /// .Destroy, hands the decision to the system's own stop detection,
        /// which is one more silent way to leak one object per pickup; a plain
        /// timer is readable and cannot mis-detect.
        /// </summary>
        private const float EffectGrace = 0.25f;

        /// <summary>
        /// V-ANIM-02: "a faint scale breath (plus or minus 1 percent) on live
        /// batteries". One percent is 1.6 mm on the body radius, which is under
        /// the eye's threshold as a size and over it as a MOTION, which is the
        /// whole trick: the cell reads as alive without appearing to change
        /// size. Uniform on all three axes, because Viewpoint/Surface lights
        /// from interpolated normals and samples triplanar from world position,
        /// and a non-uniform scale would skew both (the reason SpawnRing builds
        /// at real size).
        /// </summary>
        private const float BreathAmplitude = 0.01f;

        /// Slower than the bob (2.0) so the two never look like one pulse.
        private const float BreathSpeed = 0.9f;

        private bool _isSealed;
        private Transform _visual;
        private Renderer _bodyRenderer;
        private Renderer _tipRenderer;
        private Light _glow;
        private Renderer _bandRenderer;
        private Renderer _capRenderer;
        private float _bobPhase;
        private float _breathPhase;
        private float _spin;
        private bool _registered;
        private bool _copyableRegistered;

        /// <summary>
        /// One dust ring per battery, ever. It is an INSTANCE field and not a
        /// timer on purpose: a rewind that undoes a drop retires this very
        /// object and putting it back runs OnEnable again, so a flag that
        /// survived the retirement is what keeps the rewind from puffing dust a
        /// second time for a landing that already happened.
        /// </summary>
        private bool _dropAnnounced;

        // Shared decor, built once for the whole game and never per battery.
        private static Material _sparkMaterial;
        private static Material _dustMaterial;
        private static Texture2D _speckSprite;

        public bool IsSealed { get { return _isSealed; } }

        /// <summary>
        /// Level data calls this for the batteries listed under "sealed_batteries".
        /// The caller may run it before or after Awake, so it re-applies the look
        /// and the group membership rather than assuming an order.
        /// </summary>
        public void Setup(bool isSealed)
        {
            _isSealed = isSealed;
            ApplyLook();
            SyncGroups();
        }

        private void Awake()
        {
            Build();
        }

        private void Start()
        {
            // The world position is only final once the builder has moved us, which
            // happens after Awake; Start is the first moment the hash is meaningful.
            Vector3 world = transform.position;
            _bobPhase = Mathf.Repeat(world.x * PhaseWeightX + world.z * PhaseWeightZ, Mathf.PI * 2f);
            // The breath reads the same two weights SWAPPED, so it is hashed
            // from the same position and is just as deterministic (a reload or
            // a rewind rebuilds the identical phase), while never landing on the
            // bob's own phase: two batteries side by side breathe out of step
            // with each other AND out of step with their own bob.
            _breathPhase = Mathf.Repeat(world.x * PhaseWeightZ + world.z * PhaseWeightX, Mathf.PI * 2f);
        }

        private void OnEnable()
        {
            _registered = true;
            Groups.Add(this, Groups.Battery);
            if (!_isSealed)
            {
                // The only group the camera reads: a leaden battery is invisible to film.
                Groups.Add(this, Groups.CopyableBattery);
                _copyableRegistered = true;
            }
        }

        private void OnDisable()
        {
            _registered = false;
            Groups.Remove(this, Groups.Battery);
            if (_copyableRegistered)
            {
                Groups.Remove(this, Groups.CopyableBattery);
                _copyableRegistered = false;
            }
        }

        private void Update()
        {
            if (_isSealed)
            {
                // Dead weight: no float, no spin. Seen next to a live battery, the
                // difference is immediate.
                return;
            }
            if (_visual == null)
            {
                return;
            }
            float dt = Time.deltaTime;
            _bobPhase = Mathf.Repeat(_bobPhase + dt * BobSpeed, Mathf.PI * 2f);
            Vector3 local = _visual.localPosition;
            local.y = BobBase + Mathf.Sin(_bobPhase) * BobAmplitude;
            _visual.localPosition = local;
            _spin += dt * SpinSpeed;
            // The spin is authored in design space, so its sign goes through the
            // one mirror like every other rotation.
            _visual.localRotation = Quaternion.Euler(0f, DesignSpace.YawToUnityDegrees(_spin), 0f);

            // V-ANIM-02, the battery half. It rides the VISUAL node and nothing
            // else: the trigger collider lives on the root with its own radius
            // and centre (gameplay PRD 5.4), so the reach of a pickup is not
            // one percent wider at the top of a breath. A scale is the one thing
            // that could have leaked into gameplay here, and it does not.
            _breathPhase = Mathf.Repeat(_breathPhase + dt * BreathSpeed, Mathf.PI * 2f);
            float breath = 1f + (Mathf.Sin(_breathPhase) * BreathAmplitude);
            _visual.localScale = new Vector3(breath, breath, breath);
        }

        public void Interact(PlayerController player)
        {
            // Read BEFORE anything moves. The retire below reparents this
            // battery into the rewind graveyard, and the burst has to be thrown
            // from where the cell was standing when the player took it.
            Vector3 burstOrigin = transform.position + new Vector3(0f, BodyY, 0f);
            Camera eye = player != null ? player.Camera : null;

            GameState.Instance.CollectBattery(_isSealed);
            // A physically placed battery lives inside a rigid shell: retire the
            // shell, not just the battery, or an empty physics husk would remain.
            Transform parent = transform.parent;
            Rigidbody shell = parent != null ? parent.GetComponent<Rigidbody>() : null;
            if (shell != null)
            {
                Rewind.Retire(shell.gameObject);
            }
            else
            {
                Rewind.Retire(gameObject);
            }

            // LAST, AND DELIBERATELY LAST. Everything above is the gameplay
            // event the probe measures in the frame it happens: the counter, the
            // groups this battery leaves through OnDisable, and the retirement.
            // The burst is a comment on that event and nothing more, so it is
            // spawned after the world is already correct: if this decor ever
            // throws, the pickup has still happened in full.
            SpawnPickupBurst(burstOrigin, eye);
        }

        /// <summary>
        /// The drop half of V-VFX-04: "on drop, the battery lands with a tiny
        /// dust ring". Called by whoever puts a carried battery back on the
        /// ground, once the cell is in place.
        ///
        /// It is a method and not something this component detects on its own,
        /// and that is a decision worth recording. Nothing observable from
        /// inside a battery separates "I was just dropped" from "I was built
        /// with the level": both arrive through Setup and OnEnable, and firing
        /// on OnEnable would puff dust under all five batteries of a level at
        /// load time AND again every time a rewind put a collected one back.
        /// The one thing a battery CAN see by itself, a fall that ends on the
        /// floor, belongs to the photocopied cell, and that one is always
        /// leaden (PhotoContent: film does not print film), so it is gated out
        /// by 3.1 anyway. A caller that knows a drop happened is the honest
        /// signal; <see cref="_dropAnnounced"/> makes it idempotent.
        /// </summary>
        public void NoticeDropped()
        {
            if (_isSealed || _dropAnnounced)
            {
                return;
            }
            _dropAnnounced = true;
            SpawnDustRing(transform.position);
        }

        public string PromptText(PlayerController player)
        {
            return _isSealed ? "E : ramasser la pile plombee" : "E : ramasser la pile";
        }

        private void Build()
        {
            // The interaction ray only sees the Interact layer, and the component it
            // looks for sits on the trigger object itself (PRD 15.3).
            gameObject.layer = Layers.Interact;

            GameObject visualGo = new GameObject("Visual");
            _visual = visualGo.transform;
            _visual.SetParent(transform, false);

            _bodyRenderer = SpawnPart(
                _visual, PrimitiveType.Cylinder, "Body",
                new Vector3(0f, BodyY, 0f),
                // Unity's cylinder primitive is 2 units tall with a radius of 0.5.
                new Vector3(BodyRadius * 2f, BodyHeight * 0.5f, BodyRadius * 2f));
            _tipRenderer = SpawnPart(
                _visual, PrimitiveType.Cylinder, "Tip",
                new Vector3(0f, TipY, 0f),
                new Vector3(TipRadius * 2f, TipHeight * 0.5f, TipRadius * 2f));
            // V-PROP-01: the two pieces that turn two cylinders into a cell you
            // could pick up. Both are decor and both exist on a LEAD battery
            // too: the item is explicit that lead is "identical in shape and
            // unmistakable in nature", so the shape may never be the tell. Only
            // the material and the glow are.
            _bandRenderer = SpawnRing(
                _visual, "LabelBand",
                new Vector3(0f, BodyY, 0f),
                BodyRadius, BodyRadius + BandProud, BandHeight);
            _capRenderer = SpawnRing(
                _visual, "Cap",
                new Vector3(0f, BodyY + (BodyHeight * 0.5f) - (CapHeight * 0.5f), 0f),
                CapInnerRadius, BodyRadius + BandProud, CapHeight);

            _glow = SpawnGlow(_visual);
            ApplyLook();

            SphereCollider trigger = gameObject.AddComponent<SphereCollider>();
            trigger.isTrigger = true;
            trigger.radius = TriggerRadius;
            trigger.center = new Vector3(0f, BodyY, 0f);
        }

        private void ApplyLook()
        {
            if (_bodyRenderer == null || _tipRenderer == null)
            {
                return;
            }
            _bodyRenderer.sharedMaterial = _isSealed
                ? Materials.Solid("battery_sealed")
                : Materials.Solid("battery", 0.8f);
            _tipRenderer.sharedMaterial = Materials.Solid(_isSealed ? "sealed_dark" : "battery_tip");

            // The wrapped label. On a live cell it is the SAME amber as the body
            // at a lower emission, so it reads as printed paper over a glowing
            // shell rather than as a second colour: constraint 3.1 makes amber
            // the tell for a live battery, and a band in some other hue would
            // dilute it. On lead it is the same lead, so the band is only a
            // shape and the cell stays uniformly inert.
            if (_bandRenderer != null)
            {
                _bandRenderer.sharedMaterial = _isSealed
                    ? Materials.Solid("battery_sealed")
                    : Materials.Solid("battery", BandEnergy);
            }
            // The metal top cap: the same dark grey as the terminal, so the two
            // metal parts of the cell agree with each other.
            if (_capRenderer != null)
            {
                _capRenderer.sharedMaterial = Materials.Solid(_isSealed ? "sealed_dark" : "battery_tip");
            }
            if (_glow != null)
            {
                // Live amber stays the only warm and animated thing among the
                // pickups (PRD_VISUAL 3.1): the lead gets no pool at all, and
                // that MISSING warmth on the ground beside a live battery is
                // what teaches the rule, so the absence is the feature.
                //
                // Switched rather than created or destroyed, for the same
                // reason the materials above are re-applied: Setup may land
                // before or after Awake (PlayerController and PhotoContent both
                // configure a battery while it is still inactive), so the look
                // has to be re-appliable in either order.
                _glow.enabled = !_isSealed;
            }
        }

        /// Keeps the copyable group in step when Setup lands after OnEnable.
        private void SyncGroups()
        {
            if (!_registered)
            {
                return;
            }
            if (_isSealed && _copyableRegistered)
            {
                Groups.Remove(this, Groups.CopyableBattery);
                _copyableRegistered = false;
            }
            else if (!_isSealed && !_copyableRegistered)
            {
                Groups.Add(this, Groups.CopyableBattery);
                _copyableRegistered = true;
            }
        }

        /// <summary>
        /// The faint amber pool of PRD_VISUAL 4.4 V-LIGHT-04.
        ///
        /// It hangs under the Visual node rather than under the pickup root, and
        /// that buys two different things at once. It rides the hover bob, so
        /// the glow and the cell stay one object (a bobbing battery whose pool
        /// stayed nailed to the floor would read as two). And it inherits the
        /// exact lifetime of the mesh it belongs to: Rewind.Retire deactivates
        /// the whole subtree, so a collected battery cannot leave a glowing hole
        /// in the air the way a light parented to the level root would, and
        /// reviving the battery brings its pool back with it. Never a light of
        /// its own, tracking the battery from the side.
        /// </summary>
        private static Light SpawnGlow(Transform parent)
        {
            GameObject go = new GameObject("Glow");
            Transform t = go.transform;
            t.SetParent(parent, false);
            // Inside the body, at the height the pickup trigger is centered on:
            // the light is a glow from within the cell, not a lamp floating
            // beside it. Pure y, so the one z mirror has nothing to say here.
            t.localPosition = new Vector3(0f, BodyY, 0f);

            Light light = go.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = Palette.Get("battery");
            light.range = GlowRange;
            light.intensity = GlowIntensity;
            // Five of these can be alive at once and not one of them needs to
            // cast a shadow: the pool on the ground is the whole point, the
            // silhouette is not, and shadow casters are what a point light
            // actually costs.
            light.shadows = LightShadows.None;
            // Camera level exclusion, the same trick the world sun uses: a light
            // sharing no layer with a camera's culling mask is dropped at
            // culling time, so this one never reaches the picture studio.
            // Display mode content gets no lights (PRD_VISUAL 4.4), and a
            // battery standing inside a polaroid must not light the print.
            light.cullingMask = ~Layers.PhotoStudioMask;
            return light;
        }

        /// <summary>
        /// A flat band around the cell (V-PROP-01), built at its REAL SIZE and
        /// left at unit scale, unlike <see cref="SpawnPart"/> which scales a
        /// unit primitive. The reason is the one Tier 2 established: a
        /// non-uniform scale skews the interpolated normals, and Viewpoint/
        /// Surface samples triplanar from world position and lights from those
        /// normals, so a scaled ring would light wrongly all the way round.
        ///
        /// Returns null when the mesh cannot be built, and the caller tolerates
        /// that: a battery missing its label is still a readable battery, and a
        /// null mesh on a renderer would draw magenta.
        /// </summary>
        private static Renderer SpawnRing(Transform parent, string name, Vector3 localPosition,
            float innerRadius, float outerRadius, float height)
        {
            Mesh mesh = ProceduralMeshes.Ring(innerRadius, outerRadius, height, 24);
            if (mesh == null)
            {
                return null;
            }

            GameObject go = new GameObject(name);
            Transform t = go.transform;
            t.SetParent(parent, false);
            // Pure y offsets, so the port's single z mirror has nothing to flip.
            t.localPosition = localPosition;
            t.localScale = Vector3.one;
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            return go.AddComponent<MeshRenderer>();
        }

        private static Renderer SpawnPart(Transform parent, PrimitiveType shape, string name, Vector3 localPosition, Vector3 localScale)
        {
            GameObject go = GameObject.CreatePrimitive(shape);
            go.name = name;
            Collider col = go.GetComponent<Collider>();
            if (col != null)
            {
                // CreatePrimitive always attaches a collider; these parts are pure
                // decoration and the trigger is the only collider wanted. Disabling
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

        // --- V-VFX-04, the two events ---------------------------------------

        /// <summary>
        /// The amber burst of a pickup, thrown at the eye that took the cell.
        ///
        /// It CANNOT live on the battery. Interact retires this object in the
        /// very same frame (the counters and the groups have to be right for a
        /// probe reading the world immediately after), and a deactivated object
        /// simulates nothing: a burst parented here would be a single invisible
        /// frame. So the effect is an INDEPENDENT object, and see
        /// <see cref="NewEffect"/> for where it hangs and why that survives.
        /// </summary>
        private void SpawnPickupBurst(Vector3 origin, Camera eye)
        {
            if (_isSealed)
            {
                // PRD_VISUAL 3.1. The lead is picked up in silence, and the
                // silence is the lesson.
                return;
            }

            // Straight from the cell to the eye, computed from two WORLD
            // positions: the port's single z mirror lives in DesignSpace, on the
            // way in from level data, and has nothing to say about a direction
            // measured here. Up when there is no camera to aim at (a headless
            // probe, a scripted pickup), so the burst is never degenerate.
            Vector3 toEye = eye != null ? eye.transform.position - origin : Vector3.up;
            if (toEye.sqrMagnitude < 0.000001f)
            {
                toEye = Vector3.up;
            }

            GameObject go = NewEffect("BatterySparks", origin,
                Quaternion.LookRotation(toEye.normalized), SparkLife);
            if (go == null)
            {
                return;
            }

            ParticleSystem ps = NewBurst(go, SparkCount, SparkLife, SparkSpeed, SparkSize,
                SparkGravity, SparkMaterial(), SeedFrom(origin));
            if (ps == null)
            {
                return;
            }

            // A narrow cone down the object's forward, which LookRotation just
            // pointed at the eye.
            ParticleSystem.ShapeModule shape = ps.shape;
            shape.enabled = true;
            shape.shapeType = ParticleSystemShapeType.Cone;
            shape.angle = SparkConeAngle;
            // The cell's own radius: the sparks leave the surface of the
            // battery rather than a point inside it.
            shape.radius = BodyRadius;
            ps.Play(true);
        }

        /// <summary>
        /// The tiny dust ring of a drop. Independent of the battery for the
        /// same reason the burst is: the cell can be picked up again a moment
        /// later, and a ring that vanished mid-puff because its parent was
        /// retired would read as a glitch rather than as dust settling.
        /// </summary>
        private void SpawnDustRing(Vector3 basePosition)
        {
            if (_isSealed)
            {
                return;
            }

            // A CIRCLE SHAPE EMITS IN ITS LOCAL XY PLANE, which faces local +z.
            // Turning the emitter a quarter turn back about x lays that plane
            // flat on the floor and points its local +z at the sky. This is not
            // a design-space rotation and does not go through DesignSpace: it is
            // the orientation of a piece of decor, expressed in Unity space
            // where the plane has to end up.
            GameObject go = NewEffect("BatteryDust",
                basePosition + new Vector3(0f, DustLift, 0f),
                Quaternion.Euler(-90f, 0f, 0f), DustLife);
            if (go == null)
            {
                return;
            }

            ParticleSystem ps = NewBurst(go, DustCount, DustLife, DustSpeed, DustSize,
                0f, DustMaterial(), SeedFrom(basePosition));
            if (ps == null)
            {
                return;
            }

            ParticleSystem.ShapeModule shape = ps.shape;
            shape.enabled = true;
            shape.shapeType = ParticleSystemShapeType.Circle;
            shape.radius = DustRingRadius;
            // The rim only, so it is a ring leaving the foot of the cell and
            // not a disc filling under it.
            shape.radiusThickness = 0.35f;
            shape.arc = 360f;

            // WORLD space, and that is the point of the module here: the
            // emitter is lying on its face, so its local up is not up. Asked in
            // local space this would have pushed the ring sideways.
            ParticleSystem.VelocityOverLifetimeModule rise = ps.velocityOverLifetime;
            rise.enabled = true;
            rise.space = ParticleSystemSimulationSpace.World;
            rise.y = new ParticleSystem.MinMaxCurve(DustRise);
            ps.Play(true);
        }

        /// <summary>
        /// A short-lived decor object, and the answer to "where does an effect
        /// live when the thing it comments on is gone".
        ///
        /// It hangs under the LEVEL ROOT, which is what survives a pickup: the
        /// battery is reparented into the rewind graveyard and deactivated in
        /// the same frame, and everything under it goes quiet with it, while the
        /// level root is untouched by a retirement and is torn down with the
        /// level (Main.ClearLevel), so an effect can never outlive its world.
        ///
        /// Four things it deliberately does NOT do:
        ///   - it joins no group, so no camera frustum, no carve and no census
        ///     can find it (film reads groups, PhotoCapture);
        ///   - it carries no collider, so no raycast and no interaction ray can
        ///     touch it;
        ///   - it never goes through Rewind. Neither NoticeSpawn nor Retire:
        ///     a retirement is an UNDOABLE event, so a rewind past a pickup
        ///     would revive the burst and REPLAY it. Object.Destroy on a timer
        ///     is final, and the rewind has nothing to put back;
        ///   - it is not photographed by the studio: it sits on the World layer
        ///     and the studio camera culls everything but PhotoStudio
        ///     (PhotoSnaps), the same layer exclusion the amber pool above uses.
        ///     A polaroid is a promise about geometry and must not contain
        ///     weather.
        ///
        /// Returns null, silently, when there is nothing to show it with: a
        /// headless run has no rasterizer and no level root, and the 101 EditMode
        /// tests must not pay for particles they cannot see.
        /// </summary>
        private static GameObject NewEffect(string name, Vector3 position, Quaternion rotation,
            float particleLife)
        {
            if (SystemInfo.graphicsDeviceType == UnityEngine.Rendering.GraphicsDeviceType.Null)
            {
                return null;
            }
            // Also the play-mode gate: Rewind sets its instance in Awake, so
            // outside play mode there is no host and no Destroy to schedule.
            Transform host = Rewind.Instance != null ? Rewind.Instance.LevelRoot : null;
            if (host == null)
            {
                return null;
            }

            GameObject go = new GameObject(name);
            // Set before the ParticleSystem exists, as everywhere else in this
            // project: a renderer that registered on the wrong layer would be
            // culled by the wrong cameras, and the studio exclusion above is
            // exactly that.
            go.layer = Layers.World;
            go.transform.SetParent(host, false);
            go.transform.SetPositionAndRotation(position, rotation);
            // Its own end, on its own clock. The game never scales time (no
            // Time.timeScale anywhere in this project), so the scaled delay is
            // the unscaled one and needs no Hud.Fade style unscaled handling.
            Destroy(go, particleLife + EffectGrace);
            return go;
        }

        /// <summary>
        /// The part both effects share: one burst of n particles, no loop, and
        /// a deterministic seed.
        ///
        /// EVERY MODULE OF A ParticleSystem IS A STRUCT AND MUST BE WRITTEN
        /// THROUGH. Assigning to a local copy's field only works because the
        /// local variable IS the view onto the system; Render/Atmosphere.cs
        /// carries the long version of this warning.
        /// </summary>
        private static ParticleSystem NewBurst(GameObject go, int count, float life, float speed,
            float size, float gravity, Material material, uint seed)
        {
            if (material == null)
            {
                // No shader means a null material, and a null material draws
                // magenta quads. Better no effect at all.
                return null;
            }

            ParticleSystem ps = go.AddComponent<ParticleSystem>();
            // Stopped while it is configured: a system plays the moment it is
            // added, and one that emits during setup spits its first particles
            // from an unconfigured shape.
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);

            ParticleSystem.MainModule main = ps.main;
            main.duration = life;
            main.loop = false;
            main.startLifetime = life;
            main.startSpeed = speed;
            main.startSize = size;
            main.maxParticles = count;
            main.gravityModifier = gravity;
            main.playOnAwake = false;
            // World, so a particle keeps the trajectory it was given whatever
            // happens to the object that emitted it, and so the dust ring's
            // rise can be asked for in world space without a second thought.
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            // FULL white here and the real colour on the MATERIAL, which is the
            // trap Appendix C.20 records: a start colour reaches the shader as
            // the vertex COLOR stream, and URP's plain Unlit (the fallback taken
            // in a player, where the particle shader can be stripped) declares
            // no COLOR input at all and DISCARDS it. Both shader paths multiply
            // _BaseColor, so tint and alpha live there.
            main.startColor = Color.white;

            ParticleSystem.EmissionModule emission = ps.emission;
            emission.enabled = true;
            // One burst at t = 0 and nothing after: this is an event, not a
            // fountain. rateOverTime stays at zero.
            emission.rateOverTime = 0f;
            emission.SetBursts(new[] { new ParticleSystem.Burst(0f, (short)count) });

            // SHRINK TO NOTHING, and this curve is the one fade that survives
            // the fallback shader. The alpha ramp below rides vertex colour and
            // is dropped there (C.20 again); a size curve is read by the
            // particle SIMULATION, not by the shader, so on either path the
            // particles die by vanishing rather than by popping out at full
            // brightness.
            ParticleSystem.SizeOverLifetimeModule shrink = ps.sizeOverLifetime;
            shrink.enabled = true;
            AnimationCurve fade = new AnimationCurve();
            fade.AddKey(0f, 1f);
            fade.AddKey(1f, 0f);
            shrink.size = new ParticleSystem.MinMaxCurve(1f, fade);

            ParticleSystem.ColorOverLifetimeModule dim = ps.colorOverLifetime;
            dim.enabled = true;
            Gradient gradient = new Gradient();
            gradient.SetKeys(
                new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                new[]
                {
                    new GradientAlphaKey(1f, 0f),
                    new GradientAlphaKey(1f, 0.4f),
                    new GradientAlphaKey(0f, 1f),
                });
            dim.color = new ParticleSystem.MinMaxGradient(gradient);

            ParticleSystemRenderer renderer = go.GetComponent<ParticleSystemRenderer>();
            renderer.renderMode = ParticleSystemRenderMode.Billboard;
            renderer.alignment = ParticleSystemRenderSpace.View;
            renderer.sharedMaterial = material;
            // Eight sparks have no business in the shadow pass.
            renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            renderer.receiveShadows = false;

            // DETERMINISTIC, like the dust of Atmosphere and like the bob phase:
            // the PlayMode probe reloads a level (Stage11) and rewinds one
            // (Stage12), and neither may come back looking different. The seed
            // is hashed from the world position, so it also differs from one
            // battery to the next.
            ps.randomSeed = seed;
            ps.useAutoRandomSeed = false;
            return ps;
        }

        /// <summary>
        /// A stable seed from a world position: the same battery in the same
        /// place always bursts the same way, two batteries never burst
        /// identically.
        ///
        /// Folded through Mathf.Repeat before it becomes an int, because
        /// Mathf.RoundToInt of a large float is not a wrap but a clamp, and a
        /// clamp would hand every distant object the same seed.
        /// </summary>
        private static uint SeedFrom(Vector3 world)
        {
            float mixed = Mathf.Repeat(
                (world.x * 0.7311f) + (world.y * 0.4177f) + (world.z * 0.9137f), 1f);
            return (uint)Mathf.RoundToInt(mixed * 999983f) + 1u;
        }

        /// <summary>
        /// The spark material: amber, straight from the palette key the cell
        /// itself uses, so the burst quotes the colour language of PRD_VISUAL
        /// 3.1 instead of inventing a hue next to it.
        /// </summary>
        private static Material SparkMaterial()
        {
            if (_sparkMaterial == null)
            {
                _sparkMaterial = SpeckMaterial("BatterySpark", Palette.Get("battery"), SparkAlpha);
            }
            return _sparkMaterial;
        }

        /// <summary>
        /// The dust material: the grey of the permanent ground, at a fifth of
        /// the sparks' alpha. Dust is the floor answering, so it takes the
        /// floor's colour and never the cell's amber, which 3.1 reserves for
        /// what is warm and alive.
        /// </summary>
        private static Material DustMaterial()
        {
            if (_dustMaterial == null)
            {
                _dustMaterial = SpeckMaterial("BatteryDust", Palette.Get("platform"), DustAlpha);
            }
            return _dustMaterial;
        }

        /// <summary>
        /// An unlit additive speck material, generated and shared.
        ///
        /// This is the same recipe Render/Atmosphere.cs uses for its dust, and
        /// it is repeated here rather than shared because that one is private to
        /// its own file; the four traps it encodes are worth restating, because
        /// each of them fails SILENTLY and each has already cost this project a
        /// round:
        ///   - the particle shader is not in Always Included Shaders, so it can
        ///     be stripped from a player: fall back to plain Unlit, which is
        ///     included, rather than to null;
        ///   - the tint and the alpha go on _BaseColor, the only input BOTH
        ///     shader paths multiply (Appendix C.20);
        ///   - _Surface and _Blend alone do NOT make a material transparent.
        ///     The blend that ships is _SrcBlend / _DstBlend, and without them
        ///     a speck renders opaque, which is a hard white quad;
        ///   - a billboard with no texture IS a quad, so the round falloff is
        ///     generated below.
        /// </summary>
        private static Material SpeckMaterial(string name, Color tint, float alpha)
        {
            Shader shader = Shader.Find("Universal Render Pipeline/Particles/Unlit");
            if (shader == null)
            {
                shader = Shader.Find("Universal Render Pipeline/Unlit");
            }
            if (shader == null)
            {
                Debug.LogWarning("[Battery] No unlit shader for the pickup burst; it will be silent.");
                return null;
            }

            Material material = new Material(shader);
            material.name = name;
            material.SetColor("_BaseColor", new Color(tint.r, tint.g, tint.b, alpha));
            Texture2D sprite = SpeckSprite();
            material.SetTexture("_BaseMap", sprite);
            if (material.HasProperty("_MainTex"))
            {
                material.SetTexture("_MainTex", sprite);
            }
            material.SetFloat("_Surface", 1f);
            material.SetFloat("_Blend", 1f);
            // SrcAlpha / One: a speck brightens what it passes in front of, in
            // proportion to its falloff, and can never darken it. That is what
            // a spark and a lit mote of dust both do, and it needs no sorting.
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
        /// A soft round speck, 16 px square, generated once and shared by both
        /// effects. Only the alpha matters: the materials above supply the
        /// colour and the level of the falloff.
        ///
        /// Squared falloff, so nothing shows the edge of the disc. Sixteen
        /// pixels is plenty for something a few pixels wide on screen, and
        /// mipmaps are on so a spark at distance resolves to its average rather
        /// than shimmering.
        /// </summary>
        private static Texture2D SpeckSprite()
        {
            if (_speckSprite != null)
            {
                return _speckSprite;
            }

            const int size = 16;
            Texture2D texture = new Texture2D(size, size, TextureFormat.RGBA32, true, false);
            texture.name = "BatterySpeckSprite";
            texture.wrapMode = TextureWrapMode.Clamp;
            texture.filterMode = FilterMode.Bilinear;

            Color32[] pixels = new Color32[size * size];
            float centre = (size - 1) * 0.5f;
            float radius = centre;
            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    float dx = (x - centre) / radius;
                    float dy = (y - centre) / radius;
                    float d = Mathf.Sqrt((dx * dx) + (dy * dy));
                    float a = Mathf.Clamp01(1f - d);
                    a *= a;
                    pixels[(y * size) + x] = new Color32(255, 255, 255, (byte)Mathf.RoundToInt(a * 255f));
                }
            }
            texture.SetPixels32(pixels);
            texture.Apply(true, true);
            _speckSprite = texture;
            return _speckSprite;
        }
    }
}
