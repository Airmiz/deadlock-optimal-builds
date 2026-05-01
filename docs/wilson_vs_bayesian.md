# Wilson LB vs Bayesian shrinkage — side-by-side

Pure analysis: does NOT change the optimizer.
Compares item *scoring* (the input to Wilson greedy + synergy ILP) under three different scoring rules on `patch_125825` high-MMR data.

- **Wilson LB** (current): `Wilson_LB(wins, matches) − baseline_WR`
- **Bayes(k=100)**: Beta-binomial posterior mean − baseline, with prior strength 100 (mild shrinkage)
- **Bayes(k=300)**: prior strength 300 (moderate)
- **Bayes(k=1000)**: prior strength 1000 (heavy — items need ≥1000 matches to drift far from baseline)

Higher = better item. The optimizer picks top-4 per category + 4 flex by these scores.

## Shiv (baseline 47.35%)

_90 items meeting the 300-match floor_

- vs Bayes(k=100): avg rank shift 4.44, top-16 overlap 15/16
  - Bayes adds: Bullet Lifesteal
- vs Bayes(k=300): avg rank shift 4.73, top-16 overlap 15/16
  - Bayes adds: Unstoppable
- vs Bayes(k=1000): avg rank shift 5.93, top-16 overlap 16/16

| # | Wilson | Bayes k=100 | Bayes k=300 | Bayes k=1000 |
|---|---|---|---|---|
| 1 | Ethereal Shift (60.7%, n=5,868) | Scourge (63.6%, n=451) | Ethereal Shift (60.7%, n=5,868) | Ethereal Shift (60.7%, n=5,868) |
| 2 | Scourge (63.6%, n=451) | Ethereal Shift (60.7%, n=5,868) | Witchmail (59.8%, n=8,671) | Witchmail (59.8%, n=8,671) |
| 3 | Witchmail (59.8%, n=8,671) | Witchmail (59.8%, n=8,671) | Mystic Reverb (57.9%, n=30,129) | Mystic Reverb (57.9%, n=30,129) |
| 4 | Mystic Reverb (57.9%, n=30,129) | Mystic Reverb (57.9%, n=30,129) | Scourge (63.6%, n=451) | Escalating Exposure (56.0%, n=15,648) |
| 5 | Spirit Burn (58.4%, n=1,413) | Spirit Burn (58.4%, n=1,413) | Spirit Burn (58.4%, n=1,413) | Transcendent Cooldown (55.8%, n=17,688) |
| 6 | Escalating Exposure (56.0%, n=15,648) | Phantom Strike (58.3%, n=463) | Escalating Exposure (56.0%, n=15,648) | Arctic Blast (55.0%, n=7,359) |
| 7 | Transcendent Cooldown (55.8%, n=17,688) | Escalating Exposure (56.0%, n=15,648) | Transcendent Cooldown (55.8%, n=17,688) | Boundless Spirit (54.2%, n=19,154) |
| 8 | Arctic Blast (55.0%, n=7,359) | Transcendent Cooldown (55.8%, n=17,688) | Arctic Blast (55.0%, n=7,359) | Spirit Burn (58.4%, n=1,413) |

## Seven (baseline 55.40%)

_94 items meeting the 300-match floor_

- vs Bayes(k=100): avg rank shift 7.17, top-16 overlap 15/16
  - Bayes adds: Diviner's Kevlar
- vs Bayes(k=300): avg rank shift 7.28, top-16 overlap 15/16
  - Bayes adds: Diviner's Kevlar
- vs Bayes(k=1000): avg rank shift 7.26, top-16 overlap 15/16
  - Bayes adds: Transcendent Cooldown

