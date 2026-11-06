"""Deadlock's inventory rules, and the per-hero category bands builds must fit.

Since 2025-05-08 a hero holds at most 12 upgrades and any slot takes any
category. Since 2025-11-21 that is 9 slots from the start plus 1 for each enemy
Walker destroyed. There is no per-category limit in the game, but real
inventories are far from even: about 3% of full ones are 4/4/4, and the mean
weapon count runs from about 0 (Kelvin) to 7 (Venator).

Win rate alone doesn't capture that. Left unconstrained, the optimizer gives
some heroes no vitality at all, so each build is held near what that hero's
players actually carry. See docs/methodology.md for the evidence.

The old 16-item rules live on as the classic build system, behind the page's
flip: 4 weapon / 4 vitality / 4 spirit / 4 flex, with each category between 4
and 8 items. BUILD_SYSTEM=classic switches every helper here over to them.
"""
from __future__ import annotations

import math
from collections import Counter

from _paths import CLASSIC

INVENTORY_SLOTS = 16 if CLASSIC else 12
BASE_SLOTS = 9
EXTRA_SLOTS = 3
CATEGORIES = ("weapon", "vitality", "spirit")

# Bands come from matches at least this long, when inventories are full.
LONG_MATCH_S = 2100
# How far a build may stray from the hero's mean holding in each category.
BAND_HALF_WIDTH = 1.5
# Fewer full inventories than this and a hero's own mean is too noisy to use.
MIN_INVENTORIES_FOR_BAND = 30

# For heroes without enough data. Spans the per-hero means seen across the
# roster (weapon 0.1-7.0, vitality 2.8-5.7, spirit 0.7-8.0, Sep-Nov 2026) plus
# the same half width.
DEFAULT_BOUNDS = {"weapon": [0, 9], "vitality": [1, 8], "spirit": [0, 10]}
CLASSIC_BOUNDS = {"weapon": [4, 8], "vitality": [4, 8], "spirit": [4, 8]}

# Bump when the way match-only archetypes pick items changes, so committed
# resolutions get recomputed. See match_archetype_resolver.py.
RESOLUTION_SCHEMA = 2


def default_bands() -> dict:
    bounds = CLASSIC_BOUNDS if CLASSIC else DEFAULT_BOUNDS
    return {"source": "default", "inventories": 0, "mean": None,
            "bounds": {c: list(b) for c, b in bounds.items()}}


def bands_from_item_stats(rows: list, items_by_id: dict) -> dict:
    """Per-category bands for one hero from /v1/analytics/item-stats rows.

    `matches - sold` counts matches that ended with the item still held, since
    an item absorbed into an upgrade counts as sold. Summing that per category
    gives the hero's end-of-match inventory mix.
    """
    if CLASSIC:
        return default_bands()
    held: Counter = Counter()
    for r in rows or []:
        it = items_by_id.get(r.get("item_id"))
        if not it or it.get("type") != "upgrade" or it.get("item_slot_type") not in CATEGORIES:
            continue
        held[it["item_slot_type"]] += max(0, r.get("matches", 0) - (r.get("sold") or 0))
    total = sum(held.values())
    inventories = total // INVENTORY_SLOTS
    if inventories < MIN_INVENTORIES_FOR_BAND:
        return default_bands()
    mean = {c: INVENTORY_SLOTS * held[c] / total for c in CATEGORIES}
    return {
        "source": "hero",
        "inventories": inventories,
        "mean": {c: round(m, 2) for c, m in mean.items()},
        "bounds": {c: [max(0, math.floor(m - BAND_HALF_WIDTH)),
                       min(INVENTORY_SLOTS, math.ceil(m + BAND_HALF_WIDTH))]
                   for c, m in mean.items()},
    }


def fit_bounds(bands: dict | None, available: dict,
               slots: int = INVENTORY_SLOTS) -> tuple[dict, dict, int]:
    """Make the bands satisfiable for the candidates on offer.

    Returns (floors, ceilings, target build size). Thin slices can have too few
    candidates in a category, so floors drop to what exists and ceilings widen
    until the build can fill. A build only comes up short when there are fewer
    candidates than slots overall. The classic rules are fixed, so a pool that
    can't meet them leaves the solver with no solution, as it always did.
    """
    bounds = (bands or default_bands())["bounds"]
    if CLASSIC:
        return ({c: bounds[c][0] for c in CATEGORIES},
                {c: bounds[c][1] for c in CATEGORIES}, slots)
    floors = {c: min(bounds[c][0], available.get(c, 0)) for c in CATEGORIES}
    ceilings = {c: min(bounds[c][1], available.get(c, 0)) for c in CATEGORIES}
    target = min(slots, sum(available.get(c, 0) for c in CATEGORIES))
    short = target - sum(ceilings.values())
    for c in sorted(CATEGORIES, key=lambda c: available.get(c, 0) - ceilings[c], reverse=True):
        if short <= 0:
            break
        extra = min(short, available.get(c, 0) - ceilings[c])
        ceilings[c] += extra
        short -= extra
    return floors, ceilings, target


def select_picks(ranked: list[dict], bands: dict | None = None,
                 slots: int = INVENTORY_SLOTS) -> list[dict]:
    """Take a build from best-first candidates, staying inside the bands.

    Each category's floor is filled with its best items first, then the rest of
    the build goes to the best remaining items whose category has room. Returns
    the picks in the order they were ranked.
    """
    if CLASSIC:
        return classic_picks(ranked)
    ranked = [c for c in ranked if c.get("category") in CATEGORIES]
    floors, ceilings, target = fit_bounds(bands, Counter(c["category"] for c in ranked), slots)
    chosen: set[int] = set()
    counts: Counter = Counter()
    for i, c in enumerate(ranked):
        if counts[c["category"]] < floors[c["category"]]:
            chosen.add(i)
            counts[c["category"]] += 1
    for i, c in enumerate(ranked):
        if len(chosen) >= target:
            break
        if i not in chosen and counts[c["category"]] < ceilings[c["category"]]:
            chosen.add(i)
            counts[c["category"]] += 1
    return [c for i, c in enumerate(ranked) if i in chosen]


def classic_picks(ranked: list[dict]) -> list[dict]:
    """The old 16-item bundle from best-first candidates: the top 4 of each
    category, then the best 4 left over as flex, each labelled with its `slot`."""
    ranked = [c for c in ranked if c.get("category") in CATEGORIES]
    picks, used = [], set()
    for cat in CATEGORIES:
        for c in [c for c in ranked if c["category"] == cat][:4]:
            picks.append({**c, "slot": cat})
            used.add(c["item_id"])
    for c in [c for c in ranked if c["item_id"] not in used][:4]:
        picks.append({**c, "slot": "flex"})
    return picks


def label_slots(picks: list[dict]) -> list[dict]:
    """Label a best-first solved build for display, under the classic rules."""
    return classic_picks(picks) if CLASSIC else picks


def one_per_lineage(ranked: list[dict], lineage_canon: dict) -> list[dict]:
    """Keep the first item of each upgrade chain, since a chain shares one slot."""
    seen: set[int] = set()
    out = []
    for c in ranked:
        canon = lineage_canon.get(c["item_id"], c["item_id"])
        if canon not in seen:
            seen.add(canon)
            out.append(c)
    return out
