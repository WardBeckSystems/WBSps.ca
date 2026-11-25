#!/usr/bin/env python3
"""Render a PDF beside every CAD file in the WBS archive, so each one can be read without the CAD tool.

  FOO.DWG               -> FOO.pdf             AutoCAD DWG (R12..2010)  : LibreDWG dwg2dxf -> ezdxf -> PDF
  FOO.SchDoc            -> FOO.pdf             Altium / Protel DXP schematic (own renderer)
  FOO.sch  (Eagle XML)  -> FOO.pdf             Eagle 6+ schematic, one page per sheet (own renderer)
  FOO.cdr               -> FOO.pdf             CorelDRAW artwork (LibreOffice / libcdr, headless)
  <board>.GTL/.GBL/...  -> <board> GERBERS.pdf one PDF per Gerber job: top view, bottom view, then every layer
                                               and drill file on its own page (gerbonara)

Rules
  * A PDF that already sits beside the source and was NOT made by this script is never touched (those are the
    original plots). Our PDFs carry Creator = "WBS render_cad_pdfs", so re-runs can tell them apart.
  * Re-runs only redo files whose source is newer than its PDF (use --force to redo everything).
  * If two sources in one folder share a name (FOO.dwg + FOO.sch) the PDFs become FOO.dwg.pdf / FOO.sch.pdf.
  * Each PDF gets a FOO.pdf.md sidecar (beside it; in a 2026 module folder, in <M>/OCR/) (what it is, how it was made, parts / layers / text), and the source's
    existing .md gets a "Rendered PDF" link line.
  * Every result is logged to render_cad_pdfs.log.tsv next to this script (status, source, pdf, note).

Not rendered (no open-source reader exists): P-CAD 2002 / ACCEL binary .sch, OrCAD Capture .DSN, OrCAD SDT .sch.
KiCad's command line was checked: kicad-cli 9 only opens native .kicad_sch, and GerbView has no command line.

usage
  python3 render_cad_pdfs.py --setup                      # once: build LibreDWG into ~/.local, make the venv
  python3 render_cad_pdfs.py "WBS - DATA SHUFFLER"        # everything
  python3 render_cad_pdfs.py ROOT --only dwg,gerber,sch --jobs 8 --force --dry-run --limit 20
  python3 render_cad_pdfs.py --one FILE_OR_GERBER_DIR     # render one item (for testing)

Anthony Peter Kuzub — WBSps.Kuzub.com / WBSps.ca
"""
import argparse, html, math, os, re, shutil, struct, subprocess, sys, tempfile, time, warnings
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))
from module_layout import note_for   # module files: note in <M>/OCR/, files in kind folders; elsewhere beside the file
VENV = os.path.expanduser('~/.local/share/wbs-cad-venv')
VPY = os.path.join(VENV, 'bin', 'python')
DWG2DXF = shutil.which('dwg2dxf') or os.path.expanduser('~/.local/bin/dwg2dxf')
LIBREDWG = '0.13.4'
CREATOR = 'WBS render_cad_pdfs'
LOG = os.path.join(HERE, 'render_cad_pdfs.log.tsv')
PAGE_L, PAGE_P = (17 * 72, 11 * 72), (11 * 72, 17 * 72)      # 11x17 sheet, landscape / portrait (points)

GERBER_EXT = re.compile(r'\.(gtl|gbl|gto|gbo|gts|gbs|gtp|gbp|gko|gm\d+|gd\d+|gg\d+|g\d+|gp\d+|gpt|gpb|gbr|ger|pho|art|'
                        r'cmp|sol|stc|sts|plc|pls|crc|crs)$', re.I)
DRILL_EXT = re.compile(r'\.(drl|drd|xln|txt|exc|ncd|nc)$', re.I)


# ============================================================================================ environment
def setup():
    """Build LibreDWG (dwg2dxf) into ~/.local and create a venv with gerbonara / ezdxf / olefile / PyMuPDF."""
    if not os.path.exists(DWG2DXF):
        src = os.path.expanduser('~/.local/src')
        os.makedirs(src, exist_ok=True)
        tar = f'libredwg-{LIBREDWG}.tar.xz'
        sh = (f'cd {src} && curl -sLO https://ftp.gnu.org/gnu/libredwg/{tar} && tar xf {tar} && cd libredwg-{LIBREDWG} && '
              f'./configure --prefix=$HOME/.local --disable-bindings --disable-docs && make -j$(nproc) && make install')
        subprocess.run(sh, shell=True, check=True)
    if not os.path.exists(VPY):
        subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', VENV], check=True)
    subprocess.run([VPY, '-m', 'pip', 'install', '-q', '-U', 'ezdxf>=1.3', 'gerbonara', 'olefile', 'pymupdf'], check=True)
    print('ready:', DWG2DXF, VPY)


def ensure_venv():
    """Re-run this script under the venv when the libraries it needs are not importable here."""
    try:
        import ezdxf, gerbonara, olefile, fitz  # noqa
        if tuple(map(int, ezdxf.__version__.split('.')[:2])) >= (1, 3):
            return
    except ImportError:
        pass
    if os.path.realpath(sys.prefix) != os.path.realpath(VENV) and os.path.exists(VPY):
        os.execv(VPY, [VPY] + sys.argv)
    sys.exit('missing libraries - run:  python3 render_cad_pdfs.py --setup')


# ============================================================================================ PDF helpers
def svg_to_pdf_page(svg_text):
    import fitz
    src = fitz.open(stream=svg_text.encode('utf-8'), filetype='svg')
    return fitz.open('pdf', src.convert_to_pdf())


def compose(pages, out_pdf, source, kind):
    """pages: list of (fitz single-page doc, caption). Each lands on an 11x17 sheet (orientation by aspect)
    with a caption line, then everything is saved as one PDF tagged with our Creator string."""
    import fitz
    out = fitz.open()
    for doc, caption in pages:
        r = doc[0].rect
        W, H = PAGE_L if r.width >= r.height else PAGE_P
        page = out.new_page(width=W, height=H)
        m, top = 22, 34
        box = fitz.Rect(m, top, W - m, H - m)
        page.show_pdf_page(box, doc, 0, keep_proportion=True)
        page.insert_text((m, 20), caption[:160], fontsize=9, fontname='helv', color=(0.2, 0.2, 0.2))
        page.insert_text((W - m - 250, H - 8), 'Ward-Beck Systems archive - WBSps.ca - rendered by render_cad_pdfs.py',
                         fontsize=6, fontname='helv', color=(0.5, 0.5, 0.5))
    out.set_metadata({'title': os.path.basename(source), 'creator': CREATOR, 'producer': CREATOR,
                      'subject': f'{kind} rendered from {os.path.basename(source)}', 'author': 'Ward-Beck Systems'})
    tmp = out_pdf + '.part'
    out.save(tmp, garbage=3, deflate=True)
    os.replace(tmp, out_pdf)
    return len(pages)


def ours(pdf):
    import fitz
    try:
        return CREATOR in (fitz.open(pdf).metadata.get('creator') or '')
    except Exception:
        return False


# ============================================================================================ DWG
def repair_dxf(path):
    """Fix the POLYLINE/VERTEX/SEQEND sequences LibreDWG sometimes leaves broken: close a polyline that is
    followed by anything but VERTEX/SEQEND, drop VERTEX and SEQEND records that have no open polyline."""
    raw = open(path, 'rb').read().decode('latin1').split('\n')
    if raw and raw[-1] == '':
        raw.pop()
    pairs = [(raw[i].strip(), raw[i + 1].rstrip('\r')) for i in range(0, len(raw) - 1, 2)]
    out, open_poly, skip, changed = [], False, False, False
    for code, val in pairs:
        if code == '0':
            skip = False
            v = val.strip()
            if v == 'POLYLINE':
                if open_poly:
                    out += [('0', 'SEQEND'), ('8', '0')]; changed = True
                open_poly = True
            elif v == 'VERTEX':
                if not open_poly:
                    skip = changed = True
                    continue
            elif v == 'SEQEND':
                if not open_poly:
                    skip = changed = True
                    continue
                open_poly = False
            elif open_poly:
                out += [('0', 'SEQEND'), ('8', '0')]
                open_poly, changed = False, True
        elif skip:
            continue
        out.append((code, val))
    if changed:
        with open(path, 'w', encoding='latin1', newline='\n') as f:
            f.write(''.join(f'{c}\n{v}\n' for c, v in out))


