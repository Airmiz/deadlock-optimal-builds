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


# Page-side slice short codes ↔ JSON slice keys produced by build_hero_output.
# Ordered the way they appear in the MMR toggle on the page.
SLICE_KEYS = (
    ("all",  "all_mmr"),
    ("high", "high_mmr"),
    ("asc",  "ascendant_plus"),
    ("eter", "eternus_plus"),
)


def _compact_mmr(mmr_slices: dict) -> dict:
    """Compact mmr block keyed by short-code. Slices not present in the
    per-hero JSON (e.g. zero matches at Eternus+ for a niche hero) become
    {wr:None, matches:0, players:0} so the page JS can show 'insufficient
    data' without null-checking each access."""
    def _row(s: dict | None) -> dict:
        if not s:
            return {"wr": None, "matches": 0, "players": 0}
        return {"wr": s.get("baseline_win_rate"),
                "matches": s.get("matches", 0),
                "players": s.get("players", 0)}
    return {
        "all":  _row(mmr_slices.get("all_mmr")),
        "high": _row(mmr_slices.get("high_mmr")),
        "asc":  _row(mmr_slices.get("ascendant_plus")),
        "eter": _row(mmr_slices.get("eternus_plus")),
    }


# Asset look-ups (LEGACY/global — patch-aware code below loads per-patch
# snapshots from cache/<patch_id>/ when available, falling back to these).
with open(CACHE / "heroes.json", encoding="utf-8") as _f:
    heroes_assets = {h["id"]: h for h in json.load(_f)}
with open(CACHE / "items.json", encoding="utf-8") as _f:
    items_assets = {i["id"]: i for i in json.load(_f)}


# Per-item icon overrides produced by scripts/scrape_wiki_icons.py.
# Maps item_id -> relative path under assets/items_wiki/. Why this exists:
# items.json reuses asset filenames across unrelated items (Mercurial
# Magnum + Ballistic Enchantment + Swift Striker all share
# fire_rate_plus.png), so the assets/items/ namespace can't tell them
# apart. assets/items_wiki/ has one file per item id, no collisions.
# If the manifest is missing (scraper hasn't run yet), this is just an
# empty dict and every item falls through to its items.json image.
_WIKI_OVERRIDES_PATH = CACHE / "wiki_icon_overrides.json"
if _WIKI_OVERRIDES_PATH.exists():
    with open(_WIKI_OVERRIDES_PATH, encoding="utf-8") as _f:
        _wiki_overrides_raw = json.load(_f)
    # Manifest stores str-keyed ids because JSON has no int keys.
    # Cast back so lookups by int item_id work directly.
    _WIKI_OVERRIDES = {int(k): v for k, v in _wiki_overrides_raw.items()}
else:
    _WIKI_OVERRIDES = {}


def _apply_wiki_overrides(items_dict: dict) -> dict:
    """Replace items_dict[id].image with the wiki override (relative
    asset path) when one exists. Idempotent — safe to call on already-
    overridden dicts; just no-ops if the override == current value.

    Called immediately after every items.json load (global + per-patch)
    so every downstream image lookup gets the right per-item icon
    regardless of the api's filename-collision quirks."""
    if not _WIKI_OVERRIDES:
        return items_dict
    for iid, rel in _WIKI_OVERRIDES.items():
        if iid in items_dict:
            items_dict[iid]["image"] = rel
    return items_dict


items_assets = _apply_wiki_overrides(items_assets)


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

    with open(heroes_src, encoding="utf-8") as _f:
        h = {x["id"]: x for x in json.load(_f)}
    with open(items_src, encoding="utf-8") as _f:
        i = {x["id"]: x for x in json.load(_f)}
    return h, _apply_wiki_overrides(i)

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


