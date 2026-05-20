# Shiv Eternus+ — Old vs New Pipeline

Side-by-side of the Synergy-ILP "Recommended" build for Shiv at the Eternus+ MMR slice on `patch_125825` (the data-rich frozen patch).

- **OLD**: the pre-roadmap pipeline output, taken from `heroes/patch_125825/shiv_build.json` as it existed before the methodology-review work landed. Wilson-LB scoring, 1D pick-rate-only tags (CORE / FLEX / SIT. / STAT), no joint archetypes.
- **NEW**: regenerated with `DEADLOCK_SCORING=hierarchical FORCE=1 ONLY=19 python scripts/run_all_heroes.py`. Hierarchical empirical-Bayes scoring (§2.4), 2D pick_rate × lift tag taxonomy (§6.4), and the new `joint_archetypes` field (§3.6).

## ILP picks by phase

### Early game

| OLD (Wilson + 1D tags) | NEW (Hierarchical + 2D tags) |
| --- | --- |
| Restorative Shot — t1 $800 — `flex` | Restorative Shot — t1 $800 — `situational` |
| Monster Rounds — t1 $800 — `situational` | Extra Charge — t1 $800 — **`core_inherited`** |
| Extra Charge — t1 $800 — `core` | Stalker — t2 $1,600 — `situational` |
| Trophy Collector — t2 $1,600 — `situational` | Mystic Shot — t2 $1,600 — `situational` |
| Mystic Shot — t2 $1,600 — `situational` | Healbane — t2 $1,600 — `core_inherited` |
| | Restorative Locket — t2 $1,600 — `core_inherited` |

### Mid game

| OLD (Wilson + 1D tags) | NEW (Hierarchical + 2D tags) |
| --- | --- |
| Enchanter's Emblem — t2 $1,600 — `flex` | Spirit Snatch — t3 $3,200 — **`tech_pick`** |
| Spirit Shredder Bullets — t2 $1,600 — `situational` | Spirit Rend — t3 $3,200 — **`tech_pick`** |
| Spirit Snatch — t3 $3,200 — `situational` | |

### Late game

| OLD (Wilson + 1D tags) | NEW (Hierarchical + 2D tags) |
| --- | --- |
| Mystic Reverb — t4 $6,400 — `flex` | Mystic Reverb — t4 $6,400 — **`core_proven`** |
| Escalating Exposure — t4 $6,400 — `core` | Escalating Exposure — t4 $6,400 — **`core_proven`** |
| Boundless Spirit — t4 $6,400 — `core` | Boundless Spirit — t4 $6,400 — **`core_proven`** |
| Phantom Strike — t4 $6,400 — `flex` | Phantom Strike — t4 $6,400 — **`core_proven`** |
| Witchmail — t4 $6,400 — `core` | Witchmail — t4 $6,400 — **`core_proven`** |
| Arctic Blast — t4 $6,400 — `flex` | Arctic Blast — t4 $6,400 — **`core_proven`** |
| Ethereal Shift — t4 $6,400 — `core` | Ethereal Shift — t4 $6,400 — **`core_proven`** |
| Transcendent Cooldown — t4 $6,400 — `core` | Transcendent Cooldown — t4 $6,400 — **`core_proven`** |

## What the comparison shows

### 1. Tag taxonomy (§6.4)

All eight late-game picks get **upgraded from `core` / `flex` to `core_proven`**, meaning the data now explicitly confirms popularity + high lift. A user looking at the build knows these items aren't just meta-popular — they actually win matches.

**Extra Charge stays in the build but gets retagged from `core` to `core_inherited`** — the page is now signaling "everyone buys this, but the WR delta is essentially zero (−0.15pp at 81% pick rate). Try replacing it." This is the highest-value change in the new taxonomy: it gives the site a vocabulary to break consensus when consensus is wrong.

**Spirit Snatch becomes `tech_pick`** — only 14% of community builds use it, but it carries +6.50pp lift. The page surfaces it as an underused edge instead of burying it as just "situational".

### 2. Picks changed under hierarchical scoring (§2.4)

Four items swap out, four swap in:

| Dropped (Old) | Added (New) | Why |
| --- | --- | --- |
| Trophy Collector (+3.57pp) | Spirit Rend (+2.16pp, `tech_pick`) | Hierarchical down-weights items whose lift looks inflated by cross-hero pooling |
| Spirit Shredder Bullets (+2.38pp) | Healbane (+0.06pp, `core_inherited`) | Cross-hero data ranks Healbane higher than Spirit Shredder for spirit-leaning heroes |
| Enchanter's Emblem (+0.79pp) | Restorative Locket (−0.04pp, `core_inherited`) | Both are flat-WR; the choice reflects category-prior shrinkage |
| Monster Rounds (−0.43pp) | Stalker (−0.19pp, `situational`) | Both are weak; Stalker's cross-hero lift is less negative |

The net effect: less reliance on items whose lift might just be sample noise, more reliance on items the cross-hero prior backs up.

### 3. Joint archetypes (§3.6)

The new pipeline emits a `joint_archetypes` array on each MMR slice. Doesn't exist in the old pipeline at all. For Shiv Eternus+:

| Archetype | Ability priority | Builds | Matches | WR | Lift |
| --- | --- | --- | --- | --- | --- |
| 1 | Serrated Knives → Slice and Dice → Bloodletting | 16 | 2,937 | 46.65% | −1.19pp |
| 2 | Serrated Knives → Slice and Dice → Killing Blow | 3 | 161 | 44.72% | −3.12pp |

Both archetypes have negative lift on Eternus+ (the player pool at this rank is small and Shiv specifically underperforms there), but the *recommendations differ between archetypes* — and the page can surface that. The Bloodletting-3rd archetype leans on Monster Rounds, Point Blank, Healbane; the Killing-Blow-3rd archetype leans on Spirit Rend, Stalker, Spirit Resilience. Same hero, different ability investment → different item priorities.

The Eternus+ slice is the worst-case for joint archetypes because the sample is so thin. On hmmr the spread is much more informative — see [`validation_harness.md`](validation_harness.md) for the across-hero `joint_archetypes` summary table.

## How to regenerate

```bash
# Save the current (pre-change) shiv_build.json before regenerating
cp heroes/patch_125825/shiv_build.json /tmp/shiv_old.json

# Regenerate with the validated hierarchical scoring
cd scripts
FORCE=1 DEADLOCK_SCORING=hierarchical PATCH_ID=patch_125825 ONLY=19 python run_all_heroes.py

# Diff
diff /tmp/shiv_old.json ../heroes/patch_125825/shiv_build.json | head -100
```
