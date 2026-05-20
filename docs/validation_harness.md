# Validation harness — aggregate-level temporal hold-out

Implements roadmap item #1 from the [methodology review](https://github.com/airmiz/deadlock-optimal-builds): an objective basis for comparing the three build methods (Wilson Greedy, Synergy ILP, Build Replication) and for measuring whether future methodology changes actually improve recommendations on held-out data.

## What it does

The deadlock-api is aggregation-only — there is no per-match endpoint that returns a single match's items plus outcome — so the review's exact per-match log-loss harness is not directly achievable. The harness implements the same temporal hold-out idea using the available API:

```
train_window = [patch_start, patch_end - test_days × 86400]
test_window  = [patch_end - test_days × 86400, patch_end]
```

For each (hero × MMR slice), the harness re-queries `/v1/analytics/item-stats`, `/v1/analytics/item-permutation-stats`, `/v1/analytics/hero-build-stats`, and `/v1/analytics/hero-stats` separately for the train and test windows. It then:

1. Runs the production scoring code (`build_hero_output.method_wilson` / `method_synergy_ilp` / `method_build_replication`) against train-window inputs. The recommendation set is the method's chosen item picks.
2. Evaluates each method's picks against the test-window data:

| Metric | What it tells you |
| --- | --- |
| **Held-out Δpp** (headline) | Pooled WR of the recommended bundle in the test window minus the test-window hero baseline. Positive ⇒ picks really do beat baseline on unseen data. |
| **Top-K hit rate** (K = 8, 16) | Fraction of the method's top-K picks that also rank top-K by raw WR in the test window. Robust to the method's exact scoring rule. |
| **Spearman ρ** (data-level) | Rank correlation between train- and test-window item scores. Property of the data, identical across methods. High ρ ⇒ ranking generalizes; low ρ ⇒ noise or genuine drift. |
| **Wilson LB calibration** (data-level) | Fraction of items where train Wilson 95% LB ≤ test observed WR. Should be ≥ 0.95 if Wilson is well-calibrated under temporal drift. |

## How to run

```bash
cd validation

# Headline run: active patch, hmmr (the production-recommended slice)
python harness.py

# All four MMR slices on the data-rich patch
python harness.py --mmr all,hmmr,asc,eter --patch patch_125825

# Specific heroes, smaller test window
python harness.py --heroes 19,2,15 --test-days 5

# Compare scoring rules head-to-head (methodology review §2.4)
python harness.py --scoring wilson          # default — Wilson LB − baseline
python harness.py --scoring hierarchical    # cross-hero EB pooling
```

Outputs land at:

```
validation/reports/<patch_id>_<utc_iso>/
  summary.md       # human-readable, with method leaderboard + per-hero spread
  report.json      # full per-(hero, mmr, method) metric dump
  per_hero.csv     # one row per (hero, mmr, method) — easy to pivot

validation/reports/<patch_id>_latest/  # mirror of the most recent run
```

A separate `validation/window_cache/<patch_id>/<min_ts>_<max_ts>/` namespace caches the windowed API responses so re-runs hit the disk, not the network. The harness never writes to `cache/` or `heroes/` — the production pipeline's state is untouched.

## Headline findings (first run, 2026-05-19)

Two patches, hmmr slice, 38/38 heroes evaluated each:

| Patch | Train | Test | Wilson Δpp | ILP Δpp | Replication Δpp |
| --- | --- | --- | --- | --- | --- |
| `patch_125825` (Apr 10) | 12.8d | 7.0d | **+7.383** | +3.459 | +2.545 |
| `patch_129989` (Apr 30) | 11.6d | 7.0d | **+7.484** | +3.373 | +2.507 |

**Wilson Greedy beats Synergy ILP by ~2.1× on held-out aggregate WR**, replicated across two independent patches. The site currently defaults the headline recommendation to ILP — that default is open to challenge once the joint item+ability model (§3.6) lands, since part of ILP's gap may be that pairwise synergies are confounded by ability investment.

