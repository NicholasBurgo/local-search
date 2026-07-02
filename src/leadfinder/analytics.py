"""Interactive HTML lead worklist ("dashboard") for a leads CSV.

Renders a single self-contained (no external assets), ASCII-only HTML file.
Lead rows are embedded as JSON and the page renders client-side: a searchable /
sortable / filterable worklist where leads can be checked off as contacted
(persisted in localStorage), with live KPI tiles, charts, progress tracking,
and filtered CSV export. Light/dark theme with a persisted toggle. No server.
"""

from __future__ import annotations

import glob
import html
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

from .logging_setup import get_logger

# Columns embedded per lead for the client-side table.
_RECORD_FIELDS = [
    "name",
    "city",
    "category",
    "rating",
    "review_count",
    "phone",
    "email",
    "socials",
    "address",
    "hours",
    "price_level",
    "website_uri",
    "place_id",
    "source",
    "confidence",
]


def load_leads(csv_path: str) -> pd.DataFrame:
    return pd.read_csv(csv_path)


def _has_text(value) -> bool:
    return pd.notna(value) and str(value).strip() != ""


def _num(value) -> float | None:
    n = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(n) else float(n)


def _lead_scores(df: pd.DataFrame) -> list[float]:
    """Lead score per row, 0-100, usable by any data source.

    Contactability: phone +25, email +15, socials +5, address +10.
    Establishment: rating-based when ratings exist (Google) -- min(rating*5, 25)
    + min(log1p(reviews)*4, 15) + hours +5; otherwise the source's existence
    confidence (Overture, 0-1) * 45.
    """
    scores: list[float] = []
    for _, row in df.iterrows():
        score = 0.0
        if _has_text(row.get("phone")):
            score += 25
        if _has_text(row.get("email")):
            score += 15
        if _has_text(row.get("socials")):
            score += 5
        if _has_text(row.get("address")):
            score += 10

        rating = _num(row.get("rating"))
        if rating is not None and rating > 0:
            score += min(rating * 5, 25)
            reviews = _num(row.get("review_count"))
            if reviews is not None and reviews > 0:
                score += min(float(np.log1p(reviews)) * 4, 15)
            if _has_text(row.get("hours")):
                score += 5
        else:
            confidence = _num(row.get("confidence"))
            if confidence is not None and confidence > 0:
                score += confidence * 45

        scores.append(min(score, 100))
    return scores


def compute_stats(df: pd.DataFrame) -> dict:
    """Summary statistics for a leads DataFrame (robust to missing columns)."""
    total = len(df)
    rating = (
        pd.to_numeric(df["rating"], errors="coerce") if "rating" in df else pd.Series(dtype=float)
    )
    stats: dict = {
        "total_businesses": total,
        "cities": int(df["city"].nunique()) if "city" in df else 0,
        "categories": int(df["category"].nunique()) if "category" in df else 0,
        "with_phone": int(df["phone"].fillna("").astype(str).str.strip().ne("").sum())
        if "phone" in df
        else 0,
        "with_rating": int(rating.notna().sum()),
        "with_hours": int(df["hours"].fillna("").astype(str).str.strip().ne("").sum())
        if "hours" in df
        else 0,
    }
    scores = _lead_scores(df)
    if scores:
        stats["quality_stats"] = {
            "average": float(np.mean(scores)),
            "high_quality": int(sum(1 for s in scores if s >= 70)),
            "medium_quality": int(sum(1 for s in scores if 40 <= s < 70)),
            "low_quality": int(sum(1 for s in scores if s < 40)),
        }
    else:
        stats["quality_stats"] = {
            "average": 0.0,
            "high_quality": 0,
            "medium_quality": 0,
            "low_quality": 0,
        }
    return stats


