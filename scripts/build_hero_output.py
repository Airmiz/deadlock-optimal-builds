"""
Combined per-hero build output generator.

Produces a single JSON file per hero containing:
  - Hero metadata (id, name, abilities, baseline WR per MMR slice)
  - Item build for each MMR slice and each method (Wilson / ILP / Replication)
  - The "recommended" item build (ILP at high MMR) split into early/mid/late phases
  - Ability order (recommended full sequence + first-4 opener) per MMR slice
  - Per-ability AP priority (winners-weighted)
  - Provenance (patch, sample sizes, API queries)

This file is the reference implementation that we'll batch across all 38 heroes.
Inputs are the raw API pulls we've already saved for Shiv:
  - heroes.json, items.json (asset metadata, shared)
  - hero_stats.json + hero_stats_b91.json (baseline)
  - shiv_itemstats_raw.json + shiv_itemstats_hmmr.json (item stats)
  - shiv_perm2.json + shiv_perm2_hmmr.json (pair synergies)
  - shiv_buildstats.json + shiv_buildstats_hmmr.json + build_*.json (top builds)
  - shiv_abilityorder_all.json + shiv_abilityorder_hmmr.json (ability orders)
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import (
    ROOT, CACHE, HERO_OUT, HERO_DATA, BUILD_FILES, ASSETS,
    PATCH_ID, PATCH_TITLE, PATCH_MIN_TS,
    HMMR_BADGE, ASCENDANT_BADGE, ETERNUS_BADGE, SPEC_VERSION,
)

import json
import math
import glob
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any




# ============================================================
# Helpers shared across heroes
# ============================================================
def wilson_lb(wins: int, matches: int, z: float = 1.96) -> float:
    if matches == 0:
        return 0.0
    p = wins / matches
    n = matches
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (centre - margin) / denom


def is_upgrade_item(it: dict) -> bool:
    return it.get("type") == "upgrade" and it.get("item_slot_type") in ("weapon", "vitality", "spirit")


def extract_cooldown_s(item: dict) -> float | None:
    """Pull AbilityCooldown (in seconds) from an item's properties block."""
    props = item.get("properties") or {}
    raw = props.get("AbilityCooldown")
    if raw is None:
        return None
    val = raw.get("value") if isinstance(raw, dict) else raw
    try:
        cd = float(val)
        return cd if cd > 0 else None
    except (TypeError, ValueError):
        return None


