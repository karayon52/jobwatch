(() => {
  const $app = document.getElementById("app");
  const cfg = window.JW_CONFIG || {};
  const detect = () => {
    if (cfg.repo) return cfg.repo;
    const m = location.hostname.match(/^([^.]+)\.github\.io$/);
    const repo = location.pathname.split("/").filter(Boolean)[0];
    return m && repo ? `${m[1]}/${repo}` : null;
  };
  const REPO = detect(), BRANCH = cfg.branch || "main";
  const S = { notes: [], status: { companies: {}, config_errors: [] }, run: null, seen: localStorage.getItem("jw_seen") || "", tab: "inbox", company: "", q: "", kind: "", open: null, openFor: "" };

  const h = (tag, attrs = {}, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v === true) el.setAttribute(k, ""); else if (v !== false && v != null) el.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
    return el;
  };
  const toast = (m) => { const t = document.getElementById("toast"); t.textContent = m; t.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), 2600); };
  const ago = (iso) => {
    if (!iso) return "never"; const s = Math.max(0, (Date.now() - new Date(iso)) / 1000);
    return s < 60 ? "now" : s < 3600 ? Math.floor(s / 60) + "m" : s < 86400 ? Math.floor(s / 3600) + "h" : Math.floor(s / 86400) + "d";
  };
  const dayLabel = (iso) => {
    const d = new Date(iso), n = new Date(), same = (a, b) => a.toDateString() === b.toDateString();
    return same(d, n) ? "Today" : same(d, new Date(n - 864e5)) ? "Yesterday" : d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
  };

  // ---- data: GitHub API first (always fresh), raw CDN as fallback ----
  async function getData(path) {
    const api = `https://api.github.com/repos/${REPO}/contents/${path}?ref=${BRANCH}`;
    try {
      const r = await fetch(api, { headers: { Accept: "application/vnd.github.raw+json" }, cache: "no-store" });
      if (r.ok) return await r.json();
    } catch {}
    const r = await fetch(`https://raw.githubusercontent.com/${REPO}/${BRANCH}/${path}?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status === 404 ? "missing" : "HTTP " + r.status);
    return r.json();
  }
  async function getRun() {
    try {
      const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/collect.yml/runs?per_page=1&status=completed`, { cache: "no-store" });
      if (!r.ok) return null;
      const run = (await r.json()).workflow_runs?.[0];
      return run ? { at: run.updated_at, ok: run.conclusion === "success" } : null;
    } catch { return null; }
  }
  async function refresh(quiet) {
    const [notes, status, run] = await Promise.all([getData("data/notifications.json").catch(() => []), getData("data/status.json").catch(() => S.status), getRun()]);
    S.notes = notes; S.status = status; S.run = run; S.open = null;
    render(); if (!quiet) toast("Updated");
  }

  const unread = () => S.notes.filter((n) => n.ts > S.seen).length;
  const setTitle = () => { const u = unread(); document.title = (u ? `(${u}) ` : "") + "JobWatch"; };
  const edit = `https://github.com/${REPO}/edit/${BRANCH}/companies.yml`;
  const runUrl = `https://github.com/${REPO}/actions/workflows/collect.yml`;

  function statusLine() {
    const r = S.run, mins = r ? (Date.now() - new Date(r.at)) / 60000 : null;
    const cls = !r ? "warn" : !r.ok ? "bad" : mins > 45 ? "warn" : "";
    const text = !r ? "Last check unknown. Turn on Actions if you haven't." : !r.ok ? `Last check failed ${ago(r.at)} ago. See the Actions tab.` : mins > 45 ? `Last check was ${ago(r.at)} ago. GitHub is running late.` : `Last check ${ago(r.at)} ago`;
    return h("div", { class: "status" }, h("span", { class: "dot " + cls }), text);
  }

  function shell(body) {
    const u = unread();
    const link = (id, label, badge) => h("a", { href: "#" + id, "aria-current": S.tab === id ? "page" : null, onclick: () => { S.tab = id; setTimeout(render) } }, label, badge ? h("span", { class: "count" }, badge) : null);
    $app.replaceChildren(
      h("header", { class: "top" }, h("div", { class: "wrap" }, h("div", { class: "brand" }, h("span", { class: "dot" }), "JobWatch"),
        h("nav", {}, link("inbox", "Inbox", u || null), link("jobs", "Open jobs"), link("companies", "Companies")),
        h("button", { onclick: () => refresh().catch((e) => toast(e.message)) }, "Refresh"))),
      h("main", { class: "wrap" }, body));
    setTitle();
  }

  function inbox() {
    const companies = [...new Set(S.notes.map((n) => n.company))].sort();
    const q = S.q.toLowerCase();
    const list = S.notes.filter((n) => (!S.company || n.company === S.company) && (!S.kind || n.kind === S.kind) &&
      (!q || `${n.title} ${n.location} ${n.company}`.toLowerCase().includes(q)));
    const nodes = []; let last = "";
    for (const n of list) {
      const d = dayLabel(n.ts); if (d !== last) { nodes.push(h("div", { class: "day" }, d)); last = d; }
      nodes.push(h("div", { class: "row" + (n.ts > S.seen ? " unread" : "") },
        h("span", { class: "u" }), h("span", { class: "t" }, ago(n.ts)),
        h("div", { class: "main" }, h("a", { class: "title", href: n.url, target: "_blank", rel: "noopener noreferrer" }, n.title),
          h("span", { class: "meta" }, [n.company, n.location, n.department].filter(Boolean).join(" · "))),
        h("span", { class: "tagcell" }, n.kind === "updated" ? h("span", { class: "tag warn" }, "updated") : h("span", { class: "tag" }, "new"))));
    }
    const sel = h("select", { onchange: (e) => { S.company = e.target.value; render(); } }, h("option", { value: "" }, "All companies"), ...companies.map((c) => h("option", { value: c, selected: c === S.company }, c)));
    const kind = h("select", { onchange: (e) => { S.kind = e.target.value; render(); } }, h("option", { value: "" }, "New and updated"), h("option", { value: "new", selected: S.kind === "new" }, "New only"), h("option", { value: "updated", selected: S.kind === "updated" }, "Updated only"));
    const search = h("input", { type: "search", placeholder: "Search titles and locations", value: S.q, oninput: (e) => { S.q = e.target.value; const pos = e.target.selectionStart; render(); const el = document.querySelector("input[type=search]"); el.focus(); el.setSelectionRange(pos, pos); } });
    shell([
      h("h1", {}, "Inbox"), h("p", { class: "sub" }, "Every new or updated posting that matched your watchlist, newest first."), statusLine(),
      ...(Object.keys(S.status.companies).length === 0 && !S.status.config_errors.length ? [h("div", { class: "notice" }, "No companies are being checked yet. ", h("a", { href: edit, target: "_blank", rel: "noopener" }, "Add some in companies.yml"), ".")] : []),
      h("div", { class: "toolbar" }, search, sel, kind, h("button", { onclick: () => { S.seen = new Date().toISOString().replace(/\.\d+Z$/, "Z"); localStorage.setItem("jw_seen", S.seen); render(); } }, "Mark all read")),
      nodes.length ? nodes : h("div", { class: "empty" }, h("strong", {}, S.notes.length ? "Nothing matches that filter." : "Nothing here yet."),
        S.notes.length ? "Clear the search or filters to see everything." : "The first check saves each company's current jobs quietly. Alerts appear here as soon as something new is posted. Browse what's open now under Open jobs.")]);
  }

  async function jobs() {
    const keys = Object.keys(S.status.companies);
    if (!S.openFor && keys.length) S.openFor = keys[0];
    const sel = h("select", { onchange: (e) => { S.openFor = e.target.value; S.open = null; render(); } }, ...keys.map((k) => h("option", { value: k, selected: k === S.openFor }, `${S.status.companies[k].name} (${S.status.companies[k].open})`)));
    const holder = h("div");
    shell([h("h1", {}, "Open jobs"), h("p", { class: "sub" }, "Everything currently open at each company, newest first."), statusLine(),
      keys.length ? h("div", { class: "toolbar" }, sel, h("input", { type: "search", placeholder: "Search", value: S.q, oninput: (e) => { S.q = e.target.value; draw(); } })) : null, holder]);
    const draw = () => {
      if (!keys.length) return holder.replaceChildren(h("div", { class: "empty" }, h("strong", {}, "No companies yet."), "Add some in companies.yml."));
      if (!S.open) return holder.replaceChildren(h("div", { class: "empty" }, "Loading…"));
      const q = S.q.toLowerCase();
      const rows = Object.values(S.open.jobs).filter((j) => !j.closed_at && (!q || `${j.title} ${j.location} ${j.department}`.toLowerCase().includes(q))).sort((a, b) => b.first_seen.localeCompare(a.first_seen));
      holder.replaceChildren(...(rows.length ? rows.slice(0, 400).map((j) => h("div", { class: "row plain" }, h("span", { class: "t" }, ago(j.first_seen)),
        h("div", { class: "main" }, h("a", { class: "title", href: j.url, target: "_blank", rel: "noopener noreferrer" }, j.title), h("span", { class: "meta" }, [j.location, j.department].filter(Boolean).join(" · "))), h("span"))) : [h("div", { class: "empty" }, "No open jobs match.")]));
    };
    draw();
    if (keys.length && !S.open) { try { S.open = await getData(`data/companies/${S.openFor}.json`); } catch { S.open = { jobs: {} }; } draw(); }
  }

  function companies() {
    const rows = Object.entries(S.status.companies).map(([k, c]) => h("div", { class: "item" },
      h("div", {}, h("div", { class: "name" }, h("a", { href: c.url, target: "_blank", rel: "noopener noreferrer" }, c.name), " ", c.ok ? null : h("span", { class: "tag bad" }, "problem")),
        h("div", { class: "meta" }, `${c.source} · ${c.open} open roles`), !c.ok && h("div", { class: "meta", style: "color:var(--bad)" }, `${c.error} (since ${new Date(c.failing_since).toLocaleString()})`))));
    shell([h("h1", {}, "Companies"), h("p", { class: "sub" }, "The companies being checked."), statusLine(),
      h("div", { class: "actions" }, h("a", { class: "btn primary", href: edit, target: "_blank", rel: "noopener" }, "Edit watchlist"), h("a", { class: "btn", href: runUrl, target: "_blank", rel: "noopener" }, "Run a check now")),
      ...S.status.config_errors.map((e) => h("div", { class: "notice bad" }, e)),
      rows.length ? rows : h("div", { class: "empty" }, h("strong", {}, "No companies yet."), "Open the watchlist and add a careers link.")]);
  }

  function render() { S.tab === "jobs" ? jobs() : S.tab === "companies" ? companies() : inbox(); }

  if (!REPO) {
    $app.replaceChildren(h("main", { class: "wrap" }, h("h1", {}, "JobWatch"), h("div", { class: "notice bad" }, "This page can't tell which GitHub repository to read. Open docs/config.js and set repo to \"your-username/your-repo\".")));
    return;
  }
  S.tab = ["inbox", "jobs", "companies"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "inbox";
  window.addEventListener("hashchange", () => { const t = location.hash.slice(1); if (["inbox", "jobs", "companies"].includes(t)) { S.tab = t; render(); } });
  shell(h("div", { class: "empty" }, "Loading…"));
  refresh(true).catch((e) => toast(e.message));
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") refresh(true).catch(() => {}); });
})();
