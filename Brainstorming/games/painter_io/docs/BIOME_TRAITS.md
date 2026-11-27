# Painter IO - Biome traits (wave D spec, normative)

Status: v1.1, 2026-11-26 (section 7 adds the kill rewards). Requested by the user after the biome proposal: "tu pourras ajouter les comportements specifiques prevus pour
chaque biome, mais code-le de facon a ce que ce soit facilement debrayable individuellement ou interchangeable entre les biomes facilement."
This file is folded into docs/CONTRACT.md as section 27 once wave C-2 has written section 26. It overrides older text where they disagree.

## 1. Principles
- A TRAIT is one gameplay rule modifier: one id, one file, its own parameters, its own tests. Traits are independent of biomes.
- A biome is only a default list of traits (one data table). Moving a trait to another biome = editing one line of that table, or ticking a
  box in the hidden test settings, or a command-line override. No trait code may test the biome id.
- Every trait can be switched off individually; a master switch "Règles classiques" switches all of them off (the pure brief rules + v1.4).
- With every trait off, the simulation is bit-identical to the current one (the probe hash 246577239DE179C4 in classic mode is unchanged).
- Traits are deterministic, live in PainterIO.Core (no UnityEngine), and keep every contract signature. Rendering of trait effects is
  generic (works in all three biomes, styled by each biome's shaders), because any trait may be assigned to any biome.

## 2. The trait catalogue (initial)

| Id | Kind | Parameters (default) | Effect |
|---|---|---|---|
| Inertia | config | TurnRateDeg = 420 | Slower max turn rate: rounder curves |
| Coalescence | behaviour | MaxHoleArea = 2.0 u^2 | After an UNCHASED return, every hole of NEUTRAL cells fully enclosed by the returner's territory (after the capture) whose area < MaxHoleArea is filled; the filled cells are part of the Return's Cells |
| SparkSpeed | config | Factor = 2.1 (Fire) or 1.5 (Electric) | Overrides SparkSpeedFactor |
| Propagation | behaviour | Interval = 4.0 s, Rings = 1 | At every tick end where Time crosses a multiple of Interval: every NEUTRAL arena cell 4-adjacent to a player's cell becomes that player's (one ring), except cells claimed by two or more players at once (stay neutral), cells under any live head, cells of the propagating player's own trail raster and their 4-neighbours (so propagation never triggers that player's own return), and scorched cells (ScorchedEarth). Emits one TerritoryGrew event per player with its Cells |
| ScorchedEarth | behaviour | Duration = 15.0 s | When a player is eliminated, its freed cells become scorched until EliminatedAt + Duration: still neutral and capturable normally, but Propagation and Coalescence never fill them. Emits nothing extra (Eliminated already carries the cells); SimView exposes the scorch state |
| Conduction | behaviour | HomeSpeedFactor = 1.30 | A player whose current cell is its own at tick start moves at PawnSpeed x factor for that tick. Spark speed stays SparkSpeedFactor x the BASE PawnSpeed |
| ArcReach | config | ContactScale = 1.40 | Cut contact radius = (HeadRadius + TrailHalfWidth) x scale |
| RingInterval | config | Seconds = 10.0 | Overrides LassoFirstSpawn and LassoRespawn (only matters when the lasso option is on) |

New traits can be added later by adding one file and one registry line.

## 3. Default assignment (the one table to edit)

| Biome | Traits |
|---|---|
| Liquide | Inertia(420), Coalescence(2.0) |
| Feu | Propagation(4.0, 1), SparkSpeed(2.1), ScorchedEarth(15) |
| Électricité | Conduction(1.30), ArcReach(1.40), SparkSpeed(1.5), RingInterval(10) |

