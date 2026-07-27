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
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from _paths import (
    CACHE, HERO_DATA, PATCH_CACHE, PATCH_ID, PATCH_TITLE,
    PATCH_MAX_TS, TIME_BOUNDS_QS,
    HMMR_BADGE, ASCENDANT_BADGE, ETERNUS_BADGE,
)


def is_active_patch() -> bool:
    """True iff PATCH_ID's match window is still open (no max_ts bound).

    Closed patches are no longer accumulating new matches — their window
    is bounded by max_unix_timestamp — so their analytics aggregates are
    immutable. Callers use this to short-circuit re-fetching for closed
    patches: once the data is on disk, it stays.

    An unknown PATCH_ID (not in the registry) has no max_ts and is
    treated as active, so a first-time run still pulls fresh data.
    """
    return PATCH_MAX_TS is None


HMMR_MIN_MATCHES_BUILD = 30
ALL_MIN_MATCHES_BUILD = 50
# Higher-rank slices have fewer matches, so we relax the build-stats floor.
# Eternus is rare enough that even floor=10 may return very thin data on some
# heroes — the page handles empty slices gracefully.
ASC_MIN_MATCHES_BUILD = 15
ETER_MIN_MATCHES_BUILD = 10


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


# --- global request pacing ---------------------------------------------
# api.deadlock-api.com allows 200 req/min per anonymous IP. Uncapped worker
# pools burst well past that: GitHub runners get Cloudflare-banned after
# ~50 requests and every subsequent call fails instantly (observed
# fetched=52/errors=1354 in CI before this limiter existed). One shared
# pacer keeps ALL fetch() callers — analytics, builds, counters — at a
# safe aggregate rate no matter how many threads they use. Cached hits
# never touch the pacer, so warm runs stay fast.
_PACE_MIN_INTERVAL = 0.35          # ~170 req/min, headroom under the 200 cap
_pace_lock = threading.Lock()
_pace_next_slot = [0.0]            # monotonic time the next request may fire
_RETRIABLE_HTTP = {403, 429, 503}  # Cloudflare throttle/challenge responses
_BACKOFF_S = (10, 30, 60)          # per-attempt cooldown before retrying


def _pace() -> None:
    """Block until this thread may issue the next HTTP request.

    Sleeping while holding the lock is deliberate: it serializes slot
    reservation so N workers collectively never exceed the global rate.
    """
    with _pace_lock:
        now = time.monotonic()
        wait = _pace_next_slot[0] - now
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _pace_next_slot[0] = now + _PACE_MIN_INTERVAL


