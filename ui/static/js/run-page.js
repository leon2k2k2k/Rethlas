/* Run page orchestration: tabs, sidebar, polling. */
import { escapeHtml } from "./util.js";
import { renderMath, renderMathInline, typeset } from "./math.js";
import { fetchJSON, fetchFile, fileUrl } from "./api.js";
import { applyEvents } from "./transcript.js";
import { renderConsoleLog, trimLogPreamble } from "./console-log.js";
import { renderMemoryChannels } from "./memory.js";
import { renderRoutes } from "./routes.js";

const BASE_TABS = ["Problem", "Transcript", "Blueprint", "Verification", "Memory", "Logs", "Files"];

function tabsFor(run) {
  return run && run.has_route_cards
    ? [...BASE_TABS.slice(0, 3), "Routes", ...BASE_TABS.slice(3)]
    : BASE_TABS;
}

const state = {
  run: null,
  tab: "Problem",
  attemptIndex: 0,
  transcript: { sessionId: null, offset: 0 },
  follow: true,
  logRaw: false,
  timer: null,
};

function setStatusLine(text) {
  document.getElementById("refresh-status").textContent = text;
}

function currentAttempt() {
  return state.run.attempts[state.attemptIndex] || null;
}

function root() {
  return state.run.root || "main";
}

/* ---------- transcript ---------- */

async function pollTranscript(initial) {
  const attempt = currentAttempt();
  if (!attempt || !attempt.session_id) return;
  const t = state.transcript;
  const data = await fetchJSON("/api/transcript/" + attempt.session_id + "?offset=" + t.offset);
  t.offset = data.offset;
  const container = document.querySelector("#content .transcript");
  if (!container) return;
  if (initial && data.truncated) {
    container.insertAdjacentHTML("beforeend",
      '<div class="divider">— ' + data.truncated + " earlier events hidden —</div>");
  }
  if (data.events.length) {
    const hasMarkdown = applyEvents(container, data.events);
    if (hasMarkdown) typeset(container);
    const content = document.getElementById("content");
    if (state.follow) content.scrollTop = content.scrollHeight;
  }
  setStatusLine(t.offset === data.size
    ? "Up to date at " + new Date().toLocaleTimeString()
    : "Loading... " + Math.round(100 * t.offset / data.size) + "%");
}

async function showTranscript() {
  const attempt = currentAttempt();
  const content = document.getElementById("content");
  if (!attempt) {
    content.innerHTML = '<div class="notice">No attempt logs for this run (results only).</div>';
    return;
  }
  if (!attempt.session_id) {
    content.innerHTML = '<div class="notice">No Codex session id recorded in ' +
      escapeHtml(attempt.name) + ".</div>";
    return;
  }
  content.innerHTML = '<div class="transcript"></div>';
  state.transcript = { sessionId: attempt.session_id, offset: 0 };
  try {
    await pollTranscript(true);
  } catch (error) {
    content.innerHTML = '<div class="notice">' + escapeHtml(error.message) + "</div>";
  }
}

/* ---------- markdown / log / files tabs ---------- */

async function showMarkdownFile(path, fallbackMessage) {
  const content = document.getElementById("content");
  try {
    const text = await fetchFile(path, root());
    content.innerHTML = '<article class="markdown">' + renderMath(text) + "</article>";
    typeset(content);
    setStatusLine("Loaded " + path);
  } catch (error) {
    content.innerHTML = '<div class="notice">' + escapeHtml(fallbackMessage || error.message) + "</div>";
  }
}

async function showLog(path) {
  const content = document.getElementById("content");
  try {
    const text = await fetchFile(path, root());
    if (state.logRaw) {
      content.innerHTML = '<pre class="log"></pre>';
      content.querySelector("pre").textContent = text || "(empty)";
    } else {
      content.innerHTML = renderConsoleLog(trimLogPreamble(text || "(empty)"));
      typeset(content);
    }
    if (state.follow) content.scrollTop = content.scrollHeight;
    setStatusLine("Loaded " + path);
  } catch (error) {
    content.innerHTML = '<div class="notice">' + escapeHtml(error.message) + "</div>";
  }
}

function showFiles() {
  const content = document.getElementById("content");
  const cards = (state.run.results || []).map(file => {
    const href = fileUrl(file.path, root());
    return '<article class="file-card"><h3><a href="' + href + '" target="_blank">' +
      escapeHtml(file.name) + "</a></h3><p>" + (file.size / 1024).toFixed(1) + " KB</p></article>";
  }).join("");
  content.innerHTML = cards
    ? '<div class="file-grid">' + cards + "</div>"
    : '<div class="notice">No result files yet.</div>';
}

