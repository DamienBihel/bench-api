const COLORS = ["#7cc4ff", "#f8b26a", "#b794f6", "#4ade80", "#f87171", "#fbbf24", "#34d399", "#c084fc"];

let DATA = null;
let CURRENT_RUN = null;
let SELECTED_MODELS = new Set();
let CURRENT_TEST = null;
const charts = {};

function getCssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "";
}

/* ---------- theme ---------- */
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("bench-api-theme", theme);
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.textContent = theme === "light" ? "🌙" : "☀️";
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

  const select = document.getElementById("run-select");
  DATA.runs.forEach((r, i) => {
    const opt = document.createElement("option");
    opt.value = i;
    opt.textContent = r.name;
    select.appendChild(opt);
  });
  select.value = DATA.runs.length - 1;
  select.addEventListener("change", () => loadRun(DATA.runs[select.value]));

  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  if (DATA.runs.length) loadRun(DATA.runs[select.value]);
  else document.getElementById("kpis").innerHTML = `<div class="kpi"><div class="label">Aucun run</div><div class="value">—</div><div class="sub-value">Lance d'abord python harness/run.py</div></div>`;
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
  buildTestSelector(run);
  renderAll();
}

function modelMeta(model) { return (DATA.models || {})[model] || {}; }

function modelAlias(model) {
  const meta = modelMeta(model);
  if (meta.alias) return meta.alias;
  // Fallback : utilise alias du metrics
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

function buildModelCheckboxes(models) {
  const cb = document.getElementById("model-checkboxes");
  cb.innerHTML = "<legend>Modèles affichés</legend>";
  models.forEach((m, i) => {
    const id = "cb-" + m.replace(/[^a-z0-9]/gi, "_");
    const alias = modelAlias(m);
    const sizeLabel = modelSizeLabel(m);
    const label = document.createElement("label");
    label.innerHTML = `<input type="checkbox" id="${id}" value="${m}" checked> <span style="color:${COLORS[i % COLORS.length]}">●</span> <strong>${alias}</strong>${sizeLabel ? ` <span class="model-size">(${sizeLabel})</span>` : ""}`;
    label.querySelector("input").addEventListener("change", e => {
      if (e.target.checked) SELECTED_MODELS.add(m); else SELECTED_MODELS.delete(m);
      renderAll();
    });
    cb.appendChild(label);
  });
}

function buildTestSelector(run) {
  const tests = uniqueTests(run);
  const sel = document.getElementById("test-select");
  sel.innerHTML = "";
  tests.forEach(([id, label]) => {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = id + " — " + label;
    sel.appendChild(opt);
  });
  CURRENT_TEST = tests[0]?.[0] || null;
  sel.value = CURRENT_TEST;
  sel.onchange = () => { CURRENT_TEST = sel.value; renderResponses(); };
}

function renderAll() {
  renderKPIs();
  renderCostChart();
  renderLatencyChart();
  renderReasoningChart();
  renderParetoChart();
  renderScoresChart();
  renderScoresByTest();
  renderTestsCatalog();
  renderResponses();
}

function renderTestsCatalog() {
  const container = document.getElementById("tests-catalog");
  container.innerHTML = "";
  const prompts = DATA.prompts || [];

  // Group tests by axe
  const byAxe = {};
  prompts.forEach(p => {
    const axe = p.axe || "autre";
    (byAxe[axe] = byAxe[axe] || []).push(p);
  });

  const axeOrder = ["calibration", "instruction_following", "long_context", "business"];
  const axeLabels = {
    calibration: "Calibration (5 tests)",
    instruction_following: "Instruction following (1 test)",
    long_context: "Long context (1 test)",
    business: "Business (1 test)",
  };

  axeOrder.concat(Object.keys(byAxe).filter(a => !axeOrder.includes(a))).forEach(axe => {
    const tests = byAxe[axe];
    if (!tests || !tests.length) return;

    const axeBlock = document.createElement("div");
    axeBlock.className = "test-block";
    axeBlock.style.marginBottom = "1.5rem";

    let html = `<h3 style="color:var(--accent); font-size:1rem; margin-bottom:1rem;">${axeLabels[axe] || axe}</h3>`;

    tests.forEach(t => {
      const promptText = t.prompt || t.prompt_template || "";
      const promptPreview = promptText.replace("{vault_dump}", "[~50k tokens vault]").replace("{brief}", "[brief client fictif]");
      const criteria = t.criteria || [];

      html += `<details style="margin-bottom:.75rem; background:var(--card); border:1px solid var(--border); border-radius:6px; padding:.75rem 1rem;">`;
      html += `<summary style="cursor:pointer; font-weight:600; color:var(--fg);">${escapeHtml(t.id)} — ${escapeHtml(t.label)} <span class="model-size">(${criteria.length} critères)</span></summary>`;
      html += `<div style="margin-top:.75rem;">`;

      if (t.description) {
        html += `<p style="margin:.5rem 0;"><strong>Objectif :</strong> ${escapeHtml(t.description)}</p>`;
      }

      html += `<div style="margin:.75rem 0;"><strong>Prompt envoyé :</strong>`;
      html += `<pre style="margin-top:.35rem; white-space:pre-wrap; word-wrap:break-word; max-width:100%;">${escapeHtml(promptPreview)}</pre></div>`;

      if (criteria.length) {
        html += `<div style="margin-top:.75rem;"><strong>Critères de scoring (${criteria.length}) :</strong>`;
        html += `<table class="criteria-table" style="margin-top:.35rem;"><thead><tr>`;
        html += `<th style="width:25%;">Id</th><th>Description (condition PASS)</th>`;
        html += `</tr></thead><tbody>`;
        criteria.forEach(c => {
          html += `<tr>`;
          html += `<td><code>${escapeHtml(c.id)}</code></td>`;
          html += `<td>${escapeHtml(c.desc || "")}</td>`;
          html += `</tr>`;
        });
        html += `</tbody></table></div>`;
      }

      html += `</div></details>`;
    });

    axeBlock.innerHTML = html;
    container.appendChild(axeBlock);
  });

  if (!prompts.length) {
    container.innerHTML = `<p class="hint">Pas de prompts charges.</p>`;
  }
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
function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function scoresForTest(model, test_id) {
  return (CURRENT_RUN.scores || []).filter(s => s.model === model && s.test_id === test_id);
}

/* ---------- KPIs ---------- */
function renderKPIs() {
  const container = document.getElementById("kpis");
  container.innerHTML = "";
  const models = activeModels();
  if (!models.length) {
    container.innerHTML = `<div class="kpi"><div class="label">Aucun modèle</div><div class="value">—</div></div>`;
    return;
  }

  const add = (label, value, sub) => {
    const div = document.createElement("div");
    div.className = "kpi";
    div.innerHTML = `<div class="label">${label}</div><div class="value">${value}</div>${sub ? `<div class="sub-value">${sub}</div>` : ""}`;
    container.appendChild(div);
  };

  models.forEach(m => {
    const rows = CURRENT_RUN.metrics.filter(r => r.model === m);
    if (!rows.length) return;
    const totalCost = rows.reduce((s, r) => s + (r.cost_usd || 0), 0);
    const avgLat = rows.reduce((s, r) => s + (r.latency_s || 0), 0) / rows.length;
    const totalReasoning = rows.reduce((s, r) => s + (r.reasoning_tokens || 0), 0);
    const totalOut = rows.reduce((s, r) => s + (r.tokens_out || 0), 0);
    const ratioReasoning = totalOut ? totalReasoning / totalOut : 0;
    // Comptage failures (tokens_out=0 ou success=False)
    const failedCount = rows.filter(r => !r.success || Number(r.tokens_out) === 0).length;
    const retriedCount = rows.filter(r => Number(r.retries || 0) > 0).length;

    const scoreRows = (CURRENT_RUN.scores || []).filter(s => s.model === m);
    let scoreLine = "scoring n/a";
    if (scoreRows.length) {
      const pass = scoreRows.filter(s => s.resultat === "PASS").length;
      const pct = Math.round((pass / scoreRows.length) * 100);
      scoreLine = `${pct}% PASS (${pass}/${scoreRows.length})`;
    }

    const subBits = [
      `$${totalCost.toFixed(4)}`,
      `~${avgLat.toFixed(1)}s/test`,
    ];
    if (totalReasoning) subBits.push(`${totalReasoning.toLocaleString()} think (${Math.round(ratioReasoning * 100)}%)`);
    if (failedCount > 0) subBits.push(`<span style="color:var(--fail)">${failedCount} FAIL</span>`);
    if (retriedCount > 0) subBits.push(`${retriedCount} retried`);
    subBits.push(scoreLine);

    add(modelAlias(m), scoreRows.length
      ? `${Math.round((scoreRows.filter(s => s.resultat === "PASS").length / scoreRows.length) * 100)}%`
      : "—",
      subBits.join(" · "));
  });
}

/* ---------- Charts ---------- */
function makeDataset(field) {
  const models = activeModels();
  const tests = uniqueTests(CURRENT_RUN);
  const labels = tests.map(([id]) => id);
  const datasets = models.map(m => ({
    label: modelAlias(m),
    data: tests.map(([id]) => {
      const row = CURRENT_RUN.metrics.find(r => r.model === m && r.test_id === id);
      return row ? row[field] : null;
    }),
    backgroundColor: modelColor(m),
    borderColor: modelColor(m),
  }));
  return { labels, datasets };
}

function renderBarChart(id, field, yLabel, formatter) {
  const ctx = document.getElementById(id);
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(ctx, {
    type: "bar",
    data: makeDataset(field),
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: getCssVar("--fg") } },
        tooltip: {
          mode: "index",
          intersect: false,
          callbacks: formatter ? { label: c => c.dataset.label + ": " + formatter(c.parsed.y) } : {},
        },
      },
      scales: {
        x: { ticks: { color: getCssVar("--chart-tick") }, grid: { color: getCssVar("--chart-grid") } },
        y: {
          ticks: { color: getCssVar("--chart-tick"), callback: formatter || (v => v) },
          grid: { color: getCssVar("--chart-grid") },
          title: { display: true, text: yLabel, color: getCssVar("--chart-tick") },
        },
      },
    },
  });
}

