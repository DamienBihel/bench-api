const COLORS = ["#7cc4ff", "#f8b26a", "#b794f6", "#4ade80", "#f87171", "#fbbf24", "#34d399", "#c084fc"];

let DATA = null;
let CURRENT_RUN = null;
let SELECTED_MODELS = new Set();
const charts = {};

// Ranking sort state
let rankSortCol = "score";
let rankSortDir = "desc";

// Persiste quels <details> tests sont ouverts entre rebuilds
const OPEN_TESTS_KEY = "bench-api-open-tests";
function getOpenTests() {
  try { return new Set(JSON.parse(localStorage.getItem(OPEN_TESTS_KEY) || "[]")); }
  catch { return new Set(); }
}
function saveOpenTests(set) {
  localStorage.setItem(OPEN_TESTS_KEY, JSON.stringify([...set]));
}

function getCssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "";
}

/* ---------- theme ---------- */
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("bench-api-theme", theme);
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.textContent = theme === "light" ? "\u{1F319}" : "☀️";
  if (CURRENT_RUN) renderAll();
}
function initTheme() {
  const saved = localStorage.getItem("bench-api-theme");
  const prefersLight = window.matchMedia("(prefers-color-scheme: light)").matches;
  applyTheme(saved || (prefersLight ? "light" : "dark"));
  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    applyTheme(cur === "light" ? "dark" : "light");
  });
}
initTheme();

/* ---------- bootstrap ---------- */
async function load() {
  const res = await fetch("data.json", { cache: "no-store" });
  DATA = await res.json();

  const gen = document.getElementById("generated");
  if (DATA.generated_at) gen.textContent = "Généré : " + DATA.generated_at.replace("T", " ").slice(0, 16) + " UTC";

  initModelPanel();

  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  if (DATA.runs && DATA.runs.length) {
    loadRun(DATA.runs[0]);
  } else {
    document.getElementById("ranking-table").innerHTML = `<p class="hint">Aucun run disponible. Lance d'abord python harness/run.py</p>`;
  }
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.toggle("active", p.id === "tab-" + name));
}

function loadRun(run) {
  CURRENT_RUN = run;
  const models = uniqueModels(run);
  SELECTED_MODELS = new Set(models);
  buildModelCheckboxes(models);
  renderAll();
}

function modelMeta(model) { return (DATA.models || {})[model] || {}; }

function modelAlias(model) {
  const meta = modelMeta(model);
  if (meta.alias) return meta.alias;
  if (CURRENT_RUN) {
    const m = CURRENT_RUN.metrics.find(r => r.model === model);
    if (m && m.alias) return m.alias;
  }
  return model;
}

function modelSizeLabel(model) {
  const m = modelMeta(model);
  const bits = [];
  if (m.context) bits.push(m.context + " ctx");
  if (m.thinking) bits.push("thinking");
  if (m.price_input_per_1m) bits.push("$" + m.price_input_per_1m + "/M in");
  return bits.join(" · ");
}

const PROVIDER_ORDER = ["anthropic", "openai", "google", "mistral", "xai", "deepseek", "meta"];

function buildModelCheckboxes(models) {
  const cb = document.getElementById("model-checkboxes");
  cb.innerHTML = "";

  const groups = {};
  models.forEach(m => {
    const meta = modelMeta(m);
    const provider = meta._orphan ? "__autres" : (meta.provider || "__autres");
    (groups[provider] = groups[provider] || []).push(m);
  });

  const knownProviders = PROVIDER_ORDER.filter(p => groups[p]);
  const unknownProviders = Object.keys(groups)
    .filter(p => p !== "__autres" && !PROVIDER_ORDER.includes(p))
    .sort();
  const providerList = [...knownProviders, ...unknownProviders];
  if (groups["__autres"]) providerList.push("__autres");

  providerList.forEach(provider => {
    const groupModels = groups[provider].slice().sort((a, b) =>
      modelAlias(a).localeCompare(modelAlias(b))
    );

    const header = document.createElement("div");
    header.className = "provider-group-header";
    header.textContent = provider === "__autres" ? "AUTRES" : provider.toUpperCase();
    cb.appendChild(header);

    groupModels.forEach(m => {
      const id = "cb-" + m.replace(/[^a-z0-9]/gi, "_");
      const alias = modelAlias(m);
      const sizeLabel = modelSizeLabel(m);
      const label = document.createElement("label");
      label.innerHTML = `<input type="checkbox" id="${id}" value="${m}" checked> <span style="color:${modelColor(m)}">&#9679;</span> <strong>${alias}</strong>${sizeLabel ? ` <span class="model-size">(${sizeLabel})</span>` : ""}`;
      label.querySelector("input").addEventListener("change", e => {
        if (e.target.checked) SELECTED_MODELS.add(m); else SELECTED_MODELS.delete(m);
        updateModelCount();
        renderAll();
      });
      cb.appendChild(label);
    });
  });
  updateModelCount();
}

