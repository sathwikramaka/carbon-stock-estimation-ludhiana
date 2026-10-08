/* ═══════════════════════════════════════════════════════════
   Ludhiana carbon dashboard — main.js v8

   Every figure on the page comes from the API, which serves what
   notebooks/02_carbon_pipeline.ipynb wrote to results/. There are no
   numeric fallbacks: if the API is unreachable the page shows "—"
   rather than a stale number.
═══════════════════════════════════════════════════════════ */
"use strict";

Chart.defaults.color       = "rgb(90,138,159)";
Chart.defaults.borderColor = "rgba(0,160,220,.08)";
Chart.defaults.font.family = "'JetBrains Mono',monospace";
Chart.defaults.font.size   = 10;

const C = { green:"#00ff88", cyan:"#00d4ff", blue:"#0ea5e9",
            purple:"#a78bfa", yellow:"#fbbf24", orange:"#f97316" };
const CH = {};
function kill(id){ if(CH[id]){CH[id].destroy();delete CH[id];} }
function base(x={}){
  return { responsive:true, maintainAspectRatio:false,
    animation:{duration:800,easing:"easeOutQuart"},
    plugins:{legend:{display:false},...x.plugins}, ...x };
}
const AXIS = (title)=>({grid:{color:"rgba(0,160,220,.07)"},ticks:{color:"#5a8a9f"},
  title:{display:!!title,text:title||"",color:"#5a8a9f",font:{size:10}}});