**Wilson LB calibration is under-covering badly** — mean coverage 0.83 on `patch_125825` and 0.79 on `patch_129989`, vs the 0.95 target. Only 2/38 (resp. 6/38) heroes hit ≥ 0.95. This confirms methodology review §2.6's hypothesis: temporal drift inflates the train-window WR enough that the 95% Wilson lower bound from the train window over-states the next week's true WR. Worth being explicit about in the user-facing methodology page.

**Spearman ρ ≈ 0.84** across patches — rankings are highly stable across the train→test split, which is consistent with "the methods see real signal, but the level shifts under drift" rather than "the methods see noise".

The per-hero spread is large: Wilson Δpp ranges from +3.2 (Seven) to +12.6 (Haze) on `patch_125825`. The worst-calibrated heroes (Seven at 0.58, Dynamo at 0.68) overlap meaningfully with the worst Wilson Δpp, suggesting calibration coverage is a useful per-hero confidence signal independent of the headline metric.

## Validated methodology changes

### §2.4 — Cross-hero empirical-Bayes pooling

Implementation in [scripts/hierarchical.py](../scripts/hierarchical.py). Pre-fits per-(MMR slice) item priors from every hero's train-window observations using closed-form empirical Bayes (no MCMC). Each item's prior is shrunk toward a category-level mean (level-2 shrinkage). Per-(hero, item) scoring is a Gaussian conjugate update of the prior with the observed wins/matches.

Head-to-head on hmmr, 38/38 heroes evaluated:

| Patch | Method | Wilson Δpp | Hierarchical Δpp | Δ |
| --- | --- | --- | --- | --- |
| `patch_125825` | Wilson Greedy | +7.383 | **+8.375** | +0.99 |
| `patch_125825` | Synergy ILP | +3.555 | +3.774 | +0.22 |
| `patch_125825` | Build Replication | +2.545 | +2.585 | +0.04 |
| `patch_129989` | Wilson Greedy | +7.484 | **+8.333** | +0.85 |
| `patch_129989` | Synergy ILP | +3.373 | +3.432 | +0.06 |
| `patch_129989` | Build Replication | +2.507 | +2.620 | +0.11 |

Hierarchical pooling strictly dominates Wilson scoring on every metric on both patches — better held-out Δpp for all three methods, higher top-K hit rates, higher mean Spearman ρ (0.834 → 0.878 on `patch_125825`). The biggest gains land on Wilson Greedy because pairwise synergies in the ILP already absorb some of the noise that hierarchical pooling removes; the ILP's room-to-improve is mostly orthogonal to scoring (it's slot-counting + synergy bonuses).

New heroes appearing in the hmmr top-8 under hierarchical scoring (Paige, Silver, Vindicta) are exactly the low-pick-rate case the review predicted would benefit. Seven, the worst-Wilson hero, also moves: +3.15 → +4.72.

To switch the production pipeline:

```bash
DEADLOCK_SCORING=hierarchical python scripts/run_all_heroes.py
```

Default remains `wilson` so the production output is unchanged until explicitly opted in. The flag flows through [scripts/run_all_heroes.py](../scripts/run_all_heroes.py) → [scripts/build_hero_output.py](../scripts/build_hero_output.py)'s new `score_fn_provider` parameter → `build_candidates`'s new `score_fn` parameter.

### §3.6 — Joint item + ability optimization

Implementation in [scripts/joint_optimization.py](../scripts/joint_optimization.py). For each (hero, MMR slice), clusters the cached community builds by their *ability-ladder fingerprint* — the ordered sequence of which abilities receive their first upgrade-point spend. Within each cluster, aggregates items using the same lift-weighted scheme as `method_build_replication`, then emits a self-contained `(items, ability_order)` archetype dict.

The output lands as a new `joint_archetypes` field on `item_methods[<slice>]` in every per-hero JSON. Rendering on the public page is a separate UI task.

**Empirical motivation for the field's existence.** Scanning all 38 heroes on `patch_125825` hmmr with the 100-match build floor: 17 heroes have a single viable archetype, 21 heroes have multiple. The WR spread *between archetypes for the same hero* is large enough to be actionable for users:

