"""OCR, tag, plot and propose a home for every file in an unsorted folder.

Usage (with the EasyOCR venv):
  public/extractors/ocr_tool/venv/bin/python scan_ingest.py <source folder> <out folder>
      --archive <path to 2026> [--workers 2] [--limit N]

Reads the source read-only. Writes into <out>:
  scans.db            table `scans`: one row per file - text, tags, kind, proposed home, confidence, reasons
  ocr/<rel>.ocr.json  full OCR result with boxes (EasyOCR detail=1), for re-parsing price lists
  render/<rel>.svg    HPGL plots drawn as SVG (and .png used for OCR)
  thumbs/             320 px thumbnails
  index.html          contact sheet grouped by proposed home; assign homes by hand and export them
  assignments.json    (you save it here from index.html) manual homes, applied on the next run
Re-running skips files whose SHA-256 is unchanged, so it can be stopped and resumed.

Text by type: images -> EasyOCR (grey, <= 2200 px, plus the bottom-right title-block crop on drawings);
pdf -> text layer or OCR at 150 dpi; docx -> XML text; WordPerfect -> LibreOffice text;
eps/ps -> Ghostscript then OCR; wpg/cdr -> LibreOffice PDF then OCR; HPGL .plt -> own renderer then OCR;
dxf -> TEXT/MTEXT entities; listings and sources -> plain text; dwg, OrCAD and other binaries -> printable strings.
Homes are canonical codes from the timeline database's `modules` table or job numbers from `jobs`.
Confidence: manual > high > medium > low > none.
"""
import argparse, collections, hashlib, html, json, math, multiprocessing, os, re, sqlite3, subprocess, sys, tempfile, time, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # titles.py sits next to this script (works under python -I)
from titles import title_info, safe_filename

IMAGE = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.gif', '.psd'}
TEXT = {'.lst', '.asm', '.net', '.src', '.bom', '.inf', '.rep', '.err', '.mac', '.dat', '.txt', '.html', '.ms', '.man',
        '.cod', '.mtx', '.xrf', '.pip', '.end', '.res', '.ins', '.inx', '.drc', '.erc', '.out', '.apt', '.sta', '.tma',
        '.bat', '.cfg', '.hlp', '.rpt'}
WP = {'.wp', '.wpd', '.wp5', '.wp6'}
OFFICE_VECTOR = {'.wpg', '.cdr'}
GS = {'.eps', '.ps'}
STRINGS = {'.dwg', '.bak', '.sch', '.dsn', '.olb', '.lib', '.pcb', '.dbk', '.bkx', '.bcf', '.pjt', '.blk', '.dwk', '.igs'}
SKIP = {'.exe', '.hex', '.$$$', '.ac$', '.d~n', '.tmp', '.ftpquota', '.db', '.zip'}
RANK = {'manual': 5, 'high': 4, 'medium': 3, 'low': 2, 'none': 1}

# ------------------------------------------------------------------ vocabulary


def load_vocab(archive):
    """Canonical device codes and jobs from the timeline database, and a drawing-number register
    learned from files already filed in 2026 (Modules/<cat>/<code>/, Products/<series>/<code>/, Consoles/.../<job>...)."""
    codes, jobs = {}, {}
    db = os.path.join(archive, 'timelines', 'wbs_timeline.db')
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=30)
    has_name = 'name' in [r[1] for r in con.execute('pragma table_info(modules)')]
    names = {}
    for code, cat, name in con.execute(f'select code, category, {"name" if has_name else "null"} from modules'):
        codes[code.upper()] = code
        codes.setdefault(code.upper().replace('-', ''), code)
        if name:
            names[code] = name
    for row in con.execute('select * from jobs'):
        jobs[str(row[0])] = row
    con.close()
    # client call signs from the curated job register (timelines/projects.json): "CFTO TV, Toronto" -> CFTO -> its jobs
    clients = collections.defaultdict(set)
    try:
        projects = json.load(open(os.path.join(archive, 'timelines', 'projects.json'))).get('projects', {})
        for job, p in projects.items():
            sign = re.match(r'\s*(?:ABC\s+)?([A-Z]{3,5})\b', p.get('client', ''))
            if sign:
                clients[sign.group(1)].add(job)
                jobs.setdefault(job, (job, None, p.get('client'), 0))
    except (OSError, ValueError):
        pass
    load_vocab.clients = clients
    names.update({j: (row[2] or '') for j, row in jobs.items() if row[2] and not re.match(r'^\d{2}-\d{3}', str(row[2]))})
    load_vocab.names = names  # heading labels for the review page
    register = collections.defaultdict(collections.Counter)  # 'series-dd-seq' and 'series' -> Counter(home)
    for top in ('Modules', 'Products', 'Consoles'):
        for r, _, fs in os.walk(os.path.join(archive, top)):
            parts = os.path.relpath(r, archive).split(os.sep)
            home = next((codes[p.upper()] for p in reversed(parts) if p.upper() in codes), None)
            if not home:
                m = next((re.match(r'^(\d{5,6})\b', p) for p in reversed(parts) if re.match(r'^\d{5,6}\b', p)), None)
                home = m.group(1) if m else None
            if not home:
                continue
            for f in fs:
                for dn in drawing_numbers(f):
                    register[dn][home] += 1
                    register[dn.rsplit('-', 2)[0]][home] += 1
    return codes, jobs, register