# ============================================================
# Upgrade chains: Deadlock items can have a `component_items` field
# referencing a lower-tier item (by class_name). Buying the higher tier
# CONSUMES the component — they share a single inventory slot. Treating
# them as independent picks (which a naive ILP does) double-counts cost
# and slots.
# ============================================================
def build_lineage_map(items_by_id: dict) -> tuple[dict, dict]:
    """
    Returns:
      ancestors_of[item_id] = set of all transitive parent item_ids
                              (items whose presence would conflict)
      lineage_canon[item_id] = canonical (root) item id for the lineage
                                (every item in the same upgrade family
                                 maps to the same canonical id)
    """
    items_by_class = {it.get("class_name"): it for it in items_by_id.values()
                      if it.get("class_name")}
    parent_of: dict[int, set[int]] = {iid: set() for iid in items_by_id}
    for it in items_by_id.values():
        for cn in (it.get("component_items") or []):
            parent = items_by_class.get(cn)
            if parent and parent["id"] != it["id"]:
                parent_of[it["id"]].add(parent["id"])

    ancestors_of: dict[int, set[int]] = {}

    def get_ancestors(iid: int) -> set:
        if iid in ancestors_of:
            return ancestors_of[iid]
        out = set()
        for p in parent_of.get(iid, ()):
            out.add(p)
            out |= get_ancestors(p)
        ancestors_of[iid] = out
        return out

    for iid in items_by_id:
        get_ancestors(iid)

    # Group items into lineages via union-find on chain edges
    root: dict[int, int] = {iid: iid for iid in items_by_id}

    def find(x):
        while root[x] != x:
            root[x] = root[root[x]]
            x = root[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            root[ra] = rb

    for child, parents in parent_of.items():
        for p in parents:
            union(child, p)

    members: dict[int, list[int]] = {}
    for iid in items_by_id:
        r = find(iid)
        members.setdefault(r, []).append(iid)
    canon: dict[int, int] = {}
    for r, group in members.items():
        canonical = min(group)
        for m in group:
            canon[m] = canonical
    return ancestors_of, canon


def phase_for(buy_time_s: float) -> str:
    if buy_time_s < 750:
        return "early"
    if buy_time_s < 1500:
        return "mid"
    return "late"


# ============================================================
# Item build generation (3 methods)
# ============================================================
def build_candidates(item_stats: list, items_by_id: dict, baseline_wr: float,
                     min_matches: int, lineage_canon: dict | None = None,
                     score_fn=None) -> dict:
    """Score each upgrade item meeting the sample floor.

    If lineage_canon is provided, dedupe the candidates so each upgrade-chain
    lineage is represented by a single best-scored member. This prevents the
    downstream optimizers from picking, e.g., both Extra Spirit (T1) and
    Boundless Spirit (T4) in separate slots — they share an inventory slot
    when actually played because the higher tier consumes the lower.

    If `score_fn` is provided, it is called as `score_fn(wins, matches, item_id)`
    to compute the candidate's score, replacing the default `Wilson_LB(wins,
    matches) − baseline_wr`. This lets the hierarchical-pooling scorer
    (scripts/hierarchical.py) or any other alternative rule slot in without
    forking the method functions downstream.
    """
    raw: dict[int, dict] = {}
    for s in item_stats:
        it = items_by_id.get(s["item_id"])
        if not it or not is_upgrade_item(it):
            continue
        if s["matches"] < min_matches:
            continue
        wr = s["wins"] / s["matches"]
        lb = wilson_lb(s["wins"], s["matches"])
        sell_s = s.get("avg_sell_time_s") or 0
        sc = (score_fn(s["wins"], s["matches"], s["item_id"])
              if score_fn is not None else lb - baseline_wr)
        raw[s["item_id"]] = {
            "item_id": s["item_id"],
            "name": it["name"],
            "category": it["item_slot_type"],
            "tier": it["item_tier"],
            "cost": it["cost"],
            "matches": s["matches"],
            "wins": s["wins"],
            "win_rate": round(wr, 4),
            "wilson_lb": round(lb, 4),
            "score": round(sc, 4),
            "wr_delta_pp": round((wr - baseline_wr) * 100, 2),
            "avg_buy_time_s": round(s["avg_buy_time_s"], 1),
            "phase": phase_for(s["avg_buy_time_s"]),
            "avg_sell_time_s": round(sell_s, 1) if sell_s else None,
            "is_active": bool(it.get("is_active_item")),
            "cooldown_s": extract_cooldown_s(it),
            "imbue": it.get("imbue"),  # imbue_modifier_value, imbue_active, imbue_active_non_ult, or None
        }

    if not lineage_canon:
        return raw

    # Per-lineage: keep the strongest tier (best score; break ties by higher tier)
    best_per_lineage: dict[int, dict] = {}
    for c in raw.values():
        canon = lineage_canon.get(c["item_id"], c["item_id"])
        existing = best_per_lineage.get(canon)
        if existing is None:
            best_per_lineage[canon] = c
        else:
            score_better = c["score"] > existing["score"]
            score_tie = c["score"] == existing["score"]
            tier_better = c["tier"] > existing["tier"]
            if score_better or (score_tie and tier_better):
                best_per_lineage[canon] = c
    return {c["item_id"]: c for c in best_per_lineage.values()}


def method_wilson(candidates: dict) -> list:
    by_cat: dict[str, list] = defaultdict(list)
    for c in candidates.values():
        by_cat[c["category"]].append(c)
    for cat in by_cat:
        by_cat[cat].sort(key=lambda x: -x["score"])
    picks, used = [], set()
    for cat in ("weapon", "vitality", "spirit"):
        for c in by_cat[cat][:4]:
            picks.append({**c, "slot": cat})
            used.add(c["item_id"])
    flex = sorted(
        [c for c in candidates.values() if c["item_id"] not in used],
        key=lambda x: -x["score"],
    )[:4]
    for c in flex:
        picks.append({**c, "slot": "flex"})
    return picks


# Default cumulative soul budget by end of each phase, in souls. These are
# rough empirical defaults for hmmr play; the soul curve in /v1/analytics/
# player-performance-curve is the principled source if a tuning pass is
# worth the API cost. The defaults are deliberately *loose* — they prevent
# obviously infeasible 25k-soul-by-minute-15 builds without aggressively
# pruning expensive items that real players still buy.
DEFAULT_SOUL_BUDGETS = {
    "early": 6_000,    # cumulative through minute 12.5
    "mid":  18_000,    # cumulative through minute 25
    "late": 32_000,    # cumulative through end-of-match
}


def method_synergy_ilp(candidates: dict, pair_stats: list, pair_min_matches: int,
                       soul_budgets: dict | None = None,
                       matchup_score_augment: dict[int, float] | None = None,
                       matchup_weight: float = 0.5,
                       synergy_top_k: int = 400) -> list:
    """Synergy-aware ILP with optional per-phase cumulative cost constraints.

    `soul_budgets` (methodology review §3.1): when provided, adds three
    linear constraints to the ILP:

        sum_{i: phase(i)=early}     cost[i] * x[i] <= B_early
        sum_{i: phase(i) in {early,mid}}     cost[i] * x[i] <= B_mid
        sum_{i: all}                cost[i] * x[i] <= B_late

    These enforce temporal feasibility: a 25k-soul build that's optimal
    in isolation is rejected if it can't be afforded by minute 25.
    Keyed by phase name; missing keys leave that phase unconstrained.

    `matchup_score_augment` (methodology review §3.4): when provided,
    augments each item's score by `matchup_weight * matchup_delta_pp / 100`
    (delta_pp scaled back to WR space). The augment is added into the
    objective so the ILP picks items that are both individually strong
    AND specifically good against the chosen enemy comp. Without this,
    counter-pick recommendations only show as a sidebar — they don't
    affect the headline build.

    `synergy_top_k` (methodology review §5.3): cap on how many strongest
    pairwise synergies feed the ILP. The historical 400-item cutoff was
    a tractability heuristic; modern CBC handles 2000+ comfortably. Pass
    a larger number to let the long tail influence the build.

    Default behavior (all kwargs None / default) is unchanged from the
    pre-§3 ILP, so production output is stable until callers opt in.
    """
    import pulp

    pair_wr = {}
    for p in pair_stats:
        if p["matches"] < pair_min_matches:
            continue
        ids = tuple(sorted(p["item_ids"]))
        pair_wr[ids] = (p["wins"] / p["matches"], p["matches"])

    item_ids = list(candidates.keys())
    synergy_full = {}
    for (a, b), (pwr, pm) in pair_wr.items():
        if a not in candidates or b not in candidates:
            continue
        ind_avg = (candidates[a]["win_rate"] + candidates[b]["win_rate"]) / 2
        weight = min(1.0, pm / max(1, pair_min_matches * 4))
        bonus = (pwr - ind_avg) * weight
        synergy_full[(a, b)] = bonus
    # Keep only the strongest synergies. Default top-400 was a 2024-era
    # tractability heuristic; §5.3 says modern CBC handles 2000+ fine.
    sorted_pairs = sorted(synergy_full.items(), key=lambda kv: -abs(kv[1]))[:synergy_top_k]
    synergy = dict(sorted_pairs)

    prob = pulp.LpProblem("hero_optimal", pulp.LpMaximize)
    x = {iid: pulp.LpVariable(f"x_{iid}", cat="Binary") for iid in item_ids}
    pair_keys = list(synergy.keys())
    y = {k: pulp.LpVariable(f"y_{k[0]}_{k[1]}", cat="Binary") for k in pair_keys}

    # Methodology review §3.4: bake the matchup delta into the per-item
    # score when the caller passes an enemy-specific augment. delta_pp
    # divided by 100 puts it on the same scale as the base score (which
    # is roughly WR-delta), so matchup_weight stays interpretable
    # (~0.5 means "matchup signal is half as strong as base lift").
    def _effective_score(iid: int) -> float:
        base = candidates[iid]["score"]
        if matchup_score_augment is not None:
            return base + matchup_weight * matchup_score_augment.get(iid, 0.0) / 100.0
        return base

    prob += (
        pulp.lpSum(_effective_score(i) * x[i] for i in item_ids)
        + pulp.lpSum(synergy[k] * y[k] for k in pair_keys)
    )
    for (a, b) in pair_keys:
        prob += y[(a, b)] <= x[a]
        prob += y[(a, b)] <= x[b]
        prob += y[(a, b)] >= x[a] + x[b] - 1
    for cat in ("weapon", "vitality", "spirit"):
        cat_ids = [i for i in item_ids if candidates[i]["category"] == cat]
        if cat_ids:
            prob += pulp.lpSum(x[i] for i in cat_ids) >= 4
            prob += pulp.lpSum(x[i] for i in cat_ids) <= 8
    prob += pulp.lpSum(x[i] for i in item_ids) == 16

    # Optional per-phase cumulative cost constraints (methodology review §3.1).
    # Phase membership comes from build_candidates' phase_for() which is
    # already baked into each candidate dict.
    if soul_budgets:
        early_ids = [i for i in item_ids if candidates[i]["phase"] == "early"]
        mid_ids   = [i for i in item_ids if candidates[i]["phase"] == "mid"]
        late_ids  = [i for i in item_ids if candidates[i]["phase"] == "late"]
        cum_early = early_ids
        cum_mid   = early_ids + mid_ids
        cum_late  = early_ids + mid_ids + late_ids
        if "early" in soul_budgets:
            prob += pulp.lpSum(candidates[i]["cost"] * x[i] for i in cum_early) <= soul_budgets["early"]
        if "mid" in soul_budgets:
            prob += pulp.lpSum(candidates[i]["cost"] * x[i] for i in cum_mid) <= soul_budgets["mid"]
        if "late" in soul_budgets:
            prob += pulp.lpSum(candidates[i]["cost"] * x[i] for i in cum_late) <= soul_budgets["late"]

    prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=4))

    chosen = [i for i in item_ids if pulp.value(x[i]) > 0.5]
    by_cat: dict[str, list] = defaultdict(list)
    for i in chosen:
        by_cat[candidates[i]["category"]].append(i)
    for cat in by_cat:
        by_cat[cat].sort(key=lambda i: -candidates[i]["score"])
    picks, used = [], set()
    for cat in ("weapon", "vitality", "spirit"):
        for i in by_cat[cat][:4]:
            picks.append({**candidates[i], "slot": cat})
            used.add(i)
    flex_ids = sorted([i for i in chosen if i not in used], key=lambda i: -candidates[i]["score"])[:4]
    for i in flex_ids:
        picks.append({**candidates[i], "slot": "flex"})
    return picks


