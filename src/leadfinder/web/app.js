(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);

  // ---------- state ----------
  function load(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }
  function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }

  const state = {
    center: null, radius: 10, leads: [], selected: null,
    checked: load("lf.checked", {}) || {},
    hideDone: !!load("lf.hide", false),
    cfg: { defaultLocation: "Covington LA", defaultRadius: 10, categories: [] },
  };

  // ---------- helpers ----------
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
  function hasText(v) { return String(v == null ? "" : v).trim() !== ""; }
  function scoreColor(q) { const n = Number(q) || 0; return n >= 70 ? "#2F7D4F" : n >= 40 ? "#A97A0B" : "#8A9187"; }
  function keyOf(l) { return String(l.place_id || "") || ((l.name || "") + "|" + (l.city || "")).toLowerCase(); }
  function isDone(l) { return !!state.checked[keyOf(l)]; }
  function removed(l) { const s = l.verification_status; return s === "REMOVED_HAS_WEBSITE" || s === "REMOVED_CHAIN"; }
  function coordOf(l) { const a = Number(l.latitude), b = Number(l.longitude); return isFinite(a) && isFinite(b) && (a || b) ? [a, b] : null; }
  function telLink(v) { return hasText(v) ? '<a href="tel:' + esc(String(v).replace(/[^0-9+]/g, "")) + '">' + esc(v) + "</a>" : ""; }
  function mailLink(v) { return hasText(v) ? '<a href="mailto:' + esc(v) + '">' + esc(v) + "</a>" : ""; }
  function pillCls(q) { return q >= 70 ? "hi" : q >= 40 ? "mid" : "lo"; }
  function visible() { return state.hideDone ? state.leads.filter((l) => !isDone(l)) : state.leads; }

  // ---------- api ----------
  async function api(path, opts) { const r = await fetch(path, opts); return r.json(); }
  function post(path, body) { return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }

  // ---------- map ----------
  let MAP, LAYER, RING = null;
  const markers = {};
  function initMap() {
    MAP = L.map("map", { preferCanvas: true }).setView([30.47, -90.1], 10);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap contributors" }).addTo(MAP);
    LAYER = L.layerGroup().addTo(MAP);
    window.addEventListener("resize", () => MAP.invalidateSize());
  }
  function popup(l) {
    const b = ["<strong>" + esc(l.name) + "</strong>"];
    b.push('<div class="muted">' + esc(l.category || "") + " &middot; score " + esc(l.quality) + (l.verification_status ? " &middot; " + esc(l.verification_status) : "") + "</div>");
    if (hasText(l.phone)) b.push("<div>" + telLink(l.phone) + "</div>");
    if (hasText(l.email)) b.push("<div>" + mailLink(l.email) + "</div>");
    if (hasText(l.address)) b.push('<div class="muted">' + esc(l.address) + "</div>");
    return b.join("");
  }
  function renderMap(fit) {
    LAYER.clearLayers();
    for (const k in markers) delete markers[k];
    const pts = [];
    visible().forEach((l) => {
      const c = coordOf(l); if (!c) return; pts.push(c);
      const k = keyOf(l), sel = state.selected === k, faded = isDone(l) || removed(l);
      const m = L.circleMarker(c, { radius: sel ? 9 : 7, color: sel ? "#0E6B5C" : "#ffffff", weight: sel ? 2.5 : 1.5, fillColor: removed(l) ? "#BBBBBB" : scoreColor(l.quality), fillOpacity: faded ? 0.4 : 0.92 });
      m.bindPopup(popup(l)); m.on("click", () => selectLead(k, true)); m.addTo(LAYER); markers[k] = m;
    });
    if (RING) { MAP.removeLayer(RING); RING = null; }
    if (state.center) RING = L.circle(state.center, { radius: state.radius * 1609.34, color: "#0E6B5C", weight: 1, fill: false, dashArray: "5,5" }).addTo(MAP);
    if (fit && pts.length) { try { MAP.fitBounds(L.latLngBounds(pts), { padding: [40, 40], maxZoom: 15 }); } catch (e) {} }
    else if (fit && state.center) MAP.setView(state.center, 12);
  }

  // ---------- results ----------
  function cardHtml(l) {
    const k = keyOf(l), done = isDone(l);
    return '<div class="card ' + (state.selected === k ? "sel " : "") + (done ? "done " : "") + (removed(l) ? "removed" : "") + '" data-k="' + esc(k) + '">'
      + '<div class="card-top"><input type="checkbox" class="chk" data-k="' + esc(k) + '"' + (done ? " checked" : "") + ' aria-label="Mark contacted">'
      + '<span class="card-name">' + esc(l.name) + "</span>"
      + '<span class="pill ' + pillCls(l.quality) + '">' + esc(l.quality) + "</span></div>"
      + '<div class="card-meta">' + esc(l.category || "") + (l.verification_status ? " &middot; " + esc(l.verification_status) : "") + "</div>"
      + (hasText(l.phone) || hasText(l.email) ? '<div class="card-links">' + telLink(l.phone) + " " + mailLink(l.email) + "</div>" : "")
      + (hasText(l.address) ? '<div class="card-addr">' + esc(l.address) + "</div>" : "")
      + "</div>";
  }
  function renderCards() {
    const list = visible();
    $("cards").innerHTML = list.length ? list.map(cardHtml).join("")
      : '<div class="empty">' + (state.leads.length ? "All leads hidden. Uncheck \"Hide contacted\"." : "No businesses with no website in this area. Try a bigger radius.") + "</div>";
    const n = state.leads.length, done = state.leads.filter(isDone).length;
    $("result-count").textContent = n + " lead" + (n === 1 ? "" : "s");
    $("progress-text").textContent = n ? done + " / " + n + " contacted" : "";
  }
  function renderAll(fit) { renderMap(fit); renderCards(); }

  function selectLead(k, fromMap) {
    state.selected = k;
    renderCards();
    for (const kk in markers) { const m = markers[kk], on = kk === k; m.setStyle({ radius: on ? 9 : 7, color: on ? "#0E6B5C" : "#ffffff", weight: on ? 2.5 : 1.5 }); }
    const m = markers[k];
    if (m) { if (!fromMap) MAP.panTo(m.getLatLng()); m.openPopup(); }
    if (fromMap) { const el = [...$("cards").children].find((e) => e.dataset && e.dataset.k === k); if (el) el.scrollIntoView({ block: "nearest" }); }
  }

  // ---------- overlay / banner ----------
  function overlay(on, text) { $("overlay").hidden = !on; if (text) $("overlay-text").textContent = text; }
  function banner(msg, kind) { const b = $("banner"); b.textContent = msg; b.className = "banner " + (kind || "ok"); b.hidden = !msg; }

  // ---------- actions ----------
  function catValue() { const v = $("cat").value; return v ? [v] : null; }

  async function doSearch(body) {
    body = Object.assign({ radius_miles: state.radius, categories: catValue() }, body || {});
    if (!body.q && !("lat" in body)) { body.q = $("loc").value.trim(); }
    if (!body.q && !("lat" in body)) { banner("Enter a location to search.", "error"); return; }
    overlay(true, "Searching " + (body.q || "this area") + " (" + state.radius + " mi)...");
    banner("");
    let res;
    try { res = await post("/api/search", body); } catch (e) { res = { error: String(e) }; }
    overlay(false);
    if (res.error) { banner(res.error, "error"); return; }
    state.center = res.center; state.leads = res.leads || []; state.selected = null;
    renderAll(true);
    banner(res.count + " businesses with no website on file within " + state.radius + " mi. Click Verify to drop any that actually have a site.", "ok");
  }

  async function doVerify() {
    if (!state.leads.length) { banner("Search first, then verify.", "error"); return; }
    overlay(true, "Verifying " + state.leads.length + " leads (probing domains)...");
    let res;
    try { res = await post("/api/verify", { leads: state.leads }); } catch (e) { res = { error: String(e) }; }
    overlay(false);
    if (res.error) { banner(res.error, "error"); return; }
    state.leads = res.leads || []; renderAll(false);
    const kept = state.leads.filter((l) => !removed(l)).length;
    banner("Verified: " + kept + " confirmed no-website, " + (state.leads.length - kept) + " removed (had a live site).", "ok");
  }

  function csvCell(v) { v = v == null ? "" : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
  function exportCSV() {
    if (!state.leads.length) { banner("Nothing to export yet.", "error"); return; }
    const cols = ["contacted", "name", "city", "category", "phone", "email", "address", "website_uri", "source", "confidence", "quality", "verification_status", "latitude", "longitude"];
    const lines = [cols.join(",")];
    state.leads.forEach((l) => { const rec = Object.assign({ contacted: isDone(l) ? "yes" : "" }, l); lines.push(cols.map((c) => csvCell(rec[c])).join(",")); });
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "leadfinder_leads.csv";
    document.body.appendChild(a); a.click(); a.remove();
  }

  // ---------- autocomplete ----------
  let suggestTimer = null, suggestions = [];
  function hideSuggest() { $("suggest").hidden = true; }
  function renderSuggest() {
    const ul = $("suggest");
    if (!suggestions.length) { ul.hidden = true; return; }
    ul.innerHTML = suggestions.map((s, i) => '<li data-i="' + i + '">' + esc(s.label) + "</li>").join("");
    ul.hidden = false;
  }
  async function fetchSuggest(q) {
    let res; try { res = await api("/api/suggest?q=" + encodeURIComponent(q)); } catch (e) { return; }
    suggestions = res.suggestions || []; renderSuggest();
  }

  // ---------- wiring ----------
  function wire() {
    $("search-btn").addEventListener("click", () => { hideSuggest(); doSearch(); });
    $("verify-btn").addEventListener("click", doVerify);
    $("export-btn").addEventListener("click", exportCSV);

    const loc = $("loc");
    loc.addEventListener("input", () => {
      const q = loc.value.trim();
      clearTimeout(suggestTimer);
      if (q.length < 3) { hideSuggest(); return; }
      suggestTimer = setTimeout(() => fetchSuggest(q), 250);
    });
    loc.addEventListener("keydown", (e) => { if (e.key === "Enter") { hideSuggest(); doSearch(); } if (e.key === "Escape") hideSuggest(); });
    $("suggest").addEventListener("click", (e) => {
      const li = e.target.closest("li"); if (!li) return;
      const s = suggestions[Number(li.dataset.i)]; if (!s) return;
      loc.value = s.label; hideSuggest(); doSearch({ lat: s.lat, lon: s.lon });
    });
    document.addEventListener("click", (e) => { if (!e.target.closest(".search")) hideSuggest(); });

    const radius = $("radius");
    radius.addEventListener("input", () => { state.radius = Number(radius.value); $("rlabel").textContent = state.radius + " mi"; if (RING) RING.setRadius(state.radius * 1609.34); });
    radius.addEventListener("change", () => { if (state.center) doSearch({ lat: state.center[0], lon: state.center[1] }); });
    $("cat").addEventListener("change", () => { if (state.center) doSearch({ lat: state.center[0], lon: state.center[1] }); });

    $("hide-done").addEventListener("change", (e) => { state.hideDone = !!e.target.checked; save("lf.hide", state.hideDone); renderAll(false); });

    $("cards").addEventListener("click", (e) => {
      const chk = e.target.closest(".chk");
      if (chk) { const k = chk.dataset.k; if (chk.checked) state.checked[k] = true; else delete state.checked[k]; save("lf.checked", state.checked); renderAll(false); return; }
      if (e.target.closest("a")) return;
      const card = e.target.closest(".card"); if (card) selectLead(card.dataset.k, false);
    });

    const themeBtn = $("theme-btn");
    let theme = load("lf.theme", null);
    if (!theme) { try { theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; } catch (e) { theme = "light"; } }
    document.documentElement.setAttribute("data-theme", theme);
    themeBtn.addEventListener("click", () => { theme = theme === "dark" ? "light" : "dark"; save("lf.theme", theme); document.documentElement.setAttribute("data-theme", theme); });
  }

  async function boot() {
    initMap(); wire();
    try {
      const cfg = await api("/api/config");
      state.cfg = cfg;
      state.radius = cfg.defaultRadius || 10;
      $("radius").value = state.radius; $("rlabel").textContent = state.radius + " mi";
      $("loc").value = cfg.defaultLocation || "";
      const cat = $("cat");
      (cfg.categories || []).forEach((c) => { const o = document.createElement("option"); o.value = c.key; o.textContent = c.label; cat.appendChild(o); });
    } catch (e) { /* keep defaults */ }
    $("hide-done").checked = state.hideDone;
    setTimeout(() => MAP.invalidateSize(), 200);
    doSearch();
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
