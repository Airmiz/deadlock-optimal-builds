"""
Build a per-item-id icon override using the community Deadlock wiki.

Why a separate namespace from deadlock-api icons:
  items.json reuses asset filenames across unrelated items. Examples:
    fire_rate_plus.png -> Mercurial Magnum, Ballistic Enchantment,
                         Swift Striker, Quicksilver Reload
    tech_damage.png    -> Extra Spirit, Golden Goose Egg
    electrified_bullets.png -> Tesla Bullets, Capacitor
  (60 such collisions in items.json as of patch_129989.)
  If we overwrite assets/items/<basename>.png with a wiki PNG, ALL items
  sharing that basename end up displaying the same wiki icon — which is
  what the user reported (Mercurial Magnum showing Ballistic Enchantment).

  Solution: save each wiki icon to assets/items_wiki/<sanitized_name>.png
  (one file per item — no collisions) and emit a manifest mapping
  item_id -> relative path. build_page_data.py applies the manifest as
  an in-process override to items_assets, so every downstream item
  reference (recommended, items_by_slice, lineage_chain, archetypes,
  match-only archetypes) picks up the right per-item icon.

  Items with no wiki page (cut/beta items like Glass Cannon v2, plus a
  handful the wiki simply hasn't catalogued yet) fall through to whatever
  deadlock-api ships. Items with no deadlock-api image at all (e.g.
  Cultist Sacrifice — items.json image=None) are *recovered* by this
  pipeline because the wiki has them.

Output:
  - assets/items_wiki/<sanitized_name>.png  (one per resolved item)
  - cache/wiki_icon_overrides.json          (manifest: {item_id: rel_path})

Order in the pipeline:
  Must run BEFORE build_page_data.py so the manifest exists when the
  payload is assembled. refresh.yml is wired accordingly.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import CACHE, ASSETS


WIKI_API = "https://deadlock.wiki/api.php"
HEADERS = {
    "User-Agent": "deadlock-optimal-builds icon-refresh "
                  "(https://github.com/Airmiz/deadlock-optimal-builds)",
}
API_BATCH = 40
DOWNLOAD_WORKERS = 5

# Where the per-item wiki icons live on disk and how the page references
# them. Kept separate from assets/items/ (which mirrors deadlock-api's
# collision-prone basename scheme) so items.json collisions never cause
# one item to display another's icon.
WIKI_ASSET_DIR = ASSETS / "items_wiki"
WIKI_REL_DIR = "assets/items_wiki"
MANIFEST_PATH = CACHE / "wiki_icon_overrides.json"


def wiki_file_title(item_name: str) -> str:
    """'Hunter's Aura' -> 'File:Hunter's Aura.png'. MediaWiki normalizes
    underscores vs spaces on its end. We strip the '- Disabled' suffix
    some patches stamp onto removed items."""
    name = item_name.split(" - Disabled")[0].strip()
    return f"File:{name}.png"


def sanitize_for_filename(item_name: str) -> str:
    """'Hunter's Aura' -> 'hunters_aura'. ASCII-safe lowercase slug we
    use as the local filename — keeps the URL path tidy and side-steps
    cross-platform filename issues with apostrophes / spaces."""
    name = item_name.split(" - Disabled")[0].strip().lower()
    # Strip apostrophes entirely so 'hunters' not 'hunter_s'
    name = name.replace("'", "")
    # Anything that isn't [a-z0-9] becomes a single underscore
    name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return name or "item"


def lookup_urls_batch(titles: list[str]) -> dict[str, str | None]:
    """Query MediaWiki imageinfo for a batch of File: titles. Returns
    {requested_title -> canonical_url_or_None}."""
    qs = urllib.parse.urlencode({
        "action": "query",
        "titles": "|".join(titles),
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json",
        "formatversion": "2",
    })
    url = f"{WIKI_API}?{qs}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    norm_map = {n["from"]: n["to"]
                for n in (data.get("query", {}).get("normalized") or [])}
    pages = data.get("query", {}).get("pages") or []
    page_by_title = {p.get("title"): p for p in pages}
    results: dict[str, str | None] = {}
    for requested in titles:
        resolved = norm_map.get(requested, requested)
        page = page_by_title.get(resolved)
        if page is None or page.get("missing"):
            results[requested] = None
            continue
        ii = page.get("imageinfo") or []
        results[requested] = ii[0]["url"] if ii else None
    return results


def download_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def main() -> None:
    WIKI_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE / "items.json", encoding="utf-8") as f:
        items = json.load(f)

    # Pull EVERY real item, even those with no deadlock-api image —
    # that's how we recover Cultist Sacrifice, which has empty image
    # in items.json but does have a wiki page.
    targets = []  # (item_id, name)
    for it in items:
        if it.get("type") != "upgrade":
            continue
        name = it.get("name")
        if not name or name == it.get("class_name"):
            continue
        if it.get("id") is None:
            continue
        targets.append((it["id"], name))

    print(f"[1/3] Real items in items.json: {len(targets)}")

    # ---- Batch-query the wiki ----
    titles = [wiki_file_title(n) for _, n in targets]
    title_by_iid = {iid: wiki_file_title(n) for iid, n in targets}

    print(f"[2/3] Looking up wiki URLs via MediaWiki API "
          f"({(len(titles) + API_BATCH - 1) // API_BATCH} batched requests)...")
    title_to_url: dict[str, str | None] = {}
    t0 = time.time()
    for i in range(0, len(titles), API_BATCH):
        chunk = titles[i:i + API_BATCH]
        try:
            res = lookup_urls_batch(chunk)
        except Exception as e:
            print(f"  batch {i//API_BATCH + 1} failed: {e}")
            res = {t: None for t in chunk}
        title_to_url.update(res)
    found = sum(1 for v in title_to_url.values() if v)
    print(f"      wiki has icons for {found}/{len(titles)} items "
          f"({time.time()-t0:.1f}s)")

    # ---- Download per-item-id files, build manifest ----
    jobs = []
    for iid, name in targets:
        wiki_url = title_to_url.get(title_by_iid[iid])
        if not wiki_url:
            continue
        slug = sanitize_for_filename(name)
        dest = WIKI_ASSET_DIR / f"{slug}.png"
        rel = f"{WIKI_REL_DIR}/{slug}.png"
        jobs.append((iid, name, wiki_url, dest, rel))

    print(f"[3/3] Downloading {len(jobs)} per-item wiki icons "
          f"to {WIKI_REL_DIR}/ ...")
    t0 = time.time()
    ok = err = skipped_identical = 0
    misses_logged = 0
    manifest: dict[str, str] = {}

    def work(iid: int, name: str, url: str, dest: Path, rel: str):
        try:
            data = download_bytes(url)
        except Exception as e:
            return iid, name, rel, f"error: {e}"
        if len(data) < 100:
            return iid, name, rel, f"too-small ({len(data)}b)"
        if dest.exists() and dest.read_bytes() == data:
            return iid, name, rel, "identical"
        dest.write_bytes(data)
        return iid, name, rel, "ok"

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        futs = [pool.submit(work, *j) for j in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            iid, name, rel, status = fut.result()
            if status in ("ok", "identical"):
                # Manifest entry uses str(iid) so the JSON keys are plain
                # strings (JSON doesn't have integer keys; build_page_data
                # casts back to int on load).
                manifest[str(iid)] = rel
                if status == "ok":
                    ok += 1
                else:
                    skipped_identical += 1
            else:
                err += 1
                if misses_logged < 20:
                    print(f"  [{status}] {name}")
                    misses_logged += 1
            if i % 50 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)}  fresh={ok}  identical={skipped_identical}  "
                      f"err={err}  {time.time()-t0:.1f}s")

    # ---- Save manifest ----
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(f"\n[saved] {MANIFEST_PATH}  ({len(manifest)} item-id overrides)")

    # Items the wiki had nothing for (or that failed to download). They
    # keep whatever deadlock-api ships at items.json.image — which may
    # still be wrong (filename collision) or empty.
    no_wiki = [n for iid, n in targets
               if not title_to_url.get(title_by_iid[iid])]
    if no_wiki:
        print(f"\nNo wiki page found for {len(no_wiki)} items "
              f"(kept deadlock-api icon as fallback):")
        for n in no_wiki[:30]:
            print(f"  - {n}")
        if len(no_wiki) > 30:
            print(f"  ... and {len(no_wiki) - 30} more")

    print(f"\nDone. fresh={ok}, identical={skipped_identical}, "
          f"errors={err}, manifest-size={len(manifest)}")


if __name__ == "__main__":
    main()
