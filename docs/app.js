// Justin's University Application Dashboard — client-side renderer
//
// Loads docs/data.json, hydrates every section, and wires up interactions.
// Designed to fail loudly: if data.json can't be fetched (e.g. opened via
// file://), the top-of-page error banner shows a concrete fix.
//
// No dependencies beyond Chart.js (global, loaded via CDN in index.html).

// ════════════════════════════════════════════════════════════════════
// Constants
// ════════════════════════════════════════════════════════════════════

const JUSTIN_MID = 95.5;

// Program identity colors (charts only — deliberately distinct from the
// verdict traffic-light palette so colors never collide in meaning).
const PROGRAM_COLORS = {
  mcmaster_bhsc:         "#1f2937", // slate-800
  queens_bhsc:           "#0f766e", // teal-700
  waterloo_cs:           "#1e3a8a", // blue-900 (navy, not purple)
  uoft_lifesci_stgeorge: "#78350f", // amber-900 (bronze)
};

// Friendly short labels for the two charts' legends
const PROGRAM_SHORT = {
  mcmaster_bhsc:         "McMaster BHSc",
  queens_bhsc:           "Queen's BHSc",
  waterloo_cs:           "Waterloo CS",
  uoft_lifesci_stgeorge: "UofT Life Sci (StG)",
};

const CHECKLIST_COLUMNS = [
  { key: "tier",              label: "Tier"        },
  { key: "program",           label: "Program"     },
  { key: "deadline_ouac",     label: "OUAC"        },
  { key: "deadline_supp",     label: "Supp due"    },
  { key: "supp_app_type",     label: "Supp app"    },
  { key: "casper_required",   label: "CASPer"      },
  { key: "decision_window",   label: "Decisions"   },
  { key: "fee_cad",           label: "Fee"         },
];

// ════════════════════════════════════════════════════════════════════
// Utilities
// ════════════════════════════════════════════════════════════════════

/** Create an element with optional classes and html. */
function el(tag, className, html) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (html !== undefined && html !== null) node.innerHTML = html;
  return node;
}

/** Escape user-controlled strings before inserting via innerHTML. */
function esc(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Format an ISO date like "2027-01-15" → "Jan 15, 2027". */
function fmtDate(iso) {
  if (!iso) return "";
  const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[parseInt(m[2], 10) - 1]} ${parseInt(m[3], 10)}, ${m[1]}`;
}

/** Format a build timestamp like "2026-04-11T16:44:13" → "Apr 11, 2026 · 4:44 PM". */
function fmtTimestamp(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const hh = d.getHours();
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ampm = hh >= 12 ? "PM" : "AM";
  const h12 = ((hh + 11) % 12) + 1;
  return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()} · ${h12}:${mm} ${ampm}`;
}

/** "21.0" → "21st", "22.0" → "22nd", etc. */
function ordinal(n) {
  if (n === null || n === undefined) return "—";
  const r = Math.round(n);
  const s = ["th", "st", "nd", "rd"];
  const v = r % 100;
  return r + (s[(v - 20) % 10] || s[v] || s[0]);
}

/** Label for days_from_today — "in 4 days" / "3 days ago" / "today". */
function daysLabel(days) {
  if (days === null || days === undefined) return "";
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days === -1) return "yesterday";
  if (days > 0) return `in ${days} days`;
  return `${Math.abs(days)} days ago`;
}

/** Stable slug for program keys used as DOM IDs (already safe, but double-check). */
function slug(k) {
  return String(k).replace(/[^a-z0-9_-]/gi, "-").toLowerCase();
}

/** CSS class suffix for a verdict value. */
function verdictClass(v) {
  if (v === "safety")            return "safety";
  if (v === "target")            return "target";
  if (v === "reach")             return "reach";
  if (v === "hard_reach")        return "hardreach";
  return "insufficient";
}

// ════════════════════════════════════════════════════════════════════
// Chart.js custom plugin: Justin marker (dashed vertical line at 95.5)
// ════════════════════════════════════════════════════════════════════
//
// Passed INLINE to the distribution chart only — do NOT Chart.register()
// it globally, or it would also appear on the YoY line chart.