def render_dwg(src, out_pdf):
    from ezdxf import recover
    from ezdxf.addons.drawing import Frontend, RenderContext, pymupdf, layout, config
    doc, err = None, ''
    with tempfile.TemporaryDirectory() as tmp:
        # LibreDWG's DXF for old (R12) drawings often has unterminated POLYLINEs: repair, else retry entities-only
        for flags in ([], ['-m']):
            dxf = os.path.join(tmp, 'x.dxf')
            try:
                p = subprocess.run([DWG2DXF, '-y', *flags, '-o', dxf, src], capture_output=True, timeout=240)
                err = p.stderr.decode('latin1')[-200:].replace('\n', ' ')
            except subprocess.TimeoutExpired:
                err = 'dwg2dxf timed out'
            if not os.path.exists(dxf) or os.path.getsize(dxf) < 200:
                continue
            repair_dxf(dxf)
            try:
                doc, _ = recover.readfile(dxf)
                break
            except Exception as e:
                err = f'{type(e).__name__}: {e}'
        if doc is None:
            raise RuntimeError('dwg2dxf/ezdxf failed: ' + err)
    # LibreDWG writes layer colours negative (= "layer off" in DXF); an archive print wants every layer visible
    for L in doc.layers:
        L.dxf.color = abs(L.dxf.color) or 7
        L.dxf.flags &= ~1
    # empty POLYLINE / LWPOLYLINE records (left behind by the repair or by LibreDWG) crash the renderer
    for blk in doc.blocks:
        for e in list(blk):
            try:
                if (e.dxftype() == 'POLYLINE' and len(e.vertices) < 1) or (e.dxftype() == 'LWPOLYLINE' and len(e) < 1):
                    blk.delete_entity(e)
            except Exception:
                pass
    cfg = config.Configuration(background_policy=config.BackgroundPolicy.WHITE, color_policy=config.ColorPolicy.BLACK)
    pages, captions = [], []
    msp = doc.modelspace()
    layouts = [msp] + [l for l in doc.layouts if l.name != 'Model' and any(e.dxftype() != 'VIEWPORT' for e in l)]
    import fitz
    from ezdxf import bbox
    for lay in layouts:
        try:
            ext = bbox.extents(lay, fast=True)
            if not ext.has_data:
                continue
            w, h = ext.size.x, ext.size.y
        except Exception:                                  # odd R12 entities break the extents walk
            if not len(lay):
                continue
            try:
                a, b = doc.header.get('$EXTMIN'), doc.header.get('$EXTMAX')
                w, h = b[0] - a[0], b[1] - a[1]
            except Exception:
                w, h = 1, 0                                # landscape
        sheet = layout.Page(432, 279, layout.Units.mm, margins=layout.Margins.all(4)) if w >= h else \
            layout.Page(279, 432, layout.Units.mm, margins=layout.Margins.all(4))
        be = pymupdf.PyMuPdfBackend()
        Frontend(RenderContext(doc), be, config=cfg).draw_layout(lay, finalize=True)
        try:
            pdf = be.get_pdf_bytes(sheet, settings=layout.Settings(fit_page=True))
        except Exception:
            continue                                       # empty layout
        name = 'Model space' if lay.name == 'Model' else f'Layout "{lay.name}"'
        cap = f'{os.path.basename(src)}  -  AutoCAD {doc.acad_release}  -  {name}'
        pages.append((fitz.open('pdf', pdf), cap))
        captions.append(cap)
    if not pages:
        raise RuntimeError('drawing is empty')
    n = compose(pages, out_pdf, src, 'AutoCAD drawing')
    texts = []
    for e in msp.query('TEXT MTEXT ATTRIB'):
        t = (e.plain_text() if e.dxftype() == 'MTEXT' else e.dxf.get('text', '')).strip()
        if t and t not in texts:
            texts.append(t)
    for ins in msp.query('INSERT'):
        for at in ins.attribs:
            t = at.dxf.get('text', '').strip()
            if t and t not in texts:
                texts.append(t)
    from collections import Counter
    kinds = Counter(e.dxftype() for e in msp)
    return {'pages': n, 'captions': captions, 'type': 'AutoCAD DWG drawing',
            'summary': f'PDF rendering of the AutoCAD drawing {os.path.basename(src)} (DWG format {doc.acad_release}).',
            'details': [('DWG version', doc.acad_release), ('Layers', ', '.join(L.dxf.name for L in doc.layers)),
                        ('Model space entities', ', '.join(f'{k} {v}' for k, v in kinds.most_common())),
                        ('Pipeline', 'LibreDWG `dwg2dxf` -> ezdxf drawing add-on -> PyMuPDF, every layer forced visible, '
                                     'black on white, scaled to fit an 11x17 sheet (not to scale)')],
            'sections': [('Text in the drawing', '\n\n'.join(texts))] if texts else []}


# ============================================================================================ SVG mini-writer
class Svg:
    def __init__(self):
        self.parts = []
        self.box = [math.inf, math.inf, -math.inf, -math.inf]

    def grow(self, x, y):
        b = self.box
        b[0], b[1], b[2], b[3] = min(b[0], x), min(b[1], y), max(b[2], x), max(b[3], y)

    def line(self, pts, color, w, fill='none', close=False):
        if len(pts) < 2:
            return
        for x, y in pts:
            self.grow(x, y)
        d = 'M' + ' L'.join(f'{x:.2f} {-y:.2f}' for x, y in pts) + (' Z' if close else '')
        self.parts.append(f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{w:.2f}" '
                          f'stroke-linecap="round" stroke-linejoin="round"/>')

    def circle(self, x, y, r, color, w, fill='none'):
        self.grow(x - r, y - r); self.grow(x + r, y + r)
        self.parts.append(f'<circle cx="{x:.2f}" cy="{-y:.2f}" r="{r:.2f}" fill="{fill}" stroke="{color}" stroke-width="{w:.2f}"/>')

    def ellipse(self, x, y, rx, ry, color, w, fill='none'):
        self.grow(x - rx, y - ry); self.grow(x + rx, y + ry)
        self.parts.append(f'<ellipse cx="{x:.2f}" cy="{-y:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" fill="{fill}" stroke="{color}" stroke-width="{w:.2f}"/>')

    def arc(self, x, y, r, a0, a1, color, w, ry=None):
        ry = ry or r
        if (a1 - a0) % 360 == 0:
            return self.ellipse(x, y, r, ry, color, w)
        sweep = (a1 - a0) % 360
        p0 = (x + r * math.cos(math.radians(a0)), y + ry * math.sin(math.radians(a0)))
        p1 = (x + r * math.cos(math.radians(a1)), y + ry * math.sin(math.radians(a1)))
        self.grow(x - r, y - ry); self.grow(x + r, y + ry)
        self.parts.append(f'<path d="M{p0[0]:.2f} {-p0[1]:.2f} A{r:.2f} {ry:.2f} 0 {1 if sweep > 180 else 0} 0 '
                          f'{p1[0]:.2f} {-p1[1]:.2f}" fill="none" stroke="{color}" stroke-width="{w:.2f}"/>')

    def text(self, x, y, s, size, color, rot=0, anchor='start', base='auto', bold=False, family='Arial, Helvetica, sans-serif'):
        if not s:
            return
        self.grow(x, y)
        n = len(s) * size * 0.6
        if rot % 180 == 0:
            self.grow(x + (n if anchor == 'start' else -n), y + size)
        else:
            self.grow(x - size, y + (n if anchor == 'start' else -n))
        tr = f' transform="rotate({-rot} {x:.2f} {-y:.2f})"' if rot else ''
        self.parts.append(f'<text x="{x:.2f}" y="{-y:.2f}" font-size="{size:.2f}" font-family="{family}" fill="{color}" '
                          f'text-anchor="{anchor}" dominant-baseline="{base}"{" font-weight=\"bold\"" if bold else ""}{tr}>'
                          f'{html.escape(s)}</text>')

    def render(self, bounds=None, bg='white', pad=5):
        x0, y0, x1, y1 = bounds or self.box
        if not math.isfinite(x0):
            x0, y0, x1, y1 = 0, 0, 100, 100
        x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
        w, h = x1 - x0, y1 - y0
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.2f}" height="{h:.2f}" viewBox="{x0:.2f} {-y1:.2f} {w:.2f} {h:.2f}">'
                f'<rect x="{x0:.2f}" y="{-y1:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{bg}"/>' + ''.join(self.parts) + '</svg>')


