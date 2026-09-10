using System.Collections.Generic;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// Builds the 3D content of a photo definition in the LOCAL space of this
    /// node; the placer sets the node's world transform to the placement
    /// anchor, so a prop authored at photo space (0, -1.72, -5) lands 5 m in
    /// front of the eye, whatever the eye is looking at.
    ///
    /// Two modes that must stay geometrically identical (that identity IS the
    /// optical illusion):
    ///
    ///   solid   (display == false): real props. Non loose boxes become
    ///           ErasableBlocks (placed content is itself replaceable by the
    ///           next photo), loose boxes and batteries become rigid bodies
    ///           that fall, the backdrop becomes a thin carvable painted wall.
    ///           The node joins the group "placed_content".
    ///   display (display == true) : the same look, inert. Meshes only: no
    ///           colliders, no groups, no pickups, no rigid bodies. Used by
    ///           PhotoSnaps to render the picture of a photo in an offscreen
    ///           studio without touching gameplay state.
    ///
    /// Everything authored is DESIGN space (x right, y up, -z forward), so
    /// every center goes through DesignSpace.ToUnity on its way to a local
    /// position, and nowhere else.
    ///
    /// Since Tier 4 (V-VFX-01) the solid content also DISSOLVES into place: the
    /// geometry, the colliders, the rigid bodies and the groups are all final on
    /// the frame Setup runs, exactly as before, and only the shader's _Reveal
    /// lags behind for 0.4 s. Nothing about WHEN anything happens moved; see
    /// <see cref="BeginReveal"/> for what that costs and what it must never do.
    /// </summary>
    public sealed class PhotoContent : MonoBehaviour
    {
        /// <summary>
        /// V-VFX-01's dissolve, in seconds. The PRD's number, and the whole of
        /// this effect: content that used to appear instantly now resolves from
        /// a lavender-white edge glow (Viewpoint/Surface adds that band on the
        /// clip threshold) to its final material over this window.
        /// </summary>
        private const float RevealSeconds = 0.4f;

        /// <summary>
        /// The value written on the frame the content is BUILT, before the first
        /// tick of the animation. It is not zero on purpose: the shader clips
        /// every fragment whose reveal field falls below 1 - _Reveal, so a zero
        /// would leave the placement frame showing nothing at all where the
        /// content is, and the frame after it showing a scatter of glow. 0.15
        /// keeps only the peaks of the noise, and since the edge band is 0.16
        /// wide in the same units every surviving pixel is INSIDE the band: the
        /// first frame is the edge glow the item asks for, and no frame of the
        /// effect is empty.
        /// </summary>
        private const float RevealStart = 0.15f;

        /// <summary>
        /// Viewpoint/Surface's dissolve float. ErasableBlock owns its own copy
        /// of this id because it pushes the property itself (see below); a
        /// renderer that belongs to no block is written from here.
        /// </summary>

        /// Thickness of the invisible stairs ramp (PRD 6.6).
        private const float RampThickness = 0.4f;

        /// Thickness of the painted backdrop wall (PRD 6.6).
        private const float BackdropThickness = 0.2f;

        /// The gradient quad hugs the front face of the backdrop block: half
        /// the thickness plus 1 mm, so it never z-fights with the block mesh.
        private const float BackdropQuadOffset = 0.101f;

        /// Physical shell of a placed battery (PRD 6.6).
        private const float BatteryShellMass = 1.5f;

        /// Local offset of the real pickup inside its shell: the Battery has
        /// its origin at the BASE, the shell is centered on the primitive.
        private const float BatteryCellDrop = -0.36f;

        /// Display mode battery: a plain glowing cylinder (PRD 6.6).
        private const float DisplayBatteryDiameter = 0.32f;
        private const float DisplayBatteryHeight = 0.55f;
        private const float DisplayBatteryEmissive = 0.8f;

        /// Default color of a prop whose definition names none (photo_defs.gd).
        private const string DefaultPropColor = "stone";

        private const string DefaultBackdropTop = "sky_top";
        private const string DefaultBackdropBottom = "sky_horizon";

        /// Unity hands out no mesh without an asset, so the built in ones are
        /// grabbed once from throwaway primitives and shared by every content.
        private static Mesh _boxMesh;
        private static Mesh _cylinderMesh;
        private static Mesh _quadMesh;

        private bool _display;
        private bool _solid;
        private bool _grouped;

        /// True once Setup has run, which is what tells a LATER OnEnable apart
        /// from the one AddComponent already fired: the later one is a rewind
        /// revive, and a revive must not replay the dissolve.
        private bool _setupDone;

        /// The blocks and the plain renderers of this content, collected ONCE at
        /// the end of Setup. Two lists because a block must be written through
        /// its own door (ErasableBlock.SetReveal) and a plain renderer directly.
        private ErasableBlock[] _revealBlocks;
        private Renderer[] _revealRenderers;

        /// Reused, so a dissolve does not allocate a block per renderer per
        /// frame.
        private MaterialPropertyBlock _revealProperties;

        private float _revealElapsed;
        private bool _revealing;

        /// <summary>
        /// Builds the content. Call once, right after the component is added.
        /// </summary>
        public void Setup(PhotoDef def, bool display = false)
        {
            _display = display;
            _solid = !display;
            // OnEnable already ran (with _solid still false) when the component
            // was added, so the first registration happens here.
            if (isActiveAndEnabled)
            {
                JoinPlacedContent();
            }
            if (def == null)
            {
                _setupDone = true;
                return;
            }
            List<PhotoProp> props = def.Props;
            if (props != null)
            {
                for (int i = 0; i < props.Count; i++)
                {
                    BuildProp(props[i]);
                }
            }
            if (def.HasBackdrop)
            {
                BuildBackdrop(def.Backdrop);
            }
            _setupDone = true;
            // LAST, and after every collider and every group already exists:
            // the dissolve is the only thing in this file that is allowed to
            // land later than the frame of the placement, and it lands only on
            // material state.
            BeginReveal();
        }

        private void OnEnable()
        {
            JoinPlacedContent();
            // A rewind revive re-enables this node, and Update resumes with it.
            // Undoing a placement must not replay the placement: an object the
            // player is putting BACK is already resolved, so the dissolve is
            // finished here rather than continued. _setupDone is what separates
            // a revive from the OnEnable that AddComponent fired before Setup.
            if (_setupDone && _revealing)
            {
                FinishReveal();
            }
        }

        private void OnDisable()
        {
            // A retired content is deactivated, not destroyed: OnDisable is
            // what takes it out of the registry the way a free would.
            LeavePlacedContent();
        }

        private void JoinPlacedContent()
        {
            if (!_solid || _grouped)
            {
                return;
            }
            Groups.Add(this, Groups.PlacedContent);
            _grouped = true;
        }

        private void LeavePlacedContent()
        {
            if (!_grouped)
            {
                return;
            }
            Groups.Remove(this, Groups.PlacedContent);
            _grouped = false;
        }

        /// <summary>
        /// Arms V-VFX-01's dissolve. THE RULE THIS OBEYS: a visual event never
        /// changes when something happens, only what it looks like. Everything
        /// Setup built above is already final (colliders, rigid bodies, groups,
        /// Rewind's spawn event, the placer's HeldId), and this touches nothing
        /// but a per-renderer shader float, so the PlayMode probe stages that
        /// raycast placed content one physics step after Place (Stage03, 06, 10,
        /// 22) measure exactly the world they measured before this tier.
        ///
        /// DISPLAY MODE NEVER DISSOLVES, and that is not a preference: the
        /// picture studio photographs a display content one or two frames after
        /// building it (PhotoSnaps.RenderOne), so a dissolving one would give a
        /// DIFFERENT polaroid every time a photo was taken, and the polaroid IS
        /// the view the content produces (PRD 6.9). The guarantee is structural
        /// rather than a comparison somewhere in the animation: display mode
        /// leaves this function on its first line, collects no renderer,
        /// allocates no property block and writes _Reveal nowhere, so the
        /// materials keep the shader's own default of 1 (fully resolved) and
        /// there is no state an animation could pick up later.
        ///
        /// The renderers are collected ONCE. A renderer a child component builds
        /// in its own Start (the frame of a photo in photo, PhotoItem.TryBuild)
        /// is therefore not in the list and stays resolved: it has already been
        /// drawn whole by the time any Update of ours could reach it, and
        /// clipping it BACKWARDS a frame later is worse than not dissolving it.
        ///
        /// One deliberate divergence from V-VFX-01's wording. The item says the
        /// dissolve is "seeded from the content root", and NO seed is written
        /// here: _Seed is the same float that drives V-MAT-03's colour jitter,
        /// so writing a root seed over a block's own would repaint every placed
        /// block at the moment it lands and keep it repainted for good. It is
        /// not needed either, because Viewpoint/Surface's reveal field is a
        /// function of WORLD POSITION with the seed as a mere offset: two pieces
        /// of one content already dissolve in different patterns, and the same
        /// photo placed twice in the same spot still dissolves identically.
        /// </summary>
        private void BeginReveal()
        {
            if (!_solid)
            {
                return;
            }

            ErasableBlock[] blocks = GetComponentsInChildren<ErasableBlock>(true);
            Renderer[] renderers = GetComponentsInChildren<Renderer>(true);
            List<Renderer> plain = new List<Renderer>(renderers.Length);
            for (int i = 0; i < renderers.Length; i++)
            {
                Renderer target = renderers[i];
                if (target == null)
                {
                    continue;
                }
                // A block's renderer is written through the block, never here:
                // SetPropertyBlock replaces the block WHOLE, so a second block
                // carrying only _Reveal would erase the _Seed a block pushes
                // (its colour jitter, V-MAT-03) and the _CutGlow of a carve with
                // it. ErasableBlock.SetReveal exists for exactly this.
                // Only the block's OWN visual is skipped, not everything
                // parented under a block. The painted backdrop panel hangs on
                // the carvable wall it paints, so it is a sibling of that
                // wall's "Mesh" child and GetComponentInParent finds the block
                // from both: the wide test used to drop the panel, which is
                // most of a placement's screen area, and it popped in while
                // everything around it dissolved.
                ErasableBlock owner = target.GetComponentInParent<ErasableBlock>(true);
                if (owner != null && owner.Owns(target))
                {
                    continue;
                }
                Material material = target.sharedMaterial;
                // Anything that does not declare _Reveal is left alone, and the
                // check is worth more than it looks: it also means a build where
                // Viewpoint/Surface got stripped (the failure this project has
                // shipped once) shows its content INSTANTLY instead of clipping
                // it away forever on a property nothing reads. The painted
                // backdrop panel now passes this test: Viewpoint/Backdrop
                // declares _Reveal and clips in all three of its depth writing
                // passes, so it thins out with the props around it.
                if (material == null || !material.HasFloat(Materials.RevealId))
                {
                    continue;
                }
                plain.Add(target);
            }

            if (blocks.Length == 0 && plain.Count == 0)
            {
                return;
            }

            _revealBlocks = blocks;
            _revealRenderers = plain.ToArray();
            _revealProperties = new MaterialPropertyBlock();
            _revealElapsed = 0f;
            _revealing = true;
            // On the BUILD frame, so the first image of the content is the edge
            // glow and not the finished material: writing the first value from
            // Update instead would draw one frame fully resolved and then clip
            // it back, which is a flicker rather than an effect.
            PushReveal(RevealStart);
        }

        /// <summary>
        /// Runs the dissolve. Unscaled, like Hud.Fade and ErasableBlock's carve
        /// flash and for the same reason: this is presentation, and a stopped or
        /// slowed clock must not leave placed content frozen half clipped, which
        /// would read as missing geometry rather than as an effect in progress.
        ///
        /// Costs one early return per placed content per frame once settled,
        /// which a scene of under a hundred renderers (PRD_VISUAL 3.3) can pay.
        /// </summary>
        private void Update()
        {
            if (!_revealing)
            {
                return;
            }

            _revealElapsed += Time.unscaledDeltaTime;
            float t = _revealElapsed / RevealSeconds;
            if (t >= 1f)
            {
                FinishReveal();
                return;
            }

            // Ease OUT, not a smoothstep: the visible fraction tracks _Reveal
            // almost linearly, so a slow start would hold the content at a few
            // sparks for the first tenth of a second and read as a hitch. Fast
            // emergence and a gentle settle is what "resolves into place" looks
            // like.
            float eased = 1f - (1f - t) * (1f - t);
            PushReveal(Mathf.Lerp(RevealStart, 1f, eased));
        }

        /// <summary>
        /// Ends the dissolve at 1, which is the shader's complete no op: the
        /// reveal branch is not entered at all and the content pays nothing for
        /// having dissolved. The write is not optional, because 1 is also what
        /// takes a half clipped block back to whole.
        /// </summary>
        private void FinishReveal()
        {
            _revealing = false;
            PushReveal(1f);
        }

        /// <summary>
        /// Writes one value of _Reveal across the whole content. The renderers
        /// keep sharing the materials Materials.Solid cached, which the picture
        /// studio depends on (PRD_VISUAL 3.4), so this goes through property
        /// blocks throughout and touches no material.
        /// </summary>
        private void PushReveal(float value)
        {
            if (_revealBlocks != null)
            {
                for (int i = 0; i < _revealBlocks.Length; i++)
                {
                    ErasableBlock block = _revealBlocks[i];
                    if (block == null)
                    {
                        continue;
                    }
                    block.SetReveal(value);
                }
            }

            if (_revealRenderers == null || _revealProperties == null)
            {
                return;
            }
            for (int i = 0; i < _revealRenderers.Length; i++)
            {
                Renderer target = _revealRenderers[i];
                // A carve can retire a piece of this content mid dissolve, and
                // a level teardown destroys the lot: a destroyed renderer
                // answers null here and is simply skipped.
                if (target == null)
                {
                    continue;
                }
                // Read the renderer's own block back before adding to it. These
                // renderers carry none today, so this is belt and braces, but it
                // is the cheap kind: it means a component that starts pushing a
                // property of its own on a battery or a crate does not silently
                // lose it for the 0.4 s this animation runs. The Clear is
                // required and not decorative, because the same block instance
                // serves every renderer of the loop.
                _revealProperties.Clear();
                target.GetPropertyBlock(_revealProperties);
                _revealProperties.SetFloat(Materials.RevealId, value);
                target.SetPropertyBlock(_revealProperties);
            }
        }

        private void BuildProp(PhotoProp prop)
        {
            if (prop == null)
            {
                return;
            }
            bool stairs = prop.Kind == "stairs";
            List<Primitive> primitives = PhotoDefs.ExpandProp(prop);
            if (primitives != null)
            {
                for (int i = 0; i < primitives.Count; i++)
                {
                    Primitive prim = primitives[i];
                    if (prim.Kind == "battery")
                    {
                        BuildBattery(prim);
                    }
                    else if (prim.Kind == "photo_item")
                    {
                        BuildPhotoItem(prim);
                    }
                    else
                    {
                        // Stairs get their collision from a single walkable ramp
                        // below, not from eight tiny step boxes that a character
                        // controller cannot climb.
                        AddShape(prim, prim.Kind == "cylinder", !stairs);
                    }
                }
            }
            if (stairs && _solid)
            {
                BuildStairsRamp(prop);
            }
        }

        private void AddShape(Primitive prim, bool cylinder, bool withCollision)
        {
            if (_display || !withCollision)
            {
                GameObject visual = NewMeshObject(
                    cylinder ? "Cylinder" : "Box",
                    cylinder ? CylinderMesh() : BoxMesh(),
                    Materials.Solid(prim.Color),
                    cylinder ? CylinderScale(prim.Size) : prim.Size);
                Attach(visual.transform, prim.Center);
                return;
            }
            if (cylinder)
            {
                AddStaticCylinder(prim);
                return;
            }
            if (prim.Loose)
            {
                AddLooseBox(prim);
                return;
            }
            // Solid box: a block, so the placed content is itself replaceable by
            // the next photo. Placed content joins the PERMANENT half of the
            // ground language (grey stays), unless the photo painted it lavender
            // on purpose: a shot of a lavender plank stays carvable.
            ErasableBlock block = ErasableBlock.Create(prim.Size, prim.Color, 0f, null, prim.Color == "erasable");
            Attach(block.transform, prim.Center);
        }

        /// <summary>
        /// Loose boxes (small captured objects, the catalog crate) obey gravity:
        /// placed upside down or over a gap, they fall. That is the point.
        /// </summary>
        private void AddLooseBox(Primitive prim)
        {
            GameObject go = NewMeshObject("LooseBox", BoxMesh(), Materials.Solid(prim.Color), prim.Size);
            go.layer = Layers.World;
            // The mesh is a unit cube and the transform carries the size, so the
            // collider is a unit box too.
            BoxCollider boxCollider = go.AddComponent<BoxCollider>();
            boxCollider.size = Vector3.one;
            Rigidbody body = go.AddComponent<Rigidbody>();
            body.mass = Mathf.Clamp(prim.Size.x * prim.Size.y * prim.Size.z * 2f, 1f, 10f);
            Attach(go.transform, prim.Center);
            Rewind.TrackBody(body);
        }

        private void AddStaticCylinder(Primitive prim)
        {
            GameObject go = NewMeshObject("Cylinder", CylinderMesh(), Materials.Solid(prim.Color), CylinderScale(prim.Size));
            go.layer = Layers.World;
            // Unity has no cylinder collider. The object carries no Rigidbody, so
            // a plain mesh collider is legal and exact.
            MeshCollider meshCollider = go.AddComponent<MeshCollider>();
            meshCollider.sharedMesh = CylinderMesh();
            Attach(go.transform, prim.Center);
        }

        private void BuildBattery(Primitive prim)
        {
            if (_display)
            {
                GameObject glow = NewMeshObject(
                    "Battery",
                    CylinderMesh(),
                    Materials.Solid("battery", DisplayBatteryEmissive),
                    CylinderScale(new Vector3(DisplayBatteryDiameter, DisplayBatteryHeight, DisplayBatteryDiameter)));
                Attach(glow.transform, prim.Center);
                return;
            }
            // Placed batteries are ALWAYS physical: a rigid shell carrying the
            // real pickup, so a battery placed in the air falls where gravity
            // says.
            GameObject shell = new GameObject("PlacedBattery");
            shell.layer = Layers.World;
            BoxCollider shellCollider = shell.AddComponent<BoxCollider>();
            shellCollider.size = new Vector3(0.36f, 0.72f, 0.36f);
            Rigidbody body = shell.AddComponent<Rigidbody>();
            body.mass = BatteryShellMass;
            Attach(shell.transform, prim.Center);

            // FILM DOES NOT PRINT FILM. A battery that came out of a photo is
            // leaden: worth exactly one battery to a teleporter, and never a
            // subject again. Without this the economy of the whole game
            // collapses, because a copy is itself a model: with C batteries and
            // F films a player who photographs a copy next to its original walks
            // away with C x 2^F, and no teleporter requirement means anything.
            GameObject cell = new GameObject("Battery");
            // Configured before it is enabled: the pickup registers its groups
            // (battery, and copyable_battery when it is NOT sealed) in OnEnable,
            // which would otherwise run before Setup with the default flag.
            cell.SetActive(false);
            Battery battery = cell.AddComponent<Battery>();
            battery.Setup(true);
            cell.transform.SetParent(shell.transform, false);
            cell.transform.localPosition = DesignSpace.ToUnity(new Vector3(0f, BatteryCellDrop, 0f));
            cell.SetActive(true);
            Rewind.TrackBody(body);
        }

        /// <summary>
        /// Photo in photo: the solid content materializes a real pickable item.
        /// </summary>
        private void BuildPhotoItem(Primitive prim)
        {
            if (_display)
            {
                GameObject frame = NewMeshObject("PhotoItem", BoxMesh(), Materials.Solid("frame"), prim.Size);
                Attach(frame.transform, prim.Center);
                return;
            }
            GameObject go = new GameObject("PhotoItem");
            // Same reason as the battery above: the item joins its group in
            // OnEnable, so it is configured while still inactive.
            go.SetActive(false);
            PhotoItem item = go.AddComponent<PhotoItem>();
            item.Setup(prim.PhotoId);
            Attach(go.transform, prim.Center);
            go.SetActive(true);
        }

        /// <summary>
        /// Invisible walkable ramp along the hypotenuse of the flight, from the
        /// foot of the stairs to the top back corner. It carries ALL the
        /// collision: the eight visual steps have none, because a character
        /// controller cannot climb eight small boxes.
        ///
        /// The ramp passes through the BACK top corner of each step, so the step
        /// lips stand proud of it (up to 0.575 m on the catalog flight); that is
        /// intended, invisible in play, and not a bug.
        /// </summary>
        private void BuildStairsRamp(PhotoProp prop)
        {
            // Design space: pos is the front bottom center of the flight and
            // size is (width, total rise, total run); the flight rises away from
            // the camera, toward -z.
            Vector3 pos = prop.Pos;
            Vector3 size = prop.Size;
            float length = Mathf.Sqrt(size.y * size.y + size.z * size.z);
            if (length < 0.001f)
            {
                return;
            }
            float slopeDeg = Mathf.Atan2(size.y, size.z) * Mathf.Rad2Deg;
            string color = string.IsNullOrEmpty(prop.Color) ? DefaultPropColor : prop.Color;

            // ShowMesh is cleared after Create, exactly as in the original: the
            // block builds its renderer inside Create and the setter switches
            // that renderer off, so no grey slab floats through the flight and
            // none of its fragments show one either.
            ErasableBlock ramp = ErasableBlock.Create(new Vector3(size.x, RampThickness, length), color, 0f, null, false);
            ramp.ShowMesh = false;

            // Midpoint of the hypotenuse, from the foot (pos) to the top back
            // corner (pos.x, pos.y + rise, pos.z - run).
            Vector3 midpoint = new Vector3(pos.x, pos.y + size.y * 0.5f, pos.z - size.z * 0.5f);
            // Unit normal of the ramp surface in design space: perpendicular to
            // the hypotenuse (0, rise, -run) and pointing up. Dropping the center
            // half a thickness along it puts the TOP FACE on the hypotenuse.
            Vector3 surfaceUp = new Vector3(0f, size.z / length, size.y / length);
            Attach(ramp.transform, midpoint - surfaceUp * (RampThickness * 0.5f));

            // Under the z mirror the flight rises toward +z in Unity, so the ramp
            // must PITCH UP going forward, which is a NEGATIVE rotation about x
            // (a positive x rotation pitches down in Unity). The sign is the
            // opposite of the original GDScript, as every rotation sign is.
            ramp.transform.localRotation = Quaternion.Euler(-slopeDeg, 0f, 0f);
        }

        private void BuildBackdrop(PhotoBackdrop backdrop)
        {
            float depth = backdrop.Depth;
            string top = string.IsNullOrEmpty(backdrop.Top) ? DefaultBackdropTop : backdrop.Top;
            string bottom = string.IsNullOrEmpty(backdrop.Bottom) ? DefaultBackdropBottom : backdrop.Bottom;
            Vector2 size = PhotoMath.BackdropSize(depth, PhotoMath.PhotoFovDeg, PhotoMath.PhotoAspect);
            GameObject quad = NewMeshObject(
                "BackdropGradient",
                QuadMesh(),
                Materials.Backdrop(top, bottom),
                new Vector3(size.x, size.y, 1f));
            if (_display)
            {
                Attach(quad.transform, new Vector3(0f, 0f, -depth));
                return;
            }
            // The painted wall is a thin CARVABLE block, and it has to be: it is
            // the most ephemeral thing in the world (painted sky), it appears
            // wherever the player happens to aim, and a permanent one could wall
            // off a route with no way back. Being carvable, the next photo
            // pierces it. Carved fragments fall back to the block's own flat top
            // color (accepted).
            ErasableBlock block = ErasableBlock.Create(new Vector3(size.x, size.y, BackdropThickness), top, 0f, null, true);
            Attach(block.transform, new Vector3(0f, 0f, -depth));
            // The gradient hugs the front face of the block, and is a child of it
            // so that carving the wall takes the painting with it.
            quad.transform.SetParent(block.transform, false);
            quad.transform.localPosition = DesignSpace.ToUnity(new Vector3(0f, 0f, BackdropQuadOffset));
            quad.transform.localRotation = Quaternion.identity;
        }

        /// <summary>
        /// Where an authored design space center becomes a Unity local position:
        /// every prop of the definition goes through here, and the two offsets
        /// this file invents for itself (the cell inside its shell, the gradient
        /// in front of its wall) are the only other mirrors in the module.
        /// </summary>
        private void Attach(Transform child, Vector3 designCenter)
        {
            child.SetParent(transform, false);
            child.localPosition = DesignSpace.ToUnity(designCenter);
            child.localRotation = Quaternion.identity;
        }

        private GameObject NewMeshObject(string name, Mesh mesh, Material material, Vector3 localScale)
        {
            GameObject go = new GameObject(name);
            // Display mode inherits the node's layer, which PhotoSnaps sets to
            // PhotoStudio before Setup, so the studio camera (which culls every
            // other layer) sees the whole content. In a level the placer leaves
            // the content node on the default layer, while every other mesh of
            // the world (blocks, cages, decor) sits on World: a placed mesh
            // joins them rather than depending on how widely the level camera
            // and the level sun happen to draw their masks. These objects carry
            // no collider, so the layer is a rendering choice only.
            go.layer = _display ? gameObject.layer : Layers.World;
            go.transform.localScale = localScale;
            MeshFilter filter = go.AddComponent<MeshFilter>();
            filter.sharedMesh = mesh;
            MeshRenderer meshRenderer = go.AddComponent<MeshRenderer>();
            meshRenderer.sharedMaterial = material;
            return go;
        }

        /// The built in cylinder is 2 units tall and 1 unit across, so a prop of
        /// radius size.x / 2 and height size.y scales by (size.x, size.y / 2).
        private static Vector3 CylinderScale(Vector3 size)
        {
            return new Vector3(size.x, size.y * 0.5f, size.x);
        }

        private static Mesh BoxMesh()
        {
            if (_boxMesh == null)
            {
                _boxMesh = PrimitiveMesh(PrimitiveType.Cube);
            }
            return _boxMesh;
        }

        private static Mesh CylinderMesh()
        {
            if (_cylinderMesh == null)
            {
                _cylinderMesh = PrimitiveMesh(PrimitiveType.Cylinder);
            }
            return _cylinderMesh;
        }

        private static Mesh PrimitiveMesh(PrimitiveType type)
        {
            // CreatePrimitive is the only way to reach the built in meshes from
            // code, and it also adds a collider: the throwaway object is
            // deactivated before it is destroyed so it never renders nor
            // collides during the frame Destroy takes to land.
            GameObject temp = GameObject.CreatePrimitive(type);
            temp.SetActive(false);
            Mesh mesh = temp.GetComponent<MeshFilter>().sharedMesh;
            DestroyNow(temp);
            return mesh;
        }

        private static Mesh QuadMesh()
        {
            if (_quadMesh != null)
            {
                return _quadMesh;
            }
            // A unit quad in the xy plane facing -z, which is where the eye is:
            // the backdrop stands at +z in Unity and is seen from the origin of
            // this node. Unity front faces wind clockwise as seen from the front,
            // here with x to the right and y up.
            Mesh mesh = new Mesh();
            mesh.name = "BackdropQuad";
            mesh.vertices = new Vector3[]
            {
                new Vector3(-0.5f, -0.5f, 0f),
                new Vector3(-0.5f, 0.5f, 0f),
                new Vector3(0.5f, 0.5f, 0f),
                new Vector3(0.5f, -0.5f, 0f)
            };
            mesh.normals = new Vector3[]
            {
                new Vector3(0f, 0f, -1f),
                new Vector3(0f, 0f, -1f),
                new Vector3(0f, 0f, -1f),
                new Vector3(0f, 0f, -1f)
            };
            // v = 1 is the top row of the gradient texture, so the "top" color
            // lands on the top edge of the wall.
            mesh.uv = new Vector2[]
            {
                new Vector2(0f, 0f),
                new Vector2(0f, 1f),
                new Vector2(1f, 1f),
                new Vector2(1f, 0f)
            };
            mesh.triangles = new int[] { 0, 1, 2, 0, 2, 3 };
            mesh.RecalculateBounds();
            _quadMesh = mesh;
            return _quadMesh;
        }

        private static void DestroyNow(UnityEngine.Object target)
        {
            if (Application.isPlaying)
            {
                UnityEngine.Object.Destroy(target);
            }
            else
            {
                UnityEngine.Object.DestroyImmediate(target);
            }
        }
    }
}
