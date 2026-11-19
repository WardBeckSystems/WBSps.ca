import { defineConfig, type Connect } from 'vite';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// The suite lives in 2026/extractors: its parent is the archive, served at /archive/ for browsing the catalog.
const HERE = fileURLToPath(new URL('.', import.meta.url));
const ARCHIVE = path.resolve(HERE, '..');
const TIMELINES = path.join(ARCHIVE, 'timelines');
const GPU_PYTHON = path.join(HERE, 'ocr_tool', 'venv-gpu', 'bin', 'python');
const INBOX = path.join(HERE, 'inbox');   // scans dropped on the scanner page are kept here until they are filed
const TYPES: Record<string, string> = {
  '.json': 'application/json', '.js': 'text/javascript', '.html': 'text/html', '.md': 'text/markdown; charset=utf-8',
  '.yaml': 'text/yaml; charset=utf-8', '.txt': 'text/plain; charset=utf-8', '.pdf': 'application/pdf',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.svg': 'image/svg+xml',
  '.tif': 'image/tiff', '.tiff': 'image/tiff', '.bmp': 'image/bmp', '.webp': 'image/webp',
};

const serveArchive: Connect.NextHandleFunction = (req, res, next) => {
  if (!req.url?.startsWith('/archive/')) return next();
  const rel = decodeURIComponent(req.url.slice('/archive/'.length).split('?')[0]);
  const file = path.join(ARCHIVE, rel);
  if (!file.startsWith(ARCHIVE + path.sep)) {
    res.statusCode = 403;
    return res.end();
  }
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) {
      res.statusCode = 404;
      return res.end();
    }
    res.setHeader('Content-Type', TYPES[path.extname(file).toLowerCase()] ?? 'application/octet-stream');
    res.setHeader('Content-Length', st.size);
    fs.createReadStream(file).pipe(res);
  });
};

/** Run a timelines/ script and send what it prints (JSON) back. */
function runJson(res: any, cmd: string, args: string[], env: Record<string, string> = {}) {
  const p = spawn(cmd, args, { cwd: TIMELINES, env: { ...process.env, ...env } });
  let out = '', err = '';
  p.stdout.on('data', d => (out += d));
  p.stderr.on('data', d => (err += d));
  p.on('close', code => {
    res.setHeader('Content-Type', 'application/json');
    if (code === 0) return res.end(out);
    res.statusCode = 500;
    res.end(JSON.stringify({ error: `${path.basename(args[0])} stopped (${code})`, detail: err.split('\n').filter(l => !/warn/i.test(l)).slice(-6).join('\n') }));
  });
}

// GET /api/extractors   every pipeline extractor and what it has found (timelines/extractors.py)
// POST /api/scan?name=  the scanner page: the upload is kept in inbox/<date>/ and read by timelines/scan_one.py
// GET /api/file?path=   everything the archive's extractors know about one filed file (timelines/file_facts.py)
// GET /api/training?path=  one drawing's training record for the SVG tracer (timelines/make_training.py)
// GET /api/drive        the archive's Google Drive links (2026 path → [id, resource key, public])
let training = new Map<string, unknown>(), trainingAt = -1;   // drawings.json, read again when it changes
const api: Connect.NextHandleFunction = (req, res, next) => {
  const url = new URL(req.url ?? '/', 'http://x');
  if (url.pathname === '/api/extractors') return runJson(res, 'python3', ['-I', 'extractors.py']);
  if (url.pathname === '/api/file') return runJson(res, 'python3', ['-I', 'file_facts.py', url.searchParams.get('path') || '']);
  if (url.pathname === '/api/training') {   // one drawing's training record (timelines/make_training.py)
    const f = path.join(HERE, 'training', 'drawings.json');
    const st = fs.existsSync(f) ? fs.statSync(f).mtimeMs : 0;
    if (st !== trainingAt) { trainingAt = st; training = st ? new Map(JSON.parse(fs.readFileSync(f, 'utf8')).map((r: any) => [r.path, r])) : new Map(); }
    const rec = training.get(url.searchParams.get('path') || '');
    res.setHeader('Content-Type', 'application/json');
    if (!rec) res.statusCode = 404;
    return res.end(JSON.stringify(rec ?? null));
  }
  if (url.pathname === '/api/drive') {
    const f = path.join(ARCHIVE, '_catalog', 'drive.js');
    res.setHeader('Content-Type', 'application/json');
    return res.end(fs.existsSync(f) ? fs.readFileSync(f, 'utf8').replace(/^[^=]*=\s*/, '').replace(/;\s*$/, '') : '{}');
  }
  if (url.pathname === '/api/scan' && req.method === 'POST') {
    const name = path.basename(url.searchParams.get('name') || 'scan').replace(/[^\w .()&+,'-]/g, '_') || 'scan';
    const dir = path.join(INBOX, new Date().toISOString().slice(0, 10));
    fs.mkdirSync(dir, { recursive: true });
    let file = path.join(dir, name);
    for (let n = 2; fs.existsSync(file); n++) file = path.join(dir, name.replace(/(\.[^.]*)?$/, ` (${n})$1`));
    const chunks: Buffer[] = [];
    req.on('data', (c: Buffer) => chunks.push(c));
    req.on('end', () => {
      fs.writeFileSync(file, Buffer.concat(chunks));
      runJson(res, fs.existsSync(GPU_PYTHON) ? GPU_PYTHON : 'python3', ['scan_one.py', file], { OCR_GPU: '1' });
    });
    return;
  }
  next();
};

export default defineConfig({
  plugins: [{
    name: 'wbs-archive',
    configureServer: server => { server.middlewares.use(api); server.middlewares.use(serveArchive); },
    configurePreviewServer: server => { server.middlewares.use(api); server.middlewares.use(serveArchive); },
  }],
  // the OCR environments (13 GB of torch / CUDA), node modules, Rust build and scanner inbox are not source: never watch them
  server: { watch: { ignored: ['**/ocr_tool/**', '**/node_modules/**', '**/rust_analyzer/target/**', '**/inbox/**', '**/dist/**'] } },
  build: {
    rollupOptions: {
      input: { main: path.join(HERE, 'index.html'), scanner: path.join(HERE, 'scanner.html') },
    },
  },
});
