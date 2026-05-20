"""Extract account 54456193's actual Warden item preferences.

The deadlock-api has no per-match endpoint, so we can't pull the exact
items from the 23 matches with the Last-Stand-first ability ladder.
But `account_ids=X` is a valid filter on every aggregated analytics
endpoint, so we can pull the player's *aggregate* item-stats restricted
to just their Warden Eternus+ matches in patch_129989. That covers all
114 of their Warden games at this rank (the 23-match sequence is a
subset of those).

We also overlay the population baseline to flag items they buy
significantly more or less than the average Eternus+ Warden, which is
the closest signal we have to "what's distinctive about their build".

Outputs to stdout and saves a JSON dump to
analysis/warden_player_54456193_build.json.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from batch_fetch import _HEADERS  # noqa: E402
from _paths import PATCH_REGISTRY, ETERNUS_BADGE  # noqa: E402


ACCOUNT_ID = 54456193
HERO_ID = 25  # Warden
PATCH_ID = "patch_129989"
PATCH_MIN_TS = PATCH_REGISTRY[PATCH_ID]["min_ts"]


def _get_json(url: str, retries: int = 4, backoff: float = 30.0) -> object:
    """Resilient GET with Cloudflare-aware backoff."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < retries - 1:
                wait = backoff * (attempt + 1)
                print(f"  HTTP {e.code} — waiting {wait:.0f}s then retrying...")
                time.sleep(wait)
                continue
            raise


def fetch_player_items(badge: int | None) -> list:
    badge_q = f"&min_average_badge={badge}" if badge is not None else ""
    url = (
        f"https://api.deadlock-api.com/v1/analytics/item-stats"
        f"?hero_id={HERO_ID}"
        f"&account_ids={ACCOUNT_ID}"
        f"&min_unix_timestamp={PATCH_MIN_TS}"
        f"{badge_q}"
        f"&min_matches=1"
    )
    return _get_json(url) or []


def fetch_population_items(badge: int | None) -> dict[int, dict]:
    badge_q = f"&min_average_badge={badge}" if badge is not None else ""
    url = (
        f"https://api.deadlock-api.com/v1/analytics/item-stats"
        f"?hero_id={HERO_ID}"
        f"&min_unix_timestamp={PATCH_MIN_TS}"
        f"{badge_q}"
        f"&min_matches=20"
    )
    rows = _get_json(url) or []
    return {r["item_id"]: r for r in rows}


def fetch_player_pairs(badge: int | None) -> list:
    badge_q = f"&min_average_badge={badge}" if badge is not None else ""
    url = (
        f"https://api.deadlock-api.com/v1/analytics/item-permutation-stats"
        f"?hero_id={HERO_ID}"
        f"&account_ids={ACCOUNT_ID}"
        f"&comb_size=2"
        f"&min_unix_timestamp={PATCH_MIN_TS}"
        f"{badge_q}"
    )
    return _get_json(url) or []


def load_item_metadata() -> dict[int, dict]:
    cache_root = Path(__file__).resolve().parent.parent / "cache"
    with open(cache_root / "items.json", encoding="utf-8") as f:
        return {i["id"]: i for i in json.load(f)}


