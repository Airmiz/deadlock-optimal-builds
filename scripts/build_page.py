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
</style>
</head>
<body>
<header>
  <div>
    <h1>DEADLOCK OPTIMAL BUILDS</h1>
    <div class="meta" id="patch-info">loading…</div>
  </div>
  <div class="toggle-group" id="mmr-toggle">
    <button data-mmr="all">All MMR</button>
    <button data-mmr="high" class="active">High MMR (Phantom+)</button>
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
  document.getElementById('patch-info').textContent =
    DATA.patch.id + ' — ' + DATA.patch.title + '  ·  ' + DATA.heroes.length + ' heroes  ·  data: ' + DATA.data_source;

  let selectedHeroId = null;
  let mmrSlice = 'high';
  let sortMode = 'alpha';

  const fmtPct = v => v == null ? '—' : (v*100).toFixed(2) + '%';
  const wrClass = v => v >= 0.50 ? 'good' : v >= 0.475 ? 'neutral' : 'bad';
  const fmtCost = v => '$' + v.toLocaleString();
  const titleCase = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
  const phaseWhen = { early: 'laning · ≤12.5 min', mid: 'mid game · 12.5–25 min', late: 'late game · 25+ min' };

  function renderHeroGrid() {
    const grid = document.getElementById('hero-grid');
    let order = [...DATA.heroes];
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
    renderHeroGrid();
    renderMain();
  }

  function renderMain() {
    const main = document.getElementById('main');
    if (selectedHeroId == null) { main.innerHTML = `<div class="empty-state"><p>Select a hero from the left.</p></div>`; return; }
    const h = DATA.heroes.find(x => x.id === selectedHeroId);
    if (!h) return;

    // Get build for current MMR slice
    const items = h.items_by_slice[mmrSlice];
    // Group by phase
    const byPhase = {early: [], mid: [], late: []};
    for (const it of items) byPhase[it.phase].push(it);
    // Sort each phase by buy_min
    for (const ph in byPhase) byPhase[ph].sort((a,b) => a.buy_min - b.buy_min);
    const totalCost = items.reduce((s,i) => s + (i.cost||0), 0);

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
            ${byPhase.early.length ? byPhase.early.map(renderItemRow).join('') : '<div class="summary-line">—</div>'}
          </div>
          <div class="phase-col">
            <h4>Mid <span class="when">${phaseWhen.mid}</span></h4>
            ${byPhase.mid.length ? byPhase.mid.map(renderItemRow).join('') : '<div class="summary-line">—</div>'}
          </div>
          <div class="phase-col">
            <h4>Late <span class="when">${phaseWhen.late}</span></h4>
            ${byPhase.late.length ? byPhase.late.map(renderItemRow).join('') : '<div class="summary-line">—</div>'}
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

  function renderItemRow(item) {
    const cat = item.category;
    const slot = item.slot;
    const isFlex = slot === 'flex';
    const tag = item.tag || 'stat';
    const pickRate = item.pick_rate || 0;
    const hasAnnot = !!(item.annotation && item.annotation.length);
    const tagLabel = TAG_LABEL[tag] || tag.toUpperCase();
    const tagTitle = TAG_TITLE[tag] || '';
    const pickBar = pickRate > 0
      ? `<span class="pick-rate-bar" title="${(pickRate*100).toFixed(0)}% of top community builds use this"><i style="width:${(pickRate*100).toFixed(0)}%"></i></span>`
      : '';
    const tooltip = hasAnnot
      ? `<div class="annot-tooltip"><span class="annot-source">Community build note · ${(pickRate*100).toFixed(0)}% pick rate</span>${escHtml(item.annotation)}</div>`
      : '';
    const dataAnn = hasAnnot ? ` data-annotation="${escAttr(item.annotation)}"` : '';
    return `
      <div class="item-row"${dataAnn}>
        <div class="icon">
          ${item.image ? `<img src="${item.image}" onerror="this.style.display='none';this.parentNode.innerHTML='<span class=placeholder>'+(item.tier?'T'+item.tier:'?')+'</span>'">` : `<span class="placeholder">T${item.tier||'?'}</span>`}
        </div>
        <div>
          <div class="name">${item.name}<span class="tag-pill tag-${tag}" title="${tagTitle}">${tagLabel}</span>${pickBar}</div>
          <div class="meta">
            <span class="cat-pill cat-${cat}">${cat}</span>
            ${isFlex ? '<span class="slot-flex">FLEX SLOT · </span>' : ''}
            T${item.tier} · buy@${item.buy_min}min · WR ${fmtPct(item.wr)}
          </div>
        </div>
        <div class="cost">${fmtCost(item.cost)}</div>
        ${tooltip}
      </div>
    `;
  }

  // Wire up controls
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
