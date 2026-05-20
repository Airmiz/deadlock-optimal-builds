"""
Aggregate the 38 per-hero outputs into a single index + tier-list views.
"""
import json
import csv
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


hero_files = sorted(HERO_OUT.glob("*_build.json"))
print(f"Loading {len(hero_files)} hero output files...")

heroes = []
for f in hero_files:
    with open(f, encoding="utf-8") as fh:
        d = json.load(fh)
    rec = d["recommended"]
    rec_items = rec["items"]
    rec_ab = rec["abilities"]
    best_full = rec_ab.get("best_full_order")
    best_op = rec_ab.get("best_opener_first4")

    # Build a "consensus core" — items in all 3 high-MMR methods
    methods = d["items"]["high_mmr"]
    sets = []
    for m in ("wilson_greedy", "synergy_ilp", "build_replication"):
        sets.append({p["item_id"] for p in methods[m]["picks"]})
    consensus_ids = sets[0] & sets[1] & sets[2]
    name_map = {p["item_id"]: p["name"] for p in methods["synergy_ilp"]["picks"]}
    consensus = sorted([name_map[i] for i in consensus_ids if i in name_map])

    asc_slice = d["mmr_slices"].get("ascendant_plus")
    eter_slice = d["mmr_slices"].get("eternus_plus")
    heroes.append({
        "id": d["hero"]["id"],
        "name": d["hero"]["name"],
        "file": f"heroes/{f.name}",
        "all_mmr_baseline_wr": d["mmr_slices"]["all_mmr"]["baseline_win_rate"],
        "all_mmr_matches": d["mmr_slices"]["all_mmr"]["matches"],
        "all_mmr_players": d["mmr_slices"]["all_mmr"]["players"],
        "high_mmr_baseline_wr": d["mmr_slices"]["high_mmr"]["baseline_win_rate"],
        "high_mmr_matches": d["mmr_slices"]["high_mmr"]["matches"],
        "high_mmr_players": d["mmr_slices"]["high_mmr"]["players"],
        "ascendant_plus_baseline_wr": (asc_slice or {}).get("baseline_win_rate"),
        "ascendant_plus_matches": (asc_slice or {}).get("matches", 0),
        "ascendant_plus_players": (asc_slice or {}).get("players", 0),
        "eternus_plus_baseline_wr": (eter_slice or {}).get("baseline_win_rate"),
        "eternus_plus_matches": (eter_slice or {}).get("matches", 0),
        "eternus_plus_players": (eter_slice or {}).get("players", 0),
        "wr_lift_high_mmr_pp": round((d["mmr_slices"]["high_mmr"]["baseline_win_rate"]
                                     - d["mmr_slices"]["all_mmr"]["baseline_win_rate"]) * 100, 2),
        "candidates_all": d["items"]["all_mmr"]["candidate_count"],
        "candidates_hmmr": d["items"]["high_mmr"]["candidate_count"],
        "candidates_asc": d["items"].get("ascendant_plus", {}).get("candidate_count", 0),
        "candidates_eter": d["items"].get("eternus_plus", {}).get("candidate_count", 0),
        "recommended_total_cost": rec_items["total_cost"],
        "recommended_phases_count": {ph: len(rec_items["phases"][ph]) for ph in ("early","mid","late")},
        "ap_priority": rec_ab["ap_priority_order"],
        "best_full_order_wr": (best_full or {}).get("win_rate"),
        "best_full_order_n":  (best_full or {}).get("matches"),
        "best_opener": (best_op or {}).get("sequence_names"),
        "best_opener_wr": (best_op or {}).get("win_rate"),
        "consensus_core_count": len(consensus),
        "consensus_core_items": consensus,
    })

# Sort by high-MMR baseline WR descending — a soft tier list
heroes_sorted = sorted(heroes, key=lambda h: -h["high_mmr_baseline_wr"])

index = {
    "spec_version": SPEC_VERSION,
    "patch": PATCH_ID,
    "patch_title": PATCH_TITLE,
    "hero_count": len(heroes),
    "data_source": "api.deadlock-api.com",
    "heroes": heroes_sorted,
}
with open(ROOT / "all_heroes_index.json", "w", encoding="utf-8") as f:
    json.dump(index, f, indent=2)
print(f"[saved] {ROOT/'all_heroes_index.json'}")

# CSV — flat tier list
with open(ROOT / "all_heroes_tier_list.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["rank","hero","id","high_mmr_wr","all_mmr_wr","wr_lift_pp",
                "high_mmr_matches","high_mmr_players","candidates_hmmr",
                "recommended_cost","ap_priority","best_full_order_wr","best_full_order_n",
                "best_opener","best_opener_wr","consensus_core_items"])
    for i, h in enumerate(heroes_sorted, 1):
        w.writerow([
            i, h["name"], h["id"],
            f"{h['high_mmr_baseline_wr']*100:.2f}%",
            f"{h['all_mmr_baseline_wr']*100:.2f}%",
            f"{h['wr_lift_high_mmr_pp']:+.2f}",
            h["high_mmr_matches"], h["high_mmr_players"], h["candidates_hmmr"],
            h["recommended_total_cost"],
            " > ".join(h["ap_priority"]),
            f"{h['best_full_order_wr']*100:.2f}%" if h.get("best_full_order_wr") is not None else "",
            h.get("best_full_order_n") or "",
            " → ".join(h["best_opener"]) if h.get("best_opener") else "",
            f"{h['best_opener_wr']*100:.2f}%" if h.get("best_opener_wr") is not None else "",
            "; ".join(h["consensus_core_items"]),
        ])
print(f"[saved] {ROOT/'all_heroes_tier_list.csv'}")

# Print top 5 / bottom 5 for the chat summary
print("\n=== Top 5 by high-MMR baseline WR ===")
for h in heroes_sorted[:5]:
    print(f"  {h['name']:<14} WR={h['high_mmr_baseline_wr']*100:5.2f}%  n={h['high_mmr_matches']:>6,}  AP: {' > '.join(h['ap_priority'])}")
print("\n=== Bottom 5 ===")
for h in heroes_sorted[-5:]:
    print(f"  {h['name']:<14} WR={h['high_mmr_baseline_wr']*100:5.2f}%  n={h['high_mmr_matches']:>6,}  AP: {' > '.join(h['ap_priority'])}")

# Heroes flagged as low-data
low = [h for h in heroes if h["candidates_hmmr"] < 50 or h["high_mmr_matches"] < 2000]
if low:
    print(f"\n=== Low-data flags ({len(low)}) ===")
    for h in low:
        print(f"  {h['name']:<14} candidates_hmmr={h['candidates_hmmr']}  matches_hmmr={h['high_mmr_matches']:,}")