def lead_records(df: pd.DataFrame) -> list[dict]:
    """Per-lead records (JSON-ready) for the interactive table, incl. lead score."""
    if df.empty:
        return []
    scores = _lead_scores(df)
    present = [c for c in _RECORD_FIELDS if c in df.columns]
    rating = pd.to_numeric(df["rating"], errors="coerce") if "rating" in df else None
    reviews = pd.to_numeric(df["review_count"], errors="coerce") if "review_count" in df else None
    confidence = pd.to_numeric(df["confidence"], errors="coerce") if "confidence" in df else None

    records: list[dict] = []
    for i, (_, row) in enumerate(df.iterrows()):
        rec: dict = {}
        for field in _RECORD_FIELDS:
            value = row[field] if field in present else ""
            rec[field] = "" if pd.isna(value) else value
        if rating is not None:
            rv = rating.iloc[i]
            rec["rating"] = "" if pd.isna(rv) else round(float(rv), 1)
        if reviews is not None:
            rc = reviews.iloc[i]
            rec["review_count"] = "" if pd.isna(rc) else int(rc)
        if confidence is not None:
            cv = confidence.iloc[i]
            rec["confidence"] = "" if pd.isna(cv) else round(float(cv), 2)
        rec["quality"] = round(scores[i])
        records.append(rec)
    return records


