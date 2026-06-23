/* Markdown + TeX rendering.

marked treats backslashes as markdown escapes, which destroys \( \) \[ \]
TeX before MathJax runs — so math segments are shielded behind placeholders
around the markdown pass and restored (HTML-escaped) afterwards for MathJax
to typeset in the browser.

In the browser, `marked` comes from the vendored UMD bundle (window.marked);
tests inject it via setMarked(). */
import { escapeHtml } from "./util.js";

export const MATH_RE = /\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$[^\s$](?:[^$\n]*[^\s$])?\$/g;

let markedLib = typeof window !== "undefined" ? window.marked : null;

export function setMarked(lib) {
  markedLib = lib;
}

function md() {
  if (!markedLib && typeof window !== "undefined") markedLib = window.marked;
  if (!markedLib) throw new Error("marked library not available");
  return markedLib;
}

export function shieldMath(text) {
  const stash = [];
  const shielded = String(text).replace(MATH_RE, m => " MATH" + (stash.push(m) - 1) + " ");
  return { shielded, stash };
}

export function restoreMath(html, stash) {
  return html.replace(/ MATH(\d+) /g, (_, i) => escapeHtml(stash[Number(i)]));
}

export function renderMath(text) {
  const { shielded, stash } = shieldMath(text);
  return restoreMath(md().parse(shielded), stash);
}

export function renderMathInline(text) {
  const { shielded, stash } = shieldMath(text);
  return restoreMath(md().parseInline(shielded), stash);
}

/* Escape console/log text for HTML while disabling $-pairing (shell $VARS
   would otherwise trigger MathJax inline math); \( \) \[ \] still typeset. */
export function escapeConsoleText(text) {
  return escapeHtml(text).replace(/\$/g, "$​");
}

/* MathJax typesetting with a retry once MathJax finishes loading. */
let pendingMathRoot = null;

export function typeset(root) {
  pendingMathRoot = root;
  if (typeof window !== "undefined" && window.MathJax && window.MathJax.typesetPromise) {
    pendingMathRoot = null;
    window.MathJax.typesetPromise([root]).catch(() => {});
  }
}

if (typeof window !== "undefined") {
  window.addEventListener("rethlas-mathjax-ready", () => {
    if (pendingMathRoot) typeset(pendingMathRoot);
  });
}
