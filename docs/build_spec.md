# Per-Hero Build Output Specification (v1.0.0)

This spec defines the JSON shape produced for each Deadlock hero. One file per hero (`{hero_name_lower}_build.json`), generated from the same set of public deadlock-api.com endpoints. The reference implementation is `build_hero_output.py`; the reference output is `shiv_build.json`.

## Top-level shape

```
{
  spec_version: "1.0.0",
  hero:        { id, name, abilities[] },
  patch:       { id, title, min_unix_timestamp },
  mmr_slices:  { all_mmr, high_mmr },     // population-level baselines
  recommended: { items, abilities },      // the headline answer
  items:       { all_mmr, high_mmr },     // full method comparisons
  ability_orders: { all_mmr, high_mmr },  // full sequence + first-4 patterns
  provenance:  { data_source, endpoints_used, asset_sources }
}
```

The split into `recommended` (the answer) and `items`/`ability_orders` (the workings) is deliberate. A consumer who just wants the build reads `recommended`; a consumer who wants to inspect alternatives or cross-check methods reads the rest.

## `hero`

Static identity for the hero plus the four signature abilities resolved to (id, name) pairs. Abilities are pulled from `assets.deadlock-api.com/v2/heroes` then looked up in `assets.deadlock-api.com/v2/items` (abilities are encoded as items in the asset API).

## `patch`

The patch the analysis is scoped to. `min_unix_timestamp` is the lower bound applied to every API call. We do not set a `max_unix_timestamp` — the analysis is always against "this patch onward", which on a live patch means "this patch so far".

## `mmr_slices`

Population stats for the two skill cohorts we analyze:
- **`all_mmr`**: no MMR filter — everyone playing the patch. High sample, low signal (selection bias from low-skill noise).
- **`high_mmr`**: `min_average_badge=91` (Phantom 1+, ~top 15–20% of player base). Lower sample, sharper signal.

Each slice records `baseline_win_rate`, `matches`, and `players`. For Shiv: 47.05% over 296K matches at all-MMR vs 47.35% over 70K at high-MMR. (`players` is `null` for data generated after 2026-06-07 — the hero-stats endpoint dropped its unique-player count in that API revision; the page omits the figure when absent.)

## `recommended` (the headline answer)

```
recommended.items: {
  method: "synergy_ilp",
  mmr_slice: "high_mmr",
  total_cost: <int>,
  phases: { early: [...], mid: [...], late: [...] }
}
recommended.abilities: {
  ap_priority_order: [<ability_name>, ...],   // sorted by winner-weighted AP
  best_full_order:   { sequence_names, wins, matches, win_rate, ... },
  best_opener_first4: { sequence_names, wins, matches, win_rate }
}
```

Why these defaults:
- **Synergy ILP at high MMR** is the strongest single answer (see `shiv_mmr_comparison.md`). Wilson loses important late-game items to the sample floor; replication misses items that aren't already in popular builds. ILP covers the full progression and respects pair-synergies.
- **Phases** split items by mean buy time: `< 12.5 min` = early, `12.5–25 min` = mid, `> 25 min` = late. This converts a final-state list into a buy-order plan.
- **`ap_priority_order`** is sorted by *winner-weighted* average AP, not population average. Players who win invest differently — that's the more useful signal.
- **`best_full_order`** is the highest-win-rate complete 16-point ability sequence with sufficient sample (≥ 100 matches at high MMR). The order of upgrades, not just the count, is what matters here.
- **`best_opener_first4`** is the highest-WR pattern for the first four ability points — the laning-phase tempo decision.

## `items` (the workings)

Per MMR slice, three independently-derived 16-item builds:

```
items.{slice}: {
  candidate_count: <int>,
  min_matches_filter: <int>,
  wilson_greedy:     { picks: [16 items] },
  synergy_ilp:       { picks: [16 items] },
  build_replication: { picks: [16 items], source_builds: [...] }
}
```

Each pick contains: `slot` (weapon/vitality/spirit/flex), `category` (the item's intrinsic category), `tier`, `cost`, `name`, `item_id`, `matches`, `wins`, `win_rate`, `wilson_lb`, `score` (= wilson_lb − baseline), `wr_delta_pp` (in percentage points), `avg_buy_time_s`, `phase`. Build-replication picks also carry `build_freq_weight`. The `source_builds` list shows which community builds fed the replication aggregation.

Why three methods and not one: each captures a different signal. Wilson tells you "what wins given enough data"; ILP tells you "what wins together"; replication tells you "what real winning humans buy". Disagreements between them are diagnostic — they're how you find selection bias and missing utility items.

Sample-size floors differ by slice: 500 matches at all-MMR (lots of data, can be strict), 300 at high-MMR (smaller pool, looser threshold). Pair-synergy floors are 500 / 200 in the same way. These are tunable in `build_hero_output.py`.

## `ability_orders` (the workings)

Per MMR slice:

```
ability_orders.{slice}: {
  total_records: <int>,
  total_matches: <int>,
  ability_priority: [
    { ability_id, name, avg_ap_all_players, avg_ap_winners, winner_premium_ap }, ...
  ],
  best_full_orders: [ top 5 ... ],
  best_openers_first4: [ top 5 ... ]
}
```

`winner_premium_ap` is the diff between winners' AP investment and the population average — a positive value means winners invest more here than non-winners do. This is the cleanest "what should I do differently" signal available from this dataset.

`best_full_orders` is sorted by win rate among orders meeting the sample floor (≥ 200 matches all-MMR / ≥ 100 high-MMR). `best_openers_first4` does the same for the first four ability points only, with a higher floor (≥ 400 / ≥ 200) since there are fewer distinct openers.

## `provenance`

Lists the API endpoints and asset URLs that fed this output, for reproducibility. No timestamps or per-call response data — we don't need them, and they'd bloat the file.

## What the all-heroes batch produces

For each of the 38 heroes:
- One `{hero_name}_build.json` file (~70KB each, ~2.7MB total)
- Per-hero CSVs: `{hero}_items.csv`, `{hero}_ability_orders.csv`
- One aggregate file: `all_heroes_index.json` — quick map of hero → file path + headline stats (baseline WR, recommended build cost, top ability)

The batch will:
1. Pull hero list from the API (already cached: `heroes.json`)
2. For each hero: pull item-stats, perm-stats, build-stats, ability-orders for both MMR slices (10 API calls/hero)
3. Pull individual build details for the top builds per hero (cached across runs)
4. Run `build_hero_output()` for each hero
5. Emit per-hero JSON + CSVs + the index

Total API calls per run: ~400–450, well within the 200 req/min IP limit if we space them ~0.3s apart.

## Sample-size watchouts that may bite at scale

Some heroes have far fewer matches than Shiv. Two failure modes to handle:
- **A method may not produce 16 items.** If the candidate pool drops below 16, the ILP becomes infeasible and Wilson can't fill all category slots. The script should fall back to relaxed sample floors and flag the hero.
- **Ability-order data may be sparse.** Heroes with low pick rates may have no full-order with ≥ 100 matches. We'll need to lower the floor or omit the field for those heroes.

Both are normal — we'll surface them in `all_heroes_index.json` so you can see which heroes need extra care before trusting the output.

## Reference files

- `build_hero_output.py` — the generator (in the outputs scratch dir, ready to be moved into the workspace)
- `shiv_build.json` — reference output, ~72 KB, validates the spec end-to-end
- `shiv_build_summary.md`, `shiv_mmr_comparison.md` — written analyses for context