def main() -> None:
    items_meta = load_item_metadata()
    print(f"Extracting Warden build for account {ACCOUNT_ID} on {PATCH_ID}")

    # Try Eternus+ slice first (most relevant — that's where the 23-match
    # sequence lives). Fall back to no-badge if the slice is too sparse.
    for label, badge in (("Eternus+", ETERNUS_BADGE), ("all-mmr", None)):
        print(f"\n=== {label} ===")
        try:
            player_items = fetch_player_items(badge)
        except Exception as e:
            print(f"  fetch failed: {e}")
            continue
        if not player_items:
            print(f"  no items in {label} slice; trying next")
            continue
        # Sum total matches across all rows to see how many matches we have visibility into
        # (item-stats rows = (item, account, time-window) tuples; player has multiple items per match)
        n_distinct_items = len(player_items)
        total_match_appearances = sum(s.get("matches", 0) for s in player_items)
        most_picked_matches = max(s.get("matches", 0) for s in player_items)
        print(f"  {n_distinct_items} distinct items bought across player's matches")
        print(f"  Most-picked item appears in {most_picked_matches} matches")

        try:
            pop = fetch_population_items(badge)
        except Exception as e:
            print(f"  population fetch failed: {e}")
            pop = {}

        # Annotate each pick with metadata + population delta
        rows = []
        for s in player_items:
            it = items_meta.get(s["item_id"])
            if not it or it.get("type") != "upgrade":
                continue
            pop_row = pop.get(s["item_id"])
            player_wr = s["wins"] / s["matches"] if s["matches"] else 0
            pop_wr = pop_row["wins"] / pop_row["matches"] if pop_row and pop_row["matches"] else None
            pop_pick_rate = None
            # crude personal vs population pick-rate ratio: this item's matches / max(matches) for player
            personal_pick_rate = s["matches"] / max(1, most_picked_matches)
            rows.append({
                "item_id": s["item_id"],
                "name": it.get("name", "?"),
                "tier": it.get("item_tier"),
                "cost": it.get("cost"),
                "category": it.get("item_slot_type"),
                "is_active": bool(it.get("is_active_item")),
                "imbue": it.get("imbue"),
                "player_matches": s["matches"],
                "player_wins": s["wins"],
                "player_wr": round(player_wr, 4),
                "personal_pick_rate": round(personal_pick_rate, 3),
                "pop_wr": round(pop_wr, 4) if pop_wr is not None else None,
                "wr_delta_pp_vs_pop": round((player_wr - pop_wr) * 100, 2) if pop_wr is not None else None,
                "avg_buy_time_s": round(s.get("avg_buy_time_s", 0), 1),
            })
        rows.sort(key=lambda r: -r["personal_pick_rate"])

        # --- Render ---
        print(f"\n  Most-bought items (sorted by personal pick rate):")
        print(f"  {'#':>2}  {'Item':30s} {'cat':9s} {'tier':5s} {'pick%':>6s} "
              f"{'p_wr':>6s} {'pop_wr':>7s} {'dpp':>6s} {'buyAt':>7s}")
        for i, r in enumerate(rows[:25], 1):
            pop_wr_s = "--" if r["pop_wr"] is None else f"{r['pop_wr']*100:.1f}%"
            dpp_s = "--" if r["wr_delta_pp_vs_pop"] is None else f"{r['wr_delta_pp_vs_pop']:+.1f}"
            buy_min = r["avg_buy_time_s"] / 60
            print(f"  {i:>2}  {r['name'][:28]:30s} {r['category'][:8]:9s} t{r['tier']}    "
                  f"{r['personal_pick_rate']*100:>5.1f}% "
                  f"{r['player_wr']*100:>5.1f}% "
                  f"{pop_wr_s:>7s} "
                  f"{dpp_s:>6s} "
                  f"{buy_min:>5.1f}m")

        # --- Distinctive picks: items they pick way more than the population ---
        print(f"\n  Most distinctive picks (high personal pick rate, far from neutral lift):")
        distinctive = sorted(
            [r for r in rows if r['wr_delta_pp_vs_pop'] is not None and r['player_matches'] >= 10],
            key=lambda r: -(r['personal_pick_rate'] * abs(r['wr_delta_pp_vs_pop'] or 0)),
        )[:10]
        for r in distinctive:
            print(f"    {r['name']:30s} pick={r['personal_pick_rate']*100:.0f}%  "
                  f"p_wr={r['player_wr']*100:.1f}%  Δpp_vs_pop={r['wr_delta_pp_vs_pop']:+.2f}")

        # --- Save ---
        out_path = Path(__file__).resolve().parent / f"warden_player_{ACCOUNT_ID}_build.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({
                "account_id": ACCOUNT_ID,
                "hero_id": HERO_ID,
                "patch_id": PATCH_ID,
                "mmr_slice": label,
                "items_bought_across_matches": rows,
            }, f, indent=2)
        print(f"\n  Saved full data to {out_path.relative_to(out_path.parent.parent)}")
        return  # done at the first slice with data

    print("\nNo data found in any slice.")


if __name__ == "__main__":
    main()
