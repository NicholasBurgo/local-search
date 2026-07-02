(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
  function hasText(v) { return String(v == null ? "" : v).trim() !== ""; }
  function pillCls(q) { const n = Number(q) || 0; return n >= 70 ? "hi" : n >= 40 ? "mid" : "lo"; }

  async function api(path, opts) { const r = await fetch(path, opts); return r.json(); }
  function post(path, body) {
    return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }

  // Active pipeline columns (left to right); Won/Lost are the closed states.
  const COLUMNS = [
    { stage: "new", title: "New" },
    { stage: "contacted", title: "Contacted" },
    { stage: "qualified", title: "Qualified" },
    { stage: "proposal_sent", title: "Proposal Sent" },
    { stage: "negotiating", title: "Negotiating" },
  ];
  const ARCHIVE = [
    { stage: "won", title: "Won" },
    { stage: "lost", title: "Lost" },
  ];
  // Quick-move buttons offered on a card, by its current stage: [targetStage, label, tone].
  const MOVES = {
    new: [["contacted", "Contacted", "good"], ["lost", "Lost", "bad"]],
    contacted: [["qualified", "Qualified", "good"], ["lost", "Lost", "bad"]],
    qualified: [["proposal_sent", "Proposal", "good"], ["lost", "Lost", "bad"]],
    proposal_sent: [["negotiating", "Negotiate", "good"], ["won", "Won", "good"], ["lost", "Lost", "bad"]],
    negotiating: [["won", "Won", "good"], ["lost", "Lost", "bad"], ["proposal_sent", "Back"]],
    won: [["negotiating", "Reopen"]],
    lost: [["negotiating", "Reopen"]],
  };

  let leads = [], showArchive = false, dragK = null;

  async function load() {
    const res = await api("/api/saved?filter=listed");
    leads = res.leads || [];
    render();
  }

  function byStage(s) { return leads.filter((l) => l.stage === s); }

  function cardHtml(l) {
    const moves = (MOVES[l.stage] || []).map(([to, label, tone]) =>
      '<button class="mv' + (tone ? " " + tone : "") + '" data-to="' + to + '" data-k="' + esc(l.place_id) + '">' + esc(label) + "</button>").join("");
    const line1 = [
      hasText(l.category) ? String(l.category).replace(/_/g, " ") : "",
      l.address || l.city || "",
    ].filter(Boolean).map(esc).join(" &middot; ");
    const line2 = [];
    if (hasText(l.phone)) line2.push('<a href="tel:' + esc(String(l.phone).replace(/[^0-9+]/g, "")) + '">' + esc(l.phone) + "</a>");
    if (hasText(l.email)) line2.push('<a href="mailto:' + esc(l.email) + '">email</a>');
    if (hasText(l.verification_status)) line2.push(esc(l.verification_status));
    return (
      '<div class="pcard" draggable="true" data-k="' + esc(l.place_id) + '">' +
        '<div class="pcard-top">' +
          '<span class="pcard-name">' + esc(l.name) + "</span>" +
          '<span class="pill ' + pillCls(l.quality) + '">' + esc(l.quality) + "</span>" +
          '<button class="pcard-rm" title="Remove from list" data-rm="' + esc(l.place_id) + '">&times;</button>' +
        "</div>" +
        (line1 ? '<div class="pcard-meta">' + line1 + "</div>" : "") +
        (line2.length ? '<div class="pcard-meta">' + line2.join(" &middot; ") + "</div>" : "") +
        '<div class="pcard-acts">' + moves + "</div>" +
      "</div>"
    );
  }

  function colHtml(col) {
    const items = byStage(col.stage);
    const body = items.length ? items.map(cardHtml).join("") : '<div class="col-empty">Drop leads here</div>';
    return (
      '<div class="col" data-stage="' + col.stage + '">' +
        '<div class="col-head"><span class="col-title">' + esc(col.title) + '</span>' +
        '<span class="col-count">' + items.length + "</span></div>" +
        '<div class="col-body">' + body + "</div>" +
      "</div>"
    );
  }

  function render() {
    const n = leads.length;
    $("sub-count").textContent = n + (n === 1 ? " lead" : " leads") + " on your list";
    if (!n) {
      $("board").innerHTML = '<div class="rev-empty"><h2>Your list is empty</h2><p>Head to the <a href="/">map</a>, find businesses, and hit <b>+ Add to list</b>. They land in New here.</p></div>';
      $("archive").hidden = true; $("archive").innerHTML = "";
      $("archive-btn").hidden = true;
      return;
    }
    $("archive-btn").hidden = false;
    $("board").innerHTML = COLUMNS.map(colHtml).join("");
    const arch = $("archive");
    if (showArchive) {
      arch.hidden = false;
      arch.innerHTML = '<div class="board">' + ARCHIVE.map(colHtml).join("") + "</div>";
    } else {
      arch.hidden = true; arch.innerHTML = "";
    }
    const na = byStage("won").length + byStage("lost").length;
    $("archive-btn").textContent = (showArchive ? "Hide closed" : "Show closed") + (na ? " (" + na + ")" : "");
  }

  async function move(k, to) {
    const l = leads.find((x) => x.place_id === k);
    if (!l) return;
    l.stage = to || null;
    if (!to) leads = leads.filter((x) => x.place_id !== k); // removed from the list entirely
    render();
    await post("/api/mark", { place_id: k, stage: to || "" });
  }

  function wireDnD(wrap) {
    wrap.addEventListener("dragstart", (e) => {
      const c = e.target.closest(".pcard"); if (!c) return;
      dragK = c.dataset.k; c.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      try { e.dataTransfer.setData("text/plain", dragK); } catch (_) { /* ignore */ }
    });
    wrap.addEventListener("dragend", (e) => {
      const c = e.target.closest(".pcard"); if (c) c.classList.remove("dragging");
      document.querySelectorAll(".col.drop").forEach((x) => x.classList.remove("drop"));
      dragK = null;
    });
    wrap.addEventListener("dragover", (e) => { if (e.target.closest(".col")) { e.preventDefault(); e.dataTransfer.dropEffect = "move"; } });
    wrap.addEventListener("dragenter", (e) => { const col = e.target.closest(".col"); if (col) col.classList.add("drop"); });
    wrap.addEventListener("dragleave", (e) => { const col = e.target.closest(".col"); if (col && !col.contains(e.relatedTarget)) col.classList.remove("drop"); });
    wrap.addEventListener("drop", (e) => {
      const col = e.target.closest(".col"); if (!col || !dragK) return;
      e.preventDefault();
      const to = col.dataset.stage, k = dragK;
      col.classList.remove("drop");
      const l = leads.find((x) => x.place_id === k);
      if (l && l.stage !== to) move(k, to);
    });
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
    const wrap = $("board-wrap");
    wrap.addEventListener("click", (e) => {
      const mv = e.target.closest(".mv"); if (mv) { move(mv.dataset.k, mv.dataset.to); return; }
      const rm = e.target.closest(".pcard-rm"); if (rm) { move(rm.dataset.rm, ""); return; }
    });
    $("archive-btn").addEventListener("click", () => { showArchive = !showArchive; render(); });
    $("refresh-btn").addEventListener("click", load);
    wireDnD(wrap);
  }

  initTheme();
  wire();
  load();
})();
