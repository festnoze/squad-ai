using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// A barred cage (PRD section 5.3). ONE static body: breaking a cage
    /// removes the whole thing at once, and the point the breakable test reads
    /// is this transform, the volumetric center of the cage.
    ///
    /// Visuals are bars with gaps, so the loot inside stays visible, while
    /// collision is four full thin walls: neither the player nor the
    /// interaction ray passes between the bars. The lens does (section 7.3),
    /// which is how a steel cage is beaten.
    ///
    /// The cage is not photographable: a lattice copied as a solid block would
    /// seal its own copied battery inside.
    /// </summary>
    public sealed class Cage : MonoBehaviour
    {
        /// Collision walls are 0.12 thick and inset 0.06, so their outer face
        /// is flush with the face of the cage.
        const float WallThickness = 0.12f;
        const float WallInset = 0.06f;

        /// One bar every half meter along a face, two spans minimum.
        const float BarSpan = 0.5f;
        const float BarThickness = 0.07f;
        const float RailThickness = 0.1f;

        /// Rails sit just under the top edge and just above the bottom one.
        const float RailInset = 0.06f;

        // --- V-VFX-03, the break (PRD_VISUAL 4.8) ----------------------------
        //
        // Every number below buys a LOOK and nothing else. The cage itself is
        // retired by the placer on exactly the frame it always was, so the
        // batteries are free before any of this runs; see SpawnDebris.

        /// Rod segments thrown by a break. The item asks for 12 to 20; 16
        /// divides evenly over the four faces, so no face comes out bare.
        const int DebrisPieces = 16;

        /// Total life of the debris. The item's own acceptance criterion is
        /// "the debris is gone within 2 s", so this is the budget minus a
        /// comfortable margin, and the dissolve below fits INSIDE it rather
        /// than after it.
        const float DebrisSeconds = 1.5f;

        /// The white flash, first thing and shortest thing: _CutGlow 1 down to
        /// 0. Long enough to read as an event, short enough that it never hides
        /// what it comments on (the batteries it just freed).
        const float DebrisFlashSeconds = 0.3f;

        /// The exit. Sixteen rods blinking out on one frame reads as a bug, so
        /// the last part of the life dissolves them through _Reveal, which is
        /// the same lavender-white edge the tier uses everywhere else.
        const float DebrisFadeSeconds = 0.45f;

        /// A piece is about a third of a bar: three segments per bar is what
        /// "split into their rod segments" looks like, and a shorter chip stops
        /// reading as a bar at all.
        const float DebrisPieceLength = 0.32f;

        /// How far along a face and how high on it a piece may be drawn, as a
        /// fraction of the face. Kept inside 1 so no piece is born hanging off
        /// an edge of the cage it came from.
        const float DebrisSpreadAlong = 0.9f;
        const float DebrisSpreadUp = 0.72f;

        /// Outward and upward launch speeds, in m/s, as a base plus a random
        /// span. Tuned so the cloud opens wide enough to see the bars separate
        /// and still lands inside the life above.
        const float DebrisOutBase = 1.1f;
        const float DebrisOutSpan = 0.9f;
        const float DebrisUpBase = 1.4f;
        const float DebrisUpSpan = 1.3f;

        /// Tumble, in rad/s.
        const float DebrisSpinBase = 3f;
        const float DebrisSpinSpan = 4f;

        /// Full extents of the cage, kept for the tests and the audit.
        public Vector3 CageSize = Vector3.one;

        /// Palette key the cage was painted with, kept for the same reason.
        public string CageColor = "battery_tip";

        /// Steel: no placement ever breaks it, so it stays out of "breakable".
        public bool Sealed;

        public bool HasRoof = true;

        /// <summary>
        /// The one SHARED material every bar, rail and roof of this cage draws
        /// with, kept from Build so the debris of V-VFX-03 can draw with the
        /// same one. Recomputing it from CageColor would work today and would
        /// be a trap tomorrow: the emission argument Create passes is a function
        /// of "erasable and not sealed", which CageColor only encodes by
        /// accident, so the debris of a lavender cage would come back unlit the
        /// day either rule moved. Holding the reference states the dependency.
        /// </summary>
        Material _skin;

        /// <summary>
        /// Builds a complete cage centered on its own origin. The object comes
        /// back INACTIVE and unparented: the caller places it and enables it,
        /// because the group registration happens on enable and must see the
        /// final value of Sealed.
        /// </summary>
        public static Cage Create(Vector3 size, bool erasable, bool roof, bool isSealed)
        {
            GameObject go = new GameObject("Cage");
            go.SetActive(false);
            go.layer = Layers.World;

            Cage cage = go.AddComponent<Cage>();
            cage.CageSize = size;
            cage.Sealed = isSealed;
            cage.HasRoof = roof;

            // Steel is never lavender: the original folds "and not sealed" into
            // this choice, and repeating it here keeps a hand written
            // definition that declares both readable as steel.
            bool lavender = erasable && !isSealed;
            cage.CageColor = lavender ? "erasable" : (isSealed ? "sealed" : "battery_tip");
            cage.Build(Materials.Solid(cage.CageColor, lavender ? 0.25f : 0f));
            return cage;
        }

        void OnEnable()
        {
            // "cage" is what the world knows about; "breakable" is what a
            // placement may remove. A steel cage is in the first group only.
            Groups.Add(this, Groups.Cage);
            if (!Sealed)
            {
                Groups.Add(this, Groups.Breakable);
            }
        }

        void OnDisable()
        {
            Groups.Remove(this, Groups.Cage);
            if (!Sealed)
            {
                Groups.Remove(this, Groups.Breakable);
            }

            // AFTER the group work, deliberately: the world's answer to "is the
            // cage gone" must already be final when a purely visual object is
            // created, and the PlayMode probe reads that answer three physics
            // steps later.
            if (BrokenByPlacement())
            {
                SpawnDebris();
            }
        }

        /// <summary>
        /// Whether this deactivation is a BREAK rather than a teardown, which is
        /// the one question OnDisable has to answer and cannot ask anyone.
        ///
        /// A cage is deactivated for exactly two reasons. The placer breaks it,
        /// through Rewind.Retire, which pulls the node OUT of the level tree
        /// into the inactive graveyard and only then deactivates it (see
        /// Rewind.RetireInternal: the SetParent comes before the SetActive, so
        /// the new parent is already in place by the time this runs). Or the
        /// level goes away, and Main.ClearLevel DestroyImmediates the cage while
        /// it is still hanging under the level root. So "no longer under the
        /// level root" IS "retired", and nothing else has to be tracked.
        ///
        /// The three guards in front of it are the ways that reading goes wrong:
        ///
        ///  - a rewind UNDOING a spawn also retires nodes, and a rewind that
        ///    spat out a cloud of bars while it was putting the cage back would
        ///    be the exact bug this item must not ship;
        ///  - at application quit the level root may be destroyed before this
        ///    cage, and a destroyed Transform compares equal to null, which is
        ///    what the null check catches. Without it the whole level's cages
        ///    would each spawn debris into a scene that is being torn down;
        ///  - EditMode tests and tooling run with no Rewind at all (Retire
        ///    falls back on a real destroy there), and outside play mode
        ///    nothing animates anyway.
        ///
        /// Sealed is checked first and it is belt and braces: a steel cage is
        /// never in "breakable", so the placer can never retire one, and A
        /// STEEL CAGE MUST NEVER BREAK AT ALL. Stating it here means that stays
        /// true even if some future caller retires a cage by hand.
        /// </summary>
        bool BrokenByPlacement()
        {
            if (Sealed || !Application.isPlaying)
            {
                return false;
            }
            Rewind rewind = Rewind.Instance;
            if (rewind == null || rewind.IsRewinding)
            {
                return false;
            }
            Transform levelRoot = rewind.LevelRoot;
            if (levelRoot == null)
            {
                return false;
            }
            return !transform.IsChildOf(levelRoot);
        }

        /// <summary>
        /// The visual half of V-VFX-03: a separate object of rod segments that
        /// flashes, tumbles and dissolves where the cage stood.
        ///
        /// SEPARATE is the whole design. The real cage is already retired, out
        /// of every group and out of physics, and its batteries are already
        /// reachable; this adds a thing to LOOK at and changes nothing about
        /// what the world says. In particular the debris:
        ///
        ///  - joins NO group (the item says so in as many words), so every
        ///    Groups.Count the probe reads is the number it read before;
        ///  - carries NO collider, so no query in the game can find it. That is
        ///    stronger than a layer would be and it had to be: the interaction
        ///    ray casts WorldMask | InteractMask with QueryTriggerInteraction
        ///    .Collide and keeps the CLOSEST hit, so a debris collider on either
        ///    of those layers would swallow the prompt of the battery it just
        ///    uncaged, and the ground SphereCast casts WorldMask, so one under
        ///    the player's feet would become floor to stand on. Interact and
        ///    PhotoStudio are the only layers that collide with nothing (see
        ///    Layers and the matrix it documents) and the ray searches the first
        ///    while the main camera culls the second, so no existing layer both
        ///    hides from queries and shows on screen. With no collider the layer
        ///    is free to be World, which is what makes the pieces light and draw
        ///    exactly like the bars they came from;
        ///  - is destroyed for good, never retired. Rewind.Retire would record
        ///    an undo event, and a rewind past the break would REVIVE the
        ///    debris: a frozen cloud of bars hanging in the air beside the cage
        ///    it came from. Debris is not world state. It is also destroyed on
        ///    sight when a rewind starts, so holding R never leaves bars falling
        ///    around a cage that is coming back whole.
        ///
        /// The pieces are drawn from ProceduralMeshes.Rod at the bars' own
        /// radius, so one cached mesh serves all sixteen and they match the
        /// forged bars of V-GEO-05 rather than looking like a second material.
        /// </summary>
        void SpawnDebris()
        {
            Transform levelRoot = Rewind.Instance.LevelRoot;
            Vector3 size = CageSize;
            float radius = BarThickness * 0.5f;
            float length = size.y * DebrisPieceLength;

            Mesh mesh = ProceduralMeshes.Rod(radius, length);
            if (mesh == null || _skin == null)
            {
                // Cosmetic and cosmetic only: with no mesh or no material there
                // is nothing to show, and showing nothing is what the game did
                // before this item existed. AddRod has to fall back on a box
                // because a cage with no bars is a gameplay lie; a break with
                // no debris is merely the old break.
                return;
            }

            GameObject root = new GameObject("CageDebris");
            root.layer = Layers.World;
            root.transform.SetParent(levelRoot, false);
            // Under the level root and nowhere else, so Main.ClearLevel takes
            // the debris down with everything else: a load during the 1.5 s
            // must not leave sixteen bars falling through the next level.
            root.transform.SetPositionAndRotation(transform.position, transform.rotation);
            CageDebris debris = root.AddComponent<CageDebris>();
            if (debris == null)
            {
                // Cannot happen with a compiled assembly, and checked anyway
                // because the whole point of this object is that its failure
                // costs a visual event and never a break. Unity swallows an
                // exception thrown in OnDisable and logs it, so an unguarded
                // null here would be a line in the editor log and a cage that
                // still opened: exactly the kind of silence this codebase has
                // paid for before.
                UnityEngine.Object.Destroy(root);
                return;
            }

            // The seed is the cage's PLACE, quantised to the centimetre exactly
            // as Materials.SeedFor quantises its own. UnityEngine.Random would
            // have been wrong twice over: Stage11Reload rebuilds this level and
            // Stage12Rewind undoes a break on it, and the same cage broken again
            // has to throw the same cloud, or a replay of one action looks like
            // a different action. It also keeps the effect out of the global
            // random sequence, which nothing else here perturbs.
            int seed = SeedOf(transform.position);

            float halfX = size.x * 0.5f - WallInset;
            float halfZ = size.z * 0.5f - WallInset;

            for (int i = 0; i < DebrisPieces; i++)
            {
                // Round robin over the four faces rather than a random face, so
                // sixteen draws cannot leave one side of the cage intact.
                int face = i & 3;
                bool alongX = face >= 2;
                float sign = (face & 1) == 0 ? 1f : -1f;

                // Eight independent draws per piece, each used ONCE. Sharing a
                // draw between two of them correlates the two: reusing the
                // height draw for the outward speed, which a first pass did,
                // made every high piece fly further and the cloud came out as a
                // visible diagonal instead of a scatter.
                int draw = i * 8;

                // Both are FRACTIONS of the face, centred on its middle.
                float alongFraction = (Hash01(seed, draw) - 0.5f) * DebrisSpreadAlong;
                float riseFraction = (Hash01(seed, draw + 1) - 0.5f) * DebrisSpreadUp;

                // Design space, like every authored offset in this file, so the
                // one mirror on z applies here too and exactly once.
                Vector3 designPos = alongX
                    ? new Vector3(size.x * alongFraction, size.y * riseFraction, halfZ * sign)
                    : new Vector3(halfX * sign, size.y * riseFraction, size.z * alongFraction);
                Vector3 designOut = alongX
                    ? new Vector3(0f, 0f, sign)
                    : new Vector3(sign, 0f, 0f);

                GameObject piece = new GameObject("Bar");
                piece.layer = Layers.World;
                piece.transform.SetParent(root.transform, false);
                piece.transform.localPosition = DesignSpace.ToUnity(designPos);
                // Unit scale, for the reason AddRod states at length: a
                // non-uniform scale turns a round section into an ellipse and
                // skews the normals the triplanar sampling reads.
                piece.transform.localScale = Vector3.one;
                // The starting tilt is drawn from a distribution symmetric about
                // zero, which is why it does NOT go through DesignSpace: the
                // mirror maps that distribution onto itself, so routing it would
                // be ceremony without meaning. Every offset above, which is not
                // symmetric, does go through it.
                piece.transform.localRotation = Quaternion.Euler(
                    (Hash01(seed, draw + 2) - 0.5f) * 50f,
                    Hash01(seed, draw + 3) * 360f,
                    (Hash01(seed, draw + 4) - 0.5f) * 50f);

                piece.AddComponent<MeshFilter>().sharedMesh = mesh;
                piece.AddComponent<MeshRenderer>().sharedMaterial = _skin;

                // The Rigidbody is added AFTER the pose is written, and the
                // order matters: this project runs with autoSyncTransforms OFF
                // (ProjectSettings/DynamicsManager m_AutoSyncTransforms: 0), so
                // a Transform written after the body existed would move the
                // picture and leave the physics pose behind. A body created on
                // a placed Transform reads that Transform once, here, and from
                // then on the pose is written through body.position.
                Rigidbody body = piece.AddComponent<Rigidbody>();
                // Interpolated because the tumble is watched for a second and a
                // half and the physics rate is not the frame rate.
                body.interpolation = RigidbodyInterpolation.Interpolate;

                // Velocity is SET, not applied as an impulse. With no collider a
                // piece never resolves a contact, so its mass is a number
                // nothing reads, and stating the speed says what the effect
                // actually promises instead of hiding it behind a mass.
                Vector3 designVelocity =
                    designOut * (DebrisOutBase + DebrisOutSpan * Hash01(seed, draw + 5))
                    + new Vector3(0f, DebrisUpBase + DebrisUpSpan * Hash01(seed, draw + 6), 0f);
                body.linearVelocity = root.transform.TransformDirection(DesignSpace.ToUnity(designVelocity));

                // The tumble axis reuses the three tilt draws, which is the one
                // reuse that is meant: a piece that starts leaning one way
                // spinning about that same way looks like one bar that was
                // twisted off, and three more draws would only make it look
                // shaken.
                Vector3 axis = new Vector3(
                    Hash01(seed, draw + 2) - 0.5f,
                    Hash01(seed, draw + 3) - 0.5f,
                    Hash01(seed, draw + 4) - 0.5f);
                axis = axis.sqrMagnitude > 1e-6f ? axis.normalized : Vector3.right;
                body.angularVelocity = axis * (DebrisSpinBase + DebrisSpinSpan * Hash01(seed, draw + 7));
            }

            // The floor the pieces settle on is the cage's own bottom face,
            // which is where a cage stands: CageDef.Pos is the centre of the
            // cage FLOOR and this transform sits half a cage above it. A plane
            // is enough because it is the only contact 1.5 s of falling ever
            // reaches, and it is the version that needs no collider.
            debris.Begin(transform.position.y - size.y * 0.5f, length * 0.5f, radius,
                DebrisSeconds, DebrisFlashSeconds, DebrisFadeSeconds);
        }

        /// <summary>
        /// An INT seed for the draws below, from a world position quantised to
        /// the centimetre. Materials.SeedFor answers the same question for the
        /// shader and returns a fraction; a stream of draws needs the whole
        /// hash, so the mixing is repeated here rather than the result rounded
        /// back into an int, which would throw away most of what makes two
        /// neighbouring cages differ.
        /// </summary>
        static int SeedOf(Vector3 worldPosition)
        {
            int x = Mathf.RoundToInt(worldPosition.x * 100f);
            int y = Mathf.RoundToInt(worldPosition.y * 100f);
            int z = Mathf.RoundToInt(worldPosition.z * 100f);
            unchecked
            {
                uint h = 2166136261u;
                h = (h ^ (uint)x) * 16777619u;
                h = (h ^ (uint)y) * 16777619u;
                h = (h ^ (uint)z) * 16777619u;
                return (int)h;
            }
        }

        /// <summary>
        /// One deterministic draw in [0, 1) from a seed and an index. Pure: the
        /// same pair always gives the same number, on a reload, on a rewound and
        /// repeated break, and in any order the caller asks for them.
        /// </summary>
        static float Hash01(int seed, int index)
        {
            unchecked
            {
                uint h = (uint)seed ^ ((uint)index * 2654435761u);
                // The same avalanche Materials.SeedFor ends on, and for the same
                // reason: FNV style mixing correlates the HIGH bits of nearby
                // inputs, and the high bits are the ones a fraction is read off.
                h ^= h >> 16;
                h *= 2246822507u;
                h ^= h >> 13;
                h *= 3266489909u;
                h ^= h >> 16;
                return (h & 0x00FFFFFFu) / 16777216f;
            }
        }

        void Build(Material material)
        {
            _skin = material;
            Vector3 size = CageSize;
            float halfX = size.x * 0.5f - WallInset;
            float halfZ = size.z * 0.5f - WallInset;

            AddWall(new Vector3(halfX, 0f, 0f), new Vector3(WallThickness, size.y, size.z), false, material);
            AddWall(new Vector3(-halfX, 0f, 0f), new Vector3(WallThickness, size.y, size.z), false, material);
            AddWall(new Vector3(0f, 0f, halfZ), new Vector3(size.x, size.y, WallThickness), true, material);
            AddWall(new Vector3(0f, 0f, -halfZ), new Vector3(size.x, size.y, WallThickness), true, material);

            if (HasRoof)
            {
                AddCollider(new Vector3(size.x, WallThickness, size.z), new Vector3(0f, size.y * 0.5f - WallInset, 0f));
                AddBox("Roof", new Vector3(size.x, 0.1f, size.z), new Vector3(0f, size.y * 0.5f - 0.05f, 0f), material);
            }
        }

        /// One face: a full invisible wall for physics, then the bars and the
        /// two rails that make it read as a cage.
        void AddWall(Vector3 offset, Vector3 wall, bool alongX, Material material)
        {
            AddCollider(wall, offset);

            float span = alongX ? wall.x : wall.z;
            int barCount = Mathf.Max((int)(span / BarSpan), 2);
            for (int i = 0; i <= barCount; i++)
            {
                float t = -span * 0.5f + span * (float)i / (float)barCount;
                Vector3 along = alongX ? new Vector3(t, 0f, 0f) : new Vector3(0f, 0f, t);
                AddRod("Bar", BarThickness * 0.5f, wall.y, offset + along, material);
            }

            Vector3 railSize = alongX
                ? new Vector3(span, RailThickness, RailThickness)
                : new Vector3(RailThickness, RailThickness, span);
            AddBox("Rail", railSize, offset + new Vector3(0f, wall.y * 0.5f - RailInset, 0f), material);
            AddBox("Rail", railSize, offset + new Vector3(0f, -wall.y * 0.5f + RailInset, 0f), material);
        }

        /// <summary>
        /// A round bar (PRD_VISUAL 4.6 V-GEO-05): the cage reads as forged
        /// rather than as a lattice of little boxes.
        ///
        /// COLLISION IS UNTOUCHED, and that is the whole constraint on this
        /// item. A cage's collision is the four thin WALL boxes plus the roof,
        /// added by AddCollider; the bars have never had any. Gameplay PRD 7.3
        /// depends on the camera LENS passing between the bars while the player
        /// and the interaction ray do not, and PlayMode Stage19ThroughTheBars
        /// measures exactly that. So this changes what a bar looks like and
        /// nothing else: no collider, and BarThickness, BarSpan, RailThickness,
        /// RailInset, WallThickness and WallInset all keep their values.
        ///
        /// The radius is HALF BarThickness, so a rod is inscribed in the square
        /// the box used to occupy. That is deliberately less metal than an
        /// equal-area rod (which would be about 0.0395 for a 0.07 square): a bar
        /// that grew when it went round would start eating the gaps the lens has
        /// to pass through, and the gaps are gameplay.
        ///
        /// Built at its REAL SIZE and left at unit scale, unlike AddBox which
        /// scales a unit primitive. Two reasons, both learned in Tier 2: a
        /// non-uniform scale on a round section turns the circle into an ellipse,
        /// and it skews the normals, which breaks the triplanar sampling
        /// Viewpoint/Surface does from world position.
        /// </summary>
        void AddRod(string name, float radius, float height, Vector3 designLocalPos, Material material)
        {
            Mesh mesh = ProceduralMeshes.Rod(radius, height);
            if (mesh == null)
            {
                // A null mesh would leave a cage with no visible bars, which
                // reads as "the loot is not caged" and is a gameplay lie rather
                // than a cosmetic fault. Fall back on the box this replaced.
                AddBox(name, new Vector3(radius * 2f, height, radius * 2f), designLocalPos, material);
                return;
            }

            GameObject rod = new GameObject(name);
            rod.layer = Layers.World;
            rod.transform.SetParent(transform, false);
            // Through the one mirror like every other authored offset. The cage
            // is symmetric so it changes nothing here, but a position that
            // skipped it would be the one that bites when a cage is not.
            rod.transform.localPosition = DesignSpace.ToUnity(designLocalPos);
            rod.transform.localScale = Vector3.one;
            rod.AddComponent<MeshFilter>().sharedMesh = mesh;
            rod.AddComponent<MeshRenderer>().sharedMaterial = material;
        }

        /// Several box colliders on the same GameObject: four walls and a roof,
        /// but a single body.
        void AddCollider(Vector3 size, Vector3 designCenter)
        {
            BoxCollider box = gameObject.AddComponent<BoxCollider>();
            box.size = size;
            box.center = DesignSpace.ToUnity(designCenter);
        }

        /// Decoration only. The cage is symmetric, so the mirror on z changes
        /// nothing here, but authored offsets go through it like every other
        /// position rather than being special cased.
        void AddBox(string name, Vector3 size, Vector3 designLocalPos, Material material)
        {
            GameObject box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.name = name;
            box.layer = Layers.World;

            // CreatePrimitive hands out a collider; the walls above are the
            // only collision a cage has. This runs while the cage is being
            // built, never on a live world object. Disabling comes first
            // because Destroy only bites at the end of the frame, and a bar
            // that collides for one frame is a bar the player can stand on.
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

            box.transform.SetParent(transform, false);
            box.transform.localPosition = DesignSpace.ToUnity(designLocalPos);
            box.transform.localScale = size;
            box.GetComponent<MeshRenderer>().sharedMaterial = material;
        }
    }

    /// <summary>
    /// The falling half of V-VFX-03 (PRD_VISUAL 4.8): it flashes the rod
    /// segments white, lets them tumble, settles them on the ground plane it is
    /// handed and dissolves them away, then destroys itself.
    ///
    /// IT LIVES IN Cage.cs ON PURPOSE. It is the cage's own effect, nothing
    /// else creates it, and it is only ever added by code (Unity requires a
    /// matching file name only for a component dropped in from the editor,
    /// which nothing in this game is: every object here is built at runtime).
    /// Keeping the two together also keeps the one rule of this item, that the
    /// debris is purely visual, readable in a single file.
    ///
    /// It owns NO gameplay state whatsoever. No group, no collider, no rewind
    /// event, no counter. Deleting this component in the middle of a break
    /// would cost the game a visual event and nothing else, which is the
    /// property the tier's acceptance criteria turn on.
    /// </summary>
    sealed class CageDebris : MonoBehaviour
    {
        /// How hard a piece comes back off the ground plane, and how much of its
        /// slide and its spin the plane eats per touch. A cage's bars are heavy
        /// and land dead, so both are low: this is a clatter, not a bounce.
        const float Restitution = 0.32f;
        const float GroundDrag = 0.6f;

        /// The two Tier 4 floats of Viewpoint/Surface, pushed per RENDERER so
        /// the sixteen pieces keep sharing the ONE material the factory cached
        /// for the cage (PRD_VISUAL 3.4 requires that material to stay shared
        /// with the picture studio, and a per piece copy would break the
        /// identity outright). ErasableBlock declares the same two ids for the
        /// same reason: they are per instance values and never live on an
        /// asset.


        Rigidbody[] _bodies;
        MeshRenderer[] _renderers;
        float[] _seeds;

        /// World y of the ground, and the half extents of a piece: the height
        /// a centre may not go below depends on how the piece is lying, so the
        /// plane is stored as the ground plus the shape rather than as one
        /// number. See FixedUpdate.
        float _ground;
        float _halfLength;
        float _radius;

        float _left;
        float _life;
        float _flash;
        float _fade;

        /// Last values pushed to the block, so the middle of the life (glow
        /// already 0, dissolve not started) pushes nothing at all.
        float _glowSent = -1f;
        float _revealSent = -1f;

        /// <summary>
        /// Takes over once the pieces are built and launched. Called last so
        /// the flash is on the renderers BEFORE the first frame is drawn: a
        /// break whose flash started one frame late would read as two events.
        /// </summary>
        public void Begin(float groundY, float halfLength, float radius, float life,
            float flash, float fade)
        {
            _ground = groundY;
            _halfLength = halfLength;
            _radius = radius;
            _life = life;
            _left = life;
            _flash = flash;
            _fade = fade;

            _bodies = GetComponentsInChildren<Rigidbody>();
            _renderers = GetComponentsInChildren<MeshRenderer>();
            // One seed per renderer, from where the piece starts, so the sixteen
            // dissolves are sixteen different noise fields instead of one shape
            // repeated. Materials.SeedFor is the same function the rest of the
            // game seeds its jitter with.
            _seeds = new float[_renderers.Length];
            for (int i = 0; i < _renderers.Length; i++)
            {
                _seeds[i] = Materials.SeedFor(_renderers[i].transform.position);
            }
            Push(1f, 1f);
        }

        /// <summary>
        /// The ground plane, and the only contact the debris has. Run in
        /// FixedUpdate and so BEFORE the physics step, so the pose it writes is
        /// what PhysX integrates from rather than a correction applied after the
        /// fact, which is what would make the pieces jitter on the floor.
        ///
        /// A plane instead of colliders because colliders are exactly what this
        /// object must not have (see Cage.SpawnDebris), and because a cage
        /// stands on a floor: over 1.5 s the pieces reach the ground and
        /// nothing else.
        /// </summary>
        void FixedUpdate()
        {
            if (_bodies == null)
            {
                return;
            }
            for (int i = 0; i < _bodies.Length; i++)
            {
                Rigidbody body = _bodies[i];
                if (body == null)
                {
                    continue;
                }
                // The lowest point of a cylinder of half length h and radius r
                // whose axis makes cos c with world up sits h*|c| + r*sqrt(1-c*c)
                // under its centre. Exact, three lines, and the difference
                // between bars that LIE on the ground and bars that stand
                // buried in it to the waist: the pieces tumble, so a plane at a
                // fixed radius would be right only for the ones that happen to
                // land flat.
                // body.rotation and not transform.up: with interpolation on,
                // the Transform carries a RENDER pose that is a fraction of a
                // step away from the physics one, and the rigidbody's own
                // rotation is the pose this step is about to integrate.
                float cosine = (body.rotation * Vector3.up).y;
                float reach = _halfLength * Mathf.Abs(cosine)
                    + _radius * Mathf.Sqrt(Mathf.Max(0f, 1f - cosine * cosine));
                float floor = _ground + reach;

                Vector3 position = body.position;
                if (position.y >= floor)
                {
                    continue;
                }
                position.y = floor;
                Vector3 velocity = body.linearVelocity;
                if (velocity.y < 0f)
                {
                    velocity.y = -velocity.y * Restitution;
                }
                velocity.x *= GroundDrag;
                velocity.z *= GroundDrag;
                body.position = position;
                body.linearVelocity = velocity;
                body.angularVelocity = body.angularVelocity * GroundDrag;
            }
        }

        /// <summary>
        /// Drives the look and the clock.
        ///
        /// Time.deltaTime and NOT unscaledDeltaTime, which is the opposite of
        /// what Hud.Fade does and for a reason worth writing down: the fade has
        /// to keep running when the game does not, while this object RIDES the
        /// physics it is falling under. On a slowed or stopped clock, bars that
        /// hang frozen in the air are right and bars that dissolve out of a
        /// frozen world are wrong, and the 2 s the item asks for is 2 s of the
        /// same game time the fall is measured in. Nothing in this game touches
        /// Time.timeScale today, so the two agree anyway.
        /// </summary>
        void Update()
        {
            // A rewind is putting the cage back whole. Bars still falling around
            // it would be the effect contradicting the world, and the debris is
            // off the undo track precisely so that it can just go.
            Rewind rewind = Rewind.Instance;
            if (rewind != null && rewind.IsRewinding)
            {
                Destroy(gameObject);
                return;
            }

            _left -= Time.deltaTime;
            if (_left <= 0f)
            {
                // Destroy and never Rewind.Retire: retiring records an undo
                // event, and undoing it would REVIVE this cloud in mid air
                // beside the cage it came from. Debris is not world state.
                Destroy(gameObject);
                return;
            }

            float elapsed = _life - _left;
            float glow = _flash > 0f ? Mathf.Clamp01(1f - elapsed / _flash) : 0f;
            float reveal = _fade > 0f ? Mathf.Clamp01(_left / _fade) : 1f;
            if (glow != _glowSent || reveal != _revealSent)
            {
                Push(glow, reveal);
            }
        }

        /// <summary>
        /// Pushes the per instance floats. EVERY float on EVERY call, because
        /// SetPropertyBlock replaces the block WHOLE: a block carrying only
        /// _CutGlow would erase the _Seed beside it, and the dissolve would jump
        /// to a different noise field on the frame the flash ended.
        /// ErasableBlock.PushInstanceBlock says the same thing at length.
        /// </summary>
        void Push(float glow, float reveal)
        {
            _glowSent = glow;
            _revealSent = reveal;
            if (_renderers == null)
            {
                return;
            }
            for (int i = 0; i < _renderers.Length; i++)
            {
                MeshRenderer renderer = _renderers[i];
                if (renderer == null)
                {
                    continue;
                }
                MaterialPropertyBlock block = new MaterialPropertyBlock();
                block.SetFloat(Materials.SeedId, _seeds[i]);
                block.SetFloat(Materials.CutGlowId, glow);
                block.SetFloat(Materials.RevealId, reveal);
                renderer.SetPropertyBlock(block);
            }
        }
    }
}
