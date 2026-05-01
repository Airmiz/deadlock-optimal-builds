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
<title>Deadlock Optimal Builds — patch_125825</title>
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
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
  }
  .spike-row:last-child { border-bottom: none; }
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
    top: 0; left: 0; height: 100%;
    border-radius: 4px;
    background: rgba(240,169,59,0.18);
    border-right: 2px solid var(--accent);
    transition: width 0.2s;
  }
  .weapon .spike-fill   { background: rgba(214,133,107,0.18); border-right-color: var(--weapon); }
  .vitality .spike-fill { background: rgba(108,180,106,0.18); border-right-color: var(--vitality); }
  .spirit .spike-fill   { background: rgba(180,135,217,0.18); border-right-color: var(--spirit); }
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
</style>
</head>
<body>
<header>
  <div>
    <h1>DEADLOCK OPTIMAL BUILDS</h1>
    <div class="meta" id="patch-info">loading…</div>
  </div>
  <div style="display:flex; gap:14px; align-items:center;">
    <div class="toggle-group" id="patch-toggle"></div>
    <div class="toggle-group" id="mmr-toggle">
      <button data-mmr="all">All MMR</button>
      <button data-mmr="high" class="active">High MMR (Phantom+)</button>
    </div>
  </div>
</header>
<div class="layout">
  <aside>
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
  // Per-hero active archetype index — null/undefined means "use recommended"
  // Reset on patch change since hero objects differ between patches.
  let activeArchetypeIdxByHero = {};

  // Build the patch-toggle buttons. Sort by recency (newer patch_id first).
  const patchIds = Object.keys(DATA.patches).sort().reverse();
  const patchToggle = document.getElementById('patch-toggle');
  patchToggle.innerHTML = patchIds.map(pid => {
    const p = DATA.patches[pid];
    const cls = pid === activePatchId ? 'active' : '';
    const isNew = pid === patchIds[0] ? ' <span style="color:var(--good);font-size:9px;margin-left:3px">NEW</span>' : '';
    return `<button data-patch="${pid}" class="${cls}" title="${p.title}">${p.title}${isNew}</button>`;
  }).join('');

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
  }
  updatePatchInfo();

  const fmtPct = v => v == null ? '—' : (v*100).toFixed(2) + '%';
  const wrClass = v => v >= 0.50 ? 'good' : v >= 0.475 ? 'neutral' : 'bad';
  const fmtCost = v => '$' + v.toLocaleString();
  const titleCase = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
  const phaseWhen = { early: 'laning · ≤12.5 min', mid: 'mid game · 12.5–25 min', late: 'late game · 25+ min' };

  // Investment-spike thresholds (universal across all 38 heroes; verified from
  // hero asset data). The 4,800 milestone is the major spike — at that point
  // the per-category bonus more than doubles.
  const SPIKE_THRESHOLDS = [800, 1600, 2400, 3200, 4800, 7200, 9600, 16000];
  const SPIKE_MAJOR = 4800;
  const SPIKE_DISPLAY_MAX = 16000;
  // Bonus values at each threshold (per category). Same for all heroes.
  const SPIKE_BONUS = {
    weapon:   { 800: 7,  1600: 9,  2400: 13, 3200: 20, 4800: 49, 7200: 60, 9600: 80,  16000: 95 },
    vitality: { 800: 8,  1600: 10, 2400: 13, 3200: 17, 4800: 34, 7200: 39, 9600: 44,  16000: 48 },
    spirit:   { 800: 7,  1600: 11, 2400: 15, 3200: 19, 4800: 38, 7200: 48, 9600: 57,  16000: 66 },
  };
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
    if (sortMode === 'alpha') {
      order.sort((a,b) => a.name.localeCompare(b.name));
    } else {
      order.sort((a,b) => b.mmr[mmrSlice].wr - a.mmr[mmrSlice].wr);
    }
    grid.innerHTML = '';
    for (const h of order) {
      const div = document.createElement('div');
      div.className = 'hero-tile' + (h.id === selectedHeroId ? ' active' : '');
      const wr = h.mmr[mmrSlice].wr;
      const cls = wrClass(wr);
      div.innerHTML = `
        <img src="${h.image || ''}" loading="lazy" onerror="this.style.opacity=0.2">
        <div class="name">${h.name}</div>
        <div class="wr ${cls}">${fmtPct(wr)}</div>
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
  });

  function renderMain() {
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
    // Get build for current MMR slice (or the active archetype's composite)
    const items = activeArch ? activeArch.build : h.items_by_slice[mmrSlice];

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
          <span><strong>${escHtml(activeArch.label)}</strong> archetype build · ${activeArch.build_count} community builds · ${(activeArch.avg_wr*100).toFixed(2)}% avg WR</span>
          <button class="reset" data-reset-hero="${h.id}">← Back to recommended</button>
        </div>
      ` : ''}

      <section>
        <h3>Investment Spike Progression</h3>
        <div class="summary-line">
          Cumulative souls spent per category as the build comes online.
          The <strong style="color:var(--accent)">4,800</strong> milestone is the major spike —
          your per-category bonus <strong>more than doubles</strong> there
          (e.g. spirit goes from +19 to +38). Tick marks below show smaller thresholds.
        </div>
        ${renderSpikePanel(items)}
      </section>

      <section>
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
    return `
      <div class="item-row is-stage" title="Pre-buy that upgrades to ${escAttr(stage.upgrades_to_name)} later in the build">
        <div class="icon"><span class="placeholder">T${stage.tier}</span></div>
        <div>
          <div class="name">T${stage.tier} ${escHtml(stage.name)}</div>
          <div class="meta">
            <span class="cat-pill cat-${cat}">${cat}</span>
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

  function renderSpikePanel(items) {
    const cats = ['weapon', 'vitality', 'spirit'];
    const finalTotals = items.reduce((acc, it) => {
      if (it.category in acc) acc[it.category] += (it.cost || 0);
      return acc;
    }, { weapon: 0, vitality: 0, spirit: 0 });

    return `<div class="spike-panel">${cats.map(cat => {
      const total = finalTotals[cat];
      const crossed = spikesCrossed(total);
      // Display fill is capped at SPIKE_DISPLAY_MAX so the bar renders
      const displayTotal = Math.min(total, SPIKE_DISPLAY_MAX);
      const fillPct = (displayTotal / SPIKE_DISPLAY_MAX) * 100;
      const major = total >= SPIKE_MAJOR;
      const bonus = SPIKE_BONUS[cat];
      const finalBonus = crossed.length ? bonus[crossed[crossed.length-1]] : 0;
      const unit = SPIKE_UNIT[cat];

      const marks = SPIKE_THRESHOLDS.map(t => {
        const left = (t / SPIKE_DISPLAY_MAX) * 100;
        const isCrossed = total >= t;
        const isMajor = t === SPIKE_MAJOR;
        const cls = ['spike-mark', isCrossed ? 'crossed' : '', isMajor ? 'major' : ''].filter(Boolean).join(' ');
        return `<span class="${cls}" style="left:${left}%"><span class="lbl-mark">${t >= 1000 ? (t/1000)+'k' : t}</span></span>`;
      }).join('');

      return `
        <div class="spike-row ${cat}">
          <div class="lbl">${cat}</div>
          <div class="spike-bar">
            <div class="spike-fill" style="width:${fillPct}%"></div>
            ${marks}
            <div style="position:absolute;top:50%;right:8px;transform:translateY(-50%);font-size:11px;font-weight:600;color:var(--text)">
              ${fmtCost(total)}
              ${crossed.length ? `<span style="color:var(--text-dim);font-weight:400">  +${finalBonus}${unit}</span>` : ''}
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
      const ttl = IMBUE_TITLE[item.imbue] || 'Can be imbued onto an ability';
      imbBadge = `<span class="imbue-badge" title="${escAttr(ttl)}">🔮 ${escHtml(lbl)}</span>`;
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
  document.getElementById('patch-toggle').addEventListener('click', e => {
    if (e.target.tagName !== 'BUTTON') return;
    const pid = e.target.dataset.patch;
    if (!pid || pid === activePatchId) return;
    activePatchId = pid;
    activePatch = DATA.patches[pid];
    activeArchetypeIdxByHero = {};  // archetype refs are per-patch hero objects
    document.querySelectorAll('#patch-toggle button').forEach(b => b.classList.toggle('active', b.dataset.patch === pid));
    updatePatchInfo();
    renderHeroGrid();
    renderMain();
  });
  document.getElementById('mmr-toggle').addEventListener('click', e => {
    if (e.target.tagName !== 'BUTTON') return;
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
