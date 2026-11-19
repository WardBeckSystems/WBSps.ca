"""Build 2026/index.html, the landing page for the WBSps.ca 2026 archive.

Usage: python3 make_index.py <path to 2026>

Styled as a 1970s Ward-Beck manual: black vinyl binder with a typed spine card,
typewritten letter pages inside. Reads only the 2026/ tree (and
timelines/wbs_timeline.db read-only when it has a `modules` table), so it can be
re-run after every build. No imports outside the standard library.
"""
import datetime, html, json, os, re, sys, sqlite3
from urllib.parse import quote

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else '.')
DOC_EXT = {'.pdf', '.docx', '.doc', '.xlsx', '.xls'}
e = html.escape


def href(*parts):
    return '/'.join(quote(p) for p in parts)


def exists(*parts):
    return os.path.exists(os.path.join(ROOT, *parts))


def count_files(path):
    n = docs = 0
    for _, _, fs in os.walk(path):
        for f in fs:
            if f.endswith(('.json', '.md', ' (traced).dxf')):   # notes, sidecars and the tracer's CAD files are not archive files
                continue
            n += 1
            docs += os.path.splitext(f)[1].lower() in DOC_EXT
    return n, docs


def module_info():
    """{code: (year, name)} from the timeline database; `name` exists only in newer builds"""
    db = os.path.join(ROOT, 'timelines', 'wbs_timeline.db')
    try:
        con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        cols = [r[1] for r in con.execute('pragma table_info(modules)')]
        if 'code' in cols and 'year' in cols:
            name = 'name' if 'name' in cols else "''"
            return {c: (y, (n or '').strip()) for c, y, n in con.execute(f'select code, year, {name} from modules')}
    except sqlite3.Error:
        pass
    return {}


def sub_items():
    """{code: [(item, title, family)]} from timelines/make_registers.py (sub-assemblies, boards, transformers used)."""
    db = os.path.join(ROOT, 'timelines', 'wbs_timeline.db')
    out = {}
    try:
        con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        rows = con.execute('''SELECT u.code, u.item, i.title, i.family, MAX(u.weight) w FROM reg_used u JOIN reg_items i ON i.item = u.item
                              GROUP BY u.code, u.item ORDER BY u.code, w DESC, u.item''').fetchall()
    except sqlite3.Error:
        return out
    for code, item, title, fam, w in rows:
        out.setdefault(code, []).append((item, title or '', fam))
    return out


def context_info():
    """{code: ([jobs / consoles it is part of], files naming it)} from make_mentions.py and the job lists."""
    db = os.path.join(ROOT, 'timelines', 'wbs_timeline.db')
    out = {}
    try:
        con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        for j, c in con.execute('SELECT job, code FROM job_modules ORDER BY job'):
            out.setdefault(c, ([], [0]))[0].append(j)
        for c, n in con.execute("""SELECT m.code, COUNT(DISTINCT m.sha256) FROM mentions m JOIN files f ON f.sha256 = m.sha256
                                   WHERE f.kind NOT IN ('job', 'console') GROUP BY m.code"""):
            out.setdefault(c, ([], [0]))[1][0] = n
    except sqlite3.Error:
        pass
    return {c: (js, n[0]) for c, (js, n) in out.items()}


def context_html(code):
    js, n = context.get(code, ([], 0))
    wiki = href('PAGES', code + '.html')
    js = [j for j in js if j.isdigit() or re.fullmatch(r'[A-Z]{1,3}\d{3,5}[A-Z]?', j)]   # job numbers and console models, not folder names
    num = sorted((j for j in js if j.isdigit()), key=lambda j: (len(j), j)) + sorted((j for j in js if not j.isdigit()), key=natkey)
    shown = [f'<a href="{href("PAGES", "Job-" + j + ".html")}">{e(j)}</a>' if exists('PAGES', 'Job-' + j + '.html') else e(j[:12])
             for j in num[:2]]
    more = f' <a href="{wiki}" title="all {len(num)} consoles / jobs">+{len(num) - 2}</a>' if len(num) > 2 else ''
    docs = f'<a href="{wiki}" title="other drawings and documents that name {e(code)}">{n} doc{"s" * (n != 1)}</a>' if n else ''
    if not num and not n:
        return '<span class="ctx">--</span>'
    return '<span class="ctx">' + (' · '.join(shown) + more + ('<br>' if docs and shown else '') if shown else '') + docs + '</span>'


SERIES_ALIAS = {'MICRO SERIES': 'INTERCOM (MICRO SERIES)'}   # what the series is: Ward-Beck's intercom line


def spaced_name(name):
    """Folder names to headings: Input-Pre-Amps -> Input Pre Amps; a series like 60-x keeps its dash."""
    return re.sub(r'-(?!x\b)', ' ', SERIES_ALIAS.get(name, name))


def wy(y):
    """Years as Ward-Beck years: 1975|8 is the eighth year after the company opened in 1967|0."""
    return f'{y}|{int(y) - 1967}' if y else '--'


def register_href(item, fam):
    slug = lambda t: re.sub(r'[^A-Za-z0-9]+', '-', t).strip('-')
    return href('PAGES', f'Register-{slug(fam)}.html') + '#' + slug(item).lower()


subs = sub_items()
context = context_info()
info = module_info()
years = {c: y for c, (y, _) in info.items() if y}
names = {c: n for c, (_, n) in info.items() if n and n.lower() != 'price list'}
MODEL_NAMES = dict(names)   # kept apart: "names" is used again further down for the thanks list
design = {d for d in os.listdir(os.path.join(ROOT, 'Engineering')) if not d.startswith('_')} if exists('Engineering') else set()

def natkey(s):
    """Model numbers in number order: POD2 < POD10 < POD10A < POD12, M402 < M1026."""
    return [int(t) if t.isdigit() else t.upper() for t in re.split(r'(\d+)', s)]


def visible_dirs(*parts):
    path = os.path.join(ROOT, *parts)
    if not os.path.isdir(path):
        return []
    return [d for d in sorted(os.listdir(path), key=natkey)
            if not d.startswith(('_', '.')) and os.path.isdir(os.path.join(path, d))]


def model_href(code, parts):
    """The model's typed page: <folder>/index.html, else PAGES/<code>.html, else the folder"""
    if exists(*parts, 'index.html'):
        return href(*parts, 'index.html')
    if exists('PAGES', code + '.html'):
        return href('PAGES', code + '.html')
    return href(*parts) + '/'