function renderCostChart() {
  renderBarChart("chart-cost", "cost_usd", "$ par test", v => "$" + Number(v).toFixed(4));
}
function renderLatencyChart() {
  renderBarChart("chart-latency", "latency_s", "secondes", v => Number(v).toFixed(1) + "s");
}
function renderReasoningChart() {
  renderBarChart("chart-reasoning", "reasoning_tokens", "tokens");
}

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
      pointRadius: 8,
      pointHoverRadius: 11,
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

function renderScoresChart() {
  const ctx = document.getElementById("chart-scores");
  if (charts["chart-scores"]) charts["chart-scores"].destroy();
  const models = activeModels();
  const data = models.map(m => {
    const rows = (CURRENT_RUN.scores || []).filter(s => s.model === m);
    if (!rows.length) return 0;
    const pass = rows.filter(s => s.resultat === "PASS").length;
    return Math.round((pass / rows.length) * 100);
  });

  charts["chart-scores"] = new Chart(ctx, {
    type: "bar",
    data: {
      labels: models.map(m => modelAlias(m)),
      datasets: [{
        label: "% PASS",
        data,
        backgroundColor: models.map(m => modelColor(m)),
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => c.parsed.x + "% de criteres PASS" } } },
      scales: {
        x: { min: 0, max: 100, ticks: { color: getCssVar("--chart-tick"), callback: v => v + "%" }, grid: { color: getCssVar("--chart-grid") } },
        y: { ticks: { color: getCssVar("--chart-tick") }, grid: { color: getCssVar("--chart-grid") } },
      },
    },
  });
}