| Hero | Archetypes | Best Δpp | Worst Δpp | Spread |
| --- | --- | --- | --- | --- |
| Bebop | 4 | +5.58 (Sticky-first) | −6.32 (Sticky-low) | 11.9pp |
| Vyper | 2 | +2.28 (Slither-first) | −6.95 (Venom-first) | 9.2pp |
| Lash | 3 | −0.30 (Flog→Grapple→Ground Strike) | −9.66 (Flog→Grapple→Death Slam) | 9.4pp |
| Pocket | 2 | +5.48 (Affliction-first) | +0.29 (Satchel-first) | 5.2pp |
| Warden | 2 | +4.45 (Willpower-first) | −1.68 (Binding-first) | 6.1pp |
| Mo & Krill | 2 | +2.90 (Burrow-first) | −1.63 (Combo-first) | 4.5pp |

The fact that Vyper — explicitly flagged by the review as a low-pick hero where the pipeline currently struggles — has a clear archetype split between Slither-first (+2.28pp) and Venom-first (−6.95pp) is the strongest evidence that joint conditioning was the right hypothesis. The current single-build output averages over these archetypes and recommends an item set whose value depends on which ability priority the player happens to follow.

### §2.8 — Enemy-comp counter-picks

Two improvements landed in [scripts/build_page_data.py](../scripts/build_page_data.py) and [scripts/hero_traits.py](../scripts/hero_traits.py):

**Problem 1 — continuous confidence-weighted score.** `compute_counters_for_patch` now scores each (hero, enemy, item) row as `delta_pp × min(1, n_vs/300) × min(1, n_base/500)`. The pre-§2.8 hard thresholds (`n_vs ≥ 100`, `n_base ≥ 200`, `|Δ| ≥ 0.4`) are replaced by a soft noise floor (`|score| ≥ 0.05`). Items at 0.39pp lift no longer get dropped while items at 0.41pp pass — the discontinuity is gone.

**Problem 2 — enemy-team trait taxonomy.** Hand-curated map of `hero_class_name → {trait,...}` over an 8-element trait set (spirit_burst, bullet_dps, sustain, mobility, dive, cc, tank, stealth_pickoff, objective_pressure). Exposed in the patch payload as `hero_traits` + `trait_taxonomy`. `saturated_counter_score` aggregates per-enemy deltas with *max per trait* (so anti-heal saturates against one healer or three) rather than the previous sum-per-enemy. Page client-side switch from sum to max-per-trait is a UI follow-up; the data is in the payload.

The trait taxonomy is deliberately partial — heroes without a label fall back to the per-enemy summation, so coverage degrades gracefully as the curation grows.

### §6.4 — 2D tag taxonomy

Implemented as `classify_2d_tag(pick_rate, wr_delta_pp)` in [scripts/build_hero_output.py](../scripts/build_hero_output.py), applied in `decorate_picks`. Replaces the legacy 1D CORE/FLEX/SIT./STAT bands (which keyed on pick frequency only) with a 5-class taxonomy that combines pick frequency × adjusted lift:

| Tag | Pick rate | Lift | Meaning |
| --- | --- | --- | --- |
| `core_proven` | ≥ 50% | > +1pp | Default buy — community and data agree |
| `core_inherited` | ≥ 50% | −1 to +1pp | Meta inertia — try replacing |
| `tech_pick` | < 30% | > +2pp | Edge for consensus-breakers |
| `trap_popular` | ≥ 40% | < −1pp | Stop buying — popular but hurts WR |
| `stat_anomaly` | < 10% | > +3pp | Speculative bet |

The legacy 1D tag is preserved on each pick as `pick_rate_tag` for downstream consumers that haven't migrated. Page CSS, `TAG_LABEL`, `TAG_TITLE`, and the legend in [scripts/build_page.py](../scripts/build_page.py) are updated to render the new tags.

The most valuable addition is `trap_popular`: it is the only tag in the system that can ever signal "stop buying this even though everyone does". Under the previous taxonomy a bad-but-popular item got CORE with no caveat.

### §5.3 — Synergy top-K cutoff

`method_synergy_ilp` now takes a `synergy_top_k` parameter (default 400, the historical value). Bumping to 2000 on `patch_125825` hmmr nudges ILP Δpp from +3.424 to +3.625 — marginal positive (+0.20pp). The harness has `--synergy-top-k` for further tuning. Leaving the production default at 400 since the lift is small and the runtime cost of larger K is real on heroes with full pair pools.