| # | Wilson | Bayes k=100 | Bayes k=300 | Bayes k=1000 |
|---|---|---|---|---|
| 1 | Spiritual Overflow (65.8%, n=6,081) | Spiritual Overflow (65.8%, n=6,081) | Spiritual Overflow (65.8%, n=6,081) | Spiritual Overflow (65.8%, n=6,081) |
| 2 | Bullet Lifesteal (65.1%, n=10,870) | Bullet Lifesteal (65.1%, n=10,870) | Bullet Lifesteal (65.1%, n=10,870) | Bullet Lifesteal (65.1%, n=10,870) |
| 3 | Mercurial Magnum (63.0%, n=17,952) | Mercurial Magnum (63.0%, n=17,952) | Mercurial Magnum (63.0%, n=17,952) | Mercurial Magnum (63.0%, n=17,952) |
| 4 | Spirit Burn (62.5%, n=2,673) | Spirit Burn (62.5%, n=2,673) | Spirit Burn (62.5%, n=2,673) | Fleetfoot (61.0%, n=20,909) |
| 5 | Crippling Headshot (62.5%, n=2,154) | Crippling Headshot (62.5%, n=2,154) | Crippling Headshot (62.5%, n=2,154) | Spirit Burn (62.5%, n=2,673) |
| 6 | Fleetfoot (61.0%, n=20,909) | Siphon Bullets (61.9%, n=940) | Fleetfoot (61.0%, n=20,909) | Leech (60.6%, n=33,256) |
| 7 | Leech (60.6%, n=33,256) | Silencer (62.2%, n=479) | Leech (60.6%, n=33,256) | Crippling Headshot (62.5%, n=2,154) |
| 8 | Boundless Spirit (60.2%, n=30,315) | Fleetfoot (61.0%, n=20,909) | Siphon Bullets (61.9%, n=940) | Boundless Spirit (60.2%, n=30,315) |

### Methods disagree most on:

| Item | Wilson rank | Bayes(k=300) rank | Δ | n | wr | wilson | bayes-300 |
|---|---|---|---|---|---|---|---|
| Superior Duration | 16 | 21 | ↓ Bayes-penalized | 48,578 | 57.03% | +0.0119 | +0.0162 |
| Diviner's Kevlar | 20 | 15 | ↑ Bayes-favored | 400 | 61.00% | +0.0074 | +0.0320 |

## Bebop (baseline 47.37%)

_126 items meeting the 300-match floor_

- vs Bayes(k=100): avg rank shift 5.76, top-16 overlap 15/16
  - Bayes adds: Leech
- vs Bayes(k=300): avg rank shift 5.63, top-16 overlap 15/16
  - Bayes adds: Hollow Point
- vs Bayes(k=1000): avg rank shift 6.92, top-16 overlap 14/16
  - Bayes adds: Bullet Lifesteal, Mystic Reverb

| # | Wilson | Bayes k=100 | Bayes k=300 | Bayes k=1000 |
|---|---|---|---|---|
| 1 | Spellslinger (66.8%, n=4,668) | Spellslinger (66.8%, n=4,668) | Spellslinger (66.8%, n=4,668) | Spellslinger (66.8%, n=4,668) |
| 2 | Lucky Shot (63.9%, n=3,618) | Lucky Shot (63.9%, n=3,618) | Lucky Shot (63.9%, n=3,618) | Lucky Shot (63.9%, n=3,618) |
| 3 | Silencer (61.7%, n=5,711) | Silencer (61.7%, n=5,711) | Silencer (61.7%, n=5,711) | Silencer (61.7%, n=5,711) |
| 4 | Siphon Bullets (60.5%, n=9,572) | Siphon Bullets (60.5%, n=9,572) | Siphon Bullets (60.5%, n=9,572) | Siphon Bullets (60.5%, n=9,572) |
| 5 | Inhibitor (59.5%, n=9,028) | Healing Tempo (61.6%, n=727) | Inhibitor (59.5%, n=9,028) | Inhibitor (59.5%, n=9,028) |
| 6 | Healing Tempo (61.6%, n=727) | Inhibitor (59.5%, n=9,028) | Vampiric Burst (58.3%, n=21,675) | Vampiric Burst (58.3%, n=21,675) |
| 7 | Vampiric Burst (58.3%, n=21,675) | Vampiric Burst (58.3%, n=21,675) | Healing Tempo (61.6%, n=727) | Berserker (56.1%, n=18,992) |
| 8 | Frenzy (60.2%, n=510) | Frenzy (60.2%, n=510) | Glass Cannon (57.6%, n=1,609) | Crippling Headshot (56.2%, n=7,317) |

### Methods disagree most on:

| Item | Wilson rank | Bayes(k=300) rank | Δ | n | wr | wilson | bayes-300 |
|---|---|---|---|---|---|---|---|
| Frenzy | 8 | 13 | ↓ Bayes-penalized | 510 | 60.20% | +0.0852 | +0.0808 |

