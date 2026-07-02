(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
  function hasText(v) { return String(v == null ? "" : v).trim() !== ""; }
  function pillCls(q) { const n = Number(q) || 0; return n >= 70 ? "hi" : n >= 40 ? "mid" : "lo"; }
  function telHref(p) { return "tel:" + String(p).replace(/[^0-9+]/g, ""); }

  async function api(path, opts) { const r = await fetch(path, opts); return r.json(); }
  function post(path, body) {
    return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }

  let leads = [], filter = "undecided", stats = {};
  const list = $("list");

  function matches(l) {
    if (filter === "keep") return l.decision === "keep";
    if (filter === "reject") return l.decision === "reject";
    if (filter === "undecided") return !l.decision;
    return true; // all
  }

  async function load() {
    const res = await api("/api/saved?filter=" + encodeURIComponent(filter));
    leads = res.leads || [];
    stats = res.stats || {};
    renderCounts();
    renderList();
  }

  function renderCounts() {
    $("c-keep").textContent = stats.keep || 0;
    $("c-reject").textContent = stats.reject || 0;
    $("c-left").textContent = stats.undecided || 0;
    const total = stats.total || 0, done = (stats.keep || 0) + (stats.reject || 0);
    $("progress-fill").style.width = (total ? (done / total) * 100 : 0).toFixed(1) + "%";
  }

  function metaHtml(l) {
    const line1 = [], line2 = [];
    if (hasText(l.category)) line1.push('<span style="text-transform:capitalize">' + esc(String(l.category).replace(/_/g, " ")) + "</span>");
    if (hasText(l.address)) line1.push(esc(l.address));
    else if (hasText(l.city)) line1.push(esc(l.city));
    if (hasText(l.phone)) line2.push('<a href="' + esc(telHref(l.phone)) + '">' + esc(l.phone) + "</a>");
    if (hasText(l.email)) line2.push('<a href="mailto:' + esc(l.email) + '">' + esc(l.email) + "</a>");
    if (hasText(l.socials)) line2.push('<a href="' + esc(String(l.socials).split("|")[0]) + '" target="_blank" rel="noopener">social</a>');
    if (hasText(l.verification_status)) line2.push(esc(l.verification_status));
    let h = "";
    if (line1.length) h += '<div class="meta">' + line1.join('<span class="sep">&middot;</span>') + "</div>";
    if (line2.length) h += '<div class="meta">' + line2.join('<span class="sep">&middot;</span>') + "</div>";
    return h;
  }

  function rowHtml(l) {
    const dec = l.decision || "";
    const chip = dec ? ' <span class="chip ' + dec + '">' + esc(dec) + "</span>" : "";
    return (
      '<div class="row ' + dec + '" data-k="' + esc(l.place_id) + '">' +
        '<div class="info">' +
          '<div class="name">' + esc(l.name) +
            ' <span class="pill ' + pillCls(l.quality) + '">' + esc(l.quality) + "</span>" + chip +
          "</div>" + metaHtml(l) +
        "</div>" +
        '<div class="acts">' +
          '<button class="mk keep' + (dec === "keep" ? " on" : "") + '" data-act="keep" title="Keep (K)">&#10003;<span class="lbl">Keep</span></button>' +
          '<button class="mk reject' + (dec === "reject" ? " on" : "") + '" data-act="reject" title="Reject (X)">&#10007;<span class="lbl">Reject</span></button>' +
        "</div>" +
      "</div>"
    );
  }

  function renderList() {
    $("count").textContent = leads.length + (leads.length === 1 ? " lead" : " leads");
    if (!leads.length) {
      list.innerHTML = '<div class="rev-empty"><h2>Nothing here</h2><p>No leads in "' + esc(filter) +
        '". Switch the filter above, or head to the map to pull more.</p></div>';
      return;
    }
    list.innerHTML = leads.map(rowHtml).join("");
  }

  async function mark(k, act) {
    const l = leads.find((x) => x.place_id === k);
    if (!l) return;
    const decision = l.decision === act ? "" : act; // click active again -> undo
    l.decision = decision;
    const res = await post("/api/mark", { place_id: k, decision });
    if (res && res.stats) { stats = res.stats; renderCounts(); }
    const row = list.querySelector('.row[data-k="' + (window.CSS && CSS.escape ? CSS.escape(k) : k) + '"]');
    if (matches(l)) {
      // update in place
      if (row) row.outerHTML = rowHtml(l);
    } else {
      // no longer in this filter -> drop from the list
      leads = leads.filter((x) => x.place_id !== k);
      if (row) row.remove();
      $("count").textContent = leads.length + (leads.length === 1 ? " lead" : " leads");
      if (!leads.length) renderList();
    }
  }

  function initTheme() {
    let theme = null;
    try { theme = localStorage.getItem("lf.theme"); } catch (e) { /* ignore */ }
    if (theme) { try { theme = JSON.parse(theme); } catch (e) { /* raw string */ } }
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
    $("filter").addEventListener("change", (e) => { filter = e.target.value; load(); });
    list.addEventListener("click", (e) => {
      const btn = e.target.closest(".mk");
      if (!btn) return;
      const row = btn.closest(".row");
      if (row) mark(row.dataset.k, btn.dataset.act);
    });
  }

  initTheme();
  wire();
  load();
})();
