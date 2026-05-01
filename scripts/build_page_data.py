"""
Compile all 38 hero output files + asset metadata into one compact JS object
for the static HTML page. Output is roughly 250–400 KB embedded inline.

Adds two cross-cutting enrichments at this stage:
  - hero affinity scores per pick (a "signature" item is one this hero uses
    much more than the average hero)
  - archetype clusters per hero (community top builds grouped into 1–3
    playstyles via Jaccard-distance hierarchical clustering)
"""
import json
import re
from collections import defaultdict, Counter
from pathlib import Path
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import (
    ROOT, CACHE, HERO_OUT, HERO_DATA, BUILD_FILES, ASSETS,
    PATCH_ID, PATCH_TITLE, PATCH_MIN_TS, HMMR_BADGE, SPEC_VERSION,
)



def slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()


# Asset look-ups
heroes_assets = {h["id"]: h for h in json.load(open(CACHE / "heroes.json"))}
items_assets = {i["id"]: i for i in json.load(open(CACHE / "items.json"))}

# Build per-item lookup with name + tier + cost + category + image
def item_info(iid: int) -> dict:
    it = items_assets.get(iid, {})
    return {
        "name": it.get("name", "?"),
        "tier": it.get("item_tier"),
        "cost": it.get("cost"),
        "category": it.get("item_slot_type"),
        "image": it.get("image"),
    }


# ============================================================
# Cross-hero affinity: which items does THIS hero use more often than the
# average hero? Affinity = hero_pick_rate / cross_hero_avg_pick_rate
# ============================================================
def compute_cross_hero_baselines(hero_outputs: list[dict]) -> dict:
    """For each item id, compute the average pick rate across all heroes.
    Heroes that have zero builds containing the item count as 0.
    """
    n_heroes = len(hero_outputs)
    item_picks: dict[int, dict[int, float]] = defaultdict(dict)  # iid -> {hero_id: rate}
    for d in hero_outputs:
        hero_id = d["hero"]["id"]
        # Use high-MMR slice as the canonical signal
        meta = d.get("items", {}).get("high_mmr", {}).get("item_metadata", {})
        for iid_key, m in meta.items():
            iid = int(iid_key)
            item_picks[iid][hero_id] = m.get("pick_rate", 0.0)

    baselines: dict[int, dict] = {}
    for iid, picks in item_picks.items():
        total_rate = sum(picks.values())
        avg = total_rate / n_heroes  # implicit zero for heroes without it
        baselines[iid] = {
            "avg_pick_rate": avg,
            "hero_pick_rates": picks,
            "heroes_using": len(picks),
        }
    return baselines


def affinity_for(item_id: int, hero_id: int, baselines: dict) -> float | None:
    base = baselines.get(item_id)
    if not base or base["avg_pick_rate"] <= 0:
        return None
    hero_rate = base["hero_pick_rates"].get(hero_id, 0.0)
    return hero_rate / base["avg_pick_rate"]