### §3.4 — Counter-aware ILP

`method_synergy_ilp` accepts `matchup_score_augment={item_id: delta_pp}` and `matchup_weight` (default 0.5). When provided, the ILP objective gains `matchup_weight × delta_pp / 100 × x[i]` per item. The result is a build that's both individually strong AND specifically tuned against the chosen enemy comp — replacing the current sidebar overlay with a counter-aware default. Wiring the user's enemy-comp selection from the page into the ILP call is a UI follow-up; the optimizer-side change is shipped.

### §3.1 — ILP soul-budget feasibility (null result with default budgets)

Implementation in [scripts/build_hero_output.py](../scripts/build_hero_output.py)'s `method_synergy_ilp(...soul_budgets=...)` parameter. Adds three optional linear constraints:

```
sum_{i: phase(i)=early}        cost[i] · x[i] <= B_early
sum_{i: phase(i) in {early,mid}} cost[i] · x[i] <= B_mid
sum_{i: all}                   cost[i] · x[i] <= B_late
```

With `DEFAULT_SOUL_BUDGETS = {early: 6000, mid: 18000, late: 32000}` (rough hmmr defaults), the harness shows the constraint **hurts** the ILP on `patch_125825` hmmr:

| Config | ILP Δpp | ILP top-8 hit | ILP top-16 hit |
| --- | --- | --- | --- |
| Wilson scoring (no constraint) | +3.424 | 0.321 | 0.407 |
| Wilson scoring + feasibility | +2.079 | 0.079 | 0.123 |
| Hierarchical scoring (no constraint) | +3.774 | 0.339 | 0.428 |
| Hierarchical scoring + feasibility | +2.082 | 0.079 | 0.122 |

The constraint with default budgets is too tight: the ILP can't fit its preferred 16 items, so it falls back to cheaper-but-worse items and hit rates collapse 4×.

A defensible §3.1 implementation needs three things the cheap version doesn't have: (a) empirically-calibrated soul curves from `/v1/analytics/player-performance-curve` (the API does expose them, this is the right next step), (b) soft elasticity per the review's spec rather than hard caps, and (c) ideally co-implemented with §3.2's sequential MDP so the budget can re-allocate across phases as state evolves rather than being a snapshot constraint. None of those are short tasks.

The constraint is preserved as opt-in (`--feasibility` on the harness, `soul_budgets=...` on `method_synergy_ilp`) so future research can tune. It is not the production default.

**§3.2 (sequential MDP) and §3.7 (sell events in the LP)** are not implemented in this pass. Both require a redesign of the optimizer's formulation — the existing ILP is a single-shot 16-slot snapshot, and switching to a policy-over-time is a multi-week change with substantial risk to all downstream consumers. They remain on the roadmap as the natural continuation of §3.1 once the soul-curve calibration is real.

### §2.3 + §4.1 — Bias correction (null result)

Implementation in [scripts/bias_correction.py](../scripts/bias_correction.py). Three scoring variants based on the review's §2.3 option 1 and §4.1:

- `buy_time_bucket` — score = WR − pooled-WR of all items in the same phase (early/mid/late). T4 items compete against the T4 cohort, removing the unconditional-baseline survivorship inflation.
- `time_discount` — score = (WR − baseline) × (1 − avg_buy_time / 35min). Items bought late get attenuated.
- `bucket_plus_discount` — both applied.

Head-to-head on patch_125825 hmmr against Wilson and hierarchical scoring:

| Scoring | Wilson Greedy Δpp | Top-8 hit | Spearman ρ |
| --- | --- | --- | --- |
| `wilson` (baseline) | +7.383 | 0.470 | 0.834 |
| `hierarchical` ✓ | **+8.375** | **0.510** | **0.878** |
| `buy_time_bucket` | +6.690 | 0.438 | 0.750 |
| `time_discount` | +4.922 | 0.148 | 0.646 |
| `bucket_plus_discount` | +3.568 | 0.109 | 0.609 |

**All three bias-correction rules degrade held-out performance** — `buy_time_bucket` loses ~0.7pp, `time_discount` loses ~2.5pp, the combined rule loses ~3.8pp. This contradicts the review's prediction that bucketing would attenuate survivorship inflation and improve scoring quality.

