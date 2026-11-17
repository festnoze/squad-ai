using Meuble.Core;
using UnityEngine;

namespace Meuble
{
    /// <summary>
    /// A static furniture of the same kind as the player (PRD 11 M2, docs/CONTRACT_M2.md 3.1). It never
    /// moves and is never discovered: its pose is the memory slot every inhabitant holds for it. Built by
    /// <see cref="LevelBuilder"/> on the Furniture layer (it collides with the chair and shapes the NavMesh,
    /// but never occludes). Ids run from 1 in level order; 0 is the player furniture.
    /// </summary>
    public sealed class Decoy : MonoBehaviour
    {
        public int Id;
        public string Kind = DecoyDef.DefaultKind;
        public FurniturePose Pose;
        public Vector3 Size = new Vector3(0.45f, 0.9f, 0.45f);

        /// <summary>The five vision sample points of PRD 4.1 (output length 5), from the static pose.</summary>
        public void GetSamplePoints(Vector3[] output)
        {
            VisionMath.SamplePoints(Pose.Position, Pose.Yaw, Size, Tuning.SampleInset, output);
        }
    }
}