# ============================================================================================ Altium SchDoc
ALTIUM_SHEETS = {0: (1150, 760), 1: (1550, 1110), 2: (2230, 1570), 3: (3150, 2230), 4: (4460, 3150), 5: (950, 750),
                 6: (1500, 950), 7: (2000, 1500), 8: (3200, 2000), 9: (4200, 3200), 10: (1100, 850), 11: (1400, 850),
                 12: (1700, 1100), 13: (990, 790), 14: (1540, 990), 15: (2060, 1560), 16: (3260, 2060), 17: (4280, 3280)}


def altium_records(path):
    import olefile
    data = olefile.OleFileIO(path).openstream('FileHeader').read()
    recs, i = [], 0
    while i + 4 <= len(data):
        n = struct.unpack('<I', data[i:i + 4])[0]
        kind, n = n >> 24, n & 0xFFFFFF
        body = data[i + 4:i + 4 + n]
        i += 4 + n
        if kind == 0:
            r = {}
            for kv in body.rstrip(b'\0').decode('latin1').split('|'):
                if '=' in kv:
                    k, v = kv.split('=', 1)
                    r.setdefault(k.upper(), v)
            recs.append(r)
        elif kind == 1 and len(body) > 20:                  # binary pin record (newer Altium)
            recs.append(altium_binary_pin(body))
        else:
            recs.append({})
    return recs


def altium_binary_pin(b):
    try:
        rec, = struct.unpack_from('<i', b, 0)
        if rec != 2:
            return {}
        p = 4
        p += 1                                               # unknown
        owner, = struct.unpack_from('<h', b, p); p += 2
        p += 1; partid, = struct.unpack_from('<h', b, p); p += 2
        p += 1                                               # display mode
        p += 5                                               # symbol inner/outer/inside/outside edges
        dl = b[p]; p += 1 + dl                               # description
        p += 1                                               # formal type
        p += 1                                               # electrical
        cong = b[p]; p += 1
        length, x, y = struct.unpack_from('<hhh', b, p); p += 6
        p += 4                                               # colour
        nl = b[p]; name = b[p + 1:p + 1 + nl].decode('latin1'); p += 1 + nl
        dl = b[p]; des = b[p + 1:p + 1 + dl].decode('latin1')
        return {'RECORD': '2', 'OWNERINDEX': str(owner), 'OWNERPARTID': str(partid), 'PINCONGLOMERATE': str(cong),
                'PINLENGTH': str(length), 'LOCATION.X': str(x), 'LOCATION.Y': str(y), 'NAME': name, 'DESIGNATOR': des}
    except Exception:
        return {}


def acolor(r, key='COLOR', default='#000080'):
    v = r.get(key)
    if v is None:
        return default
    v = int(v)
    return f'#{v & 255:02x}{(v >> 8) & 255:02x}{(v >> 16) & 255:02x}'


