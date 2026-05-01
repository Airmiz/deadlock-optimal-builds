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


# Asset look-ups (LEGACY/global — patch-aware code below loads per-patch
# snapshots from cache/<patch_id>/ when available, falling back to these).
heroes_assets = {h["id"]: h for h in json.load(open(CACHE / "heroes.json"))}
items_assets = {i["id"]: i for i in json.load(open(CACHE / "items.json"))}


def load_patch_assets(patch_id: str) -> tuple[dict, dict]:
    """Load per-patch snapshots of heroes.json + items.json. Falls back to
    the global cache/ versions if the patch-specific snapshot doesn't exist
    (legacy patches fetched before snapshotting was added)."""
    patch_dir = CACHE / patch_id
    h_path = patch_dir / "heroes.json"
    i_path = patch_dir / "items.json"
    h_global = CACHE / "heroes.json"
    i_global = CACHE / "items.json"

    heroes_src = h_path if h_path.exists() else h_global
    items_src  = i_path if i_path.exists() else i_global

    h = {x["id"]: x for x in json.load(open(heroes_src))}
    i = {x["id"]: x for x in json.load(open(items_src))}
    return h, i

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
# Per-patch item overrides
# ----------------------------------------------------------------------------
# When a Deadlock patch ships, the live asset CDN at assets.deadlock-api.com
# can take several days to catch up — meanwhile, items like Shadow Weave can
# show with their PRE-patch tier/cost/cooldown values in our cache. To keep
# the page accurate as soon as the patch drops, we maintain a small
# per-patch override map keyed by item_id. Each entry is sourced from the
# patch notes; remove it once the asset CDN refreshes and a fresh
# batch_fetch picks up the new values.
# ============================================================
ITEM_OVERRIDES_BY_PATCH: dict[str, dict[int, dict]] = {
    "patch_129989": {
        # 1798666702 Shadow Weave: T4 → T3, cooldown 32s → 45s
        1798666702: {"tier": 3, "cost": 3200, "cooldown_s": 45},
        # 3074274290 Trophy Collector: T3 → T2
        3074274290: {"tier": 2, "cost": 1600},
        # 1644605047 Reactive Barrier: cooldown 40s → 55s
        1644605047: {"cooldown_s": 55},
        # 2108215830 Heroic Aura: cooldown 25s → 22s
        2108215830: {"cooldown_s": 22},
        # 1414025773 Counterspell: cooldown 20s → 23s
        1414025773: {"cooldown_s": 23},
        # 3647584222 Split Shot: cooldown 24s → 27s
        3647584222: {"cooldown_s": 27},
    },
}


def apply_item_override(pick: dict, patch_id: str) -> dict:
    """Apply patch-specific item attribute overrides on top of a pick. Mutates a copy."""
    overrides = ITEM_OVERRIDES_BY_PATCH.get(patch_id, {}).get(pick.get("item_id"))
    if not overrides:
        return pick
    return {**pick, **overrides}


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
        # Cooldown lookup straight from the item asset
        cd_s = None
        props = it.get("properties") or {}
        raw_cd = props.get("AbilityCooldown")
        if raw_cd is not None:
            v = raw_cd.get("value") if isinstance(raw_cd, dict) else raw_cd
            try:
                f = float(v)
                if f > 0:
                    cd_s = f
            except (TypeError, ValueError):
                pass
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
            "is_active": bool(it.get("is_active_item")),
            "cooldown_s": cd_s,
            "imbue": it.get("imbue"),
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


