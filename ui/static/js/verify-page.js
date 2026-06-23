import { escapeHtml } from "./util.js";
import { renderMathInline, typeset } from "./math.js";
import { fetchJSON } from "./api.js";

let current = null;
let timer = null;

async function poll() {
  if (!current) return;
  const entry = await fetchJSON("/api/verify/" + current);
  const status = document.getElementById("status");
  const outcome = document.getElementById("outcome");
  status.textContent = "status: " + entry.status +
    (entry.referee_dir ? " · referee " + entry.referee_dir : "");
  if (entry.status === "running") return;
  clearInterval(timer);
  outcome.hidden = false;
  if (entry.status === "failed") {
    outcome.innerHTML = '<div class="notice bad">verification call failed: ' +
      escapeHtml((entry.result || {}).error || "unknown") + "</div>";
    return;
  }
  const r = entry.result || {};
  const report = r.verification_report || {};
  const refLink = entry.log_path
    ? '<p><a class="button" href="/api/file?path=' + encodeURIComponent(entry.log_path) +
      "&root=" + encodeURIComponent(entry.root + "!ver") + '" target="_blank">raw referee log</a></p>'
    : "";
  outcome.innerHTML = '<div class="ev assistant"><div class="ev-head">verdict: ' +
    escapeHtml(r.verdict || "?") + "</div>" +
    '<div class="markdown"><p>' + renderMathInline(report.summary || "(no summary)") + "</p>" +
    (r.repair_hints ? "<p><strong>repair hints:</strong> " +
      renderMathInline(String(r.repair_hints)) + "</p>" : "") +
    refLink + "</div></div>";
  typeset(outcome);
}

document.getElementById("submit").addEventListener("click", async () => {
  const statement = document.getElementById("statement").value;
  const proof = document.getElementById("proof").value;
  const status = document.getElementById("status");
  try {
    const resp = await fetch("/api/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ statement, proof }),
    });
    const body = await resp.json();
    if (!resp.ok) throw new Error(body.detail || resp.status);
    current = body.id;
    status.textContent = "submitted — referee session starting (this can take minutes)...";
    document.getElementById("outcome").hidden = true;
    clearInterval(timer);
    timer = setInterval(() => poll().catch(() => {}), 5000);
  } catch (e) {
    status.textContent = "failed: " + e.message;
  }
});