def render_schdoc(src, out_pdf):
    recs = altium_records(src)
    num = lambda r, k, d=0.0: float(r.get(k, d)) + float(r.get(k + '_FRAC', 0)) / 100000.0
    loc = lambda r, k='LOCATION': (num(r, k + '.X'), num(r, k + '.Y'))
    fonts = {}
    sheet = next((r for r in recs if r.get('RECORD') == '31'), {})
    for i in range(1, int(sheet.get('FONTIDCOUNT', 0)) + 1):
        fonts[i] = (float(sheet.get(f'SIZE{i}', 10)), sheet.get(f'BOLD{i}') == 'T', sheet.get(f'FONTNAME{i}', 'Arial'))
    fsize = lambda r: fonts.get(int(r.get('FONTID', 1)), (10, False, ''))[0]
    fbold = lambda r: fonts.get(int(r.get('FONTID', 1)), (10, False, ''))[1]
    pts = lambda r: [(num(r, f'X{i}'), num(r, f'Y{i}')) for i in range(1, int(r.get('LOCATIONCOUNT', 0)) + 1)]
    lw = lambda r: [0.4, 1, 3, 5][min(3, int(r.get('LINEWIDTH', 0)))]
    hidden = lambda r: r.get('ISHIDDEN') == 'T'

    # header record is index 0 in the stream; OWNERINDEX counts records after it
    comps = {i - 1: r for i, r in enumerate(recs) if r.get('RECORD') == '1'}
    s = Svg()

    def visible(r):
        o = r.get('OWNERINDEX')
        if o is not None and 0 <= int(o) + 1 < len(recs) and recs[int(o) + 1].get('RECORD') in ('44', '45', '46', '47', '48'):
            return False                                     # model / implementation parameters (SPICE etc.)
        if o is None or int(o) not in comps:
            return True
        c = comps[int(o)]
        pid = int(r.get('OWNERPARTID', -1))
        if pid not in (-1, int(c.get('CURRENTPARTID', 1))):
            return False
        return int(r.get('OWNERPARTDISPLAYMODE', 0)) == int(c.get('DISPLAYMODE', 0))

    # sheet border
    if sheet.get('USECUSTOMSHEET') == 'T':
        W, H = num(sheet, 'CUSTOMX', 1000), num(sheet, 'CUSTOMY', 800)
    else:
        W, H = ALTIUM_SHEETS.get(int(sheet.get('SHEETSTYLE', 0)), (1150, 760))
        if sheet.get('WORKSPACEORIENTATION') == '1':
            W, H = H, W
    if sheet.get('BORDERON', 'T') == 'T':
        s.line([(0, 0), (W, 0), (W, H), (0, H)], '#000000', 1, close=True)
        s.line([(20, 20), (W - 20, 20), (W - 20, H - 20), (20, H - 20)], '#000000', 0.6, close=True)
    if sheet.get('TITLEBLOCKON') == 'T':
        x0 = W - 20 - 350
        s.line([(x0, 20), (x0, 100), (W - 20, 100)], '#000000', 0.6)
        s.text(x0 + 5, 85, 'Title', 8, '#000000')

    for r in recs:
        t = r.get('RECORD')
        if not t or not visible(r):
            continue
        col = acolor(r)
        if t == '2':                                        # pin
            cong = int(r.get('PINCONGLOMERATE', 0))
            if cong & 0x04:
                continue
            x, y = loc(r)
            L = num(r, 'PINLENGTH', 20)
            dx, dy = [(1, 0), (0, 1), (-1, 0), (0, -1)][cong & 3]
            s.line([(x, y), (x + dx * L, y + dy * L)], '#000000', 1)
            rot = 90 if dy else 0
            if cong & 0x08 and r.get('NAME'):
                anchor = 'end' if (dx > 0 or dy > 0) else 'start'
                name = re.sub(r'\\', '', r['NAME'])
                s.text(x - dx * 4 + (2 if dy else 0), y - dy * 4 - (3 if dx else 0), name, 8, '#000000',
                       rot=rot, anchor=anchor)
            if cong & 0x10 and r.get('DESIGNATOR'):
                anchor = 'start' if (dx > 0 or dy > 0) else 'end'
                s.text(x + dx * 3 - (2 if dy else 0), y + dy * 3 + (1.5 if dx else 0), r['DESIGNATOR'], 7, '#000000',
                       rot=rot, anchor=anchor)
        elif t in ('6', '27', '26'):                        # polyline, wire, bus
            w = {'27': 1, '26': 3}.get(t, lw(r))
            s.line(pts(r), col, w if t != '6' else lw(r))
        elif t == '7':                                      # polygon
            fill = acolor(r, 'AREACOLOR') if r.get('ISSOLID') == 'T' else 'none'
            s.line(pts(r), col, lw(r), fill=fill, close=True)
        elif t == '5':                                      # bezier: draw control polygon smoothly enough
            p = pts(r)
            if len(p) >= 4:
                s.grow(*p[0]); s.grow(*p[-1])
                d = f'M{p[0][0]:.2f} {-p[0][1]:.2f} ' + ' '.join(
                    f'C{p[i][0]:.2f} {-p[i][1]:.2f} {p[i + 1][0]:.2f} {-p[i + 1][1]:.2f} {p[i + 2][0]:.2f} {-p[i + 2][1]:.2f}'
                    for i in range(1, len(p) - 2, 3))
                s.parts.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{lw(r)}"/>')
        elif t == '13':                                     # line
            s.line([loc(r), loc(r, 'CORNER')], col, lw(r))
        elif t in ('14', '10', '28'):                       # rectangle, round rectangle, text frame
            (x0, y0), (x1, y1) = loc(r), loc(r, 'CORNER')
            fill = acolor(r, 'AREACOLOR') if r.get('ISSOLID') == 'T' and t != '28' else 'none'
            if t != '28' or r.get('SHOWBORDER') == 'T':
                s.line([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], col, lw(r), fill=fill, close=True)
            if t == '28':
                for k, ln in enumerate(r.get('TEXT', '').replace('~1', '\n').split('\n')):
                    s.text(min(x0, x1) + 3, max(y0, y1) - 8 - k * 10, ln, fsize(r), acolor(r, 'TEXTCOLOR', '#000000'))
        elif t in ('12', '11'):                             # arc, elliptical arc
            x, y = loc(r)
            rad = num(r, 'RADIUS')
            ry = num(r, 'SECONDARYRADIUS') if t == '11' else rad
            s.arc(x, y, rad, float(r.get('STARTANGLE', 0)), float(r.get('ENDANGLE', 360)), col, lw(r), ry=ry)
        elif t == '8':                                      # ellipse
            x, y = loc(r)
            fill = acolor(r, 'AREACOLOR') if r.get('ISSOLID') == 'T' else 'none'
            s.ellipse(x, y, num(r, 'RADIUS'), num(r, 'SECONDARYRADIUS', num(r, 'RADIUS')), col, lw(r), fill=fill)
        elif t == '29':                                     # junction
            x, y = loc(r)
            s.circle(x, y, 2, col, 0, fill=col)
        elif t in ('4', '25', '34', '41') and not hidden(r):  # label, net label, designator, parameter
            text = r.get('TEXT', '')
            if t == '41' and (text.startswith('=') or r.get('NAME', '').startswith('Current')):
                continue
            if not text or text == '*':
                continue
            x, y = loc(r)
            rot = int(r.get('ORIENTATION', 0)) * 90
            just = int(r.get('JUSTIFICATION', 0))
            anchor = ['start', 'middle', 'end'][just % 3]
            s.text(x, y, text, fsize(r), col, rot=rot, anchor=anchor, bold=fbold(r))
        elif t == '17':                                     # power port
            x, y = loc(r)
            o = int(r.get('ORIENTATION', 0))
            dx, dy = [(1, 0), (0, 1), (-1, 0), (0, -1)][o & 3]
            ex, ey = x + dx * 10, y + dy * 10
            s.line([(x, y), (ex, ey)], col, 1)
            px, py = -dy, dx
            style = int(r.get('STYLE', 0))
            if style in (4, 6, 7):                          # ground styles
                for k, h in enumerate((8, 5, 2)):
                    cx, cy = ex + dx * k * 3, ey + dy * k * 3
                    s.line([(cx - px * h, cy - py * h), (cx + px * h, cy + py * h)], col, 1)
                ty = ey + dy * 14
                tx = ex + dx * 14
            else:
                s.line([(ex - px * 7, ey - py * 7), (ex + px * 7, ey + py * 7)], col, 1.5)
                tx, ty = ex + dx * 4, ey + dy * 4
            if r.get('SHOWNETNAME', 'T') == 'T':
                s.text(tx + (0 if dx else 0), ty + (0 if dy <= 0 else 0) - (8 if dy < 0 else 0), r.get('TEXT', ''), 8, col,
                       anchor='middle' if dy else ('start' if dx > 0 else 'end'), base='auto')
        elif t == '18':                                     # port
            x, y = loc(r)
            w, h = num(r, 'WIDTH', 50), num(r, 'HEIGHT', 10)
            vertical = int(r.get('STYLE', 0)) >= 4
            if vertical:
                shape = [(x - h / 2, y), (x + h / 2, y), (x + h / 2, y + w), (x - h / 2, y + w)]
            else:
                shape = [(x, y - h / 2), (x + w - h / 2, y - h / 2), (x + w, y), (x + w - h / 2, y + h / 2), (x, y + h / 2)]
            s.line(shape, col, 1, fill=acolor(r, 'AREACOLOR', '#ffffc0'), close=True)
            s.text(x + (0 if vertical else 4), y - 3 if not vertical else y + 4, r.get('NAME', ''), 8,
                   acolor(r, 'TEXTCOLOR', '#000000'), rot=90 if vertical else 0)
        elif t == '15':                                     # sheet symbol
            x, y = loc(r)
            w, h = num(r, 'XSIZE'), num(r, 'YSIZE')
            s.line([(x, y), (x + w, y), (x + w, y - h), (x, y - h)], col, 1, fill=acolor(r, 'AREACOLOR', '#e0e0ff'), close=True)
        elif t == '16':                                     # sheet entry
            pass
        elif t == '30':                                     # embedded image -> outline only
            (x0, y0), (x1, y1) = loc(r), loc(r, 'CORNER')
            s.line([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], '#999999', 0.5, close=True)
        elif t in ('32', '33'):                             # sheet name / file name
            if not hidden(r):
                x, y = loc(r)
                s.text(x, y, r.get('TEXT', ''), fsize(r), col)
    svg = s.render(bounds=(min(0, s.box[0]), min(0, s.box[1]), max(W, s.box[2]), max(H, s.box[3])))
    cap = f'{os.path.basename(src)}  -  Altium schematic'
    n = compose([(svg_to_pdf_page(svg), cap)], out_pdf, src, 'Altium schematic')
    parts = {}
    for i, c in comps.items():
        des = next((r.get('TEXT') for r in recs if r.get('RECORD') == '34' and r.get('OWNERINDEX') == str(i)), '?')
        val = next((r.get('TEXT') for r in recs if r.get('RECORD') == '41' and r.get('OWNERINDEX') == str(i)
                    and r.get('NAME', '').lower() in ('value', 'comment') and not r.get('TEXT', '').startswith('=')), '')
        parts.setdefault(des, (c.get('LIBREFERENCE', ''), val, c.get('COMPONENTDESCRIPTION', '')))
    nets = sorted({r.get('TEXT', '') for r in recs if r.get('RECORD') in ('25', '17')} - {''})
    ports = sorted({r.get('NAME', '') for r in recs if r.get('RECORD') == '18'} - {''})
    table = '| Designator | Part | Value | Description |\n|---|---|---|---|\n' + '\n'.join(
        f'| {d} | {p} | {v} | {x} |'.replace('\n', ' ') for d, (p, v, x) in sorted(parts.items(), key=lambda kv: natural(kv[0])))
    return {'pages': n, 'captions': [cap], 'type': 'Altium Designer / Protel DXP schematic',
            'summary': f'PDF rendering of the Altium schematic sheet {os.path.basename(src)}: {len(parts)} components, '
                       f'{len(nets)} net / power labels, {len(ports)} ports.',
            'details': [('Header', recs[0].get('HEADER', '')), ('Sheet size', f'{W / 100:.1f} x {H / 100:.1f} in'),
                        ('Net and power labels', ', '.join(nets)), ('Ports', ', '.join(ports)),
                        ('Pipeline', 'records read from the OLE `FileHeader` stream (olefile) and drawn by render_cad_pdfs.py '
                                     '(wires, symbols, pins, labels, power ports, ports); fonts approximate, images shown as boxes')],
            'sections': [('Components', table)] if parts else []}


