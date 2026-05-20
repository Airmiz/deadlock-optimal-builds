"""Bias correction for item scoring (methodology review §2.3 + §4.1).

The default scoring `wr - baseline_wr` treats every match as a single
draw against the *unconditional* hero baseline. That conflates two
effects:

  - **Genuine item lift**: an item really does win more games when used.
  - **Survivorship inflation**: matches reach late-buy-time only when the
    player is winning anyway; T4 items are therefore disproportionately
    in winning inventories at game end.

The deadlock-api is aggregation-only, so the review's option-2
(propensity weighting per match) is not directly buildable here. But
the cheap option-1 ("condition on buy-time bucket") is, and so is
§4.1's time-fraction weighting. Both are implemented as alternative
`score_fn` factories that slot into `build_candidates(..., score_fn=...)`
without forking the downstream method functions.

Two scoring rules:

1. `make_buy_time_bucket_score_fn` — for each hero, compute a *per-phase*
   baseline as the pooled WR of all upgrade items whose `avg_buy_time_s`
   places them in that phase. An item's score is then `WR - phase_baseline`
   instead of `WR - hero_baseline`. T4 items compete against T4 items,
   not against T1 items.

2. `make_time_discount_score_fn` — §4.1 weighting. An item's score is
   the raw lift multiplied by `(1 - avg_buy_time / typical_game_s)`,
   approximating "fraction of the match the item was active". Late
   items get attenuated; early items keep full credit.

Both functions return a `(wins, matches, item_id) -> score` closure.
The harness's `--scoring` flag selects which is used.

Note: the time-discount rule is structurally pessimistic about T4 items
(they get discounted even when their lift is genuine). It's exposed here
because the review specifies it and the harness will tell us empirically
whether it helps. The buy-time-bucket rule has the cleaner motivation
and is the recommended first try.
"""
from __future__ import annotations

from typing import Callable


# Same phase boundaries as build_hero_output.phase_for. Mirrored here to
# avoid a circular import (build_hero_output already imports this module
# via score_fn injection points).
_EARLY_MAX_S = 750     # < 12.5 min
_MID_MAX_S   = 1500    # < 25 min
# else: late

# Typical full-match duration in seconds, for §4.1 time-discount. 35 min
# is the median Deadlock match length per public stats.
TYPICAL_GAME_S = 2100


def _phase(avg_buy_time_s: float) -> str:
    if avg_buy_time_s < _EARLY_MAX_S:
        return "early"
    if avg_buy_time_s < _MID_MAX_S:
        return "mid"
    return "late"


def _is_upgrade(it: dict) -> bool:
    return it.get("type") == "upgrade" and it.get("item_slot_type") in (
        "weapon", "vitality", "spirit",
    )


def _phase_baselines(
    item_stats: list, items_by_id: dict, fallback_wr: float,
) -> tuple[dict[str, float], dict[int, str]]:
    """Compute pooled WR per phase from the hero's item-stats.

    Returns:
      (phase_baseline, item_phase_lookup)
      phase_baseline: {phase_name: pooled_WR}, where pooled_WR is
        sum(wins) / sum(matches) over upgrade items in that phase.
      item_phase_lookup: {item_id: phase_name} for cheap lookup at scoring.

    Items not assigned to a phase (e.g. not upgrades) are absent from
    `item_phase_lookup`. Empty phases fall back to `fallback_wr`.
    """
    by_phase: dict[str, list[tuple[int, int]]] = {}
    item_phase: dict[int, str] = {}
    for s in item_stats:
        it = items_by_id.get(s["item_id"])
        if not it or not _is_upgrade(it):
            continue
        if s.get("matches", 0) <= 0:
            continue
        ph = _phase(s.get("avg_buy_time_s", 0))
        by_phase.setdefault(ph, []).append((s["wins"], s["matches"]))
        item_phase[s["item_id"]] = ph
    baselines = {}
    for ph in ("early", "mid", "late"):
        rows = by_phase.get(ph, [])
        total_w = sum(w for w, _ in rows)
        total_m = sum(m for _, m in rows)
        baselines[ph] = (total_w / total_m) if total_m else fallback_wr
    return baselines, item_phase


def make_buy_time_bucket_score_fn(
    item_stats: list, items_by_id: dict, baseline_wr: float,
) -> Callable[[int, int, int], float]:
    """Score per-(hero, item) = WR − phase_baseline (§2.3 option 1).

    Compares an item to other items bought in the same phase, instead of
    to the unconditional hero baseline. Attenuates survivorship inflation
    of late-game items: a T4 item now competes against the T4 cohort's
    pooled WR, not against the hero's all-match WR (which includes early
    losses where T4 was never reached).
    """
    phase_baselines, item_phase = _phase_baselines(item_stats, items_by_id, baseline_wr)

    def _score(wins: int, matches: int, item_id: int) -> float:
        if matches <= 0:
            return 0.0
        ph = item_phase.get(item_id)
        ref = phase_baselines.get(ph, baseline_wr) if ph else baseline_wr
        return wins / matches - ref

    return _score


def make_time_discount_score_fn(
    item_stats: list, items_by_id: dict, baseline_wr: float,
    typical_game_s: float = TYPICAL_GAME_S,
) -> Callable[[int, int, int], float]:
    """Score = (WR − baseline) × (1 − avg_buy_time / typical_game_s) (§4.1).

    Items bought late get their lift discounted by the fraction of the
    typical match they're not active for. An item bought at minute 35 of
    a 35-minute typical game gets weight ≈ 0; an item bought at minute 5
    gets weight ≈ 0.86.

    This rule is structurally pessimistic about late-game items and is
    expected to under-pick T4s. Exposed for empirical comparison via the
    validation harness; the buy-time-bucket rule above is the
    well-motivated alternative.
    """
    avg_buy_by_id: dict[int, float] = {}
    for s in item_stats:
        it = items_by_id.get(s["item_id"])
        if not it or not _is_upgrade(it):
            continue
        avg_buy_by_id[s["item_id"]] = s.get("avg_buy_time_s", 0)

    def _score(wins: int, matches: int, item_id: int) -> float:
        if matches <= 0:
            return 0.0
        t = avg_buy_by_id.get(item_id, 0)
        weight = max(0.0, 1.0 - t / typical_game_s)
        return (wins / matches - baseline_wr) * weight

    return _score


def make_combined_score_fn(
    item_stats: list, items_by_id: dict, baseline_wr: float,
    typical_game_s: float = TYPICAL_GAME_S,
) -> Callable[[int, int, int], float]:
    """Buy-time-bucket + time-discount, applied multiplicatively.

    Useful for ablation: if the combined rule does worse than the
    bucket-only rule, the time-discount is hurting; if it does better,
    they're complementary.
    """
    phase_baselines, item_phase = _phase_baselines(item_stats, items_by_id, baseline_wr)
    avg_buy_by_id: dict[int, float] = {}
    for s in item_stats:
        it = items_by_id.get(s["item_id"])
        if not it or not _is_upgrade(it):
            continue
        avg_buy_by_id[s["item_id"]] = s.get("avg_buy_time_s", 0)

    def _score(wins: int, matches: int, item_id: int) -> float:
        if matches <= 0:
            return 0.0
        ph = item_phase.get(item_id)
        ref = phase_baselines.get(ph, baseline_wr) if ph else baseline_wr
        t = avg_buy_by_id.get(item_id, 0)
        weight = max(0.0, 1.0 - t / typical_game_s)
        return (wins / matches - ref) * weight

    return _score
