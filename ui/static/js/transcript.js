/* Transcript event rendering and call/output pairing. */
import { escapeHtml } from "./util.js";
import { renderMath } from "./math.js";

export function renderEvent(ev) {
  if (ev.kind === "meta") {
    return '<div class="divider">session start — ' + escapeHtml(ev.timestamp || "") +
      " — cwd " + escapeHtml(ev.cwd || "") + "</div>";
  }
  if (ev.kind === "compacted") {
    return '<div class="divider">— context compacted —</div>';
  }
  if (ev.kind === "message") {
    if (ev.role === "assistant") {
      return '<div class="ev assistant"><div class="ev-head">codex</div>' +
        '<div class="markdown">' + renderMath(ev.text) + "</div></div>";
    }
    const label = escapeHtml(ev.role) + " message (" + ev.text.length + " chars)";
    return '<details class="ev"><summary>' + label + "</summary>" +
      '<div class="ev-body markdown">' + renderMath(ev.text) + "</div></details>";
  }
  if (ev.kind === "reasoning") {
    return '<details class="ev reasoning" open><summary>reasoning</summary>' +
      '<div class="ev-body markdown">' + renderMath(ev.text) + "</div></details>";
  }
  if (ev.kind === "call") {
    return '<details class="ev call"' +
      (ev.call_id ? ' data-call-id="' + escapeHtml(ev.call_id) + '"' : "") +
      '><summary>→ ' + escapeHtml(ev.name || "tool") +
      ' <span class="call-status">running...</span></summary>' +
      '<div class="ev-body"><pre>' + escapeHtml(ev.args || "") + "</pre>" +
      '<pre class="result" hidden></pre></div></details>';
  }
  if (ev.kind === "output") {
    return '<details class="ev output"><summary>← output (' + ev.text.length + " chars)</summary>" +
      '<div class="ev-body"><pre>' + escapeHtml(ev.text) + "</pre></div></details>";
  }
  if (ev.kind === "search") {
    return '<div class="ev search"><div class="ev-head">web search: ' +
      escapeHtml(ev.query || "") + "</div></div>";
  }
  return "";
}

/* Append a batch of events to a transcript container, pairing tool outputs
   into their call's card by call_id (the call may have arrived in an earlier
   batch). Returns true if any markdown-bearing event was appended. */
export function applyEvents(container, events) {
  let hasMarkdown = false;
  for (const ev of events) {
    if (ev.kind === "output" && ev.call_id) {
      const esc = typeof CSS !== "undefined" && CSS.escape
        ? CSS.escape(ev.call_id)
        : ev.call_id.replace(/"/g, '\\"');
      const card = container.querySelector('[data-call-id="' + esc + '"]');
      if (card) {
        const slot = card.querySelector("pre.result");
        slot.hidden = false;
        slot.textContent = ev.text || "(no output)";
        const status = card.querySelector(".call-status");
        if (status) status.textContent = "· " + (ev.text || "").length + " chars out";
        continue;
      }
    }
    if (ev.kind === "message" || ev.kind === "reasoning") hasMarkdown = true;
    container.insertAdjacentHTML("beforeend", renderEvent(ev));
  }
  return hasMarkdown;
}