# ============================================================================================ Eagle schematic
EAGLE_COL = {91: '#00a000', 92: '#0000c0', 93: '#008000', 94: '#900000', 95: '#606060', 96: '#606060', 97: '#000000',
             98: '#000000'}


def eagle_rot(spec):
    spec = spec or 'R0'
    m = re.search(r'R([\d.]+)', spec)
    return float(m.group(1)) if m else 0.0, 'M' in spec


def xf_point(x, y, ox, oy, rot, mirror):
    if mirror:
        x = -x
    a = math.radians(rot)
    return ox + x * math.cos(a) - y * math.sin(a), oy + x * math.sin(a) + y * math.cos(a)


def render_eagle_sch(src, out_pdf):
    import xml.etree.ElementTree as ET
    root = ET.parse(src).getroot()
    f = lambda e, k, d=0.0: float(e.get(k, d))
    symbols, devsets = {}, {}
    for lib in root.iter('library'):
        ln = lib.get('name')
        for sym in lib.iter('symbol'):
            symbols[(ln, sym.get('name'))] = sym
        for ds in lib.iter('deviceset'):
            devsets[(ln, ds.get('name'))] = ds
    parts = {p.get('name'): p for p in root.iter('part')}

    def draw_prims(s, el, ox, oy, rot, mir, subs=None, attrs=None):
        T = lambda x, y: xf_point(x, y, ox, oy, rot, mir)
        for e in el:
            col = EAGLE_COL.get(int(e.get('layer', 94)), '#900000')
            if e.tag == 'wire':
                p0, p1 = T(f(e, 'x1'), f(e, 'y1')), T(f(e, 'x2'), f(e, 'y2'))
                curve = f(e, 'curve')
                w = max(f(e, 'width', 0.1524), 0.12)
                if curve:
                    ch = math.dist(p0, p1)
                    r = abs(ch / (2 * math.sin(math.radians(curve) / 2))) if ch else 0
                    sweep = 0 if (curve > 0) != mir else 1
                    s.grow(*p0); s.grow(*p1)
                    s.parts.append(f'<path d="M{p0[0]:.3f} {-p0[1]:.3f} A{r:.3f} {r:.3f} 0 {1 if abs(curve) > 180 else 0} '
                                   f'{sweep} {p1[0]:.3f} {-p1[1]:.3f}" fill="none" stroke="{col}" stroke-width="{w:.3f}"/>')
                else:
                    s.line([p0, p1], col, w)
            elif e.tag == 'circle':
                x, y = T(f(e, 'x'), f(e, 'y'))
                w = f(e, 'width', 0.1524)
                s.circle(x, y, f(e, 'radius'), col, w, fill=col if w == 0 else 'none')
            elif e.tag == 'rectangle':
                c = [T(f(e, 'x1'), f(e, 'y1')), T(f(e, 'x2'), f(e, 'y1')), T(f(e, 'x2'), f(e, 'y2')), T(f(e, 'x1'), f(e, 'y2'))]
                s.line(c, col, 0.1, fill=col, close=True)
            elif e.tag == 'polygon':
                c = [T(f(v, 'x'), f(v, 'y')) for v in e.iter('vertex')]
                s.line(c, col, f(e, 'width', 0.1), fill=col, close=True)
            elif e.tag == 'pin':
                x, y = f(e, 'x'), f(e, 'y')
                L = {'point': 0, 'short': 2.54, 'middle': 5.08, 'long': 7.62}.get(e.get('length', 'long'), 7.62)
                prot, _ = eagle_rot(e.get('rot'))
                a = math.radians(prot)
                ex, ey = x + L * math.cos(a), y + L * math.sin(a)
                s.line([T(x, y), T(ex, ey)], '#900000', 0.1524)
                vis = e.get('visible', 'both')
                if vis in ('both', 'pin') and L:
                    tx, ty = T(ex + 1.5 * math.cos(a), ey + 1.5 * math.sin(a))
                    world = (prot + rot) % 360 if not mir else (180 - prot + rot) % 360
                    vert = world in (90, 270)
                    anchor = 'start' if world in (0, 90) else 'end'
                    s.text(tx, ty - (0 if vert else 0.6), e.get('name', '').split('@')[0], 1.4, '#606060',
                           rot=90 if vert else 0, anchor=anchor)
            elif e.tag == 'text':
                txt = e.text or ''
                if subs:
                    for k, v in subs.items():
                        txt = txt.replace(k, v)
                if txt.startswith('>'):
                    continue
                x, y = T(f(e, 'x'), f(e, 'y'))
                trot, _ = eagle_rot(e.get('rot'))
                s.text(x, y, txt, f(e, 'size', 1.778), col, rot=(trot + rot) % 180)

    s_pages = []
    sheets = list(root.iter('sheet'))
    for n, sh in enumerate(sheets, 1):
        s = Svg()
        plain = sh.find('plain')
        if plain is not None:
            draw_prims(s, plain, 0, 0, 0, False)
        for inst in sh.iter('instance'):
            part = parts.get(inst.get('part'))
            if part is None:
                continue
            ds = devsets.get((part.get('library'), part.get('deviceset')))
            if ds is None:
                continue
            gate = next((g for g in ds.iter('gate') if g.get('name') == inst.get('gate')), None)
            if gate is None:
                continue
            lib = part.get('library')
            sym = symbols.get((lib, gate.get('symbol')))
            if sym is None:
                continue
            rot, mir = eagle_rot(inst.get('rot'))
            ox, oy = f(inst, 'x'), f(inst, 'y')
            gname = inst.get('gate') if len(list(ds.iter('gate'))) > 1 and not inst.get('gate', '').startswith('G$') else ''
            subs = {'>NAME': part.get('name') + gname, '>VALUE': part.get('value') or part.get('deviceset'),
                    '>PART': part.get('name'), '>GATE': inst.get('gate', '')}
            smashed = inst.get('smashed') == 'yes'
            draw_prims(s, [e for e in sym if not (smashed and e.tag == 'text' and (e.text or '').startswith('>'))],
                       ox, oy, rot, mir, subs)
            if smashed:
                for a in inst.iter('attribute'):
                    if a.get('display') == 'off':
                        continue
                    v = subs.get('>' + a.get('name', ''))
                    if v:
                        arot, _ = eagle_rot(a.get('rot'))
                        s.text(f(a, 'x'), f(a, 'y'), v, f(a, 'size', 1.778),
                               EAGLE_COL.get(int(a.get('layer', 95)), '#606060'), rot=arot % 180)
            else:
                for e in sym:
                    if e.tag == 'text' and (e.text or '').startswith('>'):
                        x, y = xf_point(f(e, 'x'), f(e, 'y'), ox, oy, rot, mir)
                        s.text(x, y, subs.get(e.text, ''), f(e, 'size', 1.778), '#606060')
        for net in list(sh.iter('net')) + list(sh.iter('bus')):
            col = '#00a000' if net.tag == 'net' else '#0000c0'
            for seg in net.iter('segment'):
                for e in seg:
                    if e.tag == 'wire':
                        s.line([(f(e, 'x1'), f(e, 'y1')), (f(e, 'x2'), f(e, 'y2'))], col,
                               max(f(e, 'width', 0.1524), 0.15) * (2 if net.tag == 'bus' else 1))
                    elif e.tag == 'junction':
                        s.circle(f(e, 'x'), f(e, 'y'), 0.5, col, 0, fill=col)
                    elif e.tag == 'label':
                        lrot, _ = eagle_rot(e.get('rot'))
                        s.text(f(e, 'x'), f(e, 'y'), net.get('name', ''), f(e, 'size', 1.778), col, rot=lrot % 180)
        if s.parts:
            s_pages.append((svg_to_pdf_page(s.render(pad=3)),
                            f'{os.path.basename(src)}  -  Eagle schematic  -  sheet {n} of {len(sheets)}'))
    if not s_pages:
        raise RuntimeError('no sheets')
    n = compose(s_pages, out_pdf, src, 'Eagle schematic')
    table = '| Part | Library | Device | Value |\n|---|---|---|---|\n' + '\n'.join(
        f'| {p.get("name")} | {p.get("library")} | {p.get("deviceset")}{p.get("device", "")} | {p.get("value") or ""} |'
        for p in sorted(parts.values(), key=lambda p: natural(p.get('name'))))
    nets = sorted({n.get('name') for n in root.iter('net')})
    return {'pages': n, 'captions': [c for _, c in s_pages], 'type': 'Eagle schematic',
            'summary': f'PDF rendering of the Eagle schematic {os.path.basename(src)}: {len(sheets)} sheet(s), '
                       f'{len(parts)} parts, {len(nets)} nets.',
            'details': [('Eagle version', root.get('version', '')), ('Nets', ', '.join(nets)),
                        ('Pipeline', 'Eagle XML parsed and drawn by render_cad_pdfs.py (library symbols, nets, labels, '
                                     'junctions, plain drawing layer)')],
            'sections': [('Parts', table)] if parts else []}


