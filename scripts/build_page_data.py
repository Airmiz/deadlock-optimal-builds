"""
Compile all 38 hero output files + asset metadata into one compact JS object
for the static HTML page. Output is roughly 250–400 KB embedded inline.
"""
import json
import re
from pathlib import Path
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import (
    ROOT, CACHE, HERO_OUT, HERO_DATA, BUILD_FILES, ASSETS,
    PATCH_ID, PATCH_TITLE, PATCH_MIN_TS, HMMR_BADGE, SPEC_VERSION,
)



def slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()


# Asset look-ups
heroes_assets = {h["id"]: h for h in json.load(open(CACHE / "heroes.json"))}
items_assets = {i["id"]: i for i in json.load(open(CACHE / "items.json"))}

# Build per-item lookup with name + tier + cost + category + image
def item_info(iid: int) -> dict:
    it = items_assets.get(iid, {})
    return {
        "name": it.get("name", "?"),
        "tier": it.get("item_tier"),
        "cost": it.get("cost"),
        "category": it.get("item_slot_type"),
        "image": it.get("image"),
    }


def hero_image(hid: int) -> str | None:
    h = heroes_assets.get(hid, {})
    imgs = h.get("images", {})
    return imgs.get("icon_hero_card_webp") or imgs.get("icon_hero_card") or imgs.get("icon_image_small_webp")


def compact_hero(d: dict) -> dict:
    """Take a full hero output and pull just what the page needs."""
    hid = d["hero"]["id"]
    name = d["hero"]["name"]
    h = heroes_assets.get(hid, {})

    out = {
        "id": hid,
        "name": name,
        "image": hero_image(hid),
        "abilities": [
            {"id": a["id"], "name": a["name"],
             "image": items_assets.get(a["id"], {}).get("image")}
            for a in d["hero"]["abilities"]
        ],
        "mmr": {
            "all": {"wr": d["mmr_slices"]["all_mmr"]["baseline_win_rate"],
                    "matches": d["mmr_slices"]["all_mmr"]["matches"],
                    "players": d["mmr_slices"]["all_mmr"]["players"]},
            "high": {"wr": d["mmr_slices"]["high_mmr"]["baseline_win_rate"],
                     "matches": d["mmr_slices"]["high_mmr"]["matches"],
                     "players": d["mmr_slices"]["high_mmr"]["players"]},
        },
        "recommended": {
            "items": {
                "method": d["recommended"]["items"]["method"],
                "mmr_slice": d["recommended"]["items"]["mmr_slice"],
                "total_cost": d["recommended"]["items"]["total_cost"],
                "phases": {
                    ph: [{
                        "slot": p["slot"],
                        "name": p["name"],
                        "category": p["category"],
                        "tier": p["tier"],
                        "cost": p["cost"],
                        "buy_min": p["avg_buy_time_min"],
                        "wr": p["win_rate"],
                        "image": items_assets.get(p["item_id"], {}).get("image"),
                        "tag": p.get("tag", "stat"),
                        "pick_rate": p.get("pick_rate", 0.0),
                        "annotation": p.get("annotation", ""),
                    } for p in d["recommended"]["items"]["phases"][ph]]
                    for ph in ("early", "mid", "late")
                },
            },
            "abilities": d["recommended"]["abilities"],
        },
        # Per-MMR-slice ability breakdown so the page can offer a toggle
        "ability_orders": {
            slice_label: {
                "priority": d["ability_orders"][src]["ability_priority"],
                "best_full": d["ability_orders"][src]["best_full_orders"][0]
                    if d["ability_orders"][src]["best_full_orders"] else None,
                "best_opener": d["ability_orders"][src]["best_openers_first4"][0]
                    if d["ability_orders"][src]["best_openers_first4"] else None,
                "alternate_openers": d["ability_orders"][src]["best_openers_first4"][1:4],
                "alternate_fulls": d["ability_orders"][src]["best_full_orders"][1:4],
            }
            for slice_label, src in (("all", "all_mmr"), ("high", "high_mmr"))
        },
        # Per-MMR-slice item breakdown using the synergy ILP picks (the recommended method)
        "items_by_slice": {
            slice_label: [{
                "slot": p["slot"], "name": p["name"], "category": p["category"],
                "tier": p["tier"], "cost": p["cost"],
                "buy_min": round(p["avg_buy_time_s"] / 60, 1),
                "wr": p["win_rate"], "phase": p["phase"],
                "image": items_assets.get(p["item_id"], {}).get("image"),
                "tag": p.get("tag", "stat"),
                "pick_rate": p.get("pick_rate", 0.0),
                "annotation": p.get("annotation", ""),
            } for p in d["items"][src]["synergy_ilp"]["picks"]]
            for slice_label, src in (("all", "all_mmr"), ("high", "high_mmr"))
        },
    }
    return out


def main() -> None:
    heroes_data = []
    for f in sorted(HERO_OUT.glob("*_build.json")):
        d = json.load(open(f))
        heroes_data.append(compact_hero(d))

    # Sort alphabetically by name for stable display, but the page can re-sort
    heroes_data.sort(key=lambda h: h["name"])

    # Compute meta-level data: tier list (by high-MMR WR)
    tier = sorted(heroes_data, key=lambda h: -h["mmr"]["high"]["wr"])

    page_data = {
        "spec_version": "1.0.0",
        "patch": {"id": "patch_125825", "title": "04-10-2026 Update"},
        "data_source": "api.deadlock-api.com",
        "heroes": heroes_data,
        "tier_order_ids": [h["id"] for h in tier],
    }

    target = CACHE / "page_data.json"
    with open(target, "w") as f:
        json.dump(page_data, f, separators=(",", ":"))
    size = target.stat().st_size
    print(f"[saved] {target}  {size:,} bytes  ({size/1024:.1f} KB)")
    print(f"  {len(heroes_data)} heroes")


if __name__ == "__main__":
    main()