## Vyper (baseline 54.17%)

_82 items meeting the 300-match floor_

- vs Bayes(k=100): avg rank shift 4.56, top-16 overlap 16/16
- vs Bayes(k=300): avg rank shift 4.56, top-16 overlap 16/16
- vs Bayes(k=1000): avg rank shift 4.88, top-16 overlap 15/16
  - Bayes adds: Ricochet

| # | Wilson | Bayes k=100 | Bayes k=300 | Bayes k=1000 |
|---|---|---|---|---|
| 1 | Shadow Weave (73.0%, n=541) | Shadow Weave (73.0%, n=541) | Silencer (67.7%, n=5,457) | Silencer (67.7%, n=5,457) |
| 2 | Silencer (67.7%, n=5,457) | Silencer (67.7%, n=5,457) | Shadow Weave (73.0%, n=541) | Spiritual Overflow (66.1%, n=7,555) |
| 3 | Crippling Headshot (67.0%, n=2,643) | Crippling Headshot (67.0%, n=2,643) | Crippling Headshot (67.0%, n=2,643) | Crippling Headshot (67.0%, n=2,643) |
| 4 | Spiritual Overflow (66.1%, n=7,555) | Spiritual Overflow (66.1%, n=7,555) | Spiritual Overflow (66.1%, n=7,555) | Glass Cannon (65.3%, n=4,732) |
| 5 | Glass Cannon (65.3%, n=4,732) | Glass Cannon (65.3%, n=4,732) | Glass Cannon (65.3%, n=4,732) | Lucky Shot (64.8%, n=5,650) |
| 6 | Lucky Shot (64.8%, n=5,650) | Lucky Shot (64.8%, n=5,650) | Lucky Shot (64.8%, n=5,650) | Armor Piercing Rounds (63.9%, n=4,966) |
| 7 | Armor Piercing Rounds (63.9%, n=4,966) | Armor Piercing Rounds (63.9%, n=4,966) | Armor Piercing Rounds (63.9%, n=4,966) | Unstoppable (63.4%, n=7,034) |
| 8 | Unstoppable (63.4%, n=7,034) | Siphon Bullets (64.7%, n=892) | Unstoppable (63.4%, n=7,034) | Shadow Weave (73.0%, n=541) |

## Haze (baseline 48.88%)

_108 items meeting the 300-match floor_

- vs Bayes(k=100): avg rank shift 6.57, top-16 overlap 16/16
- vs Bayes(k=300): avg rank shift 6.00, top-16 overlap 16/16
- vs Bayes(k=1000): avg rank shift 5.56, top-16 overlap 14/16
  - Bayes adds: Armor Piercing Rounds, Superior Duration

| # | Wilson | Bayes k=100 | Bayes k=300 | Bayes k=1000 |
|---|---|---|---|---|
| 1 | Healing Tempo (67.2%, n=3,699) | Healing Tempo (67.2%, n=3,699) | Healing Tempo (67.2%, n=3,699) | Healing Tempo (67.2%, n=3,699) |
| 2 | Frenzy (67.6%, n=775) | Frenzy (67.6%, n=775) | Silencer (63.1%, n=18,910) | Silencer (63.1%, n=18,910) |
| 3 | Spiritual Overflow (67.0%, n=972) | Spiritual Overflow (67.0%, n=972) | Spiritual Overflow (67.0%, n=972) | Inhibitor (62.7%, n=8,588) |
| 4 | Silencer (63.1%, n=18,910) | Transcendent Cooldown (65.6%, n=619) | Frenzy (67.6%, n=775) | Crippling Headshot (62.0%, n=8,022) |
| 5 | Transcendent Cooldown (65.6%, n=619) | Silencer (63.1%, n=18,910) | Inhibitor (62.7%, n=8,588) | Siphon Bullets (60.2%, n=17,523) |
| 6 | Inhibitor (62.7%, n=8,588) | Inhibitor (62.7%, n=8,588) | Crippling Headshot (62.0%, n=8,022) | Lucky Shot (60.9%, n=8,122) |
| 7 | Crippling Headshot (62.0%, n=8,022) | Crippling Headshot (62.0%, n=8,022) | Lucky Shot (60.9%, n=8,122) | Rapid Recharge (61.3%, n=3,697) |
| 8 | Lucky Shot (60.9%, n=8,122) | Rapid Recharge (61.3%, n=3,697) | Rapid Recharge (61.3%, n=3,697) | Spiritual Overflow (67.0%, n=972) |

