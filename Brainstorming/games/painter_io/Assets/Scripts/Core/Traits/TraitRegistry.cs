// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 4: the one place that maps trait ids to code.
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// Maps trait ids to code (docs/BIOME_TRAITS.md section 4). Config traits rewrite fields of the round's CLONED
    /// SimConfig (never the caller's object); behaviour traits are ISimTrait instances. Adding a trait = one line here.
    /// </summary>
    public static class TraitRegistry
    {
        /// <summary>
        /// Applies the enabled config traits to cfg, in TraitId order (they touch disjoint fields):
        /// Inertia: TurnRateDeg = P1. SparkSpeed: SparkSpeedFactor = P1. ArcReach: ContactScale = P1.
        /// RingInterval: LassoFirstSpawn = LassoRespawn = P1. Behaviour traits and a null or classic set change nothing.
        /// </summary>
        public static void ApplyConfig(RuleTraits traits, SimConfig cfg)
        {
            if (cfg == null) throw new ArgumentNullException(nameof(cfg));
            if (traits == null) return;
            IReadOnlyList<TraitSpec> specs = traits.Specs;
            for (int k = 0; k < specs.Count; k++)
            {
                TraitSpec s = specs[k];
                if (!s.Enabled) continue;
                switch (s.Id)
                {
                    case TraitId.Inertia: cfg.TurnRateDeg = s.P1; break;
                    case TraitId.SparkSpeed: cfg.SparkSpeedFactor = s.P1; break;
                    case TraitId.ArcReach: cfg.ContactScale = s.P1; break;
                    case TraitId.RingInterval:
                        cfg.LassoFirstSpawn = s.P1;
                        cfg.LassoRespawn = s.P1;
                        break;
                }
            }
        }

        /// <summary>New, not yet attached instances of the enabled behaviour traits, in TraitId order (empty when classic).</summary>
        public static List<ISimTrait> CreateBehaviours(RuleTraits traits)
        {
            var list = new List<ISimTrait>();
            if (traits == null) return list;
            IReadOnlyList<TraitSpec> specs = traits.Specs;
            for (int k = 0; k < specs.Count; k++)
            {
                TraitSpec s = specs[k];
                if (!s.Enabled) continue;
                ISimTrait trait = Create(s.Id);
                if (trait != null) list.Add(trait);
            }
            return list;
        }

        /// <summary>A new instance of a behaviour trait, null for a config trait (api addition).</summary>
        public static ISimTrait Create(TraitId id)
        {
            switch (id)
            {
                case TraitId.Coalescence: return new CoalescenceTrait();
                case TraitId.Propagation: return new PropagationTrait();
                case TraitId.ScorchedEarth: return new ScorchedEarthTrait();
                case TraitId.Conduction: return new ConductionTrait();
                case TraitId.KillInheritance: return new KillInheritanceTrait();
                case TraitId.KillSpeedBoost: return new KillSpeedBoostTrait();
                case TraitId.KillShield: return new KillShieldTrait();
                default: return null;
            }
        }
    }
}
