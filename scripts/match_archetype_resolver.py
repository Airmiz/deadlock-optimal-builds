"""Resolve match-only ability-priority archetypes into concrete item builds.

Match-only archetypes (introduced in §3.6) are max-order ability ladders
observed in raw `/v1/analytics/ability-order-stats` data that have no
published Steam template. The page falls back to the recommended ILP
build for these, but ideally we'd surface the items that the actual
players running this priority buy.

This module bridges the gap by:

  1. Pulling top Warden candidates from /v1/analytics/scoreboards/players
     for the hero+slice the archetype belongs to.
  2. Querying each candidate's ability-order-stats and matching the
     archetype's max-order fingerprint against their observed
     sequences. Every account whose data contains at least one
     matching sequence gets collected.
  3. Issuing a single /v1/analytics/item-stats query with
     account_ids=[all matched accounts] to get aggregated item stats
     across only those players' matches.
  4. Aggregating into a 16-slot build using the same lift-weighted
     scheme as method_build_replication.

Results are cached per (patch_id, hero_id, slice, fingerprint) in
cache/match_archetype_resolutions/. Cache is immutable — once a
patch's data is settled (~24h after release), an archetype's
resolution doesn't change.

Run as a module to resolve a single archetype:

    python scripts/match_archetype_resolver.py --hero 25 --slice eter \\
        --fingerprint 2702908623,2656490109,2751689917 --patch patch_129989

Or as a bulk pass (called from run_all_heroes.py via a new flag):

    python scripts/match_archetype_resolver.py --bulk --patch patch_129989
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import (  # noqa: E402
    ROOT, CACHE, PATCH_REGISTRY, PATCH_CACHE,
    HMMR_BADGE, ASCENDANT_BADGE, ETERNUS_BADGE,
)
from batch_fetch import _HEADERS, fetch as _http_fetch  # noqa: E402


RESOLUTIONS_DIR = CACHE / "match_archetype_resolutions"
RESOLUTIONS_DIR.mkdir(parents=True, exist_ok=True)

SLICE_BADGE = {"all": None, "hmmr": HMMR_BADGE, "asc": ASCENDANT_BADGE, "eter": ETERNUS_BADGE}

# Per-slice scoreboard top-N to scan. Eternus+ is sparse so a deeper
# sweep is worth the API cost; all-MMR rarely needs more than the top 100.
SLICE_CANDIDATE_DEPTH = {"all": 100, "hmmr": 300, "asc": 500, "eter": 1500}

# Minimum matches in a player's sequence for it to count as a "match"
# against the archetype fingerprint. Below this we treat the player as
# an incidental visitor to the fingerprint rather than a representative.
MIN_PLAYER_SEQUENCE_MATCHES = 3


def _api_get(url: str, retries: int = 3, backoff: float = 8.0) -> object:
    """Resilient JSON GET with backoff on Cloudflare 403/429."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
                continue
            return []
        except Exception:
            return []


def _max_order_fingerprint(seq: list[int], k: int = 3) -> tuple[int, ...]:
    """Same algorithm as build_page_data._max_order_from_sequence.

    Returns the first k abilities ordered by when their tier-3 (4th
    occurrence in the 16-step ladder) lands.
    """
    counts: dict[int, int] = {}
    max_position: dict[int, int] = {}
    for i, aid in enumerate(seq or []):
        counts[aid] = counts.get(aid, 0) + 1
        if counts[aid] == 4:
            max_position[aid] = i
    ordered = sorted(max_position.items(), key=lambda x: x[1])
    return tuple(aid for aid, _ in ordered)[:k]


def _cache_path(patch_id: str, hero_id: int, slice_label: str,
                fingerprint: tuple[int, ...]) -> Path:
    h = hashlib.sha1(",".join(str(a) for a in fingerprint).encode()).hexdigest()[:10]
    return RESOLUTIONS_DIR / patch_id / f"{hero_id}_{slice_label}_{h}.json"


