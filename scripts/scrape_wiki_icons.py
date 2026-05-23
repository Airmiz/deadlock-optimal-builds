"""
Overlay item icons from the community-maintained Deadlock wiki on top of
the deadlock-api assets-bucket icons.

Why:
  The deadlock-api icon URLs are stable bucket URLs whose bytes Valve
  occasionally lets go stale on the live game (e.g. after icon redesigns
  shipped in a balance patch). Symptoms: new items show up in the data
  feed with no icon yet, or existing icons silently look like the old
  artwork. FORCE_ASSETS=1 in download_images.py forces a re-download but
  doesn't help when the upstream bytes themselves are out of date.

  The community wiki at https://deadlock.wiki/ is MediaWiki-backed and
  community-maintained, so it tends to ship updated icons within hours
  of a patch landing. We use its MediaWiki API to look up each item's
  canonical file URL and write fresh bytes on top of the local
  assets/items/<deadlock-api-filename>.png that page_data.json already
  references — so no page_data rewrite is needed.

  Items where the wiki page is missing (or the file lookup 404s) are
  left untouched — they keep the deadlock-api icon as a fallback.

When to run:
  - Triggered automatically by refresh.yml when the user ticks the
    `refresh_assets` workflow input. Wiki HTML is stable so we don't
    need to re-scrape every 3 hours.
  - Can also be run locally: `py scripts/scrape_wiki_icons.py`.

Order in the pipeline:
  download_images.py runs first (writes deadlock-api icons), then this
  script runs and overwrites in-place. build_page.py runs after.
"""
import json
import os
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
    # Identify ourselves to be a polite scraper. Deadlock wiki is a
    # community resource so be courteous in the UA string.
    "User-Agent": "deadlock-optimal-builds icon-refresh (https://github.com/Airmiz/deadlock-optimal-builds)",
}

# MediaWiki accepts up to 50 titles per query for non-bot accounts. We
# stay well under that — also keeps URLs short.
API_BATCH = 40
# Conservative — wiki is community-run, no need to hammer.
DOWNLOAD_WORKERS = 5


def wiki_file_title(item_name: str) -> str:
    """Map 'Hunter's Aura' -> 'File:Hunter's Aura.png'. MediaWiki normalizes
    underscores vs spaces and decodes percent-encoding on its end."""
    # Some items have a trailing " - Disabled" suffix (e.g. removed in a
    # patch). Strip it — the wiki page lives under the canonical name.
    name = item_name.split(" - Disabled")[0].strip()
    return f"File:{name}.png"


def local_path_from_api_url(api_url: str) -> Path:
    """The destination filename matches whatever download_images.py would
    have computed — that's the path baked into page_data.json. We just
    write fresh bytes there."""
    fname = Path(urllib.parse.urlparse(api_url).path).name
    return ASSETS / "items" / fname


def lookup_urls_batch(titles: list[str]) -> dict[str, str | None]:
    """Query the MediaWiki imageinfo API for a batch of File: titles.
    Returns {title -> canonical_url_or_None}. None means 'missing'."""
    qs = urllib.parse.urlencode({
        "action": "query",
        "titles": "|".join(titles),
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json",
        "formatversion": "2",  # v2 has cleaner page list
    })
    url = f"{WIKI_API}?{qs}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())

    # Build {requested_title -> resolved_title} so we can match results
    # back even when MediaWiki normalizes (e.g. spaces vs underscores).
    norm_map = {}
    for n in data.get("query", {}).get("normalized", []) or []:
        norm_map[n["from"]] = n["to"]

    results: dict[str, str | None] = {}
    pages = data.get("query", {}).get("pages", []) or []
    # formatversion=2 returns pages as a list with .title
    page_by_title = {p.get("title"): p for p in pages}

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
    with open(CACHE / "items.json", encoding="utf-8") as f:
        items = json.load(f)

    # Filter to "real" items the player buys. Skip:
    #   - ability/weapon entries (type != 'upgrade')
    #   - placeholder rows where name == class_name (the items without
    #     an `image` field — armor_upgrade_tN etc. that aren't shipped)
    targets = []
    for it in items:
        if it.get("type") != "upgrade":
            continue
        name = it.get("name")
        image = it.get("image")
        if not name or not image:
            continue
        if name == it.get("class_name"):
            continue
        targets.append((name, image))

    print(f"[1/3] Real items in items.json: {len(targets)}")

    # ---- Batch-query the wiki API for canonical URLs ----
    titles = [wiki_file_title(n) for n, _ in targets]
    name_to_title = {n: wiki_file_title(n) for n, _ in targets}

    print(f"[2/3] Looking up wiki URLs via MediaWiki API "
          f"({(len(titles) + API_BATCH - 1) // API_BATCH} batched requests)…")
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
    found_in_wiki = sum(1 for v in title_to_url.values() if v)
    print(f"      wiki has icons for {found_in_wiki}/{len(titles)} items "
          f"({time.time()-t0:.1f}s)")

    # ---- Download in parallel, overwrite local files ----
    jobs = []
    for name, api_url in targets:
        wiki_url = title_to_url.get(name_to_title[name])
        if not wiki_url:
            continue
        dest = local_path_from_api_url(api_url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        jobs.append((name, wiki_url, dest))

    print(f"[3/3] Downloading {len(jobs)} wiki icons "
          f"(overwriting deadlock-api versions in-place)…")
    t0 = time.time()
    ok = err = skipped_identical = 0
    misses_logged = 0

    def work(name: str, url: str, dest: Path):
        try:
            data = download_bytes(url)
        except Exception as e:
            return name, f"error: {e}", False
        if len(data) < 100:
            return name, f"too-small ({len(data)}b)", False
        # Skip writing if the bytes are identical — saves needless
        # filesystem churn (and reduces diff noise in the commit).
        if dest.exists() and dest.read_bytes() == data:
            return name, "identical", True
        dest.write_bytes(data)
        return name, "ok", True

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        futs = [pool.submit(work, n, u, d) for n, u, d in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            name, status, success = fut.result()
            if status == "ok":
                ok += 1
            elif status == "identical":
                skipped_identical += 1
            else:
                err += 1
                if misses_logged < 20:
                    print(f"  [{status}] {name}")
                    misses_logged += 1
            if i % 50 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)}  fresh={ok}  identical={skipped_identical}  "
                      f"err={err}  {time.time()-t0:.1f}s")

    # Items the wiki didn't have. Log them but don't fail — they keep
    # the deadlock-api icon.
    missing_in_wiki = [n for n, _ in targets if not title_to_url.get(name_to_title[n])]
    if missing_in_wiki:
        print(f"\nNo wiki page found for {len(missing_in_wiki)} items "
              f"(kept deadlock-api icon):")
        for n in missing_in_wiki[:30]:
            print(f"  - {n}")
        if len(missing_in_wiki) > 30:
            print(f"  … and {len(missing_in_wiki) - 30} more")

    print(f"\nDone. fresh={ok}, identical={skipped_identical}, errors={err}, "
          f"missing-on-wiki={len(missing_in_wiki)}")


if __name__ == "__main__":
    main()
