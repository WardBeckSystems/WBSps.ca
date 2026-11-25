"""Searchable catalog of the 2026 archive, plus 2026/search.html.

Usage: python3 make_catalog.py <path to 2026> [--no-thumbs] [--jobs N]

Writes 2026/_catalog/:
  catalog.json   one record per file: path, name, kind, size, section, category, model, year,
                 thumbnail, original path, and search text (from the file's .md note, or the
                 file itself for .md / .yaml / .json / .txt)
  catalog.js     the same records without their search text, as `window.WBS_CATALOG = ...`, so search.html works
                 from disk and shows its cards at once
  text/NN.js     the search text, in TEXT_SHARDS slices keyed by path (`window.WBS_TEXT_NN = {path: text}`); search.html
                 loads them only once someone types, and a new or changed file rewrites only its own slice
  thumbs/        320 px JPEG thumbnails of images and PDF first pages (only rebuilt when stale)
and 2026/search.html. Reads only 2026/; never the timeline database.
"""
import hashlib, html, json, multiprocessing, os, re, subprocess, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'tools'))
from module_layout import module_dir_of, note_for   # module files: note in <M>/OCR/, files in kind folders; elsewhere beside the file

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else '.')
THUMBS = '--no-thumbs' not in sys.argv
JOBS = int(sys.argv[sys.argv.index('--jobs') + 1]) if '--jobs' in sys.argv else 2
CAT = os.path.join(ROOT, '_catalog')
TH = os.path.join(CAT, 'thumbs')
SKIP_DIRS = {'_catalog', '_previews', 'timelines', '__pycache__', 'node_modules', 'extractors', '_sidecars', '_private'}   # extractors: the suite's code and OCR environments, not archive material
IMAGE = {'.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff', '.bmp', '.webp'}
KIND = {**{x: 'image' for x in IMAGE | {'.cr2', '.psd', '.pct', '.heic'}},
        '.pdf': 'pdf', '.docx': 'doc', '.doc': 'doc', '.wpd': 'doc', '.txt': 'text', '.rtf': 'doc',
        '.xlsx': 'sheet', '.xls': 'sheet', '.csv': 'sheet',
        '.dwg': 'drawing', '.dxf': 'drawing', '.svg': 'drawing', '.kicad_sch': 'kicad', '.kicad_sym': 'kicad',
        '.kicad_pro': 'kicad', '.cir': 'spice', '.md': 'notes', '.yaml': 'data', '.json': 'data', '.html': 'page'}
READ_AS_TEXT = {'.md', '.yaml', '.json', '.txt', '.cir', '.csv'}
TEXT_CAP = 6000
TEXT_SHARDS = 32
shard_of = lambda rel: int(hashlib.sha1(rel.encode()).hexdigest()[:4], 16) % TEXT_SHARDS
MODEL = re.compile(r'^(M\d{2,4}[A-Z]{0,3}|[A-Z]{1,4}\d{2,5}[A-Z]{0,3})$')


def is_sidecar(name, names, folder=''):
    if name.endswith(' (traced).dxf'):   # the drawing tracer's CAD file beside its drawing
        return True
    if name.endswith('.md') and os.path.basename(folder) == 'OCR' and module_dir_of(os.path.join(folder, name)) == os.path.dirname(folder).replace(os.sep, '/'):
        return True   # a module's OCR/ folder: the notes of the files in its kind folders
    m = re.match(r'^(.+)\.(md|[a-z]+\.json)$', name)
    return bool(m and m.group(1) in names)


