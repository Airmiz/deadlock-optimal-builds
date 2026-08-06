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
      same encoding _paths.py uses for the MMR cutoffs. The feed also
      contains bookkeeping rows that are not real ranks (sub-tiers 7-9
      and x0 levels, always zero players) — filtered here.
  /v1/assets/ranks — tier -> display name, colour and badge art.

The distribution is a live snapshot: the endpoint ignores time bounds
(verified — passing min_unix_timestamp returns identical totals), so
this describes the playerbase now rather than per patch. The page says
so rather than implying otherwise.

Chart design notes (the page was once a wall of horizontal bars and
unlabeled sub-tier chips; readers found it illegible):
  - One ascending histogram, lowest rank left to highest right — the
    distribution's shape (and a season-reset cliff) is visible at a
    glance. Tiers with zero players still get a column: "Eternus: 0"
    is information, hiding the column made the page look broken.
  - Every column cap carries its share, so no y-axis chrome is needed;
    exact counts live in the table below (each rank expandable to its
    sub-ranks) — hover is an enhancement, never the only path.
  - Rank colours are the game's own. They are decoration-with-
    recognition here, never the identity channel (position, badge art,
    name and the table do that): several canonical colours are
    near-invisible or neon on this background, so fills are nudged into
    a legible luminance band while keeping the hue.
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

# Histogram geometry (px). Heights are computed server-side so the CSS
# stays trivial and the columns can't drift from their data.
BAR_AREA_H = 230          # tallest column
BAR_W = 24                # mark thickness cap
SEG_GAP = 2               # surface gap between stacked sub-rank segments
SPLIT_MIN_H = 34          # don't split a column shorter than this into segments


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


# ---------------------------------------------------------------- colour --

