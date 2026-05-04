"""Assemble the static HTML page by embedding page_data.json into the template."""
from pathlib import Path
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import (
    ROOT, CACHE, HERO_OUT, HERO_DATA, BUILD_FILES, ASSETS,
    PATCH_ID, PATCH_TITLE, PATCH_MIN_TS, HMMR_BADGE, SPEC_VERSION,
)


DATA_JSON = (CACHE / "page_data.json").read_text()

HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Deadlock Optimal Builds</title>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<style>
  :root {
    --bg: #0e1217;
    --bg-elev: #161b23;
    --bg-card: #1c2230;
    --border: #2a3140;
    --text: #e6e8ec;
    --text-dim: #8b94a3;
    --accent: #f0a93b;
    --accent-dim: #c2872f;
    --weapon: #d6856b;
    --vitality: #6cb46a;
    --spirit: #b487d9;
    --flex: #6a8db4;
    --good: #58c46c;
    --bad: #d36262;
    --neutral: #8b94a3;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; height: 100%; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", sans-serif;
    font-size: 14px;
    line-height: 1.5;
    overflow: hidden;
  }
  header {
    background: var(--bg-elev);
    border-bottom: 1px solid var(--border);
    padding: 12px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }
  header h1 {
    font-size: 16px;
    font-weight: 600;
    margin: 0;
    color: var(--accent);
    letter-spacing: 0.5px;
  }
  header .meta { color: var(--text-dim); font-size: 12px; }
  .toggle-group {
    display: inline-flex;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
  }
  .toggle-group button {
    background: transparent;
    border: none;
    color: var(--text-dim);
    padding: 6px 14px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
  }
  .toggle-group button.active {
    background: var(--accent);
    color: #0e1217;
  }
  .layout {
    display: grid;
    grid-template-columns: 280px 1fr;
    height: calc(100vh - 53px);
  }
  aside {
    background: var(--bg-elev);
    border-right: 1px solid var(--border);
    overflow-y: auto;
    padding: 12px;
  }
  aside .sort {
    display: flex;
    gap: 6px;
    margin-bottom: 12px;
    font-size: 12px;
  }
  aside .sort button {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text-dim);
    padding: 6px;
    border-radius: 4px;
    cursor: pointer;
  }
  aside .sort button.active {
    color: var(--text);
    border-color: var(--accent);
  }
  .hero-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
  .hero-tile {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px;
    cursor: pointer;
    text-align: center;
    transition: border-color 0.1s, transform 0.1s;
    overflow: hidden;
  }
  .hero-tile:hover {
    border-color: var(--accent);
  }
  .hero-tile.active {
    border-color: var(--accent);
    background: #221a13;
  }
  .hero-tile img {
    width: 100%;
    aspect-ratio: 1;
    object-fit: cover;
    border-radius: 4px;
    background: #000;
  }
  .hero-tile .name {
    font-size: 11px;
    margin-top: 4px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .hero-tile .wr {
    font-size: 10px;
    color: var(--text-dim);
  }
  .hero-tile .wr.good { color: var(--good); }
  .hero-tile .wr.bad { color: var(--bad); }
  main {
    overflow-y: auto;
    padding: 24px 32px;
    max-width: 1200px;
  }
  .empty-state {
    color: var(--text-dim);
    text-align: center;
    padding: 60px;
  }
  .hero-header {
    display: flex;
    gap: 20px;
    align-items: center;
    margin-bottom: 24px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
  }
  .hero-portrait {
    width: 84px;
    height: 84px;
    border-radius: 8px;
    background: #000;
    object-fit: cover;
  }
  .hero-title h2 {
    margin: 0 0 4px;
    font-size: 28px;
    letter-spacing: 0.5px;
  }
  .hero-title .stats {
    display: flex;
    gap: 18px;
    color: var(--text-dim);
    font-size: 13px;
  }
  .hero-title .stats .stat strong {
    color: var(--text);
    font-weight: 600;
    margin-right: 4px;
  }
  .hero-title .stats .wr-badge {
    padding: 1px 8px;
    border-radius: 4px;
    background: var(--bg-elev);
    font-weight: 600;
  }
  .wr-badge.good { color: var(--good); }
  .wr-badge.bad { color: var(--bad); }
  .wr-badge.neutral { color: var(--neutral); }
  section {
    margin: 28px 0;
  }
  section h3 {
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--accent);
    margin: 0 0 14px;
    font-weight: 600;
  }
  .ability-row {
    display: grid;
    grid-template-columns: 48px 1fr 90px 90px;
    gap: 12px;
    align-items: center;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 6px;
  }
  .ability-row .icon {
    width: 36px; height: 36px;
    background: var(--bg);
    border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
  }
  .ability-row .icon img { width: 32px; height: 32px; object-fit: contain; }
  .ability-row .icon .placeholder { font-size: 16px; color: var(--text-dim); font-weight: 700; }
  .ability-row .name { font-weight: 600; }
  .ability-row .role { font-size: 11px; color: var(--text-dim); }
  .ability-row .ap-stat {
    text-align: right; font-size: 12px; color: var(--text-dim);
  }
  .ability-row .ap-stat .v { font-size: 16px; color: var(--text); font-weight: 600; }
  .ability-row .ap-stat .premium.good { color: var(--good); }
  .ability-row .ap-stat .premium.bad { color: var(--bad); }
  .order-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 8px;
  }
  .order-card .label {
    color: var(--text-dim);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 8px;
  }
  .order-seq {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin: 8px 0;
  }
  .order-seq .step {
    padding: 4px 8px;
    background: var(--bg);
    border-radius: 4px;
    font-size: 12px;
    border: 1px solid var(--border);
    color: var(--text);
  }
  .order-seq .step .num {
    color: var(--text-dim);
    margin-right: 4px;
    font-size: 10px;
  }
  .order-stats {
    color: var(--text-dim);
    font-size: 12px;
    margin-top: 8px;
  }
  .phases {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 12px;
  }
  .phase-col {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px;
  }
  .phase-col h4 {
    margin: 0 0 12px;
    font-size: 13px;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 1.5px;
  }
  .phase-col .when { font-size: 11px; color: var(--text-dim); margin-left: 6px; font-weight: 400; text-transform: none; letter-spacing: 0; }
  .item-row {
    display: grid;
    grid-template-columns: 36px 1fr auto;
    gap: 8px;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
  }
  .item-row:last-child { border-bottom: none; }
  .item-row .icon {
    width: 36px; height: 36px;
    border-radius: 4px;
    background: var(--bg);
    border: 1px solid var(--border);
    display: flex; align-items: center; justify-content: center;
    overflow: hidden;
  }
  .item-row .icon img { width: 32px; height: 32px; object-fit: contain; }
  .item-row .icon .placeholder { font-size: 11px; color: var(--text-dim); }
  .item-row .name { font-size: 13px; font-weight: 500; }
  .item-row .meta { font-size: 11px; color: var(--text-dim); margin-top: 2px; }
  .item-row .cost { font-size: 12px; font-weight: 600; color: var(--accent); }
  .cat-pill {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-right: 4px;
  }
  .cat-weapon { background: rgba(214,133,107,0.15); color: var(--weapon); }
  .cat-vitality { background: rgba(108,180,106,0.15); color: var(--vitality); }
  .cat-spirit { background: rgba(180,135,217,0.15); color: var(--spirit); }
  .slot-flex { color: var(--flex); font-size: 10px; font-weight: 600; }

  /* Tag pills: core / flex / situational / stat */
  .tag-pill {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 9.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-left: 6px;
    border: 1px solid transparent;
    vertical-align: middle;
  }
  .tag-core        { background: rgba(88,196,108,0.16);  color: var(--good);    border-color: rgba(88,196,108,0.4); }
  .tag-flex        { background: rgba(240,169,59,0.14);  color: var(--accent);  border-color: rgba(240,169,59,0.35); }
  .tag-situational { background: rgba(139,148,163,0.12); color: var(--neutral); border-color: rgba(139,148,163,0.3); }
  .tag-stat        { background: rgba(106,141,180,0.14); color: var(--flex);    border-color: rgba(106,141,180,0.35); }

  /* Hover tooltip showing the annotation */
  .item-row { position: relative; }
  .item-row[data-annotation]:hover .annot-tooltip {
    display: block;
  }
  .annot-tooltip {
    display: none;
    position: absolute;
    left: 0;
    right: 0;
    top: calc(100% + 4px);
    background: var(--bg);
    border: 1px solid var(--accent);
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 12px;
    color: var(--text);
    box-shadow: 0 6px 24px rgba(0,0,0,0.5);
    z-index: 50;
    line-height: 1.5;
    pointer-events: none;
  }
  .annot-tooltip .annot-source {
    display: block;
    color: var(--text-dim);
    font-size: 10px;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  .pick-rate-bar {
    display: inline-block;
    width: 36px;
    height: 4px;
    background: var(--bg);
    border-radius: 2px;
    overflow: hidden;
    vertical-align: middle;
    margin-left: 6px;
  }
  .pick-rate-bar > i {
    display: block;
    height: 100%;
    background: var(--accent);
  }
  .summary-line {
    color: var(--text-dim);
    font-size: 12px;
    margin-bottom: 16px;
  }
  .alt-orders {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 8px;
  }
  details > summary {
    cursor: pointer;
    color: var(--text-dim);
    font-size: 12px;
    margin-top: 12px;
    user-select: none;
  }
  details[open] > summary { color: var(--text); }
  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

  /* Lineage chain: chain stages render as their own rows in the proper
     phase column. The fallback inline chip is shown only for ancestors
     without buy-time data (rare). */
  .lineage-chain {
    margin-top: 4px;
    font-size: 10.5px;
    color: var(--text-dim);
    line-height: 1.6;
  }
  .lineage-chain .lc-label {
    text-transform: uppercase;
    letter-spacing: 0.7px;
    color: var(--text-dim);
    margin-right: 6px;
    font-size: 9px;
  }
  .lineage-chain .lc-stage {
    display: inline-block;
    padding: 1px 6px;
    margin-right: 2px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 3px;
    color: var(--text);
    font-size: 10.5px;
  }
  .lineage-chain .lc-arrow { color: var(--accent); margin: 0 3px; opacity: 0.7; }
  .lineage-chain .lc-when { color: var(--text-dim); margin-left: 3px; font-size: 9.5px; }

  /* Cooldown + imbue badges on item meta line */
  .cd-badge, .imbue-badge {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 600;
    margin-right: 4px;
    border: 1px solid;
    vertical-align: middle;
  }
  .cd-badge {
    color: #79c4ff;
    border-color: rgba(121,196,255,0.4);
    background: rgba(121,196,255,0.08);
  }
  .imbue-badge {
    color: #c984ff;
    border-color: rgba(201,132,255,0.5);
    background: rgba(201,132,255,0.08);
    cursor: help;
  }

  /* Sell row: an early/mid item being sold to free a slot */
  .item-row.is-sell {
    background: linear-gradient(90deg, rgba(211,98,98,0.06) 0%, transparent 50%);
    border-left: 2px dashed rgba(211,98,98,0.55);
    padding: 5px 0 5px 6px;
    margin-left: -8px;
    opacity: 0.85;
  }
  .item-row.is-sell .icon { width: 26px; height: 26px; }
  .item-row.is-sell .name { font-size: 12px; color: var(--text-dim); }
  .item-row.is-sell .name .sell-tag {
    color: var(--bad);
    font-size: 10.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    margin-right: 6px;
    border: 1px solid rgba(211,98,98,0.5);
    border-radius: 3px;
    padding: 1px 5px;
    background: rgba(211,98,98,0.08);
  }
  .item-row.is-sell .meta { font-size: 11px; color: var(--text-dim); }
  .item-row.is-sell .cost { color: var(--good); font-size: 11px; font-weight: 600; }
  .item-row.is-sell .cost::before { content: '+ '; }

  /* Stage row: a chain ancestor placed in its actual buy-phase column */
  .item-row.is-stage {
    background: linear-gradient(90deg, rgba(240,169,59,0.04) 0%, transparent 50%);
    border-left: 2px dashed rgba(240,169,59,0.5);
    padding: 6px 0 6px 6px;
    margin-left: -8px;
    opacity: 0.92;
  }
  .item-row.is-stage .icon { width: 28px; height: 28px; }
  .item-row.is-stage .icon img { width: 24px; height: 24px; }
  .item-row.is-stage .name { font-weight: 500; font-size: 12px; }
  .item-row.is-stage .stage-arrow {
    color: var(--accent);
    margin: 0 4px;
    opacity: 0.75;
    font-size: 11px;
  }
  .item-row.is-stage .upgrades-to {
    font-style: italic;
    font-size: 10.5px;
    color: var(--text-dim);
    margin-top: 1px;
  }
  .item-row.is-stage .upgrades-to strong { color: var(--accent); font-style: normal; font-weight: 600; }

  /* Signature items: hero-specific picks (affinity ≥ 2x with non-trivial pick rate) */
  .signature-star {
    display: inline-block;
    margin-right: 5px;
    color: var(--accent);
    font-size: 12px;
    cursor: help;
    text-shadow: 0 0 6px rgba(240,169,59,0.5);
  }
  .item-row.is-signature {
    background: linear-gradient(90deg, rgba(240,169,59,0.05) 0%, transparent 60%);
    border-left: 2px solid var(--accent);
    padding-left: 6px;
    margin-left: -8px;
  }

  /* Archetype panel */
  .archetype-panel {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
  }
  .archetype-row {
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
  }
  .archetype-row:last-child { border-bottom: none; }
  .archetype-row .label-line {
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 600;
    margin-bottom: 6px;
  }
  .archetype-row .name { font-size: 14px; }
  .archetype-row.primary .name { color: var(--accent); }
  .archetype-row.active {
    background: rgba(240,169,59,0.06);
    border-radius: 6px;
    padding: 10px 12px;
    border: 1px solid rgba(240,169,59,0.4);
    margin: 4px -8px;
  }
  .archetype-row .view-btn {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    margin-left: auto;
    transition: all 0.1s;
  }
  .archetype-row .view-btn:hover { border-color: var(--accent); color: var(--accent); }
  .archetype-row.active .view-btn {
    background: var(--accent);
    color: var(--bg);
    border-color: var(--accent);
  }
  .archetype-row.active .view-btn::before { content: '✓ '; }
  .build-view-banner {
    background: rgba(240,169,59,0.08);
    border: 1px solid rgba(240,169,59,0.3);
    border-radius: 6px;
    padding: 8px 14px;
    margin-bottom: 12px;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .build-view-banner .label {
    color: var(--accent);
    font-weight: 600;
    text-transform: uppercase;
    font-size: 10.5px;
    letter-spacing: 1px;
  }
  .build-view-banner .reset {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-dim);
    padding: 2px 10px;
    border-radius: 4px;
    font-size: 11px;
    cursor: pointer;
    margin-left: auto;
  }
  .build-view-banner .reset:hover { color: var(--accent); border-color: var(--accent); }
  .archetype-row .share-pill {
    display: inline-block;
    padding: 1px 8px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    font-size: 11px;
    color: var(--text-dim);
    font-weight: 500;
  }
  .archetype-row.primary .share-pill {
    background: rgba(240,169,59,0.1);
    border-color: var(--accent);
    color: var(--accent);
  }
  .archetype-row .archetype-meta {
    color: var(--text-dim);
    font-size: 11px;
  }
  .archetype-row .sig-items {
    margin-top: 4px;
    color: var(--text-dim);
    font-size: 12px;
  }
  .archetype-row .sig-items .name-chip {
    display: inline-block;
    background: var(--bg);
    padding: 2px 7px;
    margin: 2px 4px 2px 0;
    border-radius: 4px;
    color: var(--text);
    font-size: 11px;
  }
  .archetype-row .cat-bar {
    display: inline-flex;
    height: 6px;
    width: 100px;
    border-radius: 3px;
    overflow: hidden;
    background: var(--bg);
    vertical-align: middle;
    margin: 0 6px;
  }
  .archetype-row .cat-bar > i {
    display: block;
    height: 100%;
  }
  .archetype-row .cat-bar > i.weapon   { background: var(--weapon); }
  .archetype-row .cat-bar > i.vitality { background: var(--vitality); }
  .archetype-row .cat-bar > i.spirit   { background: var(--spirit); }

  /* Hero search filter (sidebar) */
  .hero-search {
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 7px 10px;
    border-radius: 5px;
    font-size: 13px;
    margin-bottom: 8px;
    box-sizing: border-box;
  }
  .hero-search:focus {
    outline: none;
    border-color: var(--accent);
  }
  .hero-search::placeholder { color: var(--text-dim); }
  .empty-filter {
    text-align: center;
    color: var(--text-dim);
    font-size: 12px;
    padding: 18px 6px;
  }

  /* Top-level view toggle (Detail / Matrix) */
  .view-toggle {
    display: inline-flex;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
    margin-right: 8px;
  }
  .view-toggle button {
    background: transparent;
    border: none;
    color: var(--text-dim);
    padding: 6px 14px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
  }
  .view-toggle button.active {
    background: var(--accent);
    color: var(--bg);
  }

  /* Matchup matrix */
  .matrix-container {
    overflow: auto;
    max-height: calc(100vh - 60px);
    padding: 12px;
  }
  .matrix-intro {
    color: var(--text-dim);
    font-size: 13px;
    margin-bottom: 14px;
    max-width: 720px;
    line-height: 1.5;
  }
  .matrix-intro strong { color: var(--text); }
  .matrix {
    display: grid;
    border-collapse: collapse;
    width: max-content;
  }
  .matrix .corner {
    background: var(--bg-elev);
    position: sticky;
    top: 0;
    left: 0;
    z-index: 30;
    border-right: 2px solid var(--border);
    border-bottom: 2px solid var(--border);
    width: 100px;
    height: 64px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 1px;
    text-align: center;
  }
  .matrix .col-head, .matrix .row-head {
    background: var(--bg-elev);
    width: 28px;
    height: 28px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-size: 9px;
    cursor: pointer;
    user-select: none;
  }
  .matrix .col-head {
    position: sticky;
    top: 0;
    height: 64px;
    z-index: 20;
    border-bottom: 2px solid var(--border);
  }
  .matrix .col-head img {
    width: 24px; height: 24px;
    border-radius: 3px;
    object-fit: cover;
    background: #000;
  }
  .matrix .col-head .lbl {
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    margin-top: 4px;
    color: var(--text-dim);
    white-space: nowrap;
    overflow: hidden;
    max-height: 28px;
  }
  .matrix .row-head {
    position: sticky;
    left: 0;
    width: 100px;
    height: 28px;
    z-index: 20;
    border-right: 2px solid var(--border);
    flex-direction: row;
    justify-content: flex-start;
    padding-left: 4px;
    gap: 6px;
  }
  .matrix .row-head img {
    width: 22px; height: 22px;
    border-radius: 3px;
    object-fit: cover;
    background: #000;
    flex-shrink: 0;
  }
  .matrix .row-head .lbl {
    font-size: 10px;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .matrix .col-head:hover, .matrix .row-head:hover { background: var(--bg-card); }
  .matrix-cell {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 9px;
    font-weight: 600;
    color: var(--text);
    cursor: pointer;
    border: 1px solid var(--border);
  }
  .matrix-cell.empty { background: var(--bg); color: var(--text-dim); cursor: default; }
  .matrix-cell.diag  { background: var(--bg-elev); color: var(--text-dim); cursor: default; }
  .matrix-cell:hover { outline: 2px solid var(--accent); outline-offset: -1px; z-index: 10; }
  .matrix-legend {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-top: 14px;
    font-size: 11px;
    color: var(--text-dim);
  }
  .matrix-legend .swatch {
    display: inline-block;
    width: 16px; height: 14px;
    border-radius: 2px;
    border: 1px solid var(--border);
    vertical-align: middle;
  }

  /* Copy-build button + toast */
  .copy-build-row {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 8px;
  }
  .copy-build-btn {
    background: var(--bg-card);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.1s;
  }
  .copy-build-btn:hover { border-color: var(--accent); color: var(--accent); }
  .copy-build-btn.copied { background: var(--good); color: var(--bg); border-color: var(--good); }
  .toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--bg-card);
    border: 1px solid var(--accent);
    color: var(--text);
    padding: 10px 22px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    box-shadow: 0 6px 24px rgba(0,0,0,0.5);
    z-index: 100;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.2s, transform 0.2s;
  }
  .toast.show { opacity: 1; transform: translateX(-50%) translateY(-4px); }

  /* Matchup rankings (per-hero counter best/worst lists) */
  .matchup-rankings {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 14px;
  }
  .matchup-rankings .col {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 12px;
  }
  .matchup-rankings .col.easy { border-left: 3px solid var(--good); }
  .matchup-rankings .col.hard { border-left: 3px solid var(--bad); }
  .matchup-rankings h5 {
    margin: 0 0 6px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: var(--text-dim);
    font-weight: 600;
  }
  .matchup-rankings .col.easy h5 { color: var(--good); }
  .matchup-rankings .col.hard h5 { color: var(--bad); }
  .matchup-rankings .row {
    display: grid;
    grid-template-columns: 24px 1fr auto;
    gap: 8px;
    align-items: center;
    padding: 4px 0;
    cursor: pointer;
    border-radius: 3px;
    transition: background 0.08s;
  }
  .matchup-rankings .row:hover { background: var(--bg-card); }
  .matchup-rankings .row img {
    width: 24px; height: 24px;
    border-radius: 3px;
    object-fit: cover;
    background: #000;
  }
  .matchup-rankings .row .name { font-size: 12px; }
  .matchup-rankings .row .delta {
    font-size: 11px;
    font-weight: 700;
  }
  .matchup-rankings .col.easy .delta { color: var(--good); }
  .matchup-rankings .col.hard .delta { color: var(--bad); }

  /* Counter-pick (matchup) panel */
  .counter-panel {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
  }
  .counter-enemies {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(56px, 1fr));
    gap: 6px;
    margin-bottom: 12px;
  }
  .counter-enemy {
    background: var(--bg);
    border: 1.5px solid var(--border);
    border-radius: 6px;
    padding: 4px;
    text-align: center;
    cursor: pointer;
    overflow: hidden;
    transition: all 0.1s;
    user-select: none;
  }
  .counter-enemy:hover { border-color: var(--accent); }
  .counter-enemy.active {
    border-color: var(--bad);
    background: rgba(211,98,98,0.08);
  }
  .counter-enemy img {
    width: 100%;
    aspect-ratio: 1;
    object-fit: cover;
    border-radius: 3px;
  }
  .counter-enemy .lbl {
    font-size: 9.5px;
    margin-top: 2px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .counter-results {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    margin-top: 12px;
  }
  .counter-results h4 {
    margin: 0 0 8px;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  .counter-results .buy h4   { color: var(--good); }
  .counter-results .avoid h4 { color: var(--bad); }
  .counter-row {
    display: grid;
    grid-template-columns: 28px 1fr auto;
    gap: 8px;
    align-items: center;
    padding: 5px 0;
    border-bottom: 1px dashed var(--border);
  }
  .counter-row:last-child { border-bottom: none; }
  .counter-row .icon {
    width: 28px; height: 28px;
    border-radius: 4px;
    background: var(--bg);
    border: 1px solid var(--border);
    overflow: hidden;
    display: flex; align-items: center; justify-content: center;
  }
  .counter-row .icon img { width: 24px; height: 24px; object-fit: contain; }
  .counter-row .name { font-size: 12px; }
  .counter-row .meta { font-size: 10px; color: var(--text-dim); }
  .counter-row .delta { font-size: 12px; font-weight: 700; text-align: right; min-width: 64px; }
  .counter-row.pos .delta { color: var(--good); }
  .counter-row.neg .delta { color: var(--bad); }
  .counter-empty {
    color: var(--text-dim);
    text-align: center;
    padding: 18px;
    font-size: 12px;
  }
  .counter-summary {
    color: var(--text-dim);
    font-size: 11px;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px dashed var(--border);
  }

  /* Investment-spike progression panel */
  .spike-panel {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
    margin-bottom: 16px;
  }
  .spike-row {
    display: grid;
    grid-template-columns: 80px 1fr;
    gap: 12px;
    align-items: center;
    /* Top padding reserves room for the threshold tick labels above the
       bar (positioned at top:-16px); bottom padding reserves room for the
       phase checkpoint markers below (~28px including the cost line,
       phase tag, and gap). */
    padding: 22px 0 36px;
    border-bottom: 1px solid var(--border);
  }
  .spike-row:last-child { border-bottom: none; padding-bottom: 28px; }
  .spike-row .lbl {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 600;
  }
  .spike-row.weapon .lbl   { color: var(--weapon); }
  .spike-row.vitality .lbl { color: var(--vitality); }
  .spike-row.spirit .lbl   { color: var(--spirit); }
  .spike-bar {
    position: relative;
    height: 22px;
    background: var(--bg);
    border-radius: 4px;
    overflow: visible;
  }
  .spike-fill {
    position: absolute;
    top: 0; height: 100%;
    transition: width 0.2s, left 0.2s;
  }
  /* Three progressive segments per bar: early (lightest), mid (medium),
     late (full saturation). Visually shows the build coming online. */
  .spike-fill.seg-early { opacity: 0.30; border-radius: 4px 0 0 4px; }
  .spike-fill.seg-mid   { opacity: 0.55; }
  .spike-fill.seg-late  { opacity: 0.95; border-radius: 0 4px 4px 0; }
  /* When a segment is the leftmost-filled (e.g. no early-game spend → mid is leftmost),
     give it the left rounded corner. JS adds .seg-leftmost to the right element. */
  .spike-fill.seg-leftmost  { border-radius: 4px 0 0 4px; }
  .weapon .spike-fill   { background: var(--weapon); }
  .vitality .spike-fill { background: var(--vitality); }
  .spirit .spike-fill   { background: var(--spirit); }
  /* Phase boundary tick that drops below the bar with a $ label and phase tag. */
  .phase-checkpoint {
    position: absolute;
    top: 100%;
    margin-top: 2px;
    transform: translateX(-50%);
    text-align: center;
    pointer-events: none;
    font-size: 9px;
    line-height: 1.1;
    color: var(--text-dim);
    white-space: nowrap;
  }
  .phase-checkpoint .pc-cost { color: var(--text); font-weight: 600; font-size: 10px; }
  .phase-checkpoint .pc-tag {
    display: block;
    font-size: 8.5px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    margin-top: 1px;
  }
  .phase-checkpoint .pc-marker {
    display: block;
    width: 1px;
    height: 8px;
    background: var(--text-dim);
    margin: 0 auto 1px;
    opacity: 0.6;
  }
  .phase-checkpoint.major .pc-cost { color: var(--accent); }
  .phase-checkpoint.major .pc-marker { background: var(--accent); width: 2px; opacity: 1; }
  /* (Per-row vertical padding handled in the main .spike-row rule above —
     22px top reserves room for the 800/1.6k/… threshold labels positioned
     at top:-16px on each tick; 36px bottom reserves room for the phase
     checkpoint markers + cost + phase tag below the bar.) */
  .spike-mark {
    position: absolute;
    top: -2px;
    width: 1px;
    height: 26px;
    background: var(--text-dim);
    opacity: 0.4;
  }
  .spike-mark.major {
    background: var(--accent);
    width: 2px;
    opacity: 1;
  }
  .spike-mark .lbl-mark {
    position: absolute;
    top: -16px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 9px;
    color: var(--text-dim);
    white-space: nowrap;
  }
  .spike-mark.major .lbl-mark { color: var(--accent); font-weight: 700; }
  .spike-mark.crossed { opacity: 0.85; }
  .spike-phase-marker {
    position: absolute;
    top: 100%;
    margin-top: 2px;
    transform: translateX(-50%);
    font-size: 9px;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    white-space: nowrap;
    font-weight: 700;
    pointer-events: none;
  }
  .phase-spike-summary {
    font-size: 11px;
    color: var(--text-dim);
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px dashed var(--border);
  }
  .phase-spike-summary .ok    { color: var(--good); }
  .phase-spike-summary .pend  { color: var(--text-dim); }
  .phase-spike-summary .major { color: var(--accent); font-weight: 700; }

  /* ==========================================================
     Mobile responsive layout (≤900px)
     ----------------------------------------------------------
     The desktop layout assumes a wide viewport: a fixed 280px
     left rail, two scroll regions, three side-by-side phase
     columns, and a no-scroll body. Phones can't show that, so
     on narrow viewports we:
       - let the document scroll naturally (drop body overflow)
       - collapse the layout to one column with a slide-out
         hero drawer (toggled by a hamburger button)
       - stack 2/3-column grids vertically
       - tighten paddings + font sizes
       - convert hover-only annotation tooltips to tap-to-toggle
     A mobile-nav button is appended to the header so the user
     can re-open the hero list on mobile after picking one.
     ========================================================== */
  .mobile-nav-toggle {
    display: none;
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 18px;
    cursor: pointer;
    line-height: 1;
  }
  .mobile-backdrop {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.55);
    z-index: 90;
  }
  @media (max-width: 900px) {
    body {
      overflow: auto;
      -webkit-text-size-adjust: 100%;
    }
    header {
      padding: 10px 12px;
      flex-wrap: wrap;
      gap: 10px;
    }
    header h1 { font-size: 14px; }
    header > div:last-child {
      flex-wrap: wrap;
      gap: 8px !important;
      width: 100%;
    }
    .toggle-group button {
      padding: 5px 10px;
      font-size: 12px;
    }
    .mobile-nav-toggle { display: inline-flex; align-items: center; }
    .layout {
      display: block;
      height: auto;
      min-height: calc(100vh - 53px);
    }
    /* Sidebar becomes an off-canvas drawer that slides in from
       the left when the hamburger is tapped. We keep aside in
       the DOM (don't display:none) so search + sort still work
       once it's open. */
    aside {
      position: fixed;
      top: 0;
      left: 0;
      bottom: 0;
      width: 84vw;
      max-width: 320px;
      z-index: 100;
      transform: translateX(-100%);
      transition: transform 0.2s ease;
      box-shadow: 4px 0 16px rgba(0,0,0,0.5);
    }
    body.nav-open aside { transform: translateX(0); }
    body.nav-open .mobile-backdrop { display: block; }
    main {
      padding: 14px 12px 60px;
      max-width: 100%;
      overflow: visible;
    }
    /* Hero header — portrait shrinks, stats wrap */
    .hero-header {
      gap: 12px;
      margin-bottom: 16px;
      padding-bottom: 14px;
    }
    .hero-portrait { width: 56px; height: 56px; border-radius: 6px; }
    .hero-title h2 { font-size: 20px; }
    .hero-title .stats {
      flex-wrap: wrap;
      gap: 8px 14px;
      font-size: 12px;
    }
    /* Stack the 3 phase columns into a single vertical column.
       Each phase keeps its own card but takes full width. */
    .phases { grid-template-columns: 1fr; gap: 10px; }
    .phase-col { padding: 10px 12px; }
    .phase-col h4 { font-size: 12px; margin-bottom: 8px; }
    .item-row { padding: 6px 0; gap: 6px; grid-template-columns: 32px 1fr auto; }
    .item-row .icon { width: 32px; height: 32px; }
    .item-row .icon img { width: 28px; height: 28px; }
    .item-row .name { font-size: 12px; }
    .item-row .meta { font-size: 10px; }
    .item-row .cost { font-size: 11px; }
    /* Ability rows: drop the right-most stats column on narrow
       screens — show name + AP only, hide the per-mmr breakdown */
    .ability-row {
      grid-template-columns: 36px 1fr auto;
      padding: 8px 10px;
      gap: 8px;
    }
    .ability-row .icon { width: 28px; height: 28px; }
    .ability-row .icon img { width: 26px; height: 26px; }
    .ability-row .ap-stat:last-child { display: none; }
    /* Stack alternate-orders + matchup rankings vertically */
    .alt-orders { grid-template-columns: 1fr; }
    .matchup-rankings { grid-template-columns: 1fr; gap: 10px; }
    /* Investment-spike panel: keep it readable at narrow widths */
    .spike-panel { padding: 10px 12px; }
    .spike-row { padding: 22px 0 36px !important; }
    .spike-row .lbl { font-size: 10px; }
    .lbl-mark { font-size: 9px; }
    .pc-cost { font-size: 9px; }
    .pc-tag { font-size: 8px; }
    /* Counter-pick + hero matchup: stack two-column grids */
    .counter-results { grid-template-columns: 1fr; gap: 12px; }
    .counter-enemies { grid-template-columns: repeat(auto-fill, minmax(46px, 1fr)); gap: 4px; }
    .counter-enemy .lbl { font-size: 9px; }
    .counter-panel { padding: 10px 12px; }
    /* Annotation tooltip — on mobile, hover doesn't fire. Show
       the tooltip when the row is tapped (toggled via a class). */
    .item-row[data-annotation].show-tooltip .annot-tooltip { display: block; }
    /* Order seq + chip rows wrap more aggressively */
    .order-seq .step { font-size: 11px; padding: 3px 6px; }
    .lineage-chain { font-size: 10px; }
    /* Section titles — smaller margins to claw back vertical space */
    section { margin: 18px 0; }
    section h3 { font-size: 12px; margin: 0 0 10px; }
    /* Matchup matrix is a wide table — let its container scroll
       horizontally so the rest of the page doesn't get a global
       horizontal scrollbar. */
    .matrix-container { overflow-x: auto; -webkit-overflow-scrolling: touch; padding: 10px; }
    .matrix { font-size: 9px; }
    /* Hero grid in sidebar: 3 cols at 84vw works well */
    .hero-grid { grid-template-columns: 1fr 1fr 1fr; }
    .hero-tile .name { font-size: 10px; }
    /* Compact code-style cooldown / imbue badges so they don't
       blow out the meta line on narrow screens */
    .cd-badge, .imbue-badge { font-size: 10px; padding: 1px 5px; }
  }
  @media (max-width: 480px) {
    /* Phone-sized: drop max-width buttons, two-up the hero grid,
       trim the matrix font even further. */
    .hero-grid { grid-template-columns: 1fr 1fr; }
    .hero-title h2 { font-size: 18px; }
    .matrix { font-size: 8px; }
    /* Header: title + meta on one line, controls stack below */
    header h1 { font-size: 13px; }
  }
</style>
</head>
<body>
<header>
  <div style="display:flex;align-items:center;gap:10px;flex:1;min-width:0">
    <button id="mobile-nav-toggle" class="mobile-nav-toggle" aria-label="Open hero list">☰</button>
    <div>
      <h1>DEADLOCK OPTIMAL BUILDS</h1>
      <div class="meta" id="patch-info">loading…</div>
      <div class="meta" style="margin-top:2px"><a href="methodology.html" style="color:var(--text-dim);text-decoration:underline" target="_blank">📖 Methodology &amp; glossary</a></div>
    </div>
  </div>
  <div style="display:flex; gap:14px; align-items:center; flex-wrap:wrap;">
    <div class="toggle-group" id="view-toggle">
      <button data-view="detail" class="active">Detail</button>
      <button data-view="matrix">Matchup Matrix</button>
    </div>
    <div class="toggle-group" id="patch-toggle"></div>
    <div class="toggle-group" id="mmr-toggle">
      <button data-mmr="all" title="No MMR filter — full population">All MMR</button>
      <button data-mmr="high" class="active" title="min_average_badge=91 — top ~15-20%">Phantom+</button>
      <button data-mmr="asc" title="min_average_badge=101 — top ~3-5%">Ascendant+</button>
      <button data-mmr="eter" title="min_average_badge=111 — top ~0.1-1%">Eternus+</button>
    </div>
  </div>
</header>
<div class="mobile-backdrop" id="mobile-backdrop"></div>
<div class="layout">
  <aside>
    <input id="hero-search" class="hero-search" type="search" placeholder="Search heroes…" autocomplete="off">
    <div class="sort" id="sort-buttons">
      <button data-sort="alpha" class="active">A–Z</button>
      <button data-sort="tier">By WR</button>
    </div>
    <div class="hero-grid" id="hero-grid"></div>
  </aside>
  <main id="main">
    <div class="empty-state">
      <p>Select a hero from the left to see the optimal build and ability order.</p>
    </div>
  </main>
</div>
<script id="page-data" type="application/json">__DATA__</script>
<script>
  const DATA = JSON.parse(document.getElementById('page-data').textContent);

  let activePatchId = DATA.default_patch;
  let activePatch = DATA.patches[activePatchId];
  let selectedHeroId = null;
  let mmrSlice = 'high';
  let sortMode = 'alpha';
  let viewMode = 'detail';   // 'detail' | 'matrix'
  let heroFilter = '';       // hero search filter (lowercased)
  // Per-hero active archetype index — null/undefined means "use recommended"
  // Reset on patch change since hero objects differ between patches.
  let activeArchetypeIdxByHero = {};
  // Per-(patch, hero) selected enemy hero IDs for the counter-pick panel
  // Stored as Set<enemy_id>. Up to 6 enemies (one full team minus self).
  const counterEnemiesByHero = {};
  function counterKey(heroId) { return activePatchId + ':' + heroId; }

  // Build the patch-toggle buttons. Sort by recency (newer patch_id first).
  const patchIds = Object.keys(DATA.patches).sort().reverse();
  const patchToggle = document.getElementById('patch-toggle');
  patchToggle.innerHTML = patchIds.map(pid => {
    const p = DATA.patches[pid];
    const cls = pid === activePatchId ? 'active' : '';
    const isNew = pid === patchIds[0] ? ' <span style="color:var(--good);font-size:9px;margin-left:3px">NEW</span>' : '';
    return `<button data-patch="${pid}" class="${cls}" title="${p.title}">${p.title}${isNew}</button>`;
  }).join('');

  // Slice short-codes ↔ display labels. Kept in one place so renderers
  // and the empty-state messaging stay consistent.
  const SLICE_LABELS = { all: 'All MMR', high: 'Phantom+', asc: 'Ascendant+', eter: 'Eternus+' };

  // True if at least one hero on the active patch has data for this slice.
  // Higher-rank slices are sometimes empty on a freshly-released patch.
  function patchHasSliceData(slice) {
    return activePatch.heroes.some(h => (h.mmr[slice] || {}).matches > 0);
  }

  // Auto-fall-back to the next-best slice if the active one has zero data on
  // this patch. Walks left in the toggle order so e.g. an empty Eternus+ on
  // a brand-new patch silently becomes Ascendant+, then Phantom+, etc.
  function effectiveSlice() {
    const order = ['eter', 'asc', 'high', 'all'];
    if (patchHasSliceData(mmrSlice)) return mmrSlice;
    const idx = order.indexOf(mmrSlice);
    for (let i = idx + 1; i < order.length; i++) {
      if (patchHasSliceData(order[i])) return order[i];
    }
    return 'all';  // worst case, all-MMR is always populated
  }

  // Disable MMR toggle buttons whose slice has no data on the active patch.
  function refreshMmrToggleAvailability() {
    document.querySelectorAll('#mmr-toggle button').forEach(b => {
      const has = patchHasSliceData(b.dataset.mmr);
      b.disabled = !has;
      b.title = has ? b.title.split(' — no data')[0]
                    : b.title.split(' — no data')[0] + ' — no data on this patch';
      b.style.opacity = has ? '' : '0.4';
      b.style.cursor = has ? '' : 'not-allowed';
    });
  }

  function updatePatchInfo() {
    // Compute the total match count across all heroes in this patch as a
    // freshness signal — newly-released patches have very thin data.
    const totalMatches = activePatch.heroes.reduce((s, h) => s + (h.mmr.all.matches || 0), 0);
    let freshness = '';
    if (totalMatches < 100000) {
      freshness = ` · <span style="color:var(--bad);font-weight:600">⚠ thin data (${(totalMatches/1000).toFixed(0)}K matches across all heroes — builds will look noisy)</span>`;
    } else if (totalMatches < 1000000) {
      freshness = ` · <span style="color:var(--accent)">young patch (${(totalMatches/1000).toFixed(0)}K matches)</span>`;
    }
    document.getElementById('patch-info').innerHTML =
      activePatchId + ' — ' + activePatch.title + '  ·  ' + activePatch.heroes.length + ' heroes' + freshness;
    refreshMmrToggleAvailability();
  }
  updatePatchInfo();

  const fmtPct = v => v == null ? '—' : (v*100).toFixed(2) + '%';
  const wrClass = v => v >= 0.50 ? 'good' : v >= 0.475 ? 'neutral' : 'bad';
  const fmtCost = v => '$' + v.toLocaleString();
  const titleCase = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
  const phaseWhen = { early: 'laning · ≤12.5 min', mid: 'mid game · 12.5–25 min', late: 'late game · 25+ min' };

  // Investment-spike thresholds (universal across heroes; verified from
  // the asset's cost_bonuses data). The 4,800 milestone is the major
  // spike — at that point the per-category bonus more than doubles.
  const SPIKE_THRESHOLDS = [800, 1600, 2400, 3200, 4800, 7200, 9600, 16000];
  const SPIKE_MAJOR = 4800;
  const SPIKE_DISPLAY_MAX = 16000;
  // Bonus values at each threshold, per category, per patch.
  // Source for patch_125825: asset cost_bonuses (still served by the CDN).
  // Source for patch_129989: 04-30-2026 patch notes (asset CDN had not
  //   refreshed at the time of writing — vitality/weapon bonuses changed,
  //   spirit was not mentioned so kept identical).
  const SPIKE_BONUS_BY_PATCH = {
    patch_125825: {
      weapon:   { 800: 7,  1600: 9,  2400: 13, 3200: 20, 4800: 49, 7200: 60, 9600: 80,  16000: 95 },
      vitality: { 800: 8,  1600: 10, 2400: 13, 3200: 17, 4800: 34, 7200: 39, 9600: 44,  16000: 48 },
      spirit:   { 800: 7,  1600: 11, 2400: 15, 3200: 19, 4800: 38, 7200: 48, 9600: 57,  16000: 66 },
    },
    patch_129989: {
      // Weapon: 7/9/13/20/49/60/80/95/115/135 → 9/12/15/18/46/55/70/85/100/115
      weapon:   { 800: 9,  1600: 12, 2400: 15, 3200: 18, 4800: 46, 7200: 55, 9600: 70,  16000: 85 },
      // Vitality: 8/10/13/17/34/39/44/48/52/56 → 9/12/15/20/38/42/46/50/56/62
      vitality: { 800: 9,  1600: 12, 2400: 15, 3200: 20, 4800: 38, 7200: 42, 9600: 46,  16000: 50 },
      spirit:   { 800: 7,  1600: 11, 2400: 15, 3200: 19, 4800: 38, 7200: 48, 9600: 57,  16000: 66 },
    },
  };
  // Default to the newest known patch's values for any future patch we
  // haven't hardcoded yet.
  const SPIKE_BONUS_FALLBACK = SPIKE_BONUS_BY_PATCH.patch_129989;
  function getSpikeBonus() {
    return SPIKE_BONUS_BY_PATCH[activePatchId] || SPIKE_BONUS_FALLBACK;
  }
  const SPIKE_UNIT = { weapon: '% wpn dmg', vitality: '% base HP', spirit: ' spirit' };

  // Build a list of "cost events" — each one represents gold actually spent
  // at a known time. A pick with a lineage chain decomposes into incremental
  // events: T1 stage adds its full cost, T2 adds the differential, the
  // final tier adds (final cost - last stage cost). Picks with no chain
  // just add their full cost at the final buy time. For multi-parent
  // lineages (e.g. Leech with both Spirit Lifesteal AND Bullet Lifesteal as
  // T2 components), we keep only one stage per tier — picking the earliest
  // by buy time — because a real player only pre-buys one component path.
  function buildCostEvents(build) {
    const events = [];
    const phaseFromMin = m => m < 12.5 ? 'early' : m < 25 ? 'mid' : 'late';
    for (const pick of build) {
      const rawChain = (pick.lineage_chain || []).filter(s => s.avg_buy_time_min != null);
      // Sort by tier asc, then buy_min asc, then dedupe by tier (keep earliest)
      rawChain.sort((a, b) => (a.tier - b.tier) || (a.avg_buy_time_min - b.avg_buy_time_min));
      const seenTiers = new Set();
      const stages = [];
      for (const s of rawChain) {
        if (seenTiers.has(s.tier)) continue;
        seenTiers.add(s.tier);
        stages.push(s);
      }
      let prevCost = 0;
      for (const s of stages) {
        const incr = (s.cost || 0) - prevCost;
        if (incr > 0) {
          events.push({
            buy_min: s.avg_buy_time_min,
            phase: phaseFromMin(s.avg_buy_time_min),
            category: pick.category,
            cost: incr,
          });
        }
        prevCost = Math.max(prevCost, s.cost || 0);
      }
      const finalIncr = (pick.cost || 0) - prevCost;
      if (finalIncr > 0) {
        events.push({
          buy_min: pick.buy_min,
          phase: pick.phase,
          category: pick.category,
          cost: finalIncr,
        });
      }
    }
    return events;
  }

  // Walk the cost events sorted by time, accumulate per-category totals, and
  // snapshot at phase boundaries (BEFORE the boundary-crossing event so the
  // 'end of N' figure reflects only events with phase <= N).
  function computeSpikeProgress(itemsBySlice) {
    const events = buildCostEvents(itemsBySlice);
    events.sort((a, b) => a.buy_min - b.buy_min);
    const totals = { weapon: 0, vitality: 0, spirit: 0 };
    const byPhaseEnd = { early: null, mid: null, late: null };
    const phasesOrder = ['early','mid','late'];
    let lastPhase = 'early';
    for (const e of events) {
      while (e.phase !== lastPhase) {
        byPhaseEnd[lastPhase] = { ...totals };
        const i = phasesOrder.indexOf(lastPhase);
        lastPhase = phasesOrder[i + 1] || lastPhase;
      }
      if (e.category in totals) totals[e.category] += (e.cost || 0);
    }
    while (true) {
      byPhaseEnd[lastPhase] = { ...totals };
      if (lastPhase === 'late') break;
      lastPhase = phasesOrder[phasesOrder.indexOf(lastPhase) + 1];
    }
    return { byPhaseEnd, finalTotals: totals };
  }

  function spikesCrossed(amount) {
    return SPIKE_THRESHOLDS.filter(t => amount >= t);
  }

  function renderHeroGrid() {
    const grid = document.getElementById('hero-grid');
    let order = [...activePatch.heroes];
    if (heroFilter) {
      order = order.filter(h => h.name.toLowerCase().includes(heroFilter));
    }
    // For sort + grid rendering, fall back to a populated slice if the
    // active one has no data anywhere on this patch — keeps the grid useful
    // when someone clicks an empty Eternus+ tab on a fresh patch.
    const gridSlice = effectiveSlice();
    if (sortMode === 'alpha') {
      order.sort((a,b) => a.name.localeCompare(b.name));
    } else {
      // Heroes with null WR (no data in this slice) sort to the bottom.
      order.sort((a,b) => {
        const aw = a.mmr[gridSlice].wr, bw = b.mmr[gridSlice].wr;
        if (aw == null && bw == null) return 0;
        if (aw == null) return 1;
        if (bw == null) return -1;
        return bw - aw;
      });
    }
    grid.innerHTML = '';
    if (order.length === 0) {
      const div = document.createElement('div');
      div.className = 'empty-filter';
      div.textContent = `No heroes matching "${heroFilter}"`;
      grid.appendChild(div);
      return;
    }
    for (const h of order) {
      const div = document.createElement('div');
      div.className = 'hero-tile' + (h.id === selectedHeroId ? ' active' : '');
      const sliceData = h.mmr[gridSlice] || {};
      const wr = sliceData.wr;
      const cls = wr == null ? '' : wrClass(wr);
      const hasData = sliceData.matches > 0;
      div.innerHTML = `
        <img src="${h.image || ''}" loading="lazy" onerror="this.style.opacity=0.2" ${hasData ? '' : 'style="opacity:0.4"'}>
        <div class="name">${h.name}</div>
        <div class="wr ${cls}">${hasData ? fmtPct(wr) : '—'}</div>
      `;
      div.addEventListener('click', () => selectHero(h.id));
      grid.appendChild(div);
    }
  }

  function selectHero(id) {
    selectedHeroId = id;
    // Don't reset other heroes' archetype selections — keep state per hero
    renderHeroGrid();
    renderMain();
    // Close the mobile drawer if it's open — picking a hero is the
    // intent so the hero list shouldn't stay over the content.
    document.body.classList.remove('nav-open');
    // Scroll to top so the hero header is visible after picking
    window.scrollTo({ top: 0, behavior: 'auto' });
  }

  // Plain-text export for the active build (current hero, MMR, archetype).
  function buildExportText(hero) {
    const items = (activeArchetypeIdxByHero[hero.id] != null)
      ? (() => {
          const meaningful = (hero.archetypes && hero.archetypes.clusters || []).filter(c => c.build_count >= 2 && c.build);
          return meaningful[activeArchetypeIdxByHero[hero.id]].build;
        })()
      : hero.items_by_slice[mmrSlice];
    const total = items.reduce((s, i) => s + (i.cost || 0), 0);
    const archActive = activeArchetypeIdxByHero[hero.id] != null;
    const variant = archActive
      ? `${(hero.archetypes.clusters.filter(c => c.build_count >= 2 && c.build)[activeArchetypeIdxByHero[hero.id]] || {}).label} archetype build`
      : 'Recommended build · synergy ILP';
    const phaseFromBuyMin = (m) => m < 12.5 ? 'EARLY' : m < 25 ? 'MID' : 'LATE';
    const phaseLabels = { EARLY: 'EARLY (laning · ≤12.5 min)', MID: 'MID (mid game · 12.5–25 min)', LATE: 'LATE (late game · 25+ min)' };

    const byPhase = { EARLY: [], MID: [], LATE: [] };
    for (const it of items) byPhase[phaseFromBuyMin(it.buy_min)].push(it);
    for (const ph in byPhase) byPhase[ph].sort((a,b) => a.buy_min - b.buy_min);

    const lines = [];
    lines.push(`${hero.name.toUpperCase()} — ${activePatchId} (${activePatch.title})`);
    lines.push(`${variant} · ${SLICE_LABELS[mmrSlice] || mmrSlice} · $${total.toLocaleString()}`);
    const sliceMmr = hero.mmr[mmrSlice] || {};
    if (sliceMmr.wr != null) {
      const wr = sliceMmr.wr * 100;
      lines.push(`Hero baseline WR: ${wr.toFixed(2)}% over ${sliceMmr.matches.toLocaleString()} matches`);
    } else {
      lines.push(`Hero baseline WR: insufficient data at ${SLICE_LABELS[mmrSlice]}`);
    }
    lines.push('');
    for (const ph of ['EARLY','MID','LATE']) {
      lines.push(phaseLabels[ph]);
      if (byPhase[ph].length === 0) {
        lines.push('  —');
      } else {
        for (const it of byPhase[ph]) {
          const cd = (it.is_active && it.cooldown_s) ? ` · CD ${Math.round(it.cooldown_s)}s` : '';
          const imb = it.imbue ? ' · imbuable' : '';
          const sig = it.signature ? ' ★' : '';
          lines.push(`  T${it.tier} ${it.name}${sig} (${it.category}, $${(it.cost||0).toLocaleString()}, ~${it.buy_min}min${cd}${imb})`);
        }
      }
      lines.push('');
    }

    // Ability priority + best opener (from recommended view, applies regardless of build)
    const ab = hero.recommended.abilities;
    if (ab.ap_priority_order && ab.ap_priority_order.length) {
      lines.push(`Ability priority: ${ab.ap_priority_order.join(' > ')}`);
    }
    if (ab.best_opener_first4 && ab.best_opener_first4.sequence_names) {
      const op = ab.best_opener_first4;
      lines.push(`Best opener (first 4): ${op.sequence_names.join(' → ')} (${(op.win_rate*100).toFixed(2)}% over ${op.matches.toLocaleString()} matches)`);
    }
    if (ab.best_full_order && ab.best_full_order.sequence_names) {
      const f = ab.best_full_order;
      lines.push(`Best full sequence: ${f.sequence_names.join(' → ')} (${(f.win_rate*100).toFixed(2)}% over ${f.matches.toLocaleString()} matches)`);
    }
    lines.push('');
    lines.push(`Source: ${DATA.data_source} · spec ${DATA.spec_version}`);
    return lines.join(String.fromCharCode(10));
  }

  function showToast(msg) {
    let t = document.getElementById('toast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'toast';
      t.className = 'toast';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(window.__toastTimeout);
    window.__toastTimeout = setTimeout(() => t.classList.remove('show'), 1800);
  }

  // Event delegation for archetype "View this build" buttons + reset banner.
  document.addEventListener('click', e => {
    const archBtn = e.target.closest('[data-arch-idx]');
    if (archBtn) {
      const heroId = parseInt(archBtn.dataset.archHero, 10);
      const idx = parseInt(archBtn.dataset.archIdx, 10);
      // Toggle: clicking the active one resets to recommended
      if (activeArchetypeIdxByHero[heroId] === idx) {
        delete activeArchetypeIdxByHero[heroId];
      } else {
        activeArchetypeIdxByHero[heroId] = idx;
      }
      renderMain();
      return;
    }
    const resetBtn = e.target.closest('[data-reset-hero]');
    if (resetBtn) {
      const heroId = parseInt(resetBtn.dataset.resetHero, 10);
      delete activeArchetypeIdxByHero[heroId];
      renderMain();
      return;
    }
    const copyBtn = e.target.closest('[data-copy-hero]');
    if (copyBtn) {
      const heroId = parseInt(copyBtn.dataset.copyHero, 10);
      const hero = activePatch.heroes.find(x => x.id === heroId);
      if (hero) {
        const text = buildExportText(hero);
        const fallback = () => {
          const ta = document.createElement('textarea');
          ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
          document.body.appendChild(ta); ta.select();
          try { document.execCommand('copy'); } finally { document.body.removeChild(ta); }
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).catch(fallback);
        } else {
          fallback();
        }
        copyBtn.classList.add('copied');
        copyBtn.textContent = '✓ Copied';
        showToast('Build copied to clipboard');
        setTimeout(() => {
          copyBtn.classList.remove('copied');
          copyBtn.textContent = '📋 Copy build to clipboard';
        }, 1500);
      }
      return;
    }
    // Matrix cell / header click — jump to detail view with hero + enemy pre-selected
    const jumpCell = e.target.closest('[data-jump-hero], [data-jump-enemy]');
    if (jumpCell && viewMode === 'matrix') {
      const heroId = jumpCell.dataset.jumpHero ? parseInt(jumpCell.dataset.jumpHero, 10) : null;
      const enemyId = jumpCell.dataset.jumpEnemy ? parseInt(jumpCell.dataset.jumpEnemy, 10) : null;
      if (heroId != null) {
        selectedHeroId = heroId;
        if (enemyId != null) {
          const k = counterKey(heroId);
          const set = counterEnemiesByHero[k] || new Set();
          set.add(enemyId);
          counterEnemiesByHero[k] = set;
        }
      } else if (enemyId != null && selectedHeroId != null) {
        // Clicked a column header without a row — add to current hero's enemies
        const k = counterKey(selectedHeroId);
        const set = counterEnemiesByHero[k] || new Set();
        set.add(enemyId);
        counterEnemiesByHero[k] = set;
      }
      viewMode = 'detail';
      document.querySelectorAll('#view-toggle button').forEach(b => b.classList.toggle('active', b.dataset.view === 'detail'));
      renderHeroGrid();
      renderMain();
      return;
    }

    const enemyTile = e.target.closest('[data-enemy-id]');
    if (enemyTile) {
      const heroId = parseInt(enemyTile.dataset.heroId, 10);
      const enemyId = parseInt(enemyTile.dataset.enemyId, 10);
      const key = counterKey(heroId);
      const set = counterEnemiesByHero[key] || new Set();
      if (set.has(enemyId)) {
        set.delete(enemyId);
      } else if (set.size < 6) {
        set.add(enemyId);
      }
      counterEnemiesByHero[key] = set;
      renderMain();
      return;
    }
  });

  function renderMatrix() {
    const main = document.getElementById('main');
    const counters = activePatch.counters || {};
    const heroes = [...activePatch.heroes].sort((a,b) => a.name.localeCompare(b.name));
    const itemsDict = activePatch.items_dict || {};
    if (Object.keys(counters).length === 0) {
      main.innerHTML = `<div class="empty-state"><p>No matchup data on this patch yet.</p>
        <p style="font-size:13px;margin-top:8px">The matchup matrix needs the counter-pick data fetched per (hero, enemy) pair. The new patch (${escHtml(activePatch.title)}) is too thin for that yet — switch to the older patch in the header to see the matrix.</p></div>`;
      return;
    }

    // Per-(hero,enemy) aggregate signal: sum of all delta_pp values
    const signal = {};
    let maxAbs = 1;
    for (const h of heroes) {
      const hList = counters[h.id] || counters[String(h.id)] || {};
      signal[h.id] = {};
      for (const e of heroes) {
        if (e.id === h.id) continue;
        const list = hList[e.id] || hList[String(e.id)];
        if (!list) continue;
        const s = list.reduce((acc, c) => acc + (c.delta_pp || 0), 0);
        signal[h.id][e.id] = s;
        if (Math.abs(s) > maxAbs) maxAbs = Math.abs(s);
      }
    }

    // Color: HSL — green hue 130 for positive, red hue 0 for negative.
    // Saturation scales with |signal|/maxAbs, lightness clamped to keep readable.
    const cellColor = (s) => {
      if (s == null) return '';
      const hue = s > 0 ? 130 : 0;
      const sat = Math.min(80, Math.abs(s) / maxAbs * 100);
      const light = 18 + (1 - Math.min(1, Math.abs(s) / maxAbs)) * 6;
      return `background:hsl(${hue},${sat}%,${light}%)`;
    };

    // Build the grid as one flat sequence of items: corner, col-headers, then row-by-row
    const cellsHtml = [];
    cellsHtml.push(`<div class="corner">vs →<br>↓ you</div>`);
    for (const e of heroes) {
      cellsHtml.push(`<div class="col-head" data-jump-enemy="${e.id}" title="${escAttr(e.name)}">
        <img src="${e.image || ''}" loading="lazy">
      </div>`);
    }
    for (const h of heroes) {
      cellsHtml.push(`<div class="row-head" data-jump-hero="${h.id}" title="${escAttr(h.name)}">
        <img src="${h.image || ''}" loading="lazy">
        <span class="lbl">${escHtml(h.name)}</span>
      </div>`);
      for (const e of heroes) {
        if (e.id === h.id) {
          cellsHtml.push(`<div class="matrix-cell diag">—</div>`);
          continue;
        }
        const s = signal[h.id]?.[e.id];
        if (s == null) {
          cellsHtml.push(`<div class="matrix-cell empty" title="No data">·</div>`);
        } else {
          cellsHtml.push(`<div class="matrix-cell" style="${cellColor(s)}"
            data-jump-hero="${h.id}" data-jump-enemy="${e.id}"
            title="${escAttr(h.name)} vs ${escAttr(e.name)}: ${s > 0 ? '+' : ''}${s.toFixed(1)}pp">${s > 0 ? '+' : ''}${s.toFixed(0)}</div>`);
        }
      }
    }
    const colCount = heroes.length + 1;

    main.innerHTML = `
      <div class="matrix-container">
        <h3 style="margin-top:0">Hero Matchup Matrix — ${escHtml(activePatch.title)}</h3>
        <div class="matrix-intro">
          Each cell is the <strong>aggregate matchup signal</strong> for (your hero) vs (enemy hero):
          sum of per-item win-rate deltas across the cached counter data.
          <span style="color:var(--good)">Green</span> = your hero generally wins this matchup;
          <span style="color:var(--bad)">red</span> = you struggle vs them.
          Click any cell to switch to detail view with that hero selected and the enemy pre-added to the counter panel.
          Click a row label or column header to jump to that hero's detail view.
        </div>
        <div class="matrix" style="grid-template-columns: 100px repeat(${heroes.length}, 28px)">
          ${cellsHtml.join('')}
        </div>
        <div class="matrix-legend">
          <span><span class="swatch" style="background:hsl(130,80%,20%)"></span> strong advantage</span>
          <span><span class="swatch" style="background:hsl(130,40%,22%)"></span> mild advantage</span>
          <span><span class="swatch" style="background:#1c2230"></span> neutral / no data</span>
          <span><span class="swatch" style="background:hsl(0,40%,22%)"></span> mild disadvantage</span>
          <span><span class="swatch" style="background:hsl(0,80%,20%)"></span> strong disadvantage</span>
        </div>
      </div>
    `;
  }

  function renderMain() {
    if (viewMode === 'matrix') { renderMatrix(); return; }
    const main = document.getElementById('main');
    if (selectedHeroId == null) { main.innerHTML = `<div class="empty-state"><p>Select a hero from the left.</p></div>`; return; }
    const h = activePatch.heroes.find(x => x.id === selectedHeroId);
    if (!h) {
      main.innerHTML = `<div class="empty-state"><p>This hero has no data on <strong>${escHtml(activePatch.title)}</strong>.</p>
        <p style="font-size:13px;margin-top:8px">Switch to a different patch in the header, or pick another hero.</p></div>`;
      return;
    }

    // Determine active build: either the recommended (default) or the
    // user-selected archetype's composite build for this hero.
    const activeArchIdx = activeArchetypeIdxByHero[h.id];
    const meaningfulArchs = (h.archetypes && h.archetypes.clusters || []).filter(c => c.build_count >= 2 && c.build);
    const activeArch = (activeArchIdx != null) ? meaningfulArchs[activeArchIdx] : null;
    // Get build for current MMR slice (or the active archetype's composite).
    // If the slice is empty for THIS hero (e.g. Eternus+ on a niche hero),
    // show an explicit empty-state instead of a blank build column.
    const sliceItems = h.items_by_slice[mmrSlice] || [];
    const sliceMeta = h.mmr[mmrSlice] || {};
    const sliceEmpty = !activeArch && sliceItems.length === 0;
    if (sliceEmpty) {
      // Pick a fallback slice with data so we can still show the hero header
      const fallback = effectiveSlice();
      main.innerHTML = `
        <div class="hero-header">
          <img src="${h.image || ''}" class="hero-portrait" onerror="this.style.opacity=0.2">
          <div class="hero-title">
            <h2>${h.name}</h2>
            <div class="stats">
              <div class="stat" style="color:var(--text-dim)">Insufficient ${SLICE_LABELS[mmrSlice]} data on ${escHtml(activePatch.title)}${sliceMeta.matches ? ` (${sliceMeta.matches.toLocaleString()} matches, below threshold)` : ''}.</div>
            </div>
          </div>
        </div>
        <div class="empty-state" style="margin-top:18px">
          <p><strong>No build available at ${SLICE_LABELS[mmrSlice]}</strong> for ${h.name} on ${escHtml(activePatch.title)}.</p>
          <p style="font-size:13px;margin-top:8px;color:var(--text-dim)">Higher-rank slices need a few thousand matches per hero before the optimizer has anything to chew on. Try ${SLICE_LABELS[fallback]} for now — the data tap-tap-taps in over the patch's lifetime.</p>
        </div>`;
      return;
    }
    const items = activeArch ? activeArch.build : sliceItems;

    // Build "events" — each phase column contains the buy events that happen
    // in its time window. A picked item with an upgrade chain is decomposed
    // into stage events (each ancestor in its actual buy-phase) plus the
    // final-tier event in the late game. This way an early-game T1 component
    // that upgrades to a T3 in late game shows up under EARLY.
    // We also emit "sell" events for items that the population typically
    // sells mid-game to free a slot — anything bought early/mid with a clear
    // sell time and a meaningful hold duration. End-of-game sells (very late
    // sell time, very short hold) are ignored since those are just match-end.
    const phaseFromBuyMin = (m) => m < 12.5 ? 'early' : m < 25 ? 'mid' : 'late';
    const events = [];
    for (const it of items) {
      const chain = it.lineage_chain || [];
      for (const c of chain) {
        if (c.avg_buy_time_min == null) continue;  // fall back to inline chip for these
        events.push({
          kind: 'stage',
          name: c.name, tier: c.tier, cost: c.cost, item_id: c.item_id,
          buy_min: c.avg_buy_time_min,
          phase: phaseFromBuyMin(c.avg_buy_time_min),
          category: it.category,
          upgrades_to_name: it.name,
          upgrades_to_tier: it.tier,
          // Imbue metadata — passive imbue components (Compress Cooldown,
          // Mystic Expansion, Duration Extender) are themselves imbuable
          // even though their non-imbuable T3/T4 descendants are what the
          // optimizer picks. Carry the imbue type + community-build target
          // through so renderStageRow can show the 🔮 badge.
          imbue: c.imbue,
          imbue_target_id: c.imbue_target_id,
          imbue_target_share: c.imbue_target_share,
          imbue_target_inferred: c.imbue_target_inferred,
        });
      }
      events.push({ ...it, kind: 'final' });

      // Sell event for this final pick? Conditions:
      //   - has a sell time
      //   - hold duration >= 6 min (real strategic sell, not match-end noise)
      //   - bought before late phase (late items don't get sold to free slots)
      //   - sell happens after the buy (sanity)
      if (it.sell_min != null && it.buy_min != null
          && it.sell_min > it.buy_min + 6
          && it.phase !== 'late'
          && it.sell_min < 38) {
        // Refund: sell yields ~50% of item cost (Deadlock convention; the
        // exact rate isn't critical, the user just wants to see the EVENT)
        const refund = Math.round((it.cost || 0) * 0.5);
        events.push({
          kind: 'sell',
          name: it.name, tier: it.tier, cost: refund, item_id: it.item_id,
          buy_min: it.sell_min,  // for sort
          sell_min: it.sell_min,
          original_cost: it.cost,
          phase: phaseFromBuyMin(it.sell_min),
          category: it.category,
          image: it.image,
        });
      }
    }

    // Group events by phase, sort within phase by buy time
    const byPhase = {early: [], mid: [], late: []};
    for (const e of events) byPhase[e.phase].push(e);
    for (const ph in byPhase) byPhase[ph].sort((a,b) => a.buy_min - b.buy_min);
    const totalCost = items.reduce((s,i) => s + (i.cost||0), 0);
    const spikeProgress = computeSpikeProgress(items);
    const sigCount = items.filter(i => i.signature).length;

    // Ability data for current slice
    const abInfo = h.ability_orders[mmrSlice];
    const slice = h.mmr[mmrSlice];
    const wr = slice.wr;

    main.innerHTML = `
      <div class="hero-header">
        <img src="${h.image || ''}" class="hero-portrait" onerror="this.style.opacity=0.2">
        <div class="hero-title">
          <h2>${h.name}</h2>
          <div class="stats">
            <div class="stat"><strong>Baseline WR:</strong> <span class="wr-badge ${wrClass(wr)}">${fmtPct(wr)}</span></div>
            <div class="stat"><strong>Sample:</strong> ${slice.matches.toLocaleString()} matches · ${slice.players.toLocaleString()} players</div>
            <div class="stat"><strong>Build cost:</strong> ${fmtCost(totalCost)}</div>
            ${sigCount > 0 ? `<div class="stat"><strong>Signature picks:</strong> ${sigCount} ⭐ <span style="color:var(--text-dim);font-size:11px">hero-specific items</span></div>` : ''}
          </div>
        </div>
      </div>

      <section>
        <h3>Ability Priority (Winner-Weighted)</h3>
        <div class="summary-line">Sorted by average AP investment among players who win — bigger lead vs population = more important to upgrade.</div>
        ${renderAbilityPriority(abInfo.priority, h.abilities)}
      </section>

      <section>
        <h3>Best Opener — First 4 Ability Points</h3>
        ${abInfo.best_opener ? renderOrderCard(abInfo.best_opener, 'opener') : '<div class="summary-line">No order with sufficient sample.</div>'}
        ${abInfo.alternate_openers && abInfo.alternate_openers.length ? `
          <details>
            <summary>${abInfo.alternate_openers.length} alternate openers</summary>
            <div class="alt-orders">
              ${abInfo.alternate_openers.map(o => renderOrderCard(o, 'opener-alt')).join('')}
            </div>
          </details>` : ''}
      </section>

      <section>
        <h3>Best Full Ability Order</h3>
        ${abInfo.best_full ? renderOrderCard(abInfo.best_full, 'full') : '<div class="summary-line">No order with sufficient sample.</div>'}
        ${abInfo.alternate_fulls && abInfo.alternate_fulls.length ? `
          <details>
            <summary>${abInfo.alternate_fulls.length} alternate full orders</summary>
            ${abInfo.alternate_fulls.map(o => renderOrderCard(o, 'full-alt')).join('')}
          </details>` : ''}
      </section>

      <section>
        <h3>Build Archetypes</h3>
        <div class="summary-line">
          Community builds for this hero, clustered by item composition (Jaccard distance).
          Click <strong>View this build</strong> on any archetype to swap the build view below.
          ⭐ items mark hero-specific picks — items this hero uses ≥2× more than the average hero.
        </div>
        ${renderArchetypesPanel(h.archetypes, activeArchIdx, h.id)}
      </section>

      ${activeArch ? `
        <div class="build-view-banner">
          <span class="label">Viewing</span>
          <span><strong>${escHtml(activeArch.label)}</strong> archetype build · ${activeArch.build_count} community builds · ${(activeArch.avg_wr*100).toFixed(2)}% avg WR · <em style="color:var(--text-dim);font-style:normal">build method: ${activeArch.build_method === 'synergy_ilp' ? 'synergy ILP (stat-optimized for this archetype)' : 'frequency (popularity-aggregated)'}</em></span>
          <button class="reset" data-reset-hero="${h.id}">← Back to recommended</button>
        </div>
      ` : ''}

      <section>
        <h3>Matchup Counter Picks</h3>
        <div class="summary-line">
          Click enemy heroes you'll be facing — the panel below ranks items by their
          aggregated win-rate delta vs the baseline build for those matchups.
          <strong style="color:var(--good)">Green</strong> = buy this when facing them,
          <strong style="color:var(--bad)">red</strong> = these items underperform vs them.
        </div>
        ${renderCounterPanel(h)}
      </section>

      <section>
        <h3>Investment Spike Progression</h3>
        <div class="summary-line">
          Each bar shows cumulative souls spent in that category as the build comes online.
          <span style="opacity:0.4;color:var(--accent)">■</span> = early-game spend ·
          <span style="opacity:0.65;color:var(--accent)">■</span> = added by mid-game ·
          <span style="color:var(--accent)">■</span> = added by late-game.
          Checkpoint labels below the bar show <strong>exactly</strong> how much you've spent at the end of each phase, so you can read off when each category crosses the <strong style="color:var(--accent)">4,800</strong> major spike (this patch: weapon ${getSpikeBonus().weapon[3200]}→${getSpikeBonus().weapon[4800]}%, vitality ${getSpikeBonus().vitality[3200]}→${getSpikeBonus().vitality[4800]}%, spirit ${getSpikeBonus().spirit[3200]}→${getSpikeBonus().spirit[4800]}%).
        </div>
        ${renderSpikePanel(items, spikeProgress.byPhaseEnd)}
      </section>

      <section>
        <div class="copy-build-row">
          <button class="copy-build-btn" data-copy-hero="${h.id}">📋 Copy build to clipboard</button>
        </div>
        <h3>Item Build by Phase</h3>
        <div class="summary-line">
          From the synergy-aware ILP method — items chosen for win rate <em>and</em> pairwise synergy. Buy times are population averages.
          Hover any item with a community-build note to see the tooltip authors wrote about it.
        </div>
        <div class="summary-line" style="margin-top:-8px">
          <span class="tag-pill tag-core">CORE</span> in &gt;70% of top builds &nbsp;·&nbsp;
          <span class="tag-pill tag-flex">FLEX</span> 30–70% &nbsp;·&nbsp;
          <span class="tag-pill tag-situational">SIT.</span> &lt;30% &nbsp;·&nbsp;
          <span class="tag-pill tag-stat">STAT</span> stat-derived only
        </div>
        <div class="phases">
          <div class="phase-col">
            <h4>Early <span class="when">${phaseWhen.early}</span></h4>
            ${byPhase.early.length ? byPhase.early.map(renderEvent).join('') : '<div class="summary-line">—</div>'}
            ${renderPhaseSpikeSummary(spikeProgress.byPhaseEnd.early)}
          </div>
          <div class="phase-col">
            <h4>Mid <span class="when">${phaseWhen.mid}</span></h4>
            ${byPhase.mid.length ? byPhase.mid.map(renderEvent).join('') : '<div class="summary-line">—</div>'}
            ${renderPhaseSpikeSummary(spikeProgress.byPhaseEnd.mid)}
          </div>
          <div class="phase-col">
            <h4>Late <span class="when">${phaseWhen.late}</span></h4>
            ${byPhase.late.length ? byPhase.late.map(renderEvent).join('') : '<div class="summary-line">—</div>'}
            ${renderPhaseSpikeSummary(spikeProgress.byPhaseEnd.late)}
          </div>
        </div>
      </section>
    `;
  }

  function renderAbilityPriority(priority, heroAbilities) {
    return priority.map(a => {
      const heroAbility = heroAbilities.find(x => x.id === a.ability_id) || {};
      const img = heroAbility.image;
      const premium = a.winner_premium_ap;
      const cls = premium > 0.05 ? 'good' : premium < -0.05 ? 'bad' : '';
      const sign = premium > 0 ? '+' : '';
      return `
        <div class="ability-row">
          <div class="icon">${img ? `<img src="${img}" onerror="this.style.display='none';this.parentNode.innerHTML='<span class=placeholder>'+a.name.charAt(0)+'</span>'">` : `<span class="placeholder">${a.name.charAt(0)}</span>`}</div>
          <div>
            <div class="name">${a.name}</div>
            <div class="role">avg AP across all players: ${a.avg_ap_all_players}</div>
          </div>
          <div class="ap-stat"><div class="v">${a.avg_ap_winners}</div>winners' avg AP</div>
          <div class="ap-stat"><div class="v premium ${cls}">${sign}${(premium).toFixed(2)}</div>winner premium</div>
        </div>
      `;
    }).join('');
  }

  const SHORT_AB = name => {
    // Use first letter or a known short — but the names are unique enough
    return name;
  };

  function renderOrderCard(order, kind) {
    const seq = order.sequence_names || [];
    return `
      <div class="order-card">
        <div class="order-seq">
          ${seq.map((n,i) => `<span class="step"><span class="num">${i+1}</span>${n}</span>`).join('')}
        </div>
        <div class="order-stats">
          <span class="wr-badge ${wrClass(order.win_rate)}">${fmtPct(order.win_rate)}</span>
          over <strong>${order.matches.toLocaleString()}</strong> matches
          ${order.players ? `· ${order.players.toLocaleString()} players` : ''}
        </div>
      </div>
    `;
  }

  const TAG_LABEL = { core: 'CORE', flex: 'FLEX', situational: 'SIT.', stat: 'STAT' };
  const TAG_TITLE = {
    core: 'In >70% of top community builds for this hero',
    flex: 'In 30–70% of top community builds — situational pick',
    situational: 'Used in <30% of top builds — buy when needed',
    stat: 'Stat-derived pick (no community build uses it yet)',
  };
  const escAttr = s => (s||'').replace(/"/g, '&quot;').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const escHtml = s => (s||'').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  function renderEvent(e) {
    if (e.kind === 'stage') return renderStageRow(e);
    if (e.kind === 'sell')  return renderSellRow(e);
    return renderItemRow(e);
  }

  function renderSellRow(sell) {
    const cat = sell.category;
    const imgPart = sell.image
      ? `<img src="${sell.image}" style="filter:grayscale(0.6);opacity:0.7" onerror="this.style.display='none';this.parentNode.innerHTML='<span class=placeholder>T${sell.tier}</span>'">`
      : `<span class="placeholder">T${sell.tier}</span>`;
    return `
      <div class="item-row is-sell" title="Population avg: this slot gets sold around minute ${sell.sell_min}, refunding roughly half the cost — frees a slot for late-game purchases">
        <div class="icon">${imgPart}</div>
        <div>
          <div class="name"><span class="sell-tag">↓ Sell</span>${escHtml(sell.name)}</div>
          <div class="meta">
            <span class="cat-pill cat-${cat}">${cat}</span>
            sell@${sell.sell_min}min · originally bought for ${fmtCost(sell.original_cost || 0)}
          </div>
        </div>
        <div class="cost">${fmtCost(sell.cost)}</div>
      </div>
    `;
  }

  function renderStageRow(stage) {
    const cat = stage.category;
    // Stage rows render an imbue badge when the staged component is itself
    // imbuable (e.g. Compress Cooldown). Mirrors the renderItemRow logic so
    // a player sees the same 🔮 → ability info on every imbuable line.
    let stageImbBadge = '';
    if (stage.imbue) {
      const IMBUE_LABEL_S = {
        imbue_modifier_value: 'Imbue: stats',
        imbue_active: 'Imbue: any active',
        imbue_active_non_ult: 'Imbue: non-ult active',
      };
      const IMBUE_TITLE_S = {
        imbue_modifier_value: 'Imbue this passive\\'s stats onto an ability of your choice',
        imbue_active: 'Imbue this onto one of your active abilities (works on ultimates too)',
        imbue_active_non_ult: 'Imbue this onto a non-ultimate active ability',
      };
      const lbl = IMBUE_LABEL_S[stage.imbue] || 'Imbuable';
      let ttl = IMBUE_TITLE_S[stage.imbue] || 'Can be imbued onto an ability';
      let target = '';
      if (stage.imbue_target_id) {
        const itemsDict = (activePatch.items_dict || {});
        const info = itemsDict[stage.imbue_target_id] || itemsDict[String(stage.imbue_target_id)];
        if (info && info.name) {
          if (stage.imbue_target_inferred) {
            target = ` <span style="color:var(--accent);font-weight:500;opacity:0.75">→ ${escHtml(info.name)} <span style="font-size:10px;font-weight:400">(inferred)</span></span>`;
            ttl = ttl + ' — inferred from this hero\\'s most-common imbue target across other items';
          } else {
            target = ` <span style="color:var(--accent);font-weight:600">→ ${escHtml(info.name)}</span>`;
            const sharePct = stage.imbue_target_share != null
              ? ` (${(stage.imbue_target_share*100).toFixed(0)}% of community builds)` : '';
            ttl = ttl + ' — most-common community target: ' + info.name + sharePct;
          }
        }
      }
      stageImbBadge = `<span class="imbue-badge" title="${escAttr(ttl)}">🔮 ${escHtml(lbl)}${target}</span>`;
    }
    return `
      <div class="item-row is-stage" title="Pre-buy that upgrades to ${escAttr(stage.upgrades_to_name)} later in the build">
        <div class="icon"><span class="placeholder">T${stage.tier}</span></div>
        <div>
          <div class="name">T${stage.tier} ${escHtml(stage.name)}</div>
          <div class="meta">
            <span class="cat-pill cat-${cat}">${cat}</span>
            ${stageImbBadge}
            buy@${stage.buy_min}min · pre-buy chip
          </div>
          <div class="upgrades-to">
            <span class="stage-arrow">→</span> upgrades into <strong>${escHtml(stage.upgrades_to_name)}</strong> (T${stage.upgrades_to_tier}) in late game
          </div>
        </div>
        <div class="cost">${fmtCost(stage.cost)}</div>
      </div>
    `;
  }

  // Each category bar is now a 3-segment progressive fill: early / mid / late
  // (lighter → darker), with checkpoint markers below at the phase boundaries
  // showing exactly what's spent at each phase end. Reads left-to-right as
  // a build-comes-online timeline rather than a "final state only" snapshot.
  function renderSpikePanel(items, byPhaseEnd) {
    const cats = ['weapon', 'vitality', 'spirit'];
    return `<div class="spike-panel">${cats.map(cat => {
      const earlyEnd = (byPhaseEnd && byPhaseEnd.early) ? (byPhaseEnd.early[cat] || 0) : 0;
      const midEnd   = (byPhaseEnd && byPhaseEnd.mid)   ? (byPhaseEnd.mid[cat]   || 0) : 0;
      const lateEnd  = (byPhaseEnd && byPhaseEnd.late)  ? (byPhaseEnd.late[cat]  || 0) : 0;
      const total = lateEnd;
      const crossed = spikesCrossed(total);
      const major = total >= SPIKE_MAJOR;
      const bonus = getSpikeBonus()[cat];
      const finalBonus = crossed.length ? bonus[crossed[crossed.length-1]] : 0;
      const unit = SPIKE_UNIT[cat];

      // Segment positions as % of the display max
      const pct = (v) => (Math.min(v, SPIKE_DISPLAY_MAX) / SPIKE_DISPLAY_MAX) * 100;
      const earlyPct = pct(earlyEnd);
      const midPct   = pct(midEnd);
      const latePct  = pct(lateEnd);

      // Determine which segment is the leftmost non-empty (for left rounding)
      let leftmost = '';
      if (earlyPct > 0) leftmost = 'early';
      else if (midPct > 0) leftmost = 'mid';
      else if (latePct > 0) leftmost = 'late';

      const segHtml = (cls, leftP, rightP) => {
        const w = rightP - leftP;
        if (w <= 0.01) return '';
        const lm = (cls === leftmost) ? ' seg-leftmost' : '';
        return `<div class="spike-fill seg-${cls}${lm}" style="left:${leftP}%;width:${w}%"></div>`;
      };

      const fills = [
        segHtml('early', 0,        earlyPct),
        segHtml('mid',   earlyPct, midPct),
        segHtml('late',  midPct,   latePct),
      ].join('');

      const marks = SPIKE_THRESHOLDS.map(t => {
        const left = (t / SPIKE_DISPLAY_MAX) * 100;
        const isCrossed = total >= t;
        const isMajor = t === SPIKE_MAJOR;
        const cls = ['spike-mark', isCrossed ? 'crossed' : '', isMajor ? 'major' : ''].filter(Boolean).join(' ');
        return `<span class="${cls}" style="left:${left}%"><span class="lbl-mark">${t >= 1000 ? (t/1000)+'k' : t}</span></span>`;
      }).join('');

      // Phase checkpoints below the bar — only render distinct positions.
      const checkpoints = [];
      const seen = new Set();
      const pushCheckpoint = (phaseLabel, pos, value, durationLbl) => {
        const key = pos.toFixed(1) + ':' + value;
        if (seen.has(key) || pos < 0.3) return;
        seen.add(key);
        const isMajorCp = value >= SPIKE_MAJOR;
        const phaseClass = isMajorCp ? 'major' : '';
        checkpoints.push(`
          <div class="phase-checkpoint ${phaseClass}" style="left:${pos}%">
            <span class="pc-marker"></span>
            <span class="pc-cost">${fmtCost(value)}</span>
            <span class="pc-tag">${phaseLabel}</span>
          </div>
        `);
      };
      pushCheckpoint('end early', earlyPct, earlyEnd);
      pushCheckpoint('end mid',   midPct,   midEnd);
      pushCheckpoint('final',     latePct,  lateEnd);

      return `
        <div class="spike-row ${cat}">
          <div class="lbl">${cat}</div>
          <div class="spike-bar">
            ${fills}
            ${marks}
            ${checkpoints.join('')}
            <div style="position:absolute;top:50%;right:8px;transform:translateY(-50%);font-size:11px;font-weight:600;color:var(--text)">
              ${crossed.length ? `<span style="color:var(--text-dim);font-weight:400">+${finalBonus}${unit}</span>` : ''}
              ${major ? '<span style="color:var(--accent);font-weight:700">  ⚡ SPIKE</span>' : ''}
            </div>
          </div>
        </div>
      `;
    }).join('')}</div>`;
  }

  function renderPhaseSpikeSummary(totalsAtPhaseEnd) {
    if (!totalsAtPhaseEnd) return '';
    const cats = ['weapon', 'vitality', 'spirit'];
    const parts = cats.map(cat => {
      const total = totalsAtPhaseEnd[cat] || 0;
      const crossed = spikesCrossed(total);
      const major = total >= SPIKE_MAJOR;
      const ticks = crossed.length;
      const label = total === 0
        ? `<span class="pend">${cat}: $0</span>`
        : major
          ? `<span class="major">${cat}: ${fmtCost(total)} ⚡</span>`
          : `<span class="ok">${cat}: ${fmtCost(total)} (${ticks}/${SPIKE_THRESHOLDS.length})</span>`;
      return label;
    });
    return `<div class="phase-spike-summary">at end of phase &nbsp;·&nbsp; ${parts.join(' &nbsp;·&nbsp; ')}</div>`;
  }

  function renderItemRow(item) {
    const cat = item.category;
    const slot = item.slot;
    const isFlex = slot === 'flex';
    const tag = item.tag || 'stat';
    const pickRate = item.pick_rate || 0;
    const hasAnnot = !!(item.annotation && item.annotation.length);
    const tagLabel = TAG_LABEL[tag] || tag.toUpperCase();
    const tagTitle = TAG_TITLE[tag] || '';
    const isSignature = !!item.signature;
    const affinity = item.affinity;
    const sigStar = isSignature
      ? `<span class="signature-star" title="Hero-specific: this hero picks ${item.name} ${affinity ? affinity.toFixed(1) + '× ' : ''}more often than the average hero">⭐</span>`
      : '';
    const pickBar = pickRate > 0
      ? `<span class="pick-rate-bar" title="${(pickRate*100).toFixed(0)}% of top community builds use this"><i style="width:${(pickRate*100).toFixed(0)}%"></i></span>`
      : '';
    const tooltip = hasAnnot
      ? `<div class="annot-tooltip"><span class="annot-source">Community build note · ${(pickRate*100).toFixed(0)}% pick rate${affinity ? ' · ' + affinity.toFixed(1) + '× hero affinity' : ''}</span>${escHtml(item.annotation)}</div>`
      : '';
    const dataAnn = hasAnnot ? ` data-annotation="${escAttr(item.annotation)}"` : '';
    const rowClasses = ['item-row'];
    if (isSignature) rowClasses.push('is-signature');
    // Only show the inline chip line for ancestors WITHOUT buy-time data
    // (those don't get their own stage row). Ancestors with buy times now
    // appear in their actual phase column, so the chip would be redundant.
    const chain = (item.lineage_chain || []).filter(c => c.avg_buy_time_min == null);
    const chainHtml = chain.length
      ? `<div class="lineage-chain">
           <span class="lc-label">Also pre-buy</span>
           ${chain.map(c =>
             `<span class="lc-stage" title="${escAttr(c.name)} (T${c.tier}, ${fmtCost(c.cost)})">T${c.tier} ${escHtml(c.name)} ${fmtCost(c.cost)}</span>`
           ).join('<span class="lc-arrow">→</span>')}
         </div>`
      : '';
    // Cooldown badge for active items, imbue badge for items that imbue an ability
    const IMBUE_LABEL = {
      imbue_modifier_value: 'Imbue: stats',
      imbue_active: 'Imbue: any active',
      imbue_active_non_ult: 'Imbue: non-ult active',
    };
    const IMBUE_TITLE = {
      imbue_modifier_value: 'Imbue this passive\\'s stats onto an ability of your choice',
      imbue_active: 'Imbue this onto one of your active abilities (works on ultimates too)',
      imbue_active_non_ult: 'Imbue this onto a non-ultimate active ability',
    };
    let cdBadge = '';
    if (item.is_active && item.cooldown_s != null && item.cooldown_s > 0) {
      const s = item.cooldown_s;
      const txt = s >= 60 ? `${Math.round(s/60*10)/10}m` : `${Math.round(s)}s`;
      cdBadge = `<span class="cd-badge" title="Active item — press to use, ${s}s cooldown">⚡ CD ${txt}</span>`;
    }
    let imbBadge = '';
    if (item.imbue) {
      const lbl = IMBUE_LABEL[item.imbue] || 'Imbuable';
      let ttl = IMBUE_TITLE[item.imbue] || 'Can be imbued onto an ability';
      // Resolve community-build imbue target to an ability name via the
      // shared items_dict (it carries hero abilities under their item_ids).
      let target = '';
      if (item.imbue_target_id) {
        const itemsDict = (activePatch.items_dict || {});
        const info = itemsDict[item.imbue_target_id] || itemsDict[String(item.imbue_target_id)];
        if (info && info.name) {
          // Inferred targets (no community-build evidence for THIS item;
          // we picked the hero's most-frequent imbue target across other
          // items) get a slightly dimmer look and a tilde prefix to flag
          // it as a weaker signal.
          if (item.imbue_target_inferred) {
            target = ` <span style="color:var(--accent);font-weight:500;opacity:0.75">→ ${escHtml(info.name)} <span style="font-size:10px;font-weight:400">(inferred)</span></span>`;
            ttl = ttl + ' — inferred from this hero\\'s most-common imbue target across other items (no community build evidence for this specific item)';
          } else {
            target = ` <span style="color:var(--accent);font-weight:600">→ ${escHtml(info.name)}</span>`;
            const sharePct = item.imbue_target_share != null
              ? ` (${(item.imbue_target_share*100).toFixed(0)}% of community builds)` : '';
            ttl = ttl + ' — most-common community target: ' + info.name + sharePct;
          }
        }
      }
      imbBadge = `<span class="imbue-badge" title="${escAttr(ttl)}">🔮 ${escHtml(lbl)}${target}</span>`;
    }

    return `
      <div class="${rowClasses.join(' ')}"${dataAnn}>
        <div class="icon">
          ${item.image ? `<img src="${item.image}" onerror="this.style.display='none';this.parentNode.innerHTML='<span class=placeholder>'+(item.tier?'T'+item.tier:'?')+'</span>'">` : `<span class="placeholder">T${item.tier||'?'}</span>`}
        </div>
        <div>
          <div class="name">${sigStar}${item.name}<span class="tag-pill tag-${tag}" title="${tagTitle}">${tagLabel}</span>${pickBar}</div>
          <div class="meta">
            <span class="cat-pill cat-${cat}">${cat}</span>
            ${cdBadge}${imbBadge}
            ${isFlex ? '<span class="slot-flex">FLEX SLOT · </span>' : ''}
            T${item.tier} · buy@${item.buy_min}min · WR ${fmtPct(item.wr)}
          </div>
          ${chainHtml}
        </div>
        <div class="cost">${fmtCost(item.cost)}</div>
        ${tooltip}
      </div>
    `;
  }

  // Per-enemy aggregate matchup signal — sum of all positive deltas minus
  // sum of negative deltas. Positive = your hero wins this matchup; negative
  // = you struggle vs them.
  function aggregateMatchupSignal(counterList) {
    if (!counterList) return 0;
    return counterList.reduce((acc, c) => acc + (c.delta_pp || 0), 0);
  }

  function renderMatchupRankings(hero, counters) {
    const ranked = [];
    for (const e of activePatch.heroes) {
      if (e.id === hero.id) continue;
      const list = counters[e.id] || counters[String(e.id)];
      if (!list || list.length === 0) continue;
      const signal = aggregateMatchupSignal(list);
      ranked.push({ enemy: e, signal });
    }
    if (ranked.length < 4) return '';
    ranked.sort((a, b) => b.signal - a.signal);
    const easiest = ranked.slice(0, 5);
    const hardest = ranked.slice(-5).reverse();

    const renderRow = (r) => `
      <div class="row" data-enemy-id="${r.enemy.id}" data-hero-id="${hero.id}" title="Click to add ${escAttr(r.enemy.name)} to selection">
        <img src="${r.enemy.image || ''}" loading="lazy" onerror="this.style.opacity=0.3">
        <div class="name">${escHtml(r.enemy.name)}</div>
        <div class="delta">${r.signal >= 0 ? '+' : ''}${r.signal.toFixed(1)}pp</div>
      </div>
    `;

    return `
      <div class="matchup-rankings">
        <div class="col easy">
          <h5>↑ Easiest matchups for ${escHtml(hero.name)}</h5>
          ${easiest.map(renderRow).join('')}
        </div>
        <div class="col hard">
          <h5>↓ Hardest matchups for ${escHtml(hero.name)}</h5>
          ${hardest.map(renderRow).join('')}
        </div>
      </div>
    `;
  }

  function renderCounterPanel(hero) {
    const counters = (activePatch.counters || {})[hero.id] || (activePatch.counters || {})[String(hero.id)];
    if (!counters || Object.keys(counters).length === 0) {
      return `<div class="counter-empty">No counter-pick data on this patch yet (patch released too recently — needs more matches accumulated).</div>`;
    }
    const key = counterKey(hero.id);
    const selected = counterEnemiesByHero[key] || new Set();
    const matchupSection = renderMatchupRankings(hero, counters);

    // Render enemy hero grid (every playable hero except this one)
    const enemyGrid = activePatch.heroes
      .filter(e => e.id !== hero.id)
      .sort((a, b) => a.name.localeCompare(b.name))
      .map(e => {
        const isActive = selected.has(e.id);
        const dim = !counters[e.id] && !counters[String(e.id)] ? ' style="opacity:0.4"' : '';
        return `<div class="counter-enemy ${isActive ? 'active' : ''}" data-enemy-id="${e.id}" data-hero-id="${hero.id}"${dim}>
            <img src="${e.image || ''}" loading="lazy" onerror="this.style.opacity=0.3">
            <div class="lbl">${escHtml(e.name)}</div>
          </div>`;
      }).join('');

    // Aggregate counter signals across selected enemies
    let aggregated = '';
    if (selected.size === 0) {
      aggregated = `<div class="counter-empty">Select up to 6 enemy heroes above to see recommended item swaps for that matchup.</div>`;
    } else {
      const itemAgg = {};  // item_id → { total_delta, occurrences }
      for (const eid of selected) {
        const list = counters[eid] || counters[String(eid)] || [];
        for (const c of list) {
          const cur = itemAgg[c.item_id] || { total: 0, occurrences: 0 };
          cur.total += c.delta_pp;
          cur.occurrences += 1;
          itemAgg[c.item_id] = cur;
        }
      }
      const ranked = Object.entries(itemAgg).map(([iid, info]) => ({
        item_id: parseInt(iid, 10),
        total_delta: info.total,
        avg_delta: info.total / info.occurrences,
        occurrences: info.occurrences,
      })).sort((a, b) => b.total_delta - a.total_delta);

      const positives = ranked.filter(r => r.total_delta > 0).slice(0, 7);
      const negatives = ranked.filter(r => r.total_delta < 0).slice(-7).reverse();

      const itemsDict = activePatch.items_dict || {};
      const itemInfo = (iid) => itemsDict[iid] || itemsDict[String(iid)] || {};
      const renderRow = (r, sign) => {
        const info = itemInfo(r.item_id);
        return `
          <div class="counter-row ${sign}">
            <div class="icon">${info.image
              ? `<img src="${info.image}" onerror="this.style.display='none'">`
              : `<span style="font-size:11px;color:var(--text-dim)">T${info.tier||'?'}</span>`}</div>
            <div>
              <div class="name">${escHtml(info.name || '?')}</div>
              <div class="meta">
                <span class="cat-pill cat-${info.category}">${info.category||''}</span>
                T${info.tier||'?'} · matters in ${r.occurrences}/${selected.size} matchup${selected.size === 1 ? '' : 's'}
              </div>
            </div>
            <div class="delta">${r.total_delta >= 0 ? '+' : ''}${r.total_delta.toFixed(1)}pp</div>
          </div>
        `;
      };

      aggregated = `
        <div class="counter-results">
          <div class="buy">
            <h4>↑ Buy these vs this enemy lineup</h4>
            ${positives.length ? positives.map(r => renderRow(r, 'pos')).join('') : '<div class="counter-empty">No positive deltas in selected matchups.</div>'}
          </div>
          <div class="avoid">
            <h4>↓ Avoid / sell these vs this lineup</h4>
            ${negatives.length ? negatives.map(r => renderRow(r, 'neg')).join('') : '<div class="counter-empty">No negative deltas in selected matchups.</div>'}
          </div>
        </div>
        <div class="counter-summary">
          Aggregated across ${selected.size} selected enemy hero${selected.size === 1 ? '' : 'es'}.
          Δpp = sum of (WR vs that enemy) − (baseline WR) across the listed matchups.
          Each item must have at least 100 matches in the matchup-specific slice and 200 in the baseline to surface.
        </div>
      `;
    }

    return `<div class="counter-panel">
      ${matchupSection}
      <div class="counter-enemies">${enemyGrid}</div>
      ${aggregated}
    </div>`;
  }

  function renderArchetypesPanel(archetypes, activeIdx, heroId) {
    if (!archetypes || !archetypes.clusters || archetypes.clusters.length === 0) {
      return '<div class="summary-line">Not enough community builds to cluster.</div>';
    }
    // Filter out tiny clusters (<2 builds) — they're outliers, not archetypes
    const meaningful = archetypes.clusters.filter(c => c.build_count >= 2);
    if (meaningful.length === 0) {
      return `<div class="summary-line">Only ${archetypes.total_builds} community build(s) found — too few to cluster meaningfully.</div>`;
    }
    return `<div class="archetype-panel">${meaningful.map((c, idx) => {
      const isPrimary = idx === 0;
      const isActive = (activeIdx === idx);
      const mix = c.category_mix || {};
      const sigs = (c.signature_items || []).slice(0, 4);
      const sigLine = sigs.length
        ? `<div class="sig-items">Distinguishing items: ${sigs.map(s => `<span class="name-chip" title="${(s.in_cluster_rate*100).toFixed(0)}% of this archetype's builds use it">${escHtml(s.name)}</span>`).join('')}</div>`
        : '';
      const samples = (c.sample_build_names || []).slice(0, 2).map(escHtml).join(' · ');
      const sampleLine = samples ? `<div class="archetype-meta">Top builds: ${samples}</div>` : '';
      const hasBuild = !!(c.build && c.build.length);
      const button = hasBuild
        ? `<button class="view-btn" data-arch-hero="${heroId}" data-arch-idx="${idx}" title="${isActive ? 'Currently viewing this build' : 'Show this archetype\\'s aggregated build'}">${isActive ? 'Viewing' : 'View this build'}</button>`
        : '';
      return `
        <div class="archetype-row ${isPrimary ? 'primary' : ''} ${isActive ? 'active' : ''}">
          <div class="label-line">
            <span class="name">${isPrimary ? '★ ' : ''}${escHtml(c.label)}</span>
            <span class="share-pill">${(c.share*100).toFixed(0)}% of top builds · ${c.build_count} builds${c.avg_wr != null ? ' · ' + (c.avg_wr*100).toFixed(1) + '% avg WR' : ''}</span>
            ${button}
          </div>
          <div class="archetype-meta">
            Category mix:
            <span class="cat-bar" title="${(mix.weapon||0)*100}% weapon, ${(mix.vitality||0)*100}% vitality, ${(mix.spirit||0)*100}% spirit">
              <i class="weapon" style="width:${(mix.weapon||0)*100}%"></i><i class="vitality" style="width:${(mix.vitality||0)*100}%"></i><i class="spirit" style="width:${(mix.spirit||0)*100}%"></i>
            </span>
            <span style="color:var(--weapon)">${((mix.weapon||0)*100).toFixed(0)}%</span> /
            <span style="color:var(--vitality)">${((mix.vitality||0)*100).toFixed(0)}%</span> /
            <span style="color:var(--spirit)">${((mix.spirit||0)*100).toFixed(0)}%</span>
          </div>
          ${sigLine}
          ${sampleLine}
        </div>
      `;
    }).join('')}</div>`;
  }

  // Wire up controls
  document.getElementById('view-toggle').addEventListener('click', e => {
    if (e.target.tagName !== 'BUTTON') return;
    const v = e.target.dataset.view;
    if (!v || v === viewMode) return;
    viewMode = v;
    document.querySelectorAll('#view-toggle button').forEach(b => b.classList.toggle('active', b.dataset.view === v));
    renderMain();
  });

  // Hero search filter — debounced via input event
  const searchInput = document.getElementById('hero-search');
  searchInput.addEventListener('input', () => {
    heroFilter = searchInput.value.trim().toLowerCase();
    renderHeroGrid();
  });

  document.getElementById('patch-toggle').addEventListener('click', e => {
    if (e.target.tagName !== 'BUTTON') return;
    const pid = e.target.dataset.patch;
    if (!pid || pid === activePatchId) return;
    activePatchId = pid;
    activePatch = DATA.patches[pid];
    activeArchetypeIdxByHero = {};  // archetype refs are per-patch hero objects
    document.querySelectorAll('#patch-toggle button').forEach(b => b.classList.toggle('active', b.dataset.patch === pid));
    updatePatchInfo();  // also refreshes MMR toggle availability for new patch
    renderHeroGrid();
    renderMain();
  });
  document.getElementById('mmr-toggle').addEventListener('click', e => {
    if (e.target.tagName !== 'BUTTON') return;
    if (e.target.disabled) return;  // ignore clicks on slices with no data on the active patch
    mmrSlice = e.target.dataset.mmr;
    document.querySelectorAll('#mmr-toggle button').forEach(b => b.classList.toggle('active', b.dataset.mmr === mmrSlice));
    renderHeroGrid();
    renderMain();
  });
  document.getElementById('sort-buttons').addEventListener('click', e => {
    if (e.target.tagName !== 'BUTTON') return;
    sortMode = e.target.dataset.sort;
    document.querySelectorAll('#sort-buttons button').forEach(b => b.classList.toggle('active', b.dataset.sort === sortMode));
    renderHeroGrid();
  });

  // ---- Mobile nav drawer wiring ----
  // Hamburger button toggles the slide-out hero drawer; tapping the
  // backdrop closes it. The body class drives the CSS transform.
  const navToggle = document.getElementById('mobile-nav-toggle');
  const navBackdrop = document.getElementById('mobile-backdrop');
  if (navToggle) {
    navToggle.addEventListener('click', () => {
      document.body.classList.toggle('nav-open');
    });
  }
  if (navBackdrop) {
    navBackdrop.addEventListener('click', () => {
      document.body.classList.remove('nav-open');
    });
  }

  // Tap-to-toggle annotation tooltips on touch devices. Hover doesn't
  // fire on phones so we listen for taps on item rows that have an
  // annotation, then toggle a class that mirrors the :hover style.
  // First tap reveals the tooltip; second tap (or tapping another row)
  // dismisses it.
  document.addEventListener('click', e => {
    if (!matchMedia('(max-width: 900px)').matches) return;
    const row = e.target.closest('.item-row[data-annotation]');
    document.querySelectorAll('.item-row.show-tooltip').forEach(r => {
      if (r !== row) r.classList.remove('show-tooltip');
    });
    if (row) row.classList.toggle('show-tooltip');
  });

  // Initial render
  renderHeroGrid();
</script>
</body>
</html>
"""

html = HTML.replace("__DATA__", DATA_JSON)
target = ROOT / "deadlock_builds.html"
target.write_text(html)
print(f"[saved] {target}  {target.stat().st_size:,} bytes ({target.stat().st_size/1024:.1f} KB)")
