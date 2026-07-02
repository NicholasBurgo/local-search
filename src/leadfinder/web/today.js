// The "Today" queue: follow-ups due/overdue + active deals gone quiet. Each row
// links to the shared lead-detail drawer for logging; quick snooze/dismiss inline.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
  function hasText(v) { return String(v == null ? "" : v).trim() !== ""; }
  async function api(path, opts) { const r = await fetch(path, opts); return r.json(); }
  function post(path, body) {
    return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }
  const LD = window.LeadDetail;
  const STAGE_LABEL = {
    new: "New", contacted: "Contacted", qualified: "Qualified",
    proposal_sent: "Proposal Sent", negotiating: "Negotiating",
  };

  let data = { due: [], stale: [], stale_days: 3 };

  async function load() { data = await api("/api/today"); render(); }

  function contactLine(l) {
    const c = [];
    if (hasText(l.phone)) c.push('<a href="tel:' + esc(String(l.phone).replace(/[^0-9+]/g, "")) + '">' + esc(l.phone) + "</a>");
    if (hasText(l.email)) c.push('<a href="mailto:' + esc(l.email) + '">' + esc(l.email) + "</a>");
    if (hasText(l.address)) c.push(esc(l.address));
    return c.join(" &middot; ");
  }

  function rowHtml(l, kind) {
    const stage = '<span class="qstage">' + esc(STAGE_LABEL[l.stage] || l.stage) + "</span>";
    let when = "", whenCls = "";
    if (kind === "due") {
      const fs = LD.followState(l.next_follow_up); when = fs.text; whenCls = fs.due ? " due" : "";
    } else {
      when = l.last_activity ? "Last touch " + LD.relTime(l.last_activity) : "Never contacted";
    }
    const acts = kind === "due"
      ? '<button class="btn" data-act="log" type="button">Log</button>' +
        '<button class="btn ghost" data-act="snooze" type="button">Snooze</button>' +
        '<button class="btn ghost" data-act="dismiss" type="button">Dismiss</button>'
      : '<button class="btn" data-act="log" type="button">Log</button>' +
        '<button class="btn ghost" data-act="snooze" type="button">Remind +3d</button>';
    const meta = contactLine(l);
    return (
      '<div class="qrow' + (kind === "due" && whenCls ? " overdue" : "") + '" data-k="' + esc(l.place_id) + '">' +
        '<div class="qinfo">' +
          '<div class="qname" data-act="open">' + esc(l.name) + " " + stage + "</div>" +
          (meta ? '<div class="qmeta">' + meta + "</div>" : "") +
          '<div class="qwhen' + whenCls + '">' + esc(when) + "</div>" +
        "</div>" +
        '<div class="qacts">' + acts + "</div>" +
      "</div>"
    );
  }

  function section(title, sub, rows, kind) {
    if (!rows.length) return "";
    return '<div class="today-sec"><h2>' + esc(title) + '</h2><div class="sub">' + esc(sub) + "</div>" +
      rows.map((l) => rowHtml(l, kind)).join("") + "</div>";
  }

  function render() {
    const due = data.due || [], stale = data.stale || [];
    $("summary").innerHTML =
      '<div class="tsum"><div class="tsum-val' + (due.length ? " due" : "") + '">' + due.length +
        '</div><div class="tsum-label">Follow-ups due</div></div>' +
      '<div class="tsum"><div class="tsum-val">' + stale.length +
        '</div><div class="tsum-label">Going stale</div></div>' +
      '<div class="tsum"><div class="tsum-val">' + (due.length + stale.length) +
        '</div><div class="tsum-label">To work today</div></div>';
    if (!due.length && !stale.length) {
      $("content").innerHTML = '<div class="today-done"><h2>Inbox zero</h2><p>No follow-ups due and nothing going stale. Go find more leads.</p></div>';
      return;
    }
    $("content").innerHTML =
      section("Follow-ups due", "Reminders you set that are due or overdue.", due, "due") +
      section("Going stale", "Open deals with no follow-up and no touch in " + (data.stale_days || 3) + "+ days.", stale, "stale");
  }

  function leadByKey(k) { return (data.due || []).concat(data.stale || []).find((l) => l.place_id === k); }

  async function act(k, action) {
    const l = leadByKey(k); if (!l) return;
    if (action === "open" || action === "log") { LD.open(l, () => load()); return; }
    if (action === "snooze") { await post("/api/follow-up", { place_id: k, days: 3 }); load(); return; }
    if (action === "dismiss") { await post("/api/follow-up", { place_id: k, clear: true }); load(); return; }
  }

  function initTheme() {
    let theme = null;
    try { theme = localStorage.getItem("lf.theme"); } catch (e) { /* ignore */ }
    if (theme) { try { theme = JSON.parse(theme); } catch (e) { /* raw */ } }
    if (!theme) {
      try { theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; }
      catch (e) { theme = "light"; }
    }
    document.documentElement.setAttribute("data-theme", theme);
    $("theme-btn").addEventListener("click", () => {
      theme = theme === "dark" ? "light" : "dark";
      try { localStorage.setItem("lf.theme", JSON.stringify(theme)); } catch (e) { /* ignore */ }
      document.documentElement.setAttribute("data-theme", theme);
    });
  }

  function wire() {
    $("content").addEventListener("click", (e) => {
      if (e.target.closest("a")) return;  // let tel:/mailto: work
      const btn = e.target.closest("[data-act]"); if (!btn) return;
      const row = e.target.closest(".qrow"); if (!row) return;
      act(row.dataset.k, btn.dataset.act);
    });
    $("refresh-btn").addEventListener("click", load);
  }

  initTheme();
  wire();
  load();
})();
