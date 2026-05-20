"""Validation metrics for the temporal hold-out harness.

Given a method's recommended picks (computed on the train window) and
freshly-queried item stats from the test window, compute:

  1. Spearman rank correlation between train_score and test_score across
     all items appearing in both windows. Measures how stable the
     scoring is across time.

  2. Top-K hit rate (K = 8, 16). What fraction of the method's recommended
     top-K items also rank in the top-K by raw win rate in the test window?

  3. Held-out-window WR delta vs baseline. Aggregate (wins, matches) over
     the recommended picks within the test window; compute the bundle's
     pooled WR and compare to the test-window hero baseline. Positive
     means recommended items beat the baseline on unseen data.

  4. Wilson 95% LB calibration. For items present in both windows, what
     fraction of train Wilson-LB values are ≤ the test-window observed
     WR? Should be ≥ 0.95 if Wilson is well-calibrated under temporal
     drift.

All metrics are computed independently of which method produced the
picks. The harness calls each metric with the method's pick list.
"""
from __future__ import annotations

import math
from typing import Iterable


def wilson_lb(wins: int, matches: int, z: float = 1.96) -> float:
    if matches == 0:
        return 0.0
    p = wins / matches
    denom = 1 + z * z / matches
    centre = p + z * z / (2 * matches)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * matches)) / matches)
    return (centre - margin) / denom


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation. Returns None if <3 items or zero variance."""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None

    def ranks(vs: list[float]) -> list[float]:
        # Average-rank tie handling.
        order = sorted(range(n), key=lambda i: vs[i])
        ranks_out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vs[order[j + 1]] == vs[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1  # 1-based average rank for the tie block
            for k in range(i, j + 1):
                ranks_out[order[k]] = avg
            i = j + 1
        return ranks_out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    vx = sum((rx[i] - mx) ** 2 for i in range(n))
    vy = sum((ry[i] - my) ** 2 for i in range(n))
    if vx == 0 or vy == 0:
        return None
    return cov / math.sqrt(vx * vy)


def rank_correlation(train_scores: dict[int, float],
                     test_scores: dict[int, float]) -> dict:
    """Spearman ρ on items present in both windows."""
    joint_ids = sorted(set(train_scores) & set(test_scores))
    if len(joint_ids) < 3:
        return {"spearman": None, "n_joint_items": len(joint_ids)}
    xs = [train_scores[i] for i in joint_ids]
    ys = [test_scores[i] for i in joint_ids]
    return {
        "spearman": spearman(xs, ys),
        "n_joint_items": len(joint_ids),
    }


def top_k_hit_rate(train_picks: list[int], test_ranking: list[int], k: int) -> dict:
    """Fraction of train_picks (truncated to top-k) that appear in test_ranking[:k]."""
    if not train_picks or not test_ranking:
        return {"k": k, "hit_rate": None, "intersection": 0, "n_picks": len(train_picks)}
    picks = train_picks[:k]
    test_top = set(test_ranking[:k])
    inter = sum(1 for p in picks if p in test_top)
    return {
        "k": k,
        "hit_rate": inter / min(k, len(picks)),
        "intersection": inter,
        "n_picks": len(picks),
    }


def held_out_wr_delta(recommended_item_ids: list[int],
                      test_item_stats: dict[int, dict],
                      test_baseline_wr: float) -> dict:
    """Pooled WR of recommended bundle vs baseline, in the test window.

    Each recommended item contributes its (wins, matches) from the test
    window. We pool: WR_bundle = sum(wins) / sum(matches). Delta is
    WR_bundle - test_baseline_wr (in percentage points).

    Items missing from the test window are skipped (with a coverage flag).
    """
    total_wins = 0
    total_matches = 0
    covered = 0
    for iid in recommended_item_ids:
        row = test_item_stats.get(iid)
        if not row or not row.get("matches"):
            continue
        total_wins += row["wins"]
        total_matches += row["matches"]
        covered += 1
    if total_matches == 0:
        return {
            "pooled_wr": None,
            "baseline_wr": test_baseline_wr,
            "delta_pp": None,
            "matches": 0,
            "coverage": 0,
            "n_recommended": len(recommended_item_ids),
        }
    pooled_wr = total_wins / total_matches
    return {
        "pooled_wr": round(pooled_wr, 5),
        "baseline_wr": round(test_baseline_wr, 5),
        "delta_pp": round((pooled_wr - test_baseline_wr) * 100, 3),
        "matches": total_matches,
        "coverage": covered,
        "n_recommended": len(recommended_item_ids),
    }


def calibration_check(train_item_stats: dict[int, dict],
                      test_item_stats: dict[int, dict],
                      z: float = 1.96) -> dict:
    """Wilson LB coverage check.

    For each item with non-zero samples in both windows, compute
    train_LB = wilson_lb(train.wins, train.matches). Count it as covered
    if train_LB ≤ test_observed_WR. Well-calibrated → coverage ≥ 0.95.

    Also reports the symmetric over-coverage rate (fraction where
    train_LB > test_WR — i.e. the LB was too high, indicating temporal
    drift inflated WR in train).
    """
    joint = []
    for iid, tr in train_item_stats.items():
        te = test_item_stats.get(iid)
        if not te or not te.get("matches") or not tr.get("matches"):
            continue
        train_lb = wilson_lb(tr["wins"], tr["matches"], z=z)
        test_wr = te["wins"] / te["matches"]
        joint.append((iid, train_lb, test_wr))
    if not joint:
        return {"coverage": None, "n": 0, "z": z}
    covered = sum(1 for _, lb, wr in joint if lb <= wr)
    avg_violation_pp = (
        sum(max(0.0, lb - wr) for _, lb, wr in joint) / max(1, len(joint) - covered) * 100
        if covered < len(joint) else 0.0
    )
    return {
        "coverage": round(covered / len(joint), 4),
        "n": len(joint),
        "z": z,
        "violations": len(joint) - covered,
        "avg_violation_pp": round(avg_violation_pp, 3),
    }


def rank_items_by_wr(item_stats: list, min_matches: int) -> list[int]:
    """Return item_ids sorted descending by raw WR, with the sample floor applied."""
    rows = [s for s in item_stats if s.get("matches", 0) >= min_matches]
    rows.sort(key=lambda s: -(s["wins"] / s["matches"]))
    return [s["item_id"] for s in rows]


def harmonic_mean(values: Iterable[float]) -> float | None:
    vals = [v for v in values if v is not None and v > 0]
    if not vals:
        return None
    return len(vals) / sum(1 / v for v in vals)
