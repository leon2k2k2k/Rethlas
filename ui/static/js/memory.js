/* Memory journal rendering. */
import { escapeHtml } from "./util.js";
import { renderMathInline } from "./math.js";

export const MEMORY_ORDER = [
  "branch_states", "big_decisions", "failed_paths", "subgoals", "proof_steps",
  "immediate_conclusions", "toy_examples", "counterexamples",
  "verification_reports", "events",
];

export function renderValue(v) {
  if (v === null || v === undefined) return '<span style="color:var(--faint)">null</span>';
  if (typeof v === "string") return renderMathInline(v);
  if (Array.isArray(v)) {
    return "<ul>" + v.map(x => "<li>" + renderValue(x) + "</li>").join("") + "</ul>";
  }
  if (typeof v === "object") {
    return '<div class="kv-nest">' + Object.entries(v).map(([k, x]) =>
      "<div><strong>" + escapeHtml(k) + ":</strong> " + renderValue(x) + "</div>").join("") + "</div>";
  }
  return escapeHtml(String(v));
}

export function renderMemoryChannels(channels) {
  const names = Object.keys(channels)
    .sort((a, b) => MEMORY_ORDER.indexOf(a) - MEMORY_ORDER.indexOf(b));
  const blocks = [];
  for (const name of names) {
    const records = channels[name];
    const open = name !== "events" ? " open" : "";
    blocks.push('<details class="ev"' + open + "><summary>" + escapeHtml(name) +
      " (" + records.length + ")</summary><div class='ev-body'>" +
      records.map(rec => {
        const ts = (rec.timestamp_utc || "").slice(0, 19).replace("T", " ");
        const body = rec.record !== undefined ? rec.record : rec;
        return '<div class="mem-rec"><div class="meta-line">' + escapeHtml(ts) + "</div>" +
          '<div class="markdown">' + renderValue(body) + "</div></div>";
      }).join("") + "</div></details>");
  }
  return blocks;
}
