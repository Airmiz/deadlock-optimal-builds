# Methodology & Glossary

This is a one-page explanation of every metric, badge, and term you'll see on the page. The project derives builds from public match data; nothing is hand-curated, every number is computed from the same inputs everyone has access to.

## Data sources

- **`api.deadlock-api.com`** — community-run public Deadlock API. The pipeline pulls per-hero analytics (item win rates, ability orders, top community builds, pairwise item synergies, matchup-specific item win rates) from this single source.
- **`assets.deadlock-api.com/v2/heroes` and `/v2/items`** — asset metadata (names, tiers, costs, images, upgrade-component graph, cost-bonus tables).
- **No human curation.** Every recommendation is a function of the API responses + the algorithms below.

The pipeline is patch-aware: each patch's data lives under `cache/<patch_id>/` and `heroes/<patch_id>/`. The page lets you toggle between patches.

## MMR slices

Two skill cohorts, both rendered on the page via the All MMR / High MMR toggle:

- **All-MMR** — no rank filter. Lots of data, but mixes Initiate-tier players with top-ranked players. Win-rate signals are biased by skill confounds.
- **High-MMR** (default) — `min_average_badge=91`, which is Phantom 1 and above. Roughly the top 15–20% of the player base. Sharper signal at the cost of a smaller sample. Most metrics on the page (signature stars, recommended build, archetype optimization) use this slice.

## Wilson lower bound (the "Wilson LB" tag in the data)

For every item, we have `wins` and `matches`. Naive win rate is `wins / matches`, but small samples make this misleading — a 60% win rate over 5 matches is noise.

Wilson's score interval at 95% confidence gives a **lower bound** on the true win rate that accounts for sample size. We use this as the item's score in the optimizer, then subtract the hero baseline win rate so positive scores mean "this item makes a Shiv better than the average Shiv player".

```
Wilson_LB(wins, matches) = ((p + z²/2n) - z√(p(1-p)/n + z²/4n²)) / (1 + z²/n)
where p = wins/matches, n = matches, z = 1.96 (95% CI)
```

Items with thousands of matches sit very close to their naive win rate; items with hundreds of matches get penalized more aggressively.

## Sample-size floors

Every analysis stage requires a minimum match count for an item to be considered:

- All-MMR slice: **500 matches** floor
- High-MMR slice: **300 matches** floor (smaller pool, looser threshold)
- Pair-synergy data: 500 / 200 minimum
- Per-cluster optimization: items must appear in **≥30%** of cluster builds (relaxes to 15% if needed for build feasibility)
- Matchup counter data: ≥100 matches in the matchup-specific slice AND ≥200 in the baseline

## Three build methods

The recommended build is produced by one of three methods, each surfacing different signals:

1. **Wilson Greedy** — Rank items by `Wilson_LB(item) − baseline_WR`, pick top 4 per category + 4 flex. Simple, defensible. Bias: prefers high-win-rate late-game items because they have tighter confidence intervals.

2. **Synergy-aware ILP** *(the default "Recommended" build)* — Linear program that maximizes the sum of individual scores PLUS a pairwise-synergy bonus from `/v1/analytics/item-permutation-stats`, subject to the slot constraints (≥4 per category, total = 16, per-lineage uniqueness). The pair bonus weights items that *combine* well, not just items good in isolation.

3. **Build Replication** — Aggregate items across the highest-WR community builds, weighted by `matches × max(0, win_rate − baseline + 0.02)`. Surfaces utility/defense items the win-rate-driven methods miss (Counter Spell, Dispel Magic, Metal Skin etc.).

The page shows the synergy-ILP build by default. The full per-hero JSON in `heroes/<patch_id>/` carries all three for inspection.

## Item tags (CORE / FLEX / SIT. / STAT)

Each pick on the page is colored by how often it appears across the community's top builds for this hero:

- **CORE** — used in >70% of top community builds for this hero
- **FLEX** — 30–70%; situational pick
- **SIT.** (situational) — used in <30% but appears in builds; counter / utility role
- **STAT** — purely stat-derived: the optimizer found this win rate, no community build uses it (proceed with skepticism — it could be a hidden gem or sample noise)

## Signature items (⭐ stars)