The honest interpretation: on the deadlock-api's aggregate-level data, the cheap bias-correction proxies the review suggests don't separate genuine T4 item quality from survivorship inflation. Pooling T4 items against other T4 items removes real signal alongside the bias. Time-discount weighting is structurally too pessimistic about late-game items — Deadlock's snowball dynamics mean late T4 picks have disproportionate impact per second of use, not less.

The review's preferred fix is the more principled **propensity weighting** (option 2): a model that predicts `P(player buys item X at minute T | game state at T)` from per-match data, used to re-weight each match. The deadlock-api does not expose per-match data, so propensity weighting is not directly buildable against this API. It would require either (a) a new data source with per-match histories or (b) a different platform (Steam/OpenDota-style).

The three bias-correction rules are kept in the codebase as available `--scoring` options on the harness so future research can keep iterating. They are not the production default.

## Deferred work

Items from the methodology review's §9 roadmap that are intentionally not implemented in this pass:

- **§2.1 — EB Beta-binomial shrinkage with hero-category prior.** Superseded by §2.4's cross-hero hierarchical pooling, which produces strictly stronger shrinkage and was validated to improve held-out Δpp. The original §2.1 spec is more targeted (within-hero category prior) and could complement §2.4 in principle, but the empirical lift is unlikely to be additive.
- **§2.2 — Sample-floor cross-validation.** A one-off analytical study (sweep floors on held-out matches, pick the F that minimizes log-loss / max-AUC). Easy to run now that the harness exists — `--heroes 19,...` + custom floors per slice. Punted because the existing floors are reasonable and the harness can re-evaluate cheaply when someone wants to tune.
- **§2.7 — Patch bridging.** Use the previous patch's posterior as a prior for items whose `properties` JSON didn't change. Multi-day implementation (patch-aware `build_candidates`, cross-patch diff machinery) and the harness's "wait for samples to accumulate" approach is already adequate within ~24h of a patch drop.
- **§3.2 — Sequential MDP / phase-by-phase optimization.** Replaces the single-shot 16-slot ILP with a per-phase policy. The right next step after empirically-calibrated soul curves are added; full implementation is a multi-week optimizer redesign that risks the existing pipeline's outputs without proportional benefit until the soul-curve calibration lands.
- **§3.3 — Triple synergies (`comb_size=3`).** Needs a new fetch (`/v1/analytics/item-permutation-stats?comb_size=3`) per hero per slice per window. Doubles harness fetch load and the empirical question — does it materially help — is open. Reasonable to test after the rate-limit headroom recovers.
- **§3.5 — CVaR risk-aware optimization.** Alternative ILP objective that penalizes high-variance bundles. Needs a per-item variance estimate; hierarchical pooling's posterior variance is the right source. Implementable as a small `--risk-weight` knob on the ILP once a use case demonstrates value.
- **§3.7 — Sell events in the LP.** Models `(buy_phase, sell_phase)` tuples per item with 50% refund into next phase's budget. Co-implementable with §3.2's MDP — both share the temporal-feasibility infrastructure.
- **§5.1 — Adaptive K clustering via silhouette.** The existing build-page archetype clustering uses fixed K ∈ {1,2,3}. Replacing with silhouette-driven K (or HDBSCAN) is straightforward but the §3.6 joint optimization above arguably supersedes it — clustering on ability fingerprint already produces 2–4 archetypes per hero, which is the goal.
- **§5.2 — Weighted Jaccard.** Minor improvement to the existing item-set clustering. Cost-weighted or score-weighted Jaccard is a 10-line change. Not done because the joint-ability clustering above is the more leveraged axis.
- **§5.4 — Soft cluster floor.** Replaces the binary 30%→15% relaxation with a smooth penalty. Minor cleanup, not urgent.

## Status of the rest of the roadmap

