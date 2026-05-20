"""Aggregate-level temporal hold-out validation for the three build methods.

Per methodology review §7. The deadlock-api is aggregation-only — no
per-match endpoint exists — so the harness is a *temporal-window*
hold-out rather than a per-match prediction loop:

  train_window = [patch_start, patch_end - test_days*86400]
  test_window  = [patch_end - test_days*86400, patch_end]

For each (hero × MMR slice × method ∈ {Wilson Greedy, Synergy ILP,
Build Replication}):

  1. Fetch item-stats / pair-stats / build-stats / hero-stats from the
     deadlock-api separately for train and test windows.
  2. Run the production scoring (imported from build_hero_output.py)
     against the train-window inputs. The result is a list of
     "recommended" item picks per method.
  3. Evaluate each method's picks against the test-window data:
       - Spearman rank correlation of (train_score, test_score) across
         items appearing in both windows.
       - Top-K hit rate (K=8, K=16) vs raw-WR ranking in test window.
       - Pooled bundle WR of recommended picks in test window vs the
         test-window hero baseline (Δ in percentage points).
       - Wilson 95% LB calibration — coverage of test-window WR by
         train-window Wilson LB. Well-calibrated → ≥ 0.95.

Outputs land under validation/reports/<patch>_<utc_iso>/:
  report.json    — full per-(hero,mmr,method) metric dump
  summary.md     — human-readable summary, method leaderboard, calibration
  per_hero.csv   — one row per (hero,mmr,method) for downstream analysis

CLI:
  python validation/harness.py                            # active patch, hmmr
  python validation/harness.py --patch patch_125825       # specific patch
  python validation/harness.py --heroes 19,2,15           # specific heroes
  python validation/harness.py --mmr all,hmmr,asc,eter    # all four slices
  python validation/harness.py --test-days 5              # custom test window
  python validation/harness.py --dry-run                  # no fetch, no report

The harness is read-only against the production pipeline: it never
writes to cache/ or heroes/. Its own cache lives under
validation/window_cache/<patch>/<min_ts>_<max_ts>/.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import ROOT, CACHE, BUILD_FILES, PATCH_ID, PATCH_REGISTRY  # noqa: E402
from build_hero_output import (  # noqa: E402
    build_candidates, build_lineage_map,
    method_wilson, method_synergy_ilp, method_build_replication,
    DEFAULT_SOUL_BUDGETS,
)
import hierarchical  # noqa: E402
import bias_correction  # noqa: E402

from windows import Split, make_split  # noqa: E402
from fetch_window import (  # noqa: E402
    fetch_all, fetch_build_details, hero_baseline, load_json, SLICE_FLOORS,
    item_stats_path, pair_stats_path, build_stats_path,
)
from metrics import (  # noqa: E402
    rank_correlation, top_k_hit_rate, held_out_wr_delta,
    calibration_check, rank_items_by_wr, wilson_lb,
)


METHODS = ("wilson_greedy", "synergy_ilp", "build_replication")


def _load_assets() -> tuple[dict, list]:
    items = {i["id"]: i for i in json.load(open(CACHE / "items.json"))}
    heroes = json.load(open(CACHE / "playable_heroes.json"))
    return items, heroes


def _index_item_stats(rows: list) -> dict[int, dict]:
    return {r["item_id"]: r for r in rows if r.get("matches")}


def _score_train_methods(
    train_item_stats: list,
    train_pair_stats: list,
    train_build_stats: list,
    items_by_id: dict,
    train_baseline_wr: float,
    lineage_canon: dict,
    floors: dict,
    score_fn=None,
    soul_budgets: dict | None = None,
    synergy_top_k: int = 400,
) -> dict[str, list]:
    """Compute the three method recommendations on the train window.

    Returns {method_name: [pick_dict, ...]}. Each pick dict carries the
    fields produced by build_hero_output.build_candidates() plus the
    method's slot assignment.

    If `score_fn` is provided, it is forwarded to `build_candidates` to
    override the default Wilson-LB-minus-baseline scoring (used for the
    hierarchical-pooling variant).
    """
    candidates = build_candidates(
        train_item_stats, items_by_id, train_baseline_wr,
        floors["item"], lineage_canon=lineage_canon,
        score_fn=score_fn,
    )
    out: dict[str, list] = {}
    if not candidates:
        return {m: [] for m in METHODS}
    out["wilson_greedy"] = method_wilson(candidates)
    try:
        out["synergy_ilp"] = method_synergy_ilp(
            candidates, train_pair_stats, floors["pair"],
            soul_budgets=soul_budgets,
            synergy_top_k=synergy_top_k,
        )
    except Exception:
        out["synergy_ilp"] = list(out["wilson_greedy"])
    out["build_replication"], _ = method_build_replication(
        candidates, train_build_stats, train_baseline_wr,
        BUILD_FILES, floors["build"],
    )
    # Also keep the candidate scores for the rank correlation metric.
    out["__candidates__"] = candidates  # type: ignore[assignment]
    return out


def _evaluate_picks(
    picks: list[dict],
    train_candidates: dict[int, dict],
    test_item_stats: dict[int, dict],
    test_baseline_wr: float,
    test_ranking_by_wr: list[int],
) -> dict:
    """Compute the four metrics for one method's picks."""
    recommended_ids = [p["item_id"] for p in picks]
    train_scores = {iid: c["score"] for iid, c in train_candidates.items()}
    test_scores = {
        iid: (r["wins"] / r["matches"] - test_baseline_wr)
        for iid, r in test_item_stats.items()
    }
    return {
        "n_picks": len(picks),
        "rank_corr": rank_correlation(train_scores, test_scores),
        "top_8_hit": top_k_hit_rate(recommended_ids, test_ranking_by_wr, k=8),
        "top_16_hit": top_k_hit_rate(recommended_ids, test_ranking_by_wr, k=16),
        "held_out": held_out_wr_delta(recommended_ids, test_item_stats, test_baseline_wr),
    }


