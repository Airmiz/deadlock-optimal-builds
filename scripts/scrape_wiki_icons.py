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
from _paths import CACHE, ASSETS, ROOT


WIKI_API = "https://deadlock.wiki/api.php"
HEADERS = {
    # deadlock.wiki sits behind Cloudflare, which 403s the polite bot UA
    # when requests come from datacenter IPs (every GitHub runner since
    # at least late July 2026 — "batch N failed: HTTP Error 403" across
    # the board). A browser UA passes the filter; if Cloudflare ever
    # tightens further, the merge-preserving manifest logic in main()
    # keeps the page correct on the last-known-good overrides.
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
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


def search_file_variant(item_name: str) -> str | None:
    """Find a File-namespace page whose name equals `item_name` modulo
    case and punctuation. MediaWiki titles are case-sensitive after the
    first character and uploader habits vary — the wiki serves
    'File:Glass cannon v2.png' and 'File:Endless magazine.png', which the
    exact-title imageinfo lookup misses. Accept a search hit only on an
    exact normalized match so we never adopt a lookalike item's art."""
    base = item_name.split(" - Disabled")[0].strip()
    want = re.sub(r"[^a-z0-9]+", "", f"file{base}png".lower())
    qs = urllib.parse.urlencode({
        "action": "query",
        "list": "search",
        "srsearch": base,
        "srnamespace": "6",   # File:
        "srlimit": "5",
        "format": "json",
        "formatversion": "2",
    })
    req = urllib.request.Request(f"{WIKI_API}?{qs}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    for hit in (data.get("query", {}).get("search") or []):
        title = hit.get("title", "")
        if re.sub(r"[^a-z0-9]+", "", title.lower()) == want:
            return title
    return None


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

    # Salvage pass: retry exact-title misses through a File-namespace
    # search that tolerates the wiki's case/punctuation drift. Only runs
    # for the (few) unresolved items, so it adds seconds, not minutes.
    salvaged = 0
    for iid, name in targets:
        t = title_by_iid[iid]
        if title_to_url.get(t):
            continue
        try:
            variant = search_file_variant(name)
            if variant:
                url = lookup_urls_batch([variant]).get(variant)
                if url:
                    title_to_url[t] = url
                    salvaged += 1
        except Exception:
            pass
    if salvaged:
        print(f"      +{salvaged} recovered via case-insensitive File search")

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

    # ---- Merge with the previous manifest (outage-proofing) ----
    # A wiki outage must never SHRINK coverage. On 2026-07-28 Cloudflare
    # 403'd every wiki call from the CI runner, the then-current code
    # saved a 0-entry manifest, and every colliding item on the live
    # page cross-wired. Preserve any previous entry whose item still
    # exists and whose icon file is still on disk, unless this run
    # resolved a fresh one for it. Entries for items that left
    # items.json are dropped naturally.
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            previous = json.load(f)
    except Exception:
        previous = {}
    valid_ids = {str(iid) for iid, _ in targets}
    kept = 0
    for k, rel in previous.items():
        if k in manifest or k not in valid_ids:
            continue
        if (ROOT / rel).exists():
            manifest[k] = rel
            kept += 1
    if kept:
        print(f"      +{kept} entries preserved from previous manifest (wiki gaps)")
    if found == 0 and previous:
        print("      WARNING: wiki lookups all failed this run — "
              "serving last-known-good overrides instead of shrinking")

    # ---- Self-heal collision-prone leftovers from their own CDN art ----
    # Items the wiki doesn't cover yet (typically brand-new patch items)
    # fall back to items.json.image — the shared-basename namespace where
    # unrelated items collide on one assets/items/<basename>.png and end
    # up wearing each other's art (Ancient Shield showed Close Quarters,
    # Apex Combat showed Ricochet, ... after the 05-22/06-30 patches).
    # For any unresolved item whose basename is shared with another item,
    # mirror its OWN CDN image into the per-item-id wiki namespace. The
    # art matches the game files (sometimes a placeholder for fresh
    # items), but no item can cross-wire — and the wiki lookup above
    # still wins automatically once a page appears.
    img_by_iid: dict[int, tuple[str, str]] = {}
    base_count: dict[str, int] = {}
    for it in items:
        if it.get("type") != "upgrade" or not it.get("image"):
            continue
        base = it["image"].rsplit("/", 1)[-1]
        base_count[base] = base_count.get(base, 0) + 1
        if it.get("id") is not None:
            img_by_iid[it["id"]] = (it["image"], base)

    healed = 0
    for iid, name in targets:
        if title_to_url.get(title_by_iid[iid]) or str(iid) in manifest:
            continue
        img, base = img_by_iid.get(iid, (None, None))
        if not img or base_count.get(base, 0) < 2:
            continue  # unique basename → already shows its own art
        slug = sanitize_for_filename(name)
        dest = WIKI_ASSET_DIR / f"{slug}.png"
        rel = f"{WIKI_REL_DIR}/{slug}.png"
        try:
            data = download_bytes(img)
        except Exception as e:
            print(f"  [cdn-fallback error: {e}] {name}")
            continue
        if len(data) < 100:
            continue
        if not (dest.exists() and dest.read_bytes() == data):
            dest.write_bytes(data)
        manifest[str(iid)] = rel
        healed += 1
    if healed:
        print(f"      +{healed} collision-prone items self-healed from their own CDN art")

    # ---- Save manifest ----
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(f"\n[saved] {MANIFEST_PATH}  ({len(manifest)} item-id overrides)")

    # Items with neither a wiki page nor a self-heal override. They keep
    # whatever deadlock-api ships at items.json.image — safe only when
    # the basename is unique to them.
    no_wiki = [n for iid, n in targets
               if not title_to_url.get(title_by_iid[iid])
               and str(iid) not in manifest]
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
