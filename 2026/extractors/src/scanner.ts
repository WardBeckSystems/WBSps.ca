// The scanner page: each dropped file goes to POST /api/scan (timelines/scan_one.py) and comes back read by the archive's
// extractors; the result card shows the sheet turned upright with its OCR boxes, and what was found.

interface Box { x0: number; y0: number; x1: number; y1: number; text: string; conf: number }
interface Drive { id: string; path: string; name: string; modified: string; public: boolean; view: string; preview: string; thumbnail: string }
interface Scan {
  file: string; size: number; sha256: string; md5: string; in_archive: string[]; drive: Drive | null;
  text: string; boxes: Box[]; read_by: string; rotation: { verdict: string; rotate: number; scores?: Record<string, number> } | null;
  title_block: Record<string, string | number>; models: { code: string; known: boolean; page: string }[];
  dates: { kind: string; year: number; text: string }[]; filing: { name: string; folder: string; year: number | null; code: string };
  error?: string; detail?: string;
}

const $ = (id: string) => document.getElementById(id) as HTMLElement;
const esc = (s: unknown) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!));
const wy = (y: number | null | undefined) => (y ? `${y}|${y - 1967}` : '19xx');   // Ward-Beck years: 1975|8
const arch = (p: string) => '/archive/' + p.split('/').map(encodeURIComponent).join('/');
const size = (b: number) => (b > 1e6 ? (b / 1e6).toFixed(1) + ' MB' : Math.round(b / 1e3) + ' kB');

// the extractors and what they have found so far
fetch('/api/extractors').then(r => r.json()).then((list: any[]) => {
  $('ext').innerHTML = list.map(x => `<li><b>${esc(x.step)}</b> · ${esc(x.script)}
    ${x.count != null ? `<span class="n">${Number(x.count).toLocaleString()} ${esc(x.unit)}</span>` : ''}<br><small>${esc(x.what)}</small></li>`).join('');
}).catch(() => { $('ext').innerHTML = '<li>Start the suite with <code>npm run dev</code> to see the extractors.</li>'; });

const queue: File[] = [];
let busy = false;
function add(files: FileList | File[]) {
  queue.push(...Array.from(files));
  next();
}
async function next() {
  $('queue').textContent = queue.length ? `${queue.length} waiting · each takes about half a minute on the GPU` : '';
  if (busy || !queue.length) return;
  busy = true;
  const f = queue.shift()!;
  const card = document.createElement('section');
  card.className = 'card';
  card.innerHTML = `<h3>${esc(f.name)}</h3><p class="state">Reading with the archive's extractors…</p>`;
  $('results').prepend(card);
  try {
    const r = await fetch('/api/scan?name=' + encodeURIComponent(f.name), { method: 'POST', body: f });
    const data = await r.json();
    if (!r.ok || data.error) throw new Error((data.error || r.status) + (data.detail ? '\n' + data.detail : ''));
    render(card, f, (data as Scan[])[0]);
  } catch (e) {
    card.querySelector('.state')!.innerHTML = `<span class="warn">The scan could not be read:</span> <pre>${esc(String(e))}</pre>`;
  }
  busy = false;
  next();
}