def _pace_penalty(seconds: float) -> None:
    """Push the global next-request slot out — called after a 429/403 so
    every worker backs off together instead of piling onto a tripped
    rate limit one after another."""
    with _pace_lock:
        _pace_next_slot[0] = max(_pace_next_slot[0], time.monotonic() + seconds)


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

    Live requests go through the global pacer above, and rate-limit
    responses (429/403/503) get up to three retries with escalating
    shared cooldowns before counting as an error.
    """
    if dest.exists() and dest.stat().st_size >= 2:
        if ttl is None:
            return dest, "cached"
        age = time.time() - dest.stat().st_mtime
        if age < ttl:
            return dest, "cached"
        # Stale — fall through to re-fetch
    last_err: Exception | None = None
    for cooldown in (0,) + _BACKOFF_S:
        if cooldown and isinstance(last_err, urllib.error.HTTPError) \
                and last_err.code in _RETRIABLE_HTTP:
            # Tripped the rate limit: push everyone's next slot out so the
            # pool doesn't pile onto a limit that just rejected us.
            _pace_penalty(cooldown)
        _pace()
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
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code not in _RETRIABLE_HTTP:
                break
        except Exception as e:
            # Network hiccup — one paced retry via the loop is fine.
            last_err = e
    # Failure: keep the stale file (if any) rather than blowing it away.
    # Caller sees "error" so it can log + continue.
    return dest, f"error: {last_err}"


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
    # ALWAYS overwrite: the root mirror used to be written only when
    # missing, which froze it forever inside the persisted CI cache — a
    # hero or item added in a later patch would never become visible to
    # the root readers (batch_fetch_builds, batch_fetch_counters, and the
    # per-hero item metadata). Each patch's bootstrap now stamps its own
    # snapshot into the root, so within one patch's pipeline pass the
    # root always reflects that patch.
    (CACHE / "heroes.json").write_bytes((PATCH_CACHE / "heroes.json").read_bytes())
    (CACHE / "items.json").write_bytes((PATCH_CACHE / "items.json").read_bytes())

    with open(PATCH_CACHE / "heroes.json", encoding="utf-8") as f:
        heroes = json.load(f)
    playable = [h for h in heroes
                if h.get("player_selectable", False)
                and not h.get("disabled", False)
                and not h.get("in_development", False)]
    payload = [{"id": h["id"], "name": h["name"], "class_name": h["class_name"]}
               for h in playable]
    dest = PATCH_CACHE / "playable_heroes.json"
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    # Mirror to legacy global path for backwards compat — always
    # overwritten for the same staleness reason as the asset mirrors above.
    with open(CACHE / "playable_heroes.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  playable heroes: {len(playable)} -> {dest.relative_to(PATCH_CACHE.parent.parent)}")


def hero_urls(hid: int) -> list[tuple[str, Path]]:
    base = "https://api.deadlock-api.com/v1/analytics"
    common = TIME_BOUNDS_QS
    return [
        # All MMR — no badge filter, full population
        (f"{base}/item-stats?hero_id={hid}&{common}&min_matches=20",
         HERO_DATA / f"itemstats_all_{hid}.json"),
        (f"{base}/item-permutation-stats?hero_id={hid}&comb_size=2&{common}",
         HERO_DATA / f"perm2_all_{hid}.json"),
        (f"{base}/hero-build-stats/{hid}?{common}&min_matches={ALL_MIN_MATCHES_BUILD}",
         HERO_DATA / f"buildstats_all_{hid}.json"),
        (f"{base}/ability-order-stats?hero_id={hid}&{common}&min_matches=50",
         HERO_DATA / f"abilityorder_all_{hid}.json"),
        # Phantom 1+ (high MMR)
        (f"{base}/item-stats?hero_id={hid}&{common}&min_matches=20&min_average_badge={HMMR_BADGE}",
         HERO_DATA / f"itemstats_hmmr_{hid}.json"),
        (f"{base}/item-permutation-stats?hero_id={hid}&comb_size=2&{common}&min_average_badge={HMMR_BADGE}",
         HERO_DATA / f"perm2_hmmr_{hid}.json"),
        (f"{base}/hero-build-stats/{hid}?{common}&min_matches={HMMR_MIN_MATCHES_BUILD}&min_average_badge={HMMR_BADGE}",
         HERO_DATA / f"buildstats_hmmr_{hid}.json"),
        (f"{base}/ability-order-stats?hero_id={hid}&{common}&min_matches=20&min_average_badge={HMMR_BADGE}",
         HERO_DATA / f"abilityorder_hmmr_{hid}.json"),
        # Ascendant 1+ — relaxed item/build floors since the slice is sparser
        (f"{base}/item-stats?hero_id={hid}&{common}&min_matches=10&min_average_badge={ASCENDANT_BADGE}",
         HERO_DATA / f"itemstats_asc_{hid}.json"),
        (f"{base}/item-permutation-stats?hero_id={hid}&comb_size=2&{common}&min_average_badge={ASCENDANT_BADGE}",
         HERO_DATA / f"perm2_asc_{hid}.json"),
        (f"{base}/hero-build-stats/{hid}?{common}&min_matches={ASC_MIN_MATCHES_BUILD}&min_average_badge={ASCENDANT_BADGE}",
         HERO_DATA / f"buildstats_asc_{hid}.json"),
        (f"{base}/ability-order-stats?hero_id={hid}&{common}&min_matches=10&min_average_badge={ASCENDANT_BADGE}",
         HERO_DATA / f"abilityorder_asc_{hid}.json"),
        # Eternus 1+ — floors relaxed further; expect empty data on niche heroes
        (f"{base}/item-stats?hero_id={hid}&{common}&min_matches=5&min_average_badge={ETERNUS_BADGE}",
         HERO_DATA / f"itemstats_eter_{hid}.json"),
        (f"{base}/item-permutation-stats?hero_id={hid}&comb_size=2&{common}&min_average_badge={ETERNUS_BADGE}",
         HERO_DATA / f"perm2_eter_{hid}.json"),
        (f"{base}/hero-build-stats/{hid}?{common}&min_matches={ETER_MIN_MATCHES_BUILD}&min_average_badge={ETERNUS_BADGE}",
         HERO_DATA / f"buildstats_eter_{hid}.json"),
        (f"{base}/ability-order-stats?hero_id={hid}&{common}&min_matches=5&min_average_badge={ETERNUS_BADGE}",
         HERO_DATA / f"abilityorder_eter_{hid}.json"),
    ]


def main() -> None:
    # Old patches are frozen — once their analytics aggregates are on
    # disk they don't change. Set ttl=None for non-active patches so
    # every existing file is treated as a permanent cache hit. The
    # active patch still uses the 2h analytics TTL so cron runs pick
    # up fresh aggregates.
    active = is_active_patch()
    ttl = None if not active else DEFAULT_TTL
    print(f"[1/3] Bootstrapping asset metadata for {PATCH_ID} ({PATCH_TITLE}) "
          f"[{'ACTIVE — using 2h TTL' if active else 'CLOSED — using cache forever'}] …")
    bootstrap_assets()

    fetch(f"https://api.deadlock-api.com/v1/analytics/hero-stats?{TIME_BOUNDS_QS}",
          PATCH_CACHE / "hero_stats_all.json", ttl=ttl)
    fetch(f"https://api.deadlock-api.com/v1/analytics/hero-stats?{TIME_BOUNDS_QS}&min_average_badge={HMMR_BADGE}",
          PATCH_CACHE / "hero_stats_hmmr.json", ttl=ttl)
    fetch(f"https://api.deadlock-api.com/v1/analytics/hero-stats?{TIME_BOUNDS_QS}&min_average_badge={ASCENDANT_BADGE}",
          PATCH_CACHE / "hero_stats_asc.json", ttl=ttl)
    fetch(f"https://api.deadlock-api.com/v1/analytics/hero-stats?{TIME_BOUNDS_QS}&min_average_badge={ETERNUS_BADGE}",
          PATCH_CACHE / "hero_stats_eter.json", ttl=ttl)

    print("[2/3] Building per-hero job list …")
    with open(CACHE / "playable_heroes.json", encoding="utf-8") as _f:
        heroes = json.load(_f)
    all_jobs: list[tuple[str, Path]] = []
    for h in heroes:
        all_jobs.extend(hero_urls(h["id"]))
    print(f"  {len(all_jobs)} endpoints across {len(heroes)} heroes")

    print("[3/3] Fetching …")
    t0 = time.time()
    cached = ok = stale = err = 0
    # Worker count only sets concurrency-vs-latency; the global pacer in
    # fetch() is what enforces the 200 req/min IP cap. Cold analytics
    # queries run ~3s server-side, so 6 workers ≈ 2 req/s — still under
    # the pacer's ceiling.
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch, u, d, 25, ttl): (u, d) for u, d in all_jobs}
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
