"""
Generate per-hero combined output JSON for every playable hero.
Reuses build_hero_output.build_hero_output() with paths pointing at the cached batch data.

Re-runs a hero's build whenever ANY of the underlying analytics input files
(item-stats, build-stats, ability orders, pair synergies, hero-stats) is
newer than the existing output, OR when the on-disk spec_version is older
than the current SPEC_VERSION (so schema bumps like the 1.1.0 -> 1.2.0 jump
that added Ascendant+/Eternus+ slices invalidate the cache automatically).
This way the scheduled refresh job naturally regenerates only the heroes
whose data actually changed, instead of unconditionally skipping everything
that already exists on disk.

Override: FORCE=1 to regenerate every hero regardless of timestamps/version.
"""
import os
import json
import re
import sys
import time
import traceback
from pathlib import Path
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import (
    ROOT, CACHE, PATCH_CACHE, HERO_OUT, HERO_DATA, BUILD_FILES, ASSETS,
    PATCH_ID, PATCH_TITLE, PATCH_MIN_TS, HMMR_BADGE, SPEC_VERSION,
)

from build_hero_output import build_hero_output  # noqa: E402


FORCE = os.environ.get("FORCE") == "1"
ONLY_HEROES = os.environ.get("ONLY", "")  # comma-sep ids, empty=all
SCORING = os.environ.get("DEADLOCK_SCORING", "wilson").lower()
if SCORING not in ("wilson", "hierarchical"):
    raise SystemExit(f"DEADLOCK_SCORING must be 'wilson' or 'hierarchical', got {SCORING!r}")
# We no longer use a blanket SKIP_EXISTING. Decision is per-hero based on
# spec_version + whether the inputs are newer than the output.
# FORCE bypasses the check.

with open(CACHE / "playable_heroes.json", encoding="utf-8") as _f:
    heroes = json.load(_f)
with open(CACHE / "items.json", encoding="utf-8") as _f:
    items_by_id = {i["id"]: i for i in json.load(_f)}
items_by_classname = {i["class_name"]: i for i in items_by_id.values() if "class_name" in i}
with open(CACHE / "heroes.json", encoding="utf-8") as _f:
    heroes_by_id = {h["id"]: h for h in json.load(_f)}


def slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return s


# Patch the build_hero_output module so method_build_replication can find build files
# in BUILD_FILES dir (it currently looks for CACHE/build_{id}.json).
import build_hero_output as bho


def _patched_build_replication(candidates, build_stats_raw, baseline_wr, build_files_dir, build_match_floor):
    # Re-implement here so we use BUILD_FILES, not the passed dir.
    from collections import Counter, defaultdict
    stats_by_id = {b["hero_build_id"]: b for b in build_stats_raw}
    item_weight = Counter()
    builds_seen = []
    qualifying_ids = [b["hero_build_id"] for b in build_stats_raw if b["matches"] >= build_match_floor]
    for bid in qualifying_ids:
        f = BUILD_FILES / f"build_{bid}.json"
        if not f.exists():
            f = CACHE / f"build_{bid}.json"
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
        st = stats_by_id[bid]
        wr = st["wins"] / st["matches"]
        weight = st["matches"] * max(0, wr - baseline_wr + 0.02)
        seen_in_build = set()
        for cat in b["details"].get("mod_categories", []):
            for mod in cat.get("mods", []):
                aid = mod.get("ability_id")
                if aid:
                    seen_in_build.add(aid)
        for iid in seen_in_build:
            item_weight[iid] += weight
        builds_seen.append({"build_id": bid, "name": b.get("name", "?"),
                            "win_rate": round(wr, 4), "matches": st["matches"]})
    ranked = []
    for iid, w in item_weight.items():
        if iid in candidates:
            ranked.append({**candidates[iid], "build_freq_weight": round(w, 1)})
    ranked.sort(key=lambda x: -x["build_freq_weight"])
    by_cat = {}
    for c in ranked:
        by_cat.setdefault(c["category"], []).append(c)
    picks, used = [], set()
    for cat in ("weapon", "vitality", "spirit"):
        for c in by_cat.get(cat, [])[:4]:
            picks.append({**c, "slot": cat})
            used.add(c["item_id"])
    pool = [c for c in ranked if c["item_id"] not in used][:4]
    for c in pool:
        picks.append({**c, "slot": "flex"})
    return picks, builds_seen


bho.method_build_replication = _patched_build_replication


