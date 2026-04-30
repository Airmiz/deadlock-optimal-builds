# Shiv — High-MMR vs All-MMR Build Comparison

**Patch:** patch_125825 (04-10-2026 Update)
**High-MMR cutoff:** `min_average_badge=91` (Phantom 1+, ~top 15–20% of the player base)

| Slice | Matches | Players | Baseline WR | Candidate items (≥500 matches) |
|---|---|---|---|---|
| All-MMR | 296,558 | 90,888 | 47.05% | 117 |
| High-MMR (Phantom+) | 70,530 | 18,649 | 47.35% | 75 |

Shiv's win rate climbs slightly with skill — modestly, but enough that the meta shifts visibly.

## The headline finding: Shiv is a spirit hero at high MMR

Every one of the top 10 items that *gains* win rate at high MMR is a spirit-category item except one (Spirit Shielding is technically vitality but it's a spirit-resist item):

| Item | Cat | Tier | All-MMR WR | High-MMR WR | Δ |
|---|---|---|---|---|---|
| Rusted Barrel | spirit | T1 | 33.95% | 37.53% | +3.58pp |
| Arcane Surge | spirit | T2 | 45.65% | 49.22% | +3.58pp |
| Transcendent Cooldown | spirit | T4 | 52.73% | 55.76% | +3.02pp |
| Greater Expansion | spirit | T3 | 50.70% | 53.54% | +2.84pp |
| Spirit Burn | spirit | T4 | 55.81% | 58.39% | +2.58pp |
| Spirit Shielding | vitality | T2 | 40.41% | 42.96% | +2.54pp |
| Tankbuster | spirit | T3 | 46.05% | 48.49% | +2.44pp |
| Scourge | spirit | T4 | 61.30% | 63.64% | +2.34pp |
| Mystic Burst | spirit | T1 | 45.56% | 47.73% | +2.17pp |

The pattern is unambiguous: skilled Shiv players land more spirit damage and time their cooldowns better, so anything that scales spirit becomes more valuable. **Cooldown reduction (Transcendent Cooldown, Greater Expansion) is the clearest marker** — both jump nearly 3 percentage points.

## What loses value at high MMR

Mostly low-skill-floor items and weapon picks:

| Item | Cat | Δ | Why it likely drops |
|---|---|---|---|
| Melee Lifesteal | vitality T1 | -5.98pp | Skilled enemies don't let you melee them |
| Melee Charge | weapon T2 | -4.37pp | Same |
| Mystic Shot | weapon T2 | -2.46pp | Better spirit options at high MMR |
| Sprint Boots | vitality T1 | -1.50pp | High-MMR players skip boots faster |
| Juggernaut | vitality T4 | -1.27pp | Anti-tank scaling matters less when team comp is sharper |

## Method-by-method: how the builds shift

Every method changed 3-4 items when the MMR filter was applied. Twelve to thirteen of the sixteen slots stayed identical — the high-MMR builds are *refinements*, not redesigns.

**Wilson Greedy** changes:
- Dropped: Scourge, Spiritual Overflow, Frenzy, Phantom Strike — all high-WR items that **fall below the 500-match high-MMR sample floor**. Scourge has only 451 high-MMR matches; not enough confidence.
- Added: Greater Expansion, Leech, Spirit Rend, Restorative Shot — items with adequate high-MMR sample and solid Wilson LB.

**Synergy ILP** changes:
- Dropped: Fleetfoot, Mystic Shot, Extra Charge, Arctic Blast
- Added: Spirit Rend, Monster Rounds, Enchanter's Emblem, Cold Front
- Pattern: high-MMR ILP swaps in *utility/scaling* items (Enchanter's Emblem for spirit power, Cold Front for slow, Spirit Rend for damage amp) over raw stat sticks.

**Build Replication** changes:
- Dropped: Juggernaut, Cultist Sacrifice, Crippling Headshot
- Added: Escalating Exposure, Spirit Rend, Mystic Shot
- Pattern: pro builds at high MMR drop the experimental weapon picks and double down on spirit damage amplifiers.

## The new high-MMR consensus

Items now picked by **all three methods at high MMR** (vs only 3 items at all-MMR):

| Item | Category | Tier | High-MMR WR |
|---|---|---|---|
| Boundless Spirit | spirit | T4 | 54.24% |
| Transcendent Cooldown | spirit | T4 | 55.76% |
| Escalating Exposure | spirit | T4 | 56.00% |
| Restorative Shot | weapon | T1 | 47.31% |
| Spirit Rend | weapon | T3 | 46.82% |

Five locked-in items, all spirit-or-spirit-amp. The build is drifting clearly toward a spirit nuker archetype at high skill.

## Recommended high-MMR build (Synergy ILP, the strongest single answer)

**Phase 1 — Laning (buy by ~5–8 min)**
- weapon: Restorative Shot (T1, $800)
- vitality: Extra Regen (T1, $800)
- flex: Mystic Regeneration (T1, $800)
- spirit slot opens: Cold Front (T2, $1,600)

**Phase 2 — Mid-game (10–18 min)**
- weapon: Spirit Shredder Bullets (T2, $1,600)
- vitality: Restorative Locket (T2, $1,600)
- vitality: Enchanter's Emblem (T2, $1,600)
- weapon: Spirit Rend (T3, $3,200)

**Phase 3 — Late game (28+ min)**
- spirit: Mystic Reverb, Ethereal Shift, Escalating Exposure, Transcendent Cooldown (all T4)
- vitality: Witchmail, Infuser (T4)
- flex: Boundless Spirit (T4)
- weapon: Monster Rounds (T1, $800) — gun anti-creep, gets sold

**Total cost:** ~$53,200. Drops weapon to $7,200 across 4 slots — high-MMR Shiv barely uses gun damage.

## Files

- `shiv_optimal_builds.json` — all-MMR (3 methods)
- `shiv_optimal_builds_hmmr.json` — high-MMR (3 methods)
- `shiv_optimal_builds.csv`, `shiv_optimal_builds_hmmr.csv` — flat versions
- `shiv_mmr_item_deltas.csv` — per-item WR shift between MMR slices (the "what changes by skill" table)
- `shiv_build_summary.md` — original all-MMR write-up
- `shiv_mmr_comparison.md` — this file

## What this implies for the all-heroes pass

1. **Always run high-MMR by default** — the all-MMR data is too contaminated by low-skill items (Melee Lifesteal, Cultist Sacrifice) that wouldn't survive in any real build.
2. **Lower the sample floor at high MMR** — at ≥91 we have ~24% of all-MMR sample; a 500-match floor cuts out legitimately strong picks (Scourge dropped despite 63% WR). Use 200–300 instead.
3. **The ILP method handled the MMR filter best** — its early-game picks remained sensible because synergy data still had pair-coverage; Wilson lost important late-game items to the sample floor.