def method_build_replication(candidates: dict, build_stats_raw: list,
                             baseline_wr: float, build_files_dir: Path,
                             build_match_floor: int) -> tuple[list, list]:
    stats_by_id = {b["hero_build_id"]: b for b in build_stats_raw}
    item_weight: Counter = Counter()
    builds_seen = []
    qualifying_ids = [b["hero_build_id"] for b in build_stats_raw if b["matches"] >= build_match_floor]
    for bid in qualifying_ids:
        f = build_files_dir / f"build_{bid}.json"
        if not f.exists():
            continue
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        if not (isinstance(d, list) and d):
            continue
        b = d[0]["hero_build"]
        st = stats_by_id[bid]
        wr = st["wins"] / st["matches"]
        weight = st["matches"] * max(0, wr - baseline_wr + 0.02)
        seen_in_build = set()
        for cat in b["details"]["mod_categories"]:
            for mod in cat.get("mods", []):
                aid = mod.get("ability_id")
                if aid:
                    seen_in_build.add(aid)
        for iid in seen_in_build:
            item_weight[iid] += weight
        builds_seen.append({
            "build_id": bid,
            "name": b.get("name", "?"),
            "win_rate": round(wr, 4),
            "matches": st["matches"],
        })

    ranked = []
    for iid, w in item_weight.items():
        if iid in candidates:
            ranked.append({**candidates[iid], "build_freq_weight": round(w, 1)})
    ranked.sort(key=lambda x: -x["build_freq_weight"])

    by_cat: dict[str, list] = defaultdict(list)
    for c in ranked:
        by_cat[c["category"]].append(c)
    picks, used = [], set()
    for cat in ("weapon", "vitality", "spirit"):
        for c in by_cat[cat][:4]:
            picks.append({**c, "slot": cat})
            used.add(c["item_id"])
    pool = [c for c in ranked if c["item_id"] not in used][:4]
    for c in pool:
        picks.append({**c, "slot": "flex"})
    return picks, builds_seen