const justinMarkerPlugin = {
  id: "justinMarker",
  afterDatasetsDraw(chart, _args, opts) {
    const value = opts && opts.value;
    if (value === undefined || value === null) return;
    const { ctx, chartArea, scales } = chart;
    if (!chartArea) return;
    const xScale = scales.x;
    if (!xScale) return;

    // Chart.js category-scale positioning: find the pixel for an interpolated
    // value between the bin labels "95" and "96" when value = 95.5. We walk
    // the labels and linearly interpolate.
    const labels = xScale.ticks.map(t => Number(t.label !== undefined ? t.label : t));
    let x;
    const exact = labels.indexOf(Math.round(value));
    if (Math.floor(value) === value && exact >= 0) {
      x = xScale.getPixelForTick(exact);
    } else {
      const lowIdx = labels.indexOf(Math.floor(value));
      const highIdx = labels.indexOf(Math.ceil(value));
      if (lowIdx < 0 || highIdx < 0) return;
      const xLow = xScale.getPixelForTick(lowIdx);
      const xHigh = xScale.getPixelForTick(highIdx);
      const frac = value - Math.floor(value);
      x = xLow + (xHigh - xLow) * frac;
    }

    ctx.save();
    ctx.beginPath();
    ctx.strokeStyle = opts.color || "#0a0a09";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 4]);
    ctx.moveTo(x, chartArea.top);
    ctx.lineTo(x, chartArea.bottom);
    ctx.stroke();

    // Label above the line
    ctx.setLineDash([]);
    ctx.font = '500 12px Geist, system-ui, sans-serif';
    ctx.fillStyle = opts.color || "#0a0a09";
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.fillText(`Justin ${value}%`, x, chartArea.top - 6);
    ctx.restore();
  },
};

// ════════════════════════════════════════════════════════════════════
// Renderers
// ════════════════════════════════════════════════════════════════════

function renderMetaStamp(data) {
  const stamp = document.getElementById("meta-stamp");
  const footerStamp = document.getElementById("footer-refreshed");
  const text = "Built " + fmtTimestamp(data.build_timestamp);
  if (stamp) stamp.textContent = text;
  if (footerStamp) footerStamp.textContent = fmtTimestamp(data.build_timestamp);
}

function renderProfile(profile) {
  const p = profile || {};
  document.getElementById("profile-name").textContent = p.name || "—";

  const appType = p.applicant_type;
  const groupLabel = appType === "105"
    ? "Group B (105) · out-of-province"
    : appType === "101" ? "Group A (101)" : (appType || "—");
  document.getElementById("profile-group").textContent = groupLabel;
}

function renderTop6(profile) {
  const p = profile || {};
  const avg = p.grade_12_projected_top6_average || {};
  document.getElementById("top6-low").textContent  = avg.low        != null ? avg.low.toFixed(1)        : "—";
  document.getElementById("top6-mid").textContent  = avg.midpoint   != null ? avg.midpoint.toFixed(1)   : "—";
  document.getElementById("top6-high").textContent = avg.high       != null ? avg.high.toFixed(1)       : "—";

  const ul = document.getElementById("top6-courses");
  ul.innerHTML = "";
  (p.grade_12_projected_courses || []).forEach(c => {
    const li = el("li", "course-chip",
      `<span class="course-chip__name">${esc(c.course)}</span>
       <span class="course-chip__value">${c.midpoint != null ? c.midpoint : "—"}</span>`
    );
    ul.appendChild(li);
  });
}

function renderVerdictTiles(tier1) {
  const container = document.getElementById("verdict-tiles");
  container.innerHTML = "";
  // Fixed display order: safety → target → reach → hard_reach (nicest sort for the eye)
  const verdictOrder = { safety: 0, target: 1, reach: 2, hard_reach: 3, insufficient_data: 4 };
  const sorted = [...tier1].sort((a, b) => {
    const va = verdictOrder[a.verdict] ?? 9;
    const vb = verdictOrder[b.verdict] ?? 9;
    if (va !== vb) return va - vb;
    return (b.n_accepted || 0) - (a.n_accepted || 0);
  });

  sorted.forEach(p => {
    const id = `program-${slug(p.program_key)}`;
    const tile = el("a", "verdict-tile group");
    tile.href = `#${id}`;
    tile.dataset.programKey = p.program_key;
    tile.setAttribute("aria-label", `${p.university} — ${p.program}: ${p.verdict_label}`);

    const verdictKind = verdictClass(p.verdict);
    const nextDeadline = p.deadline_ouac
      ? `OUAC · ${fmtDate(p.deadline_ouac)}`
      : (p.deadline_supp ? `Supp · ${fmtDate(p.deadline_supp)}` : "");

    tile.innerHTML = `
      <span class="verdict-tile__arrow" aria-hidden="true">→</span>
      <p class="text-[10.5px] tracking-[0.22em] uppercase text-ink-400">Tier 1</p>
      <div>
        <p class="text-[12px] text-ink-500">${esc(p.university)}</p>
        <p class="text-[15.5px] font-medium text-ink-900 leading-snug mt-0.5">${esc(p.program)}</p>
      </div>
      <div class="my-1">
        <span class="badge badge--lg badge--${verdictKind}">${esc(p.verdict_label)}</span>
      </div>
      <div class="text-[12.5px] text-ink-500 tabular-nums">
        ${p.justin_percentile_mid != null ? ordinal(p.justin_percentile_mid) + " percentile" : "—"}
        <span class="mx-1 text-ink-300">·</span>
        n=${p.n_accepted ?? "—"}
      </div>
      <div class="text-[12px] text-ink-500 leading-snug">
        ${p.supp_app_required ? esc(shortenSuppApp(p.supp_app_type)) : "No supplementary app"}
      </div>
      ${nextDeadline ? `<div class="text-[11px] text-ink-400 tabular-nums mt-auto pt-1">${esc(nextDeadline)}</div>` : ""}
    `;

    // Click handler: open the target accordion before the anchor navigates,
    // so the browser scrolls to an already-expanded section.
    tile.addEventListener("click", (e) => {
      const target = document.getElementById(id);
      if (target && target.tagName === "DETAILS") {
        target.open = true;
      }
    });

    container.appendChild(tile);
  });
}