_CSS = """<style>
  :root {
    --bg:#F7F7F4; --card:#FFFFFF; --ink:#20241F; --muted:#6A7166; --line:#E4E6DF;
    --accent:#0E6B5C; --accent-ink:#FFFFFF; --accent-soft:#E7F0EC;
    --good:#2F7D4F; --good-soft:#E6F0E8; --mid:#A97A0B; --mid-soft:#F5ECD8;
    --low:#6A7166; --low-soft:#ECEEE8; --shadow:0 1px 2px rgba(32,36,31,.05);
  }
  [data-theme="dark"] {
    --bg:#151815; --card:#1D211D; --ink:#E7EAE4; --muted:#96A096; --line:#2B302B;
    --accent:#53B8A5; --accent-ink:#10201B; --accent-soft:#20302B;
    --good:#6DBA8B; --good-soft:#1F2E24; --mid:#D3A43F; --mid-soft:#332B18;
    --low:#96A096; --low-soft:#242923; --shadow:none;
  }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
         background:var(--bg); color:var(--ink); padding:28px 24px; font-size:14px; }
  h1 { margin:0; font-family:Charter,"Bitstream Charter",Georgia,"Times New Roman",serif;
       font-size:26px; font-weight:700; letter-spacing:.2px; }
  h2 { font-size:12px; margin:0 0 12px; color:var(--muted); text-transform:uppercase;
       letter-spacing:.8px; font-weight:600; }
  .topbar { display:flex; justify-content:space-between; align-items:flex-start; gap:16px;
            max-width:1240px; margin:0 auto 18px; }
  .sub { color:var(--muted); font-size:13px; margin-top:4px; }
  .muted { color:var(--muted); font-size:12px; }
  .wrap { max-width:1240px; margin:0 auto; }
  .grid { display:grid; gap:14px; }
  .kpis { grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); }
  .cards { grid-template-columns:repeat(auto-fit,minmax(290px,1fr)); margin-top:14px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px;
          padding:16px 18px; box-shadow:var(--shadow); }
  .kpi { background:var(--card); border:1px solid var(--line); border-radius:10px;
         padding:14px 16px; box-shadow:var(--shadow); }
  .kpi-val { font-size:24px; font-weight:700; font-variant-numeric:tabular-nums; }
  .kpi-label { color:var(--muted); font-size:11px; margin-top:3px; text-transform:uppercase;
               letter-spacing:.6px; }
  .controls { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; align-items:center; }
  .controls input[type=search], .controls select {
    background:var(--card); color:var(--ink); border:1px solid var(--line); border-radius:8px;
    padding:9px 12px; font-size:13px; }
  .controls input[type=search] { flex:1; min-width:220px; }
  .controls button, .btn {
    background:var(--accent); color:var(--accent-ink); border:0; border-radius:8px;
    padding:9px 14px; font-size:13px; font-weight:600; cursor:pointer; }
  .controls button:hover, .btn:hover { filter:brightness(1.06); }
  .ghost { background:transparent; color:var(--muted); border:1px solid var(--line);
           font-weight:500; }
  .ghost:hover { color:var(--ink); filter:none; border-color:var(--muted); }
  :focus-visible { outline:2px solid var(--accent); outline-offset:2px; border-radius:4px; }
  .table-card { margin-top:14px; padding:0; overflow:hidden; }
  .table-head { display:flex; justify-content:space-between; align-items:center; gap:14px;
                flex-wrap:wrap; padding:14px 18px; border-bottom:1px solid var(--line); }
  .table-title { display:flex; align-items:baseline; gap:10px; }
  .progress-wrap { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
  .progress { width:150px; height:6px; background:var(--line); border-radius:99px;
              overflow:hidden; display:inline-block; }
  .progress-fill { display:block; height:100%; width:0; background:var(--good); }
  .toggle { display:inline-flex; align-items:center; gap:6px; font-size:12px;
            color:var(--muted); cursor:pointer; user-select:none; }
  .link-btn { background:none; border:none; color:var(--muted); font-size:12px;
              text-decoration:underline; cursor:pointer; padding:4px; }
  .link-btn:hover { color:var(--ink); }
  .table-wrap { overflow-x:auto; max-height:62vh; overflow-y:auto; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { text-align:left; padding:9px 12px; border-bottom:1px solid var(--line);
           white-space:nowrap; }
  th { color:var(--muted); font-weight:600; cursor:pointer; user-select:none; position:sticky;
       top:0; background:var(--card); z-index:1; font-size:12px; }
  th:hover { color:var(--ink); }
  th.c-check { cursor:default; }
  td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
  td:nth-child(2) { white-space:normal; font-weight:600; }
  tbody tr:hover { background:var(--accent-soft); }
  tr.done { opacity:.55; }
  tr.done .lead-name { text-decoration:line-through; text-decoration-color:var(--good);
                       text-decoration-thickness:2px; }
  input[type=checkbox] { accent-color:var(--accent); width:15px; height:15px; cursor:pointer; }
  a { color:var(--accent); text-decoration:none; }
  a:hover { text-decoration:underline; }
  .pill { display:inline-block; padding:2px 9px; border-radius:999px; font-size:11px;
          font-weight:700; font-variant-numeric:tabular-nums; }
  .pill-hi { background:var(--good-soft); color:var(--good); }
  .pill-mid { background:var(--mid-soft); color:var(--mid); }
  .pill-lo { background:var(--low-soft); color:var(--low); }
  .chip { display:inline-block; padding:2px 8px; border-radius:6px; font-size:11px;
          background:var(--low-soft); color:var(--muted); }
  .bar-row { display:flex; align-items:center; gap:10px; margin:7px 0; font-size:13px; }
  .bar-label { width:130px; color:var(--muted); overflow:hidden; text-overflow:ellipsis;
               white-space:nowrap; }
  .bar { flex:1; background:var(--line); border-radius:6px; height:10px; overflow:hidden; }
  .bar-fill { display:block; height:100%; background:var(--accent); }
  .bar-val { width:52px; text-align:right; font-variant-numeric:tabular-nums; }
  .empty { color:var(--muted); }
  @media (prefers-reduced-motion: reduce) { * { transition:none !important; } }
</style>"""