def best_pdf(*parts):
    """The module's own PDF to jump straight to: a manual first, then a data sheet / brochure, the biggest of a kind."""
    folder, found = os.path.join(ROOT, *parts), []
    if not os.path.isdir(folder):
        return None
    for root, _, fs in os.walk(folder):
        for f in fs:
            if f.lower().endswith('.pdf'):
                n = f.lower()
                rank = 0 if re.search(r'manual|tech|instruction|service', n) else 1 if re.search(r'data|spec|brochure|sheet', n) else 2
                p = os.path.join(root, f)
                found.append((rank, -os.path.getsize(p), os.path.relpath(p, ROOT).replace(os.sep, '/')))
    return min(found)[2] if found else None


def model_entry(*parts):
    code = parts[-1]
    return {'code': code, 'name': names.get(code, ''), 'files': count_files(os.path.join(ROOT, *parts))[0], 'year': years.get(code),
            'wiki': exists('PAGES', code + '.md'), 'design': code in design, 'href': model_href(code, parts),
            'subs': subs.get(code, []), 'category': parts[-2] if len(parts) > 1 else '', 'pdf': best_pdf(*parts)}


def grouped(base):
    """<base>/<CATEGORY>/<code>/ -> [{name, models}]"""
    return [{'name': cat, 'models': [model_entry(base, cat, m) for m in visible_dirs(base, cat)]}
            for cat in visible_dirs(base)]


# (page title, categories); Consoles/Models/<code>/ is one flat category
groups = [('Modules by Category', grouped('Modules')),
          ('Products by Series', grouped('Products')),
          ('Console Models', [{'name': 'Consoles', 'models': sorted([model_entry('Consoles', 'Models', m)   # by year, oldest first
                                                               for m in visible_dirs('Consoles', 'Models')], key=lambda m: (m['year'] or 9999, m['code']))}])]


def transformer_cats():
    """Ward-Beck transformer types (60-n input, 70-n output, 80-n power) from the registers, with the modules using them."""
    db = os.path.join(ROOT, 'timelines', 'wbs_timeline.db')
    try:
        con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        items = con.execute("SELECT item, family, title, year, files FROM reg_items WHERE family LIKE '%transformers%'").fetchall()
        used = {}
        for item, code in con.execute('SELECT DISTINCT item, code FROM reg_used'):
            used.setdefault(item, []).append(code)
    except sqlite3.Error:
        return []
    key = lambda it: (int(it.split('-')[0]), int(it.split('-')[1]))
    page = href('PAGES', 'Transformers.html') if exists('PAGES', 'Transformers.html') else href('PAGES', 'Registers.html')
    cats = []
    for fam, label in (('Input', '60-x Series input transformers'), ('Output', '70-x Series output transformers'), ('Power', '80-x Series power transformers')):
        rows = sorted((r for r in items if r[1].startswith(fam)), key=lambda r: key(r[0]))
        cats.append({'name': label, 'models': [
            {'code': it, 'name': (title or '').title(), 'files': len(json.loads(fl or '[]')), 'year': yr, 'wiki': False,
             'design': False, 'href': page + '#' + it.lower(), 'subs': [], 'used': sorted(used.get(it, []), key=natkey)}
            for it, _, title, yr, fl in rows]})
    return cats


groups.insert(1, ('Transformers', transformer_cats()))   # its own tab: the transformers are Ward-Beck folklore
groups = [(t, [c for c in cats if c['models']]) for t, cats in groups]
groups = [(t, cats) for t, cats in groups if cats]
model_page = {m['code']: m['href'] for t, cats in groups if t != 'Transformers' for c in cats for m in c['models']}
categories = [c for _, cats in groups for c in cats]

n_models = sum(len(c['models']) for c in categories)
n_files = sum(m['files'] for c in categories for m in c['models'])

# contents entries: (title, what it is, path, ready?)
entries = [
    ('Build status', 'live progress of the OCR and rebuild jobs, refreshed every minute',
     'status.html', exists('status.html')),
    ('Search', 'every file in the archive by name, model, year, note and OCR text, with thumbnails',
     'search.html', exists('search.html')),
    ('Timeline', 'every module, job and console placed by year, with the source of each date',
     'timelines/timeline.html', exists('timelines', 'timeline.html')),
    ('Wiki', 'one page per device, job, year and category', 'Home.html' if exists('Home.html') else 'Home.md', exists('Home.md')),
    ('Parts', 'part naming, shelf locations, parts by device and full inventory', 'PARTS.html' if exists('PARTS.html') else 'PARTS.md',
     exists('PARTS.md')),
    ('Transformers', 'Ward-Beck\'s own transformers: 60-n input, 70-n output, 80-n power types, their drawings and the modules built with them',
     'PAGES/Transformers.html', exists('PAGES', 'Transformers.html')),
    ('Registers', 'transformers (60/70/80-n), circuit boards, sub-assemblies and mechanical parts, and where each is used',
     'PAGES/Registers.html', exists('PAGES', 'Registers.html')),
    ('Device Simulations', 'one second of each product in slow motion: front panel, operator tutorial, block diagram, schematics and how each button drives the firmware',
     'siumulation-index.html', exists('siumulation-index.html')),
    ('RTO-144 Connections', 'rear connector, inputs and outputs, and pin tables for every module on the RTO-144 jumper board',
     'Engineering/RTO-144/index.html', exists('Engineering', 'RTO-144', 'index.html')),
    ('Boards in KiCad', 'the original Tango-PCB board files converted to KiCad, with top and bottom renders',
     'Engineering/PCB/index.html', exists('Engineering', 'PCB', 'index.html')),
    ('Gerbers and Plots', 'the photoplots, drill tapes and pen plots sent out to be made, drawn live from the original files',
     'Engineering/CAM/index.html', exists('Engineering', 'CAM', 'index.html')),
    ('OrCAD Schematics', 'the OrCAD schematics, netlists and bills of materials, read live from the original files',
     'Engineering/ORCAD/index.html', exists('Engineering', 'ORCAD', 'index.html')),
    ('Engineering', 'schematics redrawn in KiCad, SPICE models and parts lists', 'Engineering/', bool(design - {'RTO-144', 'PCB', 'CAM', 'Plots', 'ORCAD'})),
]
entries += [(name.title(), f'{count_files(os.path.join(ROOT, name))[0]} files', name + '/', True)
            for name in ('Products', 'Consoles', 'ADVERTISEMENTS') if exists(name)]

