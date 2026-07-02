// Shared lead-detail drawer: contact info, activity timeline, one-click logging,
// and follow-up scheduling. Exposed as window.LeadDetail.open(lead, onChange).
// onChange(updatedLead) fires after a log/follow-up change so the host page can
// refresh (e.g. re-pull the board or drop a row from the queue).
(function () {
  "use strict";
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
  function hasText(v) { return String(v == null ? "" : v).trim() !== ""; }
  async function api(path, opts) { const r = await fetch(path, opts); return r.json(); }
  function post(path, body) {
    return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }

  const TYPES = [["call", "Call"], ["email", "Email"], ["note", "Note"], ["meeting", "Meeting"]];
  const STAGE_LABEL = {
    new: "New", contacted: "Contacted", qualified: "Qualified",
    proposal_sent: "Proposal Sent", negotiating: "Negotiating", won: "Won", lost: "Lost",
  };

  function relTime(iso) {
    if (!iso) return "";
    const t = new Date(iso).getTime();
    if (isNaN(t)) return "";
    const s = Math.round((Date.now() - t) / 1000);
    if (s < 60) return "just now";
    const m = Math.round(s / 60); if (m < 60) return m + "m ago";
    const h = Math.round(m / 60); if (h < 24) return h + "h ago";
    const d = Math.round(h / 24); if (d < 30) return d + "d ago";
    return new Date(iso).toLocaleDateString();
  }

  // Days from now to a follow-up date (negative = overdue) + a human phrase.
  function followState(iso) {
    if (!iso) return { text: "No follow-up scheduled", due: false };
    const days = Math.round((new Date(iso).getTime() - Date.now()) / 86400000);
    if (days < 0) return { text: "Follow-up overdue by " + -days + "d", due: true };
    if (days === 0) return { text: "Follow-up due today", due: true };
    if (days === 1) return { text: "Follow-up tomorrow", due: false };
    return { text: "Follow-up in " + days + "d", due: false };
  }

  const CSS = `
  .lf-scrim { position:fixed; inset:0; background:rgba(0,0,0,.38); z-index:2000; opacity:0; transition:opacity .15s; }
  .lf-scrim.open { opacity:1; }
  .lf-drawer { position:fixed; top:0; right:0; height:100%; width:430px; max-width:94vw; background:var(--card);
    border-left:1px solid var(--line); box-shadow:-10px 0 34px rgba(0,0,0,.22); z-index:2001;
    transform:translateX(100%); transition:transform .18s ease; display:flex; flex-direction:column; }
  .lf-drawer.open { transform:translateX(0); }
  .lf-dh { padding:16px 18px; border-bottom:1px solid var(--line); }
  .lf-dh-top { display:flex; align-items:flex-start; gap:10px; }
  .lf-dname { font-size:18px; font-weight:700; flex:1; line-height:1.25; }
  .lf-dx { border:none; background:none; color:var(--muted); font-size:22px; line-height:1; cursor:pointer; padding:0 2px; }
  .lf-dx:hover { color:var(--ink); }
  .lf-dmeta { color:var(--muted); font-size:12.5px; margin-top:5px; text-transform:capitalize; }
  .lf-dcontacts { display:flex; gap:16px; flex-wrap:wrap; margin-top:9px; font-size:13px; }
  .lf-dcontacts a { color:var(--accent); text-decoration:none; }
  .lf-dcontacts a:hover { text-decoration:underline; }
  .lf-dbody { flex:1; overflow-y:auto; padding:16px 18px 28px; }
  .lf-label { font-size:11px; text-transform:uppercase; letter-spacing:.6px; color:var(--muted); font-weight:600; margin:0 0 8px; }
  .lf-fu { background:var(--bg); border:1px solid var(--line); border-radius:11px; padding:11px 13px; margin-bottom:16px; }
  .lf-fu-state { font-size:13.5px; font-weight:600; margin-bottom:9px; }
  .lf-fu-state.due { color:var(--mid); }
  .lf-fu-btns, .lf-types { display:flex; gap:6px; flex-wrap:wrap; }
  .lf-chip { font-size:12px; padding:6px 11px; border-radius:8px; border:1px solid var(--line); background:var(--card); color:var(--muted); cursor:pointer; }
  .lf-chip:hover { color:var(--ink); border-color:var(--muted); }
  .lf-log { border:1px solid var(--line); border-radius:11px; padding:12px 13px; margin-bottom:20px; }
  .lf-types { margin-bottom:9px; }
  .lf-type { flex:1; min-width:64px; font-size:12.5px; padding:7px; border-radius:8px; border:1px solid var(--line);
    background:var(--card); color:var(--muted); cursor:pointer; text-align:center; }
  .lf-type.on { background:var(--accent-soft); color:var(--accent); border-color:transparent; font-weight:600; }
  .lf-log textarea { width:100%; min-height:58px; resize:vertical; background:var(--bg); color:var(--ink);
    border:1px solid var(--line); border-radius:8px; padding:8px 10px; font:inherit; font-size:13px; }
  .lf-log-row { display:flex; align-items:center; gap:8px; margin-top:9px; }
  .lf-log-row select { background:var(--bg); color:var(--ink); border:1px solid var(--line); border-radius:7px; padding:6px 8px; font-size:12.5px; }
  .lf-spacer { flex:1; }
  .lf-act { display:flex; gap:11px; padding:11px 0; border-bottom:1px solid var(--line); }
  .lf-act:last-child { border-bottom:none; }
  .lf-atag { font-size:10px; text-transform:uppercase; letter-spacing:.5px; font-weight:700; padding:3px 8px;
    border-radius:99px; align-self:flex-start; background:var(--low-soft); color:var(--muted); }
  .lf-atag.call { background:var(--good-soft); color:var(--good); }
  .lf-atag.email { background:var(--accent-soft); color:var(--accent); }
  .lf-atag.meeting { background:var(--mid-soft); color:var(--mid); }
  .lf-abody { flex:1; font-size:13.5px; line-height:1.5; white-space:pre-wrap; word-break:break-word; }
  .lf-atime { color:var(--muted); font-size:11.5px; margin-top:3px; }
  .lf-empty { color:var(--muted); font-size:13px; padding:12px 0; }
  `;

  let els = null, current = null, onChangeCb = null, selType = "call";

  // Build the drawer DOM + styles once, on first open.
  function ensure() {
    if (els) return;
    const style = document.createElement("style"); style.textContent = CSS; document.head.appendChild(style);
    const scrim = document.createElement("div"); scrim.className = "lf-scrim"; scrim.hidden = true;
    const drawer = document.createElement("div"); drawer.className = "lf-drawer";
    drawer.innerHTML =
      '<div class="lf-dh">' +
        '<div class="lf-dh-top"><span class="lf-dname" id="lf-name"></span>' +
        '<button class="lf-dx" id="lf-x" title="Close" type="button">&times;</button></div>' +
        '<div class="lf-dmeta" id="lf-meta"></div>' +
        '<div class="lf-dcontacts" id="lf-contacts"></div>' +
      "</div>" +
      '<div class="lf-dbody">' +
        '<div class="lf-fu">' +
          '<div class="lf-fu-state" id="lf-fu-state"></div>' +
          '<div class="lf-fu-btns">' +
            '<button class="lf-chip" data-fu="1" type="button">Tomorrow</button>' +
            '<button class="lf-chip" data-fu="3" type="button">In 3 days</button>' +
            '<button class="lf-chip" data-fu="7" type="button">In a week</button>' +
            '<button class="lf-chip" data-fu="clear" type="button">Clear</button>' +
          "</div>" +
        "</div>" +
        '<div class="lf-log">' +
          '<div class="lf-types" id="lf-types"></div>' +
          '<textarea id="lf-note" placeholder="Log a call, email, note, or meeting..."></textarea>' +
          '<div class="lf-log-row"><label class="muted" style="font-size:12px">Then follow up ' +
            '<select id="lf-fu-days"><option value="">no reminder</option>' +
            '<option value="1">tomorrow</option><option value="3" selected>in 3 days</option>' +
            '<option value="7">in a week</option></select></label>' +
            '<span class="lf-spacer"></span>' +
            '<button class="btn" id="lf-log" type="button">Log</button></div>' +
        "</div>" +
        '<div class="lf-label">Activity</div>' +
        '<div id="lf-timeline"></div>' +
      "</div>";
    document.body.appendChild(scrim); document.body.appendChild(drawer);

    const typesEl = drawer.querySelector("#lf-types");
    typesEl.innerHTML = TYPES.map(([k, l], i) =>
      '<button class="lf-type' + (i === 0 ? " on" : "") + '" data-t="' + k + '" type="button">' + l + "</button>").join("");
    typesEl.addEventListener("click", (e) => {
      const b = e.target.closest(".lf-type"); if (!b) return;
      selType = b.dataset.t;
      typesEl.querySelectorAll(".lf-type").forEach((x) => x.classList.toggle("on", x === b));
    });
    drawer.querySelector("#lf-x").addEventListener("click", close);
    scrim.addEventListener("click", close);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !scrim.hidden) close(); });
    drawer.querySelector("#lf-log").addEventListener("click", logActivity);
    drawer.querySelector(".lf-fu-btns").addEventListener("click", (e) => {
      const b = e.target.closest("[data-fu]"); if (!b) return; setFollow(b.dataset.fu);
    });
    els = { scrim, drawer };
  }

  function q(id) { return els.drawer.querySelector(id); }

  function renderHeader() {
    const l = current;
    q("#lf-name").textContent = l.name || "(no name)";
    const meta = [STAGE_LABEL[l.stage] || l.stage, hasText(l.category) ? String(l.category).replace(/_/g, " ") : ""]
      .filter(Boolean).map(esc).join(" &middot; ");
    q("#lf-meta").innerHTML = meta + (hasText(l.address) ? '<div style="margin-top:3px">' + esc(l.address) + "</div>" : "");
    const c = [];
    if (hasText(l.phone)) c.push('<a href="tel:' + esc(String(l.phone).replace(/[^0-9+]/g, "")) + '">' + esc(l.phone) + "</a>");
    if (hasText(l.email)) c.push('<a href="mailto:' + esc(l.email) + '">' + esc(l.email) + "</a>");
    q("#lf-contacts").innerHTML = c.join("");
    const fs = followState(l.next_follow_up);
    const st = q("#lf-fu-state"); st.textContent = fs.text; st.className = "lf-fu-state" + (fs.due ? " due" : "");
  }

  function renderTimeline(acts) {
    const el = q("#lf-timeline");
    if (!acts || !acts.length) { el.innerHTML = '<div class="lf-empty">No activity logged yet.</div>'; return; }
    el.innerHTML = acts.map((a) =>
      '<div class="lf-act"><span class="lf-atag ' + esc(a.type) + '">' + esc(a.type) + "</span>" +
      '<div class="lf-abody">' + (hasText(a.body) ? esc(a.body) : '<span class="lf-empty">(no note)</span>') +
      '<div class="lf-atime">' + esc(relTime(a.created_at)) + "</div></div></div>").join("");
  }

  async function open(lead, onChange) {
    ensure();
    current = lead; onChangeCb = onChange || null;
    selType = "call";
    els.drawer.querySelectorAll(".lf-type").forEach((x, i) => x.classList.toggle("on", i === 0));
    q("#lf-note").value = "";
    renderHeader();
    q("#lf-timeline").innerHTML = '<div class="lf-empty">Loading...</div>';
    els.scrim.hidden = false;
    requestAnimationFrame(() => { els.scrim.classList.add("open"); els.drawer.classList.add("open"); });
    const res = await api("/api/activities?place_id=" + encodeURIComponent(current.place_id));
    if (current) renderTimeline(res.activities || []);
  }

  function close() {
    if (!els) return;
    els.scrim.classList.remove("open"); els.drawer.classList.remove("open");
    setTimeout(() => { if (els) els.scrim.hidden = true; }, 180);
    current = null;
  }

  async function logActivity() {
    if (!current) return;
    const body = q("#lf-note").value.trim();
    const days = q("#lf-fu-days").value;
    if (!body && selType === "note") { q("#lf-note").focus(); return; }  // a note needs text
    const payload = { place_id: current.place_id, type: selType, body: body };
    if (days !== "") payload.follow_up_days = Number(days);
    const res = await post("/api/activity", payload);
    q("#lf-note").value = "";
    if (res.next_follow_up !== undefined && res.next_follow_up !== null) current.next_follow_up = res.next_follow_up;
    else if (days !== "") current.next_follow_up = null;
    renderHeader();
    const tl = await api("/api/activities?place_id=" + encodeURIComponent(current.place_id));
    renderTimeline(tl.activities || []);
    if (onChangeCb) onChangeCb(current);
  }

  async function setFollow(v) {
    if (!current) return;
    const payload = v === "clear" ? { place_id: current.place_id, clear: true } : { place_id: current.place_id, days: Number(v) };
    const res = await post("/api/follow-up", payload);
    current.next_follow_up = res.next_follow_up || null;
    renderHeader();
    if (onChangeCb) onChangeCb(current);
  }

  window.LeadDetail = { open: open, close: close, followState: followState, relTime: relTime };
})();
