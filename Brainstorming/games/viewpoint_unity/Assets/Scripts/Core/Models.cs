using System.Collections.Generic;
using UnityEngine;

namespace Viewpoint
{
    // Plain data, straight out of Resources/Data/photos.json and levels.json.
    // EVERY position and direction below is in DESIGN space (x right, y up,
    // -z forward, PRD section 4.1) and stays that way: the mirror on z is applied
    // by DesignSpace.ToUnity at the point where a transform is set, and nowhere
    // else. Sizes are the same in both spaces.
    //
    // No attributes, no engine behavior: these types are read by the EditMode
    // tests and by the design audit outside of play mode.

    /// <summary>
    /// One authored prop of a photo, in photo space (origin at the eye of the
    /// placer). PRD section 6.1.
    /// </summary>
    public sealed class PhotoProp
    {
        /// <summary>box, cylinder, battery, bridge, stairs, arch or photo.</summary>
        public string Kind;

        /// <summary>
        /// What Pos means depends on Kind: the center for box, cylinder, the bridge
        /// deck and the photo item, the BASE for a battery, the front-bottom-center
        /// of the flight for stairs, the bottom-center of the portal for an arch.
        /// </summary>
        public Vector3 Pos;

        public Vector3 Size;

        /// <summary>A key of Palette, never a color value.</summary>
        public string Color;

        /// <summary>Boxes only: the placement materializes a falling rigid body.</summary>
        public bool Loose;

        /// <summary>The nested photo definition id, when Kind == "photo".</summary>
        public string Id;
    }

    /// <summary>
    /// The painted wall a photo carries far behind its content: the horizon of the
    /// picture, not a lid on the carve (PRD 6.1, since v6.1 the depth is more than
    /// 2.5 times erase_depth).
    /// </summary>
    public sealed class PhotoBackdrop
    {
        public float Depth;

        /// <summary>Palette keys, the gradient runs Top to Bottom.</summary>
        public string Top;

        public string Bottom;
    }

    /// <summary>A photo: pure data, whether it comes from the catalog or from the camera.</summary>
    public sealed class PhotoDef
    {
        public string Title, Hint, Seal;   // Seal == "content" for the door, null otherwise

        /// <summary>Never null. Empty is legal and meaningful: a photo of nothing but sky.</summary>
        public List<PhotoProp> Props = new List<PhotoProp>();

        /// <summary>Null when the photo has none, which only the sealed door does.</summary>
        public PhotoBackdrop Backdrop;

        /// <summary>PRD 6.1: how deep a placement replaces. 12 when the JSON omits it.</summary>
        public float EraseDepth = 12f;

        public bool HasBackdrop => Backdrop != null;
    }

    /// <summary>
    /// The result of expanding a PhotoProp (PRD 6.2). The same expansion feeds the
    /// computed thumbnail, the offscreen picture and the 3D materialization, so what
    /// the picture shows is what gets built.
    /// </summary>
    public struct Primitive
    {
        /// <summary>box, cylinder, battery or photo_item. Never a compound kind.</summary>
        public string Kind;

        /// <summary>Always the center of the shape, whatever the prop's convention was.</summary>
        public Vector3 Center;

        public Vector3 Size;
        public string Color;
        public bool Loose;

        /// <summary>The nested definition id, when Kind == "photo_item".</summary>
        public string PhotoId;
    }

    /// <summary>A ground slab. Pos is its CENTER, so a top at y = 0 means pos.y = -size.y / 2.</summary>
    public sealed class PlatformDef
    {
        public Vector3 Pos, Size;

        /// <summary>Pale ground: carvable, and the only such ground in the game (level 11).</summary>
        public bool Soft;
    }

    /// <summary>
    /// Permanent scenery, never carvable. Thin tinted slabs are the placement
    /// markers; a marker may declare the shot it expects (PRD 13.5), which the
    /// design audit reads and the world ignores.
    /// </summary>
    public sealed class DecorDef
    {
        public Vector3 Pos, Size;

        /// <summary>PRD 5.8: decor colors default to wood when the JSON omits the field.</summary>
        public string Color = "wood";

        /// <summary>Marker only: the photo the level expects to be placed here.</summary>
        public string Photo;

        /// <summary>Marker only: where the shot is aimed. Meaningless unless HasAim.</summary>
        public Vector3 Aim;

        public bool HasAim;

        /// <summary>Marker only: the roll, in 90 degree steps, 0 to 3.</summary>
        public int Roll;
    }

    /// <summary>A lavender block: carvable, and a readability marker for the tests.</summary>
    public sealed class ErasableDef
    {
        public Vector3 Pos, Size;
    }

    /// <summary>
    /// A cage of bars. Erasable and Roof default to false here but to TRUE in the
    /// original loader: it reads erasable as `get("erasable", true) and not
    /// sealed` and roof as `get("roof", true)` (level_builder.gd), and the five
    /// sealed cages (levels 19, 20, 21, 24, 25) omit the erasable key entirely.
    /// The loader must apply both rules explicitly; leaving an absent key alone
    /// would invert them.
    /// </summary>
    public sealed class CageDef
    {
        /// <summary>Pos is the center of the cage FLOOR, not of its volume.</summary>
        public Vector3 Pos, Size;

        /// <summary>Lavender bars: breakable by any placement. Steel bars never break.</summary>
        public bool Erasable;

        public bool Roof;

        /// <summary>Solid panels instead of bars: nothing can be seen or shot through.</summary>
        public bool Sealed;
    }

    /// <summary>A pickable photo lying in the level. Pos is the center of the frame.</summary>
    public sealed class PhotoPlacementDef
    {
        public string Id;
        public Vector3 Pos;
    }

    public sealed class CameraDef
    {
        public Vector3 Pos;

        /// <summary>How many shots the camera hands out.</summary>
        public int Films;
    }

    public sealed class TeleporterDef
    {
        public Vector3 Pos;

        /// <summary>Batteries needed before it will depart.</summary>
        public int Required;
    }

    /// <summary>
    /// One of the six background islands drawn around every level. Mesh only: no
    /// collision, not photographable. Pos is the center of the body box.
    /// </summary>
    public sealed class IslandDef
    {
        public Vector3 Pos, Size;
    }

    /// <summary>One level, exactly as authored in levels.json. Every list is non null.</summary>
    public sealed class LevelDef
    {
        public string Name, Subtitle;

        /// <summary>Spawn is the position of the player's FEET.</summary>
        public Vector3 Spawn;

        /// <summary>Radians, design convention. Every level authors 0.</summary>
        public float SpawnYaw;

        /// <summary>Falling below this y respawns the player.</summary>
        public float KillY;

        public List<PlatformDef> Platforms = new List<PlatformDef>();
        public List<DecorDef> Decor = new List<DecorDef>();
        public List<ErasableDef> Erasables = new List<ErasableDef>();
        public List<CageDef> Cages = new List<CageDef>();
        public List<PhotoPlacementDef> Photos = new List<PhotoPlacementDef>();

        /// <summary>Bases of the live batteries, then of the leaden ones.</summary>
        public List<Vector3> Batteries = new List<Vector3>();

        public List<Vector3> SealedBatteries = new List<Vector3>();

        /// <summary>Null when the level hands out no camera.</summary>
        public CameraDef Camera;

        public TeleporterDef Teleporter;
    }
}