def _hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(rgb_a, rgb_b):
    la, lb = _lum(rgb_a), _lum(rgb_b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _mix(rgb, other, t):
    return tuple(round(a + (b - a) * t) for a, b in zip(rgb, other))


_SURFACE = _hex_rgb("0e1217")  # --bg, the surface the columns sit on


def _fill(colour: str) -> str:
    """Nudge a canonical rank colour into a legible band on the dark surface.

    Several official colours are near-black on this background (Initiate
    #6A3E1E lands at 2.1:1) and one is neon (Eternus #5CE9A9 at ~12:1);
    as large fills both read as broken. Hue is kept — the point is
    recognition, not re-branding — only luminance is pulled into range.
    """
    try:
        rgb = _hex_rgb(colour)
    except Exception:
        return "#8b94a3"
    for _ in range(20):
        c = _contrast(rgb, _SURFACE)
        if c < 2.6:
            rgb = _mix(rgb, (255, 255, 255), 0.06)
        elif c > 8.0:
            rgb = _mix(rgb, _SURFACE, 0.08)
        else:
            break
    return "#{:02x}{:02x}{:02x}".format(*rgb)


# ------------------------------------------------------------- formatting --

def _fmt_pct(p: float, dash_zero: bool = False) -> str:
    """Adaptive precision so small-but-real shares never print as '0.0%'."""
    if p == 0:
        return "—" if dash_zero else "0%"
    if p >= 0.1:
        return f"{p:.1f}%"
    if p >= 0.01:
        return f"{p:.2f}%"
    return "<0.01%"


def _fmt_cap(p: float) -> str:
    """Column-cap label: compact, never a lying zero."""
    if p == 0:
        return "0"
    if p >= 0.1:
        return f'{p:.1f}<span class="u">%</span>'
    return '&lt;0.1<span class="u">%</span>'


def _one_in(total: int, players: int) -> str:
    if not players:
        return ""
    n = total / players
    if n < 2:
        return ""
    if n >= 100:  # two significant figures is plenty for a rarity figure
        mag = 10 ** (len(str(round(n))) - 2)
        n = round(n / mag) * mag
        return f"≈1 in {n:,.0f}"
    return f"≈1 in {n:.0f}"


# ------------------------------------------------------------------ build --

def build() -> str:
    dist, ranks_by_tier = _load()
    # Real badges only: tier >= 1, sub-tier 1..6. The feed also carries
    # zero-player bookkeeping rows (sub 7-9, x0) — drop by shape, and keep
    # legitimate ranks even when a season reset empties them.
    rows = [d for d in dist
            if (d.get("badge_level") or 0) >= 11 and 1 <= d["badge_level"] % 10 <= 6]
    rows.sort(key=lambda d: d["badge_level"])
    total_players = sum(d.get("unique_players") or 0 for d in rows)
    total_matches = sum(d.get("total_matches") or 0 for d in rows)
    if not total_players:
        raise SystemExit("badge-distribution has zero players everywhere — "
                         "refusing to emit an empty rank page")

    # Cumulative-from-the-top: players at or above each badge level. This is
    # the number that makes the site's MMR tabs meaningful.
    above = {}
    running = 0
    for d in sorted(rows, key=lambda d: -d["badge_level"]):
        running += d.get("unique_players") or 0
        above[d["badge_level"]] = running

    def players_at_or_above(badge):
        cands = [b for b in above if b >= badge]
        return above[min(cands)] if cands else 0

    def pct_at_or_above(badge):
        return players_at_or_above(badge) / total_players * 100

    # Aggregate to tiers for the histogram; sub-tiers are the detail view.
    by_tier = {}
    for d in rows:
        tier = d["badge_level"] // 10
        t = by_tier.setdefault(tier, {"players": 0, "matches": 0, "subs": []})
        t["players"] += d.get("unique_players") or 0
        t["matches"] += d.get("total_matches") or 0
        if d.get("unique_players"):
            t["subs"].append(d)

    # Show every tier the ladder defines, populated or not: after a season
    # reset the top tiers really do hold ~nobody, and an honest zero column
    # beats a silently missing rank (the cutoff tiles reference Eternus
    # even when it is empty).
    hi_tier = max(max(by_tier, default=1), ETERNUS_BADGE // 10)
    tiers = list(range(1, hi_tier + 1))
    for t in tiers:
        by_tier.setdefault(t, {"players": 0, "matches": 0, "subs": []})
    peak = max(t["players"] for t in by_tier.values()) or 1
    hmmr_tier = HMMR_BADGE // 10

    def tier_name(t):
        return ranks_by_tier.get(t, {}).get("name", f"Tier {t}")

    def tier_pct(t):
        return by_tier[t]["players"] / total_players * 100

    def tier_top_pct(t):
        return sum(by_tier[x]["players"] for x in tiers if x >= t) / total_players * 100

    # ---- cutoff tiles ----------------------------------------------------
    cutoffs = [
        ("Phantom+", HMMR_BADGE, "the site's default view"),
        ("Ascendant+", ASCENDANT_BADGE, ""),
        ("Eternus+", ETERNUS_BADGE, ""),
    ]
    tiles = []
    for name, badge, note in cutoffs:
        pl = players_at_or_above(badge)
        pct = pct_at_or_above(badge)
        if pl:
            value = f"top {_fmt_pct(pct)}"
            bits = [f"{pl:,} players", _one_in(total_players, pl)]
        else:
            value = "top —"
            bits = ["no players at this badge yet"]
        bits.append(f"badge {badge}+")
        tiles.append(
            f'<div class="cut"><div class="cut-name">{_esc(name)}'
            f'{f" <span>· {_esc(note)}</span>" if note else ""}</div>'
            f'<div class="cut-pct">{value}</div>'
            f'<div class="cut-sub">{" · ".join(b for b in bits if b)}</div></div>')
    cut_html = "".join(tiles)

    # ---- season-reset detection ------------------------------------------
    # A ranked-season reset empties the top tiers and they refill over
    # weeks, so "Phantom+ = top 0.3%" can be a true measurement of a
    # transient state rather than a stable fact about the ladder. Detect
    # the tell — a cliff where a tier holds under a tenth of the one below
    # it — and say so, instead of leaving the reader to assume the numbers
    # are broken.
    cliff = None
    for hi, lo in zip(sorted(tiers, reverse=True), sorted(tiers, reverse=True)[1:]):
        p_hi, p_lo = by_tier[hi]["players"], by_tier[lo]["players"]
        if p_lo >= 1000 and p_hi < p_lo * 0.1:
            cliff = (tier_name(lo), tier_name(hi), p_lo, p_hi)
            break
    reset_note = ""
    if cliff:
        lo_name, hi_name, p_lo, p_hi = cliff
        reset_note = (
            f'<div class="note warn"><strong>The ladder is still refilling after a '
            f'ranked-season reset.</strong> {_esc(lo_name)} holds {p_lo:,} players but '
            f'{_esc(hi_name)} only {p_hi:,} — a reset empties the top tiers, and they '
            f're-fill over weeks as players re-qualify. The percentages here are a '
            f'correct measurement of <em>right now</em>; it is also why the '
            f'Phantom+/Ascendant+/Eternus+ build samples are currently thin.</div>')

    # ---- histogram -------------------------------------------------------
    ncols = len(tiers)
    cols = []
    for i, t in enumerate(tiers):
        d = by_tier[t]
        meta = ranks_by_tier.get(t, {})
        name = tier_name(t)
        fill = _fill(meta.get("color", "#8b94a3"))
        img = _local_badge(t, meta)
        share = tier_pct(t)
        h = round(share / (peak / total_players * 100) * BAR_AREA_H) if d["players"] else 0
        h = max(h, 2) if d["players"] else 0

        # Stacked sub-rank segments (1 bottom -> 6 top) with 2px surface
        # gaps; columns too short to split stay one block — their split
        # lives in the table.
        subs = sorted(d["subs"], key=lambda s: s["badge_level"])
        segs_html = ""
        if h >= SPLIT_MIN_H and len(subs) > 1:
            usable = h - (len(subs) - 1) * SEG_GAP
            seg_hs = [max(1, round(s["unique_players"] / d["players"] * usable)) for s in subs]
            seg_hs[seg_hs.index(max(seg_hs))] += usable - sum(seg_hs)  # keep total exact
            parts = []
            for s, sh in reversed(list(zip(subs, seg_hs))):  # DOM top-first
                sub_n = s["badge_level"] % 10
                parts.append(
                    f'<div class="seg" style="height:{sh}px;background:{fill}" '
                    f'data-tip="{_esc(name)} {sub_n} · badge '
                    f'{s["badge_level"]} · {s["unique_players"]:,} players"></div>')
            segs_html = "".join(parts)
        elif h:
            segs_html = f'<div class="seg" style="height:{h}px;background:{fill}"></div>'

        radius = 4 if h >= 12 else 1
        tip = (f'{name} · {d["players"]:,} players · {_fmt_pct(share)} of ranked · '
               f'top {_fmt_pct(tier_top_pct(t), dash_zero=True)}'
               if d["players"] else f"{name} · no players yet")
        cols.append(f"""
      <div class="col" tabindex="0" data-tip="{_esc(tip)}" aria-label="{_esc(tip)}">
        <div class="bar-area"><span class="cap">{_fmt_cap(share)}</span>
          <div class="stack" style="border-radius:{radius}px {radius}px 0 0">{segs_html}</div>
        </div>
        <div class="xlab">{f'<img src="{_esc(img)}" alt="" loading="lazy">' if img else ''}
          <span class="cname">{_esc(name)}</span>
        </div>
      </div>""")

    # Accent wash tying the chart to the tiles: everything from the Phantom
    # column rightward is what the site's default "Phantom+" tab selects.
    wash_i = tiers.index(hmmr_tier) if hmmr_tier in tiers else None
    wash = ""
    if wash_i is not None:
        left = wash_i / ncols * 100
        wash = (f'<div class="wash" style="left:{left:.3f}%;width:{100 - left:.3f}%">'
                f'<span>Phantom+</span></div>')

    chart_html = f"""
  <div class="chart-head">
    <h2>Players by rank</h2>
    <div class="chart-meta">{total_players:,} ranked players · lowest rank on the left</div>
  </div>
  <div class="chart" aria-label="Histogram of ranked players by rank tier; the same numbers are in the table below.">
    <div class="plot">{wash}{"".join(cols)}
    </div>
  </div>
  <div class="chart-cap">Column = share of all ranked players at that rank. Big columns are
    split into sub-ranks 1–6, bottom to top — hover one, or use the table below, for exact
    counts. The tinted zone is what the site's Phantom+ filter selects.</div>"""

    # ---- table (the exact-numbers twin of the chart) ---------------------
    trows = []
    for t in sorted(tiers, reverse=True):
        d = by_tier[t]
        meta = ranks_by_tier.get(t, {})
        name = tier_name(t)
        img = _local_badge(t, meta)
        icon = f'<img src="{_esc(img)}" alt="">' if img else ""
        in_sample = t >= hmmr_tier
        subs = sorted(d["subs"], key=lambda s: -s["badge_level"])
        sub_rows = "".join(
            f'<div class="srow"><div>{_esc(name)} {s["badge_level"] % 10}'
            f'<span class="dim"> · badge {s["badge_level"]}</span></div>'
            f'<div class="tnum">{s["unique_players"]:,}</div>'
            f'<div class="tnum">{_fmt_pct(s["unique_players"] / total_players * 100)}</div>'
            f'<div class="tnum dim">{_fmt_pct(above[s["badge_level"]] / total_players * 100)}</div></div>'
            for s in subs)
        row_cells = (
            f'<span class="rname">{icon}{_esc(name)}</span>'
            f'<span class="tnum">{d["players"]:,}</span>'
            f'<span class="tnum">{_fmt_pct(tier_pct(t))}</span>'
            f'<span class="tnum">{_fmt_pct(tier_top_pct(t), dash_zero=True)}</span>')
        if subs:
            trows.append(
                f'<details class="trow{" hl" if in_sample else ""}">'
                f'<summary><span class="chev">▸</span>{row_cells}</summary>'
                f'<div class="subtbl">{sub_rows}</div></details>')
        else:
            trows.append(
                f'<div class="trow flat{" hl" if in_sample else ""}">'
                f'<span class="chev"></span>{row_cells}</div>')

    table_html = f"""
  <div class="tbl" role="table" aria-label="Rank distribution, exact numbers">
    <div class="thead"><span class="chev"></span><div>Rank</div><div class="tnum">Players</div>
      <div class="tnum">Share</div><div class="tnum" title="Players at this rank or higher">Top</div></div>
    {"".join(trows)}
  </div>
  <div class="tbl-cap">Click a rank for its sub-ranks 1–6. <span class="hl-key"></span> = included in
    the site's Phantom+ sample. "Top" = players at that rank <em>or higher</em>.</div>"""

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
  h2 {{ font-size:15px; margin:0; }}
  .sub-title {{ color:var(--text-dim); font-size:13px; margin-bottom:6px; }}
  .intro {{ color:var(--text-dim); font-size:13px; margin:0 0 18px; max-width:720px; }}
  a {{ color:var(--text-dim); }}
  .note {{ background:var(--bg-elev); border:1px solid var(--border); border-radius:8px;
    padding:12px 14px; font-size:13px; color:var(--text-dim); margin:18px 0 8px; }}
  .note.warn {{ border-color:var(--accent); }}
  .note strong {{ color:var(--text); }}

  .cuts {{ display:flex; gap:12px; flex-wrap:wrap; }}
  .cut {{ flex:1 1 180px; background:var(--bg-card); border:1px solid var(--border);
    border-radius:8px; padding:12px 14px; }}
  .cut-name {{ font-weight:600; font-size:13px; }}
  .cut-name span {{ color:var(--text-dim); font-weight:400; font-size:12px; }}
  .cut-pct {{ font-size:26px; color:var(--accent); font-weight:600; line-height:1.25; }}
  .cut-sub {{ font-size:11.5px; color:var(--text-dim); }}

  .chart-head {{ display:flex; align-items:baseline; justify-content:space-between;
    gap:12px; margin:30px 0 4px; flex-wrap:wrap; }}
  .chart-meta {{ color:var(--text-dim); font-size:12px; }}
  .chart {{ position:relative; }}
  .plot {{ display:flex; align-items:flex-end; gap:10px; position:relative; }}
  .plot::after {{ content:""; position:absolute; left:0; right:0;
    top:{BAR_AREA_H + 22}px; height:1px; background:var(--border); }}
  .wash {{ position:absolute; top:0; height:{BAR_AREA_H + 22}px;
    background:rgba(240,169,59,.028); border-left:1px solid rgba(240,169,59,.28); }}
  .wash span {{ position:absolute; top:2px; left:7px; font-size:10.5px; letter-spacing:.4px;
    color:rgba(240,169,59,.75); white-space:nowrap; }}
  .col {{ flex:1 1 0; min-width:0; display:flex; flex-direction:column; align-items:center;
    position:relative; border-radius:4px; }}
  .col:focus-visible {{ outline:1px solid var(--accent); outline-offset:2px; }}
  .bar-area {{ height:{BAR_AREA_H + 22}px; display:flex; flex-direction:column;
    justify-content:flex-end; align-items:center; }}
  .cap {{ font-size:11px; color:var(--text-dim); margin-bottom:3px;
    font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .col:hover .cap, .col:focus-visible .cap {{ color:var(--text); }}
  .stack {{ width:{BAR_W}px; overflow:hidden; display:flex; flex-direction:column;
    justify-content:flex-end; }}
  .seg {{ width:100%; margin-top:{SEG_GAP}px; }}
  .seg:first-child {{ margin-top:0; }}
  .col:hover .seg {{ filter:brightness(1.18); }}
  .seg:hover {{ filter:brightness(1.45) !important; }}
  .xlab {{ display:flex; flex-direction:column; align-items:center; gap:2px;
    padding-top:7px; min-height:52px; }}
  .xlab img {{ width:24px; height:24px; object-fit:contain; }}
  .cname {{ font-size:10.5px; color:var(--text-dim); white-space:nowrap; }}

  .chart-cap, .tbl-cap {{ color:var(--text-dim); font-size:12px; margin:10px 0 0;
    max-width:720px; }}

  .tbl {{ margin-top:30px; border:1px solid var(--border); border-radius:8px;
    overflow:hidden; font-size:13px; }}
  .thead, .trow.flat, .trow summary {{ display:grid;
    grid-template-columns:22px minmax(110px,1.4fr) 1fr 1fr 1fr; gap:8px;
    align-items:center; padding:7px 12px 7px 8px; }}
  .thead {{ background:var(--bg-elev); color:var(--text-dim); font-size:11px;
    text-transform:uppercase; letter-spacing:.6px; }}
  .trow {{ border-top:1px solid var(--border); }}
  .trow summary {{ cursor:pointer; list-style:none; }}
  .trow summary::-webkit-details-marker {{ display:none; }}
  .trow summary:hover, .trow.flat:hover {{ background:var(--bg-elev); }}
  .chev {{ color:var(--text-dim); font-size:10px; transition:transform .12s; text-align:center; }}
  .trow[open] .chev {{ transform:rotate(90deg); }}
  .trow.hl {{ box-shadow:inset 2px 0 0 var(--accent); background:rgba(240,169,59,.04); }}
  .rname {{ display:flex; align-items:center; gap:8px; font-weight:600; min-width:0; }}
  .rname img {{ width:20px; height:20px; object-fit:contain; }}
  .tnum {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .dim {{ color:var(--text-dim); font-weight:400; }}
  .subtbl {{ padding:2px 12px 8px 30px; }}
  .srow {{ display:grid; grid-template-columns:minmax(102px,1.4fr) 1fr 1fr 1fr; gap:8px;
    padding:3px 0; color:var(--text-dim); font-size:12.5px; }}
  .srow > div:first-child {{ color:var(--text); }}
  .hl-key {{ display:inline-block; width:9px; height:9px; border-radius:2px;
    background:rgba(240,169,59,.25); box-shadow:inset 2px 0 0 var(--accent); }}

  .tip {{ position:fixed; z-index:10; background:var(--bg-card); border:1px solid var(--border);
    border-radius:6px; padding:6px 9px; font-size:12px; pointer-events:none; display:none;
    max-width:260px; box-shadow:0 4px 14px rgba(0,0,0,.45); }}
  .foot {{ color:var(--text-dim); font-size:12px; margin-top:26px;
    border-top:1px solid var(--border); padding-top:14px; }}

  @media (max-width:640px) {{
    .plot {{ gap:4px; }}
    .cap {{ font-size:9px; }}
    .cap .u {{ display:none; }}
    .cname {{ display:none; }}
    .xlab {{ min-height:34px; }}
    .xlab img {{ width:20px; height:20px; }}
    .wash span {{ font-size:9px; left:4px; }}
    .thead, .trow.flat, .trow summary {{ grid-template-columns:18px minmax(86px,1.2fr) 1fr 1fr 1fr;
      gap:6px; }}
    .subtbl {{ padding-left:14px; }}
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
  <p class="intro">Where the ranked playerbase sits, measured live from the badge
    distribution — the same numbers the site's Phantom+/Ascendant+/Eternus+ build tabs
    select on, re-measured on every refresh rather than estimated.</p>

  <div class="cuts">{cut_html}</div>

  {reset_note}
  {chart_html}
  {table_html}

  <div class="foot">
    {total_players:,} ranked players across {total_matches:,} matches ·
    ranked accounts only (unranked Obscurus players aren't counted) ·
    badge = tier × 10 + sub-rank (Phantom 1 = badge 91) ·
    source: <a href="https://api.deadlock-api.com">deadlock-api.com</a>
    /v1/analytics/badge-distribution ·
    snapshot of the current playerbase, not per patch · generated {generated}
  </div>
</div>
<div class="tip" id="tip" aria-hidden="true"></div>
<script>
(function () {{
  var tip = document.getElementById('tip');
  function show(text, x, y) {{
    tip.textContent = text;               // data-tip holds API-derived names — textContent only
    tip.style.display = 'block';
    var r = tip.getBoundingClientRect();
    var left = Math.min(Math.max(6, x + 12), window.innerWidth - r.width - 6);
    var top = y - r.height - 10;
    if (top < 6) top = y + 16;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }}
  function hide() {{ tip.style.display = 'none'; }}
  function follow(e) {{
    var el = e.target.closest && e.target.closest('[data-tip]');
    if (el) show(el.dataset.tip, e.clientX, e.clientY); else hide();
  }}
  document.addEventListener('pointerover', follow);
  document.addEventListener('pointermove', follow);
  document.addEventListener('pointerdown', function (e) {{
    if (!e.target.closest('[data-tip]')) hide();
  }});
  document.addEventListener('focusin', function (e) {{
    var el = e.target.closest('[data-tip]');
    if (el) {{
      var r = el.getBoundingClientRect();
      show(el.dataset.tip, r.left + r.width / 2, r.top);
    }} else hide();
  }});
  window.addEventListener('scroll', hide, true);
}})();
</script>
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