# ------------------------------------------------------------------ text extraction


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def printable_strings(p, minimum=4, cap=400_000):
    with open(p, 'rb') as f:
        data = f.read(cap)
    runs = re.findall(rb'[\x20-\x7e]{%d,}' % minimum, data)
    words = [r.decode('ascii').strip() for r in runs]
    return '\n'.join(w for w in words if sum(c.isalnum() for c in w) >= 0.6 * len(w))[:60_000]


def read_text(p):
    with open(p, 'rb') as f:
        data = f.read(400_000)
    if data.count(b'\x00') > 20:
        return printable_strings(p)
    return data.decode('latin-1', errors='replace')[:60_000]


def docx_text(p):
    with zipfile.ZipFile(p) as z:
        xml = z.read('word/document.xml').decode('utf8', errors='replace')
    xml = re.sub(r'</w:p>', '\n', xml)
    return html.unescape(re.sub(r'<[^>]+>', '', xml))


def dxf_text(p):
    with open(p, errors='replace') as f:
        lines = [l.strip() for l in f]
    out = [lines[i + 1] for i in range(0, len(lines) - 1) if lines[i] in ('1', '3') and i + 1 < len(lines)]
    return '\n'.join(re.sub(r'\\[A-Za-z][^;]*;|[{}]', '', t) for t in out)

# ------------------------------------------------------------------ HPGL/2 plotter files


def hpgl_paths(p):
    """Decode HPGL/2 (inside PCL5) into polylines: PU/PD/PA/PR with coordinates, PE polyline-encoded, LB labels."""
    with open(p, 'rb') as f:
        raw = f.read()
    raw = re.sub(rb'\x1b[%&*()][^A-Z@]*[A-Z@]', b';', raw)  # drop PCL escapes
    text = raw.decode('latin-1')
    paths, labels = [], []
    x = y = 0.0
    pen_down, absolute = False, True
    cur = None

    def move(nx, ny, down):
        nonlocal x, y, cur
        if down:
            if cur is None:
                cur = [(x, y)]
                paths.append(cur)
            cur.append((nx, ny))
        else:
            cur = None
        x, y = nx, ny

    i, n = 0, len(text)
    while i < n:
        c2 = text[i:i + 2].upper()
        if not c2.isalpha() or len(c2) < 2:
            i += 1
            continue
        i += 2
        if c2 == 'LB':
            end = text.find('\x03', i)
            end = n if end < 0 else end
            labels.append((x, y, text[i:end]))
            i = end + 1
            continue
        if c2 == 'PE':
            i = decode_pe(text, i, lambda nx, ny, down: move(nx, ny, down), lambda: (x, y))
            continue
        j = i
        while j < n and text[j] not in ';' and not (text[j].isalpha() and text[j:j + 2].isalpha()):
            j += 1
        args = [float(v) for v in re.findall(r'-?\d+\.?\d*', text[i:j])]
        i = j
        if c2 in ('PU', 'PD'):
            pen_down = c2 == 'PD'
            if not pen_down:
                cur = None
            for k in range(0, len(args) - 1, 2):
                nx, ny = (args[k], args[k + 1]) if absolute else (x + args[k], y + args[k + 1])
                move(nx, ny, pen_down)
        elif c2 in ('PA', 'PR'):
            absolute = c2 == 'PA'
            for k in range(0, len(args) - 1, 2):
                nx, ny = (args[k], args[k + 1]) if absolute else (x + args[k], y + args[k + 1])
                move(nx, ny, pen_down)
        elif c2 == 'CI' and args:
            r = args[0]
            circle = [(x + r * math.cos(t / 24 * 2 * math.pi), y + r * math.sin(t / 24 * 2 * math.pi)) for t in range(25)]
            paths.append(circle)
        elif c2 == 'IN':
            x = y = 0.0
            pen_down, absolute, cur = False, True, None
    return paths, labels


def decode_pe(text, i, move, pos):
    """HPGL/2 PE: base-64 (or base-32 with the '7' flag) numbers, sign in the low bit, least significant digit first."""
    seven = False
    frac = 0
    pen_up_next = absolute_next = False
    nums = []
    n = len(text)

    def number():
        nonlocal i
        val, shift = 0, 0
        while i < n:
            c = ord(text[i])
            i += 1
            if seven:
                if 63 <= c <= 94:
                    val |= (c - 63) << shift
                    shift += 5
                elif 95 <= c <= 126:
                    val |= (c - 95) << shift
                    break
                else:
                    return None
            else:
                if 63 <= c <= 126:
                    val |= (c - 63) << shift
                    shift += 6
                elif 191 <= c <= 254:
                    val |= (c - 191) << shift
                    break
                else:
                    return None
        return (-(val >> 1) if val & 1 else val >> 1) / (1 << frac)

    while i < n and text[i] != ';':
        ch = text[i]
        if ch == '7':
            seven = True
            i += 1
        elif ch == '>':
            i += 1
            v = number()
            frac = int(v or 0)
        elif ch == ':':
            i += 1
            number()  # pen select
        elif ch == '<':
            pen_up_next = True
            i += 1
        elif ch == '=':
            absolute_next = True
            i += 1
        elif 63 <= ord(ch) <= 254:
            v = number()
            if v is None:
                break
            nums.append(v)
            if len(nums) == 2:
                x, y = pos()
                nx, ny = (nums[0], nums[1]) if absolute_next else (x + nums[0], y + nums[1])
                move(nx, ny, not pen_up_next)
                nums, pen_up_next, absolute_next = [], False, False
        else:
            i += 1
    return i + 1


