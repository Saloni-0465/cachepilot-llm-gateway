"""Self-contained local usage dashboard page."""

from fastapi.responses import HTMLResponse

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#101827">
  <title>CachePilot · Usage</title>
  <style>
    :root { color-scheme: light; --ink:#142033; --muted:#667085; --line:#e3e8ef; --paper:#fff; --canvas:#f4f7fb; --accent:#5c6cf5; --green:#16856a; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--canvas); color:var(--ink); font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    header { background:#101827; color:white; padding:22px max(24px,calc((100vw - 1080px)/2)); display:flex; align-items:center; justify-content:space-between; gap:20px; }
    .brand { font-weight:750; letter-spacing:.02em; font-size:18px; }
    .brand span { color:#9eabff; }
    .live { color:#b9c3d2; font-size:13px; }
    main { max-width:1080px; margin:38px auto; padding:0 24px 52px; }
    .heading { display:flex; justify-content:space-between; align-items:end; gap:20px; margin-bottom:23px; }
    h1 { font-size:29px; letter-spacing:-.04em; margin:0; }
    .sub { color:var(--muted); margin:5px 0 0; }
    form { background:var(--paper); border:1px solid var(--line); border-radius:13px; padding:16px; display:flex; align-items:end; gap:12px; box-shadow:0 3px 12px #152b4510; }
    label { display:block; font-weight:650; font-size:13px; margin-bottom:6px; }
    .key-wrap { flex:1; }
    input { width:100%; border:1px solid #ccd5e2; border-radius:8px; padding:11px 12px; font:inherit; outline:none; }
    input:focus { border-color:var(--accent); box-shadow:0 0 0 3px #5c6cf522; }
    button { background:var(--accent); border:0; border-radius:8px; color:white; font:inherit; font-size:14px; font-weight:650; padding:12px 17px; cursor:pointer; white-space:nowrap; }
    button:disabled { opacity:.65; cursor:wait; }
    .privacy { color:var(--muted); font-size:12px; margin:8px 2px 25px; }
    .message { min-height:22px; color:#b42318; font-size:13px; margin:-16px 2px 18px; }
    .grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:15px; }
    .card,.panel { background:var(--paper); border:1px solid var(--line); border-radius:13px; box-shadow:0 3px 12px #152b4508; }
    .card { padding:19px; min-height:123px; }
    .label { color:var(--muted); font-size:13px; font-weight:600; }
    .value { margin-top:14px; font-size:27px; letter-spacing:-.04em; font-weight:740; }
    .unit { font-size:14px; letter-spacing:0; color:var(--muted); font-weight:500; }
    .lower { display:grid; grid-template-columns:1fr 1fr; gap:15px; margin-top:15px; }
    .panel { padding:20px; min-height:190px; }
    h2 { margin:0 0 17px; font-size:16px; letter-spacing:-.02em; }
    .provider { display:flex; justify-content:space-between; padding:10px 0; border-top:1px solid var(--line); }
    .provider-name { font-weight:650; text-transform:capitalize; }
    .provider-count { color:var(--muted); }
    .empty { color:var(--muted); font-size:14px; }
    .foot { color:var(--muted); text-align:right; font-size:12px; margin-top:14px; }
    @media (max-width:760px) { .grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .heading { align-items:start; flex-direction:column; } }
    @media (max-width:500px) { header { padding:17px 20px; } main { margin:27px auto; padding:0 16px 36px; } form { align-items:stretch; flex-direction:column; } .lower { grid-template-columns:1fr; } .card { padding:15px; min-height:108px; } .value { font-size:23px; } }
  </style>
</head>
<body>
  <header><div class="brand">Cache<span>Pilot</span></div><div class="live">Local gateway analytics</div></header>
  <main>
    <div class="heading"><div><h1>Usage overview</h1><p class="sub">A snapshot of your gateway activity and cache performance.</p></div></div>
    <form id="connect-form">
      <div class="key-wrap"><label for="api-key">CachePilot API key</label><input id="api-key" type="password" autocomplete="off" placeholder="Paste the key configured for this server" required></div>
      <button id="load-button" type="submit">Load dashboard</button>
    </form>
    <p class="privacy">The key is sent only to this CachePilot server and is not saved by this page.</p>
    <div id="message" class="message" role="status" aria-live="polite"></div>
    <section class="grid" aria-label="Usage metrics">
      <article class="card"><div class="label">Total requests</div><div class="value" id="total">—</div></article>
      <article class="card"><div class="label">Failed requests</div><div class="value" id="failed">—</div></article>
      <article class="card"><div class="label">Cache hit rate</div><div class="value" id="hit-rate">—</div></article>
      <article class="card"><div class="label">Average latency</div><div class="value" id="latency">—</div></article>
      <article class="card"><div class="label">Estimated provider cost</div><div class="value" id="cost">—</div></article>
    </section>
    <section class="lower">
      <article class="panel"><h2>Provider usage</h2><div id="providers" class="empty">Load analytics to see provider activity.</div></article>
      <article class="panel"><h2>Estimated cost avoided</h2><div class="value" id="saved">—</div><p class="sub">Based on configured model rates. A dash means rates are unavailable.</p></article>
    </section>
    <div id="updated" class="foot"></div>
  </main>
  <script>
    const form = document.getElementById('connect-form');
    const button = document.getElementById('load-button');
    const message = document.getElementById('message');
    const number = new Intl.NumberFormat();
    const dollars = new Intl.NumberFormat(undefined, { style:'currency', currency:'USD', minimumFractionDigits:4, maximumFractionDigits:4 });
    function show(id, value) { document.getElementById(id).textContent = value; }
    function money(value) { return value === null || value === undefined ? '—' : dollars.format(value); }
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const key = document.getElementById('api-key').value;
      button.disabled = true;
      button.textContent = 'Loading…';
      message.textContent = '';
      try {
        const response = await fetch('/v1/analytics/summary', { headers: { Authorization: `Bearer ${key}` } });
        if (response.status === 401) throw new Error('That key was rejected. Check it matches CACHEPILOT_API_KEY on the server.');
        if (response.status === 503) throw new Error('Analytics storage is unavailable. Check that PostgreSQL is running.');
        if (!response.ok) throw new Error(`Could not load analytics (HTTP ${response.status}).`);
        const data = await response.json();
        show('total', number.format(data.total_requests));
        show('failed', number.format(data.failed_requests));
        show('hit-rate', `${data.cache_hit_rate_percent.toFixed(1)}%`);
        show('latency', data.average_latency_ms === null ? '—' : `${number.format(data.average_latency_ms)} ms`);
        show('cost', money(data.estimated_cost_usd));
        show('saved', money(data.estimated_cost_saved_usd));
        const providers = document.getElementById('providers');
        providers.replaceChildren();
        if (!data.providers.length) {
          providers.textContent = 'No logged requests yet. Send a chat completion, then reload.';
          providers.className = 'empty';
        } else {
          providers.className = '';
          for (const item of data.providers) {
            const row = document.createElement('div'); row.className = 'provider';
            const name = document.createElement('span'); name.className = 'provider-name'; name.textContent = item.name;
            const count = document.createElement('span'); count.className = 'provider-count'; count.textContent = `${number.format(item.requests)} requests`;
            row.append(name, count); providers.append(row);
          }
        }
        show('updated', `Updated ${new Date().toLocaleTimeString()}`);
      } catch (error) {
        message.textContent = error instanceof TypeError ? 'Could not reach CachePilot. Is the API server running?' : error.message;
      } finally {
        button.disabled = false;
        button.textContent = 'Load dashboard';
      }
    });
  </script>
</body>
</html>"""


def dashboard_page() -> HTMLResponse:
    """Render the local dashboard shell; analytics data still requires a key."""
    return HTMLResponse(content=DASHBOARD_HTML)
