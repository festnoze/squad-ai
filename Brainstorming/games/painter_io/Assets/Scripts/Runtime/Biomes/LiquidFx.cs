// Owned by BI (wave B-2); the LIQ agent may fill it. Contract 25.2: the Liquide biome's extra effects component, hosted by
// BiomeFx. The liquid look needs no extra effects yet: the composite, the beads and the overlays draw everything.
namespace PainterIO.Runtime
{
    public class LiquidFx : BiomeFxBehaviour
    {
        public override BiomeId Biome => BiomeId.Liquid;
    }
}