/* ---------- Criteres regroupes par test ---------- */
function renderScoresByTest() {
  const container = document.getElementById("scores-by-test");
  container.innerHTML = "";
  const scores = CURRENT_RUN.scores || [];
  if (!scores.length) {
    container.innerHTML = `<p class="hint">Pas de scoring automatique pour ce run. Lance <code>python harness/score.py &lt;run_name&gt;</code>.</p>`;
    return;
  }

  const models = activeModels();
  const tests = uniqueTests(CURRENT_RUN);

  // Map rapide : test_id -> prompt (pour description + criteria desc)
  const promptById = {};
  (DATA.prompts || []).forEach(p => { promptById[p.id] = p; });

  tests.forEach(([test_id, test_label]) => {
    const testScores = models.flatMap(m => scoresForTest(m, test_id));
    if (!testScores.length) return;

    const block = document.createElement("div");
    block.className = "test-block";

    const criteria = [...new Set(testScores.map(s => s.critere))];
    const totalPossible = criteria.length * models.length;
    const passCount = testScores.filter(s => s.resultat === "PASS").length;

    const prompt = promptById[test_id] || {};
    const description = prompt.description || "";
    // Map critere_id -> description (signification)
    const critDescById = {};
    (prompt.criteria || []).forEach(c => { critDescById[c.id] = c.desc; });

    let html = `<h3>${test_id} — ${test_label}</h3>`;
    if (description) {
      html += `<p class="test-description-inline">${escapeHtml(description)}</p>`;
    }
    html += `<p class="summary">${passCount}/${totalPossible} critères PASS sur ${models.length} modèle(s)</p>`;
    html += `<table class="criteria-table"><thead><tr><th style="width:32%">Critère</th>`;
    models.forEach(m => html += `<th>${modelAlias(m)}</th>`);
    html += `</tr></thead><tbody>`;
    criteria.forEach(c => {
      const critDesc = critDescById[c] || "";
      html += `<tr><td>`;
      html += `<code class="crit-id">${escapeHtml(c)}</code>`;
      if (critDesc) {
        html += `<div class="crit-desc">${escapeHtml(critDesc)}</div>`;
      }
      html += `</td>`;
      models.forEach(m => {
        const row = scoresForTest(m, test_id).find(s => s.critere === c);
        if (!row) { html += "<td><span class='badge'>—</span></td>"; return; }
        const cls = row.resultat === "PASS" ? "pass" : "fail";
        const detail = row.detail ? `<span class="detail">${escapeHtml(row.detail)}</span>` : "";
        html += `<td><span class="badge ${cls}">${row.resultat}</span>${detail}</td>`;
      });
      html += `</tr>`;
    });
    html += `</tbody></table>`;
    block.innerHTML = html;
    container.appendChild(block);
  });
}