def _hydrate_chain_images(chain: list) -> list:
    """Force every lineage_chain entry's `image` to whatever items_assets
    currently says for that item_id. Two reasons we OVERRIDE rather than
    just backfill:
      1. Older per-hero JSONs on disk were written before the lineage
         chain had an image field — those need backfill or stage rows
         render T1/T2 placeholder badges.
      2. EVEN OLDER per-hero JSONs were written with the api URL's
         basename baked into the chain image (e.g. Extra Spirit ->
         assets/items/tech_damage.png — colliding with Golden Goose Egg).
         When the wiki override manifest changes the right path to
         assets/items_wiki/extra_spirit.png, we must replace the stale
         path, not preserve it. Just backfilling would leave the
         cross-wired icon visible until a full hero-JSON regen.
    Idempotent: if items_assets has no entry for the item, the existing
    image (if any) is preserved as a fallback."""
    out = []
    for c in (chain or []):
        iid = c.get("item_id")
        fresh_img = items_assets.get(iid, {}).get("image") if iid is not None else None
        if fresh_img:
            out.append({**c, "image": fresh_img})
        else:
            # No items_assets entry — keep whatever the per-hero JSON had
            # (could be None, in which case the page falls back to the
            # T1/T2 placeholder badge for this stage row).
            out.append(c)
    return out


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

    # Decorate with lineage chains (same shape as the recommended build).
    # Ancestor entries also carry imbue metadata so the page can render
    # imbue badges on stage rows when a passive imbue component (e.g.
    # Compress Cooldown → Superior Cooldown) is the imbuable item even
    # though its non-imbuable descendant is what the optimizer picked.
    for p in picks:
        ancs = ancestors_of.get(p["item_id"], set())
        chain = []
        for anc_id in ancs:
            it = items_assets.get(anc_id)
            if not it:
                continue
            anc_stat = stats_by_id.get(anc_id)
            anc_meta = (metadata_by_item or {}).get(anc_id, {})
            chain.append({
                "item_id": anc_id,
                "name": it.get("name"),
                "tier": it.get("item_tier"),
                "cost": it.get("cost"),
                # Including image here is what lets stage rows render the
                # real item icon instead of the T1/T2 placeholder badge.
                # Source is items_assets (the items.json snapshot) — same
                # field the top-level picks already use.
                "image": it.get("image"),
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
        # Lineage chain (lower-tier ancestors with buy times). Ancestors
        # carry their own imbue metadata so stage rows can show imbue
        # badges (e.g. T2 Compress Cooldown is the imbuable component
        # even when the optimizer picks T3 Superior Cooldown).
        ancs = ancestors_of.get(p["item_id"], set())
        chain = []
        for anc_id in ancs:
            ait = items_assets.get(anc_id)
            if not ait:
                continue
            anc_stat = stats_by_id.get(anc_id)
            anc_meta = (metadata_by_item or {}).get(anc_id, {})
            chain.append({
                "item_id": anc_id,
                "name": ait.get("name"),
                "tier": ait.get("item_tier"),
                "cost": ait.get("cost"),
                # Including image here is what lets stage rows render the
                # real item icon instead of the T1/T2 placeholder badge.
                "image": ait.get("image"),
                "matches": anc_stat["matches"] if anc_stat else None,
                "avg_buy_time_min": (round(anc_stat["avg_buy_time_s"] / 60, 1)
                                     if anc_stat else None),
                "imbue": ait.get("imbue"),
                "imbue_target_id": anc_meta.get("imbue_target_id"),
                "imbue_target_share": anc_meta.get("imbue_target_share"),
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
        with open(f, encoding="utf-8") as _fh:
            _rows = json.load(_fh)
        for st in _rows:
            bid = st["hero_build_id"]
            if bid in seen_ids:
                continue
            if st["matches"] < 50:
                continue
            bf = BUILD_FILES / f"build_{bid}.json"
            if not bf.exists():
                continue
            try:
                with open(bf, encoding="utf-8") as _fh:
                    d = json.load(_fh)
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

    def _max_order_from_sequence(seq: list[int]) -> tuple[int, ...]:
        """Extract the *max order* (tier-3 commitment order) from a 16-step
        ability sequence.

        Each ability appears exactly four times in a complete ladder:
        once at unlock and three times for upgrades (tier 1, 2, 3). The
        fourth occurrence of an ability is the tier-3 max spend. Order
        abilities ascending by that fourth-occurrence position to get
        the strategic priority.

        Used to derive a max-order fingerprint from `best_full_orders`
        sequences pulled from raw ability-order-stats data (which has no
        accompanying item list — see match-only archetype rendering on
        the page).
        """
        counts: dict[int, int] = {}
        max_position: dict[int, int] = {}
        for i, aid in enumerate(seq or []):
            counts[aid] = counts.get(aid, 0) + 1
            if counts[aid] == 4:
                max_position[aid] = i
        ordered = sorted(max_position.items(), key=lambda x: x[1])
        return tuple(aid for aid, _ in ordered)[:3]

    def _compact_joint_archetype(arch: dict) -> dict:
        """Strip a joint archetype dict to the fields the page needs.

        Each archetype carries its own item picks + ability ladder
        (methodology review §3.6). The page renders a tab strip per
        (hero, MMR slice) when 2+ joint archetypes exist; clicking a tab
        swaps both the build and the ability priority shown below.
        """
        return {
            "archetype_id": arch.get("archetype_id"),
            "fingerprint_ability_names": arch.get("fingerprint_ability_names", []),
            "consensus_ladder_names": arch.get("consensus_ladder_names", []),
            "modal_full_ladder_names": arch.get("modal_full_ladder_names", []),
            "modal_full_ladder_ids": arch.get("modal_full_ladder_ids", []),
            "n_builds": arch.get("n_builds", 0),
            "total_matches": arch.get("total_matches", 0),
            "mean_win_rate": arch.get("mean_win_rate", 0),
            "win_rate_lift_pp": arch.get("win_rate_lift_pp", 0),
            "items": [with_affinity({
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
                "lineage_chain": _hydrate_chain_images(p.get("lineage_chain", [])),
                "is_active": p.get("is_active", False),
                "cooldown_s": p.get("cooldown_s"),
                "imbue": p.get("imbue"),
            }) for p in arch.get("items", [])],
        }

    out = {
        "id": hid,
        "name": name,
        "image": hero_image(hid),
        "abilities": [
            {"id": a["id"], "name": a["name"],
             "image": items_assets.get(a["id"], {}).get("image")}
            for a in d["hero"]["abilities"]
        ],
        # Per-slice baseline stats. all/high are guaranteed; asc/eter are
        # emitted as null-WR placeholders when the slice has no matches for
        # this hero so the page JS can render "insufficient data" without
        # null-checking everywhere.
        "mmr": _compact_mmr(d["mmr_slices"]),
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
                        "lineage_chain": _hydrate_chain_images(p.get("lineage_chain", [])),
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
        # Per-MMR-slice ability breakdown so the page can offer a toggle.
        # SLICE_KEYS keeps the four slice short-codes the page UI uses in
        # sync with the JSON keys on disk.
        "ability_orders": {
            slice_label: {
                "priority": (d["ability_orders"].get(src) or {}).get("ability_priority", []),
                "best_full": ((d["ability_orders"].get(src) or {}).get("best_full_orders") or [None])[0],
                "best_opener": ((d["ability_orders"].get(src) or {}).get("best_openers_first4") or [None])[0],
                "alternate_openers": (d["ability_orders"].get(src) or {}).get("best_openers_first4", [])[1:4],
                "alternate_fulls": (d["ability_orders"].get(src) or {}).get("best_full_orders", [])[1:4],
            }
            for slice_label, src in SLICE_KEYS
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
                "lineage_chain": _hydrate_chain_images(p.get("lineage_chain", [])),
                "is_active": p.get("is_active", False),
                "cooldown_s": p.get("cooldown_s"),
                "imbue": p.get("imbue"),
                "imbue_target_id": p.get("imbue_target_id"),
                "imbue_target_share": p.get("imbue_target_share"),
            }) for p in (d["items"].get(src, {}).get("synergy_ilp", {}).get("picks") or [])]
            for slice_label, src in SLICE_KEYS
        },
        "archetypes": archetypes or {"clusters": [], "total_builds": 0},
        # Joint item + ability archetypes (methodology review §3.6).
        # Per-MMR-slice list, each entry self-contained with its own
        # ability ladder and items. Empty list when no community builds
        # cluster cleanly (e.g. low-pick hero / thin slice).
        "joint_archetypes_by_slice": {
            slice_label: [
                _compact_joint_archetype(arch)
                for arch in (d["items"].get(src, {}).get("joint_archetypes") or [])
            ]
            for slice_label, src in SLICE_KEYS
        },
    }

    # Match-only ability archetypes (no template item data).
    # Derived from `ability_orders[<slice>].best_full_orders` — these are
    # max-order patterns observed in raw match-level data that have NO
    # corresponding published Steam template. We surface them as
    # additional tabs so users can see the high-WR ability priorities
    # that the template-based clusters miss; the item column falls back
    # to the recommended ILP build (the page makes this explicit when
    # the tab is active).
    abilities_meta = {a["id"]: a["name"] for a in d["hero"]["abilities"]}
    template_fingerprints_by_slice: dict[str, set[tuple]] = {
        slice_label: {tuple(arch.get("fingerprint_ability_ids") or [])
                      for arch in (d["items"].get(src, {}).get("joint_archetypes") or [])}
        for slice_label, src in SLICE_KEYS
    }
    baseline_wr_by_slice = {
        slice_label: out["mmr"].get(slice_label, {}).get("wr")
        for slice_label, _ in SLICE_KEYS
    }

    # Lazy import to avoid a hard dep when the resolver hasn't run yet.
    import hashlib
    resolutions_dir = CACHE / "match_archetype_resolutions" / patch_id

    def _load_resolved_items(slice_label: str, fp: tuple) -> list | None:
        """Return decorated picks from a cached resolver run, or None."""
        if not resolutions_dir.exists():
            return None
        h = hashlib.sha1(",".join(str(a) for a in fp).encode()).hexdigest()[:10]
        path = resolutions_dir / f"{hid}_{slice_label}_{h}.json"
        if not path.exists() or path.stat().st_size < 2:
            return None
        try:
            with open(path, encoding="utf-8") as f:
                res = json.load(f)
        except Exception:
            return None
        # Adapt the resolver's pick schema to the page's expected fields.
        picks = []
        for p in (res.get("items") or []):
            picks.append(with_affinity({
                "slot": p["slot"], "name": p["name"], "category": p["category"],
                "tier": p["tier"], "cost": p["cost"],
                "buy_min": round(p["avg_buy_time_s"] / 60, 1) if p.get("avg_buy_time_s") else None,
                "sell_min": (round(p["avg_sell_time_s"] / 60, 1)
                             if p.get("avg_sell_time_s") else None),
                "wr": p["win_rate"], "phase": p["phase"],
                "image": items_assets.get(p["item_id"], {}).get("image"),
                "item_id": p["item_id"],
                "tag": "stat",       # resolver doesn't have community-build metadata
                "pick_rate": p.get("personal_pick_rate", 0.0),
                "annotation": "",
                "lineage_chain": [],
                "is_active": p.get("is_active", False),
                "cooldown_s": None,
                "imbue": p.get("imbue"),
            }))
        return picks if picks else None

    out["match_only_archetypes_by_slice"] = {}
    for slice_label, src in SLICE_KEYS:
        full_orders = (d["ability_orders"].get(src) or {}).get("best_full_orders") or []
        # Bucket every sequence by its max-order fingerprint. The per-hero
        # JSON renames the raw API `abilities` field to `sequence_ids`.
        by_fp: dict[tuple, dict] = {}
        for r in full_orders:
            fp = _max_order_from_sequence(r.get("sequence_ids") or [])
            if not fp or len(fp) < 3:
                continue
            bucket = by_fp.setdefault(fp, {
                "fingerprint_ability_ids": list(fp),
                "fingerprint_ability_names": [abilities_meta.get(a, "?") for a in fp],
                "n_sequences": 0,
                "total_matches": 0,
                "total_wins": 0,
                "n_players": 0,
                # Track the highest-WR sequence in this cluster so the
                # page can show the actual 16-step AP order, not just
                # the 3-ability max-order fingerprint.
                "_best_rep": None,
            })
            bucket["n_sequences"] += 1
            bucket["total_matches"] += r.get("matches", 0)
            bucket["total_wins"] += r.get("wins", 0)
            bucket["n_players"] += r.get("players", 0)
            seq_wr = (r.get("wins", 0) / r.get("matches", 1)) if r.get("matches") else 0
            best_so_far = bucket["_best_rep"]
            if best_so_far is None or seq_wr > best_so_far["wr"]:
                bucket["_best_rep"] = {
                    "wr": seq_wr,
                    "matches": r.get("matches", 0),
                    "players": r.get("players", 0),
                    "sequence_ids": r.get("sequence_ids") or [],
                }

        baseline = baseline_wr_by_slice.get(slice_label) or 0
        template_fps = template_fingerprints_by_slice.get(slice_label, set())
        match_only = []
        for fp, bucket in by_fp.items():
            if fp in template_fps:
                continue  # already a template cluster; skip the duplicate
            if bucket["total_matches"] <= 0:
                continue
            wr = bucket["total_wins"] / bucket["total_matches"]
            bucket["mean_win_rate"] = round(wr, 4)
            bucket["win_rate_lift_pp"] = round((wr - baseline) * 100, 2) if baseline else None
            # Promote the representative-full-ladder tracking from
            # internal scratch field to the final emitted shape. The
            # page renders this as the archetype's 16-step AP order.
            rep = bucket.pop("_best_rep", None)
            if rep and rep["sequence_ids"]:
                bucket["best_full_ladder_ids"] = rep["sequence_ids"]
                bucket["best_full_ladder_names"] = [abilities_meta.get(a, "?") for a in rep["sequence_ids"]]
                bucket["best_full_ladder_wr"] = round(rep["wr"], 4)
                bucket["best_full_ladder_matches"] = rep["matches"]
                bucket["best_full_ladder_players"] = rep["players"]
            # Attach resolved items if the resolver has run for this
            # (hero, slice, fingerprint). Falls back to None → page
            # shows the recommended ILP build with a caveat banner.
            resolved = _load_resolved_items(slice_label, fp)
            if resolved:
                bucket["items"] = resolved
                bucket["resolved"] = True
            match_only.append(bucket)
        # Sort by lift descending so the headline "alternatives" land first.
        match_only.sort(key=lambda b: -(b.get("win_rate_lift_pp") or -999))
        out["match_only_archetypes_by_slice"][slice_label] = match_only

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
    with open(CACHE / "playable_heroes.json", encoding="utf-8") as _fh:
        _playable = json.load(_fh)
    for h in _playable:
        f = hero_data_dir / f"itemstats_hmmr_{h['id']}.json"
        if not f.exists():
            continue
        try:
            with open(f, encoding="utf-8") as _fh:
                d = json.load(_fh)
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
            with open(cf, encoding="utf-8") as _fh:
                stats = json.load(_fh)
        except Exception:
            continue
        baseline_for_hero = baselines.get(hero_id, {})
        if not baseline_for_hero:
            continue

        # Methodology review §2.8 Problem 1: replace hard thresholds
        # (n_vs >= 100, n_base >= 200, |Δ| >= 0.4) with a continuous
        # confidence-weighted score:
        #     score = Δpp × min(1, n_vs/300) × min(1, n_base/500)
        # Items with thin samples or tiny effect get attenuated rather
        # than dropped, which removes the 0.39pp-vs-0.41pp discontinuity
        # the review flagged. We keep a soft floor (n_vs >= 25, n_base
        # >= 50) only to filter pure noise from heroes with one or two
        # matchup observations — the confidence weight handles the rest.
        deltas = []
        for s in stats:
            iid = s["item_id"]
            base = baseline_for_hero.get(iid)
            if not base:
                continue
            n_vs = s.get("matches", 0)
            n_base = base.get("matches", 0)
            if n_vs < 25 or n_base < 50:
                continue  # pure-noise floor only
            it = items_assets.get(iid)
            if not (it and it.get("type") == "upgrade"
                    and it.get("item_slot_type") in ("weapon", "vitality", "spirit")):
                continue
            wr_vs = s["wins"] / n_vs
            wr_base = base["wins"] / n_base
            delta_pp = round((wr_vs - wr_base) * 100, 2)
            conf = min(1.0, n_vs / 300.0) * min(1.0, n_base / 500.0)
            score = round(delta_pp * conf, 3)
            # A near-zero confidence-weighted score is below the noise
            # floor — drop it. This collapses the old |Δ|>=0.4 threshold
            # into a single continuous criterion.
            if abs(score) < 0.05:
                continue
            # Only keep id-keyed fields; UI looks up name/cat/tier/cost/image
            # from a shared items dict embedded once per patch (saves ~2 MB).
            deltas.append({
                "item_id": iid,
                "delta_pp": delta_pp,
                "confidence_weighted_score": score,
                "n_vs": n_vs,
                "n_base": n_base,
            })
        if not deltas:
            continue
        # Keep top-K by |confidence-weighted score| (§2.8 Problem 1).
        # The score already attenuates thin samples and tiny effects, so
        # ranking by it gives the cleanest signal — no separate top-3-each-side
        # logic needed because confidence weighting handles the symmetry.
        deltas.sort(key=lambda x: -abs(x["confidence_weighted_score"]))
        kept = deltas[:top_k]
        kept.sort(key=lambda x: -x["confidence_weighted_score"])
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

    def _load(p):
        with open(p, encoding="utf-8") as _fh:
            return json.load(_fh)
    raw_outputs = [_load(f) for f in files]
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
        with open(patch_cache_dir / "hero_stats_hmmr.json", encoding="utf-8") as _fh:
            hero_stats_hmmr = json.load(_fh)
        baseline_by_hero = {h["hero_id"]: h for h in hero_stats_hmmr}
    except Exception:
        baseline_by_hero = {}

    def cluster_one(d):
        hid = d["hero"]["id"]
        stats_path = patch_cache_dir / "hero_data" / f"itemstats_hmmr_{hid}.json"
        try:
            if stats_path.exists():
                with open(stats_path, encoding="utf-8") as _fh:
                    hero_stats = json.load(_fh)
            else:
                hero_stats = []
        except Exception:
            hero_stats = []
        pair_path = patch_cache_dir / "hero_data" / f"perm2_hmmr_{hid}.json"
        try:
            if pair_path.exists():
                with open(pair_path, encoding="utf-8") as _fh:
                    pair_stats = json.load(_fh)
            else:
                pair_stats = []
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
    # Walk both top-level picks AND their lineage_chain ancestors, since
    # passive imbue components (Compress Cooldown, Mystic Expansion,
    # Duration Extender) carry their own imbue_target_id on the chain
    # entry — that's what stage rows render.
    def _harvest_imbue_targets(p):
        if p.get("imbue_target_id"):
            seen_item_ids.add(p["imbue_target_id"])
        for c in (p.get("lineage_chain") or []):
            if c.get("imbue_target_id"):
                seen_item_ids.add(c["imbue_target_id"])
    for h in heroes_data:
        for ph in ("early", "mid", "late"):
            for p in h["recommended"]["items"]["phases"][ph]:
                _harvest_imbue_targets(p)
        for slc in ("all", "high"):
            for p in h["items_by_slice"][slc]:
                _harvest_imbue_targets(p)
        for c in (h.get("archetypes", {}) or {}).get("clusters", []):
            for p in (c.get("build") or []):
                _harvest_imbue_targets(p)
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

    # Methodology review §2.8 Problem 2: enemy-team trait taxonomy.
    # The page client-side can use this map to aggregate per-enemy
    # counter deltas with max-per-trait saturation instead of summing
    # per-enemy (which double-counts shared traits like 'sustain' when
    # the team has two healers). Partial coverage by class_name — heroes
    # not in the map fall back to the old per-enemy summation, which
    # degrades gracefully.
    from hero_traits import HERO_TRAITS, TRAITS
    hero_traits_by_id: dict[int, list[str]] = {}
    for h in heroes_data:
        cn = h.get("class_name") or h.get("name", "").lower()
        traits = HERO_TRAITS.get(cn)
        if traits:
            hero_traits_by_id[h["id"]] = sorted(traits)

    return {
        "id": patch_id,
        "title": meta.get("title", patch_id),
        "min_unix_timestamp": meta.get("min_ts", 0),
        "hero_count": len(heroes_data),
        "signature_picks": n_signature,
        "heroes": heroes_data,
        "tier_order_ids": [h["id"] for h in tier],
        "counters": counters,
        "hero_traits": hero_traits_by_id,
        "trait_taxonomy": list(TRAITS),
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
        with open(f, encoding="utf-8") as _fh:
            _rows = json.load(_fh)
        for st in _rows:
            bid = st["hero_build_id"]
            if bid in seen_ids:
                continue
            if st["matches"] < 50:
                continue
            bf = BUILD_FILES / f"build_{bid}.json"
            if not bf.exists():
                continue
            try:
                with open(bf, encoding="utf-8") as _fh:
                    d = json.load(_fh)
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

    # Cross-patch imbue-target fallback. A new patch (e.g. patch_129989) often
    # has zero community-build metadata for the first few days because few
    # players have published builds at high MMR yet. Imbue choices, however,
    # are tied to (hero, item) pairs — they don't change patch-over-patch
    # unless an ability gets reworked. So when a pick on a newer patch is
    # missing imbue_target_id, fall back to the same (hero, item) target
    # from a prior patch's data. This restores 🔮 → ability badges on
    # patches that haven't accumulated community builds yet.
    if len(payloads) > 1:
        # Build a (hero_id, item_id) -> (target_id, share, source_patch) map
        # from each patch's per-hero JSON metadata (not just the picks),
        # since the metadata covers far more items than what the optimizer
        # ends up choosing. Prioritize newer patches but accept any.
        cross_imbue: dict[tuple[int, int], tuple[int, float | None, str]] = {}
        ordered = sorted(payloads.keys(), reverse=True)
        for pid in ordered:
            hero_dir = ROOT / "heroes" / pid
            if not hero_dir.exists():
                continue
            for hf in hero_dir.glob("*_build.json"):
                try:
                    with open(hf, encoding="utf-8") as _fh:
                        hd = json.load(_fh)
                except Exception:
                    continue
                hid = hd.get("hero", {}).get("id")
                if hid is None:
                    continue
                for slice_label in ("high_mmr", "all_mmr"):
                    md = hd.get("items", {}).get(slice_label, {}).get("item_metadata", {})
                    for iid_str, m in md.items():
                        try:
                            iid = int(iid_str)
                        except (ValueError, TypeError):
                            continue
                        tgt = m.get("imbue_target_id")
                        if not tgt:
                            continue
                        key = (hid, iid)
                        cross_imbue.setdefault(key, (tgt,
                                                    m.get("imbue_target_share"), pid))

        # Hero-mode fallback: per-hero modal imbue target across ALL items
        # in the hero's metadata. When a hero has no community-build target
        # for a specific item but the hero consistently imbues most other
        # items onto the same ability (e.g. Lash imbues 4 items onto Ground
        # Strike), we use that ability as a reasonable default for the
        # missing item. Targets are hero-specific so this only works
        # *within* a hero, never across heroes.
        from collections import Counter
        hero_modal_target: dict[int, tuple[int, str]] = {}  # hid -> (target_id, source_pid)
        for pid in ordered:
            hero_dir = ROOT / "heroes" / pid
            if not hero_dir.exists():
                continue
            for hf in hero_dir.glob("*_build.json"):
                try:
                    with open(hf, encoding="utf-8") as _fh:
                        hd = json.load(_fh)
                except Exception:
                    continue
                hid = hd.get("hero", {}).get("id")
                if hid is None or hid in hero_modal_target:
                    continue  # newer patch already supplied a modal
                target_counter: Counter = Counter()
                for slice_label in ("high_mmr", "all_mmr"):
                    md = hd.get("items", {}).get(slice_label, {}).get("item_metadata", {})
                    for m in md.values():
                        tgt = m.get("imbue_target_id")
                        if tgt:
                            target_counter[tgt] += 1
                if target_counter:
                    top, _ = target_counter.most_common(1)[0]
                    hero_modal_target[hid] = (top, pid)

        # Apply fallback: any pick missing imbue_target_id but present in the
        # cross-patch map gets filled in. If the cross-patch map doesn't
        # have an entry, fall back to the hero's modal target.
        filled = 0
        modal_filled = 0
        for pid, payload in payloads.items():
            for h in payload["heroes"]:
                hid = h["id"]
                modal = hero_modal_target.get(hid)
                def _fill(p):
                    nonlocal filled, modal_filled
                    if p.get("imbue") and not p.get("imbue_target_id"):
                        key = (hid, p.get("item_id"))
                        hit = cross_imbue.get(key)
                        if hit:
                            p["imbue_target_id"] = hit[0]
                            p["imbue_target_share"] = hit[1]
                            if hit[2] != pid:
                                p["imbue_target_source_patch"] = hit[2]
                            filled += 1
                        elif modal:
                            p["imbue_target_id"] = modal[0]
                            p["imbue_target_inferred"] = True  # weakest signal
                            p["imbue_target_source_patch"] = modal[1]
                            modal_filled += 1
                    for c in (p.get("lineage_chain") or []):
                        if c.get("imbue") and not c.get("imbue_target_id"):
                            key = (hid, c.get("item_id"))
                            hit = cross_imbue.get(key)
                            if hit:
                                c["imbue_target_id"] = hit[0]
                                c["imbue_target_share"] = hit[1]
                                if hit[2] != pid:
                                    c["imbue_target_source_patch"] = hit[2]
                                filled += 1
                            elif modal:
                                c["imbue_target_id"] = modal[0]
                                c["imbue_target_inferred"] = True
                                c["imbue_target_source_patch"] = modal[1]
                                modal_filled += 1
                for ph in ("early", "mid", "late"):
                    for p in h["recommended"]["items"]["phases"][ph]:
                        _fill(p)
                for slc in ("all", "high"):
                    for p in h["items_by_slice"][slc]:
                        _fill(p)
                for c in (h.get("archetypes", {}) or {}).get("clusters", []):
                    for p in (c.get("build") or []):
                        _fill(p)
        # Re-harvest items_dict ids since we just added new imbue_target_ids.
        # The patch's items_dict was built before fallback ran, so any newly
        # filled target won't resolve to a name. Rebuild items_dict per patch.
        for pid, payload in payloads.items():
            seen: set[int] = set(int(k) for k in payload["items_dict"].keys())
            for h in payload["heroes"]:
                def _harvest_ids(p):
                    if p.get("imbue_target_id"):
                        seen.add(p["imbue_target_id"])
                    for c in (p.get("lineage_chain") or []):
                        if c.get("imbue_target_id"):
                            seen.add(c["imbue_target_id"])
                for ph in ("early", "mid", "late"):
                    for p in h["recommended"]["items"]["phases"][ph]:
                        _harvest_ids(p)
                for slc in ("all", "high"):
                    for p in h["items_by_slice"][slc]:
                        _harvest_ids(p)
                for c in (h.get("archetypes", {}) or {}).get("clusters", []):
                    for p in (c.get("build") or []):
                        _harvest_ids(p)
            for iid in seen:
                if str(iid) in payload["items_dict"] or iid in payload["items_dict"]:
                    continue
                it = items_assets.get(iid)
                if it:
                    payload["items_dict"][iid] = {
                        "name": it.get("name", "?"),
                        "category": it.get("item_slot_type"),
                        "tier": it.get("item_tier"),
                        "image": it.get("image"),
                    }
        if filled or modal_filled:
            print(f"  imbue-target fallback: {filled} cross-patch + {modal_filled} hero-modal-inferred")

    # Default to the newest patch that has enough data to render meaningful
    # builds. Patches accumulate matches over their lifetime — landing on a
    # 3-day-old patch with 300 matches/hero shows every Ascendant+/Eternus+
    # tab as auto-disabled and every hero in the empty-state, which is a
    # bad first impression. Threshold = 100K total all-MMR matches across
    # all heroes (≈3K matches/hero on a 38-hero roster), enough for the
    # synergy ILP to produce non-empty picks for most heroes. Falls back to
    # the absolute newest patch if none qualify (so the page never shows
    # zero patches).
    DATA_RICH_THRESHOLD = 100_000

    def _patch_total_matches(p):
        total = 0
        for h in p.get("heroes", []):
            mmr_all = (h.get("mmr") or {}).get("all") or {}
            total += mmr_all.get("matches", 0)
        return total

    if payloads:
        candidates = [(pid, _patch_total_matches(p)) for pid, p in payloads.items()]
        candidates.sort(key=lambda kv: kv[0], reverse=True)  # newest first
        rich = [(pid, n) for pid, n in candidates if n >= DATA_RICH_THRESHOLD]
        default_patch = rich[0][0] if rich else candidates[0][0]
        if rich and rich[0][0] != candidates[0][0]:
            print(f"  default_patch: skipped {candidates[0][0]} ({candidates[0][1]:,} matches < "
                  f"{DATA_RICH_THRESHOLD:,} threshold) -> {default_patch}")
    else:
        default_patch = None

    page_data = {
        "spec_version": SPEC_VERSION,
        "data_source": "api.deadlock-api.com",
        "default_patch": default_patch,
        "patches": payloads,
    }

    target = CACHE / "page_data.json"
    with open(target, "w", encoding="utf-8") as f:
        json.dump(page_data, f, separators=(",", ":"), ensure_ascii=False)
    size = target.stat().st_size
    print(f"\n[saved] {target}  {size:,} bytes  ({size/1024:.1f} KB)")
    for pid, p in payloads.items():
        marker = "  <- default" if pid == default_patch else ""
        print(f"  {pid}: {p['hero_count']} heroes, {p['signature_picks']} signature picks{marker}")


if __name__ == "__main__":
    main()