function updateModelCount() {
  const el = document.getElementById("model-count");
  if (!el || !CURRENT_RUN) return;
  el.textContent = `${SELECTED_MODELS.size}/${uniqueModels(CURRENT_RUN).length}`;
}

function initModelPanel() {
  const panel = document.getElementById("model-panel");
  if (!panel) return;
  panel.open = localStorage.getItem("bench-api-model-panel-open") === "1";
  panel.addEventListener("toggle", () => {
    localStorage.setItem("bench-api-model-panel-open", panel.open ? "1" : "0");
  });
}

function renderAll() {
  renderRankingTable();
  renderParetoChart();
  renderPivotTable();
  renderTestsCombined();
}

/* ---------- helpers ---------- */
function uniqueModels(run) { return [...new Set(run.metrics.map(m => m.model))]; }
function uniqueTests(run) {
  const seen = new Map();
  run.metrics.forEach(m => { if (!seen.has(m.test_id)) seen.set(m.test_id, m.test_label); });
  return [...seen.entries()].sort(([a], [b]) => a.localeCompare(b));
}
function activeModels() { return uniqueModels(CURRENT_RUN).filter(m => SELECTED_MODELS.has(m)); }
function modelColor(model) {
  const all = uniqueModels(CURRENT_RUN);
  return COLORS[all.indexOf(model) % COLORS.length];
}
function humanizeCriterionId(id) {
  const stripped = id.replace(/^[a-z0-9]+_/, "");
  const spaced = stripped.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function scoresForTest(model, test_id) {
  return (CURRENT_RUN.scores || []).filter(s => s.model === model && s.test_id === test_id);
}

/* ---------- Ranking table ---------- */
function modelLastRun(model) {
  const rows = CURRENT_RUN.metrics.filter(r => r.model === model && r.source_run);
  if (!rows.length) return null;
  return rows.map(r => r.source_run).sort().pop();
}

function buildRankingData() {
  const models = activeModels();
  return models.map(m => {
    const rows = CURRENT_RUN.metrics.filter(r => r.model === m);
    const totalCost = rows.reduce((s, r) => s + (r.cost_usd || 0), 0);
    const avgLat = rows.length ? rows.reduce((s, r) => s + (r.latency_s || 0), 0) / rows.length : 0;
    const totalReasoning = rows.reduce((s, r) => s + (r.reasoning_tokens || 0), 0);
    const totalOut = rows.reduce((s, r) => s + (r.tokens_out || 0), 0);
    const ratioReasoning = totalOut ? Math.round((totalReasoning / totalOut) * 100) : 0;
    const scoreRows = (CURRENT_RUN.scores || []).filter(s => s.model === m);
    const scorePct = scoreRows.length ? Math.round((scoreRows.filter(s => s.resultat === "PASS").length / scoreRows.length) * 100) : null;
    const meta = modelMeta(m);
    const isOrphan = meta._orphan === true;
    const lastRun = modelLastRun(m);
    return { model: m, alias: modelAlias(m), scorePct, totalCost, avgLat, totalReasoning, ratioReasoning, isOrphan, lastRun };
  });
}

function sortRankingData(rows) {
  return [...rows].sort((a, b) => {
    let va, vb;
    if (rankSortCol === "score") {
      va = a.scorePct ?? -1;
      vb = b.scorePct ?? -1;
    } else if (rankSortCol === "cost") {
      va = a.totalCost;
      vb = b.totalCost;
    } else if (rankSortCol === "latency") {
      va = a.avgLat;
      vb = b.avgLat;
    } else if (rankSortCol === "reasoning") {
      va = a.totalReasoning;
      vb = b.totalReasoning;
    } else if (rankSortCol === "lastrun") {
      va = a.lastRun || "";
      vb = b.lastRun || "";
    } else {
      va = a.alias;
      vb = b.alias;
    }
    if (va < vb) return rankSortDir === "asc" ? -1 : 1;
    if (va > vb) return rankSortDir === "asc" ? 1 : -1;
    // Secondary sort: score desc, cost asc
    if (rankSortCol !== "score") {
      const diff = (b.scorePct ?? -1) - (a.scorePct ?? -1);
      if (diff !== 0) return diff;
    }
    if (rankSortCol !== "cost") return a.totalCost - b.totalCost;
    return 0;
  });
}

function scoreClass(pct) {
  if (pct === null) return "";
  if (pct >= 80) return "score-high";
  if (pct >= 65) return "score-mid";
  return "score-low";
}

function renderRankingTable() {
  const container = document.getElementById("ranking-table");
  const rows = buildRankingData();
  if (!rows.length) {
    container.innerHTML = `<p class="hint">Aucun modèle sélectionné.</p>`;
    return;
  }
  const sorted = sortRankingData(rows);

  const cols = [
    { key: "rank",      label: "#",            sortable: false },
    { key: "model",     label: "Modèle",       sortable: true  },
    { key: "score",     label: "Score %",      sortable: true  },
    { key: "cost",      label: "Coût total $",  sortable: true  },
    { key: "latency",   label: "Latence moy/test", sortable: true },
    { key: "reasoning", label: "Reasoning",    sortable: true  },
    { key: "lastrun",   label: "Dernier test", sortable: true  },
  ];

  let html = `<table class="ranking-table"><thead><tr>`;
  cols.forEach(c => {
    if (!c.sortable) {
      html += `<th>${c.label}</th>`;
    } else {
      const active = rankSortCol === c.key;
      const arrow = active ? (rankSortDir === "asc" ? " &#9650;" : " &#9660;") : "";
      html += `<th class="sortable${active ? " sort-active" : ""}" data-col="${c.key}">${c.label}${arrow}</th>`;
    }
  });
  html += `</tr></thead><tbody>`;

  sorted.forEach((r, i) => {
    const scoreTd = r.scorePct !== null
      ? `<span class="score-val ${scoreClass(r.scorePct)}">${r.scorePct}%</span>`
      : `<span class="score-val">—</span>`;
    const costTd = `$${r.totalCost.toFixed(4)}`;
    const latTd = `${r.avgLat.toFixed(1)}s`;
    const reasoningTd = r.totalReasoning > 0
      ? `${r.totalReasoning.toLocaleString()} (${r.ratioReasoning}%)`
      : "—";
    const orphanBadge = r.isOrphan ? ` <span class="badge-orphan">ancien</span>` : "";
    const lastRunTd = r.lastRun || "—";

    html += `<tr>`;
    html += `<td class="rank-num">${i + 1}</td>`;
    html += `<td class="model-name">${escapeHtml(r.alias)}${orphanBadge}</td>`;
    html += `<td class="num">${scoreTd}</td>`;
    html += `<td class="num mono">${costTd}</td>`;
    html += `<td class="num mono">${latTd}</td>`;
    html += `<td class="num mono">${reasoningTd}</td>`;
    html += `<td class="mono muted-cell">${escapeHtml(lastRunTd)}</td>`;
    html += `</tr>`;
  });

  html += `</tbody></table>`;
  container.innerHTML = html;

  container.querySelectorAll("th.sortable").forEach(th => {
    th.addEventListener("click", () => {
      const col = th.dataset.col;
      if (rankSortCol === col) {
        rankSortDir = rankSortDir === "asc" ? "desc" : "asc";
      } else {
        rankSortCol = col;
        rankSortDir = col === "cost" || col === "latency" ? "asc" : "desc";
      }
      renderRankingTable();
    });
  });
}

/* ---------- Pareto chart ---------- */
function renderParetoChart() {
  const ctx = document.getElementById("chart-pareto");
  if (charts["chart-pareto"]) charts["chart-pareto"].destroy();
  const models = activeModels();
  const datasets = models.map(m => {
    const rows = CURRENT_RUN.metrics.filter(r => r.model === m);
    const totalCost = rows.reduce((s, r) => s + (r.cost_usd || 0), 0);
    const scoreRows = (CURRENT_RUN.scores || []).filter(s => s.model === m);
    const pct = scoreRows.length ? (scoreRows.filter(s => s.resultat === "PASS").length / scoreRows.length) * 100 : 0;
    return {
      label: modelAlias(m),
      data: [{ x: totalCost, y: pct }],
      backgroundColor: modelColor(m),
      borderColor: modelColor(m),
      pointRadius: 9,
      pointHoverRadius: 13,
    };
  });

  charts["chart-pareto"] = new Chart(ctx, {
    type: "scatter",
    data: { datasets },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: getCssVar("--fg") } },
        tooltip: {
          callbacks: {
            label: c => c.dataset.label + " : " + c.parsed.y.toFixed(0) + "% pour $" + c.parsed.x.toFixed(4),
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: "Cout total ($)", color: getCssVar("--chart-tick") },
          ticks: { color: getCssVar("--chart-tick"), callback: v => "$" + Number(v).toFixed(3) },
          grid: { color: getCssVar("--chart-grid") },
        },
        y: {
          title: { display: true, text: "Score %", color: getCssVar("--chart-tick") },
          min: 0,
          max: 100,
          ticks: { color: getCssVar("--chart-tick"), callback: v => v + "%" },
          grid: { color: getCssVar("--chart-grid") },
        },
      },
    },
  });
}

