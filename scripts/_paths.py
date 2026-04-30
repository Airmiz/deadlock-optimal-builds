"""Shared path configuration. All scripts import from here."""
from pathlib import Path

# scripts/ lives one level under the repo root.
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
HERO_DATA = CACHE / "hero_data"
BUILD_FILES = CACHE / "build_files"
HERO_OUT = ROOT / "heroes"
ASSETS = ROOT / "assets"

for d in (CACHE, HERO_DATA, BUILD_FILES, HERO_OUT, ASSETS,
          ASSETS / "heroes", ASSETS / "items", ASSETS / "abilities"):
    d.mkdir(parents=True, exist_ok=True)

# Patch settings — update these when a new patch drops.
PATCH_ID = "patch_125825"
PATCH_TITLE = "04-10-2026 Update"
PATCH_MIN_TS = 1775880233
HMMR_BADGE = 91  # Phantom 1+
SPEC_VERSION = "1.0.0"