// ── helpers ──────────────────────────────────────────────
function esc(v){ return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function fmt(v,d=2){ return (v==null||!isFinite(+v))?"—":(+v).toFixed(d); }
function ci(e,d=3){ return e&&e.ci95?`95% CI ${(+e.ci95[0]).toFixed(d)}–${(+e.ci95[1]).toFixed(d)}`:""; }
// SoilGrids' own 90% interval for the stock (05_soilgrids_uncertainty), or the sampling CI in v1 mode
function soilRange(soil){
  const u=soil&&soil.soilgrids_uncertainty;
  if(u&&u.correlated_90pct_mtc) return `SoilGrids 90%: ${(+u.correlated_90pct_mtc[0]).toFixed(1)}–${(+u.correlated_90pct_mtc[1]).toFixed(1)} MtC`;
  return soil&&soil.stock_mtc&&soil.stock_mtc.ci95 ? ci(soil.stock_mtc,3)+" · sampling only" : "";
}
function setTxt(id,v){ const e=document.getElementById(id); if(e&&v!=null) e.textContent=v; }
function setBar(id,p){ const e=document.getElementById(id); if(e) e.style.width=Math.min(+p,100)+"%"; }
function countUp(id,target,dec=2,ms=1400){
  const el=document.getElementById(id); if(!el) return;
  if(target==null||!isFinite(+target)){ el.textContent="—"; return; }
  let start=null;
  const step=ts=>{ if(!start) start=ts; const p=Math.min((ts-start)/ms,1);
    el.textContent=(target*(1-Math.pow(1-p,4))).toFixed(dec); if(p<1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}
function makeHist(vals,bins=10){
  if(!vals.length) return{labels:[],counts:[]};
  const s=[...vals].sort((a,b)=>a-b), mn=s[Math.floor(.01*(s.length-1))], mx=s[Math.floor(.99*(s.length-1))];
  const st=(mx-mn)/bins||1, c=Array(bins).fill(0);
  vals.forEach(v=>{ if(v>=mn&&v<=mx) c[Math.min(Math.floor((v-mn)/st),bins-1)]++; });
  return{labels:c.map((_,i)=>(mn+i*st).toFixed(2)),counts:c};
}
function rows(tbody,html){ const t=document.getElementById(tbody); if(t) t.innerHTML=html; }
async function api(url){
  const r=await fetch(url);
  const body=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(body.error||`${url} → ${r.status}`);
  return body;
}
let SUMMARY=null, METRICS=null;
async function summary(){ return SUMMARY ??= await api("/api/summary"); }
async function metrics(){ return METRICS ??= await api("/api/metrics"); }

// ── NAVIGATION ───────────────────────────────────────────
function showPage(name){
  document.querySelectorAll(".page").forEach(p=>p.classList.remove("active"));
  document.querySelectorAll(".nav-link").forEach(a=>a.classList.remove("active"));
  document.getElementById("page-"+name)?.classList.add("active");
  document.querySelectorAll(".nav-link").forEach(a=>{
    if(a.textContent.trim().toLowerCase()===name) a.classList.add("active");
  });
  if(name==="map")       loadMap();
  if(name==="analytics") loadAnalytics();
  if(name==="model")     loadModel();
  if(name==="explorer")  { ePage=1; loadExplorer(); }
}
function showTab(id,btn){
  document.querySelectorAll(".tp").forEach(p=>p.classList.remove("active"));
  document.querySelectorAll(".tab").forEach(b=>b.classList.remove("active"));
  document.getElementById(id)?.classList.add("active");
  btn?.classList.add("active");
  if(id==="tf"&&window._fi) drawFI(window._fi);
}

// ── HOME ─────────────────────────────────────────────────
async function loadHome(){
  let s, m;
  try{ s=await summary(); }catch(e){
    setTxt("status-banner","Results unavailable: "+e.message);
    return;
  }
  try{ m=await metrics(); }catch(e){ console.warn(e); }
  const soil=s.soil, npp=s.npp, crop=s.crop_yield_crosscheck, prev=s.previous_published||{};
  countUp("kpi-soil",soil.stock_mtc.estimate,3); setTxt("kpi-soil-ci",soilRange(soil));
  countUp("kpi-density",soil.mean_density_tc_ha.estimate,2); setTxt("kpi-density-ci",ci(soil.mean_density_tc_ha,2));
  countUp("kpi-npp",npp.flux_mtc_per_year.estimate,3); setTxt("kpi-npp-ci",ci(npp.flux_mtc_per_year,3));
  if(crop){ countUp("kpi-crop",crop.total_mtc_median,2);
    setTxt("kpi-crop-ci",`90% range ${crop.total_mtc_p05_p95[0].toFixed(2)}–${crop.total_mtc_p05_p95[1].toFixed(2)}`); }
  const rf=m?.soc_experiment?.models?.find(x=>x.model==="Random forest");
  const co=m?.soc_experiment?.models?.find(x=>x.model==="Coordinates only");
  if(rf){ countUp("kpi-socr2",rf.r2,3); setTxt("kpi-socr2-ci",co?`coordinates alone: ${co.r2.toFixed(3)}`:""); }

  setTxt("nav-total",soil.stock_mtc.estimate.toFixed(2)+" MtC");
  setTxt("chip-cells",s.grid.cells.toLocaleString()+" cells");
  setTxt("chip-mode",s.mode==="v1-interim"?"v1 interim · provisional":"v2 census");
  setTxt("status-banner","");
  const b=document.getElementById("status-banner");
  if(b){
    const strong=document.createElement("strong");
    strong.textContent=(s.status||"").toUpperCase()+" · ";
    b.append(strong, s.mode==="v1-interim"
      ? "Computed from the existing Earth Engine exports after repairing their known defects. Re-run notebooks/00_gee_extraction.ipynb to replace this with a clean census."
      : "Computed from the validated v2 Earth Engine extraction.");
    b.append(` Run ${s.run_date} · data source: ${s.source}.`);
  }

  const change=(label,old,now,d)=>`<tr><td>${esc(label)}</td><td class="cmp-old">${esc(old)}</td><td class="cmp-new">${esc(now)}</td></tr>`;
  rows("changes-tbody",[
    change("SOC stock (MtC)", fmt(prev.soil_stock_mtc,4), fmt(soil.stock_mtc.estimate,4)),
    change("NPP flux (MtC/yr)", fmt(prev.npp_flux_mtc_per_year,4), fmt(npp.flux_mtc_per_year.estimate,4)),
    change("SOC model spatial R²", fmt(prev.soc_r2_spatial,3), rf?fmt(rf.r2,3):"—"),
    change("Grid cells", (prev.cells||0).toLocaleString(), s.grid.cells.toLocaleString()),
  ].join(""));
  setTxt("changes-why",prev.why_superseded?"Why: "+prev.why_superseded+".":"");
  rows("caveats",(s.caveats||[]).map(c=>`<li>${esc(c)}</li>`).join(""));

  setTxt("ib-area",`Grid area ${Math.round(s.grid.area_ha).toLocaleString()} ha`);
  setTxt("ib-coverage",`${(s.grid.coverage_of_official_area*100).toFixed(1)}% of Census area (${s.grid.official_area_ha.toLocaleString()} ha)`);
  setTxt("ib-cells",`${s.grid.cells.toLocaleString()} cells · soil data ${Math.round(soil.soil_area_ha.estimate).toLocaleString()} ha`);
  setTxt("ib-agri",s.grid.agri_cells!=null?`${s.grid.agri_cells.toLocaleString()} agricultural cells`:"");
  setTxt("ib-sample",s.grid.sampled_cells!=null?`Random sample: ${s.grid.sampled_cells.toLocaleString()} cells`:"Every cell observed");
  setTxt("ib-f-soil",s.formulas?.soil||"—"); setTxt("ib-f-npp",s.formulas?.npp||"—");
}

// ── MAP ──────────────────────────────────────────────────
// KEY ARCHITECTURE:
// #map-wrap  = position:sticky, height:calc(100vh - 60px), flex column
// #leaflet-map = flex:1, min-height:0  → fills all remaining space

let MAP=null, GJ_LAYER=null, GJ_DATA=null, MAP_LAYER="dem";
let CLICK_MARKER=null, AREA_LOADING=false;

// ── SEARCH ────────────────────────────────────────────────────
const LUDHIANA_PLACES = [
  {name:"Ludhiana City Centre",      lat:30.9010, lng:75.8573},
  {name:"Sahnewal",                  lat:30.8483, lng:75.9247},
  {name:"Doraha",                    lat:30.8075, lng:76.0322},
  {name:"Jagraon",                   lat:30.7894, lng:75.4742},
  {name:"Raikot",                    lat:30.6486, lng:75.6047},
  {name:"Malerkotla (border)",       lat:30.5308, lng:75.8812},
  {name:"Khanna",                    lat:30.7048, lng:76.2172},
  {name:"Machhiwara",                lat:30.9247, lng:76.1897},
  {name:"Sidhwan Bet",               lat:30.8833, lng:75.7000},
  {name:"Mullanpur Dakha",           lat:30.8561, lng:75.8178},
  {name:"Samrala",                   lat:30.8386, lng:76.1933},
  {name:"Payal",                     lat:30.6786, lng:76.0394},
  {name:"Sudhar",                    lat:30.9542, lng:75.8019},
  {name:"Dehlon",                    lat:30.8608, lng:75.9369},
  {name:"Jodhan",                    lat:30.8064, lng:75.8736},
  {name:"Khamano",                   lat:30.8025, lng:76.2822},
  {name:"Phillaur",                  lat:31.0197, lng:75.7906},
  {name:"Kartarpur (border)",        lat:31.0761, lng:75.6294},
  {name:"Ludhiana Railway Station",  lat:30.9042, lng:75.8576},
  {name:"PAU Ludhiana",              lat:30.9101, lng:75.8013},
];

let SEARCH_TIMEOUT=null;
function mapSearchInput(val){
  clearTimeout(SEARCH_TIMEOUT);
  const res=document.getElementById("map-search-results");
  if(!val||val.length<2){ res.classList.remove("open"); res.innerHTML=""; return; }
  SEARCH_TIMEOUT=setTimeout(()=>{
    // First search local list
    const q=val.toLowerCase();
    let matches=LUDHIANA_PLACES.filter(p=>p.name.toLowerCase().includes(q)).slice(0,6);
    // Also do a Nominatim API search for more specific places
    fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(val+' Ludhiana Punjab India')}&format=json&limit=4&bounded=1&viewbox=75.3,30.5,76.5,31.2`)
      .then(r=>r.json()).then(data=>{
        const apiResults=data.map(d=>({name:d.display_name.split(",").slice(0,2).join(", "),lat:parseFloat(d.lat),lng:parseFloat(d.lon)}));
        const all=[...matches,...apiResults].slice(0,7);
        renderSearchResults(all);
      }).catch(()=>{
        renderSearchResults(matches);
      });
  },300);
}

// Geocoder names come from a third party: build nodes, never interpolate into HTML.
function renderSearchResults(items){
  const res=document.getElementById("map-search-results");
  res.replaceChildren(...items.map(p=>{
    const d=document.createElement("div");
    d.className="map-sr-item"; d.textContent="📍 "+p.name;
    d.addEventListener("click",()=>mapSearchSelect(p.lat,p.lng,p.name));
    return d;
  }));
  res.classList.toggle("open", items.length>0);
}

function mapSearchSelect(lat,lng,name){
  document.getElementById("map-search-input").value=name;
  document.getElementById("map-search-results").classList.remove("open");
  if(!MAP) return;
  MAP.setView([lat,lng],14);
  // Load cells around the searched location
  loadAreaCells(lat,lng);
}

function mapSearchGo(){
  const val=document.getElementById("map-search-input").value.trim();
  if(!val) return;
  const q=val.toLowerCase();
  const match=LUDHIANA_PLACES.find(p=>p.name.toLowerCase().includes(q));
  if(match){ mapSearchSelect(match.lat,match.lng,match.name); return; }
  // fallback: Nominatim
  fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(val+' Ludhiana Punjab India')}&format=json&limit=1`)
    .then(r=>r.json()).then(data=>{
      if(data.length>0) mapSearchSelect(parseFloat(data[0].lat),parseFloat(data[0].lon),data[0].display_name.split(",")[0]);
    }).catch(()=>{});
}

// Close search results when clicking elsewhere
document.addEventListener("click",(e)=>{
  if(!e.target.closest(".map-search-wrap")){
    const res=document.getElementById("map-search-results");
    if(res) res.classList.remove("open");
  }
});

// ── INFO PANEL ────────────────────────────────────────────────
function showInfoPanel(lat,lng,features){
  const panel=document.getElementById("click-info-panel");
  const loading=document.getElementById("cip-loading");
  const data=document.getElementById("cip-data");
  const none=document.getElementById("cip-none");
  panel.style.display="block";

  if(!features||features.length===0){
    loading.style.display="none"; data.style.display="none"; none.style.display="block";
    return;
  }

  // Find nearest feature to clicked point
  // Each feature is a polygon — use centroid approximation
  let nearest=null, minDist=Infinity;
  features.forEach(f=>{
    const g=f.geometry;
    const coords=g.type==="MultiPolygon"?g.coordinates[0][0]:g.coordinates[0];
    const fLng=coords.reduce((s,c)=>s+c[0],0)/coords.length;
    const fLat=coords.reduce((s,c)=>s+c[1],0)/coords.length;
    const d=Math.pow(fLat-lat,2)+Math.pow(fLng-lng,2);
    if(d<minDist){ minDist=d; nearest=f; }
  });

  if(!nearest){ loading.style.display="none"; data.style.display="none"; none.style.display="block"; return; }

  const p=nearest.properties;
  loading.style.display="none";
  none.style.display="none";
  data.style.display="block";

  setTxt("cip-coords",`${p.cell_id}  ·  ${lat.toFixed(4)}°N, ${lng.toFixed(4)}°E`);
  setTxt("cip-soc",  fmt(p.soc,2));
  setTxt("cip-npp",  fmt(p.npp,3));
  setTxt("cip-dem",  p.dem!=null ? (+p.dem).toFixed(1)+" m" : "—");
  setTxt("cip-agri", p.agri===1 ? "Agricultural" : p.agri===0 ? "Non-agricultural" : "—");
  setTxt("cip-soil", p.soil_status||"—");
  setTxt("cip-extra",`SOC ${p.soc_gkg!=null?fmt(p.soc_gkg,2)+" g/kg":"content n/a"} (${p.soc_source||"—"}) · NPP ${p.npp_source||"—"} · BD ${fmt(p.bd,2)} g/cm³ · valid soil ${p.w_soil!=null?Math.round(p.w_soil*100)+"%":"—"}`);
}

function closeInfoPanel(){
  document.getElementById("click-info-panel").style.display="none";
  if(CLICK_MARKER){ MAP.removeLayer(CLICK_MARKER); CLICK_MARKER=null; }
}

// ── LOAD CELLS AROUND A POINT ─────────────────────────────────
async function loadAreaCells(lat,lng){
  if(AREA_LOADING) return;
  AREA_LOADING=true;

  // Show loading state in panel
  const panel=document.getElementById("click-info-panel");
  const loading=document.getElementById("cip-loading");
  const data=document.getElementById("cip-data");
  const none=document.getElementById("cip-none");
  panel.style.display="block";
  loading.style.display="block";
  data.style.display="none";
  none.style.display="none";
  loading.textContent="⏳ Loading all grid cells near this point…";

  // Show pulsing marker
  if(CLICK_MARKER) MAP.removeLayer(CLICK_MARKER);
  CLICK_MARKER=L.circleMarker([lat,lng],{
    radius:10,color:"#00d4ff",weight:2,fillColor:"#00d4ff",fillOpacity:0.35,
  }).addTo(MAP);

  setTxt("map-de",`⏳ Fetching cells near (${lat.toFixed(4)}, ${lng.toFixed(4)})…`);

  try{
    const gj=await api(`/api/geojson/area?lat=${lat}&lng=${lng}&size=0.045`);

    // Merge with existing cells (no duplicates)
    if(GJ_DATA&&GJ_DATA.features.length>0){
      const existingIds=new Set(GJ_DATA.features.map(f=>f.properties.cell_id));
      const newFeats=gj.features.filter(f=>!existingIds.has(f.properties.cell_id));
      GJ_DATA={type:"FeatureCollection",features:[...GJ_DATA.features,...newFeats]};
    } else {
      GJ_DATA=gj;
    }

    setTxt("map-de",`${GJ_DATA.features.length.toLocaleString()} polygons loaded · Click any gap to load more`);
    drawPolygons(GJ_DATA);

    // Show info for this click
    showInfoPanel(lat,lng,gj.features);

  }catch(err){
    console.error(err);
    setTxt("map-de","❌ Error loading area — check backend");
    loading.textContent="❌ Failed to load. Try again.";
  } finally {
    AREA_LOADING=false;
  }
}

// Basemaps with their required attribution. (Google's tile servers need an API
// key under its terms, so they are not used.)
const ESRI_ATTR="Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community";
const OSM_ATTR="© OpenStreetMap contributors";
const TILES = {
  sat:  [{url:"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr:ESRI_ATTR, maxZ:19}],
  hyb:  [{url:"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr:ESRI_ATTR, maxZ:19},
         {url:"https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", attr:ESRI_ATTR, maxZ:19}],
  str:  [{url:"https://tile.openstreetmap.org/{z}/{x}/{y}.png", attr:OSM_ATTR, maxZ:19}],
  dark: [{url:"https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", attr:OSM_ATTR+" © CARTO", maxZ:20, subs:"abcd"}],
};
function tileGroup(k){
  return L.layerGroup(TILES[k].map(t=>L.tileLayer(t.url,{attribution:t.attr,maxZoom:t.maxZ,subdomains:t.subs||"abc"})));
}
let TILE_L=null, ACTIVE_TILE="sat";

// 5-stop vivid colour ramp
function ramp(t){
  if(t<.2)  return `hsl(220,100%,62%)`;
  if(t<.4)  return `hsl(185,100%,52%)`;
  if(t<.6)  return `hsl(145,100%,48%)`;
  if(t<.8)  return `hsl(45, 100%,52%)`;
  return            `hsl(15, 100%,58%)`;
}

async function loadMap(){
  if(!MAP){
    MAP=L.map("leaflet-map",{
      center:[30.82,75.84],zoom:13,minZoom:3,maxZoom:20,
      zoomControl:false,preferCanvas:false,
    });
    L.control.zoom({position:"bottomright"}).addTo(MAP);
    L.control.scale({position:"bottomleft",imperial:false}).addTo(MAP);

    TILE_L=tileGroup("sat").addTo(MAP);

    MAP.on("zoomend",()=>{
      const b=document.getElementById("zoom-banner");
      if(b) b.classList.toggle("gone",MAP.getZoom()>=13);
    });

    // ── CLICK: load area cells + show info panel ──────────────
    MAP.on("click",async(e)=>{
      if(AREA_LOADING) return;
      const {lat,lng}=e.latlng;
      loadAreaCells(lat,lng);
    });
  }

  setTimeout(()=>{ MAP.invalidateSize(); },100);

  // Only fetch initial random sample once
  if(GJ_DATA){ drawPolygons(GJ_DATA); return; }

  setTxt("map-de","Fetching a random sample of grid cells…");
  try{
    const gj=await api("/api/geojson?limit=1200");
    GJ_DATA=gj;
    setTxt("mf-source","data: "+(gj.source||"—"));
    setTxt("map-de",
      `${gj.features.length.toLocaleString()} polygons loaded · 💡 Click anywhere on the map to load cells and see carbon data`);
    drawPolygons(gj);
  }catch(e){
    console.error(e);
    setTxt("map-de","Error loading data — ensure backend is running");
  }
}

const SRC_COL={"observed":"#00ff88","interpolated":"#fbbf24","no soil data":"#64748b","outside MOD17 domain":"#64748b"};
function layerValue(p,key){
  if(key==="dem")  return p.dem;
  if(key==="agri") return p.agnonag;
  if(key==="npp")  return p.npp;
  if(key==="soc")  return p.soc;
  return null;
}

function drawPolygons(gj){
  if(GJ_LAYER){ MAP.removeLayer(GJ_LAYER); GJ_LAYER=null; }
  const key=MAP_LAYER;
  const vals=gj.features.map(f=>layerValue(f.properties,key)).filter(v=>v!=null&&isFinite(v));
  const sorted=[...vals].sort((a,b)=>a-b);
  const q=t=>sorted.length?sorted[Math.min(sorted.length-1,Math.floor(t*(sorted.length-1)))]:0;
  const lo=q(.02), hi=q(.98);                         // robust colour range
  const mean=vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:NaN;

  const kp=document.getElementById("map-kpis"); if(kp) kp.style.display="flex";
  const unit=key==="npp"?" tC/ha/yr":key==="soc"?" tC/ha":key==="dem"?" m":"";
  if(key==="src"){
    const obs=gj.features.filter(f=>f.properties.soc_source==="observed").length;
    setTxt("mk-mean",obs.toLocaleString()+" observed"); setTxt("mk-max","—"); setTxt("mk-min","—");
    setTxt("leg-lo","interpolated"); setTxt("leg-hi","observed");
  } else {
    setTxt("mk-mean",isFinite(mean)?mean.toFixed(3)+unit:"—");
    setTxt("mk-max",vals.length?sorted[sorted.length-1].toFixed(3):"—");
    setTxt("mk-min",vals.length?sorted[0].toFixed(3):"—");
    setTxt("leg-lo",vals.length?lo.toFixed(2):"Low"); setTxt("leg-hi",vals.length?hi.toFixed(2):"High");
  }
  setTxt("mk-cnt",gj.features.length.toLocaleString());

  GJ_LAYER=L.geoJSON(gj,{
    style(f){
      const p=f.properties; let col;
      if(key==="src"){
        col=SRC_COL[p.soc_source]||"#64748b";
      } else if(key==="agri"){
        col=p.agri===1?`hsl(${140+(p.agnonag||0)*30},90%,50%)`:`hsl(210,70%,45%)`;
      } else {
        const v=layerValue(p,key);
        col=(v==null||!isFinite(v))?"#334155":ramp(Math.max(0,Math.min(1,(v-lo)/((hi-lo)||1))));
      }
      return {fillColor:col,fillOpacity:0.8,color:"rgba(255,255,255,0.35)",weight:1.2,opacity:1};
    },
    onEachFeature(f,layer){
      layer.bindPopup(popup(f.properties),{maxWidth:260});
      layer.on({
        mouseover(e){ e.target.setStyle({fillOpacity:1,weight:2.5,color:"#ffffff",opacity:0.9}); e.target.bringToFront(); },
        mouseout(e){ GJ_LAYER.resetStyle(e.target); },
      });
    }
  }).addTo(MAP);
}

function popup(p){
  const r=(l,v,c)=>`
    <div style="background:rgba(255,255,255,.05);border-radius:5px;padding:5px 9px">
      <div style="color:#1e4a62;font-size:.58rem;letter-spacing:1.2px;text-transform:uppercase">${esc(l)}</div>
      <div style="color:${c};font-weight:700;font-size:.82rem;margin-top:2px">${esc(v)}</div>
    </div>`;
  return `<div style="min-width:220px;font-family:'Space Grotesk',sans-serif">
    <div style="font-family:'Syne',sans-serif;font-weight:700;font-size:.9rem;color:#00d4ff;
         border-bottom:1px solid rgba(0,180,255,.2);padding-bottom:8px;margin-bottom:10px">${esc(p.cell_id)}</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:7px">
      ${r("SOC stock tC/ha", fmt(p.soc,2), "#0ea5e9")}
      ${r("NPP flux tC/ha/yr", fmt(p.npp,3), "#00ff88")}
      ${r("SOC source", p.soc_source||"—", "#8ab4c8")}
      ${r("NPP source", p.npp_source||"—", "#8ab4c8")}
      ${r("Class", p.agri===1?"Agricultural":"Non-agri", p.agri===1?"#00ff88":"#f97316")}
      ${r("DEM (m)", fmt(p.dem,1), "#fbbf24")}
    </div>
  </div>`;
}

function setLayer(l){
  MAP_LAYER=l;
  ["dem","agri","npp","soc","src"].forEach(k=>{
    document.getElementById("btn-"+k)?.classList.toggle("active", k===l);
  });
  if(GJ_DATA) drawPolygons(GJ_DATA);
}

function setTile(k){
  if(TILE_L) MAP.removeLayer(TILE_L);
  TILE_L=tileGroup(k).addTo(MAP);
  ACTIVE_TILE=k;
  if(GJ_LAYER) GJ_LAYER.bringToFront();
  ["sat","hyb","str","dark"].forEach(n=>{
    document.getElementById("ts-"+n)?.classList.toggle("active", n===k);
  });
}

// ── ANALYTICS ────────────────────────────────────────────
async function loadAnalytics(){
  let s;
  try{ s=await summary(); }catch(e){ setTxt("a-sub","Results unavailable: "+e.message); return; }
  const soil=s.soil, npp=s.npp, crop=s.crop_yield_crosscheck;
  setTxt("a-sub",`${s.mode} · ${s.status} · run ${s.run_date}`);
  setTxt("a-soil",fmt(soil.stock_mtc.estimate,3)); setTxt("a-soil-ci",soilRange(soil));
  setTxt("a-npp",fmt(npp.flux_mtc_per_year.estimate,3)); setTxt("a-npp-ci",ci(npp.flux_mtc_per_year,3));
  if(crop){ setTxt("a-crop",fmt(crop.total_mtc_median,2));
    setTxt("a-crop-ci",`90% range ${crop.total_mtc_p05_p95[0].toFixed(2)}–${crop.total_mtc_p05_p95[1].toFixed(2)}`); }

  const sens=list=>(list||[]).map(v=>`<tr><td>${esc(v.variant)}</td><td style="color:#e8f4f8;font-weight:700">${fmt(v.estimate,3)}</td><td>${v.ci95?fmt(v.ci95[0],3)+"–"+fmt(v.ci95[1],3):"—"}</td></tr>`).join("");
  rows("sens-soil",sens(soil.sensitivity)||'<tr><td colspan="3">Census mode: no sampling variants</td></tr>');
  rows("sens-npp",sens(npp.sensitivity)||'<tr><td colspan="3">Census mode: no sampling variants</td></tr>');
  if(crop){
    setTxt("crop-text",
      `Reported Ludhiana wheat and paddy yields, converted with IPCC (2019) factors, put at least `+
      `${crop.total_mtc_median.toFixed(2)} MtC/yr (90% range ${crop.total_mtc_p05_p95[0].toFixed(2)}–${crop.total_mtc_p05_p95[1].toFixed(2)}) `+
      `through the district's two main crops. Correctly scaled MOD17 reports ${npp.flux_mtc_per_year.estimate.toFixed(3)} MtC/yr — `+
      `${(crop.mod17_over_crop_ratio*100).toFixed(1)}% of that lower bound`+
      (npp.negative_share_agricultural>0?` — and negative annual NPP in ${(npp.negative_share_agricultural*100).toFixed(0)}% of agricultural cells`:"")+`. `+
      `The old dashboard figure looked plausible only because the product's scale factor had been skipped, inflating it tenfold.`);
  }

  let nd=[];
  try{ nd=await api("/api/ndvi"); }catch(e){ console.warn(e); }
  const sorted=[...nd].sort((a,b)=>a.sort_order-b.sort_order);
  const peak=season=>sorted.filter(d=>d.season===season).reduce((b,d)=>(!b||d.median_ndvi>b.median_ndvi)?d:b,null);
  const kp=peak("Kharif"), rp=peak("Rabi"), gap=sorted.reduce((b,d)=>(!b||d.missing_share>b.missing_share)?d:b,null);
  setTxt("ndvi-kharif",kp?`${kp.month} — ${kp.median_ndvi.toFixed(3)}`:"—");
  setTxt("ndvi-rabi",rp?`${rp.month} — ${rp.median_ndvi.toFixed(3)}`:"—");
  setTxt("ndvi-gap",gap?`${gap.month} — ${(gap.missing_share*100).toFixed(0)}% missing`:"—");
  kill("ndvi");
  const ctx=document.getElementById("chart-ndvi").getContext("2d");
  const g=ctx.createLinearGradient(0,0,0,290); g.addColorStop(0,"rgba(0,255,136,.32)"); g.addColorStop(1,"rgba(0,255,136,.02)");
  CH["ndvi"]=new Chart(ctx,{type:"line",
    data:{labels:sorted.map(d=>d.month),datasets:[{label:"Median NDVI",data:sorted.map(d=>d.median_ndvi),
      borderColor:C.green,borderWidth:2.5,pointBackgroundColor:sorted.map(d=>d.season==="Kharif"?C.green:d.season==="Rabi"?C.blue:C.yellow),
      pointBorderColor:"#020509",pointRadius:5,fill:true,backgroundColor:g,tension:0.35}]},
    options:base({plugins:{legend:{display:false},tooltip:{callbacks:{
      label:c=>` NDVI ${c.parsed.y.toFixed(3)} · ${(sorted[c.dataIndex].missing_share*100).toFixed(0)}% cells missing`}}},
      scales:{x:AXIS(),y:{...AXIS("Median NDVI"),min:0,max:1}}})});

  let gj={features:[]};
  try{ gj=await api("/api/geojson?limit=3000"); }catch(e){ console.warn(e); }
  const npv=gj.features.map(f=>f.properties.npp).filter(v=>v!=null);
  const sov=gj.features.map(f=>f.properties.soc).filter(v=>v!=null);
  setTxt("hist-n-npp",`${npv.length.toLocaleString()} random cells · tC/ha/yr`);
  setTxt("hist-n-soc",`${sov.length.toLocaleString()} random cells · tC/ha`);
  for(const [id,vals,col,title] of [["npp-hist",npv,C.green,"MOD17 NPP flux (tC/ha/yr)"],["soc-hist",sov,C.blue,"SOC stock (tC/ha)"]]){
    const h=makeHist(vals,12); kill(id);
    CH[id]=new Chart(document.getElementById("chart-"+id),{type:"bar",
      data:{labels:h.labels,datasets:[{data:h.counts,backgroundColor:col+"99",borderColor:col,borderWidth:1,borderRadius:3}]},
      options:base({plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>` ${c.parsed.y} cells`}}},
        scales:{x:AXIS(title),y:AXIS("cells")}})});
  }
}

// ── MODEL ────────────────────────────────────────────────
async function loadModel(){
  let m;
  try{ m=await metrics(); }catch(e){ setTxt("soc-note","Metrics unavailable: "+e.message); return; }
  const card=(key,exp,unit)=>{
    if(!exp){ setTxt(key+"-note","Not run in census mode: no model is needed."); return; }
    const rf=exp.models.find(x=>x.model==="Random forest"), co=exp.models.find(x=>x.model==="Coordinates only");
    const ring=document.getElementById("ring-"+key);
    setTimeout(()=>{ if(ring) ring.style.strokeDashoffset=251.2*(1-Math.max(0,rf.r2)); },300);
    setTxt("ring-"+key+"-t",(rf.r2*100).toFixed(1)+"%");
    setTxt(key+"-rmse",`${rf.rmse.toFixed(3)} ${unit}`);
    setTxt(key+"-coord",co.r2.toFixed(3));
    setTxt(key+"-n",exp.n.toLocaleString());
    setTxt(key+"-sd",`${exp.target_sd} ${unit}`);
    setTxt(key+"-note",`Beats coordinates alone by ${(rf.r2-co.r2).toFixed(3)} R². ${exp.validation}.`);
  };
  card("soc",m.soc_experiment,"t/ha");
  card("npp",m.npp_experiment,"gC/m²/yr");

  window._fi=(m.npp_experiment?.permutation_importance||[]).map(d=>({...d,type:d.feature.startsWith("NDVI")?"ndvi":"other"}));
  const tr=(t,name,r,n)=>`<tr><td style="color:${t==="SOC"?C.blue:C.green}">${esc(t)}</td><td>${esc(name)}</td>
    <td style="color:#e8f4f8;font-weight:700">${fmt(r.r2,3)}</td><td>${fmt(r.rmse,3)}</td><td>${fmt(r.mae,3)}</td><td>${n!=null?n.toLocaleString():"—"}</td></tr>`;
  let html="";
  for(const [t,exp] of [["SOC",m.soc_experiment],["NPP",m.npp_experiment]]) if(exp) exp.models.forEach(r=>html+=tr(t,r.model,r,exp.n));
  for(const [k,v] of Object.entries(m.interpolation||{}))
    html+=tr(k.startsWith("soc")?"SOC":"NPP",`Inverse-distance gap filling (random ${v.folds}-fold, k=${v.k})`,v,v.n);
  rows("cmp-tbody",html);
}

function drawFI(fi){
  if(!fi?.length) return;
  const s=[...fi].sort((a,b)=>a.importance-b.importance);
  kill("fi");
  CH["fi"]=new Chart(document.getElementById("chart-fi"),{type:"bar",
    data:{labels:s.map(d=>d.feature),datasets:[{data:s.map(d=>d.importance),
      backgroundColor:s.map(d=>d.type==="ndvi"?C.green:C.yellow),borderWidth:0,borderRadius:4}]},
    options:{indexAxis:"y",responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>` ${c.parsed.x.toFixed(4)} drop in R²`}}},
      scales:{x:AXIS("Drop in R² when the feature is shuffled"),y:{grid:{display:false},ticks:{color:"#8ab4c8"}}}}});
}