/* ---------- verification tab ---------- */

async function showVerification() {
  const content = document.getElementById("content");
  content.innerHTML = '<div class="notice">Loading verifications...</div>';
  let data;
  try {
    data = await fetchJSON("/api/verifications?run=" + encodeURIComponent(state.run.id));
  } catch (error) {
    content.innerHTML = '<div class="notice">' + escapeHtml(error.message) + "</div>";
    return;
  }
  const blocks = [];
  for (const a of data.attempts) {
    blocks.push('<div class="ev assistant"><div class="ev-head">verdict: ' +
      escapeHtml(a.verdict || "unknown") + " — " + escapeHtml(a.name) + "</div>" +
      '<div class="markdown"><p>' + renderMathInline(a.summary || "(no summary)") + "</p>" +
      (a.critical_errors && a.critical_errors.length
        ? "<p><strong>Critical errors:</strong> " +
          renderMathInline(JSON.stringify(a.critical_errors)) + "</p>" : "") +
      (a.repair_hints
        ? "<p><strong>Repair hints:</strong> " + renderMathInline(String(a.repair_hints)) + "</p>" : "") +
      "</div></div>");
  }
  for (const v of data.referee_runs) {
    const tlink = v.session_id
      ? ' <a class="button" href="run.html?session=' + encodeURIComponent(v.session_id) +
        '" target="_blank" style="margin-left:8px">open referee transcript</a>'
      : "";
    blocks.push('<details class="ev call"><summary>referee session ' + escapeHtml(v.id) +
      " — verdict: " + escapeHtml(v.verdict || "?") + '</summary><div class="ev-body">' +
      '<div class="markdown"><p>' + renderMathInline(v.summary || "") + tlink + "</p></div>" +
      '<div class="referee-log" data-log="' + escapeHtml(v.log_path) + '" data-root="' +
      escapeHtml(v.root) + '">(expand loads the referee session)</div></div></details>');
  }
  content.innerHTML = blocks.length
    ? '<div class="transcript">' + blocks.join("") + "</div>"
    : '<div class="notice">No verification artifacts found for this run.</div>';
  typeset(content);
  content.querySelectorAll("details.ev.call").forEach(d => d.addEventListener("toggle", async () => {
    const slot = d.querySelector(".referee-log");
    if (d.open && slot && !slot.dataset.loaded) {
      slot.dataset.loaded = "1";
      slot.textContent = "loading...";
      try {
        const resp = await fetch("/api/file?path=" + encodeURIComponent(slot.dataset.log) +
          "&root=" + encodeURIComponent(slot.dataset.root));
        slot.innerHTML = renderConsoleLog(trimLogPreamble(await resp.text()));
        typeset(slot);
      } catch (e) { slot.textContent = "failed: " + e.message; }
    }
  }));
  setStatusLine(data.attempts.length + " verdict file(s), " +
    data.referee_runs.length + " referee session(s)");
}

/* ---------- routes tab ---------- */

