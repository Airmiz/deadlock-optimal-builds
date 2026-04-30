# Shiv — Optimal Build Analysis (Patch 125825)

**Patch:** 04-10-2026 Update (live since 2026-04-11)
**Hero baseline:** 47.05% win rate over 296,558 matches, 90,888 unique players
**Candidate pool:** 117 upgrade items with ≥500 matches purchased on Shiv this patch
**Data source:** `api.deadlock-api.com` (the same backend Statlocker.gg uses)

## TL;DR — Three methods, three answers

Each method optimizes the same 16-slot build (4 weapon + 4 vitality + 4 spirit + 4 flex) but uses a different signal. All three agreed on only **three items**: Boundless Spirit, Arctic Blast, and Transcendent Cooldown — these are the consensus core of an optimal Shiv build right now.

| | Method 1: Wilson Greedy | Method 2: Synergy ILP | Method 3: Build Replication |
|---|---|---|---|
| Signal | Wilson 95% lower-bound win rate | Individual score + pairwise synergy bonus | What top-WR community builds use |
| T4 items | 14 | 8 | 8 |
| T1–T2 items | 2 | 6 | 4 |
| Phase coverage | Late-game only | Full progression | Full progression |
| Best for | Endgame snapshot | Statistically defended full build | Practical, meta-aligned build |

The three methods diverge on a real fault line: Wilson and ILP both rank by win rate, which biases toward endgame items (more matches → tighter confidence → higher LB). Replication mirrors what humans actually build, which weights utility/defense items (Dispel Magic, Healbane, Warp Stone) that don't have impressive standalone win rates but are functional through the whole game.

## The honest caveat

**Even the best Shiv build only reaches ~48% win rate this patch.** The hero is below baseline (47.05%). No combination of items lifts that to >50%. So "optimal" here means "least bad" — pick this hero in this patch and these items are your best shot.

## Method 1 — Wilson 95% LB Greedy

Picks the item with the highest lower confidence bound on win rate, four per category, plus four flex from the remaining best.

| Slot | Item | Tier | Cost | WR | Wilson LB | Δ baseline | Sample |
|---|---|---|---|---|---|---|---|
| weapon | Spiritual Overflow | T4 | $6,400 | 56.85% | 53.12% | +9.80pp | 686 |
| weapon | Frenzy | T4 | $6,400 | 56.84% | 52.51% | +9.78pp | 512 |
| weapon | Spirit Shredder Bullets | T2 | $1,600 | 47.34% | 46.61% | +0.29pp | 18,058 |
| weapon | Fleetfoot | T2 | $1,600 | 48.04% | 46.58% | +0.99pp | 4,496 |
| vitality | Witchmail | T4 | $6,400 | 57.91% | 57.43% | +10.85pp | 41,158 |
| vitality | Phantom Strike | T4 | $6,400 | 56.33% | 54.29% | +9.27pp | 2,308 |
| vitality | Infuser | T4 | $6,400 | 53.36% | 52.85% | +6.30pp | 37,985 |
| vitality | Spellbreaker | T4 | $6,400 | 52.47% | 51.70% | +5.42pp | 16,265 |
| spirit | Scourge | T4 | $6,400 | 61.30% | 59.43% | +14.25pp | 2,646 |
| spirit | Ethereal Shift | T4 | $6,400 | 59.13% | 58.47% | +12.08pp | 21,268 |
| spirit | Mystic Reverb | T4 | $6,400 | 56.45% | 56.17% | +9.40pp | 122,081 |
| spirit | Spirit Burn | T4 | $6,400 | 55.81% | 55.02% | +8.76pp | 15,168 |
| flex | Escalating Exposure | T4 | $6,400 | 54.31% | 53.99% | +7.26pp | 91,921 |
| flex | Arctic Blast | T4 | $6,400 | 53.87% | 53.38% | +6.81pp | 39,905 |
| flex | Transcendent Cooldown | T4 | $6,400 | 52.73% | 52.44% | +5.68pp | 107,364 |
| flex | Boundless Spirit | T4 | $6,400 | 52.36% | 52.05% | +5.31pp | 101,639 |