# ============================================================
# Ability order analysis
# ============================================================
def analyze_ability_orders(records: list, ability_id_to_name: dict, sample_floor: int) -> dict:
    """Return ability-order summary: top sequences, first-4 patterns, per-ability priority."""
    for r in records:
        r["wr"] = r["wins"] / r["matches"] if r["matches"] else 0
    total_matches = sum(r["matches"] for r in records)
    total_wins = sum(r["wins"] for r in records)

    # Per-ability average AP investment
    pts_match: dict[int, float] = defaultdict(float)
    pts_wins: dict[int, float] = defaultdict(float)
    for r in records:
        c = Counter(r["abilities"])
        for aid, n in c.items():
            pts_match[aid] += n * r["matches"]
            pts_wins[aid] += n * r["wins"]
    priority = []
    for aid, name in ability_id_to_name.items():
        avg_all = pts_match.get(aid, 0) / total_matches if total_matches else 0
        avg_win = pts_wins.get(aid, 0) / total_wins if total_wins else 0
        priority.append({
            "ability_id": aid,
            "name": name,
            "avg_ap_all_players": round(avg_all, 2),
            "avg_ap_winners": round(avg_win, 2),
            "winner_premium_ap": round(avg_win - avg_all, 2),
        })
    priority.sort(key=lambda x: -x["avg_ap_winners"])

    # Top full orders (need a meaningful sample)
    meaningful = sorted([r for r in records if r["matches"] >= sample_floor], key=lambda r: -r["wr"])
    top_orders = []
    for r in meaningful[:5]:
        top_orders.append({
            "sequence_ids": r["abilities"],
            "sequence_names": [ability_id_to_name.get(a, "?") for a in r["abilities"]],
            "wins": r["wins"],
            "losses": r["losses"],
            "matches": r["matches"],
            "players": r["players"],
            "win_rate": round(r["wr"], 4),
        })

    # First-4-points patterns
    first4_wr: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for r in records:
        if len(r["abilities"]) >= 4:
            k = tuple(r["abilities"][:4])
            first4_wr[k][0] += r["wins"]
            first4_wr[k][1] += r["matches"]
    first4_rows = sorted(
        [(k, w, m) for k, (w, m) in first4_wr.items() if m >= sample_floor * 2],
        key=lambda x: -x[1] / x[2],
    )
    first4 = [{
        "sequence_names": [ability_id_to_name.get(a, "?") for a in k],
        "wins": w, "matches": m, "win_rate": round(w / m, 4),
    } for k, w, m in first4_rows[:5]]

    return {
        "total_records": len(records),
        "total_matches": total_matches,
        "ability_priority": priority,
        "best_full_orders": top_orders,
        "best_openers_first4": first4,
    }


# ============================================================
# Item metadata (pick-rate tags + community-build annotations)
# ============================================================
def compute_item_metadata(build_stats_raw: list, build_files_dir: Path,
                          build_match_floor: int) -> dict:
    """
    Walk the cached community builds for this hero and compute, per item:
      - pick_rate: fraction of qualifying builds containing the item
      - tag: 'core' (>0.7), 'flex' (0.3-0.7), or 'situational' (<=0.3)
      - annotation: best author-written tooltip (highest-WR build, then longest)
      - sample sizes for transparency

    Items that never appear in any community build won't be in the result;
    callers should treat absence as tag='stat'.
    """
    stats_by_id = {b["hero_build_id"]: b for b in build_stats_raw}
    qualifying_ids = [b["hero_build_id"] for b in build_stats_raw
                      if b["matches"] >= build_match_floor]
    # Imbue-target collection uses a LOWER floor than the rest of the
    # metadata because imbue choice is hero-and-item specific (not
    # skill-specific) — pulling from a wider build pool gives us a
    # defensible target on items that only show up in 1-2 high-MMR builds
    # (e.g. Lash's Mystic Reverb where only 2 of 4 builds chose a target
    # and both fell below the 100-match high-MMR floor). We do this in a
    # separate pre-pass so we don't pollute pick-rate / tag / annotation
    # aggregation with lower-quality builds.
    imbue_target_floor = 30
    imbue_qualifying_ids = [b["hero_build_id"] for b in build_stats_raw
                            if b["matches"] >= imbue_target_floor]

    imbue_targets: dict[int, Counter] = defaultdict(Counter)
    for bid in imbue_qualifying_ids:
        f = build_files_dir / f"build_{bid}.json"
        if not f.exists():
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            continue
        if not (isinstance(d, list) and d):
            continue
        b = d[0].get("hero_build")
        if not b or "details" not in b:
            continue
        for cat in b["details"].get("mod_categories", []):
            for mod in cat.get("mods", []):
                iid = mod.get("ability_id")
                if not iid:
                    continue
                tgt = mod.get("imbue_target_ability_id")
                if tgt:
                    imbue_targets[iid][tgt] += 1

    item_appearances: Counter = Counter()
    item_annotations: dict[int, list[tuple[float, int, str]]] = defaultdict(list)
    builds_processed = 0

    for bid in qualifying_ids:
        f = build_files_dir / f"build_{bid}.json"
        if not f.exists():
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            continue
        if not (isinstance(d, list) and d):
            continue
        b = d[0].get("hero_build")
        if not b or "details" not in b:
            continue
        st = stats_by_id.get(bid)
        if not st:
            continue
        wr = st["wins"] / st["matches"]
        builds_processed += 1
        seen_in_build: set[int] = set()
        for cat in b["details"].get("mod_categories", []):
            for mod in cat.get("mods", []):
                iid = mod.get("ability_id")
                if not iid:
                    continue
                if iid not in seen_in_build:
                    item_appearances[iid] += 1
                    seen_in_build.add(iid)
                ann = mod.get("annotation")
                if ann and ann.strip():
                    item_annotations[iid].append((wr, st["matches"], ann.strip()))

    if builds_processed == 0:
        return {}

    out: dict[int, dict] = {}
    for iid, count in item_appearances.items():
        rate = count / builds_processed
        if rate > 0.7:
            tag = "core"
        elif rate > 0.3:
            tag = "flex"
        else:
            tag = "situational"
        annots = sorted(item_annotations.get(iid, []),
                        key=lambda a: (-a[0], -a[1], -len(a[2])))
        annotation = annots[0][2] if annots else ""
        # Top imbue target across this hero's builds (if any). We surface
        # the most-mentioned target id; the page resolves it to an ability
        # name via the items dict at render time.
        tgt_counter = imbue_targets.get(iid)
        top_imbue_target_id = None
        top_imbue_target_share = None
        if tgt_counter:
            (top_id, top_count), = tgt_counter.most_common(1)
            top_imbue_target_id = top_id
            top_imbue_target_share = round(top_count / sum(tgt_counter.values()), 3)
        out[iid] = {
            "tag": tag,
            "pick_rate": round(rate, 3),
            "annotation": annotation,
            "builds_appearing_in": count,
            "builds_total": builds_processed,
            "imbue_target_id": top_imbue_target_id,
            "imbue_target_share": top_imbue_target_share,
        }
    return out