today = datetime.date.today()


def logo_svg():
    """WBS_Logo.svg inlined in the text colour, so CSS can tint it."""
    if not exists('WBS_Logo.svg'):
        return 'WBS'
    s = open(os.path.join(ROOT, 'WBS_Logo.svg')).read()
    s = s[s.index('<svg'):].replace('#231f20', 'currentColor')
    return re.sub(r'<svg [^>]*>(<title[^<]*</title>)?', '<svg xmlns="http://www.w3.org/2000/svg" viewBox="178 214 437 183" aria-hidden="true">', s, 1).strip()


def thanks():
    """Names listed as '- name' in THANKS.md."""
    if not exists('THANKS.md'):
        return []
    return [l[2:].strip() for l in open(os.path.join(ROOT, 'THANKS.md')) if l.startswith('- ')]


LOGO = logo_svg()
names = thanks()
THANKS = (f'''<h3 class="sect"><u>Special Thanks:</u></h3>
    <p class="para">This archive is kept online with help from these people:</p>
    <ul class="thanks">{"".join(f"<li>{e(n)}</li>" for n in names)}</ul>''' if names else '')


def contents_item(i, title, text, path, ready):
    name = f'<a href="{e(path)}" title="{e(text)}">{e(title)}</a>' if ready else f'<span title="{e(text)}">{e(title)}</span>'
    state = '' if ready else ' <span class="stamp">in preparation</span>'
    return f'<li><span class="ix">{chr(97 + i)})</span><span class="it">{name}{state}</span></li>'


def family_name(code):
    """A model with no name of its own takes its family's (M166A → M166's), as the row above shows it."""
    fam = re.match(r'[A-Za-z]*\d+', code)
    if not fam:
        return ''
    N = MODEL_NAMES
    same = sorted((c for c in N if c != code and re.match(r'[A-Za-z]*\d+', c) and re.match(r'[A-Za-z]*\d+', c).group() == fam.group() and N[c]),
                  key=lambda c: (len(c), c))
    return N[same[0]] if same else ''


def model_row(m):
    wiki = href('PAGES', m['code'] + '.html') if exists('PAGES', m['code'] + '.html') else None
    pdf = m.get('pdf')
    pdf_link = f' <a class="pdf" href="viewer.html?f={quote(pdf)}" title="Straight to its PDF: {e(os.path.basename(pdf))}">PDF</a>' if pdf else ''
    marks = ((f'<a href="{wiki}" title="wiki page">W</a>' if wiki else 'W') if m['wiki'] else '') + \
            (f' <a href="{href("Engineering", m["code"])}/" title="KiCad / SPICE design">K</a>' if m['design'] else '')
    sb = m.get('subs', [])
    sub_html = ''
    if sb:   # sub-assemblies, boards and transformers this model uses (strongest evidence first)
        shown = [f'<a href="{register_href(it, fam)}" title="{e(fam)}">{e(it)}</a>' + (f' {e(t.title()[:34])}' if t else '')
                 for it, t, fam in sb[:4]]
        sub_html = '<span class="subs">↳ ' + ' · '.join(shown) + (f' · +{len(sb) - 4}' if len(sb) > 4 else '') + '</span>'
    if m.get('used'):   # transformers: the modules they were built into
        shown = [f'<a href="{model_page[c]}">{e(c)}</a>' if c in model_page else e(c) for c in m['used'][:8]]
        sub_html = '<span class="subs">↳ used in ' + ' · '.join(shown) + (f' · +{len(m["used"]) - 8}' if len(m['used']) > 8 else '') + '</span>'
    key = (m["code"] + " " + m["name"] + " " + " ".join(it + " " + t for it, t, _ in sb) + " " + " ".join(m.get('used', []))).lower()
    tr = TRACED.get(m['code'])
    trace = f' data-tr="{tr[0]}" data-trw="{tr[1]}" data-trh="{tr[2]}"' if tr else ''
    return (f'<li class="row" data-code="{e(key)}" data-m="{e(m["code"])}" data-n="{e(m["name"])}" data-cat="{e(m.get("category", ""))}"{trace}><a href="{m["href"]}">{e(m["code"])}</a>' +
            f'<span class="ti">{e(m["name"] or family_name(m["code"]))}{pdf_link}</span>'   # line 1: model, name and its PDF, across the row
            f'<span class="nm">{sub_html}</span>{context_html(m["code"]) if not m.get("used") else "<span></span>"}'   # line 2
            f'<span>{wy(m["year"])}</span><span>{m["files"]}</span><span>{marks}</span></li>')


def cat_html(cats):
    return '\n'.join(
        f'<section class="cat" data-cat><h3><u>{e(spaced_name(c["name"]))}</u>'
        f'<span>{len(c["models"])}</span></h3>'
        f'<ul class="tab"><li class="row head"><span>Model</span><span>Name</span><span title="consoles / jobs it was built into, and other drawings that show it">Module in context</span><span>Year</span><span>Files</span><span>Notes</span></li>'
        f'{"".join(model_row(m) for m in c["models"])}</ul></section>'
        for c in cats)


FIND = '''<div class="find">
      <label for="q">Find model:</label>
      <input id="q" type="search" placeholder="M441M or summing" autocomplete="off" spellcheck="false">
      <span id="count" aria-live="polite"></span>
      <ol id="hits" hidden></ol>
    </div>'''
LEGEND = ('<p class="legend">Notes:&nbsp; W = wiki page &nbsp; K = KiCad / SPICE design files<br>'
          'Year is written YYYY|n: n years since Ward-Beck opened in 1967|0. "--" until the timeline build has dated the model.</p>')
ROWS_PER_PAGE = 28  # what fits on a typed 8.5 x 11 sheet


def spaced(text):
    return "&nbsp;&nbsp;".join(e(w) for w in text.split())


