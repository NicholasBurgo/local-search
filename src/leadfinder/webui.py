"""HTML page for the interactive web app (served by server.py).

Reuses the dashboard's theme (`analytics._CSS`) and inline Leaflet, and talks to
the server's JSON API to search a location live, adjust the radius, and verify.
"""

from __future__ import annotations

import json

from .analytics import _CSS, _leaflet_assets
from .categories import BUSINESS_CATEGORIES
from .config import Settings

_APP_CSS = """<style>
  .appbar { max-width:1240px; margin:14px auto; display:flex; flex-wrap:wrap; gap:10px;
            align-items:center; }
  .appbar input[type=search] { flex:1; min-width:220px; background:var(--card); color:var(--ink);
    border:1px solid var(--line); border-radius:8px; padding:10px 12px; font-size:14px; }
  .appbar select { background:var(--card); color:var(--ink); border:1px solid var(--line);
    border-radius:8px; padding:9px 12px; font-size:13px; }
  .rr { display:inline-flex; align-items:center; gap:8px; font-size:13px; color:var(--muted); }
  .rr input[type=range] { accent-color:var(--accent); }
  #app-map { height:56vh; min-height:360px; width:100%; border-radius:10px;
             border:1px solid var(--line); background:var(--line); z-index:0; }
  #status { color:var(--muted); font-size:13px; margin:12px auto; max-width:1240px; }
  #status.spin::after { content:" ..."; }
  .leaflet-container { font:inherit; }
  .leaflet-popup-content { font-size:13px; line-height:1.5; }
  .leaflet-popup-content a { color:var(--accent); }
</style>"""

_APP_MARKUP = """<div class="topbar">
  <div><h1>Leadfinder</h1>
    <div class="sub">Interactive map &middot; live open-data search (Overture, no key)</div></div>
  <button id="theme-toggle" type="button" class="btn ghost">Theme</button>
</div>

<div class="appbar">
  <input id="loc" type="search" placeholder="Location, e.g. Mandeville LA">
  <span class="rr">Radius <span id="radius-label" class="muted">10 mi</span>
    <input id="radius" type="range" min="1" max="30" step="1" value="10"></span>
  <select id="cat" aria-label="Category">__CATEGORY_OPTIONS__</select>
  <button id="search" type="button">Search this area</button>
  <button id="verify" type="button" class="btn ghost">Verify</button>
  <button id="export" type="button" class="btn ghost">Export CSV</button>
</div>

<div id="status"></div>
<div class="wrap"><div id="app-map"></div></div>

<div class="wrap"><div class="card table-card" style="margin-top:14px">
  <div class="table-head"><div class="table-title"><h2 style="margin:0">Leads</h2>
    <span id="count" class="muted"></span></div></div>
  <div class="table-wrap"><table>
    <thead><tr><th>Name</th><th>Category</th><th>Phone</th><th>Email</th>
      <th class="num">Score</th><th>Status</th></tr></thead>
    <tbody id="tbody"></tbody>
  </table></div>
</div></div>"""