## 4. Core architecture (binding)
```csharp
public enum TraitId { Inertia = 1, Coalescence = 2, SparkSpeed = 3, Propagation = 4, ScorchedEarth = 5, Conduction = 6,
                      ArcReach = 7, RingInterval = 8 }
public sealed class TraitSpec {                 // data only
  public TraitId Id; public bool Enabled = true;
  public double P1, P2;                         // meaning per trait (section 2), defaults from TraitDefaults
  public TraitSpec Clone();
}
public sealed class RuleTraits {                // the set used by one simulation
  public static RuleTraits Classic { get; }     // empty set
  public IReadOnlyList<TraitSpec> Specs { get; }
  public RuleTraits(IEnumerable<TraitSpec> specs);   // duplicates: the last spec of an id wins; disabled specs are kept but inert
  public bool Has(TraitId id);                  // present AND enabled
  public TraitSpec Get(TraitId id);             // null when absent or disabled
  public string ToKey();                        // canonical text "Id(p1,p2);..." of the ENABLED traits, sorted by id (logs, hash salt)
  public static RuleTraits Parse(string key);   // inverse of ToKey; also accepts "classic" / ""
}
public interface ISimTrait {                    // one implementation per behaviour trait, Core/Traits/<Id>Trait.cs
  TraitId Id { get; }
  void Attach(Simulation sim, TraitSpec spec);
  double SpeedFactor(Simulation sim, PlayerState p);                 // step 1; 1.0 when not concerned
  void AugmentCapture(Simulation sim, PlayerState p, List<int> cells); // step a, unchased returns only, before the R18 conflict rule
  void OnEliminated(Simulation sim, PlayerState p, int[] freedCells, double time);
  void EndOfTick(Simulation sim, List<SimEvent> raised);             // step 3, after sparks, before the ring spawner
}
public static class TraitRegistry {
  public static void ApplyConfig(RuleTraits traits, SimConfig cfg); // config traits: Inertia, SparkSpeed, ArcReach, RingInterval
  public static List<ISimTrait> CreateBehaviours(RuleTraits traits);  // behaviour traits in TraitId order
}
```
- SimConfig gains `public RuleTraits Traits = RuleTraits.Classic;` and `public double ContactScale = 1.0;` (ContactRadius becomes
  (HeadRadius + TrailHalfWidth) x ContactScale). The Simulation constructor calls ApplyConfig on its cloned config, then CreateBehaviours.
  The HeadGrace check uses the maximum possible speed (PawnSpeed x the largest SpeedFactor any trait can return).
- New SimEventType values appended at the END of the enum: TerritoryGrew (Player, Cells). SimView gains `bool IsScorched(int cell)` and
  `RuleTraits Traits`. StateHash includes the trait key and the scorch state only when at least one trait is enabled (classic hash unchanged).
- Bots read speeds, contact radius, spark speed and ring timing from SimConfig (never constants) and account for Conduction when estimating
  travel times on their own territory.

## 5. Runtime architecture (binding)
- `Runtime/Biomes/BiomeTraitTable.cs`: the default table of section 3 as code data (one line per biome), and
  `RuleTraits Resolve(BiomeId biome)` = defaults, then SaveData overrides, then command-line overrides, then the master switch.
- SaveData: `bool BiomeRulesOn` (default true; Options toggle "Règles des biomes", OFF = "Règles classiques"), and a per-trait assignment
  override `string TraitMatrix` (canonical text of trait -> set of biomes, empty = defaults) with ResetTraitMatrix(). TuningModified becomes
  true when the matrix differs from the defaults (stats are not saved then, as for the other test settings); BiomeRulesOn = false is a
  normal option and does not mark tuning as modified.
- Command line: `-classic` (all traits off), `-traits "<RuleTraits key>"` (exact set for the round, any biome), `-trait <Id>=0|1` (toggle
  one trait on top of the biome defaults). Probe and DevShot run CLASSIC by default (hash unchanged) and accept these flags.
- GameSession.CreateRound / CreateAttract set SimConfig.Traits = BiomeTraitTable.Resolve(current biome). The attract match uses the traits
  of the selected biome.