/* ---------- Pivot table cost ---------- */
function renderPivotTable() {
  const container = document.getElementById("pivot-table");
  const models = activeModels();
  const tests = uniqueTests(CURRENT_RUN);

  if (!models.length || !tests.length) {
    container.innerHTML = `<p class="hint">Pas de données.</p>`;
    return;
  }

  let maxCost = 0;
  models.forEach(m => {
    tests.forEach(([id]) => {
      const row = CURRENT_RUN.metrics.find(r => r.model === m && r.test_id === id);
      if (row && row.cost_usd > maxCost) maxCost = row.cost_usd;
    });
  });

  const promptById2 = {};
  (DATA.prompts || []).forEach(p => { promptById2[p.id] = p; });

  let html = `<table class="pivot-table"><thead><tr><th class="pivot-model-header">Modèle</th>`;
  tests.forEach(([id]) => {
    const testLabel = promptById2[id]?.label || humanizeCriterionId(id);
    html += `<th class="pivot-test-header" title="${escapeHtml(testLabel)}">${escapeHtml(id)}</th>`;
  });
  html += `</tr></thead><tbody>`;

  models.forEach(m => {
    html += `<tr><td class="pivot-model-cell">${escapeHtml(modelAlias(m))}</td>`;
    tests.forEach(([id]) => {
      const row = CURRENT_RUN.metrics.find(r => r.model === m && r.test_id === id);
      if (!row || row.cost_usd == null) {
        html += `<td class="pivot-cell pivot-empty">—</td>`;
      } else {
        const opacity = maxCost > 0 ? (row.cost_usd / maxCost) : 0;
        const bg = `rgba(251, 146, 60, ${(opacity * 0.75 + 0.05).toFixed(3)})`;
        html += `<td class="pivot-cell" style="background:${bg}">$${row.cost_usd.toFixed(4)}</td>`;
      }
    });
    html += `</tr>`;
  });

  html += `</tbody></table>`;
  container.innerHTML = html;
}