def classify_2d_tag(pick_rate: float, wr_delta_pp: float) -> str:
    """2D tag taxonomy per methodology review §6.4.

    Replaces the previous one-axis (pick_rate only) CORE/FLEX/SIT/STAT
    with a five-class system that combines pick frequency with adjusted
    lift. Lift here is the raw `wr_delta_pp` already on each candidate
    (item WR minus hero baseline). Once §2.3 propensity correction is
    real, swap in the propensity-corrected lift; until then the raw
    lift is the best signal we have.

    The 'trap_popular' tag is the highest-value addition: it's the only
    way the page can ever tell a user "stop buying this even though
    everyone does". Under the previous taxonomy a bad-but-popular item
    just got tagged CORE with no signal that anything was off.
    """
    if pick_rate >= 0.50 and wr_delta_pp > 1.0:
        return "core_proven"
    if pick_rate >= 0.50 and -1.0 <= wr_delta_pp <= 1.0:
        return "core_inherited"
    if pick_rate >= 0.40 and wr_delta_pp < -1.0:
        return "trap_popular"
    if pick_rate < 0.10 and wr_delta_pp > 3.0:
        return "stat_anomaly"
    if pick_rate < 0.30 and wr_delta_pp > 2.0:
        return "tech_pick"
    # Fall through to the legacy 1D banding for the cases the 2D matrix
    # doesn't explicitly capture (e.g. mid-pick-rate / mid-lift items).
    if pick_rate > 0.7:
        return "core"
    if pick_rate > 0.3:
        return "flex"
    if pick_rate > 0:
        return "situational"
    return "stat"


def decorate_picks(picks: list, metadata: dict) -> list:
    """Attach tag + annotation to each pick. Items not in metadata are tagged 'stat'.

    Methodology review §6.4: tags are now a 2D function of (pick_rate,
    wr_delta_pp). The legacy 1D pick-rate band is preserved on each
    pick as `pick_rate_tag` for backwards compatibility with downstream
    consumers that haven't migrated to the 5-class taxonomy yet.
    """
    for p in picks:
        meta = metadata.get(p["item_id"])
        pick_rate = meta["pick_rate"] if meta else 0.0
        legacy_tag = (meta["tag"] if meta else "stat")
        lift = p.get("wr_delta_pp", 0.0)
        p["tag"] = classify_2d_tag(pick_rate, lift)
        p["pick_rate_tag"] = legacy_tag  # legacy 1D banding
        p["pick_rate"] = pick_rate
        if meta:
            if meta.get("annotation"):
                p["annotation"] = meta["annotation"]
            if meta.get("imbue_target_id"):
                p["imbue_target_id"] = meta["imbue_target_id"]
                p["imbue_target_share"] = meta.get("imbue_target_share")
    return picks


def attach_lineage_chain(picks: list, ancestors_of: dict,
                         items_by_id: dict, item_stats: list,
                         metadata: dict | None = None) -> list:
    """Decorate each pick with its lineage_chain — the lower-tier ancestors
    a player should pre-buy in the early/mid game. The chain is sorted by
    tier ascending so the earliest pre-purchase is first.

    Each chain entry also carries imbue metadata (type + community-build
    target) so the page can render imbue badges on stage rows. This
    matters when the imbuable component is a passive (Compress Cooldown,
    Mystic Expansion, Duration Extender) but the optimizer picks its
    non-imbuable T3/T4 descendant — without this, the only imbue affordance
    in the build wouldn't be visible on the chip that represents it.
    """
    stats_by_id = {s["item_id"]: s for s in item_stats}
    for p in picks:
        ancs = ancestors_of.get(p["item_id"], set())
        chain = []
        for anc_id in ancs:
            it = items_by_id.get(anc_id)
            if not it:
                continue
            anc_stat = stats_by_id.get(anc_id)
            anc_meta = (metadata or {}).get(anc_id, {})
            chain.append({
                "item_id": anc_id,
                "name": it.get("name"),
                "tier": it.get("item_tier"),
                "cost": it.get("cost"),
                "matches": anc_stat["matches"] if anc_stat else None,
                "avg_buy_time_min": (round(anc_stat["avg_buy_time_s"] / 60, 1)
                                     if anc_stat else None),
                "imbue": it.get("imbue"),
                "imbue_target_id": anc_meta.get("imbue_target_id"),
                "imbue_target_share": anc_meta.get("imbue_target_share"),
            })
        chain.sort(key=lambda c: (c["tier"] or 0, c["cost"] or 0))
        if chain:
            p["lineage_chain"] = chain
    return picks


