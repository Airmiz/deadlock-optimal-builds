"""Shared path configuration. All scripts import from here.

Patch-aware: the active patch is set via the PATCH_ID env var (defaults to
the newest patch in PATCH_REGISTRY). All patch-specific cache and output data
lives under that patch's namespace, so multiple patches can coexist on disk
side-by-side.

Layout:
  cache/
    heroes.json, items.json, playable_heroes.json   ← shared assets
    build_files/                                     ← shared build details
    <patch_id>/
      hero_stats_all.json, hero_stats_hmmr.json     ← patch-specific
      hero_data/                                     ← patch-specific
  heroes/
    <patch_id>/                                      ← patch-specific outputs
      *_build.json
"""
import os
from pathlib import Path

# Known patches — extend this map when a new patch drops.
#
# Conventions:
#   - The numeric id is the forums.playdeadlock.com changelog thread id
#     (e.g. threads/06-30-2026-update.146261/ → patch_146261). The thread
#     links are served by https://api.deadlock-api.com/v1/patches.
#   - min_ts is the patch's go-live moment: the Steam announcement epoch
#     from ISteamNews GetNewsForApp (appid 1422450), NOT the forum RSS
#     pub_date (XenForo bumps that on every hotfix edit).
#   - max_ts closes the previous patch when a new one is added: set it to
#     the new patch's min_ts. The newest patch has no max_ts (open-ended).
#     Closed patches are fetched with max_unix_timestamp so their
#     aggregates never blend in matches played on later patches.
PATCH_REGISTRY = {
    "patch_125825": {"title": "04-10-2026 Update", "min_ts": 1775880233, "max_ts": 1777592780},
    "patch_129989": {"title": "04-30-2026 Update", "min_ts": 1777592780, "max_ts": 1779486662},
    "patch_135477": {"title": "05-22-2026 Update", "min_ts": 1779486662, "max_ts": 1782840134},
    "patch_146261": {"title": "06-30-2026 Update", "min_ts": 1782840134},
}

PATCH_ID = os.environ.get("PATCH_ID", "patch_146261")
_meta = PATCH_REGISTRY.get(PATCH_ID, {})
PATCH_TITLE = _meta.get("title", PATCH_ID)
PATCH_MIN_TS = _meta.get("min_ts", 0)
PATCH_MAX_TS = _meta.get("max_ts")  # None → open-ended (the live patch)
# Query-string fragment shared by every analytics fetch. Closed patches get
# an upper bound so re-fetches stay pure even after the game moves on.
TIME_BOUNDS_QS = f"min_unix_timestamp={PATCH_MIN_TS}" + (
    f"&max_unix_timestamp={PATCH_MAX_TS}" if PATCH_MAX_TS else "")
# Deadlock badge_level encoding: tier * 10 + sub-tier (1..6).
# Phantom 1 = 91, Ascendant 1 = 101, Eternus 1 = 111.
HMMR_BADGE = 91       # Phantom 1+ — top ~15-20%
ASCENDANT_BADGE = 101  # Ascendant 1+ — top ~3-5%
ETERNUS_BADGE = 111    # Eternus 1+ — top ~0.1-1%
SPEC_VERSION = "1.2.1"  # bumped — mmr_slices players nullable (API dropped hero-stats player counts)

# scripts/ lives one level under the repo root.
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
ASSETS = ROOT / "assets"
BUILD_FILES = CACHE / "build_files"  # shared (build details by ID)

# Patch-specific directories
PATCH_CACHE = CACHE / PATCH_ID
HERO_DATA = PATCH_CACHE / "hero_data"
HERO_OUT = ROOT / "heroes" / PATCH_ID

for d in (CACHE, BUILD_FILES, ASSETS, ASSETS / "heroes", ASSETS / "items", ASSETS / "abilities",
          PATCH_CACHE, HERO_DATA, HERO_OUT):
    d.mkdir(parents=True, exist_ok=True)
