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
// Reasoning text formatter
// ════════════════════════════════════════════════════════════════════
//
// The reasoning text from analyze_program.py follows a predictable structure:
//   1. GPA placement ("Justin's projected top-6 midpoint...")
//   2. OOP signal (optional — "OOP DIRECTIONAL..." or "Out-of-province...")
//   3. EC leverage ("Supp-app leverage..." / "AIF leverage..." / "This program does not...")
//   4. EC adjustment (optional — "EC adjustment applied:...")
//   5. Final verdict ("FINAL VERDICT:...")
//   6. Caveat ("Caveat:...")
//
// We split on known sentence-starting phrases, label each section, and
// apply inline formatting (bold verdicts, italic signals, bullet-pointed
// credential lists).

function formatReasoning(text) {
  if (!text) return "";

  // Split text into sentences at ". " followed by a capital letter or known marker
  const sentences = text.split(/(?<=\.) (?=[A-Z])/);

  // Group sentences into labeled sections
  const sections = [];
  let currentLabel = "GPA Placement";
  let currentType = "default";
  let buffer = [];

  for (const s of sentences) {
    let newLabel = null;
    let newType = "default";

    if (/^OOP DIRECTIONAL|^Out-of-province|^OOP subset/i.test(s)) {
      newLabel = "Out-of-Province Signal";
      newType = "warning";
    } else if (/^Supp-app leverage/i.test(s)) {
      newLabel = "Supplementary App Leverage";
      newType = "highlight";
    } else if (/^AIF leverage/i.test(s)) {
      newLabel = "AIF Leverage";
      newType = "highlight";
    } else if (/^This program does not use/i.test(s)) {
      newLabel = "Supplementary Application";
      newType = "default";
    } else if (/^EC adjustment applied/i.test(s)) {
      newLabel = "EC Adjustment";
      newType = "accent";
    } else if (/^AIF content will be/i.test(s)) {
      newLabel = "AIF Assessment";
      newType = "default";
    } else if (/^FINAL VERDICT/i.test(s)) {
      newLabel = "Final Verdict";
      newType = "verdict";
    } else if (/^Caveat:/i.test(s)) {
      newLabel = "Data Caveat";
      newType = "muted";
    }

    if (newLabel && newLabel !== currentLabel) {
      if (buffer.length) {
        sections.push({ label: currentLabel, type: currentType, text: buffer.join(" ") });
      }
      currentLabel = newLabel;
      currentType = newType;
      buffer = [s];
    } else {
      buffer.push(s);
    }
  }
  if (buffer.length) {
    sections.push({ label: currentLabel, type: currentType, text: buffer.join(" ") });
  }

  // Render each section as a structured block
  return sections
    .map((sec) => {
      const typeClass = `reasoning-section--${sec.type}`;
      const body = highlightReasoning(esc(sec.text));
      return `<div class="reasoning-section ${typeClass}">
        <div class="reasoning-section__label">${esc(sec.label)}</div>
        <div class="reasoning-section__body">${body}</div>
      </div>`;
    })
    .join("");
}

/** Apply inline formatting to reasoning text:
 *  - Bold verdict labels (REACH, TARGET, SAFETY, HARD REACH)
 *  - Italic signal keywords (VERY STRONG, YELLOW FLAG, DIRECTIONAL SIGNAL)
 *  - Monospace-styled percentages and sample sizes
 *  - Convert "+" separated credential lists into bullet points
 */