# ============================================================
# Hero output assembly
# ============================================================
def get_hero_abilities(hero: dict, items_by_id: dict, items_by_classname: dict) -> dict:
    """Map hero's signature ability IDs -> names."""
    out = {}
    for slot in ("signature1", "signature2", "signature3", "signature4"):
        cn = hero.get("items", {}).get(slot)
        if not cn:
            continue
        it = items_by_classname.get(cn)
        if it:
            out[it["id"]] = it.get("name", cn)
    return out


def _mmr_slices_payload(base_all: dict, base_hmmr: dict,
                        base_asc: dict | None, base_eter: dict | None) -> dict:
    """Compose the mmr_slices block. Always emits all_mmr + high_mmr (the
    historical invariant). Ascendant+ and Eternus+ are added only when their
    cached baseline file exists *and* contains this hero (otherwise the
    higher-rank player pool was empty for this hero on this patch). The
    page treats absent slices as 'insufficient data'."""
    out = {
        "all_mmr": {
            "filter": "no MMR filter",
            "baseline_win_rate": round(base_all["wins"] / base_all["matches"], 4),
            "matches": base_all["matches"],
            "players": base_all["players"],
        },
        "high_mmr": {
            "filter": f"min_average_badge={HMMR_BADGE} (Phantom+)",
            "baseline_win_rate": round(base_hmmr["wins"] / base_hmmr["matches"], 4),
            "matches": base_hmmr["matches"],
            "players": base_hmmr["players"],
        },
    }
    if base_asc and base_asc.get("matches"):
        out["ascendant_plus"] = {
            "filter": f"min_average_badge={ASCENDANT_BADGE} (Ascendant+)",
            "baseline_win_rate": round(base_asc["wins"] / base_asc["matches"], 4),
            "matches": base_asc["matches"],
            "players": base_asc["players"],
        }
    if base_eter and base_eter.get("matches"):
        out["eternus_plus"] = {
            "filter": f"min_average_badge={ETERNUS_BADGE} (Eternus+)",
            "baseline_win_rate": round(base_eter["wins"] / base_eter["matches"], 4),
            "matches": base_eter["matches"],
            "players": base_eter["players"],
        }
    return out


def select_recommended(item_methods: dict, ability: dict) -> dict:
    """Pick the headline build the user should run with: ILP at high MMR, with phased breakdown."""
    picks = item_methods["high_mmr"]["synergy_ilp"]["picks"]
    by_phase: dict[str, list] = defaultdict(list)
    for p in picks:
        sell_s = p.get("avg_sell_time_s")
        entry = {
            "slot": p["slot"], "category": p["category"], "tier": p["tier"], "cost": p["cost"],
            "name": p["name"], "item_id": p["item_id"],
            "avg_buy_time_min": round(p["avg_buy_time_s"] / 60, 1),
            "avg_sell_time_min": round(sell_s / 60, 1) if sell_s else None,
            "win_rate": p["win_rate"],
            "tag": p.get("tag", "stat"),
            "pick_rate": p.get("pick_rate", 0.0),
            "is_active": p.get("is_active", False),
            "cooldown_s": p.get("cooldown_s"),
            "imbue": p.get("imbue"),
        }
        if p.get("annotation"):
            entry["annotation"] = p["annotation"]
        if p.get("lineage_chain"):
            entry["lineage_chain"] = p["lineage_chain"]
        if p.get("imbue_target_id"):
            entry["imbue_target_id"] = p["imbue_target_id"]
            entry["imbue_target_share"] = p.get("imbue_target_share")
        by_phase[p["phase"]].append(entry)
    for ph in by_phase:
        by_phase[ph].sort(key=lambda x: x["avg_buy_time_min"])
    total_cost = sum(p["cost"] for p in picks)
    best_full = ability["high_mmr"]["best_full_orders"][0] if ability["high_mmr"]["best_full_orders"] else None
    best_opener = ability["high_mmr"]["best_openers_first4"][0] if ability["high_mmr"]["best_openers_first4"] else None
    return {
        "items": {
            "method": "synergy_ilp",
            "mmr_slice": "high_mmr",
            "total_cost": total_cost,
            "phases": {
                "early": by_phase.get("early", []),
                "mid": by_phase.get("mid", []),
                "late": by_phase.get("late", []),
            },
        },
        "abilities": {
            "ap_priority_order": [p["name"] for p in ability["high_mmr"]["ability_priority"]],
            "best_full_order": best_full,
            "best_opener_first4": best_opener,
        },
    }