def _scoreboard_candidates(hero_id: int, bounds_qs: str,
                           badge: int | None, depth: int,
                           sort_by: str = "matches") -> list[int]:
    badge_q = f"&min_average_badge={badge}" if badge is not None else ""
    url = (
        "https://api.deadlock-api.com/v1/analytics/scoreboards/players"
        f"?hero_ids={hero_id}"
        f"&{bounds_qs}"
        f"{badge_q}"
        f"&sort_by={sort_by}&sort_direction=desc"
        f"&limit={depth}&min_matches=5"
    )
    rows = _api_get(url)
    return [r["account_id"] for r in rows if isinstance(r, dict) and r.get("account_id")]


def _account_sequences(hero_id: int, account_id: int, bounds_qs: str,
                       badge: int | None) -> list[dict]:
    badge_q = f"&min_average_badge={badge}" if badge is not None else ""
    url = (
        "https://api.deadlock-api.com/v1/analytics/ability-order-stats"
        f"?hero_id={hero_id}"
        f"&{bounds_qs}"
        f"{badge_q}"
        f"&account_ids={account_id}"
        "&min_matches=1"
    )
    return _api_get(url) or []


def _account_items(hero_id: int, account_ids: list[int], bounds_qs: str,
                   badge: int | None) -> list[dict]:
    """Single aggregated item-stats query for a population of accounts."""
    if not account_ids:
        return []
    badge_q = f"&min_average_badge={badge}" if badge is not None else ""
    ids_q = ",".join(str(a) for a in account_ids)
    url = (
        "https://api.deadlock-api.com/v1/analytics/item-stats"
        f"?hero_id={hero_id}"
        f"&{bounds_qs}"
        f"{badge_q}"
        f"&account_ids={ids_q}"
        "&min_matches=1"
    )
    return _api_get(url) or []