function shortenSuppApp(type) {
  if (!type) return "Supplementary application required";
  // Trim long descriptions for the tile
  if (type.length <= 40) return type;
  return type.split("—")[0].split("(")[0].trim();
}

// ────────────────────────────────────────────────────────────────────
// Accordion (Tier 1 + Tier 2)
// ────────────────────────────────────────────────────────────────────

function renderAccordion(containerId, programs) {
  const host = document.getElementById(containerId);
  host.innerHTML = "";

  // Sort by verdict (safety first) then by n_accepted desc
  const verdictOrder = { safety: 0, target: 1, reach: 2, hard_reach: 3, insufficient_data: 4 };
  const sorted = [...programs].sort((a, b) => {
    const va = verdictOrder[a.verdict] ?? 9;
    const vb = verdictOrder[b.verdict] ?? 9;
    if (va !== vb) return va - vb;
    return (b.n_accepted || 0) - (a.n_accepted || 0);
  });

  sorted.forEach(p => {
    host.appendChild(renderProgramDetails(p));
  });
}

function renderProgramDetails(p) {
  const id = `program-${slug(p.program_key)}`;
  const details = document.createElement("details");
  details.id = id;
  details.className = "program-row";

  const verdictKind = verdictClass(p.verdict);

  // Summary row
  const summary = document.createElement("summary");
  summary.innerHTML = `
    <span class="badge badge--${verdictKind}">${esc(p.verdict_label)}</span>
    <span class="summary-program">
      ${esc(p.program)}
      <small>${esc(p.university)}</small>
    </span>
    <span class="summary-stats">
      ${p.justin_percentile_mid != null ? ordinal(p.justin_percentile_mid) + " pct" : "—"}
      <span class="mx-1 text-ink-300">·</span>
      n=${p.n_accepted ?? "—"}
    </span>
    <span class="chev" aria-hidden="true"></span>
  `;
  details.appendChild(summary);

  // Body
  const body = document.createElement("div");
  body.className = "program-body";

  // Stats row
  const statsRow = document.createElement("dl");
  statsRow.className = "program-stats-row";
  const statCells = [
    ["n accepted",    p.n_accepted],
    ["25th pct avg",  p.p25],
    ["Median avg",    p.p50 != null ? p.p50 : p.median_accepted_avg],
    ["75th pct avg",  p.p75],
    ["Justin pct",    p.justin_percentile_mid != null ? ordinal(p.justin_percentile_mid) : null],
  ];
  statCells.forEach(([label, value]) => {
    const cell = el("div");
    cell.innerHTML = `<dt>${esc(label)}</dt><dd>${value != null ? esc(String(value)) : "—"}</dd>`;
    statsRow.appendChild(cell);
  });
  body.appendChild(statsRow);

  // OOP caveat (only if adverse) — stays full-width above the 2-col grid
  if (p.oop_caveat) {
    body.appendChild(el("div", "oop-warning",
      `<strong>OOP yellow flag</strong>${esc(p.oop_caveat)}`));
  }

  // Two-column grid: reasoning + ec-fit on the left, requirements sidebar on the right
  const cols = el("div", "program-body-cols");
  const main = el("div", "program-body-cols__main");
  const aside = el("div", "program-body-cols__aside");

  // Main column: long-form reasoning + EC fit
  if (p.reasoning) {
    main.appendChild(el("p", "program-reasoning", esc(p.reasoning)));
  }
  if (p.ec_strength_text) {
    main.appendChild(el("div", "ec-fit",
      `<strong>EC fit</strong>${esc(p.ec_strength_text)}`));
  }

  // Aside column: requirements meta (deadlines, fee, link, etc.)
  const meta = document.createElement("dl");
  meta.className = "program-meta";

  function metaCell(label, value) {
    if (value === null || value === undefined || value === "") return;
    const cell = el("div");
    cell.innerHTML = `<dt>${esc(label)}</dt><dd>${value}</dd>`;
    meta.appendChild(cell);
  }

  metaCell("OUAC deadline",   p.deadline_ouac ? esc(fmtDate(p.deadline_ouac)) : null);
  metaCell("Supp deadline",   p.deadline_supp ? esc(fmtDate(p.deadline_supp)) : null);
  metaCell("Document deadline", p.deadline_doc ? esc(fmtDate(p.deadline_doc)) : null);
  metaCell("Decision window", p.decision_window ? esc(p.decision_window) : null);
  metaCell("Supplementary", p.supp_app_required == null ? null :
    (p.supp_app_required ? esc(p.supp_app_type || "Required") : "None"));
  metaCell("CASPer", p.casper_required === true ? "Required" :
    (p.casper_required === false ? "Not required" : null));
  metaCell("Fee (CAD)", p.fee_cad != null ? `$${p.fee_cad}` : null);
  metaCell("Requirements confidence", p.requirements_confidence ? esc(p.requirements_confidence) : null);
  metaCell("Source", p.official_url ?
    `<a href="${esc(p.official_url)}" target="_blank" rel="noopener">Official page ↗</a>` : null);

  aside.appendChild(meta);
  cols.appendChild(main);
  cols.appendChild(aside);
  body.appendChild(cols);

  details.appendChild(body);
  return details;
}