/* ---------- Tests combinés ---------- */

function buildTestDocSection(prompt) {
  const section = document.createElement("div");
  section.className = "doc-section";

  const axe = prompt.axe || "n/a";
  const promptText = (prompt.prompt || prompt.prompt_template || "")
    .replace("{vault_dump}", "[~50k tokens vault]")
    .replace("{brief}", "[brief client fictif]");
  const criteria = prompt.criteria || [];

  let html = `<h3>Documentation</h3>`;
  html += `<p><strong>Axe :</strong> ${escapeHtml(axe)}</p>`;
  if (prompt.description) {
    html += `<p class="test-description-inline">${escapeHtml(prompt.description)}</p>`;
  }
  html += `<p><strong>Prompt envoyé :</strong></p>`;
  html += `<pre>${escapeHtml(promptText)}</pre>`;

  if (criteria.length) {
    html += `<p><strong>Critères de scoring (${criteria.length}) :</strong></p>`;
    html += `<table class="criteria-table"><thead><tr>`;
    html += `<th style="width:25%;">Id</th><th>Description (condition PASS)</th>`;
    html += `</tr></thead><tbody>`;
    criteria.forEach(c => {
      html += `<tr><td><code>${escapeHtml(c.id)}</code></td><td>${escapeHtml(c.desc || "")}</td></tr>`;
    });
    html += `</tbody></table>`;
  }

  section.innerHTML = html;
  return section;
}