// ── EXPLORER ─────────────────────────────────────────────
let EROWS=[], ePage=1;
const EPP=100;

async function loadExplorer(){
  const tl=document.getElementById("tbl-load"), tb=document.getElementById("exp-tbl");
  if(tl){ tl.style.display="block"; tl.textContent="Loading…"; } if(tb) tb.style.display="none";
  let res={records:[],total:0};
  try{ res=await api(`/api/carbon?page=${ePage}&per_page=${EPP}`); }
  catch(e){ if(tl) tl.textContent="Unavailable: "+e.message; return; }
  EROWS=res.records||[];
  setTxt("ec-tot",(res.total||0).toLocaleString());
  buildPages(res.total||0,EPP);
  renderTbl();
}

function filtered(){
  const q=(document.getElementById("fs")?.value||"").toLowerCase().trim();
  const mn=parseFloat(document.getElementById("fmin")?.value), mx=parseFloat(document.getElementById("fmax")?.value);
  return EROWS.filter(d=>(!q||String(d.cell_id).toLowerCase().includes(q))
    &&(isNaN(mn)||(d.npp_flux_tc_ha_yr!=null&&d.npp_flux_tc_ha_yr>=mn))
    &&(isNaN(mx)||(d.npp_flux_tc_ha_yr!=null&&d.npp_flux_tc_ha_yr<=mx)));
}

