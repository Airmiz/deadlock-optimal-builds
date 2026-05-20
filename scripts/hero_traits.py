"""Hand-curated enemy-team trait taxonomy (methodology review §2.8 Problem 2).

The current counter-pick aggregation sums per-enemy item deltas. That
double-counts shared traits — if two enemies are both "sustain" heroes,
anti-heal items show as twice as valuable, but the slot is binary.

Fix: classify each playable hero into a small set of trait labels, then
aggregate counter signals by taking the *max* per trait (saturating)
rather than summing per-enemy.

The trait set mirrors the review's eight-bucket proposal. Each hero gets
1–3 traits — overlapping memberships are intentional, e.g. Bebop is
both 'tank' and 'cc'. A hero with no clear trait dominance gets no
label and is treated as 'generic' in the aggregation (its per-enemy
deltas pass through unchanged).

This taxonomy is *deliberately incomplete*. Full curation needs Deadlock
domain knowledge (recent patches, current meta interpretations) and is
better treated as a living document. Heroes not present in HERO_TRAITS
fall back to per-enemy aggregation, which is the pre-§2.8 behavior, so
partial coverage degrades gracefully.

Trait definitions
-----------------

- **spirit_burst**: heroes whose damage profile leans heavily on
  ability burst (Seven, Mo+Krill ult, Vyper).
- **bullet_dps**: heroes whose damage leans on weapon damage (Wraith,
  Haze, McGinnis).
- **sustain**: heroes with strong self-heal or team-heal (Bebop +
  Healing Rite stack, Yamato, Abrams). Trips anti-heal items.
- **mobility**: heroes with high movement / dash / flight (Lash, Wraith,
  Vyper).
- **dive**: mobility + commit-tools (Lash, Mo+Krill ult, Shiv).
- **cc**: hard-CC threats (Dynamo, Bebop hook, Kelvin freeze, Warden).
- **tank**: high-HP frontliners that need % damage or anti-shield
  (Abrams, Bebop, McGinnis turtle).
- **stealth_pickoff**: heroes that win lane via pickoff/snipe (Wraith
  crit-build, Haze, Vindicta).
- **objective_pressure**: heroes that bias toward split-push and
  objective speed (McGinnis, Ivy, Bebop).
"""
from __future__ import annotations


TRAITS = (
    "spirit_burst",
    "bullet_dps",
    "sustain",
    "mobility",
    "dive",
    "cc",
    "tank",
    "stealth_pickoff",
    "objective_pressure",
)


# Class-name-keyed for stability across hero_id renumbering. The
# build_page_data layer maps these to active hero_ids via items_assets.
# Partial coverage — heroes not present fall back to per-enemy summing.
HERO_TRAITS: dict[str, frozenset[str]] = {
    "hero_abrams":     frozenset(("tank", "sustain")),
    "hero_bebop":      frozenset(("tank", "cc", "objective_pressure")),
    "hero_chrono":     frozenset(("cc", "spirit_burst")),
    "hero_dynamo":     frozenset(("cc", "spirit_burst")),
    "hero_forge":      frozenset(("tank", "objective_pressure")),
    "hero_ghost":      frozenset(("bullet_dps", "mobility", "stealth_pickoff")),
    "hero_gigawatt":   frozenset(("spirit_burst", "mobility")),
    "hero_gunslinger": frozenset(("bullet_dps", "objective_pressure")),
    "hero_haze":       frozenset(("bullet_dps", "stealth_pickoff")),
    "hero_hornet":     frozenset(("bullet_dps", "mobility", "stealth_pickoff")),
    "hero_inferno":    frozenset(("spirit_burst", "sustain")),
    "hero_ivy":        frozenset(("mobility", "objective_pressure")),
    "hero_kali":       frozenset(("spirit_burst", "mobility")),
    "hero_kelvin":     frozenset(("cc", "spirit_burst")),
    "hero_krill":      frozenset(("tank", "cc", "dive")),
    "hero_lash":       frozenset(("mobility", "dive")),
    "hero_mcginnis":   frozenset(("bullet_dps", "tank", "objective_pressure")),
    "hero_mirage":     frozenset(("spirit_burst", "mobility")),
    "hero_nano":       frozenset(("cc", "spirit_burst")),
    "hero_orion":      frozenset(("bullet_dps", "stealth_pickoff")),
    "hero_paradox":    frozenset(("cc", "spirit_burst")),
    "hero_paige":      frozenset(("spirit_burst", "cc")),
    "hero_pocket":     frozenset(("spirit_burst", "mobility")),
    "hero_rem":        frozenset(("bullet_dps", "stealth_pickoff")),
    "hero_rutger":     frozenset(("spirit_burst", "tank")),
    "hero_seven":      frozenset(("spirit_burst", "bullet_dps")),
    "hero_shiv":       frozenset(("bullet_dps", "sustain")),
    "hero_slork":      frozenset(("spirit_burst", "mobility")),
    "hero_synth":      frozenset(("spirit_burst", "sustain")),
    "hero_targe":      frozenset(("tank", "cc")),
    "hero_tengu":      frozenset(("mobility", "dive")),
    "hero_thumper":    frozenset(("tank", "cc")),
    "hero_tokamak":    frozenset(("spirit_burst", "sustain")),
    "hero_viper":      frozenset(("spirit_burst", "mobility")),
    "hero_viscous":    frozenset(("tank", "cc")),
    "hero_warden":     frozenset(("cc", "tank")),
    "hero_wraith":     frozenset(("bullet_dps", "mobility", "stealth_pickoff")),
    "hero_yamato":     frozenset(("dive", "sustain")),
}