_MARKUP = """<div class="topbar">
  <div>
    <h1>Leadfinder</h1>
    <div class="sub">Source: __SOURCE__ &middot; Generated __DATE__</div>
  </div>
  <button id="theme-toggle" type="button" class="btn ghost" aria-label="Toggle light/dark theme">
    Theme</button>
</div>

<div class="wrap">
  <div class="grid kpis" id="kpis"></div>

  <div class="controls">
    <input id="f-q" type="search" placeholder="Search name, address, or phone...">
    <select id="f-city" aria-label="Filter by city"><option value="">All cities</option></select>
    <select id="f-cat" aria-label="Filter by category">
      <option value="">All categories</option></select>
    <button id="f-export" type="button">Export filtered CSV</button>
  </div>

  <div class="card table-card">
    <div class="table-head">
      <div class="table-title"><h2 style="margin:0">Leads</h2>
        <span id="count" class="muted"></span></div>
      <div class="progress-wrap">
        <span id="progress-label" class="muted"></span>
        <span class="progress"><span id="progress-fill" class="progress-fill"></span></span>
        <label class="toggle"><input type="checkbox" id="f-hide"> Hide contacted</label>
        <button id="reset-checks" type="button" class="link-btn">Reset checks</button>
      </div>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr id="thead-row"></tr></thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </div>

  <div class="grid cards">
    <div class="card"><h2>Data coverage</h2><div id="coverage"></div></div>
    <div class="card"><h2>Leads by city</h2><div id="chart-city"></div></div>
    <div class="card"><h2>Leads by category</h2><div id="chart-cat"></div></div>
    <div class="card"><h2 id="chart-dist-title">Score distribution</h2>
      <div id="chart-dist"></div></div>
  </div>
</div>"""