# ============================================================================================ Gerbers
ROLE_COLOURS = {'top copper': '#c8102e', 'bottom copper': '#1f5fbf', 'inner copper': '#b07a00', 'top silk': '#202020',
                'bottom silk': '#505050', 'top mask': '#2f8f4f', 'bottom mask': '#2f8f4f', 'top paste': '#9a9a9a',
                'bottom paste': '#9a9a9a', 'outline': '#000000', 'drill': '#000000', 'other': '#7a4fa0'}


def gerber_role(name):
    n = os.path.basename(name).lower()
    ext = n.rsplit('.', 1)[-1]
    table = [('gtl', 'top copper'), ('gbl', 'bottom copper'), ('gto', 'top silk'), ('gbo', 'bottom silk'),
             ('gts', 'top mask'), ('gbs', 'bottom mask'), ('gtp', 'top paste'), ('gbp', 'bottom paste'),
             ('gko', 'outline'), ('cmp', 'top copper'), ('sol', 'bottom copper'), ('plc', 'top silk'),
             ('pls', 'bottom silk'), ('stc', 'top mask'), ('sts', 'bottom mask'), ('crc', 'top paste'), ('crs', 'bottom paste')]
    for e, r in table:
        if ext == e:
            return r
    if re.fullmatch(r'gm\d+', ext):
        return 'outline' if ext == 'gm1' else 'other'
    if re.fullmatch(r'g\d+|gp\d+', ext):
        return 'inner copper'
    if DRILL_EXT.search(n):
        return 'drill'
    stem = n.rsplit('.', 1)[0]
    for pat, r in [(r'(^|[^a-z])(l1|top|comp|cs)([^a-z]|$)', 'top copper'), (r'(bot|bottom|sold|ss$|l\d+-bot)', 'bottom copper'),
                   (r'silk.*(top|t$)|(top|t)silk|sst|^st$|^pt$', 'top silk'), (r'silk.*(bot|b$)|ssb|^sb$|^pb$', 'bottom silk'),
                   (r'mask.*(top|t$)|smt|^mt$', 'top mask'), (r'mask.*(bot|b$)|smb|^mb$', 'bottom mask'),
                   (r'paste.*top|spt', 'top paste'), (r'paste.*bot|spb', 'bottom paste'),
                   (r'outline|edge|board|route|rout|mill|^dd$|fab|drill', 'outline'), (r'^l\d+|inner|gnd|pwr|sig', 'inner copper')]:
        if re.search(pat, stem):
            return r
    return 'other'


def sniff_gerber(path):
    try:
        head = open(path, 'rb').read(4096).decode('latin1')
    except OSError:
        return None
    if re.search(r'%FS[LT][AI]|%MO(IN|MM)|G04 |%ADD\d', head) or re.search(r'^\s*(G0[1-3])?X-?\d+Y-?\d+D0[1-3]\*', head, re.M):
        return 'gerber'
    if re.search(r'^M48\s*$', head, re.M) or re.search(r'^T\d+C[\d.]+', head, re.M):
        return 'excellon'
    return None


def gerber_jobs(dirpath, names):
    """Group the Gerber/drill files in one folder into jobs: {job name: [paths]}."""
    gerbers = [n for n in names if GERBER_EXT.search(n) and not n.endswith('.md')]
    if not gerbers:
        return {}
    files = [n for n in gerbers if sniff_gerber(os.path.join(dirpath, n)) == 'gerber']
    if not files:
        return {}
    drills = [n for n in names if DRILL_EXT.search(n) and sniff_gerber(os.path.join(dirpath, n)) == 'excellon']
    layer_ext = re.compile(r'\.(gtl|gbl|gto|gbo|gts|gbs|gtp|gbp|gko|gm\d+|g\d+|gp\d+)$', re.I)
    stems = defaultdict(list)
    for n in files:
        stems[n.rsplit('.', 1)[0] if layer_ext.search(n) else ''].append(n)
    jobs = {}
    generic = stems.pop('', [])
    for stem, fs in stems.items():
        jobs[stem] = fs + [d for d in drills if d.lower().startswith(stem.lower())]
    if generic:
        if len(jobs) == 1:                                   # loose .gbr/.pho next to one board: same job
            next(iter(jobs.values())).extend(generic)
        else:
            name = os.path.basename(dirpath.rstrip('/')) or 'board'
            name = '' if re.search(r'gerber', name, re.I) else name
            jobs.setdefault(name, []).extend(generic)
    used = {d for fs in jobs.values() for d in fs}
    left = [d for d in drills if d not in used]
    if left and len(jobs) == 1:
        next(iter(jobs.values())).extend(left)
    return {k: [os.path.join(dirpath, n) for n in sorted(v)] for k, v in jobs.items()}