function highlightReasoning(text) {
  let out = text;

  // Bold verdict labels
  out = out.replace(
    /\b(REACH|TARGET|SAFETY|HARD REACH|FINAL VERDICT:\s*(?:REACH|TARGET|SAFETY|HARD REACH))\b/g,
    "<strong>$1</strong>"
  );

  // Italic signal phrases
  out = out.replace(
    /\b(VERY STRONG|YELLOW FLAG|DIRECTIONAL SIGNAL|NOT APPLICABLE)\b/g,
    "<em class='reasoning-signal'>$1</em>"
  );

  // Highlight percentages and sample sizes
  out = out.replace(
    /(\d+\.?\d*(?:th|st|nd|rd)?\s*(?:percentile|pct))/g,
    "<span class='reasoning-stat'>$1</span>"
  );
  out = out.replace(
    /\b(n=\d+)\b/g,
    "<span class='reasoning-stat'>$1</span>"
  );
  out = out.replace(
    /(\d+\.?\d*%)/g,
    "<span class='reasoning-num'>$1</span>"
  );

  // Convert "+" separated credential lists into bullet points.
  // Pattern: "...plus rare X + Y + Z + W." or "...plus X + Y + Z."
  // Look for "plus " followed by items separated by " + "
  out = out.replace(
    /\bplus\s+((?:[^+.]+\+\s*){2,}[^+.]+)(?=\.)/gi,
    (match, listPart) => {
      const items = listPart
        .split(/\s*\+\s*/)
        .map((item) => item.trim())
        .filter(Boolean);
      if (items.length < 3) return match; // not a real list
      const bullets = items.map((i) => `<li>${i}</li>`).join("");
      return `plus:<ul class="reasoning-credentials">${bullets}</ul>`;
    }
  );

  return out;
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
  // Explicit display order for the 3 Tier-1 hero tiles:
  // McMaster BHSc → Queen's BHSc → Waterloo CS
  const tileOrder = {
    mcmaster_bhsc: 0,
    queens_bhsc: 1,
    waterloo_cs: 2,
  };
  const sorted = [...tier1].sort((a, b) => {
    const oa = tileOrder[a.program_key] ?? 99;
    const ob = tileOrder[b.program_key] ?? 99;
    return oa - ob;
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
// Per-program cards (consolidated: GPA + EC + Verdict + Requirements)
// ────────────────────────────────────────────────────────────────────

// Display order for Tier 1 and Tier 2
const TIER1_ORDER = { mcmaster_bhsc: 0, queens_bhsc: 1, waterloo_cs: 2 };
const TIER2_ORDER = {
  western_bmsc: 0, uoft_lifesci_stgeorge: 1, mcmaster_lifesci: 2,
  queens_lifesci: 3, guelph_biomed: 4, ualberta_bsc_physiol: 5,
  waterloo_math_cs: 6, waterloo_se: 7,
};

function renderProgramCards(data) {
  const ecInsights = data.ec_insights || {};
  const timelineMap = {};
  (data.decision_timeline || []).forEach(t => { timelineMap[t.program_key] = t.months; });

  // Tier 1
  const tier1Host = document.getElementById("tier1-programs");
  if (tier1Host) {
    tier1Host.innerHTML = "";
    const sorted1 = [...(data.tier1 || [])].sort((a, b) =>
      (TIER1_ORDER[a.program_key] ?? 99) - (TIER1_ORDER[b.program_key] ?? 99));
    sorted1.forEach((p, i) => {
      tier1Host.appendChild(buildProgramCard(p, ecInsights[p.program_key], timelineMap[p.program_key], i === 0));
    });
  }

  // Tier 2
  const tier2Host = document.getElementById("tier2-programs");
  if (tier2Host) {
    tier2Host.innerHTML = "";
    const sorted2 = [...(data.tier2 || [])].sort((a, b) =>
      (TIER2_ORDER[a.program_key] ?? 99) - (TIER2_ORDER[b.program_key] ?? 99));
    sorted2.forEach(p => {
      tier2Host.appendChild(buildProgramCard(p, ecInsights[p.program_key], timelineMap[p.program_key], false));
    });
  }
}

function buildProgramCard(p, ecInsight, timelineMonths, openByDefault) {
  const id = `program-${slug(p.program_key)}`;
  const details = document.createElement("details");
  details.id = id;
  details.className = "program-row";
  if (openByDefault) details.open = true;

  const vk = verdictClass(p.verdict);

  // Summary row
  const summary = document.createElement("summary");
  summary.innerHTML = `
    <span class="badge badge--${vk}">${esc(p.verdict_label)}</span>
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

  const body = el("div", "program-body");

  // ── Sub-section 1: GPA Analysis ──
  body.appendChild(el("div", "program-subsection-label", "1. GPA Analysis"));
  const statsRow = document.createElement("dl");
  statsRow.className = "program-stats-row";
  [["n accepted", p.n_accepted], ["25th pct", p.p25],
   ["Median", p.p50 ?? p.median_accepted_avg], ["75th pct", p.p75],
   ["Justin pct", p.justin_percentile_mid != null ? ordinal(p.justin_percentile_mid) : null]
  ].forEach(([label, value]) => {
    const c = el("div");
    c.innerHTML = `<dt>${esc(label)}</dt><dd>${value != null ? esc(String(value)) : "—"}</dd>`;
    statsRow.appendChild(c);
  });
  body.appendChild(statsRow);
  if (p.oop_caveat) {
    body.appendChild(el("div", "oop-warning", `<strong>OOP yellow flag</strong>${esc(p.oop_caveat)}`));
  }

  // ── Sub-section 2: EC Analysis (Tier 1 with supp apps only) ──
  if (ecInsight && ecInsight.category_frequencies && Object.keys(ecInsight.category_frequencies).length > 0) {
    body.appendChild(el("div", "program-subsection-label mt-6", "2. EC Analysis"));
    const ecDiv = el("div", "mt-2 mb-4");

    // Alignment badge
    const align = ecInsight.justin_alignment || {};
    const cats = Object.keys(ecInsight.category_frequencies);
    const vals = Object.values(ecInsight.category_frequencies);
    const maxVal = Math.max(...vals, 1);

    ecDiv.innerHTML = `
      <div class="flex items-center gap-3 mb-4">
        <span class="inline-flex items-center px-2.5 py-1 text-[11px] font-medium rounded-full border
          ${(align.match_rate_pct || 0) >= 75 ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-amber-50 border-amber-200 text-amber-700'}">
          Justin matches ${(align.matched || []).length}/${cats.length} categories
        </span>
        <span class="text-[12px] text-ink-400">${ecInsight.n_with_ec_data} of ${ecInsight.n_accepted_total} accepted reports have EC data</span>
      </div>
    `;

    // EC bars
    const barsDiv = el("div", "space-y-1.5");
    const barColor = EC_BAR_COLORS[p.program_key] || "#1f2937";
    cats.forEach((cat, i) => {
      const count = vals[i];
      const pct = (count / maxVal) * 100;
      const isMatch = (align.matched || []).includes(cat);
      const row = el("div", "flex items-center gap-3 text-[12px]");
      row.innerHTML = `
        <span class="w-[150px] sm:w-[180px] shrink-0 text-right text-ink-500 truncate">${esc(cat)}</span>
        <div class="flex-1 h-5 bg-ink-50 rounded overflow-hidden relative">
          <div class="h-full rounded" style="width:${pct}%;background:${barColor};opacity:${isMatch ? '0.8' : '0.3'}"></div>
          <span class="absolute inset-y-0 left-2 flex items-center text-[10px] font-medium ${pct > 25 ? 'text-white' : 'text-ink-600'}">${count}</span>
        </div>
        <span class="w-4 shrink-0 text-center text-[12px] ${isMatch ? 'text-emerald-600' : 'text-ink-300'}">${isMatch ? '✓' : '—'}</span>
      `;
      barsDiv.appendChild(row);
    });
    ecDiv.appendChild(barsDiv);

    // Sample quotes
    if (ecInsight.sample_quotes && ecInsight.sample_quotes.length) {
      const quotesDiv = el("div", "mt-4 pt-3 border-t border-ink-100");
      quotesDiv.innerHTML = `<p class="text-[10px] tracking-[0.18em] uppercase text-ink-400 font-medium mb-2">What accepted students mentioned</p>`;
      ecInsight.sample_quotes.filter(q => q.length > 15).forEach(q => {
        quotesDiv.appendChild(el("p", "text-[12.5px] text-ink-500 leading-relaxed pl-3 border-l-2 border-ink-100 mb-1.5",
          `"${esc(q)}"`));
      });
      ecDiv.appendChild(quotesDiv);
    }
    body.appendChild(ecDiv);
  } else if (p.ec_weight === "medium") {
    // Waterloo CS variants — brief AIF note
    body.appendChild(el("div", "program-subsection-label mt-6", "2. EC Analysis"));
    body.appendChild(el("p", "text-[13px] text-ink-500 mt-2 mb-4",
      "AIF (Admission Information Form) required — Justin's AIF will be strong given his CyberPatriot, Kaggle, IMC, and Harvard MEDScience credentials."));
  } else {
    // No supp app — still show section 2 so numbering is consistent
    body.appendChild(el("div", "program-subsection-label mt-6", "2. EC Analysis"));
    body.appendChild(el("p", "text-[13px] text-ink-500 mt-2 mb-4",
      "This program does not use a supplementary application — ECs do not directly affect the admission decision. Verdict is driven entirely by GPA."));
  }

  // ── Sub-section 3: Justin's Verdict ──
  body.appendChild(el("div", "program-subsection-label mt-6",
    `3. Justin's Verdict — <span class="badge badge--${vk}" style="font-size:11px;padding:2px 8px;vertical-align:1px">${esc(p.verdict_label)}</span>`));
  if (p.verdict_gpa_only && p.verdict_gpa_only !== p.verdict) {
    body.appendChild(el("p", "text-[13px] text-ink-500 mt-2",
      `GPA-only verdict: <strong class="text-ink-700">${esc(p.verdict_gpa_only)}</strong> → upgraded to <strong class="text-ink-700">${esc(p.verdict)}</strong> via EC leverage`));
  }
  if (p.reasoning) {
    const rc = el("div", "program-reasoning-formatted mt-3");
    rc.innerHTML = formatReasoning(p.reasoning);
    body.appendChild(rc);
  }
  if (p.ec_strength_text) {
    body.appendChild(el("div", "ec-fit mt-3", `<strong>EC fit</strong>${esc(p.ec_strength_text)}`));
  }

  // ── UofT Life Sci special: First-year enrichment programs ──
  if (p.program_key === "uoft_lifesci_stgeorge") {
    const enrichDiv = el("div", "mt-6");
    enrichDiv.innerHTML = `
      <div class="program-subsection-label">First-Year Enrichment: "One" Programs</div>
      <div class="rounded-lg border border-ink-100 bg-ink-50/50 p-5 mt-3 text-[13.5px] text-ink-700 leading-relaxed space-y-4">
        <p>
          UofT's residential colleges offer competitive small-cohort first-year seminars called <strong class="text-ink-900">"Ones" programs</strong>
          that provide mentoring, community, and research exposure within the large Life Sciences admission category. Two streams are
          directly relevant for pre-med students:
        </p>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div class="rounded-lg border border-ink-100 bg-card p-4">
            <div class="flex items-baseline gap-2 mb-2">
              <span class="text-[14px] font-medium text-ink-900">Vic One — Stowe-Gullen Stream</span>
              <span class="text-[11px] text-ink-400">Victoria College</span>
            </div>
            <div class="flex flex-wrap gap-1.5 mb-2.5">
              <span class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded bg-ink-50 border border-ink-100 text-ink-600">~25 students</span>
              <span class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded bg-ink-50 border border-ink-100 text-ink-600">2 full-year courses</span>
              <span class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded bg-ink-50 border border-ink-100 text-ink-600">Separate application</span>
            </div>
            <p class="text-[12.5px] text-ink-600 leading-relaxed mb-2">
              <strong>VIC170</strong> (Prof. Angus McQuibban): science communication — grant proposals, three-minute thesis presentations, lab visits.
              McQuibban runs a research lab and invites colleagues as guest speakers; alumni credit this course for securing first research positions.
              <strong>VIC171</strong> (Prof. Cory Lewis): philosophy of science, reading-heavy, generous extensions, open-topic weeks.
            </p>
            <p class="text-[12px] text-ink-500">
              83% of Vic One graduates earn distinction/high distinction vs 59% of all Arts &amp; Science students.
              Named after Emily Stowe and Augusta Stowe-Gullen, pioneers of Canadian women in medicine.
            </p>
          </div>
          <div class="rounded-lg border border-ink-100 bg-card p-4">
            <div class="flex items-baseline gap-2 mb-2">
              <span class="text-[14px] font-medium text-ink-900">Trinity One — Biomedical Health Stream</span>
              <span class="text-[11px] text-ink-400">Trinity College</span>
            </div>
            <div class="flex flex-wrap gap-1.5 mb-2.5">
              <span class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded bg-ink-50 border border-ink-100 text-ink-600">~20 students</span>
              <span class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded bg-ink-50 border border-ink-100 text-ink-600">2 full-year courses</span>
              <span class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded bg-ink-50 border border-ink-100 text-ink-600">Separate application</span>
            </div>
            <p class="text-[12.5px] text-ink-600 leading-relaxed mb-2">
              Offers <strong>TRN225Y1: "The Art of Health Discovery"</strong> — scientific writing, grant proposals, manuscripts.
              Students describe the community as a "stark contrast to impersonal first-year courses."
              Access to Trinity's undergraduate research conference in first year. More institutional funding for community events (bi-weekly catered lunches, field trips, end-of-year dinner).
            </p>
            <p class="text-[12px] text-ink-500">
              ~20 per stream (smaller than Vic One). Trinity has produced 43 Rhodes Scholars. Profs know students by first name.
            </p>
          </div>
        </div>
        <div class="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-[12.5px] text-amber-800">
          <strong class="text-[10.5px] tracking-[0.12em] uppercase">Important caveat:</strong>
          No published evidence exists that either program directly boosts med-school acceptance rates. UofT's MD program
          states "it does not matter what subject you studied." The benefits are indirect: stronger reference letters from faculty
          who know you, earlier research exposure, better science-communication skills, and a support community that reduces burnout.
          If Justin goes to UofT, applying to either is free upside — but this should not be the reason to choose UofT over another university.
        </div>
      </div>
    `;
    body.appendChild(enrichDiv);
  }

  // ── UofT Life Sci special: Student spotlight ──
  if (p.program_key === "uoft_lifesci_stgeorge") {
    const spotlightDiv = el("div", "mt-6");
    spotlightDiv.innerHTML = `
      <div class="program-subsection-label">Student Spotlight: An Old Scona Alumnus at UofT</div>
      <div class="rounded-lg border border-ink-100 bg-card p-5 mt-3">
        <div class="flex flex-col sm:flex-row sm:items-start gap-4">
          <div class="flex-1 min-w-0">
            <div class="flex items-baseline gap-2 flex-wrap mb-1">
              <span class="text-[15px] font-medium text-ink-900">Patrick Wang</span>
              <span class="text-[12px] text-ink-400">Old Scona Academic → UofT Life Sciences → Victoria College</span>
            </div>
            <p class="text-[13px] text-ink-600 leading-relaxed mb-3">
              Pathobiology Specialist + Immunology Major · Class of 2026 · From <strong class="text-ink-800">Edmonton, Alberta</strong> —
              the same high school, same city, and same out-of-province pathway Justin would take.
            </p>

            <div class="space-y-3">
              <div>
                <p class="text-[10px] tracking-[0.15em] uppercase text-ink-400 font-medium mb-1.5">Trajectory at UofT</p>
                <div class="space-y-1.5 text-[12.5px] text-ink-600">
                  <div class="flex gap-2">
                    <span class="text-ink-400 shrink-0 w-[52px] tabular-nums">Year 1</span>
                    <span>Life Sciences at Victoria College. Maintained 3.50+ GPA.</span>
                  </div>
                  <div class="flex gap-2">
                    <span class="text-ink-400 shrink-0 w-[52px] tabular-nums">Year 2</span>
                    <span>Dean's List Scholar. Isabel Bader In-Course Scholarship (Vic College, GPA 3.50+). Declared Pathobiology + Immunology.</span>
                  </div>
                  <div class="flex gap-2">
                    <span class="text-ink-400 shrink-0 w-[52px] tabular-nums">Sum '24</span>
                    <span>LMP SURE program — 4 months in Dr. Kelsie Thu's lab (lung cancer chemotherapy resistance). Poster presentations at KRSS + LMP SURE competitions.</span>
                  </div>
                  <div class="flex gap-2">
                    <span class="text-ink-400 shrink-0 w-[52px] tabular-nums">Year 3</span>
                    <span>LMP305 research course (8 months in Thu Lab). Won <strong class="text-ink-800">Milne Research Award</strong>, <strong class="text-ink-800">John P. Mitchell Undergrad Research Award</strong> (given to ONE student), <strong class="text-ink-800">Alan Gornall Pathobiology Award</strong>.</span>
                  </div>
                  <div class="flex gap-2">
                    <span class="text-ink-400 shrink-0 w-[52px] tabular-nums">Sum '25</span>
                    <span>Dr. Hong Chang's lab — therapeutic targeting of resistant acute myeloid leukemia.</span>
                  </div>
                </div>
              </div>

              <div class="flex flex-wrap gap-1.5 pt-2">
                <span class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded bg-emerald-50 border border-emerald-200 text-emerald-700">Old Scona Academic</span>
                <span class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded bg-emerald-50 border border-emerald-200 text-emerald-700">Rutherford Scholars (top 10 AB Diploma)</span>
                <span class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded bg-ink-50 border border-ink-100 text-ink-600">Victoria College</span>
                <span class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded bg-ink-50 border border-ink-100 text-ink-600">Dean's List</span>
                <span class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded bg-ink-50 border border-ink-100 text-ink-600">LMP SURE Research</span>
                <span class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded bg-ink-50 border border-ink-100 text-ink-600">qPCR + Western Blotting</span>
                <span class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded bg-ink-50 border border-ink-100 text-ink-600">3 Research Awards</span>
              </div>
            </div>
          </div>
        </div>

        <div class="mt-4 pt-3 border-t border-ink-100 text-[12.5px] text-ink-500 leading-relaxed space-y-2">
          <p>
            <strong class="text-ink-700">Why this matters for Justin:</strong>
            Patrick proves the Old Scona → UofT Life Sci → Victoria College path works for an Edmonton OOP applicant. By Year 3 he had
            three research awards, funded cancer research in Faculty of Medicine labs, and a Pathobiology specialist that sits inside
            the Temerty Faculty of Medicine — giving direct access to the TAHSN hospital network from undergrad.
          </p>
          <p>
            The <strong class="text-ink-700">Rutherford Scholars Award</strong> (top 10 on Alberta Diploma Exam) suggests Patrick entered
            UofT with a comparable academic profile to Justin's projected 95.5%. The <strong class="text-ink-700">LMP SURE</strong> summer research
            program is the formal pipeline that converted his undergrad status into real lab experience — the kind of research CV
            that makes medical school applications competitive.
          </p>
        </div>

        <p class="mt-3 text-[11px] text-ink-400">
          Sources:
          <a href="https://lmp.utoronto.ca/news/humans-lmp-patrick-wang" target="_blank" rel="noopener" class="underline decoration-dotted underline-offset-3 hover:text-ink-700">LMP "Humans of LMP" profile</a> ·
          <a href="https://www.linkedin.com/in/patrick-wang-559042246/" target="_blank" rel="noopener" class="underline decoration-dotted underline-offset-3 hover:text-ink-700">LinkedIn</a>
        </p>
      </div>
    `;
    body.appendChild(spotlightDiv);
  }

  // ── Sub-section 4: Application Procedure ──
  body.appendChild(el("div", "program-subsection-label mt-6", "4. Application Procedure"));
  const reqGrid = el("div", "program-req-grid mt-3");

  function rq(label, value) {
    if (value === null || value === undefined || value === "") return "";
    return `<div><dt>${esc(label)}</dt><dd>${value}</dd></div>`;
  }

  reqGrid.innerHTML = `
    ${rq("OUAC deadline", p.deadline_ouac ? esc(fmtDate(p.deadline_ouac)) : null)}
    ${rq("Supp deadline", p.deadline_supp ? esc(fmtDate(p.deadline_supp)) : null)}
    ${rq("Document deadline", p.deadline_doc ? esc(fmtDate(p.deadline_doc)) : null)}
    ${rq("Decision window", p.decision_window ? esc(p.decision_window) : null)}
    ${rq("Supplementary", p.supp_app_required == null ? null :
      (p.supp_app_required ? esc(p.supp_app_type || "Required") : "None"))}
    ${rq("CASPer", p.casper_required === true ? "Required" :
      (p.casper_required === false ? "Not required" : null))}
    ${rq("Fee (CAD)", p.fee_cad != null ? "$" + p.fee_cad : null)}
    ${rq("Confidence", p.requirements_confidence ? esc(p.requirements_confidence) : null)}
    ${rq("Official page", p.official_url ?
      `<a href="${esc(p.official_url)}" target="_blank" rel="noopener" class="program-link">Visit page ↗</a>` : null)}
  `;
  body.appendChild(reqGrid);

  // Prereq courses
  if (p.prereq_courses && p.prereq_courses.length) {
    const prereqDiv = el("div", "mt-3");
    prereqDiv.innerHTML = `
      <p class="text-[10.5px] tracking-[0.15em] uppercase text-ink-400 font-medium mb-1.5">Prerequisite courses</p>
      <ul class="text-[13px] text-ink-600 space-y-0.5 pl-4 list-disc">${
        p.prereq_courses.map(c => `<li>${esc(c)}</li>`).join("")
      }</ul>
      ${p.prereq_notes ? `<p class="text-[12px] text-ink-400 mt-2 leading-relaxed">${esc(p.prereq_notes).slice(0, 300)}</p>` : ""}
    `;
    body.appendChild(prereqDiv);
  }

  // Decision timeline months (if available)
  if (timelineMonths && timelineMonths.length) {
    const tlDiv = el("div", "mt-3");
    tlDiv.innerHTML = `
      <p class="text-[10.5px] tracking-[0.15em] uppercase text-ink-400 font-medium mb-1.5">When decisions arrived (2024-25 cycle)</p>
      <div class="flex flex-wrap gap-1.5">${timelineMonths.map(m => {
        const month = m.year_month.split("-")[1];
        const monthNames = {
          "01":"Jan","02":"Feb","03":"Mar","04":"Apr","05":"May","06":"Jun",
          "07":"Jul","08":"Aug","09":"Sep","10":"Oct","11":"Nov","12":"Dec"};
        return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] rounded border border-ink-100 bg-ink-50 text-ink-700 tabular-nums">
          <span class="font-medium">${monthNames[month] || month}</span>
          <span class="text-ink-400">${m.n_accepted}A</span>
          ${m.n_rejected ? `<span class="text-red-500">${m.n_rejected}R</span>` : ""}
          ${m.n_deferred ? `<span class="text-amber-600">${m.n_deferred}D</span>` : ""}
        </span>`;
      }).join("")}</div>
    `;
    body.appendChild(tlDiv);
  }

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
// (Checklist section removed — merged into per-program cards)
// ────────────────────────────────────────────────────────────────────

/* Removed: renderChecklist, renderChecklistRows, renderChecklistCards, sortRows, updateSortIndicators
   — all checklist data is now inside per-program cards (sub-section 4: Application Procedure) */
function _removed_renderChecklist(data) {
  const rows = [...(data.tier1 || []), ...(data.tier2 || [])]
    .filter(p => p.deadline_ouac); // only programs with real deadlines

  const state = { sortKey: "_rank", sortDir: "asc" };

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
    // Custom rank sort: use the explicit CHECKLIST_ORDER map
    if (sortKey === "_rank") {
      const oa = CHECKLIST_ORDER[a.program_key] ?? 99;
      const ob = CHECKLIST_ORDER[b.program_key] ?? 99;
      return (oa - ob) * dir;
    }
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
// (EC Insights section removed — merged into per-program cards)
// ────────────────────────────────────────────────────────────────────

const PROGRAM_LABELS_SHORT = {
  mcmaster_bhsc: "McMaster BHSc",
  queens_bhsc: "Queen's BHSc",
  waterloo_cs: "Waterloo CS",
};

const EC_BAR_COLORS = {
  mcmaster_bhsc: "#1f2937",
  queens_bhsc: "#0f766e",
  waterloo_cs: "#1e3a8a",
};

/* Removed: renderEcInsights — EC data now rendered inside each Tier-1 program card */
function _removed_renderEcInsights(ecInsights, tier1) {
  const container = document.getElementById("ec-insights-container");
  if (!container || !ecInsights) return;
  container.innerHTML = "";

  const programs = ["mcmaster_bhsc", "queens_bhsc", "waterloo_cs"];

  programs.forEach(progKey => {
    const ec = ecInsights[progKey];
    if (!ec || !ec.category_frequencies) return;

    const label = PROGRAM_LABELS_SHORT[progKey] || progKey;
    const freq = ec.category_frequencies;
    const categories = Object.keys(freq);
    const values = Object.values(freq);
    const maxVal = Math.max(...values, 1);

    // Build the card
    const card = el("div", "rounded-lg border border-ink-100 bg-card p-5 md:p-6");

    // Header: program name + coverage stat
    card.innerHTML = `
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-5">
        <div>
          <h3 class="text-[15px] font-medium text-ink-900">${esc(label)}</h3>
          <p class="text-[12px] text-ink-400 mt-0.5">EC categories among accepted applicants (n=${ec.n_with_ec_data} of ${ec.n_accepted_total}, ${ec.coverage_pct}% coverage)</p>
        </div>
        <div class="flex items-center gap-2">
          <span class="inline-flex items-center px-2.5 py-1 text-[11px] font-medium rounded-full border
            ${ec.justin_alignment.match_rate_pct >= 75 ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-amber-50 border-amber-200 text-amber-700'}">
            Justin matches ${ec.justin_alignment.matched.length}/${categories.length} categories
          </span>
        </div>
      </div>
    `;

    // Horizontal bar chart (pure HTML/CSS, no Chart.js needed)
    const barsDiv = el("div", "space-y-2");
    categories.forEach((cat, i) => {
      const count = values[i];
      const pct = (count / maxVal) * 100;
      const isJustinMatch = ec.justin_alignment.matched.includes(cat);
      const barColor = EC_BAR_COLORS[progKey] || "#1f2937";

      const row = el("div", "flex items-center gap-3 text-[12.5px]");
      row.innerHTML = `
        <span class="w-[160px] sm:w-[200px] shrink-0 text-right text-ink-600 truncate" title="${esc(cat)}">${esc(cat)}</span>
        <div class="flex-1 h-6 bg-ink-50 rounded overflow-hidden relative">
          <div class="h-full rounded transition-all duration-300" style="width:${pct}%;background:${barColor};opacity:${isJustinMatch ? '0.85' : '0.35'}"></div>
          <span class="absolute inset-y-0 left-2 flex items-center text-[11px] font-medium ${pct > 30 ? 'text-white' : 'text-ink-700'}">${count}</span>
        </div>
        <span class="w-5 shrink-0 text-center text-[13px] ${isJustinMatch ? 'text-emerald-600' : 'text-ink-300'}" title="${isJustinMatch ? 'Justin has this' : 'Justin does not have this'}">${isJustinMatch ? '✓' : '—'}</span>
      `;
      barsDiv.appendChild(row);
    });
    card.appendChild(barsDiv);

    // Sample quotes
    if (ec.sample_quotes && ec.sample_quotes.length > 0) {
      const quotesDiv = el("div", "mt-5 pt-4 border-t border-ink-100");
      quotesDiv.innerHTML = `<p class="text-[10.5px] tracking-[0.18em] uppercase text-ink-400 font-medium mb-3">What accepted students mentioned</p>`;
      const quotesList = el("div", "space-y-2");
      ec.sample_quotes.forEach(q => {
        if (q.length > 15) {
          quotesList.appendChild(el("p", "text-[13px] text-ink-500 leading-relaxed pl-3 border-l-2 border-ink-100",
            `"${esc(q)}"`));
        }
      });
      quotesDiv.appendChild(quotesList);
      card.appendChild(quotesDiv);
    }

    container.appendChild(card);
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
    <p><strong>Other programs in the analysis (not shown above):</strong></p>
    <p>
      <strong>Tier 3 — Additional backups</strong> (${(tier3 || []).length} programs):
      ${t3Summary}. Includes remaining Waterloo variants and UofT satellite-campus Life Sciences (UTM, UTSC).
      Most have too few Reddit reports for a reliable per-program verdict.
    </p>
    <p>
      <strong>Tier 4 — UAlberta in-province options</strong> (${t4Any} programs):
      remaining UAlberta science specializations (Biological Sciences, Biochemistry, Cell Biology, Immunology, Pharmacology,
      Neuroscience, Computing Science, Pharmacy). All have insufficient Reddit sample size for per-program placement.
      Justin's 95.5% projected top-6 clears UAlberta's published thresholds comfortably — these are safeties by any measure.
      BSc Physiology (the top UAlberta pre-med major) has been promoted to Tier 2 above.
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
// Appendix — populate data sources table and total row count
// ────────────────────────────────────────────────────────────────────

function renderAppendix(data) {
  const dq = data.data_quality;
  if (!dq || !dq.cycles) return;

  // Aggregate stats
  const totalRows = dq.cycles.reduce((sum, c) => sum + (c.n_rows || 0), 0);
  const totalCycles = dq.cycles.length;
  const totalPrograms = (data.tier1 || []).length + (data.tier2 || []).length
    + (data.tier3 || []).length + (data.tier4 || []).length;
  const allProgs = [...(data.tier1 || []), ...(data.tier2 || []), ...(data.tier3 || []), ...(data.tier4 || [])];
  const totalUniversities = new Set(allProgs.map(p => p.university)).size;
  const totalDecisions = dq.cycles.reduce((sum, c) => sum + (c.n_decisions_mapped || 0), 0);
  const totalRequirements = [...(data.tier1 || []), ...(data.tier2 || [])]
    .filter(p => p.deadline_ouac).length;

  // Populate inline references
  const totalEl = document.getElementById("appendix-total-rows");
  if (totalEl) totalEl.textContent = totalRows.toLocaleString() + "+";
  const progsEl = document.getElementById("appendix-total-programs");
  if (progsEl) progsEl.textContent = String(totalPrograms);

  // Populate summary stats grid
  const statsMap = {
    "stat-total-rows":         totalRows.toLocaleString(),
    "stat-total-cycles":       String(totalCycles),
    "stat-total-programs":     String(totalPrograms),
    "stat-total-universities":  totalUniversities.toLocaleString(),
    "stat-total-requirements":  String(totalRequirements),
    "stat-total-decisions":    totalDecisions.toLocaleString(),
  };
  for (const [id, value] of Object.entries(statsMap)) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  // Sources table
  const tbody = document.getElementById("appendix-sources-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const sourceUrls = {
    "2022-2023":    "https://docs.google.com/spreadsheets/d/18xQRBO1X2llysir9GwHPhdRPeJGL-osKhOX7WC4e_3o/",
    "2023-2024":    "https://docs.google.com/spreadsheets/d/1X5oygD0Mu8v899bRBvklzB-t6saHMS7mrqfH_xsiq2Y/",
    "2024-2025":    "https://docs.google.com/spreadsheets/d/1j48oJsjcAqS9K2wQ-x-W27gYr5LuOT-a96dt_ZZpjrw/",
    "2025-2026":    "https://docs.google.com/spreadsheets/d/1NCN-1lw39N9lRyB9bJPfrkJy8v3V-yjnnZ1HjrG5I9A/",
    "2025-2026-ab": "https://docs.google.com/spreadsheets/d/1fm2jDtnOyD6102mmWVXoCTNs0miMJ6-hyh5WjFKYP6Q/",
  };

  const subreddits = {
    "ON": "r/OntarioUniversities",
    "AB": "r/AlbertaGrade12s",
  };

  dq.cycles.forEach(c => {
    const tr = document.createElement("tr");
    const statusBadge = c.live
      ? `<span class="inline-flex items-center gap-1 text-[11px] font-medium text-green-700"><span class="w-1.5 h-1.5 rounded-full bg-green-500 inline-block"></span> Live</span>`
      : `<span class="text-[11px] text-ink-400">Closed</span>`;
    const sourceUrl = sourceUrls[c.cycle] || "#";
    const subreddit = subreddits[c.region] || c.region || "—";

    tr.innerHTML = `
      <td class="px-6 py-3 font-medium text-ink-900">${esc(c.cycle)}</td>
      <td class="px-4 py-3">${esc(subreddit)}</td>
      <td class="px-4 py-3 tabular-nums">${(c.n_rows || 0).toLocaleString()}</td>
      <td class="px-4 py-3 tabular-nums">${(c.n_programs_mapped || 0).toLocaleString()}</td>
      <td class="px-4 py-3">${statusBadge}</td>
      <td class="px-4 py-3"><a href="${esc(sourceUrl)}" target="_blank" rel="noopener" class="program-link">Spreadsheet ↗</a></td>
    `;
    tbody.appendChild(tr);
  });

  // Totals row
  const totalMapped = dq.cycles.reduce((s, c) => s + (c.n_programs_mapped || 0), 0);
  const tfoot = document.createElement("tr");
  tfoot.className = "bg-ink-50/60 font-medium text-ink-900";
  tfoot.innerHTML = `
    <td class="px-6 py-2.5" colspan="2">Total</td>
    <td class="px-4 py-2.5 tabular-nums">${totalRows.toLocaleString()}</td>
    <td class="px-4 py-2.5 tabular-nums">${totalMapped.toLocaleString()}</td>
    <td class="px-4 py-2.5" colspan="2"></td>
  `;
  tbody.appendChild(tfoot);
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
    renderProgramCards(data);
    renderTier34Note(data.tier3 || [], data.tier4 || []);
    renderAppendix(data);
    wireAnchorAutoOpen();
    wireNavActiveState();
  } catch (err) {
    showError(err);
  }
}

main();