# ============================================================
# Archetype clustering: group cached community builds for one hero into
# 1–3 playstyles. Distance metric = 1 - Jaccard similarity on item sets.
# ============================================================
def _jaccard_distance(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return 1.0 - (inter / union) if union else 1.0


def _agglomerative(builds: list, k: int) -> list[list[int]]:
    """Return k clusters as lists of build indices."""
    n = len(builds)
    clusters = [[i] for i in range(n)]
    if n <= k:
        return clusters
    item_sets = [b["items"] for b in builds]
    while len(clusters) > k:
        best = (1e9, 0, 0)
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                # Average linkage: mean pairwise distance
                ds = [_jaccard_distance(item_sets[a], item_sets[b])
                      for a in clusters[i] for b in clusters[j]]
                d = sum(ds) / max(1, len(ds))
                if d < best[0]:
                    best = (d, i, j)
        _, i, j = best
        clusters[i] = clusters[i] + clusters[j]
        clusters.pop(j)
    return clusters


def _label_cluster(builds_in_cluster: list, builds_in_other_clusters: list) -> dict:
    """Auto-label a cluster from its dominant items / category mix.
    Returns: {label, dominant_category, signature_items, sample_count}.
    """
    # Pick rate within this cluster vs other clusters
    n_in = len(builds_in_cluster)
    n_out = len(builds_in_other_clusters)
    in_pick = Counter()
    for b in builds_in_cluster:
        for iid in b["items"]:
            in_pick[iid] += 1
    out_pick = Counter()
    for b in builds_in_other_clusters:
        for iid in b["items"]:
            out_pick[iid] += 1

    # Differentiating items: high in this cluster, low in others
    diff = []
    for iid, c in in_pick.items():
        in_rate = c / n_in
        out_rate = (out_pick[iid] / n_out) if n_out else 0
        if in_rate < 0.5:
            continue
        diff.append((iid, in_rate, out_rate, in_rate - out_rate))
    diff.sort(key=lambda x: -x[3])

    # Category mix across the items in this cluster
    cat_count = Counter()
    for b in builds_in_cluster:
        for iid in b["items"]:
            it = items_assets.get(iid, {})
            cat = it.get("item_slot_type")
            if cat in ("weapon", "vitality", "spirit"):
                cat_count[cat] += 1
    total = sum(cat_count.values()) or 1
    mix = {cat: cat_count.get(cat, 0) / total for cat in ("weapon", "vitality", "spirit")}
    dominant = max(mix.items(), key=lambda kv: kv[1])

    # Heuristic label. Item-count-based "Spirit-leaning" labels are weak
    # because counting items doesn't capture playstyle (a spirit nuker
    # often has more vitality slots than spirit slots). Prefer leading with
    # the most differentiating item, then optionally append a category hint
    # only when truly dominant.
    if diff and diff[0][3] >= 0.4:
        # Strong differentiator: an item picked at least 40 percentage points
        # more in this cluster than other clusters.
        top_name = items_assets.get(diff[0][0], {}).get("name", "?")
        if dominant[1] >= 0.55:
            label = f"{dominant[0].title()}-build · {top_name} core"
        else:
            label = f"{top_name} build"
    elif dominant[1] >= 0.55:
        label = f"{dominant[0].title()}-focused"
    elif diff:
        top_name = items_assets.get(diff[0][0], {}).get("name", "?")
        label = f"{top_name} build"
    else:
        label = "Mainstream build"

    return {
        "label": label,
        "dominant_category": dominant[0],
        "category_mix": {k: round(v, 3) for k, v in mix.items()},
        "signature_items": [
            {"item_id": iid, "name": items_assets.get(iid, {}).get("name", "?"),
             "in_cluster_rate": round(ir, 3), "outside_rate": round(orr, 3)}
            for iid, ir, orr, _ in diff[:5]
        ],
        "build_count": n_in,
        "avg_wr": round(sum(b["wr"] for b in builds_in_cluster) / n_in, 4) if n_in else None,
    }


def _phase_for(buy_time_s: float) -> str:
    if buy_time_s < 750:
        return "early"
    if buy_time_s < 1500:
        return "mid"
    return "late"


def _aggregate_cluster_build(in_builds: list[dict], hero_item_stats: list[dict],
                             lineage_canon: dict, ancestors_of: dict,
                             metadata_by_item: dict | None = None) -> list[dict]:
    """For one archetype cluster, build a 16-slot composite by aggregating
    item picks across the cluster's builds. Returns picks shaped like
    items_by_slice entries so the page can render them with the same code path.
    """
    n_builds = len(in_builds)
    if n_builds == 0:
        return []

    counts: dict[int, int] = {}
    for b in in_builds:
        for iid in b["items"]:
            counts[iid] = counts.get(iid, 0) + 1

    stats_by_id = {s["item_id"]: s for s in hero_item_stats}
    candidates = []
    for iid, count in counts.items():
        it = items_assets.get(iid, {})
        if not (it.get("type") == "upgrade"
                and it.get("item_slot_type") in ("weapon", "vitality", "spirit")):
            continue
        s = stats_by_id.get(iid)
        if s and s.get("matches"):
            buy_min = round(s["avg_buy_time_s"] / 60, 1)
            wr = s["wins"] / s["matches"]
            phase = _phase_for(s["avg_buy_time_s"])
            sell_s = s.get("avg_sell_time_s") or 0
            sell_min = round(sell_s / 60, 1) if sell_s else None
        else:
            buy_min = 30.0  # fallback when item isn't in this hero's stats slice
            wr = 0.0
            phase = "late"
            sell_min = None
        meta = (metadata_by_item or {}).get(iid, {})
        candidates.append({
            "item_id": iid,
            "name": it.get("name", "?"),
            "category": it.get("item_slot_type"),
            "tier": it.get("item_tier"),
            "cost": it.get("cost", 0),
            "buy_min": buy_min,
            "sell_min": sell_min,
            "wr": round(wr, 4),
            "phase": phase,
            "image": it.get("image"),
            "cluster_pick_rate": round(count / n_builds, 3),
            "tag": meta.get("tag", "stat"),
            "pick_rate": meta.get("pick_rate", 0.0),
            "annotation": meta.get("annotation", ""),
        })

    # Lineage dedupe — keep highest cluster pick rate per lineage
    by_lineage: dict[int, dict] = {}
    for c in candidates:
        canon = lineage_canon.get(c["item_id"], c["item_id"])
        existing = by_lineage.get(canon)
        if (existing is None
                or c["cluster_pick_rate"] > existing["cluster_pick_rate"]
                or (c["cluster_pick_rate"] == existing["cluster_pick_rate"] and c["tier"] > existing["tier"])):
            by_lineage[canon] = c
    candidates = list(by_lineage.values())

    # 4 per category (by cluster pick rate), then 4 flex from remaining
    by_cat: dict[str, list] = {"weapon": [], "vitality": [], "spirit": []}
    for c in candidates:
        if c["category"] in by_cat:
            by_cat[c["category"]].append(c)
    for cat in by_cat:
        by_cat[cat].sort(key=lambda x: -x["cluster_pick_rate"])

    picks, used = [], set()
    for cat in ("weapon", "vitality", "spirit"):
        for c in by_cat[cat][:4]:
            picks.append({**c, "slot": cat})
            used.add(c["item_id"])
    flex_pool = sorted(
        [c for c in candidates if c["item_id"] not in used],
        key=lambda x: -x["cluster_pick_rate"],
    )[:4]
    for c in flex_pool:
        picks.append({**c, "slot": "flex"})

    # Decorate with lineage chains (same shape as the recommended build)
    for p in picks:
        ancs = ancestors_of.get(p["item_id"], set())
        chain = []
        for anc_id in ancs:
            it = items_assets.get(anc_id)
            if not it:
                continue
            anc_stat = stats_by_id.get(anc_id)
            chain.append({
                "item_id": anc_id,
                "name": it.get("name"),
                "tier": it.get("item_tier"),
                "cost": it.get("cost"),
                "matches": anc_stat["matches"] if anc_stat else None,
                "avg_buy_time_min": (round(anc_stat["avg_buy_time_s"] / 60, 1)
                                     if anc_stat else None),
            })
        chain.sort(key=lambda c: (c["tier"] or 0, c["cost"] or 0))
        if chain:
            p["lineage_chain"] = chain

    return picks


def cluster_archetypes_for_hero(hid: int, max_clusters: int = 3,
                                hero_item_stats: list | None = None,
                                lineage_canon: dict | None = None,
                                ancestors_of: dict | None = None,
                                metadata_by_item: dict | None = None) -> dict:
    """Pull the cached community builds for a hero, cluster them, return labelled archetypes."""
    # Stitch together both slices' build lists; dedupe by build_id
    seen_ids: set[int] = set()
    builds: list[dict] = []
    for slice_label in ("all", "hmmr"):
        f = HERO_DATA / f"buildstats_{slice_label}_{hid}.json"
        if not f.exists():
            continue
        for st in json.load(open(f)):
            bid = st["hero_build_id"]
            if bid in seen_ids:
                continue
            if st["matches"] < 50:
                continue
            bf = BUILD_FILES / f"build_{bid}.json"
            if not bf.exists():
                continue
            try:
                d = json.load(open(bf))
            except Exception:
                continue
            if not (isinstance(d, list) and d):
                continue
            b = d[0].get("hero_build")
            if not b or "details" not in b:
                continue
            items: set[int] = set()
            for cat in b["details"].get("mod_categories", []):
                for mod in cat.get("mods", []):
                    iid = mod.get("ability_id")
                    if iid:
                        items.add(iid)
            if not items:
                continue
            seen_ids.add(bid)
            builds.append({
                "id": bid,
                "name": b.get("name", "?"),
                "wr": st["wins"] / st["matches"],
                "matches": st["matches"],
                "items": items,
            })

    if not builds:
        return {"clusters": [], "total_builds": 0}

    # Decide k: more builds → more clusters, but capped at max_clusters
    if len(builds) <= 2:
        k = 1
    elif len(builds) <= 5:
        k = 2
    else:
        k = min(max_clusters, max(2, len(builds) // 4))

    clusters = _agglomerative(builds, k)
    out = []
    for cluster_indices in clusters:
        in_builds = [builds[i] for i in cluster_indices]
        out_builds = [builds[i] for i in range(len(builds)) if i not in cluster_indices]
        meta = _label_cluster(in_builds, out_builds)
        meta["share"] = round(len(in_builds) / len(builds), 3)
        meta["sample_build_names"] = [b["name"] for b in sorted(in_builds, key=lambda x: -x["wr"])[:3]]
        # Aggregate a 16-slot composite build for this cluster, if we have
        # the stats / lineage maps to decorate it with buy times etc.
        if hero_item_stats is not None and lineage_canon is not None and ancestors_of is not None:
            meta["build"] = _aggregate_cluster_build(
                in_builds, hero_item_stats, lineage_canon, ancestors_of, metadata_by_item
            )
        out.append(meta)

    out.sort(key=lambda c: -c["share"])
    return {"clusters": out, "total_builds": len(builds)}


def hero_image(hid: int) -> str | None:
    h = heroes_assets.get(hid, {})
    imgs = h.get("images", {})
    return imgs.get("icon_hero_card_webp") or imgs.get("icon_hero_card") or imgs.get("icon_image_small_webp")


def compact_hero(d: dict, baselines: dict | None = None, archetypes: dict | None = None) -> dict:
    """Take a full hero output and pull just what the page needs."""
    hid = d["hero"]["id"]
    name = d["hero"]["name"]
    h = heroes_assets.get(hid, {})

    def with_affinity(item: dict) -> dict:
        """Attach affinity to one item entry (mutates a copy)."""
        if not baselines:
            return item
        score = affinity_for(item["item_id"], hid, baselines)
        if score is not None:
            item = {**item, "affinity": round(score, 2)}
            # "Signature" if this hero uses the item ≥2× the average AND the
            # hero's own pick rate is non-trivial.
            pr = item.get("pick_rate", 0.0)
            if score >= 2.0 and pr >= 0.30:
                item["signature"] = True
        return item

    out = {
        "id": hid,
        "name": name,
        "image": hero_image(hid),
        "abilities": [
            {"id": a["id"], "name": a["name"],
             "image": items_assets.get(a["id"], {}).get("image")}
            for a in d["hero"]["abilities"]
        ],
        "mmr": {
            "all": {"wr": d["mmr_slices"]["all_mmr"]["baseline_win_rate"],
                    "matches": d["mmr_slices"]["all_mmr"]["matches"],
                    "players": d["mmr_slices"]["all_mmr"]["players"]},
            "high": {"wr": d["mmr_slices"]["high_mmr"]["baseline_win_rate"],
                     "matches": d["mmr_slices"]["high_mmr"]["matches"],
                     "players": d["mmr_slices"]["high_mmr"]["players"]},
        },
        "recommended": {
            "items": {
                "method": d["recommended"]["items"]["method"],
                "mmr_slice": d["recommended"]["items"]["mmr_slice"],
                "total_cost": d["recommended"]["items"]["total_cost"],
                "phases": {
                    ph: [with_affinity({
                        "slot": p["slot"],
                        "name": p["name"],
                        "category": p["category"],
                        "tier": p["tier"],
                        "cost": p["cost"],
                        "buy_min": p["avg_buy_time_min"],
                        "sell_min": p.get("avg_sell_time_min"),
                        "wr": p["win_rate"],
                        "image": items_assets.get(p["item_id"], {}).get("image"),
                        "item_id": p["item_id"],
                        "tag": p.get("tag", "stat"),
                        "pick_rate": p.get("pick_rate", 0.0),
                        "annotation": p.get("annotation", ""),
                        "lineage_chain": p.get("lineage_chain", []),
                    }) for p in d["recommended"]["items"]["phases"][ph]]
                    for ph in ("early", "mid", "late")
                },
            },
            "abilities": d["recommended"]["abilities"],
        },
        # Per-MMR-slice ability breakdown so the page can offer a toggle
        "ability_orders": {
            slice_label: {
                "priority": d["ability_orders"][src]["ability_priority"],
                "best_full": d["ability_orders"][src]["best_full_orders"][0]
                    if d["ability_orders"][src]["best_full_orders"] else None,
                "best_opener": d["ability_orders"][src]["best_openers_first4"][0]
                    if d["ability_orders"][src]["best_openers_first4"] else None,
                "alternate_openers": d["ability_orders"][src]["best_openers_first4"][1:4],
                "alternate_fulls": d["ability_orders"][src]["best_full_orders"][1:4],
            }
            for slice_label, src in (("all", "all_mmr"), ("high", "high_mmr"))
        },
        # Per-MMR-slice item breakdown using the synergy ILP picks (the recommended method)
        "items_by_slice": {
            slice_label: [with_affinity({
                "slot": p["slot"], "name": p["name"], "category": p["category"],
                "tier": p["tier"], "cost": p["cost"],
                "buy_min": round(p["avg_buy_time_s"] / 60, 1),
                "sell_min": (round(p["avg_sell_time_s"] / 60, 1)
                             if p.get("avg_sell_time_s") else None),
                "wr": p["win_rate"], "phase": p["phase"],
                "image": items_assets.get(p["item_id"], {}).get("image"),
                "item_id": p["item_id"],
                "tag": p.get("tag", "stat"),
                "pick_rate": p.get("pick_rate", 0.0),
                "annotation": p.get("annotation", ""),
                "lineage_chain": p.get("lineage_chain", []),
            }) for p in d["items"][src]["synergy_ilp"]["picks"]]
            for slice_label, src in (("all", "all_mmr"), ("high", "high_mmr"))
        },
        "archetypes": archetypes or {"clusters": [], "total_builds": 0},
    }

    # Decorate each cluster's composite build with affinity/signature using
    # the same logic as the main picks, so clicking an archetype produces
    # a fully-featured build view.
    for c in out["archetypes"].get("clusters", []):
        if c.get("build"):
            c["build"] = [with_affinity(p) for p in c["build"]]

    return out


def main() -> None:
    # Pass 1: load all hero outputs (we'll need them twice — for cross-hero
    # baselines and for compaction).
    raw_outputs = []
    for f in sorted(HERO_OUT.glob("*_build.json")):
        raw_outputs.append(json.load(open(f)))
    print(f"Loaded {len(raw_outputs)} hero output files")

    print("Computing cross-hero pick-rate baselines …")
    baselines = compute_cross_hero_baselines(raw_outputs)
    print(f"  {len(baselines)} items have at least one hero with non-zero pick rate")

    print("Clustering archetypes per hero …")
    # Build the global lineage map once (shared across all heroes).
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from build_hero_output import build_lineage_map  # noqa: E402
    ancestors_of, lineage_canon = build_lineage_map(items_assets)

    archetypes_by_hero: dict[int, dict] = {}
    for d in raw_outputs:
        hid = d["hero"]["id"]
        # Pull this hero's high-MMR item stats so we can decorate cluster
        # builds with realistic buy times + win rates.
        stats_path = HERO_DATA / f"itemstats_hmmr_{hid}.json"
        try:
            hero_stats = json.load(open(stats_path)) if stats_path.exists() else []
        except Exception:
            hero_stats = []
        meta_high = d.get("items", {}).get("high_mmr", {}).get("item_metadata", {})
        # The metadata dict is keyed by string ids (JSON quirk); normalize to int
        meta_by_int: dict[int, dict] = {}
        for k, v in meta_high.items():
            try:
                meta_by_int[int(k)] = v
            except (ValueError, TypeError):
                pass
        archetypes_by_hero[hid] = cluster_archetypes_for_hero(
            hid,
            hero_item_stats=hero_stats,
            lineage_canon=lineage_canon,
            ancestors_of=ancestors_of,
            metadata_by_item=meta_by_int,
        )
    n_clusters = sum(len(v["clusters"]) for v in archetypes_by_hero.values())
    n_with_builds = sum(1 for v in archetypes_by_hero.values()
                        for c in v["clusters"] if c.get("build"))
    print(f"  {n_clusters} clusters across {len(archetypes_by_hero)} heroes "
          f"({n_with_builds} with composite builds)")

    print("Compacting per-hero data …")
    heroes_data = []
    n_signature = 0
    for d in raw_outputs:
        hid = d["hero"]["id"]
        ch = compact_hero(d, baselines=baselines, archetypes=archetypes_by_hero.get(hid))
        # Count signature picks for visibility
        for ph in ("early", "mid", "late"):
            for p in ch["recommended"]["items"]["phases"][ph]:
                if p.get("signature"):
                    n_signature += 1
        heroes_data.append(ch)
    print(f"  signature picks across all 38 recommended builds: {n_signature}")

    # Sort alphabetically by name for stable display, but the page can re-sort
    heroes_data.sort(key=lambda h: h["name"])

    # Compute meta-level data: tier list (by high-MMR WR)
    tier = sorted(heroes_data, key=lambda h: -h["mmr"]["high"]["wr"])

    page_data = {
        "spec_version": "1.0.0",
        "patch": {"id": "patch_125825", "title": "04-10-2026 Update"},
        "data_source": "api.deadlock-api.com",
        "heroes": heroes_data,
        "tier_order_ids": [h["id"] for h in tier],
    }

    target = CACHE / "page_data.json"
    with open(target, "w") as f:
        json.dump(page_data, f, separators=(",", ":"))
    size = target.stat().st_size
    print(f"[saved] {target}  {size:,} bytes  ({size/1024:.1f} KB)")
    print(f"  {len(heroes_data)} heroes")


if __name__ == "__main__":
    main()