// ────────────────────────────────────────────────────────────────────
// Action items
// ────────────────────────────────────────────────────────────────────

function renderActionItems(items) {
  const ol = document.getElementById("action-list");
  ol.innerHTML = "";

  // Filter: keep future items, items within 3 days of the past, and
  // pending (date:null) items. Drop everything else.
  const visible = (items || []).filter(item => {
    if (!item.date) return true; // pending (e.g. HYRS spring 2026)
    if (item.days_from_today == null) return true;
    return item.days_from_today >= -3;
  });

  if (!visible.length) {
    ol.appendChild(el("li", "text-sm text-ink-500", "No upcoming action items."));
    return;
  }

  visible.forEach(item => {
    const li = document.createElement("li");
    li.className = "action-item " + urgencyClass(item);

    const dateCell = el("div");
    if (item.date) {
      dateCell.innerHTML = `
        <div class="action-item__date">${esc(fmtDate(item.date))}</div>
        <div class="action-item__when">${esc(daysLabel(item.days_from_today))}</div>
      `;
    } else {
      dateCell.innerHTML = `
        <div class="action-item__date">${esc(item.date_label || "TBD")}</div>
        <div class="action-item__when">pending</div>
      `;
    }

    const labelCell = el("div", "action-item__label", esc(item.label));
    const priorityCell = el("div", "action-item__priority", esc(item.priority || "info"));

    li.appendChild(dateCell);
    li.appendChild(labelCell);
    li.appendChild(priorityCell);
    ol.appendChild(li);
  });
}

function urgencyClass(item) {
  if (!item.date) return "action-item--pending";
  const d = item.days_from_today;
  if (d == null) return "action-item--pending";
  if (d <= 30) return "action-item--urgent";
  if (d <= 180) return "action-item--upcoming";
  return "action-item--far";
}

// ────────────────────────────────────────────────────────────────────
// Distribution chart
// ────────────────────────────────────────────────────────────────────

