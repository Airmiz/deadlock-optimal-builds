"""
Collect every image URL referenced in our page output, download to a local
assets/ folder, and rewrite page_data.json to use relative paths.

Two refresh knobs:
  - FORCE_ASSETS=1 env var: re-download every icon even if a local copy
    already exists. Useful when Valve rotates icons silently (same URL,
    new bytes) or when assets/items/ has stale-looking PNGs after a
    patch.
  - Sweep collect_urls covers every place items can appear in the
    payload (recommended phases, items_by_slice, joint archetypes,
    match-only resolved archetypes, legacy item-set archetypes, and
    items_dict). A new item that only shows up under an archetype tab
    still gets its icon pulled.
"""
import json
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import (
    ROOT, CACHE, HERO_OUT, HERO_DATA, BUILD_FILES, ASSETS,
    PATCH_ID, PATCH_TITLE, PATCH_MIN_TS, HMMR_BADGE, SPEC_VERSION,
)


FORCE_ASSETS = os.environ.get("FORCE_ASSETS", "").lower() in ("1", "true", "yes")


def collect_urls(data: dict) -> set[tuple[str, str]]:
    """Walk the data and return (url, kind) tuples — kind = 'heroes'|'items'|'abilities'.
    Handles both the legacy single-patch shape and the multi-patch shape with a
    'patches' dict keyed by patch_id.

    Walks every nested location that can hold an item image: recommended
    phases, items_by_slice, joint_archetypes_by_slice items, match-only
    archetype items (when resolved), legacy item-set archetypes, plus
    the patch-level items_dict (the shared lookup table for hero ability
    items and any item referenced only by counter-pick data).
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
                    # Recommended-phase items also carry lineage chains —
                    # the page renders chain ancestors as stage rows too.
                    for c in (it.get("lineage_chain") or []):
                        if c.get("image"):
                            urls.add((c["image"], "items"))
            for slc in ("all", "high", "asc", "eter"):
                for it in (h.get("items_by_slice") or {}).get(slc, []):
                    if it.get("image"):
                        urls.add((it["image"], "items"))
                    # Lineage chain ancestors (pre-buy chips like Extra
                    # Spirit, Extended Magazine, Compress Cooldown) —
                    # without walking these, their icons never end up
                    # in assets/items/ and the page falls back to
                    # T1/T2 placeholder badges.
                    for c in (it.get("lineage_chain") or []):
                        if c.get("image"):
                            urls.add((c["image"], "items"))
            # Joint item+ability archetypes (§3.6) — each archetype has
            # its own items list that may reference icons not in the
            # default recommended view.
            for slc, archs in (h.get("joint_archetypes_by_slice") or {}).items():
                for arch in archs:
                    for it in (arch.get("items") or []):
                        if it.get("image"):
                            urls.add((it["image"], "items"))
            # Match-only archetypes — populated by the resolver workflow
            # with item picks from real player accounts.
            for slc, archs in (h.get("match_only_archetypes_by_slice") or {}).items():
                for arch in archs:
                    for it in (arch.get("items") or []):
                        if it.get("image"):
                            urls.add((it["image"], "items"))
            # Legacy item-set archetypes (kept alongside the new joint
            # ones so users can compare composition-based clustering
            # against ability-priority-based clustering).
            for c in ((h.get("archetypes") or {}).get("clusters") or []):
                for it in (c.get("build") or []):
                    if it.get("image"):
                        urls.add((it["image"], "items"))

    def walk_items_dict(items_dict: dict) -> None:
        """Patch-level items_dict has an `image` per (item_id -> info)
        entry. Hero abilities referenced from counter data, signature
        items, and items only present in matchup panels all come from
        this table — so it must be covered too."""
        for info in (items_dict or {}).values():
            img = info.get("image") if isinstance(info, dict) else None
            if img:
                urls.add((img, "items"))

    if "patches" in data:
        for p in data["patches"].values():
            walk_hero_list(p.get("heroes", []))
            walk_items_dict(p.get("items_dict") or {})
    else:
        walk_hero_list(data.get("heroes", []))
        walk_items_dict(data.get("items_dict") or {})
    # Filter out already-local relative paths (e.g. wiki-overlay paths
    # like 'assets/items_wiki/extra_spirit.png' applied by
    # build_page_data._apply_wiki_overrides). Those are already on disk;
    # trying to urllib.request them as URLs would fail and add noise.
    return {(u, k) for (u, k) in urls if u.startswith("http")}


def local_path(url: str, kind: str) -> Path:
    """Map a URL to its local asset path, preserving the filename."""
    fname = Path(urllib.parse.urlparse(url).path).name
    return ASSETS / kind / fname


def relative_uri(url: str, kind: str) -> str:
    """Path the page should use to reference the local file (relative to the HTML root)."""
    return f"assets/{kind}/{Path(urllib.parse.urlparse(url).path).name}"


def download(url: str, dest: Path) -> tuple[str, str]:
    # FORCE_ASSETS=1 bypasses the local-file shortcut so we re-pull every
    # icon even if it appears cached. Use sparingly — adds ~250 HTTP
    # requests to the run — but necessary when Valve quietly rotates
    # icons in place (the asset URL doesn't change, just the bytes).
    if not FORCE_ASSETS and dest.exists() and dest.stat().st_size > 100:
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
        # Already-relative paths (wiki-overlay overrides from
        # build_page_data._apply_wiki_overrides — e.g.
        # 'assets/items_wiki/extra_spirit.png') are pass-through. They
        # point at on-disk files that scrape_wiki_icons.py wrote, so
        # we must NOT remap them to the assets/<kind>/ namespace.
        if not url.startswith("http"):
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
                    for c in (it.get("lineage_chain") or []):
                        c["image"] = rewrite(c.get("image"))
            for slc in ("all", "high", "asc", "eter"):
                for it in (h.get("items_by_slice") or {}).get(slc, []):
                    it["image"] = rewrite(it.get("image"))
                    # Mirror collect_urls: rewrite chain ancestor image
                    # paths so stage rows render the local (potentially
                    # wiki-overlaid) icon instead of hitting the CDN.
                    for c in (it.get("lineage_chain") or []):
                        c["image"] = rewrite(c.get("image"))
            for slc, archs in (h.get("joint_archetypes_by_slice") or {}).items():
                for arch in archs:
                    for it in (arch.get("items") or []):
                        it["image"] = rewrite(it.get("image"))
            for slc, archs in (h.get("match_only_archetypes_by_slice") or {}).items():
                for arch in archs:
                    for it in (arch.get("items") or []):
                        it["image"] = rewrite(it.get("image"))
            for c in ((h.get("archetypes") or {}).get("clusters") or []):
                for it in (c.get("build") or []):
                    it["image"] = rewrite(it.get("image"))

    def rewrite_items_dict(items_dict: dict) -> None:
        for info in (items_dict or {}).values():
            if isinstance(info, dict) and info.get("image"):
                info["image"] = rewrite(info["image"])

    if "patches" in data:
        for p in data["patches"].values():
            rewrite_hero_list(p.get("heroes", []))
            rewrite_items_dict(p.get("items_dict") or {})
    else:
        rewrite_hero_list(data.get("heroes", []))
        rewrite_items_dict(data.get("items_dict") or {})

    # Overwrite page_data.json so build_page.py picks up the local paths
    out = CACHE / "page_data.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
    print(f"\n[saved] {out}  {out.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
