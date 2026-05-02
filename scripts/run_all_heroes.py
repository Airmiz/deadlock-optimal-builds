"""
Generate per-hero combined output JSON for every playable hero.
Reuses build_hero_output.build_hero_output() with paths pointing at the cached batch data.

Re-runs a hero's build whenever ANY of the underlying analytics input files
(item-stats, build-stats, ability orders, pair synergies, hero-stats) is
newer than the existing output. This way the scheduled refresh job naturally
regenerates only the heroes whose data actually changed, instead of
unconditionally skipping everything that already exists on disk.

Override: FORCE=1 to regenerate every hero regardless of timestamps.
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
# We no longer use a blanket SKIP_EXISTING. Decision is per-hero based on
# whether the inputs are newer than the output. FORCE bypasses the check.

heroes = json.load(open(CACHE / "playable_heroes.json"))
items_by_id = {i["id"]: i for i in json.load(open(CACHE / "items.json"))}
items_by_classname = {i["class_name"]: i for i in items_by_id.values() if "class_name" in i}
heroes_by_id = {h["id"]: h for h in json.load(open(CACHE / "heroes.json"))}


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
            d = json.load(open(f))
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


def paths_for(hid: int) -> dict:
    return {
        "hero_stats_all":  PATCH_CACHE / "hero_stats_all.json",
        "hero_stats_hmmr": PATCH_CACHE / "hero_stats_hmmr.json",
        "item_stats_all":  HERO_DATA / f"itemstats_all_{hid}.json",
        "item_stats_hmmr": HERO_DATA / f"itemstats_hmmr_{hid}.json",
        "pair_stats_all":  HERO_DATA / f"perm2_all_{hid}.json",
        "pair_stats_hmmr": HERO_DATA / f"perm2_hmmr_{hid}.json",
        "build_stats_all": HERO_DATA / f"buildstats_all_{hid}.json",
        "build_stats_hmmr":HERO_DATA / f"buildstats_hmmr_{hid}.json",
        "abilities_all":   HERO_DATA / f"abilityorder_all_{hid}.json",
        "abilities_hmmr":  HERO_DATA / f"abilityorder_hmmr_{hid}.json",
    }


def _output_is_fresh(out_path: Path, input_paths: list[Path]) -> bool:
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
        # Only skip if ALL the analytics inputs are older than the existing
        # output. As soon as batch_fetch.py re-pulls a fresher itemstats /
        # buildstats / etc. file (TTL expires every 2h), this hero will
        # re-run automatically.
        paths = paths_for(hid)
        inputs = [
            paths["hero_stats_all"], paths["hero_stats_hmmr"],
            paths["item_stats_all"], paths["item_stats_hmmr"],
            paths["pair_stats_all"], paths["pair_stats_hmmr"],
            paths["build_stats_all"], paths["build_stats_hmmr"],
            paths["abilities_all"], paths["abilities_hmmr"],
        ]
        if _output_is_fresh(out_path, inputs):
            return (hid, name, "cached", out_path)
    try:
        data = build_hero_output(hid, name, paths_for(hid),
                                 items_by_id, items_by_classname, heroes_by_id)
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)
        return (hid, name, "ok", out_path)
    except Exception as e:
        traceback.print_exc()
        return (hid, name, f"error: {e}", None)


def main():
    only = set(int(x) for x in ONLY_HEROES.split(",") if x) if ONLY_HEROES else None
    targets = [h for h in heroes if (only is None or h["id"] in only)]
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
