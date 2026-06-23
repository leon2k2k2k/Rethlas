/* Parse Codex CLI console output (user/codex/exec/tokens-used sections)
   into the same card layout as the Transcript tab. */
import { escapeHtml } from "./util.js";
import { escapeConsoleText, renderMath } from "./math.js";

const MARKERS = {
  "user": "user", "codex": "codex", "thinking": "thinking",
  "exec": "exec", "tokens used": "tokens",
};

export function renderConsoleLog(text) {
  const lines = String(text).split("\n");
  const blocks = [];
  let kind = "head", buf = [];

  function flush() {
    const body = buf.join("\n").trim();
    buf = [];
    if (!body && kind !== "tokens") return;
    if (kind === "codex") {
      blocks.push('<div class="ev assistant"><div class="ev-head">codex</div>' +
        '<div class="markdown">' + renderMath(body) + "</div></div>");
    } else if (kind === "thinking") {
      blocks.push('<details class="ev reasoning" open><summary>reasoning</summary>' +
        '<div class="ev-body markdown">' + renderMath(body) + "</div></details>");
    } else if (kind === "user") {
      blocks.push('<details class="ev"><summary>user message (' + body.length + " chars)</summary>" +
        '<div class="ev-body markdown">' + renderMath(body) + "</div></details>");
    } else if (kind === "exec") {
      const firstLine = body.split("\n")[0].slice(0, 110);
      blocks.push('<details class="ev call" open><summary>→ exec ' + escapeHtml(firstLine) +
        '</summary><div class="ev-body"><div class="log-math" style="margin:0">' +
        escapeConsoleText(body) + "</div></div></details>");
    } else if (kind === "tokens") {
      blocks.push('<div class="divider">tokens used: ' +
        escapeHtml(body.split("\n")[0] || "") + "</div>");
    } else {
      blocks.push('<div class="log-math" style="margin:0">' +
        escapeConsoleText(body) + "</div>");
    }
  }

  for (const line of lines) {
    const marker = MARKERS[line.trim()];
    if (marker) { flush(); kind = marker; }
    else buf.push(line);
  }
  flush();
  return '<div class="transcript" style="padding:10px 0 0">' + blocks.join("") + "</div>";
}

/* Strip the giant quoted command prompt that opens controller/referee logs
   (it duplicates the Problem and Blueprint tabs). */
export function trimLogPreamble(text) {
  const banner = text.indexOf("OpenAI Codex v");
  return banner > 0 ? text.slice(banner) : text;
}
