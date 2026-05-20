"""Joint item + ability optimization (methodology review §3.6).

The base pipeline produces independent item recommendations (from item-stats
+ pairwise synergies + ILP) and ability orders (from ability-order-stats),
then renders both side-by-side. That misses the conditional dependency:
imbue items target a specific ability, cooldown items scale with how
heavily the targeted ability is leveled, and spirit-power amplifiers
only matter when the hero's damage profile leans on abilities.

§3.6 fix: cluster the cached community builds by their ability ladder
fingerprint, then aggregate items separately within each cluster. The
output is a list of *archetype* recommendations, each shipping its own
(item set, ability order) pair. A Suppressor-build hero gets one
archetype; a Mystic-Reverb-build same hero gets another.

Implementation notes
--------------------

Each cached build_<id>.json carries
`details.ability_order.currency_changes`: a list of
{ability_id, currency_type, delta} entries describing the full ladder.
`currency_type=2` is the "AP" spent to unlock the next ability tier;
`currency_type=1` is the upgrade-points spent to level a specific
ability past its base unlock.

The cluster key is the ordered sequence of which abilities receive
their *first* upgrade-point spend (currency_type=1). For most heroes
this stabilizes the cluster at 2–4 archetypes — e.g. Shiv splits into
"Bloodletting-first" vs "Slice-first" vs the rest.

Aggregation within a cluster mirrors `method_build_replication`: weight
each build by `matches × max(0, wr − baseline + 0.02)`, count item
appearances across builds, then take the top-K per category. The
returned dict includes the cluster's modal full ladder (longest common
prefix of the per-build ladders) so the page can render an archetype's
ability order directly from the cluster.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


# How many "first upgrade" abilities form the cluster fingerprint.
# 3 gives strong separation without exploding the cluster count for
# heroes with thin build pools.
FINGERPRINT_K = 3

# Minimum builds per cluster to surface it. Smaller clusters get merged
# into a residual "other" archetype only if any builds remain unassigned;
# normally these tiny clusters represent one-off author experiments and
# don't merit a separate archetype card.
MIN_BUILDS_PER_CLUSTER = 2


def _cluster_key(changes: list[dict]) -> tuple[int, ...]:
    """Sequence of first-K abilities by *max position* (when tier 3 lands).

    Unlock order doesn't carry strategic signal in Deadlock — all four
    abilities are usually unlocked early at 1 AP each. What matters is
    which ability gets its tier-3 (the 5-AP commitment) first, then
    second, etc. That's the "max order" that defines the archetype.

    The fingerprint records abilities in ascending order of the
    currency_changes index where their tier-3 upgrade lands (delta=-5).
    Abilities that never reach tier 3 in the template (rare for
    high-MMR Steam builds, which tend to plan a full 16-step ladder)
    are appended at the end ordered by their highest tier reached.

    Returns a tuple of the first FINGERPRINT_K ability_ids — typically
    K=3, which fully identifies the archetype since the 4th is whatever
    remains.
    """
    max_position: dict[int, int] = {}
    highest_tier: dict[int, int] = {}
    first_touch: dict[int, int] = {}
    for i, c in enumerate(changes):
        if c.get("currency_type") != 1:
            continue
        aid = c.get("ability_id")
        if aid is None:
            continue
        first_touch.setdefault(aid, i)
        delta = c.get("delta", 0)
        tier_value = -delta  # delta is negative; tier1=1, tier2=2, tier3=5
        if tier_value > highest_tier.get(aid, 0):
            highest_tier[aid] = tier_value
        if tier_value == 5:
            max_position[aid] = i

    # Maxed abilities ordered by when they reached tier 3.
    maxed = sorted(max_position.items(), key=lambda x: x[1])
    ordered: list[int] = [aid for aid, _ in maxed]

    # Append partially-leveled abilities (no tier-3 spend), ordered by
    # highest tier reached desc, tiebreaking by first touch. Falls back
    # to the legacy "first to touch" behavior for low-AP builds.
    unmaxed = [aid for aid in highest_tier if aid not in max_position]
    unmaxed.sort(key=lambda aid: (-highest_tier[aid], first_touch[aid]))
    ordered.extend(unmaxed)

    return tuple(ordered[:FINGERPRINT_K])


def _full_ladder(changes: list[dict]) -> list[int]:
    """Compact ability-id ladder: unlocks (currency_type=2) in order,
    followed by upgrade points (currency_type=1). Used to compute the
    cluster's modal full ladder via longest-common-prefix.
    """
    unlocks = [c["ability_id"] for c in changes if c.get("currency_type") == 2]
    upgrades = [c["ability_id"] for c in changes if c.get("currency_type") == 1]
    return unlocks + upgrades


def _ladder_consensus(ladders: list[list[int]]) -> list[int]:
    """Return the longest sequence such that every ladder agrees on its prefix.

    If two builds diverge at step k, the consensus ends at step k-1.
    Returns the per-step modal ability when there's no full consensus,
    capped at the first divergence depth + 4 (so the result is informative
    even for clusters with one stubborn outlier).
    """
    if not ladders:
        return []
    max_len = min(len(l) for l in ladders)
    consensus: list[int] = []
    for i in range(max_len):
        col = Counter(l[i] for l in ladders)
        modal, count = col.most_common(1)[0]
        consensus.append(modal)
        if count < len(ladders):
            # Stop extending if the cluster diverges; we've recorded
            # the modal pick for context.
            break
    return consensus


def _is_upgrade(it: dict) -> bool:
    return it.get("type") == "upgrade" and it.get("item_slot_type") in (
        "weapon", "vitality", "spirit",
    )


def cluster_builds_by_ability(
    build_stats_raw: list,
    build_files_dir: Path,
    build_match_floor: int,
) -> dict[tuple[int, ...], dict]:
    """Cluster qualifying builds by ability-order fingerprint.

    Returns:
      {cluster_key: {builds: [build_summary], total_matches, total_wins,
                     ladders: [full_ladder]}}
      where build_summary = {build_id, matches, wins, name, items, ladder}.
      Clusters with fewer than MIN_BUILDS_PER_CLUSTER builds are dropped.
    """
    stats_by_id = {b["hero_build_id"]: b for b in build_stats_raw}
    qualifying = [b for b in build_stats_raw if b.get("matches", 0) >= build_match_floor]
    clusters: dict[tuple[int, ...], dict] = {}

    for b in qualifying:
        bid = b["hero_build_id"]
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
        hb = d[0].get("hero_build")
        if not hb or "details" not in hb:
            continue
        changes = hb["details"].get("ability_order", {}).get("currency_changes", [])
        if not changes:
            continue

        key = _cluster_key(changes)
        if not key:
            continue
        ladder = _full_ladder(changes)
        items_in_build: set[int] = set()
        for cat in hb["details"].get("mod_categories", []):
            for mod in cat.get("mods", []):
                iid = mod.get("ability_id")
                if iid:
                    items_in_build.add(iid)

        st = stats_by_id.get(bid, {})
        wr = (st["wins"] / st["matches"]) if st.get("matches") else 0.0
        summary = {
            "build_id": bid,
            "name": hb.get("name", "?"),
            "matches": st.get("matches", 0),
            "wins": st.get("wins", 0),
            "win_rate": round(wr, 4),
            "items": list(items_in_build),
            "ladder": ladder,
        }
        cluster = clusters.setdefault(key, {
            "builds": [], "total_matches": 0, "total_wins": 0, "ladders": [],
        })
        cluster["builds"].append(summary)
        cluster["total_matches"] += st.get("matches", 0)
        cluster["total_wins"] += st.get("wins", 0)
        cluster["ladders"].append(ladder)

    return {k: c for k, c in clusters.items()
            if len(c["builds"]) >= MIN_BUILDS_PER_CLUSTER}


def aggregate_cluster_items(
    cluster: dict,
    candidates: dict,
    baseline_wr: float,
) -> list[dict]:
    """Roll up items across builds in one cluster, weighted by lift × matches.

    Mirrors method_build_replication's weighting:
      weight(build) = matches × max(0, wr − baseline + 0.02)

    Returns picks sorted by weighted count, with the same dict schema as
    the existing build_replication output (compatible with downstream
    decoration and page rendering).
    """
    item_weight: Counter = Counter()
    for b in cluster["builds"]:
        weight = b["matches"] * max(0, b["win_rate"] - baseline_wr + 0.02)
        for iid in b["items"]:
            item_weight[iid] += weight

    ranked: list[dict] = []
    for iid, w in item_weight.items():
        if iid in candidates:
            ranked.append({**candidates[iid], "joint_freq_weight": round(w, 1)})
    ranked.sort(key=lambda x: -x["joint_freq_weight"])

    by_cat: dict[str, list] = defaultdict(list)
    for c in ranked:
        by_cat[c["category"]].append(c)
    picks, used = [], set()
    for cat in ("weapon", "vitality", "spirit"):
        for c in by_cat[cat][:4]:
            picks.append({**c, "slot": cat})
            used.add(c["item_id"])
    flex_pool = [c for c in ranked if c["item_id"] not in used][:4]
    for c in flex_pool:
        picks.append({**c, "slot": "flex"})
    return picks


def archetypes_for_slice(
    candidates: dict,
    build_stats_raw: list,
    baseline_wr: float,
    build_files_dir: Path,
    build_match_floor: int,
    ability_id_to_name: dict,
) -> list[dict]:
    """Top-level entry: return a list of joint archetypes for one MMR slice.

    Sorted by total matches (= popularity within the slice). Each entry
    is self-contained — items + ability ladder + provenance — so the page
    can render an archetype card directly from the dict.
    """
    clusters = cluster_builds_by_ability(
        build_stats_raw, build_files_dir, build_match_floor,
    )
    if not clusters:
        return []
    archetypes: list[dict] = []
    for i, (key, cluster) in enumerate(
        sorted(clusters.items(), key=lambda kv: -kv[1]["total_matches"])
    ):
        consensus = _ladder_consensus(cluster["ladders"])
        # Modal full ladder, padded to length 16 by per-position mode
        max_len = max(len(l) for l in cluster["ladders"])
        modal_ladder = []
        for pos in range(max_len):
            col = Counter(l[pos] for l in cluster["ladders"] if len(l) > pos)
            modal_ladder.append(col.most_common(1)[0][0])
        wr = (cluster["total_wins"] / cluster["total_matches"]
              if cluster["total_matches"] else 0.0)
        archetypes.append({
            "archetype_id": i + 1,
            "fingerprint_ability_ids": list(key),
            "fingerprint_ability_names": [
                ability_id_to_name.get(aid, "?") for aid in key
            ],
            "n_builds": len(cluster["builds"]),
            "total_matches": cluster["total_matches"],
            "total_wins": cluster["total_wins"],
            "mean_win_rate": round(wr, 4),
            "win_rate_lift_pp": round((wr - baseline_wr) * 100, 2),
            "consensus_ladder_ids": consensus,
            "consensus_ladder_names": [
                ability_id_to_name.get(aid, "?") for aid in consensus
            ],
            "modal_full_ladder_ids": modal_ladder,
            "modal_full_ladder_names": [
                ability_id_to_name.get(aid, "?") for aid in modal_ladder
            ],
            "items": aggregate_cluster_items(cluster, candidates, baseline_wr),
            "source_builds": [
                {"build_id": b["build_id"], "name": b["name"],
                 "win_rate": b["win_rate"], "matches": b["matches"]}
                for b in cluster["builds"]
            ],
        })
    return archetypes