The hero affinity score: `affinity = this_hero_pick_rate ÷ cross_hero_avg_pick_rate`. Items with affinity ≥ 2× AND pick rate ≥ 30% get tagged signature.

In plain language: "this hero uses this item at least twice as often as the average hero". Star-tagged items are the hero's *distinct fingerprint* — picks that wouldn't show up on a generic hero.

## Investment-spike progression

Deadlock has cumulative gold-spent thresholds per category (weapon / vitality / spirit). At each threshold, your damage / health / spirit-power gets a percentage bonus. The bonuses are mostly small until **4,800 souls** in a category — there the bonus more than doubles. The page calls this the *major spike*.

The thresholds are universal across heroes: 800, 1,600, 2,400, 3,200, **4,800**, 7,200, 9,600, 16,000. The bonus values changed between patches — see `SPIKE_BONUS_BY_PATCH` in `scripts/build_page.py` for the per-patch table.

The phase-summary line at the bottom of each Early/Mid/Late column shows running totals plus a ⚡ flag when the major spike has been crossed.

## Lineage chains (pre-buy progression)

Some items in Deadlock have an upgrade-component relationship — buying the higher tier *consumes* the lower-tier component. They share an inventory slot. Examples:

```
Extra Spirit (T1, $800) → Improved Spirit (T2, $1,600) → Boundless Spirit (T4, $6,400)
Compress Cooldown (T2) → Superior Cooldown (T3) → Transcendent Cooldown (T4)
Sprint Boots (T1) → Enduring Speed (T2) → Juggernaut (T4)
```

The optimizer uses **lineage dedup** — within the same upgrade family, only one item per slot. This used to be a big problem: previous builds showed both Extra Spirit and Boundless Spirit in two separate slots, double-counting cost and slot economy. After dedup, each slot represents a distinct lineage.

The page renders chain ancestors as their own *stage rows* in the phase column matching their actual buy time, with a "↑ upgrades into X in late game" footer. So you see when to buy Extra Spirit (~10 min) AND when it becomes Boundless Spirit (~30 min).

## Sell events (red-dashed rows)

The API returns an `avg_sell_time_s` for every item, indicating when the population typically sells it. Real Deadlock builds are buy timelines, not snapshots — early/mid items get sold to free slots for late-game purchases.

