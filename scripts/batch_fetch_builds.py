"""
Collect every unique build_id referenced across all heroes' build-stats files,
then fetch /v1/builds details for any missing ones.
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from _paths import CACHE, HERO_DATA, BUILD_FILES


def collect_build_ids() -> set[int]:
    heroes = json.load(open(CACHE / "playable_heroes.json"))
    ids: set[int] = set()
    for h in heroes:
        hid = h["id"]
        for slice_label, floor in (("all", 100), ("hmmr", 50)):
            f = HERO_DATA / f"buildstats_{slice_label}_{hid}.json"
            if not f.exists():
                continue
            try:
                d = json.load(open(f))
            except Exception:
                continue
            qualifying = [b for b in d if b.get("matches", 0) >= floor]
            qualifying.sort(key=lambda b: -(b["wins"] / b["matches"]))
            for b in qualifying[:8]:
                ids.add(b["hero_build_id"])
    return ids


def fetch_build(bid: int) -> tuple[int, str]:
    dest = BUILD_FILES / f"build_{bid}.json"
    if dest.exists() and dest.stat().st_size > 100:
        return bid, "cached"
    url = f"https://api.deadlock-api.com/v1/builds?build_id={bid}&limit=1&only_latest=true"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "deadlock-build-analysis/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            dest.write_bytes(r.read())
        return bid, "ok"
    except Exception as e:
        return bid, f"error: {e}"


def main() -> None:
    ids = collect_build_ids()
    print(f"Unique build IDs across all heroes: {len(ids)}")
    t0 = time.time()
    results = {"cached": 0, "ok": 0, "error": 0}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(fetch_build, bid): bid for bid in ids}
        for i, fut in enumerate(as_completed(futs), 1):
            _, status = fut.result()
            key = "error" if status.startswith("error") else status
            results[key] = results.get(key, 0) + 1
            if i % 25 == 0 or i == len(ids):
                print(f"  {i}/{len(ids)}  {results}  {time.time()-t0:.1f}s")
    print(f"\nDone in {time.time()-t0:.1f}s. {results}")


if __name__ == "__main__":
    main()
