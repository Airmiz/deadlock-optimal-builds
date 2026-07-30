# Deadlock Optimal Builds

Statistically derived optimal item builds and ability point orders for every playable hero in [Deadlock](https://www.playdeadlock.com), powered by the public [deadlock-api.com](https://api.deadlock-api.com) match data.

The headline deliverable is a single self-contained HTML page — open it in any browser, click a hero, and see the recommended build, ability priority, openers, and full ability sequence for the current patch.

![patch](https://img.shields.io/badge/patch-146261%20%E2%80%94%2006--30--2026-orange)
![heroes](https://img.shields.io/badge/heroes-38-blue)
![data](https://img.shields.io/badge/data-deadlock--api.com-lightgrey)

## Quick start

```bash
# Open the page (no server needed)
open deadlock_builds.html
```

That's it. The page loads from local files; the `assets/` folder must travel with the HTML.

## What's in the page

- **Hero grid** with portraits, sortable A–Z or by win rate
- **MMR toggle**: All MMR / Phantom+ (badge 91+, ~top 15-20%) / Ascendant+ (badge 101+, ~top 3-5%) / Eternus+ (badge 111+, ~top 0.1-1%). Higher-rank tabs auto-disable on patches where their sample is empty.
- **Ability priority** ranked by winner-weighted AP investment, with a "winner premium" delta showing where successful players invest more than the average
- **Best opener** — the highest-WR first 4 ability points
- **Best full ability order** — the highest-WR 16-point sequence
- **Item build by phase** — Early / Mid / Late columns, item icons, category pills, tier, cost, average buy time, win rate

## Methodology

Each hero's build is derived three independent ways. The page surfaces the synergy-aware ILP build at high MMR as the recommended view; the per-hero JSONs in `heroes/` carry all three method outputs for both MMR slices.

| Method | What it captures | What it misses |
|---|---|---|
| **Wilson 95% LB greedy** | Items with the highest confidence-bounded win rate, 4 per category | Item synergies; tends toward all-T4 endgame items |
| **Synergy-aware ILP** | Item win rates *plus* pairwise synergy bonuses, slot-constrained | Triple-and-higher interactions |
| **Top-build replication** | What real high-WR community builds use | Rewards meta-popularity, may miss strict-WR optima |

For ability orders we rank each hero's 4 abilities by **winner-weighted average AP** (how much skill points winners spend on each ability vs the population average). The top full 16-point sequence and the top first-4 opener are surfaced separately, each with their sample size.

See `docs/build_spec.md` for the full output schema and `docs/shiv_mmr_comparison.md` for a worked example showing why high-MMR analysis differs from all-MMR.

## Repo layout

```
.
├── deadlock_builds.html        ← the deliverable, open in a browser
├── assets/                     ← hero/item/ability icons (4 MB)
├── heroes/<patch_id>/          ← 38 per-hero spec JSONs per patch (history kept)
├── patches.json                ← patch registry, auto-maintained by detect_patches.py
├── all_heroes_index.json       ← aggregate index + headline stats
├── all_heroes_tier_list.csv    ← flat tier-list view
├── docs/
│   ├── build_spec.md           ← per-hero output schema
│   ├── shiv_build_summary.md   ← validation writeup
│   └── shiv_mmr_comparison.md  ← all-MMR vs high-MMR comparison
├── validation/                 ← Shiv-only intermediate files (validation evidence)
├── scripts/                    ← pipeline (Python 3.10+)
│   ├── _paths.py               ← path config; loads patches.json
│   ├── detect_patches.py       ← (0) adopt new patches from the changelog feed
│   ├── batch_fetch.py          ← (1) pull per-hero analytics + assets
│   ├── batch_fetch_builds.py   ← (2) pull per-build details
│   ├── batch_fetch_counters.py ← (2b) per-matchup counter data
│   ├── build_hero_output.py    ← reference per-hero generator
│   ├── run_all_heroes.py       ← (3) generate all 38 hero JSONs in parallel
│   ├── build_index.py          ← (4) aggregate the index + tier list
│   ├── scrape_wiki_icons.py    ← (5) per-item-id icon overrides
│   ├── build_page_data.py      ← (6) compile the current patch's dataset
│   ├── download_images.py      ← (7) localize image refs
│   └── build_page.py           ← (8) assemble the HTML
└── cache/                      ← API responses (gitignored, regenerated)
```

## Patches: detected automatically

**A new patch needs no code change.** `scripts/detect_patches.py` runs at the top of every refresh and maintains `patches.json`:

- Reads the changelog feed (`https://api.deadlock-api.com/v1/patches`) for which updates count as a patch and their ids — the id is the forum thread id, so `.../06-30-2026-update.146261/` → `patch_146261`.
- Takes each patch's go-live time from the Steam announcement (`ISteamNews`, appid 1422450), matched by the date in the title. The forum RSS `pub_date` is deliberately *not* used — XenForo bumps it on every hotfix edit, which would silently blend two patches' matches.
- Closes the outgoing patch by setting its `max_ts` to the new patch's `min_ts`, so old aggregates stop absorbing new-patch matches.

Existing entries are never rewritten, so committed history stays stable. To correct a patch by hand, edit `patches.json` — detection won't overwrite it.

**The site shows one patch: the current one.** Older patches stay in `heroes/<patch_id>/` as data (and still feed the cross-patch imbue fallback), but they aren't shipped in the page and aren't re-fetched — closed patches are immutable, so re-pulling them only burned API calls. A brand-new patch is held back until it has ~100K total matches (a few hours), so the page never shows a roster of empty builds; the switch then happens on its own.

To run the pipeline by hand:

```bash
python3 scripts/detect_patches.py     # ~2 sec — adopt any new patch
python3 scripts/batch_fetch.py        # ~1 min — analytics + asset metadata
python3 scripts/batch_fetch_builds.py # ~1 min — community build details
python3 scripts/batch_fetch_counters.py # ~10 min cold — matchup counters
python3 scripts/run_all_heroes.py     # ~2 min — regenerates per-hero JSONs
python3 scripts/build_index.py        # ~1 sec — aggregate index + tier list
python3 scripts/scrape_wiki_icons.py  # ~10 sec — per-item icon overrides
python3 scripts/build_page_data.py    # ~40 sec — compile page dataset
python3 scripts/download_images.py    # ~10 sec — pulls any new icons
python3 scripts/build_page.py         # ~2 sec — emits the HTML
```

Set `PATCH_ID=patch_<id>` to target a specific patch; the default is the current one. Every script is idempotent — re-running them only fetches what's missing or stale.

## Auto-refresh + GitHub Pages

`.github/workflows/refresh.yml` runs the full pipeline every 3 hours, commits the regenerated outputs back to `main`, and deploys the site to GitHub Pages. To enable for your fork:

1. **Settings → Pages** → Source: **GitHub Actions**
2. **Settings → Actions → General → Workflow permissions** → **Read and write**
3. Either wait for the scheduled run or trigger manually from the **Actions** tab → "Refresh + deploy" → "Run workflow"

After the first successful deploy you get a public URL like `https://<your-username>.github.io/deadlock/` serving the latest build view. The workflow stages just `index.html` (renamed from `deadlock_builds.html`) plus `assets/` and `docs/` into the artifact, so the Pages payload is ~5 MB and loads instantly.

For a one-off public deploy without auto-refresh, push the current state and just run the workflow manually once.

## Dependencies

- Python 3.10+
- `pulp` (for the ILP solver) — `pip install pulp`
- Standard library otherwise

## Data source and rate limits

All data comes from [api.deadlock-api.com](https://api.deadlock-api.com), the community-run public Deadlock API. Analytics endpoints are rate-limited at **200 req/min per IP** (anonymous) or **400 req/min per API key**. The pipeline respects this — it fetches with 6 parallel workers and the per-call cache TTL is 1 hour, so repeated runs return instantly from the API's cache.

The `cache/` directory in this repo holds local copies of fetched responses to avoid re-pulling between runs. It's gitignored — first-time clones run `batch_fetch.py` to populate it.

## Acknowledgements

This project would not exist without:

- [deadlock-api.com](https://deadlock-api.com) for the open API
- The Deadlock player community publishing builds that feed the replication method
- [Statlocker.gg](https://statlocker.gg) for the "WPA" framing that inspired the methodology

## License

MIT — see `LICENSE`.

---

**Status reminder:** the newest tracked patch is `patch_146261` (06-30-2026 Update). Every hero's recommended build is the highest-WR option *given current data* — Deadlock is in active development, the meta will shift, and re-running the pipeline on a new patch is one command.