_JS = """
const $ = (id) => document.getElementById(id);
const NUMERIC = ["rating", "review_count", "quality", "confidence"];
const CAP = 1000;
const LS_CHECK = "leadfinder.checked.v1";
const LS_HIDE = "leadfinder.hideDone.v1";
const LS_THEME = "leadfinder.theme.v1";

function lsGet(k, fallback){ try { const v = localStorage.getItem(k); return v===null ? fallback : JSON.parse(v); } catch(e){ return fallback; } }
function lsSet(k, v){ try { localStorage.setItem(k, JSON.stringify(v)); } catch(e){} }

let checked = lsGet(LS_CHECK, {}) || {};
const state = { q:"", city:"", cat:"", hideDone: !!lsGet(LS_HIDE, false), sortKey:"quality", sortDir:-1 };

function toNum(v){ if(v===""||v===null||v===undefined) return null; const n=Number(v); return isNaN(n)?null:n; }
function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function pct(n,d){ return d ? n/d*100 : 0; }
function hasText(v){ return String(v==null?"":v).trim() !== ""; }
function leadKey(l){ return String(l.place_id||"") || ((l.name||"")+"|"+(l.city||"")).toLowerCase(); }
function isChecked(l){ return !!checked[leadKey(l)]; }
function distinct(key){ const s=new Set(); for(const l of LEADS){ if(l[key]!==""&&l[key]!=null) s.add(l[key]); } return Array.from(s).sort(); }

const HAS = {
  email: LEADS.some(l=>hasText(l.email)),
  rating: LEADS.some(l=>toNum(l.rating)!==null),
  multiSource: new Set(LEADS.map(l=>l.source).filter(Boolean)).size > 1
};

const COLS = (function(){
  const c = [
    {key:"__check", label:"", cls:"c-check"},
    {key:"name", label:"Name"},
    {key:"city", label:"City"},
    {key:"category", label:"Category"},
    {key:"phone", label:"Phone"}
  ];
  if (HAS.email) c.push({key:"email", label:"Email"});
  if (HAS.rating) { c.push({key:"rating", label:"Rating", cls:"num"}); c.push({key:"review_count", label:"Reviews", cls:"num"}); }
  if (HAS.multiSource) c.push({key:"source", label:"Source"});
  c.push({key:"quality", label:"Score", cls:"num"});
  return c;
})();

function filtered(){
  const q = state.q.trim().toLowerCase();
  let rows = LEADS.filter(l=>{
    if(state.hideDone && isChecked(l)) return false;
    if(state.city && l.city!==state.city) return false;
    if(state.cat && l.category!==state.cat) return false;
    if(q){
      const hay = ((l.name||"")+" "+(l.address||"")+" "+(l.phone||"")+" "+(l.email||"")+" "+(l.city||"")).toLowerCase();
      if(!hay.includes(q)) return false;
    }
    return true;
  });
  const k = state.sortKey, dir = state.sortDir;
  rows = rows.slice().sort((a,b)=>{
    const an=toNum(a[k]), bn=toNum(b[k]);
    if(an!==null && bn!==null) return (an-bn)*dir;
    if(an!==null) return -1;
    if(bn!==null) return 1;
    const as=String(a[k]==null?"":a[k]).toLowerCase(), bs=String(b[k]==null?"":b[k]).toLowerCase();
    return as<bs ? -dir : as>bs ? dir : 0;
  });
  return rows;
}

function groupCount(rows,key){ const m=Object.create(null); for(const r of rows){ const v=r[key]; if(v!==""&&v!=null) m[v]=(m[v]||0)+1; } return m; }
function ratingDist(rows){
  const m=Object.create(null);
  for(const r of rows){ const n=toNum(r.rating); if(n!==null){ const k=Math.round(n).toFixed(1); m[k]=(m[k]||0)+1; } }
  const o=Object.create(null);
  Object.keys(m).sort((a,b)=>a-b).forEach(k=>o[k]=m[k]);
  return o;
}
function scoreDist(rows){
  const bands = [["70-100 (hot)",0],["40-69 (warm)",0],["0-39 (cool)",0]];
  for(const r of rows){ const n=toNum(r.quality)||0; if(n>=70) bands[0][1]++; else if(n>=40) bands[1][1]++; else bands[2][1]++; }
  const o=Object.create(null); bands.forEach(b=>o[b[0]]=b[1]); return o;
}
function avg(rows,key){ let s=0,c=0; for(const r of rows){ const n=toNum(r[key]); if(n!==null){s+=n;c++;} } return c?s/c:0; }
function countIf(rows,f){ let n=0; for(const r of rows) if(f(r)) n++; return n; }

function bars(map,limit){
  limit = limit || 15;
  const items = Object.keys(map).map(k=>[k,map[k]]).sort((a,b)=>b[1]-a[1]).slice(0,limit);
  if(!items.length) return '<p class="empty">No data.</p>';
  const top = Math.max.apply(null, items.map(i=>i[1])) || 1;
  return items.map(it=>{
    const w=(it[1]/top*100).toFixed(1);
    return '<div class="bar-row"><span class="bar-label">'+esc(it[0])+'</span><span class="bar"><span class="bar-fill" style="width:'+w+'%"></span></span><span class="bar-val">'+it[1]+'</span></div>';
  }).join("");
}

function qpill(q){ const n=toNum(q)||0; const cls = n>=70?"pill-hi":(n>=40?"pill-mid":"pill-lo"); return '<span class="pill '+cls+'">'+esc(q)+'</span>'; }
function telLink(v){ if(!hasText(v)) return ""; const digits=String(v).replace(/[^0-9+]/g,""); return '<a href="tel:'+esc(digits)+'">'+esc(v)+'</a>'; }
function mailLink(v){ if(!hasText(v)) return ""; return '<a href="mailto:'+esc(v)+'">'+esc(v)+'</a>'; }

function cellFor(col, l){
  if(col.key==="__check") return '<td class="c-check"><input type="checkbox" data-key="'+esc(leadKey(l))+'" '+(isChecked(l)?"checked":"")+' aria-label="Mark contacted"></td>';
  if(col.key==="name") return '<td><span class="lead-name">'+esc(l.name)+'</span></td>';
  if(col.key==="phone") return '<td>'+telLink(l.phone)+'</td>';
  if(col.key==="email") return '<td>'+mailLink(l.email)+'</td>';
  if(col.key==="source") return '<td><span class="chip">'+esc(l.source||"")+'</span></td>';
  if(col.key==="quality") return '<td class="num">'+qpill(l.quality)+'</td>';
  const v = l[col.key];
  return '<td class="'+(col.cls||"")+'">'+(v===""||v==null?"":esc(v))+'</td>';
}

function renderProgress(){
  const total = LEADS.length;
  const done = LEADS.filter(isChecked).length;
  $("progress-label").textContent = done+" of "+total+" contacted";
  $("progress-fill").style.width = (total? (done/total*100):0).toFixed(1)+"%";
  return done;
}

function render(){
  const rows = filtered();
  const done = renderProgress();

  const kpis = [
    ["Total leads", LEADS.length.toLocaleString()],
    ["Showing", rows.length.toLocaleString()],
    ["Contacted", done.toLocaleString()],
    ["With phone", countIf(rows, r=>hasText(r.phone)).toLocaleString()]
  ];
  if (HAS.rating) kpis.push(["Avg rating", avg(rows,"rating").toFixed(2)]);
  else if (HAS.email) kpis.push(["With email", countIf(rows, r=>hasText(r.email)).toLocaleString()]);
  kpis.push(["Avg score", String(Math.round(avg(rows,"quality")))]);
  $("kpis").innerHTML = kpis.map(k=>'<div class="kpi"><div class="kpi-val">'+esc(k[1])+'</div><div class="kpi-label">'+esc(k[0])+'</div></div>').join("");

  const cov = [
    ["Phone", pct(countIf(rows,r=>hasText(r.phone)), rows.length)],
    ["Email", pct(countIf(rows,r=>hasText(r.email)), rows.length)],
    ["Address", pct(countIf(rows,r=>hasText(r.address)), rows.length)]
  ];
  $("coverage").innerHTML = cov.map(c=>'<div class="bar-row"><span class="bar-label">'+c[0]+'</span><span class="bar"><span class="bar-fill" style="width:'+c[1].toFixed(1)+'%"></span></span><span class="bar-val">'+c[1].toFixed(0)+'%</span></div>').join("");

  $("chart-city").innerHTML = bars(groupCount(rows,"city"));
  $("chart-cat").innerHTML = bars(groupCount(rows,"category"));
  if (HAS.rating) { $("chart-dist-title").textContent = "Rating distribution"; $("chart-dist").innerHTML = bars(ratingDist(rows)); }
  else { $("chart-dist-title").textContent = "Score distribution"; $("chart-dist").innerHTML = bars(scoreDist(rows)); }

  const shown = rows.slice(0, CAP);
  $("tbody").innerHTML = shown.length
    ? shown.map(l=>'<tr class="'+(isChecked(l)?"done":"")+'">'+COLS.map(c=>cellFor(c,l)).join("")+'</tr>').join("")
    : '<tr><td colspan="'+COLS.length+'" class="empty" style="padding:18px">No matching leads.</td></tr>';
  $("count").textContent = rows.length>CAP
    ? ("showing first "+CAP+" of "+rows.length+" matches (export for all)")
    : (rows.length + (rows.length===1?" match":" matches"));

  document.querySelectorAll("th[data-key]").forEach(th=>{
    const k=th.getAttribute("data-key");
    const ind=th.querySelector(".ind");
    if(ind) ind.textContent = (state.sortKey===k) ? (state.sortDir>0?" ^":" v") : "";
  });
}

function csvCell(v){ v=(v==null?"":String(v)); return /[",\\n]/.test(v) ? '"'+v.replace(/"/g,'""')+'"' : v; }
function exportCSV(){
  const rows = filtered();
  const cols = ["contacted","name","city","category","rating","review_count","phone","email","socials","address","hours","price_level","website_uri","source","confidence","quality"];
  const lines = [cols.join(",")];
  for(const r of rows){
    const rec = Object.assign({contacted: isChecked(r) ? "yes" : ""}, r);
    lines.push(cols.map(c=>csvCell(rec[c])).join(","));
  }
  const blob = new Blob([lines.join("\\n")], {type:"text/csv;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "leads_filtered.csv";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(url), 1000);
}

function applyTheme(t){
  if (document.documentElement && document.documentElement.setAttribute)
    document.documentElement.setAttribute("data-theme", t);
}

function init(){
  let theme = lsGet(LS_THEME, null);
  if(!theme){
    try { theme = (typeof matchMedia!=="undefined" && matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light"; }
    catch(e){ theme = "light"; }
  }
  applyTheme(theme);
  $("theme-toggle").addEventListener("click", ()=>{
    theme = theme==="dark" ? "light" : "dark";
    lsSet(LS_THEME, theme); applyTheme(theme);
  });

  $("thead-row").innerHTML = COLS.map(c=>
    c.key==="__check"
      ? '<th class="c-check"></th>'
      : '<th data-key="'+c.key+'" class="'+(c.cls||"")+'">'+esc(c.label)+'<span class="ind"></span></th>'
  ).join("");

  const cs=$("f-city"), ct=$("f-cat");
  distinct("city").forEach(v=>{ const o=document.createElement("option"); o.value=v; o.textContent=v; cs.appendChild(o); });
  distinct("category").forEach(v=>{ const o=document.createElement("option"); o.value=v; o.textContent=v; ct.appendChild(o); });

  $("f-q").addEventListener("input", e=>{ state.q=e.target.value; render(); });
  cs.addEventListener("change", e=>{ state.city=e.target.value; render(); });
  ct.addEventListener("change", e=>{ state.cat=e.target.value; render(); });
  $("f-export").addEventListener("click", exportCSV);

  const hide=$("f-hide");
  hide.checked = state.hideDone;
  hide.addEventListener("change", e=>{ state.hideDone=!!e.target.checked; lsSet(LS_HIDE, state.hideDone); render(); });

  $("reset-checks").addEventListener("click", ()=>{ checked={}; lsSet(LS_CHECK, checked); render(); });

  $("tbody").addEventListener("change", e=>{
    const t=e.target;
    if(t && t.getAttribute && t.getAttribute("data-key")!==null && t.type==="checkbox"){
      const k=t.getAttribute("data-key");
      if(t.checked) checked[k]=true; else delete checked[k];
      lsSet(LS_CHECK, checked);
      render();
    }
  });

  document.querySelectorAll("th[data-key]").forEach(th=>{
    th.addEventListener("click", ()=>{
      const k=th.getAttribute("data-key");
      if(state.sortKey===k) state.sortDir*=-1;
      else { state.sortKey=k; state.sortDir = NUMERIC.indexOf(k)>=0 ? -1 : 1; }
      render();
    });
  });

  render();
}
document.addEventListener("DOMContentLoaded", init);
"""