- UI: each biome card shows its active traits as small icons with a one-line description (Strings keys trait.<id>.name / trait.<id>.desc,
  FR and EN). Options: the "Règles des biomes" toggle. Hidden test settings: a trait matrix (one row per trait, three checkboxes L / F / E)
  plus "Réinitialiser"; changes apply to the next round and to the attract match immediately.
- Generic visuals (every biome, styled by its own shaders through existing channels):
  - TerritoryGrew: TerritoryField treats it like a fill from the territory edge (reveal times), so each biome shows its own front (fire
    flames spreading, electric crackle, liquid creep). Slow and subtle: it must not look like a capture.
  - Scorched cells: a new global `_PIO_ScorchMask` (512 x 512 R8 linear, 1 = scorched, fading out over the last 2 s); each composite darkens
    and desaturates scorched ground (liquid: dried stain, fire: ash with dying embers, electric: dead burnt circuit).
  - Conduction: a short speed streak / brighter pearl glow while a pearl moves on its own territory with the trait on.
  - ArcReach: when an enemy head is within ContactRadius x 1.25 of an exposed trail point, a small arc/spark line flickers between them
    (Overlay shape), so the larger reach is visible before it cuts.
  - Coalescence: the filled holes are part of the Return fill wave (nothing extra).
  - Sounds: optional ISfxClipSet.Grow clip (soft crackle / creep), played at -18 dB for the human's own growth only, rate limited.

## 6. Tests and acceptance
- Core: one test file per trait (behaviour and parameters), RuleTraits key round trip, classic equality (every existing test green with
  Traits = Classic; the probe hash in classic mode unchanged), each trait alone and all traits of each biome together: no exception,
  invariants every tick (incl. EventCapHits == 0), determinism (same seed, same hash). Cross-rate equality (10.0) for SparkSpeed, ArcReach,
  RingInterval, Coalescence and Propagation (intervals that are multiples of 1/6 s); Inertia and Conduction are documented as tick-rate
  dependent exactly like turning already is.
- Balance report (asserted only for safety, the rest reported): bot-only rounds, 50 seeds per biome with its default traits and in classic
  mode: no exception, invariants, TimeUp in >= 40 %. Report per biome: captures per bot, cuts per round, share of cuts that kill, saved
  chased returns, coverage at the end, eliminations, average round tempo. Expected tendencies (sanity, reported): Feu has the highest kill
  share per cut and the highest passive growth; Électricité has the most cuts and the most saved chases; Liquide stays closest to classic.
- Player: probe in classic mode (hash 246577239DE179C4 at -fps 30 and -fps 144), plus one probe per biome with its default traits at -fps 30
  and -fps 144 (equal hashes per biome), screenshots showing TerritoryGrew, scorched ground, the conduction streak and the reach arc.

## 7. Kill rewards (v1.1, user decision 2026-11-26)
User: "dans paper.io 2, on recupere le terrain de l'adversaire tue, et dans le 4, on a un bonus de vitesse. Je propose de donner un avantage
specifique a chaque biome : le feu, capture du territoire ennemi, l'electricite, bonus permanent de vitesse, et l'eau, bonus temporaire
d'invincibilite. Code-le de facon a facilement pouvoir desactiver / echanger ces regles plus tard (pas hardcoder pour un biome), et verifie les
consequences sur le comportement deja decide ou deja en place, comme le biome feu."

A KILL is a Spark elimination; the killer is Spark.Attacker (the cutter whose cut was retained, R11). A TerritoryLost elimination has no
killer reward (the last cell already went to the capturer). Three new traits, same rules as section 1 (one file each, any biome):

| Id | Params (default) | Effect |
|---|---|---|
| KillInheritance (9) | Share = 1.0 | When the killer is alive after the eliminating group, the victim's cells go to the killer instead of becoming neutral (Paper.io 2). Applied in the elimination step, before the round-end check. If the killer is dead (or eliminated in the same group), the cells become neutral as today. Emits TerritoryInherited (Player = killer, Other = victim, Cells) |
| KillSpeedBoost (10) | PerKill = 0.10, Cap = 0.30 | Each kill adds +PerKill to the killer's permanent speed multiplier for the rest of the round, capped at 1 + Cap (Paper.io 4). Emits SpeedBoosted (Player, value) |
| KillShield (11) | Duration = 3.0 s | After a kill, the killer is invincible until t_kill + Duration: enemy heads cannot cut its trail (no Cut, no spark), and a spark already on its trail is extinguished at the kill instant. Territory loss to 0 cells still eliminates. Emits ShieldStarted / ShieldEnded (Player) |