def build_hero_output(
    hero_id: int,
    hero_name: str,
    paths: dict,
    items_by_id: dict,
    items_by_classname: dict,
    heroes_by_id: dict,
    score_fn_provider=None,
) -> dict:
    """Assemble the full per-hero output dict.

    If `score_fn_provider` is given, it is called once per MMR slice as
    `score_fn_provider(hero_id, slice_label, baseline_wr)` and is expected
    to return a `(wins, matches, item_id) -> score` callable that
    overrides the default Wilson-LB scoring. Used by run_all_heroes.py
    when `DEADLOCK_SCORING=hierarchical` is set to inject pre-fitted
    cross-hero priors (methodology review §2.4).
    """
    hero = heroes_by_id[hero_id]

    # ---- baselines ----
    # All-MMR + HMMR are required (legacy invariant). Ascendant+ and Eternus+
    # are optional — if the cache file is missing or doesn't contain this
    # hero (zero matches), we degrade gracefully rather than failing the run.
    def _baseline_for(path_key: str) -> dict | None:
        p = paths.get(path_key)
        if not p or not Path(p).exists():
            return None
        try:
            with open(p, encoding="utf-8") as f:
                rows = json.load(f)
        except Exception:
            return None
        return next((h for h in rows if h["hero_id"] == hero_id), None)

    base_all = _baseline_for("hero_stats_all")
    base_hmmr = _baseline_for("hero_stats_hmmr")
    base_asc = _baseline_for("hero_stats_asc")
    base_eter = _baseline_for("hero_stats_eter")
    if base_all is None or base_hmmr is None:
        raise RuntimeError(f"hero {hero_id} missing all_mmr or high_mmr baseline — cache out of date?")

    # ---- upgrade chain map (one per asset version, but cheap so we do it here) ----
    ancestors_of, lineage_canon = build_lineage_map(items_by_id)

    # ---- item methods, all four MMR slices ----
    # Each tuple: (output_key, paths_key_suffix, baseline_row, candidate_floor,
    # pair_floor, build_floor, ability_floor). Ascendant+ and Eternus+ floors
    # are relaxed to reflect their thinner sample sizes.
    slice_specs = [
        ("all_mmr",        "all",  base_all,  500, 500, 200, 200),
        ("high_mmr",       "hmmr", base_hmmr, 300, 200, 100, 100),
        ("ascendant_plus", "asc",  base_asc,  100, 100,  50,  50),
        ("eternus_plus",   "eter", base_eter,  30,  30,  15,  15),
    ]

    item_methods: dict = {}
    ability: dict = {}
    ability_id_to_name = get_hero_abilities(hero, items_by_id, items_by_classname)

    for slice_label, paths_key, baseline, min_match_floor, pair_floor, build_floor, ability_floor in slice_specs:
        # Optional slice with no usable baseline → empty placeholder so the
        # page can show "insufficient data" without breaking layout.
        if not baseline or not baseline.get("matches"):
            item_methods[slice_label] = {
                "candidate_count": 0,
                "min_matches_filter": min_match_floor,
                "wilson_greedy": {"picks": []},
                "synergy_ilp": {"picks": []},
                "build_replication": {"picks": [], "source_builds": []},
                "item_metadata": {},
            }
            ability[slice_label] = {
                "total_records": 0, "total_matches": 0,
                "ability_priority": [], "best_full_orders": [], "best_openers_first4": [],
            }
            continue

        baseline_wr = baseline["wins"] / baseline["matches"]
        # Tolerate per-file misses (e.g. asc/eter fetched on a thin slice
        # where the API returned []) — treat as empty input rather than crash.
        def _load_or_empty(key: str) -> list:
            p = paths.get(key)
            if not p or not Path(p).exists():
                return []
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []

        item_stats = _load_or_empty(f"item_stats_{paths_key}")
        pair_stats = _load_or_empty(f"pair_stats_{paths_key}")
        build_stats_raw = _load_or_empty(f"build_stats_{paths_key}")
        ability_records = _load_or_empty(f"abilities_{paths_key}")
        # Optional cross-hero EB scoring (methodology review §2.4). When
        # the provider is omitted (default), build_candidates falls back
        # to the original Wilson-LB-minus-baseline rule and production
        # output is unchanged.
        score_fn = (score_fn_provider(hero_id, slice_label, baseline_wr)
                    if score_fn_provider is not None else None)
        candidates = build_candidates(item_stats, items_by_id, baseline_wr,
                                      min_match_floor, lineage_canon=lineage_canon,
                                      score_fn=score_fn)

        m1 = method_wilson(candidates)
        # Synergy ILP can fail on tiny candidate pools (no feasible solution
        # under category constraints) — fall back to the Wilson greedy picks.
        try:
            m2 = method_synergy_ilp(candidates, pair_stats, pair_floor) if candidates else []
        except Exception:
            m2 = list(m1)
        m3, builds_seen = method_build_replication(
            candidates, build_stats_raw, baseline_wr, CACHE, build_floor
        )

        # Per-slice item metadata (pick rate + best annotation across community builds)
        metadata = compute_item_metadata(build_stats_raw, BUILD_FILES, build_floor)
        m1 = decorate_picks(m1, metadata)
        m2 = decorate_picks(m2, metadata)
        m3 = decorate_picks(m3, metadata)
        # Lineage chain: lower-tier ancestors a player should pre-buy.
        m1 = attach_lineage_chain(m1, ancestors_of, items_by_id, item_stats, metadata)
        m2 = attach_lineage_chain(m2, ancestors_of, items_by_id, item_stats, metadata)
        m3 = attach_lineage_chain(m3, ancestors_of, items_by_id, item_stats, metadata)

        # Joint item + ability archetypes (methodology review §3.6).
        # Cluster the cached community builds for this slice by their
        # ability-ladder fingerprint, then aggregate items per cluster.
        # Each archetype ships its own (items, ability order) pair, so
        # the page can render conditional recommendations instead of
        # one global build that ignores the imbue / cooldown / spirit
        # interaction with ability investment.
        try:
            from joint_optimization import archetypes_for_slice
            joint_archetypes = archetypes_for_slice(
                candidates, build_stats_raw, baseline_wr,
                BUILD_FILES, build_floor, ability_id_to_name,
            )
            # Decorate per-archetype items with the same metadata + lineage
            # the other methods get.
            for arch in joint_archetypes:
                arch["items"] = decorate_picks(arch["items"], metadata)
                arch["items"] = attach_lineage_chain(
                    arch["items"], ancestors_of, items_by_id, item_stats, metadata,
                )
        except Exception:
            joint_archetypes = []

        item_methods[slice_label] = {
            "candidate_count": len(candidates),
            "min_matches_filter": min_match_floor,
            "wilson_greedy": {"picks": m1},
            "synergy_ilp": {"picks": m2},
            "build_replication": {"picks": m3, "source_builds": builds_seen},
            "joint_archetypes": joint_archetypes,
            "item_metadata": metadata,
        }
        ability[slice_label] = analyze_ability_orders(
            ability_records, ability_id_to_name, sample_floor=ability_floor
        )

    # ---- recommended (the answer) ----
    recommended = select_recommended(item_methods, ability)

    out = {
        "spec_version": SPEC_VERSION,
        "hero": {
            "id": hero_id,
            "name": hero_name,
            "abilities": [
                {"id": aid, "name": name}
                for aid, name in ability_id_to_name.items()
            ],
        },
        "patch": {"id": PATCH_ID, "title": PATCH_TITLE, "min_unix_timestamp": PATCH_MIN_TS},
        "mmr_slices": _mmr_slices_payload(base_all, base_hmmr, base_asc, base_eter),
        "recommended": recommended,
        "items": item_methods,
        "ability_orders": ability,
        "provenance": {
            "data_source": "api.deadlock-api.com",
            "endpoints_used": [
                "/v1/analytics/hero-stats",
                "/v1/analytics/item-stats",
                "/v1/analytics/item-permutation-stats?comb_size=2",
                "/v1/analytics/hero-build-stats/{hero_id}",
                "/v1/analytics/ability-order-stats",
                "/v1/builds (per-build details)",
            ],
            "asset_sources": [
                "https://assets.deadlock-api.com/v2/heroes",
                "https://assets.deadlock-api.com/v2/items",
            ],
        },
    }
    return out


