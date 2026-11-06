"""Auto-detect new Deadlock patches and maintain patches.json.

Replaces the hand-edited PATCH_REGISTRY: run this first in the refresh
pipeline and a new patch is picked up within one cron tick of Valve
shipping it — no code edit, no redeploy.

Two sources, because neither alone is trustworthy:

  1. https://api.deadlock-api.com/v2/patches — the forums.playdeadlock.com
     changelog entries (source "forum") of its unified feed. Authoritative
     for WHICH updates count as a patch (the coarse "MM-DD-YYYY" threads,
     not every hotfix) and for the patch id, which is the thread id in the
     link: .../threads/06-30-2026-update.146261/ -> patch_146261
     Its RSS pub_date is NOT usable as a start time — XenForo bumps it
     whenever the thread is edited, so it drifts days past go-live.

  2. ISteamNews GetNewsForApp (appid 1422450) — the Steam announcement,
     whose `date` is the real go-live epoch. Matched to a forum thread
     by the MM-DD-YYYY in the title ("Gameplay Update - 06-30-2026"
     matches forum thread "06-30-2026 Update"), or, since Valve's big
     updates now have names ("City Never Sleeps"), by the day it was
     posted. If Steam has no match we fall back to the RSS pub_date and
     say so loudly, since a wrong min_ts silently mixes two patches'
     matches together.

Existing entries are never rewritten — a min_ts that has already been
used to build committed hero JSONs stays put, so history is stable and
diffs stay small. The only field this script recomputes is the max_ts
chain (each patch closes at the next one's min_ts, newest stays open),
which is idempotent and self-heals a manually-added patch.

Exit codes: 0 always, unless the write itself fails. A patch-feed
outage is not fatal — the committed registry keeps the pipeline running
on the patches it already knows.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PATCH_REGISTRY, REGISTRY_PATH  # noqa: E402

PATCHES_URL = "https://api.deadlock-api.com/v2/patches"
STEAM_NEWS_URL = ("https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
                  "?appid=1422450&count=100&maxlength=1")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}
# Thread id at the end of a forum link: ".../06-30-2026-update.146261/"
THREAD_ID_RE = re.compile(r"\.(\d+)/?$")
DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
# Valve dates its updates in Seattle time: "Minor Update - 11-04-2026" was
# posted at 05:02 UTC on 11-05. A fixed offset is close enough, as updates
# aren't shipped around midnight.
VALVE_TZ = timezone(timedelta(hours=-8))


def _get_json(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _date_key(text: str) -> str | None:
    """'Gameplay Update - 06-30-2026' -> '06-30-2026'. Used to join the
    forum thread and the Steam announcement for the same update."""
    m = DATE_RE.search(text or "")
    return m.group(0) if m else None


def _posted_date_key(epoch: int) -> str:
    """The MM-DD-YYYY Valve would give an update posted at this epoch."""
    return datetime.fromtimestamp(epoch, VALVE_TZ).strftime("%m-%d-%Y")


def _is_steam_patch(title: str) -> bool:
    """Does this official announcement ship balance changes? "Minor Update -
    MM-DD-YYYY", or an undated "Halloween 2026 + Gameplay Update". Hero
    teasers, "Ranked - Beta Season 2" and "Matchmaking Update" don't count."""
    lowered = title.lower()
    return ("update" in lowered and _date_key(title) is not None) or "gameplay update" in lowered


def _rss_epoch(pub_date: str) -> int | None:
    try:
        return int(datetime.strptime(pub_date, "%Y-%m-%dT%H:%M:%SZ")
                   .replace(tzinfo=timezone.utc).timestamp())
    except Exception:
        return None