def note_text(path):
    """Searchable text from a build note: drop markdown furniture, keep words."""
    try:
        with open(path, errors='replace') as f:
            t = f.read(200_000)
    except OSError:
        return '', {}
    meta = dict(re.findall(r'^- \*\*([^:*]+):\*\* (.+)$', t, re.M))
    t = re.sub(r'```\w*|[#*_>`|]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()[:TEXT_CAP], meta


def classify(rel):
    parts = rel.split('/')
    section = parts[0] if len(parts) > 1 else ''
    category = parts[1] if section in ('Modules', 'Products') and len(parts) > 2 else ''
    model = next((p for p in reversed(parts[:-1]) if MODEL.match(p)), '')
    if not model:
        m = re.match(r'^(?:\d{4}|19xx) - ([^ ]+) - ', parts[-1])
        model = m.group(1) if m else ''
    return section, category, model


def thumb_job(args):
    src, dst, kind = args
    try:
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            return dst
        if kind == 'pdf':
            stem = dst[:-4]
            r = subprocess.run(['pdftoppm', '-f', '1', '-l', '1', '-scale-to', '320', '-jpeg', '-jpegopt', 'quality=70',
                                '-singlefile', src, stem], capture_output=True, timeout=60)
            return dst if r.returncode == 0 and os.path.exists(dst) else None
        from PIL import Image
        with Image.open(src) as im:
            im.draft('RGB', (640, 640))
            im = im.convert('RGB')
            im.thumbnail((320, 320))
            im.save(dst, 'JPEG', quality=70)
        return dst
    except Exception:
        return None


def model_names():
    """{code: name} from the timeline database's modules.name (newer builds only)"""
    import sqlite3
    try:
        con = sqlite3.connect(f'file:{os.path.join(ROOT, "timelines", "wbs_timeline.db")}?mode=ro', uri=True)
        if 'name' in [r[1] for r in con.execute('pragma table_info(modules)')]:
            return {c: n.strip() for c, n in con.execute('select code, name from modules') if n and n.strip().lower() != 'price list'}
    except sqlite3.Error:
        pass
    return {}


def write_if_changed(path, text):
    """Leave a file that already holds this text alone, so its date (and the site's git) only moves when it changes."""
    try:
        if open(path, encoding='utf-8').read() == text:
            return
    except OSError:
        pass
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def main():
    os.makedirs(TH, exist_ok=True)
    model_name = model_names()
    records, jobs = [], []
    # browser-viewable conversions made by the timeline session (docx->pdf, tif/psd->png, dxf->svg, pcb->svg/html)
    try:
        previews = json.load(open(os.path.join(ROOT, '_previews', 'manifest.json')))
    except (OSError, ValueError):
        previews = {}
    for r, ds, fs in os.walk(ROOT):
        ds[:] = sorted(d for d in ds if d not in SKIP_DIRS and not d.startswith(('.', '_old_')))
        if os.path.relpath(r, ROOT).replace(os.sep, '/').startswith('Engineering/Scans'):
            ds[:] = []  # scan_ingest's working files; the scans enter the catalog once they are filed into 2026
            continue
        names = set(fs)
        for f in sorted(fs):
            if is_sidecar(f, names, r) or f.startswith('.') or f in ('index.html', 'search.html', 'status.html', 'viewer.html'):
                continue
            p = os.path.join(r, f)
            rel = os.path.relpath(p, ROOT).replace(os.sep, '/')
            ext = os.path.splitext(f)[1].lower()
            kind = KIND.get(ext, 'other')
            section, category, model = classify(rel)
            note = note_for(p)   # beside it, or <M>/OCR/<name>.md in a module's kind folder
            text, meta = note_text(note) if os.path.exists(note) else ('', {})
            if not text and ext in READ_AS_TEXT:
                with open(p, errors='replace') as fh:
                    text = re.sub(r'\s+', ' ', fh.read(TEXT_CAP * 2))[:TEXT_CAP]
                if f.endswith('(traced).json'):   # the sheet's number and title; the outlines after them are only coordinates
                    text = text.split('"outlines"')[0]
            year = meta.get('Year', '')[:4]
            m = re.match(r'^(\d{4}) - ', f)
            if not year.isdigit():
                year = m.group(1) if m else ''
            rec = {'p': rel, 'n': f, 'k': kind, 's': os.path.getsize(p), 'sec': section, 'cat': category or meta.get('Category', ''),
                   'm': model or meta.get('Module', ''), 'y': int(year) if year.isdigit() else None,
                   'o': meta.get('Original file', '').strip('`'), 'note': os.path.relpath(note, ROOT).replace(os.sep, '/') if os.path.exists(note) else '',
                   't': '', 'x': text, 'v': previews.get(rel, '')}
            rec['mn'] = model_name.get(rec['m'], '')
            # the model's typed page: index.html in the folder holding this file, else PAGES/<code>.html
            folder_page = os.path.join(module_dir_of(p) or r, 'index.html')   # a kind folder's file: the module's page
            rec['mp'] = (os.path.relpath(folder_page, ROOT).replace(os.sep, '/') if rec['m'] and os.path.exists(folder_page)
                         else f"PAGES/{rec['m']}.html" if rec['m'] and os.path.exists(os.path.join(ROOT, 'PAGES', rec['m'] + '.html')) else '')
            view = rec['v']
            if ext == '.svg':  # browsers draw SVG directly
                rec['t'] = rel
            elif view.endswith('.svg') and ext not in IMAGE:
                rec['t'] = view
            elif THUMBS:
                dst = os.path.join(TH, hashlib.sha1(rel.encode()).hexdigest()[:20] + '.jpg')
                if ext in IMAGE or ext == '.pdf':
                    jobs.append((len(records), (p, dst, 'pdf' if ext == '.pdf' else 'image')))
                elif view.endswith(('.png', '.pdf')):
                    jobs.append((len(records), (os.path.join(ROOT, view), dst, 'pdf' if view.endswith('.pdf') else 'image')))
            records.append(rec)
    if jobs:
        os.nice(10)
        with multiprocessing.Pool(JOBS) as pool:
            for (i, _), out in zip(jobs, pool.imap(thumb_job, [j for _, j in jobs], chunksize=16)):
                if out:
                    records[i]['t'] = os.path.relpath(out, ROOT).replace(os.sep, '/')
    payload = {'generated': __import__('datetime').date.today().isoformat(), 'count': len(records), 'files': records}
    with open(os.path.join(CAT, 'catalog.json'), 'w') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    shards = [{} for _ in range(TEXT_SHARDS)]
    for x in records:
        if x['x']:
            shards[shard_of(x['p'])][x['p']] = x['x']
    os.makedirs(os.path.join(CAT, 'text'), exist_ok=True)
    for i, sh in enumerate(shards):
        write_if_changed(os.path.join(CAT, 'text', f'{i:02d}.js'),
                         f'window.WBS_TEXT_{i:02d} = ' + json.dumps(sh, ensure_ascii=False, separators=(',', ':')) + ';\n')
    light = {**payload, 'text': TEXT_SHARDS, 'files': [{k: v for k, v in x.items() if k != 'x'} for x in records]}
    write_if_changed(os.path.join(CAT, 'catalog.js'),
                     'window.WBS_CATALOG = ' + json.dumps(light, ensure_ascii=False, separators=(',', ':')) + ';\n')
    with open(os.path.join(ROOT, 'search.html'), 'w') as f:
        f.write(SEARCH_HTML.replace('__VIEWER__', 'true' if os.path.exists(os.path.join(ROOT, 'viewer.html')) else 'false'))
    n_thumbs = sum(1 for x in records if x['t'])
    print(f'{len(records)} files catalogued, {n_thumbs} thumbnails, written to {CAT} and {ROOT}/search.html')


SEARCH_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>WBSps Archive Search</title>
<link rel="icon" href="WBS_Logo.svg">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Courier+Prime:wght@400;700&family=Michroma&display=swap">
<style>
/* Layout: the binder's card catalogue - a typed search slip on top, results as filing cards. Single look by design. */
:root { --vinyl: #141414; --card: #f4efdc; --paper: #fbfaf4; --type: #1c1c1c; --faint: #6d6a63; --rule: #1c1c1c;
  --red: #a52a22; --blue: #2a5ea0; --typewriter: "Courier Prime", "Courier New", Courier, monospace;
  --logotype: "Michroma", "Eurostile", "Arial Black", sans-serif; color-scheme: dark }
* { box-sizing: border-box }
body { margin: 0; background: var(--vinyl); color: var(--type); font: 15px/1.45 var(--typewriter);
  padding-block: 22px 60px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)) }