The page surfaces a **↓ Sell** event in the destination phase column when:
- Hold time ≥ 6 minutes (real strategic sell, not match-end noise)
- Item was bought in early or mid phase (T4 picks aren't sold)
- Sell time < minute 38 (otherwise it's just match-end)

Refund estimate is ~50% of cost, the Deadlock convention.

## Cooldown + imbue badges

- **⚡ CD <seconds>** — on active items; the press-to-use cooldown.
- **🔮 Imbue: <type>** — on items that imbue an ability:
  - *stats* — passive imbues stat modifiers (Compress Cooldown, Mystic Expansion, Duration Extender)
  - *any active* — imbues onto any active ability incl. ultimate (Mystic Reverb, Surge of Power, Quicksilver Reload, Mercurial Magnum, Ballistic Enchantment)
  - *non-ult active* — imbues onto a non-ultimate active ability only (Echo Shard, Omnicharge Signet)

## Archetype clustering

For each hero, the cached community top builds are clustered by Jaccard distance on item sets (1 − |A ∩ B| / |A ∪ B|). Average-linkage agglomerative clustering merges the closest pairs until we hit a target k (k = 1 / 2 / 3 depending on build count).

Each cluster gets:
- **Label** — derived from the most-distinguishing item (high in this cluster, low in others)
- **Distinguishing items** — top 4 items by `(in_cluster_rate − outside_rate)`
- **Sample build names** — the top 2-3 highest-WR community builds in the cluster
- **Composite build** — 16-item build either:
  - **synergy_ilp** (the good kind) — re-runs the synergy ILP scoped to items appearing in ≥30% of cluster builds. Stat-optimized for that archetype.
  - **frequency** (fallback) — tiny clusters where the optimizer can't find 16 viable picks; aggregated by community pick rate.

The build_method label appears in the "Viewing X build" banner so you know which kind you're looking at.

Most heroes have a single dominant archetype. About 7 heroes (Seven, Bebop, Dynamo, Ivy, Pocket, Mirage, Pocket-second) have meaningful 2-cluster splits where each archetype produces a genuinely different optimized build.

## Counter-pick (matchup) panel

For every (hero, enemy_hero) pair, we pull `/v1/analytics/item-stats?hero_id=X&enemy_hero_ids=Y` and compute per-item delta:

```
delta_pp = (WR with enemy on opposing team) − (baseline WR)
```

Positive delta = item works *better* than usual when this enemy is on the field; negative = it underperforms.

The panel:
- **Easiest / Hardest matchups** — top 5 enemies sorted by sum of all per-item deltas. A positive sum means your hero generally wins this matchup; negative means you struggle.
- **Enemy multi-select** — click up to 6 enemy hero portraits.
- **Buy / Avoid columns** — the panel aggregates per-enemy deltas across the selected enemies and ranks the top 7 positive (buy these) and top 7 negative (avoid / sell) items.

Filters applied so the signal isn't noise: ≥100 matches in the matchup slice, ≥200 in the baseline, |delta| ≥ 0.4pp. Top 12 stored per pair.

## Per-patch item overrides

The asset CDN can lag a Deadlock patch by hours-to-days. When a patch ships, items like Shadow Weave can show their pre-patch tier/cost/cooldown values in our cache.

`ITEM_OVERRIDES_BY_PATCH` in `scripts/build_page_data.py` is a small per-patch dict that hand-codes corrections from the patch notes. Applied at compact-hero time so patch_125825 shows old values and patch_129989 shows new ones.

Once the asset CDN refreshes, the override entries should be deleted and the cache refetched — at that point the items.json will carry the correct values natively.

## Ability priority

Per hero, we have `/v1/analytics/ability-order-stats` records: each one is an ordered sequence of ability point spends with `wins`, `losses`, `matches`. From these we compute:

- **Winner-weighted AP investment** — for each ability, the average AP spent on it weighted by `wins` only. We surface this AND the population-average value, plus the *winner premium* (`winner_avg − population_avg`). Items with positive winner premium are the abilities winners invest in more than the average player.
- **Best opener (first 4 points)** — the ordered first-4-points pattern with highest WR over enough sample (≥400 all-MMR / ≥200 high-MMR).
- **Best full sequence** — the highest-WR complete 16-point ordering with sample ≥ 200 / ≥ 100.

## Page structure

Top to bottom:

1. **Header** — patch toggle, MMR toggle, freshness warning when data is thin.
2. **Hero grid sidebar** — sortable A–Z or by WR. Click to select.
3. **Hero header** — portrait, baseline WR, sample size, build cost, signature-pick count.
4. **Ability priority** — winner-weighted AP, best opener, best full sequence.
5. **Build Archetypes** — clusters with category mix, distinguishing items, "View this build" toggle.
6. **Investment Spike Progression** — three category bars with thresholds and the ⚡ major-spike marker.
7. **Item Build by Phase** — the 16-item recommended build (or active archetype build) split into Early / Mid / Late columns. Stage rows for chain pre-buys, sell events for inventory churn.
8. **Matchup Counter Picks** — easiest/hardest rankings + enemy multi-select + aggregated buy/avoid recommendations.

## Pipeline reproducibility

Every script is patch-aware via the `PATCH_ID` env var, idempotent (skips already-cached files), and self-contained.

```bash
PATCH_ID=patch_129989 python3 scripts/batch_fetch.py        # ~1 min for fresh fetch
PATCH_ID=patch_129989 python3 scripts/batch_fetch_builds.py # community build details
PATCH_ID=patch_125825 python3 scripts/batch_fetch_counters.py # matchup data (older patch only — counters need lots of matches)
PATCH_ID=patch_129989 python3 scripts/run_all_heroes.py     # generate per-hero JSONs
python3 scripts/build_page_data.py                           # multi-patch payload
python3 scripts/download_images.py                           # localize image refs
python3 scripts/build_page.py                                # assemble HTML
```

## What this project does NOT do

- Live MMR-stratification within High MMR (Phantom-1 vs Eternus would be a follow-up)
- Hero-level matchup matrix view (data is there, only per-hero rankings render today)
- Solver-quality CD progression (CBC's 4-second timeout sometimes leaves provably-optimal slack)
- Bayesian hierarchical pooling (would help low-pick heroes; not implemented)
- Real-time push of patch updates (refresh is a manual `batch_fetch` re-run for now)