## Paradox (baseline 48.15%)

_99 items meeting the 300-match floor_

- vs Bayes(k=100): avg rank shift 6.44, top-16 overlap 16/16
- vs Bayes(k=300): avg rank shift 5.82, top-16 overlap 15/16
  - Bayes adds: Vortex Web
- vs Bayes(k=1000): avg rank shift 5.68, top-16 overlap 14/16
  - Bayes adds: Ballistic Enchantment, Vortex Web

| # | Wilson | Bayes k=100 | Bayes k=300 | Bayes k=1000 |
|---|---|---|---|---|
| 1 | Diviner's Kevlar (65.6%, n=697) | Diviner's Kevlar (65.6%, n=697) | Diviner's Kevlar (65.6%, n=697) | Siphon Bullets (60.8%, n=3,034) |
| 2 | Silencer (63.1%, n=596) | Silencer (63.1%, n=596) | Siphon Bullets (60.8%, n=3,034) | Spirit Burn (58.2%, n=4,364) |
| 3 | Siphon Bullets (60.8%, n=3,034) | Siphon Bullets (60.8%, n=3,034) | Silencer (63.1%, n=596) | Crippling Headshot (56.8%, n=14,933) |
| 4 | Inhibitor (60.2%, n=1,167) | Inhibitor (60.2%, n=1,167) | Inhibitor (60.2%, n=1,167) | Transcendent Cooldown (56.1%, n=10,347) |
| 5 | Spirit Burn (58.2%, n=4,364) | Divine Barrier (61.0%, n=441) | Spirit Burn (58.2%, n=4,364) | Escalating Exposure (56.4%, n=6,419) |
| 6 | Divine Barrier (61.0%, n=441) | Spirit Burn (58.2%, n=4,364) | Crippling Headshot (56.8%, n=14,933) | Diviner's Kevlar (65.6%, n=697) |
| 7 | Crippling Headshot (56.8%, n=14,933) | Cheat Death (60.0%, n=325) | Glass Cannon (57.2%, n=3,073) | Glass Cannon (57.2%, n=3,073) |
| 8 | Glass Cannon (57.2%, n=3,073) | Glass Cannon (57.2%, n=3,073) | Mystic Reverb (57.1%, n=2,437) | Inhibitor (60.2%, n=1,167) |

### Methods disagree most on:

| Item | Wilson rank | Bayes(k=300) rank | Δ | n | wr | wilson | bayes-300 |
|---|---|---|---|---|---|---|---|
| Divine Barrier | 6 | 11 | ↓ Bayes-penalized | 441 | 61.00% | +0.0822 | +0.0765 |

## Aggregate finding

Across 6 test heroes, total top-16 picks that would FLIP under each Bayesian prior:

- **Bayes(k=100)**: 3/96 picks would change (3.1%)
- **Bayes(k=300)**: 4/96 picks would change (4.2%)
- **Bayes(k=1000)**: 8/96 picks would change (8.3%)

## Interpretation

- **Bayes(k=100)** is closest to Wilson — both penalize small-sample items but Bayes does it smoothly. Differences are minor.
- **Bayes(k=300)** matches our 300-match optimizer floor. Items with hundreds of matches get pulled meaningfully toward baseline; items with thousands stay close to their raw WR.
- **Bayes(k=1000)** is the most conservative — even 1k-match items get noticeable shrinkage. Probably too aggressive.

**Practical takeaway:** Wilson LB and Bayes(k=300) agree on roughly 14 of 16 picks per hero. The disagreements are usually items with 300–800 matches where Wilson is somewhat more pessimistic than Bayes. Neither method is 'correct' — Wilson gives a defensible lower bound, Bayes gives a smoothed point estimate.

**Recommendation:** Don't switch. The marginal gain isn't worth introducing a new hyperparameter (prior strength) the optimizer would have to be calibrated against. If we ever DO switch, k=300 is the closest match to current behavior.