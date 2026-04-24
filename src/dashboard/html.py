"""Static HTML for the dashboard index page.

Beginner-friendly single-page dashboard. Plain English labels, friendly
empty states, an inline equity sparkline, and a glossary so first-time
users can read the page without any trading background.
"""

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Trading Bot &mdash; Your Dashboard</title>
<style>
  :root {
    --bg-1:#0b0f1a; --bg-2:#131a2c; --panel:rgba(255,255,255,0.04);
    --panel-border:rgba(255,255,255,0.08); --text:#e8ecf3; --muted:#8b95a8;
    --accent:#5cf2c1; --pos:#4ade80; --neg:#f87171; --warn:#facc15;
    --info:#60a5fa; --shadow:0 10px 30px rgba(0,0,0,0.35);
  }
  *{box-sizing:border-box} html,body{margin:0;padding:0}
  body{
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Inter","Segoe UI",
         system-ui,sans-serif;
    color:var(--text);
    background:
      radial-gradient(1200px 800px at 10% -10%,#1d2547 0%,transparent 60%),
      radial-gradient(900px 600px at 90% 0%,#0e3a3a 0%,transparent 60%),
      linear-gradient(180deg,var(--bg-1),var(--bg-2));
    min-height:100vh;
  }
  .wrap{max-width:1180px;margin:0 auto;padding:24px 20px 60px}
  header{display:flex;align-items:center;justify-content:space-between;
         margin-bottom:24px;flex-wrap:wrap;gap:12px}
  .brand{display:flex;align-items:center;gap:10px;font-weight:700}
  .brand .logo{width:30px;height:30px;border-radius:9px;
    background:linear-gradient(135deg,var(--accent),var(--info));
    box-shadow:0 0 18px rgba(92,242,193,0.45)}
  .brand h1{margin:0;font-size:18px;letter-spacing:0.2px}
  .brand .tag{color:var(--muted);font-weight:500;font-size:12px;
              margin-left:4px}
  .status{display:inline-flex;align-items:center;gap:8px;
          color:var(--muted);font-size:13px}
  .dot{width:9px;height:9px;border-radius:50%;background:#555;
       transition:background .3s,box-shadow .3s}
  .dot.live{background:var(--pos);box-shadow:0 0 12px var(--pos)}
  .grid{display:grid;gap:16px}
  .grid.cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}
  .grid.cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}
  @media (max-width:760px){
    .grid.cols-3,.grid.cols-2{grid-template-columns:1fr}
  }
  .card{background:var(--panel);border:1px solid var(--panel-border);
        border-radius:16px;padding:18px 20px;backdrop-filter:blur(8px);
        box-shadow:var(--shadow)}
  .card h2{margin:0 0 4px;font-size:12px;font-weight:600;
           color:var(--muted);text-transform:uppercase;letter-spacing:.7px}
  .card .hint{color:var(--muted);font-size:12.5px;margin-top:4px;
              line-height:1.45}
  .stat .num{font-size:30px;font-weight:700;letter-spacing:-.5px;
             margin-top:6px}
  .stat .sub{font-size:12.5px;margin-top:6px;color:var(--muted)}
  .pos{color:var(--pos)} .neg{color:var(--neg)}
  .warn{color:var(--warn)} .info{color:var(--info)}
  .pill{display:inline-flex;align-items:center;gap:5px;
        padding:3px 10px;border-radius:999px;font-size:12px;
        background:rgba(255,255,255,.06);
        border:1px solid var(--panel-border)}
  .pill.pos{background:rgba(74,222,128,.12);
            border-color:rgba(74,222,128,.4);color:var(--pos)}
  .pill.neg{background:rgba(248,113,113,.12);
            border-color:rgba(248,113,113,.4);color:var(--neg)}
  .pill.warn{background:rgba(250,204,21,.10);
             border-color:rgba(250,204,21,.4);color:var(--warn)}
  table{width:100%;border-collapse:collapse;margin-top:10px;
        font-variant-numeric:tabular-nums}
  th,td{text-align:left;padding:10px 8px;font-size:14px;
        border-bottom:1px solid rgba(255,255,255,.06)}
  th{color:var(--muted);font-weight:600;font-size:11.5px;
     text-transform:uppercase;letter-spacing:.5px}
  td.muted,.muted{color:var(--muted)}
  .empty{color:var(--muted);font-style:italic;padding:14px 8px;
         text-align:center}
  .activity{list-style:none;padding:0;margin:10px 0 0}
  .activity li{display:flex;gap:12px;padding:10px 4px;align-items:center;
    border-bottom:1px solid rgba(255,255,255,.05)}
  .activity li:last-child{border-bottom:0}
  .activity .icon{width:30px;height:30px;border-radius:9px;flex:none;
    display:flex;align-items:center;justify-content:center;font-size:15px;
    background:rgba(255,255,255,.06)}
  .activity .meta{display:flex;flex-direction:column;min-width:0;flex:1}
  .activity .meta .t{font-weight:600;font-size:14px;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .activity .meta .s{font-size:12px;color:var(--muted)}
  details.help{margin-top:22px}
  details.help summary{cursor:pointer;color:var(--muted);
    font-size:13px;padding:10px 0;list-style:none}
  details.help summary::before{content:"\\25B8  ";color:var(--muted)}
  details[open].help summary::before{content:"\\25BE  "}
  details.help dl{display:grid;grid-template-columns:170px 1fr;
    gap:8px 18px;margin:10px 0 0}
  details.help dt{color:var(--text);font-weight:600;font-size:13px}
  details.help dd{margin:0;color:var(--muted);font-size:13px}
  .welcome{display:flex;gap:16px;align-items:flex-start}
  .welcome .emoji{font-size:30px;line-height:1}
  .welcome p{margin:0 0 4px}
  svg.spark{width:100%;height:70px;display:block;margin-top:12px}
  footer{margin-top:30px;color:var(--muted);font-size:12px;text-align:center}
</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="brand">
    <div class="logo"></div>
    <h1>Trading Bot <span class="tag">your dashboard</span></h1>
  </div>
  <div class="status">
    <span class="dot" id="dot"></span>
    <span id="status-text">Connecting&hellip;</span>
  </div>
</header>

<section class="card welcome" id="welcome">
  <div class="emoji">&#128075;</div>
  <div>
    <p><strong>New to trading?</strong> This page shows what your bot is
      doing in plain English.</p>
    <p class="muted">Your bot watches the markets, follows the rules you set,
      and only acts when conditions match. Numbers refresh every 5&nbsp;seconds.</p>
  </div>
</section>


<section class="grid cols-3" style="margin-top:16px">
  <div class="card stat">
    <h2>Account value</h2>
    <div class="num" id="equity-num">&mdash;</div>
    <div class="sub">Total money your bot is managing right now.</div>
  </div>
  <div class="card stat">
    <h2>Change this session</h2>
    <div class="num" id="pnl-num">&mdash;</div>
    <div class="sub">How much you&rsquo;re up or down since the bot started.</div>
  </div>
  <div class="card stat">
    <h2>Open positions</h2>
    <div class="num" id="pos-num">&mdash;</div>
    <div class="sub">Things the bot currently owns and is waiting to sell.</div>
  </div>
</section>

<section class="card" style="margin-top:16px">
  <h2>Account value over time</h2>
  <div class="hint">A quick visual of how your account has moved during this session.</div>
  <svg class="spark" id="spark" viewBox="0 0 600 70" preserveAspectRatio="none"></svg>
</section>

<section class="grid cols-2" style="margin-top:16px">
  <div class="card">
    <h2>What you own</h2>
    <div class="hint">Each row is something the bot bought and is holding.
      A negative quantity means a short position (betting the price will drop).</div>
    <table id="positions-table">
      <thead><tr><th>Market</th><th>Asset</th><th>Quantity</th><th>Bought at</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
  <div class="card">
    <h2>Market mood</h2>
    <div class="hint">How the bot reads each market right now. The bot only
      trades when the mood matches its strategy.</div>
    <table id="regime-table">
      <thead><tr><th>Asset</th><th>Mood</th><th>Last price</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</section>

<section class="card" style="margin-top:16px">
  <h2>Recent activity</h2>
  <div class="hint">The last things your bot did, newest first.</div>
  <ul class="activity" id="activity"></ul>
</section>

<details class="help">
  <summary>What do these words mean? (click to expand glossary)</summary>
  <dl>
    <dt>Account value</dt>
      <dd>Cash in the bot plus the current value of anything it owns.</dd>
    <dt>Position</dt>
      <dd>An asset the bot has bought (or sold short) and not yet closed.</dd>
    <dt>Market mood</dt>
      <dd>The bot&rsquo;s read of the market: trending up, trending down,
          sideways, or choppy. Strategies prefer specific moods.</dd>
    <dt>Strategy</dt>
      <dd>The set of rules the bot follows to decide when to buy or sell.</dd>
    <dt>Filled order</dt>
      <dd>An order that actually went through at the listed price.</dd>
    <dt>Bot waited</dt>
      <dd>The bot saw a setup but skipped it because the market mood
          wasn&rsquo;t right for that strategy.</dd>
    <dt>Paper mode</dt>
      <dd>Practice trading with fake money. Real prices, no real risk.</dd>
  </dl>
</details>

<footer>Refreshes every 5&nbsp;seconds &middot; All values shown in your account&rsquo;s base currency.</footer>

</div>

<script>
const REGIME_LABELS = {
  trending_up:    {label:'Strong uptrend',    tone:'pos',  emoji:'\\uD83D\\uDCC8'},
  trending_down:  {label:'Strong downtrend',  tone:'neg',  emoji:'\\uD83D\\uDCC9'},
  ranging:        {label:'Sideways / quiet',  tone:'warn', emoji:'\\u2194\\uFE0F'},
  high_volatility:{label:'Choppy / volatile', tone:'warn', emoji:'\\u26A1'},
  unknown:        {label:'Not enough data',   tone:'',     emoji:'\\u2753'}
};
const EVENT_ICONS = {
  start:'\\uD83D\\uDE80', stop:'\\uD83D\\uDED1',
  order:'\\u2705', regime_snapshot:'\\uD83C\\uDF24\\uFE0F',
  regime_change:'\\uD83D\\uDD04', regime_block:'\\u23F8\\uFE0F',
  risk_block:'\\uD83D\\uDEE1\\uFE0F',
  equity_snapshot:'\\uD83D\\uDCB0', error:'\\u26A0\\uFE0F'
};

async function j(url){const r=await fetch(url);return r.json();}
function fmt(n,d){
  if(n===null||n===undefined||Number.isNaN(Number(n)))return '\\u2014';
  return Number(n).toLocaleString(undefined,
    {minimumFractionDigits:d===undefined?2:d,
     maximumFractionDigits:d===undefined?2:d});
}
function fmtMoney(n){return n===null||n===undefined?'\\u2014':'$'+fmt(n);}
function timeAgo(iso){
  if(!iso)return '';
  const t=Date.parse(iso); if(Number.isNaN(t)) return iso;
  const s=Math.max(0,Math.round((Date.now()-t)/1000));
  if(s<60) return s+'s ago';
  if(s<3600) return Math.round(s/60)+'m ago';
  if(s<86400) return Math.round(s/3600)+'h ago';
  return Math.round(s/86400)+'d ago';
}
function describeOrder(p){
  const side=(p.side||'').toUpperCase()==='BUY'?'Bought':'Sold';
  const qty=fmt(p.qty,6); const sym=p.symbol||'';
  const price=p.fill_price?' @ '+fmtMoney(p.fill_price):'';
  const strat=p.strategy?' \\u00B7 '+p.strategy:'';
  return side+' '+qty+' '+sym+price+strat;
}
function describeEvent(e){
  const p=e.payload||{};
  switch(e.event){
    case 'order': return describeOrder(p);
    case 'regime_change':
      return 'Market mood changed for '+(p.symbol||'')+
             ' \\u2192 '+(p.regime||'?');
    case 'regime_block':
      return 'Bot waited on '+(p.symbol||'')+
             ' (mood: '+(p.regime||'?')+')';
    case 'risk_block':
      return 'Trade blocked: '+(p.reason||'risk limit');
    case 'equity_snapshot':
      return 'Account value updated: '+fmtMoney(p.equity);
    case 'start':
      return 'Bot started ('+(p.mode||'paper')+' mode)';
    case 'stop': return 'Bot stopped';
    case 'error': return 'Error: '+(p.message||'see logs');
    default: return e.event;
  }
}


function renderSpark(points){
  const svg=document.getElementById('spark');
  if(!points||points.length<2){
    svg.innerHTML='<text x="300" y="40" text-anchor="middle" '+
      'fill="#8b95a8" font-size="12">Waiting for data\\u2026</text>';
    return;
  }
  const W=600,H=70,pad=4;
  const ys=points.map(p=>p.equity);
  const min=Math.min.apply(null,ys), max=Math.max.apply(null,ys);
  const span=(max-min)||1;
  const step=(W-pad*2)/(points.length-1);
  const coords=points.map((p,i)=>{
    const x=pad+i*step;
    const y=H-pad-((p.equity-min)/span)*(H-pad*2);
    return [x,y];
  });
  const d='M '+coords.map(c=>c[0].toFixed(1)+' '+c[1].toFixed(1)).join(' L ');
  const area=d+' L '+(W-pad)+' '+(H-pad)+' L '+pad+' '+(H-pad)+' Z';
  const trend=ys[ys.length-1]>=ys[0]?'#4ade80':'#f87171';
  svg.innerHTML=
    '<defs><linearGradient id="sg" x1="0" x2="0" y1="0" y2="1">'+
    '<stop offset="0%" stop-color="'+trend+'" stop-opacity=".35"/>'+
    '<stop offset="100%" stop-color="'+trend+'" stop-opacity="0"/>'+
    '</linearGradient></defs>'+
    '<path d="'+area+'" fill="url(#sg)"/>'+
    '<path d="'+d+'" fill="none" stroke="'+trend+'" stroke-width="2"/>';
}

function renderPositions(rows){
  const tb=document.querySelector('#positions-table tbody');
  document.getElementById('pos-num').textContent=rows.length;
  if(!rows.length){
    tb.innerHTML='<tr><td colspan="4" class="empty">'+
      'Nothing held right now \\u2014 the bot is watching for a setup.</td></tr>';
    return;
  }
  tb.innerHTML=rows.map(p=>{
    const cls=Number(p.qty)>=0?'pos':'neg';
    return '<tr><td>'+(p.market||'')+'</td>'+
      '<td>'+(p.symbol||'')+'</td>'+
      '<td class="'+cls+'">'+fmt(p.qty,6)+'</td>'+
      '<td>'+fmtMoney(p.avg_price)+'</td></tr>';
  }).join('');
}

function renderRegime(rows){
  const tb=document.querySelector('#regime-table tbody');
  if(!rows.length){
    tb.innerHTML='<tr><td colspan="3" class="empty">'+
      'No market readings yet.</td></tr>';
    return;
  }
  tb.innerHTML=rows.map(r=>{
    const meta=REGIME_LABELS[r.regime]||REGIME_LABELS.unknown;
    const sym=(r.market?r.market+' \\u00B7 ':'')+(r.symbol||'');
    return '<tr><td>'+sym+'</td>'+
      '<td><span class="pill '+meta.tone+'">'+meta.emoji+
      ' '+meta.label+'</span></td>'+
      '<td>'+fmtMoney(r.price)+'</td></tr>';
  }).join('');
}

function renderActivity(events){
  const ul=document.getElementById('activity');
  const recent=(events||[]).slice().reverse().slice(0,15);
  if(!recent.length){
    ul.innerHTML='<li class="empty">No activity yet. '+
      'When the bot acts, it&rsquo;ll show up here.</li>';
    return;
  }
  ul.innerHTML=recent.map(e=>{
    const icon=EVENT_ICONS[e.event]||'\\u2022';
    return '<li><div class="icon">'+icon+'</div>'+
      '<div class="meta"><div class="t">'+describeEvent(e)+'</div>'+
      '<div class="s">'+timeAgo(e.ts)+'</div></div></li>';
  }).join('');
}

function setStatus(ok,text){
  document.getElementById('dot').classList.toggle('live',!!ok);
  document.getElementById('status-text').textContent=text;
}

async function refresh(){
  try{
    const h=await j('/health');
    setStatus(h.exists,h.exists?'Live \\u00B7 connected':'Waiting for data');

    const eq=await j('/equity?limit=200');
    const pts=eq.points||[];
    const last=pts[pts.length-1];
    const first=pts[0];
    document.getElementById('equity-num').textContent=
      last?fmtMoney(last.equity):'\\u2014';
    if(last&&first){
      const delta=last.equity-first.equity;
      const pct=first.equity?(delta/first.equity)*100:0;
      const sign=delta>=0?'+':'';
      const cls=delta>=0?'pos':'neg';
      const el=document.getElementById('pnl-num');
      el.textContent=sign+fmtMoney(delta)+'  ('+sign+fmt(pct,2)+'%)';
      el.className='num '+cls;
    }else{
      document.getElementById('pnl-num').textContent='\\u2014';
    }
    renderSpark(pts);

    const pos=await j('/positions');
    renderPositions(pos.positions||[]);

    const rg=await j('/regime');
    renderRegime(rg.regimes||[]);

    const jn=await j('/journal?limit=60');
    renderActivity(jn.events||[]);
  }catch(err){
    setStatus(false,'Connection error');
  }
}
refresh();
setInterval(refresh,5000);
</script>
</body>
</html>
"""
