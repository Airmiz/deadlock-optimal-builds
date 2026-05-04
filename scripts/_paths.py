"""Shared path configuration. All scripts import from here.

Patch-aware: the active patch is set via the PATCH_ID env var (defaults to
patch_125825). All patch-specific cache and output data lives under that
patch's namespace, so multiple patches can coexist on disk side-by-side.

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

# Known patches — extend this map when a new patch drops, or just set
# PATCH_ID and let the rest fall back to whatever's loaded.
PATCH_REGISTRY = {
    "patch_125825": {"title": "04-10-2026 Update", "min_ts": 1775880233},
    "patch_129989": {"title": "04-30-2026 Update", "min_ts": 1777592780},
}

PATCH_ID = os.environ.get("PATCH_ID", "patch_125825")
_meta = PATCH_REGISTRY.get(PATCH_ID, {})
PATCH_TITLE = _meta.get("title", PATCH_ID)
PATCH_MIN_TS = _meta.get("min_ts", 0)
# Deadlock badge_level encoding: tier * 10 + sub-tier (1..6).
# Phantom 1 = 91, Ascendant 1 = 101, Eternus 1 = 111.
HMMR_BADGE = 91       # Phantom 1+ — top ~15-20%
ASCENDANT_BADGE = 101  # Ascendant 1+ — top ~3-5%
ETERNUS_BADGE = 111    # Eternus 1+ — top ~0.1-1%
SPEC_VERSION = "1.2.0"  # bumped — added ascendant_plus + eternus_plus MMR slices

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