def render_hpgl(p, svg_out, png_width=3000):
    """Write <svg_out> and a PNG beside it (drawn with Pillow, for OCR). Returns (svg path, LB label text)."""
    from PIL import Image, ImageDraw
    paths, labels = hpgl_paths(p)
    pts = [pt for path in paths for pt in path]
    if not pts:
        return None, ''
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = max(x1 - x0, 1), max(y1 - y0, 1)
    stroke = max(w, h) / 2500
    d = ' '.join('M' + ' L'.join(f'{px - x0:.0f},{y1 - py:.0f}' for px, py in path) for path in paths if len(path) > 1)
    txt = ''.join(f'<text x="{lx - x0:.0f}" y="{y1 - ly:.0f}" font-size="{max(w, h) / 120:.0f}">{html.escape(t)}</text>'
                  for lx, ly, t in labels)
    os.makedirs(os.path.dirname(svg_out), exist_ok=True)
    with open(svg_out, 'w') as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}">'
                f'<rect width="100%" height="100%" fill="#fff"/>'
                f'<path d="{d}" fill="none" stroke="#111" stroke-width="{stroke:.1f}" stroke-linecap="round"/>{txt}</svg>')
    k = png_width / w
    im = Image.new('L', (png_width, max(1, int(h * k))), 255)
    draw = ImageDraw.Draw(im)
    for path in paths:
        if len(path) > 1:
            draw.line([((px - x0) * k, (y1 - py) * k) for px, py in path], fill=0, width=max(1, png_width // 1500))
    im.save(svg_out[:-4] + '.png')
    return svg_out, '\n'.join(t for _, _, t in labels)

# ------------------------------------------------------------------ OCR (worker side)

_reader = None


def reader():
    global _reader
    if _reader is None:
        import torch, easyocr
        torch.set_num_threads(2)
        _reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    return _reader


def lines_from_boxes(res):
    """EasyOCR detail=1 results -> reading-order lines"""
    items = sorted(((min(p[1] for p in b), min(p[0] for p in b), max(p[1] for p in b) - min(p[1] for p in b), t)
                    for b, t, _ in res), key=lambda r: (r[0], r[1]))
    out, row, top, hgt = [], [], None, 0
    for y, x, h, t in items:
        if row and y > top + 0.6 * max(hgt, 1):
            out.append(' '.join(v for _, v in sorted(row)))
            row = []
        if not row:
            top, hgt = y, h
        row.append((x, t))
    if row:
        out.append(' '.join(v for _, v in sorted(row)))
    return '\n'.join(out)


def ocr_image(img, title_block=False):
    """img: PIL image. Returns (text, boxes, title_text)"""
    import numpy as np
    from PIL import Image
    g = img.convert('L')
    small = g.copy()
    small.thumbnail((2200, 2200))
    res = reader().readtext(np.array(small), detail=1, paragraph=False)
    sx = g.width / small.width
    boxes = [{'box': [[round(px * sx), round(py * sx)] for px, py in b], 'text': t, 'conf': round(float(c), 3)} for b, t, c in res]
    title = ''
    if title_block:
        crop = g.crop((int(g.width * .48), int(g.height * .66), g.width, g.height))
        if crop.width < 900:
            crop = crop.resize((900, int(crop.height * 900 / crop.width)), Image.LANCZOS)
        crop.thumbnail((2200, 2200))
        title = lines_from_boxes(reader().readtext(np.array(crop), detail=1, paragraph=False))
    return lines_from_boxes(res), boxes, title


def open_image(p):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(p)
    if im.format == 'JPEG':
        im.draft('L', (4400, 4400))
    return im


def drawing_like(im):
    return im.width >= 1.2 * im.height and max(im.size) >= 1600


def work(job):
    """One file -> extraction result. Runs in a worker process."""
    os.nice(19)
    rel, path, ext, out = job
    res = {'rel': rel, 'method': '', 'text': '', 'title': '', 'boxes': None, 'render': '', 'thumb': '', 'error': ''}
    try:
        from PIL import Image
        thumb_src = None
        if ext in IMAGE:
            im = open_image(path)
            im.load()
            res['method'] = 'ocr'
            res['text'], res['boxes'], res['title'] = ocr_image(im, drawing_like(im))
            thumb_src = im
        elif ext == '.pdf':
            t = subprocess.run(['pdftotext', '-layout', path, '-'], capture_output=True, text=True, timeout=120).stdout
            if len(t.strip()) > 80:
                res['method'], res['text'] = 'pdf-text', t
            else:
                res['method'] = 'ocr'
                texts, boxes = [], []
                with tempfile.TemporaryDirectory() as td:
                    subprocess.run(['pdftoppm', '-r', '150', '-gray', '-l', '20', '-png', path, os.path.join(td, 'p')], timeout=600)
                    for pg in sorted(os.listdir(td)):
                        im = Image.open(os.path.join(td, pg))
                        tx, bx, tt = ocr_image(im, drawing_like(im))
                        texts.append(tx + ('\n' + tt if tt else ''))
                        boxes.append(bx)
                        thumb_src = thumb_src or im.copy()
                res['text'], res['boxes'] = '\n\f\n'.join(texts), boxes
            if thumb_src is None:
                with tempfile.TemporaryDirectory() as td:
                    subprocess.run(['pdftoppm', '-r', '40', '-l', '1', '-png', path, os.path.join(td, 'p')], timeout=120)
                    pgs = sorted(os.listdir(td))
                    if pgs:
                        thumb_src = Image.open(os.path.join(td, pgs[0])).copy()
        elif ext == '.plt':
            svg = os.path.join(out, 'render', rel + '.svg')
            svg_path, labels = render_hpgl(path, svg)
            res['method'] = 'hpgl'
            if svg_path:
                res['render'] = os.path.relpath(svg_path, out)
                png = svg[:-4] + '.png'
                if os.path.exists(png):
                    im = Image.open(png)
                    tx, bx, tt = ocr_image(im, True)
                    res['text'], res['boxes'], res['title'] = (labels + '\n' + tx).strip(), bx, tt
                    thumb_src = im
        elif ext in GS or ext in OFFICE_VECTOR:
            with tempfile.TemporaryDirectory() as td:
                if ext in GS:
                    subprocess.run(['gs', '-q', '-dSAFER', '-dBATCH', '-dNOPAUSE', '-sDEVICE=pnggray', '-r150', '-dLastPage=3',
                                    f'-sOutputFile={td}/p%02d.png', path], capture_output=True, timeout=300)
                else:
                    subprocess.run(['soffice', f'-env:UserInstallation=file://{td}/lo', '--headless', '--convert-to', 'pdf',
                                    '--outdir', td, path], capture_output=True, timeout=300)
                    pdfs = [f for f in os.listdir(td) if f.endswith('.pdf')]
                    if pdfs:
                        subprocess.run(['pdftoppm', '-r', '150', '-gray', '-l', '3', '-png', os.path.join(td, pdfs[0]), f'{td}/p'], timeout=300)
                texts, boxes = [], []
                for pg in sorted(f for f in os.listdir(td) if f.endswith('.png')):
                    im = Image.open(os.path.join(td, pg))
                    tx, bx, tt = ocr_image(im, drawing_like(im))
                    texts.append(tx + ('\n' + tt if tt else ''))
                    boxes.append(bx)
                    thumb_src = thumb_src or im.copy()
                res['method'], res['text'], res['boxes'] = 'convert+ocr', '\n\f\n'.join(texts), boxes
        if thumb_src is not None:
            t = thumb_src.convert('RGB')
            t.thumbnail((320, 320))
            tp = os.path.join(out, 'thumbs', hashlib.sha1(rel.encode()).hexdigest()[:20] + '.jpg')
            t.save(tp, 'JPEG', quality=70)
            res['thumb'] = os.path.relpath(tp, out)
    except Exception as ex:  # one bad file must not stop the batch
        res['error'] = f'{type(ex).__name__}: {ex}'[:400]
    return res

# ------------------------------------------------------------------ tagging

KINDS = [  # (kind, regex on text) - first match wins
    ('advertisement', r'ARCHITECTS\s*OF\s*AUDIO|FIRST\s*BY\s*DESIGN|BROADCASTER\s*MAGAZINE|WORLD\s*LEADER'),
    ('price list', r'PRICE\s*(LIST|SCHEDULE)|LIST\s*PRICE|NET\s*PRICE|UNIT\s*PRICE'),
    ('quotation', r'QUOTATION|QUOTE\s*NO|PROPOSAL'),
    ('parts list', r'PARTS?\s*LIST|BILL\s*OF\s*MATERIALS|REPLACEMENT\s*PARTS|\bQTY\b'),
    ('schematic', r'SCHEMATIC'),
    ('layout', r'COMPONENT\s*LAYOUT|ASSEMBLY|LAYOUT|ARTWORK|DRILL'),
    ('wiring', r'WIRING|PIN\s*OUTS?|INTERCONNECT|JACKFIELD|CABLE'),
    ('data sheet', r'SPECIFICATIONS|TECHNICAL\s*DATA|FREQUENCY\s*RESPONSE|DISTORTION'),
    ('manual', r'INSTALLATION|OPERATION|MAINTENANCE|CIRCUIT\s*DESCRIPTION|USER\s*GUIDE'),
]
EXT_KIND = {'.asm': 'software', '.lst': 'software', '.hex': 'software', '.cod': 'software', '.mac': 'software',
            '.sch': 'schematic (OrCAD)', '.dsn': 'schematic (OrCAD)', '.olb': 'library', '.lib': 'library',
            '.pcb': 'pcb', '.net': 'netlist', '.dwg': 'drawing (AutoCAD)', '.dxf': 'drawing (DXF)', '.plt': 'plot (HPGL)',
            '.bom': 'parts list'}
from titles import DWG_RE, drawing_numbers  # noqa: E402
YEAR_RE = re.compile(r'(?<!\d)(19[5-9]\d|20[0-2]\d)(?!\d)')


def norm_code_token(tok):
    """OCR often reads 1 as l/I and 0 as O inside model numbers: M44lM -> M441M"""
    m = re.match(r'^([A-Z]{1,4})([0-9lIO|]{2,5})([A-Z]{0,3})$', tok)
    if not m:
        return tok
    return m.group(1) + m.group(2).translate(str.maketrans('lI|O', '1110')) + m.group(3)


def tag(rel, ext, text, title, codes, jobs, register):
    U = (text or '').upper()
    T = (title or '').upper()
    cand = collections.defaultdict(float)
    reasons = collections.defaultdict(list)

    def vote(home, score, why):
        cand[home] += score
        reasons[home].append(why)

    # curated folder and file names are the strongest evidence
    parts = rel.split('/')
    for depth, part in enumerate(parts):
        is_file = depth == len(parts) - 1
        for tok in re.findall(r'[A-Za-z]*\d+[A-Za-z]*', part):
            t = norm_code_token(tok.upper())
            if t in codes:
                vote(codes[t], 5 if not is_file else 4, f'{"file" if is_file else "folder"} name: {tok}')
            elif tok in jobs:
                vote(tok, 5, f'{"file" if is_file else "folder"} name: job {tok}')
    found_codes = collections.Counter()
    for tok in re.findall(r'[A-Z][A-Z0-9lI|-]{2,12}', (text or '') + '\n' + (title or '')):
        t = norm_code_token(tok.upper().strip('-'))
        t = t if t in codes else norm_code_token(t.replace('-', ''))
        if t in codes:
            found_codes[codes[t]] += 1
    for code, n in found_codes.items():
        in_title = code.upper() in T.replace(' ', '')
        vote(code, (4 if in_title else 0) + min(n, 3), f'text mentions {code} ×{n}' + (' (title block)' if in_title else ''))
    dwgs = drawing_numbers(U + '\n' + T + '\n' + rel.upper())
    for dn in dwgs:
        series = dn.rsplit('-', 2)[0]
        if register.get(dn):
            home = register[dn].most_common(1)[0][0]
            vote(home, 4, f'drawing {dn} is filed under {home}')
        elif series in jobs:
            vote(series, 4, f'drawing {dn} carries job number {series}')
        elif register.get(series) and len(register[series]) == 1:
            home = next(iter(register[series]))
            named = dn in rel.upper().replace(' ', '')  # a drawing number someone typed into the file name
            vote(home, 3 if named else 2, f'drawing series {series} belongs to {home}' + (' (file name)' if named else ''))
    for sign, js in getattr(load_vocab, 'clients', {}).items():  # a station named in the text points at its jobs
        if re.search(rf'(?<![A-Z]){sign}(?![A-Z])', U + ' ' + T):
            for j in js:
                vote(j, 2 if len(js) == 1 else 1, f'names client {sign} (job {j})')
    found_jobs = sorted({j for j in re.findall(r'(?<!\d)(\d{5,6})(?!\d)', U + ' ' + T) if j in jobs})
    for j in found_jobs:
        vote(j, 2, f'text mentions job {j}')
    years = collections.Counter(YEAR_RE.findall(U + ' ' + T))
    for yy in re.findall(r'DATE[:.\s]*(?:[A-Z]{3,9}\.?\s*)?(?:\d{1,2}[,/\s]+)?(\d{2})(?!\d)', U + ' ' + T):  # title blocks: DATE APR 73
        if int(yy) >= 50:
            years['19' + yy] += 2
    kind = EXT_KIND.get(ext, '')
    for k, rx in KINDS:
        if re.search(rx, U):
            kind = k if kind in ('', 'drawing (AutoCAD)', 'plot (HPGL)') or k == 'price list' else kind
            break
    camera = re.match(r'^(IMG|DSC|DSCF|PXL|P\d{7})[_ -]?\d', parts[-1], re.I) or re.match(r'^\d{8}_\d{6}', parts[-1])
    if not kind or (kind == 'manual' and camera and len(U.split()) < 60):
        kind = 'photo' if ext in IMAGE and (camera or len(U.split()) < 15) else 'document' if U.strip() else 'unknown'
    if re.search(r'magazine|broadcast(er|ing)', rel, re.I):  # trade magazines mention every station; never file by that
        kind = 'magazine'
        for h in [h for h, why in reasons.items() if all(w.startswith(('names client', 'text mentions job')) for w in why)]:
            cand.pop(h, None)
    ranked = sorted(cand.items(), key=lambda kv: -kv[1])
    home, conf = '', 'none'
    if ranked:
        home, top = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0
        conf = 'high' if top >= 4 and top - second >= 2 else 'medium' if top >= 3 else 'low'
    homes = [h for h, s in ranked if s >= 2] if kind == 'price list' else ([home] if home else [])
    return {'codes': sorted(found_codes), 'drawing_numbers': dwgs, 'jobs': found_jobs,
            'years': [int(y) for y, _ in years.most_common()], 'kind': kind, 'home': home,
            'home_kind': 'job' if home in jobs else 'module' if home else '', 'homes': homes, 'confidence': conf,
            'reasons': {h: reasons[h] for h, _ in ranked[:4]}, 'alternatives': [h for h, _ in ranked[1:4]]}

# ------------------------------------------------------------------ main

SCHEMA = '''create table if not exists scans (
  rel text primary key, sha256 text, ext text, size integer, method text, text text, title_block text,
  boxes_path text, render_path text, thumb text, codes text, drawing_numbers text, jobs text, years text,
  kind text, home text, home_kind text, homes text, confidence text, reasons text, alternatives text,
  error text, updated text)'''
# title-block fields, added by --retag on databases made before they existed
TITLE_COLS = ['dwg_no', 'device', 'title', 'doc_type', 'display_name', 'title_source', 'filename']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('out')
    ap.add_argument('--archive', required=True)
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--retag', action='store_true', help='recompute tags and titles from stored text, no OCR')
    a = ap.parse_args()
    src, out = os.path.abspath(a.src), os.path.abspath(a.out)
    for d in ('ocr', 'render', 'thumbs'):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    codes, jobs, register = load_vocab(os.path.abspath(a.archive))
    print(f'{len(codes)} device codes, {len(jobs)} jobs, {len(register)} register entries', flush=True)
    con = sqlite3.connect(os.path.join(out, 'scans.db'))
    con.execute(SCHEMA)
    # where `rel` paths start: the source folder relative to WBSps.env when it is inside it
    env = src.split(os.sep + 'WBSps.env' + os.sep, 1)
    con.execute('create table if not exists meta (key text primary key, value text)')
    con.execute("insert or replace into meta values ('source', ?)", (env[1] if len(env) == 2 else src,))
    con.commit()
    known = dict(con.execute('select rel, sha256 from scans'))
    manual = {}
    try:
        manual = json.load(open(os.path.join(out, 'assignments.json')))
    except (OSError, ValueError):
        pass
    if a.retag:
        retag(con, out, codes, jobs, register, manual)
        write_index(con, out, codes, jobs)
        con.close()
        return

    files = []
    for r, ds, fs in os.walk(src):
        ds.sort()
        for f in sorted(fs):
            if f.endswith('.json'):  # sidecars made by earlier tools
                continue
            p = os.path.join(r, f)
            files.append((os.path.relpath(p, src).replace(os.sep, '/'), p, os.path.splitext(f)[1].lower()))
    if a.limit:
        files = files[:a.limit]

    # quick types in this process; OCR types go to the pool
    quick, heavy, wp_batch = [], [], []
    for rel, p, ext in files:
        digest = sha256(p)
        if known.get(rel) == digest and rel not in manual:
            continue
        item = (rel, p, ext, digest)
        if ext in IMAGE or ext in GS or ext in OFFICE_VECTOR or ext in ('.pdf', '.plt'):
            heavy.append(item)
        elif ext in WP:
            wp_batch.append(item)
        else:
            quick.append(item)
    print(f'{len(files)} files: {len(heavy)} to OCR, {len(wp_batch)} WordPerfect, {len(quick)} text/strings, '
          f'{len(files) - len(heavy) - len(wp_batch) - len(quick)} unchanged', flush=True)

    def store(rel, p, ext, digest, res):
        text, title = res.get('text', ''), res.get('title', '')
        tags = tag(rel, ext, text, title, codes, jobs, register)
        if rel in manual:
            tags.update(home=manual[rel], home_kind='job' if manual[rel] in jobs else 'module', confidence='manual')
        boxes_path = ''
        if res.get('boxes'):
            boxes_path = os.path.join('ocr', rel + '.ocr.json')
            os.makedirs(os.path.dirname(os.path.join(out, boxes_path)), exist_ok=True)
            with open(os.path.join(out, boxes_path), 'w') as f:
                json.dump({'rel': rel, 'sha256': digest, 'method': res['method'], 'text': text, 'title_block': title,
                           'boxes': res['boxes'], **tags}, f, ensure_ascii=False)
        con.execute('insert or replace into scans values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
            rel, digest, ext, os.path.getsize(p), res.get('method', ''), text, title, boxes_path, res.get('render', ''),
            res.get('thumb', ''), json.dumps(tags['codes']), json.dumps(tags['drawing_numbers']), json.dumps(tags['jobs']),
            json.dumps(tags['years']), tags['kind'], tags['home'], tags['home_kind'], json.dumps(tags['homes']),
            tags['confidence'], json.dumps(tags['reasons']), json.dumps(tags['alternatives']), res.get('error', ''),
            time.strftime('%Y-%m-%d %H:%M:%S')))
        con.commit()

    for rel, p, ext, digest in quick:
        try:
            if ext == '.docx':
                res = {'method': 'docx', 'text': docx_text(p)}
            elif ext == '.dxf':
                res = {'method': 'dxf-text', 'text': dxf_text(p)}
            elif ext in TEXT:
                res = {'method': 'text', 'text': read_text(p)}
            elif ext in SKIP:
                res = {'method': 'skipped'}
            else:
                res = {'method': 'strings', 'text': printable_strings(p)}
        except Exception as ex:
            res = {'method': 'error', 'error': str(ex)[:400]}
        store(rel, p, ext, digest, res)

    if wp_batch:  # one LibreOffice run for all WordPerfect files
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(['nice', '-n', '19', 'soffice', f'-env:UserInstallation=file://{td}/lo', '--headless', '--convert-to',
                            'txt:Text (encoded):UTF8', '--outdir', td] + [p for _, p, _, _ in wp_batch], capture_output=True, timeout=3600)
            for rel, p, ext, digest in wp_batch:
                txt = os.path.join(td, os.path.splitext(os.path.basename(p))[0] + '.txt')
                try:
                    res = {'method': 'wordperfect', 'text': open(txt, encoding='utf-8-sig', errors='replace').read()}
                except OSError:
                    res = {'method': 'strings', 'text': printable_strings(p)}
                store(rel, p, ext, digest, res)
    print(f'text files done; OCR of {len(heavy)} files with {a.workers} workers at nice 19', flush=True)

    by_rel = {rel: (rel, p, ext, digest) for rel, p, ext, digest in heavy}
    with multiprocessing.Pool(a.workers) as pool:
        for k, res in enumerate(pool.imap_unordered(work, [(rel, p, ext, out) for rel, p, ext, _ in heavy]), 1):
            store(*by_rel[res['rel']], res)
            print(f'[{k}/{len(heavy)}] {res["rel"]} {res["error"] or ""}', flush=True)
    write_index(con, out, codes, jobs)
    con.close()


def ensure_title_cols(con):
    have = {r[1] for r in con.execute('pragma table_info(scans)')}
    for c in TITLE_COLS:
        if c not in have:
            con.execute(f'alter table scans add column {c} text')


def retag(con, out, codes, jobs, register, manual):
    """Recompute tags and title-block fields for every row from the stored text, and refresh the per-file JSON."""
    ensure_title_cols(con)
    known_series = {k for k in register if '-' not in k or k.startswith('14-')}
    try:  # board numbers from the KiCad conversion (14-302, 14-323...) also count as drawing series
        boards = json.load(open(os.path.join(os.path.dirname(os.path.dirname(out)), 'PCB', 'boards.json')))
        known_series |= {os.path.splitext(os.path.basename(b['source']))[0].upper() for b in boards}
    except (OSError, ValueError):
        pass
    rows = con.execute('select rel, ext, method, text, title_block, boxes_path from scans').fetchall()
    for rel, ext, method, text, tb, boxes_path in rows:
        tags = tag(rel, ext, text or '', tb or '', codes, jobs, register)
        if rel in manual:
            tags.update(home=manual[rel], home_kind='job' if manual[rel] in jobs else 'module', confidence='manual')
        if method == 'strings':  # years inside binary formats are software versions, not drawing dates
            tags['years'] = []
        # strings pulled from binaries and OCR crumbs from photos make no title; those keep their file names
        usable = method not in ('strings', 'skipped') and tags['kind'] != 'photo'
        ti = title_info(text or '' if usable else '', tb or '' if usable else '', rel, codes, tags['kind'])
        if ti['dwg_no']:  # OCR often drops the 14- of SA14 board drawings: 302-01-003 -> 14-302-01-003
            series = ti['dwg_no'].rsplit('-', 2)[0]
            if series not in known_series and f'14-{series}' in known_series:
                fixed = '14-' + ti['dwg_no']
                ti['display_name'] = ti['display_name'].replace(ti['dwg_no'], fixed, 1)
                ti['dwg_no'] = fixed
        year = tags['years'][0] if tags['years'] else ''
        # the name a filed copy should get: YEAR - HOME - title as written in the title block (its type included)
        flat = lambda v: re.sub(r'[\s-]', '', v or '').upper()
        if ti['title_source'] == 'file name':  # no title to read: keep the file's own name so names stay unique
            parts = [os.path.splitext(rel.rsplit('/', 1)[-1])[0]]
        else:
            parts = [p for p in ti['display_name'].split(' · ') if not (tags['home'] and flat(p) == flat(tags['home']))]
        name = ' · '.join(parts) if ti['doc_type'] else ' · '.join(parts + [tags['kind'].upper()])
        ti['filename'] = safe_filename(' - '.join(str(p) for p in (year, tags['home'], name) if p)) + ext
        con.execute(f'''update scans set codes=?, drawing_numbers=?, jobs=?, years=?, kind=?, home=?, home_kind=?, homes=?,
                        confidence=?, reasons=?, alternatives=?, {", ".join(c + "=?" for c in TITLE_COLS)} where rel=?''',
                    (json.dumps(tags['codes']), json.dumps(tags['drawing_numbers']), json.dumps(tags['jobs']), json.dumps(tags['years']),
                     tags['kind'], tags['home'], tags['home_kind'], json.dumps(tags['homes']), tags['confidence'],
                     json.dumps(tags['reasons']), json.dumps(tags['alternatives']), *[ti[c] for c in TITLE_COLS], rel))
        if boxes_path and os.path.exists(os.path.join(out, boxes_path)):
            path = os.path.join(out, boxes_path)
            data = json.load(open(path))
            data.update(tags, **ti)
            json.dump(data, open(path, 'w'), ensure_ascii=False)
    # two files with the same title get their original file name added, so filed copies never collide
    seen = collections.defaultdict(list)
    for rel, fn in con.execute('select rel, filename from scans'):
        seen[fn.lower()].append(rel)
    for fn, rels in seen.items():
        if len(rels) > 1:
            for rel in rels:
                stem, ext = os.path.splitext(con.execute('select filename from scans where rel=?', (rel,)).fetchone()[0])
                own = os.path.splitext(rel.rsplit('/', 1)[-1])[0]
                con.execute('update scans set filename=? where rel=?', (safe_filename(f'{stem} ({own})', 160) + ext, rel))
    con.commit()
    print(f'retagged {len(rows)} rows', flush=True)


def write_index(con, out, codes, jobs):
    rows = [dict(zip([d[0] for d in con.execute('select * from scans limit 0').description], r))
            for r in con.execute('select * from scans order by home, rel')]
    groups = collections.OrderedDict()
    for r in sorted(rows, key=lambda r: (not r['home'], r['home'] or '', -RANK[r['confidence']], r['rel'])):
        groups.setdefault(r['home'] or '— needs a home', []).append(r)
    e = html.escape
    options = ''.join(f'<option value="{e(c)}">' for c in sorted(set(codes.values()))) + ''.join(f'<option value="{e(j)}">' for j in sorted(jobs))

    def card(r):
        thumb = r['render_path'] or r['thumb']
        img = f'<img loading="lazy" src="{e(thumb)}" alt="">' if thumb else f'<span class="ph">{e(r["ext"])}</span>'
        tags = ' '.join(f'<span class="t">{e(x)}</span>' for x in json.loads(r['codes']) + json.loads(r['drawing_numbers']) + json.loads(r['jobs']))
        why = '; '.join(json.loads(r['reasons']).get(r['home'], [])) if r['home'] else ''
        snippet = e((r['title_block'] or r['text'] or '')[:220])
        title = r.get('display_name') or r['rel'].rsplit('/', 1)[-1]
        return (f'<li class="card c-{r["confidence"]}" data-rel="{e(r["rel"])}"><div class="th">{img}</div>'
                f'<div class="ti">{e(title)}</div>'
                f'<div class="nm">{e(r["rel"])}{" · from " + e(r["title_source"]) if r.get("title_source") else ""}</div>'
                f'<div class="mt"><b>{e(r["kind"])}</b> · {e(r["confidence"])}'
                f'{" · " + ", ".join(map(str, json.loads(r["years"])[:3])) if json.loads(r["years"]) else ""}</div>'
                f'<div class="tg">{tags}</div><div class="why">{e(why)}</div><p class="sn">{snippet}</p>'
                f'<label>Home <input list="homes" value="{e(r["home"] or "")}" data-auto="{e(r["home"] or "")}"></label></li>')

    label = getattr(load_vocab, 'names', {})
    body = ''.join(f'<section><h2>{e(h)}{" · " + e(label[h]) if h in label else ""} <small>{len(rs)}</small></h2>'
                   f'<ul class="grid">{"".join(card(r) for r in rs)}</ul></section>'
                   for h, rs in groups.items())
    counts = collections.Counter(r['confidence'] for r in rows)
    with open(os.path.join(out, 'index.html'), 'w') as f:
        f.write(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Unsorted Scans Review</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Courier+Prime:wght@400;700&display=swap">
<style>
/* Layout: the binder's review tray - one typed card per file, grouped under its proposed home. Single look by design. */
:root {{ --vinyl: #141414; --card: #f4efdc; --type: #1c1c1c; --faint: #6d6a63; --red: #a52a22; --green: #2f6b45; --amber: #9a6a12; color-scheme: dark }}
body {{ margin: 0; background: var(--vinyl); color: #e8e2c8; font: 14px/1.4 "Courier Prime", "Courier New", monospace;
  padding-block: 20px 60px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)) }}
header {{ max-width: 1300px; margin: 0 auto 16px; display: flex; flex-wrap: wrap; gap: 10px 24px; align-items: baseline }}
h1 {{ font-size: 18px; text-transform: uppercase; letter-spacing: .06em; margin: 0 }}
button {{ font: 700 13px "Courier Prime", monospace; text-transform: uppercase; padding: 6px 12px; background: var(--card); color: var(--type); border: 0; cursor: pointer }}
section {{ max-width: 1300px; margin: 0 auto 26px }}
h2 {{ font-size: 15px; text-transform: uppercase; border-bottom: 1px solid #555; padding-bottom: 4px }}
h2 small {{ color: #9c968a }}
.grid {{ list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); gap: 14px }}
.card {{ background: var(--card); color: var(--type); padding: 10px; display: grid; gap: 4px; align-content: start; border-top: 5px solid var(--faint); color-scheme: light }}
.c-high, .c-manual {{ border-top-color: var(--green) }} .c-medium {{ border-top-color: var(--amber) }} .c-low, .c-none {{ border-top-color: var(--red) }}
.th {{ aspect-ratio: 4 / 3; background: #e4dec6; display: grid; place-items: center; overflow: hidden }}
.th img {{ width: 100%; height: 100%; object-fit: contain }}
.ph {{ color: var(--faint); text-transform: uppercase }}
.ti {{ font-weight: 700; font-size: 13.5px; text-transform: uppercase; word-break: break-word }}
.nm {{ font-size: 11px; color: var(--faint); word-break: break-all }}
.mt, .why {{ font-size: 12px; color: var(--faint) }}
.t {{ display: inline-block; font-size: 11px; border: 1px solid var(--faint); padding: 0 4px; margin: 1px }}
.sn {{ font-size: 11.5px; margin: 0; color: #3a3833; max-height: 4.5em; overflow: hidden }}
label {{ font-size: 12px; text-transform: uppercase; display: flex; gap: 6px; align-items: baseline }}
input {{ flex: 1; min-width: 0; font: 14px "Courier Prime", monospace; border: 0; border-bottom: 1.5px solid var(--type); background: transparent; color: var(--type) }}
input.changed {{ background: #f2d974 }}
</style></head><body>
<header><h1>Unsorted scans · proposed homes</h1>
<span>{len(rows)} files · high {counts["high"] + counts["manual"]} · medium {counts["medium"]} · low {counts["low"]} · none {counts["none"]}</span>
<button id="export" type="button">Save my changes as assignments.json</button><span id="msg" aria-live="polite"></span></header>
<datalist id="homes">{options}</datalist>
{body}
<script>
const KEY = 'wbs-scan-assignments';
let saved = {{}};
try {{ saved = JSON.parse(localStorage.getItem(KEY) || '{{}}'); }} catch (e) {{}}
document.querySelectorAll('.card').forEach(c => {{
  const i = c.querySelector('input'), rel = c.dataset.rel;
  if (saved[rel] !== undefined) {{ i.value = saved[rel]; i.classList.add('changed'); }}
  i.addEventListener('change', () => {{
    if (i.value.trim() && i.value.trim() !== i.dataset.auto) {{ saved[rel] = i.value.trim(); i.classList.add('changed'); }}
    else {{ delete saved[rel]; i.classList.remove('changed'); }}
    try {{ localStorage.setItem(KEY, JSON.stringify(saved)); }} catch (e) {{}}
  }});
}});
document.getElementById('export').addEventListener('click', () => {{
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(saved, null, 2)], {{ type: 'application/json' }}));
  a.download = 'assignments.json';
  a.click();
  document.getElementById('msg').textContent = Object.keys(saved).length + ' homes saved. Put assignments.json next to this page and re-run scan_ingest.py.';
}});
</script></body></html>''')
    print(f'wrote {os.path.join(out, "index.html")}', flush=True)


if __name__ == '__main__':
    main()
