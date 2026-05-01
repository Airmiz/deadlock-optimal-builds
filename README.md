# Deadlock Optimal Builds

Statistically derived optimal item builds and ability point orders for every playable hero in [Deadlock](https://www.playdeadlock.com), powered by the public [deadlock-api.com](https://api.deadlock-api.com) match data.

The headline deliverable is a single self-contained HTML page — open it in any browser, click a hero, and see the recommended build, ability priority, openers, and full ability sequence for the current patch.

![patch](https://img.shields.io/badge/patch-125825%20%E2%80%94%2004--10--2026-orange)
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
- **MMR toggle**: All MMR ↔ High MMR (Phantom 1+, ~top 15-20% of players)
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
├── heroes/                     ← 38 per-hero spec JSONs
├── all_heroes_index.json       ← aggregate index + headline stats
├── all_heroes_tier_list.csv    ← flat tier-list view
├── docs/
│   ├── build_spec.md           ← per-hero output schema
│   ├── shiv_build_summary.md   ← validation writeup
│   └── shiv_mmr_comparison.md  ← all-MMR vs high-MMR comparison
├── validation/                 ← Shiv-only intermediate files (validation evidence)
├── scripts/                    ← pipeline (Python 3.10+)
│   ├── _paths.py               ← path config + patch constants
│   ├── batch_fetch.py          ← (1) pull per-hero analytics + assets
│   ├── batch_fetch_builds.py   ← (2) pull per-build details
│   ├── build_hero_output.py    ← reference per-hero generator
│   ├── run_all_heroes.py       ← (3) generate all 38 hero JSONs in parallel
│   ├── build_index.py          ← (4) aggregate the index + tier list
│   ├── build_page_data.py      ← (5) compile compact page dataset
│   ├── download_images.py      ← (6) localize image refs
│   └── build_page.py           ← (7) assemble the HTML
└── cache/                      ← API responses (gitignored, regenerated)
```

## Refreshing for a new patch

When a new patch drops:

1. Edit `scripts/_paths.py` and update `PATCH_ID`, `PATCH_TITLE`, and `PATCH_MIN_TS` to the new patch's ID and Unix start timestamp. (You can fetch the patch list from `https://api.deadlock-api.com/v1/patches` to find the new timestamp.)
2. Run the pipeline in order:

```bash
cd scripts
python3 batch_fetch.py        # ~1 min — analytics + asset metadata
python3 batch_fetch_builds.py # ~1 min — community build details
python3 run_all_heroes.py     # ~1 min — regenerates per-hero JSONs (parallel)
python3 build_index.py        # ~1 sec — aggregate index + tier list
python3 build_page_data.py    # ~1 sec — compile page dataset
python3 download_images.py    # ~10 sec — pulls any new icons
python3 build_page.py         # ~1 sec — emits the HTML
```

Every script is idempotent — re-running them only fetches missing data.

## Auto-refresh + GitHub Pages

`.github/workflows/refresh.yml` runs the full pipeline nightly at 06:00 UTC, commits the regenerated outputs back to `main`, and deploys the site to GitHub Pages. To enable for your fork:

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

**Status reminder:** the data covers `patch_125825` (04-10-2026 Update). Every hero's recommended build is the highest-WR option *given current data* — Deadlock is in active development, the meta will shift, and re-running the pipeline on a new patch is one command.