a { color: inherit }
a:focus-visible, input:focus-visible, button:focus-visible { outline: 2px dashed #e8e2c8; outline-offset: 3px }
.wrap { max-width: 1240px; margin: 0 auto; display: grid; gap: 22px }
.slip { background: var(--paper); color-scheme: light; padding: 22px clamp(16px, 4vw, 40px); display: grid; gap: 14px; box-shadow: 0 14px 30px rgba(0,0,0,.5) }
.top { display: flex; flex-wrap: wrap; gap: 10px 22px; align-items: baseline; justify-content: space-between }
h1 { margin: 0; font: 700 18px var(--typewriter); text-transform: uppercase; letter-spacing: .06em }
h1 u { text-underline-offset: 4px }
.logo { display: block; width: 150px }
.logo img { display: block; width: 100%; height: auto }
.query { display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap }
.query label { text-transform: uppercase; font-weight: 700 }
#q { flex: 1; min-width: 0; font: 20px var(--typewriter); color: var(--type); background: transparent; border: 0; border-bottom: 2px solid var(--rule); padding: 2px 4px }
.filters { display: grid; gap: 6px }
.frow { display: flex; flex-wrap: wrap; gap: 6px 8px; align-items: baseline }
.frow > span { width: 9ch; color: var(--faint); text-transform: uppercase; font-size: 12px }
.chip { font: 13px var(--typewriter); color: var(--type); background: transparent; border: 1px solid var(--faint); padding: 1px 8px; cursor: pointer }
.chip[aria-pressed="true"] { background: var(--type); color: var(--paper); border-color: var(--type) }
.status { color: var(--faint); font-size: 13px }
.cards { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr)); gap: 16px }
.card { position: relative; background: var(--card); color-scheme: light; padding: 12px 14px 12px; display: grid; gap: 6px; align-content: start;
  box-shadow: 0 6px 16px rgba(0,0,0,.45); background-image: linear-gradient(transparent 31px, rgba(42,94,160,.18) 32px, transparent 33px),
  repeating-linear-gradient(transparent 0 23px, rgba(42,94,160,.10) 23px 24px); background-position: 0 30px }
