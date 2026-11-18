using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>
    /// The player furniture bodies of M4 (docs/CONTRACT_M4.md section 2, amendment 9.5). BodyDef.Size is
    /// the one size source. The chair row equals the M1 constants exactly (CoreM4BodyTests checks every field).
    /// The rows are the contract table, data rather than tuning. The stool (CONTRACT_M4 10.3, which overrides
    /// 9.5): the fast stage ends at the tell speed (<see cref="Tuning.StoolTellSpeed"/>, 1.0 m/s), then the stool
    /// climbs at <see cref="Tuning.StoolHighAccel"/> (1.2 m/s2) to the tip speed (<see cref="Tuning.StoolTipSpeed"/>,
    /// 1.3 m/s, unchanged): 0.25 s of visible tell before it can tip.
    ///
    /// M5 (docs/CONTRACT_M5.md 5 and 16.9): the rocking chair row, and its flag <see cref="Rocks"/>. Rocks is a property,
    /// not a field, so the M4 field-by-field rows (CoreM4BodyTests) stay exactly the M4 table; CoreM5BBodyTests checks
    /// every field and every property of all six rows.
    /// </summary>
    public sealed class BodyDef
    {
        public string Kind;
        public Vector3 Size;
        public float Radius;
        public float MaxSpeed;
        public float Accel;
        /// <summary>Stool: the acceleration above <see cref="StageSpeed"/>; equal to Accel otherwise.</summary>
        public float AccelHigh;
        /// <summary>Stool: the speed where the slow stage starts (the tell speed, below the tip speed); +inf otherwise.</summary>
        public float StageSpeed;
        public float TurnRate;
        public float CarryForward;
        public bool Glides;
        public bool Tips;
        public bool HasLight;
        public bool IsSeat;
        public string Model;

        /// <summary>
        /// M5 (CONTRACT_M5 5, 16.9): the body rocks when it comes to rest after moving, for <see cref="Tuning.RockTime"/>
        /// (<see cref="Tuning.RockCarefulTime"/> after a careful stop), an action that counts as moving. Only the rocking
        /// chair. FurnitureController applies it under GameRules.Bodies.
        /// </summary>
        public bool Rocks { get; set; }

        /// <summary>The body of a kind, a new instance on every call; null or unknown returns the chair.</summary>
        public static BodyDef For(string kind)
        {
            switch (kind)
            {
                case "stool":
                    return new BodyDef
                    {
                        Kind = "stool", Size = new Vector3(0.35f, 0.55f, 0.35f), Radius = 0.22f, MaxSpeed = 2.4f, Accel = 14f,
                        AccelHigh = Tuning.StoolHighAccel, StageSpeed = Tuning.StoolTellSpeed, TurnRate = 540f, CarryForward = 0.45f,
                        Tips = true, IsSeat = true, Model = "kenney.stool",
                    };
                case "armchair":
                    return new BodyDef
                    {
                        Kind = "armchair", Size = new Vector3(0.85f, 1.05f, 0.85f), Radius = 0.45f, MaxSpeed = 0.9f, Accel = 6f,
                        AccelHigh = 6f, StageSpeed = float.PositiveInfinity, TurnRate = 200f, CarryForward = 0.65f,
                        IsSeat = true, Model = "kenney.armchair",
                    };
                case "floor_lamp":
                    return new BodyDef
                    {
                        Kind = "floor_lamp", Size = new Vector3(0.35f, 1.80f, 0.35f), Radius = 0.22f, MaxSpeed = 0.6f, Accel = 4f,
                        AccelHigh = 4f, StageSpeed = float.PositiveInfinity, TurnRate = 180f, CarryForward = 0.40f,
                        HasLight = true, Model = "kenney.floorlamp",
                    };
                case "office_chair":
                    return new BodyDef
                    {
                        Kind = "office_chair", Size = new Vector3(0.55f, 1.00f, 0.55f), Radius = 0.30f, MaxSpeed = 2.8f, Accel = 8f,
                        AccelHigh = 8f, StageSpeed = float.PositiveInfinity, TurnRate = 360f, CarryForward = 0.65f,
                        Glides = true, IsSeat = true, Model = null,
                    };
                case "rocking_chair":
                    // M5 (CONTRACT_M5 5): no Kenney rocking chair in the kit yet, so the procedural one (Model null) until
                    // the watchers agent names a catalog id.
                    return new BodyDef
                    {
                        Kind = "rocking_chair", Size = new Vector3(0.6f, 1.05f, 0.85f), Radius = 0.36f, MaxSpeed = 1.2f, Accel = 6f,
                        AccelHigh = 6f, StageSpeed = float.PositiveInfinity, TurnRate = 240f, CarryForward = 0.65f,
                        IsSeat = true, Model = null,
                        Rocks = true, // MUTATION:ROCKS_ROW
                    };
                default:
                    return new BodyDef
                    {
                        Kind = "chair", Size = new Vector3(0.45f, Tuning.ChairControllerHeight, 0.45f), Radius = Tuning.ChairControllerRadius,
                        MaxSpeed = Tuning.ChairMaxSpeed /*MUTATION:CHAIR_ROW*/, Accel = Tuning.ChairAcceleration, AccelHigh = Tuning.ChairAcceleration,
                        StageSpeed = float.PositiveInfinity, TurnRate = Tuning.ChairTurnRate, CarryForward = Tuning.CarryForward,
                        IsSeat = true, Model = "kenney.chair",
                    };
            }
        }
    }
}
