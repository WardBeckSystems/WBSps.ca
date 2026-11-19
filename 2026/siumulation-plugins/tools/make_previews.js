#!/usr/bin/env node
/* Preview pictures for siumulation-index.html: one PNG per ready plugin, its front panel as the simulator draws it.

   usage: node siumulation-plugins/tools/make_previews.js [id …]      (no ids: every "ready" plugin in plugins.js)
          --force   redraw previews that already exist and are newer than the plugin file

   Opens siumulation.html?plugin=<id>#<first tab> in headless Chrome (DevTools protocol over Node's own WebSocket, nothing
   to install), takes the first large panel drawing in the view (an <svg>, <img> or, failing those, the first card) and saves
   siumulation-plugins/previews/<id>.png. The index shows it on the product's card; a product with no preview shows none.
*/
const fs = require('fs'), path = require('path'), os = require('os'), { spawn } = require('child_process');

const PLUG = path.resolve(__dirname, '..'), ROOT = path.dirname(PLUG), OUT = path.join(PLUG, 'previews');
const CHROME = ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium'].find(f => fs.existsSync(f));
const PORT = 9333 + Math.floor(Math.random() * 500);
const args = process.argv.slice(2), force = args.includes('--force'), ids = args.filter(a => !a.startsWith('--'));

global.window = {};
eval(fs.readFileSync(path.join(PLUG, 'plugins.js'), 'utf8'));   // window.SIM_CATALOG
const cat = (window.SIM_CATALOG || []).filter(e => e.status === 'ready' && (!ids.length || ids.includes(e.id)));
fs.mkdirSync(OUT, { recursive: true });

const sleep = ms => new Promise(r => setTimeout(r, ms));

// what to photograph: the first sizeable panel drawing in the opened view
const PICK = `((canvasOk) => {
  try { if (window.SIM && SIM.seek && !window.__seeked) { window.__seeked = 1; SIM.seek(Math.min(0.5, (SIM.duration || 1) / 2)); } } catch (_) {}   // mid-second: meters and displays lit
  for (const sel of ['header.top', '#transport', '#tabs', '.footer']) { const x = document.querySelector(sel); if (x) x.style.display = 'none'; }
  const main = document.querySelector('#main');
  if (!main) return null;
  const ok = el => { const r = el.getBoundingClientRect(); return r.width >= 120 && r.height >= 50 && r.width * r.height >= 24000 && !el.parentElement.closest('svg'); };   // tall meter towers count too
  const area = el => { const r = el.getBoundingClientRect(); return r.width * Math.min(r.height, 900); };
  const big = list => list.filter(ok).sort((a, b) => area(b) - area(a))[0];   // the largest drawing: the card, not its DIP-switch key
  let el = big([...main.querySelectorAll('svg, img')])
        || (canvasOk && ([...main.querySelectorAll('canvas')].find(ok) || main.querySelector('.card')));
  if (!el) return null;
  el.scrollIntoView({block: 'start'});
  const r = el.getBoundingClientRect();
  return {x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: Math.min(r.height, 900), tag: el.tagName};
})`;

async function main() {
  if (!CHROME) throw new Error('no Chrome found');
  const prof = fs.mkdtempSync(path.join(os.tmpdir(), 'wbs-prev-'));
  const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${prof}`, '--no-first-run',
    '--allow-file-access-from-files', '--hide-scrollbars', '--window-size=1400,1100', 'about:blank'], { stdio: 'ignore' });
  let ver;
  for (let i = 0; i < 50 && !ver; i++) { await sleep(200); ver = await fetch(`http://127.0.0.1:${PORT}/json/list`).then(r => r.json()).catch(() => null); }
  const page = ver.find(t => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  let n = 0; const wait = {}, events = [];
  ws.onmessage = m => { const d = JSON.parse(m.data); if (d.id && wait[d.id]) { wait[d.id](d); delete wait[d.id]; } else if (d.method) events.push(d.method); };
  const send = (method, params = {}) => new Promise(r => { const id = ++n; wait[id] = r; ws.send(JSON.stringify({ id, method, params })); });
  await send('Page.enable');
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'light' }] });
  const done = [], failed = [];
  for (const e of cat) {
    const out = path.join(OUT, e.id + '.png'), src = path.join(PLUG, e.file);
    if (!force && fs.existsSync(out) && fs.existsSync(src) && fs.statSync(out).mtimeMs > fs.statSync(src).mtimeMs) continue;
    // the first tab with a panel drawing; a timeline canvas or the first card only if no tab has one
    const tabs = (e.tabs && e.tabs.length ? e.tabs : [{ id: 'sim' }]).map(t => t.id);
    let r2 = null;
    for (const pass of [false, true]) {
      for (const tab of pass ? tabs.slice(0, 1) : tabs.slice(0, 4)) {
        const url = 'file://' + path.join(ROOT, 'siumulation.html').split('/').map(encodeURIComponent).join('/') + `?plugin=${encodeURIComponent(e.id)}#${tab}`;
        events.length = 0;
        await send('Page.navigate', { url });
        for (let i = 0; i < 60 && !events.includes('Page.loadEventFired'); i++) await sleep(100);
        await sleep(1800);   // the plugin script loads after the page, then draws
        const ex = `${PICK}(${pass})`;
        if ((await send('Runtime.evaluate', { expression: ex, returnByValue: true })).result?.result?.value) {
          await sleep(250);
          r2 = (await send('Runtime.evaluate', { expression: ex, returnByValue: true })).result?.result?.value;
        }
        if (r2) break;
      }
      if (r2) break;
    }
    if (!r2) { failed.push(e.id); continue; }
    const scale = Math.min(1, 720 / r2.w);
    const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true,
      clip: { x: r2.x, y: r2.y, width: r2.w, height: r2.h, scale } });
    if (!shot.result) { failed.push(e.id); continue; }
    fs.writeFileSync(out, Buffer.from(shot.result.data, 'base64'));
    done.push(`${e.id} (${r2.tag.toLowerCase()} ${Math.round(r2.w)}×${Math.round(r2.h)})`);
    process.stdout.write(`\r${done.length + failed.length}/${cat.length} ${e.id}            `);
  }
  ws.close(); chrome.kill();
  await sleep(800);
  try { fs.rmSync(prof, { recursive: true, force: true }); } catch (_) { /* Chrome still closing: the temp folder stays */ }
  console.log(`\npreviews: ${done.length} drawn, ${failed.length} with nothing to show${failed.length ? ': ' + failed.join(', ') : ''} -> ${OUT}`);
}
main().catch(e => { console.error(e); process.exit(1); });
