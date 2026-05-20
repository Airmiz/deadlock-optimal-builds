"""Windowed fetch helpers for the validation harness.

Wraps batch_fetch.fetch() to write into a separate cache namespace keyed
by (patch_id, min_ts, max_ts, mmr) so train/test queries don't clobber
production cache. Re-uses the same TTL + stale-fallback semantics.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _paths import ROOT, CACHE, BUILD_FILES, HMMR_BADGE, ASCENDANT_BADGE, ETERNUS_BADGE  # noqa: E402
from batch_fetch import fetch, TTL_ANALYTICS  # noqa: E402
from batch_fetch_builds import fetch_build  # noqa: E402

from windows import Window  # noqa: E402

WINDOW_CACHE = ROOT / "validation" / "window_cache"
WINDOW_CACHE.mkdir(parents=True, exist_ok=True)

API = "https://api.deadlock-api.com/v1/analytics"

# MMR slice label -> badge floor (None = no badge filter, all MMR)
SLICE_BADGE = {
    "all":  None,
    "hmmr": HMMR_BADGE,
    "asc":  ASCENDANT_BADGE,
    "eter": ETERNUS_BADGE,
}

# Per-slice sample-size floors mirroring the production pipeline. These
# are deliberately the same as build_hero_output's slice_specs so the
# harness validates the same code paths under the same constraints.
SLICE_FLOORS = {
    "all":  {"item": 500, "pair": 500, "build": 200, "ability": 200},
    "hmmr": {"item": 300, "pair": 200, "build": 100, "ability": 100},
    "asc":  {"item": 100, "pair": 100, "build":  50, "ability":  50},
    "eter": {"item":  30, "pair":  30, "build":  15, "ability":  15},
}


def window_dir(patch_id: str, win: Window) -> Path:
    p = WINDOW_CACHE / patch_id / f"{win.min_ts}_{win.max_ts}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _badge_param(mmr: str) -> str:
    badge = SLICE_BADGE[mmr]
    return f"&min_average_badge={badge}" if badge is not None else ""


def hero_stats_url(win: Window, mmr: str) -> str:
    return f"{API}/hero-stats?{win.as_query()}{_badge_param(mmr)}"


def item_stats_url(hid: int, win: Window, mmr: str, min_matches: int = 5) -> str:
    return (
        f"{API}/item-stats?hero_id={hid}&{win.as_query()}"
        f"&min_matches={min_matches}{_badge_param(mmr)}"
    )


def pair_stats_url(hid: int, win: Window, mmr: str) -> str:
    return (
        f"{API}/item-permutation-stats?hero_id={hid}&comb_size=2"
        f"&{win.as_query()}{_badge_param(mmr)}"
    )


def build_stats_url(hid: int, win: Window, mmr: str, min_matches: int = 5) -> str:
    return (
        f"{API}/hero-build-stats/{hid}?{win.as_query()}"
        f"&min_matches={min_matches}{_badge_param(mmr)}"
    )


def hero_stats_path(patch_id: str, win: Window, mmr: str) -> Path:
    return window_dir(patch_id, win) / f"hero_stats_{mmr}.json"


def item_stats_path(patch_id: str, win: Window, mmr: str, hid: int) -> Path:
    return window_dir(patch_id, win) / f"itemstats_{mmr}_{hid}.json"


def pair_stats_path(patch_id: str, win: Window, mmr: str, hid: int) -> Path:
    return window_dir(patch_id, win) / f"perm2_{mmr}_{hid}.json"


def build_stats_path(patch_id: str, win: Window, mmr: str, hid: int) -> Path:
    return window_dir(patch_id, win) / f"buildstats_{mmr}_{hid}.json"


def fetch_all(
    patch_id: str,
    windows: Iterable[Window],
    hero_ids: list[int],
    mmr_slices: list[str],
    include_pairs: bool = True,
    include_builds: bool = True,
    workers: int = 2,
) -> dict:
    """Fetch every (window × mmr × hero × endpoint) request.

    Returns a summary dict {cached, fetched, stale_kept, errors}. The data
    itself is written to disk in window_cache/<patch>/<window>/*.json so
    subsequent reads can use the file paths directly.

    Uses the same TTL semantics as the production fetcher (2h analytics),
    so re-running within the cache window returns instantly. Workers
    defaults to 2 (the harness fans out 4× more requests than the
    production fetcher because of the train/test split, so we lower
    concurrency to stay well under Cloudflare's per-IP rate limit).
    """
    jobs: list[tuple[str, Path]] = []
    for win in windows:
        for mmr in mmr_slices:
            # baseline hero-stats per (window, mmr)
            jobs.append((hero_stats_url(win, mmr), hero_stats_path(patch_id, win, mmr)))
            for hid in hero_ids:
                jobs.append((
                    item_stats_url(hid, win, mmr),
                    item_stats_path(patch_id, win, mmr, hid),
                ))
                if include_pairs:
                    jobs.append((
                        pair_stats_url(hid, win, mmr),
                        pair_stats_path(patch_id, win, mmr, hid),
                    ))
                if include_builds:
                    jobs.append((
                        build_stats_url(hid, win, mmr),
                        build_stats_path(patch_id, win, mmr, hid),
                    ))

    t0 = time.time()
    summary = {"cached": 0, "fetched": 0, "stale_kept": 0, "errors": 0}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch, url, dest, 25, TTL_ANALYTICS): (url, dest)
                for url, dest in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            _, status = fut.result()
            if status == "cached":          summary["cached"] += 1
            elif status == "ok":            summary["fetched"] += 1
            elif status == "stale-keep":    summary["stale_kept"] += 1
            else:                            summary["errors"] += 1
            if i % 50 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} {summary} {time.time()-t0:.1f}s")
    summary["total_jobs"] = len(jobs)
    summary["elapsed_s"] = round(time.time() - t0, 1)
    return summary


def load_json(path: Path) -> list:
    """Load a windowed cache file. Returns [] if missing/empty/invalid."""
    if not path.exists() or path.stat().st_size < 2:
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def fetch_build_details(
    patch_id: str,
    windows: Iterable[Window],
    hero_ids: list[int],
    mmr_slices: list[str],
    workers: int = 6,
) -> dict:
    """Fetch per-build detail JSONs (cache/build_files/build_<id>.json) for
    every build_id that meets the per-slice floor in any train/test window.

    The Build Replication method scores by walking these per-build JSONs;
    without them present in BUILD_FILES the method returns empty picks.
    Build details are immutable (per batch_fetch_builds.fetch_build), so
    they're cached forever and only fetched on first encounter.
    """
    needed: set[int] = set()
    for win in windows:
        for mmr in mmr_slices:
            for hid in hero_ids:
                rows = load_json(build_stats_path(patch_id, win, mmr, hid))
                floor = SLICE_FLOORS[mmr]["build"]
                for b in rows:
                    if b.get("matches", 0) >= floor:
                        bid = b.get("hero_build_id")
                        if bid:
                            needed.add(bid)
    missing = [bid for bid in needed if not (BUILD_FILES / f"build_{bid}.json").exists()
               or (BUILD_FILES / f"build_{bid}.json").stat().st_size < 100]
    if not missing:
        return {"needed": len(needed), "missing": 0, "fetched": 0, "errors": 0}

    t0 = time.time()
    results = {"needed": len(needed), "missing": len(missing), "fetched": 0,
               "errors": 0, "cached": 0}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch_build, bid): bid for bid in missing}
        for i, fut in enumerate(as_completed(futs), 1):
            _, status = fut.result()
            if status == "ok":          results["fetched"] += 1
            elif status == "cached":    results["cached"] += 1
            else:                        results["errors"] += 1
            if i % 50 == 0 or i == len(missing):
                print(f"  build details {i}/{len(missing)} {results} {time.time()-t0:.1f}s")
    results["elapsed_s"] = round(time.time() - t0, 1)
    return results


def hero_baseline(patch_id: str, win: Window, mmr: str, hid: int) -> dict | None:
    """Return {wins, matches, players, win_rate} for a hero in a window."""
    rows = load_json(hero_stats_path(patch_id, win, mmr))
    row = next((r for r in rows if r.get("hero_id") == hid), None)
    if not row or not row.get("matches"):
        return None
    return {
        "wins": row["wins"],
        "matches": row["matches"],
        "players": row.get("players", 0),
        "win_rate": row["wins"] / row["matches"],
    }
