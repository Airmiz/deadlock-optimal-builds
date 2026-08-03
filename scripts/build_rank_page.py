"""Emit rank_distribution.html — where the playerbase actually sits.

Why this page exists: the whole site slices builds by badge
(Phantom+ = 91, Ascendant+ = 101, Eternus+ = 111), and those cutoffs were
described in the README with hand-waved percentages ("top ~15-20%").
This page measures them instead, straight from
/v1/analytics/badge-distribution, so a reader can see what picking a
higher-MMR tab is actually selecting for — and so the claims on the rest
of the site stay honest as the population shifts (a ranked-season reset
moves everyone).

Two data sources:
  /v1/analytics/badge-distribution — {badge_level, total_matches,
      unique_players} per badge. badge_level is tier*10 + sub-tier, the
      same encoding _paths.py uses for the MMR cutoffs.
  /v1/assets/ranks — tier -> display name, colour and badge art.

The distribution is a live snapshot: the endpoint ignores time bounds
(verified — passing min_unix_timestamp returns identical totals), so
this describes the playerbase now rather than per patch. The page says
so rather than implying otherwise.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ROOT, CACHE, ASSETS, HMMR_BADGE, ASCENDANT_BADGE, ETERNUS_BADGE  # noqa: E402
from batch_fetch import fetch, TTL_ASSETS  # noqa: E402

DIST_URL = "https://api.deadlock-api.com/v1/analytics/badge-distribution"
RANKS_URL = "https://api.deadlock-api.com/v1/assets/ranks"
# The distribution shifts slowly (and resets with a ranked season), so an
# hourly re-pull is plenty; ranks are static art/metadata.
TTL_DIST = 3600


def _load():
    dist_p, ranks_p = CACHE / "badge_distribution.json", CACHE / "ranks.json"
    _, s1 = fetch(DIST_URL, dist_p, ttl=TTL_DIST)
    _, s2 = fetch(RANKS_URL, ranks_p, ttl=TTL_ASSETS)
    print(f"  badge-distribution: {s1} | ranks: {s2}")
    with open(dist_p, encoding="utf-8") as f:
        dist = json.load(f)
    with open(ranks_p, encoding="utf-8") as f:
        ranks = json.load(f)
    if not isinstance(dist, list) or not dist:
        raise SystemExit("badge-distribution returned no rows — refusing to "
                         "emit a rank page that would claim an empty playerbase")
    return dist, {r["tier"]: r for r in ranks}


def _local_badge(tier: int, meta: dict) -> str:
    """Download a tier's badge art and return a repo-relative path.

    Only tier 0 ships a plain `small`; every ranked tier exposes `large`
    plus per-sub-rank variants instead, so a naive images["small"] lookup
    silently yields nothing for 11 of 12 tiers. Prefer whatever exists.

    Localised (rather than hot-linked) to match the rest of the site: the
    page must keep working if the asset CDN moves or goes down.
    """
    imgs = meta.get("images") or {}
    url = imgs.get("small") or imgs.get("small_subrank1") or imgs.get("large")
    if not url:
        return ""
    dest = ASSETS / "ranks" / f"tier{tier:02d}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    _, status = fetch(url, dest, ttl=TTL_ASSETS)
    if status.startswith("error") and not dest.exists():
        print(f"  WARNING: no badge art for tier {tier} ({status})")
        return ""
    return f"assets/ranks/tier{tier:02d}.png"


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def build() -> str:
    dist, ranks_by_tier = _load()
    rows = [d for d in dist if d.get("unique_players") and d.get("badge_level")]
    rows.sort(key=lambda d: d["badge_level"])
    total_players = sum(d["unique_players"] for d in rows)
    total_matches = sum(d.get("total_matches") or 0 for d in rows)

    # Cumulative-from-the-top: the share of players at or above each badge.
    # This is the number that makes the site's MMR tabs meaningful.
    above = {}
    running = 0
    for d in sorted(rows, key=lambda d: -d["badge_level"]):
        running += d["unique_players"]
        above[d["badge_level"]] = running

    def pct_at_or_above(badge):
        # Badges present in the data may skip levels; take the smallest
        # observed badge >= the cutoff so the answer is never overstated.
        cands = [b for b in above if b >= badge]
        return (above[min(cands)] / total_players * 100) if cands else 0.0

    # Aggregate to tiers for the headline chart; sub-tiers are the detail view.
    by_tier = {}
    for d in rows:
        tier = d["badge_level"] // 10
        t = by_tier.setdefault(tier, {"players": 0, "matches": 0, "subs": []})
        t["players"] += d["unique_players"]
        t["matches"] += d.get("total_matches") or 0
        t["subs"].append(d)
    peak = max((t["players"] for t in by_tier.values()), default=1)

    cutoffs = [
        ("Phantom+", HMMR_BADGE, "The site's default view"),
        ("Ascendant+", ASCENDANT_BADGE, ""),
        ("Eternus+", ETERNUS_BADGE, ""),
    ]
    cut_html = "".join(
        f'<div class="cut"><div class="cut-name">{_esc(name)}</div>'
        f'<div class="cut-pct">top {pct_at_or_above(b):.1f}%</div>'
        f'<div class="cut-sub">badge {b}+ · {above.get(min([x for x in above if x >= b], default=b), 0):,} players'
        f'{" · " + _esc(note) if note else ""}</div></div>'
        for name, b, note in cutoffs
    )

    # A ranked-season reset empties the top tiers and they refill over
    # weeks, so "Phantom+ = top 0.3%" can be a true measurement of a
    # transient state rather than a stable fact about the ladder. Detect
    # the tell — a cliff where a tier holds under a tenth of the one below
    # it — and say so, instead of leaving the reader to assume the numbers
    # are broken.
    tiers_desc = sorted(by_tier, reverse=True)
    cliff = None
    for hi, lo in zip(tiers_desc, tiers_desc[1:]):
        p_hi, p_lo = by_tier[hi]["players"], by_tier[lo]["players"]
        if p_lo >= 1000 and p_hi < p_lo * 0.1:
            cliff = (ranks_by_tier.get(lo, {}).get("name", f"tier {lo}"),
                     ranks_by_tier.get(hi, {}).get("name", f"tier {hi}"),
                     p_lo, p_hi)
            break
    reset_note = ""
    if cliff:
        lo_name, hi_name, p_lo, p_hi = cliff
        reset_note = (
            f'<div class="note warn"><strong>The ladder is still refilling.</strong> '
            f'{_esc(lo_name)} holds {p_lo:,} players but {_esc(hi_name)} only {p_hi:,} — '
            f'a cliff that big is the signature of a ranked-season reset, not the '
            f'steady-state ladder. The top-tier percentages above are a correct '
            f'measurement of right now, and will climb back over the coming weeks as '
            f'players re-qualify. It is also why the site\'s Phantom+/Ascendant+/'
            f'Eternus+ build samples are currently thinner than usual.</div>')

    bars = []
    for tier in sorted(by_tier, reverse=True):
        t = by_tier[tier]
        meta = ranks_by_tier.get(tier, {})
        name = meta.get("name", f"Tier {tier}")
        colour = meta.get("color", "#8b94a3")
        img = _local_badge(tier, meta)
        share = t["players"] / total_players * 100
        width = t["players"] / peak * 100
        subs = " ".join(
            f'<span class="sub" title="Badge {s["badge_level"]} — '
            f'{s["unique_players"]:,} players">{s["badge_level"] % 10}</span>'
            for s in sorted(t["subs"], key=lambda s: s["badge_level"])
        )
        bars.append(f"""
        <div class="row">
          <div class="rank">
            {f'<img src="{_esc(img)}" alt="" loading="lazy">' if img else ''}
            <span style="color:{_esc(colour)}">{_esc(name)}</span>
          </div>
          <div class="bar-wrap">
            <div class="bar" style="width:{width:.2f}%;background:{_esc(colour)}"></div>
          </div>
          <div class="num">{share:.1f}%</div>
          <div class="num dim">{t["players"]:,}</div>
          <div class="subs">{subs}</div>
        </div>""")

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rank distribution — Deadlock Optimal Builds</title>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<style>
  :root {{
    --bg:#0e1217; --bg-elev:#161b23; --bg-card:#1c2230; --border:#2a3140;
    --text:#e6e8ec; --text-dim:#8b94a3; --accent:#f0a93b; --good:#58c46c;
  }}
  * {{ box-sizing:border-box; }}
  html,body {{ margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--text); font-size:15px; line-height:1.6;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Inter",sans-serif; }}
  .wrap {{ max-width:960px; margin:0 auto; padding:28px 20px 60px; }}
  h1 {{ font-size:22px; margin:0 0 4px; color:var(--accent); letter-spacing:.5px; }}
  .sub-title {{ color:var(--text-dim); font-size:13px; margin-bottom:18px; }}
  a {{ color:var(--text-dim); }}
  .note {{ background:var(--bg-elev); border:1px solid var(--border); border-radius:8px;
    padding:12px 14px; font-size:13px; color:var(--text-dim); margin:18px 0 22px; }}
  .note.warn {{ border-color:var(--accent); }}
  .note strong {{ color:var(--text); }}
  .cuts {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:26px; }}
  .cut {{ flex:1 1 180px; background:var(--bg-card); border:1px solid var(--border);
    border-radius:8px; padding:12px 14px; }}
  .cut-name {{ font-weight:600; font-size:13px; }}
  .cut-pct {{ font-size:24px; color:var(--accent); font-weight:600; line-height:1.2; }}
  .cut-sub {{ font-size:11px; color:var(--text-dim); }}
  .row {{ display:grid; grid-template-columns:130px 1fr 52px 74px; gap:10px;
    align-items:center; margin-bottom:7px; }}
  .rank {{ display:flex; align-items:center; gap:7px; font-size:13px; font-weight:600; }}
  .rank img {{ width:22px; height:22px; object-fit:contain; }}
  .bar-wrap {{ background:var(--bg-elev); border-radius:4px; height:20px; overflow:hidden; }}
  .bar {{ height:100%; border-radius:4px; min-width:2px; }}
  .num {{ font-size:12px; text-align:right; font-variant-numeric:tabular-nums; }}
  .num.dim {{ color:var(--text-dim); }}
  .subs {{ grid-column:2 / -1; display:flex; gap:3px; margin:-3px 0 4px; }}
  .sub {{ font-size:9px; color:var(--text-dim); background:var(--bg-elev);
    border:1px solid var(--border); border-radius:3px; padding:0 4px; cursor:help; }}
  .foot {{ color:var(--text-dim); font-size:12px; margin-top:26px;
    border-top:1px solid var(--border); padding-top:14px; }}
  @media (max-width:640px) {{
    .row {{ grid-template-columns:104px 1fr 46px; }}
    .num.dim {{ display:none; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <h1>RANK DISTRIBUTION</h1>
  <div class="sub-title">
    <a href="deadlock_builds.html">← Back to builds</a> ·
    <a href="methodology.html">Methodology &amp; glossary</a>
  </div>

  <div class="cuts">{cut_html}</div>

  {reset_note}

  <div class="note">
    <strong>What the MMR tabs actually select.</strong> Every build on this site can be
    filtered by badge, and the percentages above are measured from the live badge
    distribution rather than estimated — so "Phantom+" means exactly the share shown,
    not a rule of thumb. A ranked-season reset moves the whole population, so these
    numbers shift; they are re-measured on every refresh.
  </div>

  {"".join(bars)}

  <div class="foot">
    {total_players:,} ranked players across {total_matches:,} matches ·
    badge = tier x 10 + sub-tier (the small numbers are sub-tiers 1-6) ·
    source: <a href="https://api.deadlock-api.com">deadlock-api.com</a>
    /v1/analytics/badge-distribution ·
    snapshot of the current playerbase, not per patch · generated {generated}
  </div>
</div>
</body>
</html>
"""


def main() -> None:
    print("Building rank distribution page …")
    html = build()
    out = ROOT / "rank_distribution.html"
    out.write_text(html, encoding="utf-8")
    print(f"[saved] {out}  {out.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