def discover() -> dict:
    """Return {patch_id: {title, min_ts}} for every patch the feeds know."""
    patches = [p for p in _get_json(PATCHES_URL) if p.get("source") == "forum"]
    try:
        steam = _get_json(STEAM_NEWS_URL)["appnews"]["newsitems"]
    except Exception as e:
        print(f"  WARNING: Steam news unavailable ({e}) — falling back to RSS dates")
        steam = []
    # Official Valve announcements only. The same feed carries press
    # coverage (PCGamesN, PC Gamer, ...) whose headlines can mention a date
    # without being a patch.
    official = [i for i in steam
                if i.get("feedname") == "steam_community_announcements" and i.get("date")]
    steam_epoch_by_date: dict[str, int] = {}
    posted_epoch_by_date: dict[str, int] = {}
    for item in official:
        # Several announcements can share a date (a patch plus its hotfix);
        # the earliest is the one that actually opened the patch window.
        key = _date_key(item.get("title", ""))
        if key:
            prev = steam_epoch_by_date.get(key)
            steam_epoch_by_date[key] = min(prev, item["date"]) if prev else item["date"]
        posted = _posted_date_key(item["date"])
        prev = posted_epoch_by_date.get(posted)
        posted_epoch_by_date[posted] = min(prev, item["date"]) if prev else item["date"]

    found: dict[str, dict] = {}
    for p in patches:
        title = (p.get("title") or "").strip()
        link = p.get("link") or ""
        m = THREAD_ID_RE.search(link)
        if not m or not title:
            continue
        pid = f"patch_{m.group(1)}"
        key = _date_key(title)
        # The thread for a named update ("City Never Sleeps") is titled by
        # date alone and its announcement has no date in the title, so fall
        # back to whatever Valve announced that day. The forum thread for it
        # went up 16 days late, so pub_date is no substitute.
        min_ts = (steam_epoch_by_date.get(key) or posted_epoch_by_date.get(key)) if key else None
        ts_source = "steam"
        if key:
            title = f"{key} Update"  # threads aren't consistently suffixed
        if min_ts is None:
            # Steam's news feed only reaches back ~100 items, so older
            # threads legitimately have no match. Note the weaker source
            # but stay quiet here — main() only warns for patches it
            # actually adopts, otherwise every run shouts about 2025.
            min_ts = _rss_epoch(p.get("pub_date", ""))
            ts_source = "forum pub_date"
            if min_ts is None:
                continue
        found[pid] = {"title": title, "min_ts": int(min_ts), "_ts_source": ts_source}

    # --- Steam-only patches ------------------------------------------------
    # Valve ships balance changes as "Minor Update - MM-DD-YYYY" Steam
    # announcements that never get a forum changelog thread, so the feed
    # above cannot see them. They are real patches: the 07-28-2026 minor
    # update moved hero win rates by 0.90pp on average and 3.78pp at the
    # extreme, while the site was still serving one blended window back to
    # 06-30 — 79% pre-patch data. _is_steam_patch() keeps this to actual
    # patches ("Matchmaking Update" is correctly ignored, and its measured
    # effect on win rates was 0.27pp — noise).
    #
    # These have no thread id, so they are keyed by date: patch_YYYYMMDD.
    # Ordering is by min_ts everywhere, so mixing id schemes is safe.
    dates_with_thread = {_date_key(meta["title"]) for meta in found.values()}
    for item in official:
        title = (item.get("title") or "").strip()
        if not _is_steam_patch(title):
            continue
        key = _date_key(title) or _posted_date_key(item["date"])
        if key in dates_with_thread:
            continue  # the forum thread is the canonical entry for this day
        mm, dd, yyyy = key.split("-")
        pid = f"patch_{yyyy}{mm}{dd}"
        if pid in found:
            continue
        found[pid] = {
            # Normalised to match the forum-thread titles the page renders.
            "title": f"{key} Update",
            "min_ts": int(steam_epoch_by_date.get(key) or item["date"]),
            "_ts_source": "steam",
        }
    return found


def main() -> None:
    registry = {pid: dict(meta) for pid, meta in PATCH_REGISTRY.items()}
    before_ids = set(registry)

    try:
        found = discover()
    except Exception as e:
        print(f"Patch feed unavailable ({e}) — keeping the committed registry as-is")
        found = {}

    newest_known = max((m.get("min_ts", 0) for m in registry.values()), default=0)
    added = []
    for pid, meta in found.items():
        if pid in registry:
            continue
        if meta["min_ts"] <= newest_known:
            # An older patch we deliberately don't track (the feed goes back
            # further than this project does). Adding it would trigger a full
            # cold fetch for data nobody looks at.
            continue
        source = meta.pop("_ts_source", "steam")
        if source != "steam":
            print(f"  WARNING: {pid} ({meta['title']}) has no Steam announcement; "
                  f"using {source} as go-live. If its build data looks blended "
                  f"with the previous patch, correct min_ts in patches.json.")
        registry[pid] = meta
        added.append(pid)

    # Recompute the max_ts chain: every patch closes when the next begins,
    # the newest stays open-ended. Idempotent, and it repairs a patch that
    # was added by hand without closing its predecessor.
    order = sorted(registry, key=lambda p: registry[p]["min_ts"])
    for i, pid in enumerate(order):
        if i + 1 < len(order):
            registry[pid]["max_ts"] = registry[order[i + 1]]["min_ts"]
        else:
            registry[pid].pop("max_ts", None)

    payload = {pid: registry[pid] for pid in order}
    existing_raw = REGISTRY_PATH.read_text(encoding="utf-8") if REGISTRY_PATH.exists() else ""
    new_raw = json.dumps(payload, indent=2, sort_keys=False) + "\n"

    if added:
        for pid in added:
            meta = registry[pid]
            when = datetime.fromtimestamp(meta["min_ts"], timezone.utc).isoformat()
            print(f"NEW PATCH: {pid} — {meta['title']} (live {when})")
    if new_raw != existing_raw:
        REGISTRY_PATH.write_text(new_raw, encoding="utf-8")
        print(f"[saved] {REGISTRY_PATH} ({len(payload)} patches)")
    else:
        print(f"No registry change ({len(payload)} patches, newest {order[-1]})")

    if not added and before_ids:
        print(f"Active patch: {order[-1]} — {registry[order[-1]]['title']}")


if __name__ == "__main__":
    main()