def _inner(source_name: str, leads: list[dict]) -> str:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    payload = json.dumps(leads, allow_nan=False).replace("<", "\\u003c")
    markup = _MARKUP.replace("__SOURCE__", html.escape(source_name)).replace("__DATE__", generated)
    return (
        _CSS + "\n" + markup + "\n<script>\nconst LEADS = " + payload + ";\n" + _JS + "</script>\n"
    )


def dashboard_fragment(source_name: str, leads: list[dict] | None = None) -> str:
    """Body-only dashboard content (no doctype/head/body), for embedding contexts."""
    return _inner(source_name, leads or [])


def render_dashboard(source_name: str, leads: list[dict] | None = None) -> str:
    """Full standalone HTML document for the interactive dashboard."""
    inner = _inner(source_name, leads or [])
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Leadfinder Dashboard</title>\n</head>\n<body>\n" + inner + "</body>\n</html>\n"
    )


def build_dashboard(csv_path: str, output_file: str | None = None) -> str:
    """Compute records from csv_path and write an interactive HTML dashboard."""
    logger = get_logger()
    df = load_leads(csv_path)
    html_out = render_dashboard(os.path.basename(csv_path), lead_records(df))
    if output_file is None:
        output_file = os.path.join(os.path.dirname(csv_path) or ".", "dashboard.html")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_out)
    logger.info("Dashboard written to %s (%d leads)", output_file, len(df))
    return output_file


def latest_leads_file(output_dir: str) -> str | None:
    files = glob.glob(os.path.join(output_dir, "all_leads_no_website_*.csv"))
    files += glob.glob(os.path.join(output_dir, "verified", "verified_no_website_*.csv"))
    return max(files) if files else None


def main(output_dir: str = "leads_output", output_file: str | None = None) -> str | None:
    logger = get_logger()
    latest = latest_leads_file(output_dir)
    if not latest:
        logger.error("No leads CSV found in %s. Run the scraper first.", output_dir)
        return None
    return build_dashboard(latest, output_file)