function render(card: HTMLElement, f: File, s: Scan) {
  const t = s.title_block || {};
  const rot = s.rotation;
  const turned = rot && rot.verdict.startsWith('rotate') ? rot.rotate : 0;
  const rows: [string, string][] = [
    ['Already in the archive', s.in_archive.length ? s.in_archive.map(d => `<a href="${arch(d)}">${esc(d)}</a>`).join('<br>') : '<span class="ok">no, it is new</span>'],
    ['Google Drive', s.drive ? `<a href="${esc(s.drive.view)}" target="_blank" rel="noopener">${esc(s.drive.path ? s.drive.path + '/' : '')}${esc(s.drive.name)}</a>
        · ${s.drive.public ? '<span class="ok">public</span>' : 'private (sign in)'} · saved ${esc(s.drive.modified.slice(0, 10))}` : 'not on the Drive (no file with the same MD5)'],
    ['Read by', esc(s.read_by)],
    ['Rotation', rot ? (turned ? `<span class="warn">turned ${turned}°</span> to read upright` : esc(rot.verdict)) +
      (rot.scores ? ` <small>(${Object.entries(rot.scores).map(([a, v]) => `${a}°: ${v}`).join(' · ')})</small>` : '') : '—'],
    ['Drawing', t.number ? `${esc(t.number)}${t.dtype_name ? ' · ' + esc(t.dtype_name) : ''}${t.sheet ? ' · sheet ' + esc(t.sheet) : ''}` : '—'],
    ['Title', esc(t.title || '—')],
    ['Date', t.date ? `${esc(t.date)} (${wy(Number(t.year))})` : '—'],
    ['Drawn · checked', [t.drawn, t.checked, t.approved].filter(Boolean).map(i => `<a href="/archive/PAGES/Person-${encodeURIComponent(String(i))}.html">${esc(i)}</a>`).join(' · ') || '—'],
    ['Issue', esc(t.issue || '—')],
    ['Models', s.models.length ? s.models.map(m => m.known ? `<a class="chip" href="${arch(m.page)}">${esc(m.code)}</a>` : `<span class="chip">${esc(m.code)}</span>`).join('') : '—'],
    ['Dates in it', s.dates.length ? s.dates.slice(0, 6).map(d => `<span class="chip">${wy(d.year)} · ${esc(d.text)}</span>`).join('') : '—'],
    ['File it as', `<b>${esc(s.filing.name)}</b><br>in <a href="${arch(s.filing.folder)}/">${esc(s.filing.folder)}</a> <button type="button" class="copy">Copy name</button>`],
    ['Fingerprints', `<small>${size(s.size)} · SHA-256 ${esc(s.sha256.slice(0, 16))}… · MD5 ${esc(s.md5)}</small>`],
  ];
  card.innerHTML = `<h3>${esc(s.file)}</h3>
    <div><canvas></canvas><details><summary>OCR text (${s.boxes.length} pieces)</summary><pre>${esc(s.text)}</pre></details></div>
    <dl class="facts">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>`;
  card.querySelector('.copy')?.addEventListener('click', ev => {
    const b = ev.target as HTMLButtonElement;
    navigator.clipboard.writeText(s.filing.name).then(() => (b.textContent = 'Copied'), () => (b.textContent = 'Select and copy'));
  });
  drawSheet(card.querySelector('canvas')!, f, turned, s.boxes);
}

/** The sheet turned upright, with the OCR's word boxes on it (the boxes are measured on the turned sheet). */
function drawSheet(cv: HTMLCanvasElement, f: File, turned: number, boxes: Box[]) {
  if (!/^image\//.test(f.type) || /tiff/.test(f.type)) {
    cv.replaceWith(Object.assign(document.createElement('p'), { className: 'state', textContent: 'No browser preview for this file type; the extractors read it all the same.' }));
    return;
  }
  const img = new Image();
  img.onload = () => {
    const side = turned === 90 || turned === 270;
    const W = side ? img.height : img.width, H = side ? img.width : img.height;
    const k = Math.min(1, 1400 / Math.max(W, H));
    cv.width = W * k; cv.height = H * k;
    const g = cv.getContext('2d')!;
    g.translate(cv.width / 2, cv.height / 2);
    g.rotate(-turned * Math.PI / 180);   // PIL turns counter-clockwise; the canvas turns clockwise
    g.drawImage(img, -img.width * k / 2, -img.height * k / 2, img.width * k, img.height * k);
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.lineWidth = 1.5;
    for (const b of boxes) {
      g.strokeStyle = /WARD|BECK|DRN|SCALE|ISSUE|WBS/i.test(b.text) ? '#a8442a' : 'rgba(31,63,107,.75)';
      g.strokeRect(b.x0 * cv.width, b.y0 * cv.height, (b.x1 - b.x0) * cv.width, (b.y1 - b.y0) * cv.height);
    }
    URL.revokeObjectURL(img.src);
  };
  img.src = URL.createObjectURL(f);
}

const drop = $('drop');
drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', e => { e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer?.files.length) add(e.dataTransfer.files); });
($('pick') as HTMLInputElement).addEventListener('change', e => { const fl = (e.target as HTMLInputElement).files; if (fl) add(fl); });