def resolve_archetype(
    hero_id: int,
    slice_label: str,
    fingerprint: tuple[int, ...],
    patch_id: str,
    use_cache: bool = True,
    candidate_workers: int = 4,
    verbose: bool = False,
) -> dict:
    """Resolve a single match-only archetype to a concrete item list.

    Returns:
      {
        "fingerprint": [...],
        "candidates_scanned": N,
        "matching_accounts": [...],
        "matching_account_count": M,
        "total_matches": T,
        "total_wins": W,
        "mean_win_rate": ...,
        "items": [item_dict, ...],  # 16-slot bundle, slot-decorated
        "from_cache": bool,
      }
    """
    cache_path = _cache_path(patch_id, hero_id, slice_label, fingerprint)
    if use_cache and cache_path.exists() and cache_path.stat().st_size >= 2:
        try:
            with open(cache_path, encoding="utf-8") as f:
                cached = json.load(f)
            cached["from_cache"] = True
            return cached
        except Exception:
            pass

    _pmeta = PATCH_REGISTRY[patch_id]
    bounds_qs = f"min_unix_timestamp={_pmeta['min_ts']}"
    if _pmeta.get("max_ts"):
        # Closed patch — bound the window so archetypes stay era-pure.
        bounds_qs += f"&max_unix_timestamp={_pmeta['max_ts']}"
    badge = SLICE_BADGE[slice_label]
    depth = SLICE_CANDIDATE_DEPTH[slice_label]
    target_fp = tuple(fingerprint)

    if verbose:
        print(f"  resolving hero={hero_id} slice={slice_label} fp={target_fp}")
        print(f"  scoreboard depth={depth} badge={badge}")

    # Pool candidates from two sort orderings — "by matches" catches
    # high-volume players, "by winrate" catches outlier-WR specialists
    # like the 86.96%/23-match Warden case. Dedupe across both lists.
    matches_candidates = _scoreboard_candidates(hero_id, bounds_qs, badge, depth, sort_by="matches")
    winrate_candidates = _scoreboard_candidates(hero_id, bounds_qs, badge, depth, sort_by="winrate")
    candidates = list(dict.fromkeys(matches_candidates + winrate_candidates))
    if verbose:
        print(f"  {len(candidates)} unique candidates ({len(matches_candidates)} by matches, "
              f"{len(winrate_candidates)} by winrate)")

    matching_accounts: list[int] = []
    total_matches = 0
    total_wins = 0
    t0 = time.time()

    def _check_account(aid: int) -> tuple[int, list[dict]]:
        seqs = _account_sequences(hero_id, aid, bounds_qs, badge)
        hits = [s for s in seqs
                if _max_order_fingerprint(s.get("abilities") or []) == target_fp
                and s.get("matches", 0) >= MIN_PLAYER_SEQUENCE_MATCHES]
        return aid, hits

    # 4 workers stays well under Cloudflare's 200/min IP cap when paired
    # with the natural ~250ms response time.
    with ThreadPoolExecutor(max_workers=candidate_workers) as pool:
        futs = {pool.submit(_check_account, c): c for c in candidates}
        for i, fut in enumerate(as_completed(futs), 1):
            aid, hits = fut.result()
            if hits:
                matching_accounts.append(aid)
                for h in hits:
                    total_matches += h.get("matches", 0)
                    total_wins += h.get("wins", 0)
            if verbose and (i % 100 == 0 or i == len(candidates)):
                print(f"    {i}/{len(candidates)} checked  matched={len(matching_accounts)}  "
                      f"({time.time()-t0:.1f}s)")

    if verbose:
        print(f"  {len(matching_accounts)} accounts contribute to this archetype")

    # Fetch aggregated item-stats for the matched accounts. account_ids
    # is a list query — the API joins them into "matches involving any
    # of these accounts" which is the right scope for the bundle.
    items = _account_items(hero_id, matching_accounts, bounds_qs, badge)

    # Aggregate into a slot-decorated 16-item bundle. Score = personal
    # pick rate (matches with item / max matches across all items for
    # this player population) weighted by raw WR. Same shape as the
    # joint_archetypes "items" dict so the page can render uniformly.
    items_meta_path = CACHE / "items.json"
    with open(items_meta_path, encoding="utf-8") as f:
        items_by_id = {i["id"]: i for i in json.load(f)}
    most_matches = max((s.get("matches", 0) for s in items), default=1) or 1

    def _phase_of(buy_s: float) -> str:
        if buy_s < 750: return "early"
        if buy_s < 1500: return "mid"
        return "late"

    decorated = []
    for s in items:
        it = items_by_id.get(s.get("item_id"))
        if not it or it.get("type") != "upgrade" or it.get("item_slot_type") not in ("weapon", "vitality", "spirit"):
            continue
        if s.get("matches", 0) <= 0:
            continue
        wr = s["wins"] / s["matches"]
        pick_rate_pop = s["matches"] / most_matches
        sell_s = s.get("avg_sell_time_s") or 0
        decorated.append({
            "item_id": s["item_id"],
            "name": it["name"],
            "category": it["item_slot_type"],
            "tier": it["item_tier"],
            "cost": it["cost"],
            "matches": s["matches"],
            "wins": s["wins"],
            "win_rate": round(wr, 4),
            "personal_pick_rate": round(pick_rate_pop, 4),
            "avg_buy_time_s": round(s.get("avg_buy_time_s", 0), 1),
            "phase": _phase_of(s.get("avg_buy_time_s", 0)),
            "avg_sell_time_s": round(sell_s, 1) if sell_s else None,
            "is_active": bool(it.get("is_active_item")),
            "imbue": it.get("imbue"),
            # personal-pick-rate-weighted score; emphasizes items the
            # population reliably buys, with high WR amplifying further
            "score": round(pick_rate_pop * wr, 4),
        })
    decorated.sort(key=lambda c: -c["score"])

    # 16-slot bundle following the same category constraints as the ILP:
    # take top-4 per category by score, then 4 flex picks.
    from collections import defaultdict
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for c in decorated:
        by_cat[c["category"]].append(c)
    picks: list[dict] = []
    used: set[int] = set()
    for cat in ("weapon", "vitality", "spirit"):
        for c in by_cat[cat][:4]:
            picks.append({**c, "slot": cat})
            used.add(c["item_id"])
    flex_pool = [c for c in decorated if c["item_id"] not in used][:4]
    for c in flex_pool:
        picks.append({**c, "slot": "flex"})

    result = {
        "fingerprint": list(target_fp),
        "patch_id": patch_id,
        "hero_id": hero_id,
        "slice": slice_label,
        "candidates_scanned": len(candidates),
        "matching_accounts": matching_accounts,
        "matching_account_count": len(matching_accounts),
        "total_matches_in_fingerprint": total_matches,
        "total_wins_in_fingerprint": total_wins,
        "mean_win_rate_in_fingerprint": round(total_wins / total_matches, 4) if total_matches else None,
        "items": picks,
        "resolved_at_unix": int(time.time()),
        "from_cache": False,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def _parse_fingerprint(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in s.split(",") if x.strip())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hero", type=int, required=False)
    ap.add_argument("--slice", choices=tuple(SLICE_BADGE), required=False)
    ap.add_argument("--fingerprint", help="Comma-separated ability_ids of the max-order fingerprint")
    ap.add_argument("--patch", default="patch_146261")
    ap.add_argument("--bulk", action="store_true",
                    help="Resolve every match-only archetype for every hero in the patch")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.bulk:
        _bulk(args.patch, use_cache=not args.no_cache, verbose=not args.quiet)
        return

    if not (args.hero and args.slice and args.fingerprint):
        ap.error("specify --hero, --slice, and --fingerprint OR --bulk")
    fp = _parse_fingerprint(args.fingerprint)
    result = resolve_archetype(
        args.hero, args.slice, fp, args.patch,
        use_cache=not args.no_cache,
        verbose=not args.quiet,
    )
    print(json.dumps({
        "matching_accounts": result["matching_account_count"],
        "total_matches": result["total_matches_in_fingerprint"],
        "mean_wr": result["mean_win_rate_in_fingerprint"],
        "top_items": [
            f"{p['name']} ({p['category']} T{p['tier']}, {p['matches']}m WR {p['win_rate']*100:.1f}%)"
            for p in result["items"][:8]
        ],
        "from_cache": result["from_cache"],
    }, indent=2))


def _bulk(patch_id: str, use_cache: bool = True, verbose: bool = True) -> None:
    """Resolve every match-only archetype across all heroes for a patch."""
    heroes_out_dir = ROOT / "heroes" / patch_id
    files = sorted(heroes_out_dir.glob("*_build.json"))
    print(f"Bulk resolve: patch {patch_id}, {len(files)} hero JSONs")

    # Build the full list of (hero, slice, fingerprint) jobs first so we
    # can report progress.
    SLICE_MAP = {"all_mmr": "all", "high_mmr": "hmmr",
                 "ascendant_plus": "asc", "eternus_plus": "eter"}
    jobs: list[tuple[int, str, tuple[int, ...]]] = []
    template_fp_by_hs: dict[tuple[int, str], set[tuple]] = {}
    for f in files:
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        hid = d["hero"]["id"]
        for src_label, short in SLICE_MAP.items():
            tpl_archs = (d["items"].get(src_label) or {}).get("joint_archetypes") or []
            tpl_fps = {tuple(a.get("fingerprint_ability_ids") or []) for a in tpl_archs}
            template_fp_by_hs[(hid, short)] = tpl_fps
            full_orders = (d["ability_orders"].get(src_label) or {}).get("best_full_orders") or []
            seen_fps: set[tuple] = set()
            for r in full_orders:
                fp = _max_order_fingerprint(r.get("sequence_ids") or [])
                if not fp or len(fp) < 3 or fp in tpl_fps or fp in seen_fps:
                    continue
                seen_fps.add(fp)
                jobs.append((hid, short, fp))

    print(f"  {len(jobs)} match-only archetypes across all heroes / slices")
    if not jobs:
        return

    t0 = time.time()
    for i, (hid, slice_label, fp) in enumerate(jobs, 1):
        try:
            result = resolve_archetype(hid, slice_label, fp, patch_id,
                                        use_cache=use_cache, verbose=False)
            if verbose:
                cache_flag = "C" if result.get("from_cache") else "N"
                print(f"  [{i:>4}/{len(jobs)}] [{cache_flag}] hero={hid} slice={slice_label} "
                      f"matched={result['matching_account_count']} "
                      f"matches={result['total_matches_in_fingerprint']} "
                      f"({time.time()-t0:.1f}s)")
        except Exception as e:
            print(f"  [{i:>4}/{len(jobs)}] hero={hid} slice={slice_label} FAILED: {e}")

    print(f"\nDone in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
