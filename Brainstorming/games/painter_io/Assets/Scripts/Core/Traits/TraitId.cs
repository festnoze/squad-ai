// Owned by traits-core (wave D-1), kill traits added by kill-core (wave D-2). docs/BIOME_TRAITS.md sections 4 and 7
// (binding enum values).
namespace PainterIO.Core
{
    /// <summary>
    /// One gameplay rule modifier (docs/BIOME_TRAITS.md section 2). Traits are independent of biomes: a biome is only a
    /// default list of traits (Runtime BiomeTraitTable). The numeric values are binding (saved matrices, keys, logs).
    /// </summary>
    public enum TraitId
    {
        Inertia = 1,
        Coalescence = 2,
        SparkSpeed = 3,
        Propagation = 4,
        ScorchedEarth = 5,
        Conduction = 6,
        ArcReach = 7,
        RingInterval = 8,

        // Kill rewards (docs/BIOME_TRAITS.md section 7, v1.1, kill-core wave D-2).
        KillInheritance = 9,
        KillSpeedBoost = 10,
        KillShield = 11,
    }

    /// <summary>
    /// How a trait acts (api addition): a Config trait only rewrites fields of the round's cloned SimConfig
    /// (TraitRegistry.ApplyConfig); a Behaviour trait is an ISimTrait called at the hook points of the event engine.
    /// </summary>
    public enum TraitKind
    {
        Config = 0,
        Behaviour = 1,
    }
}