**Total cost:** $96,800. All but two items are T4 ($6,400). This is the late-game endgame state — it tells you nothing about what to buy in the first 25 minutes. Useful as a target, useless as a guide.

## Method 2 — Synergy-Aware ILP

Pulls 21,103 pairwise win-rate records from the API and solves an integer program: maximize the sum of individual confidence-bounded scores PLUS the pairwise synergy bonus (item-pair WR minus average individual WR), subject to the slot constraints.

Phase-grouped output:

**Early (laning, 2–8 min)**
- weapon: Restorative Shot (T1, $800)
- vitality: Extra Regen (T1, $800)
- flex: Extra Charge (T1, $800)
- flex: Mystic Regeneration (T1, $800)

**Mid (12–18 min)**
- weapon: Mystic Shot (T2, $1,600)
- weapon: Fleetfoot (T2, $1,600)
- weapon: Spirit Shredder Bullets (T2, $1,600)
- vitality: Restorative Locket (T2, $1,600)

**Late (28+ min)**
- spirit: Mystic Reverb, Ethereal Shift, Escalating Exposure, Arctic Blast (all T4)
- vitality: Witchmail, Infuser (T4)
- flex: Boundless Spirit, Transcendent Cooldown (T4)

**Total cost:** $58,400. The synergy data pushed the model to keep early/mid items that *combo* with the late-game spirit core, not just the highest-WR items in isolation. This is a complete buyable progression.

## Method 3 — Top Build Replication

Aggregates items across the 11 highest-WR Shiv builds (from `/v1/analytics/hero-build-stats/19`, ≥200 matches each), weighted by `matches × max(0, wr − baseline + 0.02)`. The top builds win 47.8–48.4% — modest, but they reflect what works in practice.

**Early/Mid:** Restorative Shot, Cold Front, Healbane, Warp Stone, Dispel Magic, Torment Pulse, Cultist Sacrifice, Kinetic Dash
**Late:** Boundless Spirit, Transcendent Cooldown, Arctic Blast, Plated Armor, Crippling Headshot, Juggernaut, Spellbreaker, Metal Skin

This build looks materially different from Methods 1 & 2 — heavier on defensive utility (Dispel Magic, Metal Skin, Plated Armor, Healbane) and lighter on the spirit-burst items the win-rate data favors. The likely explanation: experienced Shiv players know they need defensive cooldowns to survive long enough to use the spirit core; the raw stats can't see that interaction.

## Recommendation

For an *actual buildable progression*, **Method 2 (Synergy ILP)** is the strongest single answer — it handles the early-game gap that Wilson can't, and it's grounded in win rates rather than meta-popularity. Use **Method 3** as a sanity check: where it agrees with Method 2, you're on solid ground; where it diverges (e.g., Method 3 includes Dispel Magic / Metal Skin), that's the model missing situational utility.

The **3-item consensus** (Boundless Spirit, Arctic Blast, Transcendent Cooldown) is mandatory in any Shiv build right now — every method picked these.

## Files

- `shiv_optimal_builds.json` — full structured output (all three methods, source builds)
- `shiv_optimal_builds.csv` — flat side-by-side comparison
- `shiv_build_phases.csv` — phase-grouped (early/mid/late) view
- `shiv_items_patch_125825.csv` — raw item-level stats from the validation step

## Method extensions to consider next

- **Bayesian shrinkage to baseline** instead of Wilson LB — a more principled handling of small-sample items (Phantom Strike's 56% on 2,308 matches would shrink toward 47%).
- **MMR-bucketed builds** — `/v1/analytics/item-stats?min_average_badge=...` lets us pull "what wins at high MMR" specifically, dodging the low-MMR signal that dominates the unfiltered data.
- **Counter builds** — `enemy_hero_ids` parameter gives matchup-specific item win rates. We could compute a build per enemy team comp.
- **Build progression as a sequence problem** — instead of bucketing by `avg_buy_time_s`, model the actual purchase order using `/v1/analytics/item-permutation-stats` with sequence flags.