function renderTbl(){
  const f=filtered();
  const mean=k=>{ const v=f.map(d=>d[k]).filter(x=>x!=null); return v.length?v.reduce((a,b)=>a+b,0)/v.length:null; };
  setTxt("ec-show",f.length+" cells");
  setTxt("ec-mnpp",fmt(mean("npp_flux_tc_ha_yr"),3)+" tC/ha/yr");
  setTxt("ec-msoc",fmt(mean("soc_stock_tc_ha"),2)+" tC/ha");
  rows("exp-tbody",f.slice(0,50).map(d=>`<tr>
    <td style="color:#00d4ff">${esc(d.cell_id)}</td><td>${esc(d.soil_status)}</td>
    <td>${fmt(d.soc_gkg,3)}</td><td style="color:#0ea5e9">${fmt(d.soc_stock_tc_ha,2)}</td><td class="src-tag">${esc(d.soc_source)}</td>
    <td style="color:#00ff88">${fmt(d.npp_flux_tc_ha_yr,3)}</td><td class="src-tag">${esc(d.npp_source)}</td></tr>`).join(""));
  const tl=document.getElementById("tbl-load"), tb=document.getElementById("exp-tbl");
  if(tl) tl.style.display="none"; if(tb) tb.style.display="table";
  const more=document.getElementById("exp-more");
  if(more){ more.style.display=f.length>50?"block":"none"; more.textContent=`Showing 50 of ${f.length}`; }

  const pts=f.filter(d=>d.npp_flux_tc_ha_yr!=null&&d.soc_stock_tc_ha!=null).map(d=>({x:d.npp_flux_tc_ha_yr,y:d.soc_stock_tc_ha}));
  kill("scatter");
  CH["scatter"]=new Chart(document.getElementById("chart-scatter"),{type:"scatter",
    data:{datasets:[{data:pts,backgroundColor:C.blue,pointRadius:3}]},
    options:base({scales:{x:AXIS("MOD17 NPP flux (tC/ha/yr)"),y:AXIS("SOC stock (tC/ha)")}})});
  const h=makeHist(f.map(d=>d.npp_flux_tc_ha_yr).filter(v=>v!=null),10);
  kill("ehist");
  CH["ehist"]=new Chart(document.getElementById("chart-ehist"),{type:"bar",
    data:{labels:h.labels,datasets:[{data:h.counts,backgroundColor:C.green+"99",borderColor:C.green,borderWidth:1,borderRadius:3}]},
    options:base({scales:{x:AXIS("MOD17 NPP flux (tC/ha/yr)"),y:AXIS("cells")}})});
}