function renderDistributionChart(tier1) {
  const canvas = document.getElementById("dist-chart-canvas");
  if (!canvas || !window.Chart) return;

  // Bin range: 80 to 100 (21 labels)
  const binRange = [];
  for (let b = 80; b <= 100; b++) binRange.push(b);

  const datasets = tier1.map(p => {
    const byBin = new Map((p.histogram_bins || []).map(h => [h.bin, h.n]));
    return {
      label: PROGRAM_SHORT[p.program_key] || p.program,
      data: binRange.map(b => byBin.get(b) || 0),
      backgroundColor: hexToRgba(PROGRAM_COLORS[p.program_key] || "#5c5c58", 0.78),
      borderColor: PROGRAM_COLORS[p.program_key] || "#5c5c58",
      borderWidth: 0,
      borderRadius: 2,
      barPercentage: 0.92,
      categoryPercentage: 0.78,
    };
  });

  // eslint-disable-next-line no-new
  new window.Chart(canvas, {
    type: "bar",
    data: {
      labels: binRange.map(String),
      datasets,
    },
    plugins: [justinMarkerPlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      layout: { padding: { top: 24 } }, // room for the "Justin 95.5%" label
      plugins: {
        legend: {
          position: "top",
          align: "start",
          labels: {
            font: { family: "Geist, sans-serif", size: 12 },
            color: "#3f3f3c",
            usePointStyle: true,
            pointStyle: "rectRounded",
            padding: 16,
            boxWidth: 10,
            boxHeight: 10,
          },
        },
        tooltip: {
          backgroundColor: "#0a0a09",
          titleFont: { family: "Geist, sans-serif", size: 12, weight: "600" },
          bodyFont: { family: "Geist, sans-serif", size: 12 },
          padding: 10,
          cornerRadius: 4,
          displayColors: true,
          boxPadding: 4,
          callbacks: {
            title: (items) => {
              if (!items.length) return "";
              const bin = items[0].label;
              return `Accepted average ${bin}–${Number(bin) + 1}`;
            },
            label: (ctx) => ` ${ctx.dataset.label}: n=${ctx.parsed.y}`,
          },
        },
        justinMarker: {
          value: JUSTIN_MID,
          color: "#0a0a09",
        },
      },
      scales: {
        x: {
          stacked: false,
          grid: { display: false, drawBorder: false },
          ticks: {
            font: { family: "Geist, sans-serif", size: 11 },
            color: "#8a8a86",
            maxRotation: 0,
            callback: function (val, idx) {
              // Show every other tick to reduce clutter on narrow screens
              const label = this.getLabelForValue(val);
              if (idx === 0 || idx === binRange.length - 1) return label;
              return Number(label) % 2 === 0 ? label : "";
            },
          },
          title: {
            display: true,
            text: "Accepted-average %",
            font: { family: "Geist, sans-serif", size: 11, weight: "500" },
            color: "#5c5c58",
            padding: { top: 12 },
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: "#ededeb", drawBorder: false, lineWidth: 1 },
          ticks: {
            font: { family: "Geist, sans-serif", size: 11 },
            color: "#8a8a86",
            precision: 0,
          },
          title: {
            display: true,
            text: "Number of accepted reports",
            font: { family: "Geist, sans-serif", size: 11, weight: "500" },
            color: "#5c5c58",
          },
        },
      },
    },
  });
}

function hexToRgba(hex, alpha) {
  const m = hex.replace("#", "").match(/.{1,2}/g);
  if (!m || m.length !== 3) return hex;
  const [r, g, b] = m.map(h => parseInt(h, 16));
  return `rgba(${r},${g},${b},${alpha})`;
}

// ────────────────────────────────────────────────────────────────────
// YoY trend chart
// ────────────────────────────────────────────────────────────────────