# one letter page per category; long categories run on to "(continued)" sheets
sheets = []  # (group title, category, models, continued?)
for title, cats in groups:
    for c in cats:
        # a model with sub-items or a long name (about 22 characters to a line) takes extra typed lines; fill each sheet by lines, not by models
        lines = lambda m: 1 + max(0, len(m['name']) - 1) // 22 + (1 if context.get(m['code'], ([], 0))[0] and context.get(m['code'], ([], 0))[1] and not m.get('subs') else 0) + (min(4, len(m.get('subs', []))) + 1) // 2 + (1 if m.get('subs') else 0) + (1 if m.get('used') else 0)
        chunk, used, start = [], 0, 0
        models = c['models']
        for i, m in enumerate(models):
            if chunk and used + lines(m) > ROWS_PER_PAGE:
                sheets.append((title, c['name'], chunk, start > 0, len(models), True))
                chunk, used, start = [], 0, i
            chunk.append(m)
            used += lines(m)
        if chunk:
            sheets.append((title, c['name'], chunk, start > 0, len(models), False))
# the console models come first, before the modules (the binder's order), in the sheets and in the contents
_con = [x for x in sheets if x[0].lower().startswith('console')]
sheets = _con + [x for x in sheets if x not in _con]
groups = [g for g in groups if g[0].lower().startswith('console')] + [g for g in groups if not g[0].lower().startswith('console')]
FIRST = 3  # 1 menu, 2 about
first_page = {}
for n, (title, cat, *_) in enumerate(sheets):
    first_page.setdefault((title, cat), FIRST + n)

index_rows = []
for title, cats in groups:
    index_rows.append(f'<li class="grp">{e(title)}</li>')
    for c in cats:
        index_rows.append(f'<li class="lead" data-cat-link="{e(c["name"])}"><a href="#p{first_page[(title, c["name"])]}">'
                          f'{e(re.sub(r"(?<=\d)-X", "-x", spaced_name(c["name"]).title()))}</a><span class="dots" aria-hidden="true"></span>'
                          f'<span class="cnt">{len(c["models"])}</span><span class="pg">{first_page[(title, c["name"])]}</span></li>')
sheet_index = (f'<ol class="leaders">{"".join(index_rows)}</ol>')


PANEL_TPL = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'panel_tpl.js'), encoding='utf-8').read()
SIM = os.path.join(ROOT, 'timelines', 'simulator_template.html')
if os.path.exists(SIM):   # the simulator's panel layouts, kept in step with it
    _s = open(SIM, encoding='utf-8').read()
    if 'const TPL =' in _s and 'function freqFromSlider' in _s:
        PANEL_TPL = _s[_s.index('const TPL ='):_s.index('function freqFromSlider')].strip()


def panel_crop(svg_text):
    """Box (x, y, w, h) of the module's front panel in a traced sheet: the largest tall-and-narrow outline in its line work."""
    d = re.search(r'<path class="line" d="([^"]+)"', svg_text)
    if not d:
        return None
    boxes = []
    for sub in re.split(r'(?=M)', d.group(1)):
        nums = [float(v) for v in re.findall(r'-?\d+\.?\d*', sub)]
        xs, ys = nums[0::2], nums[1::2]
        if len(xs) >= 2 and len(ys) >= 2:
            boxes.append((min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
    if not boxes:
        return None
    sheet = max(max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes))
    best, best_n = None, 0
    for x, y, w, h in boxes:
        short, long = min(w, h), max(w, h)
        if short < .04 * sheet or not 3 <= long / short <= 14:   # a module panel: tall and narrow, not a leader line or the border
            continue
        # the panel is the outline with the most drawn parts (knobs, keys, meters) inside it
        n = sum(1 for bx, by, bw, bh in boxes
                if .12 * short <= max(bw, bh) and bw < .9 * w and bh < .9 * h and x <= bx and bx + bw <= x + w and y <= by and by + bh <= y + h)
        if n > best_n:
            best, best_n = (x, y, w, h), n
    return best if best_n >= 6 else None   # an empty outline says nothing: keep the simulator's panel


def traced_panels():
    """Front-panel drawings that the tracer turned into vectors, cropped to the panel: _catalog/panels/<code>.svg.
    Returns {code: (href, w, h)}; the margin shows these in place of the simulator's drawn panel."""
    traces = {}
    tdir = os.path.join(ROOT, '_catalog', 'traces')
    if not os.path.isdir(tdir):
        return {}
    for f in sorted(os.listdir(tdir)):
        if f.endswith('.json'):
            traces.update(json.load(open(os.path.join(tdir, f))))
    out_dir = os.path.join(ROOT, '_catalog', 'panels')
    os.makedirs(out_dir, exist_ok=True)
    found = {}
    for path, (sha, _) in sorted(traces.items()):
        parts = path.split('/')
        if parts[0] != 'Modules' or len(parts) < 4 or 'FRONT PANEL' not in parts[-1].upper():
            continue
        code = parts[2]
        src = os.path.join(ROOT, '_traces', sha + '.svg')
        if code in found or not os.path.exists(src):
            continue
        text = open(src, encoding='utf-8').read()
        box = panel_crop(text)
        if not box:
            continue
        x, y, w, h = box
        pad = 0.04 * max(w, h)
        x, y, w, h = x - pad, y - pad, w + 2 * pad, h + 2 * pad
        line = re.search(r'<path class="line" d="[^"]+"', text).group(0)
        if w > h:   # drawn sideways on the sheet: stand it up like the module
            body = f'<g transform="translate(0 {w:.0f}) rotate(-90) translate({-x:.0f} {-y:.0f})">{line} fill="#1c1c1c"/></g>'
            w, h = h, w
        else:
            body = f'<g transform="translate({-x:.0f} {-y:.0f})">{line} fill="#1c1c1c"/></g>'
        with open(os.path.join(out_dir, code + '.svg'), 'w', encoding='utf-8') as f:
            f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" data-from="{e(path)}">{body}</svg>')
        found[code] = (href('_catalog', 'panels', code + '.svg'), round(w), round(h))
    return found


# Traced panels checked by eye against their drawings. The crop finds the panel by shape, and on a sheet that is mostly
# dimensions or a title block it can land on the wrong outline, so only these replace the simulator's drawing. Add codes as they are checked.
PANELS_CHECKED = {'M405', 'M445', 'M460M', 'M490', 'M924'}
TRACED = {c: v for c, v in traced_panels().items() if c in PANELS_CHECKED}


def sheet(n, title, cat, models, cont, total, more):
    group = title.split(' by ')[0] if ' by ' in title else title
    head = f'{group} · {spaced_name(cat)}' + (' (continued)' if cont else '')
    return f'''<article class="page sheet" id="p{n}">
    <div class="toner" aria-hidden="true"></div><div class="scan" aria-hidden="true"></div>
    <svg class="fp" aria-hidden="true"></svg>
    <a class="letterhead" href="#p1" title="Back to the index">
      <div class="mark" role="img" aria-label="Ward-Beck Systems">{LOGO}</div>
      <p>WBSps.ca Archive Index<br><small>The records of Ward-Beck Systems Limited, Scarborough, Ontario</small></p>
    </a>
    <h2 class="title"><u>{spaced(head)}</u></h2>
    <section class="cat" data-cat><h3><u>{e(spaced_name(cat))}</u><span>{total} models</span></h3>
    <ul class="tab"><li class="row head"><span>Model</span><span>Name</span><span title="consoles / jobs it was built into, and other drawings that show it">Module in context</span><span>Year</span><span>Files</span><span>Notes</span></li>
    {"".join(model_row(m) for m in models)}</ul></section>
    {f'<p class="cont">- continued on page {n + 1} -</p>' if more else ''}
    <a class="back" href="#p1">&larr; Index</a>
    <div class="folio">- {n} -</div>
  </article>'''


listing_pages = '\n'.join(sheet(FIRST + n, *s) for n, s in enumerate(sheets))
contents = ''.join(contents_item(i, *x) for i, x in enumerate(entries))

page = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>WBSps Archive 2026</title>
<link rel="icon" href="WBS_Logo.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Courier+Prime:ital,wght@0,400;0,700;1,400&family=Michroma&display=swap">
<style>
/* Layout: a black vinyl WBS binder (spine card + logo) holding typewritten letter-size pages. Single look by design. */
:root {{
  --vinyl: #141414; --welt: #2a2a2a; --card: #ebe5cf; --paper: #fbfaf4; --type: #1c1c1c;
  --faint: #6d6a63; --rule: #1c1c1c; --stamp: #a52a22; --link: #1c1c1c; --logo: #c9c9c9;
  --typewriter: "Courier Prime", "Courier New", Courier, monospace;
  --logotype: "Michroma", "Eurostile", "Arial Black", sans-serif;
  color-scheme: dark;
}}
* {{ box-sizing: border-box }}
html {{ background: var(--vinyl) }}
body {{ margin: 0; color: var(--type); font: 16px/1.5 var(--typewriter);
  background: var(--vinyl) url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'><filter id='v'><feTurbulence type='fractalNoise' baseFrequency='1.4' numOctaves='3'/><feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .05 0'/></filter><rect width='100%' height='100%' filter='url(%23v)'/></svg>");
  padding-block: 28px 60px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)) }}