# ------------------------------------------------------------------
# Optional cross-hero EB priors (methodology review §2.4).
# ------------------------------------------------------------------
# When DEADLOCK_SCORING=hierarchical, fit a per-(slice) item-prior dict
# once, then bind a per-hero closure into build_hero_output via the new
# score_fn_provider parameter. This lets the same per-hero call surface
# work — no monkey-patching, no parallel pipeline. Default scoring
# (wilson) is unchanged from production behavior.
SLICE_PATHS_KEY = {
    "all_mmr": ("all", "hero_stats_all", "item_stats_all"),
    "high_mmr": ("hmmr", "hero_stats_hmmr", "item_stats_hmmr"),
    "ascendant_plus": ("asc", "hero_stats_asc", "item_stats_asc"),
    "eternus_plus": ("eter", "hero_stats_eter", "item_stats_eter"),
}
SLICE_PRIOR_FLOORS = {
    # Per-hero match floor when contributing to the cross-hero pool. We
    # keep this looser than the candidate floor (which gates *picks*) so
    # that thin-but-real hero data still informs the prior.
    "all_mmr": 200, "high_mmr": 100, "ascendant_plus": 40, "eternus_plus": 15,
}
_priors_by_slice: dict[str, dict] = {}


def _load_slice_data(slice_label: str) -> tuple[dict, dict]:
    """Return ({hero_id: item_stats_rows}, {hero_id: baseline_wr}) for one slice."""
    suffix, hero_stats_key, item_stats_key = SLICE_PATHS_KEY[slice_label]
    hs_path = PATCH_CACHE / f"hero_stats_{suffix}.json"
    if not hs_path.exists():
        return {}, {}
    try:
        with open(hs_path, encoding="utf-8") as f:
            hero_stats = json.load(f)
    except Exception:
        return {}, {}
    baselines = {h["hero_id"]: h["wins"] / h["matches"]
                 for h in hero_stats if h.get("matches")}
    per_hero: dict[int, list] = {}
    for h in heroes:
        hid = h["id"]
        if hid not in baselines:
            continue
        f = HERO_DATA / f"itemstats_{suffix}_{hid}.json"
        if not f.exists() or f.stat().st_size < 2:
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                rows = json.load(fh)
        except Exception:
            continue
        per_hero[hid] = rows
    return per_hero, baselines


def _fit_priors_for_scoring() -> None:
    """One-time prior fit per MMR slice. No-op when scoring is 'wilson'."""
    if SCORING != "hierarchical":
        return
    import hierarchical as _h  # local import — only when needed
    for slice_label, floor in SLICE_PRIOR_FLOORS.items():
        per_hero, baselines = _load_slice_data(slice_label)
        if not per_hero:
            continue
        shrunk, cats = _h.fit_all_priors(
            per_hero, baselines, items_by_id, min_matches_per_hero=floor,
        )
        _priors_by_slice[slice_label] = shrunk
        print(f"  [hierarchical] {slice_label}: {len(shrunk)} item priors "
              f"from {len(per_hero)} heroes, {len(cats)} category priors")


def _score_fn_provider(hero_id: int, slice_label: str, baseline_wr: float):
    """Closure factory passed to build_hero_output. Returns None for
    'wilson' (preserves existing behavior) or a hierarchical scorer
    bound to this hero's baseline for 'hierarchical'."""
    if SCORING != "hierarchical":
        return None
    priors = _priors_by_slice.get(slice_label)
    if not priors:
        return None
    import hierarchical as _h
    return _h.make_score_fn(priors, baseline_wr)


def paths_for(hid: int) -> dict:
    return {
        # Population baselines (per slice)
        "hero_stats_all":  PATCH_CACHE / "hero_stats_all.json",
        "hero_stats_hmmr": PATCH_CACHE / "hero_stats_hmmr.json",
        "hero_stats_asc":  PATCH_CACHE / "hero_stats_asc.json",
        "hero_stats_eter": PATCH_CACHE / "hero_stats_eter.json",
        # Per-hero per-slice analytics
        "item_stats_all":  HERO_DATA / f"itemstats_all_{hid}.json",
        "item_stats_hmmr": HERO_DATA / f"itemstats_hmmr_{hid}.json",
        "item_stats_asc":  HERO_DATA / f"itemstats_asc_{hid}.json",
        "item_stats_eter": HERO_DATA / f"itemstats_eter_{hid}.json",
        "pair_stats_all":  HERO_DATA / f"perm2_all_{hid}.json",
        "pair_stats_hmmr": HERO_DATA / f"perm2_hmmr_{hid}.json",
        "pair_stats_asc":  HERO_DATA / f"perm2_asc_{hid}.json",
        "pair_stats_eter": HERO_DATA / f"perm2_eter_{hid}.json",
        "build_stats_all": HERO_DATA / f"buildstats_all_{hid}.json",
        "build_stats_hmmr":HERO_DATA / f"buildstats_hmmr_{hid}.json",
        "build_stats_asc": HERO_DATA / f"buildstats_asc_{hid}.json",
        "build_stats_eter":HERO_DATA / f"buildstats_eter_{hid}.json",
        "abilities_all":   HERO_DATA / f"abilityorder_all_{hid}.json",
        "abilities_hmmr":  HERO_DATA / f"abilityorder_hmmr_{hid}.json",
        "abilities_asc":   HERO_DATA / f"abilityorder_asc_{hid}.json",
        "abilities_eter":  HERO_DATA / f"abilityorder_eter_{hid}.json",
    }