def render_gerbers(job, paths, out_pdf):
    from gerbonara import GerberFile, ExcellonFile
    from gerbonara.utils import MM
    warnings.simplefilter('ignore')
    layers, notes = [], []
    for p in paths:
        try:
            kind = sniff_gerber(p)
            lf = ExcellonFile.open(p) if kind == 'excellon' else GerberFile.open(p)
            bb = lf.bounding_box(MM, default=None)
            if bb is None:
                notes.append(os.path.basename(p) + ' (empty)')
                continue
            layers.append((p, gerber_role(p) if kind != 'excellon' else 'drill', lf, bb))
        except Exception as e:
            notes.append(f'{os.path.basename(p)} ({type(e).__name__})')
    if not layers:
        raise RuntimeError('no readable layers: ' + '; '.join(notes))
    # common frame, ignoring layers wildly outside the board (stray origin markers etc.)
    # composite frame = board outline (or copper if there is no outline layer); stray artwork outside is cropped
    core = [l for l in layers if l[1] == 'outline'] or [l for l in layers if 'copper' in l[1]] or layers
    x0 = min(b[0][0] for *_, b in core); y0 = min(b[0][1] for *_, b in core)
    x1 = max(b[1][0] for *_, b in core); y1 = max(b[1][1] for *_, b in core)
    bounds = ((x0, y0), (x1, y1))
    m = max(x1 - x0, y1 - y0) * 0.03 + 1

    def layer_svg(lf, fg, bg, own=False):
        if own:
            b = lf.bounding_box(MM)
            return str(lf.to_svg(margin=max(b[1][0] - b[0][0], b[1][1] - b[0][1]) * 0.03 + 1, arg_unit=MM, svg_unit=MM,
                                 force_bounds=b, fg=fg, bg=bg))
        return str(lf.to_svg(margin=m, arg_unit=MM, svg_unit=MM, force_bounds=bounds, fg=fg, bg=bg))

    def inner(svg):
        return svg[svg.index('>', svg.index('<svg')) + 1:svg.rindex('</svg>')]

    def composite(side):
        order = ['outline', 'inner copper', 'bottom copper', 'top copper', 'bottom silk', 'top silk', 'drill', 'other']
        want = {'top': {'outline', 'top copper', 'top silk', 'drill'}, 'bottom': {'outline', 'bottom copper', 'bottom silk', 'drill'}}[side]
        chosen = [l for l in layers if l[1] in want]
        if not any(l[1].endswith('copper') for l in chosen):
            return None
        chosen.sort(key=lambda l: order.index(l[1]) if l[1] in order else 99)
        head = layer_svg(chosen[0][2], '#000', 'none')
        open_tag = head[head.index('<svg'):head.index('>', head.index('<svg')) + 1]
        vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', open_tag).group(1).split()]
        body = f'<rect x="{vb[0]}" y="{vb[1]}" width="{vb[2]}" height="{vb[3]}" fill="#ffffff"/>'
        for p, role, lf, _ in chosen:
            col = ROLE_COLOURS.get(role, '#777')
            op = 0.75 if 'copper' in role else 1
            body += f'<g opacity="{op}">{inner(layer_svg(lf, col, "none"))}</g>'
        if side == 'bottom':
            body = f'<g transform="translate({2 * vb[0] + vb[2]} 0) scale(-1 1)">{body}</g>'
        return open_tag + body + '</svg>'

    pages = []
    names = ', '.join(os.path.basename(p) for p, *_ in layers)
    for side in ('top', 'bottom'):
        svg = composite(side)
        if svg:
            pages.append((svg_to_pdf_page(svg), f'{job}  -  {side.upper()} view{" (mirrored, seen from below)" if side == "bottom" else ""}'
                                               f'  -  {names}'[:160]))
    for p, role, lf, _ in layers:
        pages.append((svg_to_pdf_page(layer_svg(lf, '#000000', '#ffffff', own=True)), f'{job}  -  {os.path.basename(p)}  -  {role}'))
    if notes:
        pages[0] = (pages[0][0], pages[0][1] + '   [unreadable: ' + '; '.join(notes) + ']')
    n = compose(pages, out_pdf, os.path.join(os.path.dirname(paths[0]), job), 'Gerber job')
    table = '| Page | File | Layer (guessed from name) | Size (mm) |\n|---|---|---|---|\n' + '\n'.join(
        f'| {i + 1 + n - len(layers)} | {os.path.basename(p)} | {role} | {b[1][0] - b[0][0]:.1f} x {b[1][1] - b[0][1]:.1f} |'
        for i, (p, role, _, b) in enumerate(layers))
    return {'pages': n, 'captions': [c for _, c in pages], 'type': 'Gerber photoplot job',
            'summary': f'PDF of the Gerber job {job}: {len(layers)} layer / drill files, board about '
                       f'{x1 - x0:.1f} x {y1 - y0:.1f} mm ({(x1 - x0) / 25.4:.2f} x {(y1 - y0) / 25.4:.2f} in).',
            'details': [('Unreadable files', '; '.join(notes) or 'none'),
                        ('Pipeline', 'gerbonara parses each Gerber (RS-274X) and Excellon drill file; pages 1-2 are colour '
                                     'composites cropped to the board outline (bottom view mirrored), then one black-on-white '
                                     'page per file at its own extents')],
            'sections': [('Layers', table)], 'sources': paths}


# ============================================================================================ CorelDRAW
def render_cdr(src, out_pdf):
    import fitz
    with tempfile.TemporaryDirectory() as tmp:
        prof = os.path.join(tmp, 'profile')
        p = subprocess.run(['soffice', f'-env:UserInstallation=file://{prof}', '--headless', '--convert-to', 'pdf',
                            '--outdir', tmp, src], capture_output=True, timeout=300)
        made = [f for f in os.listdir(tmp) if f.lower().endswith('.pdf')]
        if not made:
            raise RuntimeError('LibreOffice could not open it (CorelDRAW version not supported by libcdr?)')
        doc = fitz.open(os.path.join(tmp, made[0]))
        if not any(pg.get_drawings() or pg.get_text().strip() or pg.get_images() for pg in doc):
            raise RuntimeError('LibreOffice produced an empty page')
        texts = [pg.get_text().strip() for pg in doc]
        doc.set_metadata({'title': os.path.basename(src), 'creator': CREATOR, 'producer': CREATOR, 'author': 'Ward-Beck Systems',
                          'subject': f'CorelDRAW artwork rendered from {os.path.basename(src)}'})
        tmp_out = out_pdf + '.part'
        doc.save(tmp_out, garbage=3, deflate=True)
        os.replace(tmp_out, out_pdf)
        n = len(doc)
    ver = open(src, 'rb').read(12)
    return {'pages': n, 'captions': [f'{os.path.basename(src)}  -  page {i + 1}' for i in range(n)], 'type': 'CorelDRAW artwork',
            'summary': f'PDF rendering of the CorelDRAW file {os.path.basename(src)} ({n} page(s)).',
            'details': [('Format tag', ver[8:12].decode('latin1', 'replace') if ver[:4] == b'RIFF' else 'zip (CorelDRAW X4+)'),
                        ('Pipeline', 'LibreOffice Draw (libcdr) headless export to PDF; fonts substituted where the '
                                     'original typefaces are not installed')],
            'sections': [(f'Text on page {i + 1}', t) for i, t in enumerate(texts) if t]}


def natural(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s or '')]


# ============================================================================================ markdown sidecars
def yr(ts):
    y = int(time.strftime('%Y', time.localtime(ts)))
    return f'{y}|{y - 1967} · {time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))}'


def archive_root(path):
    env = os.environ.get('WBS_ROOT')
    d = os.path.dirname(os.path.abspath(path))
    while d != '/':
        if os.path.basename(d) == 'WBS - DATA SHUFFLER':
            return d
        d = os.path.dirname(d)
    return os.path.abspath(env) if env else os.path.dirname(os.path.abspath(path))


def link(target, frm_dir):
    from urllib.parse import quote
    return quote(os.path.relpath(target, frm_dir))


def write_sidecars(out_pdf, sources, facts):
    """FOO.pdf.md describing the rendered PDF, plus a 'Rendered PDF' line in each source's existing .md."""
    d = os.path.dirname(out_pdf)
    note = note_for(out_pdf)   # beside the PDF, or <M>/OCR/FOO.pdf.md in a module's kind folder
    nd = os.path.dirname(note)   # links are written from the note's own folder
    root = archive_root(out_pdf)
    rel = os.path.relpath(d, root)
    product = rel.split(os.sep)[0] if rel != '.' else os.path.basename(root)
    audit = os.path.join(os.path.dirname(root), os.path.basename(root) + ' - AUDIT.md')
    L = [f'# {os.path.basename(out_pdf)}', '',
         f'Product folder: **{product}** · Folder: `{rel}`  ',
         f'Archive: {os.path.basename(root)} · Audit: [archive audit]({link(audit, nd)})', '',
         '## Summary', '', facts['summary'], '',
         '## File', '',
         f'- **Type:** PDF rendering of a {facts["type"]} (`.pdf`)',
         f'- **Rendered:** {yr(time.time())} by `render_cad_pdfs.py`',
         f'- **Pages:** {facts["pages"]}',
         f'- **Size:** {os.path.getsize(out_pdf):,} bytes']
    for s in sources:
        L.append(f'- **Source:** [{os.path.basename(s)}]({link(s, nd)}) · modified {yr(os.path.getmtime(s))} · '
                 f'{os.path.getsize(s):,} bytes')
    for k, v in facts.get('details', []):
        if v:
            L.append(f'- **{k}:** {v}')
    L.append('- ⚠ This PDF is a machine rendering for reading, not an original plot: check dimensions and '
             'fine detail against the source file.')
    L += ['', '## Pages', ''] + [f'{i}. {c}' for i, c in enumerate(facts.get('captions', []), 1)]
    for head, body in facts.get('sections', []):
        L += ['', f'## {head}', '', body]
    L += ['', '---', '_Sidecar generated by `render_cad_pdfs.py` · An archive by Anthony Peter Kuzub · WBSps.ca_', '']
    os.makedirs(nd, exist_ok=True)
    with open(note, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))
    line = f'- **Rendered PDF:** [{os.path.basename(out_pdf)}]({{}}) ({facts["pages"]} page(s), made by `render_cad_pdfs.py`)'
    for s in sources:
        md = note_for(s)
        if not os.path.exists(md):
            continue
        txt = open(md, encoding='utf-8').read()
        new = line.format(link(out_pdf, os.path.dirname(md)))
        if new in txt:
            continue
        txt = re.sub(r'^- \*\*Rendered PDF:\*\*.*\n', '', txt, flags=re.M)
        if '\n- **Type:**' in txt:
            i = txt.index('\n', txt.index('\n- **Type:**') + 1)
            txt = txt[:i + 1] + new + '\n' + txt[i + 1:]
        else:
            txt = txt.rstrip('\n') + '\n\n' + new + '\n'
        with open(md, 'w', encoding='utf-8') as f:
            f.write(txt)