a {{ color: var(--link); text-decoration-thickness: 1px; text-underline-offset: 3px }}
a:hover {{ background: #efe9d2 }}
a:focus-visible, input:focus-visible {{ outline: 2px dashed var(--type); outline-offset: 3px }}
u {{ text-decoration-thickness: 1.5px; text-underline-offset: 4px }}

.binder {{ margin: 0 auto; display: grid; gap: 40px 34px; justify-items: center; justify-content: center;
  grid-template-columns: minmax(0, 8.5in) }}
.binder > .spine {{ grid-column: 1 / -1 }}
@media (min-width: 700px) {{ .binder {{ zoom: var(--z, 1); grid-template-columns: repeat(auto-fit, 8.5in) }} }}
.spine .by small {{ display: block; font-size: 14px; letter-spacing: .1em; text-transform: none; opacity: .8 }}
.spine .by a {{ color: inherit }}
.spine .by {{ color: var(--logo); text-transform: uppercase; text-align: center; letter-spacing: .14em; font-size: 20px; line-height: 1.9; margin: 0;
  writing-mode: vertical-rl; transform: rotate(180deg); margin-block: auto }}
/* the spine is one screen tall and is the measuring stick: it stands for an 11.5in binder, so --z scales every sheet below to match */
.spine {{ width: min(100%, 3.75in); height: 11.5in; padding: 22px; border-radius: 6px; display: flex; flex-direction: column;
  justify-content: flex-start; align-items: center; gap: 26px;
  background: #1b1b1b; box-shadow: inset 0 0 0 3px #101010, inset 0 0 0 7px var(--welt), inset 0 0 0 9px #0d0d0d }}
.window {{ width: 100%; padding: 12px; border-radius: 4px; background: #0e0e0e;
  box-shadow: inset 0 0 0 2px #2c2c2c, inset 0 6px 14px rgba(0,0,0,.8) }}
.card {{ background: var(--card); color: var(--type); text-align: center; text-transform: uppercase; padding: 22px 12px;
  font-size: 15px; line-height: 1.35; display: grid; gap: 16px; box-shadow: inset 0 0 18px rgba(120,100,50,.25) }}
.card p {{ margin: 0 }}
.logo {{ width: 82%; color: var(--logo) }}
.logo svg, .mark svg {{ display: block; width: 100%; height: auto }}
.mark {{ width: min(60%, 260px); margin: 0 auto 1.6em; color: var(--type) }}
.thanks {{ list-style: none; margin: 0; padding: 0; columns: 2 16ch; column-gap: 2em }}
.thanks li {{ padding-left: 2ch; text-indent: -2ch; break-inside: avoid }}
.thanks li::before {{ content: "- " }}

.page {{ position: relative; width: 100%; max-width: 8.5in; background: var(--paper); color-scheme: light;
  padding: clamp(28px, 7vw, 76px) clamp(20px, 8vw, 84px) 64px clamp(34px, 10vw, 104px);
  box-shadow: 0 1px 0 #d8d4c6, 0 18px 40px rgba(0,0,0,.55); overflow: hidden }}
.page {{ min-height: calc(min(100vw - 32px, 8.5in) * 11 / 8.5) }}
/* standard letter 3-hole punch: 5/16in holes, centres 1/2in from the edge, 4 1/4in apart at 1 1/4, 5 1/2 and 9 3/4in down */
.page::before {{ content: ""; position: absolute; left: .25in; top: 0; width: .5in; height: 11in;
  background: radial-gradient(circle at 50% 1.25in, var(--vinyl) .15625in, rgba(0,0,0,.18) .17in, transparent .19in),
              radial-gradient(circle at 50% 5.5in, var(--vinyl) .15625in, rgba(0,0,0,.18) .17in, transparent .19in),
              radial-gradient(circle at 50% 9.75in, var(--vinyl) .15625in, rgba(0,0,0,.18) .17in, transparent .19in) }}
/* a sheet on the right of a two-page spread is punched on its right edge: the binder's rings are on that side */
.page.right {{ padding-left: clamp(20px, 8vw, 84px); padding-right: clamp(34px, 10vw, 104px) }}
.page.right::before {{ left: auto; right: .25in }}
/* a module's front panel, drawn as a CAD line drawing in the margin beside its row (the simulator's panel layouts) */
.sheet .fp {{ position: absolute; left: .78in; width: .6in; top: 1.2in; height: auto; overflow: visible; transition: top .25s ease; pointer-events: none }}
.page.right .fp {{ left: .2in }}
.fp .ln {{ fill: none; stroke: var(--type); stroke-width: 1.1 }} .fp .fi {{ fill: var(--type) }}
.fp text {{ fill: var(--type); font-family: Arial, sans-serif; font-weight: 700; text-anchor: middle }}
@media (min-width: 700px) {{ .page.sheet:not(.right) {{ padding-left: 1.5in }} .page.sheet.right {{ padding-left: .95in }} }}
@media (max-width: 699px) {{ .sheet .fp {{ display: none }} }}
.folio {{ position: absolute; left: 0; right: 0; bottom: 22px; text-align: center }}
.page h1, .page h2, .page h3 {{ font: inherit; margin: 0 }}

.cover {{ min-height: min(11in, 130vw); display: flex; flex-direction: column; justify-content: space-between; align-items: center; text-align: center }}
.cover h1 {{ margin-top: 22%; text-transform: uppercase; line-height: 2.2 }}
.address {{ text-align: left; display: grid; gap: 1.2em }}
.address p {{ margin: 0; white-space: pre }}
.by {{ text-align: center }}

.title {{ text-align: center; text-transform: uppercase; margin-bottom: 2.4em !important }}
.sect {{ margin: 2em 0 1em !important }}
.contents {{ list-style: none; margin: 0; padding: 0; display: grid; gap: .25em }}
.contents li {{ display: grid; grid-template-columns: 3.5em 1fr }}
.contents .desc {{ display: block; color: var(--faint) }}
.stamp {{ display: inline-block; margin-left: .6em; color: var(--stamp); border: 2px solid; padding: 0 .4em; text-transform: uppercase;
  font-size: 12px; font-weight: 700; letter-spacing: .08em; transform: rotate(-3deg); opacity: .85 }}
.para {{ max-width: 60ch; margin: 0 0 1em }}
.facts {{ display: grid; grid-template-columns: max-content 1fr; gap: .2em 2em; margin: 0 }}
.facts dt {{ margin: 0 }} .facts dd {{ margin: 0 }}

.find {{ display: flex; flex-wrap: wrap; gap: .4em 1em; align-items: baseline; margin-bottom: 1.6em }}
#q {{ font: inherit; color: var(--type); background: transparent; border: 0; border-bottom: 1.5px solid var(--rule);
  padding: 0 4px; width: 20ch; max-width: 100% }}
#count {{ color: var(--faint) }}
#hits {{ flex-basis: 100%; list-style: none; margin: .4em 0 0; padding: 0; border-left: 1.5px solid var(--type); padding-left: 1em }}
#hits li {{ display: grid; grid-template-columns: 9ch minmax(0, 1fr) auto; gap: 0 1.2ch; line-height: 1.7 }}
#hits .pg {{ color: var(--faint) }}
.row.flash {{ animation: flash 2.4s ease-out }}
@keyframes flash {{ 0%, 30% {{ background: #f3e7a6 }} 100% {{ background: transparent }} }}
.cat {{ margin-bottom: 2em; break-inside: avoid }}
.leaders {{ list-style: none; margin: 0 0 1.6em; padding: 0 }}
.leaders .grp {{ margin: 1.2em 0 .3em; text-transform: uppercase; text-decoration: underline; text-underline-offset: 4px }}
.lead {{ display: flex; align-items: baseline; gap: 1ch }}
.lead.head {{ color: var(--faint) }}
.lead a {{ white-space: nowrap }}
.lead .dots {{ flex: 1; border-bottom: 2px dotted var(--faint); transform: translateY(-4px); min-width: 2ch }}
.lead .cnt {{ width: 6ch; text-align: right }}
.lead .pg {{ width: 4ch; text-align: right }}
.lead.none {{ opacity: .35 }}
.cont {{ text-align: center; margin: 1.4em 0 0 }}
.back {{ position: absolute; left: clamp(34px, 10vw, 104px); bottom: 22px }}
.window {{ display: block; text-decoration: none; color: inherit }}
.letterhead {{ color: inherit; text-decoration: none }} .letterhead:hover {{ background: transparent }} .letterhead:hover p {{ text-decoration: underline }}
.letterhead {{ display: flex; gap: 14px; align-items: center; margin-bottom: 1.6em; font-size: 14px; line-height: 1.35 }}
.letterhead .mark {{ width: 70px; flex: none }}
.letterhead small {{ color: var(--faint) }}
.menu .contents li {{ grid-template-columns: 3em 1fr }}
.menu .leaders {{ columns: 2 18ch; column-gap: 3ch }}
.menu .leaders li {{ break-inside: avoid }}
.menu .lead .cnt {{ display: none }}
/* typed: every character sits on the baseline and margin; only the ink density varies (script below) */
.page {{ text-shadow: 0 0 .45px rgba(28,28,28,.55) }}
.tw {{ opacity: var(--ink, 1) }}
.tw.hard {{ text-shadow: .35px 0 0 rgba(28,28,28,.8), 0 0 .5px rgba(28,28,28,.6) }}
@media print {{ .page {{ break-after: page; box-shadow: none; transform: none }} }}
.cat h3 {{ display: flex; justify-content: space-between; text-transform: uppercase; margin-bottom: .5em }}
.cat h3 span {{ color: var(--faint) }}
.tab {{ list-style: none; margin: 0; padding: 0 }}
.row {{ display: grid; grid-template-columns: 9ch minmax(0, 1fr) 11ch 8ch 5ch 6ch; gap: 0 1.2ch; font-variant-numeric: tabular-nums; align-items: baseline }}
.row .nm {{ min-width: 0 }}
.row .ti {{ grid-column: 2 / -1; font-weight: 700 }}   /* line 1: the name (and its PDF) across the row, only wrapping when it must */
.row .ti {{ text-decoration: underline; text-decoration-thickness: 1.5px; text-underline-offset: 3px }} .row .ti .pdf {{ margin-left: .6em }}
.row .ti + .nm {{ grid-column: 2 }}   /* line 2: parts, then context, year, files, notes */
.row .pdf {{ font-weight: 700; letter-spacing: .04em }}
.row .ctx {{ font-size: 12.5px; line-height: 1.35 }}
.row .subs {{ display: block; font-size: 12.5px; line-height: 1.35; color: var(--faint); margin: 1px 0 3px }}
.row .subs a {{ color: inherit }}
.row.head {{ color: var(--faint) }}
.row.head span {{ text-decoration: underline; text-underline-offset: 3px }}
.legend {{ color: var(--faint); margin-top: 2.4em }}

/* photocopy toner and the scanner bar, once per page, as it comes into view */
.toner, .scan {{ position: absolute; pointer-events: none }}
.toner {{ inset: 0; opacity: .09;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2'/><feColorMatrix values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -1.4 .62'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>") }}
.scan {{ left: 0; right: 0; height: 120px; top: -130px;
  background: linear-gradient(to bottom, transparent, rgba(150,210,255,.18) 75%, rgba(225,245,255,.6) 94%, transparent) }}
@media (prefers-reduced-motion: no-preference) {{
  .page.scanned .toner {{ animation: toner 2.2s ease-out both }}   /* "scanned": the sheet came into view (wbs_scan.js) */
  .page.scanned .scan {{ animation: scan 1.6s .5s ease-in both }}
  .page:nth-of-type(2) .toner {{ animation-delay: .5s }} .page:nth-of-type(2) .scan {{ animation-delay: 1s }}
  .page:nth-of-type(3) .toner {{ animation-delay: 1s }}  .page:nth-of-type(3) .scan {{ animation-delay: 1.5s }}
}}
@keyframes toner {{ 0% {{ opacity: 0 }} 35% {{ opacity: .38 }} 100% {{ opacity: .09 }} }}
@keyframes scan {{ to {{ top: 100% }} }}
@media (max-width: 560px) {{
  .page::before {{ display: none }}
  .row {{ grid-template-columns: 8ch minmax(0, 1fr) 8ch; font-size: 14px }}
  .row > span:nth-child(3), .row > span:nth-child(5), .row > span:nth-child(6) {{ display: none }}
  .contents li {{ grid-template-columns: 2.5em 1fr }}
}}
</style>
</head>
<body>
<div class="binder">
  <div class="spine" aria-label="Binder spine">
    <div class="logo" role="img" aria-label="Ward-Beck Systems">{LOGO}</div>
    <a class="window" href="#p1" title="Open the index"><div class="card">
      <p>WBSps.ca</p>
      <p>Archive<br>Index</p>
      <p>Modules · Consoles<br>Parts · Drawings</p>
      <p>Volume<br>2026</p>
    </div></a>
    <p class="by">An archive by Anthony Peter Kuzub
      <small><a href="https://wbsps.kuzub.com">WBSps.Kuzub.com</a> · <a href="https://wbsps.ca">WBSps.ca</a></small></p>
  </div>

  <article class="page menu" id="p1">
    <div class="toner" aria-hidden="true"></div><div class="scan" aria-hidden="true"></div>
    <a class="letterhead" href="#p1" title="Back to the index">
      <div class="mark" role="img" aria-label="Ward-Beck Systems">{LOGO}</div>
      <p>WBSps.ca Archive Index<br><small>The records of Ward-Beck Systems Limited, Scarborough, Ontario</small></p>
    </a>
    <h2 class="title"><u>Index</u></h2>
    {FIND}
    <h3 class="sect"><u>Contents:</u></h3>
    <ol class="contents">{contents}</ol>
    <h3 class="sect"><u>Sheets:</u></h3>
    {sheet_index}
    {LEGEND}
    <div class="folio">- 1 -</div>
  </article>

  <article class="page" id="p2">
    <a class="letterhead" href="#p1" title="Back to the index">
      <div class="mark" role="img" aria-label="Ward-Beck Systems">{LOGO}</div>
      <p>WBSps.ca Archive Index<br><small>The records of Ward-Beck Systems Limited, Scarborough, Ontario</small></p>
    </a>
    <div class="toner" aria-hidden="true"></div><div class="scan" aria-hidden="true"></div>
    <h2 class="title"><u>WBSps.ca&nbsp;&nbsp;Archive&nbsp;&nbsp;Index</u></h2>
    <h3 class="sect"><u>General Description:</u></h3>
    <p class="para">This archive holds the manuals, drawings, photographs and parts records of Ward-Beck broadcast equipment, sorted by model and by year. Every file was copied from the WBSps.ca collection; the originals are kept unchanged.</p>
    <h3 class="sect"><u>Archive Data:</u></h3>
    <dl class="facts">
      <dt>Models:</dt><dd>{n_models} in {len(categories)} categories</dd>
      <dt>Files:</dt><dd>{n_files:,}</dd>
      <dt>Issued:</dt><dd>{today:%B %d, %Y} by make_index.py</dd>
    </dl>
    {THANKS}
    <a class="back" href="#p1">&larr; Index</a>
    <div class="folio">- 2 -</div>
  </article>

  {listing_pages}
</div>
<script src="_catalog/wbs_panel.js"></script>
<script>
// scale the binder so the spine (11.5in) fills one screen; on phones the sheets stay fluid
function fit() {{
  const wide = innerWidth >= 700;
  const z = wide ? Math.min((innerHeight - 88) / (11.5 * 96), (innerWidth - 32) / (8.5 * 96)) : 1;
  document.documentElement.style.setProperty('--z', Math.max(.4, z).toFixed(4));
}}
fit(); addEventListener('resize', fit);
const q = document.getElementById('q'), count = document.getElementById('count');
q.addEventListener('input', () => {{
  const term = q.value.trim().toLowerCase();
  let shown = 0;
  document.querySelectorAll('[data-cat]').forEach(sec => {{
    let n = 0;
    sec.querySelectorAll('.row[data-code]').forEach(r => {{
      const hit = !term || r.dataset.code.includes(term);
      r.hidden = !hit; n += hit;
    }});
    sec.hidden = n === 0; shown += n;
    const sheet = sec.closest('.sheet');
    if (sheet) sheet.hidden = n === 0;
  }});
  document.querySelectorAll('[data-cat-link]').forEach(li => {{
    const name = li.dataset.catLink;
    const any = [...document.querySelectorAll('.sheet')].some(p => !p.hidden && p.querySelector('h3 u').textContent === name.replace(/-(?!x\\b)/g, ' '));
    li.classList.toggle('none', !!term && !any);
  }});
  count.textContent = term ? shown + (shown === 1 ? ' match' : ' matches') + (shown ? ' — press Enter to go to the first' : '') : '';
  // the matches as an index of their own: model, name, sheet — each one takes you there
  const rows = term ? [...document.querySelectorAll('.row[data-code]:not([hidden])')].filter(r => r.closest('.sheet')) : [];
  hits.hidden = !rows.length;
  hits.innerHTML = rows.slice(0, 15).map((r, i) => {{
    const page = r.closest('.page'), code = r.querySelector('a').textContent;
    const nm = (r.querySelector('.ti')?.textContent || '').trim();
    return `<li><a href="#${{page.id}}" data-i="${{i}}">${{code}}</a><span>${{nm}}</span><span class="pg">page ${{page.id.slice(1)}}</span></li>`;
  }}).join('') + (rows.length > 15 ? `<li><span></span><span class="pg">…and ${{rows.length - 15}} more on the sheets below</span><span></span></li>` : '');
  hitRows = rows;
}});
let hitRows = [];
const hits = document.getElementById('hits');
function goTo(r) {{
  if (!r) return;
  r.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
  r.classList.remove('flash'); void r.offsetWidth; r.classList.add('flash');
  history.replaceState(null, '', '#' + r.closest('.page').id);
}}
hits.addEventListener('click', ev => {{
  const a = ev.target.closest('a[data-i]');
  if (!a) return;
  ev.preventDefault();
  goTo(hitRows[+a.dataset.i]);
}});
q.addEventListener('keydown', ev => {{ if (ev.key === 'Enter') {{ ev.preventDefault(); goTo(hitRows[0]); }} }});
// Spreads: a sheet that does not sit in the left-hand column is a right-hand page (holes on its right edge).
(() => {{
  const pages = [...document.querySelectorAll('.page')];
  const mark = () => {{
    pages.forEach(p => p.classList.remove('right'));
    const left = Math.min(...pages.map(p => p.getBoundingClientRect().left));
    pages.forEach(p => p.classList.toggle('right', p.getBoundingClientRect().left > left + 20));
  }};
  mark();
  addEventListener('resize', mark);
}})();
// The spine is the cover: show it once. A reader who has already seen it opens on the first spread, pages 1/2.
try {{
  if (!location.hash && localStorage.getItem('wbs-seen-spine')) document.getElementById('p1').scrollIntoView();
  localStorage.setItem('wbs-seen-spine', '1');
}} catch (err) {{}}
// Front panels in the margin, beside the row the reader is on (drawn by _catalog/wbs_panel.js, wbsPanel)
(() => {{
  const draw = window.wbsPanel;
  if (!draw) return;
  document.querySelectorAll('.page.sheet').forEach(page => {{
    const svg = page.querySelector('.fp'), rows = [...page.querySelectorAll('.row[data-m]')];
    if (!svg || !rows.length) return;
    const show = r => {{
      if (svg.dataset.m !== r.dataset.m) {{
        if (r.dataset.tr) {{   // the traced CAD of its own front-panel drawing, when there is one
          const w = +r.dataset.trw, h = +r.dataset.trh;
          svg.setAttribute('viewBox', `0 0 ${{w}} ${{h}}`);
          svg.innerHTML = `<image href="${{r.dataset.tr}}" width="${{w}}" height="${{h}}"/>`;
        }} else draw(svg, r.dataset);
        svg.dataset.m = r.dataset.m;
      }}
      const pr = page.getBoundingClientRect(), rr = r.getBoundingClientRect(), z = pr.height / page.offsetHeight || 1;
      const h = svg.getBoundingClientRect().height / z;
      svg.style.top = Math.max(24, Math.min(page.offsetHeight - h - 40, (rr.top - pr.top) / z - 6)) + 'px';
    }};
    show(rows[0]);
    page.addEventListener('mouseover', e => {{ const r = e.target.closest('.row[data-m]'); if (r) show(r); }});
    page.addEventListener('focusin', e => {{ const r = e.target.closest('.row[data-m]'); if (r) show(r); }});
  }});
}})();

// Typewriter: each character gets a repeatable ink density and the odd hard strike; position is never altered,
// so the type stays straight and aligned. Seeded from position and character, so it never shimmers.
(() => {{
  const rnd = n => {{ n = Math.imul(n ^ (n >>> 15), 2246822507); n = Math.imul(n ^ (n >>> 13), 3266489909); return ((n ^ (n >>> 16)) >>> 0) / 4294967296; }};
  let seq = 0;
  document.querySelectorAll('.page').forEach(page => {{
    const walker = document.createTreeWalker(page, NodeFilter.SHOW_TEXT, {{
      acceptNode: t => t.parentElement.closest('script, style, input, .toner, .scan') || !t.textContent.trim()
        ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT }});
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(t => {{
      const frag = document.createDocumentFragment();
      for (const ch of t.textContent) {{
        if (ch.trim() === '') {{ frag.appendChild(document.createTextNode(ch)); continue; }}
        const r2 = rnd(++seq * 17 + ch.charCodeAt(0)), r3 = rnd(seq * 13 + 3);
        const sp = document.createElement('span');
        sp.className = 'tw' + (r3 > .965 ? ' hard' : '');
        sp.style.setProperty('--ink', (.8 + r2 * .2).toFixed(2));
        sp.textContent = ch;
        frag.appendChild(sp);
      }}
      t.replaceWith(frag);
    }});
  }});
}})();
</script>
<script src="_catalog/wbs_scan.js"></script>
</body>
</html>
'''

out = os.path.join(ROOT, 'index.html')
with open(out, 'w') as f:
    f.write(page)
print(f'wrote {out}: {n_models} models in {len(categories)} categories, {n_files} files')