def _output_is_fresh(out_path: Path, input_paths: list) -> bool:
    """True iff out_path exists, is non-trivial, and is newer than every
    existing input file. Missing inputs are ignored (the build function
    handles missing data gracefully)."""
    if not out_path.exists() or out_path.stat().st_size < 1000:
        return False
    out_mtime = out_path.stat().st_mtime
    for p in input_paths:
        if p.exists() and p.stat().st_mtime > out_mtime:
            return False
    return True


def process_one(h):
    hid, name = h["id"], h["name"]
    out_path = HERO_OUT / f"{slug(name)}_build.json"
    if not FORCE:
        # Two cache-skip gates, applied together:
        #   1. spec_version match - a schema bump (e.g. 1.1.0 -> 1.2.0 to add
        #      Ascendant+/Eternus+ slices) must always trigger a rebuild.
        #   2. input-freshness - when batch_fetch.py re-pulls fresher analytics
        #      (TTL expires every ~2h), the hero re-runs automatically.
        # Both must say "skip" for us to skip; otherwise rebuild.
        spec_matches = False
        if out_path.exists() and out_path.stat().st_size > 1000:
            try:
                with open(out_path, encoding="utf-8") as _f:
                    existing = json.load(_f)
                spec_matches = existing.get("spec_version") == SPEC_VERSION
            except Exception:
                spec_matches = False
        if spec_matches:
            paths = paths_for(hid)
            inputs = [
                paths["hero_stats_all"], paths["hero_stats_hmmr"],
                paths["hero_stats_asc"], paths["hero_stats_eter"],
                paths["item_stats_all"], paths["item_stats_hmmr"],
                paths["item_stats_asc"], paths["item_stats_eter"],
                paths["pair_stats_all"], paths["pair_stats_hmmr"],
                paths["pair_stats_asc"], paths["pair_stats_eter"],
                paths["build_stats_all"], paths["build_stats_hmmr"],
                paths["build_stats_asc"], paths["build_stats_eter"],
                paths["abilities_all"], paths["abilities_hmmr"],
                paths["abilities_asc"], paths["abilities_eter"],
            ]
            if _output_is_fresh(out_path, inputs):
                return (hid, name, "cached", out_path)
    try:
        data = build_hero_output(hid, name, paths_for(hid),
                                 items_by_id, items_by_classname, heroes_by_id,
                                 score_fn_provider=_score_fn_provider)
        data["scoring_mode"] = SCORING
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return (hid, name, "ok", out_path)
    except Exception as e:
        traceback.print_exc()
        return (hid, name, f"error: {e}", None)


def main():
    only = set(int(x) for x in ONLY_HEROES.split(",") if x) if ONLY_HEROES else None
    targets = [h for h in heroes if (only is None or h["id"] in only)]
    print(f"Scoring mode: {SCORING}")
    _fit_priors_for_scoring()
    t0 = time.time()
    results = []
    # Run 4 heroes in parallel via threads (CBC releases the GIL during native solve)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(process_one, h): h for h in targets}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            hid, name, status, path = r
            if status == "ok":
                size = path.stat().st_size // 1024
                print(f"  [{hid:>3}] {name:<20} {size:>3} KB  ({time.time()-t0:.1f}s)  {status}")
            elif status == "cached":
                print(f"  [{hid:>3}] {name:<20} cached")
            else:
                print(f"  [{hid:>3}] {name:<20} {status}")
    print(f"\nDone in {time.time()-t0:.1f}s")
    ok = sum(1 for r in results if r[2] in ("ok","cached"))
    print(f"  ok+cached: {ok}/{len(results)}")
    errors = [r for r in results if r[2].startswith("error")]
    if errors:
        print(f"  errors: {len(errors)}")
        for r in errors:
            print(f"    {r[1]}: {r[2]}")


if __name__ == "__main__":
    main()
