"""
Batch-fetch all required deadlock-api endpoints for every playable hero.
Idempotent — skips files already on disk. Bootstraps the asset files
(heroes.json, items.json, playable_heroes.json) on first run.

Endpoints used (all under https://api.deadlock-api.com):
  /v1/analytics/hero-stats          (population baseline)
  /v1/analytics/item-stats          (per-hero item win rates)
  /v1/analytics/item-permutation-stats   (pairwise item synergies)
  /v1/analytics/hero-build-stats/{hero_id}  (top builds + their stats)
  /v1/analytics/ability-order-stats (ability point ordering win rates)

Asset metadata (no rate limit, separate host):
  https://assets.deadlock-api.com/v2/heroes
  https://assets.deadlock-api.com/v2/items
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from _paths import CACHE, HERO_DATA, PATCH_CACHE, PATCH_ID, PATCH_TITLE, PATCH_MIN_TS, HMMR_BADGE


HMMR_MIN_MATCHES_BUILD = 30
ALL_MIN_MATCHES_BUILD = 50


_HEADERS = {
    # Cloudflare in front of api.deadlock-api.com sometimes 403s opaque UAs;
    # mimicking a real browser avoids the challenge.
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


# TTL (in seconds) past which a cached file is considered stale and re-fetched.
# Different endpoint families decay at different rates:
#   - Asset metadata (heroes/items.json) only changes when Valve drops a patch.
#     Re-pull weekly to catch silent CDN updates without paying every run.
#   - Analytics endpoints (hero-stats, item-stats, build-stats, ability orders,
#     pair synergies) are aggregated by deadlock-api with ~1 hour upstream
#     freshness. Re-pull every 2 hours so the 3-hour cron always sees fresh
#     numbers without slamming the API on every run.
#   - "Always" (TTL=0) — never cache. Used when callers want a guaranteed
#     fresh pull regardless of file age.
#   - "Never" (TTL=None) — cache forever. Used for genuinely immutable data
#     like an individual published build_{id}.json (handled in batch_fetch_builds.py).
TTL_ASSETS    = 7 * 24 * 3600   # 7 days
TTL_ANALYTICS = 2 * 3600        # 2 hours

# Default TTL for fetch() when no override is given. Conservative: matches the
# refresh cadence so the system actually pulls fresh data each cron tick.
DEFAULT_TTL = TTL_ANALYTICS


def fetch(url: str, dest: Path, timeout: int = 25,
          ttl: int | None = DEFAULT_TTL) -> tuple[Path, str]:
    """Fetch `url` to `dest`, returning ('cached'|'ok'|'error: ...').

    Caching rules:
      - Missing or empty file (<2 bytes): always fetch.
      - File exists and ttl is None: always cached (immutable).
      - File exists and is fresher than ttl seconds: cached.
      - Otherwise: re-fetch. On network error, fall back to the stale cached
        file rather than truncating it — preserves the "no diff means no
        commit" property of the refresh workflow.

    Empty `[]` responses (2 bytes) are valid cached results for brand-new
    patches where the API genuinely has no data yet, so we don't treat
    them as missing.
    """
    if dest.exists() and dest.stat().st_size >= 2:
        if ttl is None:
            return dest, "cached"
        age = time.time() - dest.stat().st_mtime
        if age < ttl:
            return dest, "cached"
        # Stale — fall through to re-fetch
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        if len(data) < 2 and dest.exists() and dest.stat().st_size >= 2:
            # API returned empty/error but we have a previous response —
            # prefer the stale-but-real data over an empty replacement.
            return dest, "stale-keep"
        dest.write_bytes(data)
        return dest, "ok"
    except Exception as e:
        # Network/API failure: keep the stale file (if any) rather than
        # blowing it away. Caller sees "error" so it can log + continue.
        return dest, f"error: {e}"


def bootstrap_assets() -> None:
    """Fetch asset metadata + derive playable hero list, snapshot per-patch.

    Each patch keeps its own snapshot of heroes.json + items.json under
    cache/<patch_id>/. This way, when the asset CDN updates for a new
    patch (item rebalances, new items, etc.), the previous patch's
    display stays correct because it reads its frozen snapshot.

    A copy is also written to cache/ root for backwards compatibility
    with any scripts that still reference the old global path.
    """
    # Patch-snapshot path (canonical going forward). Assets only change
    # when Valve drops a patch, so use the longer asset TTL.
    fetch("https://assets.deadlock-api.com/v2/heroes", PATCH_CACHE / "heroes.json", ttl=TTL_ASSETS)
    fetch("https://assets.deadlock-api.com/v2/items",  PATCH_CACHE / "items.json",  ttl=TTL_ASSETS)
    # Mirror to cache/ root for legacy callers (build_page_data still
    # reads items_assets at module level; will migrate in a follow-up).
    if not (CACHE / "heroes.json").exists():
        (CACHE / "heroes.json").write_bytes((PATCH_CACHE / "heroes.json").read_bytes())
    if not (CACHE / "items.json").exists():
        (CACHE / "items.json").write_bytes((PATCH_CACHE / "items.json").read_bytes())

    heroes = json.load(open(PATCH_CACHE / "heroes.json"))
    playable = [h for h in heroes
                if h.get("player_selectable", False)
                and not h.get("disabled", False)
                and not h.get("in_development", False)]
    payload = [{"id": h["id"], "name": h["name"], "class_name": h["class_name"]}
               for h in playable]
    dest = PATCH_CACHE / "playable_heroes.json"
    with open(dest, "w") as f:
        json.dump(payload, f, indent=2)
    # Mirror to legacy global path for backwards compat
    if not (CACHE / "playable_heroes.json").exists():
        with open(CACHE / "playable_heroes.json", "w") as f:
            json.dump(payload, f, indent=2)
    print(f"  playable heroes: {len(playable)} -> {dest.relative_to(PATCH_CACHE.parent.parent)}")


def hero_urls(hid: int) -> list[tuple[str, Path]]:
    base = "https://api.deadlock-api.com/v1/analytics"
    common = f"min_unix_timestamp={PATCH_MIN_TS}"
    return [
        (f"{base}/item-stats?hero_id={hid}&{common}&min_matches=20",
         HERO_DATA / f"itemstats_all_{hid}.json"),
        (f"{base}/item-stats?hero_id={hid}&{common}&min_matches=20&min_average_badge={HMMR_BADGE}",
         HERO_DATA / f"itemstats_hmmr_{hid}.json"),
        (f"{base}/item-permutation-stats?hero_id={hid}&comb_size=2&{common}",
         HERO_DATA / f"perm2_all_{hid}.json"),
        (f"{base}/item-permutation-stats?hero_id={hid}&comb_size=2&{common}&min_average_badge={HMMR_BADGE}",
         HERO_DATA / f"perm2_hmmr_{hid}.json"),
        (f"{base}/hero-build-stats/{hid}?{common}&min_matches={ALL_MIN_MATCHES_BUILD}",
         HERO_DATA / f"buildstats_all_{hid}.json"),
        (f"{base}/hero-build-stats/{hid}?{common}&min_matches={HMMR_MIN_MATCHES_BUILD}&min_average_badge={HMMR_BADGE}",
         HERO_DATA / f"buildstats_hmmr_{hid}.json"),
        (f"{base}/ability-order-stats?hero_id={hid}&{common}&min_matches=50",
         HERO_DATA / f"abilityorder_all_{hid}.json"),
        (f"{base}/ability-order-stats?hero_id={hid}&{common}&min_matches=20&min_average_badge={HMMR_BADGE}",
         HERO_DATA / f"abilityorder_hmmr_{hid}.json"),
    ]


def main() -> None:
    print(f"[1/3] Bootstrapping asset metadata for {PATCH_ID} ({PATCH_TITLE}) …")
    bootstrap_assets()

    fetch(f"https://api.deadlock-api.com/v1/analytics/hero-stats?min_unix_timestamp={PATCH_MIN_TS}",
          PATCH_CACHE / "hero_stats_all.json")
    fetch(f"https://api.deadlock-api.com/v1/analytics/hero-stats?min_unix_timestamp={PATCH_MIN_TS}&min_average_badge={HMMR_BADGE}",
          PATCH_CACHE / "hero_stats_hmmr.json")

    print("[2/3] Building per-hero job list …")
    heroes = json.load(open(CACHE / "playable_heroes.json"))
    all_jobs: list[tuple[str, Path]] = []
    for h in heroes:
        all_jobs.extend(hero_urls(h["id"]))
    print(f"  {len(all_jobs)} endpoints across {len(heroes)} heroes")

    print("[3/3] Fetching …")
    t0 = time.time()
    cached = ok = stale = err = 0
    # Lower parallelism (3 instead of 6) to stay under the 200 req/min IP cap
    # — important when both patches are being fetched on the same day.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fetch, u, d): (u, d) for u, d in all_jobs}
        for i, fut in enumerate(as_completed(futures), 1):
            _, status = fut.result()
            if status == "cached":         cached += 1
            elif status == "ok":           ok += 1
            elif status == "stale-keep":   stale += 1
            else:                          err += 1
            if i % 25 == 0 or i == len(all_jobs):
                elapsed = time.time() - t0
                print(f"  {i}/{len(all_jobs)}  cached={cached} fetched={ok} stale-kept={stale} err={err}  {elapsed:.1f}s")
    print(f"\nDone in {time.time()-t0:.1f}s. cached={cached}, fetched={ok}, stale-kept={stale}, errors={err}")


if __name__ == "__main__":
    main()