def validate_hero(
    hero: dict,
    split: Split,
    mmr: str,
    items_by_id: dict,
    lineage_canon: dict,
    priors: dict | None = None,
    scoring_mode: str = "wilson",
    soul_budgets: bool = False,
    synergy_top_k: int = 400,
) -> dict:
    """Run all three methods on one (hero, mmr) and return metrics.

    When `scoring_mode == "hierarchical"`, `priors` must be the fitted
    item-prior dict for this MMR slice (built once before the per-hero
    loop and passed in). A per-hero closure binds the hero's baseline
    WR into `hierarchical.score`, then `build_candidates` uses it.
    """
    hid = hero["id"]
    floors = SLICE_FLOORS[mmr]

    # ---- Baselines (skip slice if either window has no data) ----
    base_train = hero_baseline(split.patch_id, split.train, mmr, hid)
    base_test = hero_baseline(split.patch_id, split.test, mmr, hid)
    if not base_train or not base_test:
        return {
            "hero_id": hid, "hero_name": hero["name"], "mmr": mmr,
            "status": "no_baseline",
            "train_matches": base_train["matches"] if base_train else 0,
            "test_matches": base_test["matches"] if base_test else 0,
        }

    # ---- Load windowed data ----
    train_item_stats = load_json(item_stats_path(split.patch_id, split.train, mmr, hid))
    train_pair_stats = load_json(pair_stats_path(split.patch_id, split.train, mmr, hid))
    train_build_stats = load_json(build_stats_path(split.patch_id, split.train, mmr, hid))
    test_item_stats_raw = load_json(item_stats_path(split.patch_id, split.test, mmr, hid))

    if not train_item_stats or not test_item_stats_raw:
        return {
            "hero_id": hid, "hero_name": hero["name"], "mmr": mmr,
            "status": "no_item_stats",
            "train_items": len(train_item_stats),
            "test_items": len(test_item_stats_raw),
        }

    # ---- Train: run all three methods (with optional alt scoring) ----
    score_fn = None
    bw = base_train["win_rate"]
    if scoring_mode == "hierarchical" and priors:
        score_fn = hierarchical.make_score_fn(priors, bw)
    elif scoring_mode == "buy_time_bucket":
        score_fn = bias_correction.make_buy_time_bucket_score_fn(
            train_item_stats, items_by_id, bw,
        )
    elif scoring_mode == "time_discount":
        score_fn = bias_correction.make_time_discount_score_fn(
            train_item_stats, items_by_id, bw,
        )
    elif scoring_mode == "bucket_plus_discount":
        score_fn = bias_correction.make_combined_score_fn(
            train_item_stats, items_by_id, bw,
        )
    scored = _score_train_methods(
        train_item_stats, train_pair_stats, train_build_stats,
        items_by_id, bw, lineage_canon, floors,
        score_fn=score_fn,
        soul_budgets=DEFAULT_SOUL_BUDGETS if soul_budgets else None,
        synergy_top_k=synergy_top_k,
    )
    train_candidates = scored.pop("__candidates__")

    # ---- Test: index by item_id, rank by raw WR ----
    test_index = _index_item_stats(test_item_stats_raw)
    test_ranking = rank_items_by_wr(test_item_stats_raw, min_matches=floors["item"] // 3)

    # ---- Per-method metrics ----
    by_method = {}
    for m in METHODS:
        picks = scored.get(m, [])
        by_method[m] = _evaluate_picks(
            picks, train_candidates, test_index,
            base_test["win_rate"], test_ranking,
        )
        by_method[m]["recommended_ids"] = [p["item_id"] for p in picks]
        by_method[m]["recommended_names"] = [p.get("name") for p in picks]

    # ---- Calibration is a property of the data, not the method ----
    calib = calibration_check(
        {iid: c for iid, c in train_candidates.items()},
        test_index,
    )

    return {
        "hero_id": hid, "hero_name": hero["name"], "mmr": mmr,
        "status": "ok",
        "train": {
            "min_ts": split.train.min_ts, "max_ts": split.train.max_ts,
            "days": round(split.train.days, 2),
            "baseline_wr": round(base_train["win_rate"], 5),
            "matches": base_train["matches"],
            "n_candidate_items": len(train_candidates),
        },
        "test": {
            "min_ts": split.test.min_ts, "max_ts": split.test.max_ts,
            "days": round(split.test.days, 2),
            "baseline_wr": round(base_test["win_rate"], 5),
            "matches": base_test["matches"],
            "n_items_with_data": len(test_index),
        },
        "calibration": calib,
        "methods": by_method,
    }


def aggregate(per_hero_results: list[dict]) -> dict:
    """Roll per-hero results up to per-method, per-(method, mmr), and
    per-mmr (data-level) summaries.

    Spearman rank correlation is a property of the candidate scoring
    function (Wilson LB delta), not the method's pick set — every method
    sees the same train→test correlation for a given (hero, mmr). It's
    therefore aggregated separately, per-mmr, rather than duplicated
    across methods in the leaderboard.
    """
    by_key: dict[tuple[str, str], list[dict]] = {}
    for r in per_hero_results:
        if r.get("status") != "ok":
            continue
        for m in METHODS:
            metrics = r["methods"][m]
            by_key.setdefault((m, r["mmr"]), []).append(metrics)

    summaries: dict[str, dict] = {}
    for (m, mmr), entries in by_key.items():
        deltas = [e["held_out"]["delta_pp"] for e in entries if e["held_out"]["delta_pp"] is not None]
        h8 = [e["top_8_hit"]["hit_rate"] for e in entries if e["top_8_hit"]["hit_rate"] is not None]
        h16 = [e["top_16_hit"]["hit_rate"] for e in entries if e["top_16_hit"]["hit_rate"] is not None]
        n = len(entries)
        summaries[f"{m}__{mmr}"] = {
            "method": m,
            "mmr": mmr,
            "n_heroes": n,
            "mean_delta_pp": round(sum(deltas) / len(deltas), 3) if deltas else None,
            "median_delta_pp": round(sorted(deltas)[len(deltas)//2], 3) if deltas else None,
            "mean_top8_hit_rate": round(sum(h8) / len(h8), 4) if h8 else None,
            "mean_top16_hit_rate": round(sum(h16) / len(h16), 4) if h16 else None,
            "heroes_positive_delta": sum(1 for d in deltas if d > 0),
        }

    # Per-mmr method leaderboard by mean held-out delta_pp
    leaderboard: dict[str, list[dict]] = {}
    by_mmr: dict[str, list] = {}
    for k, s in summaries.items():
        by_mmr.setdefault(s["mmr"], []).append(s)
    for mmr, lst in by_mmr.items():
        leaderboard[mmr] = sorted(
            lst,
            key=lambda s: -(s["mean_delta_pp"] if s["mean_delta_pp"] is not None else -999),
        )

    # Data-level metrics (independent of method): score stability + calibration
    data_metrics: dict[str, dict] = {}
    by_mmr_data: dict[str, list[dict]] = {}
    for r in per_hero_results:
        if r.get("status") != "ok":
            continue
        by_mmr_data.setdefault(r["mmr"], []).append(r)
    for mmr, hero_rows in by_mmr_data.items():
        corrs = []
        for hr in hero_rows:
            rc = hr["methods"][METHODS[0]]["rank_corr"]["spearman"]
            if rc is not None:
                corrs.append(rc)
        calibs = [hr["calibration"] for hr in hero_rows
                  if hr["calibration"].get("coverage") is not None]
        data_metrics[mmr] = {
            "n_heroes": len(hero_rows),
            "mean_spearman": (round(sum(corrs) / len(corrs), 4)
                              if corrs else None),
            "min_spearman": min(corrs) if corrs else None,
            "max_spearman": max(corrs) if corrs else None,
            "calibration_mean": (round(sum(c["coverage"] for c in calibs) / len(calibs), 4)
                                  if calibs else None),
            "calibration_min": min((c["coverage"] for c in calibs), default=None),
            "calibration_max": max((c["coverage"] for c in calibs), default=None),
            "well_calibrated_heroes": sum(1 for c in calibs if c["coverage"] >= 0.95),
        }

    return {
        "by_method_and_mmr": summaries,
        "leaderboard_by_mmr": leaderboard,
        "data_metrics_by_mmr": data_metrics,
    }


def _write_csv(path: Path, per_hero: list[dict]) -> None:
    cols = [
        "hero_id", "hero_name", "mmr", "status", "method",
        "train_baseline_wr", "test_baseline_wr",
        "train_matches", "test_matches", "n_candidates",
        "spearman", "n_joint_items",
        "top8_hit_rate", "top16_hit_rate",
        "pooled_wr", "delta_pp", "coverage",
        "calib_coverage", "calib_violations",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in per_hero:
            if r.get("status") != "ok":
                w.writerow([
                    r.get("hero_id"), r.get("hero_name"), r.get("mmr"), r.get("status"),
                    "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
                ])
                continue
            tr, te = r["train"], r["test"]
            calib = r["calibration"]
            for m in METHODS:
                met = r["methods"][m]
                w.writerow([
                    r["hero_id"], r["hero_name"], r["mmr"], r["status"], m,
                    tr["baseline_wr"], te["baseline_wr"],
                    tr["matches"], te["matches"], tr["n_candidate_items"],
                    met["rank_corr"]["spearman"], met["rank_corr"]["n_joint_items"],
                    met["top_8_hit"]["hit_rate"], met["top_16_hit"]["hit_rate"],
                    met["held_out"]["pooled_wr"], met["held_out"]["delta_pp"],
                    met["held_out"]["coverage"],
                    calib.get("coverage"), calib.get("violations"),
                ])


def _write_summary_md(path: Path, split: Split, summary: dict,
                      mmr_slices: list[str], n_heroes: int,
                      per_hero: list[dict]) -> None:
    L: list[str] = []
    def P(*args: Any) -> None:
        L.append(" ".join(str(a) for a in args))

    def _fmt(v, spec):
        return "n/a" if v is None else format(v, spec)

    P(f"# Validation report — {split.patch_id}")
    P()
    P(f"- Patch: `{split.patch_id}` ({PATCH_REGISTRY.get(split.patch_id, {}).get('title', '?')})")
    P(f"- Train window: {_dt.datetime.utcfromtimestamp(split.train.min_ts):%Y-%m-%d} "
      f"→ {_dt.datetime.utcfromtimestamp(split.train.max_ts):%Y-%m-%d} "
      f"({split.train.days:.1f}d)")
    P(f"- Test window:  {_dt.datetime.utcfromtimestamp(split.test.min_ts):%Y-%m-%d} "
      f"→ {_dt.datetime.utcfromtimestamp(split.test.max_ts):%Y-%m-%d} "
      f"({split.test.days:.1f}d)")
    P(f"- Heroes evaluated: {n_heroes}")
    P(f"- MMR slices: {', '.join(mmr_slices)}")
    P()

    P("## Method leaderboard")
    P()
    P("Headline metric: held-out test-window WR of the recommended bundle minus the test-window hero baseline (pp). Higher = method's picks beat baseline on unseen data.")
    P()
    for mmr in mmr_slices:
        rows = summary["leaderboard_by_mmr"].get(mmr) or []
        if not rows:
            continue
        P(f"### MMR slice: `{mmr}`")
        P()
        P("| Rank | Method | Mean Δpp | Median Δpp | Heroes>0 | Top-8 hit | Top-16 hit | n |")
        P("|---|---|---|---|---|---|---|---|")
        for i, s in enumerate(rows, 1):
            P(f"| {i} | `{s['method']}` | "
              f"{_fmt(s['mean_delta_pp'], '+.3f')} | "
              f"{_fmt(s['median_delta_pp'], '+.3f')} | "
              f"{s['heroes_positive_delta']}/{s['n_heroes']} | "
              f"{_fmt(s['mean_top8_hit_rate'], '.3f')} | "
              f"{_fmt(s['mean_top16_hit_rate'], '.3f')} | "
              f"{s['n_heroes']} |")
        P()

    P("## Score stability & calibration (data-level, §2.6)")
    P()
    P("These metrics describe the *data*, not the method. Spearman ρ is the rank correlation between train- and test-window item scores. Calibration coverage is the fraction of items whose train Wilson LB ≤ test observed WR (well-calibrated → ≥ 0.95).")
    P()
    for mmr in mmr_slices:
        dm = summary["data_metrics_by_mmr"].get(mmr)
        if not dm:
            continue
        verdict = ("✓ well calibrated" if (dm["calibration_mean"] or 0) >= 0.95
                   else "✗ under-coverage")
        P(f"### MMR slice: `{mmr}` (n = {dm['n_heroes']} heroes)")
        P()
        P(f"- Spearman ρ — mean **{_fmt(dm['mean_spearman'], '.3f')}**, "
          f"min {_fmt(dm['min_spearman'], '.3f')}, max {_fmt(dm['max_spearman'], '.3f')}")
        P(f"- Wilson LB calibration — mean coverage **{_fmt(dm['calibration_mean'], '.4f')}** "
          f"({verdict}), range [{_fmt(dm['calibration_min'], '.4f')}, "
          f"{_fmt(dm['calibration_max'], '.4f')}], "
          f"well-calibrated heroes: {dm['well_calibrated_heroes']}/{dm['n_heroes']}")
        P()

    # ---- Per-hero spread: best / worst / failures, focused on the headline mmr ----
    headline_mmr = mmr_slices[0]
    rows_ok = [h for h in per_hero
               if h.get("status") == "ok" and h["mmr"] == headline_mmr]
    if rows_ok:
        scored = []
        for h in rows_ok:
            md = {m: h["methods"][m]["held_out"]["delta_pp"] for m in METHODS}
            scored.append((h, md))
        # Order by the leading method on this MMR (top of leaderboard)
        lead_method = (summary["leaderboard_by_mmr"][headline_mmr][0]["method"]
                       if summary["leaderboard_by_mmr"].get(headline_mmr) else METHODS[0])
        scored.sort(key=lambda x: -(x[1][lead_method] if x[1][lead_method] is not None else -999))
        P(f"## Per-hero spread (slice `{headline_mmr}`, ordered by `{lead_method}` Δpp)")
        P()
        P("| Hero | Wilson Δpp | ILP Δpp | Replication Δpp | Calib coverage |")
        P("|---|---|---|---|---|")
        head, tail = scored[:8], scored[-5:]
        for label, group in (("**Top 8**", head), ("**Bottom 5**", tail)):
            P(f"| {label} | | | | |")
            for h, md in group:
                cov = h["calibration"].get("coverage")
                P(f"| {h['hero_name']} | "
                  f"{_fmt(md['wilson_greedy'], '+.2f')} | "
                  f"{_fmt(md['synergy_ilp'], '+.2f')} | "
                  f"{_fmt(md['build_replication'], '+.2f')} | "
                  f"{_fmt(cov, '.3f')} |")
        P()

    fails = [h for h in per_hero if h.get("status") != "ok"]
    if fails:
        P("## Failures")
        P()
        for h in fails:
            P(f"- `{h['hero_id']}` **{h.get('hero_name','?')}** "
              f"({h.get('mmr','?')}) — {h.get('status')}")
        P()

    P("## How to read this")
    P()
    P("- **Δpp** is the *aggregate* held-out WR signal: pooled `sum(wins) / sum(matches)` of the recommended items in the test window, minus the test-window hero baseline. Positive means the method's picks really do outperform an average buy on data the method never saw. Negative means the picks regress to (or below) baseline in the next 7 days.")
    P("- **Top-K hit rate** is the fraction of the method's top-K picks (K = 8, 16) that also rank in the top-K by raw test-window WR. Robust to the method's exact scoring rule.")
    P("- **Spearman ρ** is a *data* property — it doesn't depend on the method. It measures how stable any given item's score is across the train→test split. High ρ → ranking generalizes; low ρ → either noise or genuine patch drift.")
    P("- **Calibration coverage** is also a *data* property. Wilson LB at 95% confidence is supposed to lie below the true WR ≥ 95% of the time. Coverage well under 0.95 means temporal drift inflates train-window WR — the LB is over-confident as soon as you cross the test boundary.")
    P()
    P("_Generated by `validation/harness.py`._")
    path.write_text("\n".join(L), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    patch_id = args.patch or PATCH_ID
    if patch_id not in PATCH_REGISTRY:
        raise SystemExit(f"unknown patch {patch_id}; known: {list(PATCH_REGISTRY)}")
    split = make_split(patch_id, test_days=args.test_days)

    mmr_slices = [m.strip() for m in args.mmr.split(",") if m.strip()]
    for m in mmr_slices:
        if m not in SLICE_FLOORS:
            raise SystemExit(f"unknown mmr slice {m}; known: {list(SLICE_FLOORS)}")

    items_by_id, all_heroes = _load_assets()
    if args.heroes:
        wanted = {int(x) for x in args.heroes.split(",") if x}
        heroes = [h for h in all_heroes if h["id"] in wanted]
    else:
        heroes = list(all_heroes)
    if not heroes:
        raise SystemExit("no heroes selected")

    print(f"Validation harness -- patch {patch_id}")
    print(f"  train: {_dt.datetime.utcfromtimestamp(split.train.min_ts):%Y-%m-%d %H:%M} "
          f"-> {_dt.datetime.utcfromtimestamp(split.train.max_ts):%Y-%m-%d %H:%M} "
          f"({split.train.days:.1f}d)")
    print(f"  test:  {_dt.datetime.utcfromtimestamp(split.test.min_ts):%Y-%m-%d %H:%M} "
          f"-> {_dt.datetime.utcfromtimestamp(split.test.max_ts):%Y-%m-%d %H:%M} "
          f"({split.test.days:.1f}d)")
    print(f"  heroes: {len(heroes)}  mmr: {','.join(mmr_slices)}")

    # ---- Phase 1: fetch every (window x mmr x hero x endpoint) ----
    if not args.dry_run:
        print("\n[1/3] Fetching windowed data ...")
        fetch_summary = fetch_all(
            patch_id, [split.train, split.test],
            hero_ids=[h["id"] for h in heroes],
            mmr_slices=mmr_slices,
        )
        print(f"  fetch summary: {fetch_summary}")
        # Build Replication needs per-build detail JSONs; these are immutable
        # so we cache them once in cache/build_files/ and reuse forever.
        build_summary = fetch_build_details(
            patch_id, [split.train, split.test],
            hero_ids=[h["id"] for h in heroes],
            mmr_slices=mmr_slices,
        )
        print(f"  build details: {build_summary}")
        fetch_summary["build_details"] = build_summary
    else:
        fetch_summary = {"dry_run": True}

    # ---- Phase 2: run all three methods on train, evaluate on test ----
    print(f"\n[2/3] Scoring + evaluating (mode={args.scoring}) ...")
    lineage_ancestors, lineage_canon = build_lineage_map(items_by_id)

    # When hierarchical scoring is requested, pre-fit per-MMR priors once
    # using every hero's train-window data. Each per-hero scoring call
    # then binds its baseline WR into a closure over the shared priors.
    priors_by_mmr: dict[str, dict] = {}
    if args.scoring == "hierarchical":
        print("  Fitting hierarchical priors per MMR slice ...")
        for mmr in mmr_slices:
            per_hero_stats: dict[int, list] = {}
            baselines: dict[int, float] = {}
            for h in heroes:
                base = hero_baseline(patch_id, split.train, mmr, h["id"])
                if not base:
                    continue
                rows = load_json(item_stats_path(patch_id, split.train, mmr, h["id"]))
                if rows:
                    per_hero_stats[h["id"]] = rows
                    baselines[h["id"]] = base["win_rate"]
            floors = SLICE_FLOORS[mmr]
            shrunk, cats = hierarchical.fit_all_priors(
                per_hero_stats, baselines, items_by_id,
                min_matches_per_hero=max(50, floors["item"] // 4),
            )
            priors_by_mmr[mmr] = shrunk
            print(f"    {mmr}: {len(shrunk)} item priors fit "
                  f"from {len(per_hero_stats)} heroes, "
                  f"{len(cats)} category priors")

    per_hero: list[dict] = []
    t0 = time.time()
    for h in heroes:
        for mmr in mmr_slices:
            try:
                r = validate_hero(h, split, mmr, items_by_id, lineage_canon,
                                   priors=priors_by_mmr.get(mmr),
                                   scoring_mode=args.scoring,
                                   soul_budgets=args.feasibility,
                                   synergy_top_k=args.synergy_top_k)
            except Exception as e:
                traceback.print_exc()
                r = {"hero_id": h["id"], "hero_name": h["name"], "mmr": mmr,
                     "status": f"error: {e}"}
            per_hero.append(r)
    print(f"  evaluated {len(per_hero)} (hero, mmr) cells in {time.time()-t0:.1f}s")
    n_ok = sum(1 for r in per_hero if r.get("status") == "ok")
    print(f"  status=ok: {n_ok}/{len(per_hero)}")

    # ---- Phase 3: aggregate + write reports ----
    print("\n[3/3] Aggregating + writing reports ...")
    summary = aggregate(per_hero)
    run_iso = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    feas_tag = "_feasible" if args.feasibility else ""
    tag = f"{patch_id}_{args.scoring}{feas_tag}_{run_iso}"
    out_dir = ROOT / "validation" / "reports" / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "patch_id": patch_id,
        "scoring_mode": args.scoring,
        "split": {
            "train": {"min_ts": split.train.min_ts, "max_ts": split.train.max_ts,
                      "days": round(split.train.days, 2)},
            "test":  {"min_ts": split.test.min_ts,  "max_ts": split.test.max_ts,
                      "days": round(split.test.days, 2)},
        },
        "mmr_slices": mmr_slices,
        "heroes_evaluated": len(heroes),
        "generated_at": run_iso,
        "fetch_summary": fetch_summary,
        "summary": summary,
        "per_hero": per_hero,
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_csv(out_dir / "per_hero.csv", per_hero)
    _write_summary_md(out_dir / "summary.md", split, summary, mmr_slices,
                      n_heroes=n_ok, per_hero=per_hero)

    # Stable "latest" symlink-equivalent: copy summary to a known path so
    # CI / docs can reference one stable location. Wilson and hierarchical
    # scoring runs land in separate directories so they don't clobber each
    # other.
    latest = ROOT / "validation" / "reports" / f"{patch_id}_{args.scoring}{feas_tag}_latest"
    latest.mkdir(parents=True, exist_ok=True)
    (latest / "summary.md").write_text((out_dir / "summary.md").read_text(encoding="utf-8"),
                                        encoding="utf-8")
    (latest / "report.json").write_text((out_dir / "report.json").read_text(encoding="utf-8"),
                                         encoding="utf-8")
    (latest / "per_hero.csv").write_text((out_dir / "per_hero.csv").read_text(encoding="utf-8"),
                                          encoding="utf-8")

    print(f"\nReport tree: {out_dir.relative_to(ROOT)}")
    print(f"  summary.md   ({(out_dir / 'summary.md').stat().st_size:,} bytes)")
    print(f"  report.json  ({(out_dir / 'report.json').stat().st_size:,} bytes)")
    print(f"  per_hero.csv ({(out_dir / 'per_hero.csv').stat().st_size:,} bytes)")
    print(f"Also mirrored to: {latest.relative_to(ROOT)}/")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--patch", default=None,
                   help="Patch id (default: active patch from _paths.PATCH_ID)")
    p.add_argument("--heroes", default="",
                   help="Comma-sep hero ids to validate (default: all playable)")
    p.add_argument("--mmr", default="hmmr",
                   help="Comma-sep MMR slices: any of all,hmmr,asc,eter (default: hmmr)")
    p.add_argument("--test-days", type=int, default=7,
                   help="Test window length in days (default: 7)")
    p.add_argument("--dry-run", action="store_true",
                   help="Skip network fetches; use already-cached windowed data")
    p.add_argument("--scoring",
                   choices=("wilson", "hierarchical", "buy_time_bucket",
                            "time_discount", "bucket_plus_discount"),
                   default="wilson",
                   help="Item scoring rule: 'wilson' (Wilson LB - baseline, the current "
                        "production scoring); 'hierarchical' (empirical-Bayes pooling "
                        "across heroes, §2.4); 'buy_time_bucket' (per-phase baseline, "
                        "§2.3 option 1); 'time_discount' (§4.1 weighting); "
                        "'bucket_plus_discount' (both bias corrections combined)")
    p.add_argument("--feasibility", action="store_true",
                   help="Add per-phase soul-budget constraints to the synergy ILP "
                        "(methodology review §3.1). Default off — constraint can "
                        "be tight in some heroes' candidate pools.")
    p.add_argument("--synergy-top-k", type=int, default=400,
                   help="Top-K strongest pairwise synergies fed to the ILP "
                        "(methodology review §5.3). Default 400 matches the "
                        "historical heuristic; try 2000 to remove the cutoff.")
    return p.parse_args()


if __name__ == "__main__":
    run(_parse_args())
