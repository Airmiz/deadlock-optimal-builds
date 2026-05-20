"""Hierarchical empirical-Bayes pooling for item scoring (methodology review §2.4).

The default scoring in `build_hero_output.build_candidates` is Wilson 95% LB
minus the hero baseline WR. That treats every (hero, item) pair as an
independent Bernoulli draw and ignores cross-hero information. Low-pick
heroes (newly released, niche picks) end up with most items below the
candidate-sample floor and fall back to STAT picks.

This module implements the two-level Normal-Normal model from §2.4:

    score[hero, item] ~ Normal(item_effect[item] + hero_residual[hero, item], σ²)
    item_effect[item] ~ Normal(category_mean[category], τ_item²)
    hero_residual[hero, item] ~ Normal(0, τ_hi²)

We work in *lift* space (observed_WR - baseline_WR), which is approximately
Normal for the sample sizes the candidate floor enforces. Empirical-Bayes
closed-form, no MCMC:

  1. fit_item_priors: pool every (hero, item) observation by item to get a
     prior (mean_lift, τ_hi²) for each item. τ_hi² subtracts expected
     binomial noise from the cross-hero variance.
  2. fit_category_priors: pool item priors within a category to get
     (μ_category, τ_item²). Used to shrink item priors with few heroes.
  3. shrink_item_priors: each item's prior mean is shrunk toward its
     category mean (weight ∝ 1 / item-effect variance).
  4. score: per (hero, item), Gaussian conjugate posterior given the
     shrunk item prior plus the observed wins/matches. Score is the
     posterior mean (or posterior 5th-percentile LB if `conservative=True`).

The module is pure functions over dicts/dataclasses — no class hierarchy
and no global state. It's imported by `build_hero_output` (via the new
optional `score_fn` parameter on `build_candidates`) and by the
validation harness for the `--scoring hierarchical` comparison.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable


# Minimum heroes contributing to an item's cross-hero pool. With fewer than
# this, the variance estimate is too noisy to trust; the item falls back to
# the category-level prior alone.
MIN_HEROES_FOR_ITEM_PRIOR = 3

# Minimum items in a category for the category-level prior to be useful.
MIN_ITEMS_FOR_CATEGORY_PRIOR = 5

# Floor for variance (avoid division by zero and degenerate priors).
MIN_VAR = 1e-6

# Binomial noise approximation: WR variance ≈ p(1-p)/n. We use 0.25/n as the
# worst-case (p = 0.5). For sample sizes ≥ 100 the approximation is fine.
def _binomial_obs_var(matches: int) -> float:
    if matches <= 0:
        return 1.0
    return 0.25 / matches


@dataclass(frozen=True)
class ItemPrior:
    """Prior over an item's true lift, pooled across heroes."""
    item_id: int
    category: str | None
    mean: float          # item_effect: pooled cross-hero lift
    var: float           # τ_hi²: residual cross-hero variance of the item's lift
    n_heroes: int        # heroes that contributed
    raw_mean: float      # pre-shrinkage mean (for inspection)
    shrunk: bool         # True if level-2 (category) shrinkage applied


@dataclass(frozen=True)
class CategoryPrior:
    """Prior over item effects within a category."""
    category: str
    mean: float          # μ_category
    var: float           # τ_item²
    n_items: int


def fit_item_priors(
    per_hero_item_stats: dict[int, list],
    baseline_wr_by_hero: dict[int, float],
    items_by_id: dict,
    min_matches_per_hero: int,
) -> dict[int, ItemPrior]:
    """Pool every (hero, item) observation by item to get a per-item prior.

    Args:
      per_hero_item_stats: {hero_id: list of item_stat rows from the API}.
        Each row has {item_id, wins, matches, ...}.
      baseline_wr_by_hero: {hero_id: baseline_win_rate}.
      items_by_id: asset metadata for items (for category lookup).
      min_matches_per_hero: drop (hero, item) cells with fewer matches
        than this — they're too noisy to contribute to the prior.

    Returns:
      {item_id: ItemPrior}. Items with fewer than MIN_HEROES_FOR_ITEM_PRIOR
      contributing heroes are omitted; the caller should fall back to the
      category prior for those.
    """
    by_item: dict[int, list[tuple[int, float, int]]] = {}
    for hid, stats in per_hero_item_stats.items():
        baseline = baseline_wr_by_hero.get(hid)
        if baseline is None:
            continue
        for s in stats:
            if s.get("matches", 0) < min_matches_per_hero:
                continue
            iid = s["item_id"]
            it = items_by_id.get(iid)
            if not it or it.get("type") != "upgrade":
                continue
            lift = s["wins"] / s["matches"] - baseline
            by_item.setdefault(iid, []).append((hid, lift, s["matches"]))

    priors: dict[int, ItemPrior] = {}
    for iid, obs in by_item.items():
        if len(obs) < MIN_HEROES_FOR_ITEM_PRIOR:
            continue
        # Weights: sqrt(n_matches) — heroes with more data contribute more,
        # but not linearly (a hero with 100,000 matches shouldn't dominate
        # a hero with 1,000 matches by 100×).
        weights = [math.sqrt(n) for _, _, n in obs]
        total_w = sum(weights)
        if total_w <= 0:
            continue
        mean = sum(w * lift for w, (_, lift, _) in zip(weights, obs)) / total_w
        # Cross-hero variance (method of moments).
        var_total = sum(w * (lift - mean) ** 2
                        for w, (_, lift, _) in zip(weights, obs)) / total_w
        # Subtract expected within-hero binomial noise to isolate true
        # hero-item interaction variance (τ_hi²).
        avg_obs_var = sum(w * _binomial_obs_var(n)
                          for w, (_, _, n) in zip(weights, obs)) / total_w
        tau_hi_sq = max(var_total - avg_obs_var, MIN_VAR)
        category = items_by_id[iid].get("item_slot_type")
        priors[iid] = ItemPrior(
            item_id=iid, category=category,
            mean=mean, var=tau_hi_sq, n_heroes=len(obs),
            raw_mean=mean, shrunk=False,
        )
    return priors


