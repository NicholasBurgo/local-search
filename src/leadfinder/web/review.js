(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
  function hasText(v) { return String(v == null ? "" : v).trim() !== ""; }
  function pillCls(q) { const n = Number(q) || 0; return n >= 70 ? "hi" : n >= 40 ? "mid" : "lo"; }

  async function api(path, opts) { const r = await fetch(path, opts); return r.json(); }
  function post(path, body) { return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }

  let leads = [], idx = 0, filter = "undecided", stats = {};

  async function load() {
    const res = await api("/api/saved?filter=" + encodeURIComponent(filter));
    leads = res.leads || [];
    stats = res.stats || {};
    idx = 0;
    renderCounts();
    render();
  }

  function renderCounts() {
    $("c-keep").textContent = stats.keep || 0;
    $("c-reject").textContent = stats.reject || 0;
    $("c-left").textContent = stats.undecided || 0;
    const total = stats.total || 0, done = (stats.keep || 0) + (stats.reject || 0);
    $("progress-fill").style.width = (total ? (done / total) * 100 : 0).toFixed(1) + "%";
  }

  function current() { return leads[idx]; }

  function render() {
    const l = current();
    $("pos").textContent = leads.length ? (idx + 1) + " of " + leads.length : "";
    if (!l) {
      $("rev-card").innerHTML = '<div class="rev-done"><h2>All done</h2><p>No leads left in "' + esc(filter) + '". Switch the filter above, or head back to the map to find more.</p></div>';
      return;
    }
    const meta = [l.category || "business", l.source, (l.confidence !== "" && l.confidence != null) ? "conf " + l.confidence : null, l.verification_status].filter(Boolean).map(esc).join(" &middot; ");
    let h = '<div class="rev-name">' + esc(l.name) + ' <span class="pill ' + pillCls(l.quality) + '">' + esc(l.quality) + "</span>";
    if (l.decision) h += ' <span class="chip">' + esc(l.decision) + "</span>";
    h += "</div><div class=\"rev-meta\">" + meta + "</div>";
    if (hasText(l.address)) h += '<div class="rev-row"><span class="rev-label">Address</span>' + esc(l.address) + "</div>";
    if (hasText(l.phone)) h += '<div class="rev-row"><span class="rev-label">Phone</span><a href="tel:' + esc(String(l.phone).replace(/[^0-9+]/g, "")) + '">' + esc(l.phone) + "</a></div>";
    if (hasText(l.email)) h += '<div class="rev-row"><span class="rev-label">Email</span><a href="mailto:' + esc(l.email) + '">' + esc(l.email) + "</a></div>";
    if (hasText(l.socials)) h += '<div class="rev-row"><span class="rev-label">Socials</span>' + esc(String(l.socials).split("|")[0]) + "</div>";
    if (hasText(l.city)) h += '<div class="rev-row"><span class="rev-label">Area</span>' + esc(l.city) + "</div>";
    $("rev-card").innerHTML = h;
  }

  async function decide(decision) {
    const l = current();
    if (!l) return;
    await post("/api/mark", { place_id: l.place_id, decision });
    const was = l.decision;
    l.decision = decision;
    // keep the counts in sync locally (server is source of truth on next load)
    if (was !== decision) {
      if (was === "keep") stats.keep = Math.max(0, (stats.keep || 0) - 1);
      if (was === "reject") stats.reject = Math.max(0, (stats.reject || 0) - 1);
      if (!was) stats.undecided = Math.max(0, (stats.undecided || 0) - 1);
      if (decision === "keep") stats.keep = (stats.keep || 0) + 1;
      if (decision === "reject") stats.reject = (stats.reject || 0) + 1;
      renderCounts();
    }
    if (filter === "undecided") {
      leads.splice(idx, 1);
      if (idx >= leads.length) idx = Math.max(0, leads.length - 1);
    } else if (idx < leads.length - 1) {
      idx++;
    }
    render();
  }

  function skip() { if (leads.length) { idx = (idx + 1) % leads.length; render(); } }
  function prev() { if (idx > 0) { idx--; render(); } }

  function initTheme() {
    let theme = null;
    try { theme = localStorage.getItem("lf.theme"); } catch (e) {}
    if (theme) { try { theme = JSON.parse(theme); } catch (e) {} }
    if (!theme) { try { theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; } catch (e) { theme = "light"; } }
    document.documentElement.setAttribute("data-theme", theme);
    $("theme-btn").addEventListener("click", () => {
      theme = theme === "dark" ? "light" : "dark";
      try { localStorage.setItem("lf.theme", JSON.stringify(theme)); } catch (e) {}
      document.documentElement.setAttribute("data-theme", theme);
    });
  }

  function wire() {
    $("keep-btn").addEventListener("click", () => decide("keep"));
    $("reject-btn").addEventListener("click", () => decide("reject"));
    $("skip-btn").addEventListener("click", skip);
    $("prev-btn").addEventListener("click", prev);
    $("filter").addEventListener("change", (e) => { filter = e.target.value; load(); });
    document.addEventListener("keydown", (e) => {
      if (e.target && (e.target.tagName === "SELECT" || e.target.tagName === "INPUT")) return;
      const k = e.key;
      if (k === "k" || k === "K" || k === "ArrowRight") { e.preventDefault(); decide("keep"); }
      else if (k === "x" || k === "X" || k === "ArrowLeft") { e.preventDefault(); decide("reject"); }
      else if (k === "s" || k === "S" || k === " ") { e.preventDefault(); skip(); }
      else if (k === "Backspace") { e.preventDefault(); prev(); }
    });
  }

  initTheme();
  wire();
  load();
})();