async function showRoutes() {
  const content = document.getElementById("content");
  content.innerHTML = '<div class="notice">Loading route cards...</div>';
  let data;
  try {
    data = await fetchJSON("/api/routes?run=" + encodeURIComponent(state.run.id));
  } catch (error) {
    content.innerHTML = '<div class="notice">' + escapeHtml(error.message) + "</div>";
    return;
  }
  const blocks = renderRoutes(data);
  const toolbar = '<div class="toolbar" style="border:1px solid var(--line);border-radius:7px;' +
    'margin-bottom:10px;justify-content:flex-start">' +
    '<button class="button" data-tool="triage">Run triage</button>' +
    '<button class="button" data-tool="promote">Generate promotion</button>' +
    (data.promotion_manifest
      ? '<button class="button" data-launch-promotion>Launch promoted run</button>' : "") +
    '<span class="refresh" id="tool-status"></span></div>';
  content.innerHTML = blocks.length
    ? '<div class="transcript">' + toolbar + blocks.join("") + "</div>"
    : '<div class="notice">No route cards found.</div>';
  typeset(content);
  content.querySelectorAll("[data-tool]").forEach(b => b.addEventListener("click", async () => {
    const st = document.getElementById("tool-status");
    st.textContent = "running " + b.dataset.tool + "...";
    try {
      const resp = await fetch("/api/tools/" + b.dataset.tool, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run: state.run.id }),
      });
      const out = await resp.json();
      if (!resp.ok) throw new Error(out.detail || resp.status);
      st.textContent = b.dataset.tool + " exit " + out.exit_code;
      showRoutes();
    } catch (e) { st.textContent = b.dataset.tool + " failed: " + e.message; }
  }));
  const launchBtn = content.querySelector("[data-launch-promotion]");
  if (launchBtn) launchBtn.addEventListener("click", async () => {
    if (!confirm("Launch the promoted child run? This starts a real Codex run.")) return;
    const st = document.getElementById("tool-status");
    try {
      const resp = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "promotion-launch", params: {
          root: state.run.root,
          launch_script: "results/" + state.run.rel_id + "/launch_promotion.sh",
        }}),
      });
      const out = await resp.json();
      if (!resp.ok) throw new Error(out.detail || resp.status);
      st.innerHTML = 'launched job <a href="jobs.html">' + out.id + "</a>";
    } catch (e) { st.textContent = "launch failed: " + e.message; }
  });
  setStatusLine(data.cards.length + " route card(s)");
}

/* ---------- memory tab ---------- */

async function showMemory() {
  const content = document.getElementById("content");
  content.innerHTML = '<div class="notice">Loading memory...</div>';
  let data;
  try {
    data = await fetchJSON("/api/memory?run=" + encodeURIComponent(state.run.id));
  } catch (error) {
    content.innerHTML = '<div class="notice">' + escapeHtml(error.message) + "</div>";
    return;
  }
  const blocks = renderMemoryChannels(data.channels);
  if (!blocks.length) {
    content.innerHTML = '<div class="notice">No memory directory for this run.</div>';
    return;
  }
  content.innerHTML = '<div class="transcript">' + blocks.join("") + "</div>";
  typeset(content);
  setStatusLine(blocks.length + " memory channels");
}

/* ---------- shell ---------- */

function blueprintPath() {
  const files = state.run.results || [];
  const pick = files.find(f => f.name === "blueprint_verified.md") ||
    files.find(f => f.name === "blueprint.md");
  return pick ? pick.path : "results/" + (state.run.rel_id || state.run.id) + "/blueprint.md";
}

function renderToolbar() {
  const toolbar = document.getElementById("toolbar");
  const attempts = state.run.attempts;
  let html = "<div class='toolbar-left'>";
  if ((state.tab === "Transcript" || state.tab === "Logs") && attempts.length) {
    html += '<select id="attempt-select">' + attempts.map((a, i) =>
      '<option value="' + i + '"' + (i === state.attemptIndex ? " selected" : "") + ">" +
      escapeHtml(a.name + (a.session_id ? "  ·  " + a.session_id : "")) + "</option>").join("") + "</select>";
  }
  html += "</div>";
  if (state.tab === "Transcript" || state.tab === "Logs") {
    html += '<label><input id="follow" type="checkbox"' + (state.follow ? " checked" : "") +
      "> follow bottom</label>";
  }
  if (state.tab === "Logs") {
    html += '<label><input id="log-raw" type="checkbox"' + (state.logRaw ? " checked" : "") +
      "> raw</label>";
  }
  toolbar.innerHTML = html;
  const select = document.getElementById("attempt-select");
  if (select) select.addEventListener("change", event => {
    state.attemptIndex = Number(event.target.value);
    drawContent();
  });
  const follow = document.getElementById("follow");
  if (follow) follow.addEventListener("change", event => { state.follow = event.target.checked; });
  const raw = document.getElementById("log-raw");
  if (raw) raw.addEventListener("change", event => { state.logRaw = event.target.checked; drawContent(); });
}

function renderTabs() {
  const tabs = document.getElementById("tabs");
  tabs.innerHTML = tabsFor(state.run).map(tab =>
    '<button class="tab' + (tab === state.tab ? " active" : "") + '" data-tab="' + tab + '">' +
    tab + "</button>").join("");
  tabs.querySelectorAll(".tab").forEach(button => button.addEventListener("click", () => {
    state.tab = button.dataset.tab;
    renderTabs();
    drawContent();
  }));
}