_APP_JS = """
const $ = (id) => document.getElementById(id);
function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function hasText(v){ return String(v==null?"":v).trim() !== ""; }
function scoreColor(q){ const n=Number(q)||0; return n>=70?"#2F7D4F":(n>=40?"#A97A0B":"#8A9187"); }
function telLink(v){ if(!hasText(v)) return ""; return '<a href="tel:'+esc(String(v).replace(/[^0-9+]/g,""))+'">'+esc(v)+'</a>'; }
function mailLink(v){ if(!hasText(v)) return ""; return '<a href="mailto:'+esc(v)+'">'+esc(v)+'</a>'; }
function coordOf(l){ const a=Number(l.latitude), b=Number(l.longitude); return (isFinite(a)&&isFinite(b)&&(a||b))?[a,b]:null; }
function removed(l){ const s=l.verification_status; return s==="REMOVED_HAS_WEBSITE"||s==="REMOVED_CHAIN"; }
function zoomFor(mi){ return mi<=2?14:mi<=5?13:mi<=10?12:mi<=20?11:10; }

let MAP, LAYER, RING=null, CENTER=null, LEADS=[];

async function api(path, method, body){
  const r = await fetch(path, {method, headers:{"Content-Type":"application/json"}, body: body?JSON.stringify(body):undefined});
  return r.json();
}
function setStatus(t, spin){ const s=$("status"); s.textContent=t; s.className = spin?"spin":""; }

function popup(l){
  const b=['<strong>'+esc(l.name)+'</strong>'];
  b.push('<div class="muted">'+esc(l.category||"")+' &middot; score '+esc(l.quality)+(l.verification_status?' &middot; '+esc(l.verification_status):'')+'</div>');
  if(hasText(l.phone)) b.push('<div>'+telLink(l.phone)+'</div>');
  if(hasText(l.email)) b.push('<div>'+mailLink(l.email)+'</div>');
  if(hasText(l.address)) b.push('<div class="muted">'+esc(l.address)+'</div>');
  return b.join("");
}

function render(){
  LAYER.clearLayers();
  const pts=[];
  LEADS.forEach(l=>{
    const c=coordOf(l); if(!c) return; pts.push(c);
    const rm=removed(l);
    L.circleMarker(c, {radius:7, color:"#ffffff", weight:1.5, fillColor: rm?"#BBBBBB":scoreColor(l.quality), fillOpacity: rm?0.4:0.92})
      .bindPopup(popup(l)).addTo(LAYER);
  });
  if(RING){ MAP.removeLayer(RING); RING=null; }
  if(CENTER){
    RING = L.circle(CENTER, {radius: Number($("radius").value)*1609.34, color:"#0E6B5C", weight:1, fill:false, dashArray:"5,5"}).addTo(MAP);
  }
  if(pts.length){ try { MAP.fitBounds(L.latLngBounds(pts), {padding:[30,30]}); } catch(e){} }
  else if(CENTER){ MAP.setView(CENTER, zoomFor(Number($("radius").value))); }

  const rows = LEADS.map(l=>'<tr class="'+(removed(l)?"done":"")+'">'
    + '<td><span class="lead-name">'+esc(l.name)+'</span></td>'
    + '<td>'+esc(l.category||"")+'</td>'
    + '<td>'+telLink(l.phone)+'</td>'
    + '<td>'+mailLink(l.email)+'</td>'
    + '<td class="num"><span class="pill '+(l.quality>=70?"pill-hi":l.quality>=40?"pill-mid":"pill-lo")+'">'+esc(l.quality)+'</span></td>'
    + '<td>'+esc(l.verification_status||"")+'</td></tr>').join("");
  $("tbody").innerHTML = rows || '<tr><td colspan="6" class="empty" style="padding:16px">No leads yet - search a location above.</td></tr>';
  $("count").textContent = LEADS.length + " leads";
}

async function doSearch(byCoords){
  const radius = Number($("radius").value);
  const cats = $("cat").value ? [$("cat").value] : null;
  const body = {radius_miles: radius, categories: cats};
  if(byCoords && CENTER){ body.lat=CENTER[0]; body.lon=CENTER[1]; }
  else { body.q = $("loc").value.trim(); if(!body.q){ setStatus("Enter a location first."); return; } }
  setStatus("Searching "+(body.q||"this area")+" ("+radius+" mi) - open data can take a few seconds", true);
  const res = await api("/api/search","POST",body);
  if(res.error){ setStatus("Error: "+res.error); return; }
  CENTER = res.center; LEADS = res.leads || [];
  render();
  setStatus(res.count+" businesses with no website on file within "+radius+" mi. Click Verify to drop any that actually have a site.");
}

async function doVerify(){
  if(!LEADS.length){ setStatus("Nothing to verify - search first."); return; }
  setStatus("Verifying "+LEADS.length+" leads by probing their likely domains", true);
  const res = await api("/api/verify","POST",{leads: LEADS});
  if(res.error){ setStatus("Error: "+res.error); return; }
  LEADS = res.leads || [];
  render();
  const kept = LEADS.filter(l=>!removed(l)).length;
  setStatus("Verified. "+kept+" of "+LEADS.length+" confirmed no-website ("+(LEADS.length-kept)+" removed).");
}

function csvCell(v){ v=(v==null?"":String(v)); return /[",\\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v; }
function exportCSV(){
  const cols=["name","city","category","phone","email","address","website_uri","source","confidence","quality","verification_status","latitude","longitude"];
  const lines=[cols.join(",")];
  LEADS.forEach(l=>lines.push(cols.map(c=>csvCell(l[c])).join(",")));
  const blob=new Blob([lines.join("\\n")],{type:"text/csv;charset=utf-8"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download="leads.csv";
  document.body.appendChild(a); a.click(); a.remove();
}

function init(){
  let theme = null;
  try { theme = localStorage.getItem("leadfinder.theme.v1"); } catch(e){}
  if(!theme){ try { theme = matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"; } catch(e){ theme="light"; } }
  document.documentElement.setAttribute("data-theme", theme);
  $("theme-toggle").addEventListener("click", ()=>{ theme = theme==="dark"?"light":"dark"; try{ localStorage.setItem("leadfinder.theme.v1", theme);}catch(e){} document.documentElement.setAttribute("data-theme", theme); });

  MAP = L.map("app-map");
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom:19, attribution:"&copy; OpenStreetMap contributors"}).addTo(MAP);
  LAYER = L.layerGroup().addTo(MAP);
  MAP.setView([CFG.defaultLat, CFG.defaultLon], 10);

  $("loc").value = CFG.defaultLocation;
  $("radius").value = CFG.defaultRadius;
  $("radius-label").textContent = CFG.defaultRadius + " mi";
  $("search").addEventListener("click", ()=>doSearch(false));
  $("loc").addEventListener("keydown", e=>{ if(e.key==="Enter") doSearch(false); });
  $("radius").addEventListener("input", e=>{ $("radius-label").textContent = e.target.value + " mi"; });
  $("radius").addEventListener("change", ()=>{ if(CENTER) doSearch(true); });
  $("verify").addEventListener("click", doVerify);
  $("export").addEventListener("click", exportCSV);

  doSearch(false);
}
document.addEventListener("DOMContentLoaded", init);
"""


def _category_options() -> str:
    opts = ['<option value="">All categories</option>']
    for key in BUSINESS_CATEGORIES:
        label = key.replace("_", " ").title()
        opts.append(f'<option value="{key}">{label}</option>')
    return "".join(opts)


def render_app_page(settings: Settings) -> str:
    """Full HTML document for the interactive web app."""
    default_city = settings.cities[0] if settings.cities else "Covington LA"
    cfg = {
        "defaultLocation": default_city,
        "defaultRadius": int(settings.radius_miles) if settings.radius_miles else 10,
        "defaultLat": 30.47,
        "defaultLon": -90.1,
    }
    leaflet_css, leaflet_js = _leaflet_assets()
    markup = _APP_MARKUP.replace("__CATEGORY_OPTIONS__", _category_options())
    body = (
        markup
        + "\n"
        + leaflet_js
        + "\n<script>\nconst CFG = "
        + json.dumps(cfg)
        + ";\n"
        + _APP_JS
        + "</script>\n"
    )
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Leadfinder</title>\n"
        + leaflet_css
        + "\n"
        + _CSS
        + "\n"
        + _APP_CSS
        + "\n</head>\n<body>\n"
        + body
        + "</body>\n</html>\n"
    )