function buildCriteriaTable(prompt, models) {
  const section = document.createElement("div");
  const scores = CURRENT_RUN.scores || [];

  const testScores = models.flatMap(m => scoresForTest(m, prompt.id));
  if (!testScores.length) {
    section.innerHTML = `<h3>Critères × modèles</h3><p class="hint">Pas de scoring pour ce test.</p>`;
    return section;
  }

  const criteria = [...new Set(testScores.map(s => s.critere))];
  const totalPossible = criteria.length * models.length;
  const passCount = testScores.filter(s => s.resultat === "PASS").length;

  const critDescById = {};
  (prompt.criteria || []).forEach(c => { critDescById[c.id] = c.desc; });

  let html = `<h3>Critères × modèles</h3>`;
  html += `<p class="summary">${passCount}/${totalPossible} critères PASS sur ${models.length} modèle(s)</p>`;
  html += `<table class="criteria-table"><thead><tr><th style="width:32%">Critère</th>`;
  models.forEach(m => html += `<th>${escapeHtml(modelAlias(m))}</th>`);
  html += `</tr></thead><tbody>`;

  criteria.forEach(c => {
    const critDesc = critDescById[c] || "";
    const critLabel = critDesc || humanizeCriterionId(c);
    html += `<tr><td>`;
    html += `<div class="crit-main">${escapeHtml(critLabel)}</div>`;
    html += `<code class="crit-id crit-sub">${escapeHtml(c)}</code>`;
    html += `</td>`;
    models.forEach(m => {
      const row = scoresForTest(m, prompt.id).find(s => s.critere === c);
      if (!row) { html += "<td><span class='badge'>—</span></td>"; return; }
      const cls = row.resultat === "PASS" ? "pass" : "fail";
      const detail = row.detail ? `<span class="detail">${escapeHtml(row.detail)}</span>` : "";
      html += `<td><span class="badge ${cls}">${row.resultat}</span>${detail}</td>`;
    });
    html += `</tr>`;
  });

  html += `</tbody></table>`;
  section.innerHTML = html;
  return section;
}