/* ---------- Reponses brutes ---------- */
function renderResponses() {
  if (!CURRENT_RUN || !CURRENT_TEST) return;
  const test_id = CURRENT_TEST;
  const prompt = (DATA.prompts || []).find(p => p.id === test_id);

  const desc = document.getElementById("test-description");
  if (prompt) {
    const axe = prompt.axe || "n/a";
    const promptText = prompt.prompt || prompt.prompt_template || "";
    desc.innerHTML = `
      <h3>${prompt.id} — ${prompt.label}</h3>
      <p class="meta"><strong>Axe :</strong> ${escapeHtml(axe)}</p>
      <dl>
        <dt>Prompt envoyé</dt><dd><pre>${escapeHtml(promptText)}</pre></dd>
        ${prompt.rubrique ? `<dt>Méthode d'évaluation</dt><dd><pre>${escapeHtml(prompt.rubrique)}</pre></dd>` : ""}
      </dl>
    `;
  } else {
    desc.innerHTML = `<p class="meta">Pas de descriptif disponible pour ce test.</p>`;
  }

  const grid = document.getElementById("responses-grid");
  grid.innerHTML = "";
  const models = activeModels();
  if (!models.length) {
    grid.innerHTML = `<p class="hint" style="padding:0 2rem">Sélectionne au moins un modèle.</p>`;
    return;
  }

  models.forEach(model => {
    const resp = (CURRENT_RUN.responses || []).find(r => r.model === model && r.test_id === test_id);
    const metric = CURRENT_RUN.metrics.find(m => m.model === model && m.test_id === test_id);
    const scores = scoresForTest(model, test_id);

    const card = document.createElement("div");
    card.className = "response-card";

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
    card.innerHTML = `
      <h3 style="color:${modelColor(model)}">${modelAlias(model)}${sizeLabel ? ` <span class="model-size">${sizeLabel}</span>` : ""}${statusBadge}</h3>
      <p class="stats">${stats}</p>
      <pre>${resp && resp.response ? escapeHtml(resp.response) : "<i>Pas de réponse</i>"}</pre>
      ${reasoningHtml}
      ${scoresHtml}
    `;
    grid.appendChild(card);
  });
}

load();