Default assignment (section 3 table gains a column): Feu + KillInheritance, Électricité + KillSpeedBoost, Liquide + KillShield.

### 7.1 Core rules made explicit by these traits (all neutral when every trait is off: classic hash unchanged)
- PlayerState.SpeedMultiplier (permanent, starts at 1.0, changed only by traits). Effective tick speed = PawnSpeed x SpeedMultiplier x
  (Conduction factor when home). The HeadGrace check uses the maximum reachable speed.
- SPARK SPEED FOLLOWS THE VICTIM (keeps the brief's "1.8 fois la vitesse du pion" true with speed bonuses): Spark.Speed is fixed at spawn to
  SparkSpeedFactor x PawnSpeed x victim.SpeedMultiplier (Conduction excluded: a chased player is outside its territory). The closed form
  uses Spark.Speed. A boost gained during the chase (the chased player kills someone) does not change the running spark. Classic: identical.
- CUT EXITS NEVER CAPTURE (v1.4 restated as a flag): PlayerState.ExitWasCut is set when a spark spawns on the current exit and cleared at
  the next Exit / return. A return with ExitWasCut captures nothing (Chased = true in the Return event), even if the spark was removed in
  the meantime (KillShield). The R14 cross-tick cancellation clears the flag together with the spark. Classic: identical to "has a spark".
- Shield timing is exact: ShieldEnd is an event candidate of section 6, so cut candidates are recomputed from that u (a head already over
  the trail when the shield ends cuts at that instant, subject to HeadGrace).

### 7.2 Consequences on what is already decided (checked)
- Feu: ScorchedEarth only marks cells that become NEUTRAL. With KillInheritance, a kill gives the land to the killer, so ash now appears
  only when the killer is already dead (rare). ScorchedEarth stays in the table (harmless, still meaningful when KillInheritance is switched
  off or moved) but its gameplay weight in Feu becomes small. Propagation then grows the inherited land too: Feu becomes the strongest
  snowball biome (deadlier cuts 2.1x + kills that pay + passive growth). The balance report must measure the swing (round decided by one kill).
  Inheritance can put the killer's own trailing head on its own cell: it then returns at that instant through the normal section 6 state
  check (an unchased return captures with its trail; a chased one captures nothing). Intended.
- Électricité: KillSpeedBoost stacks with Conduction (up to 1.3 x 1.3 = 1.69 x base at home). Because the spark follows the victim's
  multiplier, a boosted player stays catchable at the same ratio (1.5x of its own speed). Faster pawns also turn wider (turn rate unchanged).
- Liquide: KillShield gives a comeback: a chased player who kills during its flight loses its spark and survives, but its loop stays lost
  (ExitWasCut). Coalescence is unaffected. A pending lasso pocket of a cut exit is still erased at the return.
- Bots: never aim at a shielded enemy; a shielded bot may extend its excursion while the shield lasts; travel and catch estimates use
  SpeedMultiplier and Spark.Speed; with KillInheritance the value of a lethal cut includes the victim's area.
- Presentation (D-2): TerritoryInherited plays the biome's fill front over the victim's land in the killer's color (fire sweeping over it);
  SpeedBoosted shows "+10 % vitesse" and a stronger pearl aura per level; the shield shows a glossy film around the pearl and a shimmering,
  uncuttable trail with a small timer ring; toasts "Tu as pris le terrain de Safran !", "Vitesse +10 %", "Invincible 3 s".
- Rule texts on the biome cards and in the trait matrix gain the three traits.