| § | Change | Status | Verdict |
| --- | --- | --- | --- |
| §7 | Validation harness | ✅ Shipped | Foundational |
| §2.4 | Cross-hero hierarchical pooling | ✅ Shipped, opt-in via `DEADLOCK_SCORING=hierarchical` | **Improves Δpp + top-K + Spearman across both patches** |
| §2.5 | Per-MMR scoring | ✅ Shipped (harness supports 4 slices; production has them) | Mechanical |
| §2.6 | Wilson LB calibration check | ✅ Shipped (data-level metric in every harness run) | Confirms under-coverage |
| §3.6 | Joint item + ability archetypes | ✅ Shipped as new per-hero JSON field | 21/38 heroes show multi-archetype with 5–12pp WR spread |
| §6.4 | 2D tag taxonomy | ✅ Shipped end-to-end (data + page) | Adds `trap_popular` signal |
| §2.8 | Counter-pick continuous score | ✅ Shipped end-to-end | Removes hard-threshold discontinuity |
| §2.8 | Counter-pick trait archetypes | ✅ Framework shipped, taxonomy hand-curated | Page-side aggregation is UI follow-up |
| §3.4 | Counter-aware ILP | ✅ Shipped as opt-in param | UI wiring is follow-up |
| §5.3 | Synergy top-K | ✅ Configurable | +0.20pp at K=2000 vs 400 |
| §3.1 | ILP soul-budget constraint | ✅ Shipped as opt-in | **Default budgets hurt** — needs empirical soul curve |
| §2.3 | Buy-time bucketing | ✅ Shipped as opt-in `--scoring` | **Hurts Δpp** — propensity weighting needs per-match data API doesn't expose |
| §4.1 | Time-discount weighting | ✅ Shipped as opt-in `--scoring` | **Hurts Δpp** — structurally pessimistic about T4 |
| §3.2 | Sequential MDP | ⏸ Deferred | Multi-week, depends on empirical soul curve |
| §3.7 | Sell events in LP | ⏸ Deferred | Co-implementable with §3.2 |
| §2.7 | Patch bridging | ⏸ Deferred | Multi-day, marginal vs harness wait |
| §3.3 | Triple synergies | ⏸ Deferred | Needs new API fetch |
| §3.5 | CVaR risk-aware | ⏸ Deferred | Awaits use case |
| §5.1, §5.2, §5.4 | Clustering polish | ⏸ Deferred | §3.6 supersedes most of the leverage |
| §2.1 | Beta-binomial w/ category prior | ⏸ Superseded | §2.4 generalizes |
| §2.2 | Floor cross-validation | ⏸ Open study | Harness now makes it cheap |

The empirical takeaway: **the methodology review's predictions were partially right.** Hierarchical pooling (§2.4) and joint item+ability (§3.6) — the two changes the review marked as highest-leverage — both showed real, measurable improvements. The bias-correction proxies (§2.3, §4.1) and the cheap soul-budget constraint (§3.1) all degraded held-out performance with their out-of-the-box parameters, suggesting the review's intuitions about *why* they would help didn't survive contact with this data source's specific structure. Those changes are kept as opt-in for future tuning, not the production default.

The harness ([validation/harness.py](../validation/harness.py)) is the foundation that made the empirical comparison possible. Every methodology change since has either landed because the harness confirmed the lift or stayed opt-in because the harness flagged a regression. That decision quality compounds — every future change can be evaluated the same way.

## Known limitations

- **No per-match log-loss / Brier.** The API does not expose individual matches with items + outcome. Δpp is the closest aggregate-level analog: it measures whether the recommended bundle's pooled test-window WR beats the test-window baseline. It is a valid relative comparator across methods but not directly comparable to a per-match probability metric.
- **No `include_item_ids`-bundle conditioning.** A future extension can re-query `/v1/analytics/item-stats?include_item_ids=…` to get the bundle's *intersection* WR (matches that contain every recommended item), which is a closer proxy for "did this build win" than the per-item pooled WR currently used.
- **Rate-limited at scale.** Running all four MMR slices on both patches in one shot fans out ~1.8k fetches and trips Cloudflare's per-IP cap. Defaults to `workers=2` and the windowed cache is durable, so a few re-runs collect everything.
- **Asc/Eter slices need a rate-limit-friendly fetch.** The Phantom+ (hmmr) slice is the production headline and works. Ascendant+ and Eternus+ data exists in the API but is only partially fetched on a typical run. Re-run with `--mmr asc` or `--mmr eter` on a fresh IP to fill them in.