def trait_vector_for_team(class_names: list[str]) -> dict[str, int]:
    """Count enemies per trait. Multiple traits per hero are all counted."""
    out: dict[str, int] = {t: 0 for t in TRAITS}
    for cn in class_names:
        for t in HERO_TRAITS.get(cn, ()):
            out[t] = out.get(t, 0) + 1
    return out


def saturated_counter_score(
    per_enemy_deltas: list[dict],
    enemy_class_names: list[str],
    saturation: str = "max",
) -> dict[int, float]:
    """Aggregate per-(enemy hero) item deltas into per-item team scores
    that saturate per trait rather than summing per enemy.

    Args:
      per_enemy_deltas: list of {item_id, enemy_class_name, score} — one
        row per (item, enemy) pair, with the per-enemy delta already
        computed (and ideally confidence-weighted per Problem 1).
      enemy_class_names: the chosen enemy team (5 class names).
      saturation: 'max' (default) or 'sum'. 'max' takes the strongest
        signal per trait; 'sum' falls back to the old behavior.

    Returns:
      {item_id: aggregated_score}. Higher = stronger counter-buy signal.
    """
    # Bucket each row by trait. Heroes with no trait labels contribute
    # under a synthetic 'untyped' key per enemy so they don't lose signal.
    by_item_trait: dict[int, dict[str, list[float]]] = {}
    for row in per_enemy_deltas:
        iid = row["item_id"]
        enemy = row.get("enemy_class_name")
        traits = HERO_TRAITS.get(enemy)
        if not traits:
            keys = {f"untyped:{enemy}"}
        else:
            keys = traits
        bucket = by_item_trait.setdefault(iid, {})
        for k in keys:
            bucket.setdefault(k, []).append(row["score"])

    # Filter to enemies actually in this team for the team-conditional score.
    team_class_names = set(enemy_class_names)
    team_traits: set[str] = {f"untyped:{cn}" for cn in team_class_names}
    for cn in team_class_names:
        team_traits |= HERO_TRAITS.get(cn, frozenset())

    out: dict[int, float] = {}
    for iid, by_trait in by_item_trait.items():
        relevant = [vs for trait, vs in by_trait.items() if trait in team_traits]
        if not relevant:
            continue
        if saturation == "max":
            # Per-trait: take max (saturates within trait). Across traits:
            # sum (each trait is an orthogonal axis).
            out[iid] = sum(max(vs) for vs in relevant)
        else:
            out[iid] = sum(sum(vs) for vs in relevant)
    return out
