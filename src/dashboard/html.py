"""Static HTML for the dashboard index page."""

INDEX_HTML = """<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\" />
<title>Trading Bot Dashboard</title>
<style>
  body { font: 14px/1.4 system-ui, sans-serif; margin: 20px; background: #111;
         color: #eee; }
  h1 { margin: 0 0 12px; font-size: 18px; }
  h2 { margin: 16px 0 6px; font-size: 14px; color: #9cf; }
  section { border: 1px solid #333; padding: 10px 12px; margin-bottom: 12px;
            border-radius: 6px; background: #1a1a1a; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border-bottom: 1px solid #2a2a2a; padding: 4px 8px; text-align: left;
           font-variant-numeric: tabular-nums; }
  th { color: #9cf; font-weight: 600; }
  .muted { color: #888; font-size: 12px; }
  .pill { display: inline-block; padding: 1px 6px; border-radius: 10px;
          background: #222; border: 1px solid #444; font-size: 11px; }
  .pos { color: #7c7; } .neg { color: #e77; }
  pre { margin: 0; white-space: pre-wrap; font-size: 12px; color: #bbb; }
</style>
</head>
<body>
<h1>Trading Bot <span class=\"muted\" id=\"health\"></span></h1>

<section>
  <h2>Equity</h2>
  <div id=\"equity-latest\" class=\"muted\">loading…</div>
  <table id=\"equity-table\"><thead><tr><th>Time</th><th>Total</th><th>By broker</th></tr></thead><tbody></tbody></table>
</section>

<section>
  <h2>Open positions</h2>
  <table id=\"positions-table\"><thead><tr><th>Market</th><th>Symbol</th><th>Qty</th><th>Avg price</th></tr></thead><tbody></tbody></table>
</section>

<section>
  <h2>Regime (latest per symbol)</h2>
  <table id=\"regime-table\"><thead><tr><th>Market</th><th>Symbol</th><th>Regime</th><th>Price</th><th>Time</th></tr></thead><tbody></tbody></table>
</section>

<section>
  <h2>Journal (tail)</h2>
  <pre id=\"journal\">loading…</pre>
</section>

<script>
async function j(url) { const r = await fetch(url); return r.json(); }

function fmt(n, d=2) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return Number(n).toLocaleString(undefined, {minimumFractionDigits: d, maximumFractionDigits: d});
}

async function refresh() {
  try {
    const h = await j('/health');
    document.getElementById('health').textContent =
      h.exists ? 'journal: ' + h.journal : '(no journal yet)';

    const eq = await j('/equity?limit=10');
    const tb = document.querySelector('#equity-table tbody');
    tb.innerHTML = '';
    (eq.points || []).slice().reverse().forEach(p => {
      const brokers = (p.brokers || []).map(b =>
        '<span class=\"pill\">' + b.market + ':' + fmt(b.equity) + '</span>').join(' ');
      tb.insertAdjacentHTML('beforeend',
        '<tr><td>' + (p.ts || '') + '</td><td>' + fmt(p.equity) +
        '</td><td>' + brokers + '</td></tr>');
    });
    const last = (eq.points || [])[eq.points.length - 1];
    document.getElementById('equity-latest').textContent =
      last ? ('Latest: $' + fmt(last.equity) + ' (' + eq.count + ' snapshots)')
           : 'No equity snapshots yet.';

    const pos = await j('/positions');
    const pb = document.querySelector('#positions-table tbody');
    pb.innerHTML = '';
    if (!pos.positions.length) pb.innerHTML = '<tr><td colspan=4 class=\"muted\">No open positions.</td></tr>';
    pos.positions.forEach(p => {
      const cls = p.qty >= 0 ? 'pos' : 'neg';
      pb.insertAdjacentHTML('beforeend',
        '<tr><td>' + p.market + '</td><td>' + p.symbol + '</td>' +
        '<td class=\"' + cls + '\">' + fmt(p.qty, 6) + '</td>' +
        '<td>' + fmt(p.avg_price) + '</td></tr>');
    });

    const rg = await j('/regime');
    const rb = document.querySelector('#regime-table tbody');
    rb.innerHTML = '';
    if (!rg.regimes.length) rb.innerHTML = '<tr><td colspan=5 class=\"muted\">No regime data.</td></tr>';
    rg.regimes.forEach(r => {
      rb.insertAdjacentHTML('beforeend',
        '<tr><td>' + (r.market || '') + '</td><td>' + (r.symbol || '') +
        '</td><td>' + (r.regime || '—') + '</td>' +
        '<td>' + fmt(r.price) + '</td><td>' + (r.ts || '') + '</td></tr>');
    });

    const jn = await j('/journal?limit=30');
    document.getElementById('journal').textContent =
      (jn.events || []).slice().reverse().map(e =>
        e.ts + '  ' + e.event + '  ' + JSON.stringify(e.payload)).join('\\n');
  } catch (e) {
    document.getElementById('health').textContent = 'error: ' + e;
  }
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""
