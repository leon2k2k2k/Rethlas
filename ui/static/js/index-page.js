/* Run-list page: cards, search, filters. */
import { escapeHtml } from "./util.js";
import { fetchJSON } from "./api.js";

const state = { runs: [], query: "", status: "", root: "", category: "" };

function chip(value, cls) {
  return '<span class="chip ' + (cls || "") + '">' + escapeHtml(value) + "</span>";
}

function matches(run) {
  if (state.status && run.status !== state.status) return false;
  if (state.root && run.root !== state.root) return false;
  if (state.category && run.category !== state.category) return false;
  if (state.query) {
    const hay = (run.id + " " + (run.title || "") + " " + (run.model || "")).toLowerCase();
    for (const term of state.query.toLowerCase().split(/\s+/)) {
      if (term && !hay.includes(term)) return false;
    }
  }
  return true;
}

function renderCards() {
  const visible = state.runs.filter(matches);
  const counts = {};
  state.runs.forEach(run => { counts[run.status] = (counts[run.status] || 0) + 1; });
  document.getElementById("summary").textContent =
    visible.length + " / " + state.runs.length + " runs — " +
    Object.entries(counts).map(([k, v]) => v + " " + k).join(", ");

  document.getElementById("run-grid").innerHTML = visible.map(run => {
    const chips = [
      '<span class="chip status-chip-' + run.status + '">' + escapeHtml(run.status) + "</span>",
      run.dead ? '<span class="chip status-chip-no-result">dead</span>' : "",
      run.root !== "main" ? chip(run.root) : "",
      chip(run.category),
      run.model ? chip(run.model) : "",
      run.has_route_cards ? chip("routes") : "",
      run.n_attempts ? chip(run.n_attempts + " attempt" + (run.n_attempts > 1 ? "s" : "")) : "",
    ].filter(Boolean).join("");
    return '<a class="run-card" href="run.html?run=' + encodeURIComponent(run.id) + '">' +
      "<h2>" + escapeHtml(run.title) + "</h2>" +
      "<p>" + escapeHtml(run.started_at || "") + "</p>" +
      '<div class="chips">' + chips + "</div></a>";
  }).join("") || '<div class="notice">No runs match the filters.</div>';
}

function renderFilters() {
  const statuses = [...new Set(state.runs.map(r => r.status))].sort();
  const roots = [...new Set(state.runs.map(r => r.root))].sort();
  const categories = [...new Set(state.runs.map(r => r.category))].sort();
  const bar = document.getElementById("filters");
  bar.innerHTML =
    '<input id="search" type="search" placeholder="search runs..." value="' +
    escapeHtml(state.query) + '" style="min-width:260px">' +
    select("f-status", "all statuses", statuses, state.status) +
    select("f-root", "all repos", roots, state.root) +
    select("f-category", "all categories", categories, state.category);

  document.getElementById("search").addEventListener("input", e => {
    state.query = e.target.value;
    renderCards();
  });
  for (const [id, key] of [["f-status", "status"], ["f-root", "root"], ["f-category", "category"]]) {
    document.getElementById(id).addEventListener("change", e => {
      state[key] = e.target.value;
      renderCards();
    });
  }

  function select(id, label, options, current) {
    return '<select id="' + id + '" style="width:auto"><option value="">' + label + "</option>" +
      options.map(o => '<option value="' + escapeHtml(o) + '"' +
        (o === current ? " selected" : "") + ">" + escapeHtml(o) + "</option>").join("") +
      "</select>";
  }
}

async function load(initial) {
  state.runs = await fetchJSON("/api/runs");
  if (initial) renderFilters();
  renderCards();
}

load(true).catch(error => {
  document.getElementById("run-grid").innerHTML =
    '<div class="notice bad">Failed to load runs: ' + escapeHtml(error.message) + "</div>";
});
setInterval(() => load(false).catch(() => {}), 15000);