function buildResponsesGrid(prompt, models) {
  const section = document.createElement("div");
  let html = `<h3>Réponses brutes</h3>`;
  html += `<div class="responses-grid">`;

  models.forEach(model => {
    const resp = (CURRENT_RUN.responses || []).find(r => r.model === model && r.test_id === prompt.id);
    const metric = CURRENT_RUN.metrics.find(m => m.model === model && m.test_id === prompt.id);
    const scores = scoresForTest(model, prompt.id);

    let stats = "stats indisponibles";
    let statusBadge = "";
    if (metric) {
      const parts = [
        `${metric.latency_s}s`,
        `in=${metric.tokens_in}`,
        `out=${metric.tokens_out}`,
      ];
      if (metric.reasoning_tokens) {
        const pct = metric.tokens_out ? Math.round((metric.reasoning_tokens / metric.tokens_out) * 100) : 0;
        parts.push(`think=${metric.reasoning_tokens} (${pct}%)`);
      }
      if (metric.retries && Number(metric.retries) > 0) {
        parts.push(`retries=${metric.retries}`);
      }
      parts.push("$" + (metric.cost_usd || 0).toFixed(4));
      stats = parts.join(" · ");
      if (!metric.success) {
        statusBadge = `<span class="badge fail" style="margin-left:.5rem">FAIL</span>`;
      } else if (metric.tokens_out === 0 || metric.tokens_out === "0") {
        statusBadge = `<span class="badge fail" style="margin-left:.5rem">EMPTY</span>`;
      }
    }

    let scoresHtml = "";
    if (scores.length) {
      const passC = scores.filter(s => s.resultat === "PASS").length;
      scoresHtml = `<div class="scores">
        <span class="label">Scoring : ${passC}/${scores.length} PASS</span>
        <ul>` +
        scores.map(s => `<li><span class="badge ${s.resultat === 'PASS' ? 'pass' : 'fail'}">${s.resultat}</span> ${escapeHtml(s.critere)}${s.detail ? ' — <i>' + escapeHtml(s.detail) + '</i>' : ''}</li>`).join("") +
        `</ul></div>`;
    }

    let reasoningHtml = "";
    if (resp && resp.reasoning) {
      reasoningHtml = `<details class="scores"><summary class="label">Reasoning (${resp.reasoning.length} chars)</summary><pre style="margin-top:.5rem">${escapeHtml(resp.reasoning)}</pre></details>`;
    }

    const sizeLabel = modelSizeLabel(model);
    html += `<div class="response-card">
      <h3 style="color:${modelColor(model)}">${escapeHtml(modelAlias(model))}${sizeLabel ? ` <span class="model-size">${escapeHtml(sizeLabel)}</span>` : ""}${statusBadge}</h3>
      <p class="stats">${stats}</p>
      <pre>${resp && resp.response ? escapeHtml(resp.response) : "<i>Pas de réponse</i>"}</pre>
      ${reasoningHtml}
      ${scoresHtml}
    </div>`;
  });

  html += `</div>`;
  section.innerHTML = html;
  return section;
}

function renderTestsCombined() {
  const container = document.getElementById("tests-container");
  container.innerHTML = "";
  const prompts = DATA.prompts || [];
  const models = activeModels();

  if (!prompts.length) {
    container.innerHTML = `<p class="hint">Pas de prompts chargés.</p>`;
    return;
  }

  const openTests = getOpenTests();

  prompts.forEach(prompt => {
    const block = document.createElement("details");
    block.className = "test-block";
    block.dataset.testId = prompt.id;
    if (openTests.has(prompt.id)) block.open = true;

    block.addEventListener("toggle", () => {
      const current = getOpenTests();
      if (block.open) current.add(prompt.id); else current.delete(prompt.id);
      saveOpenTests(current);
    });

    const testScores = (CURRENT_RUN.scores || []).filter(
      s => s.test_id === prompt.id && SELECTED_MODELS.has(s.model)
    );
    const passCount = testScores.filter(s => s.resultat === "PASS").length;
    const totalCount = testScores.length;

    const summary = document.createElement("summary");
    summary.innerHTML = `
      <span class="test-summary-label">${escapeHtml(prompt.label || humanizeCriterionId(prompt.id))}</span>
      <span class="test-summary-id"><code>${escapeHtml(prompt.id)}</code></span>
      <span class="test-summary-score">${passCount}/${totalCount} critères PASS</span>
    `;
    block.appendChild(summary);

    const content = document.createElement("div");
    content.className = "test-content";
    content.appendChild(buildTestDocSection(prompt));
    content.appendChild(buildCriteriaTable(prompt, models));
    content.appendChild(buildResponsesGrid(prompt, models));
    block.appendChild(content);

    container.appendChild(block);
  });
}

load();