# ============================================================
# Run for Shiv (reference implementation)
# ============================================================
def main() -> None:
    items_by_id = {i["id"]: i for i in json.load(open(CACHE / "items.json"))}
    items_by_classname = {i["class_name"]: i for i in items_by_id.values() if "class_name" in i}
    heroes_by_id = {h["id"]: h for h in json.load(open(CACHE / "heroes.json"))}

    paths = {
        "hero_stats_all":  CACHE / "hero_stats.json",
        "hero_stats_hmmr": CACHE / "hero_stats_b91.json",
        "item_stats_all":  CACHE / "shiv_itemstats_raw.json",
        "item_stats_hmmr": CACHE / "shiv_itemstats_hmmr.json",
        "pair_stats_all":  CACHE / "shiv_perm2.json",
        "pair_stats_hmmr": CACHE / "shiv_perm2_hmmr.json",
        "build_stats_all": CACHE / "shiv_buildstats.json",
        "build_stats_hmmr":CACHE / "shiv_buildstats_hmmr.json",
        "abilities_all":   CACHE / "shiv_abilityorder_all.json",
        "abilities_hmmr":  CACHE / "shiv_abilityorder_hmmr.json",
    }

    out = build_hero_output(
        hero_id=19, hero_name="Shiv",
        paths=paths,
        items_by_id=items_by_id, items_by_classname=items_by_classname,
        heroes_by_id=heroes_by_id,
    )

    target = ROOT / "shiv_build.json"
    with open(target, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[saved] {target}  ({target.stat().st_size:,} bytes)")

    # Quick sanity print
    rec = out["recommended"]
    print(f"\nHero: {out['hero']['name']} (id {out['hero']['id']})")
    print(f"Patch: {out['patch']['id']} — {out['patch']['title']}")
    print(f"All-MMR baseline WR: {out['mmr_slices']['all_mmr']['baseline_win_rate']*100:.2f}%")
    print(f"High-MMR baseline WR: {out['mmr_slices']['high_mmr']['baseline_win_rate']*100:.2f}%")
    print(f"\nRecommended build (high-MMR Synergy ILP, total cost ${rec['items']['total_cost']:,}):")
    for ph in ("early", "mid", "late"):
        items_in_phase = rec["items"]["phases"][ph]
        print(f"  {ph.upper()} ({len(items_in_phase)} items)")
        for p in items_in_phase:
            print(f"    [{p['slot']:7s}] {p['name']:28s} t{p['tier']} ${p['cost']:>4} buy@{p['avg_buy_time_min']:4.1f}min  WR {p['win_rate']*100:.2f}%")
    print(f"\nAP priority (winner-weighted): {' > '.join(rec['abilities']['ap_priority_order'])}")
    if rec["abilities"]["best_opener_first4"]:
        op = rec["abilities"]["best_opener_first4"]
        print(f"Best opener (first 4 points): {' → '.join(op['sequence_names'])}  WR {op['win_rate']*100:.2f}% (n={op['matches']:,})")


if __name__ == "__main__":
    main()
