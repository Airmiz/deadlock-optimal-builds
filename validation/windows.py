"""Train/test window selection for the validation harness.

A patch's match data spans [patch_min_ts, patch_end_ts]. We split into:
  train_window = [patch_min_ts, patch_end_ts - test_days*86400]
  test_window  = [patch_end_ts - test_days*86400, patch_end_ts]

patch_end_ts is the *next* patch's min_ts when the patch is finished, or
"now" for the currently-active patch.

Default test_days = 7 (per methodology review §7).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _paths import PATCH_REGISTRY  # noqa: E402


SECONDS_PER_DAY = 86_400
MIN_TEST_DAYS = 3
MIN_TRAIN_DAYS = 3


@dataclass(frozen=True)
class Window:
    min_ts: int
    max_ts: int

    @property
    def days(self) -> float:
        return (self.max_ts - self.min_ts) / SECONDS_PER_DAY

    def as_query(self) -> str:
        return f"min_unix_timestamp={self.min_ts}&max_unix_timestamp={self.max_ts}"


@dataclass(frozen=True)
class Split:
    patch_id: str
    train: Window
    test: Window

    @property
    def total_days(self) -> float:
        return (self.test.max_ts - self.train.min_ts) / SECONDS_PER_DAY


def patch_end_ts(patch_id: str, now_ts: int | None = None) -> int:
    """Return the upper-bound timestamp of a patch's match data.

    For a finished patch this is the start of the *next* patch in the
    registry. For the currently-active patch (no successor or successor
    in the future) it's `now_ts`.
    """
    if now_ts is None:
        now_ts = int(time.time())
    starts = sorted(
        (meta["min_ts"], pid) for pid, meta in PATCH_REGISTRY.items() if meta.get("min_ts")
    )
    patch_start = PATCH_REGISTRY[patch_id]["min_ts"]
    next_start = None
    for ts, pid in starts:
        if ts > patch_start:
            next_start = ts
            break
    if next_start is None or next_start > now_ts:
        return now_ts
    return next_start


def make_split(patch_id: str, test_days: int = 7,
               now_ts: int | None = None) -> Split:
    """Build a (train, test) split for the given patch.

    Raises ValueError if the patch is too short for the requested split
    (need at least MIN_TRAIN_DAYS train and MIN_TEST_DAYS test).
    """
    if now_ts is None:
        now_ts = int(time.time())
    start = PATCH_REGISTRY[patch_id]["min_ts"]
    end = patch_end_ts(patch_id, now_ts)
    total_days = (end - start) / SECONDS_PER_DAY
    if total_days < MIN_TEST_DAYS + MIN_TRAIN_DAYS:
        raise ValueError(
            f"patch {patch_id} only has {total_days:.1f}d of data; need "
            f"≥{MIN_TEST_DAYS + MIN_TRAIN_DAYS}d for a {test_days}d test split"
        )
    # If the patch is too short for `test_days`, shrink the test window
    # rather than fail outright.
    test_days = max(MIN_TEST_DAYS, min(test_days, int(total_days - MIN_TRAIN_DAYS)))
    boundary = end - test_days * SECONDS_PER_DAY
    return Split(
        patch_id=patch_id,
        train=Window(min_ts=start, max_ts=boundary),
        test=Window(min_ts=boundary, max_ts=end),
    )
