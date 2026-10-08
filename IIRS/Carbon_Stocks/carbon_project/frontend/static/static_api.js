/* ═══════════════════════════════════════════════════════════
   static_api.js — the Flask /api/* routes, answered in the browser

   Used by the public Streamlit app (app/streamlit_app.py), which has no Flask
   server. It embeds the pipeline results as window.__CARBON_DATA__ and loads
   this file before main.js; every fetch("/api/...") is then answered from that
   data with the same JSON the Flask backend returns in DB_MODE=files.
═══════════════════════════════════════════════════════════ */
(function(){
  "use strict";
  const D = window.__CARBON_DATA__;
  if(!D) return;
  const STEP = 0.002245788210302635, HALF = STEP/2 + 1e-4;
  const MAX_LIMIT = 3000, MAX_PER_PAGE = 500, MAX_HALF_WIDTH = 0.1;
  const c = D.cells, N = c.r.length;
  const ST = ["full","partial","nodata"];
  const id  = i => `r${c.r[i]}_c${c.c[i]}`;
  const lon = i => c.c[i]*STEP + STEP/2;
  const lat = i => c.r[i]*STEP + STEP/2;

  function props(i){
    return { cell_id:id(i), agri:c.a[i], agnonag:c.g[i], dem:c.e[i], slope:c.sl[i],
      soil_status:ST[c.st[i]], w_soil:c.w[i], bd:c.bd[i], soc_gkg:c.sg[i], soc:c.so[i],
      soc_source:D.soc_sources[c.ss[i]], npp:c.np[i], npp_source:D.npp_sources[c.ns[i]] };
  }
  function feature(i){
    const x0=c.c[i]*STEP, y0=c.r[i]*STEP, x1=x0+STEP, y1=y0+STEP;
    return { type:"Feature", properties:props(i),
      geometry:{ type:"Polygon", coordinates:[[[x0,y0],[x0,y1],[x1,y1],[x1,y0],[x0,y0]]] } };
  }
  // Deterministic random sample of n cells (seeded, like the Flask route's random_state)
  function sample(n){
    let s = 42 >>> 0;
    const rnd = () => { s = (s + 0x6D2B79F5) >>> 0; let t = s;
      t = Math.imul(t ^ t >>> 15, t | 1); t ^= t + Math.imul(t ^ t >>> 7, t | 61);
      return ((t ^ t >>> 14) >>> 0) / 4294967296; };
    const idx = Array.from({length:N}, (_,i)=>i);
    for(let k=0; k<n; k++){ const j = k + Math.floor(rnd()*(N-k)); [idx[k],idx[j]] = [idx[j],idx[k]]; }
    return idx.slice(0,n);
  }
  const fc = (feats, extra={}) => ({ type:"FeatureCollection", features:feats, total:feats.length, source:"files", ...extra });

  const routes = {
    "/api/summary": () => ({ ...D.summary, source:"files" }),
    "/api/metrics": () => ({ ...D.metrics, source:"files" }),
    "/api/ndvi":    () => D.ndvi,
    "/api/health":  () => ({ db_mode:"static", cells:N }),
    "/api/geojson": q => {
      const n = Math.max(1, Math.min(+q.get("limit") || 1200, MAX_LIMIT));
      return fc(sample(Math.min(n, N)).map(feature));
    },
    "/api/geojson/area": q => {
      const la = +(q.get("lat") ?? 30.82), ln = +(q.get("lng") ?? 75.84);
      const sz = Math.max(0.005, Math.min(+(q.get("size") ?? 0.045), MAX_HALF_WIDTH));
      const [x0,y0,x1,y1] = [ln-sz, la-sz, ln+sz, la+sz];
      const out = [];
      for(let i=0; i<N && out.length<MAX_LIMIT; i++){
        const x=lon(i), y=lat(i);
        if(x+HALF>=x0 && x-HALF<=x1 && y+HALF>=y0 && y-HALF<=y1) out.push(feature(i));
      }
      return fc(out, { bbox:{min_lng:x0, min_lat:y0, max_lng:x1, max_lat:y1} });
    },
    "/api/carbon": q => {
      const page = Math.max(1, parseInt(q.get("page")) || 1);
      const per = Math.max(1, Math.min(parseInt(q.get("per_page")) || 100, MAX_PER_PAGE));
      const records = [];
      for(let i=(page-1)*per; i<Math.min(page*per, N); i++){
        const p = props(i);
        records.push({ cell_id:p.cell_id, agri_class:p.agri, soil_status:p.soil_status, soc_gkg:p.soc_gkg,
          soc_stock_tc_ha:p.soc, soc_source:p.soc_source, npp_flux_tc_ha_yr:p.npp, npp_source:p.npp_source });
      }
      return { records, total:N, page, per_page:per, source:"files" };
    },
  };

  const realFetch = window.fetch.bind(window);
  window.fetch = function(input, init){
    const url = typeof input === "string" ? input : input.url;
    if(url.startsWith("/api/")){
      const u = new URL(url, "http://local");
      const route = routes[u.pathname];
      const [status, body] = route ? [200, route(u.searchParams)] : [404, { error:`${u.pathname} not found` }];
      return Promise.resolve(new Response(JSON.stringify(body), { status, headers:{ "Content-Type":"application/json" } }));
    }
    return realFetch(input, init);
  };
})();
