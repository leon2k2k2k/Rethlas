import { escapeHtml } from "./util.js";
import { fetchJSON } from "./api.js";

function fmtTime(ts) {
  return ts ? new Date(ts * 1000).toLocaleString() : "";
}

function jobCard(job) {
  const statusCls = { running: "status-chip-running", done: "status-chip-verified",
    failed: "status-chip-no-result" }[job.status] || "";
  const runLink = job.link_run
    ? ' <a href="run.html?run=' + encodeURIComponent(job.link_run) + '">open run</a>' : "";
  return '<details class="ev"' + (job.status === "running" ? " open" : "") + ">" +
    "<summary>" + escapeHtml(job.id) + " — " + escapeHtml(job.type) +
    ' <span class="chip ' + statusCls + '">' + escapeHtml(job.status) + "</span>" +
    (job.exit_code !== null && job.exit_code !== undefined
      ? ' <span class="chip">exit ' + escapeHtml(job.exit_code) + "</span>" : "") +
    "</summary>" +
    '<div class="ev-body"><div class="kv">' +
    "<div><strong>started</strong><span>" + escapeHtml(fmtTime(job.started_at)) + "</span></div>" +
    "<div><strong>command</strong><span>" + escapeHtml(job.cmd || "") + "</span></div>" +
    "<div><strong>params</strong><span>" + escapeHtml(JSON.stringify(job.params)) + "</span></div>" +
    "</div><p>" +
    '<button class="button" data-log="' + escapeHtml(job.id) + '">show log</button> ' +
    (job.status === "running"
      ? '<button class="button" data-stop="' + escapeHtml(job.id) + '">stop</button> ' : "") +
    runLink + "</p>" +
    '<pre class="log" id="log-' + escapeHtml(job.id) + '" hidden style="min-height:120px;max-height:400px;overflow:auto"></pre>' +
    "</div></details>";
}

async function refresh() {
  const jobs = await fetchJSON("/api/jobs");
  const openLogs = new Set([...document.querySelectorAll("pre.log:not([hidden])")]
    .map(el => el.id));
  const openCards = new Set([...document.querySelectorAll("details[data-job][open]")]
    .map(el => el.dataset.job));
  document.getElementById("summary").textContent =
    jobs.length + " job(s), " + jobs.filter(j => j.status === "running").length + " running";
  const list = document.getElementById("job-list");
  list.innerHTML = jobs.map(jobCard).join("") ||
    '<div class="notice">No jobs yet — use the Launch page.</div>';
  list.querySelectorAll("details.ev").forEach((d, i) => {
    d.dataset.job = jobs[i].id;
    if (openCards.has(jobs[i].id)) d.open = true;
  });
  list.querySelectorAll("[data-stop]").forEach(b => b.addEventListener("click", async e => {
    e.preventDefault();
    if (!confirm("Stop job " + b.dataset.stop + "?")) return;
    await fetch("/api/jobs/" + b.dataset.stop + "/stop", { method: "POST" });
    refresh();
  }));
  list.querySelectorAll("[data-log]").forEach(b => b.addEventListener("click", async e => {
    e.preventDefault();
    const pre = document.getElementById("log-" + b.dataset.log);
    pre.hidden = !pre.hidden;
    if (!pre.hidden) {
      pre.textContent = await (await fetch("/api/jobs/" + b.dataset.log + "/log")).text();
      pre.scrollTop = pre.scrollHeight;
    }
  }));
  for (const id of openLogs) {
    const pre = document.getElementById(id);
    if (pre) {
      pre.hidden = false;
      pre.textContent = await (await fetch("/api/jobs/" + id.replace("log-", "") + "/log")).text();
      pre.scrollTop = pre.scrollHeight;
    }
  }
}

refresh().catch(e => {
  document.getElementById("job-list").innerHTML =
    '<div class="notice bad">' + escapeHtml(e.message) + "</div>";
});
setInterval(() => refresh().catch(() => {}), 4000);
