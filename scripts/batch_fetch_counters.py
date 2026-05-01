"""
Batch-fetch counter-pick data: per (hero, enemy_hero) pair, fetch
item-stats with the enemy_hero_ids filter applied. The downstream pipeline
diffs each item's WR against the no-enemy-filter baseline to surface
matchup-specific item swaps.

Scope:
  - One patch per run (PATCH_ID env var, defaults to oldest patch with
    stable data). Counter-picks need a healthy sample size, so we use
    the older patch by default unless the new one has accumulated enough
    matches.
  - High-MMR slice only (min_average_badge=91). Counter-picks are
    high-skill plays — averaging across all skill levels muddies the
    signal.
  - One enemy at a time. Multi-enemy queries (enemy_hero_ids=A,B,C)
    fragment sample sizes too aggressively. The page aggregates per-enemy
    deltas at render time.

Output: cache/<patch_id>/counters/<hero_id>_vs_<enemy_id>.json
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import (
    CACHE, PATCH_CACHE, PATCH_ID, PATCH_TITLE, PATCH_MIN_TS, HMMR_BADGE,
)
from batch_fetch import _HEADERS, fetch  # reuse the same fetch helper


COUNTERS_DIR = PATCH_CACHE / "counters"
COUNTERS_DIR.mkdir(parents=True, exist_ok=True)


def hero_vs_enemy_url(hero_id: int, enemy_id: int) -> str:
    return (
        "https://api.deadlock-api.com/v1/analytics/item-stats"
        f"?hero_id={hero_id}"
        f"&enemy_hero_ids={enemy_id}"
        f"&min_unix_timestamp={PATCH_MIN_TS}"
        f"&min_average_badge={HMMR_BADGE}"
        "&min_matches=20"
    )


def main() -> None:
    heroes = json.load(open(CACHE / "playable_heroes.json"))
    print(f"[1/2] Patch {PATCH_ID} ({PATCH_TITLE})")
    print(f"      {len(heroes)} heroes × {len(heroes)} enemies = {len(heroes)**2} matchups")

    jobs = []
    for h in heroes:
        for e in heroes:
            if h["id"] == e["id"]:
                continue  # mirror matches don't get an enemy filter
            dest = COUNTERS_DIR / f"{h['id']}_vs_{e['id']}.json"
            jobs.append((hero_vs_enemy_url(h["id"], e["id"]), dest))

    print(f"      {len(jobs)} jobs (excluding self-mirror)")

    print(f"[2/2] Fetching with 3 workers (Cloudflare-friendly) …")
    t0 = time.time()
    cached = ok = err = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {pool.submit(fetch, u, d): (u, d) for u, d in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            _, status = fut.result()
            if status == "cached": cached += 1
            elif status == "ok":   ok += 1
            else:                  err += 1
            if i % 100 == 0 or i == len(jobs):
                elapsed = time.time() - t0
                rate = (cached + ok) / max(elapsed, 0.1)
                print(f"  {i}/{len(jobs)}  cached={cached} ok={ok} err={err}  {elapsed:.1f}s  ({rate:.0f}/s)")
    print(f"\nDone in {time.time()-t0:.1f}s. cached={cached}, fetched={ok}, errors={err}")


if __name__ == "__main__":
    main()