function renderYoyChart(yoy) {
  const canvas = document.getElementById("yoy-chart-canvas");
  if (!canvas || !window.Chart) return;

  // Build label set from all cycles present (stable order)
  const cycleSet = new Set();
  (yoy || []).forEach(p => (p.cycles || []).forEach(c => cycleSet.add(c.cycle)));
  const labels = Array.from(cycleSet).sort();

  const datasets = (yoy || []).map(p => {
    const byCycle = new Map((p.cycles || []).map(c => [c.cycle, c]));
    const color = PROGRAM_COLORS[p.program_key] || "#5c5c58";
    return {
      label: PROGRAM_SHORT[p.program_key] || p.program,
      data: labels.map(lab => {
        const c = byCycle.get(lab);
        return c ? c.mean : null;
      }),
      borderColor: color,
      backgroundColor: color,
      pointBackgroundColor: color,
      pointBorderColor: "#fff",
      pointBorderWidth: 1.5,
      pointRadius: 5,
      pointHoverRadius: 7,
      borderWidth: 2,
      tension: 0, // straight segments — the data is 4 discrete points
      spanGaps: true,
    };
  });

  // eslint-disable-next-line no-new
  new window.Chart(canvas, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "top",
          align: "start",
          labels: {
            font: { family: "Geist, sans-serif", size: 12 },
            color: "#3f3f3c",
            usePointStyle: true,
            pointStyle: "line",
            padding: 16,
            boxWidth: 20,
          },
        },
        tooltip: {
          backgroundColor: "#0a0a09",
          titleFont: { family: "Geist, sans-serif", size: 12, weight: "600" },
          bodyFont: { family: "Geist, sans-serif", size: 12 },
          padding: 10,
          cornerRadius: 4,
          callbacks: {
            title: (items) => items[0]?.label || "",
            label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%`,
          },
        },
      },
      scales: {
        x: {
          grid: { display: false, drawBorder: false },
          ticks: {
            font: { family: "Geist, sans-serif", size: 11 },
            color: "#8a8a86",
          },
        },
        y: {
          suggestedMin: 88,
          suggestedMax: 100,
          grid: { color: "#ededeb", drawBorder: false, lineWidth: 1 },
          ticks: {
            font: { family: "Geist, sans-serif", size: 11 },
            color: "#8a8a86",
            callback: (v) => `${v}%`,
          },
          title: {
            display: true,
            text: "Mean accepted average",
            font: { family: "Geist, sans-serif", size: 11, weight: "500" },
            color: "#5c5c58",
          },
        },
      },
    },
  });
}

// ────────────────────────────────────────────────────────────────────
// Checklist (sortable table + mobile cards)
// ────────────────────────────────────────────────────────────────────

function renderChecklist(data) {
  const rows = [...(data.tier1 || []), ...(data.tier2 || [])]
    .filter(p => p.deadline_ouac); // only programs with real deadlines

  const state = { sortKey: "deadline_ouac", sortDir: "asc" };

  // Wire up table header clicks once
  const table = document.getElementById("checklist-table");
  if (table && !table.dataset.wired) {
    table.dataset.wired = "true";
    table.querySelectorAll("th.sortable").forEach(th => {
      th.setAttribute("role", "button");
      th.setAttribute("tabindex", "0");
      th.addEventListener("click", () => {
        const key = th.dataset.sortKey;
        if (state.sortKey === key) {
          state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        } else {
          state.sortKey = key;
          state.sortDir = "asc";
        }
        updateSortIndicators(state);
        renderChecklistRows(sortRows(rows, state));
        renderChecklistCards(sortRows(rows, state));
      });
      th.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          th.click();
        }
      });
    });
  }

  updateSortIndicators(state);
  renderChecklistRows(sortRows(rows, state));
  renderChecklistCards(sortRows(rows, state));
}

function sortRows(rows, state) {
  const { sortKey, sortDir } = state;
  const dir = sortDir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = a[sortKey];
    const vb = b[sortKey];
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
    return String(va).localeCompare(String(vb)) * dir;
  });
}

function updateSortIndicators(state) {
  document.querySelectorAll("#checklist-table th.sortable").forEach(th => {
    if (th.dataset.sortKey === state.sortKey) {
      th.setAttribute("aria-sort", state.sortDir === "asc" ? "ascending" : "descending");
    } else {
      th.removeAttribute("aria-sort");
    }
  });
}

function renderChecklistRows(rows) {
  const tbody = document.getElementById("checklist-tbody");
  tbody.innerHTML = "";
  rows.forEach(p => {
    const tr = document.createElement("tr");
    tr.className = "row-tier-" + (p.tier || 0);

    const casperCell = p.casper_required === true ? "Required"
                     : p.casper_required === false ? "—" : "?";

    const suppShort = p.supp_app_required
      ? esc(shortenSuppApp(p.supp_app_type || "Required"))
      : `<span class="text-ink-400">None</span>`;

    tr.innerHTML = `
      <td class="tier-label">${p.tier ? "T" + p.tier : ""}</td>
      <td>
        <div class="text-ink-900 font-medium">${esc(p.program)}</div>
        <div class="text-[11.5px] text-ink-500">${esc(p.university)}</div>
      </td>
      <td class="num tabular-nums">${p.deadline_ouac ? esc(fmtDate(p.deadline_ouac)) : "—"}</td>
      <td class="num tabular-nums">${p.deadline_supp ? esc(fmtDate(p.deadline_supp)) : "—"}</td>
      <td>${suppShort}</td>
      <td>${esc(casperCell)}</td>
      <td>${esc(p.decision_window || "—")}</td>
      <td class="num tabular-nums">${p.fee_cad != null ? "$" + p.fee_cad : "—"}</td>
      <td>${p.official_url ? `<a class="program-link" href="${esc(p.official_url)}" target="_blank" rel="noopener">Page ↗</a>` : ""}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderChecklistCards(rows) {
  const host = document.getElementById("checklist-cards");
  host.innerHTML = "";
  rows.forEach(p => {
    const card = el("article", "checklist-card");
    const casperCell = p.casper_required === true ? "Required"
                     : p.casper_required === false ? "None" : "?";
    card.innerHTML = `
      <h4>
        T${p.tier} · ${esc(p.program)}
        <small>${esc(p.university)}</small>
      </h4>
      <dl>
        <dt>OUAC</dt>            <dd>${p.deadline_ouac ? esc(fmtDate(p.deadline_ouac)) : "—"}</dd>
        <dt>Supp due</dt>        <dd>${p.deadline_supp ? esc(fmtDate(p.deadline_supp)) : "—"}</dd>
        <dt>Supp app</dt>        <dd>${p.supp_app_required ? esc(shortenSuppApp(p.supp_app_type || "Required")) : "None"}</dd>
        <dt>CASPer</dt>          <dd>${esc(casperCell)}</dd>
        <dt>Decisions</dt>       <dd>${esc(p.decision_window || "—")}</dd>
        <dt>Fee</dt>             <dd>${p.fee_cad != null ? "$" + p.fee_cad : "—"}</dd>
        ${p.official_url ? `<dt>Official</dt><dd><a class="program-link" href="${esc(p.official_url)}" target="_blank" rel="noopener">Page ↗</a></dd>` : ""}
      </dl>
    `;
    host.appendChild(card);
  });
}

// ────────────────────────────────────────────────────────────────────
// Tier 3/4 note
// ────────────────────────────────────────────────────────────────────

function renderTier34Note(tier3, tier4) {
  const host = document.getElementById("tier34-note");
  const t3Useful = (tier3 || []).filter(p => p.verdict !== "insufficient_data");
  const t4Any = (tier4 || []).length;

  const t3Summary = t3Useful.length
    ? t3Useful.map(p => `${esc(p.program)} (${esc(p.verdict_label || p.verdict)})`).join(", ")
    : "all insufficient sample";

  host.innerHTML = `
    <p><strong>Other programs in the analysis (no detail shown above):</strong></p>
    <p>
      <strong>Tier 3 — Waterloo backups</strong> (${(tier3 || []).length} programs):
      ${t3Summary}. Remaining Waterloo variants have too few Reddit reports to produce a reliable verdict.
    </p>
    <p>
      <strong>Tier 4 — UAlberta in-province options</strong> (${t4Any} programs):
      all have insufficient Reddit sample size to compute a per-program verdict. Justin's 95.5% projected top-6 clears the
      published thresholds for every UAlberta BSc program comfortably — lean on the official admissions pages for UAlberta details.
    </p>
  `;
}

// ────────────────────────────────────────────────────────────────────
// Data quality section
// ────────────────────────────────────────────────────────────────────

function renderDataQuality(dq) {
  if (!dq) return;

  // Cycles table
  const cyclesHost = document.getElementById("dq-cycles");
  const table = el("table");
  const thead = el("thead");
  thead.innerHTML = `
    <tr>
      <th>Cycle</th>
      <th>Region</th>
      <th>Rows</th>
      <th>Decisions</th>
      <th>Universities</th>
      <th>Programs</th>
      <th>Live</th>
      <th>Fetched</th>
    </tr>
  `;
  table.appendChild(thead);
  const tbody = el("tbody");
  (dq.cycles || []).forEach(c => {
    const tr = el("tr");
    tr.innerHTML = `
      <td>${esc(c.cycle)}</td>
      <td>${esc(c.region || "—")}</td>
      <td>${c.n_rows ?? "—"}</td>
      <td>${c.n_decisions_mapped ?? "—"}</td>
      <td>${c.n_universities_mapped ?? "—"}</td>
      <td>${c.n_programs_mapped ?? "—"}</td>
      <td>${c.live ? "yes" : "no"}</td>
      <td>${esc((c.fetched_at || "").slice(0, 10))}</td>
    `;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  cyclesHost.innerHTML = "";
  cyclesHost.appendChild(table);

  // Caveats
  const ol = document.getElementById("dq-caveats");
  ol.innerHTML = "";
  (dq.caveats || []).forEach(c => {
    const li = el("li");
    li.innerHTML = `<strong>${esc(c.label)}</strong>${esc(c.body)}`;
    ol.appendChild(li);
  });
}

// ────────────────────────────────────────────────────────────────────
// Anchor-scroll handler: auto-open any <details> whose id matches the hash
// ────────────────────────────────────────────────────────────────────

function wireAnchorAutoOpen() {
  const openFromHash = () => {
    if (!location.hash) return;
    const target = document.getElementById(location.hash.slice(1));
    if (target && target.tagName === "DETAILS") {
      target.open = true;
      // Re-scroll after opening (in case scroll landed on collapsed element)
      requestAnimationFrame(() => target.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  };
  window.addEventListener("hashchange", openFromHash);
  openFromHash();
}

// ────────────────────────────────────────────────────────────────────
// Sticky nav active-link highlight (IntersectionObserver)
// ────────────────────────────────────────────────────────────────────
//
// As the user scrolls, highlight the nav link whose target section is
// currently in the top portion of the viewport. Uses a rootMargin offset
// so the "active" section is the one the user is actually reading, not
// the one that just happens to have a pixel visible at the bottom.

function wireNavActiveState() {
  const links = document.querySelectorAll('.topnav__links a[data-nav-target]');
  if (!links.length || !('IntersectionObserver' in window)) return;

  // Build section -> link map
  const sectionToLink = new Map();
  links.forEach(link => {
    const targetId = link.dataset.navTarget;
    const section = document.getElementById(targetId);
    if (section) sectionToLink.set(section, link);
  });
  if (!sectionToLink.size) return;

  // Track which sections are currently intersecting; highlight the first
  // one in document order (the topmost visible section).
  const visible = new Set();

  const applyHighlight = () => {
    // Find the first section (in document order) that is visible
    const sectionsInOrder = Array.from(sectionToLink.keys()).sort(
      (a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top
    );
    const active = sectionsInOrder.find(s => visible.has(s)) || sectionsInOrder[0];
    links.forEach(l => l.removeAttribute('aria-current'));
    const activeLink = sectionToLink.get(active);
    if (activeLink) activeLink.setAttribute('aria-current', 'location');
  };

  const observer = new IntersectionObserver(
    entries => {
      entries.forEach(e => {
        if (e.isIntersecting) visible.add(e.target);
        else visible.delete(e.target);
      });
      applyHighlight();
    },
    {
      // Top of section must enter the upper ~40% of the viewport to count as "active"
      rootMargin: '-84px 0px -55% 0px',
      threshold: 0,
    }
  );

  sectionToLink.forEach((_link, section) => observer.observe(section));

  // Initial highlight (in case the page loaded scrolled somewhere)
  requestAnimationFrame(applyHighlight);
}

// ════════════════════════════════════════════════════════════════════
// Dark mode toggle (persists to localStorage, respects system pref)
// ════════════════════════════════════════════════════════════════════

function wireThemeToggle() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;

  // Resolve initial theme: localStorage > system preference > light
  const stored = localStorage.getItem("theme");
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const initial = stored || (prefersDark ? "dark" : "light");
  applyTheme(initial);

  btn.addEventListener("click", () => {
    const current = document.documentElement.classList.contains("dark") ? "dark" : "light";
    const next = current === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem("theme", next);
  });

  // Listen for system preference changes (only if user hasn't manually set)
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
    if (!localStorage.getItem("theme")) {
      applyTheme(e.matches ? "dark" : "light");
    }
  });
}

function applyTheme(theme) {
  if (theme === "dark") {
    document.documentElement.classList.add("dark");
  } else {
    document.documentElement.classList.remove("dark");
  }
}

// ════════════════════════════════════════════════════════════════════
// Error path
// ════════════════════════════════════════════════════════════════════

function showError(err) {
  const banner = document.getElementById("error-banner");
  const detail = document.getElementById("error-banner-detail");
  if (!banner) return;
  banner.classList.remove("hidden");
  if (detail) detail.textContent = String(err && err.message ? err.message : err);
  console.error("Dashboard load failed:", err);
}

// ════════════════════════════════════════════════════════════════════
// Bootstrap
// ════════════════════════════════════════════════════════════════════

async function main() {
  try {
    if (!window.Chart) {
      throw new Error("Chart.js did not load (check network / CDN).");
    }

    const response = await fetch("./data.json", { cache: "no-cache" });
    if (!response.ok) {
      throw new Error(`data.json: HTTP ${response.status}`);
    }
    const data = await response.json();

    wireThemeToggle();

    renderMetaStamp(data);
    renderProfile(data.profile);
    renderTop6(data.profile);
    renderVerdictTiles(data.tier1 || []);
    renderActionItems(data.action_items || []);
    renderDistributionChart(data.tier1 || []);
    renderYoyChart(data.yoy_trends || []);
    renderAccordion("tier1-accordion", data.tier1 || []);
    renderAccordion("tier2-accordion", data.tier2 || []);
    renderTier34Note(data.tier3 || [], data.tier4 || []);
    renderChecklist(data);
    renderDataQuality(data.data_quality);
    wireAnchorAutoOpen();
    wireNavActiveState();
  } catch (err) {
    showError(err);
  }
}

main();
