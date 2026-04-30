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


def cluster_archetypes_for_hero(hid: int, max_clusters: int = 3) -> dict:
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
                        "wr": p["win_rate"],
                        "image": items_assets.get(p["item_id"], {}).get("image"),
                        "item_id": p["item_id"],
                        "tag": p.get("tag", "stat"),
                        "pick_rate": p.get("pick_rate", 0.0),
                        "annotation": p.get("annotation", ""),
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
                "wr": p["win_rate"], "phase": p["phase"],
                "image": items_assets.get(p["item_id"], {}).get("image"),
                "item_id": p["item_id"],
                "tag": p.get("tag", "stat"),
                "pick_rate": p.get("pick_rate", 0.0),
                "annotation": p.get("annotation", ""),
            }) for p in d["items"][src]["synergy_ilp"]["picks"]]
            for slice_label, src in (("all", "all_mmr"), ("high", "high_mmr"))
        },
        "archetypes": archetypes or {"clusters": [], "total_builds": 0},
    }
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
    archetypes_by_hero: dict[int, dict] = {}
    for d in raw_outputs:
        hid = d["hero"]["id"]
        archetypes_by_hero[hid] = cluster_archetypes_for_hero(hid)
    n_clusters = sum(len(v["clusters"]) for v in archetypes_by_hero.values())
    print(f"  {n_clusters} clusters across {len(archetypes_by_hero)} heroes")

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