function drawContent() {
  renderToolbar();
  document.getElementById("detail-title").textContent = state.tab;
  document.getElementById("detail-subtitle").textContent = "";
  if (state.tab === "Transcript") return showTranscript();
  if (state.tab === "Problem") {
    const attempt = currentAttempt();
    const path = (attempt && attempt.problem_file) || state.run.problem_file;
    return path
      ? showMarkdownFile(path)
      : document.getElementById("content").innerHTML =
          '<div class="notice">No problem file recorded.</div>';
  }
  if (state.tab === "Blueprint") return showMarkdownFile(blueprintPath(), "No blueprint produced yet.");
  if (state.tab === "Routes") return showRoutes();
  if (state.tab === "Verification") return showVerification();
  if (state.tab === "Memory") return showMemory();
  if (state.tab === "Logs") {
    const attempt = currentAttempt();
    return (attempt && attempt.path)
      ? showLog(attempt.path)
      : document.getElementById("content").innerHTML = '<div class="notice">No attempt logs.</div>';
  }
  if (state.tab === "Files") return showFiles();
}

function renderShell() {
  const run = state.run;
  document.title = run.title + " — Rethlas";
  document.getElementById("page-title").textContent = run.title;
  document.getElementById("page-meta").textContent = run.id;
  document.getElementById("side-title").textContent = run.title;
  document.getElementById("side-subtitle").textContent = run.category;
  document.getElementById("side-status").textContent = run.status + (run.dead ? " (dead)" : "");
  document.getElementById("side-dot").className = "dot " + run.status;
  document.getElementById("side-details").innerHTML = [
    ["Run ID", run.id], ["Model", run.model], ["Reasoning", run.reasoning_effort],
    ["Started", run.started_at], ["Problem file", run.problem_file],
  ].map(([k, v]) => "<div><strong>" + escapeHtml(k) + "</strong><span>" +
    escapeHtml(v || "—") + "</span></div>").join("");
  document.getElementById("side-attempts").innerHTML = run.attempts.map(a =>
    "<div><strong>" + escapeHtml(a.name) + "</strong><span>" +
    escapeHtml(a.session_id || "no session id") + "</span></div>").join("") ||
    "<div><span>none</span></div>";
  document.getElementById("viewer").hidden = false;
  loadLineage();
}

async function loadLineage() {
  const el = document.getElementById("side-lineage");
  if (!el || state.run.id.startsWith("session:")) return;
  try {
    const lin = await fetchJSON("/api/lineage?run=" + encodeURIComponent(state.run.id));
    const rows = [];
    for (const p of lin.parents) {
      rows.push('<div><strong>parent</strong><span><a href="run.html?run=' +
        encodeURIComponent(p.id) + '">' + escapeHtml(p.id) + "</a></span></div>");
    }
    for (const c of lin.children) {
      rows.push('<div><strong>child</strong><span>' +
        (c.exists ? '<a href="run.html?run=' + encodeURIComponent(c.id) + '">' +
          escapeHtml(c.rel_id) + "</a>" : escapeHtml(c.rel_id) + " (no run yet)") +
        "</span></div>");
    }
    el.innerHTML = rows.join("") || "<div><span>none</span></div>";
  } catch {
    el.innerHTML = "<div><span>unavailable</span></div>";
  }
}

async function boot() {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get("session");
  const missing = document.getElementById("missing");
  if (sessionId) {
    state.run = {
      id: "session:" + sessionId, title: "Codex session", root: "main",
      category: "ad-hoc", status: "session",
      attempts: [{ name: "session", session_id: sessionId, path: null }],
      results: [],
    };
    state.tab = "Transcript";
    renderShell();
    renderTabs();
    drawContent();
    state.timer = setInterval(() => {
      if (state.tab === "Transcript") pollTranscript(false).catch(() => {});
    }, 5000);
    return;
  }
  const runId = params.get("run");
  try {
    state.run = await fetchJSON("/api/runs/" + encodeURIComponent(runId).replace(/%2F/g, "/"));
  } catch (error) {
    missing.hidden = false;
    missing.innerHTML = "Could not load run: " + escapeHtml(error.message) +
      ' — <a href="./">back to all runs</a>';
    return;
  }
  state.attemptIndex = Math.max(0, state.run.attempts.length - 1);
  renderShell();
  renderTabs();
  drawContent();
  state.timer = setInterval(() => {
    if (state.tab === "Transcript" && state.transcript.sessionId) {
      pollTranscript(false).catch(() => {});
    }
  }, 5000);
}

boot();