def fit_category_priors(item_priors: dict[int, ItemPrior]) -> dict[str, CategoryPrior]:
    """Within each item category, pool item-effect means into a
    Normal(μ_c, τ_item²) prior. Used in stage-2 shrinkage.

    Categories with fewer than MIN_ITEMS_FOR_CATEGORY_PRIOR items are
    omitted; items in those categories won't be shrunk (the per-item prior
    is used directly).
    """
    by_cat: dict[str, list[float]] = {}
    for p in item_priors.values():
        if p.category:
            by_cat.setdefault(p.category, []).append(p.mean)
    out: dict[str, CategoryPrior] = {}
    for cat, means in by_cat.items():
        if len(means) < MIN_ITEMS_FOR_CATEGORY_PRIOR:
            continue
        m = sum(means) / len(means)
        v = max(sum((x - m) ** 2 for x in means) / len(means), MIN_VAR)
        out[cat] = CategoryPrior(category=cat, mean=m, var=v, n_items=len(means))
    return out


def shrink_item_priors(
    item_priors: dict[int, ItemPrior],
    category_priors: dict[str, CategoryPrior],
) -> dict[int, ItemPrior]:
    """Apply level-2 shrinkage: each item's prior mean is pulled toward
    its category mean, weighted by the item-effect variance.

    The category prior acts as a hyperprior on item_effect. For an item
    pooled across many heroes (low item_var / n_heroes), the prior mean
    stays close to its raw value. For an item with few heroes (high
    item_var / n_heroes), it shrinks heavily toward the category mean.
    """
    out: dict[int, ItemPrior] = {}
    for iid, p in item_priors.items():
        cp = category_priors.get(p.category) if p.category else None
        if cp is None:
            out[iid] = p
            continue
        # Effective observation variance on the item-effect estimate.
        obs_var = max(p.var / p.n_heroes, MIN_VAR)
        precision_obs = 1.0 / obs_var
        precision_prior = 1.0 / cp.var
        total_precision = precision_obs + precision_prior
        post_mean = (p.mean * precision_obs + cp.mean * precision_prior) / total_precision
        out[iid] = ItemPrior(
            item_id=p.item_id, category=p.category,
            mean=post_mean, var=p.var, n_heroes=p.n_heroes,
            raw_mean=p.raw_mean, shrunk=True,
        )
    return out


def fit_all_priors(
    per_hero_item_stats: dict[int, list],
    baseline_wr_by_hero: dict[int, float],
    items_by_id: dict,
    min_matches_per_hero: int,
) -> tuple[dict[int, ItemPrior], dict[str, CategoryPrior]]:
    """Convenience: full two-stage fit. Returns (shrunk_item_priors, category_priors)."""
    raw = fit_item_priors(
        per_hero_item_stats, baseline_wr_by_hero, items_by_id, min_matches_per_hero,
    )
    cats = fit_category_priors(raw)
    return shrink_item_priors(raw, cats), cats


def posterior(
    wins: int, matches: int, prior: ItemPrior, baseline_wr: float,
) -> tuple[float, float]:
    """Gaussian conjugate update.

    Returns (posterior_mean, posterior_var) in lift space (i.e. relative
    to the hero baseline).
    """
    obs_lift = wins / matches - baseline_wr
    obs_var = _binomial_obs_var(matches)
    precision_obs = 1.0 / max(obs_var, MIN_VAR)
    precision_prior = 1.0 / max(prior.var, MIN_VAR)
    total = precision_obs + precision_prior
    post_mean = (obs_lift * precision_obs + prior.mean * precision_prior) / total
    post_var = 1.0 / total
    return post_mean, post_var


def score(
    wins: int, matches: int,
    prior: ItemPrior | None,
    baseline_wr: float,
    conservative: bool = False,
    z: float = 1.645,  # one-sided 95% LB
) -> float:
    """Score one (hero, item) cell under the hierarchical model.

    If `prior` is None, falls back to the raw observed lift (degenerate
    case — caller didn't fit a prior for this item).

    Returns a score on the same axis as the existing Wilson-LB-minus-
    baseline score (positive = item helps hero beat baseline), so the
    downstream picker functions (Wilson Greedy, Synergy ILP, Build
    Replication) all work without modification.
    """
    if prior is None or matches <= 0:
        if matches <= 0:
            return 0.0
        return wins / matches - baseline_wr
    post_mean, post_var = posterior(wins, matches, prior, baseline_wr)
    if conservative:
        return post_mean - z * math.sqrt(post_var)
    return post_mean


def make_score_fn(
    priors: dict[int, ItemPrior],
    baseline_wr: float,
    conservative: bool = False,
) -> Callable[[int, int, int], float]:
    """Build a (wins, matches, item_id) -> score closure that
    `build_hero_output.build_candidates` can use as its `score_fn`.

    `baseline_wr` is the hero's baseline WR in the current slice — it
    parameterizes the closure, so one closure is bound per hero.
    """
    def _score(wins: int, matches: int, item_id: int) -> float:
        return score(wins, matches, priors.get(item_id), baseline_wr, conservative)
    return _score
