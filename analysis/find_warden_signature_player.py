"""Find the unique account behind the 86.96% WR Warden ability sequence.

The /v1/analytics/ability-order-stats endpoint aggregates by sequence and
strips account_ids in the public response. To resolve "who is the single
player who posted this exact ladder", we:

  1. Pull the top-N Warden players from /v1/analytics/scoreboards/players
     (sorted by total Warden matches in the active patch).
  2. For each candidate, re-query ability-order-stats with
     account_ids=<candidate>, which returns the candidate's per-sequence
     stats only.
  3. Walk the candidate's sequences for an exact match to the 16-step
     target ladder with the right match count + WR.

Target (from the page's display):

    Alchemical Flask (id 2656490109)
    Willpower         (id 2751689917)
    Binding Word      (id 1656913918)
    Last Stand x4     (id 2702908623)
    Alchemical Flask x3
    Willpower x3
    Binding Word x3
    -> 23 matches, 86.96% WR (20W/3L), 1 unique player

Run:  python analysis/find_warden_signature_player.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from batch_fetch import _HEADERS  # noqa: E402
from _paths import (  # noqa: E402
    PATCH_REGISTRY, HMMR_BADGE, ASCENDANT_BADGE, ETERNUS_BADGE,
)


# --- Constants ------------------------------------------------------------

# Warden ability IDs (from cache/heroes.json + items.json)
ABILITY_ID = {
    "Alchemical Flask": 2656490109,
    "Willpower":        2751689917,
    "Binding Word":     1656913918,
    "Last Stand":       2702908623,
}
ID_TO_NAME = {v: k for k, v in ABILITY_ID.items()}

TARGET_SEQUENCE = (
    ABILITY_ID["Alchemical Flask"],
    ABILITY_ID["Willpower"],
    ABILITY_ID["Binding Word"],
    ABILITY_ID["Last Stand"],
    ABILITY_ID["Last Stand"],
    ABILITY_ID["Last Stand"],
    ABILITY_ID["Alchemical Flask"],
    ABILITY_ID["Willpower"],
    ABILITY_ID["Last Stand"],
    ABILITY_ID["Alchemical Flask"],
    ABILITY_ID["Alchemical Flask"],
    ABILITY_ID["Willpower"],
    ABILITY_ID["Willpower"],
    ABILITY_ID["Binding Word"],
    ABILITY_ID["Binding Word"],
    ABILITY_ID["Binding Word"],
)
TARGET_MATCHES = 23
TARGET_WINS = 20  # 86.96% of 23 rounds to 20W 3L

WARDEN_ID = 25
# Try both patches and a few MMR slices — the page surfaces this stat
# from whichever combination produced the "1 players" cell.
SEARCH_GRID = [
    ("patch_129989", ETERNUS_BADGE),
    ("patch_129989", ASCENDANT_BADGE),
    ("patch_129989", HMMR_BADGE),
    ("patch_129989", None),       # all-MMR
    ("patch_125825", ETERNUS_BADGE),
    ("patch_125825", ASCENDANT_BADGE),
    ("patch_125825", HMMR_BADGE),
    ("patch_125825", None),
]


# --- HTTP -----------------------------------------------------------------

def _get_json(url: str, timeout: int = 20) -> object:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch_top_warden_accounts(patch_min_ts: int, badge: int | None) -> list[int]:
    """Top Warden accounts for one (patch, MMR slice), sorted by matches."""
    badge_q = f"&min_average_badge={badge}" if badge is not None else ""
    url = (
        "https://api.deadlock-api.com/v1/analytics/scoreboards/players"
        f"?hero_ids={WARDEN_ID}"
        f"&min_unix_timestamp={patch_min_ts}"
        f"{badge_q}"
        f"&sort_by=matches&sort_direction=desc"
    )
    try:
        rows = _get_json(url)
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    return [r["account_id"] for r in rows if r.get("matches", 0) >= TARGET_MATCHES]


def fetch_ability_sequences_for_account(
    account_id: int, patch_min_ts: int, badge: int | None,
) -> list[dict]:
    """Per-sequence stats for one account on Warden in one (patch, MMR)."""
    badge_q = f"&min_average_badge={badge}" if badge is not None else ""
    url = (
        "https://api.deadlock-api.com/v1/analytics/ability-order-stats"
        f"?hero_id={WARDEN_ID}"
        f"&min_unix_timestamp={patch_min_ts}"
        f"{badge_q}"
        f"&account_ids={account_id}"
        "&min_matches=1"
    )
    try:
        return _get_json(url) or []
    except Exception:
        return []


# --- Matching -------------------------------------------------------------

def matches_target(row: dict, exact: bool = True) -> bool:
    """A candidate row matches if the full 16-step ladder is identical and
    the (matches, wins) counts line up. When `exact=False`, allow ±1 on
    match count to absorb minor data drift between when the page was
    rendered and now."""
    if tuple(row.get("abilities", [])) != TARGET_SEQUENCE:
        return False
    m = row.get("matches", 0)
    w = row.get("wins", 0)
    if exact:
        return m == TARGET_MATCHES and w == TARGET_WINS
    return abs(m - TARGET_MATCHES) <= 1 and abs(w - TARGET_WINS) <= 1


# --- Main -----------------------------------------------------------------

def search_one_slice(patch_id: str, badge: int | None) -> tuple[list, list]:
    patch_min_ts = PATCH_REGISTRY[patch_id]["min_ts"]
    label_badge = f"badge>={badge}" if badge else "all-mmr"
    print(f"\n--- {patch_id} ({label_badge}) ---")
    accounts = fetch_top_warden_accounts(patch_min_ts, badge)
    print(f"  {len(accounts)} candidates with >= {TARGET_MATCHES} Warden matches")
    if not accounts:
        return [], []

    found: list[tuple[int, dict]] = []
    near: list[tuple[int, dict]] = []
    t0 = time.time()

    def _check(account_id: int) -> tuple[int, list[dict]]:
        return account_id, fetch_ability_sequences_for_account(
            account_id, patch_min_ts, badge,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_check, a): a for a in accounts}
        for i, fut in enumerate(as_completed(futs), 1):
            account_id, rows = fut.result()
            for r in rows:
                if matches_target(r, exact=True):
                    found.append((account_id, r))
                elif matches_target(r, exact=False):
                    near.append((account_id, r))
            if i % 50 == 0 or i == len(accounts):
                print(f"    {i}/{len(accounts)} ({time.time()-t0:.1f}s)  "
                      f"exact={len(found)} near={len(near)}")
            if found:
                break
    return found, near


def main() -> None:
    print(f"Target sequence ({len(TARGET_SEQUENCE)} steps):")
    for i, aid in enumerate(TARGET_SEQUENCE, 1):
        print(f"  {i:>2}. {ID_TO_NAME[aid]}")
    print(f"Target stats: {TARGET_WINS}W / {TARGET_MATCHES - TARGET_WINS}L  "
          f"({TARGET_WINS/TARGET_MATCHES*100:.2f}% over {TARGET_MATCHES} matches)")

    all_found: list[tuple[str, str, int, dict]] = []
    all_near: list[tuple[str, str, int, dict]] = []
    for patch_id, badge in SEARCH_GRID:
        found, near = search_one_slice(patch_id, badge)
        slice_label = f"badge>={badge}" if badge else "all-mmr"
        for a, r in found:
            all_found.append((patch_id, slice_label, a, r))
        for a, r in near:
            all_near.append((patch_id, slice_label, a, r))
        if all_found:
            break  # found in earlier slice, stop scanning

    print()
    if all_found:
        for patch_id, slice_label, account_id, row in all_found:
            steam64 = account_id + 76561197960265728  # AccountID -> SteamID64
            print(f"FOUND in {patch_id} / {slice_label}:")
            print(f"  account_id        = {account_id}")
            print(f"  SteamID64         = {steam64}")
            print(f"  Steam profile     = https://steamcommunity.com/profiles/{steam64}")
            print(f"  Tracklock         = https://tracklock.gg/players/{account_id}")
            print(f"  Statlocker        = https://statlocker.gg/profile/{account_id}")
            print(f"  Stats             = {row['wins']}W / {row['matches'] - row['wins']}L "
                  f"({row['wins']/row['matches']*100:.2f}% over {row['matches']} matches)")
    elif all_near:
        print("No exact match, but close candidates (matches/wins differ by <=1):")
        for patch_id, slice_label, account_id, row in all_near[:10]:
            steam64 = account_id + 76561197960265728
            print(f"  {patch_id} / {slice_label}  account_id={account_id}  steam64={steam64}  "
                  f"{row['wins']}W/{row['matches']}M")
    else:
        print("No candidate produced the target sequence in any (patch, MMR) slice.")
        print("Try checking patch_id and MMR filter in the page header.")


if __name__ == "__main__":
    main()
