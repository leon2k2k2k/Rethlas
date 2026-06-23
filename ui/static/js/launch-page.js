import { escapeHtml } from "./util.js";
import { fetchJSON } from "./api.js";

const TYPES = {
  retries: {
    label: "Attempt-based run (run_with_retries)",
    fields: [
      ["problem_file", "select-problem", null],
      ["problem_id", "text", "(defaults to problem path)"],
      ["max_attempts", "number", 5],
      ["blind", "checkbox", true],
      ["provider", "select-provider", ""],
      ["model", "text", "gpt-5.5"],
      ["reasoning_effort", "text", "xhigh"],
    ],
  },
  discovery: {
    label: "Discovery batch (route cards)",
    fields: [
      ["problem_file", "select-problem", null],
      ["batch_id", "text", "(auto timestamped)"],
      ["samples", "number", 5],
      ["parallel", "number", 2],
      ["profile", "text", "low_hint"],
      ["provider", "select-provider", ""],
      ["model", "text", "gpt-5.5"],
      ["reasoning_effort", "text", "xhigh"],
      ["dry_run", "checkbox", false],
    ],
  },
  baseline: {
    label: "Iteration baseline (run_example, clones)",
    fields: [
      ["root", "select-root", "main"],
      ["problem_file", "select-problem", null],
      ["max_iterations", "number", 10],
      ["model", "text", "gpt-5.5"],
      ["reasoning_effort", "text", "xhigh"],
    ],
  },
};

const state = { type: "retries", roots: ["main"], files: [], root: "main" };

async function loadFiles(root) {
  const data = await fetchJSON("/api/data-files?root=" + encodeURIComponent(root));
  state.files = data.files;
  state.roots = data.roots;
}

function fieldHtml([name, kind, dflt]) {
  const id = "f-" + name;
  if (kind === "select-problem") {
    return '<div class="launch-field"><label for="' + id + '">' + name + "</label>" +
      '<select id="' + id + '">' + state.files.map(f =>
        '<option value="' + escapeHtml(f) + '">' + escapeHtml(f) + "</option>").join("") +
      "</select></div>";
  }
  if (kind === "select-provider") {
    return '<div class="launch-field"><label for="' + id + '">' + name + "</label>" +
      '<select id="' + id + '">' +
      '<option value="">gpt (default codex auth)</option>' +
      '<option value="deepseek">deepseek (V4 via local bridge — model auto-switches to deepseek-v4-pro)</option>' +
      "</select></div>";
  }
  if (kind === "select-root") {
    return '<div class="launch-field"><label for="' + id + '">' + name + "</label>" +
      '<select id="' + id + '">' + state.roots.map(r =>
        '<option value="' + escapeHtml(r) + '"' + (r === state.root ? " selected" : "") + ">" +
        escapeHtml(r) + "</option>").join("") + "</select></div>";
  }
  if (kind === "checkbox") {
    return '<div class="launch-field"><label for="' + id + '">' + name + "</label>" +
      '<input id="' + id + '" type="checkbox"' + (dflt ? " checked" : "") + "></div>";
  }
  return '<div class="launch-field"><label for="' + id + '">' + name + "</label>" +
    '<input id="' + id + '" type="' + kind + '" ' +
    (typeof dflt === "string" && dflt.startsWith("(")
      ? 'placeholder="' + escapeHtml(dflt) + '"'
      : 'value="' + escapeHtml(dflt ?? "") + '"') + "></div>";
}

function render() {
  const spec = TYPES[state.type];
  document.getElementById("form-area").innerHTML =
    '<div class="tabs" style="border:0;padding:0 0 14px 0">' +
    Object.entries(TYPES).map(([key, t]) =>
      '<button class="tab' + (key === state.type ? " active" : "") + '" data-type="' + key + '">' +
      escapeHtml(t.label) + "</button>").join("") + "</div>" +
    '<div id="fields">' + spec.fields.map(fieldHtml).join("") + "</div>" +
    '<p><button class="button" id="launch" style="border-color:var(--accent);color:var(--accent-2)">Launch</button></p>';

  document.querySelectorAll(".tab[data-type]").forEach(b =>
    b.addEventListener("click", () => { state.type = b.dataset.type; render(); }));

  const rootSel = document.getElementById("f-root");
  if (rootSel) rootSel.addEventListener("change", async () => {
    state.root = rootSel.value;
    await loadFiles(state.root);
    render();
  });

  document.getElementById("launch").addEventListener("click", async () => {
    const params = { root: state.root };
    for (const [name, kind] of TYPES[state.type].fields) {
      const el = document.getElementById("f-" + name);
      if (!el) continue;
      if (kind === "checkbox") params[name] = el.checked;
      else if (el.value) params[name] = el.value;
    }
    const result = document.getElementById("result");
    result.hidden = false;
    result.textContent = "launching...";
    try {
      const resp = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: state.type, params }),
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.detail || resp.status);
      result.innerHTML = "Launched job <strong>" + escapeHtml(body.id) +
        '</strong> — <a href="jobs.html">watch it on the Jobs page</a>' +
        (body.link_run ? ' or <a href="run.html?run=' + encodeURIComponent(body.link_run) +
          '">open the run</a>' : "");
    } catch (e) {
      result.textContent = "Launch failed: " + e.message;
    }
  });
}

loadFiles("main").then(render).catch(e => {
  document.getElementById("form-area").textContent = "failed to load: " + e.message;
});
