"""
Collect every image URL referenced in our page output, download to a local
assets/ folder, and rewrite page_data.json to use relative paths.
"""
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import (
    ROOT, CACHE, HERO_OUT, HERO_DATA, BUILD_FILES, ASSETS,
    PATCH_ID, PATCH_TITLE, PATCH_MIN_TS, HMMR_BADGE, SPEC_VERSION,
)



def collect_urls(data: dict) -> set[tuple[str, str]]:
    """Walk the data and return (url, kind) tuples — kind = 'heroes'|'items'|'abilities'.
    Handles both the legacy single-patch shape and the multi-patch shape with a
    'patches' dict keyed by patch_id.
    """
    urls: set[tuple[str, str]] = set()

    def walk_hero_list(heroes: list) -> None:
        for h in heroes:
            if h.get("image"):
                urls.add((h["image"], "heroes"))
            for ab in h.get("abilities", []):
                if ab.get("image"):
                    urls.add((ab["image"], "abilities"))
            for ph in ("early", "mid", "late"):
                for it in h["recommended"]["items"]["phases"][ph]:
                    if it.get("image"):
                        urls.add((it["image"], "items"))
            for slc in ("all", "high"):
                for it in h["items_by_slice"][slc]:
                    if it.get("image"):
                        urls.add((it["image"], "items"))

    if "patches" in data:
        for p in data["patches"].values():
            walk_hero_list(p.get("heroes", []))
    else:
        walk_hero_list(data.get("heroes", []))
    return urls


def local_path(url: str, kind: str) -> Path:
    """Map a URL to its local asset path, preserving the filename."""
    fname = Path(urllib.parse.urlparse(url).path).name
    return ASSETS / kind / fname


def relative_uri(url: str, kind: str) -> str:
    """Path the page should use to reference the local file (relative to the HTML root)."""
    return f"assets/{kind}/{Path(urllib.parse.urlparse(url).path).name}"


def download(url: str, dest: Path) -> tuple[str, str]:
    if dest.exists() and dest.stat().st_size > 100:
        return url, "cached"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "deadlock-build-analysis/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        dest.write_bytes(data)
        return url, "ok"
    except Exception as e:
        return url, f"error: {e}"


def main() -> None:
    with open(CACHE / "page_data.json", encoding="utf-8") as _fh:
        data = json.load(_fh)
    urls = collect_urls(data)
    print(f"Unique image URLs: {len(urls)}")
    by_kind: dict[str, int] = {}
    for u, k in urls:
        by_kind[k] = by_kind.get(k, 0) + 1
    print(f"  by kind: {by_kind}")

    # Download in parallel
    t0 = time.time()
    results = {"cached": 0, "ok": 0, "error": 0}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = {pool.submit(download, u, local_path(u, k)): (u, k) for u, k in urls}
        for i, fut in enumerate(as_completed(futs), 1):
            u, status = fut.result()
            key = "error" if status.startswith("error") else status
            results[key] += 1
            if i % 50 == 0 or i == len(urls):
                print(f"  {i}/{len(urls)}  {results}  {time.time()-t0:.1f}s")
    print(f"\nDownloaded in {time.time()-t0:.1f}s: {results}")

    # Rewrite the data to use relative paths
    url_to_kind = {u: k for u, k in urls}

    def rewrite(url: str | None) -> str | None:
        if not url:
            return url
        kind = url_to_kind.get(url, "items")
        local = local_path(url, kind)
        if local.exists() and local.stat().st_size > 100:
            return relative_uri(url, kind)
        # Fall back to the remote URL if download failed
        return url

    def rewrite_hero_list(heroes: list) -> None:
        for h in heroes:
            h["image"] = rewrite(h.get("image"))
            for ab in h.get("abilities", []):
                ab["image"] = rewrite(ab.get("image"))
            for ph in ("early", "mid", "late"):
                for it in h["recommended"]["items"]["phases"][ph]:
                    it["image"] = rewrite(it.get("image"))
            for slc in ("all", "high"):
                for it in h["items_by_slice"][slc]:
                    it["image"] = rewrite(it.get("image"))

    if "patches" in data:
        for p in data["patches"].values():
            rewrite_hero_list(p.get("heroes", []))
    else:
        rewrite_hero_list(data.get("heroes", []))

    # Overwrite page_data.json so build_page.py picks up the local paths
    out = CACHE / "page_data.json"
    with open(out, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"\n[saved] {out}  {out.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