def _optimize_cluster_build(in_builds: list[dict], hero_item_stats: list,
                            pair_stats: list, baseline_wr: float,
                            lineage_canon: dict, ancestors_of: dict,
                            metadata_by_item: dict | None) -> list[dict]:
    """
    Per-archetype synergy ILP. Restricts the candidate pool to items that
    appear in this cluster's community builds, then runs the same Wilson-LB
    + pairwise-synergy optimization the global recommended build uses.
    The result is a stat-optimized 16-slot build that's *coherent* with the
    archetype's playstyle, rather than the cluster's popularity aggregate.
    """
    # Lazy import to avoid circular deps
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from build_hero_output import build_candidates, method_synergy_ilp  # noqa

    n_builds = len(in_builds)
    if n_builds == 0:
        return []

    cluster_picks: dict[int, int] = {}
    for b in in_builds:
        for iid in b["items"]:
            cluster_picks[iid] = cluster_picks.get(iid, 0) + 1

    # Items used in ≥30% of the cluster's builds form the archetype's vocabulary.
    # If this is too restrictive (<20 candidates after filtering), relax to 15%.
    threshold = 0.30
    cluster_item_ids = {iid for iid, c in cluster_picks.items()
                        if c / n_builds >= threshold}

    # Build the standard candidate pool (Wilson scored, lineage-deduped) for
    # this hero, then intersect with the archetype's vocabulary.
    all_candidates = build_candidates(
        hero_item_stats, items_assets, baseline_wr,
        min_matches=300, lineage_canon=lineage_canon,
    )

    cluster_cands = {iid: c for iid, c in all_candidates.items()
                     if iid in cluster_item_ids}

    # Need ≥16 candidates plus enough per category for the slot constraints.
    # If we don't have enough, relax the threshold step-wise.
    def category_counts(cands):
        out = {"weapon": 0, "vitality": 0, "spirit": 0}
        for c in cands.values():
            if c["category"] in out:
                out[c["category"]] += 1
        return out

    relaxations = [0.30, 0.20, 0.15, 0.10]
    for thr in relaxations:
        cluster_item_ids = {iid for iid, c in cluster_picks.items()
                            if c / n_builds >= thr}
        cluster_cands = {iid: c for iid, c in all_candidates.items()
                         if iid in cluster_item_ids}
        cc = category_counts(cluster_cands)
        # Need at least 4 per main category to satisfy the slot constraint.
        if (len(cluster_cands) >= 16 and
                cc["weapon"] >= 4 and cc["vitality"] >= 4 and cc["spirit"] >= 4):
            break
    else:
        # Couldn't get enough candidates even after relaxation — bail.
        return []

    # Run the synergy ILP on the cluster-restricted pool.
    try:
        picks = method_synergy_ilp(cluster_cands, pair_stats, pair_min_matches=200)
    except Exception:
        return []

    # Annotate each pick with the same fields the cluster's frequency build has,
    # plus tag/pick_rate/annotation/cooldown/imbue from the metadata layer.
    stats_by_id = {s["item_id"]: s for s in hero_item_stats}
    for p in picks:
        # Cluster pick rate (how popular it is within this archetype)
        p["cluster_pick_rate"] = round(cluster_picks.get(p["item_id"], 0) / n_builds, 3)
        # Annotation / tag from cross-build metadata
        meta = (metadata_by_item or {}).get(p["item_id"], {})
        p["tag"] = meta.get("tag", "stat")
        p["pick_rate"] = meta.get("pick_rate", 0.0)
        if meta.get("annotation"):
            p["annotation"] = meta["annotation"]
        # Re-attach phase, sell_min, image, etc. from item-stats / asset
        s = stats_by_id.get(p["item_id"])
        if s and s.get("matches"):
            p["buy_min"] = round(s["avg_buy_time_s"] / 60, 1)
            sell_s = s.get("avg_sell_time_s") or 0
            p["sell_min"] = round(sell_s / 60, 1) if sell_s else None
            p["wr"] = round(s["wins"] / s["matches"], 4)
        else:
            p["buy_min"] = 30.0
            p["sell_min"] = None
            p["wr"] = 0.0
        # Active / cooldown / imbue
        it = items_assets.get(p["item_id"], {})
        p["image"] = it.get("image")
        p["is_active"] = bool(it.get("is_active_item"))
        p["imbue"] = it.get("imbue")
        # Cooldown lookup
        props = it.get("properties") or {}
        raw_cd = props.get("AbilityCooldown")
        cd_s = None
        if raw_cd is not None:
            v = raw_cd.get("value") if isinstance(raw_cd, dict) else raw_cd
            try:
                f = float(v)
                if f > 0:
                    cd_s = f
            except (TypeError, ValueError):
                pass
        p["cooldown_s"] = cd_s
        # Lineage chain (lower-tier ancestors with buy times)
        ancs = ancestors_of.get(p["item_id"], set())
        chain = []
        for anc_id in ancs:
            ait = items_assets.get(anc_id)
            if not ait:
                continue
            anc_stat = stats_by_id.get(anc_id)
            chain.append({
                "item_id": anc_id,
                "name": ait.get("name"),
                "tier": ait.get("item_tier"),
                "cost": ait.get("cost"),
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
                                pair_stats: list | None = None,
                                baseline_wr: float | None = None,
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


def compact_hero(d: dict, baselines: dict | None = None, archetypes: dict | None = None,
                 patch_id: str = "") -> dict:
    """Take a full hero output and pull just what the page needs."""
    hid = d["hero"]["id"]
    name = d["hero"]["name"]
    h = heroes_assets.get(hid, {})

    def with_affinity(item: dict) -> dict:
        """Attach affinity AND apply any patch-specific item overrides."""
        item = apply_item_override(item, patch_id)
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
                        "is_active": p.get("is_active", False),
                        "cooldown_s": p.get("cooldown_s"),
                        "imbue": p.get("imbue"),
                        "imbue_target_id": p.get("imbue_target_id"),
                        "imbue_target_share": p.get("imbue_target_share"),
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
                "is_active": p.get("is_active", False),
                "cooldown_s": p.get("cooldown_s"),
                "imbue": p.get("imbue"),
                "imbue_target_id": p.get("imbue_target_id"),
                "imbue_target_share": p.get("imbue_target_share"),
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


def compute_counters_for_patch(patch_id: str, top_k: int = 12) -> dict:
    """
    For each (hero, enemy) cached counter file, compute per-item WR delta
    against the no-enemy-filter baseline. Returns:
      { hero_id: { enemy_id: [ {item_id, delta_pp, n_vs, n_base, name, category, tier, cost, image}, ... ] } }
    where each list holds the top-K items by |delta|, mixing buy-this and avoid-this picks.
    """
    counters_dir = CACHE / patch_id / "counters"
    hero_data_dir = CACHE / patch_id / "hero_data"
    if not counters_dir.exists():
        return {}

    # Per-hero baselines (high-MMR slice — counters were fetched at HMMR)
    baselines: dict[int, dict[int, dict]] = {}
    for h in json.load(open(CACHE / "playable_heroes.json")):
        f = hero_data_dir / f"itemstats_hmmr_{h['id']}.json"
        if not f.exists():
            continue
        try:
            d = json.load(open(f))
        except Exception:
            continue
        baselines[h["id"]] = {s["item_id"]: s for s in d}

    out: dict[int, dict[int, list]] = {}
    for cf in counters_dir.glob("*_vs_*.json"):
        try:
            stem = cf.stem  # "19_vs_31"
            hero_id, enemy_id = (int(x) for x in stem.split("_vs_"))
        except ValueError:
            continue
        try:
            stats = json.load(open(cf))
        except Exception:
            continue
        baseline_for_hero = baselines.get(hero_id, {})
        if not baseline_for_hero:
            continue

        deltas = []
        for s in stats:
            iid = s["item_id"]
            base = baseline_for_hero.get(iid)
            if not base:
                continue
            n_vs = s.get("matches", 0)
            n_base = base.get("matches", 0)
            if n_vs < 100 or n_base < 200:
                continue  # need both samples to be meaningful
            it = items_assets.get(iid)
            if not (it and it.get("type") == "upgrade"
                    and it.get("item_slot_type") in ("weapon", "vitality", "spirit")):
                continue
            wr_vs = s["wins"] / n_vs
            wr_base = base["wins"] / n_base
            delta_pp = round((wr_vs - wr_base) * 100, 2)
            if abs(delta_pp) < 0.4:
                continue  # ignore tiny/noise deltas
            # Only keep id-keyed fields; UI looks up name/cat/tier/cost/image
            # from a shared items dict embedded once per patch (saves ~2 MB).
            deltas.append({
                "item_id": iid,
                "delta_pp": delta_pp,
                "n_vs": n_vs,
                "n_base": n_base,
            })
        if not deltas:
            continue
        # Keep top-K by |delta|. Also separately keep top-3 most-positive +
        # top-3 most-negative for guaranteed buy/avoid representation, to avoid
        # one-sided tails dominating when matchup is wholly favorable/unfavorable.
        deltas.sort(key=lambda x: -abs(x["delta_pp"]))
        kept = deltas[:top_k]
        kept.sort(key=lambda x: -x["delta_pp"])
        out.setdefault(hero_id, {})[enemy_id] = kept
    return out


def build_patch_payload(patch_id: str) -> dict | None:
    """Run the full compact pipeline for one patch and return its payload.
    Returns None if the patch has no per-hero outputs on disk.

    Loads per-patch asset snapshots (heroes.json/items.json from
    cache/<patch_id>/) so item attributes that may differ between patches
    (e.g. Shadow Weave at T4 on patch_125825 → T3 on patch_129989) display
    correctly per patch.
    """
    from _paths import PATCH_REGISTRY  # local import to keep the global pure
    hero_out_dir = ROOT / "heroes" / patch_id
    patch_cache_dir = CACHE / patch_id
    files = sorted(hero_out_dir.glob("*_build.json"))
    if not files:
        print(f"  {patch_id}: no hero outputs on disk — skipped")
        return None

    raw_outputs = [json.load(open(f)) for f in files]
    print(f"  {patch_id}: loaded {len(raw_outputs)} hero outputs")

    # Swap module-level asset dicts to this patch's snapshot for the
    # duration of this call. Used by compact_hero, _aggregate_cluster_build,
    # _optimize_cluster_build, compute_counters_for_patch, etc.
    global heroes_assets, items_assets
    saved_h, saved_i = heroes_assets, items_assets
    heroes_assets, items_assets = load_patch_assets(patch_id)
    print(f"  {patch_id}: loaded patch-specific asset snapshot ({len(items_assets)} items)")
    try:
        return _build_patch_payload_inner(patch_id, raw_outputs, hero_out_dir, patch_cache_dir, PATCH_REGISTRY)
    finally:
        heroes_assets, items_assets = saved_h, saved_i


def _build_patch_payload_inner(patch_id, raw_outputs, hero_out_dir, patch_cache_dir, PATCH_REGISTRY):
    baselines = compute_cross_hero_baselines(raw_outputs)

    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from build_hero_output import build_lineage_map  # noqa: E402
    ancestors_of, lineage_canon = build_lineage_map(items_assets)

    # Pre-load high-MMR baseline once (used per hero)
    try:
        hero_stats_hmmr = json.load(open(patch_cache_dir / "hero_stats_hmmr.json"))
        baseline_by_hero = {h["hero_id"]: h for h in hero_stats_hmmr}
    except Exception:
        baseline_by_hero = {}

    def cluster_one(d):
        hid = d["hero"]["id"]
        stats_path = patch_cache_dir / "hero_data" / f"itemstats_hmmr_{hid}.json"
        try:
            hero_stats = json.load(open(stats_path)) if stats_path.exists() else []
        except Exception:
            hero_stats = []
        pair_path = patch_cache_dir / "hero_data" / f"perm2_hmmr_{hid}.json"
        try:
            pair_stats = json.load(open(pair_path)) if pair_path.exists() else []
        except Exception:
            pair_stats = []
        base_h = baseline_by_hero.get(hid)
        baseline_wr_h = (base_h["wins"] / base_h["matches"]) if (base_h and base_h.get("matches")) else None
        meta_high = d.get("items", {}).get("high_mmr", {}).get("item_metadata", {})
        meta_by_int: dict[int, dict] = {}
        for k, v in meta_high.items():
            try:
                meta_by_int[int(k)] = v
            except (ValueError, TypeError):
                pass
        return hid, cluster_archetypes_for_hero_in(
            hid, patch_cache_dir,
            hero_item_stats=hero_stats,
            pair_stats=pair_stats,
            baseline_wr=baseline_wr_h,
            lineage_canon=lineage_canon,
            ancestors_of=ancestors_of,
            metadata_by_item=meta_by_int,
        )

    # Parallelize across 4 threads — CBC releases the GIL during native solve
    archetypes_by_hero: dict[int, dict] = {}
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time as _time
    t0 = _time.time()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(cluster_one, d): d for d in raw_outputs}
        done = 0
        for fut in as_completed(futs):
            hid, result = fut.result()
            archetypes_by_hero[hid] = result
            done += 1
            if done % 10 == 0 or done == len(raw_outputs):
                print(f"    clustered {done}/{len(raw_outputs)} heroes  ({_time.time()-t0:.1f}s)")

    heroes_data = []
    n_signature = 0
    for d in raw_outputs:
        hid = d["hero"]["id"]
        ch = compact_hero(d, baselines=baselines, archetypes=archetypes_by_hero.get(hid),
                          patch_id=patch_id)
        for ph in ("early", "mid", "late"):
            for p in ch["recommended"]["items"]["phases"][ph]:
                if p.get("signature"):
                    n_signature += 1
        heroes_data.append(ch)

    heroes_data.sort(key=lambda h: h["name"])
    tier = sorted(heroes_data, key=lambda h: -h["mmr"]["high"]["wr"])

    meta = PATCH_REGISTRY.get(patch_id, {})
    print(f"  {patch_id}: computing matchup counter signals …")
    counters = compute_counters_for_patch(patch_id)
    n_pairs = sum(len(v) for v in counters.values())
    print(f"  {patch_id}: {n_pairs} (hero,enemy) pairs with usable counter data")

    # Build a shared items dict for client-side lookups (counter rows and
    # imbue-target ability resolution). Only includes ids actually
    # referenced anywhere on the page to keep the dict tight.
    seen_item_ids: set[int] = set()
    for hd in counters.values():
        for lst in hd.values():
            for c in lst:
                seen_item_ids.add(c["item_id"])
    # Also include any imbue_target_id surfaced by picks — these are
    # ability ids (not upgrade-item ids) but live in the same items.json
    # under the signature1..4 slots, so the asset dict resolves them.
    for h in heroes_data:
        for ph in ("early", "mid", "late"):
            for p in h["recommended"]["items"]["phases"][ph]:
                if p.get("imbue_target_id"):
                    seen_item_ids.add(p["imbue_target_id"])
        for slc in ("all", "high"):
            for p in h["items_by_slice"][slc]:
                if p.get("imbue_target_id"):
                    seen_item_ids.add(p["imbue_target_id"])
    items_dict: dict[int, dict] = {}
    for iid in seen_item_ids:
        it = items_assets.get(iid)
        if it:
            items_dict[iid] = {
                "name": it.get("name", "?"),
                "category": it.get("item_slot_type"),
                "tier": it.get("item_tier"),
                "cost": it.get("cost"),
                "image": it.get("image"),
            }

    return {
        "id": patch_id,
        "title": meta.get("title", patch_id),
        "min_unix_timestamp": meta.get("min_ts", 0),
        "hero_count": len(heroes_data),
        "signature_picks": n_signature,
        "heroes": heroes_data,
        "tier_order_ids": [h["id"] for h in tier],
        "counters": counters,
        "items_dict": items_dict,
    }


def cluster_archetypes_for_hero_in(hid: int, patch_cache_dir, max_clusters: int = 3,
                                    hero_item_stats: list | None = None,
                                    pair_stats: list | None = None,
                                    baseline_wr: float | None = None,
                                    lineage_canon: dict | None = None,
                                    ancestors_of: dict | None = None,
                                    metadata_by_item: dict | None = None) -> dict:
    """Patch-scoped variant: looks up build-stats / build files under the
    given patch_cache_dir rather than the module-level HERO_DATA constant.
    """
    seen_ids: set[int] = set()
    builds: list[dict] = []
    for slice_label in ("all", "hmmr"):
        f = patch_cache_dir / "hero_data" / f"buildstats_{slice_label}_{hid}.json"
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
                "id": bid, "name": b.get("name", "?"),
                "wr": st["wins"] / st["matches"], "matches": st["matches"], "items": items,
            })

    if not builds:
        return {"clusters": [], "total_builds": 0}
    if len(builds) <= 2:
        k = 1
    elif len(builds) <= 5:
        k = 2
    else:
        k = min(max_clusters, max(2, len(builds) // 4))
    clusters = _agglomerative(builds, k)
    out = []
    for ci in clusters:
        in_b = [builds[i] for i in ci]
        out_b = [builds[i] for i in range(len(builds)) if i not in ci]
        meta = _label_cluster(in_b, out_b)
        meta["share"] = round(len(in_b) / len(builds), 3)
        meta["sample_build_names"] = [b["name"] for b in sorted(in_b, key=lambda x: -x["wr"])[:3]]
        if hero_item_stats is not None and lineage_canon is not None and ancestors_of is not None:
            # Try the synergy-ILP optimizer first (per-archetype stat optimization).
            # Fall back to frequency-based aggregation if the optimizer can't find
            # 16 viable picks (rare — happens for low-data clusters).
            optimized = []
            if pair_stats is not None and baseline_wr is not None and len(in_b) >= 2:
                optimized = _optimize_cluster_build(
                    in_b, hero_item_stats, pair_stats, baseline_wr,
                    lineage_canon, ancestors_of, metadata_by_item,
                )
            if optimized:
                meta["build"] = optimized
                meta["build_method"] = "synergy_ilp"  # the good kind
            else:
                meta["build"] = _aggregate_cluster_build(in_b, hero_item_stats,
                                                         lineage_canon, ancestors_of, metadata_by_item)
                meta["build_method"] = "frequency"  # fallback
        out.append(meta)
    out.sort(key=lambda c: -c["share"])
    return {"clusters": out, "total_builds": len(builds)}


def main() -> None:
    print("Building multi-patch page payload …")
    # Discover available patches by what's on disk
    patches_root = ROOT / "heroes"
    patch_dirs = sorted([p for p in patches_root.iterdir() if p.is_dir()],
                        key=lambda p: p.name, reverse=True)
    print(f"Patch folders found: {[p.name for p in patch_dirs]}")

    payloads = {}
    for pdir in patch_dirs:
        pid = pdir.name
        payload = build_patch_payload(pid)
        if payload:
            payloads[pid] = payload

    # Default to the newest patch present (highest patch_id by sort)
    default_patch = max(payloads.keys()) if payloads else None

    page_data = {
        "spec_version": "1.1.0",
        "data_source": "api.deadlock-api.com",
        "default_patch": default_patch,
        "patches": payloads,
    }

    target = CACHE / "page_data.json"
    with open(target, "w") as f:
        json.dump(page_data, f, separators=(",", ":"))
    size = target.stat().st_size
    print(f"\n[saved] {target}  {size:,} bytes  ({size/1024:.1f} KB)")
    for pid, p in payloads.items():
        marker = "  ← default" if pid == default_patch else ""
        print(f"  {pid}: {p['hero_count']} heroes, {p['signature_picks']} signature picks{marker}")


if __name__ == "__main__":
    main()