# ============================================================================================ discovery
def sch_kind(path):
    try:
        head = open(path, 'rb').read(512)
    except OSError:
        return None
    if path.lower().endswith('.schdoc'):
        return 'schdoc' if head.startswith(b'\xd0\xcf\x11\xe0') else None
    if b'<eagle' in head or b'eagle.dtd' in head:
        return 'eagle'
    if head.startswith(b'\xd0\xcf\x11\xe0') and b'Protel' in open(path, 'rb').read(1 << 16):
        return 'schdoc'     # Protel 99/DXP binary saved as .sch
    return None


def discover(root, only):
    """Yield work items: (kind, source path or job name, [paths], out_pdf)."""
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        stems = defaultdict(list)
        cands = []
        for n in names:
            low = n.lower()
            p = os.path.join(dirpath, n)
            if 'dwg' in only and low.endswith('.dwg'):
                cands.append(('dwg', p))
            elif 'cdr' in only and low.endswith('.cdr'):
                cands.append(('cdr', p))
            elif 'sch' in only and low.endswith(('.schdoc', '.sch')):
                k = sch_kind(p)
                if k:
                    cands.append((k, p))
        for k, p in cands:
            stems[os.path.splitext(os.path.basename(p))[0].lower()].append(p)
        for k, p in cands:
            stem = os.path.splitext(p)[0]
            out = (p + '.pdf') if len(stems[os.path.basename(stem).lower()]) > 1 else stem + '.pdf'
            yield k, p, [p], out
        if 'gerber' in only:
            for job, paths in gerber_jobs(dirpath, names).items():
                yield 'gerber', os.path.join(dirpath, job or 'GERBERS'), paths, \
                    os.path.join(dirpath, f'{job} GERBERS.pdf' if job else 'GERBERS.pdf')


def render_one(kind, src, paths, out):
    if kind == 'dwg':
        facts = render_dwg(src, out)
    elif kind == 'schdoc':
        facts = render_schdoc(src, out)
    elif kind == 'eagle':
        facts = render_eagle_sch(src, out)
    elif kind == 'cdr':
        facts = render_cdr(src, out)
    elif kind == 'gerber':
        facts = render_gerbers(os.path.basename(src), paths, out)
    else:
        raise ValueError(kind)
    write_sidecars(out, facts.get('sources', paths), facts)
    return facts['pages']


def existing_pdf_case_insensitive(out):
    d, b = os.path.split(out)
    try:
        for n in os.listdir(d):
            if n.lower() == b.lower():
                return os.path.join(d, n)
    except OSError:
        pass
    return None


# ============================================================================================ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('root', nargs='?')
    ap.add_argument('--setup', action='store_true', help='build LibreDWG and the Python venv, then exit')
    ap.add_argument('--only', default='dwg,gerber,sch,cdr', help='comma list of dwg, gerber, sch, cdr')
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument('--force', action='store_true', help='re-render even if our PDF is newer than the source')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--timeout', type=int, default=600, help='seconds per item')
    ap.add_argument('--one', help='render a single file (or a folder of Gerbers) and exit')
    ap.add_argument('--worker', nargs=4, metavar=('KIND', 'SRC', 'OUT', 'PATHS'), help=argparse.SUPPRESS)
    a = ap.parse_args()

    if a.setup:
        return setup()
    ensure_venv()
    if a.worker:
        kind, src, out, paths = a.worker
        n = render_one(kind, src, paths.split('\x1f'), out)
        print(f'pages={n}')
        return
    if a.one:
        p = os.path.abspath(a.one)
        if os.path.isdir(p):
            items = [i for i in discover_dir_only(p)]
        else:
            items = [i for i in discover(os.path.dirname(p), {'dwg', 'sch', 'cdr'}) if i[1] == p]
        for kind, src, paths, out in items:
            print(kind, src, '->', out, 'pages', render_one(kind, src, paths, out))
        return
    if not a.root:
        ap.error('give a ROOT folder (or --setup / --one)')

    only = set(a.only.split(','))
    os.environ['WBS_ROOT'] = os.path.abspath(a.root)
    todo, skipped = [], defaultdict(int)
    for kind, src, paths, out in discover(a.root, only):
        have = existing_pdf_case_insensitive(out)
        if have:
            if not ours(have):
                skipped['original PDF kept'] += 1
                log_row('kept-original', src, have, 'a PDF not made by this script already exists')
                continue
            out = have
            if not a.force and os.path.getmtime(have) >= max(os.path.getmtime(p) for p in paths):
                skipped['up to date'] += 1
                continue
        todo.append((kind, src, paths, out))
        if a.limit and len(todo) >= a.limit:
            break
    counts = defaultdict(int)
    for k, *_ in todo:
        counts[k] += 1
    print(f'to render: {dict(counts)}   skipped: {dict(skipped)}', flush=True)
    if a.dry_run:
        for kind, src, paths, out in todo:
            print(f'{kind:7s} {out}')
        return

    def run(item):
        kind, src, paths, out = item
        t = time.time()
        try:
            p = subprocess.run([sys.executable, os.path.abspath(__file__), '--worker', kind, src, out, '\x1f'.join(paths)],
                               capture_output=True, text=True, timeout=a.timeout)
            ok = p.returncode == 0 and os.path.exists(out)
            note = (p.stdout.strip().splitlines() or [''])[-1] if ok else (p.stderr.strip().splitlines() or ['failed'])[-1]
        except subprocess.TimeoutExpired:
            ok, note = False, f'timeout after {a.timeout}s'
        return item, ok, note[:300], time.time() - t

    done = fails = 0
    with ThreadPoolExecutor(a.jobs) as pool:
        for fut in as_completed([pool.submit(run, i) for i in todo]):
            (kind, src, paths, out), ok, note, dt = fut.result()
            done += 1
            fails += not ok
            log_row('ok' if ok else 'FAIL', src, out, f'{kind} {note} {dt:.1f}s')
            print(f'[{done}/{len(todo)}] {"ok  " if ok else "FAIL"} {kind:6s} {os.path.relpath(out, a.root)}  {note if not ok else ""}',
                  flush=True)
    print(f'done: {done - fails} rendered, {fails} failed - log: {LOG}')


def discover_dir_only(d):
    for kind, src, paths, out in discover(d, {'gerber'}):
        if os.path.dirname(paths[0]) == d:
            yield kind, src, paths, out


def log_row(status, src, out, note):
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")}\t{status}\t{src}\t{out}\t{note}\n')


if __name__ == '__main__':
    main()
