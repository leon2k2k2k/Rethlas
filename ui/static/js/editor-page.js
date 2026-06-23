import { escapeHtml } from "./util.js";
import { renderMath, typeset } from "./math.js";
import { fetchJSON } from "./api.js";

const TEMPLATE = `# New problem: TITLE

## Background

Context, definitions, and what is already known. Math like \\(x^2\\) renders
in the preview.

## Target Statement

State the precise theorem to prove. This section is what the verifier will
judge the proof against.

## Required analysis

1. First required step.
2. Second required step.
`;

const state = { root: "main", file: null, sha: null, kind: null, dirty: false };

function setStatus(text) {
  document.getElementById("status-line").textContent = text;
}

async function loadLists() {
  const data = await fetchJSON("/api/editables?root=" + encodeURIComponent(state.root));
  const rootSel = document.getElementById("root-select");
  rootSel.innerHTML = data.roots.map(r =>
    '<option value="' + escapeHtml(r) + '"' + (r === state.root ? " selected" : "") + ">" +
    escapeHtml(r) + "</option>").join("");
  document.getElementById("data-list").innerHTML = data.data.map(f =>
    '<div><span><a href="#" data-open="' + escapeHtml(f) + '">' +
    escapeHtml(f.replace(/^data\//, "")) + "</a></span></div>").join("") ||
    "<div><span>none</span></div>";
  document.getElementById("config-list").innerHTML = data.configs.map(f =>
    '<div><span><a href="#" data-open="' + escapeHtml(f) + '">' + escapeHtml(f) +
    "</a></span></div>").join("");
  document.querySelectorAll("[data-open]").forEach(a => a.addEventListener("click", e => {
    e.preventDefault();
    openFile(a.dataset.open);
  }));
}

async function openFile(path, fresh) {
  if (state.dirty && !confirm("Discard unsaved changes?")) return;
  const doc = await fetchJSON("/api/edit?path=" + encodeURIComponent(path) +
    "&root=" + encodeURIComponent(state.root));
  state.file = path;
  state.sha = doc.sha;
  state.kind = doc.kind;
  state.dirty = false;
  document.getElementById("edit-area").value = doc.exists ? doc.content : (fresh || "");
  document.getElementById("current-file").textContent = state.root + " : " + path +
    (doc.exists ? "" : " (new)");
  document.getElementById("config-warning").hidden = doc.kind !== "config";
  document.getElementById("save-btn").disabled = false;
  document.getElementById("backups-btn").disabled = false;
  const launch = document.getElementById("launch-link");
  launch.hidden = doc.kind !== "data";
  launch.href = "launch.html";
  refreshPreview();
  setStatus(doc.exists ? "loaded (" + doc.content.length + " chars)" : "new file — not saved yet");
}

function refreshPreview() {
  const preview = document.getElementById("preview");
  preview.innerHTML = renderMath(document.getElementById("edit-area").value || "");
  typeset(preview);
}

async function save() {
  if (!state.file) return;
  const body = {
    root: state.root, path: state.file,
    content: document.getElementById("edit-area").value, sha: state.sha,
  };
  const resp = await fetch("/api/edit", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const out = await resp.json();
  if (resp.status === 409) {
    setStatus("CONFLICT: " + out.detail);
    return;
  }
  if (!resp.ok) {
    setStatus("save failed: " + (out.detail || resp.status));
    return;
  }
  state.sha = out.sha;
  state.dirty = false;
  setStatus("saved " + state.file + (out.backup ? " (backup " + out.backup + ")" : ""));
  loadLists();
}

async function showBackups() {
  const el = document.getElementById("backup-list");
  el.hidden = !el.hidden;
  if (el.hidden || !state.file) return;
  const backups = await fetchJSON("/api/backups?path=" + encodeURIComponent(state.file) +
    "&root=" + encodeURIComponent(state.root));
  el.innerHTML = backups.map(b =>
    '<button class="button" data-backup="' + escapeHtml(b.name) + '">' +
    escapeHtml(b.name.split("__")[0]) + "</button>").join("") ||
    '<span class="meta-line">no backups for this file</span>';
  el.querySelectorAll("[data-backup]").forEach(b => b.addEventListener("click", async () => {
    const text = await (await fetch("/api/backup-content?name=" +
      encodeURIComponent(b.dataset.backup))).text();
    document.getElementById("edit-area").value = text;
    state.dirty = true;
    refreshPreview();
    setStatus("backup loaded into editor — Save to restore it");
  }));
}

document.getElementById("edit-area").addEventListener("input", () => {
  state.dirty = true;
  refreshPreview();
});
document.getElementById("edit-toggle").addEventListener("change", e => {
  // default = preview only; "edit raw" reveals the textarea side-by-side
  document.getElementById("edit-area").hidden = !e.target.checked;
});
document.getElementById("save-btn").addEventListener("click", save);
document.getElementById("backups-btn").addEventListener("click", showBackups);
document.getElementById("new-btn").addEventListener("click", () => {
  const name = document.getElementById("new-name").value.trim();
  if (!name.startsWith("data/") || !name.endsWith(".md")) {
    setStatus("new problem path must look like data/category/name.md");
    return;
  }
  openFile(name, TEMPLATE);
});
document.getElementById("root-select").addEventListener("change", async e => {
  state.root = e.target.value;
  await loadLists();
});

loadLists().then(() => {
  const params = new URLSearchParams(window.location.search);
  const file = params.get("file");
  if (params.get("root")) state.root = params.get("root");
  if (file) openFile(file);
}).catch(e => setStatus("failed: " + e.message));
