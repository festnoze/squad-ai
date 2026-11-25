using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// WINDOWS3D (2026-11-24, docs/next/progress/WINDOWS3D.md, ArtHandoff/WoodWindow/INTEGRATION.md): the art handoff's 3D wood
    /// casement window, at Assets/Resources/WindowModel.asset, baked by OutOfSight.Editor.WindowModelBuilder from
    /// Assets/ThirdParty/Models/WoodWindow/wood_casement_window.glb (being referenced from Resources is what ships its meshes,
    /// its glass material and, through that material, the glass shader).
    ///
    /// Both meshes are in the GLB's own frame as glTFast imports it (metres, x negated into Unity's left-handed frame, V flipped):
    /// the pivot at the bottom centre of the opening, y up, +z toward the room (the handle's side). The nominal opening is
    /// <see cref="NominalOpening"/>; the outer frame (the "dormant") runs from <see cref="OuterZ"/> outside to
    /// <see cref="RoomZ"/> on the room side, the sill and the handle stand further toward the room.
    /// <list type="bullet">
    /// <item><see cref="frame"/>: the satin walnut, the glazing gaskets and the metal hardware (892 triangles less the six panes),
    /// drawn with the wall material like the room dressing (DressingBuilder's encoding): a wood vertex samples the walnut_veneer
    /// slice of the wall arrays tinted by its GLB vertex colour, a gasket or hardware vertex is a flat colour with its own
    /// metallic and smoothness. So the frames cost no material and combine per wall line (LevelBuilder.Window3D).</item>
    /// <item><see cref="glass"/>: the six panes (the GLB's "Clear glazing" slot, UV 0 to 1 each), drawn by
    /// <see cref="glassMaterial"/> (shader <see cref="GlassShaderName"/>, Assets/Settings/WindowGlass.shader, the handoff's
    /// reference values), one renderer per window: the shader takes its reflection angle from the window's own object space
    /// and every window sorts as its own transparent.</item>
    /// </list>
    /// </summary>
    public sealed class WindowModel : ScriptableObject
    {
        public const string ResourcePath = "WindowModel";

        /// <summary>The handoff's glazing shader (Assets/Settings/WindowGlass.shader).</summary>
        public const string GlassShaderName = "Out of Sight/Window Glass";

        /// <summary>The model's nominal opening, width by height in metres (ArtHandoff/WoodWindow/inventory.json).</summary>
        public static readonly Vector2 NominalOpening = new Vector2(1.32f, 1.36f);

        /// <summary>The outside face of the outer frame, model z (metres; the outside sill reaches -0.105).</summary>
        public const float OuterZ = -0.103f;

        /// <summary>The room side face of the outer frame, model z (the room side strips, the handle and the sill stand further in).</summary>
        public const float RoomZ = 0.059f;

        /// <summary>The glass shader's reflection strength and tint opacity (its night factor, the wall fader's see-through copy).</summary>
        public static readonly int ReflectionId = Shader.PropertyToID("_ReflectionStrength");
        public static readonly int VeilId = Shader.PropertyToID("_Veil");

        /// <summary>The wood, the gaskets and the hardware, drawn with the wall material (see the class summary).</summary>
        public Mesh frame;

        /// <summary>The six panes, drawn with <see cref="glassMaterial"/>.</summary>
        public Mesh glass;

        /// <summary>The one glazing material every window shares (Assets/Settings/WindowGlass.mat).</summary>
        public Material glassMaterial;

        /// <summary>Measured at bake time.</summary>
        public int frameTriangles;
        public int glassTriangles;

        /// <summary>The hash of the sources the meshes were baked from (the builder rebakes when it changes).</summary>
        public string sourceHash;

        /// <summary>When true, every window keeps the flat M3 look (a pane and trim strips on an uncut wall): tests.</summary>
        public static bool Disabled;

        private static WindowModel loaded;
        private static bool missingLogged;

        public static WindowModel Load()
        {
            if (loaded == null)
            {
                loaded = Resources.Load<WindowModel>(ResourcePath);
                if (loaded == null && !missingLogged)
                {
                    missingLogged = true;
                    Debug.LogError($"[WindowModel] no window model at Resources/{ResourcePath}: the windows keep their flat look");
                }
            }
            return loaded;
        }

        /// <summary>True when both meshes and the glass material are there and the glass shader runs here.</summary>
        public bool Ready => frame != null && glass != null && glassMaterial != null && glassMaterial.shader != null
            && glassMaterial.shader.isSupported;

        /// <summary>
        /// The model the level builder puts in every window, or null: <see cref="Disabled"/>, textures off or no wall material
        /// (the frame is drawn by it, <see cref="WallArray.Material"/>), or the asset missing or incomplete. Null keeps the
        /// flat M3 window on an uncut wall.
        /// </summary>
        public static WindowModel Usable
        {
            get
            {
                if (Disabled || WallArray.Material == null)
                {
                    return null;
                }
                WindowModel model = Load();
                return model != null && model.Ready ? model : null;
            }
        }

        /// <summary>
        /// The model's scale in an opening of <paramref name="width"/> by <paramref name="height"/> in a wall of
        /// <paramref name="thickness"/>: x and y fit the nominal opening to the JSON's (the handoff's starting point), z fits
        /// the outer frame to the wall, <see cref="Tuning.WindowFrameProud"/> proud of each face.
        /// </summary>
        public static Vector3 Scale(float width, float height, float thickness)
        {
            return new Vector3(width / NominalOpening.x, height / NominalOpening.y, DepthScale(thickness));
        }

        /// <summary>The z scale that fits the outer frame (<see cref="OuterZ"/> to <see cref="RoomZ"/>) to the wall, proud of both faces.</summary>
        public static float DepthScale(float thickness)
        {
            return (thickness + 2f * Tuning.WindowFrameProud) / (RoomZ - OuterZ);
        }

        /// <summary>
        /// How far the model's origin stands from the wall's centre plane toward the room: the outer frame's room face
        /// <see cref="Tuning.WindowFrameProud"/> in front of the wall's room face, so the sill and the handle stand proud on
        /// the room side and the outside face sits as proud outside.
        /// </summary>
        public static float Depth(float thickness)
        {
            return thickness * 0.5f + Tuning.WindowFrameProud - RoomZ * DepthScale(thickness);
        }

        /// <summary>
        /// The glass's property block under the night preset (<see cref="Main.Night"/>, read as the level builds): the
        /// reflections at <see cref="Tuning.WindowGlassNightReflection"/> of the material's; null by day (the material as is).
        /// </summary>
        public MaterialPropertyBlock NightBlock()
        {
            if (!Main.Night || glassMaterial == null || !glassMaterial.HasProperty(ReflectionId))
            {
                return null;
            }
            var block = new MaterialPropertyBlock();
            block.SetFloat(ReflectionId, glassMaterial.GetFloat(ReflectionId) * Tuning.WindowGlassNightReflection); // MUTATION:NIGHT_GLASS
            return block;
        }
    }
}