function doFilter(){ renderTbl(); }
function buildPages(total,pp){
  const n=Math.ceil(total/pp), wrap=document.getElementById("pages");
  if(!wrap) return; wrap.innerHTML="";
  const first=Math.max(1,Math.min(ePage-3,n-7));
  for(let i=first;i<=Math.min(n,first+7);i++){
    const b=document.createElement("button");
    b.className="pgb"+(i===ePage?" active":""); b.textContent=i;
    b.onclick=()=>{ePage=i;loadExplorer();};
    wrap.appendChild(b);
  }
}
function doExport(){
  const cols=["cell_id","soil_status","soc_gkg","soc_stock_tc_ha","soc_source","npp_flux_tc_ha_yr","npp_source"];
  const csv=[cols.join(","),...filtered().map(d=>cols.map(c=>d[c]??"").join(","))].join("\n");
  const a=Object.assign(document.createElement("a"),{
    href:URL.createObjectURL(new Blob([csv],{type:"text/csv"})),download:`ludhiana_cells_page${ePage}.csv`});
  a.click();
}

// ── INIT ─────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded",async()=>{
  window.addEventListener("scroll",()=>{
    document.getElementById("navbar")?.classList.toggle("scrolled",window.scrollY>8);
  });
  try{ await loadHome(); }catch(e){ console.error(e); }
  const ldr=document.getElementById("ldr");
  if(ldr){ ldr.classList.add("out"); setTimeout(()=>ldr.remove(),550); }
});
