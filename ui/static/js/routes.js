/* Route-card (discovery output) rendering. */
import { escapeHtml } from "./util.js";
import { renderMath, renderMathInline } from "./math.js";
import { renderValue } from "./memory.js";

function scoreTable(scores) {
  if (!scores || !Object.keys(scores).length) return "";
  const rows = Object.entries(scores)
    .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))
    .map(([k, v]) => "<tr><td>" + escapeHtml(k) + "</td><td>" + escapeHtml(v) + "</td></tr>")
    .join("");
  return '<table class="score-table"><tbody>' + rows + "</tbody></table>";
}

export function renderRouteCard(entry) {
  const c = entry.card || {};
  const validBadge = entry.valid === false
    ? '<span class="chip status-chip-no-result">invalid</span>'
    : entry.valid === true ? '<span class="chip status-chip-verified">valid</span>' : "";
  const head = (entry.sample ? entry.sample + " — " : "") +
    (c.stage || "?") + (c.confidence != null ? " · conf " + c.confidence : "");
  const fields = [
    ["construction family", c.construction_family],
    ["positive reduction", c.positive_reduction],
    ["missing object", c.missing_object],
    ["failed because", c.failed_because],
    ["next stage", c.next_stage],
    ["next source families", (c.next_source_families || []).join("; ")],
    ["transition signal", c.transition_signal],
  ].filter(([, v]) => v);
  return '<details class="ev" open><summary>' + escapeHtml(head) + " " + validBadge +
    '</summary><div class="ev-body markdown">' +
    fields.map(([k, v]) => "<div><strong>" + escapeHtml(k) + ":</strong> " +
      renderMathInline(String(v)) + "</div>").join("") +
    scoreTable(c.scores) +
    (c.cost_formula ? "<div><strong>cost formula:</strong>" + renderValue(c.cost_formula) + "</div>" : "") +
    (entry.errors.length
      ? '<div class="bad"><strong>validation errors:</strong> ' +
        escapeHtml(entry.errors.join("; ")) + "</div>" : "") +
    "</div></details>";
}

export function renderRoutes(data) {
  const blocks = [];
  if (data.promotion_decision) {
    const d = data.promotion_decision;
    blocks.push('<div class="ev assistant"><div class="ev-head">promotion decision: ' +
      escapeHtml(d.action || "?") + "</div>" +
      '<div class="markdown">' +
      (d.reasons || []).map(r => "<p>" + renderMathInline(r) + "</p>").join("") +
      (d.stage_counts ? renderValue(d.stage_counts) : "") +
      "</div></div>");
  }
  if (data.promotion_manifest) {
    const m = data.promotion_manifest;
    blocks.push('<div class="ev"><div class="ev-head">promoted child: ' +
      escapeHtml(m.generated_problem_id || "?") +
      '</div><div class="ev-body markdown"><a href="run.html?run=' +
      encodeURIComponent(m.generated_problem_id || "") + '">open child run</a></div></div>');
  }
  for (const entry of data.cards) blocks.push(renderRouteCard(entry));
  if (data.triage_report) {
    blocks.push('<details class="ev"><summary>triage report</summary>' +
      '<div class="ev-body markdown">' + renderMath(data.triage_report) + "</div></details>");
  }
  return blocks;
}
