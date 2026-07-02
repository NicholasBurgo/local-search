(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);

  // ---------- state ----------
  function load(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }
  function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* ignore */ } }

  const state = {
    center: null, radius: 10, leads: [], selected: null,
    searched: false,  // true only after a live Overture search (controls the radius ring)
    checked: load("lf.checked", {}) || {},  // offline mirror of "on the list" (by key)
    hideDone: !!load("lf.hide", false),
    cfg: { defaultLocation: "Covington LA", defaultRadius: 10, categories: [] },
  };

  // ---------- helpers ----------
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
  function hasText(v) { return String(v == null ? "" : v).trim() !== ""; }
  function scoreColor(q) { const n = Number(q) || 0; return n >= 70 ? "#2F7D4F" : n >= 40 ? "#A97A0B" : "#8A9187"; }
  function keyOf(l) { return String(l.place_id || "") || ((l.name || "") + "|" + (l.city || "")).toLowerCase(); }
  // "On the list" = has a pipeline stage (server truth), or was just added locally.
  function isListed(l) { return !!l.stage || !!state.checked[keyOf(l)]; }
  function removed(l) { const s = l.verification_status; return s === "REMOVED_HAS_WEBSITE" || s === "REMOVED_CHAIN"; }
  function coordOf(l) { const a = Number(l.latitude), b = Number(l.longitude); return isFinite(a) && isFinite(b) && (a || b) ? [a, b] : null; }
  function telLink(v) { return hasText(v) ? '<a href="tel:' + esc(String(v).replace(/[^0-9+]/g, "")) + '">' + esc(v) + "</a>" : ""; }
  function mailLink(v) { return hasText(v) ? '<a href="mailto:' + esc(v) + '">' + esc(v) + "</a>" : ""; }
  function pillCls(q) { return q >= 70 ? "hi" : q >= 40 ? "mid" : "lo"; }
  function visible() { return state.hideDone ? state.leads.filter((l) => !isListed(l)) : state.leads; }

  // ---------- api ----------
  async function api(path, opts) { const r = await fetch(path, opts); return r.json(); }
  function post(path, body) { return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }

  // ---------- map ----------
  let MAP, LAYER, RING = null, TILES = null;
  const markers = {};
  function initMap() {
    MAP = L.map("map", { preferCanvas: true }).setView([30.47, -90.1], 10);
    LAYER = L.layerGroup().addTo(MAP);
    window.addEventListener("resize", () => MAP.invalidateSize());
  }
  // Basemap follows the theme: detailed OSM for light, CARTO Dark Matter for dark.
  function setTiles(theme) {
    if (TILES) MAP.removeLayer(TILES);
    TILES = theme === "dark"
      ? L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png", { maxZoom: 20, subdomains: "abcd", attribution: "&copy; OpenStreetMap contributors &copy; CARTO" })
      : L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap contributors" });
    TILES.addTo(MAP);
  }
  function leadByKey(k) { return state.leads.find((l) => keyOf(l) === k); }
  function markerStyle(l) {
    const on = state.selected === keyOf(l), listed = isListed(l);
    return {
      radius: on ? 10 : listed ? 8 : 7,
      color: on || listed ? "#0E6B5C" : "#ffffff",  // leads on the list get an accent ring
      weight: on ? 3 : listed ? 2.5 : 1.5,
      fillColor: removed(l) ? "#BBBBBB" : scoreColor(l.quality),
      fillOpacity: removed(l) ? 0.4 : 0.92,
    };
  }
  function popup(l) {
    const c = coordOf(l);
    const dir = c ? "https://www.google.com/maps/dir/?api=1&destination=" + c[0] + "," + c[1] : null;
    const meta = [l.category || "business", l.source, (l.confidence !== "" && l.confidence != null) ? "conf " + l.confidence : null, l.verification_status].filter(Boolean).map(esc).join(" &middot; ");
    let h = '<div class="pop"><div class="pop-head"><span class="pop-name">' + esc(l.name) + '</span><span class="pill ' + pillCls(l.quality) + '">' + esc(l.quality) + "</span></div>";
    h += '<div class="pop-meta">' + meta + "</div>";
    if (hasText(l.address)) h += '<div class="pop-addr">' + esc(l.address) + "</div>";
    const contacts = [];
    if (hasText(l.phone)) contacts.push('<a class="pop-link" href="tel:' + esc(String(l.phone).replace(/[^0-9+]/g, "")) + '">Call ' + esc(l.phone) + "</a>");
    if (hasText(l.email)) contacts.push('<a class="pop-link" href="mailto:' + esc(l.email) + '">' + esc(l.email) + "</a>");
    if (contacts.length) h += '<div class="pop-contact">' + contacts.join("") + "</div>";
    h += '<div class="pop-actions"><button type="button" class="pop-btn primary" data-act="toggle" data-k="' + esc(keyOf(l)) + '">' + (isListed(l) ? "Remove from list" : "+ Add to list") + "</button>";
    if (dir) h += '<a class="pop-btn" href="' + dir + '" target="_blank" rel="noopener">Directions</a>';
    h += "</div></div>";
    return h;
  }
  function renderMap(fit) {
    LAYER.clearLayers();
    for (const k in markers) delete markers[k];
    const pts = [];
    visible().forEach((l) => {
      const c = coordOf(l); if (!c) return; pts.push(c);
      const k = keyOf(l);
      const m = L.circleMarker(c, markerStyle(l));
      m.bindPopup(popup(l), { maxWidth: 280, minWidth: 210, autoPanPadding: [40, 60] });
      m.on("click", () => selectLead(k, true));
      m.addTo(LAYER); markers[k] = m;
    });
    if (RING) { MAP.removeLayer(RING); RING = null; }
    if (state.searched && state.center) RING = L.circle(state.center, { radius: state.radius * 1609.34, color: "#0E6B5C", weight: 1, fill: false, dashArray: "5,5", interactive: false }).addTo(MAP);
    if (fit && pts.length) { try { MAP.fitBounds(L.latLngBounds(pts), { padding: [40, 40], maxZoom: 15 }); } catch (e) { /* ignore */ } }
    else if (fit && state.center) MAP.setView(state.center, 12);
  }

  // ---------- results ----------
  function cardHtml(l) {
    const k = keyOf(l), listed = isListed(l);
    return '<div class="card ' + (state.selected === k ? "sel " : "") + (listed ? "listed " : "") + (removed(l) ? "removed" : "") + '" data-k="' + esc(k) + '">'
      + '<div class="card-top"><span class="card-name">' + esc(l.name) + "</span>"
      + '<span class="pill ' + pillCls(l.quality) + '">' + esc(l.quality) + "</span></div>"
      + '<div class="card-meta">' + esc(l.category || "") + (l.verification_status ? " &middot; " + esc(l.verification_status) : "") + "</div>"
      + (hasText(l.phone) || hasText(l.email) ? '<div class="card-links">' + telLink(l.phone) + " " + mailLink(l.email) + "</div>" : "")
      + (hasText(l.address) ? '<div class="card-addr">' + esc(l.address) + "</div>" : "")
      + '<button type="button" class="add-btn' + (listed ? " on" : "") + '" data-add="' + esc(k) + '">' + (listed ? "✓ On list" : "+ Add to list") + "</button>"
      + "</div>";
  }
  function renderCards() {
    const list = visible();
    $("cards").innerHTML = list.length ? list.map(cardHtml).join("")
      : '<div class="empty">' + (state.leads.length ? "All leads hidden. Uncheck \"Hide listed\"." : "No businesses with no website in this area. Try a bigger radius.") + "</div>";
    const n = state.leads.length, listed = state.leads.filter(isListed).length;
    $("result-count").textContent = n + " lead" + (n === 1 ? "" : "s");
    $("progress-text").textContent = listed ? listed + " on list" : "";
  }
  function renderAll(fit) { renderMap(fit); renderCards(); }

  function selectLead(k, fromMap) {
    state.selected = k;
    renderCards();
    for (const kk in markers) { const l = leadByKey(kk); if (l) markers[kk].setStyle(markerStyle(l)); }
    const m = markers[k];
    if (m) { if (!fromMap) MAP.panTo(m.getLatLng()); m.openPopup(); }
    if (fromMap) { const el = [...$("cards").children].find((e) => e.dataset && e.dataset.k === k); if (el) el.scrollIntoView({ block: "nearest" }); }
  }

  // Add/remove a lead to the review pipeline (stage "new"). Single source of truth:
  // updates state + localStorage mirror + the DB, and re-renders marker/card.
  function setListed(k, on) {
    if (on) state.checked[k] = true; else delete state.checked[k];
    save("lf.checked", state.checked);
    const l = leadByKey(k);
    if (l) l.stage = on ? "new" : null;
    const m = markers[k];
    if (l && m) { m.setStyle(markerStyle(l)); m.setPopupContent(popup(l)); }
    renderCards();
    post("/api/mark", { place_id: k, stage: on ? "new" : "" }).catch(() => {});  // persist (best-effort)
  }
  function toggleListed(k) { setListed(k, !isListed(leadByKey(k) || {})); }

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
    state.searched = true;
    renderAll(true);
    banner(res.count + " businesses with no website on file within " + state.radius + " mi. Add the good ones to your list, then open the List tab.", "ok");
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

  async function doReverify() {
    overlay(true, "Reverifying every stored lead (probing domains)...");
    let res;
    try { res = await post("/api/reverify", {}); } catch (e) { res = { error: String(e) }; }
    overlay(false);
    if (res.error) { banner(res.error, "error"); return; }
    const byId = {}; (res.leads || []).forEach((l) => { if (l.place_id) byId[l.place_id] = l; });
    state.leads.forEach((l) => { const u = byId[l.place_id]; if (u) l.verification_status = u.verification_status; });
    renderAll(false);
    banner("Reverified " + (res.count || 0) + " stored leads.", "ok");
  }

  async function doSaved() {
    overlay(true, "Loading saved leads...");
    let res;
    try { res = await api("/api/saved"); } catch (e) { res = { error: String(e) }; }
    overlay(false);
    if (res.error) { banner(res.error, "error"); return; }
    state.leads = res.leads || []; state.selected = null; state.searched = false;
    const pts = state.leads.map(coordOf).filter(Boolean);
    if (pts.length) { let la = 0, lo = 0; pts.forEach((p) => { la += p[0]; lo += p[1]; }); state.center = [la / pts.length, lo / pts.length]; }
    renderAll(true);
    const st = res.stats || {};
    banner(res.count
      ? res.count + " saved leads from the database (" + (st.listed || 0) + " on your list). Search a location to pull fresh ones."
      : "No saved leads yet. Search a location to pull businesses with no website.", "ok");
  }

  function csvCell(v) { v = v == null ? "" : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
  function exportCSV() {
    if (!state.leads.length) { banner("Nothing to export yet.", "error"); return; }
    const cols = ["stage", "name", "city", "category", "phone", "email", "address", "website_uri", "source", "confidence", "quality", "verification_status", "latitude", "longitude"];
    const lines = [cols.join(",")];
    state.leads.forEach((l) => { lines.push(cols.map((c) => csvCell(c === "stage" ? (l.stage || "") : l[c])).join(",")); });
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
    $("reverify-btn").addEventListener("click", doReverify);
    $("saved-btn").addEventListener("click", doSaved);
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

    // Popup action buttons (delegated: popups are added to the document dynamically).
    document.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-act]"); if (!btn) return;
      if (btn.getAttribute("data-act") === "toggle") toggleListed(btn.getAttribute("data-k"));
    });

    const radius = $("radius");
    radius.addEventListener("input", () => { state.radius = Number(radius.value); $("rlabel").textContent = state.radius + " mi"; if (RING) RING.setRadius(state.radius * 1609.34); });
    radius.addEventListener("change", () => { if (state.center) doSearch({ lat: state.center[0], lon: state.center[1] }); });
    $("cat").addEventListener("change", () => { if (state.center) doSearch({ lat: state.center[0], lon: state.center[1] }); });

    $("hide-done").addEventListener("change", (e) => { state.hideDone = !!e.target.checked; save("lf.hide", state.hideDone); renderAll(false); });

    $("cards").addEventListener("click", (e) => {
      const add = e.target.closest(".add-btn");
      if (add) { e.stopPropagation(); toggleListed(add.dataset.add); return; }
      if (e.target.closest("a")) return;
      const card = e.target.closest(".card"); if (card) selectLead(card.dataset.k, false);
    });

    const themeBtn = $("theme-btn");
    const urlTheme = new URLSearchParams(location.search).get("theme");
    let theme = urlTheme === "dark" || urlTheme === "light" ? urlTheme : load("lf.theme", null);
    if (!theme) { try { theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; } catch (e) { theme = "light"; } }
    function applyTheme(t) { document.documentElement.setAttribute("data-theme", t); setTiles(t); }
    applyTheme(theme);
    themeBtn.addEventListener("click", () => { theme = theme === "dark" ? "light" : "dark"; save("lf.theme", theme); applyTheme(theme); });
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
    await doSaved();  // refresh shows stored leads from the DB; searching is explicit (no re-pull)
    // Optional deep-link: ?focus=<index> opens that lead's detail card on load.
    const focus = new URLSearchParams(location.search).get("focus");
    if (focus !== null) { const l = visible()[Number(focus) || 0]; if (l) selectLead(keyOf(l), false); }
  }

  // Debug/console hooks (harmless): window.leadfinder.map / .markers / .state
  window.leadfinder = { get map() { return MAP; }, get markers() { return markers; }, get state() { return state; }, select: selectLead };
  document.addEventListener("DOMContentLoaded", boot);
})();