.card::before { content: ""; position: absolute; left: 50%; bottom: 8px; width: 12px; height: 12px; margin-left: -6px; border-radius: 50%; background: var(--vinyl); opacity: .85 }
.card .head { display: flex; justify-content: space-between; gap: 8px; font-weight: 700; text-transform: uppercase; min-height: 22px }
.card .head span { color: var(--red) }
.mname { font-size: 13px; text-transform: uppercase; margin-top: -4px }
.thumb { display: block; aspect-ratio: 4 / 3; background: #e4dec6; overflow: hidden; border: 1px solid #cfc8ae }
.thumb img { width: 100%; height: 100%; object-fit: contain; display: block; filter: grayscale(.15) contrast(1.05) }
.thumb .ph { display: grid; place-items: center; height: 100%; color: var(--faint); text-transform: uppercase; font-size: 13px }
.name { font-size: 13px; word-break: break-word }
.name a { text-decoration: none } .name a:hover { text-decoration: underline }
.meta { font-size: 12px; color: var(--faint); display: flex; flex-wrap: wrap; gap: 2px 12px }
.snip { font-size: 12.5px; color: #3a3833; margin: 0 0 14px; word-break: break-word }
mark { background: #f2d974; color: inherit; padding: 0 1px }
.more { justify-self: center; font: 700 14px var(--typewriter); text-transform: uppercase; background: var(--paper); color: var(--type); border: 0; padding: 8px 18px; cursor: pointer }
.empty { color: #e8e2c8; text-align: center; padding: 40px 0 }
</style>
</head>
<body>
<div class="wrap">
  <section class="slip" aria-label="Search">
    <div class="top">
      <h1><u>WBSps Archive Search</u></h1>
      <a class="logo" href="index.html" title="Back to the archive index"><img src="WBS_Logo.svg" alt="Ward-Beck Systems"></a>
    </div>
    <div class="query">
      <label for="q">Find:</label>
      <input id="q" type="search" placeholder="M441M  schematic  1973" autocomplete="off" spellcheck="false">
    </div>
    <div class="filters" id="filters"></div>
    <div class="status" id="status" aria-live="polite">Loading the catalog…</div>
  </section>
  <ul class="cards" id="cards"></ul>
  <button class="more" id="more" hidden>Show more cards</button>
</div>
<script src="_catalog/catalog.js"></script>
<script src="_catalog/drive_lookup.js"></script>
<script>
const CAT = window.WBS_CATALOG || { files: [] }, data = CAT.files;
const $ = id => document.getElementById(id);
const PAGE = 120;
const facets = { sec: 'Section', k: 'Kind', dec: 'Decade' };
const active = { sec: new Set(), k: new Set(), dec: new Set() };
let shown = PAGE, hits = [];
const hay = d => (d.n + ' ' + d.m + ' ' + (d.mn || '') + ' ' + d.cat + ' ' + d.sec + ' ' + (d.y || '') + ' ' + d.o + ' ' + d.x).toLowerCase();
data.forEach(d => {
  d.dec = d.y ? Math.floor(d.y / 10) * 10 + 's' : 'undated';
  d.x = d.x || '';
  d.hay = hay(d);
});
// the search text comes in CAT.text slices (_catalog/text/NN.js), fetched only once someone types; until they are all
// in, names, models, years and paths are searched and the status line says how much of the text is loaded
const byPath = new Map(data.map(d => [d.p, d]));
let textLeft = CAT.text || 0, textAsked = false;
function loadText() {
  if (textAsked || !textLeft) return;
  textAsked = true;
  for (let i = 0; i < CAT.text; i++) {
    const id = String(i).padStart(2, '0'), s = document.createElement('script');
    s.src = '_catalog/text/' + id + '.js?v=' + (CAT.generated || '');
    s.onload = s.onerror = () => {
      const sh = window['WBS_TEXT_' + id] || {};
      delete window['WBS_TEXT_' + id];
      for (const p in sh) { const d = byPath.get(p); if (d) { d.x = sh[p]; d.hay = hay(d); } }
      textLeft--;
      clearTimeout(textTimer); textTimer = setTimeout(() => run(true), textLeft ? 250 : 0);
      s.remove();
    };
    document.body.appendChild(s);
  }
}
let textTimer;
const enc = p => p.split('/').map(encodeURIComponent).join('/');
const VIEWER = __VIEWER__;  // viewer.html opens any file type, using its preview when there is one
const open = d => VIEWER ? 'viewer.html?f=' + encodeURIComponent(d.p) : enc(d.p);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function buildFilters() {
  const box = $('filters');
  for (const [key, label] of Object.entries(facets)) {
    const counts = {};
    data.forEach(d => counts[d[key] || 'other'] = (counts[d[key] || 'other'] || 0) + 1);
    const row = document.createElement('div');
    row.className = 'frow';
    row.innerHTML = `<span>${label}</span>` + Object.keys(counts).sort().map(v =>
      `<button class="chip" type="button" aria-pressed="false" data-key="${key}" data-val="${esc(v)}">${esc(v.replace(/-/g, ' '))} <small>${counts[v]}</small></button>`).join('');
    box.appendChild(row);
  }
  box.addEventListener('click', e => {
    const b = e.target.closest('.chip');
    if (!b) return;
    const set = active[b.dataset.key], v = b.dataset.val;
    set.has(v) ? set.delete(v) : set.add(v);
    b.setAttribute('aria-pressed', set.has(v));
    run();
  });
}

function snippet(d, terms) {
  if (!terms.length || !d.x) return esc(d.x.slice(0, 160));
  const low = d.x.toLowerCase();
  const at = Math.max(0, low.indexOf(terms[0]) - 60);
  let s = esc(d.x.slice(at, at + 200));
  terms.forEach(t => { s = s.replace(new RegExp('(' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'ig'), '<mark>$1</mark>'); });
  return (at ? '…' : '') + s + '…';
}

function card(d, terms) {
  // a thumbnail that is not on the website: wbsOff (drive_lookup.js) looks up its Google Drive copy, only when it is needed
  const lazyDrive = `data-f="${esc(d.p)}" data-size="320" onerror="wbsOff(this)"`;
  const thumb = d.t ? `<img loading="lazy" src="${enc(d.t)}" alt="" ${lazyDrive}>`
    : /\.(jpe?g|png|gif|tiff?|bmp|pdf)$/i.test(d.p) ? `<img loading="lazy" src="data:," alt="" ${lazyDrive}>` : `<span class="ph">${esc(d.k)}</span>`;
  return `<li class="card">
    <div class="head"><b>${d.mp ? `<a href="${enc(d.mp)}">${esc(d.m)}</a>` : esc(d.m || d.sec || '—')}</b><span>${d.y || ''}</span></div>
    ${d.mn ? `<div class="mname">${esc(d.mn)}</div>` : ''}
    <a class="thumb" href="${open(d)}" tabindex="-1">${thumb}</a>
    <div class="name"><a href="${open(d)}">${esc(d.n)}</a></div>
    <div class="meta"><span>${esc(d.sec)}${d.cat ? ' / ' + esc(d.cat) : ''}</span><span>${esc(d.k)}</span>${d.note ? `<a href="viewer.html?f=${encodeURIComponent(d.note)}">note</a>` : ''}</div>
    ${terms.length ? `<p class="snip">${snippet(d, terms)}</p>` : '<p class="snip"></p>'}
  </li>`;
}

function run(keep) {
  const terms = $('q').value.toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length) loadText();
  hits = data.filter(d => terms.every(t => d.hay.includes(t)) &&
    Object.entries(active).every(([k, set]) => !set.size || set.has(d[k] || 'other')));
  if (keep !== true) shown = PAGE;
  render(terms);
}

function render(terms = $('q').value.toLowerCase().split(/\s+/).filter(Boolean)) {
  $('cards').innerHTML = hits.length ? hits.slice(0, shown).map(d => card(d, terms)).join('')
    : '<li class="empty">No cards match. Try fewer words or clear a filter.</li>';
  $('more').hidden = shown >= hits.length;
  $('status').textContent = `${hits.length.toLocaleString()} of ${data.length.toLocaleString()} files` +
    (hits.length > shown ? ` · showing ${shown}` : '') +
    (textAsked && textLeft ? ` · loading the full text, ${CAT.text - textLeft} of ${CAT.text}` : '');
}

$('more').addEventListener('click', () => { shown += PAGE; render(); });
// load the next cards by itself when the "Show more" button scrolls into view
if ('IntersectionObserver' in window) {
  const io = new IntersectionObserver(es => {
    if (es.some(e => e.isIntersecting) && !$('more').hidden) {
      $('more').click();
      requestAnimationFrame(() => { io.unobserve($('more')); io.observe($('more')); });   // still in view? fire again
    }
  }, { rootMargin: '600px 0px' });
  io.observe($('more'));
}
let timer;
$('q').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(run, 150); });
if (!data.length) $('status').textContent = 'No catalog found. Run Engineering/_tools/make_catalog.py first.';
else { buildFilters(); run(); }
</script>
</body>
</html>
'''

if __name__ == '__main__':
    main()
