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
    /// </summary>
    public sealed class PhotoContent : MonoBehaviour
    {
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
        }

        private void OnEnable()
        {
            JoinPlacedContent();
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
